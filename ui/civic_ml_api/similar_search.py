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

import logging
import queue
import threading
from datetime import datetime, timedelta

from ml.civic_dedup import OPEN_STATUSES, get_deduper
from ml.civic_dedup.geo import bbox_around, distance_m, parse_point
from ml.civic_dedup.search import ASTANA_TZ, MAX_TEXT, clamp_days, parse_time, target_id
from ui.civic_ml_api.errors import MLServiceUnavailable

LOGGER = logging.getLogger(__name__)
DEFAULT_LIMIT = 5
BBOX_MARGIN_M = 25.0     # запас к радиусу: округления координат в БД
# R15-S13: чужие жалобы ищутся и меряются от той же огрублённой точки, что R09 показывает всем (3 знака ≈ 100 м).
# С точной точкой distance_m (0,1 м) — и даже граница радиуса (совпадение есть / нет) — из нескольких запросов
# с разных мест выдаёт место жителя до метра (трилатерация). COARSE_MARGIN_M — насколько огрубление сдвигает точку.
PUBLIC_POINT_DIGITS = 3
COARSE_MARGIN_M = 70.0
# Граница Астаны с запасом (как ASTANA_BBOX у R09) — для прогрева кэша всеми открытыми жалобами.
ASTANA_BBOX = (70.9, 50.8, 72.0, 51.5)
WARM_DAYS = 30
WARM_BATCH = 64

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


class _Warmer:
    """Фоновый поток: считает признаки текстов заранее, чтобы первый «Я тоже» в районе был быстрым.

    Для n-грамм это доли миллисекунды на текст, для e5 — миллисекунды: без прогрева первый запрос
    рядом с десятками жалоб ждал бы их эмбеддинги. Ошибки только в журнал — приём жалоб не страдает.
    """

    def __init__(self):
        self.q: queue.Queue = queue.Queue(maxsize=20_000)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.done = 0

    def _ensure(self):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="civic-dedup-warm", daemon=True)
                self._thread.start()

    def put(self, records: list[dict]) -> None:
        items = [(r["id"], r["text"]) for r in records
                 if isinstance(r, dict) and isinstance(r.get("id"), str) and isinstance(r.get("text"), str)]
        for i in range(0, len(items), WARM_BATCH):
            try:
                self.q.put_nowait(items[i:i + WARM_BATCH])
            except queue.Full:
                LOGGER.warning("civic_ml_api: очередь прогрева переполнена, пропуск")
                return
        if items:
            self._ensure()

    def _run(self):
        while True:
            batch = self.q.get()
            try:
                dd = get_deduper()
                dd.cache.get_many(dd.scorer, [(i, t[:MAX_TEXT]) for i, t in batch])
                self.done += len(batch)
            except Exception:  # noqa: BLE001 — прогрев необязателен
                LOGGER.exception("civic_ml_api: прогрев кэша не удался")
            finally:
                self.q.task_done()

    def join(self, timeout: float = 30.0) -> bool:
        """Для тестов и замеров: дождаться очереди. True — всё посчитано."""
        import time
        end = time.monotonic() + timeout
        while self.q.unfinished_tasks and time.monotonic() < end:
            time.sleep(0.01)
        return not self.q.unfinished_tasks


WARMER = _Warmer()


def warm_cache(days: int = WARM_DAYS) -> int:
    """Поставить в фоновый прогрев все открытые жалобы города за days дней. -> сколько записей."""
    src = _source.get("src")
    if src is None:
        return 0
    since = src.now() - timedelta(days=clamp_days(days))
    records = src.fetch(since=since, bbox=ASTANA_BBOX, target=None)
    WARMER.put(records)
    return len(records)


def connect_store(store, *, warm: bool = True) -> None:
    """R01 вызывает один раз при старте: similar() начинает искать в хранилище жалоб R09.

    warm=True: открытые жалобы за 30 дней сразу считаются в фоне, а каждая новая жалоба —
    по событию created хранилища R09 (store.subscribe), чтобы «Я тоже» отвечал быстро и после старта.
    """
    src = StoreSource(store)
    with _lock:
        old = _source.pop("unsubscribe", None)
        if callable(old):
            old()
        _source["src"] = src
        subscribe = getattr(src.store, "subscribe", None)
        if warm and callable(subscribe):
            _source["unsubscribe"] = subscribe(lambda event: _on_store_event(src, event))
    if warm:
        try:
            warm_cache()
        except Exception:  # noqa: BLE001 — прогрев необязателен, поиск работает и без него
            LOGGER.exception("civic_ml_api: прогрев при подключении не удался")


def _on_store_event(src: StoreSource, event: dict) -> None:
    """Событие R09 приходит синхронно после COMMIT — здесь только постановка в очередь."""
    if not isinstance(event, dict) or event.get("type") != "created":
        return
    rec = src.store.get(event.get("complaint_id"))
    if rec:
        WARMER.put([rec])


def set_complaint_source(fn_or_source, clock=None) -> None:
    """Подключить свой источник: функцию fn(since, bbox, target_id) или объект с fetch()/now(). None — отключить."""
    with _lock:
        old = _source.pop("unsubscribe", None)
        if callable(old):
            old()
        if fn_or_source is None:
            _source.pop("src", None)
        elif hasattr(fn_or_source, "fetch") and hasattr(fn_or_source, "now"):
            _source["src"] = fn_or_source
        else:
            _source["src"] = FunctionSource(fn_or_source, clock)


def source_kind() -> str | None:
    src = _source.get("src")
    return getattr(src, "kind", "custom") if src is not None else None


def _coarse(rec):
    """Копия записи с точкой, огрублённой как в публичной выдаче R09 (R15-S13)."""
    p = rec.get("point") if isinstance(rec, dict) else None
    if isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p):
        return dict(rec, point=[round(float(p[0]), PUBLIC_POINT_DIGITS), round(float(p[1]), PUBLIC_POINT_DIGITS)])
    return rec


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
    bbox = bbox_around(here, dd.radius_m + BBOX_MARGIN_M + COARSE_MARGIN_M) if here is not None else None
    records = [_coarse(rec) for rec in src.fetch(since=since, bbox=bbox, target=tid)]
    matches = dd.find(text, records, point=here, target=tid, days=days, now=now, limit=limit)
    reply["matches"] = [m.as_dict() for m in matches]
    reply["people_total"] = sum(m["people"] for m in reply["matches"])
    return reply


__all__ = ["StoreSource", "FunctionSource", "WARMER", "connect_store", "distance_m", "records_source",
           "set_complaint_source", "similar", "source_kind", "warm_cache"]
