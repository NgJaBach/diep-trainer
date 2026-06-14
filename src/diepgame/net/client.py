"""Network client: connects to a host, sends input, buffers snapshots.

Receiving runs on a background thread; sending happens from the main (pygame)
thread, which is safe since send and recv are independent directions of the
socket. Snapshots are kept in a short buffer so the render side can
interpolate ~one snapshot in the past for smooth motion.
"""
from __future__ import annotations
import socket
import threading
from collections import deque

from . import protocol
from .protocol import encode, recv_message
from .. import config as C


class NetClient:
    def __init__(self, host: str, port: int, name: str, password: str = ""):
        self.host = host
        self.port = port
        self.name = name
        self.password = password or ""
        self.sock: socket.socket | None = None
        self.cid = None
        self.arena = C.ARENA_SIZE
        self.mode = "ffa"
        self.error: str | None = None
        self.connected = False
        self._buffer: deque = deque(maxlen=8)
        self._lock = threading.Lock()
        self._recv_thread = None
        self._running = False

    # ------------------------------------------------------------- connect --
    def connect(self, timeout: float = 5.0) -> bool:
        try:
            self.sock = socket.create_connection((self.host, self.port),
                                                 timeout=timeout)
            self.sock.settimeout(None)
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError as e:
            self.error = f"could not reach {self.host}:{self.port} ({e})"
            return False
        self._send({"t": "join", "name": self.name, "pw": self.password})
        welcome = recv_message(self.sock)
        if not welcome or welcome.get("t") != "welcome":
            self.error = (welcome or {}).get("why", "connection refused")
            self.sock.close()
            return False
        if welcome.get("proto") != C.NET_PROTOCOL:
            self.error = "version mismatch with host"
            self.sock.close()
            return False
        self.cid = welcome["cid"]
        self.arena = welcome.get("arena", C.ARENA_SIZE)
        self.mode = welcome.get("mode", "ffa")
        self.connected = True
        self._running = True
        self._recv_thread = threading.Thread(target=self._recv_loop,
                                              daemon=True)
        self._recv_thread.start()
        return True

    def close(self):
        self._running = False
        if self.sock is not None:
            try:
                self._send({"t": "bye"})
            except OSError:
                pass
            try:
                self.sock.close()
            except OSError:
                pass

    # -------------------------------------------------------------- recv -----
    def _recv_loop(self):
        while self._running:
            msg = recv_message(self.sock)
            if msg is None:
                self.connected = False
                self.error = self.error or "disconnected from host"
                return
            if msg.get("t") == "snap":
                with self._lock:
                    self._buffer.append(msg)

    # -------------------------------------------------------------- send -----
    def _send(self, obj):
        if self.sock is not None:
            self.sock.sendall(encode(obj))

    def send_input(self, mv, aim_world, shooting, repelling,
                   auto_fire=False, auto_spin=False):
        if not self.connected:
            return
        msg = {"t": "in", "mv": [round(mv.x, 3), round(mv.y, 3)],
               "ax": round(aim_world.x, 1), "ay": round(aim_world.y, 1),
               "sh": bool(shooting), "rp": bool(repelling),
               "af": bool(auto_fire), "as": bool(auto_spin)}
        try:
            self._send(msg)
        except OSError:
            self.connected = False

    def send_cmd(self, **fields):
        if not self.connected:
            return
        try:
            self._send({"t": "cmd", **fields})
        except OSError:
            self.connected = False

    def upgrade_stat(self, idx):
        self.send_cmd(c="stat", i=int(idx))

    def upgrade_class(self, key):
        self.send_cmd(c="class", k=str(key))

    def respawn(self):
        self.send_cmd(c="respawn")

    # ------------------------------------------------- interpolated view -----
    def latest(self):
        with self._lock:
            return self._buffer[-1] if self._buffer else None

    def interpolated(self, delay: float = C.NET_INTERP_DELAY):
        """Return a snapshot with entity/tank positions lerped ~delay behind."""
        with self._lock:
            snaps = list(self._buffer)
        if not snaps:
            return None
        if len(snaps) == 1:
            return snaps[-1]
        target = snaps[-1]["ts"] - delay
        prev = snaps[0]
        nxt = None
        for s in snaps:
            if s["ts"] >= target:
                nxt = s
                break
            prev = s
        if nxt is None or nxt is prev or nxt["ts"] <= prev["ts"]:
            return snaps[-1]
        alpha = (target - prev["ts"]) / (nxt["ts"] - prev["ts"])
        alpha = max(0.0, min(1.0, alpha))
        return _lerp(prev, nxt, alpha)


def _lerp(a: dict, b: dict, t: float) -> dict:
    """Position-lerp entities/tanks of b toward their earlier pose in a."""
    out = dict(b)
    pa = {e["i"]: e for e in a["e"]}
    out["e"] = [_lerp_pos(pa.get(e["i"]), e, t) for e in b["e"]]
    ta = {e["i"]: e for e in a["tk"]}
    out["tk"] = [_lerp_pos(ta.get(e["i"]), e, t) for e in b["tk"]]
    return out


def _lerp_pos(old, new, t):
    if old is None:
        return new
    r = dict(new)
    r["x"] = old["x"] + (new["x"] - old["x"]) * t
    r["y"] = old["y"] + (new["y"] - old["y"]) * t
    return r
