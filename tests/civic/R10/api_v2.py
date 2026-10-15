"""R10 · раунд 15 · приёмка новых маршрутов HTTP API v2 (CONTRACT §7) на сборке R01.

    python3 tests/civic/R10/api_v2.py --root <папка сборки> [--no-world] [--out <папка отчёта>]
    R10_ROOT=<сборка> python3 -m pytest -q tests/civic/R10/test_r10_api_v2.py     # жёсткие правила (см. там)

Что проверяет для каждой пары «метод + путь» из таблицы §7 (46 пар, роли R03 R04 R06 R07 R08 R09 R12 R13 R16 R17):
  1. Маршрут есть в шлюзе: DELETE по пути → 405 с Allow, где есть нужный метод (404 — маршрута нет: R01, §7
     «в первый же час добавляет все строки»).
  2. Модуля нет → 503 {"error": "module_not_ready", "message": по-русски, "role": роль из §7}. Это PASS: так и
     должно быть, пока роль не сдала модуль («ждёт модуль» в сводке). module_failed — FAIL: модуль есть, но упал.
  3. Модуль есть → доступ: маршрут сотрудника без входа — 401/403; изменяющий запрос сотрудника без CSRF — 403;
     маршрут жителя без X-Birge-Device — 4xx с понятным текстом; открытый маршрут — 200.
  4. Ошибки понятные: JSON {"error": код, "message": текст по-русски} (шлюз) или {"ok": false, "error": {...}}
     (сервис), без следов Python; ни одного 500 на примерах из интерфейса и на пустом теле.
  5. Записи — по CONTRACT §5 (5.2 инициатива, 5.3 двор, 5.4 профиль службы, 5.5 кризис, 5.6 работа и конфликт,
     5.7 встреча, 5.8 событие ленты); приватность §10: нет устройств, телефонов, ИИН и e-mail в ответах жителю,
     членство и «Я приду» — только числа; «Я приду» с одного устройства считается один раз.
  6. Прежние маршруты FINAL-4 на месте и в том же состоянии (fixtures/final4_v2_modules.json).
Статусы строк: PASS, FAIL (с владельцем), NOT_RUN (нечего проверять — с причиной). Код возврата 1 при любом FAIL.
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stand import Stand  # noqa: E402

V2 = "/api/civic/v2"
HERE = Path(__file__).resolve().parent
FINAL4_MODULES = HERE / "fixtures" / "final4_v2_modules.json"

# CONTRACT §3: один справочник служб (R09 SERVICES = R08 routing). Новых id не придумывать.
SERVICES = frozenset("road traffic street_cleaning transport lighting landscaping greenery waste utilities heating "
                     "water power gas housing ecology emergency police animals parking akimat".split())
ASTANA = (70.9, 50.9, 71.9, 51.4)
CYR = re.compile(r"[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]")
PY_TRACE = re.compile(r"Traceback|File \"|line \d+, in |Error\(|Exception\(|KeyError|NoneType|sqlite3\.")
PHONE = re.compile(r"(?:\+7|\b8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}\b")
IIN = re.compile(r"(?<![\w-])\d{12}(?![\w-])")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")


@dataclass(frozen=True)
class Route:
    method: str
    path: str          # шаблон: {initiative} {yard} {incident} {meeting} {complaint} {idea}
    role: str          # владелец по CONTRACT §7
    who: str           # all — все · resident — житель (устройство) · staff — сотрудник (сессия + CSRF) · author — автор или сотрудник
    query: str = ""    # пример параметров GET «как в интерфейсе»
    kind: str = ""     # чем проверять ответ: initiative(s) yard agencies board handoffs incident(s) events works conflicts replay meeting(s) route moderate notifications ask


def _iso(days=0.0, hours=0.0):
    return (datetime.now(timezone.utc) + timedelta(days=days, hours=hours)).replace(microsecond=0).isoformat()


def _date(days=0):
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


ROUTES = (
    # R16 «Сделаем вместе» и «Мой двор» — ui.civic_together
    Route("GET", "together/initiatives", "R16", "all", "status=published", "initiatives"),
    Route("POST", "together/initiatives", "R16", "resident", "", "initiative"),
    Route("GET", "together/initiatives/{initiative}", "R16", "all", "", "initiative"),
    Route("POST", "together/initiatives/{initiative}/join", "R16", "resident"),
    Route("POST", "together/initiatives/{initiative}/leave", "R16", "resident"),
    Route("POST", "together/initiatives/{initiative}/support", "R16", "staff"),
    Route("POST", "together/initiatives/{initiative}/moderate", "R16", "staff"),
    Route("POST", "together/initiatives/{initiative}/report", "R16", "author"),
    Route("GET", "together/yards/{yard}", "R16", "all", "", "yard"),
    Route("POST", "together/yards/{yard}/join", "R16", "resident"),
    Route("POST", "together/yards/{yard}/leave", "R16", "resident"),
    Route("GET", "together/updates", "R16", "resident", "since={since}", "events"),
    # R17 «Штаб ведомств» и кризисный штаб — ui.civic_agencies
    Route("GET", "agencies", "R17", "all", "", "agencies"),
    Route("GET", "agencies/board", "R17", "staff", "days=30&district=nura", "board"),
    Route("GET", "agencies/joint", "R17", "staff", "", "joint"),
    Route("GET", "agencies/handoffs", "R17", "staff", "days=30", "handoffs"),
    Route("GET", "incidents", "R17", "all", "", "incidents"),
    Route("GET", "incidents/{incident}", "R17", "all", "", "incident"),
    Route("POST", "incidents", "R17", "staff", "", "incident"),
    Route("POST", "incidents/{incident}/task", "R17", "staff"),
    Route("POST", "incidents/{incident}/update", "R17", "staff"),
    Route("POST", "incidents/{incident}/close", "R17", "staff"),
    Route("GET", "incidents/updates", "R17", "resident", "since={since}", "events"),
    # R09 совместное исполнение — ui.civic_feedback.v2.integration
    Route("POST", "complaints/{complaint}/handoff", "R09", "staff"),
    Route("POST", "complaints/{complaint}/services", "R09", "staff"),
    Route("POST", "complaints/{complaint}/part", "R09", "staff"),
    # R12 календарь работ — engine.civic_geo.api
    Route("GET", "works-calendar", "R12", "staff", "from={from}&to={to}&district=nura", "works"),
    Route("GET", "works-conflicts", "R12", "staff", "from={from}&to={to}&district=nura", "conflicts"),
    # R07 хроника — ui.civic_heat.api
    Route("GET", "heat/replay", "R07", "all", "from={from_week}&to={today}&step=day&district=nura", "replay"),
    # R08 ситуационный центр — ui.civic_akim.api
    Route("GET", "akim/board", "R08", "staff", "", "object"),
    Route("GET", "akim/week", "R08", "staff", "date={today}", "object"),
    # R13 встречи с акимом — ui.civic_meetings
    Route("GET", "meetings", "R13", "all", "", "meetings"),
    Route("GET", "meetings/{meeting}", "R13", "all", "", "meeting"),
    Route("GET", "meetings/updates", "R13", "all", "since={since}", "events"),
    Route("POST", "meetings", "R13", "staff", "", "meeting"),
    Route("POST", "meetings/{meeting}/order", "R13", "staff"),
    Route("POST", "meetings/{meeting}/result", "R13", "staff"),
    Route("POST", "meetings/{meeting}/register", "R13", "resident"),
    Route("POST", "meetings/{meeting}/question", "R13", "resident"),
    # R04 ИИ для служб — ui.civic_ml_api
    Route("POST", "route", "R04", "all", "", "route"),
    Route("POST", "reply-draft", "R04", "staff", "", "object"),
    Route("POST", "moderate", "R04", "all", "", "moderate"),
    # R03 ИИ-аналитик — agent.civic_assistant.api
    Route("POST", "assistant/ask", "R03", "staff", "", "ask"),
    # R06 лента уведомлений и идея → инициатива — ui.civic_store.v2
    Route("GET", "notifications", "R06", "resident", "since={since}", "events"),
    Route("POST", "notifications/read", "R06", "resident"),
    Route("POST", "ideas/{idea}/to-initiative", "R06", "staff"),
)

PROBE = "r10-probe"
# 404 «адрес не найден» от модуля (а не «запись не найдена»): путь модулю неизвестен.
ROUTE_404 = re.compile(r"адрес|нет такого|unknown (route|path)", re.I)  # id по правилу CIVIC_ID, которого нет в базе: маршрут должен ответить 404 / 503, а не 500


def bodies(ids):
    """Примеры тел «как в интерфейсе» (форматы CONTRACT §5). Модуль вправе отказать 400 — но не упасть 500."""
    yard = ids.get("yard") or "yard-r10-probe"
    point = ids.get("_yard_point") or [71.4065, 51.1312]  # точка во дворе (R16 проверяет: «далеко от двора» — 422)
    return {
        "together/initiatives": {
            "kind": "cleanup", "title": "Субботник во дворе (проверка R10)", "lang": "ru",
            "text": "Соберёмся в субботу в 10:00, уберём двор. Возьмите перчатки.",
            "target": {"kind": "area", "id": yard}, "point": point, "district": "nura",
            "starts_at": _iso(2), "ends_at": _iso(2, 3), "bring": ["перчатки", "мешки"]},
        "together/initiatives/{initiative}/join": {},
        "together/initiatives/{initiative}/leave": {},
        "together/initiatives/{initiative}/support": {"inventory": True, "pickup_service": "waste",
                                                      "note": "Мешки и вывоз в 14:00"},
        "together/initiatives/{initiative}/moderate": {"action": "publish"},
        "together/initiatives/{initiative}/report": {"text": "Убрали двор и посадили 6 саженцев", "photo_ids": []},
        "together/yards/{yard}/join": {},
        "together/yards/{yard}/leave": {},
        # Не буран в Нуре: он уже идёт в демо-мире (сцена 9), второй такой же модуль справедливо отклонит (409).
        "incidents": {"kind": "water_outage", "title_ru": "Прорыв водопровода (проверка R10)",
                      "title_kk": "Су құбырының жарылуы (R10 тексеруі)", "zone": {"kind": "district", "district": "esil"}},
        "incidents/{incident}/task": {"service": "street_cleaning", "text_ru": "Расчистить дороги к школам",
                                      "text_kk": "Мектептерге апаратын жолдарды тазарту"},
        "incidents/{incident}/update": {"text_ru": "Дороги расчищены на 60 %", "text_kk": "Жолдар 60 % тазартылды",
                                        "public": True},
        # Запись §5.5 хранит result {text_ru, text_kk}; тело запроса CONTRACT не задаёт — даём оба вида (R17: result_ru/kk).
        "incidents/{incident}/close": {"result": {"text_ru": "Последствия бурана устранены", "text_kk": "Боран салдары жойылды"},
                                       "result_ru": "Последствия бурана устранены", "result_kk": "Боран салдары жойылды"},
        "complaints/{complaint}/handoff": {"to": "water", "reason": "Сначала нужна замена трубы"},
        "complaints/{complaint}/services": {"services": [{"service": "water", "role": "lead"},
                                                         {"service": "road", "role": "partner"}]},
        "complaints/{complaint}/part": {"service": "water", "status": "done", "note": "Трубу заменили"},
        "meetings": {"district": "nura", "title_ru": "Встреча акима района с жителями (проверка R10)",
                     "title_kk": "Аудан әкімінің тұрғындармен кездесуі (R10 тексеруі)", "at": _iso(5),
                     "place": {"kind": "object", "id": "osm-node-4109037549", "label_ru": "Остановка «Хан Шатыр»",
                               "label_kk": "«Хан Шатыр» аялдамасы"}},
        "meetings/{meeting}/order": {"text_ru": "Восстановить освещение у остановки",
                                     "text_kk": "Аялдама жанындағы жарықты қалпына келтіру",
                                     "service": "lighting", "due": _date(14)},
        "meetings/{meeting}/result": {"text_ru": "Встреча прошла, поручения даны", "text_kk": "Кездесу өтті, тапсырмалар берілді",
                                      "result_ru": "Встреча прошла, поручения даны",
                                      "result_kk": "Кездесу өтті, тапсырмалар берілді"},
        "meetings/{meeting}/register": {},
        "meetings/{meeting}/question": {"text": "Когда починят освещение у остановки?", "lang": "ru"},
        "route": {"text": "Яма после раскопок: Водоканал менял трубу, асфальт не восстановили", "lang": "ru"},
        "reply-draft": {"complaint_id": ids.get("complaint") or "c-r10probe0001", "lang": "ru"},
        "moderate": {"text": "Звоните мне +7 701 123 45 67, ИИН 900101300123, почта test@example.com",
                     "lang": "ru"},
        "assistant/ask": {"question": "Сколько жалоб в Нуре за неделю и сколько из них просрочено?", "lang": "ru"},
        "notifications/read": {"ids": []},
        "ideas/{idea}/to-initiative": {"kind": "greening", "starts_at": _iso(3)},
    }


# ------------------------------------------------------------------------------------------------ разбор ответов
LIST_KEYS = ("items", "initiatives", "incidents", "meetings", "agencies", "services", "profiles", "works",
             "conflicts", "frames", "events", "updates", "notifications", "rows", "handoffs", "joint", "results")


def unwrap(body):
    if isinstance(body, dict) and "ok" in body and "data" in body:
        return body["data"]
    return body


def records(body, *prefer):
    """Список записей из ответа: сам список, или первый список словарей по ключам prefer / LIST_KEYS."""
    body = unwrap(body)
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in (*prefer, *LIST_KEYS):
            value = body.get(key)
            if isinstance(value, list):
                return value
    return None


def record(body, *prefer):
    """Одна запись: {"initiative": {...}} / {"item": {...}} / сама запись."""
    body = unwrap(body)
    if isinstance(body, dict):
        for key in (*prefer, "item", "record"):
            if isinstance(body.get(key), dict):
                return body[key]
    return body if isinstance(body, dict) else None


def error_info(reply):
    """(код, текст) ошибки из ответа шлюза {"error","message"} или сервиса {"ok": false, "error": {...}}."""
    body = reply.body
    if not isinstance(body, dict):
        return None, None
    err, msg = body.get("error"), body.get("message")
    if isinstance(err, dict):
        return err.get("code"), msg or err.get("message")
    return err, msg


def understandable(reply):
    """Ошибка понятна человеку: есть код и текст по-русски, без следов Python."""
    code, msg = error_info(reply)
    if not isinstance(code, str) or not code:
        return False, "нет кода ошибки"
    if not isinstance(msg, str) or not CYR.search(msg):
        return False, f"нет понятного текста по-русски ({code})"
    if PY_TRACE.search(msg):
        return False, f"в тексте следы Python: {msg[:120]}"
    return True, f"{code}: {msg[:80]}"


def walk(obj, path=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from walk(value, f"{path}.{key}")
            yield path, key, value
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from walk(value, f"{path}[{i}]")


def privacy_issues(obj):
    """§10: устройства не отдаются наружу; в текстах жителю — ни телефонов, ни ИИН, ни e-mail."""
    issues = []
    for path, key, value in walk(obj):
        low = str(key).lower()
        if "device" in low and value not in (None, "", [], {}):
            issues.append(f"{path}.{key}: устройство в ответе")
        if low in ("members", "joined", "registered") and isinstance(value, list):
            issues.append(f"{path}.{key}: список людей вместо числа")
        if isinstance(value, str) and (" " in value or CYR.search(value)):
            for name, rx in (("телефон", PHONE), ("ИИН", IIN), ("e-mail", EMAIL)):
                if rx.search(value):
                    issues.append(f"{path}.{key}: {name} в тексте «{value[:60]}»")
    return issues[:10]


def _enum(rec, key, allowed, errors, required=True):
    value = rec.get(key)
    if value is None:
        if required:
            errors.append(f"нет {key}")
    elif value not in allowed:
        errors.append(f"{key}={value!r} не из {sorted(allowed)}")


def _int(rec, key, errors, required=True):
    value = rec.get(key)
    if value is None:
        if required:
            errors.append(f"нет {key}")
    elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
        errors.append(f"{key} не целое ≥ 0: {value!r}")


def _str(rec, key, errors, required=True):
    value = rec.get(key)
    if value is None:
        if required:
            errors.append(f"нет {key}")
    elif not isinstance(value, str) or not value.strip():
        errors.append(f"{key} пусто")


def _time(rec, key, errors, required=True):
    value = rec.get(key)
    if value is None:
        if required:
            errors.append(f"нет {key}")
        return
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{key} не ISO 8601: {value!r}")
        return
    if len(str(value)) > 10 and parsed.tzinfo is None:
        errors.append(f"{key} без пояса: {value!r}")


def _target(rec, key, errors, required=True):
    target = rec.get(key)
    if target is None:
        if required:
            errors.append(f"нет {key}")
        return
    if not isinstance(target, dict) or target.get("kind") not in ("object", "segment", "area") or not target.get("id"):
        errors.append(f"{key} не по §4: {target!r}"[:120])


def _demo(rec, errors, world):
    if world and rec.get("demo") is not True and rec.get("source") != "real":
        errors.append("синтетика без demo: true")


def check_initiative(rec, world=False):
    e = []
    _str(rec, "id", e)
    _enum(rec, "kind", {"cleanup", "greening", "snow", "repair", "help", "other"}, e)
    _str(rec, "title", e)
    _target(rec, "target", e)
    _enum(rec, "status", {"on_review", "published", "done", "cancelled", "hidden"}, e)
    _int(rec, "joined", e)
    _time(rec, "starts_at", e, required=False)
    point = rec.get("point")
    if point is not None and not (isinstance(point, list) and len(point) == 2
                                  and ASTANA[0] <= point[0] <= ASTANA[2] and ASTANA[1] <= point[1] <= ASTANA[3]):
        e.append(f"point вне Астаны: {point!r}")
    support = rec.get("support")
    if isinstance(support, dict) and support.get("pickup_service") not in (None, *SERVICES):
        e.append(f"support.pickup_service не из §3: {support.get('pickup_service')!r}")
    _demo(rec, e, world)
    return e


def check_yard(rec, world=False):
    e = []
    _str(rec, "id", e)
    if isinstance(rec.get("id"), str) and not rec["id"].startswith("yard-"):
        e.append(f"id двора не yard-…: {rec['id']}")
    _str(rec, "label_ru", e)
    _str(rec, "label_kk", e)
    _int(rec, "members", e)
    captain = rec.get("captain")
    if captain is not None and not (isinstance(captain, dict) and isinstance(captain.get("display_name"), str)):
        e.append(f"captain не {{display_name, since}}: {captain!r}"[:120])
    return e


def check_agency(rec, world=False):
    e = []
    _enum(rec, "id", SERVICES, e)
    _enum(rec, "kind", {"utility", "road", "cleaning", "transport", "safety", "social", "admin"}, e)
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(rec.get("color", ""))):
        e.append(f"color не #rrggbb: {rec.get('color')!r}")
    _int(rec, "sla_answer_days", e)
    _int(rec, "sla_fix_days", e)
    return e


def check_incident(rec, world=False, public=True):
    e = []
    _str(rec, "id", e)
    _enum(rec, "kind", {"blizzard", "heat_outage", "water_outage", "flood", "other"}, e)
    _str(rec, "title_ru", e)
    _str(rec, "title_kk", e)
    zone = rec.get("zone")
    if not isinstance(zone, dict) or zone.get("kind") not in ("district", "targets", "polygon"):
        e.append(f"zone не по §5.5: {zone!r}"[:120])
    _time(rec, "started_at", e)
    _enum(rec, "status", {"active", "closed"}, e)
    for task in rec.get("tasks") or []:
        if isinstance(task, dict):
            _enum(task, "service", SERVICES, e)
            _enum(task, "status", {"todo", "doing", "done"}, e)
    for upd in rec.get("updates") or []:
        if public and isinstance(upd, dict) and upd.get("public") is False:
            e.append("в публичном ответе обновление public: false")
    _demo(rec, e, world)
    return e


def check_meeting(rec, world=False):
    e = []
    _str(rec, "id", e)
    _str(rec, "title_ru", e)
    _str(rec, "title_kk", e)
    _time(rec, "at", e)
    _int(rec, "registered", e)
    for order in rec.get("orders") or []:
        if isinstance(order, dict):
            _enum(order, "service", SERVICES, e)
            _enum(order, "status", {"todo", "in_progress", "done"}, e)
            _str(order, "text_ru", e)
            _str(order, "text_kk", e)
    _demo(rec, e, world)
    return e


def check_event(rec, world=False):
    e = []
    _str(rec, "id", e)
    _time(rec, "at", e)
    _str(rec, "title_ru", e)
    _str(rec, "title_kk", e)
    link = rec.get("link")
    if link is not None and not (isinstance(link, str) and link.startswith("#")):
        e.append(f"link не «#раздел/…»: {link!r}")
    return e


def check_work(rec, world=False):
    e = []
    _enum(rec, "service", SERVICES, e)
    _enum(rec, "kind", {"dig", "surface", "closure", "landscape", "lighting", "other"}, e)
    for key in ("starts_on", "ends_on"):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(rec.get(key, ""))):
            e.append(f"{key} не ГГГГ-ММ-ДД: {rec.get(key)!r}")
    if not isinstance(rec.get("segments"), list):
        e.append("нет segments (участки улиц)")
    _enum(rec, "source", {"real", "demo"}, e)
    return e


def check_conflict(rec, world=False):
    e = []
    _str(rec, "id", e)
    _enum(rec, "kind", {"dig_after_surface", "parallel_closures", "same_segment_overlap"}, e)
    if not (isinstance(rec.get("works"), list) and len(rec["works"]) >= 2):
        e.append("works: меньше двух работ")
    _enum(rec, "severity", {"high", "medium"}, e)
    _str(rec, "advice_ru", e)
    _str(rec, "advice_kk", e)
    return e


CHECKERS = {"initiative": check_initiative, "initiatives": check_initiative, "yard": check_yard,
            "agencies": check_agency, "incident": check_incident, "incidents": check_incident,
            "meeting": check_meeting, "meetings": check_meeting, "events": check_event,
            "works": check_work, "conflicts": check_conflict}
SINGLE = {"initiative": ("initiative",), "yard": ("yard",), "incident": ("incident",), "meeting": ("meeting",)}


# ------------------------------------------------------------------------------------------------ проверка
class ApiCheck:
    def __init__(self, stand: Stand, world: bool):
        self.s, self.world = stand, world
        token = secrets.token_hex(4)
        self.anon = stand.client()
        self.res = stand.client(device=f"r10-api-res1-{token}")
        self.res2 = stand.client(device=f"r10-api-res2-{token}")
        self.staff = stand.client()
        self.staff_ok = bool(stand.staff) and self.staff.login(*stand.staff)
        self.nocsrf = stand.client()
        if stand.staff and self.nocsrf.login(*stand.staff):
            self.nocsrf.csrf = None  # сессия есть, CSRF-токена нет
        self.rows = []
        self.ids = {}
        self.allow = {}      # путь (с id-заглушкой) -> множество методов из Allow, None — маршрута нет
        self.state = {}      # (метод, шаблон) -> registered | not_registered | not_ready | failed | ready
        self.timing = {}
        self.today = datetime.now(timezone.utc).date()

    # --- журнал строк
    def add(self, area, name, status, detail=None, owner=None):
        row = {"area": area, "name": name, "status": status, "detail": detail, "owner": owner}
        self.rows.append(row)
        mark = {"PASS": "PASS   ", "FAIL": "FAIL   ", "NOT_RUN": "NOT_RUN"}[status]
        print(f"{mark} {area} {name}" + (f" — {json.dumps(detail, ensure_ascii=False)[:240]}" if detail else ""))

    # --- адреса
    def fill(self, template, ids=None):
        ids = self.ids if ids is None else ids
        return re.sub(r"\{(\w+)\}", lambda m: str(ids.get(m.group(1)) or PROBE), template)

    def query(self, route):
        values = {"since": _iso(-7), "from": _date(-30), "to": _date(60), "from_week": _date(-7),
                  "today": _date(0)}
        return route.query.format(**values) if route.query else ""

    def url(self, route, ids=None):
        q = self.query(route)
        return f"{V2}/{self.fill(route.path, ids)}" + (f"?{q}" if q else "")

    # --- 1. есть ли маршрут
    def registered(self, route):
        path = f"{V2}/{self.fill(route.path, {})}"
        if path not in self.allow:
            r = self.anon.request("DELETE", path)
            if r.status == 405:
                allow = r.headers.get("Allow") or r.headers.get("allow") or ""
                self.allow[path] = {m.strip() for m in allow.split(",") if m.strip()}
            else:
                self.allow[path] = None
        methods = self.allow[path]
        return methods is not None and route.method in methods

    # --- основной проход
    def run(self):
        # Журнал сервера — только с этого места: исключения при старте (нет файла мира и т. п.) модули ловят и пишут сами.
        self.log_from = len(self.s.log)
        self.modules_regress()
        present = [rt for rt in ROUTES if self.registered(rt)]
        if not present:
            for rt in ROUTES:
                self.add("§7", f"{rt.method} {rt.path}", "NOT_RUN",
                         "маршрутов раунда 15 нет в шлюзе этой сборки (FINAL-4 или R01 ещё не добавил, CONTRACT §7)",
                         "R01")
                self.state[(rt.method, rt.path)] = "not_registered"
            return self
        for rt in ROUTES:
            if rt not in present:
                self.state[(rt.method, rt.path)] = "not_registered"
                self.add("§7", f"{rt.method} {rt.path}", "FAIL", "маршрута нет в шлюзе (DELETE → не 405 с этим методом)",
                         "R01")
        # 2. без модуля — 503 module_not_ready
        for rt in present:
            r = self.call(self.anon, rt, ids={})
            key = (rt.method, rt.path)
            if r.status == 503:
                code, msg = error_info(r)
                body = r.body if isinstance(r.body, dict) else {}
                if code == "module_not_ready":
                    ok_msg, why = understandable(r)
                    role_ok = body.get("role") == rt.role
                    status = "PASS" if ok_msg and role_ok else "FAIL"
                    self.add("§7", f"{rt.method} {rt.path}: модуля нет → 503 module_not_ready", status,
                             {"role": body.get("role"), "module": body.get("module"), "msg": why}
                             if status == "FAIL" else {"module": body.get("module")}, None if status == "PASS" else "R01")
                    self.state[key] = "not_ready"
                else:
                    self.add("§7", f"{rt.method} {rt.path}: модуль упал при загрузке ({code})", "FAIL",
                             {"module": body.get("module"), "msg": msg}, rt.role)
                    self.state[key] = "failed"
            else:
                self.state[key] = "ready"
        ready = [rt for rt in present if self.state[(rt.method, rt.path)] == "ready"]
        if ready:
            self.discover()
            for rt in ready:
                self.access(rt)
            self.functional()
        traces = self.s.tracebacks(self.log_from)
        self.add("журнал", "сервер без Traceback модулей во время проверки", "FAIL" if traces else "PASS",
                 traces[:5] or None, "по тексту ошибки")
        return self

    def call(self, client, rt, ids=None, body=None, **kw):
        if rt.method == "GET":
            return client.get(self.url(rt, ids), **kw)
        b = bodies(self.ids if ids is None else ids).get(rt.path, {}) if body is None else body
        return client.post(self.url(rt, ids), b, **kw)

    # --- 6. прежние маршруты FINAL-4
    def modules_regress(self):
        r = self.anon.get(f"{V2}/modules")
        mods = (r.body or {}).get("modules") if isinstance(r.body, dict) else None
        if r.status != 200 or not isinstance(mods, dict):
            self.add("FINAL-4", "GET /modules отвечает картой маршрутов", "FAIL", {"status": r.status}, "R01")
            return
        self.modules = mods
        if not FINAL4_MODULES.exists():
            self.add("FINAL-4", "маршруты FINAL-4 на месте", "NOT_RUN", f"нет эталона {FINAL4_MODULES.name}", None)
            return
        base = json.loads(FINAL4_MODULES.read_text(encoding="utf-8"))["modules"]
        lost = sorted(k for k in base if k not in mods)
        worse = sorted(k for k, v in base.items() if v == "ready" and k in mods and mods[k].get("status") != "ready")
        self.add("FINAL-4", f"маршруты FINAL-4 на месте ({len(base)})", "FAIL" if lost else "PASS",
                 {"lost": lost} if lost else None, "R01")
        self.add("FINAL-4", "модули FINAL-4 подключены, как в FINAL-4 (ready)", "FAIL" if worse else "PASS",
                 {k: mods[k].get("status") for k in worse} if worse else None, "владелец модуля")

    # --- id настоящих записей (демо-мир или созданные проверкой)
    def discover(self):
        def first_id(path, *keys, pred=None):
            r = self.anon.get(f"{V2}/{path}")
            items = records(r.body, *keys) or []
            for item in items:
                if isinstance(item, dict) and item.get("id") and (pred is None or pred(item)):
                    return item
            return None

        item = first_id("together/initiatives", "initiatives")
        if item:
            self.ids["initiative"] = item["id"]
            target = item.get("target") or {}
            if str(target.get("id", "")).startswith("yard-"):
                self.ids["yard"] = target["id"]
        if "yard" in self.ids:
            yr = self.anon.get(f"{V2}/together/yards/{self.ids['yard']}")
            ypoint = ((record(yr.body, "yard") or {}).get("point") if yr.status == 200 else None)
            if isinstance(ypoint, list) and len(ypoint) == 2:
                self.ids["_yard_point"] = ypoint
        item = first_id("incidents", "incidents")
        if item:
            self.ids["incident"] = item["id"]
        item = first_id("meetings", "meetings")
        if item:
            self.ids["meeting"] = item["id"]
        item = first_id("ideas", "ideas", "items")
        if item:
            self.ids["idea"] = item["id"]
        # Жалоба для совместного исполнения: новая, у остановки «Республиканский диагностический центр» (как API-шаг demo_flow).
        r = self.res.post(f"{V2}/complaints", {
            "text": "Яма после раскопок у остановки, асфальт не восстановили", "lang": "ru", "category": "roads",
            "category_source": "resident", "point": [71.4060541, 51.1266034],
            "target": {"kind": "object", "id": "osm-node-13394597038"}, "device_id": self.res.device, "demo": True})
        rec = record(r.body, "complaint") or {}
        if r.status in (200, 201) and str(rec.get("id", "")).startswith("c-"):
            self.ids["complaint"] = rec["id"]
        self.add("подготовка", "id записей для проверки", "PASS", dict(self.ids))

    # --- 3–5. доступ, ошибки, формат
    def access(self, rt):
        name = f"{rt.method} {rt.path}"
        has_ids = all(k in self.ids for k in re.findall(r"\{(\w+)\}", rt.path))
        if rt.who == "staff":
            r = self.call(self.anon, rt)
            self.expect_denied(name + ": без входа", r, (401, 403), rt.role)
            if rt.method == "POST" and self.nocsrf.csrf is None and self.staff_ok:
                r = self.call(self.nocsrf, rt, csrf=False)
                self.expect_denied(name + ": вход без CSRF", r, (403,), rt.role)
            if self.staff_ok:
                r = self.call(self.staff, rt)
                self.expect_ok(name + ": сотрудник", r, rt, has_ids)
                if rt.method == "POST":
                    r = self.call(self.staff, rt, body={})
                    self.expect_no_crash(name + ": сотрудник, пустое тело", r, rt.role)
        elif rt.who == "resident":
            r = self.call(self.anon, rt)
            if rt.method == "GET" and r.status == 200:
                # Чтение без устройства: допустимо, если ответ — общая часть без личного (зона по параметрам, пусто).
                leaks = privacy_issues(r.body)
                self.add("доступ", f"{name}: житель без X-Birge-Device → 200 (общая часть)", "FAIL" if leaks else "PASS",
                         leaks or None, rt.role)
            else:
                self.expect_denied(name + ": житель без X-Birge-Device", r, (400, 401, 403, 422), rt.role)
            r = self.call(self.res, rt)
            self.expect_ok(name + ": житель", r, rt, has_ids)
        elif rt.who == "author":
            r = self.call(self.anon, rt)
            self.expect_denied(name + ": не автор и не сотрудник", r, (400, 401, 403, 404, 422), rt.role)
            if self.staff_ok:
                r = self.call(self.staff, rt, body={})
                self.expect_no_crash(name + ": сотрудник, пустое тело", r, rt.role)
        else:
            r = self.call(self.anon, rt)
            self.expect_ok(name + ": житель без входа", r, rt, has_ids)
            if rt.method == "POST":
                r = self.call(self.anon, rt, body={})
                self.expect_no_crash(name + ": пустое тело", r, rt.role)
        # Неверные параметры GET → 400 с понятным текстом, а не 500.
        if rt.method == "GET" and rt.query:
            client = self.staff if rt.who == "staff" else (self.res if rt.who == "resident" else self.anon)
            bad = client.get(f"{V2}/{self.fill(rt.path)}?" + re.sub(r"=[^&]*", "=bad-value", self.query(rt), count=1))
            self.expect_no_crash(name + ": неверный параметр", bad, rt.role, want_4xx=False)

    def expect_denied(self, name, r, codes, owner):
        if r.status in codes:
            ok, why = understandable(r)
            self.add("доступ", f"{name} → {r.status}", "PASS" if ok else "FAIL", None if ok else why, owner)
        elif r.status == 429:
            self.add("доступ", f"{name}", "NOT_RUN", "лимит частоты 429 — повторить отдельно", None)
        else:
            self.add("доступ", f"{name} → ожидалось {'/'.join(map(str, codes))}", "FAIL",
                     {"status": r.status, "body": str(r.body)[:200]}, owner)

    def expect_no_crash(self, name, r, owner, want_4xx=True):
        if r.status >= 500 or r.status == 0:
            self.add("ошибки", f"{name} → {r.status}", "FAIL", {"body": str(r.body)[:200]}, owner)
        elif r.status >= 400:
            ok, why = understandable(r)
            self.add("ошибки", f"{name} → {r.status} понятная ошибка", "PASS" if ok else "FAIL",
                     None if ok else why, owner)
        else:
            self.add("ошибки", f"{name} → {r.status}", "PASS", None, owner)

    def expect_ok(self, name, r, rt, has_ids):
        if r.status in (200, 201):
            self.timing.setdefault(f"{rt.method} {rt.path}", []).append(round(r.ms))
            if not isinstance(r.body, (dict, list)):
                self.add("формат", f"{name} → не JSON", "FAIL", r.text[:120], rt.role)
                return
            self.add("ответ", f"{name} → {r.status}", "PASS", None, rt.role)
            self.check_format(name, r, rt)
        elif r.status == 404 and ROUTE_404.search(str(error_info(r)[1] or "")):
            # Модуль роли раунда 14 есть, а нового пути в нём нет: поставки роли в сборке ещё нет (R01 зарегистрировал
            # маршрут заранее). Это не дефект шлюза и не FAIL роли — NOT_RUN, пока поставка не вошла в сборку.
            self.add("ответ", f"{name} → 404 «{error_info(r)[1]}»", "NOT_RUN",
                     f"модуль {rt.role} ещё не знает этот путь — поставки роли нет в сборке (лучше бы шлюз отвечал 503)",
                     rt.role)
        elif r.status == 404 and not has_ids:
            ok, why = understandable(r)
            self.add("ответ", f"{name} → 404 (записи-заглушки нет)", "PASS" if ok else "FAIL", None if ok else why,
                     rt.role)
        elif r.status == 429:
            self.add("ответ", name, "NOT_RUN", "лимит частоты 429", None)
        elif r.status == 409:
            # Конфликт по правилу модуля (дубль кризиса, итог встречи до её начала) с понятным текстом — не дефект.
            ok, why = understandable(r)
            self.add("ответ", f"{name} → 409 (правило модуля)", "PASS" if ok else "FAIL", why, rt.role)
        elif 400 <= r.status < 500:
            ok, why = understandable(r)
            # Модуль отказал на примере «как в интерфейсе»: не сбой, но и не PASS — пример из §5 должен проходить.
            self.add("ответ", f"{name} → {r.status} на примере по §5", "FAIL", why, rt.role)
        else:
            self.add("ответ", f"{name} → {r.status}", "FAIL", {"body": str(r.body)[:200]}, rt.role)

    def check_format(self, name, r, rt):
        kind = rt.kind
        problems = []
        if rt.method == "GET" and rt.who != "staff":
            problems += privacy_issues(r.body)
        checker = CHECKERS.get(kind)
        if checker:
            if kind in SINGLE:
                rec = record(r.body, *SINGLE[kind])
                recs = [rec] if isinstance(rec, dict) else []
            else:
                recs = records(r.body, kind)
                if recs is None:
                    problems.append("в ответе нет списка записей")
                    recs = []
            for rec in recs[:50]:
                if isinstance(rec, dict):
                    # Запись, созданная проверкой (POST), — не синтетика мира: demo: true от неё не требуем.
                    errs = checker(rec, world=self.world and rt.method == "GET")
                    if errs:
                        problems.append(f"{rec.get('id', '?')}: " + "; ".join(errs[:4]))
            if kind == "initiatives" and rt.who == "all":
                hidden = [x.get("id") for x in recs if isinstance(x, dict) and x.get("status") in ("on_review", "hidden")]
                if hidden:
                    problems.append(f"в общем списке непроверенные/скрытые: {hidden[:3]}")
        elif kind == "route":
            data = unwrap(r.body) or {}
            services = data.get("services") if isinstance(data, dict) else None
            if not isinstance(services, list) or not services:
                problems.append("нет services")
            else:
                ids = [s.get("service") if isinstance(s, dict) else s for s in services]
                if not set(ids) <= SERVICES:
                    problems.append(f"службы не из §3: {ids}")
        elif kind == "moderate":
            text = json.dumps(unwrap(r.body), ensure_ascii=False).lower()
            for need in ("phone", "iin", "email"):
                if need not in text and not ({"iin": "иин", "phone": "телефон", "email": "почт"}[need] in text):
                    problems.append(f"не отмечен {need}")
        elif kind == "replay":
            frames = records(r.body, "frames")
            if not frames:
                problems.append("нет кадров frames")
            elif not all(isinstance(f, dict) and (f.get("date") or f.get("at")) for f in frames[:5]):
                problems.append("кадр без даты")
        elif kind in ("board", "joint", "handoffs"):
            text = json.dumps(unwrap(r.body), ensure_ascii=False)
            if re.search(r'"(username|user|operator_name|staff_name|by_user|full_name)"\s*:', text):
                problems.append("в табло/журнале имена людей (а нужно только службы и роли)")
        status = "FAIL" if problems else "PASS"
        if checker or kind in ("route", "moderate", "replay", "board", "joint", "handoffs") or problems:
            self.add("формат", f"{name}: §5 и §10", status, problems[:6] or None, rt.role)

    # --- сквозные проверки поведения (когда модули есть)
    def functional(self):
        st = self.state
        if st.get(("POST", "together/initiatives/{initiative}/join")) == "ready" and "initiative" in self.ids:
            self.join_once("together/initiatives/{initiative}", "joined", "«Я приду»", "R16")
        if st.get(("POST", "together/yards/{yard}/join")) == "ready" and "yard" in self.ids:
            self.join_once("together/yards/{yard}", "members", "«Я живу здесь»", "R16")
        if st.get(("POST", "complaints/{complaint}/handoff")) == "ready" and "complaint" in self.ids:
            self.handoff_keeps_deadline()

    def join_once(self, base, field, label, owner):
        get = lambda: record(self.anon.get(f"{V2}/{self.fill(base)}").body, "initiative", "yard") or {}  # noqa: E731
        before = get().get(field)
        self.res2.post(f"{V2}/{self.fill(base)}/join", {})
        self.res2.post(f"{V2}/{self.fill(base)}/join", {})
        after = get().get(field)
        ok = isinstance(before, int) and after == before + 1
        self.add("поведение", f"{label}: дважды с одного устройства → +1 ({before} → {after})", "PASS" if ok else "FAIL",
                 None if ok else {"before": before, "after": after}, owner)
        self.res2.post(f"{V2}/{self.fill(base)}/leave", {})
        back = get().get(field)
        self.add("поведение", f"{label}: «Не приду / выйти» → обратно {before}", "PASS" if back == before else "FAIL",
                 None if back == before else {"after_leave": back}, owner)

    def handoff_keeps_deadline(self):
        # Своя свежая жалоба: на общей уже была передача в проверке доступа (вторая такая же — справедливо 409/422).
        fresh = self.res2.post(f"{V2}/complaints", {
            "text": "Раскопали тротуар и не засыпали, ходить негде", "lang": "ru", "category": "roads",
            "category_source": "resident", "point": [71.4060541, 51.1266034],
            "target": {"kind": "object", "id": "osm-node-13394597038"}, "device_id": self.res2.device, "demo": True})
        rec_fresh = record(fresh.body, "complaint") or {}
        cid = rec_fresh.get("id") if fresh.status in (200, 201) and str(rec_fresh.get("id", "")).startswith("c-") \
            else self.ids["complaint"]
        before = record(self.staff.get(f"{V2}/complaints/{cid}").body, "complaint") or {}
        r = self.staff.post(f"{V2}/complaints/{cid}/handoff", {"to": "water", "reason": "Сначала нужна замена трубы"})
        after = record(self.staff.get(f"{V2}/complaints/{cid}").body, "complaint") or {}
        if r.status == 404 and ROUTE_404.search(str(error_info(r)[1] or "")):
            self.add("поведение", "передача в другую службу: с причиной, срок ответа не начинается заново", "NOT_RUN",
                     "маршрута передачи в модуле R09 ещё нет (поставки нет в сборке)", "R09")
            return
        due_keys = sorted(k for k in before if "due" in k or "deadline" in k)
        changed = {k: (before.get(k), after.get(k)) for k in due_keys if before.get(k) != after.get(k)}
        handoffs = after.get("handoffs") or []
        ok = r.status in (200, 201) and not changed and any(isinstance(h, dict) and h.get("reason") for h in handoffs)
        self.add("поведение", "передача в другую службу: с причиной, срок ответа не начинается заново",
                 "PASS" if ok else "FAIL", None if ok else {"status": r.status, "due_changed": changed,
                                                            "handoffs": handoffs[:2], "due_keys": due_keys}, "R09")

    # --- сводка
    def summary(self):
        by_role = {}
        for rt in ROUTES:
            row = by_role.setdefault(rt.role, {"routes": 0, "ready": 0, "not_ready": 0, "failed": 0, "not_registered": 0})
            row["routes"] += 1
            row[self.state.get((rt.method, rt.path), "not_registered")] += 1
        counts = {s: sum(1 for r in self.rows if r["status"] == s) for s in ("PASS", "FAIL", "NOT_RUN")}
        return {"counts": counts, "by_role": by_role, "ids": self.ids, "timing_ms": self.timing}


def run(root, world=True):
    with Stand(root, world=world) as stand:
        check = ApiCheck(stand, world).run()
        return {"root": str(root), "world": world, "seeds": stand.seeds, "rows": check.rows, **check.summary()}


def to_markdown(result, label=""):
    lines = [f"# R10 · API v2 раунда 15 (CONTRACT §7) {label}".rstrip(), "",
             f"Сборка: `{result['root']}` · демо-мир: {'да' if result['world'] else 'нет'} · "
             f"PASS {result['counts']['PASS']} · FAIL {result['counts']['FAIL']} · NOT_RUN {result['counts']['NOT_RUN']}",
             "", "| Роль | маршрутов | готово | ждёт модуль (503) | модуль упал | нет в шлюзе |", "|---|---|---|---|---|---|"]
    for role, row in sorted(result["by_role"].items()):
        lines.append(f"| {role} | {row['routes']} | {row['ready']} | {row['not_ready']} | {row['failed']} | "
                     f"{row['not_registered']} |")
    lines += ["", "| Статус | Раздел | Проверка | Подробно | Владелец |", "|---|---|---|---|---|"]
    for r in result["rows"]:
        detail = json.dumps(r["detail"], ensure_ascii=False)[:160] if r["detail"] else ""
        lines.append(f"| {r['status']} | {r['area']} | {r['name']} | {detail.replace('|', '/')} | {r['owner'] or ''} |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(HERE.parents[2]))
    parser.add_argument("--out", help="папка отчёта: API_V2.json и API_V2.md")
    parser.add_argument("--label", default="")
    parser.add_argument("--no-world", action="store_true", help="без CIVIC_DEMO_WORLD=1 (прежнее демо FINAL-4)")
    parser.add_argument("--save-final4", action="store_true", help="записать карту /modules как эталон FINAL-4")
    args = parser.parse_args()
    if args.save_final4:
        with Stand(args.root, world=False) as stand:
            mods = stand.client().get(f"{V2}/modules").body["modules"]
        FINAL4_MODULES.parent.mkdir(parents=True, exist_ok=True)
        sha = subprocess.run(["git", "-C", args.root, "rev-parse", "--short=8", "HEAD"], capture_output=True,
                             text=True).stdout.strip() or "?"
        FINAL4_MODULES.write_text(json.dumps({"source": f"GET {V2}/modules на сборке {sha}, CIVIC_DEMO=1",
                                              "modules": {k: v["status"] for k, v in sorted(mods.items())}},
                                             ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"эталон: {FINAL4_MODULES} ({len(mods)} маршрутов)")
        return 0
    result = run(args.root, world=not args.no_world)
    print(json.dumps({k: result[k] for k in ("counts", "by_role")}, ensure_ascii=False))
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "API_V2.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "API_V2.md").write_text(to_markdown(result, args.label), encoding="utf-8")
    return 1 if result["counts"]["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
