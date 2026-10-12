"""R01 · R10 B-061: в демо-сборке (CIVIC_DEMO=1) пример «Нужно решение акима» не пропадает после первой жалобы
репетиции (demo: false); в обычной сборке среди настоящих обращений пример по-прежнему не подмешивается."""

from datetime import datetime, timedelta, timezone

import pytest

summary_mod = pytest.importorskip("ui.civic_akim.summary")

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=timezone(timedelta(hours=5)))


def _record(demo):
    created = (NOW - timedelta(hours=2)).isoformat()
    return {"id": "c-r01-b061", "demo": demo, "status": "new", "category": "lighting", "created_at": created,
            "updated_at": created, "district": "nura", "point": [71.406553, 51.131155],
            "target": {"kind": "stop", "id": "osm-node-4109037549", "label_ru": "Остановка «Хан Шатыр»"}}


def _service(records, **kwargs):
    return summary_mod.AkimService(heat=False, records=lambda since=None: list(records), objects=lambda *a, **k: [],
                                   proposals=lambda *a, **k: [], clock=lambda: NOW, **kwargs)


def test_demo_build_keeps_the_example_after_a_rehearsal_complaint():
    part = _service([_record(demo=False)], demo_build=True).summary(now=NOW)["decisions"]
    assert part["demo"] is True and part["source"] == "example" and part["count"] > 0


def test_regular_build_never_mixes_the_example_into_real_complaints():
    part = _service([_record(demo=False)]).summary(now=NOW)["decisions"]
    assert part["demo"] is False and part["source"] == "complaints"


def test_all_demo_complaints_still_show_the_example_without_demo_build():
    part = _service([_record(demo=True)]).summary(now=NOW)["decisions"]
    assert part["demo"] is True and part["count"] > 0
