"""«Картина дня» для акима: все числа одной функцией summary(date, district).

ОПРЕДЕЛЕНИЯ (одним местом, чтобы следующий разработчик не искал по коду):
- Время — Астана, UTC+5. День D = [D 00:00, D+1 00:00). Если D — сегодня, считаем до текущего
  момента (as_of = сейчас); если D в прошлом — на конец дня (as_of = D 23:59:59).
- Обращение = запись жалобы v2 без duplicate_of (дубль уже влит в оригинал как «Я тоже»).
- «Новые за день» — поданы с начала дня D до as_of. Сравниваем с тем же отрезком ровно неделю назад:
  в 10:00 — с прошлой неделей до 10:00, а не с целым днём, иначе утром всегда было бы «меньше».
- «Новые за 7 дней» — (as_of − 7 дн., as_of]; сравнение — с 7 днями перед ними.
- «В работе» — статус на момент as_of «принято» или «в работе». «Ждут ответа» — статус «новое».
- «Просрочено» — на момент as_of не исправлено (новое / принято / в работе), а с подачи прошло
  больше срока категории (deadlines.py, демо-норматив).
- «Исправлено за неделю» — получили статус «исправлено» за (as_of − 7 дн., as_of] и не открыты снова.
  Статус «на момент» восстанавливается по status_history, поэтому прошлые даты и «неделю назад» честные.
- «Горячие места», «Темы», «Районы» и главная проблема — РОВНО тепловая карта R07 за 7 дней:
  сколько человек (жалоба + «Я тоже») сообщили о нерешённом. Сегодняшние числа берутся вызовом
  HeatService.heat (тот же, что отвечает карте), неделю назад — тем же расчётом R07 (engine.compute)
  по состоянию записей на тот момент. Тест tests/civic/R08/test_r08_heat_match.py сверяет это.
- Изменение: при базе < 10 показываем разницу в штуках («на 3 больше»), от 10 — в процентах,
  при росте вдвое и больше — «в 2,5 раза». Проценты на маленькой базе вводят в заблуждение (1 → 3 = «+200 %»).
"""
from __future__ import annotations

import json
import math
import threading
import time
from datetime import date as Date, datetime, timedelta, timezone

from . import deadlines, sources, text

ASTANA_TZ = timezone(timedelta(hours=5))
WEEK = timedelta(days=7)
HEAT_DAYS = 7           # период тепловой карты для «Картины дня»: последняя неделя
TOP_N = 10              # «Горячие места» — первые 10 целей карты
OPEN = ("new", "accepted", "in_progress")
WORK = ("accepted", "in_progress")
PCT_MIN_BASE = 10       # с какой базы показывать изменение в процентах
CACHE_TTL_S = 30.0

_AUTO = object()        # «подключить соседа автоматически»


class AkimError(ValueError):
    """Неверный запрос; field — какой параметр (для ответа 400)."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


# ---------------------------------------------------------------- время и статусы

def parse_time(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=ASTANA_TZ)
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=ASTANA_TZ)


def iso(dt: datetime) -> str:
    return dt.astimezone(ASTANA_TZ).isoformat(timespec="seconds")


def astana_today(now: datetime) -> Date:
    return now.astimezone(ASTANA_TZ).date()


def _history(record: dict) -> list[tuple[datetime, str]]:
    out = []
    for h in record.get("status_history") or []:
        if isinstance(h, dict):
            t = parse_time(h.get("at"))
            if t is not None and h.get("status"):
                out.append((t, str(h["status"])))
    out.sort(key=lambda x: x[0])
    return out


def status_at(record: dict, moment: datetime) -> str | None:
    """Статус обращения на момент moment; None — его ещё не было.

    Если в истории нет записей позже moment, верим текущему полю status (у старых записей
    история бывает неполной). Иначе — последний статус из истории не позже moment.
    """
    created = parse_time(record.get("created_at"))
    if created is None or created > moment:
        return None
    hist = _history(record)
    if not any(t > moment for t, _ in hist):
        return record.get("status") or (hist[-1][1] if hist else "new")
    current = "new"
    for t, s in hist:
        if t <= moment:
            current = s
    return current


def fixed_moment(record: dict, moment: datetime) -> datetime | None:
    """Когда обращение (последний раз до moment) стало «исправлено»; None — не исправлено на moment."""
    if status_at(record, moment) != "fixed":
        return None
    last = None
    for t, s in _history(record):
        if s == "fixed" and t <= moment:
            last = t
    if last is None:  # статус fixed без истории — как у R07: время обновления или подачи
        last = parse_time(record.get("updated_at")) or parse_time(record.get("created_at"))
    return last


def snapshot(record: dict, moment: datetime) -> dict | None:
    """Запись такой, какой она была в момент moment (для расчёта карты «неделю назад»).

    Ограничение: у записи v2 нет времени каждого «Я тоже», поэтому metoo берётся текущим.
    """
    st = status_at(record, moment)
    if st is None:
        return None
    copy = dict(record)
    copy["status"] = st
    copy["status_history"] = [h for h in record.get("status_history") or []
                              if isinstance(h, dict) and (parse_time(h.get("at")) or moment) <= moment]
    return copy


# ---------------------------------------------------------------- изменение к прошлому периоду

def change(value: int, prev: int) -> dict:
    """{trend: up|down|flat, mode: abs|pct|ratio|new, abs, pct, ratio, prev}. Подписи — в text.py и в интерфейсе."""
    value, prev = int(value), int(prev)
    diff = value - prev
    out = {"value": value, "prev": prev, "abs": abs(diff), "pct": None, "ratio": None,
           "trend": "up" if diff > 0 else "down" if diff < 0 else "flat", "mode": "abs"}
    if diff == 0:
        return out
    if prev == 0:
        out["mode"] = "new"          # неделю назад не было ни одного
        return out
    pct = abs(diff) * 100.0 / prev
    if prev >= PCT_MIN_BASE and value > 0 and round(pct) >= 1:
        out["pct"] = int(round(pct))
        out["mode"] = "pct"
        if value >= 2 * prev:
            out["ratio"] = math.floor(value * 10.0 / prev + 0.5) / 10.0
            out["mode"] = "ratio"
    return out


# ---------------------------------------------------------------- районы

def _district_table() -> dict:
    """id → {ru, kk}. Список — реальные районы из geofence.json (тот же, что у R07), подписи — из i18n R11."""
    geofence = json.loads((deadlines.ROOT / "data" / "civic" / "astana" / "geofence.json").read_text("utf-8"))
    out: dict = {}
    for p in geofence.get("polygons", []):
        d_id = p.get("district_id")
        if d_id and d_id not in out:
            out[d_id] = {"id": d_id, "ru": text.district_name(d_id, "ru") or p.get("name") or d_id,
                         "kk": text.district_name(d_id, "kk") or p.get("name") or d_id}
    return out


_DISTRICTS: dict | None = None


def districts() -> dict:
    global _DISTRICTS
    if _DISTRICTS is None:
        _DISTRICTS = _district_table()
    return _DISTRICTS


# ---------------------------------------------------------------- сервис

class AkimService:
    def __init__(self, *, heat=_AUTO, records=_AUTO, objects=_AUTO, proposals=_AUTO, clock=None):
        """heat — HeatService R07 (False — без карты); records — функция since → записи v2;
        objects / proposals — функции (district, today) → список (CONTRACT §7, R06).
        По умолчанию всё подключается само (sources.py)."""
        self.heat = sources.heat_service() if heat is _AUTO else (heat or None)
        self.engine = sources.heat_engine() if self.heat is not None else None
        self.source_names = {}
        if records is _AUTO:
            records = sources.records_from_heat(self.heat)
            self.source_names["complaints"] = ("r07-demo" if getattr(self.heat, "is_demo", False) else "r07") if records else "none"
        else:
            self.source_names["complaints"] = "custom"
        self._records = records
        if objects is _AUTO:
            objects, self.source_names["objects"] = sources.default_objects()
        else:
            self.source_names["objects"] = "custom" if objects else "none"
        if proposals is _AUTO:
            proposals, self.source_names["proposals"] = sources.default_proposals()
        else:
            self.source_names["proposals"] = "custom" if proposals else "none"
        self._objects, self._proposals = objects, proposals
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.source_names["heat"] = "r07" if self.heat is not None else "none"
        self._lock = threading.Lock()
        self._cache: dict = {}
        deadlines.validate()

    def invalidate(self) -> None:
        with self._lock:
            self._cache.clear()

    # ---------- параметры ----------
    def _params(self, day, district, now: datetime):
        today = astana_today(now)
        if day in (None, "", "today"):
            day = today
        elif isinstance(day, str):
            try:
                day = Date.fromisoformat(day.strip())
            except ValueError:
                raise AkimError("date", "date — дата вида 2026-10-12") from None
        elif isinstance(day, datetime):
            day = astana_today(day)
        if not isinstance(day, Date):
            raise AkimError("date", "date — дата вида 2026-10-12")
        if day > today:
            raise AkimError("date", "картина дня ещё не наступила: выберите сегодня или прошлый день")
        if district in (None, "", "all"):
            district = None
        elif district not in districts():
            raise AkimError("district", "неизвестный район: " + str(district))
        return day, district

    # ---------- главное ----------
    def summary(self, date=None, district=None, now: datetime | None = None) -> dict:
        now = now or self._clock()
        day, district = self._params(date, district, now)
        # Поколение кэша карты R07 в ключе: R09 сбрасывает кэш карты после новой жалобы — сбросится и наш.
        key = (day.isoformat(), district, int(now.timestamp() // 60), getattr(self.heat, "_generation", 0))
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
                return hit[1]
        result = self._build(day, district, now)
        with self._lock:
            if len(self._cache) > 32:
                self._cache.clear()
            self._cache[key] = (time.monotonic(), result)
        return result

    def _build(self, day: Date, district: str | None, now: datetime) -> dict:
        started = time.perf_counter()
        is_today = day == astana_today(now)
        day_start = datetime(day.year, day.month, day.day, tzinfo=ASTANA_TZ)
        as_of = now.astimezone(ASTANA_TZ) if is_today else day_start + timedelta(days=1) - timedelta(seconds=1)
        week_ago = as_of - WEEK

        all_records, skipped = self._load_records()
        recs = [r for r in all_records if not r.get("duplicate_of")]
        scoped = [r for r in recs if district is None or self._district_of(r) == district]

        kpi = self._kpi(scoped, day_start, as_of)
        # Карте отдаём ровно те записи, что получает R07 (с дублями — как у него), чтобы «неделю назад» считалось так же.
        heat_part = self._heat_part(all_records, district, as_of, is_today)
        objects = self._objects_part(district, as_of)
        proposals = self._proposals_part(district, as_of)

        d_info = districts().get(district) if district else None
        result = {
            "generated_at": iso(now),
            "date": day.isoformat(),
            "is_today": is_today,
            "as_of": iso(as_of),
            "compare_to": iso(week_ago),
            "district": d_info,
            "kpi": kpi,
            **heat_part,
            "objects": objects,
            "proposals": proposals,
            "deadlines": dict(deadlines.DEADLINE_DAYS),
            "heat_days": HEAT_DAYS,
            "empty": kpi["new_day"]["value"] == 0,
            "sources": dict(self.source_names),
            "demo": {
                "complaints": any(r.get("demo") for r in scoped) or self.source_names["complaints"] == "r07-demo",
                "objects": objects.get("demo", False),
                "proposals": proposals.get("demo", False),
            },
            "stats": {"records": len(all_records), "skipped_invalid": skipped,
                      "duplicates": len(all_records) - len(recs), "in_scope": len(scoped)},
        }
        result["demo"]["any"] = any(result["demo"].values())
        result["text"] = {"ru": text.render(result, "ru"), "kk": text.render(result, "kk")}
        result["text_parts"] = {"ru": text.render_parts(result, "ru"), "kk": text.render_parts(result, "kk")}
        result["compute_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return result

    # ---------- жалобы ----------
    def _load_records(self) -> tuple[list[dict], int]:
        if self._records is None:
            return [], 0
        raw = self._records(None)  # все записи: старые незакрытые тоже бывают просрочены
        good, skipped = [], 0
        for r in raw or []:
            if isinstance(r, dict) and parse_time(r.get("created_at")) is not None:
                good.append(r)
            else:
                skipped += 1
        return good, skipped

    def _district_of(self, record: dict) -> str | None:
        if self.engine is not None:
            return self.engine.complaint_district(record)  # то же правило, что у карты
        return record.get("district")

    def _kpi(self, recs: list[dict], day_start: datetime, as_of: datetime) -> dict:
        def created_between(a: datetime, b: datetime, include_start: bool) -> int:
            n = 0
            for r in recs:
                c = parse_time(r["created_at"])
                if (a <= c if include_start else a < c) and c <= b:
                    n += 1
            return n

        def at(moment: datetime) -> dict:
            work = waiting = overdue = fixed = 0
            for r in recs:
                st = status_at(r, moment)
                if st is None:
                    continue
                if st in WORK:
                    work += 1
                elif st == "new":
                    waiting += 1
                if st in OPEN:
                    age = moment - parse_time(r["created_at"])
                    if age > timedelta(days=deadlines.deadline_days(r.get("category"))):
                        overdue += 1
                f = fixed_moment(r, moment)
                if f is not None and moment - WEEK < f <= moment:
                    fixed += 1
            return {"work": work, "waiting": waiting, "overdue": overdue, "fixed": fixed}

        now_state, prev_state = at(as_of), at(as_of - WEEK)
        new_day = created_between(day_start, as_of, True)
        new_day_prev = created_between(day_start - WEEK, as_of - WEEK, True)
        new_week = created_between(as_of - WEEK, as_of, False)
        new_week_prev = created_between(as_of - 2 * WEEK, as_of - WEEK, False)
        return {
            "new_day": change(new_day, new_day_prev),
            "new_week": change(new_week, new_week_prev),
            "in_progress": {**change(now_state["work"], prev_state["work"]), "waiting": now_state["waiting"]},
            "overdue": change(now_state["overdue"], prev_state["overdue"]),
            "fixed_week": change(now_state["fixed"], prev_state["fixed"]),
        }

    # ---------- тепловая карта ----------
    def _items_now(self, as_of, is_today, past, *, category=None, district=None) -> list:
        """Цели карты за HEAT_DAYS. Сегодня — сам HeatService (ровно ответ /heat), иначе расчёт R07 по снимку."""
        if is_today:
            return self.heat.heat(days=HEAT_DAYS, category=category, district=district, now=as_of)["items"]
        return self._items_past(past, as_of, category=category, district=district)

    def _items_past(self, snap: list, moment, *, category=None, district=None) -> list:
        return self.engine.compute(snap, now=moment, days=HEAT_DAYS, config=self.heat.config,
                                   resolver=self.heat.resolver, category=category, district=district)["items"]

    @staticmethod
    def _active(items: list) -> list:
        return [it for it in items if it.get("state") == "active"]

    @staticmethod
    def _by_district(items: list) -> dict:
        """Сумма по районам — как engine.districts_summary R07 (только активные цели с районом)."""
        acc: dict = {}
        for it in items:
            if it.get("state") == "active" and it.get("district") in districts():
                acc[it["district"]] = acc.get(it["district"], 0) + int(it.get("count") or 0)
        return acc

    def _heat_part(self, recs: list[dict], district: str | None, as_of: datetime, is_today: bool) -> dict:
        unavailable = {"available": False, "reason": "heat_unavailable"}
        if self.heat is None or self.engine is None:
            return {"hot": unavailable, "topics": unavailable, "districts": unavailable, "main_problem": None}

        moment_prev = as_of - WEEK
        snap_prev = [s for s in (snapshot(r, moment_prev) for r in recs) if s]
        snap_now = None if is_today else [s for s in (snapshot(r, as_of) for r in recs) if s]

        # Горячие места: первые TOP_N активных целей — то же, что HeatService.top().
        items = self._items_now(as_of, is_today, snap_now, district=district)
        hot = []
        for rank, it in enumerate(self._active(items)[:TOP_N], start=1):
            by_cat = it.get("by_category") or {}
            hot.append({
                "rank": rank,
                "target": {k: it["target"].get(k) for k in ("kind", "id", "label_ru", "label_kk")},
                "count": it["count"], "level": it["level"], "color": it.get("color"), "weight": it["weight"],
                "status": it.get("status"), "district": it.get("district"),
                "category": next(iter(by_cat), None), "approximate": bool(it.get("approximate")),
                "anchor": it.get("anchor"), "last_at": it.get("last_at"), "demo": bool(it.get("demo")),
            })

        # Темы: для каждой категории — карта с фильтром этой категории (ровно что увидит аким на карте).
        cats = deadlines.load_categories()["categories"]
        topics, pairs = [], []
        for c in cats:
            cur_items = self._items_now(as_of, is_today, snap_now, category=c["id"], district=district)
            prev_items = self._items_past(snap_prev, moment_prev, category=c["id"], district=district)
            cur = sum(it["count"] for it in self._active(cur_items))
            prev = sum(it["count"] for it in self._active(prev_items))
            if cur or prev:
                topics.append({"category": c["id"], "ru": c["ru"], "kk": c["kk"], "icon": c.get("icon"),
                               **change(cur, prev)})
            if district is not None:
                pairs.append((c, district, cur, prev))
            else:
                cur_d, prev_d = self._by_district(cur_items), self._by_district(prev_items)
                for d_id in set(cur_d) | set(prev_d):
                    pairs.append((c, d_id, cur_d.get(d_id, 0), prev_d.get(d_id, 0)))
        order = {c["id"]: i for i, c in enumerate(cats)}
        topics.sort(key=lambda t: (-t["value"], order[t["category"]]))

        # Районы — всегда по всему городу (сравнение районов), выбранный район подсвечивает интерфейс.
        if is_today:
            d_now = {it["district"]: it["count"] for it in
                     self.heat.heat(days=HEAT_DAYS, zoom=0, now=as_of)["items"] if it.get("state") == "active"}
        else:
            d_now = self._by_district(self._items_past(snap_now, as_of))
        d_prev = self._by_district(self._items_past(snap_prev, moment_prev))
        dist_rows = []
        for d_id, info in districts().items():
            row = {"district": d_id, "ru": info["ru"], "kk": info["kk"], **change(d_now.get(d_id, 0), d_prev.get(d_id, 0))}
            dist_rows.append(row)
        dist_rows.sort(key=lambda r: (-r["value"], r["ru"]))

        main = None
        live = [p for p in pairs if p[2] > 0]
        if live:
            c, d_id, cur, prev = max(live, key=lambda p: (p[2], p[2] - p[3], -order[p[0]["id"]]))
            info = districts().get(d_id, {})
            main = {"category": c["id"], "category_ru": c["ru"], "category_kk": c["kk"],
                    "district": d_id, "district_ru": info.get("ru"), "district_kk": info.get("kk"),
                    **change(cur, prev)}

        return {
            "hot": {"available": True, "days": HEAT_DAYS, "items": hot},
            "topics": {"available": True, "days": HEAT_DAYS, "items": topics,
                       "total": sum(t["value"] for t in topics)},
            "districts": {"available": True, "days": HEAT_DAYS, "items": dist_rows, "selected": district},
            "main_problem": main,
        }

    # ---------- объекты и предложения (R06) ----------
    def _objects_part(self, district, as_of: datetime) -> dict:
        if self._objects is None:
            return {"available": False, "late": [], "stale": [], "late_count": 0, "stale_count": 0, "total": 0}
        try:
            raw = self._objects(district, as_of.date())
        except Exception:  # R06 не должен ронять всю картину дня
            return {"available": False, "reason": "objects_failed", "late": [], "stale": [],
                    "late_count": 0, "stale_count": 0, "total": 0}
        objs = [sources.normalize_object(o, as_of) for o in raw or [] if isinstance(o, dict)]
        objs = [o for o in objs if district is None or o["district"] == district]
        objs = [o for o in objs if o["stage"] != "operating"]  # работающие — уже не стройка
        late = sorted((o for o in objs if o["delay_days"] > 0), key=lambda o: (-o["delay_days"], o["title_ru"]))
        stale = sorted((o for o in objs if o["stale"]), key=lambda o: -(o["days_since_update"] or 0))
        return {"available": True, "late": late, "stale": stale, "late_count": len(late),
                "stale_count": len(stale), "total": len(objs), "stale_after_days": sources.STALE_DAYS,
                "demo": any(o["demo"] for o in objs)}

    def _proposals_part(self, district, as_of: datetime) -> dict:
        empty = {"available": False, "new_count": 0, "open_count": 0, "votes_up": 0, "votes_down": 0, "top": []}
        if self._proposals is None:
            return empty
        try:
            raw = self._proposals(district, as_of.date())
        except Exception:
            return {**empty, "reason": "proposals_failed"}
        props = [p for p in raw or [] if isinstance(p, dict) and (district is None or p.get("district") == district)]
        open_props = [p for p in props if p.get("status", "proposal") == "proposal"
                      and (parse_time(p.get("created_at")) or as_of) <= as_of]
        new = [p for p in open_props if (t := parse_time(p.get("created_at"))) and as_of - WEEK < t <= as_of]
        top = sorted(open_props, key=lambda p: (-int(p.get("votes_up") or 0), str(p.get("id"))))[:3]
        return {
            "available": True,
            "new_count": len(new),
            "open_count": len(open_props),
            "votes_up": sum(int(p.get("votes_up") or 0) for p in open_props),
            "votes_down": sum(int(p.get("votes_down") or 0) for p in open_props),
            "top": [{"id": p.get("id"), "kind": p.get("kind"),
                     "title_ru": p.get("title_ru") or p.get("title") or p.get("id"),
                     "title_kk": p.get("title_kk") or p.get("title_ru") or p.get("title") or p.get("id"),
                     "votes_up": int(p.get("votes_up") or 0), "votes_down": int(p.get("votes_down") or 0),
                     "is_new": p in new, "demo": bool(p.get("demo"))} for p in top],
            "demo": any(p.get("demo") for p in props),
        }


# ---------------------------------------------------------------- общий сервис процесса

_default: AkimService | None = None
_default_lock = threading.Lock()


def default_service() -> AkimService:
    global _default
    with _default_lock:
        if _default is None:
            _default = AkimService()
        return _default


def configure(**kwargs) -> AkimService:
    """R01: configure(heat=civic_heat.default_service()) или свои records/objects/proposals."""
    global _default
    with _default_lock:
        _default = AkimService(**kwargs)
        return _default


def summary(date=None, district=None, now: datetime | None = None) -> dict:
    """Функция для соседей и сервера: картина дня на дату (по умолчанию сегодня) и район (None — весь город)."""
    return default_service().summary(date=date, district=district, now=now)
