"""R10 standalone acceptance of R06 ui/civic_feedback at a pinned SHA.

Usage (stdlib unittest only):
    R10_R06_ROOT=<detached worktree of R06 SHA> [R10_R06_SHA=<full sha>] \
        python3 -I -B -m unittest -v standalone_r06      (cwd = this directory)
  or  python3 -I -B standalone_r06.py

Without R10_R06_ROOT every test is skipped with "NOT_RUN: ...".
Product code runs only inside a subprocess: python3 -I -B r06_driver.py <root>
(cwd = root, sys.path[0] = root, DB in tempfile.mkdtemp()). The driver prints raw
observations; the expectations below are derived from CONTRACT civic-v1 (PACK 9c2f5c0)
section 2-3 and prompts/R06.txt "ПРИЁМКА", not from R06's implementation choices.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest

ENV_ROOT, ENV_SHA = "R10_R06_ROOT", "R10_R06_SHA"
HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.join(HERE, "r06_driver.py")
_CACHE: dict = {}

FORBIDDEN_PUBLIC_KEYS = {
    "receipt_id", "client_hash", "client_ip", "ip", "moderated_by", "moderation_reason", "reason",
    "actor", "antispam", "classifier", "personal_data_hints", "text_fingerprint", "client_request_id",
    "email", "phone", "csrf_token", "consent_withdrawn_at", "similar", "password_hash", "internal_notes",
}
TRACE_PATTERNS = (re.compile(r"Traceback \(most recent call last\)"), re.compile(r'File "[^"]+", line \d+'),
                  re.compile(r"sqlite3?\.", re.I), re.compile(r"\b\w+Error\b"), re.compile(r"/tmp/|/home/|\.py\b"))


def _keys(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield key
            yield from _keys(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _keys(value)


def run_driver() -> dict:
    if "r" in _CACHE:
        return _CACHE["r"]
    root = os.environ.get(ENV_ROOT)
    if not root:
        raise unittest.SkipTest(f"NOT_RUN: {ENV_ROOT} is not set (path to detached worktree of R06 SHA)")
    root = os.path.realpath(root)
    if not os.path.isfile(os.path.join(root, "ui", "civic_feedback", "service.py")):
        raise unittest.SkipTest(f"NOT_RUN: {root} has no ui/civic_feedback/service.py")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    proc = subprocess.run([sys.executable, "-I", "-B", DRIVER, root], cwd=root, env=env,
                          capture_output=True, text=True, timeout=300)
    head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"driver exit {proc.returncode}: {proc.stderr[-2000:]}")
    data = json.loads(proc.stdout)
    data["meta"]["git_head"] = head.stdout.strip() if head.returncode == 0 else None
    data["meta"]["driver_exit"] = proc.returncode
    _CACHE["r"] = data
    return data


class R06Standalone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run_driver()
        cls.C = cls.R["checks"]
        if os.environ.get("R10_VERBOSE"):
            print(json.dumps(cls.R["meta"], indent=1), file=sys.stderr)

    def check(self, name):
        if name in self.R.get("driver_errors", {}):
            self.fail(f"driver error in {name}: {self.R['driver_errors'][name]}")
        self.assertIn(name, self.C, f"scenario {name} missing")
        return self.C[name]

    def assertStatus(self, rec, allowed, msg=""):
        self.assertIsNone(rec.get("exception"), f"{msg}: handle() raised {rec.get('exception')}: {rec.get('exception_text')}")
        self.assertIn(rec.get("status"), allowed, f"{msg}: got {rec.get('status')} {rec.get('code')} {rec.get('raw', '')[:300]}")

    # ------------------------------------------------------------------ meta
    def test_00_pinned_sha_and_isolation(self):
        """[META] product imported from the pinned worktree, -I -B, sys.path[0]=root."""
        meta = self.R["meta"]
        root = os.path.realpath(os.environ[ENV_ROOT])
        self.assertTrue(meta["module_file"].startswith(root + os.sep), meta["module_file"])
        self.assertEqual(meta["sys_path0"], root)
        self.assertTrue(meta["flags_isolated"])
        self.assertTrue(meta["dont_write_bytecode"])
        if os.environ.get(ENV_SHA):
            self.assertEqual(meta["git_head"], os.environ[ENV_SHA])

    # ------------------------------------------------------------------ A07 / A08
    def test_a07_receipt_has_no_personal_echo(self):
        """[A07][S09] receipt = {receipt_id, moderation:"pending"} without text/contact/ip echo."""
        c = self.check("receipt")
        self.assertStatus(c["submit"], (200, 201), "submit")
        self.assertEqual(c["moderation"], "pending")
        self.assertTrue(isinstance(c["receipt_id"], str) and c["receipt_id"])
        raw = c["submit"]["raw"]
        for secret in (c["marker"], c["email"], c["phone_text"], c["phone_digits"], c["ip"]):
            self.assertNotIn(secret, raw, f"receipt echoes {secret!r}")
        self.assertNotEqual(c["official_registration"], True, "must not claim official registration")

    def test_a08_pending_not_public(self):
        """[A08] a pending message is absent from GET /objects/{id}/feedback."""
        c = self.check("receipt")
        self.assertStatus(c["public_pending"], (200,), "public list")
        self.assertNotIn(c["marker"], c["public_pending"]["raw"])

    def test_a08_approve_with_consent_visible_with_reply(self):
        """[A08][S09] approve + consent -> text and public_reply visible; no staff/private fields leak."""
        c = self.check("approve_consent")
        self.assertStatus(c["moderate"], (200,), "approve")
        pub = c["public"]
        self.assertStatus(pub, (200,), "public list")
        self.assertIn(c["marker"], pub["raw"])
        self.assertIn(c["reply"], pub["raw"])
        for value in (c["reason"], c["editor"], c["ip"], c["csrf"], c["receipt_id"]):
            self.assertNotIn(value, pub["raw"], f"public list leaks {value!r}")
        leaked = FORBIDDEN_PUBLIC_KEYS & set(_keys(c["public_body"]))
        self.assertFalse(leaked, f"public DTO has non-allowlisted keys {sorted(leaked)}")

    def test_a08_approve_without_consent_text_absent(self):
        """[A08] approve without consent_public -> text (and reply) absent from raw public JSON."""
        c = self.check("approve_no_consent")
        self.assertStatus(c["submit"], (200, 201), "submit")
        self.assertIsNotNone(c["moderate"], "message not found in staff queue")
        self.assertStatus(c["public"], (200,), "public list")
        self.assertNotIn(c["marker"], c["public"]["raw"])
        self.assertNotIn(c["reply"], c["public"]["raw"])

    def test_a08_reject_invisible_and_retained(self):
        """[A08] reject -> invisible publicly, still in staff queue; approved-then-rejected disappears."""
        c = self.check("reject")
        self.assertStatus(c["moderate"], (200,), "reject")
        self.assertNotIn(c["marker"], c["public"]["raw"])
        self.assertEqual(c["still_in_staff_queue"], 1, "rejected message must not be deleted")
        self.assertEqual(c["staff_moderation_after"], "rejected")
        self.assertIn(c["marker2"], c["public_mid"]["raw"], "precondition: approved message visible")
        self.assertStatus(c["reject2"], (200,), "re-reject")
        self.assertNotIn(c["marker2"], c["public_end"]["raw"])

    def test_s09_author_contacts_never_published(self):
        """[S09] approve of a consented text containing e-mail/phone never publishes the contact."""
        c = self.check("receipt")
        self.assertIsNotNone(c["approve_with_contacts"], "message not found in staff queue")
        self.assertIsNone(c["approve_with_contacts"].get("exception"))
        raw = c["public_after_approve"]["raw"]
        for secret in (c["email"], c["phone_text"], c["phone_digits"]):
            self.assertNotIn(secret, raw)

    def test_a08_consent_withdrawal_removes_public_text(self):
        """[A08] withdrawn consent -> no public card (R06 extension; NOT_RUN if absent)."""
        c = self.check("withdraw")
        if c["withdraw"].get("none") or c["withdraw"].get("status") == 404 and c["withdraw"].get("code") == "not_found":
            self.skipTest("NOT_RUN: consent withdrawal endpoint not implemented")
        self.assertIn(c["marker"], c["public_before"]["raw"], "precondition: approved+consent visible")
        self.assertStatus(c["withdraw"], (200,), "withdraw")
        self.assertNotIn(c["marker"], c["public_after"]["raw"])
        self.assertStatus(c["forged"], (400, 404, 422), "forged receipt")

    # ------------------------------------------------------------------ S12 / S07
    def test_s12_moderation_only_editor_with_csrf_and_origin(self):
        """[S12][S07][S04] anon->401, logged-out->401, fake/resident role->403, no/bad CSRF or cross-origin->403; no state change."""
        c = self.check("authz")
        cases = c["cases"]
        self.assertTrue(c["found"])
        self.assertStatus(cases["anon"], (401,), "anonymous moderate")
        self.assertStatus(cases["logged_out"], (401,), "logged-out principal")
        self.assertStatus(cases["anon_body_role"], (401,), "anonymous with role in body")
        self.assertStatus(cases["resident"], (403,), "resident role")
        self.assertStatus(cases["resident_body_role"], (400, 403), "resident + role editor in body")
        self.assertStatus(cases["editor_no_csrf"], (403,), "editor without CSRF")
        self.assertStatus(cases["editor_bad_csrf"], (403,), "editor wrong CSRF")
        self.assertStatus(cases["editor_cross_origin"], (403,), "editor is_same_origin False")
        self.assertStatus(cases["queue_anon"], (401,), "anonymous staff queue")
        self.assertStatus(cases["queue_resident"], (403,), "resident staff queue")
        self.assertEqual(c["after"], {"moderation": "pending", "revision": c["rev_before"]}, "state changed")
        self.assertNotIn(c["marker"], c["public"]["raw"])

    def test_c04_stale_revision_409_without_change(self):
        """[C04][A08] stale expected_revision -> 409; decision, reply and revision unchanged."""
        c = self.check("stale")
        self.assertStatus(c["first"], (200,), "first decision")
        self.assertStatus(c["stale"], (409,), "stale decision")
        self.assertEqual(c["after"], c["mid"], "stale request changed stored state")
        self.assertIn(c["reply_a"], c["public"]["raw"])
        self.assertNotIn(c["reply_b"], c["public"]["raw"])

    def test_s07_unknown_fields_with_role_never_grant_rights(self):
        """[S07][C02] submit with role/actor/moderation/revision/public_text -> rejected or ignored, never published."""
        c = self.check("unknown_fields")
        self.assertIsNone(c["submit"].get("exception"))
        status = c["submit"]["status"]
        self.assertTrue(400 <= status < 500 or status in (200, 201), status)
        if status in (200, 201):
            self.assertEqual(c["moderation_after"], "pending")
            self.assertEqual(c["revision_after"], 1)
        self.assertNotIn(c["marker"], c["public"]["raw"])

    # ------------------------------------------------------------------ S14
    def test_s14_draft_and_nonexistent_indistinguishable(self):
        """[S14] feedback to draft/archived vs nonexistent id: identical error; no title leak; nothing stored."""
        c = self.check("object_privacy")
        for kind in ("submit", "public"):
            draft, nope, arch = c[f"{kind}_draft"], c[f"{kind}_nonexistent"], c[f"{kind}_archived"]
            self.assertStatus(nope, range(400, 500), f"{kind} nonexistent")
            self.assertEqual((draft["status"], draft["code"]), (nope["status"], nope["code"]), kind)
            self.assertEqual(c[f"{kind}_draft_error"], c[f"{kind}_nonexistent_error"], f"{kind} body differs")
            self.assertEqual((arch["status"], arch["code"]), (nope["status"], nope["code"]), f"{kind} archived")
            for rec in (draft, arch):
                self.assertNotIn(c["draft_title"], rec["raw"])
                self.assertNotIn(c["arch_title"], rec["raw"])
        self.assertEqual(c["rows_created"], 0)
        for kind in ("submit", "public"):
            rec = c[f"{kind}_lookup_raises"]
            self.assertIsNone(rec.get("exception"))
            self.assertGreaterEqual(rec["status"], 400)
            self.assertNotIn("R10-LOOKUP-SECRET", rec["raw"])

    # ------------------------------------------------------------------ C06 / C07
    def test_c06_location_rules(self):
        """[C06] no object & no geometry, outside Astana, swapped lon/lat, object far from point -> 4xx; valid -> 201."""
        c = self.check("location")
        for name in ("neither", "outside_astana", "swapped_lonlat", "far_from_object"):
            self.assertStatus(c[name], range(400, 500), name)
        self.assertStatus(c["near_object_ok"], (200, 201), "point near object")
        self.assertStatus(c["geometry_only_ok"], (200, 201), "object_id=null with place in Astana")

    def test_c06_raw_json_nan_infinity_malformed(self):
        """[C06][C01] raw bytes accepted; NaN/Infinity/malformed/non-object/invalid UTF-8/empty -> 400/422."""
        c = self.check("raw_json")
        self.assertStatus(c["raw_bytes_valid"], (200, 201), "raw bytes body")
        for name in ("nan_consent", "nan_coordinates", "infinity_coordinates", "nan_category",
                     "broken_json", "json_array", "invalid_utf8", "empty"):
            self.assertStatus(c[name], (400, 422), name)
        for name in ("broken_json", "json_array", "invalid_utf8"):
            self.assertEqual(c[name]["status"], 400, name)

    def test_c06_lone_surrogate_gives_json_error(self):
        """[C06][C01][S13] JSON with lone \\ud800 escape -> 400/422 envelope, never an exception out of handle()."""
        c = self.check("surrogate")
        self.assertStatus(c["submit_dict"], (200, 201, 400, 422), "dict body")
        self.assertStatus(c["moderate_reason"], (200, 400, 422), "moderate dict body")
        self.assertStatus(c["alive_after"], (200, 201), "service alive after")
        self.assertEqual(c.get("base_after"), {"moderation": "pending", "revision": 1})
        self.assertStatus(c["submit_raw_bytes"], (200, 201, 400, 422), "submit raw bytes with \\ud800")
        self.assertStatus(c["moderate_reason_raw_bytes"], (200, 400, 422), "moderate raw bytes with \\ud800")

    def test_c07_body_size_limits(self):
        """[C07] 120 KB body (bytes and dict) -> 413; 2500-char text -> 400/413/422, not stored; alive after."""
        c = self.check("body_size")
        self.assertStatus(c["raw_bytes_120k"], (413,), "raw bytes")
        self.assertStatus(c["dict_120k"], (413,), "dict")
        self.assertStatus(c["text_2500"], (400, 413, 422), "long text")
        self.assertEqual(c["rows_long"], 0)
        self.assertStatus(c["alive_after"], (200, 201), "alive after")

    # ------------------------------------------------------------------ S10
    def test_s10_xss_payload_returned_as_literal_text(self):
        """[S10] HTML/script text stored and returned literally in JSON (not executed, not mangled)."""
        c = self.check("xss")
        self.assertStatus(c["approve"], (200,), "approve")
        self.assertEqual(c["staff_text"], c["payload"])
        items = [json.loads(it) for it in c["public_items"]]
        self.assertTrue(any(it.get("text") == c["payload"] for it in items),
                        f"literal payload not in public items: {c['public_items'][:1]}")

    # ------------------------------------------------------------------ robustness / lifecycle
    def test_a07_duplicate_submit_warned_or_single_row(self):
        """[A07] repeated identical submit does not silently create many identical rows."""
        c = self.check("duplicate")
        self.assertStatus(c["first"], (200, 201), "first")
        warned = c["second"]["status"] >= 400 or bool(c["second_warnings"])
        self.assertTrue(c["rows_with_marker"] == 1 or warned,
                        f"rows={c['rows_with_marker']} second={c['second']['status']}")

    def test_a07_classifier_failure_does_not_lose_message(self):
        """[A07] classifier raising / hanging / returning garbage: 201, message stored, category unchanged, not public."""
        c = self.check("classifier")
        for name in ("raising", "hanging", "garbage"):
            r = c[name]
            if "not_run" in r:
                self.skipTest(f"NOT_RUN: {r['not_run']}")
            self.assertStatus(r["submit"], (200, 201), name)
            self.assertEqual(r["rows"], 1, f"{name}: message lost")
            self.assertEqual(r["category_after"], "sidewalks", f"{name}: machine overrode category")
            self.assertEqual(r["moderation_after"], "pending", f"{name}: machine moderated")
            self.assertFalse(r["public_has_marker"])
        self.assertLess(c["hanging"]["elapsed_s"], 5.0, "hanging classifier blocked the request")

    def test_a06_restart_keeps_public_and_hidden_state(self):
        """[A06][A08] close + reopen on same DB: approved still public, pending still hidden and still moderatable."""
        c = self.check("restart")
        self.assertStatus(c["approve"], (200,), "approve before restart")
        self.assertIn(c["ma"], c["public_before"]["raw"])
        self.assertIn(c["ma"], c["public_after"]["raw"])
        self.assertNotIn(c["mb"], c["public_after"]["raw"])
        self.assertEqual(c["pending_rows_after"], 1)
        self.assertEqual(c["pending_moderation_after"], "pending")
        self.assertStatus(c["approve_b_after"], (200,), "moderation after restart")
        self.assertIn(c["mb"], c["public_after2"]["raw"])

    def test_rate_limit_per_sender_small_n(self):
        """[R06-ACC-RATE][C01] same client_ip -> 429 within 10 submits (no row created); other client_ip not blocked."""
        c = self.check("rate_limit")
        self.assertIsNotNone(c["first_429_at_attempt"], f"no 429 in {c['statuses']}")
        self.assertLessEqual(c["first_429_at_attempt"], 10)
        self.assertEqual(c["rec_429"]["code"] is not None, True)
        self.assertEqual(c["rows_ip_a"], c["created_201"], "429 attempt created a row")
        self.assertStatus(c["other_ip"], (200, 201), "different client_ip")

    def test_c01_error_envelope_and_no_tracebacks(self):
        """[C01][S13] every error is {ok:false,error:{code,message}} JSON without traceback/paths/exception names."""
        routes = self.check("routes")
        self.assertStatus(routes["unknown_feedback_path"], (404,), "unknown path")
        self.assertStatus(routes["get_on_submit"], (404, 405), "wrong method")
        self.assertTrue(routes["foreign_path_returns_none"], "foreign API path must return None")
        problems = []
        for rec in self.R["all_errors"]:
            if rec.get("exception"):
                if not rec["label"].startswith("surrogate."):  # reported by test_c06_lone_surrogate
                    problems.append(f"{rec['label']}: raised {rec['exception']}")
                continue
            body = rec.get("body")
            if not (rec.get("serializable") and isinstance(body, dict) and body.get("ok") is False
                    and isinstance(body.get("error"), dict) and isinstance(body["error"].get("code"), str)
                    and isinstance(body["error"].get("message"), str)):
                problems.append(f"{rec['label']}: bad envelope {rec.get('raw', '')[:200]}")
                continue
            for pattern in TRACE_PATTERNS:
                if pattern.search(rec["raw"]):
                    problems.append(f"{rec['label']}: matches {pattern.pattern}: {rec['raw'][:200]}")
        self.assertGreater(len(self.R["all_errors"]), 20, "too few error samples")
        self.assertFalse(problems, "\n".join(problems))

    def test_c01_paths_outside_api_prefix_not_claimed(self):
        """[C01] handle() returns None for paths outside /api/civic/v1 (e.g. '/feedback' static route)."""
        c = self.check("prefixless")
        claimed = {k: v for k, v in c.items() if v is not None}
        self.assertFalse(claimed, f"service answered non-API paths: {claimed}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
