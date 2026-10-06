"""R10 independent acceptance of R09 agent/civic_assistant (round 11, Astana, civic-v1).

Expectations come from CONTRACT.txt (PACK 9c2f5c0, sections 1 and 6) and prompts/R09.txt,
not from the R09 implementation. Product code runs only inside r09_driver.py, started here as
    python3 -I -B r09_driver.py <R10_R09_ROOT> <pack fixture>     (cwd = R10_R09_ROOT)
and this file asserts on the JSON it prints.

    R10_R09_ROOT=<detached worktree of the pinned R09 SHA> \
    [R10_R09_SHA=<expected full sha>] python3 -I -B -m unittest standalone_r09 -v

Without R10_R09_ROOT every test is skipped with "NOT_RUN: ...".
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.join(HERE, "r09_driver.py")
FIXTURE = os.path.normpath(os.path.join(HERE, "..", "fixtures", "pack_civic_object.json"))
PACK_FIXTURE_SHA256 = "e2ba1de7d263f69629d12c01dea35c774f0be321a1fb9f7685787c33caad88f2"  # 9c2f5c0:fixtures/civic_object.json
ROOT = os.environ.get("R10_R09_ROOT")
EXPECTED_SHA = os.environ.get("R10_R09_SHA")

# Facts R10 put into the contexts (own knowledge of own inputs, not read back from the product).
PACK_DATES = {"2026-10-14", "2026-10-20", "2026-10-22"}
UPDATED_AT_DATE = "2026-10-06"
H2_AT, H1_AT = "2026-10-05", "2026-10-01"
TODAY = "2026-10-06"
SHIFT_DAYS = 2  # 2026-10-22 minus 2026-10-20

OBS: dict = {}
RUN: dict = {}

MONTHS = {m: i + 1 for i, m in enumerate(
    ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
     "ноября", "декабря"))}
MONTHS.update({m: i + 1 for i, m in enumerate(
    ("қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан",
     "қараша", "желтоқсан"))})
_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
SYNTH_RE = re.compile(r"синтетич|демонстрацион|синтетикалық|демонстрациялық|synthetic", re.I)
UNKNOWN_RE = re.compile(r"нет данных|не указан|неизвест|деректер жоқ|көрсетілмеген|белгісіз|unknown", re.I)
COMPLETION_RE = re.compile(r"законч|заверш|сдан[аоы]?\b|аяқталды|аяқталған|бітт", re.I)
NEGATION_RE = re.compile(r"(?<!\w)(не|нет|ни)(?!\w)|емес|жоқ|білдірмейді|расталмаған", re.I)
ORG_RE = re.compile(r"акимат|ТОО|\bАО\b|\bГУ\b|КГУ|управлени[ея] |компани|ИП ", re.I)


def extract_dates_numbers(text: str):
    """Return (set of ISO dates, list of other numbers) mentioned in text."""
    dates = set()
    rest = text

    def iso(m):
        dates.add(m.group(1))
        return " "
    rest = re.sub(r"(\d{4}-\d{2}-\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?", iso, rest)

    def dmy(m):
        dates.add(f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}")
        return " "
    rest = re.sub(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)", dmy, rest)

    def word(m):
        dates.add(f"{int(m.group(3)):04d}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}")
        return " "
    rest = re.sub(r"(?<!\d)(\d{1,2})\s+(" + _MONTH_RE + r")\w*\s+(\d{4})", word, rest, flags=re.I)

    def kk(m):  # "2026 жылғы 22 қазан"
        dates.add(f"{int(m.group(1)):04d}-{MONTHS[m.group(3).lower()]:02d}-{int(m.group(2)):02d}")
        return " "
    rest = re.sub(r"(\d{4})\s+жылғы\s+(\d{1,2})\s+(" + _MONTH_RE + r")\w*", kk, rest, flags=re.I)
    nums = [re.sub(r"[\s  ]", "", n).replace(",", ".")
            for n in re.findall(r"\d+(?:[   ]\d{3})*(?:[.,]\d+)?", rest)]
    return dates, nums


def _clean_env():
    tmp = tempfile.mkdtemp(prefix="r10-r09-env-")
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "HOME": tmp, "TMPDIR": tmp}, tmp


def _git(*args):
    p = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True)
    return p.stdout.strip()


def setUpModule():  # noqa: N802
    if not ROOT:
        raise unittest.SkipTest("NOT_RUN: R10_R09_ROOT is not set (path to a detached worktree of the pinned R09 SHA)")
    if not os.path.isfile(os.path.join(ROOT, "agent", "civic_assistant", "__init__.py")):
        raise unittest.SkipTest(f"NOT_RUN: agent/civic_assistant not found under {ROOT}")
    with open(FIXTURE, "rb") as fh:
        RUN["fixture_sha256"] = hashlib.sha256(fh.read()).hexdigest()
    RUN["sha"] = _git("rev-parse", "HEAD")
    RUN["status_before"] = _git("status", "--porcelain", "--untracked-files=all")
    env, tmp = _clean_env()
    cmd = [sys.executable, "-I", "-B", DRIVER, ROOT, FIXTURE]
    RUN["cmd"] = " ".join(cmd)
    proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    RUN["exit"] = proc.returncode
    RUN["stderr"] = proc.stderr
    RUN["status_after"] = _git("status", "--porcelain", "--untracked-files=all")
    RUN["env_tmp_entries"] = sorted(os.listdir(tmp))
    try:
        OBS.update(json.loads(proc.stdout.strip().splitlines()[-1]))
    except (ValueError, IndexError):
        OBS["_driver_error"] = (proc.stderr or proc.stdout)[-3000:]


def sc(name):
    return OBS["scenarios"][name]


def ans(name):
    s = sc(name)
    assert s and s.get("ok"), f"{name}: no answer ({s and s.get('error')})"
    return s["answer"]


def object_answers():
    """Scenario names that returned an answer about the published object."""
    out = []
    for k, v in OBS["scenarios"].items():
        if v and v.get("ok") and v["answer"]["source"] != "unavailable":
            out.append(k)
    return out


class R09Standalone(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        if "_driver_error" in OBS or not OBS:
            self.fail("driver produced no JSON: " + OBS.get("_driver_error", "")[-1500:])

    # ------------------------------------------------------------------ process / isolation
    def test_00_isolation_and_pin(self):
        """[M03][D02] product imported only from the pinned worktree, python -I -B, no writes to the worktree."""
        m = OBS["meta"]
        self.assertEqual(RUN["exit"], 0, RUN["stderr"][-800:])
        self.assertEqual(RUN["fixture_sha256"], PACK_FIXTURE_SHA256, "R10 fixture differs from PACK fixture")
        if EXPECTED_SHA:
            self.assertEqual(RUN["sha"], EXPECTED_SHA)
        self.assertEqual(m["isolated_flag"], 1)
        self.assertEqual(m["dont_write_bytecode"], 1)
        self.assertEqual(os.path.realpath(m["sys_path0"]), os.path.realpath(ROOT))
        self.assertEqual(os.path.realpath(m["cwd"]), os.path.realpath(ROOT))
        for name, path in m["module_files"].items():
            self.assertTrue(os.path.realpath(path).startswith(os.path.realpath(ROOT) + os.sep), (name, path))
        self.assertEqual(RUN["status_before"], "", "worktree was not clean before the run")
        self.assertEqual(RUN["status_after"], "", "product run changed files in the worktree")
        self.assertEqual(m["tmpdir_entries"], [])
        self.assertEqual(RUN["env_tmp_entries"], [])

    # ------------------------------------------------------------------ template path
    def test_01_no_provider_is_never_llm(self):
        """[M03] provider=None -> source 'template' for every object question (never 'llm')."""
        names = [k for k in OBS["scenarios"] if k.startswith(("tpl_", "miss_", "two_", "r02_", "priv_", "inj_",
                                                               "html_")) and not k.endswith("_llm")
                 and not k.startswith("inj_llm")]
        self.assertGreaterEqual(len(names), 25)
        for k in names:
            a = ans(k)
            self.assertEqual(a["source"], "template", k)
            self.assertFalse(str(a.get("mode", "")).startswith("llm"), (k, a.get("mode")))

    def test_02_dates_and_numbers_only_from_facts(self):
        """[M03][C03] every date/number in answer text exists in the verified facts (or is the derived 2-day shift)."""
        allowed_dates = {
            "base": PACK_DATES | {UPDATED_AT_DATE, H2_AT},
            "missing": {"2026-10-14", UPDATED_AT_DATE},
            "two": PACK_DATES | {UPDATED_AT_DATE, H1_AT, H2_AT},
            "r02": PACK_DATES | {UPDATED_AT_DATE, H1_AT, H2_AT},
        }
        allowed_nums = {"base": {"2"}, "missing": {"2"}, "two": {"1", "2"}, "r02": {"2", "4"}}
        groups = {"tpl_": "base", "p1_": "base", "p2_": "base", "p3_": "base", "p4_": "base", "p5_": "base",
                  "pool_": "base", "html_question": "base", "priv_": "base", "miss_": "missing", "two_": "two",
                  "r02_": "r02"}
        checked = 0
        for k, v in OBS["scenarios"].items():
            g = next((grp for pre, grp in groups.items() if k.startswith(pre)), None)
            if g is None or not v or not v.get("ok"):
                continue
            text = v["answer"]["text"].replace(OBS["meta"]["reason"], " ")
            dates, nums = extract_dates_numbers(text)
            self.assertLessEqual(dates, allowed_dates[g], (k, text))
            self.assertLessEqual(set(nums), allowed_nums[g], (k, nums, text))
            for n in nums:  # the only free number in these answers is the revision or the 2-day shift
                self.assertIn(int(float(n)), {1, 2, 4}, (k, text))
            checked += 1
        self.assertGreaterEqual(checked, 40)
        # derived shift is computed correctly from the facts, not invented
        self.assertRegex(ans("tpl_schedule")["text"], rf"(?<!\d){SHIFT_DAYS}(?!\d)\s*дн")

    def test_03_unknown_budget_not_zero(self):
        """[C03][M03] budget.amount_kzt=null is stated as unknown; never 0 or an invented amount (RU, KK, llm path)."""
        for k in ("tpl_budget", "tpl_kk_budget", "p2_valid_budget", "p2_text_key"):
            t = ans(k)["text"]
            self.assertRegex(t, UNKNOWN_RE, k)
            self.assertNotRegex(t, r"(?<![\d.])0(?![\d.])", k)
            self.assertNotRegex(t, r"\d\s*(₸|тенге|теңге|KZT)", k)
            self.assertNotIn("проверен", t.lower(), k)

    def test_04_unknown_responsible_not_invented(self):
        """[C03][M03] responsible.organization/public_contact null -> 'no data', no invented organisation."""
        for k in ("tpl_responsible", "tpl_kk_responsible", "priv_responsible", "priv_llm"):
            t = ans(k)["text"]
            self.assertRegex(t, UNKNOWN_RE, k)
            self.assertNotRegex(t, ORG_RE, k)
            self.assertNotIn("@", t, k)

    def test_05_missing_deadline_says_no_data(self):
        """[C03][M03] current/original end null -> 'no data'; no invented or today's date; no shift number."""
        for k in ("miss_schedule", "miss_schedule_kk", "miss_delay", "miss_done"):
            t = ans(k)["text"]
            dates, nums = extract_dates_numbers(t)
            self.assertLessEqual(dates, {"2026-10-14"}, (k, t))  # only the known planned_start may appear
            self.assertNotIn(TODAY, dates, k)
            self.assertEqual(nums, [], (k, t))
        for k in ("miss_schedule", "miss_schedule_kk"):
            self.assertRegex(ans(k)["text"], UNKNOWN_RE, k)

    def test_06_synthetic_visible_in_every_answer(self):
        """[M03][C03] evidence_type=synthetic is visible in the text of every object answer (template, llm, fallback)."""
        names = object_answers()
        self.assertGreaterEqual(len(names), 45)
        missing = [k for k in names if not SYNTH_RE.search(ans(k)["text"])]
        self.assertEqual(missing, [])

    def test_07_planned_is_not_completed(self):
        """[M03][C03] status=planned, actual_end=null: 'already finished?' gets no completion claim and no actual date."""
        for k in ("tpl_done", "miss_done", "tpl_overview", "tpl_schedule", "tpl_kk_schedule"):
            t = ans(k)["text"]
            for sentence in re.split(r"(?<=[.!?»])\s+", t):
                if COMPLETION_RE.search(sentence):
                    self.assertRegex(sentence, NEGATION_RE, (k, sentence))
            m = re.search(r"Фактическ[^:]*:\s*([^.]+)", t)
            if m:
                self.assertRegex(m.group(1), UNKNOWN_RE, (k, t))
        self.assertRegex(ans("tpl_done")["text"], r"запланир|не подтвержд", "status/plan caveat missing")

    # ------------------------------------------------------------------ history reason
    def test_08_delay_reason_from_single_public_history_entry(self):
        """[M03][A04] PACK object (orig 2026-10-20 -> current 2026-10-22) + one public history entry with reason:
        'why was it moved?' must quote that reason, not claim the reason is missing."""
        reason = OBS["meta"]["reason"]
        t = ans("tpl_delay")["text"]
        self.assertIn(reason, ans("tpl_history_kw")["text"], "control: reason is in the verified context")
        self.assertIn(reason, t, "delay answer: " + t)

    def test_09_delay_reason_control_histories(self):
        """[M03][A04] control: with an earlier publication entry (generic and R02-shaped history) the reason is quoted."""
        reason = OBS["meta"]["reason"]
        for k in ("two_delay", "r02_delay"):
            t = ans(k)["text"]
            self.assertIn(reason, t, k)
            self.assertNotIn("Первичная публикация", t, k)
            self.assertNotIn("Первая публикация", t, k)

    # ------------------------------------------------------------------ fake providers
    def test_10_provider_unknown_fact_ids_rejected(self):
        """[M03] (1) provider returns fact ids absent from the catalog -> rejected with warning, template answer."""
        a = ans("p1_unknown_ids")
        self.assertEqual(sc("p1_unknown_ids")["provider_calls"], 1)
        self.assertEqual(a["source"], "template")
        self.assertTrue(a["warnings"], "no warning about rejected provider output")
        self.assertEqual(a["text"], ans("tpl_schedule")["text"])
        self.assertNotIn("schedule.real_end_2027", a["fact_ids"])
        self.assertNotIn("2027", a["text"])

    def test_11_provider_cannot_inject_numbers_or_dates(self):
        """[M03] (2) provider adds a date/amount/free text -> not used; numbers in final text only from facts."""
        for k in ("p2_extra_keys", "p2_free_text", "p2_text_key"):
            a = ans(k)
            self.assertNotEqual(a["source"], "llm", k)
            self.assertTrue(a["warnings"], k)
            for bad in ("2027", "15.03", "987", "официально", "одобрен"):
                self.assertNotIn(bad, a["text"], (k, bad))
        for k in ("p2_valid_schedule", "p2_valid_budget", "p2_valid_overview"):
            a = ans(k)
            self.assertEqual(a["source"], "llm", k)
            dates, nums = extract_dates_numbers(a["text"])
            self.assertLessEqual(dates, PACK_DATES, k)
            self.assertLessEqual(set(nums), {"2"}, k)

    def test_12_no_fetch_shell_sql_or_writes(self):
        """[M03][S11] instructions/URLs in provider output, question and verified context cause no fetch/shell/SQL/write."""
        self.assertTrue(OBS["meta"]["canary_selftest"], "canary listener positive control failed")
        self.assertTrue(OBS["meta"]["hook_selftest"], "audit hook positive control failed")
        self.assertEqual(OBS["canary_hits"], [], "loopback canary was contacted")
        self.assertEqual(OBS["audit_events"], [], "network/subprocess/sqlite/file-write audit events during product calls")
        for k in ("p3_fetch_text", "p3_fetch_json"):
            self.assertNotEqual(ans(k)["source"], "llm", k)
        # instructions inside the card are only quoted as data, never executed or turned into claims
        t = ans("inj_overview")["text"]
        non_quote = re.sub(r"«[^»]*»", " ", t)
        self.assertNotRegex(non_quote, r"одобрен|опубликован|publish", t)

    def test_13_provider_failure_is_not_fabricated(self):
        """[M03] (4) provider raises / times out / returns None -> template|unavailable with warning; no secret leak."""
        secret = OBS["meta"]["secret_marker"]
        for k in ("p4_raises", "p4_timeout", "p4_returns_none"):
            a = ans(k)
            self.assertIn(a["source"], ("template", "unavailable"), k)
            self.assertTrue(a["warnings"], k)
            self.assertNotIn(secret, json.dumps(a, ensure_ascii=False), k)
        self.assertNotIn(secret, RUN["stderr"], "secret from provider exception reached the log")
        self.assertLess(sc("p4_timeout")["elapsed"], 1.5, "timeout_s=0.3 not honoured")

    def test_14_provider_base_exception_does_not_escape(self):
        """[M03] (4b) provider raising asyncio.CancelledError (BaseException, common in async SDKs) -> template fallback,
        not an exception out of build_answer (would become a 500 in POST /assistant)."""
        s = sc("p4_base_exception")
        self.assertTrue(s["ok"], f"exception escaped build_answer: {s.get('error')}")
        self.assertNotEqual(s["answer"]["source"], "llm")

    def test_15_source_label_honesty(self):
        """[M03] (5) source matches the real path: provider claims of source/text are rejected; 'llm' only when a
        provider was actually called and its choice accepted."""
        for k in ("p5_claims_llm_text", "p5_claims_llm_choice"):
            a = ans(k)
            self.assertEqual(a["source"], "template", k)
            self.assertEqual(a["text"], ans("tpl_schedule")["text"], k)
        self.assertEqual(ans("p5_named_template")["source"], "llm", "provider named 'template' is still the llm path")
        for k, v in OBS["scenarios"].items():
            if v and v.get("ok") and v["answer"]["source"] == "llm":
                self.assertEqual(v.get("provider_calls"), 1, k)
                self.assertFalse([w for w in v["answer"]["warnings"] if w.startswith("provider_") and
                                  w != "provider_overridden_unsupported"], k)

    def test_16_overridden_model_choice_not_labelled_llm(self):
        """[M03] when the safety rule discards the model's choice and returns the fixed template refusal,
        the answer should not be labelled source='llm' (BRIEF: 'нельзя шаблон как ответ LLM')."""
        a = ans("p5_override_unsupported")
        self.assertEqual(a["intent"], "unsupported")
        self.assertNotEqual(a["source"], "llm", f"template refusal labelled llm; warnings={a['warnings']}")

    def test_17_html_is_plain_text(self):
        """[S10][M03] HTML/script in the question is not reflected; in card text it stays literal plain text
        (module returns text only; UI rendering NOT_RUN: web/civic/assistant absent at this SHA)."""
        a = ans("html_question")
        dump = json.dumps(a, ensure_ascii=False)
        self.assertNotIn("<script", dump)
        self.assertNotIn("onerror", dump)
        d = ans("html_description")
        self.assertFalse({k for k in d if "html" in k.lower()}, "answer exposes an HTML field")
        for st in d["statements"]:
            self.assertIsInstance(st["text"], str)
        self.assertFalse(os.path.isdir(os.path.join(ROOT, "web", "civic", "assistant")),
                         "UI exists now: run browser check U10 for it")

    def test_18_private_fields_never_reach_answer_or_provider(self):
        """[S09][M03] internal_notes/password_hash/author contact/session/editor login never reach context,
        answer text or provider request."""
        markers = OBS["meta"]["private_markers"]
        blobs = {"context": OBS["contexts"]["private"]["dump"] or ""}
        for k, v in OBS["scenarios"].items():
            if k.startswith("priv_") and v:
                blobs[k] = json.dumps(v, ensure_ascii=False)
        self.assertGreaterEqual(len(blobs), 6)
        for where, blob in blobs.items():
            for mk in markers:
                self.assertNotIn(mk, blob, (where, mk))

    def test_19_context_gate(self):
        """[A02][M03] draft/archived refused for public audience; tampered, absent or client-shaped context -> unavailable."""
        for pub in ("draft", "archived"):
            c = OBS["contexts"][pub]
            self.assertFalse(c["ok"], pub)
            self.assertIsNone(sc(pub + "_public_ask"))
        for k in ("ctx_tampered", "ctx_none", "ctx_client_shape"):
            a = ans(k)
            self.assertEqual(a["source"], "unavailable", k)
            self.assertNotIn("2030", a["text"], k)
            self.assertEqual(a["fact_ids"], [], k)

    def test_20_hung_provider_calls_do_not_starve_others(self):
        """[M03] after several provider calls that time out but keep hanging, a provider that answers at once
        is still called (shared pool must not be exhausted by abandoned calls)."""
        for i in range(5):
            self.assertEqual(ans(f"pool_hung_{i}")["source"], "template")
        self.assertEqual(ans("pool_fast_after_release")["source"], "llm", "control: provider works when idle")
        s = sc("pool_fast_while_hung")
        self.assertEqual(s["provider_calls"], 1,
                         f"instant provider never called; source={s['answer']['source']} "
                         f"warnings={s['answer']['warnings']} elapsed={s['elapsed']}s")

    def test_21_common_questions_routed(self):
        """[M03] R09 prompt key questions in plain wording: 'Откуда эти данные?' must speak about sources;
        'Что менялось в карточке?' must speak about history (template classifier)."""
        with self.subTest("sources"):
            a = ans("tpl_sources")
            self.assertRegex(a["text"], r"[Ии]сточник", f"intent={a['intent']} warnings={a['warnings']}")
        with self.subTest("history"):
            a = ans("tpl_history")
            self.assertRegex(a["text"], r"[Рр]евизи|истори|изменен", f"intent={a['intent']} warnings={a['warnings']}")
        with self.subTest("control: keyword wording works"):
            self.assertRegex(ans("tpl_sources_kw")["text"], r"источник")
            self.assertRegex(ans("tpl_history_kw")["text"], r"Ревизия 2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
