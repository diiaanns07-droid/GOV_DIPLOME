"""Привязка старых демо-геометрий к улицам OSM -> data/civic/astana/geo/demo_snapped.json (+ копия для карты).

Демо-записи R05 (data/civic/astana/demo_synthetic.json) нарисованы от руки 2–3 точками и режут дома.
Здесь каждая линия заменяется участком по рёбрам графа через те же точки (segment.snap_polyline),
форма — из OSM. Сами записи не меняются: карта берёт замену по id и только если исходная
геометрия в хранилище совпадает с original_coordinates (иначе запись уже исправили — замена не нужна).

Площадь «условного двора» привязывается к двору OSM, внутри которого её центр (yards.json);
если дворов ещё нет (LOCAL-1) — запись остаётся областью «примерное место» (display=approximate_area).
Примерные точки карта сама рисует мягкой областью — в этот файл они не попадают.

    python3 -m engine.civic_geo.snap_demo
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from . import geo
from .graph import get_graph
from .objects import get_layers
from .paths import DEMO_SYNTHETIC, GEO_DIR, ROOT, WEB_MAP_DIR
from .segment import GeoError, snap_along_one_street, snap_polyline

# Какие улицы брать для демо-линии: ремонт тротуара — тротуар/дорожка, остальное — проезжая часть.
GROUP_HINTS = {
    "demo-astana-roadworks-completed": ("foot",),
}
DEFAULT_GROUPS = ("road", "service")
# Путь по улицам, который сильно длиннее нарисованной линии или уходит от неё, значит: неизвестно, какую улицу
# имели в виду. Тогда не выдумываем — показываем «примерное место» областью (CONTRACT §8.4).
MAX_LENGTH_RATIO = 1.2
MAX_DEVIATION_M = 40.0


def snap_item(item: dict, graph, yards) -> dict | None:
    g = item.get("geometry")
    if not g:
        return None
    if g["type"] == "LineString":
        groups = GROUP_HINTS.get(item["id"], DEFAULT_GROUPS)
        try:
            # Сначала — вдоль одной улицы/дорожки (без крюков на соседние улицы); не вышло — через все точки.
            try:
                r = snap_along_one_street(graph, g["coordinates"], groups=groups)
            except GeoError:
                r = None
            r = r or snap_polyline(graph, g["coordinates"], groups=groups)
        except GeoError as exc:
            return {"status": "not_snapped", "reason": exc.message, "original_coordinates": g["coordinates"],
                    "display": "approximate_area"}
        drawn = geo.polyline_length_m(g["coordinates"])
        ratio = r["length_m"] / drawn if drawn > 0 else float("inf")
        deviation = geo.max_offset_m(r["geometry"]["coordinates"], [g["coordinates"]])
        if ratio > MAX_LENGTH_RATIO or deviation > MAX_DEVIATION_M:
            return {"status": "not_snapped", "original_coordinates": g["coordinates"], "display": "approximate_area",
                    "reason": f"линия от руки не идёт вдоль одной улицы (путь по улицам в {ratio:.2f} раза длиннее, "
                              f"отходит на {deviation:.0f} м) — показываем примерное место",
                    "candidate_names": r["names"]}
        return {
            "status": "snapped",
            "original_coordinates": g["coordinates"],
            "geometry": r["geometry"],
            "geometry_source": "osm-graph",
            "edge_ids": r["edge_ids"],
            "street_ru": r["street_ru"],
            "street_kk": r["street_kk"],
            "names": r["names"],
            "same_street": r["same_street"],
            "length_m": r["length_m"],
            "max_snap_m": r["max_snap_m"],
            "length_ratio": round(ratio, 3),
            "max_deviation_from_drawn_m": round(deviation, 1),
            "display": "street_line",
        }
    if g["type"] == "Polygon":
        center = geo.bbox_center(g["coordinates"][0])
        inside = yards.containing(center)
        if inside:
            y = inside[0]
            return {"status": "snapped", "original_coordinates": g["coordinates"],
                    "geometry": {"type": "Polygon", "coordinates": y.polygon}, "geometry_source": "osm-yard",
                    "yard_id": y.id, "display": "yard"}
        return {"status": "not_snapped", "reason": "нет данных о дворах OSM (LOCAL-1) — показываем как примерное место",
                "original_coordinates": g["coordinates"], "display": "approximate_area"}
    return None


def build(demo_path: Path = DEMO_SYNTHETIC) -> dict:
    raw = Path(demo_path).read_bytes()
    demo = json.loads(raw)
    graph = get_graph()
    _, yards, _ = get_layers()
    items = {}
    for it in demo["items"]:
        r = snap_item(it, graph, yards)
        if r is not None:
            items[it["id"]] = r
    return {
        "schema": "r12-demo-snapped-v1",
        "evidence_type": "synthetic",
        "note": "Демо-записи СИНТЕТИЧЕСКИЕ. Здесь только их геометрия, привязанная к улицам OSM; "
                "сведений о реальных работах нет.",
        "source": {"path": str(Path(demo_path).resolve().relative_to(ROOT)), "sha256": hashlib.sha256(raw).hexdigest(),
                   "version": (demo.get("slice") or {}).get("version")},
        "graph": {"id": graph.id, "digest": graph.digest, "snapshot_at": graph.snapshot_at},
        "license": {"id": "ODbL-1.0", "attribution": "© OpenStreetMap contributors"},
        "builder": "engine/civic_geo/snap_demo.py",
        "items": items,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(GEO_DIR / "demo_snapped.json"))
    ap.add_argument("--web-copy", default=str(WEB_MAP_DIR / "demo_snapped.json"),
                    help="копия для карты (её отдаёт сервер как /civic/map/demo_snapped.json); '' — не писать")
    args = ap.parse_args(argv)
    result = build()
    text = json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    for path in filter(None, (args.out, args.web_copy)):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, "utf-8")
    for k, v in result["items"].items():
        print(k, v["status"], v.get("display"), v.get("names"), v.get("length_m"), v.get("max_snap_m"), v.get("reason", ""))


if __name__ == "__main__":
    main()
