"""Подложка для стенда R12: рёбра графа OSM в окне демо-записей (OpenFreeMap в облаке недоступен — 403).

    python3 -B tests/civic/R12/map/make_streets_fixture.py   -> tests/civic/R12/map/fixtures/.generated/streets_demo_area.json
Файл не коммитится (.generated/.gitignore); граф только читается.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from engine.civic_geo import geo  # noqa: E402
from engine.civic_geo.graph import get_graph  # noqa: E402

BBOX = [71.416, 51.160, 71.446, 51.182]
OUT = Path(__file__).resolve().parent / "fixtures" / ".generated" / "streets_demo_area.json"


def main():
    g = get_graph()
    feats = []
    for e in g.edges:
        b = e.bbox
        if b[2] < BBOX[0] or b[0] > BBOX[2] or b[3] < BBOX[1] or b[1] > BBOX[3]:
            continue
        feats.append({"type": "Feature", "properties": {"g": e.group},
                      "geometry": {"type": "LineString", "coordinates": [geo.round_coord(c, 6) for c in e.geometry]}})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")), "utf-8")
    print(OUT, len(feats))


if __name__ == "__main__":
    main()
