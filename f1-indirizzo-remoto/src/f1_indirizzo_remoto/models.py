"""Nomi e relazioni delle entita persistite in SQLite.

Il progetto usa sqlite3 con query parametrizzate per mantenere l'installazione Windows semplice.
Le tabelle principali sono practices, property_units, sources, documents, contacts e audit_log.
"""

ENTITY_NAMES = ("practices", "property_units", "sources", "documents", "contacts", "audit_log")
