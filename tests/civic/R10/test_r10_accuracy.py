"""R10 · pytest-обёртка над accuracy.py (CONTRACT §8) + проверка самой геометрии проверки.

    python3 -m pytest -q tests/civic/R10                   # на текущем дереве (сборка R01: B1/B2/FINAL)
    R10_ROOT=<папка сборки> python3 -m pytest -q tests/civic/R10

Набор данных, которого нет в сборке, даёт skip с причиной (это NOT_RUN, а не PASS).
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import accuracy as A  # noqa: E402

ROOT = Path(os.environ.get("R10_ROOT") or Path(__file__).resolve().parents[3])


# ------------------------------------------------------------------ геометрия проверки (без данных репозитория)
def test_point_segment_distance_in_metres():
    # 0.001° широты ≈ 111 м; точка над серединой горизонтального отрезка
    a, b = [71.40, 51.12], [71.41, 51.12]
    d = A.point_segment_m([71.405, 51.121], a, b)
    assert 110 < d < 112
    assert A.point_segment_m([71.40, 51.12], a, b) == pytest.approx(0, abs=1e-6)


def test_hausdorff_catches_cut_corner():
    # Улица с изгибом и «линия от руки» напрямую: вершина изгиба в ~70 м от прямой → больше 5 м.
    street = [[71.400, 51.120], [71.401, 51.1206], [71.402, 51.120]]
    straight = [[71.400, 51.120], [71.402, 51.120]]
    assert A.hausdorff_m(street, street) == pytest.approx(0, abs=1e-6)
    assert A.hausdorff_m(straight, street) > 60


def test_hausdorff_catches_shortened_line():
    # Линия лежит на улице, но покрывает только половину ребра — тоже не «участок = ребро».
    edge = [[71.400, 51.120], [71.402, 51.120]]
    half = [[71.400, 51.120], [71.401, 51.120]]
    assert A.hausdorff_m(half, edge) > 60


def test_point_in_rings_with_hole():
    outer = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
    hole = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]
    assert A.point_in_rings([2, 2], [outer, hole])
    assert not A.point_in_rings([5, 5], [outer, hole])
    assert not A.point_in_rings([11, 5], [outer, hole])


def test_iter_coords_reads_geojson_and_nested_lists():
    g = {"type": "Polygon", "coordinates": [[[71.4, 51.1], [71.5, 51.1], [71.5, 51.2], [71.4, 51.1]]]}
    assert len(list(A.iter_coords(g))) == 4
    assert list(A.iter_coords([71.4, 51.1])) == [[71.4, 51.1]]


def test_python_literal_lines_does_not_execute_code(tmp_path):
    f = tmp_path / "ui" / "x.py"
    f.parent.mkdir(parents=True)
    f.write_text('import os\nos.system("echo should-not-run")\n'
                 'LINE = {"coordinates": [[71.36, 51.13], [71.37, 51.14]]}\nP = (71.5, 51.2)\n', encoding="utf-8")
    got = A.python_literal_lines(tmp_path, "ui/x.py")
    assert got["lines"] == [[[71.36, 51.13], [71.37, 51.14]]]
    assert got["points"] == [[71.5, 51.2]]


# ------------------------------------------------------------------ данные сборки
_REPORT = None


def report():
    global _REPORT
    if _REPORT is None:
        _REPORT = A.run(ROOT)
    return _REPORT


def _names():
    try:
        return [c["name"] for c in report().checks]
    except Exception as exc:  # отчёт не собрался — покажем это одним упавшим тестом
        return [f"ошибка запуска accuracy.py: {type(exc).__name__}: {exc}"]


def _ids(names):
    """Короткие латинские id для pytest (кириллицу он экранирует); полное имя — в тексте ошибки."""
    out = []
    for i, n in enumerate(names):
        owner = next((c["owner"] for c in (_REPORT.checks if _REPORT else []) if c["name"] == n), None)
        out.append(f"c{i:02d}-{owner or 'all'}")
    return out


_NAMES = _names()


@pytest.mark.parametrize("name", _NAMES, ids=_ids(_NAMES))
def test_map_accuracy(name):
    if name.startswith("ошибка запуска"):
        pytest.fail(name)
    check = next(c for c in report().checks if c["name"] == name)
    if check["status"] == "NOT_RUN":
        pytest.skip(f"NOT_RUN: {check['detail']}")
    assert check["status"] == "PASS", name + ": " + json.dumps(check["detail"], ensure_ascii=False)[:1500]


def test_real_graph_edge_matches_itself_and_rejects_shifted_copy():
    """Самопроверка на настоящем графе: ребро совпадает с собой; копия, сдвинутая на 6 м, — нет."""
    path = ROOT / A.GRAPH
    if not path.is_file():
        pytest.skip("NOT_RUN: нет графа улиц")
    graph = A.Graph(path, None)
    edge = next(e for e in graph.edges.values() if e["length_m"] > 50)
    line = edge["geometry"]
    assert A.hausdorff_m(line, line) == pytest.approx(0, abs=1e-6)
    shift = 6.0 / (A.M_PER_DEG_LAT * math.cos(math.radians(line[0][1])))  # 6 м на восток
    moved = [[x + shift, y] for x, y in line]
    assert A.hausdorff_m(moved, line) > A.SEGMENT_TOL_M
