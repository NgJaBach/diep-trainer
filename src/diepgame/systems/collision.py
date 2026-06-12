"""Narrow-phase collision resolution + contact damage rules.

Two damage regimes:
  * body vs body (tank/shape grinding): continuous, scaled by dt — slow burn.
  * anything involving a projectile: a discrete exchange. On contact each
    side takes the other's body_damage ONCE, then that pair is on cooldown
    for HIT_COOLDOWN seconds. This makes damage frame-rate independent and
    makes bullet penetration meaningful: a bullet survives as many hits as
    its hp allows, losing the victim's body_damage per hit.
"""
from __future__ import annotations
from ..core.vector import Vec2

# damage applied per second of overlap, scaled by the *other* side's body_damage
CONTACT_DPS_SCALE = 4.2
SEPARATION_FORCE = 260.0
HIT_COOLDOWN = 0.25        # seconds between hits for the same projectile pair


def _hostile(a, b) -> bool:
    """Should these two entities damage each other?"""
    if a.team == b.team:
        return False
    # projectiles never hurt their own owner (covered by team) — neutral
    # shapes (team 0) hurt everyone and everyone hurts them.
    return True


def _owner(e):
    return getattr(e, "owner", None)


def _gate_open(proj, other, now: float) -> bool:
    """Per-pair hit cooldown, stored on the projectile."""
    gate = proj.hit_gate
    if now < gate.get(other.id, 0.0):
        return False
    gate[other.id] = now + HIT_COOLDOWN
    if len(gate) > 32:                      # drones live forever; prune
        for k in [k for k, v in gate.items() if v < now]:
            del gate[k]
    return True


def resolve(a, b, dt: float):
    if not (a.alive and b.alive):
        return
    delta = b.pos - a.pos
    rsum = a.radius + b.radius
    d2 = delta.length_sq()
    if d2 >= rsum * rsum:
        return
    dist = max(1e-4, d2 ** 0.5)
    n = delta / dist
    overlap = rsum - dist

    # positional separation / knockback
    total = a.push_factor + b.push_factor
    if total > 0:
        push = SEPARATION_FORCE * overlap / max(rsum, 1.0)
        a.vel -= n * (push * (a.push_factor / total) * dt * 60)
        b.vel += n * (push * (b.push_factor / total) * dt * 60)

    if not _hostile(a, b):
        return

    now = a.world.time
    # spawn-protected tanks neither take nor deal damage
    if getattr(a, "shield_until", 0.0) > now \
            or getattr(b, "shield_until", 0.0) > now:
        return

    a_proj = a.kind in ("bullet", "trap", "drone")
    b_proj = b.kind in ("bullet", "trap", "drone")

    if a_proj or b_proj:
        # discrete exchange, rate-limited per pair
        keeper = a if a_proj else b
        if a_proj and b_proj and b.id < a.id:
            keeper = b
        if not _gate_open(keeper, b if keeper is a else a, now):
            return
        dmg_to_b = a.body_damage
        dmg_to_a = b.body_damage
    else:
        # body contact: each deals its body_damage to the other, per-second
        dmg_to_b = a.body_damage * CONTACT_DPS_SCALE * dt
        dmg_to_a = b.body_damage * CONTACT_DPS_SCALE * dt

    credit_a = _owner(a) or a
    credit_b = _owner(b) or b
    b.take_damage(dmg_to_b, attacker=credit_a)
    a.take_damage(dmg_to_a, attacker=credit_b)
