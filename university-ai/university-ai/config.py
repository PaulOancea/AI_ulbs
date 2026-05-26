"""
config.py — shim de compatibilitate

Acest fișier a fost înlocuit de `backend/config.py` (Pydantic Settings).
Îl păstrăm doar pentru cod legacy care face `from config import OLLAMA_MODEL`.
"""

from backend.config import settings

# Re-export constante pentru API legacy
EMBED_MODEL = settings.embed_model
OLLAMA_MODEL = settings.ollama_model
OLLAMA_URL = settings.ollama_generate_url
CHROMA_PATH = settings.chroma_path
COLLECTION_NAME = settings.collection_name
CHUNK_SIZE = settings.chunk_size
CHUNK_OVERLAP = settings.chunk_overlap
TOP_K = settings.final_top_k
MIN_SCORE = settings.min_score
DOCS_FOLDER = settings.docs_folder
