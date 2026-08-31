#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 Local Call Server — espone SOLO la Centrale Telefonate Guidate.

URL stabile via mDNS: http://f1-radar.local:8766/
Telefono, email, esiti e prospect restano sul PC. Nessun upload a GitHub/cloud.
"""
from __future__ import annotations

import html
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.getenv("F1_MOBILE_PORT", "8766"))
BASE = Path.home() / "Documents" / "F1_Directory_Microzone"
REPORT = BASE / "F1_CENTRALE_TELEFONATE_GUIDATE.html"
LINK_FILE = BASE / "LINK_CENTRALE_TELEFONATE.txt"
HOSTNAME = "f1-radar.local."


def private_ipv4():
    candidates = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            candidates.append(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip not in candidates and not ip.startswith("127."):
            candidates.insert(0, ip)
    except Exception:
        pass
    return candidates[0] if candidates else "127.0.0.1"


class Handler(BaseHTTPRequestHandler):
    server_version = "F1Calls/2.0"

    def _headers(self, status=200, ctype="text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Robots-Tag", "noindex, nofollow, noarchive")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._headers(200, "text/plain; charset=utf-8")
            self.wfile.write(b"OK")
            return
        if path not in {"/", "/F1_CENTRALE_TELEFONATE_GUIDATE.html"}:
            self._headers(404, "text/plain; charset=utf-8")
            self.wfile.write(b"Not found")
            return
        if not REPORT.exists():
            self._headers(503)
            body = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><meta http-equiv='refresh' content='20'><title>F1 Centrale Telefonate</title><style>body{font-family:Arial;background:#070907;color:#fff;padding:24px}h1{color:#39f28a}.box{background:#101510;border:1px solid #2a342c;border-radius:14px;padding:18px}</style></head><body><h1>F1 Centrale Telefonate Guidate</h1><div class='box'><b>Lista del mattino non ancora pronta.</b><p>Il Radar Susa 20 km sta preparando i prospect. La pagina si aggiorna automaticamente.</p></div></body></html>"""
            self.wfile.write(body.encode("utf-8"))
            return
        try:
            self._headers(200)
            self.wfile.write(REPORT.read_bytes())
        except Exception as exc:
            self._headers(500)
            self.wfile.write(("Errore lettura Centrale: " + html.escape(str(exc))).encode("utf-8"))

    def log_message(self, fmt, *args):
        return


def register_mdns(ip):
    try:
        from zeroconf import IPVersion, ServiceInfo, Zeroconf
        import socket as _socket
        info = ServiceInfo(
            "_http._tcp.local.",
            "F1 Centrale Telefonate._http._tcp.local.",
            addresses=[_socket.inet_aton(ip)],
            port=PORT,
            properties={b"path": b"/"},
            server=HOSTNAME,
        )
        zc = Zeroconf(ip_version=IPVersion.V4Only)
        zc.register_service(info, allow_name_change=True)
        return zc, info
    except Exception:
        return None, None


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    ip = private_ipv4()
    stable = f"http://f1-radar.local:{PORT}/"
    fallback = f"http://{ip}:{PORT}/"
    local_pc = f"http://127.0.0.1:{PORT}/"
    LINK_FILE.write_text(
        "F1 CENTRALE TELEFONATE GUIDATE\n\n"
        f"PC: {local_pc}\n"
        f"Telefono: {stable}\n"
        f"Telefono - IP di riserva: {fallback}\n\n"
        "PC e telefono devono essere sulla stessa rete privata oppure collegati tramite la VPN privata configurata.\n",
        encoding="utf-8",
    )
    zc, info = register_mdns(ip)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        if zc and info:
            try:
                zc.unregister_service(info)
                zc.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
