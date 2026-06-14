# CLAUDE.md

Guidance for working in this repo. Read this first; it captures the parts that
aren't obvious from a quick skim.

## What this is

**Polygon Arena** — an offline + LAN tank-arena game (diep.io-style) in Python
with `pygame-ce`. Single dependency, fully procedural art, original balance.
You farm polygons for XP, allocate 8 stats, and climb a 40-class upgrade tree
while fighting AI bots (and, in LAN mode, friends). Package name: `diepgame`.

## Environment & commands

Uses `uv` (not pip/venv directly). Python 3.10+.

```bash
uv sync                                   # install deps into .venv
uv run diep                               # play solo (or: uv run python -m diepgame)
uv run diep --difficulty hard --bots 20   # tuning knobs
uv run diep --class overlord --level 45   # practice mode: jump into a build
uv run diep --host --mode team            # host LAN game
uv run diep --join 192.168.1.42:8765      # join a LAN game
```

Tests are **plain scripts run with `uv run python`**, not pytest. They run
headless via the SDL dummy driver (set inside each test), so no window opens:

```bash
uv run python tests/smoke_test.py     # 30s bot sim, instantiates every class
uv run python tests/net_test.py       # LAN host+client over a loopback socket
uv run python tests/ai_bench.py       # bot AI: arena / dodge / pressure probes
uv run python tests/balance_audit.py  # per-class DPS / range / TTK tables
```

Always run `smoke_test.py` after touching simulation/entities, and
`net_test.py` after touching anything under `net/`.

## Architecture

The simulation is **headless and deterministic-ish**; rendering/input are a
thin layer on top. This separation is what makes bots, the smoke test, and LAN
all reuse the same core.

- `World.step(dt)` is the authoritative simulation tick: updates entities,
  rebuilds the spatial hash, resolves collisions, culls dead, maintains shape
  counts, ages effects/kill-feed, spawns the boss.
- A `Tank` is driven by either local input (`Game`), a `BotController`
  (`ai/bot.py`), or a remote client's input (`net/server.py`). **A remote
  player is just a Tank whose input arrives over the network** — bots, boss,
  classes, scoring all work in multiplayer for free.
- Three run modes share `World`:
  - **solo** — `game.Game` owns world + bots + local player.
  - **host** — `Game(mode=...)` plus a `net.server.GameServer` wrapping the
    same world; the game loop calls `server.pump()` before the step and
    `server.publish()` after.
  - **join** — `net.clientgame.ClientGame`; owns no world, renders interpolated
    snapshots from the host through the *same* `Renderer`/`Hud`.

### Key files

| File | Role |
|---|---|
| `config.py` | **All balance + tuning constants.** XP curve, stat scaling, bullet/recoil formulas, shape counts, bot/difficulty presets, team ids, net ports. Start here for any number change. |
| `entities/base.py` | `Entity`: pos/vel/hp, knockback, regen, arena clamp. |
| `entities/tank.py` | Stats, leveling, reload cycles, firing, recoil boost, drones, class upgrades, spawn shield. |
| `entities/projectiles.py` | `Bullet` / `Trap` / `Drone` (+ per-pair hit gate). |
| `entities/shapes.py` | Polygons, crashers, shiny variants, `Guardian` boss. |
| `tanks/definitions.py` | **Data-driven class tree.** Every tank = barrels + modifiers. `available_upgrades()` helper lives here (shared by Tank + client). |
| `ai/bot.py` | Bot brain (FARM/ATTACK/FLEE, dodging, leading, class tactics) + `BotManager` respawns. `BUILDS`/`ARCHETYPE`/`CLASS_WEIGHTS`. |
| `systems/world.py` | Entity registry, spawner, scoring, boss schedule, team helpers, death effects. |
| `systems/collision.py` | Contact damage rules (see "discrete hit model"). |
| `ui/renderer.py` | Procedural drawing of everything; `draw_tank_icon` for HUD previews. |
| `ui/hud.py` | Stat panel, class buttons, bars, leaderboard, minimap, kill feed, death screen. |
| `net/protocol.py` | Framed JSON + `build_snapshot` / `apply_input`. |
| `net/server.py` | Authoritative `GameServer` + per-client `Session`; asyncio I/O on a background thread. |
| `net/client.py` | `NetClient`: connect, send input, buffer + interpolate snapshots. |
| `net/clientgame.py` | Client render loop + lightweight view shims (`SnapEntity`/`SnapTank`/`ClientWorld`). |
| `net/lan.py` | LAN IP detection + HTTP invite page. |

## Conventions & gotchas

- **Balance lives in `config.py`.** Don't scatter magic numbers; route through
  it. Tank shapes are pure data in `definitions.py` — add `_add("key", ...)`,
  list it in another tank's `upgrades_to`, and it's playable.
- **Discrete hit model** (`collision.py`): a projectile deals damage **once per
  contact**, then that bullet+victim pair is on a `HIT_COOLDOWN` (~0.25s) via a
  per-bullet `hit_gate` dict. This is frame-rate independent and makes
  penetration meaningful. Body-vs-body contact is still continuous (dt-scaled).
  Don't "fix" this back into per-frame damage.
- **Recoil is its own velocity channel** (`tank.boost_vel`), *not* added to
  `vel`, so rear-barrel fire (Tri-Angle/Booster/Fighter) genuinely accelerates
  past the move-speed cap and Destroyer shells kick hard. See
  `RECOIL_IMPULSE` / `BOOST_DECAY` / `BOOST_MAX`.
- **Teams**: `0` neutral (shapes), `1` blue (all humans in team mode), `2` red
  (all bots in team mode), `10+` unique per-tank in FFA. Same team = no damage
  (this is why team mode needs no collision changes). Use
  `world.human_team()` / `world.bot_team()` when spawning.
- **Netcode is host-authoritative.** The host's `World` is the only source of
  truth; clients send input + render snapshots. `protocol.py` uses short keys
  and packed RGB; tanks are always sent in full (few), other entities are
  area-of-interest culled (`NET_AOI_RADIUS`). Clients interpolate ~`NET_INTERP_
  DELAY` behind for smooth motion. Bump `NET_PROTOCOL` on wire-format changes.
- **Client view shims must stay attribute-compatible with the renderer.** If
  you add an attribute the renderer/HUD reads off a Tank/Entity/World, also add
  it to `SnapTank`/`SnapEntity`/`ClientWorld` in `clientgame.py` and serialize
  it in `protocol.build_snapshot`, or the client crashes. (This is the most
  common LAN break — `net_test.py` won't catch render-only attrs since it's
  headless-logic-only; the smoke path doesn't render either, so test a real
  client boot if you change rendering.)
- **Headless testing**: set `SDL_VIDEODRIVER=dummy` / `SDL_AUDIODRIVER=dummy`
  before importing pygame to run windowless. `Game._update` / `_draw` /
  `step_headless` are usable without a real display.
- **Don't commit** unless asked. Tests are scripts; there's no CI.

## Current state (as of this writing)

- Arena 9000², ~14 bots default, level cap 45, ~13k score to cap (fast trainer
  pacing). 40 classes incl. Necromancer; Guardian boss; shiny shapes; spawn
  protection; personal bests persisted to `~/.polygon_arena_stats.json`.
- LAN mode (FFA/Team) is implemented and tested headlessly end-to-end
  (in-process and as two real processes). Friendly fire is off in team mode.
- Known scaling note: JSON snapshots at 20 Hz are fine for a small LAN party;
  for many players you'd want msgpack/binary + tighter AOI.
