"""R16 · «Бірге: жители вместе» (раунд 15): «Мой двор» и «Сделаем вместе» — инициативы соседей, «Я приду»,
поддержка акимата, отчёт «Сделано вместе». Своя часть той же SQLite (таблицы tg_*), CONTRACT §5.2–5.3, §7, §10.

    from ui.civic_together import make_service
    service = make_service(".runtime/civic.sqlite3")        # та же база, что у шлюза R01 (CIVIC_DB_PATH)
    service.handle("GET", "/api/civic/v2/together/yards/yard-1454082638", "", None, principal=None,
                   context={"headers": {"x-birge-device": "d-…"}})
      -> {"status": 200, "headers": {}, "body": {"yard": {...}, "counts": {...}, ...}}

Функции для соседей (вызов в процессе; модуля нет — сосед пропускает блок):
    updates(device_id, since=None)          — R06: события ленты «Что нового для меня» (CONTRACT §5.8)
    seed_world(db_path, records, now=None)  — R01: своя часть демо-мира R02 (дворы, инициативы), идемпотентно
    create_from_idea(idea, starts_at=None)  — R06: POST ideas/{id}/to-initiative («Сделайте вместе — поддержим»)
    initiatives_summary(district=None)      — R08/R03: сколько дел, сколько соседей пришло (числа — код)
    pickups(district=None)                  — R17: вывоз мусора после дел, которые поддержал акимат (служба waste)
    configure(problems=…, ideas=…, works=…) — R01/тесты: подменить источник блока «Мой двор»

Подключение к шлюзу, маршруты, лимиты и экран — research/round-15-results/R16/INTEGRATION.txt.
Экран — web/civic/together/together.js (window.BirgeTogether, разделы оболочки #yard и #together).
"""

from __future__ import annotations

from datetime import datetime

from . import demo as _demo
from .neighbors import configure
from .service import TogetherService, default_service, make_service
from .store import TogetherStore

SCENE = _demo.SCENE

__all__ = ["SCENE", "TogetherService", "TogetherStore", "configure", "create_from_idea", "default_service",
           "initiatives_summary", "make_service", "pickups", "seed_world", "updates"]


def updates(device_id, since=None, db_path=None, limit: int = 50) -> list[dict]:
    """События R16 для ленты R06: двор устройства, инициативы, куда оно записалось, его собственные.
    Нет базы или сервиса — пустой список (лента просто без блока R16)."""
    service = default_service(db_path)
    if service is None:
        return []
    return service.updates(device_id, since, limit=limit)


def seed_world(db_path, records, now: datetime | None = None) -> dict:
    """Своя часть демо-мира R02 (yards, initiatives): {"inserted", "skipped", "reset", "source"}.

    Повтор возвращает демо-записи к виду мира от нового now (просьба R02, как reset у R09 и R17): через сутки
    «Субботник в субботу» не окажется в прошлом, «Я приду» снова 14. Записи жителей не трогает.
    В демо-мире нет инициатив — засевается фикстура модуля, чтобы сцена 7 не была пустой."""
    store = TogetherStore(db_path)
    moment = now or store.now()
    yards, items = _demo.world_part(records if isinstance(records, dict) else {}, moment)
    source = "world"
    if not items:
        yards, items = _demo.rows(moment)
        source = "fixture"
    result = store.seed(yards, items, reset=True)
    return dict(result, source=source)


def create_from_idea(idea: dict, *, starts_at: str | None = None, db_path=None, actor: str = "staff") -> dict:
    """Идея -> опубликованная инициатива с поддержкой акимата (инвентарь и вывоз). Ошибка данных — ValueError."""
    service = default_service(db_path)
    if service is None:
        raise RuntimeError("R16: нет базы (CIVIC_DB_PATH) — инициативу не создать")
    return service.create_from_idea(idea, starts_at=starts_at, actor=actor)


def initiatives_summary(district: str | None = None, db_path=None) -> dict:
    """Для «Картины дня» и Ситуационного центра R08 и «Спросить Birge» R03: числа считает код (CONTRACT §0)."""
    service = default_service(db_path)
    if service is None:
        return {"status": "no_data"}
    store = service.store
    upcoming = store.list(statuses=("published",), district=district, upcoming_only=True, limit=60)
    done = store.list(statuses=("done",), district=district, limit=60)
    return {"status": "ok", "district": district, "upcoming": len(upcoming),
            "joined_upcoming": sum(int(r.get("joined") or 0) for r in upcoming),
            "supported": sum(1 for r in upcoming if (r.get("support") or {}).get("by_akimat")),
            "done": len(done), "neighbors_done": sum(int((r.get("report") or {}).get("joined_final") or r.get("joined")
                                                         or 0) for r in done),
            "on_review": store.count(statuses=("on_review",), district=district),
            "next": [{"id": r["id"], "title": r.get("title_public") or r["title"], "starts_at": r["starts_at"],
                      "joined": int(r.get("joined") or 0), "district": r.get("district"),
                      "target": {"kind": "area", "id": r["target_id"]} if r.get("target_id") else None,
                      "demo": bool(r.get("demo"))} for r in upcoming[:3]],
            "demo": bool(upcoming or done) and all(r.get("demo") for r in upcoming + done)}


def pickups(district: str | None = None, db_path=None) -> list[dict]:
    """Для R17 (задача оператору вывоза, CONTRACT §3 «waste»): опубликованные дела, где акимат обещал вывоз мусора.
    Только то, что видно всем: дело, место, время, заметка акимата — без жителей и устройств."""
    service = default_service(db_path)
    if service is None:
        return []
    out = []
    for row in service.store.list(statuses=("published",), district=district, upcoming_only=True, limit=60):
        support = row.get("support") or {}
        if not support.get("by_akimat") or not support.get("pickup_service"):
            continue
        out.append({"initiative_id": row["id"], "service": support["pickup_service"],
                    "title": row.get("title_public") or row["title"], "point": [row["lon"], row["lat"]],
                    "district": row.get("district"), "target": {"kind": "area", "id": row["target_id"]}
                    if row.get("target_id") else None, "starts_at": row["starts_at"], "ends_at": row.get("ends_at"),
                    "note": support.get("note"), "supported_at": support.get("at"), "demo": bool(row.get("demo"))})
    return out
