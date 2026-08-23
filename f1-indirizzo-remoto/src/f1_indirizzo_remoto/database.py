import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DuplicatePracticeError(ValueError):
    def __init__(self, practice_id: str):
        super().__init__(f"Pratica gia esistente: {practice_id}")
        self.practice_id = practice_id


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS practices (
    id TEXT PRIMARY KEY,
    canonical_external_id TEXT,
    opened_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    operator TEXT NOT NULL DEFAULT '',
    comune TEXT NOT NULL,
    provincia TEXT NOT NULL,
    cap TEXT NOT NULL DEFAULT '',
    via TEXT NOT NULL,
    civico TEXT NOT NULL,
    scala TEXT NOT NULL DEFAULT '',
    piano TEXT NOT NULL DEFAULT '',
    interno TEXT NOT NULL DEFAULT '',
    frazione TEXT NOT NULL DEFAULT '',
    original_address TEXT NOT NULL,
    normalized_address TEXT NOT NULL,
    duplicate_key TEXT NOT NULL,
    map_url TEXT NOT NULL DEFAULT '',
    address_status TEXT NOT NULL DEFAULT 'DA VERIFICARE',
    status TEXT NOT NULL DEFAULT 'NUOVA',
    cadastral_municipality TEXT NOT NULL DEFAULT '',
    section TEXT NOT NULL DEFAULT '',
    sheet TEXT NOT NULL DEFAULT '',
    parcel TEXT NOT NULL DEFAULT '',
    subaltern TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    class TEXT NOT NULL DEFAULT '',
    consistency TEXT NOT NULL DEFAULT '',
    cadastral_area TEXT NOT NULL DEFAULT '',
    cadastral_income TEXT NOT NULL DEFAULT '',
    cadastral_holder TEXT NOT NULL DEFAULT '',
    holder_share TEXT NOT NULL DEFAULT '',
    verified_owner TEXT NOT NULL DEFAULT '',
    title_verification_status TEXT NOT NULL DEFAULT 'DA CONFERMARE',
    property_type TEXT NOT NULL DEFAULT '',
    initial_source TEXT NOT NULL DEFAULT '',
    initial_url TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    last_outcome TEXT NOT NULL DEFAULT '',
    next_action TEXT NOT NULL DEFAULT 'VERIFICA INDIRIZZO',
    next_action_date TEXT NOT NULL DEFAULT '',
    letter_generated INTEGER NOT NULL DEFAULT 0,
    letter_sent_at TEXT NOT NULL DEFAULT '',
    response TEXT NOT NULL DEFAULT '',
    privacy_status TEXT NOT NULL DEFAULT 'ATTIVO',
    UNIQUE(duplicate_key)
);
CREATE INDEX IF NOT EXISTS idx_practices_status ON practices(status);
CREATE INDEX IF NOT EXISTS idx_practices_next_action_date ON practices(next_action_date);

CREATE TABLE IF NOT EXISTS property_units (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    practice_id TEXT NOT NULL REFERENCES practices(id) ON DELETE CASCADE,
    section TEXT NOT NULL DEFAULT '',
    sheet TEXT NOT NULL DEFAULT '',
    parcel TEXT NOT NULL DEFAULT '',
    subaltern TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    floor TEXT NOT NULL DEFAULT '',
    interior TEXT NOT NULL DEFAULT '',
    holder TEXT NOT NULL DEFAULT '',
    holder_share TEXT NOT NULL DEFAULT '',
    verification_status TEXT NOT NULL DEFAULT 'DA VERIFICARE',
    selected INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    practice_id TEXT NOT NULL REFERENCES practices(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    url TEXT NOT NULL,
    query_text TEXT NOT NULL DEFAULT '',
    page_title TEXT NOT NULL DEFAULT '',
    useful_text TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    operator_confirmed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    practice_id TEXT NOT NULL REFERENCES practices(id) ON DELETE CASCADE,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    mime_type TEXT NOT NULL DEFAULT '',
    document_type TEXT NOT NULL DEFAULT 'ALTRO',
    acquired_at TEXT NOT NULL,
    extracted_text TEXT NOT NULL DEFAULT '',
    proposed_fields_json TEXT NOT NULL DEFAULT '{}',
    operator_confirmed INTEGER NOT NULL DEFAULT 0,
    verification_status TEXT NOT NULL DEFAULT 'DA CONFERMARE',
    UNIQUE(practice_id, sha256)
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    practice_id TEXT NOT NULL REFERENCES practices(id) ON DELETE CASCADE,
    contact_type TEXT NOT NULL,
    value TEXT NOT NULL,
    subject_name TEXT NOT NULL,
    source_address TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL,
    source_name TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    context_text TEXT NOT NULL DEFAULT '',
    match_reason TEXT NOT NULL,
    address_match TEXT NOT NULL DEFAULT 'DA VERIFICARE',
    reliability TEXT NOT NULL,
    use_condition TEXT NOT NULL,
    operator_confirmed INTEGER NOT NULL DEFAULT 0,
    contact_status TEXT NOT NULL DEFAULT 'DA VERIFICARE',
    last_outcome TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(practice_id, contact_type, value, source_url)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    practice_id TEXT,
    occurred_at TEXT NOT NULL,
    operator TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    field_name TEXT NOT NULL DEFAULT '',
    old_value TEXT NOT NULL DEFAULT '',
    new_value TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT ''
);
"""


PRACTICE_UPDATE_FIELDS = {
    "operator", "cap", "scala", "piano", "interno", "frazione", "address_status", "status",
    "cadastral_municipality", "section", "sheet", "parcel", "subaltern", "category", "class",
    "consistency", "cadastral_area", "cadastral_income", "cadastral_holder", "holder_share",
    "verified_owner", "title_verification_status", "property_type", "reason", "notes", "last_outcome",
    "next_action", "next_action_date", "letter_generated", "letter_sent_at", "response", "privacy_status",
    "canonical_external_id",
}


class Database:
    def __init__(self, path: Path, backups_dir: Path | None = None):
        self.path = Path(path)
        self.backups_dir = Path(backups_dir) if backups_dir else self.path.parent / "backups"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        if self.path.exists() and not self.integrity_ok():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            damaged = self.backups_dir / f"database-danneggiato-{stamp}.sqlite3"
            shutil.copy2(self.path, damaged)
            restored = self.restore_latest_backup()
            if not restored:
                raise RuntimeError(f"Database danneggiato. Copia protetta: {damaged}")
        if self.path.exists() and self.path.stat().st_size:
            self.backup()
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def integrity_ok(self) -> bool:
        if not self.path.exists():
            return True
        try:
            with sqlite3.connect(self.path) as connection:
                return connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        except sqlite3.DatabaseError:
            return False

    def backup(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.backups_dir / f"f1-ir-backup-{stamp}.sqlite3"
        with self.connect() as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        return target

    def restore_latest_backup(self) -> Path | None:
        for candidate in sorted(self.backups_dir.glob("f1-ir-backup-*.sqlite3"), reverse=True):
            try:
                with sqlite3.connect(candidate) as connection:
                    valid = connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            except sqlite3.DatabaseError:
                valid = False
            if valid:
                shutil.copy2(candidate, self.path)
                return candidate
        return None

    def next_practice_id(self, comune: str) -> str:
        date = datetime.now().strftime("%Y-%m-%d")
        slug = "".join(ch for ch in comune.upper().replace(" ", "-") if ch.isalnum() or ch == "-")[:25]
        prefix = f"F1-IR-{date}-{slug}-"
        with self.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM practices WHERE id LIKE ?", (prefix + "%",)).fetchone()[0]
        return prefix + f"{count + 1:04d}"

    def create_practice(self, normalized: dict) -> str:
        with self.connect() as connection:
            canonical = normalized.get("canonical_external_id", "").strip()
            duplicate = connection.execute(
                "SELECT id FROM practices WHERE duplicate_key=? OR (?<>'' AND canonical_external_id=?)",
                (normalized["duplicate_key"], canonical, canonical),
            ).fetchone()
            if duplicate:
                raise DuplicatePracticeError(duplicate["id"])
            practice_id = self.next_practice_id(normalized["comune"])
            timestamp = now_iso()
            connection.execute(
                """INSERT INTO practices (
                    id, canonical_external_id, opened_at, updated_at, operator, comune, provincia, cap,
                    via, civico, scala, piano, interno, frazione, original_address, normalized_address,
                    duplicate_key, map_url, address_status, status, property_type, initial_source,
                    initial_url, reason, notes, last_outcome, next_action, next_action_date
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    practice_id, normalized.get("canonical_external_id", ""), timestamp, timestamp,
                    normalized.get("funzionario", ""), normalized["comune"], normalized["provincia"],
                    normalized.get("cap", ""), normalized["via"], normalized["civico"],
                    normalized.get("scala", ""), normalized.get("piano", ""), normalized.get("interno", ""),
                    normalized.get("frazione", ""), normalized["indirizzo_originale"],
                    normalized["indirizzo_normalizzato"], normalized["duplicate_key"],
                    normalized.get("map_url", ""), "DA VERIFICARE", "NUOVA",
                    normalized.get("nome_immobile", ""), normalized.get("fonte_iniziale", ""),
                    normalized.get("link_iniziale", ""), normalized.get("motivo", ""),
                    normalized.get("nota", ""), "Pratica aperta", "VERIFICA INDIRIZZO", datetime.now().date().isoformat(),
                ),
            )
            self._audit(connection, practice_id, normalized.get("funzionario", ""), "CREA PRATICA", outcome="OK")
        return practice_id

    def _audit(self, connection, practice_id: str | None, operator: str, action: str, field_name="", old_value="", new_value="", source="", reason="", outcome=""):
        connection.execute(
            "INSERT INTO audit_log (practice_id,occurred_at,operator,action,field_name,old_value,new_value,source,reason,outcome) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (practice_id, now_iso(), operator or "", action, field_name, str(old_value or ""), str(new_value or ""), source or "", reason or "", outcome or ""),
        )

    def audit(self, practice_id: str | None, operator: str, action: str, **kwargs) -> None:
        with self.connect() as connection:
            self._audit(connection, practice_id, operator, action, **kwargs)

    def get_practice(self, practice_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM practices WHERE id=?", (practice_id,)).fetchone()
            return dict(row) if row else None

    def find_existing_practice(self, duplicate_key: str, canonical_external_id: str = "") -> str:
        canonical = (canonical_external_id or "").strip()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM practices WHERE duplicate_key=? OR (?<>'' AND canonical_external_id=?) ORDER BY opened_at LIMIT 1",
                (duplicate_key, canonical, canonical),
            ).fetchone()
        return row["id"] if row else ""

    def get_practice_full(self, practice_id: str) -> dict | None:
        practice = self.get_practice(practice_id)
        if not practice:
            return None
        with self.connect() as connection:
            practice["sources"] = [dict(row) for row in connection.execute("SELECT * FROM sources WHERE practice_id=? ORDER BY id DESC", (practice_id,))]
            practice["documents"] = [dict(row) for row in connection.execute("SELECT * FROM documents WHERE practice_id=? ORDER BY id DESC", (practice_id,))]
            for document in practice["documents"]:
                try:
                    document["proposed_fields"] = json.loads(document.get("proposed_fields_json") or "{}")
                except (TypeError, json.JSONDecodeError):
                    document["proposed_fields"] = {}
            practice["contacts"] = [dict(row) for row in connection.execute("SELECT * FROM contacts WHERE practice_id=? ORDER BY id DESC", (practice_id,))]
            practice["units"] = [dict(row) for row in connection.execute("SELECT * FROM property_units WHERE practice_id=? ORDER BY id", (practice_id,))]
            practice["audit"] = [dict(row) for row in connection.execute("SELECT * FROM audit_log WHERE practice_id=? ORDER BY id DESC LIMIT 100", (practice_id,))]
        return practice

    def list_practices(self, status: str = "", query: str = "") -> list[dict]:
        sql = "SELECT * FROM practices WHERE 1=1"
        params = []
        if status:
            sql += " AND status=?"
            params.append(status)
        if query:
            sql += " AND (id LIKE ? OR comune LIKE ? OR via LIKE ? OR civico LIKE ?)"
            like = f"%{query}%"
            params.extend([like, like, like, like])
        sql += " ORDER BY CASE WHEN next_action_date='' THEN 1 ELSE 0 END, next_action_date, updated_at DESC"
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(sql, params)]

    def stats(self) -> dict:
        with self.connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM practices").fetchone()[0]
            pending = connection.execute("SELECT COUNT(*) FROM practices WHERE status NOT IN ('CHIUSA','SCARTATA','NON CONTATTARE')").fetchone()[0]
            letters = connection.execute("SELECT COUNT(*) FROM practices WHERE status='LETTERA DA GENERARE'").fetchone()[0]
            usable = connection.execute("SELECT COUNT(*) FROM practices WHERE status='CONTATTO UTILIZZABILE'").fetchone()[0]
        return {"total": total, "pending": pending, "letters": letters, "usable": usable}

    def update_practice(self, practice_id: str, values: dict, operator: str = "") -> None:
        updates = {key: value for key, value in values.items() if key in PRACTICE_UPDATE_FIELDS}
        if not updates:
            return
        with self.connect() as connection:
            current = connection.execute("SELECT * FROM practices WHERE id=?", (practice_id,)).fetchone()
            if not current:
                raise KeyError(practice_id)
            for key, value in updates.items():
                if str(current[key]) != str(value):
                    self._audit(connection, practice_id, operator, "AGGIORNA PRATICA", key, current[key], value, outcome="OK")
            updates["updated_at"] = now_iso()
            columns = ",".join(f"{key}=?" for key in updates)
            connection.execute(f"UPDATE practices SET {columns} WHERE id=?", (*updates.values(), practice_id))

    def add_source(self, practice_id: str, data: dict, operator: str = "") -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO sources (practice_id,source_name,url,query_text,page_title,useful_text,state,acquired_at,operator_confirmed)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (practice_id, data["source_name"], data["url"], data.get("query_text", ""), data.get("page_title", ""),
                 data.get("useful_text", ""), data["state"], data.get("acquired_at") or now_iso(), int(data.get("operator_confirmed", False))),
            )
            self._audit(connection, practice_id, operator, "AGGIUNGE FONTE", source=data["url"], outcome="OK")
            return cursor.lastrowid

    def add_unit(self, practice_id: str, data: dict, operator: str = "") -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO property_units (practice_id,section,sheet,parcel,subaltern,category,floor,interior,holder,holder_share,verification_status,selected,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (practice_id, data.get("section", ""), data.get("sheet", ""), data.get("parcel", ""), data.get("subaltern", ""),
                 data.get("category", ""), data.get("floor", ""), data.get("interior", ""), data.get("holder", ""),
                 data.get("holder_share", ""), data.get("verification_status", "DA VERIFICARE"), int(data.get("selected", False)), now_iso()),
            )
            self._audit(connection, practice_id, operator, "AGGIUNGE UNITA", outcome="OK")
            return cursor.lastrowid

    def add_document(self, practice_id: str, data: dict, operator: str = "") -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO documents (practice_id,original_name,stored_name,sha256,mime_type,document_type,acquired_at,extracted_text,proposed_fields_json,operator_confirmed,verification_status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (practice_id, data["original_name"], data["stored_name"], data["sha256"], data.get("mime_type", ""),
                 data.get("document_type", "ALTRO"), now_iso(), data.get("extracted_text", "")[:100000],
                 json.dumps(data.get("proposed_fields", {}), ensure_ascii=False), int(data.get("operator_confirmed", False)),
                 data.get("verification_status", "DA CONFERMARE")),
            )
            self._audit(connection, practice_id, operator, "CARICA DOCUMENTO", source=data["sha256"], outcome="DA CONFERMARE")
            return cursor.lastrowid

    def confirm_document(self, practice_id: str, document_id: int, operator: str = "") -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE documents SET operator_confirmed=1, verification_status='CONFERMATO' WHERE id=? AND practice_id=?",
                (document_id, practice_id),
            )
            self._audit(connection, practice_id, operator, "CONFERMA DOCUMENTO", field_name="document_id", new_value=document_id, outcome="OK")

    def add_contact(self, practice_id: str, data: dict, operator: str = "") -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO contacts (practice_id,contact_type,value,subject_name,source_address,source_url,source_name,acquired_at,context_text,match_reason,address_match,reliability,use_condition,operator_confirmed,contact_status,last_outcome,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (practice_id, data["contact_type"], data["value"], data["subject_name"], data.get("source_address", ""),
                 data["source_url"], data["source_name"], data["acquired_at"], data.get("context_text", ""), data["match_reason"],
                 data.get("address_match", "DA VERIFICARE"), data["reliability"], data["use_condition"], int(data.get("operator_confirmed", False)),
                 data.get("contact_status", "DA VERIFICARE"), data.get("last_outcome", ""), now_iso()),
            )
            self._audit(connection, practice_id, operator, "AGGIUNGE CONTATTO", source=data["source_url"], outcome=data["reliability"])
            return cursor.lastrowid

    def mark_contact_outcome(self, practice_id: str, contact_id: int, status: str, outcome: str, operator: str = "") -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE contacts SET contact_status=?, last_outcome=? WHERE id=? AND practice_id=?",
                (status, outcome, contact_id, practice_id),
            )
            if status == "NON CONTATTARE":
                connection.execute("UPDATE practices SET privacy_status='NON CONTATTARE', status='NON CONTATTARE', updated_at=? WHERE id=?", (now_iso(), practice_id))
            self._audit(connection, practice_id, operator, "ESITO CONTATTO", field_name="contact_id", new_value=f"{status}: {outcome}", outcome="OK")

    def all_for_export(self) -> list[dict]:
        with self.connect() as connection:
            practices = [dict(row) for row in connection.execute("SELECT * FROM practices ORDER BY updated_at DESC")]
            for practice in practices:
                contacts = [dict(row) for row in connection.execute("SELECT * FROM contacts WHERE practice_id=? ORDER BY reliability,id", (practice["id"],))]
                practice["contacts"] = contacts
                source = connection.execute("SELECT url,source_name FROM sources WHERE practice_id=? AND state='CONFERMATO' ORDER BY id DESC LIMIT 1", (practice["id"],)).fetchone()
                practice["confirmed_source_url"] = source["url"] if source else practice.get("initial_url", "")
                practice["confirmed_source_name"] = source["source_name"] if source else practice.get("initial_source", "")
                document = connection.execute("SELECT document_type,acquired_at FROM documents WHERE practice_id=? ORDER BY id DESC LIMIT 1", (practice["id"],)).fetchone()
                practice["latest_document"] = dict(document) if document else {}
            return practices

    def diagnostic_summary(self) -> dict:
        with self.connect() as connection:
            schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
            counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("practices", "sources", "documents", "contacts", "audit_log")}
        return {"database_ok": self.integrity_ok(), "schema_version": schema_version, "counts": counts}
