"""Bot controller: a genome-parameterized brain with multi-threat awareness.

States: FARM (grind shapes), ATTACK (push an enemy), FLEE (low hp / outmatched
/ outnumbered, with heal-up hysteresis). On top of the state machine bots:

  * dodge incoming bullets (sidestep the closest-approach path of several at
    once; big shells weighted heavier)
  * stay un-surrounded: steer away from the *centroid* of nearby enemies and
    keep spacing from the nearest threat, scaled by how many are shooting
  * disengage when outnumbered instead of tunnel-visioning one target and
    eating crossfire (the classic "sneak attack" failure)
  * pick targets that are weak AND isolated, not the nearest one in a cluster
  * keep class-appropriate range, orbit-strafe, hold big Destroyer shells, and
    use drone repel to screen retreats / meet rammers

Everything tunable lives in the bot's :class:`Genome`; defaults already give
the above behaviors. The evolutionary trainer (tools/train.py) optimizes the
genome for kills + survival via an ELO ladder.
"""
from __future__ import annotations
import math
import random
from ..core.vector import Vec2
from ..entities.tank import Tank
from .genome import Genome, DEFAULT_GENOME
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

# base upgrade-pick weights; multiplied by the genome's archetype preference
CLASS_WEIGHTS = {
    "overseer": 5, "overlord": 6, "necromancer": 4, "annihilator": 5,
    "destroyer": 4, "fighter": 5, "booster": 4, "triplet": 5, "penta_shot": 4,
    "octo_tank": 4, "streamliner": 5, "tri_angle": 4, "spike": 3,
    "twin": 3, "sniper": 3, "machine_gun": 3, "hunter": 3, "gunner": 3,
    "ranger": 3, "hybrid": 3, "spread_shot": 3,
}

BIG_SHOT = {"destroyer", "annihilator", "hybrid"}

IDEAL_RANGE = {"bullet": 420, "sniper": 680, "drone": 540,
               "trap": 240, "body": 0, "drift": 200}

_PREF = {"bullet": "pref_bullet", "sniper": "pref_sniper",
         "drone": "pref_drone", "trap": "pref_drone", "body": "pref_body",
         "drift": "pref_bullet"}

SPECIES = ("bullet", "sniper", "drone", "trap", "body", "drift")


def _reachable_archetypes():
    """For each class, the set of archetypes reachable in its upgrade subtree.
    Lets a bot steer upgrades toward a target playstyle (used for speciated
    training so every archetype is actually exercised)."""
    from ..tanks.definitions import TANK_DEFS
    memo: dict[str, set] = {}

    def visit(key, stack):
        if key in memo:
            return memo[key]
        out = {ARCHETYPE.get(key, "bullet")}
        for nxt in TANK_DEFS[key].upgrades_to:
            if nxt not in stack:
                out |= visit(nxt, stack | {nxt})
        memo[key] = out
        return out

    for k in TANK_DEFS:
        visit(k, {k})
    return memo


REACHABLE = _reachable_archetypes()


class BotController:
    def __init__(self, world, tank: Tank, skill: float = 1.0, genome=None,
                 force_archetype: str | None = None):
        self.world = world
        self.tank = tank
        self.skill = skill
        self.g = genome or DEFAULT_GENOME
        self.force_archetype = force_archetype   # steer upgrades to this playstyle
        self.think_timer = random.uniform(0, C.BOT_THINK_INTERVAL)
        self.state = "FARM"
        self.target = None
        self.target_lock = 0.0
        self.recover_frac = 0.0
        self.strafe_dir = random.choice((-1.0, 1.0))
        self.strafe_timer = random.uniform(0.8, 2.2)
        self.wander = Vec2.from_angle(random.uniform(0, math.tau))
        acc = self.g["accuracy"]
        self.aim_jitter = max(0.03, (1.0 - 0.85 * acc)
                              * random.uniform(0.4, 1.0) * (1.6 - skill))
        self.preferred_branch = random.choice(
            ["twin", "sniper", "machine_gun", "flank_guard"])
        self.nearby: list = []           # visible enemy tanks (cached)
        self.centroid = None             # centroid of nearby enemies

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
        g = self.g
        self._spend_points()
        self._maybe_upgrade_class()

        hp = t.health / t.max_health
        enemy, engage = self._pick_enemy()
        n = len(self.nearby)

        finishing = (enemy is not None
                     and enemy.health < enemy.max_health * 0.30
                     and t.pos.dist_to(enemy.pos) < 780 and n <= 2)

        if self.state == "FLEE":
            healed = hp >= self.recover_frac
            if enemy is None or (healed and not self._overmatched(enemy)
                                 and n < g["outnumber"]):
                self.state = "FARM"
            else:
                self.target = enemy
                return

        base_flee = 0.40 - 0.16 * self.skill * C.BOT_AGGRESSION
        flee_at = max(0.10, base_flee * g["caution"])
        near = enemy is not None and t.pos.dist_to(enemy.pos) < 760
        outnumbered = n >= g["outnumber"]
        regen_want = hp < 0.55 and g["regen_kite"] > 0.8 and not finishing

        if near and not finishing and (hp < flee_at or self._overmatched(enemy)
                                       or outnumbered or regen_want):
            self.state = "FLEE"
            self.recover_frac = min(0.95, hp + 0.30 + 0.1 * g["regen_kite"])
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
        return t.score + 120.0 * t.level + 200.0

    def _overmatched(self, enemy) -> bool:
        if enemy is None:
            return False
        courage = 1.6 + 0.8 * min(self.skill * C.BOT_AGGRESSION
                                  * self.g["aggression"], 1.8)
        return self._power(enemy) > self._power(self.tank) * courage

    def _pick_enemy(self):
        """Cache nearby enemies; return (best_target, engage_bool).

        Targets are scored by closeness, woundedness and *isolation* — a weak
        tank alone is far better prey than a weak tank inside a cluster."""
        t = self.tank
        g = self.g
        rng = (1000 + 250 * C.BOT_AGGRESSION) * (0.8 + 0.3 * g["aggression"])
        cands = self.world.tanks_near(t.pos, rng, exclude_team=t.team)
        cands = [c for c in cands if c.invisible_alpha > 0.25]
        self.nearby = cands
        if not cands:
            self.centroid = None
            return None, False

        cx = sum(c.pos.x for c in cands) / len(cands)
        cy = sum(c.pos.y for c in cands) / len(cands)
        self.centroid = Vec2(cx, cy)

        cur = self.target if isinstance(self.target, Tank) else None
        best, best_s = None, 0.0
        for c in cands:
            d = max(80.0, t.pos.dist_to(c.pos))
            s = 900.0 / d
            if c.health < c.max_health * 0.45:
                s *= g["wounded"]
            if self._overmatched(c):
                s *= 0.22
            elif self._power(c) < self._power(t):
                s *= 1.4
            # mild isolation preference: nudge toward lone prey, but never
            # refuse a good target just because the brawl is crowded
            cluster = sum(1 for o in cands
                          if o is not c and o.pos.dist_to(c.pos) < 320)
            s /= (1.0 + g["spacing"] * 0.18 * min(cluster, 3))
            if c.is_player:
                s *= C.BOT_PLAYER_FOCUS
            if c is cur:
                s *= 1.0 + 0.5 * g["focus"] * (1.0 if self.target_lock > 0
                                               else 0.4)
            if s > best_s:
                best, best_s = c, s
        d = t.pos.dist_to(best.pos)
        wounded = best.health < best.max_health * 0.45
        reach = 900 * self.skill * C.BOT_AGGRESSION * g["aggression"]
        return best, (d < reach or wounded)

    def _pick_shape(self):
        t = self.tank
        g = self.g
        shapes = self.world.shapes_near(t.pos, 900)
        hp = t.health / max(1.0, t.max_health)

        def value(s):
            d = max(60.0, s.pos.dist_to(t.pos))
            v = s.xp_value / d
            if s.is_crasher and (t.level < 10 or hp < 0.5):
                v *= 0.3
            if s.shape_type == "alpha_pentagon" and t.level < 28:
                v *= 0.25
            if s.shape_type == "pentagon" and t.level >= 15:
                v *= 1.0 + 0.6 * g["nest_greed"]
            if s.shape_type == "boss_guardian" and (t.level < 25 or hp < 0.6):
                v *= 0.05
            return v
        return max(shapes, key=value) if shapes else None

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
        fa = self.force_archetype
        if fa is not None:
            # steer toward the species archetype: keep only options whose
            # subtree can still reach it, preferring ones that already are it
            viable = [k for k in opts if fa in REACHABLE.get(k, ())]
            pool = viable or opts
            now = [k for k in pool if ARCHETYPE.get(k) == fa]
            choices = now or pool
            weights = [CLASS_WEIGHTS.get(k, 2) for k in choices]
            t.upgrade_class(random.choices(choices, weights=weights)[0])
            return
        if t.def_key == "basic" and self.preferred_branch in opts:
            t.upgrade_class(self.preferred_branch)
            return
        weights = []
        for k in opts:
            arche = ARCHETYPE.get(k, "bullet")
            weights.append(CLASS_WEIGHTS.get(k, 2) * self.g[_PREF[arche]])
        t.upgrade_class(random.choices(opts, weights=weights)[0])

    # -------------------------------------------------------------- body ----
    def _act(self, dt: float):
        t = self.tank
        g = self.g
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
            t.shooting = True
            if t.tdef.max_drones > 0:
                t.repelling = True
                t.shooting = False
        elif self.state == "ATTACK" and target is not None:
            move = self._combat_move(target)
            self._aim_at(target)
            t.shooting = self._trigger(target)
            if (t.tdef.max_drones > 0
                    and ARCHETYPE.get(target.def_key) == "body"
                    and t.pos.dist_to(target.pos)
                    < t.radius + target.radius + 160):
                t.repelling = True
        elif target is not None:   # FARM
            d = target.pos - t.pos
            move = d.normalized() if d.length() > 120 else Vec2()
            self._aim_at(target)
            t.shooting = d.length() < 650
        else:
            if random.random() < 0.02:
                self.wander = Vec2.from_angle(random.uniform(0, math.tau))
            pull = (self.world.center - t.pos)
            if pull.length() > C.ARENA_SIZE * 0.45:
                self.wander = pull.normalized()
            move = self.wander
            t.shooting = False
            t.aim_target = None
            t.aim_angle = self.wander.angle()

        # ---- multi-threat steering: don't get surrounded ----
        move = move + self._threat_vector()

        dodge = self._dodge_vector()
        if dodge is not None:
            k = 1.2 * min(1.6, C.BOT_DODGE * g["dodge"] * (0.4 + 0.6 * self.skill))
            move = move * 0.5 + dodge * k

        move += self._border_push()
        t.move_input = move

    def _threat_vector(self) -> Vec2:
        """Reposition out of crossfire — but only when hurt or truly swarmed,
        so healthy bots stay aggressive and keep focus-firing."""
        t = self.tank
        g = self.g
        if ARCHETYPE.get(t.def_key) == "body":
            return Vec2()                       # rammers want to be close
        n = len(self.nearby)
        if n == 0:
            return Vec2()
        hp = t.health / max(1.0, t.max_health)
        out = Vec2()
        if (n >= 3 and self.centroid is not None
                and (hp < 0.6 or n >= g["outnumber"])):
            away = (t.pos - self.centroid)
            if away.length() > 1:
                out += away.normalized() * (0.5 * g["threat_avoid"] * (n - 2))
        # back off only if a threat is right on top of us
        nearest = min(self.nearby, key=lambda c: c.pos.dist_sq_to(t.pos))
        d = t.pos.dist_to(nearest.pos)
        keep = IDEAL_RANGE.get(ARCHETYPE.get(t.def_key, "bullet"), 420) \
            * g["range_bias"]
        if keep > 0 and d < keep * 0.5:
            out += (t.pos - nearest.pos).normalized() * (g["spacing"] * 0.5
                    * (1.0 - d / max(1.0, keep)))
        return out

    def _combat_move(self, target) -> Vec2:
        t = self.tank
        g = self.g
        d = t.pos.dist_to(target.pos)
        direction = (target.pos - t.pos).normalized()
        perp = Vec2(-direction.y, direction.x)
        arche = ARCHETYPE.get(t.def_key, "bullet")
        if arche == "body":
            return direction + perp * (0.35 * self.strafe_dir)
        move = Vec2()
        ideal = IDEAL_RANGE[arche] * g["range_bias"]
        if d > ideal * 1.1:
            move += direction
        elif d < ideal * 0.65:
            move -= direction
        move += perp * (g["strafe"] * self.strafe_dir)
        if target.health < target.max_health * 0.3 and len(self.nearby) <= 2:
            move += direction * 0.6
        return move

    def _trigger(self, target) -> bool:
        t = self.tank
        if t.def_key in BIG_SHOT:
            return t.pos.dist_to(target.pos) < 540 * self.g["discipline"]
        return True

    def _dodge_vector(self):
        t = self.tank
        if C.BOT_DODGE <= 0 or self.g["dodge"] <= 0:
            return None
        acc = Vec2()
        n = 0
        for e in self.world.grid.query_circle(t.pos, 240 + t.radius):
            if e.kind != "bullet" or not e.alive or e.team == t.team:
                continue
            r = e.pos - t.pos
            v = e.vel - t.vel
            vv = v.length_sq()
            if vv < 1600 or r.dot(v) >= 0:
                continue
            tca = -r.dot(v) / vv
            if tca > 0.9:
                continue
            closest = r + v * tca
            if closest.length() > t.radius + e.radius + 26:
                continue
            perp = Vec2(-v.y, v.x).normalized()
            if perp.dot(closest) > 0:
                perp = -perp
            w = (1.0 - tca / 0.9) * (2.2 if e.radius > 13 else 1.0)
            acc += perp * w
            n += 1
            if n >= 8:
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
            lead = target.pos + target.vel * 0.2
        else:
            bspd = max(140.0, t.bullet_speed())
            lead = target.pos
            for _ in range(2):
                lead = target.pos + target.vel * (t.pos.dist_to(lead) / bspd)
        err = self.aim_jitter * 0.05
        t.aim_angle = (lead - t.pos).angle() + random.uniform(-err, err)
        t.aim_target = lead


class BotManager:
    """Keeps BOT_COUNT bots alive; respawns them after a delay.

    If a trained population is provided, each bot is assigned a genome and
    displays its ELO in the name ("Vex — ELO 1240")."""

    def __init__(self, world, population=None):
        self.world = world
        self.population = population         # ai.population.Population or None
        self.controllers: list[BotController] = []
        self.pending: list[tuple] = []       # (time, name, skill, lvl, member)

    def spawn_initial(self):
        names = random.sample(C.BOT_NAMES, min(C.BOT_COUNT, len(C.BOT_NAMES)))
        while len(names) < C.BOT_COUNT:
            names.append(f"Bot{len(names) + 1}")
        for n in names:
            lvl = random.randint(*C.BOT_SPAWN_LEVELS)
            self._spawn(n, random.uniform(*C.BOT_SKILL_RANGE), lvl)

    def _spawn(self, name, skill, level, member=None):
        if member is None and self.population is not None:
            member = self.population.sample()
        if member is not None:
            disp = f"{name} — ELO {int(member['elo'])}"
            genome = Genome.from_dict(member["genome"])
            arche = member.get("archetype")
        else:
            disp, genome, arche = name, DEFAULT_GENOME, None
        tank = self.world.spawn_tank(disp, def_key="basic", level=level,
                                     team=self.world.bot_team())
        tank.member = member             # for live ELO updates, if any
        ctrl = BotController(self.world, tank, skill, genome,
                             force_archetype=arche)
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
                base = c.tank.name.split(" — ")[0]
                self.pending.append((now + C.BOT_RESPAWN_DELAY, base,
                                     c.skill, self._respawn_level(c.tank.level),
                                     None))
            else:
                c.update(dt)
        for item in list(self.pending):
            when, name, skill, lvl, member = item
            if now >= when:
                self.pending.remove(item)
                self._spawn(name, skill, lvl, member)
