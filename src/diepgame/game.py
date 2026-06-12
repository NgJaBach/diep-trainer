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
import random
import pygame
from .core.camera import Camera
from .core.vector import Vec2
from .systems.world import World
from .ai.bot import BotManager
from .ui.renderer import Renderer
from .ui.hud import Hud
from . import config as C


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
        self.paused = False
        self.running = True
        self._spawn_player()

    # ------------------------------------------------------------------
    def _spawn_player(self):
        self.player = self.world.spawn_tank(self.player_name, is_player=True,
                                            color=C.COL_PLAYER)
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
                if not self.hud.handle_click(ev.pos, self.player):
                    pass  # click-to-fire is handled by polling below

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
        p.shooting = mouse[0] or keys[pygame.K_SPACE]
        p.repelling = mouse[2] or keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        mx, my = pygame.mouse.get_pos()
        target = self.camera.to_world(mx, my)
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
                self.death_stats = dict(
                    score=p.score, level=p.level, kills=p.kills,
                    time=self.world.time - self.spawn_time,
                    **{"class": p.tdef.name})

    def _draw(self):
        self.renderer.draw_background(self.camera)
        self.renderer.draw_world(self.world, self.camera, self.player)
        self.hud.draw(self.world, self.player, paused=self.paused)
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
