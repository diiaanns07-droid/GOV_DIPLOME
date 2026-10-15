"""R12 · раунд 15 · Единый календарь работ и «копаем один раз» (CONTRACT §5.6, §7, §8).

Работы всех служб хранит R06 (запись «Работа v2», §5.6). Здесь — только две вещи:
1. Привязка работы к рёбрам графа OSM с настоящей формой улицы (`bind_work`):
   - по списку рёбер `segments` (так пишет редактор R12 и форма R06);
   - по улице и двум точкам (`street` + `from` + `to`) — участок строится только по рёбрам этой улицы;
   - по линии из редактора (`geometry` LineString) — линия «прилипает» к одной улице или к улицам по порядку;
   - только точка — честное «примерное место» (круг), без уверенной линии (CONTRACT §8).
2. Поиск конфликтов до того, как они случились (`find_conflicts`):
   - dig_after_surface    — асфальт или ремонт покрытия заканчивается, а потом на том же или соседнем участке
                            начинается раскопка (не позже чем через DIG_AFTER_SURFACE_MONTHS) — «копаем дважды»;
   - same_segment_overlap — работы двух служб на одном участке в одни и те же дни;
   - parallel_closures    — одновременно перекрыты параллельные улицы одного коридора (объезда не остаётся).
   Совет — словами ru/kk («Сначала замените сети, потом кладите асфальт»), без денег и без выдуманных чисел.

Всё детерминировано: одни и те же работы дают одни и те же конфликты, id и порядок (id конфликта — хэш вида и работ).
Числа считает код; тексты — шаблоны с датами и названиями улиц из OSM.
"""
from __future__ import annotations

import hashlib
import heapq
import json
import math
import threading
from datetime import date, datetime, timedelta
from typing import Iterable, Sequence

from . import geo, names
from .graph import StreetGraph, get_graph
from .paths import GEOFENCE
from .segment import GeoError, snap_along_one_street, snap_polyline, street_segment

# ------------------------------------------------------------------ виды работ (CONTRACT §5.6)
KINDS = ("dig", "surface", "closure", "landscape", "lighting", "other")
DIG_KINDS = frozenset({"dig"})            # раскопка: сети воды, тепла, газа, кабели
SURFACE_KINDS = frozenset({"surface"})    # асфальт, ремонт покрытия
CLOSURE_KINDS = frozenset({"closure"})    # перекрытие улицы (полностью или полосы)
# Старые виды записей раунда 14 (объекты R06 и «Работы и отключения») → вид v2, если R06 ещё не дал поле kind.
LEGACY_KINDS = {"roadworks": "surface", "event": "closure", "landscaping": "landscape", "lighting": "lighting",
                "construction": "other", "other": "other"}
# Статусы: отменённые работы не участвуют в конфликтах и не рисуются на календаре.
CANCELLED = frozenset({"cancelled", "canceled", "removed"})

# ------------------------------------------------------------------ правила конфликтов (все числа — здесь)
# «Копаем дважды»: раскопка позже нового покрытия не дальше чем через 18 месяцев. Это настройка платформы,
# а не норматив: 18 месяцев — текущий строительный сезон и следующий за ним (весна–осень и ещё одна весна–осень),
# то есть планы, которые службы уже знают и ещё могут поменять местами. Раскопка позже — обычный плановый ремонт.
DIG_AFTER_SURFACE_MONTHS = 18
# Соседний участок: касается работы в узле графа (продолжение улицы, перекрёсток) или проходит ближе 20 м от неё
# (вторая проезжая часть, тротуар или газон той же улицы — раскопка рядом всё равно задевает новое покрытие).
ADJACENT_M = 20.0
# Коридор для parallel_closures. Две улицы — «параллельные улицы одного коридора», если одновременно:
#   1) расстояние по графу улиц между их участками ≤ 400 м — путь пешком/на машине по улицам между ними короткий,
#      то есть это соседние улицы одного квартала, а не просто похожие по направлению улицы разных районов;
#   2) направления близки: оси участков различаются не больше чем на 30° (ось — средняя по длине, без учёта
#      стороны: улица «с севера на юг» и «с юга на север» — одно направление);
#   3) они идут бок о бок: проекции на общую ось перекрываются хотя бы на 50 м, а поперёк оси улицы разнесены
#      хотя бы на 25 м (ближе — это одна улица или её вторая проезжая часть, а не параллельная улица).
# Тогда транспорт с одной улицы уходит на другую; перекрыть обе сразу — значит не оставить объезда.
CORRIDOR_GRAPH_M = 400.0
PARALLEL_MAX_ANGLE_DEG = 30.0
PARALLEL_MIN_SIDE_BY_SIDE_M = 50.0
PARALLEL_MIN_APART_M = 25.0
# Важность: high — прямой ущерб (раскопка того же участка, что только что заасфальтирован; сети и асфальт на одном
# участке одновременно) или долгое совпадение (≥ 14 дней); medium — остальное (соседний участок, короткое совпадение).
LONG_OVERLAP_DAYS = 14
# Примерное место (работа без участков): круг этого радиуса на карте, в конфликтах не участвует.
APPROX_RADIUS_M = 120.0
APPROX_SNAP_M = 60.0          # точка дальше 60 м от улицы — к улице не привязываем
MAX_WORKS = 2000              # защита от случайно огромного ответа

KIND_LABELS = {
    "dig": ("Раскопка сетей", "Желілерді қазу"),
    "surface": ("Асфальт и покрытие", "Асфальт және жабын"),
    "closure": ("Перекрытие", "Жолды жабу"),
    "landscape": ("Благоустройство", "Абаттандыру"),
    "lighting": ("Освещение", "Жарықтандыру"),
    "other": ("Другие работы", "Басқа жұмыстар"),
}
CONFLICT_TITLES = {
    "dig_after_surface": ("Копаем дважды", "Екі рет қазу"),
    "same_segment_overlap": ("Две службы на одном участке", "Бір учаскеде екі қызмет"),
    "parallel_closures": ("Параллельные улицы перекрыты одновременно", "Қатар көшелер бір уақытта жабылады"),
}
KIND_ORDER = {"dig_after_surface": 0, "same_segment_overlap": 1, "parallel_closures": 2}
SEVERITY_ORDER = {"high": 0, "medium": 1}

MONTHS_RU_GEN = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
                 "ноября", "декабря")
MONTHS_KK = ("қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан",
             "қараша", "желтоқсан")
KK_VOWELS = set("аәеёиоөұүуыіэюяАӘЕЁИОӨҰҮУЫІЭЮЯ")


class WorkError(ValueError):
    """Неверная запись работы (код для API и текст для человека)."""
    status = 400

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ------------------------------------------------------------------ даты
def parse_day(value) -> date | None:
    """«2027-05-01», «2027-05-01T09:00:00+05:00» или date → date; пусто или ошибка → None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        if len(text) == 10:
            return date.fromisoformat(text)
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def add_months(day: date, months: int) -> date:
    """Тот же день через months месяцев (31 января + 1 → 28/29 февраля)."""
    y, m = divmod(day.month - 1 + months, 12)
    year, month = day.year + y, m + 1
    for d in (day.day, 30, 29, 28):
        try:
            return date(year, month, min(d, day.day))
        except ValueError:
            continue
    return date(year, month, 28)


def ru_plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def gap_words(days: int) -> tuple[str, str]:
    """Промежуток словами: («через 2 месяца», «2 айдан кейін»); меньше 45 дней — в днях."""
    if days < 45:
        n = max(1, days)
        return f"через {n} {ru_plural(n, 'день', 'дня', 'дней')}", f"{n} күннен кейін"
    n = max(1, round(days / 30.4))
    return f"через {n} {ru_plural(n, 'месяц', 'месяца', 'месяцев')}", f"{n} айдан кейін"


def day_words(day: date) -> tuple[str, str]:
    """(«20 мая 2027», «2027 ж. 20 мамыр»)."""
    return f"{day.day} {MONTHS_RU_GEN[day.month - 1]} {day.year}", f"{day.year} ж. {day.day} {MONTHS_KK[day.month - 1]}"


def range_words(a: date, b: date) -> tuple[str, str]:
    """(«1–20 мая 2027», «2027 ж. 1–20 мамыр») — даты одной работы коротко."""
    if a.year == b.year and a.month == b.month:
        return (f"{a.day}–{b.day} {MONTHS_RU_GEN[a.month - 1]} {a.year}",
                f"{a.year} ж. {a.day}–{b.day} {MONTHS_KK[a.month - 1]}")
    ra, ka = day_words(a)
    rb, kb = day_words(b)
    return f"{ra} – {rb}", f"{ka} – {kb}"


# ------------------------------------------------------------------ районы (для фильтра district)
_district_lock = threading.Lock()
_districts: list | None = None


def _district_rings() -> list:
    global _districts
    with _district_lock:
        if _districts is None:
            out = []
            try:
                data = json.loads(GEOFENCE.read_text("utf-8"))
                for item in data.get("polygons", []):
                    for ring in item.get("rings", []):
                        if len(ring) >= 4:
                            out.append((item.get("district_id"), ring, geo.bbox_of(ring)))
            except (OSError, ValueError, TypeError):
                out = []
            _districts = out
        return _districts


def district_of_point(p) -> str | None:
    for district, ring, bb in _district_rings():
        if bb[0] <= p[0] <= bb[2] and bb[1] <= p[1] <= bb[3] and geo.point_in_ring(p, ring):
            return district
    return None


# ------------------------------------------------------------------ привязка работы к графу
class BoundWork:
    """Работа, разложенная на рёбра графа, с датами, видом и формой — то, с чем работает поиск конфликтов."""

    __slots__ = ("id", "record", "service", "kind", "start", "end", "status", "edges", "edge_ids", "nodes",
                 "lines", "length_m", "street_ru", "street_kk", "approximate", "bind", "point", "bbox", "district",
                 "axis", "issues", "source", "demo")

    def to_public(self) -> dict:
        """Поля работы для календаря (запись §5.6 + форма и подписи; служебного в ответе нет)."""
        r = self.record
        out = {
            "id": self.id,
            "title_ru": r.get("title_ru") or r.get("title") or KIND_LABELS[self.kind][0],
            "title_kk": r.get("title_kk") or None,
            "service": self.service, "kind": self.kind,
            "kind_ru": KIND_LABELS[self.kind][0], "kind_kk": KIND_LABELS[self.kind][1],
            "starts_on": self.start.isoformat() if self.start else None,
            "ends_on": self.end.isoformat() if self.end else None,
            "status": self.status, "source": self.source, "demo": self.demo, "district": self.district,
            "segments": list(self.edge_ids),
            "length_m": round(self.length_m, 1) if self.length_m else 0.0,
            "street_ru": self.street_ru, "street_kk": self.street_kk,
            "approximate": self.approximate, "bind": self.bind, "point": self.point,
        }
        if self.approximate:
            out["geometry"] = {"type": "Point", "coordinates": self.point} if self.point else None
            out["radius_m"] = APPROX_RADIUS_M
        else:
            out["geometry"] = {"type": "MultiLineString", "coordinates": self.lines}
            out["bbox"] = [round(v, 6) for v in self.bbox]
        if self.issues:
            out["issues"] = list(self.issues)
        for key in ("source_ref", "source_name"):
            if r.get(key):
                out[key] = r[key]
        return out


def _first(record: dict, *keys):
    for k in keys:
        v = record.get(k)
        if v not in (None, "", []):
            return v
    return None


def work_dates(record: dict) -> tuple[date | None, date | None]:
    """Даты работы: поля v2 (starts_on/ends_on), иначе прежние поля R06 (start/planned_end, schedule.*)."""
    sched = record.get("schedule") if isinstance(record.get("schedule"), dict) else {}
    start = parse_day(_first(record, "starts_on", "start", "planned_start") or sched.get("planned_start"))
    end = parse_day(_first(record, "ends_on", "forecast_end", "end", "planned_end", "current_planned_end")
                    or sched.get("current_planned_end") or sched.get("original_planned_end"))
    if start and not end:
        end = start
    if end and not start:
        start = end
    return start, end


def work_kind(record: dict) -> str:
    kind = record.get("kind")
    if kind in KINDS:
        return kind
    legacy = record.get("work_kind") or kind
    return LEGACY_KINDS.get(legacy, "other")


def _chain_lines(graph: StreetGraph, edges) -> list[list[list[float]]]:
    """Рёбра по порядку → ломаные MultiLineString: соседние рёбра с общим узлом склеиваются в одну линию.
    Вершины — из OSM без изменений (форма улицы точная)."""
    lines: list[list[list[float]]] = []
    end_node = None
    edges = list(edges)
    for i, e in enumerate(edges):
        if lines and end_node in (e.a, e.b):
            coords = graph.oriented(e, end_node)
            lines[-1].extend([geo.round_coord(c) for c in coords[1:]])
            end_node = graph.other_end(e, end_node)
            continue
        # Новая линия: направление выбираем так, чтобы следующее ребро её продолжило.
        start = e.a
        nxt = edges[i + 1] if i + 1 < len(edges) else None
        if nxt is not None and e.a in (nxt.a, nxt.b) and e.b not in (nxt.a, nxt.b):
            start = e.b
        lines.append([geo.round_coord(c) for c in graph.oriented(e, start)])
        end_node = graph.other_end(e, start)
    return lines


def _axis_deg(lines) -> float | None:
    """Ось работы в градусах [0, 180): средняя по длине без учёта стороны (удвоенный угол)."""
    sx = sy = total = 0.0
    for line in lines:
        if len(line) < 2:
            continue
        f = geo.LocalFrame(line[0][0], line[0][1])
        prev = f.to_xy(line[0])
        for p in line[1:]:
            cur = f.to_xy(p)
            dx, dy = cur[0] - prev[0], cur[1] - prev[1]
            ln = math.hypot(dx, dy)
            if ln > 0:
                a = math.atan2(dy, dx)
                sx += ln * math.cos(2 * a)
                sy += ln * math.sin(2 * a)
                total += ln
            prev = cur
    if total <= 0 or math.hypot(sx, sy) < 1e-9 * total:
        return None
    return (math.degrees(math.atan2(sy, sx)) / 2.0) % 180.0


def _street_of(edges) -> tuple[str | None, str | None]:
    """Главная улица работы — название с наибольшей длиной среди её рёбер."""
    by_name: dict[str, float] = {}
    first: dict[str, object] = {}
    for e in edges:
        if e.name:
            by_name[e.name] = by_name.get(e.name, 0.0) + e.length_m
            first.setdefault(e.name, e)
    if not by_name:
        return None, None
    name = min(by_name, key=lambda n: (-by_name[n], n))
    return name, first[name].label_kk()


def bind_work(record: dict, graph: StreetGraph | None = None) -> BoundWork:
    """Привязать одну работу к графу (без исключений: что не вышло — в issues, место — «примерное»)."""
    g = graph or get_graph()
    w = BoundWork()
    w.record = record
    w.id = str(record.get("id") or "")
    w.service = record.get("service") or record.get("source_service") or None
    if w.service is None and record.get("type") == "outage" and record.get("source"):
        w.service = record.get("source")
    w.kind = work_kind(record)
    w.start, w.end = work_dates(record)
    if w.start and w.end and w.end < w.start:
        w.start, w.end = w.end, w.start
    w.status = record.get("status") or None
    w.source = record.get("source") if record.get("source") in ("real", "demo") else ("demo" if record.get("demo") else None)
    w.demo = bool(record.get("demo")) or w.source == "demo"
    w.issues = []
    edges = []
    w.bind = "none"
    seg_ids = record.get("segments")
    if isinstance(seg_ids, (list, tuple)) and seg_ids:
        seen = set()
        for sid in seg_ids:
            e = g.by_id.get(str(sid))
            if e is None:
                w.issues.append("unknown_segment")
                continue
            if e.id not in seen:
                seen.add(e.id)
                edges.append(e)
        if edges:
            w.bind = "segments"
    if not edges and record.get("street") and record.get("from") and record.get("to"):
        try:
            edges = _edges_of(g, segment_on_street(record["street"], record["from"], record["to"], g))
            w.bind = "street"
        except (GeoError, WorkError, TypeError, ValueError):
            w.issues.append("street_not_found")
    geom = record.get("geometry") if isinstance(record.get("geometry"), dict) else None
    if not edges and geom and geom.get("type") == "LineString" and len(geom.get("coordinates") or []) >= 2:
        coords = geom["coordinates"]
        try:
            res = snap_along_one_street(g, coords, ("road", "service")) or snap_polyline(g, coords)
            edges = _edges_of(g, res)
            w.bind = "line"
        except GeoError:
            w.issues.append("line_not_on_street")
    if edges:
        w.approximate = False
        w.edges = tuple(edges)
        w.edge_ids = tuple(e.id for e in edges)
        w.nodes = frozenset(n for e in edges for n in (e.a, e.b))
        w.lines = _chain_lines(g, edges)
        w.length_m = sum(e.length_m for e in edges)
        w.street_ru, w.street_kk = _street_of(edges)
        if record.get("street_ru") and not w.street_ru:
            w.street_ru = record.get("street_ru")
        xs = [c[0] for line in w.lines for c in line]
        ys = [c[1] for line in w.lines for c in line]
        w.bbox = (min(xs), min(ys), max(xs), max(ys))
        mid_line = max(w.lines, key=len)
        w.point = geo.round_coord(geo.point_at_along(mid_line, geo.polyline_length_m(mid_line) / 2)[1])
        w.axis = _axis_deg(w.lines)
    else:
        w.approximate = True
        w.edges, w.edge_ids, w.nodes, w.lines = (), (), frozenset(), []
        w.length_m = 0.0
        w.axis = None
        w.point = _approx_point(record)
        w.bbox = tuple(w.point * 2) if w.point else None
        w.bind = "point" if w.point else "none"
        w.street_ru = record.get("street_ru") or (record.get("street") if isinstance(record.get("street"), str) else None)
        w.street_kk = record.get("street_kk") or None
        if w.point and not w.street_ru:
            near = g.nearest(w.point, APPROX_SNAP_M, accept=lambda e: bool(e.name))
            if near:
                w.street_ru, w.street_kk = near[0][1].name, near[0][1].label_kk()
    w.district = record.get("district") or (district_of_point(w.point) if w.point else None)
    if not w.start:
        w.issues.append("no_dates")
    return w


def _edges_of(g: StreetGraph, res: dict):
    out, seen = [], set()
    for eid in res.get("edge_ids") or []:
        e = g.by_id.get(eid)
        if e is not None and e.id not in seen:
            seen.add(e.id)
            out.append(e)
    if not out:
        raise GeoError("no_edges", "Участок не лёг на улицы.")
    return out


def _approx_point(record: dict) -> list[float] | None:
    p = record.get("point")
    geom = record.get("geometry") if isinstance(record.get("geometry"), dict) else None
    if p is None and geom:
        c = geom.get("coordinates")
        if geom.get("type") == "Point":
            p = c
        elif geom.get("type") == "LineString" and c:
            p = c[len(c) // 2]
        elif geom.get("type") == "Polygon" and c and c[0]:
            p = geo.bbox_center(c[0])
    try:
        lon, lat = float(p[0]), float(p[1])
    except (TypeError, ValueError, IndexError):
        return None
    if not (math.isfinite(lon) and math.isfinite(lat)):
        return None
    return geo.round_coord([lon, lat])


def segment_on_street(street: str, a, b, graph: StreetGraph | None = None) -> dict:
    """Участок ОДНОЙ улицы между двумя точками: рёбра только с этим названием (ru или kk), форма — из OSM.

    Для формы R06 «по улице» и для генератора демо-мира R02. Точки — [lon, lat] (щелчки или концы участка).
    Нет такой улицы ближе 60 м от точек — GeoError not_on_street (тогда место «примерное», не линия)."""
    g = graph or get_graph()
    want = _norm(street)
    if not want:
        raise WorkError("bad_street", "Укажите улицу.")

    def same(e) -> bool:
        return bool(e.name) and (_norm(e.name) == want or _norm(e.label_kk()) == want
                                 or _norm(names.ru_short(e.name)) == want)
    return street_segment(g, _pt(a), _pt(b), only=same)


def _pt(p) -> list[float]:
    if isinstance(p, str):
        p = p.split(",")
    return [float(p[0]), float(p[1])]


def _norm(text) -> str:
    return " ".join(str(text or "").lower().replace("ё", "е").split())


# ------------------------------------------------------------------ геометрия пар
def _seg_dist(p, q, r, s) -> float:
    """Расстояние между отрезками pq и rs на плоскости (метры)."""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1, d2, d3, d4 = cross(r, s, p), cross(r, s, q), cross(p, q, r), cross(p, q, s)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 and d2 and d3 and d4:
        return 0.0

    def pt_seg(x, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        ll = dx * dx + dy * dy
        t = 0.0 if ll <= 0 else max(0.0, min(1.0, ((x[0] - a[0]) * dx + (x[1] - a[1]) * dy) / ll))
        return math.hypot(a[0] + t * dx - x[0], a[1] + t * dy - x[1])
    return min(pt_seg(p, r, s), pt_seg(q, r, s), pt_seg(r, p, q), pt_seg(s, p, q))


def _near_edges(a: BoundWork, b: BoundWork, limit_m: float) -> tuple[set, set]:
    """Рёбра a и b, которые ближе limit_m друг к другу (по точной форме). Пустые множества — не рядом."""
    pad = limit_m / geo.M_PER_DEG * 1.7
    bb_a, bb_b = a.bbox, b.bbox
    if (bb_a[0] - pad > bb_b[2] or bb_b[0] - pad > bb_a[2] or bb_a[1] - pad > bb_b[3] or bb_b[1] - pad > bb_a[3]):
        return set(), set()
    frame = geo.LocalFrame(bb_a[0], bb_a[1])
    near_a, near_b = set(), set()
    pad_lat = limit_m / geo.M_PER_DEG
    pad_lon = pad_lat / max(0.2, math.cos(math.radians(bb_a[1])))
    for ea in a.edges:
        ba = ea.bbox
        for eb in b.edges:
            bb = eb.bbox
            if (ba[0] - pad_lon > bb[2] or bb[0] - pad_lon > ba[2] or ba[1] - pad_lat > bb[3] or bb[1] - pad_lat > ba[3]):
                continue
            if ea.id == eb.id or {ea.a, ea.b} & {eb.a, eb.b}:
                near_a.add(ea.id)
                near_b.add(eb.id)
                continue
            if _edges_dist(frame, ea, eb, limit_m) <= limit_m:
                near_a.add(ea.id)
                near_b.add(eb.id)
    return near_a, near_b


def _edges_dist(frame, ea, eb, limit_m: float) -> float:
    pa = [frame.to_xy(c) for c in ea.geometry]
    pb = [frame.to_xy(c) for c in eb.geometry]
    best = float("inf")
    for i in range(len(pa) - 1):
        for j in range(len(pb) - 1):
            d = _seg_dist(pa[i], pa[i + 1], pb[j], pb[j + 1])
            if d < best:
                best = d
                if best <= limit_m:
                    return best
    return best


def _graph_reach(g: StreetGraph, nodes: Iterable[str], limit_m: float) -> dict[str, float]:
    """Узлы графа не дальше limit_m по улицам от любого из nodes (многоисточниковая Дейкстра)."""
    dist: dict[str, float] = {}
    heap = []
    for n in sorted(set(nodes)):
        dist[n] = 0.0
        heap.append((0.0, n))
    heapq.heapify(heap)
    while heap:
        d, n = heapq.heappop(heap)
        if d > dist.get(n, float("inf")):
            continue
        for idx in g.adj.get(n, ()):
            e = g.edges[idx]
            m = e.b if n == e.a else e.a
            nd = d + e.length_m
            if nd <= limit_m and nd < dist.get(m, float("inf")):
                dist[m] = nd
                heapq.heappush(heap, (nd, m))
    return dist


def _angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _side_by_side(a: BoundWork, b: BoundWork) -> tuple[float, float]:
    """(перекрытие проекций на общую ось, расстояние поперёк оси) в метрах — «идут ли улицы бок о бок»."""
    axis = math.radians(_mean_axis(a.axis, b.axis))
    ux, uy = math.cos(axis), math.sin(axis)
    frame = geo.LocalFrame(a.point[0], a.point[1])

    def spans(w):
        along, across = [], []
        for line in w.lines:
            for c in line:
                x, y = frame.to_xy(c)
                along.append(x * ux + y * uy)
                across.append(-x * uy + y * ux)
        return min(along), max(along), sum(across) / len(across)
    a0, a1, ca = spans(a)
    b0, b1, cb = spans(b)
    return min(a1, b1) - max(a0, b0), abs(ca - cb)


def _mean_axis(a: float, b: float) -> float:
    x = math.cos(math.radians(2 * a)) + math.cos(math.radians(2 * b))
    y = math.sin(math.radians(2 * a)) + math.sin(math.radians(2 * b))
    return (math.degrees(math.atan2(y, x)) / 2.0) % 180.0


# ------------------------------------------------------------------ конфликты
def _overlap(a: BoundWork, b: BoundWork) -> tuple[date, date] | None:
    lo, hi = max(a.start, b.start), min(a.end, b.end)
    return (lo, hi) if lo <= hi else None


def _conflict_id(kind: str, ids: Sequence[str]) -> str:
    digest = hashlib.sha1(("|".join([kind, *ids])).encode("utf-8")).hexdigest()[:10]
    return f"cf-{digest}"


def _street_pair(a: BoundWork, b: BoundWork) -> tuple[str | None, str | None]:
    """Подпись улиц конфликта: одна улица или «ул. A и ул. B» / «A көшесі мен B көшесі»."""
    ra = names.ru_short(a.street_ru) if a.street_ru else None
    rb = names.ru_short(b.street_ru) if b.street_ru else None
    ka, kb = a.street_kk or a.street_ru, b.street_kk or b.street_ru
    if not ra and not rb:
        return None, None
    if not rb or ra == rb:
        return ra, ka
    if not ra:
        return rb, kb
    # «мен» после гласной (у казахских подписей улиц — «көшесі», «даңғылы»); иначе — через запятую.
    kk = f"{ka} мен {kb}" if ka and ka[-1] in KK_VOWELS else f"{ka}, {kb}"
    return f"{ra} и {rb}", kk


def _service_names() -> dict[str, dict]:
    """Названия служб ru/kk — таблица служб R08 (с правками акимата); нет модуля — своя копия общих названий."""
    try:
        from ui.civic_akim import routing  # только чтение (CONTRACT §3)
        return routing.table().get("services") or dict(routing.SERVICES)
    except Exception:  # модуль R08 недоступен — общие названия без правок
        return dict(FALLBACK_SERVICES)


FALLBACK_SERVICES = {
    "road": {"ru": "Дорожная служба", "kk": "Жол қызметі"},
    "traffic": {"ru": "Служба светофоров и разметки", "kk": "Бағдаршам және жол таңбасы қызметі"},
    "street_cleaning": {"ru": "Служба уборки улиц", "kk": "Көшелерді тазалау қызметі"},
    "transport": {"ru": "Служба общественного транспорта", "kk": "Қоғамдық көлік қызметі"},
    "lighting": {"ru": "Служба освещения", "kk": "Жарықтандыру қызметі"},
    "landscaping": {"ru": "Служба благоустройства", "kk": "Абаттандыру қызметі"},
    "greenery": {"ru": "Служба озеленения", "kk": "Көгалдандыру қызметі"},
    "waste": {"ru": "Оператор вывоза мусора", "kk": "Қоқыс шығару операторы"},
    "utilities": {"ru": "Служба ЖКХ", "kk": "ТКШ қызметі"},
    "heating": {"ru": "Теплосеть", "kk": "Жылу желісі"},
    "water": {"ru": "Водоканал", "kk": "Сумен жабдықтау қызметі"},
    "power": {"ru": "Электросети", "kk": "Электр желілері"},
    "gas": {"ru": "Газовая служба", "kk": "Газ қызметі"},
    "housing": {"ru": "Управляющая компания дома", "kk": "Үйді басқарушы компания"},
    "ecology": {"ru": "Служба экологии", "kk": "Экология қызметі"},
    "emergency": {"ru": "Служба спасения", "kk": "Құтқару қызметі"},
    "police": {"ru": "Полиция", "kk": "Полиция"},
    "animals": {"ru": "Служба отлова животных", "kk": "Жануарларды аулау қызметі"},
    "parking": {"ru": "Служба парковок", "kk": "Тұрақ қызметі"},
    "akimat": {"ru": "Аппарат акима района", "kk": "Аудан әкімінің аппараты"},
}


def _svc(services: dict, sid: str | None) -> tuple[str, str]:
    item = services.get(sid or "") or {}
    ru = item.get("ru") or (FALLBACK_SERVICES.get(sid or "") or {}).get("ru") or "Служба не указана"
    kk = item.get("kk") or (FALLBACK_SERVICES.get(sid or "") or {}).get("kk") or "Қызмет көрсетілмеген"
    return ru, kk


def _make(kind: str, a: BoundWork, b: BoundWork, severity: str, segments, extra: dict, advice: tuple[str, str],
          g: StreetGraph) -> dict:
    ids = sorted([a.id, b.id])
    edges = [g.by_id[s] for s in segments if s in g.by_id]
    lines = _chain_lines(g, edges)
    street_ru, street_kk = _street_pair(a, b)
    title_ru, title_kk = CONFLICT_TITLES[kind]
    out = {
        "id": _conflict_id(kind, ids), "kind": kind, "works": ids, "segments": list(segments),
        "severity": severity, "advice_ru": advice[0], "advice_kk": advice[1],
        "title_ru": title_ru, "title_kk": title_kk, "street_ru": street_ru, "street_kk": street_kk,
        "geometry": {"type": "MultiLineString", "coordinates": lines} if lines else None,
        "demo": a.demo or b.demo,
    }
    if lines:
        xs = [c[0] for line in lines for c in line]
        ys = [c[1] for line in lines for c in line]
        out["bbox"] = [round(min(xs), 6), round(min(ys), 6), round(max(xs), 6), round(max(ys), 6)]
    out.update(extra)
    return out


def _dig_after_surface(surface: BoundWork, dig: BoundWork, g: StreetGraph, services: dict) -> dict | None:
    """Асфальт (surface) закончили, потом на том же или соседнем участке начинается раскопка (dig)."""
    if not (surface.end < dig.start <= add_months(surface.end, DIG_AFTER_SURFACE_MONTHS)):
        return None
    shared = sorted(set(surface.edge_ids) & set(dig.edge_ids))
    if shared:
        segments, severity = shared, "high"
    else:
        near_s, near_d = _near_edges(surface, dig, ADJACENT_M)
        if not near_s:
            return None
        segments = sorted(near_s | near_d)
        severity = "medium"
    gap = (dig.start - surface.end).days
    gap_ru, gap_kk = gap_words(gap)
    s_ru, s_kk = _svc(services, surface.service)
    d_ru, d_kk = _svc(services, dig.service)
    where = "на том же участке" if severity == "high" else "на соседнем участке"
    where_kk = "сол учаскеде" if severity == "high" else "көрші учаскеде"
    advice_ru = (f"Сначала замените сети, потом кладите асфальт. {d_ru} начнёт раскопку {where} {gap_ru} после "
                 f"нового асфальта ({s_ru}). Перенесите асфальт на время после раскопки или раскопку — до асфальта.")
    advice_kk = (f"Алдымен желілерді ауыстырыңыз, содан кейін асфальт төсеңіз. Жаңа асфальт төселгеннен "
                 f"{gap_kk} {where_kk} қазу басталады ({d_kk}). Асфальт төсеуді қазудан кейінге "
                 f"ауыстырыңыз немесе қазуды асфальтқа дейін жүргізіңіз.")
    extra = {"surface_ends_on": surface.end.isoformat(), "dig_starts_on": dig.start.isoformat(), "gap_days": gap,
             "first": surface.id, "second": dig.id, "when_from": surface.start.isoformat(),
             "when_to": dig.end.isoformat()}
    return _make("dig_after_surface", surface, dig, severity, segments, extra, (advice_ru, advice_kk), g)


def _same_segment(a: BoundWork, b: BoundWork, g: StreetGraph, services: dict) -> dict | None:
    """Две службы на одном участке в одни и те же дни."""
    if a.service and b.service and a.service == b.service:
        return None  # одна служба планирует свои работы сама
    shared = sorted(set(a.edge_ids) & set(b.edge_ids))
    if not shared:
        return None
    ov = _overlap(a, b)
    if not ov:
        return None
    days = (ov[1] - ov[0]).days + 1
    kinds = {a.kind, b.kind}
    wrong_order = bool(kinds & DIG_KINDS) and bool(kinds & SURFACE_KINDS)
    severity = "high" if wrong_order or days >= LONG_OVERLAP_DAYS else "medium"
    a_ru, a_kk = _svc(services, a.service)
    b_ru, b_kk = _svc(services, b.service)
    if wrong_order:
        advice_ru = ("Сначала замените сети, потом кладите асфальт: на этом участке раскопка и асфальт идут в одни "
                     f"и те же дни ({a_ru}, {b_ru}). Договоритесь о порядке — сначала сети.")
        advice_kk = ("Алдымен желілерді ауыстырыңыз, содан кейін асфальт төсеңіз: бұл учаскеде қазу мен асфальт "
                     f"бір уақытта жоспарланған ({a_kk}, {b_kk}). Ретін келісіңіз — алдымен желілер.")
    else:
        advice_ru = (f"Совместите работы на этом участке: одно перекрытие и общий график для двух служб "
                     f"({a_ru}, {b_ru}) вместо двух отдельных.")
        advice_kk = (f"Осы учаскедегі жұмыстарды біріктіріңіз: екі қызметке бір жабу және ортақ кесте "
                     f"({a_kk}, {b_kk}).")
    first, second = sorted([a, b], key=lambda w: (w.start, w.id))
    extra = {"overlap_from": ov[0].isoformat(), "overlap_to": ov[1].isoformat(), "overlap_days": days,
             "first": first.id, "second": second.id, "when_from": min(a.start, b.start).isoformat(),
             "when_to": max(a.end, b.end).isoformat()}
    return _make("same_segment_overlap", a, b, severity, shared, extra, (advice_ru, advice_kk), g)


def _parallel(a: BoundWork, b: BoundWork, reach: dict[str, float], g: StreetGraph, services: dict) -> dict | None:
    """Перекрытия на параллельных улицах одного коридора в одни и те же дни."""
    ov = _overlap(a, b)
    if not ov or a.axis is None or b.axis is None:
        return None
    if set(a.edge_ids) & set(b.edge_ids) or a.nodes & b.nodes:
        return None  # одна улица или продолжение — это не «параллельные улицы»
    if a.street_ru and a.street_ru == b.street_ru:
        return None
    if _angle_diff(a.axis, b.axis) > PARALLEL_MAX_ANGLE_DEG:
        return None
    graph_m = min((reach[n] for n in b.nodes if n in reach), default=None)
    if graph_m is None or graph_m > CORRIDOR_GRAPH_M:
        return None
    along, apart = _side_by_side(a, b)
    if along < PARALLEL_MIN_SIDE_BY_SIDE_M or apart < PARALLEL_MIN_APART_M:
        return None
    days = (ov[1] - ov[0]).days + 1
    severity = "high" if days >= LONG_OVERLAP_DAYS else "medium"
    street_ru, street_kk = _street_pair(a, b)
    on_ru = f" ({street_ru})" if street_ru else ""
    on_kk = f" ({street_kk})" if street_kk else ""
    advice_ru = (f"Не перекрывайте параллельные улицы одновременно{on_ru}: разнесите перекрытия по времени, "
                 f"чтобы остался объезд.")
    advice_kk = (f"Қатар көшелерді бір уақытта жаппаңыз{on_kk}: айналма жол қалуы үшін жабуларды әр уақытқа "
                 f"бөліңіз.")
    first, second = sorted([a, b], key=lambda w: (w.start, w.id))
    extra = {"overlap_from": ov[0].isoformat(), "overlap_to": ov[1].isoformat(), "overlap_days": days,
             "graph_m": round(graph_m, 1), "angle_deg": round(_angle_diff(a.axis, b.axis), 1),
             "first": first.id, "second": second.id, "when_from": min(a.start, b.start).isoformat(),
             "when_to": max(a.end, b.end).isoformat()}
    segments = sorted(set(a.edge_ids) | set(b.edge_ids))
    return _make("parallel_closures", a, b, severity, segments, extra, (advice_ru, advice_kk), g)


def find_conflicts(bound: Sequence[BoundWork], graph: StreetGraph | None = None) -> list[dict]:
    """Все конфликты между привязанными работами (примерные места и отменённые не участвуют)."""
    g = graph or get_graph()
    services = _service_names()
    usable = [w for w in bound if not w.approximate and w.start and w.end and (w.status or "") not in CANCELLED]
    usable.sort(key=lambda w: w.id)
    out: dict[str, dict] = {}

    def keep(c):
        if c and c["id"] not in out:
            out[c["id"]] = c

    surfaces = [w for w in usable if w.kind in SURFACE_KINDS]
    digs = [w for w in usable if w.kind in DIG_KINDS]
    for s in surfaces:
        for d in digs:
            if s.id != d.id:
                keep(_dig_after_surface(s, d, g, services))
    for i, a in enumerate(usable):
        for b in usable[i + 1:]:
            keep(_same_segment(a, b, g, services))
    closures = [w for w in usable if w.kind in CLOSURE_KINDS]
    for i, a in enumerate(closures):
        rest = closures[i + 1:]
        if not rest:
            continue
        reach = _graph_reach(g, a.nodes, CORRIDOR_GRAPH_M)
        for b in rest:
            keep(_parallel(a, b, reach, g, services))
    return sorted(out.values(), key=lambda c: (SEVERITY_ORDER[c["severity"]], KIND_ORDER[c["kind"]],
                                               c.get("when_from") or "", c["id"]))


# ------------------------------------------------------------------ кэш привязки
_bind_lock = threading.Lock()
_bind_cache: dict[str, BoundWork] = {}
BIND_CACHE_MAX = 4000


def _fingerprint(record: dict) -> str:
    keys = ("id", "segments", "street", "from", "to", "geometry", "point", "kind", "work_kind", "service", "starts_on",
            "ends_on", "start", "end", "planned_end", "forecast_end", "schedule", "status", "district", "source", "demo",
            "title_ru", "title_kk", "title", "street_ru", "street_kk", "source_ref", "source_name", "type")
    raw = json.dumps({k: record.get(k) for k in keys}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def bind_all(records: Iterable[dict], graph: StreetGraph | None = None) -> list[BoundWork]:
    """Привязка списка работ с кэшем процесса (повторный запрос календаря — без пересчёта форм)."""
    g = graph or get_graph()
    out = []
    for record in records:
        if not isinstance(record, dict) or not record.get("id"):
            continue
        key = f"{id(g)}:{_fingerprint(record)}"
        with _bind_lock:
            w = _bind_cache.get(key)
        if w is None:
            w = bind_work(record, g)
            with _bind_lock:
                if len(_bind_cache) >= BIND_CACHE_MAX:
                    _bind_cache.clear()
                _bind_cache[key] = w
        out.append(w)
        if len(out) >= MAX_WORKS:
            break
    return out
