from urllib.parse import quote_plus


VISURA_URL = "https://www.agenziaentrate.gov.it/portale/schede/fabbricatiterreni/visura-catastale/visura-catastale-online"
ISPEZIONE_URL = "https://www.agenziaentrate.gov.it/portale/schede/fabbricatiterreni/ispezione-ipotecaria/ispezione-ipotecaria-online"


def google_search(query: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(query)


def google_images(query: str) -> str:
    return "https://www.google.com/search?tbm=isch&q=" + quote_plus(query)


def build_queries(practice: dict, confirmed_name: str = "") -> list[dict]:
    address = f"{practice['via']} {practice['civico']}"
    comune = practice["comune"]
    exact = f'"{address}" "{comune}"'
    maps_query = quote_plus(f"{address}, {comune}, {practice.get('provincia', '')}")
    queries = [
        ("Google Maps", f"https://www.google.com/maps/search/?api=1&query={maps_query}", f"{address}, {comune}"),
        ("Street View / Mappa", f"https://www.google.com/maps/@?api=1&map_action=map&query={maps_query}", f"Street View {address}, {comune}"),
        ("Ricerca web indirizzo", google_search(exact), exact),
        ("Immagini pubbliche", google_images(exact), exact),
        ("Portali immobiliari", google_search(f'{exact} (vendita OR affitto OR immobile)'), f'{exact} vendita affitto immobile'),
        ("Annunci storici", google_search(f'{exact} (annuncio OR venduto OR ribasso)'), f'{exact} annuncio venduto ribasso'),
        ("Attivita al civico", google_search(f'{exact} (azienda OR studio OR ufficio OR condominio)'), f'{exact} azienda studio ufficio condominio'),
        ("Telefono", google_search(f'{exact} telefono'), f'{exact} telefono'),
        ("Contatti", google_search(f'{exact} contatti'), f'{exact} contatti'),
        ("PagineBianche", google_search(f'site:paginebianche.it "{practice["via"]}" "{comune}"'), f'site:paginebianche.it "{practice["via"]}" "{comune}"'),
        ("PagineGialle", google_search(f'site:paginegialle.it "{practice["via"]}" "{comune}"'), f'site:paginegialle.it "{practice["via"]}" "{comune}"'),
        ("Visura catastale ufficiale", VISURA_URL, "Servizio ufficiale Agenzia delle Entrate"),
        ("Ispezione ipotecaria ufficiale", ISPEZIONE_URL, "Servizio ufficiale Agenzia delle Entrate"),
    ]
    if confirmed_name:
        queries.append(("Nominativo confermato", google_search(f'"{confirmed_name}" {exact} contatti'), f'"{confirmed_name}" {exact} contatti'))
    return [{"fonte": label, "url": url, "query": query} for label, url, query in queries]
