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

Волна 2 (POLISH_WAVE_2): 6 демо-идей жителей в Нуре (п. 7) и 8 демо-записей «Что делают рядом» (п. 4).
  - Идеи — те же правила места, что у проектов (жилой квартал OSM, ≥ 60 м от площадок и парков, вне школ и детсадов,
    улица с названием ≤ 100 м — test_r06r14_wave2_demo.py). Тексты придуманы (demo, «Пример»), ru и kk (kk — черновик
    R06 на вычитку R11). Одна идея «стала проектом» — это демо-проект освещения улицы Ильяса Омарова; одна отклонена
    с причиной и «Можно доработать»; одна ждёт проверки (видна только сотруднику).
  - «Рядом» — пример R08 (ui/civic_akim/fixtures/nearby_demo.json): события придуманы, улицы настоящие, источник —
    общее название службы. Сроки — относительно сегодняшнего дня. Пустой «обход» («—») не храним.
"""

from __future__ import annotations

from datetime import timedelta
import secrets

from .ideas import IdeaRepository
from .nearby import NearbyRepository
from .objects import Actor, iso, utc_now
from .proposals import ProposalRepository
from .stages import StageRepository
from .world import world_enabled


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


def _point(lon, lat):
    return {"type": "Point", "coordinates": [lon, lat]}


# Идеи жителей (демо). votes — поддержек; у project/rejected — сколько было на момент решения.
YES, NO = "yes", "no"
DEMO_IDEAS = (
    {"key": "square", "status": "voting", "votes": 47, "place": "inside osm-way-257962279, улица Сыганак 73 м",
     "geometry": _point(71.364964, 51.132812),
     "object": {"kind": "square", "geometry": _point(71.364964, 51.132812), "rotation_deg": 15},
     "texts": {"title_ru": "Сквер у улицы Сыганак", "title_kk": "Сығанақ көшесі маңындағы гүлзар",
               "description_ru": "Во дворе нет тени и негде присесть. Нужны деревья, скамейки и урны.",
               "description_kk": "Аулада көлеңке жоқ, отыратын орын жоқ. Ағаштар, орындықтар мен қоқыс жәшіктері керек."}},
    {"key": "sports", "status": "voting", "votes": 23, "place": "landuse=residential, улица Ильяса Омарова 51 м",
     "geometry": _point(71.369444, 51.139359),
     "object": {"kind": "sports", "geometry": _point(71.369444, 51.139359)},
     "texts": {"title_ru": "Спортплощадка для подростков у улицы Ильяса Омарова",
               "title_kk": "Ілияс Омаров көшесі маңында жасөспірімдерге спорт алаңы",
               "description_ru": "Подросткам негде играть в футбол и баскетбол — играют на парковке.",
               "description_kk": "Жасөспірімдерге футбол мен баскетбол ойнайтын орын жоқ — тұрақта ойнайды."}},
    {"key": "gazebo", "status": "voting", "votes": 12, "place": "landuse=residential, улица Чингиза Айтматова 35 м",
     "geometry": _point(71.366098, 51.141718),
     "texts": {"title_ru": "Беседка и скамейки во дворе", "title_kk": "Аулада беседка мен орындықтар",
               "description_ru": "Пожилым жителям негде отдохнуть во дворе.",
               "description_kk": "Егде тұрғындарға аулада демалатын орын жоқ."}},
    # Стала проектом: демо-проект «Освещение улицы Ильяса Омарова» (точка — середина того же участка улицы).
    {"key": "lighting", "status": "project", "votes": 52, "project_kind": "lighting", "place": "osm-w1482578141-6",
     "geometry": _point(71.3688499, 51.1358187), "object": {"kind": "lighting"},
     "check": {"land": YES, "networks": YES, "access": YES, "maintenance": YES},
     "texts": {"title_ru": "Свет на улице Ильяса Омарова", "title_kk": "Ілияс Омаров көшесіне жарық",
               "description_ru": "Вечером на улице темно, страшно идти от остановки.",
               "description_kk": "Кешке көше қараңғы, аялдамадан жүру қорқынышты."}},
    {"key": "fountain", "status": "rejected", "votes": 8, "place": "inside osm-way-257962279, улица Ильяса Омарова 55 м",
     "geometry": _point(71.367439, 51.134156),
     "check": {"land": YES, "networks": NO, "access": YES, "maintenance": NO},
     "reason": "На участке нет водопровода, а содержание фонтана дорого для двора",
     "can_improve": "Предложите питьевой фонтанчик у сквера — к нему можно подвести воду",
     "texts": {"title_ru": "Фонтан во дворе", "title_kk": "Аулада субұрқақ",
               "description_ru": "Летом жарко, детям нужен фонтан.",
               "description_kk": "Жазда ыстық, балаларға субұрқақ керек.",
               "reason_ru": "На участке нет водопровода, а содержание фонтана дорого для двора",
               "reason_kk": "Учаскеде су құбыры жоқ, ал субұрқақты күтіп-ұстау аула үшін қымбат",
               "can_improve_ru": "Предложите питьевой фонтанчик у сквера — к нему можно подвести воду",
               "can_improve_kk": "Гүлзар жанынан ауыз су бұрқағын ұсыныңыз — оған су тартуға болады"}},
    # Ждёт проверки — видна только сотруднику («Идеи на проверке»). Место — остановка OSM «Ильяса Омарова».
    {"key": "bikes", "status": "review", "votes": 0, "place": "osm-node-5259599422 highway=bus_stop «Ильяса Омарова»",
     "geometry": _point(71.3677445, 51.1324657),
     "texts": {"title_ru": "Велопарковка у остановки «Ильяса Омарова»",
               "title_kk": "«Ильяса Омарова» аялдамасы жанында велотұрақ",
               "description_ru": "Велосипеды пристёгивают к деревьям.",
               "description_kk": "Велосипедтерді ағаштарға байлайды."}},
)


def _why(problem, reason, result, inconvenience):
    """4 строки «Зачем?» (ru, kk) → поля texts_json."""
    out = {}
    for key, (ru, kk) in zip(("problem", "reason", "result", "inconvenience"), (problem, reason, result, inconvenience)):
        out[f"why_{key}_ru"], out[f"why_{key}_kk"] = ru, kk
    return out


# «Что делают рядом» — пример R08 (fixtures/nearby_demo.json, тот же id): события придуманы, улицы настоящие.
DEMO_NEARBY = (
    {"demo_key": "nb-demo-water-nura", "type": "outage", "utility": "water", "district": "nura", "source": "water",
     "rel": {"when": {"day": 1, "from": "10:00", "to": "16:00"}, "updated_ago_min": 12},
     "texts": {"title_ru": "Не будет холодной воды", "title_kk": "Суық су болмайды",
               "zone_ru": "ул. Кабанбай батыра, 48–56", "zone_kk": "Қабанбай батыр көшесі, 48–56",
               "detour_ru": "Питьевая вода — в автоцистерне у дома 52 с 10:00",
               "detour_kk": "Ауыз су — 10:00-ден бастап 52-үй жанындағы автоцистернада",
               **_why(("Течь на водопроводе под двором", "Аула астындағы су құбыры ағып тұр"),
                      ("Трубу меняют днём, когда расход воды меньше", "Құбырды су аз жұмсалатын күндізгі уақытта ауыстырады"),
                      ("Напор во дворах вернётся к норме", "Аулалардағы су қысымы қалпына келеді"),
                      ("Без воды 6 часов, завтра 10:00–16:00", "6 сағат су болмайды, ертең 10:00–16:00"))}},
    {"demo_key": "nb-demo-road-nura", "type": "work", "status": "in_progress", "work_kind": "roadworks",
     "district": "nura", "rel": {"start_day": -12, "planned_end_day": 2, "forecast_end_day": 9, "updated_ago_min": 190},
     "texts": {"title_ru": "Ремонт дороги на улице Е-308", "title_kk": "Е-308 көшесінде жол жөндеу",
               **_why(("Ямы и провалы после замены труб", "Құбыр ауыстырылғаннан кейінгі шұңқырлар мен ойықтар"),
                      ("Сначала меняли трубы под дорогой, потом кладут асфальт — иначе пришлось бы вскрывать заново",
                       "Алдымен жол астындағы құбырларды ауыстырды, содан кейін асфальт төселеді — әйтпесе қайта қазуға тура келер еді"),
                      ("Новый асфальт и разметка на 600 м", "600 м жаңа асфальт пен жол таңбасы"),
                      ("Одна полоса закрыта; срок перенесён из-за дождей", "Бір жолақ жабық; жаңбырға байланысты мерзімі ауыстырылды"))}},
    {"demo_key": "nb-demo-yard-nura", "type": "work", "status": "done", "work_kind": "landscaping", "district": "nura",
     "rel": {"start_day": -40, "planned_end_day": -6, "forecast_end_day": -6, "updated_ago_min": 4300},
     "texts": {"title_ru": "Новая детская площадка во дворе", "title_kk": "Аулада жаңа балалар алаңы",
               **_why(("Старая площадка была опасной", "Ескі алаң қауіпті болды"),
                      ("Жители выбрали этот двор голосованием", "Тұрғындар осы аулаға дауыс берді"),
                      ("Безопасная площадка с мягким покрытием", "Жұмсақ төсемі бар қауіпсіз алаң"),
                      ("Работы закончены", "Жұмыс аяқталды"))}},
    {"demo_key": "nb-demo-light-nura", "type": "work", "status": "planned", "work_kind": "lighting", "district": "nura",
     "rel": {"start_day": 14, "planned_end_day": 30, "forecast_end_day": 30, "updated_ago_min": 2900},
     "texts": {"title_ru": "Освещение пешеходной дорожки", "title_kk": "Жаяу жүргіншілер жолын жарықтандыру",
               **_why(("Вечером на дорожке темно", "Кешке жолда қараңғы"),
                      ("Опоры ставят после окончания дорожного ремонта рядом",
                       "Тіректер жанындағы жол жөндеу аяқталған соң орнатылады"),
                      ("12 фонарей вдоль дорожки", "Жол бойында 12 шам"),
                      ("Дорожка закрыта 2 дня во время монтажа", "Монтаж кезінде жол 2 күн жабық"))}},
    {"demo_key": "nb-demo-heat-esil", "type": "outage", "utility": "heating", "district": "esil", "source": "heating",
     "rel": {"when": {"day": 0, "from": "08:00", "to": "20:00"}, "updated_ago_min": 35},
     "texts": {"title_ru": "Отопление включат позже", "title_kk": "Жылу кейінірек қосылады",
               "zone_ru": "ул. Сыганак, 10–14", "zone_kk": "Сығанақ көшесі, 10–14",
               **_why(("Промывка труб перед зимой", "Қыс алдында құбырларды жуу"),
                      ("Без промывки зимой батареи греют хуже", "Жумаса, қыста батареялар нашар жылытады"),
                      ("Ровное тепло во всех подъездах", "Барлық кіреберісте бірқалыпты жылу"),
                      ("Сегодня 08:00–20:00 батареи холодные", "Бүгін 08:00–20:00 батареялар суық"))}},
    {"demo_key": "nb-demo-close-esil", "type": "outage", "utility": "road_closure", "district": "esil", "source": "road",
     "rel": {"when": {"day": 2, "from": "22:00", "to": "06:00"}, "updated_ago_min": 70},
     "texts": {"title_ru": "Перекрытие проезда", "title_kk": "Жол жабылады",
               "zone_ru": "Проезд между ул. Достык и ул. Акмешит", "zone_kk": "Достық және Ақмешіт көшелері арасындағы өтпе жол",
               "detour_ru": "Объезд по ул. Кунаева", "detour_kk": "Қонаев көшесі арқылы айналып өту",
               **_why(("Замена бордюров", "Жиектасты ауыстыру"),
                      ("Ночью меньше машин — работы быстрее и безопаснее", "Түнде көлік аз — жұмыс тезірек әрі қауіпсіз"),
                      ("Ровные бордюры и пандусы у перехода", "Өткел жанында тегіс жиектас пен пандустар"),
                      ("Проезд закрыт ночью 22:00–06:00", "Түнде 22:00–06:00 жол жабық"))}},
    {"demo_key": "nb-demo-square-esil", "type": "work", "status": "in_progress", "work_kind": "landscaping",
     "district": "esil", "rel": {"start_day": -20, "planned_end_day": 20, "forecast_end_day": 20, "updated_ago_min": 600},
     "texts": {"title_ru": "Благоустройство сквера", "title_kk": "Скверді абаттандыру",
               **_why(("Разбитые дорожки и нет скамеек", "Жолдар бұзылған, орындық жоқ"),
                      ("Работы идут участками, чтобы сквер оставался открытым",
                       "Сквер ашық тұруы үшін жұмыс бөлікпен жүргізіледі"),
                      ("Новые дорожки, скамейки и деревья", "Жаңа жолдар, орындықтар мен ағаштар"),
                      ("Часть сквера огорожена до конца месяца", "Сквердің бір бөлігі ай соңына дейін қоршалған"))}},
    {"demo_key": "nb-demo-power-almaty", "type": "outage", "utility": "power", "district": "almaty", "source": "power",
     "rel": {"when": {"day": 3, "from": "09:00", "to": "13:00"}, "updated_ago_min": 240},
     "texts": {"title_ru": "Не будет света", "title_kk": "Жарық болмайды",
               "zone_ru": "ул. Жансугурова, 4–8", "zone_kk": "Жансүгіров көшесі, 4–8",
               **_why(("Старый кабель часто отключается", "Ескі кабель жиі сөніп қалады"),
                      ("Кабель меняют днём, в будни, когда дома меньше людей",
                       "Кабель адамдар үйде аз болатын жұмыс күні ауыстырылады"),
                      ("Меньше аварийных отключений зимой", "Қыста апаттық сөну азаяды"),
                      ("Без света 4 часа", "4 сағат жарық болмайды"))}},
)


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
                # R15-S20: случайный id — id, известный по исходникам, позволял любому перевернуть демо-голос.
                device = proposals.device_hash(conn, f"demo-seed-{secrets.token_hex(16)}")
                conn.execute("""INSERT OR IGNORE INTO civic_votes(proposal_id, device_hash, value, created_at,
                                    updated_at) VALUES (?, ?, ?, ?, ?)""",
                             (item["id"], device, 1 if n < up else -1, iso(now), iso(now)))
        report["proposals"].append({"kind": kind, "action": "create", "id": item["id"],
                                    "votes_up": up, "votes_down": down, "place": osm_ref})
    if world_enabled():
        # Раунд 15: демо-мир R02 (CIVIC_DEMO_WORLD=1) — идеи и «Рядом» засевает seed_world из мира, иначе в разделах
        # два демо-набора и числа расходятся. Этапы и 5 проектов выше (шаг 5 сценария) — как в FINAL-4.
        report["ideas"] = [{"action": "skipped", "reason": "demo world (seed_world R06)"}]
        report["nearby"] = [{"action": "skipped", "reason": "demo world (seed_world R06)"}]
        return report
    report["ideas"] = seed_demo_ideas(service, proposals)
    nearby = NearbyRepository(service.db, service.clock)
    report["nearby"] = [{"id": item["demo_key"], "action": "create" if nearby.seed_demo(item) else "kept"}
                        for item in DEMO_NEARBY]
    return report


def seed_demo_ideas(service, proposals) -> list[dict]:
    """Демо-идеи — один раз на базу (есть хоть одна демо-идея — ничего не делаем: настоящие не трогаются)."""
    ideas = IdeaRepository(service.db, service.clock, proposals)
    with service.db.read() as conn:
        if conn.execute("SELECT COUNT(*) FROM civic_ideas WHERE demo = 1").fetchone()[0]:
            return [{"action": "kept"}]
        project = {r["kind"]: r["id"] for r in conn.execute(
            "SELECT kind, id FROM civic_proposals WHERE demo = 1 AND status = 'proposal' AND idea_id IS NULL")}
    out = []
    for idea in DEMO_IDEAS:
        status, project_id = idea["status"], None
        if status == "project":
            project_id = project.get(idea["project_kind"])
            if project_id is None:  # демо-проекта нет (снят) — идея остаётся на голосовании
                status = "voting"
        seeded = ideas.seed_demo({**idea, "status": status}, votes=idea["votes"], project_id=project_id)
        out.append({"key": idea["key"], "action": "create", **seeded, "place": idea["place"]})
    return out
