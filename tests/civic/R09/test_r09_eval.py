"""CP6: adversarial-набор из fixtures/eval_cases.json — регрессия: ни одного FAIL."""

import json

from agent.civic_assistant.evaluate import main


def test_adversarial_eval_has_no_failures(tmp_path):
    assert main(["--out", str(tmp_path)]) == 0
    result = json.loads((tmp_path / "eval_results.json").read_text(encoding="utf-8"))
    assert result["summary"]["FAIL"] == 0 and result["summary"]["PASS"] >= 35
    assert result["facts_version"] == "civic-assistant-facts-v1"
    assert {"template", "llm:mock", "template-fallback", "unavailable"} <= set(result["modes_executed"])
    statuses = {r["id"]: r["status"] for r in result["rows"]}
    assert statuses["L00"] == "NOT_RUN"  # живой LLM никогда не выдаётся за PASS
    report = (tmp_path / "EVAL_REPORT.txt").read_text(encoding="utf-8")
    assert "code_sha:" in report and "live LLM: NOT_RUN" in report
