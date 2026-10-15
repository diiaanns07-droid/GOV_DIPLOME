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
    akim_initiatives / akim_yards(district) — R08: дела (публичные, «на проверке» — только числом) и дворы (числа)
    configure(problems=…, ideas=…, works=…) — R01/тесты: подменить источник блока «Мой двор»
    warm_up(db_path=None)                   — R01: при старте в фоне (как warm_up R12) — «Мой двор» без секунд ожидания

Подключение к шлюзу, маршруты, лимиты и экран — research/round-15-results/R16/INTEGRATION.txt.
Экран — web/civic/together/together.js (window.BirgeTogether, разделы оболочки #yard и #together).
"""

from __future__ import annotations

from datetime import datetime
import logging

from . import demo as _demo
from .neighbors import configure
from .service import TogetherService, default_service, make_service, start_warm_up
from .store import TogetherStore

SCENE = _demo.SCENE

__all__ = ["SCENE", "TogetherService", "TogetherStore", "akim_initiatives", "akim_yards", "configure", "create_from_idea",
           "default_service", "initiatives_summary", "make_service", "pickups", "seed_world", "updates", "warm_up"]


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
    # Двор сцены 7 — первым в списке дворов (IA R11 §5.1): из scenes мира или своей фикстуры.
    scene = ((records or {}).get("scenes") or {}).get("scene7") if isinstance(records, dict) else None
    store.meta("scene_yard", (scene or {}).get("yard") if source == "world" and scene else _demo.SCENE["yard"])
    # Демо-мир засевают при старте сервера: сразу прогреваем дворы в фоне (R10 B-124 — первая сцена части 2).
    start_warm_up(db_path=db_path)
    return dict(result, source=source)


def warm_up(db_path=None, limit: int = 4) -> dict:
    """Прогреть соседей для двора сцены демо и самых «людных» дворов: {"yards": [...], "ms"}. Блокирует — R01 зовёт
    в фоновом потоке при старте сервера (как engine.civic_geo.api.warm_up). Нет базы — ничего не делает."""
    try:
        service = default_service(db_path)
        return service.warm_up(limit=limit) if service is not None else {"yards": [], "ms": 0}
    except Exception:  # база ещё создаётся или сосед упал — первый житель просто подождёт расчёта
        logging.getLogger("civic_together").exception("R16: прогрев дворов не удался")
        return {"yards": [], "ms": 0}


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
            "next": [_summary_row(service, r) for r in upcoming[:3]],
            "demo": bool(upcoming or done) and all(r.get("demo") for r in upcoming + done)}


def _summary_row(service, row: dict) -> dict:
    """Ближайшее дело сводки — то же публичное представление, что GET together/initiatives: вид, время конца, поддержка
    акимата, место с подписью и настоящим видом цели (R08 «Поддержать» не ведёт к уже поддержанному делу без второго
    запроса). Без устройств и авторов; поля прежней сводки (id, title, starts_at, joined, district, target, demo) — те же."""
    view = service._public(row)
    for key in ("my_join", "mine"):
        view.pop(key, None)
    return view


def akim_initiatives(district: str | None = None, db_path=None) -> dict | None:
    """Для «Картины дня» / «Картины недели» R08 (ui/civic_akim/neighbors.py FUNCS «initiatives»): опубликованные и сделанные
    дела — в том же виде, что GET together/initiatives (публичные названия, без устройств и авторов); дела «на проверке» —
    только id, вид, район и статус (текст ещё не проверен — его нет). Нет базы — None («пока нет данных» у R08)."""
    service = default_service(db_path)
    if service is None:
        return None
    store = service.store
    items = [service._public(r) for r in store.list(statuses=("published", "done"), district=district, limit=200)]
    items += [{"id": r["id"], "kind": r["kind"], "status": "on_review", "district": r.get("district"),
               "demo": bool(r.get("demo"))} for r in store.list(statuses=("on_review",), district=district, limit=200)]
    return {"items": items}


def akim_yards(district: str | None = None, db_path=None) -> dict | None:
    """Для R08 (FUNCS «yards»): дворы, где есть соседи или дела, — только числа (соседей в Birge, дел), без людей."""
    service = default_service(db_path)
    if service is None:
        return None
    return {"yards": [{"id": y["id"], "label_ru": y.get("label_ru"), "label_kk": y.get("label_kk"),
                       "district": y.get("district"), "members": int(y.get("members") or 0),
                       "initiatives": int(y.get("initiatives") or 0), "demo": bool(y.get("demo"))}
                      for y in service.store.yards(district=district, limit=200)]}


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
