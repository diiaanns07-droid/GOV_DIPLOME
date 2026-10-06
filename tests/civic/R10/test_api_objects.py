"""R10 acceptance: civic-v1 object lifecycle over HTTP (staff write path + public read path).

Acceptance IDs: A01 A02 A03 A04 A05 A06 A09 A10 C02 C03 C04 C05 C09 (+S09 where the
public projection must not carry editor identity / internal notes).

Written only from CONTRACT.txt (PACK_SHA 9c2f5c0) and the R10 harness; it does not
look at how the R10 oracle or any product implements the API.

Contract readings used here (ambiguities resolved explicitly, see report):
  R1  `changes` in POST .../update is a nested partial object. `schedule` is always sent
      complete (unchanged keys repeated) so "merge" and "replace" readings agree.
  R2  Whether an update of a published object is public at once or needs a new
      /publish is not fixed by the contract. change_published() looks at the public
      detail first and, only if the change is not visible, makes ONE publish call with
      the same reason. Which behaviour applied is printed at the end, never failed on.
  R3  from/to are inclusive and match on planned_start/current_planned_end. Overlap vs
      containment is not fixed, so boundary tests use single-day objects (start == end)
      on and just outside the window, where both readings give the same answer.
  R4  changed_fields "mentions" a field when an entry contains the leaf name
      (schedule.current_planned_end, current_planned_end, schedule/current_planned_end).
  R5  Server-owned fields (id, publication, revision, updated_at, actor, city,
      schema_version) in a body may be ignored or the request rejected with 400/422
      (409 accepted where an id/revision clash is reported); either way nothing from
      the body may take effect.
  R6  "Публичный history показывает только опубликованные изменения": reasons and
      values written while the object was still a draft are not published changes and
      must not appear in any public response after publication.
  R7  original_planned_end after first publication: a change may be rejected, ignored,
      or applied with a public history entry naming the field and the reason. A silent
      public change is a FAIL.
  R8  C05 under a "staged" reading (update accepted, public data unchanged until
      publish) is tolerated, but then a publish without reason must not change public
      dates either: no public date change ever happens without a non-blank reason.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import random
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r10lib import contract, helpers  # noqa: E402
from r10lib.helpers import (  # noqa: E402
    create_draft, expect_error, expect_ok, public_detail, publish, staff_detail, token,
)
from r10lib.target import get_target  # noqa: E402

VALIDATION = (400, 422)
SUCCESS = (200, 201)
DAY = dt.timedelta(days=1)
OMIT = object()
NOTES: set[str] = set()
_RND = random.SystemRandom()


def tearDownModule():  # noqa: N802 (unittest hook name)
    if NOTES:
        sys.stderr.write("\n[test_api_objects] contract-open behaviour observed on this target:\n")
        for line in sorted(NOTES):
            sys.stderr.write(f"  - {line}\n")


# ---------------------------------------------------------------- small helpers
def editor(index: int = 0):
    """Fresh logged-in editor; falls back to a second session of editor 0."""
    t = get_target()
    return t.editor(index if index < len(t.editors) else 0)


def iso(value) -> str | None:
    return value.isoformat() if isinstance(value, dt.date) else value


def schedule(start, end, original=None, actual=None) -> dict:
    return {"planned_start": iso(start), "original_planned_end": iso(original if original is not None else end),
            "current_planned_end": iso(end), "actual_end": iso(actual)}


def fresh_window(years=(2041, 2089)):
    """A random 11-day window far from other tests' dates (default fixtures use 2026)."""
    first = dt.date(_RND.randint(*years), _RND.randint(1, 12), 10)
    return first, first + 10 * DAY


def parse_ts(value):
    if not isinstance(value, str):
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def recent(value, days: int = 2) -> bool:
    parsed = parse_ts(value)
    return parsed is not None and abs(parsed - dt.datetime.now(dt.timezone.utc)) < dt.timedelta(days=days)


def mentions(changed_fields, leaf: str) -> bool:
    return isinstance(changed_fields, list) and any(leaf in str(f) for f in changed_fields)


def sched_of(item) -> dict:
    s = item.get("schedule") if isinstance(item, dict) else None
    return s if isinstance(s, dict) else {}


def post_update(ed, obj_id, expected_revision, changes, reason=OMIT, extra=None):
    body = {"expected_revision": expected_revision, "changes": changes}
    if reason is not OMIT:
        body["reason"] = reason
    body.update(extra or {})
    return ed.post(f"/staff/objects/{obj_id}/update", body)


def staff_view(tc, ed, obj_id) -> tuple[dict, list]:
    r = staff_detail(ed, obj_id)
    data = expect_ok(tc, r, f"staff detail {obj_id}", statuses=(200,))
    tc.assertIsInstance(data, dict, r.brief())
    tc.assertIsInstance(data.get("item"), dict, f"staff detail without data.item: {r.brief()}")
    return data["item"], data.get("history")


def public_view(tc, obj_id, what="public detail"):
    r = public_detail(obj_id)
    data = expect_ok(tc, r, f"{what} {obj_id}", statuses=(200,))
    tc.assertIsInstance(data, dict, r.brief())
    tc.assertIsInstance(data.get("item"), dict, f"{what}: no data.item: {r.brief()}")
    tc.assertIsInstance(data.get("history"), list, f"{what}: data.history must be a list: {r.brief()}")
    return data["item"], data["history"], r


def walk(tc, client, path="/objects", query=None, what="public list", max_pages=400) -> dict:
    """Follow next_cursor to the end; fail on cursor loops. Returns items/ids/pages/text."""
    items, texts, cursor, seen, pages = [], [], None, set(), 0
    base = {k: iso(v) for k, v in (query or {}).items() if v is not None}
    while True:
        q = dict(base)
        if cursor is not None:
            q["cursor"] = cursor
        r = client.get(path, query=q)
        data = expect_ok(tc, r, f"{what}: GET {path} {q}", statuses=(200,))
        tc.assertIsInstance(data, dict, f"{what}: {r.brief()}")
        tc.assertIsInstance(data.get("items"), list, f"{what}: data.items must be a list: {r.brief()}")
        tc.assertIn("next_cursor", data, f"{what}: data.next_cursor missing: {r.brief()}")
        items.extend(data["items"])
        texts.append(r.text)
        pages += 1
        cursor = data.get("next_cursor")
        if cursor in (None, ""):
            break
        key = json.dumps(cursor, sort_keys=True)
        tc.assertNotIn(key, seen, f"{what}: next_cursor {cursor!r} repeated; pagination loops")
        seen.add(key)
        tc.assertLess(pages, max_pages, f"{what}: more than {max_pages} pages, pagination does not end")
    ids = [it.get("id") for it in items if isinstance(it, dict)]
    return {"items": items, "ids": ids, "pages": pages, "text": "\n".join(texts)}


def ghost_id(real_id: str) -> str:
    """An id of the same shape as a real one that almost surely does not exist."""
    if real_id.isdigit():
        return str(int(real_id) + 10 ** 9)
    tail = "ffff" if real_id[-4:] != "ffff" else "eeee"
    return real_id[:-4] + tail if len(real_id) > 4 else real_id + tail


def assert_publicly_hidden(tc, obj_id, markers, what):
    """[A02]/[A09] public detail is 404 (not 403/200), same error class as a missing id, no leak."""
    r = public_detail(obj_id)
    if r.status == 403:
        tc.fail(f"{what}: public detail answered 403, which confirms the hidden object exists "
                f"(contract: draft/archived not visible publicly -> 404): {r.brief()}")
    err = expect_error(tc, r, f"{what}: public detail must be 404", (404,))
    for m in markers:
        tc.assertNotIn(m, r.text, f"{what}: 404 body leaks hidden content {m!r}: {r.brief()}")
    g = public_detail(ghost_id(obj_id))
    if g.status == 404 and isinstance(err, dict) and isinstance(g.error, dict):
        tc.assertEqual(err.get("code"), g.error.get("code"),
                       f"{what}: hidden object and missing id give different error codes "
                       f"(existence oracle): hidden={r.brief()} missing={g.brief()}")


def make_public(tc, ed, staff_item, reason, visible, what):
    """Return (public Resp, latest staff item) once a change already saved on staff_item is public.

    Reading R2: if the change is not visible publicly, ONE publish call with the same
    reason is made and the behaviour is recorded in NOTES (not a failure by itself).
    """
    pub = public_detail(staff_item["id"])
    if pub.status == 200 and isinstance(pub.data, dict) and visible(pub.data.get("item") or {}):
        NOTES.add("update of a published object is public at once (no re-publish needed)")
        return pub, staff_item
    seen = pub.brief()
    rp = ed.post(f"/staff/objects/{staff_item['id']}/publish",
                 {"expected_revision": staff_item["revision"], "reason": reason})
    staff = expect_ok(tc, rp, f"{what}: change not public after update (public detail: {seen}); "
                              f"one re-publish attempt")["item"]
    NOTES.add("update of a published object became public only after a new /publish"
              + (" (public detail was 404 in between)" if pub.status == 404 else
                 " (old version stayed public in between)"))
    pub = public_detail(staff_item["id"])
    expect_ok(tc, pub, f"{what}: public detail after re-publish", statuses=(200,))
    return pub, staff


def change_published(tc, ed, obj, changes, reason, visible, what):
    """Update a published object (expected_revision=obj.revision) and make the change public."""
    r = post_update(ed, obj["id"], obj["revision"], changes, reason)
    staff = expect_ok(tc, r, f"{what}: update of published object")["item"]
    return make_public(tc, ed, staff, reason, visible, what)


def staff_problems(item) -> list[str]:
    """check_object for an editor DTO: staff-only keys are allowed there."""
    return [p for p in contract.check_object(item, strict_keys=False)
            if not p.startswith("sensitive-looking key")]


def check_public_history(tc, history, obj_id, what):
    for entry in history:
        tc.assertEqual(contract.check_history_entry(entry, public=True, object_id=obj_id), [],
                       f"{what}: public history entry breaks allowlist: {entry}")
        for field in entry.get("changed_fields") or []:
            tc.assertIsNone(contract.SENSITIVE_KEY.search(str(field)),
                            f"{what}: public history names a non-public field {field!r}: {entry}")
            top = str(field).replace("/", ".").split(".")[0]
            if top not in contract.OBJECT_FIELDS:
                NOTES.add(f"public history changed_fields uses a non-field name {field!r}")


# ================================================================ main path
class ObjectLifecycle(unittest.TestCase):

    def test_a01_create_draft_server_assigns_identity(self):
        """[A01][C03] create -> draft with server id, revision>=1, server updated_at, fields stored as sent."""
        ed = editor(0)
        payload = helpers.object_payload(marker=token("a01"))
        r = ed.post("/staff/objects", helpers.wrap_create(payload))
        data = expect_ok(self, r, "create draft")
        item = data.get("item") if isinstance(data, dict) else None
        self.assertIsInstance(item, dict, f"create: data.item missing: {r.brief()}")
        self.assertTrue(isinstance(item.get("id"), str) and item["id"], f"no server id: {r.brief()}")
        rev = item.get("revision")
        self.assertTrue(isinstance(rev, int) and not isinstance(rev, bool) and rev >= 1, f"revision: {r.brief()}")
        self.assertEqual(item.get("publication"), "draft", f"new object must be a draft: {r.brief()}")
        self.assertTrue(recent(item.get("updated_at")),
                        f"updated_at must be a server timestamp near now: {item.get('updated_at')!r}")
        self.assertEqual(staff_problems(item), [], f"staff DTO breaks civic-v1: {r.brief()}")
        for key in sorted(contract.CLIENT_EDITABLE):
            self.assertEqual(item.get(key), payload[key], f"create altered client field {key!r}: {r.brief()}")

        staff_item, history = staff_view(self, ed, item["id"])
        self.assertEqual((staff_item["id"], staff_item["revision"], staff_item["title"]),
                         (item["id"], item["revision"], payload["title"]), "staff detail differs from create reply")
        self.assertIsInstance(history, list, "staff detail must carry data.history list")

        second = create_draft(self, ed)
        self.assertNotEqual(second["id"], item["id"], "two creates returned the same id")
        staff_ids = walk(self, ed, "/staff/objects", what="staff list")["ids"]
        for oid in (item["id"], second["id"]):
            self.assertEqual(staff_ids.count(oid), 1, f"staff list must contain draft {oid} exactly once")

    def test_a02_draft_invisible_publicly(self):
        """[A02] draft: absent from every public list page (filtered or not), detail 404, nothing leaks."""
        ed = editor(0)
        first, last = fresh_window()
        marker, secret = token("a02"), token("a02desc")
        item = create_draft(self, ed, marker=marker, description=f"Черновик R10 {secret}",
                            schedule=schedule(first + DAY, first + 3 * DAY))
        assert_publicly_hidden(self, item["id"], [marker, secret], "draft")
        anon = get_target().client()
        for query in (None, {"from": first, "to": last}, {"kind": "roadworks", "from": first, "to": last},
                      {"status": "planned", "from": first, "to": last}):
            with self.subTest(query=query):
                lst = walk(self, anon, query=query)
                self.assertNotIn(item["id"], lst["ids"], f"draft listed publicly with {query}")
                self.assertNotIn(marker, lst["text"], f"draft title leaks into public list {query}")
                self.assertNotIn(secret, lst["text"], f"draft description leaks into public list {query}")
        staff_item, _ = staff_view(self, ed, item["id"])  # positive control: it does exist
        self.assertEqual(staff_item.get("publication"), "draft")

    def test_a03_publish_makes_object_public_with_contract_dto(self):
        """[A03] publish -> object in public list/detail, public DTO passes civic-v1 public checks."""
        ed = editor(0)
        first, last = fresh_window()
        marker = token("a03")
        draft = create_draft(self, ed, marker=marker, schedule=schedule(first + DAY, first + 4 * DAY))
        pub = publish(self, ed, draft)
        self.assertEqual(pub.get("publication"), "published", f"publish reply: {pub}")
        self.assertEqual(pub.get("id"), draft["id"], "publish changed the id")
        self.assertGreaterEqual(pub.get("revision", 0), draft["revision"])

        item, history, r = public_view(self, draft["id"])
        self.assertEqual(contract.check_object(item, public=True), [], f"public DTO: {r.brief()}")
        self.assertEqual(item["id"], draft["id"])
        for key in sorted(contract.CLIENT_EDITABLE):
            self.assertEqual(item.get(key), draft.get(key), f"public {key!r} differs from what the editor stored")
        check_public_history(self, history, draft["id"], "A03")

        anon = get_target().client()
        lst = walk(self, anon, query={"from": first, "to": last})
        self.assertEqual(lst["ids"].count(draft["id"]), 1, "published object must be listed exactly once in its window")
        listed = next(it for it in lst["items"] if isinstance(it, dict) and it.get("id") == draft["id"])
        self.assertIn(listed.get("publication", "published"), ("published",), f"list item: {listed}")
        leaky = [k for k in listed if contract.SENSITIVE_KEY.search(k)]
        self.assertEqual(leaky, [], f"public list item exposes sensitive-looking keys: {listed}")
        full = walk(self, anon)
        self.assertEqual(full["ids"].count(draft["id"]), 1, "published object must appear once in the default public list")

    def test_a04_date_change_with_reason_is_public_and_explained(self):
        """[A04][C05] new current_planned_end with reason: public date changes, original kept, history explains."""
        ed = editor(0)
        first, last = fresh_window()
        start, orig_end, new_end = first, first + 6 * DAY, first + 8 * DAY
        pub = publish(self, ed, create_draft(self, ed, schedule=schedule(start, orig_end)))
        reason = f"R10: подрядчик перенёс срок {token('why')}"
        resp, staff = change_published(
            self, ed, pub, {"schedule": schedule(start, new_end, original=orig_end)}, reason,
            lambda it: sched_of(it).get("current_planned_end") == iso(new_end), "A04")
        item, history = resp.data["item"], resp.data["history"]
        self.assertEqual(contract.check_object(item, public=True), [], resp.brief())
        s = sched_of(item)
        self.assertEqual(s.get("current_planned_end"), iso(new_end), resp.brief())
        self.assertEqual(s.get("original_planned_end"), iso(orig_end),
                         f"original_planned_end overwritten by a current_planned_end change: {s}")
        self.assertEqual(s.get("planned_start"), iso(start), f"planned_start changed: {s}")
        self.assertGreater(item["revision"], pub["revision"], "revision must grow after a change")
        self.assertIsNotNone(parse_ts(pub.get("updated_at")), f"publish reply updated_at: {pub.get('updated_at')!r}")
        self.assertGreaterEqual(parse_ts(item["updated_at"]), parse_ts(pub["updated_at"]), "updated_at went back")

        check_public_history(self, history, pub["id"], "A04")
        touching = [e for e in history if mentions(e.get("changed_fields"), "current_planned_end")]
        self.assertTrue(touching, f"no public history entry names current_planned_end: {history}")
        explained = [e for e in touching if reason in str(e.get("reason"))]
        self.assertTrue(explained, f"public history entry for the date change lacks the reason {reason!r}: {touching}")
        self.assertFalse(mentions(explained[0]["changed_fields"], "original_planned_end"),
                         f"history claims original_planned_end changed, it did not: {explained[0]}")

        lst = walk(self, get_target().client(), query={"from": first, "to": last})
        listed = [it for it in lst["items"] if isinstance(it, dict) and it.get("id") == pub["id"]]
        self.assertEqual(len(listed), 1, "changed object must stay listed once in its window")
        if "schedule" in listed[0]:
            self.assertEqual(sched_of(listed[0]).get("current_planned_end"), iso(new_end),
                             f"public list shows a stale date: {listed[0]}")

    def test_a05_draft_era_changes_never_reach_public_history(self):
        """[A05] contract reading "только опубликованные изменения": draft-era reasons/values never public."""
        ed = editor(0)
        first, _ = fresh_window()
        draft_title, marker = token("a05draft"), token("a05")
        draft_reasons = [f"R10 черновая причина {token('dr1')}", f"R10 черновая причина {token('dr2')}"]
        item = create_draft(self, ed, title=f"R10 черновое название {draft_title}",
                            schedule=schedule(first, first + 3 * DAY))
        r = post_update(ed, item["id"], item["revision"], {"title": f"R10 публичное название {marker}"},
                        draft_reasons[0])
        item = expect_ok(self, r, "draft title update")["item"]
        r = post_update(ed, item["id"], item["revision"], {"schedule": schedule(first, first + 5 * DAY)},
                        draft_reasons[1])
        item = expect_ok(self, r, "draft schedule update (before first publication)")["item"]
        pub = publish(self, ed, item, reason=f"R10: первая публикация {token('pr')}")

        public_item, history, resp = public_view(self, pub["id"])
        self.assertIn(marker, public_item.get("title", ""))
        self.assertEqual(sched_of(public_item).get("original_planned_end"), iso(first + 5 * DAY),
                         "original_planned_end must be the value at first publication")
        check_public_history(self, history, pub["id"], "A05 after publish")
        for secret in [draft_title] + draft_reasons:
            self.assertNotIn(secret, resp.text, f"draft-era text {secret!r} is public: {resp.brief()}")

        # positive control: a change made after publication IS explained publicly
        after_reason = f"R10: перенос после публикации {token('ar')}"
        resp2, _ = change_published(
            self, ed, pub, {"schedule": schedule(first, first + 7 * DAY, original=first + 5 * DAY)}, after_reason,
            lambda it: sched_of(it).get("current_planned_end") == iso(first + 7 * DAY), "A05")
        history2 = resp2.data["history"]
        check_public_history(self, history2, pub["id"], "A05 after change")
        self.assertTrue(any(after_reason in str(e.get("reason")) for e in history2),
                        f"post-publication change missing from public history: {history2}")
        for secret in [draft_title] + draft_reasons:
            self.assertNotIn(secret, resp2.text, f"draft-era text {secret!r} became public later: {resp2.brief()}")

    def test_a05_s09_no_editor_identity_or_internal_notes_publicly(self):
        """[A05][S09] editor usernames and internal notes never appear in public list/detail/history."""
        t = get_target()
        usernames = [u for u, _ in t.editors]
        ed = editor(0)
        first, last = fresh_window()
        internal = [token("internal1"), token("internal2"), token("internalreason")]
        payload = helpers.object_payload(marker=token("a05s09"), schedule=schedule(first, first + 2 * DAY))
        payload["internal_notes"] = f"R10 служебная заметка {internal[0]}"
        r = ed.post("/staff/objects", helpers.wrap_create(payload))
        if r.status in VALIDATION:
            NOTES.add("create rejects an internal_notes field (no internal-notes leak path to test)")
            payload.pop("internal_notes")
            r = ed.post("/staff/objects", helpers.wrap_create(payload))
        item = expect_ok(self, r, "create")["item"]
        pub = publish(self, ed, item)
        resp, staff = change_published(
            self, ed, pub, {"schedule": schedule(first, first + 4 * DAY, original=first + 2 * DAY)},
            f"R10: перенос {token('s09')}", lambda it: sched_of(it).get("current_planned_end") == iso(first + 4 * DAY),
            "S09")
        if "internal_notes" in payload:
            ri = post_update(ed, pub["id"], staff["revision"], {"internal_notes": f"R10 правка {internal[1]}"},
                             f"R10 служебная причина {internal[2]}")
            if ri.status in SUCCESS:
                NOTES.add("editor can store internal_notes; checked they stay out of public responses")
                staged = ri.data["item"]
                shown = public_detail(pub["id"])
                if shown.status == 200 and (shown.data or {}).get("item", {}).get("revision") != staged.get("revision"):
                    # staged reading (R2): publish too, so a leak at publish time is also caught
                    ed.post(f"/staff/objects/{pub['id']}/publish",
                            {"expected_revision": staged["revision"], "reason": "R10: публикация после правки"})
        anon = t.client()
        texts = {"public detail": public_detail(pub["id"]).text,
                 "public list (window)": walk(self, anon, query={"from": first, "to": last})["text"]}
        for item_ in walk(self, anon)["items"]:
            if isinstance(item_, dict) and item_.get("id") == pub["id"]:
                texts["default public list item"] = json.dumps(item_, ensure_ascii=False)
        for where, text in texts.items():
            for name in usernames:
                self.assertNotIn(name, text, f"{where} exposes editor username {name!r}: {text[:400]!r}")
            for secret in internal:
                self.assertNotIn(secret, text, f"{where} exposes internal notes/reason {secret!r}")
            self.assertNotIn("internal_notes", text, f"{where} names internal_notes")
        _, history, _ = public_view(self, pub["id"])
        check_public_history(self, history, pub["id"], "S09")

    def test_a09_archive_hides_publicly_staff_keeps(self):
        """[A09] archive -> public list/detail hide it (404), staff still sees intact archived object."""
        ed = editor(0)
        first, last = fresh_window()
        marker = token("a09")
        pub = publish(self, ed, create_draft(self, ed, marker=marker, schedule=schedule(first, first + 2 * DAY)))
        public_view(self, pub["id"], "before archive")  # positive control
        r = helpers.archive(ed, pub, reason=f"R10: архив {token('arch')}")
        archived = expect_ok(self, r, "archive")["item"]
        self.assertEqual(archived.get("publication"), "archived", r.brief())
        assert_publicly_hidden(self, pub["id"], [marker], "archived object")
        lst = walk(self, get_target().client(), query={"from": first, "to": last})
        self.assertNotIn(pub["id"], lst["ids"], "archived object still in public list")
        self.assertNotIn(marker, lst["text"], "archived title still in public list")
        staff_item, history = staff_view(self, ed, pub["id"])
        self.assertEqual(staff_item.get("publication"), "archived")
        for key in ("title", "schedule", "budget", "geometry", "kind", "status"):
            self.assertEqual(staff_item.get(key), pub.get(key), f"archive altered {key!r}")
        self.assertIsInstance(history, list)
        staff_ids = walk(self, ed, "/staff/objects", what="staff list")["ids"]
        self.assertEqual(staff_ids.count(pub["id"]), 1, "archived object missing from staff list")

    def test_c09_no_physical_delete(self):
        """[C09] DELETE (and /delete) on objects -> 404/405 (anon also 401/403); objects still exist."""
        ed = editor(0)
        anon = get_target().client()
        pub = publish(self, ed, create_draft(self, ed))
        draft = create_draft(self, ed)
        attempts = [
            (ed, "DELETE", f"/staff/objects/{pub['id']}", (404, 405)),
            (ed, "DELETE", f"/staff/objects/{draft['id']}", (404, 405)),
            (ed, "POST", f"/staff/objects/{pub['id']}/delete", (404, 405)),
            (anon, "DELETE", f"/objects/{pub['id']}", (401, 403, 404, 405)),
            (anon, "DELETE", f"/staff/objects/{pub['id']}", (401, 403, 404, 405)),
        ]
        for client, method, path, statuses in attempts:
            with self.subTest(method=method, path=path, anonymous=client is anon):
                r = client.call(method, path, {} if method == "POST" else None)
                expect_error(self, r, f"{method} {path}", statuses)
        for obj in (pub, draft):
            staff_item, _ = staff_view(self, ed, obj["id"])
            self.assertEqual((staff_item["revision"], staff_item["publication"]),
                             (obj["revision"], obj["publication"]), "delete attempt changed the object")
        public_view(self, pub["id"], "published object after delete attempts")


# ================================================================ C02 server-owned fields
class ServerOwnedFields(unittest.TestCase):
    FORGED_TS = "2001-01-01T00:00:00+00:00"

    def test_c02_create_ignores_server_owned_fields(self):
        """[C02][A01] create body id/publication/revision/updated_at/actor/city/schema are not trusted."""
        ed = editor(0)
        forged_id, marker = token("forged"), token("c02c")
        payload = helpers.object_payload(marker=marker)
        payload.update({"id": forged_id, "publication": "published", "revision": 77, "updated_at": self.FORGED_TS,
                        "actor": "Аким города", "public_actor_label": "Аким города", "city": "shymkent",
                        "schema_version": "civic-v0"})
        r = ed.post("/staff/objects", helpers.wrap_create(payload))
        if r.status in VALIDATION:
            expect_error(self, r, "create with server-owned fields", VALIDATION)
            NOTES.add("create rejects bodies carrying server-owned fields (400/422)")
        else:
            item = expect_ok(self, r, "create with server-owned fields")["item"]
            self.assertNotEqual(item.get("id"), forged_id, "server took id from the body")
            self.assertEqual(item.get("publication"), "draft", f"publication taken from body: {r.brief()}")
            self.assertNotEqual(item.get("revision"), 77, "revision taken from body")
            self.assertNotEqual(item.get("updated_at"), self.FORGED_TS, "updated_at taken from body")
            self.assertTrue(recent(item.get("updated_at")), f"updated_at not server time: {item.get('updated_at')}")
            self.assertEqual((item.get("city"), item.get("schema_version")), ("astana", "civic-v1"))
            assert_publicly_hidden(self, item["id"], [marker], "draft created with publication=published")
        assert_publicly_hidden(self, forged_id, [marker], "forged id")
        self.assertEqual(staff_detail(ed, forged_id).status, 404, "an object exists under the body-supplied id")

    def test_c02_create_with_existing_id_cannot_overwrite_published(self):
        """[C02] create with body id of an existing published object never replaces/changes that object."""
        ed = editor(0)
        victim = publish(self, ed, create_draft(self, ed, marker=token("victim")))
        before, before_hist, _ = public_view(self, victim["id"])
        intruder = token("intruder")
        payload = helpers.object_payload(marker=intruder, status="cancelled")
        payload.update({"id": victim["id"], "publication": "published", "revision": victim["revision"]})
        r = ed.post("/staff/objects", helpers.wrap_create(payload))
        if r.status in SUCCESS:
            created = expect_ok(self, r, "create with existing id")["item"]
            self.assertNotEqual(created.get("id"), victim["id"], "create reused an existing object's id")
            assert_publicly_hidden(self, created["id"], [intruder], "object created with forged id")
        else:
            expect_error(self, r, "create with existing id", VALIDATION + (409,))
        after, after_hist, resp = public_view(self, victim["id"])
        self.assertEqual(after, before, f"published object changed by a create with its id: {resp.brief()}")
        self.assertEqual(len(after_hist), len(before_hist), "history of the existing object changed")
        self.assertNotIn(intruder, resp.text)
        staff_item, _ = staff_view(self, ed, victim["id"])
        self.assertEqual((staff_item["title"], staff_item["revision"]), (victim["title"], victim["revision"]))

    def test_c02_update_ignores_server_owned_fields(self):
        """[C02] update with publication/id/revision/updated_at in changes or body cannot publish/rename/rewind."""
        ed = editor(0)
        item = create_draft(self, ed, marker=token("c02u"))
        other = create_draft(self, ed, marker=token("c02other"))
        new_title = f"R10 правка {token('c02t')}"
        forged = {"publication": "published", "id": other["id"], "revision": 99, "updated_at": self.FORGED_TS,
                  "city": "shymkent", "schema_version": "civic-v0"}
        changes = dict(forged, title=new_title)
        r = post_update(ed, item["id"], item["revision"], changes, "R10 попытка подмены служебных полей",
                        extra={"publication": "published", "actor": "admin", "id": other["id"], "revision": 99})
        staff_item, _ = staff_view(self, ed, item["id"])
        if r.status in VALIDATION + (409,):
            expect_error(self, r, "update with server-owned fields", VALIDATION + (409,))
            NOTES.add(f"update rejects server-owned fields in changes/body ({r.status})")
            self.assertEqual((staff_item["title"], staff_item["revision"]), (item["title"], item["revision"]),
                             "rejected update still changed the object")
        else:
            got = expect_ok(self, r, "update with server-owned fields")["item"]
            self.assertEqual(got.get("id"), item["id"], "update renamed the object from body id")
            self.assertEqual(got.get("revision"), item["revision"] + 1, f"revision not server-assigned: {r.brief()}")
            self.assertNotEqual(got.get("updated_at"), self.FORGED_TS, "updated_at taken from body")
            self.assertEqual((got.get("city"), got.get("schema_version")), ("astana", "civic-v1"))
        self.assertEqual(staff_item.get("publication"), "draft", "update body published the object")
        self.assertEqual(staff_item.get("id"), item["id"])
        assert_publicly_hidden(self, item["id"], [new_title], "draft after forged publication=published")
        other_now, _ = staff_view(self, ed, other["id"])
        self.assertEqual((other_now["title"], other_now["revision"]), (other["title"], other["revision"]),
                         "update with body id modified a different object")

    def test_c02_public_actor_label_not_taken_from_body(self):
        """[C02][A05] actor/public_actor_label sent in an update body never shows in public history."""
        ed = editor(0)
        first, _ = fresh_window()
        pub = publish(self, ed, create_draft(self, ed, schedule=schedule(first, first + 2 * DAY)))
        fake = token("fakeactor")
        label = f"Аким города {fake}"
        new_end = first + 5 * DAY
        reason = f"R10: перенос {token('c02a')}"
        r = post_update(ed, pub["id"], pub["revision"],
                        {"schedule": schedule(first, new_end, original=first + 2 * DAY)}, reason,
                        extra={"actor": label, "public_actor_label": label, "user": {"name": label, "role": "admin"}})
        if r.status in VALIDATION:
            NOTES.add("update rejects unknown top-level body keys such as actor (400/422)")
            _, _, resp = public_view(self, pub["id"])
            self.assertNotIn(fake, resp.text)
            return
        staff = expect_ok(self, r, "update with actor in body")["item"]
        make_public(self, ed, staff, reason,
                    lambda it: sched_of(it).get("current_planned_end") == iso(new_end), "C02 actor")
        _, history, resp = public_view(self, pub["id"])
        self.assertNotIn(fake, resp.text, f"actor label from request body is public: {resp.brief()}")
        _, staff_hist = staff_view(self, ed, pub["id"])
        self.assertNotIn(fake, json.dumps(staff_hist, ensure_ascii=False), "staff history recorded body-supplied actor")


# ================================================================ C03 unknown stays unknown
class UnknownStaysUnknown(unittest.TestCase):

    def test_c03_null_schedule_budget_geometry_survive_publish_and_update(self):
        """[C03][A03] null dates/budget/geometry stay null (not today/0) through create, publish, unrelated update."""
        ed = editor(0)
        nulls = {"planned_start": None, "original_planned_end": None, "current_planned_end": None, "actual_end": None}
        item = create_draft(self, ed, status="unknown", geometry=None, geometry_precision="unknown", schedule=nulls,
                            budget={"amount_kzt": None, "basis": "unknown", "source_id": None},
                            responsible={"organization": None, "public_contact": None})

        def check(obj, where):
            self.assertEqual(obj.get("schedule"), nulls, f"{where}: unknown dates were filled in: {obj.get('schedule')}")
            budget = obj.get("budget") or {}
            self.assertIsNone(budget.get("amount_kzt"), f"{where}: unknown budget masked: {budget}")
            self.assertEqual(budget.get("basis"), "unknown", f"{where}: budget basis invented: {budget}")
            self.assertIsNone(obj.get("geometry"), f"{where}: geometry invented: {obj.get('geometry')}")
            self.assertEqual(obj.get("status"), "unknown", f"{where}: status invented")
            self.assertEqual(obj.get("responsible"), {"organization": None, "public_contact": None}, where)

        check(item, "create reply")
        pub = publish(self, ed, item)
        check(pub, "publish reply")
        public_item, _, resp = public_view(self, item["id"])
        self.assertEqual(contract.check_object(public_item, public=True), [], resp.brief())
        check(public_item, "public detail after publish")
        new_desc = f"Синтетическая запись R10, уточнено описание {token('c03')}"
        resp, staff = change_published(self, ed, pub, {"description": new_desc}, "R10: уточнение описания",
                                       lambda it: it.get("description") == new_desc, "C03")
        check(resp.data["item"], "public detail after unrelated update")
        check(staff_view(self, ed, item["id"])[0], "staff detail after unrelated update")

    def test_c03_a10_no_status_or_actual_end_computed_from_dates(self):
        """[C03][A10] past dates do not change status or set actual_end; status filter uses stored status."""
        ed = editor(0)
        first, last = fresh_window(years=(2001, 2024))
        item = create_draft(self, ed, status="in_progress", schedule=schedule(first + DAY, first + 3 * DAY))
        pub = publish(self, ed, item)
        public_item, _, _ = public_view(self, pub["id"])
        self.assertEqual(public_item.get("status"), "in_progress", "status computed from past dates")
        self.assertIsNone(sched_of(public_item).get("actual_end"), "actual_end invented from past dates")
        anon = get_target().client()
        window = {"from": first, "to": last}
        self.assertEqual(walk(self, anon, query=dict(window, status="in_progress"))["ids"].count(pub["id"]), 1,
                         "status=in_progress filter misses an in_progress object with past dates")
        self.assertNotIn(pub["id"], walk(self, anon, query=dict(window, status="completed"))["ids"],
                         "status=completed filter returns an object whose stored status is in_progress")

        r = post_update(ed, pub["id"], pub["revision"], {"status": "completed"}, "R10: работы завершены (синтетика)")
        if r.status in VALIDATION:
            NOTES.add("status=completed without actual_end is rejected (nothing auto-filled)")
            expect_error(self, r, "status completed without actual_end", VALIDATION)
            return
        staff = expect_ok(self, r, "status -> completed")["item"]
        resp, _ = make_public(self, ed, staff, "R10: работы завершены (синтетика)",
                              lambda it: it.get("status") == "completed", "C03 status")
        done = resp.data["item"]
        self.assertEqual(done.get("status"), "completed")
        self.assertIsNone(sched_of(done).get("actual_end"),
                          f"actual_end auto-set when status became completed: {sched_of(done)}")
        self.assertIsNone(sched_of(staff_view(self, ed, pub["id"])[0]).get("actual_end"),
                          "staff record got an invented actual_end")


# ================================================================ C04/C05 revisions and reasons
class RevisionsAndReasons(unittest.TestCase):

    def test_c04_stale_or_missing_revision_rejected_without_change(self):
        """[C04] stale/future/missing expected_revision on update, stale on publish/archive -> rejected, no change."""
        ed = editor(0)
        marker = token("c04")
        item = create_draft(self, ed, marker=marker)
        title1 = f"R10 правка 1 {marker}"
        cur = expect_ok(self, post_update(ed, item["id"], item["revision"], {"title": title1}, "R10 правка 1"),
                        "first update")["item"]

        def unchanged(what):
            now, _ = staff_view(self, ed, item["id"])
            self.assertEqual((now["title"], now["revision"], now["publication"]),
                             (title1, cur["revision"], "draft"), f"{what} changed the object")

        r = post_update(ed, item["id"], item["revision"], {"title": "R10 STALE"}, "R10 stale")
        expect_error(self, r, "stale expected_revision", (409,))
        unchanged("stale update")
        r = post_update(ed, item["id"], cur["revision"] + 5, {"title": "R10 FUTURE"}, "R10 future")
        expect_error(self, r, "future expected_revision", (409,) + VALIDATION)
        unchanged("future-revision update")
        r = ed.post(f"/staff/objects/{item['id']}/update", {"changes": {"title": "R10 NOREV"}, "reason": "R10"})
        expect_error(self, r, "update without expected_revision", (409,) + VALIDATION)
        unchanged("update without expected_revision")
        r = ed.post(f"/staff/objects/{item['id']}/publish", {"expected_revision": item["revision"], "reason": "R10"})
        expect_error(self, r, "stale publish", (409,))
        unchanged("stale publish")
        assert_publicly_hidden(self, item["id"], [marker], "draft after stale publish")

        pub = publish(self, ed, cur)
        r = ed.post(f"/staff/objects/{item['id']}/archive", {"expected_revision": item["revision"], "reason": "R10"})
        expect_error(self, r, "stale archive", (409,))
        now, _ = staff_view(self, ed, item["id"])
        self.assertEqual((now["publication"], now["revision"]), ("published", pub["revision"]),
                         "stale archive changed the object")
        public_view(self, item["id"], "published object after stale archive")

    def test_c04_concurrent_same_revision_exactly_one_wins(self):
        """[C04] two editors, same expected_revision, parallel -> one 2xx + one 409, revision+1, one history entry."""
        ed_a, ed_b = editor(0), editor(1)
        item = create_draft(self, ed_a, marker=token("c04race"))
        for round_no in range(3):
            with self.subTest(round=round_no):
                cur, hist_before = staff_view(self, ed_a, item["id"])
                values = {"a": f"R10 гонка A{round_no} {token('ra')}", "b": f"R10 гонка B{round_no} {token('rb')}"}
                barrier, results = threading.Barrier(2, timeout=10), {}

                def worker(name, client):
                    try:
                        barrier.wait()
                        results[name] = post_update(client, cur["id"], cur["revision"], {"title": values[name]},
                                                    f"R10 параллельная правка {name}")
                    except Exception as exc:  # recorded and asserted below
                        results[name] = exc

                threads = [threading.Thread(target=worker, args=("a", ed_a)),
                           threading.Thread(target=worker, args=("b", ed_b))]
                for th in threads:
                    th.start()
                for th in threads:
                    th.join(30)
                for name in "ab":
                    self.assertNotIsInstance(results.get(name), (Exception, type(None)), f"worker {name}: {results}")
                statuses = sorted(results[n].status for n in "ab")
                winners = [n for n in "ab" if results[n].status in SUCCESS]
                self.assertEqual(len(winners), 1, f"exactly one update must win: {[results[n].brief() for n in 'ab']}")
                loser = "b" if winners[0] == "a" else "a"
                self.assertEqual(results[loser].status, 409, f"loser must get 409, statuses={statuses}: "
                                                             f"{results[loser].brief()}")
                expect_error(self, results[loser], "losing concurrent update", (409,))
                final, hist_after = staff_view(self, ed_a, item["id"])
                self.assertEqual(final["revision"], cur["revision"] + 1, "revision must grow by exactly one")
                self.assertEqual(final["title"], values[winners[0]], "final title is not the winner's value")
                if isinstance(hist_after, list):
                    new_entries = [e for e in hist_after if isinstance(e, dict) and e.get("revision") == final["revision"]]
                    self.assertEqual(len(new_entries), 1, f"expected one history entry for revision "
                                                          f"{final['revision']}: {hist_after}")
                    self.assertFalse(any(isinstance(e, dict) and isinstance(e.get("revision"), int)
                                         and e["revision"] > final["revision"] for e in hist_after),
                                     f"history has a revision beyond the final one: {hist_after}")
                    if isinstance(hist_before, list):
                        self.assertEqual(len(hist_after), len(hist_before) + 1,
                                         "concurrent pair must add exactly one history entry")
                else:
                    self.fail(f"staff detail has no history list: {hist_after!r}")

    def test_c05_reason_required_for_public_date_change(self):
        """[C05] published object: no public date change without a non-blank reason (update or publish)."""
        ed = editor(0)
        first, _ = fresh_window()
        pub = publish(self, ed, create_draft(self, ed, schedule=schedule(first, first + 4 * DAY)))
        base = sched_of(public_view(self, pub["id"])[0])
        attempts = [("current_planned_end", OMIT), ("current_planned_end", None), ("current_planned_end", ""),
                    ("current_planned_end", "   \t"), ("planned_start", OMIT)]
        for field, reason in attempts:
            with self.subTest(field=field, reason="<missing>" if reason is OMIT else repr(reason)):
                cur, _ = staff_view(self, ed, pub["id"])
                new = dict(base)
                if field == "current_planned_end":
                    new["current_planned_end"] = iso(first + 9 * DAY)
                else:
                    new["planned_start"] = iso(first - 3 * DAY)
                r = post_update(ed, pub["id"], cur["revision"], {"schedule": new}, reason)
                if r.status in VALIDATION:
                    expect_error(self, r, "date change without reason", VALIDATION)
                    after, _ = staff_view(self, ed, pub["id"])
                    self.assertEqual(after["revision"], cur["revision"], "rejected update still bumped revision")
                elif r.status in SUCCESS:
                    NOTES.add("update without reason on a published object is accepted as a staged change; "
                              "C05 then checked on publish")
                    self.assertEqual(sched_of(public_view(self, pub["id"])[0]), base,
                                     f"public dates changed by an update without reason: {r.brief()}")
                    staged = r.data["item"]
                    for body in ({"expected_revision": staged["revision"]},
                                 {"expected_revision": staged["revision"], "reason": "  "}):
                        rp = ed.post(f"/staff/objects/{pub['id']}/publish", body)
                        self.assertEqual(sched_of(public_view(self, pub["id"])[0]), base,
                                         f"publish {body} made a date change public without reason: {rp.brief()}")
                        if rp.status in SUCCESS:
                            break
                else:
                    self.fail(f"date change without reason: expected 400/422, got {r.brief()}")
                self.assertEqual(sched_of(public_view(self, pub["id"])[0]), base, "public dates changed")
        # positive control: with a reason the same change is accepted and public
        cur, _ = staff_view(self, ed, pub["id"])
        new = dict(base, current_planned_end=iso(first + 9 * DAY))
        resp, _ = change_published(self, ed, cur, {"schedule": new}, f"R10: обоснованный перенос {token('c05')}",
                                   lambda it: sched_of(it).get("current_planned_end") == iso(first + 9 * DAY), "C05")
        self.assertEqual(sched_of(resp.data["item"]).get("current_planned_end"), iso(first + 9 * DAY))

    def test_c05_original_planned_end_never_silently_overwritten(self):
        """[C05][A04] after publication original_planned_end is rejected, ignored, or changed only with public history+reason."""
        ed = editor(0)
        first, _ = fresh_window()
        orig = iso(first + 5 * DAY)
        pub = publish(self, ed, create_draft(self, ed, schedule=schedule(first, first + 5 * DAY)))
        new = schedule(first, first + 5 * DAY, original=first + 2 * DAY)

        r0 = post_update(ed, pub["id"], pub["revision"], {"schedule": new})
        self.assertNotIn(r0.status, range(500, 600), r0.brief())
        self.assertEqual(sched_of(public_view(self, pub["id"])[0]).get("original_planned_end"), orig,
                         f"original_planned_end changed publicly with no reason: {r0.brief()}")

        cur, _ = staff_view(self, ed, pub["id"])
        reason = f"R10: исправление первоначального срока {token('orig')}"
        r = post_update(ed, pub["id"], cur["revision"], {"schedule": new}, reason)
        if r.status in VALIDATION + (403, 409):
            expect_error(self, r, "change of original_planned_end", VALIDATION + (403, 409))
            NOTES.add(f"original_planned_end change after publication rejected with {r.status}")
            self.assertEqual(sched_of(public_view(self, pub["id"])[0]).get("original_planned_end"), orig)
            return
        staff = expect_ok(self, r, "change of original_planned_end")["item"]
        if sched_of(staff).get("original_planned_end") == orig:
            NOTES.add("original_planned_end in update body is ignored after publication")
            self.assertEqual(sched_of(public_view(self, pub["id"])[0]).get("original_planned_end"), orig)
            return
        resp = public_detail(pub["id"])
        if not (resp.status == 200 and sched_of(resp.data["item"]).get("original_planned_end") != orig):
            rp = ed.post(f"/staff/objects/{pub['id']}/publish", {"expected_revision": staff["revision"], "reason": reason})
            if rp.status in VALIDATION + (403, 409):
                expect_error(self, rp, "publish of original_planned_end change", VALIDATION + (403, 409))
                NOTES.add(f"original_planned_end change accepted as staged edit, rejected at publish ({rp.status})")
                self.assertEqual(sched_of(public_view(self, pub["id"])[0]).get("original_planned_end"), orig)
                return
            expect_ok(self, rp, "re-publish of original_planned_end change")
        item, history, resp = public_view(self, pub["id"])
        if sched_of(item).get("original_planned_end") == orig:
            NOTES.add("original_planned_end change stayed staff-only even after publish")
            return
        NOTES.add("original_planned_end can be changed after publication with reason + history")
        explained = [e for e in history if mentions(e.get("changed_fields"), "original_planned_end")
                     and reason in str(e.get("reason"))]
        self.assertTrue(explained, f"original_planned_end silently changed {orig} -> "
                                   f"{sched_of(item).get('original_planned_end')}; public history: {history}")


# ================================================================ A10 filters and pagination
class FiltersAndPagination(unittest.TestCase):

    def assert_window_sane(self, items, first, last, what):
        """Under both overlap and containment readings, a returned dated object touches [first,last]."""
        for it in items:
            s = sched_of(it)
            start, end = s.get("planned_start"), s.get("current_planned_end")
            if contract.is_date(start) and contract.is_date(end):
                self.assertFalse(end < iso(first) or start > iso(last),
                                 f"{what}: item {it.get('id')} [{start}..{end}] outside [{first}..{last}]")

    def test_a10_inclusive_date_window_with_kind_and_status(self):
        """[A10] from/to inclusive on boundaries, outside days excluded, kind/status narrow, drafts never listed."""
        ed = editor(0)
        first, last = fresh_window()
        specs = {
            "on_from": dict(kind="roadworks", status="planned", schedule=schedule(first, first)),
            "on_to": dict(kind="event", status="in_progress", schedule=schedule(last, last)),
            "inside": dict(kind="landscaping", status="planned", schedule=schedule(first + 2 * DAY, first + 5 * DAY)),
            "day_before": dict(kind="roadworks", status="planned", schedule=schedule(first - DAY, first - DAY)),
            "day_after": dict(kind="roadworks", status="planned", schedule=schedule(last + DAY, last + DAY)),
        }
        ids = {name: publish(self, ed, create_draft(self, ed, **ov))["id"] for name, ov in specs.items()}
        draft_id = create_draft(self, ed, schedule=schedule(first + 3 * DAY, first + 3 * DAY))["id"]
        anon = get_target().client()
        cases = [
            ({"from": first, "to": last}, ["on_from", "on_to", "inside"], ["day_before", "day_after"], None),
            ({"from": first, "to": last, "kind": "roadworks"}, ["on_from"],
             ["on_to", "inside", "day_before", "day_after"], ("kind", "roadworks")),
            ({"from": first, "to": last, "status": "in_progress"}, ["on_to"],
             ["on_from", "inside", "day_before", "day_after"], ("status", "in_progress")),
            ({"from": first}, ["on_from", "on_to", "inside", "day_after"], ["day_before"], None),
            ({"to": last}, ["on_from", "on_to", "inside", "day_before"], ["day_after"], None),
            ({"kind": "event"}, ["on_to"], ["on_from", "inside", "day_before", "day_after"], ("kind", "event")),
        ]
        for query, present, absent, field_value in cases:
            with self.subTest(query={k: iso(v) for k, v in query.items()}):
                lst = walk(self, anon, query=query)
                for name in present:
                    self.assertEqual(lst["ids"].count(ids[name]), 1, f"{name} must be listed exactly once for {query}")
                for name in absent:
                    self.assertNotIn(ids[name], lst["ids"], f"{name} must be filtered out by {query}")
                self.assertNotIn(draft_id, lst["ids"], "draft listed publicly")
                if field_value:
                    key, value = field_value
                    wrong = [it.get("id") for it in lst["items"] if isinstance(it, dict) and it.get(key, value) != value]
                    self.assertEqual(wrong, [], f"{key}={value} filter returned other {key}s")
                if "from" in query and "to" in query:
                    self.assert_window_sane(lst["items"], query["from"], query["to"], str(query))

    def test_a10_invalid_filters_rejected(self):
        """[A10][C06] unknown kind/status, impossible or malformed dates -> 400/422 JSON error, never 500."""
        anon = get_target().client()
        bad = [{"kind": "pothole"}, {"kind": "roadworks' OR '1'='1"}, {"status": "active"}, {"status": "done"},
               {"from": "2026-02-30"}, {"from": "06.10.2026"}, {"from": "2026-13-01"}, {"to": "yesterday"}]
        for query in bad:
            with self.subTest(query=query):
                expect_error(self, anon.get("/objects", query=query), f"GET /objects {query}", VALIDATION)
        r = anon.get("/objects", query={"cursor": "%%%not-a-real-cursor%%%"})
        self.assertIn(r.status, (200,) + VALIDATION, f"garbage cursor: {r.brief()}")
        self.assertEqual(contract.check_envelope(r.json, r.status), [], r.brief())
        self.assertFalse(contract.has_traceback(r.text), r.brief())

    def _limit(self, client, query):
        """Page size 2 if the server honours ?limit= (not in contract), else None."""
        r = client.get("/objects", query=dict(query, limit=2))
        if r.status == 200 and isinstance(r.data, dict) and isinstance(r.data.get("items"), list) \
                and len(r.data["items"]) <= 2 and r.data.get("next_cursor"):
            return 2
        NOTES.add("?limit= not honoured; pagination walked with the server's own page size")
        return None

    def test_a10_cursor_pagination_each_object_exactly_once(self):
        """[A10] cursor walk (filtered and default list) returns every published object exactly once, incl. ties."""
        ed = editor(0)
        first, last = fresh_window()
        same_day = schedule(first + 4 * DAY, first + 4 * DAY)  # ties on date (and likely updated_at)
        scheds = [same_day, same_day, same_day, schedule(first, first + DAY), schedule(first + 6 * DAY, last)]
        mine = [publish(self, ed, create_draft(self, ed, schedule=s))["id"] for s in scheds]
        anon = get_target().client()
        window = {"from": first, "to": last}
        limit = self._limit(anon, window)
        lst = walk(self, anon, query=dict(window, limit=limit))
        for oid in mine:
            self.assertEqual(lst["ids"].count(oid), 1, f"object {oid} seen {lst['ids'].count(oid)}x in window walk")
        dupes = {i for i in lst["ids"] if lst["ids"].count(i) > 1}
        self.assertEqual(dupes, set(), f"duplicates across pages: {dupes}")
        if limit:
            self.assertGreaterEqual(lst["pages"], 3, f"limit=2 over >=5 objects must give >=3 pages, got {lst['pages']}")
        full = walk(self, anon)
        dupes = {i for i in full["ids"] if full["ids"].count(i) > 1}
        self.assertEqual(dupes, set(), f"duplicates in default public list: {dupes}")
        for oid in mine:
            self.assertEqual(full["ids"].count(oid), 1, f"object {oid} missing/duplicated in default public list")
        if lst["pages"] == 1 and full["pages"] == 1:
            NOTES.add("all public lists fit in one page; cursor continuation not exercised")

    def test_a10_pagination_stable_when_objects_published_mid_walk(self):
        """[A10] objects published between page requests cause no loss/duplication of already-existing ones."""
        ed = editor(0)
        first, last = fresh_window()
        mine = [publish(self, ed, create_draft(self, ed, schedule=schedule(first + i * DAY, first + i * DAY)))["id"]
                for i in range(5)]
        anon = get_target().client()
        window = {"from": first, "to": last}
        limit = self._limit(anon, window)
        if not limit:
            raise unittest.SkipTest("server ignores ?limit= and a 5-object window fits one page: "
                                    "insert-between-pages cannot be exercised")
        q = dict(window, limit=limit)
        r = anon.get("/objects", query={k: iso(v) for k, v in q.items()})
        page = expect_ok(self, r, "first page", statuses=(200,))
        seen = [it.get("id") for it in page["items"]]
        for i in range(2):  # new objects that sort anywhere (same dates as existing ones)
            publish(self, ed, create_draft(self, ed, schedule=schedule(first + i * DAY, first + i * DAY)))
        cursor = page.get("next_cursor")
        pages = 1
        while cursor:
            r = anon.get("/objects", query=dict({k: iso(v) for k, v in q.items()}, cursor=cursor))
            page = expect_ok(self, r, "next page", statuses=(200,))
            seen += [it.get("id") for it in page["items"]]
            cursor = page.get("next_cursor")
            pages += 1
            self.assertLess(pages, 100, "pagination does not end")
        for oid in mine:
            self.assertEqual(seen.count(oid), 1, f"pre-existing object {oid} seen {seen.count(oid)}x "
                                                 f"after inserts mid-walk")


# ================================================================ A06 restart
class PersistenceAcrossRestart(unittest.TestCase):

    def test_a06_restart_keeps_objects_history_and_hiding(self):
        """[A06][A02][A04] after restart: published object, dates, history, revision counter persist; draft stays hidden."""
        t = get_target()
        if not t.can_restart:
            raise unittest.SkipTest(f"target {t.name!r} cannot be restarted by the suite")
        ed = editor(0)
        first, last = fresh_window()
        draft_marker = token("a06draft")
        pub = publish(self, ed, create_draft(self, ed, schedule=schedule(first, first + 3 * DAY)))
        reason = f"R10: перенос до рестарта {token('a06')}"
        change_published(self, ed, pub, {"schedule": schedule(first, first + 6 * DAY, original=first + 3 * DAY)},
                         reason, lambda it: sched_of(it).get("current_planned_end") == iso(first + 6 * DAY), "A06")
        draft = create_draft(self, ed, marker=draft_marker, schedule=schedule(first + DAY, first + 2 * DAY))
        item_before, hist_before, _ = public_view(self, pub["id"], "before restart")
        staff_before, _ = staff_view(self, ed, pub["id"])
        draft_before, _ = staff_view(self, ed, draft["id"])

        t.restart()

        item_after, hist_after, resp = public_view(self, pub["id"], "after restart")
        for key in sorted(set(item_before) | set(item_after)):
            if key == "updated_at":
                self.assertEqual(parse_ts(item_after.get(key)), parse_ts(item_before.get(key)), "updated_at changed")
            else:
                self.assertEqual(item_after.get(key), item_before.get(key), f"public {key!r} changed by restart")
        self.assertEqual(sched_of(item_after).get("original_planned_end"), iso(first + 3 * DAY))
        self.assertEqual(sched_of(item_after).get("current_planned_end"), iso(first + 6 * DAY))
        strip = [{k: v for k, v in e.items() if k != "at"} for e in hist_before]
        self.assertEqual([{k: v for k, v in e.items() if k != "at"} for e in hist_after], strip,
                         "public history changed by restart")
        self.assertTrue(any(reason in str(e.get("reason")) for e in hist_after), "date-change reason lost")
        for b, a in zip(hist_before, hist_after):
            self.assertEqual(parse_ts(a.get("at")), parse_ts(b.get("at")), "history timestamp changed")

        assert_publicly_hidden(self, draft["id"], [draft_marker], "draft after restart")
        anon = t.client()
        lst = walk(self, anon, query={"from": first, "to": last})
        self.assertNotIn(draft["id"], lst["ids"], "draft became public after restart")
        self.assertEqual(lst["ids"].count(pub["id"]), 1, "published object lost from list after restart")

        ed2 = editor(0)  # sessions may legitimately not survive a restart
        staff_after, _ = staff_view(self, ed2, pub["id"])
        self.assertEqual((staff_after["revision"], staff_after["publication"]),
                         (staff_before["revision"], staff_before["publication"]))
        draft_after, _ = staff_view(self, ed2, draft["id"])
        self.assertEqual((draft_after["revision"], draft_after["publication"], draft_after["title"]),
                         (draft_before["revision"], "draft", draft_before["title"]))

        r = post_update(ed2, draft["id"], draft_after["revision"], {"title": f"R10 после рестарта {draft_marker}"},
                        "R10: правка после рестарта")
        got = expect_ok(self, r, "update after restart")["item"]
        self.assertEqual(got["revision"], draft_after["revision"] + 1, "revision counter reset by restart")
        newcomer = create_draft(self, ed2)
        self.assertNotIn(newcomer["id"], (pub["id"], draft["id"]), "restart reused an existing id")
        again, _, _ = public_view(self, pub["id"], "published object after post-restart writes")
        self.assertEqual(again.get("revision"), item_before.get("revision"), "post-restart create clobbered object")
        self.assertEqual(again.get("title"), item_before.get("title"))


if __name__ == "__main__":
    unittest.main()
