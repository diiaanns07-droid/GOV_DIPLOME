"""«Пульс района» (волна 2 п. 8): 1–5 тревог с причиной и ссылкой на карту.

МЕТОД — простой и объяснимый (без модели; R13 может заменить расчёт, сохранив формат тревоги):
  сообщение = жалоба или «Я тоже» (время нажатия из metoo_times; без времени — время жалобы).
  1. Всплеск (spike): по паре «категория × район» сообщений за последние 7 дней не меньше MIN_REPORTS
     и не меньше SPIKE_RATIO × обычного уровня. Обычный уровень — среднее за 4 предыдущие недели
     (берём только недели, за которые есть данные; меньше 2 недель — всплески не считаем: не с чем сравнить).
     Было 0 — «раньше такого не было» (spike_new), если сообщений не меньше MIN_REPORTS.
  2. Новое горячее место (new_hot): цель тепловой карты, о которой за 7 дней сообщили не меньше MIN_REPORTS
     человек, а неделю назад на карте её не было.
  3. Растёт «Я тоже» (metoo): у одной цели за 7 дней не меньше MIN_METOO_WEEK нажатий «Я тоже»
     и вдвое больше, чем за 7 дней до того (нужны времена нажатий metoo_times).
Одна тема всплеснула сразу в нескольких районах (снегопад) — одна тревога «по городу» со списком районов
(spike_city), а не пять одинаковых строк. Порядок — по силе сигнала (score), не больше MAX_ALARMS.
Не случайно ли (R13, research/round-14-results/R13/PULSE_METHOD.md): всплеск остаётся, только если при обычном уровне
такая неделя бывает реже чем в 1 случае из 100 (SURPRISE_P). Проверка учитывает, что «обычный уровень» сам посчитан
по 2–4 неделям: если всё как обычно, каждое из n = сейчас + сумма прошлых недель сообщений с равной вероятностью
попадает в любую из недель; P(в текущую ≥ сейчас) — биномиальная. Без неё на обычных неделях (синтетика R13, 72 пары
«район × тема») пульс показывал ~2,9 ложной тревоги в неделю, с ней ~0,3; всплеск ×5 находится в 90 % недель (было 95 %).
Тревога «по городу» остаётся, если неожиданна хотя бы в одном районе. Текст тревоги не меняется.
Ссылка: место на карте (у всплеска — самое горячее место этой категории в районе / в городе).
"""
from __future__ import annotations

from datetime import datetime, timedelta
import math

from . import text as T

WEEK = timedelta(days=7)
DAY = timedelta(days=1)
BASE_WEEKS = 4
MIN_BASE_WEEKS = 2
MIN_REPORTS = 5
SPIKE_RATIO = 2.0
MIN_METOO_WEEK = 8
MAX_ALARMS = 5
SURPRISE_P = 0.01


def _report_times(r: dict, parse_time) -> list[datetime]:
    created = parse_time(r.get("created_at"))
    out = [created]
    times = r.get("metoo_times")
    timed = []
    if isinstance(times, (list, tuple)):
        timed = [t for t in (parse_time(x) for x in times) if t is not None]
    try:
        metoo = int(r.get("metoo") or 0)
    except (TypeError, ValueError):
        metoo = 0
    out += timed + [created] * max(0, metoo - len(timed))
    return out


def alarms(records: list[dict], as_of: datetime, *, parse_time, district_of, categories: list[dict],
           district_names: dict, items_now: list[dict], items_prev: list[dict]) -> dict:
    """records — жалобы без дублей (уже в выбранном районе); items_now / items_prev — активные цели карты."""
    cats = {c["id"]: c for c in categories}
    oldest = min((parse_time(r.get("created_at")) for r in records), default=None)
    weeks = [k for k in range(1, BASE_WEEKS + 1) if oldest is not None and oldest <= as_of - WEEK * (k + 1) + DAY]
    counts: dict = {}
    for r in records:
        key = (r.get("category") if r.get("category") in cats else "other", district_of(r))
        if key[1] is None:
            continue
        for t in _report_times(r, parse_time):
            if t > as_of:
                continue
            k = int((as_of - t) / WEEK)  # 0 — последние 7 дней, 1..4 — недели раньше
            if k <= BASE_WEEKS:
                counts.setdefault(key, [0] * (BASE_WEEKS + 1))[k] += 1

    hottest: dict = {}
    for it in items_now:
        for cat in (it.get("by_category") or {}):
            hottest.setdefault((cat, it.get("district")), it)  # items уже по убыванию — первое и есть самое горячее

    out = []
    if len(weeks) >= MIN_BASE_WEEKS:
        for (cat, d_id), row in counts.items():
            cur = row[0]
            if cur < MIN_REPORTS:
                continue
            base = sum(row[k] for k in weeks) / len(weeks)
            if base == 0:
                kind, ratio, score = "spike_new", None, cur * 2.0
            elif cur >= SPIKE_RATIO * base:
                ratio = round(cur / base, 1)
                kind, score = "spike", cur * min(ratio, 5.0)
            else:
                continue
            out.append({"kind": kind, "category": cat, "district": d_id, "value": cur,
                        "base": round(base, 1), "ratio": ratio, "weeks": len(weeks), "score": score,
                        "target": _target(hottest.get((cat, d_id)))})
        out = [a for a in _merge_city(out, hottest) if _not_by_chance(a)]

    prev_ids = {(it["target"].get("kind"), it["target"].get("id")) for it in items_prev}
    for it in items_now:
        if int(it.get("count") or 0) >= MIN_REPORTS and (it["target"].get("kind"), it["target"].get("id")) not in prev_ids:
            cat = next(iter(it.get("by_category") or {}), None)
            out.append({"kind": "new_hot", "category": cat, "district": it.get("district"), "value": int(it["count"]),
                        "score": int(it["count"]) * 1.5, "target": _target(it)})

    labels = {it["target"].get("id"): it for it in items_now}
    metoo_by_target: dict = {}
    for r in records:
        tid = (r.get("target") or {}).get("id") if isinstance(r.get("target"), dict) else None
        times = r.get("metoo_times")
        if not tid or not isinstance(times, (list, tuple)):
            continue
        acc = metoo_by_target.setdefault(tid, [0, 0])
        for t in (parse_time(x) for x in times):
            if t is not None and as_of - WEEK < t <= as_of:
                acc[0] += 1
            elif t is not None and as_of - 2 * WEEK < t <= as_of - WEEK:
                acc[1] += 1
    for tid, (n, prev) in metoo_by_target.items():
        if n >= MIN_METOO_WEEK and n >= 2 * prev and tid in labels:
            it = labels[tid]
            cat = next(iter(it.get("by_category") or {}), None)
            out.append({"kind": "metoo", "category": cat, "district": it.get("district"), "value": n, "prev": prev,
                        "score": n * 1.5, "target": _target(it)})

    out.sort(key=lambda a: (-a["score"], a["kind"], str(a.get("category")), str(a.get("district"))))
    out = out[:MAX_ALARMS]
    for a in out:
        c = cats.get(a.get("category")) or {}
        d = district_names.get(a.get("district")) or {}
        a.update(category_ru=c.get("ru"), category_kk=c.get("kk"), district_ru=d.get("ru"), district_kk=d.get("kk"))
        for row in a.get("districts") or []:
            n = district_names.get(row["district"]) or {}
            row.update(ru=n.get("ru") or row["district"], kk=n.get("kk") or row["district"])
        # «×{k}» для экрана — с шагом 0,5 (R11 IA_WAVE2 §7): «×4», «×3,5», без ложной точности.
        a["k"] = max(1.0, round(a["ratio"] * 2) / 2) if a.get("ratio") else None
        a["text"] = {"ru": T.pulse_ru(a), "kk": T.pulse_kk(a)}
    return {"available": True, "items": out, "base_weeks": len(weeks),
            "method": {"min_reports": MIN_REPORTS, "spike_ratio": SPIKE_RATIO, "base_weeks": BASE_WEEKS,
                       "min_metoo_week": MIN_METOO_WEEK},
            "note": None if len(weeks) >= MIN_BASE_WEEKS else "too_little_history"}


def _surprise(value: int, base: float, weeks: int) -> float:
    """P(в текущей неделе ≥ value сообщений), если всё как обычно: биномиальная, n = value + base × weeks, q = 1/(weeks+1).

    Первый член — через логарифм гамма-функции, следующие — умножением; хвост дальше 1e-12 не считаем (быстро и при
    тысячах сообщений в неделю).
    """
    k, n = int(value), int(value) + int(round(base * weeks))
    q = 1.0 / (weeks + 1)
    if k <= 0:
        return 1.0
    term = math.exp(math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
                    + k * math.log(q) + (n - k) * math.log1p(-q))
    if term == 0.0:  # всплеск ≥ 2 × обычного: члены дальше только убывают — хвост тоже ≈ 0
        return 0.0
    total, ratio = term, q / (1 - q)
    for i in range(k + 1, n + 1):
        term *= (n - i + 1) / i * ratio
        total += term
        if term < 1e-12 * total:
            break
    return min(1.0, total)


def _not_by_chance(a: dict) -> bool:
    if a["kind"] == "spike_city":
        return any(_surprise(r["value"], r["value"] / r["ratio"] if r.get("ratio") else 0.0, a["weeks"]) <= SURPRISE_P
                   for r in a["districts"])
    return _surprise(a["value"], a.get("base") or 0.0, a["weeks"]) <= SURPRISE_P


def _merge_city(spikes: list[dict], hottest: dict) -> list[dict]:
    """Всплески одной темы в 2+ районах → одна тревога spike_city (районы — по силе, первые 3 в тексте)."""
    by_cat: dict = {}
    for a in spikes:
        by_cat.setdefault(a["category"], []).append(a)
    out = []
    for cat, group in by_cat.items():
        if len(group) < 2:
            out += group
            continue
        group.sort(key=lambda a: -a["score"])
        top = group[0]
        cur, base = sum(a["value"] for a in group), sum(a["base"] for a in group)
        out.append({"kind": "spike_city", "category": cat, "district": None, "value": cur,
                    "base": round(base, 1), "ratio": round(cur / base, 1) if base else None, "weeks": top["weeks"],
                    "score": sum(a["score"] for a in group),
                    # районы — по числу сообщений («больше всего: Нура — 41, …»)
                    "districts": [{"district": a["district"], "value": a["value"], "ratio": a["ratio"]}
                                  for a in sorted(group, key=lambda a: (-a["value"], a["district"]))],
                    "target": top["target"]})
    return out


def _target(it: dict | None) -> dict | None:
    if not it:
        return None
    t = it["target"]
    return {"kind": t.get("kind"), "id": t.get("id"), "label_ru": t.get("label_ru"), "label_kk": t.get("label_kk")}
