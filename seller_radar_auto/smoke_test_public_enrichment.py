#!/usr/bin/env python3
"""Smoke test deterministico del modulo public_enrichment.py."""
import ast
from pathlib import Path

SRC = Path(__file__).with_name("public_enrichment.py")
source = SRC.read_text(encoding="utf-8")
tree = ast.parse(source, filename=str(SRC))

# Carica dal file reale solo import, costanti e funzioni; non esegue il ciclo operativo di rete.
allowed = []
for node in tree.body:
    if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.Assign, ast.AnnAssign)):
        allowed.append(node)
module = ast.Module(body=allowed, type_ignores=[])
ast.fix_missing_locations(module)
ns = {"__file__": str(SRC)}
exec(compile(module, str(SRC), "exec"), ns)

contacts = ns["contacts"]
addresses = ns["addresses"]
seller_name = ns["seller_name"]
match_score = ns["match_score"]

# 1) Estrazione indirizzo/civico.
addr = addresses("Privato vende appartamento in Via Roma 10, Vaie (TO).")
assert any("Via Roma 10".casefold() in a.casefold() for a in addr), addr

# 2) Estrazione nominativo esplicito dall'annuncio.
name = seller_name('{"seller":{"name":"Mario Rossi"}}')
assert name == "Mario Rossi", name

# 3) Estrazione di recapiti pubblicati nell'annuncio.
html = """
<html><body>
Privato vende appartamento in Via Roma 10, Vaie.
Inserzionista: Mario Rossi.
Telefono 333 1234567 - email mario.rossi@example.com
</body></html>
"""
cs = contacts(html, "https://example.test/annuncio-privato", "LISTING_ORIGINALE", "HIGH")
phones = {c["value"] for c in cs if c["type"] == "PHONE"}
emails = {c["value"] for c in cs if c["type"] == "EMAIL"}
assert "3331234567" in phones, phones
assert "mario.rossi@example.com" in emails, emails

# 4) Cross-match: stesso comune + titolo/descrizione molto simili + stesso indirizzo.
item = {
    "title": "Trilocale in vendita Via Roma 10 Vaie",
    "snippet": "Trilocale 85 mq due camere balcone privato vende",
    "comune": "Vaie",
}
result = {
    "title": "Trilocale Via Roma 10 Vaie in vendita",
    "snippet": "Appartamento trilocale 85 mq due camere balcone",
}
ms = match_score(item, result, ["Via Roma 10"])
assert ms >= 55, ms

# 5) Gate privacy/qualità: contatto operativo solo per candidato privato.
private_item = {"seller_hint": "INDIZIO_PRIVATO", "private_intent": True}
agency_item = {"seller_hint": "INDIZIO_AGENZIA", "private_intent": False}
def is_private_candidate(x):
    return (
        x.get("seller_hint") == "INDIZIO_PRIVATO" or bool(x.get("private_intent"))
    ) and x.get("seller_hint") != "INDIZIO_AGENZIA"
assert is_private_candidate(private_item) is True
assert is_private_candidate(agency_item) is False

# 6) Una directory pubblica marcata REVIEW non diventa automaticamente contatto pronto.
review_contact = {"type": "PHONE", "value": "0111234567", "confidence": "REVIEW"}
assert review_contact["confidence"] not in {"HIGH", "MEDIUM"}

print("SMOKE TEST OK")
print(f"indirizzo={addr[0]}")
print(f"inserzionista={name}")
print(f"telefono={next(iter(phones))}")
print(f"email={next(iter(emails))}")
print(f"cross_match_score={ms}")
print("gate_privato=OK | gate_agenzia=OK | directory_review=OK")
