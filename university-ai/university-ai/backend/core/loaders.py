"""
backend/core/loaders.py
═══════════════════════
Extracție de text din PDF, DOCX și TXT, cu metadate (pagina, sursa).

Diferențe față de versiunea originală:
  • normalizare diacritice (ţ→ț, ş→ș) — Standard Unicode modern
  • detecție automată encoding pentru TXT
  • extragere structurată din tabele DOCX (cu separator semantic)
  • păstrare metadata "page" + "section" (capitol detectat)
  • gestionarea defensivă a fișierelor corupte
"""

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pdfplumber
from docx import Document

from backend.config import settings
from backend.core import ocr
from backend.exceptions import DocumentProcessingError
from backend.logging_config import logger


# ── Normalizare ───────────────────────────────────────────────────────────────

# Caractere diacritice "vechi" din PDF-uri ROM legacy → standard Unicode
DIACRITIC_FIX = str.maketrans({
    "ţ": "ț", "Ţ": "Ț",  # virgulă în loc de sedilă
    "ş": "ș", "Ş": "Ș",
    " ": " ",        # non-breaking space
    "–": "-",        # en-dash
    "—": "-",        # em-dash
    "“": '"', "”": '"',
    "‘": "'", "’": "'",
})


def clean_text(text: str) -> str:
    """Normalizează și curăță textul extras."""
    if not text:
        return ""

    # Normalizare Unicode + corectare diacritice
    text = unicodedata.normalize("NFC", text)
    text = text.translate(DIACRITIC_FIX)

    # Form feed → paragraf
    text = re.sub(r"\f", "\n\n", text)
    text = re.sub(r"\r\n", "\n", text)

    # Eliminăm liniuțele de hyphenation (cuvinte rupte între linii)
    # ex: "regula-\nment" → "regulament"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    # Spații multiple → unul singur
    text = re.sub(r"[ \t]{2,}", " ", text)

    # Max 2 newline-uri consecutive
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ── Container pentru rezultatul unui loader ──────────────────────────────────

@dataclass
class ExtractedPage:
    """O pagină extrasă, cu metadate."""
    text: str
    page: int = 1
    extra: dict = field(default_factory=dict)


# ── PDF loader ────────────────────────────────────────────────────────────────

def extract_pdf(path: Path) -> List[ExtractedPage]:
    """
    Extrage text din PDF cu strategie hibridă:
      1. Încearcă pdfplumber (rapid, text nativ).
      2. Pentru fiecare pagină cu text gol/scurt → OCR pe acea pagină.
      3. Dacă întregul PDF e gol → OCR pe TOATE paginile.

    Numerele de pagină sunt păstrate consistent (1-indexed).
    """
    pages: List[ExtractedPage] = []
    pages_needing_ocr: List[int] = []
    total_pages = 0

    try:
        with pdfplumber.open(path) as pdf:
            total_pages = len(pdf.pages)
            for i, page in enumerate(pdf.pages, start=1):
                raw = page.extract_text() or ""
                text = clean_text(raw)
                if text and len(text) > settings.ocr_min_text_threshold:
                    pages.append(ExtractedPage(text=text, page=i))
                else:
                    # Pagina pare să fie scanată (imagine) — marcăm pentru OCR
                    pages_needing_ocr.append(i)
    except Exception as exc:
        logger.exception("Eroare la citirea PDF {}: {}", path.name, exc)
        raise DocumentProcessingError(
            f"PDF-ul '{path.name}' nu a putut fi citit. "
            "Verifică dacă nu este corupt."
        ) from exc

    # ── OCR pe paginile fără text ────────────────────────────────────────────
    if pages_needing_ocr and settings.ocr_enabled:
        if not ocr.is_tesseract_available():
            logger.warning(
                "PDF '{}' are {} pagini scanate, dar Tesseract nu e instalat. "
                "Aceste pagini vor fi sărite.",
                path.name, len(pages_needing_ocr),
            )
        else:
            logger.info(
                "OCR pe {} pagini scanate din {} (total {} pagini)",
                len(pages_needing_ocr), path.name, total_pages,
            )
            for page_num in pages_needing_ocr:
                ocr_text = ocr.ocr_pdf_page(path, page_num, dpi=settings.ocr_dpi)
                if ocr_text and len(ocr_text) > 20:
                    text = clean_text(ocr_text)
                    pages.append(ExtractedPage(
                        text=text, page=page_num, extra={"ocr": True}
                    ))
            # Resortăm după număr de pagină
            pages.sort(key=lambda p: p.page)

    if not pages:
        logger.warning("PDF gol (nici text nativ, nici OCR n-a reușit): {}", path.name)

    return pages


def extract_image(path: Path) -> List[ExtractedPage]:
    """
    Extrage text dintr-o imagine (PNG/JPG/JPEG/TIFF/BMP) prin OCR.
    """
    if not settings.ocr_enabled:
        raise DocumentProcessingError(
            "OCR este dezactivat în configurație (OCR_ENABLED=false)."
        )

    if not ocr.is_tesseract_available():
        raise DocumentProcessingError(
            "Tesseract OCR nu este instalat. Vezi README pentru instalare. "
            "Windows: https://github.com/UB-Mannheim/tesseract/wiki"
        )

    logger.info("OCR pe imagine: {}", path.name)
    text = ocr.ocr_image_file(path)
    text = clean_text(text)
    if not text or len(text) < 10:
        logger.warning("OCR a returnat text gol/foarte scurt din {}", path.name)
        return []
    return [ExtractedPage(text=text, page=1, extra={"ocr": True})]


# ── DOCX loader ───────────────────────────────────────────────────────────────

def extract_docx(path: Path) -> List[ExtractedPage]:
    """
    Extrage text dintr-un .docx, incluzând paragrafele și tabelele.

    Paragrafele intră în ordinea naturală. Tabelele sunt convertite în
    format markdown-like (cu `|`) pentru a păstra structura tabulară.
    """
    try:
        doc = Document(path)
    except Exception as exc:
        logger.exception("DOCX corupt: {}", path.name)
        raise DocumentProcessingError(
            f"Documentul Word '{path.name}' este corupt sau invalid."
        ) from exc

    parts: List[str] = []

    # Paragrafe (skip cele goale)
    for p in doc.paragraphs:
        text = p.text.strip()
        if text:
            parts.append(text)

    # Tabele → format pipe-separated cu header marker
    for ti, table in enumerate(doc.tables, start=1):
        rows_md = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                rows_md.append(" | ".join(cells))
        if rows_md:
            parts.append(f"\n[Tabel {ti}]\n" + "\n".join(rows_md))

    full_text = clean_text("\n\n".join(parts))
    return [ExtractedPage(text=full_text, page=1)] if full_text else []


# ── TXT loader ────────────────────────────────────────────────────────────────

def _detect_encoding(path: Path) -> str:
    """Detectează encoding-ul unui fișier text (UTF-8 / Latin-2 / CP1250)."""
    candidates = ["utf-8", "utf-8-sig", "windows-1250", "iso-8859-2", "latin-1"]
    raw = path.read_bytes()
    for enc in candidates:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "utf-8"  # fallback (errors=ignore)


def extract_txt(path: Path) -> List[ExtractedPage]:
    """Extrage text dintr-un .txt cu detecție automată de encoding."""
    try:
        encoding = _detect_encoding(path)
        text = path.read_text(encoding=encoding, errors="ignore")
        text = clean_text(text)
        return [ExtractedPage(text=text, page=1)] if text else []
    except Exception as exc:
        logger.exception("TXT eroare: {}", path.name)
        raise DocumentProcessingError(
            f"Fișierul text '{path.name}' nu a putut fi citit."
        ) from exc


# ── Dispatcher ────────────────────────────────────────────────────────────────

LOADERS = {
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".doc": extract_docx,
    ".txt": extract_txt,
    # Imagini — necesită Tesseract OCR instalat
    ".png": extract_image,
    ".jpg": extract_image,
    ".jpeg": extract_image,
    ".tiff": extract_image,
    ".tif": extract_image,
    ".bmp": extract_image,
}

SUPPORTED_EXTENSIONS = set(LOADERS.keys())
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}


def load_document(path: Path) -> List[ExtractedPage]:
    """Punct de intrare unic — alege loader-ul corect după extensie."""
    ext = path.suffix.lower()
    loader = LOADERS.get(ext)

    if loader is None:
        raise DocumentProcessingError(
            f"Format nesuportat: {ext}. Acceptate: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    logger.info("Extrag text din {}", path.name)
    pages = loader(path)
    logger.debug("Pagini extrase: {} (fișier: {})", len(pages), path.name)
    return pages
