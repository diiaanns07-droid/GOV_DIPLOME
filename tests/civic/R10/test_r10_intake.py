"""R10 · П3 · логика приёмки сцены 0 (tests/civic/R10/intake.py) на ответах-образцах — без сервера сборки.

    python3 -m pytest -q tests/civic/R10/test_r10_intake.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from intake import sample_texts, summary_consistency, task_issues  # noqa: E402

CATS = {"roads", "snow_ice", "sidewalks", "transport", "lighting", "yards", "waste", "utilities", "smell_air",
        "noise_safety", "parking", "other"}


def task(tid, ids, *, urgent=False, target=True, services=(("lighting", "lead"),), category="lighting"):
    return {"id": tid, "title_ru": "Не горит фонарь", "title_kk": "Шам жанбайды", "category": category,
            "services": [{"id": s, "role": r} for s, r in services], "why_ru": "Категория и место",
            "why_kk": "Санат пен орын", "target": {"id": "osm-node-4109037548", "point": [71.4069, 51.1335]} if target else None,
            "address_text": "" if target else "адрес уточнить", "text_ids": list(ids), "people": len(ids),
            "urgent": urgent, "urgent_why": "люк, дети" if urgent else ""}


def analysis(items, **summary):
    base = {"total": 6, "tasks": len(items), "services": 2, "urgent": 1, "merged": 2, "no_address": 1, "ms": 120}
    base.update(summary)
    return {"summary": base, "tasks": items, "method": "rules+clf", "demo": True, "batch_id": "b-1"}


TASKS = [task("t1", [0, 1, 2]), task("t2", [3], urgent=True, services=(("utilities", "lead"), ("road", "co"))),
         task("t3", [4], target=False, services=(("waste", "lead"),), category="waste"), task("t4", [5])]


def checks(data, total):
    return {name: ok for name, ok, _detail, _blocking in summary_consistency(data, total)}


def test_consistent_summary_passes():
    res = checks(analysis(TASKS, services=4, merged=2, no_address=1), 6)
    assert all(res.values()), res


def test_services_lead_only_reading_is_accepted():
    # все службы: lighting, utilities, road, waste = 4; ведущие: lighting, utilities, waste = 3
    assert checks(analysis(TASKS, services=3), 6)["итог: служб = разных служб в задачах"]
    assert not checks(analysis(TASKS, services=5), 6)["итог: служб = разных служб в задачах"]


def test_merged_two_readings():
    name = "итог: повторов склеено = повторы в задачах"
    assert checks(analysis(TASKS, services=4, merged=2), 6)[name]       # лишние тексты: 3 − 1
    assert checks(analysis(TASKS, services=4, merged=1), 6)[name]       # одна группа повторов
    assert not checks(analysis(TASKS, services=4, merged=5), 6)[name]


def test_wrong_counts_fail():
    res = checks(analysis(TASKS, services=4, tasks=5, urgent=0, total=7), 6)
    assert not res["итог: задач = число задач в списке"]
    assert not res["итог: срочных = задач с пометкой «срочно»"]
    assert not res["итог: обращений = число текстов на входе"]


def test_text_in_two_tasks_is_double_count():
    bad = TASKS + [task("t5", [0])]
    assert not checks(analysis(bad, services=4), 6)["у каждого текста не больше одной задачи (без двойного счёта)"]


def test_no_address_two_readings():
    name = "итог: без адреса = задач (текстов) без места"
    two = TASKS[:2] + [task("t3", [4, 6], target=False, services=(("waste", "lead"),), category="waste")]
    assert checks(analysis(two, services=4, no_address=1), 7)[name]     # задач без места
    assert checks(analysis(two, services=4, no_address=2), 7)[name]     # текстов без места
    assert not checks(analysis(two, services=4, no_address=0), 7)[name]


def test_task_issues():
    assert task_issues(TASKS[0], CATS) == []
    t = task("x", [1], urgent=True)
    t.update(urgent_why="", category="potholes", services=[{"id": "roads_dept", "role": "lead"}], title_kk="")
    issues = task_issues(t, CATS)
    assert any("категория" in i for i in issues)
    assert any("справочника" in i for i in issues)
    assert any("urgent_why" in i for i in issues)
    assert any("title_kk" in i for i in issues)
    far = task("y", [2])
    far["target"]["point"] = [76.9, 43.2]  # Алматы
    assert any("вне Астаны" in i for i in task_issues(far, CATS))
    # без места: пустой address_text — можно («адрес уточнить» пишет экран), а точка без цели — угаданное место
    lost = task("z", [3], target=False)
    lost["address_text"] = ""
    assert task_issues(lost, CATS) == []
    lost["point"] = [71.43, 51.13]
    assert any("угадано" in i for i in task_issues(lost, CATS))


def test_sample_shapes():
    assert len(sample_texts({"texts": ["а", "б"], "demo": True})[0]) == 2
    texts, demo = sample_texts({"ok": True, "data": {"items": [{"id": "n1", "text": "а"}], "demo": True}})
    assert texts[0]["id"] == "n1" and demo is True
    texts, demo = sample_texts({"sample": {"texts": ["а", "б", "в"], "demo": True}})
    assert len(texts) == 3 and demo is True
