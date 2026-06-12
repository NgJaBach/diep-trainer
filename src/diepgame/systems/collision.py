"""Narrow-phase collision resolution + contact damage rules."""
from __future__ import annotations
from ..core.vector import Vec2

# damage applied per second of overlap, scaled by the *other* side's body_damage
CONTACT_DPS_SCALE = 4.2
SEPARATION_FORCE = 260.0


def _hostile(a, b) -> bool:
    """Should these two entities damage each other?"""
    if a.team == b.team:
        return False
    # projectiles never hurt their own owner (covered by team) — neutral
    # shapes (team 0) hurt everyone and everyone hurts them.
    return True


def _owner(e):
    return getattr(e, "owner", None)


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

    # contact damage: each deals its body_damage to the other, per-second
    dmg_to_b = a.body_damage * CONTACT_DPS_SCALE * dt
    dmg_to_a = b.body_damage * CONTACT_DPS_SCALE * dt

    # bullets burn out fast on impact: trade hp directly so penetration matters
    a_proj = a.kind in ("bullet", "trap", "drone")
    b_proj = b.kind in ("bullet", "trap", "drone")
    if a_proj or b_proj:
        dmg_to_b = a.body_damage * (1.0 if a_proj else CONTACT_DPS_SCALE * dt)
        dmg_to_a = b.body_damage * (1.0 if b_proj else CONTACT_DPS_SCALE * dt)
        if a_proj and b_proj:
            # projectile vs projectile: simultaneous hp exchange
            pass

    credit_a = _owner(a) or a
    credit_b = _owner(b) or b
    b.take_damage(dmg_to_b, attacker=credit_a)
    a.take_damage(dmg_to_a, attacker=credit_b)
