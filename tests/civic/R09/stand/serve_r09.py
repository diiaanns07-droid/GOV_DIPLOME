"""Стенд R09: путь жителя v2 без остальных модулей (для браузерных проверок и показа владельцу).

  python tests/civic/R09/stand/serve_r09.py --port 8790 [--seed] [--no-ml] [--no-targets] [--db <файл>]
  -> http://127.0.0.1:8790/stand/

Что настоящее, а что заглушка:
  * /api/civic/v2/complaints...  — НАСТОЯЩИЙ модуль R09 (ui.civic_feedback.v2) на временной SQLite.
  * /api/civic/v2/targets        — FIXTURE вместо R12, но на РЕАЛЬНЫХ данных: объекты OSM из
                                   data/civic/astana/osm-objects (LOCAL-1: остановки, площадки, спортплощадки,
                                   парки, дворы, школы, детсады, мусорные площадки) и рёбра OSM-графа
                                   engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json.
  * /api/civic/v2/classify, /similar — FIXTURE вместо R04: ключевые слова и пересечение слов.
                                   --no-ml: оба отвечают 503 (проверка «форма работает без ML»).
  * Карта — MapLibre из web/vendor, без тайлов (в облаке их нет): фон + реальные улицы из того же графа.
  * --seed — демо-записи (demo=true, «Пример») на реальной остановке (7 человек) и реальных участках улиц.
Ничего не пишет в репозиторий: БД во временной папке, если не указан --db.
"""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from ui.civic_feedback import text as textutil  # noqa: E402
from ui.civic_feedback.v2 import ComplaintStore, ComplaintsV2Service  # noqa: E402
from ui.civic_feedback.v2 import categories  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from osm_objects import OsmObjects  # noqa: E402

GRAPH = ROOT / "engine" / "civic_scenarios" / "graphs" / "osm-astana-walking-20260506.graph.json"
STAND_BBOX = (71.395, 51.075, 71.465, 51.125)   # левый берег, ЭКСПО и окрестности
WEB = ROOT / "web"
STAND = Path(__file__).resolve().parent
STATIC = {
    "/vendor/maplibre-gl.js": WEB / "vendor" / "maplibre-gl.js",
    "/vendor/maplibre-gl.css": WEB / "vendor" / "maplibre-gl.css",
    "/stand/": STAND / "index.html",
}
for name in ("complaint.js", "complaint.css", "complaint-strings.js", "categories_v2.js", "kit-fallback.css"):
    STATIC["/civic/feedback/" + name] = WEB / "civic" / "feedback" / name
for name in ("tokens.css", "components.css", "icons.svg"):  # ui-kit R11, если уже есть в дереве
    STATIC["/civic/ui-kit/" + name] = WEB / "civic" / "ui-kit" / name
for name in ("i18n.js", "ru.json", "kk.json"):
    STATIC["/civic/i18n/" + name] = WEB / "civic" / "i18n" / name

KEYWORDS = {  # FIXTURE-классификатор: только для стенда, не модель
    "snow_ice": ("снег", "налед", "гололед", "гололёд", "скольз", "сосульк", "қар", "тайғақ", "мұз"),
    "roads": ("яма", "асфальт", "дорог", "разметк", "шұңқыр", "жол"),
    "sidewalks": ("тротуар", "пандус", "бордюр"),
    "transport": ("остановк", "автобус", "павильон", "аялдама"),
    "lighting": ("фонар", "темно", "освещ", "шам", "жарық", "қараңғы"),
    "yards": ("площадк", "двор", "скамейк", "алаң", "аула"),
    "waste": ("мусор", "бак", "свалк", "қоқыс"),
    "utilities": ("отоплен", "вода", "воды", "канализ", "жылу", "су "),
    "smell_air": ("запах", "вонь", "дым", "пыль", "иіс", "түтін"),
    "noise_safety": ("шум", "опасн", "переход", "шу", "қауіп"),
    "parking": ("парков", "машин", "газон", "тұрақ", "көлік"),
}


def meters(lon1, lat1, lon2, lat2):
    kx = 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot((lon2 - lon1) * kx, (lat2 - lat1) * 111_320)


def point_segment_m(p, a, b):
    kx = 111_320 * math.cos(math.radians(p[1]))
    ax, ay = (a[0] - p[0]) * kx, (a[1] - p[1]) * 111_320
    bx, by = (b[0] - p[0]) * kx, (b[1] - p[1]) * 111_320
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / length2))
    return math.hypot(ax + t * dx, ay + t * dy)


class Stand:
    def __init__(self, db_path, *, ml=True, targets=True):
        self.store = ComplaintStore(db_path)
        self.api = ComplaintsV2Service(self.store)
        self.ml, self.targets_on = ml, targets
        self.lock = threading.Lock()
        graph = json.loads(GRAPH.read_text(encoding="utf-8"))
        lon0, lat0, lon1, lat1 = STAND_BBOX
        self.edges = [e for e in graph["edges"] if e.get("geometry") and any(
            lon0 <= x <= lon1 and lat0 <= y <= lat1 for x, y in e["geometry"])]
        self.objects = OsmObjects(STAND_BBOX)
        self.streets = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": e["geometry"]},
             "properties": {"named": bool(e.get("name"))}} for e in self.edges]}

    # ---------------------------------------------------------- FIXTURE R12
    def targets(self, lon, lat):
        """До 3 кандидатов: реальные объекты OSM (остановки, площадки, дворы…) и участки улиц, ближайшие первыми."""
        scored = []
        for score, distance, item in self.objects.nearby(lon, lat):
            scored.append((score, {"target": dict(item["target"]), "distance_m": round(distance, 1),
                                   "geometry": item["geometry"],
                                   "source": "FIXTURE R12: реальный объект OSM (data/civic/astana/osm-objects)"}))
        found = []
        for edge in self.edges:
            geom = edge["geometry"]
            if not any(abs(x - lon) < 0.003 and abs(y - lat) < 0.002 for x, y in geom):
                continue
            d = min(point_segment_m((lon, lat), geom[i], geom[i + 1]) for i in range(len(geom) - 1))
            if d <= 80:
                found.append((d, edge))
        found.sort(key=lambda item: item[0])
        names = set()
        for d, edge in found:
            name = edge.get("name") or ""
            key = name or "<без названия>"   # безымянные рёбра — один вариант, иначе две одинаковые кнопки
            if key in names:
                continue
            names.add(key)
            label_ru = f"Участок: {name}" if name else "Участок улицы"
            label_kk = f"Көше бөлігі: {name}" if name else "Көше бөлігі"
            scored.append((d, {"target": {"kind": "segment", "id": edge["id"], "label_ru": label_ru, "label_kk": label_kk},
                               "distance_m": round(d, 1),
                               "geometry": {"type": "LineString", "coordinates": edge["geometry"]},
                               "source": "FIXTURE R12: ребро реального OSM-графа"}))
            if len(names) == 2:
                break
        scored.sort(key=lambda item: item[0])
        return [candidate for _, candidate in scored[:3]]

    # ---------------------------------------------------------- FIXTURE R04
    def classify(self, text):
        low = text.lower()
        scores = {cat: sum(1 for k in words if k in low) for cat, words in KEYWORDS.items()}
        best = max(scores, key=scores.get)
        if scores[best] == 0:
            return {"category": "other", "score": 0.3, "needs_review": True, "model_version": "FIXTURE-keywords",
                    "top3": [{"category": "other", "score": 0.3}]}
        return {"category": best, "score": 0.8, "needs_review": False, "model_version": "FIXTURE-keywords",
                "top3": [{"category": best, "score": 0.8}]}

    def similar(self, text, point, days):
        from datetime import timedelta
        since = self.store._now() - timedelta(days=days or 14)
        matches = []
        for record in self.store.list(since=since, status=("new", "accepted", "in_progress")):
            score = textutil.similarity(text, record["text"])
            if point and meters(point[0], point[1], *record["point"]) > 300:
                continue
            if score >= 0.2:
                matches.append({"complaint_id": record["id"], "score": round(min(1.0, score + 0.4), 3),
                                "target": record["target"], "metoo": record["metoo"]})
        matches.sort(key=lambda m: -m["score"])
        return {"matches": matches[:3], "source": "FIXTURE"}

    def seed(self):
        """Демо-записи: «горячая» реальная остановка (7 человек) и пара жалоб на реальных участках улиц."""
        named = [e for e in self.edges if e.get("name")]
        if not named:
            return
        def mid(edge):
            # Середина отрезка, а не вершина: вершина может быть общей с соседним ребром той же улицы.
            g = edge["geometry"]
            i = max(0, (len(g) - 1) // 2)
            return [round((g[i][0] + g[i + 1][0]) / 2, 7), round((g[i][1] + g[i + 1][1]) / 2, 7)]
        # «Горячая» цель — реальная остановка с названием (сценарий демо: «Это остановка «…»?»).
        # Берём остановку, рядом с которой (60 м) нет другой остановки, чтобы выбор был однозначным.
        stops = [i for i in self.objects.items if i["kind"] == "stop" and "«" in i["target"]["label_ru"]]
        def lonely(stop):
            x, y = stop["geometry"]["coordinates"]
            return all(o is stop or math.hypot((o["geometry"]["coordinates"][0] - x) * 70_000,
                                               (o["geometry"]["coordinates"][1] - y) * 111_320) > 60 for o in stops)
        cx, cy = (STAND_BBOX[0] + STAND_BBOX[2]) / 2, (STAND_BBOX[1] + STAND_BBOX[3]) / 2
        by_center = sorted(stops, key=lambda s: meters(cx, cy, *s["geometry"]["coordinates"]))
        hot_stop = next(s for s in by_center if lonely(s))
        point = hot_stop["geometry"]["coordinates"]
        target = dict(hot_stop["target"])
        rec, _ = self.store.create({"text": "Павильон остановки сломан, нет крыши", "category": "transport",
                                    "point": point, "target": target}, "seed-device-000000001", demo=True)
        for i in range(6):
            self.store.metoo(rec["id"], f"seed-device-metoo-{i:06d}")
        for i, (edge, cat, txt) in enumerate([(named[len(named) // 2], "roads", "Яма на дороге"),
                                               (named[2 * len(named) // 3], "lighting", "Не горят фонари")]):
            self.store.create({"text": txt, "category": cat, "point": mid(edge),
                               "target": {"kind": "segment", "id": edge["id"], "label_ru": f"Участок: {edge['name']}"}},
                              f"seed-device-other-{i:04d}", demo=True)
        self.hot = {"point": point, "target": target, "complaint_id": rec["id"]}


class Handler(BaseHTTPRequestHandler):
    stand: Stand = None

    def log_message(self, *args):
        pass

    def _send(self, status, payload, ctype="application/json; charset=utf-8", headers=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _context(self):
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        return {"headers": dict(self.headers.items()), "host_allowed": True,
                "is_same_origin": None if origin is None else origin.endswith("//" + host)}

    def _api(self, method):
        parts = urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        path, query = parts.path, parse_qs(parts.query)
        stand = self.stand
        if path == "/api/civic/v2/targets":
            if not stand.targets_on:
                return self._send(503, {"ok": False, "error": {"code": "module_unavailable"}})
            try:
                lon, lat = float(query["lon"][0]), float(query["lat"][0])
            except (KeyError, ValueError):
                return self._send(422, {"ok": False, "error": {"code": "invalid"}})
            return self._send(200, {"ok": True, "data": {"candidates": stand.targets(lon, lat)}})
        if path in ("/api/civic/v2/classify", "/api/civic/v2/similar"):
            if not stand.ml:
                return self._send(503, {"ok": False, "error": {"code": "module_unavailable"}})
            data = json.loads(body or b"{}")
            if path.endswith("classify"):
                return self._send(200, {"ok": True, "data": stand.classify(data.get("text", ""))})
            return self._send(200, {"ok": True, "data": stand.similar(data.get("text", ""), data.get("point"),
                                                                     data.get("days"))})
        if path == "/stand/streets.geojson":
            return self._send(200, stand.streets, "application/geo+json")
        if path == "/stand/objects.geojson":
            return self._send(200, stand.objects.geojson(), "application/geo+json")
        if path == "/stand/info":
            return self._send(200, {"hot": getattr(stand, "hot", None), "ml": stand.ml, "targets": stand.targets_on})
        reply = stand.api.handle(method, self.path, None, body, None, self._context())
        if reply is None:
            return self._send(404, {"ok": False, "error": {"code": "not_found"}})
        return self._send(reply["status"], reply["body"], headers={k: v for k, v in reply["headers"].items()
                                                                     if k.lower() != "cache-control"})

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith("/api/") or path.endswith(".geojson") or path == "/stand/info":
            return self._api("GET")
        if path == "/stand":
            self.send_response(302)
            self.send_header("Location", "/stand/")
            self.end_headers()
            return None
        file = STATIC.get(path)
        if file is None or not file.exists():
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(str(file))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        return self._send(200, file.read_bytes(), ctype)

    def do_POST(self):
        return self._api("POST")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--db")
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--no-ml", action="store_true")
    parser.add_argument("--no-targets", action="store_true")
    args = parser.parse_args(argv)
    db = args.db or str(Path(tempfile.mkdtemp(prefix="r09-stand-")) / "complaints.sqlite3")
    Handler.stand = Stand(db, ml=not args.no_ml, targets=not args.no_targets)
    if args.seed:
        Handler.stand.seed()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"R09 stand: http://127.0.0.1:{args.port}/stand/  db={db}  ml={not args.no_ml} "
          f"targets={not args.no_targets} categories={len(categories.ids())}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
