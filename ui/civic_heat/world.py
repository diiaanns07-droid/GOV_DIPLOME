"""Демо-мир раунда 15 (CONTRACT §11) для тепловой карты и «Хроники города» (R07).

Один источник (задача R07 №1). При CIVIC_DEMO=1 и CIVIC_DEMO_WORLD=1 у карты нет своих примеров: все жалобы —
из базы R09 (её засевает R09.seed_world из того же world_v1.json), поэтому числа на карте = «Обращения».
Без флага — как в FINAL-4: к жалобам R09 добавляется синтетический набор R07 (demo_seed.demo_records).

Что R07 берёт из мира сам — seed_world(db_path, records, now): только отметки для шкалы «Хроники»
(кризисы `incidents` и события `scenes`) с абсолютным временем от момента засева, в своей таблице
heat_replay_marks_v1 той же SQLite. Жалобы R07 не засевает и в чужие таблицы не пишет.
Главный источник отметок — кризисы R17 (ui.civic_agencies, см. marks.py); своя копия нужна, чтобы шкала
показывала «Буран», даже если модуля R17 в сборке нет. Время мира относительное (ago_days / ago_hours / in_days),
поэтому засев запоминает момент: повторный запуск сервера ничего не дублирует и не сдвигает даты.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .engine import ASTANA_TZ, iso, parse_time

ROOT = Path(__file__).resolve().parents[2]
WORLD_PATH = ROOT / "data" / "civic" / "astana" / "demo-world" / "world_v1.json"
DEFAULT_RUNTIME_DB = ROOT / ".runtime" / "civic.sqlite3"   # то же, что ui/web_server.resolve_db_path(None)
TABLE = "heat_replay_marks_v1"
MARK_KINDS = ("blizzard", "heat_outage", "water_outage", "flood", "other")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")

_lock = threading.Lock()
_db_path: str | None = None   # путь базы из seed_world / configure — где искать свои отметки


def world_mode() -> bool:
    """Демо-мир включён (R01 засевает модули из world_v1.json): CIVIC_DEMO=1 и CIVIC_DEMO_WORLD=1."""
    return os.environ.get("CIVIC_DEMO") == "1" and os.environ.get("CIVIC_DEMO_WORLD") == "1"


def examples_enabled() -> bool:
    """Есть ли у карты свои примеры R07. В демо-мире — нет: один источник, база R09."""
    return not world_mode()


def remember_db(db_path) -> None:
    """Запомнить базу сборки (seed_world или configure(db_path=…)): там лежат отметки шкалы."""
    global _db_path
    if db_path:
        with _lock:
            _db_path = str(db_path)


def db_path() -> str | None:
    """База для своих отметок: из seed_world / configure, иначе CIVIC_DB_PATH, иначе база сервера по умолчанию."""
    with _lock:
        if _db_path:
            return _db_path
    env = os.environ.get("CIVIC_DB_PATH") or os.environ.get("CIVIC_DB")
    if env:
        return env
    return str(DEFAULT_RUNTIME_DB) if DEFAULT_RUNTIME_DB.exists() else None


# ---------------------------------------------------------------- разбор мира (терпимо: SCHEMA R02 ещё уточняется)

def _relative(value: dict, now: datetime, prefixes: tuple[str, ...]) -> datetime | None:
    """Время записи мира: ISO (<p>_at) или относительно засева (<p>_ago_days / _ago_hours / _in_days / _in_hours)."""
    for p in prefixes:
        at = parse_time(value.get(p + "_at")) if p else None
        if at is not None:
            return at
        base = (p + "_") if p else ""
        ago_d, ago_h = value.get(base + "ago_days"), value.get(base + "ago_hours")
        in_d, in_h = value.get(base + "in_days"), value.get(base + "in_hours")
        if any(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (ago_d, ago_h, in_d, in_h)):
            delta = timedelta(days=float(ago_d or 0), hours=float(ago_h or 0)) - timedelta(days=float(in_d or 0), hours=float(in_h or 0))
            return now - delta
    return None


def _title(value: dict, lang: str) -> str:
    title = value.get("title_" + lang)
    if not title and isinstance(value.get("title"), dict):
        title = value["title"].get(lang)
    if not title and lang == "ru" and isinstance(value.get("title"), str):
        title = value["title"]
    return str(title or "").strip()[:80]


def _district(value: dict) -> str | None:
    zone = value.get("zone") if isinstance(value.get("zone"), dict) else {}
    d = zone.get("district") or value.get("district")
    return str(d) if isinstance(d, str) and re.match(r"^[a-z][a-z0-9_-]{1,30}$", d) else None


def mark_from_world(value: dict, now: datetime, *, source: str = "world") -> dict | None:
    """Кризис мира (§5.5) или событие сцены → отметка шкалы. Без названия или времени — None."""
    if not isinstance(value, dict):
        return None
    mid = str(value.get("id") or "")
    title_ru, title_kk = _title(value, "ru"), _title(value, "kk")
    started = _relative(value, now, ("started", "starts", "start", ""))
    if not _ID_RE.match(mid) or not title_ru or started is None:
        return None
    ended = _relative(value, now, ("ended", "closed", "ends", "end"))
    if ended is None:
        dur_d, dur_h = value.get("duration_days"), value.get("duration_hours")
        if isinstance(dur_d, (int, float)) or isinstance(dur_h, (int, float)):
            ended = started + timedelta(days=float(dur_d or 0), hours=float(dur_h or 0))
    if ended is not None and ended < started:
        ended = None
    kind = value.get("kind") if value.get("kind") in MARK_KINDS else "other"
    status = value.get("status") if value.get("status") in ("active", "closed") else ("closed" if ended and ended <= now else "active")
    return {
        "id": mid, "kind": kind, "title_ru": title_ru, "title_kk": title_kk or title_ru,
        "district": _district(value), "started_at": iso(started), "ended_at": iso(ended) if ended else None,
        "status": status, "source": source, "scene": None, "demo": value.get("demo") is not False,
    }


def _scene_refs(scenes) -> dict[str, str]:
    """id → номер сцены: в каком месте scenes упомянут кризис (scene9 / {"scene": 9, "incident": …} / {"9": {…}})."""
    out: dict[str, str] = {}

    def walk(node, scene):
        if isinstance(node, dict):
            sc = node.get("scene") or node.get("number") or scene
            for k, v in node.items():
                m = re.match(r"^(?:scene[_-]?)?(\d{1,2})$", str(k))
                walk(v, m.group(1) if m else sc)
        elif isinstance(node, list):
            for v in node:
                walk(v, scene)
        elif isinstance(node, str) and scene is not None:
            out.setdefault(node, str(scene))

    walk(scenes, None)
    return out


def world_marks(world, now: datetime) -> list[dict]:
    """Все отметки шкалы из мира: кризисы (incidents) и события сцен с названием и временем."""
    if isinstance(world, list):
        world = {"incidents": [x for x in world if isinstance(x, dict) and str(x.get("id", "")).startswith("inc-")]}
    if not isinstance(world, dict):
        return []
    refs = _scene_refs(world.get("scenes"))
    marks: dict[str, dict] = {}
    for inc in world.get("incidents") or []:
        m = mark_from_world(inc, now)
        if m:
            m["scene"] = refs.get(m["id"])
            marks[m["id"]] = m
    scenes = world.get("scenes")
    events = scenes if isinstance(scenes, list) else list(scenes.values()) if isinstance(scenes, dict) else []
    for ev in events:
        if isinstance(ev, dict) and ev.get("id") not in marks and (ev.get("title_ru") or ev.get("title")):
            m = mark_from_world(ev, now, source="scene")
            if m:
                m["scene"] = str(ev.get("scene") or ev.get("number") or refs.get(m["id"]) or "") or None
                marks[m["id"]] = m
    return sorted(marks.values(), key=lambda m: m["started_at"])


# ---------------------------------------------------------------- своя таблица отметок

SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id TEXT PRIMARY KEY,
    record_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    seeded_at TEXT NOT NULL
)
"""


def _connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute(SCHEMA_SQL)
    return db


def seed_world(db_path, records, now: datetime | None = None) -> dict:
    """Засев части мира R07 — отметок шкалы «Хроники» (CONTRACT §11). Идемпотентно по id отметки:
    повторный запуск оставляет прежнее время (даты мира не «уезжают» вслед за перезапуском сервера).
    records — весь мир (dict из world_v1.json) или список записей. -> {"inserted", "skipped"}."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ASTANA_TZ)
    marks = world_marks(records, now)
    remember_db(db_path)
    if not db_path:
        return {"inserted": 0, "skipped": len(marks)}
    inserted = skipped = 0
    with _lock:
        db = _connect(str(db_path))
        try:
            with db:
                for m in marks:
                    cur = db.execute(f"INSERT OR IGNORE INTO {TABLE} (id, record_json, started_at, seeded_at) VALUES (?,?,?,?)",
                                     (m["id"], json.dumps(m, ensure_ascii=False), m["started_at"], iso(now)))
                    if cur.rowcount:
                        inserted += 1
                    else:
                        skipped += 1
        finally:
            db.close()
    return {"inserted": inserted, "skipped": skipped}


def stored_marks(path: str | None = None) -> list[dict]:
    """Отметки, засеянные seed_world. Нет базы или таблицы — пустой список (шкала просто без отметок)."""
    path = path or db_path()
    if not path or (path != ":memory:" and not Path(path).exists()):
        return []
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return []
    try:
        rows = db.execute(f"SELECT record_json FROM {TABLE} ORDER BY started_at").fetchall()
    except sqlite3.Error:
        return []   # таблицы нет: мир не засевали
    finally:
        db.close()
    out = []
    for (raw,) in rows:
        try:
            m = json.loads(raw)
        except ValueError:
            continue
        if isinstance(m, dict) and m.get("id"):
            out.append(m)
    return out


def load_world(path: Path | None = None) -> dict | None:
    """world_v1.json R02 (для стенда R07 и тестов). Нет файла — None."""
    p = Path(path) if path else WORLD_PATH
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return None
