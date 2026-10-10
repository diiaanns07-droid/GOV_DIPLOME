"""Общие фикстуры pytest для R03 (раунд 14). Запуск: python -m pytest tests/civic/R03/round14 -q"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import r03_fixtures as F  # noqa: E402
from r03_markers import has  # noqa: E402


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("r03data")
    F.write_jsonl(d / "synth_v3" / "corpus_v3.jsonl", F.synth_corpus())
    # Рядом — файл пар перефразов (как у R02 для R04): загрузчик не должен брать его в корпус.
    F.write_jsonl(d / "synth_v3" / "pairs_v3.jsonl", [{"a": "x", "b": "y", "same": True}])
    F.write_jsonl(d / "human.jsonl", F.human_like())
    F.write_jsonl(d / "probe_v2" / "probe_v2.jsonl", F.probe_like())
    return d


@pytest.fixture(scope="session")
def tiny_model(tmp_path_factory) -> Path:
    if not has("torch", "transformers", "tokenizers"):
        pytest.skip("NOT_RUN: нет torch/transformers")
    return F.build_tiny_model(tmp_path_factory.mktemp("tiny") / "model")
