"""Соседи Ситуационного центра и «Картины дня» 2.0 (раунд 15): только чтение, R08 ничего не пересчитывает.

    R17 ui.civic_agencies .... табло служб (agencies/board), кризисы (incidents)
    R16 ui.civic_together .... «Жители вместе»: инициативы недели, дворы
    R13 ui.civic_meetings .... поручения встреч с акимом;  ui.civic_forecast — прогноз (прототип)

Правило CONTRACT §7: вызовы между модулями — только чтением и только через функции соседа с запасным вариантом.
Для каждого блока по порядку:
  1) функция чтения соседа (имена — research/round-15-results/R08/INTEGRATION.txt §2–4; первая найденная);
  2) нет функции, но есть make_service(db_path) — GET-маршрут соседа из CONTRACT §7 внутри процесса
     (служебный сотрудник «situation-center»; сам akim/board отдаётся только сотруднику);
  3) соседа нет в сборке, а сборка демо (CIVIC_DEMO=1) без демо-мира — фикстура fixtures/board_demo.json
     (demo: true, на экране «Пример»). С демо-миром (CIVIC_DEMO_WORLD=1) фикстуры не подмешиваются никогда;
  4) иначе {"available": False, "reason": "module_not_ready"} — экран пишет «пока нет данных».
Сбой соседа (исключение, ответ не 200) — тот же пустой блок с reason="module_failed"; ответ R08 не падает.

Что R08 делает с числами соседей: только выбирает, что показать (первые N, порядок «самые отстающие» — если сосед
не дал свой), и считает штуки по записям, если сосед не прислал готовые счётчики (например, сколько поручений
просрочено — по полям due и status записи встречи §5.7). Формулы соседей не повторяются.
"""
from __future__ import annotations

import importlib
import inspect
import json
import logging
import os
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import routing, text

log = logging.getLogger("civic_akim.neighbors")

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "board_demo.json"
PREFIX = "/api/civic/v2"
ASTANA_TZ = timezone(timedelta(hours=5))

# Имена функций чтения (INTEGRATION R08 §2–4). Первое — то, что R08 попросил; остальные — вероятные синонимы.
R17_MODULE = "ui.civic_agencies"
R17_BOARD_FUNCS = ("board_for_akim", "akim_board", "board_summary", "board")
R17_INCIDENT_FUNCS = ("incidents_for_akim", "akim_incidents", "active_incidents", "list_incidents")
R16_MODULE = "ui.civic_together"
R16_FUNCS = ("together_for_akim", "akim_together", "akim_summary", "week_summary")
R13_MEETINGS_MODULE = "ui.civic_meetings"
R13_MEETINGS_FUNCS = ("meetings_for_akim", "orders_for_akim", "akim_meetings", "list_meetings")
R13_FORECAST_MODULE = "ui.civic_forecast"
R13_WEEK_FUNCS = ("week_forecast", "forecast_week", "attention_next_week")

# Вид кризиса R17 по теме тревоги пульса: «Открыть кризисный штаб» → шаблон этого вида (CONTRACT §5.5).
CRISIS_KIND = {"snow_ice": "blizzard", "utilities/no_heating": "heat_outage", "utilities/no_water": "water_outage",
               "utilities/sewage": "flood"}
TOPIC_ALARMS = ("spike", "spike_new", "spike_city")   # тревоги «тема растёт» — у них кнопка штаба
SHOWN_INITIATIVE = ("published", "done")             # CONTRACT §10: на проверке и скрытые не показываем никогда
ORDER_STATUSES = ("todo", "in_progress", "done")


class _Unavailable(Exception):
    """Соседа нет (reason) — блок пустой, а не ошибка."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class _Principal(dict):
    """Служебный сотрудник для чтения сервисов соседей внутри процесса (только GET; CSRF не проходит никогда)."""

    username = "situation-center"
    role = "staff"
    is_staff = True

    def __init__(self):
        super().__init__(username=self.username, role=self.role)

    def check_csrf(self, _token) -> bool:  # запись этим «сотрудником» невозможна
        return False


# ---------------------------------------------------------------- настройки процесса

class Settings:
    """Что знает R08 о сборке: путь к общей SQLite (для сервисов соседей), демо-сборка, демо-мир."""

    def __init__(self, db_path=None, demo_build=False, demo_world=None, examples=None):
        env_db = os.environ.get("CIVIC_DB_PATH") or os.environ.get("CIVIC_DB")
        self.db_path = str(db_path) if db_path else (str(Path(env_db).expanduser()) if env_db else None)
        self.demo_build = bool(demo_build)
        self.demo_world = (os.environ.get("CIVIC_DEMO_WORLD") == "1") if demo_world is None else bool(demo_world)
        # examples — можно ли показывать фикстуру вместо отсутствующего соседа; None — решает демо-сборка.
        self.examples = examples

    def may_use_fixture(self, all_demo: bool = False) -> bool:
        if self.demo_world:
            return False
        if self.examples is not None:
            return bool(self.examples)
        return self.demo_build or all_demo


_services: dict = {}
_services_lock = threading.Lock()


def reset_cache() -> None:
    """Для тестов: забыть созданные сервисы соседей."""
    with _services_lock:
        _services.clear()


def _import(name: str):
    """Модуль соседа или None, если его ещё нет в сборке. Сбой внутри модуля — исключение (это «module_failed»)."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", None) or ""
        if name == missing or name.startswith(missing + "."):
            return None
        raise


def _call(fn, **kwargs):
    """Вызов функции соседа только с теми параметрами, которые она объявила."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return fn(**kwargs)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(**kwargs)
    return fn(**{k: v for k, v in kwargs.items() if k in params})


def _unwrap(body):
    """Конверт {"ok": true, "data": …} (R09, R13) или голое тело (R07, R08)."""
    if isinstance(body, dict) and body.get("ok") is True and "data" in body:
        return body["data"]
    return body


def _service_get(module, settings: Settings, route: str, query: str = ""):
    """GET-маршрут соседа внутри процесса: make_service(db_path).handle(...). Только если база уже есть."""
    factory = getattr(module, "make_service", None)
    if not callable(factory):
        raise _Unavailable("module_not_ready")
    if not settings.db_path or not Path(settings.db_path).is_file():
        raise _Unavailable("no_database")
    key = (module.__name__, settings.db_path)
    with _services_lock:
        svc = _services.get(key)
        if svc is None:
            svc = factory(settings.db_path)
            _services[key] = svc
    reply = svc.handle("GET", PREFIX + "/" + route, query, None, _Principal(), {"headers": {}})
    if not isinstance(reply, dict) or reply.get("status") != 200:
        raise _Unavailable("module_failed")
    return _unwrap(reply.get("body"))


def _read(module_name: str, funcs: tuple, route: str | None, query: str, settings: Settings, **kwargs):
    """(данные, source) соседа: функция → сервис → _Unavailable. Ошибка соседа — _Unavailable("module_failed")."""
    try:
        module = _import(module_name)
    except Exception:
        log.exception("R08: модуль соседа %s не загрузился", module_name)
        raise _Unavailable("module_failed") from None
    if module is None:
        raise _Unavailable("module_not_ready")
    try:
        for name in funcs:
            fn = getattr(module, name, None)
            if callable(fn):
                return _unwrap(_call(fn, db_path=settings.db_path, **kwargs)), "function"
        if route is None:
            raise _Unavailable("module_not_ready")
        return _service_get(module, settings, route, query), "service"
    except _Unavailable:
        raise
    except Exception:
        log.exception("R08: сосед %s ответил ошибкой", module_name)
        raise _Unavailable("module_failed") from None


# ---------------------------------------------------------------- фикстура

def _shift_value(value, delta: timedelta):
    if not isinstance(value, str) or len(value) < 10 or value[4:5] != "-" or value[7:8] != "-":
        return value
    try:
        if len(value) == 10:
            return (date.fromisoformat(value) + timedelta(days=round(delta.total_seconds() / 86400))).isoformat()
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return (dt + delta).isoformat(timespec="seconds")


def _shift(node, delta: timedelta):
    if isinstance(node, dict):
        return {k: _shift(v, delta) for k, v in node.items()}
    if isinstance(node, list):
        return [_shift(v, delta) for v in node]
    return _shift_value(node, delta)


def fixture(now: datetime) -> dict:
    """Фикстура, «прожившая» до сейчас: все даты сдвинуты на (now − anchor)."""
    raw = json.loads(FIXTURE.read_text("utf-8"))
    anchor = datetime.fromisoformat(raw["_meta"]["anchor"])
    return _shift({k: v for k, v in raw.items() if k != "_meta"}, now - anchor)


# ---------------------------------------------------------------- общие мелочи

def parse_time(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=ASTANA_TZ)
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=ASTANA_TZ)


def _day(value) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    t = parse_time(value)
    if t is not None:
        return t.astimezone(ASTANA_TZ).date()
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _num(row: dict, names: tuple, kind=int):
    for n in names:
        v = row.get(n)
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            return kind(v)
        if isinstance(v, str):
            try:
                return kind(float(v))
            except ValueError:
                continue
    return None


def service_names() -> dict:
    """id → {ru, kk, edited} — названия служб из таблицы R08 (CONTRACT §3: R17 их не дублирует)."""
    try:
        return routing.table()["services"]
    except Exception:  # таблица — не повод ронять табло
        return {k: dict(v) for k, v in routing.SERVICES.items()}


def _service_label(sid, names: dict) -> dict:
    info = names.get(sid) or {}
    return {"service": sid, "ru": info.get("ru") or sid, "kk": info.get("kk") or info.get("ru") or sid,
            "name_edited": bool(info.get("edited"))}


def _district_label(d_id) -> dict:
    return {"district": d_id, "district_ru": text.district_name(d_id, "ru") if d_id else None,
            "district_kk": text.district_name(d_id, "kk") if d_id else None}


def _empty(reason: str, **extra) -> dict:
    return {"available": False, "reason": reason, "source": "none", "demo": False, **extra}


def _fixture_or_empty(settings: Settings, reason: str, all_demo: bool, build, now: datetime):
    if reason == "module_not_ready" and settings.may_use_fixture(all_demo):
        out = build(fixture(now))
        out.update(source="fixture", demo=True)
        return out
    return None


# ---------------------------------------------------------------- R17: табло служб

BOARD_SYNONYMS = {
    "open": ("open", "open_count", "opened", "active", "in_work"),
    "overdue": ("overdue", "overdue_count", "late"),
    "median_answer_days": ("median_answer_days", "median_days", "median_response_days", "answer_median_days",
                           "median_answer"),
    "verified_share": ("verified_share", "verified_pct", "verified_ratio", "verified_by_residents_share"),
    "returned": ("returned", "reopened", "returned_by_residents", "reopened_by_residents"),
    "handoffs_in": ("handoffs_in", "handoff_in", "in"),
    "handoffs_out": ("handoffs_out", "handoff_out", "out"),
    "joint": ("joint", "joint_count", "joint_open"),
}
LAGGING_N = 3


def normalize_board(body, names: dict | None = None) -> dict:
    """Ответ R17 (agencies/board) → строки для показа. Числа — как прислал R17, R08 только выбирает порядок."""
    names = names or service_names()
    data = body if isinstance(body, dict) else {"items": body if isinstance(body, list) else []}
    rows = data.get("items") or data.get("services") or data.get("rows") or []
    items = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        sid = row.get("service") or row.get("id")
        if not isinstance(sid, str):
            continue
        item = _service_label(sid, names)
        for key, syn in BOARD_SYNONYMS.items():
            item[key] = _num(row, syn, float if key in ("median_answer_days", "verified_share") else int)
        share = item["verified_share"]
        if share is not None and share > 1:   # пришли проценты
            item["verified_share"] = share / 100.0
        if item["verified_share"] is not None:
            item["verified_share"] = round(max(0.0, min(1.0, item["verified_share"])), 3)
        if item["median_answer_days"] is not None:
            item["median_answer_days"] = round(item["median_answer_days"], 1)
        items.append(item)
    lagging = [s for s in data.get("lagging") or [] if isinstance(s, str)]
    if lagging:
        order = {sid: i for i, sid in enumerate(lagging)}
        ranked = sorted((it for it in items if it["service"] in order), key=lambda it: order[it["service"]])
    else:
        ranked = sorted((it for it in items if (it["overdue"] or 0) > 0),
                        key=lambda it: (-(it["overdue"] or 0), -(it["median_answer_days"] or 0), it["service"]))
    joint, handoffs = data.get("joint"), data.get("handoffs")
    joint = joint if isinstance(joint, dict) else ({"open": joint} if isinstance(joint, int) else {})
    handoffs = handoffs if isinstance(handoffs, dict) else ({"week": handoffs} if isinstance(handoffs, int) else {})
    return {
        "available": True,
        "days": data.get("days") or 7,
        "items": items,
        "lagging": [it["service"] for it in ranked[:LAGGING_N]],
        "lagging_source": "r17" if lagging else "r08_order",
        "joint": {"open": _num(joint, ("open", "open_count")), "week": _num(joint, ("week", "new", "count"))},
        "handoffs": {"week": _num(handoffs, ("week", "count", "total"))},
        "demo": bool(data.get("demo")),
    }


def agencies_board(settings: Settings, *, days: int = 7, district=None, now: datetime, all_demo=False) -> dict:
    query = f"days={days}" + (f"&district={district}" if district else "")
    try:
        body, how = _read(R17_MODULE, R17_BOARD_FUNCS, "agencies/board", query, settings,
                          days=days, district=district, now=now)
    except _Unavailable as exc:
        names = service_names()
        out = _fixture_or_empty(settings, exc.reason, all_demo,
                                lambda fx: normalize_board(fx["agencies_board"], names), now)
        return out or _empty(exc.reason, items=[], lagging=[])
    out = normalize_board(body)
    out.update(source="r17" if how == "function" else "r17-service")
    return out


# ---------------------------------------------------------------- R17: кризисы

def crisis_link(incident: dict | None, *, kind: str | None = None, district: str | None = None) -> str:
    """Адрес «Открыть кризисный штаб» (INTEGRATION R08 §2.3; свой адрес R17 — поле link записи кризиса)."""
    if incident:
        link = incident.get("link")
        if isinstance(link, str) and link.startswith(("/", "#")):
            return link
        return "/#agencies/" + str(incident.get("id"))
    params = []
    if kind:
        params.append("kind=" + kind)
    if district:
        params.append("district=" + district)
    return "/#agencies/new" + ("?" + "&".join(params) if params else "")


def normalize_incident(rec: dict, names: dict) -> dict | None:
    """Кризис §5.5 → то, что показывает R08: зона, задачи по службам (сделано / всего), последнее обновление."""
    if not isinstance(rec, dict) or not rec.get("id"):
        return None
    zone = rec.get("zone") if isinstance(rec.get("zone"), dict) else {}
    tasks = [t for t in rec.get("tasks") or [] if isinstance(t, dict)]
    per: dict = {}
    for t in tasks:
        sid = t.get("service") if isinstance(t.get("service"), str) else "akimat"
        acc = per.setdefault(sid, {"done": 0, "total": 0})
        acc["total"] += 1
        acc["done"] += int(t.get("status") == "done")
    updates = sorted((u for u in rec.get("updates") or [] if isinstance(u, dict) and u.get("public", True)
                      and parse_time(u.get("at"))), key=lambda u: parse_time(u["at"]))
    last = updates[-1] if updates else None
    targets = zone.get("targets") if isinstance(zone.get("targets"), list) else []
    return {
        "id": rec["id"], "kind": rec.get("kind") or "other", "status": rec.get("status") or "active",
        "title_ru": rec.get("title_ru") or rec.get("title_kk") or "", "title_kk": rec.get("title_kk") or rec.get("title_ru") or "",
        "started_at": rec.get("started_at"),
        "zone": {"kind": zone.get("kind") or "district", **_district_label(zone.get("district")),
                 "targets": len(targets), "approximate": zone.get("geometry") is not None},
        "tasks": {"total": len(tasks), "done": sum(1 for t in tasks if t.get("status") == "done"),
                  "doing": sum(1 for t in tasks if t.get("status") == "doing"),
                  "todo": sum(1 for t in tasks if t.get("status") not in ("done", "doing"))},
        "services": sorted(({**_service_label(sid, names), **acc} for sid, acc in per.items()),
                           key=lambda s: (s["done"] == s["total"], -s["total"], s["service"])),
        "last_update": {"at": last.get("at"), "text_ru": last.get("text_ru") or last.get("text_kk") or "",
                        "text_kk": last.get("text_kk") or last.get("text_ru") or ""} if last else None,
        "updates": len(updates),
        "link": crisis_link(rec),
        "demo": bool(rec.get("demo")),
    }


def incidents(settings: Settings, *, district=None, now: datetime, all_demo=False) -> dict:
    """Активные кризисы (первым — самый свежий) и закрытые за 7 дней — числом."""
    names = service_names()

    def build(records) -> dict:
        recs = records if isinstance(records, list) else (records or {}).get("items") or []
        norm = [n for n in (normalize_incident(r, names) for r in recs) if n]
        if district:
            norm = [n for n in norm if n["zone"]["district"] in (None, district)]
        active = sorted((n for n in norm if n["status"] == "active"),
                        key=lambda n: parse_time(n["started_at"]) or now, reverse=True)
        closed = [n for n in norm if n["status"] == "closed"]
        return {"available": True, "active": active, "closed": len(closed), "demo": any(n["demo"] for n in norm)}

    try:
        body, how = _read(R17_MODULE, R17_INCIDENT_FUNCS, "incidents", "", settings, district=district, now=now)
    except _Unavailable as exc:
        out = _fixture_or_empty(settings, exc.reason, all_demo, lambda fx: build(fx["incidents"]), now)
        return out or _empty(exc.reason, active=[], closed=0)
    out = build(body)
    out.update(source="r17" if how == "function" else "r17-service")
    return out


def pulse_links(items: list[dict], crisis: dict) -> None:
    """Кнопка «Открыть кризисный штаб» у тревог «тема растёт» (R08 промпт п. 3; R13 п. 4 — поле ссылки в пульсе).

    Есть активный кризис в районе тревоги (или по всему городу) — ссылка на него; нет — на создание кризиса из шаблона
    R17 по теме тревоги. Тревоги об одном месте (new_hot, metoo) ведут на карту, как раньше.
    """
    active = (crisis.get("active") or []) if crisis.get("available") else []
    for a in items:
        if a.get("kind") not in TOPIC_ALARMS:
            continue
        kind = CRISIS_KIND.get(a.get("category") or "", "other")
        match = next((c for c in active if a.get("district") in (None, c["zone"]["district"])
                      or c["zone"]["district"] is None), None)
        a["crisis"] = {"link": crisis_link(match, kind=kind, district=a.get("district")),
                       "incident": match["id"] if match else None, "kind": kind}


# ---------------------------------------------------------------- R16: жители вместе

def normalize_together(body, *, days: int, district, now: datetime) -> dict:
    data = body if isinstance(body, dict) else {"initiatives": body if isinstance(body, list) else []}
    raw = [r for r in data.get("initiatives") or data.get("items") or [] if isinstance(r, dict)]
    shown = [r for r in raw if r.get("status") in SHOWN_INITIATIVE and (district is None or r.get("district") == district)]
    since = now - timedelta(days=days)

    def when(r):
        return parse_time((r.get("report") or {}).get("at") if isinstance(r.get("report"), dict) else None) \
            or parse_time(r.get("starts_at")) or parse_time(r.get("created_at"))

    def recent(r) -> bool:
        # Опубликованные — будущие и начатые за период; сделанные — с отчётом (или датой) за период.
        t = when(r)
        if r.get("status") == "published":
            return t is None or t >= since
        return t is not None and since <= t <= now + timedelta(hours=1)

    relevant = [r for r in shown if recent(r)]
    upcoming = [r for r in relevant if r.get("status") == "published" and (parse_time(r.get("starts_at")) or now) >= now]
    done_week = [r for r in relevant if r.get("status") == "done"]
    counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
    joined = lambda r: max(0, int(r.get("joined") or 0))  # noqa: E731

    def row(r) -> dict:
        target = r.get("target") if isinstance(r.get("target"), dict) else {}
        support = r.get("support") if isinstance(r.get("support"), dict) else {}
        return {"id": r.get("id"), "kind": r.get("kind") or "other", "title": r.get("title") or "",
                "lang": r.get("lang") or "ru", "status": r.get("status"),
                "place_ru": target.get("label_ru"), "place_kk": target.get("label_kk") or target.get("label_ru"),
                "target": {"kind": target.get("kind"), "id": target.get("id")} if target.get("id") else None,
                **_district_label(r.get("district")),
                "starts_at": r.get("starts_at"), "joined": joined(r), "supported": bool(support.get("by_akimat")),
                "support_note": support.get("note") if support.get("by_akimat") else None,
                "report": bool(r.get("report")), "demo": bool(r.get("demo"))}

    # Показ: сначала ближайшие (их ещё можно поддержать), потом сделанные за неделю — по числу соседей.
    top = sorted(upcoming, key=lambda r: (parse_time(r.get("starts_at")) or now, -joined(r)))[:2]
    top += sorted((r for r in done_week if r not in top), key=lambda r: -joined(r))[:3 - len(top)]

    yards = {y.get("id"): y for y in data.get("yards") or [] if isinstance(y, dict) and y.get("id")}
    pick = (data.get("yard_of_week") or {}).get("id") if isinstance(data.get("yard_of_week"), dict) else None
    star = None
    if pick is None:
        # «Двор недели» (VISUAL_BRIEF §1 п. 4): двор, где за неделю больше всего соседей сделали дело вместе;
        # нет сделанного — где больше всего «Я приду» у ближайшей инициативы.
        pool = done_week or upcoming
        star = max(pool, key=lambda r: (joined(r), str(r.get("id"))), default=None)
        pick = ((star or {}).get("target") or {}).get("id")
    yard_of_week = None
    if pick:
        y = yards.get(pick, {})
        star = star or next((r for r in shown if (r.get("target") or {}).get("id") == pick), None)
        t = (star or {}).get("target") or {}
        yard_of_week = {"id": pick, "label_ru": y.get("label_ru") or t.get("label_ru"),
                        "label_kk": y.get("label_kk") or t.get("label_kk") or y.get("label_ru") or t.get("label_ru"),
                        **_district_label(y.get("district") or (star or {}).get("district")),
                        "members": int(y["members"]) if isinstance(y.get("members"), int) else None,
                        "initiative": row(star) if star else None}
    return {
        "available": True, "days": days,
        # Счётчики R16, если прислал; иначе — штуки по записям за период (одна инициатива — один раз).
        "counts": {"published": _num(counts, ("published", "active")) if counts else
                   sum(r.get("status") == "published" for r in relevant),
                   "joined": _num(counts, ("joined",)) if counts else sum(joined(r) for r in relevant),
                   "done": _num(counts, ("done",)) if counts else len(done_week),
                   "supported": _num(counts, ("supported",)) if counts else sum(
                       1 for r in relevant if isinstance(r.get("support"), dict) and r["support"].get("by_akimat"))},
        "top": [row(r) for r in top],
        "yard_of_week": yard_of_week,
        "demo": any(r.get("demo") for r in shown),
    }


def together(settings: Settings, *, days: int = 7, district=None, now: datetime, all_demo=False) -> dict:
    query = "status=published,done" + (f"&district={district}" if district else "")
    try:
        body, how = _read(R16_MODULE, R16_FUNCS, "together/initiatives", query, settings,
                          days=days, district=district, now=now)
    except _Unavailable as exc:
        out = _fixture_or_empty(settings, exc.reason, all_demo,
                                lambda fx: normalize_together(fx["together"], days=days, district=district, now=now), now)
        return out or _empty(exc.reason, top=[], yard_of_week=None, counts={})
    out = normalize_together(body, days=days, district=district, now=now)
    out.update(source="r16" if how == "function" else "r16-service")
    return out


# ---------------------------------------------------------------- R13: встречи и поручения

ORDERS_N = 5


def normalize_meetings(body, *, district, now: datetime, names: dict | None = None) -> dict:
    names = names or service_names()
    data = body if isinstance(body, list) else (body or {}).get("items") or (body or {}).get("meetings") or []
    meetings = [m for m in data if isinstance(m, dict) and (district is None or m.get("district") == district)]
    today = now.astimezone(ASTANA_TZ).date()
    orders = []
    for m in meetings:
        for o in m.get("orders") or []:
            if not isinstance(o, dict):
                continue
            status = o.get("status") if o.get("status") in ORDER_STATUSES else "todo"
            due = _day(o.get("due"))
            orders.append({"id": o.get("id"), "text_ru": o.get("text_ru") or o.get("text_kk") or "",
                           "text_kk": o.get("text_kk") or o.get("text_ru") or "", "status": status,
                           "due": due.isoformat() if due else None,
                           "overdue": bool(due and status != "done" and due < today),
                           "days_left": (due - today).days if due and status != "done" else None,
                           **_service_label(o.get("service") or "akimat", names),
                           "meeting": {"id": m.get("id"), "title_ru": m.get("title_ru"), "title_kk": m.get("title_kk"),
                                       "at": m.get("at"), **_district_label(m.get("district"))},
                           "demo": bool(m.get("demo"))})
    rank = {"overdue": 0, "todo": 1, "in_progress": 1, "done": 2}
    orders.sort(key=lambda o: (rank["overdue"] if o["overdue"] else rank[o["status"]],
                               o["due"] or "9999", str(o["id"])))
    upcoming = sorted((m for m in meetings if (t := parse_time(m.get("at"))) is not None and t >= now),
                      key=lambda m: parse_time(m["at"]))
    nxt = upcoming[0] if upcoming else None
    return {
        "available": True,
        "orders": orders[:ORDERS_N],
        "counts": {"total": len(orders), "overdue": sum(o["overdue"] for o in orders),
                   "todo": sum(o["status"] == "todo" for o in orders),
                   "in_progress": sum(o["status"] == "in_progress" for o in orders),
                   "done": sum(o["status"] == "done" for o in orders)},
        "next": {"id": nxt.get("id"), "title_ru": nxt.get("title_ru"), "title_kk": nxt.get("title_kk"),
                 "at": nxt.get("at"), "registered": nxt.get("registered"), **_district_label(nxt.get("district")),
                 "demo": bool(nxt.get("demo"))} if nxt else None,
        "meetings": len(meetings),
        "demo": any(m.get("demo") for m in meetings),
    }


def meetings(settings: Settings, *, district=None, now: datetime, all_demo=False) -> dict:
    query = f"district={district}" if district else ""
    try:
        body, how = _read(R13_MEETINGS_MODULE, R13_MEETINGS_FUNCS, "meetings", query, settings, district=district, now=now)
    except _Unavailable as exc:
        out = _fixture_or_empty(settings, exc.reason, all_demo,
                                lambda fx: normalize_meetings(fx["meetings"], district=district, now=now), now)
        return out or _empty(exc.reason, orders=[], counts={}, next=None)
    out = normalize_meetings(body, district=district, now=now)
    out.update(source="r13" if how == "function" else "r13-service")
    return out


# ---------------------------------------------------------------- R13: прогноз (прототип)

FORECAST_N = 5


def _forecast_row(it: dict) -> dict | None:
    if not isinstance(it, dict):
        return None
    target = it.get("target") if isinstance(it.get("target"), dict) else {}
    reasons = it.get("reasons") or it.get("top_reasons") or []
    first = reasons[0] if reasons and isinstance(reasons[0], dict) else {}
    reason_ru = it.get("reason_ru") or first.get("ru")
    reason_kk = it.get("reason_kk") or first.get("kk") or reason_ru
    return {"target": {k: target.get(k) for k in ("kind", "id", "label_ru", "label_kk")} if target else None,
            "label_ru": target.get("label_ru") or it.get("label_ru"),
            "label_kk": target.get("label_kk") or it.get("label_kk") or target.get("label_ru"),
            **_district_label(it.get("district")),
            "category": it.get("main_category") or it.get("category"), "level": it.get("level"),
            "reason_ru": reason_ru, "reason_kk": reason_kk}


def forecast(settings: Settings, *, district=None, now: datetime) -> dict:
    """Прогноз R13. Есть «на неделю» — его; нет — «на следующий месяц» FINAL-4 с честным заголовком. Всегда прототип."""
    try:
        module = _import(R13_FORECAST_MODULE)
    except Exception:
        log.exception("R08: прогноз R13 не загрузился")
        return _empty("module_failed", items=[], prototype=True)
    if module is None:
        return _empty("module_not_ready", items=[], prototype=True)
    try:
        week_fn = next((getattr(module, n) for n in R13_WEEK_FUNCS if callable(getattr(module, n, None))), None)
        if week_fn is not None:
            body, horizon = _unwrap(_call(week_fn, district=district, k=FORECAST_N, now=now)), "week"
        elif callable(getattr(module, "attention_next_month", None)):
            body = _call(module.attention_next_month, district=district, k=FORECAST_N,
                         today=now.astimezone(ASTANA_TZ).date())
            horizon = "month"
        else:
            return _empty("module_not_ready", items=[], prototype=True)
    except Exception:
        log.exception("R08: прогноз R13 ответил ошибкой")
        return _empty("module_failed", items=[], prototype=True)
    body = body if isinstance(body, dict) else {"items": body if isinstance(body, list) else []}
    rows = [r for r in (_forecast_row(it) for it in body.get("items") or []) if r]
    return {"available": True, "source": "r13-" + horizon, "horizon": body.get("horizon") or horizon,
            "month": body.get("month"), "prototype": True,
            "evidence_type": body.get("evidence_type") or "synthetic",
            "demo": bool(body.get("demo", True)), "items": rows[:FORECAST_N],
            "method_ru": body.get("method_ru") or body.get("note_ru"),
            "method_kk": body.get("method_kk") or body.get("note_kk")}
