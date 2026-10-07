"""Regression tests for defects confirmed by the round-11 adversarial review of the R05 package."""

import copy
import json
import os
import sys
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PKG = os.path.join(REPO, "data", "civic", "astana")
sys.path.insert(0, os.path.join(PKG, "tools"))
sys.path.insert(0, os.path.dirname(__file__))

import build_slice as bs  # noqa: E402
import civic_v1 as cv  # noqa: E402
from test_build_slice import FETCHED, INTAKE, TempPackage  # noqa: E402
from test_validator_contract import CONTRACT_FIXTURE, FENCE, real_record  # noqa: E402

AS_OF = "2026-10-06"


def errors(obj, profile="contract", **kw):
    return {i["code"] for i in cv.validate_object(obj, profile=profile, as_of=AS_OF, fence=FENCE, **kw)
            if i["severity"] == "error"}


def all_codes(obj, profile="contract"):
    return {(i["code"], i["severity"]) for i in cv.validate_object(obj, profile=profile, as_of=AS_OF, fence=FENCE)}


class NeverCrashes(unittest.TestCase):
    BAD = [
        ("budget", {"amount_kzt": None, "basis": "unknown", "source_id": []}),
        ("budget", {"amount_kzt": json.loads("1" + "0" * 400), "basis": "planned", "source_id": None}),
        ("budget", "x"), ("budget", [1]), ("schedule", "x"), ("schedule", ["x"]), ("responsible", [1]),
        ("source_refs", 7), ("evidence_notes", 5), ("kind", ["roadworks"]), ("geometry", {"type": "Point", "coordinates": ["a", "b"]}),
        ("geometry", {"type": "Point", "coordinates": [json.loads("1" + "0" * 400), 51.0]}),
        ("source_refs", [{"id": "s", "url": "https://[example]/x", "publisher": None, "published_on": None,
                          "retrieved_at": None, "access_status": "not_fetched", "license": None, "fields": 3}]),
    ]

    def test_bad_types_are_issues_in_every_profile(self):
        for key, value in self.BAD:
            for evidence in ("synthetic", "observed", "derived"):
                obj = copy.deepcopy(CONTRACT_FIXTURE)
                obj[key] = value
                obj["evidence_type"] = evidence
                for profile in ("contract", "real", "demo"):
                    issues = cv.validate_object(obj, profile=profile, as_of=AS_OF, fence=FENCE)
                    self.assertTrue(any(i["severity"] == "error" for i in issues), (key, value, profile))
                    self.assertNotIn("validator_exception", {i["code"] for i in issues}, (key, profile))
                report = cv.validate_collection([obj], profile="contract", as_of=AS_OF, fence=FENCE)
                self.assertFalse(report["valid"])


class TextAndUrl(unittest.TestCase):
    def test_entities_and_unclosed_tags_rejected(self):
        for title in ("Демо &laquo;Парк&raquo;", "Демо &#x3c;b&#x3e;", "Демо <img src=x onerror=alert(1)//",
                      "Демо&nbsp;текст"):
            self.assertIn("text_html", errors(dict(CONTRACT_FIXTURE, title=title)), title)
        for ok in ("Демо R&D; AT&T", "Демо ТОО «A&B»"):
            self.assertNotIn("text_html", errors(dict(CONTRACT_FIXTURE, title=ok)), ok)

    def test_bidi_zero_width_and_line_breaks(self):
        for title in ("Демо ‮текст", "Демо a​b", "Демо a\x85b", "Демо\nвторая строка"):
            found = errors(dict(CONTRACT_FIXTURE, title=title))
            self.assertTrue(found & {"text_control_chars", "text_line_break"}, repr(title))
        self.assertNotIn("text_line_break", errors(dict(CONTRACT_FIXTURE, description="Демо.\nВторая строка.")))

    def test_bad_urls_rejected(self):
        for url in ("https://www.gov.kz@evil.example/news", "https://editor:pw@www.gov.kz/x",
                    'https://www.gov.kz/x" onmouseover="alert(1)', "https://www.gov.kz/a b", "https://:80/",
                    "javascript:alert(1)", "https://[example]/x"):
            obj = real_record()
            obj["source_refs"][0]["url"] = url
            self.assertIn("source_ref_url", errors(obj, "real"), url)

    def test_proprietary_hosts_by_label(self):
        self.assertTrue(cv.proprietary_host("2gis.kz"))
        self.assertTrue(cv.proprietary_host("maps.google.com"))
        self.assertTrue(cv.proprietary_host("yandex.kz"))
        self.assertFalse(cv.proprietary_host("www.somewhere.com"))
        self.assertFalse(cv.proprietary_host("scrapple.com"))

    def test_kz_phones_iin_and_unicode_email(self):
        for text in ("тел. 8 (7172) 55-12-34", "+7 7172 551234", "7 701 123 45 67", "ИИН 900101300123",
                     "иван@почта.рф", "+7 701 123 45 67"):
            self.assertTrue(cv.find_pii(text), text)
        for text in ("с 15.11.2026 по 30.11.2026", "выделено 250 000 000 тенге", "2026-10-06"):
            self.assertFalse(cv.find_pii(text), text)

    def test_r05_policies_are_warnings_in_contract_profile(self):
        obj = dict(CONTRACT_FIXTURE, description="Синтетическая запись. Пресс-служба: press@example.org")
        self.assertIn(("pii_suspected", "warning"), all_codes(obj, "contract"))
        self.assertIn("pii_suspected", errors(obj, "demo"))


class SemanticsAlignedWithR02(unittest.TestCase):
    def test_end_before_start_is_error_in_real(self):
        obj = real_record()
        obj["schedule"].update(planned_start="2026-10-10", current_planned_end="2026-10-01")
        obj["source_refs"][0]["fields"] += ["schedule.planned_start", "schedule.current_planned_end"]
        self.assertIn("schedule_order", errors(obj, "real"))

    def test_amount_needs_basis(self):
        obj = real_record()
        obj["budget"] = {"amount_kzt": 1000000, "basis": "unknown", "source_id": "src-test"}
        obj["source_refs"][0]["fields"].append("budget.amount_kzt")
        self.assertIn("budget_amount_without_basis", errors(obj, "real"))

    def test_years_outside_r02_window_rejected(self):
        obj = copy.deepcopy(CONTRACT_FIXTURE)
        obj["schedule"]["planned_start"] = "1900-01-01"
        self.assertIn("date_format", errors(obj))

    def test_coarse_field_paths_allowed_only_in_contract(self):
        obj = real_record()
        obj["source_refs"][0]["fields"] = ["schedule"]
        self.assertNotIn("source_ref_field_path", errors(obj, "contract"))
        self.assertIn("source_ref_field_path", errors(obj, "real"))

    def test_utc_retrieval_on_publication_day_ok(self):
        obj = real_record()
        obj["source_refs"][0].update(published_on="2026-09-30", retrieved_at="2026-09-29T20:00:00Z")
        self.assertNotIn("retrieved_before_published", errors(obj, "real"))
        obj["source_refs"][0]["retrieved_at"] = "2026-09-29T18:59:00Z"  # 23:59 in Astana on the 29th
        self.assertIn("retrieved_before_published", errors(obj, "real"))

    def test_real_profile_requires_as_of(self):
        issues = cv.validate_object(real_record(), profile="real", as_of=None, fence=FENCE)
        self.assertIn("as_of_required", {i["code"] for i in issues})

    def test_status_age_is_a_parameter_not_global(self):
        obj = real_record()
        obj["status"] = "in_progress"
        obj["source_refs"][0]["fields"].append("status")
        obj["source_refs"][0]["published_on"] = "2026-09-01"
        self.assertIn("stale_status", errors(obj, "real", max_status_age_days=10))
        self.assertNotIn("stale_status", errors(obj, "real", max_status_age_days=60))
        self.assertEqual(cv.STATUS_MAX_AGE_DAYS, 45)


class PolygonRules(unittest.TestCase):
    def test_hole_outside_and_zero_area(self):
        shell = [[71.40, 51.15], [71.46, 51.15], [71.46, 51.19], [71.40, 51.19], [71.40, 51.15]]
        hole = [[71.48, 51.16], [71.48, 51.18], [71.50, 51.18], [71.50, 51.16], [71.48, 51.16]]
        self.assertIn("geometry_hole_outside",
                      errors(dict(CONTRACT_FIXTURE, geometry={"type": "Polygon", "coordinates": [shell, hole]})))
        flat = [[71.43, 51.17]] * 4
        self.assertIn("geometry_degenerate",
                      errors(dict(CONTRACT_FIXTURE, geometry={"type": "Polygon", "coordinates": [flat]})))


class DemoMarker(unittest.TestCase):
    def test_ordinary_words_do_not_count_as_demo_marker(self):
        for title in ("Демонтаж рекламных конструкций", "Укладка синтетического покрытия", "Demolition of the depot"):
            obj = dict(CONTRACT_FIXTURE, title=title, description="Работы")
            self.assertIn("demo_unmarked", errors(obj, "demo"), title)


class BuilderProvenance(unittest.TestCase):
    def _build_with(self, rec):
        with TempPackage([FETCHED], [rec]) as pkg:
            return bs.build(pkg)

    def test_expected_claim_cannot_set_actual_state(self):
        for value in ("in_progress", "cancelled"):
            rec = copy.deepcopy(INTAKE)
            rec["claims"].append({"field": "status", "value": value, "source_id": "src-test-news",
                                  "claim_type": "expected", "quote": "работы будут вестись", "locator": "a"})
            with self.assertRaisesRegex(bs.IntakeError, "actual state"):
                self._build_with(rec)

    def test_geometry_claim_cannot_upgrade_approximate(self):
        rec = copy.deepcopy(INTAKE)
        rec.update(geometry={"type": "Point", "coordinates": [71.43, 51.17]}, geometry_precision="approximate",
                   geometry_basis="Точка по названию улицы.")
        rec["claims"].append({"field": "geometry", "value": None, "source_id": "src-test-news",
                              "claim_type": "stated", "quote": "ул. Условная", "locator": "a"})
        with self.assertRaisesRegex(bs.IntakeError, "contradicts"):
            self._build_with(rec)

    def test_geometry_basis_is_kept(self):
        rec = copy.deepcopy(INTAKE)
        rec.update(geometry={"type": "Point", "coordinates": [71.43, 51.17]}, geometry_precision="approximate",
                   geometry_basis="Точка у начала участка по названию улицы.")
        obj = self._build_with(rec)["objects.json"]["items"][0]
        self.assertIn("Геометрия: Точка у начала участка", obj["evidence_notes"])

    def test_amount_without_basis_claim_refused(self):
        rec = copy.deepcopy(INTAKE)
        rec["claims"] = [c for c in rec["claims"] if c["field"] != "budget.basis"]
        with self.assertRaisesRegex(bs.IntakeError, "budget.basis"):
            self._build_with(rec)

    def test_undated_source_gets_readiness_note(self):
        with TempPackage([dict(FETCHED, published_on=None)], [INTAKE]) as pkg:
            out = bs.build(pkg)
        notes = out["validation.json"]["public_readiness"][0]["notes"]
        self.assertTrue(any("no publication date" in n for n in notes))

    def test_bom_input_is_read_and_bad_json_is_intake_error(self):
        with TempPackage([FETCHED], [INTAKE]) as pkg:
            path = os.path.join(pkg, "intake", "real", "000.json")
            raw = open(path, "rb").read()
            open(path, "wb").write(b"\xef\xbb\xbf" + raw)
            bs.build(pkg)
            open(path, "wb").write(b"{broken")
            with self.assertRaisesRegex(bs.IntakeError, "invalid JSON"):
                bs.build(pkg)


import schedule_diff as sd  # noqa: E402


def _snap(text, published_on="2026-10-20"):
    return sd.make_snapshot(text, source_id="src-synthetic", url="https://example.org/synthetic",
                            retrieved_at="2026-10-21T08:00:00Z", published_on=published_on)


class DateRoles(unittest.TestCase):
    CASES = [
        ("Подрядчик не завершил работы к 30 сентября 2026 года, срок продлён до 1 декабря 2026 года.",
         [("unclassified", "2026-09-30"), ("expected_end", "2026-12-01")]),
        ("Работы, которые должны были быть завершены 30 сентября 2026 года, до сих пор не окончены.",
         [("expected_end", "2026-09-30")]),
        ("На 1 октября 2026 года работы завершены на 60%.", [("unclassified", "2026-10-01")]),
        ("Проект стартовал 1 мая 2026 года, открыт будет 1 декабря 2026 года.",
         [("start", "2026-05-01"), ("expected_end", "2026-12-01")]),
        ("Работы не завершены 30 сентября 2026 года.", [("unclassified", "2026-09-30")]),
        ("Работы будут завершены 30 ноября 2026 года.", [("expected_end", "2026-11-30")]),
        ("Срок сдачи перенесён с 30 сентября 2026 года на 1 декабря 2026 года.",
         [("previous_end", "2026-09-30"), ("expected_end", "2026-12-01")]),
        ("Работы по благоустройству начнутся 5 октября 2026 года.", [("start", "2026-10-05")]),
        ("Подрядчик приступит к работам 5 октября 2026 года.", [("start", "2026-10-05")]),
        ("По состоянию на 1 октября 2026 года готовность объекта составляет 80%.", [("unclassified", "2026-10-01")]),
        ("Работы, завершённые 1 октября 2026 года, приняты комиссией.", [("reported_actual_end", "2026-10-01")]),
        ("Ожидается, что объект будет сдан 1 ноября 2026 года.", [("expected_end", "2026-11-01")]),
    ]

    def test_roles(self):
        for text, expected in self.CASES:
            got = [(d["role"], d.get("value")) for d in sd.extract_dates(text)]
            self.assertEqual(got, expected, text)

    def test_impossible_date_is_invalid_not_day(self):
        d = sd.extract_dates("Работы завершены 31 сентября 2026 года.")[0]
        self.assertEqual(d["precision"], "invalid_date")
        r = sd.diff(_snap("Работы планируется завершить до 30 сентября 2026 года."),
                    _snap("Работы завершены 31 сентября 2026 года."))
        self.assertTrue(any(f["kind"] == "imprecise_date" for f in r["findings"]))

    def test_cross_year_range(self):
        d = sd.extract_dates("С 25 декабря по 15 января 2027 года на площади будет ледовый городок.")[0]
        self.assertEqual((d["start"], d["end"], d["precision"]), ("2026-12-25", "2027-01-15", "day"))


class SnapshotSplitting(unittest.TestCase):
    def test_numeric_dates_survive_and_change_is_found(self):
        old, new = _snap("Работы завершат до 30.10.2026."), _snap("Работы завершат до 30.11.2026.")
        self.assertEqual(old["excerpts"], ["Работы завершат до 30.10.2026."])
        r = sd.diff(old, new)
        self.assertTrue(any(f["kind"] == "changed" and f["new"] == "2026-11-30" for f in r["findings"]))

    def test_postponement_with_g_abbreviation(self):
        old = _snap("Работы планируется завершить до 30 сентября 2026 г.")
        new = _snap("Срок сдачи перенесён с 30 сентября 2026 г. на 1 декабря 2026 г.")
        r = sd.diff(old, new)
        changed = [f for f in r["findings"] if f["field"] == "schedule.current_planned_end"]
        self.assertEqual((changed[0]["old"], changed[0]["new"]), ("2026-09-30", "2026-12-01"))
        self.assertNotIn("schedule.planned_start", {f["field"] for f in r["findings"]})

    def test_snapshot_never_stores_whole_dense_notice(self):
        text = " ".join(f"Участок {i} закрыт до {i % 28 + 1} октября 2026 года." for i in range(60))
        s = _snap(text)
        self.assertTrue(s["truncated"])
        self.assertLessEqual(sum(len(e) for e in s["excerpts"]), sd.MAX_SNAPSHOT_CHARS)
        self.assertLess(sum(len(e) for e in s["excerpts"]), len(text))
        r = sd.diff(s, s)
        self.assertTrue(any(f["kind"] == "snapshot_truncated" for f in r["findings"]))

    def test_contacts_redacted_in_excerpts(self):
        s = _snap("Работы завершат до 30 октября 2026 года, справки по тел. 8 (7172) 55-12-34.")
        self.assertNotIn("55-12-34", " ".join(s["excerpts"]))
        self.assertIn("[контакт удалён]", " ".join(s["excerpts"]))



class RegistryHardening(unittest.TestCase):
    def test_license_text_cannot_back_a_civic_fact(self):
        lic = dict(FETCHED, role="license_text")
        with TempPackage([lic], [INTAKE]) as pkg:
            with self.assertRaisesRegex(bs.IntakeError, "not a publication about city works"):
                bs.build(pkg)

    def test_fetched_without_successful_attempt_is_flagged(self):
        bad = dict(FETCHED, id="src-bad", sha256="xyz", access_attempts=[{"outcome": "egress_denied"}])
        codes = {i["code"] for i in bs.registry_checks({"sources": [FETCHED, bad]})}
        self.assertIn("fetched_without_proof", codes)
        self.assertEqual(bs.registry_checks({"sources": [FETCHED]}), [])



class Round2DateRegressions(unittest.TestCase):
    """Second review round (fix diff e4ab1ff..01f89df): cases found by the dates finder."""

    def _diff(self, old, new, record=None, pub="2026-10-05"):
        r = sd.diff(_snap(old, pub), _snap(new, pub), record)
        return [(f["kind"], f["field"], f["old"], f["new"]) for f in r["findings"]], r

    def test_cue_does_not_leak_across_sentences(self):
        f, _ = self._diff("Ремонт планируется начать 1 сентября 2026 г. Работы завершены 20 сентября 2026 г.",
                          "Ремонт планируется начать 1 сентября 2026 г. Работы завершены 25 сентября 2026 г.")
        self.assertIn(("candidate_actual", "schedule.actual_end", None, "2026-09-25"), f)
        for text in ("Работы на первом участке завершены 15 сентября 2026 г. На втором участке приступят к работам 1 октября 2026 г.",
                     "Работы на первом участке ул. Сарайшық завершены. 1 октября 2026 года начался ремонт второго участка.",
                     "Ремонт завершён 30 сентября 2026 года. Қабанбай батыра проспект закроют с 3 октября 2026 года."):
            roles = {d.get("value"): d["role"] for d in sd.extract_dates(text)}
            self.assertNotEqual(roles.get("2026-10-01", roles.get("2026-10-03")), "reported_actual_end", text)

    def test_deadline_of_ordinary_article_survives_snapshot(self):
        tmpl = ("Акимат города Астаны сообщает о ремонте ул. Кенесары. Ремонт начнётся 1 октября 2026 года. "
                "Движение на участке будет ограничено с 1 по 20 октября 2026 года, объезд по ул. Иманова. "
                "Укладку покрытия выполнят с 21 октября по 5 ноября 2026 года. Работы планируется завершить до {} 2026 года.")
        f, _ = self._diff(tmpl.format("15 ноября"), tmpl.format("15 декабря"))
        self.assertIn(("changed", "schedule.current_planned_end", "2026-11-15", "2026-12-15"), f)

    def test_hard_wrapped_text(self):
        self.assertEqual(sd.split_sentences("Работы планируется завершить до 30\nоктября 2026 года."),
                         ["Работы планируется завершить до 30 октября 2026 года."])
        d = sd.extract_dates("Работы, которые должны\nбыли быть завершены 30 сентября 2026 года, продолжаются.")
        self.assertEqual(d[0]["role"], "expected_end")

    def test_other_postponement_wordings(self):
        for verb in ("переносится", "сдвигается", "откладывается"):
            text = f"Срок сдачи {verb} с 30 сентября 2026 года на 30 ноября 2026 года."
            self.assertEqual([(d["role"], d["value"]) for d in sd.extract_dates(text)],
                             [("previous_end", "2026-09-30"), ("expected_end", "2026-11-30")], text)

    def test_adjectives_are_not_modal(self):
        for text in ("Запланированный капитальный ремонт школы № 15 завершён 1 октября 2026 года.",
                     "По словам должностных лиц акимата работы завершены 1 октября 2026 года.",
                     "Ожидаемый жителями сквер открыт 2 октября 2026 года."):
            self.assertEqual(sd.extract_dates(text)[0]["role"], "reported_actual_end", text)

    def test_colon_dash_clauses(self):
        d = sd.extract_dates("Работы завершены с опозданием на месяц: по контракту срок был 30 августа 2026 года.")
        self.assertEqual(d[0]["role"], "previous_end")
        d = sd.extract_dates("Сквер открыт для посещения — 15 октября 2026 года начнётся второй этап.")
        self.assertEqual(d[0]["role"], "start")
        d = sd.extract_dates("Срок начала работ — 5 октября 2026 года.")
        self.assertEqual(d[0]["role"], "start")

    def test_closure_with_clock_times_is_a_period(self):
        d = sd.extract_dates("Движение будет перекрыто с 22:00 10 октября до 06:00 12 октября 2026 года.")
        self.assertEqual((d[0]["role"], d[0]["start"], d[0]["end"]), ("range", "2026-10-10", "2026-10-12"))

    def test_unclassified_change_reaches_editor(self):
        f, r = self._diff("Городской фестиваль пройдёт 12 октября 2026 года на набережной.",
                          "Городской фестиваль пройдёт 19 октября 2026 года на набережной.")
        self.assertIn(("unclassified_changed", None, ["2026-10-12"], ["2026-10-19"]), f)

    def test_quarter_and_half_year_are_imprecise(self):
        d = sd.extract_dates("Строительство планируется завершить во II квартале 2027 года.")
        self.assertEqual((d[0]["precision"], d[0]["month"]), ("quarter", "2027-Q2"))
        d = sd.extract_dates("Работы завершат до конца первого полугодия 2027 года.")
        self.assertEqual(d[0]["precision"], "half_year")
        f, _ = self._diff("Работы планируется завершить в IV квартале 2026 года.",
                          "Работы планируется завершить во II квартале 2027 года.")
        self.assertTrue(any(k == "imprecise_date" for k, *_ in f))

    def test_sloppy_range_is_invalid_not_a_year(self):
        d = sd.extract_dates("Перекрытие с 28 по 3 октября 2026 года.")[0]
        self.assertEqual(d["precision"], "invalid_date")

    def test_suspension_is_not_a_start(self):
        for text in ("Работы приостановлены с 1 октября 2026 года до особого распоряжения.",
                     "Ограничения сняты с 3 октября 2026 года.",
                     "Движение возобновлено с 3 октября 2026 года."):
            self.assertEqual(sd.extract_dates(text)[0]["role"], "unclassified", text)

    def test_odd_unicode_does_not_crash(self):
        sd.extract_dates("Работы завершат до 30 \u1c82ктября 2026 года.")
        sd.make_snapshot("Работы завершат до 30 \u1c82ктября 2026 года.", source_id="s", url="https://e.org/x",
                         retrieved_at="2026-10-06T08:00:00Z", published_on=None)

    def test_every_date_keeps_its_role_in_snapshot(self):
        text = ("Акимат сообщает. " + "Вводный текст без дат. " * 30 +
                "Ремонт начнётся 1 октября 2026 года, а завершить его планируется до 30 ноября 2026 года, "
                "при этом движение будет ограничено с 1 по 20 октября 2026 года и объезд организуют по соседним "
                "улицам района с учётом графика общественного транспорта и пожеланий жителей микрорайона.")
        full = {(d["role"], d.get("value") or (d.get("start"), d.get("end"))) for d in sd.extract_dates(text)}
        snap = _snap(text)
        kept = {(d["role"], d.get("value") or (d.get("start"), d.get("end")))
                for e in snap["excerpts"] for d in sd.extract_dates(e)}
        self.assertEqual(full, kept)
        self.assertFalse(snap["truncated"])



import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402

import import_helper as ih  # noqa: E402


class Round2ValidatorRegressions(unittest.TestCase):
    def test_budgets_and_bins_are_not_pii(self):
        for text in ("Стоимость строительства школы 7 500 000 000 тенге.", "Сумма договора 7 245 300 000 тг",
                     "Выделено 77 400 000 000 тенге", "Сметная стоимость 125000000000 тенге", "БИН 123456789012",
                     "до 7.10.2026 (120 календарных дней)"):
            self.assertEqual(cv.find_pii(text), [], text)
        self.assertTrue(cv.find_pii("IIN 900101300126"))  # unlabelled but a valid IIN checksum

    def test_hole_touching_shell_is_valid_on_every_side(self):
        shell = [[71.40, 51.10], [71.50, 51.10], [71.50, 51.20], [71.40, 51.20], [71.40, 51.10]]
        for touch in ([71.40, 51.15], [71.50, 51.15], [71.45, 51.20], [71.45, 51.10]):
            cx, cy = 71.45, 51.15
            hole = [touch, [cx + 0.01, cy + 0.01], [cx - 0.01, cy + 0.01], touch]
            if touch[1] == 51.20:
                hole = [touch, [cx + 0.01, cy - 0.01], [cx - 0.01, cy - 0.01], touch]
            geom = {"type": "Polygon", "coordinates": [shell, hole]}
            self.assertNotIn("geometry_hole_outside", errors(dict(CONTRACT_FIXTURE, geometry=geom)), touch)

    def test_company_names_with_ampersand_are_plain_text(self):
        for title in ("Демо: аудит Ernst&Young; приёмка в ноябре", "Демо: спонсор Procter&Gamble; вход свободный"):
            self.assertNotIn("text_html", errors(dict(CONTRACT_FIXTURE, title=title)), title)
        self.assertIn("text_html", errors(dict(CONTRACT_FIXTURE, title="Демо &laquo;Парк&raquo;")))

    def test_apostrophe_url_is_valid(self):
        self.assertIsNone(cv.check_url("https://en.wikipedia.org/wiki/People's_Square"))

    def test_out_of_window_timestamp_is_an_issue_not_a_crash(self):
        obj = real_record()
        obj["source_refs"][0]["retrieved_at"] = "0001-01-01T00:00:00+05:00"
        codes = {i["code"] for i in cv.validate_object(obj, profile="real", as_of=AS_OF, fence=FENCE)}
        self.assertIn("timestamp_format", codes)
        self.assertNotIn("validator_exception", codes)

    def test_long_line_is_warning_in_contract_profile(self):
        line = {"type": "LineString", "coordinates": [[71.25, 51.00], [71.75, 51.30], [71.25, 51.01]]}  # ~96 km
        self.assertIn(("geometry_too_long", "warning"), all_codes(dict(CONTRACT_FIXTURE, geometry=line), "contract"))
        self.assertIn("geometry_too_long", errors(dict(CONTRACT_FIXTURE, geometry=line), "demo"))

    def test_trailing_newline_id_rejected(self):
        self.assertIn("id_format", errors(dict(real_record(), id="ast-r05-test\n"), "real"))

    def test_r02_source_id_and_amount_limits(self):
        obj = real_record()
        obj["source_refs"][0]["id"] = "src:akimat/news#42"
        self.assertIn("source_ref_id_format", errors(obj, "real"))
        obj = real_record()
        obj["budget"] = {"amount_kzt": 25 * 10 ** 12, "basis": "planned", "source_id": "src-test"}
        obj["source_refs"][0]["fields"] += ["budget.amount_kzt", "budget.basis"]
        self.assertIn("budget_amount_limit", errors(obj, "real"))

    def test_cli_survives_surrogates_and_deep_nesting(self):
        d = tempfile.mkdtemp(prefix="r05cli-")
        try:
            sur = os.path.join(d, "s.json")
            open(sur, "w", encoding="utf-8").write(json.dumps(dict(CONTRACT_FIXTURE, id="demo-\ud800")))
            deep = os.path.join(d, "d.json")
            open(deep, "w", encoding="utf-8").write("[" * 100000 + "]" * 100000)
            for path, rc in ((sur, (0, 1)), (deep, (2,))):
                r = subprocess.run([sys.executable, "-I", os.path.join(PKG, "tools", "civic_v1.py"), path],
                                   capture_output=True, text=True, timeout=60)
                self.assertIn(r.returncode, rc, r.stderr[-300:])
                self.assertNotIn("Traceback", r.stderr)
        finally:
            shutil.rmtree(d)


def _copy_pkg():
    d = tempfile.mkdtemp(prefix="r05pkg2-")
    dst = os.path.join(d, "pkg")
    shutil.copytree(PKG, dst, ignore=shutil.ignore_patterns("__pycache__"))
    return d, dst


class Round2PipelineRegressions(unittest.TestCase):
    def test_r02_row_recipe_gives_editor_review(self):
        it = ih.load_package(PKG, include_demo=True)["items"][0]
        row = {"revision": 2, "import_revision": 1, "first_published_at": None, "publication": "draft"}
        edited = not (row["import_revision"] == row["revision"] and row["first_published_at"] is None)
        existing = {it["external_id"]: {"digest": "old", "publication": row["publication"],
                                        "edited_after_import": edited, "source": it["source"]}}
        self.assertEqual(ih.plan([it], existing)[0]["action"], "editor_review")

    def test_hand_edited_status_age_refused(self):
        d, pkg = _copy_pkg()
        try:
            path = os.path.join(pkg, "objects.json")
            data = json.load(open(path, encoding="utf-8"))
            data["slice"]["status_max_age_days"] = 100000
            json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False)
            with self.assertRaisesRegex(ih.PackageError, "does not match"):
                ih.load_package(pkg)
        finally:
            shutil.rmtree(d)

    def test_dot_files_are_ignored_and_new_demo_intake_is_stale(self):
        d, pkg = _copy_pkg()
        try:
            open(os.path.join(pkg, "intake", "real", "._ast-r05-x.json"), "wb").write(b"\x00\x05\x16\x07")
            ih.load_package(pkg, include_demo=True)  # AppleDouble file does not block the package
            open(os.path.join(pkg, "intake", "demo", "extra.json"), "w", encoding="utf-8").write('{"records": []}')
            with self.assertRaisesRegex(ih.PackageError, "intake/demo files differ"):
                ih.load_package(pkg, include_demo=True)
        finally:
            shutil.rmtree(d)

    def test_bad_historical_and_geofence_are_package_errors(self):
        d, pkg = _copy_pkg()
        try:
            open(os.path.join(pkg, "historical.json"), "w").write("[]")
            with self.assertRaises(ih.PackageError):
                ih.load_package(pkg)
        finally:
            shutil.rmtree(d)
        d, pkg = _copy_pkg()
        try:
            path = os.path.join(pkg, "geofence.json")
            raw = open(path, "rb").read()
            open(path, "wb").write(b"\xef\xbb\xbf" + raw)
            ih.load_package(pkg)            # BOM tolerated
            bs.build(pkg)
            open(path, "w").write("{}")
            with self.assertRaises(ih.PackageError):
                ih.load_package(pkg)
            with self.assertRaises(bs.IntakeError):
                bs.build(pkg)
        finally:
            shutil.rmtree(d)



class R02CharacterParity(unittest.TestCase):
    """R02 7d5e39a clean_text/clean_url/SOURCE_FIELD_PATHS: R05-valid must stay R02-importable."""

    def test_format_and_filler_characters(self):
        for title in ("Демо со\u00adмягким переносом", "Демо\u200dтекст", "\u3164\u3164", "Демо \ue000"):
            found = errors(dict(CONTRACT_FIXTURE, title=title))
            self.assertTrue(found & {"text_control_chars", "text_invisible"}, repr(title))
        self.assertNotIn("text_control_chars",
                         errors(dict(CONTRACT_FIXTURE, description="Демо.\u2028Вторая строка в описании.")))

    def test_invisible_characters_in_urls(self):
        for url in ("https://www.gov.kz/x\u00a0", "https://www.gov.kz/\u2060x", "https://www.gov.kz/\u202ex"):
            self.assertIsNotNone(cv.check_url(url), repr(url))

    def test_contract_field_paths_match_r02(self):
        obj = real_record()
        for path, ok in (("budget.source_id", True), ("evidence_type", True), ("schedule.foo", False)):
            obj["source_refs"][0]["fields"] = [path]
            self.assertEqual("source_ref_field_path" not in errors(obj, "contract"), ok, path)


if __name__ == "__main__":
    unittest.main()
