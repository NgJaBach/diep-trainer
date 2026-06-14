"""A/B test: do the evolved genomes actually kill better and survive longer?

Champions (best trained genome) on BLUE vs baseline (hand-tuned default genome)
on RED, equal numbers, same spawn levels, fighting only each other (team mode,
no friendly fire). Counts cross-side kills and deaths. Run:

  uv run python tools/evaluate.py                 # champion vs default
  uv run python tools/evaluate.py --minutes 4 --per-side 8
"""
from __future__ import annotations
import argparse
import os
import random
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from diepgame import config as C
from diepgame.ai.genome import Genome
from diepgame.ai.population import Population, DEFAULT_PATH
from diepgame.ai.bot import BotController
from diepgame.entities.tank import Tank

DT = 1.0 / 30.0


def run(champ: Genome, base: Genome, per_side: int, seconds: float,
        arena: int, arche: str | None = None) -> dict:
    C.ARENA_SIZE = arena
    C.NEST_RADIUS = int(arena * 0.11)
    scale = (arena / 9000.0) ** 2
    C.SHAPE_TARGETS = {"square": int(300 * scale) + 30,
                       "triangle": int(160 * scale) + 16,
                       "pentagon": int(60 * scale) + 8, "alpha_pentagon": 2,
                       "crasher_small": int(18 * scale) + 2,
                       "crasher_large": int(11 * scale) + 1}
    from diepgame.systems.world import World
    w = World()
    w.mode = "team"
    w.next_boss_at = 1e18
    w.populate_initial()

    side = {}                       # tank id -> "champ"/"base"
    ctrls = []
    score = {"champ": {"k": 0, "d": 0}, "base": {"k": 0, "d": 0}}

    def spawn(which, genome, team):
        lvl = random.randint(1, 12)
        t = w.spawn_tank(which, def_key="basic", level=lvl, team=team)
        side[t.id] = which
        c = BotController(w, t, skill=1.15, genome=genome,
                          force_archetype=arche)
        c._spend_points(); c._maybe_upgrade_class()
        ctrls.append(c)
        return c

    for _ in range(per_side):
        spawn("champ", champ, C.TEAM_BLUE)
        spawn("base", base, C.TEAM_RED)

    orig = w.on_entity_died

    def on_died(e):
        if isinstance(e, Tank):
            who = side.pop(e.id, None)
            a = e.last_attacker
            kt = a if isinstance(a, Tank) else getattr(a, "owner", None)
            if who:
                score[who]["d"] += 1
            if isinstance(kt, Tank) and kt is not e:
                kw = side.get(kt.id)
                if kw and kw != who:
                    score[kw]["k"] += 1
        orig(e)
    w.on_entity_died = on_died

    pending = []
    for _ in range(int(seconds / DT)):
        now = w.time
        for c in list(ctrls):
            if not c.tank.alive:
                ctrls.remove(c)
                pending.append((now + 0.8, side_of(c)))
            else:
                c.update(DT)
        for item in list(pending):
            when, which = item
            if now >= when:
                pending.remove(item)
                spawn(which, champ if which == "champ" else base,
                      C.TEAM_BLUE if which == "champ" else C.TEAM_RED)
        w.step(DT)
    return score


def side_of(ctrl):
    return ctrl.tank.name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=1.0)
    ap.add_argument("--matches", type=int, default=3,
                    help="independent matches per species (averaged)")
    ap.add_argument("--per-side", type=int, default=8)
    ap.add_argument("--arena", type=int, default=4200)
    ap.add_argument("--path", default=str(DEFAULT_PATH))
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    random.seed(args.seed)

    pop = Population.load(args.path)
    if pop is None:
        raise SystemExit("no trained population found — run tools/train.py first")

    champs = pop.species_champions()
    print(f"gen {pop.generation} — champion (trained) vs baseline, same "
          f"playstyle, averaged over {args.matches} matches x "
          f"{args.minutes:.1f} min:\n")
    total_edge = 0
    for arche, m in champs.items():
        champ = Genome.from_dict(m["genome"])
        ck = cd = bk = bd = 0
        for j in range(args.matches):
            random.seed(args.seed + j * 101)
            s = run(champ, Genome.default(), args.per_side, args.minutes * 60,
                    args.arena, arche=arche)
            ck += s["champ"]["k"]; cd += s["champ"]["d"]
            bk += s["base"]["k"]; bd += s["base"]["d"]
        # the objective is kills MINUS deaths (out-kill AND out-survive)
        net = (ck - cd) - (bk - bd)
        total_edge += net
        verdict = "BETTER" if net > 4 else ("~base " if net >= -4 else "WORSE ")
        print(f"  [{verdict}] {arche:7s} ELO {m['elo']:4.0f} | "
              f"champ {ck:3d}k/{cd:3d}d  vs  base {bk:3d}k/{bd:3d}d  | "
              f"net K-D {ck-cd:+d} vs {bk-bd:+d}  (edge {net:+d})")
    print(f"\ntotal net (kills-deaths) edge to trained champions: {total_edge:+d}"
          f"  (positive = trained AI out-kills AND out-survives the baseline)")


if __name__ == "__main__":
    main()
