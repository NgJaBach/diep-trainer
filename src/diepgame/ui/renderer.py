"""Rendering of the world: background grid, shapes, tanks, projectiles.

Everything is drawn procedurally with pygame primitives — no image assets.
"""
from __future__ import annotations
import math
import pygame
from ..core.vector import Vec2
from ..entities.tank import Tank
from ..entities.shapes import Shape
from ..entities.projectiles import Bullet, Trap, Drone
from .. import config as C


def darken(color, k=C.OUTLINE_DARKEN):
    return tuple(int(c * k) for c in color)


def flash(color, amount):
    """Blend toward white for damage flash."""
    a = max(0.0, min(1.0, amount))
    return tuple(int(c + (255 - c) * a) for c in color)


def regular_polygon(cx, cy, r, sides, rot):
    return [(cx + r * math.cos(rot + i * math.tau / sides),
             cy + r * math.sin(rot + i * math.tau / sides))
            for i in range(sides)]


class Renderer:
    def __init__(self, screen):
        self.screen = screen

    # ---------------------------------------------------------- background ----
    def draw_background(self, cam):
        s = self.screen
        s.fill(C.COL_OUTSIDE)
        x0, y0, x1, y1 = cam.visible_rect()
        # arena interior
        ax0, ay0 = cam.to_screen(Vec2(0, 0))
        ax1, ay1 = cam.to_screen(Vec2(C.ARENA_SIZE, C.ARENA_SIZE))
        pygame.draw.rect(s, C.COL_BG, (ax0, ay0, ax1 - ax0, ay1 - ay0))
        # grid
        step = C.GRID_STEP
        if cam.zoom * step >= 6:
            gx = math.floor(max(x0, 0) / step) * step
            while gx <= min(x1, C.ARENA_SIZE):
                sx, _ = cam.to_screen(Vec2(gx, 0))
                pygame.draw.line(s, C.COL_GRID,
                                 (sx, max(ay0, 0)), (sx, min(ay1, C.WINDOW_H)))
                gx += step
            gy = math.floor(max(y0, 0) / step) * step
            while gy <= min(y1, C.ARENA_SIZE):
                _, sy = cam.to_screen(Vec2(0, gy))
                pygame.draw.line(s, C.COL_GRID,
                                 (max(ax0, 0), sy), (min(ax1, C.WINDOW_W), sy))
                gy += step

    # --------------------------------------------------------------- world ----
    def draw_world(self, world, cam, player):
        x0, y0, x1, y1 = cam.visible_rect()
        pad = 140

        def on_screen(e):
            return (x0 - pad < e.pos.x < x1 + pad
                    and y0 - pad < e.pos.y < y1 + pad)

        layers = {"trap": [], "bullet": [], "drone": [], "shape": [],
                  "tank": []}
        for e in world.entities:
            if e.alive and on_screen(e):
                layers.get(e.kind, layers["shape"]).append(e)

        for trap in layers["trap"]:
            self._draw_trap(trap, cam)
        for b in layers["bullet"]:
            self._draw_bullet(b, cam)
        for sh in layers["shape"]:
            self._draw_shape(sh, cam)
        for d in layers["drone"]:
            self._draw_drone(d, cam)
        for t in layers["tank"]:
            self._draw_tank(t, cam, is_self=(t is player))

        # health bars + nameplates last, on top
        for sh in layers["shape"]:
            self._draw_health(sh, cam)
        for t in layers["tank"]:
            self._draw_health(t, cam)
            self._draw_nameplate(t, cam, player)

    # ------------------------------------------------------------- pieces ----
    def _tank_color(self, t: Tank, viewer):
        if viewer is None or t is viewer:
            return t.color
        return C.COL_ENEMY if t.team != viewer.team else C.COL_PLAYER

    def _draw_tank(self, t: Tank, cam, is_self=False):
        alpha = t.invisible_alpha if not is_self else max(0.25, t.invisible_alpha)
        if alpha <= 0.02 and not is_self:
            return
        sx, sy = cam.to_screen(t.pos)
        r = t.radius * cam.zoom
        body = flash(t.color if is_self else C.COL_ENEMY, t.damage_flash * 6)
        if is_self:
            body = flash(t.color, t.damage_flash * 6)
        barrel_col = flash(C.COL_BARREL, t.damage_flash * 6)

        surf = self.screen
        use_alpha = alpha < 0.98
        if use_alpha:
            size = int(r * 7)
            tmp = pygame.Surface((size, size), pygame.SRCALPHA)
            ox, oy = size / 2 - sx, size / 2 - sy
        else:
            tmp, ox, oy = surf, 0.0, 0.0

        cx, cy = sx + ox, sy + oy

        # smasher / spike under-body
        if t.tdef.body_shape == "smasher":
            pts = regular_polygon(cx, cy, r * 1.32, 6, t.aim_angle * 0.4)
            pygame.draw.polygon(tmp, C.COL_SMASHER, pts)
            pygame.draw.polygon(tmp, darken(C.COL_SMASHER), pts,
                                max(1, int(3 * cam.zoom)))
        elif t.tdef.body_shape == "spike":
            pts = regular_polygon(cx, cy, r * 1.45, 12, t.aim_angle * 0.6)
            star = []
            for i, p in enumerate(pts):
                if i % 2 == 0:
                    star.append(p)
                else:
                    star.append((cx + (p[0] - cx) * 0.62,
                                 cy + (p[1] - cy) * 0.62))
            pygame.draw.polygon(tmp, C.COL_SMASHER, star)

        # barrels
        for spec in t.tdef.barrels:
            self._draw_barrel(tmp, cx, cy, r, t.aim_angle, spec, barrel_col,
                              cam.zoom)

        # body
        pygame.draw.circle(tmp, body, (cx, cy), r)
        pygame.draw.circle(tmp, darken(body), (cx, cy), r,
                           max(1, int(3 * cam.zoom)))

        if use_alpha:
            tmp.set_alpha(int(255 * alpha))
            surf.blit(tmp, (sx - size / 2, sy - size / 2))

    def _draw_barrel(self, surf, cx, cy, r, aim, spec, color, zoom):
        ang = aim + math.radians(spec.angle)
        d = Vec2.from_angle(ang)
        p = Vec2.from_angle(ang + math.pi / 2)
        L = r * spec.length
        w0 = r * spec.width
        w1 = w0 * (1.45 if spec.trapezoid else 1.0)
        base = Vec2(cx, cy) + p * (r * spec.lat)
        tip = base + d * L
        pts = [
            (base.x + p.x * w0 / 2, base.y + p.y * w0 / 2),
            (tip.x + p.x * w1 / 2, tip.y + p.y * w1 / 2),
            (tip.x - p.x * w1 / 2, tip.y - p.y * w1 / 2),
            (base.x - p.x * w0 / 2, base.y - p.y * w0 / 2),
        ]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, darken(color), pts, max(1, int(2 * zoom)))

    def _draw_shape(self, sh: Shape, cam):
        sx, sy = cam.to_screen(sh.pos)
        r = sh.radius * cam.zoom * (1.18 if sh.sides <= 4 else 1.05)
        col = flash(sh.color, sh.damage_flash * 6)
        pts = regular_polygon(sx, sy, r, sh.sides, sh.rotation)
        pygame.draw.polygon(self.screen, col, pts)
        pygame.draw.polygon(self.screen, darken(col), pts,
                            max(1, int(3 * cam.zoom)))

    def _draw_bullet(self, b: Bullet, cam):
        sx, sy = cam.to_screen(b.pos)
        r = max(1.0, b.radius * cam.zoom)
        col = flash(b.color, b.damage_flash * 6)
        pygame.draw.circle(self.screen, col, (sx, sy), r)
        pygame.draw.circle(self.screen, darken(col), (sx, sy), r,
                           max(1, int(2 * cam.zoom)))

    def _draw_drone(self, d: Drone, cam):
        sx, sy = cam.to_screen(d.pos)
        r = max(2.0, d.radius * cam.zoom * 1.25)
        col = flash(d.color, d.damage_flash * 6)
        rot = d.vel.angle() if d.vel.length_sq() > 4 else 0.0
        pts = regular_polygon(sx, sy, r, 3, rot)
        pygame.draw.polygon(self.screen, col, pts)
        pygame.draw.polygon(self.screen, darken(col), pts,
                            max(1, int(2 * cam.zoom)))

    def _draw_trap(self, t: Trap, cam):
        sx, sy = cam.to_screen(t.pos)
        r = max(2.0, t.radius * cam.zoom * 1.3)
        col = flash(t.color, t.damage_flash * 6)
        outer = regular_polygon(sx, sy, r, 3, t.rotation)
        inner = regular_polygon(sx, sy, r * 0.55, 3,
                                t.rotation + math.pi / 3)
        star = []
        for o, i in zip(outer, inner):
            star += [o, i]
        pygame.draw.polygon(self.screen, col, star)
        pygame.draw.polygon(self.screen, darken(col), star,
                            max(1, int(2 * cam.zoom)))

    def _draw_health(self, e, cam):
        if e.health >= e.max_health - 0.5:
            return
        if isinstance(e, Tank) and e.invisible_alpha < 0.2:
            return
        sx, sy = cam.to_screen(e.pos)
        w = e.radius * 2.2 * cam.zoom
        h = max(3.0, 5 * cam.zoom)
        y = sy + (e.radius + 10) * cam.zoom
        frac = max(0.0, e.health / e.max_health)
        pygame.draw.rect(self.screen, C.COL_HP_BACK,
                         (sx - w / 2, y, w, h), border_radius=int(h / 2))
        pygame.draw.rect(self.screen, C.COL_HP_FRONT,
                         (sx - w / 2 + 1, y + 1, (w - 2) * frac, h - 2),
                         border_radius=int(h / 2))

    def _draw_nameplate(self, t: Tank, cam, viewer):
        if t is viewer or t.invisible_alpha < 0.2:
            return
        sx, sy = cam.to_screen(t.pos)
        font = pygame.font.Font(None, max(14, int(20 * cam.zoom)))
        img = font.render(f"{t.name}", True, (60, 60, 60))
        self.screen.blit(img, (sx - img.get_width() / 2,
                               sy - (t.radius + 30) * cam.zoom))
