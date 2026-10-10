"""Демо-жалобы R09 для показа (сборка с CIVIC_DEMO=1) — R10 B-030.

На чистой базе в хранилище R09 нет ни одной жалобы, поэтому на шаге 2 демо «Об этом уже сообщили N человек →
Я тоже» не появлялся (у R07 свой синтетический набор, но он живёт только в тепловой карте). Здесь — несколько
СИНТЕТИЧЕСКИХ обращений (demo: true, в интерфейсе метка «Пример») у реальной остановки OSM из сценария демо.

    from ui.civic_feedback.v2.demo_seed import seed_demo
    seed_demo(store)                                   # идемпотентно: повторный запуск ничего не дублирует
    python -m ui.civic_feedback.v2 seed-demo --db <civic.sqlite3>

Тексты, люди и время придуманы; цель — настоящая остановка «Хан Шатыр» (OSM node 4109037549, та же, что в
демо-наборе R07 ui/civic_heat/fixtures/targets_demo.json). Сходство текста демо «Аялдамада жарық жоқ, вечером на
остановке темно» с первой записью — 0,70 по замеру R10 на R04 /similar, поэтому «Я тоже» находит её.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from . import record as rec

# Остановка «Хан Шатыр» (Нура): та же цель и подпись, что у R07 и R12 (OSM, ODbL).
KHAN_SHATYR = {"kind": "object", "id": "osm-node-4109037549",
               "label_ru": "Остановка «Хан Шатыр»", "label_kk": "«Хан Шатыр» аялдамасы"}
KHAN_SHATYR_POINT = [71.406553, 51.131155]

# key — стабильная часть id (повторный засев узнаёт запись); people — сколько жителей «сообщили» (автор + «Я тоже»).
DEMO_COMPLAINTS = (
    {"key": "khan-shatyr-lighting", "category": "lighting", "people": 3, "hours_ago": 30,
     "text": "Вечером на остановке нет света, темно", "point": [71.406601, 51.131120]},
    {"key": "khan-shatyr-pavilion", "category": "transport", "people": 2, "hours_ago": 52,
     "text": "Аялдаманың павильоны сынған, орындық жоқ", "point": [71.406520, 51.131190]},
)


def _demo_id(key: str) -> str:
    return "c-demo" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _demo_device(key: str, n: int) -> str:
    # Синтетические «устройства» сообщивших: хэш, как у настоящих, но из фиксированной строки (не чьё-то устройство).
    return hashlib.sha256(f"r09-demo-device:{key}:{n}".encode("utf-8")).hexdigest()


def demo_records(now) -> list[tuple[dict, list[tuple[str, str]]]]:
    """[(запись v2, [(device_hash, at) для «Я тоже»])] — детерминированно при одном now."""
    out = []
    for item in DEMO_COMPLAINTS:
        created = now - timedelta(hours=item["hours_ago"])
        created_at = rec.iso(created)
        metoo = [(_demo_device(item["key"], n), rec.iso(created + timedelta(hours=2 * n)))
                 for n in range(1, item["people"])]
        record = {
            "id": _demo_id(item["key"]), "code": None, "created_at": created_at,
            "text": item["text"], "lang": rec.detect_lang(item["text"]),
            "category": item["category"], "category_source": "resident", "model": None,
            "point": list(item["point"]), "target": dict(KHAN_SHATYR), "district": "nura",
            "status": "new", "status_history": [{"at": created_at, "status": "new"}],
            "metoo": len(metoo), "duplicate_of": None, "demo": True,
            "due_at": rec.due_at(created_at, item["category"]), "schema": rec.SCHEMA,
        }
        out.append((record, metoo))
    return out


def seed_demo(store, now=None) -> dict:
    """Засеять демо-жалобы в хранилище R09. -> {"added": n, "kept": m}. Повторный вызов ничего не дублирует."""
    now = now or store._now()
    added = kept = 0
    for record, metoo in demo_records(now):
        if store.import_record(record, metoo_devices=metoo):
            added += 1
        else:
            kept += 1
    return {"added": added, "kept": kept, "target": KHAN_SHATYR["id"]}
