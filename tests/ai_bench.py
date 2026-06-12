"""Bot AI benchmark: run before/after AI changes and compare the numbers.

Run with:  uv run python tests/ai_bench.py

Three probes:
  * arena   — fixed-seed 150s bot-vs-bot sim: deaths, kills, levels, scores
  * dodge   — a turret fires perfectly-led bullets at one bot; counts hits
  * pressure— a stationary player dummy; how fast do bots punish it?
"""
import os, random, statistics
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from diepgame.systems.world import World
from diepgame.ai.bot import BotManager, BotController
from diepgame.entities.tank import Tank
from diepgame.entities.projectiles import Bullet
from diepgame.core.vector import Vec2
from diepgame import config as C

DT = 1 / 60


def arena(seed, seconds=150.0, dt=1 / 30):
    random.seed(seed)
    world = World()
    world.populate_initial()
    bots = BotManager(world)
    bots.spawn_initial()

    deaths = [0]
    orig = world.on_entity_died

    def hook(e):
        if isinstance(e, Tank):
            deaths[0] += 1
        orig(e)
    world.on_entity_died = hook

    for _ in range(int(seconds / dt)):
        bots.update(dt)
        world.step(dt)

    alive = [c.tank for c in bots.controllers if c.tank.alive]
    levels = [t.level for t in alive]
    print(f"arena seed {seed}: deaths={deaths[0]} "
          f"kills={sum(t.kills for t in alive)} "
          f"avg_lvl={statistics.mean(levels):.1f} max_lvl={max(levels)} "
          f"max_score={max(t.score for t in alive):.0f} "
          f"classes={sorted({t.def_key for t in alive})}")


def dodge(seconds=12.0):
    random.seed(3)
    world = World()                      # no shapes: isolate the duel
    bot_tank = world.spawn_tank("Dodger", level=10)
    bot_tank.pos = Vec2(3000.0, 3000.0)
    ctrl = BotController(world, bot_tank, skill=1.3)
    shooter = world.spawn_tank("Turret", level=45)
    shooter.pos = Vec2(3700.0, 3000.0)

    hits = [0]
    orig = bot_tank.take_damage

    def counted(amount, attacker=None):
        hits[0] += 1
        orig(amount, attacker)
    bot_tank.take_damage = counted

    fire_t, shots = 0.0, 0
    for _ in range(int(seconds / DT)):
        shooter.pos = Vec2(3700.0, 3000.0)   # turret is bolted down
        shooter.vel = Vec2()
        fire_t -= DT
        if fire_t <= 0 and bot_tank.alive:
            fire_t = 0.4
            shots += 1
            bspd = 700.0
            lead = bot_tank.pos.copy()
            for _ in range(2):
                lead = bot_tank.pos + bot_tank.vel * (shooter.pos.dist_to(lead) / bspd)
            d = (lead - shooter.pos).normalized()
            world.add(Bullet(world, shooter, shooter.pos + d * 60, d * bspd,
                             10.0, 6.0, 50.0, lifetime=4.0))
        if bot_tank.alive:
            ctrl.update(DT)
        world.step(DT)
    print(f"dodge: {shots} aimed shots -> {hits[0]} hit-frames, "
          f"survived={bot_tank.alive}")


def pressure(dummy_level, seconds=90.0):
    random.seed(9)
    world = World()
    world.populate_initial()
    bots = BotManager(world)
    bots.spawn_initial()
    dummy = world.spawn_tank("Dummy", is_player=True, level=dummy_level)
    dummy.pos = Vec2(2600.0, 2000.0)
    world.player = dummy

    died_at = None
    for i in range(int(seconds / DT)):
        dummy.move_input = Vec2()
        dummy.shooting = False
        bots.update(DT)
        world.step(DT)
        if not dummy.alive:
            died_at = i * DT
            break
    when = f"{died_at:.0f}s" if died_at is not None else f"survived {seconds:.0f}s"
    print(f"pressure(lvl {dummy_level} dummy): killed in {when}")


if __name__ == "__main__":
    for seed in (5, 11, 23):
        arena(seed)
    dodge()
    pressure(15)
    pressure(30)
