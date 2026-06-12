"""Farmable polygon shapes (XP food) and crashers that chase tanks."""
from __future__ import annotations
import math
import random
from .base import Entity
from ..core.vector import Vec2
from .. import config as C

SHAPE_DEFS = {
    # hp, body damage, xp, radius, sides, color, score multiplier on kill
    "square":         dict(hp=10,   bd=8,  xp=10,   r=19, sides=4, color=C.COL_SQUARE),
    "triangle":       dict(hp=30,   bd=8,  xp=25,   r=17, sides=3, color=C.COL_TRIANGLE),
    "pentagon":       dict(hp=100,  bd=12, xp=130,  r=27, sides=5, color=C.COL_PENTAGON),
    "alpha_pentagon": dict(hp=3000, bd=20, xp=3000, r=92, sides=5, color=C.COL_ALPHA),
    "crasher_small":  dict(hp=10,   bd=8,  xp=15,   r=11, sides=3, color=C.COL_CRASHER),
    "crasher_large":  dict(hp=30,   bd=8,  xp=35,   r=17, sides=3, color=C.COL_CRASHER),
    "boss_guardian":  dict(hp=3200, bd=36, xp=8000, r=68, sides=12,
                           color=(214, 76, 168)),
}

SHAPE_TEAM = 0   # neutral team: hostile to everyone

SHINY_CHANCE = 1 / 90            # squares/triangles/pentagons only
SHINY_XP_MULT = 25
COL_SHINY = (95, 230, 120)


class Shape(Entity):
    kind = "shape"

    def __init__(self, world, pos: Vec2, shape_type: str):
        d = SHAPE_DEFS[shape_type]
        super().__init__(world, pos, d["r"], SHAPE_TEAM, d["hp"], d["bd"])
        self.shape_type = shape_type
        self.sides = d["sides"]
        self.color = d["color"]
        self.xp_value = d["xp"]
        self.shiny = (shape_type in ("square", "triangle", "pentagon")
                      and random.random() < SHINY_CHANCE)
        if self.shiny:
            self.color = COL_SHINY
            self.xp_value *= SHINY_XP_MULT
            self.max_health *= 2.0
            self.health = self.max_health
        self.rotation = random.uniform(0, math.tau)
        self.spin = random.uniform(-0.35, 0.35)
        self.drift_angle = random.uniform(0, math.tau)
        self.is_crasher = shape_type.startswith("crasher")
        self.friction = 1.2 if not self.is_crasher else 2.5
        self.push_factor = 1.0 if not self.is_crasher else 0.8
        self.regen_rate = 0.0005
        if shape_type == "alpha_pentagon":
            self.push_factor = 0.06
            self.spin *= 0.2

    def update(self, dt: float):
        if self.is_crasher:
            target = self.world.nearest_tank(self.pos, max_dist=520)
            if target is not None:
                d = (target.pos - self.pos).normalized()
                speed = 175 if self.shape_type == "crasher_small" else 130
                self.vel += d * (speed * 3.2 * dt)
                self.rotation = d.angle()
            else:
                self.rotation += self.spin * dt
        else:
            # lazy drift
            self.drift_angle += random.uniform(-0.6, 0.6) * dt
            self.vel += Vec2.from_angle(self.drift_angle, 4.5 * dt)
            self.rotation += self.spin * dt
        super().update(dt)


class Guardian(Shape):
    """Boss: a huge crasher-mother that hunts tanks and births crashers."""

    def __init__(self, world, pos: Vec2):
        super().__init__(world, pos, "boss_guardian")
        self.shiny = False
        self.spawn_cd = 2.0
        self.friction = 1.8
        self.push_factor = 0.04
        self.regen_rate = 0.002

    def update(self, dt: float):
        target = self.world.nearest_tank(self.pos, max_dist=1600)
        if target is not None:
            d = (target.pos - self.pos).normalized()
            self.vel += d * (130 * 2.4 * dt)
            self.rotation += 0.8 * dt
            self.spawn_cd -= dt
            if self.spawn_cd <= 0:
                self.spawn_cd = 2.5
                for _ in range(2):
                    ang = random.uniform(0, math.tau)
                    p = self.pos + Vec2.from_angle(ang, self.radius + 24)
                    self.world.add(Shape(self.world, p, "crasher_small"))
        else:
            self.rotation += self.spin * dt
        Entity.update(self, dt)
