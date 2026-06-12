# Polygon Arena: offline tank trainer

A fully offline, single-player tank-arena game inspired by diep.io. You fight
in a 6000x6000 arena against AI bots, farm polygons for XP, allocate 8 stat
lines, and climb a 38-class upgrade tree (Twin / Sniper / Machine Gun / Flank
Guard branches up through tier-4 classes like Overlord, Annihilator, Booster,
Ranger, Octo Tank and more).

Everything (code, art, balance numbers) is original and generated procedurally
with `pygame`. No internet connection is ever needed.

---

## 1. Requirements

* Python **3.10+**
* [`uv`](https://docs.astral.sh/uv/) for environment + package management
* Any OS with SDL support (Windows / macOS / Linux)

Install `uv` if you don't have it:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## 2. Setup

```bash
cd diep-trainer        # the folder containing pyproject.toml
uv sync                # creates .venv and installs pygame-ce
```

That's it. `uv sync` reads `pyproject.toml`, creates an isolated virtual
environment in `.venv/`, and installs the single dependency (`pygame-ce`).

## 3. Run the game

```bash
uv run diep
```

Options:

```bash
uv run diep --name "Ace"          # your in-game name
uv run diep --bots 12             # number of AI opponents (default 8)
uv run diep --window 1600x900     # window size (default 1280x720)
uv run diep --difficulty hard     # bot AI: easy / normal / hard
```

Equivalent: `uv run python -m diepgame`.

## 4. Verify the install (headless smoke test)

```bash
uv run python tests/smoke_test.py
```

This simulates 30 seconds of bot-vs-bot play with no window, instantiates
every tank class, and checks leveling/upgrades/projectiles all work.

---

## 5. Controls

| Input | Action |
|---|---|
| `WASD` / arrows | Move |
| Mouse | Aim |
| Left click / `Space` | Fire (or command drones to attack the cursor) |
| Right click / `Shift` | Repel drones |
| `1`–`8` | Spend skill points on the matching stat |
| `F1`–`F6` or click | Choose a class upgrade when offered |
| `E` | Toggle auto-fire |
| `C` | Toggle auto-spin |
| `P` | Pause |
| `Enter` | Respawn after death |
| `Esc` | Quit |

## 6. Gameplay summary

* **Shapes**: squares (10 XP), triangles (25), pentagons (130), alpha
  pentagons (3000). Pink **crashers** in the central pentagon nest chase you.
* **Leveling**: cap is level 45; you earn 33 skill points across 8 stats
  (Health Regen, Max Health, Body Damage, Bullet Speed, Bullet Penetration,
  Bullet Damage, Reload, Movement Speed, max 7 points each).
* **Class upgrades** unlock at levels **15 / 30 / 45**.
* **Killing a tank** grants half its score. Dying shows your run stats;
  you can respawn with `Enter`. Bots respawn at a level that keeps pace
  with the arena leader (tunable via `--difficulty`).
* **Bots** dodge bullets, lead their shots, finish wounded enemies, keep
  class-appropriate range, screen retreats with drones, and hold huge
  Destroyer shells until you are in range.
* Special mechanics included: drone control (Overseer line), traps
  (Trapper line), recoil propulsion (Tri-Angle/Booster/Fighter), invisibility
  (Stalker, Manager, Landmine), rammer bodies (Smasher, Spike), huge-shell
  knockback (Destroyer line), and per-class field-of-view zoom.

### Class tree implemented

```
Basic
├─ Twin ──────── Triple Shot ── Triplet | Penta Shot | Spread Shot
│                Quad Tank ──── Octo Tank
│                Twin Flank ─── Triple Twin | Battleship
├─ Sniper ────── Assassin ───── Ranger | Stalker
│                Overseer ───── Overlord | Manager | Battleship | Overtrapper
│                Hunter ─────── Predator | Streamliner
│                Trapper ────── Tri-Trapper | Mega Trapper | Overtrapper | Gunner Trapper
├─ Machine Gun ─ Destroyer ──── Annihilator | Hybrid
│                Gunner ─────── Gunner Trapper | Streamliner
│                Sprayer
└─ Flank Guard ─ Tri-Angle ──── Booster | Fighter
                 Quad Tank / Twin Flank (shared)
                 Smasher ────── Spike | Landmine
```

## 7. Codebase layout

```
diep-trainer/
├── pyproject.toml              # uv/pip metadata, deps, `diep` script
├── README.md
├── tests/
│   └── smoke_test.py           # headless 30s simulation + class checks
└── src/diepgame/
    ├── config.py               # every balance constant in one place
    ├── main.py / __main__.py   # CLI entry point
    ├── game.py                 # pygame loop, input, camera glue
    ├── core/
    │   ├── vector.py           # Vec2 math
    │   └── camera.py           # smooth follow + FOV zoom
    ├── entities/
    │   ├── base.py             # Entity: hp, knockback, regen
    │   ├── shapes.py           # polygons & crashers
    │   ├── projectiles.py      # Bullet / Trap / Drone
    │   └── tank.py             # stats, leveling, firing, upgrades
    ├── tanks/
    │   └── definitions.py      # the entire class tree, data-driven
    ├── ai/
    │   └── bot.py              # bot brains + respawn manager
    ├── systems/
    │   ├── spatial.py          # spatial hash broad-phase
    │   ├── collision.py        # contact damage + separation
    │   └── world.py            # entity registry, spawner, scoring
    └── ui/
        ├── renderer.py         # procedural drawing of everything
        └── hud.py              # stat panel, upgrades, minimap, leaderboard
```

## 8. Tuning & modding

* All balance lives in `src/diepgame/config.py` (XP curve, stat scaling,
  reload, bullet formulas, shape counts, bot count).
* Add or tweak tank classes in `src/diepgame/tanks/definitions.py`. They are
  plain data. Add a `_add("my_tank", ...)` entry, list it in some tank's
  `upgrades_to`, and it's playable immediately.
* Bot builds/personalities are in `src/diepgame/ai/bot.py` (`BUILDS`,
  `ARCHETYPE`, `CLASS_WEIGHTS`); fierceness knobs (aggression, dodging,
  respawn catch-up, player focus) live in `config.py` as the
  `DIFFICULTY_PRESETS`.
* Benchmark AI changes with `uv run python tests/ai_bench.py` (bot-vs-bot
  arena stats, a bullet-dodging probe, and a player-pressure probe).

## 9. Troubleshooting

* **Black/blank window on Linux**: ensure SDL can reach your display
  (`echo $DISPLAY`), or try `SDL_VIDEODRIVER=x11 uv run diep`.
* **`uv: command not found`**: reopen your shell after installing uv, or add
  `~/.local/bin` to `PATH`.
* **Low FPS**: shrink the window (`--window 960x540`) or lower
  `SHAPE_TARGETS` in `config.py`.
