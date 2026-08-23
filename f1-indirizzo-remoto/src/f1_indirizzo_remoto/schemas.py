from dataclasses import dataclass, field


PRACTICE_STATES = (
    "NUOVA",
    "INDIRIZZO DA VERIFICARE",
    "INDIRIZZO VERIFICATO",
    "ATTESA VISURA",
    "VISURA CARICATA",
    "ATTESA OPERATORE",
    "UNITA DA IDENTIFICARE",
    "INTESTATARIO CATASTALE TROVATO",
    "TITOLARITA DA CONFERMARE",
    "TITOLARITA VERIFICATA",
    "CONTATTO PUBBLICO DA VERIFICARE",
    "CONTATTO UTILIZZABILE",
    "LETTERA DA GENERARE",
    "LETTERA SPEDITA",
    "IN ATTESA DI RISPOSTA",
    "APPUNTAMENTO",
    "NON CONTATTARE",
    "SCARTATA",
    "CHIUSA",
)

SOURCE_STATES = ("CONFERMATO", "DA VERIFICARE", "NON PERTINENTE", "NON DISPONIBILE")
RELIABILITY_LEVELS = ("A - VERIFICATO", "B - PROBABILE", "C - DEBOLE", "X - SCARTATO")


@dataclass
class AddressInput:
    comune: str
    provincia: str
    via: str
    civico: str
    cap: str = ""
    scala: str = ""
    piano: str = ""
    interno: str = ""
    frazione: str = ""
    nome_immobile: str = ""
    fonte_iniziale: str = ""
    link_iniziale: str = ""
    nota: str = ""
    funzionario: str = ""
    motivo: str = ""
    extras: dict = field(default_factory=dict)
