"""Этапы объекта, отставание и «давно не обновлялось» (R06, раунд 14; CONTRACT §7).

Этап хранится отдельным слоем (таблица civic_object_stages, миграция 6) поверх объекта civic-v1:
сам объект, его публичная проекция и история не меняются. Жителю этап показывается только у
опубликованного объекта (берётся из civic_public_objects).

Правила расчёта (их же проверяют tests/civic/R06/round14/):
  stage         planned → design → procurement → construction → acceptance → operating; None — неизвестен.
  planned_end   плановый срок окончания (по умолчанию — исходный срок объекта original_planned_end).
  forecast_end  прогноз окончания от сотрудника. Если его нет, план взят из карточки (миграция или
                значение по умолчанию), а срок объекта перенесён (current_planned_end ≠ planned_end),
                прогнозом считается перенесённый срок.
  delay_days    на сколько дней объект отстаёт от плана СЕЙЧАС:
                - не работает и сегодня позже плана → не меньше (сегодня − план), даже если старый
                  прогноз обещал раньше (прогноз в прошлом уже не прогноз);
                - иначе (прогноз − план), не меньше 0;
                - operating → фактическое отставание (actual_end или прогноз − план), late = False;
                - нет плана или этапа → None.
  late          delay_days > 0 и объект ещё не работает.
  stale         не обновлялся больше 14 дней (этап и карточка объекта — берётся более свежее),
                только для незавершённых объектов с известным этапом: работающий сквер
                «давно не обновлялся» по естественной причине и тревогу не поднимает.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from .districts import DISTRICT_NAMES, bbox_intersects, district_of, geometry_bbox
from .objects import ASTANA_TZ, BadRequest, Conflict, NotFound, iso, utc_now, _dumps, _loads
from .validate import (MAX_YEAR, MIN_YEAR, ValidationError, _Errors, clean_text, is_valid_id,
                       parse_date)
from . import dto


STAGES = ("planned", "design", "procurement", "construction", "acceptance", "operating")
# Вывод этапа из статуса civic-v1 — тот же, что в миграции 6 (db.py). Для объектов,
# созданных после миграции и ещё без своей строки этапа.
STATUS_TO_STAGE = {"planned": "planned", "in_progress": "construction", "completed": "operating"}
STALE_DAYS = 14
MAX_REASON = 500
MAX_OBJECTS = 1000  # публичный список: Астана — сотни объектов, не десятки тысяч
# Казахские названия СИНТЕТИЧЕСКИХ демо-записей (seed-demo R02 и demo_package.json R06; просьба R08, день 3).
# Настоящие записи civic-v1 одноязычные: у них title_kk = None, интерфейс показывает title с lang="ru".
# Черновик R06 — на вычитку R11.
DEMO_TITLES_KK = {
    "demo-r02-sidewalk-delay": "Тротуарды жөндеу",
    "demo-r02-yard-landscaping": "Ауланы абаттандыру",
    "demo-r02-event-no-geometry": "Нақты орны көрсетілмеген қалалық іс-шара",
}


def _date(value):
    return parse_date(value) if isinstance(value, str) else None


def _days(a: date, b: date) -> int:
    return (a - b).days


def compute_lifecycle(*, stage, planned_end, forecast_end, current_planned_end=None, actual_end=None,
                      last_update=None, today: date) -> dict:
    """Чистая функция расчёта: без базы, чтобы её можно было проверить на краевых случаях."""
    planned = _date(planned_end)
    forecast = _date(forecast_end)
    moved = _date(current_planned_end)
    if forecast is None and moved is not None and planned is not None and moved != planned:
        forecast = moved  # срок объекта перенесён — это и есть прогноз
    delay = None
    if stage is not None and planned is not None:
        if stage == "operating":
            finished = _date(actual_end) or forecast
            delay = max(0, _days(finished, planned)) if finished else 0
        else:
            expected = forecast or planned
            if today > planned and today > expected:
                expected = today
            delay = max(0, _days(expected, planned))
    late = bool(delay) and stage != "operating"
    stale_days = None
    if last_update is not None:
        stale_days = max(0, _days(today, last_update))
    stale = (stage is not None and stage != "operating" and stale_days is not None
             and stale_days > STALE_DAYS)
    return {
        "stage": stage,
        "stage_index": STAGES.index(stage) if stage in STAGES else None,
        "planned_end": planned.isoformat() if planned else None,
        "forecast_end": forecast.isoformat() if forecast else None,
        "forecast_source": ("editor" if _date(forecast_end) else ("schedule" if forecast else None)),
        "delay_days": delay,
        "late": late,
        "stale": stale,
        "stale_days": stale_days,
    }


def _parse_ts(value):
    """ISO-время из базы → дата в Астане (для «давно не обновлялось»)."""
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def parse_bbox(text):
    """bbox=min_lon,min_lat,max_lon,max_lat → кортеж; ошибки — 400 с понятным полем."""
    if text is None:
        return None
    try:
        parts = [float(part) for part in text.split(",")]
    except (ValueError, AttributeError):
        parts = []
    if (len(parts) != 4 or any(p != p or p in (float("inf"), float("-inf")) for p in parts)
            or not (-180 <= parts[0] <= parts[2] <= 180 and -90 <= parts[1] <= parts[3] <= 90)):
        raise BadRequest("Недопустимый bbox.", {"bbox": "min_lon,min_lat,max_lon,max_lat (WGS84)."})
    return tuple(parts)


def _single(query, name):
    items = query.get(name, [])
    if len(items) > 1:
        raise BadRequest("Параметр указан несколько раз.", {name: "Один раз."})
    return items[0] if items else None


def parse_district(query):
    value = _single(query, "district")
    if value is None or value in ("", "all"):
        return None
    if value not in DISTRICT_NAMES:
        raise BadRequest("Неизвестный район.", {"district": "Допустимо: " + ", ".join(DISTRICT_NAMES)})
    return value


class StageRepository:
    def __init__(self, database, clock):
        self.db = database
        self.clock = clock

    def today(self) -> date:
        return utc_now(self.clock).astimezone(ASTANA_TZ).date()

    # --- чтение ------------------------------------------------------------------------

    @staticmethod
    def _stage_row(conn, object_id):
        return conn.execute("SELECT * FROM civic_object_stages WHERE object_id = ?", (object_id,)).fetchone()

    def _item(self, public_item: dict, stage_row, today: date) -> dict:
        """Публичный DTO объекта + поля этапа (CONTRACT §7)."""
        schedule = public_item.get("schedule") or {}
        if stage_row is not None:
            stage, planned_end, forecast_end = stage_row["stage"], stage_row["planned_end"], stage_row["forecast_end"]
            source, stage_updated = stage_row["source"], stage_row["updated_at"]
        else:
            # Объект появился после миграции и этап ещё не задавали: тот же вывод из статуса.
            stage = STATUS_TO_STAGE.get(public_item.get("status"))
            planned_end = schedule.get("original_planned_end") or schedule.get("current_planned_end")
            forecast_end, source, stage_updated = None, "default", None
        moments = [m for m in (_parse_ts(stage_updated), _parse_ts(public_item.get("updated_at"))) if m]
        last = max(moments) if moments else None
        # Перенесённый срок карточки — прогноз, только если и план взят из карточки (migrated/default).
        # Если план задал сотрудник (editor/demo), прогноз — только его forecast_end.
        moved = schedule.get("current_planned_end") if source in ("migrated", "default") else None
        life = compute_lifecycle(
            stage=stage, planned_end=planned_end, forecast_end=forecast_end,
            current_planned_end=moved, actual_end=schedule.get("actual_end"),
            last_update=last.astimezone(ASTANA_TZ).date() if last else None, today=today)
        district = district_of(public_item.get("geometry"))
        # demo: синтетическая запись (evidence_type synthetic) — интерфейс помечает «Пример».
        demo = public_item.get("evidence_type") == "synthetic"
        return {
            **public_item,
            **life,
            "stage_source": source,
            "stage_updated_at": stage_updated,
            "last_update_at": iso(last) if last else None,
            "district": district,
            "demo": demo,
            "title_kk": DEMO_TITLES_KK.get(public_item.get("id")) if demo else None,
        }

    def list_public(self, query: dict) -> dict:
        bbox = parse_bbox(_single(query, "bbox"))
        district = parse_district(query)
        today = self.today()
        with self.db.read() as conn:
            rows = conn.execute(
                """SELECT p.dto_json, s.stage, s.planned_end, s.forecast_end, s.source, s.updated_at
                     AS updated_at FROM civic_public_objects p
                   LEFT JOIN civic_object_stages s ON s.object_id = p.id
                   ORDER BY p.updated_at DESC, p.id DESC LIMIT ?""", (MAX_OBJECTS + 1,)).fetchall()
        items = []
        for row in rows[:MAX_OBJECTS]:
            public_item = dto.sanitize_public(_loads(row["dto_json"]))
            if bbox is not None:
                box = geometry_bbox(public_item.get("geometry"))
                if box is None or not bbox_intersects(box, bbox):
                    continue
            item = self._item(public_item, row if row["source"] is not None else None, today)
            if district is not None and item["district"] != district:
                continue
            items.append(item)
        return {"items": items, "truncated": len(rows) > MAX_OBJECTS, "today": today.isoformat(),
                "stale_after_days": STALE_DAYS}

    def get_public(self, object_id) -> dict:
        if not is_valid_id(object_id):
            raise BadRequest("Недопустимый ID объекта.", {"id": "Пустой или недопустимый ID."})
        with self.db.read() as conn:
            row = conn.execute("SELECT dto_json FROM civic_public_objects WHERE id = ?", (object_id,)).fetchone()
            if row is None:
                raise NotFound(object_id)
            stage_row = self._stage_row(conn, object_id)
            history = conn.execute(
                """SELECT revision, at, stage, planned_end, forecast_end, public_actor_label
                   FROM civic_stage_history WHERE object_id = ? ORDER BY revision""", (object_id,)).fetchall()
        item = self._item(dto.sanitize_public(_loads(row["dto_json"])), stage_row, self.today())
        return {"item": item, "stage_history": [
            {"revision": h["revision"], "at": h["at"], "stage": h["stage"], "planned_end": h["planned_end"],
             "forecast_end": h["forecast_end"], "public_actor_label": h["public_actor_label"]}
            for h in history]}

    def get_staff(self, object_id) -> dict:
        """Этап любой рабочей копии (и черновика) с ревизией для expected_revision и служебной историей."""
        if not is_valid_id(object_id):
            raise BadRequest("Недопустимый ID объекта.", {"id": "Пустой или недопустимый ID."})
        with self.db.read() as conn:
            obj = conn.execute("SELECT status, data_json, updated_at, publication FROM civic_objects WHERE id = ?",
                               (object_id,)).fetchone()
            if obj is None:
                raise NotFound(object_id)
            stage_row = self._stage_row(conn, object_id)
            history = conn.execute("SELECT * FROM civic_stage_history WHERE object_id = ? ORDER BY revision",
                                   (object_id,)).fetchall()
        content = _loads(obj["data_json"])
        pseudo = {"status": obj["status"], "schedule": content.get("schedule") or {},
                  "geometry": content.get("geometry"), "updated_at": obj["updated_at"],
                  "evidence_type": content.get("evidence_type")}
        item = self._item(pseudo, stage_row, self.today())
        for key in ("status", "schedule", "geometry", "updated_at", "evidence_type"):
            item.pop(key, None)
        item.update({"object_id": object_id, "publication": obj["publication"],
                     "stage_revision": stage_row["revision"] if stage_row else 0})
        return {"item": item, "history": [{
            "revision": h["revision"], "at": h["at"], "action": h["action"], "stage": h["stage"],
            "planned_end": h["planned_end"], "forecast_end": h["forecast_end"], "reason": h["reason"],
            "actor_label": h["actor_label"], "public_actor_label": h["public_actor_label"]} for h in history]}

    # --- запись ------------------------------------------------------------------------

    @staticmethod
    def _clean(payload: dict):
        errors = _Errors()
        stage = payload.get("stage")
        if stage not in STAGES:
            errors.add("stage", "Выберите этап: " + ", ".join(STAGES) + ".")
        dates = {}
        for name in ("planned_end", "forecast_end"):
            value = payload.get(name)
            if value is None or value == "":
                dates[name] = None
                continue
            parsed = parse_date(value) if isinstance(value, str) else None
            if parsed is None or not MIN_YEAR <= parsed.year <= MAX_YEAR:
                errors.add(name, f"Дата YYYY-MM-DD ({MIN_YEAR}–{MAX_YEAR}) или пусто.")
            else:
                dates[name] = parsed.isoformat()
        reason = clean_text(payload.get("reason"), "reason", errors, max_len=MAX_REASON)
        expected = payload.get("expected_revision")
        if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
            errors.add("expected_revision", "Целое ≥ 0: stage_revision из последней карточки (0 — этапа ещё нет).")
        unknown = sorted(set(payload) - {"stage", "planned_end", "forecast_end", "reason", "expected_revision"})
        if unknown:
            errors.add(unknown[0] if len(unknown[0]) <= 64 else "body", "Неизвестное поле.")
        if errors.fields:
            raise ValidationError(errors.fields)
        return stage, dates["planned_end"], dates["forecast_end"], reason or "", expected

    def set_stage(self, actor, object_id, payload: dict) -> dict:
        """Сотрудник задаёт этап и сроки. Одна транзакция: строка этапа + запись истории."""
        if not is_valid_id(object_id):
            raise BadRequest("Недопустимый ID объекта.", {"id": "Пустой или недопустимый ID."})
        stage, planned_end, forecast_end, reason, expected = self._clean(payload)
        now = iso(utc_now(self.clock))
        with self.db.write() as conn:
            if conn.execute("SELECT 1 FROM civic_objects WHERE id = ?", (object_id,)).fetchone() is None:
                raise NotFound(object_id)
            row = self._stage_row(conn, object_id)
            current = row["revision"] if row else 0
            if current != expected:
                raise Conflict("Этап уже изменил другой сотрудник: обновите карточку.", current)
            unchanged = (row is not None and row["stage"] == stage and row["planned_end"] == planned_end
                         and row["forecast_end"] == forecast_end)
            if not unchanged:
                revision = current + 1
                if row is None:
                    conn.execute(
                        """INSERT INTO civic_object_stages(object_id, stage, planned_end, forecast_end, revision,
                               updated_at, updated_by, source) VALUES (?, ?, ?, ?, ?, ?, ?, 'editor')""",
                        (object_id, stage, planned_end, forecast_end, revision, now, actor.user_id))
                else:
                    cursor = conn.execute(
                        """UPDATE civic_object_stages SET stage = ?, planned_end = ?, forecast_end = ?,
                               revision = ?, updated_at = ?, updated_by = ?, source = 'editor'
                           WHERE object_id = ? AND revision = ?""",
                        (stage, planned_end, forecast_end, revision, now, actor.user_id, object_id, current))
                    if cursor.rowcount != 1:
                        raise Conflict("Этап изменён параллельно.", None)
                conn.execute(
                    """INSERT INTO civic_stage_history(object_id, revision, at, action, stage, planned_end,
                           forecast_end, reason, actor_user_id, actor_label, public_actor_label)
                       VALUES (?, ?, ?, 'set', ?, ?, ?, ?, ?, ?, ?)""",
                    (object_id, revision, now, stage, planned_end, forecast_end, reason, actor.user_id,
                     actor.label, actor.public_label))
        result = self.get_staff(object_id)
        result["changed"] = not unchanged
        return result

    def seed_demo(self, object_id, *, stage, planned_end, forecast_end=None, updated_at=None) -> None:
        """Только для демо-стенда (CLI seed-r14-demo): этап с заданным временем обновления."""
        stamp = updated_at or iso(utc_now(self.clock))
        with self.db.write() as conn:
            row = self._stage_row(conn, object_id)
            revision = (row["revision"] if row else 0) + 1
            conn.execute(
                """INSERT INTO civic_object_stages(object_id, stage, planned_end, forecast_end, revision,
                       updated_at, updated_by, source) VALUES (?, ?, ?, ?, ?, ?, NULL, 'demo')
                   ON CONFLICT(object_id) DO UPDATE SET stage = excluded.stage, planned_end = excluded.planned_end,
                       forecast_end = excluded.forecast_end, revision = excluded.revision,
                       updated_at = excluded.updated_at, source = 'demo'""",
                (object_id, stage, planned_end, forecast_end, revision, stamp))
            conn.execute(
                """INSERT INTO civic_stage_history(object_id, revision, at, action, stage, planned_end,
                       forecast_end, reason, actor_user_id, actor_label, public_actor_label)
                   VALUES (?, ?, ?, 'demo', ?, ?, ?, 'Демо-данные (synthetic)', NULL, 'demo', 'Birge')""",
                (object_id, revision, stamp, stage, planned_end, forecast_end))

    # --- для «Картины дня» (R08) ----------------------------------------------------------

    def lagging(self, district=None) -> dict:
        """Опубликованные объекты с отставанием и устаревшие, по району (None — весь город).

        Возвращает только посчитанные данные: R08 строит из них свои фразы.
        late — по убыванию delay_days; stale — по убыванию stale_days.
        """
        if district is not None and district not in DISTRICT_NAMES:
            raise BadRequest("Неизвестный район.", {"district": "Допустимо: " + ", ".join(DISTRICT_NAMES)})
        query = {"district": [district]} if district else {}
        data = self.list_public(query)

        def brief(item):
            return {"id": item["id"], "title": item["title"], "title_kk": item["title_kk"], "kind": item["kind"],
                    "district": item["district"], "stage": item["stage"], "planned_end": item["planned_end"],
                    "forecast_end": item["forecast_end"], "delay_days": item["delay_days"],
                    "stale_days": item["stale_days"], "late": item["late"], "stale": item["stale"],
                    "demo": item["demo"], "geometry": item["geometry"]}

        late = sorted((brief(i) for i in data["items"] if i["late"]),
                      key=lambda i: (-i["delay_days"], i["id"]))
        stale = sorted((brief(i) for i in data["items"] if i["stale"]),
                       key=lambda i: (-(i["stale_days"] or 0), i["id"]))
        by_district = {}
        for item in data["items"]:
            key = item["district"] or "unknown"
            entry = by_district.setdefault(key, {"total": 0, "late": 0, "stale": 0})
            entry["total"] += 1
            entry["late"] += int(item["late"])
            entry["stale"] += int(item["stale"])
        return {"today": data["today"], "district": district, "late": late, "stale": stale,
                "counts": {"total": len(data["items"]), "late": len(late), "stale": len(stale)},
                "by_district": by_district, "stale_after_days": STALE_DAYS, "truncated": data["truncated"]}
