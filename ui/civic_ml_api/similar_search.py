"""similar(text, point, days) — похожие открытые обращения рядом (CONTRACT §7: POST /api/civic/v2/similar).

Откуда берутся обращения: источник подключает R01 при старте сервера (INTEGRATION.txt):
    connect_store(store)          — хранилище R09 (ui.civic_feedback.v2.ComplaintStore или его сервис);
    set_complaint_source(fn)      — любая функция fn(since, bbox, target_id) -> [запись CONTRACT §5].
Пока источник не подключён, similar отвечает 503 source_not_connected — форма R09 тогда работает
без подсказки «Я тоже» (так задумано у R09), а не показывает ложное «никто не сообщал».

Хранилище запрашивается узко: прямоугольник вокруг точки (радиус + запас) и записи той же цели,
только открытые и за последние N дней. Сравнение текстов — ml/civic_dedup (e5 или n-граммы).
Ответ не содержит текстов чужих жалоб (правило R09: жителю — только «сообщили N человек»).
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta

from ml.civic_dedup import OPEN_STATUSES, get_deduper
from ml.civic_dedup.geo import bbox_around, distance_m, parse_point
from ml.civic_dedup.search import ASTANA_TZ, clamp_days, parse_time, target_id
from ui.civic_ml_api.errors import MLServiceUnavailable

MAX_TEXT = 2000          # длиннее не сравниваем: смысл жалобы в начале, а n-граммы растут с длиной
DEFAULT_LIMIT = 5
BBOX_MARGIN_M = 25.0     # запас к радиусу: округления координат в БД

_lock = threading.Lock()
_source: dict = {}


class StoreSource:
    """Адаптер ComplaintStore R09: list(bbox, since, category, *, status, target_id, …)."""

    kind = "complaints_v2"

    def __init__(self, store):
        self.store = getattr(store, "store", store)  # ComplaintsV2Service -> его ComplaintStore
        if not callable(getattr(self.store, "list", None)):
            raise TypeError("connect_store: нужен ComplaintStore R09 (метод list)")

    def now(self) -> datetime:
        clock = getattr(self.store, "clock", None)
        moment = clock() if callable(clock) else datetime.now(ASTANA_TZ)
        return moment if moment.tzinfo else moment.replace(tzinfo=ASTANA_TZ)

    def fetch(self, *, since: datetime, bbox, target: str | None) -> list[dict]:
        out = []
        if bbox is not None:
            out += self.store.list(bbox=bbox, since=since, status=list(OPEN_STATUSES))
        if target is not None:
            out += self.store.list(since=since, status=list(OPEN_STATUSES), target_id=target)
        return out


class FunctionSource:
    """Любая функция fn(since=datetime, bbox=(lon_min, lat_min, lon_max, lat_max)|None, target_id=str|None)."""

    kind = "function"

    def __init__(self, fn, clock=None):
        if not callable(fn):
            raise TypeError("set_complaint_source: нужна функция")
        self.fn = fn
        self.clock = clock

    def now(self) -> datetime:
        moment = self.clock() if callable(self.clock) else datetime.now(ASTANA_TZ)
        return moment if moment.tzinfo else moment.replace(tzinfo=ASTANA_TZ)

    def fetch(self, *, since: datetime, bbox, target: str | None) -> list[dict]:
        return list(self.fn(since=since, bbox=bbox, target_id=target) or [])


def records_source(records, clock=None) -> FunctionSource:
    """Источник из списка записей в памяти (тесты, замер скорости, стенд без БД). Фильтрует сам."""
    items = list(records)

    def fn(*, since, bbox, target_id):
        out = []
        for rec in items:
            created = parse_time(rec.get("created_at"))
            if created is None or created < since:
                continue
            pt = parse_point(rec.get("point")) if rec.get("point") is not None else None
            in_box = bbox is not None and pt is not None and bbox[0] <= pt[0] <= bbox[2] and bbox[1] <= pt[1] <= bbox[3]
            same = target_id is not None and _target_id_of(rec) == target_id
            if in_box or same:
                out.append(rec)
        return out

    return FunctionSource(fn, clock)


def _target_id_of(rec: dict) -> str | None:
    return target_id(rec.get("target"))


def connect_store(store) -> None:
    """R01 вызывает один раз при старте: similar() начинает искать в хранилище жалоб R09."""
    src = StoreSource(store)
    with _lock:
        _source["src"] = src


def set_complaint_source(fn_or_source, clock=None) -> None:
    """Подключить свой источник: функцию fn(since, bbox, target_id) или объект с fetch()/now(). None — отключить."""
    with _lock:
        if fn_or_source is None:
            _source.pop("src", None)
        elif hasattr(fn_or_source, "fetch") and hasattr(fn_or_source, "now"):
            _source["src"] = fn_or_source
        else:
            _source["src"] = FunctionSource(fn_or_source, clock)


def source_kind() -> str | None:
    src = _source.get("src")
    return getattr(src, "kind", "custom") if src is not None else None


def similar(text, point=None, days=None, target=None, limit=DEFAULT_LIMIT) -> dict:
    """Похожие открытые обращения рядом с точкой / на той же цели за последние days дней (по умолчанию 14).

    target — необязательно ({"kind", "id"} или id): шлюз R01 пока передаёт только text, point, days
    (строка для R01 — в INTEGRATION.txt). Все matches уже прошли порог — повторно не фильтровать.
    """
    if not isinstance(text, str):
        raise ValueError("text: нужна строка с текстом обращения.")
    text = text.strip()[:MAX_TEXT]
    days = clamp_days(days)
    here = None
    if point is not None:
        here = parse_point(point)
        if here is None:
            raise ValueError("point: нужна точка [долгота, широта].")
    tid = target_id(target)
    if target is not None and tid is None:
        raise ValueError("target: нужен объект {kind, id} или id цели.")
    try:
        limit = max(1, min(20, int(limit)))
    except (TypeError, ValueError):
        raise ValueError("limit: число от 1 до 20.") from None

    dd = get_deduper()
    reply = {"matches": [], "people_total": 0, "method": dd.scorer.method, "model_version": dd.version,
             "threshold": dd.threshold, "days": days, "radius_m": dd.radius_m}
    src = _source.get("src")
    if src is None:
        raise MLServiceUnavailable("source_not_connected",
                                   "Поиск похожих обращений пока не подключён к хранилищу жалоб.")
    if here is None and tid is None:
        reply["note"] = "no_location"  # без места дубль не ищем (ml/civic_dedup/search.py)
        return reply
    now = src.now()
    since = now - timedelta(days=days)
    bbox = bbox_around(here, dd.radius_m + BBOX_MARGIN_M) if here is not None else None
    records = src.fetch(since=since, bbox=bbox, target=tid)
    matches = dd.find(text, records, point=here, target=tid, days=days, now=now, limit=limit)
    reply["matches"] = [m.as_dict() for m in matches]
    reply["people_total"] = sum(m["people"] for m in reply["matches"])
    return reply


__all__ = ["StoreSource", "FunctionSource", "connect_store", "distance_m", "records_source",
           "set_complaint_source", "similar", "source_kind"]
