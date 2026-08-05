"""Optional OCR support for enriching screenshot context."""

from __future__ import annotations

from pathlib import Path


def extract_screen_text(image_path: Path) -> tuple[str, str]:
    """Return OCR text and a short status message."""

    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return "", "OCR unavailable: install pytesseract from requirements.txt."

    try:
        text = pytesseract.image_to_string(Image.open(image_path))
    except pytesseract.TesseractNotFoundError:
        return "", "OCR unavailable: Tesseract is not installed or not on PATH."
    except Exception:
        return "", "OCR unavailable: Tesseract could not read this screenshot."

    cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not cleaned:
        return "", "OCR ran but found no readable text."
    return cleaned, f"OCR detected {len(cleaned)} characters."
