"""R05 раунд 13: очередь проверки и путь candidate -> evidence attached -> review -> draft package (stdlib).

    python3 -I data/civic/astana/round13-verified/tools/r13.py queue [--check]
    python3 -I .../r13.py status [SLUG]
    python3 -I .../r13.py form SLUG [--source SRC_ID | --url URL --publisher NAME --publisher-kind KIND] > form.json
    python3 -I .../r13.py attach form.json --text /вне/репозитория/page.txt [--attached-at TS] [--replace]
    python3 -I .../r13.py review-form SLUG > review.json
    python3 -I .../r13.py review review.json [--text SRC_ID=/вне/репозитория/page.txt ...] [--reviewed-at TS]
    python3 -I .../r13.py build [--check]
    python3 -I .../r13.py check
    python3 -I .../r13.py geocode --street NAME [--cross NAME | --from A --to B]

Состояние цели НЕ хранится и не выводится из имени/места файла: оно каждый раз вычисляется из содержимого
evidence/ и reviews/ и их отпечатков. Значение попадает в черновик, только если
  1) человек сохранил текст страницы источника (вне Git) и каждая выдержка нашлась в нём дословно (attach);
  2) другой человек (сотрудник) проверил выдержки по странице или по тому же файлу и принял поле (review).
Заголовок/пересказ поиска доказательством не является. Импорт пакета создаёт только черновики; публикует сотрудник.
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent.parent     # .../data/civic/astana/round13-verified
ASTANA = PACKAGE_DIR.parent
REPO = ASTANA.parents[2]
HERE = Path(os.environ["R13_HOME"]).resolve() if os.environ.get("R13_HOME") else PACKAGE_DIR
R12_PATH = ASTANA / "round12-verified" / "tools" / "r12.py"
DISTRICTS_PATH = REPO / "data" / "astana_districts.geojson"


def _load_r12():
    """Инструмент раунда 12 — источник общих правил сверки выдержек, дат, сумм и геокодера (не копируется)."""
    spec = importlib.util.spec_from_file_location("r05_r12_tool", R12_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


r12 = _load_r12()
norm_text, quote_found, page_text = r12.norm_text, r12.quote_found, r12.page_text
date_in_quote, amount_in_quote, parse_date = r12.date_in_quote, r12.amount_in_quote, r12.parse_date
dump_json, Issues = r12.dump_json, r12.Issues

KINDS = ("construction", "roadworks", "landscaping", "event")
CLAIM_FIELDS = ("what", "location.text", "status", "schedule.planned_start", "schedule.original_planned_end",
                "schedule.current_planned_end", "schedule.actual_end", "budget.amount_kzt", "budget.basis",
                "responsible.organization")
CIVIC_CLAIM_FIELDS = tuple(f for f in CLAIM_FIELDS if f not in ("what", "location.text"))
CLAIM_TYPES = ("stated", "expected", "reported_actual")
STATUSES = ("planned", "in_progress", "completed", "cancelled")
WHEN_FIELDS = ("schedule.planned_start", "schedule.current_planned_end", "schedule.original_planned_end",
               "schedule.actual_end")
ORIGINS_OK = ("human_saved_page_text", "agent_http")
# Явно отвергаемые «происхождения»: выдача поиска, сам URL, имя файла — не текст источника.
ORIGINS_REFUSED = ("search_title", "search_summary", "search_snippet", "url", "file_name", "none")
PUBLISHER_KINDS = r12.PUBLISHER_KINDS
GEOMETRY_LEVELS = ("street_segment", "intersection", "whole_street", "manual", "none")
OSM_LEVELS = ("street_segment", "intersection", "whole_street")
REVIEW_METHODS = ("url_opened_by_reviewer", "saved_text_rechecked")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}\Z")
SOURCE_ID_RE = re.compile(r"^src-r1[23]-[a-z0-9-]{3,48}\Z")
TS_RE = r12.TS_RE
SHA_RE = r12.SHA_RE
CITY_RE = re.compile(r"астан|astana|нур-султан|нұр-сұлтан|nur-sultan")
MAX_QUOTE = r12.MAX_QUOTE
MIN_QUOTE_WORDS = r12.MIN_QUOTE_WORDS
SNAPSHOT_WIDTH = 120
MAX_SNAPSHOT_CHARS = 8000
MAX_TEXT_BYTES = 20 * 1024 * 1024

EVIDENCE_SCHEMA = "r05-r13-evidence-v1"
EVIDENCE_FORM = "r05-r13-evidence-form-v1"
REVIEW_SCHEMA = "r05-r13-review-v1"
REVIEW_FORM = "r05-r13-review-form-v1"
ANALYSIS_SCHEMA = "r05-r13-queue-analysis-v1"
QUEUE_SCHEMA = "r05-r13-verify-queue-v1"
SUMMARY_SCHEMA = "r05-r13-summary-v1"

EVIDENCE_KEYS = frozenset({"schema", "target", "source", "capture", "page", "claims", "snapshot", "not_stated", "notes"})
SOURCE_KEYS = frozenset({"id", "url", "publisher", "publisher_kind", "registered"})
CAPTURE_KEYS = frozenset({"origin", "attached_by", "attached_at", "retrieved_at", "content_sha256", "text_chars",
                          "storage"})
PAGE_KEYS = frozenset({"title_quote", "published_on", "published_quote", "city_quote"})
CLAIM_KEYS = frozenset({"field", "value", "quote", "claim_type", "value_basis", "locator"})
REVIEW_KEYS = frozenset({"schema", "target", "evidence_digest", "reviewer", "reviewed_at", "method", "decision",
                         "reason", "kind", "title", "description", "claims", "geometry", "text_rechecked"})
GEOMETRY_KEYS = frozenset({"level", "osm_query", "manual_geojson", "basis", "reason", "geometry_sha256"})


# ---------------------------------------------------------------- io
def load_json(path: Path, default: Any = None) -> Any:
    return r12.load_json(path, default)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_json(value), encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha(value: Any) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def config() -> dict:
    return load_json(HERE / "config.json", {}) or {}


def _rel(path_text: str | None) -> Path | None:
    if not path_text:
        return None
    p = Path(path_text)
    return p if p.is_absolute() else (HERE / p).resolve()


def registry() -> dict:
    """Реестр источников раунда 12 (только чтение): id -> запись."""
    path = _rel(config().get("base_sources"))
    reg = load_json(path, {}) if path else {}
    return {s["id"]: s for s in (reg or {}).get("sources") or [] if isinstance(s, dict) and "id" in s}


def candidates() -> dict:
    path = _rel(config().get("base_candidates"))
    doc = load_json(path, {}) if path else {}
    return {c["id"]: c for c in (doc or {}).get("candidates") or [] if isinstance(c, dict) and "id" in c}


def analysis() -> dict:
    return load_json(HERE / "analysis" / "queue_analysis.json", {}) or {}


def targets() -> dict:
    return {t["slug"]: t for t in analysis().get("targets") or [] if isinstance(t, dict) and isinstance(t.get("slug"), str)}


def record_id(target: dict) -> str:
    return f"ast-r05-{target['kind']}-{target['slug']}"


def new_source_id(url: str) -> str:
    return "src-r13-" + sha256_bytes(norm_url(url).encode())[:12]


def norm_url(url: str) -> str:
    return url.strip()


def as_of() -> _dt.date | None:
    return parse_date(config().get("as_of"))


def now_ts() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def astana_date(ts: str) -> _dt.date:
    return r12._astana_date(ts)


def pii_finder():
    validator = r12.base_validator()
    return getattr(validator, "find_pii", None) if validator else None


# ---------------------------------------------------------------- text helpers
def norm_keep_case(value: str) -> str:
    """Как r12.norm_text, но без смены регистра — для читаемого контекста в snapshot."""
    import unicodedata
    text = unicodedata.normalize("NFKC", value).replace("­", "")
    for a, b in (("«", '"'), ("»", '"'), ("“", '"'), ("”", '"'), ("„", '"'), ("‘", "'"), ("’", "'"),
                 ("–", "-"), ("—", "-"), ("−", "-"), ("‑", "-"), ("ё", "е"), ("Ё", "Е")):
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip()


def context_of(quote: str, text_keep: str) -> str | None:
    match = re.search(re.escape(norm_keep_case(quote)), text_keep, re.IGNORECASE)
    if not match:
        return None
    a, b = max(0, match.start() - SNAPSHOT_WIDTH), min(len(text_keep), match.end() + SNAPSHOT_WIDTH)
    return ("…" if a else "") + text_keep[a:b] + ("…" if b < len(text_keep) else "")


def quotes_of(ev: dict) -> list[tuple[str, str]]:
    """(ссылка, выдержка) всех выдержек доказательства: заголовок, дата, город, утверждения."""
    page = ev.get("page") or {}
    out = [(f"page.{k}", page.get(k)) for k in ("title_quote", "published_quote", "city_quote")]
    out += [(f"claims[{i}]", c.get("quote")) for i, c in enumerate(ev.get("claims") or []) if isinstance(c, dict)]
    return [(ref, q) for ref, q in out if isinstance(q, str)]


def _text_ok(value: Any, where: str, issues: Issues, *, required: bool, max_len: int, pii=None) -> None:
    if value is None or value == "":
        if required:
            issues.add(where, "required", "обязательное поле")
        return
    if not isinstance(value, str):
        issues.add(where, "type", "строка")
        return
    if len(value) > max_len:
        issues.add(where, "too_long", f"не длиннее {max_len} символов")
    if r12.HTML_TAG_RE.search(value):
        issues.add(where, "html", "только простой текст")
    if pii is not None and pii(value):
        issues.add(where, "pii", "похоже на телефон/ИИН/e-mail: персональные данные не хранятся")


# ---------------------------------------------------------------- analysis / queue
def check_analysis(doc: dict, issues: Issues) -> dict:
    if doc.get("schema") != ANALYSIS_SCHEMA:
        issues.add("analysis", "schema", f"ожидается {ANALYSIS_SCHEMA}")
    cands, reg = candidates(), registry()
    out = {}
    for i, t in enumerate(doc.get("targets") or []):
        where = f"analysis.targets[{i}]"
        if not isinstance(t, dict):
            issues.add(where, "type", "объект")
            continue
        slug = t.get("slug")
        if not isinstance(slug, str) or not SLUG_RE.match(slug):
            issues.add(where + ".slug", "slug", "a-z0-9-, 3..40 символов")
            continue
        if slug in out:
            issues.add(where + ".slug", "dup_slug", f"slug {slug} повторяется")
        if t.get("kind") not in KINDS:
            issues.add(where + ".kind", "enum", "kind civic-v1")
        for cid in t.get("candidate_ids") or []:
            if cid not in cands:
                issues.add(where + ".candidate_ids", "unknown_candidate", f"{cid} нет в candidates.json раунда 12")
        for sid in t.get("source_ids") or []:
            if sid not in reg:
                issues.add(where + ".source_ids", "unknown_source", f"{sid} нет в реестре источников")
        if t.get("geometry_level") not in GEOMETRY_LEVELS:
            issues.add(where + ".geometry_level", "enum", "|".join(GEOMETRY_LEVELS))
        q = t.get("osm_query")
        if q is not None and (not isinstance(q, dict) or not isinstance(q.get("street"), str)):
            issues.add(where + ".osm_query", "type", "{street, cross?, from?, to?} или null")
        out[slug] = t
    return out


_OSM = None


def osm():
    global _OSM
    if _OSM is None:
        path = REPO / (config().get("osm_snapshot") or "data/civic/astana/osm-walking/overpass.json.gz")
        _OSM = r12.Osm(path)
    return _OSM


def run_geocode(query: dict) -> dict:
    snap = (config().get("osm_snapshot_at") or "2026-05-06")[:10]
    return r12.geocode(osm(), query["street"], query.get("cross"), query.get("from"), query.get("to"), snapshot=snap)


_DISTRICTS = None


def districts() -> list:
    global _DISTRICTS
    if _DISTRICTS is None:
        doc = load_json(DISTRICTS_PATH, {}) or {}
        _DISTRICTS = [(f["properties"].get("name"), f["geometry"]) for f in doc.get("features") or []]
    return _DISTRICTS


def _in_ring(lon: float, lat: float, ring: list) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / ((y2 - y1) or 1e-12) + x1:
            inside = not inside
    return inside


def district_of(geometry: dict | None) -> str | None:
    """Район по OSM-границам (data/astana_districts.geojson, не официальное описание) для средней точки."""
    if not geometry:
        return None
    coords = geometry.get("coordinates")
    if geometry.get("type") == "Point":
        point = coords
    elif geometry.get("type") == "LineString" and coords:
        point = coords[len(coords) // 2]
    else:
        return None
    lon, lat = point
    for name, geom in districts():
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            if _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, hole) for hole in poly[1:]):
                return name
    return None


# ---------------------------------------------------------------- evidence
def evidence_dir(slug: str) -> Path:
    return HERE / "evidence" / slug


def evidence_files(slug: str) -> list[Path]:
    folder = evidence_dir(slug)
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


def evidence_digest(slug: str) -> str | None:
    files = evidence_files(slug)
    if not files:
        return None
    return canonical_sha([[p.name, sha256_bytes(p.read_bytes())] for p in files])


def _claim_problems(c: dict, where: str, issues: Issues, published: _dt.date | None, pii) -> None:
    field, value, ctype, quote, basis = c.get("field"), c.get("value"), c.get("claim_type"), c.get("quote"), c.get("value_basis")
    if set(c) - CLAIM_KEYS:
        issues.add(where, "unknown_keys", "лишние поля утверждения: " + ", ".join(sorted(set(c) - CLAIM_KEYS)))
    if field not in CLAIM_FIELDS:
        issues.add(where + ".field", "enum", "|".join(CLAIM_FIELDS))
        return
    if ctype not in CLAIM_TYPES:
        issues.add(where + ".claim_type", "enum", "|".join(CLAIM_TYPES))
    if not isinstance(quote, str) or not quote.strip() or len(quote) > MAX_QUOTE:
        issues.add(where + ".quote", "quote", f"дословная выдержка 1–{MAX_QUOTE} символов")
        quote = ""
    elif len(norm_text(quote).split()) < MIN_QUOTE_WORDS:
        issues.add(where + ".quote", "quote_short", f"выдержка не короче {MIN_QUOTE_WORDS} слов")
    _text_ok(basis, where + ".value_basis", issues, required=False, max_len=300, pii=pii)
    _text_ok(c.get("locator"), where + ".locator", issues, required=False, max_len=200, pii=pii)
    if field.startswith("schedule."):
        if parse_date(value) is None:
            issues.add(where + ".value", "date", "YYYY-MM-DD")
        elif quote and not basis and not date_in_quote(value, quote):
            issues.add(where + ".quote", "value_not_in_quote",
                       "дата значения должна быть в выдержке; перевод формулировки («до конца года») — в value_basis")
        if field == "schedule.actual_end":
            if ctype != "reported_actual":
                issues.add(where + ".claim_type", "actual_type", "actual_end — только reported_actual (обещание ≠ факт)")
            if parse_date(value) and (published is None or parse_date(value) > published):
                issues.add(where + ".value", "actual_after_publication",
                           "фактическое окончание не может быть позже публикации источника")
        elif ctype == "reported_actual" and field != "schedule.planned_start":
            issues.add(where + ".claim_type", "planned_as_actual", "плановая дата — stated/expected, не reported_actual")
    elif field == "status":
        if value not in STATUSES:
            issues.add(where + ".value", "enum", "|".join(STATUSES) + " (неизвестный статус — не утверждение)")
        elif value == "planned" and ctype == "reported_actual":
            issues.add(where + ".claim_type", "status_type", "planned — план, не фактическое сообщение")
        elif value in ("in_progress", "completed", "cancelled") and ctype != "reported_actual":
            issues.add(where + ".claim_type", "status_type", f"{value} требует reported_actual (обещание ≠ факт)")
    elif field == "budget.amount_kzt":
        if not (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0):
            issues.add(where + ".value", "amount", "сумма в тенге > 0 (неизвестное — не утверждение, не ноль)")
        elif quote and not basis and not amount_in_quote(value, quote):
            issues.add(where + ".quote", "value_not_in_quote", "сумма цифрами должна быть в выдержке (иначе value_basis)")
    elif field == "budget.basis":
        if value not in ("planned", "contract", "spent"):
            issues.add(where + ".value", "enum", "planned | contract | spent")
    else:
        _text_ok(value, where + ".value", issues, required=True, max_len=300, pii=pii)


def check_evidence(ev: Any, path: Path, slug: str, tgts: dict, reg: dict, issues: Issues, pii=None) -> None:
    """Проверка сохранённого доказательства без полного текста (текст в Git не хранится)."""
    cfg = config()
    here = f"evidence/{slug}/{path.name}"
    if not isinstance(ev, dict):
        issues.add(here, "type", "JSON-объект")
        return
    if set(ev) - EVIDENCE_KEYS:
        issues.add(here, "unknown_keys", "лишние поля: " + ", ".join(sorted(set(ev) - EVIDENCE_KEYS)))
    if ev.get("schema") != EVIDENCE_SCHEMA:
        issues.add(here, "schema", f"ожидается {EVIDENCE_SCHEMA}")
    if ev.get("target") != slug or slug not in tgts:
        issues.add(here + ".target", "target", "target совпадает с папкой и есть в очереди")
    src = ev.get("source") if isinstance(ev.get("source"), dict) else {}
    cap = ev.get("capture") if isinstance(ev.get("capture"), dict) else {}
    page = ev.get("page") if isinstance(ev.get("page"), dict) else {}
    claims = ev.get("claims") if isinstance(ev.get("claims"), list) else []
    for name, block, keys in (("source", src, SOURCE_KEYS), ("capture", cap, CAPTURE_KEYS), ("page", page, PAGE_KEYS)):
        if not block:
            issues.add(here + "." + name, "required", "обязательный блок")
        elif set(block) - keys:
            issues.add(here + "." + name, "unknown_keys", "лишние поля: " + ", ".join(sorted(set(block) - keys)))
    sid, url = src.get("id"), src.get("url")
    if path.stem != sid:
        issues.add(here, "file_name", "имя файла — <source.id>.json")
    if not isinstance(url, str) or not url.startswith("https://") or len(url) > 500:
        issues.add(here + ".source.url", "url", "https://… не длиннее 500 символов")
    elif sid in reg:
        if reg[sid].get("url") != url:
            issues.add(here + ".source.url", "url_mismatch", f"URL не совпадает с реестром для {sid}")
        if src.get("registered") is not True:
            issues.add(here + ".source.registered", "registered", "источник из реестра: registered=true")
    elif not isinstance(sid, str) or sid != new_source_id(url):
        issues.add(here + ".source.id", "source_id", "новый источник: id = src-r13-<sha256(url)[:12]> (r13.py form --url)")
    elif src.get("registered") is not False:
        issues.add(here + ".source.registered", "registered", "нового источника нет в реестре: registered=false")
    if src.get("publisher_kind") not in PUBLISHER_KINDS:
        issues.add(here + ".source.publisher_kind", "enum", "|".join(PUBLISHER_KINDS))
    _text_ok(src.get("publisher"), here + ".source.publisher", issues, required=True, max_len=200, pii=pii)

    origin = cap.get("origin")
    if origin in ORIGINS_REFUSED:
        issues.add(here + ".capture.origin", "snippet_not_evidence",
                   f"{origin}: заголовок/пересказ поиска, URL или имя файла не являются текстом источника")
    elif origin not in ORIGINS_OK:
        issues.add(here + ".capture.origin", "enum", "|".join(ORIGINS_OK))
    _text_ok(cap.get("attached_by"), here + ".capture.attached_by", issues, required=True, max_len=80, pii=pii)
    for key in ("attached_at", "retrieved_at"):
        if not isinstance(cap.get(key), str) or not TS_RE.match(cap[key]):
            issues.add(here + f".capture.{key}", "timestamp", "YYYY-MM-DDThh:mm:ssZ (UTC)")
    if not isinstance(cap.get("content_sha256"), str) or not SHA_RE.match(cap["content_sha256"]):
        issues.add(here + ".capture.content_sha256", "sha256", "sha256 сохранённого текста страницы")
    min_chars = int(cfg.get("min_page_chars", 400))
    if not isinstance(cap.get("text_chars"), int) or cap["text_chars"] < min_chars:
        issues.add(here + ".capture.text_chars", "too_short",
                   f"текст страницы короче {min_chars} символов: это выдержка/сниппет, а не страница")
    if cap.get("storage") != "outside_repo":
        issues.add(here + ".capture.storage", "storage", "текст страницы хранится вне Git: outside_repo")
    retrieved = astana_date(cap["retrieved_at"]) if TS_RE.match(str(cap.get("retrieved_at"))) else None
    attached = astana_date(cap["attached_at"]) if TS_RE.match(str(cap.get("attached_at"))) else None
    if retrieved and attached and cap["retrieved_at"] > cap["attached_at"]:
        issues.add(here + ".capture.retrieved_at", "order", "страница получена позже, чем прикреплена")
    if retrieved and as_of() and retrieved > as_of() + _dt.timedelta(days=1):
        issues.add(here + ".capture.retrieved_at", "after_as_of",
                   f"получено ({retrieved}) позже среза as_of={as_of()}: обновите as_of в config.json")

    published = parse_date(page.get("published_on"))
    if published is None:
        issues.add(here + ".page.published_on", "date", "дата публикации на самой странице, YYYY-MM-DD")
    for key in ("title_quote", "published_quote", "city_quote"):
        q = page.get(key)
        if not isinstance(q, str) or not q.strip() or len(q) > MAX_QUOTE:
            issues.add(here + f".page.{key}", "quote", f"дословная выдержка 1–{MAX_QUOTE} символов")
    if isinstance(page.get("title_quote"), str) and len(norm_text(page["title_quote"]).split()) < MIN_QUOTE_WORDS:
        issues.add(here + ".page.title_quote", "quote_short", "заголовок статьи целиком (не короче 3 слов)")
    if published and isinstance(page.get("published_quote"), str) and not date_in_quote(page["published_on"], page["published_quote"]):
        issues.add(here + ".page.published_quote", "value_not_in_quote", "выдержка должна содержать дату публикации")
    if isinstance(page.get("city_quote"), str) and not CITY_RE.search(norm_text(page["city_quote"])):
        issues.add(here + ".page.city_quote", "city", "выдержка должна называть город (Астана)")
    if published and retrieved and retrieved < published:
        issues.add(here + ".page.published_on", "order", f"получено ({retrieved}) раньше публикации ({published})")

    if not claims or not all(isinstance(c, dict) for c in claims):
        issues.add(here + ".claims", "required", "утверждения с выдержками")
        claims = [c for c in claims if isinstance(c, dict)]
    seen = set()
    for i, c in enumerate(claims):
        _claim_problems(c, f"{here}.claims[{i}]", issues, published, pii)
        if c.get("field") in seen:
            issues.add(f"{here}.claims[{i}].field", "dup_field", "одно поле — одно утверждение в источнике")
        seen.add(c.get("field"))
    fields = {c.get("field") for c in claims}
    for need in ("what", "location.text"):
        if need not in fields:
            issues.add(here + ".claims", "missing_" + need.replace(".", "_"), f"обязательна выдержка для {need}")
    kind = (tgts.get(slug) or {}).get("kind")
    if kind in ("roadworks", "event") and not fields & {"schedule.planned_start", "schedule.current_planned_end"}:
        issues.add(here + ".claims", "missing_when", "для перекрытия/события обязательна дата начала или окончания")
    elif not fields & (set(WHEN_FIELDS) | {"status"}):
        issues.add(here + ".claims", "missing_when", "нужна хотя бы одна дата или статус из источника")
    if "budget.amount_kzt" in fields and "budget.basis" not in fields:
        issues.add(here + ".claims", "budget_basis", "сумма без основания (planned/contract/spent) не принимается")
    for item in ev.get("not_stated") or []:
        if item not in CIVIC_CLAIM_FIELDS:
            issues.add(here + ".not_stated", "enum", "поля civic из списка")
    _text_ok(ev.get("notes"), here + ".notes", issues, required=False, max_len=1500, pii=pii)

    snapshot = ev.get("snapshot")
    if not isinstance(snapshot, list):
        issues.add(here + ".snapshot", "required", "минимальный текстовый snapshot (контекст выдержек)")
        return
    by_ref = {s.get("ref"): s.get("context") for s in snapshot if isinstance(s, dict)}
    total = sum(len(s or "") for s in by_ref.values() if isinstance(s, str))
    if total > MAX_SNAPSHOT_CHARS:
        issues.add(here + ".snapshot", "too_long", f"snapshot не больше {MAX_SNAPSHOT_CHARS} символов")
    for ref, quote in quotes_of(ev):
        ctx = by_ref.get(ref)
        if not isinstance(ctx, str) or norm_text(quote) not in norm_text(ctx):
            issues.add(f"{here}.snapshot", "snapshot_mismatch", f"{ref}: выдержки нет в сохранённом контексте")
        elif pii is not None and pii(ctx):
            issues.add(f"{here}.snapshot", "pii", f"{ref}: в контексте похоже на персональные данные — сократите выдержку")


def verify_against_text(ev: dict, raw: bytes) -> list[dict]:
    """Каждая выдержка дословно (целыми словами) есть в тексте страницы; текст тот же, что при attach."""
    problems = []
    sha = sha256_bytes(raw)
    cap = ev.get("capture") or {}
    if cap.get("content_sha256") and cap["content_sha256"] != sha:
        problems.append({"problem": "sha256 файла не совпадает с прикреплённым текстом", "expected": cap["content_sha256"], "got": sha})
    text_norm = norm_text(page_text(raw.decode("utf-8", "replace")))
    for ref, quote in quotes_of(ev):
        if not quote_found(quote, text_norm):
            problems.append({"ref": ref, "problem": "выдержка не найдена дословно в тексте страницы", "quote": quote})
    if not CITY_RE.search(text_norm):
        problems.append({"problem": "в тексте страницы не названа Астана"})
    return problems


# ---------------------------------------------------------------- review
def claim_key(ev: dict, c: dict) -> str:
    return f"{(ev.get('source') or {}).get('id')}:{c.get('field')}"


def check_review(rv: Any, slug: str, evs: list[dict], tgts: dict, issues: Issues, pii=None) -> None:
    here = f"reviews/{slug}.json"
    if not isinstance(rv, dict):
        issues.add(here, "type", "JSON-объект")
        return
    if set(rv) - REVIEW_KEYS:
        issues.add(here, "unknown_keys", "лишние поля: " + ", ".join(sorted(set(rv) - REVIEW_KEYS)))
    if rv.get("schema") != REVIEW_SCHEMA:
        issues.add(here, "schema", f"ожидается {REVIEW_SCHEMA}")
    if rv.get("target") != slug:
        issues.add(here + ".target", "target", "target совпадает с именем файла")
    _text_ok(rv.get("reviewer"), here + ".reviewer", issues, required=True, max_len=80, pii=pii)
    attachers = {norm_text((e.get("capture") or {}).get("attached_by") or "") for e in evs}
    if isinstance(rv.get("reviewer"), str) and norm_text(rv["reviewer"]) in attachers:
        issues.add(here + ".reviewer", "same_person", "проверяет другой человек, не тот, кто прикрепил выдержки")
    if not isinstance(rv.get("reviewed_at"), str) or not TS_RE.match(rv["reviewed_at"]):
        issues.add(here + ".reviewed_at", "timestamp", "YYYY-MM-DDThh:mm:ssZ (UTC)")
    else:
        for e in evs:
            at = (e.get("capture") or {}).get("attached_at")
            if isinstance(at, str) and rv["reviewed_at"] < at:
                issues.add(here + ".reviewed_at", "order", "проверка раньше прикрепления доказательства")
    if rv.get("method") not in REVIEW_METHODS:
        issues.add(here + ".method", "enum", "|".join(REVIEW_METHODS))
    if rv.get("method") == "saved_text_rechecked" and rv.get("text_rechecked") is not True:
        issues.add(here + ".text_rechecked", "required", "saved_text_rechecked требует сверки файла (review --text)")
    if rv.get("decision") not in ("accept", "reject"):
        issues.add(here + ".decision", "enum", "accept | reject")
    _text_ok(rv.get("reason"), here + ".reason", issues, required=rv.get("decision") == "reject", max_len=500, pii=pii)
    decisions = rv.get("claims") if isinstance(rv.get("claims"), dict) else {}
    keys = {claim_key(e, c) for e in evs for c in e.get("claims") or [] if isinstance(c, dict)}
    for k in sorted(keys - set(decisions)):
        issues.add(here + ".claims", "undecided", f"нет решения по {k}")
    for k in sorted(set(decisions) - keys):
        issues.add(here + ".claims", "unknown_claim", f"{k}: такого утверждения нет в доказательствах")
    for k, d in decisions.items():
        if not isinstance(d, str) or not (d == "accept" or (d.startswith("reject:") and len(d.strip()) > 8)):
            issues.add(here + f".claims.{k}", "decision", "accept | reject: <причина>")
    if rv.get("decision") != "accept":
        return
    accepted = [k for k, d in decisions.items() if d == "accept" and k in keys]
    fields = [k.split(":", 1)[1] for k in accepted]
    for f in sorted({f for f in fields if fields.count(f) > 1}):
        issues.add(here + ".claims", "conflict", f"{f}: принято несколько источников — выберите одно значение, "
                                                 "противоречие опишите в description")
    for need in ("what", "location.text"):
        if need not in fields:
            issues.add(here + ".claims", "missing_" + need.replace(".", "_"), f"принятие требует принятого {need}")
    kind = rv.get("kind")
    if kind not in KINDS or kind != (tgts.get(slug) or {}).get("kind"):
        issues.add(here + ".kind", "kind", "kind из очереди")
    if kind in ("roadworks", "event") and not set(fields) & {"schedule.planned_start", "schedule.current_planned_end"}:
        issues.add(here + ".claims", "missing_when", "перекрытие/событие без принятой даты не принимается")
    elif not set(fields) & (set(WHEN_FIELDS) | {"status"}):
        issues.add(here + ".claims", "missing_when", "нужна принятая дата или статус")
    accepted_fields = set(fields)
    if "budget.amount_kzt" in accepted_fields:
        by = {k.split(":", 1)[1]: k.split(":", 1)[0] for k in accepted}
        if by.get("budget.basis") != by.get("budget.amount_kzt"):
            issues.add(here + ".claims", "budget_basis", "сумма принимается только с основанием из того же источника")
    _text_ok(rv.get("title"), here + ".title", issues, required=True, max_len=200, pii=pii)
    _text_ok(rv.get("description"), here + ".description", issues, required=True, max_len=2000, pii=pii)
    geo = rv.get("geometry") if isinstance(rv.get("geometry"), dict) else None
    if geo is None:
        issues.add(here + ".geometry", "required", "решение по геометрии (level none — запись непубликуема)")
        return
    if set(geo) - GEOMETRY_KEYS:
        issues.add(here + ".geometry", "unknown_keys", "лишние поля геометрии")
    level = geo.get("level")
    if level not in GEOMETRY_LEVELS:
        issues.add(here + ".geometry.level", "enum", "|".join(GEOMETRY_LEVELS))
    if level in OSM_LEVELS and not isinstance(geo.get("osm_query"), dict):
        issues.add(here + ".geometry.osm_query", "required", "запрос к OSM-снимку {street, cross | from+to}")
    if level == "whole_street":
        _text_ok(geo.get("reason"), here + ".geometry.reason", issues, required=True, max_len=300, pii=pii)
    if level == "manual":
        _text_ok(geo.get("basis"), here + ".geometry.basis", issues, required=True, max_len=400, pii=pii)
        g = geo.get("manual_geojson")
        if not (isinstance(g, dict) and g.get("type") in ("Point", "LineString")):
            issues.add(here + ".geometry.manual_geojson", "geometry", "Point или LineString в WGS84")
    if level != "none" and not (isinstance(geo.get("geometry_sha256"), str) and SHA_RE.match(geo["geometry_sha256"])):
        issues.add(here + ".geometry.geometry_sha256", "sha256", "отпечаток геометрии ставит команда review")


def geometry_from_review(geo: dict) -> tuple[dict | None, str | None, list[str]]:
    """(geometry, basis, problems). Геометрия OSM пересчитывается из запроса — координаты руками не вносятся."""
    level = geo.get("level")
    if level in OSM_LEVELS:
        q = geo.get("osm_query") or {}
        if level == "intersection" and not q.get("cross"):
            return None, None, ["intersection требует cross"]
        if level == "street_segment" and not (q.get("from") and q.get("to")):
            return None, None, ["street_segment требует from и to"]
        if level == "whole_street" and (q.get("cross") or q.get("from") or q.get("to")):
            return None, None, ["whole_street — без cross/from/to"]
        res = run_geocode(q)
        if res.get("ambiguous") or res.get("geometry") is None:
            return None, None, ["OSM-снимок не дал однозначной геометрии: " + "; ".join(res.get("notes") or [])]
        basis = res.get("geometry_basis")
        if level == "whole_street":
            basis = f"{basis}; вся улица как приблизительная привязка: {geo.get('reason')}"
        return res["geometry"], basis, []
    if level == "manual":
        g = geo.get("manual_geojson")
        problems = []
        pts = [g.get("coordinates")] if g.get("type") == "Point" else (g.get("coordinates") or [])
        box = config().get("city_bbox") or [71.2079, 50.9206, 71.7953, 51.3612]
        for p in pts:
            if not (isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p)
                    and box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]):
                problems.append("координаты вне Астаны или не [lon, lat]")
                break
        if g.get("type") == "LineString" and len(pts) < 2:
            problems.append("LineString из двух и более точек")
        return (None, None, problems) if problems else (g, f"вручную сотрудником: {geo.get('basis')}", [])
    return None, None, []


# ---------------------------------------------------------------- state
def target_state(slug: str, tgts: dict | None = None, reg: dict | None = None) -> dict:
    tgts = targets() if tgts is None else tgts
    reg = registry() if reg is None else reg
    pii = pii_finder()
    files = evidence_files(slug)
    if not files:
        return {"state": "candidate", "detail": "доказательств нет"}
    evs, issues = [], Issues()
    for path in files:
        ev = r12.read_json(path, issues)
        check_evidence(ev, path, slug, tgts, reg, issues, pii)
        if isinstance(ev, dict):
            evs.append(ev)
    if issues.errors:
        return {"state": "evidence_invalid", "detail": issues.errors[:20]}
    rpath = HERE / "reviews" / f"{slug}.json"
    if not rpath.exists():
        return {"state": "evidence_attached", "detail": f"{len(evs)} источник(а) с выдержками; ждёт проверки сотрудником"}
    rv = r12.read_json(rpath, issues)
    if isinstance(rv, dict) and rv.get("evidence_digest") != evidence_digest(slug):
        return {"state": "review_stale", "detail": "доказательства изменены после проверки: нужна новая проверка"}
    check_review(rv, slug, evs, tgts, issues, pii)
    if issues.errors:
        return {"state": "review_invalid", "detail": issues.errors[:20]}
    if rv["decision"] == "reject":
        return {"state": "rejected", "detail": rv.get("reason")}
    geo = rv["geometry"]
    if geo.get("level") == "none":
        return {"state": "reviewed_no_geometry", "detail": "принято, но без пригодной геометрии: не публикуется"}
    geometry, basis, problems = geometry_from_review(geo)
    if problems:
        return {"state": "reviewed_no_geometry", "detail": problems}
    if canonical_sha(geometry) != geo.get("geometry_sha256"):
        return {"state": "review_stale", "detail": "геометрия по OSM-снимку изменилась после проверки"}
    return {"state": "draft_ready", "detail": "войдёт в пакет черновиков", "evidence": evs, "review": rv,
            "geometry": geometry, "geometry_basis": basis}


# ---------------------------------------------------------------- civic-v1
def to_item(slug: str, st: dict, tgts: dict) -> tuple[dict, dict]:
    """Запись civic-v1 (через r12.to_civic) и служебные сведения об актуальности."""
    cfg = config()
    target, rv, evs = tgts[slug], st["review"], st["evidence"]
    decisions = rv["claims"]
    sources, claims, used_sources = {}, [], set()
    for ev in evs:
        src, cap, page = ev["source"], ev["capture"], ev["page"]
        for c in ev["claims"]:
            if decisions.get(claim_key(ev, c)) != "accept":
                continue
            used_sources.add(src["id"])
            claims.append({**c, "source_id": src["id"], "published_on": page["published_on"]})
        sources[src["id"]] = {"url": src["url"], "publisher": src.get("publisher"), "published_on": page["published_on"],
                              "retrieved_at": cap["retrieved_at"], "access_status": "fetched",
                              "license": None}
    by_field = {c["field"]: c for c in claims}
    notes, actuality = [], {}
    day = as_of()
    status = by_field.get("status")
    max_age = int(cfg.get("status_max_age_days", 45))
    if status and status["value"] in ("planned", "in_progress"):
        pub = parse_date(status["published_on"])
        if pub is None or (day - pub).days > max_age:
            notes.append(f"Статус «{status['value']}» сообщён {status['published_on']}; на {day.isoformat()} "
                         f"актуальность неизвестна (сообщение старше {max_age} дней), поэтому статус — unknown.")
            del by_field["status"]
            actuality["status_dropped_as_stale"] = status["published_on"]
    civic_claims = [c for f, c in sorted(by_field.items()) if f in CIVIC_CLAIM_FIELDS]
    where = by_field["location.text"]["value"]
    what = by_field["what"]["value"]
    not_stated = sorted({f for ev in evs for f in ev.get("not_stated") or []} - set(by_field))
    level = rv["geometry"]["level"]
    evidence_notes = f"Что: {what}. Где (по источнику): {where}. Проверено сотрудником ({rv['method']})."
    basis = f"{st['geometry_basis']} (уровень {level}; приблизительная привязка, требует сверки на месте)"
    record = {
        "id": record_id(target), "kind": target["kind"], "title": rv["title"], "description": rv["description"],
        "location": {"text": where, "geometry": st["geometry"], "geometry_precision": "approximate",
                     "geometry_basis": basis},
        "claims": [{"field": c["field"], "value": c["value"], "claim_type": c["claim_type"], "source_id": c["source_id"],
                    "quote": c["quote"], "value_basis": c.get("value_basis")} for c in civic_claims],
        "not_confirmed": [f for f in not_stated if f in CIVIC_CLAIM_FIELDS],
        "evidence_notes": " ".join([evidence_notes] + notes),
    }
    item = r12.to_civic(record, {k: v for k, v in sources.items() if k in used_sources}, cfg.get("as_of"))
    ends = [parse_date(by_field[f]["value"]) for f in ("schedule.actual_end", "schedule.current_planned_end") if f in by_field]
    ends = [e for e in ends if e]
    final = item["status"] in ("completed", "cancelled")
    fresh_active = item["status"] in ("planned", "in_progress")
    if final or (not fresh_active and ends and max(ends) < day):
        actuality["bucket"] = "historical"
    else:
        actuality["bucket"] = "current"
    actuality["district"] = district_of(st["geometry"])
    return item, actuality


def build(write: bool = True) -> tuple[dict, list, dict]:
    cfg = config()
    tgts, reg = targets(), registry()
    validator = r12.base_validator()
    current, historical, problems, states = [], [], [], {}
    for slug in sorted(tgts):
        st = target_state(slug, tgts, reg)
        states[slug] = st
        if st["state"] != "draft_ready":
            continue
        item, actuality = to_item(slug, st, tgts)
        st["actuality"] = actuality
        if validator is None:
            problems.append({"where": slug, "code": "validator_not_run",
                             "message": "нет data/civic/astana/tools/civic_v1.py: без профиля real запись не попадает в пакет"})
            st["state"] = "blocked_by_validator"
            continue
        bad = [i for i in validator.validate_object(item, profile="real", as_of=cfg.get("as_of"))
               if i.get("severity", "error") == "error"]
        if bad:
            problems.extend({"where": slug, **b} for b in bad)
            st["state"] = "blocked_by_validator"
            continue
        (historical if actuality["bucket"] == "historical" else current).append(item)

    inputs = []
    for folder in ("evidence", "reviews"):
        for p in sorted((HERE / folder).rglob("*.json")) if (HERE / folder).is_dir() else []:
            inputs.append({"path": p.relative_to(HERE).as_posix(), "sha256": sha256_bytes(p.read_bytes())})
    for name in ("config.json", "analysis/queue_analysis.json"):
        p = HERE / name
        inputs.append({"path": name, "sha256": sha256_bytes(p.read_bytes()) if p.exists() else None})

    def package(items, name, source):
        items = sorted(items, key=lambda x: x["id"])
        return {"schema_version": "civic-v1", "city": "astana",
                "slice": {"name": name, "version": cfg.get("package_version"), "demo": False, "count": len(items),
                          "content_sha256": canonical_sha(items), "source": source, "as_of": cfg.get("as_of"),
                          "builder": "data/civic/astana/round13-verified/tools/r13.py", "inputs": inputs,
                          "notes": "Только цели, прошедшие attach (выдержки в сохранённом тексте страницы) и review "
                                   "сотрудником. Импорт R02 создаёт черновики; публикует сотрудник."},
                "items": items}

    src = cfg.get("package_source", "r05-astana-r13-verified")
    out = {"package.civic-v1.json": package(current, "r05-astana-r13-verified", src),
           "historical.civic-v1.json": package(historical, "r05-astana-r13-verified-historical", src + "-historical")}
    out["summary.json"] = summary(states, out, tgts)
    if write:
        for name, value in out.items():
            write_json(HERE / name, value)
    return out, problems, states


def summary(states: dict, packages: dict, tgts: dict) -> dict:
    cands = candidates()
    current = packages["package.civic-v1.json"]["items"]
    hist = packages["historical.civic-v1.json"]["items"]
    with_valid_text = sorted({p.stem for slug, st in states.items()
                              if st["state"] not in ("candidate", "evidence_invalid") for p in evidence_files(slug)})
    attached = sorted({p.stem for slug in tgts for p in evidence_files(slug)})
    state_counts: dict[str, int] = {}
    for st in states.values():
        state_counts[st["state"]] = state_counts.get(st["state"], 0) + 1
    by_kind = {}
    for slug, t in sorted(tgts.items()):
        row = by_kind.setdefault(t["kind"], {"queue_targets": 0, "mappable": 0, "verified": 0})
        row["queue_targets"] += 1
        row["mappable"] += 1 if t.get("mappable") else 0
        row["verified"] += 1 if states.get(slug, {}).get("state") == "draft_ready" else 0
    by_district = {}
    for slug, t in sorted(tgts.items()):
        st = states.get(slug, {})
        name = ((st.get("actuality") or {}).get("district") or geometry_hint(t).get("district_by_osm_boundaries")
                or "не определён (нет геометрии)")
        row = by_district.setdefault(name, {"queue_targets": 0, "verified": 0})
        row["queue_targets"] += 1
        row["verified"] += 1 if states.get(slug, {}).get("state") == "draft_ready" else 0
    review_rejected = sum(1 for st in states.values() if st["state"] == "rejected")
    return {
        "schema": SUMMARY_SCHEMA, "as_of": config().get("as_of"),
        "verified_current": len(current),
        "verified_historical": len(hist),
        "candidates": {
            "round12_to_verify": sum(1 for c in cands.values() if c.get("decision") == "to_verify"),
            "round12_current_priority": sum(1 for c in cands.values() if c.get("decision") == "to_verify"
                                            and c.get("freshness") == "current_or_upcoming_2026"),
            "queue_targets": len(tgts),
            "queue_targets_mappable": sum(1 for t in tgts.values() if t.get("mappable")),
        },
        "rejected": {
            "round12_rejected": sum(1 for c in cands.values() if c.get("decision") == "rejected"),
            "round12_duplicates": sum(1 for c in cands.values() if c.get("decision") == "duplicate"),
            "round13_review_rejected": review_rejected,
        },
        "fetched_sources": len(with_valid_text),
        "sources_with_attached_text": len(attached),
        "states": dict(sorted(state_counts.items())),
        "coverage_by_kind": by_kind,
        "coverage_by_district": dict(sorted(by_district.items())),
        "note": "verified = цель прошла attach (каждая выдержка найдена в сохранённом тексте страницы) и review "
                "сотрудником и пропущена профилем real R05; районы — по OSM-границам data/astana_districts.geojson "
                "(не официальное описание) для геометрии-подсказки очереди. Неизвестное не равно нулю.",
    }


# ---------------------------------------------------------------- queue
_HINTS: dict = {}


def geometry_hint(t: dict) -> dict:
    """Подсказка геометрии для очереди по OSM-снимку (не решение сотрудника)."""
    key = canonical_sha([t.get("geometry_level"), t.get("osm_query")])
    if key in _HINTS:
        return _HINTS[key]
    if t.get("osm_query") and t.get("geometry_level") in OSM_LEVELS:
        res = run_geocode(t["osm_query"])
        ok = bool(res.get("geometry")) and not res.get("ambiguous")
        hint = {"level": t["geometry_level"], "osm_query": t["osm_query"], "result": "ok" if ok else "no_geometry",
                "geometry_type": (res.get("geometry") or {}).get("type") if ok else None,
                "basis": res.get("geometry_basis") if ok else None, "notes": res.get("notes") or [],
                "district_by_osm_boundaries": district_of(res.get("geometry")) if ok else None,
                "precision": "approximate — подсказка для сотрудника, не точный адрес"}
    else:
        hint = {"level": t.get("geometry_level"), "osm_query": None, "result": "manual_needed",
                "geometry_type": None, "basis": None, "notes": [], "district_by_osm_boundaries": None,
                "precision": "в OSM-снимке только улицы: нужна ручная привязка сотрудником или геометрия нет"}
    _HINTS[key] = hint
    return hint


def build_queue() -> dict:
    cfg = config()
    doc = analysis()
    tgts, reg, cands = targets(), registry(), candidates()
    clusters = doc.get("clusters") or []
    rows = []
    for slug, t in tgts.items():
        st = target_state(slug, tgts, reg)
        geo_hint = geometry_hint(t)
        related_clusters = [c for c in clusters if set(c.get("candidate_ids") or []) & set(t.get("candidate_ids") or [])]
        rows.append({
            "slug": slug, "record_id": record_id(t), "kind": t["kind"], "title_working": t.get("title_ru"),
            "priority": t.get("priority"), "state": st["state"],
            "state_detail": st["detail"] if isinstance(st["detail"], str) else "см. r13.py status " + slug,
            "what_hint": t.get("what_hint"), "location_text": t.get("location_text"),
            "candidate_ids": t.get("candidate_ids") or [],
            "sources_to_open": [{"id": sid, "url": reg[sid]["url"], "publisher": reg[sid].get("publisher"),
                                 "publisher_kind": reg[sid].get("publisher_kind"),
                                 "access_status_in_this_environment": reg[sid].get("access_status")}
                                for sid in t.get("source_ids") or [] if sid in reg],
            "timing_hint": t.get("timing"), "geometry_plan": geo_hint,
            "required_evidence": t.get("required_evidence") or [],
            "do_not_infer": t.get("do_not_infer") or [],
            "contradictions": [x for c in related_clusters for x in c.get("contradictions") or []
                               if not x.get("targets") or slug in x["targets"]],
            "followup_hints": [x for c in related_clusters for x in c.get("followup_hints") or []],
            "mappable": bool(t.get("mappable")), "provability": t.get("provability"),
            "next_action": (f"открыть источник в своём браузере, сохранить текст страницы вне репозитория, "
                            f"r13.py form {slug} --source <id> > form.json, заполнить, r13.py attach form.json --text <файл>")
            if st["state"] == "candidate" else "см. r13.py status " + slug,
        })
    rows.sort(key=lambda r: (r["priority"] if isinstance(r["priority"], int) else 999, r["slug"]))
    current = {cid: c for cid, c in cands.items()
               if c.get("decision") == "to_verify" and c.get("freshness") == "current_or_upcoming_2026"}
    decisions = {}
    for c in clusters:
        for d in c.get("candidate_decisions") or []:
            decisions[d["candidate_id"]] = {**d, "cluster": c.get("key")}
    cand_rows = []
    for cid in sorted(current):
        d = decisions.get(cid) or {}
        cand_rows.append({"candidate_id": cid, "title_as_listed": current[cid].get("title_as_listed"),
                          "kind": current[cid].get("kind"), "cluster": d.get("cluster"), "role": d.get("role"),
                          "related_to": d.get("related_to") or [], "reason": d.get("reason"),
                          "targets": sorted(s for s, t in tgts.items() if cid in (t.get("candidate_ids") or []))})
    return {
        "schema": QUEUE_SCHEMA, "city": "astana", "as_of": cfg.get("as_of"),
        "note": "Очередь проверки. Ни одна цель не подтверждена, пока state не draft_ready. Подсказки (timing_hint, "
                "followup_hints, contradictions) — из заголовков/пересказов поиска раунда 12 и анализа очереди: "
                "проверять по самой странице источника.",
        "analysis_method": doc.get("method"),
        "counts": {"targets": len(rows), "current_priority_candidates": len(cand_rows),
                   "candidates_without_decision": sum(1 for r in cand_rows if not r["role"]),
                   "by_state": {s: sum(1 for r in rows if r["state"] == s) for s in sorted({r["state"] for r in rows})}},
        "targets": rows,
        "current_candidates": cand_rows,
    }


def queue_markdown(queue: dict) -> str:
    """Лист проверки для человека из VERIFY_QUEUE.json (тот же порядок и те же оговорки)."""
    out = [f"# Очередь проверки R05 (раунд 13), срез {queue.get('as_of')}", "",
           queue.get("note", ""), "",
           f"Целей: {queue['counts']['targets']}; текущих кандидатов раунда 12: "
           f"{queue['counts']['current_priority_candidates']}; по состояниям: "
           + ", ".join(f"{k} {v}" for k, v in queue["counts"]["by_state"].items()), ""]
    for i, t in enumerate(queue["targets"], 1):
        geo = t.get("geometry_plan") or {}
        out += [f"## {i}. {t['title_working']} — `{t['slug']}`",
                f"- вид: {t['kind']}; состояние: **{t['state']}**; на карте: {'да' if t['mappable'] else 'нет (программа/без места)'}; "
                f"доказуемость: {(t.get('provability') or {}).get('score')}/5",
                f"- где (подсказка): {t.get('location_text')}"]
        if geo.get("result") == "ok":
            out.append(f"- геометрия-подсказка: {geo['level']} — {geo.get('basis')}; район по OSM-границам: "
                       f"{geo.get('district_by_osm_boundaries') or 'не определён'}")
        else:
            out.append(f"- геометрия: {geo.get('level')} — {geo.get('precision')}"
                       + (f" ({'; '.join(geo.get('notes') or [])})" if geo.get("notes") else ""))
        th = t.get("timing_hint") or {}
        if th:
            out.append(f"- сроки (подсказка, {th.get('origin')}): начало {th.get('start_hint') or '—'}; окончание "
                       f"{th.get('end_hint') or '—'}; актуальность на {queue.get('as_of')}: {th.get('actuality_on_2026_10_07')}"
                       f" — {th.get('reason') or ''}")
        for s in t.get("sources_to_open") or []:
            out.append(f"- открыть: {s['url']} ({s.get('publisher') or 'издатель не указан'}, `{s['id']}`)")
        req = [r for r in t.get("required_evidence") or [] if isinstance(r, dict)]
        if req:
            out.append("- выписать дословно: " + "; ".join(
                f"{r.get('field')}{' (обязательно)' if r.get('mandatory') else ''}: {r.get('quote_must_show')}" for r in req))
        if t.get("do_not_infer"):
            out.append("- не выводить: " + "; ".join(t["do_not_infer"]))
        for c in t.get("contradictions") or []:
            out.append(f"- противоречие: {c.get('about')} — {c.get('assessment')}; проверить: {c.get('what_to_check_on_page')}")
        for h in t.get("followup_hints") or []:
            out.append(f"- позднее сообщение (только подсказка поиска, {h.get('origin')}): {h.get('title')} — {h.get('url')}")
        out.append(f"- шаг: {t['next_action']}")
        out.append("")
    out += ["## Текущие кандидаты раунда 12 и решения", "",
            "| кандидат | вид | роль | цели |", "|---|---|---|---|"]
    for c in queue["current_candidates"]:
        out.append(f"| {c['title_as_listed']} (`{c['candidate_id']}`) | {c['kind']} | {c.get('role') or '—'} | "
                   f"{', '.join(c['targets']) or '—'} |")
    return "\n".join(out).rstrip() + "\n"


def coverage_markdown(summary: dict, queue: dict, packages: dict) -> str:
    """Краткая таблица: проверенные факты, пустые поля, неподтверждённые цели; покрытие по видам и районам."""
    items = packages["package.civic-v1.json"]["items"] + packages["historical.civic-v1.json"]["items"]
    out = [f"# Покрытие R05 (раунд 13), срез {summary.get('as_of')}", "",
           "| счётчик | значение |", "|---|---|"]
    for key in ("verified_current", "verified_historical", "fetched_sources", "sources_with_attached_text"):
        out.append(f"| {key} | {summary.get(key)} |")
    for key, value in summary["candidates"].items():
        out.append(f"| candidates.{key} | {value} |")
    for key, value in summary["rejected"].items():
        out.append(f"| rejected.{key} | {value} |")
    out += ["", "## Проверенные факты", ""]
    if not items:
        out.append("Нет: ни одна цель не прошла attach + review (страницы источников в этой среде не открывались).")
    for it in items:
        filled = [f for f in ("status",) if it["status"] != "unknown"]
        filled += [f"schedule.{k}" for k, v in it["schedule"].items() if v]
        filled += ["budget.amount_kzt"] if it["budget"]["amount_kzt"] is not None else []
        filled += [f"responsible.{k}" for k, v in it["responsible"].items() if v]
        empty = sorted({"status", "schedule.planned_start", "schedule.original_planned_end", "schedule.current_planned_end",
                        "schedule.actual_end", "budget.amount_kzt", "responsible.organization"} - set(filled))
        out.append(f"- `{it['id']}` {it['title']}: подтверждено {', '.join(filled) or '—'}; пусто (неизвестно): {', '.join(empty)}")
    out += ["", "## Покрытие по видам", "", "| вид | целей | на карте возможно | подтверждено |", "|---|---|---|---|"]
    for kind, row in summary["coverage_by_kind"].items():
        out.append(f"| {kind} | {row['queue_targets']} | {row['mappable']} | {row['verified']} |")
    out += ["", "## Покрытие по районам (OSM-границы, не официальные; по подсказке геометрии очереди)", "",
            "| район | целей | подтверждено |", "|---|---|---|"]
    for name, row in summary["coverage_by_district"].items():
        out.append(f"| {name} | {row['queue_targets']} | {row['verified']} |")
    out += ["", "## Неподтверждённые цели (что не знаем)", "",
            "| цель | вид | состояние | геометрия | актуальность на срез (подсказка) |", "|---|---|---|---|---|"]
    for t in queue["targets"]:
        if t["state"] == "draft_ready":
            continue
        geo = t["geometry_plan"]
        out.append(f"| `{t['slug']}` | {t['kind']} | {t['state']} | {geo.get('level')}: {geo.get('result')} | "
                   f"{(t.get('timing_hint') or {}).get('actuality_on_2026_10_07', '—')} |")
    out += ["", "Неизвестное не равно нулю: пустая сумма/подрядчик/дата означают «источник не открыт или не говорит»."]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- forms
def evidence_form(slug: str, source_id: str | None, url: str | None, publisher: str | None, kind_pub: str | None) -> dict:
    tgts, reg = targets(), registry()
    if slug not in tgts:
        raise SystemExit(f"нет цели {slug} в очереди")
    t = tgts[slug]
    if source_id:
        if source_id not in reg:
            raise SystemExit(f"нет источника {source_id} в реестре")
        s = reg[source_id]
        source = {"id": source_id, "url": s["url"], "publisher": s.get("publisher") or "",
                  "publisher_kind": s.get("publisher_kind"), "registered": True}
    elif url:
        source = {"id": new_source_id(url), "url": norm_url(url), "publisher": publisher or "",
                  "publisher_kind": kind_pub or "other", "registered": False}
    else:
        raise SystemExit("укажите --source SRC_ID из очереди или --url (новый источник)")
    when = ["schedule.planned_start", "schedule.current_planned_end"]
    rows = ["what", "location.text"] + when + ["schedule.original_planned_end", "status", "responsible.organization",
                                               "budget.amount_kzt", "budget.basis"]
    return {
        "_help": [
            "1. Откройте URL в своём браузере, сохраните ТЕКСТ страницы в файл ВНЕ репозитория (Ctrl+A, Ctrl+C -> .txt или «Сохранить как»).",
            "2. Выдержки копируйте ДОСЛОВНО (≤300 символов, ≥3 слов). Пустые строки утверждений будут отброшены.",
            "3. Дата на странице -> page.published_on (YYYY-MM-DD) и выдержка с ней -> page.published_quote.",
            "4. Формулировку («до конца года») переводите в дату только с пояснением value_basis.",
            "5. claim_type: stated/expected — план; reported_actual — сообщение о факте (идёт/завершено/отменено).",
            "6. Чего страница НЕ говорит — перечислите в not_stated (сумма, подрядчик и т.п.). Неизвестное не равно нулю.",
            "7. Не вставляйте персональные данные. attached_by — роль/метка, не контакт.",
            "8. Затем: r13.py attach form.json --text /путь/вне/репозитория/page.txt",
        ],
        "_target": {"title_working": t.get("title_ru"), "what_hint": t.get("what_hint"),
                    "location_text": t.get("location_text"), "required_evidence": t.get("required_evidence"),
                    "do_not_infer": t.get("do_not_infer")},
        "schema": EVIDENCE_FORM, "target": slug, "source": source,
        "capture": {"origin": "human_saved_page_text", "attached_by": "", "retrieved_at": ""},
        "page": {"title_quote": "", "published_on": "", "published_quote": "", "city_quote": ""},
        "claims": [{"field": f, "value": None, "quote": "", "claim_type": "stated", "value_basis": None} for f in rows],
        "not_stated": [], "notes": "",
    }


def review_form(slug: str) -> dict:
    tgts = targets()
    if slug not in tgts:
        raise SystemExit(f"нет цели {slug} в очереди")
    t = tgts[slug]
    evs = [r12.load_json(p, {}) for p in evidence_files(slug)]
    if not evs:
        raise SystemExit(f"{slug}: нет прикреплённых доказательств (r13.py attach)")
    return {
        "_help": [
            "Проверяет ДРУГОЙ человек: откройте URL источника (или тот же сохранённый файл) и сверьте каждую выдержку.",
            "claims: для каждого утверждения 'accept' или 'reject: причина'. Одно значение поля — один источник.",
            "geometry.level: street_segment|intersection|whole_street (OSM-снимок 2026-05-06) | manual | none.",
            "none — запись не публикуема (нет пригодной геометрии). whole_street требует reason.",
            "method: url_opened_by_reviewer | saved_text_rechecked (тогда review --text SRC_ID=файл).",
        ],
        "_evidence": [{"source": e.get("source"), "page": e.get("page"),
                       "claims": [{"key": claim_key(e, c), "value": c.get("value"), "quote": c.get("quote"),
                                   "claim_type": c.get("claim_type"), "value_basis": c.get("value_basis")}
                                  for c in e.get("claims") or []],
                       "not_stated": e.get("not_stated")} for e in evs],
        "schema": REVIEW_FORM, "target": slug, "evidence_digest": evidence_digest(slug),
        "reviewer": "", "method": "url_opened_by_reviewer", "decision": "accept", "reason": "",
        "kind": t["kind"], "title": t.get("title_ru") or "", "description": "",
        "claims": {claim_key(e, c): "" for e in evs for c in e.get("claims") or []},
        "geometry": {"level": t.get("geometry_level") if t.get("geometry_level") in GEOMETRY_LEVELS else "none",
                     "osm_query": t.get("osm_query"), "manual_geojson": None, "basis": "", "reason": ""},
    }


def _strip_help(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO.resolve())
        return True
    except ValueError:
        return False


def _fail(status: str, problems: list, code: int = 1) -> int:
    print(dump_json({"status": status, "problems": problems}))
    return code


def cmd_attach(args) -> int:
    form = r12.load_json(Path(args.form), None)
    if not isinstance(form, dict) or form.get("schema") != EVIDENCE_FORM:
        return _fail("rejected", [{"problem": f"ожидается форма {EVIDENCE_FORM} (r13.py form)"}], 2)
    text_path = Path(args.text)
    if not text_path.is_file():
        return _fail("rejected", [{"problem": f"нет файла текста страницы {text_path}"}], 2)
    if _inside_repo(text_path):
        return _fail("rejected", [{"problem": "текст страницы храните ВНЕ репозитория (он не коммитится)"}], 2)
    if text_path.stat().st_size > MAX_TEXT_BYTES:
        return _fail("rejected", [{"problem": "файл больше 20 МиБ — сохраните только текст статьи"}], 2)
    slug = form.get("target")
    tgts, reg = targets(), registry()
    if slug not in tgts:
        return _fail("rejected", [{"problem": f"нет цели {slug} в очереди"}], 2)
    raw = text_path.read_bytes()
    text = page_text(raw.decode("utf-8", "replace"))
    keep = norm_keep_case(text)
    ev = _strip_help(copy.deepcopy(form))
    ev["schema"] = EVIDENCE_SCHEMA
    ev["claims"] = [c for c in ev.get("claims") or []
                    if isinstance(c, dict) and not (c.get("value") in (None, "") and not (c.get("quote") or "").strip())]
    for c in ev["claims"]:
        if c.get("value_basis") in ("", None):
            c.pop("value_basis", None)
    cap = dict(ev.get("capture") or {})
    cap.update({"attached_at": args.attached_at or now_ts(), "content_sha256": sha256_bytes(raw),
                "text_chars": len(norm_text(text)), "storage": "outside_repo"})
    ev["capture"] = cap
    ev["snapshot"] = [{"ref": ref, "context": context_of(q, keep)} for ref, q in quotes_of(ev)]
    issues = Issues()
    sid = (ev.get("source") or {}).get("id") or "?"
    path = evidence_dir(slug) / f"{sid}.json"
    check_evidence(ev, path, slug, tgts, reg, issues, pii_finder())
    found = verify_against_text(ev, raw)
    if issues.errors or found:
        return _fail("not_attached", issues.errors + found)
    if path.exists() and not args.replace:
        return _fail("not_attached", [{"problem": f"{path.relative_to(HERE)} уже есть; --replace заменит его "
                                                  "(проверка сотрудником станет устаревшей)"}])
    write_json(path, ev)
    print(dump_json({"status": "evidence_attached", "target": slug, "source": sid,
                     "file": path.relative_to(HERE).as_posix(), "state": target_state(slug)["state"]}))
    return 0


def cmd_review(args) -> int:
    form = r12.load_json(Path(args.form), None)
    if not isinstance(form, dict) or form.get("schema") != REVIEW_FORM:
        return _fail("rejected", [{"problem": f"ожидается форма {REVIEW_FORM} (r13.py review-form)"}], 2)
    slug = form.get("target")
    tgts, reg = targets(), registry()
    if slug not in tgts:
        return _fail("rejected", [{"problem": f"нет цели {slug} в очереди"}], 2)
    files = evidence_files(slug)
    evs, issues = [], Issues()
    for p in files:
        ev = r12.read_json(p, issues)
        check_evidence(ev, p, slug, tgts, reg, issues, pii_finder())
        evs.append(ev)
    if not evs or issues.errors:
        return _fail("rejected", issues.errors or [{"problem": "нет прикреплённых доказательств"}])
    if form.get("evidence_digest") != evidence_digest(slug):
        return _fail("rejected", [{"problem": "доказательства изменились после review-form: сформируйте форму заново"}])
    rv = _strip_help(copy.deepcopy(form))
    rv["schema"] = REVIEW_SCHEMA
    rv["reviewed_at"] = args.reviewed_at or now_ts()
    rechecked = None
    if rv.get("method") == "saved_text_rechecked":
        texts = {}
        for item in args.text or []:
            sid, sep, file = item.partition("=")
            if not sep or not Path(file).is_file():
                return _fail("rejected", [{"problem": f"--text ожидает SRC_ID=файл: {item}"}], 2)
            texts[sid] = Path(file).read_bytes()
        problems = []
        for ev in evs:
            sid = ev["source"]["id"]
            if sid not in texts:
                problems.append({"source_id": sid, "problem": "нет --text для сверки"})
            else:
                problems += [{"source_id": sid, **p} for p in verify_against_text(ev, texts[sid])]
        if problems:
            return _fail("rejected", problems)
        rechecked = True
    rv["text_rechecked"] = bool(rechecked)
    geo = rv.get("geometry") if isinstance(rv.get("geometry"), dict) else None
    if geo is not None:
        for key in [k for k in geo if geo[k] in (None, "") and k in ("manual_geojson", "basis", "reason", "osm_query")]:
            geo.pop(key)
    if rv.get("decision") == "accept" and geo is not None and geo.get("level") in GEOMETRY_LEVELS and geo.get("level") != "none":
        geometry, basis, problems = geometry_from_review(geo)
        for p in problems:
            issues.add(f"reviews/{slug}.json.geometry", "geometry", p)
        if not problems:
            geo["geometry_sha256"] = canonical_sha(geometry)
    check_review(rv, slug, evs, tgts, issues, pii_finder())
    if issues.errors:
        return _fail("rejected", issues.errors)
    write_json(HERE / "reviews" / f"{slug}.json", rv)
    print(dump_json({"status": "reviewed", "target": slug, "decision": rv["decision"],
                     "state": target_state(slug)["state"]}))
    return 0


def cmd_status(args) -> int:
    tgts = targets()
    slugs = [args.slug] if args.slug else sorted(tgts)
    out = []
    for slug in slugs:
        if slug not in tgts:
            return _fail("unknown", [{"problem": f"нет цели {slug}"}], 2)
        st = target_state(slug, tgts)
        out.append({"slug": slug, "kind": tgts[slug]["kind"], "state": st["state"], "detail": st["detail"]})
    print(dump_json(out))
    return 0


def cmd_check(args) -> int:
    issues = Issues()
    doc = analysis()
    tgts = check_analysis(doc, issues)
    # Файлы вне известных целей и вне схемы каталога — ошибка, а не «тихо проверенные».
    for folder in ("evidence", "reviews"):
        base = HERE / folder
        for p in sorted(base.rglob("*")) if base.is_dir() else []:
            if p.is_dir() or p.name == ".gitkeep":
                continue
            rel = p.relative_to(HERE).as_posix()
            parts = p.relative_to(base).parts
            if p.suffix != ".json":
                issues.add(rel, "stray_file", "в каталоге только JSON доказательств/проверок")
            elif folder == "evidence" and (len(parts) != 2 or parts[0] not in tgts):
                issues.add(rel, "stray_file", "evidence/<slug очереди>/<source.id>.json")
            elif folder == "reviews" and (len(parts) != 1 or p.stem not in tgts):
                issues.add(rel, "stray_file", "reviews/<slug очереди>.json")
            elif folder == "reviews" and not evidence_files(p.stem):
                issues.add(rel, "review_without_evidence", "проверка без прикреплённых доказательств ничего не подтверждает")
    states = {}
    for slug in sorted(tgts):
        st = target_state(slug, tgts)
        states[slug] = st["state"]
        if st["state"] in ("evidence_invalid", "review_invalid"):
            for item in st["detail"]:
                issues.add(item.get("where", slug), item.get("code", "invalid"), item.get("message", ""))
    stale = []
    packages, problems, _ = build(write=False)
    for name, value in packages.items():
        p = HERE / name
        if not p.exists() or p.read_text(encoding="utf-8") != dump_json(value):
            stale.append(name)
    queue = build_queue()
    qp = HERE / "VERIFY_QUEUE.json"
    if not qp.exists() or qp.read_text(encoding="utf-8") != dump_json(queue):
        stale.append("VERIFY_QUEUE.json")
    print(dump_json({"status": "ok" if not (issues.errors or problems or stale) else "problems",
                     "errors": issues.errors, "build_problems": problems, "stale_outputs": stale, "states": states}))
    return 1 if issues.errors or problems or stale else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("queue")
    q.add_argument("--check", action="store_true")
    q.add_argument("--markdown", help="также записать лист проверки для человека (Markdown) в этот файл")
    s = sub.add_parser("status")
    s.add_argument("slug", nargs="?")
    f = sub.add_parser("form")
    f.add_argument("slug")
    f.add_argument("--source")
    f.add_argument("--url")
    f.add_argument("--publisher")
    f.add_argument("--publisher-kind", choices=PUBLISHER_KINDS)
    a = sub.add_parser("attach")
    a.add_argument("form")
    a.add_argument("--text", required=True, help="файл с текстом/HTML страницы вне репозитория")
    a.add_argument("--attached-at")
    a.add_argument("--replace", action="store_true")
    rf = sub.add_parser("review-form")
    rf.add_argument("slug")
    r = sub.add_parser("review")
    r.add_argument("form")
    r.add_argument("--text", action="append", help="SRC_ID=файл (для method saved_text_rechecked)")
    r.add_argument("--reviewed-at")
    b = sub.add_parser("build")
    b.add_argument("--check", action="store_true")
    sub.add_parser("check")
    rp = sub.add_parser("report")
    rp.add_argument("--markdown", required=True, help="файл таблицы покрытия (вне каталога пакета)")
    g = sub.add_parser("geocode")
    g.add_argument("--street", required=True)
    g.add_argument("--cross")
    g.add_argument("--from", dest="frm")
    g.add_argument("--to")
    args = ap.parse_args(argv)

    if args.cmd == "queue":
        queue = build_queue()
        path = HERE / "VERIFY_QUEUE.json"
        if args.check:
            ok = path.exists() and path.read_text(encoding="utf-8") == dump_json(queue)
            print(dump_json({"status": "ok" if ok else "stale", "counts": queue["counts"]}))
            return 0 if ok else 1
        write_json(path, queue)
        if args.markdown:
            Path(args.markdown).write_text(queue_markdown(queue), encoding="utf-8")
        print(dump_json({"status": "written", "counts": queue["counts"]}))
        return 0
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "form":
        print(dump_json(evidence_form(args.slug, args.source, args.url, args.publisher, args.publisher_kind)), end="")
        return 0
    if args.cmd == "attach":
        return cmd_attach(args)
    if args.cmd == "review-form":
        print(dump_json(review_form(args.slug)), end="")
        return 0
    if args.cmd == "review":
        return cmd_review(args)
    if args.cmd == "build":
        packages, problems, _ = build(write=not args.check)
        if args.check:
            stale = [n for n, v in packages.items()
                     if not (HERE / n).exists() or (HERE / n).read_text(encoding="utf-8") != dump_json(v)]
            print(dump_json({"status": "ok" if not stale and not problems else "stale_or_problems",
                             "stale": stale, "problems": problems}))
            return 1 if stale or problems else 0
        print(dump_json({"status": "built", "summary": packages["summary.json"], "problems": problems}))
        return 0
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "report":
        packages, problems, _ = build(write=False)
        Path(args.markdown).write_text(coverage_markdown(packages["summary.json"], build_queue(), packages),
                                       encoding="utf-8")
        print(dump_json({"status": "written", "file": args.markdown, "problems": problems}))
        return 0
    if args.cmd == "geocode":
        print(dump_json(run_geocode({"street": args.street, "cross": args.cross, "from": args.frm, "to": args.to})))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
