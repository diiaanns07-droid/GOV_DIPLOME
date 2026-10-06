#!/usr/bin/env python3
"""Адаптер формы ответа K05 resilience.js → поля, которые читает K06 compare_resilience_js.py.
Меняет только представление (не математику и не gold):
  worst_vector {unknown_count, weighted_sum_mm, max_mm} → [unknown, sum, max|null];
  price_of_resilience_m → также price_of_robustness_m.
  python3 map_to_k06.py IN.json OUT.json
"""
import json, sys

def vec(w):
    return None if w is None else [w["unknown_count"], w["weighted_sum_mm"], w["max_mm"]]

src, dst = sys.argv[1], sys.argv[2]
doc = json.load(open(src, encoding="utf-8"))
for name, r in (doc.get("results") or {}).items():
    if not isinstance(r, dict) or r.get("status") != "optimal":
        continue
    for k in ("nominal", "robust"):
        if r.get(k):
            r[k] = {"selected_ids": r[k]["selected_ids"], "worst_vector": vec(r[k]["worst_vector"]), "worst_case_ids": r[k]["worst_case_ids"]}
    r["price_of_robustness_m"] = r.get("price_of_resilience_m")
json.dump(doc, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
print("mapped", len(doc.get("results") or {}), "->", dst)
