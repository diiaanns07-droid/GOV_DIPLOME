"""R07: HTTP-адаптер (форма ответа CONTRACT) и статические требования к UI-модулю."""
import copy
import json
import re
from pathlib import Path

from engine.civic_scenarios.http import handle

ROOT = Path(__file__).resolve().parents[3]
CASE = json.loads((ROOT / "engine/civic_scenarios/cases/synthetic-tiny-v1.case.json").read_text("utf-8"))["payload"]
JS = (ROOT / "web/civic/scenarios/scenarios.js").read_text("utf-8")
CSS = (ROOT / "web/civic/scenarios/scenarios.css").read_text("utf-8")
API = "/api/civic/v1/scenarios"


def test_envelope_ok_and_errors():
    r = handle("POST", API + "/compare", body=copy.deepcopy(CASE))
    assert r["status"] == 200 and r["body"]["ok"] is True and r["body"]["data"]["schema_version"] == "civic-scenario-result-v1"
    assert r["headers"]["Content-Type"].startswith("application/json")
    cases = [
        (("GET", API + "/nope"), 404, "not_found"),
        (("GET", API + "/compare"), 405, "method_not_allowed"),
        (("POST", API + "/compare", None, "not json"), 400, "invalid_payload"),
        (("GET", API + "/graphs/..%2F..%2Fetc%2Fpasswd"), 404, "unknown_graph"),
        (("POST", API + "/compare", None, dict(CASE, graph_id="/etc/passwd")), 404, "unknown_graph"),
        (("POST", API + "/compare", None, dict(CASE, graph_digest="f" * 64)), 409, "graph_digest_mismatch"),
        (("POST", API + "/compare", None, dict(CASE, analysis_at="2026-10-07T09:00")), 422, "invalid_payload"),
    ]
    for args, status, code in cases:
        r = handle(*args)
        assert r["status"] == status and r["body"] == {"ok": False, "error": r["body"]["error"]}, args
        assert r["body"]["error"]["code"] == code, (args, r["body"])
        assert "Traceback" not in json.dumps(r["body"])
    assert handle("GET", "/api/civic/v1/objects") is None   # чужие пути не перехватываются


def test_graph_listing_has_no_file_paths_and_shows_not_ready():
    d = handle("GET", API + "/graphs")["body"]["data"]
    assert all("file" not in g for g in d["items"])
    assert {g["evidence_type"] for g in d["items"]} == {"synthetic", "derived"}
    assert d["not_ready"][0]["mode"] == "driving"


def test_cases_reference_known_graphs_with_current_digest():
    d = handle("GET", API + "/cases")["body"]["data"]["items"]
    graphs = {g["id"]: g["digest"] for g in handle("GET", API + "/graphs")["body"]["data"]["items"]}
    for c in d:
        assert graphs[c["payload"]["graph_id"]] == c["payload"]["graph_digest"]
        assert c["evidence_type"] in ("synthetic", "hypothesis")
        assert handle("POST", API + "/compare", body=c["payload"])["status"] == 200


def test_ui_contract_and_safety():
    assert re.search(r"root\.CivicScenarios = \{ mount[,}]", JS)
    # round 13 lifecycle: клики только в явном режиме, Escape в capture с preventDefault, destroy снимает всё
    assert 'document.addEventListener("keydown", onKey, true)' in JS and "e.preventDefault()" in JS
    assert '"civic-scenarios:tool"' in JS and "if (!S.tool || !S.graph || S.destroyed) return;" in JS
    assert "document.removeEventListener(ev, fn, cap)" in JS and "map.off(ev, fn)" in JS
    assert "scenarioId" in JS and '"result:" + result.result_digest' in JS
    assert "innerHTML" not in JS and "insertAdjacentHTML" not in JS and "eval(" not in JS
    assert "document.body" not in JS                       # компонент не трогает body
    assert "new maplibregl.Map" not in JS                  # вторую карту не создаёт
    assert "localStorage" not in JS
    for lid in re.findall(r'id: (P \+ "[^"]+")', JS):
        assert lid.startswith('P + "')
    assert 'const P = "civic-r07-"' in JS
    for sel in re.findall(r"^\.([a-z0-9-]+)", CSS, flags=re.M):
        assert sel.startswith("civic-r07-"), sel
    assert "fetch(" not in JS                              # сеть только через api.request
