"""«Нужно решение акима» (волна 2 п. 5): 1–3 просрочки, которые служба не может сдвинуть сама.

КРИТЕРИЙ (одним местом):
  обращение не исправлено, срок категории истёк (deadlines.due — рабочие дни),
  И в паспорте решения (R09, волна 2 п. 2) причина задержки — «нужно решение руководителя»:
  delay.reason_code ∈ NEEDS_DECISION или delay.needs_decision = true.
Почему так: аким не должен разбирать каждую просрочку. Обычные задержки — погода, подрядчик, материалы —
видны в «Просрочено» и решаются службой. Сюда попадает только то, где нужен выбор руководителя:
деньги вне плана, «чей это объект», согласование между ведомствами. Без двух вариантов действия пункт
всё равно показывается, но с пометкой «варианты не предложены» — это сигнал службе, а не акиму.

Где лежит причина (читаем все формы, точную выбирает R09 — INTEGRATION.txt §8):
  record["delay"] или record["passport"]["delay"] = {reason_code, problem_ru/kk, blocker_ru/kk,
  options: [{ru, kk}, {ru, kk}], decision_ru/kk, temp_measure_ru/kk, next_update}.
Пока R09 не даёт причин, а жалобы — демо (R07), блок показывает пример из fixtures/decisions_demo.json
(помечен «Пример»): эти записи проходят тот же критерий, что и настоящие.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from . import deadlines, routing

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "decisions_demo.json"
NEEDS_DECISION = {"needs_decision", "leader_decision", "akim_decision", "needs_akim_decision", "management_decision"}
MAX_ITEMS = 3


def delay_of(record: dict) -> dict | None:
    d = record.get("delay")
    if not isinstance(d, dict):
        passport = record.get("passport")
        d = passport.get("delay") if isinstance(passport, dict) else None
    return d if isinstance(d, dict) else None


def needs_decision(record: dict) -> bool:
    d = delay_of(record)
    if not d:
        return False
    return d.get("needs_decision") is True or str(d.get("reason_code") or d.get("reason") or "").lower() in NEEDS_DECISION


def _txt(d: dict, key: str, lang: str):
    v = d.get(f"{key}_{lang}")
    if v is None and isinstance(d.get(key), dict):
        v = d[key].get(lang)
    if v is None and lang == "ru" and isinstance(d.get(key), str):
        v = d[key]
    return v.strip() if isinstance(v, str) and v.strip() else None


def _subtopic(category: str | None, subtopic: str | None) -> dict | None:
    if not subtopic:
        return None
    for c in deadlines.load_categories()["categories"]:
        if c["id"] == category:
            for s in c.get("subtopics") or []:
                if s["id"] == subtopic:
                    return {"id": subtopic, "ru": s["ru"], "kk": s["kk"]}
    return None


def build(records: list[dict], as_of: datetime, *, status_at, parse_time, labels: dict | None = None) -> list[dict]:
    """Пункты блока по записям (уже отфильтрованным по району), самые давние просрочки первыми."""
    labels = labels or {}
    cats = {c["id"]: c for c in deadlines.load_categories()["categories"]}
    out = []
    for r in records:
        st = status_at(r, as_of)
        if st not in ("new", "accepted", "in_progress") or not needs_decision(r):
            continue
        created = parse_time(r.get("created_at"))
        timer = deadlines.timer(r.get("category"), created, as_of)
        if timer["state"] != "overdue":
            continue
        d = delay_of(r)
        options = [{"ru": (o.get("ru") or o.get("kk")).strip(), "kk": (o.get("kk") or o.get("ru")).strip(),
                    "kk_missing": not o.get("kk")}
                   for o in (d.get("options") or []) if isinstance(o, dict) and (o.get("ru") or o.get("kk"))][:2]
        target = r.get("target") if isinstance(r.get("target"), dict) else None
        label = labels.get(target.get("id")) if target else None
        cat = cats.get(r.get("category")) or cats["other"]
        sub = _subtopic(r.get("category"), r.get("subtopic"))
        service = routing.service_for(r.get("category"), r.get("subtopic"))
        item = {
            "id": r.get("id"),
            "category": cat["id"], "category_ru": cat["ru"], "category_kk": cat["kk"],
            "subtopic": sub,
            "district": r.get("district"),
            "place_ru": (label or {}).get("ru") or r.get("place_ru"),
            "place_kk": (label or {}).get("kk") or r.get("place_kk"),
            "target": {"kind": target.get("kind"), "id": target.get("id")} if target and label else None,
            "people": 1 + int(r.get("metoo") or 0),
            "timer": timer,
            "service": {"id": service["id"], "ru": service["ru"], "kk": service["kk"]},
            "problem_ru": _txt(d, "problem", "ru") or (sub or cat)["ru"],
            "problem_kk": _txt(d, "problem", "kk"),
            "blocker_ru": _txt(d, "blocker", "ru"), "blocker_kk": _txt(d, "blocker", "kk"),
            "options": options,
            "options_missing": len(options) < 2,
            "decision_ru": _txt(d, "decision", "ru"), "decision_kk": _txt(d, "decision", "kk"),
            "temp_measure_ru": _txt(d, "temp_measure", "ru"), "temp_measure_kk": _txt(d, "temp_measure", "kk"),
            "demo": bool(r.get("demo")),
        }
        # kk нет — интерфейс покажет русский текст с пометкой (как у объектов без kk), а не пустое место.
        for key in ("problem", "blocker", "decision", "temp_measure"):
            item[f"{key}_kk_missing"] = item[f"{key}_ru"] is not None and item[f"{key}_kk"] is None
            if item[f"{key}_kk"] is None:
                item[f"{key}_kk"] = item[f"{key}_ru"]
        out.append(item)
    out.sort(key=lambda x: (-x["timer"]["overdue_by"], -x["people"], str(x["id"])))
    return out


def fixture_records(today: date) -> list[dict]:
    """Пример из fixtures/decisions_demo.json со сдвигом дат на (today − anchor)."""
    from .sources import _shift, _shift_days  # те же правила сдвига, что у фикстур объектов
    raw = json.loads(FIXTURE.read_text("utf-8"))
    days = _shift_days(raw.get("_meta", {}), today)
    out = []
    for r in raw.get("records", []):
        r = json.loads(json.dumps(r))
        r["created_at"] = _shift(r.get("created_at"), days)
        for h in r.get("status_history") or []:
            h["at"] = _shift(h.get("at"), days)
        out.append(r)
    return out
