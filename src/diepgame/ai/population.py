"""Speciated, evolving population with fitness measured against a fixed baseline.

Two design choices keep training honest (so the AI reliably gets *better*, never
worse, and stays diverse):

1. **Speciation by archetype** (bullet / sniper / drone / trap / body / drift):
   culling and breeding happen *within* each species, so no single strategy
   takes over and every playstyle keeps improving.

2. **Fitness vs a fixed baseline, with elitism.** Every training arena also
   fields immortal "reference" bots running the hand-tuned `DEFAULT_GENOME`. A
   genome's fitness is how it does *against those references* (kills minus
   deaths), not a self-referential ELO that can drift/inflate. Each species
   keeps an immortal copy of the default genome, so its champion is by
   construction never worse than the baseline.

ELO is still tracked for flavor/naming, but **selection uses fitness**.

member = {id, name, archetype, genome, elo, fit_k, fit_d, kills, deaths,
          games, gen, immortal}
"""
from __future__ import annotations
import json
import random
from pathlib import Path

from .genome import Genome
from .bot import SPECIES

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "training" / "population.json"
START_ELO = 1200.0
K_FACTOR = 24.0
FIT_DECAY = 0.55                 # how fast old fitness samples fade each gen
ENV_DEATH_FIT = 0.5             # fitness penalty for dying to the arena


def expected(ra, rb):
    return 1.0 / (1.0 + 10.0 ** ((rb - ra) / 400.0))


class Population:
    def __init__(self, members, generation=0):
        self.members = members
        self.generation = generation
        self._reindex()

    def _reindex(self):
        self._by_id = {m["id"]: m for m in self.members}
        self._next_id = max((m["id"] for m in self.members), default=0) + 1

    # ----------------------------------------------------------- factories
    @classmethod
    def seed(cls, per_species: int = 7):
        members, mid = [], 1
        for arche in SPECIES:
            # slot 0 is the immortal baseline; the rest explore
            members.append(cls._new(mid, Genome.default(), arche, immortal=True))
            mid += 1
            for _ in range(per_species - 1):
                members.append(cls._new(mid, Genome.random(), arche))
                mid += 1
        return cls(members)

    @staticmethod
    def _new(mid, genome, archetype, elo=START_ELO, gen=0, immortal=False):
        return {"id": mid, "name": f"g{mid}", "archetype": archetype,
                "genome": genome.to_dict(), "elo": elo, "fit_k": 0.0,
                "fit_d": 0.0, "kills": 0, "deaths": 0, "games": 0, "gen": gen,
                "immortal": immortal}

    # --------------------------------------------------------------- io
    @classmethod
    def load(cls, path=DEFAULT_PATH):
        path = Path(path)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        members = data["members"]
        if not members or "fit_k" not in members[0]:
            return None             # old format: reseed
        return cls(members, data.get("generation", 0))

    def save(self, path=DEFAULT_PATH):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(
            {"generation": self.generation, "members": self.members}))
        tmp.replace(path)

    # --------------------------------------------------------------- access
    def get(self, mid):
        return self._by_id.get(mid)

    @staticmethod
    def fitness(m) -> float:
        return m["fit_k"] - m["fit_d"]

    def ranked(self):
        return sorted(self.members, key=self.fitness, reverse=True)

    def species(self, arche):
        return [m for m in self.members if m["archetype"] == arche]

    # an evolved genome must clear the default's fitness by this margin AND have
    # played enough games before it's trusted (guards against noisy/overfit
    # flukes). The default is already a strong, fierce brain, so the live game
    # only swaps in an evolved genome that has *proven* it clearly beats it.
    WIN_MARGIN = 2.0
    MIN_TRUST_GAMES = 12

    def _default(self, arche):
        return next((m for m in self.species(arche) if m["immortal"]), None)

    def _proven(self, grp):
        return [m for m in grp
                if m["immortal"] or m["games"] >= self.MIN_TRUST_GAMES]

    def species_best(self, arche):
        """Best *proven* genome that robustly beats the baseline, else baseline."""
        grp = self.species(arche)
        if not grp:
            return None
        default = self._default(arche)
        best = max(self._proven(grp) or grp, key=self.fitness)
        if default is None:
            return best
        return best if self.fitness(best) > self.fitness(default) + self.WIN_MARGIN \
            else default

    def species_champions(self):
        return {a: self.species_best(a) for a in SPECIES if self.species(a)}

    def field(self, n):
        """n members spread across species, biased to under-played (training)."""
        out = []
        for _ in range(n):
            grp = sorted(self.species(random.choice(SPECIES)) or self.members,
                         key=lambda m: m["games"])
            out.append(random.choice(grp[:max(1, len(grp) // 2)]))
        return out

    def sample(self):
        """One member for the live game. Never field a genome worse than the
        species baseline, so live bots are always >= the hand-tuned default;
        bias toward fitter ones but keep diversity."""
        arche = random.choice(SPECIES)
        grp = self.species(arche) or self.members
        default = self._default(arche)
        floor = self.fitness(default) if default else -1e9
        pool = [m for m in self._proven(grp) if self.fitness(m) >= floor]
        pool = sorted(pool or [default] if default else grp,
                      key=self.fitness, reverse=True)
        return random.choice(pool[:max(1, len(pool) * 2 // 3)])

    # --------------------------------------------------------------- scoring
    # ELO is rated against the fixed baseline (START_ELO): a candidate above
    # 1200 genuinely beats the hand-tuned default; below means worse.
    def record_ref_kill(self, gid):          # candidate killed a baseline bot
        m = self.get(gid)
        if m:
            m["fit_k"] += 1.0
            m["kills"] += 1
            m["games"] += 1
            m["elo"] += K_FACTOR * (1.0 - expected(m["elo"], START_ELO))

    def record_ref_death(self, gid):         # candidate died to a baseline bot
        m = self.get(gid)
        if m:
            m["fit_d"] += 1.0
            m["deaths"] += 1
            m["games"] += 1
            m["elo"] += K_FACTOR * (0.0 - expected(m["elo"], START_ELO))

    def record_env_death(self, gid):
        m = self.get(gid)
        if m:
            m["fit_d"] += ENV_DEATH_FIT
            m["deaths"] += 1

    # --------------------------------------------------------------- evolve
    def evolve(self, cull_frac=0.30):
        self.generation += 1
        for m in self.members:                # fade old fitness samples
            m["fit_k"] *= FIT_DECAY
            m["fit_d"] *= FIT_DECAY
        new_members = []
        for arche in SPECIES:
            grp = sorted(self.species(arche), key=self.fitness, reverse=True)
            if not grp:
                continue
            immortals = [m for m in grp if m["immortal"]]
            mortal = [m for m in grp if not m["immortal"]]
            n_cull = max(1, int(len(mortal) * cull_frac)) if len(mortal) >= 4 else 0
            survivors = mortal[:len(mortal) - n_cull] if n_cull else mortal
            elites = grp[:max(2, len(grp) // 2)]      # best may be immortal
            for _ in range(n_cull):
                a, b = (random.sample(elites, 2) if len(elites) >= 2
                        else (elites[0], elites[0]))
                cg = Genome.crossover(Genome.from_dict(a["genome"]),
                                      Genome.from_dict(b["genome"])).mutate()
                survivors.append(self._new(self._next_id, cg, arche,
                                           gen=self.generation))
                self._next_id += 1
            new_members.extend(immortals + survivors)
        self.members = new_members
        self._reindex()
