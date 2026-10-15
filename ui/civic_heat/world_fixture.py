"""Мини-мир R07 — фикстура в духе демо-мира R02 (CONTRACT §11), пока world_v1.json не готов. ВСЁ синтетическое.

    python -m ui.civic_heat.world_fixture            # сводка
    python -m ui.civic_heat.world_fixture --write    # fixtures/world_r07_mini.json

Зачем: тесты «Хроники» и стенд R07 (devserver --world) — неделя бурана в Нуре: снег копится три дня, город краснеет,
службы чистят, места зеленеют и остывают. Время — относительно засева (ago_hours), как в мире R02.
Цели — настоящие объекты OSM из fixtures/targets_demo.json (те же, что у демо-набора R07).

Формат жалобы мира (наше понимание SCHEMA R02; при расхождении правится только to_records):
    {"id", "ago_hours", "category", "text", "lang", "point", "target", "district", "status",
     "status_history": [{"status", "ago_hours"}], "metoo_ago_hours": [..], "resolution": {"state", "reported_ago_hours",
     "verified_ago_hours" | "reopened_ago_hours", "votes"} | null, "demo": true}
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import demo_seed
from .engine import ASTANA_TZ, iso

HERE = Path(__file__).resolve().parent
OUT_PATH = HERE / "fixtures" / "world_r07_mini.json"
SEED = 15
BLIZZARD = {"id": "inc-r07-blizzard-nura", "kind": "blizzard", "title_ru": "Буран", "title_kk": "Боран",
            "zone": {"kind": "district", "district": "nura", "targets": [], "geometry": None},
            "started_ago_hours": 8 * 24 + 6, "ended_ago_hours": 5 * 24 + 4, "status": "closed",
            "tasks": [], "updates": [], "result": {"text_ru": "Дороги и дворы расчищены", "text_kk": "Жолдар мен аулалар тазартылды"},
            "demo": True}
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


def _point(t: dict, rnd: random.Random) -> list[float]:
    return demo_seed._point_on(t["geometry"], rnd)


def build_world(seed: int = SEED) -> dict:
    """Детерминированный мини-мир: ~40 дней фона + буран в Нуре (8–5 дней назад) + чистка после."""
    rnd = random.Random(seed)
    targets = demo_seed.load_targets()
    ids = sorted(targets)
    complaints = []
    n = 0

    def add(tid, ago_h, category, *, fixed_after_h=None, verify=None, metoo=0):
        nonlocal n
        t = targets[tid]
        n += 1
        text, lang = rnd.choice(TEXTS.get(category) or TEXTS["other"])
        hist = [{"status": "new", "ago_hours": round(ago_h, 2)}]
        status = "new"
        res = None
        if fixed_after_h is not None and ago_h - fixed_after_h > 0.5:
            acc = ago_h - min(6.0, fixed_after_h * 0.3)
            hist.append({"status": "accepted", "ago_hours": round(acc, 2)})
            fixed_h = ago_h - fixed_after_h
            work = (acc + fixed_h) / 2
            hist.append({"status": "in_progress", "ago_hours": round(work, 2)})
            hist.append({"status": "fixed", "ago_hours": round(fixed_h, 2)})
            status = "fixed"
            res = {"state": "reported", "reported_ago_hours": round(fixed_h, 2), "votes": {"yes": 0, "no": 0, "cant": 0}}
            if verify == "yes" and fixed_h > 6:
                res.update(state="verified", verified_ago_hours=round(fixed_h - 5, 2), votes={"yes": 1, "no": 0, "cant": 0})
            elif verify == "no" and fixed_h > 8:
                res.update(state="reopened", reopened_ago_hours=round(fixed_h - 7, 2), votes={"yes": 0, "no": 1, "cant": 0})
                hist.append({"status": "in_progress", "ago_hours": round(fixed_h - 7, 2), "reopened_by_residents": True})
                status = "in_progress"
        elif ago_h > 30 and rnd.random() < 0.5:
            hist.append({"status": "accepted", "ago_hours": round(ago_h - 20, 2)})
            status = "accepted"
        me = sorted((round(ago_h - rnd.uniform(0.2, min(ago_h - 0.1, 30)), 2) for _ in range(metoo)), reverse=True)
        complaints.append({
            "id": f"c-w07-{n:04d}", "ago_hours": round(ago_h, 2), "category": category, "text": text, "lang": lang,
            "point": _point(t, rnd), "target": {"kind": t["kind"], "id": tid}, "district": t.get("district"),
            "status": status, "status_history": hist, "metoo_ago_hours": [m for m in me if m > 0], "resolution": res,
            "demo": True,
        })

    # Фон: 40 дней, по 0–3 жалобы в день на разные цели; старое чинят за 2–6 дней, часть проверяют жители.
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
    start_h, end_h = BLIZZARD["started_ago_hours"], BLIZZARD["ended_ago_hours"]
    nura = [tid for tid in ids if targets[tid].get("district") == "nura" and targets[tid]["kind"] in ("segment", "area", "object")]
    other = [tid for tid in ids if targets[tid].get("district") != "nura"]
    for i in range(70):
        tid = nura[i % len(nura)] if i < 56 else rnd.choice(other)
        ago = rnd.uniform(end_h, start_h)
        # Чистка — через 1–3 дня после бурана; несколько мест жители «вернули» (снег остался).
        fix_at = rnd.uniform(end_h - 70, end_h - 18)
        verify = "no" if i in (5, 23) else rnd.choice(["yes", "yes", None])
        add(tid, ago, "snow_ice", fixed_after_h=ago - fix_at, verify=verify, metoo=rnd.choice([0, 1, 2, 3]))
    # Сегодня и вчера — свежие жалобы (карта «сегодня» не пустая).
    for _ in range(12):
        tid = rnd.choice(ids)
        add(tid, rnd.uniform(1, 40), ROLE_CATEGORY.get(targets[tid]["role"], "other"), metoo=rnd.choice([0, 1]))
    return {
        "version": "r07-mini-1", "demo": True, "note": "Синтетика R07 для тестов и стенда (не мир R02).",
        "complaints": complaints, "incidents": [dict(BLIZZARD)],
        "scenes": {"scene9": {"incident": BLIZZARD["id"], "replay": {"last": 7}}},
    }


def _at(now: datetime, hours) -> str:
    return iso(now - timedelta(hours=float(hours)))


def to_records(world: dict, now: datetime | None = None) -> list[dict]:
    """Жалобы мира → записи v2 (как их сохранил бы R09.seed_world), время — от now."""
    now = (now or datetime.now(timezone.utc)).astimezone(ASTANA_TZ)
    out = []
    for c in world.get("complaints") or []:
        created = _at(now, c["ago_hours"])
        r = {k: c[k] for k in ("id", "category", "text", "lang", "point", "target", "district", "status", "demo") if k in c}
        r["created_at"] = created
        r["status_history"] = [{"at": _at(now, h["ago_hours"]), **{k: v for k, v in h.items() if k != "ago_hours"}}
                               for h in c.get("status_history") or []]
        times = [_at(now, h) for h in c.get("metoo_ago_hours") or []]
        r["metoo"] = len(times)
        r["metoo_times"] = sorted(times)
        r["duplicate_of"] = None
        res = c.get("resolution")
        if res:
            r["resolution"] = {"round": 1, "state": res["state"], "votes": dict(res.get("votes") or {}),
                               "reported_at": _at(now, res["reported_ago_hours"]),
                               "verified_at": _at(now, res["verified_ago_hours"]) if res.get("verified_ago_hours") is not None else None,
                               "reopened_at": _at(now, res["reopened_ago_hours"]) if res.get("reopened_ago_hours") is not None else None}
        r["schema"] = "complaint.v2"
        out.append(r)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    world = build_world()
    recs = to_records(world)
    print(f"жалоб {len(recs)}, людей {sum(1 + r['metoo'] for r in recs)}, буран — {world['incidents'][0]['title_ru']}")
    if args.write:
        OUT_PATH.write_text(json.dumps(world, ensure_ascii=False, indent=1) + "\n", "utf-8")
        print("записано", OUT_PATH)


if __name__ == "__main__":
    main()
