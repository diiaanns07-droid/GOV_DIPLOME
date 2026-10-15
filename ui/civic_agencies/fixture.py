"""Фикстура R17: синтетические жалобы в формате CONTRACT §5.1 — пока R09 не поставил части служб и передачи.

Только для демо-сборки (CIVIC_DEMO=1) и тестов. Все записи demo: true — на экране слово «Пример».
Генератор детерминированный (seed 17): тот же момент «сейчас» → те же записи; время — относительно «сейчас»
(как демо-мир R02: демо всегда «свежее»). Цели — настоящие дворы R12 (yards.json, OSM) или ячейки «примерного
места»; категории и уточнения — из categories_v2.json; служба — по таблице R08; срок ответа — рабочие дни R09.
Когда R09 поставит v2.1 (services[], handoffs[]) или R02 — демо-мир, источник табло переключается на R09 сам
(sources.py), фикстура остаётся только для тестов.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from . import board as calc
from . import geo, profiles

# (категория, уточнение | None, вес) — все 20 служб справочника получают хотя бы несколько обращений.
MIX = (
    ("roads", None, 10), ("roads", "traffic_light_broken", 4), ("snow_ice", None, 12), ("snow_ice", "icicles", 3),
    ("sidewalks", None, 5), ("transport", None, 5), ("lighting", None, 8), ("lighting", "wire_down", 2),
    ("yards", None, 6), ("yards", "trees_lawn", 3), ("waste", None, 8), ("utilities", None, 3),
    ("utilities", "no_heating", 5), ("utilities", "no_water", 4), ("utilities", "power_building", 2),
    ("smell_air", None, 2), ("smell_air", "gas", 1), ("smell_air", "smoke_fire", 1), ("noise_safety", None, 3),
    ("noise_safety", "stray_dogs", 2), ("parking", None, 3), ("other", None, 2),
)
DISTRICT_WEIGHTS = (("nura", 35), ("esil", 18), ("almaty", 15), ("saryarka", 14), ("baikonur", 12), ("saraishyk", 6))
# Совместные обращения: (категория, уточнение, ведущая, участвующая, причина передачи ru) — синтетика.
JOINT = (
    ("roads", None, "water", "road", "Сначала нужна замена трубы"),
    ("sidewalks", None, "heating", "road", "Под тротуаром течёт теплотрасса"),
    ("lighting", None, "power", "lighting", "Нет питания на линии"),
    ("yards", None, "landscaping", "waste", "Нужен вывоз строительного мусора"),
    ("snow_ice", None, "street_cleaning", "transport", "Остановку закрыл сугроб"),
    ("utilities", "no_water", "water", "housing", "Течёт внутри дома"),
)
SCENE_COMPLAINT = "c-r17demoscene8pit"   # «Яма после раскопок» для сцены 8 (до демо-мира R02)
TOTAL = 160
SEED = 17


def _service(category: str, subtopic: str | None) -> str:
    return calc.lead_service({"category": category, "subtopic": subtopic}, _r08_lookup())


def _r08_lookup():
    try:
        from ui.civic_akim.routing import service_for  # type: ignore
        return service_for
    except Exception:  # noqa: BLE001
        return None


def _response_days(category: str) -> int:
    try:
        from ui.civic_feedback.v2 import categories  # type: ignore
        return int(categories.response_days(category))
    except Exception:  # noqa: BLE001
        return 10


def _add_working_days(start: datetime, days: int) -> datetime:
    try:
        from ui.civic_feedback.v2 import workdays  # type: ignore
        return workdays.add_working_days(start, days)
    except Exception:  # noqa: BLE001
        moment, counted = start, 0
        while counted < days:
            moment += timedelta(days=1)
            if moment.weekday() < 5:
                counted += 1
        return moment


def _pick(rng: random.Random, weighted):
    total = sum(w for *_x, w in weighted)
    roll, acc = rng.uniform(0, total), 0.0
    for item in weighted:
        acc += item[-1]
        if roll <= acc:
            return item
    return weighted[-1]


def _yards_by_district() -> dict:
    out: dict[str, list[dict]] = {d: [] for d in geo.DISTRICTS}
    for yard in sorted(geo.yards().values(), key=lambda y: y["id"]):
        if yard["district"] in out:
            out[yard["district"]].append(yard)
    return out


def _target(rng: random.Random, district: str, yards: dict) -> tuple[dict, list[float]]:
    pool = yards.get(district) or []
    if pool:
        yard = pool[rng.randrange(len(pool))]
        return ({"kind": "area", "id": yard["id"], "label_ru": yard["label_ru"], "label_kk": yard["label_kk"]},
                [round(yard["point"][0], 6), round(yard["point"][1], 6)])
    # Нет данных R12: ячейка «примерного места» у условной точки района (подпись честная: «примерное место»).
    centre = {"nura": (71.41, 51.09), "esil": (71.43, 51.13), "almaty": (71.48, 51.15),
              "saryarka": (71.42, 51.18), "baikonur": (71.46, 51.17), "saraishyk": (71.38, 51.11)}[district]
    point = [round(centre[0] + rng.uniform(-0.01, 0.01), 6), round(centre[1] + rng.uniform(-0.006, 0.006), 6)]
    try:
        from ui.civic_feedback.v2.record import cell_target  # type: ignore
        return cell_target(*point), point
    except Exception:  # noqa: BLE001
        return {"kind": "area", "id": "cell-0-0", "approximate": True, "label_ru": "Примерное место",
                "label_kk": "Шамамен орны"}, point


def _history(rng: random.Random, created: datetime, now: datetime, final: str) -> tuple[list[dict], dict | None]:
    """История статусов до final и (для fixed) раунд проверки жителями."""
    history = [{"at": calc.iso(created), "status": "new"}]
    if final == "new":
        return history, None
    answer = created + timedelta(hours=rng.choice((3, 6, 20, 26, 30, 50, 75, 100)))
    answer = min(answer, now - timedelta(minutes=30))
    history.append({"at": calc.iso(answer), "status": "accepted" if final != "rejected" else "rejected"})
    if final in ("accepted", "rejected"):
        return history, None
    work = min(answer + timedelta(hours=rng.choice((4, 12, 30))), now - timedelta(minutes=20))
    history.append({"at": calc.iso(work), "status": "in_progress"})
    if final == "in_progress":
        return history, None
    fixed = min(work + timedelta(hours=rng.choice((6, 24, 48, 96))), now - timedelta(minutes=10))
    history.append({"at": calc.iso(fixed), "status": "fixed"})
    roll = rng.random()
    if roll < 0.55:
        resolution = {"state": "verified", "round": 1, "reported_at": calc.iso(fixed),
                      "verified_at": calc.iso(min(fixed + timedelta(hours=8), now)), "votes": {"yes": 2}}
    else:
        resolution = {"state": "reported", "round": 1, "reported_at": calc.iso(fixed), "votes": {}}
    return history, resolution


def demo_records(now: datetime | None = None) -> list[dict]:
    """Синтетические жалобы v2.1 за 45 дней (demo: true). Детерминированно относительно now."""
    now = (now or datetime.now(calc.ASTANA)).astimezone(calc.ASTANA).replace(microsecond=0)
    rng = random.Random(SEED)
    yards = _yards_by_district()
    records = []
    for n in range(TOTAL):
        district = _pick(rng, DISTRICT_WEIGHTS)[0]
        category, subtopic, _w = _pick(rng, MIX)
        age_hours = rng.uniform(2, 45 * 24)
        created = now - timedelta(hours=age_hours)
        # Чем старше обращение, тем вероятнее оно закрыто; часть свежих — ещё без ответа.
        if age_hours < 30:
            final = rng.choice(("new", "new", "accepted", "in_progress"))
        elif age_hours < 24 * 10:
            final = rng.choice(("new", "accepted", "in_progress", "in_progress", "fixed", "fixed"))
        else:
            final = rng.choice(("new", "in_progress", "fixed", "fixed", "fixed", "fixed", "rejected"))
        history, resolution = _history(rng, created, now, final)
        lead = _service(category, subtopic)
        target, point = _target(rng, district, yards)
        record = {
            "id": f"c-r17demo{n:04d}", "code": f"П-{n + 1:04d}", "created_at": calc.iso(created),
            "category": category, "subtopic": subtopic, "district": district, "status": final,
            "status_history": history,
            "due_at": calc.iso(_add_working_days(created, _response_days(category))),
            "target": target, "point": point, "metoo": rng.choice((0, 0, 1, 2, 4)),
            "service": lead, "services": [], "handoffs": [], "demo": True,
        }
        if resolution:
            record["resolution"] = resolution
        # «Вернули жители»: несколько закрытых обращений жители вернули в работу (R09 verify → reopened).
        if final == "in_progress" and rng.random() < 0.12:
            record["resolution"] = {"state": "reopened", "round": 1, "reopen_count": 1,
                                    "reopened_at": calc.iso(now - timedelta(hours=rng.uniform(3, 60))), "votes": {"no": 1}}
        records.append(record)
    _add_joint(rng, records, now, yards)
    return records


def _part_status(status: str) -> str:
    return calc.PART_FROM_STATUS.get(status, "new")


def _add_joint(rng: random.Random, records: list[dict], now: datetime, yards: dict) -> None:
    """Совместные обращения с передачами (§5.1), среди них «передачи по кругу» и сцена 8."""
    for i, (category, subtopic, lead, partner, reason) in enumerate(JOINT * 2):
        record = records[7 + i * 11]
        created = calc.parse_iso(record["created_at"])
        record.update({"category": category, "subtopic": subtopic, "service": lead,
                       "due_at": calc.iso(_add_working_days(created, _response_days(category)))})
        first = created + timedelta(hours=2)
        handoffs = [{"at": calc.iso(min(first, now)), "from": partner, "to": lead, "reason": reason, "by_role": "operator"}]
        if i in (3, 8):   # «передачи по кругу»: вернули обратно, затем снова передали
            back = created + timedelta(hours=26)
            handoffs.append({"at": calc.iso(min(back, now)), "from": lead, "to": partner,
                             "reason": "Не наш участок", "by_role": "operator"})
            handoffs.append({"at": calc.iso(min(back + timedelta(hours=20), now)), "from": partner, "to": lead,
                             "reason": reason, "by_role": "editor"})
        lead_status = _part_status(record["status"])
        partner_status = "in_progress" if lead_status == "done" else rng.choice(("new", "in_progress"))
        if record["status"] == "fixed":
            partner_status = "done"
        record["services"] = [
            {"service": lead, "role": "lead", "status": lead_status, "updated_at": record["status_history"][-1]["at"]},
            {"service": partner, "role": "partner", "status": partner_status,
             "updated_at": record["status_history"][-1]["at"]},
        ]
        if record["status"] == "fixed" and partner_status != "done":
            record["status"] = "in_progress"
        record["handoffs"] = handoffs
        record["route_hint"] = {"services": [lead, partner], "joint": True, "source": "rules", "model_version": None}
    # Сцена 8: «Яма после раскопок» — Водоканал сделал, Дорожная служба в работе, передача road → water.
    scene = records[0]
    created = now - timedelta(days=3, hours=4)
    district = "nura"
    target, point = _target(random.Random(SEED + 8), district, yards)
    scene.update({
        "id": SCENE_COMPLAINT, "code": "П-0008", "created_at": calc.iso(created), "category": "roads", "subtopic": None,
        "district": district, "status": "in_progress", "target": target, "point": point, "metoo": 5,
        "status_history": [{"at": calc.iso(created), "status": "new"},
                           {"at": calc.iso(created + timedelta(hours=5)), "status": "accepted"},
                           {"at": calc.iso(created + timedelta(hours=30)), "status": "in_progress"}],
        "due_at": calc.iso(_add_working_days(created, _response_days("roads"))),
        "service": "water",
        "services": [{"service": "water", "role": "lead", "status": "done", "note": "Трубу заменили",
                      "updated_at": calc.iso(created + timedelta(days=2))},
                     {"service": "road", "role": "partner", "status": "in_progress",
                      "updated_at": calc.iso(created + timedelta(days=2, hours=3))}],
        "handoffs": [{"at": calc.iso(created + timedelta(hours=4)), "from": "road", "to": "water",
                      "reason": "Сначала нужна замена трубы", "by_role": "operator"}],
        "route_hint": {"services": ["water", "road"], "joint": True, "source": "rules", "model_version": None},
    })
    scene.pop("resolution", None)
    # Служба — только из справочника CONTRACT §3 (таблица R08 с правками акимата не может дать другой id).
    records[:] = [r for r in records if r["service"] in profiles.PROFILES]
