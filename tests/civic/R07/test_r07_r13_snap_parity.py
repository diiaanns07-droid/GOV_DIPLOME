"""R07 round 13: привязка в браузере (web/civic/scenarios/scenarios.js) = эталон engine/civic_scenarios/snap.py.

Настоящий scenarios.js исполняется в Node (без DOM: используются только чистые функции _internal).
Пропускается, если node не установлен.
"""
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from engine.civic_scenarios.registry import GRAPHS, load_graph, manifest
from engine.civic_scenarios.snap import snap_point

ROOT = Path(__file__).resolve().parents[3]
JS = ROOT / "web/civic/scenarios/scenarios.js"
NODE = shutil.which("node")
RUNNER = r"""
const fs = require("fs");
require(process.argv[2]);
const { buildSnapIndex, snapPoint } = globalThis.CivicScenarios._internal;
const graph = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const points = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
const idx = buildSnapIndex(graph);
process.stdout.write(JSON.stringify(points.map(([lon, lat, max]) => snapPoint(idx, lon, lat, max))));
"""


def js_snaps(graph_file, points, tmp_path):
    (tmp_path / "pts.json").write_text(json.dumps(points))
    (tmp_path / "run.cjs").write_text(RUNNER)
    out = subprocess.run([NODE, str(tmp_path / "run.cjs"), str(JS), str(graph_file), str(tmp_path / "pts.json")],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def check(py, js):
    for key in ("status", "node_id", "main_component", "component_edges"):
        assert py[key] == js[key], (key, py, js)
    for key in ("distance_m", "nearest_allowed_m", "nearer_unverified_m"):
        if py[key] is None or js[key] is None:
            assert py[key] == js[key], (key, py, js)
        else:
            assert abs(py[key] - js[key]) <= 0.11, (key, py, js)
    assert (py["main_alternative"] or {}).get("node_id") == (js["main_alternative"] or {}).get("node_id")


def graph_file(graph_id):
    return GRAPHS / next(g["file"] for g in manifest()["graphs"] if g["id"] == graph_id)


@pytest.mark.skipif(NODE is None, reason="node не установлен")
def test_parity_on_synthetic_graph(tmp_path):
    pg = load_graph("synthetic-tiny-v1")
    rnd = random.Random(3)
    points = [[rnd.uniform(71.398, 71.410), rnd.uniform(51.098, 51.103), rnd.choice([30, 150, 400])] for _ in range(60)]
    for p, js in zip(points, js_snaps(graph_file("synthetic-tiny-v1"), points, tmp_path)):
        check(snap_point(pg, p[0], p[1], max_m=p[2]), js)


@pytest.mark.skipif(NODE is None, reason="node не установлен")
def test_parity_on_city_snapshot(tmp_path):
    gid = "osm-astana-walking-20260506"
    pg = load_graph(gid)
    rnd = random.Random(13)
    points = [[rnd.uniform(71.36, 71.55), rnd.uniform(51.07, 51.22), 150] for _ in range(150)]
    points += [[71.4305, 51.1283, 150], [71.404, 51.1324, 150], [71.5330, 51.1105, 150], [71.5330, 51.1105, 400], [72.5, 51.1, 150]]
    results = js_snaps(graph_file(gid), points, tmp_path)
    statuses = set()
    for p, js in zip(points, results):
        py = snap_point(pg, p[0], p[1], max_m=p[2])
        check(py, js)
        statuses.add(py["status"])
    assert statuses == {"ok", "too_far", "outside_graph"}     # проверены все исходы, не только удачные
