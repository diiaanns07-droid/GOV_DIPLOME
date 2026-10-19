"""Оценка разбора R04 на наборе R02: весь набор, dev (чётные группы — по ним разбирались ошибки) и отложенная половина
(нечётные — не смотрелись). Код R04 берётся из дерева argv[1] (копия сборки + код R04), оценщик и эталон — R02."""
import importlib.util, json, sys, time
TREE = sys.argv[1]
SCR = __import__("os").environ.get("R04_EVAL_DIR", ".")  # папка: r02/ (набор и эталон R02), r02wt/ (дерево R02 с оценщиком)
sys.path.insert(0, TREE)
spec = importlib.util.spec_from_file_location("demo_intake_eval", f"{SCR}/r02wt/ml/datasets/demo_intake_eval.py")
ev = importlib.util.module_from_spec(spec)
sys.path.insert(1, f"{SCR}/r02wt")
spec.loader.exec_module(ev)
from ui.civic_ml_api import intake
gold = json.load(open(f"{SCR}/r02/intake_night_v1.gold.json", encoding="utf-8"))
texts = [{"id": t["id"], "text": t["text"]} for t in json.load(open(f"{SCR}/r02/intake_night_v1.json", encoding="utf-8"))["texts"]]
t0 = time.perf_counter()
pred = intake.analyze(texts, keep=False)
wall = round((time.perf_counter() - t0) * 1000)
streets = ev._street_names()

def half(parity):
    groups = [g for g in gold["groups"] if parity is None or int(g["id"].split("-")[1]) % 2 == parity]
    keep = {tid for g in groups for tid in g["text_ids"]}
    gh = dict(gold, groups=groups, items=[i for i in gold["items"] if i["id"] in keep])
    tasks = []
    for t in pred["tasks"]:
        ids = [i for i in t["text_ids"] if i in keep]
        if ids:
            tasks.append(dict(t, text_ids=ids))
    return ev.evaluate({"summary": pred["summary"], "tasks": tasks}, gh, streets)

out = {"version": intake.VERSION, "wall_ms": wall, "summary": pred["summary"]}
for name, parity in (("full", None), ("dev_even", 0), ("heldout_odd", 1)):
    r = half(parity)
    out[name] = {"texts": r["texts"], "tasks": r["tasks"], "gold_groups": r["gold_groups"],
                 "lead": r["services"]["lead_accuracy"], "set": r["services"]["exact_set"],
                 "two_rec": r["services"]["two_services_recall"], "two_prec": r["services"]["two_services_precision"],
                 "dup_p": r["duplicates"]["pairwise_precision"], "dup_r": r["duplicates"]["pairwise_recall"],
                 "dup_f1": r["duplicates"]["pairwise_f1"], "groups_exact": r["duplicates"]["groups_exact"],
                 "places": r["places"]["found_share"], "abstain": r["places"]["no_address_abstained"],
                 "urg_rec": r["urgent"]["recall_texts"], "urg_groups": r["urgent"]["recall_groups"],
                 "urg_prec": r["urgent"]["precision_texts"]}
print(json.dumps(out, ensure_ascii=False, indent=1))
if len(sys.argv) > 2:
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
