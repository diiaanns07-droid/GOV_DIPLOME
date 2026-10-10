"""Откуда «Картина дня» берёт данные. Сама ничего не хранит.

    жалобы v2 ............ те же записи, что у тепловой карты R07 (а она берёт их у R09);
    тепловая карта ....... HeatService R07 (ui.civic_heat) — топ мест, темы, районы;
    объекты и отставание . функция R06; пока её нет — fixtures/objects_demo.json (demo);
    предложения и голоса . функция R06; пока её нет — fixtures/proposals_demo.json (demo).

Главное правило: числа «Картины дня» обязаны совпадать с картой. Поэтому жалобы берутся
у того же HeatService, который отвечает на /heat, а не из отдельного запроса к базе.
R01 может подключить всё явно: ui.civic_akim.configure(heat=..., records=..., objects=..., proposals=...).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OBJECTS_FIXTURE = HERE / "fixtures" / "objects_demo.json"
PROPOSALS_FIXTURE = HERE / "fixtures" / "proposals_demo.json"
ASTANA_TZ = timezone(timedelta(hours=5))
STALE_DAYS = 14  # CONTRACT §7: stale = запись не обновлялась больше 14 дней

# Имена функций, которые может отдать R06 в ui.civic_store (prompt R06, п.5). Проверяются по порядку.
R06_OBJECT_FUNCS = ("akim_objects", "lagging_objects", "late_objects", "objects_for_akim")
R06_PROPOSAL_FUNCS = ("akim_proposals", "list_proposals", "proposals_for_akim")


# ---------------------------------------------------------------- тепловая карта R07

def heat_service():
    """Общий HeatService R07 или None, если модуля ещё нет в сборке."""
    try:
        from ui.civic_heat import default_service  # type: ignore
    except ImportError:
        return None
    return default_service()


def heat_engine():
    """Функции расчёта R07 (нужны для «как было неделю назад»)."""
    try:
        from ui.civic_heat import engine  # type: ignore
    except ImportError:
        return None
    return engine


def records_from_heat(svc):
    """Функция since → записи v2 из того же источника, что и карта.

    У HeatService R07 нет публичного метода для записей; просим добавить records(since)
    (INTEGRATION.txt). Пока берём внутренний _records — так числа гарантированно те же.
    """
    if svc is None:
        return None
    fn = getattr(svc, "records", None)
    if not callable(fn):
        fn = getattr(svc, "_records", None)
    return fn if callable(fn) else None


# ---------------------------------------------------------------- R06: объекты и предложения

def _r06(names):
    try:
        import ui.civic_store as store  # type: ignore
    except Exception:
        return None
    for name in names:
        fn = getattr(store, name, None)
        if callable(fn):
            return fn
    return None


def _shift_days(meta: dict, today: date) -> int:
    """На сколько дней сдвинуть даты фикстуры, чтобы она «жила» в сегодняшнем дне."""
    try:
        anchor = date.fromisoformat(meta["anchor"])
    except (KeyError, TypeError, ValueError):
        return 0
    return (today - anchor).days


def _shift(value, days: int):
    if not value or not days:
        return value
    text = str(value)
    if len(text) == 10:
        return (date.fromisoformat(text) + timedelta(days=days)).isoformat()
    return (datetime.fromisoformat(text) + timedelta(days=days)).isoformat(timespec="seconds")


def fixture_objects(today: date) -> list[dict]:
    raw = json.loads(OBJECTS_FIXTURE.read_text("utf-8"))
    days = _shift_days(raw.get("_meta", {}), today)
    out = []
    for o in raw["objects"]:
        o = dict(o)
        for key in ("planned_end", "forecast_end", "updated_at"):
            o[key] = _shift(o.get(key), days)
        out.append(o)
    return out


def fixture_proposals(today: date) -> list[dict]:
    raw = json.loads(PROPOSALS_FIXTURE.read_text("utf-8"))
    days = _shift_days(raw.get("_meta", {}), today)
    out = []
    for p in raw["proposals"]:
        p = dict(p)
        p["created_at"] = _shift(p.get("created_at"), days)
        out.append(p)
    return out


def default_objects():
    """Функция (district, today) → объекты. R06, если есть; иначе демо-фикстура."""
    fn = _r06(R06_OBJECT_FUNCS)
    if fn is not None:
        return (lambda district, today: list(fn(district=district))), "r06"
    return (lambda district, today: fixture_objects(today)), "fixture"


def default_proposals():
    fn = _r06(R06_PROPOSAL_FUNCS)
    if fn is not None:
        return (lambda district, today: list(fn(district=district))), "r06"
    return (lambda district, today: fixture_proposals(today)), "fixture"


# ---------------------------------------------------------------- нормализация объекта R06

def _parse_day(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=ASTANA_TZ)


def normalize_object(o: dict, as_of: datetime) -> dict:
    """Объект в виде для «Картины дня». delay_days и stale берём у R06; нет — считаем по CONTRACT §7."""
    planned, forecast = _parse_day(o.get("planned_end")), _parse_day(o.get("forecast_end"))
    delay = o.get("delay_days")
    if not isinstance(delay, (int, float)):
        delay = (forecast - planned).days if planned and forecast else 0
    updated = _parse_time(o.get("updated_at"))
    days_since = (as_of - updated).days if updated else None
    stale = o.get("stale")
    if not isinstance(stale, bool):
        stale = days_since is not None and days_since > STALE_DAYS
    title_ru = o.get("title_ru") or o.get("title") or o.get("name") or o.get("id")
    return {
        "id": o.get("id"),
        "kind": o.get("kind"),
        "title_ru": title_ru,
        "title_kk": o.get("title_kk") or title_ru,
        "district": o.get("district"),
        "stage": o.get("stage"),
        "planned_end": planned.isoformat() if planned else None,
        "forecast_end": forecast.isoformat() if forecast else None,
        "delay_days": max(0, int(delay)),
        "stale": bool(stale),
        "updated_at": o.get("updated_at"),
        "days_since_update": days_since,
        "has_place": bool(o.get("geometry")),
        "demo": bool(o.get("demo")),
    }
