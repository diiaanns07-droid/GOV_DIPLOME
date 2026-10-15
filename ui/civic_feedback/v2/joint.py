"""Совместное исполнение и передачи между службами (раунд 15, CONTRACT §5.1) — чистые функции без БД.

Запись жалобы v2.1 = запись v2 + поля:
  service     — ведущая служба (id из lifecycle.SERVICES); старые экраны берут её через паспорт (assignee_id);
  services    — части служб [{service, role: lead|partner, status: todo|in_progress|done, note?, updated_at}];
  handoffs    — передачи [{at, from, to, reason, reason_code?, by_role}] — причина видна только сотрудникам;
  route_hint  — подсказка R04 POST /route: {services: [...], joint, source: model|rules, model_version}.

Правила (объяснимые; тесты — tests/civic/R09/test_r09v21_joint.py):
  1. Статус всей жалобы — по ведущей службе; «исправлено» — только когда все части done.
  2. Передача и новая служба НЕ трогают срок ответа жителю: due_at считается от подачи и не пересчитывается.
  3. Пустой services (записи до v2.1 и обычные жалобы одной службы) = одна часть ведущей службы, её статус — по
     статусу жалобы. Ведущая служба такой записи — как в FINAL-4: выбор сотрудника → таблица R08 → таблица R09.
  4. Жителю — кто и что делает («Водоканал — сделано · Дорожная служба — в работе») и «Передано: служба»; причины
     передач, роли и имена сотрудников — только акимату.
"""

from __future__ import annotations

from . import lifecycle
from . import record as rec

PART_STATUSES = ("todo", "in_progress", "done")
# Синонимы на входе (демо-мир R02, старые вызовы): статусы жалобы и задач кризиса R17 → статус части.
PART_ALIASES = {"new": "todo", "accepted": "todo", "waiting": "todo", "doing": "in_progress",
                "fixed": "done", "rejected": "todo"}
PART_ROLES = ("lead", "partner")
MAX_SERVICES = 3          # IDEA §2 B: «у обращения может быть 2–3 службы»
NOTE_MAX = lifecycle.WHAT_DONE_MAX
REASON_MIN, REASON_MAX = 3, 160
# Откуда взята ведущая служба. «table» — по таблице R08/R09 на момент подачи: такая служба следует за таблицей
# (правки акимата в R08 видны сразу, как в FINAL-4). Остальные — явный выбор, таблица их не меняет.
SERVICE_SOURCES = ("table", "staff", "handoff", "joint", "world")
EXPLICIT_SOURCES = lifecycle.EXPLICIT_SERVICE_SOURCES

# Причины передачи — чипы на экране сотрудника (ключи R11 handoff.reason.<id>; запасной текст — здесь и в
# complaint-strings.js). Видит только акимат; жителю — «Передано: служба».
HANDOFF_REASONS = {
    "other_service": {"ru": "Нужна другая служба", "kk": "Басқа қызмет керек"},
    "first_other_work": {"ru": "Сначала работы другой службы", "kk": "Алдымен басқа қызметтің жұмысы"},
    "not_our_zone": {"ru": "Не наша зона ответственности", "kk": "Біздің жауапкершілік аймағы емес"},
    "wrong_category": {"ru": "Неверная категория", "kk": "Санат қате таңдалған"},
}
# Служебные причины, которые пишет сам модуль (подсказка R04 принята, выбор в паспорте).
SYSTEM_REASONS = {
    "joint": {"ru": "Совместное исполнение", "kk": "Бірлескен орындау"},
    "passport": {"ru": "Выбор службы в паспорте", "kk": "Паспортта қызмет таңдалды"},
}

# Порядок шагов для правила «передача не двигает статус назад» (rejected — вне шкалы).
STATUS_ORDER = {"new": 0, "accepted": 1, "in_progress": 2, "fixed": 3}
_PART_FROM_COMPLAINT = {"new": "todo", "accepted": "todo", "in_progress": "in_progress", "fixed": "done",
                        "rejected": "todo"}


class JointError(rec.RecordError):
    """Ошибка проверки частей служб или передачи (422)."""


# ---------------------------------------------------------------- разбор входа
def part_status(value) -> str | None:
    """Статус части или None, если такого нет (синонимы — PART_ALIASES)."""
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    value = PART_ALIASES.get(value, value)
    return value if value in PART_STATUSES else None


def part_status_from_complaint(status: str | None) -> str:
    return _PART_FROM_COMPLAINT.get(status or "new", "todo")


def clean_note(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise JointError("Заметка — строка.", {"note": "строка"})
    return " ".join(value.split())[:NOTE_MAX] or None


def clean_reason(reason, code=None) -> tuple[str, str | None]:
    """(текст, код). Нужна причина: чип (код) или строка от 3 символов; чип без строки — его подпись."""
    if code is not None and code not in HANDOFF_REASONS and code not in SYSTEM_REASONS:
        raise JointError("Неизвестная причина передачи.", {"reason_code": ", ".join(HANDOFF_REASONS)})
    text = " ".join(reason.split())[:REASON_MAX] if isinstance(reason, str) else ""
    if reason is not None and not isinstance(reason, str):
        raise JointError("Причина — строка.", {"reason": "строка"})
    if not text and code is not None:
        text = (HANDOFF_REASONS.get(code) or SYSTEM_REASONS[code])["ru"]
    if len(text) < REASON_MIN:
        raise JointError("Укажите причину передачи.", {"reason": "выберите причину или напишите её словами"})
    return text, code


def parse_services(value) -> list[dict]:
    """[{service, role}] из запроса POST /services: 1–3 службы из справочника, ровно одна ведущая (lead)."""
    if not isinstance(value, list) or not value:
        raise JointError("Укажите службы.", {"services": "список {service, role}"})
    if len(value) > MAX_SERVICES:
        raise JointError(f"Не больше {MAX_SERVICES} служб на одно обращение.", {"services": f"до {MAX_SERVICES}"})
    out, seen = [], set()
    for index, item in enumerate(value):
        sid = item.get("service") if isinstance(item, dict) else item
        role = item.get("role", "lead" if index == 0 else "partner") if isinstance(item, dict) else \
            ("lead" if index == 0 else "partner")
        if sid not in lifecycle.SERVICES:
            raise JointError("Неизвестная служба.", {f"services[{index}].service": ", ".join(lifecycle.SERVICES)})
        if role not in PART_ROLES:
            raise JointError("Роль службы: ведущая или участвует.", {f"services[{index}].role": "lead | partner"})
        if sid in seen:
            raise JointError("Служба указана дважды.", {f"services[{index}].service": sid})
        seen.add(sid)
        out.append({"service": sid, "role": role})
    if sum(1 for item in out if item["role"] == "lead") != 1:
        raise JointError("Нужна ровно одна ведущая служба.", {"services": "одна role=lead"})
    out.sort(key=lambda item: item["role"] != "lead")          # ведущая — первой (устойчиво для участников)
    return out


def parse_route_hint(value) -> dict | None:
    """Подсказка R04 route(): {services: [{service, score?, why_ru?, why_kk?}] | [id], joint, model_version} →
    {services: [id], joint, source, model_version, why_ru?, why_kk?}. Мусор — None (подсказка не обязательна)."""
    if not isinstance(value, dict):
        return None
    ids, why_ru, why_kk = [], None, None
    for item in value.get("services") or []:
        sid = item.get("service") if isinstance(item, dict) else item
        if sid in lifecycle.SERVICES and sid not in ids:
            ids.append(sid)
            if isinstance(item, dict) and why_ru is None:
                why_ru = item.get("why_ru") if isinstance(item.get("why_ru"), str) else None
                why_kk = item.get("why_kk") if isinstance(item.get("why_kk"), str) else None
    if not ids:
        return None
    # R04 route() отдаёт и общее объяснение одной строкой (why_* / summary_*) — оно лучше объяснения первой службы.
    for key_ru, key_kk in (("why_ru", "why_kk"), ("summary_ru", "summary_kk")):
        if isinstance(value.get(key_ru), str) and value[key_ru].strip():
            why_ru = value[key_ru]
            why_kk = value.get(key_kk) if isinstance(value.get(key_kk), str) else why_kk
            break
    source = value.get("source")
    if source not in ("model", "rules"):
        source = "model" if value.get("model_version") else "rules"
    version = value.get("model_version")
    hint = {"services": ids[:MAX_SERVICES], "joint": bool(value.get("joint")) and len(ids) > 1,
            "source": source, "model_version": version[:80] if isinstance(version, str) else None}
    if why_ru:
        hint["why_ru"] = " ".join(why_ru.split())[:200]
    if why_kk:
        hint["why_kk"] = " ".join(why_kk.split())[:200]
    if isinstance(value.get("accepted_at"), str):
        hint["accepted_at"] = value["accepted_at"]
    return hint


# ---------------------------------------------------------------- миграция v2 → v2.1
def upgrade(record: dict) -> bool:
    """Запись v2 → v2.1 без потерь: только ДОБАВЛЯЕТ недостающие поля, существующие не меняет. -> изменилась ли.
    service — явная служба записи, иначе выбор сотрудника в паспорте, иначе таблица R09 (source «table» — такая
    служба в паспорте и частях по-прежнему следует за таблицей R08, как в FINAL-4)."""
    changed = False
    if record.get("service") not in lifecycle.SERVICES:
        chosen = (record.get("passport") or {}).get("assignee_id")
        explicit = lifecycle.explicit_service(record)
        if explicit:
            record["service"] = explicit
        elif chosen in lifecycle.SERVICES:
            record["service"] = chosen
            record.setdefault("service_source", "staff")
        else:
            record["service"] = lifecycle.default_service(record.get("category"), record.get("subtopic"))
        changed = True
    for key, default in (("service_source", "table"), ("services", None), ("handoffs", None), ("route_hint", None)):
        if key not in record:
            record[key] = [] if default is None and key != "route_hint" else default
            changed = True
    if record.get("schema") != rec.SCHEMA:
        record["schema"] = rec.SCHEMA
        changed = True
    return changed


# ---------------------------------------------------------------- ведущая служба и части
explicit_lead = lifecycle.explicit_service   # явная ведущая (части, передача, демо-мир) или None — «по таблице»


def lead_service(record: dict, assignee_lookup=None) -> str:
    """id ведущей службы: явная → выбор сотрудника в паспорте → таблица R08 → таблица R09 (как паспорт FINAL-4).
    Служба старой записи задана свободным текстом (без id) — служба по таблице R09."""
    sid = lifecycle.passport_assignee(record, assignee_lookup)["assignee_id"]
    if sid in lifecycle.SERVICES:
        return sid
    return lifecycle.default_service(record.get("category"), record.get("subtopic"))


def parts(record: dict, assignee_lookup=None) -> list[dict]:
    """Части служб, ведущая первой. Записи без частей — одна часть ведущей службы по статусу жалобы."""
    stored = [dict(p) for p in record.get("services") or [] if isinstance(p, dict) and p.get("service")]
    if stored:
        for part in stored:
            part["status"] = part_status(part.get("status")) or "todo"
            part["role"] = part.get("role") if part.get("role") in PART_ROLES else "partner"
        stored.sort(key=lambda p: p["role"] != "lead")
        return stored
    lead = lead_service(record, assignee_lookup)
    history = record.get("status_history") or []
    return [{"service": lead, "role": "lead", "status": part_status_from_complaint(record.get("status")),
             "updated_at": (history[-1].get("at") if history else record.get("created_at")), "implicit": True}]


def is_joint(record: dict) -> bool:
    return sum(1 for p in record.get("services") or [] if isinstance(p, dict) and p.get("service")) > 1


def waiting(parts_list: list[dict]) -> list[str]:
    """Службы, чья часть ещё не сделана (в порядке частей)."""
    return [p["service"] for p in parts_list if p.get("status") != "done"]


def status_after_parts(current: str, parts_list: list[dict]) -> str:
    """Статус жалобы после смены частей (правило 1). Переходы — только из record.TRANSITIONS.
    Все части done → fixed; ведущая сделала или в работе → in_progress; ведущая ещё не начала →
    new/accepted как были (жалобу «в работе» или «исправлено» — назад в «принято»)."""
    if current == "rejected" or not parts_list:
        return current
    lead = next((p for p in parts_list if p.get("role") == "lead"), parts_list[0])
    if all(p.get("status") == "done" for p in parts_list):
        target = "fixed"
    elif lead.get("status") in ("in_progress", "done"):
        target = "in_progress"
    else:
        target = current if current in ("new", "accepted") else "accepted"
    if target == current:
        return current
    if target in rec.TRANSITIONS.get(current, ()):
        return target
    # Нет прямого перехода (fixed → accepted): ближайший разрешённый — «в работе».
    return "in_progress" if "in_progress" in rec.TRANSITIONS.get(current, ()) else current


def combined_note(parts_list: list[dict]) -> str | None:
    """«Что сделали» для жителей, когда все части done: заметки служб по порядку, ведущая первой."""
    notes = [p["note"] for p in parts_list if p.get("note")]
    text = "; ".join(notes)
    return text[:lifecycle.WHAT_DONE_MAX] or None


# ---------------------------------------------------------------- проекции
def service_names(sid: str | None) -> dict:
    base = lifecycle.SERVICES.get(sid or "", {})
    return {"ru": base.get("ru"), "kk": base.get("kk")}


def staff_parts(record: dict, assignee_lookup=None) -> dict:
    """Акимату: части, передачи с причинами, подсказка R04, кого ждём."""
    items = parts(record, assignee_lookup)
    return {"lead": items[0]["service"] if items else None, "joint": len(items) > 1,
            "services": [{**p, "names": service_names(p["service"])} for p in items],
            "waiting": waiting(items) if len(items) > 1 else [],
            "handoffs": [dict(h) for h in record.get("handoffs") or []],
            "route_hint": record.get("route_hint")}


def resident_parts(record: dict, assignee_lookup=None, *, participant: bool = False) -> dict:
    """Жителю: какие службы работают и что с их частью; «Передано: …» без причин и ролей сотрудников.
    participant (автор и «Я тоже») видит и заметки служб («Трубу заменили») — как «что сделали»."""
    items = parts(record, assignee_lookup)
    services = []
    for p in items:
        view = {"service": p["service"], "role": p["role"], "status": p["status"], "updated_at": p.get("updated_at")}
        if participant and p.get("note"):
            view["note"] = p["note"]
        services.append(view)
    handoffs = [{"at": h.get("at"), "from": h.get("from"), "to": h.get("to")}
                for h in record.get("handoffs") or [] if h.get("to") in lifecycle.SERVICES]
    return {"joint": len(services) > 1, "services": services, "handoffs": handoffs}


def answer_at(record: dict) -> str | None:
    """Когда жителю ответили: первый шаг статуса после «new» (принято, в работе, исправлено, отклонено)."""
    for entry in (record.get("status_history") or [])[1:]:
        if entry.get("status") != "new" and not (entry.get("duplicate_of") or entry.get("unmerged_from")
                                                 or entry.get("separated_from")):
            return entry.get("at")
    return None
