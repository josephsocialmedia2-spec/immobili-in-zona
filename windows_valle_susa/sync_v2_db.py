#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sincronizza VALLE_SUSA_UNICO v2.0.1 con il motore microzone locale.
Entrambi i database restano sul PC Windows: nessun dato personale va su GitHub.
"""
from __future__ import annotations
import argparse, csv, os, re, sqlite3
from datetime import datetime
from pathlib import Path

LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", Path.home()/"AppData"/"Local"))
V2_DB = LOCALAPPDATA / "ValleSusaUnicoV2" / "contatti.sqlite3"
MICRO_BASE = Path.home() / "Documents" / "F1_Directory_Microzone"
MICRO_DB = MICRO_BASE / "data" / "contacts.sqlite"
IMPORT_DIR = MICRO_BASE / "IMPORTA_ESISTENTI"
EXPORT_CSV = IMPORT_DIR / "VALLE_SUSA_UNICO_v2_AUTO.csv"


def digits(v):
    d = re.sub(r"\D+", "", str(v or ""))
    return d[2:] if d.startswith("39") and len(d)>10 else d


def ensure_v2():
    V2_DB.parent.mkdir(parents=True, exist_ok=True)
    db=sqlite3.connect(V2_DB)
    db.execute("""CREATE TABLE IF NOT EXISTS contatti(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL DEFAULT '', telefono TEXT NOT NULL DEFAULT '',
      via TEXT NOT NULL DEFAULT '', civico TEXT NOT NULL DEFAULT '', cap TEXT NOT NULL DEFAULT '',
      comune TEXT NOT NULL DEFAULT '', provincia TEXT NOT NULL DEFAULT '',
      tipo TEXT NOT NULL DEFAULT '', link TEXT NOT NULL DEFAULT '', fonte TEXT NOT NULL DEFAULT '',
      acquisito_il TEXT NOT NULL DEFAULT '', aggiornato_il TEXT NOT NULL DEFAULT '',
      UNIQUE(link,nome))""")
    db.commit(); db.close()


def export_v2():
    ensure_v2(); IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    db=sqlite3.connect(V2_DB); db.row_factory=sqlite3.Row
    rows=db.execute("SELECT * FROM contatti ORDER BY comune,via,civico,nome").fetchall(); db.close()
    with EXPORT_CSV.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f,delimiter=";")
        w.writerow(["Nome","Telefono","Via","Civico","CAP","Comune","Provincia","Tipo","Fonte","Link"])
        for r in rows:
            w.writerow([r["nome"],digits(r["telefono"]),r["via"],r["civico"],r["cap"],r["comune"],r["provincia"],r["tipo"],r["fonte"],r["link"]])
    print(f"V2->MICROZONE: {len(rows)} contatti locali")


def import_micro():
    ensure_v2()
    if not MICRO_DB.exists():
        print("MICROZONE->V2: database microzone non ancora presente"); return
    src=sqlite3.connect(MICRO_DB); src.row_factory=sqlite3.Row
    rows=src.execute("SELECT * FROM contacts").fetchall(); src.close()
    dst=sqlite3.connect(V2_DB); dst.row_factory=sqlite3.Row
    now=datetime.now().isoformat(timespec="seconds"); added=updated=0
    for r in rows:
        phone=digits(r["phone"])
        if len(phone)<7: continue
        link=(r["source_url"] or "").strip(); name=(r["name"] or "").strip()
        ex=None
        if link and name:
            ex=dst.execute("SELECT * FROM contatti WHERE link=? AND nome=?",(link,name)).fetchone()
        if ex is None:
            ex=dst.execute("SELECT * FROM contatti WHERE telefono=? AND comune=? AND via=?",(phone,r["comune"],r["street"])).fetchone()
        tipo="Privato" if "bianche" in (r["source"] or "").lower() else "Azienda"
        if ex:
            dst.execute("""UPDATE contatti SET telefono=?,via=?,civico=?,comune=?,provincia=?,tipo=?,fonte=?,link=?,aggiornato_il=? WHERE id=?""",
                        (phone,r["street"],r["civic"],r["comune"],"TO",tipo,r["source"],link or ex["link"],now,ex["id"]))
            updated+=1
        else:
            dst.execute("""INSERT INTO contatti(nome,telefono,via,civico,cap,comune,provincia,tipo,link,fonte,acquisito_il,aggiornato_il)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (name,phone,r["street"],r["civic"],"",r["comune"],"TO",tipo,link,r["source"],now,now))
            added+=1
    dst.commit(); dst.close()
    print(f"MICROZONE->V2: aggiunti {added}, aggiornati {updated}")


if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("mode",choices=["export","import","both"],default="both",nargs="?")
    a=p.parse_args()
    if a.mode in {"export","both"}: export_v2()
    if a.mode in {"import","both"}: import_micro()
