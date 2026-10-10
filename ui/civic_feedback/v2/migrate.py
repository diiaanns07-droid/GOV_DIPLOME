"""Миграция сообщений v1 (таблица feedback_messages, раунды 11–13) в записи v2.

Без потерь:
  * таблицы v1 НЕ изменяются и не удаляются (миграция только читает их);
  * каждая строка v1 целиком (все колонки + её события feedback_events) кладётся в record["legacy"];
  * повторный запуск ничего не дублирует (ключ — legacy_v1_id).
Строка без координат и без геометрии объекта в v2 не переносится (точку выдумывать нельзя —
точность карты важнее), она перечисляется в отчёте skipped_no_location и остаётся в v1.

Соответствие статусов (v1 -> v2):
  модерация rejected -> rejected;
  handling new -> new; in_review -> accepted; answered -> accepted (ответ дан, но «исправлено» не доказано);
  closed -> accepted + legacy.needs_review (закрыто ≠ исправлено: решает сотрудник);
  duplicate -> статус по исходной логике + duplicate_of = id исходной записи v2.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from . import categories
from . import record as rec
from .store import ComplaintStore

HANDLING_TO_V2 = {"new": "new", "in_review": "accepted", "answered": "accepted",
                  "closed": "accepted", "duplicate": "accepted"}


def v2_id(public_id: str) -> str:
    """Детерминированный id: повторная миграция даёт тот же id."""
    return "c-v1" + hashlib.sha256(public_id.encode()).hexdigest()[:16]


def _status(moderation: str | None, handling: str | None) -> str:
    if moderation == "rejected":
        return "rejected"
    return HANDLING_TO_V2.get(handling or "new", "new")


def _snapshot_point(snapshot) -> list[float] | None:
    """Первая точка геометрии объекта из снимка v3 (если у строки нет своей точки)."""
    if not isinstance(snapshot, dict):
        return None
    geometry = snapshot.get("geometry") or {}
    coords = geometry.get("coordinates")
    while isinstance(coords, list) and coords and isinstance(coords[0], list):
        coords = coords[0]
    if isinstance(coords, list) and len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
        return [float(coords[0]), float(coords[1])]
    return None


def row_to_v2(row: dict, events: list[dict], *, demo: bool = True) -> dict | None:
    """Одна строка v1 (dict всех колонок) -> запись v2 или None, если места нет.
    Чистая функция: тестируется без БД."""
    snapshot = None
    if row.get("object_snapshot"):
        try:
            snapshot = json.loads(row["object_snapshot"])
        except ValueError:
            snapshot = None
    point = None
    if row.get("lon") is not None and row.get("lat") is not None:
        point = [float(row["lon"]), float(row["lat"])]
    else:
        point = _snapshot_point(snapshot)
    if point is None:
        return None
    try:
        point = rec.parse_point(point)
    except rec.RecordError:
        return None

    if row.get("object_id"):
        target = rec.parse_target({"kind": "object", "id": row["object_id"],
                                   "label_ru": (snapshot or {}).get("title")}, legacy_ok=True)
    else:
        target = rec.cell_target(*point)

    created_at = rec.iso(rec.parse_iso(row["created_at"]))
    history = [{"at": created_at, "status": "new"}]
    for event in events:
        after = event.get("handling_after")
        moderation_after = event.get("moderation_after")
        if after is None and moderation_after is None:
            continue
        status = _status(moderation_after, after)
        if status != history[-1]["status"]:
            history.append({"at": rec.iso(rec.parse_iso(event["at"])), "status": status})
    status = _status(row.get("moderation"), row.get("handling_status"))
    if status != history[-1]["status"]:
        # События старых версий могли не хранить состояние после действия — фиксируем текущее.
        history.append({"at": rec.iso(rec.parse_iso(row.get("updated_at") or row["created_at"])), "status": status})

    staff_category = row.get("staff_category")
    category = categories.v1_to_v2(staff_category or row.get("category"))
    model = None
    if row.get("classifier_json"):
        try:
            hint = json.loads(row["classifier_json"])
        except ValueError:
            hint = None
        if isinstance(hint, dict) and hint.get("label"):
            # score v1 не калиброван и не хранился (раунд 13) — переносим только метку.
            model = {"label": categories.v1_to_v2(hint["label"]), "score": None,
                     "version": hint.get("model_version"), "needs_review": True}
    text = row.get("text") or ""
    lang = row.get("language") if row.get("language") in ("ru", "kk") else rec.detect_lang(text)
    legacy = {"v1_columns": dict(row), "v1_events": events}
    if row.get("handling_status") == "closed":
        legacy["needs_review"] = "v1: закрыто — проверьте, исправлено ли на месте"
    return {
        "id": v2_id(row["public_id"]),
        "code": None,
        "created_at": created_at,
        "text": text, "lang": lang,
        "category": category, "category_source": "staff" if staff_category else "resident",
        "model": model,
        "point": point, "target": target, "district": None,
        "status": status, "status_history": history,
        "metoo": 0, "duplicate_of": None,  # duplicate_of проставляется вторым проходом
        "demo": bool(demo),
        "due_at": rec.due_at(created_at, category),
        "schema": rec.SCHEMA,
        "legacy": legacy,
    }


def migrate(v1_db_path, store: ComplaintStore, *, demo: bool = True) -> dict:
    """Перенести все строки v1 в store. -> отчёт {total, migrated, already, skipped_no_location, duplicates}."""
    report = {"total": 0, "migrated": 0, "already": 0, "skipped_no_location": [], "duplicates": 0}
    path = Path(v1_db_path)
    if not path.exists():
        raise FileNotFoundError(f"Нет базы v1: {path}")
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "feedback_messages" not in tables:
            return report
        rows = [dict(r) for r in db.execute("SELECT * FROM feedback_messages ORDER BY id")]
        events_by_id: dict[int, list[dict]] = {}
        if "feedback_events" in tables:
            for event in db.execute("SELECT * FROM feedback_events ORDER BY id"):
                events_by_id.setdefault(event["feedback_id"], []).append(dict(event))
    finally:
        db.close()

    id_map = {}
    for row in rows:
        report["total"] += 1
        record = row_to_v2(row, events_by_id.get(row["id"], []), demo=demo)
        if record is None:
            report["skipped_no_location"].append(row["public_id"])
            continue
        id_map[row["id"]] = record["id"]
        if store.import_record(record, legacy_v1_id=row["id"]):
            report["migrated"] += 1
        else:
            report["already"] += 1
    # Второй проход: дубли v1 (duplicate_of — внутренний int id) -> mark_duplicate v2.
    for row in rows:
        original = id_map.get(row.get("duplicate_of"))
        duplicate = id_map.get(row["id"])
        if not original or not duplicate:
            continue
        current = store.get(duplicate)
        if current and not current.get("duplicate_of"):
            store.mark_duplicate(duplicate, original, actor="migration-v1")
            report["duplicates"] += 1
    return report
