def availability() -> dict:
    try:
        import pytesseract
        from PIL import Image  # noqa: F401

        version = str(pytesseract.get_tesseract_version())
        return {"available": True, "version": version}
    except Exception as exc:
        return {"available": False, "message": "OCR opzionale non disponibile", "detail": type(exc).__name__}
