"""R10 acceptance: access control, sessions, request hygiene and exposure over HTTP.

Acceptance IDs: S01 S02 S03 S04 S05 S06 S07 S08 S11 S13 C01 C06 C07 C08.
Local loopback server under test only, small request counts, no external hosts.

Contract readings (CONTRACT.txt, PACK_SHA 9c2f5c0, §2):
  - unauthenticated -> 401; CSRF / foreign Origin -> 403. For an anonymous write a server may
    check CSRF before authentication; 403 is tolerated there (noted), never 2xx.
  - every refused write must leave the object unchanged (checked through the staff detail).
  - validation -> 400/422, too large -> 413, wrong Content-Type -> 415 or 400, errors are JSON
    envelopes without traceback/SQL/paths, and the server keeps answering afterwards.
  - the contract sets no maximum title length: an accepted long title must round-trip intact.
Set R10_NO_STATIC=1 for targets that serve no files at all (R10 standalone harness);
S08 then reports NOT_RUN instead of a meaningless PASS.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r10lib import contract, helpers  # noqa: E402
from r10lib.helpers import create_draft, expect_error, expect_ok, publish, token  # noqa: E402
from r10lib.target import get_target  # noqa: E402

VALIDATION = (400, 422)
NOTES: set[str] = set()


def tearDownModule():  # noqa: N802
    for note in sorted(NOTES):
        print(f"[R10 note] {note}", file=sys.stderr)


def staff_state(tc, ed, obj_id) -> tuple:
    r = ed.get(f"/staff/objects/{obj_id}")
    data = expect_ok(tc, r, "staff detail")
    item = data["item"]
    return (item.get("revision"), item.get("publication"), item.get("title"),
            json.dumps(item.get("schedule"), sort_keys=True))


def session_cookie_names(resp) -> list[str]:
    names = []
    for line in resp.set_cookies:
        name, _, rest = line.partition("=")
        value = rest.split(";", 1)[0]
        if value and "max-age=0" not in line.lower() and "expires=thu, 01 jan 1970" not in line.lower():
            names.append(name.strip())
    return names


def assert_alive(tc, what):
    r = get_target().client().get("/session")
    tc.assertEqual(r.status, 200, f"server not answering after {what}: {r.brief()}")


def write_routes(obj, fb=None):
    """(name, path, body) for every mutating staff route of the contract."""
    rev = obj["revision"]
    routes = [
        ("create", "/staff/objects", helpers.wrap_create(helpers.object_payload())),
        ("update", f"/staff/objects/{obj['id']}/update",
         {"expected_revision": rev, "changes": {"title": "R10 изменено без прав"}, "reason": "R10"}),
        ("publish", f"/staff/objects/{obj['id']}/publish", {"expected_revision": rev, "reason": "R10"}),
        ("archive", f"/staff/objects/{obj['id']}/archive", {"expected_revision": rev, "reason": "R10"}),
    ]
    if fb is not None:
        routes.append(("moderate", f"/staff/feedback/{fb['id']}/moderate",
                       {"expected_revision": fb.get("revision", 1), "action": "approve",
                        "reason": "R10", "public_reply": "R10 без прав"}))
    return routes


def count_staff_objects(ed) -> int | None:
    total, cursor = 0, None
    for _ in range(200):
        r = ed.get("/staff/objects", query={"cursor": cursor} if cursor else None)
        if r.status != 200 or not isinstance(r.data, dict):
            return None
        total += len(r.data.get("items", []))
        cursor = r.data.get("next_cursor")
        if not cursor:
            return total
    return None


def pending_feedback(tc, ed, obj_id) -> dict | None:
    marker = token("sec-fb")
    r = get_target().resident().post("/feedback", helpers.feedback_body(
        object_id=obj_id, text=f"R10 проверка прав модерации {marker}"))
    if r.status == 429:
        return None
    expect_ok(tc, r, "feedback submit")
    found = helpers.find_staff_feedback(ed, marker)
    tc.assertTrue(found, f"submitted feedback {marker} not in staff queue")
    return found[0]


class AnonymousAccess(unittest.TestCase):
    def test_s01_staff_reads_require_session(self):
        """[S01] anonymous GET of staff list/detail/feedback queue -> 401 without data"""
        ed = get_target().editor(0)
        draft = create_draft(self, ed)
        anon = get_target().client()
        for path in ("/staff/objects", f"/staff/objects/{draft['id']}", "/staff/feedback"):
            with self.subTest(path=path):
                r = anon.get(path)
                expect_error(self, r, f"anonymous GET {path}", (401,))
                self.assertNotIn(draft["title"], r.text, f"{path} leaked draft title to anonymous")

    def test_s01_s12_staff_writes_require_session(self):
        """[S01][S12] anonymous create/update/publish/archive/moderate refused, state unchanged"""
        ed = get_target().editor(0)
        obj = publish(self, ed, create_draft(self, ed))
        draft = create_draft(self, ed)
        fb = pending_feedback(self, ed, obj["id"])
        before_obj, before_draft = staff_state(self, ed, obj["id"]), staff_state(self, ed, draft["id"])
        before_count = count_staff_objects(ed)
        anon = get_target().client()
        anon.refresh_session()  # a server may hand anonymous clients a token; it must not help
        for name, path, body in write_routes(draft, fb) + write_routes(obj)[1:4]:
            with self.subTest(route=name, path=path):
                r = anon.post(path, body)
                expect_error(self, r, f"anonymous {name}", (401, 403))
                if r.status == 403:
                    NOTES.add(f"anonymous {name} answered 403 (CSRF before auth); contract prefers 401")
        self.assertEqual(staff_state(self, ed, obj["id"]), before_obj, "published object changed by anonymous")
        self.assertEqual(staff_state(self, ed, draft["id"]), before_draft, "draft changed by anonymous")
        self.assertEqual(count_staff_objects(ed), before_count, "anonymous create added an object")
        if fb is not None:
            still = helpers.find_staff_feedback(ed, fb["text"])
            self.assertTrue(still, "feedback disappeared after anonymous moderate")
            pub = get_target().client().get(f"/objects/{obj['id']}/feedback")
            self.assertNotIn(fb["text"], pub.text, "anonymous moderate published the feedback")


class CsrfAndOrigin(unittest.TestCase):
    def test_s02_writes_without_or_with_wrong_csrf_rejected(self):
        """[S02] editor session but missing/wrong/foreign-session CSRF -> 403, nothing changes"""
        tgt = get_target()
        ed = tgt.editor(0)
        other = tgt.editor(1 if len(tgt.editors) > 1 else 0)
        obj = publish(self, ed, create_draft(self, ed))
        draft = create_draft(self, ed)
        before = (staff_state(self, ed, obj["id"]), staff_state(self, ed, draft["id"]))
        before_count = count_staff_objects(ed)
        for label, csrf in (("missing", ""), ("wrong", "r10-not-a-token"),
                            ("other session", other.csrf_token)):
            if label == "other session" and other.csrf_token == ed.csrf_token:
                continue
            for name, path, body in write_routes(draft) + write_routes(obj)[1:4]:
                with self.subTest(csrf=label, route=name):
                    r = ed.post(path, body, csrf=csrf or None)
                    expect_error(self, r, f"{name} with {label} CSRF", (403,))
        self.assertEqual((staff_state(self, ed, obj["id"]), staff_state(self, ed, draft["id"])), before,
                         "a write without a valid CSRF token changed state")
        self.assertEqual(count_staff_objects(ed), before_count, "create without CSRF added an object")

    def test_s03_foreign_or_null_origin_rejected(self):
        """[S03] valid session+CSRF but foreign/null Origin -> 403, nothing changes; login too"""
        ed = get_target().editor(0)
        obj = publish(self, ed, create_draft(self, ed))
        before = staff_state(self, ed, obj["id"])
        for origin in ("http://evil.example", "null", f"http://127.0.0.1:1"):
            for name, path, body in write_routes(obj)[1:3]:
                with self.subTest(origin=origin, route=name):
                    r = ed.post(path, body, origin=origin)
                    expect_error(self, r, f"{name} from Origin {origin}", (403,))
        self.assertEqual(staff_state(self, ed, obj["id"]), before, "cross-origin write changed state")
        user, password = get_target().editors[0]
        fresh = get_target().client()
        r = fresh.post("/session/login", {"username": user, "password": password}, origin="http://evil.example")
        expect_error(self, r, "login from foreign Origin", (403,))
        self.assertEqual(session_cookie_names(r), [], "login from foreign Origin still set a session cookie")

    def test_s03_wrong_host_rejected(self):
        """[S03] Host not this server (DNS-rebinding shape) -> refused for login and writes"""
        tgt = get_target()
        ed = tgt.editor(0)
        obj = publish(self, ed, create_draft(self, ed))
        before = staff_state(self, ed, obj["id"])
        port = tgt.base_url.rsplit(":", 1)[-1]
        for host in (f"evil.example:{port}", f"localhost.evil.example:{port}"):
            with self.subTest(host=host):
                origin = f"http://{host}"
                name, path, body = write_routes(obj)[1]
                r = ed.post(path, body, host=host, origin=origin)
                expect_error(self, r, f"update with Host {host}", (400, 403, 421))
                user, password = tgt.editors[0]
                r = tgt.client().post("/session/login", {"username": user, "password": password},
                                      host=host, origin=origin)
                expect_error(self, r, f"login with Host {host}", (400, 403, 421))
                self.assertEqual(session_cookie_names(r), [], f"login via Host {host} set a cookie")
        self.assertEqual(staff_state(self, ed, obj["id"]), before, "write with foreign Host changed state")


class SessionLifecycle(unittest.TestCase):
    def test_s04_logout_revokes_server_side_session(self):
        """[S04] after logout a replayed cookie+CSRF token cannot read staff data or write"""
        ed = get_target().editor(0)
        obj = publish(self, ed, create_draft(self, ed))
        stolen = ed.clone_credentials()
        r = ed.logout()
        self.assertIn(r.status, (200, 204), f"logout: {r.brief()}")
        before = staff_state(self, get_target().editor(0), obj["id"])
        name, path, body = write_routes(obj)[1]
        r = stolen.post(path, body)
        expect_error(self, r, "write with logged-out session", (401, 403))
        r = stolen.get("/staff/objects")
        expect_error(self, r, "staff read with logged-out session", (401,))
        s = stolen.get("/session")
        self.assertEqual(s.status, 200, s.brief())
        self.assertFalse((s.data or {}).get("authenticated"), f"session still authenticated: {s.brief()}")
        self.assertEqual(staff_state(self, get_target().editor(0), obj["id"]), before)

    def test_s05_wrong_password_gives_401_and_no_session(self):
        """[S05] wrong password -> 401, no session cookie, /session stays anonymous"""
        user, _ = get_target().editors[0]
        c = get_target().resident()
        r = c.post("/session/login", {"username": user, "password": "R10-wrong-" + token()})
        expect_error(self, r, "login with wrong password", (401,))
        self.assertEqual(session_cookie_names(r), [], "failed login set a session cookie")
        self.assertFalse((c.get("/session").data or {}).get("authenticated"))
        r = c.get("/staff/objects")
        expect_error(self, r, "staff read after failed login", (401,))

    def test_s06_session_cookie_flags_and_not_in_body(self):
        """[S06] session cookie HttpOnly + SameSite; session id never echoed in JSON"""
        user, password = get_target().editors[0]
        c = get_target().client()
        r = c.login(user, password)
        self.assertEqual(r.status, 200, r.brief())
        lines = [line for line in r.set_cookies if line.split("=", 1)[0].strip() in session_cookie_names(r)]
        if not lines:
            r2 = c.get("/session")
            lines = r2.set_cookies
        self.assertTrue(lines, "login set no cookie at all")
        for line in lines:
            low = line.lower()
            self.assertIn("httponly", low, f"session cookie without HttpOnly: {line[:120]}")
            self.assertRegex(low, r"samesite=(lax|strict)", f"session cookie without SameSite: {line[:120]}")
            value = line.split("=", 1)[1].split(";", 1)[0]
            if len(value) >= 16:
                self.assertNotIn(value, r.text, "session id echoed in the JSON body")
                self.assertNotIn(value, c.get("/session").text, "session id in GET /session body")

    def test_s07_role_and_identity_not_taken_from_request(self):
        """[S07] role/actor in login body or headers grants nothing"""
        tgt = get_target()
        c = tgt.resident()
        r = c.post("/session/login", {"username": "r10_nobody_" + token()[-6:], "password": "x" * 12,
                                       "role": "editor", "authenticated": True})
        self.assertIn(r.status, (400, 401, 422), f"login of unknown user with role in body: {r.brief()}")
        self.assertEqual(session_cookie_names(r), [])
        spoof = {"X-Role": "editor", "X-User": tgt.editors[0][0], "X-Forwarded-User": tgt.editors[0][0],
                 "X-Remote-User": tgt.editors[0][0], "Authorization": "Bearer editor"}
        r = c.get("/staff/objects", headers=spoof)
        expect_error(self, r, "staff read with spoofed identity headers", (401,))
        body = dict(helpers.object_payload(), role="editor", actor="r10", user={"role": "editor"})
        r = c.post("/staff/objects", body, headers=spoof)
        expect_error(self, r, "create with spoofed role in body+headers", (401, 403))
        s = c.get("/session", headers=spoof)
        self.assertFalse((s.data or {}).get("authenticated"), f"spoofed headers authenticated: {s.brief()}")

    def test_zz_s05_failed_logins_are_limited(self):
        """[S05] repeated wrong passwords (N<=12, own source IP, throwaway name) eventually 429"""
        tgt = get_target()
        c = tgt.resident()
        name = "r10_bruteforce_" + token()[-6:]
        statuses = []
        for i in range(12):
            r = c.post("/session/login", {"username": name, "password": f"wrong-{i}-" + token()})
            statuses.append(r.status)
            self.assertNotIn(r.status, (200, 500), f"attempt {i}: {r.brief()}")
            if r.status == 429:
                break
        # the real editor (other source IP) must still be able to log in
        user, password = tgt.editors[0]
        ok = tgt.client().login(user, password)
        self.assertEqual(ok.status, 200, f"real editor locked out by another client's failures: {ok.brief()}")
        self.assertIn(429, statuses, f"no login rate limit observed in {len(statuses)} attempts: {statuses}")


class StaticExposure(unittest.TestCase):
    MARKERS = (b"SQLite format 3", b"[core]", b"import ", b"def ", b"OPENAI", b"ANTHROPIC",
               b"password_hash", b"scrypt$", b"pbkdf2")

    def test_s08_runtime_db_env_and_sources_not_served(self):
        """[S08] .sqlite/-wal/-shm, .env, .git, Python sources not downloadable (incl. traversal)"""
        if os.environ.get("R10_NO_STATIC") == "1":
            raise unittest.SkipTest("NOT_RUN: target serves no static files (R10 standalone harness)")
        tgt = get_target()
        names = {"civic.sqlite3", "civic.sqlite", "civic.db"}
        db = getattr(tgt, "db", None)
        if db is not None:
            names.add(Path(db).name)
        paths = ["/.env", "/.env.example", "/.git/config", "/.git/HEAD", "/app.py", "/ui/web_server.py",
                 "/ui/civic_store/auth.py", "/web/../.env", "/%2e%2e/.env", "/..%2f.env", "/static/../../.env",
                 "/api/civic/v1/../../.env", "/api/civic/v1/%2e%2e/%2e%2e/.env", "/.runtime/", "/web/index.html/../../.env"]
        for n in sorted(names):
            for prefix in ("/", "/.runtime/", "/data/", "/web/", "/../.runtime/"):
                for suffix in ("", "-wal", "-shm"):
                    paths.append(f"{prefix}{n}{suffix}")
        c = tgt.client()
        leaks = []
        for path in paths:
            r = c.raw("GET", path)
            if r.status == 200 and any(m in r.raw for m in self.MARKERS):
                leaks.append(f"{path} -> 200 {r.raw[:40]!r}")
        self.assertEqual(leaks, [], "server returned runtime/secret/source content")
        root = c.raw("GET", "/")
        self.assertIn(root.status, (200, 404), f"GET / : {root.brief()}")


class NoServerSideFetch(unittest.TestCase):
    def test_s11_urls_in_sources_and_feedback_are_never_fetched(self):
        """[S11] server never requests URLs from source_refs or feedback text (local canary)"""
        hits = []

        class Canary(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                hits.append(self.path)
                self.send_response(204)
                self.end_headers()

            do_HEAD = do_POST = do_GET

            def log_message(self, *args):
                pass

        canary = ThreadingHTTPServer(("127.0.0.1", 0), Canary)
        threading.Thread(target=canary.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{canary.server_address[1]}/r10-ssrf-{token()}"
        try:
            ed = get_target().editor(0)
            ref = {"id": "r10-src-1", "url": url, "publisher": "R10 canary", "published_on": None,
                   "retrieved_at": None, "access_status": "not_fetched", "license": None, "fields": ["title"]}
            draft = create_draft(self, ed, source_refs=[ref])
            obj = publish(self, ed, draft)
            r = helpers.update(ed, obj, {"source_refs": [dict(ref, url=url + "/u")]}, "R10: источник")
            self.assertIn(r.status, (200, 400, 422), r.brief())
            r = get_target().resident().post("/feedback", helpers.feedback_body(
                object_id=obj["id"], text=f"Смотрите {url}/fb пожалуйста проверьте"))
            self.assertIn(r.status, (200, 201, 400, 409, 422, 429), r.brief())
            get_target().client().get(f"/objects/{obj['id']}")
            time.sleep(1.5)
        finally:
            canary.shutdown()
            canary.server_close()
        self.assertEqual(hits, [], f"server fetched attacker-chosen URLs: {hits}")


class RequestHygiene(unittest.TestCase):
    def test_c01_unknown_paths_and_methods_are_json(self):
        """[C01][S13] unknown API path -> 404 JSON; DELETE/PUT/PATCH -> 404/405 JSON, object stays"""
        ed = get_target().editor(0)
        obj = publish(self, ed, create_draft(self, ed))
        anon = get_target().client()
        expect_error(self, anon.get("/r10-no-such-route"), "unknown GET", (404,))
        expect_error(self, anon.post("/r10-no-such-route", {}), "unknown POST", (404, 403, 405))
        for method in ("DELETE", "PUT", "PATCH"):
            for client, path in ((anon, f"/objects/{obj['id']}"), (ed, f"/staff/objects/{obj['id']}")):
                with self.subTest(method=method, path=path):
                    r = client.call(method, path, {})
                    self.assertIn(r.status, (401, 403, 404, 405, 501), f"{method} {path}: {r.brief()}")
                    self.assertFalse(contract.has_traceback(r.text), r.text[:300])
                    self.assertEqual(contract.check_envelope(r.json, r.status), [], f"{method} {path}: {r.brief()}")
        detail = get_target().client().get(f"/objects/{obj['id']}")
        self.assertEqual(detail.status, 200, f"object gone after DELETE/PUT/PATCH: {detail.brief()}")

    def test_c06_s13_invalid_values_rejected_without_500(self):
        """[C06][S13] bad dates/numbers/geometry/enums/title -> 400/422 JSON, server alive"""
        ed = get_target().editor(0)
        base = helpers.object_payload()
        cases = {
            "impossible date": {"schedule": dict(base["schedule"], current_planned_end="2026-02-30")},
            "datetime as date": {"schedule": dict(base["schedule"], planned_start="2026-10-14T00:00:00+05:00")},
            "end before start": {"schedule": dict(base["schedule"], current_planned_end="2026-10-01")},
            "negative budget": {"budget": {"amount_kzt": -1, "basis": "planned", "source_id": None}},
            "bool budget": {"budget": {"amount_kzt": True, "basis": "planned", "source_id": None}},
            "string budget": {"budget": {"amount_kzt": "1000", "basis": "planned", "source_id": None}},
            "swapped lat/lon": {"geometry": {"type": "Point", "coordinates": [51.17, 71.43]}},
            "out of range": {"geometry": {"type": "Point", "coordinates": [271.4, 51.1]}},
            "geometry string": {"geometry": "71.43,51.17"},
            "unknown geometry": {"geometry": {"type": "Circle", "coordinates": [71.43, 51.17]}},
            "empty title": {"title": "   "},
            "unknown kind": {"kind": "pothole"},
            "unknown status": {"status": "active"},
            "unknown evidence": {"evidence_type": "verified"},
        }
        for label, override in cases.items():
            with self.subTest(case=label):
                r = ed.post("/staff/objects", helpers.wrap_create(dict(base, **override)))
                expect_error(self, r, f"create with {label}", VALIDATION)
        raw_cases = {
            "NaN": b'{"kind":"roadworks","title":"R10 NaN","evidence_type":"synthetic","budget":{"amount_kzt":NaN,"basis":"planned","source_id":null}}',
            "Infinity": b'{"kind":"roadworks","title":"R10 Inf","evidence_type":"synthetic","budget":{"amount_kzt":Infinity,"basis":"planned","source_id":null}}',
            "huge number": b'{"kind":"roadworks","title":"R10 big","evidence_type":"synthetic","budget":{"amount_kzt":1e999,"basis":"planned","source_id":null}}',
        }
        for label, raw in raw_cases.items():
            with self.subTest(case=label):
                r = ed.post("/staff/objects", raw_body=raw)
                expect_error(self, r, f"create with {label}", VALIDATION)
        assert_alive(self, "validation matrix")

    def test_c07_oversized_body_and_long_text(self):
        """[C07] 100 KiB body -> 413; 5000-char title -> 4xx or exact round-trip; server alive"""
        ed = get_target().editor(0)
        big = json.dumps(helpers.object_payload(description="я" * 51200)).encode("utf-8")
        self.assertGreater(len(big), 64 * 1024)
        r = ed.post("/staff/objects", raw_body=big)
        expect_error(self, r, "100 KiB create body", (413,))
        r = get_target().resident().post("/feedback", raw_body=json.dumps(
            helpers.feedback_body(text="ы" * 60000)).encode())
        expect_error(self, r, "120 KiB feedback body", (413,))
        title = "Длинное название R10 " + "ж" * 5000
        r = ed.post("/staff/objects", helpers.wrap_create(helpers.object_payload(title=title)))
        if r.status in (200, 201):
            NOTES.add("5000-char title accepted (contract sets no limit)")
            self.assertEqual(r.data["item"]["title"], title, "long title silently altered/truncated")
        else:
            expect_error(self, r, "5000-char title", (400, 413, 422))
        assert_alive(self, "oversized bodies")

    def test_c08_content_type_and_malformed_json(self):
        """[C08][S13] wrong Content-Type -> 415/400; broken/non-object JSON -> 400; no object created"""
        ed = get_target().editor(0)
        before = count_staff_objects(ed)
        good = json.dumps(helpers.object_payload()).encode()
        cases = [
            ("text/plain", good, (400, 415)),
            ("application/x-www-form-urlencoded", b"title=R10&kind=roadworks", (400, 415)),
            ("application/json", b'{"kind": "roadworks", "title": ', (400,)),
            ("application/json", b'["kind", "roadworks"]', (400, 422)),
            ("application/json", b'"just a string"', (400, 422)),
            ("application/json", b"\xff\xfe\x00{", (400,)),
        ]
        for ctype, raw, statuses in cases:
            with self.subTest(content_type=ctype, body=raw[:20]):
                r = ed.post("/staff/objects", raw_body=raw, content_type=ctype)
                expect_error(self, r, f"create with {ctype} {raw[:20]!r}", statuses)
        r = ed.post("/staff/objects", raw_body=b"", content_type="application/json")
        expect_error(self, r, "create with empty body", (400, 411, 422))
        self.assertEqual(count_staff_objects(ed), before, "a malformed request created an object")
        assert_alive(self, "malformed bodies")


if __name__ == "__main__":
    unittest.main()
