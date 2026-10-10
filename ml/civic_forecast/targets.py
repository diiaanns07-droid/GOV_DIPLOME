"""Территории прогноза R13 — реальные цели R12 (дворы, остановки, площадки, парки, места для мусора, участки улиц).

Источник — данные R12 (data/civic/astana/geo/: objects.json, yards.json, way_tags.json; ODbL, © OpenStreetMap
contributors) и пешеходный граф OSM (engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json).
Сами объекты НАСТОЯЩИЕ (evidence real), а жалобы на них в истории R13 — синтетика (см. history.py).

Чтобы прогноз не зависел от того, какая версия файлов R12 сейчас лежит в рабочем дереве, список территорий
собирается один раз командой

    python3 -m ml.civic_forecast build-targets [--geo-dir data/civic/astana/geo]

и хранится в ml/civic_forecast/data/targets.json (id, вид, имя ru/kk, точка, район). Полигоны и формы улиц
остаются у R12 — по id цели их берёт карта (CONTRACT §4).
"""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGETS_PATH = Path(__file__).with_name("data") / "targets.json"
GEO_DIR = REPO / "data" / "civic" / "astana" / "geo"
GRAPH_PATH = REPO / "engine" / "civic_scenarios" / "graphs" / "osm-astana-walking-20260506.graph.json"
GEOFENCE_PATH = REPO / "data" / "civic" / "astana" / "geofence.json"

# Виды территорий и вид цели по CONTRACT §4 (object | segment | area).
KIND_TO_TARGET = {"yard": "area", "bus_stop": "object", "playground": "object", "park": "object",
                  "waste": "object", "segment": "segment"}
OBJECT_KINDS = ("bus_stop", "playground", "park", "waste")
# Участки улиц: одно ребро на название улицы этих классов (way_tags.json R12: индекс класса).
MAJOR_CLASSES = {"primary": 0, "secondary": 1, "tertiary": 4}
MIN_SEGMENT_M = 40.0
LANDMARK_RADIUS_M = 800.0

DISTRICT_NAMES = {
    "almaty": ("Алматы", "Алматы"), "baikonur": ("Байконур", "Байқоңыр"), "esil": ("Есиль", "Есіл"),
    "nura": ("Нура", "Нұра"), "saraishyk": ("Сарайшык", "Сарайшық"), "saryarka": ("Сарыарка", "Сарыарқа"),
}


def _inside(lon, lat, ring) -> bool:
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi, xj, yj = ring[i][0], ring[i][1], ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def load_districts(path: Path = GEOFENCE_PATH):
    """[(district_id, ring)] из реальных полигонов OSM (geofence.json; не юридическая граница)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [(p["district_id"], ring) for p in data.get("polygons", []) if p.get("district_id") in DISTRICT_NAMES
            for ring in p.get("rings", []) if len(ring) >= 4]


def district_of(point, districts) -> str | None:
    lon, lat = point
    for district, ring in districts:
        if _inside(lon, lat, ring):
            return district
    return None


def build_targets(geo_dir: Path = GEO_DIR, graph_path: Path = GRAPH_PATH, geofence: Path = GEOFENCE_PATH) -> dict:
    """Собирает список территорий из файлов R12. Только объекты внутри районов Астаны."""
    districts = load_districts(geofence)
    objects = json.loads((geo_dir / "objects.json").read_text(encoding="utf-8"))
    yards = json.loads((geo_dir / "yards.json").read_text(encoding="utf-8"))
    way_tags = json.loads((geo_dir / "way_tags.json").read_text(encoding="utf-8"))
    items = []
    for yard in yards["items"]:
        items.append({"id": yard["id"], "kind": "yard", "name_ru": yard.get("name_ru"), "name_kk": yard.get("name_kk"),
                      "point": yard["point"], "osm": yard.get("osm")})
    for obj in objects["items"]:
        if obj["kind"] in OBJECT_KINDS:
            items.append({"id": obj["id"], "kind": obj["kind"], "name_ru": obj.get("name_ru"),
                          "name_kk": obj.get("name_kk"), "point": obj["point"], "osm": obj["id"]})
    # Участки: рёбра графа OSM крупных улиц. Одна улица в OSM разбита на много линий (way), поэтому группируем
    # по названию улицы и берём одно ребро: самой длинной линии улицы, из её середины.
    wanted = {way: tags for way, tags in way_tags["ways"].items() if tags[0] in MAJOR_CLASSES.values()}
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    by_way = {}
    for edge in graph["edges"]:
        way = str(edge.get("osm_way_id"))
        if way in wanted and edge.get("name") and edge.get("length_m", 0) >= MIN_SEGMENT_M:
            by_way.setdefault(way, []).append(edge)
    by_street = {}
    for way, edges in by_way.items():
        length = sum(e["length_m"] for e in edges)
        name = edges[0]["name"]
        if name not in by_street or (length, -int(way)) > by_street[name][0]:
            by_street[name] = ((length, -int(way)), way, edges)
    for name, (_, way, edges) in sorted(by_street.items()):
        edges.sort(key=lambda e: int(e["id"].rsplit("-", 1)[1]))
        edge = edges[len(edges) // 2]
        geom = edge["geometry"]
        mid = geom[len(geom) // 2] if len(geom) > 2 else [(geom[0][0] + geom[-1][0]) / 2, (geom[0][1] + geom[-1][1]) / 2]
        items.append({"id": edge["id"], "kind": "segment", "name_ru": name, "name_kk": wanted[way][1] or None,
                      "point": [round(mid[0], 7), round(mid[1], 7)], "osm": f"osm-way-{way}",
                      "length_m": round(edge["length_m"], 1)})
    out, seen = [], set()
    for item in items:
        if item["id"] in seen:
            continue
        district = district_of(item["point"], districts)
        if district is None:
            continue  # за пределами районов города (пригород в bbox графа)
        seen.add(item["id"])
        item["district"] = district
        item["target_kind"] = KIND_TO_TARGET[item["kind"]]
        out.append(item)
    _add_landmarks(out)
    out.sort(key=lambda i: (i["kind"], i["id"]))
    source = json.loads((geo_dir / "SOURCE.json").read_text(encoding="utf-8")) if (geo_dir / "SOURCE.json").exists() else {}
    return {
        "schema": "r13-targets-v1",
        "evidence_type": "real",
        "note": "Реальные объекты OSM из данных R12. Жалобы на них в истории R13 — синтетика.",
        "license": "ODbL-1.0, © OpenStreetMap contributors",
        "source": {"r12_geo_built_at": source.get("built_at"), "graph": graph.get("id"), "graph_digest": graph.get("digest")},
        "count": len(out),
        "by_kind": dict(sorted(Counter(i["kind"] for i in out).items())),
        "by_district": dict(sorted(Counter(i["district"] for i in out).items())),
        "items": out,
    }


def _metres(a, b) -> float:
    k = math.cos(math.radians((a[1] + b[1]) / 2))
    return math.hypot((a[0] - b[0]) * 111320 * k, (a[1] - b[1]) * 110540)


def _add_landmarks(items, radius_m: float = LANDMARK_RADIUS_M) -> None:
    """У территории без имени — ориентир: ближайшая названная остановка или улица (не дальше radius_m).

    Иначе в списке прогноза стояло бы просто «Двор» — непонятно, какой. Ориентир — тоже из OSM.
    """
    named = [i for i in items if i.get("name_ru") and i["kind"] in ("bus_stop", "segment")]
    cell = 0.01  # ~1 км: простая сетка, чтобы не перебирать все пары
    grid = {}
    for n in named:
        grid.setdefault((int(n["point"][0] / cell), int(n["point"][1] / cell)), []).append(n)
    for item in items:
        if item.get("name_ru"):
            continue
        gx, gy = int(item["point"][0] / cell), int(item["point"][1] / cell)
        best, best_d = None, radius_m
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for n in grid.get((gx + dx, gy + dy), ()):
                    if item["kind"] == "bus_stop" and n["kind"] == "bus_stop":
                        continue  # у безымянной остановки ориентир — улица, а не соседняя остановка
                    d = _metres(item["point"], n["point"])
                    if d < best_d:
                        best, best_d = n, d
        if best is not None:
            item["near"] = {"kind": best["kind"], "name_ru": best["name_ru"], "name_kk": best.get("name_kk"),
                            "distance_m": round(best_d)}


def load_targets(path: Path = TARGETS_PATH) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["items"]


# Русский тип улицы → казахский после названия, когда в OSM нет name:kk: «улица Кенгир» → «Кенгир көшесі»
# (то же правило, что kk_street_from_ru у R07; UX_REVIEW R11, ночь, п. 5: в ҚАЗ не оставлять «улица …» по-русски).
_KK_STREET_TYPES = (("улица ", "көшесі"), ("проспект ", "даңғылы"), ("переулок ", "тұйық көшесі"),
                    ("шоссе ", "тас жолы"), ("бульвар ", "бульвары"), ("площадь ", "алаңы"))


def kk_street(name_ru: str | None) -> str | None:
    """Казахская подпись улицы без name:kk: тип по-казахски, имя собственное как есть; не улица — без изменений."""
    if not name_ru:
        return name_ru
    for ru_type, kk_type in _KK_STREET_TYPES:
        if name_ru.startswith(ru_type):
            return f"{name_ru[len(ru_type):]} {kk_type}"
        if name_ru.endswith(" " + ru_type.strip()):
            return f"{name_ru[: -len(ru_type)]} {kk_type}"
    return name_ru


def label(target: dict, lang: str) -> str:
    """Подпись для интерфейса: «Остановка «Нура»», «Двор: ЖК Инжу Арена», «Участок ул. …»."""
    name = (target.get("name_kk") or kk_street(target.get("name_ru"))) if lang == "kk" else target.get("name_ru")
    kind = target["kind"]
    if lang == "kk":
        base = {"yard": "Аула", "bus_stop": "Аялдама", "playground": "Балалар алаңы", "park": "Саябақ",
                "waste": "Қоқыс алаңы", "segment": "Көше бөлігі"}[kind]
    else:
        base = {"yard": "Двор", "bus_stop": "Остановка", "playground": "Детская площадка", "park": "Парк",
                "waste": "Площадка для мусора", "segment": "Участок улицы"}[kind]
    if name:
        return f"{base} «{name}»"
    near = target.get("near")
    if near:
        near_name = (near.get("name_kk") or kk_street(near["name_ru"])) if lang == "kk" else near["name_ru"]
        if near["kind"] == "bus_stop":
            return f"{base} · жанында «{near_name}» аялдамасы" if lang == "kk" else f"{base} рядом: остановка «{near_name}»"
        return f"{base} · жанында {near_name}" if lang == "kk" else f"{base} рядом: {near_name}"
    return base
