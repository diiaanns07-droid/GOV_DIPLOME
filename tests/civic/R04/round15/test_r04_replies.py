"""R04 раунд 15: reply_draft() — черновик ответа жителю ru / kk (CONTRACT §7 POST /reply-draft, сотрудник)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

import ui.civic_ml_api as api
from ml.civic_replies import draft
from ml.civic_replies.guard import check as guard_check
from ml.civic_replies.templates import BUREAUCRATESE
from ui.civic_ml_api import reply_draft
from ui.civic_ml_api.errors import MLServiceUnavailable

TZ = timezone(timedelta(hours=5))
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=TZ)
REC = {"id": "c-abc1234", "code": "B-0042", "category": "roads", "subtopic": "pothole", "status": "new",
       "created_at": "2026-10-15T10:00:00+05:00", "due_at": "2026-10-29T10:00:00+05:00", "metoo": 3,
       "passport": {}, "lang": "ru", "text": "Личный текст жителя с телефоном 87011234567"}


@pytest.fixture(autouse=True)
def no_store():
    api.set_complaint_source(None)
    yield
    api.set_complaint_source(None)


def numbers(text):
    return set(re.findall(r"\d+", text))


@pytest.mark.parametrize("status", ["new", "accepted", "in_progress", "fixed", "rejected"])
def test_every_status_both_languages_plain_and_factual(status):
    res = reply_draft(record=REC, status=status, now=NOW)
    for text in (res["draft_ru"], res["draft_kk"]):
        assert text and "{" not in text and "  " not in text and text.endswith((".", "!"))
        assert not any(phrase in text.casefold() for phrase in BUREAUCRATESE)
        assert "Личный текст" not in text and "87011234567" not in text
        # Числа — только из записи: номер (0042), день срока (29), рабочие дни до срока.
        allowed = {"0042", "29"} | ({str(res["facts"]["response_days_left"])}
                                    if res["facts"]["response_days_left"] else set())
        assert numbers(text) <= allowed, (text, numbers(text) - allowed)
    assert res["draft_ru"].startswith("Здравствуйте!") and res["draft_kk"].startswith("Сәлеметсіз бе!")
    assert res["status"] == status and res["version"].startswith("r04-replies-")


def test_new_mentions_service_and_response_deadline_in_working_days():
    res = reply_draft(record=REC, status="new", now=NOW)
    assert "Дорожная служба" in res["draft_ru"] and "Жол қызметі" in res["draft_kk"]
    assert "рабочих дней — до 29 октября" in res["draft_ru"]
    assert "жұмыс күні ішінде" in res["draft_kk"] and "29 қазан" in res["draft_kk"]
    assert "response_due" in res["facts_used"]


def test_no_promised_dates_without_passport():
    res = reply_draft(record=dict(REC, status="in_progress"), now=NOW)
    assert "сообщим, как только служба его определит" in res["draft_ru"]
    assert any("дату не обещаем" in w for w in res["warnings"])
    rec = dict(REC, status="in_progress", passport={"fix_eta": "2026-10-22", "next_step": "Заделаем яму"})
    res = reply_draft(record=rec, now=NOW)
    assert "22 октября" in res["draft_ru"] and "22 қазан" in res["draft_kk"]
    assert "Следующий шаг: заделаем яму." in res["draft_ru"]
    assert any("по-русски" in w for w in res["warnings"])        # шаг сотрудника — перевести для kk


def test_joint_parts_and_handoff_keep_deadline():
    rec = dict(REC, status="in_progress",
               services=[{"service": "water", "role": "lead", "status": "done"},
                         {"service": "road", "role": "partner", "status": "in_progress"}])
    res = reply_draft(record=rec, now=NOW)
    assert "работают 2 службы: Водоканал — сделано, Дорожная служба — в работе" in res["draft_ru"]
    assert "екі қызмет жұмыс істейді: Сумен жабдықтау қызметі — орындалды, Жол қызметі — жұмыста" in res["draft_kk"]
    rec = dict(REC, status="accepted", handoffs=[{"at": "2026-10-15T11:00:00+05:00", "from": "road", "to": "water",
                                                  "reason": "внутренняя причина сотрудника"}])
    res = reply_draft(record=rec, now=NOW)
    assert "Срок ответа не меняется — до 29 октября" in res["draft_ru"]
    assert "внутренняя причина" not in res["draft_ru"] + res["draft_kk"]


def test_fixed_rejected_duplicate():
    rec = dict(REC, status="fixed", resolution={"what_done": "Заасфальтировали яму"})
    res = reply_draft(record=rec, now=NOW)
    assert "устранили: заасфальтировали яму" in res["draft_ru"] and "«Не исправлено»" in res["draft_ru"]
    res = reply_draft(record=dict(REC, status="rejected"), now=NOW)
    assert res["needs_input"] == ["reason"] and "[причина — допишите]" in res["draft_ru"]
    assert "[себебін жазыңыз]" in res["draft_kk"]
    res = draft(dict(REC, duplicate_of="c-orig123"), names={}, now=NOW, original_code="B-0007")
    assert "B-0007" in res["draft_ru"] and "B-0007" in res["draft_kk"] and res["template"] == "duplicate"


def test_text_only_draft_uses_route():
    res = reply_draft(text="Яма после раскопок водоканала", status="new", lang="kk")
    assert "передали двум службам: Водоканал и Дорожная служба" in res["draft_ru"]
    assert res["text"] == res["draft_kk"] and res["lang"] == "kk"
    assert not numbers(res["draft_ru"]) and not numbers(res["draft_kk"])


def test_llm_guard_rejects_new_facts_and_accepts_rephrase():
    tpl = reply_draft(record=REC, status="new", now=NOW)["draft_ru"]
    assert guard_check(tpl, tpl.replace("29 октября", "1 ноября")) is not None
    assert guard_check(tpl, tpl + " Починим за три дня.") is not None
    assert guard_check(tpl, tpl.replace("Дорожная служба", "Водоканал"), ["Водоканал", "Дорожная служба"]) is not None
    res = reply_draft(record=REC, status="new", now=NOW, polish=lambda text, lang: text.replace("Здравствуйте!", "Добрый день!"))
    assert res["source"] == "template+llm" and res["draft_ru"].startswith("Добрый день!")
    res = reply_draft(record=REC, status="new", now=NOW, polish=lambda text, lang: text + " Сделаем за 2 дня.")
    assert res["source"] == "template" and any("добавила числа" in w for w in res["warnings"])

    def broken(text, lang):
        raise TimeoutError

    assert reply_draft(record=REC, status="new", now=NOW, polish=broken)["source"] == "template"


def test_store_lookup_errors_and_staff_only(tmp_path):
    with pytest.raises(MLServiceUnavailable):
        reply_draft(complaint_id="c-abc1234")
    with pytest.raises(ValueError):
        reply_draft(complaint_id="../etc")
    with pytest.raises(ValueError):
        reply_draft()
    with pytest.raises(PermissionError):
        reply_draft(body={"text": "Яма"}, context={"headers": {}}, principal=None)

    from ui.civic_feedback.v2.store import ComplaintStore
    store = ComplaintStore(tmp_path / "c.sqlite3")
    rec, _ = store.create({"text": "Яма после раскопок водоканала, не закопали", "category": "roads",
                           "subtopic": "pothole", "point": [71.4065, 51.1311], "district": "nura"},
                          "device-test-000000001")
    api.connect_store(store, warm=False)
    res = reply_draft(body={"complaint_id": rec["id"], "lang": "kk"}, principal={"username": "op", "role": "editor"},
                      context={"headers": {}})
    assert res["facts"]["code"] == rec["code"] and rec["code"] in res["draft_kk"] and res["lang"] == "kk"
    assert "Жол қызметі" in res["draft_kk"]
    assert reply_draft(code=rec["code"])["facts"]["code"] == rec["code"]
    with pytest.raises(LookupError):
        reply_draft(complaint_id="c-nothere1")
