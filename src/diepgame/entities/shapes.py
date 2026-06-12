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
}

SHAPE_TEAM = 0   # neutral team: hostile to everyone


class Shape(Entity):
    kind = "shape"

    def __init__(self, world, pos: Vec2, shape_type: str):
        d = SHAPE_DEFS[shape_type]
        super().__init__(world, pos, d["r"], SHAPE_TEAM, d["hp"], d["bd"])
        self.shape_type = shape_type
        self.sides = d["sides"]
        self.color = d["color"]
        self.xp_value = d["xp"]
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
