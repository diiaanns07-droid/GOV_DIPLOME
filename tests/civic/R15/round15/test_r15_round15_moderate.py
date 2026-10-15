"""R15 раунд 15 · R04 модерация текстов сообщества (ui.civic_ml_api.moderate) — THREATS_R15 §11.

moderate(text, lang?) -> {text_public, flags, …} — единый фильтр для R16 (инициативы, «старший»), R13 (вопросы встреч),
R17 (обновления кризиса) и маршрута POST /moderate (предпросмотр). Проверяем обход, а не словарь:
- форматы телефона, ИИН (с пробелами), e-mail (в т. ч. «[at]», «собака»), карты, IBAN, квартиры, ники (T-R04-01…07);
- подпись вплотную к номеру («Тел.8701…», «ИИН-…»), номер через точки, полноширинные цифры — S48 (T-R04-01/02);
- маска целиком: в text_public нет 7+ цифр исходника; оригинала нет в остальных полях ответа (T-R04-09);
- скорость на враждебных 5000 символах (ReDoS, публичный маршрут) — T-R04-08.
Нет moderate в ui.civic_ml_api — NOT_RUN.
"""

from __future__ import annotations

import re
import time

import pytest

from r15_round15 import CARD, CARD_SPACED, IIN, dump, module, not_run, xmarks


@pytest.fixture(scope="module")
def moderate():
    fn = getattr(module("ui.civic_ml_api", "R04"), "moderate", None)
    if not callable(fn):
        not_run("в ui.civic_ml_api нет moderate (R04 раунда 15)")
    return fn


MUST_MASK = [
    ("Звоните +7 701 123 45 67 вечером", "701 123 45 67"),
    ("тел 8 (701) 123-45-67", "123-45-67"),
    ("8-701-123-45-67 Айгуль", "701-123-45-67"),
    ("87011234567", "87011234567"),
    ("701 123 45 67 после шести", "701 123 45 67"),
    ("8 7 0 1 1 2 3 4 5 6 7", "8 7 0 1 1 2 3 4 5 6 7"),
    ("WhatsApp 8(701)1234567", "1234567"),
    ("ватсап 87011234567.", "87011234567"),
    (f"ИИН {IIN}", IIN),
    (f"ИИН {IIN[:6]} {IIN[6:9]} {IIN[9:]}", f"{IIN[:6]} {IIN[6:9]} {IIN[9:]}"),
    ("пишите a.k.r15@mail.kz", "a.k.r15@mail.kz"),
    ("пишите a.k.r15 [at] mail.kz", "a.k.r15"),
    ("a.k.r15 собака mail.ru", "a.k.r15"),
    (f"скинемся на карту {CARD_SPACED}", CARD_SPACED),
    (f"карта {CARD}", CARD),
    ("KZ86125KZT5004100100 — счёт для сбора", "KZ86125KZT5004100100"),
    ("заходите, кв. 45", "кв. 45"),
    ("пәтер 12, үшінші қабат", "пәтер 12"),
    ("Telegram @aigul_r15", "@aigul_r15"),
    ("пишите t.me/aigul_r15", "t.me/aigul_r15"),
]
S48_BYPASS = [
    ("Тел.87011234567 — Айгуль", "87011234567"),
    (f"ИИН-{IIN}", IIN),
    (f"ИИН.{IIN}", IIN),
    ("8.701.123.45.67 после шести", "8.701.123.45.67"),
    ("８７０１１２３４５６７", "８７０１１２３４５６７"),
]
RUDE = ["Сука, опять яма у подъезда", "cyka блин", "xуй", "бл@ть", "б л я т ь"]


@pytest.mark.parametrize("text,secret", MUST_MASK, ids=[t for t, _s in MUST_MASK])
def test_personal_data_is_masked(moderate, text, secret):
    """T-R04-01…07: личные данные скрыты в text_public и помечены для сотрудника."""
    result = moderate(text)
    assert secret not in result["text_public"], result["text_public"]
    assert result["flags"], result


@pytest.mark.parametrize("text,secret", [pytest.param(t, s, marks=xmarks("S48")) for t, s in S48_BYPASS],
                         ids=[t for t, _s in S48_BYPASS])
def test_label_glued_dotted_and_fullwidth_numbers(moderate, text, secret):
    """S48: «Тел.8701…», «ИИН-…» (подпись вплотную), «8.701.123.45.67», полноширинные цифры — тоже скрыты."""
    assert secret not in moderate(text)["text_public"]


@pytest.mark.parametrize("text", RUDE)
def test_rude_words_flagged_with_homoglyphs(moderate, text):
    """T-R04-06: мат латиницей/вперемешку, через пробелы и символы — маска и пометка rude."""
    result = moderate(text)
    assert result["text_public"] != text and any((f.get("kind") if isinstance(f, dict) else f) == "rude"
                                                for f in result["flags"]), result


@pytest.mark.parametrize("text,secret", MUST_MASK[:6] + MUST_MASK[8:10], ids=[t for t, _s in MUST_MASK[:6] + MUST_MASK[8:10]])
def test_mask_is_whole_and_original_not_echoed(moderate, text, secret):
    """T-R04-09: маска целиком (в публичном тексте нет 7+ цифр подряд из исходника); вне text_public исходника нет."""
    result = moderate(text)
    digits = re.sub(r"\D", "", secret)
    public_digits = re.sub(r"\D", "", result["text_public"])
    assert len(digits) < 7 or not any(digits[i:i + 7] in public_digits for i in range(len(digits) - 6))
    rest = {k: v for k, v in result.items() if k != "text_public"}
    assert secret not in dump(rest), rest


@pytest.mark.parametrize("name,text", [("letters", "a" * 5000), ("digit-space", "8 " * 2500), ("at", "@" * 5000),
                                       ("a@", "a@" * 2500), ("kv", "кв " * 1600), ("dashes", "1-" * 2500),
                                       ("brackets", "(" * 5000), ("dots", "a." * 2500), ("at-words", "x at " * 1000),
                                       ("digits", "7" * 5000), ("mixed", "1 (2 " * 1000)])
def test_moderate_is_fast_on_hostile_text(moderate, name, text):
    """T-R04-08: публичный предпросмотр не «вешается» на враждебных 5000 символах (цель R04 — 5 мс на текст)."""
    started = time.perf_counter()
    moderate(text[:5000])
    assert (time.perf_counter() - started) < 0.2, name


def test_non_string_and_too_long_are_rejected(moderate):
    """P7: не строка и длиннее предела — ValueError (шлюз отвечает 400), а не 500."""
    for bad in (["8 701 123 45 67"], {"text": 1}, 42, "а" * 20000):
        with pytest.raises(ValueError):
            moderate(bad)
