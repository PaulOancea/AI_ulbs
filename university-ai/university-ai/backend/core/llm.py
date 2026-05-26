"""
backend/core/llm.py
═══════════════════
Wrapper peste Ollama API cu:
  • detectare disponibilitate (`is_alive`, `list_models`);
  • generare sincronă (`generate`);
  • generare streaming sincronă (`stream`) — pentru Streamlit;
  • generare streaming async (`astream`) — pentru FastAPI WebSocket.

Toate funcțiile gestionează defensiv:
  • ConnectionError → OllamaUnavailableError
  • Timeout → mesaj prietenos
  • Modele lipsă → ModelNotFoundError
"""

import json
from typing import AsyncGenerator, Generator, List

import httpx
import requests

from backend.config import settings
from backend.exceptions import OllamaUnavailableError, ModelNotFoundError
from backend.logging_config import logger


# ── Status & lista modele ─────────────────────────────────────────────────────

def is_alive() -> bool:
    """Verifică rapid dacă Ollama răspunde."""
    try:
        r = requests.get(settings.ollama_tags_url, timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def list_models() -> List[str]:
    """Listează modelele instalate în Ollama."""
    try:
        r = requests.get(settings.ollama_tags_url, timeout=3)
        if r.status_code != 200:
            return []
        return [m["name"] for m in r.json().get("models", [])]
    except Exception as exc:
        logger.debug("list_models: {}", exc)
        return []


def _ollama_options(temperature: float = None) -> dict:
    """Returnează dict-ul de opțiuni standard pentru Ollama."""
    return {
        "temperature": temperature if temperature is not None else settings.ollama_temperature,
        "top_p": settings.ollama_top_p,
        "num_predict": settings.ollama_num_predict,
        "repeat_penalty": settings.ollama_repeat_penalty,
    }


# ── Generare sincronă (non-streaming) ─────────────────────────────────────────

def generate(prompt: str, model: str = None, temperature: float = None) -> str:
    """Generează răspuns complet (folosit pentru query rewriting)."""
    model = model or settings.ollama_model
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": _ollama_options(temperature),
    }

    try:
        r = requests.post(
            settings.ollama_generate_url,
            json=payload,
            timeout=settings.ollama_timeout,
        )
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except requests.exceptions.ConnectionError as exc:
        logger.error("Ollama nu răspunde: {}", exc)
        raise OllamaUnavailableError() from exc
    except requests.exceptions.HTTPError as exc:
        if r.status_code == 404:
            raise ModelNotFoundError(
                f"Modelul '{model}' nu este instalat. "
                f"Rulează: `ollama pull {model}`"
            ) from exc
        logger.exception("Eroare HTTP Ollama")
        raise OllamaUnavailableError(f"Ollama a întors HTTP {r.status_code}") from exc
    except requests.exceptions.Timeout as exc:
        logger.error("Timeout Ollama după {}s", settings.ollama_timeout)
        raise OllamaUnavailableError(
            "Ollama nu a răspuns în timp util. "
            "Încercați un model mai mic sau verificați resursele sistemului."
        ) from exc


# ── Streaming sincron (pentru Streamlit, generator clasic) ────────────────────

def stream(prompt: str, model: str = None) -> Generator[str, None, None]:
    """
    Streaming generator clasic — produce token cu token.
    Streamlit-ul consumă cu `for token in stream(...):`.
    """
    model = model or settings.ollama_model
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": _ollama_options(),
    }

    try:
        with requests.post(
            settings.ollama_generate_url,
            json=payload,
            stream=True,
            timeout=settings.ollama_timeout,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = data.get("response", "")
                if token:
                    yield token
                if data.get("done"):
                    return

    except requests.exceptions.ConnectionError as exc:
        raise OllamaUnavailableError() from exc
    except requests.exceptions.HTTPError as exc:
        if r.status_code == 404:
            raise ModelNotFoundError(f"Modelul '{model}' nu este instalat.") from exc
        raise OllamaUnavailableError(f"HTTP {r.status_code}") from exc
    except requests.exceptions.Timeout as exc:
        raise OllamaUnavailableError("Timeout la generarea răspunsului.") from exc


# ── Streaming async (pentru FastAPI WebSocket) ────────────────────────────────

async def astream(prompt: str, model: str = None) -> AsyncGenerator[str, None]:
    """
    Streaming async pentru WebSocket-uri FastAPI.
    """
    model = model or settings.ollama_model
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": _ollama_options(),
    }

    timeout = httpx.Timeout(settings.ollama_timeout, connect=5.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", settings.ollama_generate_url, json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = data.get("response", "")
                    if token:
                        yield token
                    if data.get("done"):
                        return

    except httpx.ConnectError as exc:
        raise OllamaUnavailableError() from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ModelNotFoundError(f"Modelul '{model}' nu este instalat.") from exc
        raise OllamaUnavailableError(f"HTTP {exc.response.status_code}") from exc
    except httpx.TimeoutException as exc:
        raise OllamaUnavailableError("Timeout la generarea răspunsului.") from exc
