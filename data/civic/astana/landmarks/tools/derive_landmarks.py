"""Ориентиры Астаны (R05, раунд 15): центры и названия ru/kk — из данных OSM в репозитории.

Один источник для подписей ориентиров на карте (R01 web/civic/shell/basemap-style.js выделяет настоящие здания
подложки), для поиска («Байтерек» → перелёт камеры к зданию с наклоном) и для условных 3D-моделей пяти ориентиров
на карте (web/civic/build3d/build3d-landmarks.js; поле model и размеры — словарь MODELS ниже). Модели убрали поправкой
П1 15 окт и вернули по решению владельца 19 окт; у мечети Хазрет Султан модели нет — её здание рисует подложка.

Контуров самих зданий (Байтерек, Хан Шатыр, Ақорда, Хазрет Султан, «Нұр Әлем», Дворец мира и согласия) в репозитории нет:
выгрузка LOCAL-1 брала только площадки, остановки, парки и дворы. Зато в снимке пешеходной сети
(data/civic/astana/osm-walking/overpass.json.gz, OSM на 2026-05-06) есть дорожки и проезды, которые обходят
эти здания кольцом. Центр здания считаем по этим кольцам, а способ и номера линий OSM пишем в запись:

  named_node  — узел OSM с именем здания (Дворец мира и согласия: узел 5009488810);
  ring        — центр замкнутого кольца площади (Байтерек: кольцо радиусом 42 м вокруг монумента);
  ellipse     — центр и ось эллипса, вписанного по точкам кольцевого проезда (Хан Шатыр);
  circles     — средний центр концентрических колец (ЭКСПО: «Нұр Әлем» в центре колец павильонов);
  hole        — центр пустого места, со всех сторон окружённого дорожками (Ақорда, двор мечети Хазрет Султан).

Это вывод по соседним линиям, а не контур здания, поэтому у каждой записи check = "LOCAL-13": на ноутбуке
Codex скачивает контуры через Overpass и сверяет (research/round-15-results/R05/INTEGRATION.txt).

Запуск из корня репозитория:
    python3 data/civic/astana/landmarks/tools/derive_landmarks.py          # пересобрать landmarks.json
    python3 data/civic/astana/landmarks/tools/derive_landmarks.py --check  # только сверить с файлом

Пишет два одинаковых файла: data/civic/astana/landmarks/landmarks.json (источник) и
web/civic/build3d/data/landmarks.json (его берут поиск, подписи и модели в браузере: web/civic/build3d/landmarks.js,
basemap-style.js, build3d.js).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SNAPSHOT = ROOT / "data/civic/astana/osm-walking/overpass.json.gz"
OUT = ROOT / "data/civic/astana/landmarks/landmarks.json"
WEB_OUT = ROOT / "web/civic/build3d/data/landmarks.json"

KY = 110540.0  # метров в градусе широты (как в engine/civic_geo)


def kx(lat: float) -> float:
    return 111320.0 * math.cos(math.radians(lat))


def to_xy(lat: float, lon: float, o: tuple[float, float]) -> tuple[float, float]:
    return ((lon - o[1]) * kx(o[0]), (lat - o[0]) * KY)


def to_ll(x: float, y: float, o: tuple[float, float]) -> tuple[float, float]:
    return (o[0] + y / KY, o[1] + x / kx(o[0]))


def dist_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    x, y = to_xy(b[0], b[1], a)
    return math.hypot(x, y)


def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Гаусс с выбором главного элемента — без numpy (на ноутбуке Codex может не быть)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        if abs(m[c][c]) < 1e-12:
            raise ValueError("вырожденная система")
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] for i in range(n)]


class Snapshot:
    def __init__(self, path: Path):
        raw = path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        data = json.loads(gzip.decompress(raw))
        self.osm_base = (data.get("osm3s") or {}).get("timestamp_osm_base")
        self.nodes: dict[int, dict] = {}
        self.ways: dict[int, dict] = {}
        for el in data["elements"]:
            if el["type"] == "node":
                self.nodes[el["id"]] = el
            elif el["type"] == "way":
                self.ways[el["id"]] = el

    def way_points(self, wid: int) -> list[tuple[float, float]]:
        w = self.ways[wid]
        return [(self.nodes[n]["lat"], self.nodes[n]["lon"]) for n in w["nodes"]]

    def surface_segments(self, o: tuple[float, float], radius: float):
        """Отрезки линий на земле рядом с точкой (подземные переходы и туннели — не граница здания)."""
        out = []
        for w in self.ways.values():
            tags = w.get("tags") or {}
            if tags.get("tunnel") in ("yes", "building_passage") or str(tags.get("layer", "0")).startswith("-"):
                continue
            if tags.get("indoor") or tags.get("highway") in ("elevator", "corridor"):
                continue
            pts = [to_xy(self.nodes[n]["lat"], self.nodes[n]["lon"], o) for n in w["nodes"] if n in self.nodes]
            for a, b in zip(pts, pts[1:]):
                if min(math.hypot(*a), math.hypot(*b)) < radius * 2:
                    out.append((a, b))
        return out


def polygon_centroid(pts: list[tuple[float, float]]) -> tuple[float, float, float]:
    area = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        c = x0 * y1 - x1 * y0
        area += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    area /= 2.0
    return cx / (6 * area), cy / (6 * area), abs(area)


def ring_center(snap: Snapshot, wid: int, o):
    w = snap.ways[wid]
    if w["nodes"][0] != w["nodes"][-1]:
        raise ValueError(f"way {wid} не замкнут")
    pts = [to_xy(lat, lon, o) for lat, lon in snap.way_points(wid)][:-1]
    cx, cy, area = polygon_centroid(pts)
    rs = [math.hypot(x - cx, y - cy) for x, y in pts]
    return to_ll(cx, cy, o), {"radius_m": round(sum(rs) / len(rs), 1), "radius_spread_m": round(max(rs) - min(rs), 1)}


def circle_fit(points: list[tuple[float, float]]):
    """Окружность по точкам (Kåsa): x² + y² + D·x + E·y + F = 0."""
    a = [[0.0] * 3 for _ in range(3)]
    b = [0.0] * 3
    for x, y in points:
        row = [x, y, 1.0]
        rhs = -(x * x + y * y)
        for i in range(3):
            b[i] += row[i] * rhs
            for j in range(3):
                a[i][j] += row[i] * row[j]
    d, e, f = solve(a, b)
    cx, cy = -d / 2, -e / 2
    r = math.sqrt(max(cx * cx + cy * cy - f, 0.0))
    rms = math.sqrt(sum((math.hypot(x - cx, y - cy) - r) ** 2 for x, y in points) / len(points))
    return cx, cy, r, rms


def ellipse_fit(points: list[tuple[float, float]]):
    """Эллипс по точкам: A·x² + B·xy + C·y² + D·x + E·y = 1 (точки сдвинуты к их среднему)."""
    mx = sum(p[0] for p in points) / len(points)
    my = sum(p[1] for p in points) / len(points)
    a = [[0.0] * 5 for _ in range(5)]
    b = [0.0] * 5
    for x, y in points:
        x, y = x - mx, y - my
        row = [x * x, x * y, y * y, x, y]
        for i in range(5):
            b[i] += row[i]
            for j in range(5):
                a[i][j] += row[i] * row[j]
    A, B, C, D, E = solve(a, b)
    # Центр — где градиент равен нулю.
    x0, y0 = solve([[2 * A, B], [B, 2 * C]], [-D, -E])
    # Полуоси: от центра q(u) = 1 + q(x0), где q — квадратичная часть (в центре D·x0 + E·y0 = −2·q(x0)).
    q0 = A * x0 * x0 + B * x0 * y0 + C * y0 * y0
    k = 1 + q0
    theta = 0.5 * math.atan2(B, A - C)
    ct, st = math.cos(theta), math.sin(theta)
    a2 = A * ct * ct + B * ct * st + C * st * st
    c2 = A * st * st - B * ct * st + C * ct * ct
    ra, rb = math.sqrt(k / a2), math.sqrt(k / c2)
    major_deg = math.degrees(theta if ra >= rb else theta + math.pi / 2)
    return x0 + mx, y0 + my, max(ra, rb), min(ra, rb), major_deg


def hole_center(snap: Snapshot, seed, max_r=150.0, rays=720, rounds=6):
    """Центр пустого места: из точки — лучи до первой линии на земле, центр многоугольника видимости, и снова."""
    c = seed
    info = {}
    for _ in range(rounds):
        segs = snap.surface_segments(c, max_r)
        poly = []
        for i in range(rays):
            ang = 2 * math.pi * i / rays
            dx, dy = math.cos(ang), math.sin(ang)
            best = max_r
            for (ax, ay), (bx, by) in segs:
                ex, ey = bx - ax, by - ay
                den = dx * ey - dy * ex
                if abs(den) < 1e-12:
                    continue
                t = (ax * ey - ay * ex) / den
                u = (ax * dy - ay * dx) / den
                if 0 <= u <= 1 and 0 < t < best:
                    best = t
            poly.append((dx * best, dy * best))
        cx, cy, area = polygon_centroid(poly)
        rs = [math.hypot(x, y) for x, y in poly]
        info = {"area_m2": round(area), "ray_min_m": round(min(rs), 1), "ray_max_m": round(max(rs), 1),
                "open_rays": sum(1 for r in rs if r >= max_r - 1e-6)}
        nc = to_ll(cx, cy, c)
        if dist_m(c, nc) < 0.05:
            c = nc
            break
        c = nc
    return c, info


def norm180(deg: float) -> float:
    """Ось без направления: угол в (−90°, 90°]."""
    deg = (deg + 90.0) % 180.0 - 90.0
    return 90.0 if deg == -90.0 else deg


def axis_deg(p_south, p_north) -> float:
    """Азимут оси симметрии (по часовой от востока), перпендикулярной отрезку между двумя одинаковыми садами."""
    x, y = to_xy(p_north[0], p_north[1], p_south)
    # Ось перпендикулярна отрезку «сад — сад»: поворот на −90°.
    ang = math.degrees(math.atan2(-x, y))  # направление (y, −x)
    return round(-ang, 1)


DISTRICTS = ROOT / "web/civic/build3d/data/astana-districts.json"


def district_of(lat: float, lon: float) -> str | None:
    """Район по контурам OSM (data/civic/astana/geofence.json → web/civic/build3d/data/astana-districts.json)."""
    data = json.loads(DISTRICTS.read_text(encoding="utf-8"))
    for d in data["districts"]:
        rings = d["rings"]
        inside = False
        for ring in rings:
            for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
                if (y0 > lat) != (y1 > lat) and lon < x0 + (lat - y0) * (x1 - x0) / (y1 - y0):
                    inside = not inside
        if inside:
            return d["id"]
    return None


# Что показывать в поиске и подписи: название ru/kk, подпись на карте (label; если нет — название), вид здания
# (строка подсказки), другие написания для поиска,
# радиус «здание подложки — этот ориентир» (R01 basemap-style.js, выражение distance) и камера перелёта из поиска
# (наклон 52° — как кнопка «3D» оболочки, иначе автонаклон R01 доворачивает камеру второй раз).
INFO = {
    "baiterek": {
        "name": {"ru": "Байтерек", "kk": "Бәйтерек"},
        "kind": {"ru": "монумент", "kk": "монумент"},
        "aliases": ["Монумент Байтерек", "Baiterek", "Bayterek"],
        "radius_m": 30,
        "camera": {"zoom": 16.6, "pitch": 52, "bearing": -76},
    },
    "khan-shatyr": {
        "name": {"ru": "Хан Шатыр", "kk": "Хан Шатыр"},
        "kind": {"ru": "торговый центр", "kk": "сауда орталығы"},
        "aliases": ["ТРЦ Хан Шатыр", "Khan Shatyr"],
        "radius_m": 60,
        "camera": {"zoom": 15.9, "pitch": 52, "bearing": -76},
    },
    "akorda": {
        "name": {"ru": "Акорда", "kk": "Ақорда"},
        "kind": {"ru": "резиденция Президента", "kk": "Президент резиденциясы"},
        "aliases": ["Ак Орда", "Ақ Орда", "Akorda", "Ak Orda"],
        "radius_m": 50,
        "camera": {"zoom": 16.3, "pitch": 52, "bearing": -76},
    },
    "hazrat-sultan": {
        "name": {"ru": "Мечеть Хазрет Султан", "kk": "Әзірет Сұлтан мешіті"},
        "kind": {"ru": "мечеть", "kk": "мешіт"},
        "aliases": ["Хазрет Султан", "Хазрат Султан", "Әзірет Сұлтан", "Hazrat Sultan"],
        "radius_m": 60,
        "camera": {"zoom": 16.0, "pitch": 52, "bearing": -45},
    },
    "palace-peace": {
        "name": {"ru": "Дворец мира и согласия", "kk": "Бейбітшілік және келісім сарайы"},
        "kind": {"ru": "дворец (пирамида)", "kk": "сарай (пирамида)"},
        "aliases": ["Пирамида", "Palace of Peace and Reconciliation", "Pyramid"],
        "radius_m": 40,
        "camera": {"zoom": 16.5, "pitch": 52, "bearing": -76},
    },
    "nur-alem": {
        "name": {"ru": "Нур Алем", "kk": "Нұр Әлем"},
        # Подпись на карте — как была у R01 (basemap-style.js): «ЭКСПО» узнают чаще, чем «Нур Алем».
        "label": {"ru": "Нур Алем · ЭКСПО", "kk": "Нұр Әлем · ЭКСПО"},
        "kind": {"ru": "павильон ЭКСПО", "kk": "ЭКСПО павильоны"},
        "aliases": ["ЭКСПО", "Экспо", "EXPO", "Nur Alem"],
        "radius_m": 45,
        "camera": {"zoom": 16.1, "pitch": 52, "bearing": -20},
    },
}

# 3D-модели ориентиров на карте (web/civic/build3d/build3d-landmarks.js; владелец 19 окт: вернуть модели, удалённые по
# поправке П1, и показывать их на самой карте). Модели условные: высота и размеры — примерные, поворот — по данным OSM
# (Хан Шатыр — ось кольцевого проезда, Ақорда и пирамида — ось бульвара по садам Ақорды). mask_m — где модель стоит
# вместо здания подложки. У мечети Хазрет Султан модели нет — её показывает подложка.
MODELS = {
    "baiterek": {"model": "baiterek", "height_m": 105, "size_m": {"base_r": 16, "sphere_d": 22},
                 "mask_m": {"shape": "circle", "r": 26}},
    "khan-shatyr": {"model": "khan_shatyr", "height_m": 150, "size_m": {"base_a": 100, "base_b": 86},
                    "mask_m": {"shape": "ellipse", "a": 108, "b": 94}},
    # w — вдоль оси бульвара (x модели), d — поперёк: здание вытянуто поперёк оси, фасад — на восток.
    "akorda": {"model": "akorda", "height_m": 80, "size_m": {"length": 116, "depth": 46},
               "mask_m": {"shape": "rect", "w": 72, "d": 128}},
    "palace-peace": {"model": "pyramid", "height_m": 62, "size_m": {"base": 62},
                     "mask_m": {"shape": "rect", "w": 76, "d": 76}},
    "nur-alem": {"model": "nur_alem", "height_m": 100, "size_m": {"sphere_d": 80},
                 "mask_m": {"shape": "circle", "r": 46}},
}


def build(snap: Snapshot) -> dict:
    items = []
    rotation = {"baiterek": 0, "nur-alem": 0}  # поворот модели (азимут по часовой от востока), остальные — ниже

    # 1. Байтерек — центр круглой площади вокруг монумента (кольцо 258818019, r ≈ 42 м); проверка — внешнее
    #    кольцо 258818051 (r ≈ 84 м) и входы 2389116250 («main») / 2389116244 («exit») у самого основания.
    o = (51.1283, 71.4305)
    c, ring = ring_center(snap, 258818019, o)
    c2, _ = ring_center(snap, 258818051, o)
    entrances = [(snap.nodes[n]["lat"], snap.nodes[n]["lon"]) for n in (2389116250, 2389116244)]
    items.append({"id": "baiterek", "lat": c[0], "lon": c[1], "coords": {
        "method": "ring",
        "osm": [{"type": "way", "id": 258818019, "role": "кольцо площади вокруг монумента"},
                {"type": "way", "id": 258818051, "role": "внешнее кольцо (проверка)"},
                {"type": "node", "id": 2389116250, "role": "вход main у основания"},
                {"type": "node", "id": 2389116244, "role": "вход exit у основания"}],
        "ring_radius_m": ring["radius_m"], "ring_spread_m": ring["radius_spread_m"],
        "outer_ring_offset_m": round(dist_m(c, c2), 1),
        "entrances_offset_m": [round(dist_m(c, e), 1) for e in entrances],
    }})

    # 2. Хан Шатыр — центр эллипса кольцевого проезда вокруг шатра (way 164938029, 43 точки, охват ~330°).
    o = (51.13247, 71.40393)
    pts = [to_xy(lat, lon, o) for lat, lon in snap.way_points(164938029)]
    ex, ey, ra, rb, major = ellipse_fit(pts)
    c = to_ll(ex, ey, o)
    door = (snap.nodes[13294095201]["lat"], snap.nodes[13294095201]["lon"])
    rotation["khan-shatyr"] = round(norm180(-major), 1)  # ось шатра — по большой оси кольца
    items.append({"id": "khan-shatyr", "lat": c[0], "lon": c[1], "coords": {
        "method": "ellipse",
        "osm": [{"type": "way", "id": 164938029, "role": "кольцевой проезд вокруг шатра"},
                {"type": "node", "id": 13294095201, "role": "вход в шатёр (проверка радиуса)"}],
        "ring_semi_axes_m": [round(ra, 1), round(rb, 1)], "ring_axis_deg": round(norm180(-major), 1),
        # Вход (door, level 1) — на краю шатра: его расстояние до центра — радиус основания в ту сторону.
        "door_offset_m": round(dist_m(c, door), 1),
    }})

    # 3. Ақорда — пустое место между дорожками в центре симметричной композиции: два одинаковых сада
    #    (кольца 329669144 на севере и 329669208 на юге) задают ось бульвара, полукруглая площадь — восточный фасад.
    seed = (51.1256, 71.4464)
    c, hole = hole_center(snap, seed)
    gn, _ = ring_center(snap, 329669144, seed)
    gs, _ = ring_center(snap, 329669208, seed)
    axis = axis_deg(gs, gn)
    mid = ((gn[0] + gs[0]) / 2, (gn[1] + gs[1]) / 2)
    ax, ay = to_xy(c[0], c[1], mid)
    th = math.radians(-axis)
    off_axis = abs(-ax * math.sin(th) + ay * math.cos(th))
    rotation["akorda"] = rotation["palace-peace"] = axis  # пирамида стоит на той же оси бульвара
    items.append({"id": "akorda", "lat": c[0], "lon": c[1], "coords": {
        "method": "hole",
        "osm": [{"type": "way", "id": 329669144, "role": "северный сад (ось)"},
                {"type": "way", "id": 329669208, "role": "южный сад (ось)"}],
        "hole": hole, "axis_deg": axis, "offset_from_axis_m": round(off_axis, 1),
    }})

    # 4. Мечеть Хазрет Султан — центр большого восьмиугольного места внутри кольца дорожек (двор мечети).
    c, hole = hole_center(snap, (51.1254, 71.4718), max_r=170.0)
    items.append({"id": "hazrat-sultan", "lat": c[0], "lon": c[1], "coords": {
        "method": "hole",
        "osm": [{"type": "way", "id": 1373014142, "role": "дорожки вокруг двора мечети"}],
        "hole": hole,
    }})

    # 5. Дворец мира и согласия — узел OSM с именем здания (5009488810, вход подземного перехода в пирамиду);
    #    проверка — центр пустого квадрата между дорожками вокруг пирамиды.
    n = snap.nodes[5009488810]
    c = (n["lat"], n["lon"])
    hc, hole = hole_center(snap, c)
    items.append({"id": "palace-peace", "lat": c[0], "lon": c[1], "coords": {
        "method": "named_node",
        "osm": [{"type": "node", "id": 5009488810, "role": "узел с именем «Дворец мира и согласия»"}],
        "hole_center_offset_m": round(dist_m(c, hc), 1), "hole": hole,
    }})

    # 6. «Нұр Әлем» — центр концентрических колец ЭКСПО (проезды 455013941/2/3, дорожки 1461824179/80).
    o = (51.08925, 71.41624)
    rings = [455013941, 455013942, 455013943, 1461824179, 1461824180]
    centers, fits = [], []
    for wid in rings:
        cx, cy, r, rms = circle_fit([to_xy(lat, lon, o) for lat, lon in snap.way_points(wid)])
        centers.append((cx, cy))
        fits.append({"way": wid, "radius_m": round(r, 1), "rms_m": round(rms, 1)})
    cx = sum(p[0] for p in centers) / len(centers)
    cy = sum(p[1] for p in centers) / len(centers)
    spread = max(math.hypot(p[0] - cx, p[1] - cy) for p in centers)
    c = to_ll(cx, cy, o)
    items.append({"id": "nur-alem", "lat": c[0], "lon": c[1], "coords": {
        "method": "circles",
        "osm": [{"type": "way", "id": w, "role": "кольцо площади ЭКСПО"} for w in rings],
        "fits": fits, "centers_spread_m": round(spread, 1),
    }})

    out = []
    for it in items:
        info = INFO[it["id"]]
        lat, lon = round(it["lat"], 7), round(it["lon"], 7)
        it["coords"]["check"] = "LOCAL-13"
        entry = {
            "id": it["id"],
            "name": info["name"],
            "label": info.get("label", info["name"]),
            "kind": info["kind"],
            "aliases": info["aliases"],
            "lat": lat,
            "lon": lon,
            "district": district_of(lat, lon),
            "radius_m": info["radius_m"],
            "camera": info["camera"],
            "osm_object": {"type": "node", "id": 5009488810} if it["id"] == "palace-peace" else None,
        }
        model = MODELS.get(it["id"])
        if model:
            entry.update({"model": model["model"], "rotation_deg": rotation[it["id"]], "height_m": model["height_m"],
                          "size_m": model["size_m"], "mask_m": model["mask_m"], "conditional": True})
        entry["coords"] = it["coords"]
        out.append(entry)

    return {
        "schema": "birge-landmarks-v2",
        "purpose": "Ориентиры Астаны — один источник центров и названий ru/kk для подписей на карте (R01 basemap-style.js), "
                   "поиска (перелёт к зданию) и условных 3D-моделей на карте (build3d-landmarks.js, поле model).",
        "evidence_type": "real (OSM): координаты выведены из снимка пешеходной сети, контуры зданий — LOCAL-13; "
                         "модели, высоты и размеры — условные",
        "note": {
            "ru": "Условные модели: форма упрощена, размеры примерные. Это не точные копии зданий.",
            "kk": "Шартты модельдер: пішіні жеңілдетілген, өлшемдері шамамен алынған. Бұл ғимараттардың дәл көшірмесі емес.",
        },
        "generated_by": "data/civic/astana/landmarks/tools/derive_landmarks.py",
        "source": {
            "path": "data/civic/astana/osm-walking/overpass.json.gz",
            "sha256": snap.sha256,
            "osm_base": snap.osm_base,
            "license": "ODbL-1.0",
            "attribution": "© OpenStreetMap contributors",
        },
        "landmarks": out,
    }


def dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="не писать файлы, только сверить")
    args = parser.parse_args()
    text = dump(build(Snapshot(SNAPSHOT)))
    if args.check:
        bad = [p for p in (OUT, WEB_OUT) if not p.exists() or p.read_text(encoding="utf-8") != text]
        for p in bad:
            print(f"расходится с расчётом: {p.relative_to(ROOT)}")
        return 1 if bad else 0
    for p in (OUT, WEB_OUT):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"записано: {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
