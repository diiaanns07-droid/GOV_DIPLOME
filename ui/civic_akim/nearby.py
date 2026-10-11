"""«Что делают рядом» (волна 2 п. 4; экран — R08, данные — R06). Раздел жителя «Рядом» (R11 IA_WAVE2 §4).

    from ui.civic_akim import nearby
    nearby.feed("nura", tab="now")   # {district, tabs:{now,done,planned,outages}, items, banners, demo, …}

ВКЛАДКИ: now — ремонтируют сейчас; done — завершили за последние DONE_DAYS дней; planned — запланировано;
outages — отключения и перекрытия, которые идут сейчас или начнутся в ближайшие OUTAGE_AHEAD_DAYS дней.
Баннеры сверху — не больше 2 отключений: идут сейчас или начнутся в ближайшие BANNER_HOURS часов.
Задержки показываем, не только успехи: delayed = прогноз окончания позже плана («срок перенесён»).

ИСТОЧНИКИ (по порядку, ничего не придумываем):
  1. R06: функция ui.civic_store(.v2).nearby_items(district) — «работы и отключения», которые сотрудник
     добавил вручную (форма R06: 4 строки «Зачем» обязательны, у отключения — источник и время). Формат — ITEM ниже.
  2. Объекты R06 (те же, что в «Картине дня»): этап → вкладка (строительство/приёмка — now, работает — done,
     план/проект/закупка — planned). У них нет строк «Зачем» — карточка без них.
  3. Пока функции 1 нет — пример fixtures/nearby_demo.json (demo: true, на экране «Пример»).

ITEM: {id, type: work|outage, status: in_progress|done|planned (у work), work_kind, utility (у outage:
water|heating|power|gas|road_closure), district, title_ru/kk, start, end (у outage — ISO время),
planned_end, forecast_end (у work — даты), zone_ru/kk, detour_ru/kk, source (id службы routing.SERVICES),
updated_at, why: {problem_ru/kk, reason_ru/kk, result_ru/kk, inconvenience_ru/kk}, target {kind,id}?, demo}.

ПОДПИСКА (житель): subscribe(device_id, scope, scope_id) — scope district | item. Хранится в
.runtime/civic_akim/subscriptions.json (путь — BIRGE_AKIM_SUBSCRIPTIONS). updates_for(device_id, since) — что
изменилось в подписках; R09 показывает это в «Мои обращения → Что изменилось» (R11 IA_WAVE2 §4).
В ответе нет личных данных; device_id — случайный номер устройства (как у R09, birge.device).
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import deadlines, sources

ASTANA_TZ = timezone(timedelta(hours=5))
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "nearby_demo.json"
SUBS_PATH = Path(os.environ.get("BIRGE_AKIM_SUBSCRIPTIONS") or deadlines.ROOT / ".runtime" / "civic_akim" / "subscriptions.json")
TABS = ("now", "done", "planned", "outages")
DONE_DAYS = 30
OUTAGE_AHEAD_DAYS = 7
BANNER_HOURS = 36
MAX_BANNERS = 2
MAX_SUBS_PER_DEVICE = 20
DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{16,80}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
R06_NEARBY_FUNCS = ("nearby_items", "works_nearby")
STAGE_TAB = {"construction": "now", "acceptance": "now", "operating": "done",
             "planned": "planned", "design": "planned", "procurement": "planned"}
_lock = threading.Lock()


class NearbyError(ValueError):
    def __init__(self, field: str, message: str, status: int = 400):
        super().__init__(message)
        self.field, self.status = field, status


def _now(now: datetime | None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(ASTANA_TZ)


def _iso(dt: datetime) -> str:
    return dt.astimezone(ASTANA_TZ).isoformat(timespec="seconds")


def _parse(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            d = date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
        return datetime(d.year, d.month, d.day, tzinfo=ASTANA_TZ)
    return dt if dt.tzinfo else dt.replace(tzinfo=ASTANA_TZ)


# ---------------------------------------------------------------- источники

def fixture_items(now: datetime) -> list[dict]:
    """Пример: времена — относительно «сейчас» (сегодняшняя дата Астаны + day, часы from/to)."""
    raw = json.loads(FIXTURE.read_text("utf-8"))
    today = now.date()
    out = []
    for x in raw.get("items", []):
        x = json.loads(json.dumps(x))
        if "when" in x:
            w = x.pop("when")
            day = today + timedelta(days=int(w.get("day", 0)))
            fh, fm = (int(v) for v in w["from"].split(":"))
            th, tm = (int(v) for v in w["to"].split(":"))
            start = datetime(day.year, day.month, day.day, fh, fm, tzinfo=ASTANA_TZ)
            end = datetime(day.year, day.month, day.day, th, tm, tzinfo=ASTANA_TZ)
            if end <= start:
                end += timedelta(days=1)  # ночное перекрытие 22:00–06:00
            x["start"], x["end"] = _iso(start), _iso(end)
        for key in ("start_day", "planned_end_day", "forecast_end_day"):
            if key in x:
                x[key.replace("_day", "")] = (today + timedelta(days=int(x.pop(key)))).isoformat()
        x["updated_at"] = _iso(now - timedelta(minutes=int(x.pop("updated_ago_min", 0))))
        x["demo"] = True
        out.append(x)
    return out


def _object_item(o: dict, now: datetime) -> dict | None:
    """Объект R06 → карточка «Рядом» (без строк «Зачем»: их у объекта нет)."""
    n = sources.normalize_object(o, now)
    tab = STAGE_TAB.get(n["stage"])
    if tab is None:
        return None
    status = {"now": "in_progress", "done": "done", "planned": "planned"}[tab]
    end = n["forecast_end"] or n["planned_end"]
    if tab == "done":
        updated = _parse(n["updated_at"])
        if updated is None or (now - updated).days > DONE_DAYS:
            return None  # давно работающий объект — уже не «завершили недавно»
    return {"id": n["id"], "type": "work", "status": status, "work_kind": n["kind"], "district": n["district"],
            "title_ru": n["title_ru"], "title_kk": n["title_kk"], "title_kk_missing": n["title_kk_missing"],
            "planned_end": n["planned_end"], "forecast_end": n["forecast_end"], "end": end,
            "stage": n["stage"], "updated_at": n["updated_at"], "why": None,
            "target": {"kind": "object", "id": n["id"]} if n["has_place"] else None,
            "source_kind": "object", "demo": n["demo"]}


def _r06_nearby():
    return sources._r06(R06_NEARBY_FUNCS)


def load_items(district: str | None, now: datetime, *, objects=None, nearby_fn=None) -> tuple[list[dict], dict]:
    """Все карточки района из всех источников и имена источников."""
    names = {}
    items: list[dict] = []
    fn = nearby_fn if nearby_fn is not None else _r06_nearby()
    if fn:
        try:
            raw = sources._call_r06(fn, district=district)
            raw = raw.get("items", []) if isinstance(raw, dict) else raw
            items += [dict(x) for x in raw or [] if isinstance(x, dict)]
            names["nearby"] = "r06"
        except sources.R06NotReady:
            fn = None
    if not fn:
        items += fixture_items(now)
        names["nearby"] = "example"
    if objects is None:
        objects, names["objects"] = sources.default_objects()
    else:
        names["objects"] = "custom"
    try:
        raw_objects = objects(district, now.date()) if objects else []
    except Exception:
        raw_objects, names["objects"] = [], "failed"
    for o in raw_objects or []:
        if isinstance(o, dict):
            it = _object_item(o, now)
            if it:
                items.append(it)
    if district:
        items = [x for x in items if x.get("district") == district]
    return items, names


# ---------------------------------------------------------------- лента

def _tab(x: dict, now: datetime) -> str | None:
    if x.get("type") == "outage":
        start, end = _parse(x.get("start")), _parse(x.get("end"))
        if start is None or end is None or end < now or start > now + timedelta(days=OUTAGE_AHEAD_DAYS):
            return None  # закончилось или ещё далеко; у отключения без времени нет места в ленте (R11 §4)
        return "outages"
    status = x.get("status")
    if status == "done":
        end = _parse(x.get("forecast_end") or x.get("planned_end") or x.get("end"))
        if end is not None and (now - end).days > DONE_DAYS:
            return None
        return "done"
    return {"in_progress": "now", "planned": "planned"}.get(status)


def _decorate(x: dict, now: datetime) -> dict:
    x = dict(x)
    planned, forecast = _parse(x.get("planned_end")), _parse(x.get("forecast_end"))
    x["delayed"] = bool(planned and forecast and forecast.date() > planned.date())
    x["delay_days"] = (forecast.date() - planned.date()).days if x["delayed"] else 0
    updated = _parse(x.get("updated_at"))
    x["updated_min_ago"] = max(0, int((now - updated).total_seconds() // 60)) if updated else None
    if x.get("type") == "outage":
        start, end = _parse(x.get("start")), _parse(x.get("end"))
        x["active"] = bool(start and end and start <= now <= end)
        x["starts_in_h"] = round((start - now).total_seconds() / 3600, 1) if start and start > now else 0
    why = x.get("why") if isinstance(x.get("why"), dict) else None
    x["why"] = why if why and any(why.get(f"{k}_ru") for k in ("problem", "reason", "result", "inconvenience")) else None
    if x.get("title_kk") in (None, ""):
        x["title_kk"], x["title_kk_missing"] = x.get("title_ru"), True
    return x


def feed(district: str | None, tab: str | None = None, *, now: datetime | None = None, objects=None, nearby_fn=None) -> dict:
    """Лента «Рядом» района. tab=None — все вкладки (items по вкладкам в поле tab у каждой карточки)."""
    now = _now(now)
    if isinstance(district, str):
        district = district.strip().lower() or None
    from .summary import districts  # тот же список районов, что у «Картины дня»
    if district is not None and district not in districts():
        raise NearbyError("district", "неизвестный район: " + str(district))
    if tab is not None and tab not in TABS:
        raise NearbyError("tab", "вкладка — now, done, planned или outages")
    raw, names = load_items(district, now, objects=objects, nearby_fn=nearby_fn)
    cards = []
    for x in raw:
        t = _tab(x, now)
        if t:
            cards.append({**_decorate(x, now), "tab": t})
    counts = {t: sum(1 for c in cards if c["tab"] == t) for t in TABS}

    def order(c):
        # отключения: идущие сейчас, потом ближайшие; завершили: свежие сверху; остальное: сначала с задержкой, потом по сроку
        end = _parse(c.get("forecast_end") or c.get("planned_end") or c.get("end"))
        ts = end.timestamp() if end else float("inf")
        if c["tab"] == "outages":
            start = _parse(c.get("start"))
            return (0 if c["active"] else 1, start.timestamp() if start else 0.0)
        if c["tab"] == "done":
            return (0, -ts if end else 0.0)
        return (0 if c.get("delayed") else 1, ts)
    cards.sort(key=lambda c: (TABS.index(c["tab"]),) + order(c))
    banners = [c for c in cards if c["tab"] == "outages" and (c["active"] or c["starts_in_h"] <= BANNER_HOURS)][:MAX_BANNERS]
    shown = [c for c in cards if tab is None or c["tab"] == tab]
    return {"generated_at": _iso(now), "district": district, "tab": tab, "tabs": counts, "items": shown,
            "banners": [{k: c.get(k) for k in ("id", "utility", "title_ru", "title_kk", "start", "end", "zone_ru",
                                                "zone_kk", "active", "source", "updated_min_ago", "demo")} for c in banners],
            "demo": any(c.get("demo") for c in cards), "sources": names}


# ---------------------------------------------------------------- подписка

def _load_subs(path: Path | None = None) -> dict:
    try:
        data = json.loads(Path(path or SUBS_PATH).read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def subscriptions(device_id: str, path: Path | None = None) -> list[dict]:
    if not isinstance(device_id, str) or not DEVICE_RE.match(device_id):
        raise NearbyError("device_id", "неверный номер устройства")
    return list(_load_subs(path).get(device_id, []))


def subscribe(device_id: str, scope: str, scope_id: str, *, on: bool = True, path: Path | None = None,
              now: datetime | None = None) -> list[dict]:
    """Подписаться (on=True) или отписаться. scope: district — весь район; item — одна работа/отключение."""
    if not isinstance(device_id, str) or not DEVICE_RE.match(device_id):
        raise NearbyError("device_id", "неверный номер устройства")
    if scope not in ("district", "item"):
        raise NearbyError("scope", "подписка — на район (district) или на карточку (item)")
    if scope == "district":
        from .summary import districts
        if scope_id not in districts():
            raise NearbyError("id", "неизвестный район")
    elif not isinstance(scope_id, str) or not ID_RE.match(scope_id):
        raise NearbyError("id", "неверный номер карточки")
    p = Path(path or SUBS_PATH)
    with _lock:
        data = _load_subs(p)
        mine = [s for s in data.get(device_id, []) if not (s.get("scope") == scope and s.get("id") == scope_id)]
        if on:
            if len(mine) >= MAX_SUBS_PER_DEVICE:
                raise NearbyError("limit", f"не больше {MAX_SUBS_PER_DEVICE} подписок на устройство", 429)
            mine.append({"scope": scope, "id": scope_id, "since": _iso(_now(now))})
        if mine:
            data[device_id] = mine
        else:
            data.pop(device_id, None)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, p)
    return mine


def updates_for(device_id: str, since=None, *, now: datetime | None = None, path: Path | None = None,
                objects=None, nearby_fn=None) -> list[dict]:
    """Для R09 «Мои обращения → Что изменилось»: карточки из подписок, обновлённые после since (или после подписки)."""
    now = _now(now)
    subs = subscriptions(device_id, path)
    since_dt = _parse(since)
    out, seen = [], set()
    for s in subs:
        start = max(filter(None, [since_dt, _parse(s.get("since"))]), default=None)
        district = s["id"] if s["scope"] == "district" else None
        for c in feed(district, now=now, objects=objects, nearby_fn=nearby_fn)["items"]:
            if s["scope"] == "item" and c["id"] != s["id"]:
                continue
            upd = _parse(c.get("updated_at"))
            if c["id"] in seen or (start and upd and upd <= start):
                continue
            seen.add(c["id"])
            out.append({"id": c["id"], "tab": c["tab"], "title_ru": c["title_ru"], "title_kk": c["title_kk"],
                        "district": c.get("district"), "updated_at": c.get("updated_at"), "scope": s["scope"],
                        "demo": c.get("demo", False)})
    out.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    return out
