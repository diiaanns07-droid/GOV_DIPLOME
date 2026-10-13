"""Индекс подсказок поиска для оболочки R01 (эталон A, правило качества Linear 1: «подсказки с первой буквы — улицы,
остановки, дворы, районы и горячие места»). R12 даёт данные улиц и объектов; поле, список и горячие места — R01 и R07.

    python3 -m engine.civic_geo search-index [--out web/civic/map/search_index.json]

Что внутри (всё из снимка OSM R12, тот же, что у карточек; ничего не выдумывается):
  streets — улицы с названием (ru и kk — как в подписях R12), точка на самой улице (середина самого длинного ребра),
            рамка всей улицы и id этого ребра (участок — цель R07/R09, его можно открыть карточкой);
  objects — остановки, площадки, спортплощадки и парки с названием, дворы с названием: id цели (как у карточки),
            вид, подписи ru/kk (те же функции, что у паспорта и карточек), точка.
Остановки с одинаковым названием ближе 300 м (две стороны улицы) — одна подсказка: первая по id, остальные id — в «also».
Улица с одним названием в разных частях города («1 улица») — отдельные подсказки (куски дальше 1,5 км друг от друга); у каждой — район «d».
Районы и горячие места сюда не входят — их R01 берёт у R07 (/heat) и из границ районов.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import geo
from .graph import get_graph
from .objects import get_layers
from .paths import WEB_MAP_DIR
from .targets import object_target, yard_target

OUT = WEB_MAP_DIR / "search_index.json"
DISTRICTS = WEB_MAP_DIR.parents[2] / "data" / "astana_districts.geojson"
OBJECT_KINDS = ("bus_stop", "playground", "pitch", "park")
STREET_GROUPS = ("road", "service", "foot")
SAME_STOP_M = 300.0


def _r(x: float) -> float:
    return round(float(x), 5)


def _districts(path: Path = DISTRICTS):
    """Районы Астаны (data/astana_districts.geojson): [(id, полигоны)] — чтобы различать одноимённые улицы."""
    if not path.is_file():
        return []
    out = []
    for f in json.loads(path.read_text("utf-8")).get("features", []):
        g = f.get("geometry") or {}
        polys = [g["coordinates"]] if g.get("type") == "Polygon" else g.get("coordinates", []) if g.get("type") == "MultiPolygon" else []
        out.append(((f.get("properties") or {}).get("id"), polys))
    return out


def _district_of(p, districts) -> str | None:
    for did, polys in districts:
        if any(geo.point_in_polygon(p, rings) for rings in polys):
            return did
    return None


def _clusters(edges, gap_m: float = 1500.0) -> list[list]:
    """Куски улицы: связанные общими узлами, затем склейка кусков, чьи рамки ближе gap_m (мост, безымянная вставка)."""
    parent: dict[str, str] = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for e in edges:
        parent[find(e.a)] = find(e.b)
    groups: dict[str, list] = {}
    for e in edges:
        groups.setdefault(find(e.a), []).append(e)
    parts = [{"edges": g, "box": [min(e.bbox[0] for e in g), min(e.bbox[1] for e in g), max(e.bbox[2] for e in g), max(e.bbox[3] for e in g)]}
             for g in groups.values()]

    def near(a, b) -> bool:
        dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2])) * 111320.0 * 0.63  # cos(51°) — Астана
        dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3])) * 110540.0
        return (dx * dx + dy * dy) ** 0.5 <= gap_m
    merged = True
    while merged and len(parts) > 1:
        merged = False
        for i in range(len(parts)):
            for j in range(i + 1, len(parts)):
                if near(parts[i]["box"], parts[j]["box"]):
                    a, b = parts[i], parts.pop(j)
                    a["edges"] += b["edges"]
                    a["box"] = [min(a["box"][0], b["box"][0]), min(a["box"][1], b["box"][1]), max(a["box"][2], b["box"][2]), max(a["box"][3], b["box"][3])]
                    merged = True
                    break
            if merged:
                break
    return sorted((p["edges"] for p in parts), key=lambda g: min(e.id for e in g))


def build(graph=None, layers=None) -> dict:
    graph = graph or get_graph()
    objects, yards, _ = layers or get_layers()
    districts = _districts()
    by_name: dict[str, dict] = {}
    for e in graph.edges:
        if not e.name or e.group not in STREET_GROUPS:
            continue
        s = by_name.setdefault(e.name, {"edges": [], "kk": {}})
        s["edges"].append(e)
        kk = e.label_kk()
        if kk:
            s["kk"][kk] = s["kk"].get(kk, 0) + e.length_m
    streets = []
    for name in sorted(by_name):
        s = by_name[name]
        kk = max(s["kk"].items(), key=lambda kv: (kv[1], kv[0]))[0] if s["kk"] else name
        # Одно название — разные улицы («1 улица» в разных посёлках): куски, связанные узлами или ближе 1,5 км, — одна улица.
        for part in _clusters(s["edges"]):
            longest = max(part, key=lambda e: (e.length_m, e.id))
            mid = geo.point_at_along(longest.geometry, longest.length_m / 2)[1]
            box = [min(e.bbox[0] for e in part), min(e.bbox[1] for e in part), max(e.bbox[2] for e in part), max(e.bbox[3] for e in part)]
            st = {"ru": name, "kk": kk, "c": [_r(mid[0]), _r(mid[1])], "b": [_r(v) for v in box], "seg": longest.id}
            d = _district_of(mid, districts)
            if d:
                st["d"] = d
            streets.append(st)
    out_objects = []
    stops: dict[str, list] = {}
    for f in sorted(objects.items, key=lambda f: f.id):
        if f.kind not in OBJECT_KINDS or not (f.name_ru or f.name_kk):
            continue
        t = object_target(f)
        if f.kind == "bus_stop":
            # Две стороны улицы с одним названием — одна подсказка; все id — в «also» (R01 сверяет их с горячими местами R07).
            same = next((o for o in stops.setdefault(t["label_ru"], []) if geo.haversine_m(o["_p"], f.point) < SAME_STOP_M), None)
            if same:
                same.setdefault("also", []).append(f.id)
                continue
        o = {"id": f.id, "k": f.kind, "ru": t["label_ru"], "kk": t["label_kk"], "c": [_r(f.point[0]), _r(f.point[1])], "_p": f.point}
        d = _district_of(f.point, districts)
        if d:
            o["d"] = d
        if f.kind == "bus_stop":
            stops[t["label_ru"]].append(o)
        out_objects.append(o)
    for o in out_objects:
        o.pop("_p", None)
    for f in sorted(yards.items, key=lambda f: f.id):
        if not (f.name_ru or f.name_kk):
            continue
        t = yard_target(f, (None, None))
        o = {"id": f.id, "k": "yard", "ru": t["label_ru"], "kk": t["label_kk"], "c": [_r(f.point[0]), _r(f.point[1])]}
        d = _district_of(f.point, districts)
        if d:
            o["d"] = d
        out_objects.append(o)
    counts = {"streets": len(streets)}
    for o in out_objects:
        counts[o["k"]] = counts.get(o["k"], 0) + 1
    return {
        "schema": "birge.search_index.v1",
        "source": {"graph_id": graph.id, "graph_digest": graph.digest, "snapshot_at": graph.snapshot_at,
                   "objects": (objects.meta or {}).get("schema"), "evidence_type": "observed (OpenStreetMap)"},
        "license": "ODbL 1.0 — © OpenStreetMap contributors",
        "fields": {"streets": "ru, kk — название; c — точка на улице [lon, lat]; b — рамка [w, s, e, n]; seg — id участка (цель); d — район (нет — за границей районов)",
                   "objects": "id — цель карточки; k — вид (bus_stop, playground, pitch, park, yard); ru, kk — подпись; c — точка; d — район; also — id других сторон той же остановки"},
        "counts": counts,
        "streets": streets,
        "objects": out_objects,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="search-index")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)
    data = build()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8")
    print(f"ok {out} {out.stat().st_size} байт {data['counts']}")
    return 0
