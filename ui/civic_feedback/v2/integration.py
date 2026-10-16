"""Точка подключения жалоб v2 к шлюзу R01 (ui/web_server.py) — без изменения кода R09.

    from ui.civic_feedback.v2.integration import make_service, ROUTES
    complaints = make_service(civic_db_path)            # те же SQLite-файл, что у v1, свои таблицы
    # в шлюзе /api/civic/v2: для маршрутов из ROUTES
    reply = complaints.handle(method, "/api/civic/v2" + rel_path, query, body, principal, context)

Цель жалобы (R15 S04/S12): подписи берутся только с карты R12, а цель дальше 300 м от точки жителя становится
«примерным местом». Карту подключает хост: make_service(db, target_lookup=geo_target_lookup()) или
store.target_lookup = engine.civic_geo.target_geometry (так делает шлюз R01 в wire()). Без карты подписи из запроса
не сохраняются, а ячейки «примерного места» R09 проверяет по своей сетке.

Демо-сборка (CIVIC_DEMO=1, R10 B-030): make_service(db, demo_seed=True) засевает несколько синтетических жалоб
(demo: true, «Пример») у остановки из сценария, чтобы на шаге 2 демо было «Я тоже». Повтор ничего не дублирует.

principal — store.resolve_principal(context) (R02) или None; context — как у v1:
{"headers": заголовки запроса (нужен X-Birge-Device, для сотрудника X-CSRF-Token),
 "host_allowed": bool, "is_same_origin": bool|None}.
"""

from __future__ import annotations

from .api import ComplaintsV2Service
from .store import ComplaintStore

# (метод, шаблон пути после /api/civic/v2) — для таблицы маршрутов R01. {id} — id или номер B-0001.
ROUTES = (
    ("GET", "/categories"),
    ("GET", "/complaints"),
    ("POST", "/complaints"),
    ("GET", "/complaints/mine"),
    ("GET", "/complaints/events"),
    ("GET", "/complaints/summary"),
    ("GET", "/complaints/place"),
    ("GET", "/complaints/{id}"),
    ("POST", "/complaints/{id}/metoo"),
    ("POST", "/complaints/{id}/status"),      # только сотрудник (R02 session + CSRF)
    ("POST", "/complaints/{id}/duplicate"),   # только сотрудник
    # Волны 1–2 (POLISH_WAVE.md, POLISH_WAVE_2.md). «changes» — точный путь, в таблице R01 раньше {id}.
    ("GET", "/complaints/changes"),
    ("GET", "/complaints/inbox"),             # только сотрудник: экран «Обращения» (#complaints)
    ("POST", "/complaints/{id}/verify"),      # житель: автор или «Я тоже»
    ("POST", "/complaints/{id}/passport"),    # только сотрудник
    ("POST", "/complaints/{id}/update"),      # только сотрудник
    ("POST", "/complaints/{id}/unduplicate"), # только сотрудник
    ("POST", "/complaints/{id}/photos"),      # житель (автор) — resident; сотрудник — after
    ("POST", "/complaints/{id}/photos/{upload}"),
    ("GET", "/complaints/{id}/photos/{photo}"),
    ("POST", "/complaints/{id}/unsubscribe"), # житель: «Отписаться» от «Я тоже»
    ("GET", "/complaints/merged"),            # только сотрудник: что объединено с жалобами цели (п. 9, R04)
    ("POST", "/complaints/{id}/separate"),    # только сотрудник: «Это разные проблемы» (п. 9, R04)
    # Раунд 15 (CONTRACT §7): обращение для нескольких служб — только сотрудник (сессия R02 + CSRF).
    ("POST", "/complaints/{id}/handoff"),     # «Передать в другую службу» {to, reason | reason_code, keep?}
    ("POST", "/complaints/{id}/services"),    # «Совместное исполнение» {services: [{service, role}]}
    ("POST", "/complaints/{id}/part"),        # статус части службы {service, status, note?}
)


def geo_target_lookup():
    """engine.civic_geo.target_geometry (R12), если модуль есть в сборке; иначе None."""
    try:
        from engine.civic_geo import target_geometry
    except ImportError:
        return None
    return target_geometry


def r08_assignee_lookup():
    """ui.civic_akim.routing.service_for (R08: таблица «категория/уточнение → служба» с правками акимата), если
    модуль есть в сборке; иначе None — паспорт берёт таблицу R09 (копия умолчаний R08)."""
    try:
        from ui.civic_akim.routing import service_for
    except ImportError:
        return None
    return service_for


def r08_decision_lookup():
    """ui.civic_akim.decisions.choice_for (R08: выбор акима по обращению) или None."""
    try:
        from ui.civic_akim.decisions import choice_for
    except ImportError:
        return None
    return choice_for


def r08_nearby_lookup():
    """ui.civic_akim.nearby.updates_for (R08: обновления подписок «Рядом» для «Что изменилось») или None."""
    try:
        from ui.civic_akim.nearby import updates_for
    except ImportError:
        return None
    return updates_for


def r04_route_lookup():
    """ui.civic_ml_api.route (R04, раунд 15: «Похоже, нужны 2 службы») или None — подсказки нет, всё работает."""
    try:
        from ui.civic_ml_api import route
    except ImportError:
        return None
    return route if callable(route) else None


def make_service(db_path, *, target_lookup=None, assignee_lookup="auto", route_lookup="auto", demo_seed: bool = False,
                 **store_options) -> ComplaintsV2Service:
    store = ComplaintStore(db_path, **store_options)
    # "auto" — взять R12 из сборки, если он есть. По умолчанию None: тесты соседей создают жалобы с условными id.
    store.target_lookup = geo_target_lookup() if target_lookup == "auto" else target_lookup
    # «Кому передано» (волна 1, п. 7): по умолчанию — таблица R08, если она в сборке.
    store.assignee_lookup = r08_assignee_lookup() if assignee_lookup == "auto" else assignee_lookup
    # R08 в сборке: выбор акима в паспорте и подписки «Рядом» в «Что изменилось» (без R08 — None, всё работает).
    store.decision_lookup = r08_decision_lookup() if assignee_lookup == "auto" else None
    store.nearby_lookup = r08_nearby_lookup() if assignee_lookup == "auto" else None
    # Раунд 15: подсказка R04 «нужны 2 службы» сохраняется в route_hint новой жалобы (R04 нет — None).
    store.route_lookup = r04_route_lookup() if route_lookup == "auto" else route_lookup
    if demo_seed:
        from .demo_seed import seed_demo
        seed_demo(store)
    service = ComplaintsV2Service(store)
    _remember(store)
    return service


# ---------------------------------------------------------------- функции чтения для соседей (раунд 15, CONTRACT §7)
# Вызов в процессе, только чтение, без текстов жителей, точек и устройств. Первый аргумент — путь к SQLite (тот же
# CIVIC_DB_PATH), хранилище R09 или его сервис; None — хранилище, которое поднял шлюз (make_service) в этом процессе.
#   R17 «Штаб ведомств»:  service_parts(db, days=30) · handoffs(db, days=30)
#   R16 «Мой двор»:       yard_complaints(db, "yard-123", targets=[...], polygon=...)
#   R06 лента:            updates(device, since)  (CONTRACT §5.8)
# Запись (раунд 15+, П3): R04 «ИИ-разбор пачки» — intake_commit(None, batch_id, tasks, texts, demo=…) создаёт жалобы.
_STORES: dict[str, ComplaintStore] = {}
_DEFAULT: list[ComplaintStore] = []


def _remember(store: ComplaintStore) -> None:
    _STORES.setdefault(store.db_path, store)
    _DEFAULT[:] = [store]


def _store(source=None) -> ComplaintStore:
    if isinstance(source, ComplaintStore):
        return source
    inner = getattr(source, "store", None)
    if isinstance(inner, ComplaintStore):
        return inner
    if source is None:
        if _DEFAULT:
            return _DEFAULT[0]
        import os
        source = os.environ.get("CIVIC_DB_PATH")
        if not source:
            raise LookupError("Хранилище жалоб R09 не подключено (нет make_service и CIVIC_DB_PATH).")
    key = str(source)
    if key not in _STORES:
        store = ComplaintStore(key)
        store.assignee_lookup = r08_assignee_lookup()
        _STORES[key] = store
    return _STORES[key]


def service_parts(db=None, since=None, until=None, *, days=None, district=None) -> list[dict]:
    """Части служб по жалобам периода — табло служб R17 (CONTRACT §5.1): service, role, status у каждой жалобы."""
    return _store(db).service_parts(since, until, days=days, district=district)


def handoffs(db=None, since=None, until=None, *, days=None, district=None) -> list[dict]:
    """Журнал передач за период (новые сверху) — R17 «Передачи»: from, to, at, reason, by_role."""
    return _store(db).handoffs_log(since, until, days=days, district=district)


def yard_complaints(db=None, yard_id: str = "", *, days: int = 60, targets=None, polygon=None) -> dict:
    """Жалобы двора для «Мой двор» R16: {items, counts: {open, fixed, verified, total, people}} — без текстов."""
    if not isinstance(yard_id, str) or not yard_id:
        raise ValueError("Не указан двор.")
    return _store(db).yard_complaints(yard_id, days=days, targets=targets, polygon=polygon)


def updates(device, since=None, db=None) -> list[dict]:
    """События ленты R06 (CONTRACT §5.8) по жалобам устройства (автор и «Я тоже»): ответы и смены статуса,
    «служба сообщила», «проверено жителями», передачи и части служб. Без имён сотрудников и причин передач."""
    from .feed import feed_events
    store = _store(db)
    try:
        records = store.mine(device)
    except Exception:  # noqa: BLE001 — чужое или пустое устройство: ленте R06 — пусто, не ошибка
        return []
    return feed_events(records, since)


def seed_world(db_path, records, now=None, *, reset: bool = True) -> dict:
    """Демо-мир R02 (CONTRACT §11): жалобы, «Я тоже», статусы, части служб и передачи — в хранилище R09.
    Идемпотентно; reset=True (по умолчанию) — демо-записи мира к виду мира от нового now. -> {"inserted", "skipped",
    "reset", "invalid", "total"}. Подробно — world_seed.py."""
    from .world_seed import seed_world as seed
    return seed(db_path, records, now=now, reset=reset)


def intake_commit(db=None, batch_id: str = "", tasks=(), texts=None, *, demo: bool = False, actor=None, method=None,
                  now=None) -> dict:
    """«ИИ-разбор пачки обращений» R04 (П3, сцена 0): задачи пачки → жалобы R09 одной транзакцией, событие «created» у
    каждой. Идемпотентно по (batch_id, task_id); без точки задача не создаётся (skipped: no_place — «адрес уточнить»).
    db=None — хранилище шлюза. -> {"batch_id", "total", "people", "created": [{"task_id", "id", "code"}], "existing",
    "skipped": [{"task_id", "reason"}]}. ValueError — неверная пачка целиком. Подробно — intake.py."""
    from .intake import commit_tasks
    return commit_tasks(db, batch_id, tasks, texts, demo=demo, now=now, actor=actor, method=method)


def create_from_intake(store=None, items=(), *, batch_id: str = "", texts=None, demo: bool = False, actor=None,
                       method=None, now=None) -> dict:
    """То же, что intake_commit, под именем из контракта R04 (INTEGRATION R04 §9.3): store — хранилище, которое шлюз
    передал R04 в connect_store (или None — хранилище шлюза), items — задачи пачки."""
    from .intake import commit_tasks
    return commit_tasks(store, batch_id, items, texts, demo=demo, now=now, actor=actor, method=method)
