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
ARENA_SIZE = 6000          # square arena, world units == pixels at zoom 1
GRID_STEP = 30             # background grid spacing
NEST_RADIUS = 650          # central "pentagon nest" radius
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

OUTLINE_DARKEN = 0.75      # outline color = fill * this

# -------------------------------------------------------------- leveling ----
LEVEL_CAP = 45

def xp_for_level(level: int) -> float:
    """Total score required to *be* at `level` (cumulative)."""
    if level <= 1:
        return 0.0
    n = level - 1
    return 0.83 * (n ** 3) + 9.0 * n

# levels that grant a skill point (1..28 every level, then every 3rd)
def points_at_level(level: int) -> int:
    if level <= 1:
        return 0
    if level <= 28:
        return 1
    return 1 if (level - 28) % 3 == 0 else 0

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
TANK_RADIUS_PER_LEVEL = 0.28
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

# ---------------------------------------------------------------- bullets ----
BULLET_BASE_DMG = 7.0
BULLET_DMG_PER_STAT = 3.0
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
BOT_COUNT = 8
BOT_NAMES = [
    "Shiny", "Arras", "Pental", "Dorito", "Bluep", "Crash", "Octo", "Vex",
    "Mango", "Drift", "Nova", "Pixel", "Rhomb", "Snek", "Turbo", "Zephyr",
]
BOT_THINK_INTERVAL = 0.35
BOT_RESPAWN_DELAY = 2.5

# ----------------------------------------------------------------- shapes ----
SHAPE_TARGETS = {          # how many of each shape the spawner maintains
    "square": 130,
    "triangle": 70,
    "pentagon": 28,
    "alpha_pentagon": 2,
    "crasher_small": 10,
    "crasher_large": 6,
}
