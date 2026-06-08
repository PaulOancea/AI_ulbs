"""
scripts/sync_exams.py
═════════════════════
Descarcă examenele (ULBS Connect) pentru fiecare grupă și le salvează local în
`data/schedule/exams.json`.

Utilizare:
    python -m scripts.sync_exams

Configurare (din .env):
    EXAMS_API_URL=https://connect.ulbsibiu.ro/api/schedule/faculties/ing/exams
    EXAMS_FACULTY=ing
    EXAMS_PLANNING_TIME_UNIT_ID=5
    EXAMS_START_DATE=2026-03-02
    EXAMS_END_DATE=2026-09-30
    EXAMS_PER_PAGE=300
    EXAMS_STUDY_FORMATIONS=C_31,C_32,TI_31,ISM_31

Endpoint-ul e apelat SEPARAT pentru fiecare grupă (parametrul study_formation),
cu cerere simplă `requests.get()` (fără cookies, fără Authorization, fără
Origin/Referer). Suportă paginare prin câmpul `pagination.last_page`.

Rezultatul salvat: { "C_31": [examene...], "C_32": [...], ... }
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from backend.config import settings
from backend.logging_config import logger, setup_logging

_WITH = "professor,assistant,examRoom,studyFormation,type,session"


def fetch_group_exams(study_formation: str) -> list:
    """Descarcă TOATE examenele unei grupe (cu paginare)."""
    all_exams: list = []
    page = 1
    while True:
        params = {
            "planning_time_unit_id": settings.exams_planning_time_unit_id,
            "page": page,
            "per_page": settings.exams_per_page,
            "start_date": settings.exams_start_date,
            "end_date": settings.exams_end_date,
            "study_formation": study_formation,
            "with": _WITH,
        }
        resp = requests.get(settings.exams_api_url, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        data = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(data, list):
            data = []
        all_exams.extend(data)

        # Paginare: dacă există last_page, mergem până la ea; altfel oprim când
        # pagina curentă nu mai întoarce rezultate.
        pagination = payload.get("pagination") if isinstance(payload, dict) else None
        last_page = pagination.get("last_page") if isinstance(pagination, dict) else None
        if last_page is not None:
            if page >= int(last_page):
                break
        elif not data:
            break
        page += 1

    return all_exams


def main() -> int:
    setup_logging()
    groups = settings.exams_study_formation_list

    logger.info("=== Sincronizare examene pornită === ({} grupe)", len(groups))
    result: dict = {}
    errors = []

    for group in groups:
        print(f"GET  [{group}]  {settings.exams_api_url}?study_formation={group}")
        try:
            exams = fetch_group_exams(group)
            result[group] = exams
            logger.info("Examene descărcate pentru {}: {}", group, len(exams))
        except Exception as exc:
            logger.error("Eroare la grupa {}: {}", group, exc)
            errors.append(f"{group}: {exc}")

    if not result:
        print("❌ Nu s-au descărcat examene.")
        for e in errors:
            print("  •", e)
        return 1

    dest = settings.exams_data_path_abs
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(len(v) for v in result.values())
    print(f"\n✅ Salvat {total} examene ({len(result)} grupe) în {dest}")
    if errors:
        print("Erori:")
        for e in errors:
            print("  •", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
