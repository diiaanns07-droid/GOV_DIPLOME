"""Работа v2 (раунд 15, CONTRACT §5.6): служба, вид, участки улиц и даты — для календаря R12 и «Моего двора» R16.

Хранится в той же таблице civic_nearby_items, что «Работы и отключения» раунда 14 (миграция 10 добавила колонки
service, kind, segments_json, place_json, world_key). Старый формат записи для R08 «Рядом» не меняется: в нём
`source` — по-прежнему служба-источник отключения. Запись v2 (work_record) — формат §5.6, в нём
`source` — "real" | "demo" (откуда запись), а служба — поле `service`.

Участки улиц — только рёбра графа OSM R12 (CONTRACT §8: никаких линий «от руки»):
  - «по улице»: сотрудник отмечает на карте начало и конец участка, сервер сам строит участок функцией R12
    engine.civic_geo.api.segment_between (форма линии и id рёбер — из OSM), клиентской линии не верим;
  - из редактора R12 или демо-мира R02: список id рёбер `segments`; форма линии — геометрия этих рёбер из графа R12.
Нет модуля карты R12 — участок «по улице» не построить (понятная ошибка формы), список рёбер принимается по формату.
"""

from __future__ import annotations

import logging
import math
import re

from .validate import _Errors


LOGGER = logging.getLogger("ui.civic_store.works_v2")

KINDS_V2 = ("dig", "surface", "closure", "landscape", "lighting", "other")
# Вид раунда 14 (подпись R08 works.kind.*) по виду v2 — если форма прислала только вид v2.
KIND_TO_WORK_KIND = {"dig": "roadworks", "surface": "roadworks", "closure": "roadworks",
                     "landscape": "landscaping", "lighting": "lighting", "other": "other"}
# Вид v2 по виду раунда 14 — для старых клиентов (форма FINAL-4 шлёт только work_kind). Та же таблица — в миграции 10.
WORK_KIND_TO_KIND = {"roadworks": "surface", "construction": "other", "landscaping": "landscape",
                     "lighting": "lighting", "event": "other", "other": "other"}
WORK_KIND_TO_SERVICE = {"roadworks": "road", "landscaping": "landscaping", "lighting": "lighting"}
SEGMENT_RE = re.compile(r"^osm-w\d{1,12}-\d{1,5}\Z")   # id ребра графа R12: osm-w<way>-<номер куска>
MAX_SEGMENTS = 200
EARTH_M = 6371008.8


class SegmentsUnavailable(RuntimeError):
    """Граф улиц R12 не загружен: участок «по улице» построить нельзя."""


# --- граф улиц R12 (необязательная зависимость) -----------------------------------------------------------------
# Тесты подменяют эти две функции, чтобы не грузить граф Астаны (2–4 с).

def _segment_between(a, b):
    """Участок улицы R12 между точками [lon, lat]: {geometry, edge_ids, street_ru, street_kk, length_m}."""
    try:
        from engine.civic_geo import api as geo_api
    except Exception as exc:  # noqa: BLE001 — нет модуля R12 в сборке
        raise SegmentsUnavailable(str(exc)) from None
    return geo_api.segment_between(a, b, kind="road")


def _edges(ids):
    """Рёбра графа R12 по id: {id: (geometry [(lon, lat)…], name_ru, name_kk, a, b)}; None — граф недоступен."""
    try:
        from engine.civic_geo.graph import get_graph
        graph = get_graph()
    except Exception:  # noqa: BLE001 — нет модуля или файла графа: проверяем только формат id
        LOGGER.info("works v2: граф улиц R12 недоступен, участки проверены только по формату id")
        return None
    out = {}
    for edge_id in ids:
        edge = graph.by_id.get(edge_id)
        if edge is not None:
            out[edge_id] = (edge.geometry, edge.name, edge.label_kk(), edge.a, edge.b)
    return out


segment_between = _segment_between
edges_lookup = _edges


# --- разбор полей формы -----------------------------------------------------------------------------------------

def _point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        lon, lat = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if not (70.9 <= lon <= 71.9 and 50.9 <= lat <= 51.4):  # Астана с запасом (как ASTANA_BOUNDS шлюза)
        return None
    return [round(lon, 7), round(lat, 7)]


def clean_segments(payload: dict, errors: _Errors):
    """Участки из запроса → (segments | None, place | None, geometry | None).

    segment: {from: [lon, lat], to: [lon, lat]} — участок «по улице» (строит R12);
    segments: ["osm-w…-n", …] — рёбра из редактора R12 или демо-мира.
    """
    segment, ids = payload.get("segment"), payload.get("segments")
    if segment is not None and ids is not None:
        errors.add("segments", "Либо участок по улице (segment), либо список участков (segments).")
        return None, None, None
    if segment is not None:
        if not isinstance(segment, dict) or set(segment) - {"from", "to"}:
            errors.add("segment", "Участок: {from: [долгота, широта], to: [долгота, широта]}.")
            return None, None, None
        a, b = _point(segment.get("from")), _point(segment.get("to"))
        if a is None or b is None:
            errors.add("segment", "Отметьте начало и конец участка на карте Астаны.")
            return None, None, None
        try:
            built = segment_between(a, b)
        except SegmentsUnavailable:
            errors.add("segment", "Карта улиц сейчас не загружена — участок не построить. Сохраните точку на карте.")
            return None, None, None
        except Exception as exc:  # noqa: BLE001 — ошибка R12 (точка далеко от улицы, нет пути) — его текст
            message = getattr(exc, "message", None) or str(exc) or "Участок не построить: выберите точки на одной улице."
            errors.add("segment", str(message)[:200])
            return None, None, None
        edge_ids = [e for e in (built.get("edge_ids") or []) if isinstance(e, str) and SEGMENT_RE.match(e)]
        geometry = built.get("geometry")
        if not edge_ids or not isinstance(geometry, dict) or geometry.get("type") != "LineString":
            errors.add("segment", "Участок не построить: выберите точки на одной улице.")
            return None, None, None
        place = {"from": a, "to": b, "street_ru": built.get("street_ru"), "street_kk": built.get("street_kk"),
                 "length_m": built.get("length_m"), "by": "street"}
        return edge_ids[:MAX_SEGMENTS], place, geometry
    if ids is None:
        return None, None, None
    if not isinstance(ids, list) or not ids or len(ids) > MAX_SEGMENTS or \
            not all(isinstance(e, str) and SEGMENT_RE.match(e) for e in ids):
        errors.add("segments", f"Участки — от 1 до {MAX_SEGMENTS} id участков улиц карты (osm-w…-n).")
        return None, None, None
    unique = list(dict.fromkeys(ids))
    found = edges_lookup(unique)
    if found is None:  # граф недоступен: форму линии нарисует R12, у нас — только id
        return unique, {"by": "editor"}, None
    missing = [e for e in unique if e not in found]
    if missing:
        errors.add("segments", "Участок не найден на карте улиц: " + ", ".join(missing[:3]) + ".")
        return None, None, None
    geometry = chain_geometry([found[e] for e in unique])
    names = [found[e][1] for e in unique if found[e][1]]
    names_kk = [found[e][2] for e in unique if found[e][2]]
    place = {"street_ru": names[0] if names else None, "street_kk": names_kk[0] if names_kk else None,
             "length_m": round(sum(_line_length(found[e][0]) for e in unique), 1), "by": "editor"}
    return unique, place, geometry


def chain_geometry(edges):
    """Форма участка из рёбер OSM: одна линия, если рёбра идут цепочкой, иначе MultiLineString. Вершины — из OSM."""
    lines = [[list(map(float, p)) for p in geometry] for geometry, *_rest in edges]
    if len(edges) == 1:
        return {"type": "LineString", "coordinates": lines[0]}
    # Цепочка по общим узлам a/b графа: ищем порядок, в котором каждое следующее ребро начинается там, где кончилось
    # предыдущее. Ребро «прямо» идёт от a к b (порядок вершин OSM), «обратно» — от b к a.
    ends = [(a, b) for _g, _n, _k, a, b in edges]
    n = len(edges)
    for start in range(n):
        for start_reversed in (False, True):
            order, used = [(start, start_reversed)], {start}
            node = ends[start][0] if start_reversed else ends[start][1]
            while len(order) < n:
                step = None
                for i in range(n):
                    if i in used:
                        continue
                    if ends[i][0] == node:
                        step = (i, False)
                        break
                    if ends[i][1] == node:
                        step = (i, True)
                        break
                if step is None:
                    break
                order.append(step)
                used.add(step[0])
                node = ends[step[0]][0] if step[1] else ends[step[0]][1]
            if len(order) == n:
                coords = []
                for i, backwards in order:
                    part = list(reversed(lines[i])) if backwards else lines[i]
                    coords.extend(part[1:] if coords and part[0] == coords[-1] else part)
                return {"type": "LineString", "coordinates": coords}
    return {"type": "MultiLineString", "coordinates": lines}


def _line_length(points) -> float:
    total = 0.0
    for p, q in zip(points, points[1:]):
        total += haversine_m(p, q)
    return total


def haversine_m(p, q) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (p[0], p[1], q[0], q[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_M * math.asin(min(1.0, math.sqrt(h)))


def distance_to_geometry_m(point, geometry) -> float | None:
    """Расстояние от точки [lon, lat] до точки или линии работы (метры); None — у работы нет места."""
    if not isinstance(geometry, dict):
        return None
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind == "Point":
        return haversine_m(point, coords)
    lines = [coords] if kind == "LineString" else coords if kind == "MultiLineString" else None
    if not lines:
        return None
    best = None
    # Локальная проекция в метрах вокруг точки: на масштабе города ошибка меньше метра.
    k = math.cos(math.radians(point[1]))
    for line in lines:
        for p, q in zip(line, line[1:]):
            ax, ay = (p[0] - point[0]) * k, p[1] - point[1]
            bx, by = (q[0] - point[0]) * k, q[1] - point[1]
            dx, dy = bx - ax, by - ay
            t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
            cx, cy = ax + t * dx, ay + t * dy
            d = math.hypot(cx, cy) * math.pi / 180 * EARTH_M
            best = d if best is None or d < best else best
        if len(line) == 1:
            d = haversine_m(point, line[0])
            best = d if best is None or d < best else best
    return best


# --- запись v2 для соседей ---------------------------------------------------------------------------------------

def dates_of(item: dict):
    """(starts_on, ends_on) работы или отключения — даты Астаны ГГГГ-ММ-ДД; неизвестно — None."""
    if item["type"] == "outage":
        start, end = item.get("start"), item.get("end")
        return (start[:10] if isinstance(start, str) else None), (end[:10] if isinstance(end, str) else None)
    start = item.get("start")
    return (start[:10] if isinstance(start, str) else None), (item.get("forecast_end") or item.get("planned_end"))


def work_record(item: dict) -> dict:
    """Запись CONTRACT §5.6 из записи «Рядом» (NearbyRepository._item): то, что читают R12 и R16."""
    starts_on, ends_on = dates_of(item)
    planned, forecast = item.get("planned_end"), item.get("forecast_end")
    return {
        "id": item["id"], "type": item["type"], "service": item.get("service"), "kind": item.get("kind"),
        "segments": list(item.get("segments") or []), "starts_on": starts_on, "ends_on": ends_on,
        "source": "demo" if item.get("demo") else "real",
        "status": item.get("status"), "utility": item.get("utility"), "district": item.get("district"),
        "title_ru": item.get("title_ru"), "title_kk": item.get("title_kk"),
        "street_ru": item.get("street_ru"), "street_kk": item.get("street_kk"),
        "zone_ru": item.get("zone_ru"), "zone_kk": item.get("zone_kk"),
        "planned_end": planned, "forecast_end": forecast,
        "delayed": bool(planned and forecast and forecast > planned),
        "geometry": item.get("geometry"), "updated_at": item.get("updated_at"), "demo": bool(item.get("demo")),
        # Раздел сотрудника «Работы и отключения» открывает эту запись (оболочка R01: #works/<id>).
        "link": "#works/" + item["id"],
    }


def overlaps(record: dict, date_from=None, date_to=None) -> bool:
    """Работа идёт хотя бы один день периода [date_from, date_to]; неизвестное начало — «с давних пор»."""
    start, end = record.get("starts_on"), record.get("ends_on") or record.get("starts_on")
    if date_to and start and start > date_to:
        return False
    if date_from and end and end < date_from:
        return False
    return bool(start or end)


__all__ = ["KINDS_V2", "KIND_TO_WORK_KIND", "MAX_SEGMENTS", "SEGMENT_RE", "SegmentsUnavailable", "WORK_KIND_TO_KIND",
           "WORK_KIND_TO_SERVICE", "chain_geometry", "clean_segments", "dates_of", "distance_to_geometry_m",
           "haversine_m", "overlaps", "work_record"]
