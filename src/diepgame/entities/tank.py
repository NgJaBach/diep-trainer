"""The Tank entity: player and bots both use this class.

Handles stat allocation, leveling, barrel reload cycles, projectile
spawning, recoil, drone command routing and class upgrades.
"""
from __future__ import annotations
import math
import random
from .base import Entity
from .projectiles import Bullet, Trap, Drone
from ..core.vector import Vec2
from ..tanks.definitions import TANK_DEFS, Barrel
from .. import config as C


class BarrelState:
    __slots__ = ("spec", "cooldown")

    def __init__(self, spec: Barrel, base_interval: float):
        self.spec = spec
        self.cooldown = spec.delay * base_interval * spec.reload


class Tank(Entity):
    kind = "tank"

    def __init__(self, world, pos: Vec2, name: str, team: int,
                 def_key: str = "basic", is_player: bool = False,
                 color=None):
        self.def_key = def_key
        self.tdef = TANK_DEFS[def_key]
        self.level = 1
        self.score = 0.0
        self.stats = [0] * 8
        self.stat_points = 0
        super().__init__(world, pos, C.TANK_BASE_RADIUS, team,
                         self._compute_max_hp(), C.TANK_BASE_BODY_DMG)
        self.name = name
        self.is_player = is_player
        self.color = color or (C.COL_PLAYER if is_player else C.COL_ENEMY)
        self.aim_angle = 0.0
        self.move_input = Vec2()        # unit-ish input vector
        self.shooting = False
        self.repelling = False          # right-click for drone classes
        self.auto_fire = False
        self.auto_spin = False
        self.kills = 0
        self.friction = 7.5
        self.push_factor = 0.9
        self.barrel_states: list[BarrelState] = []
        self.drones: list[Drone] = []
        self.invisible_alpha = 1.0      # 1 = fully visible
        self.idle_timer = 0.0
        self.recoil_vel = Vec2()
        self.pending_class_choice = False
        self._rebuild_barrels()
        self._refresh_derived()

    # ----------------------------------------------------------- derived ----
    def _compute_max_hp(self) -> float:
        mult = TANK_DEFS[self.def_key].max_health_mult
        return (C.TANK_BASE_HP + C.TANK_HP_PER_LEVEL * (self.level - 1)
                + C.TANK_HP_PER_STAT * self.stats[1]) * mult

    def _refresh_derived(self):
        frac = 1.0 if self.max_health <= 0 else self.health / self.max_health
        self.max_health = self._compute_max_hp()
        self.health = self.max_health * max(0.05, frac)
        self.body_damage = (C.TANK_BASE_BODY_DMG
                            + C.TANK_BODY_DMG_PER_STAT * self.stats[2]) \
            * self.tdef.body_damage_mult
        self.regen_rate = C.TANK_REGEN_BASE + C.TANK_REGEN_PER_STAT * self.stats[0]
        self.radius = C.TANK_BASE_RADIUS + C.TANK_RADIUS_PER_LEVEL * (self.level - 1)

    def _rebuild_barrels(self):
        self.tdef = TANK_DEFS[self.def_key]
        base = self.reload_interval()
        self.barrel_states = [BarrelState(b, base) for b in self.tdef.barrels]

    # ------------------------------------------------------------- stats ----
    def move_speed(self) -> float:
        return (C.TANK_BASE_SPEED
                * (1.0 + C.TANK_SPEED_PER_STAT * self.stats[7])
                * (1.0 - C.TANK_SPEED_LEVEL_DECAY * (self.level - 1))
                * self.tdef.speed_mult)

    def reload_interval(self) -> float:
        return C.BASE_RELOAD * (1.0 - C.RELOAD_PER_STAT * self.stats[6])

    def bullet_damage(self) -> float:
        return C.BULLET_BASE_DMG + C.BULLET_DMG_PER_STAT * self.stats[5]

    def bullet_hp(self) -> float:
        return C.BULLET_BASE_HP + C.BULLET_HP_PER_STAT * self.stats[4]

    def bullet_speed(self) -> float:
        return C.BULLET_BASE_SPEED + C.BULLET_SPEED_PER_STAT * self.stats[3]

    def upgrade_stat(self, idx: int) -> bool:
        if self.stat_points <= 0 or not (0 <= idx < 8):
            return False
        if self.stats[idx] >= C.MAX_STAT:
            return False
        self.stats[idx] += 1
        self.stat_points -= 1
        self._refresh_derived()
        return True

    # ---------------------------------------------------------- leveling ----
    def add_score(self, amount: float):
        self.score += amount
        while (self.level < C.LEVEL_CAP
               and self.score >= C.xp_for_level(self.level + 1)):
            self.level += 1
            self.stat_points += C.points_at_level(self.level)
            self._refresh_derived()
            self.heal(self.max_health * 0.1)
            if self.level in C.CLASS_UPGRADE_LEVELS and self.available_upgrades():
                self.pending_class_choice = True

    def available_upgrades(self) -> list[str]:
        """Class keys this tank may upgrade into at its current level."""
        out = []
        for key in self.tdef.upgrades_to:
            t = TANK_DEFS[key]
            need = C.CLASS_UPGRADE_LEVELS[min(t.tier - 2, 2)]
            if self.level >= need:
                out.append(key)
        return out

    def upgrade_class(self, key: str) -> bool:
        if key not in self.available_upgrades():
            return False
        # clear existing drones if the new class can't keep them
        self.def_key = key
        self._rebuild_barrels()
        self._refresh_derived()
        keep = self.tdef.max_drones
        while len(self.drones) > keep:
            self.drones.pop().alive = False
        self.pending_class_choice = bool(self.available_upgrades()) and \
            self.level in C.CLASS_UPGRADE_LEVELS
        self.pending_class_choice = False
        return True

    # ------------------------------------------------------------ drones ----
    def drone_command(self):
        """Returns (cmd, point) consumed by Drone.update each frame."""
        if self.repelling:
            return "repel", self.pos
        if self.shooting or self.auto_fire:
            return "attack", self.aim_point()
        return "idle", self.pos

    def aim_point(self) -> Vec2:
        return self.pos + Vec2.from_angle(self.aim_angle, 600.0)

    # ------------------------------------------------------------ firing ----
    def _spawn_projectile(self, spec: Barrel):
        ang = math.radians(spec.angle) + self.aim_angle
        if self.auto_spin and not spec.kind == "drone":
            ang = math.radians(spec.angle) + self.aim_angle
        direction = Vec2.from_angle(ang)
        perp = Vec2.from_angle(ang + math.pi / 2)
        muzzle = (self.pos
                  + direction * (self.radius * spec.length)
                  + perp * (self.radius * spec.lat))
        spread = math.radians(spec.spread)
        shot_ang = ang + random.uniform(-spread, spread)
        shot_dir = Vec2.from_angle(shot_ang)

        speed = self.bullet_speed() * spec.spd
        dmg = self.bullet_damage() * spec.dmg
        hp = self.bullet_hp() * spec.pen
        radius = self.radius * spec.width * 0.62 * spec.size

        if spec.kind == "trap":
            p = Trap(self.world, self, muzzle, shot_dir * (speed * 0.85),
                     radius, dmg, hp)
        elif spec.kind in ("drone", "swarm"):
            if len(self.drones) >= max(1, self.tdef.max_drones):
                return False
            p = Drone(self.world, self, muzzle, shot_dir * (speed * 0.6),
                      radius, dmg, hp, swarm=(spec.kind == "swarm"))
            self.drones.append(p)
        else:
            p = Bullet(self.world, self, muzzle,
                       shot_dir * speed + self.vel * 0.35, radius, dmg, hp)
        self.world.add(p)
        # recoil
        self.recoil_vel -= direction * (38.0 * spec.recoil)
        return True

    def update(self, dt: float):
        if not self.alive:
            return
        want_fire = self.shooting or self.auto_fire
        moving = self.move_input.length_sq() > 0.01

        # invisibility (stalker / manager / landmine)
        if self.tdef.invisible_when_idle:
            if moving or want_fire:
                self.idle_timer = 0.0
            else:
                self.idle_timer += dt
            target_alpha = 0.0 if self.idle_timer > 1.2 else 1.0
            rate = 1.6 * dt
            if self.invisible_alpha < target_alpha:
                self.invisible_alpha = min(target_alpha, self.invisible_alpha + rate)
            else:
                self.invisible_alpha = max(target_alpha, self.invisible_alpha - rate)
        else:
            self.invisible_alpha = 1.0

        # movement
        accel = self.move_speed() * 9.0
        self.vel += self.move_input.normalized() * (accel * dt)
        sp = self.vel.length()
        cap = self.move_speed()
        if sp > cap:
            self.vel = self.vel * (cap / sp)
        self.vel += self.recoil_vel
        self.recoil_vel = Vec2()

        if self.auto_spin:
            self.aim_angle += 1.4 * dt

        # fast regen after not being hit for a while
        if self.world.time - self.last_hit_time > C.TANK_FAST_REGEN_DELAY:
            self.heal(self.max_health * C.TANK_FAST_REGEN_RATE * dt)

        # barrels
        base = self.reload_interval()
        for bs in self.barrel_states:
            bs.cooldown -= dt
            fire = want_fire or bs.spec.auto_fire
            if bs.spec.kind in ("drone", "swarm"):
                fire = True  # spawners always try to refill
            if fire and bs.cooldown <= 0:
                if self._spawn_projectile(bs.spec):
                    bs.cooldown = base * bs.spec.reload
                else:
                    bs.cooldown = 0.15  # drone cap reached; retry soon
            if not fire and bs.cooldown < 0:
                bs.cooldown = 0.0

        super().update(dt)

    def die(self):
        for d in list(self.drones):
            d.alive = False
        self.drones.clear()
        super().die()
