"""Data-driven tank class definitions.

Every tank is described declaratively: a list of barrels plus a handful of
modifiers. The upgrade tree mirrors the classic four-branch layout
(Twin / Sniper / Machine Gun / Flank Guard) up through tier-4 classes.

Barrel geometry units are relative to the tank's body radius:
  * length : how far the barrel extends from the center (1.0 = one radius)
  * width  : barrel thickness
  * lat    : sideways offset (perpendicular to the barrel's aim direction)
  * angle  : fixed rotation offset from the tank's aim, in degrees
  * delay  : fraction [0..1) of the reload cycle this barrel waits before
             its first shot (used to stagger multi-barrel tanks)

Per-barrel multipliers (dmg/pen/spd/size/reload/recoil/spread) scale the
tank's computed bullet stats. kind is one of "bullet", "drone", "trap",
"swarm".
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .. import config as C


@dataclass(frozen=True)
class Barrel:
    angle: float = 0.0
    lat: float = 0.0
    length: float = 1.75
    width: float = 0.42
    delay: float = 0.0
    kind: str = "bullet"
    dmg: float = 1.0
    pen: float = 1.0
    spd: float = 1.0
    size: float = 1.0       # bullet radius relative to barrel width
    reload: float = 1.0     # per-barrel reload multiplier
    recoil: float = 1.0
    spread: float = 2.0     # random aim error, degrees
    trapezoid: bool = False # drawn as a trapezoid (drone spawners / mg)
    auto_fire: bool = False # fires regardless of input (hybrid drones etc.)


@dataclass(frozen=True)
class TankDef:
    name: str
    tier: int
    barrels: tuple
    upgrades_to: tuple = ()
    fov: float = 1.0
    speed_mult: float = 1.0
    body_damage_mult: float = 1.0
    max_health_mult: float = 1.0
    max_drones: int = 0
    invisible_when_idle: bool = False
    body_shape: str = "circle"     # circle | smasher | spike | square
    necro: bool = False            # raises killed squares as drones
    notes: str = ""


T: dict[str, TankDef] = {}


def _add(key, **kw):
    T[key] = TankDef(**kw)


# ---------------------------------------------------------------- tier 1 ----
_add("basic", name="Basic Tank", tier=1,
     barrels=(Barrel(),),
     upgrades_to=("twin", "sniper", "machine_gun", "flank_guard"))

# ---------------------------------------------------------------- tier 2 ----
_add("twin", name="Twin", tier=2,
     barrels=(Barrel(lat=-0.42, dmg=0.7, reload=1.0),
              Barrel(lat=0.42, delay=0.5, dmg=0.7)),
     upgrades_to=("triple_shot", "quad_tank", "twin_flank"))

_add("sniper", name="Sniper", tier=2, fov=1.28,
     barrels=(Barrel(length=2.0, width=0.40, reload=1.9, spd=1.5,
                     dmg=1.35, pen=1.1, spread=0.4, recoil=1.4),),
     upgrades_to=("assassin", "overseer", "hunter", "trapper"))

_add("machine_gun", name="Machine Gun", tier=2,
     barrels=(Barrel(length=1.65, width=0.55, reload=0.55, dmg=0.8,
                     pen=0.85, spread=11, trapezoid=True),),
     upgrades_to=("destroyer", "gunner", "sprayer"))

_add("flank_guard", name="Flank Guard", tier=2,
     barrels=(Barrel(),
              Barrel(angle=180, length=1.55)),
     upgrades_to=("tri_angle", "quad_tank", "twin_flank", "smasher"))

# ---------------------------------------------------------------- tier 3 ----
_add("triple_shot", name="Triple Shot", tier=3,
     barrels=(Barrel(angle=-26, length=1.62, dmg=0.85),
              Barrel(angle=26, length=1.62, dmg=0.85),
              Barrel(length=1.75, dmg=0.85)),
     upgrades_to=("triplet", "penta_shot", "spread_shot"))

_add("quad_tank", name="Quad Tank", tier=3,
     barrels=tuple(Barrel(angle=a, dmg=0.85) for a in (0, 90, 180, 270)),
     upgrades_to=("octo_tank",))

_add("twin_flank", name="Twin Flank", tier=3,
     barrels=(Barrel(lat=-0.42, dmg=0.7), Barrel(lat=0.42, delay=0.5, dmg=0.7),
              Barrel(angle=180, lat=-0.42, delay=0.5, dmg=0.7),
              Barrel(angle=180, lat=0.42, dmg=0.7)),
     upgrades_to=("triple_twin", "battleship"))

_add("assassin", name="Assassin", tier=3, fov=1.45,
     barrels=(Barrel(length=2.2, width=0.38, reload=2.3, spd=1.75,
                     dmg=1.65, pen=1.2, spread=0.25, recoil=1.7),),
     upgrades_to=("ranger", "stalker"))

_add("overseer", name="Overseer", tier=3, fov=1.12, max_drones=8,
     barrels=(Barrel(angle=90, length=1.15, width=0.62, kind="drone",
                     reload=5.5, trapezoid=True),
              Barrel(angle=-90, length=1.15, width=0.62, kind="drone",
                     reload=5.5, delay=0.5, trapezoid=True)),
     upgrades_to=("overlord", "necromancer", "manager", "battleship",
                  "overtrapper"))

_add("hunter", name="Hunter", tier=3, fov=1.22,
     barrels=(Barrel(length=2.05, width=0.36, reload=2.1, spd=1.5, dmg=0.95,
                     pen=1.05, spread=0.6),
              Barrel(length=1.8, width=0.52, reload=2.1, delay=0.12, spd=1.5,
                     dmg=1.0, pen=1.05, size=1.0, spread=0.6)),
     upgrades_to=("predator", "streamliner"))

_add("trapper", name="Trapper", tier=3, fov=1.08,
     barrels=(Barrel(length=1.15, width=0.5, kind="trap", reload=1.6,
                     dmg=1.1, pen=2.2, spd=1.0, size=1.25, trapezoid=True),),
     upgrades_to=("tri_trapper", "mega_trapper", "overtrapper",
                  "gunner_trapper"))

_add("destroyer", name="Destroyer", tier=3,
     barrels=(Barrel(length=1.75, width=0.82, reload=4.2, dmg=3.0, pen=3.2,
                     spd=0.72, recoil=9.0, spread=1.0),),
     upgrades_to=("annihilator", "hybrid"))

_add("gunner", name="Gunner", tier=3,
     barrels=(Barrel(lat=-0.62, length=1.45, width=0.22, delay=0.0, dmg=0.52,
                     pen=0.6, reload=1.05, size=1.0),
              Barrel(lat=0.62, length=1.45, width=0.22, delay=0.5, dmg=0.52,
                     pen=0.6, reload=1.05),
              Barrel(lat=-0.21, length=1.7, width=0.22, delay=0.25, dmg=0.52,
                     pen=0.6, reload=1.05),
              Barrel(lat=0.21, length=1.7, width=0.22, delay=0.75, dmg=0.52,
                     pen=0.6, reload=1.05)),
     upgrades_to=("gunner_trapper", "streamliner"))

_add("tri_angle", name="Tri-Angle", tier=3, speed_mult=1.08,
     barrels=(Barrel(),
              Barrel(angle=150, length=1.5, dmg=0.4, pen=0.4, reload=0.9,
                     recoil=2.6),
              Barrel(angle=210, length=1.5, dmg=0.4, pen=0.4, reload=0.9,
                     recoil=2.6)),
     upgrades_to=("booster", "fighter"))

_add("smasher", name="Smasher", tier=3, body_shape="smasher",
     barrels=(), speed_mult=1.12, body_damage_mult=1.5, max_health_mult=1.15,
     fov=0.95,
     upgrades_to=("spike", "landmine"))

# ---------------------------------------------------------------- tier 4 ----
_add("sprayer", name="Sprayer", tier=4,
     barrels=(Barrel(length=1.9, width=0.34, reload=0.62, dmg=0.5, pen=0.6,
                     spread=3.0),
              Barrel(length=1.6, width=0.58, reload=0.62, delay=0.5, dmg=0.6,
                     pen=0.7, spread=12, trapezoid=True)))

_add("triplet", name="Triplet", tier=4,
     barrels=(Barrel(lat=-0.5, length=1.6, dmg=0.62),
              Barrel(lat=0.5, length=1.6, dmg=0.62),
              Barrel(length=1.78, delay=0.5, dmg=0.62)))

_add("penta_shot", name="Penta Shot", tier=4,
     barrels=(Barrel(angle=-46, length=1.5, delay=0.0, dmg=0.72),
              Barrel(angle=46, length=1.5, delay=0.0, dmg=0.72),
              Barrel(angle=-23, length=1.65, delay=0.33, dmg=0.72),
              Barrel(angle=23, length=1.65, delay=0.33, dmg=0.72),
              Barrel(length=1.8, delay=0.66, dmg=0.72)))

_add("spread_shot", name="Spread Shot", tier=4,
     barrels=tuple(
         [Barrel(angle=a, length=1.3 + 0.05 * (5 - abs(i - 5)),
                 width=0.26, dmg=0.5, pen=0.5, delay=(abs(i - 5)) * 0.09,
                 reload=1.4)
          for i, a in enumerate((-75, -60, -45, -30, -15, 999, 15, 30, 45,
                                 60, 75)) if a != 999]
         + [Barrel(length=1.8, dmg=0.95)]))

_add("octo_tank", name="Octo Tank", tier=4,
     barrels=tuple(Barrel(angle=a, dmg=0.7,
                          delay=(0.0 if (a // 45) % 2 == 0 else 0.5))
                   for a in range(0, 360, 45)))

_add("triple_twin", name="Triple Twin", tier=4,
     barrels=tuple(
         Barrel(angle=a, lat=l, delay=d, dmg=0.72)
         for a in (0, 120, 240)
         for l, d in ((-0.42, 0.0), (0.42, 0.5))))

_add("battleship", name="Battleship", tier=4, max_drones=16,
     barrels=tuple(
         Barrel(angle=a, lat=l, length=1.1, width=0.3, kind="swarm",
                reload=1.5, delay=d, trapezoid=True, dmg=0.4, pen=0.35,
                auto_fire=True)
         for (a, l, d) in ((90, -0.32, 0.0), (90, 0.32, 0.5),
                           (-90, -0.32, 0.5), (-90, 0.32, 0.0))))

_add("ranger", name="Ranger", tier=4, fov=1.7,
     barrels=(Barrel(length=2.35, width=0.36, reload=2.5, spd=2.05, dmg=1.9,
                     pen=1.3, spread=0.15, recoil=2.0, trapezoid=False),))

_add("stalker", name="Stalker", tier=4, fov=1.45, invisible_when_idle=True,
     barrels=(Barrel(length=2.2, width=0.38, reload=2.3, spd=1.8, dmg=1.55,
                     pen=1.2, spread=0.25, recoil=1.7, trapezoid=True),))

_add("overlord", name="Overlord", tier=4, fov=1.12, max_drones=8,
     barrels=tuple(Barrel(angle=a, length=1.15, width=0.62, kind="drone",
                          reload=3.4, delay=i * 0.25, trapezoid=True)
                   for i, a in enumerate((0, 90, 180, 270))))

_add("manager", name="Manager", tier=4, fov=1.18, max_drones=8,
     invisible_when_idle=True,
     barrels=(Barrel(length=1.15, width=0.62, kind="drone", reload=2.8,
                     trapezoid=True),))

_add("necromancer", name="Necromancer", tier=4, fov=1.15, max_drones=12,
     body_shape="square", necro=True, speed_mult=0.95,
     barrels=(Barrel(angle=90, length=1.1, width=0.6, kind="drone",
                     reload=6.0, dmg=0.6, trapezoid=True),
              Barrel(angle=-90, length=1.1, width=0.6, kind="drone",
                     reload=6.0, delay=0.5, dmg=0.6, trapezoid=True)),
     notes="slowly births squares; killed squares rise as drones too")

_add("predator", name="Predator", tier=4, fov=1.35,
     barrels=(Barrel(length=2.15, width=0.34, reload=2.6, spd=1.55, dmg=1.0,
                     pen=1.1, spread=0.5),
              Barrel(length=1.9, width=0.5, reload=2.6, delay=0.12, spd=1.55,
                     dmg=1.05, pen=1.1, spread=0.5),
              Barrel(length=1.65, width=0.66, reload=2.6, delay=0.24,
                     spd=1.55, dmg=1.1, pen=1.1, spread=0.5)))

_add("streamliner", name="Streamliner", tier=4, fov=1.18,
     barrels=tuple(Barrel(length=2.1 - i * 0.12, width=0.36, reload=0.44,
                          delay=i * 0.2, dmg=0.2, pen=0.4, spd=1.6,
                          spread=1.2)
                   for i in range(5)))

_add("annihilator", name="Annihilator", tier=4,
     barrels=(Barrel(length=1.8, width=0.96, reload=4.6, dmg=3.6, pen=3.8,
                     spd=0.7, recoil=12.0, spread=1.0),))

_add("hybrid", name="Hybrid", tier=4, max_drones=2,
     barrels=(Barrel(length=1.75, width=0.82, reload=4.2, dmg=3.0, pen=3.2,
                     spd=0.72, recoil=9.0, spread=1.0),
              Barrel(angle=180, length=1.1, width=0.6, kind="drone",
                     reload=4.0, trapezoid=True, auto_fire=True)))

_add("booster", name="Booster", tier=4, speed_mult=1.14,
     barrels=(Barrel(),
              Barrel(angle=150, length=1.45, dmg=0.35, pen=0.35, reload=0.8,
                     recoil=2.6),
              Barrel(angle=210, length=1.45, dmg=0.35, pen=0.35, reload=0.8,
                     recoil=2.6),
              Barrel(angle=165, length=1.3, dmg=0.35, pen=0.35, reload=0.8,
                     delay=0.5, recoil=2.6),
              Barrel(angle=195, length=1.3, dmg=0.35, pen=0.35, reload=0.8,
                     delay=0.5, recoil=2.6)))

_add("fighter", name="Fighter", tier=4, speed_mult=1.1,
     barrels=(Barrel(),
              Barrel(angle=90, length=1.55, dmg=0.7),
              Barrel(angle=270, length=1.55, dmg=0.7),
              Barrel(angle=150, length=1.45, dmg=0.35, pen=0.35, reload=0.85,
                     recoil=2.4),
              Barrel(angle=210, length=1.45, dmg=0.35, pen=0.35, reload=0.85,
                     recoil=2.4)))

_add("tri_trapper", name="Tri-Trapper", tier=4, fov=1.08,
     barrels=tuple(Barrel(angle=a, length=1.15, width=0.5, kind="trap",
                          reload=1.9, dmg=1.0, pen=2.0, size=1.25,
                          trapezoid=True)
                   for a in (0, 120, 240)))

_add("mega_trapper", name="Mega Trapper", tier=4, fov=1.08,
     barrels=(Barrel(length=1.2, width=0.72, kind="trap", reload=2.6,
                     dmg=1.7, pen=3.4, size=1.3, trapezoid=True),))

_add("overtrapper", name="Overtrapper", tier=4, fov=1.1, max_drones=4,
     barrels=(Barrel(length=1.15, width=0.5, kind="trap", reload=1.7,
                     dmg=1.1, pen=2.2, size=1.25, trapezoid=True),
              Barrel(angle=150, length=1.05, width=0.55, kind="drone",
                     reload=4.5, trapezoid=True, auto_fire=True),
              Barrel(angle=210, length=1.05, width=0.55, kind="drone",
                     reload=4.5, delay=0.5, trapezoid=True, auto_fire=True)))

_add("gunner_trapper", name="Gunner Trapper", tier=4,
     barrels=(Barrel(lat=-0.3, length=1.6, width=0.24, dmg=0.55, pen=0.6,
                     reload=1.0),
              Barrel(lat=0.3, length=1.6, width=0.24, delay=0.5, dmg=0.55,
                     pen=0.6, reload=1.0),
              Barrel(angle=180, length=1.1, width=0.6, kind="trap",
                     reload=2.0, dmg=1.2, pen=2.4, size=1.2, trapezoid=True)))

_add("spike", name="Spike", tier=4, body_shape="spike",
     barrels=(), speed_mult=1.05, body_damage_mult=2.1, max_health_mult=1.2,
     fov=0.95)

_add("landmine", name="Landmine", tier=4, body_shape="smasher",
     barrels=(), speed_mult=1.12, body_damage_mult=1.6, max_health_mult=1.2,
     fov=0.95, invisible_when_idle=True)

TANK_DEFS = T


def available_upgrades(def_key: str, level: int) -> list[str]:
    """Class keys a tank of `def_key` may upgrade into at `level`.

    Pure function shared by the Tank entity (server side) and the network
    client (which has no live Tank objects, only def_key + level)."""
    out = []
    for key in TANK_DEFS[def_key].upgrades_to:
        need = C.CLASS_UPGRADE_LEVELS[min(TANK_DEFS[key].tier - 2, 2)]
        if level >= need:
            out.append(key)
    return out
