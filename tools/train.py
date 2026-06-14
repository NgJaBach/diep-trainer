"""Parallel evolutionary self-play trainer for the bot AI.

Runs one dense headless FFA arena per CPU core (multiprocessing). Every kill is
an ELO match for the genomes involved; dying to the arena costs ELO. Each
generation the master ships the current genomes to all workers, they each
simulate `--gen-seconds` of combat in parallel and return kill/death events,
the master replays those into the ELO ladder, evolves (cull worst, breed best)
and saves. Stop anytime (Ctrl+C / kill) — at most one generation is lost.

  uv run python tools/train.py                  # all cores, defaults
  uv run python tools/train.py --hours 12       # long unattended run
  uv run python tools/train.py --workers 6      # cap worker processes
  uv run python tools/train.py --fresh          # ignore saved population

Outputs:  training/population.json   (evolving brains + ELO)
          training/log.csv          (per-generation telemetry)
"""
from __future__ import annotations
import argparse
import csv
import os
import random
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

DT = 1.0 / 30.0


# ----------------------------------------------------------------- worker ----
# A worker runs ONE arena for `sim_seconds` and returns match events. It is a
# top-level function so it pickles cleanly to spawned processes. Heavy imports
# happen inside so each process initializes its own engine state.
def run_episode(job: dict):
    import os as _os
    _os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    _os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import random as _r
    from collections import defaultdict
    from diepgame import config as C
    from diepgame.ai.genome import Genome, DEFAULT_GENOME
    from diepgame.ai.bot import BotController, SPECIES
    from diepgame.entities.tank import Tank
    from diepgame.systems.world import World

    _r.seed(job["seed"])
    C.ARENA_SIZE = job["arena"]
    C.NEST_RADIUS = int(job["arena"] * 0.11)
    C.SHAPE_TARGETS = job["shapes"]

    members = job["members"]           # [{id, genome, arche}]
    genomes = {m["id"]: Genome.from_dict(m["genome"]) for m in members}
    by_species = defaultdict(list)
    for m in members:
        by_species[m["arche"]].append(m["id"])
    n_bots = job["bots"]

    from diepgame import config as C2  # team ids
    world = World()
    world.mode = "team"                # candidates (blue) vs baseline (red):
    world.next_boss_at = 1e18          # every PvP kill is a fitness signal
    world.populate_initial()

    role_of: dict[int, tuple] = {}     # tank id -> ("cand", gid) | ("ref", arche)
    ctrl_slot = {}                     # ctrl -> slot spec ("cand"/"ref")
    ref_kills, ref_deaths, env_deaths = [], [], []
    per_side = max(1, n_bots // 2)
    roster = ["cand"] * per_side + ["ref"] * per_side

    def spawn(slot):
        arche = _r.choice([s for s in SPECIES if by_species[s]])
        if slot == "ref":
            genome, tag = DEFAULT_GENOME, ("ref", arche)
            team = C2.TEAM_RED
        else:
            gid = _r.choice(by_species[arche])
            genome, tag = genomes[gid], ("cand", gid)
            team = C2.TEAM_BLUE
        tank = world.spawn_tank("b", def_key="basic", level=_r.randint(1, 14),
                                team=team)
        role_of[tank.id] = tag
        c = BotController(world, tank, skill=_r.uniform(0.9, 1.3),
                          genome=genome, force_archetype=arche)
        c._spend_points(); c._maybe_upgrade_class()
        ctrl_slot[c] = slot

    orig = world.on_entity_died

    def on_died(e):
        if isinstance(e, Tank):
            vr = role_of.pop(e.id, None)
            a = e.last_attacker
            kt = a if isinstance(a, Tank) else getattr(a, "owner", None)
            kr = role_of.get(kt.id) if isinstance(kt, Tank) and kt is not e else None
            if vr and vr[0] == "cand":
                if kr and kr[0] == "ref":
                    ref_deaths.append(vr[1])
                else:
                    env_deaths.append(vr[1])
            elif vr and vr[0] == "ref" and kr and kr[0] == "cand":
                ref_kills.append(kr[1])
        orig(e)
    world.on_entity_died = on_died

    for slot in roster:
        spawn(slot)

    pending = []
    steps = int(job["sim_seconds"] / DT)
    for _ in range(steps):
        now = world.time
        for c in list(ctrl_slot):
            if c.tank.alive:
                c.update(DT)
            else:
                pending.append((now + 0.8, ctrl_slot.pop(c)))
        while pending and now >= pending[0][0]:
            spawn(pending.pop(0)[1])
        world.step(DT)

    return {"ref_kills": ref_kills, "ref_deaths": ref_deaths,
            "env_deaths": env_deaths, "steps": steps}


# ----------------------------------------------------------------- master ----
def build_shapes(arena: int) -> dict:
    scale = (arena / 9000.0) ** 2
    return {"square": int(300 * scale) + 30, "triangle": int(160 * scale) + 16,
            "pentagon": int(60 * scale) + 8, "alpha_pentagon": 2,
            "crasher_small": int(18 * scale) + 2,
            "crasher_large": int(11 * scale) + 1}


def champion_summary(pop) -> str:
    """Per-species champion fitness (kills-minus-deaths vs the baseline)."""
    parts = []
    for arche, m in pop.species_champions().items():
        parts.append(f"{arche[:3]} {pop.fitness(m):+.1f}")
    return " | ".join(parts)


def main():
    import multiprocessing as mp
    from diepgame.ai.population import Population, DEFAULT_PATH

    ap = argparse.ArgumentParser(description="Parallel evolutionary AI trainer")
    ap.add_argument("--hours", type=float, default=0.0)
    ap.add_argument("--minutes", type=float, default=0.0)
    ap.add_argument("--seconds", type=float, default=0.0)
    ap.add_argument("--workers", type=int, default=0,
                    help="parallel arenas (default: all CPU cores)")
    ap.add_argument("--per-species", type=int, default=7,
                    help="genomes per archetype (x6 species = total population)")
    ap.add_argument("--bots", type=int, default=18, help="tanks per arena")
    ap.add_argument("--arena", type=int, default=4200)
    ap.add_argument("--gen-seconds", type=float, default=90.0,
                    help="simulated seconds per arena per generation")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--path", default=str(DEFAULT_PATH))
    args = ap.parse_args()

    budget = args.hours * 3600 + args.minutes * 60 + args.seconds or 600.0
    workers = args.workers or os.cpu_count() or 1
    log_path = Path(args.path).parent / "log.csv"

    pop = None if args.fresh else Population.load(args.path)
    if pop is None:
        pop = Population.seed(args.per_species)
        print(f"seeded fresh population of {len(pop.members)} "
              f"({args.per_species}/species)")
    else:
        print(f"resumed gen {pop.generation}, {len(pop.members)} members")

    shapes = build_shapes(args.arena)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_log = not log_path.exists()
    logf = open(log_path, "a", newline="")
    writer = csv.writer(logf)
    if new_log:
        writer.writerow(["wall_s", "gen", "workers", "members", "top_elo",
                         "mean_elo", "elo_spread", "kills", "env_deaths",
                         "sim_steps_per_s"])

    print(f"training {budget/60:.1f} min on {workers} workers | "
          f"pop {len(pop.members)} | {args.bots} bots/arena | "
          f"arena {args.arena} | {args.gen_seconds}s/gen "
          f"(~{workers*args.gen_seconds:.0f} sim-s/gen)")

    t_start = time.perf_counter()
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=workers) as pool:
        try:
            while time.perf_counter() - t_start < budget:
                gen_t0 = time.perf_counter()
                gseed = random.randrange(1 << 30)
                job_base = dict(arena=args.arena, shapes=shapes, bots=args.bots,
                                sim_seconds=args.gen_seconds)
                payload = [{"id": m["id"], "genome": m["genome"],
                            "arche": m["archetype"]} for m in pop.members]
                jobs = [dict(job_base, members=payload, seed=gseed + i)
                        for i in range(workers)]
                results = pool.map(run_episode, jobs)

                rk = rd = env = total_steps = 0
                for res in results:
                    total_steps += res["steps"]
                    for gid in res["ref_kills"]:
                        pop.record_ref_kill(gid); rk += 1
                    for gid in res["ref_deaths"]:
                        pop.record_ref_death(gid); rd += 1
                    for gid in res["env_deaths"]:
                        pop.record_env_death(gid); env += 1

                gen_wall = time.perf_counter() - gen_t0
                wall = time.perf_counter() - t_start
                elo_vals = [m["elo"] for m in pop.members]
                top_elo, mean = max(elo_vals), sum(elo_vals) / len(elo_vals)
                sps = total_steps / max(1e-6, gen_wall)   # aggregate across cores
                writer.writerow([f"{wall:.0f}", pop.generation, workers,
                                 len(pop.members), f"{top_elo:.0f}",
                                 f"{mean:.0f}", f"{top_elo-min(elo_vals):.0f}",
                                 rk, rd, f"{sps:.0f}"])
                logf.flush()
                print(f"[gen {pop.generation:>3}] wall {wall:6.0f}s "
                      f"{sps:5.0f} step/s | vs-baseline {rk:4d}k/{rd:4d}d "
                      f"across {workers} arenas | {champion_summary(pop)}")
                pop.evolve()
                pop.save(args.path)
        except KeyboardInterrupt:
            print("\ninterrupted — saving...")
        finally:
            pop.save(args.path)
            logf.close()
            wall = time.perf_counter() - t_start
            print(f"done. {pop.generation} generations in {wall/60:.1f} min. "
                  f"saved -> {args.path}")
            print("FINAL " + champion_summary(pop))


if __name__ == "__main__":
    main()
