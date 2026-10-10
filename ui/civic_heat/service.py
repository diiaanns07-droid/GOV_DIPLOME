"""HeatService — то, что вызывает сервер (R01) и «Картина дня» (R08).

Источник жалоб подключается снаружи (функции R09). Пока R09 нет, используется демо-набор
demo_seed.py (все записи demo: true). Результаты кэшируются; кэш сбрасывается вызовом
invalidate() (его должен дёргать R09 после create / metoo / set_status) и сам — раз в минуту,
потому что вес жалоб со временем «остывает».
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

from . import engine, geo
from .config import DEFAULT_DAYS, DISTRICT_ZOOM_MAX, MAX_DAYS, PERIODS, load_config
from .targets import TargetResolver

CACHE_TTL_S = 60.0
CACHE_MAX = 64


class HeatError(ValueError):
    """Неверный запрос: field — какой параметр, для ответа 400."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


class HeatService:
    def __init__(self, source=None, *, config=None, resolver: TargetResolver | None = None, clock=None):
        """source: функция (since: datetime) -> список жалоб v2, или объект с методом list(since=...).

        Без source берётся демо-набор (synthetic, demo: true), сдвинутый к текущему времени.
        """
        self.config = config or load_config()
        self.resolver = resolver or TargetResolver()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._source = source
        self._demo_records = None
        self._lock = threading.Lock()
        self._cache: dict = {}
        self._generation = 0
        self.last_compute_ms = 0.0

    # ---------- данные ----------
    def _records(self, since: datetime):
        if self._source is None:
            if self._demo_records is None:
                from . import demo_seed

                self._demo_records = demo_seed.demo_records(now=self._clock())
            return self._demo_records
        if callable(self._source):
            return list(self._source(since))
        if hasattr(self._source, "list"):
            return list(self._source.list(since=since))
        raise TypeError("source должен быть функцией или объектом с методом list()")

    @property
    def is_demo(self) -> bool:
        return self._source is None

    def use_records(self, records) -> None:
        """Подменить демо-данные (например, демо-сервер добавил жалобу)."""
        self._demo_records = list(records)
        self.invalidate()

    def records(self, since=None):
        """Записи жалоб v2 — те же, по которым считается карта (для «Картины дня» R08).
        Патч R08 (research/round-14-results/R08/INTEGRATION.txt §4), применён R01 в сборке B1."""
        return self._records(since)

    @property
    def generation(self) -> int:
        """Растёт при каждом invalidate(): по нему R08 сбрасывает свой кэш."""
        return self._generation

    def invalidate(self) -> None:
        """Сбросить кэш: новая жалоба, «Я тоже» или смена статуса. Вызывать из R09."""
        with self._lock:
            self._generation += 1
            self._cache.clear()

    # ---------- проверка параметров ----------
    def _params(self, *, bbox=None, days=None, category=None, district=None, zoom=None):
        if days in (None, ""):
            days = DEFAULT_DAYS
        try:
            days = int(days)
        except (TypeError, ValueError):
            raise HeatError("days", "days — целое число дней (7, 30 или 90)") from None
        if not 1 <= days <= MAX_DAYS:
            raise HeatError("days", f"days — от 1 до {MAX_DAYS}")
        if category in ("", "all"):
            category = None
        if category is not None and category not in self.config.category_ids:
            raise HeatError("category", "неизвестная категория: " + str(category))
        if district in ("", "all"):
            district = None
        if district is not None and district not in geo.districts():
            raise HeatError("district", "неизвестный район: " + str(district))
        if zoom in (None, ""):
            zoom = None
        else:
            try:
                zoom = float(zoom)
            except (TypeError, ValueError):
                raise HeatError("zoom", "zoom — число") from None
        if bbox in (None, ""):
            bbox = None
        else:
            if isinstance(bbox, str):
                parts = bbox.split(",")
            else:
                parts = list(bbox)
            try:
                bbox = tuple(float(x) for x in parts)
            except (TypeError, ValueError):
                raise HeatError("bbox", "bbox — четыре числа: запад,юг,восток,север") from None
            if len(bbox) != 4 or not (bbox[0] < bbox[2] and bbox[1] < bbox[3]) or not all(engine.is_finite_number(v) for v in bbox):
                raise HeatError("bbox", "bbox — четыре числа: запад,юг,восток,север")
        return bbox, days, category, district, zoom

    # ---------- основное ----------
    def heat(self, *, bbox=None, days=None, category=None, district=None, zoom=None, now: datetime | None = None) -> dict:
        """Ответ GET /api/civic/v2/heat (CONTRACT §7) + легенда и служебные поля."""
        bbox, days, category, district, zoom = self._params(bbox=bbox, days=days, category=category, district=district, zoom=zoom)
        now = now or self._clock()
        mode = "districts" if zoom is not None and zoom < DISTRICT_ZOOM_MAX else "targets"
        # Время в ключе кэша округляем до минуты: вес за минуту почти не меняется.
        key = (self._generation, mode, bbox, days, category, district, int(now.timestamp() // 60))
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
                return hit[1]
        started = time.perf_counter()
        computed = self._compute(now=now, days=days, category=category, district=district,
                                 bbox=None if mode == "districts" else bbox)
        items = computed["items"]
        if mode == "districts":
            items = engine.districts_summary(items, self.config)
            if bbox is not None:
                items = [it for it in items if geo.bbox_intersects(geo.bbox_of(it["geometry"]), bbox)]
        result = {
            "generated_at": engine.iso(now),
            "mode": mode,
            "params": {"bbox": list(bbox) if bbox else None, "days": days, "category": category, "district": district, "zoom": zoom},
            "items": items,
            "legend": self.config.legend(),
            "demo": self.is_demo or (bool(items) and all(it.get("demo") for it in items if "demo" in it)),
            "stats": computed["stats"],
        }
        self.last_compute_ms = round((time.perf_counter() - started) * 1000, 1)
        result["compute_ms"] = self.last_compute_ms
        with self._lock:
            if len(self._cache) >= CACHE_MAX:
                self._cache.clear()
            self._cache[key] = (time.monotonic(), result)
        return result

    def _compute(self, *, now, days, category, district, bbox):
        records = self._records(now - timedelta(days=max(days, self.config.fixed_days + days)))
        return engine.compute(records, now=now, days=days, config=self.config, resolver=self.resolver,
                              category=category, district=district, bbox=bbox)

    # ---------- для «Картины дня» (R08) и карточки ----------
    def top(self, n: int = 10, *, days=None, district=None, category=None, now=None) -> list:
        """Топ горячих мест — те же числа, что на карте (R08 сверяет тестом)."""
        data = self.heat(days=days, district=district, category=category, now=now)
        return [it for it in data["items"] if it["state"] == "active"][:max(0, int(n))]

    def districts(self, *, days=None, category=None, now=None) -> list:
        return self.heat(days=days, category=category, zoom=0, now=now)["items"]

    def target(self, kind: str, target_id: str, *, days=None, now=None) -> dict | None:
        data = self.heat(days=days, now=now)
        for it in data["items"]:
            if it["target"]["id"] == target_id and it["target"]["kind"] == kind:
                return it
        return None

    def meta(self) -> dict:
        """Категории, легенда, районы и периоды — чтобы интерфейс ничего не копировал руками."""
        return {
            "categories_version": self.config.version,
            "categories": [{"id": c["id"], "ru": c["ru"], "kk": c["kk"], "icon": c.get("icon")} for c in self.config.categories],
            "legend": self.config.legend(),
            "periods": list(PERIODS),
            "default_days": DEFAULT_DAYS,
            "district_zoom_max": DISTRICT_ZOOM_MAX,
            "districts": [{"id": d["id"], "ru": d["name_ru"], "kk": d["name_kk"], "bbox": d["bbox"]} for d in geo.districts().values()],
            "demo": self.is_demo,
        }


_default: HeatService | None = None
_default_lock = threading.Lock()


def default_service() -> HeatService:
    """Один общий сервис на процесс (сервер R01 вызывает функции модуля, а не создаёт свой)."""
    global _default
    with _default_lock:
        if _default is None:
            _default = HeatService(source=_feedback_source())
        return _default


def configure(source=None, **kwargs) -> HeatService:
    """R01 подключает источник жалоб R09: configure(source=lambda since: civic_feedback.list(since=since))."""
    global _default
    with _default_lock:
        _default = HeatService(source=source, **kwargs)
        return _default


def invalidate() -> None:
    if _default is not None:
        _default.invalidate()


def _feedback_source():
    """Если у R09 уже есть функция list(bbox, since, category) для записей v2 — берём её, иначе демо."""
    try:
        from ui import civic_feedback  # type: ignore
    except Exception:
        return None
    fn = getattr(civic_feedback, "list_complaints_v2", None) or getattr(civic_feedback, "list_v2", None)
    if callable(fn):
        return lambda since: fn(bbox=None, since=since, category=None)
    return None
