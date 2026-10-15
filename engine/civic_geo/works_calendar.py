"""R12 · раунд 15 · «Календарь работ» для сотрудника: откуда берутся работы, строки и месяцы, ответы маршрутов.

    GET /api/civic/v2/works-calendar?from&to&district&street&service   -> calendar_response(query, staff)
    GET /api/civic/v2/works-conflicts?from&to&district&service         -> conflicts_response(query, staff)

Оба маршрута — только для сотрудника. Сотрудника проверяет шлюз R01 ДО вызова модуля (раунд 15, ветка R01 d987a112:
V2Handler kind="raw", strip_prefix=True, staff=True — сессия R02 + CSRF; raw-обработчик контекста не получает).
Если шлюз передаёт staff=False явно — модуль отвечает 401 (вторая линия, например при staff_view).

Откуда работы (по порядку, CONTRACT §5.6 и §11):
1. R06 — функция чтения работ v2 из ui.civic_store.v2 (R06_FUNCTIONS; в процессе, только чтение).
2. Демо-режим (CIVIC_DEMO=1), если у R06 ещё нет ни одной работы с участками:
   демо-мир R02 (CIVIC_DEMO_WORLD=1, data/civic/astana/demo-world/world_v1.json → works),
   иначе фикстура R12 data/civic/astana/geo/works_fixture.json — синтетика на настоящих улицах Нуры (demo: true).
   Записи R06 без участков при этом остаются (как «примерное место»), фикстура только добавляет работы с участками.
Числа (сколько работ, конфликтов, дней) считает код; ничего не придумывается.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone

from . import names
from .graph import get_graph
from .paths import GEO_DIR, ROOT
from .works import (APPROX_RADIUS_M, CANCELLED, FALLBACK_SERVICES, KINDS, KIND_LABELS, BoundWork, add_months,
                    bind_all, find_conflicts, parse_day, _norm, _service_names)

LOGGER = logging.getLogger(__name__)

ASTANA_TZ = timezone(timedelta(hours=5))
FIXTURE_PATH = GEO_DIR / "works_fixture.json"
WORLD_PATH = ROOT / "data" / "civic" / "astana" / "demo-world" / "world_v1.json"
R06_MODULE = "ui.civic_store.v2"
# Имена функции чтения работ v2 у R06 (первое найденное). Договорённость — INTEGRATION.txt R12 §R06.
R06_FUNCTIONS = ("works_v2", "calendar_works", "list_works_v2", "works_for_calendar")
DISTRICTS = ("almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka")
DEFAULT_MONTHS_BACK = 1      # календарь по умолчанию: прошлый месяц …
DEFAULT_MONTHS_AHEAD = 11    # … и ещё 11 месяцев вперёд от текущего (весь следующий строительный сезон)
MAX_MONTHS = 24              # длиннее — календарь не читается

# Запасные цвета служб (пока нет профилей R17, CONTRACT §5.4). Без зелёного (он — только «исправлено») и без
# красного (он — только конфликт). Контраст с белым ≥ 3:1 — полосу видно, подпись на полосе белая.
FALLBACK_COLORS = {
    "road": "#5B6577", "traffic": "#0E7FB8", "street_cleaning": "#6B7A8F", "transport": "#5A5FD6",
    "lighting": "#B07A06", "landscaping": "#0F8A80", "greenery": "#5F7F1E", "waste": "#7A6E64",
    "utilities": "#8A5A2B", "heating": "#D0621B", "water": "#2563EB", "power": "#8E44C9", "gas": "#B5398F",
    "housing": "#6D5BD0", "ecology": "#2F7D6A", "emergency": "#B4235A", "police": "#2B3F7A", "animals": "#9A5BC2",
    "parking": "#0B7A93", "akimat": "#3E4A5C",
}
NO_SERVICE_COLOR = "#7B8494"


class CalendarError(ValueError):
    def __init__(self, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.code, self.message, self.field = code, message, field


def today_astana() -> date:
    return datetime.now(ASTANA_TZ).date()


def demo_mode() -> bool:
    return os.environ.get("CIVIC_DEMO") == "1"


def world_mode() -> bool:
    return os.environ.get("CIVIC_DEMO_WORLD") == "1"


# ------------------------------------------------------------------ источники
def _shift_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 февраля
        return day.replace(year=day.year + years, day=28)


def load_fixture(today: date | None = None, path=FIXTURE_PATH) -> list[dict]:
    """Фикстура R12: даты записаны для anchor (день сборки). Если показ позже чем через год — даты сдвигаются на
    целые годы, чтобы «асфальт в мае, сети в июле» оставались ближайшим сезоном, а месяцы — теми же."""
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return []
    today = today or today_astana()
    anchor = parse_day(data.get("anchor")) or today
    shift = max(0, int((today - anchor).days // 365.25))
    out = []
    for raw in data.get("works") or []:
        w = dict(raw)
        for key in ("starts_on", "ends_on"):
            d = parse_day(w.get(key))
            if d and shift:
                w[key] = _shift_years(d, shift).isoformat()
        w.setdefault("demo", True)
        w.setdefault("source", "demo")
        out.append(w)
    return out


def _relative_day(rec: dict, keys, today: date) -> str | None:
    """Демо-мир R02 хранит время относительно засева: in_days (вперёд) / ago_days (назад)."""
    for key, sign in keys:
        v = rec.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return (today + timedelta(days=sign * int(v))).isoformat()
    return None


def _season_day(spec: dict, today: date) -> str | None:
    """{"season": {"month": 5, "day": 4}} — дата в следующем строительном сезоне (правило R02 SCHEMA §1):
    год = текущий, если сейчас январь–март, иначе следующий."""
    try:
        month, day = int(spec["month"]), int(spec["day"])
        year = today.year if today.month <= 3 else today.year + 1
        return date(year, month, day).isoformat()
    except (KeyError, TypeError, ValueError):
        return None


def _materialize_day(value, today: date):
    """Относительная дата мира R02 → «ГГГГ-ММ-ДД»: {"day": N}, {"season": {…}}, {"in_days"/"ago_days": N}."""
    if not isinstance(value, dict):
        return value
    if isinstance(value.get("day"), (int, float)) and not isinstance(value.get("day"), bool):
        return (today + timedelta(days=int(value["day"]))).isoformat()
    if isinstance(value.get("season"), dict):
        return _season_day(value["season"], today)
    for key, sign in (("in_days", 1), ("ago_days", -1)):
        v = value.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return (today + timedelta(days=sign * float(v))).isoformat()
    return None


def _r02_materialize(data: dict):
    """Сначала — функция R02 (ml.datasets.demo_world_io.materialize: один «сейчас» со всеми модулями); нет — своя."""
    try:
        from ml.datasets import demo_world_io  # только чтение, вызов в процессе (CONTRACT §11)
        return demo_world_io.materialize(data, datetime.now(ASTANA_TZ))
    except Exception:
        return None


def is_street_work(record: dict) -> bool:
    """Работа на улице: работы и перекрытия проезда; отключения воды, тепла, света, газа — не работы (как у R06)."""
    if record.get("type") != "outage":
        return True
    return record.get("utility") == "road_closure" or record.get("kind") == "closure"


def load_world(today: date | None = None, path=WORLD_PATH, raw_world: dict | None = None) -> list[dict]:
    """Работы демо-мира R02 (CONTRACT §11). Даты: как есть или из относительных полей (§1 SCHEMA R02)."""
    try:
        data = raw_world if raw_world is not None else json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return []
    today = today or today_astana()
    materialized = _r02_materialize(data) if raw_world is None and isinstance(data, dict) else None
    if isinstance(materialized, dict):
        data = materialized
    out = []
    for raw in (data.get("works") if isinstance(data, dict) else None) or []:
        if not isinstance(raw, dict) or not is_street_work(raw):
            continue
        w = dict(raw)
        for key in ("starts_on", "ends_on", "starts_at", "ends_at"):
            if isinstance(w.get(key), dict):
                w[key] = _materialize_day(w[key], today)
        if not w.get("starts_on"):
            w["starts_on"] = _relative_day(raw, (("starts_in_days", 1), ("start_in_days", 1), ("in_days", 1),
                                                 ("starts_ago_days", -1), ("start_ago_days", -1), ("ago_days", -1)), today)
        if not w.get("ends_on"):
            w["ends_on"] = _relative_day(raw, (("ends_in_days", 1), ("end_in_days", 1), ("ends_ago_days", -1),
                                               ("end_ago_days", -1)), today)
        if not w.get("ends_on") and w.get("starts_on") and isinstance(raw.get("days"), int):
            w["ends_on"] = (parse_day(w["starts_on"]) + timedelta(days=max(0, raw["days"] - 1))).isoformat()
        w.setdefault("demo", True)
        w.setdefault("source", "demo")
        out.append(w)
    return out


_planned_cache: dict = {}
# Мир R02, который R01 передал при засеве (seed_world: уже материализован с одним «сейчас» на все модули).
_WORLD: dict = {}


def remember_world(records, now=None) -> dict:
    """R01 при CIVIC_DEMO=1 и CIVIC_DEMO_WORLD=1 зовёт engine.civic_geo.seed_world(db_path, records, now): R12 записей не
    хранит (работы — у R06), но запоминает работы мира и задуманные конфликты — для id конфликтов (сцена 8 = cf-w15-01)
    и как запасной источник, если у R06 ещё нет работ v2."""
    if not isinstance(records, dict):
        return {"inserted": 0, "skipped": 0, "note": "нет мира"}
    today = (now.astimezone(ASTANA_TZ).date() if isinstance(now, datetime) else None) or today_astana()
    works = load_world(today, raw_world=records)
    items = records.get("planned_conflicts")
    planned = {(c.get("kind"), tuple(sorted(c["works"]))): c.get("id")
               for c in (items if isinstance(items, list) else [])
               if isinstance(c, dict) and c.get("id") and isinstance(c.get("works"), list)
               and all(isinstance(w, str) for w in c["works"])}
    _WORLD.clear()
    _WORLD.update({"works": works, "planned": planned, "scene": _scene_of(records), "today": today.isoformat()})
    return {"inserted": 0, "skipped": len(works), "planned_conflicts": len(planned),
            "note": "R12 не хранит записи: работы засевает R06, конфликты считаются при открытии календаря"}


def _scene_of(world) -> str | None:
    """Конфликт сцены 8 мира R02 (scenes.scene8.conflict) или None — при любом другом виде данных."""
    scenes = world.get("scenes") if isinstance(world, dict) else None
    scene = scenes.get("scene8") if isinstance(scenes, dict) else None
    cid = scene.get("conflict") if isinstance(scene, dict) else None
    return cid if isinstance(cid, str) and cid else None


def scene_conflict(path=WORLD_PATH) -> str | None:
    """Конфликт сцены 8 демо-мира: в режиме мира экран открывается на нём (DEMO_SCRIPT R01, сцена 8, шаг 4 —
    «асфальт в мае, сети в июле»), а список конфликтов остаётся по срочности. Мир засеян — из него, иначе из файла."""
    if _WORLD.get("planned") is not None and "scene" in _WORLD:
        return _WORLD.get("scene")
    planned_ids(path)
    return _planned_cache.get("scene")


def planned_ids(path=WORLD_PATH) -> dict:
    """id задуманных конфликтов демо-мира R02 (planned_conflicts) по (вид, работы): тогда у найденного конфликта id —
    тот же, что в сценах R02 и проверках R10 (сцена 8: cf-w15-01). Сначала — мир, переданный R01 при засеве; иначе файл."""
    if _WORLD.get("planned"):
        return _WORLD["planned"]
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return {}
    if _planned_cache.get("stamp") != stamp:
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            data = None
        items = data.get("planned_conflicts") if isinstance(data, dict) else None
        ids = {}
        for c in items if isinstance(items, list) else []:
            works = c.get("works") if isinstance(c, dict) else None
            if isinstance(works, list) and c.get("id") and all(isinstance(w, str) for w in works):
                ids[(c.get("kind"), tuple(sorted(works)))] = c.get("id")
        # Кэш — одной записью: сбой на середине не оставляет «stamp без ids».
        _planned_cache.clear()
        _planned_cache.update({"stamp": stamp, "scene": _scene_of(data), "ids": ids})
    return _planned_cache["ids"]


def read_r06() -> tuple[list[dict] | None, str]:
    """Работы v2 из хранилища R06 (только чтение). (None, причина) — модуля или функции ещё нет."""
    try:
        mod = importlib.import_module(R06_MODULE)
    except Exception:  # нет модуля или он не загрузился — календарь работает на демо-данных
        return None, "module_missing"
    for name in R06_FUNCTIONS:
        fn = getattr(mod, name, None)
        if not callable(fn):
            continue
        try:
            got = fn()
        except Exception as exc:  # хранилище не подключено (503) или ошибка — не роняем календарь
            status = getattr(exc, "status", None)
            if status != 503:
                LOGGER.warning("R06 %s.%s: %s", R06_MODULE, name, exc)
            return None, "not_ready" if status == 503 else "failed"
        items = (got.get("items") or got.get("works")) if isinstance(got, dict) else got
        return [x for x in (items or []) if isinstance(x, dict)], "ok"
    return None, "no_function"


def _has_place(record: dict) -> bool:
    return bool(record.get("segments")) or bool(record.get("street") and record.get("from") and record.get("to"))


def load_works(today: date | None = None) -> tuple[list[dict], dict]:
    """(записи работ, {source, r06, real}) — см. порядок источников в начале модуля.

    Настоящие работы LOCAL-5 (data/civic/astana/nura-real/records.csv, engine.civic_geo.real_works) добавляются всегда,
    если файл есть: source "real", ссылка на источник, покрытие привязки — info["real"]."""
    today = today or today_astana()
    records, r06 = read_r06()
    info = {"r06": r06, "source": "r06" if records is not None else None}
    records = [r for r in (records or []) if is_street_work(r)]
    # Демо (мир R02 или фикстура) — только если у R06 нет ни одной работы с участком; настоящие работы LOCAL-5 на это
    # не влияют и добавляются после (иначе одна настоящая запись прятала бы сцену 8).
    if demo_mode() and not any(_has_place(r) for r in records):
        extra = (_WORLD.get("works") or load_world(today)) if world_mode() else []
        label = "world"
        if not any(_has_place(r) for r in extra):
            extra, label = load_fixture(today), "fixture"
        if extra:
            known = {r.get("id") for r in records}
            records.extend(r for r in extra if r.get("id") not in known)
            info["source"] = f"{info['source']}+{label}" if info["source"] else label
    try:
        from .real_works import load_real_works
        real, coverage = load_real_works()
    except Exception:
        LOGGER.exception("civic_geo real works failed")
        real, coverage = [], {"status": "FAILED"}
    info["real"] = coverage
    if real:
        known = {r.get("id") for r in records}
        records.extend(r for r in real if r.get("id") not in known)
        info["source"] = f"{info['source']}+real" if info["source"] else "real"
    info["source"] = info["source"] or "none"
    return records, info


# ------------------------------------------------------------------ параметры запроса
def _one(query: dict, key: str):
    v = query.get(key)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else None
    return v.strip() if isinstance(v, str) else v


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _month_end(d: date) -> date:
    return add_months(d.replace(day=1), 1) - timedelta(days=1)


def parse_period(query: dict, today: date) -> tuple[date, date]:
    """from/to: «2027-05» (месяц целиком) или «2027-05-01». Нет — прошлый месяц и 11 месяцев вперёд."""
    def day(key, end=False):
        text = _one(query, key)
        if not text:
            return None
        if len(text) == 7:
            d = parse_day(text + "-01")
            if d is None:
                raise CalendarError("bad_date", f"Параметр {key}: месяц в виде ГГГГ-ММ.", key)
            return _month_end(d) if end else d
        d = parse_day(text) if len(text) == 10 else None
        if d is None:
            raise CalendarError("bad_date", f"Параметр {key}: дата в виде ГГГГ-ММ-ДД.", key)
        return d
    start, end = day("from"), day("to", end=True)
    if start is None and end is None:
        start = add_months(_month_start(today), -DEFAULT_MONTHS_BACK)
        end = _month_end(add_months(_month_start(today), DEFAULT_MONTHS_AHEAD))
    elif start is None:
        start = add_months(_month_start(end), -(DEFAULT_MONTHS_BACK + DEFAULT_MONTHS_AHEAD))
    elif end is None:
        end = _month_end(add_months(_month_start(start), DEFAULT_MONTHS_BACK + DEFAULT_MONTHS_AHEAD))
    if end < start:
        raise CalendarError("bad_period", "Конец периода раньше начала.", "to")
    if (end.year - start.year) * 12 + end.month - start.month + 1 > MAX_MONTHS:
        raise CalendarError("period_too_long", f"Период — не длиннее {MAX_MONTHS} месяцев.", "to")
    return start, end


def parse_filters(query: dict) -> dict:
    district = (_one(query, "district") or "").lower() or None
    if district in ("all", "*"):
        district = None
    if district is not None and district not in DISTRICTS:
        raise CalendarError("bad_district", "Неизвестный район.", "district")
    service = _one(query, "service") or None
    if service is not None and service not in FALLBACK_SERVICES:
        raise CalendarError("bad_service", "Неизвестная служба.", "service")
    street = _one(query, "street") or None
    if street is not None and len(street) > 80:
        raise CalendarError("bad_street", "Название улицы — не длиннее 80 знаков.", "street")
    kind = _one(query, "kind") or None
    if kind is not None and kind not in KINDS:
        raise CalendarError("bad_kind", "Неизвестный вид работы.", "kind")
    return {"district": district, "service": service, "street": street, "kind": kind}


# ------------------------------------------------------------------ сборка календаря
def _months(start: date, end: date) -> list[str]:
    out, cur = [], _month_start(start)
    while cur <= end:
        out.append(cur.strftime("%Y-%m"))
        cur = add_months(cur, 1)
    return out


def _intersects(a0: date, a1: date, b0: date, b1: date) -> bool:
    return a0 <= b1 and b0 <= a1


def service_list(ids) -> list[dict]:
    """Службы календаря: id, названия (таблица служб R08), цвет (профиль R17, иначе запасной)."""
    names_ = _service_names()
    profiles = _profiles()
    out = []
    for sid in sorted({i for i in ids if i}, key=lambda s: (list(FALLBACK_SERVICES).index(s) if s in FALLBACK_SERVICES else 99, s)):
        item = names_.get(sid) or FALLBACK_SERVICES.get(sid) or {}
        prof = profiles.get(sid) or {}
        out.append({"id": sid, "name_ru": item.get("ru") or sid, "name_kk": item.get("kk") or item.get("ru") or sid,
                    "color": prof.get("color") or FALLBACK_COLORS.get(sid, NO_SERVICE_COLOR),
                    "icon": prof.get("icon"), "color_source": "r17" if prof.get("color") else "r12"})
    return out


def _profiles() -> dict:
    """Профили служб R17 (CONTRACT §5.4): цвет и иконка. Нет модуля — {} (запасные цвета R12)."""
    try:
        mod = importlib.import_module("ui.civic_agencies")
    except Exception:
        return {}
    for name in ("service_profiles", "profiles", "list_profiles"):
        fn = getattr(mod, name, None)
        if callable(fn):
            try:
                got = fn()
            except Exception:
                return {}
            items = got.get("items") or got.get("services") or got.get("profiles") if isinstance(got, dict) else got
            if isinstance(items, dict):
                return {k: v for k, v in items.items() if isinstance(v, dict)}
            return {x.get("id"): x for x in (items or []) if isinstance(x, dict) and x.get("id")}
    return {}


def _row_key(w: BoundWork) -> tuple[str, str | None, str | None]:
    if w.street_ru:
        short = names.ru_short(w.street_ru)
        return "street:" + _norm(w.street_ru), short, w.street_kk or w.street_ru
    return "place:none", None, None


def build_calendar(records: list[dict], date_from: date, date_to: date, filters: dict | None = None,
                   today: date | None = None, graph=None) -> dict:
    """Календарь: строки по улицам, полосы работ по датам, конфликты со связями. Детерминированно."""
    t0 = time.perf_counter()
    filters = filters or {}
    today = today or today_astana()
    g = graph or get_graph()
    bound = bind_all(records, g)
    district = filters.get("district")
    in_district = [w for w in bound if district is None or w.district == district]
    conflicts_all = find_conflicts(in_district, g, today)
    planned = planned_ids()
    if planned:
        for c in conflicts_all:
            pid = planned.get((c["kind"], tuple(c["works"])))
            if pid:
                c["id"], c["planned"] = pid, True

    def visible(w: BoundWork) -> bool:
        if (w.status or "") in CANCELLED or not w.start:
            return False
        if filters.get("service") and w.service != filters["service"]:
            return False
        if filters.get("kind") and w.kind != filters["kind"]:
            return False
        if filters.get("street"):
            want = _norm(filters["street"])
            if want not in _norm(w.street_ru) and want not in _norm(w.street_kk) and want not in _norm(names.ru_short(w.street_ru)):
                return False
        return _intersects(w.start, w.end, date_from, date_to)

    shown = {w.id: w for w in in_district if visible(w)}
    by_id = {w.id: w for w in in_district}
    conflicts = []
    for c in conflicts_all:
        if not any(i in shown for i in c["works"]):
            continue
        if not _intersects(parse_day(c["when_from"]), parse_day(c["when_to"]), date_from, date_to):
            continue
        conflicts.append(c)
    context = {}
    for c in conflicts:  # вторая работа конфликта видна, даже если её отсекли фильтры службы/улицы (без неё нет связи)
        for i in c["works"]:
            if i not in shown and i in by_id:
                context[i] = by_id[i]
    works_out = []
    conflicts_of: dict[str, list[str]] = {}
    for c in conflicts:
        for i in c["works"]:
            conflicts_of.setdefault(i, []).append(c["id"])
    rows: dict[str, dict] = {}
    ordered = sorted(list(shown.values()) + list(context.values()), key=lambda w: (w.start, w.end, w.id))
    for w in ordered:
        item = w.to_public()
        item["conflicts"] = conflicts_of.get(w.id, [])
        if w.id in context:
            item["context"] = True
        key, ru, kk = _row_key(w)
        row = rows.setdefault(key, {"key": key, "street_ru": ru, "street_kk": kk, "works": [], "conflicts": 0,
                                    "first": item["starts_on"]})
        row["works"].append(w.id)
        item["row"] = key
        works_out.append(item)
    for c in conflicts:
        for k in {_row_key(by_id[i])[0] for i in c["works"] if i in by_id}:
            if k in rows:
                rows[k]["conflicts"] += 1
    # Порядок строк: сначала с конфликтами (важнее), потом по первой дате; «без улицы» — в конце.
    row_list = sorted(rows.values(), key=lambda r: (r["key"] == "place:none", r["conflicts"] == 0, r["first"] or "",
                                                     r["street_ru"] or ""))
    for r in row_list:
        r.pop("first", None)
    undated = [w for w in in_district if not w.start and (w.status or "") not in CANCELLED]
    services = service_list([w.service for w in ordered])
    counts = {
        "works": len(shown), "context": len(context), "conflicts": len(conflicts),
        "high": sum(1 for c in conflicts if c["severity"] == "high"),
        "by_kind": {k: sum(1 for c in conflicts if c["kind"] == k)
                    for k in ("dig_after_surface", "same_segment_overlap", "parallel_closures")},
        "approximate": sum(1 for w in shown.values() if w.approximate),
        "undated": len(undated), "total_in_district": len(in_district),
    }
    out = {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat(), "today": today.isoformat()},
        "months": _months(date_from, date_to),
        "filters": {k: v for k, v in filters.items() if v},
        "rows": row_list,
        "works": works_out,
        "conflicts": conflicts,
        "services": services,
        "kinds": [{"id": k, "name_ru": KIND_LABELS[k][0], "name_kk": KIND_LABELS[k][1]} for k in KINDS],
        "undated": [{"id": w.id, "title_ru": w.record.get("title_ru") or w.record.get("title"),
                     "title_kk": w.record.get("title_kk"), "service": w.service} for w in undated[:50]],
        "counts": counts,
        "demo": any(w.demo for w in ordered),
        "approx_radius_m": APPROX_RADIUS_M,
        "generated_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
    scene = scene_conflict() if world_mode() else None
    if scene and any(c["id"] == scene for c in conflicts):
        out["scene_conflict"] = scene  # экран открывается на нём; порядок списка не меняется
    return out


# ------------------------------------------------------------------ для соседей (вызов в процессе, только чтение)
def conflicts_summary(district: str | None = None, months_ahead: int = DEFAULT_MONTHS_AHEAD, limit: int = 3) -> dict:
    """Короткая сводка конфликтов работ для R08 (ситуационный центр) и R17 («Штаб ведомств»).

    {"conflicts": n, "high": k, "top": [{id, kind, severity, stage, title_ru, title_kk, street_ru, street_kk, advice_ru,
    advice_kk, when_from, when_to, works}], "period": {...}, "demo": bool, "source": "..."} — те же числа и советы, что
    в «Календаре работ» (R03 «Спросить Birge» читает совет первого конфликта).
    Права проверяет вызывающий модуль (данные — для экранов сотрудника). Ошибка данных — {"conflicts": 0, ...}."""
    today = today_astana()
    start = add_months(_month_start(today), -DEFAULT_MONTHS_BACK)
    end = _month_end(add_months(_month_start(today), max(0, int(months_ahead))))
    try:
        records, info = load_works(today)
        cal = build_calendar(records, start, end, {"district": district} if district in DISTRICTS else {}, today)
    except Exception:
        LOGGER.exception("civic_geo conflicts_summary failed")
        return {"conflicts": 0, "high": 0, "top": [], "period": {"from": start.isoformat(), "to": end.isoformat()},
                "demo": False, "source": "error"}
    top = [{k: c.get(k) for k in ("id", "kind", "severity", "stage", "title_ru", "title_kk", "street_ru", "street_kk",
                                  "advice_ru", "advice_kk", "when_from", "when_to", "works")}
           for c in cal["conflicts"][:max(0, int(limit))]]
    return {"conflicts": cal["counts"]["conflicts"], "high": cal["counts"]["high"], "top": top,
            "period": cal["period"], "demo": cal["demo"], "source": info["source"]}


# ------------------------------------------------------------------ ответы маршрутов
def _error(status: int, code: str, message: str, field: str | None = None):
    body = {"error": {"code": code, "message": message}}
    if field:
        body["error"]["field"] = field
    return status, body


def _staff_only(staff) -> tuple[int, dict] | None:
    """Сотрудника проверяет шлюз R01 (staff=True у маршрута); явное staff=False — отказ и здесь."""
    if staff is False:
        return _error(401, "staff_required", "Календарь работ — для сотрудников. Войдите как сотрудник.")
    return None


def calendar_response(query: dict, staff=None):
    denied = _staff_only(staff)
    if denied:
        return denied
    try:
        today = today_astana()
        start, end = parse_period(query, today)
        filters = parse_filters(query)
        records, info = load_works(today)
        body = build_calendar(records, start, end, filters, today)
        body["source"] = info["source"]
        body["r06"] = info["r06"]
        body["real"] = info.get("real")  # покрытие LOCAL-5: сколько на участке, примерно, без места, без дат (или NOT_RUN)
        return 200, body
    except CalendarError as exc:
        return _error(400, exc.code, exc.message, exc.field)
    except Exception:
        LOGGER.exception("civic_geo works-calendar failed")
        return _error(503, "works_unavailable", "Календарь работ сейчас недоступен. Повторите позже.")


def conflicts_response(query: dict, staff=None):
    """Только конфликты (для слоя карты «Конфликты работ» и для соседей: R08, R17)."""
    denied = _staff_only(staff)
    if denied:
        return denied
    try:
        today = today_astana()
        start, end = parse_period(query, today)
        filters = parse_filters(query)
        records, info = load_works(today)
        cal = build_calendar(records, start, end, filters, today)
        works = {w["id"]: {k: w.get(k) for k in ("id", "title_ru", "title_kk", "service", "kind", "kind_ru", "kind_kk",
                                                 "starts_on", "ends_on", "status", "street_ru", "street_kk", "demo",
                                                 "district", "geometry", "bbox", "length_m")}
                 for w in cal["works"] if w["conflicts"]}
        return 200, {"period": cal["period"], "filters": cal["filters"], "conflicts": cal["conflicts"],
                     "works": works, "services": [s for s in cal["services"] if any(w["service"] == s["id"] for w in works.values())],
                     "counts": {k: cal["counts"][k] for k in ("conflicts", "high", "by_kind")},
                     "demo": cal["demo"], "source": info["source"], "generated_ms": cal["generated_ms"]}
    except CalendarError as exc:
        return _error(400, exc.code, exc.message, exc.field)
    except Exception:
        LOGGER.exception("civic_geo works-conflicts failed")
        return _error(503, "works_unavailable", "Конфликты работ сейчас недоступны. Повторите позже.")
