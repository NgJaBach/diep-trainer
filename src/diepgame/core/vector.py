"""Tiny 2D vector used everywhere in the simulation."""
from __future__ import annotations
import math


class Vec2:
    __slots__ = ("x", "y")

    def __init__(self, x: float = 0.0, y: float = 0.0):
        self.x = float(x)
        self.y = float(y)

    def __add__(self, o): return Vec2(self.x + o.x, self.y + o.y)
    def __sub__(self, o): return Vec2(self.x - o.x, self.y - o.y)
    def __mul__(self, k: float): return Vec2(self.x * k, self.y * k)
    __rmul__ = __mul__
    def __truediv__(self, k: float): return Vec2(self.x / k, self.y / k)
    def __neg__(self): return Vec2(-self.x, -self.y)
    def __iadd__(self, o):
        self.x += o.x; self.y += o.y; return self
    def __isub__(self, o):
        self.x -= o.x; self.y -= o.y; return self

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def length_sq(self) -> float:
        return self.x * self.x + self.y * self.y

    def normalized(self) -> "Vec2":
        l = self.length()
        if l < 1e-9:
            return Vec2(0.0, 0.0)
        return Vec2(self.x / l, self.y / l)

    def angle(self) -> float:
        return math.atan2(self.y, self.x)

    def copy(self) -> "Vec2":
        return Vec2(self.x, self.y)

    def dist_to(self, o: "Vec2") -> float:
        return math.hypot(self.x - o.x, self.y - o.y)

    def dist_sq_to(self, o: "Vec2") -> float:
        dx, dy = self.x - o.x, self.y - o.y
        return dx * dx + dy * dy

    @staticmethod
    def from_angle(a: float, length: float = 1.0) -> "Vec2":
        return Vec2(math.cos(a) * length, math.sin(a) * length)

    def __repr__(self):
        return f"Vec2({self.x:.1f}, {self.y:.1f})"
