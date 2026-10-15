"""Засев жалоб демо-мира в хранилище R09 (R02, раунд 15) — готовая основа для seed_world R09 и запасной путь R01.

    from ml.datasets.demo_world_seed import seed_r09
    report = seed_r09(store, world, now)     # store — ui.civic_feedback.v2.store.ComplaintStore

или одной функцией с путём к базе (вид CONTRACT §11):

    from ml.datasets.demo_world_seed import seed_world
    seed_world(db_path, world, now=None)     # -> {"inserted", "skipped", "reset"}

Правила (как у R09 seed_demo, R10 B-048/B-049):
  - только записи мира с demo: true; настоящие жалобы жителей не трогаются никогда;
  - запись с тем же id возвращается в исходное состояние со временем от нового now (reset=True): демо всегда «свежее»,
    а репетиция («Взять в работу», «Я тоже», проверка) не съедает показ;
  - «Я тоже» — синтетические устройства demo_device(id, n), время — metoo_times мира;
  - срок ответа (due_at) и номер (B-0001) ставит сам R09: record.due_at и _next_code.
"""

from __future__ import annotations

from datetime import datetime

from ml.datasets import demo_world_io as wio


def complaint_rows(world: dict, now: datetime | None = None) -> list[tuple[dict, list[tuple[str, str]]]]:
    """[(запись v2 с абсолютным временем и due_at, [(device_hash, at)])] — по возрастанию времени подачи."""
    from ui.civic_feedback.v2 import record as rec
    now = wio.astana_now(now)
    complaints = wio.materialize(world["complaints"], now)
    rows = []
    for c in sorted(complaints, key=lambda x: (x["created_at"], x["id"])):
        if c.get("demo") is not True:
            continue
        c = dict(c)
        c["due_at"] = rec.due_at(c["created_at"], c["category"])
        devices = [(wio.demo_device(c["id"], n), at) for n, at in enumerate(c.get("metoo_times") or [], start=1)]
        rows.append((c, devices))
    return rows


def seed_r09(store, world: dict, now: datetime | None = None, *, reset: bool = True) -> dict:
    """Все жалобы мира -> хранилище R09. Повтор с reset=True возвращает демо-записи к исходному виду."""
    inserted = skipped = was_reset = 0
    for record, devices in complaint_rows(world, now):
        if reset:
            result = store.reset_demo_record(record, metoo_devices=devices)
            inserted += result == "added"
            was_reset += result == "reset"
            skipped += result == "skipped"
        elif store.import_record(record, metoo_devices=devices):
            inserted += 1
        else:
            skipped += 1
    return {"inserted": inserted, "skipped": skipped, "reset": was_reset}


def seed_world(db_path, records: dict | None = None, now: datetime | None = None, *, reset: bool = True) -> dict:
    """Вид CONTRACT §11 для части R09: records — весь мир (None — world_v1.json)."""
    from ui.civic_feedback.v2.store import ComplaintStore
    world = records if records is not None else wio.load_world()
    store = ComplaintStore(db_path)
    try:
        return seed_r09(store, world, now, reset=reset)
    finally:
        store.close()
