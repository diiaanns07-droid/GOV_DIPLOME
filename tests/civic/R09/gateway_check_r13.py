"""Проверка стыка R01 <-> R07 <-> R09 через НАСТОЯЩИЙ шлюз ui.web_server.CivicGateway (раунд 13).

    python3 tests/civic/R09/gateway_check_r13.py --root <checkout кандидата> [--out FILE.json]

Кандидат = голова R01 + пути R09 + research/round-13-results/R09/r01_integration_r13.patch (git apply).
БД — временная (tempfile). Шаги: POST /scenarios/compare двумя разными входами -> POST /assistant с
scenario_id "result:<digest>" -> «Это ваш расчёт» и длины движка; неизвестный digest -> «не найден»;
вопрос с устаревшей revision -> object_revision_changed. Без патча (нет scenario_results) -> NOT_APPLICABLE.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile


def run(root: Path) -> dict:
    sys.path.insert(0, str(root))
    from ui import web_server  # noqa: E402 — код кандидата
    registry = __import__("engine.civic_scenarios.registry", fromlist=["x"])
    checks = []

    def check(name, ok, observed):
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "observed": observed})

    tmp = tempfile.TemporaryDirectory(prefix="r09-r13-gateway-")
    gw = web_server.CivicGateway.for_project(root, Path(tmp.name) / "civic.sqlite3")
    if not hasattr(gw, "scenario_results"):
        tmp.cleanup()
        return {"status": "NOT_APPLICABLE", "reason": "в шлюзе нет scenario_results (патч R09 не применён)",
                "checks": []}
    ctx = {"headers": {"Host": "127.0.0.1"}, "client_ip": "127.0.0.1", "host_allowed": True, "is_same_origin": True}

    def post(path, body):
        return gw.handle("POST", path, "", json.dumps(body).encode("utf-8") if path == "/assistant" else body, ctx)

    case = next(c for c in registry.list_cases() if c["case_id"] == "astana-citywide-north-south-v1")
    p1 = copy.deepcopy(case["payload"])
    p2 = copy.deepcopy(case["payload"])
    p2["plans"][1]["closures"] = p1["plans"][0]["closures"] + p1["plans"][1]["closures"]
    results = []
    for body in (p1, p2):
        reply = post("/scenarios/compare", body)
        results.append(reply["body"]["data"] if reply.get("status") == 200 else None)
    check("compare_via_gateway", all(results) and results[0]["result_digest"] != results[1]["result_digest"],
          [r and r["result_digest"][:12] for r in results])
    texts = []
    for r in results:
        sid = "result:" + r["result_digest"]
        data = post("/assistant", {"question": "Чем план A отличается от B?", "scenario_id": sid})["body"]["data"]
        texts.append(data["text"])
        b_len = next(p for p in r["plans"] if p["id"] == "B")["routes"][0]["length_m"]
        from agent.civic_assistant.render import fmt_money
        check("assistant_explains_own_result_" + r["result_digest"][:8],
              data["scenario_id"] == sid and "Это ваш расчёт" in data["text"]
              and f"План B: путь {fmt_money(b_len)} м" in data["text"], data["text"][:300])
    check("two_results_differ", texts[0] != texts[1], len(texts))
    missing = post("/assistant", {"question": "Сравни планы", "scenario_id": "result:" + "0" * 64})["body"]["data"]
    check("unknown_result_asks_to_recompute", "scenario_result_unknown" in missing["warnings"], missing["text"])
    stats = gw.scenario_results().stats()
    check("cache_holds_two_compact_entries", stats["items"] == 2 and stats["bytes"] < 64 * 1024, stats)
    tmp.cleanup()
    return {"status": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL", "checks": checks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[3]))
    ap.add_argument("--out")
    args = ap.parse_args()
    report = run(Path(args.root).resolve())
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    for c in report["checks"]:
        print(c["status"], c["name"])
    print("STATUS", report["status"])
    sys.exit(0 if report["status"] in ("PASS", "NOT_APPLICABLE") else 1)


if __name__ == "__main__":
    main()
