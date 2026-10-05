"""AST-A13 E7 — ISOLATED PROTOTYPE (outside the STUPITS repo; repo is not modified).
Checks: (1) the frozen hackathon model can be wrapped as configuration 'astana_hackathon'
without touching engine code and reproduces its references; (2) a 'real' configuration whose
inputs are missing/synthetic is refused a composite score; (3) legacy request bodies (no city)
route to astana_hackathon and give byte-identical canonical JSON; (4) result_id is a content hash.
Names (astana_hackathon, astana_real, shymkent_real) are PROPOSED, not existing code."""
import hashlib, json, sys
from pathlib import Path
REPO = Path("/home/claude/stupits"); sys.path.insert(0, str(REPO))
import engine
from engine.data import CityData

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canon(o): return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

ENGINE_VERSION = "stupits@834a25f"
CONFIGS = {
  "astana_hackathon": {"city": "astana", "mode": "training", "model": "akim5h-tz-2026",
     "data_files": {"city_data": str(REPO/"data/city_data.json"), "events": str(REPO/"data/events.json")},
     "input_kind": "synthetic", "composite_score_allowed": True,
     "label": "Учебная модель хакатона. Не измерение и не прогноз реального города."},
  "astana_real": {"city": "astana", "mode": "city", "model": None, "observations": [
     {"indicator_id": "population_total", "unit_id": "astana", "period": None, "value": None,
      "kind": "observed", "source_refs": [], "note": "stat.gov.kz не открыт из среды AST-A13 → null"}],
     "composite_score_allowed": False},
  "shymkent_real": {"city": "shymkent", "mode": "city", "model": None, "observations": [], "composite_score_allowed": False},
}
def data_version(cfg_id):
    c = CONFIGS[cfg_id]
    if "data_files" in c: return cfg_id + "@" + hashlib.sha256("".join(sha(p) for p in c["data_files"].values()).encode()).hexdigest()[:12]
    return cfg_id + "@" + hashlib.sha256(canon(c.get("observations", [])).encode()).hexdigest()[:12]

class Refused(Exception): pass
def compute(cfg_id, op, body):
    c = CONFIGS[cfg_id]
    if op in ("simulate", "optimize", "baseline") and not c["composite_score_allowed"]:
        missing = [o["indicator_id"] for o in c.get("observations", []) if o["value"] is None]
        raise Refused(f"{cfg_id}: композитный индекс не определён для реальной конфигурации; "
                      f"нет значений: {missing or 'нет наблюдений'}. Показывайте наблюдения по отдельности.")
    data = engine.load_data(c["data_files"]["city_data"])
    out = {"simulate": lambda: engine.simulate(body["decisions"], data=data),
           "optimize": lambda: engine.optimize(top_n=body.get("top_n", 10), constraints=body.get("constraints"), data=data),
           "baseline": lambda: engine.baseline(data=data)}[op]()
    dv = data_version(cfg_id)
    rid = "sha256:" + hashlib.sha256(canon({"cfg": cfg_id, "dv": dv, "op": op, "body": body, "engine": ENGINE_VERSION}).encode()).hexdigest()
    return {"result_id": rid, "data_version": dv, "mode": c["mode"], "label": c.get("label"), "outputs": out}

def legacy(op, body):  # old /api/* without a city → frozen hackathon config
    return compute("astana_hackathon", op, body)

if __name__ == "__main__":
    TZ = [{"measure":"M7","district":"nura"},{"measure":"M8","district":"nura"},{"measure":"M10","district":"nura"},
          {"measure":"M12","district":None},{"measure":"M5","district":"saryarka"}]
    rep = {}
    b = compute("astana_hackathon", "baseline", {}); rep["baseline_score"] = b["outputs"]["score"]
    s = compute("astana_hackathon", "simulate", {"decisions": TZ}); rep["tz_example"] = s["outputs"]["score"]
    o = compute("astana_hackathon", "optimize", {"top_n": 1}); rep["best"] = o["outputs"]["results"][0]["score"]
    rep["references_ok"] = (rep["baseline_score"], rep["tz_example"], rep["best"]) == (52.56, 56.54, 57.24)
    direct = engine.simulate(TZ)  # engine called exactly as the old server does
    rep["legacy_byte_identical"] = canon(legacy("simulate", {"decisions": TZ})["outputs"]) == canon(direct)
    rep["result_id_deterministic"] = compute("astana_hackathon", "simulate", {"decisions": TZ})["result_id"] == s["result_id"]
    rep["result_id"] = s["result_id"]; rep["data_version"] = s["data_version"]
    for cid in ("astana_real", "shymkent_real"):
        try: compute(cid, "simulate", {"decisions": TZ}); rep[cid] = "NOT REFUSED (bug)"
        except Refused as e: rep[cid] = "refused: " + str(e)
    rep["golden_sha256_simulate_tz"] = hashlib.sha256(canon(direct).encode()).hexdigest()
    print(json.dumps(rep, ensure_ascii=False, indent=1))
