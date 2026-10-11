"""Жизнь жалобы после отправки (POLISH_WAVE 1 и 2): срочные случаи, «служба сообщила — жители проверили»,
паспорт решения, обновления всем участникам, «что изменилось с вашим участием».

Чистые функции без БД — их используют store.py (запись), api.py (проекции) и соседи:
  R07 — heat_state(record, now) -> ключ из categories_v2.json → heat_states (или None = цвет по весу);
  R08 — deadline(record, now), resolution counts (verified / reopened / reported) для счётчиков.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from . import categories, workdays
from . import record as rec

# ---------------------------------------------------------------- срочные случаи (волна 1, п. 3)
# Слова в тексте, при которых до отправки показываем «Звоните N сейчас». Целые слова: «газон» и «газета» — не газ.
_GAS = re.compile(r"\bгаз(а|ом|у|ом)?\b|\bгаз\w* утечк|\bутечк\w* газ|\bгаз иіс|\bгаздың иіс", re.IGNORECASE)
_FIRE = re.compile(r"\bпожар\w*|\bзадымлен\w*|\bдым\b|\bдымит\w*|\bөрт\w*|\bтүтін\w*|\bжанып жатыр", re.IGNORECASE)
# «Горит/горят» — только не про свет: «не горят фонари» и «фонарь горит днём» — жалобы на освещение, не пожар.
_BURNS = re.compile(r"(?<!не )\bгор(ит|ят)\b|\bзагорел\w*", re.IGNORECASE)
_LIGHT_CONTEXT = re.compile(r"фонар|свет|ламп|освещ|шам\b|шамдар|жарық", re.IGNORECASE)
_WIRE = re.compile(r"оборван\w* провод|провод\w* оборван|обрыв\w* провод|провод\w* (лежит|висит|упал)|"
                   r"сым үзіл|үзілген сым|сым жерде", re.IGNORECASE)


def emergency(category: str | None, subtopic: str | None, text: str | None) -> dict | None:
    """{"phone": "104"|"112", "reason": "subtopic"|"text"} или None. Уточнение с emergency_phone важнее слов."""
    if category and subtopic:
        found = categories.subtopic(category, subtopic)
        if found and found.get("emergency_phone"):
            return {"phone": found["emergency_phone"], "reason": "subtopic"}
    value = (text or "").replace("ё", "е")
    if _GAS.search(value):
        return {"phone": "104", "reason": "text"}
    if _WIRE.search(value) or _FIRE.search(value):
        return {"phone": "112", "reason": "text"}
    if _BURNS.search(value) and not _LIGHT_CONTEXT.search(value):
        return {"phone": "112", "reason": "text"}
    return None


# ---------------------------------------------------------------- «исправлено — проверьте» (волна 2, п. 1)
VERIFY_ANSWERS = ("yes", "no", "cant")
WHAT_DONE_MAX = 200
VERIFIED_DAYS = 7  # categories_v2.json → heat_states.verified_fixed.days_visible (проверяется тестом)


def new_resolution(previous: dict | None, at: str, what_done: str | None, actor: str | None,
                   photos: list[str] | None) -> dict:
    """Новый «раунд» после «Служба сообщила об устранении». Раунд растёт при каждом повторном «Исправлено»:
    голоса прошлого раунда не переносятся (житель проверяет новый ремонт)."""
    round_no = int((previous or {}).get("round") or 0) + 1
    return {"round": round_no, "state": "reported", "reported_at": at, "what_done": what_done,
            "by": actor, "photos_after": list(photos or []),
            "votes": {"yes": 0, "no": 0, "cant": 0}, "verified_at": None, "reopened_at": None,
            "reopen_count": int((previous or {}).get("reopen_count") or 0)}


def heat_state(record: dict, now: datetime) -> str | None:
    """Ключ heat_states для R07: reported_fixed | verified_fixed | reopened | None (обычный цвет по весу).
    «no_data» — понятие карты (нет жалоб за период), его определяет R07, не запись."""
    resolution = record.get("resolution") or {}
    status = record.get("status")
    if status == "fixed":
        if resolution.get("state") == "verified":
            verified = rec.parse_iso(resolution.get("verified_at"))
            if verified is not None and now - verified <= timedelta(days=VERIFIED_DAYS):
                return "verified_fixed"
            return None  # проверено давно — цель остывает как обычно
        return "reported_fixed"
    if status in rec.OPEN_STATUSES and resolution.get("state") == "reopened":
        return "reopened"
    return None


def public_resolution(record: dict) -> dict | None:
    """Для карты и чужих жителей: состояние и числа голосов, без исполнителей."""
    resolution = record.get("resolution")
    if not resolution:
        return None
    return {"state": resolution.get("state"), "round": resolution.get("round"),
            "reported_at": resolution.get("reported_at"), "verified_at": resolution.get("verified_at"),
            "reopened_at": resolution.get("reopened_at"), "votes": dict(resolution.get("votes") or {}),
            "reopen_count": resolution.get("reopen_count", 0)}


def participant_resolution(record: dict) -> dict | None:
    """Автору и «Я тоже»: плюс «что сделали» и фото «после» (до/после), без имени сотрудника."""
    view = public_resolution(record)
    if view is None:
        return None
    view["what_done"] = record["resolution"].get("what_done")
    view["photos_after"] = list(record["resolution"].get("photos_after") or [])
    return view


# ---------------------------------------------------------------- паспорт решения (волна 2, п. 2; волна 1, п. 7)
PASSPORT_TEXT_MAX = 160
# Общие названия служб (POLISH_WAVE п. 7: реальные организации не придумывать). Таблицу ведёт R08; это запасной
# вариант R09 — пока таблицы R08 нет в сборке. assignee_lookup(category, subtopic) из R08 имеет приоритет.
DEFAULT_SERVICES = {
    "roads": "Дорожная служба", "snow_ice": "Дорожная служба", "sidewalks": "Служба благоустройства",
    "transport": "Служба пассажирского транспорта", "lighting": "Служба освещения",
    "yards": "Служба благоустройства", "waste": "Оператор вывоза мусора", "utilities": "Теплосеть или водоканал",
    "smell_air": "Служба экологии", "noise_safety": "Полиция", "parking": "Полиция", "other": "Акимат района",
}
# id уточнений — из categories_v2.json (проверяет тест test_subtopic_services_use_real_ids).
SUBTOPIC_SERVICES = {"no_heating": "Теплосеть", "no_water": "Водоканал", "sewage": "Водоканал",
                     "power_building": "Служба электроснабжения", "gas": "Газовая служба",
                     "stray_dogs": "Служба отлова бездомных животных"}


# Казахские подписи тех же общих названий (перевод R09 — сверить R11; таблица R08 может дать свои ru/kk).
SERVICES_KK = {
    "Дорожная служба": "Жол қызметі", "Служба благоустройства": "Абаттандыру қызметі",
    "Служба пассажирского транспорта": "Жолаушылар көлігі қызметі", "Служба освещения": "Жарықтандыру қызметі",
    "Оператор вывоза мусора": "Қоқыс шығару операторы", "Теплосеть или водоканал": "Жылу желісі немесе су арнасы",
    "Служба экологии": "Экология қызметі", "Полиция": "Полиция", "Акимат района": "Аудан әкімдігі",
    "Теплосеть": "Жылу желісі", "Водоканал": "Су арнасы", "Служба электроснабжения": "Электрмен жабдықтау қызметі",
    "Газовая служба": "Газ қызметі", "Служба отлова бездомных животных": "Қаңғыбас жануарларды аулау қызметі",
}


def default_assignee(category: str | None, subtopic: str | None) -> str | None:
    if subtopic and subtopic in SUBTOPIC_SERVICES:
        return SUBTOPIC_SERVICES[subtopic]
    return DEFAULT_SERVICES.get(category or "")


def deadline(record: dict, now: datetime) -> dict | None:
    """Срок ответа службы в рабочих днях (workdays.deadline_info): ответ дан, когда жалобу приняли/взяли в работу."""
    answered = record.get("status") != "new"
    return workdays.deadline_info(rec.parse_iso(record.get("due_at")), now, done=answered)


def passport_view(record: dict, now: datetime, assignee_lookup=None) -> dict:
    """«Паспорт решения» для карточки: кто отвечает, следующий шаг, два срока, задержка.
    next_step — текст сотрудника; без него интерфейс показывает шаг по статусу (ключ complaint.passport.step.*)."""
    passport = dict(record.get("passport") or {})
    assignee = passport.get("assignee")
    assignee_kk = None
    source = "staff" if assignee else None
    if not assignee and assignee_lookup is not None:
        try:
            found = assignee_lookup(record.get("category"), record.get("subtopic"))
            # R08 может вернуть строку или {"ru": ..., "kk": ...}.
            if isinstance(found, dict):
                assignee, assignee_kk = found.get("ru"), found.get("kk")
            else:
                assignee = found
            source = "r08" if assignee else None
        except Exception:  # noqa: BLE001 — таблица R08 недоступна: берём общий вариант
            assignee = None
    if not assignee:
        assignee = default_assignee(record.get("category"), record.get("subtopic"))
        source = "default" if assignee else None
    if assignee and not assignee_kk:
        assignee_kk = SERVICES_KK.get(assignee)
    delay = passport.get("delay") or None
    next_update = rec.parse_iso((delay or {}).get("next_update_at"))
    return {
        "assignee": assignee, "assignee_kk": assignee_kk, "assignee_source": source,
        "next_step": passport.get("next_step"),
        "response_due": record.get("due_at"),
        "deadline": deadline(record, now),
        "fix_eta": passport.get("fix_eta"),            # «YYYY-MM-DD» или None = «пока не определено»
        "delay": delay,
        # Просроченное обновление видит руководитель (R08): обещали обновить к дате — и не обновили.
        "update_overdue": bool(next_update and now > next_update and record.get("status") in rec.OPEN_STATUSES),
        "updated_at": passport.get("updated_at"),
    }


# ---------------------------------------------------------------- «что изменилось с вашим участием» (волна 2, п. 10)
def _events(record: dict) -> list[dict]:
    """Что произошло с жалобой, понятными жителю событиями (без имён сотрудников и служебных заметок)."""
    out = []
    history = record.get("status_history") or []
    for index, entry in enumerate(history):
        if index == 0:
            continue  # «new» при создании — это действие самого жителя
        if entry.get("duplicate_of") or entry.get("unmerged_from"):
            continue  # объединение и разъединение — служебные действия, жителю не показываем
        kind = "reopened" if entry.get("reopened_by_residents") else "status"
        if kind:
            out.append({"at": entry["at"], "kind": kind, "status": entry.get("status")})
    for update in record.get("updates") or []:
        if update.get("kind") in ("note", "passport"):
            out.append({"at": update["at"], "kind": update["kind"], "text": update.get("text")})
    resolution = record.get("resolution") or {}
    if resolution.get("verified_at"):
        out.append({"at": resolution["verified_at"], "kind": "verified"})
    return out


def changes(records: list[dict], since: str | None) -> dict:
    """Изменения по жалобам устройства (автор и «Я тоже») после since (ISO) — новые сверху, и итог одной строкой."""
    edge = rec.parse_iso(since) if since else None
    items = []
    waiting = 0
    for record in records:
        if record.get("status") in rec.OPEN_STATUSES or (record.get("status") == "fixed"
                                                         and (record.get("resolution") or {}).get("state") == "reported"):
            waiting += 1
        for order, event in enumerate(_events(record)):
            moment = rec.parse_iso(event["at"])
            if edge is not None and (moment is None or moment <= edge):
                continue
            items.append({**event, "_order": order, "complaint_id": record["id"], "code": record.get("code"),
                          "relation": record.get("relation"), "category": record.get("category"),
                          "target": {k: v for k, v in (record.get("target") or {}).items()
                                     if k in ("kind", "id", "label_ru", "label_kk", "approximate")}})
    # Новые сверху; при одинаковом времени — более позднее по ходу жизни жалобы («проверено» выше «исправлено»).
    items.sort(key=lambda e: (e["at"], e["_order"]), reverse=True)
    for item in items:
        item.pop("_order")
    fixed_verified = sum(1 for r in records if (r.get("resolution") or {}).get("state") == "verified")
    return {"items": items, "summary": {"verified": fixed_verified, "waiting": waiting, "total": len(records)}}
