"""Сборка data/civic/astana/geo/way_tags.json: тип дороги и казахское название для каждой линии графа.

Вход (только чтение): data/civic/astana/osm-walking/overpass.json.gz — тот же снимок OSM 2026-05-06,
из которого собран граф osm-astana-walking-20260506. Выход — по одной записи на way, который есть в графе:
    "ways": {"<osm way id>": [номер класса в "classes", "казахское название" | null, 1 если footway=sidewalk]}

    python3 -m engine.civic_geo.build_way_tags
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from .graph import KAZAKH_LETTERS, load_raw_graph
from .paths import GEO_DIR, GRAPH_ID, OSM_WALKING_RAW, ROOT


def kazakh_name(tags: dict) -> str | None:
    """name:kk, а если его нет — основное name, когда оно написано по-казахски (есть буквы ә, ғ, қ, ң, ө, ұ, ү, һ, і)."""
    if tags.get("name:kk"):
        return tags["name:kk"].strip()
    name = (tags.get("name") or "").strip()
    if name and any(ch in KAZAKH_LETTERS for ch in name):
        return name
    return None


def build(raw_path: Path = OSM_WALKING_RAW, graph_id: str = GRAPH_ID) -> dict:
    raw_bytes = Path(raw_path).read_bytes()
    data = json.loads(gzip.decompress(raw_bytes))
    graph = load_raw_graph(graph_id)
    used = {e["osm_way_id"] for e in graph["edges"]}
    classes: list[str] = []
    class_idx: dict[str, int] = {}
    ways: dict[str, list] = {}
    for el in data["elements"]:
        if el.get("type") != "way" or el["id"] not in used:
            continue
        tags = el.get("tags") or {}
        hw = tags.get("highway") or "unknown"
        if hw not in class_idx:
            class_idx[hw] = len(classes)
            classes.append(hw)
        ways[str(el["id"])] = [class_idx[hw], kazakh_name(tags), 1 if tags.get("footway") == "sidewalk" else 0]
    return {
        "schema": "r12-way-tags-v1",
        "graph_id": graph_id,
        "graph_digest": graph.get("digest"),
        "source": {
            "path": str(Path(raw_path).resolve().relative_to(ROOT)) if Path(raw_path).resolve().is_relative_to(ROOT) else str(raw_path),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "snapshot_at": (data.get("osm3s") or {}).get("timestamp_osm_base"),
        },
        "license": {"id": "ODbL-1.0", "attribution": "© OpenStreetMap contributors"},
        "evidence_type": "derived",
        "note": "Производная таблица из снимка OSM: тип дороги (highway), казахское название, признак тротуара. Граф не менялся.",
        "classes": classes,
        "ways": dict(sorted(ways.items(), key=lambda kv: int(kv[0]))),
        "count": len(ways),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(GEO_DIR / "way_tags.json"))
    args = ap.parse_args(argv)
    result = build()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8")
    print(f"way_tags: {result['count']} линий, {len(result['classes'])} типов -> {out} ({out.stat().st_size // 1024} КБ)")


if __name__ == "__main__":
    main()
