"""«ИИ-разбор пачки обращений» (П3, сцена 0): сотрудник загружает обращения, пришедшие за ночь, — Birge раскладывает
их по службам, склеивает повторы, ставит на карту и поднимает срочные. Всё в процессе, без сети.

    from ui.civic_ml_api import intake_analyze, intake_sample, intake_commit
    r = intake_analyze(["На остановке Хан Шатыр сломан навес", "Хан Шатыр аялдамасының шатыры сынған", …])
    r["summary"]   # {"total": 312, "tasks": 41, "services": 9, "urgent": 6, "merged": 37, "no_address": 5, "ms": 840}
    r["tasks"]     # [{id, title_ru, title_kk, category, services [{id, role, name_ru, name_kk}], why_ru, why_kk,
                   #   target {kind, id, label_ru, label_kk} | None, address_text, text_ids, people, urgent, …}]
    intake_commit(r["batch_id"])  # задачи с местом -> жалобы R09 (store.create); повтор того же batch_id — без дублей

Каждое обращение: moderate() (телефоны, ИИН, мат — «***»; дальше наружу идёт только этот текст) -> route() (категория:
сигналы текста и цепочка classify; службы и «нужны 2 службы» с объяснением) -> место по индексу карты R12
(web/civic/map/search_index.json: остановки, дворы, парки, площадки, улицы; не нашли — «адрес уточнить», место не
угадываем) -> срочность по явным правилам (люк, провода, газ, пожар, нет тепла / воды, опасно, дети + опасность).
Повторы: одна цель + одна категория + похожий текст (pair_score модуля дублей ml/civic_dedup); без места — только
одинаковые тексты. Числа итога считает код; ИИ — подсказки категории и служб, как везде в Birge.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from pathlib import Path

from ml.civic_dedup.normalize import KK_FOLD, detranslit, normalize
from ui.civic_ml_api.errors import MLServiceUnavailable
from ui.civic_ml_api.moderation import moderate
from ui.civic_ml_api.routing import VERSION as ROUTE_VERSION
from ui.civic_ml_api.routing import route, service_names

VERSION = "r04-intake-1"
MAX_TEXTS = 500
MAX_BYTES = 300 * 1024
MAX_TEXT = 2000          # длиннее — режем для разбора (в R09 запись не длиннее 2000 знаков)
MIN_TEXT = 3             # короче — не обращение (R09 TEXT_MIN)
MAX_BATCHES = 16         # разборы в памяти для «Создать задачи» (после перезапуска — разобрать снова)
DEVICE_PREFIX = "birge-intake"

ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = ROOT / "web" / "civic" / "map" / "search_index.json"
SAMPLE_R02 = ROOT / "data" / "civic" / "astana" / "demo-world" / "intake_night_v1.json"
SAMPLE_R04 = Path(__file__).with_name("intake_sample_r04.json")

# ---------------------------------------------------------------- подписи задач
# Короткое название задачи (им. падеж): по правилу совместного случая route(), уточнению или категории.
TITLES = {
    "roads": ("Дорога", "Жол"),
    "roads/pothole": ("Яма на дороге", "Жолдағы шұңқыр"),
    "roads/traffic_light_broken": ("Не работает светофор", "Бағдаршам істемейді"),
    "roads/traffic_light_timing": ("Режим светофора", "Бағдаршам режимі"),
    "roads/intersection": ("Опасный перекрёсток", "Қауіпті қиылыс"),
    "roads/marking": ("Стёрлась разметка", "Жол таңбасы өшіп қалған"),
    "roads/speed_bump": ("Лежачий полицейский", "Жасанды кедір-бұдыр"),
    "snow_ice": ("Снег и гололёд", "Қар мен көктайғақ"),
    "snow_ice/snow_not_cleared": ("Не убран снег", "Қар тазаланбаған"),
    "snow_ice/ice": ("Гололёд", "Көктайғақ"),
    "snow_ice/icicles": ("Сосульки и снег на крыше", "Шатырдағы сүңгілер мен қар"),
    "sidewalks": ("Тротуар", "Тротуар"),
    "sidewalks/crossing": ("Пешеходный переход", "Жаяу жүргіншілер өткелі"),
    "sidewalks/broken_sidewalk": ("Разбитый тротуар", "Бұзылған тротуар"),
    "sidewalks/accessibility": ("Пандус и бордюр", "Пандус пен жиек"),
    "transport": ("Остановка и транспорт", "Аялдама мен көлік"),
    "transport/stop_shelter": ("Навес и скамейки", "Шатыр мен орындықтар"),
    "transport/schedule": ("Расписание транспорта", "Көлік кестесі"),
    "transport/route": ("Маршрут транспорта", "Көлік бағыты"),
    "lighting": ("Освещение", "Жарықтандыру"),
    "lighting/lamp_off": ("Не горит фонарь", "Шам жанбайды"),
    "lighting/dark_yard": ("Темно во дворе", "Аулада қараңғы"),
    "lighting/blinking": ("Мигает фонарь", "Шам жыпылықтайды"),
    "lighting/wire_down": ("Оборван провод", "Сым үзілген"),
    "yards": ("Двор", "Аула"),
    "yards/playground": ("Детская площадка", "Балалар алаңы"),
    "yards/trees_lawn": ("Деревья и газон", "Ағаштар мен көгал"),
    "yards/benches": ("Скамейки и благоустройство", "Орындықтар мен абаттандыру"),
    "waste": ("Мусор", "Қоқыс"),
    "waste/bins_full": ("Переполнены баки", "Контейнерлер толып кеткен"),
    "waste/dump": ("Стихийная свалка", "Заңсыз қоқыс үйіндісі"),
    "waste/not_collected": ("Не вывезен мусор", "Қоқыс шығарылмаған"),
    "utilities": ("Коммунальные услуги", "Коммуналдық қызметтер"),
    "utilities/no_heating": ("Нет отопления", "Жылу жоқ"),
    "utilities/no_water": ("Нет воды", "Су жоқ"),
    "utilities/sewage": ("Канализация", "Кәріз"),
    "utilities/power_building": ("Нет света в доме", "Үйде жарық жоқ"),
    "smell_air": ("Запах и воздух", "Иіс пен ауа"),
    "smell_air/gas": ("Запах газа", "Газ иісі"),
    "smell_air/smoke_fire": ("Дым", "Түтін"),
    "smell_air/dust": ("Пыль", "Шаң"),
    "smell_air/bad_smell": ("Неприятный запах", "Жағымсыз иіс"),
    "noise_safety": ("Шум и безопасность", "Шу мен қауіпсіздік"),
    "noise_safety/noise_night": ("Шум ночью", "Түнгі шу"),
    "noise_safety/dangerous_place": ("Опасное место", "Қауіпті орын"),
    "noise_safety/stray_dogs": ("Бродячие собаки", "Қаңғыбас иттер"),
    "parking": ("Парковка", "Тұрақ"),
    "parking/yard_cars": ("Машины во дворе", "Ауладағы көліктер"),
    "parking/sidewalk_parking": ("Парковка на тротуаре", "Тротуардағы көліктер"),
    "parking/no_spaces": ("Не хватает мест для парковки", "Тұрақ орындары жетіспейді"),
    "other": ("Другое", "Басқа"),
}
JOINT_TITLES = {
    "dig_after_works": ("Яма после раскопок", "Қазбадан кейінгі шұңқыр"),
    "burst_pit": ("Течь и провал покрытия", "Ағу мен опырылған жабын"),
    "leak_ice": ("Наледь из-за течи", "Ағудан пайда болған мұз"),
    "pole_down": ("Упал столб", "Бағана құлаған"),
    "tree_on_wires": ("Дерево на проводах", "Сымдағы ағаш"),
    "roof_snow_walk": ("Снег с крыши на тротуаре", "Шатырдан түскен қар"),
    "signal_power": ("Светофор без электричества", "Электрсіз бағдаршам"),
    "two_outages": ("Отключения", "Ажыратулар"),
}

# «Как разбирали» — для экрана и объяснения жюри: что считает код, где подсказка ИИ.
METHOD_RU = (
    "Личные данные: телефоны и ИИН закрыты «***» до разбора.",
    "Категория и службы: правила и модель classify — подсказка ИИ, сотрудник проверяет.",
    "Место: название остановки, двора, парка или улицы из текста по карте (OSM); нет названия — «адрес уточнить».",
    "Повторы: одно место, одна категория, похожий текст.",
    "Срочно: явные правила — люк, провода, газ, пожар, нет тепла или воды, опасно для детей.",
)
METHOD_KK = (
    "Жеке деректер: телефон мен ЖСН талдауға дейін «***» белгісімен жабылады.",
    "Санат пен қызметтер: ережелер және classify моделі — ЖИ кеңесі, қызметкер тексереді.",
    "Орын: мәтіндегі аялдама, аула, саябақ не көше атауы карта бойынша (OSM); атау жоқ — «мекенжайды нақтылау».",
    "Қайталанулар: бір орын, бір санат, ұқсас мәтін.",
    "Шұғыл: нақты ережелер — люк, сым, газ, өрт, жылу не су жоқ, балаларға қауіпті.",
)

# ---------------------------------------------------------------- срочность (явные правила)
# Текст сравнивается в виде normalize(): нижний регистр, без цифр и пунктуации, казахские буквы сведены к русским
# (қ -> к, ұ -> у, і -> и, й -> и). Правило -> пояснение для сотрудника (ru, kk).
URGENT_RULES = (
    ("manhole", re.compile(r"\b(открыт\w*|ашык|без крышк\w*)\s+(канализационн\w* )?люк|\bлюк\w*\b.{0,40}"
                           r"\b(открыт|без крышк|нет крышк|ашык|какпаг\w* жок|провал)"),
     ("Открытый люк — можно упасть", "Ашық люк — құлап кетуге болады")),
    ("wires", re.compile(r"\b(провод\w*|сым\w*)\b.{0,30}\b(оборв|обрыв|упал|висит|висят|лежит|на земле|оголен|искр"
                         r"|узил|жерде|салбыра)|\b(оборван\w*|оголенн\w*|узилген)\s+(провод|сым)"),
     ("Оборван или оголён провод — опасно", "Сым үзілген не ашық — қауіпті")),
    ("gas", re.compile(r"\bзапах\w* газ|\bпахнет газ|\bпахнет\b.{0,10}\bгаз|\bгаз\w* иис|\bутечк\w* газ"),
     ("Запах газа — сообщить в 104", "Газ иісі — 104-ке хабарлау")),
    ("fire", re.compile(r"\bпожар\w*|\bзадымлен\w*|\bдым\w* (из|валит)|\bзагорел\w*|\bподожгл\w*|\bорт\b"
                        r"|\bортенип|\bжанып жатыр"),
     ("Пожар или дым", "Өрт не түтін")),
    ("no_heat", re.compile(r"\b(нет|отключ\w*|не работает|холодн\w*|не греют)\b.{0,25}\b(отоплен|батаре|тепл)"
                           r"|\b(отоплен\w*|батаре\w*)\b.{0,20}\b(нет|отключ|холодн|не греют|не работа)"
                           r"|\b(жылу|батарея\w*)\b.{0,15}\b(жок|берилмеи|суык)"),
     ("Нет отопления", "Жылу жоқ")),
    ("no_water", re.compile(r"\b(нет|отключ\w*)\b.{0,15}\bвод\w*|\bвод\w*\b.{0,10}\b(нет|отключ)|\bсу\b.{0,10}"
                            r"\b(жок|берилмеи|ажыратыл)"),
     ("Нет воды", "Су жоқ")),
    ("children", None, ("Опасно для детей", "Балаларға қауіпті")),
    ("danger", re.compile(r"\b(опасн\w*|угроз\w*|аварийн\w*|может упасть|обрушен\w*|обвал\w*|кауипти\w*"
                          r"|кулап кетуи мумкин)"),
     ("Опасное место", "Қауіпті орын")),
)
# «Горит» — пожар, только если речь не о свете: «не горит фонарь», «фонари горят днём» — освещение.
_BURNS = re.compile(r"\bгор(ит|ят)\b")
_BURNS_UNLESS = re.compile(r"\bне гор(ит|ят)\b|\bфонар|\bсвет|\bламп|\bосвещ|\bшам|\bжарык|\bтабло")
_CHILD = re.compile(r"\b(дет\w*|ребен\w*|ребят\w*|школьник\w*|бала\w*|окушы\w*)")
_CHILD_RISK = re.compile(r"\b(опасн\w*|травм\w*|упал\w*|упад\w*|порез\w*|пораня\w*|стекл\w*|гвозд\w*|торч\w*|"
                         r"провал\w*|люк\w*|ток\w*|провод\w*|кауипти\w*|жаракат\w*|сынган\w*|сынык\w*|шеге\w*)")


def urgency(norm_text: str):
    """(rule, why_ru, why_kk) первого сработавшего правила или None. norm_text — normalize(text)."""
    for name, rx, why in URGENT_RULES:
        if name == "children":
            if _CHILD.search(norm_text) and _CHILD_RISK.search(norm_text):
                return name, why[0], why[1]
            continue
        if rx.search(norm_text) or (name == "fire" and _BURNS.search(norm_text)
                                    and not _BURNS_UNLESS.search(norm_text)):
            return name, why[0], why[1]
    return None


# ---------------------------------------------------------------- место по названию (индекс карты R12)
_WORD = re.compile(r"[^\W_]+")
_RAW_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")      # «o'zen» (казахская латиница 2017 г.) — одно слово
_APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'", "`": "'", "´": "'", "‘": "'"})
_VOWELS = set("аеиоуыэюяё")
_ORDINAL = re.compile(r"(?<=\d)-[a-zа-яё]{1,3}\b", re.IGNORECASE)    # «1-й микрорайон» -> «1 микрорайон»
# Падежные окончания и казахские аффиксы (после KK_FOLD: ғ -> г, ң -> н, і -> и, й -> и): «Сауранда», «Байтерекке»,
# «шатырдағы», «Карбышевой». Другое продолжение слова («Арна» -> «Арнасай») — уже другое название.
_ENDINGS = ("а", "я", "у", "ю", "е", "ы", "и", "о", "ои", "еи", "ыи", "ии", "ом", "ем", "ам", "ям", "ах", "ях", "ою",
            "ею", "ого", "его", "ому", "ему", "ых", "их", "ым", "им", "ую", "юю", "ая", "яя", "ое", "ее", "ые", "ие",
            "ов", "ев", "ами", "ями",
            "сы", "си", "ны", "ни", "ды", "ди", "ты", "ти", "н", "нын", "нин", "дын", "дин", "тын", "тин", "ын", "ин",
            "га", "ге", "ка", "ке", "на", "не", "да", "де", "та", "те", "нда", "нде", "дан", "ден", "тан", "тен", "нан",
            "нен", "мен", "бен", "пен", "гы", "ги", "лар", "лер", "дар", "дер", "тар", "тер")
_SUFFIX = re.compile("(?:" + "|".join(sorted(_ENDINGS, key=len, reverse=True)) + ")+")

# Слово-подсказка рядом с названием: без неё одно общее слово («Алан», «Школа») местом не считается.
# (начала слов, целые короткие слова) после tokens(): «остановке», «аялдамада», «ул.», «пр.», «ЖК», «үйде».
CONTEXT = {
    "bus_stop": (("остановк", "остановоч", "астановк", "остоновк", "аялдам", "автобус"), {"ост"}),
    "yard": (("двор", "аула", "жилои", "комплекс", "подъезд", "подьезд", "киребер", "микрораион"),
             {"жк", "дом", "дома", "доме", "дому", "домом", "уи", "уиде", "уидин", "уиинде", "уидеги", "уиимиздин"}),
    "yard_strong": (("двор", "аула", "жилои", "комплекс", "микрораион"), {"жк"}),
    "street": (("улиц", "проспект", "переул", "шоссе", "бульвар", "коше", "данг", "проезд", "трасс", "тупик"),
               {"ул", "пр", "пер"}),
}
_TOKEN_ALIASES = {"мкр": "микрораион", "мкрн": "микрораион"}
# «На Айнаколь ямы», «по Сарайшык»: предлог + название с большой буквы — тоже улица.
_PREPOSITIONS = {"на", "по", "с", "со", "у", "возле", "около", "вдоль", "напротив", "между"}
# Названия-типы без имени («Сквер», «Парк») — не место.
_GENERIC = {"сквер", "парк", "саябак", "саябагы", "бульвар", "аллея", "алан", "аланы", "площадь", "алангы"}
# Тип в самом названии улицы — только целые слова (в «Көшек батыр» «көшек» — имя, а не «көше»).
_LABEL_TYPES = {"улица", "ул", "проспект", "пр", "переулок", "пер", "шоссе", "бульвар", "проезд", "тупик", "трасса",
                "коше", "кошеси", "дангыл", "дангылы", "тупиги", "жолы"}
_STREET_TYPES = (("street", ("улиц", "коше"), {"ул"}), ("avenue", ("проспект", "данг"), {"пр"}),
                 ("lane", ("переул",), {"пер"}), ("highway", ("шоссе", "трасс"), set()),
                 ("boulevard", ("бульвар",), set()), ("passage", ("проезд",), set()), ("deadend", ("тупик",), set()))


def _is_context(word: str, kind: str) -> bool:
    prefixes, exact = CONTEXT[kind]
    return word in exact or word.startswith(prefixes)


def _street_type(word: str) -> str | None:
    for name, prefixes, exact in _STREET_TYPES:
        if word in exact or word.startswith(prefixes):
            return name
    return None


KIND_RANK = {"bus_stop": 1, "yard": 1, "park": 1, "playground": 1, "street": 2}
CATEGORY_KIND = {  # какую цель брать первой, если в тексте их несколько
    "transport": "bus_stop", "yards": "yard", "waste": "yard", "utilities": "yard", "parking": "yard",
    "noise_safety": "yard", "roads": "street", "sidewalks": "street", "snow_ice": "street",
}
TARGET_KIND = {"bus_stop": "object", "park": "object", "playground": "object", "yard": "area", "street": "segment"}


def _tokenize(text: str) -> tuple[list[str], list[bool]]:
    """Слова для поиска мест и признак «с большой буквы» у каждого. Как normalize() (латиница -> кириллица,
    қ -> к …), но цифры остаются (номер дома, «Нурсая-2»); «1-й микрорайон» -> «1 микрорайон», «мкр» -> «микрораион»."""
    raw = _ORDINAL.sub("", unicodedata.normalize("NFC", str(text)).translate(_APOSTROPHES))
    toks, caps = [], []
    for word in _RAW_WORD.findall(raw):
        cap = word[:1].isupper()
        for part in _WORD.findall(detranslit(word.casefold()).translate(KK_FOLD)):
            toks.append(_TOKEN_ALIASES.get(part, part))
            caps.append(cap)
    return toks, caps


def tokens(text: str) -> list[str]:
    return _tokenize(text)[0]


def _stem(token: str) -> str:
    return token[:-1] if len(token) >= 5 and token[-1] in _VOWELS else token


def _token_match(text_tok: str, name_tok: str) -> int:
    """3 — то же слово, 2 — с окончанием («Сауранда»), 1 — одна опечатка в длинном слове («Шарбаккл»), 0 — нет."""
    if text_tok == name_tok:
        return 3
    if len(name_tok) < 4 or name_tok.isdigit():
        return 0
    stem = _stem(name_tok)
    if text_tok.startswith(stem):
        extra = text_tok[len(stem):]
        if not extra or (len(extra) <= 8 and _SUFFIX.fullmatch(extra) is not None):
            return 2
    if len(name_tok) >= 6 and abs(len(text_tok) - len(name_tok)) <= 1 and _one_edit(text_tok, name_tok):
        return 1
    return 0


def _one_edit(a: str, b: str) -> bool:
    """Строки отличаются одной правкой: замена, пропуск или лишняя буква."""
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        return a[i + 1:] == b[i + 1:]
    return a[i:] == b[i + 1:]


def _distinctive(variant: tuple[str, ...]) -> bool:
    """Редкое имя из двух слов и больше: «Инжу Арена», «Доспамбет жырау» — место и без слова-подсказки."""
    return len(variant) >= 2 and sum(len(t) >= 4 and not t.isdigit() for t in variant) >= 2


class Places:
    """Справочник мест из индекса поиска R12: имя -> цель. Ищет названия в тексте с падежными окончаниями."""

    def __init__(self, index: dict):
        self.schema = index.get("schema")
        self.entries: list[dict] = []
        self.by_key: dict[str, list[tuple[tuple[str, ...], int]]] = {}
        for obj in index.get("objects") or []:
            kind = obj.get("k")
            if kind not in TARGET_KIND:
                continue  # спортплощадки «Футбольное поле» — общее имя без места
            self._add(kind, obj["id"], obj.get("ru"), obj.get("kk"), obj.get("c"), obj.get("d"), obj.get("also"))
        for street in index.get("streets") or []:
            self._add("street", street["seg"], street.get("ru"), street.get("kk"), street.get("c"), street.get("d"))

    def _add(self, kind, target_id, label_ru, label_kk, point, district, also=None):
        if not label_ru or not isinstance(point, list):
            return
        stype = None
        if kind == "street":
            stype = next((_street_type(t) for t in tokens(label_ru) if t in _LABEL_TYPES), None)
        entry = {"kind": kind, "id": target_id, "label_ru": label_ru, "label_kk": label_kk or label_ru,
                 "point": point, "district": district, "also": list(also or []), "stype": stype}
        idx = len(self.entries)
        self.entries.append(entry)
        for variant in self._variants(kind, label_ru, label_kk):
            if variant and not all(t in _GENERIC for t in variant):
                self.by_key.setdefault(variant[0][:3], []).append((variant, idx))

    @staticmethod
    def _variants(kind, label_ru, label_kk) -> set[tuple[str, ...]]:
        """Последовательности слов, по которым место ищется в тексте."""
        names = set()
        for label in (label_ru, label_kk):
            if not label:
                continue
            quoted = re.findall(r"«([^»]+)»", label)
            if kind == "bus_stop" or kind == "playground":
                core = quoted[0] if quoted else label
            elif kind == "yard":
                core = label.split(":", 1)[1] if ":" in label else label
            else:
                core = label  # улица: тип отрезаем ниже (до или после имени); парк — вместе со словом «парк»
            toks = tokens(core.replace('"', " "))
            if kind == "street":
                toks = [t for t in toks if t not in _LABEL_TYPES] or toks
            if toks[:2] == ["жилои", "комплекс"]:                 # «Жилой комплекс Зелёный Квартал» = «ЖК …»
                toks = ["жк"] + toks[2:]
            if len(toks) > 1 and toks[0] == "жк":
                names.add(tuple(toks[1:]))
            if toks:
                names.add(tuple(toks))
        return names

    def find(self, text: str, category: str | None = None) -> dict | None:
        """Лучшее место, названное в тексте, или None («адрес уточнить»)."""
        toks, caps = _tokenize(text)
        found = []
        for i, tok in enumerate(toks):
            for variant, idx in self.by_key.get(tok[:3], ()):
                n = len(variant)
                if i + n > len(toks):
                    continue
                levels = [_token_match(toks[i + j], variant[j]) for j in range(n)]
                if not all(levels):
                    continue
                entry = self.entries[idx]
                ok = self._context_ok(entry, variant, toks, caps, i, i + n)
                if ok and min(levels) == 1 and not (entry["kind"] == "street" and self._typed(toks, i, i + n)):
                    ok = 0                                   # опечатка — только у улицы рядом со словом «улица»
                if ok:
                    found.append((i, n, entry, ok, sum(levels)))
        if not found:
            return None
        # Название внутри более длинного («улица Сарытогай» внутри остановки «улица Сарытогай») не считается.
        spans = [(f[0], f[0] + f[1]) for f in found]
        found = [f for f in found if not any(a <= f[0] and f[0] + f[1] <= b and b - a > f[1] for a, b in spans)]
        prefer = CATEGORY_KIND.get(category or "")

        def rank(item):
            i, n, entry, ok, exact = item
            kind = entry["kind"]
            plain = 0 if kind != "street" or ok == 2 or entry["stype"] in (None, "street") else 1
            return (0 if kind == prefer else KIND_RANK.get(kind, 3), -n, -ok, -exact, plain, i,
                    0 if entry["district"] else 1)

        return min(found, key=rank)[2]

    @staticmethod
    def _typed(toks, start, end) -> bool:
        near = toks[max(0, start - 2):start] + toks[end:end + 1]
        return any(_street_type(w) for w in near)

    @staticmethod
    def _context_ok(entry, variant, toks, caps, start, end) -> int:
        """0 — не место; 1 — место; 2 — место, и тип улицы в тексте тот же («проспект Абая», а не «улица Абая»)."""
        kind = entry["kind"]
        if kind in ("park", "playground"):
            return 1  # слово-тип («парк», «саябағы») уже внутри названия
        single = len(variant) == 1 and not variant[0].isdigit()
        if kind == "street":
            near = toks[max(0, start - 2):start] + toks[end:end + 1]
            if all(t.isdigit() or len(t) == 1 for t in variant):  # «улица Е-614», «улица 206»: тип — вплотную
                near = toks[max(0, start - 1):start] + toks[end:end + 1]
            types = {_street_type(w) for w in near} - {None}
            if types:
                return 2 if entry["stype"] in types else 1
            if _distinctive(variant):
                return 1
            if start > 0 and toks[start - 1] in _PREPOSITIONS and caps[start]:
                return 1                                         # «На Айнаколь ямы», «на Е-614»
            return int(not variant[-1].isdigit() and end < len(toks) and toks[end].isdigit())   # «Кенесары 40»
        if kind == "yard":
            if any(_is_context(t, "yard") for t in variant) or _distinctive(variant):
                return 1                                         # «1 микрорайон», «Инжу Арена»
            window = toks[max(0, start - 3):start] + toks[end:end + 2]
            if single:  # «Жарык», «Энергетик» — обычные слова: нужен «двор / ЖК» рядом и большая буква
                return int(caps[start] and any(_is_context(w, "yard_strong") for w in window))
            return int(any(_is_context(w, "yard") for w in window))
        window = toks[max(0, start - 3):start] + toks[end:end + 2]
        return int(any(_is_context(t, "bus_stop") for t in variant) or any(_is_context(w, "bus_stop") for w in window))


_PLACES: dict = {}
_PLACES_LOCK = threading.Lock()


def places() -> Places | None:
    """Справочник мест (лениво, один раз на процесс). Нет индекса R12 — None: места не ищем."""
    with _PLACES_LOCK:
        if "obj" not in _PLACES:
            try:
                _PLACES["obj"] = Places(json.loads(INDEX_PATH.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                _PLACES["obj"] = None
        return _PLACES["obj"]


# ---------------------------------------------------------------- вход
def _items(texts) -> list[tuple[str, str]]:
    """[(id, text)] из списка строк, строки («строка = обращение») или [{id, text}]. Пустые строки пропускаются."""
    if isinstance(texts, str):
        texts = texts.splitlines()
    if not isinstance(texts, (list, tuple)):
        raise ValueError("texts: список обращений или текст, где строка = обращение.")
    out, seen = [], set()
    for n, item in enumerate(texts, 1):
        if isinstance(item, dict):
            text, item_id = item.get("text"), item.get("id")
        else:
            text, item_id = item, None
        if not isinstance(text, str):
            raise ValueError("texts: каждое обращение — строка.")
        text = text.strip()
        if len(text) < MIN_TEXT:
            continue
        item_id = str(item_id) if isinstance(item_id, (str, int)) and str(item_id).strip() else f"t{n}"
        if item_id in seen:
            item_id = f"{item_id}-{n}"
        seen.add(item_id)
        out.append((item_id[:40], text))
    return out


def _check_limits(texts) -> None:
    if isinstance(texts, str):
        size = len(texts.encode("utf-8"))
    elif isinstance(texts, (list, tuple)):
        size = sum(len((t.get("text") if isinstance(t, dict) else t or "").encode("utf-8"))
                   for t in texts if isinstance(t, (str, dict)) and isinstance(t.get("text") if isinstance(t, dict)
                                                                             else t, str))
    else:
        size = 0
    if size > MAX_BYTES:
        raise ValueError(f"Слишком много текста: не больше {MAX_BYTES // 1024} КБ за раз.")


def load_sample(name: str = "night") -> dict:
    """Пример «обращения за ночь»: набор R02 (если есть в демо-мире), иначе фикстура R04. Всё — синтетика."""
    if name != "night":
        raise ValueError("sample: есть только «night».")
    for path, source in ((SAMPLE_R02, "R02 demo-world intake_night_v1 (синтетика)"),
                         (SAMPLE_R04, "R04 intake_sample_r04 (синтетика)")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        texts = [{"id": str(t.get("id")), "text": t.get("text")} for t in data.get("texts") or []
                 if isinstance(t, dict) and isinstance(t.get("text"), str)]
        if texts:
            return {"name": name, "texts": texts, "demo": True, "source": source}
    raise LookupError("sample")


# ---------------------------------------------------------------- разбор
# Название по самому тексту важнее названия уточнения: «люк» в «Канализации», «горячая вода» в «Нет отопления».
TITLE_HINTS = (
    (re.compile(r"\bлюк\w*"), ("Открытый люк", "Ашық люк"), "manhole"),
    (re.compile(r"\bгоряч\w* вод|\bыстык су"), ("Нет горячей воды", "Ыстық су жоқ"), None),
)


def _title(rule: str | None, category: str, subtopic: str | None, norm: str = "",
           urgent_rule: str | None = None) -> tuple[str, str]:
    if rule and rule.startswith("joint."):
        key = rule.split(".")[1]
        if key in JOINT_TITLES:
            return JOINT_TITLES[key]
    for rx, title, need_rule in TITLE_HINTS:
        if (need_rule is None or need_rule == urgent_rule) and rx.search(norm):
            return title
    return TITLES.get(f"{category}/{subtopic}") or TITLES.get(category) or TITLES["other"]


def _deduper():
    try:
        from ml.civic_dedup import get_deduper
        return get_deduper()
    except Exception:  # noqa: BLE001 — без модуля дублей склеиваем только одинаковые тексты
        return None


def _people_words(n: int) -> tuple[str, str]:
    m10, m100 = n % 10, n % 100
    if m10 == 1 and m100 != 11:
        ru = f"{n} обращение"
    elif 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        ru = f"{n} обращения"
    else:
        ru = f"{n} обращений"
    return ru, f"{n} өтініш"


def _analyze_items(items: list[tuple[str, str]]) -> list[dict]:
    """Разбор каждого обращения: публичный текст, категория и службы, место, срочность."""
    gaz = places()
    out = []
    for item_id, text in items:
        text = text[:MAX_TEXT]
        mod = moderate(text)
        norm = normalize(text)
        place = gaz.find(text) if gaz else None
        point = place["point"] if place else None
        routed = route(text=text, point=point)
        category = routed.get("category") or "other"
        if gaz and place and CATEGORY_KIND.get(category) and CATEGORY_KIND[category] != place["kind"]:
            place = gaz.find(text, category) or place   # несколько мест — берём то, что подходит к категории
            if place["point"] != point:
                routed = route(text=text, point=place["point"])
        if place and place["kind"] == "bus_stop" and routed.get("category") == "yards":
            # «На остановке сломана скамейка»: скамейка и навес остановки — павильон, а не двор.
            routed = route(text=text, category="transport", subtopic="stop_shelter", point=place["point"])
        out.append({"id": item_id, "text_public": mod["text_public"], "pii": bool(mod.get("pii")),
                    "rude": bool(mod.get("rude")), "norm": norm, "route": routed,
                    "category": routed.get("category") or "other", "subtopic": routed.get("subtopic"),
                    "place": place, "urgent": urgency(norm)})
    return out


def _cluster(rows: list[dict], dd) -> list[list[dict]]:
    """Повторы: одна цель + одна категория + похожий текст (pair_score); без места — только одинаковые тексты."""
    groups: "OrderedDict[tuple, list[dict]]" = OrderedDict()
    for row in rows:
        target = row["place"]["id"] if row["place"] else None
        key = (target, row["category"]) if target else (None, row["category"], row["norm"])
        groups.setdefault(key, []).append(row)
    clusters = []
    for key, members in groups.items():
        if key[0] is None:
            clusters.append(members)                       # без места: ключ уже включает текст
            continue
        local: list[list[dict]] = []
        for row in members:
            for cluster in local:
                if _same_problem(cluster[0], row, dd):
                    cluster.append(row)
                    break
            else:
                local.append([row])
        clusters.extend(local)
    return clusters


def _same_problem(head: dict, row: dict, dd) -> bool:
    """Одна цель и категория уже совпали. Разные уточнения («навес» и «расписание») — разные задачи; то же уточнение,
    тот же текст или pair_score модуля дублей не ниже порога — повтор."""
    a, b = head["subtopic"], row["subtopic"]
    if a and b and a != b:
        return False
    if (a and a == b) or head["norm"] == row["norm"]:
        return True
    if dd is None:
        return False
    score, threshold = dd.pair_score(head["text_public"], row["text_public"])
    return score >= threshold


def _task(cluster: list[dict], names: dict) -> dict:
    # Главный текст задачи — где route() нашёл больше служб (совместный случай), затем самый подробный.
    head = max(cluster, key=lambda r: (len(r["route"].get("services") or []), len(r["text_public"])))
    routed = head["route"]
    category, place = head["category"], head["place"]
    subs = [r["subtopic"] for r in cluster if r["subtopic"]]
    subtopic = head["subtopic"] or (max(subs, key=subs.count) if subs else None)   # «яма» у соседнего текста
    urgent = next((r["urgent"] for r in cluster if r["urgent"]), None)
    title_ru, title_kk = _title(routed.get("rule"), category, subtopic, " ".join(r["norm"] for r in cluster),
                                urgent[0] if urgent else None)
    services = [{"id": s["service"], "role": s.get("role") or "lead",
                 "name_ru": (names.get(s["service"]) or {}).get("ru") or s.get("name_ru") or s["service"],
                 "name_kk": (names.get(s["service"]) or {}).get("kk") or s.get("name_kk") or s["service"]}
                for s in routed.get("services") or []]
    people = len(cluster)
    # «Почему так» по частям (экран показывает их строками) и одной строкой why_ru / why_kk.
    parts = {"services": [routed.get("why_ru") or "", routed.get("why_kk") or ""]}
    if place:
        parts["place"] = [f"{place['label_ru']} — названо в тексте.", f"{place['label_kk']} — мәтінде аталған."]
    else:
        parts["place"] = ["Место в тексте не названо — уточните адрес.", "Мәтінде орын аталмаған — мекенжайды нақтылаңыз."]
    parts["repeats"] = None
    if people > 1:
        p_ru, p_kk = _people_words(people)
        parts["repeats"] = [f"Склеено {p_ru}: одно место, одна категория, похожий текст.",
                            f"{p_kk} біріктірілді: бір орын, бір санат, ұқсас мәтін."]
    parts["urgent"] = [urgent[1] + ".", urgent[2] + "."] if urgent else None
    why_ru = [parts["services"][0], "Место: " + parts["place"][0] if place else parts["place"][0]]
    why_kk = [parts["services"][1], "Орны: " + parts["place"][1] if place else parts["place"][1]]
    if parts["repeats"]:
        why_ru.append(parts["repeats"][0])
        why_kk.append(parts["repeats"][1])
    if urgent:
        why_ru.append(f"Срочно: {urgent[1][:1].lower()}{urgent[1][1:]}.")
        why_kk.append(f"Шұғыл: {urgent[2][:1].lower()}{urgent[2][1:]}.")
    target = None
    if place:
        target = {"kind": TARGET_KIND[place["kind"]], "id": place["id"], "label_ru": place["label_ru"],
                  "label_kk": place["label_kk"]}
        if target["kind"] == "object":
            target["object_kind"] = place["kind"]
    return {
        "title_ru": f"{title_ru} · {place['label_ru']}" if place else title_ru,
        "title_kk": f"{title_kk} · {place['label_kk']}" if place else title_kk,
        "category": category, "subtopic": subtopic,
        "services": services, "joint": bool(routed.get("joint")),
        "why_ru": " ".join(w for w in why_ru if w), "why_kk": " ".join(w for w in why_kk if w),
        "why_parts": {k: ({"ru": v[0], "kk": v[1]} if v else None) for k, v in parts.items()},
        "target": target, "point": place["point"] if place else None,
        "district": place["district"] if place else None,
        "address_text": place["label_ru"] if place else "",
        "text_ids": [r["id"] for r in cluster], "people": people,
        "texts": [{"id": r["id"], "text": r["text_public"]} for r in cluster[:5]],
        "urgent": bool(urgent), "urgent_rule": urgent[0] if urgent else None,
        "urgent_why": urgent[1] if urgent else None,                   # П3: поле контракта (ru), ниже — ru / kk
        "urgent_why_ru": urgent[1] if urgent else None, "urgent_why_kk": urgent[2] if urgent else None,
        "evidence": routed.get("evidence"),
        "existing": None,        # открытое обращение той же цели и категории — заполняет _attach_existing
        "_record_text": head["text_public"],
        "_head_id": head["id"],
        "_others": [(r["id"], r["text_public"]) for r in cluster if r is not head],
    }


def _attach_existing(tasks: list[dict], batch_id: str, demo: bool) -> None:
    """Задача, у цели которой уже есть открытое обращение той же категории (хранилище R09, connect_store), не создаёт
    новую запись: её тексты присоединятся к нему как «Я тоже» с текстом (просьба R01, П3: числа карты и «Картины дня»
    растут меньше, повтор склеен и с тем, что уже пришло). Свой пример к настоящим записям не цепляется и наоборот;
    записи этой же пачки (повторный разбор после «Создать задачи») — не «уже открытые»."""
    store = _store()
    if store is None or not callable(getattr(store, "list", None)):
        return
    for task in tasks:
        if not task["target"]:
            continue
        try:
            rows = store.list(category=task["category"], status=OPEN_STATUSES, target_id=task["target"]["id"], limit=20)
        except Exception:  # noqa: BLE001 — нет записей / старое хранилище: просто создаём новые
            continue
        for row in rows:
            if (bool(row.get("demo")) != bool(demo) or row.get("duplicate_of")
                    or (row.get("intake") or {}).get("batch_id") == batch_id
                    or row.get("id") in _OWN_RECORDS.get(batch_id, ())):
                continue
            if task["subtopic"] and row.get("subtopic") and row["subtopic"] != task["subtopic"]:
                continue     # как у склейки: «навес» и «расписание» одной остановки — разные проблемы
            task["existing"] = {"id": row.get("id"), "code": row.get("code"), "status": row.get("status"),
                                "people": 1 + int(row.get("metoo") or 0)}
            code = row.get("code") or row.get("id")
            parts = task["why_parts"]
            parts["existing"] = {
                "ru": f"Уже есть открытое обращение {code}: та же цель и категория — тексты присоединятся к нему («Я тоже»).",
                "kk": f"{code} ашық өтініші бар: орны мен санаты бірдей — мәтіндер соған қосылады («Мен де»)."}
            break


def analyze(texts=None, *, sample: str | None = None, keep: bool = True) -> dict:
    """Разбор пачки: список обращений -> задачи по службам (см. docstring модуля). keep — запомнить для commit."""
    started = time.perf_counter()
    demo = False
    if sample is not None:
        data = load_sample(sample)
        texts, demo = data["texts"], True
    if texts is None:
        raise ValueError("Нужен список обращений (texts) или пример (sample: \"night\").")
    _check_limits(texts)
    items = _items(texts)
    if not items:
        raise ValueError("Нет обращений: вставьте текст, где строка = одно обращение.")
    if len(items) > MAX_TEXTS:
        raise ValueError(f"Не больше {MAX_TEXTS} обращений за раз.")
    rows = _analyze_items(items)
    dd = _deduper()
    names = service_names()
    tasks = [_task(c, names) for c in _cluster(rows, dd)]
    tasks.sort(key=lambda t: (not t["urgent"], -t["people"], t["services"][0]["id"] if t["services"] else "",
                              t["title_ru"]))
    for n, task in enumerate(tasks, 1):
        task["id"] = f"t{n}"
    batch_id = hashlib.sha256((VERSION + "\n" + "\n".join(f"{i}\t{t}" for i, t in items)).encode("utf-8")).hexdigest()[:16]
    _attach_existing(tasks, batch_id, demo)
    ready = sum(1 for t in tasks if t["target"] is not None)
    to_existing = sum(1 for t in tasks if t["target"] is not None and t["existing"])
    summary = {
        "total": len(items), "tasks": len(tasks),
        "services": len({s["id"] for t in tasks for s in t["services"]}),
        "urgent": sum(1 for t in tasks if t["urgent"]),
        "merged": sum(t["people"] - 1 for t in tasks),
        "no_address": sum(1 for t in tasks if t["target"] is None),
        # «Создать задачи»: ready = задачи с местом; из них to_existing — к уже открытому обращению той же цели и
        # категории («Я тоже» с текстом), to_create — новые записи R09. Записей станет ровно to_create.
        "ready": ready, "to_existing": to_existing, "to_create": ready - to_existing,
        "pii_masked": sum(1 for r in rows if r["pii"]),
        "ms": 0,
    }
    by_service: "OrderedDict[str, dict]" = OrderedDict()
    for task in tasks:
        for s in task["services"][:1]:
            group = by_service.setdefault(s["id"], {"id": s["id"], "name_ru": s["name_ru"], "name_kk": s["name_kk"],
                                                    "tasks": 0, "urgent": 0})
            group["tasks"] += 1
            group["urgent"] += task["urgent"]
    summary["ms"] = round((time.perf_counter() - started) * 1000)
    result = {
        "batch_id": batch_id, "summary": summary, "tasks": [_public(t) for t in tasks],
        "services": list(by_service.values()),
        "method": {"pipeline": "moderate -> route (сигналы + classify) -> место по индексу R12 -> повторы -> срочность",
                   "steps_ru": METHOD_RU, "steps_kk": METHOD_KK,
                   "route": ROUTE_VERSION, "dedup": getattr(dd, "version", None) if dd else None,
                   "places": places().schema if places() else None},
        "demo": demo, "version": VERSION,
    }
    if keep:
        _remember(batch_id, tasks, demo)
    return result


def _public(task: dict) -> dict:
    return {k: v for k, v in task.items() if not k.startswith("_")}


# ---------------------------------------------------------------- «Создать задачи» (только функциями R09)
_BATCHES: "OrderedDict[str, dict]" = OrderedDict()
_BATCHES_LOCK = threading.Lock()
_OWN_RECORDS: dict[str, set] = {}      # batch_id -> id записей, созданных этой пачкой (запасной путь без intake в записи)
OPEN_STATUSES = ("new", "accepted", "in_progress")


def _remember(batch_id: str, tasks: list[dict], demo: bool) -> None:
    with _BATCHES_LOCK:
        _BATCHES[batch_id] = {"tasks": tasks, "demo": demo, "at": time.time()}
        _BATCHES.move_to_end(batch_id)
        while len(_BATCHES) > MAX_BATCHES:
            _BATCHES.popitem(last=False)


def _store():
    from ui.civic_ml_api.similar_search import complaint_store
    return complaint_store()


def _r09_entry():
    """Точка входа R09 для задач разбора (INTEGRATION R09 §G1) или None, если в сборке R09 старше."""
    try:
        from ui.civic_feedback.v2.integration import create_from_intake
    except Exception:  # noqa: BLE001
        return None
    return create_from_intake


def _for_r09(task: dict) -> dict:
    """Задача для R09: без служебных полей; главный текст — первым (R09 берёт текст первого обращения группы)."""
    out = _public(task)
    head = task["_head_id"]
    out["text_ids"] = [head] + [i for i in task["text_ids"] if i != head]
    out["text"] = task["_record_text"]
    out.pop("texts", None)
    out.pop("existing", None)
    return out


def commit(batch_id, task_ids=None, *, store=None, actor=None) -> dict:
    """Задачи разбора -> обращения R09, в процессе и только функциями R09:
      * задача с открытым обращением той же цели и категории (existing, см. _attach_existing) — store.metoo(id, device,
        note={text, point, target, category}) по каждому её тексту: «Я тоже» с текстом, как склейка в мастере жалобы
        (п. 9) — тексты видны в «Что объединено», ошибочно склеенное сотрудник выделит («Это разные проблемы»);
      * остальные — create_from_intake R09 (одна транзакция на пачку, «Сообщили N человек» = people, source "intake");
        в сборке без неё — store.create + store.metoo (своё устройство у задачи: у create предел 20 в час на устройство).
    Повтор того же batch_id — без дублей (id записи R09 — от batch_id и задачи; устройства «Я тоже» постоянны).
    Задачи без места не создаются: точку не угадываем."""
    if not isinstance(batch_id, str) or not re.fullmatch(r"[0-9a-f]{16}", batch_id):
        raise ValueError("batch_id: номер разбора из ответа intake/analyze.")
    if task_ids is not None and (not isinstance(task_ids, list) or len(task_ids) > MAX_TEXTS
                                 or not all(isinstance(t, str) for t in task_ids)):
        raise ValueError("task_ids: список номеров задач (t1, t2 …).")
    with _BATCHES_LOCK:
        batch = _BATCHES.get(batch_id)
    if batch is None:
        raise LookupError(batch_id)
    store = store if store is not None else _store()
    if store is None or not callable(getattr(store, "create", None)):
        raise MLServiceUnavailable("source_not_connected", "Хранилище обращений не подключено.")
    wanted = set(task_ids) if task_ids is not None else None
    chosen = [t for t in batch["tasks"] if wanted is None or t["id"] in wanted]
    ready = [t for t in chosen if t["target"] and t["point"]]
    out = {"batch_id": batch_id, "created": 0, "existing": 0, "joined_existing": 0, "joined": 0,
           "skipped_no_address": len(chosen) - len(ready), "failed": 0, "records": [], "demo": batch["demo"]}
    fresh = []
    for task in ready:
        if task.get("existing") and callable(getattr(store, "metoo", None)):
            _join_existing(store, batch_id, task, out)
        else:
            fresh.append(task)
    entry = _r09_entry()
    if fresh and entry is not None and callable(getattr(store, "_tx", None)):
        _create_r09(entry, store, batch_id, batch, fresh, out, actor)
    else:
        for task in fresh:
            _create_fallback(store, batch_id, batch, task, out)
    return out


def _device(batch_id: str, task: dict, n: int) -> str:
    """Устройство n-го текста задачи (1 — главный). Постоянное: повтор commit — «уже», а не новый голос."""
    base = f"{DEVICE_PREFIX}-{batch_id}-{task['id']}"
    return base if n == 1 else f"{base}-{n}"


def _note(task: dict, text: str) -> dict:
    return {"text": text, "point": task["point"], "target": {"kind": task["target"]["kind"], "id": task["target"]["id"]},
            "category": task["category"]}


def _join_existing(store, batch_id: str, task: dict, out: dict) -> None:
    existing = task["existing"]
    texts = [task["_record_text"]] + [text for _id, text in task["_others"]]
    added = 0
    for n, text in enumerate(texts, 1):
        try:
            _rec, result = store.metoo(existing["id"], _device(batch_id, task, n), note=_note(task, text))
        except Exception:  # noqa: BLE001 — обращение закрыли или удалили: этот текст не присоединён
            continue
        added += result == "added"
    out["joined_existing"] += 1
    out["joined"] += added
    out["records"].append({"task_id": task["id"], "complaint_id": existing["id"], "code": existing.get("code"),
                           "created": False, "joined_existing": True, "joined": added})


def _create_r09(entry, store, batch_id: str, batch: dict, tasks: list[dict], out: dict, actor) -> None:
    texts = {}
    for task in tasks:
        texts[task["_head_id"]] = task["_record_text"]
        texts.update({text_id: text for text_id, text in task["_others"]})
    by_id = {t["id"]: t for t in tasks}
    report = entry(store, [_for_r09(t) for t in tasks], batch_id=batch_id, texts=texts, demo=batch["demo"],
                   actor=actor or "Сотрудник акимата", method=VERSION)
    for kind in ("created", "existing"):
        for item in report.get(kind) or []:
            task = by_id.get(item.get("task_id")) or {}
            out[kind] += 1
            out["joined"] += max(0, int(task.get("people") or 1) - 1) if kind == "created" else 0
            out["records"].append({"task_id": item.get("task_id"), "complaint_id": item.get("id"),
                                   "code": item.get("code"), "created": kind == "created"})
    for item in report.get("skipped") or []:
        if item.get("reason") == "no_place":
            out["skipped_no_address"] += 1
        else:
            out["failed"] += 1
            out["records"].append({"task_id": item.get("task_id"), "error": item.get("reason")})


def _create_fallback(store, batch_id: str, batch: dict, task: dict, out: dict) -> None:
    """Старая сборка R09 без create_from_intake: store.create по главному тексту + «Я тоже» с текстом остальных."""
    target = {"kind": task["target"]["kind"], "id": task["target"]["id"]}
    payload = {"text": task["_record_text"], "category": task["category"], "category_source": "model",
               "target": target, "point": task["point"], "request_id": f"in-{batch_id}-{task['id']}",
               "source": "intake", "intake": {"batch_id": batch_id, "task_id": task["id"], "people": task["people"]}}
    if task["subtopic"]:
        payload["subtopic"] = task["subtopic"]
    if task["district"]:
        payload["district"] = task["district"]
    device = _device(batch_id, task, 1)
    record = None
    try:
        record, was_created = store.create(payload, device, demo=batch["demo"])
    except Exception as exc:  # noqa: BLE001 — уточнение не подошло к категории R09 и т. п.: пробуем без него
        error = exc
        if payload.pop("subtopic", None) is not None:
            try:
                record, was_created = store.create(payload, device, demo=batch["demo"])
            except Exception as exc2:  # noqa: BLE001
                error = exc2
        if record is None:
            out["failed"] += 1
            out["records"].append({"task_id": task["id"], "error": type(error).__name__})
            return
    _OWN_RECORDS.setdefault(batch_id, set()).add(record.get("id"))
    out["created" if was_created else "existing"] += 1
    added = 0
    if callable(getattr(store, "metoo", None)):
        for n, (_text_id, text) in enumerate(task["_others"], 2):
            try:
                _rec, result = store.metoo(record["id"], _device(batch_id, task, n), note=_note(task, text))
            except Exception:  # noqa: BLE001 — «Я тоже» не причина не создать задачу
                continue
            added += result == "added"
    out["joined"] += added
    out["records"].append({"task_id": task["id"], "complaint_id": record.get("id"), "code": record.get("code"),
                           "created": bool(was_created), "joined": added})


# ---------------------------------------------------------------- функции для шлюза R01 (маршруты intake/*)
def _staff_only(principal, context) -> None:
    """Шлюз R01 (staff=True) сам проверяет сессию и CSRF; вызов через шлюз без сотрудника — 403 и здесь."""
    if context is not None and principal is None:
        raise PermissionError("Разбор обращений доступен только сотруднику.")


def intake_analyze(texts=None, sample=None, body=None, principal=None, context=None, **_ignored) -> dict:
    """POST intake/analyze {texts | sample: "night"} — только сотрудник (шлюз, staff=True)."""
    _staff_only(principal, context)
    if isinstance(body, dict):
        texts = body.get("texts", texts)
        sample = body.get("sample", sample)
    if sample is not None and not isinstance(sample, str):
        raise ValueError("sample: «night».")
    return analyze(texts, sample=sample)


def intake_sample(name="night", body=None, principal=None, context=None, **_ignored) -> dict:
    """GET intake/sample — тексты примера «обращения за ночь» (синтетика, demo: true), только сотрудник."""
    _staff_only(principal, context)
    if isinstance(body, dict) and isinstance(body.get("name"), str):
        name = body["name"]
    return load_sample(name or "night")


def intake_commit(batch_id=None, task_ids=None, body=None, principal=None, context=None, **_ignored) -> dict:
    """POST intake/commit {batch_id, task_ids?} — задачи -> записи R09 (только сотрудник, CSRF — шлюз)."""
    _staff_only(principal, context)
    if isinstance(body, dict):
        batch_id = body.get("batch_id", batch_id)
        task_ids = body.get("task_ids", task_ids)
    actor = principal.get("username") if isinstance(principal, dict) and isinstance(principal.get("username"), str) else None
    return commit(batch_id, task_ids, actor=actor)


__all__ = ["VERSION", "MAX_TEXTS", "MAX_BYTES", "Places", "analyze", "commit", "intake_analyze", "intake_commit",
           "intake_sample", "load_sample", "places", "tokens", "urgency"]
