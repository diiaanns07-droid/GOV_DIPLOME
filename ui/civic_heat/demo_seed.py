"""Демо-набор жалоб для тепловой карты — ВСЕ записи синтетические (demo: true).

    python -m ui.civic_heat.demo_seed            # сводка набора
    python -m ui.civic_heat.demo_seed --write    # сохранить fixtures/demo_complaints.json (якорь 2026-10-11 12:00)

Цели — настоящие участки улиц, кварталы и остановки из fixtures/targets_demo.json (собраны из OSM).
Тексты, люди, время и статусы придуманы. Формат записи — CONTRACT §5 (v2).
Набор детерминированный: при одном seed и одном now — те же записи. Возраст жалоб задаётся
относительно now, поэтому в день показа карта выглядит так же «свежо», как при разработке.
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
DEFAULT_SEED = 20261011
ANCHOR = datetime(2026, 10, 11, 12, 0, tzinfo=ASTANA_TZ)

# Роль цели → (категория, сколько жалоб у целей этой роли по порядку, максимальный возраст в днях).
# Числа подобраны так, чтобы на карте были все 4 уровня: снег в Нуре — свежий и плотный,
# дороги — старые и «остывшие», одна остановка уже исправлена.
CLUSTERS = {
    "snow": ("snow_ice", [9, 6, 5, 4, 3, 2, 1], 5),
    "roads": ("roads", [5, 3, 2], 45),
    "sidewalks": ("sidewalks", [3, 2], 20),
    "lighting": ("lighting", [4, 2, 2], 14),
    "parking": ("parking", [3, 2, 1], 25),
    "yards": ("yards", [5, 3, 2], 20),
    "waste": ("waste", [4, 2], 10),
    "utilities": ("utilities", [4], 6),
    "smell_air": ("smell_air", [5, 3, 2], 8),
    "transport": ("transport", [8, 4, 3, 2], 12),
    "city_snow": ("snow_ice", [4, 3, 2, 2, 1], 6),
    "city_roads": ("roads", [2, 2, 1, 1, 1], 40),
}

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


def demo_records(now: datetime | None = None, seed: int = DEFAULT_SEED, targets: dict | None = None) -> list[dict]:
    now = (now or datetime.now(timezone.utc)).astimezone(ASTANA_TZ)
    targets = targets or load_targets()
    rnd = random.Random(seed)
    by_role: dict = {}
    for tid in sorted(targets):
        by_role.setdefault(targets[tid]["role"], []).append(tid)

    records = []
    n = 0
    for role in sorted(CLUSTERS):
        category, counts, max_age = CLUSTERS[role]
        for idx, tid in enumerate(by_role.get(role, [])[: len(counts)]):
            t = targets[tid]
            # Особые случаи, чтобы показать все состояния карточки:
            fixed_case = role == "transport" and idx == 2            # остановка исправлена 2 дня назад → зелёная
            in_progress_case = role == "snow" and idx == 1           # участок со снегом уже «в работе»
            accepted_case = role == "yards" and idx == 0             # двор: обращение принято
            for k in range(counts[idx]):
                n += 1
                lang, text = TEXTS[category][rnd.randrange(len(TEXTS[category]))]
                if fixed_case:
                    age_days = rnd.uniform(4, 12)
                elif role == "roads":
                    age_days = rnd.uniform(20, max_age)                  # старые жалобы — «остывшая» цель
                else:
                    age_days = rnd.triangular(0.02, max_age, 0.3)        # больше всего свежих
                created = now - timedelta(days=age_days)
                history = [{"at": iso(created), "status": "new"}]
                status = "new"
                if fixed_case:
                    fixed_time = now - timedelta(days=2)
                    history += [{"at": iso(created + timedelta(hours=6)), "status": "accepted"},
                                {"at": iso(fixed_time - timedelta(days=1)), "status": "in_progress"},
                                {"at": iso(fixed_time), "status": "fixed"}]
                    status = "fixed"
                elif in_progress_case:
                    history += [{"at": iso(min(now, created + timedelta(hours=3))), "status": "accepted"},
                                {"at": iso(min(now, created + timedelta(hours=8))), "status": "in_progress"}]
                    status = "in_progress"
                elif accepted_case:
                    history.append({"at": iso(min(now, created + timedelta(hours=5))), "status": "accepted"})
                    status = "accepted"
                score = round(rnd.uniform(0.62, 0.97), 2)
                metoo = rnd.choice((0, 0, 0, 1, 1, 2, 3)) if k < 3 else rnd.choice((0, 0, 1))
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
                    "status_history": history,
                    "metoo": metoo,
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
