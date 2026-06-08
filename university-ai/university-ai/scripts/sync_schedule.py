"""
scripts/sync_schedule.py
════════════════════════
Descarcă orarul grupei (grupelor) din API-ul public schedule.ulbsibiu.ro și îl
salvează local în `data/schedule/schedule.json`.

Utilizare:
    python -m scripts.sync_schedule

Configurare (din .env):
    SCHEDULE_FACULTY=ing
    SCHEDULE_PLANNING_TIME_UNIT_ID=5
    SCHEDULE_FORMATION_IDS=541            # mai multe: 541,562,563
    DEFAULT_SCHEDULE_FORMATION_ID=541

URL-ul construit (exemplu):
    https://schedule.ulbsibiu.ro/api/faculties/ing/study-formations/541/schedule?planning_time_unit_id=5

Notă: cerere simplă cu requests.get(), fără cookies din cURL și fără header
`Authorization: Bearer` (este gol).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from backend.config import settings
from backend.core.schedule_service import load_formation_map
from backend.logging_config import logger, setup_logging


def build_url(faculty: str, formation_id: str, planning_time_unit_id) -> str:
    base = settings.schedule_base_url.rstrip("/")
    return (
        f"{base}/faculties/{faculty}/study-formations/{formation_id}"
        f"/schedule?planning_time_unit_id={planning_time_unit_id}"
    )


def _id_to_label(formation_map: dict) -> dict:
    """{formation_id(str): 'C_31/1'} — etichetă prietenoasă pentru loguri."""
    return {
        str(fid): f"{group}/{sub}"
        for group, subs in formation_map.items()
        for sub, fid in subs.items()
    }


def main() -> int:
    setup_logging()
    faculty = settings.schedule_faculty
    ptu = settings.schedule_planning_time_unit_id
    ids = settings.schedule_formation_id_list
    labels = _id_to_label(load_formation_map())

    logger.info("=== Sincronizare orar pornită === ({} formații)", len(ids))
    result: dict = {}
    errors = []

    for fid in ids:
        label = labels.get(str(fid), "?")
        url = build_url(faculty, fid, ptu)
        print(f"GET  [{label}]  {url}")
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            result[str(fid)] = resp.json()
            logger.info("Orar descărcat pentru formația {} ({})", fid, label)
        except Exception as exc:
            logger.error("Eroare la formația {} ({}): {}", fid, label, exc)
            errors.append(f"{fid} ({label}): {exc}")

    if not result:
        print("❌ Nu s-a descărcat niciun orar.")
        for e in errors:
            print("  •", e)
        return 1

    dest = settings.schedule_data_path_abs
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ Salvat {len(result)} formație(i) în {dest}")
    if errors:
        print("Erori:")
        for e in errors:
            print("  •", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
