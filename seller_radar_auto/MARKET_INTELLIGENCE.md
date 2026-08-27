# F1 Market Intelligence

Il Seller Radar alimenta un livello storico di intelligence immobiliare per Comune, via, tipologia e agenzia.

## Orario

Il workflow principale è schedulato ogni giorno alle **00:15 Europe/Rome**. GitHub usa UTC, quindi il workflow ha due slot UTC e un gate sull'ora locale italiana per gestire automaticamente ora solare/legale e piccoli ritardi di GitHub Actions.

## Output

- `data/intelligence/immobili_snapshot.csv`: fotografia normalizzata degli immobili monitorati.
- `data/intelligence/kpi_comuni.csv`: stock, prezzi, €/m², permanenza, nuovi, ribassi, uscite osservate, turnover e tipologie.
- `data/intelligence/kpi_vie.csv`: brief per singola via/borgata/località.
- `data/intelligence/kpi_tipologie.csv`: comportamento delle tipologie per Comune.
- `data/intelligence/kpi_agenzie.csv`: stock, nuovi incarichi osservati, uscite, ribassi, tempi e score operativo per agenzia quando il nome dell'inserzionista è identificabile.
- `data/intelligence/eventi_mercato.csv`: nuovi immobili, ribassi, aumenti, uscite osservate, rientri/ripubblicazioni, cambi agenzia e indirizzi scoperti.
- `data/intelligence/history/YYYY-MM-DD.json`: snapshot giornaliero per analisi storiche.
- `intelligence_dashboard.html`: dashboard consultabile da smartphone prima di un appuntamento.

## Stati di uscita

Una sparizione dai risultati non è una vendita certa.

- 1–2 cicli sani senza ritrovamento: l'immobile resta monitorato.
- 3–6 cicli sani senza ritrovamento: `POSSIBILE_USCITA`.
- 7+ cicli sani senza ritrovamento: `USCITO_MERCATO`.
- Se ricompare: `RELISTED`, poi torna `TRACKED` al controllo successivo.
- `VENDUTO_CONFERMATO` viene conteggiato solo se lo stato o il testo forniscono una conferma esplicita.

## KPI da leggere davanti al cliente

Filtrando Comune e via si ottengono: stock attivo, prezzo mediano, prezzo mediano €/m², permanenza mediana, ribassi rilevati, immobili monitorati, tipologie con maggiore offerta e proxy di rotazione.

La “tipologia a rotazione rapida” è un **proxy** basato sulle uscite osservate e sui tempi di permanenza; non è una misura diretta della domanda degli acquirenti finché non viene collegata a dati di venduto/rogito o lead.

## Agenzie

La classifica agenzie misura comportamento osservato, non vendite dichiarate: stock, nuovi annunci, uscite, tempo medio/mediano, frequenza e tempi dei ribassi, ribasso medio e turnover. Un'uscita può essere vendita, scadenza mandato, ritiro o mancata indicizzazione.
