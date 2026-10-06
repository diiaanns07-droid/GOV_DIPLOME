"""Проверка содержимого объекта civic-v1 (CONTRACT.txt раунда 11, раздел 1).

Сервер не доверяет телу запроса: служебные поля (id, revision, publication,
updated_at, actor/role...) игнорируются, неизвестные поля — ошибка 422.
Неизвестное остаётся null/unknown: ни нулевой стоимости, ни сегодняшней даты.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import math
import re
import unicodedata
from urllib.parse import urlsplit


SCHEMA_VERSION = "civic-v1"
CITY = "astana"
KINDS = ("construction", "roadworks", "landscaping", "event")
STATUSES = ("planned", "in_progress", "completed", "cancelled", "unknown")
PUBLICATIONS = ("draft", "published", "archived")
PRECISIONS = ("source", "approximate", "unknown")
EVIDENCE_TYPES = ("observed", "derived", "hypothesis", "synthetic")
BUDGET_BASES = ("planned", "contract", "spent", "unknown")
ACCESS_STATUSES = ("fetched", "not_fetched", "unavailable")
SCHEDULE_KEYS = ("planned_start", "original_planned_end", "current_planned_end", "actual_end")
BUDGET_KEYS = ("amount_kzt", "basis", "source_id")
RESPONSIBLE_KEYS = ("organization", "public_contact")
SOURCE_REF_KEYS = ("id", "url", "publisher", "published_on", "retrieved_at",
                   "access_status", "license", "fields")

# Содержимое, которое задаёт редактор/импорт. Остальные поля civic-v1 назначает сервер.
CONTENT_FIELDS = ("kind", "title", "description", "status", "geometry", "geometry_precision",
                  "schedule", "budget", "responsible", "evidence_type", "source_refs",
                  "evidence_notes")
STAFF_ONLY_FIELDS = ("internal_notes",)
# Эти ключи клиент может прислать (например, вернув карточку целиком), но сервер
# их не принимает: значения назначает только он.
SERVER_FIELDS = frozenset({
    "schema_version", "id", "city", "publication", "updated_at", "revision",
    "created_at", "created_by", "updated_by", "published_at", "first_published_at",
    "published_revision", "actor", "actor_id", "role", "user", "user_id", "author",
    "public_actor_label", "staff", "history",
})
NESTED_FIELDS = {"schedule": SCHEDULE_KEYS, "budget": BUDGET_KEYS, "responsible": RESPONSIBLE_KEYS}

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FIELD_PATH_RE = re.compile(r"^[a-z_]{1,40}(\.[a-z_]{1,40}){0,2}$")
HTML_RE = re.compile(r"<\s*[A-Za-z/!?]")
BIDI_CONTROLS = frozenset("‪‫‬‭‮⁦⁧⁨⁩")

MAX_TEXT = {"title": 200, "description": 5000, "evidence_notes": 2000, "internal_notes": 5000,
            "organization": 300, "public_contact": 200, "publisher": 300, "license": 200,
            "reason": 1000}
MAX_URL = 2000
MAX_SOURCE_REFS = 30
MAX_FIELDS_PER_REF = 40
MAX_POSITIONS = 5000
MAX_RINGS = 50
MAX_AMOUNT_KZT = 10 ** 13
MIN_YEAR, MAX_YEAR = 1990, 2100
# Широкая рамка вокруг Астаны (~±50 км): ловит перепутанные долготу/широту и чужой город.
ASTANA_BBOX = (70.8, 50.75, 72.1, 51.6)  # min_lon, min_lat, max_lon, max_lat


class ValidationError(ValueError):
    """Ошибка данных клиента: HTTP 422 с картой полей."""

    def __init__(self, fields: dict[str, str], message: str = "Проверьте выделенные поля."):
        super().__init__(message)
        self.fields = dict(fields)
        self.message = message


class _Errors:
    def __init__(self):
        self.fields: dict[str, str] = {}

    def add(self, path: str, message: str) -> None:
        self.fields.setdefault(path, message)

    def raise_if_any(self) -> None:
        if self.fields:
            raise ValidationError(self.fields)


# --- примитивы ---------------------------------------------------------------

def is_valid_id(value) -> bool:
    return isinstance(value, str) and bool(ID_RE.match(value))


def clean_text(value, path, errors, *, max_len, required=False, multiline=False, nullable=False):
    """Простой текст: без HTML, управляющих и bidi-символов, с пределом длины."""
    if value is None:
        if nullable:
            return None
        if required:
            errors.add(path, "Обязательное поле.")
            return None
        return ""
    if not isinstance(value, str):
        errors.add(path, "Ожидается строка.")
        return None
    text = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n")).strip()
    for char in text:
        category = unicodedata.category(char)
        if char in BIDI_CONTROLS or category == "Cs" or (
                category == "Cc" and not (multiline and char in "\n\t")):
            errors.add(path, "Текст содержит управляющие символы.")
            return None
    if HTML_RE.search(text):
        errors.add(path, "HTML не допускается: только простой текст.")
        return None
    if len(text) > max_len:
        errors.add(path, f"Слишком длинный текст: не более {max_len} символов.")
        return None
    if not text:
        if required:
            errors.add(path, "Обязательное поле.")
            return None
        return None if nullable else ""
    return text


def clean_enum(value, path, errors, allowed, *, default=None):
    if value is None and default is not None:
        return default
    if not isinstance(value, str) or value not in allowed:
        errors.add(path, "Допустимые значения: " + ", ".join(allowed) + ".")
        return None
    return value


def parse_date(value) -> date | None:
    """YYYY-MM-DD реальной календарной даты в разумном диапазоне, иначе None."""
    if not isinstance(value, str) or not DATE_RE.match(value):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    if not MIN_YEAR <= parsed.year <= MAX_YEAR:
        return None
    return parsed


def clean_date(value, path, errors):
    if value is None:
        return None
    if parse_date(value) is None:
        errors.add(path, f"Дата в формате YYYY-MM-DD ({MIN_YEAR}–{MAX_YEAR}) или null.")
        return None
    return value


def clean_timestamp(value, path, errors):
    """ISO 8601 дата или дата-время (со смещением либо без), либо null."""
    if value is None:
        return None
    if isinstance(value, str) and len(value) <= 40:
        if parse_date(value) is not None:
            return value
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if MIN_YEAR <= parsed.year <= MAX_YEAR:
                return value
        except ValueError:
            pass
    errors.add(path, "Ожидается дата/время ISO 8601 или null.")
    return None


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def clean_amount(value, path, errors):
    if value is None:
        return None
    if not _is_number(value) or not math.isfinite(value):
        errors.add(path, "Сумма — конечное неотрицательное число или null (неизвестно).")
        return None
    if value < 0 or value > MAX_AMOUNT_KZT:
        errors.add(path, "Сумма должна быть от 0 до 10^13 тенге.")
        return None
    return value


def clean_url(value, path, errors):
    if not isinstance(value, str) or not value or len(value) > MAX_URL:
        errors.add(path, f"Ссылка http(s) не длиннее {MAX_URL} символов.")
        return None
    if any(char.isspace() or unicodedata.category(char) == "Cc" for char in value):
        errors.add(path, "Ссылка не должна содержать пробелы и управляющие символы.")
        return None
    try:
        parts = urlsplit(value)
        port_ok = parts.port is None or 0 < parts.port < 65536
    except ValueError:
        parts, port_ok = None, False
    if (not parts or parts.scheme.lower() not in ("http", "https") or not parts.hostname
            or parts.username is not None or parts.password is not None or not port_ok):
        errors.add(path, "Допустимы только ссылки http/https без логина и пароля.")
        return None
    return value


# --- геометрия ----------------------------------------------------------------

def _position(value, path, errors, counter):
    counter[0] += 1
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(_is_number(v) and math.isfinite(v) for v in value)):
        errors.add(path, "Координата — [долгота, широта] из двух конечных чисел.")
        return None
    lon, lat = value
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        errors.add(path, "Координаты вне диапазона WGS84.")
        return None
    min_lon, min_lat, max_lon, max_lat = ASTANA_BBOX
    if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
        errors.add(path, "Точка вне Астаны: проверьте порядок [долгота, широта].")
        return None
    return [lon, lat]


def clean_geometry(value, path, errors):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"type", "coordinates"}:
        errors.add(path, "GeoJSON-геометрия {type, coordinates} или null.")
        return None
    kind, coords = value["type"], value["coordinates"]
    counter = [0]
    before = len(errors.fields)
    if kind == "Point":
        result = _position(coords, path + ".coordinates", errors, counter)
    elif kind == "LineString":
        if not isinstance(coords, list) or not 2 <= len(coords) <= MAX_POSITIONS:
            errors.add(path, "LineString — не менее двух точек.")
            return None
        result = [_position(p, f"{path}.coordinates[{i}]", errors, counter) for i, p in enumerate(coords)]
    elif kind == "Polygon":
        if not isinstance(coords, list) or not 1 <= len(coords) <= MAX_RINGS:
            errors.add(path, "Polygon — список колец.")
            return None
        result = []
        for r, ring in enumerate(coords):
            if not isinstance(ring, list) or not 4 <= len(ring) <= MAX_POSITIONS:
                errors.add(f"{path}.coordinates[{r}]", "Кольцо полигона — не менее четырёх точек.")
                return None
            points = [_position(p, f"{path}.coordinates[{r}][{i}]", errors, counter)
                      for i, p in enumerate(ring)]
            if len(errors.fields) == before and points[0] != points[-1]:
                errors.add(f"{path}.coordinates[{r}]", "Кольцо полигона должно быть замкнуто.")
            result.append(points)
            if counter[0] > MAX_POSITIONS:
                break
    else:
        errors.add(path + ".type", "Допустимы Point, LineString, Polygon или null.")
        return None
    if counter[0] > MAX_POSITIONS:
        errors.add(path, f"Слишком много точек: не более {MAX_POSITIONS}.")
        return None
    if len(errors.fields) != before:
        return None
    return {"type": kind, "coordinates": result}


# --- источники ----------------------------------------------------------------

def clean_source_refs(value, path, errors):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_SOURCE_REFS:
        errors.add(path, f"Список источников (не более {MAX_SOURCE_REFS}).")
        return []
    result, seen = [], set()
    for index, ref in enumerate(value):
        here = f"{path}[{index}]"
        if not isinstance(ref, dict):
            errors.add(here, "Источник — объект.")
            continue
        unknown = set(ref) - set(SOURCE_REF_KEYS)
        if unknown:
            errors.add(here, "Неизвестные поля источника: " + ", ".join(sorted(unknown)) + ".")
            continue
        ref_id = ref.get("id")
        if not is_valid_id(ref_id):
            errors.add(here + ".id", "ID источника: латиница/цифры/._- до 64 символов.")
        elif ref_id in seen:
            errors.add(here + ".id", "ID источников не должны повторяться.")
        seen.add(ref_id)
        fields = ref.get("fields", [])
        clean_fields = []
        if not isinstance(fields, list) or len(fields) > MAX_FIELDS_PER_REF:
            errors.add(here + ".fields", "Список путей полей, поддержанных источником.")
        else:
            for f_index, field in enumerate(fields):
                if (not isinstance(field, str) or not FIELD_PATH_RE.match(field)
                        or field.split(".")[0] not in CONTENT_FIELDS):
                    errors.add(f"{here}.fields[{f_index}]", "Путь поля civic-v1, например schedule.current_planned_end.")
                else:
                    clean_fields.append(field)
        access = clean_enum(ref.get("access_status"), here + ".access_status", errors, ACCESS_STATUSES)
        retrieved = clean_timestamp(ref.get("retrieved_at"), here + ".retrieved_at", errors)
        if access == "fetched" and retrieved is None and here + ".retrieved_at" not in errors.fields:
            errors.add(here + ".retrieved_at", "Для fetched укажите дату получения.")
        result.append({
            "id": ref_id,
            "url": clean_url(ref.get("url"), here + ".url", errors),
            "publisher": clean_text(ref.get("publisher"), here + ".publisher", errors,
                                    max_len=MAX_TEXT["publisher"], nullable=True),
            "published_on": clean_date(ref.get("published_on"), here + ".published_on", errors),
            "retrieved_at": retrieved,
            "access_status": access,
            "license": clean_text(ref.get("license"), here + ".license", errors,
                                  max_len=MAX_TEXT["license"], nullable=True),
            "fields": clean_fields,
        })
    return result


# --- объект целиком -------------------------------------------------------------

def empty_content() -> dict:
    return {
        "kind": None, "title": None, "description": "", "status": "unknown",
        "geometry": None, "geometry_precision": "unknown",
        "schedule": {key: None for key in SCHEDULE_KEYS},
        "budget": {"amount_kzt": None, "basis": "unknown", "source_id": None},
        "responsible": {"organization": None, "public_contact": None},
        "evidence_type": None, "source_refs": [], "evidence_notes": "",
    }


def split_payload(payload, *, allow_internal=True):
    """Отделяет содержимое от служебных полей. Возвращает (content, internal_notes|..., ignored)."""
    if not isinstance(payload, dict):
        raise ValidationError({"body": "Ожидается JSON-объект."})
    ignored = sorted(key for key in payload if key in SERVER_FIELDS)
    allowed = set(CONTENT_FIELDS) | (set(STAFF_ONLY_FIELDS) if allow_internal else set())
    unknown = sorted(key for key in payload if key not in SERVER_FIELDS and key not in allowed)
    if unknown:
        raise ValidationError({key: "Неизвестное поле civic-v1." for key in unknown},
                              "Запрос содержит неизвестные поля.")
    content = {key: payload[key] for key in CONTENT_FIELDS if key in payload}
    internal = payload.get("internal_notes", ...) if allow_internal else ...
    return content, internal, ignored


def merge_content(current: dict, changes: dict) -> dict:
    """Частичное обновление: schedule/budget/responsible сливаются по ключам."""
    merged = deepcopy(current)
    errors = _Errors()
    for key, value in changes.items():
        if key in NESTED_FIELDS and isinstance(value, dict):
            unknown = set(value) - set(NESTED_FIELDS[key])
            for name in sorted(unknown):
                errors.add(f"{key}.{name}", "Неизвестное поле civic-v1.")
            merged[key] = {**(merged.get(key) or {}), **value}
        else:
            merged[key] = deepcopy(value)
    errors.raise_if_any()
    return merged


def validate_content(raw: dict, *, today: date) -> dict:
    """Полная проверка содержимого; возвращает нормализованную копию либо ValidationError."""
    errors = _Errors()
    data = {**empty_content(), **raw}
    out = {}
    out["kind"] = clean_enum(data["kind"], "kind", errors, KINDS)
    out["title"] = clean_text(data["title"], "title", errors, max_len=MAX_TEXT["title"], required=True)
    out["description"] = clean_text(data["description"], "description", errors,
                                    max_len=MAX_TEXT["description"], multiline=True)
    out["status"] = clean_enum(data["status"], "status", errors, STATUSES, default="unknown")
    out["geometry"] = clean_geometry(data["geometry"], "geometry", errors)
    precision = clean_enum(data["geometry_precision"], "geometry_precision", errors, PRECISIONS,
                           default="unknown")
    # Без геометрии точность места не может быть «source»/«approximate».
    out["geometry_precision"] = "unknown" if data["geometry"] is None else precision

    for key, names in NESTED_FIELDS.items():
        value = data[key]
        if value is None:
            value = empty_content()[key]
        if not isinstance(value, dict):
            errors.add(key, "Ожидается объект.")
            value = empty_content()[key]
        unknown = set(value) - set(names)
        for name in sorted(unknown):
            errors.add(f"{key}.{name}", "Неизвестное поле civic-v1.")
        data[key] = {**empty_content()[key], **value}

    schedule = {key: clean_date(data["schedule"][key], f"schedule.{key}", errors) for key in SCHEDULE_KEYS}
    out["schedule"] = schedule
    out["evidence_type"] = clean_enum(data["evidence_type"], "evidence_type", errors, EVIDENCE_TYPES)
    out["source_refs"] = clean_source_refs(data["source_refs"], "source_refs", errors)
    budget = data["budget"]
    out["budget"] = {
        "amount_kzt": clean_amount(budget["amount_kzt"], "budget.amount_kzt", errors),
        "basis": clean_enum(budget["basis"], "budget.basis", errors, BUDGET_BASES, default="unknown"),
        "source_id": None,
    }
    if budget["source_id"] is not None:
        ref_ids = {ref["id"] for ref in out["source_refs"]}
        if not is_valid_id(budget["source_id"]) or budget["source_id"] not in ref_ids:
            errors.add("budget.source_id", "source_id должен ссылаться на id из source_refs.")
        else:
            out["budget"]["source_id"] = budget["source_id"]
    responsible = data["responsible"]
    out["responsible"] = {
        "organization": clean_text(responsible["organization"], "responsible.organization", errors,
                                   max_len=MAX_TEXT["organization"], nullable=True),
        "public_contact": clean_text(responsible["public_contact"], "responsible.public_contact", errors,
                                     max_len=MAX_TEXT["public_contact"], nullable=True),
    }
    out["evidence_notes"] = clean_text(data["evidence_notes"], "evidence_notes", errors,
                                       max_len=MAX_TEXT["evidence_notes"], multiline=True)
    errors.raise_if_any()

    # Согласованность после проверки типов.
    dates = {key: parse_date(value) for key, value in schedule.items()}
    start = dates["planned_start"]
    for key in ("original_planned_end", "current_planned_end", "actual_end"):
        if start and dates[key] and dates[key] < start:
            errors.add(f"schedule.{key}", "Дата окончания раньше planned_start.")
    if dates["actual_end"]:
        if dates["actual_end"] > today:
            errors.add("schedule.actual_end", "Фактическое окончание не может быть в будущем.")
        if out["status"] != "completed":
            errors.add("schedule.actual_end", "actual_end указывается только для status=completed.")
    amount = out["budget"]["amount_kzt"]
    if amount is not None:
        if out["budget"]["source_id"] is None:
            errors.add("budget.source_id", "Сумма без источника не публикуется: укажите source_id.")
        if out["budget"]["basis"] == "unknown":
            errors.add("budget.basis", "Для суммы укажите основание: planned, contract или spent.")
        if out["evidence_type"] == "synthetic":
            errors.add("budget.amount_kzt", "Синтетическая запись не может содержать сумму в тенге.")
    errors.raise_if_any()
    return out


def validate_for_publication(content: dict) -> None:
    """Дополнительные условия перед публикацией."""
    errors = _Errors()
    if content["evidence_type"] in ("observed", "derived") and not content["source_refs"]:
        errors.add("source_refs", "Для observed/derived нужен хотя бы один источник.")
    errors.raise_if_any()


def clean_reason(value, *, required: bool) -> str:
    errors = _Errors()
    text = clean_text(value, "reason", errors, max_len=MAX_TEXT["reason"], required=required,
                      multiline=True)
    errors.raise_if_any()
    return text or ""


def clean_internal_notes(value) -> str:
    errors = _Errors()
    text = clean_text(value, "internal_notes", errors, max_len=MAX_TEXT["internal_notes"],
                      multiline=True)
    errors.raise_if_any()
    return text or ""


def flatten(content: dict) -> dict:
    """Плоское представление для diff: schedule.planned_start, budget.amount_kzt..."""
    flat = {}
    for key in CONTENT_FIELDS:
        value = content.get(key)
        if key in NESTED_FIELDS:
            for name in NESTED_FIELDS[key]:
                flat[f"{key}.{name}"] = (value or {}).get(name)
        else:
            flat[key] = value
    return flat


def diff(before: dict | None, after: dict) -> dict:
    """{путь: {before, after}} по содержимому (+ internal_notes, если есть в обоих)."""
    old = flatten(before) if before is not None else {}
    new = flatten(after)
    changes = {}
    for path, value in new.items():
        if before is None or old.get(path) != value:
            changes[path] = {"before": old.get(path), "after": value}
    return changes
