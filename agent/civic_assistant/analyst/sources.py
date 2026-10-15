"""Откуда аналитик берёт числа: функции модулей-соседей в том же процессе (CONTRACT §7, «вызовы между модулями»).

    R07 тепловая карта ...... ui.civic_heat.default_service(): heat / districts — те же числа, что на карте;
    R08 «Картина дня» ....... ui.civic_akim.summary(date, district): темы, районы, просрочки, пульс, сводка;
    R17 «Штаб ведомств» ..... ui.civic_agencies: табло служб и кризисы (раунд 15; пока нет — запасной расчёт или «нет»);
    R12 календарь работ ..... engine.civic_geo: конфликты работ «копаем дважды»;
    R16 «Сделаем вместе» .... ui.civic_together: инициативы жителей;
    R13 встречи и прогноз ... ui.civic_meetings (поручения), ui.civic_forecast (прогноз).

Правила:
- только чтение и только через функции соседа; модуля или функции нет → статус not_ready, ответ «пока нет данных»,
  а не ошибка (CONTRACT §7);
- каждый вызов пишется в журнал (CallLog): модуль, функция, параметры, статус, миллисекунды — это «Как получен ответ»;
- тексты жителей отсюда не уходят: берутся только числа, подписи мест (улицы и дворы из OSM) и названия служб.

R01 или тесты могут подменить любой источник: configure(heat=…, akim=…, agencies_board=…, …) в core.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
import inspect
import logging
import time

LOGGER = logging.getLogger(__name__)
ASTANA_TZ = timezone(timedelta(hours=5))
OPEN = ("new", "accepted", "in_progress")


MODULE_NAMES = {
    "R07": {"ru": "Карта жалоб", "kk": "Шағымдар картасы"},
    "R08": {"ru": "Картина дня", "kk": "Күн қорытындысы"},
    "R12": {"ru": "Календарь работ", "kk": "Жұмыстар күнтізбесі"},
    "R13": {"ru": "Встречи и прогноз", "kk": "Кездесулер мен болжам"},
    "R16": {"ru": "Сделаем вместе", "kk": "Бірге жасайық"},
    "R17": {"ru": "Штаб ведомств", "kk": "Ведомстволар штабы"},
}


class NotReady(Exception):
    """Модуля-соседа нет в сборке (или он не связан с базой) — честное «пока нет данных»."""


class CallLog:
    """Журнал вызовов одного ответа. rows уходят в ответ как «Как получен ответ» (без значений и текстов)."""

    def __init__(self):
        self.rows: list[dict] = []

    def run(self, role: str, module: str, fn_name: str, fn, args: dict | None = None):
        """Вызвать fn(**args) и записать строку журнала. Возвращает (status, value)."""
        args = dict(args or {})
        started = time.perf_counter()
        status, value, note = "ok", None, None
        try:
            value = fn(**args)
            if value is None:
                status = "empty"
        except NotReady as exc:
            status, note = "not_ready", str(exc)[:120] or None
        except Exception as exc:  # noqa: BLE001 — сосед сломался: отвечаем без него, подробности — в журнал сервера
            # Модуль, который сам отвечает 503 module_not_ready (как R06 до bind), — это «нет данных», а не сбой.
            if getattr(exc, "status", None) == 503 or getattr(exc, "code", None) == "module_not_ready":
                status = "not_ready"
            else:
                status = "error"
                LOGGER.exception("analyst: %s.%s failed", module, fn_name)
        # name — подпись источника для акима (R11 R03-3: коды модулей — только в подсказке строки).
        row = {"role": role, "name": dict(MODULE_NAMES.get(role) or {"ru": role, "kk": role}), "module": module, "fn": fn_name,
               "args": {k: v for k, v in args.items() if isinstance(v, (str, int, float, bool)) or v is None},
               "status": status, "ms": round((time.perf_counter() - started) * 1000, 1)}
        if note:
            row["note"] = note
        if isinstance(value, dict) and isinstance(value.get("demo"), (bool, dict)):
            demo = value["demo"]
            row["demo"] = bool(demo.get("any")) if isinstance(demo, dict) else demo
        self.rows.append(row)
        return status, value


def _import(name: str):
    """Модуль или None, если его (или его пакета) нет; сломанная зависимость внутри модуля — исключение."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", None) or ""
        if name == missing or name.startswith(missing + "."):
            return None
        raise


def find_function(modules: tuple[str, ...], names: tuple[str, ...]):
    """Первая найденная функция соседа: (модуль, имя, функция) или (None, None, None)."""
    for modname in modules:
        try:
            module = _import(modname)
        except Exception:  # noqa: BLE001 — модуль есть, но не загрузился: считаем, что его нет
            LOGGER.exception("analyst: module %s failed to import", modname)
            continue
        if module is None:
            continue
        for name in names:
            fn = getattr(module, name, None)
            if callable(fn):
                return modname, name, fn
    return None, None, None


def call_flexible(fn, **kwargs):
    """Вызвать функцию соседа только с теми именованными параметрами, которые она объявила."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return fn(**kwargs)
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(**kwargs)
    return fn(**{k: v for k, v in kwargs.items() if k in params})


def unwrap(answer):
    """Ответ соседа в любом из принятых видов → данные: {ok, data} → data; (status, body) → body."""
    if isinstance(answer, tuple) and len(answer) == 2 and isinstance(answer[0], int):
        status, body = answer
        if status >= 400:
            raise NotReady(f"status {status}") if status == 503 else RuntimeError(f"status {status}")
        answer = body
    if isinstance(answer, dict) and answer.get("ok") is True and "data" in answer:
        return answer["data"]
    if isinstance(answer, dict) and answer.get("ok") is False:
        error = answer.get("error") or {}
        code = error.get("code") if isinstance(error, dict) else error
        raise NotReady(str(code)) if code == "module_not_ready" else RuntimeError(str(code))
    return answer


def items_of(answer, *keys: str) -> list:
    """Список записей из ответа: сам список, {items: […]} или первый найденный ключ из keys."""
    answer = unwrap(answer)
    if isinstance(answer, list):
        return answer
    if isinstance(answer, dict):
        for key in keys + ("items",):
            value = answer.get(key)
            if isinstance(value, list):
                return value
    return []


# ---------------------------------------------------------------- R07 тепловая карта

def heat_service():
    try:
        module = _import("ui.civic_heat")
    except Exception:  # noqa: BLE001
        LOGGER.exception("analyst: ui.civic_heat failed to import")
        return None
    return module.default_service() if module is not None else None


def heat_targets(service, *, days: int, district: str | None, category: str | None) -> dict:
    """Горячие места: ответ R07 heat() в режиме целей (только активные — как «Горячие места» у R08)."""
    if service is None:
        raise NotReady("ui.civic_heat")
    data = service.heat(days=days, district=district, category=category)
    items = [it for it in data.get("items") or [] if it.get("state") == "active"]
    return {"items": items, "demo": bool(data.get("demo")), "days": days}


def heat_districts(service, *, days: int, category: str | None) -> dict:
    """Районы: сумма активных целей по району (R07 districts_summary) — те же числа, что «Нура · 81» на карте."""
    if service is None:
        raise NotReady("ui.civic_heat")
    items = service.districts(days=days, category=category)
    return {"items": [it for it in items if it.get("state") != "no_data"], "demo": bool(getattr(service, "is_demo", False)),
            "days": days}


# ---------------------------------------------------------------- R08 «Картина дня»

def akim_summary_fn():
    _mod, _name, fn = find_function(("ui.civic_akim",), ("summary",))
    return fn


def akim_summary(fn, *, district: str | None) -> dict:
    if fn is None:
        raise NotReady("ui.civic_akim")
    return fn(district=district)


def services_from_deadlines(heat, *, district: str | None, now: datetime | None = None) -> dict:
    """Запасное «табло служб», пока нет R17: открытые и просроченные обращения по службам.

    Те же определения и функции, что у «Картины дня» R08 (просрочено — открыто и срок категории истёк;
    служба — таблица маршрутизации R08), записи — те же, что у карты R07. Поэтому сумма просрочек по службам
    равна «Просрочено N» в «Картине дня» (тест tests/civic/R03/test_analyst_sources.py).
    """
    if heat is None:
        raise NotReady("ui.civic_heat")
    summary_mod = _import("ui.civic_akim.summary")
    deadlines = _import("ui.civic_akim.deadlines")
    routing = _import("ui.civic_akim.routing")
    engine = _import("ui.civic_heat.engine")
    if summary_mod is None or deadlines is None or routing is None:
        raise NotReady("ui.civic_akim")
    as_of = (now or datetime.now(timezone.utc)).astimezone(ASTANA_TZ)
    rows: dict[str, dict] = {}
    demo = bool(getattr(heat, "is_demo", False))
    for record in heat.records(None) or []:
        if not isinstance(record, dict) or record.get("duplicate_of"):
            continue
        created = summary_mod.parse_time(record.get("created_at"))
        if created is None or created > as_of:
            continue
        rec_district = engine.complaint_district(record) if engine is not None else record.get("district")
        if district and rec_district != district:
            continue
        if summary_mod.status_at(record, as_of) not in OPEN:
            continue
        service = routing.service_for(record.get("category"), record.get("subtopic"))
        row = rows.setdefault(service["id"], {"service": service["id"], "ru": service.get("ru"),
                                              "kk": service.get("kk"), "open": 0, "overdue": 0, "max_overdue_by": 0,
                                              "demo": False})
        row["open"] += 1
        row["demo"] = row["demo"] or bool(record.get("demo"))
        timer = deadlines.timer(record.get("category"), created, as_of)
        if timer.get("state") == "overdue":
            row["overdue"] += 1
            row["max_overdue_by"] = max(row["max_overdue_by"], int(timer.get("overdue_by") or 0))
        demo = demo or bool(record.get("demo"))
    items = sorted(rows.values(), key=lambda r: (-r["overdue"], -r["max_overdue_by"], -r["open"], r["service"]))
    return {"items": items, "demo": demo, "source": "deadlines", "as_of": as_of.isoformat(timespec="seconds")}


# ---------------------------------------------------------------- соседи раунда 15 (имена — по CONTRACT §7)
# Пока модуля нет, find_function вернёт None → not_ready. Когда сосед сдаст работу под другим именем,
# достаточно добавить имя в кортеж (или R01 подключит источник через configure).

# Первое имя в каждом кортеже — функция, которую сосед сделал для R03 (его __init__.py, раунд 15):
#   R17 board_snapshot(days, district), active_incidents(district); R12 conflicts_summary(district);
#   R16 initiatives_summary(district); R13 board_block(district=…). Остальные имена — запас по CONTRACT §7.
AGENCIES_MODULES = ("ui.civic_agencies", "ui.civic_agencies.board", "ui.civic_agencies.service", "ui.civic_agencies.api")
BOARD_FUNCS = ("board_snapshot", "board", "agencies_board", "board_summary", "service_board", "get_board")
INCIDENT_FUNCS = ("active_incidents", "list_incidents", "incidents", "public_incidents", "get_incidents")
GEO_MODULES = ("engine.civic_geo.works_calendar", "engine.civic_geo.works", "engine.civic_geo.calendar",
               "engine.civic_geo")
CONFLICT_FUNCS = ("conflicts_summary", "works_conflicts", "list_conflicts", "conflicts", "find_conflicts")
TOGETHER_MODULES = ("ui.civic_together", "ui.civic_together.service", "ui.civic_together.store")
INITIATIVE_FUNCS = ("initiatives_summary", "list_initiatives", "initiatives", "public_initiatives", "get_initiatives")
MEETINGS_MODULES = ("ui.civic_meetings", "ui.civic_meetings.service", "ui.civic_meetings.store")
MEETING_FUNCS = ("board_block", "list_meetings", "meetings", "public_meetings", "get_meetings")


def neighbour(modules, funcs):
    """Функция-источник «спросить соседа»: (**kwargs) → данные; соседа нет → NotReady."""
    def call(**kwargs):
        modname, _name, fn = find_function(modules, funcs)
        if fn is None:
            raise NotReady(modules[0])
        answer = unwrap(call_flexible(fn, **kwargs))
        # Сосед есть, но не связан с базой: None (R13 board_block), {"status": "no_data"} (R16),
        # {"source": "none", "empty": True} (R17 board_snapshot) — это «пока нет данных», а не ноль.
        if answer is None or (isinstance(answer, dict) and (answer.get("status") == "no_data"
                                                            or answer.get("source") == "none")):
            raise NotReady(modname or modules[0])
        return answer
    call.modules = modules
    return call


agencies_board = neighbour(AGENCIES_MODULES, BOARD_FUNCS)
agencies_incidents = neighbour(AGENCIES_MODULES, INCIDENT_FUNCS)
works_conflicts = neighbour(GEO_MODULES, CONFLICT_FUNCS)
together_initiatives = neighbour(TOGETHER_MODULES, INITIATIVE_FUNCS)
meetings_list = neighbour(MEETINGS_MODULES, MEETING_FUNCS)


def forecast(**kwargs):
    """R13 прогноз (раунд 14, есть в FINAL-4): forecast_response(month, district, k)."""
    _mod, _name, fn = find_function(("ui.civic_forecast",), ("forecast_response",))
    if fn is None:
        raise NotReady("ui.civic_forecast")
    return unwrap(call_flexible(fn, **kwargs))
