"""Демо-мир Астаны (R02, раунд 15): чтение файла мира и перевод относительных времён в абсолютные.

Модули ролей зовут это из своего seed_world (CONTRACT §11) — только стандартная библиотека, без сети:

    from ml.datasets.demo_world_io import load_world, materialize, demo_device
    world = load_world()                          # data/civic/astana/demo-world/world_v1.json
    complaints = materialize(world, now)["complaints"]

Время в файле мира записано относительно момента засева (SCHEMA.md §1):
    {"ago_hours": h} {"in_hours": h} {"ago_days": d} {"in_days": d}   -> мгновение ISO 8601 по Астане (+05:00)
    {"day": n}                                                        -> дата YYYY-MM-DD (сегодня по Астане + n)
    {"season": {"month": m, "day": d}}                               -> дата в следующем строительном сезоне
    {"next_weekday": {"weekday": 5, "hour": 10, "minute": 0}}         -> ближайшая суббота 10:00 (не раньше чем через 12 ч)
    {"day_at": {"day": -12, "hour": 18, "minute": 30}}                -> мгновение: сегодня − 12 дней в 18:30 по Астане
Строки и числа не трогаются, поэтому materialize можно звать повторно.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ASTANA_TZ = timezone(timedelta(hours=5))
ROOT = Path(__file__).resolve().parents[2]
WORLD_DIR = ROOT / "data" / "civic" / "astana" / "demo-world"
WORLD_PATH = WORLD_DIR / "world_v1.json"
SAMPLE_PATH = WORLD_DIR / "world_v1.sample.json"
SCHEMA_ID = "birge-demo-world-v1"

_INSTANT_KEYS = {"ago_hours": -3600.0, "in_hours": 3600.0, "ago_days": -86400.0, "in_days": 86400.0}
# Сезон работ: с января по март «следующий сезон» — этот год, с апреля — следующий (асфальт зимой не кладут).
SEASON_SAME_YEAR_UNTIL_MONTH = 3
# «В субботу в 10:00» не должно оказаться «через час»: ближайший такой момент не раньше чем через 12 часов.
NEXT_WEEKDAY_MIN_HOURS = 12


class WorldError(ValueError):
    """Файл мира не тот или повреждён: что не так — понятной строкой."""


def world_path() -> Path:
    """Путь к миру: переменная CIVIC_DEMO_WORLD_PATH (для тестов и стенда) или файл в репозитории."""
    value = os.environ.get("CIVIC_DEMO_WORLD_PATH")
    return Path(value) if value else WORLD_PATH


def load_world(path: str | Path | None = None) -> dict:
    """Прочитать мир (относительные времена). Неверный файл -> WorldError, а не молчаливо пустой мир."""
    path = Path(path) if path else world_path()
    try:
        world = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorldError(f"Нет файла демо-мира: {path}") from exc
    except ValueError as exc:
        raise WorldError(f"Файл демо-мира не читается как JSON: {path}: {exc}") from exc
    if not isinstance(world, dict) or world.get("schema") != SCHEMA_ID:
        raise WorldError(f"Это не демо-мир {SCHEMA_ID}: {path}")
    return world


def is_reltime(value) -> bool:
    """Объект относительного времени: ровно один ключ из SCHEMA §1."""
    if not isinstance(value, dict) or len(value) != 1:
        return False
    (key, inner), = value.items()
    if key in _INSTANT_KEYS:
        return isinstance(inner, (int, float)) and not isinstance(inner, bool)
    if key == "day":
        return isinstance(inner, int) and not isinstance(inner, bool)  # дата — целое число дней
    if key == "season":
        return (isinstance(inner, dict) and set(inner) == {"month", "day"}
                and all(isinstance(inner[k], int) and not isinstance(inner[k], bool) for k in inner))
    if key == "next_weekday":
        return (isinstance(inner, dict) and set(inner) == {"weekday", "hour", "minute"}
                and all(isinstance(inner[k], int) and not isinstance(inner[k], bool) for k in inner)
                and 0 <= inner["weekday"] <= 6 and 0 <= inner["hour"] <= 23 and 0 <= inner["minute"] <= 59)
    if key == "day_at":
        return (isinstance(inner, dict) and set(inner) == {"day", "hour", "minute"}
                and all(isinstance(inner[k], int) and not isinstance(inner[k], bool) for k in inner)
                and 0 <= inner["hour"] <= 23 and 0 <= inner["minute"] <= 59)
    return False


def astana_now(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ASTANA_TZ)  # наивное время считаем астанинским
    return now.astimezone(ASTANA_TZ)


def iso(moment: datetime) -> str:
    """Как у R09 record.iso: по Астане, секунды без долей."""
    return moment.astimezone(ASTANA_TZ).replace(microsecond=0).isoformat()


def season_date(month: int, day: int, now: datetime | None = None) -> date:
    """Дата следующего строительного сезона (SCHEMA §1, сцена 8: асфальт в мае, сети в июле)."""
    today = astana_now(now).date()
    year = today.year if today.month <= SEASON_SAME_YEAR_UNTIL_MONTH else today.year + 1
    return date(year, month, day)


def next_weekday(weekday: int, hour: int, minute: int, now: datetime | None = None) -> datetime:
    """Ближайший день недели (пн = 0 … вс = 6) в hh:mm по Астане, не раньше чем через NEXT_WEEKDAY_MIN_HOURS."""
    now = astana_now(now)
    day = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    day += timedelta(days=(weekday - now.weekday()) % 7)
    while day - now < timedelta(hours=NEXT_WEEKDAY_MIN_HOURS):
        day += timedelta(days=7)
    return day


def resolve(value, now: datetime | None = None):
    """Один объект относительного времени -> ISO-строка (мгновение) или YYYY-MM-DD (дата). Иначе — как есть."""
    if not is_reltime(value):
        return value
    now = astana_now(now)
    (key, inner), = value.items()
    if key in _INSTANT_KEYS:
        return iso(now + timedelta(seconds=float(inner) * _INSTANT_KEYS[key]))
    if key == "day":
        return (now.date() + timedelta(days=int(inner))).isoformat()
    if key == "next_weekday":
        return iso(next_weekday(inner["weekday"], inner["hour"], inner["minute"], now))
    if key == "day_at":
        day = now.date() + timedelta(days=inner["day"])
        return iso(datetime(day.year, day.month, day.day, inner["hour"], inner["minute"], tzinfo=ASTANA_TZ))
    return season_date(inner["month"], inner["day"], now).isoformat()


def _walk(value, now: datetime):
    if is_reltime(value):
        return resolve(value, now)
    if isinstance(value, dict):
        return {key: _walk(item, now) for key, item in value.items()}
    if isinstance(value, list):
        return [_walk(item, now) for item in value]
    return value


def materialize(world_or_records, now: datetime | None = None):
    """Копия мира (или части/записи) с абсолютными временами от now. Исходный объект не меняется."""
    now = astana_now(now)
    return _walk(copy.deepcopy(world_or_records), now)


def demo_device(record_id: str, n: int) -> str:
    """Синтетическое «устройство» n-го «Я тоже» у записи мира (sha256 hex) — одинаково при каждом засеве."""
    return hashlib.sha256(f"demo-world-v1:{record_id}:{n}".encode("utf-8")).hexdigest()


def part(world: dict, key: str, now: datetime | None = None) -> list:
    """Одна часть мира с абсолютными временами: part(world, "ideas", now)."""
    if key not in world:
        raise WorldError(f"В мире нет части {key!r}")
    return materialize(world[key], now)
