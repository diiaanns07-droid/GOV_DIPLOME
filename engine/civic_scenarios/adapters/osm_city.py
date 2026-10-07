"""Reproducible conservative walking graph from an offline Overpass JSON extract.

OSM node IDs define connectivity, never geometric line intersections. Interior
degree-two geometry is retained while routing vertices are spaced <=~250m.
No network access and no inference of car access from walking data.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path

from ..canon import canonical_json, graph_digest
from ..graph import prepare_graph

BBOX = [71.2079, 50.9206, 71.7953, 51.3612]
GRAPH_ID = "osm-astana-walking-20260506"
ALLOW = {"yes", "designated", "permissive"}
DENY = {"no", "private"}
NON_PUBLIC = {"customers", "destination", "delivery", "permit", "agricultural", "forestry"}
PEDESTRIAN = {"footway", "pedestrian", "steps"}
EXCLUDE = {"construction", "proposed", "abandoned", "razed", "services", "rest_area", "elevator"}


def distance(a, b):
    lat1, lat2 = math.radians(a[1]), math.radians(b[1])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))


def foot_access(tags, *, node=False):
    # More specific foot tags override generic access, but conditional rules
    # cannot be flattened into a permanent permission for arbitrary analysis_at.
    if any(k.startswith(("foot:", "access:")) for k in tags):
        return "unknown"
    value = tags.get("foot", tags.get("access"))
    if value in DENY or value in NON_PUBLIC:
        return "denied"
    if value in ALLOW:
        return "allowed"
    if value is not None:
        return "unknown"
    if node:
        return "unknown" if tags.get("barrier") not in (None, "no") else "allowed"
    if tags.get("indoor") == "yes" or tags.get("conveying") not in (None, "no"):
        return "unknown"
    if tags.get("highway") in PEDESTRIAN:
        return "allowed"  # facility designated for walking in OSM, not a field survey
    return "unknown"


def build_graph(raw, source, bbox=BBOX):
    if raw.get("remark"):
        raise ValueError("Incomplete Overpass response: " + raw["remark"])
    nodes = {x["id"]: x for x in raw["elements"] if x["type"] == "node"}
    ways = sorted((x for x in raw["elements"] if x["type"] == "way" and x.get("tags", {}).get("highway") not in EXCLUDE
                   and x.get("tags", {}).get("area") != "yes"), key=lambda x: x["id"])
    def inside(n):
        return bbox[0] <= n["lon"] <= bbox[2] and bbox[1] <= n["lat"] <= bbox[3]
    uses = Counter(n for w in ways for n in w["nodes"])
    graph_nodes, edges = {}, []
    def add_node(nid):
        n = nodes[nid]
        graph_nodes.setdefault(nid, {"id": f"osm-n{nid}", "lon": n["lon"], "lat": n["lat"], "boundary": False})
        return graph_nodes[nid]
    for way in ways:
        tags, ids = way["tags"], way["nodes"]
        if any(n not in nodes for n in ids):
            raise ValueError(f"Way {way['id']} references a missing node")
        direction = tags.get("oneway:foot", "no")
        way_access = foot_access(tags)
        if direction not in ("no", "0", "false", "yes", "1", "true", "-1"):
            way_access = "unknown"
        path, length, part = [], 0., 0
        def flush():
            nonlocal path, length, part
            if len(path) < 2:
                return
            a, b = add_node(path[0]), add_node(path[-1])
            policies = [way_access, foot_access(nodes[path[0]].get("tags", {}), node=True), foot_access(nodes[path[-1]].get("tags", {}), node=True)]
            access = "denied" if "denied" in policies else "unknown" if "unknown" in policies else "allowed"
            coords = [[nodes[n]["lon"], nodes[n]["lat"]] for n in path]
            if direction == "-1":
                a, b, coords = b, a, list(reversed(coords))
            edges.append({"id": f"osm-w{way['id']}-{part}", "from": a["id"], "to": b["id"],
                          "length_m": round(length, 3), "access": access,
                          "oneway": direction in ("yes", "1", "true", "-1"), "geometry": coords,
                          "name": tags.get("name:ru", tags.get("name", "")), "osm_way_id": way["id"]})
            part += 1
            path, length = [path[-1]], 0.
        for i, nid in enumerate(ids):
            n = nodes[nid]
            if not inside(n):
                if path:
                    flush(); add_node(path[-1])["boundary"] = True
                path, length = [], 0.
                continue
            if i and not inside(nodes[ids[i - 1]]):
                add_node(nid)["boundary"] = True
            if path:
                prev = nodes[path[-1]]
                length += distance([prev["lon"], prev["lat"]], [n["lon"], n["lat"]])
            path.append(nid)
            if uses[nid] > 1 or foot_access(n.get("tags", {}), node=True) != "allowed" or length >= 250 or i == len(ids) - 1:
                flush()
    used = {e[k] for e in edges for k in ("from", "to")}
    graph = {"id": GRAPH_ID, "city": "astana", "mode": "walking", "evidence_type": "derived",
             "label": "Астана и окрестности · пешеходная сеть OSM", "bbox": bbox,
             "nodes": [n for _, n in sorted(graph_nodes.items()) if n["id"] in used], "edges": edges,
             "source": source, "license": {"id": "ODbL-1.0", "attribution": ["© OpenStreetMap contributors"]},
             "limitations": [
                 "Снимок OSM на " + raw.get("osm3s", {}).get("timestamp_osm_base", "неизвестную дату") + "; не оперативные данные.",
                 "Прямоугольная выборка Астаны и окрестностей: наличие линий не подтверждает полноту сети.",
                 "Пеший доступ: явные foot/access или пешеходное назначение footway/pedestrian/steps; прочие улицы без сведений имеют неизвестный доступ и исключены из маршрута.",
                 "Условный доступ и непроверенные барьеры считаются неизвестными. Ограничения через отношения OSM не разобраны; натурной проверки нет.",
                 "Только длина пути; нет прогноза пробок, времени, пропускной способности или выбросов. Не навигатор для поездок.",
             ]}
    graph["digest"] = graph_digest(graph)
    prepare_graph(graph)
    return graph


def street_index(graph):
    """Group nearby same-name geometry for map search only, never for routing.

    A 150m endpoint neighbourhood can join opposite carriageways. Distant namesakes
    remain separate choices instead of one bounding box covering unrelated towns.
    """
    names = {}
    for edge in graph["edges"]:
        if edge.get("name"):
            names.setdefault(edge["name"].strip().casefold(), []).append(edge)
    streets = []
    for _, edges in sorted(names.items()):
        name = min(edge["name"].strip() for edge in edges)
        parent = list(range(len(edges)))
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]; i = parent[i]
            return i
        buckets = {}
        for i, edge in enumerate(edges):
            for point in (edge["geometry"][0], edge["geometry"][-1]):
                x, y = int(point[0] * 70000 // 150), int(point[1] * 111000 // 150)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for j, other in buckets.get((x + dx, y + dy), ()):
                            if distance(point, other) <= 150:
                                parent[find(i)] = find(j)
                buckets.setdefault((x, y), []).append((i, point))
        groups = {}
        for i, edge in enumerate(edges):
            box = groups.setdefault(find(i), [180, 90, -180, -90])
            for lon, lat in edge["geometry"]:
                box[0], box[1] = min(box[0], lon), min(box[1], lat)
                box[2], box[3] = max(box[2], lon), max(box[3], lat)
        for idx, box in enumerate(sorted(groups.values())):
            label = name if len(groups) == 1 else f"{name} · участок {idx + 1} ({(box[1] + box[3]) / 2:.3f}, {(box[0] + box[2]) / 2:.3f})"
            streets.append({"name": name, "label": label, "bbox": box})
    return {"source": graph["source"], "license": graph["license"], "grouping": "same-name endpoints within 150m; map search only", "streets": streets}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    data = args.raw.read_bytes()
    if args.raw.suffix == ".gz":
        data = gzip.decompress(data)
    raw = json.loads(data)
    repo = Path(__file__).resolve().parents[3]
    folder = repo / "data/civic/astana/osm-walking"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "overpass.json.gz").write_bytes(gzip.compress(data, mtime=0))
    source = {"kind": "overpass_snapshot", "url": args.source_url, "query": args.query,
              "snapshot_at": raw["osm3s"]["timestamp_osm_base"], "retrieved_at": "2026-10-07",
              "raw_sha256": hashlib.sha256(data).hexdigest(), "path": "data/civic/astana/osm-walking/overpass.json.gz",
              "policy": "osm-conservative-walking-v1", "docs": ["https://wiki.openstreetmap.org/wiki/Key:foot", "https://wiki.openstreetmap.org/wiki/Key:access"]}
    graph = build_graph(raw, source)
    target = repo / "engine/civic_scenarios/graphs"
    content = (canonical_json(graph) + "\n").encode("utf-8")
    filename = GRAPH_ID + ".graph.json"
    (target / filename).write_bytes(content)
    manifest_path = target / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    entry = {k: graph[k] for k in ("id", "city", "mode", "label", "evidence_type", "digest", "source", "license", "bbox", "limitations")}
    entry.update(file=filename, file_sha256=hashlib.sha256(content).hexdigest(), default=True,
                 nodes=len(graph["nodes"]), edges=len(graph["edges"]))
    manifest["graphs"] = [g for g in manifest["graphs"] if g["id"] != GRAPH_ID] + [entry]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    (folder / "SOURCE.json").write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    index = street_index(graph)
    (repo / "web/civic/map/streets.json").write_text(canonical_json(index) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"id": graph["id"], "nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
                      "access": dict(Counter(e["access"] for e in graph["edges"])), "bytes": len(content), "digest": graph["digest"]}))


if __name__ == "__main__":
    main()
