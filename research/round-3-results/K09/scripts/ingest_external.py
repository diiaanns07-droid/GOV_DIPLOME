"""K09-T1: сборка внешнего набора external_v1 из результата workflow (писатель + слепой разметчик).

Вход: dataset/external_v1/raw_workflow_output.json (сохранённый как есть результат workflow).
В набор попадают только примеры, где эталон писателя и независимого разметчика совпал полностью
(status, reason, city, канонические ограничения). Расхождения сохраняются отдельно.
Запуск из корня репозитория: python3 research/round-3-results/K09/scripts/ingest_external.py
"""
import hashlib, json
from collections import Counter
from pathlib import Path

K = Path(__file__).resolve().parents[1]
E = K / "dataset/external_v1"


def canon_gold(g):
    c = g.get("constraints")
    if g["status"] != "ok" or c is None:
        cc = None
    else:
        inc = sorted(json.dumps(x, ensure_ascii=False, sort_keys=True) if isinstance(x, dict) else x for x in (c.get("include") or []))
        cc = {"include": inc, "exclude": sorted(c.get("exclude") or []), "budget": c.get("budget")}
    return {"status": g["status"], "reason": g.get("reason"), "city": g.get("city"), "constraints": cc}


def clean_gold(g):
    if g["status"] != "ok":
        return {"status": g["status"], "reason": g.get("reason"), "city": g.get("city"), "constraints": None}
    c = g.get("constraints") or {}
    out = {}
    if c.get("exclude"): out["exclude"] = c["exclude"]
    if c.get("include"): out["include"] = c["include"]
    if c.get("budget") is not None: out["budget"] = c["budget"]
    return {"status": "ok", "reason": None, "city": g.get("city"), "constraints": out}


def kappa(pairs):
    n = len(pairs)
    if not n: return None
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


raw = json.loads((E / "raw_workflow_output.json").read_text(encoding="utf-8"))
agreed, disagreed, pairs = [], [], []
for block in raw["results"]:
    lang = block["lang"]
    labels = {l["idx"]: l for l in block["labels"]}
    for i, it in enumerate(block["items"]):
        lab = labels.get(i)
        wg = canon_gold(it["gold"])
        ag = canon_gold(lab["gold"]) if lab else None
        pairs.append((f"{wg['status']}/{wg['reason']}", f"{ag['status']}/{ag['reason']}" if ag else "missing"))
        row = {"id": f"x-{lang}-{i + 1:02d}", "split": "external", "lang": lang, "template_id": "external",
               "class": it["intended_class"], "context_city": it["context_city"], "text": it["text"],
               "gold": clean_gold(it["gold"]), "synthetic": True,
               "author": f"workflow writer agent ({lang}); blind annotator agent ({lang})",
               "native_speaker_check": "required" if lang == "kk" else "recommended",
               "annotator_unsure": bool(lab and lab.get("unsure")), "annotator_note": (lab or {}).get("note")}
        if lab and wg == ag:
            agreed.append(row)
        else:
            disagreed.append({**row, "writer_gold": it["gold"], "annotator_gold": lab["gold"] if lab else None})
body = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in agreed)
(E / "t1_external.jsonl").write_text(body, encoding="utf-8")
(E / "disagreements.json").write_text(json.dumps(disagreed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
stats = {"items_total": len(pairs), "agreed_full_label": len(agreed), "disagreed": len(disagreed),
         "cohen_kappa_status_reason": kappa(pairs),
         "agreed_by_lang": dict(Counter(r["lang"] for r in agreed)),
         "agreed_by_status": dict(Counter(r["gold"]["status"] for r in agreed)),
         "t1_external_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
         "raw_sha256": hashlib.sha256((E / "raw_workflow_output.json").read_bytes()).hexdigest()}
(E / "agreement.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(json.dumps(stats, ensure_ascii=False, indent=1))
