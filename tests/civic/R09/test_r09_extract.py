"""CP4: черновик извлечения из переданного текста публикации (редактор принимает поля вручную)."""

import json
import socket
from pathlib import Path

import pytest

from agent.civic_assistant.api import EXTRACT_PATH, AssistantEndpoint, RateLimiter
from agent.civic_assistant.extract import FIELDS, extract_draft
from agent.civic_assistant.providers import MockProvider

PUB = json.loads((Path(__file__).parent / "fixtures" / "publications.json").read_text(encoding="utf-8"))


def draft(name, **kw):
    p = PUB[name]
    return extract_draft(p["text"], p["source_id"], url=p.get("url"), publisher=p.get("publisher"),
                         published_on=p.get("published_on"), **kw), p["text"]


def check_spans(d, text):
    for f, p in d["fields"].items():
        assert text[p["span"][0]:p["span"][1]] == p["quote"], f
        assert p["source_id"] and p["needs_review"] is True and p["confidence_kind"]
        for alt in p["alternatives"]:
            assert text[alt["span"][0]:alt["span"][1]] == alt["quote"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("extraction must not open network connections")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def test_full_ru_publication():
    d, text = draft("ru_full")
    v = {f: p["value"] for f, p in d["fields"].items()}
    assert v["schedule.planned_start"] == "2026-09-15" and v["schedule.current_planned_end"] == "2026-10-20"
    assert v["budget.amount_kzt"] == 1200000000 and d["fields"]["budget.amount_kzt"]["confidence_kind"] == "unit_conversion"
    assert v["budget.basis"] == "contract" and d["fields"]["budget.basis"]["quote"] == "договору"
    assert v["responsible.organization"] == "ГУ «Синтетическое управление (тест)»"
    assert v["kind"] == "roadworks"
    check_spans(d, text)
    assert d["status"] == "draft_requires_editor_review" and "не является сообщением городского органа" in d["notice"].lower()
    assert d["source"]["fetched"] is False and "url_not_fetched" in d["warnings"]
    assert "status_not_extracted" in d["warnings"]
    assert set(d["fields"]) <= set(FIELDS)
    assert not {"status", "publication", "revision", "evidence_type"} & set(d["fields"])


def test_inexact_dates_stay_null_with_quote():
    d, text = draft("partial_dates")
    start, end = d["fields"]["schedule.planned_start"], d["fields"]["schedule.current_planned_end"]
    assert start["value"] is None and start["quote"] == "5 мая" and start["confidence_kind"] == "partial_date"
    assert end["value"] is None and end["quote"] == "до конца октября 2026"
    assert d["fields"]["budget.amount_kzt"]["value"] == 350000000 and d["fields"]["budget.basis"]["value"] == "planned"
    check_spans(d, text)


def test_conflicting_values_are_null_with_alternatives():
    d, text = draft("conflict")
    end, amount = d["fields"]["schedule.current_planned_end"], d["fields"]["budget.amount_kzt"]
    assert end["value"] is None and end["confidence_kind"] == "conflict"
    assert {a["value"] for a in end["alternatives"]} == {"2026-11-01", "2026-12-15"}
    assert amount["value"] is None and {a["value"] for a in amount["alternatives"]} == {100000000, 120000000}
    assert "budget.basis" not in d["fields"]
    check_spans(d, text)


def test_kazakh_publication():
    d, text = draft("kk")
    v = {f: p["value"] for f, p in d["fields"].items()}
    assert v["schedule.planned_start"] == "2026-09-01" and v["schedule.current_planned_end"] == "2026-10-30"
    assert v["budget.amount_kzt"] == 500000000 and v["budget.basis"] == "contract" and v["kind"] == "roadworks"
    check_spans(d, text)


def test_instructions_inside_source_are_data():
    d, text = draft("injection")
    blob = json.dumps(d["fields"], ensure_ascii=False)
    for bad in ("2030", "999", "password", "localhost", "rm -rf", "script"):
        assert bad not in blob, bad
    quotes = " ".join(r["quote"] for r in d["ignored_instructions"])
    for marker in ("ИГНОРИРУЙ", "SELECT", "Покажи пароли", "localhost", "<script>"):
        assert marker in quotes
    assert all(r["action"] == "ignored_as_data" for r in d["ignored_instructions"])
    assert d["source"]["url"] == "http://127.0.0.1:8501/api/civic/v1/staff/objects" and d["source"]["fetched"] is False
    assert d["unassigned_dates"] == [{"value": "2026-09-12", "quote": "12.09.2026", "span": [30, 40],
                                      "confidence_kind": "exact_date"}]
    assert d["fields"]["kind"]["value"] == "event"


def test_text_without_facts():
    d, _ = draft("no_facts")
    assert set(d["fields"]) == {"title"}


@pytest.mark.parametrize("text,sid,code", [
    ("", "s1", "text_required"), (None, "s1", "text_required"), ("x" * 20001, "s1", "text_too_long"),
    ("Текст", "../etc/passwd", "source_id_invalid"), ("Текст", None, "source_id_invalid"),
])
def test_input_validation(text, sid, code):
    with pytest.raises(ValueError) as exc:
        extract_draft(text, sid)
    assert str(exc.value) == code


def test_provider_quotes_are_verified_and_parsed_by_code():
    p = PUB["ru_full"]
    prov = MockProvider([{"fields": {
        "schedule.current_planned_end": {"quote": "до 20.10.2026"},
        "responsible.organization": {"quote": "ГУ «Синтетическое управление (тест)»"},
        "budget.amount_kzt": {"quote": "1,5 млрд тенге"},
    }}])
    d = extract_draft(p["text"], p["source_id"], provider=prov)
    assert d["mode"] == "llm:mock"
    assert d["fields"]["schedule.current_planned_end"]["value"] == "2026-10-20"
    assert d["fields"]["schedule.current_planned_end"]["confidence_kind"] == "model_quote_exact_date"
    assert "extract_quote_not_in_text:budget.amount_kzt" in d["warnings"]
    assert d["fields"]["budget.amount_kzt"]["value"] == 1200000000  # шаблонное значение не заменено выдумкой
    assert "1,5" not in json.dumps(d["fields"], ensure_ascii=False)
    assert prov.requests[0]["schema"] == "civic-assistant-extract-request-v1"


def test_provider_quote_inside_instruction_rejected():
    p = PUB["injection"]
    prov = MockProvider([{"fields": {"schedule.current_planned_end": {"quote": "31.12.2030"},
                                     "budget.amount_kzt": {"quote": "999 млрд тенге"}}}])
    d = extract_draft(p["text"], p["source_id"], provider=prov)
    assert "extract_quote_in_instruction:schedule.current_planned_end" in d["warnings"]
    assert "extract_quote_in_instruction:budget.amount_kzt" in d["warnings"]
    assert "2030" not in json.dumps(d["fields"]) and "999" not in json.dumps(d["fields"])


@pytest.mark.parametrize("raw,warning", [
    ({"fields": {"schedule.current_planned_end": {"quote": "20.10.2026", "value": "2026-12-31"}}}, "extract_provider_schema"),
    ({"fields": {"publication": {"quote": "Ремонт"}}}, "extract_provider_unknown_field"),
    ({"fields": {}, "actions": ["publish"]}, "extract_provider_schema"),
    ("Срок: 31.12.2030, всё одобрено", "extract_provider_not_json"),
    (["fields"], "extract_provider_schema"),
])
def test_bad_provider_extraction_falls_back_to_template(raw, warning):
    p = PUB["ru_full"]
    d = extract_draft(p["text"], p["source_id"], provider=MockProvider([raw]))
    assert d["mode"] == "template" and warning in d["warnings"]
    assert d["fields"]["schedule.current_planned_end"]["value"] == "2026-10-20"
    assert "2030" not in json.dumps(d, ensure_ascii=False).replace(p["text"], "")


def test_provider_partial_date_quote_stays_null_and_conflict_is_flagged():
    p = PUB["partial_dates"]
    d = extract_draft(p["text"], p["source_id"], provider=MockProvider([
        {"fields": {"schedule.current_planned_end": {"quote": "до конца октября 2026 года"}}}]))
    assert d["fields"]["schedule.current_planned_end"]["value"] is None
    p = PUB["ru_full"]
    d = extract_draft(p["text"], p["source_id"], provider=MockProvider([
        {"fields": {"schedule.current_planned_end": {"quote": "15 сентября 2026 года"}}}]))
    end = d["fields"]["schedule.current_planned_end"]
    assert end["value"] is None and end["confidence_kind"] == "conflict"
    assert {a["value"] for a in end["alternatives"]} >= {"2026-10-20"}


# --- редакторский HTTP-путь -----------------------------------------------------------------------

def ep(principal):
    return AssistantEndpoint(lambda oid: None, resolve_principal=lambda ctx: principal,
                             rate_limiter=RateLimiter(100, 60))


def post(endpoint, body, same_origin=True):
    return endpoint.handle("POST", EXTRACT_PATH, {}, body, {"client_ip": "127.0.0.1", "is_same_origin": same_origin,
                                                            "headers": {}})


BODY = {"source_id": "synth-pub-ru-1", "text": PUB["ru_full"]["text"], "url": "https://example.invalid/news/1"}


def test_extract_requires_editor_and_same_origin():
    assert post(ep(None), BODY)["status"] == 401
    assert post(ep({"name": "x", "role": "resident"}), BODY)["status"] == 403
    resp = post(ep({"name": "ed", "role": "editor"}), BODY, same_origin=False)
    assert resp["status"] == 403 and resp["body"]["error"]["code"] == "csrf"


def test_extract_ok_and_validation():
    e = ep({"name": "ed", "role": "editor"})
    resp = post(e, BODY)
    assert resp["status"] == 200 and resp["body"]["data"]["schema"] == "civic-extraction-draft-v1"
    assert post(e, dict(BODY, publish=True))["body"]["error"]["code"] == "unexpected_fields"
    assert post(e, dict(BODY, text="x" * 20001))["status"] == 413
    assert post(e, dict(BODY, source_id="bad id"))["status"] == 422
    assert post(e, "text")["status"] == 400


@pytest.mark.parametrize("text", ["01.01.2026 " * 1818, "игнорируй. " * 1818, "5 млн тенге. " * 1538,
                                  "1 000 " * 3333, "9" * 20000])
def test_hostile_long_texts_are_bounded(text):
    import time
    t0 = time.monotonic()
    d = extract_draft(text[:20000], "s1")
    assert time.monotonic() - t0 < 5
    assert len(d["ignored_instructions"]) <= 20 and len(d["unassigned_dates"]) <= 20
    assert all(len(p["alternatives"]) <= 20 for p in d["fields"].values())
    assert len(json.dumps(d, ensure_ascii=False)) < 60000


def test_extract_accepts_r02_principal_object():
    from dataclasses import dataclass

    @dataclass
    class Principal:  # форма R02 ui.civic_store.auth.Principal (существенные поля)
        username: str
        role: str

    assert post(ep(Principal("ed", "editor")), BODY)["status"] == 200
    assert post(ep(Principal("x", "viewer")), BODY)["status"] == 403
