"""Соседи «Ситуационного центра» и «Картины дня» 2.0 (R08, раунд 15): что читаем у R17, R16, R13. Только чтение.

КТО ЧТО ДАЁТ (CONTRACT §5, §7):
    R17 ui.civic_agencies ... табло служб (agencies/board), совместные (agencies/joint), передачи (agencies/handoffs),
                              кризисы (incidents, формат §5.5);
    R16 ui.civic_together ... инициативы жителей (§5.2) и дворы (§5.3);
    R13 ui.civic_meetings ... встречи с поручениями (§5.7);
    R13 ui.civic_forecast ... прогноз (прототип на синтетике): на неделю, если есть, иначе на месяц (раунд 14).

КАК ИЩЕМ У СОСЕДА (по порядку; первый ответ — он и есть):
  1. Явная подстановка: configure(neighbor_sources={"agencies_board": fn, ...}) — R01 в wire() или тесты.
  2. Функция модуля по одному из имён FUNCS ниже (CONTRACT §7: «вызовы между модулями — через функции соседа»).
     Параметры передаём только те, что функция принимает (days, district, status, db_path, now).
  3. Сервис соседа make_service(db_path).handle("GET", <маршрут CONTRACT §7>, …) — тот же ответ, что видит экран соседа.
     Маршруты akim/board и akim/week открыты только сотруднику (шлюз R01), поэтому читаем от имени сотрудника
     (READER, роль editor) — и только GET. База — configure(db_path=…), иначе CIVIC_DB_PATH, иначе .runtime/civic.sqlite3.
  4. Фикстура fixtures/*_demo.json (все записи demo: true) — ТОЛЬКО на стенде и в тестах (BIRGE_AKIM_FIXTURES=1 или
     configure(fixtures=True)); при CIVIC_DEMO_WORLD=1 — никогда: числа приходят из модулей (раунд 15, задача 5).
  Нет ни одного — источник «не готов»: блок на экране скрыт или «пока нет данных», а не ошибка.

Сосед упал — ответ {"available": False, "reason": "module_failed"}: экран прячет блок, сервер не падает.
Числа соседа НЕ пересчитываем (табло служб считает R17, хронику — R07): только выбираем, что показать, и подписываем.
"""
from __future__ import annotations

import importlib
import inspect
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import deadlines

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
ASTANA_TZ = timezone(timedelta(hours=5))
PREFIX = "/api/civic/v2"
log = logging.getLogger("civic_akim")

# Имена функций у соседей — по порядку. Первое найденное и вызывается (R17/R16/R13 называют сами; новое имя —
# одна строка здесь). Ответ — тело того же вида, что у маршрута CONTRACT §7 (dict), или список записей.
FUNCS = {
    # R17 (claude/sweet-euler-5tiu5b): agencies_week — блок «Ведомства» (3 отстающие, совместные, передачи за неделю,
    # порядок и числа R17); board_snapshot — табло служб как GET agencies/board; active_incidents — идущие кризисы.
    "agencies_week": ("ui.civic_agencies", ("agencies_week", "akim_agencies_week")),
    "agencies_board": ("ui.civic_agencies", ("akim_board", "board_snapshot", "board_for_akim", "agencies_board", "board_summary")),
    "agencies_joint": ("ui.civic_agencies", ("akim_joint", "joint_summary", "list_joint", "joint")),
    "agencies_handoffs": ("ui.civic_agencies", ("akim_handoffs", "list_handoffs", "handoffs")),
    "incidents": ("ui.civic_agencies", ("akim_incidents", "active_incidents", "list_incidents", "incidents")),
    "initiatives": ("ui.civic_together", ("akim_initiatives", "list_initiatives", "initiatives")),
    "yards": ("ui.civic_together", ("akim_yards", "list_yards", "yards")),
    # R13 (claude/gifted-mayer-p86myv): board_block — ближайшая встреча и открытые поручения со сроком (их порядок);
    # запасной путь — список встреч §5.7 (функция или GET meetings).
    "meetings_block": ("ui.civic_meetings", ("board_block", "akim_meetings_block")),
    "meetings": ("ui.civic_meetings", ("akim_meetings", "list_meetings", "meetings")),
    "forecast_week": ("ui.civic_forecast", ("attention_next_week", "forecast_week", "week_forecast", "akim_forecast_week")),
    "forecast_month": ("ui.civic_forecast", ("attention_next_month",)),
}
# Запасной путь — маршрут соседа (CONTRACT §7). Модуль, функция-фабрика, путь, строка запроса.
ROUTES = {
    "agencies_board": ("ui.civic_agencies", "/agencies/board", "days={days}"),
    "agencies_joint": ("ui.civic_agencies", "/agencies/joint", ""),
    "agencies_handoffs": ("ui.civic_agencies", "/agencies/handoffs", "days={days}"),
    "incidents": ("ui.civic_agencies", "/incidents", ""),
    "initiatives": ("ui.civic_together", "/together/initiatives", ""),
    "meetings": ("ui.civic_meetings", "/meetings", ""),
}
# Фикстура для стенда и тестов: файл и ключ внутри (формат CONTRACT §5).
FIXTURE_FILES = {
    "agencies_board": ("agencies_demo.json", "board"),
    "agencies_joint": ("agencies_demo.json", "joint"),
    "agencies_handoffs": ("agencies_demo.json", "handoffs"),
    "incidents": ("incidents_demo.json", "incidents"),
    "initiatives": ("together_demo.json", "initiatives"),
    "yards": ("together_demo.json", "yards"),
    "meetings": ("meetings_demo.json", "meetings"),
}
OWNER = {"agencies_week": "R17", "agencies_board": "R17", "agencies_joint": "R17", "agencies_handoffs": "R17",
         "incidents": "R17", "initiatives": "R16", "yards": "R16", "meetings_block": "R13", "meetings": "R13",
         "forecast_week": "R13", "forecast_month": "R13"}
# Модули, чьи функции для соседей читают сервис, созданный шлюзом (R17: api_state.current()). Пока шлюз его не
# создал (никто ещё не открыл «Ведомства»), функции отвечают пусто — поэтому сервис создаём сами на той же базе.
NEEDS_SERVICE = {"ui.civic_agencies"}


class _Reader(dict):
    """Сотрудник-читатель для сервисов соседей: и словарь (как principal шлюза), и объект (как principal R02)."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


READER = _Reader(username="akim-board", role="editor", is_staff=True)


def demo_world() -> bool:
    """Демо-мир R02 (CIVIC_DEMO_WORLD=1): числа — только из модулей, фикстуры R08 не подмешиваются."""
    return os.environ.get("CIVIC_DEMO_WORLD") == "1"


def fixtures_env() -> bool:
    return os.environ.get("BIRGE_AKIM_FIXTURES") == "1"


# ---------------------------------------------------------------- время в фикстурах

def _rel_time(item: dict, now: datetime) -> dict:
    """Фикстура живёт «сегодня»: ago_days / ago_hours / in_days / in_hours → ISO-время относительно now (как демо-мир R02).

    Ключ вида «starts_at__in_days» превращается в «starts_at». Вложенные словари и списки — так же.
    """
    if isinstance(item, list):
        return [_rel_time(x, now) if isinstance(x, (dict, list)) else x for x in item]
    out = {}
    for key, value in item.items():
        if "__" in key and isinstance(value, (int, float)):
            name, how = key.split("__", 1)
            sign = -1 if how.startswith("ago_") else 1
            unit = how.split("_", 1)[1] if "_" in how else "days"
            delta = timedelta(hours=value) if unit == "hours" else timedelta(days=value)
            moment = now + sign * delta
            out[name] = moment.date().isoformat() if name in ("due", "starts_on", "ends_on") else \
                moment.astimezone(ASTANA_TZ).isoformat(timespec="seconds")
        elif isinstance(value, (dict, list)):
            out[key] = _rel_time(value, now)
        else:
            out[key] = value
    return out


def fixture(name: str, now: datetime):
    file, key = FIXTURE_FILES[name]
    raw = json.loads((FIXTURES / file).read_text("utf-8"))
    return _rel_time({"x": raw[key]}, now)["x"]


# ---------------------------------------------------------------- чтение соседей

def _accepts(fn, kwargs: dict) -> dict:
    """Только те параметры, что функция соседа принимает (у старой функции нового параметра нет — не падаем)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return dict(kwargs)
    return {k: v for k, v in kwargs.items() if k in params}


def _import(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", None) or ""
        if name == missing or name.startswith(missing + "."):
            return None  # модуля ещё нет в сборке — «не готов», не ошибка
        raise


def default_db_path() -> str | None:
    value = os.environ.get("CIVIC_DB_PATH") or os.environ.get("CIVIC_DB")
    if value:
        return str(Path(value).expanduser())
    fallback = deadlines.ROOT / ".runtime" / "civic.sqlite3"
    return str(fallback) if fallback.is_file() else None


class Neighbors:
    """Источники соседей. get(name, **kw) → (данные | None, откуда: custom|r17|r16|r13|fixture|none|failed)."""

    def __init__(self, *, sources: dict | None = None, db_path=None, fixtures: bool | None = None):
        self.sources = dict(sources or {})
        self.db_path = str(db_path) if db_path else None
        self._fixtures = fixtures
        self._services: dict = {}
        self._lock = threading.Lock()

    @property
    def fixtures(self) -> bool:
        if demo_world():
            return False
        return fixtures_env() if self._fixtures is None else bool(self._fixtures)

    def _service(self, module_name: str):
        """Сервис соседа на той же базе (один на процесс). Нет базы или фабрики — None.

        Сначала default_service(db_path) соседа (R16: общий экземпляр без демо-засева), потом make_service(db_path)."""
        with self._lock:
            if module_name in self._services:
                return self._services[module_name]
            service = None
            module = _import(module_name)
            db_path = self.db_path or default_db_path()
            for name in ("default_service", "make_service"):
                factory = getattr(module, name, None) if module is not None else None
                if not callable(factory) or not db_path:
                    continue
                try:
                    service = factory(db_path)
                except Exception:
                    log.exception("akim board: сервис %s (%s) не запустился", module_name, name)
                    service = None
                if service is not None:
                    break
            self._services[module_name] = service
            return service

    def get(self, name: str, *, now: datetime, **kwargs):
        owner = OWNER[name].lower()
        custom = self.sources.get(name)
        if custom is not None:
            if custom is False:  # подстановка «соседа нет» (тесты, R01)
                return None, "none"
            return custom(**_accepts(custom, {**kwargs, "now": now})), "custom"
        module_name, names = FUNCS[name]
        module = _import(module_name)
        if module is not None:
            if module_name in NEEDS_SERVICE:
                self._service(module_name)
            for fn_name in names:
                fn = getattr(module, fn_name, None)
                if callable(fn):
                    args = {**kwargs, "now": now, "db_path": self.db_path or default_db_path()}
                    return fn(**_accepts(fn, args)), owner
            route = ROUTES.get(name)
            if route:
                service = self._service(module_name)
                handle = getattr(service, "handle", None)
                if callable(handle):
                    query = route[2].format(days=kwargs.get("days", 7))
                    if kwargs.get("district") and name == "agencies_board":  # district — только у agencies/board (§7)
                        query = (query + "&" if query else "") + "district=" + str(kwargs["district"])
                    reply = handle("GET", PREFIX + route[1], query, None, READER, {"internal": "R08"})
                    if isinstance(reply, dict) and reply.get("status") == 200:
                        body = reply.get("body")
                        if isinstance(body, dict) and body.get("ok") is True and "data" in body:
                            body = body["data"]  # конверт ok/data (как у R09)
                        return body, owner
                    log.warning("akim board: %s %s ответил %s", module_name, route[1],
                                reply.get("status") if isinstance(reply, dict) else type(reply).__name__)
                    return None, "failed"
        if self.fixtures and name in FIXTURE_FILES:
            return fixture(name, now), "fixture"
        return None, "none"

    def safe(self, name: str, *, now: datetime, **kwargs):
        """Как get, но сбой соседа → (None, "failed"): картина не падает из-за чужого модуля."""
        try:
            return self.get(name, now=now, **kwargs)
        except Exception:
            log.exception("akim board: сосед %s (%s) упал", name, OWNER.get(name))
            return None, "failed"


# ---------------------------------------------------------------- разбор ответов соседей

def items_of(answer, *keys: str) -> list:
    """Ответ соседа → список записей: сам список, или answer[keys…] / answer["items"]."""
    if isinstance(answer, list):
        return [x for x in answer if isinstance(x, dict)]
    if not isinstance(answer, dict):
        return []
    for key in keys + ("items",):
        value = answer.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
    return []


def number(row: dict, *names: str):
    """Первое число из полей names (bool — не число); нет — None."""
    for name in names:
        value = row.get(name) if isinstance(row, dict) else None
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, dict):  # {"count": 3} / {"value": 3}
            inner = number(value, "count", "value", "total", "open")
            if inner is not None:
                return inner
    return None
