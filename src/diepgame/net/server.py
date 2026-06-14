"""Authoritative game server.

The host's game loop owns the simulation and calls :meth:`GameServer.pump`
(drain joins/leaves, apply inputs) before stepping the world and
:meth:`GameServer.publish` after. All socket I/O runs on a private asyncio
loop in a background thread; the two sides communicate through plain
structures guarded by a lock, using latest-value slots so a slow client can
never lag the simulation.
"""
from __future__ import annotations
import asyncio
import threading

from .protocol import (encode, read_message, build_snapshot, apply_input)
from .. import config as C


class Session:
    __slots__ = ("cid", "name", "writer", "tank", "input", "cmds", "snap",
                 "connected", "spawn_time", "death_time", "death_recorded",
                 "killed_by", "death_class")

    def __init__(self, cid: int, name: str):
        self.cid = cid
        self.name = name
        self.writer = None
        self.tank = None
        self.input: dict = {}
        self.cmds: list = []
        self.snap: bytes = b""
        self.connected = True
        self.spawn_time = 0.0
        self.death_time = 0.0
        self.death_recorded = False
        self.killed_by = "the arena"
        self.death_class = ""


class GameServer:
    def __init__(self, world, password: str = "",
                 snapshot_hz: int = C.NET_SNAPSHOT_HZ,
                 aoi: float = C.NET_AOI_RADIUS):
        self.world = world
        self.password = password or ""
        self.snapshot_hz = snapshot_hz
        self.aoi = aoi
        self.sessions: dict[int, Session] = {}
        self.lock = threading.Lock()
        self._join_q: list[int] = []
        self._leave_q: list[int] = []
        self._next_cid = 1
        self._loop = None
        self._server = None
        self._thread = None
        self._ready = threading.Event()
        self.port = C.NET_PORT

    # ----------------------------------------------------- lifecycle (host) --
    def start(self, port: int = C.NET_PORT) -> bool:
        self.port = port
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return self._ready.wait(timeout=5.0)

    def stop(self):
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        try:
            fut = asyncio.run_coroutine_threadsafe(self._shutdown(), loop)
            fut.result(timeout=1.0)
        except (RuntimeError, TimeoutError, OSError):
            pass
        loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    async def _shutdown(self):
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except OSError:
                pass
        pending = [t for t in asyncio.all_tasks(self._loop)
                   if t is not asyncio.current_task()]
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    @property
    def player_count(self) -> int:
        return sum(1 for s in self.sessions.values() if s.tank is not None)

    # ----------------------------------------------------- asyncio I/O side --
    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except OSError:
            self._ready.set()        # unblock start(); caller sees not serving
            return
        self._loop.run_forever()

    async def _serve(self):
        self._server = await asyncio.start_server(
            self._handle, "0.0.0.0", self.port)
        self._ready.set()

    async def _handle(self, reader, writer):
        msg = await read_message(reader)
        if not msg or msg.get("t") != "join":
            writer.close()
            return
        if self.password and str(msg.get("pw", "")) != self.password:
            writer.write(encode({"t": "deny", "why": "wrong password"}))
            try:
                await writer.drain()
            except (OSError, ConnectionError):
                pass
            writer.close()
            return
        name = (str(msg.get("name") or "Player").strip() or "Player")[:16]
        with self.lock:
            cid = self._next_cid
            self._next_cid += 1
            sess = Session(cid, name)
            sess.writer = writer
            self.sessions[cid] = sess
            self._join_q.append(cid)
        writer.write(encode({"t": "welcome", "cid": cid, "arena": C.ARENA_SIZE,
                             "mode": self.world.mode, "snap_hz": self.snapshot_hz,
                             "proto": C.NET_PROTOCOL}))
        try:
            await writer.drain()
        except (OSError, ConnectionError):
            pass

        sender = asyncio.create_task(self._sender(sess))
        try:
            while True:
                m = await read_message(reader)
                if m is None or m.get("t") == "bye":
                    break
                t = m.get("t")
                if t == "in":
                    with self.lock:
                        sess.input = m
                elif t == "cmd":
                    with self.lock:
                        sess.cmds.append(m)
        finally:
            sender.cancel()
            with self.lock:
                sess.connected = False
                self._leave_q.append(cid)
            try:
                writer.close()
            except OSError:
                pass

    async def _sender(self, sess: Session):
        interval = 1.0 / self.snapshot_hz
        try:
            while True:
                await asyncio.sleep(interval)
                with self.lock:
                    data = sess.snap
                if data:
                    sess.writer.write(data)
                    await sess.writer.drain()
        except (asyncio.CancelledError, OSError, ConnectionError):
            return

    # --------------------------------------------------- simulation side -----
    def pump(self):
        """Game thread: apply joins/leaves and the latest client input."""
        with self.lock:
            joins, self._join_q = self._join_q, []
            leaves, self._leave_q = self._leave_q, []
            work = [(s, s.input, s.cmds) for s in self.sessions.values()]
            for s in self.sessions.values():
                s.cmds = []
        for cid in joins:
            self._spawn_for(cid)
        for sess, inp, cmds in work:
            t = sess.tank
            if t is not None and t.alive:
                if inp:
                    apply_input(t, inp)
                for c in cmds:
                    self._apply_cmd(sess, c)
            else:
                if any(c.get("c") == "respawn" for c in cmds):
                    self._respawn(sess)
        for cid in leaves:
            self._remove(cid)

    def publish(self):
        """Game thread: record deaths, then encode each client's snapshot."""
        with self.lock:
            sessions = list(self.sessions.values())
        for sess in sessions:
            t = sess.tank
            if t is None:
                continue
            if not t.alive and not sess.death_recorded:
                sess.death_recorded = True
                sess.death_time = self.world.time
                sess.death_class = t.tdef.name
                a = t.last_attacker
                sess.killed_by = getattr(a, "name", None) or (
                    getattr(a, "shape_type", "the arena").replace("_", " ")
                    if a is not None else "the arena")
            data = encode(build_snapshot(self.world, t, session=sess,
                                         aoi=self.aoi))
            with self.lock:
                sess.snap = data

    def _spawn_for(self, cid: int):
        sess = self.sessions.get(cid)
        if sess is None:
            return
        sess.tank = self.world.spawn_tank(
            sess.name, is_player=False, team=self.world.human_team(),
            color=C.COL_PLAYER)
        sess.spawn_time = self.world.time
        sess.death_recorded = False

    def _respawn(self, sess: Session):
        if sess.tank is not None and sess.tank.alive:
            return
        sess.tank = self.world.spawn_tank(
            sess.name, is_player=False, team=self.world.human_team(),
            color=C.COL_PLAYER)
        sess.spawn_time = self.world.time
        sess.death_recorded = False

    def _apply_cmd(self, sess: Session, c: dict):
        cc = c.get("c")
        t = sess.tank
        if t is None:
            return
        if cc == "stat":
            t.upgrade_stat(int(c.get("i", -1)))
        elif cc == "class":
            t.upgrade_class(str(c.get("k", "")))

    def _remove(self, cid: int):
        sess = self.sessions.pop(cid, None)
        if sess is not None and sess.tank is not None and sess.tank.alive:
            sess.tank.alive = False
