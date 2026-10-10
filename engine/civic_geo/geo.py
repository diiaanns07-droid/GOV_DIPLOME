"""Геометрия в метрах для небольших расстояний внутри города (только стандартная библиотека).

Координаты везде — [lon, lat] (как в GeoJSON и в графе OSM).
Для расстояний до нескольких километров используется локальная равнопромежуточная проекция:
x = Δlon·cos(lat0)·k, y = Δlat·k. В Астане (широта ~51°) погрешность на отрезке до 5 км
меньше 0,1 % — это сантиметры на длинах, с которыми работает карта (ребро графа в среднем ~40 м).
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

EARTH_RADIUS_M = 6371008.8
M_PER_DEG = math.pi / 180.0 * EARTH_RADIUS_M  # метров в одном градусе широты (~111 195 м)

Point = Sequence[float]


def haversine_m(a: Point, b: Point) -> float:
    """Расстояние по большой окружности между двумя точками [lon, lat], в метрах."""
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


class LocalFrame:
    """Плоская система координат в метрах вокруг точки lat0 (для расчётов рядом с этой точкой)."""

    __slots__ = ("lon0", "lat0", "kx", "ky")

    def __init__(self, lon0: float, lat0: float):
        self.lon0 = lon0
        self.lat0 = lat0
        self.kx = M_PER_DEG * math.cos(math.radians(lat0))
        self.ky = M_PER_DEG

    def to_xy(self, p: Point) -> tuple[float, float]:
        return ((p[0] - self.lon0) * self.kx, (p[1] - self.lat0) * self.ky)

    def to_lonlat(self, x: float, y: float) -> list[float]:
        return [self.lon0 + x / self.kx, self.lat0 + y / self.ky]


def _seg_project(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> tuple[float, float]:
    """Проекция точки P на отрезок AB в плоскости: (квадрат расстояния, параметр t в [0, 1])."""
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    if ll <= 0.0:
        t = 0.0
    else:
        t = ((px - ax) * dx + (py - ay) * dy) / ll
        t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    qx, qy = ax + t * dx - px, ay + t * dy - py
    return qx * qx + qy * qy, t


def polyline_length_m(line: Sequence[Point]) -> float:
    if len(line) < 2:
        return 0.0
    f = LocalFrame(line[0][0], line[0][1])
    total = 0.0
    prev = f.to_xy(line[0])
    for p in line[1:]:
        cur = f.to_xy(p)
        total += math.hypot(cur[0] - prev[0], cur[1] - prev[1])
        prev = cur
    return total


class Projection:
    """Результат проекции точки на ломаную."""

    __slots__ = ("distance_m", "index", "t", "along_m", "point")

    def __init__(self, distance_m: float, index: int, t: float, along_m: float, point: list[float]):
        self.distance_m = distance_m  # расстояние от точки до ломаной
        self.index = index            # номер отрезка ломаной (между вершинами index и index+1)
        self.t = t                    # положение на этом отрезке, 0..1
        self.along_m = along_m        # расстояние вдоль ломаной от её начала до проекции
        self.point = point            # сама проекция [lon, lat]


def project_on_polyline(p: Point, line: Sequence[Point]) -> Projection:
    """Ближайшая к p точка ломаной line (минимум 1 вершина)."""
    if not line:
        raise ValueError("пустая линия")
    f = LocalFrame(p[0], p[1])
    px, py = 0.0, 0.0
    if len(line) == 1:
        x, y = f.to_xy(line[0])
        return Projection(math.hypot(x, y), 0, 0.0, 0.0, [line[0][0], line[0][1]])
    best = None
    along = 0.0
    a = f.to_xy(line[0])
    for i in range(len(line) - 1):
        b = f.to_xy(line[i + 1])
        d2, t = _seg_project(px, py, a[0], a[1], b[0], b[1])
        seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
        if best is None or d2 < best[0]:
            best = (d2, i, t, along + t * seg_len, a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        along += seg_len
        a = b
    d2, i, t, al, qx, qy = best
    return Projection(math.sqrt(d2), i, t, al, f.to_lonlat(qx, qy))


def distance_to_polyline_m(p: Point, line: Sequence[Point]) -> float:
    return project_on_polyline(p, line).distance_m


def point_at_along(line: Sequence[Point], along_m: float) -> tuple[int, list[float]]:
    """Точка на ломаной на расстоянии along_m от начала: (номер отрезка, [lon, lat])."""
    f = LocalFrame(line[0][0], line[0][1])
    walked = 0.0
    a = f.to_xy(line[0])
    for i in range(len(line) - 1):
        b = f.to_xy(line[i + 1])
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if walked + seg >= along_m or i == len(line) - 2:
            t = 0.0 if seg <= 0 else max(0.0, min(1.0, (along_m - walked) / seg))
            return i, f.to_lonlat(a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        walked += seg
        a = b
    return 0, [line[0][0], line[0][1]]


def cut_polyline(line: Sequence[Point], start_m: float, end_m: float) -> list[list[float]]:
    """Часть ломаной между расстояниями start_m и end_m от начала.

    Если start_m > end_m, часть возвращается в обратном направлении (от start к end).
    Промежуточные вершины берутся из исходной линии без изменений — форма улицы сохраняется точно.
    """
    if start_m > end_m:
        return list(reversed(cut_polyline(line, end_m, start_m)))
    total = polyline_length_m(line)
    start_m = max(0.0, min(total, start_m))
    end_m = max(0.0, min(total, end_m))
    i0, p0 = point_at_along(line, start_m)
    i1, p1 = point_at_along(line, end_m)
    out = [p0]
    for k in range(i0 + 1, i1 + 1):
        out.append([line[k][0], line[k][1]])
    out.append(p1)
    return dedupe(out)


def dedupe(line: Iterable[Point], eps_m: float = 0.01) -> list[list[float]]:
    """Убирает подряд идущие совпадающие вершины (ближе eps_m)."""
    out: list[list[float]] = []
    for p in line:
        q = [float(p[0]), float(p[1])]
        if out and haversine_m(out[-1], q) < eps_m:
            continue
        out.append(q)
    return out


def point_in_ring(p: Point, ring: Sequence[Point]) -> bool:
    """Точка внутри замкнутого кольца (луч вдоль долготы, чётно-нечётное правило)."""
    x, y = p[0], p[1]
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y):
            xc = xi + (y - yi) * (xj - xi) / (yj - yi)
            if x < xc:
                inside = not inside
        j = i
    return inside


def point_in_polygon(p: Point, rings: Sequence[Sequence[Point]]) -> bool:
    """Полигон GeoJSON: первое кольцо — внешняя граница, остальные — дыры."""
    if not rings or not point_in_ring(p, rings[0]):
        return False
    return not any(point_in_ring(p, hole) for hole in rings[1:])


def distance_to_polygon_m(p: Point, rings: Sequence[Sequence[Point]]) -> float:
    """0 внутри полигона, иначе расстояние до ближайшей границы."""
    if point_in_polygon(p, rings):
        return 0.0
    return min(distance_to_polyline_m(p, ring) for ring in rings if ring)


def bbox_center(coords: Sequence[Point]) -> list[float]:
    """Точка для значка площадного объекта: центроид кольца, а если он вне полигона — ближайшая вершина к нему."""
    ring = list(coords)
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    f = LocalFrame(ring[0][0], ring[0][1])
    xy = [f.to_xy(p) for p in ring]
    a = cx = cy = 0.0
    for i in range(len(xy)):
        x0, y0 = xy[i]
        x1, y1 = xy[(i + 1) % len(xy)]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a) < 1e-9:
        c = [sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)]
    else:
        c = f.to_lonlat(cx / (3 * a), cy / (3 * a))
    if not point_in_ring(c, list(coords)):
        # Невыпуклый полигон (буква «Г»): значок ставим на вершину, а не в чужой двор.
        c = min(ring, key=lambda p: haversine_m(p, c))
    return round_coord(c)


def bbox_of(coords: Iterable[Point]) -> list[float]:
    xs, ys = [], []
    for c in coords:
        xs.append(c[0])
        ys.append(c[1])
    return [min(xs), min(ys), max(xs), max(ys)]


def simplify(line: Sequence[Point], tolerance_m: float) -> list[list[float]]:
    """Упрощение Дугласа — Пекера с допуском в метрах (концы сохраняются)."""
    if len(line) <= 2:
        return [[p[0], p[1]] for p in line]
    f = LocalFrame(line[0][0], line[0][1])
    xy = [f.to_xy(p) for p in line]
    keep = [False] * len(line)
    keep[0] = keep[-1] = True
    stack = [(0, len(line) - 1)]
    tol2 = tolerance_m * tolerance_m
    while stack:
        i, j = stack.pop()
        best, best_k = -1.0, -1
        for k in range(i + 1, j):
            d2, _ = _seg_project(xy[k][0], xy[k][1], xy[i][0], xy[i][1], xy[j][0], xy[j][1])
            if d2 > best:
                best, best_k = d2, k
        if best_k > 0 and best > tol2:
            keep[best_k] = True
            stack.append((i, best_k))
            stack.append((best_k, j))
    return [[line[k][0], line[k][1]] for k in range(len(line)) if keep[k]]


def round_coord(p: Point, digits: int = 7) -> list[float]:
    """7 знаков после запятой ≈ 1 см — точность самого OSM."""
    return [round(p[0], digits), round(p[1], digits)]


def max_offset_m(line: Sequence[Point], reference: Sequence[Sequence[Point]], step_m: float = 2.0) -> float:
    """Наибольшее отклонение линии от набора эталонных ломаных (односторонне, с шагом step_m).

    Проверяются вершины линии и точки между ними через каждые step_m метров, так что
    «срезанный» угол улицы тоже будет замечен.
    """
    if not line or not reference:
        return float("inf")
    worst = 0.0
    samples: list[list[float]] = []
    for i in range(len(line) - 1):
        a, b = line[i], line[i + 1]
        seg = haversine_m(a, b)
        n = max(1, int(seg // step_m))
        for k in range(n):
            t = k / n
            samples.append([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])])
    samples.append([line[-1][0], line[-1][1]])
    for s in samples:
        d = min(distance_to_polyline_m(s, ref) for ref in reference)
        if d > worst:
            worst = d
    return worst
