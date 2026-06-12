"""Per-class balance audit.

Table 1 (static): frontal DPS, biggest per-bullet hit, fire interval, range,
recoil thrust, speed, HP — for a level-45 tank built along its archetype.

Table 2 (empirical): time-to-kill a standard level-30 dummy (108 hp, pinned)
from the class's ideal range, full build, 30 s cap.
"""
import os, math, random
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from diepgame.systems.world import World
from diepgame.entities.tank import Tank
from diepgame.core.vector import Vec2
from diepgame.tanks.definitions import TANK_DEFS
from diepgame.ai.bot import BUILDS, ARCHETYPE, IDEAL_RANGE
from diepgame import config as C

DT = 1 / 60


def build_tank(world, key, pos):
    t = Tank(world, pos, key, world.new_team(), def_key=key)
    t.add_score(C.xp_for_level(45))
    order = BUILDS[ARCHETYPE.get(key, "bullet")]
    guard = 0
    while t.stat_points > 0 and guard < 60:
        guard += 1
        for idx in order:
            if t.stats[idx] < C.MAX_STAT and t.upgrade_stat(idx):
                break
        else:
            break
    t.shield_until = 0.0
    return t


def static_table():
    random.seed(0)
    world = World()
    print(f"{'class':<15}{'arch':<7}{'fDPS':>6}{'hit':>6}{'int_s':>7}"
          f"{'range':>7}{'thrust':>7}{'speed':>6}{'hp':>6}")
    rows = []
    for key in TANK_DEFS:
        t = build_tank(world, key, Vec2(2000, 2000))
        base = t.reload_interval()
        D = t.bullet_damage()
        fdps = hit = 0.0
        interval = 0.0
        rng = 0.0
        thrust = Vec2()
        for sp in t.tdef.barrels:
            rate = 1.0 / (base * sp.reload)
            thrust -= Vec2.from_angle(math.radians(sp.angle)) \
                * (C.RECOIL_IMPULSE * sp.recoil * rate)
            if sp.kind != "bullet":
                continue
            if math.cos(math.radians(sp.angle)) > 0.7:   # frontal cone
                fdps += D * sp.dmg * rate
                if D * sp.dmg > hit:
                    hit = D * sp.dmg
                    interval = base * sp.reload
            rng = max(rng, t.bullet_speed() * sp.spd * C.BULLET_LIFETIME)
        fwd_boost = max(0.0, thrust.x / C.BOOST_DECAY)   # aim = 0 rad
        spd = t.move_speed() + fwd_boost
        rows.append((key, fdps))
        print(f"{key:<15}{ARCHETYPE.get(key,'?'):<7}{fdps:>6.0f}{hit:>6.0f}"
              f"{interval:>7.2f}{rng:>7.0f}{fwd_boost:>7.0f}{spd:>6.0f}"
              f"{t.max_health:>6.0f}")
    return dict(rows)


def ttk_table():
    print(f"\n{'class':<15}{'range':>6}{'TTK_s':>7}   notes")
    for key in TANK_DEFS:
        random.seed(1)
        world = World()                  # empty: pure duel
        arche = ARCHETYPE.get(key, "bullet")
        rng = max(120.0, IDEAL_RANGE[arche])
        t = build_tank(world, key, Vec2(3000.0, 3000.0))
        world.add(t)
        dummy = Tank(world, Vec2(3000.0 + rng, 3000.0), "Dummy",
                     world.new_team())
        dummy.add_score(C.xp_for_level(45))
        for _ in range(7):
            dummy.upgrade_stat(1)       # max-health build: ~278 hp
        dummy.shield_until = 0.0
        world.add(dummy)
        home = Vec2(3000.0 + rng, 3000.0)

        t.aim_angle = 0.0
        ttk = None
        for i in range(int(30.0 / DT)):
            t.aim_angle = (dummy.pos - t.pos).angle()
            t.aim_target = dummy.pos
            t.shooting = True
            if arche == "body":
                t.move_input = (dummy.pos - t.pos).normalized()
            else:
                t.move_input = Vec2()
                t.pos = Vec2(3000.0, 3000.0)
                t.vel = Vec2()
                t.boost_vel = Vec2()
            # pin the dummy near home so knockback can't end the test
            if dummy.pos.dist_to(home) > 150:
                dummy.pos = home.copy()
                dummy.vel = Vec2()
            world.step(DT)
            if not dummy.alive:
                ttk = (i + 1) * DT
                break
        note = "" if ttk else f"dummy at {dummy.health:.0f}/{dummy.max_health:.0f} hp"
        print(f"{key:<15}{rng:>6.0f}{(ttk if ttk else 99):>7.1f}   {note}")


if __name__ == "__main__":
    static_table()
    ttk_table()
