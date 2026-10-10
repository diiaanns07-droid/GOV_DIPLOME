"""Проверки точности карты (CONTRACT §8) и отчёт по всем объектам, которые показывает карта.

Правила:
  1. Линия участка отстоит от формы своих рёбер графа не больше чем на 5 м (LINE_TOLERANCE_M).
  2. Остановка — не дальше 60 м от улицы (STOP_TO_STREET_M).
  3. Все координаты — внутри границы Астаны (полигоны районов OSM из geofence.json).
  4. Ни одной линии «от руки»: каждая линия на карте либо построена по рёбрам графа, либо
     показывается областью «примерное место».
  5. Цели в сценариях (перекрытия) ссылаются на существующие рёбра графа.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import geo
from .build_geo_data import CityBoundary
from .graph import StreetGraph, get_graph
from .objects import get_layers
from .paths import DEMO_SYNTHETIC, GEO_DIR, ROOT

LINE_TOLERANCE_M = 5.0
STOP_TO_STREET_M = 60.0
SCENARIO_CASES = ROOT / "engine" / "civic_scenarios" / "cases"


def check_line_on_edges(graph: StreetGraph, coords, edge_ids) -> tuple[bool, float, str]:
    """(PASS?, наибольшее отклонение в метрах, пояснение) для линии, построенной по рёбрам."""
    missing = [e for e in edge_ids if e not in graph.by_id]
    if missing:
        return False, float("inf"), f"нет рёбер в графе: {missing[:3]}"
    if not edge_ids:
        return False, float("inf"), "линия без рёбер графа (нарисована от руки)"
    refs = [graph.by_id[e].geometry for e in edge_ids]
    off = geo.max_offset_m(coords, refs)
    return off <= LINE_TOLERANCE_M, off, f"отклонение от формы улицы {off:.2f} м (допуск {LINE_TOLERANCE_M:g} м)"


def stop_distance(graph: StreetGraph, point) -> float:
    near = graph.nearest(point, STOP_TO_STREET_M * 2, limit=1, accept=lambda e: e.group in ("road", "service", "unknown"))
    if not near:
        near = graph.nearest(point, STOP_TO_STREET_M * 2, limit=1)
    return near[0][0] if near else float("inf")


def _row(check: str, obj: str, ok: bool, value, detail: str) -> dict:
    return {"check": check, "id": obj, "status": "PASS" if ok else "FAIL",
            "value": None if value is None else (round(value, 2) if value != float("inf") else "inf"), "detail": detail}


def report(graph: StreetGraph | None = None, geo_dir: Path = GEO_DIR, demo_path: Path = DEMO_SYNTHETIC,
           snapped_path: Path | None = None) -> dict:
    graph = graph or get_graph()
    objects, yards, _ = get_layers(geo_dir)
    city = CityBoundary()
    rows: list[dict] = []

    # 1 + 4. Демо-записи на карте: линии только по рёбрам, координаты внутри города.
    demo = json.loads(Path(demo_path).read_text("utf-8"))
    sp = Path(snapped_path) if snapped_path else Path(geo_dir) / "demo_snapped.json"
    snapped = json.loads(sp.read_text("utf-8"))["items"] if sp.is_file() else {}
    for it in demo["items"]:
        g = it.get("geometry")
        if not g or it.get("publication") != "published":
            continue
        s = snapped.get(it["id"])
        if g["type"] == "LineString":
            coords = g["coordinates"]
            if not s or s.get("status") != "snapped":
                shown_as_area = bool(s) and s.get("display") == "approximate_area"
                rows.append(_row("no_freehand_line", it["id"], shown_as_area, None,
                                 "линия не привязана; карта показывает её областью «примерное место»" if shown_as_area
                                 else "линия от руки: нет привязки к улице в demo_snapped.json"))
            elif s.get("original_coordinates") != g["coordinates"]:
                rows.append(_row("no_freehand_line", it["id"], False, None,
                                 "исходная линия изменилась после привязки — запустите snap_demo заново"))
            else:
                ok, off, detail = check_line_on_edges(graph, s["geometry"]["coordinates"], s["edge_ids"])
                rows.append(_row("line_within_5m_of_street", it["id"], ok, off, detail))
                coords = s["geometry"]["coordinates"]
        elif g["type"] == "Polygon":
            coords = (s or {}).get("geometry", g)["coordinates"][0]
            if not s or s.get("status") != "snapped":
                ok = bool(s) and s.get("display") == "approximate_area"
                rows.append(_row("approximate_place_as_area", it["id"], ok, None,
                                 "условный участок показан областью «примерное место» (двор OSM не найден)" if ok
                                 else "условный участок без пометки «примерное место»"))
        else:
            coords = [g["coordinates"]]
            if it.get("geometry_precision") != "exact":
                rows.append(_row("approximate_place_as_area", it["id"], True, None,
                                 "примерная точка — карта рисует её областью «примерное место»"))
        outside = [c for c in coords if not city.contains(c)]
        rows.append(_row("inside_astana", it["id"], not outside, len(outside),
                         "все координаты внутри Астаны" if not outside else f"вне границы: {outside[:2]}"))

    # 2 + 3. Объекты OSM: остановки рядом с улицей, всё внутри города.
    for f in objects.items:
        if not city.contains(f.point):
            rows.append(_row("inside_astana", f.id, False, None, f"вне границы: {f.point}"))
        if f.kind == "bus_stop":
            d = stop_distance(graph, f.point)
            rows.append(_row("stop_within_60m_of_street", f.id, d <= STOP_TO_STREET_M, d,
                             f"до улицы {d:.1f} м (допуск {STOP_TO_STREET_M:g} м)"))
    for y in yards.items:
        if not city.contains(y.point):
            rows.append(_row("inside_astana", y.id, False, None, f"центр двора вне границы: {y.point}"))

    # 5. Перекрытия в сценариях ссылаются на настоящие рёбра этого графа.
    for p in sorted(SCENARIO_CASES.glob("*.case.json")):
        case = json.loads(p.read_text("utf-8"))
        payload = case.get("payload") or {}
        if payload.get("graph_id") != graph.id:
            continue
        for plan in payload.get("plans", []):
            for cl in plan.get("closures", []):
                for eid in cl.get("edge_ids", []):
                    e = graph.by_id.get(eid)
                    rows.append(_row("scenario_closure_on_graph", f"{case['case_id']}:{plan['id']}:{eid}", e is not None,
                                     None, "перекрытие идёт по ребру графа (форма OSM)" if e else "ребра нет в графе"))

    summary: dict[str, dict] = {}
    for r in rows:
        s = summary.setdefault(r["check"], {"PASS": 0, "FAIL": 0})
        s[r["status"]] += 1
    total_fail = sum(s["FAIL"] for s in summary.values())
    return {
        "schema": "r12-accuracy-report-v1",
        "graph": {"id": graph.id, "digest": graph.digest},
        "inputs": {"demo": str(Path(demo_path).resolve().relative_to(ROOT)), "snapped": str(sp.resolve().relative_to(ROOT)) if sp.is_file() else None,
                   "objects": len(objects.items), "yards": len(yards.items)},
        "rules": {"line_tolerance_m": LINE_TOLERANCE_M, "stop_to_street_m": STOP_TO_STREET_M,
                  "boundary": "data/civic/astana/geofence.json (полигоны районов OSM)"},
        "summary": summary,
        "total": len(rows),
        "failed": total_fail,
        "result": "PASS" if total_fail == 0 and rows else ("FAIL" if total_fail else "EMPTY"),
        "rows": rows,
    }


def format_report(r: dict) -> str:
    lines = [f"Проверка точности карты: {r['result']} — {r['total'] - r['failed']} из {r['total']} PASS"]
    for check, s in r["summary"].items():
        lines.append(f"  {check:32s} PASS {s['PASS']:4d}   FAIL {s['FAIL']:4d}")
    for row in r["rows"]:
        if row["status"] == "FAIL":
            lines.append(f"  FAIL {row['check']} {row['id']}: {row['detail']}")
    return "\n".join(lines)
