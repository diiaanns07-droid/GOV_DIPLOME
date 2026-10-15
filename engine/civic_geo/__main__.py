"""Командная строка R12:

    python3 -m engine.civic_geo report [--json out.json] [--objects store.json]   отчёт точности (код 1 при FAIL)
    python3 -m engine.civic_geo targets LON LAT CATEGORY         кандидаты привязки жалобы
    python3 -m engine.civic_geo segment LON,LAT LON,LAT [--kind road|foot]   участок улицы по графу
    python3 -m engine.civic_geo bench [N]                        время ответа /targets на N случайных точках
    python3 -m engine.civic_geo build-way-tags | build-data | snap-demo   пересборка данных
    python3 -m engine.civic_geo search-index [--out FILE]        индекс подсказок поиска (улицы, остановки, дворы) для R01
    python3 -m engine.civic_geo build-works-fixture [--out FILE] фикстура «Календаря работ» (синтетика на улицах OSM)
    python3 -m engine.civic_geo works [--from 2026-09 --to 2027-09 --district nura]   календарь и конфликты в консоли
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "build-way-tags":
        from .build_way_tags import main as m
        return m(rest)
    if cmd == "build-data":
        from .build_geo_data import main as m
        return m(rest)
    if cmd == "snap-demo":
        from .snap_demo import main as m
        return m(rest)
    if cmd == "search-index":
        from .search_index import main as m
        return m(rest)
    if cmd == "build-works-fixture":
        from .build_works_fixture import main as m
        return m(rest)
    if cmd == "works":
        from .works_calendar import build_calendar, load_fixture, load_works, parse_filters, parse_period, today_astana
        ap = argparse.ArgumentParser(prog="works")
        ap.add_argument("--from", dest="date_from")
        ap.add_argument("--to", dest="date_to")
        ap.add_argument("--district")
        ap.add_argument("--fixture", action="store_true", help="только фикстура R12 (без R06)")
        a = ap.parse_args(rest)
        today = today_astana()
        start, end = parse_period({"from": a.date_from, "to": a.date_to}, today)
        records = load_fixture(today) if a.fixture else load_works(today)[0]
        cal = build_calendar(records, start, end, parse_filters({"district": a.district}), today)
        for c in cal["conflicts"]:
            print(f"{c['severity']:6s} {c['kind']:22s} {c['street_ru'] or '—'}: {', '.join(c['works'])}\n       {c['advice_ru']}")
        print(json.dumps(cal["counts"], ensure_ascii=False), f"{cal['generated_ms']} мс")
        return 0
    if cmd == "report":
        from .accuracy import format_report, report
        ap = argparse.ArgumentParser(prog="report")
        ap.add_argument("--json")
        ap.add_argument("--objects", help="выгрузка записей civic-v1 (JSON {items:[...]}) — проверить их линии")
        a = ap.parse_args(rest)
        r = report(objects_path=Path(a.objects) if a.objects else None)
        print(format_report(r))
        if a.json:
            Path(a.json).parent.mkdir(parents=True, exist_ok=True)
            Path(a.json).write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n", "utf-8")
        return 0 if r["result"] == "PASS" else 1
    if cmd == "targets":
        from .api import targets_response
        lon, lat, cat = rest[0], rest[1], rest[2] if len(rest) > 2 else "other"
        status, body = targets_response({"lon": lon, "lat": lat, "category": cat})
        print(json.dumps(body, ensure_ascii=False, indent=1))
        return 0 if status == 200 else 1
    if cmd == "segment":
        from .api import segment_response
        ap = argparse.ArgumentParser(prog="segment")
        ap.add_argument("a")
        ap.add_argument("b")
        ap.add_argument("--kind")
        a = ap.parse_args(rest)
        status, body = segment_response({"from": a.a, "to": a.b, "kind": a.kind})
        print(json.dumps(body, ensure_ascii=False, indent=1))
        return 0 if status == 200 else 1
    if cmd == "bench":
        from .api import targets_response, warm_up
        from .targets import load_categories
        n = int(rest[0]) if rest else 2000
        t0 = time.perf_counter()
        warm_up()
        load_s = time.perf_counter() - t0
        rnd = random.Random(14)
        cats = list(load_categories())
        times = []
        for _ in range(n):
            q = {"lon": str(rnd.uniform(71.36, 71.52)), "lat": str(rnd.uniform(51.08, 51.20)), "category": rnd.choice(cats)}
            t = time.perf_counter()
            status, _ = targets_response(q)
            times.append((time.perf_counter() - t) * 1000)
            assert status == 200
        times.sort()
        print(json.dumps({"points": n, "load_s": round(load_s, 2), "p50_ms": round(times[n // 2], 2),
                          "p95_ms": round(times[int(n * 0.95)], 2), "max_ms": round(times[-1], 2)}))
        return 0
    print(f"неизвестная команда: {cmd}\n{__doc__}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
