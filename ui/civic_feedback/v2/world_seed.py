"""Демо-мир R02 в хранилище жалоб R09 (раунд 15, CONTRACT §11): seed_world(db_path, records, now=None).

R01 вызывает при CIVIC_DEMO=1 и CIVIC_DEMO_WORLD=1 (data/civic/astana/demo-world/world_v1.json) — тогда карта R07,
«Картина дня» R08, табло служб R17 и «Мой двор» R16 считают из одних и тех же жалоб, а «Обращения» сотрудника
показывают те же числа. Без флага — прежнее демо FINAL-4 (seed_demo: две жалобы «Хан Шатыр» шага 2 — остаются всегда).

Что берётся из мира: complaints (или records как список жалоб). Каждая жалоба — формат CONTRACT §5 / §5.1, время —
ОТНОСИТЕЛЬНО МОМЕНТА ЗАСЕВА: у самой жалобы ago_days / ago_hours / ago_minutes (или created_at), у шагов истории,
частей служб, передач и «Я тоже» — так же (ago_* или at). Числа «Я тоже» — metoo (число) или metoo_ago (список).

Правила:
  * идемпотентно: повтор ничего не дублирует (id записи детерминирован из id мира); reset=True — записи мира
    возвращаются в исходное состояние со временем от этого засева (репетиция не «съедает» сцену, как R10 B-048);
  * всё синтетическое: demo: true («Пример» на экране), устройства «Я тоже» — хэши фиксированных строк;
  * срок ответа считается кодом (рабочие дни РК), не берётся из файла; служба — из мира (service_source «world»);
  * неверная запись (категория, место вне Астаны, цель) не ломает засев — она в отчёте invalid с причиной.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from . import categories, joint, lifecycle
from . import record as rec

WORLD_PREFIX = "c-w"
MAX_METOO = 400          # защита от опечатки в генераторе (одна цель — не больше 400 «Я тоже»)


class WorldError(ValueError):
    pass


def world_id(source_id) -> str:
    """id записи R09 для жалобы мира: свой id c-… (если подходит) или детерминированный c-w<хэш>."""
    if isinstance(source_id, str) and rec.COMPLAINT_ID.match(source_id):
        return source_id
    return WORLD_PREFIX + hashlib.sha256(f"r09-world:{source_id}".encode("utf-8")).hexdigest()[:16]


def _device(cid: str, n: int) -> str:
    # Синтетическое «устройство» n-го «Я тоже» — хэш фиксированной строки (как у demo_seed), не чьё-то устройство.
    return hashlib.sha256(f"r09-world-device:{cid}:{n}".encode("utf-8")).hexdigest()


def _now(value) -> datetime:
    if value is None:
        return datetime.now(rec.ASTANA_TZ)
    if isinstance(value, str):
        moment = rec.parse_iso(value)
        if moment is None:
            raise WorldError("now — ISO-время")
        return moment
    return value if value.tzinfo else value.replace(tzinfo=rec.ASTANA_TZ)


def _ago(item: dict) -> timedelta | None:
    if not isinstance(item, dict):
        return None
    keys = {"ago_days": "days", "ago_hours": "hours", "ago_minutes": "minutes"}
    found = {name: item[key] for key, name in keys.items()
             if isinstance(item.get(key), (int, float)) and not isinstance(item.get(key), bool)}
    return timedelta(**found) if found else None


def _moment(item, now: datetime, default: datetime | None = None, *, key: str = "at") -> datetime | None:
    """Время шага: at (ISO) → ago_* от момента засева → default. Будущее время мира обрезается до «сейчас»."""
    moment = None
    if isinstance(item, dict) and isinstance(item.get(key), str):
        moment = rec.parse_iso(item[key])
    if moment is None:
        delta = _ago(item)
        moment = now - delta if delta is not None else default
    if moment is not None and moment > now:
        moment = now
    return moment


def _complaints(records) -> list[dict]:
    if isinstance(records, (str, Path)):
        records = json.loads(Path(records).read_text(encoding="utf-8"))
    if isinstance(records, dict):
        records = records.get("complaints") or []
    if not isinstance(records, list):
        raise WorldError("Ожидается мир R02 (объект с complaints) или список жалоб.")
    return [item for item in records if isinstance(item, dict)]


def _history(item: dict, status: str, created: datetime, now: datetime) -> list[dict]:
    """Шаги статуса: из мира (по времени, первый — «new» в момент подачи) или правдоподобные по статусу."""
    out = [{"at": rec.iso(created), "status": "new"}]
    given = item.get("status_history")
    if isinstance(given, list) and given:
        steps = []
        for entry in given:
            st = entry.get("status") if isinstance(entry, dict) else None
            if st not in rec.STATUSES:
                continue
            moment = _moment(entry, now, created)
            if moment is None or moment < created:
                moment = created
            steps.append((moment, st, entry))
        steps.sort(key=lambda s: s[0])
        for moment, st, entry in steps:
            if st == out[-1]["status"]:
                continue
            step = {"at": rec.iso(moment), "status": st}
            if entry.get("reopened_by_residents") is True:
                step["reopened_by_residents"] = True
            out.append(step)
        if out[-1]["status"] != status:
            out.append({"at": rec.iso(max(rec.parse_iso(out[-1]["at"]), min(now, created + timedelta(hours=6)))),
                        "status": status})
        return out
    # Нет истории в мире: принято через 3 ч, в работу через сутки, «исправлено» через 3 дня (не позже «сейчас»).
    plan = {"accepted": ["accepted"], "in_progress": ["accepted", "in_progress"],
            "fixed": ["accepted", "in_progress", "fixed"], "rejected": ["rejected"]}.get(status, [])
    offsets = {"accepted": timedelta(hours=3), "in_progress": timedelta(days=1), "fixed": timedelta(days=3),
               "rejected": timedelta(hours=5)}
    span = max(now - created, timedelta(minutes=len(plan) + 1))
    for index, st in enumerate(plan, start=1):
        moment = created + min(offsets[st], span * index / (len(plan) + 1))
        out.append({"at": rec.iso(moment), "status": st})
    return out


def _parts(item: dict, created: datetime, now: datetime) -> tuple[list[dict], list[dict]]:
    """services[] и handoffs[] мира → v2.1 (проверка справочника служб, время от засева)."""
    parts, seen = [], set()
    for index, part in enumerate(item.get("services") or []):
        if not isinstance(part, dict) or part.get("service") not in lifecycle.SERVICES or part["service"] in seen:
            continue
        seen.add(part["service"])
        moment = _moment(part, now, created, key="updated_at") or created
        clean = {"service": part["service"], "role": part.get("role") if part.get("role") in joint.PART_ROLES else
                 ("lead" if index == 0 else "partner"),
                 "status": joint.part_status(part.get("status")) or "todo", "updated_at": rec.iso(moment)}
        note = joint.clean_note(part.get("note")) if isinstance(part.get("note"), str) else None
        if note:
            clean["note"] = note
        parts.append(clean)
    parts = parts[:joint.MAX_SERVICES]
    if parts and sum(1 for p in parts if p["role"] == "lead") != 1:
        for index, part in enumerate(parts):
            part["role"] = "lead" if index == 0 else "partner"
    parts.sort(key=lambda p: p["role"] != "lead")
    handoffs = []
    for entry in item.get("handoffs") or []:
        if not isinstance(entry, dict) or entry.get("to") not in lifecycle.SERVICES:
            continue
        moment = _moment(entry, now, created) or created
        reason = entry.get("reason") if isinstance(entry.get("reason"), str) and entry["reason"].strip() else None
        code = entry.get("reason_code") if entry.get("reason_code") in joint.HANDOFF_REASONS else None
        handoffs.append({"at": rec.iso(max(moment, created)), "from": entry.get("from") if entry.get("from") in
                         lifecycle.SERVICES else None, "to": entry["to"],
                         "reason": (reason or (joint.HANDOFF_REASONS[code]["ru"] if code else
                                               joint.HANDOFF_REASONS["other_service"]["ru"]))[:joint.REASON_MAX],
                         "by_role": entry.get("by_role") if entry.get("by_role") in ("operator", "admin") else "operator",
                         **({"reason_code": code} if code else {})})
    handoffs.sort(key=lambda h: h["at"])
    return parts, handoffs


def _resolution(item: dict, history: list[dict], now: datetime) -> dict | None:
    """Раунд «служба сообщила об устранении» для исправленных и возвращённых жителями (state из мира)."""
    given = item.get("resolution") if isinstance(item.get("resolution"), dict) else {}
    fixed_at = next((h["at"] for h in reversed(history) if h["status"] == "fixed"), None)
    state = given.get("state")
    if fixed_at is None and state != "reopened":
        return None
    reported = rec.parse_iso(fixed_at) if fixed_at else _moment(given, now, now - timedelta(days=2), key="reported_at")
    votes = given.get("votes") if isinstance(given.get("votes"), dict) else {}
    clean_votes = {k: int(votes.get(k) or 0) for k in lifecycle.VERIFY_ANSWERS}
    if state not in ("reported", "verified", "reopened"):
        state = "reported"
    resolution = lifecycle.new_resolution(None, rec.iso(reported), joint.clean_note(given.get("what_done"))
                                          if isinstance(given.get("what_done"), str) else None, None, [])
    resolution["by"] = None
    resolution["metoo_upto"] = 0
    resolution["state"] = state
    if state == "verified":
        verified = _moment(given, now, min(now, reported + timedelta(hours=20)), key="verified_at")
        resolution["verified_at"] = rec.iso(max(verified, reported))
        clean_votes["yes"] = max(1, clean_votes["yes"])
    if state == "reopened":
        reopened = _moment(given, now, min(now, reported + timedelta(hours=20)), key="reopened_at")
        resolution["reopened_at"] = rec.iso(max(reopened, reported))
        resolution["reopen_count"] = max(1, int(given.get("reopen_count") or 1))
        clean_votes["no"] = max(1, clean_votes["no"])
    resolution["votes"] = clean_votes
    return resolution


def build_record(item: dict, now: datetime) -> tuple[dict, list[tuple[str, str]]]:
    """Одна жалоба мира → (запись v2.1, [(device_hash, at) «Я тоже»]). WorldError — запись неверная."""
    cid = world_id(item.get("id"))
    category = item.get("category")
    if not categories.is_category(category):
        raise WorldError(f"{item.get('id')}: неизвестная категория {category!r}")
    subtopic = item.get("subtopic")
    if subtopic is not None and categories.subtopic(category, subtopic) is None:
        subtopic = None
    try:
        text = rec.parse_text(item.get("text") or "")
        point = rec.parse_point(item.get("point"))
        target = rec.parse_target(item["target"]) if item.get("target") is not None else rec.cell_target(*point)
    except (rec.RecordError, KeyError) as exc:
        raise WorldError(f"{item.get('id')}: {exc}") from None
    created = _moment(item, now, None, key="created_at")
    if created is None:
        raise WorldError(f"{item.get('id')}: нет времени (ago_days / ago_hours / created_at)")
    status = item.get("status") if item.get("status") in rec.STATUSES else "new"
    history = _history(item, status, created, now)
    status = history[-1]["status"]
    parts, handoffs = _parts(item, created, now)
    lead = parts[0]["service"] if parts else (item.get("service") if item.get("service") in lifecycle.SERVICES
                                              else lifecycle.default_service(category, subtopic))
    district = item.get("district") if isinstance(item.get("district"), str) and rec.DISTRICT.match(item["district"]) \
        else None
    lang = item.get("lang") if item.get("lang") in ("ru", "kk", "mixed") else rec.detect_lang(text)
    created_at = rec.iso(created)
    record = {
        "id": cid, "code": None, "created_at": created_at, "text": text, "lang": lang,
        "category": category, "category_source": "resident", "subtopic": subtopic,
        "emergency": lifecycle.emergency(category, subtopic, text), "model": None,
        "point": point, "target": target, "district": district,
        "status": status, "status_history": history, "metoo": 0, "duplicate_of": None, "demo": True,
        "due_at": rec.due_at(created_at, category),
        "service": lead, "service_source": "world", "services": parts, "handoffs": handoffs,
        "route_hint": joint.parse_route_hint(item.get("route_hint")),
        "world": {"id": item.get("id"), "scene": item.get("scene")} if item.get("scene") else {"id": item.get("id")},
        "schema": rec.SCHEMA,
    }
    if record["emergency"] is not None:
        record["emergency"]["banner_shown"] = False
    resolution = _resolution(item, history, now)
    if resolution is not None:
        record["resolution"] = resolution
        if resolution["state"] == "reopened" and status not in rec.OPEN_STATUSES:
            record["status"] = "in_progress"
            history.append({"at": resolution["reopened_at"], "status": "in_progress", "reopened_by_residents": True})
    flag = rec.moderation(text)
    if flag:
        record["moderation"] = flag
    # «Я тоже»: список времён из мира или число — равномерно между подачей и «сейчас» (детерминированно).
    metoo = []
    times = item.get("metoo_ago")
    if isinstance(times, list) and times:
        for n, entry in enumerate(times[:MAX_METOO], start=1):
            moment = _moment(entry if isinstance(entry, dict) else {"ago_hours": entry}, now, created)
            metoo.append((_device(cid, n), rec.iso(max(moment, created))))
    else:
        count = item.get("metoo")
        count = max(0, min(int(count), MAX_METOO)) if isinstance(count, (int, float)) and not isinstance(count, bool) else 0
        span = now - created
        for n in range(1, count + 1):
            metoo.append((_device(cid, n), rec.iso(created + span * n / (count + 1))))
    record["metoo"] = len(metoo)
    return record, metoo


def seed_world(db_path, records, now=None, *, reset: bool = False) -> dict:
    """Засеять жалобы мира. db_path — путь к SQLite, ComplaintStore или сервис R09 (его store).
    -> {"inserted", "skipped", "reset", "invalid": [причины], "total"}. Идемпотентно (см. модуль)."""
    from .store import ComplaintStore
    store = db_path if isinstance(db_path, ComplaintStore) else getattr(db_path, "store", None)
    own = None
    if not isinstance(store, ComplaintStore):
        own = store = ComplaintStore(str(db_path))
    report = {"inserted": 0, "skipped": 0, "reset": 0, "invalid": [], "total": 0}
    try:
        moment = _now(now) if now is not None else store._now()
        items = _complaints(records)
        report["total"] = len(items)
        built = []
        for item in items:
            try:
                built.append(build_record(item, moment))
            except WorldError as exc:
                report["invalid"].append(str(exc)[:200])
        # Одна транзакция на весь мир: 700–900 записей за доли секунды, а не по fsync на запись.
        with store._tx() as db:
            for record, metoo in built:
                old = store._load(db, record["id"])
                if old is not None and not (reset and old.get("demo")):
                    report["skipped"] += 1
                    continue
                record["code"] = (old or {}).get("code") or store._next_code(db)
                if old is not None:
                    for table in ("complaint_metoo_v2", "complaint_votes_v2", "complaint_photos_v2",
                                  "complaint_uploads_v2"):
                        db.execute(f"DELETE FROM {table} WHERE complaint_id = ?", (record["id"],))
                for device, at in metoo:
                    db.execute("INSERT OR IGNORE INTO complaint_metoo_v2 (complaint_id, device_hash, at) VALUES (?,?,?)",
                               (record["id"], device, at))
                if record.get("resolution"):
                    # R15-S24, как в set_status: проверить ремонт могут только «Я тоже», нажатые до «служба сообщила»
                    # (здесь — синтетические этого засева); нажавший после показа — уже нет.
                    record["resolution"]["metoo_upto"] = db.execute(
                        "SELECT COALESCE(MAX(rowid), 0) FROM complaint_metoo_v2").fetchone()[0]
                store._save(db, record)
                report["reset" if old is not None else "inserted"] += 1
            db.execute("INSERT OR REPLACE INTO complaint_meta_v2 (key, value) VALUES ('world_seeded_at', ?)",
                       (rec.iso(moment),))
        if report["inserted"] or report["reset"]:
            # Карта R07 (подписка шлюза) сбрасывает кэш; в таблицу событий засев не пишется — это не новые жалобы.
            store._emit([{"type": "world_seeded", "at": rec.iso(moment), "inserted": report["inserted"],
                          "reset": report["reset"]}])
    finally:
        if own is not None:
            own.close()
    return report


def scene_complaint(db_path, scene: str):
    """Запись сцены мира (scenes R02 → complaint с полем scene, например «pit_after_digging») или None."""
    from .store import ComplaintStore
    store = db_path if isinstance(db_path, ComplaintStore) else getattr(db_path, "store", None)
    own = None
    if not isinstance(store, ComplaintStore):
        own = store = ComplaintStore(str(db_path))
    try:
        for record in store.list(include_duplicates=True):
            if (record.get("world") or {}).get("scene") == scene:
                return record
        return None
    finally:
        if own is not None:
            own.close()

