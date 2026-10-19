"""Разбор ошибок R04 на наборе R02 — только группы dev (чётный номер группы). Отложенная половина (нечётные) не смотрится."""
import json, sys, collections
SCR = __import__("os").environ.get("R04_EVAL_DIR", ".")  # папка: r02/ (набор и эталон R02), r02wt/ (дерево R02 с оценщиком)
gold = json.load(open(f"{SCR}/r02/intake_night_v1.gold.json", encoding="utf-8"))
pred = json.load(open(sys.argv[1], encoding="utf-8"))
texts = {t["id"]: t["text"] for t in json.load(open(f"{SCR}/r02/intake_night_v1.json", encoding="utf-8"))["texts"]}
dev_groups = [g for g in gold["groups"] if int(g["id"].split("-")[1]) % 2 == 0]
dev_ids = {tid for g in dev_groups for tid in g["text_ids"]}
gi = {i["id"]: i for i in gold["items"]}
task_of = {tid: t for t in pred["tasks"] for tid in t["text_ids"]}
section = sys.argv[2] if len(sys.argv) > 2 else "all"
if section in ("all", "merge"):
    print("== DEV: группы, разбитые на несколько задач")
    for g in dev_groups:
        if len(g["text_ids"]) < 2: continue
        tasks = collections.OrderedDict()
        for tid in g["text_ids"]:
            t = task_of[tid]; tasks.setdefault(t["id"], []).append(tid)
        if len(tasks) > 1:
            print(f"-- {g['id']} {g['category']}/{g['subtopic']} @ {g['place']['target'] and g['place']['target'].get('label_ru')} ({len(g['text_ids'])} текстов -> {len(tasks)} задач)")
            for tk, ids in tasks.items():
                t = next(x for x in pred["tasks"] if x["id"] == tk)
                print(f"   {tk} [{t['category']}/{t['subtopic']}] {t['target'] and t['target']['label_ru']} n={len(ids)}: {texts[ids[0]][:90]}")
if section in ("all", "place"):
    print("== DEV: места не найдены / не те")
    for tid in sorted(dev_ids):
        gp = next(g for g in dev_groups if tid in g["text_ids"])["place"]
        if gp["target"] is None: continue
        t = task_of[tid]; pid = t["target"] and t["target"]["id"]
        ok = pid in gp["accept_ids"] or (t["target"] and gp.get("street_ru") and t["target"]["label_ru"].casefold() == gp["street_ru"].casefold())
        if not ok:
            print(f"   {tid} gold={gp['target']['label_ru']} | pred={t['target'] and t['target']['label_ru']} | {texts[tid][:110]}")
if section in ("all", "service"):
    print("== DEV: ведущая служба не та")
    for tid in sorted(dev_ids):
        t = task_of[tid]; g = gi[tid]
        lead = next((s["id"] for s in t["services"] if s["role"] == "lead"), None)
        glead = next((s["id"] for s in g["services"] if s["role"] == "lead"), None)
        if lead != glead:
            print(f"   {tid} gold={g['category']}/{g['subtopic']}:{glead} | pred={t['category']}/{t['subtopic']}:{lead} | {texts[tid][:100]}")
if section in ("all", "urgent"):
    print("== DEV: срочность")
    for tid in sorted(dev_ids):
        t = task_of[tid]; g = gi[tid]
        if bool(t["urgent"]) != bool(g["urgent"]):
            print(f"   {tid} gold={g['urgent']}({g['urgent_why']}) pred={t['urgent']}({t.get('urgent_rule')}) | {texts[tid][:100]}")
