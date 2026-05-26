"""
backend/logging_config.py
═════════════════════════
Configurația sistemului de logging cu Loguru.

Caracteristici:
  • output colorat în consolă (developer-friendly)
  • fișier rotativ zilnic în data/logs/app.log
  • fișier separat doar pentru erori (errors.log)
  • format structurat cu timestamp, level, modul, linie
  • rotație automată după mărime și retenție configurabilă
"""

import sys
from pathlib import Path
from loguru import logger

from backend.config import settings


def setup_logging() -> None:
    """Inițializează logger-ul global. Apelat o singură dată la pornire."""
    log_dir = settings.log_dir_abs
    log_dir.mkdir(parents=True, exist_ok=True)

    # Eliminăm handler-ul default (stderr necolorat)
    logger.remove()

    # ── Consolă (colorat) ─────────────────────────────────────────────────────
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}:{function}:{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # ── Fișier general (rotație zilnică, retenție 14 zile) ────────────────────
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        level=settings.log_level,
        rotation="00:00",  # roteste la miezul nopții
        retention=f"{settings.log_retention_days} days",
        compression="zip",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
        enqueue=True,  # thread-safe
    )

    # ── Fișier doar pentru erori (pentru audit rapid) ─────────────────────────
    logger.add(
        log_dir / "errors_{time:YYYY-MM-DD}.log",
        level="ERROR",
        rotation="10 MB",
        retention=f"{settings.log_retention_days} days",
        compression="zip",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}\n{exception}"
        ),
        backtrace=True,
        diagnose=True,
        enqueue=True,
    )

    logger.info("Sistem logging inițializat — nivel: {}", settings.log_level)


# Export direct pentru import facil
__all__ = ["logger", "setup_logging"]
