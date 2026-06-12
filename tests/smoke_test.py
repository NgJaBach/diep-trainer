"""Headless smoke test: simulates 30 seconds of gameplay with bots only.

Run with:  uv run python tests/smoke_test.py
"""
import os
import random
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from diepgame.systems.world import World
from diepgame.ai.bot import BotManager
from diepgame.tanks.definitions import TANK_DEFS
from diepgame import config as C


def test_tank_tree_is_wired():
    for key, t in TANK_DEFS.items():
        for up in t.upgrades_to:
            assert up in TANK_DEFS, f"{key} upgrades to unknown {up}"
        assert TANK_DEFS[key].tier in (1, 2, 3, 4)
    print(f"[ok] {len(TANK_DEFS)} tank classes, tree wired correctly")


def test_simulation(seconds=30.0, dt=1 / 30):
    random.seed(7)
    world = World()
    world.populate_initial()
    bots = BotManager(world)
    bots.spawn_initial()
    # force-level one bot to exercise upgrades quickly
    bots.controllers[0].tank.add_score(C.xp_for_level(45))
    steps = int(seconds / dt)
    for i in range(steps):
        bots.update(dt)
        world.step(dt)
    levels = sorted(t.level for t in world.tanks)
    classes = {t.def_key for t in world.tanks}
    assert any(l >= 45 for l in levels), "leveling failed"
    assert len(classes) > 1, "bots never class-upgraded"
    assert world.entities, "world emptied itself"
    print(f"[ok] simulated {seconds:.0f}s: {len(world.entities)} entities, "
          f"{len(world.tanks)} tanks alive, levels={levels}, "
          f"classes={sorted(classes)}")


def test_every_class_can_fire(dt=1 / 30):
    """Spawn one tank of every class and let it shoot for 3 seconds."""
    random.seed(1)
    world = World()
    from diepgame.entities.tank import Tank
    from diepgame.core.vector import Vec2
    for i, key in enumerate(TANK_DEFS):
        t = Tank(world, Vec2(300 + (i % 8) * 600, 300 + (i // 8) * 600),
                 key, world.new_team(), def_key=key)
        t.add_score(C.xp_for_level(45))
        t.shooting = True
        world.add(t)
    for _ in range(int(3 / dt)):
        world.step(dt)
    kinds = {e.kind for e in world.entities}
    assert "bullet" in kinds and "drone" in kinds and "trap" in kinds, kinds
    print(f"[ok] all {len(TANK_DEFS)} classes instantiated & projectiles "
          f"spawned: {sorted(kinds)}")


if __name__ == "__main__":
    test_tank_tree_is_wired()
    test_every_class_can_fire()
    test_simulation()
    print("ALL SMOKE TESTS PASSED")
