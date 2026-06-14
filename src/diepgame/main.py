"""Entry point: `uv run diep` or `python -m diepgame`.

Modes:
  (default)            single-player vs bots
  --host               host a LAN game (you play + friends can join)
  --join HOST[:PORT]   join a friend's LAN game
"""
from __future__ import annotations
import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="Polygon Arena — offline/LAN tank arena")
    parser.add_argument("--name", default="You", help="your in-game name")
    parser.add_argument("--bots", type=int, default=None,
                        help="number of bot opponents (default 14)")
    parser.add_argument("--window", default=None,
                        help="window size, e.g. 1600x900")
    parser.add_argument("--difficulty", choices=("easy", "normal", "hard"),
                        default="normal", help="bot AI difficulty (default normal)")
    parser.add_argument("--class", dest="tank_class", default=None,
                        help="practice mode: start as this class (e.g. overlord)")
    parser.add_argument("--level", type=int, default=None,
                        help="practice mode: start at this level (1-45)")
    # --- LAN ---
    parser.add_argument("--host", action="store_true",
                        help="host a LAN game others can join")
    parser.add_argument("--join", default=None, metavar="HOST[:PORT]",
                        help="join a LAN game at this address")
    parser.add_argument("--mode", choices=("ffa", "team"), default="ffa",
                        help="host only: ffa (everyone) or team (players vs bots)")
    parser.add_argument("--port", type=int, default=None,
                        help="game server port (default 8765)")
    parser.add_argument("--invite-port", type=int, default=None,
                        help="host invite web page port (default 8080)")
    parser.add_argument("--password", default="",
                        help="optional join password")
    parser.add_argument("--no-window", action="store_true",
                        help="host only: run a dedicated server with no window")
    args = parser.parse_args()

    if args.no_window:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    from . import config as C
    for key, value in C.DIFFICULTY_PRESETS[args.difficulty].items():
        setattr(C, key, value)
    if args.bots is not None:
        C.BOT_COUNT = max(0, args.bots)
    window = None
    if args.window:
        try:
            w, h = args.window.lower().split("x")
            window = (int(w), int(h))
            C.WINDOW_W, C.WINDOW_H = window
        except ValueError:
            parser.error("--window must look like 1600x900")
    if args.tank_class is not None:
        from .tanks.definitions import TANK_DEFS
        key = args.tank_class.lower().replace("-", "_").replace(" ", "_")
        if key not in TANK_DEFS:
            parser.error(f"unknown class '{args.tank_class}'. "
                         f"Valid: {', '.join(sorted(TANK_DEFS))}")
        C.PLAYER_START_CLASS = key
    if args.level is not None:
        C.PLAYER_START_LEVEL = max(1, min(C.LEVEL_CAP, args.level))

    port = args.port or C.NET_PORT
    invite_port = args.invite_port or C.NET_INVITE_PORT

    if args.join:
        _run_client(args, window, port)
    elif args.host:
        _run_host(args, port, invite_port)
    else:
        from .game import Game
        Game(player_name=args.name).run()


def _run_client(args, window, default_port):
    from .net.clientgame import ClientGame
    host = args.join
    port = default_port
    if ":" in host:
        host, p = host.rsplit(":", 1)
        try:
            port = int(p)
        except ValueError:
            raise SystemExit("--join port must be a number")
    if args.port:
        port = args.port
    print(f"Connecting to {host}:{port} ...")
    try:
        ClientGame(host, port, args.name, args.password, window).run()
    except ConnectionError as e:
        raise SystemExit(f"Could not join: {e}")


def _run_host(args, port, invite_port):
    from .game import Game
    from .net.server import GameServer
    from .net.lan import lan_ip, start_invite_server

    game = Game(player_name=args.name, mode=args.mode)
    server = GameServer(game.world, password=args.password)
    if not server.start(port):
        raise SystemExit(f"Could not bind game port {port} (already in use?)")
    game.server = server
    ip = lan_ip()
    start_invite_server(port, args.password, args.mode, friendly_fire=False,
                        invite_port=invite_port)
    game.net_banner = f"LAN {args.mode.upper()} {ip}:{port}"

    print("=" * 60)
    print(f"  Hosting Polygon Arena ({args.mode.upper()}) on the LAN")
    print(f"  Friends join with:  uv run diep --join {ip}:{port}"
          + (" --password ****" if args.password else ""))
    print(f"  Or open the invite page:  http://{ip}:{invite_port}")
    if args.password:
        print(f"  Password: {args.password}")
    print("=" * 60)

    if args.no_window:
        _serve_headless(game)
    else:
        game.run()
    server.stop()


def _serve_headless(game):
    """Dedicated server loop: tick the world + network, no rendering."""
    import time
    print("  (headless server — Ctrl+C to stop)")
    dt = 1.0 / 60.0
    try:
        while True:
            t0 = time.perf_counter()
            game._update(dt)
            time.sleep(max(0.0, dt - (time.perf_counter() - t0)))
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
