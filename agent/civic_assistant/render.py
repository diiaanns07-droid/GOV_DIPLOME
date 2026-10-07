"""Сборка текста ответа кодом из каталога фактов.

Каждое утверждение — отдельный statement со списком fact_ids и source_ids,
поэтому у каждой фразы есть опора. Формулировки фиксированы: ни модель, ни
шаблон не могут добавить «официально одобрено», «работы закончены» и т. п.,
если в карточке нет соответствующего значения. Цитаты (описание карточки,
причина из публичной истории) помечаются kind="quote" и приписываются карточке.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

NO_DATA = {"ru": "нет данных", "kk": "деректер жоқ"}

KIND_LABELS = {
    "ru": {"construction": "строительство", "roadworks": "дорожные работы", "landscaping": "благоустройство",
           "event": "мероприятие"},
    "kk": {"construction": "құрылыс", "roadworks": "жол жұмыстары", "landscaping": "абаттандыру",
           "event": "іс-шара"},
}
STATUS_LABELS = {
    "ru": {"planned": "запланировано", "in_progress": "идут работы", "completed": "завершено",
           "cancelled": "отменено", "unknown": "статус неизвестен"},
    "kk": {"planned": "жоспарланған", "in_progress": "жұмыс жүріп жатыр", "completed": "аяқталды",
           "cancelled": "тоқтатылды", "unknown": "мәртебесі белгісіз"},
}
BASIS_LABELS = {
    "ru": {"planned": "плановая сумма", "contract": "сумма по договору", "spent": "фактически освоено",
           "unknown": "основание суммы не указано"},
    "kk": {"planned": "жоспарлы сома", "contract": "шарт бойынша сома", "spent": "нақты игерілген",
           "unknown": "соманың негізі көрсетілмеген"},
}
ACCESS_LABELS = {
    "ru": {"fetched": "получен при проверке", "not_fetched": "не загружался при проверке",
           "unavailable": "был недоступен при проверке", None: "статус доступа не указан"},
    "kk": {"fetched": "тексеру кезінде алынды", "not_fetched": "тексеру кезінде жүктелмеді",
           "unavailable": "тексеру кезінде қолжетімсіз болды", None: "қолжетімділік күйі көрсетілмеген"},
}
GEOMETRY_LABELS = {
    "ru": {"Point": "точка", "LineString": "линия", "Polygon": "участок"},
    "kk": {"Point": "нүкте", "LineString": "сызық", "Polygon": "аумақ"},
}
PRECISION_LABELS = {
    "ru": {"source": "по источнику", "approximate": "приблизительно", "unknown": "точность неизвестна"},
    "kk": {"source": "дереккөз бойынша", "approximate": "шамамен", "unknown": "дәлдігі белгісіз"},
}
FIELD_LABELS = {
    "ru": {"title": "название", "description": "описание", "status": "статус", "kind": "тип",
           "geometry": "положение", "schedule": "сроки", "schedule.planned_start": "плановое начало",
           "schedule.original_planned_end": "первоначальный срок", "schedule.current_planned_end": "текущий срок",
           "schedule.actual_end": "фактическое окончание", "budget": "сумма", "budget.amount_kzt": "сумма",
           "responsible": "ответственный", "responsible.organization": "ответственная организация",
           "source_refs": "источники", "publication": "публикация"},
    "kk": {"title": "атауы", "description": "сипаттама", "status": "мәртебе", "kind": "түрі",
           "geometry": "орны", "schedule": "мерзімдер", "schedule.planned_start": "жоспарлы басталуы",
           "schedule.original_planned_end": "бастапқы мерзім", "schedule.current_planned_end": "ағымдағы мерзім",
           "schedule.actual_end": "нақты аяқталуы", "budget": "сома", "budget.amount_kzt": "сома",
           "responsible": "жауапты", "responsible.organization": "жауапты ұйым",
           "source_refs": "дереккөздер", "publication": "жариялау"},
}

T = {
    "ru": {
        "synthetic": "Это демонстрационная (синтетическая) запись, а не сведения о реальных работах.",
        "hypothesis": "Сведения карточки имеют статус гипотезы и не подтверждены источником.",
        "derived": "Сведения карточки выведены из других данных, а не взяты из источника напрямую.",
        "evidence_unknown": "Тип доказательности записи не указан.",
        "object": "Объект: «{title}» ({kind}).",
        "object_no_title": "Название объекта: нет данных.",
        "status": "Статус в карточке: {status}.",
        "description": "Описание в карточке: «{text}»",
        "current_end": "Текущий плановый срок окончания: {d}.",
        "original_end": "Первоначальный плановый срок окончания: {d}.",
        "planned_start": "Плановое начало: {d}.",
        "actual_end": "Фактическая дата окончания: {d}.",
        "planned_not_actual": "Плановый срок — это план; он не означает, что работы закончены.",
        "completed_status": "В карточке указан статус «завершено».",
        "cancelled": "В карточке указан статус «отменено»: даты ниже относятся к прежнему плану, это не ожидаемое окончание.",
        "completed_no_actual": "Фактическая дата окончания в карточке не указана.",
        "not_confirmed_done": "Завершение работ не подтверждено: в карточке нет даты фактического окончания.",
        "actual_status_conflict": "В карточке есть дата фактического окончания ({d}), но статус — «{status}». "
                                  "Это расхождение данных карточки.",
        "shift": "Текущий срок сдвинут относительно первоначального на {n} дн. (разница посчитана по датам карточки).",
        "shift_earlier": "Текущий срок раньше первоначального на {n} дн. (разница посчитана по датам карточки).",
        "no_shift": "Текущий плановый срок совпадает с первоначальным.",
        "shift_unknown": "Сравнить первоначальный и текущий срок нельзя: одной из дат нет.",
        "reason_quote": "В публичной истории (ревизия {r}, {at}) о сроках сказано: «{text}»",
        "reason_missing": "Причина изменения сроков в публичной истории не указана — нет данных.",
        "organization": "Ответственная организация (как в карточке): «{v}».",
        "organization_missing": "Ответственная организация в карточке не указана — нет данных.",
        "contact": "Публичный контакт (как в карточке): «{v}».",
        "contact_missing": "Публичный контакт: нет данных.",
        "amount": "Сумма: {v} ₸ ({basis}).",
        "amount_missing": "Сумма в карточке не указана — нет данных.",
        "amount_source": "Источник суммы: {src}.",
        "amount_source_missing": "Источник суммы не указан.",
        "source": "Источник: «{publisher}»; опубликовано: {published}; получено системой: {retrieved}; доступ: {access}; "
                  "лицензия: {license}{url}.",
        "source_url": "; ссылка: {u}",
        "no_sources": "У записи нет ссылок на источники.",
        "old_plan": "Публикация плана не доказывает фактическое состояние работ.",
        "history_entry": "Ревизия {r} ({at}): изменено — {fields}.",
        "history_reason": "Причина, указанная в публичной истории: «{text}»",
        "history_none": "Публичной истории изменений нет.",
        "history_more": "Показаны только последние записи истории.",
        "location": "Положение на карте: {geom}, точность — {precision}.",
        "location_none": "Достоверной геометрии нет; объект показан списком.",
        "access_none": "Расчёт доступности для этого объекта не подключён — нет данных. "
                       "Помощник не оценивает пробки и время в пути без расчёта движка.",
        "scenario_none": "Результат сравнения сценариев не передан — нет данных.",
        "unsupported": "Я отвечаю только по опубликованным сведениям карточки: что происходит, сроки, статус, "
                       "ответственный, сумма, источники и история изменений. Этот вопрос вне этих данных.",
        "unavailable": "Помощник сейчас не может ответить: опубликованные сведения по этому объекту недоступны.",
        "clarify": "Вопрос не распознан, поэтому помощник не отвечает наугад. Можно спросить: что здесь происходит, "
                   "когда закончат, почему перенесли срок, подтверждено ли завершение, кто отвечает, сколько стоит, откуда "
                   "данные, насколько они свежие, что менялось, какие сведения отсутствуют.",
        "clarify_scenario": "Вопрос не распознан, поэтому помощник не отвечает наугад. О сценарии можно спросить: "
                            "чем план A отличается от B, как изменится проход, насколько полные данные сети.",
        "unavailable_result_expired": "Сохранённый результат вашего расчёта больше не хранится на сервере. Выполните "
                                      "сравнение заново — помощник не подставляет другой сценарий.",
        "unavailable_result_unknown": "Результат расчёта с таким идентификатором на сервере не найден. Выполните "
                                      "сравнение заново — помощник не подставляет другой сценарий.",
        "unavailable_scenario": "Сценарий с таким идентификатором недоступен — помощник не подставляет другой сценарий.",
        "revision_changed": "Карточка объекта изменилась после того, как вы её открыли: сейчас опубликована редакция {r}. "
                            "Обновите карточку и задайте вопрос снова — помощник не отвечает по устаревшей редакции.",
        "freshness_card": "Карточка обновлена в системе {d} (редакция {r}). Это дата изменения записи, а не дата проверки "
                          "работ на месте.",
        "freshness_card_missing": "Дата обновления карточки: нет данных.",
        "freshness_source": "Источник «{publisher}»: опубликован {published}; получен системой {retrieved}; доступ при "
                            "проверке: {access}.",
        "freshness_source_note": "Дата публикации — когда источник выпустил сведения; дата получения — когда система их "
                                 "загрузила. Ни одна из них не подтверждает, что сведения верны сегодня.",
        "freshness_no_sources": "У записи нет источников — подтвердить свежесть сведений нечем.",
        "freshness_none": "Сведений о датах данных нет.",
        "freshness_unknown_after": "Помощник не знает, менялось ли что-то после этих дат.",
        "no_active_closure_claim": "Помощник не делает вывода, что перекрытие действует сейчас: объявление о работах или план "
                                   "не подтверждают текущее состояние на месте.",
        "unknown_value": "нет данных",
        "unknown_actor": "",
        "missing_list": "В опубликованной карточке не указано: {fields}.",
        "missing_none": "Основные поля карточки заполнены: сроки, ответственный, сумма с источником, место и источники.",
        "missing_reason": "Срок сдвинут, но причина в публичной истории не указана.",
        "missing_note": "Пустое поле означает, что сведений нет, а не ноль и не «всё в порядке».",
        "missing_labels": {"schedule.current_planned_end": "текущий плановый срок окончания",
                           "schedule.original_planned_end": "первоначальный срок окончания",
                           "schedule.planned_start": "плановое начало",
                           "schedule.actual_end": "фактическая дата окончания",
                           "budget.amount_kzt": "сумма", "budget.source_id": "источник суммы",
                           "responsible.organization": "ответственная организация",
                           "responsible.public_contact": "публичный контакт",
                           "object.geometry_type": "место на карте", "sources": "источники сведений",
                           "object.description": "описание"},
    },
    "kk": {
        "synthetic": "Бұл демонстрациялық (синтетикалық) жазба, нақты жұмыстар туралы мәлімет емес.",
        "hypothesis": "Карточкадағы мәліметтер болжам мәртебесінде, дереккөзбен расталмаған.",
        "derived": "Карточкадағы мәліметтер дереккөзден тікелей емес, басқа деректерден шығарылған.",
        "evidence_unknown": "Жазбаның дәлелдік түрі көрсетілмеген.",
        "object": "Нысан: «{title}» ({kind}).",
        "object_no_title": "Нысан атауы: деректер жоқ.",
        "status": "Карточкадағы мәртебе: {status}.",
        "description": "Карточкадағы сипаттама: «{text}»",
        "current_end": "Ағымдағы жоспарлы аяқталу мерзімі: {d}.",
        "original_end": "Бастапқы жоспарлы аяқталу мерзімі: {d}.",
        "planned_start": "Жоспарлы басталу күні: {d}.",
        "actual_end": "Нақты аяқталу күні: {d}.",
        "planned_not_actual": "Жоспарлы мерзім — жоспар ғана; ол жұмыстың аяқталғанын білдірмейді.",
        "completed_status": "Карточкада «аяқталды» мәртебесі көрсетілген.",
        "cancelled": "Карточкада «тоқтатылды» мәртебесі көрсетілген: төмендегі күндер бұрынғы жоспарға қатысты, күтілетін аяқталу емес.",
        "completed_no_actual": "Нақты аяқталу күні карточкада көрсетілмеген.",
        "not_confirmed_done": "Жұмыстың аяқталуы расталмаған: карточкада нақты аяқталу күні жоқ.",
        "actual_status_conflict": "Карточкада нақты аяқталу күні бар ({d}), бірақ мәртебесі — «{status}». "
                                  "Бұл карточка деректеріндегі сәйкессіздік.",
        "shift": "Ағымдағы мерзім бастапқыдан {n} күнге кейін жылжыды (карточкадағы күндер бойынша есептелді).",
        "shift_earlier": "Ағымдағы мерзім бастапқыдан {n} күн ерте (карточкадағы күндер бойынша есептелді).",
        "no_shift": "Ағымдағы жоспарлы мерзім бастапқымен сәйкес.",
        "shift_unknown": "Бастапқы және ағымдағы мерзімді салыстыру мүмкін емес: күндердің бірі жоқ.",
        "reason_quote": "Жария тарихта ({r}-нұсқа, {at}) мерзім туралы былай жазылған: «{text}»",
        "reason_missing": "Мерзімді өзгерту себебі жария тарихта көрсетілмеген — деректер жоқ.",
        "organization": "Жауапты ұйым (карточкадағыдай): «{v}».",
        "organization_missing": "Жауапты ұйым карточкада көрсетілмеген — деректер жоқ.",
        "contact": "Жария байланыс (карточкадағыдай): «{v}».",
        "contact_missing": "Жария байланыс: деректер жоқ.",
        "amount": "Сома: {v} ₸ ({basis}).",
        "amount_missing": "Сома карточкада көрсетілмеген — деректер жоқ.",
        "amount_source": "Сома дереккөзі: {src}.",
        "amount_source_missing": "Сома дереккөзі көрсетілмеген.",
        "source": "Дереккөз: «{publisher}»; жарияланған күні: {published}; жүйе алған күні: {retrieved}; қолжетімділік: "
                  "{access}; лицензия: {license}{url}.",
        "source_url": "; сілтеме: {u}",
        "no_sources": "Жазбада дереккөзге сілтеме жоқ.",
        "old_plan": "Жоспардың жариялануы жұмыстың нақты жағдайын дәлелдемейді.",
        "history_entry": "{r}-нұсқа ({at}): өзгертілді — {fields}.",
        "history_reason": "Жария тарихта көрсетілген себеп: «{text}»",
        "history_none": "Жария өзгерістер тарихы жоқ.",
        "history_more": "Тарихтың тек соңғы жазбалары көрсетілді.",
        "location": "Картадағы орны: {geom}, дәлдігі — {precision}.",
        "location_none": "Сенімді геометрия жоқ; нысан тізіммен көрсетіледі.",
        "access_none": "Бұл нысан үшін қолжетімділік есебі қосылмаған — деректер жоқ. "
                       "Көмекші қозғалыс кептелісін және жол уақытын қозғалтқыш есебінсіз бағаламайды.",
        "scenario_none": "Сценарийлерді салыстыру нәтижесі берілмеген — деректер жоқ.",
        "unsupported": "Мен тек карточкадағы жарияланған мәліметтер бойынша жауап беремін: не болып жатыр, мерзімдер, "
                       "мәртебе, жауапты ұйым, сома, дереккөздер және өзгерістер тарихы. Бұл сұрақ осы деректерден тыс.",
        "unavailable": "Көмекші қазір жауап бере алмайды: бұл нысан бойынша жарияланған мәліметтер қолжетімсіз.",
        "clarify": "Сұрақ танылмады, сондықтан көмекші болжап жауап бермейді. Мынаны сұрауға болады: мұнда не болып "
                   "жатыр, қашан аяқталады, мерзім неге ауыстырылды, жұмыстың аяқталуы расталған ба, кім жауапты, қанша тұрады, "
                   "деректер қайдан, олар қаншалықты өзекті, не өзгерді, қандай мәліметтер жоқ.",
        "clarify_scenario": "Сұрақ танылмады, сондықтан көмекші болжап жауап бермейді. Сценарий туралы сұрауға болады: "
                            "A жоспарының B-дан айырмашылығы, өту қалай өзгереді, желі деректері қаншалықты толық.",
        "unavailable_result_expired": "Сіздің есебіңіздің сақталған нәтижесі серверде енді сақталмайды. Салыстыруды "
                                      "қайта орындаңыз — көмекші басқа сценарийді қоймайды.",
        "unavailable_result_unknown": "Мұндай идентификатормен есеп нәтижесі серверде табылмады. Салыстыруды қайта "
                                      "орындаңыз — көмекші басқа сценарийді қоймайды.",
        "unavailable_scenario": "Мұндай идентификатормен сценарий қолжетімсіз — көмекші басқа сценарийді қоймайды.",
        "revision_changed": "Сіз ашқаннан кейін нысан карточкасы өзгерді: қазір {r}-нұсқа жарияланған. Карточканы "
                            "жаңартып, сұрақты қайта қойыңыз — көмекші ескірген нұсқа бойынша жауап бермейді.",
        "freshness_card": "Карточка жүйеде {d} жаңартылды ({r}-нұсқа). Бұл жазбаның өзгерген күні, жұмыстың орнында "
                          "тексерілген күні емес.",
        "freshness_card_missing": "Карточканың жаңартылған күні: деректер жоқ.",
        "freshness_source": "«{publisher}» дереккөзі: {published} жарияланған; жүйе {retrieved} алған; тексеру кезіндегі "
                            "қолжетімділік: {access}.",
        "freshness_source_note": "Жариялану күні — дереккөз мәліметті шығарған күн; алыну күні — жүйе оны жүктеген күн. "
                                 "Екеуі де мәліметтің бүгін дұрыс екенін растамайды.",
        "freshness_no_sources": "Жазбада дереккөз жоқ — мәліметтің өзектілігін растайтын ештеңе жоқ.",
        "freshness_none": "Деректердің күндері туралы мәлімет жоқ.",
        "freshness_unknown_after": "Осы күндерден кейін бірдеңе өзгергенін көмекші білмейді.",
        "no_active_closure_claim": "Көмекші жабылу қазір әрекет етеді деп айтпайды: жұмыс туралы хабарландыру немесе "
                                   "жоспар орындағы қазіргі жағдайды растамайды.",
        "unknown_value": "деректер жоқ",
        "unknown_actor": "",
        "missing_list": "Жарияланған карточкада көрсетілмеген: {fields}.",
        "missing_none": "Карточканың негізгі өрістері толтырылған: мерзімдер, жауапты ұйым, дереккөзі бар сома, орны және дереккөздер.",
        "missing_reason": "Мерзім жылжыған, бірақ себебі жария тарихта көрсетілмеген.",
        "missing_note": "Бос өріс мәлімет жоқ дегенді білдіреді, нөл немесе «бәрі дұрыс» дегенді емес.",
        "missing_labels": {"schedule.current_planned_end": "ағымдағы жоспарлы аяқталу мерзімі",
                           "schedule.original_planned_end": "бастапқы аяқталу мерзімі",
                           "schedule.planned_start": "жоспарлы басталуы",
                           "schedule.actual_end": "нақты аяқталу күні",
                           "budget.amount_kzt": "сома", "budget.source_id": "соманың дереккөзі",
                           "responsible.organization": "жауапты ұйым",
                           "responsible.public_contact": "жария байланыс",
                           "object.geometry_type": "картадағы орны", "sources": "мәліметтер дереккөздері",
                           "object.description": "сипаттама"},
    },
}


def fmt_date(value: str | None, lang: str) -> str:
    if not value:
        return NO_DATA[lang]
    d = date.fromisoformat(value)
    return f"{d.day:02d}.{d.month:02d}.{d.year:04d}"


def fmt_at(value: str | None, lang: str) -> str:
    """Отметка времени истории -> дата DD.MM.YYYY; нераспознанная -> «нет данных»."""
    if isinstance(value, str) and len(value) >= 10:
        try:
            return fmt_date(date.fromisoformat(value[:10]).isoformat(), lang)
        except ValueError:
            pass
    return NO_DATA[lang]


def fmt_money(value) -> str:
    """Меняется только запись числа: группы разрядов, без округления и пересчёта."""
    dec = Decimal(str(value))
    sign, digits = "", format(dec, "f")
    whole, _, frac = digits.partition(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    text = " ".join(groups)
    frac = frac.rstrip("0")
    return sign + text + ("," + frac if frac else "")


def _st(text, fact_ids=(), kind="fact", facts=None):
    sources = set()
    if facts is not None:
        for fid in fact_ids:
            sources.update(facts.get(fid, {}).get("source_ids", []))
    return {"text": text, "kind": kind, "fact_ids": list(dict.fromkeys(fact_ids)), "source_ids": sorted(sources)}


def _req(st):
    """Обязательная фраза: выбор фактов моделью не может её убрать (оговорки о статусе/отсутствии данных)."""
    st["required"] = True
    return st


def _v(facts, fid):
    f = facts.get(fid)
    return f["value"] if f and f["known"] else None


def evidence_notice(facts, lang) -> list[dict]:
    """Обязательная пометка типа доказательности: synthetic виден в каждом ответе."""
    if "object.evidence_type" not in facts:
        return []
    ev = _v(facts, "object.evidence_type")
    key = {"synthetic": "synthetic", "hypothesis": "hypothesis", "derived": "derived", None: "evidence_unknown"}.get(ev)
    if key is None:
        return []
    return [_st(T[lang][key], ["object.evidence_type"], kind="notice")]


def r_overview(facts, lang):
    t = T[lang]
    out = []
    title, kind = _v(facts, "object.title"), _v(facts, "object.kind")
    if title:
        out.append(_st(t["object"].format(title=title, kind=KIND_LABELS[lang].get(kind, NO_DATA[lang])),
                       ["object.title", "object.kind"], facts=facts))
    else:
        out.append(_st(t["object_no_title"], ["object.title"], kind="missing"))
    out.append(_st(t["status"].format(status=STATUS_LABELS[lang][_v(facts, "object.status") or "unknown"]),
                   ["object.status"], facts=facts))
    desc = _v(facts, "object.description")
    if desc:
        out.append(_st(t["description"].format(text=desc), ["object.description"], kind="quote", facts=facts))
    out += r_schedule(facts, lang, brief=True)
    return out


def r_status(facts, lang):
    t = T[lang]
    status = _v(facts, "object.status") or "unknown"
    actual = _v(facts, "schedule.actual_end")
    current = _v(facts, "schedule.current_planned_end")
    out = []
    if status == "completed":
        out.append(_req(_st(t["completed_status"], ["object.status"], facts=facts)))
        if actual:
            out.append(_req(_st(t["actual_end"].format(d=fmt_date(actual, lang)), ["schedule.actual_end"], facts=facts)))
        else:
            out.append(_req(_st(t["completed_no_actual"], ["schedule.actual_end"], kind="missing")))
        return out
    if status == "cancelled":
        out.append(_req(_st(t["cancelled"], ["object.status"], kind="notice", facts=facts)))
        return out
    out.append(_req(_st(t["status"].format(status=STATUS_LABELS[lang][status]), ["object.status"], facts=facts)))
    if actual:
        out.append(_st(t["actual_status_conflict"].format(d=fmt_date(actual, lang), status=STATUS_LABELS[lang][status]),
                       ["schedule.actual_end", "object.status"], kind="notice", facts=facts))
    else:
        out.append(_req(_st(t["not_confirmed_done"], ["schedule.actual_end"], kind="missing")))
    if current:
        out.append(_st(t["current_end"].format(d=fmt_date(current, lang)), ["schedule.current_planned_end"], facts=facts))
        out.append(_st(t["planned_not_actual"], ["schedule.current_planned_end"], kind="notice"))
    return out


def _cancelled_notice(facts, lang):
    if _v(facts, "object.status") == "cancelled":
        return [_req(_st(T[lang]["cancelled"], ["object.status"], kind="notice", facts=facts))]
    return []


def r_schedule(facts, lang, brief=False):
    t = T[lang]
    out = [] if brief else _cancelled_notice(facts, lang)
    current = _v(facts, "schedule.current_planned_end")
    kind = "fact" if current else "missing"
    out.append(_req(_st(t["current_end"].format(d=fmt_date(current, lang)), ["schedule.current_planned_end"], kind,
                        facts)))
    if brief:
        if current and not _v(facts, "schedule.actual_end"):
            out.append(_st(t["planned_not_actual"], ["schedule.current_planned_end"], kind="notice"))
        return out
    for key, fid in (("original_end", "schedule.original_planned_end"), ("planned_start", "schedule.planned_start")):
        val = _v(facts, fid)
        out.append(_st(t[key].format(d=fmt_date(val, lang)), [fid], "fact" if val else "missing", facts))
    actual = _v(facts, "schedule.actual_end")
    out.append(_st(t["actual_end"].format(d=fmt_date(actual, lang)), ["schedule.actual_end"],
                   "fact" if actual else "missing", facts))
    out += _shift(facts, lang)
    if not actual:
        out.append(_st(t["planned_not_actual"], ["schedule.current_planned_end"], kind="notice"))
    return out


def _shift(facts, lang):
    t = T[lang]
    shift = _v(facts, "schedule.shift_days")
    ids = ["schedule.shift_days", "schedule.original_planned_end", "schedule.current_planned_end"]
    if shift is None:
        return [_st(t["shift_unknown"], ids, kind="missing")]
    if shift > 0:
        return [_st(t["shift"].format(n=shift), ids, kind="derived", facts=facts)]
    if shift < 0:
        return [_st(t["shift_earlier"].format(n=-shift), ids, kind="derived", facts=facts)]
    return [_st(t["no_shift"], ids, kind="derived", facts=facts)]


def _history(facts):
    return [f for fid, f in facts.items() if fid.startswith("history.r")]


def r_delay_reason(facts, lang):
    t = T[lang]
    out = _cancelled_notice(facts, lang)
    for key, fid in (("original_end", "schedule.original_planned_end"), ("current_end", "schedule.current_planned_end")):
        val = _v(facts, fid)
        out.append(_st(t[key].format(d=fmt_date(val, lang)), [fid], "fact" if val else "missing", facts))
    out += _shift(facts, lang)
    hist = _history(facts)
    # История может быть неполной: первая доступная запись тоже может содержать перенос.
    # Учитываем явное изменение текущего срока независимо от позиции записи.
    reasons = [h for h in hist if h["value"]["reason"]
               and "schedule.current_planned_end" in h["value"]["changed_fields"]]
    if not reasons:
        # Старый контракт мог отмечать весь schedule; цитируем его без вывода
        # о конкретной изменённой дате. Явная публикация не является переносом.
        reasons = [h for h in hist if h["value"]["reason"]
                   and "schedule" in h["value"]["changed_fields"]
                   and "publication" not in h["value"]["changed_fields"]]
    for h in reasons[-3:]:
        e = h["value"]
        out.append(_st(t["reason_quote"].format(r=e["revision"], at=fmt_at(e["at"], lang), text=e["reason"]),
                       [h["id"]], kind="quote"))
    if not reasons:
        out.append(_req(_st(t["reason_missing"], [h["id"] for h in hist][-3:], kind="missing")))
    return out


def r_responsible(facts, lang):
    t = T[lang]
    org, contact = _v(facts, "responsible.organization"), _v(facts, "responsible.public_contact")
    return [
        _st(t["organization"].format(v=org), ["responsible.organization"], facts=facts) if org
        else _st(t["organization_missing"], ["responsible.organization"], kind="missing"),
        _st(t["contact"].format(v=contact), ["responsible.public_contact"], facts=facts) if contact
        else _st(t["contact_missing"], ["responsible.public_contact"], kind="missing"),
    ]


def _source_text(ref, lang):
    t = T[lang]
    return t["source"].format(
        publisher=ref["publisher"] or NO_DATA[lang],
        published=fmt_date(ref["published_on"], lang),
        retrieved=fmt_at(ref["retrieved_at"], lang),
        access=ACCESS_LABELS[lang][ref["access_status"]],
        license=ref["license"] or NO_DATA[lang],
        url=t["source_url"].format(u=ref["url"]) if ref["url"] else "",
    )


def r_budget(facts, lang):
    t = T[lang]
    amount = _v(facts, "budget.amount_kzt")
    basis = _v(facts, "budget.basis") or "unknown"
    out = []
    if amount is None:
        out.append(_req(_st(t["amount_missing"], ["budget.amount_kzt"], kind="missing")))
    else:
        out.append(_req(_st(t["amount"].format(v=fmt_money(amount), basis=BASIS_LABELS[lang][basis]),
                            ["budget.amount_kzt", "budget.basis"], facts=facts)))
    sid = _v(facts, "budget.source_id")
    ref = _v(facts, "source." + sid) if sid else None
    if ref:
        out.append(_st(t["amount_source"].format(src=_source_text(ref, lang).rstrip(".")),
                       ["budget.source_id", "source." + sid], facts=facts))
    else:
        out.append(_st(t["amount_source_missing"], ["budget.source_id"], kind="missing"))
    return out


def r_sources(facts, lang):
    t = T[lang]
    out = []
    refs = [f for fid, f in facts.items() if fid.startswith("source.")]
    for f in refs:
        out.append(_st(_source_text(f["value"], lang), [f["id"]]))
    if not refs:
        out.append(_st(t["no_sources"], [], kind="missing"))
    if refs:
        out.append(_st(t["old_plan"], [], kind="notice"))
    return out


def r_history(facts, lang, limit=5):
    t = T[lang]
    hist = _history(facts)
    out = []
    for h in hist[-limit:]:
        e = h["value"]
        labels = [FIELD_LABELS[lang].get(c, c) for c in e["changed_fields"]] or [NO_DATA[lang]]
        out.append(_st(t["history_entry"].format(r=e["revision"], at=fmt_at(e["at"], lang),
                                                 fields=", ".join(dict.fromkeys(labels))), [h["id"]]))
        if e["reason"]:
            out.append(_st(t["history_reason"].format(text=e["reason"]), [h["id"]], kind="quote"))
    if not hist:
        out.append(_st(t["history_none"], [], kind="missing"))
    elif len(hist) > limit:
        out.append(_st(t["history_more"], [], kind="notice"))
    return out


def r_location(facts, lang):
    t = T[lang]
    geom = _v(facts, "object.geometry_type")
    if not geom:
        return [_st(t["location_none"], ["object.geometry_type"], kind="missing")]
    precision = _v(facts, "object.geometry_precision") or "unknown"
    return [_st(t["location"].format(geom=GEOMETRY_LABELS[lang][geom], precision=PRECISION_LABELS[lang][precision]),
                ["object.geometry_type", "object.geometry_precision"], facts=facts)]


def r_access_impact(facts, lang):
    from agent.civic_assistant.scenario import render_scenario
    out = render_scenario(facts, lang, focus="impact") or [_st(T[lang]["access_none"], [], kind="missing")]
    # Объявление/план не доказывает, что перекрытие действует сейчас; сценарий — только гипотеза.
    return out + [_req(_st(T[lang]["no_active_closure_claim"], [], kind="notice"))]


def r_freshness(facts, lang):
    """Даты данных с явной основой: изменение карточки, публикация и получение источника, снимок сети."""
    from agent.civic_assistant.scenario import render_scenario_freshness
    t = T[lang]
    out = []
    if "object.title" in facts:
        upd, rev = _v(facts, "object.updated_at"), _v(facts, "object.revision")
        if upd and rev and fmt_at(upd, lang) != NO_DATA[lang]:
            out.append(_st(t["freshness_card"].format(d=fmt_at(upd, lang), r=rev),
                           ["object.updated_at", "object.revision"], facts=facts))
        else:
            out.append(_req(_st(t["freshness_card_missing"], ["object.updated_at"], kind="missing")))
        refs = [f for fid, f in facts.items() if fid.startswith("source.")]
        for f in refs:
            ref = f["value"]
            out.append(_st(t["freshness_source"].format(publisher=ref["publisher"] or NO_DATA[lang],
                                                        published=fmt_date(ref["published_on"], lang),
                                                        retrieved=fmt_at(ref["retrieved_at"], lang),
                                                        access=ACCESS_LABELS[lang][ref["access_status"]]),
                           [f["id"]], facts=facts))
        if refs:
            out.append(_req(_st(t["freshness_source_note"], [], kind="notice")))
        else:
            out.append(_req(_st(t["freshness_no_sources"], [], kind="missing")))
    out += render_scenario_freshness(facts, lang)
    if not out:
        out.append(_st(t["freshness_none"], [], kind="missing"))
    out.append(_req(_st(t["freshness_unknown_after"], [], kind="notice")))
    return out


def r_scenario_compare(facts, lang):
    from agent.civic_assistant.scenario import render_scenario
    out = render_scenario(facts, lang, focus="compare")
    return out or [_st(T[lang]["scenario_none"], [], kind="missing")]


# Поля, отсутствие которых важно жителю. actual_end ожидаемо пуст у незавершённых работ,
# поэтому его отсутствие называем только при статусе «завершено».
MISSING_FIELDS = ("schedule.current_planned_end", "schedule.original_planned_end", "schedule.planned_start",
                  "budget.amount_kzt", "budget.source_id", "responsible.organization",
                  "responsible.public_contact", "object.geometry_type", "object.description")


def r_missing_data(facts, lang):
    """Какие сведения в опубликованной карточке отсутствуют (known=False), без догадок о значениях."""
    t = T[lang]
    missing = [fid for fid in MISSING_FIELDS if fid in facts and not facts[fid]["known"]]
    if _v(facts, "object.status") == "completed" and "schedule.actual_end" in facts \
            and not facts["schedule.actual_end"]["known"]:
        missing.append("schedule.actual_end")
    has_sources = any(fid.startswith("source.") for fid in facts)
    labels = [t["missing_labels"][fid] for fid in missing]
    if not has_sources:
        labels.append(t["missing_labels"]["sources"])
    out = []
    if labels:
        out.append(_req(_st(t["missing_list"].format(fields=", ".join(labels)), missing, kind="missing")))
    else:
        out.append(_st(t["missing_none"], [], kind="notice"))
    shift = _v(facts, "schedule.shift_days")
    hist = _history(facts)
    has_reason = any(h["value"]["reason"] and any(c == "schedule" or c.startswith("schedule.")
                                                  for c in h["value"]["changed_fields"])
                     and "publication" not in h["value"]["changed_fields"] for h in hist)
    if shift and not has_reason:
        out.append(_req(_st(t["missing_reason"], ["schedule.shift_days"] + [h["id"] for h in hist][-3:],
                            kind="missing")))
    out.append(_st(t["missing_note"], [], kind="notice"))
    return out


def r_unsupported(facts, lang):
    return [_st(T[lang]["unsupported"], [], kind="notice")]


def r_clarify(facts, lang):
    t = T[lang]
    out = []
    if "object.title" in facts:
        out.append(_st(t["clarify"], [], kind="notice"))
    if any(fid.startswith("scenario.") for fid in facts):
        out.append(_st(t["clarify_scenario"], [], kind="notice"))
    return out or [_st(t["clarify"], [], kind="notice")]


RENDERERS = {
    "overview": r_overview,
    "status": r_status,
    "schedule": r_schedule,
    "delay_reason": r_delay_reason,
    "responsible": r_responsible,
    "budget": r_budget,
    "sources": r_sources,
    "history": r_history,
    "location": r_location,
    "access_impact": r_access_impact,
    "scenario_compare": r_scenario_compare,
    "freshness": r_freshness,
    "missing_data": r_missing_data,
    "unsupported": r_unsupported,
    "clarify": r_clarify,
}
INTENTS = tuple(RENDERERS)

# Какие факты может выбрать модель для каждого типа ответа (префиксы ID).
INTENT_FACT_PREFIXES = {
    "overview": ("object.", "schedule.current_planned_end", "schedule.actual_end"),
    "status": ("object.status", "schedule."),
    "schedule": ("schedule.",),
    "delay_reason": ("schedule.", "history."),
    "responsible": ("responsible.",),
    "budget": ("budget.", "source."),
    "sources": ("source.", "object.evidence_type"),
    "history": ("history.",),
    "location": ("object.geometry_type", "object.geometry_precision"),
    "access_impact": ("scenario.",),
    "scenario_compare": ("scenario.",),
    "freshness": ("object.updated_at", "object.revision", "source.", "scenario.graph.", "scenario.known_access_share",
                  "scenario.unknown_access_share", "scenario.engine_warnings"),
    "missing_data": ("schedule.", "budget.", "responsible.", "object.", "source.", "history."),
    "unsupported": (),
    "clarify": (),
}


def render(intent: str, facts: dict, lang: str, selected: list[str] | None = None) -> list[dict]:
    statements = RENDERERS[intent](facts, lang)
    if selected:
        chosen = set(selected)
        narrowed = [s for s in statements if s["kind"] == "notice" or s.get("required") or chosen & set(s["fact_ids"])]
        if any(s["kind"] != "notice" for s in narrowed):
            statements = narrowed
    # Пометка synthetic/hypothesis/derived добавляется кодом в каждый ответ, а не только в README.
    return evidence_notice(facts, lang) + statements
