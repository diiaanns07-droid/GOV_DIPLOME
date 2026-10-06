"""Совместимость помощника R09 с записями civic-v1 другого производителя (R05).

    git show <R05_SHA>:data/civic/astana/demo_synthetic.json > /tmp/r05_demo.json
    python3 research/round-11-results/R09/check_r05_compat.py /tmp/r05_demo.json <R05_SHA>

Для каждой записи: публичный контекст (draft/archived обязаны отклоняться), все типы вопросов RU/KK
в шаблонном режиме и выбор каждого intent через MockProvider. Проверяется: нет исключений, нет
отброшенных аудитом фраз, пометка synthetic в каждом ответе, «завершено» только при completed.
Это СИНТЕТИЧЕСКИЙ срез R05 (реальных записей в R05 на 2026-10-06 — 0: egress закрыт).
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from agent.civic_assistant import ContextError, build_answer, build_verified_context  # noqa: E402
from agent.civic_assistant.audit import statement_violations  # noqa: E402
from agent.civic_assistant.facts import check_context  # noqa: E402
from agent.civic_assistant.providers import MockProvider  # noqa: E402
from agent.civic_assistant.render import INTENTS  # noqa: E402

QUESTIONS = ("Что здесь происходит?", "Когда закончат работы?", "Почему перенесли срок?", "Кто отвечает за работы?",
             "Сколько это стоит и откуда сумма?", "Откуда эти данные?", "Работы уже закончены?", "Что менялось?",
             "Где это?", "Как изменится проход?", "Мұнда не болып жатыр?", "Жұмыс қашан аяқталады?", "Қанша тұрады?")


def main(path, r05_sha):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = []
    for item in data["items"]:
        oid = item.get("id")
        try:
            ctx = build_verified_context(item, [])
        except ContextError as exc:
            ok = item.get("publication") != "published" and exc.code == "object_not_public"
            rows.append({"id": oid, "publication": item.get("publication"), "status": "PASS" if ok else "FAIL",
                         "detail": "rejected: " + exc.code})
            continue
        facts = check_context(ctx)
        problems = []
        answers = [build_answer(q, ctx) for q in QUESTIONS]
        for intent in INTENTS:
            answers.append(build_answer("вопрос", ctx, MockProvider([{"intent": intent, "fact_ids": []}])))
        for ans in answers:
            if [w for w in ans["warnings"] if w.startswith("audit_dropped")]:
                problems.append(f"{ans['intent']}: {ans['warnings']}")
            for st in ans["statements"]:
                v = statement_violations(st, facts)
                if v:
                    problems.append(f"{ans['intent']}: {v}")
            if item.get("evidence_type") == "synthetic" and "синтет" not in ans["text"]:
                problems.append(f"{ans['intent']}: no synthetic marker")
            if item.get("status") != "completed" and ("«завершено»" in ans["text"] or "Статус в карточке: завершено" in ans["text"]):
                problems.append(f"{ans['intent']}: completion claim")
        rows.append({"id": oid, "publication": item.get("publication"), "status": "FAIL" if problems else "PASS",
                     "detail": "; ".join(problems)[:400] or f"{len(answers)} answers, warnings={ctx['warnings']}",
                     "sample": answers[1]["text"][:300]})
    out = {"r05_sha": r05_sha, "slice": data.get("slice", {}).get("version"), "demo": data.get("slice", {}).get("demo"),
           "summary": {s: sum(1 for r in rows if r["status"] == s) for s in ("PASS", "FAIL")}, "rows": rows}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0 if out["summary"]["FAIL"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
