"""Расчёт тепловой карты: вес, уровень, «исправлено», районы (CONTRACT §6).

Правила (одним местом, чтобы следующий разработчик не искал по коду):
- Человек = одна жалоба + каждое «Я тоже» к ней. Вклад жалобы: (1 + metoo) * 0.5 ** (возраст_в_днях / 14).
  У записи v2 нет времени каждого «Я тоже», поэтому «Я тоже» стареет вместе со своей жалобой.
- В расчёт идут жалобы за выбранный период (7/30/90 дней), кроме статусов fixed и rejected.
- Если цель отмечена исправленной (статус fixed в истории), всё, что пришло ДО этого момента, считается
  закрытым. Новых жалоб нет → цель 7 дней зелёная «исправлено», вес 0. Пришли новые → снова краснеет.
- count — сколько человек сообщили за период (без затухания): это число на значке и в карточке.
  level — по весу (с затуханием): так цель «остывает», если новых жалоб нет.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from . import geo
from .config import DAILY_WINDOW_DAYS, DISTRICT_LEVEL_SCALE, HeatConfig

ASTANA_TZ = timezone(timedelta(hours=5))
OPEN_STATUSES = ("new", "accepted", "in_progress")
STATUS_RANK = {"new": 0, "accepted": 1, "in_progress": 2}
MAX_OPEN_IDS = 50


def parse_time(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=ASTANA_TZ)
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=ASTANA_TZ)


def iso(dt: datetime) -> str:
    return dt.astimezone(ASTANA_TZ).isoformat(timespec="seconds")


def people(c: dict) -> int:
    try:
        metoo = int(c.get("metoo") or 0)
    except (TypeError, ValueError):
        metoo = 0
    return 1 + max(0, metoo)


def fixed_at(c: dict) -> datetime | None:
    """Когда жалоба получила статус fixed (последний раз). Нет истории — время создания."""
    last = None
    for h in c.get("status_history") or []:
        if isinstance(h, dict) and h.get("status") == "fixed":
            t = parse_time(h.get("at"))
            if t and (last is None or t > last):
                last = t
    if last is None and c.get("status") == "fixed":
        last = parse_time(c.get("updated_at")) or parse_time(c.get("created_at"))
    return last


def decay(age_days: float, half_life: float) -> float:
    return 0.5 ** (max(0.0, age_days) / half_life)


def target_key(c: dict) -> tuple[dict, bool] | None:
    """Цель жалобы. Без цели — ячейка ~150 м вокруг точки, помеченная как примерное место."""
    t = c.get("target")
    if isinstance(t, dict) and t.get("id"):
        return t, False
    p = c.get("point")
    if isinstance(p, (list, tuple)) and len(p) == 2:
        return {"kind": "area", "id": geo.cell_id_for(p)}, True
    return None


def complaint_district(c: dict) -> str | None:
    d = c.get("district")
    if d:
        return str(d)
    p = c.get("point")
    if isinstance(p, (list, tuple)) and len(p) == 2:
        return geo.district_of(p)
    return None


def _astana_day(dt: datetime):
    return dt.astimezone(ASTANA_TZ).date()


def compute(complaints, *, now: datetime, days: int, config: HeatConfig, resolver, category: str | None = None,
            district: str | None = None, bbox=None) -> dict:
    """Все цели с жалобами → {items, stats}. Порядок items: сначала самые горячие."""
    period_start = now - timedelta(days=days)
    fixed_span = timedelta(days=config.fixed_days)
    today = _astana_day(now)
    groups: dict = defaultdict(list)
    meta: dict = {}
    stats = {"complaints": 0, "skipped_invalid": 0, "unresolved_targets": 0, "approximate_targets": 0}

    for c in complaints:
        if not isinstance(c, dict):
            stats["skipped_invalid"] += 1
            continue
        created = parse_time(c.get("created_at"))
        tk = target_key(c)
        if created is None or tk is None:
            stats["skipped_invalid"] += 1
            continue
        if category and c.get("category") != category:
            continue
        cd = complaint_district(c)
        if district and cd != district:
            continue
        stats["complaints"] += 1
        target, missing = tk
        key = (target.get("kind") or "area", str(target["id"]))
        groups[key].append((c, created))
        m = meta.setdefault(key, {"target": target, "missing": missing, "district": cd, "point": None, "last": None})
        if m["last"] is None or created > m["last"]:
            m["last"] = created
            m["point"] = c.get("point")
            m["district"] = cd or m["district"]

    items = []
    for key, rows in groups.items():
        m = meta[key]
        t_fixed = None
        for c, _ in rows:
            f = fixed_at(c)
            if f and (t_fixed is None or f > t_fixed):
                t_fixed = f
        active = [(c, cr) for c, cr in rows
                  if c.get("status", "new") in OPEN_STATUSES and (t_fixed is None or cr > t_fixed)]
        in_period = [(c, cr) for c, cr in active if period_start <= cr <= now + timedelta(minutes=5)]
        weight = 0.0
        count = 0
        by_cat: dict = defaultdict(int)
        status_rank = 0
        for c, cr in in_period:
            n = people(c)
            age = (now - cr).total_seconds() / 86400.0
            weight += n * decay(age, config.half_life_days)
            count += n
            by_cat[c.get("category") or "other"] += n
            status_rank = max(status_rank, STATUS_RANK.get(c.get("status", "new"), 0))

        state = "active"
        fixed_until = None
        if count == 0:
            if t_fixed is not None and now < t_fixed + fixed_span:
                state = "fixed"
                fixed_until = t_fixed + fixed_span
                closed = [(c, cr) for c, cr in rows if c.get("status") != "rejected" and cr <= t_fixed
                          and cr >= t_fixed - timedelta(days=days)]
                count = sum(people(c) for c, _ in closed)
                for c, _ in closed:
                    by_cat[c.get("category") or "other"] += people(c)
            else:
                continue

        resolved = resolver.resolve(m["target"], m["point"])
        if not resolved:
            stats["unresolved_targets"] += 1
            continue
        approximate = bool(resolved.get("approximate") or m["missing"])
        if approximate:
            stats["approximate_targets"] += 1
        if bbox is not None:
            gb = geo.bbox_of(resolved["geometry"])
            if gb is None or not geo.bbox_intersects(gb, bbox):
                continue

        daily = [0] * DAILY_WINDOW_DAYS
        for c, cr in (in_period if state == "active" else []):
            idx = DAILY_WINDOW_DAYS - 1 - (today - _astana_day(cr)).days
            if 0 <= idx < DAILY_WINDOW_DAYS:
                daily[idx] += people(c)

        level = config.level_for(weight) if state == "active" else "fixed"
        color = config.color_for(level) if state == "active" else config.fixed_color
        status = "fixed" if state == "fixed" else ("new", "accepted", "in_progress")[status_rank]
        open_sorted = sorted(in_period, key=lambda x: x[1], reverse=True)
        label_ru = "Примерное место" if m["missing"] else resolved["label_ru"]
        label_kk = "Шамамен көрсетілген орын" if m["missing"] else resolved["label_kk"]
        target_out = {"kind": key[0], "id": key[1], "label_ru": label_ru, "label_kk": label_kk}
        if resolved.get("subtype"):
            target_out["subtype"] = resolved["subtype"]   # например bus_stop → в карточке «Остановка»
        items.append({
            "target": target_out,
            "geometry": resolved["geometry"],
            "anchor": [round(v, 6) for v in resolved["anchor"]] if resolved.get("anchor") else None,
            "weight": round(weight, 3),
            "level": level,
            "color": color,
            "count": count,
            "fixed_until": iso(fixed_until) if fixed_until else None,
            "state": state,
            "status": status,
            "approximate": approximate,
            "district": m["district"],
            "by_category": dict(sorted(by_cat.items(), key=lambda kv: -kv[1])),
            "daily": daily,
            "last_at": iso(m["last"]),
            "open_ids": [c.get("id") for c, _ in open_sorted[:MAX_OPEN_IDS] if c.get("id")],
            "demo": all(bool(c.get("demo")) for c, _ in rows),
        })

    items.sort(key=lambda it: (it["state"] == "active", it["level"] if it["state"] == "active" else 0, it["weight"], it["count"]), reverse=True)
    return {"items": items, "stats": stats}


def districts_summary(target_items: list, config: HeatConfig) -> list:
    """Мелкий масштаб: сумма по району. Пороги уровней умножены на DISTRICT_LEVEL_SCALE."""
    acc: dict = {}
    for it in target_items:
        d = it.get("district")
        if not d:
            continue
        a = acc.setdefault(d, {"weight": 0.0, "count": 0, "targets": 0, "fixed": 0, "top": None})
        if it["state"] == "fixed":
            a["fixed"] += 1
            continue
        a["weight"] += it["weight"]
        a["count"] += it["count"]
        a["targets"] += 1
        if a["top"] is None or it["weight"] > a["top"]["weight"]:
            a["top"] = {"target": it["target"], "weight": it["weight"], "count": it["count"]}
    out = []
    all_d = geo.districts()
    for d_id, a in acc.items():
        d = all_d.get(d_id)
        if not d:
            continue
        level = config.level_for(a["weight"], DISTRICT_LEVEL_SCALE) if a["count"] else 0
        out.append({
            "target": {"kind": "district", "id": d_id, "label_ru": d["name_ru"], "label_kk": d["name_kk"]},
            "geometry": d["geometry"],
            "anchor": [round(v, 6) for v in geo.anchor_of(d["geometry"])],
            "weight": round(a["weight"], 3),
            "level": level,
            "color": config.color_for(level),
            "count": a["count"],
            "fixed_until": None,
            "state": "active" if a["count"] else "calm",
            "targets": a["targets"],
            "fixed_targets": a["fixed"],
            "top": a["top"],
            "district": d_id,
        })
    out.sort(key=lambda it: (it["weight"], it["count"]), reverse=True)
    return out


def round_geometry(geometry: dict, digits: int = 6) -> dict:
    def r(c):
        if c and isinstance(c[0], (int, float)):
            return [round(c[0], digits), round(c[1], digits)]
        return [r(x) for x in c]
    return {"type": geometry["type"], "coordinates": r(geometry["coordinates"])}


def is_finite_number(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)
