"""Задачи «ИИ-разбора пачки обращений» R04 → записи жалоб R09 (раунд 15+, поправка П3, сцена 0 демо).

R04 (ui/civic_ml_api/intake.py) раскладывает пачку текстов по задачам: категория, службы route(), место, повторы,
срочность. Сотрудник нажимает «Создать задачи» → маршрут R04 POST intake/commit {batch_id, task_ids} → R04 в процессе
зовёт R09 (записи жалоб создаёт только R09, как R03 зовёт соседей):

    from ui.civic_feedback.v2.integration import intake_commit
    report = intake_commit(None, batch_id, tasks, texts, demo=is_sample, actor="Сотрудник акимата")
    # None — хранилище шлюза R01 (make_service) этого процесса: событие «created» сразу видят карта R07 и соседи.
    # -> {"batch_id", "total", "people", "created": [{"task_id", "id", "code"}], "existing": [{"task_id", "id", "code"}],
    #     "skipped": [{"task_id", "reason"}]}      reason: no_place · category · text · invalid

Задача — как в ответе R04 analyze (П3): {id, title_ru, title_kk, category, subtopic?, services [{id, role}], why_ru,
why_kk, target | null, point?, district?, address_text, text_ids, people, urgent, urgent_why, score?, model_version?}.
texts — тексты пачки: {text_id: текст} или [{"id", "text"}] (список строк — id = номер строки с 0).

Правила:
  * одна задача → одна жалоба цели: текст — первое обращение группы (оригинал; длиннее 2000 символов — обрезан),
    «Сообщили N человек» — people задачи: автор + N−1 «Я тоже» с синтетическими устройствами (sha256, не настоящие
    устройства — уведомлений никто не получит);
  * id — от (batch_id, task_id): повторный commit той же пачки (целиком или частями) не дублирует записи (existing);
  * место — только найденное R04: point задачи (или target.point / target.center) в границах Астаны; цель проверяется
    картой R12, как у жалобы жителя (подписи — с карты, цель дальше 300 м от точки — «примерное место»); без карты R12
    в сборке остаются подписи R04 (они из данных карты, не из текста жителя). Нет точки — задача не создаётся
    (skipped: no_place, «адрес уточнить»): R09 место не угадывает;
  * район — из задачи или по точке (границы районов R07 ui.civic_heat.geo — те же, что у карты «Нура · N»);
  * категория — одна из 12; службы — справочник R09: ведущая (role lead или первая) — служба записи (service_source
    «intake»: выбор подтвердил сотрудник кнопкой «Создать задачи»); две службы и больше — подсказка «Похоже, нужны
    2 службы» (route_hint, «Принять» в карточке), как у жалобы жителя: совместное исполнение решает сотрудник;
  * срок ответа (рабочие дни РК), номер B-0001, пометка грубых слов R04, номер 104/112 — как у жалобы жителя;
  * пример (sample «night», demo=True) — demo: true («Пример»), но записи рабочие: с ними идёт сцена 0;
  * в записи — intake {batch_id, task_id, people, urgent, urgent_why, method, at, by}: в «Обращениях» — «Источник:
    разбор пачки». Публично (карта, житель) intake не отдаётся — record.public_view.
"""

from __future__ import annotations

import hashlib
import re

from .. import text as textutil
from . import categories, joint, lifecycle
from . import record as rec

INTAKE_PREFIX = "c-i"
BATCH_ID = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
TASK_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
MAX_TASKS = 500           # предел пачки R04 — 500 текстов за раз; задач не больше
MAX_PEOPLE = 400          # как у демо-мира: одна жалоба — не больше 400 «Я тоже»
NOTE_MAX = 160
METHOD_MAX = 40
SKIP_REASONS = ("no_place", "category", "text", "invalid")


class IntakeError(ValueError):
    """Задачу нельзя превратить в запись: reason — код для экрана R04 (SKIP_REASONS)."""

    def __init__(self, reason: str, message: str = ""):
        super().__init__(message or reason)
        self.reason = reason


def intake_id(batch_id: str, task_id: str) -> str:
    """id записи R09 для задачи пачки: детерминированный c-i<хэш> — повторный commit узнаёт запись."""
    return INTAKE_PREFIX + hashlib.sha256(f"r09-intake:{batch_id}:{task_id}".encode("utf-8")).hexdigest()[:16]


def intake_device(record_id: str, n: int) -> str:
    """Синтетическое устройство n-го «Я тоже» записи пачки (не устройство жителя: уведомлений нет)."""
    return hashlib.sha256(f"r09-intake:{record_id}:{n}".encode("utf-8")).hexdigest()


def _texts(value) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, dict):
        items = list(value.items())
    elif isinstance(value, (list, tuple)):
        items = [(item.get("id", n), item.get("text")) if isinstance(item, dict) else (n, item)
                 for n, item in enumerate(value)]
    else:
        raise IntakeError("invalid", "texts — {id: текст} или список")
    return {str(key): text for key, text in items
            if isinstance(text, str) and isinstance(key, (str, int)) and not isinstance(key, bool)}


def _clip(value: str) -> str:
    text = textutil.clean_text(value)
    if len(text) > rec.TEXT_MAX:
        cut = text[:rec.TEXT_MAX - 1]
        space = cut.rfind(" ")
        text = (cut[:space] if space > rec.TEXT_MAX // 2 else cut).rstrip() + "…"
    return text


def _text(task: dict, texts: dict[str, str]) -> str:
    """Оригинал первого обращения группы; нет текстов — текст или заголовок задачи."""
    candidates = [texts.get(str(tid)) for tid in task.get("text_ids") or [] if isinstance(tid, (str, int))]
    candidates += [task.get("text"), task.get("title_ru")]
    for raw in candidates:
        if isinstance(raw, str):
            text = _clip(raw)
            if len(text) >= rec.TEXT_MIN:
                return rec.parse_text(text)
    raise IntakeError("text", "нет текста обращения")


def _point(task: dict) -> list[float]:
    target = task.get("target") if isinstance(task.get("target"), dict) else {}
    for value in (task.get("point"), target.get("point"), target.get("center")):
        if value is None:
            continue
        try:
            return rec.parse_point(value)
        except rec.RecordError:
            continue
    raise IntakeError("no_place", "место не найдено — адрес уточнить")


def _target(task: dict, point: list[float], lookup) -> dict:
    raw = task.get("target")
    target = None
    if isinstance(raw, dict) and raw.get("kind") in rec.TARGET_KINDS:
        try:
            target = rec.parse_target({key: raw.get(key) for key in ("kind", "id", "label_ru", "label_kk", "approximate")})
        except rec.RecordError:
            target = None
    if target is None:
        return rec.checked_target(rec.cell_target(*point), point, lookup)
    checked = rec.checked_target(target, point, lookup)
    if lookup is None and checked["id"] == target["id"]:
        # Карты R12 в сборке нет: подписи — R04 (из данных карты по названию, не из текста жителя).
        for name in ("label_ru", "label_kk"):
            if target.get(name):
                checked[name] = target[name]
    return checked


def _district(task: dict, point: list[float]) -> str | None:
    target = task.get("target") if isinstance(task.get("target"), dict) else {}
    for value in (task.get("district"), target.get("district")):
        if isinstance(value, str) and rec.DISTRICT.match(value):
            return value
    try:
        from ui.civic_heat.geo import district_of   # границы районов R07 — те же, что у карты «Нура · N»
        found = district_of(point)
    except Exception:  # noqa: BLE001 — нет R07 в сборке или файла границ: район не обязателен
        return None
    return found if isinstance(found, str) and rec.DISTRICT.match(found) else None


def _services(task: dict, category: str, subtopic: str | None) -> list[str]:
    """id служб задачи из справочника R09, ведущая первой; нет ни одной — служба категории по таблице."""
    ids, lead = [], None
    for item in task.get("services") or []:
        sid = (item.get("id", item.get("service")) if isinstance(item, dict) else item)
        if not lifecycle.is_service(sid) or sid in ids:
            continue
        ids.append(sid)
        if lead is None and isinstance(item, dict) and item.get("role") == "lead":
            lead = sid
    if lead is not None:
        ids.remove(lead)
        ids.insert(0, lead)
    return ids[:joint.MAX_SERVICES] or [lifecycle.default_service(category, subtopic)]


def _note(value, limit: int = NOTE_MAX) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(textutil.clean_text(value).split())[:limit]
    return text or None


def _people(task: dict) -> int:
    value = task.get("people")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        value = len(task.get("text_ids") or []) or 1
    return max(1, min(int(value), MAX_PEOPLE + 1))


def build_record(task: dict, texts: dict[str, str], *, batch_id: str, now, demo: bool = False, actor=None,
                 method=None, target_lookup=None) -> tuple[dict, list[tuple[str, str]]]:
    """Задача R04 → (запись v2.1 без номера, [(device_hash, at) «Я тоже»]). IntakeError — задача не подходит."""
    if not isinstance(task, dict):
        raise IntakeError("invalid", "задача — объект")
    task_id = task.get("id")
    if isinstance(task_id, int) and not isinstance(task_id, bool):
        task_id = str(task_id)
    if not isinstance(task_id, str) or not TASK_ID.match(task_id):
        raise IntakeError("invalid", "неверный id задачи")
    category = task.get("category")
    if not categories.is_category(category):
        raise IntakeError("category", "неизвестная категория")
    subtopic = task.get("subtopic")
    if subtopic is not None and categories.subtopic(category, subtopic) is None:
        subtopic = None
    text = _text(task, texts)
    point = _point(task)
    target = _target(task, point, target_lookup)
    services = _services(task, category, subtopic)
    version = task.get("model_version") if isinstance(task.get("model_version"), str) else method
    version = version[:80] if isinstance(version, str) else None
    hint = joint.parse_route_hint({"services": [{"service": sid} for sid in services], "joint": len(services) > 1,
                                   "why_ru": task.get("why_ru"), "why_kk": task.get("why_kk"),
                                   "source": "model", "model_version": version})
    created_at = rec.iso(now)
    cid = intake_id(batch_id, task_id)
    banner = lifecycle.emergency(category, subtopic, text)
    if banner is not None:
        banner["banner_shown"] = False
    urgent = task.get("urgent") is True
    people = _people(task)
    record = {
        "id": cid, "code": None, "created_at": created_at, "text": text, "lang": rec.detect_lang(text),
        "category": category, "category_source": "model", "subtopic": subtopic, "emergency": banner,
        "model": rec.parse_model({"label": category, "score": task.get("score", task.get("category_score")),
                                  "version": version}),
        "point": point, "target": target, "district": _district(task, point),
        "status": "new", "status_history": [{"at": created_at, "status": "new"}],
        "metoo": people - 1, "duplicate_of": None, "demo": bool(demo),
        "due_at": rec.due_at(created_at, category),
        "service": services[0], "service_source": "intake", "services": [], "handoffs": [], "route_hint": hint,
        "intake": {"batch_id": batch_id, "task_id": task_id, "people": people, "urgent": urgent,
                   "urgent_why": _note(task.get("urgent_why")) if urgent else None,
                   "method": _note(method, METHOD_MAX), "at": created_at, "by": _note(actor, 80)},
        "schema": rec.SCHEMA,
    }
    flag = rec.moderation(text)   # п. 8 (R04): акимат видит оригинал с пометкой
    if flag:
        record["moderation"] = flag
    metoo = [(intake_device(cid, n), created_at) for n in range(1, people)]
    return record, metoo


def _moment(value):
    if isinstance(value, str):
        moment = rec.parse_iso(value)
        if moment is None:
            raise ValueError("now — ISO-время")
        return moment
    return value if value.tzinfo else value.replace(tzinfo=rec.ASTANA_TZ)


def _store_of(source):
    """Хранилище, которое поднял шлюз (make_service), если путь тот же или source=None: события «created» уходят его
    подписчикам (карта R07). Иначе — хранилище по пути (как у функций чтения integration)."""
    from .integration import _store
    return _store(source), None


def commit_tasks(db, batch_id, tasks, texts=None, *, demo: bool = False, now=None, actor=None, method=None) -> dict:
    """Создать записи R09 из задач пачки R04 (см. модуль). db — ComplaintStore, сервис R09 или путь к SQLite.
    Идемпотентно по (batch_id, task_id). ValueError — неверная пачка целиком (batch_id, не список, больше 500)."""
    if not isinstance(batch_id, str) or not BATCH_ID.match(batch_id):
        raise ValueError("batch_id — 4–64 символа: латиница, цифры, - и _")
    if not isinstance(tasks, (list, tuple)):
        raise ValueError("tasks — список задач")
    if len(tasks) > MAX_TASKS:
        raise ValueError(f"не больше {MAX_TASKS} задач за раз")
    pool = _texts(texts)
    store, own = _store_of(db)
    report = {"batch_id": batch_id, "total": len(tasks), "people": 0, "created": [], "existing": [], "skipped": []}
    try:
        moment = store._now() if now is None else _moment(now)
        lookup = store.target_lookup
        if lookup is None:
            from .integration import geo_target_lookup
            lookup = geo_target_lookup()
        built, seen = [], set()
        for task in tasks:
            task_id = task.get("id") if isinstance(task, dict) else None
            try:
                record, metoo = build_record(task, pool, batch_id=batch_id, now=moment, demo=demo, actor=actor,
                                             method=method, target_lookup=lookup)
            except IntakeError as exc:
                report["skipped"].append({"task_id": task_id if isinstance(task_id, (str, int)) else None,
                                          "reason": exc.reason})
                continue
            except (rec.RecordError, TypeError, ValueError):
                report["skipped"].append({"task_id": task_id if isinstance(task_id, (str, int)) else None,
                                          "reason": "invalid"})
                continue
            if record["id"] in seen:          # одна задача дважды в одном вызове — одна запись
                continue
            seen.add(record["id"])
            built.append((record, metoo))
        events = []
        with store._tx() as db_tx:
            for record, metoo in built:
                old = store._load(db_tx, record["id"])
                task_id = record["intake"]["task_id"]
                if old is not None:
                    report["existing"].append({"task_id": task_id, "id": old["id"], "code": old.get("code")})
                    continue
                record["code"] = store._next_code(db_tx)
                store._save(db_tx, record)
                db_tx.executemany("INSERT OR IGNORE INTO complaint_metoo_v2 (complaint_id, device_hash, at) VALUES (?,?,?)",
                                  [(record["id"], device, at) for device, at in metoo])
                events.append(store._event(db_tx, "created", record, record["created_at"]))
                report["created"].append({"task_id": task_id, "id": record["id"], "code": record["code"]})
                report["people"] += rec.reporters(record)
        store._emit(events)
    finally:
        if own is not None:
            own.close()
    return report
