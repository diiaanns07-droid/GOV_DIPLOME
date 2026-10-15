"""Чтение жалоб для R17 «Штаб ведомств» (CONTRACT §7: R17 читает R09 — части служб и передачи, только чтение).

    from ui.civic_feedback.v2.agencies import records_for_agencies
    records = records_for_agencies(db_path)      # путь к SQLite (CIVIC_DB_PATH), хранилище/сервис R09 или None

Запись v2.1 без того, что табло не нужно и что может быть личным: нет текста жителя, точки, фото, устройств, заметок
сотрудников. Ведущая служба и части — те же, что в «Обращениях» (joint.parts: явная → паспорт → таблица R08 → R09),
поэтому числа табло R17 = числа «Обращений» R09. Имя модуля и функции — из R17 ui/civic_agencies/sources.py
(R09_READERS); agency_records — то же самое.
"""

from __future__ import annotations

from . import joint
from .integration import _store

# Поля, которые читает табло R17 (ui/civic_agencies/metrics.py): статусы, сроки, район, категория, службы, передачи.
KEEP = ("id", "code", "created_at", "category", "subtopic", "district", "status", "status_history", "due_at",
        "duplicate_of", "demo", "metoo", "handoffs", "route_hint", "event", "scene", "schema")
TARGET_KEEP = ("kind", "id", "label_ru", "label_kk", "approximate", "object_kind")


def _resolution(record: dict) -> dict | None:
    resolution = record.get("resolution")
    if not isinstance(resolution, dict):
        return None
    # Без «кто» и фото «после»: табло считает состояния и голоса, а не людей.
    return {k: resolution.get(k) for k in ("round", "state", "reported_at", "verified_at", "reopened_at",
                                            "reopen_count", "votes")}


def agency_view(record: dict, assignee_lookup=None) -> dict:
    """Одна запись для табло: служебные поля + ведущая служба и части (как в «Обращениях»)."""
    view = {key: record.get(key) for key in KEEP if key in record}
    view["status_history"] = [{"at": h.get("at"), "status": h.get("status"),
                               **({"reopened_by_residents": True} if h.get("reopened_by_residents") else {})}
                              for h in record.get("status_history") or []]
    view["target"] = {k: v for k, v in (record.get("target") or {}).items() if k in TARGET_KEEP}
    items = joint.parts(record, assignee_lookup)
    view["service"] = items[0]["service"] if items else record.get("service")
    view["services"] = [{"service": p["service"], "role": p["role"], "status": p["status"],
                         "updated_at": p.get("updated_at")} for p in items]
    view["joint"] = len(items) > 1
    view["handoffs"] = [{k: h.get(k) for k in ("at", "from", "to", "reason", "reason_code", "by_role")}
                        for h in record.get("handoffs") or []]
    view["passport"] = {"assignee_id": view["service"]}
    view["answered_at"] = joint.answer_at(record)
    view["reporters"] = 1 + int(record.get("metoo") or 0)
    resolution = _resolution(record)
    if resolution is not None:
        view["resolution"] = resolution
    return view


def records_for_agencies(db=None, *, include_duplicates: bool = True) -> list[dict]:
    """Все жалобы хранилища R09 для табло R17 (дубли — с duplicate_of: табло само их не считает)."""
    store = _store(db)
    return [agency_view(record, store.assignee_lookup)
            for record in store.list(include_duplicates=include_duplicates, limit=store.limits["list_max"])]


agency_records = records_for_agencies
