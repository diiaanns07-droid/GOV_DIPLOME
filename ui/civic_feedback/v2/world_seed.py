"""Демо-мир R02 в хранилище жалоб R09 (раунд 15, CONTRACT §11): seed_world(db_path, records, now=None).

R01 вызывает при CIVIC_DEMO=1 и CIVIC_DEMO_WORLD=1 (data/civic/astana/demo-world/world_v1.json) — тогда карта R07,
«Картина дня» R08, табло служб R17 и «Мой двор» R16 считают из одних и тех же жалоб, а «Обращения» сотрудника
показывают те же числа. Без флага — прежнее демо FINAL-4 (seed_demo: две жалобы «Хан Шатыр» шага 2 — остаются всегда;
их id в мире совпадают с demo_seed, поэтому оба засева не дублируют друг друга).

Формат — data/civic/astana/demo-world/SCHEMA.md (R02, birge-demo-world-v1 1.1), §2.3: запись R09 v2 + v2.1, все времена
— объекты относительного времени ({"ago_hours": 30.5}, {"day": 6} …) от МОМЕНТА ЗАСЕВА. Перевод в ISO — функцией R02
ml.datasets.demo_world_io.materialize (та же грамматика, что у генератора); нет модуля R02 — своя копия грамматики ниже.
Уже абсолютные строки не трогаются: R01 может передать и materialize(world, now)["complaints"].

Правила:
  * идемпотентно: повтор ничего не дублирует (id мира — c-w…); reset=True — записи мира возвращаются в исходное
    состояние со временем от этого засева (репетиция не «съедает» сцену 8, как R10 B-048); настоящие жалобы — никогда;
  * всё синтетическое: demo: true («Пример»), устройства «Я тоже» — sha256("demo-world-v1:<id>:<n>") (SCHEMA §2.3);
  * срок ответа (due_at) и номер B-0001 ставит R09: due_at — рабочие дни РК от created_at, не из файла;
  * неверная запись (категория, место вне Астаны, цель, время) не ломает засев — она в отчёте invalid с причиной.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from . import categories, joint, lifecycle
from . import record as rec

WORLD_PREFIX = "c-w"
MAX_METOO = 400          # защита от опечатки генератора: одна жалоба — не больше 400 «Я тоже»
UPDATE_KINDS = ("fixed", "reopened", "passport", "note")


class WorldError(ValueError):
    pass


def world_id(source_id) -> str:
    """id записи R09 для жалобы мира: свой id c-… (если подходит правилу R09) или детерминированный c-w<хэш>."""
    if isinstance(source_id, str) and rec.COMPLAINT_ID.match(source_id):
        return source_id
    return WORLD_PREFIX + hashlib.sha256(f"r09-world:{source_id}".encode("utf-8")).hexdigest()[:16]


def demo_device(record_id: str, n: int) -> str:
    """Устройство n-го «Я тоже» жалобы мира — формула R02 (SCHEMA §2.3, demo_world_io.demo_device)."""
    return hashlib.sha256(f"demo-world-v1:{record_id}:{n}".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- время мира (SCHEMA §1)
_INSTANT = {"ago_hours": -3600.0, "in_hours": 3600.0, "ago_days": -86400.0, "in_days": 86400.0}


def _resolve(value, now: datetime):
    """Копия грамматики R02 demo_world_io.resolve: объект относительного времени → ISO / YYYY-MM-DD."""
    if not isinstance(value, dict) or len(value) != 1:
        return value
    (key, inner), = value.items()
    num = isinstance(inner, (int, float)) and not isinstance(inner, bool)
    if key in _INSTANT and num:
        return rec.iso(now + timedelta(seconds=float(inner) * _INSTANT[key]))
    if key == "day" and isinstance(inner, int) and not isinstance(inner, bool):
        return (now.astimezone(rec.ASTANA_TZ).date() + timedelta(days=inner)).isoformat()
    if key == "day_at" and isinstance(inner, dict) and {"day", "hour", "minute"} <= set(inner):
        day = now.astimezone(rec.ASTANA_TZ).date() + timedelta(days=int(inner["day"]))
        return rec.iso(datetime(day.year, day.month, day.day, int(inner["hour"]), int(inner["minute"]), tzinfo=rec.ASTANA_TZ))
    if key == "next_weekday" and isinstance(inner, dict) and {"weekday", "hour", "minute"} <= set(inner):
        local = now.astimezone(rec.ASTANA_TZ)
        moment = local.replace(hour=int(inner["hour"]), minute=int(inner["minute"]), second=0, microsecond=0)
        moment += timedelta(days=(int(inner["weekday"]) - local.weekday()) % 7)
        while moment - local < timedelta(hours=12):
            moment += timedelta(days=7)
        return rec.iso(moment)
    if key == "season" and isinstance(inner, dict) and {"month", "day"} <= set(inner):
        today = now.astimezone(rec.ASTANA_TZ).date()
        year = today.year if today.month <= 3 else today.year + 1
        return date(year, int(inner["month"]), int(inner["day"])).isoformat()
    return value


def _walk(value, now: datetime):
    resolved = _resolve(value, now)
    if resolved is not value:
        return resolved
    if isinstance(value, dict):
        return {key: _walk(item, now) for key, item in value.items()}
    if isinstance(value, list):
        return [_walk(item, now) for item in value]
    return value


def materialize(item, now: datetime):
    """Абсолютные времена от now: функция R02 (если модуль в сборке), иначе своя копия грамматики SCHEMA §1."""
    try:
        from ml.datasets.demo_world_io import materialize as r02_materialize
    except ImportError:
        return _walk(copy.deepcopy(item), now)
    return r02_materialize(item, now)


def _now(value) -> datetime:
    if value is None:
        return datetime.now(rec.ASTANA_TZ)
    if isinstance(value, str):
        moment = rec.parse_iso(value)
        if moment is None:
            raise WorldError("now — ISO-время")
        return moment
    return value if value.tzinfo else value.replace(tzinfo=rec.ASTANA_TZ)


def _complaints(records) -> list[dict]:
    if isinstance(records, (str, Path)):
        records = json.loads(Path(records).read_text(encoding="utf-8"))
    if isinstance(records, dict):
        records = records.get("complaints") or []
    if not isinstance(records, list):
        raise WorldError("Ожидается мир R02 (объект с complaints) или список жалоб.")
    return [item for item in records if isinstance(item, dict)]


def _at(value, now: datetime, default: datetime | None = None) -> datetime | None:
    """ISO-строка мира → момент; будущее время обрезается до «сейчас» (жалоба не из будущего)."""
    moment = rec.parse_iso(value) if isinstance(value, str) else None
    if moment is None:
        moment = default
    if moment is not None and moment > now:
        moment = now
    return moment


# ---------------------------------------------------------------- части записи
def _history(item: dict, status: str, created: datetime, now: datetime) -> list[dict]:
    """Шаги статуса мира (по времени; первый — «new» в момент подачи). Нет истории — правдоподобная по статусу."""
    out = [{"at": rec.iso(created), "status": "new"}]
    given = item.get("status_history")
    if isinstance(given, list) and given:
        steps = []
        for entry in given:
            st = entry.get("status") if isinstance(entry, dict) else None
            if st not in rec.STATUSES:
                continue
            moment = max(_at(entry.get("at"), now, created), created)
            steps.append((moment, st, entry))
        steps.sort(key=lambda s: s[0])
        for moment, st, entry in steps:
            if st == out[-1]["status"] and not entry.get("reopened_by_residents"):
                continue
            step = {"at": rec.iso(moment), "status": st}
            if entry.get("reopened_by_residents") is True:
                step["reopened_by_residents"] = True
            out.append(step)
        if out[-1]["status"] != status:
            out.append({"at": rec.iso(max(rec.parse_iso(out[-1]["at"]), min(now, created + timedelta(hours=6)))),
                        "status": status})
        return out
    plan = {"accepted": ["accepted"], "in_progress": ["accepted", "in_progress"],
            "fixed": ["accepted", "in_progress", "fixed"], "rejected": ["rejected"]}.get(status, [])
    offsets = {"accepted": timedelta(hours=3), "in_progress": timedelta(days=1), "fixed": timedelta(days=3),
               "rejected": timedelta(hours=5)}
    span = max(now - created, timedelta(minutes=len(plan) + 1))
    for index, st in enumerate(plan, start=1):
        out.append({"at": rec.iso(created + min(offsets[st], span * index / (len(plan) + 1))), "status": st})
    return out


def _parts(item: dict, created: datetime, now: datetime) -> tuple[list[dict], list[dict]]:
    """services[] и handoffs[] мира → v2.1 (справочник служб, статусы частей new|accepted → todo)."""
    parts, seen = [], set()
    for index, part in enumerate(item.get("services") or []):
        if not isinstance(part, dict) or part.get("service") not in lifecycle.SERVICES or part["service"] in seen:
            continue
        seen.add(part["service"])
        clean = {"service": part["service"],
                 "role": part.get("role") if part.get("role") in joint.PART_ROLES else ("lead" if index == 0 else "partner"),
                 "status": joint.part_status(part.get("status")) or "todo",
                 "updated_at": rec.iso(max(_at(part.get("updated_at"), now, created), created))}
        note = joint.clean_note(part["note"]) if isinstance(part.get("note"), str) else None
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
        reason = entry.get("reason") if isinstance(entry.get("reason"), str) and entry["reason"].strip() else None
        code = entry.get("reason_code") if entry.get("reason_code") in joint.HANDOFF_REASONS else None
        clean = {"at": rec.iso(max(_at(entry.get("at"), now, created), created)),
                 "from": entry.get("from") if entry.get("from") in lifecycle.SERVICES else None, "to": entry["to"],
                 "reason": " ".join((reason or (joint.HANDOFF_REASONS[code]["ru"] if code else
                                                joint.HANDOFF_REASONS["other_service"]["ru"])).split())[:joint.REASON_MAX],
                 "by_role": entry.get("by_role") if entry.get("by_role") in ("operator", "admin") else "operator"}
        if code:
            clean["reason_code"] = code
        handoffs.append(clean)
    handoffs.sort(key=lambda h: h["at"])
    return parts, handoffs


def _text(value, limit=lifecycle.PASSPORT_TEXT_MAX) -> str | None:
    return " ".join(value.split())[:limit] or None if isinstance(value, str) else None


def _passport(item: dict, now: datetime) -> dict | None:
    """Паспорт решения мира → формат R09 (store.update_passport): кто, следующий шаг, ориентир, задержка.
    Задержка с «нужно решение акима» — как читает R08 decisions: delay.needs_decision, options [{ru, kk}], decision."""
    given = item.get("passport")
    if not isinstance(given, dict):
        return None
    passport = {}
    if given.get("assignee_id") in lifecycle.SERVICES:
        passport["assignee_id"] = given["assignee_id"]
    if _text(given.get("next_step")):
        passport["next_step"] = _text(given["next_step"])
    eta = given.get("fix_eta")
    if isinstance(eta, str):
        try:
            passport["fix_eta"] = date.fromisoformat(eta[:10]).isoformat()
        except ValueError:
            pass
    delay = given.get("delay")
    if isinstance(delay, dict):
        clean = {"reason": _text(delay.get("reason")) or _text(delay.get("blocker_ru")) or _text(delay.get("problem_ru")),
                 "temp_measure": _text(delay.get("temp_measure")) or _text(delay.get("temp_measure_ru")),
                 "next_update_at": None}
        nxt = delay.get("next_update_at")
        if isinstance(nxt, str):
            try:
                clean["next_update_at"] = date.fromisoformat(nxt[:10]).isoformat()
            except ValueError:
                pass
        for key in ("problem_ru", "problem_kk", "blocker_ru", "blocker_kk", "temp_measure_kk", "decision_kk"):
            if _text(delay.get(key)):
                clean[key] = _text(delay[key])
        if delay.get("needs_decision") is True:
            clean["needs_decision"] = True
            clean["options"] = [{k: _text(o.get(k)) for k in ("ru", "kk") if _text(o.get(k))}
                                for o in delay.get("options") or [] if isinstance(o, dict)][:2]
            clean["decision"] = _text(delay.get("decision")) or _text(delay.get("decision_ru"))
        if isinstance(delay.get("reason_code"), str):
            clean["reason_code"] = delay["reason_code"][:40]
        passport["delay"] = clean
    passport["updated_at"] = rec.iso(now)
    return passport


def _resolution(item: dict, history: list[dict], now: datetime) -> dict | None:
    """Раунд «служба сообщила об устранении» мира: reported | verified | reopened, голоса, «что сделали»."""
    given = item.get("resolution") if isinstance(item.get("resolution"), dict) else {}
    fixed_at = next((h["at"] for h in reversed(history) if h["status"] == "fixed"), None)
    state = given.get("state")
    if fixed_at is None and state != "reopened":
        return None
    reported = _at(given.get("reported_at"), now, rec.parse_iso(fixed_at) if fixed_at else now - timedelta(days=2))
    if state not in ("reported", "verified", "reopened"):
        state = "reported"
    what = joint.clean_note(given["what_done"]) if isinstance(given.get("what_done"), str) else None
    resolution = lifecycle.new_resolution(None, rec.iso(reported), what, None, [])
    resolution["round"] = int(given.get("round") or 1)
    resolution["by"] = "service"
    resolution["state"] = state
    votes = given.get("votes") if isinstance(given.get("votes"), dict) else {}
    resolution["votes"] = {k: max(0, int(votes.get(k) or 0)) for k in lifecycle.VERIFY_ANSWERS}
    resolution["reopen_count"] = max(0, int(given.get("reopen_count") or 0))
    if state == "verified":
        resolution["verified_at"] = rec.iso(max(_at(given.get("verified_at"), now, min(now, reported + timedelta(hours=20))), reported))
        resolution["votes"]["yes"] = max(1, resolution["votes"]["yes"])
    if state == "reopened":
        resolution["reopened_at"] = rec.iso(max(_at(given.get("reopened_at"), now, min(now, reported + timedelta(hours=20))), reported))
        resolution["reopen_count"] = max(1, resolution["reopen_count"])
        resolution["votes"]["no"] = max(1, resolution["votes"]["no"])
    return resolution


def build_record(raw: dict, now: datetime) -> tuple[dict, list[tuple[str, str]]]:
    """Одна жалоба мира → (запись v2.1, [(device_hash, at) «Я тоже»]). WorldError — запись неверная."""
    item = materialize(raw, now)
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
    if isinstance(item.get("target"), dict) and isinstance(item["target"].get("object_kind"), str) \
            and rec.OBJECT_KIND_RE.match(item["target"]["object_kind"]):
        target["object_kind"] = item["target"]["object_kind"]
    created = _at(item.get("created_at"), now, None)
    if created is None:
        raise WorldError(f"{item.get('id')}: нет времени подачи (created_at)")
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
    source = item.get("category_source") if item.get("category_source") in ("resident", "model", "staff") else "resident"
    urgent = lifecycle.emergency(category, subtopic, text)
    if urgent is not None:
        urgent["banner_shown"] = False
    record = {
        "id": cid, "code": None, "created_at": created_at, "text": text, "lang": lang,
        "category": category, "category_source": source, "subtopic": subtopic, "emergency": urgent,
        "model": rec.parse_model(item.get("model")),
        "point": point, "target": target, "district": district,
        "status": status, "status_history": history, "metoo": 0,
        "duplicate_of": item["duplicate_of"] if isinstance(item.get("duplicate_of"), str)
        and rec.COMPLAINT_ID.match(item["duplicate_of"]) else None,
        "demo": True, "due_at": rec.due_at(created_at, category),
        "service": lead, "service_source": "world", "services": parts, "handoffs": handoffs,
        "route_hint": joint.parse_route_hint(item.get("route_hint")),
        "event": item.get("event") if isinstance(item.get("event"), str) else None,
        "scene": item.get("scene") if isinstance(item.get("scene"), str) else None,
        "world": {"id": item.get("id"), "scene": item.get("scene"), "event": item.get("event")},
        "schema": rec.SCHEMA,
    }
    passport = _passport(item, now)
    if passport:
        record["passport"] = passport
    updates = []
    for entry in item.get("updates") or []:
        if isinstance(entry, dict) and entry.get("kind") in UPDATE_KINDS:
            moment = max(_at(entry.get("at"), now, created), created)
            updates.append({"at": rec.iso(moment), "kind": entry["kind"],
                            "text": _text(entry.get("text"), lifecycle.PASSPORT_TEXT_MAX * 2)})
    if updates:
        record["updates"] = sorted(updates, key=lambda u: u["at"])
    resolution = _resolution(item, history, now)
    if resolution is not None:
        record["resolution"] = resolution
        if resolution["state"] == "reopened" and status not in rec.OPEN_STATUSES:
            record["status"] = "in_progress"
            history.append({"at": resolution["reopened_at"], "status": "in_progress", "reopened_by_residents": True})
    flag = rec.moderation(text)
    if flag:
        record["moderation"] = flag
    # «Я тоже»: времена из мира (metoo_times) или число — равномерно между подачей и «сейчас» (детерминированно).
    metoo = []
    times = item.get("metoo_times")
    if isinstance(times, list) and times:
        for n, value in enumerate(times[:MAX_METOO], start=1):
            moment = max(_at(value, now, created), created)
            metoo.append((demo_device(cid, n), rec.iso(moment)))
    else:
        count = item.get("metoo")
        count = max(0, min(int(count), MAX_METOO)) if isinstance(count, (int, float)) and not isinstance(count, bool) else 0
        span = now - created
        metoo = [(demo_device(cid, n), rec.iso(created + span * n / (count + 1))) for n in range(1, count + 1)]
    record["metoo"] = len(metoo)
    return record, metoo


def seed_world(db_path, records, now=None, *, reset: bool = True) -> dict:
    """Засеять жалобы мира. db_path — путь к SQLite, ComplaintStore или сервис R09 (его store).
    -> {"inserted", "skipped", "reset", "invalid": [причины], "total"}. Идемпотентно (см. модуль).
    reset=True по умолчанию (просьба R02, как seed_demo FINAL-4): демо-записи мира — к виду мира от нового now при каждом
    запуске (иначе через сутки «сегодня» пусто); reset=False — только добавить недостающие. Настоящие жалобы — никогда."""
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
            except (WorldError, TypeError, ValueError) as exc:
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
    """Запись сцены мира (поле scene у жалобы, scenes R02: «scene8» — яма после раскопок) или None."""
    from .store import ComplaintStore
    store = db_path if isinstance(db_path, ComplaintStore) else getattr(db_path, "store", None)
    own = None
    if not isinstance(store, ComplaintStore):
        own = store = ComplaintStore(str(db_path))
    try:
        for record in store.list(include_duplicates=True, limit=store.limits["list_max"]):
            if record.get("scene") == scene or (record.get("world") or {}).get("scene") == scene:
                return record
        return None
    finally:
        if own is not None:
            own.close()
