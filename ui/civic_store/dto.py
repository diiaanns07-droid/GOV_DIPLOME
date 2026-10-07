"""Проекции civic-v1: публичный DTO строится только из allowlist контракта.

internal_notes, password_hash, сессии, импортные ключи и учётные записи
сюда не попадают по построению: каждое поле перечислено явно.
"""

from __future__ import annotations

from copy import deepcopy

from .validate import (BUDGET_KEYS, CITY, CONTENT_FIELDS, RESPONSIBLE_KEYS, SCHEDULE_KEYS,
                       SCHEMA_VERSION, SOURCE_REF_KEYS)


PUBLIC_FIELDS = ("schema_version", "id", "city", "kind", "title", "description", "status",
                 "publication", "geometry", "geometry_precision", "schedule", "budget",
                 "responsible", "evidence_type", "source_refs", "evidence_notes", "updated_at",
                 "revision")
PUBLIC_HISTORY_FIELDS = ("id", "object_id", "revision", "at", "changed_fields", "reason",
                         "public_actor_label")
_NESTED = {"schedule": SCHEDULE_KEYS, "budget": BUDGET_KEYS, "responsible": RESPONSIBLE_KEYS}


def _public_geometry(geometry):
    if not isinstance(geometry, dict):
        return None
    return {"type": geometry.get("type"), "coordinates": deepcopy(geometry.get("coordinates"))}


def public_dto(object_id: str, content: dict, *, publication: str, revision: int,
               updated_at: str) -> dict:
    """Публичная карточка объекта: только поля контракта civic-v1."""
    item = {
        "schema_version": SCHEMA_VERSION,
        "id": object_id,
        "city": CITY,
        "kind": content["kind"],
        "title": content["title"],
        "description": content["description"],
        "status": content["status"],
        "publication": publication,
        "geometry": _public_geometry(content["geometry"]),
        "geometry_precision": content["geometry_precision"],
        "schedule": {key: content["schedule"].get(key) for key in SCHEDULE_KEYS},
        "budget": {key: content["budget"].get(key) for key in BUDGET_KEYS},
        "responsible": {key: content["responsible"].get(key) for key in RESPONSIBLE_KEYS},
        "evidence_type": content["evidence_type"],
        "source_refs": [{key: deepcopy(ref.get(key)) for key in SOURCE_REF_KEYS}
                        for ref in content["source_refs"]],
        "evidence_notes": content["evidence_notes"],
        "updated_at": updated_at,
        "revision": revision,
    }
    return item


def sanitize_public(item: dict) -> dict:
    """Повторный allowlist при чтении из проекции (защита от повреждённой строки)."""
    out = {}
    for key in PUBLIC_FIELDS:
        value = item.get(key)
        if key in _NESTED:
            value = {name: (value or {}).get(name) for name in _NESTED[key]}
        elif key == "source_refs":
            value = [{name: deepcopy(ref.get(name)) for name in SOURCE_REF_KEYS}
                     for ref in (value or []) if isinstance(ref, dict)]
        elif key == "geometry":
            value = _public_geometry(value)
        out[key] = value
    return out


def content_of(item: dict) -> dict:
    """Содержимое (CONTENT_FIELDS) из публичного DTO для сравнения публикаций."""
    return {key: deepcopy(item.get(key)) for key in CONTENT_FIELDS}


def public_history_entry(row) -> dict:
    return {
        "id": row["id"],
        "object_id": row["object_id"],
        "revision": row["revision"],
        "at": row["at"],
        "changed_fields": list(row["changed_fields"]),
        "reason": row["reason"],
        "public_actor_label": row["public_actor_label"],
    }
