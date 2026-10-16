"""Оценка «ИИ-разбора пачки» на наборе R02 «обращения за ночь» (раунд 15+, поправка П3) — метрики из П3.

    python3 -m ml.datasets.demo_intake_eval ответ.json            # ответ analyze() R04 на тексты набора
    python3 -m ml.datasets.demo_intake_eval ответ.json --json     # то же одной строкой JSON (для FACTS R14)

ответ.json — то, что вернул analyze(texts) или POST intake/analyze {sample: "night"}: {"summary": {...},
"tasks": [{"services": [{"id", "role"}], "target": {"kind", "id"} | null, "text_ids": [...], "urgent": bool}, ...]}.
text_ids — id текстов набора (night-001 …) или номера строк с нуля в порядке набора (0, 1, …).

Метрики (эталон — intake_night_v1.gold.json, размечен правилами R02, без моделей R04):
  службы     — у текста ведущая служба задачи = ведущей службе эталона; полное совпадение набора служб;
               «две службы»: полнота и точность по текстам;
  повторы    — попарная F1: пара текстов в одной задаче ↔ в одной группе эталона; число задач против числа групп;
  места      — доля текстов с местом в эталоне, у задачи которых цель верная (id из accept_ids; для улицы — любой
               участок той же улицы); у текстов без места верно «адрес уточнить» (target null);
  срочность  — полнота срочных: по текстам и по группам (группа поймана, если не меньше половины её текстов —
               в срочных задачах); точность — по текстам;
  время      — summary.ms ответа (если есть).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from ml.datasets import demo_world_io as wio

GOLD_FILE = wio.WORLD_DIR / "intake_night_v1.gold.json"


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None




def _street_names() -> dict | None:
    """id участка → название улицы (граф R12); нет графа — None (улицы сверяются только по id)."""
    try:
        sys.path.insert(0, str(wio.ROOT))
        from engine.civic_geo.graph import get_graph
        return {e.id: e.name for e in get_graph().edges}
    except Exception:  # noqa: BLE001 — оценка без графа тоже полезна
        return None


def _text_ids(raw, order: list[str]) -> list[str]:
    """id набора как есть; число (или строка из цифр) — номер строки с нуля в порядке набора."""
    out = []
    for x in raw or []:
        if isinstance(x, bool):
            continue
        if isinstance(x, int) and 0 <= x < len(order):
            out.append(order[x])
        elif isinstance(x, str) and x.isdigit() and int(x) < len(order):
            out.append(order[int(x)])
        else:
            out.append(str(x))
    return out


def evaluate(pred: dict, gold: dict, streets: dict | None = None) -> dict:
    order = [i["id"] for i in gold["items"]]
    g = {i["id"]: i for i in gold["items"]}
    place = {gr["id"]: gr["place"] for gr in gold["groups"]}
    task_of: dict[str, dict] = {}
    for t in pred.get("tasks") or []:
        for tid in _text_ids(t.get("text_ids"), order):
            if tid in g and tid not in task_of:
                task_of[tid] = t
    n = len(order)
    covered = [tid for tid in order if tid in task_of]

    def lead(services):
        services = services or []
        for s in services:
            if s.get("role") == "lead":
                return s.get("id")
        return services[0].get("id") if services else None

    def sset(services):
        return frozenset(s.get("id") for s in services or [])

    lead_ok = set_ok = 0
    two_tp = two_gold = two_pred = 0
    for tid in covered:
        gi, t = g[tid], task_of[tid]
        lead_ok += lead(t.get("services")) == lead(gi["services"])
        set_ok += sset(t.get("services")) == sset(gi["services"])
        p2 = len(sset(t.get("services"))) > 1
        two_gold += gi["two_services"]
        two_pred += p2
        two_tp += gi["two_services"] and p2 and sset(t.get("services")) == sset(gi["services"])
    two_gold_all = sum(1 for i in gold["items"] if i["two_services"])

    # повторы: попарно по всем текстам набора (без задачи — одиночка)
    tp = fp = fn = 0
    key = {tid: id(task_of[tid]) if tid in task_of else ("solo", tid) for tid in order}
    for a, b in combinations(order, 2):
        same_p, same_g = key[a] == key[b], g[a]["group"] == g[b]["group"]
        tp += same_p and same_g
        fp += same_p and not same_g
        fn += same_g and not same_p
    pp, pr = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    f1 = _ratio(2 * tp, 2 * tp + fp + fn)
    # группы с повторами, собранные ровно в одну задачу (и без чужих текстов)
    exact = multi = 0
    for gr in gold["groups"]:
        if len(gr["text_ids"]) < 2:
            continue
        multi += 1
        keys = {key[tid] for tid in gr["text_ids"]}
        if len(keys) == 1:
            k = next(iter(keys))
            exact += sum(1 for tid in order if key[tid] == k) == len(gr["text_ids"])

    # места
    found = with_place = abstain_ok = without_place = 0
    for tid in order:
        gp = place[g[tid]["group"]]
        target = (task_of.get(tid) or {}).get("target") or None
        tid_pred = target.get("id") if isinstance(target, dict) else None
        if gp["target"] is None:
            without_place += 1
            abstain_ok += tid_pred is None
            continue
        with_place += 1
        ok = tid_pred in gp["accept_ids"]
        if not ok and tid_pred and gp.get("street_ru") and streets:
            ok = streets.get(tid_pred) == gp["street_ru"]
        found += ok

    # срочность
    u_gold = [tid for tid in order if g[tid]["urgent"]]
    u_pred = [tid for tid in order if (task_of.get(tid) or {}).get("urgent")]
    u_tp = len(set(u_gold) & set(u_pred))
    groups_caught = 0
    urgent_groups = [gr for gr in gold["groups"] if gr["urgent"]]
    for gr in urgent_groups:
        hit = sum(1 for tid in gr["text_ids"] if (task_of.get(tid) or {}).get("urgent"))
        groups_caught += hit * 2 >= len(gr["text_ids"])

    summary = pred.get("summary") or {}
    return {
        "texts": n, "covered": len(covered), "tasks": len(pred.get("tasks") or []), "gold_groups": len(gold["groups"]),
        "services": {"lead_accuracy": _ratio(lead_ok, len(covered)), "exact_set": _ratio(set_ok, len(covered)),
                     "two_services_recall": _ratio(two_tp, two_gold_all), "two_services_precision": _ratio(two_tp, two_pred),
                     "two_services_gold_texts": two_gold_all},
        "duplicates": {"pairwise_precision": pp, "pairwise_recall": pr, "pairwise_f1": f1,
                       "pairs_gold": tp + fn, "pairs_pred": tp + fp,
                       "groups_exact": _ratio(exact, multi), "groups_with_repeats": multi},
        "places": {"found_share": _ratio(found, with_place), "with_place": with_place,
                   "no_address_abstained": _ratio(abstain_ok, without_place), "without_place": without_place,
                   "street_by_name": streets is not None},
        "urgent": {"recall_texts": _ratio(u_tp, len(u_gold)), "precision_texts": _ratio(u_tp, len(u_pred)),
                   "recall_groups": _ratio(groups_caught, len(urgent_groups)), "gold_groups": len(urgent_groups),
                   "gold_texts": len(u_gold)},
        "time_ms": summary.get("ms"),
        "note_ru": "набор синтетический (R02, demo: true); числа — для FACTS и диплома с пометкой «синтетика»",
    }


def gold_as_prediction(gold: dict) -> dict:
    """Ответ «как в эталоне» — для проверки оценщика (все метрики = 1)."""
    tasks = []
    for gr in gold["groups"]:
        tasks.append({"id": gr["id"], "services": gr["services"], "target": gr["place"]["target"],
                      "text_ids": gr["text_ids"], "urgent": gr["urgent"]})
    return {"summary": {"total": sum(len(t["text_ids"]) for t in tasks), "tasks": len(tasks)}, "tasks": tasks}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="demo_intake_eval", description=__doc__.split("\n")[0])
    ap.add_argument("prediction", help="JSON-ответ analyze() на тексты набора")
    ap.add_argument("--gold", default=str(GOLD_FILE))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    gold = json.loads(Path(a.gold).read_text(encoding="utf-8"))
    pred = json.loads(Path(a.prediction).read_text(encoding="utf-8"))
    if isinstance(pred, dict) and "data" in pred and "tasks" not in pred:
        pred = pred["data"]                                   # ответ маршрута в обёртке {"ok", "data"}
    res = evaluate(pred, gold, _street_names())
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
        return 0
    s, d, p, u = res["services"], res["duplicates"], res["places"], res["urgent"]
    print(f"Текстов {res['texts']} (в задачах {res['covered']}), задач {res['tasks']} — групп в эталоне {res['gold_groups']}")
    print(f"Службы: ведущая {s['lead_accuracy']}, весь набор {s['exact_set']}; две службы — полнота "
          f"{s['two_services_recall']}, точность {s['two_services_precision']}")
    print(f"Повторы (попарно): точность {d['pairwise_precision']}, полнота {d['pairwise_recall']}, F1 {d['pairwise_f1']}; "
          f"групп с повторами собрано точно {d['groups_exact']} из {d['groups_with_repeats']}")
    print(f"Места: найдено {p['found_share']} из {p['with_place']}; без адреса — «уточнить» {p['no_address_abstained']} "
          f"из {p['without_place']}" + ("" if p["street_by_name"] else " (улицы — только по id: нет графа)"))
    print(f"Срочные: полнота по текстам {u['recall_texts']}, по группам {u['recall_groups']} ({u['gold_groups']}); "
          f"точность {u['precision_texts']}")
    print(f"Время: {res['time_ms']} мс" if res["time_ms"] is not None else "Время: нет summary.ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
