import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def data():
    return json.loads((FIXTURES / "objects.json").read_text(encoding="utf-8"))


@pytest.fixture
def ctx_of(data):
    from agent.civic_assistant import build_verified_context

    def make(name, **kw):
        return build_verified_context(data["objects"][name], data["history"].get(name), **kw)
    return make
