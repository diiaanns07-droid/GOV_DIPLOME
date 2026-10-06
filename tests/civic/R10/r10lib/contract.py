"""Independent civic-v1 checks written by R10 from CONTRACT.txt (PACK_SHA 9c2f5c0).

Nothing here is imported from product code: the point is to compare the product
against a second reading of the contract. Functions return lists of problems
(empty list == conforms) so tests can show every violation at once.
"""

from __future__ import annotations

import datetime as _dt
import math
import re

SCHEMA_VERSION = "civic-v1"
KINDS = {"construction", "roadworks", "landscaping", "event"}
STATUSES = {"planned", "in_progress", "completed", "cancelled", "unknown"}
PUBLICATIONS = {"draft", "published", "archived"}
PRECISIONS = {"source", "approximate", "unknown"}
EVIDENCE_TYPES = {"observed", "derived", "hypothesis", "synthetic"}
BUDGET_BASES = {"planned", "contract", "spent", "unknown"}
ACCESS_STATUSES = {"fetched", "not_fetched", "unavailable"}
GEOMETRY_TYPES = {"Point", "LineString", "Polygon"}
FEEDBACK_LABELS = {"roads", "sidewalks", "transport_stops", "lighting", "landscaping", "other"}

OBJECT_FIELDS = {
    "schema_version", "id", "city", "kind", "title", "description", "status",
    "publication", "geometry", "geometry_precision", "schedule", "budget",
    "responsible", "evidence_type", "source_refs", "evidence_notes",
    "updated_at", "revision",
}
SCHEDULE_FIELDS = {"planned_start", "original_planned_end", "current_planned_end", "actual_end"}
BUDGET_FIELDS = {"amount_kzt", "basis", "source_id"}
RESPONSIBLE_FIELDS = {"organization", "public_contact"}
SOURCE_REF_FIELDS = {"id", "url", "publisher", "published_on", "retrieved_at",
                     "access_status", "license", "fields"}
HISTORY_FIELDS = {"id", "object_id", "revision", "at", "changed_fields", "reason",
                  "public_actor_label"}
# Fields the client may send on create/update (server owns the rest).
CLIENT_EDITABLE = {"kind", "title", "description", "status", "geometry",
                   "geometry_precision", "schedule", "budget", "responsible",
                   "evidence_type", "source_refs", "evidence_notes"}
SERVER_OWNED = {"id", "revision", "updated_at", "publication", "schema_version", "city"}

# Key names that must never reach a public projection (CONTRACT §1, §3).
SENSITIVE_KEY = re.compile(
    r"(password|passwd|hash|salt|secret|token|csrf|session|cookie|internal|"
    r"private|author_contact|contact_email|email|phone|ip_addr|client_ip|"
    r"user_agent|username|login|created_by|updated_by|actor_id|editor_id|user_id)",
    re.IGNORECASE,
)
TRACEBACK_MARKERS = ("Traceback (most recent call last)", 'File "/', "File \"C:\\",
                     "sqlite3.", "OperationalError", "<html", "<!DOCTYPE")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")

# Generous envelope around Astana (city + suburbs). Used only to catch swapped
# lon/lat or a different city, never to claim that a point is correct.
ASTANA_BBOX = (70.9, 50.8, 72.0, 51.5)  # lon_min, lat_min, lon_max, lat_max


def is_date(value) -> bool:
    if not isinstance(value, str) or not DATE_RE.match(value):
        return False
    try:
        _dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def is_timestamp(value) -> bool:
    """ISO8601 timestamp with explicit offset or Z (server-assigned updated_at/at)."""
    if not isinstance(value, str) or "T" not in value:
        return False
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _finite_number(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _position(pos, where, problems, bbox):
    if (not isinstance(pos, list) or len(pos) not in (2, 3)
            or not all(_finite_number(v) for v in pos)):
        problems.append(f"{where}: position must be [lon, lat] finite numbers")
        return
    lon, lat = pos[0], pos[1]
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        problems.append(f"{where}: out of WGS84 range {pos}")
        return
    if bbox:
        lon_min, lat_min, lon_max, lat_max = bbox
        if not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max):
            swapped = lon_min <= lat <= lon_max and lat_min <= lon <= lat_max
            problems.append(f"{where}: {pos} outside Astana envelope"
                            + (" (looks like swapped [lat, lon])" if swapped else ""))


def check_geometry(geometry, where="geometry", bbox=ASTANA_BBOX) -> list[str]:
    problems: list[str] = []
    if geometry is None:
        return problems
    if not isinstance(geometry, dict) or geometry.get("type") not in GEOMETRY_TYPES:
        return [f"{where}: must be null or GeoJSON Point|LineString|Polygon"]
    coords = geometry.get("coordinates")
    kind = geometry["type"]
    if kind == "Point":
        _position(coords, where, problems, bbox)
    elif kind == "LineString":
        if not isinstance(coords, list) or len(coords) < 2:
            problems.append(f"{where}: LineString needs >= 2 positions")
        else:
            for i, pos in enumerate(coords):
                _position(pos, f"{where}[{i}]", problems, bbox)
    else:
        if not isinstance(coords, list) or not coords:
            problems.append(f"{where}: Polygon needs rings")
        else:
            for r, ring in enumerate(coords):
                if not isinstance(ring, list) or len(ring) < 4:
                    problems.append(f"{where}: ring {r} needs >= 4 positions")
                    continue
                if ring[0] != ring[-1]:
                    problems.append(f"{where}: ring {r} not closed")
                for i, pos in enumerate(ring):
                    _position(pos, f"{where}[{r}][{i}]", problems, bbox)
    return problems


def check_object(obj, *, public: bool = False, strict_keys: bool = True) -> list[str]:
    """Validate one civic-v1 object. public=True adds projection rules."""
    p: list[str] = []
    if not isinstance(obj, dict):
        return ["object is not a JSON object"]
    missing = OBJECT_FIELDS - obj.keys()
    if missing:
        p.append(f"missing fields: {sorted(missing)}")
    extra = obj.keys() - OBJECT_FIELDS
    if extra and strict_keys:
        p.append(f"fields outside civic-v1 allowlist: {sorted(extra)}")
    for key in obj:
        if SENSITIVE_KEY.search(key):
            p.append(f"sensitive-looking key exposed: {key}")
    if obj.get("schema_version") != SCHEMA_VERSION:
        p.append(f"schema_version={obj.get('schema_version')!r}")
    if not isinstance(obj.get("id"), str) or not obj.get("id"):
        p.append("id must be non-empty string")
    if obj.get("city") != "astana":
        p.append(f"city={obj.get('city')!r}")
    for key, allowed in (("kind", KINDS), ("status", STATUSES), ("publication", PUBLICATIONS),
                         ("geometry_precision", PRECISIONS), ("evidence_type", EVIDENCE_TYPES)):
        if key in obj and obj[key] not in allowed:
            p.append(f"{key}={obj[key]!r} not in {sorted(allowed)}")
    for key in ("title", "description", "evidence_notes"):
        if key in obj and not isinstance(obj[key], str):
            p.append(f"{key} must be string")
    if not isinstance(obj.get("title"), str) or not obj.get("title", "").strip():
        p.append("title must be non-empty text")
    p += check_geometry(obj.get("geometry"))
    if obj.get("geometry") is None and obj.get("geometry_precision") == "source":
        p.append("geometry is null but geometry_precision=source")

    sched = obj.get("schedule")
    if not isinstance(sched, dict):
        p.append("schedule must be object")
    else:
        if set(sched) != SCHEDULE_FIELDS:
            p.append(f"schedule keys {sorted(sched)} != {sorted(SCHEDULE_FIELDS)}")
        for key in SCHEDULE_FIELDS & sched.keys():
            if sched[key] is not None and not is_date(sched[key]):
                p.append(f"schedule.{key}={sched[key]!r} not YYYY-MM-DD or null")
        start, cur = sched.get("planned_start"), sched.get("current_planned_end")
        if is_date(start) and is_date(cur) and cur < start:
            p.append("schedule.current_planned_end before planned_start")
        if sched.get("actual_end") is not None and obj.get("status") != "completed":
            p.append("schedule.actual_end set while status != completed")

    budget = obj.get("budget")
    if not isinstance(budget, dict):
        p.append("budget must be object")
    else:
        if set(budget) != BUDGET_FIELDS:
            p.append(f"budget keys {sorted(budget)} != {sorted(BUDGET_FIELDS)}")
        amount = budget.get("amount_kzt")
        if amount is not None and not (_finite_number(amount) and amount >= 0):
            p.append(f"budget.amount_kzt={amount!r} must be finite >= 0 or null")
        if budget.get("basis") not in BUDGET_BASES:
            p.append(f"budget.basis={budget.get('basis')!r}")
        if amount is None and budget.get("basis") not in ("unknown", None):
            p.append("budget.amount_kzt null but basis claims a known amount")
        if budget.get("source_id") is not None and not isinstance(budget.get("source_id"), str):
            p.append("budget.source_id must be string|null")

    resp = obj.get("responsible")
    if not isinstance(resp, dict) or set(resp) != RESPONSIBLE_FIELDS:
        p.append("responsible must be {organization, public_contact}")
    else:
        for key in RESPONSIBLE_FIELDS:
            if resp[key] is not None and not isinstance(resp[key], str):
                p.append(f"responsible.{key} must be string|null")

    refs = obj.get("source_refs")
    if not isinstance(refs, list):
        p.append("source_refs must be list")
    else:
        for i, ref in enumerate(refs):
            if not isinstance(ref, dict):
                p.append(f"source_refs[{i}] not object")
                continue
            if set(ref) != SOURCE_REF_FIELDS:
                p.append(f"source_refs[{i}] keys {sorted(ref)}")
            if ref.get("access_status") not in ACCESS_STATUSES:
                p.append(f"source_refs[{i}].access_status={ref.get('access_status')!r}")
            if not isinstance(ref.get("fields"), list):
                p.append(f"source_refs[{i}].fields must be list of field paths")
            url = ref.get("url")
            if url is not None and not (isinstance(url, str) and url.startswith(("https://", "http://"))):
                p.append(f"source_refs[{i}].url not http(s)")
            for key in ("published_on",):
                if ref.get(key) is not None and not is_date(ref[key]) and not is_timestamp(ref[key]):
                    p.append(f"source_refs[{i}].{key} not a date")
        if obj.get("evidence_type") == "observed" and not refs:
            p.append("evidence_type=observed without any source_refs")

    rev = obj.get("revision")
    if not (isinstance(rev, int) and not isinstance(rev, bool) and rev >= 1):
        p.append(f"revision={rev!r} must be integer >= 1")
    if not is_timestamp(obj.get("updated_at")):
        p.append(f"updated_at={obj.get('updated_at')!r} not ISO8601 with offset")
    if public and obj.get("publication") not in (None, "published"):
        p.append(f"public projection contains publication={obj.get('publication')!r}")
    return p


def check_history_entry(entry, *, public: bool = True, object_id=None) -> list[str]:
    p: list[str] = []
    if not isinstance(entry, dict):
        return ["history entry not object"]
    missing = HISTORY_FIELDS - entry.keys()
    if missing:
        p.append(f"history missing {sorted(missing)}")
    if public:
        extra = entry.keys() - HISTORY_FIELDS
        if extra:
            p.append(f"public history has fields outside allowlist: {sorted(extra)}")
        for key in entry:
            if SENSITIVE_KEY.search(key):
                p.append(f"sensitive-looking history key: {key}")
    if object_id is not None and entry.get("object_id") != object_id:
        p.append(f"history object_id {entry.get('object_id')!r} != {object_id!r}")
    if not isinstance(entry.get("changed_fields"), list):
        p.append("changed_fields must be list")
    if not is_timestamp(entry.get("at")):
        p.append(f"history.at={entry.get('at')!r} not timestamp")
    rev = entry.get("revision")
    if not (isinstance(rev, int) and not isinstance(rev, bool) and rev >= 1):
        p.append(f"history.revision={rev!r}")
    return p


def check_envelope(body, status: int) -> list[str]:
    """CONTRACT §2: {ok:true,data} for 2xx, {ok:false,error:{code,message,fields?}} otherwise."""
    if not isinstance(body, dict):
        return [f"HTTP {status}: body is not a JSON object envelope"]
    if 200 <= status < 300:
        if body.get("ok") is not True or "data" not in body:
            return [f"HTTP {status}: success envelope must be ok:true + data"]
        return []
    err = body.get("error")
    p = []
    if body.get("ok") is not False:
        p.append(f"HTTP {status}: error envelope must have ok:false")
    if not isinstance(err, dict) or not isinstance(err.get("code"), str) \
            or not isinstance(err.get("message"), str):
        p.append(f"HTTP {status}: error must be {{code:str, message:str}}")
    return p


def find_text_leaks(payload_text: str, secrets) -> list[str]:
    """Return which secret strings occur verbatim inside a response body."""
    return [s for s in secrets if s and s in payload_text]


def has_traceback(text: str) -> bool:
    return any(marker in text for marker in TRACEBACK_MARKERS)


DELIVERY_KEYS = {"round", "role", "branch", "base_sha", "pack_sha", "status", "owned_paths",
                 "integration_notes", "code_commit", "checks", "limitations", "next_step"}


def check_delivery(doc, role: str | None = None, pack_sha: str | None = None) -> list[str]:
    p: list[str] = []
    if not isinstance(doc, dict):
        return ["DELIVERY is not an object"]
    missing = DELIVERY_KEYS - doc.keys()
    if missing:
        p.append(f"DELIVERY missing {sorted(missing)}")
    if doc.get("round") != 11:
        p.append(f"round={doc.get('round')!r}")
    if role and doc.get("role") != role:
        p.append(f"role={doc.get('role')!r} != {role}")
    if pack_sha and doc.get("pack_sha") not in (pack_sha, pack_sha[:7]) \
            and not str(doc.get("pack_sha", "")).startswith(pack_sha[:7]):
        p.append(f"pack_sha={doc.get('pack_sha')!r} != {pack_sha[:12]}")
    if doc.get("status") not in ("partial", "ready"):
        p.append(f"status={doc.get('status')!r}")
    for i, chk in enumerate(doc.get("checks") or []):
        if not isinstance(chk, dict) or chk.get("status") not in ("PASS", "FAIL", "NOT_RUN"):
            p.append(f"checks[{i}] status must be PASS|FAIL|NOT_RUN")
    return p
