"""Расстояния на местности для фильтра «рядом» (≤ 200 м). Точки — [lon, lat] (WGS84), как в CONTRACT §5."""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8


def parse_point(point) -> tuple[float, float] | None:
    """[lon, lat] / (lon, lat) / {"lon":…, "lat":…} -> (lon, lat); иначе None. NaN и выход за диапазон — None."""
    try:
        if isinstance(point, dict):
            lon, lat = float(point["lon"]), float(point["lat"])
        else:
            lon, lat = (float(v) for v in point)
    except (TypeError, ValueError, KeyError):
        return None
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return lon, lat


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Расстояние по большому кругу (формула гаверсинусов), метры."""
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def bbox_around(point: tuple[float, float], radius_m: float) -> tuple[float, float, float, float]:
    """Прямоугольник (lon_min, lat_min, lon_max, lat_max), гарантированно содержащий круг radius_m.

    Нужен, чтобы хранилище R09 отдало только ближайшие записи (SQL по lon/lat), а точное
    расстояние потом проверяет distance_m.
    """
    lon, lat = point
    dlat = math.degrees(radius_m / EARTH_RADIUS_M)
    coslat = max(math.cos(math.radians(lat)), 1e-6)
    dlon = min(180.0, dlat / coslat)
    return lon - dlon, lat - dlat, lon + dlon, lat + dlat
