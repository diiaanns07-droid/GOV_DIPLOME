"""Adversarial-оценка помощника R09: python3 -m agent.civic_assistant.evaluate [--ui] [--out DIR]

Читает tests/civic/R09/fixtures/eval_cases.json и синтетические fixtures, выполняет каждый
кейс фактическим путём (template / MockProvider / endpoint / extract / audit) и пишет
EVAL_REPORT.txt + eval_results.json. С --ui дополнительно запускает проверку в реальном
Chromium (tests/civic/R09/ui_check.cjs); без node/playwright эти строки — NOT_RUN.
Живой платный LLM не вызывается никогда: соответствующая строка всегда NOT_RUN.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from agent.civic_assistant import FACTS_VERSION, build_answer, build_verified_context
from agent.civic_assistant.api import ASSISTANT_PATH, EXTRACT_PATH, AssistantEndpoint, RateLimiter
from agent.civic_assistant.audit import statement_violations
from agent.civic_assistant.extract import extract_draft
from agent.civic_assistant.facts import check_context
from agent.civic_assistant.providers import MockProvider

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "civic" / "R09" / "fixtures"


def _load():
    objects = json.loads((FIX / "objects.json").read_text(encoding="utf-8"))
    pubs = json.loads((FIX / "publications.json").read_text(encoding="utf-8"))
    r07 = json.loads((FIX / "r07_synthetic_result.json").read_text(encoding="utf-8"))
    cases = json.loads((FIX / "eval_cases.json").read_text(encoding="utf-8"))["cases"]
    html = copy.deepcopy(objects["objects"]["full"])
    html.update(id="r09-synth-html", title='<img src=x onerror="window.__xss=1">Синтетика с HTML')
    objects["objects"]["html"] = html
    return objects, pubs, r07, cases


def _provider(spec):
    if spec is None:
        return None
    items = []
    for item in spec:
        if isinstance(item, list) and item and item[0] == "sleep":
            items.append(("sleep", float(item[1]), item[2]))
        elif isinstance(item, dict) and "__raise__" in item:
            items.append(RuntimeError(item["__raise__"]))
        else:
            items.append(item)
    return MockProvider(items)


def _outside_quotes(ans):
    return " ".join(s["text"] for s in ans.get("statements", []) if s.get("kind") != "quote")


def _check(expect, ans=None, *, elapsed=None, provider=None, resp=None):
    problems = []
    text = (ans or {}).get("text", "")
    for key in ("source", "intent", "language", "mode", "object_id"):
        if key in expect and (ans or {}).get(key) != expect[key]:
            problems.append(f"{key}={ (ans or {}).get(key)!r} != {expect[key]!r}")
    if "model" in expect and (ans or {}).get("model") != expect["model"]:
        problems.append(f"model={(ans or {}).get('model')!r}")
    for w in expect.get("warnings_include", []):
        if w not in (ans or {}).get("warnings", []):
            problems.append("missing warning " + w)
    for s in expect.get("text_includes", []):
        if s not in text:
            problems.append("text lacks " + repr(s))
    for s in expect.get("text_excludes", []):
        if s in text:
            problems.append("text has " + repr(s))
    for s in expect.get("text_excludes_outside_quotes", []):
        if s in _outside_quotes(ans or {}):
            problems.append("non-quote text has " + repr(s))
    for s in expect.get("quote_includes", []):
        if not any(s in st["text"] for st in (ans or {}).get("statements", []) if st.get("kind") == "quote"):
            problems.append("no quote with " + repr(s))
    if expect.get("no_digits") and re.search(r"\d", text):
        problems.append("digits in text without data")
    if "max_seconds" in expect and elapsed is not None and elapsed > expect["max_seconds"]:
        problems.append(f"took {elapsed:.2f}s")
    if "provider_request_excludes" in expect and provider is not None:
        sent = json.dumps(provider.requests, ensure_ascii=False)
        for s in expect["provider_request_excludes"]:
            if s in sent:
                problems.append("provider saw " + repr(s))
    return problems


def run_case(case, objects, pubs, r07):
    kind = case["kind"]
    expect = case["expect"]
    obj = objects["objects"]
    hist = objects["history"]

    def ctx_for(name):
        return build_verified_context(obj[name], hist.get(name))

    if kind == "answer":
        prov = _provider(case.get("provider"))
        t0 = time.monotonic()
        ans = build_answer(case["question"], ctx_for(case["object"]), prov, timeout_s=case.get("timeout_s", 8.0))
        elapsed = time.monotonic() - t0
        if isinstance(prov, MockProvider):
            prov._cancel.set()
        return _check(expect, ans, elapsed=elapsed, provider=prov), ans.get("mode")
    if kind == "tampered_context":
        ctx = copy.deepcopy(ctx_for(case["object"]))
        for f in ctx["facts"]:
            if f["id"] in case["tamper"]:
                f["value"], f["known"] = case["tamper"][f["id"]], True
        ans = build_answer(case["question"], ctx)
        return _check(expect, ans), ans.get("mode")
    if kind == "audit":
        facts = check_context(ctx_for(case["object"]))
        got = statement_violations(case["statement"], facts)
        return ([] if got == expect["violations"] else [f"violations {got} != {expect['violations']}"]), "audit"
    if kind == "scenario":
        ctx = build_verified_context(None, None, r07["result"], scenario_id=r07["_provenance"]["case_id"])
        ans = build_answer(case["question"], ctx)
        problems = _check({k: v for k, v in expect.items() if k != "text_excludes_outside_question"}, ans)
        for s in expect.get("text_excludes_outside_question", []):
            if s in ans["text"]:
                problems.append("text has " + repr(s))
        return problems, ans.get("mode")
    if kind == "endpoint":
        loaded = {"r09-synth-full": (obj["full"], hist["full"]), "r09-synth-draft": (obj["draft"], []),
                  "r09-synth-html": (obj["html"], [])}
        ep = AssistantEndpoint(lambda oid: loaded.get(oid), rate_limiter=RateLimiter(1000, 60))
        body = copy.deepcopy(case["body"])
        if isinstance(body, dict) and isinstance(body.get("question"), str) and body["question"].startswith("LONG:"):
            body["question"] = "?" * int(body["question"][5:])
        resp = ep.handle("POST", ASSISTANT_PATH, {}, body, {"client_ip": "127.0.0.1", "headers": {}})
        problems = []
        if resp["status"] != expect["status"]:
            problems.append(f"status {resp['status']} != {expect['status']}")
        if "error_code" in expect and resp["body"].get("error", {}).get("code") != expect["error_code"]:
            problems.append("error_code " + str(resp["body"].get("error")))
        data = resp["body"].get("data") if resp["body"].get("ok") else None
        if data is not None:
            problems += _check({k: v for k, v in expect.items() if k not in ("status", "error_code", "note")}, data)
        return problems, "endpoint"
    if kind == "extract":
        pub = pubs[case["publication"]]
        prov = _provider(case.get("provider"))
        d = extract_draft(pub["text"], pub["source_id"], url=pub.get("url"), provider=prov)
        problems = []
        blob = json.dumps(d["fields"], ensure_ascii=False)
        for s in expect.get("fields_exclude", []):
            if s in blob:
                problems.append("fields contain " + repr(s))
        quotes = " ".join(r["quote"] for r in d["ignored_instructions"])
        for s in expect.get("ignored_includes", []):
            if s not in quotes:
                problems.append("instruction not reported: " + repr(s))
        for f, v in expect.get("field_values", {}).items():
            got = d["fields"].get(f, {}).get("value", "<absent>")
            if got != v:
                problems.append(f"{f}={got!r} != {v!r}")
        for w in expect.get("warnings_include", []):
            if w not in d["warnings"]:
                problems.append("missing warning " + w)
        if "status" in expect and d["status"] != expect["status"]:
            problems.append("status " + d["status"])
        for spec in d["fields"].values():
            if pub["text"][spec["span"][0]:spec["span"][1]] != spec["quote"]:
                problems.append("span/quote mismatch " + spec["field"])
        return problems, "extract:" + d["mode"]
    if kind == "extract_endpoint":
        ep = AssistantEndpoint(lambda oid: None, resolve_principal=lambda ctx: case["principal"],
                               rate_limiter=RateLimiter(100, 60))
        pub = pubs["ru_full"]
        resp = ep.handle("POST", EXTRACT_PATH, {}, {"source_id": pub["source_id"], "text": pub["text"]},
                         {"client_ip": "127.0.0.1", "is_same_origin": True, "headers": {}})
        return ([] if resp["status"] == expect["status"] else [f"status {resp['status']}"]), "endpoint"
    return ["unknown case kind " + kind], None


def run_ui(out_dir: Path):
    env = {**os.environ, "NODE_PATH": os.environ.get("NODE_PATH", "/opt/node22/lib/node_modules")}
    if not shutil.which("node") or subprocess.run(["node", "-e", "require('playwright')"], capture_output=True,
                                                   env=env).returncode != 0:
        return None, "node/playwright недоступны"
    here = ROOT / "tests" / "civic" / "R09"
    srv = subprocess.Popen([sys.executable, str(here / "demo_server.py"), "0"], stdout=subprocess.PIPE, text=True)
    try:
        line = srv.stdout.readline().strip()
        port = int(line.split()[1])
        out = subprocess.run(["node", str(here / "ui_check.cjs"), f"http://127.0.0.1:{port}", str(out_dir)],
                             capture_output=True, text=True, timeout=300, env=env)
        return json.loads(out.stdout.strip().splitlines()[-1])["checks"], None
    except Exception as exc:  # noqa: BLE001
        return None, f"ui run failed: {type(exc).__name__}"
    finally:
        srv.terminate()
        srv.wait(timeout=10)


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "research" / "round-11-results" / "R09"))
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    objects, pubs, r07, cases = _load()
    rows = []
    modes = set()
    for case in cases:
        try:
            problems, mode = run_case(case, objects, pubs, r07)
        except Exception as exc:  # noqa: BLE001
            problems, mode = [f"exception {type(exc).__name__}: {exc}"], None
        if mode:
            modes.add(mode)
        rows.append({"id": case["id"], "category": case["category"], "kind": case["kind"],
                     "status": "FAIL" if problems else "PASS", "detail": "; ".join(problems)[:300]})
    ui_checks, ui_reason = (run_ui(out_dir) if args.ui else (None, "запуск без --ui"))
    if ui_checks is None:
        rows.append({"id": "U00", "category": "ui_browser", "kind": "ui", "status": "NOT_RUN", "detail": ui_reason})
    else:
        modes.add("browser:chromium")
        for i, c in enumerate(ui_checks, 1):
            rows.append({"id": f"U{i:02d}", "category": "ui:" + c["name"], "kind": "ui", "status": c["status"],
                         "detail": "" if c["status"] == "PASS" else c["detail"][:300]})
    rows.append({"id": "L00", "category": "live_llm_provider", "kind": "llm", "status": "NOT_RUN",
                 "detail": "Платный живой вызов вне задания R09; адаптер проверен на поддельном клиенте (pytest)."})
    head = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain", "--", "agent/civic_assistant", "web/civic/assistant", "tests/civic/R09"))
    summary = {s: sum(1 for r in rows if r["status"] == s) for s in ("PASS", "FAIL", "NOT_RUN")}
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_sha": head, "code_paths_dirty": dirty, "facts_version": FACTS_VERSION,
        "modes_executed": sorted(modes), "summary": summary, "rows": rows,
        "inputs": ["tests/civic/R09/fixtures/eval_cases.json", "objects.json", "publications.json",
                   "r07_synthetic_result.json (R07 18f8ac8)"],
    }
    (out_dir / "eval_results.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [
        "R09 — ADVERSARIAL EVALUATION (раунд 11, Астана, синтетические данные)",
        f"generated_at: {result['generated_at']}",
        f"code_sha: {head}{' (ВНИМАНИЕ: незакоммиченные изменения в путях R09)' if dirty else ''}",
        f"facts_version: {FACTS_VERSION}",
        "modes_executed: " + ", ".join(result["modes_executed"]),
        "live LLM: NOT_RUN (платные вызовы не выполнялись; source=llm в кейсах — MockProvider)",
        f"summary: PASS {summary['PASS']} / FAIL {summary['FAIL']} / NOT_RUN {summary['NOT_RUN']}",
        "команда: python3 -m agent.civic_assistant.evaluate --ui",
        "",
        f"{'ID':<5} {'STATUS':<8} {'KIND':<17} CATEGORY / DETAIL",
    ]
    for r in rows:
        lines.append(f"{r['id']:<5} {r['status']:<8} {r['kind']:<17} {r['category']}" + (f" — {r['detail']}" if r["detail"] else ""))
    (out_dir / "EVAL_REPORT.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 1 if summary["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
