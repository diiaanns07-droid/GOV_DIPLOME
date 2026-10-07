"""civic-v1 validator for the R05 Astana data package (round 11).

Stdlib only. Three profiles:

* ``contract`` - only the shape rules of research/round-11/CONTRACT.txt (what any
  civic-v1 consumer such as R02 must accept or reject).
* ``real``     - contract + R05 provenance rules for records that claim to be real
  Astana works/events: every material value must be backed by a fetched source
  whose ``fields`` list names it; synthetic records are rejected.
* ``demo``     - contract + rules for the separate synthetic demo slice: records must
  be visibly synthetic, carry no budget amounts and no real-looking source links.

Issues are dicts ``{code, severity, path, message}``; severity is ``error`` or
``warning``. A record is valid for a profile when it has no ``error`` issues.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
import re
from typing import Any, Iterable
from urllib.parse import urlparse

SCHEMA_VERSION = "civic-v1"
CITY = "astana"

KINDS = ("construction", "roadworks", "landscaping", "event")
STATUSES = ("planned", "in_progress", "completed", "cancelled", "unknown")
PUBLICATIONS = ("draft", "published", "archived")
PRECISIONS = ("source", "approximate", "unknown")
BASES = ("planned", "contract", "spent", "unknown")
EVIDENCE_TYPES = ("observed", "derived", "hypothesis", "synthetic")
ACCESS_STATUSES = ("fetched", "not_fetched", "unavailable")
GEOMETRY_TYPES = ("Point", "LineString", "Polygon")

TOP_LEVEL_KEYS = (
    "schema_version", "id", "city", "kind", "title", "description", "status",
    "publication", "geometry", "geometry_precision", "schedule", "budget",
    "responsible", "evidence_type", "source_refs", "evidence_notes",
    "updated_at", "revision",
)
SCHEDULE_KEYS = ("planned_start", "original_planned_end", "current_planned_end", "actual_end")
BUDGET_KEYS = ("amount_kzt", "basis", "source_id")
RESPONSIBLE_KEYS = ("organization", "public_contact")
SOURCE_REF_KEYS = ("id", "url", "publisher", "published_on", "retrieved_at",
                   "access_status", "license", "fields")

# Paths that may appear in source_refs[].fields.
FIELD_PATHS = frozenset(
    ["kind", "title", "description", "status", "geometry", "geometry_precision"]
    + ["schedule." + k for k in SCHEDULE_KEYS]
    + ["budget." + k for k in BUDGET_KEYS if k != "source_id"]
    + ["responsible." + k for k in RESPONSIBLE_KEYS]
)

# Content fields as R02 accepts them in source_refs[].fields paths (first segment).
CONTENT_FIELDS = ("kind", "title", "description", "status", "geometry", "geometry_precision",
                  "schedule", "budget", "responsible", "evidence_type", "source_refs", "evidence_notes")
COARSE_FIELD_PATH_RE = re.compile(r"^[a-z_]{1,40}(\.[a-z_]{1,40}){0,2}$")

# Map services whose geometry must never be copied (viewing licence != extraction licence).
PROPRIETARY_MAP_LABELS = frozenset({"2gis", "google", "yandex"})
PROPRIETARY_MAP_DOMAINS = ("goo.gl", "here.com", "apple.com")

ASTANA_TZ = _dt.timezone(_dt.timedelta(hours=5))  # Kazakhstan: single zone UTC+5 since 2024-03-01
MIN_YEAR, MAX_YEAR = 1990, 2100                   # same window as R02 validate.py

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")  # R02 civic_objects.id is <= 64 chars
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})$")
# Any tag opener (closed or not) or any named/decimal/hex character reference.
HTML_RE = re.compile(r"<\s*[/!?A-Za-z]|&(?:#[xX][0-9A-Fa-f]+|#\d+|[A-Za-z][A-Za-z0-9]{1,31});")
# C0 (except tab/LF/CR), DEL, C1, zero-width, line/paragraph separators, bidi embeddings/isolates, BOM.
CTRL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2060-\u2064\u2066-\u2069\ufeff\ud800-\udfff]")
LINEBREAK_RE = re.compile(r"[\t\n\r]")
DIGIT_RUN_RE = re.compile(r"\+?\d[\d\s\-().]{8,}\d")
IIN_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")
EMAIL_RE = re.compile(r"[\w.%+-]+[@\uff20][\w-]+(?:\.[\w-]+)*\.\w{2,}")
URL_BAD_CHARS_RE = re.compile(r"[\s\"'<>`\\\x00-\x1f\x7f-\x9f]")
SYNTHETIC_MARK_RE = re.compile(r"\b(?:демо|demo|synthetic)\b|синтетическ\w*\s+(?:запис|данн|пример)|демонстрационн", re.I)

# Text limits follow R02 ui/civic_store/validate.py MAX_TEXT so an R05-valid record imports.
TITLE_MAX = 200
DESCRIPTION_MAX = 5000
NOTES_MAX = 2000
ORGANIZATION_MAX = 300
CONTACT_MAX = 200
URL_MAX = 2000
STATUS_MAX_AGE_DAYS = 45  # planned/in_progress claims older than this are stale
MAX_LINE_KM = 60.0

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GEOFENCE_PATH = os.path.join(os.path.dirname(_HERE), "geofence.json")


def _issue(code: str, path: str, message: str, severity: str = "error") -> dict:
    return {"code": code, "severity": severity, "path": path, "message": message}


def parse_date(value: Any) -> _dt.date | None:
    if not isinstance(value, str) or not DATE_RE.match(value):
        return None
    try:
        d = _dt.date.fromisoformat(value)
    except ValueError:
        return None
    return d if MIN_YEAR <= d.year <= MAX_YEAR else None


def parse_ts(value: Any) -> _dt.datetime | None:
    if not isinstance(value, str) or not TS_RE.match(value):
        return None
    try:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:  # a JSON integer with hundreds of digits
        return False


def _d(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _l(value: Any) -> list:
    return value if isinstance(value, list) else []


def astana_date(ts: _dt.datetime) -> _dt.date:
    """Calendar date in Astana for a timestamp (published_on dates are local dates)."""
    return ts.astimezone(ASTANA_TZ).date()


def _shoelace(ring: list) -> float:
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2.0


def proprietary_host(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    labels = host.split(".")
    if any(label in PROPRIETARY_MAP_LABELS for label in labels[:-1]):
        return True
    return any(host == d or host.endswith("." + d) for d in PROPRIETARY_MAP_DOMAINS)


def check_url(url: Any) -> str | None:
    """Return None for an acceptable absolute http(s) URL, else a reason (mirrors R02 clean_url)."""
    if not isinstance(url, str) or not url or len(url) > URL_MAX:
        return f"url must be a non-empty string of at most {URL_MAX} characters"
    if URL_BAD_CHARS_RE.search(url):
        return "url must not contain spaces, quotes, angle brackets or control characters"
    try:
        parts = urlparse(url)
        port_ok = parts.port is None or 0 < parts.port < 65536
    except ValueError:
        return "url cannot be parsed"
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return "url must be an absolute http(s) URL with a host"
    if parts.username is not None or parts.password is not None:
        return "url must not carry a user name or password"
    if not port_ok:
        return "url port is invalid"
    return None


# ---------------------------------------------------------------- geofence

def load_geofence(path: str | None = None) -> dict | None:
    """Load the Astana geofence produced by build_geofence (None if missing)."""
    path = path or DEFAULT_GEOFENCE_PATH
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _point_in_ring(lon: float, lat: float, ring: list) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            x_cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lon < x_cross:
                inside = not inside
        j = i
    return inside


def _point_in_polygon(lon: float, lat: float, rings: list) -> bool:
    if not rings or not _point_in_ring(lon, lat, rings[0]):
        return False
    return not any(_point_in_ring(lon, lat, hole) for hole in rings[1:])


def fence_position(lon: float, lat: float, fence: dict) -> str:
    """Return 'inside', 'margin' (in the outer bbox but not in a district) or 'outside'."""
    bbox = fence["outer_bbox"]
    if not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
        return "outside"
    for poly in fence["polygons"]:
        if _point_in_polygon(lon, lat, poly["rings"]):
            return "inside"
    return "margin"


def _positions(geometry: dict) -> list:
    coords = geometry.get("coordinates")
    gtype = geometry.get("type")
    if gtype == "Point":
        return [coords]
    if gtype == "LineString":
        return list(coords)
    if gtype == "Polygon":
        return [p for ring in coords for p in ring]
    return []


def haversine_km(a: list, b: list) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def _segments_cross(p1, p2, p3, p4) -> bool:
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-15 else (1 if v > 0 else -1)
    o1, o2, o3, o4 = orient(p1, p2, p3), orient(p1, p2, p4), orient(p3, p4, p1), orient(p3, p4, p2)
    return o1 != o2 and o3 != o4 and 0 not in (o1, o2, o3, o4)


def _ring_self_intersects(ring: list) -> bool:
    n = len(ring) - 1  # closed ring, last == first
    if n > 600:
        return False  # too large for the quadratic check; not expected in this package
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # adjacent through the closing vertex
            if _segments_cross(ring[i], ring[i + 1], ring[j], ring[j + 1]):
                return True
    return False


def _validate_position(pos: Any, path: str, issues: list) -> bool:
    if (not isinstance(pos, list) or len(pos) != 2
            or not all(_is_number(v) for v in pos)):
        issues.append(_issue("geometry_position", path, "position must be [longitude, latitude] finite numbers"))
        return False
    lon, lat = pos
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        issues.append(_issue("geometry_range", path, "longitude/latitude out of WGS84 range"))
        return False
    return True


def validate_geometry(geometry: Any, issues: list, fence: dict | None, path: str = "geometry") -> None:
    if geometry is None:
        return
    if not isinstance(geometry, dict):
        issues.append(_issue("geometry_type", path, "geometry must be a GeoJSON object or null"))
        return
    extra = set(geometry) - {"type", "coordinates"}
    if extra:
        issues.append(_issue("geometry_keys", path, f"unexpected geometry keys: {sorted(extra)}"))
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype not in GEOMETRY_TYPES:
        issues.append(_issue("geometry_type", path + ".type", f"geometry type must be one of {GEOMETRY_TYPES}"))
        return
    ok = True
    if gtype == "Point":
        ok = _validate_position(coords, path + ".coordinates", issues)
    elif gtype == "LineString":
        if not isinstance(coords, list) or len(coords) < 2:
            issues.append(_issue("geometry_linestring", path + ".coordinates", "LineString needs >= 2 positions"))
            return
        ok = all(_validate_position(p, f"{path}.coordinates[{i}]", issues) for i, p in enumerate(coords))
        if ok:
            length = sum(haversine_km(coords[i], coords[i + 1]) for i in range(len(coords) - 1))
            if length == 0:
                issues.append(_issue("geometry_degenerate", path, "LineString has zero length"))
            elif length > MAX_LINE_KM:
                issues.append(_issue("geometry_too_long", path,
                                     f"LineString is {length:.1f} km; a single civic object should be a local section"))
    elif gtype == "Polygon":
        if not isinstance(coords, list) or not coords:
            issues.append(_issue("geometry_polygon", path + ".coordinates", "Polygon needs at least one ring"))
            return
        for r, ring in enumerate(coords):
            rpath = f"{path}.coordinates[{r}]"
            if not isinstance(ring, list) or len(ring) < 4:
                issues.append(_issue("geometry_polygon", rpath, "linear ring needs >= 4 positions"))
                ok = False
                continue
            if not all(_validate_position(p, f"{rpath}[{i}]", issues) for i, p in enumerate(ring)):
                ok = False
                continue
            if ring[0] != ring[-1]:
                issues.append(_issue("geometry_ring_open", rpath, "linear ring must be closed (first == last)"))
                ok = False
            elif _ring_self_intersects(ring):
                issues.append(_issue("geometry_self_intersection", rpath, "linear ring self-intersects"))
                ok = False
            elif _shoelace(ring) == 0:
                issues.append(_issue("geometry_degenerate", rpath, "linear ring has zero area"))
                ok = False
        if ok and len(coords) > 1:
            shell = coords[0]
            for r, hole in enumerate(coords[1:], start=1):
                inside = all(_point_in_ring(v[0], v[1], shell) for v in hole[:-1])
                crosses = any(_segments_cross(hole[i], hole[i + 1], shell[j], shell[j + 1])
                              for i in range(len(hole) - 1) for j in range(len(shell) - 1))
                if not inside or crosses:
                    issues.append(_issue("geometry_hole_outside", f"{path}.coordinates[{r}]",
                                         "interior ring must lie inside the exterior ring"))
    if not ok or fence is None:
        return
    positions = _positions(geometry)
    states = [fence_position(p[0], p[1], fence) for p in positions]
    if "outside" in states:
        swapped = [fence_position(p[1], p[0], fence) for p in positions]
        if all(s != "outside" for s in swapped):
            issues.append(_issue("geometry_swapped", path,
                                 "coordinates look like [latitude, longitude]; civic-v1 requires [longitude, latitude]"))
        else:
            issues.append(_issue("geometry_outside_astana", path,
                                 "geometry lies outside the Astana geofence (city bbox + margin)"))
    elif "margin" in states:
        issues.append(_issue("geometry_outside_districts", path,
                             "geometry is near Astana but outside the OSM district polygons; check the location",
                             "warning"))


# ---------------------------------------------------------------- text

def _check_text(value: Any, path: str, issues: list, *, required: bool, max_len: int,
                single_line: bool = False, length_severity: str = "error") -> None:
    if not isinstance(value, str):
        issues.append(_issue("text_type", path, "must be a string"))
        return
    if required and not value.strip():
        issues.append(_issue("text_empty", path, "must not be empty"))
    if len(value) > max_len:
        issues.append(_issue("text_too_long", path, f"longer than {max_len} characters (R02 limit)", length_severity))
    if HTML_RE.search(value):
        issues.append(_issue("text_html", path, "plain text only; HTML tags/entities are not allowed"))
    if CTRL_RE.search(value):
        issues.append(_issue("text_control_chars", path,
                             "contains control, zero-width or bidi characters"))
    if single_line and LINEBREAK_RE.search(value):
        issues.append(_issue("text_line_break", path, "single-line field must not contain tabs or line breaks"))


def find_pii(value: Any) -> list[str]:
    """Phone numbers (KZ mobile/landline, any grouping), 12-digit IIN/BIN, e-mails."""
    if not isinstance(value, str):
        return []
    hits = []
    for m in DIGIT_RUN_RE.finditer(value):
        digits = re.sub(r"\D", "", m.group(0))
        if (len(digits) == 11 and digits[0] in "78" and digits[1] == "7") or (len(digits) == 10 and digits[0] == "7"):
            hits.append(m.group(0))
    hits += IIN_RE.findall(value)
    hits += EMAIL_RE.findall(value)
    return hits


def _check_pii(value: Any, path: str, issues: list, severity: str = "error") -> None:
    if find_pii(value):
        issues.append(_issue("pii_suspected", path,
                             "looks like a phone number, IIN or e-mail; personal data must not be stored", severity))


# ---------------------------------------------------------------- object

def _supported_fields(obj: dict) -> dict:
    """Map field path -> list of fetched source_refs that claim to support it."""
    support: dict[str, list] = {}
    for ref in _l(obj.get("source_refs")):
        if not isinstance(ref, dict) or ref.get("access_status") != "fetched":
            continue
        for f in _l(ref.get("fields")):
            if isinstance(f, str):
                support.setdefault(f, []).append(ref)
    return support


def material_claims(obj: dict) -> list[str]:
    """Field paths whose current value is a factual claim needing a source."""
    claims = []
    if obj.get("status") not in (None, "unknown"):
        claims.append("status")
    if obj.get("geometry") is not None and obj.get("geometry_precision") == "source":
        claims.append("geometry")
    for k in SCHEDULE_KEYS:
        if _d(obj.get("schedule")).get(k) is not None:
            claims.append("schedule." + k)
    budget = _d(obj.get("budget"))
    if budget.get("amount_kzt") is not None:
        claims.append("budget.amount_kzt")
    if budget.get("basis") not in (None, "unknown"):
        claims.append("budget.basis")
    for k in RESPONSIBLE_KEYS:
        if _d(obj.get("responsible")).get(k) is not None:
            claims.append("responsible." + k)
    return claims


def validate_object(obj: Any, *, profile: str = "contract", as_of: str | None = None,
                    fence: dict | None = None, max_status_age_days: int = STATUS_MAX_AGE_DAYS) -> list[dict]:
    """Validate one object. Never raises on JSON input (only on a bad ``profile`` argument)."""
    if profile not in ("contract", "real", "demo"):
        raise ValueError("profile must be contract, real or demo")
    try:
        return _validate_object(obj, profile, as_of, fence, max_status_age_days)
    except Exception as exc:  # defensive: a validator bug must surface as a rejection, not a crash
        return [_issue("validator_exception", "", f"{type(exc).__name__}: {exc}"[:300])]


def _validate_object(obj: Any, profile: str, as_of: str | None, fence: dict | None,
                     max_status_age_days: int) -> list[dict]:
    policy = "warning" if profile == "contract" else "error"  # R05 policies beyond the civic-v1 shape
    issues: list[dict] = []
    if not isinstance(obj, dict):
        return [_issue("object_type", "", "object must be a JSON object")]

    missing = [k for k in TOP_LEVEL_KEYS if k not in obj]
    for k in missing:
        issues.append(_issue("missing_field", k, "required civic-v1 field is missing"))
    extra = sorted(set(obj) - set(TOP_LEVEL_KEYS))
    for k in extra:
        issues.append(_issue("unknown_field", k, "field is not in the civic-v1 allowlist"))

    if obj.get("schema_version") != SCHEMA_VERSION:
        issues.append(_issue("schema_version", "schema_version", f"must be {SCHEMA_VERSION!r}"))
    oid = obj.get("id")
    if not isinstance(oid, str) or not oid:
        issues.append(_issue("id_type", "id", "id must be a non-empty string"))
    elif not ID_RE.match(oid):
        issues.append(_issue("id_format", "id", "R05 ids are lowercase [a-z0-9-], 3-64 chars", "warning"
                             if profile == "contract" else "error"))
    if obj.get("city") != CITY:
        issues.append(_issue("city", "city", "city must be 'astana'"))
    for key, allowed in (("kind", KINDS), ("status", STATUSES), ("publication", PUBLICATIONS),
                         ("geometry_precision", PRECISIONS), ("evidence_type", EVIDENCE_TYPES)):
        if key in obj and obj.get(key) not in allowed:
            issues.append(_issue("enum", key, f"must be one of {allowed}"))

    _check_text(obj.get("title"), "title", issues, required=True, max_len=TITLE_MAX,
                single_line=True, length_severity=policy)
    _check_text(obj.get("description"), "description", issues, required=False, max_len=DESCRIPTION_MAX,
                length_severity=policy)
    _check_text(obj.get("evidence_notes"), "evidence_notes", issues, required=False, max_len=NOTES_MAX,
                length_severity=policy)
    for key in ("title", "description", "evidence_notes"):
        _check_pii(obj.get(key), key, issues, policy)

    validate_geometry(obj.get("geometry"), issues, fence)

    # schedule
    schedule = obj.get("schedule")
    dates: dict[str, _dt.date | None] = {}
    if not isinstance(schedule, dict):
        if "schedule" in obj:
            issues.append(_issue("schedule_type", "schedule", "schedule must be an object"))
    else:
        for k in sorted(set(schedule) - set(SCHEDULE_KEYS)):
            issues.append(_issue("unknown_field", "schedule." + k, "not a civic-v1 schedule key"))
        for k in SCHEDULE_KEYS:
            if k not in schedule:
                issues.append(_issue("missing_field", "schedule." + k, "required (use null when unknown)"))
                continue
            v = schedule[k]
            if v is None:
                dates[k] = None
                continue
            d = parse_date(v)
            if d is None:
                issues.append(_issue("date_format", "schedule." + k, "must be YYYY-MM-DD or null"))
            dates[k] = d

    # budget
    budget = obj.get("budget")
    if not isinstance(budget, dict):
        if "budget" in obj:
            issues.append(_issue("budget_type", "budget", "budget must be an object"))
        budget = {}
    else:
        for k in sorted(set(budget) - set(BUDGET_KEYS)):
            issues.append(_issue("unknown_field", "budget." + k, "not a civic-v1 budget key"))
        for k in BUDGET_KEYS:
            if k not in budget:
                issues.append(_issue("missing_field", "budget." + k, "required (use null/unknown)"))
        amount = budget.get("amount_kzt")
        if amount is not None and (not _is_number(amount) or amount < 0):
            issues.append(_issue("budget_amount", "budget.amount_kzt", "must be a finite non-negative number or null"))
        if budget.get("basis") not in BASES:
            issues.append(_issue("enum", "budget.basis", f"must be one of {BASES}"))
        sid = budget.get("source_id")
        if sid is not None and not isinstance(sid, str):
            issues.append(_issue("budget_source", "budget.source_id", "must be a string or null"))

    responsible = obj.get("responsible")
    if not isinstance(responsible, dict):
        if "responsible" in obj:
            issues.append(_issue("responsible_type", "responsible", "responsible must be an object"))
        responsible = {}
    else:
        for k in sorted(set(responsible) - set(RESPONSIBLE_KEYS)):
            issues.append(_issue("unknown_field", "responsible." + k, "not a civic-v1 responsible key"))
        for k in RESPONSIBLE_KEYS:
            if k not in responsible:
                issues.append(_issue("missing_field", "responsible." + k, "required (use null when unknown)"))
            elif responsible[k] is not None:
                _check_text(responsible[k], "responsible." + k, issues, required=True,
                            max_len=CONTACT_MAX if k == "public_contact" else ORGANIZATION_MAX,
                            single_line=True, length_severity=policy)

    # source refs
    refs = obj.get("source_refs")
    ref_ids: dict[str, dict] = {}
    if not isinstance(refs, list):
        if "source_refs" in obj:
            issues.append(_issue("source_refs_type", "source_refs", "source_refs must be a list"))
        refs = []
    as_of_date = parse_date(as_of) if as_of else None
    for i, ref in enumerate(refs):
        rp = f"source_refs[{i}]"
        if not isinstance(ref, dict):
            issues.append(_issue("source_ref_type", rp, "source_ref must be an object"))
            continue
        for k in SOURCE_REF_KEYS:
            if k not in ref:
                issues.append(_issue("missing_field", f"{rp}.{k}", "required source_ref key"))
        for k in sorted(set(ref) - set(SOURCE_REF_KEYS)):
            issues.append(_issue("unknown_field", f"{rp}.{k}", "not a civic-v1 source_ref key"))
        rid = ref.get("id")
        if not isinstance(rid, str) or not rid:
            issues.append(_issue("source_ref_id", f"{rp}.id", "id must be a non-empty string"))
        elif rid in ref_ids:
            issues.append(_issue("source_ref_duplicate", f"{rp}.id", f"duplicate source_ref id {rid!r}"))
        else:
            ref_ids[rid] = ref
        url = ref.get("url")
        url_problem = check_url(url)
        if url_problem:
            issues.append(_issue("source_ref_url", f"{rp}.url", url_problem))
        if ref.get("access_status") not in ACCESS_STATUSES:
            issues.append(_issue("enum", f"{rp}.access_status", f"must be one of {ACCESS_STATUSES}"))
        pub = ref.get("published_on")
        pub_d = parse_date(pub) if pub is not None else None
        if pub is not None and pub_d is None:
            issues.append(_issue("date_format", f"{rp}.published_on", "must be YYYY-MM-DD or null"))
        ret = ref.get("retrieved_at")
        ret_ts = parse_ts(ret) if ret is not None else None
        if ret is not None and ret_ts is None:
            issues.append(_issue("timestamp_format", f"{rp}.retrieved_at", "must be ISO8601 with offset or null"))
        if ref.get("access_status") == "fetched" and ret is None:
            issues.append(_issue("fetched_without_time", f"{rp}.retrieved_at", "fetched source needs retrieved_at"))
        if pub_d and ret_ts and astana_date(ret_ts) < pub_d:
            issues.append(_issue("retrieved_before_published", f"{rp}", "retrieved_at is earlier than published_on"))
        if as_of_date and ret_ts and astana_date(ret_ts) > as_of_date + _dt.timedelta(days=1):
            issues.append(_issue("retrieved_in_future", f"{rp}.retrieved_at", "retrieved_at is after the slice as_of date"))
        lic = ref.get("license")
        if lic is not None and not isinstance(lic, str):
            issues.append(_issue("source_ref_license", f"{rp}.license", "license must be a string or null"))
        pubr = ref.get("publisher")
        if pubr is not None and not isinstance(pubr, str):
            issues.append(_issue("source_ref_publisher", f"{rp}.publisher", "publisher must be a string or null"))
        elif isinstance(pubr, str):
            _check_text(pubr, f"{rp}.publisher", issues, required=False, max_len=300, single_line=True,
                        length_severity=policy)
        if isinstance(lic, str):
            _check_text(lic, f"{rp}.license", issues, required=False, max_len=200, single_line=True,
                        length_severity=policy)
        fields = ref.get("fields")
        if not isinstance(fields, list) or not all(isinstance(f, str) for f in fields):
            issues.append(_issue("source_ref_fields", f"{rp}.fields", "fields must be a list of field paths"))
            fields = []
        for f in fields:
            if f in FIELD_PATHS:
                continue
            coarse_ok = bool(COARSE_FIELD_PATH_RE.match(f)) and f.split(".")[0] in CONTENT_FIELDS
            if profile == "contract" and coarse_ok:
                continue  # civic-v1 only says "paths of supported fields"; R02 accepts these
            issues.append(_issue("source_ref_field_path", f"{rp}.fields",
                                 f"field path {f!r} is not a supported leaf path"
                                 + (" (R05 real/demo slices need leaf paths such as schedule.planned_start)"
                                    if coarse_ok else "")))
        if fields and ref.get("access_status") != "fetched":
            sev = "warning" if profile == "contract" else "error"
            issues.append(_issue("unfetched_support", f"{rp}.fields",
                                 "a source that was not fetched cannot support field values", sev))
        try:
            host = urlparse(url).hostname or "" if isinstance(url, str) else ""
        except ValueError:
            host = ""
        if "geometry" in fields and proprietary_host(host):
            issues.append(_issue("proprietary_geometry", f"{rp}.fields",
                                 "geometry must not be copied from proprietary web maps", policy))

    sid = budget.get("source_id") if isinstance(budget, dict) else None
    if isinstance(sid, str) and sid not in ref_ids:
        issues.append(_issue("budget_source", "budget.source_id", "source_id must match a source_refs[].id"))

    if not isinstance(obj.get("updated_at"), str) or parse_ts(obj.get("updated_at")) is None:
        issues.append(_issue("timestamp_format", "updated_at", "updated_at must be ISO8601 with offset"))
    rev = obj.get("revision")
    if not isinstance(rev, int) or isinstance(rev, bool) or rev < 1:
        issues.append(_issue("revision", "revision", "revision must be an integer >= 1"))

    # ---- semantic rules shared by all profiles
    status = obj.get("status")
    actual_end = dates.get("actual_end")
    if actual_end is not None and status != "completed":
        issues.append(_issue("actual_end_without_completion", "schedule.actual_end",
                             "actual_end is set but status is not 'completed'"))
    if as_of_date and actual_end and actual_end > as_of_date:
        issues.append(_issue("actual_end_in_future", "schedule.actual_end",
                             "actual_end cannot be later than the slice date; an expected date is not an actual end"))
    ps = dates.get("planned_start")
    for key in ("original_planned_end", "current_planned_end", "actual_end"):
        end = dates.get(key)
        if ps and end and end < ps:  # R02 rejects this on import
            issues.append(_issue("schedule_order", "schedule." + key, f"{key} is before planned_start", policy))
    cpe = dates.get("current_planned_end")
    if cpe and dates.get("original_planned_end") is None and "original_planned_end" in (schedule or {}):
        issues.append(_issue("original_end_unknown", "schedule.original_planned_end",
                             "current end is known but the original end is not; history of delays cannot be shown",
                             "warning"))
    if obj.get("geometry") is None and obj.get("geometry_precision") not in (None, "unknown"):
        sev = "warning" if profile == "contract" else "error"
        issues.append(_issue("precision_without_geometry", "geometry_precision",
                             "geometry is null, so geometry_precision must be 'unknown'", sev))
    if obj.get("geometry") is not None and obj.get("geometry_precision") == "unknown":
        issues.append(_issue("geometry_precision_unknown", "geometry_precision",
                             "geometry is present but its precision is unknown", "warning"))
    amount = budget.get("amount_kzt") if isinstance(budget, dict) else None
    if isinstance(budget, dict) and amount is None and (budget.get("basis") not in (None, "unknown")
                                                         or budget.get("source_id") is not None):
        sev = "warning" if profile == "contract" else "error"
        issues.append(_issue("budget_basis_without_amount", "budget",
                             "amount is unknown, so basis must be 'unknown' and source_id null", sev))
    if _is_number(amount) and budget.get("basis") == "unknown":  # R02: a sum needs planned/contract/spent
        issues.append(_issue("budget_amount_without_basis", "budget.basis",
                             "an amount needs basis planned, contract or spent", policy))
    if _is_number(amount) and amount == 0 and profile != "contract":
        issues.append(_issue("budget_zero", "budget.amount_kzt",
                             "0 tenge is not a placeholder; use null when the amount is unknown"))
    if _is_number(amount) and 0 < amount < 1000:
        issues.append(_issue("budget_scale", "budget.amount_kzt",
                             "amount below 1000 KZT looks like a unit error (thousands/millions?)", "warning"))
    if obj.get("evidence_type") == "hypothesis" and obj.get("publication") == "published":
        sev = "warning" if profile == "contract" else "error"
        issues.append(_issue("hypothesis_published", "publication", "a hypothesis must not be published", sev))

    if profile == "real":
        _real_rules(obj, issues, as_of_date, ref_ids, max_status_age_days)
    elif profile == "demo":
        _demo_rules(obj, issues)
    return issues


def _real_rules(obj: dict, issues: list, as_of_date, ref_ids: dict, max_age: int) -> None:
    et = obj.get("evidence_type")
    if as_of_date is None:
        issues.append(_issue("as_of_required", "", "the real profile needs the slice as_of date for freshness checks"))
    if et == "synthetic":
        issues.append(_issue("synthetic_in_real", "evidence_type",
                             "synthetic records belong to the separate demo slice"))
        return
    if isinstance(obj.get("id"), str) and obj["id"].startswith("demo-"):
        issues.append(_issue("demo_id_in_real", "id", "demo- ids are reserved for synthetic records"))
    support = _supported_fields(obj)
    fetched = [r for r in _l(obj.get("source_refs")) if isinstance(r, dict) and r.get("access_status") == "fetched"]
    if et in ("observed", "derived") and not any(_l(r.get("fields")) for r in fetched):
        issues.append(_issue("no_fetched_source", "source_refs",
                             f"{et} records need at least one fetched source with supported fields"))
    notes = obj.get("evidence_notes")
    if et == "derived" and not (notes.strip() if isinstance(notes, str) else ""):
        issues.append(_issue("derived_without_notes", "evidence_notes", "derived records must explain the derivation"))
    for claim in material_claims(obj):
        if claim not in support:
            issues.append(_issue("unsupported_claim", claim,
                                 "value is not backed by a fetched source_ref listing this field; use null/unknown"))
    # completion must be reported, not expected: a source cannot report an actual end after its publication
    actual_end = parse_date(_d(obj.get("schedule")).get("actual_end"))
    if actual_end and "schedule.actual_end" in support:
        pubs = [parse_date(r.get("published_on")) for r in support["schedule.actual_end"]]
        pubs = [p for p in pubs if p]
        if not pubs:
            issues.append(_issue("actual_end_undated_source", "schedule.actual_end",
                                 "the source for actual_end has no published_on; cannot tell actual from expected"))
        elif max(pubs) < actual_end:
            issues.append(_issue("actual_end_after_publication", "schedule.actual_end",
                                 "source was published before this date, so it can only state an expected end"))
    status = obj.get("status")
    if status in ("planned", "in_progress") and "status" in support and as_of_date:
        pubs = [parse_date(r.get("published_on")) for r in support["status"]]
        pubs = [p for p in pubs if p]
        newest = max(pubs) if pubs else None
        if newest is None or (as_of_date - newest).days > max_age:
            issues.append(_issue("stale_status", "status",
                                 f"status '{status}' rests on a source older than {max_age} days "
                                 "(or undated); an old announcement does not prove the current state"))
    budget = _d(obj.get("budget"))
    sid = budget.get("source_id")
    if budget.get("amount_kzt") is not None:
        ref = ref_ids.get(sid) if isinstance(sid, str) else None
        if ref is None or "budget.amount_kzt" not in _l(ref.get("fields")) or ref.get("access_status") != "fetched":
            issues.append(_issue("budget_unlinked", "budget.source_id",
                                 "budget amount must name the fetched source_ref that states it"))


def _demo_rules(obj: dict, issues: list) -> None:
    if obj.get("evidence_type") != "synthetic":
        issues.append(_issue("demo_not_synthetic", "evidence_type", "demo slice records must be synthetic"))
    if not (isinstance(obj.get("id"), str) and obj["id"].startswith("demo-")):
        issues.append(_issue("demo_id_prefix", "id", "synthetic record ids must start with 'demo-'"))
    text = f"{obj.get('title') or ''} {obj.get('description') or ''}"
    if not SYNTHETIC_MARK_RE.search(text):
        issues.append(_issue("demo_unmarked", "title",
                             "title or description must visibly say the record is a demo/synthetic"))
    if obj.get("source_refs"):
        issues.append(_issue("demo_with_sources", "source_refs",
                             "synthetic records must not carry source links that look like evidence"))
    if _d(obj.get("budget")).get("amount_kzt") is not None:
        issues.append(_issue("demo_budget", "budget.amount_kzt",
                             "synthetic records carry no tenge amounts (a model budget is not money)"))
    resp = _d(obj.get("responsible"))
    if resp.get("organization") is not None or resp.get("public_contact") is not None:
        issues.append(_issue("demo_responsible", "responsible",
                             "synthetic records must not name real organizations or contacts"))


# ---------------------------------------------------------------- collection

def _norm_title(title: Any) -> str:
    return re.sub(r"\W+", " ", str(title or "").lower()).strip()


def validate_collection(items: Iterable[Any], *, profile: str = "contract", as_of: str | None = None,
                        fence: dict | None = None, max_status_age_days: int = STATUS_MAX_AGE_DAYS) -> dict:
    """Validate a list of objects; returns {valid, errors, warnings, by_object, collection_issues}."""
    items = list(items)
    by_object: dict[str, list] = {}
    collection_issues: list[dict] = []
    seen_ids: dict[str, int] = {}
    seen_titles: dict[tuple, str] = {}
    for idx, obj in enumerate(items):
        key = obj.get("id") if isinstance(obj, dict) and isinstance(obj.get("id"), str) else f"#{idx}"
        issues = validate_object(obj, profile=profile, as_of=as_of, fence=fence,
                                 max_status_age_days=max_status_age_days)
        if key in seen_ids:
            collection_issues.append(_issue("duplicate_id", f"[{idx}].id", f"id {key!r} repeats item #{seen_ids[key]}"))
            key = f"{key}#{idx}"
        else:
            seen_ids[key] = idx
        if isinstance(obj, dict):
            kind = obj.get("kind")
            tkey = (kind if isinstance(kind, str) else None, _norm_title(obj.get("title")))
            if tkey[1] and tkey in seen_titles:
                collection_issues.append(_issue("duplicate_title", f"[{idx}].title",
                                                f"same kind and title as {seen_titles[tkey]!r}; possible duplicate",
                                                "warning"))
            else:
                seen_titles[tkey] = key
        by_object[key] = issues
    errors = sum(1 for v in by_object.values() for i in v if i["severity"] == "error")
    errors += sum(1 for i in collection_issues if i["severity"] == "error")
    warnings = sum(1 for v in by_object.values() for i in v if i["severity"] == "warning")
    warnings += sum(1 for i in collection_issues if i["severity"] == "warning")
    return {
        "profile": profile,
        "as_of": as_of,
        "count": len(items),
        "valid": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "by_object": by_object,
        "collection_issues": collection_issues,
    }


def load_items(path: str) -> list:
    """Load objects from a slice envelope {items:[...]} or a bare list."""
    with open(path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data["items"]
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "schema_version" in data:
        return [data]  # a single civic object such as the contract fixture
    raise ValueError(f"{path}: expected a list, an object with 'items' or one civic object")


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Validate civic-v1 objects (R05 Astana package)")
    ap.add_argument("path", help="objects.json / demo slice / bare list")
    ap.add_argument("--profile", choices=("contract", "real", "demo"), default="contract")
    ap.add_argument("--as-of", default=None, help="slice date YYYY-MM-DD for staleness/future checks")
    ap.add_argument("--geofence", default=DEFAULT_GEOFENCE_PATH)
    ap.add_argument("--no-geofence", action="store_true")
    args = ap.parse_args(argv)
    fence = None if args.no_geofence else load_geofence(args.geofence)
    as_of = args.as_of
    max_age = STATUS_MAX_AGE_DAYS
    try:
        with open(args.path, encoding="utf-8-sig") as fh:
            envelope = json.load(fh)
        items = load_items(args.path)
    except (OSError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": f"cannot read {args.path}: {exc}"}, ensure_ascii=False))
        return 2
    if isinstance(envelope, dict) and isinstance(envelope.get("slice"), dict):
        as_of = as_of or envelope["slice"].get("as_of")  # the slice's own date unless overridden
        max_age = envelope["slice"].get("status_max_age_days", max_age)
    report = validate_collection(items, profile=args.profile, as_of=as_of, fence=fence,
                                 max_status_age_days=max_age)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
