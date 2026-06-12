"""Smooth-follow camera with zoom (used to emulate field-of-view differences)."""
from __future__ import annotations
from .vector import Vec2
from .. import config as C


class Camera:
    def __init__(self):
        self.pos = Vec2(C.ARENA_SIZE / 2, C.ARENA_SIZE / 2)
        self.zoom = 1.0
        self.target_zoom = 1.0

    def follow(self, target: Vec2, dt: float, stiffness: float = 6.0):
        k = min(1.0, stiffness * dt)
        self.pos += (target - self.pos) * k
        self.zoom += (self.target_zoom - self.zoom) * min(1.0, 3.0 * dt)

    def set_fov(self, fov: float, level_scale: float = 1.0):
        # bigger fov / level => more world visible => smaller zoom
        self.target_zoom = 1.0 / (fov * level_scale)

    def to_screen(self, world: Vec2) -> tuple[float, float]:
        return (
            (world.x - self.pos.x) * self.zoom + C.WINDOW_W / 2,
            (world.y - self.pos.y) * self.zoom + C.WINDOW_H / 2,
        )

    def to_world(self, sx: float, sy: float) -> Vec2:
        return Vec2(
            (sx - C.WINDOW_W / 2) / self.zoom + self.pos.x,
            (sy - C.WINDOW_H / 2) / self.zoom + self.pos.y,
        )

    def visible_rect(self):
        hw = C.WINDOW_W / 2 / self.zoom
        hh = C.WINDOW_H / 2 / self.zoom
        return (self.pos.x - hw, self.pos.y - hh, self.pos.x + hw, self.pos.y + hh)
