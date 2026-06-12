"""Base entity: position, velocity, health, body damage, knockback."""
from __future__ import annotations
import itertools
from ..core.vector import Vec2
from .. import config as C

_ids = itertools.count(1)


class Entity:
    kind = "entity"

    def __init__(self, world, pos: Vec2, radius: float, team: int,
                 max_health: float, body_damage: float):
        self.id = next(_ids)
        self.world = world
        self.pos = pos.copy()
        self.vel = Vec2()
        self.radius = radius
        self.team = team
        self.max_health = max_health
        self.health = max_health
        self.body_damage = body_damage
        self.alive = True
        self.friction = 6.0            # /s velocity damping
        self.push_factor = 1.0         # how easily this entity is shoved
        self.damage_flash = 0.0
        self.last_hit_time = -999.0
        self.last_attacker = None      # entity credited with the kill
        self.regen_rate = 0.0          # fraction of max hp / s
        self.xp_value = 0.0

    # ------------------------------------------------------------------
    def take_damage(self, amount: float, attacker=None):
        if not self.alive or amount <= 0:
            return
        self.health -= amount
        self.damage_flash = 0.12
        self.last_hit_time = self.world.time
        if attacker is not None:
            self.last_attacker = attacker
        if self.health <= 0:
            self.die()

    def die(self):
        self.alive = False
        self.world.on_entity_died(self)

    def heal(self, amount: float):
        self.health = min(self.max_health, self.health + amount)

    # ------------------------------------------------------------------
    def apply_knockback(self, direction: Vec2, strength: float):
        self.vel += direction * (strength * self.push_factor)

    def clamp_to_arena(self, dt: float):
        m = 0.0
        if self.pos.x < m:
            self.vel.x += C.BORDER_PUSH * dt * 6
        elif self.pos.x > C.ARENA_SIZE - m:
            self.vel.x -= C.BORDER_PUSH * dt * 6
        if self.pos.y < m:
            self.vel.y += C.BORDER_PUSH * dt * 6
        elif self.pos.y > C.ARENA_SIZE - m:
            self.vel.y -= C.BORDER_PUSH * dt * 6
        # hard clamp far outside
        pad = 120
        self.pos.x = max(-pad, min(C.ARENA_SIZE + pad, self.pos.x))
        self.pos.y = max(-pad, min(C.ARENA_SIZE + pad, self.pos.y))

    def update(self, dt: float):
        self.pos += self.vel * dt
        damp = max(0.0, 1.0 - self.friction * dt)
        self.vel = self.vel * damp
        if self.damage_flash > 0:
            self.damage_flash -= dt
        if self.regen_rate > 0 and self.health < self.max_health:
            self.heal(self.regen_rate * self.max_health * dt)
        self.clamp_to_arena(dt)
