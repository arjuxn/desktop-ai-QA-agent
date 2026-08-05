"""OCR support for enriching screenshot context and locating text targets."""

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


def find_text_location(image_path: Path, target_text: str) -> tuple[int, int] | None:
    """Find the exact pixel center (x, y) of target_text in the screenshot using OCR."""

    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None

    raw_target = target_text.strip()
    if not raw_target:
        return None

    try:
        data = pytesseract.image_to_data(Image.open(image_path), output_type=pytesseract.Output.DICT)
    except Exception:
        return None

    n = len(data.get("text", []))
    if n == 0:
        return None

    text_clean = [str(t).strip().strip(".,'\"()[]:;").casefold() for t in data["text"]]
    confidence = [float(value) if str(value).replace(".", "", 1).lstrip("-").isdigit() else -1 for value in data.get("conf", [])]

    noise = {"button", "dropdown", "link", "icon", "the", "header", "menu", "section"}
    filtered_words = [w for w in raw_target.lower().strip(".,'\"()[]:;").split() if w not in noise]
    target_words = filtered_words if filtered_words else raw_target.lower().split()

    for w in target_words:
        w_clean = w.strip(".,'\"()[]:;")
        if not w_clean:
            continue
        for i in range(n):
            if text_clean[i] and w_clean.casefold() == text_clean[i] and (i >= len(confidence) or confidence[i] >= 20):
                l, t, width, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                return (l + width // 2, t + h // 2)

    return None
