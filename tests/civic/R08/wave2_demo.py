"""Стенд R08, волна 2: дописать в демо-жалобы R07 то, чего у них пока нет (СИНТЕТИКА, только для стенда и тестов).

- subtopic — уточнение из categories_v2.json (у одной цели — чаще одно и то же: люди сообщают об одном);
- проверка жителями после «исправлено» — в форме R09 (lifecycle.py): resolution = {state: reported|verified,
  reported_at, verified_at, votes}; «Да» через 0,5–2 дня у ~55 % исправлений; возврат в работу после «исправлено»
  помечается reopened_by_residents у ~70 % возвратов; ~30 % обращений «в работе» получают историю «исправлено →
  житель: проблема осталась → снова в работе» (в демо R07 возвратов нет).

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
        prev = None
        for h in hist:  # возврат в работу после «исправлено» — чаще всего ответ жителя «Проблема осталась»
            if prev == "fixed" and h.get("status") in ("new", "accepted", "in_progress") and _u("reopen", r.get("id")) < 0.7:
                h["reopened_by_residents"] = True
            prev = h.get("status")
        # ~30 % обращений «в работе» уже были «исправлены» и возвращены жителями («Проблема осталась») —
        # в демо R07 таких историй нет, а счётчик «вернули» должен быть виден на стенде.
        last = max((parse_time(h.get("at")) for h in hist), default=None)
        gap = (datetime.now(last.tzinfo) - last) if last is not None else None
        if (r.get("status") == "in_progress" and gap is not None and gap >= timedelta(hours=2)
                and _u("back", r.get("id")) < 0.3):
            fix_at, back_at = last + gap * 0.3, last + gap * 0.6
            hist += [{"at": fix_at.isoformat(), "status": "fixed"},
                     {"at": back_at.isoformat(), "status": "in_progress", "reopened_by_residents": True}]
            r["resolution"] = {"round": 1, "state": "reopened", "reported_at": fix_at.isoformat(), "verified_at": None,
                               "reopened_at": back_at.isoformat(), "votes": {"yes": 0, "no": 2, "cant": 0}, "demo_stand": True}
        if fixed and r.get("status") == "fixed":
            x = _u("check", r.get("id"))
            at = fixed[-1] + timedelta(days=0.5 + 1.5 * _u("delay", r.get("id")))
            res = {"round": 1, "state": "reported", "reported_at": fixed[-1].isoformat(), "verified_at": None,
                   "votes": {"yes": 0, "no": 0, "cant": 0}, "demo_stand": True}
            if x < 0.55:
                res.update(state="verified", verified_at=at.isoformat(), votes={"yes": 1 + int(3 * x), "no": 0, "cant": 0})
            elif x < 0.65:
                res["votes"]["cant"] = 1
            r["resolution"] = res
        r["status_history"] = hist
        out.append(r)
    return out


def wrap(records_fn):
    """records(since) → те же записи с уточнениями и проверкой жителями."""
    return lambda since: augment(records_fn(since) or [])
