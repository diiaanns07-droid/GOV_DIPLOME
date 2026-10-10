"""Подбор seed демо-набора R07 по числам «Картины дня» R08 (инструмент, не тест).

Модель демо-набора фиксирована (ui/civic_heat/demo_seed.py), seed выбирает одну правдоподобную реализацию.
Нужен модуль R08 ui/civic_akim рядом (сборка R01 или копия ветки claude/r14-R08):
    python tests/civic/R07/tune_demo_seed.py <папка, где лежит ui/civic_akim> [сколько seed проверить]
Критерии (UX_REVIEW R11, день 3, №9) — те же, что в test_r07_heat.py::test_demo_numbers_are_plausible:
неделя к неделе и день к дню сопоставимы, просрочено 5–8, Нура не «в 6 раз» больше прошлой недели и других районов,
на карте есть уровни 3–4, самое горячее место — в Нуре (её показывает демо).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def problems(k: dict, d: dict, items: list) -> list[str]:
    """Пустой список — набор правдоподобен. k: kpi R08 {name: (value, prev)}, d: районы {id: (value, prev)}."""
    ratio = lambda a: a[0] / max(1, a[1])
    out = []
    if not 0.85 <= ratio(k["new_week"]) <= 1.4:
        out.append(f"новых за неделю {k['new_week']}")
    if not 0.6 <= ratio(k["new_day"]) <= 1.6:
        out.append(f"новых за день {k['new_day']}")
    if not 0.7 <= ratio(k["fixed_week"]) <= 1.4:
        out.append(f"исправлено за неделю {k['fixed_week']}")
    if not 5 <= k["overdue"][0] <= 8:
        out.append(f"просрочено {k['overdue']}")
    if d:
        others = sorted(v[0] for x, v in d.items() if x != "nura")
        nura = d.get("nura", (0, 0))
        if ratio(nura) > 2.5:
            out.append(f"Нура к прошлой неделе {nura}")
        if nura[0] > 5 * max(1, others[len(others) // 2]):
            out.append(f"Нура к другим районам {nura[0]} / {others}")
    active = [i for i in items if i["state"] == "active"]
    levels = [i["level"] for i in active]
    if levels.count(4) < 2 or levels.count(4) + levels.count(3) < 5:
        out.append(f"мало горячих мест: 4×{levels.count(4)}, 3×{levels.count(3)}")
    if not active or active[0]["district"] != "nura":
        out.append("самое горячее место не в Нуре")
    greens = sum(1 for i in items if i["state"] == "fixed")
    if not 3 <= greens <= 10:
        out.append(f"зелёных «исправлено» {greens}")
    return out


def measure(seed: int):
    from ui.civic_heat import HeatService, demo_seed
    from ui.civic_akim.summary import AkimService

    recs = demo_seed.demo_records(now=demo_seed.ANCHOR, seed=seed)
    heat = HeatService(source=lambda since: recs, clock=lambda: demo_seed.ANCHOR)
    s = AkimService(heat=heat, clock=lambda: demo_seed.ANCHOR).summary(now=demo_seed.ANCHOR)
    k = {n: (v["value"], v["prev"]) for n, v in s["kpi"].items()}
    d = {i["district"]: (i["value"], i["prev"]) for i in s["districts"]["items"]}
    return k, d, heat.heat(days=30)["items"]


if __name__ == "__main__":
    sys.path.insert(0, sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    found = 0
    for seed in range(20261011, 20261011 + n):
        k, d, items = measure(seed)
        p = problems(k, d, items)
        if not p:
            found += 1
            print("OK seed", seed, k, d)
            if found >= 3:
                break
    if not found:
        print("подходящего seed нет — ослабьте критерии или поменяйте модель")
