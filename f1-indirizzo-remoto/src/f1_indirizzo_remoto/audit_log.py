SENSITIVE_FIELDS = {"value", "extracted_text", "cadastral_holder", "verified_owner"}


def redact_for_diagnostic(field_name: str, value) -> str:
    if field_name in SENSITIVE_FIELDS and value:
        return "[DATO LOCALE OMESSO]"
    return str(value or "")[:500]
