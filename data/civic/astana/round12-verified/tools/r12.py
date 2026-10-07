"""R05 раунд 12: пакет подтверждённых работ/событий Астаны (только stdlib).

    python3 -I data/civic/astana/round12-verified/tools/r12.py check
    python3 -I .../r12.py verify drafts/<id>.json --text SRC=FILE [--text ...] \
        [--published-on SRC=YYYY-MM-DD] --retrieved-at 2026-10-07T12:00:00Z [--method human_saved_text]
    python3 -I .../r12.py build [--check]
    python3 -I .../r12.py geocode --street "Кайсенова" [--cross "Тлендиева"] [--from A --to B]
    python3 -I .../r12.py fetch SRC_ID --out DIR      # только где политика сети разрешает домен
    python3 -I .../r12.py summary

Принцип: значение попадает в карточку, только если дословная выдержка из полученного текста источника
это говорит. Выдача поиска (заголовок, URL, пересказ) источник «полученным» не делает.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import hashlib
import html
import json
import math
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent.parent    # .../data/civic/astana/round12-verified
ASTANA = PACKAGE_DIR.parent                              # .../data/civic/astana
REPO = ASTANA.parents[2]
BASE_TOOLS = ASTANA / "tools"
# Каталог пакета можно подменить (изолированные тесты); код и валидаторы базы берутся из репозитория.
HERE = Path(os.environ["R12_HOME"]).resolve() if os.environ.get("R12_HOME") else PACKAGE_DIR

KINDS = ("construction", "roadworks", "landscaping", "event")
STATUSES = ("planned", "in_progress", "completed", "cancelled", "unknown")
CLAIM_FIELDS = ("status", "schedule.planned_start", "schedule.original_planned_end",
                "schedule.current_planned_end", "schedule.actual_end", "budget.amount_kzt",
                "budget.basis", "responsible.organization", "responsible.public_contact")
CLAIM_TYPES = ("stated", "expected", "reported_actual")
PUBLISHER_KINDS = ("official_gov", "city_utility_or_operator", "state_media", "city_media", "news", "other")
ACCESS = ("fetched", "not_fetched", "unavailable")
DECISIONS = ("to_verify", "rejected", "duplicate")
HINT_ORIGINS = ("url", "search_title", "search_summary", "none")
PRECISIONS = ("approximate", "unknown")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
RECORD_ID_RE = re.compile(r"^ast-r12-(construction|roadworks|landscaping|event)-[a-z0-9-]{3,40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
HTML_TAG_RE = re.compile(r"<\s*[A-Za-z/!?]")
MAX_QUOTE = 300
PROPRIETARY_GEO = ("2gis", "google", "yandex", "apple.com/maps", "here.com")


# ---------------------------------------------------------------- utilities
def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_json(value), encoding="utf-8")


def parse_date(value: Any) -> _dt.date | None:
    if not isinstance(value, str) or not DATE_RE.match(value):
        return None
    try:
        return _dt.date.fromisoformat(value)
    except ValueError:
        return None


def norm_text(value: str) -> str:
    """Нормализация для сверки выдержек: регистр, пробелы, кавычки, тире, ё."""
    text = unicodedata.normalize("NFKC", value).replace("­", "")
    for a, b in (("«", '"'), ("»", '"'), ("“", '"'), ("”", '"'), ("„", '"'), ("‘", "'"), ("’", "'"),
                 ("–", "-"), ("—", "-"), ("−", "-"), ("‑", "-"), ("ё", "е"), ("Ё", "Е")):
        text = text.replace(a, b)
    return re.sub(r"\s+", " ", text).strip().casefold()


def page_text(raw: str) -> str:
    """HTML/фрагмент -> текст: комментарии, script/style/noscript/template и теги удаляются всегда,
    если в файле есть разметка (даже без <html>/<body>). Обычный текст — как есть."""
    if re.search(r"<\s*[A-Za-z!/]", raw):
        raw = re.sub(r"(?s)<!--.*?-->", " ", raw)
        raw = re.sub(r"(?is)<(script|style|noscript|template)\b.*?</\1\s*>", " ", raw)
        raw = re.sub(r"(?is)<(script|style|noscript|template)\b.*$", " ", raw)   # незакрытый блок
        raw = re.sub(r"(?s)<[^>]*>", " ", raw)
        raw = html.unescape(raw)
    return raw


def quote_found(quote: str, text_norm: str) -> bool:
    """Выдержка найдена целыми словами: «250 000 000» не совпадает внутри «1 250 000 000», «1 ноября» — внутри «21 ноября»."""
    q = norm_text(quote)
    pattern = r"(?<!\w)(?<!\d )" + re.escape(q) + r"(?!\w)(?! \d)"
    return re.search(pattern, text_norm) is not None


MONTHS_GEN = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
              "октября", "ноября", "декабря")


def date_in_quote(value: str, quote: str) -> bool:
    d = parse_date(value)
    if d is None:
        return False
    q = norm_text(quote)
    forms = [d.isoformat(), f"{d.day:02d}.{d.month:02d}.{d.year}", f"{d.day}.{d.month:02d}.{d.year}",
             f"{d.day} {MONTHS_GEN[d.month - 1]} {d.year}", f"{d.day:02d} {MONTHS_GEN[d.month - 1]} {d.year}"]
    return any(re.search(r"(?<!\d)" + re.escape(f) + r"(?!\d)", q) for f in forms)


def amount_in_quote(value, quote: str) -> bool:
    """Сумма в тенге целиком записана цифрами в выдержке (разряды через пробел допустимы)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value != int(value):
        return False
    numbers = re.findall(r"(?<![\d.,])\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?![\d])|(?<![\d.,])\d+(?![\d.,])",
                         unicodedata.normalize("NFKC", quote))
    return any(int(re.sub(r"\D", "", n)) == int(value) for n in numbers)


MIN_QUOTE_WORDS = 3


def claims_digest(rec: dict) -> str:
    """Отпечаток того, что проверил verify: правка claims/места после проверки его меняет."""
    keep = {k: rec.get(k) for k in ("id", "kind", "historical", "location", "claims")}
    return hashlib.sha256(json.dumps(keep, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def config() -> dict:
    return load_json(HERE / "config.json", {})


def base_validator():
    """Валидатор R05 раунда 11 (data/civic/astana/tools/civic_v1.py), если он есть в дереве."""
    if not (BASE_TOOLS / "civic_v1.py").exists():
        return None
    sys.path.insert(0, str(BASE_TOOLS))
    try:
        import civic_v1  # type: ignore
        return civic_v1
    except Exception:  # pragma: no cover - сломанный чужой модуль = проверка NOT_RUN
        return None
    finally:
        sys.path.pop(0)


def r02_validate_content():
    """ui.civic_store.validate.validate_content (R02), если доступен."""
    sys.path.insert(0, str(REPO))
    try:
        from ui.civic_store.validate import ValidationError, validate_content  # type: ignore
        return validate_content, ValidationError
    except Exception:
        return None, None
    finally:
        sys.path.pop(0)


# ---------------------------------------------------------------- checks
class Issues:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, where: str, code: str, message: str, severity: str = "error") -> None:
        self.items.append({"where": where, "code": code, "message": message, "severity": severity})

    @property
    def errors(self) -> list[dict]:
        return [i for i in self.items if i["severity"] == "error"]


def _text_ok(value: Any, where: str, issues: Issues, *, required: bool, max_len: int) -> None:
    if value is None or value == "":
        if required:
            issues.add(where, "required", "обязательный текст")
        return
    if not isinstance(value, str) or len(value) > max_len:
        issues.add(where, "bad_text", f"строка до {max_len} символов")
    elif HTML_TAG_RE.search(value):
        issues.add(where, "html", "HTML-теги не допускаются")


def check_sources(reg: dict, issues: Issues) -> dict:
    sources = {}
    if not isinstance(reg, dict) or reg.get("schema") != "r05-r12-sources-v1" or reg.get("city") != "astana":
        issues.add("sources.json", "schema", "ожидается r05-r12-sources-v1 для astana")
        return sources
    for i, src in enumerate(reg.get("sources") or []):
        here = f"sources[{i}]"
        sid = src.get("id")
        if not isinstance(sid, str) or not ID_RE.match(sid):
            issues.add(here, "id", "id источника: латиница/цифры/._- до 64")
            continue
        if sid in sources:
            issues.add(here, "dup_id", f"повтор id {sid}")
        sources[sid] = src
        url = src.get("url")
        if not isinstance(url, str) or not url.startswith("https://") or len(url) > 2000 or " " in url:
            issues.add(here + ".url", "url", "нужна ссылка https://")
        elif any(p in url.lower() for p in ("web.archive.org", "archive.ph", "r.jina.ai", "webcache")):
            issues.add(here + ".url", "mirror", "ссылка должна вести на источник, а не на копию/читалку")
        if src.get("publisher_kind") not in PUBLISHER_KINDS:
            issues.add(here + ".publisher_kind", "enum", "publisher_kind из списка")
        access = src.get("access_status")
        if access not in ACCESS:
            issues.add(here + ".access_status", "enum", "fetched | not_fetched | unavailable")
        if src.get("published_on") is not None:
            if parse_date(src.get("published_on")) is None:
                issues.add(here + ".published_on", "date", "YYYY-MM-DD или null")
            elif src.get("published_on_basis") not in ("page", "url"):
                issues.add(here + ".published_on_basis", "basis", "дата публикации только со страницы (page) или из URL (url)")
            elif src.get("published_on_basis") == "url" and src["published_on"] not in str(src.get("url")):
                issues.add(here + ".published_on", "url_date", "published_on_basis=url, но этой даты нет в URL")
        if access == "fetched":
            if not (isinstance(src.get("retrieved_at"), str) and TS_RE.match(src["retrieved_at"])):
                issues.add(here + ".retrieved_at", "required", "fetched требует retrieved_at (UTC ...Z)")
            if not (isinstance(src.get("content_sha256"), str) and SHA_RE.match(src["content_sha256"])):
                issues.add(here + ".content_sha256", "required", "fetched требует sha256 полученного текста")
            if src.get("fetch_method") not in ("agent_http", "human_saved_text"):
                issues.add(here + ".fetch_method", "enum", "agent_http | human_saved_text")
        _text_ok(src.get("title_as_listed"), here + ".title_as_listed", issues, required=False, max_len=400)
    return sources


def check_candidates(doc: dict, sources: dict, issues: Issues) -> list:
    if not isinstance(doc, dict) or doc.get("schema") != "r05-r12-candidates-v1":
        issues.add("candidates.json", "schema", "ожидается r05-r12-candidates-v1")
        return []
    seen = set()
    items = doc.get("candidates") or []
    for i, cand in enumerate(items):
        here = f"candidates[{i}]"
        cid = cand.get("id")
        if not isinstance(cid, str) or not ID_RE.match(cid):
            issues.add(here + ".id", "id", "id кандидата")
        elif cid in seen:
            issues.add(here + ".id", "dup_id", f"повтор {cid}")
        seen.add(cid)
        if cand.get("decision") not in DECISIONS:
            issues.add(here + ".decision", "enum", "to_verify | rejected | duplicate")
        if cand.get("kind") not in KINDS:
            issues.add(here + ".kind", "enum", "kind civic-v1")
        if not cand.get("reason"):
            issues.add(here + ".reason", "required", "нужна причина решения")
        ids = cand.get("source_ids") or []
        if not ids:
            issues.add(here + ".source_ids", "required", "хотя бы один источник")
        for sid in ids:
            if sid not in sources:
                issues.add(here + ".source_ids", "unknown_source", f"{sid} нет в sources.json")
        if cand.get("date_hint_origin") not in HINT_ORIGINS:
            issues.add(here + ".date_hint_origin", "enum", "url | search_title | search_summary | none")
        if cand.get("decision") == "duplicate" and cand.get("duplicate_of") not in seen | {c.get("id") for c in items}:
            issues.add(here + ".duplicate_of", "unknown", "duplicate_of должен ссылаться на кандидата")
        for j, hint in enumerate(cand.get("hints") or []):
            if hint.get("origin") not in ("url", "search_title", "search_summary"):
                issues.add(f"{here}.hints[{j}]", "origin", "происхождение подсказки")
        geo = cand.get("geocode")
        if geo is not None:
            _check_location(geo, here + ".geocode", issues)
    return items


def _check_location(loc: dict, where: str, issues: Issues) -> None:
    if not isinstance(loc, dict):
        issues.add(where, "type", "объект location")
        return
    geom = loc.get("geometry")
    precision = loc.get("geometry_precision")
    if precision not in PRECISIONS:
        issues.add(where + ".geometry_precision", "enum", "approximate | unknown (source — только если координаты дал сам источник)")
    if geom is None:
        if precision != "unknown":
            issues.add(where + ".geometry_precision", "no_geometry", "без геометрии точность unknown")
        return
    if not isinstance(geom, dict) or geom.get("type") not in ("Point", "LineString", "Polygon"):
        issues.add(where + ".geometry", "type", "GeoJSON Point | LineString | Polygon")
        return
    basis = loc.get("geometry_basis") or ""
    if not basis:
        issues.add(where + ".geometry_basis", "required", "откуда геометрия (OSM id, снимок)")
    if any(p in basis.lower() for p in PROPRIETARY_GEO):
        issues.add(where + ".geometry_basis", "proprietary", "геометрия из закрытых карт не допускается")
    pts = geom.get("coordinates")
    flat = [pts] if geom["type"] == "Point" else (pts if geom["type"] == "LineString" else [p for r in pts or [] for p in r])
    for p in flat or []:
        if not (isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in p)
                and 70.8 <= p[0] <= 72.1 and 50.75 <= p[1] <= 51.6):
            issues.add(where + ".geometry", "outside", "координаты [lon, lat] в рамке Астаны")
            break


def check_record(rec: dict, sources: dict, issues: Issues, *, verified: bool, pii=None) -> None:
    rid = rec.get("id", "?")
    here = f"record:{rid}"
    if rec.get("schema") != "r05-r12-record-v1":
        issues.add(here, "schema", "ожидается r05-r12-record-v1")
    if not isinstance(rid, str) or not RECORD_ID_RE.match(rid):
        issues.add(here + ".id", "id", "ast-r12-<kind>-<slug>")
    elif rec.get("kind") and not rid.startswith(f"ast-r12-{rec.get('kind')}-"):
        issues.add(here + ".id", "id_kind", "id должен начинаться с ast-r12-<kind>-")
    if rec.get("kind") not in KINDS:
        issues.add(here + ".kind", "enum", "kind civic-v1")
    _text_ok(rec.get("title"), here + ".title", issues, required=True, max_len=200)
    _text_ok(rec.get("description"), here + ".description", issues, required=False, max_len=5000)
    _text_ok(rec.get("evidence_notes"), here + ".evidence_notes", issues, required=True, max_len=1500)
    _check_location(rec.get("location") or {}, here + ".location", issues)
    claims = rec.get("claims") or []
    if not claims:
        issues.add(here + ".claims", "required", "без подтверждённых значений запись не нужна")
    seen_fields = set()
    for j, claim in enumerate(claims):
        cw = f"{here}.claims[{j}]"
        field = claim.get("field")
        if field not in CLAIM_FIELDS:
            issues.add(cw + ".field", "enum", "поле civic-v1 из списка")
            continue
        if field in seen_fields:
            issues.add(cw + ".field", "dup_field", "одно значение поля — одна запись claims (противоречие → кандидаты)")
        seen_fields.add(field)
        if claim.get("claim_type") not in CLAIM_TYPES:
            issues.add(cw + ".claim_type", "enum", "stated | expected | reported_actual")
        sid = claim.get("source_id")
        if sid not in sources:
            issues.add(cw + ".source_id", "unknown_source", f"{sid} нет в sources.json")
        elif verified and sources[sid].get("access_status") != "fetched":
            issues.add(cw + ".source_id", "not_fetched", "подтверждённая запись ссылается только на полученные источники")
        quote = claim.get("quote")
        if not isinstance(quote, str) or not quote.strip() or len(quote) > MAX_QUOTE:
            issues.add(cw + ".quote", "quote", f"дословная выдержка 1–{MAX_QUOTE} символов")
            quote = ""
        elif len(norm_text(quote).split()) < MIN_QUOTE_WORDS:
            issues.add(cw + ".quote", "quote_short", f"выдержка не короче {MIN_QUOTE_WORDS} слов (одно слово ничего не подтверждает)")
        value = claim.get("value")
        basis = claim.get("value_basis")
        if field.startswith("schedule.") and quote and not basis and parse_date(value) and not date_in_quote(value, quote):
            issues.add(cw + ".quote", "value_not_in_quote", "дата значения должна быть в выдержке (иначе объясните в value_basis)")
        if field == "budget.amount_kzt" and quote and not basis and not amount_in_quote(value, quote):
            issues.add(cw + ".quote", "value_not_in_quote", "сумма цифрами должна быть в выдержке (иначе объясните в value_basis)")
        if field == "schedule.actual_end" and claim.get("claim_type") != "reported_actual":
            issues.add(cw + ".claim_type", "actual_type", "actual_end — только reported_actual (обещанная дата ≠ факт)")
        if field.startswith("schedule."):
            if parse_date(value) is None:
                issues.add(cw + ".value", "date", "YYYY-MM-DD")
        elif field == "status":
            if value not in STATUSES or value == "unknown":
                issues.add(cw + ".value", "enum", "planned | in_progress | completed | cancelled")
            elif value == "planned" and claim.get("claim_type") == "reported_actual":
                issues.add(cw + ".claim_type", "status_type", "planned — это план, не фактическое сообщение")
            elif value in ("in_progress", "completed", "cancelled") and claim.get("claim_type") != "reported_actual":
                issues.add(cw + ".claim_type", "status_type", f"{value} требует reported_actual (обещание ≠ факт)")
        elif field == "budget.amount_kzt":
            if not (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0):
                issues.add(cw + ".value", "amount", "сумма в тенге > 0 (неизвестное — не claim)")
        elif field == "budget.basis":
            if value not in ("planned", "contract", "spent"):
                issues.add(cw + ".value", "enum", "planned | contract | spent")
        else:
            _text_ok(value, cw + ".value", issues, required=True, max_len=300)
        if pii is not None:
            for text in (quote, claim.get("value") if isinstance(claim.get("value"), str) else None):
                if isinstance(text, str) and pii(text):
                    issues.add(cw, "pii", "персональные данные в выдержке/значении")
    fields = {c.get("field") for c in claims}
    if "budget.amount_kzt" in fields and "budget.basis" not in fields:
        issues.add(here + ".claims", "budget_basis", "сумма без основания (planned/contract/spent)")
    by_field = {c.get("field"): c for c in claims}
    if "budget.amount_kzt" in by_field and "budget.basis" in by_field and \
            by_field["budget.amount_kzt"].get("source_id") != by_field["budget.basis"].get("source_id"):
        issues.add(here + ".claims", "budget_basis_source", "основание суммы должно быть из того же источника, что и сумма")
    status = next((c.get("value") for c in claims if c.get("field") == "status"), None)
    if "schedule.actual_end" in fields and status != "completed":
        issues.add(here + ".claims", "actual_end", "actual_end только при status=completed")
    if verified:
        ver = rec.get("verification")
        if not isinstance(ver, dict) or not isinstance(ver.get("sources"), dict):
            issues.add(here + ".verification", "required", "блок verification создаёт команда verify")
        else:
            if ver.get("claims_digest") != claims_digest(rec):
                issues.add(here + ".verification", "edited_after_verify",
                           "claims/место изменены после verify: запись нужно проверить заново")
            for c in claims:
                if c.get("source_id") not in ver["sources"]:
                    issues.add(here + ".verification", "unverified_source", f"{c.get('source_id')} не проверялся для этой записи")
            for sid, info in ver["sources"].items():
                src = sources.get(sid, {})
                for key in ("content_sha256", "published_on", "retrieved_at"):
                    if src.get(key) != info.get(key):
                        issues.add(here + ".verification", "source_changed", f"{sid}.{key} изменился после проверки записи")


# ---------------------------------------------------------------- civic-v1
def to_civic(rec: dict, sources: dict, as_of: str) -> dict:
    claims = {c["field"]: c for c in rec.get("claims") or []}
    loc = rec.get("location") or {}
    by_source: dict[str, set] = {}
    for c in rec.get("claims") or []:
        by_source.setdefault(c["source_id"], set()).add(c["field"])
    refs = []
    for sid in sorted(by_source):
        src = sources[sid]
        refs.append({"id": sid, "url": src["url"], "publisher": src.get("publisher"),
                     "published_on": src.get("published_on"), "retrieved_at": src.get("retrieved_at"),
                     "access_status": src.get("access_status"), "license": src.get("license"),
                     "fields": sorted(by_source[sid])})

    def val(field):
        return claims[field]["value"] if field in claims else None

    derived = [c for c in rec.get("claims") or [] if c.get("value_basis")]
    notes = [rec.get("evidence_notes", "").strip()]
    if derived:
        notes.append("Значения, выведенные из формулировок: " + "; ".join(
            f"{c['field']}: {c['value_basis']}" for c in derived) + ".")
    if loc.get("geometry") is not None:
        notes.append("Геометрия: " + loc.get("geometry_basis", "") + ".")
    if rec.get("not_confirmed"):
        notes.append("Источник не подтверждает: " + ", ".join(rec["not_confirmed"]) + ".")
    amount = val("budget.amount_kzt")
    # Серверные поля — как в срезах R05 раунда 11: импортер R02 их игнорирует и назначает сам.
    return {
        "schema_version": "civic-v1",
        "id": rec["id"],
        "city": "astana",
        "publication": "draft",
        "revision": 1,
        "updated_at": f"{as_of}T00:00:00Z",
        "kind": rec["kind"],
        "title": rec["title"],
        "description": rec.get("description") or "",
        "status": val("status") or "unknown",
        "geometry": loc.get("geometry"),
        "geometry_precision": loc.get("geometry_precision", "unknown") if loc.get("geometry") else "unknown",
        "schedule": {k: val("schedule." + k) for k in ("planned_start", "original_planned_end",
                                                       "current_planned_end", "actual_end")},
        "budget": {"amount_kzt": amount, "basis": val("budget.basis") or "unknown",
                   "source_id": claims["budget.amount_kzt"]["source_id"] if amount is not None else None},
        "responsible": {"organization": val("responsible.organization"),
                        "public_contact": val("responsible.public_contact")},
        "evidence_type": "derived" if derived else "observed",
        "source_refs": refs,
        "evidence_notes": " ".join(n for n in notes if n)[:2000],
    }


def is_historical(rec: dict, as_of: _dt.date, cutoff_days: int) -> bool:
    if rec.get("historical") is True:
        return True
    ends = [parse_date(c.get("value")) for c in rec.get("claims") or []
            if c.get("field") in ("schedule.actual_end", "schedule.current_planned_end")]
    ends = [e for e in ends if e]
    return bool(ends) and max(ends) < as_of - _dt.timedelta(days=cutoff_days)


def load_records(folder: str) -> list[dict]:
    path = HERE / folder
    return [load_json(p) for p in sorted(path.glob("*.json"))] if path.exists() else []


def build(write: bool = True) -> tuple[dict, list[dict]]:
    cfg = config()
    as_of = parse_date(cfg.get("as_of"))
    reg = load_json(HERE / "sources.json", {"schema": "r05-r12-sources-v1", "city": "astana", "sources": []})
    issues = Issues()
    sources = check_sources(reg, issues)
    current, historical = [], []
    validator = base_validator()
    records = load_records("verified")
    if records and validator is None:
        issues.add("build", "validator_not_run",
                   "нет data/civic/astana/tools/civic_v1.py: без профиля real записи в пакет не попадают")
    for rec in records:
        before = len(issues.errors)
        check_record(rec, sources, issues, verified=True)
        if len(issues.errors) > before or validator is None:
            continue
        item = to_civic(rec, sources, cfg.get("as_of"))
        problems = [i for i in validator.validate_object(item, profile="real", as_of=cfg.get("as_of"))
                    if i.get("severity", "error") == "error"]
        for prob in problems:
            issues.add(f"record:{rec.get('id')}", "r05_real_" + str(prob.get("code")), str(prob.get("message"))[:300])
        if problems:
            continue
        (historical if is_historical(rec, as_of, cfg.get("historical_cutoff_days", 365)) else current).append(item)

    inputs = [{"path": f"verified/{p.name}", "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
              for p in sorted((HERE / "verified").glob("*.json"))]
    inputs.append({"path": "sources.json", "sha256": hashlib.sha256((HERE / "sources.json").read_bytes()).hexdigest()
                   if (HERE / "sources.json").exists() else None})

    def package(items, name):
        items = sorted(items, key=lambda x: x["id"])
        digest = hashlib.sha256(json.dumps(items, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        return {"schema_version": "civic-v1", "city": "astana",
                "slice": {"name": name, "version": cfg.get("package_version"), "demo": False,
                          "count": len(items), "content_sha256": digest,
                          "builder": "data/civic/astana/round12-verified/tools/r12.py", "inputs": inputs,
                          "source": cfg.get("package_source") + ("-historical" if name.endswith("historical") else ""),
                          "as_of": cfg.get("as_of"),
                          "notes": "Только записи из verified/ (каждое значение — дословная выдержка из полученного источника). Импорт создаёт черновики."},
                "items": items}

    out = {"package.civic-v1.json": package(current, "r05-astana-r12-verified"),
           "historical.civic-v1.json": package(historical, "r05-astana-r12-verified-historical")}
    if write:
        for name, value in out.items():
            write_json(HERE / name, value)
    return out, issues.items


def civic_issues(packages: dict) -> tuple[list, dict]:
    """Проверка собранных объектов валидатором R05 (profile real) и правилами R02, если они есть."""
    cfg = config()
    found, ran = [], {"r05_civic_v1_real": "NOT_RUN", "r02_validate_content": "NOT_RUN"}
    validator = base_validator()
    validate_content, ValidationError = r02_validate_content()
    for name, pkg in packages.items():
        for item in pkg["items"]:
            if validator is not None:
                ran["r05_civic_v1_real"] = "RUN"
                for issue in validator.validate_object(item, profile="real", as_of=cfg.get("as_of")):
                    if issue.get("severity", "error") == "error":
                        found.append({"where": f"{name}:{item['id']}", **issue})
            if validate_content is not None:
                ran["r02_validate_content"] = "RUN"
                try:
                    validate_content({k: v for k, v in item.items() if k != "id"}, today=parse_date(cfg.get("as_of")))
                except ValidationError as exc:
                    found.append({"where": f"{name}:{item['id']}", "code": "r02_validation", "message": json.dumps(exc.fields, ensure_ascii=False)})
    return found, ran


# ---------------------------------------------------------------- verify
def cmd_verify(args) -> int:
    draft_path = Path(args.draft)
    rec = load_json(draft_path)
    reg_path = HERE / "sources.json"
    reg = load_json(reg_path)
    issues = Issues()
    sources = check_sources(reg, issues)
    validator = base_validator()
    check_record(rec, sources, issues, verified=False, pii=getattr(validator, "find_pii", None))
    if issues.errors:
        print(dump_json({"status": "rejected", "issues": issues.errors}))
        return 1
    if not args.retrieved_at or not TS_RE.match(args.retrieved_at):
        print("--retrieved-at YYYY-MM-DDThh:mm:ssZ обязателен", file=sys.stderr)
        return 2
    texts = {}
    for item in args.text or []:
        sid, _, file = item.partition("=")
        raw = Path(file).read_bytes()
        texts[sid] = (hashlib.sha256(raw).hexdigest(), norm_text(page_text(raw.decode("utf-8", "replace"))))
    published = dict(item.partition("=")[::2] for item in args.published_on or [])
    missing = []
    for claim in rec["claims"]:
        sid = claim["source_id"]
        if sid not in texts:
            missing.append({"field": claim["field"], "source_id": sid, "problem": "нет текста источника (--text)"})
        elif not quote_found(claim["quote"], texts[sid][1]):
            missing.append({"field": claim["field"], "source_id": sid, "problem": "выдержка не найдена дословно",
                            "quote": claim["quote"]})
    for sid, date in published.items():
        if parse_date(date) is None:
            missing.append({"source_id": sid, "problem": "--published-on не YYYY-MM-DD"})
    if missing:
        print(dump_json({"status": "not_verified", "problems": missing}))
        return 1
    used = sorted({c["source_id"] for c in rec["claims"]})
    by_id = {s["id"]: s for s in reg["sources"]}
    conflicts = []
    for sid in used:
        src = by_id[sid]
        if src.get("access_status") == "fetched":
            # Источник уже подтверждал другие записи: другой текст или другая дата публикации их обесценили бы.
            if src.get("content_sha256") != texts[sid][0]:
                conflicts.append({"source_id": sid, "problem": "текст отличается от уже проверенного (sha256): "
                                  "сохраните прежнюю версию или перепроверьте все записи этого источника"})
            if sid in published and src.get("published_on") not in (None, published[sid]):
                conflicts.append({"source_id": sid, "problem": "дата публикации отличается от уже записанной"})
    if conflicts:
        print(dump_json({"status": "not_verified", "problems": conflicts}))
        return 1
    for sid in used:
        src = by_id[sid]
        if src.get("access_status") != "fetched":
            src.update({"access_status": "fetched", "retrieved_at": args.retrieved_at,
                        "content_sha256": texts[sid][0], "fetch_method": args.method})
            src.setdefault("access_attempts", []).append(
                {"at": args.retrieved_at, "method": args.method, "outcome": "fetched",
                 "detail": "все выдержки записи найдены целыми словами; текст страницы в Git не хранится"})
        if sid in published:
            src["published_on"], src["published_on_basis"] = published[sid], "page"
        elif src.get("published_on_basis") not in ("page", "url"):
            src["published_on"], src["published_on_basis"] = None, None   # дата без основания не используется
    rec["verification"] = {"method": "quote_match_saved_text", "verified_at": args.retrieved_at,
                           "claims_digest": claims_digest(rec),
                           "sources": {sid: {"content_sha256": by_id[sid]["content_sha256"],
                                             "published_on": by_id[sid].get("published_on"),
                                             "retrieved_at": by_id[sid].get("retrieved_at")} for sid in used}}
    # actual_end не может быть позже публикации источника, сообщившего о нём
    for claim in rec["claims"]:
        if claim["field"] == "schedule.actual_end":
            pub = parse_date(by_id[claim["source_id"]].get("published_on"))
            if pub is None or parse_date(claim["value"]) > pub:
                print(dump_json({"status": "not_verified", "problems": [
                    {"field": "schedule.actual_end", "problem": "дата позже публикации или публикация без даты: это ожидание, не факт"}]}))
                return 1
    write_json(reg_path, reg)
    write_json(HERE / "verified" / f"{rec['id']}.json", rec)
    if draft_path.resolve().parent == (HERE / "drafts").resolve():
        draft_path.unlink()
    print(dump_json({"status": "verified", "id": rec["id"], "sources": used}))
    return 0


# ---------------------------------------------------------------- geocode (OSM snapshot)
STREET_WORDS = {"улица", "ул", "проспект", "пр", "пр-т", "даңғылы", "дангылы", "көшесі", "кошеси", "шоссе",
                "тас", "жолы", "бульвар", "б-р", "переулок", "пер", "тупик", "проезд", "набережная",
                "микрорайон", "мкр", "street", "avenue", "и", "улиц", "улицы", "пересечение", "пересечении"}
NAME_KEYS = ("name", "name:ru", "name:kk", "alt_name", "old_name", "official_name", "name:en")


KAZAKH_TO_RU = str.maketrans({"ә": "а", "ғ": "г", "қ": "к", "ң": "н", "ө": "о", "ұ": "у", "ү": "у", "һ": "х", "і": "и"})


def _words(name: str) -> list:
    words = re.findall(r"[^\W\d_]+|\d+", norm_text(name).translate(KAZAKH_TO_RU))
    return [w for w in words if w not in STREET_WORDS and (len(w) >= 3 or w.isdigit())]


def _same_word(q: str, w: str) -> bool:
    """Одно слово с точностью до падежного окончания: «Бейсековой» = «Бейсекова», но не «Бейсекбаева»."""
    if q.isdigit() or w.isdigit():
        return q == w
    common = 0
    for a, b in zip(q, w):
        if a != b:
            break
        common += 1
    # Падежное окончание — до 2 букв; и не меньше 3/4 более короткого слова («Алматы» ≠ «Алмалы»).
    return common >= max(4, max(len(q), len(w)) - 2) and common * 4 >= 3 * min(len(q), len(w))


def name_matches(query: str, name: str) -> bool:
    want, have = _words(query), _words(name)
    return bool(want) and all(any(_same_word(q, w) for w in have) for q in want)


class Osm:
    def __init__(self, path: Path):
        data = json.load(gzip.open(path))
        self.nodes = {e["id"]: (e["lon"], e["lat"]) for e in data["elements"] if e["type"] == "node"}
        self.ways = [e for e in data["elements"] if e["type"] == "way"]

    def street(self, query: str) -> list:
        hits = []
        for way in self.ways:
            tags = way.get("tags", {})
            if any(name_matches(query, tags[k]) for k in NAME_KEYS if k in tags):
                hits.append(way)
        return hits

    def length_m(self, a, b) -> float:
        (x1, y1), (x2, y2) = self.nodes[a], self.nodes[b]
        k = math.cos(math.radians((y1 + y2) / 2))
        return math.hypot((x2 - x1) * 111320 * k, (y2 - y1) * 110540)

    def graph(self, ways: list) -> dict:
        adj: dict[int, dict] = {}
        for way in ways:
            nds = [n for n in way["nodes"] if n in self.nodes]
            for a, b in zip(nds, nds[1:]):
                d = self.length_m(a, b)
                adj.setdefault(a, {})[b] = d
                adj.setdefault(b, {})[a] = d
        return adj

    @staticmethod
    def components(adj: dict) -> list[set]:
        seen, comps = set(), []
        for start in adj:
            if start in seen:
                continue
            comp, stack = set(), [start]
            while stack:
                n = stack.pop()
                if n in comp:
                    continue
                comp.add(n)
                stack.extend(m for m in adj[n] if m not in comp)
            seen |= comp
            comps.append(comp)
        return comps

    @staticmethod
    def shortest(adj: dict, src: int, dst: int) -> list | None:
        import heapq
        dist, prev, heap = {src: 0.0}, {}, [(0.0, src)]
        while heap:
            d, n = heapq.heappop(heap)
            if n == dst:
                path = [n]
                while n in prev:
                    n = prev[n]
                    path.append(n)
                return path[::-1]
            if d > dist.get(n, math.inf):
                continue
            for m, w in adj[n].items():
                if d + w < dist.get(m, math.inf):
                    dist[m], prev[m] = d + w, n
                    heapq.heappush(heap, (d + w, m))
        return None

    def coords(self, path: list) -> list:
        return [[round(self.nodes[n][0], 6), round(self.nodes[n][1], 6)] for n in path]


def _names(ways: list) -> list:
    return sorted({w.get("tags", {}).get("name", "?") for w in ways})


def geocode(osm: Osm, street: str, cross: str | None = None, frm: str | None = None, to: str | None = None,
            snapshot: str = "2026-05-06") -> dict:
    """Предложение геометрии по открытому OSM-снимку. Никогда не «центр района»."""
    result = {"query": {"street": street, "cross": cross, "from": frm, "to": to}, "geometry": None,
              "geometry_precision": "unknown", "geometry_basis": None, "ambiguous": False, "notes": []}
    main = osm.street(street)
    result["matched_names"] = _names(main)
    if not main:
        result["notes"].append("улица не найдена в OSM-снимке: geometry null")
        return result
    adj = osm.graph(main)
    comps = osm.components(adj)

    def crossing_nodes(other_query):
        other = osm.street(other_query)
        other_nodes = {n for w in other for n in w["nodes"] if n in osm.nodes}
        shared = [n for n in adj if n in other_nodes]
        if shared or not other_nodes:
            return shared, _names(other)
        # Развязки/съезды: общего узла может не быть — ближайшая пара узлов не дальше 60 м.
        best = min(((osm.length_m(a, b), a) for a in adj for b in other_nodes
                    if abs(osm.nodes[a][0] - osm.nodes[b][0]) < 0.002 and abs(osm.nodes[a][1] - osm.nodes[b][1]) < 0.002),
                   default=None)
        if best and best[0] <= 60:
            result["notes"].append(f"общего узла нет; ближайшие узлы улиц в {round(best[0])} м")
            return [best[1]], _names(other)
        return [], _names(other)

    if cross and not (frm or to):
        nodes, other_names = crossing_nodes(cross)
        result["matched_cross_names"] = other_names
        if not nodes:
            result["notes"].append("общих узлов улиц нет в снимке: geometry null")
            return result
        clusters = []
        for n in nodes:
            for cl in clusters:
                if osm.length_m(n, cl[0]) < 250:
                    cl.append(n)
                    break
            else:
                clusters.append([n])
        if len(clusters) > 1:
            result["ambiguous"] = True
            result["notes"].append(f"{len(clusters)} разнесённых пересечения: нужен выбор человека")
            result["candidates"] = [osm.coords(cl[:1])[0] for cl in clusters]
            return result
        cl = clusters[0]
        lon = sum(osm.nodes[n][0] for n in cl) / len(cl)
        lat = sum(osm.nodes[n][1] for n in cl) / len(cl)
        result.update(geometry={"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                      geometry_precision="approximate",
                      geometry_basis=f"OSM: пересечение «{result['matched_names'][0]}» и «{other_names[0]}», "
                                     f"узлы {','.join(map(str, sorted(cl)[:6]))}, снимок {snapshot}, ODbL")
        return result
    if frm and to:
        a_nodes, a_names = crossing_nodes(frm)
        b_nodes, b_names = crossing_nodes(to)
        if not a_nodes or not b_nodes:
            result["notes"].append("границы участка не найдены на улице: geometry null")
            return result
        best = None
        for a in a_nodes:
            for b in b_nodes:
                path = osm.shortest(adj, a, b)
                if path and (best is None or len(path) < len(best)):
                    best = path
        if not best or len(best) < 2:
            result["notes"].append("участок между границами не связан в снимке: geometry null")
            return result
        result.update(geometry={"type": "LineString", "coordinates": osm.coords(best)},
                      geometry_precision="approximate",
                      geometry_basis=f"OSM: «{result['matched_names'][0]}» от «{a_names[0]}» до «{b_names[0]}», "
                                     f"{len(best)} узлов, снимок {snapshot}, ODbL")
        return result
    # Вся улица: только если это одна связная цепочка; одноимённые разнесённые улицы не склеиваем.
    big = [c for c in comps if len(c) >= 2]
    if len(big) != 1:
        result["ambiguous"] = True
        result["notes"].append(f"{len(big)} несвязанных участков с таким названием: нужен участок или выбор человека")
        return result
    comp = big[0]
    start = next(iter(comp))
    far = max(comp, key=lambda n: osm.length_m(start, n))
    other_end = max(comp, key=lambda n: osm.length_m(far, n))
    path = osm.shortest(adj, far, other_end)
    result.update(geometry={"type": "LineString", "coordinates": osm.coords(path)},
                  geometry_precision="approximate",
                  geometry_basis=f"OSM: ось «{result['matched_names'][0]}» (крайние точки связной цепочки; "
                                 f"разделённые проезжие части упрощены), снимок {snapshot}, ODbL")
    return result


# ---------------------------------------------------------------- summary
def summary() -> dict:
    cfg = config()
    cands = (load_json(HERE / "candidates.json", {}) or {}).get("candidates") or []
    packages, _ = build(write=False)
    current = packages["package.civic-v1.json"]["items"]
    hist = packages["historical.civic-v1.json"]["items"]
    to_verify = [c for c in cands if c.get("decision") == "to_verify"]
    by = lambda items, key: {k: sum(1 for i in items if i.get(key) == k) for k in sorted({i.get(key) for i in items})}
    return {
        "schema": "r05-r12-summary-v1", "as_of": cfg.get("as_of"),
        "confirmed_current": len(current),
        "confirmed_historical": len(hist),
        "unverified_candidates": len(to_verify),
        "rejected_candidates": sum(1 for c in cands if c.get("decision") == "rejected"),
        "duplicate_candidates": sum(1 for c in cands if c.get("decision") == "duplicate"),
        "without_geometry": {
            "confirmed": sum(1 for i in current + hist if i["geometry"] is None),
            "unverified_candidates": sum(1 for c in to_verify if not (c.get("geocode") or {}).get("geometry")),
        },
        "unverified_by_kind": by(to_verify, "kind"),
        "unverified_by_freshness": by(to_verify, "freshness"),
        "note": "confirmed = каждое значение подтверждено дословной выдержкой из полученного текста источника; "
                "unverified = найдено поиском, страница источника в этой среде не открыта.",
    }


# ---------------------------------------------------------------- verification sheet
def verify_sheet() -> str:
    """Лист проверки для человека: что открыть и что выписать дословно."""
    reg = {s["id"]: s for s in (load_json(HERE / "sources.json", {}) or {}).get("sources") or []}
    cands = [c for c in (load_json(HERE / "candidates.json", {}) or {}).get("candidates") or []
             if c.get("decision") == "to_verify"]
    order = {"official_gov": 0, "city_utility_or_operator": 1, "state_media": 2, "city_media": 3, "news": 4, "other": 5}
    fresh = {"current_or_upcoming_2026": 0, "past_2026": 1, "unknown": 2, "historical_before_2026": 3}
    cands.sort(key=lambda c: (fresh.get(c.get("freshness"), 9),
                              order.get(reg.get((c.get("source_ids") or [""])[0], {}).get("publisher_kind"), 9), c["id"]))
    lines = ["# Лист проверки кандидатов R05 (раунд 12)", "",
             f"Срез: {config().get('as_of')}. Кандидатов к проверке: {len(cands)}. Все найдены поиском; страницы в среде R05 "
             "не открывались (сеть закрыта). Подсказки «пересказ поиска» — ненадёжны, проверять по самой странице.", "",
             "Порядок: открыть ссылку → сохранить текст страницы вне репозитория → заполнить drafts/<id>.json "
             "(дословные выдержки ≤ 300 символов) → `r12.py verify`.", ""]
    for i, cand in enumerate(cands, 1):
        lines.append(f"## {i}. {cand['title_as_listed']}")
        lines.append(f"- id кандидата: `{cand['id']}`; тип: {cand['kind']}; актуальность по выдаче: {cand.get('freshness')}")
        for sid in cand.get("source_ids") or []:
            src = reg.get(sid, {})
            lines.append(f"- источник `{sid}` ({src.get('publisher') or 'издатель не определён'}, {src.get('publisher_kind')}): {src.get('url')}")
        if cand.get("location_text"):
            lines.append(f"- место по выдаче: {cand['location_text']}")
        if cand.get("date_hint"):
            lines.append(f"- дата-подсказка: {cand['date_hint']} (происхождение: {cand.get('date_hint_origin')})")
        for hint in cand.get("hints") or []:
            origin = {"search_title": "заголовок", "url": "URL", "search_summary": "пересказ поиска"}.get(hint["origin"], hint["origin"])
            lines.append(f"  - подсказка [{origin}] {hint['field']}: {hint['text']}")
        geo = cand.get("geocode") or {}
        if geo.get("geometry"):
            lines.append(f"- геометрия-предложение: {geo['geometry']['type']}, {geo.get('geometry_basis')}")
        if cand.get("contradictions"):
            lines.append(f"- противоречия: {cand['contradictions']}")
        lines.append("- проверить: " + "; ".join(cand.get("verify_checklist") or []))
        lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- fetch (where the network allows it)
def cmd_fetch(args) -> int:
    import urllib.request
    reg_path = HERE / "sources.json"
    reg = load_json(reg_path)
    src = next((s for s in reg["sources"] if s["id"] == args.source_id), None)
    if src is None:
        print(f"нет источника {args.source_id}", file=sys.stderr)
        return 2
    out = Path(args.out).resolve()
    if REPO in out.parents or out == REPO:
        print("--out должен быть вне репозитория: полный текст статей в Git не хранится", file=sys.stderr)
        return 2
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    attempt = {"at": now, "method": "r12.py fetch (urllib GET via environment proxy)"}
    try:
        req = urllib.request.Request(src["url"], headers={"User-Agent": "GOV_DIPLOME-R05-verifier/1 (study project)"})
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            body = resp.read(5 * 1024 * 1024)
        out.mkdir(parents=True, exist_ok=True)
        file = out / f"{src['id']}.html"
        file.write_bytes(body)
        attempt.update(outcome="downloaded", detail=f"{len(body)} байт, sha256 {hashlib.sha256(body).hexdigest()}; "
                                                    "fetched станет только после verify")
        print(str(file))
        code = 0
    except Exception as exc:  # сеть закрыта/недоступна — фиксируем, не выдумываем
        attempt.update(outcome="failed", detail=f"{type(exc).__name__}: {str(exc)[:200]}")
        print(dump_json(attempt), file=sys.stderr)
        code = 1
    src.setdefault("access_attempts", []).append(attempt)
    write_json(reg_path, reg)
    return code


# ---------------------------------------------------------------- CLI
def cmd_check(args) -> int:
    issues = Issues()
    sources = check_sources(load_json(HERE / "sources.json", {}), issues)
    check_candidates(load_json(HERE / "candidates.json", {}), sources, issues)
    validator = base_validator()
    pii = getattr(validator, "find_pii", None)
    for rec in load_records("drafts"):
        check_record(rec, sources, issues, verified=False, pii=pii)
    for rec in load_records("verified"):
        check_record(rec, sources, issues, verified=True, pii=pii)
    packages, _ = build(write=False)
    civic, ran = civic_issues(packages)
    stale = []
    for name, value in packages.items():
        on_disk = (HERE / name).read_text(encoding="utf-8") if (HERE / name).exists() else None
        if on_disk != dump_json(value):
            stale.append(name)
    if load_records("verified") and "NOT_RUN" in ran.values():
        issues.add("check", "validator_not_run", "есть подтверждённые записи, но валидаторы R05/R02 не запускались")
    report = {"issues": issues.items, "civic_issues": civic, "validators": ran, "stale_packages": stale}
    print(dump_json(report))
    return 1 if issues.errors or civic or stale else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    v = sub.add_parser("verify")
    v.add_argument("draft")
    v.add_argument("--text", action="append", help="SRC_ID=файл с текстом/HTML страницы (вне репозитория)")
    v.add_argument("--published-on", action="append", help="SRC_ID=YYYY-MM-DD (дата на самой странице)")
    v.add_argument("--retrieved-at", required=True)
    v.add_argument("--method", choices=("human_saved_text", "agent_http"), default="human_saved_text")
    b = sub.add_parser("build")
    b.add_argument("--check", action="store_true", help="не писать файлы, exit 1 если устарели")
    g = sub.add_parser("geocode")
    g.add_argument("--street", required=True)
    g.add_argument("--cross")
    g.add_argument("--from", dest="frm")
    g.add_argument("--to")
    g.add_argument("--osm", default=None)
    f = sub.add_parser("fetch")
    f.add_argument("source_id")
    f.add_argument("--out", required=True)
    f.add_argument("--timeout", type=float, default=20)
    sub.add_parser("summary")
    sh = sub.add_parser("sheet")
    sh.add_argument("--out", default=None, help="файл Markdown (по умолчанию — stdout)")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "build":
        packages, problems = build(write=not args.check)
        errors = [p for p in problems if p["severity"] == "error"]
        if args.check:
            stale = [n for n, v in packages.items()
                     if not (HERE / n).exists() or (HERE / n).read_text(encoding="utf-8") != dump_json(v)]
            print(dump_json({"stale": stale, "issues": errors}))
            return 1 if stale or errors else 0
        write_json(HERE / "summary.json", summary())
        print(dump_json({n: len(v["items"]) for n, v in packages.items()} | {"issues": errors}))
        return 1 if errors else 0
    if args.cmd == "geocode":
        cfg = config()
        osm = Osm(Path(args.osm) if args.osm else REPO / cfg.get("osm_snapshot", ""))
        print(dump_json(geocode(osm, args.street, args.cross, args.frm, args.to,
                                (cfg.get("osm_snapshot_at") or "")[:10])))
        return 0
    if args.cmd == "fetch":
        return cmd_fetch(args)
    if args.cmd == "summary":
        print(dump_json(summary()))
        return 0
    if args.cmd == "sheet":
        text = verify_sheet()
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
