"""«Ситуационный центр» (R08, раунд 15): GET /api/civic/v2/akim/board?district=<id> — один ответ для большого экрана.

Откуда числа (ни одного противоречия с картой и «Картиной дня»):
- KPI, пульс, горячие места, районы, «Нужно решение акима» — ровно «Картина дня» на сегодня (summary.py), а она
  берёт места и районы у тепловой карты R07 тем же вызовом, что отвечает карте;
- ведомства и кризис (R17), жители вместе (R16 + «проверено жителями» R09), поручения встреч и прогноз (R13) — те же
  блоки, что «Картина дня» 2.0 (blocks.py), то есть числа соседей как есть.
Здесь только форма для большого экрана: что крупно, что в ленте сменяющихся блоков и в каком порядке.

Блоки ленты (stage) сменяются на экране каждые ROTATE_S секунд; в ленту попадают только блоки с данными:
    crisis (активный кризис) → agencies (табло служб) → together (жители вместе) → meetings (поручения встреч) →
    forecast (прогноз, прототип). Пульс и горячие места на экране всегда, кризис ещё и полосой сверху.
"""
from __future__ import annotations

from datetime import datetime

from .summary import districts, iso

ROTATE_S = 15      # смена блока ленты, секунд (prompt R08: каждые 15 с)
REFRESH_S = 60     # тихое обновление данных экраном, секунд
HOT_TOP = 5
PULSE_TOP = 3
STAGE = ("crisis", "agencies", "together", "meetings", "forecast")


def _has(name: str, part: dict) -> bool:
    """Есть ли что показать в блоке ленты (пустое не показываем)."""
    if not part or not part.get("available"):
        return False
    if name == "crisis":
        return bool(part.get("active"))
    if name == "agencies":
        return bool(part.get("board"))
    if name == "together":
        return bool(part.get("done_week") or part.get("upcoming") or part.get("yard_of_week"))
    if name == "meetings":
        return bool(part.get("orders", {}).get("total") or part.get("next"))
    if name == "forecast":
        return bool(part.get("items"))
    return True


def _kpi(s: dict) -> dict:
    k = s.get("kpi") or {}

    def tile(key: str, extra: tuple = ()) -> dict:
        ch = k.get(key) or {}
        out = {"id": key, **{f: ch.get(f) for f in ("value", "prev", "abs", "pct", "ratio", "trend", "mode")},
               "series": list(ch.get("series") or [])}
        for f in extra:
            out[f] = ch.get(f)
        return out

    return {
        "available": s.get("complaints_available") is not False,
        "items": [tile("new_day"), tile("in_progress", ("waiting",)), tile("overdue"),
                  tile("fixed_week", ("verified", "awaiting", "reopened", "reopened_by_residents"))],
        "new_week": {f: (k.get("new_week") or {}).get(f) for f in ("value", "prev", "abs", "pct", "ratio", "trend", "mode")},
        "verification_available": bool(k.get("verification_available")),
    }


def build(svc, *, district=None, now: datetime) -> dict:
    s = svc.summary(date=None, district=district, now=now)
    hot = s.get("hot") or {}
    pulse = s.get("pulse") or {}
    dec = s.get("decisions") or {}
    dist = s.get("districts") or {}
    parts = {name: s.get(name) or {"available": False, "reason": "module_not_ready"} for name in STAGE}
    stage = [name for name in STAGE if _has(name, parts[name])]
    d_info = districts().get(district) if district else None
    demo = dict(s.get("demo") or {})
    return {
        "generated_at": s.get("generated_at") or iso(now),
        "as_of": s.get("as_of"),
        "date": s.get("date"),
        "compare_to": s.get("compare_to"),
        "district": d_info,
        "rotate_s": ROTATE_S,
        "refresh_s": REFRESH_S,
        "kpi": _kpi(s),
        "hot": {"available": bool(hot.get("available")), "days": hot.get("days"),
                "items": list(hot.get("items") or [])[:HOT_TOP]},
        "districts": {"available": bool(dist.get("available")), "selected": district,
                      "items": [{k: r.get(k) for k in ("district", "ru", "kk", "value", "prev", "trend", "mode", "abs", "pct", "ratio")}
                                for r in dist.get("items") or []]},
        "main_problem": s.get("main_problem"),
        "pulse": {"available": bool(pulse.get("available")), "items": list(pulse.get("items") or [])[:PULSE_TOP],
                  "more": max(0, len(pulse.get("items") or []) - PULSE_TOP)},
        "decisions": {"available": bool(dec.get("available")), "count": int(dec.get("count") or 0),
                      "demo": bool(dec.get("demo")),
                      "items": [{k: it.get(k) for k in ("id", "problem_ru", "problem_kk", "district", "category")}
                                for it in (dec.get("items") or [])[:3]]},
        **parts,
        "stage": stage,
        "summary_text": s.get("text"),
        "demo": demo,
        "sources": s.get("sources"),
        "compute_ms": s.get("compute_ms"),
    }
