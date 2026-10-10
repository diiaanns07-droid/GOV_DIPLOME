"""Запись жалобы v2 (CONTRACT §5): проверка, нормализация, проекции.

Чистые функции без БД — их удобно тестировать и переиспользовать (миграция, API, R07/R08).
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

from .. import text as textutil
from . import categories

SCHEMA = "civic-complaint-v2"
ASTANA_TZ = timezone(timedelta(hours=5))
# Граница Астаны с запасом (та же, что в v1 ASTANA_BBOX): lon_min, lat_min, lon_max, lat_max.
ASTANA_BBOX = (70.9, 50.8, 72.0, 51.5)

STATUSES = ("new", "accepted", "in_progress", "fixed", "rejected")
# Разрешённые переходы статуса (сотрудник). Повторное открытие возможно: fixed -> in_progress,
# rejected -> accepted. Переход в тот же статус — ошибка (ничего не меняет, но и историю не засоряет).
TRANSITIONS = {
    "new": {"accepted", "in_progress", "fixed", "rejected"},
    "accepted": {"in_progress", "fixed", "rejected"},
    "in_progress": {"accepted", "fixed", "rejected"},
    "fixed": {"in_progress"},
    "rejected": {"accepted"},
}
# Шкала жителя (UX_SPEC §6.4): принято → в работе → исправлено. «new» = заявка дошла (шаг 1).
RESIDENT_STEPS = ("accepted", "in_progress", "fixed")
OPEN_STATUSES = ("new", "accepted", "in_progress")

TARGET_KINDS = ("object", "segment", "area")
TARGET_ID = {
    "object": re.compile(r"^osm-(node|way|relation)-[0-9]{1,15}$"),
    "segment": re.compile(r"^osm-w[0-9]{1,15}-[0-9]{1,6}$"),
    "area": re.compile(r"^(yard|cell)-[A-Za-z0-9_-]{1,60}$"),
}
COMPLAINT_ID = re.compile(r"^c-[A-Za-z0-9]{6,40}$")
DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{16,80}$")
REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
DISTRICT = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")
TEXT_MIN, TEXT_MAX = 3, 2000
LABEL_MAX = 160
CATEGORY_SOURCES = ("resident", "model", "staff")

# Ячейка ~150 м там, где нет двора (CONTRACT §4: cell-<ix>-<iy>). ОБЩАЯ сетка с R07 (ui/civic_heat/geo.py) и
# R12 (data/civic/astana/geo/cells.json, схема r12-cells-v2): иначе жалоба на «примерное место» попала бы в другую
# ячейку тепловой карты. Константы меняются только вместе с R07 и R12 (тест сверяет с cells.json, если он есть).
CELL_M = 150.0
CELL_ORIGIN = (71.0, 50.8)
CELL_LAT0 = 51.15
_LAT_STEP = CELL_M / 110_574.0
_LON_STEP = CELL_M / (111_320.0 * math.cos(math.radians(CELL_LAT0)))

# Слова, которых нет в казахском (для «mixed»): частые русские служебные слова.
_RU_MARKERS = frozenset("не на и в у с нет возле около уже очень уже где когда что это из за по до "
                        "двор улица дорога остановка снег яма свет тротуар мусор".split())


class RecordError(ValueError):
    """Ошибка проверки данных: field -> понятное объяснение для человека."""

    def __init__(self, message: str, fields: dict | None = None):
        super().__init__(message)
        self.fields = fields or {}


# ---------------------------------------------------------------- время
def iso(moment: datetime) -> str:
    """ISO-время по Астане (+05:00), секунды без долей — как в примере CONTRACT §5."""
    return moment.astimezone(ASTANA_TZ).replace(microsecond=0).isoformat()


def parse_iso(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=ASTANA_TZ)


# ---------------------------------------------------------------- язык
def detect_lang(text: str) -> str:
    """ru | kk | mixed. Казахские буквы + русские служебные слова = mixed (житель пишет вперемешку)."""
    words = textutil.normalize_for_match(text).split()
    kk_words = sum(1 for word in words if any(ch in textutil._KAZAKH for ch in word))
    if kk_words == 0:
        return "ru"
    ru_words = sum(1 for word in words if word in _RU_MARKERS)
    return "mixed" if ru_words else "kk"


# ---------------------------------------------------------------- место
def in_astana(lon: float, lat: float) -> bool:
    lon_min, lat_min, lon_max, lat_max = ASTANA_BBOX
    return lon_min <= lon <= lon_max and lat_min <= lat <= lat_max


def parse_point(value) -> list[float]:
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
        raise RecordError("Место указано неверно.", {"point": "нужно [долгота, широта]"})
    lon, lat = float(value[0]), float(value[1])
    if not (math.isfinite(lon) and math.isfinite(lat)) or not in_astana(lon, lat):
        raise RecordError("Место вне Астаны.", {"point": "точка должна быть в границах Астаны"})
    # 6 знаков ≈ 10 см: больше точности у телефона нет, а лишние знаки только раздувают запись.
    return [round(lon, 6), round(lat, 6)]


def cell_id(lon: float, lat: float) -> str:
    col = math.floor((lon - CELL_ORIGIN[0]) / _LON_STEP)
    row = math.floor((lat - CELL_ORIGIN[1]) / _LAT_STEP)
    return f"cell-{col}-{row}"


def cell_target(lon: float, lat: float) -> dict:
    """Запасная цель «примерное место»: ячейка ~150 м. Используется, когда R12 /targets
    недоступен или житель выбрал «Другое место». approximate=true -> интерфейс пишет
    «примерное место», а не уверенную линию (CONTRACT §8.4)."""
    return {"kind": "area", "id": cell_id(lon, lat), "approximate": True,
            "label_ru": "Примерное место", "label_kk": "Шамамен орны"}


def cell_polygon(target_id: str) -> list[list[float]] | None:
    """Контур ячейки cell-<col>-<row> (замкнутое кольцо) для подсветки области."""
    match = re.match(r"^cell-(-?[0-9]+)-(-?[0-9]+)$", target_id or "")
    if not match:
        return None
    col, row = int(match.group(1)), int(match.group(2))
    lon0 = CELL_ORIGIN[0] + col * _LON_STEP
    lat0 = CELL_ORIGIN[1] + row * _LAT_STEP
    lon1, lat1 = lon0 + _LON_STEP, lat0 + _LAT_STEP
    ring = [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]
    return [[round(x, 6), round(y, 6)] for x, y in ring]


def _label(value, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RecordError("Подпись места указана неверно.", {name: "строка"})
    value = textutil.clean_text(value)[:LABEL_MAX]
    return value or None


def parse_target(value, *, legacy_ok: bool = False) -> dict:
    """{kind, id, label_ru?, label_kk?, approximate?}. legacy_ok — только для миграции v1
    (там object_id — id редактора, а не OSM; запись помечается legacy=true)."""
    if not isinstance(value, dict):
        raise RecordError("Не выбрано место жалобы.", {"target": "выберите объект, участок улицы или двор"})
    kind, target_id = value.get("kind"), value.get("id")
    if kind not in TARGET_KINDS:
        raise RecordError("Не выбрано место жалобы.", {"target.kind": "object, segment или area"})
    if not isinstance(target_id, str) or not TARGET_ID[kind].match(target_id):
        if not (legacy_ok and isinstance(target_id, str) and 0 < len(target_id) <= 100):
            raise RecordError("Место жалобы указано неверно.", {"target.id": f"неверный id для {kind}"})
    result = {"kind": kind, "id": target_id}
    for name in ("label_ru", "label_kk"):
        label = _label(value.get(name), name)
        if label:
            result[name] = label
    if value.get("approximate") is True:
        result["approximate"] = True
    if legacy_ok and not TARGET_ID[kind].match(target_id):
        result["legacy"] = True
    return result


# ---------------------------------------------------------------- текст и модель
def parse_text(value) -> str:
    if not isinstance(value, str):
        raise RecordError("Опишите проблему.", {"text": "нужен текст"})
    text = textutil.clean_text(value)
    if len(text) < TEXT_MIN:
        raise RecordError("Опишите проблему чуть подробнее.", {"text": f"не короче {TEXT_MIN} символов"})
    if len(text) > TEXT_MAX:
        raise RecordError("Текст слишком длинный.", {"text": f"не длиннее {TEXT_MAX} символов"})
    return text


def parse_model(value) -> dict | None:
    """Подсказка /classify, как её получил клиент. Хранится для разбора качества модели;
    категорию определяет житель (category_source). Мусор не сохраняем — молча None."""
    if not isinstance(value, dict):
        return None
    label = value.get("label", value.get("category"))
    score = value.get("score")
    if not categories.is_category(label):
        return None
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 1:
        score = None
    version = value.get("version", value.get("model_version"))
    return {"label": label, "score": None if score is None else round(float(score), 4),
            "version": version[:80] if isinstance(version, str) else None,
            "needs_review": bool(value.get("needs_review", score is None))}


def due_at(created_at: str, category: str) -> str:
    created = parse_iso(created_at)
    return iso(created + timedelta(days=categories.response_days(category)))


def is_overdue(record: dict, now: datetime) -> bool:
    """Просрочено = новое (никто не ответил), а срок ответа прошёл."""
    due = parse_iso(record.get("due_at"))
    return record.get("status") == "new" and due is not None and now > due


def reporters(record: dict) -> int:
    """Сколько человек сообщили: автор + «Я тоже»."""
    return 1 + int(record.get("metoo") or 0)


# ---------------------------------------------------------------- проекции
PUBLIC_FIELDS = ("id", "created_at", "category", "point", "target", "district", "status",
                 "status_history", "metoo", "duplicate_of", "demo", "due_at", "lang")


# R15-S03: другим жителям — точка не точнее 3 знаков (≈ 110 м по широте, ≈ 70 м по долготе). Точка с 6 знаками
# (≈ 10 см) и временем до секунды показывает, из какого подъезда писал автор. Карте (R07) хватает цели.
PUBLIC_POINT_DIGITS = 3
# R15-S12: цель жалобы не дальше этого от точки жителя (объект R12 ищется в радиусе ~100 м, парк бывает большим).
TARGET_MAX_M = 300.0


def public_point(point):
    if not isinstance(point, (list, tuple)) or len(point) != 2:
        return None
    return [round(float(point[0]), PUBLIC_POINT_DIGITS), round(float(point[1]), PUBLIC_POINT_DIGITS)]


def _xy(lon: float, lat: float, lat0: float) -> tuple[float, float]:
    return (lon * 111_320.0 * math.cos(math.radians(lat0)), lat * 110_540.0)


def distance_to_geometry_m(point, geometry) -> float | None:
    """Расстояние (м) от точки до Point / LineString / Polygon (внутри многоугольника — 0). None — форма неизвестна."""
    if not isinstance(geometry, dict):
        return None
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    lat0 = float(point[1])
    px, py = _xy(float(point[0]), lat0, lat0)
    if kind == "Point":
        x, y = _xy(coords[0], coords[1], lat0)
        return math.hypot(x - px, y - py)
    lines = [coords] if kind == "LineString" else list(coords or []) if kind == "Polygon" else []
    if not lines:
        return None
    best, inside = float("inf"), False
    for ring in lines:
        pts = [_xy(c[0], c[1], lat0) for c in ring]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            dx, dy = bx - ax, by - ay
            t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
            best = min(best, math.hypot(ax + t * dx - px, ay + t * dy - py))
            if kind == "Polygon" and (ay > py) != (by > py) and px < ax + (py - ay) * dx / (dy or 1e-12):
                inside = not inside
    return 0.0 if inside else best


def checked_target(target: dict, point: list[float], lookup=None) -> dict:
    """R15-S04/S12: цель, которой можно верить. Подписи — только с карты (R12), не из запроса жителя.

    lookup(target) -> {"geometry", "label_ru", "label_kk"} | None — R12 engine.civic_geo.target_geometry
    (подключает R01). Цель неизвестна карте или дальше TARGET_MAX_M от точки -> «примерное место» у точки.
    Без lookup подписи жителя не сохраняются (интерфейс покажет общее слово по виду цели).
    """
    own_cell = cell_target(*point)
    if target["id"] == own_cell["id"]:
        return own_cell  # «Другое место»: ячейка R09 у точки жителя, подписи — свои
    clean = {"kind": target["kind"], "id": target["id"]}
    if target.get("approximate") is True:
        clean["approximate"] = True
    if lookup is None:
        return clean
    try:
        found = lookup(clean)
    except Exception:
        found = None
    distance = distance_to_geometry_m(point, (found or {}).get("geometry")) if found else None
    if distance is None or distance > TARGET_MAX_M:
        return own_cell
    for name in ("label_ru", "label_kk"):
        if isinstance(found.get(name), str) and found[name]:
            clean[name] = found[name][:LABEL_MAX]
    if found.get("approximate") is True:
        clean["approximate"] = True
    return clean


def public_view(record: dict) -> dict:
    """Что видят другие жители и карта: без текста, без модели, без устройства.
    Правило R09: чужие тексты (могут содержать личные данные) жителям не показываем —
    только «сообщили N человек»."""
    view = {key: record.get(key) for key in PUBLIC_FIELDS}
    view["point"] = public_point(record.get("point"))
    view["status_history"] = [{"at": h["at"], "status": h["status"]} for h in record.get("status_history", [])]
    view["reporters"] = reporters(record)
    return view


def author_view(record: dict) -> dict:
    """Автору (его устройство) — его собственный текст и шкала статуса, без служебных заметок."""
    view = public_view(record)
    view["point"] = record.get("point")  # своё место автор видит точно
    view["text"] = record.get("text")
    view["category_source"] = record.get("category_source")
    view["code"] = record.get("code")
    view["steps"] = resident_steps(record)
    return view


def staff_view(record: dict) -> dict:
    """Акимату — всё, кроме хэшей устройства."""
    return {key: value for key, value in record.items() if key not in ("device_hash", "request_id")}


def resident_steps(record: dict) -> list[dict]:
    """Шкала «принято → в работе → исправлено»: done/current/todo; при отказе — rejected."""
    status = record.get("status")
    reached = {h["status"] for h in record.get("status_history", [])}
    if status == "rejected":
        return [{"status": "accepted", "state": "done"}, {"status": "rejected", "state": "current"}]
    order = {"new": 0, "accepted": 0, "in_progress": 1, "fixed": 2}
    current = order.get(status, 0)
    steps = []
    for index, step in enumerate(RESIDENT_STEPS):
        if index < current or (index == current and status == "fixed"):
            state = "done"
        elif index == current:
            state = "current"
        else:
            state = "todo"
        steps.append({"status": step, "state": state, "reached": step in reached or index <= current})
    return steps
