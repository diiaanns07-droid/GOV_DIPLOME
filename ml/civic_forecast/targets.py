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
    qualify_duplicates(out)
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


# Одинаковые подписи соседних мест («Двор рядом: остановка «X»» у двух дворов) в списке прогноза читаются как одна строка
# (R03, круг 15: в 7 из 14 списков «первые 5» были повторы). Безымянные места с повторяющейся подписью получают ref —
# привязку к ближайшей названной остановке (точка OSM): сторона света и расстояние; нет остановки ближе 800 м — к ближайшему
# названному двору (жилой комплекс, его центр); нет и его — то же в радиусе 1,5 км. К улице так не привязываем: от улицы
# в данных одна точка (середина самой длинной линии), а не сама линия, — «в 300 м к югу от улицы» было бы неправдой.
REF_RADII_M = (LANDMARK_RADIUS_M, 1500.0)
_DIRS = ("n", "ne", "e", "se", "s", "sw", "w", "nw")
DIR_RU = {"n": "к северу", "ne": "к северо-востоку", "e": "к востоку", "se": "к юго-востоку", "s": "к югу",
          "sw": "к юго-западу", "w": "к западу", "nw": "к северо-западу"}
DIR_KK = {"n": "солтүстікке қарай", "ne": "солтүстік-шығысқа қарай", "e": "шығысқа қарай",
          "se": "оңтүстік-шығысқа қарай", "s": "оңтүстікке қарай", "sw": "оңтүстік-батысқа қарай",
          "w": "батысқа қарай", "nw": "солтүстік-батысқа қарай"}


def _direction(origin, point) -> str:
    """Сторона света точки point относительно origin (8 румбов, 0° — север)."""
    k = math.cos(math.radians((origin[1] + point[1]) / 2))
    angle = math.degrees(math.atan2((point[0] - origin[0]) * k, point[1] - origin[1])) % 360
    return _DIRS[int((angle + 22.5) // 45) % 8]


def _distance_text(m: int) -> str:
    """«380 м», «1,2 км» (запятая — и в РУС, и в ҚАЗ)."""
    return f"{m} м" if m < 1000 else f"{m / 1000:.1f}".replace(".", ",").replace(",0", "") + " км"


def qualify_duplicates(items) -> int:
    """У безымянных мест с одинаковой подписью (ru или kk) — ref к ближайшей названной остановке. Возвращает число ref."""
    for item in items:
        item.pop("ref", None)
    unnamed = [i for i in items if not i.get("name_ru") and not i.get("name_kk") and i.get("near")]
    need = set()
    for lang in ("ru", "kk"):
        groups = {}
        for item in unnamed:
            groups.setdefault(label(item, lang), []).append(item["id"])
        need.update(i for ids in groups.values() if len(ids) > 1 for i in ids)
    cell = 0.01  # ~0,7 × 1,1 км; ищем в соседних клетках ±3 — радиус 1,5 км покрыт
    grids = {}
    for kind in ("bus_stop", "yard"):
        grid = grids[kind] = {}
        for ref in items:
            if ref["kind"] == kind and ref.get("name_ru"):
                grid.setdefault((int(ref["point"][0] / cell), int(ref["point"][1] / cell)), []).append(ref)
    count = 0
    for item in unnamed:
        if item["id"] not in need:
            continue
        gx, gy = int(item["point"][0] / cell), int(item["point"][1] / cell)
        for radius, kind in ((r, k) for r in REF_RADII_M for k in ("bus_stop", "yard")):
            best, best_d = None, radius
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    for ref in grids[kind].get((gx + dx, gy + dy), ()):
                        d = _metres(item["point"], ref["point"])
                        if ref["id"] != item["id"] and d < best_d:
                            best, best_d = ref, d
            if best is not None:
                step = 10 if best_d < 1000 else 100
                item["ref"] = {"kind": kind, "name_ru": best["name_ru"], "name_kk": best.get("name_kk"),
                               "dir": _direction(best["point"], item["point"]),
                               "m": max(10, int(round(best_d / step)) * step)}
                count += 1
                break
    return count


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
    low = name_ru[:1].lower() + name_ru[1:]  # «Улица Касым Кайсенов» — тип с большой буквы
    for ru_type, kk_type in _KK_STREET_TYPES:
        if low.startswith(ru_type):
            return f"{name_ru[len(ru_type):]} {kk_type}"
        if name_ru.endswith(" " + ru_type.strip()):
            return f"{name_ru[: -len(ru_type)]} {kk_type}"
    return name_ru


# Обратное правило: у улицы в OSM только казахское имя — в РУС тип по-русски перед названием, имя собственное как есть,
# без склонения: «Иван Панфилов көшесі» → «улица Иван Панфилов» (раунд 15: 69 русских подписей были с «көшесі»).
_RU_STREET_TYPES = (("тұйық көшесі", "переулок"), ("көшесі", "улица"), ("даңғылы", "проспект"), ("тас жолы", "шоссе"),
                    ("тасжолы", "шоссе"), ("бульвары", "бульвар"), ("алаңы", "площадь"))


def ru_street(name: str | None) -> str | None:
    """Русская подпись улицы с одним казахским именем: тип по-русски, имя собственное как есть; не улица — без изменений."""
    if not name:
        return name
    for kk_type, ru_type in _RU_STREET_TYPES:
        if name.endswith(" " + kk_type):
            return f"{ru_type} {name[: -len(kk_type) - 1]}"
    return name


# Участок улицы — без повтора типа: «Участок улицы Анет Баба», «Әнет Баба көшесінің бөлігі» (было «Участок улицы
# «улица Анет Баба»» и «Көше бөлігі «Әнет Баба көшесі»»). Имя собственное не склоняем — только слово типа.
_RU_TYPE_GENITIVE = (("улица ", "улицы "), ("проспект ", "проспекта "), ("переулок ", "переулка "), ("шоссе ", "шоссе "),
                     ("бульвар ", "бульвара "), ("площадь ", "площади "))
_KK_TYPE_GENITIVE = (("тұйық көшесі", "тұйық көшесінің"), ("көшесі", "көшесінің"), ("даңғылы", "даңғылының"),
                     ("тас жолы", "тас жолының"), ("бульвары", "бульварының"), ("алаңы", "алаңының"))


def _segment_label(name: str, lang: str) -> str:
    if lang == "kk":
        for kk_type, genitive in _KK_TYPE_GENITIVE:
            if name.endswith(" " + kk_type):
                return f"{name[: -len(kk_type)]}{genitive} бөлігі"
        return f"Көше бөлігі: {name}"
    low = name[:1].lower() + name[1:]
    for ru_type, genitive in _RU_TYPE_GENITIVE:
        if low.startswith(ru_type):
            return f"Участок {genitive}{name[len(ru_type):]}"
    return f"Участок: {name}"


def label(target: dict, lang: str) -> str:
    """Подпись для интерфейса: «Остановка «Нура»», «Двор: ЖК Инжу Арена», «Участок ул. …»."""
    # Имя собственное годится в обоих языках: у двора только с name:kk («Ақ-Тау») русская подпись — «Двор «Ақ-Тау»», а не
    # «Двор рядом: остановка …» (раунд 15: ru и kk подписи одной территории расходились).
    if lang == "kk":
        name = target.get("name_kk") or kk_street(target.get("name_ru"))
    else:
        name = ru_street(target.get("name_ru") or target.get("name_kk"))
    kind = target["kind"]
    if lang == "kk":
        base = {"yard": "Аула", "bus_stop": "Аялдама", "playground": "Балалар алаңы", "park": "Саябақ",
                "waste": "Қоқыс алаңы", "segment": "Көше бөлігі"}[kind]
    else:
        base = {"yard": "Двор", "bus_stop": "Остановка", "playground": "Детская площадка", "park": "Парк",
                "waste": "Площадка для мусора", "segment": "Участок улицы"}[kind]
    if name:
        return _segment_label(name, lang) if kind == "segment" else f"{base} «{name}»"
    ref = target.get("ref")
    if ref:  # повтор подписи у соседних мест — привязка к остановке или названному двору (qualify_duplicates)
        yard = ref.get("kind") == "yard"
        if lang == "kk":
            what = ref.get("name_kk") or kk_street(ref["name_ru"])
            far = _distance_text(ref["m"])
            return f"«{what}» {'ауласынан' if yard else 'аялдамасынан'} {DIR_KK[ref['dir']]} {far} жердегі {base.lower()}"
        what = ref.get("name_ru") if yard else ru_street(ref["name_ru"])
        return f"{base} в {_distance_text(ref['m'])} {DIR_RU[ref['dir']]} от {'двора' if yard else 'остановки'} «{what}»"
    near = target.get("near")
    if near:
        near_name = (near.get("name_kk") or kk_street(near["name_ru"])) if lang == "kk" else ru_street(near["name_ru"])
        # По-казахски ориентир стоит перед словом: «А-359 көшесі жанындағы аула» («двор у улицы А-359»), а не
        # «Аула · жанында А-359 көшесі» (порядок слов русской подписи).
        if near["kind"] == "bus_stop":
            return f"«{near_name}» аялдамасы жанындағы {base.lower()}" if lang == "kk" else f"{base} рядом: остановка «{near_name}»"
        return f"{near_name} жанындағы {base.lower()}" if lang == "kk" else f"{base} рядом: {near_name}"
    return base
