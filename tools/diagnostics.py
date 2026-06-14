"""Systems diagnostics: assert the core mechanics behave as configured.

Numeric, headless, no images. Checks reload cadence, the discrete-hit damage
model, body-contact damage, health regen (slow + fast), recoil/boost, spawn
shield, and HP scaling. Run:  uv run python tools/diagnostics.py
"""
from __future__ import annotations
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from diepgame.systems.world import World
from diepgame.entities.tank import Tank
from diepgame.entities.shapes import Shape
from diepgame.core.vector import Vec2
from diepgame import config as C

DT = 1.0 / 60.0
_fails = []


def check(name, cond, detail=""):
    tag = "ok " if cond else "FAIL"
    print(f"[{tag}] {name}{('  — ' + detail) if detail else ''}")
    if not cond:
        _fails.append(name)


def fresh_world():
    w = World()
    w.next_boss_at = 1e18
    return w


def maxed(w, key="basic", level=1, pos=(2000, 2000), stat=None, pts=0):
    t = Tank(w, Vec2(*pos), "T", w.new_team(), def_key=key)
    if level > 1:
        t.add_score(C.xp_for_level(level))
    if stat is not None:
        for _ in range(pts):
            t.upgrade_stat(stat)
    t.shield_until = 0.0
    w.add(t)
    return t


def test_reload_cadence():
    w = fresh_world()
    t = maxed(w)
    t.aim_angle = 0.0
    shots = [0]
    real_spawn = w.add

    def counting_add(e):
        if e.kind == "bullet":
            shots[0] += 1
        real_spawn(e)
    w.add = counting_add
    t.shooting = True
    secs = 3.0
    for _ in range(int(secs / DT)):
        w.step(DT)
    expected = secs / t.reload_interval()
    check("reload cadence", abs(shots[0] - expected) <= 2,
          f"{shots[0]} shots vs ~{expected:.1f} expected "
          f"(interval {t.reload_interval():.3f}s)")


def test_discrete_hit():
    """One bullet should deal its damage ONCE, not per frame of overlap."""
    w = fresh_world()
    t = maxed(w, stat=5, pts=2)            # some bullet damage
    dmg = t.bullet_damage()
    victim = maxed(w, key="octo_tank", level=30, pos=(2140, 2000))
    victim.stats[1] = 7
    victim._refresh_derived()
    victim.move_input = Vec2()
    hp0 = victim.health
    t.aim_angle = 0.0
    fired = False
    drop = 0.0
    for i in range(int(1.2 / DT)):
        t.shooting = not fired
        if any(e.kind == "bullet" for e in w.entities):
            fired = True
        victim.pos = Vec2(2140, 2000)
        victim.vel = Vec2()
        w.step(DT)
        drop = hp0 - victim.health
        if drop > 0:
            # wait a few frames to ensure no per-frame stacking
            for _ in range(8):
                victim.pos = Vec2(2140, 2000)
                w.step(DT)
            break
    final = hp0 - victim.health
    check("discrete hit model", abs(final - dmg) <= dmg * 0.35 + 1,
          f"one bullet removed {final:.1f} hp (bullet dmg {dmg:.1f})")


def test_regen():
    w = fresh_world()
    t = maxed(w, level=20, stat=0, pts=5)   # regen stat
    t.health = t.max_health * 0.5
    t.last_hit_time = -999.0                 # eligible for fast regen
    before = t.health
    for _ in range(int(2.0 / DT)):
        t.move_input = Vec2()
        w.step(DT)
    check("health regen heals", t.health > before + 1,
          f"healed {t.health - before:.1f} hp in 2s")


def test_spawn_shield():
    w = fresh_world()
    t = maxed(w, level=10)
    t.shield_until = w.time + 5.0
    hp0 = t.health
    t.take_damage(9999, attacker=None)
    check("spawn shield blocks damage", t.health == hp0,
          f"hp {t.health:.0f} after big hit while shielded")
    t.shield_until = 0.0
    t.take_damage(5, attacker=None)
    check("shield expiry lets damage through", t.health < hp0)


def test_recoil_boost():
    w = fresh_world()
    t = maxed(w, key="annihilator", level=45)
    t.aim_angle = 0.0
    t.move_input = Vec2()
    t.shooting = True
    peak = 0.0
    for _ in range(int(1.0 / DT)):
        w.step(DT)
        peak = max(peak, t.boost_vel.length())
        t.shooting = False
    check("recoil produces boost thrust", peak > 80,
          f"peak boost {peak:.0f} px/s (separate from move cap)")


def test_hp_scaling():
    w = fresh_world()
    lo = maxed(w, level=1)
    hi = maxed(w, level=45, stat=1, pts=7)
    check("max-health scales with level+stat", hi.max_health > lo.max_health * 3,
          f"lvl1 {lo.max_health:.0f} -> lvl45+maxHP {hi.max_health:.0f}")


def test_body_contact_damage():
    w = fresh_world()
    t = maxed(w, key="smasher", level=30, pos=(2000, 2000))
    sq = Shape(w, Vec2(2000 + t.radius + 5, 2000), "square")
    sq.vel = Vec2()
    w.add(sq)
    hp0 = sq.health
    for _ in range(int(0.5 / DT)):
        sq.pos = Vec2(2000 + t.radius + 5, 2000)
        sq.vel = Vec2()
        w.step(DT)
        if not sq.alive:
            break
    check("body contact deals damage", sq.health < hp0 or not sq.alive,
          f"square hp {max(0, sq.health):.1f}/{hp0:.0f}")


if __name__ == "__main__":
    print("=== Polygon Arena systems diagnostics ===")
    test_reload_cadence()
    test_discrete_hit()
    test_body_contact_damage()
    test_regen()
    test_spawn_shield()
    test_recoil_boost()
    test_hp_scaling()
    print("=" * 42)
    if _fails:
        print(f"{len(_fails)} CHECK(S) FAILED: {', '.join(_fails)}")
        raise SystemExit(1)
    print("ALL SYSTEMS NOMINAL")
