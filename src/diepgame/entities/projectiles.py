"""Bullets, drones and traps fired/spawned by tank barrels."""
from __future__ import annotations
import math
import random
from .base import Entity
from ..core.vector import Vec2
from .. import config as C


class Bullet(Entity):
    kind = "bullet"

    def __init__(self, world, owner, pos: Vec2, vel: Vec2, radius: float,
                 damage: float, hp: float, lifetime: float = C.BULLET_LIFETIME):
        super().__init__(world, pos, radius, owner.team, hp, damage)
        self.owner = owner
        self.vel = vel
        self.lifetime = lifetime
        self.friction = 0.25
        self.push_factor = 0.6
        self.color = owner.color
        self.hit_gate: dict[int, float] = {}   # per-victim hit cooldowns

    def clamp_to_arena(self, dt: float):
        pass        # bullets fly past the wall and expire on their own

    def update(self, dt: float):
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.alive = False
            return
        super().update(dt)


class Trap(Bullet):
    kind = "trap"

    def __init__(self, world, owner, pos, vel, radius, damage, hp):
        super().__init__(world, owner, pos, vel, radius, damage, hp,
                         lifetime=C.TRAP_LIFETIME)
        self.friction = 1.8         # glide ~200 units before settling
        self.push_factor = 0.15
        self.rotation = random.uniform(0, math.tau)

    def clamp_to_arena(self, dt: float):
        Entity.clamp_to_arena(self, dt)   # traps are walls; keep them inside


class Drone(Bullet):
    """Controllable drone. Follows its owner's drone command each frame."""
    kind = "drone"

    def __init__(self, world, owner, pos, vel, radius, damage, hp,
                 swarm: bool = False):
        super().__init__(world, owner, pos, vel, radius, damage, hp,
                         lifetime=C.DRONE_LIFETIME)
        self.friction = 2.4
        self.push_factor = 0.8
        self.swarm = swarm           # battleship-style cheap drones
        self.accel = 1500.0 if swarm else 1150.0
        self.max_speed = 420.0 if swarm else 330.0
        self.orbit_phase = random.uniform(0, math.tau)
        if swarm:
            self.lifetime = 6.5

    def die(self):
        if self in getattr(self.owner, "drones", ()):
            self.owner.drones.remove(self)
        super().die()

    def update(self, dt: float):
        o = self.owner
        if not o.alive:
            self.alive = False
            return
        cmd, point = o.drone_command()
        if cmd == "attack":
            desired = (point - self.pos)
        elif cmd == "repel":
            desired = (self.pos - o.pos)
        else:  # idle: orbit the owner
            self.orbit_phase += 1.6 * dt
            anchor = o.pos + Vec2.from_angle(self.orbit_phase, o.radius * 2.6)
            desired = anchor - self.pos
        d = desired.normalized()
        self.vel += d * (self.accel * dt)
        sp = self.vel.length()
        ms = self.max_speed * (1.0 + 0.06 * o.stats[3])
        if sp > ms:
            self.vel = self.vel * (ms / sp)
        # drones use bullet lifetime rules of their own (effectively infinite)
        self.lifetime = C.DRONE_LIFETIME if not self.swarm else self.lifetime - dt
        if self.lifetime <= 0:
            self.die()
            return
        Entity.update(self, dt)
