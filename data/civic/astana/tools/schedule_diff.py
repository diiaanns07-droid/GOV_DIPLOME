"""Detect a changed published schedule between two saved versions of a source (R05 stretch).

Two steps, both offline:

1. ``snapshot`` - from a locally fetched page converted to plain text, keep only the
   date-bearing sentences (each <= 300 chars) plus the sha256 of the full text. The whole
   article is never stored, only short excerpts with their hash for re-verification.
2. ``diff``     - compare two snapshots of the same source (and optionally the current
   civic-v1 record) and emit a report of *proposed* schedule changes. Every proposal has
   ``requires_editor_confirmation: true``; nothing is applied automatically.

Rules kept from the contract/R05 brief:
* an expected end ("завершат до ...") never becomes actual_end;
* "завершены ..." is only a candidate actual_end, and only when the date is not after
  the snapshot's published_on;
* month-only or year-less dates are reported, not turned into a day;
* original_planned_end is never proposed for change once the record has one.

Russian-language heuristics only; Kazakh text is not parsed (reported as no dates).

  python3 -I schedule_diff.py snapshot --text page.txt --source-id src-x --url URL \
      --retrieved-at 2026-10-06T10:00:00Z [--published-on 2026-10-05] > snap.json
  python3 -I schedule_diff.py diff old.json new.json [--record objects.json --object-id ast-r05-x]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys

MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}
MONTH_RE = r"(январ[яеь]|феврал[яеь]|март[аеу]?|апрел[яеь]|ма[йяе]|июн[яеь]|июл[яеь]|август[аеу]?|сентябр[яеь]|октябр[яеь]|ноябр[яеь]|декабр[яеь])"
YEAR_RE = r"(20\d{2})"

# day-month[-year] ranges: "с 10 по 20 октября 2026", "с 10 октября по 2 ноября 2026"
RANGE_RE = re.compile(
    rf"\bс\s+(\d{{1,2}})(?:\s+{MONTH_RE})?(?:\s+{YEAR_RE})?\s*(?:года|г\.)?\s+(?:по|до)\s+(\d{{1,2}})\s+{MONTH_RE}(?:\s+{YEAR_RE})?",
    re.I)
DAY_RE = re.compile(rf"\b(\d{{1,2}})\s+{MONTH_RE}(?:\s+{YEAR_RE})?", re.I)
NUMERIC_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})\b")
ISO_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
MONTH_ONLY_RE = re.compile(rf"\b(?:в|до|к)\s+(?:конц[еу]\s+|начал[еу]\s+|середин[еу]\s+)?{MONTH_RE}(?:\s+{YEAR_RE})?", re.I)

ACTUAL_RE = re.compile(r"(заверш[её]н[аоы]?\b|завершили|завершила|завершил\b|сдан[аоы]?\b|открыт[аоы]?\b|"
                       r"введ[её]н[аоы]?\s+в\s+эксплуатаци|работы\s+выполнены|закончили)", re.I)
END_RE = re.compile(r"(заверш\w*|оконч\w*|сдач\w*|сдать|продл\w*|перенес\w*|продолж\w*\s+до|до\b|по\b|к\b|срок\w*)", re.I)
START_RE = re.compile(r"(начн\w*|начал\w*|старт\w*|приступ\w*|откро\w*\s+движени\w*|перекро\w*|\bс\b)", re.I)
SENTENCE_RE = re.compile(r"[^.!?\n]*?(?:\d|январ|феврал|март|апрел|ма[йяе]|июн|июл|август|сентябр|октябр|ноябр|декабр)[^.!?\n]*[.!?]?", re.I)

MAX_EXCERPT = 300


def _month(word: str) -> int:
    w = word.lower()
    for stem, n in MONTHS.items():
        if w.startswith(stem) and not (stem == "ма" and not re.match(r"ма[йяе]$", w)):
            return n
    raise ValueError(word)


def _mk(y, m, d):
    try:
        return dt.date(int(y), int(m), int(d)).isoformat()
    except (TypeError, ValueError):
        return None


def _role(before: str, after: str) -> str:
    window = before[-70:]
    if ACTUAL_RE.search(window) or ACTUAL_RE.search(after[:25]):
        return "reported_actual_end"
    if END_RE.search(window[-35:]):
        return "expected_end"
    if START_RE.search(window[-35:]):
        return "start"
    return "unclassified"


def extract_dates(text: str) -> list[dict]:
    """Find dates with precision and a role guess. Pure heuristics; output goes to an editor."""
    found, taken = [], []

    def add(s0, s1, **rec):
        if any(a < s1 and s0 < b for a, b in taken):
            return
        taken.append((s0, s1))
        rec.update(span=[s0, s1], raw=text[s0:s1])
        found.append(rec)

    for m in RANGE_RE.finditer(text):
        d1, mon1, y1, d2, mon2, y2 = m.groups()
        year = y2 or y1
        m2 = _month(mon2)
        m1 = _month(mon1) if mon1 else m2
        y_first = y1 or year
        prec = "day" if year else "day_without_year"
        add(m.start(), m.end(), role="range", precision=prec,
            start=_mk(y_first, m1, d1) if year else None, end=_mk(year, m2, d2) if year else None,
            context=text[max(0, m.start() - 70):m.start()])
    for rx, kind in ((ISO_RE, "iso"), (NUMERIC_RE, "numeric"), (DAY_RE, "day")):
        for m in rx.finditer(text):
            if kind == "iso":
                value, prec = _mk(*m.groups()), "day"
            elif kind == "numeric":
                d, mo, y = m.groups()
                value, prec = _mk(y, mo, d), "day"
            else:
                d, mon, y = m.groups()
                value = _mk(y, _month(mon), d) if y else None
                prec = "day" if y else "day_without_year"
            if kind != "day" and value is None:
                continue
            add(m.start(), m.end(), role=_role(text[:m.start()], text[m.end():]), precision=prec,
                value=value, context=text[max(0, m.start() - 70):m.start()])
    for m in MONTH_ONLY_RE.finditer(text):
        mon, y = m.groups()
        add(m.start(), m.end(), role=_role(text[:m.start() + 3], text[m.end():]), precision="month" if y else "month_without_year",
            value=None, month=f"{y}-{_month(mon):02d}" if y else None, context=text[max(0, m.start() - 70):m.start()])
    found.sort(key=lambda r: r["span"][0])
    return found


def make_snapshot(text: str, *, source_id: str, url: str, retrieved_at: str, published_on: str | None) -> dict:
    sentences = []
    for m in SENTENCE_RE.finditer(text):
        s = " ".join(m.group(0).split())
        if s and extract_dates(s):
            sentences.append(s[:MAX_EXCERPT])
    return {
        "schema": "r05-source-snapshot-v1",
        "source_id": source_id,
        "url": url,
        "retrieved_at": retrieved_at,
        "published_on": published_on,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "excerpts": sentences,
        "note": "Только предложения с датами (<=300 символов каждое) и хэш полного текста; статья целиком не хранится.",
    }


def schedule_signals(snapshot: dict) -> dict:
    """Collapse a snapshot's dates into candidate schedule values with their excerpts."""
    sig = {"start": [], "expected_end": [], "reported_actual_end": [], "period": [], "imprecise": [], "unclassified": []}
    for ex in snapshot.get("excerpts", []):
        for d in extract_dates(ex):
            entry = {"excerpt": ex, "raw": d["raw"], "precision": d["precision"]}
            if d["precision"] != "day":
                sig["imprecise"].append(dict(entry, role=d["role"], month=d.get("month")))
                continue
            if d["role"] == "range":
                # A period ("с 5 по 25 октября") may be a closure or an event, not the works themselves.
                sig["period"].append(dict(entry, value=f"{d['start']}/{d['end']}"))
            elif d["role"] in sig:
                sig[d["role"]].append(dict(entry, value=d["value"]))
    return sig


def _values(entries):
    return sorted({e["value"] for e in entries if e.get("value")})


def diff(old: dict, new: dict, record: dict | None = None) -> dict:
    if old.get("source_id") != new.get("source_id"):
        raise ValueError("snapshots belong to different sources")
    so, sn = schedule_signals(old), schedule_signals(new)
    findings = []
    sched = (record or {}).get("schedule") or {}

    def propose(kind, field, old_v, new_v, excerpts, note, extra=None):
        f = {"kind": kind, "field": field, "old": old_v, "new": new_v, "excerpts_new": excerpts[:3],
             "requires_editor_confirmation": True, "note": note}
        if extra:
            f.update(extra)
        findings.append(f)

    for role, field in (("start", "schedule.planned_start"), ("expected_end", "schedule.current_planned_end"),
                        ("period", None)):
        ov, nv = _values(so[role]), _values(sn[role])
        if ov == nv:
            pass
        elif role == "period":
            propose("period_changed", None, ov or None, nv or None, [e["excerpt"] for e in sn[role]],
                    "изменился период (ограничение движения или мероприятие); соотнести со сроками записи вручную")
            continue
        elif len(nv) > 1:
            propose("ambiguous", field, ov, nv, [e["excerpt"] for e in sn[role]],
                    "в новой версии несколько разных дат этой роли; выбрать вручную")
        else:
            note = "опубликованный срок изменился между версиями источника"
            if field == "schedule.current_planned_end":
                note += "; original_planned_end не меняется, при публикации нужна причина переноса"
            propose("changed" if ov and nv else ("added" if nv else "removed"), field,
                    ov[0] if len(ov) == 1 else (ov or None), nv[0] if nv else None,
                    [e["excerpt"] for e in sn[role]], note)
        if role != "period" and record is not None and len(nv) == 1 and sched.get(field.split(".")[1]) not in (None, nv[0]):
            propose("differs_from_record", field, sched.get(field.split(".")[1]), nv[0],
                    [e["excerpt"] for e in sn[role]], "значение в записи отличается от новой версии источника")

    pub = new.get("published_on")
    for e in sn["reported_actual_end"]:
        if e["value"] in _values(so["reported_actual_end"]):
            continue
        if pub and e["value"] > pub:
            propose("rejected_actual", "schedule.actual_end", None, e["value"], [e["excerpt"]],
                    "дата позже публикации источника: это не фактическое завершение")
        else:
            propose("candidate_actual", "schedule.actual_end", sched.get("actual_end"), e["value"], [e["excerpt"]],
                    "источник сообщает о завершении; status=completed и actual_end только после подтверждения редактором"
                    + ("" if pub else "; у версии нет published_on — проверить дату вручную"))
    for e in sn["imprecise"]:
        if e["excerpt"] not in [x["excerpt"] for x in so["imprecise"]]:
            propose("imprecise_date", None, None, None, [e["excerpt"]],
                    f"дата с точностью '{e['precision']}' ({e.get('month') or e['raw']}): в поле YYYY-MM-DD не переносится")
    if sched.get("original_planned_end") and any(f["field"] == "schedule.original_planned_end" for f in findings):
        raise AssertionError("original_planned_end must never be proposed")  # defensive: not produced above
    return {
        "schema": "r05-schedule-diff-v1",
        "source_id": new.get("source_id"),
        "url": new.get("url"),
        "old": {"retrieved_at": old.get("retrieved_at"), "published_on": old.get("published_on"),
                "text_sha256": old.get("text_sha256")},
        "new": {"retrieved_at": new.get("retrieved_at"), "published_on": new.get("published_on"),
                "text_sha256": new.get("text_sha256")},
        "content_changed": old.get("text_sha256") != new.get("text_sha256"),
        "record_id": (record or {}).get("id"),
        "findings": findings,
        "auto_applied": False,
        "editor_action": ("Нет изменений сроков." if not findings else
                          "Проверить каждую находку по источнику; изменения сроков вносить через редактор с причиной."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="R05 schedule change detection between two saved source versions")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--text", required=True)
    s.add_argument("--source-id", required=True)
    s.add_argument("--url", required=True)
    s.add_argument("--retrieved-at", required=True)
    s.add_argument("--published-on")
    d = sub.add_parser("diff")
    d.add_argument("old")
    d.add_argument("new")
    d.add_argument("--record", help="slice file or single civic object")
    d.add_argument("--object-id")
    args = ap.parse_args(argv)
    if args.cmd == "snapshot":
        with open(args.text, encoding="utf-8") as fh:
            text = fh.read()
        out = make_snapshot(text, source_id=args.source_id, url=args.url,
                            retrieved_at=args.retrieved_at, published_on=args.published_on)
    else:
        with open(args.old, encoding="utf-8") as fh:
            old = json.load(fh)
        with open(args.new, encoding="utf-8") as fh:
            new = json.load(fh)
        record = None
        if args.record:
            with open(args.record, encoding="utf-8") as fh:
                data = json.load(fh)
            items = data.get("items", [data]) if isinstance(data, dict) else data
            record = next((o for o in items if o.get("id") == args.object_id), None)
            if record is None:
                print(f"record {args.object_id!r} not found", file=sys.stderr)
                return 2
        out = diff(old, new, record)
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
