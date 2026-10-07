"""Integrated extras on a running build (R10_TARGET=command|external): evidence JSON, not unittest.

  R10_TARGET=command R10_CODE_ROOT=<isolated copy> R10_START_CMD=... R10_CREATE_EDITOR_CMD=... \
    python3 -I -B tests/civic/R10/integrated_checks.py --out research/round-11-results/R10/runs/integrated-extra-<sha7>.json

H6 (assistant fact fidelity): every date in an answer must come from the object's facts
(schedule dates, history 'at' dates); unknown budget/responsible must read as unknown, not 0;
source label honest (no live LLM configured -> 'template').
D002 at the gateway: non-string graph_id -> 4xx JSON.
O001: which reason residents see for a re-published deadline change.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r10lib import helpers  # noqa: E402
from r10lib.target import JOURNAL, get_target  # noqa: E402

QUESTIONS = {
    "delay_reason": "Почему перенесли срок?",
    "deadline": "До какого числа ремонт?",
    "sources": "Откуда эти данные?",
    "history": "Что менялось в карточке?",
    "responsible": "Кто отвечает за работы?",
    "budget": "Сколько стоит ремонт?",
}
DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b")
NUM_RE = re.compile(r"(?<![\d.])\d[\d\s]{2,}(?:[.,]\d+)?\s*(?:тг|тенге|₸|KZT)", re.IGNORECASE)


def dates_in(text: str) -> set[str]:
    out = set()
    for m in DATE_RE.finditer(text):
        if m.group(1):
            out.add(f"{m.group(3)}-{m.group(2)}-{m.group(1)}")
        else:
            out.add(f"{m.group(4)}-{m.group(5)}-{m.group(6)}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    tc = unittest.TestCase()
    t = get_target()
    ed = t.editor(0)
    checks, answers = [], {}

    # D002 through the gateway
    anon = t.client()
    statuses = {}
    for gid in (["x"], {"a": 1}, 5, None):
        r = anon.post("/scenarios/compare", {"schema_version": "civic-scenario-v1", "graph_id": gid})
        statuses[json.dumps(gid)] = r.status
    checks.append({"id": "D002-gateway", "status": "PASS" if all(400 <= s < 500 for s in statuses.values()) else "FAIL",
                   "evidence": statuses})

    # object with a published deadline change
    item = helpers.create_draft(tc, ed, schedule={"planned_start": "2026-10-14", "original_planned_end": "2026-10-20",
                                                  "current_planned_end": "2026-10-20", "actual_end": None})
    pub = helpers.publish(tc, ed, item, reason="Первая публикация (R10)")
    update_reason = "Поставщик задержал асфальт (R10 причина правки)"
    r = helpers.update(ed, pub, {"schedule": dict(pub["schedule"], current_planned_end="2026-10-27")}, update_reason)
    upd = r.data["item"]
    detail = t.client().get(f"/objects/{item['id']}").data
    republished = False
    if detail["item"]["schedule"]["current_planned_end"] != "2026-10-27":
        r2 = ed.post(f"/staff/objects/{item['id']}/publish",
                     {"expected_revision": upd["revision"], "reason": "Публикация изменений (R10 общий текст)"})
        republished = r2.status == 200
        detail = t.client().get(f"/objects/{item['id']}").data
    shown = [h.get("reason") for h in detail["history"] if "schedule.current_planned_end" in (h.get("changed_fields") or [])]
    checks.append({"id": "O001-history-reason", "status": "OBSERVED",
                   "evidence": {"needed_republish": republished, "public_reasons_for_date_change": shown,
                                "update_reason_visible_publicly": update_reason in json.dumps(detail, ensure_ascii=False)}})

    # H6: assistant answers vs facts
    facts_dates = {d for d in detail["item"]["schedule"].values() if d}
    for h in detail["history"]:
        if isinstance(h.get("at"), str):
            facts_dates.add(h["at"][:10])
            try:
                local = dt.datetime.fromisoformat(h["at"].replace("Z", "+00:00")).astimezone(
                    dt.timezone(dt.timedelta(hours=5)))
                facts_dates.add(local.date().isoformat())
            except ValueError:
                pass
    for key, q in QUESTIONS.items():
        r = anon.post("/assistant", {"question": q, "object_id": item["id"], "scenario_id": None})
        d = r.data or {}
        text = d.get("text") or ""
        untraced = sorted(dates_in(text) - facts_dates)
        answers[key] = {"question": q, "http": r.status, "source": d.get("source"), "intent": d.get("intent"),
                        "warnings": d.get("warnings"), "fact_ids": len(d.get("fact_ids") or []),
                        "dates": sorted(dates_in(text)), "untraced_dates": untraced,
                        "money_amounts": NUM_RE.findall(text), "text": text[:600]}
    ok_dates = all(not a["untraced_dates"] for a in answers.values())
    checks.append({"id": "H6-dates-traceable", "status": "PASS" if ok_dates else "FAIL",
                   "evidence": {k: a["untraced_dates"] for k, a in answers.items()}})
    checks.append({"id": "H6-source-label", "status": "PASS" if all(a["source"] in ("template", "unavailable") for a in answers.values()) else "REVIEW",
                   "evidence": {k: a["source"] for k, a in answers.items()},
                   "note": "No LLM provider configured in this isolated run; 'llm' here would be a mislabel."})
    budget = answers["budget"]["text"]
    checks.append({"id": "H6-C03-unknown-budget", "status": "PASS" if (not answers["budget"]["money_amounts"] and " 0 " not in budget and "нет данных" in budget) else "FAIL",
                   "evidence": budget[:200]})
    checks.append({"id": "H6-delay-reason", "status": "PASS" if any(s and s in answers["delay_reason"]["text"] for s in shown) else "FAIL",
                   "evidence": answers["delay_reason"]["text"][:400]})
    checks.append({"id": "H6-routing", "status": "OBSERVED",
                   "evidence": {k: a["intent"] for k, a in answers.items()}})

    out = {"generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "target": t.describe(), "object_id": item["id"], "checks": checks, "assistant_answers": answers,
           "journal": JOURNAL}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in checks:
        print(f"{c['id']:24} {c['status']}")


if __name__ == "__main__":
    main()
