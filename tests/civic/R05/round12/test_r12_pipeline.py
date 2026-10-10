"""R05 раунд 12: verify → build → проверка civic-v1 → dry-run импортера R02 на FIXTURE-данных.

FIXTURE-текст ниже синтетический и нужен только тесту механизма: он никогда не попадает
в data/civic/astana/round12-verified/. Реальные кандидаты проверяются в test_r12_real_data.py.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[4]
PKG = REPO / "data/civic/astana/round12-verified"
TOOL = PKG / "tools/r12.py"
HAS_BASE = (REPO / "data/civic/astana/tools/civic_v1.py").exists()
needs_base = pytest.mark.skipif(not HAS_BASE, reason="NOT_RUN: нет валидатора R05 data/civic/astana/tools (дерево не от 56538a3)")

FIXTURE_TEXT = """<html><body><h1>FIXTURE R05: синтетическая заметка для теста механизма проверки</h1>
<p>Опубликовано 2026-09-20. Ремонт тестового участка улицы Примерной планируют завершить
до 30 ноября 2026 года.</p>
<p>Работы ведёт ТОО «Тестовый подрядчик». Стоимость работ по договору — 125 000 000 тенге.</p>
<script>var ignored = "текст скрипта не считается текстом страницы";</script>
</body></html>"""

SOURCE = {"id": "src-r12-fixture-1", "url": "https://example.org/r05-fixture-1",
          "publisher": "FIXTURE publisher", "publisher_kind": "other",
          "title_as_listed": "FIXTURE R05: синтетическая заметка", "published_on": None,
          "published_on_basis": None,
          "discovered_via": {"tool": "fixture", "at": "2026-10-07T00:00:00Z", "query": "fixture"},
          "access_status": "not_fetched", "retrieved_at": None, "content_sha256": None,
          "fetch_method": None, "license": None, "license_status": "unknown", "access_attempts": []}


def draft(**changes):
    rec = {
        "schema": "r05-r12-record-v1", "id": "ast-r12-roadworks-fixture-primernaya",
        "kind": "roadworks", "title": "FIXTURE: ремонт тестового участка",
        "description": "Синтетическая запись теста механизма.", "historical": False,
        "location": {"text": "улица Примерная", "geometry": {"type": "Point", "coordinates": [71.43, 51.16]},
                     "geometry_precision": "approximate", "geometry_basis": "FIXTURE: условная точка теста"},
        "claims": [
            {"field": "status", "value": "planned", "claim_type": "expected", "source_id": "src-r12-fixture-1",
             "quote": "планируют завершить до 30 ноября 2026 года", "locator": "абзац 1", "value_basis": None},
            {"field": "schedule.current_planned_end", "value": "2026-11-30", "claim_type": "expected",
             "source_id": "src-r12-fixture-1", "quote": "завершить до 30 ноября 2026 года", "locator": "абзац 1",
             "value_basis": None},
            {"field": "responsible.organization", "value": "ТОО «Тестовый подрядчик»", "claim_type": "stated",
             "source_id": "src-r12-fixture-1", "quote": "Работы ведёт ТОО «Тестовый подрядчик»",
             "locator": "абзац 2", "value_basis": None},
            {"field": "budget.amount_kzt", "value": 125000000, "claim_type": "stated",
             "source_id": "src-r12-fixture-1", "quote": "по договору — 125 000 000 тенге", "locator": "абзац 2",
             "value_basis": None},
            {"field": "budget.basis", "value": "contract", "claim_type": "stated",
             "source_id": "src-r12-fixture-1", "quote": "Стоимость работ по договору", "locator": "абзац 2",
             "value_basis": None},
        ],
        "not_confirmed": ["schedule.planned_start"],
        "evidence_notes": "FIXTURE: срок — ожидаемый, о начале работ источник не сообщает.",
    }
    rec.update(changes)
    return rec


@pytest.fixture
def home(tmp_path):
    root = tmp_path / "pkg"
    (root / "drafts").mkdir(parents=True)
    (root / "verified").mkdir()
    shutil.copy(PKG / "config.json", root / "config.json")
    (root / "sources.json").write_text(json.dumps(
        {"schema": "r05-r12-sources-v1", "city": "astana", "sources": [dict(SOURCE)]}, ensure_ascii=False))
    (root / "candidates.json").write_text(json.dumps({"schema": "r05-r12-candidates-v1", "candidates": []}))
    page = tmp_path / "outside" / "page.html"
    page.parent.mkdir()
    page.write_text(FIXTURE_TEXT, encoding="utf-8")
    return root, page


def run(home_dir, *args):
    env = dict(os.environ, R12_HOME=str(home_dir))
    return subprocess.run([sys.executable, "-I", str(TOOL), *args], capture_output=True, text=True, env=env,
                          cwd=str(REPO), timeout=120)


def write_draft(root, rec):
    path = root / "drafts" / f"{rec['id']}.json"
    path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return path


def verify(root, page, path, *extra):
    return run(root, "verify", str(path), "--text", f"src-r12-fixture-1={page}",
               "--published-on", "src-r12-fixture-1=2026-09-20", "--retrieved-at", "2026-10-07T10:30:00Z", *extra)


def test_verify_moves_record_and_records_sha(home):
    root, page = home
    path = write_draft(root, draft())
    result = verify(root, page, path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not path.exists() and (root / "verified" / path.name).exists()
    src = json.loads((root / "sources.json").read_text())["sources"][0]
    assert src["access_status"] == "fetched" and src["published_on"] == "2026-09-20"
    assert src["content_sha256"] == hashlib.sha256(page.read_bytes()).hexdigest()
    rec = json.loads((root / "verified" / path.name).read_text())
    assert rec["verification"]["sources"]["src-r12-fixture-1"]["content_sha256"] == src["content_sha256"]


def test_missing_quote_keeps_draft_and_registry_untouched(home):
    root, page = home
    rec = draft()
    rec["claims"][1]["quote"] = "сдать объект до 30 ноября 2026 года"   # дата согласована, но фразы нет в тексте
    path = write_draft(root, rec)
    result = verify(root, page, path)
    assert result.returncode == 1 and "не найдена дословно" in result.stdout
    assert path.exists() and not list((root / "verified").glob("*.json"))
    assert json.loads((root / "sources.json").read_text())["sources"][0]["access_status"] == "not_fetched"


def test_script_text_is_not_page_text(home):
    root, page = home
    rec = draft()
    rec["claims"][2]["quote"] = "текст скрипта не считается текстом страницы"
    result = verify(root, page, write_draft(root, rec))
    assert result.returncode == 1


@pytest.mark.parametrize("claim_change,code", [
    ({"field": "status", "value": "in_progress", "claim_type": "expected"}, "status_type"),
    ({"field": "status", "value": "completed", "claim_type": "stated"}, "status_type"),
    ({"field": "schedule.current_planned_end", "value": "30.11.2026"}, "date"),
    ({"field": "budget.amount_kzt", "value": 0}, "amount"),
    ({"field": "budget.amount_kzt", "value": "125 млн"}, "amount"),
])
def test_bad_claims_rejected_before_text_check(home, claim_change, code):
    root, page = home
    rec = draft()
    target = next(c for c in rec["claims"] if c["field"] == claim_change["field"])
    target.update(claim_change)
    result = verify(root, page, write_draft(root, rec))
    assert result.returncode == 1 and code in result.stdout


def test_budget_without_basis_and_actual_end_without_completed(home):
    root, page = home
    rec = draft()
    rec["claims"] = [c for c in rec["claims"] if c["field"] != "budget.basis"]
    rec["claims"].append({"field": "schedule.actual_end", "value": "2026-09-01", "claim_type": "reported_actual",
                          "source_id": "src-r12-fixture-1", "quote": "Опубликовано 2026-09-20",
                          "locator": "шапка", "value_basis": None})
    result = verify(root, page, write_draft(root, rec))
    assert result.returncode == 1 and "budget_basis" in result.stdout and "actual_end" in result.stdout


@pytest.mark.skipif(not HAS_BASE, reason="NOT_RUN: нет data/civic/astana/tools (дерево не от 56538a3)")
def test_pii_in_quote_is_rejected(home):
    root, page = home
    rec = draft()
    rec["claims"][2]["quote"] = "Работы ведёт ТОО, телефон +7 701 123 45 67"
    result = verify(root, page, write_draft(root, rec))
    assert result.returncode == 1 and "pii" in result.stdout


@needs_base
def test_build_is_deterministic_and_check_detects_staleness(home):
    root, page = home
    assert verify(root, page, write_draft(root, draft())).returncode == 0
    first = run(root, "build")
    assert first.returncode == 0, first.stdout + first.stderr
    pkg_bytes = (root / "package.civic-v1.json").read_bytes()
    assert run(root, "build").returncode == 0
    assert (root / "package.civic-v1.json").read_bytes() == pkg_bytes
    assert run(root, "build", "--check").returncode == 0
    (root / "package.civic-v1.json").write_text("{}")
    assert run(root, "build", "--check").returncode == 1
    package = json.loads(pkg_bytes)
    item = package["items"][0]
    # Серверные поля есть (как в срезах раунда 11), но импорт их игнорирует; публикации в пакете нет.
    assert package["slice"]["demo"] is False and item["publication"] == "draft" and item["revision"] == 1
    assert package["slice"]["count"] == 1 and len(package["slice"]["content_sha256"]) == 64
    assert item["status"] == "planned" and item["schedule"]["current_planned_end"] == "2026-11-30"
    assert item["schedule"]["planned_start"] is None
    assert item["budget"] == {"amount_kzt": 125000000, "basis": "contract", "source_id": "src-r12-fixture-1"}
    assert item["evidence_type"] == "observed"
    assert item["source_refs"][0]["access_status"] == "fetched"
    assert "Источник не подтверждает: schedule.planned_start" in item["evidence_notes"]
    summary = json.loads((root / "summary.json").read_text())
    assert summary["confirmed_current"] == 1 and summary["confirmed_historical"] == 0


@needs_base
def test_value_basis_makes_record_derived_and_flagged_historical_goes_to_historical(home):
    root, page = home
    rec = draft(historical=True)
    rec["claims"][1].update(value_basis="FIXTURE: проверка производного значения")
    assert verify(root, page, write_draft(root, rec)).returncode == 0
    assert run(root, "build").returncode == 0
    current = json.loads((root / "package.civic-v1.json").read_text())["items"]
    hist = json.loads((root / "historical.civic-v1.json").read_text())["items"]
    assert current == [] and hist[0]["evidence_type"] == "derived"
    assert "FIXTURE: проверка производного значения" in hist[0]["evidence_notes"]


@needs_base
def test_overdue_project_without_completion_stays_current(home):
    """Регрессия ревью: план «до 2025» без сообщения о завершении — не повод уводить объект в историю."""
    root, page = home
    rec = draft()
    rec["claims"][1].update(value="2024-11-30", value_basis="FIXTURE: старый плановый срок")
    assert verify(root, page, write_draft(root, rec)).returncode == 0
    assert run(root, "build").returncode == 0
    assert json.loads((root / "historical.civic-v1.json").read_text())["items"] == []
    current = json.loads((root / "package.civic-v1.json").read_text())["items"]
    assert [i["id"] for i in current] == ["ast-r12-roadworks-fixture-primernaya"]


@pytest.mark.skipif(not HAS_BASE, reason="NOT_RUN: нет валидатора R05 (дерево не от 56538a3)")
def test_built_package_passes_r05_real_profile_and_r02_rules(home):
    root, page = home
    assert verify(root, page, write_draft(root, draft())).returncode == 0
    assert run(root, "build").returncode == 0
    check = run(root, "check")
    report = json.loads(check.stdout)
    assert check.returncode == 0, report
    assert report["validators"]["r05_civic_v1_real"] == "RUN"
    if (REPO / "ui/civic_store/validate.py").exists():
        assert report["validators"]["r02_validate_content"] == "RUN"


@pytest.mark.skipif(not (REPO / "ui/civic_store/importer.py").exists(), reason="NOT_RUN: нет импортера R02")
def test_importer_dry_run_accepts_package(home, tmp_path):
    root, page = home
    assert verify(root, page, write_draft(root, draft())).returncode == 0
    assert run(root, "build").returncode == 0
    sys.path.insert(0, str(REPO))
    try:
        from ui.civic_store.importer import import_package, load_package
        from ui.civic_store.service import CivicService
    finally:
        sys.path.pop(0)
    service = CivicService(tmp_path / "dry.sqlite3")
    report = import_package(service.objects, load_package(root / "package.civic-v1.json"), dry_run=True)
    assert report["status"] == "dry_run" and report["counts"].get("create") == 1
    assert not any(item["action"] == "invalid" for item in report["items"])
    assert report["source"] == "r05-astana-r12-verified"


def test_build_refuses_records_without_base_validator(home, monkeypatch):
    root, page = home
    assert verify(root, page, write_draft(root, draft())).returncode == 0
    if HAS_BASE:
        pytest.skip("проверяется только в дереве без валидатора R05")
    result = run(root, "build")
    assert result.returncode == 1 and "validator_not_run" in result.stdout
    assert json.loads((root / "package.civic-v1.json").read_text())["items"] == []


# ---------------------------------------------------------------- регрессии ревью (2026-10-07)
@needs_base
def test_editing_verified_record_after_verify_drops_it(home):
    root, page = home
    assert verify(root, page, write_draft(root, draft())).returncode == 0
    path = root / "verified" / "ast-r12-roadworks-fixture-primernaya.json"
    rec = json.loads(path.read_text())
    rec["claims"][2]["value"] = "ТОО «Другой подрядчик»"          # правка после проверки
    path.write_text(json.dumps(rec, ensure_ascii=False))
    result = run(root, "build")
    assert result.returncode == 1 and "edited_after_verify" in result.stdout
    assert json.loads((root / "package.civic-v1.json").read_text())["items"] == []
    assert run(root, "check").returncode == 1


def test_budget_basis_from_another_source_is_rejected(home):
    root, page = home
    reg = json.loads((root / "sources.json").read_text())
    reg["sources"].append(dict(SOURCE, id="src-r12-fixture-2", url="https://example.org/r05-fixture-2"))
    (root / "sources.json").write_text(json.dumps(reg, ensure_ascii=False))
    rec = draft()
    next(c for c in rec["claims"] if c["field"] == "budget.basis")["source_id"] = "src-r12-fixture-2"
    result = run(root, "verify", str(write_draft(root, rec)), "--text", f"src-r12-fixture-1={page}",
                 "--text", f"src-r12-fixture-2={page}", "--retrieved-at", "2026-10-07T10:30:00Z")
    assert result.returncode == 1 and "budget_basis_source" in result.stdout


def test_actual_end_must_be_reported_actual(home):
    root, page = home
    rec = draft()
    rec["claims"][0].update(value="completed", claim_type="reported_actual", quote="планируют завершить до 30 ноября 2026 года")
    rec["claims"].append({"field": "schedule.actual_end", "value": "2026-09-20", "claim_type": "expected",
                          "source_id": "src-r12-fixture-1", "quote": "Опубликовано 2026-09-20. Ремонт",
                          "locator": "шапка", "value_basis": None})
    result = verify(root, page, write_draft(root, rec))
    assert result.returncode == 1 and "actual_type" in result.stdout


@pytest.mark.parametrize("field,value,quote,code", [
    ("budget.amount_kzt", 25000000, "по договору — 125 000 000 тенге", "value_not_in_quote"),
    ("schedule.current_planned_end", "2026-11-03", "завершить до 30 ноября 2026 года", "value_not_in_quote"),
    ("responsible.organization", "ТОО", "ведёт", "quote_short"),
])
def test_value_must_be_in_quote_and_quote_not_trivial(home, field, value, quote, code):
    root, page = home
    rec = draft()
    claim = next(c for c in rec["claims"] if c["field"] == field)
    claim.update(value=value, quote=quote)
    result = verify(root, page, write_draft(root, rec))
    assert result.returncode == 1 and code in result.stdout


def test_number_inside_bigger_number_is_not_a_match(home, tmp_path):
    root, _ = home
    page = tmp_path / "big.txt"
    page.write_text("Опубликовано 2026-09-20. Общая стоимость работ по договору — 1 125 000 000 тенге. "
                    "Ремонт планируют завершить до 30 ноября 2026 года. Работы ведёт ТОО «Тестовый подрядчик».",
                    encoding="utf-8")
    result = verify(root, page, write_draft(root, draft()))
    assert result.returncode == 1 and "по договору — 125 000 000 тенге" in result.stdout


def test_script_in_fragment_without_html_tag_is_not_text(home, tmp_path):
    root, _ = home
    page = tmp_path / "fragment.html"
    page.write_text('<article><script>window.x="Работы ведёт ТОО «Тестовый подрядчик»"</script>'
                    "Ремонт планируют завершить до 30 ноября 2026 года. Стоимость работ по договору — 125 000 000 тенге."
                    "</article>", encoding="utf-8")
    result = verify(root, page, write_draft(root, draft()))
    assert result.returncode == 1 and "Тестовый подрядчик" in result.stdout


def test_reverify_shared_source_with_other_text_is_refused(home, tmp_path):
    root, page = home
    assert verify(root, page, write_draft(root, draft())).returncode == 0
    other = tmp_path / "other.html"
    other.write_text(FIXTURE_TEXT + "<p>Обновлено.</p>", encoding="utf-8")
    rec = draft(id="ast-r12-roadworks-fixture-second")
    result = verify(root, other, write_draft(root, rec))
    assert result.returncode == 1 and "текст отличается" in result.stdout
    changed_date = verify(root, page, write_draft(root, rec), "--published-on", "src-r12-fixture-1=2026-09-01")
    assert changed_date.returncode == 1 and "дата публикации отличается" in changed_date.stdout


def test_published_on_without_basis_is_an_error(home):
    root, _ = home
    reg = json.loads((root / "sources.json").read_text())
    reg["sources"][0].update(published_on="2026-09-30", published_on_basis=None)
    (root / "sources.json").write_text(json.dumps(reg, ensure_ascii=False))
    result = run(root, "check")
    assert result.returncode == 1 and "published_on_basis" in result.stdout


def test_fetch_refuses_to_store_text_inside_repo(home):
    root, _ = home
    result = run(root, "fetch", "src-r12-fixture-1", "--out", str(REPO / "data"))
    assert result.returncode == 2 and "вне репозитория" in result.stderr


def test_summary_tolerates_candidates_without_freshness(home):
    root, _ = home
    (root / "candidates.json").write_text(json.dumps({"schema": "r05-r12-candidates-v1", "candidates": [
        {"id": "cand-a", "decision": "to_verify", "reason": "r", "kind": "event", "source_ids": ["src-r12-fixture-1"],
         "date_hint_origin": "none", "hints": [], "freshness": "past_2026"},
        {"id": "cand-b", "decision": "to_verify", "reason": "r", "kind": "event", "source_ids": ["src-r12-fixture-1"],
         "date_hint_origin": "none", "hints": []}]}), encoding="utf-8")
    result = run(root, "summary")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["unverified_by_freshness"] == {"past_2026": 1, "unknown": 1}


# ---------------------------------------------------------------- регрессии ревью устойчивости (2026-10-07)
def test_verify_does_not_overwrite_another_record_with_same_id(home):
    root, page = home
    assert verify(root, page, write_draft(root, draft())).returncode == 0
    other = draft(title="FIXTURE: другой объект с тем же id")
    other["claims"] = other["claims"][2:3]
    path = root / "drafts" / "second-object.json"
    path.write_text(json.dumps(other, ensure_ascii=False), encoding="utf-8")
    refused = verify(root, page, path)
    assert refused.returncode == 1 and "--replace" in refused.stdout
    kept = json.loads((root / "verified" / "ast-r12-roadworks-fixture-primernaya.json").read_text())
    assert len(kept["claims"]) == 5
    assert verify(root, page, path, "--replace").returncode == 0


@needs_base
def test_duplicate_id_files_do_not_reach_the_package(home):
    root, page = home
    assert verify(root, page, write_draft(root, draft())).returncode == 0
    src = root / "verified" / "ast-r12-roadworks-fixture-primernaya.json"
    (root / "verified" / "copy-of-record.json").write_bytes(src.read_bytes())
    result = run(root, "build")
    assert result.returncode == 1 and "dup_id" in result.stdout and "file_name" in result.stdout
    assert len(json.loads((root / "package.civic-v1.json").read_text())["items"]) == 1


def test_published_on_null_to_date_on_fetched_source_is_a_conflict(home):
    root, page = home
    rec = draft()
    rec["claims"] = rec["claims"][2:3]                                  # только организация
    assert run(root, "verify", str(write_draft(root, rec)), "--text", f"src-r12-fixture-1={page}",
               "--retrieved-at", "2026-10-07T10:30:00Z").returncode == 0
    second = verify(root, page, write_draft(root, draft(id="ast-r12-roadworks-fixture-second")))
    assert second.returncode == 1 and "null → дата" in second.stdout
    assert "ast-r12-roadworks-fixture-primernaya" in second.stdout     # названы затронутые записи


@pytest.mark.parametrize("retrieved,needle", [("2026-09-01T10:00:00Z", "раньше публикации"),
                                              ("2026-11-01T10:00:00Z", "позже даты среза")])
def test_retrieved_at_must_fit_publication_and_slice(home, retrieved, needle):
    root, page = home
    result = run(root, "verify", str(write_draft(root, draft())), "--text", f"src-r12-fixture-1={page}",
                 "--published-on", "src-r12-fixture-1=2026-09-20", "--retrieved-at", retrieved)
    assert result.returncode == 1 and needle in result.stdout
    assert json.loads((root / "sources.json").read_text())["sources"][0]["access_status"] == "not_fetched"


def test_malformed_inputs_give_reports_not_tracebacks(home, tmp_path):
    root, page = home
    (root / "drafts" / "broken.json").write_text('{"id": "x",}', encoding="utf-8")
    check = run(root, "check")
    assert "Traceback" not in check.stderr and "unreadable" in check.stdout
    (root / "drafts" / "broken.json").unlink()
    missing = run(root, "verify", str(root / "drafts" / "nope.json"), "--retrieved-at", "2026-10-07T10:30:00Z")
    assert missing.returncode == 2 and "Traceback" not in missing.stderr
    path = write_draft(root, draft())
    no_eq = run(root, "verify", str(path), "--text", str(page), "--retrieved-at", "2026-10-07T10:30:00Z")
    assert no_eq.returncode == 2 and "SRC_ID=" in no_eq.stdout
    gone = run(root, "verify", str(path), "--text", "src-r12-fixture-1=/nonexistent/page.txt",
               "--retrieved-at", "2026-10-07T10:30:00Z")
    assert gone.returncode == 2 and "нет файла" in gone.stdout
    inf = draft()
    next(c for c in inf["claims"] if c["field"] == "budget.amount_kzt")["value"] = float("inf")
    path.write_text(json.dumps(inf), encoding="utf-8")
    res = verify(root, page, path)
    assert res.returncode == 1 and "Traceback" not in res.stderr


@pytest.mark.parametrize("mutate,code", [
    (lambda r: r["claims"][0].update(locator="абзац: " + "длинный текст страницы " * 20), "bad_text"),
    (lambda r: r["claims"][0].update(page_text="полный текст статьи"), "unknown_keys"),
    (lambda r: r.update(full_article="..."), "unknown_keys"),
    (lambda r: r["location"].update(text="место " * 80), "bad_text"),
])
def test_free_text_fields_are_limited_and_allowlisted(home, mutate, code):
    root, page = home
    rec = draft()
    mutate(rec)
    result = verify(root, page, write_draft(root, rec))
    assert result.returncode == 1 and code in result.stdout


@needs_base
def test_pii_outside_quotes_is_rejected(home):
    root, page = home
    rec = draft()
    rec["location"]["text"] = "прораб, телефон +7 701 234 56 78"
    result = verify(root, page, write_draft(root, rec))
    assert result.returncode == 1 and "pii" in result.stdout


@needs_base
def test_slice_inputs_record_config_and_missing_summary_is_stale(home):
    root, page = home
    assert verify(root, page, write_draft(root, draft())).returncode == 0
    assert run(root, "build").returncode == 0
    inputs = {i["path"] for i in json.loads((root / "package.civic-v1.json").read_text())["slice"]["inputs"]}
    assert {"config.json", "sources.json"} <= inputs
    (root / "summary.json").unlink()
    assert run(root, "build", "--check").returncode == 1
    assert "summary.json" in json.loads(run(root, "check").stdout)["stale_packages"]
