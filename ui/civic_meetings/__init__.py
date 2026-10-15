"""R13 · «Встречи с акимом» (раунд 15): встречи акима района с жителями, «Приду», вопросы заранее, поручения.

    from ui.civic_meetings import make_service
    service = make_service(".runtime/civic.sqlite3")          # та же база, что у шлюза R01 (таблицы mt_*)
    service.handle("GET", "/api/civic/v2/meetings", "when=upcoming", None, principal=None, context={...})
      -> {"status": 200, "headers": {}, "body": {"items": [...], "next_id": "m-…", ...}}

Функции для соседей (вызов в процессе, CONTRACT §7 «Вызовы между модулями»):
    updates(device, since, db_path=None)  -> [событие ленты §5.8]        — R06 «Что нового для меня»
    board_block(db_path=None, district=None) -> {"next", "orders", ...}    — R08 «Картина дня», Ситуационный центр, R03
    seed_world(db_path, records, now=None) -> {"inserted", "skipped"}     — R01 демо-мир (CONTRACT §11)

Маршруты, лимиты, экран и ключи словаря — research/round-15-results/R13/INTEGRATION.txt.
Экран — web/civic/meetings/meetings.js (window.BirgeMeetings, раздел оболочки #meetings).
"""

from __future__ import annotations

import os
import threading

from .service import MeetingService
from .service import make_service as _make_service
from .store import MeetingStore
from .world import seed_world

__all__ = ["MeetingService", "MeetingStore", "board_block", "make_service", "seed_world", "updates"]

# Последний сервис на каждую базу: соседи (R06, R08) зовут updates()/board_block() без своей копии сервиса.
_SERVICES: dict[str, MeetingService] = {}
_LOCK = threading.Lock()


def make_service(db_path, **options) -> MeetingService:
    service = _make_service(db_path, **options)
    with _LOCK:
        _SERVICES[str(db_path)] = service
    return service


def _service(db_path=None) -> MeetingService | None:
    """Сервис для вызова соседом: по db_path; иначе тот, что создал шлюз; иначе по CIVIC_DB_PATH. Нет — None."""
    with _LOCK:
        if db_path is not None and str(db_path) in _SERVICES:
            return _SERVICES[str(db_path)]
        if db_path is None and _SERVICES:
            return next(reversed(_SERVICES.values()))
    path = db_path or os.environ.get("CIVIC_DB_PATH")
    if not path:
        return None
    try:
        return make_service(path, demo=False)
    except Exception:
        return None


def updates(device, since=None, *, db_path=None, limit: int = 50) -> list[dict]:
    """События ленты (CONTRACT §5.8) для устройства жителя после since (ISO). Модуль не готов — пустой список."""
    service = _service(db_path)
    if service is None:
        return []
    try:
        return service.updates(device, since, limit=limit)
    except Exception:
        return []


def board_block(db_path=None, *, district=None, limit: int = 5) -> dict | None:
    """Блок «Встречи» для R08/R03: ближайшая встреча и открытые поручения со сроком. Нет данных — None."""
    service = _service(db_path)
    if service is None:
        return None
    try:
        return service.board_block(district=district, limit=limit)
    except Exception:
        return None
