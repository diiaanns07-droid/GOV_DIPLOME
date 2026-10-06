"""K06 round 9 stage 3: compare optimizeResilience output of another implementation with K06 independent gold.
  python3 compare_resilience_js.py --fixture fixtures/resilience_gold.json --export /tmp/res_problems.json
  python3 compare_resilience_js.py --fixture fixtures/resilience_gold.json --candidate-json out.json [--json report.json]
Compared (math only; internal digests are never compared byte-wise): status, feasible_count, nominal and robust
selected IDs, robust worst_vector (null for unknown max) and worst_case_ids, price of robustness (metres, 1e-9).
Accepted aliases: selected_ids|ids; price_of_robustness_m|price_m. A run file with status NOT_RUN gives NOT_RUN (exit 2),
never PASS. Exit 1 on any FAIL/MISSING/ERROR."""
import argparse, json, sys


def view(r):
    if r is None:
        return None
    if r.get("status") != "optimal":
        return {"status": r.get("status")}
    pick = lambda p: sorted(p.get("selected_ids", p.get("ids", [])))
    price = r.get("price_of_robustness_m", r.get("price_m"))
    return {"status": "optimal", "feasible_count": r.get("feasible_count"),
            "nominal": pick(r["nominal"]), "robust": pick(r["robust"]),
            "robust_W": r["robust"].get("worst_vector"), "robust_worst": sorted(r["robust"].get("worst_case_ids") or []),
            "price": None if price is None else round(price, 9)}


def compare(doc, cand):
    rep = {"implementation": cand.get("implementation"), "commit": cand.get("commit"), "cases": {}}
    if cand.get("status") == "NOT_RUN":
        rep["summary"] = {"NOT_RUN": len(doc["cases"])}; rep["reason"] = cand.get("reason")
        return rep
    res = cand.get("results", {})
    for c in doc["cases"]:
        want, got = view(c["gold"]), res.get(c["case"])
        if got is None:
            rep["cases"][c["case"]] = {"status": "MISSING"}; continue
        if got.get("status") == "error":
            rep["cases"][c["case"]] = {"status": "ERROR", "error": got.get("error")}; continue
        try:
            g = view(got)
        except (KeyError, TypeError, AttributeError) as e:
            rep["cases"][c["case"]] = {"status": "FAIL", "error": f"unreadable: {e!r}"}; continue
        d = {k: {"gold": want.get(k), "candidate": g.get(k)} for k in sorted(set(want) | set(g)) if want.get(k) != g.get(k)}
        rep["cases"][c["case"]] = {"status": "PASS" if not d else "FAIL", **({"diff": d} if d else {})}
    st = [v["status"] for v in rep["cases"].values()]
    rep["summary"] = {s: st.count(s) for s in sorted(set(st))}
    return rep


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--fixture", required=True)
    ap.add_argument("--candidate-json"); ap.add_argument("--export"); ap.add_argument("--json")
    a = ap.parse_args()
    doc = json.load(open(a.fixture, encoding="utf-8"))
    if a.export:
        json.dump({"cases": {c["case"]: {"context": c["context"], "envelope": c["envelope"]} for c in doc["cases"]}},
                  open(a.export, "w", encoding="utf-8"), ensure_ascii=False)
        print(len(doc["cases"]), "problems ->", a.export)
    if a.candidate_json:
        rep = compare(doc, json.load(open(a.candidate_json, encoding="utf-8")))
        if a.json:
            json.dump(rep, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        for n, v in rep["cases"].items():
            if v["status"] != "PASS":
                print(v["status"], n, json.dumps(v.get("diff") or v.get("error") or "", ensure_ascii=False)[:300])
        print(rep["summary"])
        if "NOT_RUN" in rep["summary"]:
            return 2
        return 0 if set(rep["summary"]) <= {"PASS"} else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
