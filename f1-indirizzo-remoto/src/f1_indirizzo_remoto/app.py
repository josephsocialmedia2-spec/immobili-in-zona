import argparse
import mimetypes
import os
import secrets
import socket
import sqlite3
import tempfile
import threading
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for

from .address_normalizer import normalize_address
from .config import Settings, load_settings
from .contact_validator import validate_contact
from .crm_export import export_csv, export_json, export_pdf, export_xlsx
from .database import Database, DuplicatePracticeError, now_iso
from .document_parser import parse_document
from .integrations.radar_dork_adapter import prepare_import
from .letter_generator import generate_letter
from .privacy_guard import action_allowed, safe_join, validate_upload
from .query_builder import build_queries, google_search
from .schemas import AddressInput, PRACTICE_STATES, RELIABILITY_LEVELS, SOURCE_STATES
from .source_registry import validate_source


def form_bool(name: str) -> bool:
    return request.form.get(name) in {"1", "true", "on", "yes"}


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or load_settings()
    settings.ensure_directories()
    database = Database(settings.database_path, settings.backups_dir)
    database.initialize()

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=settings.secret_key,
        MAX_CONTENT_LENGTH=settings.max_upload_bytes,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
    )
    app.extensions["f1_database"] = database
    app.extensions["f1_settings"] = settings

    @app.before_request
    def csrf_protection():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not supplied or not secrets.compare_digest(str(supplied), str(session["csrf_token"])):
                abort(400, "Token di sicurezza non valido. Ricarica la pagina e riprova.")

    @app.context_processor
    def shared_context():
        return {
            "csrf_token": session.get("csrf_token", ""),
            "practice_states": PRACTICE_STATES,
            "source_states": SOURCE_STATES,
            "reliability_levels": RELIABILITY_LEVELS,
        }

    @app.get("/health")
    def health():
        return {"ok": database.integrity_ok(), "service": "F1 Indirizzo Remoto", "version": "1.0.0"}

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html", stats=database.stats(), recent=database.list_practices()[:8])

    @app.get("/pratiche")
    def practices():
        return render_template(
            "practices.html",
            practices=database.list_practices(request.args.get("stato", ""), request.args.get("q", "")),
            selected_status=request.args.get("stato", ""),
            query=request.args.get("q", ""),
        )

    @app.route("/pratiche/nuova", methods=["GET", "POST"])
    def new_practice():
        prefill = {key: request.args.get(key, "") for key in ("comune", "provincia", "via", "civico", "fonte", "url", "titolo", "segnale", "canonical_id")}
        if request.method == "GET":
            return render_template("new_practice.html", prefill=prefill)
        try:
            data = AddressInput(
                comune=request.form.get("comune", ""), provincia=request.form.get("provincia", ""),
                via=request.form.get("via", ""), civico=request.form.get("civico", ""), cap=request.form.get("cap", ""),
                scala=request.form.get("scala", ""), piano=request.form.get("piano", ""), interno=request.form.get("interno", ""),
                frazione=request.form.get("frazione", ""), nome_immobile=request.form.get("nome_immobile", ""),
                fonte_iniziale=request.form.get("fonte_iniziale", ""), link_iniziale=request.form.get("link_iniziale", ""),
                nota=request.form.get("nota", ""), funzionario=request.form.get("funzionario", ""), motivo=request.form.get("motivo", ""),
            )
            normalized = normalize_address(data)
            normalized["canonical_external_id"] = request.form.get("canonical_external_id", "").strip()
            normalized["map_url"] = build_queries(normalized)[0]["url"]
            practice_id = database.create_practice(normalized)
            if normalized.get("link_iniziale", "").startswith(("http://", "https://")):
                database.add_source(practice_id, {
                    "source_name": normalized.get("fonte_iniziale") or "Fonte iniziale",
                    "url": normalized["link_iniziale"], "query_text": "Import iniziale", "state": "DA VERIFICARE",
                    "operator_confirmed": False,
                }, normalized.get("funzionario", ""))
            flash("Pratica creata. Ora verifica indirizzo e fonti.", "success")
            return redirect(url_for("practice_detail", practice_id=practice_id))
        except DuplicatePracticeError as exc:
            flash("Esiste gia una pratica per questo indirizzo. Apro la pratica esistente.", "warning")
            return redirect(url_for("practice_detail", practice_id=exc.practice_id))
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("new_practice.html", prefill=request.form), 400

    @app.get("/pratiche/<practice_id>")
    def practice_detail(practice_id):
        practice = database.get_practice_full(practice_id)
        if not practice:
            abort(404)
        queries = build_queries(practice, practice.get("verified_owner", "") if practice.get("title_verification_status") == "VERIFICATA" else "")
        contact_permissions = {}
        for contact in practice["contacts"]:
            contact_permissions[contact["id"]] = action_allowed(contact, practice)
        return render_template("practice_detail.html", practice=practice, queries=queries, contact_permissions=contact_permissions)

    @app.post("/pratiche/<practice_id>/aggiorna")
    def update_practice(practice_id):
        practice = database.get_practice(practice_id)
        if not practice:
            abort(404)
        fields = {key: request.form.get(key, "") for key in (
            "operator", "cap", "scala", "piano", "interno", "frazione", "address_status", "status",
            "cadastral_municipality", "section", "sheet", "parcel", "subaltern", "category", "class",
            "consistency", "cadastral_area", "cadastral_income", "cadastral_holder", "holder_share",
            "verified_owner", "title_verification_status", "property_type", "reason", "notes", "last_outcome",
            "next_action", "next_action_date", "response", "privacy_status",
        )}
        if fields["privacy_status"] == "NON CONTATTARE":
            fields["status"] = "NON CONTATTARE"
            fields["next_action"] = "NESSUNA - OPPOSIZIONE REGISTRATA"
            fields["next_action_date"] = ""
        database.update_practice(practice_id, fields, fields.get("operator") or practice.get("operator", ""))
        flash("Pratica aggiornata.", "success")
        return redirect(url_for("practice_detail", practice_id=practice_id))

    @app.post("/pratiche/<practice_id>/fonti")
    def add_source(practice_id):
        practice = database.get_practice(practice_id)
        if not practice:
            abort(404)
        try:
            checked = validate_source(request.form.get("url", ""), request.form.get("state", "DA VERIFICARE"), request.form.get("page_title", ""))
            data = {
                "source_name": request.form.get("source_name", "").strip() or checked["domain"],
                "url": checked["url"], "query_text": request.form.get("query_text", "").strip(),
                "page_title": checked["title"], "useful_text": request.form.get("useful_text", "").strip()[:3000],
                "state": checked["state"], "acquired_at": now_iso(), "operator_confirmed": form_bool("operator_confirmed"),
            }
            database.add_source(practice_id, data, practice.get("operator", ""))
            flash("Fonte registrata.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("practice_detail", practice_id=practice_id))

    @app.post("/pratiche/<practice_id>/unita")
    def add_unit(practice_id):
        practice = database.get_practice(practice_id)
        if not practice:
            abort(404)
        database.add_unit(practice_id, {key: request.form.get(key, "") for key in (
            "section", "sheet", "parcel", "subaltern", "category", "floor", "interior", "holder", "holder_share", "verification_status"
        )}, practice.get("operator", ""))
        database.update_practice(practice_id, {"status": "UNITA DA IDENTIFICARE", "next_action": "SELEZIONA UNITA CORRETTA"}, practice.get("operator", ""))
        flash("Unita aggiunta senza associarla automaticamente all'intero edificio.", "success")
        return redirect(url_for("practice_detail", practice_id=practice_id))

    @app.post("/pratiche/<practice_id>/documenti")
    def upload_document(practice_id):
        practice = database.get_practice(practice_id)
        if not practice:
            abort(404)
        upload = request.files.get("document")
        if not upload or not upload.filename:
            flash("Seleziona un documento.", "error")
            return redirect(url_for("practice_detail", practice_id=practice_id))
        upload.stream.seek(0, os.SEEK_END)
        size = upload.stream.tell()
        upload.stream.seek(0)
        destination = None
        try:
            suffix = validate_upload(upload.filename, size, settings.max_upload_bytes)
            stored_name = f"{practice_id}-{uuid.uuid4().hex}{suffix}"
            destination = safe_join(settings.uploads_dir, settings.uploads_dir / stored_name)
            upload.save(destination)
            parsed = parse_document(destination)
            database.add_document(practice_id, {
                "original_name": Path(upload.filename).name,
                "stored_name": stored_name,
                "sha256": parsed["sha256"],
                "mime_type": mimetypes.guess_type(upload.filename)[0] or "application/octet-stream",
                "document_type": request.form.get("document_type", "ALTRO"),
                "extracted_text": parsed["extracted_text"],
                "proposed_fields": parsed["proposed_fields"],
            }, practice.get("operator", ""))
            new_status = "VISURA CARICATA" if request.form.get("document_type") == "VISURA CATASTALE" else practice["status"]
            database.update_practice(practice_id, {"status": new_status, "next_action": "CONFERMA DATI ESTRATTI"}, practice.get("operator", ""))
            flash("Documento letto localmente. Conferma manualmente i dati proposti.", "success")
        except (ValueError, sqlite3.IntegrityError) as exc:
            if destination and destination.exists():
                destination.unlink()
            flash(f"Documento non acquisito: {exc}", "error")
        return redirect(url_for("practice_detail", practice_id=practice_id))

    @app.post("/pratiche/<practice_id>/documenti/<int:document_id>/conferma")
    def confirm_document(practice_id, document_id):
        practice = database.get_practice_full(practice_id)
        if not practice:
            abort(404)
        document = next((item for item in practice["documents"] if item["id"] == document_id), None)
        if not document:
            abort(404)
        allowed_fields = {
            "sheet": "sheet", "parcel": "parcel", "subaltern": "subaltern", "category": "category",
            "class": "class", "consistency": "consistency", "cadastral_area": "cadastral_area",
            "cadastral_income": "cadastral_income", "holder_share": "holder_share",
            "cadastral_holder_proposed": "cadastral_holder",
        }
        updates = {}
        for proposed_name, practice_name in allowed_fields.items():
            if proposed_name in document["proposed_fields"] and form_bool(f"confirm_{proposed_name}"):
                updates[practice_name] = request.form.get(f"value_{proposed_name}", "").strip()[:250]
        if updates:
            updates["next_action"] = "VERIFICA TITOLARITA E DATI CONFERMATI"
            database.update_practice(practice_id, updates, practice.get("operator", ""))
        database.confirm_document(practice_id, document_id, practice.get("operator", ""))
        flash("Documento confermato. Sono stati salvati soltanto i campi selezionati; l'intestatario catastale resta distinto dal proprietario verificato.", "success")
        return redirect(url_for("practice_detail", practice_id=practice_id))

    @app.post("/pratiche/<practice_id>/contatti")
    def add_contact(practice_id):
        practice = database.get_practice(practice_id)
        if not practice:
            abort(404)
        try:
            data = {key: request.form.get(key, "") for key in (
                "value", "contact_type", "subject_name", "source_address", "source_url", "source_name",
                "acquired_at", "context_text", "match_reason", "address_match", "reliability", "use_condition", "contact_status", "last_outcome",
            )}
            data["operator_confirmed"] = form_bool("operator_confirmed")
            checked = validate_contact(data, practice)
            database.add_contact(practice_id, checked, practice.get("operator", ""))
            allowed, _ = action_allowed(checked, practice)
            database.update_practice(practice_id, {
                "status": "CONTATTO UTILIZZABILE" if allowed else "CONTATTO PUBBLICO DA VERIFICARE",
                "next_action": "CONTATTO MANUALE CONSENTITO" if allowed else "COMPLETA VERIFICA CONTATTO",
            }, practice.get("operator", ""))
            flash("Contatto registrato con fonte e attendibilita.", "success")
        except (ValueError, sqlite3.IntegrityError) as exc:
            flash(f"Contatto non registrato: {exc}", "error")
        return redirect(url_for("practice_detail", practice_id=practice_id))

    @app.post("/pratiche/<practice_id>/contatti/<int:contact_id>/esito")
    def contact_outcome(practice_id, contact_id):
        practice = database.get_practice_full(practice_id)
        if not practice:
            abort(404)
        contact = next((item for item in practice["contacts"] if item["id"] == contact_id), None)
        if not contact:
            abort(404)
        status = request.form.get("contact_status", "")
        if status not in {"CONTATTATO", "NESSUNA RISPOSTA", "APPUNTAMENTO", "NON CONTATTARE", "SCARTATO"}:
            flash("Esito non valido.", "error")
            return redirect(url_for("practice_detail", practice_id=practice_id))
        allowed, blockers = action_allowed(contact, practice)
        if status not in {"NON CONTATTARE", "SCARTATO"} and not allowed:
            flash("Azione bloccata: " + "; ".join(blockers), "error")
            return redirect(url_for("practice_detail", practice_id=practice_id))
        database.mark_contact_outcome(practice_id, contact_id, status, request.form.get("last_outcome", ""), practice.get("operator", ""))
        flash("Esito registrato.", "success")
        return redirect(url_for("practice_detail", practice_id=practice_id))

    @app.post("/pratiche/<practice_id>/lettera")
    def create_letter(practice_id):
        practice = database.get_practice(practice_id)
        if not practice:
            abort(404)
        if practice.get("privacy_status") == "NON CONTATTARE" or practice.get("status") == "NON CONTATTARE":
            flash("Lettera bloccata: la pratica e marcata NON CONTATTARE.", "error")
            return redirect(url_for("practice_detail", practice_id=practice_id))
        confirmed_name = request.form.get("confirmed_name", "").strip()
        if confirmed_name and practice.get("title_verification_status") != "VERIFICATA":
            flash("Nominativo escluso: la titolarita non e marcata VERIFICATA.", "warning")
            confirmed_name = ""
        destination = safe_join(settings.letters_dir, settings.letters_dir / f"LETTERA_{practice_id}.pdf")
        generate_letter(practice, destination, settings.site_url, confirmed_name)
        database.update_practice(practice_id, {"letter_generated": 1, "status": "LETTERA DA GENERARE", "next_action": "STAMPA E SPEDISCI LETTERA"}, practice.get("operator", ""))
        database.audit(practice_id, practice.get("operator", ""), "GENERA LETTERA", source=destination.name, outcome="OK")
        flash("Lettera PDF generata.", "success")
        return send_file(destination, as_attachment=True, download_name=destination.name)

    @app.get("/pratiche/<practice_id>/lettera.pdf")
    def download_letter(practice_id):
        practice = database.get_practice(practice_id)
        if not practice or not practice.get("letter_generated"):
            abort(404)
        destination = safe_join(settings.letters_dir, settings.letters_dir / f"LETTERA_{practice_id}.pdf")
        if not destination.is_file():
            abort(404)
        return send_file(destination, as_attachment=False, download_name=destination.name)

    @app.post("/pratiche/<practice_id>/lettera/spedita")
    def mark_letter_sent(practice_id):
        practice = database.get_practice(practice_id)
        if not practice:
            abort(404)
        if practice.get("privacy_status") == "NON CONTATTARE" or practice.get("status") == "NON CONTATTARE":
            flash("Spedizione bloccata: la pratica e marcata NON CONTATTARE.", "error")
            return redirect(url_for("practice_detail", practice_id=practice_id))
        database.update_practice(practice_id, {
            "letter_sent_at": request.form.get("letter_sent_at") or datetime.now().date().isoformat(),
            "status": "LETTERA SPEDITA", "next_action": "VERIFICA RISPOSTA",
            "next_action_date": request.form.get("next_action_date", ""),
        }, practice.get("operator", ""))
        flash("Spedizione registrata.", "success")
        return redirect(url_for("practice_detail", practice_id=practice_id))

    @app.get("/export/crm.csv")
    def crm_csv():
        destination = safe_join(settings.exports_dir, settings.exports_dir / "CRM_F1_INDIRIZZO_REMOTO.csv")
        export_csv(database.all_for_export(), destination)
        return send_file(destination, as_attachment=True, download_name=destination.name)

    @app.get("/export/crm.xlsx")
    def crm_xlsx():
        destination = safe_join(settings.exports_dir, settings.exports_dir / "CRM_F1_INDIRIZZO_REMOTO.xlsx")
        export_xlsx(database.all_for_export(), destination)
        return send_file(destination, as_attachment=True, download_name=destination.name)

    @app.get("/export/crm.pdf")
    def crm_pdf():
        destination = safe_join(settings.exports_dir, settings.exports_dir / "CRM_F1_INDIRIZZO_REMOTO.pdf")
        export_pdf(database.all_for_export(), destination)
        return send_file(destination, as_attachment=True, download_name=destination.name)

    @app.get("/export/crm.json")
    def crm_json():
        destination = safe_join(settings.exports_dir, settings.exports_dir / "CRM_F1_INDIRIZZO_REMOTO.json")
        export_json(database.all_for_export(), destination)
        return send_file(destination, as_attachment=True, download_name=destination.name)

    @app.get("/radar/importa")
    def radar_import():
        try:
            normalized = prepare_import(request.args.to_dict())
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("new_practice"))
        existing_id = database.find_existing_practice(normalized["duplicate_key"], normalized.get("canonical_external_id", ""))
        if existing_id:
            flash("Pratica gia esistente: apro il record senza duplicarlo.", "warning")
            return redirect(url_for("practice_detail", practice_id=existing_id))
        radar_note = normalized.get("nota", "")
        if normalized.get("public_phone_from_radar") and normalized.get("public_phone_source_from_radar"):
            radar_note += f" | CANDIDATO TELEFONO RADAR NON CONFERMATO: {normalized['public_phone_from_radar']} | FONTE CONTATTO: {normalized['public_phone_source_from_radar']}"
        return render_template("new_practice.html", prefill={
            "comune": normalized["comune"], "provincia": normalized["provincia"], "via": normalized["via"],
            "civico": normalized["civico"], "fonte": normalized.get("fonte_iniziale", "Radar F1"),
            "url": normalized.get("link_iniziale", ""), "titolo": radar_note,
            "canonical_id": normalized.get("canonical_external_id", ""),
        })

    @app.errorhandler(413)
    def too_large(_):
        return "Documento troppo grande", 413

    return app


def server_running(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def run_self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="f1-ir-selftest-") as temp:
        home = Path(temp)
        settings = Settings(home, "127.0.0.1", 8765, "self-test-secret", 2 * 1024 * 1024, "https://f1immobiliare.com")
        app = create_app(settings)
        client = app.test_client()
        response = client.get("/health")
        if response.status_code != 200 or not response.get_json().get("ok"):
            print("SELF-TEST FALLITO: servizio/database")
            return 1
        print("SELF-TEST SUPERATO")
        return 0


def main():
    parser = argparse.ArgumentParser(description="F1 Indirizzo Remoto")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        raise SystemExit(run_self_test())
    settings = load_settings()
    if settings.host not in {"127.0.0.1", "localhost", "::1"} and os.getenv("F1_IR_ALLOW_REMOTE") != "1":
        raise SystemExit("Avvio bloccato: F1 Indirizzo Remoto deve ascoltare solo su localhost")
    url = f"http://127.0.0.1:{settings.port}/"
    if server_running("127.0.0.1", settings.port):
        if os.getenv("F1_IR_NO_BROWSER") != "1":
            webbrowser.open(url)
        return
    if args.open_browser and os.getenv("F1_IR_NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app = create_app(settings)
    app.run(host=settings.host, port=settings.port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
