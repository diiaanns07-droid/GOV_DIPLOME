"""Демо-стенд R06 раунда 14: этапы у синтетических объектов и 5 предложений в Нуре.

    python -m ui.civic_store --db .runtime/civic.sqlite3 seed-r14-demo

Всё, что создаёт эта команда, — synthetic/demo:
  - этапы ставятся только объектам с evidence_type=synthetic (встроенный demo_package.json);
    у объекта, этап которого уже задал сотрудник (source=editor), ничего не меняется;
  - предложения помечены demo=true (интерфейс показывает «Пример»), голоса у них — тоже демо
    (устройства demo-seed-…); у настоящих предложений голоса не создаются никогда.
Команда идемпотентна: повторный запуск ничего не дублирует.

Геометрия: освещение — настоящий участок улицы Ильяса Омарова из пешеходного графа OSM
(engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json, рёбра osm-w1482578141-0…8,
ODbL © OpenStreetMap contributors). Точки остальных предложений — гипотетические места
рядом с этой улицей в районе Нура (предлагаемые объекты, а не существующие).
"""

from __future__ import annotations

from datetime import timedelta

from .objects import Actor, iso, utc_now
from .proposals import ProposalRepository
from .stages import StageRepository


DEMO_ACTOR = Actor(kind="system", user_id=None, label="seed-r14-demo", public_label="Демо-данные (синтетика)")
OMAROVA_SEGMENT = {  # рёбра osm-w1482578141-0…8, 396 м, район Нура
    "type": "LineString",
    "coordinates": [[71.3695148, 51.1376971], [71.369295, 51.1371074], [71.3692344, 51.1369249],
                    [71.369154, 51.1367237], [71.3690745, 51.1365186], [71.369041, 51.1364283],
                    [71.3688499, 51.1358187], [71.3687441, 51.1354795], [71.3686656, 51.1352723],
                    [71.3686027, 51.1351064], [71.3682669, 51.1342208]],
}
DEMO_PROPOSALS = (
    # kind, точка/линия, ru, kk, голоса за/против (демо)
    ("square", {"type": "Point", "coordinates": [71.3712, 51.1368]}, "Сквер у улицы Ильяса Омарова",
     "Ілияс Омаров көшесі жанындағы гүлзар", 128, 12),
    ("playground", {"type": "Point", "coordinates": [71.3705, 51.1352]}, "Детская площадка во дворе",
     "Аула ішіндегі балалар алаңы", 64, 5),
    ("sports", {"type": "Point", "coordinates": [71.3668, 51.1361]}, "Спортплощадка у школы",
     "Мектеп жанындағы спорт алаңы", 41, 9),
    ("stop", {"type": "Point", "coordinates": [71.36985, 51.13795]}, "Остановка с павильоном",
     "Павильоны бар аялдама", 23, 2),
    ("lighting", OMAROVA_SEGMENT, "Освещение улицы Ильяса Омарова", "Ілияс Омаров көшесін жарықтандыру", 87, 3),
)
# Этапы для синтетических объектов по кругу. Сроки — от сегодняшнего дня, чтобы демо всегда
# показывало одно и то же: первый объект отстаёт на 23 дня (как в макете UX_SPEC §6.2).
DEMO_STAGES = (
    ("procurement", -10, 13),   # план 10 дней назад, прогноз через 13 → «Отстаёт на 23 дня»
    ("design", 60, None),       # идёт по графику
    ("construction", 20, 26),   # прогноз на 6 дней позже плана
    ("acceptance", 3, None),
)


def seed_r14_demo(service) -> dict:
    stages = StageRepository(service.db, service.clock)
    proposals = ProposalRepository(service.db, service.clock)
    today = stages.today()
    report = {"stages": [], "proposals": [], "note": "synthetic/demo: не реальные работы и не реальные голоса"}
    with service.db.read() as conn:
        rows = conn.execute(
            """SELECT o.id, s.source FROM civic_public_objects p JOIN civic_objects o ON o.id = p.id
               LEFT JOIN civic_object_stages s ON s.object_id = o.id
               WHERE json_extract(o.data_json, '$.evidence_type') = 'synthetic'
               ORDER BY json_extract(o.data_json, '$.geometry') IS NULL, o.id""").fetchall()
        have_demo = {r["kind"] for r in conn.execute("SELECT kind FROM civic_proposals WHERE demo = 1")}
    for index, row in enumerate(rows):
        if row["source"] in ("editor", "demo"):
            report["stages"].append({"object_id": row["id"], "action": "kept", "source": row["source"]})
            continue
        stage, plan_shift, forecast_shift = DEMO_STAGES[index % len(DEMO_STAGES)]
        planned = (today + timedelta(days=plan_shift)).isoformat()
        forecast = (today + timedelta(days=forecast_shift)).isoformat() if forecast_shift is not None else None
        stages.seed_demo(row["id"], stage=stage, planned_end=planned, forecast_end=forecast)
        report["stages"].append({"object_id": row["id"], "action": "set", "stage": stage,
                                 "planned_end": planned, "forecast_end": forecast})
    now = utc_now(service.clock)
    for number, (kind, geometry, title_ru, title_kk, up, down) in enumerate(DEMO_PROPOSALS):
        if kind in have_demo:
            report["proposals"].append({"kind": kind, "action": "kept"})
            continue
        item = proposals.create(DEMO_ACTOR, {"kind": kind, "geometry": geometry, "title_ru": title_ru,
                                             "title_kk": title_kk, "planned_year": 2027, "demo": True})["item"]
        # Демо-голоса пишутся напрямую одной транзакцией (без ограничителя частоты HTTP).
        with service.db.write() as conn:
            for n in range(up + down):
                device = proposals.device_hash(conn, f"demo-seed-{number}-{n:05d}-device")
                conn.execute("""INSERT OR IGNORE INTO civic_votes(proposal_id, device_hash, value, created_at,
                                    updated_at) VALUES (?, ?, ?, ?, ?)""",
                             (item["id"], device, 1 if n < up else -1, iso(now), iso(now)))
        report["proposals"].append({"kind": kind, "action": "create", "id": item["id"],
                                    "votes_up": up, "votes_down": down})
    return report
