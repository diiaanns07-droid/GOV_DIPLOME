"""Где находится цель жалобы и как её назвать (CONTRACT §4).

Тепловая карта сама цели не выбирает (это R12, engine/civic_geo) — она только достаёт форму
и подпись цели по её id. Источники по порядку:
  1. реестр готовых целей (fixtures/targets_demo.json и данные R12 data/civic/astana/geo/*.json);
     для id osm-…/yard-… свой слой OSM (2а) главнее файлов R12: у R12 голое имя («Хан Шатыр») и name_kk = null,
     а слой R07 подписывает тип объекта на двух языках (I-01 R01); выверенные подписи демо-фикстуры — главнее всех;
  2. модуль R12 engine.civic_geo, если в нём есть функция target_geometry(target);
  2а. реальные объекты OSM (LOCAL-1, data/civic/astana/osm-objects/): osm-node-…, osm-way-…, yard-…;
  3. участок улицы osm-w<way>-<n> — настоящая форма ребра из пешеходного графа OSM;
  4. ячейка cell-<ix>-<iy> — квадрат ~150 м по формуле из geo.py;
  5. иначе — «примерное место»: круг 60 м вокруг точки жалобы (никаких уверенных линий).
"""
from __future__ import annotations

import json
import math
import re
import threading
from pathlib import Path

from . import geo, osm_objects
from .config import GRAPH_PATH, ROOT

FIXTURE_TARGETS = Path(__file__).resolve().parent / "fixtures" / "targets_demo.json"
STREET_LABELS = Path(__file__).resolve().parent / "fixtures" / "osm_street_labels.json"
R12_GEO_DIR = ROOT / "data" / "civic" / "astana" / "geo"
APPROX_RADIUS_M = 60.0
_EDGE_RE = re.compile(r"^osm-w(\d+)-(\d+)$")
_OSM_RE = re.compile(r"^(osm-(node|way|relation)-\d+|yard-r?\d+)$")
_STREET_CELL = 0.003   # ячейка индекса улиц, градусы (~200–330 м)

# Подпись безымянного объекта по ближайшей улице: (ru — после «у ул. …», kk — перед «маңындағы»).
_NEAR_WORDS = {
    "bus_stop": ("Остановка", "жанындағы аялдама"),
    "playground": ("Детская площадка", "маңындағы балалар алаңы"),
    "pitch": ("Спортплощадка", "маңындағы спорт алаңы"),
    "yard": ("Двор", "маңындағы аула"),
    "waste_disposal": ("Контейнерная площадка", "маңындағы қоқыс алаңы"),
    "recycling": ("Пункт приёма вторсырья", "маңындағы қайта өңдеу пункті"),
    "street_lamp": ("Фонарь", "маңындағы көше шамы"),
    "park": ("Парк", "маңындағы саябақ"),
    "garden": ("Сквер", "маңындағы гүлзар"),
}


def near_street_labels(subtype: str, street_ru: str | None, street_kk: str | None = None) -> tuple[str, str] | None:
    """«Остановка у ул. Сыганак» / «Сыганак көшесі жанындағы аялдама». Без улицы — None."""
    if not street_ru or subtype not in _NEAR_WORDS:
        return None
    word_ru, tail_kk = _NEAR_WORDS[subtype]
    short = short_street_ru(street_ru)
    # «у ул. …» читается правильно только с сокращённым типом улицы; без типа — через запятую.
    ru = f"{word_ru} у {short}" if short != street_ru else f"{word_ru}, {street_ru}"
    return ru, f"{street_kk or kk_street_from_ru(street_ru)} {tail_kk}"

APPROX_LABELS = ("Примерное место", "Шамамен көрсетілген орын")
_APPROX_KK_SHORT = "Шамамен орны"
# Источники формы без собственного названия: только здесь подпись из записи жалобы допустима (R15-S11).
RECORD_LABEL_SOURCES = frozenset({"cell-grid", "cell-grid-r09"})

KIND_WORD = {
    "object": ("Объект", "Нысан"),
    "segment": ("Участок улицы", "Көше бөлігі"),
    "area": ("Двор или квартал", "Аула немесе орам"),
    "district": ("Район", "Аудан"),
}


def short_street_ru(name: str) -> str:
    """«улица Сыганак» → «ул. Сыганак», «проспект Туран» → «пр. Туран» (для подписей)."""
    for full, short in (("улица ", "ул. "), ("проспект ", "пр. "), ("переулок ", "пер. "), ("шоссе ", "ш. "), ("бульвар ", "бул. ")):
        if name.startswith(full):
            return short + name[len(full):]
    return name


# Русский тип улицы → казахский (ставится ПОСЛЕ названия): «улица Сыганак» → «Сыганак көшесі».
_KK_TYPES = (("улица ", "көшесі"), ("проспект ", "даңғылы"), ("переулок ", "тұйық көшесі"),
             ("шоссе ", "тас жолы"), ("бульвар ", "бульвары"), ("площадь ", "алаңы"))


def kk_street_from_ru(name_ru: str | None) -> str | None:
    """Казахская подпись улицы, когда в OSM нет name:kk: тип по-казахски, имя собственное как есть."""
    if not name_ru:
        return None
    for ru_type, kk_type in _KK_TYPES:
        if name_ru.startswith(ru_type):
            return f"{name_ru[len(ru_type):]} {kk_type}"
        if name_ru.endswith(" " + ru_type.strip()):
            return f"{name_ru[: -len(ru_type)]} {kk_type}"
    return name_ru


# Родительный падеж для типов улиц: окончание у слова-типа всегда одно и то же, имя собственное не трогаем.
_KK_GENITIVE = (("көшесі", "нің"), ("даңғылы", "ның"), ("жолы", "ның"), ("бульвары", "ның"), ("алаңы", "ның"))


def kk_genitive(name_kk: str | None) -> str | None:
    """«Сығанақ көшесі» → «Сығанақ көшесінің». Неизвестное окончание → None (тогда подпись через двоеточие)."""
    if not name_kk:
        return None
    for ending, suffix in _KK_GENITIVE:
        if name_kk.endswith(ending):
            return name_kk + suffix
    return None


def segment_labels(street_ru: str | None, street_kk: str | None, from_ru=None, to_ru=None, from_kk=None, to_kk=None) -> tuple[str, str]:
    """Подпись участка: «Участок ул. Сыганак от ул. X до ул. Y».

    По-казахски окончание зависит от последнего звука слова. Склоняем только слово-тип улицы
    («көшесі» → «көшесінің»), у которого окончание известно заранее; имена собственные не трогаем:
    «Сығанақ көшесінің бөлігі», «Сығанақ көшесінің Тұран даңғылы – Достық көшесі аралығы».
    """
    if not street_ru:
        return "Участок улицы", "Көше бөлігі"
    short = short_street_ru(street_ru)
    # «Участок ул. Сыганак», но «Участок: Объездная Астаны» — когда в названии нет типа улицы.
    ru = ("Участок " if short != street_ru else "Участок: ") + short
    if from_ru and to_ru and from_ru != to_ru:
        ru += f" от {short_street_ru(from_ru)} до {short_street_ru(to_ru)}"
    kk_street = street_kk or kk_street_from_ru(street_ru)
    from_kk = from_kk or kk_street_from_ru(from_ru)
    to_kk = to_kk or kk_street_from_ru(to_ru)
    gen = kk_genitive(kk_street)
    kk = f"{gen} бөлігі" if gen else f"{kk_street}: көше бөлігі"
    if from_kk and to_kk and from_kk != to_kk:
        kk = f"{gen} {from_kk} – {to_kk} аралығы" if gen else f"{kk_street}: {from_kk} – {to_kk} аралығы"
    return ru, kk


class TargetResolver:
    """Ищет форму и подпись цели. Потокобезопасен; граф грузится один раз и только при нужде."""

    def __init__(self, registry: dict | None = None, *, graph_path: Path | None = GRAPH_PATH, use_r12: bool = True,
                 use_osm_objects: bool = True):
        self._registry: dict = {}
        self._lock = threading.Lock()
        self._graph_path = graph_path
        self._edges: dict | None = None
        self._streets: dict | None = None
        self._r12 = None
        self._use_osm_objects = use_osm_objects
        self._cache: dict = {}
        self.add_registry(_load_json_targets(FIXTURE_TARGETS, origin="r07"))
        for name in ("objects.json", "yards.json", "targets.json"):
            self.add_registry(_load_json_targets(R12_GEO_DIR / name, origin="r12"))
        if registry:
            self.add_registry(registry)
        if use_r12:
            try:  # R12 ещё может не быть — это нормально.
                from engine import civic_geo  # type: ignore

                if hasattr(civic_geo, "target_geometry"):
                    self._r12 = civic_geo
            except Exception:
                self._r12 = None

    def add_registry(self, items: dict) -> None:
        for tid, item in (items or {}).items():
            if isinstance(item, dict) and item.get("geometry"):
                self._registry[tid] = item
        self._cache.clear()

    # ---- граф улиц ----
    def _edge_index(self) -> dict:
        with self._lock:
            if self._edges is None:
                self._edges = {}
                if self._graph_path and Path(self._graph_path).exists():
                    raw = json.loads(Path(self._graph_path).read_text("utf-8"))
                    for e in raw.get("edges", []):
                        self._edges[e["id"]] = (e.get("geometry"), e.get("name"))
            return self._edges

    def _street_index(self) -> dict:
        """Сетка середин рёбер с названиями — для подписи «у ул. …». Строится один раз."""
        edges = self._edge_index()
        with self._lock:
            if self._streets is None:
                grid: dict = {}
                for geom, name in edges.values():
                    if not name or not geom:
                        continue
                    mid = geo.line_midpoint(geom)
                    grid.setdefault((int(mid[0] // _STREET_CELL), int(mid[1] // _STREET_CELL)), []).append((mid, name))
                self._streets = grid
            return self._streets

    def nearest_street(self, point, max_m: float = 250.0) -> str | None:
        grid = self._street_index()
        cx, cy = int(point[0] // _STREET_CELL), int(point[1] // _STREET_CELL)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for mid, name in grid.get((cx + dx, cy + dy), ()):
                    d = geo.haversine_m(point, mid)
                    if d <= max_m and (best is None or d < best[0]):
                        best = (d, name)
        return best[1] if best else None

    def _osm_object(self, tid: str) -> dict | None:
        if not self._use_osm_objects or not _OSM_RE.match(tid):
            return None
        item = osm_objects.load().get(tid)
        if not item:
            return None
        label_ru, label_kk = item["label_ru"], item["label_kk"]
        if item.get("needs_street_label"):
            near = _street_labels().get(tid)          # заранее посчитано build_fixtures (быстро, с name:kk)
            if not near:
                anchor = geo.anchor_of(item["geometry"])
                near = near_street_labels(item["subtype"], self.nearest_street(anchor)) if anchor else None
            if near:
                label_ru, label_kk = near
        return {"geometry": item["geometry"], "label_ru": label_ru, "label_kk": label_kk, "approximate": False,
                "source": item["source"], "subtype": item["subtype"]}

    def _cell(self, tid: str, target: dict, point) -> dict | None:
        """Ячейка cell-<x>-<y>. С R09 fa49fc9 сетка общая (угол 71.0/50.8, geo.py = ui/civic_feedback/v2/record.py),
        но записи R09 до fa49fc9 считали id от угла 70.9/50.8 — та же id там в ~7 км.
        Решает точка жалобы: какая ячейка её содержит, та и правильная. Без точки — флаг approximate
        (его ставит только запасная цель R09). Ячейка с approximate — «примерное место» (пунктир), иначе «Квартал»."""
        family = cell_family(tid, point, target)
        approx = family != "r07" or bool(target.get("approximate"))
        poly = geo.cell_polygon(tid) if family == "r07" else r09_cell_polygon(tid, legacy=(family == "r09-legacy"))
        if not poly:
            return None
        if approx:
            return {"geometry": poly, "label_ru": APPROX_LABELS[0], "label_kk": APPROX_LABELS[1],
                    "approximate": True, "source": "cell-grid" if family == "r07" else "cell-grid-r09"}
        return {"geometry": poly, "label_ru": "Квартал", "label_kk": "Орам", "approximate": False, "source": "cell-grid"}

    def resolve(self, target: dict | None, point=None) -> dict | None:
        """→ {geometry, label_ru, label_kk, approximate, anchor, source} или None, если нечего показать."""
        target = target or {}
        tid = str(target.get("id") or "")
        kind = target.get("kind") or "area"
        key = (kind, tid) if tid else ("point", tuple(point) if point else None)
        if tid.startswith("cell-"):
            key = (kind, tid, cell_family(tid, point, target))   # одна id — два места (сетки R07 и R09)
        if key in self._cache:
            return self._cache[key]
        found = self._resolve(kind, tid, target, point)
        if found:
            found.setdefault("anchor", geo.anchor_of(found["geometry"]))
            # R15-S11: подпись из записи жалобы — только у ячейки «примерного места», где своего названия у карты нет.
            # Объект, участок улицы, двор подписываются по OSM/R12: запись приходит от жителя, и её подпись иначе
            # показывалась бы всем на карте и в «Картине дня» (подмена названия любым текстом).
            if found.get("source") in RECORD_LABEL_SOURCES:
                if target.get("label_ru"):
                    found["label_ru"] = str(target["label_ru"])[:80]
                if target.get("label_kk"):
                    found["label_kk"] = str(target["label_kk"])[:80]
                # R09/R12 пишут «Шамамен орны»; в словаре R11 (target.kind.cell, common.tag.approx) — «Шамамен көрсетілген орын».
                if found["label_kk"].startswith(_APPROX_KK_SHORT):
                    found["label_kk"] = APPROX_LABELS[1] + found["label_kk"][len(_APPROX_KK_SHORT):]
        if tid:
            self._cache[key] = found
        return found

    def _resolve(self, kind, tid, target, point):
        if tid.startswith("cell-") and tid not in self._registry:
            return self._cell(tid, target, point)
        item = self._registry.get(tid)
        if _OSM_RE.match(tid) and (item is None or item.get("_origin") != "r07"):
            real = self._osm_object(tid)      # I-01: свой слой OSM главнее голых имён из файлов R12
            if real:
                return real
        if item is not None:
            label_ru, label_kk = item.get("label_ru"), item.get("label_kk")
            if not label_ru and item.get("subtype") in _NEAR_WORDS:
                anchor = geo.anchor_of(item["geometry"])
                near = near_street_labels(item["subtype"], self.nearest_street(anchor)) if anchor else None
                label_ru, label_kk = near or (None, None)
            plain = osm_objects.plain_labels(item.get("subtype")) or KIND_WORD.get(kind, KIND_WORD["area"])
            return {"geometry": item["geometry"], "label_ru": label_ru or plain[0], "label_kk": label_kk or plain[1],
                    "approximate": bool(item.get("approximate")), "source": item.get("source", "registry"),
                    "subtype": item.get("subtype")}
        if self._r12 is not None and tid:
            try:
                got = self._r12.target_geometry({"kind": kind, "id": tid})
                if got and got.get("geometry"):
                    plain = KIND_WORD.get(kind, KIND_WORD["area"])
                    return {"geometry": got["geometry"], "label_ru": got.get("label_ru") or plain[0],
                            "label_kk": got.get("label_kk") or plain[1],
                            "approximate": bool(got.get("approximate")), "source": "r12"}
            except Exception:
                pass
        real = self._osm_object(tid)
        if real:
            return real
        if kind == "segment" and _EDGE_RE.match(tid):
            edge = self._edge_index().get(tid)
            if edge and edge[0] and len(edge[0]) >= 2:
                ru, kk = segment_labels(edge[1], None)
                return {"geometry": {"type": "LineString", "coordinates": edge[0]}, "label_ru": ru, "label_kk": kk,
                        "approximate": False, "source": "osm-walking-graph"}
        if point and len(point) == 2:
            return {"geometry": geo.circle_polygon(point, APPROX_RADIUS_M), "label_ru": APPROX_LABELS[0],
                    "label_kk": APPROX_LABELS[1], "approximate": True, "source": "complaint-point"}
        return None


# ---------- Сетка «примерного места» R09 ----------
# Сейчас R09 считает ячейки по общей сетке (ui/civic_feedback/v2/record.py, угол 71.0/50.8) — берём его функцию.
# Записи R09 до fa49fc9 считали id от угла 70.9/50.8 («старая» формула ниже) — их тоже рисуем там, где нажал житель.
R09_CELL_ORIGIN = (70.9, 50.8)
R09_DLAT = 150.0 / 111320.0
R09_DLON = 150.0 / (111320.0 * math.cos(math.radians(51.15)))
_CELL_ID_RE = re.compile(r"^cell-(-?\d+)-(-?\d+)$")


def r09_cell_polygon(cell_id: str, *, legacy: bool = False) -> dict | None:
    """Контур ячейки R09: функция модуля R09, если он есть (и legacy=False), иначе «старая» формула 70.9/50.8."""
    if not legacy:
        try:
            from ui.civic_feedback.v2 import record as r09_record  # type: ignore

            ring = r09_record.cell_polygon(cell_id)
            if ring:
                return {"type": "Polygon", "coordinates": [ring]}
        except Exception:
            pass
    m = _CELL_ID_RE.match(cell_id or "")
    if not m:
        return None
    col, row = int(m.group(1)), int(m.group(2))
    x0 = R09_CELL_ORIGIN[0] + col * R09_DLON
    y0 = R09_CELL_ORIGIN[1] + row * R09_DLAT
    x1, y1 = x0 + R09_DLON, y0 + R09_DLAT
    ring = [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]
    return {"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)] for x, y in ring]]}


def _in_box(point, polygon: dict | None, pad: float = 1e-6) -> bool:
    if not polygon:
        return False
    bb = geo.bbox_of(polygon)
    return bb[0] - pad <= point[0] <= bb[2] + pad and bb[1] - pad <= point[1] <= bb[3] + pad


def cell_family(cell_id: str, point, target: dict | None) -> str:
    """'r07' (общая сетка R07/R12/R09), 'r09' (контур модуля R09) или 'r09-legacy' (старая формула R09) —
    по точке жалобы: какая ячейка её содержит. Без точки — по флагу approximate."""
    if point and len(point) == 2:
        if _in_box(point, geo.cell_polygon(cell_id)):
            return "r07"
        if _in_box(point, r09_cell_polygon(cell_id)):
            return "r09"
        if _in_box(point, r09_cell_polygon(cell_id, legacy=True)):
            return "r09-legacy"
    return "r09" if (target or {}).get("approximate") else "r07"


_street_labels_cache: dict | None = None


def _street_labels() -> dict:
    global _street_labels_cache
    if _street_labels_cache is None:
        try:
            raw = json.loads(STREET_LABELS.read_text("utf-8"))
            _street_labels_cache = {k: tuple(v) for k, v in raw.get("labels", {}).items()}
        except (OSError, ValueError):
            _street_labels_cache = {}
    return _street_labels_cache


def _load_json_targets(path: Path, origin: str | None = None) -> dict:
    """Читает реестр целей: {"targets": {id: {...}}} или {"items": [{id, geometry, ...}]}; иначе пусто.
    origin: "r07" — своя демо-фикстура (подписи выверены), "r12" — файлы R12 (kind = подтип, имя без типа)."""
    try:
        raw = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(raw, dict) and isinstance(raw.get("targets"), dict):
        return {tid: (dict(it, _origin=origin) if isinstance(it, dict) and origin else it) for tid, it in raw["targets"].items()}
    items = raw.get("items") if isinstance(raw, dict) else raw
    out = {}
    for it in items or []:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        it = dict(it)
        if not it.get("geometry"):
            # R12 (geo/objects.json, yards.json): поля point / polygon; другие источники — {lon, lat} или coordinates.
            poly = it.get("polygon")
            if isinstance(poly, list) and poly and isinstance(poly[0], list):
                rings = poly if isinstance(poly[0][0], list) else [poly]
                it["geometry"] = {"type": "Polygon", "coordinates": rings}
            c = it.get("point") or it.get("coordinates") or ([it["lon"], it["lat"]] if "lon" in it and "lat" in it else None)
            if not it.get("geometry") and c and len(c) == 2 and all(isinstance(v, (int, float)) for v in c):
                it["geometry"] = {"type": "Point", "coordinates": [float(c[0]), float(c[1])]}
        if origin == "r12" and not it.get("subtype") and osm_objects.plain_labels(it.get("kind")):
            it["subtype"] = it["kind"]             # у R12 kind = bus_stop / playground / yard …
        made = osm_objects.labels_for_subtype(it.get("subtype"), it.get("name_ru") or it.get("name"), it.get("name_kk")) \
            if origin == "r12" and not it.get("label_ru") else None
        if made:
            it["label_ru"], it["label_kk"] = made
        it.setdefault("label_ru", it.get("name_ru") or it.get("name"))
        it.setdefault("label_kk", it.get("name_kk"))
        if origin:
            it["_origin"] = origin
        if it.get("geometry"):
            out[str(it["id"])] = it
    return out
