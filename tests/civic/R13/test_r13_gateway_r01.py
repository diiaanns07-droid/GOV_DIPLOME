"""R13 через шлюз v2 R01 (CivicV2Gateway в ui/web_server.py) с patch маршрута GET /api/civic/v2/forecast.

Шлюза R01 в общей сборке ещё нет. Тест берёт его файл из переменной R13_R01_WEB_SERVER
(git show origin/claude/sharp-dijkstra-0t87gl:ui/web_server.py > /tmp/web_server.py), копирует во временную папку,
накладывает research/round-14-results/R13/r01_forecast_route.patch (если маршрута ещё нет) и вызывает настоящий
маршрутизатор. Без переменной и без маршрута в рабочем дереве — SKIP, а не PASS.
"""

import importlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[3]
PATCH = REPO / "research" / "round-14-results" / "R13" / "r01_forecast_route.patch"


def load_gateway(tmp_root: Path):
    source = os.environ.get("R13_R01_WEB_SERVER")
    if not source:
        module = importlib.import_module("ui.web_server")
        return module if "\"forecast\"" in Path(module.__file__).read_text(encoding="utf-8") else None
    (tmp_root / "ui").mkdir(parents=True, exist_ok=True)
    target = tmp_root / "ui" / "web_server.py"
    shutil.copy(source, target)
    if '"forecast"' not in target.read_text(encoding="utf-8"):
        subprocess.run(["git", "apply", str(PATCH)], cwd=tmp_root, check=True)
    spec = importlib.util.spec_from_file_location("r01_web_server_for_r13", target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gateway(tmp_path_factory):
    module = load_gateway(tmp_path_factory.mktemp("r01"))
    if module is None:
        pytest.skip("шлюз v2 R01 с маршрутом forecast не найден: задайте R13_R01_WEB_SERVER")
    return module.CivicV2Gateway(None)


def test_route_ready(gateway):
    modules = gateway.handle("GET", "/modules", "", None, {})["body"]["modules"]
    assert modules["forecast"]["status"] == "ready" and modules["forecast"]["role"] == "R13"


def test_forecast_through_gateway(gateway):
    reply = gateway.handle("GET", "/forecast", "month=2026-11&district=nura&k=5", None, {})
    assert reply["status"] == 200, reply
    body = reply["body"]
    assert body["evidence_type"] == "synthetic" and body["demo"] is True
    assert len(body["items"]) == 5 and all(i["district"] == "nura" for i in body["items"])
    default = gateway.handle("GET", "/forecast", "", None, {})
    assert default["status"] == 200 and len(default["body"]["items"]) == 10


@pytest.mark.parametrize("query", ["month=2026-13", "k=0", "k=99", "district=Mars!"])
def test_bad_parameters_are_400(gateway, query):
    assert gateway.handle("GET", "/forecast", query, None, {})["status"] == 400


def test_unknown_district_name_from_module_is_400(gateway):
    # Формат правильный, но такого района нет — ответ модуля R13 (ForecastError status=400).
    assert gateway.handle("GET", "/forecast", "district=mars", None, {})["status"] == 400
