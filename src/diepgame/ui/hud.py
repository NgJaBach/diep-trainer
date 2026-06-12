"""HUD overlay: stat upgrade panel, class upgrade choices, score & level
bars, leaderboard, minimap, kill feed and the death screen."""
from __future__ import annotations
import math
import pygame
from ..core.vector import Vec2
from ..tanks.definitions import TANK_DEFS
from .renderer import draw_tank_icon
from .. import config as C


def fmt_score(v: float) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}m"
    if v >= 1_000:
        return f"{v / 1_000:.1f}k"
    return str(int(v))


class Hud:
    def __init__(self, screen):
        self.screen = screen
        self.font_s = pygame.font.Font(None, 18)
        self.font_m = pygame.font.Font(None, 24)
        self.font_l = pygame.font.Font(None, 36)
        self.font_xl = pygame.font.Font(None, 60)
        self.stat_buttons: list[pygame.Rect] = []
        self.class_buttons: list[tuple[pygame.Rect, str]] = []

    # ------------------------------------------------------------- helpers ----
    def _text(self, font, msg, color=C.COL_TEXT, shadow=True):
        if shadow:
            base = font.render(msg, True, (40, 40, 40))
        img = font.render(msg, True, color)
        surf = pygame.Surface((img.get_width() + 2, img.get_height() + 2),
                              pygame.SRCALPHA)
        if shadow:
            surf.blit(base, (2, 2))
        surf.blit(img, (0, 0))
        return surf

    # --------------------------------------------------------------- draw ----
    def draw(self, world, player, paused=False, fps=None):
        self.stat_buttons.clear()
        self.class_buttons.clear()
        if player is not None and player.alive:
            self._draw_score_bars(player)
            self._draw_stat_panel(player)
            self._draw_class_choices(player)
            self._draw_toggles(player)
            self._draw_leader_arrow(world, player)
        feed_y = self._draw_leaderboard(world)
        self._draw_minimap(world, player)
        self._draw_killfeed(world, feed_y + 10)
        if fps:
            img = self._text(self.font_s, f"{fps:.0f} fps")
            self.screen.blit(img, (C.WINDOW_W - 174,
                                   C.WINDOW_H - 174 - 22))
        if paused:
            img = self._text(self.font_xl, "PAUSED")
            self.screen.blit(img, ((C.WINDOW_W - img.get_width()) / 2, 200))

    # ------------------------------------------------------------ sub-draws --
    def _draw_score_bars(self, p):
        cx = C.WINDOW_W / 2
        # level / xp bar
        w, h = 420, 22
        y = C.WINDOW_H - 38
        cur, nxt = C.xp_for_level(p.level), C.xp_for_level(p.level + 1)
        frac = 1.0 if p.level >= C.LEVEL_CAP else \
            max(0.0, min(1.0, (p.score - cur) / max(1.0, nxt - cur)))
        pygame.draw.rect(self.screen, (60, 60, 60, 180),
                         (cx - w / 2, y, w, h), border_radius=11)
        fw = (w - 4) * frac
        if fw > 3:      # radius capped so a sliver doesn't render as a blob
            pygame.draw.rect(self.screen, C.COL_XP_BAR,
                             (cx - w / 2 + 2, y + 2, fw, h - 4),
                             border_radius=min(9, int(fw / 2)))
        label = self._text(self.font_m,
                           f"Lvl {p.level}  {TANK_DEFS[p.def_key].name}")
        self.screen.blit(label, (cx - label.get_width() / 2, y + 1))
        # score bar
        w2, h2 = 300, 18
        y2 = y - 24
        pygame.draw.rect(self.screen, (60, 60, 60),
                         (cx - w2 / 2, y2, w2, h2), border_radius=9)
        score = self._text(self.font_s, f"Score: {fmt_score(p.score)}")
        self.screen.blit(score, (cx - score.get_width() / 2, y2 + 2))
        name = self._text(self.font_l, p.name)
        self.screen.blit(name, (cx - name.get_width() / 2, y2 - 34))

    def _draw_stat_panel(self, p):
        x, y0 = 14, C.WINDOW_H - 8 * 26 - 14
        for i, sname in enumerate(C.STAT_NAMES):
            y = y0 + i * 26
            w, h = 200, 22
            rect = pygame.Rect(x, y, w + 26, h)
            pygame.draw.rect(self.screen, (50, 50, 50),
                             (x, y, w, h), border_radius=11)
            # filled pips
            pip_w = (w - 8) / C.MAX_STAT
            for s in range(p.stats[i]):
                pygame.draw.rect(
                    self.screen, C.STAT_COLORS[i],
                    (x + 4 + s * pip_w, y + 3, pip_w - 2, h - 6),
                    border_radius=5)
            label = self._text(self.font_s, f"[{i+1}] {sname}")
            self.screen.blit(label, (x + 8, y + 4))
            # plus button
            if p.stat_points > 0 and p.stats[i] < C.MAX_STAT:
                br = pygame.Rect(x + w + 4, y, 22, h)
                pygame.draw.rect(self.screen, C.STAT_COLORS[i], br,
                                 border_radius=6)
                plus = self._text(self.font_m, "+", shadow=False)
                self.screen.blit(plus, (br.x + 6, br.y + 2))
                self.stat_buttons.append(rect.union(br))
            else:
                self.stat_buttons.append(rect)
        if p.stat_points > 0:
            img = self._text(self.font_m, f"x{p.stat_points} points  (keys 1-8)")
            self.screen.blit(img, (x, y0 - 26))

    def _draw_class_choices(self, p):
        opts = p.available_upgrades()
        if not opts:
            return
        x0, y0 = 14, 14
        size = 108
        gap = 10
        per_row = 2
        for i, key in enumerate(opts):
            col, row = i % per_row, i // per_row
            r = pygame.Rect(x0 + col * (size + gap), y0 + row * (size + gap),
                            size, size)
            tier_col = [(120, 200, 120), (120, 160, 230),
                        (230, 160, 120)][TANK_DEFS[key].tier - 2]
            pygame.draw.rect(self.screen, tier_col, r, border_radius=10)
            pygame.draw.rect(self.screen, tuple(int(c * 0.7) for c in tier_col),
                             r, 3, border_radius=10)
            draw_tank_icon(self.screen, r.centerx, r.centery - 8, 20,
                           TANK_DEFS[key], C.COL_PLAYER)
            name = TANK_DEFS[key].name
            img = self._text(self.font_s, name)
            self.screen.blit(img, (r.centerx - img.get_width() / 2,
                                   r.bottom - 24))
            hot = self._text(self.font_m, f"F{i+1}")
            self.screen.blit(hot, (r.x + 8, r.y + 6))
            self.class_buttons.append((r, key))
        tip = self._text(self.font_s, "Upgrade class: click or F1..F6")
        self.screen.blit(tip, (x0, y0 + ((len(opts) + 1) // per_row)
                               * (size + gap) + 2))

    def _draw_leader_arrow(self, world, player):
        """Red arrow at the screen edge pointing toward the arena leader."""
        top = world.leaderboard(1)
        if not top:
            return
        leader = top[0]
        if leader is player or not leader.alive:
            return
        d = leader.pos - player.pos
        if d.length() < 900:        # close enough to just see them
            return
        ang = d.angle()
        cx, cy = C.WINDOW_W / 2, C.WINDOW_H / 2
        edge = min(C.WINDOW_W, C.WINDOW_H) / 2 - 70
        bx = cx + math.cos(ang) * edge
        by = cy + math.sin(ang) * edge
        pts = [(bx + 16 * math.cos(ang), by + 16 * math.sin(ang)),
               (bx + 13 * math.cos(ang + 2.5), by + 13 * math.sin(ang + 2.5)),
               (bx + 13 * math.cos(ang - 2.5), by + 13 * math.sin(ang - 2.5))]
        pygame.draw.polygon(self.screen, (205, 60, 60), pts)
        img = self._text(self.font_s, "leader")
        self.screen.blit(img, (bx - img.get_width() / 2 - 22 * math.cos(ang),
                               by - img.get_height() / 2 - 22 * math.sin(ang)))

    def _draw_toggles(self, p):
        bits = []
        if p.auto_fire:
            bits.append("AUTO-FIRE [E]")
        if p.auto_spin:
            bits.append("AUTO-SPIN [C]")
        if bits:
            img = self._text(self.font_s, "   ".join(bits), color=(255, 230, 120))
            self.screen.blit(img, ((C.WINDOW_W - img.get_width()) / 2, 10))

    def _draw_leaderboard(self, world) -> int:
        """Draws the top-10 list; returns the bottom y so the kill feed
        can stack below instead of overlapping."""
        top = world.leaderboard(10)
        x = C.WINDOW_W - 230
        y = 14
        title = self._text(self.font_m, "Leaderboard")
        self.screen.blit(title, (x + 50, y))
        y += 28
        best = top[0].score if top else 1.0
        for t in top:
            w = 200
            frac = max(0.06, t.score / max(1.0, best))
            pygame.draw.rect(self.screen, (60, 60, 60),
                             (x, y, w, 16), border_radius=8)
            col = C.COL_PLAYER if t.is_player else C.COL_ENEMY
            fw = (w - 2) * frac
            pygame.draw.rect(self.screen, col,
                             (x + 1, y + 1, fw, 14),
                             border_radius=min(8, int(fw / 2)))
            img = self._text(self.font_s,
                             f"{t.name} — {fmt_score(t.score)}")
            self.screen.blit(img, (x + 6, y + 1))
            y += 20
        return y

    def _draw_minimap(self, world, player):
        size = 160
        x = C.WINDOW_W - size - 14
        y = C.WINDOW_H - size - 14
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        surf.fill((252, 252, 252, 228))
        pygame.draw.rect(surf, (90, 90, 90), (0, 0, size, size), 2)
        k = size / C.ARENA_SIZE
        # nest
        pygame.draw.circle(surf, (118, 141, 252, 90),
                           (size / 2, size / 2), C.NEST_RADIUS * k)
        boss = world.boss
        if boss is not None and boss.alive:
            pygame.draw.circle(surf, (170, 40, 130),
                               (boss.pos.x * k, boss.pos.y * k), 5)
        for t in world.tanks:
            if not t.alive:
                continue
            col = C.COL_PLAYER if t is player else C.COL_ENEMY
            pygame.draw.circle(surf, col, (t.pos.x * k, t.pos.y * k),
                               4 if t is player else 2.5)
        self.screen.blit(surf, (x, y))

    def _draw_killfeed(self, world, y: int = 130):
        for text, _ in world.kill_feed:
            img = self._text(self.font_s, text)
            self.screen.blit(img, (C.WINDOW_W - img.get_width() - 18, y))
            y += 20

    # -------------------------------------------------------- death screen ----
    def draw_death(self, stats: dict):
        overlay = pygame.Surface((C.WINDOW_W, C.WINDOW_H), pygame.SRCALPHA)
        overlay.fill((30, 30, 30, 160))
        self.screen.blit(overlay, (0, 0))
        cx = C.WINDOW_W / 2
        img = self._text(self.font_xl, "You were destroyed")
        self.screen.blit(img, (cx - img.get_width() / 2, 170))
        lines = [
            f"Killed by {stats.get('killed_by', 'the arena')}",
            f"Score: {fmt_score(stats['score'])}",
            f"Level: {stats['level']}  ({stats['class']})",
            f"Kills: {stats['kills']}",
            f"Time alive: {stats['time']:.0f}s",
        ]
        if stats.get("new_best"):
            lines.append("NEW PERSONAL BEST!")
        elif stats.get("best_score"):
            lines.append(f"Personal best: {fmt_score(stats['best_score'])}")
        y = 260
        for ln in lines:
            img = self._text(self.font_l, ln)
            self.screen.blit(img, (cx - img.get_width() / 2, y))
            y += 42
        img = self._text(self.font_m, "Press ENTER to respawn")
        self.screen.blit(img, (cx - img.get_width() / 2, y + 30))

    # -------------------------------------------------------- input routing --
    def handle_click(self, pos, player) -> bool:
        """Returns True if the click was consumed by the HUD."""
        if player is None or not player.alive:
            return False
        for i, r in enumerate(self.stat_buttons):
            if r.collidepoint(pos):
                player.upgrade_stat(i)
                return True
        for r, key in self.class_buttons:
            if r.collidepoint(pos):
                player.upgrade_class(key)
                return True
        return False
