"""Detect a changed published schedule between two saved versions of a source (R05 stretch).

Two steps, both offline:

1. ``snapshot`` - from a locally fetched page converted to plain text, keep only the
   date-bearing sentences or windows around each date (each <= 300 chars, <= 1500 in total,
   contacts redacted) plus the sha256 of the full text. A long article is never stored whole.
2. ``diff``     - compare two snapshots of the same source (and optionally the current
   civic-v1 record) and emit a report of *proposed* schedule changes. Every proposal has
   ``requires_editor_confirmation: true``; nothing is applied automatically.

Rules kept from the contract/R05 brief:
* an expected end ("завершат до ...") never becomes actual_end;
* "завершены ..." is only a candidate actual_end, and only when the date is not after
  the snapshot's published_on;
* month-only, quarter, half-year, year-end or year-less dates are reported, not turned into a day;
* original_planned_end is never proposed for change once the record has one.

Russian-language heuristics only; Kazakh text is not parsed (reported as no dates). Unsure roles
are 'unclassified' and still reach the editor when they change (kind unclassified_changed).

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
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import civic_v1 as cv  # noqa: E402  (PII detection shared with the validator)

MONTHS3 = {"янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "мая": 5, "мае": 5, "июн": 6, "июл": 7, "авг": 8,
           "сен": 9, "окт": 10, "ноя": 11, "дек": 12}
MONTH_RE = (r"(январ[яеь]|феврал[яеь]|март[аеу]?|апрел[яеь]|ма[йяе]|июн[яеь]|июл[яеь]|август[аеу]?|сентябр[яеь]|"
            r"октябр[яеь]|ноябр[яеь]|декабр[яеь]|(?:янв|февр?|мар|апр|авг|сент?|окт|нояб?|дек)(?:\.|(?![а-яёa-z])))")
YEAR_RE = r"(20\d{2})"
_T = r"(?:\d{1,2}[:.]\d{2}\s+)?"  # optional clock time: "с 22:00 10 октября до 06:00 12 октября"

# day-month[-year] ranges: "с 10 по 20 октября 2026", "с 10 октября по 2 ноября 2026", with optional times
RANGE_RE = re.compile(
    rf"\bс\s+{_T}(\d{{1,2}})(?:\s+{MONTH_RE})?(?:\s+{YEAR_RE})?\s*(?:года|г\.)?\s+(?:по|до)\s+{_T}(\d{{1,2}})\s+{MONTH_RE}(?:\s+{YEAR_RE})?",
    re.I)
DAY_RE = re.compile(rf"\b(\d{{1,2}})\s+{MONTH_RE}(?:\s+{YEAR_RE})?", re.I)
NUMERIC_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(20\d{2})(?!\d)")  # also "30.10.2026г."
# numeric ranges: "с 15.10.2026 по 16.10.2026", "7.10-8.10.2026"
NUM_RANGE_RE = re.compile(rf"\bс\s+{_T}(\d{{1,2}})\.(\d{{1,2}})\.(20\d{{2}})(?:\s*г\.?|\s+года)?\s+(?:по|до)\s+{_T}"
                          r"(\d{1,2})\.(\d{1,2})\.(20\d{2})(?!\d)", re.I)
SHORT_RANGE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\s*[-–—]\s*(\d{1,2})\.(\d{1,2})\.(20\d{2})(?!\d)")
ISO_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
MONTH_ONLY_RE = re.compile(rf"\b(?:в|до|к|на)\s+(?:конц[еуа]\s+|начал[еуа]\s+|середин[еуы]\s+)?{MONTH_RE}(?:\s+{YEAR_RE})?", re.I)
YEAR_ONLY_RE = re.compile(r"\b(?:в|на|до|к)\s+(20\d{2})\s*(?:год\w*|г\.)", re.I)
# Coarser deadlines: always imprecise (never turned into a day).
QUARTER_RE = re.compile(r"\b(IV|I{1,3}|[1-4])(?:-?(?:м|ом|й|ый|го))?\s+квартал\w*\s+(?:(20\d{2})|текущего)\s+год\w*", re.I)
HALF_RE = re.compile(r"\b(перв\w+|втор\w+|[12](?:-?(?:м|ом|го))?)\s+полугоди\w*\s+(?:(20\d{2})|текущего)\s+год\w*", re.I)
YEAR_END_RE = re.compile(r"\bконц[аеу]\s+(?:(20\d{2})\s+|текущего\s+)?год\w*", re.I)
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}

CAPS = "A-ZА-ЯЁӘҒҚҢӨҰҮҺІ"
_SENT_END = rf"[.!?]\s+(?=[{CAPS}\d«\"„(])"
# Role cues are read only inside the clause that holds the date: cut at , ; ( : dashes and sentence ends.
CLAUSE_SPLIT_RE = re.compile(rf"([,;(:—–]|{_SENT_END})")
TAIL_CUT_RE = re.compile(r"[,;(:—–.!?]")
YEAR_TAIL_RE = re.compile(r"^\s*(?:года|году|год|г\.|гг\.)?")
ACTUAL_RE = re.compile(r"(заверш[её]н[аоы]?\b|заверш[её]нн\w+|завершили|завершила|завершил\b|оконч[её]н\w*|окончили|"
                       r"сдан[аоы]?\b|сдали|открыт[аоы]?\b|открыли|введ[её]н[аоы]?\s+в\s+эксплуатаци|"
                       r"выполнен[аоы]?\b|закончили|законч[её]н\w*)", re.I)
NEG_ACTUAL_RE = re.compile(r"\bне\s+(?:был\w*\s+)?(?:заверш|оконч|сдан|сдал|открыт|выполн|законч)", re.I)
# Predicate forms only: "Запланированный", "должностных", "Ожидаемый" are not modal.
MODAL_RE = re.compile(r"\b(?:будет|будут|должн(?:а|о|ы)?\b|планиру(?:ется|ются|ет|ют)\b|планировал\w*|"
                      r"запланирован[аоы]?\b|ожида(?:ется|ются|лось|лся|лась)\b|намечен[аоы]?\b|"
                      r"предполага(?:ется|ются|ет|ют)\b|предстоит)", re.I)
PERCENT_RE = re.compile(r"\d\s*%|процент", re.I)
MOVE_RE = re.compile(r"(?:перен[её]с|перенос|продл(?!итс|ятс)|сдви[нг]|отлож|отклад)\w*", re.I)
SUSPEND_RE = re.compile(r"(?:приостанов|сня[тл]|отмен|возобнов|заморож|прекращ)\w*", re.I)
PREV_RE = re.compile(r"\b(?:вместо|был[аои]?)\s*$", re.I)
START_VERB_RE = re.compile(r"(?:начн|начал|начат|старт|приступ|закро|закры|перекро|перекры)\w*", re.I)
END_VERB_RE = re.compile(r"(?:заверш|оконч|сдач|сдать|сдадут|продл|перенес|выполн|законч|открыт|откро)\w*", re.I)
# What a postponement is about: start nouns/verbs vs end nouns/verbs (without the move stems themselves).
START_CUE_RE = re.compile(r"(?:начал|начат|старт|приступ|закры|перекры)\w*", re.I)
END_CUE_RE = re.compile(r"(?:заверш|оконч|сдач|сдать|сдадут|выполн|законч|открыт|откро|срок)\w*", re.I)
_TIME = r"(?:\d{1,2}[:.]\d{2}\s*)?"
END_ANCHOR_RE = re.compile(rf"\b(?:до|к|по)\s*{_TIME}$", re.I)
START_ANCHOR_RE = re.compile(rf"\bс\s*{_TIME}$", re.I)
ON_ANCHOR_RE = re.compile(r"\bна\s*$", re.I)
SENT_CANDIDATE_RE = re.compile(rf"[.!?](?=\s+[{CAPS}\d«\"„(])|\n\s*\n")
ABBREVIATIONS = frozenset({"ул", "пр", "пр-т", "просп", "мкр", "д", "им", "т", "обл", "р-н", "пос", "корп", "стр", "кв",
                           "тыс", "млн", "млрд", "руб", "тг", "м", "км", "см", "№", "тел", "моб", "факс", "напр", "т.е",
                           "янв", "фев", "февр", "мар", "апр", "авг", "сен", "сент", "окт", "ноя", "нояб", "дек"})
MAX_SNAPSHOT_CHARS = 1500
MAX_EXCERPT = 300
WINDOW_BEFORE, WINDOW_AFTER = 150, 60
ROLE_PRIORITY = {"expected_end": 0, "reported_actual_end": 0, "previous_end": 1, "previous_start": 1, "start": 1,
                 "range": 2, "unclassified": 3}


def normalize_text(text: str) -> str:
    """NFKC, unify line ends, join hard-wrapped lines (a single newline is a space; a blank line stays)."""
    t = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"(?<!\n)\n(?!\n)", " ", t)
    return re.sub(r"[ \t]+", " ", t)


def _month(word: str) -> int:
    w = word.lower().rstrip(".")
    n = MONTHS3.get(w[:3])
    if n is None or (w[:3] == "мар" and w not in ("мар", "март", "марта", "марте", "марту")):
        raise ValueError(word)
    return n


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


def _verb_role(clause: str, nearest_last: bool = True) -> str | None:
    s_pos, e_pos = _last(START_VERB_RE, clause), _last(END_VERB_RE, clause)
    if not nearest_last:  # after the date the first verb is the nearest one
        sm, em = START_VERB_RE.search(clause), END_VERB_RE.search(clause)
        s_pos = sm.start() if sm else -1
        e_pos = em.start() if em else -1
        if s_pos < 0 and e_pos < 0:
            return None
        if s_pos < 0 or (e_pos >= 0 and e_pos < s_pos):
            return "expected_end"
        return "start"
    if s_pos < 0 and e_pos < 0:
        return None
    return "start" if s_pos > e_pos else "expected_end"


def _actual_role(clause: str, tail: str) -> str:
    if MODAL_RE.search(clause):
        return "expected_end"  # "будет сдан", "должны были быть завершены"
    if PERCENT_RE.search(clause) or PERCENT_RE.search(tail):
        return "unclassified"  # "завершены на 60%"
    return "reported_actual_end"


def _ends_sentence(text: str) -> bool:
    """True when text ends with sentence punctuation that is not an abbreviation ('ул.', 'г. Астана')."""
    t = text.rstrip()
    if not t or t[-1] not in ".!?" or len(t) == len(text):
        return False  # no punctuation, or punctuation glued to the date (30.11.2026)
    if t[-1] != ".":
        return True
    tok_m = re.search(r"(\S+)\.$", t)
    tok = tok_m.group(1).lower() if tok_m else ""
    if tok in ABBREVIATIONS or (len(tok) == 1 and tok.isalpha() and tok != "г"):
        return False
    if tok in ("г", "гг"):
        return bool(re.search(r"\d{4}\s*(?:г|гг)\.$", t))
    return True


def _role(before: str, after: str) -> str:
    """Guess what a date means from its own clause. Unsure -> 'unclassified' (the editor decides)."""
    pieces = CLAUSE_SPLIT_RE.split(before[-200:])
    clause = pieces[-1][-120:]
    cut = pieces[-2] if len(pieces) > 1 else None
    label = pieces[-3] if len(pieces) > 2 else ""
    if _ends_sentence(clause):
        clause, cut, label = "", None, ""  # the date opens a new sentence: "...завершены. 1 октября начался"
    tail = TAIL_CUT_RE.split(YEAR_TAIL_RE.sub("", after[:100], count=1))[0]

    if NEG_ACTUAL_RE.search(clause):
        return "unclassified"  # "не завершили к ..." - a missed date, not a completion
    actual_pos = _last(ACTUAL_RE, clause)
    if actual_pos >= 0 and actual_pos > _last(START_VERB_RE, clause) and not ON_ANCHOR_RE.search(clause):
        return _actual_role(clause, tail)  # the completion word is the cue nearest to the date
    if MOVE_RE.search(clause) and (ON_ANCHOR_RE.search(clause) or START_ANCHOR_RE.search(clause)
                                   or END_ANCHOR_RE.search(clause)):
        about_start = bool(START_CUE_RE.search(clause))
        about_end = bool(END_CUE_RE.search(clause))
        new_date = not START_ANCHOR_RE.search(clause)  # "... на/до <date>" is the new date, "с <date>" the old
        if about_start and not about_end:
            return "start" if new_date else "previous_start"
        if about_end and not about_start:
            return "expected_end" if new_date else "previous_end"
        return "unclassified"  # "Мероприятие перенесли на ...": the editor decides what moved
    if PREV_RE.search(clause):
        return "previous_end"  # "вместо <date>", "срок был <date>"
    if SUSPEND_RE.search(clause):
        return "unclassified"  # suspended / lifted / resumed: not the planned start of the works
    if ON_ANCHOR_RE.search(clause):
        if MODAL_RE.search(clause):
            s_cue, e_cue = START_VERB_RE.search(clause), END_VERB_RE.search(clause)
            if bool(s_cue) != bool(e_cue):
                return "start" if s_cue else "expected_end"
        return "unclassified"  # "по состоянию на <date>", "Окончание перекрытия ... запланировано на"
    if END_ANCHOR_RE.search(clause):
        return "expected_end"
    if START_ANCHOR_RE.search(clause):
        return "start"
    role = _verb_role(clause)
    if role:
        return role
    # Nothing before the date in its clause: read the clause right after it ("1 октября начался ремонт").
    if NEG_ACTUAL_RE.search(tail):
        return "unclassified"
    if ACTUAL_RE.search(tail):
        return _actual_role(tail, tail)
    role = _verb_role(tail, nearest_last=False)
    if role:
        return role
    # "Срок начала работ — 5 октября": a label before a dash/colon.
    if cut is not None and cut.strip() in ("—", "–", ":") and not clause.strip():
        if not ACTUAL_RE.search(label) and not NEG_ACTUAL_RE.search(label):
            return _verb_role(label) or "unclassified"
    return "unclassified"


def extract_dates(text: str) -> list[dict]:
    """Find dates with precision and a role guess. Pure heuristics; output goes to an editor."""
    text = normalize_text(text)
    found, taken = [], []

    def add(s0, s1, **rec):
        if any(a < s1 and s0 < b for a, b in taken):
            return
        taken.append((s0, s1))
        rec.update(span=[s0, s1], raw=text[s0:s1])
        found.append(rec)

    def ctx(m):
        return text[max(0, m.start() - 70):m.start()]

    for m in RANGE_RE.finditer(text):
        d1, mon1, y1, d2, mon2, y2 = m.groups()
        try:
            m2 = _month(mon2)
            m1 = _month(mon1) if mon1 else m2
        except ValueError:
            continue
        year = y2 or y1
        if y1:
            y_first = y1
        elif year and mon1 and m1 > m2:
            y_first = str(int(year) - 1)  # "с 25 декабря по 15 января 2027 года"
        else:
            y_first = year
        start, end = (_mk(y_first, m1, d1), _mk(year, m2, d2)) if year else (None, None)
        if not year:
            prec = "day_without_year"
        elif start is None or end is None or start > end:
            prec = "invalid_date"  # "с 28 по 3 октября": sloppy wording, the editor resolves it
        else:
            prec = "day"
        add(m.start(), m.end(), role="range", precision=prec, start=start, end=end, context=ctx(m))
    for m in NUM_RANGE_RE.finditer(text):
        d1, m1, y1, d2, m2, y2 = m.groups()
        start, end = _mk(y1, m1, d1), _mk(y2, m2, d2)
        prec = "day" if start and end and start <= end else "invalid_date"
        add(m.start(), m.end(), role="range", precision=prec, start=start, end=end, context=ctx(m))
    for m in SHORT_RANGE_RE.finditer(text):
        d1, m1, d2, m2, y = m.groups()
        start, end = _mk(y, m1, d1), _mk(y, m2, d2)
        prec = "day" if start and end and start <= end else "invalid_date"
        add(m.start(), m.end(), role="range", precision=prec, start=start, end=end, context=ctx(m))
    for rx, kind in ((ISO_RE, "iso"), (NUMERIC_RE, "numeric"), (DAY_RE, "day")):
        for m in rx.finditer(text):
            try:
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
            except ValueError:
                continue
            add(m.start(), m.end(), role=_role(text[:m.start()], text[m.end():]), precision=prec,
                value=value, context=ctx(m))
    for m in QUARTER_RE.finditer(text):
        q, y = m.groups()
        n = ROMAN.get(q.lower()) or int(q)
        add(m.start(), m.end(), role=_role(text[:m.start()], text[m.end():]), precision="quarter", value=None,
            month=f"{y or 'current'}-Q{n}", context=ctx(m))
    for m in HALF_RE.finditer(text):
        h, y = m.groups()
        n = 2 if h.lower().startswith(("втор", "2")) else 1
        add(m.start(), m.end(), role=_role(text[:m.start()], text[m.end():]), precision="half_year", value=None,
            month=f"{y or 'current'}-H{n}", context=ctx(m))
    for m in YEAR_END_RE.finditer(text):
        (y,) = m.groups()
        add(m.start(), m.end(), role=_role(text[:m.start()], text[m.end():]), precision="year_end", value=None,
            month=f"{y or 'current'}-end", context=ctx(m))
    for m in YEAR_ONLY_RE.finditer(text):
        (y,) = m.groups()
        add(m.start(), m.end(), role=_role(text[:m.start()], text[m.end():]), precision="year", value=None,
            month=f"{y}", context=ctx(m))
    for m in MONTH_ONLY_RE.finditer(text):
        mon, y = m.groups()
        try:
            n = _month(mon)
        except ValueError:
            continue
        add(m.start(), m.end(), role=_role(text[:m.start()], text[m.end():]),
            precision="month" if y else "month_without_year", value=None,
            month=f"{y}-{n:02d}" if y else None, context=ctx(m))
    found.sort(key=lambda r: r["span"][0])
    return found


def split_sentences(text: str) -> list[str]:
    """Sentence split that keeps 30.11.2026, 'г. Астана', 'ул. Кенесары' and hard-wrapped lines intact."""
    t = normalize_text(text)
    out, start = [], 0
    for m in SENT_CANDIDATE_RE.finditer(t):
        if m.group(0)[0] in ".!?":
            tok_m = re.search(r"(\S+)$", t[start:m.start()])
            tok = tok_m.group(1).lower() if tok_m else ""
            if m.group(0) == ".":
                if tok in ABBREVIATIONS or (len(tok) == 1 and tok.isalpha() and tok not in ("г",)):
                    continue  # "ул.", initials "А."
                if tok in ("г", "гг") and not re.search(r"\d{4}\s*$", t[start:m.start() - len(tok)]):
                    continue  # "г. Астана" - but "2026 г." ends a sentence
            cut = m.end()
        else:
            cut = m.start()
        piece = " ".join(t[start:cut].split())
        if piece:
            out.append(piece)
        start = cut
    piece = " ".join(t[start:].split())
    if piece:
        out.append(piece)
    return out


def _redact(sentence: str) -> str:
    """Remove phone numbers / IIN / e-mails, never the dates (date digits are masked during detection)."""
    masked = list(sentence)
    for d in extract_dates(sentence):
        for i in range(*d["span"]):
            if i < len(masked):
                masked[i] = "§"
    for hit in sorted(set(cv.find_pii("".join(masked))), key=len, reverse=True):
        if "§" not in hit:
            sentence = sentence.replace(hit, "[контакт удалён]")
    return sentence


def _windows(sentence: str) -> list[tuple[int, str]]:
    """(priority, excerpt) pieces of a dated sentence; long sentences become windows around each date."""
    dates = extract_dates(sentence)
    if not dates:
        return []
    if len(sentence) <= MAX_EXCERPT:
        return [(min(ROLE_PRIORITY.get(d["role"], 3) for d in dates), sentence)]
    out = []
    for d in dates:
        a = max(0, d["span"][0] - WINDOW_BEFORE)
        b = min(len(sentence), d["span"][1] + WINDOW_AFTER)
        if a > 0:
            sp = sentence.find(" ", a)
            a = sp + 1 if 0 <= sp < d["span"][0] else a
        if b < len(sentence):
            sp = sentence.rfind(" ", d["span"][1], b)
            b = sp if sp > d["span"][1] else b
        piece = "… " * (a > 0) + sentence[a:b] + " …" * (b < len(sentence))
        out.append((ROLE_PRIORITY.get(d["role"], 3), piece[:MAX_EXCERPT]))
    return out


def make_snapshot(text: str, *, source_id: str, url: str, retrieved_at: str, published_on: str | None) -> dict:
    pieces = []
    for s in split_sentences(text):
        for prio, piece in _windows(_redact(s)):
            if piece not in [p for _, p in pieces]:
                pieces.append((prio, piece))
    keep, used = set(), 0
    for idx in sorted(range(len(pieces)), key=lambda i: (pieces[i][0], i)):
        if used + len(pieces[idx][1]) <= MAX_SNAPSHOT_CHARS:
            keep.add(idx)
            used += len(pieces[idx][1])
    excerpts = [pieces[i][1] for i in range(len(pieces)) if i in keep]
    return {
        "schema": "r05-source-snapshot-v1",
        "source_id": source_id,
        "url": url,
        "retrieved_at": retrieved_at,
        "published_on": published_on,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "excerpts": excerpts,
        "truncated": len(keep) < len(pieces),
        "note": (f"Только предложения или окна вокруг дат (<= {MAX_EXCERPT} символов каждое, всего <= "
                 f"{MAX_SNAPSHOT_CHARS}), контакты удалены, плюс sha256 полного текста. Длинная статья целиком "
                 "не хранится; короткое объявление может сохраниться почти полностью."),
    }


def schedule_signals(snapshot: dict) -> dict:
    """Collapse a snapshot's dates into candidate schedule values with their excerpts."""
    sig = {"start": [], "expected_end": [], "reported_actual_end": [], "previous_end": [], "previous_start": [],
           "period": [], "imprecise": [], "unclassified": []}
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
        elif (not nv and new.get("truncated")) or (not ov and old.get("truncated")):
            pass  # the value may only be missing from a truncated snapshot: reported as snapshot_truncated
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
    ou, nu = _values(so["unclassified"]), _values(sn["unclassified"])
    if ou != nu:
        propose("unclassified_changed", None, ou or None, nu or None, [e["excerpt"] for e in sn["unclassified"]],
                "изменилась дата, роль которой не определена автоматически; редактор решает, к какому полю она относится")
    if old.get("truncated") or new.get("truncated"):
        propose("snapshot_truncated", None, None, None, [],
                "снимок источника усечён: часть дат не сохранена; сравнить с источником целиком")
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
        "editor_action": (("В обеих версиях не найдено распознаваемых дат; сравнить тексты вручную."
                           if old.get("text_sha256") != new.get("text_sha256") and not old.get("excerpts")
                           and not new.get("excerpts") else "Нет изменений сроков в сохранённых фрагментах.")
                          if not findings else
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
