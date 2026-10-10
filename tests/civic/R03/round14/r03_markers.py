"""Маркеры пропуска тестов R03 (NOT_RUN, если нет тяжёлых библиотек).

Отдельный модуль с уникальным именем, а не `from conftest import …`: при запуске нескольких папок тестов
сразу (`pytest tests/civic/R03/round14 tests/civic/R09`) имя `conftest` занято чужим файлом (просьба R01, B2 §9).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
for _p in (str(ROOT), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def has(*mods: str) -> bool:
    return all(importlib.util.find_spec(m) is not None for m in mods)


needs_ml = pytest.mark.skipif(not has("torch", "transformers", "tokenizers"),
                              reason="NOT_RUN: нет torch/transformers (ставятся по RUN.txt)")
needs_onnx = pytest.mark.skipif(not has("torch", "transformers", "onnx", "onnxruntime"),
                                reason="NOT_RUN: нет onnx/onnxruntime")
needs_sklearn = pytest.mark.skipif(not has("sklearn", "scipy"), reason="NOT_RUN: нет scikit-learn")
