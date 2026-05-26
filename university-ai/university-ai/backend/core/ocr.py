"""
backend/core/ocr.py
═══════════════════
Motor OCR pentru documente scanate și imagini.

Tehnologii:
  • pypdfium2  — pur pip, rasterizează PDF la imagine (înlocuiește poppler)
  • pytesseract — wrapper peste Tesseract OCR (binar sistem)
  • Pillow      — manipulare imagini

Strategia:
  1. Loader-ul PDF încearcă mai întâi pdfplumber (rapid, pentru PDF nativ).
  2. Dacă pagina returnează text gol/foarte scurt → rasterizăm pagina ca imagine
     la 300 DPI și o trecem prin Tesseract cu limbile `ron+eng`.
  3. Pentru fișiere imagine (PNG/JPG/TIFF) → direct prin Tesseract.

Dacă Tesseract nu este instalat pe sistem, OCR-ul se dezactivează grațios
(fără să crash-uiască aplicația) și logăm un warning clar pentru utilizator.
"""

import shutil
from pathlib import Path
from typing import List, Optional

from backend.config import settings
from backend.exceptions import DocumentProcessingError
from backend.logging_config import logger


# ── Detectare disponibilitate Tesseract ──────────────────────────────────────

_TESSERACT_AVAILABLE: Optional[bool] = None
_TESSERACT_LANGUAGES: List[str] = []


def is_tesseract_available() -> bool:
    """Detectează (o singură dată, cached) dacă Tesseract e instalat."""
    global _TESSERACT_AVAILABLE, _TESSERACT_LANGUAGES
    if _TESSERACT_AVAILABLE is not None:
        return _TESSERACT_AVAILABLE

    try:
        import pytesseract
    except ImportError:
        logger.warning("pytesseract nu e instalat — OCR dezactivat")
        _TESSERACT_AVAILABLE = False
        return False

    # Permitem suprascrierea căii binarului prin variabilă de mediu
    tesseract_cmd = settings.tesseract_cmd
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    # Verificăm că binarul există pe sistem
    binary = pytesseract.pytesseract.tesseract_cmd
    if not (Path(binary).exists() or shutil.which(binary)):
        logger.warning(
            "Tesseract NU este instalat pe sistem ('{}' nu există). "
            "OCR-ul pentru PDF-uri scanate va fi sărit. "
            "Instalare Windows: https://github.com/UB-Mannheim/tesseract/wiki",
            binary,
        )
        _TESSERACT_AVAILABLE = False
        return False

    try:
        _TESSERACT_LANGUAGES = pytesseract.get_languages(config="")
        logger.info(
            "Tesseract detectat. Limbi disponibile: {}",
            ", ".join(_TESSERACT_LANGUAGES[:10]) + "..." if len(_TESSERACT_LANGUAGES) > 10 else ", ".join(_TESSERACT_LANGUAGES),
        )
        _TESSERACT_AVAILABLE = True
    except Exception as exc:
        logger.warning("Tesseract pare instalat dar a eșuat: {}", exc)
        _TESSERACT_AVAILABLE = False

    return _TESSERACT_AVAILABLE


def _resolve_languages() -> str:
    """
    Returnează șirul de limbi pentru Tesseract, ex: "ron+eng".
    Folosește doar limbile efectiv instalate; fallback pe "eng".
    """
    requested = [l.strip() for l in settings.ocr_languages.split("+") if l.strip()]
    available = [l for l in requested if l in _TESSERACT_LANGUAGES]
    if not available:
        if "eng" in _TESSERACT_LANGUAGES:
            logger.warning(
                "Niciuna din limbile OCR cerute ({}) nu e instalată. Folosesc 'eng'.",
                requested,
            )
            return "eng"
        # Ultimă șansă — folosim ce găsim
        return _TESSERACT_LANGUAGES[0] if _TESSERACT_LANGUAGES else "eng"
    return "+".join(available)


# ── OCR pe o imagine PIL ─────────────────────────────────────────────────────

def ocr_image(image, langs: Optional[str] = None) -> str:
    """
    Rulează Tesseract pe un obiect PIL.Image.
    Returnează șir gol dacă OCR nu e disponibil.
    """
    if not is_tesseract_available():
        return ""

    import pytesseract
    langs = langs or _resolve_languages()

    try:
        text = pytesseract.image_to_string(image, lang=langs)
        return text.strip()
    except Exception as exc:
        logger.exception("OCR a eșuat pe imagine: {}", exc)
        return ""


# ── OCR pe un fișier imagine (PNG/JPG/TIFF) ──────────────────────────────────

def ocr_image_file(path: Path) -> str:
    """Aplică OCR pe un fișier imagine."""
    if not is_tesseract_available():
        raise DocumentProcessingError(
            "OCR nu este disponibil (Tesseract nu e instalat). "
            "Vezi README pentru instrucțiuni de instalare."
        )

    try:
        from PIL import Image
    except ImportError as exc:
        raise DocumentProcessingError("Pillow nu e instalat.") from exc

    try:
        with Image.open(path) as img:
            return ocr_image(img)
    except Exception as exc:
        logger.exception("OCR fișier imagine {} eșuat", path.name)
        raise DocumentProcessingError(
            f"Imaginea '{path.name}' nu a putut fi procesată: {exc}"
        ) from exc


# ── OCR pe PDF rasterizat ────────────────────────────────────────────────────

def ocr_pdf_page(pdf_path: Path, page_num: int, dpi: int = 300) -> str:
    """
    Rasterizează o pagină PDF la `dpi` și aplică OCR.
    page_num e 1-indexed (consistent cu pdfplumber).

    Returnează șir gol dacă OCR-ul nu reușește.
    """
    if not is_tesseract_available():
        return ""

    try:
        import pypdfium2 as pdfium
    except ImportError:
        logger.warning("pypdfium2 nu e instalat — OCR PDF dezactivat")
        return ""

    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
        if page_num < 1 or page_num > len(pdf):
            return ""
        page = pdf[page_num - 1]
        # scale = dpi / 72 (PDF default e 72 dpi)
        scale = dpi / 72.0
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()
        return ocr_image(pil_image)
    except Exception as exc:
        logger.warning("OCR pagina {} din {} eșuat: {}", page_num, pdf_path.name, exc)
        return ""


def ocr_pdf_all_pages(pdf_path: Path, dpi: int = 300) -> List[dict]:
    """
    Rulează OCR pe TOATE paginile unui PDF.
    Folosit când documentul e complet scanat (fără strat de text).

    Returnează listă de {"text": str, "page": int}.
    """
    if not is_tesseract_available():
        return []

    try:
        import pypdfium2 as pdfium
    except ImportError:
        return []

    results: List[dict] = []
    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
        n_pages = len(pdf)
        scale = dpi / 72.0
        logger.info("OCR full pe {} ({} pagini)", pdf_path.name, n_pages)

        for i in range(n_pages):
            page = pdf[i]
            bitmap = page.render(scale=scale)
            pil_image = bitmap.to_pil()
            text = ocr_image(pil_image)
            if text and len(text.strip()) > 20:
                results.append({"text": text, "page": i + 1})
            del bitmap, pil_image  # eliberăm memoria explicit
    except Exception as exc:
        logger.exception("OCR full PDF eșuat pentru {}: {}", pdf_path.name, exc)

    return results
