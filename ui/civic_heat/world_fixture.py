"""Мини-мир R07 — фикстура в формате демо-мира R02 (SCHEMA birge-demo-world-v1 1.1). ВСЁ синтетическое.

    python -m ui.civic_heat.world_fixture            # сводка
    python -m ui.civic_heat.world_fixture --write    # fixtures/world_r07_mini.json

Зачем: тесты «Хроники» и стенд R07 (devserver --world) без файла R02 — неделя бурана в Нуре (6–3 дня назад): снег
копится три дня, город краснеет, службы чистят, места зеленеют и остывают. Формат — как world_v1.json R02:
время — объекты относительного времени ({"ago_hours": 30.5}, SCHEMA §1), жалоба — запись R09 (§2.3: created_at,
status_history[].at, metoo_times, resolution), событие мира «Буран в Нуре» (events, §2.1), кризисный штаб о нём
(incidents, §2.8: event, closed_at), сцена 9 (scenes). Настоящий мир R02 читается тем же кодом (world.materialize).
Цели — настоящие объекты OSM из fixtures/targets_demo.json (те же, что у демо-набора R07).
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from . import demo_seed
from .engine import ASTANA_TZ
from .world import materialize

HERE = Path(__file__).resolve().parent
OUT_PATH = HERE / "fixtures" / "world_r07_mini.json"
SEED = 15
BLIZZARD_HOURS = (6 * 24 + 6, 3 * 24 + 4)   # буран: начался и кончился (часов назад)
EVENT = {"id": "ev-r07-buran", "kind": "blizzard", "title_ru": "Буран в Нуре", "title_kk": "Нұрада боран", "district": "nura",
         "started_at": {"ago_hours": BLIZZARD_HOURS[0]}, "ended_at": {"ago_hours": BLIZZARD_HOURS[1]}, "demo": True}
BLIZZARD = {"id": "inc-r07-blizzard-nura", "kind": "blizzard", "title_ru": "Буран", "title_kk": "Боран",
            "zone": {"kind": "district", "district": "nura", "targets": [], "geometry": None},
            "started_at": {"ago_hours": BLIZZARD_HOURS[0] - 4}, "status": "closed", "closed_at": {"ago_hours": BLIZZARD_HOURS[1] - 20},
            "tasks": [], "updates": [], "result": {"text_ru": "Дороги и дворы расчищены", "text_kk": "Жолдар мен аулалар тазартылды"},
            "event": EVENT["id"], "demo": True}
TEXTS = {
    "snow_ice": [("Дорогу замело, машины буксуют", "ru"), ("Жол қарға толды, көлік өтпейді", "kk"),
                 ("Во дворе сугробы по колено, не выйти", "ru"), ("Аялдамада қар тазартылмаған", "kk")],
    "roads": [("Яма на дороге после раскопок", "ru"), ("Жолда шұңқыр бар", "kk")],
    "transport": [("Автобус не ходит по расписанию", "ru"), ("Аялдамада автобус жоқ", "kk")],
    "yards": [("Во дворе сломана лавочка", "ru"), ("Аулада балалар алаңы бұзылған", "kk")],
    "lighting": [("Не горит фонарь у остановки", "ru"), ("Көше шамы жанбайды", "kk")],
    "other": [("Проблема во дворе", "ru"), ("Аулада мәселе бар", "kk")],
}
ROLE_CATEGORY = {"snow": "snow_ice", "city_snow": "snow_ice", "roads": "roads", "city_roads": "roads",
                 "transport": "transport", "city_stop": "transport", "yards": "yards", "city_yard": "yards",
                 "playground": "yards", "lighting": "lighting", "sidewalks": "roads", "parking": "other",
                 "smell_air": "other", "utilities": "other", "waste": "other", "waste_site": "other", "signal": "roads",
                 "city_crossroads": "roads", "city_zebra": "roads"}


def _h(x: float) -> dict:
    return {"ago_hours": round(float(x), 2)}


def _complaint(cid: str, ago_h: float, category: str, text: str, lang: str, point, target: dict, district,
               rnd: random.Random, *, fixed_after_h=None, verify=None, metoo=0, event=None) -> dict:
    """Жалоба в формате мира R02 (§2.3): история статусов, «Я тоже», раунд ремонта — время-объекты от засева."""
    hist = [{"at": _h(ago_h), "status": "new"}]
    status, res = "new", None
    if fixed_after_h is not None and ago_h - fixed_after_h > 0.5:
        acc = ago_h - min(6.0, fixed_after_h * 0.3)
        fixed_h = ago_h - fixed_after_h
        hist += [{"at": _h(acc), "status": "accepted"}, {"at": _h((acc + fixed_h) / 2), "status": "in_progress"},
                 {"at": _h(fixed_h), "status": "fixed"}]
        status = "fixed"
        res = {"round": 1, "state": "reported", "reported_at": _h(fixed_h), "votes": {"yes": 0, "no": 0, "cant": 0},
               "verified_at": None, "reopened_at": None, "photos_after": []}
        if verify == "yes" and fixed_h > 6:
            res.update(state="verified", verified_at=_h(fixed_h - 5), votes={"yes": 1, "no": 0, "cant": 0})
        elif verify == "no" and fixed_h > 8:
            res.update(state="reopened", reopened_at=_h(fixed_h - 7), votes={"yes": 0, "no": 1, "cant": 0})
            hist.append({"at": _h(fixed_h - 7), "status": "in_progress", "reopened_by_residents": True})
            status = "in_progress"
    elif ago_h > 30 and rnd.random() < 0.5:
        hist.append({"at": _h(ago_h - 20), "status": "accepted"})
        status = "accepted"
    me = sorted((round(ago_h - rnd.uniform(0.2, min(ago_h - 0.1, 30)), 2) for _ in range(metoo)), reverse=True)
    me = [m for m in me if m > 0]
    return {"id": cid, "schema": "civic-complaint-v2", "created_at": _h(ago_h), "text": text, "lang": lang,
            "category": category, "subtopic": None, "category_source": "resident", "model": None,
            "point": point, "target": target, "district": district, "status": status, "status_history": hist,
            "metoo": len(me), "metoo_times": [_h(m) for m in me], "duplicate_of": None, "demo": True,
            "resolution": res, "event": event}


def build_world(seed: int = SEED) -> dict:
    """Детерминированный мини-мир: ~40 дней фона + буран в Нуре (6–3 дня назад) + чистка после: «Хроника» за 7 дней
    показывает спокойный день, буран, чистку и «сегодня»."""
    rnd = random.Random(seed)
    targets = demo_seed.load_targets()
    ids = sorted(targets)
    complaints = []

    def add(tid, ago_h, category, **kw):
        t = targets[tid]
        text, lang = rnd.choice(TEXTS.get(category) or TEXTS["other"])
        complaints.append(_complaint(f"c-w07{len(complaints) + 1:04d}", ago_h, category, text, lang, _point(t, rnd),
                                     {"kind": t["kind"], "id": tid}, t.get("district"), rnd, **kw))

    # Фон: 40 дней, по 1–4 жалобы в день на разные цели; старое чинят за 2–6 дней, часть проверяют жители.
    for day in range(40, 0, -1):
        for _ in range(rnd.randint(1, 4)):
            tid = rnd.choice(ids)
            cat = ROLE_CATEGORY.get(targets[tid]["role"], "other")
            if cat == "snow_ice":
                cat = "roads" if targets[tid]["kind"] == "segment" else "yards"
            ago = day * 24 - rnd.uniform(0, 23)
            fix = rnd.uniform(40, 140) if day > 3 and rnd.random() < 0.75 else None
            add(tid, ago, cat, fixed_after_h=fix, verify=rnd.choice(["yes", "yes", None]), metoo=rnd.choice([0, 0, 1, 2]))
    # Буран в Нуре: 3 дня, снег на улицах, во дворах и на остановках Нуры (и меньше — в других районах).
    start_h, end_h = BLIZZARD_HOURS
    nura = [tid for tid in ids if targets[tid].get("district") == "nura"]
    other = [tid for tid in ids if targets[tid].get("district") != "nura"]
    for i in range(70):
        tid = nura[i % len(nura)] if i < 56 else rnd.choice(other)
        ago = rnd.uniform(end_h, start_h)
        # Чистка — через 1–3 дня после бурана; несколько мест жители «вернули» (снег остался).
        fix_at = rnd.uniform(end_h - 70, end_h - 18)
        verify = "no" if i in (5, 23) else rnd.choice(["yes", "yes", None])
        add(tid, ago, "snow_ice", fixed_after_h=ago - fix_at, verify=verify, metoo=rnd.choice([0, 1, 2, 3]),
            event=EVENT["id"] if targets[tid].get("district") == "nura" else None)
    # Сегодня и вчера — свежие жалобы (карта «сегодня» не пустая).
    for _ in range(12):
        tid = rnd.choice(ids)
        add(tid, rnd.uniform(1, 40), ROLE_CATEGORY.get(targets[tid]["role"], "other"), metoo=rnd.choice([0, 1]))
    return {
        "schema": "birge-demo-world-v1", "schema_version": "1.1", "seed": seed, "synthetic": True,
        "note": "Мини-мир R07 для тестов и стенда (не мир R02).",
        "events": [dict(EVENT)], "complaints": complaints, "incidents": [dict(BLIZZARD)],
        "scenes": {"scene9": {"incident": BLIZZARD["id"], "event": EVENT["id"], "district": "nura"}},
    }


def city_world(n_targets: int = 1000, n_complaints: int = 2500, seed: int = 7) -> dict:
    """Большой синтетический город для замера плавности «Хроники» (1 000 целей): ячейки ~150 м по всей Астане,
    40 дней фона, буран в Нуре (как в build_world). Только для стенда и тестов скорости — не демо."""
    from . import geo

    rnd = random.Random(seed)
    bbox = (71.30, 51.05, 71.60, 51.25)
    cells: dict = {}
    while len(cells) < n_targets:
        pt = [round(rnd.uniform(bbox[0], bbox[2]), 6), round(rnd.uniform(bbox[1], bbox[3]), 6)]
        d = geo.district_of(pt)
        if d:
            cells.setdefault(geo.cell_id_for(pt), (pt, d))
    ids = sorted(cells)
    nura = [c for c in ids if cells[c][1] == "nura"]
    start_h, end_h = BLIZZARD_HOURS
    complaints = []
    for i in range(n_complaints):
        blizzard = bool(i % 4 == 0 and nura)
        cid = rnd.choice(nura) if blizzard else rnd.choice(ids)
        pt, d = cells[cid]
        ago = rnd.uniform(end_h, start_h) if blizzard else rnd.uniform(1, 40 * 24)
        fix = (ago - rnd.uniform(end_h - 70, end_h - 18)) if blizzard else (rnd.uniform(40, 140) if ago > 72 and rnd.random() < 0.75 else None)
        complaints.append(_complaint(f"c-city{i:05d}", ago, "snow_ice" if blizzard else rnd.choice(["roads", "yards", "transport", "lighting"]),
                                     "Пример", "ru", pt, {"kind": "area", "id": cid}, d, rnd, fixed_after_h=fix,
                                     event=EVENT["id"] if blizzard else None))
    return {"schema": "birge-demo-world-v1", "schema_version": "1.1", "synthetic": True,
            "note": "Синтетика R07 для замера плавности (не мир R02).", "events": [dict(EVENT)],
            "complaints": complaints, "incidents": [dict(BLIZZARD)], "scenes": {"scene9": {"incident": BLIZZARD["id"], "event": EVENT["id"]}}}


def _point(t: dict, rnd: random.Random) -> list[float]:
    return demo_seed._point_on(t["geometry"], rnd)


def to_records(world: dict, now: datetime | None = None) -> list[dict]:
    """Жалобы мира → записи v2 с абсолютным временем от now (как их сохранил бы R09.seed_world)."""
    now = (now or datetime.now(timezone.utc)).astimezone(ASTANA_TZ)
    return [dict(materialize(c, now)) for c in world.get("complaints") or []]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    world = build_world()
    recs = to_records(world)
    print(f"жалоб {len(recs)}, людей {sum(1 + r['metoo'] for r in recs)}, событие — {world['events'][0]['title_ru']}")
    if args.write:
        OUT_PATH.write_text(json.dumps(world, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print("записано", OUT_PATH)


if __name__ == "__main__":
    main()
