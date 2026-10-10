"""Где находится цель жалобы и как её назвать (CONTRACT §4).

Тепловая карта сама цели не выбирает (это R12, engine/civic_geo) — она только достаёт форму
и подпись цели по её id. Источники по порядку:
  1. реестр готовых целей (fixtures/targets_demo.json и данные R12 data/civic/astana/geo/*.json);
  2. модуль R12 engine.civic_geo, если в нём есть функция target_geometry(target);
  2а. реальные объекты OSM (LOCAL-1, data/civic/astana/osm-objects/): osm-node-…, osm-way-…, yard-…;
  3. участок улицы osm-w<way>-<n> — настоящая форма ребра из пешеходного графа OSM;
  4. ячейка cell-<ix>-<iy> — квадрат ~150 м по формуле из geo.py;
  5. иначе — «примерное место»: круг 60 м вокруг точки жалобы (никаких уверенных линий).
"""
from __future__ import annotations

import json
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
        self.add_registry(_load_json_targets(FIXTURE_TARGETS))
        for name in ("objects.json", "yards.json", "targets.json"):
            self.add_registry(_load_json_targets(R12_GEO_DIR / name))
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

    def resolve(self, target: dict | None, point=None) -> dict | None:
        """→ {geometry, label_ru, label_kk, approximate, anchor, source} или None, если нечего показать."""
        target = target or {}
        tid = str(target.get("id") or "")
        kind = target.get("kind") or "area"
        key = (kind, tid) if tid else ("point", tuple(point) if point else None)
        if key in self._cache:
            return self._cache[key]
        found = self._resolve(kind, tid, target, point)
        if found:
            found.setdefault("anchor", geo.anchor_of(found["geometry"]))
            # Подписи из записи жалобы (label_ru/label_kk) главнее автоматических.
            if target.get("label_ru"):
                found["label_ru"] = target["label_ru"]
            if target.get("label_kk"):
                found["label_kk"] = target["label_kk"]
        if tid:
            self._cache[key] = found
        return found

    def _resolve(self, kind, tid, target, point):
        if tid in self._registry:
            item = self._registry[tid]
            return {"geometry": item["geometry"], "label_ru": item.get("label_ru") or KIND_WORD.get(kind, KIND_WORD["area"])[0],
                    "label_kk": item.get("label_kk") or KIND_WORD.get(kind, KIND_WORD["area"])[1],
                    "approximate": bool(item.get("approximate")), "source": item.get("source", "registry"),
                    "subtype": item.get("subtype")}
        if self._r12 is not None and tid:
            try:
                got = self._r12.target_geometry({"kind": kind, "id": tid})
                if got and got.get("geometry"):
                    return {"geometry": got["geometry"], "label_ru": got.get("label_ru") or KIND_WORD[kind][0],
                            "label_kk": got.get("label_kk") or KIND_WORD[kind][1],
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
        if kind == "area" and tid.startswith("cell-"):
            poly = geo.cell_polygon(tid)
            if poly:
                return {"geometry": poly, "label_ru": "Квартал", "label_kk": "Орам", "approximate": False, "source": "cell-grid"}
        if point and len(point) == 2:
            return {"geometry": geo.circle_polygon(point, APPROX_RADIUS_M), "label_ru": "Примерное место",
                    "label_kk": "Шамамен көрсетілген орын", "approximate": True, "source": "complaint-point"}
        return None


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


def _load_json_targets(path: Path) -> dict:
    """Читает реестр целей: {"targets": {id: {...}}} или {"items": [{id, geometry, ...}]}; иначе пусто."""
    try:
        raw = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(raw, dict) and isinstance(raw.get("targets"), dict):
        return raw["targets"]
    items = raw.get("items") if isinstance(raw, dict) else raw
    out = {}
    for it in items or []:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        it = dict(it)
        if not it.get("geometry"):
            # Точечные объекты R12 могут прийти как {lon, lat} или {coordinates: [lon, lat]}.
            c = it.get("coordinates") or ([it["lon"], it["lat"]] if "lon" in it and "lat" in it else None)
            if c and len(c) == 2 and all(isinstance(v, (int, float)) for v in c):
                it["geometry"] = {"type": "Point", "coordinates": [float(c[0]), float(c[1])]}
        it.setdefault("label_ru", it.get("name_ru") or it.get("name"))
        it.setdefault("label_kk", it.get("name_kk"))
        if it.get("geometry"):
            out[str(it["id"])] = it
    return out
