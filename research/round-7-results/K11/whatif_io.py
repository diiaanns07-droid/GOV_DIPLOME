"""K11 round 7: isolated reference for saving / opening city-whatif-v1 scenario files (stdlib only).

Not integrated into prototypes/city-evidence. Scope is FILE I/O of the contract in
research/round-7/FEATURE_SPEC.txt: strict parsing and validation before use, canonical UTF-8
output, and opening a saved file from any directory independent of the OS code page.
Distances (before/after/delta) are NOT computed here; imported results are dropped as untrusted.

K11 decisions where the spec leaves a number open (documented, adjustable by BUILD):
  id length 1..64 characters, ids must be Unicode NFC, a UTF-8 BOM (Windows Notepad) is accepted
  and stripped (browsers' File.text() strips it too), JSON integers longer than 30 digits rejected.

CLI (ASCII-only output, safe for any console code page):
    python whatif_io.py check <file> --snapshot <id> --bbox minlon,minlat,maxlon,maxlat
    python whatif_io.py fingerprint --app-root <prototypes/city-evidence> --city shymkent|astana
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unicodedata

SCHEMA = "city-whatif-v1"
CITIES = ("shymkent", "astana")
CATEGORIES = ("school", "outpatient_clinic")
MAX_BYTES = 256 * 1024
MAX_POINTS = 10
MAX_ID_LEN = 64
MAX_INT_DIGITS = 30
TOP_KEYS = ("schema_version", "city_id", "source_snapshot", "category", "control_points", "proposed_object")
UNTRUSTED_KEYS = ("results",)  # recomputed by the app, never trusted from a file
POINT_KEYS = ("id", "lon", "lat")
PROPOSED_KEYS = ("id", "lon", "lat", "category", "kind")
FORBIDDEN_IN_TEXT = ("://", "javascript:", "data:", "<", ">", "\\")


class ScenarioError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


# ------------------------------------------------------------------ strict JSON
def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ScenarioError("E_DUPLICATE_KEY", f"повторный ключ JSON {k!r}")
        out[k] = v
    return out


def _reject_constant(name):
    raise ScenarioError("E_NONFINITE", f"значение {name} не допускается")


def _finite_float(text):
    v = float(text)
    if not math.isfinite(v):
        raise ScenarioError("E_NONFINITE", f"число {text} переполняет диапазон")
    return v


def _bounded_int(text):
    if len(text.lstrip("-")) > MAX_INT_DIGITS:
        raise ScenarioError("E_NUMBER_TOO_LONG", "слишком длинное целое число")
    return int(text)


def parse_strict(data: bytes):
    """bytes -> (object, notes). Size and encoding are checked before parsing."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("parse_strict expects bytes")
    if len(data) > MAX_BYTES:
        raise ScenarioError("E_TOO_LARGE", f"файл больше {MAX_BYTES} байт")
    notes = []
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
        notes.append("utf8_bom_stripped")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ScenarioError("E_NOT_UTF8", f"файл не в UTF-8 (байт {e.start})") from None
    try:
        obj = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant,
                         parse_float=_finite_float, parse_int=_bounded_int)
    except ScenarioError:
        raise
    except (ValueError, RecursionError) as e:
        raise ScenarioError("E_JSON", f"некорректный JSON: {e}") from None
    return obj, notes


# ------------------------------------------------------------------ contract
def _check_text_id(value, where):
    if not isinstance(value, str) or not value:
        raise ScenarioError("E_ID", f"{where}: id должен быть непустой строкой")
    if len(value) > MAX_ID_LEN:
        raise ScenarioError("E_ID", f"{where}: id длиннее {MAX_ID_LEN} символов")
    if unicodedata.normalize("NFC", value) != value:
        raise ScenarioError("E_ID_NOT_NFC", f"{where}: id не в форме Unicode NFC")
    if any(unicodedata.category(ch).startswith("C") for ch in value):
        raise ScenarioError("E_ID", f"{where}: управляющие символы в id")
    low = value.lower()
    if any(s in low for s in FORBIDDEN_IN_TEXT):
        raise ScenarioError("E_ID_FORBIDDEN", f"{where}: id содержит адрес, разметку или путь")
    return value


def _check_coord(point, where, bbox):
    for key, lo, hi in (("lon", -180.0, 180.0), ("lat", -90.0, 90.0)):
        v = point[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ScenarioError("E_COORD", f"{where}: {key} должен быть конечным числом")
        if not lo <= v <= hi:
            raise ScenarioError("E_COORD", f"{where}: {key} вне допустимого диапазона")
    lon, lat = point["lon"], point["lat"]
    if not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
        raise ScenarioError("E_OUTSIDE_BBOX", f"{where}: точка вне сохранённого квадрата выбранного города")


def _exact_keys(obj, allowed, where):
    if not isinstance(obj, dict):
        raise ScenarioError("E_SHAPE", f"{where}: ожидается объект")
    missing = [k for k in allowed if k not in obj]
    extra = [k for k in obj if k not in allowed]
    if missing:
        raise ScenarioError("E_MISSING", f"{where}: нет полей {missing}")
    if extra:
        raise ScenarioError("E_UNKNOWN_FIELD", f"{where}: неизвестные поля {extra}")


def validate(obj, *, expected_snapshot: str, bbox, expected_city: str | None = None):
    """Validate a parsed scenario. Returns (clean_scenario, notes); raises ScenarioError."""
    notes = []
    if not isinstance(obj, dict):
        raise ScenarioError("E_SHAPE", "сценарий должен быть JSON-объектом")
    obj = dict(obj)
    for k in UNTRUSTED_KEYS:
        if k in obj:
            obj.pop(k)
            notes.append(f"untrusted_{k}_dropped")
    if obj.get("schema_version") != SCHEMA:
        raise ScenarioError("E_VERSION", f"неизвестная версия схемы {obj.get('schema_version')!r}")
    if isinstance(obj.get("proposed_object"), list):
        raise ScenarioError("E_MULTIPLE_PROJECTS", "допускается не больше одного проектного объекта")
    _exact_keys(obj, TOP_KEYS, "сценарий")
    if obj["city_id"] not in CITIES:
        raise ScenarioError("E_CITY", f"неизвестный город {obj['city_id']!r}")
    if expected_city is not None and obj["city_id"] != expected_city:
        raise ScenarioError("E_CITY", "сценарий другого города: точки между городами не переносятся")
    if not isinstance(obj["source_snapshot"], str) or obj["source_snapshot"] != expected_snapshot:
        raise ScenarioError("E_SNAPSHOT", "сценарий относится к другому срезу данных")
    if obj["category"] not in CATEGORIES:
        raise ScenarioError("E_CATEGORY", f"неизвестная категория {obj['category']!r}")
    pts = obj["control_points"]
    if not isinstance(pts, list) or not 1 <= len(pts) <= MAX_POINTS:
        raise ScenarioError("E_POINTS", f"нужно от 1 до {MAX_POINTS} контрольных точек")
    seen = set()
    clean_pts = []
    for i, p in enumerate(pts):
        where = f"control_points[{i}]"
        _exact_keys(p, POINT_KEYS, where)
        pid = _check_text_id(p["id"], where)
        if pid in seen:
            raise ScenarioError("E_DUPLICATE_ID", f"{where}: повторный id")
        seen.add(pid)
        _check_coord(p, where, bbox)
        clean_pts.append({"id": pid, "lon": p["lon"], "lat": p["lat"]})
    prop = obj["proposed_object"]
    clean_prop = None
    if prop is not None:
        _exact_keys(prop, PROPOSED_KEYS, "proposed_object")
        pid = _check_text_id(prop["id"], "proposed_object")
        if pid in seen:
            raise ScenarioError("E_DUPLICATE_ID", "proposed_object: id совпадает с контрольной точкой")
        if prop["category"] != obj["category"]:
            raise ScenarioError("E_CATEGORY", "категория проекта не совпадает с выбранной категорией")
        if prop["kind"] != "hypothetical":
            raise ScenarioError("E_KIND", "проектный объект должен иметь kind=\"hypothetical\"")
        _check_coord(prop, "proposed_object", bbox)
        clean_prop = {"id": pid, "lon": prop["lon"], "lat": prop["lat"], "category": prop["category"],
                      "kind": "hypothetical"}
    clean = {"schema_version": SCHEMA, "city_id": obj["city_id"], "source_snapshot": obj["source_snapshot"],
             "category": obj["category"], "control_points": clean_pts, "proposed_object": clean_prop}
    return clean, notes


# ------------------------------------------------------------------ files
def dumps(scenario) -> bytes:
    """Canonical file bytes: UTF-8 without BOM, LF, readable Cyrillic/Kazakh, no NaN, fixed key order."""
    ordered = {k: scenario[k] for k in TOP_KEYS}
    return (json.dumps(ordered, ensure_ascii=False, allow_nan=False, indent=1) + "\n").encode("utf-8")


def save(path, scenario, *, expected_snapshot: str, bbox) -> Path:
    """Validate, then write atomically (temp file in the same directory + os.replace)."""
    clean, _ = validate(scenario, expected_snapshot=expected_snapshot, bbox=bbox)
    data = dumps(clean)
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".whatif-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path


def load(path, *, expected_snapshot: str, bbox, expected_city: str | None = None):
    """Open a scenario file as bytes (never the OS default text encoding) and validate it."""
    path = Path(path)
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise ScenarioError("E_TOO_LARGE", f"файл больше {MAX_BYTES} байт")
    obj, notes = parse_strict(path.read_bytes())
    clean, more = validate(obj, expected_snapshot=expected_snapshot, bbox=bbox, expected_city=expected_city)
    return clean, notes + more


def snapshot_fingerprint(app_root, city: str) -> str:
    """K11 FIXTURE CONVENTION (not the BUILD's API): fingerprint of the slice the scenario refers to,
    from the bytes of web/data.js plus city and distance parameters. Never derived from a file name."""
    data_js = Path(app_root) / "web" / "data.js"
    h = hashlib.sha256()
    h.update(json.dumps({"schema": SCHEMA, "city": city, "distance": "haversine", "R_m": 6371008.8,
                         "data_js_sha256": hashlib.sha256(data_js.read_bytes()).hexdigest()},
                        sort_keys=True, separators=(",", ":")).encode("ascii"))
    return "k11fx-sha256:" + h.hexdigest()


def city_bbox(app_root, city: str):
    """Read cities.<city>.bbox from web/data.js ("window.CITY_EVIDENCE = {...};")."""
    text = (Path(app_root) / "web" / "data.js").read_bytes().decode("utf-8")
    start = text.index("{")
    end = text.rindex("}")
    return json.loads(text[start:end + 1])["cities"][city]["bbox"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("file")
    c.add_argument("--snapshot", required=True)
    c.add_argument("--bbox", required=True, help="minlon,minlat,maxlon,maxlat")
    f = sub.add_parser("fingerprint")
    f.add_argument("--app-root", required=True)
    f.add_argument("--city", required=True, choices=CITIES)
    a = ap.parse_args(argv)
    if a.cmd == "fingerprint":
        print(json.dumps({"city": a.city, "source_snapshot": snapshot_fingerprint(a.app_root, a.city),
                          "bbox": city_bbox(a.app_root, a.city)}))
        return 0
    bbox = [float(x) for x in a.bbox.split(",")]
    try:
        clean, notes = load(a.file, expected_snapshot=a.snapshot, bbox=bbox)
    except ScenarioError as e:
        print(json.dumps({"ok": False, "code": e.code, "message": e.message}))  # ensure_ascii: any console
        return 2
    print(json.dumps({"ok": True, "city_id": clean["city_id"], "category": clean["category"],
                      "control_points": [p["id"] for p in clean["control_points"]],
                      "proposed": clean["proposed_object"]["id"] if clean["proposed_object"] else None,
                      "notes": notes}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
