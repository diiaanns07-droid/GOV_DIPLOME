"""AST-A06 R2 (derived from REAL data R1b 'clean_weekday'): compare PTAL fixed reliability +2 min
with excess wait implied by observed headway irregularity: excess = E[H]/2 * CV^2
(formula = assumption, random passenger arrivals; see Shymkent pass A06-F025)."""
import json, statistics as st
r = json.load(open('r1/cv_sensitivity.json'))['clean_weekday']
rows = []
for k, (H, cv, n) in r.items():
    rt, d, band = k.split('/')
    rows.append({"key": k, "mean_headway_min": H, "cv": cv, "n": n,
                 "ptal_awt_min": round(H/2 + 2, 1),
                 "random_arrival_wait_min": round(H/2*(1+cv**2), 1),
                 "excess_wait_min": round(H/2*cv**2, 1)})
json.dump(rows, open('r1/ptal_vs_observed.json', 'w'), indent=1)
for x in rows: print(x)
ex = [x["excess_wait_min"] for x in rows]
print("excess wait min/median/max:", min(ex), st.median(ex), max(ex), "| bands with excess > 2 min:", sum(e > 2 for e in ex), "of", len(ex))
