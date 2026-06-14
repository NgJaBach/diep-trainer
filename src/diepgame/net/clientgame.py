"""Client-side game: render interpolated host snapshots, send local input.

Builds lightweight view objects that quack like the real Entity/Tank/World so
the existing Renderer and Hud can draw them unchanged.
"""
from __future__ import annotations
import pygame

from .client import NetClient
from .protocol import unpack_rgb
from ..core.vector import Vec2
from ..core.camera import Camera
from ..ui.renderer import Renderer
from ..ui.hud import Hud
from ..tanks.definitions import TANK_DEFS, available_upgrades
from .. import config as C


# ----------------------------------------------------------- view objects ----
class SnapEntity:
    __slots__ = ("kind", "pos", "radius", "color", "id", "world", "alive",
                 "damage_flash", "sides", "rotation", "vel", "shiny",
                 "health", "max_health")

    def __init__(self, kind, rec, world):
        self.kind = kind
        self.id = rec["i"]
        self.pos = Vec2(rec["x"], rec["y"])
        self.radius = rec["r"]
        self.color = unpack_rgb(rec["c"])
        self.world = world
        self.alive = True
        self.damage_flash = 0.0
        self.sides = rec.get("s", 3)
        self.rotation = rec.get("o", 0.0)
        self.shiny = bool(rec.get("sh", 0))
        # health bar for damaged shapes (1.0 = full -> renderer skips it)
        self.max_health = 1.0
        self.health = rec.get("hf", 1.0)
        # drones are drawn from velocity angle; synthesize one
        self.vel = Vec2.from_angle(rec.get("o", 0.0), 10.0)


class SnapTank:
    """Quacks like Tank for the renderer/HUD; mutations route to the network."""
    kind = "tank"

    def __init__(self, rec, world, client, is_player):
        self.id = rec["i"]
        self.pos = Vec2(rec["x"], rec["y"])
        self.radius = rec["r"]
        self.def_key = rec["d"]
        self.tdef = TANK_DEFS[rec["d"]]
        self.aim_angle = rec["a"]
        self.name = rec["n"]
        self.team = rec["tm"]
        self.health = rec["hp"]
        self.max_health = rec["mhp"]
        self.invisible_alpha = rec["ia"]
        self.damage_flash = rec.get("fl", 0.0)
        self.score = rec["sc"]
        self.level = rec["lv"]
        self.world = world
        self.alive = True
        self.is_player = is_player
        self.color = C.COL_PLAYER if is_player else C.COL_ENEMY
        self.shield_until = (world.time + 1.0) if rec.get("sld") else -1e9
        self._client = client
        self.auto_fire = False
        self.auto_spin = False
        # filled from the "you" block for the local player
        self.stats = [0] * 8
        self.stat_points = 0

    def available_upgrades(self):
        return available_upgrades(self.def_key, self.level)

    def upgrade_stat(self, idx):
        self._client.upgrade_stat(idx)

    def upgrade_class(self, key):
        self._client.upgrade_class(key)


class _Boss:
    def __init__(self, x, y):
        self.pos = Vec2(x, y)
        self.alive = True


class ClientWorld:
    def __init__(self):
        self.entities = []
        self.tanks = []
        self.effects = []
        self.kill_feed = []
        self.boss = None
        self.time = 0.0
        self.mode = "ffa"
        self.center = Vec2(C.ARENA_SIZE / 2, C.ARENA_SIZE / 2)

    def leaderboard(self, n=10):
        return sorted(self.tanks, key=lambda t: t.score, reverse=True)[:n]


# ---------------------------------------------------------------- the game ----
class ClientGame:
    def __init__(self, host, port, name, password="", window=None):
        if window:
            C.WINDOW_W, C.WINDOW_H = window
        self.client = NetClient(host, port, name, password)
        if not self.client.connect():
            raise ConnectionError(self.client.error or "could not connect")
        # adopt the host's arena/mode so renderer + minimap match
        C.ARENA_SIZE = self.client.arena
        C.GAME_MODE = self.client.mode
        pygame.init()
        pygame.display.set_caption(f"{C.TITLE}  —  {self.client.mode.upper()} @ {host}")
        self.screen = pygame.display.set_mode((C.WINDOW_W, C.WINDOW_H))
        self.clock = pygame.time.Clock()
        self.camera = Camera()
        self.renderer = Renderer(self.screen)
        self.hud = Hud(self.screen)
        self.running = True
        self.auto_fire = False
        self.auto_spin = False
        self._mouse_block = False
        self.player = None          # current local SnapTank (or None if dead)
        self.you = None             # latest "you" block

    # -------------------------------------------------------------- build ----
    def _build_world(self):
        snap = self.client.interpolated()
        if snap is None:
            return None
        w = ClientWorld()
        w.time = snap["ts"]
        w.mode = snap.get("md", "ffa")
        self.you = snap.get("you")
        you_id = self.you["id"] if self.you else -1

        for rec in snap["e"]:
            kind = {"s": "shape", "b": "bullet", "d": "drone",
                    "p": "trap"}[rec["k"]]
            w.entities.append(SnapEntity(kind, rec, w))

        player = None
        for rec in snap["tk"]:
            is_self = rec["i"] == you_id
            t = SnapTank(rec, w, self.client, is_self)
            w.tanks.append(t)
            w.entities.append(t)
            if is_self:
                player = t
        if player is not None and self.you is not None:
            player.stats = self.you.get("st", player.stats)
            player.stat_points = self.you.get("sp", 0)
            player.auto_fire = self.auto_fire
            player.auto_spin = self.auto_spin

        for f in snap["fx"]:
            w.effects.append(dict(pos=Vec2(f["x"], f["y"]), radius=f["r"],
                                  color=unpack_rgb(f["c"]), sides=f["s"],
                                  rotation=f["o"], age=f["a"], dur=f["du"]))
        if snap.get("boss"):
            w.boss = _Boss(snap["boss"][0], snap["boss"][1])
        w.kill_feed = [(text, 0.0) for text in snap.get("kf", [])]
        self.player = player
        return w

    # -------------------------------------------------------------- input ----
    def _handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.KEYDOWN:
                self._key_down(ev.key)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                self._mouse_block = self.hud.handle_click(ev.pos, self.player)
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                self._mouse_block = False

    def _key_down(self, key):
        if key == pygame.K_ESCAPE:
            self.running = False
        elif key == pygame.K_RETURN and (self.you and not self.you["al"]):
            self.client.respawn()
        elif key == pygame.K_e:
            self.auto_fire = not self.auto_fire
        elif key == pygame.K_c:
            self.auto_spin = not self.auto_spin
        elif pygame.K_1 <= key <= pygame.K_8:
            self.client.upgrade_stat(key - pygame.K_1)
        elif pygame.K_F1 <= key <= pygame.K_F6 and self.player is not None:
            opts = self.player.available_upgrades()
            idx = key - pygame.K_F1
            if idx < len(opts):
                self.client.upgrade_class(opts[idx])

    def _send_input(self):
        alive = bool(self.you and self.you["al"]) and self.player is not None
        if not alive:
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
        mouse = pygame.mouse.get_pressed(3)
        mx, my = pygame.mouse.get_pos()
        aim_world = self.camera.to_world(mx, my)
        shooting = (mouse[0] and not self._mouse_block) or keys[pygame.K_SPACE]
        repel = mouse[2] or keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        self.client.send_input(mv, aim_world, shooting, repel,
                               self.auto_fire, self.auto_spin)

    # -------------------------------------------------------------- frame ----
    def _draw(self, world):
        if world is None:
            self.screen.fill(C.COL_BG)
            msg = self.hud._text(self.hud.font_l, "Connecting to host...")
            self.screen.blit(msg, ((C.WINDOW_W - msg.get_width()) / 2, 300))
            pygame.display.flip()
            return
        p = self.player
        if p is not None:
            level_scale = 1.0 + 0.006 * (p.level - 1)
            self.camera.set_fov(p.tdef.fov, level_scale)
            self.camera.follow(p.pos, 1 / 60)
        self.renderer.draw_background(self.camera)
        self.renderer.draw_world(world, self.camera, p)
        self.hud.draw(world, p if (self.you and self.you["al"]) else None,
                      fps=self.clock.get_fps())
        if self.you is not None and not self.you["al"]:
            self.hud.draw_death(dict(
                score=self.you.get("sc", 0), level=self.you.get("lv", 1),
                kills=self.you.get("k", 0), time=self.you.get("ta", 0),
                killed_by=self.you.get("by", "the arena"),
                **{"class": self.you.get("cl", "")}))
        pygame.display.flip()

    def run(self):
        while self.running:
            self.clock.tick(C.FPS)
            self._handle_events()
            world = self._build_world()
            self._send_input()
            self._draw(world)
            if not self.client.connected:
                self._draw_disconnect()
                break
        self.client.close()
        pygame.quit()

    def _draw_disconnect(self):
        overlay = pygame.Surface((C.WINDOW_W, C.WINDOW_H), pygame.SRCALPHA)
        overlay.fill((20, 20, 20, 200))
        self.screen.blit(overlay, (0, 0))
        msg = self.hud._text(self.hud.font_xl, "Disconnected")
        self.screen.blit(msg, ((C.WINDOW_W - msg.get_width()) / 2, 280))
        why = self.hud._text(self.hud.font_m,
                             self.client.error or "connection lost")
        self.screen.blit(why, ((C.WINDOW_W - why.get_width()) / 2, 350))
        pygame.display.flip()
        pygame.time.wait(2500)
