"""R08 раунд 14: демо-числа «Картины дня» правдоподобны (UX_REVIEW R11, день 3, п. 9).

Жюри смотрит на 4 крупных числа как на работу акимата. Если пример показывает «56 просрочено, в 4 раза больше»
и «за 7 дней 104 — в 6,9 раза больше», это читается как авария, а не как пример.

Числа считает R08, но жалобы — демо-набор R07 (ui/civic_heat/demo_seed.py). Поэтому тест проверяет
итог на настоящем наборе R07, а не на своих записях. Правила (R11):
  - просрочено меньше, чем новых за неделю, и не больше 10 (R11: «≈ 5–8»);
  - «за 7 дней» сопоставимо с прошлой неделей: ±40 %;
  - «новые за день» неделю назад тоже были (не «неделю назад не было»);
  - районы ближе друг к другу: в самом тихом районе не меньше 1/10 самого громкого.

Пока R07 не растянул демо-набор на 3 недели (просьба в INTEGRATION.txt п. 4а), тест отмечается XFAIL с
перечнем нарушений — так видно, что именно не так. Для приёмки B2: BIRGE_STRICT_DEMO=1 делает его обычным FAIL.
"""
import os
from datetime import datetime, timedelta, timezone

import pytest

civic_heat = pytest.importorskip("ui.civic_heat", reason="нет модуля R07 ui/civic_heat в сборке — демо-набора жалоб нет")

from ui.civic_akim import AkimService  # noqa: E402

MAX_OVERDUE = 10
WEEK_RATIO = (0.6, 1.4)
DISTRICT_SPREAD = 10


def violations(s: dict) -> list[str]:
    k = s["kpi"]
    out = []
    overdue, week, day = k["overdue"]["value"], k["new_week"], k["new_day"]
    if overdue >= week["value"]:
        out.append(f"просрочено {overdue} ≥ новых за неделю {week['value']}")
    if overdue > MAX_OVERDUE:
        out.append(f"просрочено {overdue} > {MAX_OVERDUE}")
    prev = week["prev"]
    if not prev or not WEEK_RATIO[0] <= week["value"] / prev <= WEEK_RATIO[1]:
        out.append(f"за 7 дней {week['value']} против {prev} неделю назад (нужно ±40 %)")
    if not day["prev"]:
        out.append(f"новые за день {day['value']}, неделю назад — 0")
    values = [d["value"] for d in s["districts"]["items"] if d["value"] > 0]
    if values and min(values) * DISTRICT_SPREAD < max(values):
        out.append(f"районы от {min(values)} до {max(values)} (разброс больше чем в {DISTRICT_SPREAD} раз)")
    return out


def test_rules_catch_the_case_from_ux_review():
    """Сами правила: случай из UX_REVIEW (56 просрочено, 104 против 15, Нура 149 / Есиль 1) — три нарушения."""
    s = {"kpi": {"overdue": {"value": 56}, "new_week": {"value": 104, "prev": 15}, "new_day": {"value": 20, "prev": 4}},
         "districts": {"items": [{"value": 149}, {"value": 1}]}}
    assert len(violations(s)) == 3
    ok = {"kpi": {"overdue": {"value": 6}, "new_week": {"value": 104, "prev": 90}, "new_day": {"value": 20, "prev": 17}},
          "districts": {"items": [{"value": 40}, {"value": 12}]}}
    assert violations(ok) == []


# Момент проверки зафиксирован — полдень понедельника по Астане. С настоящими часами тест зависел от часа запуска:
# сразу после полуночи «новых за день» ещё 0 и тест уходил в XFAIL (найдено ночью в FINAL R01 85c16e2, 00:38).
# Демо-набор R07 строится относительно часов сервиса, поэтому полдень даёт тот же «обычный день», что и на показе.
NOON = datetime(2026, 10, 12, 12, 0, tzinfo=timezone(timedelta(hours=5)))


def test_demo_numbers_look_like_a_normal_day():
    svc = AkimService(heat=civic_heat.HeatService(clock=lambda: NOON), objects=None, proposals=None, clock=lambda: NOON)
    s = svc.summary(now=NOON)
    assert s["demo"]["complaints"] is True, "проверяем именно демо-набор"
    bad = violations(s)
    if bad and os.environ.get("BIRGE_STRICT_DEMO") != "1":
        pytest.xfail("демо-набор R07 ещё не растянут на 3 недели (UX_REVIEW п. 9): " + "; ".join(bad))
    assert not bad, bad
