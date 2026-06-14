"""World: owns every entity, runs simulation steps, spawns shapes and bots."""
from __future__ import annotations
import math
import random
from ..core.vector import Vec2
from ..entities.base import Entity
from ..entities.shapes import Shape, Guardian, SHAPE_DEFS
from ..entities.projectiles import Drone
from ..entities.tank import Tank
from .spatial import SpatialHash
from . import collision
from .. import config as C


class World:
    def __init__(self):
        self.time = 0.0
        self.entities: list[Entity] = []
        self.tanks: list[Tank] = []
        self.grid = SpatialHash(140.0)
        self.player: Tank | None = None
        self.mode = C.GAME_MODE                        # "ffa" or "team"
        self.kill_feed: list[tuple[str, float]] = []   # (text, expiry)
        self.effects: list[dict] = []                  # death bursts
        self._team_counter = C.TEAM_FFA_START
        self._shape_counts = {k: 0 for k in SHAPE_DEFS}
        self.bot_controllers = []   # filled by Game
        self.center = Vec2(C.ARENA_SIZE / 2, C.ARENA_SIZE / 2)
        self.boss: Guardian | None = None
        self.next_boss_at = C.BOSS_FIRST_AT

    # ---------------------------------------------------------- plumbing ----
    def add(self, e: Entity):
        self.entities.append(e)
        if isinstance(e, Tank):
            self.tanks.append(e)
        elif isinstance(e, Shape):
            self._shape_counts[e.shape_type] += 1

    def new_team(self) -> int:
        self._team_counter += 1
        return self._team_counter

    def human_team(self) -> int:
        """Team for a human player: shared blue in team mode, unique in FFA."""
        return C.TEAM_BLUE if self.mode == "team" else self.new_team()

    def bot_team(self) -> int:
        """Team for a bot: shared red in team mode, unique in FFA."""
        return C.TEAM_RED if self.mode == "team" else self.new_team()

    def on_entity_died(self, e: Entity):
        # death burst (drawn by the renderer, aged in step)
        if len(self.effects) < 80:
            big = e.kind in ("tank", "shape")
            self.effects.append(dict(
                pos=e.pos.copy(), radius=e.radius,
                color=getattr(e, "color", (160, 160, 160)),
                sides=getattr(e, "sides", 0),
                rotation=getattr(e, "rotation", 0.0),
                age=0.0, dur=0.4 if big else 0.22))
        # award XP to the killer
        attacker = e.last_attacker
        if isinstance(e, Shape):
            self._shape_counts[e.shape_type] -= 1
            if e.shape_type == "boss_guardian":
                self.boss = None
                self.next_boss_at = self.time + C.BOSS_INTERVAL
                name = attacker.name if isinstance(attacker, Tank) else "the arena"
                self.kill_feed.append(
                    (f"{name} slew The Guardian! (+{int(e.xp_value)} XP)",
                     self.time + 8.0))
            if isinstance(attacker, Tank) and attacker.alive:
                # necromancers raise killed squares as drones instead of XP
                if (e.shape_type == "square" and attacker.tdef.necro
                        and len(attacker.drones) < attacker.tdef.max_drones):
                    d = Drone(self, attacker, e.pos.copy(), Vec2(),
                              e.radius * 0.78,
                              attacker.bullet_damage() * 0.6,
                              attacker.bullet_hp())
                    d.sides = 4
                    attacker.drones.append(d)
                    self.add(d)
                else:
                    attacker.add_score(e.xp_value)
        elif isinstance(e, Tank):
            if isinstance(attacker, Tank) and attacker.alive and attacker is not e:
                gained = max(20.0, e.score * C.KILL_XP_FRACTION)
                attacker.add_score(gained)
                attacker.kills += 1
                self.kill_feed.append(
                    (f"{attacker.name} destroyed {e.name}", self.time + 5.0))
            else:
                self.kill_feed.append((f"{e.name} died", self.time + 5.0))

    # ------------------------------------------------------------ queries ----
    def nearest_tank(self, pos: Vec2, max_dist: float = 1e9,
                     exclude_team: int | None = None) -> Tank | None:
        best, best_d = None, max_dist * max_dist
        for t in self.tanks:
            if not t.alive:
                continue
            if exclude_team is not None and t.team == exclude_team:
                continue
            d = t.pos.dist_sq_to(pos)
            if d < best_d:
                best, best_d = t, d
        return best

    def shapes_near(self, pos: Vec2, radius: float):
        return [e for e in self.grid.query_circle(pos, radius)
                if isinstance(e, Shape) and e.alive]

    def tanks_near(self, pos: Vec2, radius: float, exclude_team=None):
        out = []
        r2 = radius * radius
        for t in self.tanks:
            if not t.alive or (exclude_team is not None and t.team == exclude_team):
                continue
            if t.pos.dist_sq_to(pos) <= r2:
                out.append(t)
        return out

    # ----------------------------------------------------------- spawning ----
    def random_spawn_pos(self, margin: float = 250.0) -> Vec2:
        for _ in range(40):
            p = Vec2(random.uniform(margin, C.ARENA_SIZE - margin),
                     random.uniform(margin, C.ARENA_SIZE - margin))
            if p.dist_to(self.center) < C.NEST_RADIUS + 300:
                continue            # never spawn into the crasher nest
            if self.nearest_tank(p, max_dist=600) is None:
                return p
        return p

    def _spawn_shape(self, shape_type: str):
        if shape_type in ("pentagon", "alpha_pentagon", "crasher_small",
                          "crasher_large"):
            # bias pentagons & crashers toward the central nest
            if shape_type.startswith("crasher") or shape_type == "alpha_pentagon" \
                    or random.random() < 0.55:
                ang = random.uniform(0, math.tau)
                r = random.uniform(0, C.NEST_RADIUS * 0.92)
                pos = self.center + Vec2.from_angle(ang, r)
            else:
                pos = Vec2(random.uniform(80, C.ARENA_SIZE - 80),
                           random.uniform(80, C.ARENA_SIZE - 80))
        else:
            pos = Vec2(random.uniform(60, C.ARENA_SIZE - 60),
                       random.uniform(60, C.ARENA_SIZE - 60))
        self.add(Shape(self, pos, shape_type))

    def maintain_shapes(self, budget: int = 6):
        spawned = 0
        for st, target in C.SHAPE_TARGETS.items():
            while self._shape_counts[st] < target and spawned < budget:
                self._spawn_shape(st)
                spawned += 1

    def populate_initial(self):
        for st, target in C.SHAPE_TARGETS.items():
            for _ in range(target):
                self._spawn_shape(st)

    def spawn_tank(self, name: str, is_player=False, def_key="basic",
                   level: int = 1, color=None, team: int | None = None) -> Tank:
        if team is None:
            team = self.human_team() if is_player else self.new_team()
        t = Tank(self, self.random_spawn_pos(), name, team,
                 def_key=def_key, is_player=is_player, color=color)
        if level > 1:
            t.add_score(C.xp_for_level(level))
        self.add(t)
        return t

    def _spawn_boss(self):
        ang = random.uniform(0, math.tau)
        pos = self.center + Vec2.from_angle(ang, C.ARENA_SIZE * 0.38)
        self.boss = Guardian(self, pos)
        self.add(self.boss)
        self.kill_feed.append(("The Guardian has awakened!", self.time + 8.0))

    # --------------------------------------------------------------- step ----
    def step(self, dt: float):
        self.time += dt
        if self.boss is None and self.time >= self.next_boss_at:
            self._spawn_boss()
        for e in self.entities:
            if e.alive:
                e.update(dt)
        self.grid.rebuild(self.entities)
        for a, b in self.grid.candidate_pairs():
            collision.resolve(a, b, dt)
        # cull
        self.entities = [e for e in self.entities if e.alive]
        self.tanks = [t for t in self.tanks if t.alive]
        self.maintain_shapes()
        self.kill_feed = [(t, exp) for t, exp in self.kill_feed
                          if exp > self.time][-6:]
        for fx in self.effects:
            fx["age"] += dt
        self.effects = [fx for fx in self.effects if fx["age"] < fx["dur"]]

    def leaderboard(self, n: int = 10):
        return sorted(self.tanks, key=lambda t: t.score, reverse=True)[:n]
