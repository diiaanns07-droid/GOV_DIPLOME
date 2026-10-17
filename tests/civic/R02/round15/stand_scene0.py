"""R02 · раунд 15+ (П3) · сцена 0 «ИИ-разбор пачки» на живом стенде — набор R02 «обращения за ночь».

    python3 tests/civic/R02/round15/stand_scene0.py --base http://127.0.0.1:8656 --password-file p.txt [--no-commit]

Как экран сотрудника: GET intake/sample (пример = intake_night_v1.json R02, эталона в ответе нет) -> POST intake/analyze
{sample: "night"} -> оценщик R02 (ml.datasets.demo_intake_eval, правило улиц) -> POST intake/commit («Создать задачи»)
и повтор того же batch_id (дублей быть не должно). --no-commit — только разбор (числа мира не меняются).
После commit числа мира на стенде нарочно другие: сверка stand_numbers.py — до сцены 0 или на восстановленной базе
(INTEGRATION R02 §12). Печатает сводку и пишет JSON (--out). Код выхода 1 — пример не совпал с набором или повтор
создал записи. Только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ml.datasets import demo_intake_eval as ev  # noqa: E402
from stand_numbers import Client, unwrap  # noqa: E402

WORLD_DIR = ROOT / "data/civic/astana/demo-world"


def counts(result) -> dict:
    """Ответ commit без списков записей: created, existing, joined_existing, joined, skipped_no_address, failed."""
    return {k: v for k, v in (result or {}).items() if not isinstance(v, (list, dict))}


def scene0(c: Client, commit: bool = True) -> tuple[dict, dict]:
    texts = json.loads((WORLD_DIR / "intake_night_v1.json").read_text(encoding="utf-8"))
    gold = json.loads((WORLD_DIR / "intake_night_v1.gold.json").read_text(encoding="utf-8"))
    out = {}
    status, body = c.call("GET", "/api/civic/v2/intake/sample?name=night")
    sample = unwrap(body) if isinstance(unwrap(body), dict) else {}
    got = {t.get("id"): t.get("text") for t in sample.get("texts") or []}
    out["sample"] = {"status": status, "texts": len(got), "same_as_r02": got == {t["id"]: t["text"] for t in texts["texts"]},
                     "gold_in_answer": "gold" in sample}
    started = time.time()
    status, body = c.call("POST", "/api/civic/v2/intake/analyze", {"sample": "night"})
    answer = unwrap(body) if isinstance(unwrap(body), dict) else {}
    out["analyze"] = {"status": status, "wall_ms": round((time.time() - started) * 1000), "summary": answer.get("summary"),
                      "batch_id": answer.get("batch_id")}
    out["eval"] = ev.evaluate(answer, gold, ev._street_names()) if answer.get("tasks") else None
    if commit and answer.get("batch_id"):
        status, body = c.call("POST", "/api/civic/v2/intake/commit", {"batch_id": answer["batch_id"]})
        out["commit"] = {"status": status, **counts(unwrap(body))}
        status, body = c.call("POST", "/api/civic/v2/intake/commit", {"batch_id": answer["batch_id"]})
        out["commit_again"] = {"status": status, **counts(unwrap(body))}
    return out, answer


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Сцена 0 на стенде: набор R02 «обращения за ночь»")
    ap.add_argument("--base", default="http://127.0.0.1:8656")
    ap.add_argument("--user", default="operator")
    ap.add_argument("--password-file", required=True, help="файл с паролем сотрудника (пароль не в командной строке)")
    ap.add_argument("--no-commit", action="store_true", help="только разбор, без «Создать задачи»")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    c = Client(args.base)
    if not c.login(args.user, Path(args.password_file).read_text(encoding="utf-8").strip()):
        print("вход сотрудника не удался")
        return 2
    out, _ = scene0(c, commit=not args.no_commit)
    s, e = out["analyze"]["summary"] or {}, out["eval"] or {}
    print(f"пример: {out['sample']['texts']} текстов, = набору R02: {out['sample']['same_as_r02']}, "
          f"эталон в ответе: {out['sample']['gold_in_answer']}")
    print(f"разбор: {s.get('total')} → {s.get('tasks')} задач · {s.get('services')} служб · {s.get('urgent')} срочных · "
          f"{s.get('merged')} склеено · {s.get('no_address')} без адреса; создать {s.get('ready')} "
          f"({s.get('to_create')} новых + {s.get('to_existing')} к открытым), {s.get('ms')} мс")
    if e:
        print(f"оценщик R02: служба {e['services']['lead_accuracy']}, F1 повторов {e['duplicates']['pairwise_f1']} "
              f"(групп точно {e['duplicates']['groups_exact']}), места {e['places']['found_share']}, "
              f"срочные группы {e['urgent']['recall_groups']}")
    if "commit" in out:
        print(f"«Создать задачи»: {json.dumps(out['commit'], ensure_ascii=False)}")
        print(f"повтор:          {json.dumps(out['commit_again'], ensure_ascii=False)}")
    if args.out:
        Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    bad = not out["sample"]["same_as_r02"] or out["sample"]["gold_in_answer"]
    bad = bad or bool(out.get("commit_again", {}).get("created"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
