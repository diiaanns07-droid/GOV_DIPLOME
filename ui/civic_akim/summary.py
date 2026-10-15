"""«Картина дня» для акима: все числа одной функцией summary(date, district).

ОПРЕДЕЛЕНИЯ (одним местом, чтобы следующий разработчик не искал по коду):
- Время — Астана, UTC+5. День D = [D 00:00, D+1 00:00). Если D — сегодня, считаем до текущего
  момента (as_of = сейчас); если D в прошлом — на конец дня (as_of = D 23:59:59).
- Обращение = запись жалобы v2 без duplicate_of (дубль уже влит в оригинал как «Я тоже»).
- «Новые за день» — поданы с начала дня D до as_of. Сравниваем с тем же отрезком ровно неделю назад:
  в 10:00 — с прошлой неделей до 10:00, а не с целым днём, иначе утром всегда было бы «меньше».
- «Новые за 7 дней» — (as_of − 7 дн., as_of]; сравнение — с 7 днями перед ними.
- «В работе» — статус на момент as_of «принято» или «в работе». «Ждут ответа» — статус «новое».
- «Просрочено» — на момент as_of не исправлено (новое / принято / в работе), а срок категории истёк
  (deadlines.due: рабочие дни с праздниками РК, у аварийных категорий — календарные; демо-норматив).
- «Исправлено за неделю» — получили статус «исправлено» за (as_of − 7 дн., as_of] и не открыты снова.
  Делится на «проверено жителями» и «ждёт проверки» (служба сообщила об устранении, жители ещё не
  подтвердили) — heat_states в categories_v2.json. «Вернули в работу» — за 7 дней после «исправлено»
  обращение снова открыто (у R09 так бывает, когда житель ответил «Проблема осталась»).
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

from . import blocks, deadlines, decisions, neighbors, pulse, routing, sources, text

ASTANA_TZ = timezone(timedelta(hours=5))
WEEK = timedelta(days=7)
SERIES_DAYS = 14  # мини-графики под числами «Картины дня» (дизайн-марафон): по дням, последний — сегодня до as_of
HEAT_DAYS = 7           # период тепловой карты для «Картины дня»: последняя неделя
TOP_N = 10              # «Горячие места» — первые 10 целей карты
OVERDUE_TOP = 5         # «Просрочено — дольше всех»: сколько строк с таймером показать
OPEN = ("new", "accepted", "in_progress")
WORK = ("accepted", "in_progress")
# «Исправлено»: fixed у R09 сейчас; verified / verified_fixed — если R09 сделает «проверено жителями» статусом.
FIXED = ("fixed", "verified", "verified_fixed")
VERIFIED_STATUSES = ("verified", "verified_fixed")
# Проверка жителями (волна 2 п. 1). Основная форма — R09 lifecycle.py (claude/modest-shannon-0ki93p, 8c07864):
#   record["resolution"] = {state: reported|verified|reopened, reported_at, verified_at, reopened_at, votes, round};
#   возврат в работу — шаг истории {"status": "in_progress", "reopened_by_residents": true}.
# Запасные формы (если R09 поменяет): в status_history {"event": "resident_check", "answer": "yes|no|cant"},
#   {"event": "verified"} / {"event": "reopened", "by": "resident"}; у записи verification = {"state", "at"}.
VERIFIED_EVENTS = {"verified", "verified_fixed", "resident_verified", "resident_confirmed"}
REOPEN_EVENTS = {"reopened", "resident_reopened", "resident_not_fixed", "not_fixed"}
YES = {"yes", "fixed", "confirmed", "verified"}
NO = {"no", "not_fixed", "still_there", "reopened"}
PCT_MIN_BASE = 10       # с какой базы показывать изменение в процентах
CACHE_TTL_S = 30.0
# Блоки соседей (раунд 15, blocks.py): ведомства и кризис — R17, жители вместе — R16 (+ R09), встречи и прогноз — R13.
NEIGHBOR_BLOCKS = ("agencies", "crisis", "together", "meetings", "forecast")

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
    """Когда обращение (последний раз до moment) стало «исправлено»; None — не исправлено на moment.

    «Проверено жителями» после «исправлено» — то же исправление: считаем от первого перехода в группу FIXED.
    """
    if status_at(record, moment) not in FIXED:
        return None
    last, prev = None, None
    for t, s in _history(record):
        if t > moment:
            break
        if s in FIXED and prev not in FIXED:
            last = t
        prev = s
    if last is None:  # статус fixed без истории — как у R07: время обновления или подачи
        last = parse_time(record.get("updated_at")) or parse_time(record.get("created_at"))
    return last


def kpi_series(recs: list[dict], ends: list[datetime]) -> dict:
    """«В работе», «просрочено», «исправлено за 7 дней» на каждый момент ends — то же, что _kpi.at(), но за один проход:
    история каждой записи разбирается один раз (14 моментов × все записи по отдельности — в 3 раза медленнее сводки)."""
    n = len(ends)
    work, overdue, fixed = [0] * n, [0] * n, [0] * n
    for r in recs:
        created = parse_time(r.get("created_at"))
        if created is None:
            continue
        hist = _history(r)
        due = deadlines.due(r.get("category"), created)
        fallback_fixed = parse_time(r.get("updated_at")) or created
        last_t = hist[-1][0] if hist else None
        for i, m in enumerate(ends):
            if created > m:
                continue
            if last_t is None or last_t <= m:  # позже m в истории ничего нет — верим текущему полю (как status_at)
                st = r.get("status") or (hist[-1][1] if hist else "new")
            else:
                st = "new"
                for t, s_ in hist:
                    if t > m:
                        break
                    st = s_
            if st in WORK:
                work[i] += 1
            if st in OPEN and m > due:
                overdue[i] += 1
            if st in FIXED:
                last, prev = None, None
                for t, s_ in hist:
                    if t > m:
                        break
                    if s_ in FIXED and prev not in FIXED:
                        last = t
                    prev = s_
                f = last if last is not None else fallback_fixed
                if m - WEEK < f <= m:
                    fixed[i] += 1
    return {"work": work, "overdue": overdue, "fixed": fixed}


def _resident_marks(record: dict) -> list[tuple[datetime, str]]:
    """Отметки жителей: [(время, verified|reopened)] из status_history и поля verification."""
    marks = []
    for h in record.get("status_history") or []:
        if not isinstance(h, dict):
            continue
        t = parse_time(h.get("at"))
        if t is None:
            continue
        ev = str(h.get("event") or h.get("type") or "").lower()
        answer = str(h.get("answer") or "").lower()
        reason = str(h.get("reason") or "").lower()
        if h.get("status") in VERIFIED_STATUSES or ev in VERIFIED_EVENTS or (ev == "resident_check" and answer in YES):
            marks.append((t, "verified"))
        elif (ev in REOPEN_EVENTS or reason in REOPEN_EVENTS or (ev == "resident_check" and answer in NO)
              or h.get("reopened_by_residents") is True):
            marks.append((t, "reopened"))
    res = record.get("resolution")
    if isinstance(res, dict):  # R09: время последнего «Да, исправлено» в текущем раунде
        t = parse_time(res.get("verified_at"))
        if t is not None and res.get("state") == "verified":
            marks.append((t, "verified"))
    v = record.get("verification") or record.get("resident_check")
    if isinstance(v, dict):
        state = str(v.get("state") or v.get("status") or "").lower()
        t = parse_time(v.get("at")) or parse_time(record.get("updated_at"))
        if t is not None and state in YES | {"verified_fixed"}:
            marks.append((t, "verified"))
        elif t is not None and state in NO:
            marks.append((t, "reopened"))
    marks.sort(key=lambda m: m[0])
    return marks


def verified_at(record: dict, moment: datetime) -> datetime | None:
    """Когда жители подтвердили текущее исправление (на момент moment); None — ещё не подтвердили."""
    fixed = fixed_moment(record, moment)
    if fixed is None:
        return None
    for t, kind in _resident_marks(record):
        if kind == "verified" and fixed <= t <= moment:
            return t
    if status_at(record, moment) in VERIFIED_STATUSES:  # статус без отметки времени
        return fixed
    return None


def reopen_moments(record: dict, moment: datetime) -> list[tuple[datetime, bool]]:
    """Возвраты в работу после «исправлено» до moment: [(время, by_resident)].

    Порядок шагов — как в списке status_history (R09 дописывает шаги по порядку), а не по времени: в демо-наборе
    R07 у части записей время «исправлено» раньше времени «принято», и сортировка по времени выдумала бы возврат.
    by_resident — у шага reopened_by_residents (R09) или by=resident, или рядом (±1 ч) отметка «Проблема осталась».
    """
    marks = [t for t, kind in _resident_marks(record) if kind == "reopened"]
    out, prev = [], None
    for h in record.get("status_history") or []:
        if not isinstance(h, dict) or not h.get("status"):
            continue
        t, s = parse_time(h.get("at")), str(h["status"])
        if t is None:
            continue
        if prev in FIXED and s in OPEN and t <= moment:
            by_resident = (h.get("reopened_by_residents") is True or str(h.get("by") or "").lower() == "resident"
                           or any(abs((m - t).total_seconds()) <= 3600 for m in marks))
            out.append((t, by_resident))
        prev = s
    return out


def snapshot(record: dict, moment: datetime) -> dict | None:
    """Запись такой, какой она была в момент moment (для расчёта карты «неделю назад»).

    «Я тоже»: если у записи есть metoo_times (время каждого нажатия, R09 → R07), нажатия после moment
    отбрасываются и metoo уменьшается. «Я тоже» без времени (старые записи) считаются нажатыми при подаче.
    """
    st = status_at(record, moment)
    if st is None:
        return None
    copy = dict(record)
    copy["status"] = st
    copy["status_history"] = [h for h in record.get("status_history") or []
                              if isinstance(h, dict) and (parse_time(h.get("at")) or moment) <= moment]
    times = record.get("metoo_times")
    if isinstance(times, (list, tuple)) and times:
        parsed = [(x, parse_time(x)) for x in times]
        kept = [x for x, t in parsed if t is not None and t <= moment]
        later = sum(1 for _, t in parsed if t is not None and t > moment)
        try:
            metoo = int(record.get("metoo") or 0)
        except (TypeError, ValueError):
            metoo = 0
        copy["metoo_times"] = kept
        copy["metoo"] = max(0, metoo - later)
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
    def __init__(self, *, heat=_AUTO, records=_AUTO, objects=_AUTO, proposals=_AUTO, clock=None, demo_build=False,
                 db_path=None, neighbor_sources=None, fixtures=None, neighbors_=None):
        """heat — HeatService R07 (False — без карты); records — функция since → записи v2;
        objects / proposals — функции (district, today) → список (CONTRACT §7, R06).
        demo_build — демо-сборка R01 (CIVIC_DEMO=1): пример «Нужно решение акима» виден, пока настоящих нет (R10 B-061).
        Раунд 15 — соседи «Картины дня» 2.0 и ситуационного центра (neighbors.py): db_path — база шлюза (для сервисов
        R17/R16/R13), neighbor_sources — явные функции соседей {"agencies_board": fn, …} (имена — neighbors.FUNCS),
        fixtures — фикстуры R08 (стенд, тесты).
        По умолчанию всё подключается само (sources.py, neighbors.py)."""
        self.demo_build = bool(demo_build)
        self.neighbors = neighbors_ or neighbors.Neighbors(sources=neighbor_sources, db_path=db_path, fixtures=fixtures)
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
        if isinstance(district, str):
            district = district.strip().lower()  # «Nura», « nura » из адресной строки — тот же район
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
        gen = getattr(self.heat, "generation", None)
        gen = getattr(self.heat, "_generation", 0) if gen is None else gen  # публичное имя — после patch R07
        key = (day.isoformat(), district, int(now.timestamp() // 60), gen)
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
        items_now, items_prev = heat_part.pop("_items_now"), heat_part.pop("_items_prev")
        labels = {it["target"].get("id"): {"ru": it["target"].get("label_ru"), "kk": it["target"].get("label_kk")}
                  for it in items_now or [] if it["target"].get("label_ru")}
        objects = self._objects_part(district, as_of)
        proposals = self._proposals_part(district, as_of)
        overdue_list = self._overdue_part(scoped, as_of, labels)
        decisions_part = self._decisions_part(scoped, district, as_of, labels)
        pulse_part = self._pulse_part(scoped, as_of, items_now, items_prev)
        # Раунд 15 («Картина дня» 2.0): блоки соседей R17 / R16 / R13 — только «сегодня»: у соседей нет истории «на дату».
        if is_today:
            nb = self.neighbor_blocks(district, as_of, kpi)
            blocks.crisis_links(pulse_part.get("items") or [], nb["crisis"])
        else:
            nb = {name: blocks.past_date() for name in NEIGHBOR_BLOCKS}

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
            "overdue": overdue_list,
            "decisions": decisions_part,
            "pulse": pulse_part,
            "objects": objects,
            "proposals": proposals,
            **nb,
            "deadlines": dict(deadlines.DEADLINE_DAYS),
            "deadline_units": {c: deadlines.unit(c) for c in deadlines.DEADLINE_DAYS},
            "heat_days": HEAT_DAYS,
            # Нет источника жалоб — это «нет данных», а не «ноль обращений»: интерфейс и сводка говорят об этом прямо.
            "complaints_available": self._records is not None,
            "empty": self._records is not None and kpi["new_day"]["value"] == 0,
            "sources": dict(self.source_names),
            "demo": {
                "complaints": any(r.get("demo") for r in scoped) or self.source_names["complaints"] == "r07-demo",
                "objects": objects.get("demo", False),
                "proposals": proposals.get("demo", False),
                "decisions": decisions_part.get("demo", False),
                # Прогноз R13 — всегда прототип на синтетике: у блока своя пометка «прототип», в «данные — пример» не идёт.
                **{name: bool(nb[name].get("demo")) for name in NEIGHBOR_BLOCKS if name != "forecast"},
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
            work = waiting = overdue = fixed = verified = reopened = reopened_res = 0
            for r in recs:
                st = status_at(r, moment)
                if st is None:
                    continue
                if st in WORK:
                    work += 1
                elif st == "new":
                    waiting += 1
                if st in OPEN and moment > deadlines.due(r.get("category"), parse_time(r["created_at"])):
                    overdue += 1
                f = fixed_moment(r, moment)
                if f is not None and moment - WEEK < f <= moment:
                    fixed += 1
                    if verified_at(r, moment) is not None:
                        verified += 1
                for t, by_resident in reopen_moments(r, moment):
                    if moment - WEEK < t <= moment:
                        reopened += 1
                        reopened_res += int(by_resident)
            return {"work": work, "waiting": waiting, "overdue": overdue, "fixed": fixed, "verified": verified,
                    "reopened": reopened, "reopened_by_residents": reopened_res}

        now_state, prev_state = at(as_of), at(as_of - WEEK)
        new_day = created_between(day_start, as_of, True)
        new_day_prev = created_between(day_start - WEEK, as_of - WEEK, True)
        new_week = created_between(as_of - WEEK, as_of, False)
        new_week_prev = created_between(as_of - 2 * WEEK, as_of - WEEK, False)
        # Мини-графики: новые за каждый из 14 дней; «в работе», «просрочено», «исправлено за 7 дней» — на конец дня
        # (сегодня — на as_of, последняя точка = само число). Только для вида — числа и сравнения выше не меняются.
        tick = timedelta(microseconds=1)
        starts = [day_start - timedelta(days=k) for k in range(SERIES_DAYS - 1, -1, -1)]
        ends = [a + timedelta(days=1) - tick for a in starts[:-1]] + [as_of]
        series = kpi_series(recs, ends)
        series_new = [0] * SERIES_DAYS
        for r in recs:
            c = parse_time(r["created_at"])
            if starts[0] <= c <= as_of:
                series_new[min((c - starts[0]).days, SERIES_DAYS - 1)] += 1
        return {
            "new_day": {**change(new_day, new_day_prev), "series": series_new},
            "new_week": change(new_week, new_week_prev),
            "in_progress": {**change(now_state["work"], prev_state["work"]), "waiting": now_state["waiting"],
                            "series": series["work"]},
            "overdue": {**change(now_state["overdue"], prev_state["overdue"]), "series": series["overdue"]},
            # verified + awaiting = value: «служба сообщила об устранении» делится на проверенные жителями и ждущие проверки.
            "fixed_week": {**change(now_state["fixed"], prev_state["fixed"]), "series": series["fixed"],
                           "verified": now_state["verified"],
                           "awaiting": now_state["fixed"] - now_state["verified"], "reopened": now_state["reopened"],
                           "reopened_by_residents": now_state["reopened_by_residents"]},
            # Проверка жителями есть в данных (R09 волна 2)? Нет — интерфейс не пишет «проверено: 0», а молчит.
            "verification_available": any(isinstance(r.get("resolution"), dict) or _resident_marks(r)
                                          or r.get("status") in VERIFIED_STATUSES for r in recs),
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
            return {"hot": unavailable, "topics": unavailable, "districts": unavailable, "main_problem": None,
                    "_items_now": None, "_items_prev": None}

        moment_prev = as_of - WEEK
        snap_prev = [s for s in (snapshot(r, moment_prev) for r in recs) if s]
        snap_now = None if is_today else [s for s in (snapshot(r, as_of) for r in recs) if s]

        # Горячие места: первые TOP_N активных целей — то же, что HeatService.top().
        items = self._items_now(as_of, is_today, snap_now, district=district)
        active_now = self._active(items)
        by_target: dict = {}
        for r in recs:
            t = r.get("target")
            if isinstance(t, dict) and t.get("id") and not r.get("duplicate_of"):
                by_target.setdefault(t["id"], []).append(r)
        hot = []
        for rank, it in enumerate(active_now[:TOP_N], start=1):
            by_cat = it.get("by_category") or {}
            hot.append({
                "rank": rank,
                "target": {k: it["target"].get(k) for k in ("kind", "id", "label_ru", "label_kk")},
                "count": it["count"], "level": it["level"], "color": it.get("color"), "weight": it["weight"],
                "status": it.get("status"), "district": it.get("district"),
                "category": next(iter(by_cat), None), "approximate": bool(it.get("approximate")),
                "subtopic": self._subtopic_of(by_target.get(it["target"].get("id"), []), as_of),
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
            # Внутреннее (не уходит в ответ): цели карты сейчас и неделю назад — для «Пульса» и подписей мест.
            "_items_now": active_now,
            "_items_prev": self._active(self._items_past(snap_prev, moment_prev, district=district)),
        }

    @staticmethod
    def _subtopic_of(records: list[dict], as_of: datetime) -> dict | None:
        """Уточнение горячего места (волна мелочей п. 12): чаще всего выбранное жителями среди нерешённых.

        Считаем людей (жалоба + «Я тоже»). Нет уточнений в данных — None, интерфейс пишет только категорию.
        """
        acc: dict = {}
        for r in records:
            if status_at(r, as_of) not in OPEN or not r.get("subtopic"):
                continue
            key = (r.get("category"), r["subtopic"])
            acc[key] = acc.get(key, 0) + 1 + int(r.get("metoo") or 0)
        if not acc:
            return None
        (cat, sub), n = max(acc.items(), key=lambda kv: (kv[1], kv[0][1]))
        info = decisions._subtopic(cat, sub)
        if info is None:
            return None
        return {**info, "category": cat, "people": n, "share": round(n / sum(acc.values()), 2)}

    # ---------- просрочки, решения, пульс ----------
    def _overdue_part(self, recs: list[dict], as_of: datetime, labels: dict) -> dict:
        """«Просрочено — дольше всех»: таймер в рабочих днях (волна мелочей п. 6), служба (п. 7), без текстов жителей."""
        rows = []
        for r in recs:
            if status_at(r, as_of) not in OPEN:
                continue
            created = parse_time(r["created_at"])
            timer = deadlines.timer(r.get("category"), created, as_of)
            if timer["state"] != "overdue":
                continue
            target = r.get("target") if isinstance(r.get("target"), dict) else {}
            label = labels.get(target.get("id"))
            service = routing.service_for(r.get("category"), r.get("subtopic"))
            rows.append({"id": r.get("id"), "category": r.get("category"), "district": self._district_of(r),
                         "subtopic": decisions._subtopic(r.get("category"), r.get("subtopic")),
                         "place_ru": (label or {}).get("ru"), "place_kk": (label or {}).get("kk"),
                         # Ссылка на карту — только если место есть на карте (у него есть подпись цели).
                         "target": {"kind": target.get("kind"), "id": target.get("id")} if target.get("id") else None,
                         "on_map": bool(label),
                         "people": 1 + int(r.get("metoo") or 0), "timer": timer,
                         "service": {k: service[k] for k in ("id", "ru", "kk", "name_edited")},
                         "demo": bool(r.get("demo"))})
        # Одно место — одна строка: несколько просроченных обращений об одной остановке не повторяем.
        places: dict = {}
        for row in rows:
            key = ("t", row["target"]["kind"], row["target"]["id"]) if row["target"] else ("c", row["id"])
            cur = places.get(key)
            if cur is None:
                places[key] = {**row, "complaints": 1}
                continue
            cur["complaints"] += 1
            cur["people"] += row["people"]
            cur["demo"] = cur["demo"] or row["demo"]
            if row["timer"]["overdue_by"] > cur["timer"]["overdue_by"]:
                cur.update({k: row[k] for k in ("id", "timer", "category", "subtopic", "service")})
        grouped = sorted(places.values(), key=lambda x: (-x["timer"]["overdue_by"], -x["complaints"], -x["people"], str(x["id"])))
        return {"count": len(rows), "places": len(grouped), "items": grouped[:OVERDUE_TOP], "top": OVERDUE_TOP}

    def _decisions_part(self, recs: list[dict], district, as_of: datetime, labels: dict) -> dict:
        """«Нужно решение акима» (волна 2 п. 5). Критерий — decisions.py.

        Пример из фикстуры — только когда все жалобы демо (источник R07-демо или каждая запись demo: true) или это
        демо-сборка R01 (CIVIC_DEMO=1): там первая же жалоба репетиции (demo: false) прятала блок до перезапуска
        (R10 B-061). Пример — только пока настоящих «нужно решение» нет, с пометкой demo/«пример»; в обычной сборке
        среди настоящих обращений пример не подмешиваем никогда.
        """
        items = decisions.build(recs, as_of, status_at=status_at, parse_time=parse_time, labels=labels)
        demo = False
        all_demo = self.source_names.get("complaints") == "r07-demo" or (bool(recs) and all(r.get("demo") is True for r in recs))
        # Демо-мир R02 (CIVIC_DEMO_WORLD=1): примера R08 нет — «Нужно решение» только из жалоб демо-мира (паспорт R09).
        if not items and (all_demo or self.demo_build) and not neighbors.demo_world():
            example = [r for r in decisions.fixture_records(as_of.date())
                       if district is None or r.get("district") == district]
            items = decisions.build(example, as_of, status_at=status_at, parse_time=parse_time)
            demo = bool(items)
        return {"available": self._records is not None, "items": items[:decisions.MAX_ITEMS], "count": len(items),
                "demo": demo, "source": "example" if demo else "complaints"}

    def choose_decision(self, item_id: str, option, *, actor: str | None = None, district=None) -> dict:
        """«Выбрать» вариант (R11 IA_WAVE2 §5). Выбирать можно только из пунктов, которые аким сейчас видит."""
        now = self._clock()
        day, district = self._params(None, district, now)
        all_records, _ = self._load_records()
        scoped = [r for r in all_records if not r.get("duplicate_of")
                  and (district is None or self._district_of(r) == district)]
        part = self._decisions_part(scoped, district, now.astimezone(ASTANA_TZ), {})
        record = decisions.choose(item_id, option, items=part["items"], actor=actor)
        self.invalidate()
        return {"id": item_id, "chosen": record}

    def neighbor_blocks(self, district, as_of: datetime, kpi: dict | None) -> dict:
        """Блоки соседей на момент as_of (раунд 15). Сосед не готов или упал — блок {"available": False} (blocks.py)."""
        nb, names = self.neighbors, {d_id: {"ru": i["ru"], "kk": i["kk"]} for d_id, i in districts().items()}
        board, board_src = nb.safe("agencies_board", now=as_of, days=7, district=district)
        joint = hand = None
        if board is not None:
            joint, _ = nb.safe("agencies_joint", now=as_of, days=7, district=district)
            hand, _ = nb.safe("agencies_handoffs", now=as_of, days=7, district=district)
        incidents, inc_src = nb.safe("incidents", now=as_of, district=district)
        inits, init_src = nb.safe("initiatives", now=as_of, district=district)
        yards = nb.safe("yards", now=as_of, district=district)[0] if inits is not None else None
        meets, meet_src = nb.safe("meetings", now=as_of, district=district)
        today = as_of.astimezone(ASTANA_TZ).date()
        fc, fc_src = nb.safe("forecast_week", now=as_of, district=district, k=blocks.FORECAST_TOP, today=today)
        period = "week"
        if fc is None:
            fc, fc_src = nb.safe("forecast_month", now=as_of, district=district, k=blocks.FORECAST_TOP, today=today)
            period = "month"
        return {
            "agencies": blocks.agencies(board, board_src, joint, hand, as_of=as_of),
            "crisis": blocks.crisis(incidents, inc_src, as_of=as_of, district=district, district_names=names),
            "together": blocks.together(inits, init_src, yards, as_of=as_of, district=district, kpi=kpi),
            "meetings": blocks.meetings(meets, meet_src, as_of=as_of, district=district, district_names=names),
            "forecast": blocks.forecast(fc, fc_src, period),
        }

    def board(self, district=None, now: datetime | None = None) -> dict:
        """«Ситуационный центр» (GET akim/board) — situation.py."""
        from . import situation  # локально: situation импортирует summary
        return situation.build(self, district=district, now=now or self._clock())

    def week(self, date=None, district=None, now: datetime | None = None) -> dict:
        """«Картина недели» (GET akim/week?date) — weekly.py."""
        from . import weekly
        return weekly.build(self, date=date, district=district, now=now or self._clock())

    def _pulse_part(self, recs: list[dict], as_of: datetime, items_now, items_prev) -> dict:
        """«Пульс» (волна 2 п. 8): метод — pulse.py."""
        if self._records is None or items_now is None:
            return {"available": False, "items": []}
        names = {d_id: {"ru": i["ru"], "kk": i["kk"]} for d_id, i in districts().items()}
        return pulse.alarms(recs, as_of, parse_time=parse_time, district_of=self._district_of,
                            categories=deadlines.load_categories()["categories"], district_names=names,
                            items_now=items_now, items_prev=items_prev or [])

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
                     "title_kk_missing": not p.get("title_kk"),
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


def board(district=None, now: datetime | None = None) -> dict:
    """«Ситуационный центр» (раунд 15) — для соседей (R03 «ИИ-аналитик», R10): то же, что GET akim/board."""
    return default_service().board(district=district, now=now)


def week(date=None, district=None, now: datetime | None = None) -> dict:
    """«Картина недели» (раунд 15): то же, что GET akim/week?date."""
    return default_service().week(date=date, district=district, now=now)
