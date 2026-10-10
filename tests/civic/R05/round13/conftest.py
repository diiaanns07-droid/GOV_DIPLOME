"""Изолированный каталог пакета R05 раунда 13 для синтетических проверок (реальные файлы не меняются)."""

import importlib.util

import pytest

from r13_helpers import TOOL, make_home


@pytest.fixture(scope="session")
def tool():
    spec = importlib.util.spec_from_file_location("r05_r13_tool_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def home(tmp_path, tool):
    saved = tool.HERE
    try:
        yield make_home(tool, tmp_path)
    finally:
        tool.HERE = saved
