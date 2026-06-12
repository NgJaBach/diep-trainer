"""Global configuration: window, arena, colors, leveling and balance constants.

All gameplay numbers are original approximations designed to *feel* like the
classic browser tank-arena genre. Tweak freely -- everything routes through here.
"""

# ---------------------------------------------------------------- window ----
WINDOW_W = 1280
WINDOW_H = 720
FPS = 60
TITLE = "Polygon Arena — offline tank trainer"

# ----------------------------------------------------------------- arena ----
ARENA_SIZE = 9000          # square arena, world units == pixels at zoom 1
GRID_STEP = 30             # background grid spacing
NEST_RADIUS = 850          # central "pentagon nest" radius
BORDER_PUSH = 220.0        # force pushing entities back inside the arena

# ---------------------------------------------------------------- colors ----
COL_BG        = (205, 205, 205)
COL_GRID      = (193, 193, 193)
COL_OUTSIDE   = (185, 185, 185)
COL_PLAYER    = (0, 178, 225)     # blue
COL_ENEMY     = (241, 78, 84)     # red
COL_BARREL    = (153, 153, 153)
COL_SQUARE    = (255, 232, 105)
COL_TRIANGLE  = (252, 118, 119)
COL_PENTAGON  = (118, 141, 252)
COL_ALPHA     = (118, 141, 252)
COL_CRASHER   = (241, 119, 221)
COL_HP_BACK   = (85, 85, 85)
COL_HP_FRONT  = (133, 227, 125)
COL_XP_BAR    = (255, 222, 67)
COL_LVL_BAR   = (108, 240, 162)
COL_TEXT      = (255, 255, 255)
COL_SMASHER   = (90, 90, 90)
COL_NEST      = (199, 199, 208)   # subtle tint of the central pentagon nest

OUTLINE_DARKEN = 0.75      # outline color = fill * this

# -------------------------------------------------------------- leveling ----
LEVEL_CAP = 45

def xp_for_level(level: int) -> float:
    """Total score required to *be* at `level` (cumulative).
    ~13k for level 45 — a fast trainer pace, about half the classic curve."""
    if level <= 1:
        return 0.0
    n = level - 1
    return 0.15 * (n ** 3) + 9.0 * n

# levels that grant a skill point (2..28 every level, then 30/33/.../45)
def points_at_level(level: int) -> int:
    if level <= 1:
        return 0
    if level <= 28:
        return 1
    return 1 if (level - 27) % 3 == 0 else 0

TOTAL_SKILL_POINTS = sum(points_at_level(l) for l in range(2, LEVEL_CAP + 1))  # 33

MAX_STAT = 7
STAT_NAMES = [
    "Health Regen",
    "Max Health",
    "Body Damage",
    "Bullet Speed",
    "Bullet Penetration",
    "Bullet Damage",
    "Reload",
    "Movement Speed",
]
STAT_COLORS = [
    (240, 178, 122),  # regen
    (235, 117, 251),  # max health
    (147, 112, 219),  # body dmg
    (120, 150, 255),  # blt speed
    (255, 222, 67),   # penetration
    (241, 78, 84),    # blt dmg
    (140, 255, 140),  # reload
    (0, 178, 225),    # move speed
]
CLASS_UPGRADE_LEVELS = (15, 30, 45)

# -------------------------------------------------------------- tank base ----
TANK_BASE_RADIUS = 24.0
TANK_RADIUS_PER_LEVEL = 0.36
TANK_BASE_HP = 50.0
TANK_HP_PER_LEVEL = 2.0
TANK_HP_PER_STAT = 20.0
TANK_BASE_SPEED = 230.0          # px / s
TANK_SPEED_PER_STAT = 0.07       # +7% per point
TANK_SPEED_LEVEL_DECAY = 0.0035  # slight slowdown as you level
TANK_BASE_BODY_DMG = 20.0
TANK_BODY_DMG_PER_STAT = 4.0
TANK_REGEN_BASE = 0.0012         # fraction of max hp per second
TANK_REGEN_PER_STAT = 0.0044
TANK_FAST_REGEN_DELAY = 14.0     # seconds without damage -> fast regen
TANK_FAST_REGEN_RATE = 0.07
SPAWN_PROTECTION = 6.0           # seconds of spawn shield (breaks on firing)

# practice mode (set via --class / --level CLI flags)
PLAYER_START_CLASS = None        # tank def key, or None for "basic"
PLAYER_START_LEVEL = None        # 1..45, or None for normal progression

# ----------------------------------------------------------------- recoil ----
RECOIL_IMPULSE = 26.0      # boost velocity gained per shot, per point of recoil
BOOST_DECAY = 3.0          # /s decay of recoil thrust (not capped by move speed)
BOOST_MAX = 420.0          # hard ceiling on recoil-driven speed

# ---------------------------------------------------------------- bullets ----
BULLET_BASE_DMG = 7.0
BULLET_DMG_PER_STAT = 9.0
BULLET_DMG_PER_LEVEL = 0.01      # +1%/level: a maxed lvl-45 bullet ≈ 101 dmg
                                 # (one-shots a pentagon or a fresh tank)
BULLET_SIZE_PER_LEVEL = 0.008    # bullets fatten with level (on top of body growth)
BULLET_BASE_HP = 9.0
BULLET_HP_PER_STAT = 5.5
BULLET_BASE_SPEED = 420.0
BULLET_SPEED_PER_STAT = 52.0
BULLET_LIFETIME = 2.6
BASE_RELOAD = 0.62               # seconds between shots for the basic tank
RELOAD_PER_STAT = 0.062          # multiplicative reduction per point

DRONE_LIFETIME = 1e9
TRAP_LIFETIME = 11.0

# -------------------------------------------------------------------- xp ----
KILL_XP_FRACTION = 0.5           # killing a tank grants half its score

# ------------------------------------------------------------------- bots ----
BOT_COUNT = 14
BOT_NAMES = [
    "Shiny", "Arras", "Pental", "Dorito", "Bluep", "Crash", "Octo", "Vex",
    "Mango", "Drift", "Nova", "Pixel", "Rhomb", "Snek", "Turbo", "Zephyr",
    "Quark", "Glide", "Fang", "Bolt", "Echo", "Razor", "Comet", "Mocha",
]
BOT_THINK_INTERVAL = 0.25       # seconds between brain re-evaluations
BOT_RESPAWN_DELAY = 2.5

# bot fierceness tuning (overridden by --difficulty presets below)
BOT_SKILL_RANGE = (0.7, 1.4)    # per-bot skill roll: aim, dodge, courage
BOT_SPAWN_LEVELS = (4, 22)      # initial spawn level range
BOT_RESPAWN_LEVEL_CAP = 32      # ceiling for the level bots respawn at
BOT_CATCHUP_FACTOR = 0.5        # respawn floor = this * top alive tank level
BOT_AGGRESSION = 1.0            # scales engage range / flee thresholds
BOT_DODGE = 1.0                 # 0..1+ bullet-dodging competence
BOT_PLAYER_FOCUS = 1.0          # >1 biases bot target choice toward the player

DIFFICULTY_PRESETS = {
    "easy": dict(BOT_SKILL_RANGE=(0.45, 0.9), BOT_SPAWN_LEVELS=(1, 12),
                 BOT_RESPAWN_LEVEL_CAP=15, BOT_CATCHUP_FACTOR=0.25,
                 BOT_AGGRESSION=0.7, BOT_DODGE=0.3, BOT_PLAYER_FOCUS=0.8),
    "normal": dict(BOT_SKILL_RANGE=(0.7, 1.4), BOT_SPAWN_LEVELS=(4, 22),
                   BOT_RESPAWN_LEVEL_CAP=32, BOT_CATCHUP_FACTOR=0.5,
                   BOT_AGGRESSION=1.0, BOT_DODGE=1.0, BOT_PLAYER_FOCUS=1.0),
    "hard": dict(BOT_SKILL_RANGE=(1.1, 1.6), BOT_SPAWN_LEVELS=(10, 30),
                 BOT_RESPAWN_LEVEL_CAP=45, BOT_CATCHUP_FACTOR=0.7,
                 BOT_AGGRESSION=1.35, BOT_DODGE=1.2, BOT_PLAYER_FOCUS=1.3),
}

# ----------------------------------------------------------------- shapes ----
SHAPE_TARGETS = {          # how many of each shape the spawner maintains
    "square": 290,
    "triangle": 155,
    "pentagon": 60,
    "alpha_pentagon": 4,
    "crasher_small": 18,
    "crasher_large": 11,
}

# ------------------------------------------------------------------- boss ----
BOSS_FIRST_AT = 150.0      # seconds until the first Guardian spawns
BOSS_INTERVAL = 240.0      # seconds between boss respawns after a kill
