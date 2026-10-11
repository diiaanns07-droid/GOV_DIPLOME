"""Стенд R08, волна 2: дописать в демо-жалобы R07 то, чего у них пока нет (СИНТЕТИКА, только для стенда и тестов).

- subtopic — уточнение из categories_v2.json (у одной цели — чаще одно и то же: люди сообщают об одном);
- проверка жителями после «исправлено»: {"event": "resident_check", "answer": "yes|cant"} через 0,5–2 дня.

Это не меняет модуль ui/civic_akim: там читаются те же поля из настоящих записей R09 (INTEGRATION.txt §8).
Выбор детерминированный (по хэшу id) — скриншоты повторяемы. Записи и так demo: true (R07).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from ui.civic_akim import deadlines
from ui.civic_akim.summary import parse_time


def _u(*parts) -> float:
    """Детерминированное «случайное» число 0..1 от строк."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


def augment(records: list[dict]) -> list[dict]:
    subs = {c["id"]: [s["id"] for s in c.get("subtopics") or []] for c in deadlines.load_categories()["categories"]}
    out = []
    for r in records:
        r = dict(r)
        options = subs.get(r.get("category")) or []
        if options and not r.get("subtopic"):
            tid = (r.get("target") or {}).get("id") or r.get("id")
            # 80 % — «главное» уточнение места, остальные — по записи; первое уточнение категории чаще прочих.
            key = tid if _u("same", r.get("id")) < 0.8 else r.get("id")
            x = _u("sub", key)
            i = 0 if x < 0.45 else 1 + int((x - 0.45) / 0.55 * (len(options) - 1)) if len(options) > 1 else 0
            r["subtopic"] = options[min(i, len(options) - 1)]
        hist = [dict(h) for h in r.get("status_history") or [] if isinstance(h, dict)]
        fixed = [parse_time(h.get("at")) for h in hist if h.get("status") == "fixed"]
        if fixed and r.get("status") == "fixed":
            x = _u("check", r.get("id"))
            at = fixed[-1] + timedelta(days=0.5 + 1.5 * _u("delay", r.get("id")))
            if x < 0.55:
                hist.append({"at": at.isoformat(), "event": "resident_check", "answer": "yes"})
            elif x < 0.65:
                hist.append({"at": at.isoformat(), "event": "resident_check", "answer": "cant"})
        r["status_history"] = hist
        out.append(r)
    return out


def wrap(records_fn):
    """records(since) → те же записи с уточнениями и проверкой жителями."""
    return lambda since: augment(records_fn(since) or [])
