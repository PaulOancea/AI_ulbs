"""
backend/exceptions.py
═════════════════════
Ierarhia de excepții custom — fiecare cu cod HTTP recomandat și mesaj prietenos.

Tratarea defensivă:
  • orice excepție rezultă în răspuns JSON consistent
  • niciun stack trace nu ajunge la utilizator (doar în log-uri)
  • fiecare clasă are mesaj implicit în română
"""


class AppException(Exception):
    """Excepție de bază pentru tot ce ține de logica aplicației."""

    status_code: int = 500
    default_message: str = "A apărut o eroare neașteptată."

    def __init__(self, message: str | None = None, *, details: dict | None = None):
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)


class OllamaUnavailableError(AppException):
    """Serviciul Ollama nu răspunde sau nu rulează."""
    status_code = 503
    default_message = (
        "Serviciul Ollama nu este disponibil. "
        "Asigură-te că rulează cu comanda `ollama serve`."
    )


class ModelNotFoundError(AppException):
    """Modelul cerut nu e instalat în Ollama."""
    status_code = 404
    default_message = "Modelul cerut nu este instalat în Ollama."


class DocumentProcessingError(AppException):
    """Eroare la procesarea unui document (PDF/DOCX corupt etc.)."""
    status_code = 422
    default_message = "Documentul nu a putut fi procesat."


class EmptyContextError(AppException):
    """Nu s-au găsit fragmente relevante pentru întrebare."""
    status_code = 404
    default_message = (
        "Nu am găsit informații relevante în documentele indexate "
        "care să răspundă întrebării tale."
    )


class VectorStoreError(AppException):
    """Eroare la operațiile cu ChromaDB."""
    status_code = 500
    default_message = "Eroare la baza de date vectorială."


class InvalidQueryError(AppException):
    """Întrebarea utilizatorului e invalidă (goală, prea scurtă, etc.)."""
    status_code = 400
    default_message = "Întrebarea este invalidă. Te rog formulează clar."
