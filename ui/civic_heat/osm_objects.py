"""Реальные объекты OSM Астаны (LOCAL-1, data/civic/astana/osm-objects/) — цели жалоб для тепловой карты.

Файлы не меняются: читаем сжатые ответы Overpass как есть (лицензия ODbL, © OpenStreetMap contributors).
id целей по CONTRACT §4:
    объект  — osm-node-<id> / osm-way-<id> / osm-relation-<id>  (остановки, площадки, спортплощадки, парки, мусор…);
    двор    — yard-<id пути> (landuse=residential), для отношения — yard-r<id>.
Подписи ru/kk строятся из тегов name / name:ru / name:kk; казахские окончания ставим только к словам-типам
(«аялдамасы», «ауласы»), имена собственные не склоняем.
"""
from __future__ import annotations

import gzip
import json
import re
import threading
from pathlib import Path

from . import geo
from .config import ROOT

OSM_OBJECTS_DIR = ROOT / "data" / "civic" / "astana" / "osm-objects"
KK_LETTERS = re.compile(r"[әғқңөұүһіӘҒҚҢӨҰҮҺІ]")

# Набор → (вид цели, подтип, подпись без имени ru, kk, шаблон с именем ru, kk)
SETS = {
    "bus_stops": ("object", "bus_stop", "Остановка", "Аялдама", "Остановка «{n}»", "«{n}» аялдамасы"),
    "platforms": ("object", "bus_stop", "Остановка", "Аялдама", "Остановка «{n}»", "«{n}» аялдамасы"),
    "playgrounds": ("object", "playground", "Детская площадка", "Балалар алаңы", "Детская площадка «{n}»", "«{n}» балалар алаңы"),
    "pitches": ("object", "pitch", "Спортплощадка", "Спорт алаңы", "Спортплощадка «{n}»", "«{n}» спорт алаңы"),
    "parks": ("object", "park", "Парк", "Саябақ", "Парк «{n}»", "«{n}» саябағы"),
    "gardens": ("object", "garden", "Сквер", "Гүлзар", "Сквер «{n}»", "«{n}» гүлзары"),
    "waste_disposal": ("object", "waste_disposal", "Контейнерная площадка", "Қоқыс алаңы", "Контейнерная площадка «{n}»", "«{n}» қоқыс алаңы"),
    "recycling": ("object", "recycling", "Пункт приёма вторсырья", "Қайталама шикізат қабылдау пункті", "Пункт приёма вторсырья «{n}»", "«{n}» қайталама шикізат қабылдау пункті"),
    "street_lamps": ("object", "street_lamp", "Фонарь", "Көше шамы", "Фонарь «{n}»", "«{n}» көше шамы"),
    "schools": ("object", "school", "Школа", "Мектеп", "{n}", "{n}"),
    "kindergartens": ("object", "kindergarten", "Детский сад", "Балабақша", "{n}", "{n}"),
    "residential": ("area", "yard", "Двор", "Аула", "Двор ЖК «{n}»", "«{n}» ТК ауласы"),
}
# Порядок важен: при повторе (type, id) в нескольких наборах берётся первый (остановка важнее платформы).
SET_ORDER = ("bus_stops", "platforms", "playgrounds", "pitches", "parks", "gardens", "waste_disposal",
             "recycling", "schools", "kindergartens", "street_lamps", "residential")

_JK_PREFIX = re.compile(r"^(ЖК|Жилой комплекс|жилой комплекс|ТК)\s+", re.U)


def clean_complex_name(name: str) -> str:
    """'ЖК "Семейный"' → 'Семейный', 'Жилой комплекс Зелёный Квартал' → 'Зелёный Квартал'."""
    n = _JK_PREFIX.sub("", name.strip())
    return n.strip().strip('"«»„“”\'').strip()


def names(tags: dict) -> tuple[str | None, str | None]:
    """(имя для ru, имя для kk). В Астане тег name часто казахский, а name:ru — русский."""
    base = tags.get("name")
    ru = tags.get("name:ru") or base
    kk = tags.get("name:kk") or (base if base and KK_LETTERS.search(base) else None) or base
    return ru, kk


_STRAIGHT_QUOTES = re.compile(r'"([^"]+)"')


def inner_quotes(name: str) -> str:
    """Имя пойдёт внутрь «ёлочек»: прямые кавычки внутри заменяем на „лапки“ (МЦ „Астана-Эколайф“)."""
    return _STRAIGHT_QUOTES.sub(lambda m: "„" + m.group(1) + "“", name).replace("«", "„").replace("»", "“")


def labels(set_name: str, tags: dict) -> tuple[str, str] | None:
    kind, subtype, plain_ru, plain_kk, tpl_ru, tpl_kk = SETS[set_name]
    ru, kk = names(tags)
    if not ru:
        return None  # без имени подпись достраивается по ближайшей улице (targets.py)
    if subtype == "yard":
        ru, kk = clean_complex_name(ru), clean_complex_name(kk or ru)
    if "«{n}»" in tpl_ru:
        ru, kk = inner_quotes(ru), inner_quotes(kk or ru)
    return tpl_ru.format(n=ru), tpl_kk.format(n=kk or ru)


_SET_BY_SUBTYPE = {}
for _name in SET_ORDER:
    _SET_BY_SUBTYPE.setdefault(SETS[_name][1], _name)


def plain_labels(subtype: str | None) -> tuple[str, str] | None:
    """Подпись без имени по подтипу: ('Остановка', 'Аялдама'); None — подтип неизвестен."""
    name = _SET_BY_SUBTYPE.get(subtype or "")
    return (SETS[name][2], SETS[name][3]) if name else None


def labels_for_subtype(subtype: str | None, name_ru: str | None, name_kk: str | None = None) -> tuple[str, str] | None:
    """Подпись по подтипу и имени из чужого реестра (R12: name_ru, name_kk) — так же, как у своих объектов OSM."""
    name = _SET_BY_SUBTYPE.get(subtype or "")
    if not name or not name_ru:
        return None
    tags = {"name": name_ru, "name:ru": name_ru}
    if name_kk:
        tags["name:kk"] = name_kk
    return labels(name, tags)


def _ring(points) -> list | None:
    ring = [[round(p["lon"], 7), round(p["lat"], 7)] for p in points or [] if "lon" in p and "lat" in p]
    if len(ring) < 2:
        return None
    return ring


def _join_rings(parts: list[list]) -> list[list]:
    """Собирает замкнутые кольца из кусков путей отношения (куски могут идти в разные стороны)."""
    parts = [p[:] for p in parts if p and len(p) >= 2]
    rings = []
    while parts:
        cur = parts.pop(0)
        changed = True
        while cur[0] != cur[-1] and changed:
            changed = False
            for i, p in enumerate(parts):
                if p[0] == cur[-1]:
                    cur += p[1:]
                elif p[-1] == cur[-1]:
                    cur += p[::-1][1:]
                elif p[-1] == cur[0]:
                    cur = p[:-1] + cur
                elif p[0] == cur[0]:
                    cur = p[::-1][:-1] + cur
                else:
                    continue
                parts.pop(i)
                changed = True
                break
        if cur[0] == cur[-1] and len(cur) >= 4:
            rings.append(cur)
    return rings


def geometry_of(el: dict, area: bool) -> dict | None:
    """GeoJSON-геометрия элемента Overpass (out geom)."""
    t = el.get("type")
    if t == "node":
        return {"type": "Point", "coordinates": [round(el["lon"], 7), round(el["lat"], 7)]}
    if t == "way":
        ring = _ring(el.get("geometry"))
        if not ring:
            return None
        if ring[0] == ring[-1] and len(ring) >= 4:
            return {"type": "Polygon", "coordinates": [ring]}
        return None if area else {"type": "LineString", "coordinates": ring}
    if t == "relation":
        outer = [_ring(m.get("geometry")) for m in el.get("members", []) if m.get("type") == "way" and m.get("role") in ("outer", "")]
        inner = [_ring(m.get("geometry")) for m in el.get("members", []) if m.get("type") == "way" and m.get("role") == "inner"]
        outers = _join_rings([r for r in outer if r])
        inners = _join_rings([r for r in inner if r])
        if not outers:
            return None
        polys = [[o] for o in outers]
        for h in inners:
            for poly in polys:
                if geo.point_in_ring(h[0], poly[0]):
                    poly.append(h)
                    break
        return {"type": "MultiPolygon", "coordinates": polys} if len(polys) > 1 else {"type": "Polygon", "coordinates": polys[0]}
    return None


def is_bus_platform(tags: dict) -> bool:
    """public_transport=platform — это и автобус, и поезд. Остановка — только по правилу приёмки R10:
    highway=bus_stop или платформа с явным bus/trolleybus/share_taxi=yes; ж/д платформы — никогда (B-007)."""
    if tags.get("railway") in ("platform", "halt", "station") or tags.get("train") == "yes" or tags.get("subway") == "yes":
        return False
    return (tags.get("highway") == "bus_stop" or tags.get("bus") == "yes" or tags.get("trolleybus") == "yes"
            or tags.get("share_taxi") == "yes")


def target_id(set_name: str, el: dict) -> str | None:
    if SETS[set_name][1] == "yard":
        if el["type"] == "way":
            return f"yard-{el['id']}"
        if el["type"] == "relation":
            return f"yard-r{el['id']}"
        return None  # точка жилого комплекса — не двор
    return f"osm-{el['type']}-{el['id']}"


_lock = threading.Lock()
_cache: dict | None = None


def load(directory: Path | None = None) -> dict:
    """id → {kind, subtype, geometry, label_ru, label_kk, needs_street_label, district, source, osm}. Читается один раз."""
    global _cache
    with _lock:
        if _cache is not None and directory is None:
            return _cache
        base = Path(directory or OSM_OBJECTS_DIR) / "raw"
        out: dict = {}
        for set_name in SET_ORDER:
            path = base / f"{set_name}.json.gz"
            try:
                raw = json.loads(gzip.open(path).read().decode("utf-8"))
            except (OSError, ValueError):
                continue
            kind, subtype, plain_ru, plain_kk = SETS[set_name][:4]
            for el in raw.get("elements", []):
                if set_name == "platforms" and not is_bus_platform(el.get("tags") or {}):
                    continue  # ж/д платформы вокзала — не остановки (R10, B-007)
                tid = target_id(set_name, el)
                if not tid or tid in out:
                    continue
                g = geometry_of(el, area=(kind == "area"))
                if not g:
                    continue
                lab = labels(set_name, el.get("tags") or {})
                anchor = geo.anchor_of(g)
                out[tid] = {
                    "kind": kind, "subtype": subtype, "geometry": g,
                    "label_ru": lab[0] if lab else plain_ru, "label_kk": lab[1] if lab else plain_kk,
                    "needs_street_label": lab is None,
                    "district": geo.district_of(anchor) if anchor else None,
                    "source": f"osm-objects/{set_name}", "osm": {"type": el["type"], "id": el["id"]},
                }
        if directory is None:
            _cache = out
        return out


def available() -> bool:
    return (OSM_OBJECTS_DIR / "raw" / "bus_stops.json.gz").exists()
