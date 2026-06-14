"""Bot 'genome': the tunable personality vector the evolutionary trainer
optimizes. Each gene is a float in a fixed range; the defaults reproduce a
sensible, multi-threat-aware baseline so untrained bots already play well.

The genome is read by ``BotController`` (see bot.py). Evolution lives in
``population.py`` / ``tools/train.py``.
"""
from __future__ import annotations
import random
from dataclasses import dataclass

# gene -> (low, high, default).  Defaults = hand-tuned improved baseline.
GENES: dict[str, tuple[float, float, float]] = {
    "aggression":   (0.40, 1.90, 1.00),   # engage range / courage
    "caution":      (0.40, 1.80, 1.00),   # higher = flee at higher hp
    "dodge":        (0.20, 2.40, 1.20),   # weight of bullet-dodge steering
    "focus":        (0.50, 2.20, 1.20),   # target stickiness / commitment
    "wounded":      (1.00, 2.60, 1.70),   # bonus for finishing low-hp enemies
    "threat_avoid": (0.00, 2.40, 0.65),   # flee the *centroid* when swarmed (3+)
    "outnumber":    (2.00, 5.00, 3.00),   # enemy count that triggers disengage
    "spacing":      (0.00, 2.00, 0.65),   # keep distance from nearest threat
    "strafe":       (0.20, 1.60, 0.90),   # orbit amplitude while fighting
    "range_bias":   (0.70, 1.45, 1.00),   # multiplies ideal engagement range
    "nest_greed":   (0.50, 2.00, 1.20),   # farm pentagons vs hunt tanks
    "accuracy":     (0.00, 1.00, 0.60),   # higher = less aim jitter (capped)
    "regen_kite":   (0.00, 1.60, 0.80),   # back off to heal when hurt
    "discipline":   (0.60, 1.50, 1.00),   # hold big shells until in range
    "pref_bullet":  (0.20, 2.50, 1.00),   # class-pick weights by archetype
    "pref_sniper":  (0.20, 2.50, 1.00),
    "pref_drone":   (0.20, 2.50, 1.00),
    "pref_body":    (0.20, 2.50, 1.00),
}


@dataclass
class Genome:
    genes: dict

    # ------------------------------------------------------------- factories
    @classmethod
    def default(cls) -> "Genome":
        return cls({k: v[2] for k, v in GENES.items()})

    @classmethod
    def random(cls) -> "Genome":
        return cls({k: random.uniform(lo, hi) for k, (lo, hi, _) in GENES.items()})

    @classmethod
    def from_dict(cls, d: dict) -> "Genome":
        g = {k: float(d.get(k, default)) for k, (_, _, default) in GENES.items()}
        return cls(g)

    def to_dict(self) -> dict:
        return dict(self.genes)

    # --------------------------------------------------------------- access
    def __getitem__(self, key: str) -> float:
        return self.genes[key]

    def get(self, key: str, default: float = 0.0) -> float:
        return self.genes.get(key, default)

    # ------------------------------------------------------------- evolution
    def clamped(self) -> "Genome":
        for k, (lo, hi, _) in GENES.items():
            self.genes[k] = max(lo, min(hi, self.genes[k]))
        return self

    def mutate(self, rate: float = 0.35, scale: float = 0.18) -> "Genome":
        """Gaussian perturbation of a random subset of genes (in-place copy)."""
        child = {k: v for k, v in self.genes.items()}
        for k, (lo, hi, _) in GENES.items():
            if random.random() < rate:
                child[k] += random.gauss(0.0, scale) * (hi - lo)
        return Genome(child).clamped()

    @staticmethod
    def crossover(a: "Genome", b: "Genome") -> "Genome":
        """Per-gene blend/pick of two parents."""
        child = {}
        for k in GENES:
            if random.random() < 0.5:
                child[k] = a.genes[k]
            else:
                child[k] = b.genes[k]
            if random.random() < 0.5:                 # occasional blend
                child[k] = 0.5 * (a.genes[k] + b.genes[k])
        return Genome(child).clamped()


DEFAULT_GENOME = Genome.default()
