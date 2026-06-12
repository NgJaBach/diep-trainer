"""Game: the pygame main loop. Wires together world, bots, camera, HUD.

Controls
--------
  WASD / arrows : move            Mouse        : aim
  LMB / Space   : fire            RMB / Shift  : repel drones
  1..8          : spend stat points
  F1..F6        : pick class upgrade (or click the buttons)
  E             : toggle auto-fire     C : toggle auto-spin
  P             : pause                Enter : respawn after death
  Esc           : quit
"""
from __future__ import annotations
import json
import random
from pathlib import Path
import pygame
from .core.camera import Camera
from .core.vector import Vec2
from .systems.world import World
from .ai.bot import BotManager
from .ui.renderer import Renderer
from .ui.hud import Hud
from . import config as C


STATS_PATH = Path.home() / ".polygon_arena_stats.json"
STATS_KEYS = ("best_score", "best_level", "best_kills", "longest_life", "games")


class Game:
    def __init__(self, player_name: str = "You"):
        pygame.init()
        pygame.display.set_caption(C.TITLE)
        self.screen = pygame.display.set_mode((C.WINDOW_W, C.WINDOW_H))
        self.clock = pygame.time.Clock()
        self.world = World()
        self.world.populate_initial()
        self.bots = BotManager(self.world)
        self.bots.spawn_initial()
        self.camera = Camera()
        self.renderer = Renderer(self.screen)
        self.hud = Hud(self.screen)
        self.player_name = player_name
        self.player = None
        self.spawn_time = 0.0
        self.death_stats = None
        self.death_level = 1
        self.paused = False
        self.running = True
        self._mouse_block = False     # HUD swallowed the current click
        self.stats = self._load_stats()
        self._spawn_player()

    # ------------------------------------------------------ personal bests --
    @staticmethod
    def _load_stats() -> dict:
        try:
            data = json.loads(STATS_PATH.read_text())
            return {k: data.get(k, 0) for k in STATS_KEYS}
        except (OSError, ValueError):
            return {k: 0 for k in STATS_KEYS}

    def _record_run(self, stats: dict) -> bool:
        """Update personal bests; returns True if the score is a new best."""
        s = self.stats
        new_best = stats["score"] > s["best_score"]
        s["best_score"] = max(s["best_score"], int(stats["score"]))
        s["best_level"] = max(s["best_level"], stats["level"])
        s["best_kills"] = max(s["best_kills"], stats["kills"])
        s["longest_life"] = max(s["longest_life"], int(stats["time"]))
        s["games"] += 1
        try:
            STATS_PATH.write_text(json.dumps(s))
        except OSError:
            pass
        return new_best

    # ------------------------------------------------------------------
    def _spawn_player(self):
        # like the bots, keep part of your progress when you respawn
        level = max(1, min(C.BOT_RESPAWN_LEVEL_CAP, self.death_level * 2 // 3))
        if C.PLAYER_START_LEVEL is not None:
            level = max(level, C.PLAYER_START_LEVEL)
        self.player = self.world.spawn_tank(self.player_name, is_player=True,
                                            color=C.COL_PLAYER, level=level)
        if C.PLAYER_START_CLASS:        # practice mode: jump to a class
            self.player.def_key = C.PLAYER_START_CLASS
            self.player._rebuild_barrels()
            self.player._refresh_derived()
        self.world.player = self.player
        self.spawn_time = self.world.time
        self.death_stats = None
        self.camera.pos = self.player.pos.copy()

    # ------------------------------------------------------------- input ----
    def _handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.KEYDOWN:
                self._key_down(ev.key)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                # a click the HUD consumes must not also fire the gun
                self._mouse_block = self.hud.handle_click(ev.pos, self.player)
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                self._mouse_block = False

    def _key_down(self, key):
        p = self.player
        if key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_p:
            self.paused = not self.paused
        elif key == pygame.K_RETURN and (p is None or not p.alive):
            self._spawn_player()
        if p is None or not p.alive:
            return
        if key == pygame.K_e:
            p.auto_fire = not p.auto_fire
        elif key == pygame.K_c:
            p.auto_spin = not p.auto_spin
        elif pygame.K_1 <= key <= pygame.K_8:
            p.upgrade_stat(key - pygame.K_1)
        elif pygame.K_F1 <= key <= pygame.K_F6:
            opts = p.available_upgrades()
            idx = key - pygame.K_F1
            if idx < len(opts):
                p.upgrade_class(opts[idx])

    def _poll_player_input(self):
        p = self.player
        if p is None or not p.alive:
            return
        keys = pygame.key.get_pressed()
        mv = Vec2()
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            mv.y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            mv.y += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            mv.x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            mv.x += 1
        p.move_input = mv
        mouse = pygame.mouse.get_pressed(3)
        p.shooting = (mouse[0] and not self._mouse_block) or keys[pygame.K_SPACE]
        p.repelling = mouse[2] or keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        mx, my = pygame.mouse.get_pos()
        target = self.camera.to_world(mx, my)
        p.aim_target = target           # drones fly to the cursor
        if not p.auto_spin:
            p.aim_angle = (target - p.pos).angle()

    # -------------------------------------------------------------- frame ----
    def _update(self, dt):
        if self.paused:
            return
        self._poll_player_input()
        self.bots.update(dt)
        self.world.step(dt)
        p = self.player
        if p is not None:
            if p.alive:
                level_scale = 1.0 + 0.006 * (p.level - 1)
                self.camera.set_fov(p.tdef.fov, level_scale)
                self.camera.follow(p.pos, dt)
            elif self.death_stats is None:
                self.death_level = p.level
                killer = p.last_attacker
                if killer is None:
                    killed_by = "the arena"
                elif getattr(killer, "name", None):
                    killed_by = killer.name
                else:
                    killed_by = getattr(killer, "shape_type",
                                        "something") .replace("_", " ")
                self.death_stats = dict(
                    score=p.score, level=p.level, kills=p.kills,
                    time=self.world.time - self.spawn_time,
                    killed_by=killed_by,
                    **{"class": p.tdef.name})
                self.death_stats["new_best"] = self._record_run(self.death_stats)
                self.death_stats["best_score"] = self.stats["best_score"]

    def _draw(self):
        self.renderer.draw_background(self.camera)
        self.renderer.draw_world(self.world, self.camera, self.player)
        self.hud.draw(self.world, self.player, paused=self.paused,
                      fps=self.clock.get_fps())
        if self.player is not None and not self.player.alive \
                and self.death_stats is not None:
            self.hud.draw_death(self.death_stats)
        pygame.display.flip()

    # --------------------------------------------------------------- loop ----
    def run(self):
        while self.running:
            dt = min(0.05, self.clock.tick(C.FPS) / 1000.0)
            self._handle_events()
            self._update(dt)
            self._draw()
        pygame.quit()

    # headless stepping used by the smoke test
    def step_headless(self, dt: float):
        self.bots.update(dt)
        self.world.step(dt)
