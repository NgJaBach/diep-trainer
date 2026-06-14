"""LAN netcode integration test: a real GameServer + real NetClient over a
loopback socket, driven headlessly. No window.

Run with:  uv run python tests/net_test.py
"""
import os
import time
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from diepgame.systems.world import World
from diepgame.ai.bot import BotManager
from diepgame.net.server import GameServer
from diepgame.net.client import NetClient
from diepgame.core.vector import Vec2
from diepgame import config as C

PORT = 8799
DT = 1 / 60


def _tick(world, bots, server, n):
    for _ in range(n):
        server.pump()
        bots.update(DT)
        world.step(DT)
        server.publish()
        time.sleep(DT)


def test_protocol_roundtrip():
    from diepgame.net import protocol as P
    msg = {"t": "in", "mv": [1, 0], "aim": 0.5}
    data = P.encode(msg)
    assert len(data) > 4
    assert P.pack_rgb((0, 178, 225)) == (0 << 16) | (178 << 8) | 225
    assert P.unpack_rgb(P.pack_rgb((1, 2, 3))) == (1, 2, 3)
    print("[ok] protocol encode/color round-trips")


def test_password_rejected():
    world = World()
    server = GameServer(world, password="secret")
    assert server.start(PORT + 1), "server failed to bind"
    try:
        bad = NetClient("127.0.0.1", PORT + 1, "Hacker", password="wrong")
        assert not bad.connect(), "client with wrong password should be denied"
        assert "password" in (bad.error or "")
        print("[ok] wrong password is rejected:", bad.error)
    finally:
        server.stop()


def test_full_session():
    world = World()
    world.mode = "team"
    world.populate_initial()
    bots = BotManager(world)
    bots.spawn_initial()
    server = GameServer(world)
    assert server.start(PORT), "server failed to bind"
    try:
        client = NetClient("127.0.0.1", PORT, "Remote", password="")
        assert client.connect(), f"client could not connect: {client.error}"
        assert client.mode == "team"

        # let the join register and snapshots flow
        _tick(world, bots, server, 20)
        assert server.player_count == 1, "server did not spawn the remote tank"

        snap = client.latest()
        assert snap is not None, "client received no snapshot"
        you = snap["you"]
        assert you["al"] and you["tm"] == C.TEAM_BLUE, "remote not on blue team"
        assert any(t["tm"] == C.TEAM_RED for t in snap["tk"]), "no red bots"
        start_id = you["id"]

        # find our tank, record position, then drive right for ~1s
        tank = next(t for t in world.tanks if t.id == start_id)
        x0 = tank.pos.x
        for _ in range(60):
            client.send_input(Vec2(1, 0), tank.pos + Vec2(600, 0),
                              shooting=True, repelling=False)
            _tick(world, bots, server, 1)
        assert tank.pos.x - x0 > 80, f"remote tank didn't move (dx={tank.pos.x-x0:.0f})"
        assert any(e.kind == "bullet" for e in world.entities), "no bullets fired"
        print(f"[ok] remote player moved {tank.pos.x - x0:.0f}px and fired")

        # level up (grants skill points + class choice), then upgrade remotely
        tank.add_score(C.xp_for_level(15))
        client.upgrade_stat(6)            # reload
        _tick(world, bots, server, 6)
        assert tank.stats[6] >= 1, "stat command not applied"
        client.upgrade_class("twin")
        _tick(world, bots, server, 6)
        assert tank.def_key == "twin", "class command not applied"
        print("[ok] remote stat + class upgrades applied")

        # interpolation should return a usable snapshot
        interp = client.interpolated()
        assert interp is not None and "tk" in interp
        print("[ok] snapshot interpolation returns frames")

        # death + respawn
        tank.take_damage(1e9, attacker=None)
        _tick(world, bots, server, 5)
        snap = client.latest()
        assert not snap["you"]["al"], "client not told it died"
        client.respawn()
        _tick(world, bots, server, 10)
        assert server.player_count == 1
        new_tank = next(t for t in world.tanks
                        if t.team == C.TEAM_BLUE and t.alive)
        assert new_tank.id != start_id, "respawn did not create a new tank"
        print("[ok] death reported + respawn works")

        # disconnect frees the slot
        client.close()
        _tick(world, bots, server, 10)
        assert server.player_count == 0, "session not cleaned up on disconnect"
        print("[ok] disconnect cleans up the session")
    finally:
        server.stop()


if __name__ == "__main__":
    test_protocol_roundtrip()
    test_password_rejected()
    test_full_session()
    print("ALL NET TESTS PASSED")
