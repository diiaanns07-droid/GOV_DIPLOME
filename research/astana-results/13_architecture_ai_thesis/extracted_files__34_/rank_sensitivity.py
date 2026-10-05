"""AST-A13 E6: rank stability of the hackathon optimum under parameter uncertainty.
Model: astana_hackathon (SYNTHETIC training data, commit 834a25f). Perturbations are SYNTHETIC
assumptions (not calibrated): weights x LogNormal(0, sigma_w) renormalised; each effect e_mk x U(1-a, 1+a).
Question: is 'the best plan' a stable object worth showing as a single point?"""
import copy, json, sys, time
sys.path.insert(0, "/home/claude/stupits")
import numpy as np, engine
from engine.data import CityData
raw0 = json.load(open("/home/claude/stupits/data/city_data.json"))
def key(dec): return " + ".join(sorted(f"{d['measure']}@{d['district'] or 'city'}" for d in dec))
base = engine.optimize(top_n=10)
base_top = [key(r["decisions"]) for r in base["results"]]
def run(n, sigma_w, a, seed):
    rng = np.random.default_rng(seed); out = []
    for _ in range(n):
        raw = copy.deepcopy(raw0)
        ks = list(raw["indicators"]); w = np.array([raw["indicators"][k]["weight"] for k in ks])
        w = w * rng.lognormal(0, sigma_w, len(w)); w = w / w.sum()
        for k, v in zip(ks, w): raw["indicators"][k]["weight"] = float(v)
        for m in raw["measures"]:
            m["effects"] = {k: float(v * rng.uniform(1 - a, 1 + a)) for k, v in m["effects"].items()}
        raw["reference_checks"] = {}
        for d in raw["districts"]: d.pop("base_D", None)
        r = engine.optimize(top_n=10, data=CityData(raw, source="perturbed-synthetic"))
        top = [key(x["decisions"]) for x in r["results"]]
        # score of base-best plan under perturbed params, and regret
        s_base = engine.simulate(base["results"][0]["decisions"], data=CityData(raw, source="p"))["score"]
        out.append({"top1": top[0], "base_top1_rank": top.index(base_top[0]) + 1 if base_top[0] in top else None,
                    "overlap_top10": len(set(top) & set(base_top)), "regret_of_base_top1": round(r["results"][0]["score"] - s_base, 3)})
    n_ = len(out)
    return {"n": n_, "sigma_w": sigma_w, "effect_pm": a,
            "base_top1_still_top1": sum(o["base_top1_rank"] == 1 for o in out) / n_,
            "base_top1_in_top10": sum(o["base_top1_rank"] is not None for o in out) / n_,
            "distinct_top1": len({o["top1"] for o in out}),
            "mean_overlap_top10": round(float(np.mean([o["overlap_top10"] for o in out])), 2),
            "regret_median": float(np.median([o["regret_of_base_top1"] for o in out])),
            "regret_p95": float(np.percentile([o["regret_of_base_top1"] for o in out], 95)),
            "most_common_top1": max({o["top1"] for o in out}, key=lambda k: sum(o["top1"] == k for o in out))}
t = time.perf_counter()
res = {"base_top1": base_top[0], "base_score": base["results"][0]["score"],
       "runs": [run(60, 0.1, 0.1, 1), run(60, 0.2, 0.2, 2), run(60, 0.3, 0.3, 3)],
       "seconds": round(time.perf_counter() - t, 1),
       "versions": {"python": sys.version.split()[0], "numpy": np.__version__}}
print(json.dumps(res, ensure_ascii=False, indent=1))
