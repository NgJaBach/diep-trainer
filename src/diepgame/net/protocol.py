"""Wire protocol: length-prefixed JSON frames + snapshot build/apply helpers.

Framing: a 4-byte big-endian unsigned length, then that many UTF-8 JSON bytes.
JSON keeps the protocol trivial to debug; on a LAN the bandwidth is ample.

Message types (``t`` field)
  client -> server : join, in (continuous input), cmd (discrete), bye
  server -> client : welcome, deny, snap

Snapshots use short keys and packed colors to stay compact. Tanks are always
sent in full (there are only ~tens of them) so the minimap/leaderboard stay
correct; the numerous shapes/bullets/drones/traps are area-of-interest culled
around each viewer.
"""
from __future__ import annotations
import json
import struct

from ..core.vector import Vec2

_HEADER = struct.Struct(">I")
MAX_FRAME = 8 * 1024 * 1024

# entity kind -> 1-char code and back
_K2C = {"shape": "s", "bullet": "b", "drone": "d", "trap": "p", "tank": "t"}
_C2K = {v: k for k, v in _K2C.items()}


# ----------------------------------------------------------------- framing ----
def encode(obj) -> bytes:
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    return _HEADER.pack(len(body)) + body


def recv_message(sock):
    """Blocking read of one framed message from a sync socket (None on EOF)."""
    head = _recv_exactly(sock, 4)
    if head is None:
        return None
    (length,) = _HEADER.unpack(head)
    if length == 0 or length > MAX_FRAME:
        return None
    body = _recv_exactly(sock, length)
    if body is None:
        return None
    return json.loads(body.decode("utf-8"))


def _recv_exactly(sock, n):
    buf = bytearray()
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except OSError:
            return None
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


async def read_message(reader):
    """Async read of one framed message (None on EOF/short read)."""
    try:
        head = await reader.readexactly(4)
        (length,) = _HEADER.unpack(head)
        if length == 0 or length > MAX_FRAME:
            return None
        body = await reader.readexactly(length)
    except (EOFError, OSError, ConnectionError):
        return None
    return json.loads(body.decode("utf-8"))


# --------------------------------------------------------------- color util ----
def pack_rgb(c) -> int:
    return (int(c[0]) << 16) | (int(c[1]) << 8) | int(c[2])


def unpack_rgb(v: int):
    return ((v >> 16) & 255, (v >> 8) & 255, v & 255)


# ------------------------------------------------------------- build (host) ----
def build_snapshot(world, viewer, session=None, aoi=2200.0) -> dict:
    """Serialize the part of ``world`` relevant to ``viewer`` (a Tank)."""
    vx, vy = viewer.pos.x, viewer.pos.y
    a2 = aoi * aoi

    ents = []
    for e in world.entities:
        if not e.alive or e.kind == "tank":
            continue
        dx, dy = e.pos.x - vx, e.pos.y - vy
        if dx * dx + dy * dy > a2:
            continue
        rec = {"i": e.id, "k": _K2C[e.kind],
               "x": round(e.pos.x, 1), "y": round(e.pos.y, 1),
               "r": round(e.radius, 1), "c": pack_rgb(e.color)}
        if e.kind == "shape":
            rec["s"] = e.sides
            rec["o"] = round(e.rotation, 2)
            if getattr(e, "shiny", False):
                rec["sh"] = 1
            if e.health < e.max_health - 0.5:     # damaged: show a health bar
                rec["hf"] = round(e.health / e.max_health, 2)
        elif e.kind == "drone":
            rec["s"] = getattr(e, "sides", 3)
            rec["o"] = round(e.vel.angle(), 2)
        elif e.kind == "trap":
            rec["o"] = round(getattr(e, "rotation", 0.0), 2)
        ents.append(rec)

    tanks = []
    for t in world.tanks:
        if not t.alive:
            continue
        tanks.append({
            "i": t.id, "x": round(t.pos.x, 1), "y": round(t.pos.y, 1),
            "r": round(t.radius, 1), "d": t.def_key, "a": round(t.aim_angle, 3),
            "n": t.name, "tm": t.team, "hp": round(t.health, 1),
            "mhp": round(t.max_health, 1), "ia": round(t.invisible_alpha, 2),
            "fl": round(t.damage_flash, 3), "sc": round(t.score),
            "lv": t.level,
            "sld": 1 if world.time < getattr(t, "shield_until", 0.0) else 0})

    fx = [{"x": round(f["pos"].x, 1), "y": round(f["pos"].y, 1),
           "r": round(f["radius"], 1), "c": pack_rgb(f["color"]),
           "s": f["sides"], "o": round(f["rotation"], 2),
           "a": round(f["age"], 3), "du": round(f["dur"], 3)}
          for f in world.effects
          if (f["pos"].x - vx) ** 2 + (f["pos"].y - vy) ** 2 <= a2]

    boss = None
    if world.boss is not None and world.boss.alive:
        boss = [round(world.boss.pos.x, 1), round(world.boss.pos.y, 1)]

    you = {"id": viewer.id, "al": viewer.alive, "sp": viewer.stat_points,
           "st": list(viewer.stats), "sc": round(viewer.score),
           "lv": viewer.level, "d": viewer.def_key, "tm": viewer.team,
           "k": viewer.kills}
    if not viewer.alive and session is not None:
        you["by"] = session.killed_by
        you["ta"] = round(session.death_time - session.spawn_time, 1)
        you["cl"] = session.death_class

    return {"t": "snap", "ts": round(world.time, 3), "md": world.mode,
            "e": ents, "tk": tanks, "fx": fx, "boss": boss,
            "kf": [text for text, _ in world.kill_feed], "you": you}


def apply_input(tank, msg):
    """Apply a continuous-input message to a tank (server side)."""
    mv = msg.get("mv")
    if mv:
        tank.move_input = Vec2(mv[0], mv[1])
    else:
        tank.move_input = Vec2()
    if "ax" in msg:                       # precise world aim point (drones)
        tank.aim_target = Vec2(msg["ax"], msg["ay"])
        tank.aim_angle = (tank.aim_target - tank.pos).angle()
    elif "aim" in msg:
        tank.aim_angle = msg["aim"]
        tank.aim_target = tank.pos + Vec2.from_angle(msg["aim"], 600.0)
    tank.shooting = bool(msg.get("sh"))
    tank.repelling = bool(msg.get("rp"))
    tank.auto_fire = bool(msg.get("af"))
    tank.auto_spin = bool(msg.get("as"))
