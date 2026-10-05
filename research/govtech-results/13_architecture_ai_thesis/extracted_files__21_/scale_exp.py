"""A13 experiment: does STUPITS engine generalize to N districts / M measures, and how
does exhaustive search scale? ALL CITY DATA HERE IS SYNTHETIC (derived from Astana TZ data
by cloning districts/measures). Not Shymkent data."""
import copy, json, sys, time, platform
sys.path.insert(0, "/home/claude/stupits")
import numpy as np, engine
from engine.data import CityData

raw0 = json.load(open("/home/claude/stupits/data/city_data.json"))

def synth(n_d, n_m, seed=0):
    rng = np.random.default_rng(seed)
    raw = copy.deepcopy(raw0)
    base = raw["districts"]
    ds = []
    for i in range(n_d):
        d = copy.deepcopy(base[i % len(base)])
        d["id"] = f"syn_d{i}"; d["name"] = f"SynDistrict{i}"
        d["indicators"] = {k: int(np.clip(v + rng.integers(-5, 6), 0, 100)) for k, v in d["indicators"].items()}
        d.pop("base_D", None)
        ds.append(d)
    sh = rng.dirichlet(np.ones(n_d)); sh = np.round(sh, 4); sh[-1] = round(1 - sh[:-1].sum(), 4)
    for d, s in zip(ds, sh): d["population_share"] = float(s)
    raw["districts"] = ds
    ms = copy.deepcopy(raw0["measures"])
    extra = []
    i = 0
    while len(ms) + len(extra) < n_m:
        m = copy.deepcopy(raw0["measures"][i % 14]); m["id"] = f"MX{i}"; m["name"] += " (клон)"
        m["cost"] = int(max(5, m["cost"] + rng.integers(-3, 4))); extra.append(m); i += 1
    raw["measures"] = (ms + extra)[:n_m]
    keep = {m["id"] for m in raw["measures"]}
    raw["synergies"] = [s for s in raw["synergies"] if set(s["pair"]) <= keep]
    raw["incompatibilities"] = [s for s in raw["incompatibilities"] if set(s["pair"]) <= keep]
    raw["reference_checks"] = {}
    return raw

print("python", platform.python_version(), "numpy", np.__version__, platform.machine())
# 0) reproduce official Astana numbers
d0 = engine.load_data()
t = time.perf_counter(); r = engine.optimize(top_n=3, data=d0); dt = time.perf_counter() - t
print("ASTANA official: best", r["plans"][0]["score"] if "plans" in r else list(r.keys())[:8], f"time={dt:.2f}s")
for n_d, n_m in [(5, 14), (6, 14), (8, 14), (5, 20), (6, 20), (8, 20)]:
    raw = synth(n_d, n_m)
    try:
        d = CityData(raw, source="synthetic")
    except Exception as e:
        print(n_d, n_m, "LOAD FAIL:", type(e).__name__, str(e)[:200]); continue
    t = time.perf_counter()
    try:
        r = engine.optimize(top_n=1, data=d)
        dt = time.perf_counter() - t
        keys = {k: r[k] for k in r if k in ("scenarios_total", "scenarios_valid", "combos_total", "searched")}
        print(f"SYN districts={n_d} measures={n_m}: ok time={dt:.2f}s {keys if keys else sorted(r)[:10]}")
    except Exception as e:
        print(n_d, n_m, "OPT FAIL:", type(e).__name__, str(e)[:200], f"after {time.perf_counter()-t:.1f}s")
