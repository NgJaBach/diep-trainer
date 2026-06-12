"""Entry point: `uv run diep` or `python -m diepgame`."""
from __future__ import annotations
import argparse


def main():
    parser = argparse.ArgumentParser(description="Polygon Arena — offline tank trainer")
    parser.add_argument("--name", default="You", help="your in-game name")
    parser.add_argument("--bots", type=int, default=None,
                        help="number of bot opponents (default 8)")
    parser.add_argument("--window", default=None,
                        help="window size, e.g. 1600x900")
    parser.add_argument("--difficulty", choices=("easy", "normal", "hard"),
                        default="normal", help="bot AI difficulty (default normal)")
    parser.add_argument("--class", dest="tank_class", default=None,
                        help="practice mode: start as this class (e.g. overlord)")
    parser.add_argument("--level", type=int, default=None,
                        help="practice mode: start at this level (1-45)")
    args = parser.parse_args()

    from . import config as C
    for key, value in C.DIFFICULTY_PRESETS[args.difficulty].items():
        setattr(C, key, value)
    if args.bots is not None:
        C.BOT_COUNT = max(0, args.bots)
    if args.tank_class is not None:
        from .tanks.definitions import TANK_DEFS
        key = args.tank_class.lower().replace("-", "_").replace(" ", "_")
        if key not in TANK_DEFS:
            parser.error(f"unknown class '{args.tank_class}'. "
                         f"Valid: {', '.join(sorted(TANK_DEFS))}")
        C.PLAYER_START_CLASS = key
    if args.level is not None:
        C.PLAYER_START_LEVEL = max(1, min(C.LEVEL_CAP, args.level))
    if args.window:
        try:
            w, h = args.window.lower().split("x")
            C.WINDOW_W, C.WINDOW_H = int(w), int(h)
        except ValueError:
            parser.error("--window must look like 1600x900")

    from .game import Game
    Game(player_name=args.name).run()


if __name__ == "__main__":
    main()
