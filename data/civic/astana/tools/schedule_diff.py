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
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import civic_v1 as cv  # noqa: E402  (PII detection shared with the validator)

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

# Role cues are read only inside the clause that holds the date (text after the last , ; or ().
CLAUSE_CUT_RE = re.compile(r"[,;(]")
ACTUAL_RE = re.compile(r"(заверш[её]н[аоы]?\b|заверш[её]нн\w+|завершили|завершила|завершил\b|оконч[её]н\w*|окончили|"
                       r"сдан[аоы]?\b|сдали|открыт[аоы]?\b|открыли|введ[её]н[аоы]?\s+в\s+эксплуатаци|"
                       r"выполнен[аоы]?\b|закончили|законч[её]н\w*)", re.I)
NEG_ACTUAL_RE = re.compile(r"\bне\s+(?:был\w*\s+)?(?:заверш|оконч|сдан|сдал|открыт|выполн|законч)", re.I)
MODAL_RE = re.compile(r"\b(?:будет|будут|должн\w*|планир\w*|запланир\w*|ожида\w*|намеч\w*|предполага\w*)", re.I)
PERCENT_RE = re.compile(r"\d\s*%|процент", re.I)
MOVE_RE = re.compile(r"(?:перенес|перенёс|продл|сдвин|отлож)\w*", re.I)
START_VERB_RE = re.compile(r"(?:начн|начал|начат|старт|приступ|закро|закры|перекро|перекры)\w*", re.I)
END_VERB_RE = re.compile(r"(?:заверш|оконч|сдач|сдать|сдадут|продл|перенес|выполн|законч|открыт|откро)\w*", re.I)
_TIME = r"(?:\d{1,2}[:.]\d{2}\s*)?"
END_ANCHOR_RE = re.compile(rf"\b(?:до|к|по)\s*{_TIME}$", re.I)
START_ANCHOR_RE = re.compile(rf"\bс\s*{_TIME}$", re.I)
ON_ANCHOR_RE = re.compile(r"\bна\s*$", re.I)
# Sentence end: . ! ? followed by space and a capital/quote, or a line break. Not inside 30.11.2026
# and not after common abbreviations (г. ул. пр. мкр. ...).
SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?])(?<!\bг\.)(?<!\bгг\.)(?<!\bул\.)(?<!\bпр\.)(?<!\bмкр\.)(?<!\bим\.)(?<!\bд\.)(?<!\bт\.)"
    r"\s+(?=[А-ЯЁA-Z«\"„(])|\n+")
MAX_SNAPSHOT_CHARS = 1500

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


def _last(rx, text):
    pos = -1
    for m in rx.finditer(text):
        pos = m.start()
    return pos


def _role(before: str, after: str) -> str:
    """Guess what a date means from its own clause. Unsure -> 'unclassified' (the editor decides)."""
    clause = CLAUSE_CUT_RE.split(before[-120:])[-1]
    tail = CLAUSE_CUT_RE.split(after[:30])[0]
    if NEG_ACTUAL_RE.search(clause):
        return "unclassified"  # "не завершили к ..." - a missed date, not a completion
    if ACTUAL_RE.search(clause):
        if MODAL_RE.search(clause):
            return "expected_end"  # "будет сдан", "должны были быть завершены"
        if PERCENT_RE.search(clause) or PERCENT_RE.search(tail):
            return "unclassified"  # "завершены на 60%"
        return "reported_actual_end"
    if MOVE_RE.search(clause):
        if ON_ANCHOR_RE.search(clause):
            return "expected_end"  # "перенесён ... на <date>"
        if START_ANCHOR_RE.search(clause):
            return "previous_end"  # "перенесён с <date> ..."
    if ON_ANCHOR_RE.search(clause):
        if MODAL_RE.search(clause):
            return "start" if _last(START_VERB_RE, clause) > _last(END_VERB_RE, clause) else "expected_end"
        return "unclassified"  # "по состоянию на <date>"
    if END_ANCHOR_RE.search(clause):
        return "expected_end"
    if START_ANCHOR_RE.search(clause):
        return "start"
    s_pos, e_pos = _last(START_VERB_RE, clause), _last(END_VERB_RE, clause)
    if s_pos < 0 and e_pos < 0:
        return "unclassified"
    return "start" if s_pos > e_pos else "expected_end"  # the verb nearest to the date wins


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
        if y1:
            y_first = y1
        elif year and (m1, int(d1)) > (m2, int(d2)):
            y_first = str(int(year) - 1)  # "с 25 декабря по 15 января 2027 года"
        else:
            y_first = year
        start, end = (_mk(y_first, m1, d1), _mk(year, m2, d2)) if year else (None, None)
        if not year:
            prec = "day_without_year"
        elif start is None or end is None or start > end:
            prec = "invalid_date"
        else:
            prec = "day"
        add(m.start(), m.end(), role="range", precision=prec, start=start, end=end,
            context=text[max(0, m.start() - 70):m.start()])
    for rx, kind in ((ISO_RE, "iso"), (NUMERIC_RE, "numeric"), (DAY_RE, "day")):
        for m in rx.finditer(text):
            if kind == "iso":
                value = _mk(*m.groups())
                prec = "day" if value else "invalid_date"
            elif kind == "numeric":
                d, mo, y = m.groups()
                value = _mk(y, mo, d)
                prec = "day" if value else "invalid_date"
            else:
                d, mon, y = m.groups()
                value = _mk(y, _month(mon), d) if y else None
                prec = ("day" if value else "invalid_date") if y else "day_without_year"
            add(m.start(), m.end(), role=_role(text[:m.start()], text[m.end():]), precision=prec,
                value=value, context=text[max(0, m.start() - 70):m.start()])
    for m in MONTH_ONLY_RE.finditer(text):
        mon, y = m.groups()
        add(m.start(), m.end(), role=_role(text[:m.start()], text[m.end():]), precision="month" if y else "month_without_year",
            value=None, month=f"{y}-{_month(mon):02d}" if y else None, context=text[max(0, m.start() - 70):m.start()])
    found.sort(key=lambda r: r["span"][0])
    return found


def split_sentences(text: str) -> list[str]:
    return [" ".join(part.split()) for part in SENTENCE_SPLIT_RE.split(text) if part and part.strip()]


def _redact(sentence: str) -> str:
    for hit in sorted(set(cv.find_pii(sentence)), key=len, reverse=True):
        sentence = sentence.replace(hit, "[контакт удалён]")
    return sentence


def make_snapshot(text: str, *, source_id: str, url: str, retrieved_at: str, published_on: str | None) -> dict:
    budget = max(MAX_EXCERPT, min(MAX_SNAPSHOT_CHARS, len(text) // 2))
    sentences, used, truncated = [], 0, False
    for s in split_sentences(text):
        if not extract_dates(s):
            continue
        s = _redact(s)[:MAX_EXCERPT]
        if used + len(s) > budget:
            truncated = True
            break
        sentences.append(s)
        used += len(s)
    return {
        "schema": "r05-source-snapshot-v1",
        "source_id": source_id,
        "url": url,
        "retrieved_at": retrieved_at,
        "published_on": published_on,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "excerpts": sentences,
        "truncated": truncated,
        "note": ("Только предложения с датами (<=300 символов каждое, всего не больше половины текста и "
                 f"<= {MAX_SNAPSHOT_CHARS}), контакты удалены, плюс хэш полного текста; статья целиком не хранится."),
    }


def schedule_signals(snapshot: dict) -> dict:
    """Collapse a snapshot's dates into candidate schedule values with their excerpts."""
    sig = {"start": [], "expected_end": [], "reported_actual_end": [], "previous_end": [], "period": [],
           "imprecise": [], "unclassified": []}
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

    pub = new.get("published_on") or (new.get("retrieved_at") or "")[:10] or None
    for e in sn["reported_actual_end"]:
        if not e.get("value") or e["value"] in _values(so["reported_actual_end"]):
            continue
        if pub and e["value"] > pub:
            propose("rejected_actual", "schedule.actual_end", None, e["value"], [e["excerpt"]],
                    "дата позже публикации источника: это не фактическое завершение")
        else:
            propose("candidate_actual", "schedule.actual_end", sched.get("actual_end"), e["value"], [e["excerpt"]],
                    "источник сообщает о завершении; status=completed и actual_end только после подтверждения редактором"
                    + ("" if new.get("published_on") else "; у версии нет published_on — сравнено с датой получения"))
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
