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
    args = parser.parse_args()

    from . import config as C
    if args.bots is not None:
        C.BOT_COUNT = max(0, args.bots)
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
