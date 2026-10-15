"""Разбор вопроса акима без сети: язык, намерения, район, категория, период, служба, сигналы безопасности.

Правила работают по «сложенному» тексту (fold): нижний регистр, ё → е, казахские буквы → близкие русские
(қ → к, ұ/ү → у, ә → а, і → и …). Тогда «Нұрада» и «Нурада», «қар» и «кар» совпадают одним правилом, а
человек без казахской раскладки тоже понят. Короткие казахские слова («қар», «су», «ай», «шу») ищутся
только целым словом с окончаниями, иначе «қар» ловил бы «карта», «картина», «қараңғы».

Вопрос — данные, а не инструкция: слова «забудь правила», «придумай число», «удали жалобы» не меняют
поведение кода, а только поднимают флаги; ответ всё равно строится из данных модулей, с пометкой.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata

MAX_QUESTION = 500
DEFAULT_DAYS = 7
MAX_DAYS = 90

_FOLD = str.maketrans({"ә": "а", "ғ": "г", "қ": "к", "ң": "н", "ө": "о", "ұ": "у", "ү": "у", "һ": "х", "і": "и",
                       "ё": "е"})
_KK_LETTERS = re.compile(r"[әғқңөұүһі]", re.IGNORECASE)
# Служебные казахские слова (по сложенному тексту): отличают kk от ru, когда казахских букв нет.
_KK_WORDS = re.compile(r"(?<!\w)(?:канша|кай|кайда|кандай|неше|бойынша|туралы|бар ма|жок па|ма|ме|ба|бе|па|пе|"
                       r"бугин|апта\w*|аудан\w*|кызмет\w*|шагым\w*|отиниш\w*|кандай|кимдер|не болды|кешикт\w*|"
                       r"калып|жатыр|болды|болып|коп|азай\w*|осу|ости|кайсы|корсет\w*|айт\w*|кездесу\w*|тапсырма\w*|"
                       r"болжам\w*|келеси|бастама\w*|тургын\w*|жумыс\w*|кала\w*|жаналык\w*|ережеле\w*|деп)(?!\w)")
_RU_WORDS = re.compile(r"(?<!\w)(?:где|сколько|какие|какой|какая|каком|что|почему|когда|кто|как|за|на|в|по|и|или|"
                       r"больше|меньше|всего|жалоб\w*|обращен\w*|служб\w*|район\w*|неделю|недел\w*|сегодня|месяц\w*|"
                       r"отста\w*|просроч\w*|покажи|расскажи|есть)(?!\w)")


def fold(text: str) -> str:
    return text.casefold().translate(_FOLD)


def normalize_question(question) -> str:
    """Строка 1–500 знаков без управляющих символов; иначе ValueError (шлюз ответит 400)."""
    if not isinstance(question, str):
        raise ValueError("question: нужен текст вопроса.")
    if len(question) > MAX_QUESTION * 4:
        raise ValueError(f"question: вопрос длиннее {MAX_QUESTION} знаков.")
    text = unicodedata.normalize("NFC", question)
    text = "".join(" " if unicodedata.category(ch)[0] == "C" else ch for ch in text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ValueError("question: вопрос пустой.")
    if len(text) > MAX_QUESTION:
        raise ValueError(f"question: вопрос длиннее {MAX_QUESTION} знаков.")
    return text


def detect_language(text: str) -> str:
    """ru | kk | mixed (по казахским буквам и служебным словам обоих языков)."""
    folded = fold(text)
    kk = len(_KK_LETTERS.findall(text)) + 2 * len(_KK_WORDS.findall(folded))
    ru = len(_RU_WORDS.findall(folded))
    if kk and ru:
        # Одно-два русских слова в казахском вопросе («снег», «жалобы») — это и есть «вперемешку».
        return "mixed"
    return "kk" if kk else "ru"


def answer_language(question_lang: str, requested: str | None, text: str) -> str:
    """Язык ответа: выбранный в интерфейсе; без выбора — язык вопроса (вперемешку — по перевесу)."""
    if requested in ("ru", "kk"):
        return requested
    if question_lang == "mixed":
        folded = fold(text)
        kk = len(_KK_LETTERS.findall(text)) + 2 * len(_KK_WORDS.findall(folded))
        return "kk" if kk >= len(_RU_WORDS.findall(folded)) else "ru"
    return question_lang


# ---------------------------------------------------------------- словари (сложенный текст)

def _stems(*words: str) -> str:
    """Начало слова: «снег» ловит «снега», «снегопад»."""
    return r"(?<!\w)(?:" + "|".join(words) + r")"


# Короткие казахские слова — только явными формами (по сложенному тексту): общий список окончаний давал
# «кар» + «те» = русское «карте». Длинные казахские основы («аялдама», «жарык») безопасны как начало слова.
_KK_FORMS = {
    "кар": "кар кары карды кардын карга карда кардан карлы карын карымен кармен карсыз",
    "муз": "муз музы музды муздын музга музда муздан",
    "жол": "жол жолы жолды жолдын жолга жолда жолдан жолдар жолдары жолдарда жолдардын жолдарга жолмен",
    "шам": "шам шамы шамды шамдар шамдары шамдарда шамдардын шамдарга",
    "су": "су суы суды судын суга суда судан сумен суын сусыз",
    "шу": "шу шуы шуды шудын шуга шуда шудан",
    "иис": "иис иси иисти иистин иисы",
    "ауа": "ауа ауасы ауаны ауада ауанын ауага",
    "алан": "алан аланы аландар аландары аланда аланга аланнын аландардын",
    "ткш": "ткш",
}


def _kk_words(*words: str) -> str:
    """Казахское слово: короткое — одной из явных форм _KK_FORMS, длинное — по началу слова."""
    forms = []
    for w in words:
        forms.extend(_KK_FORMS[w].split() if w in _KK_FORMS else [w + r"\w*"])
    return r"(?<!\w)(?:" + "|".join(forms) + r")(?!\w)"


def _rx(*parts: str) -> re.Pattern:
    return re.compile("|".join(parts))


DISTRICT_RULES = (
    ("nura", _rx(r"(?<!\w)нур(?:а\w*|е|ы|ой|у|ин\w*)(?!\w)")),
    ("esil", _rx(_stems("есил"))),
    ("almaty", _rx(_stems("алматы", "алматин"))),
    ("baikonur", _rx(_stems("байконур", "байконыр"))),
    ("saryarka", _rx(_stems("сарыарк"))),
    ("saraishyk", _rx(_stems("сарайшык", "сарайшик"))),
)

CATEGORY_RULES = (
    ("snow_ice", _rx(_stems("снег", "снеж", "сугроб", "гололед", "налед", "скользк", "метел", "буран", "сосул"),
                     _kk_words("кар", "муз", "коктайгак", "тайгак", "боран", "кардан"))),
    ("roads", _rx(_stems("дорог", "выбоин", "асфальт", "ямы", "ямам", "ямами"), r"(?<!\w)ям[ау]?(?!\w)",
                  _kk_words("жол", "шункыр"))),
    ("sidewalks", _rx(_stems("тротуар"), r"жаяу жургинши")),
    ("transport", _rx(_stems("остановк", "автобус", "общественн\\w* транспорт", "транспорт"),
                      _kk_words("аялдама", "автобус"))),
    ("lighting", _rx(_stems("освещ", "фонар", "темно", "темнот"), r"(?<!\w)свет(?!офор)\w*",
                     _kk_words("жарык", "шам", "карангы"))),
    ("yards", _rx(_stems("двор", "площадк", "детск\\w* площад", "газон"), _kk_words("аула", "алан"))),
    ("waste", _rx(_stems("мусор", "свалк", "контейнер", "отход"), _kk_words("кокыс"))),
    ("utilities", _rx(_stems("жкх", "отоплен", "батаре", "горяч\\w* вод", "холодн\\w* вод", "канализац",
                             "прорыв", "водопровод", "теплоснаб"), _kk_words("жылу", "су", "ткш", "кариз"))),
    ("smell_air", _rx(_stems("запах", "вон", "дым", "воздух", "смог", "выброс"), _kk_words("иис", "ауа", "тутин"))),
    ("noise_safety", _rx(_stems("шум", "громк", "безопасн", "драк", "хулиган"), _kk_words("шу", "кауипсиздик"))),
    ("parking", _rx(_stems("парков", "стоянк"), _kk_words("турак"), r"колик кою")),
)

SERVICE_RULES = (
    ("water", _rx(_stems("водоканал"), r"сумен жабдыкта")),
    ("heating", _rx(_stems("теплосет", "тепловик"), r"жылу жели")),
    ("road", _rx(_stems("дорожн\\w* служб", "дорожник"), r"жол кызмет")),
    ("street_cleaning", _rx(_stems("уборк\\w* улиц", "служб\\w* уборк", "уборщик", "коммунальщик"),
                            r"тазалау кызмет", r"кошелерди тазалау")),
    ("lighting", _rx(_stems("служб\\w* освещ"), r"жарыктандыру кызмет")),
    ("landscaping", _rx(_stems("благоустр"), _kk_words("абаттандыру"))),
    ("greenery", _rx(_stems("озелен"), _kk_words("когалдандыру"))),
    ("waste", _rx(_stems("вывоз\\w* мусор", "оператор\\w* вывоз", "мусоровоз"), r"кокыс шыгару")),
    ("power", _rx(_stems("электросет", "энергетик"), r"электр жели")),
    ("gas", _rx(_stems("газов\\w* служб", "газовик"), r"газ кызмет")),
    ("traffic", _rx(_stems("светофор", "разметк"), _kk_words("багдаршам"))),
    ("transport", _rx(_stems("служб\\w* транспорт", "транспортн\\w* служб"), r"когамдык колик")),
    ("utilities", _rx(_stems("служб\\w* жкх"), r"ткш кызмет")),
    ("police", _rx(_stems("полиц"))),
    ("emergency", _rx(_stems("служб\\w* спасен", "спасател", "дчс", "мчс"), r"куткару кызмет")),
    ("animals", _rx(_stems("отлов"), r"жануарларды аулау")),
    ("parking", _rx(_stems("служб\\w* парков"), r"турак кызмет")),
)

# Намерения: (id, правило). Порядок ответа — по месту первого совпадения в вопросе.
INTENT_RULES = (
    ("crisis", _rx(_stems("буран", "метел", "кризис", "чрезвычай", "авари", "прорыв", "отключени",
                          "снегопад", "непогод", "стихи"), r"(?<!\w)чс(?!\w)",
                   _kk_words("боран", "дагдарыс", "апат"), r"(?<!\w)тотенше")),
    ("work_conflicts", _rx(_stems("конфликт", "копа", "раскоп", "перекоп", "дважды", "календар\\w* работ",
                                  "пересека", "асфальт\\w* после", "сначала сет"),
                           r"(?<!\w)работ\w* (?:ведомств|служб)", r"екi рет|еки рет", _kk_words("казу", "казып"),
                           r"жумыстар кест", r"жумыстар кунтизб", r"кайшылы[кг]")),
    ("initiatives", _rx(_stems("инициатив", "субботник", "сделаем вместе", "волонтер", "соседи сами", "жители сами",
                               "толок"), _kk_words("бастама", "сенбилик"), r"бирге жасайык")),
    ("meeting_orders", _rx(_stems("поручени", "встреч", "прием граждан", "приём граждан", "что поручил"),
                           _kk_words("тапсырма", "кездесу", "кездесуде"))),
    ("lagging_services", _rx(_stems("отста", "отстающ", "тормоз", "медленн", "затягива", "хуже всех работа"),
                             r"(?<!\w)как\w* служб", r"(?<!\w)служб\w* (?:работа|справля|не успева)",
                             r"(?<!\w)кто (?:не успева|медленн|хуже)", r"(?<!\w)кто из служб", r"(?<!\w)как\w* из служб",
                             r"(?:служб|ведомств)\w*[^.?!]{0,20}(?:хуже|справля|не успева|не закрыва)", r"табло",
                             r"штаб ведомств", r"по служб",
                             r"(?<!\w)ведомств\w* отста", r"ведомстволар штаб",
                             _kk_words("артта", "калып жаткан", "кешигип"), r"кай кызмет", r"кандай кызмет",
                             r"кызметтер кешик")),
    ("overdue", _rx(_stems("просроч", "сорва\\w* срок", "срок\\w* сорва", "не уложил", "опозда", "истек\\w* срок",
                           "срок\\w* истек", "вышли из срок"),
                    r"мерзими от\w*", r"мерзими бузыл", r"мерзиминен", _kk_words("кешиктирилген"))),
    ("category_growth", _rx(_stems("рост", "раст", "вырос", "увелич", "прибав", "всплеск", "скач", "тренд",
                                   "динамик", "чаще стали", "больше чем", "больше, чем", "по сравнению"),
                            _kk_words("осу", "ости", "осип", "кобей", "кобейди", "артты", "арту"))),
    ("district_compare", _rx(r"(?<!по )(?<!\w)сравн(?!ени[юе] с)", _stems("по район", "какой район", "каком район", "какие район",
                                    "в каком из район", "в как\\w* район", "между район", "районы", "районах"),
                             _kk_words("салыстыр"), r"кай аудан", r"кандай аудан", r"(?<!\w)как\w* аудан", r"аудандар")),
    ("forecast", _rx(_stems("прогноз", "что будет", "ожида", "предсказ", "следующ\\w* недел"),
                     _kk_words("болжам"), r"не болады")),
    ("day_summary", _rx(_stems("что сегодня", "картин\\w* дня", "сводк", "главное", "ситуаци", "обстановк",
                               "что нового", "как дела", "итог\\w* дня", "что происходит", "общая картина"),
                        r"кун корин", r"бугин не", r"жалпы жагдай", r"кыскаша", r"жаналык")),
    ("hot_spots", _rx(_stems("горяч", "больше всего", "чаще всего", "топ", "самы\\w* проблемн",
                             "проблемн\\w* мест", "какие мест", "какие улиц", "какие двор", "куда жалу",
                             "хуже всего", "больше всех"),
                      r"жерде коп", r"кай кошеде", r"кай аулада", r"ен коп", _kk_words("ыстык"))),
)
# «Где» / «қайда» — слабый признак горячих мест: только если других намерений в вопросе нет.
WEAK_HOT = _rx(r"(?<!\w)где(?!\w)", r"(?<!\w)кайда(?!\w)", r"(?<!\w)кай жер")

# Сигналы безопасности (вопрос — данные). Не меняют расчёт, дают пометку и вежливый отказ от части просьбы.
SAFETY_RULES = (
    ("injection", _rx(_stems("забуд", "игнорир", "ignore", "disregard", "previous instruction", "системн\\w* промпт",
                             "system prompt", "ты теперь", "act as", "притворись", "jailbreak", "developer mode",
                             "отключи правил", "без правил", "новые правила", "инструкци", "prompt"),
                      r"ережелерди умыт", _kk_words("умыт", "елеме"))),
    ("fabricate", _rx(_stems("придума", "выдума", "сочини", "нарисуй цифр", "поставь цифр", "сделай вид",
                             "округли в", "приукрас", "занизь", "завысь", "подгони", "скажи что все хорошо",
                             "скажи, что все хорошо", "просто напиши", "любое число", "любую цифр", "примерно скажи"),
                      r"(?:скажи|напиши|ответь|сообщи|доложи),? что(?: в \w+)? (?:все|нет|никто|ни одн|ничего)",
                      r"ойлап тап", r"ойдан шыгар", r"кез келген сан", r"деп (?:жаз|айт)")),
    ("write", _rx(_stems("удали", "удалить", "измени", "изменить", "поменяй", "закрой", "отметь", "опубликуй",
                         "отправь", "назначь", "переназнач", "сотри", "отклони", "одобри", "поставь статус"),
                  _kk_words("ошир", "озгерт", "жариял", "жиберу"))),
    ("personal", _rx(_stems("телефон", "иин", "иин", "фамили", "кто пожаловал", "кто написал", "кто жалу",
                            "имя жител", "имена", "адрес\\w* жител", "паспорт", "e-mail", "email", "почт"),
                     r"аты-жони", r"аты жони", r"кім жазды", r"ким жазды", r"ким шагымдан")),
)

_DAYS_EXPLICIT = re.compile(r"(?<!\d)(\d{1,3})\s*(?:-?\s*)?(?:дн\w*|ден\w*|суток|сутки|кун\w*)(?!\w)")
_WEEKS_EXPLICIT = re.compile(r"(?<!\d)(\d{1,2})\s*(?:недел\w*|апта\w*)(?!\w)")
_PERIODS = (
    (1, _rx(_stems("сегодня", "за сутки", "за день", "сегодняшн", "вчера", "последние сутки"),
            _kk_words("бугин", "кеше"), r"бир тауликте")),
    (30, _rx(_stems("месяц", "за 30"), r"(?<!\w)ай(?:да|га|дагы|лык|ы|дын|ды|дан)?(?!\w)", r"сонгы ай")),
    (7, _rx(_stems("недел", "за 7", "семь дней"), _kk_words("апта"))),
)


@dataclass
class Parsed:
    question: str
    question_lang: str
    intents: list[str] = field(default_factory=list)
    district: str | None = None
    districts: list[str] = field(default_factory=list)
    category: str | None = None
    service: str | None = None
    days: int = DEFAULT_DAYS
    days_given: bool = False
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"intents": list(self.intents), "district": self.district, "districts": list(self.districts),
                "category": self.category, "service": self.service, "days": self.days,
                "days_given": self.days_given, "flags": list(self.flags), "question_lang": self.question_lang}


def _first(rules, folded: str):
    """Все совпавшие id по месту первого совпадения: [(pos, id)]."""
    found = []
    for key, rx in rules:
        m = rx.search(folded)
        if m:
            found.append((m.start(), key))
    return sorted(found)


_WORD_NUMBERS = {"один": 1, "одну": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6,
                 "бир": 1, "еки": 2, "уш": 3, "торт": 4, "бес": 5, "алты": 6}
_WORDS_PERIOD = re.compile(r"(?<!\w)(" + "|".join(_WORD_NUMBERS) + r")\s+(недел\w*|апта\w*|месяц\w*|ай\w*|дн\w*|ден\w*|кун\w*)(?!\w)")
_UNIT_DAYS = (("недел", 7), ("апта", 7), ("месяц", 30), ("ай", 30), ("дн", 1), ("ден", 1), ("кун", 1))


def _period(folded: str) -> tuple[int, bool]:
    m = _WORDS_PERIOD.search(folded)
    if m:
        unit = next(days for stem, days in _UNIT_DAYS if m.group(2).startswith(stem))
        return max(1, min(MAX_DAYS, _WORD_NUMBERS[m.group(1)] * unit)), True
    if re.search(r"(?<!\w)полмесяц", folded):
        return 15, True
    if re.search(r"(?<!\w)квартал", folded):
        return MAX_DAYS, True
    m = _DAYS_EXPLICIT.search(folded)
    if m:
        return max(1, min(MAX_DAYS, int(m.group(1)))), True
    m = _WEEKS_EXPLICIT.search(folded)
    if m:
        return max(1, min(MAX_DAYS, int(m.group(1)) * 7)), True
    for days, rx in _PERIODS:
        if rx.search(folded):
            return days, True
    return DEFAULT_DAYS, False


def parse(question: str) -> Parsed:
    """Вопрос (уже normalize_question) → намерения и параметры. Ничего не вызывает и не знает о данных."""
    folded = " " + fold(question) + " "
    parsed = Parsed(question=question, question_lang=detect_language(question))
    parsed.districts = [key for _pos, key in _first(DISTRICT_RULES, folded)]
    parsed.district = parsed.districts[0] if parsed.districts else None
    categories = [key for _pos, key in _first(CATEGORY_RULES, folded)]
    # «Двор» чаще место, чем тема: «во дворе темно» — освещение, «снег во дворе» — снег.
    if len(categories) > 1 and categories[0] == "yards":
        categories = categories[1:] + ["yards"]
    parsed.category = categories[0] if categories else None
    services = [key for _pos, key in _first(SERVICE_RULES, folded)]
    parsed.service = services[0] if services else None
    parsed.days, parsed.days_given = _period(folded)
    parsed.flags = [key for _pos, key in _first(SAFETY_RULES, folded)]

    hits = _first(INTENT_RULES, folded)
    intents = [key for _pos, key in hits]
    if not intents and WEAK_HOT.search(folded) and (parsed.category or parsed.district):
        intents = ["hot_spots"]
    # «Буран» — и кризис, и категория «снег»: если кризисных слов нет, кроме снега/бурана, всё равно кризис.
    if "crisis" in intents and parsed.category is None and re.search(r"буран|боран|метел|снегопад", folded):
        parsed.category = "snow_ice"
    # Два района в вопросе — это сравнение, даже без слова «сравни».
    if len(parsed.districts) >= 2 and "district_compare" not in intents:
        intents.append("district_compare")
    # «Где» в вопросе о службах («где отстают службы») — не про горячие места.
    if "hot_spots" in intents and "lagging_services" in intents:
        hot_only_where = not re.search(r"больше всего|горяч|топ|проблемн|ен коп|ыстык|жалоб|шагым", folded)
        if hot_only_where:
            intents.remove("hot_spots")
    # «Прогноз проблемных мест» — прогноз, а не сегодняшние горячие места; «ситуация при буране» — кризис, а не сводка.
    if intents == ["work_conflicts"]:
        parsed.category = None
    if "forecast" in intents and "hot_spots" in intents:
        intents.remove("hot_spots")
    if "crisis" in intents and "day_summary" in intents:
        intents.remove("day_summary")
    # «В каком районе больше всего …» — сравнение районов, а не места внутри района.
    if "district_compare" in intents and "hot_spots" in intents and parsed.district is None:
        intents.remove("hot_spots")
    # Рост без категории и района, но со словом «где» — это рост, «где» лишь вопросительное слово.
    if not intents and (parsed.category or parsed.district or parsed.service):
        intents = ["lagging_services"] if parsed.service and not parsed.category else ["hot_spots"]
    parsed.intents = list(dict.fromkeys(intents))[:3]
    return parsed
