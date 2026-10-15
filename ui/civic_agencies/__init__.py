"""R17 · «Бірге: ведомства вместе» — штаб ведомств и кризисный штаб (раунд 15).

    from ui.civic_agencies import make_service
    service = make_service(".runtime/civic.sqlite3")         # та же база, что у шлюза R01 (таблицы agency_*)
    service.handle("GET", "/api/civic/v2/agencies/board", "days=30", None, principal, context)
      -> {"status": 200, "headers": {}, "body": {"services": [...20 служб...], "totals": {...}, ...}}

Подключение к шлюзу R01 (V2Handler kind="service"), маршруты и порядок строк — research/round-15-results/R17/INTEGRATION.txt.
Экран — web/civic/agencies/agencies.js (window.BirgeAgencies, раздел оболочки #agencies; слой карты «Кризис»).

Функции для соседей в том же процессе (только чтение; сервиса нет — пустой ответ, а не ошибка, CONTRACT §7):
  updates(device, since)        R06: события ленты «Что нового» (§5.8) — обновления кризисов зоны жителя;
  board_snapshot(days, district) R08 / R03: табло служб (числа считает этот модуль, R08 только показывает);
  agencies_week(days, district)  R08 «Картина дня» → «Ведомства»: 3 отстающие службы, совместные, передачи;
  active_incidents(district)     R08 ситуационный центр, R13 пульс: идущие кризисы (публичная часть);
  incident_marks(start, end)     R07 хроника: отметки «Буран 12 окт» на шкале;
  service_profiles()             R12 календарь работ: цвета и значки служб;
  crisis_link(district, kind)    R08 / R13: адрес кнопки «Открыть кризисный штаб»;
  seed_world(db_path, records)   R01 при CIVIC_DEMO_WORLD=1: кризисы демо-мира R02 (CONTRACT §11).
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import api_state, board as _calc, crisis as _crisis, profiles as _profiles, sources as _sources
from .demo import seed_world
from .service import AgencyService, make_service, resident_feed, device_places
from .store import AgencyStore, iso as _iso, parse_iso as _parse_iso

__all__ = [
    "AgencyService", "AgencyStore", "make_service", "seed_world", "configure", "updates", "board_snapshot",
    "agencies_week", "active_incidents", "incident_marks", "service_profiles", "crisis_link",
]


def configure(records=None, db_path=None) -> None:
    """R01 (wire): records() — те же записи хранилища R09, что у шлюза; db_path — создать сервис, если его ещё нет."""
    _sources.configure(records=records)
    if db_path is not None and api_state.current() is None:
        make_service(db_path)


def _service():
    return api_state.current()


def _now() -> datetime:
    service = _service()
    moment = service.store.now() if service is not None else datetime.now(timezone.utc)
    return moment.astimezone(_calc.ASTANA)


def updates(device, since=None) -> list[dict]:
    """События ленты R06 (CONTRACT §5.8): обновления кризисов, чья зона — район или двор жителя.

    Район и двор — по устройству у соседей (R16 «Я живу здесь», R08 подписка на район). Неизвестно где живёт —
    пустой список: кризис в чужом районе не шумит в ленте.
    """
    service = _service()
    if service is None or not isinstance(device, str):
        return []
    try:
        districts, yards = device_places(device)
        items = resident_feed(service.store, districts, yards, since)
    except Exception:  # noqa: BLE001 — лента R06 не должна падать из-за модуля R17
        return []
    out = []
    for item in items:
        zone = {"kind": "district", "id": item["district"]} if item.get("district") else {"kind": "city", "id": "astana"}
        prefix_ru = "Кризис закрыт" if item["kind"] == "closed" else item["title_ru"]
        prefix_kk = "Жағдай аяқталды" if item["kind"] == "closed" else item["title_kk"]
        out.append({"id": "incident." + item["id"], "at": item["at"], "module": "R17", "kind": "incident.update",
                    "target": zone, "title_ru": f"{prefix_ru}: {item['text_ru']}",
                    "title_kk": f"{prefix_kk}: {item['text_kk']}", "link": "#incident=" + item["incident_id"],
                    "demo": bool(item.get("demo"))})
    return out


def board_snapshot(days: int = 30, district: str | None = None) -> dict:
    """Табло служб (как GET agencies/board) для R08 и R03. Сервиса нет — {"services": [], "empty": True}."""
    service = _service()
    if service is None:
        return {"services": [], "totals": {}, "empty": True, "source": "none"}
    now = _now()
    records, source = service._records(now)
    body = _calc.board(records, now, days=days, district=district, lookup=_sources.r08_lookup())
    body["source"] = source
    return body


def agencies_week(days: int = 7, district: str | None = None, lagging: int = 3) -> dict:
    """Блок «Ведомства» для «Картины дня» R08: 3 отстающие службы, совместные обращения и передачи за неделю."""
    service = _service()
    if service is None:
        return {"lagging": [], "joint": 0, "handoffs": 0, "loops": 0, "empty": True, "source": "none"}
    now = _now()
    records, source = service._records(now)
    body = _calc.board(records, now, days=days, district=district, lookup=_sources.r08_lookup())
    return {"days": days, "district": district, "lagging": _calc.lagging(body, lagging),
            "joint": body["totals"]["joint"], "handoffs": body["totals"]["handoffs"],
            "loops": body["totals"]["loops"], "open": body["totals"]["open"], "overdue": body["totals"]["overdue"],
            "demo": body["demo"], "source": source, "link": "#agencies"}


def active_incidents(district: str | None = None) -> list[dict]:
    """Идущие кризисы (публичная часть, без задач) — для ситуационного центра R08 и пульса R13."""
    service = _service()
    if service is None:
        return []
    try:
        rows = service.store.list(status="active", district=district)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for row in rows:
        view = _crisis.public_view(row)
        view["progress"] = _crisis.progress(row)   # чипы служб: сколько задач сделано (без текстов задач)
        view["link"] = "#agencies/crisis=" + row["id"]
        out.append(view)
    return out


def incident_marks(start=None, end=None) -> list[dict]:
    """Отметки для хроники R07: {id, kind, title_ru, title_kk, started_at, closed_at, district, demo} за период."""
    service = _service()
    if service is None:
        return []
    lo, hi = _parse_iso(start) if isinstance(start, str) else start, _parse_iso(end) if isinstance(end, str) else end
    out = []
    for row in service.store.list(limit=200):
        began = _parse_iso(row["started_at"])
        ended = _parse_iso(row.get("closed_at")) or _now()
        if lo is not None and ended < lo or hi is not None and began is not None and began > hi:
            continue
        out.append({"id": row["id"], "kind": row["kind"], "title_ru": row["title_ru"], "title_kk": row["title_kk"],
                    "started_at": row["started_at"], "closed_at": row.get("closed_at"), "district": row.get("district"),
                    "status": row["status"], "demo": row["demo"]})
    out.sort(key=lambda m: m["started_at"])
    return out


def service_profiles() -> list[dict]:
    """Профили 20 служб (§5.4) с названиями R08 — для R12 (цвета полос календаря работ) и R08."""
    return _profiles.all_profiles()


def crisis_link(district: str | None = None, kind: str = "blizzard") -> str:
    """Адрес кнопки «Открыть кризисный штаб»: идущий кризис района — его карточка; нет — форма с шаблоном."""
    for incident in active_incidents(district):
        if incident["kind"] == kind or kind is None:
            return "#agencies/crisis=" + incident["id"]
    tail = f"&district={district}" if district else ""
    return f"#agencies/crisis=new&template={kind}{tail}"
