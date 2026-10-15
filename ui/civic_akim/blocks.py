"""Блоки соседей для «Картины дня» 2.0, «Ситуационного центра» и «Картины недели» (R08, раунд 15).

Каждая функция берёт ответ соседа (neighbors.py) и отдаёт блок в одном виде для всех трёх экранов:
    {"available": False, "reason": "module_not_ready" | "module_failed" | "past_date", "source": …}  — блока нет;
    {"available": True, …, "demo": bool, "source": "r17" | "r16" | "r13" | "fixture" | "custom"}       — блок есть.
Экран прячет недоступный блок (или пишет «пока нет данных»), пустой — не показывает (правило CLEAN_PASS раунда 14).

ЧИСЛА НЕ ПЕРЕСЧИТЫВАЕМ (prompt R08 «НЕ ДЕЛАЙ»): у служб — числа R17 как есть (открытые, просроченные, медиана ответа,
«проверено жителями», «вернули жители», передачи); здесь только выбор «кого показать» и подписи ru/kk из таблицы
служб R08 (CONTRACT §3). Счёт записей соседа (сколько инициатив за неделю, сколько поручений просрочено) — это
отбор по датам из записей самого соседа в его формате (§5.2, §5.5, §5.7), не новая метрика.

ОПРЕДЕЛЕНИЯ (одним местом):
- Неделя — 7 суток до момента as_of (как «за 7 дней» в «Картине дня»); «ближайшие» — 7 суток после.
- Отстающие службы: порядок R17, если он его задал (rank / lagging); иначе — больше просроченных, потом доля
  просроченных среди открытых, потом медиана ответа. Только службы с открытыми обращениями.
- Инициативы недели: «сделано» за 7 дней (время отчёта, иначе окончания) и опубликованные, которые начнутся в
  ближайшие 7 дней. Участники — сумма «Я приду» (joined, только число — CONTRACT §10). На проверке — отдельно.
- «Двор недели»: двор самой многолюдной инициативы «сделано» за неделю; если таких нет — ближайшей.
- Поручения встреч: «просрочено» — срок (due, день по Астане) прошёл, статус не done; «на этой неделе» — срок в
  ближайшие 7 дней. Порядок: сначала просроченные (давние первыми), потом по сроку.
- Кризис: активный (status active), самый свежий по started_at; в районе — если зона кризиса в этом районе.
  Обновление жителям — последнее публичное (public: true); служебные заметки на большой экран не выводим.
- Прогноз: R13 на неделю, если функция есть; иначе прогноз раунда 14 на месяц с пометкой периода. Всегда «прототип».
"""
from __future__ import annotations

from datetime import date as Date, datetime, timedelta, timezone

from . import routing
from .neighbors import items_of, number

ASTANA_TZ = timezone(timedelta(hours=5))
WEEK = timedelta(days=7)
LAGGING_TOP = 3
BOARD_SERVICES = 8
ORDERS_TOP = 4
FORECAST_TOP = 5
DONE = {"done", "closed", "completed", "fixed"}
# Тема всплеска пульса → вид кризиса R17 (кнопка «Открыть кризисный штаб» с шаблоном, если кризиса ещё нет).
CRISIS_KIND = {"snow_ice": "blizzard"}
# Вид кризиса R17 (CONTRACT §5.5) → темы жалоб, тревоги по которым ведут в этот штаб. «other» — по району, любая тема.
CRISIS_TOPICS = {"blizzard": {"snow_ice"}, "heat_outage": {"utilities"}, "water_outage": {"utilities"},
                 "flood": {"utilities", "roads"}}


def _time(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=ASTANA_TZ)
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=ASTANA_TZ)


def _day(value) -> Date | None:
    if isinstance(value, Date) and not isinstance(value, datetime):
        return value
    t = _time(value)
    if t is not None and len(str(value)) > 10:
        return t.astimezone(ASTANA_TZ).date()
    try:
        return Date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _iso(dt: datetime | None) -> str | None:
    return dt.astimezone(ASTANA_TZ).isoformat(timespec="seconds") if dt else None


def missing(source: str) -> dict:
    return {"available": False, "reason": "module_failed" if source == "failed" else "module_not_ready", "source": source}


def past_date() -> dict:
    return {"available": False, "reason": "past_date"}


def service_names() -> dict:
    """id → {ru, kk, edited}: названия служб из таблицы R08 (с правками акимата) — единый справочник (CONTRACT §3)."""
    return routing.table()["services"]


def _service_ref(sid: str, names: dict) -> dict:
    n = names.get(sid) or {}
    return {"id": sid, "ru": n.get("ru") or sid, "kk": n.get("kk") or n.get("ru") or sid, "name_edited": bool(n.get("edited"))}


def _demo(rows) -> bool:
    return any(isinstance(r, dict) and r.get("demo") is True for r in rows or [])


# ---------------------------------------------------------------- ведомства (R17)

def agencies(board, board_src: str, joint=None, handoffs=None, *, as_of: datetime, days: int = 7) -> dict:
    """Табло служб R17 → «Ведомства»: службы как у R17, три отстающие, совместные, передачи за неделю."""
    if board is None:
        return missing(board_src)
    names = service_names()
    rows = items_of(board, "services", "board", "rows")
    services, ranked = [], False
    for row in rows:
        sid = row.get("service") or row.get("id") or row.get("service_id")
        if sid not in routing.SERVICES:  # новых id не придумываем (CONTRACT §3) — чужое не показываем
            continue
        share = number(row, "verified_share", "verified_ratio")
        if share is None:
            pct = number(row, "verified_pct", "verified_percent")
            share = pct / 100.0 if pct is not None else None
        item = {
            "service": _service_ref(sid, names),
            "total": number(row, "total", "complaints", "count"),
            "open": number(row, "open", "open_count", "in_work", "active"),
            "overdue": number(row, "overdue", "overdue_count", "late"),
            "median_answer_days": number(row, "median_answer_days", "median_days", "median_response_days"),
            "verified_share": round(share, 3) if isinstance(share, (int, float)) else None,
            "returned": number(row, "returned", "reopened", "returned_by_residents", "reopened_by_residents"),
            "handoffs_in": number(row, "handoffs_in", "received"),
            "handoffs_out": number(row, "handoffs_out", "passed"),
            "rank": number(row, "rank", "lag_rank"),
            "lagging": row.get("lagging") is True,
        }
        ranked = ranked or item["rank"] is not None or item["lagging"]
        services.append(item)
    if ranked:  # порядок R17 — главный
        lag = sorted((s for s in services if s["lagging"] or s["rank"] is not None),
                     key=lambda s: (s["rank"] if s["rank"] is not None else 1e9))
    else:
        def lag_key(s):
            open_, over = s["open"] or 0, s["overdue"] or 0
            return (-over, -(over / open_ if open_ else 0), -(s["median_answer_days"] or 0), s["service"]["id"])
        lag = sorted((s for s in services if (s["open"] or 0) > 0 and (s["overdue"] or 0) > 0), key=lag_key)
    # Табло для большого экрана: службы по нагрузке (открытые), не больше BOARD_SERVICES строк.
    by_load = sorted(services, key=lambda s: (-(s["open"] or 0), -(s["overdue"] or 0), s["service"]["id"]))
    joint_n = _joint_count(board, joint)
    hand_n = _handoffs_count(board, handoffs, as_of)
    return {
        "available": True, "days": number(board, "days") or days if isinstance(board, dict) else days,
        "board": by_load[:BOARD_SERVICES], "services_total": len(services),
        "lagging": lag[:LAGGING_TOP], "joint": joint_n, "handoffs_week": hand_n,
        "demo": bool(isinstance(board, dict) and board.get("demo")) or _demo(rows) or board_src == "fixture",
        "source": board_src,
    }


def _joint_count(board, joint):
    """Совместные в работе: из списка agencies/joint (не закрытые) или из поля табло R17."""
    rows = items_of(joint, "joint", "complaints")
    if rows:
        def finished(r):
            parts = r.get("services") if isinstance(r.get("services"), list) else []
            if r.get("status") in DONE | {"verified"}:
                return True
            return bool(parts) and all(isinstance(p, dict) and p.get("status") in DONE for p in parts)
        return sum(1 for r in rows if not finished(r))
    if isinstance(joint, dict):
        n = number(joint, "open", "count", "total")
        if n is not None:
            return int(n)
    if isinstance(board, dict):
        n = number(board, "joint_open", "joint")
        if n is not None:
            return int(n)
    return None


def _handoffs_count(board, handoffs, as_of: datetime):
    rows = items_of(handoffs, "handoffs")
    if rows:
        n = 0
        for r in rows:
            t = _time(r.get("at"))
            if t is not None and as_of - WEEK < t <= as_of:
                n += 1
        return n
    if isinstance(handoffs, dict):
        n = number(handoffs, "week", "count", "total")
        if n is not None:
            return int(n)
    if isinstance(board, dict):
        n = number(board, "handoffs_week", "handoffs")
        if n is not None:
            return int(n)
    return None


# ---------------------------------------------------------------- кризис (R17)

def _zone_districts(zone) -> list[str]:
    if not isinstance(zone, dict):
        return []
    out = [zone["district"]] if isinstance(zone.get("district"), str) else []
    out += [d for d in zone.get("districts") or [] if isinstance(d, str)]
    return out


def _incident(inc: dict, names: dict, district_names: dict, as_of: datetime) -> dict:
    started = _time(inc.get("started_at"))
    closed = _time(inc.get("closed_at")) if inc.get("status") == "closed" else None
    tasks = [t for t in inc.get("tasks") or [] if isinstance(t, dict)]
    by_service: dict = {}
    for t in tasks:
        sid = t.get("service") if t.get("service") in routing.SERVICES else "akimat"
        row = by_service.setdefault(sid, {"service": _service_ref(sid, names), "total": 0, "done": 0, "doing": 0})
        row["total"] += 1
        row["done"] += int(t.get("status") in DONE)
        row["doing"] += int(t.get("status") == "doing" or t.get("status") == "in_progress")
    updates = sorted((u for u in inc.get("updates") or [] if isinstance(u, dict) and u.get("public") is not False
                      and _time(u.get("at")) is not None and _time(u.get("at")) <= as_of),
                     key=lambda u: _time(u["at"]), reverse=True)
    zone = inc.get("zone") if isinstance(inc.get("zone"), dict) else {}
    dists = _zone_districts(zone)
    result = inc.get("result") if isinstance(inc.get("result"), dict) else None
    return {
        "id": inc.get("id"), "kind": inc.get("kind"), "status": inc.get("status"),
        "title_ru": inc.get("title_ru") or inc.get("title") or inc.get("id"),
        "title_kk": inc.get("title_kk") or inc.get("title_ru") or inc.get("title") or inc.get("id"),
        "zone": {"kind": zone.get("kind"), "districts": [{"id": d, **(district_names.get(d) or {"ru": d, "kk": d})} for d in dists],
                 "targets": len(zone.get("targets") or []), "approximate": zone.get("kind") == "polygon"},
        # Сколько часов идёт кризис (у закрытого — сколько длился).
        "started_at": _iso(started),
        "hours": int(((closed or as_of) - started).total_seconds() // 3600) if started else None,
        "closed_at": _iso(closed),
        "tasks_total": len(tasks), "tasks_done": sum(r["done"] for r in by_service.values()),
        "tasks_doing": sum(r["doing"] for r in by_service.values()),
        "services": sorted(by_service.values(), key=lambda r: (r["done"] == r["total"], -r["total"], r["service"]["id"])),
        "last_update": ({"at": _iso(_time(updates[0]["at"])), "text_ru": updates[0].get("text_ru"),
                         "text_kk": updates[0].get("text_kk") or updates[0].get("text_ru")} if updates else None),
        "updates_public": len(updates),
        "result": ({"text_ru": result.get("text_ru"), "text_kk": result.get("text_kk") or result.get("text_ru")}
                   if result else None),
        "demo": inc.get("demo") is True,
    }


def crisis(answer, src: str, *, as_of: datetime, district: str | None, district_names: dict) -> dict:
    if answer is None:
        return missing(src)
    names = service_names()
    rows = items_of(answer, "incidents")
    if district:
        rows = [r for r in rows if district in _zone_districts(r.get("zone"))]
    active = [r for r in rows if r.get("status") == "active" and (_time(r.get("started_at")) or as_of) <= as_of]
    active.sort(key=lambda r: _time(r.get("started_at")) or as_of, reverse=True)
    closed_week = [r for r in rows if r.get("status") == "closed"
                   and (t := _time(r.get("closed_at") or r.get("updated_at"))) is not None and as_of - WEEK < t <= as_of]
    return {
        "available": True,
        "active": _incident(active[0], names, district_names, as_of) if active else None,
        "active_count": len(active),
        "others": [_incident(r, names, district_names, as_of) for r in active[1:3]],
        "closed_week": [_incident(r, names, district_names, as_of) for r in closed_week[:3]],
        "demo": _demo(rows) or src == "fixture", "source": src,
    }


def crisis_links(pulse_items: list[dict], crisis_part: dict) -> None:
    """У тревоги пульса — кнопка «Открыть кризисный штаб» (R17): есть активный кризис в её районе → ссылка на него;
    нет, но тема кризисная (снег) и штаб R17 подключён → шаблон нового кризиса (вид и район). Меняет список на месте."""
    if not crisis_part.get("available"):
        return
    active = [crisis_part.get("active")] + list(crisis_part.get("others") or [])
    active = [a for a in active if a]
    for alarm in pulse_items:
        alarm_districts = [alarm["district"]] if alarm.get("district") else \
            [row["district"] for row in alarm.get("districts") or []]

        def related(a):
            # Та же тема (буран ↔ «Снег и гололёд») и тот же район: «Дороги» в Нуре не ведут в штаб бурана.
            topics = CRISIS_TOPICS.get(a.get("kind"))
            if topics is not None and alarm.get("category") not in topics:
                return False
            zone = {d["id"] for d in a["zone"]["districts"]}
            return not alarm_districts or not zone or bool(zone & set(alarm_districts))
        match = next((a for a in active if related(a)), None)
        if match:
            alarm["crisis"] = {"id": match["id"], "title_ru": match["title_ru"], "title_kk": match["title_kk"]}
        elif alarm.get("category") in CRISIS_KIND:
            alarm["crisis_new"] = {"kind": CRISIS_KIND[alarm["category"]],
                                   "district": alarm.get("district") or (alarm_districts[0] if alarm_districts else None)}


# ---------------------------------------------------------------- жители вместе (R16 + R09)

def _initiative(i: dict, members: dict) -> dict:
    target = i.get("target") if isinstance(i.get("target"), dict) else {}
    report = i.get("report") if isinstance(i.get("report"), dict) else None
    support = i.get("support") if isinstance(i.get("support"), dict) else None
    title = i.get("title")
    return {
        "id": i.get("id"), "kind": i.get("kind"), "status": i.get("status"),
        "title_ru": i.get("title_ru") or (title if isinstance(title, str) else None) or i.get("id"),
        "title_kk": i.get("title_kk") or i.get("title_ru") or (title if isinstance(title, str) else None) or i.get("id"),
        "title_kk_missing": not i.get("title_kk"),
        "target": {k: target.get(k) for k in ("kind", "id", "label_ru", "label_kk")} if target.get("id") else None,
        "district": i.get("district"), "starts_at": i.get("starts_at"), "ends_at": i.get("ends_at"),
        "joined": int(number(i, "joined") or 0),
        "supported": bool(support and support.get("by_akimat")),
        "done_at": (report or {}).get("at") or (i.get("ends_at") if i.get("status") == "done" else None),
        "yard_members": members.get(target.get("id")) if target.get("id") else None,
        "demo": i.get("demo") is True,
    }


def together(answer, src: str, yards=None, *, as_of: datetime, district: str | None, kpi: dict | None) -> dict:
    """«Жители вместе»: инициативы недели и участники (R16), «проверено жителями» за неделю (R09 — из KPI «Картины дня»)."""
    fixed = (kpi or {}).get("fixed_week") or {}
    verified = {"value": fixed.get("verified"), "fixed": fixed.get("value"),
                "available": bool((kpi or {}).get("verification_available"))}
    if answer is None:
        out = missing(src)
        out["verified"] = verified  # R09 есть, R16 нет — «проверено жителями» всё равно показываем
        return out
    members = {y.get("id"): int(number(y, "members") or 0) for y in items_of(yards, "yards") if y.get("id")}
    rows = items_of(answer, "initiatives")
    if district:
        rows = [r for r in rows if r.get("district") == district]
    items = [_initiative(r, members) for r in rows]
    done_week, upcoming = [], []
    for it in items:
        if it["status"] == "done":
            t = _time(it["done_at"]) or _time(it["starts_at"])
            if t is not None and as_of - WEEK < t <= as_of:
                done_week.append(it)
        elif it["status"] == "published":
            t = _time(it["starts_at"])
            # Началась сегодня (ещё идёт) или начнётся в ближайшие 7 дней.
            if t is not None and as_of - timedelta(hours=12) <= t <= as_of + WEEK:
                upcoming.append(it)
    done_week.sort(key=lambda x: (-x["joined"], str(x["id"])))
    upcoming.sort(key=lambda x: (_time(x["starts_at"]), -x["joined"], str(x["id"])))
    star = max(done_week, key=lambda x: (x["joined"], str(x["id"])), default=None) or \
        max(upcoming, key=lambda x: (x["joined"], str(x["id"])), default=None)
    return {
        "available": True,
        "done_week": len(done_week), "people_done": sum(x["joined"] for x in done_week),
        "upcoming": len(upcoming), "people_upcoming": sum(x["joined"] for x in upcoming),
        "supported": sum(1 for x in done_week + upcoming if x["supported"]),
        "on_review": sum(1 for x in items if x["status"] == "on_review"),
        "done_items": done_week[:3], "upcoming_items": upcoming[:3],
        "yard_of_week": star,
        "verified": verified,
        "demo": _demo(rows) or src == "fixture", "source": src,
    }


# ---------------------------------------------------------------- встречи (R13)

def meetings(answer, src: str, *, as_of: datetime, district: str | None, district_names: dict) -> dict:
    if answer is None:
        return missing(src)
    names = service_names()
    rows = items_of(answer, "meetings")
    if district:
        rows = [m for m in rows if m.get("district") == district]
    today = as_of.astimezone(ASTANA_TZ).date()
    orders = []
    for m in rows:
        ref = {"id": m.get("id"), "title_ru": m.get("title_ru"), "title_kk": m.get("title_kk") or m.get("title_ru"),
               "district": m.get("district"), "at": m.get("at")}
        for o in m.get("orders") or []:
            if not isinstance(o, dict):
                continue
            due = _day(o.get("due"))
            status = o.get("status") or "todo"
            done = status in DONE
            sid = o.get("service") if o.get("service") in routing.SERVICES else None
            orders.append({
                "id": f"{m.get('id')}/{o.get('id')}", "text_ru": o.get("text_ru"), "text_kk": o.get("text_kk") or o.get("text_ru"),
                "service": _service_ref(sid, names) if sid else None, "due": due.isoformat() if due else None,
                "status": status, "done": done,
                "overdue": bool(due and not done and due < today),
                "days_left": (due - today).days if due else None,
                "link": o.get("link") if isinstance(o.get("link"), dict) else None,
                "meeting": ref, "demo": m.get("demo") is True,
            })
    open_orders = [o for o in orders if not o["done"]]
    open_orders.sort(key=lambda o: (not o["overdue"], o["due"] or "9999", o["id"]))
    future = sorted((m for m in rows if (_time(m.get("at")) or as_of) > as_of), key=lambda m: _time(m.get("at")))
    nxt = future[0] if future else None
    return {
        "available": True, "meetings": len(rows),
        "orders": {"total": len(orders), "done": sum(o["done"] for o in orders),
                   "in_progress": sum(o["status"] == "in_progress" for o in orders),
                   "todo": sum(o["status"] == "todo" for o in orders),
                   "overdue": sum(o["overdue"] for o in orders),
                   "due_week": sum(1 for o in open_orders if o["days_left"] is not None and 0 <= o["days_left"] <= 7)},
        "items": open_orders[:ORDERS_TOP],
        "next": ({"id": nxt.get("id"), "title_ru": nxt.get("title_ru"), "title_kk": nxt.get("title_kk") or nxt.get("title_ru"),
                  "district": nxt.get("district"), "district_ru": (district_names.get(nxt.get("district")) or {}).get("ru"),
                  "district_kk": (district_names.get(nxt.get("district")) or {}).get("kk"),
                  "at": nxt.get("at"), "registered": int(number(nxt, "registered") or 0),
                  "questions": len(nxt.get("questions") or []),
                  "place_ru": (nxt.get("place") or {}).get("label_ru") if isinstance(nxt.get("place"), dict) else None,
                  "place_kk": (nxt.get("place") or {}).get("label_kk") if isinstance(nxt.get("place"), dict) else None}
                 if nxt else None),
        "demo": _demo(rows) or src == "fixture", "source": src,
    }


# ---------------------------------------------------------------- прогноз (R13, прототип)

def forecast(answer, src: str, period: str) -> dict:
    if answer is None:
        return missing(src)
    items = []
    for it in items_of(answer, "items")[:FORECAST_TOP]:
        target = it.get("target") if isinstance(it.get("target"), dict) else {}
        reasons = [r for r in (it.get("reasons") or it.get("top_reasons") or []) if isinstance(r, dict)]
        items.append({
            "target": {k: target.get(k) for k in ("kind", "id", "label_ru", "label_kk")} if target.get("id") else None,
            "level": it.get("level"), "risk": number(it, "risk"),
            "category": it.get("main_category") or it.get("category"), "district": it.get("district"),
            "reason_ru": reasons[0].get("ru") if reasons else None,
            "reason_kk": (reasons[0].get("kk") or reasons[0].get("ru")) if reasons else None,
        })
    a = answer if isinstance(answer, dict) else {}
    return {
        "available": True, "prototype": True, "period": a.get("period") or period,
        "month": a.get("month"), "week": a.get("week"),
        "evidence_type": a.get("evidence_type") or "synthetic",
        "note_ru": a.get("note_ru") or "Прототип: модель обучена на синтетической истории. Не реальная оценка риска.",
        "note_kk": a.get("note_kk") or "Прототип: модель синтетикалық тарихи деректерде оқытылған. Нақты тәуекел бағасы емес.",
        "items": items, "demo": True, "source": src,
    }
