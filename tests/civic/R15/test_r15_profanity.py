"""R15: фильтр мата и оскорблений (волна 1 п. 8, владелец R04; включение во все ответы API — R01).

- Скорость: на 5000 символов худшего вида (разрядка, повторы, смесь алфавитов) — миллисекунды, без катастрофического
  перебора регулярных выражений (отказ в обслуживании через «Вопрос акиму», тексты, подписи).
- Сотрудник видит оригинал; остальным — звёздочки.
- S26: фильтр в шлюзе R01 обходит ВСЕ строки ответа — и машинные: base64 фото, CSRF-токен входа, номер квитанции,
  id устройства. В случайных символах «грубое» латинское сочетание попадается часто: фото ломается (13 из 20 по 300 КБ),
  токен входа — примерно один из 7000.
"""

from __future__ import annotations

import time

import pytest

from r15_common import need_module, xfail


@pytest.fixture()
def P():
    return need_module("ui.civic_ml_api.profanity")


# Настоящие случайные строки, на которых фильтр ставил звёздочки (найдены перебором secrets/os.urandom).
CSRF = "xUjDQqfJhvZvGxiHUuRsnvpZlKp-OYipB3say7-RMsQ"
RECEIPT = "EBaHJGTXiDLOllOEdJYQZTiv"
DEVICE = "d-xYETxWaPVXDiaGxApShaFmQY"
DATA_URL = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD" + "htPN+AAxueakg+ZE" + "AAAA"


@xfail("S26")
def test_machine_strings_are_not_masked(P):
    body = {"ok": True, "data": {"csrf_token": CSRF, "receipt": RECEIPT, "device_id": DEVICE,
                                 "photo": {"id": "p-0123456789abcdef", "mime": "image/jpeg", "data_url": DATA_URL}}}
    out, _changed = P.mask_json(body)
    assert out["data"]["csrf_token"] == CSRF
    assert out["data"]["receipt"] == RECEIPT
    assert out["data"]["device_id"] == DEVICE
    assert out["data"]["photo"]["data_url"] == DATA_URL


@pytest.mark.parametrize("text", ["na_huy_vse_pizdets_tut", "Nahuyvsepizdetsvsem", "https:// сука, опять яма"])
def test_people_text_that_looks_like_a_token_is_still_masked(P, text):
    """Обратная сторона S26: машинные строки узнаются по ключу, а не по виду. Правило «длинное латинское слово /
    начинается с http — не текст» (первая версия P-R04-2) пропускало бы мат в подписи идеи или вопросе акиму."""
    body = {"items": [{"title": text, "question": text}]}
    out = P.public_response(body)["items"][0]
    assert out["title"] != text and out["question"] != text, out
    assert P.is_rude(text) and P.moderation(text)["rude"]


def test_rude_human_text_is_masked_for_public_but_not_for_staff(P):
    body = {"items": [{"text": "Сука, опять яма", "label_ru": "Остановка «Нура»"}]}
    public = P.public_response(body)
    assert "Сука" not in public["items"][0]["text"] and public["items"][0]["label_ru"] == "Остановка «Нура»"
    assert P.public_response(body, staff=True) is body
    assert body["items"][0]["text"] == "Сука, опять яма"        # оригинал не изменён


def test_mask_output_is_plain_text(P):
    out = P.mask('<img src=x onerror="alert(1)"> сука')
    assert "<img src=x" in out                                    # фильтр не экранирует и не добавляет HTML
    assert "<" not in out.replace('<img src=x onerror="alert(1)">', "")


WORST = {
    "разрядка с хвостом": "а " * 2499 + "аа",
    "точки": "х." * 2499 + "уу",
    "повторы": "хууууууу" * 625,
    "цифры": "1" * 5000,
    "латиница с символами": "x@3 " * 1250,
    "эмодзи": "😀" * 5000,
}


@pytest.mark.parametrize("name", sorted(WORST))
def test_filter_is_fast_on_worst_inputs(P, name):
    text = WORST[name]
    started = time.perf_counter()
    P.check(text)
    P.mask(text)
    assert time.perf_counter() - started < 0.5, name             # на ноутбуке ~10 мс; 0,5 с — запас для слабой машины
