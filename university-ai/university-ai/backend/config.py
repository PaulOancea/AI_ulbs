"""
backend/config.py
═════════════════
Configurația centralizată a aplicației, validată prin Pydantic Settings.

Avantaje față de constante hard-coded:
  • toate valorile pot fi suprascrise prin variabile de mediu sau fișier .env
  • validare automată de tipuri (int, float, bool, listă)
  • o singură sursă de adevăr — restul codului importă obiectul `settings`
"""

from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Toate parametrii configurabili ai sistemului."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Ollama LLM ────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout: int = 180
    ollama_temperature: float = 0.1
    ollama_top_p: float = 0.9
    ollama_num_predict: int = 2000
    ollama_repeat_penalty: float = 1.1

    # ── Embeddings ────────────────────────────────────────────────────────────
    embed_model: str = "paraphrase-multilingual-mpnet-base-v2"
    embed_device: str = "cpu"  # "cuda" dacă există GPU

    # ── Reranker ──────────────────────────────────────────────────────────────
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_top_n: int = 5
    reranker_enabled: bool = True
    # Prag RELATIV de relevanță aplicat după rerank: păstrăm un fragment doar
    # dacă scorul lui ≥ ratio × scorul celui mai bun fragment. Astfel evităm
    # afișarea surselor irelevante (fragmente cu scor mult sub vârf).
    # 0.0 = păstrează tot (top_n); 1.0 = doar fragmentele la egalitate cu vârful.
    rerank_keep_ratio: float = 0.5

    # ── ChromaDB ──────────────────────────────────────────────────────────────
    chroma_path: str = "./data/chroma_db"
    collection_name: str = "university_docs"

    # ── Chunking ──────────────────────────────────────────────────────────────
    chunk_size: int = 900
    chunk_overlap: int = 150
    chunk_legal_aware: bool = True

    # ── Retrieval ─────────────────────────────────────────────────────────────
    retrieval_top_k: int = 20  # câte rezultate brute din fiecare retriever
    final_top_k: int = 5       # câte ajung în prompt după rerank
    min_score: float = 0.20
    hybrid_alpha: float = 0.5  # 0=BM25 pur, 1=dense pur

    # ── Memorie conversațională ───────────────────────────────────────────────
    memory_window: int = 6
    memory_enabled: bool = True

    # ── Loguri ────────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_dir: str = "./data/logs"
    log_retention_days: int = 14

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:8501"])

    # ── Documente ─────────────────────────────────────────────────────────────
    docs_folder: str = "./documente"

    # ── OCR (PDF-uri scanate + imagini) ──────────────────────────────────────
    ocr_enabled: bool = True
    ocr_languages: str = "ron+eng"     # Tesseract: ex. "ron+eng+fra"
    ocr_dpi: int = 300                  # rezoluție rasterizare PDF
    ocr_min_text_threshold: int = 50   # sub atâtea caractere → declanșăm OCR
    # Cale spre binarul Tesseract; gol = caut automat în PATH
    # Windows tipic: "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
    tesseract_cmd: str = ""

    # ── Autentificare + istoric chat ─────────────────────────────────────────
    auth_enabled: bool = True
    database_path: str = "./data/app.db"
    guest_question_limit: int = 3       # întrebări permise fără cont
    password_min_length: int = 6
    session_secret: str = "change-me-in-production-please-very-secret"
    # Utilizatorii (username) cu drepturi de administrator — văd panoul tehnic
    # (status sistem, încărcare documente, selector model etc.). CSV în .env.
    admin_usernames: List[str] = Field(default_factory=lambda: ["admin"])

    # ── Validatori ────────────────────────────────────────────────────────────

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors(cls, v):
        """Permite specificarea CORS prin string CSV în .env."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("admin_usernames", mode="before")
    @classmethod
    def split_admins(cls, v):
        """Permite specificarea adminilor prin string CSV în .env."""
        if isinstance(v, str):
            return [u.strip() for u in v.split(",") if u.strip()]
        return v

    @field_validator("hybrid_alpha")
    @classmethod
    def validate_alpha(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("hybrid_alpha trebuie să fie între 0 și 1")
        return v

    # ── Proprietăți derivate ──────────────────────────────────────────────────

    @property
    def chroma_path_abs(self) -> Path:
        return Path(self.chroma_path).resolve()

    @property
    def log_dir_abs(self) -> Path:
        return Path(self.log_dir).resolve()

    @property
    def docs_folder_abs(self) -> Path:
        return Path(self.docs_folder).resolve()

    @property
    def database_path_abs(self) -> Path:
        return Path(self.database_path).resolve()

    @property
    def ollama_generate_url(self) -> str:
        return f"{self.ollama_base_url.rstrip('/')}/api/generate"

    @property
    def ollama_tags_url(self) -> str:
        return f"{self.ollama_base_url.rstrip('/')}/api/tags"


# Singleton — importat în tot proiectul
settings = Settings()

# Asigurăm că folderele există încă de la inițializare
settings.chroma_path_abs.mkdir(parents=True, exist_ok=True)
settings.log_dir_abs.mkdir(parents=True, exist_ok=True)
settings.docs_folder_abs.mkdir(parents=True, exist_ok=True)
settings.database_path_abs.parent.mkdir(parents=True, exist_ok=True)
