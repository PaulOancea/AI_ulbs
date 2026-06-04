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
        "repeat_last_n": settings.ollama_repeat_last_n,
    }


def _ollama_error_detail(resp) -> str:
    """Extrage mesajul de eroare din corpul răspunsului Ollama (dacă există)."""
    try:
        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            return str(data["error"])
    except Exception:
        pass
    try:
        return (resp.text or "").strip()[:300]
    except Exception:
        return ""


def _friendly_ollama_error(status: int, detail: str) -> str:
    """Transformă o eroare HTTP Ollama într-un mesaj clar, acționabil (RO)."""
    d = (detail or "").lower()
    if "memory" in d or "out of memory" in d or "too large" in d:
        return (
            "Modelul este prea mare pentru memoria RAM disponibilă. "
            "Folosește un model mai mic — de ex. rulează ollama pull llama3.2:3b "
            "și selectează-l din Panou administrare -> Model AI (sau setează "
            "OLLAMA_MODEL=llama3.2:3b în .env). Poți și să închizi alte aplicații "
            "ori să dezactivezi reranker-ul (RERANKER_ENABLED=false) pentru a elibera memorie."
        )
    if detail:
        return f"Ollama a întors o eroare (HTTP {status}): {detail}"
    return f"Ollama a întors HTTP {status}."


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
            timeout=(settings.ollama_connect_timeout, settings.ollama_timeout),
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
        detail = _ollama_error_detail(r)
        logger.error("Eroare HTTP Ollama {}: {}", r.status_code, detail)
        raise OllamaUnavailableError(
            _friendly_ollama_error(r.status_code, detail)
        ) from exc
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
            timeout=(settings.ollama_connect_timeout, settings.ollama_timeout),
        ) as r:
            # Verificăm statusul explicit cât timp răspunsul e încă deschis, ca să
            # putem citi corpul erorii (ex: „model requires more system memory").
            if r.status_code != 200:
                if r.status_code == 404:
                    raise ModelNotFoundError(
                        f"Modelul '{model}' nu este instalat. "
                        f"Rulează: `ollama pull {model}`"
                    )
                detail = _ollama_error_detail(r)
                logger.error("Eroare HTTP Ollama {}: {}", r.status_code, detail)
                raise OllamaUnavailableError(
                    _friendly_ollama_error(r.status_code, detail)
                )
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
    except requests.exceptions.Timeout as exc:
        raise OllamaUnavailableError(
            "Modelul a depășit timpul de generare. Pe CPU, modelele 7–8B sunt lente, "
            "mai ales dacă RAM-ul e insuficient (modelul intră în swap). "
            "Soluții: folosește un model mai mic (ex. llama3.2:3b), eliberează memorie "
            "închizând alte aplicații, sau mărește OLLAMA_TIMEOUT în .env."
        ) from exc


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
