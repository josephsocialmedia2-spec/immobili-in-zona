#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 Foto Portali: screenshot desktop e scorrimento automatico."""
from __future__ import annotations

import csv, ctypes, hashlib, json, os, time, traceback
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from PIL import ImageGrab
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.common.by import By
except ImportError as exc:
    print(f"Componente mancante: {exc}\nEsegui INSTALLA_COMPONENTI.bat")
    input("Premi INVIO per chiudere...")
    raise SystemExit(1)

BASE = Path(__file__).resolve().parent
OUT = BASE / "FOTO_PORTALI"
STOP = BASE / "STOP.txt"
CONFIG = BASE / "config.json"
CSV = OUT / "indice_screenshot.csv"
LOG = OUT / "registro_esecuzione.log"

DEFAULT: dict[str, Any] = {
    "attesa_iniziale_secondi": 45,
    "intervallo_screenshot_secondi": 5,
    "percentuale_scorrimento": 0.82,
    "attesa_caricamento_pagina_secondi": 8,
    "max_pagine_per_portale": 0,
    "porta_chrome_in_primo_piano": True,
    "attesa_tra_portali_secondi": 3,
    "portali": [
        {"nome": "IMMOBILIARE", "dominio": "immobiliare.it", "url": "https://www.immobiliare.it/"},
        {"nome": "CASA_IT", "dominio": "casa.it", "url": "https://www.casa.it/"},
        {"nome": "IDEALISTA", "dominio": "idealista.it", "url": "https://www.idealista.it/"},
    ],
}


def load_config() -> dict[str, Any]:
    if not CONFIG.exists():
        CONFIG.write_text(json.dumps(DEFAULT, ensure_ascii=False, indent=2), encoding="utf-8")
        return DEFAULT.copy()
    try:
        return {**DEFAULT, **json.loads(CONFIG.read_text(encoding="utf-8"))}
    except Exception:
        return DEFAULT.copy()


class Recorder:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        options = webdriver.ChromeOptions()
        options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        self.driver = webdriver.Chrome(options=options)

    def log(self, text: str) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        line = f"[{datetime.now():%d/%m/%Y %H:%M:%S}] {text}"
        print(line)
        with LOG.open("a", encoding="utf-8") as file:
            file.write(line + "\n")

    def check_stop(self) -> None:
        if STOP.exists():
            raise KeyboardInterrupt("Arresto richiesto")

    def sleep(self, seconds: float) -> None:
        end = time.time() + max(0, seconds)
        while time.time() < end:
            self.check_stop()
            time.sleep(min(0.25, end - time.time()))

    def focus_chrome(self) -> None:
        if os.name != "nt" or not self.cfg.get("porta_chrome_in_primo_piano", True):
            return
        try:
            user32, found = ctypes.windll.user32, []
            callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
            def callback(hwnd: int, _unused: int) -> bool:
                length = user32.GetWindowTextLengthW(hwnd)
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                if user32.IsWindowVisible(hwnd) and "chrome" in buffer.value.lower():
                    found.append(hwnd)
                return True
            user32.EnumWindows(callback_type(callback), 0)
            if found:
                user32.ShowWindow(found[0], 3)
                user32.SetForegroundWindow(found[0])
                time.sleep(0.3)
        except Exception:
            pass

    def select_portal(self, domain: str, url: str) -> None:
        for handle in self.driver.window_handles:
            self.driver.switch_to.window(handle)
            if domain in self.driver.current_url.lower():
                return
        self.driver.execute_script("window.open(arguments[0], '_blank')", url)
        self.driver.switch_to.window(self.driver.window_handles[-1])

    def countdown(self, name: str) -> None:
        seconds = int(self.cfg["attesa_iniziale_secondi"])
        print(f"\nPREPARA {name}: imposta zona e filtri.")
        for remaining in range(seconds, 0, -1):
            self.check_stop()
            print(f"\rPartenza tra {remaining:02d} secondi...", end="", flush=True)
            time.sleep(1)
        print("\r" + " " * 50 + "\r", end="")

    def screenshot(self, name: str, page: int, shot: int) -> None:
        self.focus_chrome()
        folder = OUT / name
        folder.mkdir(parents=True, exist_ok=True)
        filename = f"{name}_pagina_{page:04d}_foto_{shot:04d}_{datetime.now():%Y%m%d_%H%M%S}.png"
        path = folder / filename
        ImageGrab.grab(all_screens=True).save(path, "PNG", optimize=True)
        y = int(self.driver.execute_script("return Math.round(window.scrollY || 0)"))
        height = int(self.driver.execute_script("return Math.max(document.body.scrollHeight,document.documentElement.scrollHeight)"))
        row = [datetime.now().strftime("%d/%m/%Y %H:%M:%S"), name, page, shot, y, height, self.driver.current_url, str(path)]
        header = not CSV.exists()
        with CSV.open("a", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file, delimiter=";")
            if header:
                writer.writerow(["data_ora","portale","pagina","foto","scroll_y","altezza_pagina","url","file"])
            writer.writerow(row)
        self.log(f"Salvata {filename} | scroll {y}/{height}")

    def capture_page(self, name: str, page: int) -> None:
        self.driver.execute_script("window.scrollTo(0,0)")
        self.sleep(1)
        shot, same = 1, 0
        previous = -1
        while True:
            self.screenshot(name, page, shot)
            shot += 1
            y, viewport, height = self.driver.execute_script(
                "return [Math.round(window.scrollY),window.innerHeight,Math.max(document.body.scrollHeight,document.documentElement.scrollHeight)]"
            )
            if y + viewport >= height - 8:
                break
            self.sleep(float(self.cfg["intervallo_screenshot_secondi"]))
            self.driver.execute_script(
                "window.scrollBy(0,Math.max(300,Math.floor(window.innerHeight*arguments[0])))",
                float(self.cfg["percentuale_scorrimento"]),
            )
            current = int(self.driver.execute_script("return Math.round(window.scrollY)"))
            same = same + 1 if current == previous else 0
            previous = current
            if same >= 2:
                break

    def next_page(self) -> bool:
        selectors = [
            (By.CSS_SELECTOR, "a[rel='next'],button[rel='next']"),
            (By.XPATH, "//*[self::a or self::button or @role='button'][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'successiva')]"),
            (By.XPATH, "//*[self::a or self::button or @role='button'][contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'successiva') or contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]"),
            (By.XPATH, "//*[self::a or self::button][normalize-space(.)='›' or normalize-space(.)='»' or normalize-space(.)='→']"),
        ]
        before = self.driver.current_url + hashlib.sha1(self.driver.page_source[:12000].encode("utf-8", "ignore")).hexdigest()
        for by, selector in selectors:
            for element in self.driver.find_elements(by, selector):
                try:
                    if element.is_displayed() and element.is_enabled() and element.get_attribute("aria-disabled") != "true":
                        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});arguments[0].click();", element)
                        end = time.time() + max(15, int(self.cfg["attesa_caricamento_pagina_secondi"]) * 3)
                        while time.time() < end:
                            self.sleep(1)
                            after = self.driver.current_url + hashlib.sha1(self.driver.page_source[:12000].encode("utf-8", "ignore")).hexdigest()
                            if after != before:
                                self.sleep(float(self.cfg["attesa_caricamento_pagina_secondi"]))
                                return True
                        return False
                except WebDriverException:
                    continue
        return False

    def process(self, portal: dict[str, str]) -> None:
        name = portal["nome"]
        domain = portal.get("dominio") or portal.get("domini", [""])[0]
        url = portal.get("url") or portal.get("url_apertura")
        self.select_portal(domain, url)
        self.focus_chrome()
        self.countdown(name)
        page, seen = 1, set()
        while True:
            self.check_stop()
            signature = self.driver.current_url + hashlib.sha1(self.driver.page_source[:12000].encode("utf-8", "ignore")).hexdigest()
            if signature in seen:
                break
            seen.add(signature)
            self.log(f"{name}: pagina {page} - {self.driver.current_url}")
            self.capture_page(name, page)
            limit = int(self.cfg.get("max_pagine_per_portale", 0))
            if limit and page >= limit:
                break
            if not self.next_page():
                break
            page += 1
        (OUT / f"FINITO_{name}.txt").write_text(f"FINITO {name}\n{datetime.now():%d/%m/%Y %H:%M:%S}\n", encoding="utf-8")
        self.log(f"FINITO {name}")

    def run(self) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        STOP.unlink(missing_ok=True)
        for index, portal in enumerate(self.cfg["portali"]):
            self.process(portal)
            if index < len(self.cfg["portali"]) - 1:
                self.sleep(float(self.cfg.get("attesa_tra_portali_secondi", 3)))
        (OUT / "FINITO_TUTTI_I_PORTALI.txt").write_text("FINITO TUTTI I PORTALI", encoding="utf-8")
        self.log("FINITO TUTTI I PORTALI")


def main() -> int:
    try:
        Recorder(load_config()).run()
        return 0
    except KeyboardInterrupt:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "PROGRAMMA_FERMATO.txt").write_text("PROGRAMMA FERMATO", encoding="utf-8")
        return 2
    except Exception:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "ERRORE_PROGRAMMA.txt").write_text(traceback.format_exc(), encoding="utf-8")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    code = main()
    if os.name == "nt":
        input("\nPremi INVIO per chiudere...")
    raise SystemExit(code)
