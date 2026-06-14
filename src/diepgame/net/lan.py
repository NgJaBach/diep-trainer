"""LAN address discovery + a tiny HTTP invite page the host serves to friends."""
from __future__ import annotations
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def lan_ip() -> str:
    """Best-effort primary LAN IPv4 address of this machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))      # no packets sent; just picks the iface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Polygon Arena - join</title>
<style>
 body{{font-family:system-ui,Segoe UI,Arial,sans-serif;background:#cdcdcd;
   color:#222;margin:0;padding:40px;text-align:center}}
 .card{{max-width:560px;margin:0 auto;background:#fff;border-radius:16px;
   padding:32px 36px;box-shadow:0 6px 24px rgba(0,0,0,.15)}}
 h1{{margin:.2em 0;color:#00b2e1}}
 code{{background:#eee;padding:3px 8px;border-radius:6px;font-size:1.05em}}
 .cmd{{display:block;background:#1d1f24;color:#7fe3ff;padding:14px;
   border-radius:10px;margin:14px 0;font-size:1.1em;user-select:all}}
 .tag{{display:inline-block;background:#00b2e1;color:#fff;border-radius:20px;
   padding:4px 14px;margin:4px;font-weight:600}}
 .muted{{color:#777;font-size:.9em;margin-top:18px}}
</style></head><body><div class="card">
 <h1>Polygon Arena</h1>
 <p><span class="tag">{mode}</span>{ff}</p>
 <p>You're invited to a LAN match. Install the game, then run:</p>
 <span class="cmd">uv run diep --join {ip}:{port}{pwflag}</span>
 <p>Server address: <code>{ip}:{port}</code>{pwline}</p>
 <p class="muted">Same Wi-Fi/LAN required. On a trusted network only &mdash;
   traffic is not encrypted.</p>
</div></body></html>"""


def _render(ip, port, password, mode, friendly_fire) -> bytes:
    pwflag = " --password ****" if password else ""
    pwline = (f"<br>Password: <code>{password}</code>" if password else "")
    ff = ""
    if mode == "team":
        ff = " &middot; friendly fire " + ("ON" if friendly_fire else "OFF")
    html = _PAGE.format(ip=ip, port=port, mode=mode.upper(), ff=ff,
                        pwflag=pwflag, pwline=pwline)
    return html.encode("utf-8")


def start_invite_server(game_port, password, mode, friendly_fire,
                        invite_port) -> ThreadingHTTPServer | None:
    """Serve the invite page in a background thread. Returns the server."""
    ip = lan_ip()
    page = _render(ip, game_port, password, mode, friendly_fire)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, *a):
            pass

    try:
        httpd = ThreadingHTTPServer(("0.0.0.0", invite_port), Handler)
    except OSError:
        return None
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
