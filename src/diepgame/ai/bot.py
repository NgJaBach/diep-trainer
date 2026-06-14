"""Bot controller: drives a Tank with perception, dodging and class tactics.

States: FARM (grind shapes), ATTACK (push an enemy), FLEE (low hp or
outmatched, with heal-up hysteresis). On top of the state machine bots:

  * dodge incoming bullets every frame (sidestep along the perpendicular
    of the bullet's closest-approach path; big shells weighted heavier)
  * score targets instead of taking the nearest: wounded enemies and weaker
    tanks are preferred, locked targets are sticky, the player can be
    prioritized via config.BOT_PLAYER_FOCUS
  * never break off a kill: an enemy under 30% hp is chased down even when
    the bot itself is hurt
  * keep class-appropriate range, orbit-strafe with random direction flips,
    and weave while ramming
  * hold huge shells (Destroyer line) until the target is in range
  * use drone repel to screen retreats and to meet charging rammers
  * lead shots with a two-pass intercept solve and steer clear of the wall

Bots allocate skill points along per-archetype build orders and pick class
upgrades along weighted favorite paths. Difficulty knobs live in config.py
(BOT_AGGRESSION, BOT_DODGE, respawn level scaling, ...).
"""
from __future__ import annotations
import math
import random
from ..core.vector import Vec2
from ..entities.tank import Tank
from .. import config as C

# stat priority orders by archetype (indices into the 8-stat array)
BUILDS = {
    "bullet":  [6, 5, 4, 3, 7, 1, 0, 2],   # reload, dmg, pen, speed...
    "sniper":  [5, 4, 3, 6, 7, 1, 0, 2],
    "drone":   [5, 4, 3, 6, 1, 0, 7, 2],
    "trap":    [6, 5, 4, 1, 0, 3, 7, 2],
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
    "battleship": "drone", "necromancer": "drone",
    "trapper": "trap", "tri_trapper": "trap", "mega_trapper": "trap",
    "overtrapper": "trap",
    "flank_guard": "bullet", "tri_angle": "drift", "booster": "drift",
    "fighter": "drift",
    "smasher": "body", "spike": "body", "landmine": "body",
}

# upgrade-pick weights; unlisted classes default to 2
CLASS_WEIGHTS = {
    "overseer": 5, "overlord": 6, "necromancer": 4, "annihilator": 5,
    "destroyer": 4,
    "fighter": 5, "booster": 4, "triplet": 5, "penta_shot": 4,
    "octo_tank": 4, "streamliner": 5, "tri_angle": 4, "spike": 3,
    "twin": 3, "sniper": 3, "machine_gun": 3, "hunter": 3, "gunner": 3,
    "ranger": 3, "hybrid": 3, "spread_shot": 3,
}

# classes whose single shell is too precious to spray at nothing
BIG_SHOT = {"destroyer", "annihilator", "hybrid"}

IDEAL_RANGE = {"bullet": 420, "sniper": 680, "drone": 540,
               "trap": 240, "body": 0, "drift": 200}


class BotController:
    def __init__(self, world, tank: Tank, skill: float = 1.0):
        self.world = world
        self.tank = tank
        self.skill = skill                       # 0.5 timid .. 1.6 fierce
        self.think_timer = random.uniform(0, C.BOT_THINK_INTERVAL)
        self.state = "FARM"
        self.target = None                       # entity being pursued
        self.target_lock = 0.0                   # stickiness timer
        self.recover_frac = 0.0                  # heal to this before re-engaging
        self.strafe_dir = random.choice((-1.0, 1.0))
        self.strafe_timer = random.uniform(0.8, 2.2)
        self.wander = Vec2.from_angle(random.uniform(0, math.tau))
        self.aim_jitter = max(0.05, random.uniform(0.4, 1.0) * (1.6 - skill))
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

        hp = t.health / t.max_health
        enemy, engage = self._pick_enemy()

        # blood in the water: a nearly dead enemy is worth almost any risk
        finishing = (enemy is not None
                     and enemy.health < enemy.max_health * 0.30
                     and t.pos.dist_to(enemy.pos) < 820)

        if self.state == "FLEE":
            if enemy is None or (hp >= self.recover_frac
                                 and not self._overmatched(enemy)):
                self.state = "FARM"
            else:
                self.target = enemy
                return

        flee_at = max(0.12, 0.40 - 0.16 * self.skill * C.BOT_AGGRESSION)
        threatened = enemy is not None and t.pos.dist_to(enemy.pos) < 700
        if threatened and not finishing \
                and (hp < flee_at or self._overmatched(enemy)):
            self.state = "FLEE"
            self.recover_frac = min(0.9, hp + 0.35)
            self.target = enemy
            return

        if enemy is not None and engage and (hp > flee_at + 0.1 or finishing):
            self.state = "ATTACK"
            self.target = enemy
            self.target_lock = 1.5
            return

        self.state = "FARM"
        self.target = self._pick_shape()

    def _power(self, t: Tank) -> float:
        # judge threat mostly by level (what a real player can see) so a fat
        # score doesn't make everyone too scared to ever challenge the leader
        return 150.0 * t.level + min(t.score, 3000.0) + 200.0

    def _overmatched(self, enemy) -> bool:
        if enemy is None:
            return False
        courage = 1.6 + 0.8 * min(self.skill * C.BOT_AGGRESSION, 1.8)
        return self._power(enemy) > self._power(self.tank) * courage

    def _pick_enemy(self):
        """Returns (best_enemy_or_None, engage_bool)."""
        t = self.tank
        rng = 1000 + 250 * C.BOT_AGGRESSION
        cands = self.world.tanks_near(t.pos, rng, exclude_team=t.team)
        cands = [c for c in cands if c.invisible_alpha > 0.25]
        if not cands:
            return None, False
        cur = self.target if isinstance(self.target, Tank) else None
        best, best_s = None, 0.0
        for c in cands:
            d = max(80.0, t.pos.dist_to(c.pos))
            s = 900.0 / d
            if c.health < c.max_health * 0.45:
                s *= 1.8                       # wounded: finish the job
            if self._overmatched(c):
                s *= 0.25
            elif self._power(c) < self._power(t):
                s *= 1.4                       # prey
            if c.is_player:
                s *= C.BOT_PLAYER_FOCUS
            if c is cur:
                s *= 1.5 if self.target_lock > 0 else 1.15
            if s > best_s:
                best, best_s = c, s
        d = t.pos.dist_to(best.pos)
        wounded = best.health < best.max_health * 0.45
        engage = d < 900 * self.skill * C.BOT_AGGRESSION or wounded
        return best, engage

    def _pick_shape(self):
        t = self.tank
        shapes = self.world.shapes_near(t.pos, 900)
        hp = t.health / max(1.0, t.max_health)

        def value(s):
            d = max(60.0, s.pos.dist_to(t.pos))
            v = s.xp_value / d
            if s.is_crasher and (t.level < 10 or hp < 0.5):
                v *= 0.3                       # dangerous food
            if s.shape_type == "alpha_pentagon" and t.level < 28:
                v *= 0.25
            if s.shape_type == "pentagon" and t.level >= 15:
                v *= 1.6                       # leveled bots camp the nest
            if s.shape_type == "boss_guardian" and (t.level < 25 or hp < 0.6):
                v *= 0.05                      # don't feed the boss
            return v
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
            return
        weights = [CLASS_WEIGHTS.get(k, 2) for k in opts]
        t.upgrade_class(random.choices(opts, weights=weights)[0])

    # -------------------------------------------------------------- body ----
    def _act(self, dt: float):
        t = self.tank
        self.target_lock = max(0.0, self.target_lock - dt)
        self.strafe_timer -= dt
        if self.strafe_timer <= 0:
            self.strafe_timer = random.uniform(0.8, 2.2)
            self.strafe_dir = -self.strafe_dir

        target = self.target if (self.target and self.target.alive) else None
        move = Vec2()
        t.repelling = False

        if self.state == "FLEE" and target is not None:
            move = (t.pos - target.pos).normalized()
            self._aim_at(target)
            t.shooting = True            # shoot while retreating
            if t.tdef.max_drones > 0:
                t.repelling = True       # drones screen the retreat
                t.shooting = False
        elif self.state == "ATTACK" and target is not None:
            move = self._combat_move(target)
            self._aim_at(target)
            t.shooting = self._trigger(target)
            if (t.tdef.max_drones > 0
                    and ARCHETYPE.get(target.def_key) == "body"
                    and t.pos.dist_to(target.pos)
                    < t.radius + target.radius + 160):
                t.repelling = True       # throw drones into a charging rammer
        elif target is not None:   # FARM
            d = target.pos - t.pos
            move = d.normalized() if d.length() > 120 else Vec2()
            self._aim_at(target)
            t.shooting = d.length() < 650
        else:
            # wander, drifting back toward the arena's inner area
            if random.random() < 0.02:
                self.wander = Vec2.from_angle(random.uniform(0, math.tau))
            center_pull = (self.world.center - t.pos)
            if center_pull.length() > C.ARENA_SIZE * 0.45:
                self.wander = center_pull.normalized()
            move = self.wander
            t.shooting = False
            t.aim_target = None
            t.aim_angle = self.wander.angle()

        dodge = self._dodge_vector()
        if dodge is not None:
            k = 1.2 * min(1.5, C.BOT_DODGE * (0.4 + 0.6 * self.skill))
            move = move * 0.55 + dodge * k

        move += self._border_push()
        t.move_input = move

    def _combat_move(self, target) -> Vec2:
        t = self.tank
        d = t.pos.dist_to(target.pos)
        direction = (target.pos - t.pos).normalized()
        perp = Vec2(-direction.y, direction.x)
        arche = ARCHETYPE.get(t.def_key, "bullet")
        if arche == "body":
            # charge with a weave so bullet streams miss
            return direction + perp * (0.35 * self.strafe_dir)
        move = Vec2()
        ideal = IDEAL_RANGE[arche]
        if d > ideal * 1.1:
            move += direction
        elif d < ideal * 0.65:
            move -= direction
        move += perp * (0.8 * self.strafe_dir)
        if target.health < target.max_health * 0.3:
            move += direction * 0.6      # run the kill down
        return move

    def _trigger(self, target) -> bool:
        """Whether to hold the fire button this frame."""
        t = self.tank
        if t.def_key in BIG_SHOT:
            return t.pos.dist_to(target.pos) < 540
        return True

    def _dodge_vector(self):
        """Perpendicular escape vector for incoming bullets, or None."""
        t = self.tank
        if C.BOT_DODGE <= 0:
            return None
        acc = Vec2()
        n = 0
        for e in self.world.grid.query_circle(t.pos, 230 + t.radius):
            if e.kind != "bullet" or not e.alive or e.team == t.team:
                continue
            r = e.pos - t.pos
            v = e.vel - t.vel
            vv = v.length_sq()
            if vv < 1600 or r.dot(v) >= 0:      # slow or moving away
                continue
            tca = -r.dot(v) / vv                # time of closest approach
            if tca > 0.9:
                continue
            closest = r + v * tca               # offset at closest approach
            if closest.length() > t.radius + e.radius + 26:
                continue
            perp = Vec2(-v.y, v.x).normalized()
            if perp.dot(closest) > 0:
                perp = -perp                    # step away from the path
            w = (1.0 - tca / 0.9) * (2.2 if e.radius > 13 else 1.0)
            acc += perp * w
            n += 1
            if n >= 6:
                break
        return acc.normalized() if n else None

    def _border_push(self) -> Vec2:
        t = self.tank
        m = 160.0
        push = Vec2()
        if t.pos.x < m:
            push.x += 1
        elif t.pos.x > C.ARENA_SIZE - m:
            push.x -= 1
        if t.pos.y < m:
            push.y += 1
        elif t.pos.y > C.ARENA_SIZE - m:
            push.y -= 1
        return push * 0.9

    def _aim_at(self, target):
        t = self.tank
        if ARCHETYPE.get(t.def_key) == "drone":
            # drones home continuously; aim at a lightly-led position
            lead = target.pos + target.vel * 0.2
        else:
            # two-pass intercept solve on bullet travel time
            bspd = max(140.0, t.bullet_speed())
            lead = target.pos
            for _ in range(2):
                lead = target.pos + target.vel * (t.pos.dist_to(lead) / bspd)
        err = self.aim_jitter * 0.05
        t.aim_angle = (lead - t.pos).angle() + random.uniform(-err, err)
        t.aim_target = lead                     # drones fly to the intercept


class BotManager:
    """Keeps BOT_COUNT bots alive; respawns them after a delay."""

    def __init__(self, world):
        self.world = world
        self.controllers: list[BotController] = []
        self.pending: list[tuple[float, str, float, int]] = []  # time, name, skill, lvl

    def spawn_initial(self):
        names = random.sample(C.BOT_NAMES, min(C.BOT_COUNT, len(C.BOT_NAMES)))
        while len(names) < C.BOT_COUNT:
            names.append(f"Bot{len(names) + 1}")
        for n in names:
            lvl = random.randint(*C.BOT_SPAWN_LEVELS)
            self._spawn(n, random.uniform(*C.BOT_SKILL_RANGE), lvl)

    def _spawn(self, name, skill, level):
        tank = self.world.spawn_tank(name, def_key="basic", level=level,
                                     team=self.world.bot_team())
        ctrl = BotController(self.world, tank, skill)
        ctrl._spend_points()
        ctrl._maybe_upgrade_class()
        self.controllers.append(ctrl)

    def _respawn_level(self, died_at: int) -> int:
        top = max((t.level for t in self.world.tanks if t.alive), default=1)
        floor = int(top * C.BOT_CATCHUP_FACTOR)
        lvl = max(died_at * 2 // 3, floor, 6)
        return min(C.BOT_RESPAWN_LEVEL_CAP, lvl)

    def update(self, dt: float):
        now = self.world.time
        for c in list(self.controllers):
            if not c.tank.alive:
                self.controllers.remove(c)
                self.pending.append((now + C.BOT_RESPAWN_DELAY, c.tank.name,
                                     c.skill, self._respawn_level(c.tank.level)))
            else:
                c.update(dt)
        for item in list(self.pending):
            when, name, skill, lvl = item
            if now >= when:
                self.pending.remove(item)
                self._spawn(name, skill, lvl)
