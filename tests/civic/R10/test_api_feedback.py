"""R10 acceptance: resident feedback over HTTP (submit -> moderate -> public) and its edges.

Acceptance IDs: A07 A08 S09 S10 S12 S14 (+S07 for role spoofing on moderation).

Written only from CONTRACT.txt (PACK_SHA 9c2f5c0, sections 2-3, 6) and the R10 harness;
it does not look at how the R10 oracle or any product implements the API.
At most 16 POST /feedback calls are made by this whole file (typical rate limits).

Contract readings used here (ambiguities resolved explicitly, see report):
  F1  Public GET /objects/{id}/feedback: data is {items, next_cursor?} or a bare list.
      Field names of a public feedback item are not fixed, so tests look for the
      submitted text / reply among the item's string values and search the raw body.
  F2  GET /staff/feedback is "the editor queue"; it may list only pending items. Tests
      look items up there only while pending and judge the result of moderation
      through the public endpoints, never through the queue.
  F3  Moderation takes expected_revision, so a successful moderation must make the
      pre-moderation revision stale: reusing it -> 409 and nothing changes.
  F4  "Без согласия автора публичного текста нет": approving a consent_public=false
      item may be refused (400/422) or accepted (e.g. reply only); either way the
      author's text never appears in any public response.
  F5  Receipt is {receipt_id, moderation:"pending"}. Extra keys are recorded as notes;
      echo of the text, the client IP or User-Agent, or a sensitive-looking key = FAIL.
  F6  Duplicate submit: one staff item, or an explicit duplicate/warning marker (in
      the second response or on the staff item), or an explicit 4xx. Two unmarked
      identical pending items = silent duplicate = FAIL. The original is never lost.
  F7  HTML payloads: exact literal = PASS; stored HTML-entity-escaped = PASS + note
      (the browser layer must then show text; checked elsewhere); a 400/422 rejection
      of HTML in an object title = PASS + note (title is "plain text, без HTML");
      any other silent alteration = FAIL (user data changed without a documented rule).
  F8  Draft vs missing object id: both must be refused with identical status, error.code
      and (id-normalised) message; 403 for the draft confirms existence = FAIL.
  F9  Anonymous moderation must be 401. 403 is tolerated only when the server handed
      the anonymous client no CSRF token (CSRF checked before authentication); noted.
  F10 Moderation reason or receipt_id appearing publicly is not fixed by the contract:
      recorded as a note, not failed.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
import re
import sys
import threading
import unittest
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r10lib import contract, helpers  # noqa: E402
from r10lib.helpers import create_draft, expect_error, expect_ok, feedback_body, publish, token  # noqa: E402
from r10lib.target import get_target  # noqa: E402

VALIDATION = (400, 422)
SUCCESS = (200, 201)
ASTANA_POINT = {"type": "Point", "coordinates": [71.43, 51.17]}
SHYMKENT_POINT = {"type": "Point", "coordinates": [69.59, 42.32]}
XSS = "<img src=x onerror=alert(1)><script>alert(2)</script>"
FLAG_KEY = re.compile(r"(dup|warn|similar|notice|repeat)", re.IGNORECASE)
NOTES: set[str] = set()


def tearDownModule():  # noqa: N802 (unittest hook name)
    if NOTES:
        sys.stderr.write("\n[test_api_feedback] contract-open behaviour observed on this target:\n")
        for line in sorted(NOTES):
            sys.stderr.write(f"  - {line}\n")


# ---------------------------------------------------------------- small helpers
def editor(index: int = 0):
    """Fresh logged-in editor; falls back to a second session of editor 0."""
    t = get_target()
    return t.editor(index if index < len(t.editors) else 0)


def editor_names() -> list[str]:
    return [user for user, _ in get_target().editors]


def resident():
    """Anonymous resident, from its own 127.0.x.y address when the target is on loopback.

    GET /session first, as a browser page would, so a server that hands anonymous
    clients a pre-session CSRF token is not failed for that design choice.
    """
    t = get_target()
    c = t.client()
    if str(c.host).startswith("127."):
        c = t.resident()
    c.refresh_session()
    return c


def submit(tc, client, body: dict, ua: str | None = None):
    """POST /feedback; a 429 makes the test NOT_RUN (same rule as helpers.submit_feedback)."""
    headers = {"User-Agent": ua} if ua else None
    r = client.post("/feedback", body, headers=headers)
    if r.status == 429:
        raise unittest.SkipTest("feedback rate limit reached during suite; check NOT_RUN, not FAIL")
    return r


def keys_recursive(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key)
            yield from keys_recursive(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from keys_recursive(value)


def string_values(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from string_values(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from string_values(value)


def receipt(tc, r, what: str, privates=()) -> dict:
    """[A07] receipt envelope and shape; nothing the resident sent comes back."""
    data = expect_ok(tc, r, what)
    tc.assertIsInstance(data, dict, f"{what}: data must be an object: {r.brief()}")
    rid = data.get("receipt_id")
    tc.assertTrue(isinstance(rid, (str, int)) and not isinstance(rid, bool) and str(rid).strip(),
                  f"{what}: receipt_id missing/empty: {r.brief()}")
    tc.assertEqual(data.get("moderation"), "pending", f"{what}: moderation must be 'pending': {r.brief()}")
    leaky = [k for k in keys_recursive(data) if contract.SENSITIVE_KEY.search(k)]
    tc.assertEqual(leaky, [], f"{what}: receipt carries sensitive-looking keys: {r.brief()}")
    for needle, label in privates:
        if needle:
            tc.assertNotIn(needle, r.text, f"{what}: receipt echoes the {label}: {r.brief()}")
    extra = sorted(set(data) - {"receipt_id", "moderation"})
    if extra:
        NOTES.add(f"feedback receipt carries extra keys {extra}")
    return data


def staff_feedback(tc, ed, needle: str, field: str = "text", max_pages: int = 200) -> list[dict]:
    """Staff queue items whose `field` (or, if absent, whole JSON) contains needle."""
    found, cursor, seen = [], None, set()
    for _ in range(max_pages):
        r = ed.get("/staff/feedback", query={"cursor": cursor} if cursor else None)
        data = expect_ok(tc, r, "staff feedback queue", statuses=(200,))
        rows = data if isinstance(data, list) else (data.get("items") if isinstance(data, dict) else None)
        tc.assertIsInstance(rows, list, f"staff feedback queue: data.items must be a list: {r.brief()}")
        for it in rows:
            if not isinstance(it, dict):
                continue
            hay = str(it.get(field)) if field in it else json.dumps(it, ensure_ascii=False)
            if needle in hay:
                found.append(it)
        cursor = data.get("next_cursor") if isinstance(data, dict) else None
        if cursor in (None, ""):
            break
        key = json.dumps(cursor, sort_keys=True)
        tc.assertNotIn(key, seen, f"staff feedback queue: next_cursor {cursor!r} repeats")
        seen.add(key)
    return found


def staff_one(tc, ed, needle: str, what: str) -> dict:
    items = staff_feedback(tc, ed, needle)
    tc.assertEqual(len(items), 1, f"{what}: expected exactly one staff queue item with {needle!r}, "
                                  f"got {len(items)}: {items[:3]}")
    fb = items[0]
    tc.assertIn("id", fb, f"{what}: staff queue item has no id: {fb}")
    return fb


def public_feedback(tc, obj_id: str, what: str = "public feedback"):
    """All pages of GET /objects/{id}/feedback -> (items, raw text of all pages, last Resp)."""
    c = get_target().client()
    items, texts, cursor, seen, last = [], [], None, set(), None
    for _ in range(200):
        r = c.get(f"/objects/{obj_id}/feedback", query={"cursor": cursor} if cursor else None)
        data = expect_ok(tc, r, f"{what}: GET /objects/{obj_id}/feedback", statuses=(200,))
        texts.append(r.text)
        last = r
        if isinstance(data, list):
            items.extend(data)
            break
        tc.assertIsInstance(data, dict, f"{what}: {r.brief()}")
        tc.assertIsInstance(data.get("items"), list, f"{what}: data.items must be a list: {r.brief()}")
        items.extend(data["items"])
        cursor = data.get("next_cursor")
        if cursor in (None, ""):
            break
        key = json.dumps(cursor, sort_keys=True)
        tc.assertNotIn(key, seen, f"{what}: next_cursor {cursor!r} repeats")
        seen.add(key)
    return items, "\n".join(texts), last


def public_objects_text(tc) -> str:
    """Raw text of every page of the public object list."""
    c = get_target().client()
    texts, cursor, seen = [], None, set()
    for _ in range(400):
        r = c.get("/objects", query={"cursor": cursor} if cursor else None)
        data = expect_ok(tc, r, "public object list", statuses=(200,))
        texts.append(r.text)
        cursor = data.get("next_cursor") if isinstance(data, dict) else None
        if cursor in (None, ""):
            break
        key = json.dumps(cursor, sort_keys=True)
        tc.assertNotIn(key, seen, f"public object list: next_cursor {cursor!r} repeats")
        seen.add(key)
    return "\n".join(texts)


def published(tc, ed, **overrides) -> dict:
    return publish(tc, ed, create_draft(tc, ed, **overrides))


def ghost_id(real_id: str) -> str:
    """An id of the same shape as a real one that almost surely does not exist."""
    if real_id.isdigit():
        return str(int(real_id) + 10 ** 9)
    tail = "ffff" if real_id[-4:] != "ffff" else "eeee"
    return real_id[:-4] + tail if len(real_id) > 4 else real_id + tail


def mine(items, needle: str) -> list:
    return [it for it in items if needle in json.dumps(it, ensure_ascii=False)]


def json_headers(tc, r, what: str):
    """[S10] JSON is labelled as JSON and must not be content-sniffed into HTML."""
    tc.assertTrue(r.content_type.lower().startswith("application/json"),
                  f"{what}: Content-Type must be application/json: {r.brief()}")
    tc.assertEqual(r.headers.get("x-content-type-options", "").strip().lower(), "nosniff",
                   f"{what}: X-Content-Type-Options: nosniff missing (headers={r.headers})")


def literal_or_escaped(tc, stored, sent: str, what: str):
    """[S10] F7: stored value is the literal text, or (noted) its HTML-escaped form."""
    if stored == sent:
        return "literal"
    if isinstance(stored, str) and stored in (html.escape(sent), html.escape(sent, quote=False)):
        NOTES.add(f"{what}: stored/returned HTML-escaped inside JSON (browser layer must render text)")
        return "escaped"
    tc.fail(f"{what}: text altered by the server without a documented rule: sent {sent!r}, got {stored!r}")
    return None


def value_with(tc, item, needle: str, what: str) -> str:
    vals = [v for v in string_values(item) if needle in v]
    tc.assertTrue(vals, f"{what}: no string field containing {needle!r} in {item}")
    return vals[0]


def error_code(r):
    err = r.error
    return err.get("code") if isinstance(err, dict) else None


def error_message(r, obj_id: str):
    err = r.error
    msg = err.get("message") if isinstance(err, dict) else None
    return msg.replace(obj_id, "<id>") if isinstance(msg, str) else msg


def assert_unauthenticated(tc, r, csrf_available: bool, what: str):
    """[S12] F9: 401; 403 tolerated only when no CSRF token could have been sent."""
    if r.status == 403 and not csrf_available:
        NOTES.add("anonymous write without any CSRF token answered 403 (CSRF checked before auth)")
        expect_error(tc, r, what, (403,))
        return
    expect_error(tc, r, f"{what}: must be 401 Unauthenticated", (401,))


# ================================================================ main path
class FeedbackLifecycle(unittest.TestCase):

    def test_a07_receipt_only_pending_stays_private(self):
        """[A07][A08][S09] submit -> receipt {receipt_id, moderation:pending} only; pending stays private, staff queue has it."""
        ed = editor(0)
        obj = published(self, ed)
        res = resident()
        tok, ua = token("a07"), token("ua")
        text = f"R10 обращение {tok}: на тротуаре у остановки глубокая яма"
        r = submit(self, res, feedback_body(object_id=obj["id"], text=text, category="sidewalks"),
                   ua=f"R10-UA {ua}")
        receipt(self, r, "A07 submit", privates=((tok, "feedback text"), (ua, "User-Agent"),
                                                 (res.source_ip, "client IP address")))

        items, raw, _ = public_feedback(self, obj["id"], "A08 pending")
        self.assertNotIn(tok, raw, "A08: pending (unmoderated) feedback is visible in public feedback list")
        pd = helpers.public_detail(obj["id"])
        expect_ok(self, pd, "public object detail", statuses=(200,))
        self.assertNotIn(tok, pd.text, f"A08: pending feedback text leaks into public object detail: {pd.brief()}")
        self.assertNotIn(tok, public_objects_text(self), "A08: pending feedback text leaks into the public object list")

        fb = staff_one(self, ed, tok, "A07 staff queue")
        self.assertIn(text, list(string_values(fb)),
                      f"A07: staff queue must hold the resident's text exactly as sent: {fb}")
        rev = fb.get("revision")
        self.assertTrue(isinstance(rev, int) and not isinstance(rev, bool) and rev >= 1,
                        f"A07: staff item needs an integer revision >= 1 for expected_revision: {fb}")
        if "moderation" in fb:
            self.assertEqual(fb["moderation"], "pending", f"A07: new item must be pending in staff queue: {fb}")
        if "object_id" in fb:
            self.assertEqual(str(fb["object_id"]), str(obj["id"]), f"A07: staff item lost its object link: {fb}")

    def test_a08_approved_with_consent_public_with_reply(self):
        """[A08][S09] approve + consent + public_reply -> public with reply; no IP/UA/editor identity publicly."""
        ed = editor(0)
        obj = published(self, ed)
        res = resident()
        tok, rtok, why, ua = token("a08ok"), token("reply"), token("why"), token("ua")
        text = f"R10 одобряемое обращение {tok}: не горит фонарь"
        r = submit(self, res, feedback_body(object_id=obj["id"], text=text, category="lighting"),
                   ua=f"R10-UA {ua}")
        rcpt = receipt(self, r, "A08 submit")
        fb = staff_one(self, ed, tok, "A08 staff queue")
        reply = f"R10 синтетический ответ редакции {rtok}"
        m = helpers.moderate(ed, fb, "approve", public_reply=reply, reason=f"R10 модерация {why}")
        expect_ok(self, m, "A08 approve with consent")

        items, raw, last = public_feedback(self, obj["id"], "A08 approved")
        hits = mine(items, tok)
        self.assertEqual(len(hits), 1, f"A08: approved consented feedback must be listed publicly once; "
                                       f"found {len(hits)}: {last.brief()}")
        item = hits[0]
        self.assertIn(text, list(string_values(item)), f"A08: public item must carry the author's text: {item}")
        self.assertTrue(any(reply in v for v in string_values(item)),
                        f"A08: public item must carry the public_reply {reply!r}: {item}")
        leaky = [k for k in keys_recursive(item) if contract.SENSITIVE_KEY.search(k)]
        self.assertEqual(leaky, [], f"S09: public feedback item has sensitive-looking keys: {item}")
        for needle, label in [(ua, "User-Agent"), (res.source_ip, "client IP address")] + \
                [(name, "editor username") for name in editor_names()]:
            if needle:
                self.assertNotIn(needle, raw, f"S09: public feedback exposes the {label} {needle!r}: {last.brief()}")
        if why in raw:
            NOTES.add("moderation reason is shown in public feedback")
        if str(rcpt.get("receipt_id")) in raw:
            NOTES.add("receipt_id is shown in public feedback")

    def test_a08_s09_no_consent_text_never_public(self):
        """[A08][S09] consent_public=false: text never reaches public feedback, object detail or object list."""
        ed = editor(0)
        obj = published(self, ed)
        res = resident()
        head, tail, rtok = token("nchead"), token("nctail"), token("reply")
        text = f"{head} R10 личное обращение без согласия на публикацию {tail}"
        receipt(self, submit(self, res, feedback_body(object_id=obj["id"], text=text, consent_public=False)),
                "no-consent submit")
        fb = staff_one(self, ed, head, "no-consent staff queue")
        self.assertIn(text, list(string_values(fb)), f"moderators must still see the full text: {fb}")

        m = helpers.moderate(ed, fb, "approve", public_reply=f"R10 синтетический ответ {rtok}")
        if m.status in SUCCESS:
            expect_ok(self, m, "approve of no-consent feedback")
        else:
            expect_error(self, m, "approve of no-consent feedback: refused must be validation", VALIDATION)
            NOTES.add(f"approve of consent_public=false feedback refused with {m.status}")

        _, raw, last = public_feedback(self, obj["id"], "no-consent approved")
        for needle in (head, tail, "без согласия на публикацию"):
            self.assertNotIn(needle, raw, f"A08: text of a no-consent item is public in feedback list: {last.brief()}")
        if rtok in raw:
            NOTES.add("approved consent_public=false item listed publicly without author text (reply only)")
        pd = helpers.public_detail(obj["id"])
        expect_ok(self, pd, "public object detail", statuses=(200,))
        self.assertNotIn(head, pd.text, f"A08: no-consent text leaks into public object detail: {pd.brief()}")
        self.assertNotIn(tail, pd.text, f"A08: no-consent text leaks into public object detail: {pd.brief()}")
        everything = public_objects_text(self)
        self.assertNotIn(head, everything, "A08: no-consent text leaks into the public object list")
        self.assertNotIn(tail, everything, "A08: no-consent text leaks into the public object list")

    def test_a08_rejected_never_public(self):
        """[A08] rejected feedback (consent given) never appears publicly."""
        ed = editor(0)
        obj = published(self, ed)
        res = resident()
        tok, rtok = token("a08rej"), token("reply")
        receipt(self, submit(self, res, feedback_body(object_id=obj["id"], text=f"R10 отклоняемое {tok}")),
                "reject submit")
        fb = staff_one(self, ed, tok, "reject staff queue")
        m = helpers.moderate(ed, fb, "reject", public_reply=None, reason=f"R10 отклонено {rtok}")
        expect_ok(self, m, "reject")
        _, raw, last = public_feedback(self, obj["id"], "rejected")
        self.assertNotIn(tok, raw, f"A08: rejected feedback is public: {last.brief()}")
        pd = helpers.public_detail(obj["id"])
        expect_ok(self, pd, "public object detail", statuses=(200,))
        self.assertNotIn(tok, pd.text, f"A08: rejected feedback leaks into public object detail: {pd.brief()}")
        self.assertNotIn(tok, public_objects_text(self), "A08: rejected feedback leaks into the public object list")

    def test_a08_moderation_revision_conflicts(self):
        """[A08][S12] concurrent same-revision moderation: exactly one wins, other 409; stale revision -> 409, no change."""
        ed0, ed1 = editor(0), editor(1)
        obj = published(self, ed0)
        res = resident()
        tok, rtok = token("a08rev"), token("reply")
        receipt(self, submit(self, res, feedback_body(object_id=obj["id"], text=f"R10 гонка модерации {tok}")),
                "race submit")
        fb = staff_one(self, ed0, tok, "race staff queue")
        reply = f"R10 синтетический ответ {rtok}"
        barrier = threading.Barrier(2)
        results: dict = {}

        def go(name, client, action):
            try:
                barrier.wait(timeout=10)
                results[name] = helpers.moderate(client, fb, action,
                                                 public_reply=reply if action == "approve" else None)
            except Exception as exc:  # recorded and reported below
                results[name] = exc

        threads = [threading.Thread(target=go, args=("approve", ed0, "approve")),
                   threading.Thread(target=go, args=("reject", ed1, "reject"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        for name, r in results.items():
            self.assertNotIsInstance(r, Exception, f"{name} request failed at transport level: {r!r}")
        self.assertEqual(len(results), 2, f"both moderations must finish: {results}")
        briefs = {n: r.brief() for n, r in results.items()}
        winners = [n for n, r in results.items() if r.status in SUCCESS]
        self.assertEqual(len(winners), 1, f"concurrent moderation with the same expected_revision: exactly one "
                                          f"must win, got {briefs}")
        winner = winners[0]
        loser = "reject" if winner == "approve" else "approve"
        expect_error(self, results[loser], f"losing concurrent moderation ({loser}) must be 409", (409,))

        _, raw, last = public_feedback(self, obj["id"], "after race")
        if winner == "approve":
            self.assertIn(tok, raw, f"approve won the race but the item is not public: {last.brief()}")
        else:
            self.assertNotIn(tok, raw, f"reject won the race but the item is public: {last.brief()}")

        stale = helpers.moderate(ed0, fb, loser, public_reply=reply if loser == "approve" else None)
        expect_error(self, stale, f"{loser} with pre-moderation revision {fb.get('revision', 1)} must be 409", (409,))
        _, raw2, last2 = public_feedback(self, obj["id"], "after stale moderation")
        self.assertEqual(tok in raw2, tok in raw,
                         f"stale moderation changed public visibility (winner={winner}): {last2.brief()}")

    def test_a06_a08_restart_keeps_moderated_feedback(self):
        """[A06][A08] after a real server restart approved feedback + reply stay public, revision stays stale."""
        t = get_target()
        if not t.can_restart:
            raise unittest.SkipTest(f"target {t.name!r} cannot be restarted by the suite")
        ed = editor(0)
        obj = published(self, ed)
        res = resident()
        tok, rtok = token("a06fb"), token("reply")
        receipt(self, submit(self, res, feedback_body(object_id=obj["id"], text=f"R10 до рестарта {tok}")),
                "restart submit")
        fb = staff_one(self, ed, tok, "restart staff queue")
        reply = f"R10 синтетический ответ {rtok}"
        expect_ok(self, helpers.moderate(ed, fb, "approve", public_reply=reply), "approve before restart")
        before, _, last = public_feedback(self, obj["id"], "before restart")
        self.assertEqual(len(mine(before, tok)), 1, f"approved item not public before restart: {last.brief()}")

        t.restart()  # harness proves the old process stopped listening before the new one starts

        after, _, last = public_feedback(self, obj["id"], "after restart")
        hits = mine(after, tok)
        self.assertEqual(len(hits), 1, f"A06: approved feedback lost/duplicated by restart (feedback storage "
                                       f"not persistent?): {last.brief()}")
        self.assertTrue(any(reply in v for v in string_values(hits[0])),
                        f"A06: public_reply lost by restart: {hits[0]}")
        stale = helpers.moderate(editor(0), fb, "reject")
        expect_error(self, stale, "moderation with the pre-moderation revision after restart must be 409", (409,))
        _, raw, last = public_feedback(self, obj["id"], "after stale moderation post restart")
        self.assertIn(tok, raw, f"A06: stale moderation after restart hid the approved item: {last.brief()}")


class FeedbackAccessControl(unittest.TestCase):

    def test_s12_s07_moderation_needs_session_csrf_origin(self):
        """[S12][S07] moderation needs editor session + CSRF + same Origin; spoofed roles grant nothing."""
        ed = editor(0)
        obj = published(self, ed)
        res = resident()
        tok, ftok = token("s12"), token("forged")
        receipt(self, submit(self, res, feedback_body(object_id=obj["id"], text=f"R10 доступ к модерации {tok}")),
                "S12 submit")
        fb = staff_one(self, ed, tok, "S12 staff queue")
        path = f"/staff/feedback/{fb['id']}/moderate"
        body = {"expected_revision": fb.get("revision", 1), "action": "approve",
                "reason": "R10 попытка без прав", "public_reply": f"R10 подделка {ftok}"}
        who = editor_names()[0]
        spoof_body = dict(body, role="admin", actor=who, user={"name": who, "role": "editor"},
                          authenticated=True, is_editor=True)
        spoof_headers = {"X-Role": "editor", "X-User": who, "X-Forwarded-User": who,
                         "X-Remote-User": who, "X-Actor": who, "X-User-Role": "admin"}

        anon = get_target().client()
        anon.refresh_session()
        r = anon.post(path, spoof_body, headers=spoof_headers)
        assert_unauthenticated(self, r, bool(anon.csrf_token),
                               "S12/S07 anonymous moderate with role/actor in body and headers")

        thief = get_target().client()  # editor's CSRF token without the editor's cookie
        r = thief.post(path, body, csrf=ed.csrf_token)
        expect_error(self, r, "S12 editor's CSRF token without the session cookie must be refused", (401, 403))

        r = ed.post(path, body, csrf=None)
        expect_error(self, r, "S12 editor moderate without X-CSRF-Token must be 403", (403,))
        r = ed.post(path, body, csrf="r10-wrong-" + token("csrf"))
        expect_error(self, r, "S12 editor moderate with wrong X-CSRF-Token must be 403", (403,))
        r = ed.post(path, body, origin="http://evil.example")
        expect_error(self, r, "S12 editor moderate with foreign Origin must be 403", (403,))

        r = anon.get("/staff/feedback", headers=spoof_headers)
        expect_error(self, r, "S12/S07 anonymous staff queue read with spoofed role headers must be 401", (401,))
        self.assertNotIn(tok, r.text, f"S12: staff queue content leaks to anonymous: {r.brief()}")

        _, raw, last = public_feedback(self, obj["id"], "after refused moderations")
        self.assertNotIn(tok, raw, f"S12: a refused moderation published the item: {last.brief()}")
        self.assertNotIn(ftok, raw, f"S12: a refused moderation stored the forged reply: {last.brief()}")
        after = staff_one(self, ed, tok, "S12 staff queue after refused attempts")
        self.assertEqual(after.get("revision"), fb.get("revision"),
                         f"S12: refused moderation attempts changed the item revision: {fb} -> {after}")
        for key in ("moderation", "status", "public_reply"):  # whichever names the product uses
            self.assertEqual(after.get(key), fb.get(key), f"S12: refused attempts changed {key}: {fb} -> {after}")

        ok = helpers.moderate(ed, after, "approve", public_reply=f"R10 синтетический ответ {token('ok')}")
        expect_ok(self, ok, "S12 positive control: editor with session + CSRF + Origin can moderate")
        _, raw, last = public_feedback(self, obj["id"], "after legitimate approve")
        self.assertIn(tok, raw, f"S12 positive control: approved item not public: {last.brief()}")

    def test_s14_feedback_to_draft_and_missing_id_indistinguishable(self):
        """[S14][S09] feedback to a draft and to a missing id: same status, error.code, message; no draft data."""
        ed = editor(0)
        marker, secret = token("s14"), token("s14desc")
        draft = create_draft(self, ed, marker=marker, description=f"Черновик R10 {secret}")
        ghost = ghost_id(draft["id"])
        res = resident()
        tok_d, tok_g = token("todraft"), token("toghost")
        rd = submit(self, res, feedback_body(object_id=draft["id"], text=f"R10 к черновику {tok_d}"))
        rg = submit(self, res, feedback_body(object_id=ghost, text=f"R10 к несуществующему {tok_g}"))
        if rd.status == 403:
            self.fail(f"S14: feedback to a draft answered 403, which confirms the draft exists: {rd.brief()}")
        for r, what in ((rd, "draft"), (rg, "missing id")):
            self.assertNotIn(r.status, SUCCESS, f"S14: feedback accepted for a {what} object: {r.brief()}")
            expect_error(self, r, f"S14 feedback to {what}", (400, 404, 422))
            for needle in (marker, secret):
                self.assertNotIn(needle, r.text, f"S14: error for {what} leaks draft data {needle!r}: {r.brief()}")
        self.assertEqual(rd.status, rg.status, f"S14: draft vs missing distinguishable by status: "
                                               f"draft={rd.brief()} missing={rg.brief()}")
        self.assertEqual(error_code(rd), error_code(rg), f"S14: draft vs missing distinguishable by error.code: "
                                                         f"draft={rd.brief()} missing={rg.brief()}")
        self.assertEqual(error_message(rd, draft["id"]), error_message(rg, ghost),
                         f"S14: draft vs missing distinguishable by error.message: "
                         f"draft={rd.brief()} missing={rg.brief()}")
        self.assertEqual(staff_feedback(self, ed, tok_d), [], "S14: refused feedback to a draft was stored anyway")
        self.assertEqual(staff_feedback(self, ed, tok_g), [], "S14: refused feedback to a missing id was stored")

        anon = get_target().client()
        pd = anon.get(f"/objects/{draft['id']}/feedback")
        pg = anon.get(f"/objects/{ghost}/feedback")
        if pd.status == 403:
            self.fail(f"S14: public feedback list of a draft answered 403 (existence leak): {pd.brief()}")
        for r, what in ((pd, "draft"), (pg, "missing id")):
            self.assertNotIn(marker, r.text, f"S14: public feedback list of {what} leaks draft data: {r.brief()}")
            self.assertNotIn(secret, r.text, f"S14: public feedback list of {what} leaks draft data: {r.brief()}")
        self.assertEqual(pd.status, pg.status, f"S14: public feedback list distinguishes draft from missing: "
                                               f"draft={pd.brief()} missing={pg.brief()}")
        if pd.status == 404:
            expect_error(self, pd, "public feedback list of a draft", (404,))
            expect_error(self, pg, "public feedback list of a missing id", (404,))
            self.assertEqual(error_code(pd), error_code(pg), f"S14: error.code differs draft={pd.brief()} "
                                                             f"missing={pg.brief()}")
        else:
            NOTES.add(f"GET /objects/<draft|missing>/feedback answers {pd.status} (not 404)")
            expect_ok(self, pd, "public feedback list of a draft", statuses=(200,))
            expect_ok(self, pg, "public feedback list of a missing id", statuses=(200,))


class FeedbackValidation(unittest.TestCase):

    def test_a07_location_only_accepted_no_location_or_outside_astana_rejected(self):
        """[A07] object_id null + Astana Point accepted; no object and no geometry -> 400/422; Shymkent point -> 4xx, not stored."""
        ed = editor(0)
        res = resident()
        tok_ok, tok_none, tok_far = token("geo"), token("nogeo"), token("fargeo")
        r = submit(self, res, feedback_body(object_id=None, geometry=ASTANA_POINT, category="other",
                                            text=f"R10 обращение только с точкой {tok_ok}"))
        receipt(self, r, "A07 location-only submit (category other)")
        fb = staff_one(self, ed, tok_ok, "A07 location-only staff queue")
        if "geometry" in fb:
            self.assertEqual(fb["geometry"], ASTANA_POINT, f"A07: staff item geometry differs from submitted: {fb}")
        if "object_id" in fb:
            self.assertIsNone(fb["object_id"], f"A07: location-only item got an object link out of nowhere: {fb}")

        r = submit(self, res, feedback_body(object_id=None, geometry=None, text=f"R10 без места {tok_none}"))
        expect_error(self, r, "A07 feedback with neither object_id nor geometry", VALIDATION)

        r = submit(self, res, feedback_body(object_id=None, geometry=SHYMKENT_POINT,
                                            text=f"R10 точка в Шымкенте {tok_far}"))
        self.assertTrue(400 <= r.status < 500 and r.status not in (401, 403),
                        f"A07: point in Shymkent (outside Astana) must be refused as invalid input: {r.brief()}")
        expect_error(self, r, "A07 feedback outside Astana", (r.status,))
        if r.status not in VALIDATION:
            NOTES.add(f"feedback outside Astana refused with {r.status} (not 400/422)")
        self.assertEqual(staff_feedback(self, ed, tok_none), [], "A07: refused location-less feedback was stored")
        self.assertEqual(staff_feedback(self, ed, tok_far), [], "A07: refused out-of-city feedback was stored")

    def test_a07_unknown_category_rejected(self):
        """[A07] category outside roads/sidewalks/transport_stops/lighting/landscaping/other -> 400/422, not stored."""
        ed = editor(0)
        obj = published(self, ed)
        res = resident()
        tok = token("cat")
        r = submit(self, res, feedback_body(object_id=obj["id"], category="pothole", text=f"R10 категория {tok}"))
        expect_error(self, r, "A07 unknown feedback category", VALIDATION)
        self.assertEqual(staff_feedback(self, ed, tok), [], "A07: feedback with an unknown category was stored")

    def test_a07_duplicate_submission_not_silent(self):
        """[A07] identical resubmission is deduplicated or flagged, never a silent duplicate; original kept."""
        ed = editor(0)
        obj = published(self, ed)
        res = resident()
        tok = token("dup")
        body = feedback_body(object_id=obj["id"], text=f"R10 повторное одинаковое обращение {tok}")
        first = receipt(self, submit(self, res, body), "A07 first submit")
        r2 = submit(self, res, dict(body))
        stored = staff_feedback(self, ed, tok)
        self.assertGreaterEqual(len(stored), 1, "A07: the original feedback disappeared after a duplicate submit")
        if r2.status not in SUCCESS:
            expect_error(self, r2, "A07 duplicate submit refused explicitly", (400, 409, 422))
            self.assertEqual(len(stored), 1, f"A07: duplicate refused with {r2.status} but stored anyway: {stored}")
            NOTES.add(f"identical resubmission refused explicitly with {r2.status}")
            return
        d2 = expect_ok(self, r2, "A07 duplicate submit")
        self.assertIsInstance(d2, dict, r2.brief())
        flagged_reply = {k: v for k, v in d2.items() if FLAG_KEY.search(k) and v}
        if len(stored) == 1:
            NOTES.add("identical resubmission deduplicated into one staff item"
                      + (" (same receipt_id)" if d2.get("receipt_id") == first.get("receipt_id") else ""))
            return
        self.assertEqual(len(stored), 2, f"A07: two submits produced {len(stored)} staff items")
        flagged_staff = [it for it in stored
                         if any(FLAG_KEY.search(k) and v for k, v in it.items())]
        self.assertTrue(flagged_reply or flagged_staff,
                        f"A07: identical text submitted twice -> two unmarked pending items (silent duplicate); "
                        f"second reply {r2.brief()}; staff items {stored}")
        NOTES.add("duplicate kept as second item and marked "
                  + ("in the submit reply" if flagged_reply else "on the staff item"))


class FeedbackHtmlIsText(unittest.TestCase):

    def test_s10_html_payload_stays_literal_json_text(self):
        """[S10] HTML/script in feedback text, public_reply and object title stays literal text in JSON with nosniff."""
        ed = editor(0)
        marker = token("s10")
        title = f"R10 {XSS} {marker}"
        r = ed.post("/staff/objects", helpers.wrap_create(helpers.object_payload(marker=marker, title=title)))
        if r.status in VALIDATION:
            expect_error(self, r, "S10 object title with HTML refused as validation", VALIDATION)
            NOTES.add("object title containing HTML is rejected with 400/422 (plain-text policy)")
            obj = published(self, ed)
        else:
            data = expect_ok(self, r, "S10 create object with HTML in title")
            json_headers(self, r, "S10 create object")
            self.assertIsInstance(data.get("item") if isinstance(data, dict) else None, dict, r.brief())
            literal_or_escaped(self, data["item"].get("title"), title, "object title (staff)")
            obj = publish(self, ed, data["item"])
            pd = helpers.public_detail(obj["id"])
            pdata = expect_ok(self, pd, "S10 public detail", statuses=(200,))
            json_headers(self, pd, "S10 public object detail")
            literal_or_escaped(self, (pdata.get("item") or {}).get("title"), title, "object title (public)")

        res = resident()
        tok, rtok = token("s10fb"), token("s10reply")
        text = f"{XSS} {tok}"
        reply = f"{XSS} R10 ответ {rtok}"
        rr = submit(self, res, feedback_body(object_id=obj["id"], text=text))
        receipt(self, rr, "S10 submit")
        json_headers(self, rr, "S10 feedback receipt")

        q = ed.get("/staff/feedback")
        json_headers(self, q, "S10 staff feedback queue")
        fb = staff_one(self, ed, tok, "S10 staff queue")
        literal_or_escaped(self, value_with(self, fb, tok, "S10 staff item"), text, "feedback text (staff)")

        m = helpers.moderate(ed, fb, "approve", public_reply=reply)
        expect_ok(self, m, "S10 approve")
        items, _, last = public_feedback(self, obj["id"], "S10 public feedback")
        json_headers(self, last, "S10 public feedback list")
        hits = mine(items, tok)
        self.assertEqual(len(hits), 1, f"S10: approved HTML-bearing feedback not listed once: {last.brief()}")
        literal_or_escaped(self, value_with(self, hits[0], tok, "S10 public item"), text, "feedback text (public)")
        literal_or_escaped(self, value_with(self, hits[0], rtok, "S10 public item"), reply, "public_reply (public)")

        # the public object list is a second projection of the title, and error replies that may
        # reflect the request (path, filter) must be JSON + nosniff too, or they are reflected XSS
        anon, cursor, listed = get_target().client(), None, []
        for _ in range(400):
            lr = anon.get("/objects", query={"cursor": cursor} if cursor else None)
            ldata = expect_ok(self, lr, "S10 public object list", statuses=(200,))
            json_headers(self, lr, "S10 public object list")
            listed += [it for it in ldata.get("items", []) if isinstance(it, dict) and it.get("id") == obj["id"]]
            cursor = ldata.get("next_cursor")
            if cursor in (None, ""):
                break
        self.assertEqual(len(listed), 1, f"S10: published object not listed once in the public list: {listed}")
        if r.status not in VALIDATION and "title" in listed[0]:
            literal_or_escaped(self, listed[0]["title"], title, "object title (public list)")
        enc = quote(XSS, safe="")
        for path, query in ((f"/objects/{enc}", None), (f"/objects/{enc}/feedback", None),
                            (f"/r10-{enc}", None), ("/objects", {"kind": XSS})):
            with self.subTest(reflected=path, query=query):
                er = anon.get(path, query=query)
                self.assertTrue(400 <= er.status < 500, f"S10: HTML in path/query must be a 4xx: {er.brief()}")
                expect_error(self, er, f"S10 error reply for {path} {query}", (er.status,))
                json_headers(self, er, f"S10 error reply for {path} {query}")


if __name__ == "__main__":
    unittest.main()
