#!/usr/bin/env python3
"""R10 standalone driver for R06 ui/civic_feedback (FeedbackService).

Run ONLY as:  python3 -I -B r06_driver.py <worktree_root>
cwd and sys.path[0] are set to the worktree; every DB lives in a fresh
tempfile.mkdtemp(). The driver performs product calls and prints raw
observations as JSON on stdout. It does NOT decide PASS/FAIL: expectations
live in standalone_r06.py (derived from CONTRACT civic-v1 + R06 prompt).
No network, no shell, no writes outside the temp dir.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone

API = "/api/civic/v1"
PUB, DRAFT, ARCH, BOOM, NOPE = "r10-pub-01", "r10-draft-02", "r10-arch-03", "r10-boom-04", "r10-nope-99"
DRAFT_TITLE = "R10-DRAFT-TITLE-qzxw secret plan"
ARCH_TITLE = "R10-ARCH-TITLE-wvut"
LOOKUP_SECRET = "R10-LOOKUP-SECRET /srv/r10/secret.db"
CSRF = "tok-r10"
EDITOR = {"authenticated": True, "role": "editor", "name": "r10_mod", "csrf_token": CSRF}
RESIDENT = {"authenticated": True, "role": "resident", "name": "r10_resident", "csrf_token": CSRF}
LOGGED_OUT = {"authenticated": False, "role": None, "name": None, "csrf_token": None}


def _object(oid, publication, title, geometry):
    return {
        "schema_version": "civic-v1", "id": oid, "city": "astana", "kind": "roadworks",
        "title": title, "description": "R10 synthetic test object", "status": "planned",
        "publication": publication, "geometry": geometry, "geometry_precision": "approximate",
        "schedule": {"planned_start": None, "original_planned_end": None,
                     "current_planned_end": None, "actual_end": None},
        "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
        "responsible": {"organization": None, "public_contact": None},
        "evidence_type": "synthetic", "source_refs": [], "evidence_notes": "R10 synthetic",
        "updated_at": "2026-10-06T12:00:00Z", "revision": 1,
    }


POINT = {"type": "Point", "coordinates": [71.43, 51.17]}
OBJECTS = {
    PUB: _object(PUB, "published", "R10 published object", POINT),
    DRAFT: _object(DRAFT, "draft", DRAFT_TITLE, POINT),
    ARCH: _object(ARCH, "archived", ARCH_TITLE, POINT),
}


def lookup(object_id):
    if object_id == BOOM:
        raise RuntimeError(LOOKUP_SECRET)
    item = OBJECTS.get(object_id)
    return copy.deepcopy(item) if item else None


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)


def ctx(ip="127.0.0.2", csrf=None, same=True):
    headers = {"Host": "127.0.0.1:8501", "Origin": "http://127.0.0.1:8501"}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    return {"headers": headers, "client_ip": ip, "is_same_origin": same}


ALL: list[dict] = []


def call(svc, label, method, path, body=None, principal=None, context=None, query=None):
    """One product call; exceptions out of handle() are recorded, never re-raised."""
    try:
        resp = svc.handle(method, API + path, query if query is not None else {}, body,
                          principal, context if context is not None else ctx())
    except BaseException as exc:  # noqa: BLE001 — we record what escaped handle()
        rec = {"label": label, "status": None, "exception": type(exc).__name__,
               "exception_text": str(exc)[:300], "raw": "", "body": None}
        ALL.append(rec)
        return rec
    if resp is None:
        rec = {"label": label, "status": None, "none": True, "raw": "", "body": None}
    else:
        body_out = resp.get("body")
        try:
            raw = json.dumps(body_out, ensure_ascii=False)
            serializable = True
        except (TypeError, ValueError):
            raw, serializable = repr(body_out), False
        rec = {"label": label, "status": resp.get("status"), "body": body_out, "raw": raw,
               "serializable": serializable, "headers": resp.get("headers")}
    ALL.append(rec)
    return rec


def code_of(rec):
    body = rec.get("body")
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return body["error"].get("code")
    return None


def fb(text, object_id=PUB, geometry=None, category="sidewalks", consent=True, **extra):
    body = {"object_id": object_id, "geometry": geometry, "category": category, "text": text,
            "consent_public": consent}
    body.update(extra)
    return body


def txt(marker):
    # lowercase, no digits runs, no contacts — so moderation heuristics are not triggered
    return f"на тротуаре глубокая яма, трудно пройти с коляской, метка {marker}"


class Env:
    def __init__(self, tmp, FeedbackService):
        self.tmp, self.FS, self.n = tmp, FeedbackService, 0

    def new(self, name=None, **kwargs):
        self.n += 1
        path = os.path.join(self.tmp, f"{name or 'svc'}-{self.n}.sqlite3")
        return self.FS(path, lookup, Clock(), **kwargs), path


def submit(svc, label, body, ip="127.0.0.2", same=True):
    return call(svc, label, "POST", "/feedback", body, None, ctx(ip, same=same))


def public(svc, label, object_id=PUB):
    return call(svc, label, "GET", f"/objects/{object_id}/feedback", None, None, ctx("127.0.0.250"))


def queue_all(svc, label="queue"):
    return call(svc, label, "GET", "/staff/feedback", None, EDITOR, ctx("127.0.0.251"),
                {"moderation": "all", "limit": "50"})


def find(svc, marker, label="queue-find"):
    rec = queue_all(svc, label)
    items = (((rec.get("body") or {}).get("data") or {}).get("items")) or []
    hits = [it for it in items if marker in json.dumps(it, ensure_ascii=False)]
    return (hits[0] if hits else None), len(hits), rec


def moderate(svc, label, staff_id, body, principal=EDITOR, context=None):
    return call(svc, label, "POST", f"/staff/feedback/{staff_id}/moderate", body, principal,
                context if context is not None else ctx("127.0.0.252", csrf=CSRF))


def slim(rec, keep_raw=True, limit=4000):
    out = {"status": rec.get("status"), "code": code_of(rec)}
    for key in ("exception", "exception_text", "none", "serializable"):
        if key in rec:
            out[key] = rec[key]
    if keep_raw:
        out["raw"] = rec.get("raw", "")[:limit]
    return out


# ------------------------------------------------------------------ scenarios
def sc_receipt(env):
    svc, _ = env.new("receipt")
    m = "r10mk-receipt"
    text = f"не работает освещение во дворе, пишите мне r10.author@example.com или +7 701 555 12 34 {m}"
    r = submit(svc, "receipt.submit", fb(text, category="lighting"), ip="127.0.0.11")
    data = ((r.get("body") or {}).get("data")) or {}
    pub_pending = public(svc, "receipt.public_pending")
    item, _, _ = find(svc, m)
    appr = None
    pub_after = None
    if item:
        appr = moderate(svc, "receipt.approve_with_contacts", item["id"],
                        {"expected_revision": item.get("revision", 1), "action": "approve",
                         "reason": "проверено r10", "public_reply": None})
        pub_after = public(svc, "receipt.public_after_approve")
    return {"marker": m, "email": "r10.author@example.com", "phone_digits": "7015551234",
            "phone_text": "555 12 34", "ip": "127.0.0.11",
            "submit": slim(r), "data_keys": sorted(data) if isinstance(data, dict) else None,
            "moderation": data.get("moderation") if isinstance(data, dict) else None,
            "receipt_id": data.get("receipt_id") if isinstance(data, dict) else None,
            "official_registration": data.get("official_registration") if isinstance(data, dict) else None,
            "public_pending": slim(pub_pending), "found_in_queue": item is not None,
            "approve_with_contacts": slim(appr) if appr else None,
            "public_after_approve": slim(pub_after) if pub_after else None}


def sc_approve_consent(env):
    svc, _ = env.new("approve")
    m, reply, reason = "r10mk-approve", "ответ модератора: учтено r10reply-approve", "r10reason-approve"
    r = submit(svc, "approve.submit", fb(txt(m)), ip="127.0.0.12")
    receipt_id = (((r.get("body") or {}).get("data")) or {}).get("receipt_id")
    item, _, _ = find(svc, m)
    appr = moderate(svc, "approve.moderate", item["id"],
                    {"expected_revision": item.get("revision", 1), "action": "approve",
                     "reason": reason, "public_reply": reply}) if item else None
    pub = public(svc, "approve.public")
    return {"marker": m, "reply": reply, "reason": reason, "ip": "127.0.0.12", "editor": EDITOR["name"],
            "csrf": CSRF, "receipt_id": receipt_id, "submit": slim(r),
            "moderate": slim(appr) if appr else None, "public": slim(pub),
            "public_body": pub.get("body")}


def sc_approve_no_consent(env):
    svc, _ = env.new("noconsent")
    m, reply = "r10mk-noconsent", "ответ модератора: учтено r10reply-noconsent"
    r = submit(svc, "noconsent.submit", fb(txt(m), consent=False), ip="127.0.0.13")
    item, _, _ = find(svc, m)
    appr = moderate(svc, "noconsent.moderate", item["id"],
                    {"expected_revision": item.get("revision", 1), "action": "approve",
                     "reason": "одобрено без согласия", "public_reply": reply}) if item else None
    pub = public(svc, "noconsent.public")
    return {"marker": m, "reply": reply, "submit": slim(r),
            "moderate": slim(appr) if appr else None, "public": slim(pub)}


def sc_reject(env):
    svc, _ = env.new("reject")
    m = "r10mk-reject"
    r = submit(svc, "reject.submit", fb(txt(m)), ip="127.0.0.14")
    item, _, _ = find(svc, m)
    rej = moderate(svc, "reject.moderate", item["id"],
                   {"expected_revision": item.get("revision", 1), "action": "reject",
                    "reason": "спам r10", "public_reply": None}) if item else None
    pub = public(svc, "reject.public")
    after, count, _ = find(svc, m, "reject.queue_after")
    # approved+consent message later rejected must disappear from the public list
    m2 = "r10mk-rereject"
    submit(svc, "reject.submit2", fb(txt(m2)), ip="127.0.0.17")
    it2, _, _ = find(svc, m2, "reject.queue2")
    a2 = moderate(svc, "reject.approve2", it2["id"], {"expected_revision": it2.get("revision", 1),
                                                       "action": "approve", "reason": "проверено r10",
                                                       "public_reply": None}) if it2 else None
    pub_mid = public(svc, "reject.public_mid")
    it2b, _, _ = find(svc, m2, "reject.queue2b")
    r2 = moderate(svc, "reject.reject2", it2b["id"], {"expected_revision": it2b.get("revision"),
                                                       "action": "reject", "reason": "отозвано модератором",
                                                       "public_reply": None}) if it2b else None
    pub_end = public(svc, "reject.public_end")
    return {"marker": m, "submit": slim(r), "moderate": slim(rej) if rej else None,
            "public": slim(pub), "still_in_staff_queue": count,
            "staff_moderation_after": after.get("moderation") if after else None,
            "marker2": m2, "approve2": slim(a2, limit=300) if a2 else None, "public_mid": slim(pub_mid),
            "reject2": slim(r2, limit=300) if r2 else None, "public_end": slim(pub_end)}


def sc_authz(env):
    svc, _ = env.new("authz")
    m = "r10mk-authz"
    submit(svc, "authz.submit", fb(txt(m)), ip="127.0.0.15")
    item, _, _ = find(svc, m)
    sid, rev = (item["id"], item.get("revision", 1)) if item else ("1", 1)
    good = {"expected_revision": rev, "action": "approve", "reason": "попытка r10", "public_reply": None}
    spoof = dict(good, role="editor", actor="r10_mod", user={"role": "editor"})
    cases = {
        "anon": moderate(svc, "authz.anon", sid, good, None, ctx("127.0.0.15", csrf=CSRF)),
        "logged_out": moderate(svc, "authz.logged_out", sid, good, LOGGED_OUT, ctx("127.0.0.15", csrf=CSRF)),
        "anon_body_role": moderate(svc, "authz.anon_body_role", sid, spoof, None, ctx("127.0.0.15", csrf=CSRF)),
        "resident": moderate(svc, "authz.resident", sid, good, RESIDENT, ctx("127.0.0.15", csrf=CSRF)),
        "resident_body_role": moderate(svc, "authz.resident_body_role", sid, spoof, RESIDENT,
                                       ctx("127.0.0.15", csrf=CSRF)),
        "editor_no_csrf": moderate(svc, "authz.editor_no_csrf", sid, good, EDITOR, ctx("127.0.0.15")),
        "editor_bad_csrf": moderate(svc, "authz.editor_bad_csrf", sid, good, EDITOR,
                                    ctx("127.0.0.15", csrf="tok-WRONG")),
        "editor_cross_origin": moderate(svc, "authz.editor_cross_origin", sid, good, EDITOR,
                                        ctx("127.0.0.15", csrf=CSRF, same=False)),
        "queue_anon": call(svc, "authz.queue_anon", "GET", "/staff/feedback", None, None, ctx("127.0.0.15")),
        "queue_resident": call(svc, "authz.queue_resident", "GET", "/staff/feedback", None, RESIDENT,
                               ctx("127.0.0.15")),
    }
    after, _, _ = find(svc, m, "authz.queue_after")
    pub = public(svc, "authz.public")
    return {"marker": m, "found": item is not None, "rev_before": rev,
            "cases": {k: slim(v, limit=600) for k, v in cases.items()},
            "after": {"moderation": after.get("moderation"), "revision": after.get("revision")} if after else None,
            "public": slim(pub)}


def sc_stale(env):
    svc, _ = env.new("stale")
    m, reply_a, reply_b = "r10mk-stale", "ответ модератора: учтено r10reply-staleaaa", "ответ модератора: учтено r10reply-stalebbb"
    submit(svc, "stale.submit", fb(txt(m)), ip="127.0.0.16")
    item, _, _ = find(svc, m)
    first = moderate(svc, "stale.first", item["id"], {"expected_revision": item.get("revision", 1),
                                                     "action": "approve", "reason": "первое решение",
                                                     "public_reply": reply_a}) if item else None
    mid, _, _ = find(svc, m, "stale.queue_mid")
    stale = moderate(svc, "stale.second_stale", item["id"], {"expected_revision": item.get("revision", 1),
                                                            "action": "reject", "reason": "второе решение",
                                                            "public_reply": reply_b}) if item else None
    after, _, _ = find(svc, m, "stale.queue_after")
    pub = public(svc, "stale.public")
    keys = ("moderation", "revision", "public_reply", "moderation_reason")
    return {"marker": m, "reply_a": reply_a, "reply_b": reply_b,
            "first": slim(first, limit=500) if first else None, "stale": slim(stale, limit=800) if stale else None,
            "mid": {k: mid.get(k) for k in keys} if mid else None,
            "after": {k: after.get(k) for k in keys} if after else None, "public": slim(pub)}


def sc_object_privacy(env):
    svc, _ = env.new("objpriv")
    out = {"draft_title": DRAFT_TITLE, "arch_title": ARCH_TITLE, "lookup_secret": LOOKUP_SECRET}
    for i, (name, oid) in enumerate((("draft", DRAFT), ("archived", ARCH), ("nonexistent", NOPE),
                                     ("lookup_raises", BOOM))):
        r = submit(svc, f"objpriv.submit_{name}", fb(txt(f"r10mk-obj{name}"), object_id=oid), ip=f"127.0.0.{20 + i}")
        out[f"submit_{name}"] = slim(r)
        out[f"submit_{name}_error"] = (r.get("body") or {}).get("error")
        g = public(svc, f"objpriv.public_{name}", oid)
        out[f"public_{name}"] = slim(g)
        out[f"public_{name}_error"] = (g.get("body") or {}).get("error")
    _, count, _ = find(svc, "r10mk-obj", "objpriv.queue")
    out["rows_created"] = count
    return out


def sc_location(env):
    svc, _ = env.new("location")
    cases = {
        "neither": fb(txt("r10mk-loc-neither"), object_id=None, geometry=None),
        "outside_astana": fb(txt("r10mk-loc-almaty"), object_id=None,
                             geometry={"type": "Point", "coordinates": [76.95, 43.24]}),
        "swapped_lonlat": fb(txt("r10mk-loc-swapped"), object_id=None,
                             geometry={"type": "Point", "coordinates": [51.17, 71.43]}),
        "far_from_object": fb(txt("r10mk-loc-far"), object_id=PUB,
                              geometry={"type": "Point", "coordinates": [71.0, 51.17]}),
        "near_object_ok": fb(txt("r10mk-loc-near"), object_id=PUB,
                             geometry={"type": "Point", "coordinates": [71.4305, 51.1702]}),
        "geometry_only_ok": fb(txt("r10mk-loc-geo"), object_id=None,
                               geometry={"type": "Point", "coordinates": [71.45, 51.16]}),
    }
    out = {}
    for i, (name, body) in enumerate(cases.items()):
        out[name] = slim(submit(svc, f"location.{name}", body, ip=f"127.0.0.{30 + i}"), limit=600)
    return out


def sc_duplicate(env):
    svc, _ = env.new("dup")
    m = "r10mk-dup"
    body = fb(txt(m))
    first = submit(svc, "dup.first", body, ip="127.0.0.40")
    second = submit(svc, "dup.second", copy.deepcopy(body), ip="127.0.0.40")
    third = submit(svc, "dup.third", copy.deepcopy(body), ip="127.0.0.40")
    _, count, _ = find(svc, m, "dup.queue")
    sdata = ((second.get("body") or {}).get("data")) or {}
    return {"first": slim(first, limit=600), "second": slim(second, limit=800), "third": slim(third, limit=800),
            "second_warnings": sdata.get("warnings") if isinstance(sdata, dict) else None,
            "rows_with_marker": count}


def sc_xss(env):
    svc, _ = env.new("xss")
    payload = '<script>alert("r10")</script><img src=x onerror=alert(1)> r10mk-xss текст сообщения'
    r = submit(svc, "xss.submit", fb(payload), ip="127.0.0.41")
    item, _, _ = find(svc, "r10mk-xss")
    appr = moderate(svc, "xss.approve", item["id"], {"expected_revision": item.get("revision", 1),
                                                      "action": "approve", "reason": "проверено",
                                                      "public_reply": None}) if item else None
    pub = public(svc, "xss.public")
    items = (((pub.get("body") or {}).get("data") or {}).get("items")) or []
    texts = [json.dumps(it, ensure_ascii=False) for it in items]
    return {"payload": payload, "submit": slim(r, limit=600),
            "approve": slim(appr, limit=600) if appr else None,
            "staff_text": item.get("text") if item else None, "public": slim(pub), "public_items": texts}


def sc_body_size(env):
    svc, _ = env.new("size")
    big_text = "я" * 60000
    raw_big = json.dumps(fb(big_text), ensure_ascii=False).encode("utf-8")
    out = {"raw_big_bytes": len(raw_big)}
    out["raw_bytes_120k"] = slim(submit(svc, "size.raw_bytes", raw_big, ip="127.0.0.42"), limit=600)
    out["dict_120k"] = slim(submit(svc, "size.dict", fb(big_text), ip="127.0.0.43"), limit=600)
    out["text_2500"] = slim(submit(svc, "size.text_2500", fb("ы" * 2500 + " r10mk-long"), ip="127.0.0.44"), limit=600)
    out["alive_after"] = slim(submit(svc, "size.alive", fb(txt("r10mk-alive")), ip="127.0.0.45"), limit=600)
    _, out["rows_long"], _ = find(svc, "r10mk-long", "size.queue")
    return out


def sc_raw_json(env):
    svc, _ = env.new("rawjson")
    good = json.dumps(fb(txt("r10mk-rawok")), ensure_ascii=False).encode("utf-8")
    t = txt("r10mk-nan")
    cases = {
        "raw_bytes_valid": good,
        "str_valid": json.dumps(fb(txt("r10mk-strok")), ensure_ascii=False),
        "nan_consent": ('{"object_id":"%s","geometry":null,"category":"roads","text":"%s","consent_public":NaN}'
                        % (PUB, t)).encode(),
        "nan_coordinates": ('{"object_id":null,"geometry":{"type":"Point","coordinates":[NaN,51.17]},'
                            '"category":"roads","text":"%s","consent_public":true}' % t).encode(),
        "infinity_coordinates": ('{"object_id":null,"geometry":{"type":"Point","coordinates":[Infinity,51.17]},'
                                 '"category":"roads","text":"%s","consent_public":true}' % t).encode(),
        "nan_category": ('{"object_id":"%s","geometry":null,"category":NaN,"text":"%s","consent_public":true}'
                         % (PUB, t)).encode(),
        "broken_json": b'{"object_id": "r10-pub-01", "text": ',
        "json_array": b'[1, 2, 3]',
        "invalid_utf8": b'\xff\xfe{"a":1}',
        "empty": b"",
    }
    out = {}
    for i, (name, body) in enumerate(cases.items()):
        out[name] = slim(submit(svc, f"rawjson.{name}", body, ip=f"127.0.1.{i + 1}"), limit=600)
    return out


def sc_surrogate(env):
    """Lone UTF-16 surrogate: valid JSON escape that Python json accepts but UTF-8/SQLite cannot store."""
    svc, _ = env.new("surrogate")
    raw = ('{"object_id":"%s","geometry":null,"category":"roads",'
           '"text":"разбитый тротуар \\ud800 у остановки r10mk-sur","consent_public":true}' % PUB).encode()
    out = {"raw_body_submitted": raw.decode()}
    out["submit_raw_bytes"] = slim(submit(svc, "surrogate.submit_raw", raw, ip="127.0.2.1"), limit=600)
    out["submit_dict"] = slim(submit(svc, "surrogate.submit_dict", json.loads(raw), ip="127.0.2.2"), limit=600)
    submit(svc, "surrogate.base", fb(txt("r10mk-surbase")), ip="127.0.2.3")
    item, _, _ = find(svc, "r10mk-surbase", "surrogate.queue")
    if item:
        out["moderate_reason"] = slim(moderate(svc, "surrogate.moderate_reason", item["id"],
                                               {"expected_revision": item.get("revision", 1), "action": "reject",
                                                "reason": "плохо \ud800 причина", "public_reply": None}), limit=600)
        raw_mod = ('{"expected_revision":%d,"action":"reject","reason":"bad \\ud800 reason","public_reply":null}'
                   % item.get("revision", 1)).encode()
        out["moderate_reason_raw_bytes"] = slim(moderate(svc, "surrogate.moderate_reason_raw", item["id"], raw_mod),
                                                limit=600)
        after, _, _ = find(svc, "r10mk-surbase", "surrogate.queue_after")
        out["base_after"] = {"moderation": after.get("moderation"), "revision": after.get("revision")} if after else None
    out["alive_after"] = slim(submit(svc, "surrogate.alive", fb(txt("r10mk-suralive")), ip="127.0.2.4"), limit=600)
    return out


def sc_withdraw(env):
    svc, _ = env.new("withdraw")
    m = "r10mk-withdraw"
    r = submit(svc, "withdraw.submit", fb(txt(m)), ip="127.0.0.46")
    receipt_id = (((r.get("body") or {}).get("data")) or {}).get("receipt_id")
    item, _, _ = find(svc, m)
    moderate(svc, "withdraw.approve", item["id"], {"expected_revision": item.get("revision", 1),
                                                    "action": "approve", "reason": "проверено r10", "public_reply": None})
    before = public(svc, "withdraw.public_before")
    w = call(svc, "withdraw.withdraw", "POST", "/feedback/withdraw-consent", {"receipt_id": receipt_id},
             None, ctx("127.0.0.46"))
    after = public(svc, "withdraw.public_after")
    # forged receipt must not withdraw someone else's consent nor crash
    forged = call(svc, "withdraw.forged", "POST", "/feedback/withdraw-consent",
                  {"receipt_id": "fbr_AAAAAAAAAAAAAAAAAAAAAAAA"}, None, ctx("127.0.0.47"))
    return {"marker": m, "withdraw": slim(w, limit=600), "public_before": slim(before),
            "public_after": slim(after), "forged": slim(forged, limit=600)}


def sc_classifier(env):
    out = {}

    def raising(text, language):
        raise RuntimeError("R10 model crashed")

    gate = threading.Event()

    def hanging(text, language):
        gate.wait(10)
        return {"label": "roads", "score": 0.9}

    def garbage(text, language):
        return {"label": "official_urgent", "score": float("nan"), "assign_to": "akimat",
                "publish": True}

    for name, fn, extra in (("raising", raising, {}),
                            ("hanging", hanging, {"limits": {"classifier_timeout_s": 0.5}}),
                            ("garbage", garbage, {})):
        try:
            svc, _ = env.new(f"clf-{name}", classifier=fn, **extra)
        except TypeError as exc:
            out[name] = {"not_run": f"constructor rejected classifier kwarg: {exc}"}
            continue
        m = f"r10mk-clf-{name}"
        t0 = time.monotonic()
        r = submit(svc, f"classifier.{name}", fb(txt(m), category="sidewalks"), ip="127.0.0.48")
        elapsed = round(time.monotonic() - t0, 3)
        item, count, _ = find(svc, m, f"classifier.{name}.queue")
        out[name] = {"submit": slim(r, limit=600), "elapsed_s": elapsed, "rows": count,
                     "category_after": item.get("category") if item else None,
                     "moderation_after": item.get("moderation") if item else None}
        pub = public(svc, f"classifier.{name}.public")
        out[name]["public_has_marker"] = m in pub.get("raw", "")
    gate.set()
    return out


def sc_restart(env):
    svc, path = env.new("restart")
    ma, mb = "r10mk-restart-approved", "r10mk-restart-pending"
    submit(svc, "restart.a", fb(txt(ma)), ip="127.0.0.50")
    submit(svc, "restart.b", fb(txt(mb)), ip="127.0.0.51")
    item, _, _ = find(svc, ma)
    appr = moderate(svc, "restart.approve", item["id"], {"expected_revision": item.get("revision", 1),
                                                          "action": "approve", "reason": "проверено r10",
                                                          "public_reply": "ответ модератора r10reply-restart"})
    before = public(svc, "restart.public_before")
    closer = getattr(svc, "close", None)
    if callable(closer):
        closer()
    del svc
    svc2 = env.FS(path, lookup, Clock())
    after = public(svc2, "restart.public_after")
    pend, pend_count, _ = find(svc2, mb, "restart.queue_after")
    approve_b = moderate(svc2, "restart.approve_b_after", pend["id"],
                         {"expected_revision": pend.get("revision", 1), "action": "approve", "reason": "проверено r10",
                          "public_reply": None}) if pend else None
    after2 = public(svc2, "restart.public_after2")
    return {"ma": ma, "mb": mb, "approve": slim(appr, limit=400), "public_before": slim(before),
            "public_after": slim(after), "pending_rows_after": pend_count,
            "pending_moderation_after": pend.get("moderation") if pend else None,
            "approve_b_after": slim(approve_b, limit=400) if approve_b else None,
            "public_after2": slim(after2)}


def sc_unknown_fields(env):
    svc, _ = env.new("unknown")
    m = "r10mk-unknown"
    body = fb(txt(m), role="editor", actor="r10_mod", moderation="approved", revision=7,
              publication="published", public_text=txt(m) + " forged", user={"role": "editor"})
    r = submit(svc, "unknown.submit", body, ip="127.0.0.52")
    item, count, _ = find(svc, m)
    pub = public(svc, "unknown.public")
    return {"marker": m, "submit": slim(r, limit=800), "rows": count,
            "moderation_after": item.get("moderation") if item else None,
            "revision_after": item.get("revision") if item else None, "public": slim(pub)}


def sc_rate_limit(env):
    svc, _ = env.new("rate")
    statuses, first_429, rec429 = [], None, None
    for i in range(10):
        r = submit(svc, f"rate.a{i}", fb(txt(f"r10mk-rate-a{chr(97 + i)}x")), ip="127.0.0.60")
        statuses.append(r.get("status"))
        if r.get("status") == 429 and first_429 is None:
            first_429, rec429 = i + 1, r
            break
    other = submit(svc, "rate.other_ip", fb(txt("r10mk-rate-other")), ip="127.0.0.61")
    _, rows_a, _ = find(svc, "r10mk-rate-a", "rate.queue")
    return {"statuses": statuses, "first_429_at_attempt": first_429,
            "rec_429": slim(rec429, limit=600) if rec429 else None,
            "headers_429": (rec429 or {}).get("headers"),
            "created_201": sum(1 for s in statuses if s in (200, 201)), "rows_ip_a": rows_a,
            "other_ip": slim(other, limit=600)}


def sc_routes(env):
    svc, _ = env.new("routes")
    return {
        "unknown_feedback_path": slim(call(svc, "routes.unknown", "GET", "/feedback/r10-unknown-x"), limit=400),
        "get_on_submit": slim(call(svc, "routes.get_submit", "GET", "/feedback"), limit=400),
        "public_list_ok": slim(public(svc, "routes.public_ok"), limit=400),
        "foreign_path_returns_none": call(svc, "routes.foreign", "GET", "/objects")["status"] is None
        and ALL[-1].get("none", False),
    }


def sc_prefixless(env):
    """Paths outside /api/civic/v1 (e.g. a static '/feedback' page) — service should not claim them."""
    svc, _ = env.new("prefixless")
    out = {}
    for name, method, path, body in (("post_feedback", "POST", "/feedback", fb(txt("r10mk-prefixless"))),
                                     ("get_public", "GET", "/objects/%s/feedback" % PUB, None),
                                     ("get_staff", "GET", "/staff/feedback", None)):
        try:
            resp = svc.handle(method, path, {}, body, None, ctx("127.0.3.1"))
            out[name] = None if resp is None else {"status": resp.get("status"),
                                                   "code": ((resp.get("body") or {}).get("error") or {}).get("code")}
        except Exception as exc:  # noqa: BLE001
            out[name] = {"exception": type(exc).__name__}
    return out


SCENARIOS = [
    ("receipt", sc_receipt), ("approve_consent", sc_approve_consent),
    ("approve_no_consent", sc_approve_no_consent), ("reject", sc_reject), ("authz", sc_authz),
    ("stale", sc_stale), ("object_privacy", sc_object_privacy), ("location", sc_location),
    ("duplicate", sc_duplicate), ("xss", sc_xss), ("body_size", sc_body_size),
    ("raw_json", sc_raw_json), ("surrogate", sc_surrogate), ("withdraw", sc_withdraw),
    ("classifier", sc_classifier), ("restart", sc_restart), ("unknown_fields", sc_unknown_fields),
    ("rate_limit", sc_rate_limit), ("routes", sc_routes), ("prefixless", sc_prefixless),
]


def main():
    if len(sys.argv) != 2:
        print(json.dumps({"fatal": "usage: python3 -I -B r06_driver.py <worktree_root>"}))
        return 2
    root = os.path.realpath(sys.argv[1])
    here = os.path.dirname(os.path.realpath(__file__))
    sys.path[:] = [p for p in sys.path if p and os.path.realpath(p) != here]
    sys.path.insert(0, root)
    os.chdir(root)
    import logging
    logging.disable(logging.CRITICAL)  # product logs exceptions; keep stdout pure JSON
    tmp = tempfile.mkdtemp(prefix="r10-r06-")
    result = {"meta": {"root": root, "sys_path0": sys.path[0], "cwd": os.getcwd(),
                       "python": sys.version.split()[0], "flags_isolated": bool(sys.flags.isolated),
                       "dont_write_bytecode": sys.dont_write_bytecode, "tmp": tmp},
              "checks": {}, "driver_errors": {}}
    try:
        import ui.civic_feedback as pkg
        from ui.civic_feedback import FeedbackService
        import ui.civic_feedback.service as svcmod
        result["meta"]["package_file"] = os.path.realpath(pkg.__file__)
        result["meta"]["module_file"] = os.path.realpath(svcmod.__file__)
        env = Env(tmp, FeedbackService)
        for name, fn in SCENARIOS:
            try:
                result["checks"][name] = fn(env)
            except Exception:  # driver bug or product shape mismatch — reported, not hidden
                result["driver_errors"][name] = traceback.format_exc()[-1500:]
        result["all_errors"] = [
            {"label": r["label"], "status": r.get("status"), "code": code_of(r),
             "exception": r.get("exception"), "serializable": r.get("serializable"),
             "body": r.get("body") if (r.get("status") or 0) >= 400 else None,
             "raw": r.get("raw", "")[:1500]}
            for r in ALL if r.get("exception") or (r.get("status") or 0) >= 400]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps(result, ensure_ascii=True, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
