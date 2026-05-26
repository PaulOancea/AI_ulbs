"""
scripts/ingest.py
═════════════════
Script CLI pentru indexare automată a unui folder de documente.

Utilizare:
    python -m scripts.ingest                          # indexează folderul default
    python -m scripts.ingest --folder ./documente     # folder explicit
    python -m scripts.ingest --force                  # re-indexează tot
    python -m scripts.ingest --reset                  # resetează DB înainte
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings
from backend.core.ingestion import IngestionService
from backend.core.vector_store import VectorStore
from backend.logging_config import logger, setup_logging


def main():
    parser = argparse.ArgumentParser(description="Indexare documente universitare")
    parser.add_argument("--folder", default=settings.docs_folder, help="Folder cu PDF/DOCX/TXT")
    parser.add_argument("--force", action="store_true", help="Re-indexează chiar dacă există")
    parser.add_argument("--reset", action="store_true", help="Resetează DB înainte de ingestie")
    args = parser.parse_args()

    setup_logging()
    logger.info("=== Script ingestie pornit ===")

    vs = VectorStore()
    if args.reset:
        logger.warning("Resetez baza vectorială...")
        vs.clear_all()

    service = IngestionService(vs)
    result = service.ingest_folder(args.folder, force=args.force)

    print()
    print("=" * 60)
    print(f"  Fișiere procesate:  {result['files_processed']}")
    print(f"  Sărite (deja indexate): {result['skipped']}")
    print(f"  Fragmente adăugate: {result['chunks_added']}")
    print(f"  Erori:              {len(result['errors'])}")
    print("=" * 60)

    if result["errors"]:
        print("\nErori detaliate:")
        for e in result["errors"]:
            print(f"  • {e}")

    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
