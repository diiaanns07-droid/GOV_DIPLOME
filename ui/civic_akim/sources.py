"""Откуда «Картина дня» берёт данные. Сама ничего не хранит.

    жалобы v2 ............ те же записи, что у тепловой карты R07 (а она берёт их у R09);
    тепловая карта ....... HeatService R07 (ui.civic_heat) — топ мест, темы, районы;
    объекты и отставание . R06 ui.civic_store.v2.lagging_objects(district); пока модуля нет или шлюз R01
                           не связал его с базой (bind) — fixtures/objects_demo.json (demo);
    предложения и голоса . R06 ui.civic_store.v2.list_proposals(district=, status="proposal"); иначе —
                           fixtures/proposals_demo.json (demo).

Главное правило: числа «Картины дня» обязаны совпадать с картой. Поэтому жалобы берутся
у того же HeatService, который отвечает на /heat, а не из отдельного запроса к базе.
R01 может подключить всё явно: ui.civic_akim.configure(heat=..., records=..., objects=..., proposals=...).
"""
from __future__ import annotations

import json
import re
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
    """Функция R06 по имени: сначала модуль v2 (раунд 14, ветка claude/round-14-r06), потом сам пакет."""
    for modname in ("ui.civic_store.v2", "ui.civic_store"):
        try:
            module = __import__(modname, fromlist=["_"])
        except Exception:
            continue
        for name in names:
            fn = getattr(module, name, None)
            if callable(fn):
                return fn
    return None


class R06NotReady(RuntimeError):
    """Модуль R06 есть, но шлюз R01 ещё не вызвал civic_store.v2.bind(service) — базы нет."""


def _call_r06(fn, **kwargs):
    try:
        return fn(**kwargs)
    except Exception as exc:  # V2Error R06: status 503 module_not_ready — модуль не связан с базой
        if getattr(exc, "status", None) == 503 or getattr(exc, "code", None) == "module_not_ready":
            raise R06NotReady(str(exc)) from exc
        raise


def r06_object_list(answer) -> list[dict]:
    """Ответ R06 → список объектов. lagging_objects отдаёт {late:[…], stale:[…]} (объект может быть в обоих);
    на будущее принимается и простой список, и {items:[…]}."""
    if isinstance(answer, list):
        return answer
    if not isinstance(answer, dict):
        return []
    if "items" in answer:
        return list(answer.get("items") or [])
    seen, out = set(), []
    for item in list(answer.get("late") or []) + list(answer.get("stale") or []):
        key = item.get("id") if isinstance(item, dict) else None
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def r06_proposal_list(answer) -> list[dict]:
    """Ответ R06 list_proposals → {items:[…], truncated}; список тоже принимается."""
    if isinstance(answer, list):
        return answer
    if isinstance(answer, dict):
        return list(answer.get("items") or [])
    return []


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
    """Функция (district, today) → объекты. R06, если есть и связан с базой; иначе демо-фикстура (demo: true)."""
    fn = _r06(R06_OBJECT_FUNCS)
    if fn is None:
        return (lambda district, today: fixture_objects(today)), "fixture"

    def objects(district, today):
        try:
            return r06_object_list(_call_r06(fn, district=district))
        except R06NotReady:
            return fixture_objects(today)
    return objects, "r06"


def default_proposals():
    fn = _r06(R06_PROPOSAL_FUNCS)
    if fn is None:
        return (lambda district, today: fixture_proposals(today)), "fixture"

    def proposals(district, today):
        kwargs = {"district": district}
        if getattr(fn, "__name__", "") == "list_proposals":
            kwargs["status"] = "proposal"  # «Картине дня» нужны только открытые для голосования
        try:
            return r06_proposal_list(_call_r06(fn, **kwargs))
        except R06NotReady:
            return fixture_proposals(today)
    return proposals, "r06"


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


_DEMO_PREFIX = re.compile(r"^\s*(Демо|Demo|Үлгі)\s*[:·—-]\s*", re.I)
_DEMO_SUFFIX = re.compile(r"\s*\((синтетика|synthetic|демо|demo)\)\s*$", re.I)


def demo_title(title):
    """«Демо: ремонт тротуара (синтетика)» → «Ремонт тротуара». Только для записей demo: true —
    пометку «Пример» страница ставит сама, служебные слова в названии не нужны (UX_BRIEF: без технических слов)."""
    if not isinstance(title, str):
        return title
    clean = _DEMO_SUFFIX.sub("", _DEMO_PREFIX.sub("", title)).strip()
    return (clean[:1].upper() + clean[1:]) if clean else title


def normalize_object(o: dict, as_of: datetime) -> dict:
    """Объект в виде для «Картины дня». delay_days и stale берём у R06; нет — считаем по CONTRACT §7."""
    planned, forecast = _parse_day(o.get("planned_end")), _parse_day(o.get("forecast_end"))
    delay = o.get("delay_days")
    if not isinstance(delay, (int, float)):
        delay = (forecast - planned).days if planned and forecast else 0
    updated = _parse_time(o.get("updated_at") or o.get("last_update_at"))
    days_since = (as_of - updated).days if updated else None
    if days_since is None and isinstance(o.get("stale_days"), (int, float)):
        days_since = int(o["stale_days"])  # R06 lagging_objects: дней без обновления, времени нет
    stale = o.get("stale")
    if not isinstance(stale, bool):
        stale = days_since is not None and days_since > STALE_DAYS
    title = o.get("title")
    if isinstance(title, dict):  # civic-v1 может хранить {ru, kk}
        title_ru = o.get("title_ru") or title.get("ru") or title.get("kk") or o.get("id")
        title_kk = o.get("title_kk") or title.get("kk") or title_ru
    else:
        title_ru = o.get("title_ru") or title or o.get("name") or o.get("id")
        title_kk = o.get("title_kk") or title_ru
    if o.get("demo"):
        title_ru, title_kk = demo_title(title_ru), demo_title(title_kk)
    return {
        "id": o.get("id"),
        "kind": o.get("kind"),
        "title_ru": title_ru,
        "title_kk": title_kk,
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
