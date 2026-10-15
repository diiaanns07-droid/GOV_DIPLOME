"""Демо-данные кризисного штаба: пример до демо-мира R02 и засев демо-мира (CONTRACT §11).

Всё синтетическое: demo: true, на экране слово «Пример». Время — относительно момента засева, поэтому демо всегда
«свежее». Повторный засев ничего не дублирует (seed_key). Реальных названий организаций и людей нет.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import crisis, geo, profiles
from .store import ASTANA, AgencyStore, iso, parse_iso

DEMO_BLIZZARD = "inc-demo-blizzard-nura"
DEMO_HEAT = "inc-demo-heat-saryarka"


def _demo_yards(district: str, n: int) -> list[str]:
    pool = sorted(y["id"] for y in geo.yards().values() if y["district"] == district)
    return pool[:n]


def demo_incidents(now: datetime) -> list[dict]:
    """Два примера: идёт «Буран» в Нуре (сцена 9) и закрытая «Авария теплосети» в Сарыарке (для хроники R07)."""
    tpl = crisis.TEMPLATES["blizzard"]
    started = now - timedelta(hours=5)
    blizzard = {
        "id": DEMO_BLIZZARD, "seed_key": "r17-demo:" + DEMO_BLIZZARD, "kind": "blizzard",
        "title_ru": "Буран в Нуре", "title_kk": "Нұрадағы боран",
        "zone": {"kind": "district", "district": "nura", "targets": [], "geometry": None},
        "started_at": iso(started), "status": "active",
        "tasks": [
            {"id": f"t-demo-bz-{i}", "service": s, "text_ru": ru, "text_kk": kk, "status": status}
            for i, ((s, ru, kk), status) in enumerate(zip(tpl["tasks"], ("doing", "done", "todo", "doing")), 1)
        ],
        "updates": [
            {"id": "u-demo-bz-1", "at": iso(started + timedelta(minutes=20)), "public": True,
             "text_ru": tpl["update_ru"], "text_kk": tpl["update_kk"]},
            {"id": "u-demo-bz-2", "at": iso(started + timedelta(hours=1, minutes=10)), "public": False,
             "text_ru": "Две снегоуборочные бригады переведены с проспекта на дворы у школ.",
             "text_kk": "Екі қар тазалау бригадасы даңғылдан мектеп маңындағы аулаларға ауыстырылды."},
            {"id": "u-demo-bz-3", "at": iso(started + timedelta(hours=3)), "public": True,
             "text_ru": "Автобусы ходят по зимней схеме. Остановки у школ расчищены.",
             "text_kk": "Автобустар қысқы сызба бойынша жүріп тұр. Мектеп маңындағы аялдамалар тазартылды."},
        ],
        "result": None,
    }
    yards = _demo_yards("saryarka", 3)
    heat_zone = ({"kind": "targets", "district": "saryarka", "targets": yards, "geometry": None} if yards
                 else {"kind": "district", "district": "saryarka", "targets": [], "geometry": None})
    heat_tpl = crisis.TEMPLATES["heat_outage"]
    heat_start = now - timedelta(days=9, hours=6)
    heat = {
        "id": DEMO_HEAT, "seed_key": "r17-demo:" + DEMO_HEAT, "kind": "heat_outage",
        "title_ru": "Авария теплосети", "title_kk": "Жылу желісіндегі апат",
        "zone": heat_zone, "started_at": iso(heat_start), "status": "closed",
        "closed_at": iso(heat_start + timedelta(hours=14)),
        "tasks": [{"id": f"t-demo-ht-{i}", "service": s, "text_ru": ru, "text_kk": kk, "status": "done"}
                  for i, (s, ru, kk) in enumerate(heat_tpl["tasks"], 1)],
        "updates": [
            {"id": "u-demo-ht-1", "at": iso(heat_start + timedelta(minutes=30)), "public": True,
             "text_ru": heat_tpl["update_ru"], "text_kk": heat_tpl["update_kk"]},
        ],
        "result": {"text_ru": "Трубу заменили, тепло вернули во все дома зоны.",
                   "text_kk": "Құбыр ауыстырылды, аймақтағы барлық үйге жылу қайта берілді."},
    }
    return [blizzard, heat]


def _insert(store: AgencyStore, spec: dict, *, demo: bool = True) -> bool:
    zone, district = crisis.parse_zone({k: v for k, v in spec["zone"].items() if k != "geometry"})
    tasks = [t for t in spec.get("tasks") or [] if t.get("service") in profiles.PROFILES]
    updates = list(spec.get("updates") or [])
    if spec.get("status") == "closed" and spec.get("result"):
        updates.append({"id": (spec["id"].replace("inc-", "u-") + "-closed")[:48], "at": spec.get("closed_at"),
                        "kind": "closed", "public": True, "text_ru": spec["result"].get("text_ru"),
                        "text_kk": spec["result"].get("text_kk")})
    _incident, created = store.create(
        kind=spec["kind"], title_ru=spec["title_ru"], title_kk=spec["title_kk"], zone=zone, district=district,
        tasks=tasks, by_role="demo", started_at=spec.get("started_at"), demo=demo, seed_key=spec.get("seed_key"),
        incident_id=spec.get("id"), status=spec.get("status", "active"), closed_at=spec.get("closed_at"),
        result=spec.get("result"), updates=updates)
    return created


def seed_demo_incidents(store: AgencyStore, now: datetime | None = None) -> dict:
    """Пример кризисов для демо-сборки без демо-мира (CIVIC_DEMO=1, CIVIC_DEMO_WORLD не 1). Идемпотентно."""
    now = (now or store.now()).astimezone(ASTANA).replace(microsecond=0)
    report = {"inserted": 0, "skipped": 0}
    for spec in demo_incidents(now):
        try:
            created = _insert(store, spec)
        except crisis.InputError:
            created = False
        report["inserted" if created else "skipped"] += 1
    return report


# ---------------------------------------------------------------------- демо-мир R02 (CONTRACT §11)
def _when(base: datetime, item: dict, prefix: str = "") -> str | None:
    """ISO-время из абсолютного поля или из относительных ago_days / ago_hours / in_days (+ prefix для вложенных)."""
    absolute = item.get(prefix + "at") if prefix else None
    if isinstance(absolute, str) and parse_iso(absolute):
        return iso(parse_iso(absolute))
    days = item.get(prefix + "ago_days")
    hours = item.get(prefix + "ago_hours")
    ahead = item.get(prefix + "in_days")
    if days is None and hours is None and ahead is None:
        return None
    moment = base - timedelta(days=float(days or 0), hours=float(hours or 0)) + timedelta(days=float(ahead or 0))
    return iso(moment)


def _world_incidents(records) -> list[dict]:
    if isinstance(records, dict):
        return [r for r in records.get("incidents") or [] if isinstance(r, dict)]
    return [r for r in records or [] if isinstance(r, dict) and str(r.get("id", "")).startswith("inc-")]


def from_world(item: dict, now: datetime) -> dict:
    """Кризис демо-мира (§5.5 + относительное время) → запись для store.create. Ошибка формата — ValueError."""
    if item.get("kind") not in crisis.TEMPLATES:
        raise ValueError("kind")
    started = item.get("started_at") if parse_iso(item.get("started_at")) else None
    started = iso(parse_iso(started)) if started else _when(now, item, "started_") or _when(now, item) or iso(now)
    closed = item.get("closed_at") if parse_iso(item.get("closed_at")) else None
    closed = iso(parse_iso(closed)) if closed else _when(now, item, "closed_")
    status = item.get("status") if item.get("status") in ("active", "closed") else ("closed" if closed else "active")
    if status == "closed" and not closed:
        closed = iso(now)
    updates = []
    for i, u in enumerate(item.get("updates") or []):
        if not isinstance(u, dict):
            continue
        at = (iso(parse_iso(u["at"])) if parse_iso(u.get("at")) else _when(now, u)) or started
        updates.append({"id": u.get("id") or f"{item['id'].replace('inc-', 'u-')}-{i}"[:48], "at": at,
                        "public": u.get("public", True) is not False, "text_ru": u.get("text_ru"),
                        "text_kk": u.get("text_kk")})
    # id задач демо-мира («t-1» у каждого кризиса) не берём: id задачи общий для базы — его даёт хранилище.
    tasks = [{"id": None, "service": t.get("service"), "text_ru": t.get("text_ru") or t.get("text_kk") or "",
              "text_kk": t.get("text_kk") or t.get("text_ru") or "",
              "status": t.get("status") if t.get("status") in ("todo", "doing", "done") else "todo"}
             for t in item.get("tasks") or [] if isinstance(t, dict)]
    return {"id": item["id"], "seed_key": "world:" + item["id"], "kind": item["kind"],
            "title_ru": item.get("title_ru") or crisis.TEMPLATES[item["kind"]]["title_ru"],
            "title_kk": item.get("title_kk") or crisis.TEMPLATES[item["kind"]]["title_kk"],
            "zone": item.get("zone") or {}, "started_at": started, "status": status, "closed_at": closed,
            "tasks": tasks, "updates": updates, "result": item.get("result")}


def seed_world(db_path, records, now: datetime | None = None) -> dict:
    """CONTRACT §11: из демо-мира R02 (world_v1.json или список записей) берём только кризисы (incidents).

    -> {"inserted", "skipped"}; повтор ничего не дублирует. Запись с неверной зоной или видом — skipped (в журнал
    сервера), остальное засевается. Время — относительно now (момента засева).
    """
    store = AgencyStore(db_path)
    now = (now or datetime.now(timezone.utc)).astimezone(ASTANA).replace(microsecond=0)
    report = {"inserted": 0, "skipped": 0}
    for item in _world_incidents(records):
        try:
            spec = from_world(item, now)
            created = _insert(store, spec, demo=item.get("demo", True) is not False)
        except (ValueError, KeyError, TypeError, crisis.InputError):
            created = False
        report["inserted" if created else "skipped"] += 1
    return report
