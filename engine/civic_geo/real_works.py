"""Реальные работы района Нура (LOCAL-5): data/civic/astana/nura-real/records.csv → работы v2 (source: real) с участками.

Файл собирают на ноутбуке владельца (ChatGPT с поиском, только официальные источники и крупные СМИ — research/round-14/
LOCAL_TASKS.md, LOCAL-5); в облаке его нет. Колонки — любые из распознаваемых (ru/en): название, тип, адрес или улицы,
начало, окончание, перенос, статус, ссылка, дата публикации, цитата. Ничего не придумываем:
  - нет даты — работа «без дат» (в календаре не рисуется, считается в покрытии);
  - «II квартал 2025» — границы квартала с пометкой dates_approx (так и написано в источнике);
  - улица и два пересечения («от ул. … до ул. …») → участок этой улицы между перекрёстками (рёбра графа, форма OSM);
  - только улица → «примерное место» (середина улицы в районе), без уверенной линии (CONTRACT §8);
  - нет улицы → без места.
Покрытие (coverage): сколько записей легло на участок, сколько — примерным местом, сколько без места и без дат.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import threading
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from . import geo
from .graph import StreetGraph, get_graph
from .paths import ROOT
from .works import KINDS, district_of_point, parse_day, segment_on_street

REAL_PATH = ROOT / "data" / "civic" / "astana" / "nura-real" / "records.csv"
DISTRICT = "nura"
MAX_ROWS = 500

# Заголовки CSV → поле (по началу слова, без регистра). Первое совпадение выигрывает.
HEADERS = (
    ("title", ("название", "наименование", "работа", "title", "name", "объект")),
    ("type", ("тип", "вид", "type", "kind", "категория")),
    ("place", ("адрес", "улиц", "место", "участок", "address", "street", "location")),
    ("start", ("начало", "старт", "дата начала", "start", "begin")),
    ("end", ("окончан", "плановое окончание", "плановый срок", "срок", "конец", "end", "finish", "deadline")),
    ("postponed", ("перенос", "новый срок", "перенесен", "postpon", "new deadline")),
    ("status", ("статус", "состояние", "status")),
    ("url", ("ссылка", "источник", "url", "link", "source")),
    ("published", ("дата публикации", "опубликован", "publication", "published")),
    ("quote", ("цитата", "подтвержден", "quote", "evidence")),
)
KIND_WORDS = (
    ("closure", ("перекрыт", "ограничен движ", "закрыт проезд", "closure")),
    ("dig", ("водопровод", "канализац", "теплосет", "теплотрасс", "газопровод", "кабел", "сети", "инженерн", "раскоп",
             "трубопровод", "ливнев")),
    ("surface", ("асфальт", "покрыт", "дорог", "тротуар", "ямочн", "проезж")),
    ("lighting", ("освещен", "фонар", "светильник")),
    ("landscape", ("благоустр", "сквер", "парк", "озелен", "двор", "детск", "спортивн", "площадк")),
)
SERVICE_WORDS = (
    ("water", ("водопровод", "канализац", "водоотвед", "ливнев")),
    ("heating", ("теплосет", "теплотрасс", "отоплен", "тепловых сетей")),
    ("gas", ("газопровод", "газоснабж")),
    ("power", ("электросет", "кабел", "подстанц", "лэп")),
    ("lighting", ("освещен", "фонар", "светильник")),
    ("greenery", ("озелен", "посадк", "деревь")),
    ("landscaping", ("благоустр", "сквер", "парк", "детск", "двор")),
    ("road", ("асфальт", "дорог", "тротуар", "покрыт", "ямочн", "проезж")),
)
STATUS_WORDS = (
    ("done", ("заверш", "выполнен", "сдан", "открыт", "закончен", "done", "completed")),
    ("in_progress", ("идут", "ведутся", "в работе", "в процессе", "начат", "in progress", "ongoing")),
    ("planned", ("план", "запланир", "начнется", "начнётся", "будет", "предстоит", "planned")),
    ("cancelled", ("отменен", "отменён", "cancel")),
)
MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8, "сентябр": 9,
          "октябр": 10, "ноябр": 11, "декабр": 12}
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "1": 1, "2": 2, "3": 3, "4": 4}
TYPE_WORDS = ("улица", "ул", "проспект", "пр", "пр-т", "просп", "шоссе", "ш", "переулок", "пер", "бульвар", "б-р",
              "площадь", "пл", "набережная", "наб", "көшесі", "даңғылы", "тас", "жолы", "street", "avenue", "st", "ave")


def _norm(text) -> str:
    t = str(text or "").lower().replace("ё", "е")
    t = re.sub(r"[«»\"'`()\[\],;:]", " ", t)
    return " ".join(t.split())


def _core(name: str) -> str:
    """«улица Кайыма Мухамедханова» → «кайыма мухамедханова» (без слова-типа и точек)."""
    words = [w.strip(".") for w in _norm(name).split()]
    return " ".join(w for w in words if w and w not in TYPE_WORDS)


class StreetIndex:
    """Названия улиц района из графа: ядро имени → (полное имя, рёбра). Для поиска улиц в тексте адреса."""

    def __init__(self, graph: StreetGraph, district: str = DISTRICT):
        self.graph = graph
        self.by_core: dict[str, tuple[str, list]] = {}
        for e in graph.edges:
            if not e.name or e.group not in ("road", "service", "unknown"):
                continue
            mid = e.geometry[len(e.geometry) // 2]
            if district and district_of_point(mid) != district:
                continue
            core = _core(e.name)
            if len(core) < 3:
                continue
            entry = self.by_core.setdefault(core, (e.name, []))
            entry[1].append(e)
        # Длинные ядра раньше коротких: «толе би» не должно съесть «кабанбай батыра» и т. п.
        self.cores = sorted(self.by_core, key=lambda c: (-len(c), c))

    def find(self, text: str) -> list[tuple[int, str]]:
        """Улицы в тексте по порядку упоминания: [(позиция, полное имя)] без повторов и без вложенных совпадений."""
        t = " " + _core(text) + " "
        taken: list[tuple[int, int]] = []
        found = []
        for core in self.cores:
            start = 0
            while True:
                i = t.find(" " + core + " ", start)
                if i < 0:
                    break
                span = (i, i + len(core) + 2)
                if not any(a < span[1] and span[0] < b for a, b in taken):
                    taken.append(span)
                    found.append((i, self.by_core[core][0]))
                start = i + 1
        found.sort()
        out, seen = [], set()
        for pos, name in found:
            if name not in seen:
                seen.add(name)
                out.append((pos, name))
        return out

    def crossing(self, main: str, other: str) -> list[float] | None:
        """Точка пересечения двух улиц: общий узел их рёбер (если улицы пересекаются в районе)."""
        a = self.by_core.get(_core(main))
        b = self.by_core.get(_core(other))
        if not a or not b:
            return None
        nodes_a = {n for e in a[1] for n in (e.a, e.b)}
        common = sorted(n for e in b[1] for n in (e.a, e.b) if n in nodes_a)
        if not common:
            return None
        return list(self.graph.nodes[common[0]])

    def middle(self, main: str) -> list[float] | None:
        """Середина улицы в районе — для «примерного места» (только точка, без линии)."""
        entry = self.by_core.get(_core(main))
        if not entry:
            return None
        edges = sorted(entry[1], key=lambda e: e.id)
        mid = edges[len(edges) // 2]
        return geo.round_coord(mid.geometry[len(mid.geometry) // 2])


_index_lock = threading.Lock()
_indexes: dict[int, StreetIndex] = {}


def street_index(graph: StreetGraph | None = None) -> StreetIndex:
    g = graph or get_graph()
    with _index_lock:
        idx = _indexes.get(id(g))
        if idx is None:
            idx = _indexes[id(g)] = StreetIndex(g)
        return idx


# ------------------------------------------------------------------ разбор полей
def map_headers(header: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, raw in enumerate(header):
        h = _norm(raw)
        for field, keys in HEADERS:
            if field not in out and any(h.startswith(k) or k in h for k in keys):
                out[field] = i
                break
    return out


def _words(text: str, table) -> str | None:
    t = _norm(text)
    for value, keys in table:
        if any(k in t for k in keys):
            return value
    return None


def parse_date_text(text, end: bool = False) -> tuple[date | None, bool]:
    """(дата, примерная?) из «2025-05-01», «01.05.2025», «1 мая 2025», «май 2025», «II квартал 2025». Иначе (None, False)."""
    t = _norm(text)
    if not t:
        return None, False
    d = parse_day(t[:10]) if re.match(r"^\d{4}-\d{2}-\d{2}", t) else None
    if d:
        return d, False
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})", t)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))), False
        except ValueError:
            return None, False
    m = re.match(r"^(\d{1,2})\s+([а-я]+)\s+(\d{4})", t)
    if m:
        month = next((v for k, v in MONTHS.items() if m.group(2).startswith(k)), None)
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(1))), False
            except ValueError:
                return None, False
    m = re.match(r"^([а-я]+)\s+(\d{4})", t)
    if m:
        month = next((v for k, v in MONTHS.items() if m.group(1).startswith(k)), None)
        if month:
            first = date(int(m.group(2)), month, 1)
            last = (date(first.year + (month == 12), month % 12 + 1, 1) - timedelta(days=1))
            return (last if end else first), True
    m = re.match(r"^(i{1,3}|iv|[1-4])\s*(?:-?й\s*)?кв\w*\s+(\d{4})", t)
    if m and m.group(1) in ROMAN:
        q, year = ROMAN[m.group(1)], int(m.group(2))
        first = date(year, 3 * q - 2, 1)
        last = date(year + (q == 4), (3 * q) % 12 + 1, 1) - timedelta(days=1)
        return (last if end else first), True
    return None, False


def _safe_url(url: str) -> str | None:
    u = str(url or "").strip()
    try:
        parts = urlsplit(u)
    except ValueError:
        return None
    return u if parts.scheme in ("http", "https") and parts.netloc and len(u) <= 500 else None


def record_from_row(row: dict, idx: StreetIndex, graph: StreetGraph) -> dict:
    """Строка CSV → работа v2 (source: real). Место — по правилам в начале модуля, без догадок."""
    title = (row.get("title") or "").strip()
    place = (row.get("place") or "").strip()
    text = " ".join(x for x in (title, row.get("type") or "", place) if x)
    kind = _words(text, KIND_WORDS) or "other"
    service = _words(text, SERVICE_WORDS)
    start, a1 = parse_date_text(row.get("start"))
    end, a2 = parse_date_text(row.get("end"), end=True)
    moved, a3 = parse_date_text(row.get("postponed"), end=True)
    url = _safe_url(row.get("url"))
    rec = {
        "id": "w-real-" + hashlib.sha1("|".join([title, place, row.get("start") or ""]).encode("utf-8")).hexdigest()[:10],
        "title_ru": title or None, "kind": kind if kind in KINDS else "other", "service": service,
        "starts_on": start.isoformat() if start else None,
        "ends_on": (moved or end).isoformat() if (moved or end) else None,
        "status": _words(row.get("status") or "", STATUS_WORDS),
        "source": "real", "demo": False, "district": DISTRICT,
        "source_ref": url, "source_name": urlsplit(url).netloc if url else None,
        "published_on": (parse_date_text(row.get("published"))[0] or None),
        "place_text": place or None,
    }
    if rec["published_on"]:
        rec["published_on"] = rec["published_on"].isoformat()
    if moved and end and moved > end:
        rec["delayed"] = True
    if a1 or a2 or a3:
        rec["dates_approx"] = True
    streets = idx.find(place or title)
    rec["place_bind"] = "none"
    if streets:
        main = streets[0][1]
        cross = [name for _, name in streets[1:] if name != main]
        points = [p for p in (idx.crossing(main, c) for c in cross[:2]) if p]
        if len(points) == 2 and geo.haversine_m(points[0], points[1]) > 20:
            try:
                seg = segment_on_street(main, points[0], points[1], graph)
                rec["segments"] = seg["edge_ids"]
                rec["street_ru"] = main
                rec["place_bind"] = "street_between"
            except Exception:
                rec["place_bind"] = "street_only"
        else:
            rec["place_bind"] = "street_only"
        if rec["place_bind"] == "street_only":
            rec["point"] = idx.middle(main)
            rec["street_ru"] = main
    return rec


def load_real_works(path: Path = REAL_PATH, graph: StreetGraph | None = None) -> tuple[list[dict], dict]:
    """(работы, покрытие). Нет файла — ([], {"status": "NOT_RUN", "reason": …})."""
    if not path.is_file():
        return [], {"status": "NOT_RUN", "reason": f"нет файла {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}"}
    g = graph or get_graph()
    idx = street_index(g)
    raw = path.read_text("utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(raw), dialect))
    if not rows:
        return [], {"status": "EMPTY", "total": 0}
    head = map_headers(rows[0])
    works = []
    for r in rows[1:MAX_ROWS + 1]:
        if not any(c.strip() for c in r):
            continue
        row = {f: (r[i] if i < len(r) else "") for f, i in head.items()}
        works.append(record_from_row(row, idx, g))
    cov = {
        "status": "OK", "total": len(works),
        "on_segments": sum(1 for w in works if w.get("segments")),
        "approximate": sum(1 for w in works if w["place_bind"] == "street_only"),
        "no_place": sum(1 for w in works if w["place_bind"] == "none"),
        "no_dates": sum(1 for w in works if not w.get("starts_on")),
        "dates_approx": sum(1 for w in works if w.get("dates_approx")),
        "with_source": sum(1 for w in works if w.get("source_ref")),
        "columns": sorted(head),
    }
    return works, cov
