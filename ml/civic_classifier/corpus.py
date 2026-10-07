"""Детерминированный СИНТЕТИЧЕСКИЙ корпус сообщений жителей RU/KK/смешанный (R08, раунд 12).

Это не реальные обращения. Шаблоны и метки написаны агентом (Claude, R08) по LABELING_GUIDE.md;
это не экспертная человеческая разметка. Названия улиц — публичные топонимы Астаны, использованы
только как значения слотов; сообщения о них выдуманы.

Сборка: python -m ml.civic_classifier build-corpus  ->  data/corpus_synthetic_v1.jsonl + data/split_v1.json
Защита от утечки:
  1) обезличивание (text.anonymize) до сохранения; в корпус попадает только обезличенный текст;
  2) точные дубликаты после нормализации удаляются ДО split (при разных метках — удаляются все копии);
  3) split по шаблонам (group split): валидация и тест построены из шаблонов, которых нет в обучении;
  4) элементы val/test, близкие к обучающим (Jaccard символьных 3-грамм >= NEAR_DUP), исключаются.
"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

from ml.civic_classifier.labels import LABELS
from ml.civic_classifier.text import anonymize, normalize

CORPUS_VERSION = "synthetic_v1"
SEED = 20261007
EXPANSIONS = 16
SHORT_EXPANSIONS = 4
NEAR_DUP = 0.8
DATA_DIR = Path(__file__).resolve().parent / "data"
CORPUS_PATH = DATA_DIR / "corpus_synthetic_v1.jsonl"
SPLIT_PATH = DATA_DIR / "split_v1.json"
SPLIT_PATTERN = ("train", "test", "val", "train", "train")

STREETS = ("Кабанбай батыра", "Туран", "Сыганак", "Достык", "Мангилик Ел", "Абая", "Республики", "Кенесары",
           "Бейбитшилик", "Сарыарка", "Богенбай батыра", "Жубанова", "Момышулы", "Сейфуллина", "Иманова",
           "Тауелсиздик", "Кошкарбаева", "Улы Дала", "Акмешит", "Сатпаева")
PLACE_RU = ("возле дома {n}", "у школы №{n}", "рядом с ТРЦ", "во дворе дома {n}", "у поликлиники",
            "возле детского сада", "на перекрёстке", "около рынка", "в микрорайоне", "возле ЖК", "у дома {n}")
PLACE_KK = ("{n}-үйдің жанында", "№{n} мектептің қасында", "аулада", "емхананың жанында",
            "балабақшаның жанында", "қиылыста", "базардың жанында", "тұрғын үй кешенінің жанында")
TIME_RU = ("уже неделю", "второй месяц", "с весны", "после ремонта", "каждый вечер", "с прошлого года", "", "")
TIME_KK = ("бір аптадан бері", "екі айдан бері", "көктемнен бері", "жөндеуден кейін", "әр кеш сайын", "", "")
PREFIX_RU = ("Здравствуйте!", "Добрый день.", "Прошу обратить внимание:", "Жители жалуются:", "Уважаемый акимат,",
             "", "", "")
PREFIX_KK = ("Сәлеметсіз бе!", "Қайырлы күн.", "Назар аударуыңызды сұраймын:", "Тұрғындар шағымданады:", "", "", "")
SUFFIX_RU = ("Примите меры.", "Просим исправить.", "Опасно для детей.", "Когда исправят?", "Спасибо.", "", "", "")
SUFFIX_KK = ("Шара қолдануды сұраймыз.", "Түзетуді сұраймыз.", "Балаларға қауіпті.", "Қашан түзетеді?", "Рақмет.",
             "", "", "")
CONTACT_RU = ("Мой телефон +7 70{d} {a} {b} {c}.", "Пишите на resident{n}@mail.kz.", "Тел. 8 777 {a} {b} {c}.")

# (template_id, label, language, family, text, ambiguous). Слоты: {street} {street2} {street_kk} {place}
# {place_kk} {time} {time_kk}. Короткие шаблоны (family *_short) без префиксов/суффиксов.
T = [
    # --- roads
    ("rd-pot-ru1", "roads", "ru", "pothole", "На улице {street} огромная яма на дороге {place}.", False),
    ("rd-pot-ru2", "roads", "ru", "pothole", "{Place} на проезжей части выбоины, машины объезжают по встречке.", False),
    ("rd-pot-ru3", "roads", "ru", "pothole", "Дорогу на {street} всю разбило, ямы {time}.", False),
    ("rd-pot-kk1", "roads", "kk", "pothole", "{street_kk} жолда үлкен шұңқыр бар.", False),
    ("rd-pot-kk2", "roads", "kk", "pothole", "{Place_kk} жол бұзылып, шұңқырлар пайда болды.", False),
    ("rd-pot-mx1", "roads", "mixed", "pothole", "{street_kk} жолда яма, машины объезжают.", False),
    ("rd-asp-ru1", "roads", "ru", "asphalt", "После раскопок на {street} не восстановили асфальт {time}.", False),
    ("rd-asp-ru2", "roads", "ru", "asphalt", "Разрыли дорогу {place} и так и оставили.", False),
    ("rd-asp-kk1", "roads", "kk", "asphalt", "Жөндеуден кейін {street_kk} асфальт төселмеді.", False),
    ("rd-mrk-ru1", "roads", "ru", "marking", "Стерлась разметка пешеходного перехода {place}.", True),
    ("rd-mrk-ru2", "roads", "ru", "marking", "На {street} не видно разметки, водители путаются в полосах.", False),
    ("rd-mrk-kk1", "roads", "kk", "marking", "{Place_kk} жол таңбасы өшіп қалған.", False),
    ("rd-tl-ru1", "roads", "ru", "traffic_light", "Не работает светофор на перекрёстке {street} и {street2}.", False),
    ("rd-tl-ru2", "roads", "ru", "traffic_light", "Светофор {place} мигает жёлтым {time}, опасно.", False),
    ("rd-tl-kk1", "roads", "kk", "traffic_light", "{street_kk} қиылысындағы бағдаршам жұмыс істемейді.", False),
    ("rd-tl-mx1", "roads", "mixed", "traffic_light", "Бағдаршам не работает {place}.", False),
    ("rd-snw-ru1", "roads", "ru", "snow_water", "Проезжую часть на {street} не чистят от снега.", False),
    ("rd-snw-ru2", "roads", "ru", "snow_water", "После дождя на дороге {place} стоит огромная лужа, ливнёвка забита.", False),
    ("rd-snw-kk1", "roads", "kk", "snow_water", "{street_kk} жолдағы қар тазаланбаған.", False),
    ("rd-snw-kk2", "roads", "kk", "snow_water", "Жаңбырдан кейін жолда су тұрып қалды {place_kk}.", False),
    ("rd-sgn-ru1", "roads", "ru", "signs", "Перекрыли дорогу {place} без знаков объезда.", False),
    ("rd-sgn-ru2", "roads", "ru", "signs", "Упал дорожный знак на {street}.", False),
    ("rd-sgn-kk1", "roads", "kk", "signs", "Жол белгісі құлап қалған {place_kk}.", False),
    ("rd-bmp-ru1", "roads", "ru", "speed_bump", "Просим установить лежачий полицейский {place}, машины гоняют.", False),
    ("rd-bmp-kk1", "roads", "kk", "speed_bump", "{Place_kk} жылдамдықты азайтатын кедергі қою керек.", False),
    ("rd-sh1", "roads", "ru", "roads_short", "яма", False),
    ("rd-sh2", "roads", "ru", "roads_short", "ямы на дороге", False),
    ("rd-sh3", "roads", "kk", "roads_short", "жолда шұңқыр", False),
    ("rd-sh4", "roads", "ru", "roads_short", "светофор не работает", False),
    # --- sidewalks
    ("sw-til-ru1", "sidewalks", "ru", "tiles", "На тротуаре {place} разбита плитка, люди спотыкаются.", False),
    ("sw-til-ru2", "sidewalks", "ru", "tiles", "Тротуарная плитка на {street} провалилась {time}.", False),
    ("sw-til-kk1", "sidewalks", "kk", "tiles", "Тротуардағы плитка сынған {place_kk}.", False),
    ("sw-til-mx1", "sidewalks", "mixed", "tiles", "Тротуарда плитка разбита {time}.", False),
    ("sw-no-ru1", "sidewalks", "ru", "no_sidewalk", "Вдоль {street} нет тротуара, ходим по проезжей части.", True),
    ("sw-no-ru2", "sidewalks", "ru", "no_sidewalk", "Нет пешеходной дорожки до остановки {place}.", True),
    ("sw-no-kk1", "sidewalks", "kk", "no_sidewalk", "{street_kk} бойында тротуар жоқ, жолмен жүруге тура келеді.", True),
    ("sw-no-kk2", "sidewalks", "kk", "no_sidewalk", "Жаяу жүргіншілер жолы жоқ {place_kk}.", False),
    ("sw-rmp-ru1", "sidewalks", "ru", "ramp", "Нет пандуса у перехода {place}, с коляской не проехать.", True),
    ("sw-rmp-ru2", "sidewalks", "ru", "ramp", "Слишком высокий бордюр на {street}, инвалидная коляска не заезжает.", False),
    ("sw-rmp-kk1", "sidewalks", "kk", "ramp", "Пандус жоқ, арбамен өту мүмкін емес {place_kk}.", False),
    ("sw-fnc-ru1", "sidewalks", "ru", "fence", "Забор стройки перекрыл тротуар на {street}, приходится выходить на дорогу.", True),
    ("sw-fnc-kk1", "sidewalks", "kk", "fence", "Құрылыс қоршауы тротуарды жауып тастады {place_kk}.", False),
    ("sw-ice-ru1", "sidewalks", "ru", "ice_water", "На тротуаре {place} гололёд, никто не посыпает.", False),
    ("sw-ice-ru2", "sidewalks", "ru", "ice_water", "Пешеходная дорожка {place} затоплена водой.", False),
    ("sw-ice-kk1", "sidewalks", "kk", "ice_water", "Тротуарда көктайғақ, құм себілмеген.", False),
    ("sw-ice-mx1", "sidewalks", "mixed", "ice_water", "Тротуарда гололёд {time}, адамдар құлап жатыр.", False),
    ("sw-und-ru1", "sidewalks", "ru", "underpass", "В подземном переходе на {street} вода и грязь.", False),
    ("sw-und-ru2", "sidewalks", "ru", "underpass", "Не работает лифт в надземном переходе {place}.", False),
    ("sw-und-kk1", "sidewalks", "kk", "underpass", "Жер асты өткелінде су тұр {place_kk}.", False),
    ("sw-sh1", "sidewalks", "ru", "sidewalks_short", "плитка разбита", False),
    ("sw-sh2", "sidewalks", "ru", "sidewalks_short", "нет тротуара", False),
    ("sw-sh3", "sidewalks", "kk", "sidewalks_short", "тротуар жоқ", False),
    # --- transport_stops
    ("ts-pav-ru1", "transport_stops", "ru", "pavilion", "На остановке {place} разбито стекло павильона.", False),
    ("ts-pav-ru2", "transport_stops", "ru", "pavilion", "Павильон остановки на {street} весь сломан.", False),
    ("ts-pav-kk1", "transport_stops", "kk", "pavilion", "Аялдамадағы павильонның әйнегі сынған {place_kk}.", False),
    ("ts-pav-mx1", "transport_stops", "mixed", "pavilion", "Аялдамада павильон сломан {time}.", False),
    ("ts-shl-ru1", "transport_stops", "ru", "shelter", "На остановке {place} нет навеса, люди мокнут под дождём.", False),
    ("ts-shl-ru2", "transport_stops", "ru", "shelter", "На остановке на {street} нет ни одной скамейки.", True),
    ("ts-shl-kk1", "transport_stops", "kk", "shelter", "Аялдамада орындық жоқ, қарттарға отыратын жер жоқ.", True),
    ("ts-shl-kk2", "transport_stops", "kk", "shelter", "{street_kk} аялдамасында шатыр жоқ.", False),
    ("ts-brd-ru1", "transport_stops", "ru", "board", "Электронное табло на остановке {place} не работает {time}.", False),
    ("ts-brd-kk1", "transport_stops", "kk", "board", "Аялдамадағы электронды табло жұмыс істемейді.", False),
    ("ts-brd-mx1", "transport_stops", "mixed", "board", "Табло на аялдама не работает {time}.", False),
    ("ts-mov-ru1", "transport_stops", "ru", "moved", "Остановку на {street} перенесли из-за ремонта, указателей нет.", False),
    ("ts-mov-kk1", "transport_stops", "kk", "moved", "Жөндеуге байланысты аялдаманы ауыстырды, жаңасы қайда екені белгісіз.", False),
    ("ts-bus-ru1", "transport_stops", "ru", "bus_skips", "Автобусы проезжают мимо остановки {place}, не останавливаются.", False),
    ("ts-bus-kk1", "transport_stops", "kk", "bus_skips", "Автобус {place_kk} аялдамаға тоқтамай өтіп кетеді.", False),
    ("ts-snw-ru1", "transport_stops", "ru", "stop_snow", "Посадочную площадку на остановке {place} не чистят от снега.", True),
    ("ts-snw-kk1", "transport_stops", "kk", "stop_snow", "Аялдамада қар тазаланбаған {place_kk}.", True),
    ("ts-sh1", "transport_stops", "ru", "stops_short", "нет остановки", False),
    ("ts-sh2", "transport_stops", "ru", "stops_short", "табло не работает", False),
    ("ts-sh3", "transport_stops", "kk", "stops_short", "аялдама сынған", False),
    # --- lighting
    ("lt-off-ru1", "lighting", "ru", "lamps_off", "Не горят фонари на улице {street} {time}.", False),
    ("lt-off-ru2", "lighting", "ru", "lamps_off", "Вся улица {street} без освещения.", False),
    ("lt-off-kk1", "lighting", "kk", "lamps_off", "{street_kk} көше шамдары жанбайды.", False),
    ("lt-off-mx1", "lighting", "mixed", "lamps_off", "Көше шамдары не горят {time}.", False),
    ("lt-drk-ru1", "lighting", "ru", "dark", "Во дворе {place} очень темно, нет ни одного фонаря.", False),
    ("lt-drk-ru2", "lighting", "ru", "dark", "Дорожка в парке не освещена, вечером страшно идти.", True),
    ("lt-drk-kk1", "lighting", "kk", "dark", "Аулада қараңғы, шам жоқ {place_kk}.", False),
    ("lt-day-ru1", "lighting", "ru", "day_burning", "Фонари на {street} горят днём, зря тратится электричество.", False),
    ("lt-day-kk1", "lighting", "kk", "day_burning", "Шамдар күндіз жанып тұр {street_kk}.", False),
    ("lt-flk-ru1", "lighting", "ru", "flicker", "Фонарь {place} постоянно мигает.", False),
    ("lt-flk-kk1", "lighting", "kk", "flicker", "Шам жыпылықтап тұр {place_kk}.", False),
    ("lt-pol-ru1", "lighting", "ru", "pole", "Покосилась опора освещения {place}, может упасть.", False),
    ("lt-pol-ru2", "lighting", "ru", "pole", "У фонарного столба на {street} торчат провода.", False),
    ("lt-pol-kk1", "lighting", "kk", "pole", "Шам бағанасы қисайып тұр {place_kk}.", False),
    ("lt-stp-ru1", "lighting", "ru", "stop_lamp", "На остановке {place} не горит фонарь, ждём автобус в темноте.", True),
    ("lt-stp-kk1", "lighting", "kk", "stop_lamp", "Аялдамадағы шам жанбайды, қараңғыда күтеміз.", True),
    ("lt-sh1", "lighting", "ru", "lighting_short", "фонари не горят", False),
    ("lt-sh2", "lighting", "ru", "lighting_short", "темно во дворе", False),
    ("lt-sh3", "lighting", "kk", "lighting_short", "шам жанбайды", False),
    # --- landscaping
    ("ls-tre-ru1", "landscaping", "ru", "trees", "Во дворе {place} вырубили деревья без объяснений.", False),
    ("ls-tre-ru2", "landscaping", "ru", "trees", "Просим посадить деревья вдоль {street}.", False),
    ("ls-tre-kk1", "landscaping", "kk", "trees", "Аулада ағаштарды кесіп тастады {place_kk}.", False),
    ("ls-tre-kk2", "landscaping", "kk", "trees", "{street_kk} бойына ағаш отырғызу керек.", False),
    ("ls-pla-ru1", "landscaping", "ru", "playground", "Детская площадка {place} сломана, качели опасные.", False),
    ("ls-pla-kk1", "landscaping", "kk", "playground", "Балалар алаңы сынған {place_kk}.", False),
    ("ls-pla-mx1", "landscaping", "mixed", "playground", "Балалар алаңында качели сломаны {time}.", False),
    ("ls-ben-ru1", "landscaping", "ru", "benches", "В сквере на {street} не хватает скамеек и урн.", True),
    ("ls-ben-kk1", "landscaping", "kk", "benches", "Саябақта орындықтар мен қоқыс жәшіктері жоқ.", True),
    ("ls-lwn-ru1", "landscaping", "ru", "lawn", "После ремонта теплотрассы {place} не восстановили газон.", False),
    ("ls-lwn-kk1", "landscaping", "kk", "lawn", "Жөндеуден кейін көгал қалпына келтірілмеді {place_kk}.", False),
    ("ls-yrd-ru1", "landscaping", "ru", "yard", "Просим провести благоустройство двора {place}.", False),
    ("ls-yrd-kk1", "landscaping", "kk", "yard", "Аулаға абаттандыру жұмыстарын жүргізуді сұраймыз.", False),
    ("ls-flw-ru1", "landscaping", "ru", "flowers", "Фонтан в парке не работает {time}.", False),
    ("ls-flw-ru2", "landscaping", "ru", "flowers", "Клумбы на {street} заброшены.", False),
    ("ls-flw-kk1", "landscaping", "kk", "flowers", "Гүлзарлар күтімсіз қалған {place_kk}.", False),
    ("ls-sh1", "landscaping", "ru", "landscaping_short", "вырубили деревья", False),
    ("ls-sh2", "landscaping", "ru", "landscaping_short", "площадка сломана", False),
    ("ls-sh3", "landscaping", "kk", "landscaping_short", "ағаш кесілді", False),
    # --- other
    ("ot-grb-ru1", "other", "ru", "garbage", "Мусор во дворе {place} не вывозят {time}.", False),
    ("ot-grb-kk1", "other", "kk", "garbage", "Аулада қоқыс шығарылмайды {time_kk}.", False),
    ("ot-nse-ru1", "other", "ru", "noise", "Стройка {place} шумит по ночам.", False),
    ("ot-nse-kk1", "other", "kk", "noise", "Түнде құрылыс шуы ұйықтатпайды {place_kk}.", False),
    ("ot-dog-ru1", "other", "ru", "dogs", "Во дворе {place} стая бездомных собак.", False),
    ("ot-dog-kk1", "other", "kk", "dogs", "Аулада иесіз иттер көп.", False),
    ("ot-utl-ru1", "other", "ru", "utilities", "Нет горячей воды {time}.", False),
    ("ot-utl-ru2", "other", "ru", "utilities", "В доме холодно, отопление не включили.", False),
    ("ot-utl-kk1", "other", "kk", "utilities", "Ыстық су жоқ {time_kk}.", False),
    ("ot-qst-ru1", "other", "ru", "question", "Когда закончат ремонт на {street}?", True),
    ("ot-qst-ru2", "other", "ru", "question", "Подскажите, до какого числа продлятся работы {place}?", True),
    ("ot-qst-kk1", "other", "kk", "question", "Жөндеу қашан бітеді?", True),
    ("ot-thx-ru1", "other", "ru", "thanks", "Спасибо за новый сквер, очень красиво!", True),
    ("ot-thx-ru2", "other", "ru", "thanks", "Благодарим за быстрый ремонт дороги на {street}.", True),
    ("ot-thx-kk1", "other", "kk", "thanks", "Жаңа саябақ үшін рақмет!", True),
    ("ot-irr-ru1", "other", "ru", "irrelevant", "Где можно оплатить штраф за парковку?", False),
    ("ot-irr-ru2", "other", "ru", "irrelevant", "Как записаться к врачу в поликлинику?", False),
    ("ot-irr-kk1", "other", "kk", "irrelevant", "Емханаға қалай жазылуға болады?", False),
    ("ot-sh1", "other", "ru", "other_short", "мусор", False),
    ("ot-sh2", "other", "ru", "other_short", "шум ночью", False),
    ("ot-sh3", "other", "kk", "other_short", "рақмет", False),
]


def _kk_street(street: str, rng: random.Random) -> str:
    return street + rng.choice((" көшесі", " көшесінде", " даңғылы", " даңғылында"))


def _typo(text: str, rng: random.Random) -> str:
    words = text.split(" ")
    idx = [i for i, w in enumerate(words) if len(w) >= 5]
    if not idx:
        return text
    i = rng.choice(idx)
    w = words[i]
    j = rng.randrange(1, len(w) - 1)
    op = rng.choice(("drop", "swap", "dup"))
    if op == "drop":
        w = w[:j] + w[j + 1:]
    elif op == "swap":
        w = w[:j - 1] + w[j] + w[j - 1] + w[j + 1:]
    else:
        w = w[:j] + w[j] + w[j:]
    words[i] = w
    return " ".join(words)


def _fill(template: str, rng: random.Random) -> str:
    n = rng.randint(2, 120)
    s1, s2 = rng.sample(STREETS, 2)
    place = rng.choice(PLACE_RU).format(n=n)
    place_kk = rng.choice(PLACE_KK).format(n=n)
    values = {"street": s1, "street2": s2, "street_kk": _kk_street(s1, rng), "place": place,
              "Place": place[:1].upper() + place[1:], "place_kk": place_kk,
              "Place_kk": place_kk[:1].upper() + place_kk[1:],
              "time": rng.choice(TIME_RU), "time_kk": rng.choice(TIME_KK)}
    text = template.format(**values)
    return " ".join(text.split()).replace(" .", ".").replace(" ,", ",").replace(" ?", "?")


def _expand(tpl, rng: random.Random) -> list[str]:
    tid, label, lang, family, text, _amb = tpl
    short = family.endswith("_short")
    out = []
    for _ in range(SHORT_EXPANSIONS if short else EXPANSIONS):
        msg = _fill(text, rng)
        if not short:
            ru_side = lang in ("ru", "mixed")
            prefix = rng.choice(PREFIX_RU if ru_side else PREFIX_KK)
            suffix = rng.choice(SUFFIX_RU if ru_side and rng.random() < 0.8 else SUFFIX_KK if not ru_side else SUFFIX_RU)
            msg = " ".join(x for x in (prefix, msg, suffix) if x)
            if rng.random() < 0.08:
                msg += " " + rng.choice(CONTACT_RU).format(d=rng.randint(0, 8), a=rng.randint(100, 999),
                                                           b=rng.randint(10, 99), c=rng.randint(10, 99),
                                                           n=rng.randint(1, 99))
        r = rng.random()
        if r < 0.25:
            msg = msg.lower()
        elif r < 0.30:
            msg = msg.rstrip(".!?")
        if rng.random() < 0.15:
            msg = _typo(msg, rng)
        out.append(msg)
    return out


def _grams(text: str) -> frozenset:
    t = f" {normalize(text)} "
    return frozenset(t[i:i + 3] for i in range(len(t) - 2))


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a or b else 1.0


def max_similarity(items_grams: list[frozenset], pool: list[frozenset]) -> list[float]:
    """Максимальная Jaccard-близость каждого элемента к пулу (инвертированный индекс по 3-граммам)."""
    index: dict[str, list[int]] = {}
    for j, g in enumerate(pool):
        for gram in g:
            index.setdefault(gram, []).append(j)
    out = []
    for g in items_grams:
        overlap: dict[int, int] = {}
        for gram in g:
            for j in index.get(gram, ()):
                overlap[j] = overlap.get(j, 0) + 1
        best = 0.0
        for j, inter in overlap.items():
            union = len(g) + len(pool[j]) - inter
            best = max(best, inter / union if union else 1.0)
        out.append(best)
    return out


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(out_dir: Path = DATA_DIR) -> dict:
    rng = random.Random(SEED)
    ids = [t[0] for t in T]
    assert len(ids) == len(set(ids)), "duplicate template id"
    assert all(t[1] in LABELS for t in T)
    # Split по шаблонам: внутри (метка, язык) порядок по sha256(seed:id), затем шаблон SPLIT_PATTERN.
    split_of: dict[str, str] = {}
    groups: dict[tuple, list] = {}
    for t in T:
        groups.setdefault((t[1], t[2]), []).append(t[0])
    for key in sorted(groups):
        ordered = sorted(groups[key], key=lambda i: hashlib.sha256(f"{SEED}:{i}".encode()).hexdigest())
        for k, tid in enumerate(ordered):
            split_of[tid] = SPLIT_PATTERN[k % len(SPLIT_PATTERN)]
    rows, pii = [], {}
    for tpl in T:
        for k, raw in enumerate(_expand(tpl, rng)):
            text, counts = anonymize(raw)
            text = " ".join(text.split())
            for c, n in counts.items():
                pii[c] = pii.get(c, 0) + n
            rows.append({"id": f"{tpl[0]}-{k:02d}", "text": text, "label": tpl[1], "language": tpl[2],
                         "template_id": tpl[0], "family": tpl[3], "ambiguous": tpl[5], "split": split_of[tpl[0]],
                         "short": tpl[3].endswith("_short")})
    # (2) точные дубликаты после нормализации — до split-фильтрации
    by_norm: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        by_norm.setdefault(normalize(r["text"]), []).append(i)
    drop, conflicts = set(), 0
    for idxs in by_norm.values():
        labels = {rows[i]["label"] for i in idxs}
        if len(labels) > 1:
            conflicts += 1
            drop.update(idxs)
        else:
            drop.update(idxs[1:])
    exact_removed = len(drop)
    rows = [r for i, r in enumerate(rows) if i not in drop]
    # (4) близкие к обучающим элементы val/test исключаются
    train_g = [_grams(r["text"]) for r in rows if r["split"] == "train"]
    held = [r for r in rows if r["split"] != "train"]
    sims = max_similarity([_grams(r["text"]) for r in held], train_g)
    near_removed = 0
    for r, s in zip(held, sims):
        r["max_train_jaccard"] = round(s, 3)
        if s >= NEAR_DUP:
            r["split"] = "excluded_near_dup"
            near_removed += 1
    out_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = out_dir / CORPUS_PATH.name
    with open(corpus_path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps({k: r[k] for k in ("id", "text", "label", "language", "template_id", "family",
                                                     "ambiguous", "short")}, ensure_ascii=False) + "\n")
    split = {r["id"]: r["split"] for r in rows}
    counts = {}
    for r in rows:
        key = f'{r["split"]}/{r["label"]}'
        counts[key] = counts.get(key, 0) + 1
    manifest = {
        "corpus": corpus_path.name, "corpus_version": CORPUS_VERSION, "corpus_sha256": sha256_file(corpus_path),
        "evidence_type": "synthetic", "labels_by": "agent (Claude, R08) by LABELING_GUIDE.md — not expert human",
        "seed": SEED, "expansions": EXPANSIONS, "short_expansions": SHORT_EXPANSIONS, "templates": len(T),
        "split_unit": "template_id (group split)", "split_pattern": list(SPLIT_PATTERN),
        "template_split": dict(sorted(split_of.items())), "near_dup_threshold": NEAR_DUP,
        "removed": {"exact_duplicates": exact_removed, "label_conflicts": conflicts, "near_dup_val_test": near_removed},
        "anonymized_markers": pii, "rows": len(rows), "counts": dict(sorted(counts.items())),
        "split": split,
    }
    split_path = out_dir / SPLIT_PATH.name
    split_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    manifest["split_sha256"] = sha256_file(split_path)
    return manifest


def load_corpus(path: Path = CORPUS_PATH, split_path: Path = SPLIT_PATH) -> tuple[list[dict], dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    manifest = json.loads(split_path.read_text(encoding="utf-8"))
    if manifest["corpus_sha256"] != sha256_file(path):
        raise ValueError("corpus sha256 differs from split manifest")
    for r in rows:
        r["split"] = manifest["split"][r["id"]]
    return rows, manifest
