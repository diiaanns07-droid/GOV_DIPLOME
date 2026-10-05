"""K02 demo: объяснение лучшего плана учебной модели по ID фактов, ru и kk.

Запуск из корня репозитория (нужен numpy, как для движка):
  python research/round-3-results/K02/demo.py [--lang ru|kk|both] [--event E2]
Селектор — детерминированная заглушка, вызова LLM нет.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verified_explainer import explain  # noqa: E402
from engine.optimizer import optimize  # noqa: E402
from engine.simulation import simulate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", choices=("ru", "kk", "both"), default="both")
    parser.add_argument("--event", default=None, help="id события, например E2")
    parser.add_argument("--json", action="store_true", help="печатать полный результат")
    args = parser.parse_args()
    decisions = optimize(top_n=1)["results"][0]["decisions"]
    result = simulate(decisions, event_id=args.event)
    for lang in (("ru", "kk") if args.lang == "both" else (args.lang,)):
        out = explain(result, lang=lang)
        print(f"=== {lang} | selector: {out['selector']} | scenario: {out['scenario_id']} ===")
        print(json.dumps(out, ensure_ascii=False, indent=1) if args.json else out["text"])
        print()


if __name__ == "__main__":
    main()
