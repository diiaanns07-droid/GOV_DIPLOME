"""Откуда табло берёт обращения. R17 жалобы не хранит и не меняет (CONTRACT §5.1, §7: только чтение у R09).

Порядок (первый доступный):
  1. configure(records=fn) — R01 передаёт функцию чтения того же экземпляра хранилища R09, что у шлюза;
  2. функция чтения R09 v2.1 для R17 (ui.civic_feedback.v2.agencies.<имя из R09_READERS>), когда R09 её поставит;
  3. хранилище R09 на той же SQLite (ComplaintStore(db_path).list) — те же записи, что видят «Обращения»;
  4. нет R09 в сборке — пусто (в демо-сборке — фикстура R17, fixture.py).
Фикстура в демо-сборке (CIVIC_DEMO=1) берётся и тогда, когда R09 ещё не умеет части служб и передачи (нет маршрута
complaints/{id}/handoff) и демо-мира нет (CIVIC_DEMO_WORLD не 1): иначе табло показывало бы одну службу из трёх
демо-жалоб шага 2. Ответ табло всегда говорит, откуда числа: source = r09 | fixture | none.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime

LOGGER = logging.getLogger("birge.agencies")
# Имена, под которыми R09 может отдать записи для табло (prompt R09, п. 2: «функции чтения для R17»).
R09_READERS = ("records_for_agencies", "agency_records", "records_for_board", "list_for_agencies")

_lock = threading.Lock()
_configured: dict = {"records": None}
_stores: dict = {}


def configure(records=None) -> None:
    """R01 (wire): records() -> список записей жалоб v2/v2.1 (полные записи, только чтение, без дублей)."""
    _configured["records"] = records if callable(records) else None


def r09_supports_parts() -> bool:
    """R09 уже поставил v2.1 (совместное исполнение и передачи)? Признак — маршрут complaints/{id}/handoff."""
    try:
        from ui.civic_feedback.v2 import integration  # type: ignore
    except Exception:  # noqa: BLE001
        return False
    return any(str(path).endswith("/handoff") for _method, path in getattr(integration, "ROUTES", ()) or ())


def _r09_reader():
    try:
        import importlib
        module = importlib.import_module("ui.civic_feedback.v2.agencies")
    except Exception:  # noqa: BLE001 — R09 ещё не поставил модуль чтения
        return None
    for name in R09_READERS:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    return None


def _r09_store(db_path: str):
    with _lock:
        if db_path in _stores:
            return _stores[db_path]
        store = None
        try:
            from ui.civic_feedback.v2.store import ComplaintStore  # type: ignore
            store = ComplaintStore(db_path)
        except Exception:  # noqa: BLE001 — нет R09 или база недоступна
            LOGGER.info("agencies: хранилище R09 недоступно, табло без обращений", exc_info=True)
        _stores[db_path] = store
        return store


def _flag(name: str) -> bool:
    return os.environ.get(name) == "1"


def load(db_path: str | None, *, now: datetime, demo: bool | None = None) -> tuple[list[dict], str]:
    """(записи, источник). Источник: r09 | fixture | none."""
    demo = _flag("CIVIC_DEMO") if demo is None else demo
    fn = _configured["records"]
    if fn is not None:
        try:
            return list(fn() or []), "r09"
        except Exception:  # noqa: BLE001
            LOGGER.exception("agencies: функция записей R01 упала — пробуем дальше")
    if demo and not _flag("CIVIC_DEMO_WORLD") and not r09_supports_parts():
        from .fixture import demo_records
        return demo_records(now), "fixture"
    reader = _r09_reader()
    if reader is not None:
        try:
            try:
                return list(reader(db_path) or []), "r09"
            except TypeError:
                return list(reader() or []), "r09"
        except Exception:  # noqa: BLE001
            LOGGER.exception("agencies: функция чтения R09 упала — читаем хранилище")
    store = _r09_store(db_path) if db_path else None
    if store is not None:
        try:
            return list(store.list()), "r09"
        except Exception:  # noqa: BLE001
            LOGGER.exception("agencies: хранилище R09 не прочиталось")
    if demo:
        from .fixture import demo_records
        return demo_records(now), "fixture"
    return [], "none"


def r08_lookup():
    """Таблица R08 «категория → служба» (с правками акимата) для старых записей без поля service."""
    try:
        from ui.civic_akim.routing import service_for  # type: ignore
        return service_for
    except Exception:  # noqa: BLE001
        return None


def pickups(db_path: str | None, district: str | None = None) -> list[dict]:
    """Задачи оператору вывоза после дел жителей, которые поддержал акимат (IDEA §2A: «задача оператору вывоза — R17»).

    Источник — R16 ui.civic_together.pickups(district, db_path) → [{initiative_id, service, title, point, district,
    target, starts_at, ends_at, note, supported_at, demo}] — только публичное (без жителей и устройств). Нет R16 — [].
    """
    try:
        from ui.civic_together import pickups as r16_pickups  # type: ignore
    except Exception:  # noqa: BLE001 — R16 нет в сборке
        return []
    try:
        rows = r16_pickups(district=district, db_path=db_path)
    except TypeError:
        try:
            rows = r16_pickups(district)
        except Exception:  # noqa: BLE001
            LOGGER.info("agencies: R16 pickups не прочитались", exc_info=True)
            return []
    except Exception:  # noqa: BLE001
        LOGGER.info("agencies: R16 pickups не прочитались", exc_info=True)
        return []
    out = []
    for row in rows or []:
        if not isinstance(row, dict) or not isinstance(row.get("service"), str):
            continue
        out.append({k: row.get(k) for k in ("initiative_id", "service", "title", "district", "target", "starts_at",
                                              "ends_at", "note", "demo")})
    return out
