"""Ситуационный центр акимата (раунд 15): GET /api/civic/v2/akim/board — всё для большого экрана одним ответом.

Откуда числа (R08 ничего не считает заново — только собирает и выбирает, что показать):
- KPI, мини-графики, пульс, горячие места, темы, районы, «Нужно решение акима» — summary() «Картины дня»
  на сегодня (те же числа, что на карте R07 и в «Картине дня»: один расчёт, общий кэш);
- «Ведомства» и кризис — R17; «Жители вместе» — R16 (инициативы) и R09 («проверено жителями» из KPI);
  поручения встреч и прогноз — R13. Как читаются соседи и что бывает, если соседа нет, — neighbors.py.

Каждый блок необязателен: {"available": false, "reason": …} — экран блок не показывает или пишет «пока нет данных».
Слайды правой части экрана (сменяются каждые ROTATE_S секунд) — только блоки, в которых есть что показать;
«Темы недели» и «Районы» есть всегда, когда есть карта, поэтому экран не бывает пустым.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime

from . import neighbors

ROTATE_S = 15        # смена блоков на экране (промпт R08 п. 2)
REFRESH_S = 60       # как часто экран спрашивает новые числа
HOT_N = 5
TOPICS_N = 6
DECISIONS_N = 3
CACHE_TTL_S = 15.0

_cache: dict = {}
_cache_lock = threading.Lock()


def reset_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _kpi(s: dict) -> dict:
    k = s.get("kpi") or {}
    keep = ("value", "prev", "abs", "pct", "ratio", "trend", "mode", "series")
    out = {name: {f: (k.get(name) or {}).get(f) for f in keep} for name in ("new_day", "in_progress", "overdue", "fixed_week")}
    out["in_progress"]["waiting"] = (k.get("in_progress") or {}).get("waiting")
    fw = k.get("fixed_week") or {}
    out["fixed_week"].update(verified=fw.get("verified"), awaiting=fw.get("awaiting"),
                             reopened_by_residents=fw.get("reopened_by_residents"))
    out["new_week"] = {f: (k.get("new_week") or {}).get(f) for f in keep if f != "series"}
    out["verification_available"] = bool(k.get("verification_available"))
    return out


def _hot(s: dict) -> dict:
    hot = s.get("hot") or {}
    if not hot.get("available"):
        return {"available": False, "reason": hot.get("reason") or "heat_unavailable", "items": []}
    keep = ("rank", "target", "count", "level", "color", "status", "district", "category", "subtopic", "approximate", "demo")
    return {"available": True, "days": hot.get("days"),
            "items": [{f: it.get(f) for f in keep} for it in (hot.get("items") or [])[:HOT_N]]}


def _topics(s: dict) -> dict:
    t = s.get("topics") or {}
    if not t.get("available"):
        return {"available": False, "reason": t.get("reason") or "heat_unavailable", "items": []}
    return {"available": True, "days": t.get("days"), "total": t.get("total"), "items": (t.get("items") or [])[:TOPICS_N]}


def _districts(s: dict) -> dict:
    d = s.get("districts") or {}
    if not d.get("available"):
        return {"available": False, "reason": d.get("reason") or "heat_unavailable", "items": []}
    return {"available": True, "days": d.get("days"), "selected": d.get("selected"), "items": d.get("items") or []}


def compact_decisions(s: dict, limit: int = DECISIONS_N) -> dict:
    """«Нужно решение акима» коротко (VISUAL_BRIEF §3): проблема → варианты → кнопка. Длинные абзацы — в «Картине дня»."""
    part = s.get("decisions") or {}
    items = []
    for it in (part.get("items") or [])[:limit]:
        place = it.get("place_ru") and {"ru": it.get("place_ru"), "kk": it.get("place_kk") or it.get("place_ru")}
        items.append({
            "id": it.get("id"),
            "problem_ru": it.get("problem_ru"), "problem_kk": it.get("problem_kk") or it.get("problem_ru"),
            "place": place or None,
            "overdue_by": (it.get("timer") or {}).get("overdue_by"), "unit": (it.get("timer") or {}).get("unit"),
            "service": it.get("service"), "people": it.get("people"),
            "options": [{"n": n, "ru": o.get("ru"), "kk": o.get("kk") or o.get("ru")}
                        for n, o in enumerate(it.get("options") or [], start=1) if isinstance(o, dict)],
            "chosen": it.get("chosen"), "demo": bool(it.get("demo") or part.get("demo")),
        })
    return {"available": bool(part.get("available")), "count": part.get("count") or 0, "items": items,
            "demo": bool(part.get("demo"))}


def _slides(b: dict) -> list[str]:
    """Порядок слайдов правой части. Пустые блоки не показываем — на большом экране не бывает «пока нет данных»."""
    out = []
    if (b["crisis"].get("active") or []):
        out.append("crisis")
    if b["services"].get("available") and b["services"].get("items"):
        out.append("services")
    if b["decisions"]["count"]:
        out.append("decisions")
    t = b["together"]
    if t.get("available") and (t.get("top") or t.get("yard_of_week")):
        out.append("together")
    if b["meetings"].get("available") and (b["meetings"].get("orders") or b["meetings"].get("next")):
        out.append("meetings")
    if b["forecast"].get("available") and b["forecast"].get("items"):
        out.append("forecast")
    if b["topics"].get("available") and b["topics"].get("items"):
        out.append("topics")
    if b["districts"].get("available") and b["districts"].get("items"):
        out.append("districts")
    return out


def build(service, *, district=None, now: datetime | None = None) -> dict:
    """Ответ akim/board. service — AkimService (summary + настройки соседей)."""
    now = now or service._clock()
    s = service.summary(date=None, district=district, now=now)
    gen = getattr(service.heat, "generation", None) if service.heat is not None else None
    d_id = (s.get("district") or {}).get("id")
    key = (d_id, int(now.timestamp() // CACHE_TTL_S), gen, id(service))
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            return hit[1]
    started = time.perf_counter()
    settings = service.neighbors
    all_demo = service.source_names.get("complaints") == "r07-demo"
    crisis = neighbors.incidents(settings, district=d_id, now=now, all_demo=all_demo)
    pulse = s.get("pulse") or {"available": False, "items": []}
    pulse = {**pulse, "items": [dict(a) for a in pulse.get("items") or []]}
    neighbors.pulse_links(pulse["items"], crisis)
    together = neighbors.together(settings, district=d_id, now=now, all_demo=all_demo)
    fw = (s.get("kpi") or {}).get("fixed_week") or {}
    # «Проверено жителями» (R09) — то же число, что в KPI «Исправлено за 7 дней»; R08 его не пересчитывает.
    together["verified_week"] = fw.get("verified") if (s.get("kpi") or {}).get("verification_available") else None
    board = {
        "generated_at": s.get("generated_at"), "as_of": s.get("as_of"), "date": s.get("date"),
        "district": s.get("district"), "rotate_s": ROTATE_S, "refresh_s": REFRESH_S,
        "complaints_available": s.get("complaints_available"), "empty": s.get("empty"),
        "kpi": _kpi(s), "pulse": pulse, "hot": _hot(s), "topics": _topics(s), "districts": _districts(s),
        "decisions": compact_decisions(s),
        "services": neighbors.agencies_board(settings, district=d_id, now=now, all_demo=all_demo),
        "crisis": crisis,
        "together": together,
        "meetings": neighbors.meetings(settings, district=d_id, now=now, all_demo=all_demo),
        "forecast": neighbors.forecast(settings, district=d_id, now=now),
    }
    board["slides"] = _slides(board)
    blocks = ("services", "crisis", "together", "meetings", "forecast")
    board["demo"] = {**{k: bool(v) for k, v in (s.get("demo") or {}).items()},
                     **{name: bool(board[name].get("demo")) for name in blocks}}
    board["demo"]["any"] = any(board["demo"].values())
    board["sources"] = {**(s.get("sources") or {}), **{name: board[name].get("source", "none") for name in blocks},
                        "demo_world": settings.demo_world}
    board["compute_ms"] = round((time.perf_counter() - started) * 1000 + float(s.get("compute_ms") or 0), 1)
    with _cache_lock:
        if len(_cache) > 16:
            _cache.clear()
        _cache[key] = (time.monotonic(), board)
    return board
