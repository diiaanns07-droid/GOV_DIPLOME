"""Отметки событий на шкале «Хроники города» (R07): «Буран 12 окт», «Авария теплосети»…

Только из двух источников (CONTRACT §6): кризисы R17 (ui.civic_agencies, CONTRACT §5.5) и события демо-мира
(свои отметки из world.seed_world). Сами отметки R07 не придумывает. Модуля R17 нет или он упал — шкала
без его отметок, а не ошибка (CONTRACT §7: вызовы соседей — чтением и с запасным вариантом).

Как читается R17 (первое, что найдётся): incident_marks(start, end) — его функция для хроники ({id, kind, title_ru,
title_kk, started_at, closed_at, district, status, demo}); иначе list_incidents(status="all") → {"items": [публичная часть]};
иначе сервис make_service(db_path).handle("GET", "/api/civic/v2/incidents", …). Ответ R17 кэшируется на 30 с.
Кризис о событии мира (тот же район и время, связь event) — ссылка отметки события, а не вторая отметка (world.same_story).
"""
from __future__ import annotations

import importlib
import inspect
import logging
import threading
import time
from datetime import datetime

from . import geo, world
from .engine import ASTANA_TZ, iso, parse_time

log = logging.getLogger("civic_heat")
R17_MODULE = "ui.civic_agencies"
R17_TTL_S = 30.0
_lock = threading.Lock()
_r17_cache: dict = {}     # db_path -> (monotonic, [кризисы])
_r17_services: dict = {}  # db_path -> сервис R17 (один на процесс, как у шлюза)


def _items(body) -> list:
    """Список кризисов из ответа R17: список, {items}, {incidents}, конверт {ok, data}."""
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if isinstance(body, dict):
        for k in ("data", "body"):
            if k in body and isinstance(body[k], (dict, list)):
                return _items(body[k])
        for k in ("items", "incidents"):
            if isinstance(body.get(k), list):
                return [x for x in body[k] if isinstance(x, dict)]
    return []


def _call(fn, db_path):
    params = inspect.signature(fn).parameters
    if not params:
        return fn()
    if "db_path" in params:
        return fn(db_path=db_path)
    return fn(db_path)


def r17_incidents(db_path: str | None, since=None, until=None) -> list[dict]:
    """Кризисы R17 (CONTRACT §5.5). Нет модуля / функции / базы — []."""
    key = (db_path or "", since.isoformat() if since else "", until.isoformat() if until else "")
    with _lock:
        hit = _r17_cache.get(key)
        if hit and time.monotonic() - hit[0] < R17_TTL_S:
            return hit[1]
    found: list = []
    try:
        mod = importlib.import_module(R17_MODULE)
    except ModuleNotFoundError:
        mod = None
    except Exception:
        log.exception("R17 (%s) не загрузился — хроника без его отметок", R17_MODULE)
        mod = None
    if mod is not None:
        try:
            if callable(getattr(mod, "incident_marks", None)):
                found = _items(mod.incident_marks(since, until))
            elif callable(getattr(mod, "list_incidents", None)):
                fn = mod.list_incidents
                params = inspect.signature(fn).parameters
                found = _items(fn(status="all") if "status" in params else _call(fn, db_path))
            elif db_path and callable(getattr(mod, "make_service", None)):
                with _lock:
                    svc = _r17_services.get(db_path)
                if svc is None:
                    svc = mod.make_service(db_path)
                    with _lock:
                        _r17_services[db_path] = svc
                reply = svc.handle("GET", "/api/civic/v2/incidents", "", None, None, {})
                if isinstance(reply, dict) and reply.get("status") == 200:
                    found = _items(reply.get("body"))
        except Exception:
            log.exception("R17: кризисы для хроники не прочитались")
            found = []
    with _lock:
        _r17_cache[key] = (time.monotonic(), found)
    return found


def _with_names(m: dict) -> dict:
    d = m.get("district")
    info = geo.districts().get(d) if d else None
    out = dict(m)
    out["district_ru"] = info["name_ru"] if info else None
    out["district_kk"] = info["name_kk"] if info else None
    st, en = parse_time(m.get("started_at")), parse_time(m.get("ended_at"))
    out["start"] = st.astimezone(ASTANA_TZ).date().isoformat() if st else None
    out["end"] = en.astimezone(ASTANA_TZ).date().isoformat() if en else None
    return out


def collect(svc, since: datetime, until: datetime, *, district: str | None = None) -> list[dict]:
    """Отметки, которые пересекают [since, until]: сначала свои (мир), потом R17 — у R17 приоритет по id."""
    path = getattr(svc, "db_path", None) or world.db_path()
    by_id: dict[str, dict] = {}
    for m in world.stored_marks(path):
        by_id[m["id"]] = m
    for inc in r17_incidents(path, since, until):
        m = world.mark_from_world(inc, until, source="incident")
        if not m:
            continue
        m["event"] = inc.get("event") if isinstance(inc.get("event"), str) else None
        m["incident"] = m["id"]
        # Тот же кризис, что засеян из мира (id совпал), — свежие данные R17 вместо копии, номер сцены сохраняем
        old = by_id.get(m["id"])
        if old is not None:
            m["scene"] = old.get("scene")
            by_id[m["id"]] = m
            continue
        # Кризис о событии мира (связь event / тот же район и время) — ссылка отметки события, а не вторая отметка
        story = next((x for x in by_id.values() if x.get("incident") == m["id"] and x.get("id") != m["id"]), None) or \
            next((x for x in by_id.values() if x.get("source") != "incident" and x.get("id") != m["id"]
                  and x.get("incident") is None and world.same_story(x, m)), None)
        if story is not None:
            story["incident"] = m["id"]
            if m.get("status") == "active":
                story["status"] = "active"
            continue
        by_id[m["id"]] = m
    out = []
    for m in by_id.values():
        st, en = parse_time(m.get("started_at")), parse_time(m.get("ended_at"))
        if st is None or st > until or (en is not None and en < since):
            continue
        if district and m.get("district") and m["district"] != district:
            continue
        out.append(_with_names(m))
    out.sort(key=lambda m: m["started_at"])
    return out


__all__ = ["collect", "r17_incidents", "iso"]
