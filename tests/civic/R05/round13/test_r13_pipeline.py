"""R05 раунд 13: candidate -> evidence attached -> review -> draft package на синтетических данных.

Каждая проверка — реальный риск: повышение статуса по сниппету/имени файла, устаревшее объявление как
действующее, неизвестное как ноль, правка после проверки, публикация без сотрудника.
"""

import json
import shutil

import pytest

from r13_helpers import attach_a, evidence_form_a, review, review_form_for, run, write


def states(tool):
    code, out = run(tool, "status")
    assert code == 0
    return {row["slug"]: row["state"] for row in out}


def test_full_transition_builds_one_draft_with_sources(tool, home):
    assert states(tool) == {"test-almaty-closure": "candidate", "test-programme": "candidate"}
    code, out = attach_a(tool, home)
    assert code == 0, out
    assert out["state"] == "evidence_attached"
    ev = json.loads((home["root"] / "evidence/test-almaty-closure/src-r12-test-almaty-a.json").read_text("utf-8"))
    assert ev["capture"]["storage"] == "outside_repo" and len(ev["capture"]["content_sha256"]) == 64
    assert all(s["context"] for s in ev["snapshot"]) and "999 000 000" not in json.dumps(ev, ensure_ascii=False)
    code, out = review(tool, home, review_form_for(tool, "test-almaty-closure"))
    assert code == 0, out
    assert out["state"] == "draft_ready"
    code, out = run(tool, "build")
    assert code == 0 and out["problems"] == []
    pkg = json.loads((home["root"] / "package.civic-v1.json").read_text("utf-8"))
    assert pkg["slice"]["demo"] is False and pkg["slice"]["source"] == "r05-astana-r13-verified"
    [item] = pkg["items"]
    assert item["id"] == "ast-r05-roadworks-test-almaty-closure"
    assert item["publication"] == "draft"                       # импорт не публикует
    assert item["status"] == "unknown"                          # статус в источнике не назван
    assert item["schedule"] == {"planned_start": "2026-07-20", "original_planned_end": None,
                                "current_planned_end": "2026-12-31", "actual_end": None}
    assert item["budget"]["amount_kzt"] is None                 # неизвестное ≠ 0
    assert item["evidence_type"] == "derived"                   # «до конца года» -> дата
    assert item["geometry"]["type"] == "LineString" and item["geometry_precision"] == "approximate"
    assert "street_segment" in item["evidence_notes"] and "до конца 2026 года" in item["evidence_notes"]
    [ref] = item["source_refs"]
    assert ref["access_status"] == "fetched" and ref["published_on"] == "2026-07-18"
    assert set(ref["fields"]) == {"schedule.planned_start", "schedule.current_planned_end", "responsible.organization"}
    summary = json.loads((home["root"] / "summary.json").read_text("utf-8"))
    assert summary["verified_current"] == 1 and summary["verified_historical"] == 0
    assert summary["fetched_sources"] == 1 and summary["states"]["candidate"] == 1
    first = (home["root"] / "package.civic-v1.json").read_bytes()
    assert run(tool, "build")[0] == 0 and (home["root"] / "package.civic-v1.json").read_bytes() == first
    assert run(tool, "build", "--check")[0] == 0


@pytest.mark.parametrize("origin", ["search_summary", "search_title", "search_snippet", "file_name", "url"])
def test_search_snippet_or_file_name_is_not_evidence(tool, home, origin):
    form = evidence_form_a(tool)
    form["capture"]["origin"] = origin
    code, out = attach_a(tool, home, form)
    assert code == 1 and any(p.get("code") == "snippet_not_evidence" for p in out["problems"])
    assert states(tool)["test-almaty-closure"] == "candidate"


def test_snippet_pasted_as_page_text_is_refused(tool, home):
    snippet = home["texts"] / "snippet.txt"
    snippet.write_text("Улицу Алматы в Астане частично закроют до конца 2026 года. Опубликовано: 18 июля 2026",
                       encoding="utf-8")
    path = write(home["tmp"] / "f.json", evidence_form_a(tool))
    code, out = run(tool, "attach", path, "--text", snippet, "--attached-at", "2026-10-06T10:00:00Z")
    assert code == 1
    codes = {p.get("code") for p in out["problems"]}
    assert "too_short" in codes                                  # один сниппет — не страница
    assert not (home["root"] / "evidence").exists()


def test_quote_must_be_found_verbatim_and_script_text_does_not_count(tool, home):
    form = evidence_form_a(tool)
    claims = {c["field"]: c for c in form["claims"]}
    claims["budget.amount_kzt"].update(value=999000000, quote="в Астане сумма 999 000 000 тенге")
    claims["budget.basis"].update(value="planned", quote="в Астане сумма 999 000 000 тенге")
    code, out = attach_a(tool, home, form)
    assert code == 1
    assert sum(1 for p in out["problems"] if p.get("problem", "").startswith("выдержка не найдена")) == 2


@pytest.mark.parametrize("page_key,value,code_expected", [
    ("published_quote", "Опубликовано недавно, в июле", "value_not_in_quote"),
    ("city_quote", "будет закрыт участок улицы Алматы", "city"),
    ("title_quote", "Улицу Алматы", "quote_short"),
])
def test_page_level_evidence_is_mandatory(tool, home, page_key, value, code_expected):
    form = evidence_form_a(tool)
    form["page"][page_key] = value
    code, out = attach_a(tool, home, form)
    assert code == 1 and any(p.get("code") == code_expected for p in out["problems"])


@pytest.mark.parametrize("drop,code_expected", [
    ("what", "missing_what"), ("location.text", "missing_location_text"),
    (("schedule.planned_start", "schedule.current_planned_end"), "missing_when")])
def test_what_where_when_are_mandatory(tool, home, drop, code_expected):
    form = evidence_form_a(tool)
    drop = (drop,) if isinstance(drop, str) else drop
    form["claims"] = [c for c in form["claims"] if c["field"] not in drop]
    code, out = attach_a(tool, home, form)
    assert code == 1 and any(p.get("code") == code_expected for p in out["problems"])


def test_page_text_inside_repository_is_refused(tool, home):
    from r13_helpers import REPO
    path = write(home["tmp"] / "f.json", evidence_form_a(tool))
    inside = REPO / "data/civic/astana/round13-verified/config.json"
    code, out = run(tool, "attach", path, "--text", inside)
    assert code == 2 and "ВНЕ репозитория" in out["problems"][0]["problem"]


def test_personal_data_in_attacher_label_is_refused(tool, home):
    form = evidence_form_a(tool)
    form["capture"]["attached_by"] = "Иван, +7 701 123 45 67"
    code, out = attach_a(tool, home, form)
    assert code == 1 and any(p.get("code") == "pii" for p in out["problems"])


def test_attach_does_not_overwrite_without_replace(tool, home):
    assert attach_a(tool, home)[0] == 0
    code, out = attach_a(tool, home)
    assert code == 1 and "--replace" in out["problems"][0]["problem"]
    assert attach_a(tool, home, None, "--replace")[0] == 0


def test_reviewer_must_be_another_person(tool, home):
    assert attach_a(tool, home)[0] == 0
    code, out = review(tool, home, review_form_for(tool, "test-almaty-closure", reviewer="Оператор R05 (ТЕСТ)"))
    assert code == 1 and any(p.get("code") == "same_person" for p in out["problems"])
    assert states(tool)["test-almaty-closure"] == "evidence_attached"


def test_every_claim_needs_a_decision_and_rejected_fields_stay_null(tool, home):
    assert attach_a(tool, home)[0] == 0
    form = review_form_for(tool, "test-almaty-closure")
    key = "src-r12-test-almaty-a:responsible.organization"
    form["claims"][key] = ""
    code, out = review(tool, home, form)
    assert code == 1 and any(p.get("code") == "decision" for p in out["problems"])
    form["claims"][key] = "reject: название органа на странице неполное"
    assert review(tool, home, form)[0] == 0
    run(tool, "build")
    [item] = json.loads((home["root"] / "package.civic-v1.json").read_text("utf-8"))["items"]
    assert item["responsible"]["organization"] is None


def test_evidence_edit_after_review_makes_review_stale_and_drops_draft(tool, home):
    assert attach_a(tool, home)[0] == 0
    assert review(tool, home, review_form_for(tool, "test-almaty-closure"))[0] == 0
    path = home["root"] / "evidence/test-almaty-closure/src-r12-test-almaty-a.json"
    ev = json.loads(path.read_text("utf-8"))
    ev["notes"] = "дописано после проверки"
    path.write_text(json.dumps(ev, ensure_ascii=False), encoding="utf-8")
    assert states(tool)["test-almaty-closure"] == "review_stale"
    run(tool, "build")
    assert json.loads((home["root"] / "package.civic-v1.json").read_text("utf-8"))["items"] == []


def test_file_names_and_folders_do_not_promote(tool, home):
    """Файл «verified» или ручная проверка без доказательств ничего не повышают."""
    reviews = home["root"] / "reviews"
    reviews.mkdir()
    fake = {"schema": "r05-r13-review-v1", "target": "test-programme", "evidence_digest": None, "reviewer": "кто-то",
            "reviewed_at": "2026-10-06T12:00:00Z", "method": "url_opened_by_reviewer", "decision": "accept"}
    write(reviews / "test-programme.json", fake)
    (home["root"] / "verified").mkdir()
    write(home["root"] / "verified" / "ast-r05-construction-test-programme.json", {"id": "x"})
    assert states(tool)["test-programme"] == "candidate"
    assert attach_a(tool, home)[0] == 0
    src = home["root"] / "evidence/test-almaty-closure/src-r12-test-almaty-a.json"
    shutil.copy(src, home["root"] / "evidence/test-almaty-closure/verified-final.json")
    assert states(tool)["test-almaty-closure"] == "evidence_invalid"     # имя файла ≠ source.id
    code, out = run(tool, "check")
    assert code == 1
    codes = {e["code"] for e in out["errors"]}
    assert {"file_name", "review_without_evidence"} <= codes
    run(tool, "build")
    assert json.loads((home["root"] / "package.civic-v1.json").read_text("utf-8"))["items"] == []


def test_old_status_announcement_is_not_current_state(tool, home):
    form = evidence_form_a(tool)
    claims = {c["field"]: c for c in form["claims"]}
    claims["status"].update(value="in_progress", claim_type="reported_actual",
                            quote="будет закрыт участок улицы Алматы от улицы Акмешит")
    assert attach_a(tool, home, form)[0] == 0
    assert review(tool, home, review_form_for(tool, "test-almaty-closure"))[0] == 0
    run(tool, "build")
    [item] = json.loads((home["root"] / "package.civic-v1.json").read_text("utf-8"))["items"]
    assert item["status"] == "unknown"                          # 18.07 старше 45 дней на 07.10
    assert "актуальность неизвестна" in item["evidence_notes"]
    assert all("status" not in r["fields"] for r in item["source_refs"])


def test_fresh_update_supports_current_status(tool, home):
    assert attach_a(tool, home)[0] == 0
    form = tool.evidence_form("test-almaty-closure", "src-r12-test-almaty-b", None, None, None)
    form["capture"].update({"attached_by": "оператор R05 (тест)", "retrieved_at": "2026-10-06T09:30:00Z"})
    form["page"] = {"title_quote": "Перекрытие улицы Алматы в Астане продлено", "published_on": "2026-10-01",
                    "published_quote": "Дата публикации: 01.10.2026",
                    "city_quote": "В Астане продолжаются работы на участке улицы Алматы"}
    claims = {c["field"]: c for c in form["claims"]}
    claims["what"].update(value="Строительство транспортного тоннеля", quote="строительство транспортного тоннеля идёт по графику")
    claims["location.text"].update(value="ул. Алматы от ул. Акмешит до ул. Сауран",
                                   quote="участке улицы Алматы от улицы Акмешит до улицы Сауран")
    claims["status"].update(value="in_progress", claim_type="reported_actual",
                            quote="строительство транспортного тоннеля идёт по графику")
    claims["schedule.current_planned_end"].update(value="2026-12-31", claim_type="expected",
                                                  quote="Ограничение движения сохранится до 31 декабря 2026 года")
    path = write(home["tmp"] / "f-b.json", form)
    code, out = run(tool, "attach", path, "--text", home["texts"] / "b.html", "--attached-at", "2026-10-06T10:30:00Z")
    assert code == 0, out
    rf = review_form_for(tool, "test-almaty-closure")
    code, out = review(tool, home, rf)
    assert code == 1 and any(p.get("code") == "conflict" for p in out["problems"])   # два значения одного поля
    rf["claims"]["src-r12-test-almaty-a:schedule.current_planned_end"] = "reject: есть более позднее сообщение"
    rf["claims"]["src-r12-test-almaty-a:what"] = "reject: формулировка из второго источника точнее"
    rf["claims"]["src-r12-test-almaty-a:location.text"] = "reject: то же место во втором источнике"
    assert review(tool, home, rf)[0] == 0
    run(tool, "build")
    [item] = json.loads((home["root"] / "package.civic-v1.json").read_text("utf-8"))["items"]
    assert item["status"] == "in_progress" and item["evidence_type"] == "observed"   # дата дословно, без вывода
    assert {r["id"] for r in item["source_refs"]} == {"src-r12-test-almaty-a", "src-r12-test-almaty-b"}


def test_past_closure_goes_to_historical_not_current(tool, home):
    form = evidence_form_a(tool)
    claims = {c["field"]: c for c in form["claims"]}
    claims["schedule.current_planned_end"].update(value="2026-07-20", claim_type="stated", value_basis=None,
                                                  quote="с 20 июля 2026 года будет закрыт участок улицы Алматы")
    claims["schedule.planned_start"].update(value=None, quote="")
    assert attach_a(tool, home, form)[0] == 0
    assert review(tool, home, review_form_for(tool, "test-almaty-closure"))[0] == 0
    code, out = run(tool, "build")
    assert code == 0
    assert out["summary"]["verified_current"] == 0 and out["summary"]["verified_historical"] == 1


def test_actual_end_needs_report_not_later_than_publication(tool, home):
    form = evidence_form_a(tool)
    claims = {c["field"]: c for c in form["claims"]}
    claims["schedule.actual_end"] = {"field": "schedule.actual_end", "value": "2026-12-31", "claim_type": "reported_actual",
                                     "quote": "Ограничение продлится до конца 2026 года",
                                     "value_basis": "«до конца 2026 года»"}
    form["claims"] = list(claims.values())
    code, out = attach_a(tool, home, form)
    assert code == 1 and any(p.get("code") == "actual_after_publication" for p in out["problems"])


def test_amount_without_basis_is_refused(tool, home):
    form = evidence_form_a(tool)
    claims = {c["field"]: c for c in form["claims"]}
    claims["budget.amount_kzt"].update(value=5, quote="Сумма работ в сообщении не указана", value_basis="выдумано")
    code, out = attach_a(tool, home, form)
    assert code == 1 and any(p.get("code") == "budget_basis" for p in out["problems"])


def test_without_usable_geometry_record_is_not_published(tool, home):
    assert attach_a(tool, home)[0] == 0
    assert review(tool, home, review_form_for(tool, "test-almaty-closure", level="none"))[0] == 0
    assert states(tool)["test-almaty-closure"] == "reviewed_no_geometry"
    code, out = run(tool, "build")
    assert out["summary"]["verified_current"] == 0


def test_whole_street_is_approximate_and_needs_a_reason(tool, home):
    assert attach_a(tool, home)[0] == 0
    form = review_form_for(tool, "test-almaty-closure", level="whole_street")
    form["geometry"]["osm_query"] = {"street": "Сауран"}
    code, out = review(tool, home, form)
    assert code == 1 and any(p.get("where", "").endswith("geometry.reason") for p in out["problems"])


def test_reviewer_can_recheck_the_same_saved_text(tool, home):
    assert attach_a(tool, home)[0] == 0
    form = review_form_for(tool, "test-almaty-closure", method="saved_text_rechecked")
    code, out = review(tool, home, form, "--text", f"src-r12-test-almaty-a={home['texts'] / 'b.html'}")
    assert code == 1 and any("sha256" in p.get("problem", "") for p in out["problems"])
    code, out = review(tool, home, form, "--text", f"src-r12-test-almaty-a={home['texts'] / 'a.html'}")
    assert code == 0 and out["state"] == "draft_ready"


def test_unknown_target_and_bad_forms_fail_cleanly(tool, home):
    path = write(home["tmp"] / "bad.json", {"schema": "something-else"})
    assert run(tool, "attach", path, "--text", home["texts"] / "a.html")[0] == 2
    assert run(tool, "review", path)[0] == 2
    assert run(tool, "status", "no-such-target")[0] == 2
