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
# «Кому передано»: службы и таблица «категория/уточнение → служба» — КОПИЯ умолчаний R08
# (ui/civic_akim/routing.py @ 9dbd62c: SERVICES, DEFAULT_RULES; kk вычитан R11, словарь service.<id>).
# Общие названия — реальные организации не придумываем (POLISH_WAVE п. 7). В сборке R01 подключает таблицу R08
# с правками акимата: store.assignee_lookup = ui.civic_akim.routing.service_for (она имеет приоритет).
SERVICES = {
    "road": {"ru": "Дорожная служба", "kk": "Жол қызметі"},
    "traffic": {"ru": "Служба светофоров и разметки", "kk": "Бағдаршам және жол таңбасы қызметі"},
    "street_cleaning": {"ru": "Служба уборки улиц", "kk": "Көшелерді тазалау қызметі"},
    "transport": {"ru": "Служба общественного транспорта", "kk": "Қоғамдық көлік қызметі"},
    "lighting": {"ru": "Служба освещения", "kk": "Жарықтандыру қызметі"},
    "landscaping": {"ru": "Служба благоустройства", "kk": "Абаттандыру қызметі"},
    "greenery": {"ru": "Служба озеленения", "kk": "Көгалдандыру қызметі"},
    "waste": {"ru": "Оператор вывоза мусора", "kk": "Қоқыс шығару операторы"},
    "utilities": {"ru": "Служба ЖКХ", "kk": "ТКШ қызметі"},
    "heating": {"ru": "Теплосеть", "kk": "Жылу желісі"},
    "water": {"ru": "Водоканал", "kk": "Сумен жабдықтау қызметі"},
    "power": {"ru": "Электросети", "kk": "Электр желілері"},
    "gas": {"ru": "Газовая служба", "kk": "Газ қызметі"},
    "housing": {"ru": "Управляющая компания дома", "kk": "Үйді басқарушы компания"},
    "ecology": {"ru": "Служба экологии", "kk": "Экология қызметі"},
    "emergency": {"ru": "Служба спасения", "kk": "Құтқару қызметі"},
    "police": {"ru": "Полиция", "kk": "Полиция"},
    "animals": {"ru": "Служба отлова животных", "kk": "Жануарларды аулау қызметі"},
    "parking": {"ru": "Служба парковок", "kk": "Тұрақ қызметі"},
    "akimat": {"ru": "Аппарат акима района", "kk": "Аудан әкімінің аппараты"},
}
# Ключ — категория или «категория/уточнение»; уточнение, которого нет, идёт в службу категории.
SERVICE_RULES = {
    "roads": "road", "roads/traffic_light_broken": "traffic", "roads/traffic_light_timing": "traffic",
    "roads/intersection": "traffic", "roads/marking": "traffic",
    "snow_ice": "street_cleaning", "snow_ice/icicles": "housing",
    "sidewalks": "road", "sidewalks/crossing": "traffic",
    "transport": "transport",
    "lighting": "lighting", "lighting/wire_down": "power",
    "yards": "landscaping", "yards/trees_lawn": "greenery",
    "waste": "waste",
    "utilities": "utilities", "utilities/no_heating": "heating", "utilities/no_water": "water",
    "utilities/sewage": "water", "utilities/power_building": "power",
    "smell_air": "ecology", "smell_air/gas": "gas", "smell_air/smoke_fire": "emergency",
    "noise_safety": "police", "noise_safety/stray_dogs": "animals",
    "parking": "parking", "parking/sidewalk_parking": "police",
    "other": "akimat",
}


def default_service(category: str | None, subtopic: str | None) -> str:
    """id службы по таблице R09 (= умолчания R08): уточнение → категория → «Другое»."""
    if category and subtopic and f"{category}/{subtopic}" in SERVICE_RULES:
        return SERVICE_RULES[f"{category}/{subtopic}"]
    return SERVICE_RULES.get(category or "", SERVICE_RULES["other"])


def default_assignee(category: str | None, subtopic: str | None) -> str:
    """Название службы по-русски (для старых вызовов и текстов сотрудника)."""
    return SERVICES[default_service(category, subtopic)]["ru"]


def deadline(record: dict, now: datetime) -> dict | None:
    """Срок ответа службы в рабочих днях (workdays.deadline_info): ответ дан, когда жалобу приняли/взяли в работу."""
    answered = record.get("status") != "new"
    return workdays.deadline_info(rec.parse_iso(record.get("due_at")), now, done=answered)


def _assignee(record: dict, assignee_lookup) -> dict:
    """Кто отвечает: выбор сотрудника (id из SERVICES) → таблица R08 с правками акимата → таблица R09."""
    passport = record.get("passport") or {}
    category, subtopic = record.get("category"), record.get("subtopic")
    sid, names, source = passport.get("assignee_id"), None, None
    if sid in SERVICES:
        source = "staff"
    elif passport.get("assignee"):                        # свободный текст старых записей
        sid, names, source = None, {"ru": passport["assignee"], "name_edited": True}, "staff"
    elif assignee_lookup is not None:
        try:
            found = assignee_lookup(category, subtopic)
        except Exception:  # noqa: BLE001 — таблица R08 недоступна: берём таблицу R09
            found = None
        if isinstance(found, dict) and (found.get("id") or found.get("ru")):   # R08 service_for()
            sid, names, source = found.get("id"), found, "r08"
        elif isinstance(found, str) and found:                                 # R08 assignee_lookup() — имя
            sid, names, source = None, {"ru": found, "name_edited": True}, "r08"
    if source is None:
        sid, source = default_service(category, subtopic), "default"
    base = SERVICES.get(sid or "", {})
    names = names or {}
    return {"assignee_id": sid, "assignee": names.get("ru") or base.get("ru"),
            "assignee_kk": names.get("kk") or base.get("kk"),
            # Акимат переименовал службу (R08 name_edited): интерфейс показывает его название, а не service.<id>.
            "assignee_custom": bool(names.get("name_edited")), "assignee_source": source}


def passport_view(record: dict, now: datetime, assignee_lookup=None) -> dict:
    """«Паспорт решения» для карточки: кто отвечает, следующий шаг, два срока, задержка.
    next_step — текст сотрудника; без него интерфейс показывает шаг по статусу (ключ mine.passport.next_default.*)."""
    passport = dict(record.get("passport") or {})
    delay = passport.get("delay") or None
    next_update = rec.parse_iso((delay or {}).get("next_update_at"))
    return {
        **_assignee(record, assignee_lookup),
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
            # id для ссылки из уведомления (#mine/event=<id>): номер жалобы + вид + время — не меняется со временем.
            stamp = re.sub(r"[^0-9T]", "", event["at"])[:15]
            items.append({**event, "_order": order, "id": f"{record.get('code') or record['id']}.{event['kind']}.{stamp}",
                          "complaint_id": record["id"], "code": record.get("code"),
                          "relation": record.get("relation"), "category": record.get("category"),
                          "target": {k: v for k, v in (record.get("target") or {}).items()
                                     if k in ("kind", "id", "label_ru", "label_kk", "approximate")}})
    # Новые сверху; при одинаковом времени — более позднее по ходу жизни жалобы («проверено» выше «исправлено»).
    items.sort(key=lambda e: (e["at"], e["_order"]), reverse=True)
    for item in items:
        item.pop("_order")
    fixed_verified = sum(1 for r in records if (r.get("resolution") or {}).get("state") == "verified")
    return {"items": items, "summary": {"verified": fixed_verified, "waiting": waiting, "total": len(records)}}


# ---------------------------------------------------------------- акимат: «Обращения» (R11 IA_WAVE2 §2.5)
INBOX_TABS = ("new", "in_progress", "waiting_check", "overdue", "reopened")
_TAB_ORDER = ("reopened", "overdue", "waiting_check", "new", "in_progress")   # срочнее — раньше


def inbox_tab(record: dict, now: datetime) -> str | None:
    """Вкладка списка акимата для одной жалобы (одна, самая срочная) или None — решено/отклонено."""
    status = record.get("status")
    state = (record.get("resolution") or {}).get("state")
    if record.get("duplicate_of"):
        return None
    if status in rec.OPEN_STATUSES and state == "reopened":
        return "reopened"
    if status in rec.OPEN_STATUSES:
        info = deadline(record, now) or {}
        next_update = rec.parse_iso(((record.get("passport") or {}).get("delay") or {}).get("next_update_at"))
        if info.get("state") == "overdue" or (next_update and now > next_update):
            return "overdue"
        return "new" if status == "new" else "in_progress"
    if status == "fixed" and state == "reported":
        return "waiting_check"
    return None


def _deadline_rank(info: dict | None) -> tuple:
    """Какой срок показать у группы: просроченный сильнее, затем «сегодня», затем меньше всего дней осталось."""
    if not info:
        return (-1, 0)
    state = info.get("state")
    if state == "overdue":
        return (3, info.get("overdue_working_days") or 0)
    if state == "today":
        return (2, 0)
    if state == "ok":
        return (1, -(info.get("working_days_left") or 0))
    return (0, 0)                                         # ответ уже дан


def inbox(records: list[dict], now: datetime, tab: str | None = None) -> dict:
    """Список целей с открытыми обращениями (не отдельных жалоб): группа = цель + категория.
    -> {"counts": {вкладка: групп}, "items": [группа]} — items только выбранной вкладки (или все)."""
    groups: dict[tuple, dict] = {}
    for record in records:
        rtab = inbox_tab(record, now)
        if rtab is None:
            continue
        target = record.get("target") or {}
        key = (target.get("id") or record["id"], record.get("category"))
        group = groups.setdefault(key, {"key": f"{key[0]}|{key[1]}", "tab": rtab, "category": record.get("category"),
                                        "subtopic": record.get("subtopic"), "people": 0, "complaints": [],
                                        "target": {k: v for k, v in target.items()
                                                   if k in ("kind", "id", "label_ru", "label_kk", "approximate")},
                                        "point": record.get("point"), "deadline": None, "demo": True,
                                        "created_at": record.get("created_at")})
        if _TAB_ORDER.index(rtab) < _TAB_ORDER.index(group["tab"]):
            group["tab"] = rtab
        group["people"] += rec.reporters(record)
        group["demo"] = group["demo"] and bool(record.get("demo"))
        group["complaints"].append({"id": record["id"], "code": record.get("code"), "status": record.get("status"),
                                    "reporters": rec.reporters(record), "tab": rtab, "demo": bool(record.get("demo"))})
        info = deadline(record, now)
        if info and _deadline_rank(info) > _deadline_rank(group["deadline"]):
            group["deadline"] = info
        if group["subtopic"] is None and record.get("subtopic"):
            group["subtopic"] = record.get("subtopic")
        if (record.get("created_at") or "") < (group["created_at"] or "~"):
            group["created_at"] = record.get("created_at")
    counts = {name: 0 for name in INBOX_TABS}
    for group in groups.values():
        counts[group["tab"]] += 1
    items = [g for g in groups.values() if tab is None or g["tab"] == tab]
    # Сначала дольше всех просроченные, затем больше людей, затем старше.
    items.sort(key=lambda g: (-_deadline_rank(g["deadline"])[0] if (g["deadline"] or {}).get("state") == "overdue" else 0,
                              -((g["deadline"] or {}).get("overdue_working_days") or 0), -g["people"], g["created_at"] or ""))
    for group in items:
        group["complaints"].sort(key=lambda c: (_TAB_ORDER.index(c["tab"]), -c["reporters"]))
    return {"counts": counts, "items": items}
