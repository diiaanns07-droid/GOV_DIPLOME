"""R11 · подложка для макетов: оси улиц OSM (граф пешеходной сети) во фрагменте у пр. Туран и ул. Орынбор.

    python3 tests/civic/R11/tools/make_proto_streets.py   -> web/civic/ui-kit/prototypes/proto-streets.js

Граф только читается: engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json (© OpenStreetMap
contributors, ODbL). Координаты переводятся в «единицы макета» (ширина окна = 1000), чтобы SVG был лёгким;
обратное преобразование в градусы — в proto.js (BBOX и SCALE ниже попадают в файл).
Участки улиц для целей макета собираются из тех же рёбер — линия идёт строго по форме улицы.
"""
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GRAPH = ROOT / "engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json"
OUT = ROOT / "web/civic/ui-kit/prototypes/proto-streets.js"
BBOX = [71.398, 51.100, 71.424, 51.116]  # lon_min, lat_min, lon_max, lat_max (~1,8 × 1,8 км)
WIDTH = 1000.0
LAT0 = (BBOX[1] + BBOX[3]) / 2
KX = WIDTH / (BBOX[2] - BBOX[0])
KY = KX / math.cos(math.radians(LAT0))  # единицы на градус широты: один масштаб по осям в метрах
HEIGHT = (BBOX[3] - BBOX[1]) * KY
M_PER_UNIT = (BBOX[2] - BBOX[0]) * 111320 * math.cos(math.radians(LAT0)) / WIDTH


def xy(c):
    return (round((c[0] - BBOX[0]) * KX, 1), round((BBOX[3] - c[1]) * KY, 1))


def inside(geom):
    return all(BBOX[0] <= c[0] <= BBOX[2] and BBOX[1] <= c[1] <= BBOX[3] for c in geom)


def path(lines):
    out = []
    for line in lines:
        pts = [xy(c) for c in line]
        out.append("M" + " L".join(f"{x:g} {y:g}" for x, y in pts))
    return "".join(out)


def main():
    g = json.loads(GRAPH.read_text("utf-8"))
    named, paths = defaultdict(list), []
    edges_by_name = defaultdict(list)
    for e in g["edges"]:
        geom = e["geometry"]
        if not inside(geom):
            continue
        name = e.get("name")
        if name:
            named[name].append(geom)
            edges_by_name[name].append(e)
        else:
            paths.append(geom)

    def segment(name, pick):
        """Участок улицы: рёбра с этим именем, у которых середина удовлетворяет условию pick(lon, lat)."""
        chosen = []
        for e in edges_by_name[name]:
            geom = e["geometry"]
            mid = geom[len(geom) // 2]
            if pick(mid[0], mid[1]):
                chosen.append(e)
        return {"edges": [e["id"] for e in chosen], "d": path([e["geometry"] for e in chosen]),
                "length_m": round(sum(e.get("length_m", 0) for e in chosen))}

    def node_on(name, lon, lat):
        """Ближайшая к (lon, lat) вершина улицы name — точка «остановки» стоит на оси улицы."""
        best = None
        for e in edges_by_name[name]:
            for c in e["geometry"]:
                d = (c[0] - lon) ** 2 + ((c[1] - lat) * 1.6) ** 2
                if best is None or d < best[0]:
                    best = (d, c)
        return {"lonlat": [round(best[1][0], 6), round(best[1][1], 6)], "xy": list(xy(best[1]))}

    def label_line(lines):
        """Самая длинная цепочка рёбер улицы — по ней в макете идёт подпись (textPath)."""
        def length(line):
            return sum(math.dist(xy(a), xy(b)) for a, b in zip(line, line[1:]))
        # склеиваем рёбра, у которых конец одного = начало другого
        chains = []
        for line in lines:
            for ch in chains:
                if ch[-1] == line[0]:
                    ch.extend(line[1:])
                    break
            else:
                chains.append(list(line))
        best = max(chains, key=length)
        if xy(best[0])[0] > xy(best[-1])[0]:
            best = best[::-1]  # подпись читается слева направо
        return path([best]), round(length(best))

    streets = []
    for n, lines in sorted(named.items(), key=lambda kv: -len(kv[1])):
        lp, ll = label_line(lines)
        streets.append({"name": n, "d": path(lines), "n": len(lines), "label_d": lp, "label_len": ll})
    data = {
        "source": "OSM, пешеходная сеть Астаны на 2026-05-06 (" + g["id"] + "), © OpenStreetMap contributors, ODbL",
        "bbox": BBOX, "size": [WIDTH, round(HEIGHT, 1)], "m_per_unit": round(M_PER_UNIT, 3),
        "streets": streets,
        "paths": path(paths),
        "segments": {
            "bukhar": segment("улица Бухар Жырау", lambda lon, lat: 71.4110 <= lon <= 71.4195),
            "orynbor": segment("улица Орынбор", lambda lon, lat: 71.4040 <= lon <= 71.4120),
            "kabanbay": segment("проспект Кабанбай Батыра", lambda lon, lat: 51.1020 <= lat <= 51.1080),
        },
        "points": {
            "stop_bukhar": node_on("улица Бухар жырау", 71.4045, 51.1033),
            "stop_orynbor": node_on("улица Орынбор", 71.4165, 51.1075),
            "stop_kabanbay": node_on("проспект Кабанбай Батыра", 71.4045, 51.1100),
            "stop_sauran": node_on("улица Сауран", 71.4160, 51.1135),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("/* СГЕНЕРИРОВАНО: python3 tests/civic/R11/tools/make_proto_streets.py — не править руками.\n"
                   " * Оси улиц OSM для макетов R11 (© OpenStreetMap contributors, ODbL). */\n"
                   "window.BirgeProtoStreets = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n", "utf-8")
    print(OUT.relative_to(ROOT), round(OUT.stat().st_size / 1024), "КБ; улиц:", len(streets),
          {k: (len(v["edges"]), v["length_m"]) for k, v in data["segments"].items()}, data["points"])


if __name__ == "__main__":
    main()
