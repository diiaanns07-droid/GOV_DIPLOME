#!/usr/bin/env python3
"""Детерминированные наборы исключений по атрибутам исходных записей (семейство «attribute» протокола T3).

Источник: data.js и evidence.js BUILD @ d865dd4 (git show, байты фиксируются sha256).
- low_confidence: Overture confidence < 0.5 (порог задан до прогона);
- qa_flagged: записи с QA-метками BUILD (COLOCATED, POSSIBLE_DUPLICATE, CATEGORY_DOUBT — правила facts.qaOf);
- union: объединение.
Пустые и совпадающие наборы не включаются (дубль не меняет результат, но не нужен).
Это гипотетические исключения для анализа допущений о данных, а не утверждение, что записи ошибочны.

  python3 scripts/t3_attribute_sets.py   -> config/t3_attribute_sets.json
"""
import hashlib, json, subprocess
from pathlib import Path

K = Path(__file__).resolve().parents[1]
REPO = K.parents[2]
SHA = "d865dd4a124291e10dd0b7bb1d9eada20d34c268"
SLICES = {"shymkent_school": ("shymkent", "school"), "astana_clinic": ("astana", "outpatient_clinic")}
THRESHOLD = 0.5


def js_obj(path):
    raw = subprocess.run(["git", "show", f"{SHA}:{path}"], cwd=REPO, capture_output=True, check=True).stdout
    s = raw.decode("utf-8")
    i = s.index("{")
    j = s.rstrip().rstrip(";").rstrip()
    return json.loads(s[i:len(j)]), hashlib.sha256(raw).hexdigest()


def main():
    data, dsha = js_obj("prototypes/city-evidence/web/data.js")
    ev, esha = js_obj("prototypes/city-evidence/web/evidence.js")
    out = {"build_sha": SHA, "data_js_sha256": dsha, "evidence_js_sha256": esha, "confidence_threshold": THRESHOLD,
           "provenance": "исходные записи — observed_secondary (Overture places_social в срезе BUILD); исключения — hypothetical", "slices": {}}
    for sid, (city, cat) in SLICES.items():
        recs = [p for p in data["cities"][city]["places"] if p.get("group") == cat]
        ids = {p["id"] for p in recs}
        qa = ev["cities"][city]["qa"]
        flagged = set()
        for g in qa["colocated"]:
            flagged |= set(g["ids"]) & ids
        for d in qa["possible_duplicates"]:
            flagged |= {d["a"], d["b"]} & ids
        flagged |= set(qa["category_doubt"]) & ids
        low = {p["id"] for p in recs if isinstance(p.get("confidence"), (int, float)) and p["confidence"] < THRESHOLD}
        cand = [("low_confidence", "Overture confidence < 0.5", low), ("qa_flagged", "QA-метки BUILD (колокация, возможный дубль, сомнение в категории)", flagged),
                ("low_or_qa", "confidence < 0.5 или QA-метка", low | flagged)]
        cases, seen = [], set()
        for cid, label, s in cand:
            key = tuple(sorted(s))
            if not s or key in seen:
                continue
            seen.add(key)
            cases.append({"id": cid, "label": label, "disabled_source_ids": sorted(s)})
        out["slices"][sid] = {"n_sources": len(ids), "low_confidence": len(low), "qa_flagged": len(flagged), "cases": cases}
    p = K / "config/t3_attribute_sets.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({s: {k: v for k, v in d.items() if k != "cases"} | {"cases": [c["id"] for c in d["cases"]]} for s, d in out["slices"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
