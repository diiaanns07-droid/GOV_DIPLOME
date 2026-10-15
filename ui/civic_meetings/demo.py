"""Демо-набор «Встреч с акимом» (только CIVIC_DEMO=1 без демо-мира; demo: true — на экране метка «Пример / Үлгі»).

Три встречи акима района с жителями (ведущий — «аким района», без имени):
  m-demo-nura-next   — ближайшая, Нура, через 3 дня в 18:30: 54 «Приду», 6 вопросов с голосами + 1 на проверке;
  m-demo-nura-past   — Нура, 12 дней назад: итог и 5 поручений (выполнено, в работе, не начато, одно просрочено);
  m-demo-esil-past   — Есиль, 26 дней назад: итог и 4 поручения (3 выполнено, 1 в работе).
Места — настоящие дворы OSM (цели R12 «yard-…», подписи — как в поиске карты); всё остальное — синтетика:
тексты, числа, поручения и сроки придуманы, реальных людей и организаций нет. Время — относительно запуска.
«Приду» и голоса — числа «как будто раньше» (base_registered, base_votes), без выдуманных устройств (R15 S20).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

from .store import iso

ASTANA = timezone(timedelta(hours=5))
D = timedelta(days=1)
H = timedelta(hours=1)

# Настоящие дворы OSM из поиска карты (web/civic/map/search_index.json, ODbL): id, подписи, центр.
ECO_PARK = ({"kind": "area", "id": "yard-1424189376", "label_ru": "Двор: Eco Park", "label_kk": "Аула: Eco Park"},
            [71.39142, 51.12761])
RESPUBLIKA = ({"kind": "area", "id": "yard-1424189336", "label_ru": "Двор: Respublika",
               "label_kk": "Аула: Respublika"}, [71.38398, 51.12248])
ARGENTO = ({"kind": "area", "id": "yard-1209611630", "label_ru": "Двор: Argento", "label_kk": "Аула: Argento"},
           [71.4215, 51.11142])


def _local(now: datetime, days: int, hour: int, minute: int = 0) -> datetime:
    """Через days дней (минус — назад) в hour:minute по Астане -> UTC."""
    local = now.astimezone(ASTANA) + timedelta(days=days)
    return local.replace(hour=hour, minute=minute, second=0, microsecond=0).astimezone(timezone.utc)


def _date(moment: datetime, days: int) -> str:
    return (moment.astimezone(ASTANA) + timedelta(days=days)).date().isoformat()


def r09_demo_complaint(key: str) -> str:
    """id демо-жалобы R09 (ui/civic_feedback/v2/demo_seed.py: «c-demo» + sha256(key)[:16])."""
    return "c-demo" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def records(now: datetime) -> tuple[list[dict], list[dict], list[dict]]:
    """(встречи, поручения, вопросы) — детерминированно при одном now."""
    nxt = _local(now, 3, 18, 30)
    nura = _local(now, -12, 18, 0)
    esil = _local(now, -26, 17, 0)
    meetings = [
        {"id": "m-demo-nura-next", "district": "nura",
         "title_ru": "Встреча акима района Нура с жителями", "title_kk": "Нұра ауданы әкімінің тұрғындармен кездесуі",
         "at": iso(nxt), "duration_min": 90, "place": ECO_PARK[0], "point": ECO_PARK[1], "base_registered": 54,
         "created_at": iso(now - 6 * D)},
        {"id": "m-demo-nura-past", "district": "nura",
         "title_ru": "Встреча акима района Нура с жителями", "title_kk": "Нұра ауданы әкімінің тұрғындармен кездесуі",
         "at": iso(nura), "duration_min": 90, "place": RESPUBLIKA[0], "point": RESPUBLIKA[1], "base_registered": 61,
         "result_ru": "Пришли 58 жителей, прозвучали 14 вопросов. Главное — освещение дворов, разметка у школы и вывоз "
                      "строительного мусора. Аким района дал 5 поручений службам со сроками; ход работ — ниже.",
         "result_kk": "58 тұрғын келіп, 14 сұрақ қойылды. Негізгісі — аулаларды жарықтандыру, мектеп жанындағы жол "
                      "таңбасы және құрылыс қоқысын шығару. Аудан әкімі қызметтерге мерзімі көрсетілген 5 тапсырма "
                      "берді; жұмыс барысы — төменде.",
         "result_at": iso(nura + 20 * H), "created_at": iso(nura - 10 * D)},
        {"id": "m-demo-esil-past", "district": "esil",
         "title_ru": "Встреча акима района Есиль с жителями", "title_kk": "Есіл ауданы әкімінің тұрғындармен кездесуі",
         "at": iso(esil), "duration_min": 120, "place": ARGENTO[0], "point": ARGENTO[1], "base_registered": 47,
         "result_ru": "Пришли 44 жителя. Обсудили парковку во дворах, остановку без павильона и полив сквера. "
                      "Даны 4 поручения; 3 уже выполнены.",
         "result_kk": "44 тұрғын келді. Аулалардағы тұрақ, павильоны жоқ аялдама және скверді суару талқыланды. "
                      "4 тапсырма берілді; 3-еуі орындалды.",
         "result_at": iso(esil + 22 * H), "created_at": iso(esil - 9 * D)},
    ]
    nura_day, esil_day = nura, esil
    orders = [
        {"id": "o-demo-n1", "meeting_id": "m-demo-nura-past", "service": "lighting", "status": "in_progress",
         "text_ru": "Восстановить освещение на остановке «Хан Шатыр» и у детской площадки двора",
         "text_kk": "«Хан Шатыр» аялдамасы мен ауладағы балалар алаңының жарығын қалпына келтіру",
         "due": _date(nura_day, 20), "created_at": iso(nura + 20 * H), "updated_at": iso(now - 26 * H),
         "link": {"kind": "complaint", "id": r09_demo_complaint("khan-shatyr-lighting")}},
        {"id": "o-demo-n2", "meeting_id": "m-demo-nura-past", "service": "traffic", "status": "todo",
         "text_ru": "Нанести разметку пешеходного перехода у школы",
         "text_kk": "Мектеп жанындағы жаяу жүргіншілер өтпесінің жол таңбасын салу",
         "due": _date(nura_day, 10), "created_at": iso(nura + 20 * H)},
        {"id": "o-demo-n3", "meeting_id": "m-demo-nura-past", "service": "waste", "status": "done",
         "text_ru": "Вывезти строительный мусор со двора", "text_kk": "Ауладан құрылыс қоқысын шығару",
         "due": _date(nura_day, 5), "created_at": iso(nura + 20 * H), "updated_at": iso(nura + 3 * D),
         "done_at": iso(nura + 3 * D)},
        {"id": "o-demo-n4", "meeting_id": "m-demo-nura-past", "service": "water", "status": "in_progress",
         "text_ru": "Прочистить ливнёвку на улице вдоль двора до морозов",
         "text_kk": "Аяз түскенге дейін аула бойындағы көшенің нөсер кәрізін тазалау",
         "due": _date(nura_day, 25), "created_at": iso(nura + 20 * H), "updated_at": iso(now - 3 * D)},
        {"id": "o-demo-n5", "meeting_id": "m-demo-nura-past", "service": "landscaping", "status": "todo",
         "text_ru": "Подготовить проект новой детской площадки и показать жителям в «Идеях»",
         "text_kk": "Жаңа балалар алаңының жобасын дайындап, тұрғындарға «Идеялар» бөлімінде көрсету",
         "due": _date(nura_day, 40), "created_at": iso(nura + 20 * H)},
        {"id": "o-demo-e1", "meeting_id": "m-demo-esil-past", "service": "parking", "status": "done",
         "text_ru": "Разметить парковку во дворе и освободить проезд для пожарных",
         "text_kk": "Аулада тұрақ таңбасын салып, өрт сөндірушілерге жол ашу",
         "due": _date(esil_day, 14), "created_at": iso(esil + 22 * H), "updated_at": iso(esil + 9 * D),
         "done_at": iso(esil + 9 * D)},
        {"id": "o-demo-e2", "meeting_id": "m-demo-esil-past", "service": "transport", "status": "done",
         "text_ru": "Поставить павильон на остановке у двора", "text_kk": "Аула жанындағы аялдамаға павильон орнату",
         "due": _date(esil_day, 21), "created_at": iso(esil + 22 * H), "updated_at": iso(esil + 17 * D),
         "done_at": iso(esil + 17 * D)},
        {"id": "o-demo-e3", "meeting_id": "m-demo-esil-past", "service": "greenery", "status": "done",
         "text_ru": "Наладить полив сквера", "text_kk": "Скверді суаруды жолға қою",
         "due": _date(esil_day, 7), "created_at": iso(esil + 22 * H), "updated_at": iso(esil + 5 * D),
         "done_at": iso(esil + 5 * D)},
        {"id": "o-demo-e4", "meeting_id": "m-demo-esil-past", "service": "road", "status": "in_progress",
         "text_ru": "Отремонтировать тротуар вдоль двора", "text_kk": "Аула бойындағы тротуарды жөндеу",
         "due": _date(esil_day, 45), "created_at": iso(esil + 22 * H), "updated_at": iso(now - 2 * D)},
    ]
    close = iso(nxt)
    questions = [
        # (id, язык, текст, голоса, опубликован назад)
        ("q-demo-m01", "ru", "Когда во дворах Нуры поставят освещение у детских площадок? Вечером там совсем темно.",
         43, 5 * D),
        ("q-demo-m02", "kk", "Мектеп жанындағы жолға жаяу жүргіншілер өтпесі қашан салынады?", 37, 5 * D),
        ("q-demo-m03", "ru", "Можно ли пустить автобус до станции LRT чаще в утренний час пик?", 29, 4 * D),
        ("q-demo-m04", "ru", "Кто будет чистить снег во внутренних дворах этой зимой — УК или район?", 22, 3 * D),
        ("q-demo-m05", "kk", "Аулаларда қоқыс контейнерлері жиі толып кетеді. Шығару кестесін өзгертуге бола ма?",
         15, 2 * D),
        ("q-demo-m06", "ru", "Будет ли спортивная площадка для подростков рядом с новыми домами?", 9, 1 * D),
    ]
    q_rows = []
    for qid, lang, text, votes, ago in questions:
        q_rows.append({"id": qid, "district": "nura", "lang": lang, "text": text, "status": "published",
                       "created_at": iso(now - ago - 2 * H), "published_at": iso(now - ago), "base_votes": votes,
                       "meeting_id": "m-demo-nura-next", "votes_close_at": close})
    q_rows.append({"id": "q-demo-m07", "district": "nura", "lang": "ru",
                   "text": "Почему возле школы машины паркуются прямо на тротуаре?", "status": "pending",
                   "created_at": iso(now - 2 * H), "meeting_id": "m-demo-nura-next", "votes_close_at": close})
    # Вопросы прошедшей встречи — с ответом, данным на встрече (коротко, что решили).
    past = (
        ("q-demo-m11", "ru", "Когда починят свет на остановке «Хан Шатыр»?", 31,
         "Дано поручение службе освещения; срок — 20 дней после встречи.",
         "Жарықтандыру қызметіне тапсырма берілді; мерзімі — кездесуден кейін 20 күн."),
        ("q-demo-m12", "kk", "Мектеп алдында жол таңбасы өшіп қалған. Қашан жаңартылады?", 26,
         "Разметку нанесут по поручению службы светофоров и разметки.",
         "Жол таңбасы бағдаршам және жол таңбасы қызметіне берілген тапсырма бойынша салынады."),
    )
    for qid, lang, text, votes, ans_ru, ans_kk in past:
        q_rows.append({"id": qid, "district": "nura", "lang": lang, "text": text, "status": "published",
                       "created_at": iso(nura - 4 * D), "published_at": iso(nura - 4 * D + 2 * H), "base_votes": votes,
                       "answer_ru": ans_ru, "answer_kk": ans_kk, "answered_at": iso(nura + 20 * H),
                       "meeting_id": "m-demo-nura-past", "votes_close_at": iso(nura)})
    return meetings, orders, q_rows


def seed(service, now: datetime | None = None) -> dict:
    """Засеять демо-набор (идемпотентно). -> {"inserted", "skipped"}."""
    now = now or service.store.now()
    meetings, orders, questions = records(now)
    inserted, skipped = service.store.seed(meetings, orders)
    if service.qa is not None:
        made = service.qa.store.seed(questions, refresh=True)
        inserted += made
        skipped += len(questions) - made
    return {"inserted": inserted, "skipped": skipped}
