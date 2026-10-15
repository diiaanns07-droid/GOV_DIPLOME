"""Табло служб, совместные обращения и журнал передач — чистые функции над записями жалоб (CONTRACT §5.1).

Ничего не пишет и не хранит: записи даёт R09 (только чтение) или фикстура R17 в том же формате.

МЕТОД РАСЧЁТА ТАБЛО (то же — в research/round-15-results/R17/DELIVERY.json, поле method)
Единица счёта — ОБРАЩЕНИЕ (жалоба), а не место: у одной цели может быть несколько обращений. Дубли
(duplicate_of) не считаются нигде — как в «Обращениях» R09. Часть службы — запись services[] (§5.1);
у старой записи без services[] одна часть: ведущая служба, статус части = статус жалобы.

Сейчас (без фильтра периода — как вкладки «Обращений»):
  open      — обращения, где у службы открытая часть (не done и не rejected);
  overdue   — из них просроченные по правилу R09 (lifecycle.inbox_tab = "overdue": срок ответа прошёл,
              а ответа нет, или прошла обещанная дата обновления); срок не обнуляется передачей;
  deadline  — те же открытые части по состоянию срока ответа R09: overdue | today | ok | answered;
  places    — сколько разных мест (целей) у открытых частей.
За период (обращения, поданные за последние days дней; передачи — по времени передачи):
  received            — обращений с частью этой службы;
  median_answer_days  — медиана рабочих дней РК от подачи до первого ответа (первый статус, кроме «new»),
                        только обращения, где служба ведущая; рабочие дни — календарь R09 (holidays_kz.json);
  fixed / verified    — части «сделано» / из них обращение «проверено жителями» (resolution.state = verified);
  verified_share      — verified / fixed (нет fixed — null, а не 0 %);
  returned            — «вернули жители»: ведущая служба, у обращения был возврат жителями (reopen_count > 0);
  joint               — обращения с двумя и более службами, где участвует эта служба;
  handoffs_in / _out  — передачи в службу / из службы за период.
Людей и сотрудников не оцениваем и не сравниваем — только службы (IDEA §4).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median

from . import profiles

ASTANA = timezone(timedelta(hours=5))
OPEN_COMPLAINT = ("new", "accepted", "in_progress")
PART_DONE = frozenset({"done", "fixed"})
PART_CLOSED = frozenset({"done", "fixed", "rejected", "cancelled", "removed"})
# Статус части по статусу жалобы — для старых записей без services[] (одна служба).
PART_FROM_STATUS = {"new": "new", "accepted": "accepted", "in_progress": "in_progress", "fixed": "done",
                    "rejected": "rejected"}
DEADLINE_STATES = ("overdue", "today", "ok", "answered")


# ---------------------------------------------------------------- время
def parse_iso(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=ASTANA)


def iso(moment: datetime) -> str:
    return moment.astimezone(ASTANA).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- правила R09 (с запасным вариантом)
def _lifecycle():
    try:
        from ui.civic_feedback.v2 import lifecycle  # type: ignore
        return lifecycle
    except Exception:  # noqa: BLE001 — R09 нет в сборке: правила ниже повторяют его смысл
        return None


def _workdays():
    try:
        from ui.civic_feedback.v2 import workdays  # type: ignore
        return workdays
    except Exception:  # noqa: BLE001
        return None


def working_days(start: datetime, end: datetime) -> int:
    """Рабочие дни РК между датами (start, end] — календарь R09; без него — только выходные."""
    wd = _workdays()
    a, b = start.astimezone(ASTANA).date(), end.astimezone(ASTANA).date()
    if wd is not None:
        return wd.working_days_between(a, b)
    count, day = 0, a
    while day < b:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return count


def deadline_state(record: dict, now: datetime) -> dict | None:
    """Состояние срока ответа жителю (R09 lifecycle.deadline): {state, working_days_left, overdue_working_days, due_at}."""
    lc = _lifecycle()
    if lc is not None:
        try:
            return lc.deadline(record, now)
        except Exception:  # noqa: BLE001 — запись не в формате R09: считаем сами
            pass
    due = parse_iso(record.get("due_at"))
    if due is None:
        return None
    if record.get("status") != "new":
        return {"state": "answered", "due_at": due.isoformat(), "working_days_left": None, "overdue_working_days": None}
    if now <= due:
        left = working_days(now, due)
        return {"state": "today" if left == 0 else "ok", "due_at": due.isoformat(), "working_days_left": left,
                "overdue_working_days": None}
    return {"state": "overdue", "due_at": due.isoformat(), "working_days_left": None,
            "overdue_working_days": max(1, working_days(due, now))}


def inbox_tab(record: dict, now: datetime) -> str | None:
    """Вкладка «Обращений» R09 для жалобы (overdue, reopened, new, in_progress, waiting_check) или None."""
    lc = _lifecycle()
    if lc is not None:
        try:
            return lc.inbox_tab(record, now)
        except Exception:  # noqa: BLE001
            pass
    if record.get("duplicate_of"):
        return None
    status = record.get("status")
    state = (record.get("resolution") or {}).get("state")
    if status in OPEN_COMPLAINT and state == "reopened":
        return "reopened"
    if status in OPEN_COMPLAINT:
        info = deadline_state(record, now) or {}
        if info.get("state") == "overdue":
            return "overdue"
        return "new" if status == "new" else "in_progress"
    if status == "fixed" and state == "reported":
        return "waiting_check"
    return None


# ---------------------------------------------------------------- приведение записи к частям служб
def lead_service(record: dict, lookup=None) -> str | None:
    """Ведущая служба: поле service (§5.1) → выбор сотрудника в паспорте → таблица R08 → таблица R09."""
    sid = record.get("service")
    if sid in profiles.PROFILES:
        return sid
    sid = (record.get("passport") or {}).get("assignee_id")
    if sid in profiles.PROFILES:
        return sid
    category, subtopic = record.get("category"), record.get("subtopic")
    if lookup is not None:
        try:
            found = lookup(category, subtopic)
            sid = found.get("id") if isinstance(found, dict) else None
            if sid in profiles.PROFILES:
                return sid
        except Exception:  # noqa: BLE001 — таблица R08 недоступна: правило R09
            pass
    lc = _lifecycle()
    if lc is not None:
        try:
            sid = lc.default_service(category, subtopic)
            if sid in profiles.PROFILES:
                return sid
        except Exception:  # noqa: BLE001
            pass
    return "akimat" if category else None


def parts_of(record: dict, lookup=None) -> list[dict]:
    """Части служб: services[] из §5.1 или одна часть ведущей службы. Неизвестные id служб пропускаются."""
    parts, seen = [], set()
    for item in record.get("services") or []:
        if not isinstance(item, dict) or item.get("service") not in profiles.PROFILES or item["service"] in seen:
            continue
        seen.add(item["service"])
        status = str(item.get("status") or "new")
        parts.append({"service": item["service"], "role": "lead" if item.get("role") == "lead" else "partner",
                      "status": "done" if status == "fixed" else status, "updated_at": item.get("updated_at")})
    if parts:
        if not any(p["role"] == "lead" for p in parts):
            lead = lead_service(record, lookup)
            for p in parts:
                if p["service"] == lead:
                    p["role"] = "lead"
        return parts
    lead = lead_service(record, lookup)
    if lead is None:
        return []
    return [{"service": lead, "role": "lead", "status": PART_FROM_STATUS.get(record.get("status"), "new"),
             "updated_at": None}]


def answered_at(record: dict) -> datetime | None:
    """Первый ответ службы: первый статус в истории, кроме «new» (так же R09 считает «ответ дан»)."""
    for entry in record.get("status_history") or []:
        if isinstance(entry, dict) and entry.get("status") not in (None, "new"):
            return parse_iso(entry.get("at"))
    return None


def handoffs_of(record: dict) -> list[dict]:
    out = []
    for item in record.get("handoffs") or []:
        if not isinstance(item, dict):
            continue
        at = parse_iso(item.get("at"))
        if at is None or item.get("from") not in profiles.PROFILES or item.get("to") not in profiles.PROFILES:
            continue
        out.append({"at": at, "from": item["from"], "to": item["to"], "reason": str(item.get("reason") or "")[:300],
                    "by_role": str(item.get("by_role") or "operator")[:32]})
    out.sort(key=lambda h: h["at"])
    return out


def loop_flags(handoffs: list[dict]) -> list[bool]:
    """«Передачи по кругу»: служба получает обращение обратно после того, как сама его передала (A→B, B→A)."""
    handed, flags = set(), []
    for h in handoffs:
        flags.append(h["to"] in handed)
        handed.add(h["from"])
    return flags


def _usable(records, district: str | None) -> list[dict]:
    out = []
    for record in records or []:
        if not isinstance(record, dict) or record.get("duplicate_of"):
            continue
        if district and record.get("district") != district:
            continue
        out.append(record)
    return out


def _share(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


# ---------------------------------------------------------------- табло
def board(records, now: datetime, *, days: int = 30, district: str | None = None, lookup=None) -> dict:
    """Табло всех 20 служб (порядок — справочник CONTRACT §3). См. МЕТОД РАСЧЁТА в шапке файла."""
    since = now - timedelta(days=days)
    rows = {sid: {"service": sid, "open": 0, "overdue": 0, "deadline": {s: 0 for s in DEADLINE_STATES},
                  "places": 0, "received": 0, "answered": 0, "median_answer_days": None, "fixed": 0,
                  "verified": 0, "verified_share": None, "returned": 0, "joint": 0,
                  "handoffs_in": 0, "handoffs_out": 0} for sid in profiles.SERVICE_IDS}
    places = {sid: set() for sid in rows}
    answer_days = {sid: [] for sid in rows}
    totals = {"open": 0, "overdue": 0, "received": 0, "joint": 0, "handoffs": 0, "loops": 0, "fixed": 0,
              "verified": 0, "returned": 0}
    demo_only, any_record = True, False
    for record in _usable(records, district):
        any_record = True
        demo_only = demo_only and bool(record.get("demo"))
        parts = parts_of(record, lookup)
        if not parts:
            continue
        tab = inbox_tab(record, now)
        info = deadline_state(record, now) or {}
        created = parse_iso(record.get("created_at"))
        in_period = created is not None and created >= since
        target = (record.get("target") or {}).get("id") or record.get("id")
        resolution = record.get("resolution") or {}
        verified = resolution.get("state") == "verified"
        returned = int(resolution.get("reopen_count") or 0) > 0 or resolution.get("state") == "reopened"
        joint = len(parts) >= 2
        open_any = False
        for part in parts:
            row = rows[part["service"]]
            if part["status"] not in PART_CLOSED:
                open_any = True
                row["open"] += 1
                places[part["service"]].add(target)
                if tab == "overdue":
                    row["overdue"] += 1
                    row["deadline"]["overdue"] += 1
                else:
                    # Нет срока у записи (старый импорт) — считаем «в срок», чтобы полоса сходилась с числом open.
                    state = info.get("state")
                    row["deadline"][state if state in ("today", "ok", "answered") else "ok"] += 1
            if not in_period:
                continue
            row["received"] += 1
            if joint:
                row["joint"] += 1
            if part["status"] in PART_DONE:
                row["fixed"] += 1
                if verified:
                    row["verified"] += 1
            if part["role"] == "lead":
                if returned:
                    row["returned"] += 1
                first = answered_at(record)
                if first is not None and created is not None and first >= created:
                    answer_days[part["service"]].append(working_days(created, first))
        if open_any:
            totals["open"] += 1
            if tab == "overdue":
                totals["overdue"] += 1
        if in_period:
            totals["received"] += 1
            totals["joint"] += 1 if joint else 0
            totals["returned"] += 1 if returned else 0
            if record.get("status") == "fixed":
                totals["fixed"] += 1
                totals["verified"] += 1 if verified else 0
        handoffs = handoffs_of(record)
        looped = False
        for h, loop in zip(handoffs, loop_flags(handoffs)):
            if h["at"] < since:
                continue
            rows[h["from"]]["handoffs_out"] += 1
            rows[h["to"]]["handoffs_in"] += 1
            totals["handoffs"] += 1
            looped = looped or loop
        totals["loops"] += 1 if looped else 0   # обращений с передачами по кругу (как в журнале передач)
    for sid, row in rows.items():
        row["places"] = len(places[sid])
        sample = answer_days[sid]
        row["answered"] = len(sample)
        row["median_answer_days"] = round(float(median(sample)), 1) if sample else None
        row["verified_share"] = _share(row["verified"], row["fixed"])
    totals["verified_share"] = _share(totals["verified"], totals["fixed"])
    return {"generated_at": iso(now), "days": days, "district": district, "since": iso(since),
            "services": [rows[sid] for sid in profiles.SERVICE_IDS], "totals": totals,
            "demo": bool(any_record and demo_only), "empty": not any_record}


def lagging(board_body: dict, n: int = 3) -> list[dict]:
    """Службы с наибольшим числом просроченных (затем открытых) — для блока «Ведомства» R08. Только службы."""
    rows = [r for r in board_body.get("services", []) if r["overdue"] or r["open"]]
    rows.sort(key=lambda r: (-r["overdue"], -r["open"], r["service"]))
    return [{"service": r["service"], "overdue": r["overdue"], "open": r["open"]} for r in rows[:max(0, int(n))]]


# ---------------------------------------------------------------- совместные обращения
def joint(records, now: datetime, *, days: int = 30, district: str | None = None, lookup=None,
          limit: int = 200) -> dict:
    """Обращения с двумя и более службами: открытые (любой давности) и поданные за период.

    Без текстов жителей и без устройств: сотрудник открывает обращение в «Обращениях» R09.
    """
    since = now - timedelta(days=days)
    items = []
    for record in _usable(records, district):
        parts = parts_of(record, lookup)
        if len(parts) < 2:
            continue
        created = parse_iso(record.get("created_at"))
        is_open = any(p["status"] not in PART_CLOSED for p in parts)
        if not is_open and (created is None or created < since):
            continue
        handoffs = handoffs_of(record)
        target = record.get("target") or {}
        items.append({
            "id": record.get("id"), "code": record.get("code"), "category": record.get("category"),
            "subtopic": record.get("subtopic"), "district": record.get("district"),
            "target": {k: target.get(k) for k in ("kind", "id", "label_ru", "label_kk", "approximate") if k in target},
            "created_at": record.get("created_at"), "status": record.get("status"), "open": is_open,
            "tab": inbox_tab(record, now), "deadline": deadline_state(record, now),
            "lead": next((p["service"] for p in parts if p["role"] == "lead"), parts[0]["service"]),
            "parts": parts, "handoffs": len(handoffs), "loop": any(loop_flags(handoffs)),
            "demo": bool(record.get("demo")),
        })
    order = {"overdue": 0, "reopened": 1, "new": 2, "in_progress": 3, "waiting_check": 4, None: 5}
    items.sort(key=lambda x: (not x["open"], order.get(x["tab"], 5), x["created_at"] or ""))
    counts = {"total": len(items), "open": sum(1 for x in items if x["open"]),
              "overdue": sum(1 for x in items if x["tab"] == "overdue")}
    return {"generated_at": iso(now), "days": days, "district": district, "items": items[:limit], "counts": counts,
            "demo": bool(items) and all(x["demo"] for x in items)}


# ---------------------------------------------------------------- журнал передач
def handoff_log(records, now: datetime, *, days: int = 30, district: str | None = None, limit: int = 300) -> dict:
    """Все передачи за период, новые сверху; пары «откуда → куда»; передачи по кругу.

    Срок ответа жителю передачей не обнуляется (CONTRACT §5.1) — рядом с передачей показываем тот же due_at.
    Кто передал — только роль (by_role), без имени сотрудника (CONTRACT §10).
    """
    since = now - timedelta(days=days)
    entries, pairs, loops = [], {}, set()
    for record in _usable(records, district):
        handoffs = handoffs_of(record)
        for h, loop in zip(handoffs, loop_flags(handoffs)):
            if h["at"] < since:
                continue
            if loop:
                loops.add(record.get("id"))
            key = (h["from"], h["to"])
            pairs[key] = pairs.get(key, 0) + 1
            entries.append({"at": iso(h["at"]), "complaint_id": record.get("id"), "code": record.get("code"),
                            "category": record.get("category"), "district": record.get("district"),
                            "from": h["from"], "to": h["to"], "reason": h["reason"], "by_role": h["by_role"],
                            "due_at": record.get("due_at"), "deadline": deadline_state(record, now),
                            "loop": loop, "demo": bool(record.get("demo"))})
    entries.sort(key=lambda e: e["at"], reverse=True)
    pair_rows = [{"from": f, "to": t, "count": c} for (f, t), c in pairs.items()]
    pair_rows.sort(key=lambda p: (-p["count"], p["from"], p["to"]))
    return {"generated_at": iso(now), "days": days, "district": district, "items": entries[:limit],
            "total": len(entries), "pairs": pair_rows[:20], "loops": len(loops),
            "demo": bool(entries) and all(e["demo"] for e in entries)}
