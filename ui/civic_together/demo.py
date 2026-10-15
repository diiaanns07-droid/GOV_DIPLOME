"""Демо-набор «Бірге: жители вместе» (CIVIC_DEMO=1) и чтение своей части демо-мира R02 (CONTRACT §11).

Пока демо-мира R02 нет (data/civic/astana/demo-world/world_v1.json), модуль засевает свою фикстуру строго в формате
CONTRACT §5.2–5.3: 8 дворов (настоящие дворы OSM из R12, landuse=residential, подписи и точки — с карты R12) и
9 инициатив (синтетика, demo: true — на экране «Пример»). Тексты придуманы, без имён, телефонов и организаций; номер
+7 700 000 00 00 у инициативы на проверке — заведомо несуществующий, он показывает пометку модерации R04.
Число соседей и «Я приду» у демо-записей — числом (base_members, base_joined), без выдуманных устройств (R15 S20).
Фото «после» у демо-записей нет (поправка П1: фото — только настоящие фото жителей); экран пишет «Фото появится после дела».

Время — относительно момента засева: демо всегда «свежее» в день показа. Сцена 7 демо v2 (IDEA §3):
двор GreenLine.Asyl Mura (Нура) → «Субботник во дворе» в ближайшую субботу, 10:00 → «Я приду» 14 → 15 →
«Поддержать: мешки и вывоз» → «Сделано вместе». Для сцены — SCENE.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from .store import ASTANA, iso, parse_iso

SCENE = {"yard": "yard-1454082638", "initiative": "i-demo-scene7"}

# (id, район, подпись ru, подпись kk, точка, соседей «раньше»)
_YARDS = (
    ("yard-1454082638", "nura", "Двор: GreenLine.Asyl Mura", "Аула: GreenLine.Asyl Mura", (71.3970633, 51.1348358), 37),
    ("yard-1461758835", "nura", "Двор: Tandau", "Аула: Tandau", (71.4052617, 51.122119), 24),
    ("yard-1424189376", "nura", "Двор: Eco Park", "Аула: Eco Park", (71.3914178, 51.1276056), 12),
    ("yard-1148721825", "nura", "Двор: Evolution", "Аула: Evolution", (71.4018712, 51.1288692), 9),
    ("yard-1209611630", "esil", "Двор: Argento", "Аула: Argento", (71.4215016, 51.1114194), 15),
    ("yard-1531938764", "saryarka", "Двор: Столичный-2", "Аула: Столичный-2", (71.4066876, 51.1650743), 6),
    ("yard-1104998691", "almaty", "Двор: Энергетик", "Аула: Энергетик", (71.4517805, 51.1478191), 11),
    ("yard-1385141130", "saraishyk", "Двор: Highvill", "Аула: Highvill", (71.4644431, 51.1272278), 8),
)
_YARD = {row[0]: row for row in _YARDS}

D = timedelta(days=1)
H = timedelta(hours=1)


def next_weekday(now: datetime, weekday: int, hour: int, minimum: timedelta = timedelta(hours=20)) -> datetime:
    """Ближайший день недели (0 — понедельник) в hour:00 по Астане, не раньше чем через minimum."""
    local = now.astimezone(ASTANA)
    day = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    day += timedelta(days=(weekday - local.weekday()) % 7)
    while day - local < minimum:
        day += timedelta(days=7)
    return day


def _target(yard_id: str) -> dict:
    row = _YARD[yard_id]
    return {"kind": "area", "id": yard_id, "label_ru": row[2], "label_kk": row[3]}


def _initiative(iid, kind, yard_id, lang, title, text, bring, status, joined, starts: datetime, hours: float,
                created: datetime, published: datetime | None = None, support=None, report=None, done=None):
    row = _YARD[yard_id]
    return {"id": iid, "kind": kind, "title": title, "text": text, "lang": lang, "target": _target(yard_id),
            "point": list(row[4]), "district": row[1], "starts_at": iso(starts), "ends_at": iso(starts + hours * H),
            "bring": list(bring), "status": status, "joined": joined, "support": support, "report": report,
            "created_at": iso(created), "published_at": iso(published) if published else None,
            "done_at": iso(done) if done else None, "updated_at": iso(done or published or created), "demo": True}


def rows(now: datetime) -> tuple[list[dict], list[dict]]:
    """(дворы, инициативы) демо-набора на момент now."""
    now = now.astimezone(ASTANA)
    yards = [{"id": y[0], "district": y[1], "label_ru": y[2], "label_kk": y[3], "point": list(y[4]), "members": y[5],
              "captain": None, "demo": True} for y in _YARDS]
    saturday = next_weekday(now, 5, 10)
    sunday = next_weekday(now, 6, 11)
    snow_day = (now + 3 * D).replace(hour=9, minute=0, second=0, microsecond=0)
    benches_done = (now - 9 * D).replace(hour=13, minute=0, second=0, microsecond=0)
    trees_done = (now - 20 * D).replace(hour=14, minute=0, second=0, microsecond=0)
    items = [
        # Сцена 7: опубликована два дня назад, 14 соседей «Я приду», поддержки акимата ещё нет.
        _initiative("i-demo-scene7", "cleanup", "yard-1454082638", "ru", "Субботник во дворе",
                    "Уберём листья и мусор у детской площадки и вдоль дорожек. Начнём у первого подъезда.",
                    ("перчатки", "мешки", "грабли"), "published", 14, saturday, 3, now - 2 * D - 3 * H, now - 2 * D),
        _initiative("i-demo-benches", "repair", "yard-1454082638", "ru", "Покрасим лавочки и урны",
                    "Освежим лавочки у площадки и урны у подъездов. Краску и кисти обещали привезти.",
                    ("старую одежду", "перчатки"), "done", 11, benches_done - 3 * H, 3, now - 16 * D, now - 15 * D,
                    support={"by_akimat": True, "inventory": True, "pickup_service": None,
                             "note": "Краска и кисти от акимата", "at": iso(now - 13 * D)},
                    report={"text": "Покрасили 8 лавочек и 4 урны, убрали старые объявления со столбов.",
                            "joined": 11, "status": "published", "by_role": "staff", "at": iso(benches_done)},
                    done=benches_done),
        _initiative("i-demo-review-flowers", "greening", "yard-1454082638", "ru", "Сделаем клумбу у подъезда",
                    "Разобьём клумбу у второго подъезда: вскопаем землю и посадим луковицы тюльпанов до заморозков.",
                    ("лопаты",), "on_review", 0, sunday + 7 * D, 2, now - 3 * H),
        _initiative("i-demo-trees", "greening", "yard-1461758835", "ru", "Посадим саженцы у площадки",
                    "Посадим клёны вдоль дорожки к детской площадке. Нужны руки и вёдра для полива.",
                    ("перчатки", "вёдра"), "published", 9, sunday, 2, now - 4 * D, now - 4 * D + 5 * H,
                    support={"by_akimat": True, "inventory": True, "pickup_service": None,
                             "note": "Саженцы и лопаты привезут к 11:00", "at": iso(now - 1 * D)}),
        _initiative("i-demo-snow", "snow", "yard-1424189376", "ru", "Расчистим дорожки после снегопада",
                    "Если ночью выпадет снег, утром вместе расчистим дорожки к подъездам и к остановке.",
                    ("лопату", "тёплые перчатки"), "published", 6, snow_day, 2, now - 1 * D, now - 20 * H),
        _initiative("i-demo-help", "help", "yard-1148721825", "kk", "Қарт көршілерге көмектесейік",
                    "Сенбі күні қарт көршілерге дүкеннен азық-түлік жеткізуге көмектесеміз. "
                    "Жиналу орны — бірінші подъезд жанында.",
                    ("сөмке",), "published", 5, saturday + 2 * H, 2, now - 2 * D, now - 2 * D + 2 * H),
        _initiative("i-demo-argento", "cleanup", "yard-1209611630", "kk", "Ауланы бірге тазалайық",
                    "Сенбі күні аула мен балалар алаңын жапырақтан тазалаймыз.",
                    ("қолғап", "қап"), "published", 8, saturday + 1 * H, 3, now - 3 * D, now - 3 * D + 4 * H),
        _initiative("i-demo-trees-done", "greening", "yard-1461758835", "ru", "Посадили саженцы вдоль дорожки",
                    "Весенняя посадка у детской площадки.", ("перчатки",), "done", 15, trees_done - 3 * H, 3,
                    now - 27 * D, now - 26 * D,
                    support={"by_akimat": True, "inventory": True, "pickup_service": "waste",
                             "note": "Мешки и вывоз в 14:00", "at": iso(now - 23 * D)},
                    report={"text": "Убрали двор и посадили 6 саженцев.", "joined": 15, "status": "published",
                            "by_role": "staff", "at": iso(trees_done)},
                    done=trees_done),
        _initiative("i-demo-review-phone", "cleanup", "yard-1531938764", "ru", "Субботник у школы",
                    "Приглашаю всех на уборку у школы. Вопросы — по телефону +7 700 000 00 00.",
                    ("мешки",), "on_review", 0, saturday, 3, now - 1 * H),
    ]
    return yards, items


# --------------------------------------------------------------------------- демо-мир R02
_TIME_FIELDS = ("starts_at", "ends_at", "created_at", "published_at", "done_at", "updated_at")


def _relative(spec, now: datetime) -> datetime | None:
    """Относительное время -> время по Астане. Понимает объекты SCHEMA R02 §1 ({"next_weekday": {weekday, hour,
    minute}}, {"day_at": {day, hour, minute}}, {"day": N}) и плоские {"in_days", "in_hours", "ago_days", "ago_hours",
    "hour", "minute"}."""
    if not isinstance(spec, dict):
        return None
    if isinstance(spec.get("next_weekday"), dict):
        nw = spec["next_weekday"]
        return next_weekday(now, int(nw.get("weekday", 5)), int(nw.get("hour", 10)), minimum=timedelta(hours=12)) \
            .replace(minute=int(nw.get("minute") or 0))
    if isinstance(spec.get("day_at"), dict):
        da = spec["day_at"]
        day = (now.astimezone(ASTANA) + timedelta(days=int(da.get("day") or 0)))
        return day.replace(hour=int(da.get("hour") or 0), minute=int(da.get("minute") or 0), second=0, microsecond=0)
    if isinstance(spec.get("day"), (int, float)) and len(spec) == 1:
        return (now.astimezone(ASTANA) + timedelta(days=int(spec["day"]))).replace(hour=12, minute=0, second=0,
                                                                                  microsecond=0)
    moment = now
    moment += timedelta(days=float(spec.get("in_days") or 0), hours=float(spec.get("in_hours") or 0))
    moment -= timedelta(days=float(spec.get("ago_days") or 0), hours=float(spec.get("ago_hours") or 0))
    if spec.get("hour") is not None:
        moment = moment.astimezone(ASTANA).replace(hour=int(spec["hour"]), minute=int(spec.get("minute") or 0),
                                                   second=0, microsecond=0)
    return moment


def _moment(record: dict, field: str, now: datetime) -> str | None:
    """Время поля из записи демо-мира: ISO-строка, вложенный объект {in_days|ago_days…} или плоские поля
    <поле>_in_days / <поле>_ago_hours (field без «_at»). Формат R02 (SCHEMA.md) пока не выпущен — понимаем все три."""
    value = record.get(field)
    if isinstance(value, str):
        parsed = parse_iso(value)
        return iso(parsed) if parsed else None
    rel = _relative(value, now)
    if rel is not None:
        return iso(rel)
    stem = field[:-3] if field.endswith("_at") else field
    flat = {k[len(stem) + 1:]: v for k, v in record.items() if k.startswith(stem + "_") and k != field}
    if any(k in flat for k in ("in_days", "in_hours", "ago_days", "ago_hours")):
        return iso(_relative(flat, now))
    return None


def _materialize(records: dict, now: datetime) -> dict:
    """R01 передаёт мир уже с абсолютными временами (SCHEMA R02 §4). Сырой мир — через materialize R02, если он есть
    в сборке; нет — свой разбор ниже понимает те же объекты времени."""
    try:
        from ml.datasets.demo_world_io import materialize
    except Exception:
        return records
    try:
        part = {key: records[key] for key in ("yards", "initiatives") if key in records}
        return dict(records, **materialize(part, now))
    except Exception:
        return records


def _round_hour(value: str | None) -> str | None:
    """Время дела в демо — круглые часы: «17:00–20:00», а не «17:14–20:14» от минуты засева (просьба R01 к R02/R16).
    Мир R02 задаёт часть дел относительными часами (in_hours / ago_hours); округляем до ближайшего часа."""
    moment = parse_iso(value) if value else None
    if moment is None:
        return value
    return iso((moment + H / 2).replace(minute=0, second=0, microsecond=0))


def world_part(records: dict, now: datetime) -> tuple[list[dict], list[dict]]:
    """Дворы и инициативы из world_v1.json (R02) в формате seed(): только своя часть, время — от момента засева."""
    now = now.astimezone(ASTANA)
    records = _materialize(records, now)
    yards = []
    for raw in records.get("yards") or []:
        if not isinstance(raw, dict) or not str(raw.get("id", "")).startswith(("yard-", "cell-")):
            continue
        captain = raw.get("captain") if isinstance(raw.get("captain"), dict) and raw["captain"].get("display_name") else None
        if captain:
            captain = {"display_name": str(captain["display_name"])[:40], "since": _moment(captain, "since", now)}
        yards.append({"id": raw["id"], "label_ru": raw.get("label_ru"), "label_kk": raw.get("label_kk"),
                      "district": raw.get("district"), "point": raw.get("point"),
                      "members": int(raw.get("members") or 0), "captain": captain, "demo": True})
    items = []
    for raw in records.get("initiatives") or []:
        if not isinstance(raw, dict) or not raw.get("id") or not raw.get("title") or not raw.get("point"):
            continue
        item = {k: raw.get(k) for k in ("id", "kind", "title", "text", "lang", "target", "point", "district", "bring",
                                        "status", "joined", "from_idea")}
        item["kind"] = item["kind"] or "other"
        item["status"] = item["status"] or "published"
        times = {field: _moment(raw, field, now) for field in _TIME_FIELDS}
        # Общие поля демо-мира: ago_days/ago_hours — когда создана, in_days/in_hours — когда начнётся.
        if times["created_at"] is None and any(k in raw for k in ("ago_days", "ago_hours")):
            times["created_at"] = iso(_relative({"ago_days": raw.get("ago_days"), "ago_hours": raw.get("ago_hours")}, now))
        if times["starts_at"] is None and any(k in raw for k in ("in_days", "in_hours")):
            times["starts_at"] = iso(_relative({"in_days": raw.get("in_days"), "in_hours": raw.get("in_hours"),
                                                "hour": raw.get("hour", 10)}, now))
        times["created_at"] = times["created_at"] or iso(now - 2 * D)
        times["starts_at"] = times["starts_at"] or iso(next_weekday(now, 5, 10))
        if times["ends_at"] is None:
            times["ends_at"] = iso(parse_iso(times["starts_at"]) + 3 * H)
        times["starts_at"], times["ends_at"] = _round_hour(times["starts_at"]), _round_hour(times["ends_at"])
        if parse_iso(times["ends_at"]) <= parse_iso(times["starts_at"]):
            times["ends_at"] = iso(parse_iso(times["starts_at"]) + H)
        if item["status"] in ("published", "done") and times["published_at"] is None:
            times["published_at"] = times["created_at"]
        item.update(times)
        support = raw.get("support")
        if isinstance(support, dict) and support.get("by_akimat"):
            support = dict(support)
            support["at"] = _moment(support, "at", now) or times["published_at"] or times["created_at"]
            item["support"] = support
        report = raw.get("report")
        if isinstance(report, dict) and report.get("text"):
            at = _moment(report, "at", now) or times["done_at"] or iso(now - 1 * D)
            # Фото демо-мира не берём (поправка П1): фото «после» — только настоящие, загруженные людьми.
            item["report"] = {"text": report["text"], "joined": report.get("joined") or item.get("joined"),
                              "status": "published", "by_role": "staff", "at": at}
            if item["status"] == "done" and not item.get("done_at"):
                item["done_at"] = at
        item["demo"] = True
        items.append(item)
    return yards, items
