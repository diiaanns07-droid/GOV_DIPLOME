"""Проверка ML-API без сервера.

    python -m ui.civic_ml_api status
    python -m ui.civic_ml_api classify "Во дворе не горят фонари" "Аялдамада қар тазаланбаған"
    python -m ui.civic_ml_api similar "Не убран снег на остановке" --lon 71.42 --lat 51.09 --demo

--demo: вместо хранилища R09 — 5 000 синтетических обращений (demo) вокруг точки; без --demo similar
отвечает 503 source_not_connected (хранилище подключает сервер R01).
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import ui.civic_ml_api as api


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ui.civic_ml_api")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    c = sub.add_parser("classify")
    c.add_argument("texts", nargs="+")
    s = sub.add_parser("similar")
    s.add_argument("text")
    s.add_argument("--lon", type=float, required=True)
    s.add_argument("--lat", type=float, required=True)
    s.add_argument("--days", type=int, default=14)
    s.add_argument("--target", help="id цели (osm-node-…, osm-w…-…, yard-…, cell-…)")
    s.add_argument("--demo", action="store_true", help="синтетические обращения вокруг точки")
    args = ap.parse_args(argv)

    if args.cmd == "status":
        print(json.dumps(api.status(), ensure_ascii=False, indent=1))
        return 0
    if args.cmd == "classify":
        for text in args.texts:
            t0 = time.perf_counter()
            res = api.classify(text)
            res["ms"] = round((time.perf_counter() - t0) * 1000, 2)
            print(json.dumps(res, ensure_ascii=False))
        return 0
    if args.demo:
        from ml.civic_dedup import fixtures as F
        api.set_complaint_source(api.records_source(F.make_records(5000, hotspot=(args.lon, args.lat),
                                                                   hotspot_radius_m=1500, n_targets=200)))
    try:
        t0 = time.perf_counter()
        res = api.similar(args.text, point=[args.lon, args.lat], days=args.days, target=args.target)
        res["ms"] = round((time.perf_counter() - t0) * 1000, 2)
    except api.MLServiceUnavailable as exc:
        print(json.dumps({"status": exc.status, "error": exc.code, "message": exc.message}, ensure_ascii=False))
        return 3
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
