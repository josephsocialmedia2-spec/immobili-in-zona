from f1_indirizzo_remoto.app import create_app
from f1_indirizzo_remoto.address_normalizer import normalize_address
from f1_indirizzo_remoto.schemas import AddressInput


def csrf(client):
    client.get("/")
    with client.session_transaction() as session:
        return session["csrf_token"]


def test_server_is_local_and_dashboard_works(settings):
    app = create_app(settings)
    assert settings.host == "127.0.0.1"
    response = app.test_client().get("/")
    assert response.status_code == 200
    assert b"NUOVO INDIRIZZO" in response.data


def test_csrf_blocks_mutation(settings):
    app = create_app(settings)
    response = app.test_client().post("/pratiche/nuova", data={})
    assert response.status_code == 400


def test_create_practice_end_to_end(settings):
    app = create_app(settings)
    client = app.test_client()
    response = client.post("/pratiche/nuova", data={
        "csrf_token": csrf(client), "comune": "Comune Esempio", "provincia": "TO",
        "via": "Via Inventata", "civico": "7", "funzionario": "Operatore Test",
        "motivo": "Test", "nota": "Dati sintetici",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Via Inventata 7" in response.data
    assert b"PROSSIMA AZIONE" in response.data


def test_document_confirmation_updates_only_selected_fields(settings):
    app = create_app(settings)
    db = app.extensions["f1_database"]
    normalized = normalize_address(AddressInput(comune="Comune Esempio", provincia="TO", via="Via Inventata", civico="9"))
    normalized.update({"map_url": "https://example.test/maps", "canonical_external_id": ""})
    practice_id = db.create_practice(normalized)
    document_id = db.add_document(practice_id, {
        "original_name": "visura_demo.pdf", "stored_name": "demo.pdf", "sha256": "a" * 64,
        "proposed_fields": {"sheet": "10", "parcel": "20"},
    })
    client = app.test_client()
    response = client.post(f"/pratiche/{practice_id}/documenti/{document_id}/conferma", data={
        "csrf_token": csrf(client), "confirm_sheet": "on", "value_sheet": "10", "value_parcel": "20",
    }, follow_redirects=True)
    assert response.status_code == 200
    practice = db.get_practice(practice_id)
    assert practice["sheet"] == "10"
    assert practice["parcel"] == ""


def test_non_contact_status_blocks_letter(settings):
    app = create_app(settings)
    db = app.extensions["f1_database"]
    normalized = normalize_address(AddressInput(comune="Comune Esempio", provincia="TO", via="Via Inventata", civico="11"))
    normalized.update({"map_url": "https://example.test/maps", "canonical_external_id": ""})
    practice_id = db.create_practice(normalized)
    db.update_practice(practice_id, {"status": "NON CONTATTARE", "privacy_status": "NON CONTATTARE"})
    client = app.test_client()
    response = client.post(f"/pratiche/{practice_id}/lettera", data={"csrf_token": csrf(client)}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Lettera bloccata" in response.data
    assert not list(settings.letters_dir.glob("*.pdf"))


def test_user_text_is_html_escaped(settings):
    app = create_app(settings)
    client = app.test_client()
    response = client.post("/pratiche/nuova", data={
        "csrf_token": csrf(client), "comune": "Comune <script>alert(1)</script>", "provincia": "TO",
        "via": "Via Inventata", "civico": "15", "motivo": "Test escaping",
    }, follow_redirects=True)
    assert b"<script>alert(1)</script>" not in response.data
    assert b"&lt;script&gt;" in response.data
