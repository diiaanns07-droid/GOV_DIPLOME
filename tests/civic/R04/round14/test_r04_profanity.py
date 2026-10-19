"""R04 · волна мелочей п. 8: фильтр мата и оскорблений (ui/civic_ml_api/profanity.py).

Проверяем то, что важно на защите и в жизни:
  - мат ru/kk и типичные обходы ловятся;
  - обычные слова жалоб НЕ ловятся (плохую, страхуйте, небо, сигнал, просрочка, ебін, көтеру, other, id-хэши);
  - публичный текст со звёздочками, у акимата оригинал + пометка;
  - JSON-ответ без грубых слов возвращается тем же объектом (быстрый путь), с ними — маскируются только строки;
  - на корпусах репозитория (синтетика R02, словари R11, категории, подписи OSM) — 0 срабатываний.
"""

from __future__ import annotations

import glob
import gzip
import json
import time
from pathlib import Path

import pytest

from ui.civic_ml_api import profanity as P

ROOT = Path(__file__).resolve().parents[4]

RUDE = {
    "mat": ["хуй", "Нахуй такую дорогу", "ПОХУЙ им", "охуели совсем", "нихуя не делают", "хуёвая дорога",
            "пиздец", "спиздили лавку", "распиздяи", "заебали", "ебаные ямы", "уебки", "долбоёбы", "наебали",
            "ебанутые", "проебали", "блядь", "блять", "бля", "выблядок", "мудаки", "мудила", "пидорасы", "залупа",
            "херня", "нахер", "охеренно", "манда", "пиздато"],
    "vulgar": ["жопа", "говно", "дерьмо", "засрали двор", "насрали", "обосрались", "срач", "обоссали подъезд",
               "ссаный лифт", "гондоны"],
    "insult": ["сука", "суки", "сукин сын", "сучка", "шлюха", "мразь", "мрази", "твари", "уроды", "дебилы", "идиоты",
               "придурки", "ублюдки", "кретины", "быдло", "скотина", "чмо", "сволочи", "гниды", "падла", "паскуда"],
    "slur": ["педики", "чурки", "хачи", "жиды", "нерусь", "көтен"],
    "kk": ["қотақ", "котак", "сігейін", "сигейин", "сіктім", "сиктим", "амыңды", "көтің", "қаншық", "каншык",
           "жезөкше", "ақымақтар", "акымак", "оңбаған", "малғұн", "мисыз", "боқ", "иттің баласы", "шешеңді ұрайын",
           "Иттин баласы"],
    "obfuscated": ["xуй", "6лядь", "п1здец", "бл@ть", "бляяяяять", "сссука", "х у й", "б.л.я.т.ь", "п-и-з-д-е-ц",
                   "blyat", "nahuy", "pizdec", "cyka", "xyu", "suka", "huy", "ebat", "mudak", "zaebali", "blyaaaat",
                   "pohuy", "kotak", "aqymaq", "qanshyq", "sikeyin", "fuck", "motherfucker", "shit", "bitch"],
}

CLEAN = [
    # «ху» не в начале слова и не после приставки
    "плохую дорогу", "тихую улицу", "страхуйте", "застрахуем", "глухую стену", "сухую траву", "похуже", "похудеть",
    "худой забор", "хулиганы", "хутор", "выхухоль", "хуже некуда",
    # «еб» внутри обычных слов и казахское «ебі» (способ)
    "небо", "себе", "хлеб", "веб-сайт", "вебинар", "ребенок", "требует", "потребовать", "ебін тауып", "ебедейсіз",
    # похожие начала
    "бляха", "бляшка", "блат", "мудрый", "мудрость", "мандарин", "мандат", "Педро", "педикюр", "педагог", "педиатр",
    "просрочка", "срок", "сразу", "срабатывает", "сравнить", "средний", "посредник", "усреднить", "ссылка",
    "ссадина", "ссора", "рассада", "рассказ", "поссорились", "касса", "массаж", "кассир", "Херсон", "херувим",
    "котенок", "кот", "котангенс", "катаклизм", "көтеру", "көтерілді", "боқтық", "бок дома", "сбоку", "сигнал",
    "сигарета", "Амина", "жидкость", "жидкий", "сукно", "сук", "сучок", "уродливый", "урожай", "тупик", "хохолок",
    "Москалев", "скот", "скотный", "падеж", "обосновать", "страхование", "трассу",
    # резкая, но приличная критика — суть обращения, её не прячем
    "позор", "безобразие", "бездельники", "воруют", "коррупция", "дурак", "отписки",
    # латиница, id и коды в ответах API
    "other", "another", "together", "cpython", "scalable", "scale_exp", "degenerate", "hue", "huge", "human", "hub",
    "Huawei", "Hyundai", "pizza", "debate", "website", "eBay", "ebony", "shuttle",
    "eba61783-9060-4b8a-9c13-99329a45034a", "c-ebabcafe00112233", "osm-w123-4", "B-0007",
    # смешанные цифры и буквы
    "Нурa", "3шт", "10км", "2х", "5-й этаж",
    "Остановка «Хан Шатыр»", "Аялдамада қар тазаланбаған", "Аулада жарық жоқ",
    # казахская латиница: «joba» — «жоба» (проект), не транслит «ёба…» (найдено на корпусе llm_v1)
    "Salem qolymnıñ jobasy, Nurly tau 7-şi jaqyn", "Jobany qoldaımyn", "jobalar", "Jobağa dauys berdim", "joba",
]


@pytest.mark.parametrize("kind,text", [(k, t) for k, items in RUDE.items() for t in items])
def test_rude_words_are_found(kind, text):
    assert P.is_rude(text), text
    v = P.check(text)
    assert v.rude and v.count >= 1 and v.kinds
    assert v.masked != text


@pytest.mark.parametrize("text", CLEAN)
def test_clean_words_are_not_touched(text):
    assert not P.is_rude(text), text
    assert P.mask(text) is text           # без грубых слов — та же строка, без копии


def test_mask_keeps_first_letter_length_and_punctuation():
    text = "Опять эта блядская яма у остановки!!! Заебали, когда починят?"
    masked = P.mask(text)
    assert masked == "Опять эта б******* яма у остановки!!! З******, когда починят?"
    assert len(masked) == len(text)
    assert P.mask("х у й вам") == "х * * вам"


def test_kinds_and_count():
    v = P.check("Мрази, засрали весь двор, пиздец")
    assert v.count == 3
    assert v.kinds == ["insult", "mat", "vulgar"]
    assert [text for text in (v.masked[a:b] for a, b, _ in v.spans)] == ["М****", "з******", "п*****"]


def test_mixed_language_text():
    text = "Аулада жарық жоқ, ақымақтар! Фонари не горят, бля"
    v = P.check(text)
    assert v.count == 2 and set(v.kinds) == {"insult", "mat"}
    assert v.masked == "Аулада жарық жоқ, а********! Фонари не горят, б**"


def test_moderation_field_for_akimat():
    m = P.moderation("Уроды, когда уберёте снег")
    assert m == {"rude": True, "count": 1, "kinds": ["insult"], "version": P.VERSION}
    assert P.moderation("Когда уберёте снег")["rude"] is False
    assert P.LABEL_KEY == "moderation.rude" and set(P.LABELS) == {"ru", "kk"}


def test_non_strings_and_empty():
    assert P.mask(None) is None and P.mask(5) == 5 and P.mask("") == ""
    assert not P.is_rude(None) and not P.check(None).rude


def test_mask_json_fast_path_returns_same_object():
    body = {"items": [{"id": "c-ebab0011", "text": "Не горит фонарь", "point": [71.41, 51.09], "metoo": 3}]}
    out, n = P.mask_json(body)
    assert out is body and n == 0


def test_mask_json_masks_only_rude_strings():
    body = {"groups": [{"text": "Сука, опять яма\nбля", "people": 2, "demo": True},
                       {"text": "Яма у остановки", "people": 1}],
            "target": {"id": "osm-node-1", "label_ru": "Остановка «Нура»"}, "other": "other"}
    out, n = P.mask_json(body)
    assert n == 1
    assert out["groups"][0]["text"] == "С***, опять яма\nб**"
    assert out["groups"][1] == body["groups"][1]
    assert out["target"] == body["target"] and out["other"] == "other"
    assert body["groups"][0]["text"] == "Сука, опять яма\nбля"   # оригинал не изменён (для акимата)


def test_mask_json_sees_word_after_json_escape():
    # В сериализованном JSON перевод строки — «\n»: «\nблять» не должно читаться как слово «nблять».
    body = {"text": "Двор\nблять\tзасрали \"суки\""}
    out, n = P.mask_json(body)
    assert n == 1 and "блять" not in out["text"] and "засрали" not in out["text"] and "суки" not in out["text"]


def test_public_response_staff_sees_original():
    body = {"text": "Мрази"}
    assert P.public_response(body, staff=True) is body
    assert P.public_response(body)["text"] == "М****"


def test_mask_json_speed_on_heat_sized_payload():
    """Ответ тепловой карты на 5 000 целей: без грубых слов — быстрый путь (один проход по JSON)."""
    items = [{"target": {"kind": "object", "id": f"osm-node-{i}", "label_ru": f"Остановка «Нура-{i % 300}»",
                         "label_kk": f"«Нұра-{i % 300}» аялдамасы"},
              "geometry": {"type": "Point", "coordinates": [71.4 + i * 1e-5, 51.09]}, "weight": 1.5, "level": 2,
              "count": 3} for i in range(5000)]
    body = {"generated_at": "2026-10-11T10:00:00+05:00", "items": items}
    P.mask_json(body)                                  # прогрев кэша слов
    t0 = time.perf_counter()
    out, n = P.mask_json(body)
    elapsed = time.perf_counter() - t0
    assert out is body and n == 0
    assert elapsed < 1.0, f"{elapsed:.3f} s"            # обычно ~0.05 с; запас для загруженной машины


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from _strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _strings(value)


def _corpus():
    """Тексты репозитория, где мата нет: синтетика R02, словари R11, категории, подписи OSM."""
    texts = []
    for path in sorted(glob.glob(str(ROOT / "ml/datasets/**/*.jsonl"), recursive=True)):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                texts.extend(_strings(json.loads(line)))
            except ValueError:
                pass
    for pattern in ("web/civic/i18n/*.json", "research/round-14/categories_v2.json", "data/civic/astana/geo/*.json"):
        for path in sorted(glob.glob(str(ROOT / pattern))):
            texts.extend(_strings(json.loads(Path(path).read_text(encoding="utf-8"))))
    for path in sorted(glob.glob(str(ROOT / "data/civic/astana/osm-objects/raw/*.json.gz"))):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            texts.extend(_strings(json.load(fh)))
    return texts


def test_no_false_positives_on_repository_corpora():
    texts = _corpus()
    if len(texts) < 1000:
        pytest.skip("корпусов нет в этой ветке (ml/datasets — путь R02, есть в сборке R01)")
    hits = [t[:80] for t in texts if P.is_rude(t)]
    assert hits == [], hits[:10]
