"""R04 раунд 15: moderate() — мат, телефоны, ИИН, e-mail, карты до публикации (CONTRACT §10). Без сети."""

from __future__ import annotations

import glob
import json
import time
from pathlib import Path

import pytest

from ui.civic_ml_api import moderate, moderation_record, public_text
from ui.civic_ml_api.moderation import iin_checksum_ok, luhn_ok

ROOT = Path(__file__).resolve().parents[4]


def synthetic_iin(prefix11: str) -> str:
    """ИИН с правильной контрольной цифрой для заданных 11 цифр (в тестах номер собирается на лету)."""
    for k in range(10):
        if iin_checksum_ok(prefix11 + str(k)):
            return prefix11 + str(k)
    raise AssertionError("для этого префикса контрольной цифры нет")


def luhn_card(prefix15: str) -> str:
    """Номер карты с правильной контрольной цифрой Луна (синтетический, собирается в тесте)."""
    for k in range(10):
        if luhn_ok(prefix15 + str(k)):
            return prefix15 + str(k)
    raise AssertionError


def kinds(result):
    return {f["kind"]: f["count"] for f in result["flags"]}


@pytest.mark.parametrize("text, public", [
    ("Звоните 8 701 123 45 67", "Звоните ***"),
    ("Звоните +7 (701) 123-45-67", "Звоните ***"),
    ("Звоните 87011234567", "Звоните ***"),
    ("Звоните +77011234567, Айгуль", "Звоните ***, Айгуль"),
    ("Звоните 701 123 45 67", "Звоните ***"),
    ("Звоните:8-701-123-45-67", "Звоните:***"),
    ("Городской 8 (7172) 21-34-56", "Городской ***"),
    ("Городской 21-34-56", "Городской ***"),
    ("Тел. 8 701 123 45 67", "Тел. ***"),
    ("Телефон: 8 707 555 12 34, келіңіздер", "Телефон: ***, келіңіздер"),
])
def test_phones(text, public):
    res = moderate(text)
    assert res["text_public"] == public
    assert kinds(res) == {"phone": 1} and res["action"] == "review" and res["pii"] is True


@pytest.mark.parametrize("text, public, kind", [
    ("Тел.87011234567 — Айгуль", "Тел.*** — Айгуль", "phone"),       # R15-S48: подпись вплотную через точку
    ("тел:87011234567", "тел:***", "phone"),
    ("моб-8 701 123 45 67", "моб-***", "phone"),                      # подпись через дефис — номер целиком
    ("ИИН-900101300126", "ИИН-***", "iin"),
    ("ИИН.900101300126", "ИИН.***", "iin"),
    ("8.701.123.45.67 после шести", "*** после шести", "phone"),      # мобильный через точки
    ("８７０１１２３４５６７", "***", "phone"),                          # полноширинные цифры
])
def test_r15_s48_glued_dotted_fullwidth(text, public, kind):
    res = moderate(text)
    assert res["text_public"] == public and kinds(res) == {kind: 1}


def test_iin_with_checksum_and_other_long_numbers():
    iin = synthetic_iin("95010130012")
    res = moderate(f"Мой ИИН {iin}, помогите")
    assert res["text_public"] == "Мой ИИН ***, помогите" and kinds(res) == {"iin": 1}
    assert res["flags"][0]["checksum_ok"] == 1
    bad = iin[:-1] + str((int(iin[-1]) + 1) % 10)
    res = moderate(f"Номер {bad}")                     # опечатка в контрольной цифре — всё равно ИИН (R16, R17)
    assert res["text_public"] == "Номер ***" and kinds(res) == {"iin": 1} and res["flags"][0]["checksum_ok"] == 0
    # Как в тесте R16 (test_personal_data_is_flagged_and_masked_for_public): телефон, e-mail и ИИН — три вида.
    res = moderate("Звоните +7 701 123-45-67 или пишите a.b@example.com, ИИН 900101300123")
    assert set(kinds(res)) == {"phone", "email", "iin"} and "900101300123" not in res["text_public"]


def test_cards_iban_email_apartment_contacts():
    card = luhn_card("440043012345678")
    assert luhn_ok(card) and not luhn_ok(card[:-1] + str((int(card[-1]) + 1) % 10))
    grouped = " ".join(card[i:i + 4] for i in range(0, 16, 4))
    assert kinds(moderate(f"Карта {grouped}")) == {"card": 1}
    res = moderate(f"Карта {card}")
    assert kinds(res) == {"card": 1} and res["flags"][0]["luhn_ok"] == 1
    res = moderate("Карта " + card[:-1] + str((int(card[-1]) + 1) % 10))
    assert kinds(res) == {"card": 1} and res["flags"][0]["luhn_ok"] == 0
    assert kinds(moderate("Счёт KZ86 125K ZT50 0410 0100")) == {"iban": 1}
    res = moderate("Почта aigul.k@mail.ru, aigul собака mail.ru, aigul (at) gmail (dot) com")
    assert res["text_public"] == "Почта ***, ***, ***" and kinds(res) == {"email": 3}
    res = moderate("Живу в кв. 45, квартира 12, 45-пәтер")
    assert res["text_public"] == "Живу в кв. ***, квартира ***, ***-пәтер" and kinds(res) == {"apartment": 3}
    res = moderate("Пишите в телеграм @aigul_88 или t.me/aigul88")
    assert res["text_public"] == "Пишите в телеграм *** или ***" and kinds(res) == {"contact": 2}


def test_rude_words_masked_like_gateway_and_combined_with_pii():
    res = moderate("Опять эта блядская яма, звоните 8-701-123-45-67")
    assert res["text_public"] == "Опять эта б******* яма, звоните ***"
    assert kinds(res) == {"phone": 1, "rude": 1} and res["rude"] and res["pii"]
    assert moderate("Сосед — дебил")["text_public"] == "Сосед — д****"


@pytest.mark.parametrize("text", [
    "Субботник в субботу, 10:00, у дома 15. Берите перчатки и мешки.",
    "Встреча 12.10.2026 в 18:30, собрали 1 000 000 тенге, индекс 010000",
    "Сенбілік сенбіде, сағат 10:00-де, 15-үйдің жанында",
    "osm-node-7127598060 и cand-r12-13-07-2026-10-40-16251",
    "programme 2025-2029 (2025-2026 tranche)",
    "Посадили 6 саженцев, пришли 15 соседей, 2 мешка мусора",
    "дома 15 17 18 по улице Кенесары",
    "Встреча 12.10.2026 в 10.00, т.е. после работы",                  # R15-S48: даты с точками — не телефон
    "Позор, бездельники, когда отремонтируете? Безобразие!",
    "",
])
def test_no_false_positives(text):
    res = moderate(text)
    assert res["clean"] is True and res["text_public"] == text and res["action"] == "publish"


def test_no_pii_flags_on_r02_corpora_and_r11_dictionaries():
    texts = []
    for path in ("ml/datasets/synth_v3/data/corpus_v3.jsonl", "ml/datasets/probe_v2/probe_v2.jsonl",
                 "ml/datasets/v1_in_v2/corpus_v1_in_v2.jsonl"):
        full = ROOT / path
        if full.exists():
            texts += [json.loads(line)["text"] for line in full.read_text(encoding="utf-8").splitlines() if line]

    def walk(obj):
        if isinstance(obj, str):
            texts.append(obj)
        elif isinstance(obj, dict):
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    for path in glob.glob(str(ROOT / "web/civic/i18n/*.json")):
        walk(json.loads(Path(path).read_text(encoding="utf-8")))
    assert len(texts) > 3000
    flagged = [(t, kinds(r)) for t in texts for r in [moderate(t[:5000])] if r["pii"]]
    assert flagged == []


def test_response_has_no_original_and_record_has_no_values():
    res = moderate("Звоните 8 701 123 45 67")
    assert "text" not in res and "8 701" not in json.dumps(res, ensure_ascii=False)
    rec = moderation_record(res)
    assert rec == {"rude": False, "pii": True, "kinds": ["phone"], "count": 1, "version": rec["version"]}
    assert public_text("Звоните 8 701 123 45 67") == "Звоните ***"
    assert public_text(None) is None


def test_body_and_validation():
    assert moderate(body={"text": "Звоните 87011234567", "lang": "kk"})["hint_kk"].startswith("Жеке деректер")
    for bad in ({"text": 5}, {"text": "x" * 5001}, {"text": "ok", "lang": "en"}):
        with pytest.raises(ValueError):
            moderate(**bad)


def test_speed_under_5ms():
    texts = ["Субботник в субботу, звоните 8 701 123 45 67, aigul@mail.ru, кв. 45, опять эта блядская яма " * 3,
             "Аулада жарық жоқ, балалар алаңы бұзылған. Телефон: 8 707 555 12 34"] * 200
    moderate("прогрев")
    times = []
    for text in texts:
        t0 = time.perf_counter()
        moderate(text)
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    assert times[int(0.95 * (len(times) - 1))] < 5
