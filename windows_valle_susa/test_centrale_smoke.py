from __future__ import annotations

import importlib.util
import tempfile
import threading
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    central = load("centrale_telefonate_guidate", HERE / "centrale_telefonate_guidate.py")
    server_mod = load("f1_mobile_server", HERE / "f1_mobile_server.py")

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        data = base / "data"
        central.BASE = base
        central.DATA = data
        central.OUT_CSV = data / "centrale_telefonate_guidate.csv"
        central.OUT_HTML = base / "F1_CENTRALE_TELEFONATE_GUIDATE.html"

        sample = {
            "ID": "TEST001",
            "SCORE": 80,
            "COMUNE": "SUSA",
            "NOME": "Contatto Test",
            "CATEGORIA": "TEST",
            "TELEFONO": "3331234567",
            "EMAIL": "test@example.com",
            "MOTIVO_CONTATTO": "Verifica funzionale",
            "SEGNALE_RADAR": "TEST",
            "RADAR_SCORE": 80,
            "RADAR_URL": "https://example.com/radar",
            "FONTE_CONTATTO": "TEST",
            "URL_CONTATTO": "https://example.com/contatto",
            "ORIGINE": "TEST RADAR",
            "RPO_STATUS": "VERIFICATO",
            "STATO": "DA_CONTATTARE",
        }
        central.render([sample])
        html = central.OUT_HTML.read_text(encoding="utf-8")

        required = [
            "id='q'",
            "id='town'",
            "id='status'",
            "data-verify=",
            "data-outcome=",
            "CHIAMA",
            "EMAIL",
            "FONTE CONTATTO",
            "FONTE RADAR",
            "SCRIPT F1",
            "PASSA AL CRM",
            central.SCRIPT_URL,
            central.CRM_URL,
        ]
        missing = [x for x in required if x not in html]
        if missing:
            raise AssertionError("Elementi mancanti nella Centrale: " + ", ".join(missing))

        server_mod.REPORT = central.OUT_HTML
        httpd = server_mod.ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        t.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                body = r.read().decode("utf-8").strip()
                assert r.status == 200 and body == "OK", (r.status, body)
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
                body = r.read().decode("utf-8")
                assert r.status == 200
                assert "F1 CENTRALE TELEFONATE GUIDATE" in body
                assert "Contatto Test" in body
        finally:
            httpd.shutdown()
            httpd.server_close()
            t.join(timeout=2)

    print("OK: Centrale generata, controlli/tasti presenti, /health OK, pagina servita HTTP 200.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
