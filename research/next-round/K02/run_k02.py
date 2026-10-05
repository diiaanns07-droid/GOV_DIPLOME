"""K02: прогон случаев cases.json через текущий фильтр и прототип.

Запуск из корня репозитория: python research/next-round/K02/run_k02.py
Пишет results.json рядом со скриптом. Сеть и ключи API не нужны.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from kk_numeral_guard import REPO, qualitative_comment_v2  # noqa: E402
from agent.evidence import EvidenceError, qualitative_comment  # noqa: E402


def kept(fn, sentence: str) -> bool:
    # Добавляем нейтральное русское предложение, чтобы удаление единственного
    # предложения не превращалось в EvidenceError и было видно, что именно удалено.
    anchor = "Решение требует обсуждения с жителями."
    try:
        comment, _ = fn(sentence + " " + anchor)
    except EvidenceError:
        return False
    return sentence.strip() in comment.split("\n")


def main() -> None:
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))["cases"]
    rows, summary = [], {}
    for case in cases:
        row = {"id": case["id"], "lang": case["lang"], "expected": case["expected"],
               "category": case["category"], "text": case["text"]}
        for name, fn in (("current", qualitative_comment), ("prototype", qualitative_comment_v2)):
            is_kept = kept(fn, case["text"])
            if case["expected"] == "numeric":
                verdict = "LEAK" if is_kept else "ok"
            else:
                verdict = "ok" if is_kept else "FALSE_REMOVAL"
            row[name] = verdict
            bucket = summary.setdefault(name, {}).setdefault(case["lang"], {
                "numeric": 0, "leaks": 0, "qualitative": 0, "false_removals": 0})
            bucket["numeric" if case["expected"] == "numeric" else "qualitative"] += 1
            bucket["leaks"] += verdict == "LEAK"
            bucket["false_removals"] += verdict == "FALSE_REMOVAL"
        rows.append(row)
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    out = {"repo_commit": commit, "python": sys.version.split()[0],
           "evaluated": "agent.evidence.qualitative_comment (current) vs kk_numeral_guard.qualitative_comment_v2",
           "summary": summary, "rows": rows}
    (HERE / "results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for row in rows:
        if row["current"] != "ok" or row["prototype"] != "ok":
            print(f'{row["id"]:6} current={row["current"]:13} prototype={row["prototype"]:13} {row["text"]}')


if __name__ == "__main__":
    main()
