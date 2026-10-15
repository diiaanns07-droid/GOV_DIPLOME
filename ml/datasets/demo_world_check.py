"""Проверка демо-мира (R02, раунд 15): форматы, id, цели, согласованность чисел, приватность, пометка demo.

    python3 -m ml.datasets.demo_world_check                       # world_v1.json и world_v1.sample.json
    python3 -m ml.datasets.demo_world_check --world путь.json     # любой файл мира
    python3 -m ml.datasets.demo_world_check --no-geo              # без карты R12 (быстро; цели не сверяются)

Код выхода 0 — ошибок нет (предупреждения можно). Что проверяется (prompts/R02.txt, задача 4):
  1. форматы CONTRACT §5 (раунд 15) и SCHEMA.md: обязательные поля, перечисления, относительное время;
  2. уникальные id и правила id (шлюз CIVIC_ID, жалоба R09 ^c-…);
  3. цели существуют: объекты, участки, дворы, ячейки — у карты R12 (engine.civic_geo.target_geometry), участки работ —
     рёбра графа; ссылки между записями (сцены, конфликты → работы, инициатива → двор, поручение → жалоба/работа);
  4. числа согласованы: «Я тоже» = длина metoo_times, люди у цели = жалобы + «Я тоже» (сверка с картой R07),
     статус = последний шаг истории, совместная жалоба «исправлена» только когда все части done, даты по порядку;
  5. в текстах нет телефонов, ИИН, e-mail, номеров квартир; у всех записей demo: true (кроме работ source: real).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime

from ml.datasets import demo_world_io as wio

CIVIC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")
COMPLAINT_ID = re.compile(r"^c-[A-Za-z0-9]{6,40}\Z")
SEGMENT_ID = re.compile(r"^osm-w[0-9]{1,15}-[0-9]{1,6}\Z")
TARGET_ID = {"object": re.compile(r"^osm-(node|way|relation)-[0-9]{1,15}\Z"), "segment": SEGMENT_ID,
             "area": re.compile(r"^(yard|cell)-[A-Za-z0-9_-]{1,60}\Z")}
DISTRICTS = {"nura", "esil", "almaty", "saryarka", "baikonur", "saraishyk"}
SERVICES = {"road", "traffic", "street_cleaning", "transport", "lighting", "landscaping", "greenery", "waste",
            "utilities", "heating", "water", "power", "gas", "housing", "ecology", "emergency", "police", "animals",
            "parking", "akimat"}
STATUSES = ("new", "accepted", "in_progress", "fixed", "rejected")
PART_STATUSES = {"new", "accepted", "in_progress", "done"}
WORK_KINDS = {"dig", "surface", "closure", "landscape", "lighting", "other"}
WORK_STATUSES = {"planned", "in_progress", "done"}
UTILITIES = {"water", "heating", "power", "gas", "road_closure"}
CONFLICT_KINDS = {"dig_after_surface", "parallel_closures", "same_segment_overlap"}
INITIATIVE_KINDS = {"cleanup", "greening", "snow", "repair", "help", "other"}
INITIATIVE_STATUSES = {"on_review", "published", "done", "cancelled", "hidden"}
INCIDENT_KINDS = {"blizzard", "heat_outage", "water_outage", "flood", "other"}
IDEA_STATUSES = {"review", "voting", "checking", "project", "rejected", "hidden"}
ORDER_STATUSES = {"todo", "in_progress", "done"}
LANGS = {"ru", "kk", "mixed"}

# Личные данные в текстах (CONTRACT §5, §10): телефоны, ИИН (12 цифр), e-mail, номер квартиры.
PII = (
    ("телефон", re.compile(r"(?<!\d)(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)")),
    ("ИИН", re.compile(r"(?<!\d)\d{12}(?!\d)")),
    ("e-mail", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("квартира", re.compile(r"(?i)\b(кв\.?|квартира|пәтер)\s*№?\s*\d+")),
    ("длинное число", re.compile(r"(?<!\d)\d{7,}(?!\d)")),
)
TEXT_FIELDS = {"text", "title", "title_ru", "title_kk", "description_ru", "description_kk", "note", "reason",
               "text_ru", "text_kk", "what_done", "next_step", "answer_ru", "answer_kk", "advice_ru", "advice_kk",
               "problem_ru", "problem_kk", "blocker_ru", "blocker_kk", "decision_ru", "decision_kk",
               "temp_measure_ru", "temp_measure_kk", "reason_ru", "reason_kk", "can_improve_ru", "can_improve_kk",
               "zone_ru", "zone_kk", "display_name", "ru", "kk"}


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")

    def ok(self) -> bool:
        return not self.errors


# ---------------------------------------------------------------- время
def _hours(value) -> float | None:
    """Относительное время -> часы НАЗАД (будущее — отрицательное). Даты и сезоны — None (сравниваются отдельно)."""
    if not wio.is_reltime(value):
        return None
    (key, inner), = value.items()
    if key == "ago_hours":
        return float(inner)
    if key == "in_hours":
        return -float(inner)
    if key == "ago_days":
        return float(inner) * 24
    if key == "in_days":
        return -float(inner) * 24
    return None  # дата, сезон, «ближайшая суббота», «день + время» — сравниваются отдельно


def _order_bad(start, end) -> bool:
    """Конец раньше начала? Для «ближайшего дня недели» сравниваем (день, час, минута) — одно событие в одну неделю."""
    a, b = _hours(start), _hours(end)
    if a is not None and b is not None:
        return b > a + 1e-9
    if wio.is_reltime(start) and wio.is_reltime(end) and "next_weekday" in start and "next_weekday" in end:
        s, e = start["next_weekday"], end["next_weekday"]
        return (e["weekday"], e["hour"], e["minute"]) < (s["weekday"], s["hour"], s["minute"])
    if wio.is_reltime(start) and "next_weekday" in start and b is not None:
        return b >= 0  # начало — в будущем, конец уже прошёл
    if wio.is_reltime(start) and wio.is_reltime(end) and "day_at" in start and "day_at" in end:
        s, e = start["day_at"], end["day_at"]
        return (e["day"], e["hour"], e["minute"]) < (s["day"], s["hour"], s["minute"])
    return False


def _check_time(rep: Report, where: str, value, *, allow_future: bool = True, allow_date: bool = False) -> None:
    if not wio.is_reltime(value):
        rep.err(where, f"время должно быть объектом относительного времени (SCHEMA §1), а не {value!r}")
        return
    key = next(iter(value))
    if key in ("day", "season") and not allow_date:
        rep.err(where, "здесь нужно мгновение, а не дата")
    if key in ("ago_hours", "ago_days") and next(iter(value.values())) < 0:
        rep.err(where, "«назад» не может быть отрицательным")
    if not allow_future and (key in ("in_hours", "in_days", "next_weekday")
                             or (key == "day_at" and value["day_at"]["day"] > 0)):
        rep.err(where, "время в будущем там, где событие уже было")


# ---------------------------------------------------------------- приватность и пометка demo
def _walk_texts(obj, path=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            sub = f"{path}.{key}" if path else key
            if isinstance(value, str) and key in TEXT_FIELDS:
                yield sub, value
            else:
                yield from _walk_texts(value, sub)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from _walk_texts(value, f"{path}[{i}]")


def check_private(rep: Report, world: dict) -> None:
    for key in ("complaints", "works", "planned_conflicts", "ideas", "initiatives", "incidents", "meetings",
                "questions", "yards", "events"):
        for item in world.get(key, []):
            for path, text in _walk_texts(item):
                for name, rx in PII:
                    if rx.search(text):
                        rep.err(f"{key}/{item.get('id')}/{path}", f"похоже на личные данные ({name}): {text[:80]!r}")
            if item.get("source") == "real":
                if item.get("demo"):
                    rep.err(f"{key}/{item.get('id')}", "реальная запись (source: real) не может быть demo")
            elif item.get("demo") is not True:
                rep.err(f"{key}/{item.get('id')}", "нет demo: true (синтетика должна быть помечена)")
            for forbidden in ("device", "device_id", "device_hash", "author_device", "phone", "email", "iin"):
                if forbidden in item:
                    rep.err(f"{key}/{item.get('id')}", f"поле {forbidden} не должно быть в мире")
            # П1 (AMENDMENTS.md): в демо-мире фото нет — только текст; картинки не выдумываются.
            photos = ((item.get("resolution") or {}).get("photos_after") or []) + \
                ((item.get("report") or {}).get("photo_ids") or []) + list(item.get("photo_ids") or [])
            if photos:
                rep.err(f"{key}/{item.get('id')}", "в демо-мире не должно быть фото (поправка П1): только текст")


# ---------------------------------------------------------------- id
def check_ids(rep: Report, world: dict) -> dict[str, set]:
    ids: dict[str, set] = {}
    prefixes = {"complaints": None, "works": "w-", "planned_conflicts": "cf-", "ideas": "idea-", "initiatives": "i-",
                "incidents": "inc-", "meetings": "m-", "questions": "q-", "yards": "yard-", "events": "ev-"}
    for key, prefix in prefixes.items():
        seen = Counter(item.get("id") for item in world.get(key, []))
        for item_id, n in seen.items():
            if n > 1:
                rep.err(f"{key}/{item_id}", f"id повторяется {n} раза")
            if not isinstance(item_id, str) or not CIVIC_ID.match(item_id):
                rep.err(f"{key}/{item_id}", "id не проходит правило шлюза CIVIC_ID")
            elif prefix and not item_id.startswith(prefix):
                rep.err(f"{key}/{item_id}", f"id должен начинаться с {prefix}")
        ids[key] = set(seen)
    for item_id in ids.get("complaints", ()):
        if not COMPLAINT_ID.match(str(item_id)):
            rep.err(f"complaints/{item_id}", "id жалобы не проходит правило R09 ^c-[A-Za-z0-9]{6,40}")
    return ids


# ---------------------------------------------------------------- цели
class Geo:
    """Цели и рёбра — у карты R12 (только чтение). Без карты (--no-geo) проверяется лишь вид id."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._cache: dict = {}
        self.graph = None
        if enabled:
            from engine.civic_geo import target_geometry
            from engine.civic_geo.graph import get_graph
            self._lookup = target_geometry
            self.graph = get_graph()

    def target(self, kind: str, tid: str):
        if not self.enabled:
            return True
        key = (kind, tid)
        if key not in self._cache:
            self._cache[key] = self._lookup({"kind": kind, "id": tid})
        return self._cache[key]

    def edge(self, tid: str) -> bool:
        return True if not self.enabled else tid in self.graph.by_id


def check_target(rep: Report, geo: Geo, where: str, target, *, kinds=("object", "segment", "area")) -> None:
    if not isinstance(target, dict):
        rep.err(where, "нет цели {kind, id}")
        return
    kind, tid = target.get("kind"), target.get("id")
    if kind not in kinds or not isinstance(tid, str) or not TARGET_ID[kind].match(tid):
        rep.err(where, f"цель неверного вида: {target}")
        return
    found = geo.target(kind, tid)
    if not found:
        rep.err(where, f"цель неизвестна карте R12: {tid}")
        return
    if geo.enabled and isinstance(found, dict) and target.get("label_ru") and found.get("label_ru") != target["label_ru"]:
        rep.warn(where, f"подпись цели отличается от карты R12: {target['label_ru']!r} ≠ {found.get('label_ru')!r}")


# ---------------------------------------------------------------- жалобы
def check_complaints(rep: Report, world: dict, geo: Geo, categories: dict) -> None:
    services_rules = None
    try:
        from ui.civic_feedback.v2 import lifecycle
        services_rules = lifecycle.default_service
    except Exception:  # noqa: BLE001 — модуль R09 не обязателен для проверки формы
        rep.warn("complaints", "модуль R09 не загрузился: служба по умолчанию не сверяется")
    for c in world.get("complaints", []):
        where = f"complaints/{c.get('id')}"
        for field in ("id", "schema", "created_at", "text", "lang", "category", "point", "target", "district",
                      "status", "status_history", "metoo", "metoo_times", "duplicate_of", "demo", "service"):
            if field not in c:
                rep.err(where, f"нет поля {field}")
        if c.get("schema") != "civic-complaint-v2":
            rep.err(where, "schema должна быть civic-complaint-v2")
        if c.get("category") not in categories:
            rep.err(where, f"категория не из categories_v2: {c.get('category')}")
        elif c.get("subtopic") is not None and c["subtopic"] not in categories[c["category"]]:
            rep.err(where, f"уточнение {c['subtopic']} не из категории {c['category']}")
        if c.get("lang") not in LANGS:
            rep.err(where, f"язык {c.get('lang')}")
        if c.get("district") not in DISTRICTS:
            rep.err(where, f"район {c.get('district')}")
        if c.get("service") not in SERVICES:
            rep.err(where, f"служба {c.get('service')} не из CONTRACT §3")
        if not isinstance(c.get("text"), str) or not 3 <= len(c["text"]) <= 2000:
            rep.err(where, "текст 3–2000 символов")
        point = c.get("point")
        if not (isinstance(point, list) and len(point) == 2 and 70.9 <= point[0] <= 72.0 and 50.8 <= point[1] <= 51.5):
            rep.err(where, f"точка вне Астаны: {point}")
        check_target(rep, geo, where + "/target", c.get("target"))
        _check_time(rep, where + "/created_at", c.get("created_at"), allow_future=False)
        # история: первый шаг — new в момент подачи, шаги по времени, статус = последний шаг
        hist = c.get("status_history") or []
        if not hist or hist[0].get("status") != "new" or hist[0].get("at") != c.get("created_at"):
            rep.err(where, "история должна начинаться с «new» в момент подачи")
        prev = None
        for i, step in enumerate(hist):
            _check_time(rep, f"{where}/status_history[{i}]", step.get("at"), allow_future=False)
            if step.get("status") not in STATUSES:
                rep.err(where, f"неизвестный статус в истории: {step.get('status')}")
            h = _hours(step.get("at"))
            if prev is not None and h is not None and h > prev + 1e-9:
                rep.err(where, f"шаг истории [{i}] раньше предыдущего")
            prev = h if h is not None else prev
        if hist and hist[-1].get("status") != c.get("status"):
            rep.err(where, f"статус {c.get('status')} не равен последнему шагу истории {hist[-1].get('status')}")
        # «Я тоже»
        times = c.get("metoo_times") or []
        if c.get("metoo") != len(times):
            rep.err(where, f"metoo = {c.get('metoo')}, а времён «Я тоже» {len(times)}")
        created_h = _hours(c.get("created_at"))
        for i, t in enumerate(times):
            _check_time(rep, f"{where}/metoo_times[{i}]", t, allow_future=False)
            h = _hours(t)
            if created_h is not None and h is not None and h > created_h + 1e-9:
                rep.err(where, f"«Я тоже» [{i}] раньше самой жалобы")
        # службы
        if services_rules and c.get("category") in categories and not c.get("services"):
            want = services_rules(c.get("category"), c.get("subtopic"))
            if c.get("service") != want and not c.get("route_hint"):
                rep.warn(where, f"служба {c.get('service')} ≠ таблице R09/R08 ({want})")
        parts = c.get("services")
        if parts is not None:
            if not isinstance(parts, list) or len(parts) < 2:
                rep.err(where, "services — список из 2+ частей (совместная жалоба)")
            else:
                if parts[0].get("role") != "lead" or parts[0].get("service") != c.get("service"):
                    rep.err(where, "первая часть — ведущая служба (= поле service)")
                for p in parts:
                    if p.get("service") not in SERVICES or p.get("status") not in PART_STATUSES:
                        rep.err(where, f"часть службы неверна: {p}")
                    if p.get("role") not in ("lead", "partner"):
                        rep.err(where, f"роль части: {p.get('role')}")
                all_done = all(p.get("status") == "done" for p in parts)
                if c.get("status") == "fixed" and not all_done:
                    rep.err(where, "«исправлено», а не все части служб done (CONTRACT §5.1)")
                if all_done and c.get("status") not in ("fixed",) and not any(
                        h.get("reopened_by_residents") for h in hist):
                    rep.err(where, "все части done, а жалоба не исправлена")
        for h in c.get("handoffs") or []:
            if h.get("from") not in SERVICES or h.get("to") not in SERVICES or not h.get("reason"):
                rep.err(where, f"передача неверна: {h}")
            _check_time(rep, where + "/handoffs", h.get("at"), allow_future=False)
        hint = c.get("route_hint")
        if hint is not None and (not isinstance(hint.get("services"), list)
                                 or any(s not in SERVICES for s in hint["services"])):
            rep.err(where, f"route_hint неверен: {hint}")
        res = c.get("resolution")
        if res is not None:
            if res.get("state") not in ("reported", "verified", "reopened"):
                rep.err(where, f"resolution.state: {res.get('state')}")
            if res.get("state") == "verified" and c.get("status") != "fixed":
                rep.err(where, "«проверено жителями», а жалоба не исправлена")
            if res.get("state") == "reopened" and not any(h.get("reopened_by_residents") for h in hist):
                rep.err(where, "«вернули жители» без шага истории reopened_by_residents")
            for name in ("reported_at", "verified_at", "reopened_at"):
                if res.get(name) is not None:
                    _check_time(rep, f"{where}/resolution.{name}", res[name], allow_future=False)
        elif c.get("status") == "fixed":
            rep.warn(where, "исправлено без resolution (R09 создаёт её при «Исправлено»)")
        delay = ((c.get("passport") or {}).get("delay") or {})
        if delay.get("needs_decision") and len(delay.get("options") or []) != 2:
            rep.err(where, "«нужно решение акима» — ровно два варианта (R08)")


def check_heat_consistency(rep: Report, world: dict, now: datetime) -> dict:
    """Люди у цели на карте = жалобы + «Я тоже» (открытые, за период): общий счёт R07 = сумма по записям мира."""
    try:
        from ml.datasets.demo_world_expected import _with_r09_fields
        from ui.civic_heat.service import HeatService
    except Exception as exc:  # noqa: BLE001
        rep.warn("heat", f"карта R07 не загрузилась — сверка людей у целей пропущена ({exc})")
        return {}
    world_m = wio.materialize(world, now)
    records = _with_r09_fields(world_m["complaints"])
    heat = HeatService(source=lambda since: records, clock=lambda: now)
    data = heat.heat(days=14, now=now)
    edge = now.timestamp() - 14 * 86400
    expected: Counter = Counter()
    for r in records:
        if r["status"] not in ("new", "accepted", "in_progress"):
            continue
        moments = [datetime.fromisoformat(t).timestamp() for t in [r["created_at"]] + list(r.get("metoo_times") or [])]
        res = r.get("resolution") or {}
        if res.get("state") == "reopened" and res.get("reopened_at"):
            # правило R07: жители вернули — проблема есть сейчас, сообщения считаются с момента возврата
            back = datetime.fromisoformat(res["reopened_at"]).timestamp()
            moments = [max(t, back) for t in moments]
        n = sum(1 for t in moments if t >= edge)
        if n:
            expected[r["target"]["id"]] += n
    got = {it["target"]["id"]: it["count"] for it in data["items"] if it["state"] == "active"}
    diff = {tid: (expected.get(tid, 0), got.get(tid, 0)) for tid in set(expected) | set(got)
            if expected.get(tid, 0) != got.get(tid, 0)}
    if diff:
        sample = dict(list(sorted(diff.items()))[:5])
        rep.err("heat", f"люди у целей на карте R07 ≠ жалобы + «Я тоже» мира у {len(diff)} целей, например {sample}")
    return {"targets": len(got), "people": sum(got.values())}


# ---------------------------------------------------------------- работы и конфликты
def check_works(rep: Report, world: dict, geo: Geo) -> None:
    ids = {w.get("id") for w in world.get("works", [])}
    for w in world.get("works", []):
        where = f"works/{w.get('id')}"
        if w.get("district") not in DISTRICTS:
            rep.err(where, f"район {w.get('district')}")
        if w.get("service") not in SERVICES:
            rep.err(where, f"служба {w.get('service')}")
        if w.get("source") not in ("demo", "real"):
            rep.err(where, "source: demo | real")
        if w.get("type") == "outage":
            if w.get("utility") not in UTILITIES:
                rep.err(where, f"utility {w.get('utility')}")
            _check_time(rep, where + "/starts_at", w.get("starts_at"))
            _check_time(rep, where + "/ends_at", w.get("ends_at"))
            a, b = _hours(w.get("starts_at")), _hours(w.get("ends_at"))
            if a is not None and b is not None and b > a:
                rep.err(where, "конец отключения раньше начала")
            continue
        if w.get("type") != "work":
            rep.err(where, f"type: work | outage, а не {w.get('type')}")
        if w.get("kind") not in WORK_KINDS:
            rep.err(where, f"kind {w.get('kind')}")
        if w.get("status") not in WORK_STATUSES:
            rep.err(where, f"status {w.get('status')}")
        segs = w.get("segments") or []
        if not segs:
            rep.err(where, "работа без участков графа")
        for s in segs:
            if not SEGMENT_ID.match(str(s)) or not geo.edge(s):
                rep.err(where, f"участок {s} — не ребро графа R12")
        if geo.enabled and segs and w.get("geometry"):
            coords = w["geometry"].get("coordinates") or []
            if len(coords) != len(segs):
                rep.err(where, "форма работы не совпадает с числом участков")
        for name in ("starts_on", "ends_on"):
            value = w.get(name)
            if not wio.is_reltime(value) or next(iter(value)) not in ("day", "season"):
                rep.err(where, f"{name} — дата {{day}} или {{season}}")
        start, end = w.get("starts_on"), w.get("ends_on")
        if wio.is_reltime(start) and wio.is_reltime(end):
            ks, ke = next(iter(start)), next(iter(end))
            if ks == ke == "day":
                if end["day"] < start["day"]:
                    rep.err(where, "конец работ раньше начала")
                status = "done" if end["day"] < 0 else ("planned" if start["day"] > 0 else "in_progress")
                if w.get("status") != status and not (status == "in_progress" and start["day"] == 0):
                    rep.err(where, f"статус {w.get('status')} не совпадает с датами (ожидалось {status})")
            elif ks == ke == "season":
                if (end["season"]["month"], end["season"]["day"]) < (start["season"]["month"], start["season"]["day"]):
                    rep.err(where, "конец работ раньше начала")
                if w.get("status") != "planned":
                    rep.err(where, "работы следующего сезона — planned")
            else:
                rep.err(where, "начало и конец — в одной форме (оба day или оба season)")
    for cf in world.get("planned_conflicts", []):
        where = f"planned_conflicts/{cf.get('id')}"
        if cf.get("kind") not in CONFLICT_KINDS:
            rep.err(where, f"kind {cf.get('kind')}")
        if cf.get("severity") not in ("high", "medium"):
            rep.err(where, f"severity {cf.get('severity')}")
        works = [w for w in world.get("works", []) if w.get("id") in (cf.get("works") or [])]
        if len(works) != 2 or any(x not in ids for x in cf.get("works") or []):
            rep.err(where, "конфликт — две работы этого мира")
            continue
        shared = set(works[0]["segments"]) & set(works[1]["segments"])
        if cf.get("kind") in ("dig_after_surface", "same_segment_overlap"):
            if not set(cf.get("segments") or []) <= shared or not shared:
                rep.err(where, "участки конфликта должны быть общими у обеих работ")
        if cf.get("kind") == "dig_after_surface":
            kinds = {w["kind"] for w in works}
            if kinds != {"dig", "surface"}:
                rep.err(where, "«асфальт раньше сетей» — работы dig и surface")
        if not cf.get("advice_ru") or not cf.get("advice_kk"):
            rep.err(where, "нужен совет ru и kk")


# ---------------------------------------------------------------- остальное
def check_rest(rep: Report, world: dict, geo: Geo, ids: dict) -> None:
    yards = {y.get("id") for y in world.get("yards", [])}
    for y in world.get("yards", []):
        where = f"yards/{y.get('id')}"
        check_target(rep, geo, where, {"kind": "area", "id": y.get("id"), "label_ru": y.get("label_ru")}, kinds=("area",))
        if not str(y.get("id", "")).startswith("yard-"):
            rep.err(where, "двор — только yard-<id> (R12, OSM landuse=residential)")
        if not isinstance(y.get("members"), int) or y["members"] < 0:
            rep.err(where, "members — число")
        cap = y.get("captain")
        if cap is not None and (not isinstance(cap.get("display_name"), str) or " " in cap["display_name"].strip()):
            rep.err(where, "старший по двору — одно отображаемое имя")
    for i in world.get("initiatives", []):
        where = f"initiatives/{i.get('id')}"
        if i.get("kind") not in INITIATIVE_KINDS or i.get("status") not in INITIATIVE_STATUSES:
            rep.err(where, f"kind/status: {i.get('kind')}/{i.get('status')}")
        if i.get("lang") not in LANGS:
            rep.err(where, f"язык {i.get('lang')}")
        tgt = i.get("target") or {}
        if tgt.get("id") not in yards:
            rep.err(where, f"двор инициативы {tgt.get('id')} не из yards")
        check_target(rep, geo, where + "/target", tgt, kinds=("area",))
        _check_time(rep, where + "/starts_at", i.get("starts_at"))
        _check_time(rep, where + "/ends_at", i.get("ends_at"))
        a, b = _hours(i.get("starts_at")), _hours(i.get("ends_at"))
        if _order_bad(i.get("starts_at"), i.get("ends_at")):
            rep.err(where, "конец раньше начала")
        if i.get("status") == "done" and not i.get("report"):
            rep.err(where, "сделанная инициатива без отчёта")
        if i.get("status") in ("published", "on_review") and a is not None and a > 0 and b is not None and b > 0:
            rep.err(where, "опубликованная инициатива уже прошла — статус должен быть done/cancelled")
        if i.get("from_idea") and i["from_idea"] not in ids.get("ideas", set()):
            rep.err(where, f"from_idea {i['from_idea']} — нет такой идеи")
        if not isinstance(i.get("joined"), int) or i["joined"] < 0:
            rep.err(where, "joined — число")
        sup = i.get("support")
        if sup and sup.get("pickup_service") not in SERVICES | {None}:
            rep.err(where, f"служба вывоза {sup.get('pickup_service')}")
    for idea in world.get("ideas", []):
        where = f"ideas/{idea.get('id')}"
        if idea.get("status") not in IDEA_STATUSES:
            rep.err(where, f"status {idea.get('status')}")
        if idea.get("target"):
            check_target(rep, geo, where + "/target", idea["target"], kinds=("area",))
        if idea.get("to_initiative") and idea["to_initiative"] not in ids.get("initiatives", set()):
            rep.err(where, "to_initiative — нет такой инициативы")
        if idea.get("status") == "rejected" and not idea.get("reason_ru"):
            rep.warn(where, "отклонённая идея без причины")
    for inc in world.get("incidents", []):
        where = f"incidents/{inc.get('id')}"
        if inc.get("kind") not in INCIDENT_KINDS or inc.get("status") not in ("active", "closed"):
            rep.err(where, f"kind/status {inc.get('kind')}/{inc.get('status')}")
        zone = inc.get("zone") or {}
        if zone.get("kind") not in ("district", "targets", "polygon") or zone.get("district") not in DISTRICTS:
            rep.err(where, f"zone неверна: {zone}")
        for tid in zone.get("targets") or []:
            check_target(rep, geo, where + "/zone", {"kind": "area" if tid.startswith(("yard-", "cell-")) else "object",
                                                     "id": tid})
        for t in inc.get("tasks") or []:
            if t.get("service") not in SERVICES or t.get("status") not in ("todo", "doing", "done"):
                rep.err(where, f"задача неверна: {t}")
        if inc.get("status") == "closed" and not inc.get("result"):
            rep.err(where, "закрытый кризис без итога")
        if inc.get("event") and inc["event"] not in ids.get("events", set()):
            rep.err(where, f"событие {inc['event']} не из events")
    complaints, works = ids.get("complaints", set()), ids.get("works", set())
    questions = ids.get("questions", set())
    for m in world.get("meetings", []):
        where = f"meetings/{m.get('id')}"
        if m.get("district") not in DISTRICTS:
            rep.err(where, f"район {m.get('district')}")
        check_target(rep, geo, where + "/place", m.get("place"))
        for q in m.get("questions") or []:
            if q not in questions:
                rep.err(where, f"вопрос {q} не из questions")
        for o in m.get("orders") or []:
            if o.get("service") not in SERVICES or o.get("status") not in ORDER_STATUSES:
                rep.err(where, f"поручение неверно: {o}")
            link = o.get("link")
            if link and not ((link.get("kind") == "complaint" and link.get("id") in complaints)
                             or (link.get("kind") == "work" and link.get("id") in works)):
                rep.err(where, f"поручение ссылается на запись не из мира: {link}")
    for q in world.get("questions", []):
        where = f"questions/{q.get('id')}"
        if q.get("status") not in ("published", "pending") or q.get("lang") not in LANGS:
            rep.err(where, "status/lang")
        if q.get("meeting") and q["meeting"] not in ids.get("meetings", set()):
            rep.err(where, f"встреча {q['meeting']} не из meetings")
    for e in world.get("events", []):
        where = f"events/{e.get('id')}"
        if e.get("district") is not None and e["district"] not in DISTRICTS:
            rep.err(where, "район события")
        _check_time(rep, where + "/started_at", e.get("started_at"))
        if e.get("ended_at") is not None:
            _check_time(rep, where + "/ended_at", e.get("ended_at"))
            if _order_bad(e.get("started_at"), e.get("ended_at")):
                rep.err(where, "конец события раньше начала")


def check_scenes(rep: Report, world: dict, ids: dict) -> None:
    scenes = world.get("scenes") or {}
    for name in ("step2", "scene7", "scene8", "scene9"):
        if name not in scenes:
            rep.err("scenes", f"нет сцены {name}")
    every = set().union(*ids.values()) if ids else set()
    for name, scene in scenes.items():
        for key, value in scene.items():
            refs = value if isinstance(value, list) else [value]
            for ref in refs:
                if isinstance(ref, str) and re.match(r"^(c-|w-|cf-|i-|inc-|ev-|yard-|m-|q-|idea-)", ref) \
                        and ref not in every and key not in ("segments",):
                    rep.err(f"scenes/{name}/{key}", f"ссылка {ref} не найдена в мире")


def check_world(world: dict, *, geo: bool = True, now: datetime | None = None, heat: bool = True) -> Report:
    rep = Report()
    if world.get("schema") != wio.SCHEMA_ID:
        rep.err("schema", f"ожидалось {wio.SCHEMA_ID}")
    for key in ("complaints", "works", "planned_conflicts", "ideas", "initiatives", "yards", "incidents", "meetings",
                "questions", "events", "scenes"):
        if key not in world:
            rep.err("world", f"нет ключа {key}")
    if rep.errors:
        return rep
    counts = world.get("counts") or {}
    for key, n in counts.items():
        if key in world and len(world[key]) != n:
            rep.err("counts", f"{key}: заявлено {n}, на деле {len(world[key])}")
    cats = json.loads((wio.ROOT / "research" / "round-14" / "categories_v2.json").read_text("utf-8"))
    categories = {c["id"]: {s["id"] for s in c.get("subtopics", [])} for c in cats["categories"]}
    g = Geo(geo)
    ids = check_ids(rep, world)
    check_complaints(rep, world, g, categories)
    check_works(rep, world, g)
    check_rest(rep, world, g, ids)
    check_scenes(rep, world, ids)
    check_private(rep, world)
    if heat and not world.get("sample"):
        check_heat_consistency(rep, world, wio.astana_now(now))
    return rep


def check_sample(rep: Report, sample: dict, world: dict) -> None:
    """Образец — подмножество мира: те же записи с теми же полями."""
    for key in ("complaints", "works", "ideas", "initiatives", "yards", "incidents", "meetings", "questions",
                "planned_conflicts"):
        full = {x["id"]: x for x in world.get(key, [])}
        for item in sample.get(key, []):
            if full.get(item.get("id")) != item:
                rep.err(f"sample/{key}/{item.get('id')}", "запись образца не совпадает с полным миром")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Проверка демо-мира R02")
    ap.add_argument("--world", default=None)
    ap.add_argument("--no-geo", action="store_true", help="не сверять цели с картой R12")
    ap.add_argument("--no-heat", action="store_true", help="не сверять людей у целей с картой R07")
    ap.add_argument("--now", default=None, help="момент засева для сверки карты (ISO), по умолчанию сейчас")
    args = ap.parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else None
    paths = [args.world] if args.world else [str(wio.WORLD_PATH), str(wio.SAMPLE_PATH)]
    worst = 0
    world_full = None
    for path in paths:
        world = wio.load_world(path)
        rep = check_world(world, geo=not args.no_geo, now=now, heat=not args.no_heat)
        if world.get("sample") and world_full is not None:
            check_sample(rep, world, world_full)
        if not world.get("sample"):
            world_full = world
        print(f"{path}: ошибок {len(rep.errors)}, предупреждений {len(rep.warnings)}")
        for line in rep.errors[:40]:
            print("  ОШИБКА", line)
        for line in rep.warnings[:15]:
            print("  внимание", line)
        worst = max(worst, 1 if rep.errors else 0)
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
