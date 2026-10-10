"""Точка подключения жалоб v2 к шлюзу R01 (ui/web_server.py) — без изменения кода R09.

    from ui.civic_feedback.v2.integration import make_service, ROUTES
    complaints = make_service(civic_db_path)            # те же SQLite-файл, что у v1, свои таблицы
    # в шлюзе /api/civic/v2: для маршрутов из ROUTES
    reply = complaints.handle(method, "/api/civic/v2" + rel_path, query, body, principal, context)

Цель жалобы (R15 S04/S12): подписи берутся только с карты R12, а цель дальше 300 м от точки жителя становится
«примерным местом». make_service по умолчанию сам подключает engine.civic_geo.target_geometry, если R12 есть в
сборке (target_lookup="auto"); без R12 подписи из запроса не сохраняются. Явно: make_service(db, target_lookup=f|None).

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
)


def geo_target_lookup():
    """engine.civic_geo.target_geometry (R12), если модуль есть в сборке; иначе None."""
    try:
        from engine.civic_geo import target_geometry
    except ImportError:
        return None
    return target_geometry


def make_service(db_path, *, target_lookup="auto", **store_options) -> ComplaintsV2Service:
    store = ComplaintStore(db_path, **store_options)
    store.target_lookup = geo_target_lookup() if target_lookup == "auto" else target_lookup
    return ComplaintsV2Service(store)
