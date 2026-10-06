"""Адаптер K03 r10 pedestrian graph (k03-pedestrian-graph-v1) -> civic-scenario graph (mode=walking).

Источник (закреплён): ветка claude/beautiful-clarke-sbzomj, коммит b2cb2e02c602c166ba6d47c02d8e902e5478c791,
файл web/govtech/k03/astana.graph.json. Граф построен K03 (research/round-10-results/K03/build_graph.py)
из Overture 2026-09-23.1 (производная OSM, ODbL-1.0). Это ПЕШЕХОДНЫЙ граф небольшого квадрата
центра Астаны (bbox ~2×2 км), а не автомобильная сеть города. Режим walking не переименовывается.

Что есть в источнике и как переносится (поля K03 -> civic):
  e.s = [вперёд, назад] доступ strict (ok|unk|no), e.x — exploratory (ok|no).
    s=[ok,ok]                -> access=allowed, oneway=false
    s=[ok,no] / s=[no,ok]    -> access=allowed, oneway=true (направление по s; в astana не встречается)
    s=[unk,unk], x=[ok,ok]   -> access=unknown, oneway=false
    s=[unk,no],  x=[ok,ok]   -> access=unknown, oneway=false: K03 strict буквально применяет автомобильный
                                oneway к пешеходу; exploratory — нет (допущение vehicle_oneway_not_applied_to_foot).
                                В civic unknown не используется для ok-маршрутов, поэтому разницы для strict нет.
    s=[no,no],   x=[no,no]   -> access=denied
    иные сочетания           -> AdapterNotReady (не угадываем).
  e.len_mm -> length_m = len_mm / 1000 (точно, целые мм).
  n.open   -> boundary (граница среза: за узлом сеть продолжается вне графа).
  e.coords -> geometry (только для карты).
Чего нет: подтверждения на местности, времени в пути, светофоров, ширины, доступности для МГН,
разрешений для автомобиля. Данных для mode=driving НЕТ (см. driving_not_ready()).

Проверка целостности: sha256 сырого файла (закреплён) и пересчёт graph_sha256 по канонизации K03
(JSON.stringify с сортировкой ключей по UTF-16; Python-реализация чисел по образцу
research/round-10-results/K03/k03net.py, ветка claude/epic-curie-iitc43).
"""
import hashlib
import json
from decimal import Decimal

from ..canon import graph_digest

SOURCE = {
    "branch": "claude/beautiful-clarke-sbzomj",
    "commit": "b2cb2e02c602c166ba6d47c02d8e902e5478c791",
    "path": "web/govtech/k03/astana.graph.json",
    "file_sha256": "a6f823292331713dc5eb314aff53fc3de0836bf9fdc95f310c21053d0c28aace",
    "graph_sha256": "799d26e5155248cceb31eb67f76f92d453491770a73c387bf0371289ddcf0ae4",
    "schema": "k03-pedestrian-graph-v1",
}
GRAPH_ID = "k03-astana-pedestrian-r10"
HASH_KEYS = ["schema", "city", "bbox", "release", "policy_family", "policy_sha256", "max_snap_m", "inputs", "nodes", "edges"]


class AdapterNotReady(Exception):
    pass


# ---------- канонизация K03 (совместимо с JSON.stringify) ----------
def _js_num(x):
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, int):
        return str(x)
    if x != x or x in (float("inf"), float("-inf")):
        return "null"
    if x == 0:
        return "0"
    _, digits, exp = Decimal(repr(abs(x))).as_tuple()
    ds = "".join(map(str, digits)).rstrip("0") or "0"
    exp += len(digits) - len(ds)
    k, n = len(ds), exp + len(ds)
    neg = "-" if x < 0 else ""
    if k <= n <= 21:
        return neg + ds + "0" * (n - k)
    if 0 < n <= 21:
        return neg + ds[:n] + "." + ds[n:]
    if -6 < n <= 0:
        return neg + "0." + "0" * (-n) + ds
    e = n - 1
    return neg + ds[0] + ("." + ds[1:] if k > 1 else "") + "e" + ("+" if e > 0 else "-") + str(abs(e))


def _js_str(s):
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch in "\b\f\n\r\t":
            out.append({"\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}[ch])
        elif o < 0x20 or 0xD800 <= o <= 0xDFFF:
            out.append("\\u%04x" % o)
        else:
            out.append(ch)
    return "".join(out) + '"'


def _canon(v):
    if v is None:
        return "null"
    if isinstance(v, (bool, int, float)):
        return _js_num(v)
    if isinstance(v, str):
        return _js_str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(_canon(x) for x in v) + "]"
    return "{" + ",".join(_js_str(k) + ":" + _canon(v[k]) for k in sorted(v, key=lambda s: s.encode("utf-16-be"))) + "}"


def k03_graph_sha256(g):
    return hashlib.sha256(_canon({k: g[k] for k in HASH_KEYS}).encode("utf-8")).hexdigest()


# ---------- преобразование ----------
def _edge_access(e):
    s, x = tuple(e["s"]), tuple(e["x"])
    if s == ("ok", "ok"):
        return "allowed", False, False
    if s in (("ok", "no"), ("no", "ok")):
        return "allowed", True, s == ("no", "ok")
    if s == ("unk", "unk") and x == ("ok", "ok"):
        return "unknown", False, False
    if s == ("unk", "no") and x == ("ok", "ok"):
        return "unknown", False, False
    if s == ("no", "no") and x == ("no", "no"):
        return "denied", False, False
    raise AdapterNotReady(f"edge {e['id']}: сочетание s={list(s)} x={list(x)} не имеет однозначного отображения в civic access")


def adapt(raw_bytes):
    """raw_bytes — содержимое astana.graph.json. Возвращает civic graph (dict) с digest."""
    file_sha = hashlib.sha256(raw_bytes).hexdigest()
    if file_sha != SOURCE["file_sha256"]:
        raise AdapterNotReady(f"sha256 файла {file_sha} не равен закреплённому {SOURCE['file_sha256']}")
    g = json.loads(raw_bytes.decode("utf-8"))
    if g.get("schema") != SOURCE["schema"] or g.get("city") != "astana":
        raise AdapterNotReady("ожидается k03-pedestrian-graph-v1 для astana")
    if k03_graph_sha256(g) != g["graph_sha256"] or g["graph_sha256"] != SOURCE["graph_sha256"]:
        raise AdapterNotReady("graph_sha256 не подтверждается пересчётом")

    nodes = [{"id": n["id"], "lon": n["lon"], "lat": n["lat"], "boundary": bool(n["open"])} for n in g["nodes"]]
    edges, counts = [], {}
    for e in g["edges"]:
        access, oneway, reverse = _edge_access(e)
        frm, to, coords = (e["to"], e["from"], e["coords"][::-1]) if reverse else (e["from"], e["to"], e["coords"])
        key = f"s={'/'.join(e['s'])};x={'/'.join(e['x'])}->{access}"
        counts[key] = counts.get(key, 0) + 1
        edges.append({
            "id": e["id"], "from": frm, "to": to, "length_m": e["len_mm"] / 1000, "access": access, "oneway": oneway,
            "geometry": coords,
            "source": {"cls": e["cls"], "s": e["s"], "x": e["x"], "ev": e["ev"], "out_of_bbox": e["out"],
                       "assumptions": sorted({a for xa in e["xa"] for a in xa}), "osm": e["osm"]},
        })
    civic = {
        "id": GRAPH_ID, "city": "astana", "mode": "walking", "evidence_type": "derived",
        "label": "Пешеходный граф K03 (центр Астаны, ~2×2 км), Overture/OSM — не проверен на месте",
        "bbox": g["bbox"],
        "license": g["license"],
        "source": dict(SOURCE, release=g["release"], policy_family=g["policy_family"],
                       policy_sha256=g["policy_sha256"], build=g["build"], inputs=g["inputs"]),
        "access_mapping_counts": dict(sorted(counts.items())),
        "limitations": [
            "Только пешеходный режим (walking); автомобильный граф Астаны не подтверждён.",
            "Небольшой срез центра (bbox ~2×2 км); граничные узлы помечены boundary — за ними сеть не моделируется.",
            "64% рёбер (по числу) с неизвестным пешеходным доступом: в strict-маршрутах не используются.",
            "Длина — метры по ломаной (гаверсинус), не время в пути; нет светофоров, переходов-ожиданий, МГН.",
            "Данные OSM/Overture не проверялись на местности; дата релиза 2026-09-23.1.",
        ],
        "nodes": nodes, "edges": edges,
    }
    civic["digest"] = graph_digest(civic)
    return civic


def driving_not_ready():
    return {
        "status": "NOT_READY",
        "mode": "driving",
        "missing_fields": [
            "motor_vehicle access по направлениям (в K03 есть только foot-политика pedestrian-v1)",
            "oneway для автомобилей как отдельный признак (K03 сворачивает его в strict-доступ пешехода)",
            "запреты поворотов (turn restrictions) и связность по уровням для машин",
            "покрытие города: доступен только bbox центра ~2×2 км",
        ],
        "note": "Пешеходный граф не переименовывается в driving ради интерфейса.",
    }
