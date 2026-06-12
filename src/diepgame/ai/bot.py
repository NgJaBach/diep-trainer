"""Bot controller: drives a Tank with simple but effective behaviors.

States: FARM (grind shapes), ATTACK (push a weaker enemy), FLEE (low hp or
outmatched). Bots also allocate skill points along per-archetype build
orders and pick class upgrades automatically.
"""
from __future__ import annotations
import math
import random
from ..core.vector import Vec2
from ..entities.tank import Tank
from ..tanks.definitions import TANK_DEFS
from .. import config as C

# stat priority orders by archetype (indices into the 8-stat array)
BUILDS = {
    "bullet":  [6, 5, 4, 3, 7, 1, 0, 2],   # reload, dmg, pen, speed...
    "sniper":  [5, 4, 3, 6, 7, 1, 0, 2],
    "drone":   [5, 4, 3, 6, 1, 0, 7, 2],
    "body":    [7, 2, 1, 0, 3, 4, 5, 6],   # rammer
    "drift":   [7, 6, 5, 4, 1, 0, 3, 2],   # booster-style
}

ARCHETYPE = {
    "basic": "bullet", "twin": "bullet", "triple_shot": "bullet",
    "triplet": "bullet", "penta_shot": "bullet", "spread_shot": "bullet",
    "quad_tank": "bullet", "octo_tank": "bullet", "twin_flank": "bullet",
    "triple_twin": "bullet", "machine_gun": "bullet", "sprayer": "bullet",
    "gunner": "bullet", "gunner_trapper": "bullet", "destroyer": "bullet",
    "annihilator": "bullet", "hybrid": "bullet", "streamliner": "bullet",
    "sniper": "sniper", "assassin": "sniper", "ranger": "sniper",
    "stalker": "sniper", "hunter": "sniper", "predator": "sniper",
    "overseer": "drone", "overlord": "drone", "manager": "drone",
    "battleship": "drone", "trapper": "drone", "tri_trapper": "drone",
    "mega_trapper": "drone", "overtrapper": "drone",
    "flank_guard": "bullet", "tri_angle": "drift", "booster": "drift",
    "fighter": "drift",
    "smasher": "body", "spike": "body", "landmine": "body",
}


class BotController:
    def __init__(self, world, tank: Tank, skill: float = 1.0):
        self.world = world
        self.tank = tank
        self.skill = skill                       # 0.5 timid .. 1.5 aggressive
        self.think_timer = random.uniform(0, C.BOT_THINK_INTERVAL)
        self.state = "FARM"
        self.target = None                       # entity being pursued
        self.wander = Vec2.from_angle(random.uniform(0, math.tau))
        self.aim_jitter = random.uniform(0.5, 1.0) * (2.0 - skill)
        self.respawn_timer = 0.0
        self.preferred_branch = random.choice(
            ["twin", "sniper", "machine_gun", "flank_guard"])

    # ------------------------------------------------------------------
    def update(self, dt: float):
        t = self.tank
        if not t.alive:
            return
        self.think_timer -= dt
        if self.think_timer <= 0:
            self.think_timer = C.BOT_THINK_INTERVAL
            self._think()
        self._act(dt)

    # ------------------------------------------------------------- brain ----
    def _think(self):
        t = self.tank
        self._spend_points()
        self._maybe_upgrade_class()

        hp_frac = t.health / t.max_health
        enemy = self._pick_enemy()

        if hp_frac < 0.3:
            self.state, self.target = "FLEE", enemy
            return
        if enemy is not None:
            my_power = t.score + 200
            their_power = enemy.score + 200
            dist = t.pos.dist_to(enemy.pos)
            if their_power > my_power * (2.2 - 0.6 * self.skill) and dist < 700:
                self.state, self.target = "FLEE", enemy
                return
            if (their_power < my_power * (1.1 + 0.5 * self.skill)
                    and dist < 900 * self.skill):
                self.state, self.target = "ATTACK", enemy
                return
        # otherwise: farm
        self.state = "FARM"
        self.target = self._pick_shape()

    def _pick_enemy(self):
        t = self.tank
        candidates = self.world.tanks_near(t.pos, 1100, exclude_team=t.team)
        visible = [c for c in candidates if c.invisible_alpha > 0.25]
        if not visible:
            return None
        return min(visible, key=lambda c: c.pos.dist_sq_to(t.pos))

    def _pick_shape(self):
        t = self.tank
        shapes = self.world.shapes_near(t.pos, 850)
        # crashers are dangerous food; deprioritize for weak bots
        def value(s):
            d = max(60.0, s.pos.dist_to(t.pos))
            risk = 2.0 if s.is_crasher and t.level < 10 else 1.0
            big = 3.0 if s.shape_type == "alpha_pentagon" and t.level < 25 else 1.0
            return (s.xp_value / d) / (risk * big)
        if shapes:
            return max(shapes, key=value)
        return None

    def _spend_points(self):
        t = self.tank
        order = BUILDS[ARCHETYPE.get(t.def_key, "bullet")]
        guard = 0
        while t.stat_points > 0 and guard < 40:
            guard += 1
            for idx in order:
                if t.stats[idx] < C.MAX_STAT and t.upgrade_stat(idx):
                    break
            else:
                break

    def _maybe_upgrade_class(self):
        t = self.tank
        opts = t.available_upgrades()
        if not opts:
            return
        if t.def_key == "basic" and self.preferred_branch in opts:
            t.upgrade_class(self.preferred_branch)
        else:
            t.upgrade_class(random.choice(opts))

    # -------------------------------------------------------------- body ----
    def _act(self, dt: float):
        t = self.tank
        target = self.target if (self.target and self.target.alive) else None
        move = Vec2()

        if self.state == "FLEE" and target is not None:
            move = (t.pos - target.pos).normalized()
            self._aim_at(target)
            t.shooting = True            # shoot while retreating
        elif self.state == "ATTACK" and target is not None:
            d = t.pos.dist_to(target.pos)
            ideal = self._ideal_range()
            direction = (target.pos - t.pos).normalized()
            if d > ideal:
                move = direction
            elif d < ideal * 0.6:
                move = -direction
            # strafe
            strafe = Vec2(-direction.y, direction.x)
            move += strafe * math.sin(self.world.time * 1.7 + t.id)
            self._aim_at(target)
            t.shooting = True
        elif target is not None:   # FARM
            move = (target.pos - t.pos).normalized()
            self._aim_at(target)
            t.shooting = t.pos.dist_to(target.pos) < 700
        else:
            # wander, drifting back toward the arena's inner area
            if random.random() < 0.02:
                self.wander = Vec2.from_angle(random.uniform(0, math.tau))
            center_pull = (self.world.center - t.pos)
            if center_pull.length() > C.ARENA_SIZE * 0.45:
                self.wander = center_pull.normalized()
            move = self.wander
            t.shooting = False

        # rammers always charge
        if ARCHETYPE.get(t.def_key) == "body" and target is not None \
                and self.state != "FLEE":
            move = (target.pos - t.pos).normalized()

        t.move_input = move
        t.repelling = False

    def _ideal_range(self) -> float:
        a = ARCHETYPE.get(self.tank.def_key, "bullet")
        return {"bullet": 420, "sniper": 640, "drone": 520,
                "body": 0, "drift": 220}[a]

    def _aim_at(self, target):
        t = self.tank
        # lead the target based on bullet travel time
        d = t.pos.dist_to(target.pos)
        bspd = max(120.0, t.bullet_speed())
        lead = target.pos + target.vel * (d / bspd) * 0.85
        err = self.aim_jitter * 0.06
        ang = (lead - t.pos).angle() + random.uniform(-err, err)
        t.aim_angle = ang


class BotManager:
    """Keeps BOT_COUNT bots alive; respawns them after a delay."""

    def __init__(self, world):
        self.world = world
        self.controllers: list[BotController] = []
        self.pending: list[tuple[float, str, float, int]] = []  # time, name, skill, lvl
        self._used_names = set()

    def spawn_initial(self):
        names = random.sample(C.BOT_NAMES, C.BOT_COUNT)
        for n in names:
            lvl = random.randint(1, 18)
            self._spawn(n, random.uniform(0.6, 1.4), lvl)

    def _spawn(self, name, skill, level):
        tank = self.world.spawn_tank(name, def_key="basic", level=level)
        ctrl = BotController(self.world, tank, skill)
        ctrl._spend_points()
        ctrl._maybe_upgrade_class()
        self.controllers.append(ctrl)

    def update(self, dt: float):
        now = self.world.time
        for c in list(self.controllers):
            if not c.tank.alive:
                self.controllers.remove(c)
                respawn_lvl = max(1, min(15, c.tank.level // 2))
                self.pending.append((now + C.BOT_RESPAWN_DELAY, c.tank.name,
                                     c.skill, respawn_lvl))
            else:
                c.update(dt)
        for item in list(self.pending):
            when, name, skill, lvl = item
            if now >= when:
                self.pending.remove(item)
                self._spawn(name, skill, lvl)
