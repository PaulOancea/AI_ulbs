"""
backend/core/chunker.py
═══════════════════════
Chunking inteligent pentru documente juridice/regulamentare.

Strategia "legal-aware":
  1. Identifică structura textului: Capitol, Secțiune, Articol, alineate.
  2. Preferă să rupă pe limite naturale (articol întreg) când e posibil.
  3. Folosește RecursiveCharacterTextSplitter ca fallback (LangChain).
  4. Atașează metadate cu eticheta secțiunii detectate (ex: "Art. 17").

Motivul pentru care chunking-ul naiv eșuează:
  • un articol din regulament poate avea 200-1500 caractere → split fix
    rupe la jumătatea unei propoziții juridice esențiale;
  • numerele de articol ("Art. 17 alin. (2)") sunt referințe critice
    care trebuie păstrate în același chunk cu conținutul lor;
  • articolele scurte (un singur alineat) ar trebui să rămână întregi.
"""

import re
from dataclasses import dataclass
from typing import List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.config import settings
from backend.logging_config import logger


# ── Pattern-uri pentru structura juridică ─────────────────────────────────────
# Captează: "Articolul 17", "Art. 17", "ART. 17", "Capitolul III", "Secțiunea 2"

RE_ARTICLE = re.compile(
    r"(?im)^\s*(?:articolul|art\.?)\s+(\d+(?:[a-z])?(?:\^?\d+)?)\b",
)
RE_CHAPTER = re.compile(r"(?im)^\s*capitolul\s+([ivxlcdm]+|\d+)\b")
RE_SECTION = re.compile(r"(?im)^\s*sec[țt]iunea\s+(\d+|[ivxlcdm]+)\b")


@dataclass
class Chunk:
    """Un fragment de text gata pentru a fi indexat."""
    text: str
    source: str
    page: int
    section: Optional[str] = None  # ex: "Art. 17" sau "Capitolul II"
    chunk_index: int = 0

    def to_metadata(self) -> dict:
        """Convertește în dict pentru ChromaDB (toate valorile string)."""
        return {
            "source": self.source,
            "page": str(self.page),
            "section": self.section or "",
            "chunk_index": str(self.chunk_index),
        }


# ── Detector de structură ─────────────────────────────────────────────────────

def detect_section(text: str) -> Optional[str]:
    """
    Identifică eticheta secțiunii care apare la începutul unui chunk.
    Prioritate: Articol > Secțiune > Capitol (cel mai specific câștigă).
    """
    # Examinăm doar primele 200 caractere — eticheta apare la început
    head = text[:200]

    m = RE_ARTICLE.search(head)
    if m:
        return f"Art. {m.group(1)}"

    m = RE_SECTION.search(head)
    if m:
        return f"Secțiunea {m.group(1)}"

    m = RE_CHAPTER.search(head)
    if m:
        return f"Capitolul {m.group(1)}"

    return None


# ── Chunker principal ─────────────────────────────────────────────────────────

class LegalAwareChunker:
    """
    Chunker care încearcă întâi să segmenteze pe articole/capitole.
    Dacă un articol e prea mare, fallback pe RecursiveCharacterTextSplitter.
    """

    def __init__(
        self,
        chunk_size: int = settings.chunk_size,
        chunk_overlap: int = settings.chunk_overlap,
        legal_aware: bool = settings.chunk_legal_aware,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.legal_aware = legal_aware

        # Fallback splitter din LangChain — separatori în ordine de prioritate
        self._fallback = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=[
                "\n\n",     # paragrafe
                "\n",        # linii
                ". ",        # propoziții
                "; ",        # clauze
                ", ",        # virgule
                " ",         # cuvinte
                "",          # caracter (ultimul resort)
            ],
        )

    # ── Segmentare după articole ─────────────────────────────────────────────

    def _split_by_articles(self, text: str) -> List[str]:
        """
        Împarte textul în segmente, fiecare începând cu un "Articol N".
        Dacă textul nu conține articole, returnează lista cu textul întreg.
        """
        # Găsim toate pozițiile unde începe un articol
        matches = list(RE_ARTICLE.finditer(text))
        if not matches:
            return [text]

        segments: List[str] = []

        # Text înainte de primul articol (preambul, capitol header etc.)
        if matches[0].start() > 50:
            preamble = text[: matches[0].start()].strip()
            if preamble:
                segments.append(preamble)

        # Fiecare articol = de la start până la următorul articol
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            segment = text[start:end].strip()
            if segment:
                segments.append(segment)

        return segments

    # ── Public API ───────────────────────────────────────────────────────────

    def chunk(self, text: str, source: str, page: int = 1) -> List[Chunk]:
        """
        Returnează lista de Chunk-uri pentru un text dat.

        Algoritm:
          1. Dacă legal_aware=True și textul conține articole → segmentăm pe articole.
          2. Dacă un segment depășește chunk_size → îl tăiem cu fallback.
          3. Eliminăm chunk-urile foarte scurte (< 40 caractere).
        """
        text = text.strip()
        if not text:
            return []

        # Strategia 1: segmentare după articole
        if self.legal_aware:
            segments = self._split_by_articles(text)
        else:
            segments = [text]

        chunks: List[Chunk] = []
        chunk_idx = 0

        for segment in segments:
            # Dacă segmentul încape integral într-un chunk → îl păstrăm întreg
            if len(segment) <= self.chunk_size:
                if len(segment) >= 40:
                    chunks.append(Chunk(
                        text=segment,
                        source=source,
                        page=page,
                        section=detect_section(segment),
                        chunk_index=chunk_idx,
                    ))
                    chunk_idx += 1
                continue

            # Altfel, segmentul e prea mare → folosim fallback
            sub_chunks = self._fallback.split_text(segment)
            section_label = detect_section(segment)  # eticheta articolului

            for sub in sub_chunks:
                sub = sub.strip()
                if len(sub) >= 40:
                    chunks.append(Chunk(
                        text=sub,
                        source=source,
                        page=page,
                        # subchunk-urile moștenesc eticheta articolului-părinte
                        section=detect_section(sub) or section_label,
                        chunk_index=chunk_idx,
                    ))
                    chunk_idx += 1

        logger.debug(
            "Chunking {}: {} fragmente generate (legal_aware={})",
            source, len(chunks), self.legal_aware,
        )
        return chunks


# Instanță globală pentru reutilizare
default_chunker = LegalAwareChunker()
