"""Демо-мир R02 для R06 (раунд 15, CONTRACT §11): идеи, проекты и работы из data/civic/astana/demo-world/world_v1.json.

    seed_world(db_path, records, now=None, *, reset=False) -> {"inserted", "skipped", "reset", "retired", ...}

Берём только свои ключи мира: works (работы и отключения, §2.4 схемы R02) и ideas (§2.6). Проектов (proposals) в мире
нет: у идеи со статусом project R06 сам делает демо-проект «По идее жителей» (вид — объект идеи; освещение — линия по
ближайшему ребру улицы графа OSM R12, иначе идея остаётся «Акимат проверяет»). Пять демо-проектов FINAL-4 для шага 5
сценария ставит прежний seed_r14_demo — их не трогаем.

Как засеваем (опыт R09 seed_demo и советы R02 SCHEMA §4):
  - идемпотентно по id записи мира (колонка world_key): повтор ничего не дублирует;
  - reset=True — демо-записи мира возвращаются к виду мира (статус, голоса, тексты), настоящие записи (demo = 0) —
    никогда; без reset существующие записи мира не трогаются;
  - сроки работ храним относительно «сегодня» (demo_rel_json, как демо FINAL-4): витрина свежая в любой день показа,
    а календарь R12 и «Рядом» R08 видят те же даты, что мир от момента засева;
  - голоса идей — синтетические устройства R02: sha256("demo-world-v1:<id>:<n>") — одинаковы при каждом засеве;
  - демо FINAL-4 (6 идей «i-demo-…» и 8 записей «Рядом» «nb-demo-…») в режиме мира убираем: иначе в «Идеях» и «Рядом»
    два демо-набора и числа расходятся (IDEA §2D). Настоящие записи не трогаем.
records — мир целиком (dict) от R01, уже материализованный (ISO-времена); сырой мир (относительные времена) модуль
материализует сам помощником R02 ml.datasets.demo_world_io.materialize (или такой же функцией ниже, если R02 нет).
"""

from __future__ import annotations

import copy
from datetime import date, datetime, timedelta, timezone
import hashlib
import logging
import os

from .districts import DISTRICT_NAMES, district_of
from .ideas import CHECK_ANSWERS, CHECK_KEYS, IdeaRepository
from .nearby import ASTANA_TZ, SOURCES, UTILITIES, WORK_KINDS, WORK_STATUSES, default_kind
from .objects import Actor, iso, utc_now, _dumps, _loads
from .proposals import KINDS as PROJECT_KINDS, ProposalRepository
from .validate import is_valid_id
from . import works_v2
from .works_v2 import KINDS_V2, SEGMENT_RE


LOGGER = logging.getLogger("ui.civic_store.world")
WORLD_ACTOR = Actor(kind="system", user_id=None, label="seed-world", public_label="Демо-мир (синтетика)")
IDEA_STATUSES = ("review", "voting", "checking", "project", "rejected")
WHY_KEYS = ("problem", "reason", "result", "inconvenience")
MAX_VOTES = 500                      # голосов у демо-идеи не больше (мир даёт десятки)


def seed_world(db_path, records, now=None, *, reset=False, service=None) -> dict:
    """Своя часть демо-мира R02: идеи (+ демо-проекты из идей «стала проектом») и работы/отключения."""
    from .service import CivicService

    world = records if isinstance(records, dict) else {}
    now_dt = _astana(now)
    world = _materialize({"works": world.get("works") or [], "ideas": world.get("ideas") or []}, now_dt)
    svc = service or CivicService(db_path)
    report = {"inserted": 0, "skipped": 0, "reset": 0, "retired": 0, "projects": 0, "invalid": 0, "notes": [],
              "source": "world" if world["works"] or world["ideas"] else "empty"}
    if report["source"] == "empty":
        return report
    stamp = iso(now_dt)
    report["retired"] = _retire_final4_demo(svc, stamp)
    for rec in world["works"]:
        _count(report, _seed_work(svc, rec, now_dt, stamp, reset))
    proposals = ProposalRepository(svc.db, lambda: now_dt)
    for rec in world["ideas"]:
        outcome = _seed_idea(svc, proposals, rec, now_dt, stamp, reset)
        _count(report, outcome)
        if isinstance(outcome, tuple) and outcome[1]:
            report["notes"].append(outcome[1])
    with svc.db.read() as conn:
        report["projects"] = conn.execute("SELECT COUNT(*) FROM civic_proposals WHERE world_key IS NOT NULL").fetchone()[0]
    return report


def _count(report, outcome):
    action = outcome[0] if isinstance(outcome, tuple) else outcome
    key = {"insert": "inserted", "skip": "skipped", "reset": "reset", "invalid": "invalid"}[action]
    report[key] += 1


# --- время мира -------------------------------------------------------------------------------------------------

def _astana(now):
    if now is None:
        now = datetime.now(timezone.utc)
    if isinstance(now, str):
        now = datetime.fromisoformat(now.replace("Z", "+00:00"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=ASTANA_TZ)
    return now.astimezone(ASTANA_TZ)


def _materialize(part, now):
    """Относительные времена мира → ISO (помощник R02; нет его в сборке — те же правила SCHEMA §1 ниже)."""
    try:
        from ml.datasets.demo_world_io import materialize
        return materialize(part, now)
    except ImportError:
        return _walk(copy.deepcopy(part), now)


_INSTANT = {"ago_hours": -3600, "in_hours": 3600, "ago_days": -86400, "in_days": 86400}


def _walk(value, now):
    if isinstance(value, dict) and len(value) == 1:
        (key, inner), = value.items()
        if key in _INSTANT and isinstance(inner, (int, float)) and not isinstance(inner, bool):
            return (now + timedelta(seconds=float(inner) * _INSTANT[key])).replace(microsecond=0).isoformat()
        if key == "day" and isinstance(inner, int) and not isinstance(inner, bool):
            return (now.date() + timedelta(days=inner)).isoformat()
        if key == "season" and isinstance(inner, dict) and set(inner) == {"month", "day"}:
            year = now.year if now.month <= 3 else now.year + 1       # следующий строительный сезон
            return date(year, inner["month"], inner["day"]).isoformat()
        if key == "day_at" and isinstance(inner, dict) and set(inner) == {"day", "hour", "minute"}:
            day = now.date() + timedelta(days=inner["day"])
            return datetime(day.year, day.month, day.day, inner["hour"], inner["minute"], tzinfo=ASTANA_TZ).isoformat()
        if key == "next_weekday" and isinstance(inner, dict) and set(inner) == {"weekday", "hour", "minute"}:
            moment = now.replace(hour=inner["hour"], minute=inner["minute"], second=0, microsecond=0)
            moment += timedelta(days=(inner["weekday"] - now.weekday()) % 7)
            while moment - now < timedelta(hours=12):
                moment += timedelta(days=7)
            return moment.isoformat()
    if isinstance(value, dict):
        return {k: _walk(v, now) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk(v, now) for v in value]
    return value


def _date(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else None
    except ValueError:
        return None


def _moment(value):
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=ASTANA_TZ)).astimezone(ASTANA_TZ)


# --- демо FINAL-4 в режиме мира ---------------------------------------------------------------------------------

def _retire_final4_demo(svc, stamp) -> int:
    """Демо-идеи и записи «Рядом» FINAL-4 (не из мира) — убрать: в режиме мира один демо-набор."""
    retired = 0
    with svc.db.write() as conn:
        for row in conn.execute("""SELECT id, revision FROM civic_nearby_items
                                   WHERE demo = 1 AND world_key IS NULL AND removed = 0 AND id LIKE 'nb-demo-%'""").fetchall():
            conn.execute("UPDATE civic_nearby_items SET removed = 1, revision = ?, updated_at = ? WHERE id = ?",
                         (row["revision"] + 1, stamp, row["id"]))
            conn.execute("""INSERT INTO civic_nearby_history(item_id, revision, at, action, snapshot_json, actor_user_id,
                                actor_label) VALUES (?, ?, ?, 'remove', ?, NULL, 'seed-world')""",
                         (row["id"], row["revision"] + 1, stamp, _dumps({"reason": "демо FINAL-4 заменено демо-миром R02"})))
            retired += 1
        for row in conn.execute("""SELECT id FROM civic_ideas WHERE demo = 1 AND world_key IS NULL
                                   AND status != 'hidden' AND id LIKE 'i-demo-%'""").fetchall():
            conn.execute("UPDATE civic_ideas SET status = 'hidden', updated_at = ? WHERE id = ?", (stamp, row["id"]))
            IdeaRepository._history(conn, row["id"], stamp, "hide", "hidden",
                                    "Демо FINAL-4 заменено демо-миром R02", None, "seed-world")
            retired += 1
    return retired


# --- работы и отключения (§2.4) ---------------------------------------------------------------------------------

def _texts(rec):
    texts = {"lang": "ru"}
    for field in ("title", "zone", "detour"):
        for lang in ("ru", "kk"):
            value = rec.get(f"{field}_{lang}")
            if isinstance(value, str) and value.strip():
                texts[f"{field}_{lang}"] = value.strip()[:200]
    why = rec.get("why") if isinstance(rec.get("why"), dict) else {}
    for key in WHY_KEYS:
        for lang in ("ru", "kk"):
            value = why.get(f"{key}_{lang}")
            if isinstance(value, str) and value.strip():
                texts[f"why_{key}_{lang}"] = value.strip()[:200]
    return texts


def _geometry(value):
    """Форма из мира (рёбра графа R12): Point / LineString / MultiLineString с числами внутри Астаны."""
    if not isinstance(value, dict):
        return None
    kind, coords = value.get("type"), value.get("coordinates")
    lines = [[coords]] if kind == "Point" else [coords] if kind == "LineString" else coords if kind == "MultiLineString" else None
    if not lines:
        return None
    try:
        for line in lines:
            for p in line:
                lon, lat = float(p[0]), float(p[1])
                if not (70.9 <= lon <= 71.9 and 50.9 <= lat <= 51.4):
                    return None
    except (TypeError, ValueError, IndexError):
        return None
    return {"type": kind, "coordinates": coords}


def _yard_point(yard_id):
    try:
        from .notify import _yard_point as point_of
        import importlib
        return point_of(importlib.import_module, yard_id)
    except Exception:  # noqa: BLE001
        return None


def _seed_work(svc, rec, now, stamp, reset):
    rid = rec.get("id") if isinstance(rec, dict) else None
    if not is_valid_id(rid) or len(rid) > 64 or rec.get("type") not in ("work", "outage"):
        return "invalid"
    district = rec.get("district")
    service = rec.get("service") if rec.get("service") in SOURCES else None
    if district not in DISTRICT_NAMES or service is None:
        return "invalid"
    today = now.date()
    texts = _texts(rec)
    if not texts.get("title_ru") and not texts.get("title_kk"):
        return "invalid"
    demo = rec.get("source") != "real"
    geometry = _geometry(rec.get("geometry"))
    if geometry is None and isinstance(rec.get("near"), str):
        point = _yard_point(rec["near"])           # отключение у двора: точка двора R12 — для «работ рядом»
        geometry = {"type": "Point", "coordinates": point} if point else None
    segments = [s for s in (rec.get("segments") or []) if isinstance(s, str) and SEGMENT_RE.match(s)]
    place = {"street_ru": rec.get("street_ru"), "street_kk": rec.get("street_kk"), "length_m": rec.get("length_m"),
             "by": "world"} if segments or rec.get("street_ru") else None
    fields = {"district": district, "texts_json": _dumps(texts), "service": service,
              "geometry_json": _dumps(geometry) if geometry else None,
              "segments_json": _dumps(segments) if segments else None, "place_json": _dumps(place) if place else None,
              "demo": 1 if demo else 0, "start_at": None, "end_at": None, "planned_end": None, "forecast_end": None}
    if rec["type"] == "work":
        start, end = _date(rec.get("starts_on")), _date(rec.get("ends_on"))
        if end is None or (start is not None and end < start):
            return "invalid"
        status = rec.get("status") if rec.get("status") in WORK_STATUSES else "planned"
        work_kind = rec.get("work_kind") if rec.get("work_kind") in WORK_KINDS else "other"
        fields.update(type="work", status=status, work_kind=work_kind, utility=None, source=None,
                      kind=rec.get("kind") if rec.get("kind") in KINDS_V2 else default_kind("work", work_kind, None),
                      start_at=start.isoformat() if start else None, planned_end=end.isoformat())
        # Демо: сроки относительно «сегодня» (как демо FINAL-4), «изменено» — по стадии работы.
        rel = {"planned_end_day": (end - today).days, "forecast_end_day": (end - today).days,
               "updated_ago_min": {"in_progress": 180, "planned": 2880}.get(status, max(60, (today - end).days * 1440))}
        if start is not None:
            rel["start_day"] = (start - today).days
    else:
        start, end = _moment(rec.get("starts_at")), _moment(rec.get("ends_at"))
        utility = rec.get("utility") if rec.get("utility") in UTILITIES else None
        if start is None or end is None or end <= start or utility is None:
            return "invalid"
        fields.update(type="outage", status=None, work_kind=None, utility=utility, source=service,
                      kind="closure" if utility == "road_closure" else None,
                      start_at=start.isoformat(), end_at=end.isoformat())
        # Короче суток — время относительно «сегодня» (день и часы, как демо FINAL-4); дольше — как в мире.
        rel = {"updated_ago_min": 45}
        if end - start < timedelta(hours=24):
            rel["when"] = {"day": (start.date() - today).days, "from": start.strftime("%H:%M"), "to": end.strftime("%H:%M")}
    fields["demo_rel_json"] = _dumps(rel) if demo else None
    with svc.db.write() as conn:
        row = conn.execute("SELECT id, demo, revision FROM civic_nearby_items WHERE world_key = ? OR id = ?",
                           (rid, rid)).fetchone()
        if row is not None:
            if not reset or not row["demo"]:
                return "skip"
            sets = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(f"UPDATE civic_nearby_items SET {sets}, removed = 0, revision = ?, updated_at = ?, world_key = ? "
                         "WHERE id = ?", (*fields.values(), row["revision"] + 1, stamp, rid, row["id"]))
            conn.execute("""INSERT INTO civic_nearby_history(item_id, revision, at, action, snapshot_json, actor_user_id,
                                actor_label) VALUES (?, ?, ?, 'update', ?, NULL, 'seed-world')""",
                         (row["id"], row["revision"] + 1, stamp, _dumps({"world": rid, "reset": True})))
            return "reset"
        cols = ["id", "world_key", "revision", "created_at", "updated_at", *fields]
        conn.execute(f"INSERT INTO civic_nearby_items({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                     (rid, rid, 1, stamp, stamp, *fields.values()))
        conn.execute("""INSERT INTO civic_nearby_history(item_id, revision, at, action, snapshot_json, actor_user_id,
                            actor_label) VALUES (?, 1, ?, 'create', ?, NULL, 'seed-world')""",
                     (rid, stamp, _dumps({"world": rid, "demo": demo})))
    return "insert"


# --- идеи и демо-проекты (§2.6) ---------------------------------------------------------------------------------

def _idea_device(idea_id, n) -> str:
    return hashlib.sha256(f"demo-world-v1:{idea_id}:{n}".encode("utf-8")).hexdigest()


def _clean_check(value):
    if not isinstance(value, dict):
        return None
    out = {k: value.get(k) for k in CHECK_KEYS}
    return out if all(v in CHECK_ANSWERS for v in out.values()) else None


def _seed_idea(svc, proposals, rec, now, stamp, reset):
    rid = rec.get("id") if isinstance(rec, dict) else None
    status = rec.get("status") if isinstance(rec, dict) else None
    geometry = _geometry(rec.get("geometry")) if isinstance(rec, dict) else None
    if not is_valid_id(rid) or len(rid) > 64 or status not in IDEA_STATUSES or not geometry or geometry["type"] != "Point":
        return "invalid"
    district = rec.get("district") if rec.get("district") in DISTRICT_NAMES else district_of(geometry)
    texts = {}
    for field in ("title", "description", "reason", "can_improve"):
        for lang in ("ru", "kk"):
            value = rec.get(f"{field}_{lang}")
            if isinstance(value, str) and value.strip():
                texts[f"{field}_{lang}"] = value.strip()[:300]
    if not texts.get("title_ru") and not texts.get("title_kk"):
        return "invalid"
    if rec.get("self_doable") is True:
        texts["self_doable"] = True           # «жители могут сделать сами» → «Сделайте вместе» (R16)
    obj = rec.get("object") if isinstance(rec.get("object"), dict) else None
    obj = {"kind": obj["kind"]} if obj and obj.get("kind") in PROJECT_KINDS else None
    votes = rec.get("votes") if isinstance(rec.get("votes"), int) and not isinstance(rec.get("votes"), bool) else 0
    votes = max(0, min(MAX_VOTES, votes)) if status != "review" else 0
    created = _moment(rec.get("created_at")) or now
    decided = _moment(rec.get("decided_at"))
    check = _clean_check(rec.get("check"))
    note = None
    with svc.db.write() as conn:
        row = conn.execute("SELECT id, demo, project_id FROM civic_ideas WHERE world_key = ? OR id = ?", (rid, rid)).fetchone()
        if row is not None and (not reset or not row["demo"]):
            return "skip"
        project_id = row["project_id"] if row is not None else None
        if status == "project" and project_id is None:
            project_id, note = _world_project(conn, proposals, obj, geometry, rid, stamp, now)
            if project_id is None:
                status = "checking"           # проект не поставить честно (нет линии улицы) — «Акимат проверяет»
        lang = rec.get("lang") if rec.get("lang") in ("ru", "kk") else "ru"
        values = {"lang": lang, "texts_json": _dumps(texts), "geometry_json": _dumps(geometry), "district": district,
                  "object_json": _dumps(obj) if obj else None, "status": status, "check_json": _dumps(check) if check else None,
                  "reason": texts.get("reason_ru") or texts.get("reason_kk") or "",
                  "can_improve": texts.get("can_improve_ru") or texts.get("can_improve_kk") or "",
                  "project_id": project_id if status == "project" else None,
                  "votes_at_decision": votes if status in ("project", "rejected") else None,
                  "demo": 1, "created_at": iso(created), "updated_at": stamp,
                  "published_at": iso(created) if status != "review" else None,
                  "decided_at": iso(decided) if decided and status in ("project", "rejected") else None,
                  "initiative_id": rec["to_initiative"] if is_valid_id(rec.get("to_initiative")) else None,
                  "initiative_at": iso(decided or created) if is_valid_id(rec.get("to_initiative")) else None,
                  "world_key": rid}
        idea_id = row["id"] if row is not None else rid
        if row is None:
            cols = ["id", *values]
            conn.execute(f"INSERT INTO civic_ideas({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                         (idea_id, *values.values()))
            IdeaRepository._history(conn, idea_id, stamp, "create", status, "Демо-мир R02 (синтетика)", None, "seed-world")
            action = "insert"
        else:
            sets = ", ".join(f"{k} = ?" for k in values)
            conn.execute(f"UPDATE civic_ideas SET {sets} WHERE id = ?", (*values.values(), idea_id))
            # Голоса демо-идеи — снова как в мире: только синтетические устройства мира (настоящих тут нет: идея демо).
            conn.execute("DELETE FROM civic_idea_votes WHERE idea_id = ?", (idea_id,))
            action = "reset"
        for n in range(votes):
            conn.execute("INSERT OR IGNORE INTO civic_idea_votes(idea_id, device_hash, created_at) VALUES (?, ?, ?)",
                         (idea_id, _idea_device(idea_id, n + 1), iso(created)))
        if project_id is not None and status == "project":
            conn.execute("UPDATE civic_proposals SET idea_id = ? WHERE id = ? AND (idea_id IS NULL OR idea_id = ?)",
                         (idea_id, project_id, idea_id))
    return (action, note)


def _world_project(conn, proposals, obj, geometry, rid, stamp, now):
    """Демо-проект для идеи мира «стала проектом»: вид — объект идеи, место — точка идеи; освещение — линия по
    ближайшему ребру улицы графа OSM R12 (без R12 проект не ставим). Повтор — тот же проект (world_key)."""
    key = rid + ":project"
    found = conn.execute("SELECT id FROM civic_proposals WHERE world_key = ?", (key,)).fetchone()
    if found is not None:
        return found["id"], None
    kind = obj["kind"] if obj else None
    if kind is None:
        return None, f"{rid}: у идеи «стала проектом» нет объекта — оставлена «Акимат проверяет»"
    shape, street = geometry, (None, None)
    try:
        from engine.civic_geo import api as geo_api
        snapped = geo_api.street_snap(geometry["coordinates"][0], geometry["coordinates"][1])
        street = (snapped.get("street_ru") or snapped.get("near_street_ru"), snapped.get("street_kk") or snapped.get("near_street_kk"))
        if kind == "lighting":
            edges = works_v2.edges_lookup([snapped["edge_id"]]) or {}
            if snapped.get("edge_id") in edges:
                shape = works_v2.chain_geometry([edges[snapped["edge_id"]]])
    except Exception:  # noqa: BLE001 — R12 нет: точечные объекты ставим без улицы, освещение — нет
        pass
    if kind == "lighting" and shape.get("type") != "LineString":
        return None, f"{rid}: освещение без линии улицы (нет графа R12) — оставлена «Акимат проверяет»"
    body = {"kind": kind, "geometry": shape, "demo": True, "planned_year": now.year + 1}
    if street[0]:
        body["near_street"], body["near_street_kk"] = street[0], street[1]
    # Связь «проект ← идея» ставит _seed_idea после вставки идеи (внешний ключ civic_proposals.idea_id).
    item = proposals.create_in(conn, WORLD_ACTOR, body, stamp, idea_id=None)
    conn.execute("UPDATE civic_proposals SET world_key = ? WHERE id = ?", (key, item["id"]))
    return item["id"], None


def world_enabled() -> bool:
    """Режим демо-мира сборки (R01: CIVIC_DEMO=1 и CIVIC_DEMO_WORLD=1)."""
    return os.environ.get("CIVIC_DEMO") == "1" and os.environ.get("CIVIC_DEMO_WORLD") == "1"


__all__ = ["seed_world", "world_enabled"]
