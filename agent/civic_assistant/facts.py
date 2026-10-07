"""Каталог проверенных фактов для помощника civic-v1 (роль R09, раунд 11).

Контекст строит только сервер из публичного DTO объекта, публичной истории и
результата сценарного движка. Клиент не передаёт фактов: всё, что не попало в
allowlist контракта, отбрасывается, а draft/archived для публичной аудитории
отклоняются целиком. Неизвестное значение остаётся None (known=False), а не
нулём, сегодняшней датой или словом «проверено».

Подход перенят из agent/school_ai.py (снимок b2cb2e0): модель видит только ID и
подписи фактов, но не значения; числа и даты в ответ выводит код.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
import math
import re

FACTS_VERSION = "civic-assistant-facts-v1"
CONTEXT_SCHEMA = "civic-assistant-context-v1"
OBJECT_SCHEMA = "civic-v1"

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,120}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏  ‪-‮⁦-⁩]")

KINDS = ("construction", "roadworks", "landscaping", "event")
STATUSES = ("planned", "in_progress", "completed", "cancelled", "unknown")
PUBLICATIONS = ("draft", "published", "archived")
EVIDENCE_TYPES = ("observed", "derived", "hypothesis", "synthetic")
PRECISIONS = ("source", "approximate", "unknown")
BUDGET_BASES = ("planned", "contract", "spent", "unknown")
ACCESS_STATUSES = ("fetched", "not_fetched", "unavailable")
SCHEDULE_FIELDS = ("planned_start", "original_planned_end", "current_planned_end", "actual_end")

# Allowlist публичного DTO из CONTRACT.txt раздел 1. Всё прочее (internal_notes,
# password_hash, контакты автора, session/token, служебный аудит) не попадает в контекст.
PUBLIC_OBJECT_FIELDS = (
    "schema_version", "id", "city", "kind", "title", "description", "status", "publication",
    "geometry", "geometry_precision", "schedule", "budget", "responsible", "evidence_type",
    "source_refs", "evidence_notes", "updated_at", "revision",
)
PUBLIC_HISTORY_FIELDS = ("id", "object_id", "revision", "at", "changed_fields", "reason", "public_actor_label")
SOURCE_REF_FIELDS = ("id", "url", "publisher", "published_on", "retrieved_at", "access_status", "license", "fields")

MAX_TEXT = 600
MAX_REASON = 300
MAX_HISTORY = 20
MAX_SOURCES = 12


class ContextError(ValueError):
    """Контекст нельзя использовать для ответа (не публичный, другой город, повреждён)."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def clean_text(value, limit: int = MAX_TEXT) -> str | None:
    """Plain text без управляющих/bidi-символов; длинный текст обрезается с пометкой."""
    if not isinstance(value, str):
        return None
    text = _CONTROL.sub("", value)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def parse_day(value) -> date | None:
    """Строго YYYY-MM-DD. date.fromisoformat в 3.11+ принимает и другие формы — их не берём."""
    if not isinstance(value, str) or not DATE_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _finite_amount(value) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _enum(value, allowed, default="unknown"):
    return value if value in allowed else default


def _fact(fid, label_key, value, kind, origin, *, source_ids=(), meta=None):
    fact = {
        "id": fid,
        "label_key": label_key,
        "value": value,
        "known": value is not None,
        "kind": kind,
        "origin": origin,
        "source_ids": sorted(set(source_ids)),
    }
    if meta:
        fact["meta"] = meta
    return fact


def public_object_view(item: dict, *, audience: str = "public") -> tuple[dict, list[str]]:
    """Проекция объекта по allowlist; draft/archived недоступны публичной аудитории."""
    warnings: list[str] = []
    if not isinstance(item, dict):
        raise ContextError("object_invalid", "объект не JSON-объект")
    if item.get("schema_version") != OBJECT_SCHEMA:
        raise ContextError("object_schema", "ожидается civic-v1")
    if item.get("city") != "astana":
        raise ContextError("object_city", "раунд 11 — только Астана")
    oid = item.get("id")
    if not isinstance(oid, str) or not ID_RE.match(oid):
        raise ContextError("object_id", "недопустимый id")
    publication = item.get("publication")
    if publication not in PUBLICATIONS:
        raise ContextError("object_publication", "неизвестное состояние публикации")
    if audience == "public" and publication != "published":
        # Помощник не делает обход к draft/archived: для жителя объекта нет.
        raise ContextError("object_not_public", "объект не опубликован")
    view = {k: item.get(k) for k in PUBLIC_OBJECT_FIELDS}
    dropped = sorted(set(item) - set(PUBLIC_OBJECT_FIELDS))
    if dropped:
        warnings.append("dropped_non_public_fields")
    return view, warnings


def _sources(view: dict, warnings: list[str]) -> dict[str, dict]:
    refs = view.get("source_refs")
    out: dict[str, dict] = {}
    if refs is None:
        return out
    if not isinstance(refs, list):
        warnings.append("source_refs_invalid")
        return out
    for ref in refs[:MAX_SOURCES]:
        if not isinstance(ref, dict) or not isinstance(ref.get("id"), str) or not ID_RE.match(ref["id"]):
            warnings.append("source_ref_skipped")
            continue
        url = ref.get("url")
        url = url if isinstance(url, str) and re.match(r"^https?://[^\s<>\"']{1,500}$", url) else None
        fields = ref.get("fields") if isinstance(ref.get("fields"), list) else []
        out[ref["id"]] = {
            "id": ref["id"],
            "url": url,
            "publisher": clean_text(ref.get("publisher"), 160),
            "published_on": ref.get("published_on") if parse_day(ref.get("published_on")) else None,
            "retrieved_at": clean_text(ref.get("retrieved_at"), 40),
            "access_status": _enum(ref.get("access_status"), ACCESS_STATUSES, None),
            "license": clean_text(ref.get("license"), 120),
            "fields": [f for f in fields if isinstance(f, str) and len(f) <= 80][:40],
        }
    if isinstance(refs, list) and len(refs) > MAX_SOURCES:
        warnings.append("source_refs_truncated")
    return out


def _supporting(sources: dict[str, dict], path: str) -> list[str]:
    """Источник поддерживает путь, если в его fields указан сам путь или его родитель."""
    found = []
    for sid, ref in sources.items():
        for field in ref["fields"]:
            if path == field or path.startswith(field + "."):
                found.append(sid)
                break
    return found


def object_facts(view: dict, warnings: list[str]) -> tuple[list[dict], dict[str, dict]]:
    sources = _sources(view, warnings)
    sup = lambda path: _supporting(sources, path)  # noqa: E731
    facts = [
        _fact("object.title", "title", clean_text(view.get("title"), 200), "text", "object", source_ids=sup("title")),
        _fact("object.kind", "kind", view.get("kind") if view.get("kind") in KINDS else None, "enum", "object"),
        _fact("object.description", "description", clean_text(view.get("description")), "text", "object",
              source_ids=sup("description")),
        _fact("object.status", "status", _enum(view.get("status"), STATUSES), "enum", "object",
              source_ids=sup("status")),
        _fact("object.evidence_type", "evidence_type",
              view.get("evidence_type") if view.get("evidence_type") in EVIDENCE_TYPES else None, "enum", "object"),
        _fact("object.geometry_precision", "geometry_precision",
              _enum(view.get("geometry_precision"), PRECISIONS), "enum", "object"),
        _fact("object.geometry_type", "geometry_type",
              view["geometry"].get("type") if isinstance(view.get("geometry"), dict)
              and view["geometry"].get("type") in ("Point", "LineString", "Polygon") else None, "enum", "object",
              source_ids=sup("geometry")),
        _fact("object.evidence_notes", "evidence_notes", clean_text(view.get("evidence_notes"), 400), "text", "object"),
        _fact("object.updated_at", "updated_at", clean_text(view.get("updated_at"), 40), "timestamp", "object"),
        _fact("object.revision", "revision",
              view.get("revision") if isinstance(view.get("revision"), int) and not isinstance(view.get("revision"), bool)
              and view["revision"] >= 1 else None, "count", "object"),
    ]
    if facts[3]["value"] == "unknown" and view.get("status") != "unknown":
        warnings.append("status_invalid")

    schedule = view.get("schedule") if isinstance(view.get("schedule"), dict) else {}
    days = {}
    for name in SCHEDULE_FIELDS:
        raw = schedule.get(name)
        day = parse_day(raw)
        if raw is not None and day is None:
            warnings.append("invalid_date:schedule." + name)
        days[name] = day
        facts.append(_fact("schedule." + name, name, day.isoformat() if day else None, "date", "object",
                           source_ids=sup("schedule." + name)))
    shift = None
    if days["original_planned_end"] and days["current_planned_end"]:
        shift = (days["current_planned_end"] - days["original_planned_end"]).days
    facts.append(_fact("schedule.shift_days", "shift_days", shift, "days", "derived",
                       meta={"from": ["schedule.original_planned_end", "schedule.current_planned_end"]}))

    budget = view.get("budget") if isinstance(view.get("budget"), dict) else {}
    amount = _finite_amount(budget.get("amount_kzt"))
    if budget.get("amount_kzt") is not None and amount is None:
        warnings.append("invalid_amount:budget.amount_kzt")
    basis = _enum(budget.get("basis"), BUDGET_BASES)
    bsrc = budget.get("source_id") if isinstance(budget.get("source_id"), str) and budget.get("source_id") in sources else None
    if budget.get("source_id") is not None and bsrc is None:
        warnings.append("budget_source_not_in_refs")
    amount_sources = sup("budget.amount_kzt") + ([bsrc] if bsrc else [])
    facts += [
        _fact("budget.amount_kzt", "amount_kzt", amount, "money", "object", source_ids=amount_sources),
        _fact("budget.basis", "basis", basis, "enum", "object"),
        _fact("budget.source_id", "budget_source", bsrc, "source_ref", "object"),
    ]
    resp = view.get("responsible") if isinstance(view.get("responsible"), dict) else {}
    facts += [
        _fact("responsible.organization", "organization", clean_text(resp.get("organization"), 200), "text", "object",
              source_ids=sup("responsible.organization")),
        _fact("responsible.public_contact", "public_contact", clean_text(resp.get("public_contact"), 200), "text",
              "object", source_ids=sup("responsible.public_contact")),
    ]
    for sid, ref in sources.items():
        facts.append(_fact("source." + sid, "source", ref, "source_ref", "object"))
    return facts, sources


def history_facts(history, object_id: str, warnings: list[str]) -> list[dict]:
    """Только публичная история этого объекта; чужие записи и служебные поля отбрасываются."""
    if history is None:
        return []
    if not isinstance(history, list):
        warnings.append("history_invalid")
        return []
    entries = []
    for h in history:
        if not isinstance(h, dict) or h.get("object_id") != object_id:
            warnings.append("history_entry_skipped")
            continue
        rev = h.get("revision")
        if not isinstance(rev, int) or isinstance(rev, bool) or rev < 1:
            warnings.append("history_entry_skipped")
            continue
        changed = h.get("changed_fields") if isinstance(h.get("changed_fields"), list) else []
        entries.append({
            "revision": rev,
            "at": clean_text(h.get("at"), 40),
            "changed_fields": [c for c in changed if isinstance(c, str) and len(c) <= 80][:30],
            "reason": clean_text(h.get("reason"), MAX_REASON),
            "public_actor_label": clean_text(h.get("public_actor_label"), 80),
        })
    entries.sort(key=lambda e: e["revision"])
    entries = entries[-MAX_HISTORY:]
    facts = []
    for e in entries:
        schedule_change = any(c == "schedule" or c.startswith("schedule.") for c in e["changed_fields"])
        facts.append(_fact(f"history.r{e['revision']}", "history_entry", e, "history", "history",
                           meta={"schedule_change": schedule_change}))
    return facts


def digest_of(payload) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_verified_context(item: dict | None = None, history=None, scenario: dict | None = None, *,
                           audience: str = "public", scenario_id: str | None = None) -> dict:
    """Серверная сборка контекста. Вход — уже публичный DTO/история/результат движка.

    audience="public" отклоняет draft/archived. Для редакторских черновиков
    помощник по объекту не нужен: extraction работает отдельно (extract.py).
    """
    if audience not in ("public", "staff"):
        raise ContextError("audience", "public|staff")
    warnings: list[str] = []
    facts: list[dict] = []
    meta = {"object_id": None, "evidence_type": None, "title": None, "kind": None}
    if item is not None:
        view, w = public_object_view(item, audience=audience)
        warnings += w
        ofacts, _ = object_facts(view, warnings)
        facts += ofacts
        facts += history_facts(history, view["id"], warnings)
        meta = {"object_id": view["id"], "evidence_type": view.get("evidence_type") if view.get("evidence_type")
                in EVIDENCE_TYPES else None, "title": clean_text(view.get("title"), 200), "kind": view.get("kind")}
    if scenario is not None:
        from agent.civic_assistant.scenario import scenario_facts  # локальный импорт: модуль сценариев опционален
        sfacts, w = scenario_facts(scenario, scenario_id=scenario_id)
        facts += sfacts
        warnings += w
    if item is None and scenario is None:
        raise ContextError("empty_context", "нет ни объекта, ни сценария")
    ids = [f["id"] for f in facts]
    if len(ids) != len(set(ids)):
        raise ContextError("duplicate_fact_id")
    body = {"facts": facts, "meta": meta, "scenario_id": scenario_id}
    return {
        "schema": CONTEXT_SCHEMA,
        "facts_version": FACTS_VERSION,
        "audience": audience,
        "object_id": meta["object_id"],
        "scenario_id": scenario_id,
        "meta": meta,
        "facts": facts,
        "warnings": sorted(set(warnings)),
        "digest": digest_of(body),
    }


def check_context(ctx) -> dict[str, dict]:
    """Проверка, что контекст собран build_verified_context и не изменён после сборки."""
    if not isinstance(ctx, dict) or ctx.get("schema") != CONTEXT_SCHEMA or ctx.get("facts_version") != FACTS_VERSION:
        raise ContextError("context_schema")
    facts = ctx.get("facts")
    if not isinstance(facts, list):
        raise ContextError("context_schema")
    body = {"facts": facts, "meta": ctx.get("meta"), "scenario_id": ctx.get("scenario_id")}
    if ctx.get("digest") != digest_of(body):
        raise ContextError("context_digest", "контекст изменён после серверной сборки")
    return {f["id"]: f for f in facts}
