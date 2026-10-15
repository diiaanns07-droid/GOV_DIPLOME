"""«Хроника города» (R07, раунд 15): тепловая карта по дням за 7 / 30 дней — та же формула, что GET /heat.

Как считается кадр дня D (CONTRACT §6: «никакой отдельной математики»):
  1. каждая жалоба «отматывается» к концу дня D (as_of): её ещё не было — пропускаем; статус — последний шаг
     истории не позже D; «Я тоже» — только нажатые до D; ответы жителей и раунд проверки ремонта — какими были в D;
  2. на этих записях вызывается тот же расчёт, что у /heat (HeatService._compute → engine.compute: вес
     0.5 ** (возраст / 14), уровни heat_levels, «исправлено» 7 дней), с now = конец дня D (для сегодня — сейчас).
Поэтому последний кадр хроники = /heat прямо сейчас (тест tests/civic/R07/test_r07_replay.py).

Чего «отмотать» точно нельзя (в записи нет времени): пометку дубля (дубль — дублем всегда) и голоса «не могу
проверить» (остаются как есть); у прошлых раундов ремонта, если жалобу чинили дважды, нет голосов (видно только
«служба сообщила»). На цвет и число на значке «сегодня» это не влияет.

Ответ компактный: формы целей — один раз в `targets`; в первом кадре все цели, дальше — только изменившиеся
(`changed`) и пропавшие (`removed`). Прошлые дни кэшируются (до invalidate), «сегодня» пересчитывается раз в минуту.
"""
from __future__ import annotations

import gc
import threading
import time
from datetime import date, datetime, time as dtime, timedelta

from . import engine, geo, marks as marks_mod
from .config import DISTRICT_ZOOM_MAX
from .engine import ASTANA_TZ, iso, parse_time

MAX_SPAN_DAYS = 92          # самая длинная хроника — квартал (кадров не больше 92)
MAX_BACK_DAYS = 366         # раньше года назад хроника не смотрит
STEPS = ("day",)
CACHE_DAYS_MAX = 400        # кадров прошлых дней в памяти (на все фильтры вместе)
CACHE_REPLIES_MAX = 16      # готовых ответов
REPLY_TTL_S = 60.0


class ReplayError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


# ---------------------------------------------------------------- «отмотать» жалобу к моменту t

def _after(value, t: datetime) -> bool:
    at = parse_time(value)
    return at is not None and at > t


def as_of(c: dict, t: datetime) -> dict | None:
    """Запись жалобы такой, какой она была в момент t. Жалобы ещё не было — None. Исходная запись не меняется."""
    created = parse_time(c.get("created_at"))
    if created is None or created > t:
        return None
    out = dict(c)
    hist = c.get("status_history")
    if isinstance(hist, list) and hist:
        kept = [h for h in hist if not (isinstance(h, dict) and _after(h.get("at"), t))]
        if len(kept) != len(hist):
            out["status_history"] = kept
            last = next((h for h in reversed(kept) if isinstance(h, dict) and h.get("status")), None)
            out["status"] = last["status"] if last else "new"
    elif _after(c.get("updated_at"), t):
        out["status"] = "new"          # истории нет: статус сменился в updated_at, а в момент t жалоба была новой

    times = c.get("metoo_times")
    if isinstance(times, list) and times:
        timed = [x for x in times if parse_time(x) is not None]
        kept_t = [x for x in timed if not _after(x, t)]
        if len(kept_t) != len(timed):
            untimed = max(0, int(c.get("metoo") or 0) - len(timed))   # «Я тоже» без времени стареют с жалобой
            out["metoo_times"] = kept_t
            out["metoo"] = len(kept_t) + untimed

    fallback = c.get("verified_at") or c.get("checked_at") or c.get("updated_at")
    for key in ("resident_checks", "checks"):
        val = c.get(key)
        if isinstance(val, list):
            out[key] = [x for x in val if not _after(x.get("at") if isinstance(x, dict) and x.get("at") else fallback, t)]
    for key in ("resident_check", "verification"):
        val = c.get(key)
        at = (val.get("at") or fallback) if isinstance(val, dict) else fallback
        if val is not None and _after(at, t):
            out.pop(key, None)
    for key in ("verified", "verified_by_residents", "resident_confirmed"):
        if c.get(key) is True and _after(fallback, t):
            out[key] = False

    res = c.get("resolution")
    if isinstance(res, dict):
        if parse_time(res.get("reported_at")) is None or _after(res.get("reported_at"), t):
            out.pop("resolution", None)   # раунда ремонта ещё не было (прошлый раунд — по истории статусов)
        else:
            r2 = dict(res)
            votes = dict(res.get("votes") or {}) if isinstance(res.get("votes"), dict) else {}
            ver = parse_time(res.get("verified_at"))
            ver_ok = ver is not None and ver <= t
            state = res.get("state")
            if state == "reopened" and _after(res.get("reopened_at"), t):
                state = "verified" if ver_ok else "reported"
                votes["no"] = 0
                r2["reopened_at"] = None
            if ver is not None and ver > t:     # первое «Да» и есть проверка: до неё голосов «да» не было
                if state == "verified":
                    state = "reported"
                votes["yes"] = 0
                r2["verified_at"] = None
            if state == "withdrawn" and out.get("status") == "fixed":
                state = "verified" if ver_ok else "reported"   # служба вернула в работу позже t
            r2["state"] = state
            r2["votes"] = votes
            out["resolution"] = r2
    return out


def last_event(c: dict) -> datetime | None:
    """Самое позднее событие жалобы (шаг статуса, «Я тоже», ответ жителя, раунд ремонта). Кадр позже него получает
    запись как есть, без копии: так прошлые дни месяца считаются быстро (as_of нужен только «молодым» жалобам)."""
    found = [parse_time(c.get(k)) for k in ("created_at", "updated_at", "verified_at", "checked_at")]
    for h in c.get("status_history") or []:
        if isinstance(h, dict):
            found.append(parse_time(h.get("at")))
    found.extend(parse_time(x) for x in c.get("metoo_times") or [])
    for key in ("resident_checks", "checks"):
        for x in c.get(key) or [] if isinstance(c.get(key), list) else []:
            if isinstance(x, dict):
                found.append(parse_time(x.get("at")))
    for key in ("resident_check", "verification"):
        if isinstance(c.get(key), dict):
            found.append(parse_time(c[key].get("at")))
    res = c.get("resolution")
    if isinstance(res, dict):
        found.extend(parse_time(res.get(k)) for k in ("reported_at", "verified_at", "reopened_at"))
    found = [x for x in found if x is not None]
    return max(found) if found else None


# ---------------------------------------------------------------- даты

def parse_day(value, field: str) -> date | None:
    if value in (None, ""):
        return None
    s = str(value).strip()
    try:
        if len(s) == 10:
            return date.fromisoformat(s)
    except ValueError:
        pass
    t = parse_time(s)
    if t is None:
        raise ReplayError(field, f"{field} — дата ГГГГ-ММ-ДД")
    return t.astimezone(ASTANA_TZ).date()


def day_moment(d: date, now: datetime) -> datetime:
    """Момент кадра дня d: конец дня по Астане, для сегодня — сейчас."""
    end = datetime.combine(d, dtime(23, 59, 59), tzinfo=ASTANA_TZ)
    return now if end >= now else end


def _days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ---------------------------------------------------------------- компактный вид кадра

STATIC_FIELDS = ("target", "geometry", "anchor", "district", "approximate")


def _key(it: dict) -> str:
    return it["target"]["kind"] + ":" + str(it["target"]["id"])


def _compact(it: dict) -> dict:
    """То, что меняется день ото дня: вес, уровень, цвет, число, состояние. Вес — до 0,1 (ореол на глаз не отличит)."""
    out = {"key": _key(it), "w": round(float(it.get("weight") or 0), 1), "level": it.get("level"), "color": it.get("color"),
           "count": int(it.get("count") or 0), "state": it.get("state")}
    if it.get("fixed_kind"):
        out["fixed_kind"] = it["fixed_kind"]
    if it.get("reopened"):
        out["reopened"] = True
    if it["target"]["kind"] == "district":
        out["targets"] = int(it.get("targets") or 0)
    return out


def _static(it: dict) -> dict:
    """Что у цели не меняется: подпись, форма, якорь значка, район; cat — главная категория (иконка значка)."""
    out = {k: it.get(k) for k in STATIC_FIELDS if k in it}
    cats = it.get("by_category") or {}
    if cats:
        out["cat"] = next(iter(cats))
    return out


def _totals(items: list, districts: list) -> dict:
    active = [it for it in items if it["state"] == "active"]
    return {
        "people": sum(int(it.get("count") or 0) for it in active),
        "active": len(active),
        "hot": sum(1 for it in active if isinstance(it.get("level"), int) and it["level"] >= 3),
        "fixed": sum(1 for it in items if it["state"] == "fixed"),
        "verified": sum(1 for it in items if it["state"] == "fixed" and it.get("fixed_kind") == "verified"),
        "reopened": sum(1 for it in active if it.get("reopened")),
        "districts_active": sum(1 for it in districts if it["state"] == "active"),
    }


# ---------------------------------------------------------------- сам расчёт

class Replay:
    """Хроника поверх HeatService: те же записи, тот же расчёт, свой кэш кадров прошлых дней."""

    def __init__(self, svc):
        self.svc = svc
        self._lock = threading.Lock()
        self._frames: dict = {}    # (поколение, день, days, category, district) -> (items, districts)
        self._replies: dict = {}   # ключ запроса -> (monotonic, ответ)
        self._warmed: set = set()  # (поколение, days, category, district): месяц уже досчитывается в фоне
        self.last_compute_ms = 0.0

    def params(self, *, from_=None, to=None, step=None, days=None, category=None, district=None, last=None, fmt=None, now=None):
        svc = self.svc
        now = now or svc._clock()
        today = now.astimezone(ASTANA_TZ).date()
        _bbox, days, category, district, _zoom = svc._params(days=days, category=category, district=district)
        step = step or "day"
        if step not in STEPS:
            raise ReplayError("step", "step — только day (кадр на каждый день)")
        fmt = fmt or "compact"
        if fmt not in ("compact", "full"):
            raise ReplayError("format", "format — compact или full")
        end = parse_day(to, "to") or today
        start = parse_day(from_, "from")
        if start is None:
            if last in (None, ""):
                n = 7
            else:
                try:
                    n = int(last)
                except (TypeError, ValueError):
                    raise ReplayError("last", "last — число дней (7 или 30)") from None
                if not 1 <= n <= MAX_SPAN_DAYS:
                    raise ReplayError("last", f"last — от 1 до {MAX_SPAN_DAYS}")
            start = end - timedelta(days=n - 1)
        if end > today:
            end = today          # будущего у хроники нет — последний кадр «сегодня»
        if start > end:
            raise ReplayError("from", "from позже to")
        if (end - start).days + 1 > MAX_SPAN_DAYS:
            raise ReplayError("from", f"не больше {MAX_SPAN_DAYS} дней за раз")
        if (today - start).days > MAX_BACK_DAYS:
            raise ReplayError("from", "хроника — не дальше года назад")
        return {"start": start, "end": end, "days": days, "category": category, "district": district, "fmt": fmt,
                "step": step, "now": now}

    def build(self, **kwargs) -> dict:
        p = self.params(**kwargs)
        svc = self.svc
        now = p["now"]
        gen = svc.generation
        rkey = (gen, p["start"], p["end"], p["days"], p["category"], p["district"], p["fmt"], int(now.timestamp() // 60))
        with self._lock:
            hit = self._replies.get(rkey)
            if hit and time.monotonic() - hit[0] < REPLY_TTL_S:
                return hit[1]
        started = time.perf_counter()
        frames = self._frames_for(p, gen)
        reply = self._reply(p, frames)
        reply["events"] = marks_mod.collect(svc, day_moment(p["start"], now) - timedelta(days=1), now, district=p["district"])
        self.last_compute_ms = round((time.perf_counter() - started) * 1000, 1)
        reply["compute_ms"] = self.last_compute_ms
        with self._lock:
            if len(self._replies) >= CACHE_REPLIES_MAX:
                self._replies.clear()
            self._replies[rkey] = (time.monotonic(), reply)
        self._warm_month(p, gen)
        return reply

    def _warm_month(self, p: dict, gen: int) -> None:
        """Попросили неделю — в фоне досчитать месяц (чип «30 дней» откроется сразу). Один раз на поколение данных."""
        today = p["now"].astimezone(ASTANA_TZ).date()
        if p["end"] != today or (p["end"] - p["start"]).days >= 29:
            return
        key = (gen, p["days"], p["category"], p["district"])
        with self._lock:
            if key in self._warmed:
                return
            self._warmed.add(key)
        month = dict(p, start=today - timedelta(days=29))

        def run():
            try:
                self._frames_for(month, gen)
            except Exception:   # фоновый расчёт не мешает ответу; ошибку увидит обычный запрос
                pass

        threading.Thread(target=run, name="heat-replay-warm", daemon=True).start()

    # кадры: прошлые дни — из кэша, если записи не менялись (то же поколение)
    def _frames_for(self, p: dict, gen: int) -> list:
        svc, now = self.svc, p["now"]
        today = now.astimezone(ASTANA_TZ).date()
        span = svc.window(p["days"])   # то же окно выборки, что у /heat
        need, out = [], {}
        with self._lock:
            for d in _days(p["start"], p["end"]):
                fk = (gen, d, p["days"], p["category"], p["district"])
                if d < today and fk in self._frames:
                    out[d] = self._frames[fk]
                else:
                    need.append(d)
        if need:
            # Сборщик мусора — на время расчёта кадров выключен: кадры создают десятки тысяч коротких словарей без циклов
            # (их освобождает счётчик ссылок), а полный обход большой кучи процесса (граф R12, слой OSM) удваивал время.
            gc_on = gc.isenabled()
            gc.disable()
            try:
                self._compute_days(p, need, out, gen, span)
            finally:
                if gc_on:
                    gc.enable()
        return [(d,) + out[d] for d in _days(p["start"], p["end"])]

    def _compute_days(self, p: dict, need: list, out: dict, gen: int, span: timedelta) -> None:
        """Кадры дней need: одна выборка записей, затем на каждый день — as_of и тот же расчёт, что у /heat."""
        svc, now = self.svc, p["now"]
        today = now.astimezone(ASTANA_TZ).date()
        first = day_moment(need[0], now)
        # Один запрос к источнику на все кадры (с запасом на самый ранний); дальше — фильтр как у источника:
        # R09 отдаёт жалобы, созданные не раньше since (= момент − HeatService.window), демо-набор — все.
        records = svc.records(first - span)
        # Порядок записей — как у источника: при равных весе и числе порядок мест в ответе тот же, что у /heat.
        rows = []
        for r in records:
            if isinstance(r, dict):
                cr = parse_time(r.get("created_at"))
                if cr is not None:
                    rows.append((cr, last_event(r) or cr, r))
        filter_since = not svc.is_demo
        for d in need:
            t = day_moment(d, now)
            lo = t - span
            recs = []
            for cr, last, r in rows:
                if cr > t or (filter_since and cr < lo):
                    continue
                a = r if last <= t else as_of(r, t)
                if a is not None:
                    recs.append(a)
            computed = svc._compute(now=t, days=p["days"], category=p["category"], district=p["district"], bbox=None, records=recs)
            items = computed["items"]
            dists = engine.districts_summary(items, svc.config, district=p["district"])
            out[d] = (t, items, dists)
            if d < today:
                with self._lock:
                    if len(self._frames) >= CACHE_DAYS_MAX:
                        self._frames.clear()
                    self._frames[(gen, d, p["days"], p["category"], p["district"])] = out[d]

    def _reply(self, p: dict, frames: list) -> dict:
        svc = self.svc
        targets: dict = {}
        out_frames = []
        prev: dict | None = None
        prev_d: dict | None = None
        for d, t, items, dists in frames:
            fr = {"date": d.isoformat(), "at": iso(t), "totals": _totals(items, dists)}
            if p["fmt"] == "full":
                fr["items"] = items
                fr["districts"] = dists
            else:
                cur = {}
                for it in items:
                    k = _key(it)
                    cur[k] = _compact(it)
                    targets[k] = _static(it)   # последний день, где цель была, — её подпись и главная категория
                cur_d = {}
                for it in dists:
                    k = _key(it)
                    cur_d[k] = _compact(it)
                    targets.setdefault(k, _static(it))
                if prev is None:
                    fr["items"] = list(cur.values())
                    fr["districts"] = list(cur_d.values())
                else:
                    fr["changed"] = [v for k, v in cur.items() if prev.get(k) != v]
                    fr["removed"] = [k for k in prev if k not in cur]
                    fr["districts_changed"] = [v for k, v in cur_d.items() if prev_d.get(k) != v]
                    fr["districts_removed"] = [k for k in prev_d if k not in cur_d]
                prev, prev_d = cur, cur_d
            out_frames.append(fr)
        demo_flags = [it.get("demo") for _d, _t, items, _ds in frames for it in items if "demo" in it]
        return {
            "generated_at": iso(p["now"]),
            "params": {"from": p["start"].isoformat(), "to": p["end"].isoformat(), "step": p["step"], "days": p["days"],
                       "category": p["category"], "district": p["district"], "format": p["fmt"]},
            "format": p["fmt"],
            "legend": svc.config.legend(),
            "targets": targets if p["fmt"] == "compact" else None,
            "frames": out_frames,
            "demo": svc.is_demo or (bool(demo_flags) and all(demo_flags)),
            "district_zoom_max": DISTRICT_ZOOM_MAX,
        }


def district_names() -> dict:
    return {d_id: {"ru": d["name_ru"], "kk": d["name_kk"]} for d_id, d in geo.districts().items()}
