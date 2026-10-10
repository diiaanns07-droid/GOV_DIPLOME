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
    def __init__(self, source=None, *, config=None, resolver: TargetResolver | None = None, clock=None, metoo_times=None,
                 examples_actionable: bool | None = None):
        """source: функция (since: datetime) -> список жалоб v2, или объект с методом list(since=...).
        metoo_times: функция ([complaint_id, …]) -> {id: [ISO, …]} — время каждого «Я тоже» (R09
        ComplaintStore.metoo_times); тогда «Я тоже» остывает от своего момента, а не от момента жалобы.

        Без source берётся демо-набор (synthetic, demo: true), сдвинутый к текущему времени.
        examples_actionable: можно ли менять статус примеров R07 (c-demo-…). По умолчанию — только без source
        (чистое демо); стенд R07 (devserver) включает явно — у него свои маршруты статуса; в оболочке R01 примеров
        нет в хранилище R09, поэтому кнопок у них нет (R10 B-037).
        """
        self.config = config or load_config()
        self.resolver = resolver or TargetResolver()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._source = source
        self._metoo_times = metoo_times
        self._examples_actionable = examples_actionable
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
            recs = list(self._source(since))
        elif hasattr(self._source, "list"):
            recs = list(self._source.list(since=since))
        else:
            raise TypeError("source должен быть функцией или объектом с методом list()")
        return self._with_metoo_times(recs)

    def _with_metoo_times(self, recs: list) -> list:
        """Добавляет к записям с «Я тоже» поле metoo_times (если R09 дал функцию). Записи источника не меняем."""
        if not self._metoo_times:
            return recs
        ids = [r.get("id") for r in recs if isinstance(r, dict) and r.get("id") and int(r.get("metoo") or 0) > 0 and "metoo_times" not in r]
        if not ids:
            return recs
        try:
            times = self._metoo_times(ids) or {}
        except Exception:
            return recs  # без времени «Я тоже» карта всё равно работает (стареет вместе с жалобой)
        return [dict(r, metoo_times=times[r["id"]]) if isinstance(r, dict) and r.get("id") in times else r for r in recs]

    # ---------- для «Картины дня» (R08): те же записи и то же поколение кэша ----------
    def records(self, since=None) -> list:
        """Записи жалоб v2 — ровно те, по которым считается карта (патч R08, INTEGRATION R08 §4)."""
        return self._records(since)

    @property
    def generation(self) -> int:
        """Растёт при каждом invalidate(): по нему R08 сбрасывает свой кэш."""
        return self._generation

    @property
    def is_demo(self) -> bool:
        return self._source is None

    def use_records(self, records) -> None:
        """Подменить демо-данные (например, демо-сервер добавил жалобу)."""
        self._demo_records = list(records)
        self.invalidate()

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
        # Чистое демо (свой стенд, source=None): примеры R07 — сами жалобы, действия с ними работают. С живым источником
        # (оболочка R01: жалобы R09 + примеры R07 при CIVIC_DEMO=1) у примеров R07 кнопок нет — их нет в R09 (B-037).
        examples_ok = self.is_demo if self._examples_actionable is None else self._examples_actionable
        actionable = None if examples_ok else (lambda c: not engine.is_r07_example(c))
        return engine.compute(records, now=now, days=days, config=self.config, resolver=self.resolver,
                              category=category, district=district, bbox=bbox, actionable=actionable)

    # ---------- для «Картины дня» (R08) и карточки ----------
    def top(self, n: int = 10, *, days=None, district=None, category=None, now=None) -> list:
        """Топ горячих мест — те же числа, что на карте (R08 сверяет тестом)."""
        data = self.heat(days=days, district=district, category=category, now=now)
        return [it for it in data["items"] if it["state"] == "active"][:max(0, int(n))]

    def districts(self, *, days=None, category=None, now=None) -> list:
        return self.heat(days=days, category=category, zoom=0, now=now)["items"]

    def target(self, kind: str, target_id: str, *, days=None, now=None, include_real_texts: bool = False,
               with_texts: bool = True) -> dict | None:
        """Одна цель для карточки + «Что пишут жители» (группы текстов).

        include_real_texts=True — только для сотрудника акимата (решает шлюз R01 после проверки входа);
        иначе в группах только тексты демо-записей (synthetic), а люди настоящих жалоб — числом hidden_people.
        """
        data = self.heat(days=days, now=now)
        for it in data["items"]:
            if it["target"]["id"] == target_id and it["target"]["kind"] == kind:
                if not with_texts:
                    return it
                now = now or self._clock()
                days_n = data["params"]["days"]
                texts = engine.text_groups(self._records(now - timedelta(days=days_n)), kind=kind, target_id=target_id,
                                           now=now, days=days_n, include_real=include_real_texts)
                return dict(it, texts=texts)
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
    """R01 подключает источник жалоб R09:
        configure(source=lambda since: store.list(since=since), metoo_times=store.metoo_times)."""
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
