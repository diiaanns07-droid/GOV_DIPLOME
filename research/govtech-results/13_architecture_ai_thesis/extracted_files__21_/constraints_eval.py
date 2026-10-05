"""A13 experiment: harness for 'instruction -> validated constraints'.
Gold set is SYNTHETIC (written by A13 for the Astana training model). No LLM is called.
Baseline = deterministic keyword parser. Metrics: schema-valid rate, exact match, slot F1,
engine-accepted rate (optimize() returns no errors)."""
import json, re, sys
sys.path.insert(0, "/home/claude/stupits")
import jsonschema, engine
from agent.tools import SCHEMAS
schema = SCHEMAS["optimize"][1]
data = engine.load_data()

GOLD = [  # synthetic
 ("Найди лучший план без ЛРТ", {"exclude": ["M3"]}),
 ("Без ЛРТ, школа в Нуре, бюджет до 80", {"exclude": ["M3"], "include": [{"measure": "M7", "district": "nura"}], "budget": 80}),
 ("Обязательно поликлиника в Нуре", {"include": [{"measure": "M8", "district": "nura"}]}),
 ("Хочу уложиться в 70 у.е.", {"budget": 70}),
 ("Не трогай частный сектор и не строй ЛРТ", {"exclude": ["M5", "M3"]}),
 ("Парк в Есиле и умные светофоры обязательно", {"include": [{"measure": "M4", "district": "esil"}, "M2"]}),
 ("Какой план лучший, если денег 85?", {"budget": 85}),
 ("Исключи выделенные полосы, оставь камеры в Сарыарке", {"exclude": ["M1"], "include": [{"measure": "M10", "district": "saryarka"}]}),
 ("Без модернизации сетей, бюджет 90, обязательно цифровая платформа обращений", {"exclude": ["M13"], "budget": 90, "include": ["M12"]}),
 ("Спорт-хабы в Байконуре и в Алматы", {"include": [{"measure": "M9", "district": "baikonur"}, {"measure": "M9", "district": "almaty"}]}),  # engine should reject: one measure twice
 ("Поставь школу где-нибудь", {"include": ["M7"]}),
 ("Без светофоров и без озеленения", {"exclude": ["M2", "M6"]}),
]
LEX = {"ЛРТ": "M3", "светофор": "M2", "частный сектор": "M5", "полос": "M1", "парк": "M4", "озеленени": "M6",
       "школ": "M7", "поликлиник": "M8", "спорт-хаб": "M9", "камер": "M10", "переход": "M11",
       "платформ": "M12", "сет": "M13", "бригад": "M14"}
DIST = {"нур": "nura", "есил": "esil", "сарыарк": "saryarka", "байконур": "baikonur", "алмат": "almaty"}
NEG = re.compile(r"(без|не\s+\w+|исключи)\s*$", re.I)

def baseline_parse(text):
    t = text.lower(); out = {}
    m = re.search(r"(\d{2,3})", t)
    if m: out["budget"] = int(m.group(1))
    clauses = re.split(r",| и (?=не|без|обязательно)", t)
    for cl in clauses:
        for key, mid in LEX.items():
            pos = cl.find(key.lower())
            if pos < 0: continue
            neg = bool(re.search(r"(без|не\b|не трогай|не строй|исключи)", cl[:pos]))
            if neg: out.setdefault("exclude", []).append(mid); continue
            dists = [d for k, d in DIST.items() if k in cl[pos:]]
            if data.is_city(mid) or not dists: out.setdefault("include", []).append(mid)
            else:
                for d in dists: out.setdefault("include", []).append({"measure": mid, "district": d})
    for k in ("exclude", "include"):
        if k in out:
            seen = []; [seen.append(x) for x in out[k] if x not in seen]; out[k] = seen
    return out

def slots(c):
    s = set()
    for x in c.get("exclude", []): s.add(("ex", x))
    for x in c.get("include", []): s.add(("in", json.dumps(x, sort_keys=True)))
    if c.get("budget") is not None: s.add(("budget", c["budget"]))
    return s

rows = []; tp = fp = fn = 0
for text, gold in GOLD:
    pred = baseline_parse(text)
    try: jsonschema.validate({"constraints": pred}, schema); valid = True
    except jsonschema.ValidationError: valid = False
    r = engine.optimize(top_n=1, constraints=pred, data=data)
    g, p = slots(gold), slots(pred); tp += len(g & p); fp += len(p - g); fn += len(g - p)
    gold_r = engine.optimize(top_n=1, constraints=gold, data=data)
    rows.append({"text": text, "pred": pred, "gold": gold, "schema_valid": valid, "exact": g == p,
                 "engine_errors_pred": bool(r.get("errors")), "engine_errors_gold": bool(gold_r.get("errors"))})
prec = tp / (tp + fp) if tp + fp else 0; rec = tp / (tp + fn) if tp + fn else 0
summary = {"n": len(rows), "schema_valid": sum(r["schema_valid"] for r in rows), "exact_match": sum(r["exact"] for r in rows),
           "slot_precision": round(prec, 3), "slot_recall": round(rec, 3),
           "slot_f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0,
           "gold_rejected_by_engine": [r["text"] for r in rows if r["engine_errors_gold"]]}
print(json.dumps({"summary": summary, "misses": [r for r in rows if not r["exact"]]}, ensure_ascii=False, indent=1))
