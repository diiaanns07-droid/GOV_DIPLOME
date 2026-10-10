"""Куда привязать жалобу: 1–3 кандидата по точке и категории (CONTRACT §4, §7 GET /targets).

Ответ: {"candidates": [{"target": {kind, id, label_ru, label_kk}, "distance_m", "geometry", "approximate"}]}
- object  — реальный объект OSM рядом (остановка, площадка, спортплощадка, парк, место для мусора);
- segment — ребро пешеходного графа (id osm-w<way>-<n>) с настоящей формой улицы;
- area    — двор (landuse=residential) или ячейка ~150 м, если двора нет; ячейка — всегда «примерное место».
Порядок видов — target_kinds категории из categories_v2.json; ближний кандидат второго вида может
обойти дальний кандидат первого (штраф KIND_STEP_M за каждую позицию в списке видов).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from . import geo
from .graph import StreetGraph, get_graph
from .objects import Cells, FeatureSet, get_layers
from .paths import CATEGORIES

KIND_STEP_M = 25.0      # «штраф» в метрах за второй и третий вид привязки категории
OBJECT_RADIUS_M = 150.0  # остановку ищем шире: житель часто ставит точку «примерно»
SEGMENT_RADIUS_M = 80.0
YARD_RADIUS_M = 40.0
LABEL_STREET_RADIUS_M = 150.0

# Какие объекты OSM подходят категории (виды привязки берутся из categories_v2.json).
CATEGORY_OBJECT_KINDS = {
    "transport": ("bus_stop",),
    "yards": ("playground", "pitch", "park"),
    "waste": ("waste",),
}
# Какие улицы предпочитать для участка: road — проезжая часть, service — проезды, foot — тротуары.
CATEGORY_SEGMENT_GROUPS = {
    "roads": ("road", "service"),
    "sidewalks": ("foot",),
    "parking": ("service", "road"),
    "snow_ice": ("road", "service", "foot"),
}

# Подписи. Казахские формы — на проверку R11/владельцу (KK_REVIEW), см. INTEGRATION.txt.
OBJECT_LABELS = {
    "bus_stop": ("Остановка «{n}»", "«{n}» аялдамасы", "Остановка без названия", "Атауы жоқ аялдама"),
    "playground": ("Детская площадка «{n}»", "«{n}» балалар алаңы", "Детская площадка", "Балалар алаңы"),
    "pitch": ("Спортплощадка «{n}»", "«{n}» спорт алаңы", "Спортплощадка", "Спорт алаңы"),
    "park": ("Парк «{n}»", "«{n}» саябағы", "Парк или сквер", "Саябақ немесе гүлзар"),
    "waste": ("Контейнерная площадка «{n}»", "«{n}» қоқыс алаңы", "Контейнерная площадка", "Қоқыс алаңы"),
}


class TargetError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_cat_lock = threading.Lock()
_categories: dict[str, dict] = {}


def load_categories(path: Path | None = None) -> dict[str, dict]:
    p = Path(path) if path else CATEGORIES
    key = str(p)
    with _cat_lock:
        if key not in _categories:
            data = json.loads(p.read_text("utf-8"))
            _categories[key] = {c["id"]: c for c in data["categories"]}
        return _categories[key]


def _street_near(graph: StreetGraph, p) -> tuple[str | None, str | None]:
    """Ближайшая улица с названием — для подписи двора и примерного места."""
    for _, e, _ in graph.nearest(p, LABEL_STREET_RADIUS_M, accept=lambda e: bool(e.name)):
        return e.name, e.label_kk()
    return None, None


def object_target(f) -> dict:
    ru, kk, ru0, kk0 = OBJECT_LABELS.get(f.kind, ("{n}", "{n}", "Объект", "Нысан"))
    name_ru, name_kk = f.name_ru or f.name_kk, f.name_kk or f.name_ru
    if f.kind == "park" and f.raw.get("subkind") == "garden" and name_ru:
        ru, kk = "Сквер «{n}»", "«{n}» гүлзары"
    return {"kind": "object", "id": f.id, "object_kind": f.kind,
            "label_ru": ru.format(n=name_ru) if name_ru else ru0,
            "label_kk": kk.format(n=name_kk) if name_kk else kk0}


def segment_target(e) -> dict:
    if e.name:
        ru, kk = f"Участок: {e.name}", f"Учаске: {e.label_kk()}"
    elif e.group == "foot":
        ru, kk = "Тротуар или дорожка без названия", "Атауы жоқ жаяу жол"
    elif e.group == "service":
        ru, kk = "Проезд без названия", "Атауы жоқ өтпе жол"
    else:
        ru, kk = "Участок улицы без названия", "Атауы жоқ көше учаскесі"
    return {"kind": "segment", "id": e.id, "label_ru": ru, "label_kk": kk}


def yard_target(f, street) -> dict:
    s_ru, s_kk = street
    if f.name_ru or f.name_kk:
        ru, kk = f"Двор: {f.name_ru or f.name_kk}", f"Аула: {f.name_kk or f.name_ru}"
    elif s_ru:
        ru, kk = f"Двор — {s_ru}", f"Аула — {s_kk}"
    else:
        ru, kk = "Двор", "Аула"
    return {"kind": "area", "id": f.id, "area_kind": "yard", "label_ru": ru, "label_kk": kk}


def cell_target(cell_id: str, street) -> dict:
    s_ru, s_kk = street
    ru = f"Примерное место — {s_ru}" if s_ru else "Примерное место"
    kk = f"Шамамен орны — {s_kk}" if s_kk else "Шамамен орны"
    return {"kind": "area", "id": cell_id, "area_kind": "cell", "label_ru": ru, "label_kk": kk}


def _segment_penalty(e, groups) -> float:
    """Для дороги главная улица важнее безымянного проезда во дворе: +12 м за каждую следующую группу,
    +5 м за отсутствие названия (в подписи жителю не на что опереться)."""
    pen = 0.0 if e.name else 5.0
    if groups and e.group in groups:
        pen += groups.index(e.group) * 12.0
    return pen


def _geom_point(p):
    return {"type": "Point", "coordinates": geo.round_coord(p)}


def targets(lon: float, lat: float, category: str, limit: int = 3, graph: StreetGraph | None = None,
            layers: tuple[FeatureSet, FeatureSet, Cells] | None = None, categories: dict | None = None) -> dict:
    cats = categories or load_categories()
    if category not in cats:
        raise TargetError("unknown_category", "Неизвестная категория.")
    graph = graph or get_graph()
    objects, yards, cells = layers or get_layers()
    p = (float(lon), float(lat))
    kinds = list(cats[category].get("target_kinds") or ["area"])
    found: list[tuple[float, dict]] = []  # (score, candidate)
    street_cache: list = []

    def street():
        if not street_cache:
            street_cache.append(_street_near(graph, p))
        return street_cache[0]

    for rank, kind in enumerate(kinds):
        penalty = rank * KIND_STEP_M
        if kind == "object":
            obj_kinds = CATEGORY_OBJECT_KINDS.get(category)
            for d, f in objects.near(p, OBJECT_RADIUS_M, obj_kinds)[:3]:
                geom = {"type": "Polygon", "coordinates": f.polygon} if f.polygon else _geom_point(f.point)
                found.append((d + penalty, {"target": object_target(f), "distance_m": round(d, 1),
                                            "geometry": geom, "point": geo.round_coord(f.point), "approximate": False}))
        elif kind == "segment":
            groups = CATEGORY_SEGMENT_GROUPS.get(category)
            near = graph.nearest(p, SEGMENT_RADIUS_M, limit=40)
            if groups:
                preferred = [r for r in near if r[1].group in groups or r[1].group == "unknown"]
                near = preferred or near
            ranked = sorted(near, key=lambda r: (r[0] + _segment_penalty(r[1], groups), r[1].id))
            seen_names: set = set()
            for d, e, pr in ranked:
                # Одна улица — один кандидат (ближайший кусок); безымянная линия OSM — тоже один.
                key = e.name or f"way-{e.way_id}"
                if key in seen_names:
                    continue
                seen_names.add(key)
                found.append((d + penalty + _segment_penalty(e, groups), {"target": segment_target(e), "distance_m": round(d, 1),
                                            "geometry": {"type": "LineString",
                                                         "coordinates": [geo.round_coord(c) for c in e.geometry]},
                                            "point": geo.round_coord(pr.point), "approximate": False}))
                if len(seen_names) >= 3:
                    break
        elif kind == "area":
            inside = yards.containing(p)
            if inside:
                f = inside[0]
                found.append((penalty, {"target": yard_target(f, street()), "distance_m": 0.0,
                                        "geometry": {"type": "Polygon", "coordinates": f.polygon},
                                        "point": geo.round_coord(p), "approximate": False}))
            else:
                for d, f in yards.near(p, YARD_RADIUS_M)[:1]:
                    found.append((d + penalty, {"target": yard_target(f, street()), "distance_m": round(d, 1),
                                                "geometry": {"type": "Polygon", "coordinates": f.polygon},
                                                "point": geo.round_coord(p), "approximate": False}))
    found.sort(key=lambda r: (r[0], r[1]["target"]["id"]))
    out = [c for _, c in found[:limit]]
    # Ни одного кандидата рядом (или категория без «area») — честное «примерное место» ячейкой ~150 м.
    if not out or ("area" in kinds and not any(c["target"]["kind"] == "area" for c in out) and len(out) < limit):
        cid = cells.cell_id(p)
        out.append({"target": cell_target(cid, street()), "distance_m": 0.0,
                    "geometry": {"type": "Polygon", "coordinates": cells.polygon(cid)},
                    "point": geo.round_coord(p), "approximate": True})
    return {"candidates": out[:limit]}
