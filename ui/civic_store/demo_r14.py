"""Демо-стенд R06 раунда 14: этапы у синтетических объектов и 5 предложений в Нуре.

    python -m ui.civic_store --db .runtime/civic.sqlite3 seed-r14-demo

Всё, что создаёт эта команда, — synthetic/demo:
  - этапы ставятся только объектам с evidence_type=synthetic (встроенный demo_package.json или
    data/civic/astana/demo_synthetic.json сборки R01) — по статусу записи (demo_stage): идущие работы отстают,
    плановые — по графику или с затянутой закупкой, завершённые — «Работает»; отменённым, со статусом
    unknown и мероприятиям этап не ставится; у объекта, этап которого уже задал сотрудник (source=editor),
    ничего не меняется;
  - предложения помечены demo=true (интерфейс показывает «Пример»), голоса у них — тоже демо
    (устройства demo-seed-…); у настоящих предложений голоса не создаются никогда.
Команда идемпотентна: повторный запуск ничего не дублирует.

Геометрия — по реальным данным OSM (ODbL, © OpenStreetMap contributors), без точек «от руки»:
  - освещение — настоящий участок улицы Ильяса Омарова из пешеходного графа
    (engine/civic_scenarios/graphs/osm-astana-walking-20260506.graph.json, рёбра osm-w1482578141-0…8, 396 м).
    Фонарей highway=street_lamp в OSM у участка нет (ближайший — 3,4 км), но это полнота OSM, а не замер освещённости;
  - остановка — существующая остановка OSM «Жағалау-3» (osm-node-5254203835, 13 м от оси улицы): проект павильона
    на ней. Тега shelter у неё в OSM нет — «павильона нет» отсюда НЕ следует, это демо;
  - сквер, площадка, спортплощадка — точки внутри реальных жилых кварталов OSM района Нура (landuse=residential:
    way 1526197869 и «Жағалау шағын ауданы» way 257962279), не ближе 60 м к существующим площадкам, спортплощадкам,
    паркам и вне территорий школ и детсадов (data/civic/astana/osm-objects, LOCAL-1). Подбор и проверка —
    tests/civic/R06/round14/test_r06r14_demo_osm.py. Зданий в этих данных нет: попадание в дом не проверено.
  Прежние гипотетические точки отвергнуты этой проверкой: «площадка» стояла на территории школы, «спортплощадка» —
  в 25 м от существующей.
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
# Улицы рядом — ближайшая улица с названием по пешеходному графу OSM (≤ 100 м, проверка в test_r06r14_demo_osm.py);
# казахское название улицы — для «Жанында: …» в ҚАЗ (UX_REVIEW R11, ночь, п. 5), без него R05 улицу не показывает.
OMAROVA = ("улица Ильяса Омарова", "Ілияс Омаров көшесі")
AITMATOVA = ("улица Чингиза Айтматова", "Шыңғыс Айтматов көшесі")
DEMO_PROPOSALS = (
    # kind, точка/линия, ru, kk, голоса за/против (демо), откуда место (OSM), улица рядом (ru, kk)
    # kk-название упрощено по UX_REVIEW R11 (день 3, п. 19): «шағын аудандағы» лишнее.
    # Сквер: ближайшая улица по OSM — Айтматова (68 м), а не Омарова (308 м) — название исправлено (ночь 10→11 окт).
    ("square", {"type": "Point", "coordinates": [71.36554, 51.139097]}, "Сквер у улицы Чингиза Айтматова",
     "Шыңғыс Айтматов көшесі маңындағы гүлзар", 128, 12, "inside osm-way-1526197869 (landuse=residential)", AITMATOVA),
    ("playground", {"type": "Point", "coordinates": [71.366889, 51.132499]}, "Детская площадка в микрорайоне Жагалау",
     "Жағалау шағын ауданындағы балалар алаңы", 64, 5, "inside osm-way-257962279 «Жағалау шағын ауданы»", OMAROVA),
    ("sports", {"type": "Point", "coordinates": [71.36403, 51.135544]}, "Спортплощадка в микрорайоне Жагалау",
     "Жағалау шағын ауданындағы спорт алаңы", 41, 9, "inside osm-way-257962279 «Жағалау шағын ауданы»", AITMATOVA),
    ("stop", {"type": "Point", "coordinates": [71.3691001, 51.136005]}, "Павильон на остановке «Жағалау-3»",
     "«Жағалау-3» аялдамасындағы павильон", 23, 2, "osm-node-5254203835 highway=bus_stop «Жағалау-3»", OMAROVA),
    ("lighting", OMAROVA_SEGMENT, "Освещение улицы Ильяса Омарова", "Ілияс Омаров көшесін жарықтандыру", 87, 3,
     "osm-w1482578141-0…8 (пешеходный граф OSM)", OMAROVA),
)
# Этапы синтетических объектов — по их статусу и виду, чтобы карточка не спорила со своим названием
# (свой проход по UX_BRIEF: «Ремонт со сдвигом срока» шёл «по графику», а «Завершённый ремонт» — «отставал»).
# Сроки — от сегодняшнего дня: демо показывает одно и то же в любой день показа.
IN_PROGRESS_STAGE = ("construction", -10, 13)  # план 10 дней назад, прогноз через 13 → «Отстаёт на 23 дня» (UX_SPEC §6.2)
PLANNED_STAGES = (
    ("design", 60, None),        # идёт по графику
    ("procurement", 20, 26),     # закупка затянулась: прогноз на 6 дней позже плана
)
# Без демо-этапа (этап выводится из статуса, как после миграции 6): отменённые и с неизвестным статусом —
# честно «Этап работ не указан»; мероприятия — у них нет этапов стройки.
SKIP_STATUSES = ("cancelled", "unknown")
SKIP_KINDS = ("event",)


def demo_stage(status, kind, planned_index, today, actual_end=None):
    """(stage, planned_end, forecast_end) для синтетического объекта или None — этап не ставим."""
    if status in SKIP_STATUSES or kind in SKIP_KINDS:
        return None
    if status == "completed":
        done = actual_end or (today - timedelta(days=30)).isoformat()
        return "operating", done, None
    if status == "in_progress":
        stage, plan_shift, forecast_shift = IN_PROGRESS_STAGE
    else:
        stage, plan_shift, forecast_shift = PLANNED_STAGES[planned_index % len(PLANNED_STAGES)]
    planned = (today + timedelta(days=plan_shift)).isoformat()
    forecast = (today + timedelta(days=forecast_shift)).isoformat() if forecast_shift is not None else None
    return stage, planned, forecast


def seed_r14_demo(service) -> dict:
    stages = StageRepository(service.db, service.clock)
    proposals = ProposalRepository(service.db, service.clock)
    today = stages.today()
    report = {"stages": [], "proposals": [], "note": "synthetic/demo: не реальные работы и не реальные голоса"}
    with service.db.read() as conn:
        rows = conn.execute(
            """SELECT o.id, s.source, json_extract(o.data_json, '$.status') AS status,
                      json_extract(o.data_json, '$.kind') AS kind,
                      json_extract(o.data_json, '$.schedule.actual_end') AS actual_end
                 FROM civic_public_objects p JOIN civic_objects o ON o.id = p.id
               LEFT JOIN civic_object_stages s ON s.object_id = o.id
               WHERE json_extract(o.data_json, '$.evidence_type') = 'synthetic'
               ORDER BY json_extract(o.data_json, '$.geometry') IS NULL, o.id""").fetchall()
        have_demo = {r["kind"] for r in conn.execute("SELECT kind FROM civic_proposals WHERE demo = 1")}
    planned_index = 0
    for row in rows:
        if row["source"] in ("editor", "demo"):
            report["stages"].append({"object_id": row["id"], "action": "kept", "source": row["source"]})
            continue
        chosen = demo_stage(row["status"], row["kind"], planned_index, today, row["actual_end"])
        if chosen is None:
            report["stages"].append({"object_id": row["id"], "action": "skipped", "status": row["status"],
                                     "kind": row["kind"]})
            continue
        if row["status"] not in ("completed", "in_progress"):
            planned_index += 1
        stage, planned, forecast = chosen
        stages.seed_demo(row["id"], stage=stage, planned_end=planned, forecast_end=forecast)
        report["stages"].append({"object_id": row["id"], "action": "set", "stage": stage,
                                 "planned_end": planned, "forecast_end": forecast})
    now = utc_now(service.clock)
    for number, (kind, geometry, title_ru, title_kk, up, down, osm_ref, street) in enumerate(DEMO_PROPOSALS):
        if kind in have_demo:
            # Уже засеянная база (ноутбук владельца): обновить только тексты ДЕМО-записи этого вида, если они
            # устарели (например, название сквера). Голоса, статус и настоящие предложения не трогаются.
            with service.db.write() as conn:
                changed = conn.execute(
                    """UPDATE civic_proposals SET title_ru = ?, title_kk = ?, near_street = ?, near_street_kk = ?
                       WHERE demo = 1 AND kind = ? AND (title_ru IS NOT ? OR title_kk IS NOT ? OR near_street IS NOT ?
                             OR near_street_kk IS NOT ?)""",
                    (title_ru, title_kk, street[0], street[1], kind, title_ru, title_kk, street[0], street[1])).rowcount
            report["proposals"].append({"kind": kind, "action": "updated" if changed else "kept"})
            continue
        item = proposals.create(DEMO_ACTOR, {"kind": kind, "geometry": geometry, "title_ru": title_ru,
                                             "title_kk": title_kk, "planned_year": 2027, "demo": True,
                                             "near_street": street[0], "near_street_kk": street[1]})["item"]
        # Демо-голоса пишутся напрямую одной транзакцией (без ограничителя частоты HTTP).
        with service.db.write() as conn:
            for n in range(up + down):
                device = proposals.device_hash(conn, f"demo-seed-{number}-{n:05d}-device")
                conn.execute("""INSERT OR IGNORE INTO civic_votes(proposal_id, device_hash, value, created_at,
                                    updated_at) VALUES (?, ?, ?, ?, ?)""",
                             (item["id"], device, 1 if n < up else -1, iso(now), iso(now)))
        report["proposals"].append({"kind": kind, "action": "create", "id": item["id"],
                                    "votes_up": up, "votes_down": down, "place": osm_ref})
    return report
