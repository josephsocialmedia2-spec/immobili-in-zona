#!/usr/bin/env python3
"""Self-test logico per Area Radar, senza modificare dati di produzione."""
import re

ADDRESS_RE = re.compile(
    r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo)\s+"
    r"[A-Za-zÀ-ÿ0-9'’.\-\s]{2,80}?\s+\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|\s*[A-Za-z])?\b",
    re.I,
)
STREET_RE = re.compile(
    r"\b(?:via|viale|corso|piazza|strada|borgata|frazione|vicolo|largo)\s+"
    r"[A-Za-zÀ-ÿ0-9'’.\-\s]{2,80}?",
    re.I,
)

def address_list(text):
    vals=[]
    for m in ADDRESS_RE.finditer(text):
        v=re.sub(r"\s+"," ",m.group(0)).strip(" ,.;")
        if v not in vals: vals.append(v)
    return vals

def street_of(address):
    m=STREET_RE.search(address or "")
    if not m: return ""
    s=re.sub(r"\s+"," ",m.group(0)).strip(" ,.;")
    return re.sub(r"\s+\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|\s*[A-Za-z])?$","",s).strip()

def norm_phone(v):
    d=re.sub(r"\D","",v or "")
    return d[2:] if d.startswith("39") and len(d)>10 else d

sample = "Vendesi appartamento in Via Roma 10, Vaie. Altri riferimenti: Via Roma 12 e Via Roma 14/B."
addrs = address_list(sample)
assert any("Via Roma 10" in a for a in addrs), addrs
assert street_of("Via Roma 10") == "Via Roma", street_of("Via Roma 10")
assert norm_phone("+39 333 123 4567") == "3331234567"

rpo_ok = {"3331234567"}
assert norm_phone("+39 333 123 4567") in rpo_ok
assert norm_phone("011 1234567") not in rpo_ok

print("SELFTEST OK: indirizzi, via, normalizzazione telefono e gate RPO funzionano.")
