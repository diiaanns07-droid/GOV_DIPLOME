"""Budget non-binding share per (n_candidates, budget_ratio) and hit rates restricted to |exact|>=2. Reads results/*.csv only."""
import csv, math
from collections import defaultdict
R = "/home/user/GOV_DIPLOME/research/round-8-results/K09/results/"
sc = {r["scenario_key"]: r for r in csv.DictReader(open(R + "scenarios.csv"))}
agg = defaultdict(lambda: [0, 0])
for r in sc.values():
    full = sum(math.comb(int(r["n_candidates"]), k) for k in range(int(r["max_selected"]) + 1))
    a = agg[(r["analysis"], int(r["n_candidates"]), r["budget_ratio"], r["max_selected"])]; a[0] += 1; a[1] += int(r["feasible_count"]) == full
for k in sorted(agg): print("non-binding", k, f"{agg[k][1]}/{agg[k][0]}")
runs = [r for r in csv.DictReader(open(R + "runs.csv")) if r["analysis"] == "main"]
t = defaultdict(lambda: [0, 0]); tn = defaultdict(lambda: [0, 0])
for r in runs:
    k = (r["algorithm"], r["objective"], r["n_candidates"], r["budget_ratio"]); t[k][0] += 1; t[k][1] += int(r["hit"])
    k2 = (r["algorithm"], r["objective"], r["budget_ratio"])
    if len(r["exact_ids"].split()) >= 2: tn[k2][0] += 1; tn[k2][1] += int(r["hit"])
for k in sorted(t): print("hit", k, f"{100*t[k][1]/t[k][0]:.1f}%")
for k in sorted(tn): print("hit |exact|>=2", k, f"{100*tn[k][1]/tn[k][0]:.1f}% n={tn[k][0]}")
