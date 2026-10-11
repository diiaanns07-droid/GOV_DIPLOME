"""Фильтр мата и оскорблений для публичных выводов текста (волна мелочей, п. 8; владелец R04).

Зачем. Жители пишут в сердцах. Публично (карта, «Рядом», идеи, «Вопрос акиму», любые будущие экраны)
грубые слова заменяются звёздочками — «Опять эта б******* яма» — смысл жалобы остаётся. Акимат видит
оригинал целиком и пометку «содержит грубые слова» (поле moderation в записи R09), текст для работы не теряется.

Что считается грубым (kinds):
  mat     — русский мат: хуй, пизд-, еб-, бля-, муда-, пидор, залупа, манда, хер- …
  vulgar  — вульгарное: говно, жопа, дерьмо, засрали, обоссали, гондон …
  insult  — оскорбление человека: дебил, идиот, урод, мразь, тварь, сука, шлюха, ублюдок …;
            казахские: ақымақ, оңбаған, малғұн, мисыз, қаншық, жезөкше, «иттің баласы»
  slur    — оскорбление по национальности или ориентации: чурка, хач, жид, педик, көтен …
  kk_mat  — казахский мат: қотақ, сігейін/сіктім, амың, көтің, боқ, «шешеңді …»
НЕ фильтруется резкая, но приличная критика («позор», «безобразие», «бездельники», «воруют», «коррупция»):
это суть обращения, её акимат должен читать как есть, а жители — видеть.

Как ищем (без сети и моделей, только re; ~20 мкс на текст жалобы, повторы — из кэша):
  1) слово -> нижний регистр, ё -> е; казахские буквы -> похожие русские (қ->к, ң->н, і->и …);
  2) обходы: латиница/цифры внутри русского слова (xуй, 6лядь, п1зда, бл@ть), слово целиком латиницей
     (blyat, nahuy, cyka), растянутые буквы (бляяяять), разрядка (х у й, б.л.я.т.ь);
  3) корни с якорем на начало слова и закрытым списком приставок/окончаний — чтобы не ловить
     «плохую», «тихую», «страхуйте», «небо», «себе», «веб», «сигнал», «мудрый», «просрочка», «сразу»,
     «ссылка», «рассада», «педикюр», «котенок», «көтеру», «ебін» (каз. «способ»), «жидкость».
Проверка ложных срабатываний — tests/civic/R04/round14/test_r04_profanity.py (корпуса R02, словари R11, подписи OSM:
0 срабатываний на 2,4 млн строк JSON и 172 тыс. строк текстов репозитория).

Функции:
  check(text)       -> Verdict(rude, count, kinds, masked, spans)
  mask(text)        -> str: текст со звёздочками (первая буква слова остаётся)
  is_rude(text)     -> bool
  moderation(text)  -> {"rude", "count", "kinds", "version"} — поле записи жалобы для акимата (R09)
  mask_json(obj)    -> (obj, n): все строки ответа API; без грубых слов — тот же объект без копии (шлюз R01)
  public_response(body, staff=False) -> body для отправки: сотруднику как есть, остальным — mask_json
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

VERSION = "r04-profanity-1"
LABEL_KEY = "moderation.rude"          # ключ i18n R11 для пометки у акимата
LABELS = {"ru": "Содержит грубые слова", "kk": "Дөрекі сөздер бар"}  # запасной текст, если ключа нет
MASK_CHAR = "*"

# --------------------------------------------------------------------------- нормализация
# Казахские буквы -> похожие русские: один набор русских корней ловит и «қотақ», и «котак».
_KK_UNMARK = str.maketrans({"ә": "а", "ғ": "г", "қ": "к", "ң": "н", "ө": "о", "ұ": "у", "ү": "у", "һ": "х", "і": "и"})
# Буквы, которые есть только в казахском. Слово с ними — казахское: русские корни к нему не применяем
# («ебін» — «способ», «көтеру» — «поднять»). «і» сюда не входит: её подставляют и вместо «и» (п1зда, пізда).
_KK_ONLY = set("әғқңөұүһ")
# Латиница, цифры и знаки, которыми подменяют похожие русские буквы внутри русского слова (xуй, 6ля, бл@ть).
_LOOKALIKE = str.maketrans({
    "a": "а", "b": "б", "c": "с", "d": "д", "e": "е", "h": "н", "i": "и", "k": "к", "l": "л", "m": "м",
    "n": "п", "o": "о", "p": "р", "r": "г", "s": "с", "t": "т", "u": "и", "x": "х", "y": "у", "z": "з",
    "0": "о", "1": "и", "3": "з", "4": "ч", "6": "б", "@": "а", "$": "с",
})
_CYR = re.compile(r"[а-яеәғқңөұүһі]")
_LAT = re.compile(r"[a-z]")
_OBF = re.compile(r"[a-z0-9@$]")
_HEXISH = re.compile(r"\d|^[a-f]+$")
_REPEAT = re.compile(r"(.)\1+")
# Слово: буквы/цифры/@/$, хотя бы одна буква (чистые числа — координаты в JSON — пропускаются движком re).
_TOKEN = re.compile(r"(?<![\w@$])(?=[\w@$]*[^\W\d_])[\w@$]+")
# Разрядка: ≥ 3 одиночных знака через пробел, точку, дефис, подчёркивание («х у й», «б.л.я.т.ь»).
_SPACED = re.compile(r"(?<![\w@$])(?:[\w@$][ .\-_·]{1,2}){2,}[\w@$](?![\w@$])")
_SPACED_SEP = re.compile(r"[ .\-_·]")

# --------------------------------------------------------------------------- корни
# Каждый шаблон применяется к ОДНОМУ слову (re.match — от начала слова); «$» — точная форма слова.
# Приставки перечислены явно: «на|по|ни…» + корень, иначе «плохую», «страхуй», «себе» были бы матом.
_P_HUY = r"(?:на|по|ни|до|за|от|ото|у|при|рас|раз|вы|под|о|об|а|с|в|ох|ах|недо|пере)"
_P_EB = (r"(?:за|у|на|вы|от|отъ|до|по|при|под|подъ|пере|недо|раз|разъ|рас|съ|сь|въ|вь|изъ|объ|обь|долбо|ни"
         r"|про|вз|взъ|за)")
_RU = {
    "mat": [
        rf"{_P_HUY}?ху[йяеию]",
        r".*п[еи]зд",                                 # пизд- в любом месте слова (распиздяй, спиздили)
        rf"{_P_EB}?(?:е|йо)б(?:а|ал|ан|ат|ет|ут|у|л|к|ну|ыр|ись|ищ|уч|ок|ош|ен)",
        r"долбо[её]б",
        r"(?:вы)?бля(?:$|[дт])",                      # бля, блядь, блять, выблядок; не «бляха», «бляшка»
        r"бла[дт]ь$",                                 # «бл@ть» после замены @ -> а; не «блат», «блатной»
        r"муд(?:ак|ач|ил|озвон|оеб|ень|ня)",          # не «мудрый»
        r"пид[оа]?р",                                 # пидор, пидар, пидр; не «Педро»
        r"залуп",
        r"манд(?:а|ы|е|у|ой|авош\w*)$",               # не «мандарин», «мандат»
        rf"(?:на|по|о|от|за|ни)?хер(?:|а|у|ом|ня|ни|ню|ней|ово|овый|овая|овое|овые|ов|ач\w*|ен\w*|ну\w*)$",
    ],
    "vulgar": [
        r"г[ао]ндон",
        r"(?:черно)?жоп",
        r"г[ао]вн",
        r"дерьм",
        # засрали, насрать, обосрались, срач; не «сразу», «срок», «срабатывает», «просрочка», «сравнить»
        r"(?:за|на|об|обо|по|вы|у)?ср(?:ать|ал|ан|ач|ак|ет|ешь|ут)",
        # обоссали, ссаный, ссыт; не «ссылка», «ссадина», «ссора», «рассада», «поссорились»
        r"(?:обо|о|об|на|за|по|вы)?сс(?:ать|ал|ан|ак|ыт|ыш|ыкун)",
    ],
    "insult": [
        r"с+ук(?:а|и|у|ой|ам|ами|ах|ин|ина|ины|ино|ину|иным|иных)$",   # не «сук» (ветка), «сукно»
        r"суч(?:ка|ки|ке|ку|кой|ара\w*)$",
        r"шлюх", r"шалав",
        r"мраз(?:ь|и|ей|ям|ями|ях|от\w*)$",
        r"твар(?:ь|и|ей|ям|ями|ях)$",
        r"урод(?:|а|у|ом|е|ы|ов|ам|ами|ах|ина|ины|ине|ину|иной)$",      # не «уродливый», «урожай»
        r"дебил", r"идиот", r"придур(?:ок|к|ош)", r"ублюд", r"кретин", r"дегенерат", r"олигофрен", r"быдл",
        r"скотин(?:а|ы|е|у|ой)$",
        r"чмо(?:$|ш)",
        r"сволоч",
        r"гнид(?:а|ы|е|у|ой|ам|ами)$",
        r"падл(?:а|ы|е|у|ой)$", r"паскуд",
    ],
    "slur": [
        r"педик(?:|и|а|ов|ам|ами|ах|у|ом)$",           # не «педикюр»
        r"педераст", r"гомик",
        r"чурк(?:а|и|е|у|ой|ам|ами|ах)$",
        r"хач(?:|и|ей|а|у|ом|ам|ами|ах|ик|ики|иков)$",
        r"жид(?:|ы|ов|а|у|ом|ам|ами|ах|овск\w*|яр\w*)$",  # не «жидкость», «жидкий»
        r"нерус(?:ь|и|ью)$", r"чучмек", r"узкоглаз",
        r"хохл(?:ы|ов|ам|ами|а|у|ом)$", r"хохол$", r"москал(?:ь|и|ей|я|ю|ям)$", r"кацап",
    ],
}
# Казахские корни на слове БЕЗ спецбукв (қотақ и котак — одно и то же после _KK_UNMARK).
_KK_UNMARKED = {
    "kk_mat": [
        r"кота[кг]",                                   # қотақ; не «катаклизм», «котенок»
        r"си(?:к(?:|ейин|ем|емин|тим|ти|тир|тирши|пе|пей|кен|ип)|г(?:ейин|ем|емин|ип|у))$",  # не «сигнал», «сигарета»
    ],
    "insult": [
        r"каншык", r"жезокше", r"акымак", r"онбаган", r"малгун", r"мисыз",
    ],
}
# Казахские слова, которые без спецбукв совпадают с обычными русскими (көт ≠ кот, ам ≠ «Амина», боқ ≠ бок):
# только в написании со спецбуквами.
_KK_MARKED = {
    "kk_mat": [
        r"ам[ыі]ң(?:|ды|ді|а|е|нан|нен|ыз)$",
        r"көт(?:|ің|іңе|іңді|ін|ке)$",                 # не «көтеру» (поднять), «көтерілді»
        r"боқ(?:|қа|тан|ты)$",                         # не «боқтық» (мусор — так пишут о свалке)
    ],
    "slur": [
        r"көтен(?:|дер|ге|ді|нің|шек)$",
    ],
}
# Слово целиком латиницей: русский мат транслитом (blyat, nahuy, pizdec), подмена x/y (xyu, cyka),
# казахский латиницей (kotak, qanshyq) и английская брань. Отдельный короткий список, а не транслит всего
# русского набора: транслит превращал обычные слова в мат («other» -> «отхер», «cpython» -> «срут…»).
_LATIN = {
    "mat": [
        r"(?:na|po|ni|do|za|o|a)?(?:h|x|kh)u(?:y|i|j|e|ya|yu|yo)",
        r"(?:na|po|ni|do|za)?xy(?:i|y|u|e|ya)",
        r".*p[ie]zd",
        r"(?:za|u|na|vy|ot|do|po|pri|pod|raz|pro)?(?:e|yo|jo|ye)b(?:a|al|an|at|u|l|nu|ut|et)",
        r"(?:vy)?bl(?:y|j)a(?:$|d|t)",
        r"mud(?:ak|il)", r"pid[oa]?r", r"zalup",
        r"(?:mother)?f+u+c+k", r"sh+i+t+(?:s|ty|head|hole)?$", r"bitch", r"assh+ole", r"cunt", r"dickhead",
    ],
    "vulgar": [r"g[ao]ndon", r"(?:zh|j)op(?:a|u|e|oy)$", r"g[ao]vn(?:o|a|u|om|e)$"],
    "insult": [r"s+u+k(?:a|i|u)$", r"cyka$", r"mraz", r"debil", r"idiot", r"shlyuh", r"ublyud",
               r"(?:aq|ak)ymaq|akymak", r"(?:q|k)anshy(?:q|k)"],
    "kk_mat": [r"(?:q|k)otaq|kotak", r"si[kg](?:eyin|eiin|ejin|tim|tir|tirshi)$"],
}
# Латинские слова, которые совпадают с шаблоном случайно.
_LATIN_OK = {"ebay", "hue", "hues", "huey", "suki", "sukiyaki", "ebullient"}
# Казахские оскорбления из двух слов (на всём тексте без спецбукв, в нижнем регистре).
# Подсказка: второе слово фразы — без неё дорогие фразовые выражения не запускаются.
_PHRASE_HINT = re.compile(r"балас|[уұ]рай|аузын|с[іи][кг]ей", re.IGNORECASE)
_KK_PHRASES = [
    ("insult", re.compile(r"(?<!\w)иттин\s+баласы(?!\w)")),
    ("kk_mat", re.compile(r"(?<!\w)(?:шешен|акен|апан)(?:ди|нин)\s+(?:урайын|сигейин|сикейин|аузын\w*)(?!\w)")),
]


def _compile(groups: dict) -> list:
    return [(kind, re.compile("(?:" + "|".join(patterns) + ")")) for kind, patterns in groups.items()]


_RU_RX = _compile(_RU)
_KK_UNMARKED_RX = _compile(_KK_UNMARKED)
_KK_MARKED_RX = _compile(_KK_MARKED)
_LATIN_RX = _compile(_LATIN)

# --------------------------------------------------------------------------- проверка слова
_CACHE: dict[str, str | None] = {}
_CACHE_MAX = 200_000


def _variants(low: str) -> list[str]:
    """Варианты написания слова для проверки (уже в нижнем регистре, ё -> е)."""
    base = [low.translate(_LOOKALIKE) if _OBF.search(low) else low]  # «xуй», «6лядь», «п1зда», «бл@ть»
    out = []
    for word in base:
        out.append(word)
        squeezed = _REPEAT.sub(r"\1", word)              # «бляяяять» -> «блять», «сссука» -> «сука»
        if squeezed != word:
            out.append(squeezed)
    return out


def _word_kind(token: str) -> str | None:
    """Вид грубого слова или None. Результат кэшируется: слова в ответах API повторяются."""
    hit = _CACHE.get(token, False)
    if hit is not False:
        return hit
    hit = _classify_word(token)
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[token] = hit
    return hit


def _classify_word(token: str) -> str | None:
    low = token.lower().replace("ё", "е").replace("_", "")   # «х_у_й» -> «хуй»
    if len(low) < 3:
        return None
    if not _CYR.search(low):
        # Слово без кириллицы — только латинские шаблоны (не транслит: «other» -> «отхер» был бы матом).
        # С цифрами или из одних hex-знаков — это id, код, хэш («eba61783-…», «c-0f3a…»), не слово.
        if low in _LATIN_OK or not _LAT.search(low) or _HEXISH.search(low):
            return None
        for word in {low, _REPEAT.sub(r"\1", low)}:
            for kind, rx in _LATIN_RX:
                if rx.match(word):
                    return kind
        return None
    kk_word = any(ch in _KK_ONLY for ch in low)
    if kk_word:
        for kind, rx in _KK_MARKED_RX:
            if rx.match(low):
                return kind
    for word in _variants(low):
        plain = word.translate(_KK_UNMARK)
        if not kk_word:
            for kind, rx in _RU_RX:
                if rx.match(plain):
                    return kind
        for kind, rx in _KK_UNMARKED_RX:
            if rx.match(plain):
                return kind
    return None


# --------------------------------------------------------------------------- текст
@dataclass
class Verdict:
    rude: bool
    count: int = 0
    kinds: list = field(default_factory=list)
    masked: str = ""
    spans: list = field(default_factory=list)     # [(start, end, kind)] в исходном тексте

    def as_dict(self) -> dict:
        return {"rude": self.rude, "count": self.count, "kinds": self.kinds, "masked": self.masked}


def _find(text: str, first_only: bool = False) -> list:
    """Места грубых слов в тексте: [(start, end, kind)], отсортированы, без пересечений."""
    spans, taken = [], []
    tokens = list(_TOKEN.finditer(text))
    # Разрядка («х у й» -> «хуй») возможна, только если в тексте есть хотя бы 3 однобуквенных «слова».
    if sum(1 for m in tokens if m.end() - m.start() == 1) >= 3:
        for m in _SPACED.finditer(text):
            kind = _word_kind(_SPACED_SEP.sub("", m.group()))
            if kind:
                spans.append((m.start(), m.end(), kind))
                taken.append((m.start(), m.end()))
                if first_only:
                    return spans
    for m in tokens:
        kind = _word_kind(m.group())
        if kind and not any(a <= m.start() < b for a, b in taken):
            spans.append((m.start(), m.end(), kind))
            if first_only:
                return spans
    if _PHRASE_HINT.search(text):
        low = text.lower().replace("ё", "е")
        if len(low) == len(text):                     # смещения совпадают с исходным текстом
            plain = low.translate(_KK_UNMARK)
            for kind, rx in _KK_PHRASES:
                for m in rx.finditer(plain):
                    if not any(a < m.end() and m.start() < b for a, b, _ in spans):
                        spans.append((m.start(), m.end(), kind))
                        if first_only:
                            return spans
    spans.sort()
    return spans


def _apply_mask(text: str, spans: list) -> str:
    """Первая буква грубого слова остаётся, остальные буквы и цифры -> «*» (пробелы и знаки — как были)."""
    if not spans:
        return text
    out, pos = [], 0
    for start, end, _kind in spans:
        out.append(text[pos:start])
        piece = text[start:end]
        out.append(piece[0] + "".join(MASK_CHAR if (ch.isalnum() or ch in "@$") else ch for ch in piece[1:]))
        pos = end
    out.append(text[pos:])
    return "".join(out)


def check(text) -> Verdict:
    """Полная проверка: есть ли грубые слова, сколько, какие виды, текст со звёздочками."""
    if not isinstance(text, str) or not text:
        return Verdict(False, masked=text if isinstance(text, str) else "")
    spans = _find(text)
    kinds = sorted({kind for _a, _b, kind in spans})
    return Verdict(bool(spans), len(spans), kinds, _apply_mask(text, spans), spans)


def is_rude(text) -> bool:
    """Есть ли грубые слова. Проверенные строки — из кэша (подписи и тексты повторяются из ответа в ответ)."""
    return isinstance(text, str) and bool(text) and _masked_or_none(text) is not None


def mask(text):
    """Текст для публичного вывода. Не строка — возвращается как есть."""
    if not isinstance(text, str) or not text:
        return text
    spans = _find(text)
    return _apply_mask(text, spans) if spans else text


def moderation(text) -> dict:
    """Поле для записи жалобы (R09 при создании): акимат видит пометку «Содержит грубые слова».
    Чистый текст — из кэша строк (список сотрудника на 5 000 жалоб не пересчитывает каждую)."""
    if not is_rude(text):
        return {"rude": False, "count": 0, "kinds": [], "version": VERSION}
    v = check(text)
    return {"rude": v.rude, "count": v.count, "kinds": v.kinds, "version": VERSION}


# --------------------------------------------------------------------------- JSON-ответы API
# Ключи, под которыми только геометрия и числа: их не обходим (ответ тепловой карты — в основном координаты).
_SKIP_KEYS = frozenset({"geometry", "coordinates", "bbox", "point", "points"})
_CLEAN = object()                       # метка «строка проверена, грубых слов нет» в кэше строк
_STR_CACHE: dict = {}                   # строка -> _CLEAN или текст со звёздочками
_STR_CACHE_MAX = 100_000
_STR_CACHE_LEN = 2_000                  # длинные строки не кэшируем (тексты жалоб и так короткие)


def _masked_or_none(text: str):
    """Текст со звёздочками или None, если грубых слов нет. Подписи целей повторяются из ответа в ответ —
    проверенные строки берутся из кэша."""
    hit = _STR_CACHE.get(text)
    if hit is None:
        masked = mask(text)
        hit = _CLEAN if masked is text else masked
        if len(text) <= _STR_CACHE_LEN:
            if len(_STR_CACHE) >= _STR_CACHE_MAX:
                _STR_CACHE.clear()
            _STR_CACHE[text] = hit
    return None if hit is _CLEAN else hit


def _needs_mask(obj) -> bool:
    """Есть ли в ответе хоть одна строка с грубым словом (обход без рекурсии и без копий)."""
    stack = [obj]
    pop, push = stack.pop, stack.append
    while stack:
        item = pop()
        kind = type(item)
        if kind is str:
            if _masked_or_none(item) is not None:
                return True
        elif kind is dict:
            for key, value in item.items():
                if key not in _SKIP_KEYS and value is not None and type(value) not in (int, float, bool):
                    push(value)
        elif kind is list or kind is tuple:
            stack.extend(item)
    return False


def _walk(obj):
    if isinstance(obj, str):
        masked = _masked_or_none(obj)
        return (obj, 0) if masked is None else (masked, 1)
    if isinstance(obj, dict):
        total, out = 0, {}
        for key, value in obj.items():
            if key in _SKIP_KEYS:
                out[key] = value
                continue
            out[key], n = _walk(value)
            total += n
        return out, total
    if isinstance(obj, (list, tuple)):
        total, out = 0, []
        for value in obj:
            item, n = _walk(value)
            out.append(item)
            total += n
        return out, total
    return obj, 0


def mask_json(obj):
    """Все строки ответа -> со звёздочками (ключи, числа и геометрия — как есть). -> (объект, сколько строк изменено).

    Быстрый путь: сначала только проверка (без копий); нет грубых слов — возвращается ТОТ ЖЕ объект.
    Копия строится лишь для ответа, где грубое слово есть, и исходный объект не меняется (оригинал — акимату).
    """
    if not _needs_mask(obj):
        return obj, 0
    return _walk(obj)


def public_response(body, staff: bool = False):
    """Тело ответа API для отправки: сотруднику акимата — как есть (оригинал), остальным — со звёздочками."""
    if staff:
        return body
    return mask_json(body)[0]


__all__ = ["LABELS", "LABEL_KEY", "VERSION", "Verdict", "check", "is_rude", "mask", "mask_json", "moderation",
           "public_response"]
