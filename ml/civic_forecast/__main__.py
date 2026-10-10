"""CLI R13: python3 -m ml.civic_forecast <команда>.

  build-targets [--geo-dir DIR]     собрать data/targets.json из данных R12 (data/civic/astana/geo/)
  weather-fixture                   пересоздать синтетическую фикстуру погоды (если нет LOCAL-9)
  history [--seed N]                сводка синтетической истории (JSON)
  backtest [--seeds 2026,2027]      проверка «как будто в прошлом» → RESULTS.md и results.json
  report                            перестроить RESULTS.md из results.json (без пересчёта)
  build-cache [--months 2026-10,2026-11]  прогноз с причинами → ui/civic_forecast/data/forecast_cache.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ml.civic_forecast")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("build-targets")
    cmd.add_argument("--geo-dir")
    sub.add_parser("weather-fixture")
    cmd = sub.add_parser("history")
    cmd.add_argument("--seed", type=int)
    cmd = sub.add_parser("backtest")
    cmd.add_argument("--seeds", default="2026")
    cmd.add_argument("--out", default=str(HERE))
    cmd = sub.add_parser("report")
    cmd.add_argument("--out", default=str(HERE))
    cmd = sub.add_parser("build-cache")
    cmd.add_argument("--months", default="")
    args = parser.parse_args(argv)

    if args.command == "build-targets":
        from .targets import GEO_DIR, TARGETS_PATH, build_targets
        data = build_targets(Path(args.geo_dir) if args.geo_dir else GEO_DIR)
        TARGETS_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(json.dumps({k: data[k] for k in ("count", "by_kind", "by_district")}, ensure_ascii=False))
    elif args.command == "weather-fixture":
        from .weather import write_fixture
        print(json.dumps(write_fixture(), ensure_ascii=False))
    elif args.command == "history":
        from .history import SEED, generate
        summary = generate(seed=args.seed or SEED).summary()
        print(json.dumps(summary, ensure_ascii=False, indent=1))
    elif args.command == "backtest":
        from .backtest import main as backtest
        seeds = tuple(int(s) for s in args.seeds.split(",") if s)
        backtest(seeds=seeds, out_dir=Path(args.out), log=lambda m: print(m, file=sys.stderr))
        print((Path(args.out) / "RESULTS.md").read_text(encoding="utf-8"))
    elif args.command == "report":
        from .backtest import rerender
        print(rerender(Path(args.out)))
    elif args.command == "build-cache":
        from ui.civic_forecast.build import build_cache
        months = [m for m in args.months.split(",") if m]
        print(json.dumps(build_cache(months or None), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
