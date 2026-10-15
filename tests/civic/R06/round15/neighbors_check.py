"""Стык ленты R06 с НАСТОЯЩИМИ модулями соседей (не pytest: запускается на дереве, где есть их модули).

    bash tests/civic/R06/round15/neighbors_tree.sh /путь/к/дереву      # HEAD R06 + модули R09, R13, R16, R17, мир R02
    cd /путь/к/дереву && CIVIC_DEMO=1 CIVIC_DEMO_WORLD=1 python3 -B tests/civic/R06/round15/neighbors_check.py

Что делает: новая база → seed_world всех модулей на одном материализованном мире R02 → житель (одно устройство)
отмечает двор «Я живу здесь» (R16), записывается на субботник (R16), подаёт жалобу (R09), подписан на Нуру в «Рядом»
(R08) → лента R06 для этого устройства: источники ok, события каждого модуля, ссылки внутренние, чужих данных нет.
Печатает итог JSON; код выхода 1 — если проверка не прошла.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="r06-neighbors-"))
    db = str(tmp / "civic.sqlite3")
    os.environ["CIVIC_DB_PATH"] = db
    os.environ["BIRGE_AKIM_SUBSCRIPTIONS"] = str(tmp / "subs.json")
    from ml.datasets.demo_world_io import load_world, materialize
    from ui.civic_store.service import CivicService
    from ui.civic_store import v2 as r06
    now = datetime.now(timezone.utc)
    world = materialize(load_world(), now)
    svc = CivicService(db)
    r06.bind(svc)
    out = {"tree": str(ROOT), "seed": {}, "checks": []}

    def check(name, ok, detail=None):
        out["checks"].append({"name": name, "ok": bool(ok), "detail": detail if not ok else None})

    # 1. засев всех модулей на одном мире (как R01 по патчу R02)
    seeds = [("R06", "ui.civic_store"), ("R16", "ui.civic_together"), ("R17", "ui.civic_agencies"),
             ("R13", "ui.civic_meetings"), ("R09", "ui.civic_feedback.v2.integration")]
    services = {}
    for role, name in seeds:
        try:
            module = importlib.import_module(name)
            if role == "R09":
                services["R09"] = module.make_service(db)
            if role in ("R16", "R17", "R13"):
                services[role] = module.make_service(db, demo=False) if role != "R17" else module.make_service(db)
            fn = getattr(module, "seed_world")
            kwargs = {"reset": True} if "reset" in fn.__code__.co_varnames else {}
            res = fn(db, world, now, **kwargs)
            out["seed"][role] = {k: v for k, v in (res or {}).items() if k in ("inserted", "skipped", "reset", "source")}
        except Exception as exc:  # noqa: BLE001
            out["seed"][role] = f"ERROR {type(exc).__name__}: {exc}"[:300]
    # 2. житель
    device = "d-" + "N" * 24
    ideas_device = "dev-" + "n" * 32
    scene = world.get("scenes", {}).get("scene7", {})
    yard = scene.get("yard")
    initiative = scene.get("initiative")
    together = services.get("R16")
    ctx = {"headers": {"x-birge-device": device}, "host_allowed": True, "is_same_origin": True, "client_ip": "127.0.0.1"}
    if together is not None and yard:
        r = together.handle("POST", f"/api/civic/v2/together/yards/{yard}/join", "", json.dumps({}).encode(), None, ctx)
        check("R16: «Я живу здесь» для двора сцены 7", r["status"] in (200, 201), r)
    if together is not None and initiative:
        r = together.handle("POST", f"/api/civic/v2/together/initiatives/{initiative}/join", "", json.dumps({}).encode(), None, ctx)
        check("R16: «Я приду» на субботник сцены 7", r["status"] in (200, 201), r)
    complaints = services.get("R09")
    if complaints is not None:
        body = {"text": "Яма на тротуаре у подъезда", "lang": "ru", "category": "roads", "point": [71.4185, 51.1285],
                "district": "nura", "request_id": "r06-neighbors-check-1"}
        r = complaints.handle("POST", "/api/civic/v2/complaints", "", json.dumps(body).encode(), None, ctx)
        check("R09: жалоба жителя", r["status"] in (200, 201), str(r)[:300])
    nearby = importlib.import_module("ui.civic_akim.nearby")
    nearby.subscribe(device, "district", "nura")
    # 3. лента
    data = r06.list_notifications(context={"headers": {"x-birge-device": device, "x-birge-ideas-device": ideas_device},
                                           "host_allowed": True})
    out["sources"] = data["sources"]
    kinds = {}
    for e in data["items"]:
        kinds.setdefault(e["module"], set()).add(e["kind"])
    out["kinds"] = {k: sorted(v) for k, v in kinds.items()}
    out["unread"] = data["unread"]
    out["sample"] = [{k: e[k] for k in ("module", "kind", "title_ru", "link")} for e in data["items"][:12]]
    for role in ("R09", "R16", "R17", "R13"):
        check(f"лента: сосед {role} подключён (не absent/error)", data["sources"].get(role) == "ok", data["sources"].get(role))
    check("лента: события R16 (двор/дело)", "R16" in kinds, out["kinds"])
    check("лента: работы рядом R06 (подписка на Нуру)", "work.near" in kinds.get("R06", set()), out["kinds"])
    text = json.dumps(data, ensure_ascii=False)
    check("лента: нет id устройства жителя", device not in text and ideas_device not in text)
    check("лента: все ссылки внутренние", all(e["link"] is None or e["link"].startswith("#") for e in data["items"]))
    out["ok"] = all(c["ok"] for c in out["checks"])
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
