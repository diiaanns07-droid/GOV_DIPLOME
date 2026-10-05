"""K09-E6b: параметризованная копия метода AST-A13-E6 (rank_sensitivity.py).

Метод не меняется: веса x LogNormal(0, sigma) с нормировкой, каждый эффект e_mk x U(1-a, 1+a),
полный перебор top-10, регрет базового топ-1. Модель — учебная astana_hackathon (СИНТЕТИКА).
Отличия от оригинала: путь к репозиторию берётся из расположения файла; n и seed задаются
аргументами; дополнительно сохраняются сырые выборки и 95% интервалы Уилсона для долей.

Проверка эквивалентности: при --n 60 --seeds 1 2 3 агрегаты должны совпасть с
research/astana-results/13_architecture_ai_thesis/extracted_files__34_/rank_sensitivity_result.json.

Запуск из корня репозитория:
    python research/next-round/K09/scripts/e6b_rank_sensitivity.py --n 60 --seeds 1 2 3 --out <file>
"""
import argparse, copy, json, math, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402
import engine  # noqa: E402
from engine.data import CityData  # noqa: E402

LEVELS = [0.1, 0.2, 0.3]  # sigma_w = a, как в AST-A13-E6


def key(dec):
    return " + ".join(sorted(f"{d['measure']}@{d['district'] or 'city'}" for d in dec))


def wilson(k, n, z=1.959964):
    if n == 0:
        return [None, None]
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(c - h, 4), round(c + h, 4)]


def run(raw0, base, base_top, n, s, a, seed):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        raw = copy.deepcopy(raw0)
        ks = list(raw["indicators"])
        w = np.array([raw["indicators"][k]["weight"] for k in ks])
        w = w * rng.lognormal(0, s, len(w)); w = w / w.sum()
        for k, v in zip(ks, w):
            raw["indicators"][k]["weight"] = float(v)
        for m in raw["measures"]:
            m["effects"] = {k: float(v * rng.uniform(1 - a, 1 + a)) for k, v in m["effects"].items()}
        raw["reference_checks"] = {}
        for d in raw["districts"]:
            d.pop("base_D", None)
        r = engine.optimize(top_n=10, data=CityData(raw, source="perturbed-synthetic"))
        top = [key(x["decisions"]) for x in r["results"]]
        s_base = engine.simulate(base["results"][0]["decisions"], data=CityData(raw, source="p"))["score"]
        out.append({"top1": top[0], "base_top1_rank": top.index(base_top[0]) + 1 if base_top[0] in top else None,
                    "overlap_top10": len(set(top) & set(base_top)),
                    "regret_of_base_top1": round(r["results"][0]["score"] - s_base, 3)})
    n_ = len(out)
    k1 = sum(o["base_top1_rank"] == 1 for o in out)
    k10 = sum(o["base_top1_rank"] is not None for o in out)
    agg = {"n": n_, "sigma_w": s, "effect_pm": a, "seed": seed,
           "base_top1_still_top1": k1 / n_, "base_top1_still_top1_wilson95": wilson(k1, n_),
           "base_top1_in_top10": k10 / n_, "base_top1_in_top10_wilson95": wilson(k10, n_),
           "distinct_top1": len({o["top1"] for o in out}),
           "mean_overlap_top10": round(float(np.mean([o["overlap_top10"] for o in out])), 2),
           "regret_median": float(np.median([o["regret_of_base_top1"] for o in out])),
           "regret_p95": float(np.percentile([o["regret_of_base_top1"] for o in out], 95)),
           "most_common_top1": max({o["top1"] for o in out}, key=lambda k: sum(o["top1"] == k for o in out))}
    return agg, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--seeds", type=int, nargs=3, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    raw0 = json.loads((ROOT / "data/city_data.json").read_text(encoding="utf-8"))
    base = engine.optimize(top_n=10)
    base_top = [key(r["decisions"]) for r in base["results"]]
    t = time.perf_counter()
    runs, samples = [], []
    for lvl, seed in zip(LEVELS, args.seeds):
        agg, out = run(raw0, base, base_top, args.n, lvl, lvl, seed)
        runs.append(agg); samples.append({"sigma_w": lvl, "seed": seed, "samples": out})
    res = {"label": "SYNTHETIC training model astana_hackathon; perturbation ranges are assumptions",
           "base_top1": base_top[0], "base_score": base["results"][0]["score"], "runs": runs,
           "seconds": round(time.perf_counter() - t, 1),
           "versions": {"python": sys.version.split()[0], "numpy": np.__version__}}
    Path(args.out).write_text(json.dumps({"result": res, "raw_samples": samples}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
