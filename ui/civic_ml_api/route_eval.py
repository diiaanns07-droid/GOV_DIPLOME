"""Оценка route() на наборе фраз (tests/civic/R04/round15/route_cases.json) — числа для DELIVERY и диплома.

    python -m ui.civic_ml_api route-eval --split dev        # подбор правил — только dev
    python -m ui.civic_ml_api route-eval --split test       # итог; каждый прогон test — строка в журнале RESULTS
    python -m ui.civic_ml_api route-eval --split all --errors

Метрики:
  set_acc   — набор служб совпал полностью (ведущая и участвующие, без учёта порядка);
  lead_acc  — ведущая служба совпала (для any_order — любая из ожидаемых);
  joint     — «нужны 2 службы»: precision / recall / F1 по флагу joint (главное число для диплома);
  pair_acc  — среди верно найденных совместных: пара служб совпала;
  ms        — время одного вызова (p50 / p95 / max), без первого прогрева.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from ui.civic_ml_api.routing import route

CASES_PATH = Path(__file__).resolve().parents[2] / "tests" / "civic" / "R04" / "round15" / "route_cases.json"


def load_cases(path: Path | None = None) -> list[dict]:
    return json.loads(Path(path or CASES_PATH).read_text(encoding="utf-8"))["cases"]


def _safe_div(a: float, b: float) -> float:
    return round(a / b, 4) if b else 0.0


def evaluate(cases: list[dict], split: str = "dev") -> dict:
    chosen = [c for c in cases if split == "all" or c.get("split") == split]
    # Первая загрузка моделей не считается во время (на сервере её делает warmup() при старте).
    route(text="Прогрев: яма на дороге")
    route(text="Прогрев без сигналов: непонятный текст обращения")
    rows, times = [], []
    for case in chosen:
        t0 = time.perf_counter()
        res = route(text=case.get("text") or None, category=case.get("category"), subtopic=case.get("subtopic"))
        times.append((time.perf_counter() - t0) * 1000)
        got = [s["service"] for s in res["services"]]
        expect = list(case["expect"])
        lead_ok = got[0] in expect if case.get("any_order") else got[0] == expect[0]
        rows.append({"id": case["id"], "lang": case.get("lang"), "text": case.get("text"), "expect": expect,
                     "got": got, "rule": res["rule"], "set_ok": set(got) == set(expect), "lead_ok": lead_ok,
                     "joint_expect": len(expect) > 1, "joint_got": res["joint"]})
    tp = sum(1 for r in rows if r["joint_expect"] and r["joint_got"])
    fp = sum(1 for r in rows if not r["joint_expect"] and r["joint_got"])
    fn = sum(1 for r in rows if r["joint_expect"] and not r["joint_got"])
    precision, recall = _safe_div(tp, tp + fp), _safe_div(tp, tp + fn)
    f1 = round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0
    by_lang = {}
    for lang in sorted({r["lang"] for r in rows}):
        part = [r for r in rows if r["lang"] == lang]
        by_lang[lang] = {"n": len(part), "set_acc": _safe_div(sum(r["set_ok"] for r in part), len(part))}
    times.sort()
    return {
        "split": split, "n": len(rows), "n_joint": sum(r["joint_expect"] for r in rows),
        "set_acc": _safe_div(sum(r["set_ok"] for r in rows), len(rows)),
        "lead_acc": _safe_div(sum(r["lead_ok"] for r in rows), len(rows)),
        "joint": {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn},
        "pair_acc": _safe_div(sum(1 for r in rows if r["joint_expect"] and r["joint_got"] and r["set_ok"]), tp),
        "by_lang": by_lang,
        "ms": {"p50": round(statistics.median(times), 3) if times else None,
               "p95": round(times[int(0.95 * (len(times) - 1))], 3) if times else None,
               "max": round(times[-1], 3) if times else None},
        "errors": [r for r in rows if not (r["set_ok"] and r["lead_ok"])],
    }
