"""ml/civic_classifier_v2/eval_human.py (LOCAL-14): оценка на текстах людей без утечки текстов.

Людей в облаке нет — проверка на СИНТЕТИКЕ в формате экспорта web/labeling (r03_fixtures.human_like, раунд 14),
во временной папке вне Git. Трансформер — NOT_RUN (нет весов), логрегрессия — если есть scikit-learn.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import r03_r15_fixtures  # noqa: F401 — путь к корню репозитория

ROUND14 = Path(__file__).resolve().parents[1] / "round14"
if str(ROUND14) not in sys.path:
    sys.path.insert(0, str(ROUND14))

pytest.importorskip("numpy")
from ml.civic_classifier_v2 import eval_human as E  # noqa: E402
import r03_fixtures as F14  # noqa: E402


@pytest.fixture()
def human_file(tmp_path):
    rows = F14.human_like(n=60)
    path = tmp_path / "labels_people.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path, rows


def test_eval_human_writes_numbers_only(human_file, tmp_path):
    path, rows = human_file
    out = tmp_path / "results"
    assert E.main(["--human", str(path), "--no-logreg", "--out", str(out)]) == 0
    raw_json = (out / "human_eval.json").read_text("utf-8")
    raw_md = (out / "RESULTS_HUMAN.md").read_text("utf-8")
    for r in rows:   # ни одного текста «людей» в результатах
        assert r["text"] not in raw_json and r["text"] not in raw_md
    result = json.loads(raw_json)
    assert result["n"] == 60
    heur = next(s for s in result["systems"] if s["name"] == "heuristic")
    assert heur["status"] == "ok"
    assert set(heur["human"]["by_lang"]) == {"ru", "kk"}
    assert heur["human"]["ci"]["macro_f1"]["low"] is not None
    assert len(heur["human"]["confusion"]["rows_true_cols_pred"]) == len(result["labels"])
    assert heur["vs_synthetic"]["probe_v2"]["n"] == 300
    trans = next(s for s in result["systems"] if s["name"] == "transformer")
    assert trans["status"] == "NOT_RUN"
    assert "меньше 200" in raw_md           # 60 текстов — предупреждение о широких интервалах


def test_refuses_file_tracked_by_git(tmp_path):
    tracked = E.REPO_ROOT / "ml" / "datasets" / "probe_v2" / "probe_v2.jsonl"
    assert E.main(["--human", str(tracked), "--no-logreg", "--out", str(tmp_path)]) == 3


def test_missing_file_is_not_run(tmp_path):
    assert E.main(["--human", str(tmp_path / "nope.jsonl"), "--out", str(tmp_path)]) == 2
