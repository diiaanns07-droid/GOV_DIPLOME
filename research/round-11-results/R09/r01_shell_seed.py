"""Засев временной SQLite для проверки R09 внутри настоящего shell R01 (только синтетика).

    cd <R01 checkout с применённым r01_integration.patch и импортированными путями R09>
    python3 <этот файл> <db_path>     -> печатает JSON {object_id, title}

Пользователь-редактор создаётся со случайным одноразовым паролем, который нигде не сохраняется.
"""

import json
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path.cwd()))

from ui.civic_store.service import CivicService  # noqa: E402

db = Path(sys.argv[1])
db.parent.mkdir(parents=True, exist_ok=True)
svc = CivicService(str(db))
password = secrets.token_urlsafe(18)
svc.accounts.create_user("r09seed", password, display_name="R09 seed", public_label="Редакция (проверка R09)")


def call(method, path, body=None, cookie=None, csrf=None):
    headers = {"Host": "127.0.0.1"}
    if cookie:
        headers["Cookie"] = cookie
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return svc.handle(method, "/api/civic/v1" + path, {}, json.dumps(body).encode() if body is not None else None,
                      {"headers": headers, "client_ip": "127.0.0.1", "host_allowed": True, "is_same_origin": True,
                       "is_https": False})


login = call("POST", "/session/login", {"username": "r09seed", "password": password})
cookie, csrf = login["headers"]["Set-Cookie"].split(";", 1)[0], login["body"]["data"]["csrf_token"]
title = "Синтетический ремонт тротуара (проверка R09)"
body = {
    "kind": "roadworks", "title": title,
    "description": "Синтетическая запись для проверки помощника. Не сведения о реальных работах.",
    "status": "in_progress", "geometry": {"type": "Point", "coordinates": [71.43, 51.128]},
    "geometry_precision": "approximate",
    "schedule": {"planned_start": "2026-10-01", "original_planned_end": "2026-10-20",
                 "current_planned_end": "2026-10-20", "actual_end": None},
    "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
    "responsible": {"organization": None, "public_contact": None},
    "evidence_type": "synthetic", "source_refs": [], "evidence_notes": "Синтетика R09.",
}
item = call("POST", "/staff/objects", body, cookie, csrf)["body"]["data"]["item"]
item = call("POST", f"/staff/objects/{item['id']}/publish",
            {"expected_revision": item["revision"], "reason": "Первичная публикация (синтетика R09)"}, cookie, csrf)["body"]["data"]["item"]
schedule = dict(item["schedule"], current_planned_end="2026-11-05")
item = call("POST", f"/staff/objects/{item['id']}/update",
            {"expected_revision": item["revision"], "changes": {"schedule": schedule},
             "reason": "СЛУЖЕБНО: правка срока"}, cookie, csrf)["body"]["data"]["item"]
item = call("POST", f"/staff/objects/{item['id']}/publish",
            {"expected_revision": item["revision"],
             "reason": "Синтетическая причина: задержка поставки плитки (проверка R09)"}, cookie, csrf)["body"]["data"]["item"]
print(json.dumps({"object_id": item["id"], "title": title}, ensure_ascii=False))
