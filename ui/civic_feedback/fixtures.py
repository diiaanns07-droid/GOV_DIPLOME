"""FIXTURE ONLY — заглушки R02/R01 для тестов и демонстрации R06.

Это НЕ реальные объекты Астаны и НЕ реальная авторизация. Пока backend R02
(CivicService.resolve_principal и чтение объектов) не подключён, R06 проверяется
на этих данных. В продукте R01 передаёт настоящий object_lookup и principal.
"""

from __future__ import annotations

from copy import deepcopy

FIXTURE_NOTICE = "FIXTURE: синтетические объекты и учётные записи для тестов R06, не реальные данные."

_BASE = {
    "schema_version": "civic-v1",
    "id": "demo-astana-work-01",
    "city": "astana",
    "kind": "roadworks",
    "title": "Демонстрационный ремонт прохода",
    "description": "Синтетическая запись для проверки интерфейса. Не сведения о реальных работах.",
    "status": "planned",
    "publication": "published",
    "geometry": {"type": "Point", "coordinates": [71.43, 51.17]},
    "geometry_precision": "approximate",
    "schedule": {"planned_start": "2026-10-14", "original_planned_end": "2026-10-20",
                 "current_planned_end": "2026-10-22", "actual_end": None},
    "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
    "responsible": {"organization": None, "public_contact": None},
    "evidence_type": "synthetic",
    "source_refs": [],
    "evidence_notes": "Создано координатором для теста; не публиковать как реальный ремонт.",
    "updated_at": "2026-10-06T12:00:00+06:00",
    "revision": 2,
}


def _variant(**changes):
    item = deepcopy(_BASE)
    item.update(changes)
    return item


# Первый объект совпадает с research/round-11/fixtures/civic_object.json (PACK_SHA 9c2f5c0).
FIXTURE_OBJECTS = {
    item["id"]: item for item in (
        _BASE,
        _variant(id="demo-astana-park-02", kind="landscaping", title="Демонстрационный сквер",
                 geometry={"type": "Polygon", "coordinates": [[[71.40, 51.12], [71.41, 51.12],
                                                                [71.41, 51.13], [71.40, 51.13],
                                                                [71.40, 51.12]]]}),
        _variant(id="demo-astana-nogeo-03", title="Демонстрационный объект без геометрии",
                 geometry=None, geometry_precision="unknown"),
        _variant(id="demo-astana-draft-04", title="Черновик редактора (не публичный)",
                 publication="draft"),
        _variant(id="demo-astana-archived-05", title="Архивная запись", publication="archived"),
        _variant(id="demo-other-city-06", city="shymkent", title="Объект другого города",
                 geometry={"type": "Point", "coordinates": [69.59, 42.32]}),
    )
}


def fixture_object_lookup(object_id: str):
    """Возвращает копию объекта независимо от публикации — как служебное чтение R02."""
    item = FIXTURE_OBJECTS.get(object_id)
    return deepcopy(item) if item else None


def failing_object_lookup(object_id: str):
    raise RuntimeError("FIXTURE: справочник объектов недоступен")


# Серверные principal-заглушки. В продукте их создаёт resolve_principal(context).
FIXTURE_EDITOR = {"authenticated": True, "name": "fixture-editor", "role": "editor",
                  "csrf_token": "fixture-csrf-token-editor", "fixture": True}
FIXTURE_SECOND_EDITOR = {"authenticated": True, "name": "fixture-editor-2", "role": "editor",
                         "csrf_token": "fixture-csrf-token-editor-2", "fixture": True}
FIXTURE_RESIDENT = {"authenticated": True, "name": "fixture-resident", "role": "resident",
                    "csrf_token": "fixture-csrf-token-resident", "fixture": True}
FIXTURE_LOGGED_OUT = {"authenticated": False, "name": None, "role": None, "fixture": True}


def fixture_context(client_ip: str = "127.0.0.1", *, same_origin: bool = True,
                    csrf: str | None = None) -> dict:
    headers = {"Host": "127.0.0.1:8501", "Origin": "http://127.0.0.1:8501"}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    return {"headers": headers, "client_ip": client_ip, "is_same_origin": same_origin}
