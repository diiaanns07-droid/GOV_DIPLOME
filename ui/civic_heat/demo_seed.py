"""Демо-набор жалоб для тепловой карты — ВСЕ записи синтетические (demo: true).

    python -m ui.civic_heat.demo_seed            # сводка набора
    python -m ui.civic_heat.demo_seed --write    # сохранить fixtures/demo_complaints.json (якорь 2026-10-11 12:00)

Цели — настоящие объекты OSM из fixtures/targets_demo.json: участки улиц, остановки, дворы жилых комплексов,
детские и контейнерные площадки (LOCAL-1); ячейки ~150 м — только для «запахов».
Тексты, люди, время и статусы придуманы. Формат записи — CONTRACT §5 (v2).
Набор детерминированный: при одном seed и одном now — те же записи. Возраст жалоб задаётся
относительно now, поэтому в день показа карта выглядит так же «свежо», как при разработке.
История — 3 недели с работой акимата (старое закрыто, свежее открыто), чтобы «Картина дня» R08
показывала правдоподобные числа: неделя к неделе сопоставимо, просроченных немного.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import geo
from .engine import ASTANA_TZ, iso

HERE = Path(__file__).resolve().parent
TARGETS_PATH = HERE / "fixtures" / "targets_demo.json"
OUT_PATH = HERE / "fixtures" / "demo_complaints.json"
DEFAULT_SEED = 20261014   # выбран tests/civic/R07/tune_demo_seed.py: все критерии правдоподобия (см. там)
ANCHOR = datetime(2026, 10, 11, 12, 0, tzinfo=ASTANA_TZ)

HORIZON_DAYS = 35   # демо-история — 5 недель: первые две — «разгон», последние две сравнивает «Картина дня»

# Роль цели → (категория, сколько жалоб за 3 недели у целей этой роли по порядку, форма потока).
# Формы: steady — ровно за 3 недели; snow — два снегопада (сейчас и ровно неделю назад); recent — последние 5 дней.
CLUSTERS = {
    "snow": ("snow_ice", [19, 8, 3, 3, 2, 2, 2], "snow"),
    "roads": ("roads", [7, 3, 2], "steady"),
    "sidewalks": ("sidewalks", [3, 2], "steady"),
    "lighting": ("lighting", [4, 3, 2], "steady"),
    "parking": ("parking", [3, 2, 2], "steady"),
    "yards": ("yards", [5, 3, 2], "steady"),
    "waste": ("waste", [4], "steady"),
    "utilities": ("utilities", [3], "recent"),
    "smell_air": ("smell_air", [7, 3, 2], "recent"),
    "transport": ("transport", [12, 5, 5, 3, 2], "steady"),
    "playground": ("yards", [4, 3], "steady"),          # реальные детские площадки OSM
    "waste_site": ("waste", [4, 3], "steady"),           # реальные контейнерные площадки OSM
    "city_snow": ("snow_ice", [18, 17, 17, 16, 16], "snow"),
    "city_roads": ("roads", [18, 17, 16, 15, 14], "steady"),
    "city_stop": ("transport", [22, 21, 20, 19, 19], "steady"),
    "city_yard": ("yards", [20, 19, 19, 18, 18], "steady"),
}

# Через сколько дней акимат обычно закрывает жалобу категории — по смыслу из демо-норматива «Картины дня»
# (R08, ui/civic_akim/deadlines.py): закрываем чуть раньше срока, поэтому «просрочено» — немного.
# Числа CLUSTERS и FIX_LAG_DAYS проверены кодом R08: tests/civic/R07/tune_demo_seed.py.
FIX_LAG_DAYS = {"roads": 6, "snow_ice": 1.6, "sidewalks": 8, "transport": 4, "lighting": 2.5, "yards": 11,
                "waste": 1.6, "utilities": 0.8, "smell_air": 2.5, "noise_safety": 2.5, "parking": 11, "other": 8}
# Цели, где акимат не успевает: здесь и только здесь будут просроченные жалобы (≈ 5–8 на город).
LATE = {("transport", 0), ("roads", 0), ("lighting", 0), ("city_stop", 1), ("city_roads", 0), ("city_yard", 2)}
# Горячие места: к свежим жалобам здесь присоединяется много людей («Я тоже»). Число ОБРАЩЕНИЙ (его считает
# «Картина дня») от этого не растёт, а цель на карте краснеет — как на демо: снег, остановка, запахи, двор.
HOT = {("snow", 0), ("transport", 0), ("smell_air", 0),
       ("city_snow", 0), ("city_stop", 0), ("city_stop", 1), ("city_yard", 0), ("city_yard", 1)}
# Ещё две цели отремонтированы и стоят зелёными (кроме остановки transport/2): пример «исправлено» на карте.
CALM = {("roads", 2), ("city_roads", 4)}

TEXTS = {
    "snow_ice": [("ru", "Не убран снег на тротуаре, очень скользко"), ("kk", "Тротуардағы қар тазаланбаған, өте тайғақ"),
                 ("ru", "Гололёд у перехода, люди падают"), ("mixed", "Қар тазаланбаған, пройти невозможно"),
                 ("kk", "Көктайғақ, балалар мектепке әрең барады")],
    "roads": [("ru", "Большая яма на дороге, машины объезжают"), ("kk", "Жолда үлкен шұңқыр бар"),
              ("ru", "Разбитый асфальт после ремонта")],
    "sidewalks": [("ru", "Разбит тротуар, с коляской не пройти"), ("kk", "Жаяу жүргіншілер жолы бұзылған")],
    "transport": [("ru", "Сломан павильон остановки, нет скамейки"), ("kk", "Аялдамада кесте жоқ, автобус сирек келеді"),
                  ("mixed", "Аялдама шатыры сынған, под дождём стоим")],
    "lighting": [("ru", "Не горят фонари, вечером темно"), ("kk", "Ауладағы шамдар жанбайды, кешке қараңғы")],
    "yards": [("ru", "Сломана детская площадка во дворе"), ("kk", "Ауладағы балалар алаңы сынған"),
              ("ru", "Во дворе вырубили деревья")],
    "waste": [("ru", "Переполнены мусорные баки, не вывозят"), ("kk", "Қоқыс шығарылмайды, жәшіктер толы")],
    "utilities": [("ru", "В доме нет горячей воды третий день"), ("kk", "Үйде жылу жоқ, пәтер суық")],
    "smell_air": [("ru", "Сильный запах гари по вечерам"), ("kk", "Кешке түтін иісі қатты шығады"),
                  ("mixed", "Иіс өте қатты, окна не открыть")],
    "parking": [("ru", "Машины паркуются на газоне"), ("kk", "Аулада көлік қоятын орын жоқ")],
}


def load_targets(path: Path = TARGETS_PATH) -> dict:
    return json.loads(Path(path).read_text("utf-8"))["targets"]


def _point_on(geometry: dict, rnd: random.Random) -> list[float]:
    """Точка жалобы рядом с целью: на линии участка, внутри квартала или в 5–15 м от остановки."""
    t = geometry["type"]
    c = geometry["coordinates"]
    if t == "Point":
        ang = rnd.uniform(0, 2 * math.pi)
        dist = rnd.uniform(5, 15)
        return [round(c[0] + dist * math.cos(ang) / (111320 * math.cos(math.radians(c[1]))), 6),
                round(c[1] + dist * math.sin(ang) / 110574, 6)]
    if t == "LineString":
        i = rnd.randrange(len(c) - 1)
        f = rnd.random()
        return [round(c[i][0] + (c[i + 1][0] - c[i][0]) * f, 6), round(c[i][1] + (c[i + 1][1] - c[i][1]) * f, 6)]
    ring = c[0]
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    for _ in range(50):
        p = [rnd.uniform(min(xs), max(xs)), rnd.uniform(min(ys), max(ys))]
        if geo.point_in_ring(p, ring):
            return [round(p[0], 6), round(p[1], 6)]
    return [round(v, 6) for v in geo.anchor_of(geometry)]


def _ages(shape: str, n: int, rnd: random.Random) -> list[float]:
    """Возраст жалоб в днях — ровный поток за 3 недели (неделя к неделе сопоставимо по построению).
    snow: два одинаковых снегопада — сейчас и ровно неделю назад — плюс фон; recent: последние 6 дней."""
    out = []
    for i in range(n):
        if shape == "snow":
            r = i % 5
            out.append(rnd.uniform(0.05, 1.8) if r in (0, 2) else rnd.uniform(7.05, 8.8) if r in (1, 3) else rnd.uniform(0.05, HORIZON_DAYS))
        elif shape == "recent":
            out.append(rnd.uniform(0.05, 6.0))
        else:
            out.append(rnd.uniform(0.05, HORIZON_DAYS))
    return sorted(out, reverse=True)          # от старых к новым


def _repairs(created: list[datetime], lag: float, late: bool, now: datetime, rnd: random.Random) -> list[datetime | None]:
    """Когда закрыта каждая жалоба. Каждой назначен срок lag × 0.5–1.0; ремонт в этот момент закрывает ВСЕ
    открытые жалобы цели, пришедшие раньше (одна яма — один ремонт). None — ещё открыта.
    late: у этой цели акимат хронически не успевает (срок × 2–3) — отсюда «просрочено» в «Картине дня»,
    и сегодня, и неделю назад одинаково (≈ 5–8 на город)."""
    due = [c + timedelta(days=lag * (rnd.uniform(2.0, 3.0) if late else rnd.uniform(0.5, 1.0))) for c in created]
    closed: list = [None] * len(created)
    for i in sorted(range(len(created)), key=lambda k: due[k]):
        if closed[i] is not None or due[i] > now:
            continue
        for j in range(len(created)):
            if closed[j] is None and created[j] <= due[i]:
                closed[j] = due[i]
    return closed


def _history(created: datetime, end_status: str, fixed_time: datetime | None, now: datetime, rnd: random.Random) -> list:
    hist = [{"at": iso(created), "status": "new"}]
    if end_status == "new":
        return hist
    accepted = min(now, created + timedelta(hours=rnd.uniform(1, 8)))
    hist.append({"at": iso(accepted), "status": "accepted"})
    if end_status == "accepted":
        return hist
    work = min(now, accepted + timedelta(hours=rnd.uniform(2, 20)))
    if fixed_time is not None:
        work = min(work, fixed_time - timedelta(hours=1))
    hist.append({"at": iso(max(work, accepted)), "status": "in_progress"})
    if end_status == "fixed":
        hist.append({"at": iso(fixed_time), "status": "fixed"})
    return hist


def demo_records(now: datetime | None = None, seed: int = DEFAULT_SEED, targets: dict | None = None) -> list[dict]:
    """Поток жалоб за 3 недели + работа акимата: старые жалобы у цели закрываются одним ремонтом
    (статус fixed у всех, кто пришёл до него), свежие — открыты. Поэтому на карте горят свежие места,
    «неделю назад» сопоставимо с «сейчас», а просроченных немного (только цели из LATE)."""
    now = (now or datetime.now(timezone.utc)).astimezone(ASTANA_TZ)
    targets = targets or load_targets()
    rnd = random.Random(seed)
    by_role: dict = {}
    for tid in sorted(targets):
        by_role.setdefault(targets[tid]["role"], []).append(tid)

    records = []
    n = 0
    for role in sorted(CLUSTERS):
        category, counts, shape = CLUSTERS[role]
        lag = FIX_LAG_DAYS.get(category, 8)
        for idx, tid in enumerate(by_role.get(role, [])[: len(counts)]):
            t = targets[tid]
            fixed_case = role == "transport" and idx == 2        # остановка исправлена 2 дня назад → зелёная
            in_progress_case = role == "snow" and idx == 1       # участок со снегом уже «в работе»
            accepted_case = role == "yards" and idx == 0         # двор: обращение принято
            calm = fixed_case or (role, idx) in CALM
            ages = _ages(shape, counts[idx], rnd)
            if calm:
                # отремонтировано недавно, новых жалоб после ремонта нет → 7 дней зелёная «исправлено»
                repair_age = 2.0 if fixed_case else 3.0
                ages = sorted((rnd.uniform(repair_age + 0.5, repair_age + 9) for _ in ages), reverse=True)
            created_list = [now - timedelta(days=a) for a in ages]
            if calm:
                closes = [now - timedelta(days=repair_age)] * len(created_list)
            else:
                closes = _repairs(created_list, lag, (role, idx) in LATE, now, rnd)
                if all(c is not None for c in closes) and rnd.random() < 0.85:
                    # У большинства мест после последнего ремонта уже кто-то снова написал: карта не «вся зелёная».
                    created_list[-1] = now - timedelta(days=rnd.uniform(0.05, min(lag * 0.5, 2.0)))
                    closes = _repairs(created_list, lag, (role, idx) in LATE, now, rnd)
            for k, (created, own_fix) in enumerate(zip(created_list, closes)):
                n += 1
                age = (now - created).total_seconds() / 86400
                lang, text = TEXTS[category][rnd.randrange(len(TEXTS[category]))]
                if own_fix is not None:
                    status = "fixed"
                elif in_progress_case:
                    status = "in_progress"
                elif accepted_case or age > 0.5:
                    status = "accepted" if rnd.random() < 0.7 else "in_progress"
                else:
                    status = "new"
                score = round(rnd.uniform(0.62, 0.97), 2)
                if (role, idx) in HOT:
                    metoo = rnd.choice((1, 2, 2, 3, 3, 4))
                else:
                    metoo = rnd.choice((0, 0, 0, 1, 1, 2)) if k % 3 == 0 else rnd.choice((0, 0, 1))
                # «Я тоже» приходят в первые полсуток после жалобы (и не позже ремонта / сейчас)
                limit = min(now, own_fix) if own_fix is not None else now
                span = max(0.0, min((limit - created).total_seconds(), 12 * 3600))
                metoo_times = sorted(iso(created + timedelta(seconds=rnd.uniform(0, span))) for _ in range(metoo))
                records.append({
                    "id": f"c-demo-{n:04d}",
                    "created_at": iso(created),
                    "text": text,
                    "lang": lang,
                    "category": category,
                    "category_source": "model",
                    "model": {"label": category, "score": score, "version": "demo-synthetic", "needs_review": score < 0.7},
                    "point": _point_on(t["geometry"], rnd),
                    "target": {"kind": t["kind"], "id": tid},
                    "district": t.get("district"),
                    "status": status,
                    "status_history": _history(created, status, own_fix, now, rnd),
                    "metoo": metoo,
                    "metoo_times": metoo_times,
                    "duplicate_of": None,
                    "demo": True,
                })
    records.sort(key=lambda r: r["created_at"])
    return records


def add_demo_complaint(records: list, target_id: str, *, now: datetime | None = None, targets: dict | None = None,
                       category: str | None = None) -> dict:
    """Новая демо-жалоба на цель (для показа пульса на защите). Возвращает запись."""
    now = (now or datetime.now(timezone.utc)).astimezone(ASTANA_TZ)
    targets = targets or load_targets()
    t = targets[target_id]
    cat = category or CLUSTERS.get(t["role"], ("other",))[0]
    rnd = random.Random(f"{target_id}-{len(records)}")
    lang, text = TEXTS.get(cat, [("ru", "Новая жалоба")])[0]
    rec = {
        "id": f"c-demo-live-{len(records) + 1:04d}", "created_at": iso(now), "text": text, "lang": lang,
        "category": cat, "category_source": "resident", "model": None, "point": _point_on(t["geometry"], rnd),
        "target": {"kind": t["kind"], "id": target_id}, "district": t.get("district"), "status": "new",
        "status_history": [{"at": iso(now), "status": "new"}], "metoo": 0, "duplicate_of": None, "demo": True,
    }
    records.append(rec)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description="Демо-набор жалоб R07 (synthetic)")
    ap.add_argument("--write", action="store_true", help="записать fixtures/demo_complaints.json")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args(argv)
    recs = demo_records(now=ANCHOR, seed=args.seed)
    people = sum(1 + r["metoo"] for r in recs)
    print(f"жалоб: {len(recs)}, людей с «Я тоже»: {people}, целей: {len({r['target']['id'] for r in recs})}")
    if args.write:
        OUT_PATH.write_text(json.dumps({"_meta": {"synthetic": True, "anchor": iso(ANCHOR), "seed": args.seed,
                                                  "note": "Все жалобы придуманы (demo: true). Цели — реальные объекты OSM."},
                                        "records": recs}, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print("записано:", OUT_PATH)


if __name__ == "__main__":
    main()
