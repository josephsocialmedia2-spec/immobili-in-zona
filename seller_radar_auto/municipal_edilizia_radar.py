#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1 RADAR EDILIZIO COMUNALE.

Per ogni segnale immobiliare target del MASTER 660 cerca sul web pubblico del Comune
atti/pratiche edilizie collegabili all'indirizzo. Non ricerca proprietari, telefoni,
email o altri dati personali. Estrae solo metadati tecnici del documento e le
DENOMINAZIONI delle pratiche/interventi riportate nel testo.

Output worker: data/edilizia_one.json
"""
from __future__ import annotations

import csv, hashlib, io, json, os, re, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

from search_engine import search

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
MASTER = DATA / "seller_master_660_classificato.csv"
OUT = Path(os.getenv("F1_EDILIZIA_OUT", str(DATA / "edilizia_one.json")))
COMUNE_ONLY = os.getenv("F1_COMUNE", "").strip()
MAX_RESULTS = int(os.getenv("F1_EDILIZIA_RESULTS", "7"))
MAX_PAGES_PER_ADDRESS = int(os.getenv("F1_EDILIZIA_PAGES_PER_ADDRESS", "10"))
UA = "F1Immobiliare-RadarEdilizio/1.0 (public municipal acts; f1immobiliaresusa@outlook.it)"

TARGET_TYPES = {
    "APPARTAMENTO", "VILLA", "CASA_INDIPENDENTE_TERRATETTO",
    "RUSTICO_CASALE_BAITA", "NEGOZIO_COMMERCIALE",
}

# Nome canonico -> regex. Questi sono NOMI DI PRATICHE/ATTI, non persone.
TERMS = {
    "EDILIZIA_LIBERA": r"\bedilizia\s+libera\b",
    "CILA": r"\bC\.?I\.?L\.?A\.?\b|comunicazione\s+di\s+inizio\s+lavori\s+asseverata",
    "CILAS": r"\bC\.?I\.?L\.?A\.?S\.?\b",
    "SCIA_EDILIZIA": r"\bS\.?C\.?I\.?A\.?\b|segnalazione\s+certificata\s+di\s+inizio\s+attivit[aà]",
    "SCIA_ALTERNATIVA_PDC": r"SCIA.{0,50}(alternativa|sostitutiva).{0,50}(permesso|PDC)",
    "PERMESSO_DI_COSTRUIRE": r"permesso\s+di\s+costruire|\bP\.?D\.?C\.?\b",
    "PERMESSO_CONVENZIONATO": r"permesso\s+di\s+costruire\s+convenzionato",
    "DIA_STORICA": r"\bD\.?I\.?A\.?\b|denuncia\s+di\s+inizio\s+attivit[aà]",
    "CONCESSIONE_EDILIZIA_STORICA": r"concessione\s+edilizia",
    "LICENZA_EDILIZIA_STORICA": r"licenza\s+edilizia",
    "AUTORIZZAZIONE_EDILIZIA_STORICA": r"autorizzazione\s+edilizia",
    "AGIBILITA_SCA": r"agibilit[aà]|segnalazione\s+certificata\s+.*agibilit[aà]|\bSCA\b",
    "AUTORIZZAZIONE_PAESAGGISTICA": r"autorizzazione\s+paesaggistica",
    "COMPATIBILITA_PAESAGGISTICA": r"accertamento\s+di\s+compatibilit[aà]\s+paesaggistica",
    "SANATORIA": r"sanatoria|permesso\s+in\s+sanatoria|fiscalizzazione\s+abuso",
    "ACCERTAMENTO_CONFORMITA": r"accertamento\s+di\s+conformit[aà]",
    "CONDONO_EDILIZIO": r"condono\s+edilizio",
    "ORDINANZA_DEMOLIZIONE": r"ordinanza.{0,80}demolizion|demolizione.{0,80}ordinanza",
    "SOSPENSIONE_LAVORI": r"sospensione\s+(dei\s+)?lavori",
    "ABUSO_EDILIZIO": r"abuso\s+edilizio|opere\s+abusive",
    "VARIANTE": r"variante\s+(in\s+corso\s+d['’]opera|al\s+permesso|alla\s+SCIA|edilizia)",
    "CAMBIO_DESTINAZIONE_USO": r"cambio\s+di\s+destinazione\s+d['’]uso|mutamento\s+di\s+destinazione\s+d['’]uso",
    "FRAZIONAMENTO_FUSIONE": r"frazionamento|fusione\s+di\s+unit[aà]",
    "RISTRUTTURAZIONE_EDILIZIA": r"ristrutturazione\s+edilizia",
    "MANUTENZIONE_STRAORDINARIA": r"manutenzione\s+straordinaria",
    "RESTAURO_RISANAMENTO": r"restauro|risanamento\s+conservativo",
    "NUOVA_COSTRUZIONE": r"nuova\s+costruzione",
    "DEMOLIZIONE_RICOSTRUZIONE": r"demolizione.{0,50}ricostruzione|ricostruzione.{0,50}demolizione",
    "AMPLIAMENTO": r"\bampliamento\b",
    "SOPRAELEVAZIONE": r"\bsopraelevazione\b",
    "AUTORIZZAZIONE_SISMICA": r"autorizzazione\s+sismica|deposito\s+sismico|denuncia\s+opere\s+strutturali",
    "PIANO_ESECUTIVO_CONVENZIONATO": r"piano\s+esecutivo\s+convenzionato|\bPEC\b.{0,80}(urbanistic|convenzion|piano)|(?:piano|convenzion).{0,80}\bPEC\b",
    "PIANO_DI_RECUPERO": r"piano\s+di\s+recupero",
    "CONVENZIONE_URBANISTICA": r"convenzione\s+urbanistica",
}

PUBLIC_PLATFORM_HINTS = (
    "comune.", "gov.it", "halleyweb", "servizipubblicaamministrazione",
    "trasparenza", "albopretorio", "albo-pretorio", "hypersic", "urbi",
    "municipiumapp", "cloud.urbi", "soluzionipa", "egov",
)
DOC_HINTS = (
    "comune di ", "albo pretorio", "amministrazione trasparente", "urbanistica",
    "edilizia", "sportello unico", "determinazione", "deliberazione", "ordinanza",
    "permesso di costruire", "autorizzazione paesaggistica",
)
PERSONAL_LABEL_RE = re.compile(r"(?i)(proprietari[oa]?|richiedente|intestatari[oa]?|codice\s+fiscale|nato\s+a|residente\s+in)\s*[:\-].{0,120}")


def now(): return datetime.now(timezone.utc).isoformat()
def norm(s):
    s = str(s or "").casefold().replace("’", "'")
    s = s.translate(str.maketrans("àèéìòù", "aeeiou"))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()
def street_only(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip(" ,.;")
    return re.sub(r"\s+\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|\s*[A-Za-z])?\s*$", "", s).strip()
def civic_only(s):
    m = re.search(r"\s+(\d{1,4}(?:\s*/\s*[A-Za-z0-9]+|\s*[A-Za-z])?)\s*$", str(s or ""))
    return re.sub(r"\s+", "", m.group(1)) if m else ""
def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f)) if path.exists() else []
def safe_url(u):
    try:
        p=urllib.parse.urlparse(str(u or "").strip())
        return u if p.scheme in {"http","https"} and p.netloc else ""
    except Exception: return ""
def clean_html(s):
    s=re.sub(r"(?is)<script\b[^>]*>.*?</script>"," ",s or "")
    s=re.sub(r"(?is)<style\b[^>]*>.*?</style>"," ",s)
    s=re.sub(r"(?s)<[^>]+>"," ",s)
    return re.sub(r"\s+"," ",s).strip()
def fetch_bytes(url, limit=5_000_000):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/pdf,*/*"})
    try:
        with urllib.request.urlopen(req,timeout=22) as r:
            return r.read(limit),(r.headers.get("Content-Type") or "").lower()
    except Exception: return b"",""
def page_text(url, title, snippet):
    raw,ctype=fetch_bytes(url)
    base=(title or "")+" "+(snippet or "")
    if not raw: return base,"SOLO_SNIPPET_DA_VERIFICARE"
    if "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader=PdfReader(io.BytesIO(raw))
            text=" ".join((p.extract_text() or "") for p in reader.pages[:35])
            return (base+" "+text)[:900_000],"TESTO_PDF"
        except Exception:
            return base,"PDF_NON_LEGGIBILE"
    try: body=raw.decode("utf-8",errors="replace")
    except Exception: body=str(raw[:500000])
    return (base+" "+clean_html(body))[:900_000],"TESTO_HTML"
def public_municipal_source(url,text,comune):
    host=urllib.parse.urlparse(url).netloc.casefold()
    low=str(text or "").casefold()
    content_ok=("comune di "+comune.casefold()) in low and any(h in low for h in DOC_HINTS)
    host_ok=any(h in host for h in PUBLIC_PLATFORM_HINTS)
    return host_ok or content_ok

def detect_terms(text):
    # Rimuove segmenti tipicamente personali prima della classificazione; non vengono salvati.
    safe_text=PERSONAL_LABEL_RE.sub(" ",str(text or ""))
    found=[]
    for name,pat in TERMS.items():
        if re.search(pat,safe_text,re.I|re.S): found.append(name)
    # PEC mail/allegato non è PEC urbanistico se manca il contesto urbanistico.
    if "PIANO_ESECUTIVO_CONVENZIONATO" in found:
        if re.search(r"(?i)posta\s+elettronica\s+certificata|\bpec@|documento[_ -]?pec",safe_text) and not re.search(r"(?i)piano\s+esecutivo\s+convenzionato|strumento\s+urbanistico|convenzione\s+urbanistica",safe_text):
            found.remove("PIANO_ESECUTIVO_CONVENZIONATO")
    return found

def nature(terms):
    t=set(terms)
    if t & {"CILA","CILAS"}: return "COMUNICAZIONE"
    if t & {"SCIA_EDILIZIA","SCIA_ALTERNATIVA_PDC","AGIBILITA_SCA","DIA_STORICA"}: return "SEGNALAZIONE"
    if t & {"PERMESSO_DI_COSTRUIRE","PERMESSO_CONVENZIONATO","AUTORIZZAZIONE_PAESAGGISTICA","AUTORIZZAZIONE_SISMICA"}: return "AUTORIZZAZIONE_O_PERMESSO"
    if t & {"SANATORIA","ACCERTAMENTO_CONFORMITA","CONDONO_EDILIZIO","COMPATIBILITA_PAESAGGISTICA"}: return "REGOLARIZZAZIONE_SANATORIA"
    if t & {"ORDINANZA_DEMOLIZIONE","SOSPENSIONE_LAVORI","ABUSO_EDILIZIO"}: return "VIGILANZA_ORDINANZA"
    if t & {"PIANO_ESECUTIVO_CONVENZIONATO","PIANO_DI_RECUPERO","CONVENZIONE_URBANISTICA"}: return "URBANISTICA_ATTUATIVA"
    return "INTERVENTO_EDILIZIO"
def match_level(text,comune,address):
    n=norm(text); town=norm(comune); street=norm(street_only(address)); civic=norm(civic_only(address))
    if town and town not in n: return "NESSUN_MATCH_COMUNE"
    if not street or street not in n: return "COMUNE_SENZA_MATCH_VIA"
    if civic and re.search(rf"(?:^| ){re.escape(civic)}(?: |$)",n): return "CIVICO_ESATTO"
    return "STESSA_VIA"
def queries(comune,address):
    st=street_only(address); cv=civic_only(address)
    full=f"{st} {cv}".strip()
    return [
        f'"{full}" "{comune}" ("permesso di costruire" OR CILA OR SCIA OR CILAS OR DIA)',
        f'"{st}" "{comune}" (sanatoria OR condono OR demolizione OR agibilita OR "autorizzazione paesaggistica")',
        f'"{st}" "{comune}" (ristrutturazione OR ampliamento OR sopraelevazione OR "cambio destinazione d uso" OR frazionamento)',
        f'"Comune di {comune}" "{st}" (edilizia OR urbanistica OR "albo pretorio")',
    ]

def main():
    rows=read_csv(MASTER)
    targets=[]
    for r in rows:
        if COMUNE_ONLY and norm(r.get("COMUNE"))!=norm(COMUNE_ONLY): continue
        typ=(r.get("TIPOLOGIA_REALE_INFERITA") or "").strip()
        title=(r.get("TITOLO") or "")
        if typ not in TARGET_TYPES and not re.search(r"(?i)attivit[aà]|locale\s+commerciale|negozio",title): continue
        addr=(r.get("DOVE_ANDRE") or "").strip()
        if not addr or "verificare" in norm(addr): continue
        targets.append(r)

    docs=[]; seen=set()
    for pos,r in enumerate(targets,1):
        comune=(r.get("COMUNE") or "").strip(); address=(r.get("DOVE_ANDRE") or "").strip()
        pages=0
        for q in queries(comune,address):
            results,err=search(q,MAX_RESULTS)
            for hit in results:
                if pages>=MAX_PAGES_PER_ADDRESS: break
                url=safe_url(hit.get("url"))
                if not url or (r.get("MASTER_660_ID"),url) in seen: continue
                seen.add((r.get("MASTER_660_ID"),url)); pages+=1
                text,read_state=page_text(url,hit.get("title"),hit.get("snippet"))
                if not public_municipal_source(url,text,comune): continue
                terms=detect_terms(text)
                if not terms: continue
                level=match_level(text,comune,address)
                if level in {"NESSUN_MATCH_COMUNE","COMUNE_SENZA_MATCH_VIA"}: continue
                excerpt=re.sub(r"\s+"," ",str(hit.get("snippet") or ""))[:700]
                did=hashlib.sha256(f"{r.get('MASTER_660_ID')}|{url}|{'|'.join(terms)}".encode()).hexdigest()[:20]
                docs.append({
                    "DOC_ID":did,"MASTER_660_ID":r.get("MASTER_660_ID","") ,"COMUNE":comune,
                    "INDIRIZZO_SEGNALE":address,"TIPOLOGIA_IMMOBILE":r.get("TIPOLOGIA_REALE_INFERITA","") ,
                    "MATCH_INDIRIZZO":level,"NATURA_ATTO":nature(terms),"PRATICHE_RILEVATE":terms,
                    "TITOLO_DOCUMENTO":hit.get("title","")[:240],"ESTRATTO_PUBBLICO":excerpt,
                    "URL_DOCUMENTO":url,"FONTE_HOST":urllib.parse.urlparse(url).netloc,
                    "LETTURA":read_state,"RILEVATO_IL":now(),"QUERY":q,
                    "NOTA":"Segnale documentale pubblico: non prova proprieta, vendita o incarico; verificare il documento.",
                })
        print(f"EDILIZIA {pos}/{len(targets)} | {comune} | {address} | documenti={sum(1 for d in docs if d['MASTER_660_ID']==r.get('MASTER_660_ID'))}")

    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"generated_at":now(),"comune":COMUNE_ONLY,"targets":len(targets),"documents":docs},ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"EDILIZIA WORKER OK | comune={COMUNE_ONLY or 'ALL'} | target={len(targets)} | documenti={len(docs)}")

if __name__=="__main__": main()
