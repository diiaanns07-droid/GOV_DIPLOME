#!/usr/bin/env python3
# =============================================================================
# R10 ORACLE - NOT PRODUCT CODE.
# A compact REFERENCE implementation of the civic-v1 HTTP API (round 11 CONTRACT,
# PACK 9c2f5c0), written by R10 only to self-test the acceptance suite and to run
# mutation testing: R10_ORACLE_MUTANT=name[,name] switches on deliberate defects
# (each guarded by `M("name")`, grep "MUTANT"). Never deploy it, never import it
# from product code, never treat its behaviour as a product decision.
# stdlib only.
# =============================================================================
"""R10 civic-v1 reference oracle (test-only).

  python -I -B server.py serve --db PATH --port N [--host 127.0.0.1]
  python -I -B server.py create-editor --db PATH --username NAME   (password via getpass)

Choices where CONTRACT.txt leaves room are marked "DECISION:" in comments.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import copy
import datetime as dt
import getpass
import hashlib
import hmac
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import sqlite3
import sys
import threading
import time
import traceback
from urllib.parse import parse_qs, unquote, urlsplit
import urllib.request

# ---- mutation switches -------------------------------------------------------
KNOWN_MUTANTS = frozenset("""
no_csrf no_origin draft_public list_drafts body_publication no_409 no_reason overwrite_original
leak_internal history_username budget_zero today_dates logout_noop pending_public no_consent
anon_moderate traceback no_size_limit static_leak accept_nan memory_db role_from_body cookie_flags
archive_visible ssrf draft_history_public feedback_draft dup_feedback""".split())
MUTANTS = frozenset(m.strip() for m in os.environ.get("R10_ORACLE_MUTANT", "").split(",") if m.strip())


def M(name: str) -> bool:
    """True when deliberate defect `name` is switched on (mutation testing only)."""
    return name in MUTANTS


# ---- contract vocabulary (CONTRACT section 1) --------------------------------
PREFIX = "/api/civic/v1"
KINDS = frozenset({"construction", "roadworks", "landscaping", "event"})
STATUSES = frozenset({"planned", "in_progress", "completed", "cancelled", "unknown"})
PUBLICATIONS = frozenset({"draft", "published", "archived"})
PRECISIONS = frozenset({"source", "approximate", "unknown"})
EVIDENCE_TYPES = frozenset({"observed", "derived", "hypothesis", "synthetic"})
BUDGET_BASES = frozenset({"planned", "contract", "spent", "unknown"})
ACCESS_STATUSES = frozenset({"fetched", "not_fetched", "unavailable"})
GEOMETRY_TYPES = frozenset({"Point", "LineString", "Polygon"})
FEEDBACK_CATEGORIES = frozenset({"roads", "sidewalks", "transport_stops", "lighting", "landscaping", "other"})
FEEDBACK_STATUSES = frozenset({"pending", "approved", "rejected"})

OBJECT_FIELDS = ("schema_version", "id", "city", "kind", "title", "description", "status",
                 "publication", "geometry", "geometry_precision", "schedule", "budget",
                 "responsible", "evidence_type", "source_refs", "evidence_notes", "updated_at",
                 "revision")
EDITABLE = ("kind", "title", "description", "status", "geometry", "geometry_precision",
            "schedule", "budget", "responsible", "evidence_type", "source_refs", "evidence_notes")
STAFF_ONLY = ("internal_notes",)  # editable, stored privately, never public
SCHEDULE_KEYS = ("planned_start", "original_planned_end", "current_planned_end", "actual_end")
BUDGET_KEYS = ("amount_kzt", "basis", "source_id")
RESPONSIBLE_KEYS = ("organization", "public_contact")
NESTED = {"schedule": SCHEDULE_KEYS, "budget": BUDGET_KEYS, "responsible": RESPONSIBLE_KEYS}
SOURCE_REF_KEYS = ("id", "url", "publisher", "published_on", "retrieved_at", "access_status",
                   "license", "fields")
# Server-owned keys: silently ignored in create bodies and in update `changes` (not errors).
SERVER_OWNED = frozenset({"id", "publication", "revision", "updated_at", "schema_version", "city",
                          "actor", "role", "created_by", "created_at", "actor_user",
                          "first_published_at", "public_actor_label"})
DEFAULT_STATE = {
    "kind": None, "title": None, "description": "", "status": "unknown", "geometry": None,
    "geometry_precision": "unknown", "schedule": dict.fromkeys(SCHEDULE_KEYS),
    "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
    "responsible": dict.fromkeys(RESPONSIBLE_KEYS), "evidence_type": None, "source_refs": [],
    "evidence_notes": "", "internal_notes": None,
}
PUBLIC_ACTOR_LABEL = "Редактор"

# ---- limits --------------------------------------------------------------------
MAX_BODY = 64 * 1024
DRAIN_CAP = 8 * 1024 * 1024   # DECISION: drain oversized bodies up to 8 MiB so clients read 413, not RST
SESSION_TTL = 8 * 3600
COOKIE_NAME = "civic_session"
PBKDF2_ITERATIONS = 260_000
LOGIN_FAILS_PER_USER = 8      # per (client ip, username) in LOGIN_WINDOW
LOGIN_FAILS_PER_IP = 32       # per client ip, any usernames (stops username spraying)
LOGIN_WINDOW = 600
FEEDBACK_LIMIT = int(os.environ.get("R10_ORACLE_FEEDBACK_LIMIT") or 20)
FEEDBACK_WINDOW = 600         # rate-limit window and duplicate window
MISMATCH_METERS = 2000.0
ASTANA_BBOX = (70.9, 50.8, 72.0, 51.5)  # lon_min, lat_min, lon_max, lat_max
TZ = dt.timezone(dt.timedelta(hours=5))
DUMMY_HASH = f"pbkdf2_sha256${PBKDF2_ITERATIONS}${'00' * 16}${'00' * 32}"  # equal work for unknown users
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
URL_RE = re.compile(r"https?://[^\s/?#]+[^\s]*", re.IGNORECASE)
INDEX_HTML = ("<!doctype html><meta charset=utf-8><title>R10 oracle</title>"
              "<p>R10 oracle: reference civic-v1 server for acceptance self-test. Not product code.</p>")


# ---- small helpers ---------------------------------------------------------------
def now_iso() -> str:
    return dt.datetime.now(TZ).isoformat(timespec="microseconds")


def is_date(v) -> bool:
    if not isinstance(v, str) or not DATE_RE.fullmatch(v):
        return False
    try:
        dt.date.fromisoformat(v)
    except ValueError:
        return False
    return True


def is_timestamp(v) -> bool:
    if not isinstance(v, str) or "T" not in v or len(v) > 40:
        return False
    try:
        return dt.datetime.fromisoformat(v[:-1] + "+00:00" if v.endswith("Z") else v).tzinfo is not None
    except ValueError:
        return False


def is_number(v) -> bool:
    """Finite JSON number and not a bool."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return isinstance(v, int) or math.isfinite(v) or M("accept_nan")  # MUTANT accept_nan


def in_enum(v, allowed) -> bool:
    return isinstance(v, str) and v in allowed


def text_or_null(v, limit: int = 500) -> bool:
    return v is None or (isinstance(v, str) and len(v) <= limit)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def distance_m(a, b) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


class ApiError(Exception):
    def __init__(self, status, code, message, fields=None, headers=None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.fields, self.headers = fields, headers or {}


def not_found(what: str = "object") -> ApiError:
    # Identical for draft, archived and nonexistent: existence is not revealed.
    return ApiError(404, "not_found", f"{what} not found")


def invalid(fields: dict):
    raise ApiError(422, "validation_error", "request failed validation", fields)


def error_body(code, message, fields=None) -> dict:
    err = {"code": code, "message": message}
    if fields:
        err["fields"] = fields
    return {"ok": False, "error": err}


def encode_cursor(key) -> str:
    return base64.urlsafe_b64encode(str(key).encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(text: str):
    """Opaque cursor -> last key, or None when it is not one we issued."""
    try:
        raw = base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"-_", validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    return raw if raw and encode_cursor(raw) == text else None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8", "surrogatepass"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8", "surrogatepass"),
                                     bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


# ---- storage -----------------------------------------------------------------------
SCHEMA_MAIN = """
CREATE TABLE IF NOT EXISTS editors (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (sid_hash TEXT PRIMARY KEY, username TEXT NOT NULL,
  csrf_token TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS feedback_items (seq INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT UNIQUE NOT NULL, receipt_id TEXT UNIQUE NOT NULL, object_id TEXT, geometry TEXT,
  category TEXT NOT NULL, text TEXT NOT NULL, consent_public INTEGER NOT NULL,
  status TEXT NOT NULL, public_reply TEXT, reason TEXT, revision INTEGER NOT NULL,
  created_at TEXT NOT NULL, created_ts REAL NOT NULL, moderated_at TEXT,
  client_ip_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feedback_history (seq INTEGER PRIMARY KEY AUTOINCREMENT,
  feedback_id TEXT NOT NULL, revision INTEGER NOT NULL, at TEXT NOT NULL, action TEXT NOT NULL,
  reason TEXT, actor_user TEXT NOT NULL);
"""
SCHEMA_OBJECTS = """
CREATE TABLE IF NOT EXISTS objects (id TEXT PRIMARY KEY, data TEXT NOT NULL, internal_notes TEXT,
  created_by TEXT NOT NULL, publication TEXT NOT NULL, revision INTEGER NOT NULL,
  first_published_at TEXT, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS object_history (seq INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT UNIQUE NOT NULL, object_id TEXT NOT NULL, revision INTEGER NOT NULL, at TEXT NOT NULL,
  changed_fields TEXT NOT NULL, reason TEXT, public_actor_label TEXT NOT NULL,
  actor_user TEXT NOT NULL, public INTEGER NOT NULL, diff TEXT NOT NULL);
"""


class Store:
    """SQLite in WAL mode; one connection per request; writes serialized by a lock."""

    def __init__(self, path: str):
        self.path = path
        self.lock = threading.RLock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._open()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA_MAIN + SCHEMA_OBJECTS)
        conn.close()
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)
        self.shared = None
        if M("memory_db"):  # MUTANT memory_db: object tables shadowed by TEMP tables, lost on restart
            self.shared = self._open(check_same_thread=False)
            self.shared.executescript(SCHEMA_OBJECTS.replace("CREATE TABLE", "CREATE TEMP TABLE"))

    def _open(self, **kw) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None, **kw)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    @contextlib.contextmanager
    def tx(self, write: bool = False):
        conn = self.shared or self._open()
        guard = self.lock if (write or self.shared) else contextlib.nullcontext()
        with guard:
            try:
                if write:
                    conn.execute("BEGIN IMMEDIATE")
                yield conn
                if write:
                    conn.execute("COMMIT")
            except BaseException:
                if write and conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                if conn is not self.shared:
                    conn.close()


# ---- object validation ---------------------------------------------------------------
def merge(base: dict, changes: dict, errors: dict) -> dict:
    """Apply a partial object: nested objects merge key by key; `a.b` dotted keys also accepted."""
    out = copy.deepcopy(base)
    for key, value in changes.items():
        top, _, sub = key.partition(".")
        if sub and top in NESTED:  # DECISION: {"schedule.current_planned_end": x} == nested form
            key, value = top, {sub: value}
        if key in SERVER_OWNED:
            continue
        if key not in EDITABLE and key not in STAFF_ONLY:
            errors.setdefault(key, "unknown or read-only field")
            continue
        if key in NESTED:
            if not isinstance(value, dict):
                errors.setdefault(key, "must be an object")
                continue
            for sub_key, sub_value in value.items():
                if sub_key in NESTED[key]:
                    out[key][sub_key] = sub_value
                else:
                    errors.setdefault(f"{key}.{sub_key}", "unknown field")
        else:
            out[key] = value
    return out


def check_geometry(g, where: str, errors: dict):
    if g is None:
        return None
    if not isinstance(g, dict) or not in_enum(g.get("type"), GEOMETRY_TYPES):
        errors.setdefault(where, "must be null or a GeoJSON Point, LineString or Polygon")
        return None
    lon_min, lat_min, lon_max, lat_max = ASTANA_BBOX

    def pos(p) -> bool:
        return (isinstance(p, list) and len(p) in (2, 3) and all(is_number(v) for v in p)
                and lon_min <= p[0] <= lon_max and lat_min <= p[1] <= lat_max)

    kind, coords = g["type"], g.get("coordinates")
    if kind == "Point":
        ok = pos(coords)
    elif kind == "LineString":
        ok = isinstance(coords, list) and len(coords) >= 2 and all(pos(p) for p in coords)
    else:
        ok = isinstance(coords, list) and len(coords) >= 1 and all(
            isinstance(ring, list) and len(ring) >= 4 and all(pos(p) for p in ring) and ring[0] == ring[-1]
            for ring in coords)
    if not ok:
        errors.setdefault(where, "coordinates must be [lon, lat] inside Astana (lon 70.9..72.0, "
                                 "lat 50.8..51.5); LineString >= 2 positions; Polygon rings closed")
        return None
    return {"type": kind, "coordinates": coords}


def check_source_refs(refs, errors: dict) -> list:
    """Normalize source_refs to the full civic-v1 key set. URLs are stored, NEVER fetched."""
    if not isinstance(refs, list) or len(refs) > 50:
        errors.setdefault("source_refs", "must be a list of at most 50 objects")
        return []
    out = []
    for i, ref in enumerate(refs):
        where = f"source_refs[{i}]"
        if not isinstance(ref, dict):
            errors.setdefault(where, "must be an object")
            continue
        extra = sorted(set(ref) - set(SOURCE_REF_KEYS))
        if extra:
            errors.setdefault(where, f"unknown keys: {', '.join(extra)}")
        n = {k: ref.get(k) for k in SOURCE_REF_KEYS}
        n["access_status"] = ref.get("access_status", "not_fetched")  # DECISION: default not_fetched
        n["fields"] = ref.get("fields", [])
        url = n["url"]
        if url is not None and not (isinstance(url, str) and len(url) <= 2000 and URL_RE.fullmatch(url)):
            errors.setdefault(f"{where}.url", "must be an http(s) URL or null")
        for key in ("id", "publisher", "license"):
            if not text_or_null(n[key]):
                errors.setdefault(f"{where}.{key}", "must be text or null")
        for key in ("published_on", "retrieved_at"):
            if n[key] is not None and not (is_date(n[key]) or is_timestamp(n[key])):
                errors.setdefault(f"{where}.{key}", "must be YYYY-MM-DD, ISO8601 timestamp or null")
        if not in_enum(n["access_status"], ACCESS_STATUSES):
            errors.setdefault(f"{where}.access_status", "must be fetched, not_fetched or unavailable")
        fields = n["fields"]
        if not (isinstance(fields, list) and len(fields) <= 50
                and all(isinstance(f, str) and len(f) <= 100 for f in fields)):
            errors.setdefault(f"{where}.fields", "must be a list of field paths")
        out.append(n)
    return out


def validate_state(st: dict, errors: dict) -> dict:
    """Check a whole merged editable state; returns it with geometry/source_refs normalized."""
    out = dict(st)
    err = errors.setdefault
    for key, limit in (("title", 200), ("description", 5000), ("evidence_notes", 5000), ("internal_notes", 5000)):
        v = out.get(key)
        if key == "internal_notes" and v is None:
            continue
        if not isinstance(v, str):
            err(key, "must be a string")
        elif key == "title" and not v.strip():
            err(key, "must not be empty")
        elif len(v) > limit:
            err(key, f"must be at most {limit} characters")
    for key, allowed in (("kind", KINDS), ("status", STATUSES), ("geometry_precision", PRECISIONS),
                         ("evidence_type", EVIDENCE_TYPES)):
        if not in_enum(out.get(key), allowed):
            err(key, "must be one of: " + ", ".join(sorted(allowed)))
    out["geometry"] = check_geometry(out.get("geometry"), "geometry", errors)
    if out["geometry"] is None and out.get("geometry_precision") == "source":
        err("geometry_precision", "precision 'source' needs a geometry")

    sch = out["schedule"]
    for key in SCHEDULE_KEYS:
        if sch.get(key) is not None and not is_date(sch[key]):
            err(f"schedule.{key}", "must be a real date YYYY-MM-DD or null")
    if (is_date(sch.get("planned_start")) and is_date(sch.get("current_planned_end"))
            and sch["current_planned_end"] < sch["planned_start"]):
        err("schedule.current_planned_end", "must not be before planned_start")
    if sch.get("actual_end") is not None and out.get("status") != "completed":
        err("schedule.actual_end", "allowed only with status=completed")  # never auto-set either

    budget = out["budget"]
    if M("budget_zero") and budget.get("amount_kzt") is None:  # MUTANT budget_zero
        budget["amount_kzt"] = 0
    amount = budget.get("amount_kzt")
    if amount is not None and (not is_number(amount) or amount < 0):
        err("budget.amount_kzt", "must be a finite number >= 0 or null")
    if not in_enum(budget.get("basis"), BUDGET_BASES):
        err("budget.basis", "must be one of: " + ", ".join(sorted(BUDGET_BASES)))
    elif amount is None and budget["basis"] != "unknown":
        err("budget.basis", "a known basis needs amount_kzt; unknown amount means basis=unknown")
    if not text_or_null(budget.get("source_id"), 200):
        err("budget.source_id", "must be text or null")
    for key in RESPONSIBLE_KEYS:
        if not text_or_null(out["responsible"].get(key)):
            err(f"responsible.{key}", "must be text (<= 500) or null")

    out["source_refs"] = check_source_refs(out.get("source_refs"), errors)
    if out.get("evidence_type") == "observed" and not out["source_refs"]:
        err("evidence_type", "observed needs at least one source_ref")  # DECISION: as R10 validator
    return out


def changed_paths(before: dict, after: dict) -> list:
    out = []
    for key in EDITABLE + STAFF_ONLY:
        if key in NESTED:
            out += [f"{key}.{s}" for s in NESTED[key] if before[key].get(s) != after[key].get(s)]
        elif before.get(key) != after.get(key):
            out.append(key)
    return out


def get_path(state: dict, path: str):
    top, _, sub = path.partition(".")
    return state[top][sub] if sub else state.get(top)


def reason_of(body: dict):
    reason = body.get("reason")
    if reason is not None and (not isinstance(reason, str) or len(reason) > 1000):
        invalid({"reason": "must be text up to 1000 characters or null"})
    return (reason.strip() or None) if isinstance(reason, str) else None


def check_revision(body: dict, current: int):
    expected = body.get("expected_revision")
    if isinstance(expected, bool) or not isinstance(expected, int):
        invalid({"expected_revision": "required integer"})
    if expected != current and not M("no_409"):  # MUTANT no_409
        raise ApiError(409, "stale_revision", f"stale expected_revision; current revision is {current}")


def fetch_sources(refs: list):
    """MUTANT ssrf only. The correct server never dereferences source URLs."""
    if M("ssrf"):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for ref in refs:
            with contextlib.suppress(Exception):
                opener.open(ref["url"], timeout=1).close() if ref.get("url") else None


# ---- object persistence and projections ----------------------------------------------
def load_object(conn, oid: str):
    row = conn.execute("SELECT * FROM objects WHERE id=?", (oid,)).fetchone()
    return None if row is None else (json.loads(row["data"]), row)


def state_of(obj: dict, row) -> dict:
    state = {k: copy.deepcopy(obj[k]) for k in EDITABLE}
    state["internal_notes"] = row["internal_notes"]
    return state


def build_object(oid: str, state: dict, publication: str, revision: int) -> dict:
    src = dict(state, schema_version="civic-v1", id=oid, city="astana", publication=publication,
               revision=revision, updated_at=now_iso())
    return {k: copy.deepcopy(src[k]) for k in OBJECT_FIELDS}


def save_object(conn, obj: dict, internal_notes, first_published_at, created_by: str):
    conn.execute(
        "INSERT INTO objects (id, data, internal_notes, created_by, publication, revision, "
        "first_published_at, updated_at) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
        "data=excluded.data, internal_notes=excluded.internal_notes, publication=excluded.publication, "
        "revision=excluded.revision, first_published_at=excluded.first_published_at, "
        "updated_at=excluded.updated_at",
        (obj["id"], json.dumps(obj, ensure_ascii=False, allow_nan=M("accept_nan")), internal_notes,
         created_by, obj["publication"], obj["revision"], first_published_at, obj["updated_at"]))


def add_history(conn, obj: dict, changed: list, reason, who: dict, public: bool, diff: dict):
    conn.execute(
        "INSERT INTO object_history (id, object_id, revision, at, changed_fields, reason, "
        "public_actor_label, actor_user, public, diff) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("hist-" + secrets.token_hex(8), obj["id"], obj["revision"], obj["updated_at"],
         json.dumps(list(changed)), reason, PUBLIC_ACTOR_LABEL, who["username"], int(public),
         json.dumps(diff, ensure_ascii=False, allow_nan=M("accept_nan"))))


def history_rows(conn, oid: str):
    return conn.execute("SELECT * FROM object_history WHERE object_id=? ORDER BY revision, seq", (oid,)).fetchall()


def visible(publication: str, *, detail: bool) -> bool:
    if publication == "published":
        return True
    if publication == "archived":
        return M("archive_visible")  # MUTANT archive_visible
    return M("draft_public") if detail else M("list_drafts")  # MUTANT draft_public / list_drafts


def public_item(obj: dict, row) -> dict:
    item = {k: obj[k] for k in OBJECT_FIELDS}  # strict civic-v1 allowlist
    if M("leak_internal"):  # MUTANT leak_internal
        item.update(internal_notes=row["internal_notes"], created_by=row["created_by"])
    return item


def public_history(row):
    """Public projection: allowlisted keys, public fields only; internal-only entries vanish."""
    fields = [f for f in json.loads(row["changed_fields"]) if f.split(".")[0] in OBJECT_FIELDS]
    if not fields:
        return None
    label = row["actor_user"] if M("history_username") else row["public_actor_label"]  # MUTANT history_username
    return {"id": row["id"], "object_id": row["object_id"], "revision": row["revision"], "at": row["at"],
            "changed_fields": fields, "reason": row["reason"], "public_actor_label": label}


def staff_history(row) -> dict:
    # DECISION: editors see the service diff and the public flag, not the internal actor_user.
    return {"id": row["id"], "object_id": row["object_id"], "revision": row["revision"], "at": row["at"],
            "changed_fields": json.loads(row["changed_fields"]), "reason": row["reason"],
            "public_actor_label": row["public_actor_label"], "public": bool(row["public"]),
            "diff": json.loads(row["diff"])}


def staff_feedback(r) -> dict:
    return {"id": r["id"], "receipt_id": r["receipt_id"], "object_id": r["object_id"],
            "geometry": json.loads(r["geometry"]) if r["geometry"] else None, "category": r["category"],
            "text": r["text"], "consent_public": bool(r["consent_public"]), "status": r["status"],
            "public_reply": r["public_reply"], "reason": r["reason"], "revision": r["revision"],
            "created_at": r["created_at"], "moderated_at": r["moderated_at"]}


def session_view(who) -> dict:
    if not who:
        return {"authenticated": False, "user": None, "csrf_token": None}
    return {"authenticated": True, "user": {"name": who["username"], "role": "editor"},
            "csrf_token": who["csrf"]}


def list_filters(query: dict, enums: dict) -> dict:
    one = {k: v[0] for k, v in query.items()}
    f, errors = {}, {}
    for key, allowed in enums.items():
        f[key] = one.get(key)
        if f[key] is not None and f[key] not in allowed:
            errors[key] = "must be one of: " + ", ".join(sorted(allowed))
    for key in ("from", "to"):
        f[key] = one.get(key)
        if f[key] is not None and not is_date(f[key]):
            errors[key] = "must be a real date YYYY-MM-DD"
    if not errors.keys() & {"from", "to"} and f["from"] and f["to"] and f["from"] > f["to"]:
        errors["to"] = "must not be before from"
    limit = one.get("limit", "50")
    f["limit"] = int(limit) if re.fullmatch(r"[0-9]{1,3}", limit) else 0
    if not 1 <= f["limit"] <= 100:
        errors["limit"] = "must be an integer 1..100"
    f["cursor"] = None
    if "cursor" in one:
        f["cursor"] = decode_cursor(one["cursor"])
        if f["cursor"] is None:
            errors["cursor"] = "invalid cursor"
    if errors:
        raise ApiError(400, "bad_query", "invalid query parameters", errors)
    return f


def object_matches(obj: dict, f: dict) -> bool:
    for key in ("kind", "status", "publication"):
        if f.get(key) and obj.get(key) != f[key]:
            return False
    if f["from"] or f["to"]:
        # Known interval [planned_start, current_planned_end] must intersect [from, to];
        # an unknown end is open; with both unknown the object matches no date filter.
        start, end = obj["schedule"]["planned_start"], obj["schedule"]["current_planned_end"]
        if start is None and end is None:
            return False
        if f["to"] and start and start > f["to"]:
            return False
        if f["from"] and end and end < f["from"]:
            return False
    return True


# ---- HTTP --------------------------------------------------------------------------
ROUTES = [(method, re.compile(pattern), name, staff) for method, pattern, name, staff in (
    ("GET", r"/session", "session", False),
    ("POST", r"/session/login", "login", False),
    ("POST", r"/session/logout", "logout", False),
    ("GET", r"/objects", "list_public", False),
    ("GET", r"/objects/(?P<oid>[^/]+)", "detail_public", False),
    ("GET", r"/objects/(?P<oid>[^/]+)/feedback", "feedback_public", False),
    ("POST", r"/feedback", "feedback_submit", False),
    ("GET", r"/staff/objects", "list_staff", True),
    ("POST", r"/staff/objects", "create", True),
    ("GET", r"/staff/objects/(?P<oid>[^/]+)", "detail_staff", True),
    ("POST", r"/staff/objects/(?P<oid>[^/]+)/(?P<action>update|publish|archive)", "object_action", True),
    ("GET", r"/staff/feedback", "feedback_queue", True),
    ("POST", r"/staff/feedback/(?P<fid>[^/]+)/moderate", "moderate", True),
)]


class OracleServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, address, store: Store):
        super().__init__(address, Handler)
        self.store = store
        port = self.server_address[1]
        self.allowed_hosts = {f"{h}:{port}" for h in ("127.0.0.1", "localhost", "[::1]", address[0].lower())}
        self.failures: dict[str, list[float]] = {}
        self.failures_lock = threading.Lock()

    def login_gate(self, keys: dict):
        cutoff = time.monotonic() - LOGIN_WINDOW
        with self.failures_lock:
            for key, limit in keys.items():
                recent = [t for t in self.failures.get(key, ()) if t > cutoff]
                self.failures[key] = recent
                if len(recent) >= limit:
                    raise ApiError(429, "rate_limited", "too many failed logins; try again later",
                                   headers={"Retry-After": str(LOGIN_WINDOW)})

    def login_failed(self, keys: dict):
        with self.failures_lock:
            for key in keys:
                self.failures.setdefault(key, []).append(time.monotonic())

    def login_succeeded(self, key: str):
        with self.failures_lock:
            self.failures.pop(key, None)


class Handler(BaseHTTPRequestHandler):
    server_version = "R10-oracle"
    sys_version = ""
    timeout = 30

    # -- plumbing -------------------------------------------------------------
    def do_GET(self):
        try:
            self.route()
        except ApiError as e:
            self.send_json(e.status, error_body(e.code, e.message, e.fields), e.headers)
        except RecursionError:
            self.send_json(400, error_body("bad_request", "request is nested too deeply"))
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception as e:  # never a traceback to the client; log only type and location
            frame = traceback.extract_tb(e.__traceback__)[-1]
            self.log_message("internal error %s at %s:%s", type(e).__name__, frame.name, frame.lineno)
            self.send_json(500, error_body("internal_error", "internal server error"))

    do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = do_GET

    def send_error(self, code, message=None, explain=None):
        """Protocol-level errors raised by http.server itself are JSON as well."""
        self.close_connection = True
        try:
            phrase = HTTPStatus(code).phrase
        except ValueError:
            phrase = "error"
        self.send_json(code, error_body("http_error", phrase))

    def send_bytes(self, status: int, raw: bytes, ctype: str, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def send_json(self, status: int, body: dict, headers=None):
        raw = json.dumps(body, ensure_ascii=False, allow_nan=M("accept_nan")).encode("utf-8")
        self.send_bytes(status, raw, "application/json; charset=utf-8", headers)

    def ok(self, data, status: int = 200, headers=None):
        self.send_json(status, {"ok": True, "data": data}, headers)

    def read_body(self) -> bytes:
        """Always consume the body first so an early error never meets unread bytes (RST)."""
        if self.headers.get("Transfer-Encoding"):
            self.close_connection = True
            raise ApiError(411, "length_required", "Content-Length is required")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0:
            self.close_connection = True
            raise ApiError(400, "bad_request", "invalid Content-Length")
        if length > MAX_BODY and not M("no_size_limit"):  # MUTANT no_size_limit
            left = min(length, DRAIN_CAP)
            while left > 0:
                chunk = self.rfile.read(min(left, 65536))
                if not chunk:
                    break
                left -= len(chunk)
            self.close_connection = True
            raise ApiError(413, "too_large", f"request body exceeds {MAX_BODY} bytes")
        return self.rfile.read(length) if length else b""

    def parse_json(self, raw: bytes) -> dict:
        ctype = self.headers.get("Content-Type")
        if not raw and ctype is None:
            return {}  # bodiless POST (e.g. logout) counts as {}
        if (ctype or "").split(";")[0].strip().lower() != "application/json":
            raise ApiError(415, "unsupported_media_type", "Content-Type must be application/json")

        def reject_constant(token):
            raise ValueError(f"non-finite number {token}")

        def finite_float(text):
            value = float(text)
            if not math.isfinite(value):
                raise ValueError("number out of range")
            return value

        try:
            if M("accept_nan"):  # MUTANT accept_nan
                value = json.loads(raw.decode("utf-8"))
            else:
                value = json.loads(raw.decode("utf-8"), parse_constant=reject_constant, parse_float=finite_float)
        except (ValueError, UnicodeDecodeError, RecursionError):
            message = traceback.format_exc() if M("traceback") else "request body is not valid JSON"  # MUTANT traceback
            raise ApiError(400, "bad_json", message) from None
        if not isinstance(value, dict):
            raise ApiError(400, "bad_request", "JSON body must be an object")
        return value

    def check_host_origin(self):
        if M("no_origin"):  # MUTANT no_origin
            return
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in self.server.allowed_hosts:
            raise ApiError(403, "bad_host", "unexpected Host header")
        origin = self.headers.get("Origin")
        if origin is not None and origin.strip().lower() != "http://" + host:
            raise ApiError(403, "bad_origin", "cross-origin write refused")

    def check_csrf(self, who: dict):
        if M("no_csrf"):  # MUTANT no_csrf
            return
        sent = (self.headers.get("X-CSRF-Token") or "").encode("utf-8", "replace")
        if not hmac.compare_digest(sent, who["csrf"].encode("utf-8")):
            raise ApiError(403, "csrf_failed", "missing or invalid X-CSRF-Token")

    def principal(self):
        """Server-side identity from the session cookie only (never from body or headers)."""
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except CookieError:
            return None
        morsel = jar.get(COOKIE_NAME)
        if morsel is None or not morsel.value:
            return None
        sid_hash = sha256(morsel.value)
        with self.server.store.tx() as conn:
            row = conn.execute("SELECT username, csrf_token FROM sessions WHERE sid_hash=? AND revoked=0 "
                               "AND expires_at>?", (sid_hash, time.time())).fetchone()
        return {"username": row["username"], "csrf": row["csrf_token"], "sid_hash": sid_hash} if row else None

    def leak_file(self, path: str) -> bool:
        """MUTANT static_leak only: serve files beside the DB. The correct server serves no files."""
        rel = unquote(path).lstrip("/")
        rel = rel[len(".runtime/"):] if rel.startswith(".runtime/") else rel
        target = Path(self.server.store.path).resolve().parent / rel
        if not rel or not target.is_file():
            return False
        self.send_bytes(200, target.read_bytes(), "application/octet-stream")
        return True

    def route(self):
        raw = self.read_body()
        url = urlsplit(self.path)
        if not url.path.startswith(PREFIX + "/"):
            if M("static_leak") and self.command == "GET" and self.leak_file(url.path):  # MUTANT static_leak
                return
            if url.path == "/" and self.command == "GET":
                return self.send_bytes(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8",
                                       {"Content-Security-Policy": "default-src 'none'"})
            raise ApiError(404, "not_found", "no such resource")  # no static file serving at all
        sub, match, allowed = url.path[len(PREFIX):], None, set()
        for method, rx, name, staff in ROUTES:
            m = rx.fullmatch(sub)
            if m:
                allowed.add(method)
                if method == self.command:
                    match = (m, name, staff)
                    break
        if match is None:
            if allowed:
                raise ApiError(405, "method_not_allowed", f"{self.command} is not allowed here",
                               headers={"Allow": ", ".join(sorted(allowed))})
            raise ApiError(404, "not_found", "unknown API path")
        m, name, staff = match
        params = {k: unquote(v) for k, v in m.groupdict().items()}
        if self.command == "POST":
            self.check_host_origin()
        who = self.principal()
        if staff and not (name == "moderate" and M("anon_moderate")):  # MUTANT anon_moderate
            if who is None:
                raise ApiError(401, "unauthenticated", "editor session required")
            if self.command == "POST":
                self.check_csrf(who)
        body = self.parse_json(raw) if self.command == "POST" else None
        try:
            query = parse_qs(url.query, max_num_fields=50)
        except ValueError:
            raise ApiError(400, "bad_query", "too many query parameters") from None
        getattr(self, "h_" + name)(params, query, body, who)

    # -- session --------------------------------------------------------------
    def h_session(self, params, query, body, who):
        self.ok(session_view(who))

    def h_login(self, params, query, body, who):
        user, password = body.get("username"), body.get("password")
        errors = {}
        if not isinstance(user, str) or not 1 <= len(user) <= 128:
            errors["username"] = "required text"
        if not isinstance(password, str) or not 1 <= len(password) <= 1024:
            errors["password"] = "required text"
        if errors:
            invalid(errors)
        ip = self.client_address[0]
        user_key = f"user:{ip}:{user.lower()}"
        keys = {f"ip:{ip}": LOGIN_FAILS_PER_IP, user_key: LOGIN_FAILS_PER_USER}
        self.server.login_gate(keys)  # 429 applies to correct passwords too while blocked
        with self.server.store.tx() as conn:
            row = conn.execute("SELECT password_hash FROM editors WHERE username=?", (user,)).fetchone()
        good = verify_password(password, row["password_hash"] if row else DUMMY_HASH) and row is not None
        if M("role_from_body") and "editor" in (body.get("role"), self.headers.get("X-Role")):  # MUTANT role_from_body
            good = True
        if not good:
            self.server.login_failed(keys)
            raise ApiError(401, "bad_credentials", "wrong username or password")
        self.server.login_succeeded(user_key)
        sid, csrf, t = secrets.token_urlsafe(32), secrets.token_urlsafe(32), time.time()
        with self.server.store.tx(write=True) as conn:
            if who:  # a new login ends the previous session (no fixation)
                conn.execute("UPDATE sessions SET revoked=1 WHERE sid_hash=?", (who["sid_hash"],))
            conn.execute("INSERT INTO sessions (sid_hash, username, csrf_token, created_at, expires_at) "
                         "VALUES (?,?,?,?,?)", (sha256(sid), user, csrf, t, t + SESSION_TTL))
        flags = "" if M("cookie_flags") else "; HttpOnly; SameSite=Strict"  # MUTANT cookie_flags
        cookie = f"{COOKIE_NAME}={sid}; Path=/; Max-Age={SESSION_TTL}{flags}"
        self.ok(session_view({"username": user, "csrf": csrf}), headers={"Set-Cookie": cookie})

    def h_logout(self, params, query, body, who):
        if who:
            self.check_csrf(who)  # DECISION: logout with a live session is a write -> CSRF required
            if not M("logout_noop"):  # MUTANT logout_noop
                with self.server.store.tx(write=True) as conn:
                    conn.execute("UPDATE sessions SET revoked=1 WHERE sid_hash=?", (who["sid_hash"],))
        expired = f"{COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
        self.ok(session_view(None), headers={"Set-Cookie": expired})

    # -- objects --------------------------------------------------------------
    def list_objects(self, query, staff: bool) -> dict:
        enums = {"kind": KINDS, "status": STATUSES}
        if staff:
            enums["publication"] = PUBLICATIONS
        f = list_filters(query, enums)
        with self.server.store.tx() as conn:
            rows = conn.execute("SELECT data, publication, internal_notes, created_by FROM objects").fetchall()
        items = []
        for row in rows:
            obj = json.loads(row["data"])
            if (staff or visible(row["publication"], detail=False)) and object_matches(obj, f):
                items.append(obj if staff else public_item(obj, row))
        items.sort(key=lambda o: o["id"])  # stable order by id; cursor = last id seen
        if f["cursor"] is not None:
            items = [o for o in items if o["id"] > f["cursor"]]
        page = items[: f["limit"]]
        return {"items": page, "next_cursor": encode_cursor(page[-1]["id"]) if len(items) > len(page) else None}

    def h_list_public(self, params, query, body, who):
        self.ok(self.list_objects(query, staff=False))

    def h_list_staff(self, params, query, body, who):
        self.ok(self.list_objects(query, staff=True))

    def visible_object(self, conn, oid: str):
        got = load_object(conn, oid)
        if got is None or not visible(got[1]["publication"], detail=True):
            raise not_found()
        return got

    def h_detail_public(self, params, query, body, who):
        with self.server.store.tx() as conn:
            obj, row = self.visible_object(conn, params["oid"])
            rows = history_rows(conn, obj["id"])
        shown = [r for r in rows if r["public"] or M("draft_history_public")]  # MUTANT draft_history_public
        history = [h for h in map(public_history, shown) if h]
        self.ok({"item": public_item(obj, row), "history": history})

    def h_detail_staff(self, params, query, body, who):
        with self.server.store.tx() as conn:
            got = load_object(conn, params["oid"])
            if got is None:
                raise not_found()
            rows = history_rows(conn, params["oid"])
        obj, row = got
        self.ok({"item": obj, "history": [staff_history(r) for r in rows],
                 "internal": {"internal_notes": row["internal_notes"], "created_by": row["created_by"],
                              "first_published_at": row["first_published_at"]}})

    def h_create(self, params, query, body, who):
        reason = reason_of(body)
        fields = {k: v for k, v in body.items() if k != "reason"}
        errors = {k: "required" for k in ("kind", "title", "evidence_type") if k not in fields}
        state = merge(DEFAULT_STATE, fields, errors)
        if M("today_dates") and state["schedule"]["planned_start"] is None:  # MUTANT today_dates
            state["schedule"]["planned_start"] = dt.date.today().isoformat()
        state = validate_state(state, errors)
        if errors:
            invalid(errors)
        publication = "draft"
        if M("body_publication") and in_enum(body.get("publication"), PUBLICATIONS):  # MUTANT body_publication
            publication = body["publication"]
        obj = build_object("obj-" + secrets.token_hex(8), state, publication, 1)
        with self.server.store.tx(write=True) as conn:
            save_object(conn, obj, state["internal_notes"], None, who["username"])
            add_history(conn, obj, list(EDITABLE), reason, who, publication == "published", {"created": True})
        fetch_sources(state["source_refs"])
        self.ok({"item": obj}, status=201)

    def h_object_action(self, params, query, body, who):
        action, refs = params["action"], []
        with self.server.store.tx(write=True) as conn:
            got = load_object(conn, params["oid"])
            if got is None:
                raise not_found()
            obj, row = got
            check_revision(body, obj["revision"])
            reason = reason_of(body)
            state, first = state_of(obj, row), row["first_published_at"]
            publication = obj["publication"]
            if action == "update":
                state, changed = self.apply_changes(obj, state, first, body, reason)
                public = publication == "published"
                refs = state["source_refs"]
            elif action == "publish":
                if publication == "published":
                    raise ApiError(409, "invalid_state", "object is already published")
                changed, public, publication = ["publication"], True, "published"
                if first is None:  # first publication fixes the original planned end
                    first = now_iso()
                    sch = state["schedule"]
                    if sch["original_planned_end"] is None and sch["current_planned_end"] is not None:
                        sch["original_planned_end"] = sch["current_planned_end"]
                        changed.append("schedule.original_planned_end")
            else:
                if publication == "archived":
                    raise ApiError(409, "invalid_state", "object is already archived")
                changed, public, publication = ["publication"], False, "archived"
            if changed:
                before = state_of(obj, row)
                diff = {p: {"from": get_path(before, p), "to": get_path(state, p)} for p in changed if p != "publication"}
                if action != "update":
                    diff["publication"] = {"from": obj["publication"], "to": publication}
                new = build_object(obj["id"], state, publication, obj["revision"] + 1)
                save_object(conn, new, state["internal_notes"], first, row["created_by"])
                add_history(conn, new, changed, reason, who, public, diff)
            else:
                new = obj  # DECISION: a no-op update keeps the revision and writes no history
        fetch_sources(refs)
        self.ok({"item": new})

    @staticmethod
    def apply_changes(obj: dict, before: dict, first_published, body: dict, reason):
        changes = body.get("changes")
        if not isinstance(changes, dict):
            invalid({"changes": "must be an object with the fields to change"})
        errors = {}
        after = validate_state(merge(before, changes, errors), errors)
        if errors:
            invalid(errors)
        changed = changed_paths(before, after)
        if first_published and "schedule.original_planned_end" in changed:
            errors["schedule.original_planned_end"] = "fixed at first publication; change current_planned_end"
        touches_public = any(p not in STAFF_ONLY for p in changed)
        if obj["publication"] != "draft" and touches_public and not reason and not M("no_reason"):  # MUTANT no_reason
            errors["reason"] = "a reason is required to change a published object"
        if errors:
            invalid(errors)
        if M("overwrite_original") and "schedule.current_planned_end" in changed:  # MUTANT overwrite_original
            after["schedule"]["original_planned_end"] = after["schedule"]["current_planned_end"]
        return after, changed

    # -- feedback -------------------------------------------------------------
    def h_feedback_submit(self, params, query, body, who):
        oid, text, consent = body.get("object_id"), body.get("text"), body.get("consent_public", False)
        errors = {}
        if oid is not None and (not isinstance(oid, str) or not 1 <= len(oid) <= 200):
            errors["object_id"] = "must be an object id or null"
        geometry = check_geometry(body.get("geometry"), "geometry", errors)
        if oid is None and body.get("geometry") is None:
            errors["object_id"] = "object_id or geometry is required"
        if not in_enum(body.get("category"), FEEDBACK_CATEGORIES):
            errors["category"] = "must be one of: " + ", ".join(sorted(FEEDBACK_CATEGORIES))
        if not isinstance(text, str) or len(text.strip()) < 3 or len(text) > 2000:
            errors["text"] = "must be 3..2000 characters"
        if not isinstance(consent, bool):
            errors["consent_public"] = "must be true or false"
        if errors:
            invalid(errors)
        ip_hash = sha256("r10-oracle-client:" + self.client_address[0])
        geo_json = json.dumps(geometry, sort_keys=True) if geometry else None
        t, dup, receipt = time.time(), None, None
        with self.server.store.tx(write=True) as conn:
            if oid is not None:
                got = load_object(conn, oid)
                accepted = ("published", "draft") if M("feedback_draft") else ("published",)  # MUTANT feedback_draft
                if got is None or got[0]["publication"] not in accepted:
                    raise not_found()  # same answer for draft, archived and nonexistent
                target = got[0]["geometry"]
                if (geometry and geometry["type"] == "Point" and target and target["type"] == "Point"
                        and distance_m(geometry["coordinates"], target["coordinates"]) > MISMATCH_METERS):
                    raise ApiError(422, "location_mismatch", "the point is more than 2 km from the object",
                                   {"geometry": "does not match the object location"})
            if not M("dup_feedback"):  # MUTANT dup_feedback
                dup = conn.execute(
                    "SELECT receipt_id, status FROM feedback_items WHERE client_ip_hash=? AND object_id IS ? "
                    "AND (? IS NOT NULL OR geometry IS ?) AND text=? AND created_ts>? ORDER BY seq DESC LIMIT 1",
                    (ip_hash, oid, oid, geo_json, text, t - FEEDBACK_WINDOW)).fetchone()
            if dup is None:
                recent = conn.execute("SELECT COUNT(*) FROM feedback_items WHERE client_ip_hash=? AND created_ts>?",
                                      (ip_hash, t - FEEDBACK_WINDOW)).fetchone()[0]
                if recent >= FEEDBACK_LIMIT:
                    raise ApiError(429, "rate_limited", "too many submissions; try again later",
                                   headers={"Retry-After": str(FEEDBACK_WINDOW)})
                receipt = "rcpt-" + secrets.token_hex(8)
                conn.execute(
                    "INSERT INTO feedback_items (id, receipt_id, object_id, geometry, category, text, "
                    "consent_public, status, revision, created_at, created_ts, client_ip_hash) "
                    "VALUES (?,?,?,?,?,?,?,'pending',1,?,?,?)",
                    ("fb-" + secrets.token_hex(8), receipt, oid, geo_json, body["category"], text,
                     int(consent), now_iso(), t, ip_hash))
        if dup is not None:  # DECISION: duplicate answers 200 with the existing receipt and its status
            return self.ok({"receipt_id": dup["receipt_id"], "moderation": dup["status"], "duplicate": True})
        self.ok({"receipt_id": receipt, "moderation": "pending"}, status=201)

    def h_feedback_public(self, params, query, body, who):
        statuses = ("approved", "pending") if M("pending_public") else ("approved",)  # MUTANT pending_public
        with self.server.store.tx() as conn:
            self.visible_object(conn, params["oid"])
            rows = conn.execute(
                f"SELECT * FROM feedback_items WHERE object_id=? AND status IN ({','.join('?' * len(statuses))}) "
                "ORDER BY seq", (params["oid"], *statuses)).fetchall()
        items = [{"id": r["id"], "category": r["category"],
                  "text": r["text"] if r["consent_public"] or M("no_consent") else None,  # MUTANT no_consent
                  "public_reply": r["public_reply"], "moderated_at": r["moderated_at"]} for r in rows]
        self.ok({"items": items})

    def h_feedback_queue(self, params, query, body, who):
        f = list_filters(query, {"status": FEEDBACK_STATUSES})
        if f["cursor"] is not None and not re.fullmatch(r"[0-9]{1,18}", f["cursor"]):
            raise ApiError(400, "bad_query", "invalid query parameters", {"cursor": "invalid cursor"})
        sql, args = "SELECT * FROM feedback_items WHERE seq>?", [int(f["cursor"] or 0)]
        if f["status"]:
            sql, args = sql + " AND status=?", args + [f["status"]]
        oid = (query.get("object_id") or [None])[0]
        if oid:
            sql, args = sql + " AND object_id=?", args + [oid]
        with self.server.store.tx() as conn:
            rows = conn.execute(sql + " ORDER BY seq LIMIT ?", (*args, f["limit"] + 1)).fetchall()
        page = rows[: f["limit"]]
        self.ok({"items": [staff_feedback(r) for r in page],
                 "next_cursor": encode_cursor(page[-1]["seq"]) if len(rows) > len(page) else None})

    def h_moderate(self, params, query, body, who):
        with self.server.store.tx(write=True) as conn:
            row = conn.execute("SELECT * FROM feedback_items WHERE id=?", (params["fid"],)).fetchone()
            if row is None:
                raise not_found("feedback")
            check_revision(body, row["revision"])
            reason, action, reply = reason_of(body), body.get("action"), body.get("public_reply")
            errors = {}
            if not in_enum(action, ("approve", "reject")):
                errors["action"] = "must be approve or reject"
            if not text_or_null(reply, 2000):
                errors["public_reply"] = "must be text up to 2000 characters or null"
            if errors:
                invalid(errors)
            at = now_iso()
            conn.execute("UPDATE feedback_items SET status=?, public_reply=?, reason=?, revision=revision+1, "
                         "moderated_at=? WHERE id=?",
                         ("approved" if action == "approve" else "rejected", reply, reason, at, row["id"]))
            conn.execute("INSERT INTO feedback_history (feedback_id, revision, at, action, reason, actor_user) "
                         "VALUES (?,?,?,?,?,?)", (row["id"], row["revision"] + 1, at, action, reason,
                                                  who["username"] if who else "anonymous"))
            row = conn.execute("SELECT * FROM feedback_items WHERE id=?", (row["id"],)).fetchone()
        self.ok({"item": staff_feedback(row)})


# ---- CLI ------------------------------------------------------------------------------
def cmd_serve(args) -> int:
    store = Store(args.db)
    httpd = OracleServer((args.host, args.port), store)

    def stop(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    print(f"R10 oracle (NOT product code) on http://{args.host}:{httpd.server_address[1]}; "
          f"mutants: {', '.join(sorted(MUTANTS)) or 'none'}", flush=True)
    try:
        httpd.serve_forever(poll_interval=0.2)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        httpd.server_close()
    return 0


def cmd_create_editor(args) -> int:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", args.username):
        print("username must be 1-64 characters of A-Z a-z 0-9 _ . -", file=sys.stderr)
        return 2
    try:
        password = getpass.getpass("Password: ")
        repeat = getpass.getpass("Repeat password: ")
    except (EOFError, KeyboardInterrupt):
        print("\naborted; nothing changed.", file=sys.stderr)
        return 2
    if password != repeat:
        print("Passwords do not match; nothing changed.", file=sys.stderr)
        return 2
    if len(password) < 10:
        print("Password must have at least 10 characters; nothing changed.", file=sys.stderr)
        return 2
    store = Store(args.db)
    with store.tx(write=True) as conn:
        existed = conn.execute("SELECT 1 FROM editors WHERE username=?", (args.username,)).fetchone()
        conn.execute("INSERT INTO editors (username, password_hash, created_at) VALUES (?,?,?) "
                     "ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash",
                     (args.username, hash_password(password), now_iso()))
        conn.execute("UPDATE sessions SET revoked=1 WHERE username=?", (args.username,))
    print(f"Editor {args.username!r} {'password reset' if existed else 'created'} in {args.db}.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R10 civic-v1 reference oracle (test-only; NOT product code)")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the HTTP server")
    serve.add_argument("--db", required=True)
    serve.add_argument("--port", type=int, required=True)
    serve.add_argument("--host", default="127.0.0.1")
    editor = sub.add_parser("create-editor", help="create or reset a local editor; password via getpass")
    editor.add_argument("--db", required=True)
    editor.add_argument("--username", required=True)
    args = parser.parse_args(argv)
    unknown = MUTANTS - KNOWN_MUTANTS
    if unknown:  # a typo must not silently run the correct oracle and fake a "killed" result
        print(f"unknown R10_ORACLE_MUTANT name(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    return cmd_serve(args) if args.command == "serve" else cmd_create_editor(args)


if __name__ == "__main__":
    sys.exit(main())
