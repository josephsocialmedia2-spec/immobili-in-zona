# Area Radar

Flusso operativo:

1. Ogni annuncio, anche se pubblicato da un'agenzia, entra nel radar di zona.
2. Il sistema ricava via/civico dalle evidenze pubbliche disponibili.
3. Cerca altri indirizzi pubblicamente indicizzati sulla stessa via.
4. Genera azioni `VAI_IN_ZONA` per gli indirizzi rilevati.
5. I recapiti telefonici già collegati all'annuncio restano `VERIFICA_RPO` finché non risultano presenti in `rpo_approved.csv` con `approved=SI`.
6. Solo dopo la verifica diventano `CHIAMA`.
7. Non vengono associati numeri a vicini o presunti parenti per sola coincidenza di cognome o prossimità geografica.

Output principale: `seller_radar_auto/data/area_radar.csv`.
