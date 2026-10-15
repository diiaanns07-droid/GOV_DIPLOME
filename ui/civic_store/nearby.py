"""«Что делают рядом»: работы и отключения, которые сотрудник добавляет вручную (R06 — данные, волна 2 п. 4).

Экран жителя «Рядом» — R08 (ui/civic_akim/nearby.py, web/civic/nearby/): он вызывает nearby_items(district) из
ui.civic_store.v2 и сам раскладывает карточки по вкладкам «Ремонтируют сейчас / Завершили / Запланировано /
Отключения». Форма сотрудника — web/civic/proposals/works.js (акимат: «Ещё → Работы и отключения»).

Правила R11 (IA_WAVE2 §4) — проверяет сервер, не только форма:
  - у каждой записи 4 строки «Зачем?»: проблема → почему так → результат → неудобства и срок;
  - у отключения обязательны источник (служба), время начала и конца, где (зона);
  - задержки показываем: у работы плановый срок и, если сдвинулся, прогноз (R08 пишет «срок перенесён»);
  - реальные названия организаций не придумываем: источник — общее название службы (как в таблице служб R08).

Тексты — на языке сотрудника (lang). Второй язык можно дописать позже той же правкой с другим lang. Пока перевода
нет, R08 показывает текст на языке записи (для title_kk — его пометка title_kk_missing).
Демо-записи (demo=true, «Пример») хранят сроки относительно сегодняшнего дня — показ в любой день одинаков.

Раунд 15 (работа v2, CONTRACT §5.6; подробности — works_v2.py): у записи есть служба (service), вид v2 (kind:
dig | surface | closure | landscape | lighting | other) и участки улиц (segments — рёбра графа OSM R12). Старая форма,
которая их не шлёт, получает значения по умолчанию из вида раунда 14; при правке старой формой участки и служба
сохраняются. Чтение для соседей: works_v2 (календарь и конфликты R12) и works_near (работы рядом с двором R16).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import secrets

from .districts import DISTRICT_NAMES, district_of
from .objects import BadRequest, Conflict, NotFound, iso, utc_now, _dumps, _loads
from .stages import parse_district
from .validate import ValidationError, _Errors, clean_geometry, clean_text, is_valid_id, parse_date
from . import works_v2
from .works_v2 import KINDS_V2, KIND_TO_WORK_KIND, WORK_KIND_TO_KIND, WORK_KIND_TO_SERVICE


ASTANA_TZ = timezone(timedelta(hours=5))
TYPES = ("work", "outage")
WORK_STATUSES = ("in_progress", "done", "planned")
WORK_KINDS = ("roadworks", "construction", "landscaping", "lighting", "event", "other")  # works.kind.* R11 (+ lighting, как у R08)
UTILITIES = ("water", "heating", "power", "gas", "road_closure")             # nearby.utility.* словаря R11
# Источник отключения — id службы из таблицы служб R08 (ui/civic_akim/routing.py SERVICES): общие названия
# («Водоканал», «Теплосеть»), не реальные организации. Копия id, чтобы хранилище не зависело от модуля R08.
SOURCES = ("road", "traffic", "street_cleaning", "transport", "lighting", "landscaping", "greenery", "waste",
           "utilities", "heating", "water", "power", "gas", "housing", "ecology", "emergency", "police", "animals",
           "parking", "akimat")
WHY_KEYS = ("problem", "reason", "result", "inconvenience")
LANGS = ("ru", "kk")
TITLE_MAX = 120
LINE_MAX = 200
MAX_OUTAGE_DAYS = 14        # отключение дольше двух недель — это уже работа, а не «отключение»
MAX_AHEAD_DAYS = 120
MAX_ITEMS = 500
NEAR_RADIUS_M = 500         # «работы рядом с двором» R16 по умолчанию: 500 м от точки двора
NEAR_RADIUS_MAX_M = 3000
_KEEP = object()            # поле v2 не прислано (старая форма) — при правке оставить как было


def default_service(kind_type, work_kind, source):
    """Служба по умолчанию (как в миграции 10): источник отключения или служба по виду работы раунда 14."""
    return source or WORK_KIND_TO_SERVICE.get(work_kind)


def default_kind(kind_type, work_kind, utility):
    """Вид v2 по умолчанию (как в миграции 10): перекрытие — closure; другие отключения — не работы на улице."""
    if kind_type == "outage":
        return "closure" if utility == "road_closure" else None
    return WORK_KIND_TO_KIND.get(work_kind or "other", "other")


class NearbyRepository:
    def __init__(self, database, clock):
        self.db = database
        self.clock = clock

    def now(self) -> datetime:
        return utc_now(self.clock).astimezone(ASTANA_TZ)

    # --- чтение --------------------------------------------------------------------------

    def items(self, district=None) -> list[dict]:
        """Для R08 nearby.load_items: записи района в формате ITEM (без служебных полей)."""
        if district is not None and district not in DISTRICT_NAMES:
            raise BadRequest("Неизвестный район.", {"district": "Допустимо: " + ", ".join(DISTRICT_NAMES)})
        now = self.now()
        with self.db.read() as conn:
            rows = conn.execute(
                """SELECT * FROM civic_nearby_items WHERE removed = 0 AND (? IS NULL OR district = ?)
                   ORDER BY updated_at DESC, id LIMIT ?""", (district, district, MAX_ITEMS)).fetchall()
        return [self._item(row, now) for row in rows]

    def list_staff(self, query: dict) -> dict:
        """Сотруднику: все записи района (и прошедшие), с ревизией и текстами по языкам — для правки."""
        district = parse_district(query)
        now = self.now()
        with self.db.read() as conn:
            rows = conn.execute(
                """SELECT * FROM civic_nearby_items WHERE removed = 0 AND (? IS NULL OR district = ?)
                   ORDER BY updated_at DESC, id LIMIT ?""", (district, district, MAX_ITEMS + 1)).fetchall()
        items = [self._item(row, now, staff=True) for row in rows[:MAX_ITEMS]]
        return {"items": items, "truncated": len(rows) > MAX_ITEMS,
                "options": {"types": list(TYPES), "statuses": list(WORK_STATUSES), "work_kinds": list(WORK_KINDS),
                            "utilities": list(UTILITIES), "sources": list(SOURCES),
                            "districts": list(DISTRICT_NAMES),
                            # работа v2: служба — те же id, что sources; вид v2 — для календаря R12
                            "services": list(SOURCES), "kinds": list(KINDS_V2)}}

    def get_staff(self, item_id) -> dict:
        with self.db.read() as conn:
            return {"item": self._item(self._row(conn, item_id), self.now(), staff=True)}

    # --- чтение для соседей: работа v2 (CONTRACT §5.6) ------------------------------------------------------

    def works_v2(self, *, date_from=None, date_to=None, district=None, street=None, service=None,
                 include_outages=False) -> dict:
        """Календарь и конфликты R12: работы (и перекрытия проезда — вид closure) в формате §5.6.

        date_from / date_to — даты ГГГГ-ММ-ДД (работа идёт хотя бы день периода); street — часть названия улицы
        участка (ru или kk, без регистра); include_outages — ещё и отключения воды/тепла/света/газа (не работы на улице).
        """
        if district is not None and district not in DISTRICT_NAMES:
            raise BadRequest("Неизвестный район.", {"district": "Допустимо: " + ", ".join(DISTRICT_NAMES)})
        for name, value in (("from", date_from), ("to", date_to)):
            if value is not None and parse_date(value) is None:
                raise BadRequest("Дата ГГГГ-ММ-ДД.", {name: "Дата ГГГГ-ММ-ДД."})
        if service is not None and service not in SOURCES:
            raise BadRequest("Неизвестная служба.", {"service": "Служба — из таблицы служб."})
        needle = street.strip().casefold() if isinstance(street, str) and street.strip() else None
        out = []
        for item in self.items(district):
            if item["type"] == "outage" and item.get("kind") != "closure" and not include_outages:
                continue
            record = works_v2.work_record(item)
            if service is not None and record["service"] != service:
                continue
            if needle and not any(needle in (record.get(k) or "").casefold() for k in ("street_ru", "street_kk",
                                                                                       "zone_ru", "zone_kk")):
                continue
            if (date_from or date_to) and not works_v2.overlaps(record, date_from, date_to):
                continue
            out.append(record)
        out.sort(key=lambda r: (r["starts_on"] or "", r["ends_on"] or "", r["id"]))
        return {"items": out, "count": len(out), "today": self.now().date().isoformat(), "module": "R06",
                "kinds": list(KINDS_V2), "services": list(SOURCES)}

    def works_near(self, point, *, radius_m=NEAR_RADIUS_M, include_outages=True, include_done=False) -> dict:
        """«Работы рядом» для двора R16: записи, место которых (точка или участок улицы) ближе radius_m к точке.

        Записи без места не показываем — честнее, чем «где-то в районе». Ближние — первыми.
        """
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise BadRequest("Нужна точка [долгота, широта].", {"point": "Пара [долгота, широта]."})
        try:
            lon, lat = float(point[0]), float(point[1])
        except (TypeError, ValueError):
            raise BadRequest("Нужна точка [долгота, широта].", {"point": "Пара [долгота, широта]."}) from None
        if not (70.9 <= lon <= 71.9 and 50.9 <= lat <= 51.4):
            raise BadRequest("Точка вне Астаны.", {"point": "Точка внутри Астаны."})
        radius = NEAR_RADIUS_M if radius_m is None else radius_m
        if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not 10 <= radius <= NEAR_RADIUS_MAX_M:
            raise BadRequest("Радиус 10–3000 м.", {"radius_m": "Число от 10 до 3000."})
        out = []
        for item in self.items(None):
            if item["type"] == "outage" and not include_outages:
                continue
            if item["type"] == "work" and item["status"] == "done" and not include_done:
                continue
            distance = works_v2.distance_to_geometry_m([lon, lat], item.get("geometry"))
            if distance is None or distance > radius:
                continue
            record = works_v2.work_record(item)
            record["distance_m"] = int(round(distance))
            out.append(record)
        out.sort(key=lambda r: (r["distance_m"], r["id"]))
        return {"items": out, "count": len(out), "radius_m": radius, "module": "R06"}

    @staticmethod
    def _row(conn, item_id):
        if not is_valid_id(item_id):
            raise BadRequest("Недопустимый ID записи.", {"id": "Пустой или недопустимый ID."})
        row = conn.execute("SELECT * FROM civic_nearby_items WHERE id = ? AND removed = 0", (item_id,)).fetchone()
        if row is None:
            raise NotFound(item_id)
        return row

    def _item(self, row, now: datetime, *, staff=False) -> dict:
        texts = _loads(row["texts_json"]) or {}
        start, end = row["start_at"], row["end_at"]
        planned, forecast = row["planned_end"], row["forecast_end"]
        updated = row["updated_at"]
        rel = _loads(row["demo_rel_json"]) if row["demo"] and row["demo_rel_json"] else None
        if rel:
            start, end, planned, forecast, updated = _demo_times(rel, now, start, end, planned, forecast, updated)

        def pair(field):
            # ru всегда заполнен (у R08 запасной язык — ru); kk — только настоящий перевод, иначе None.
            ru, kk = texts.get(field + "_ru"), texts.get(field + "_kk")
            return (ru or kk or None), (kk or None)

        out = {"id": row["id"], "type": row["type"], "status": row["status"], "work_kind": row["work_kind"],
               "utility": row["utility"], "district": row["district"],
               "start": start, "end": end, "planned_end": planned, "forecast_end": forecast,
               "source": row["source"], "updated_at": updated, "demo": bool(row["demo"]),
               "geometry": _loads(row["geometry_json"]) if row["geometry_json"] else None,
               "text_lang": texts.get("lang") or "ru", "source_kind": "r06"}
        # Работа v2 (миграция 10): служба, вид v2, участки улиц и их улица. source выше — прежний (служба отключения).
        place = (_loads(row["place_json"]) if row["place_json"] else None) or {}
        out["service"] = row["service"]
        out["kind"] = row["kind"]
        out["segments"] = (_loads(row["segments_json"]) if row["segments_json"] else None) or []
        out["street_ru"], out["street_kk"] = place.get("street_ru"), place.get("street_kk")
        for field in ("title", "zone", "detour"):
            out[field + "_ru"], out[field + "_kk"] = pair(field)
        why = {}
        for key in WHY_KEYS:
            why[key + "_ru"], why[key + "_kk"] = pair("why_" + key)
        out["why"] = why if any(why.values()) else None
        if staff:
            out["revision"] = row["revision"]
            out["texts"] = {k: v for k, v in texts.items() if k != "lang"}
            out["created_at"] = row["created_at"]
            out["place"] = place or None
        return out

    # --- запись (сотрудник) --------------------------------------------------------------

    def _clean(self, payload: dict, *, update=False) -> dict:
        errors = _Errors()
        allowed = {"type", "status", "work_kind", "utility", "district", "lang", "title", "zone", "detour", "why",
                   "start", "end", "planned_end", "forecast_end", "source", "geometry", "expected_revision",
                   # работа v2 (раунд 15, CONTRACT §5.6)
                   "service", "kind", "segments", "segment", "starts_on", "ends_on"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            errors.add(unknown[0] if isinstance(unknown[0], str) and len(unknown[0]) <= 64 else "body",
                       "Неизвестное поле.")
        kind = payload.get("type")
        if kind not in TYPES:
            errors.add("type", "work (работа) или outage (отключение, перекрытие).")
        lang = payload.get("lang", "ru")
        if lang not in LANGS:
            errors.add("lang", "ru или kk.")
        geometry = clean_geometry(payload.get("geometry"), "geometry", errors)
        if geometry is not None and geometry["type"] != "Point":
            errors.add("geometry", "Место — точка на карте (или без места); участок улицы — полем segment.")
            geometry = None
        # Участки улиц (v2): не прислано — при правке остаются прежние; [] или null — убрать участки.
        segments = place = _KEEP
        if "segment" in payload or "segments" in payload:
            if "segment" not in payload and payload.get("segments") in (None, []):
                segments = place = None
            else:
                segments, place, line = works_v2.clean_segments(payload, errors)
                if line is not None:
                    geometry = line  # форма участка — из графа OSM R12, а не точка формы
        district = payload.get("district")
        if district is None and geometry is not None:
            district = district_of(geometry)
        if not isinstance(district, str) or district not in DISTRICT_NAMES:
            errors.add("district", "Выберите район: " + ", ".join(DISTRICT_NAMES) + ".")
        elif geometry is not None and district_of(geometry) not in (None, district):
            errors.add("geometry", "Точка — в другом районе." if geometry["type"] == "Point"
                       else "Участок улицы — в другом районе.")
        title = clean_text(payload.get("title"), "title", errors, max_len=TITLE_MAX, required=True)
        zone = clean_text(payload.get("zone"), "zone", errors, max_len=LINE_MAX, required=kind == "outage")
        detour = clean_text(payload.get("detour"), "detour", errors, max_len=LINE_MAX)
        why = payload.get("why")
        lines = {}
        if not isinstance(why, dict) or set(why) - set(WHY_KEYS):
            errors.add("why", "4 строки «Зачем?»: problem, reason, result, inconvenience.")
        else:
            for key in WHY_KEYS:
                lines[key] = clean_text(why.get(key), "why." + key, errors, max_len=LINE_MAX, required=True)
        # Служба и вид v2. Не прислано при правке — решит update (выбранное сотрудником остаётся).
        service = payload.get("service", _KEEP if update else None)
        if service is not _KEEP and service is not None and service not in SOURCES:
            errors.add("service", "Служба — из таблицы служб.")
        kind_v2 = payload.get("kind", _KEEP if update else None)
        if kind_v2 is not _KEEP and kind_v2 is not None and kind_v2 not in KINDS_V2:
            errors.add("kind", "Вид работы: " + ", ".join(KINDS_V2) + ".")
        status = work_kind = utility = source = start = end = planned = forecast = None
        today = self.now().date()
        if kind == "work":
            status = payload.get("status")
            if status not in WORK_STATUSES:
                errors.add("status", "in_progress, done или planned.")
            work_kind = payload.get("work_kind") or (KIND_TO_WORK_KIND.get(kind_v2) if isinstance(kind_v2, str)
                                                     else None) or "other"
            if work_kind not in WORK_KINDS:
                errors.add("work_kind", "Допустимо: " + ", ".join(WORK_KINDS) + ".")
            # starts_on / ends_on (CONTRACT §5.6) — те же даты, что start / planned_end раунда 14.
            for old_name, new_name in (("start", "starts_on"), ("planned_end", "ends_on")):
                if payload.get(new_name) not in (None, "") and payload.get(old_name) not in (None, "", payload[new_name]):
                    errors.add(new_name, f"{new_name} и {old_name} различаются: пришлите одно поле.")
            planned = _date(payload.get("planned_end") or payload.get("ends_on"), "planned_end", errors, today,
                            required=True)
            forecast = _date(payload.get("forecast_end"), "forecast_end", errors, today)
            start = _date(payload.get("start") or payload.get("starts_on"), "start", errors, today)
            if start and planned and planned < start:
                errors.add("planned_end", "Окончание раньше начала.")
            if payload.get("utility") is not None or payload.get("end") is not None:
                errors.add("utility" if payload.get("utility") is not None else "end",
                           "У работы нет вида отключения и времени окончания: срок — planned_end.")
        elif kind == "outage":
            utility = payload.get("utility")
            if utility not in UTILITIES:
                errors.add("utility", "Допустимо: " + ", ".join(UTILITIES) + ".")
            source = payload.get("source")
            if source is None and isinstance(service, str):
                source = service  # форма v2 шлёт службу; у отключения источник — та же служба
            if source not in SOURCES:
                errors.add("source", "Источник — служба из таблицы служб.")
            elif isinstance(service, str) and service != source:
                errors.add("service", "У отключения служба и источник — одно и то же.")
            if kind_v2 not in (None, _KEEP) and (kind_v2 != "closure" or utility != "road_closure"):
                errors.add("kind", "У отключения вид работы — только closure для перекрытия проезда.")
            start = _moment(payload.get("start"), "start", errors)
            end = _moment(payload.get("end"), "end", errors)
            if start and end:
                if end <= start:
                    errors.add("end", "Окончание позже начала.")
                elif end - start > timedelta(days=MAX_OUTAGE_DAYS):
                    errors.add("end", f"Отключение — не дольше {MAX_OUTAGE_DAYS} дней (дольше — это работа).")
                elif start > self.now() + timedelta(days=MAX_AHEAD_DAYS):
                    errors.add("start", f"Не дальше чем через {MAX_AHEAD_DAYS} дней.")
            for name in ("status", "planned_end", "forecast_end", "starts_on", "ends_on"):
                if payload.get(name) is not None:
                    errors.add(name, "У отключения — время начала и конца (start, end).")
        if kind == "work" and payload.get("source") is not None:  # у работы источник — по желанию
            source = payload.get("source")
            if source not in SOURCES:
                errors.add("source", "Источник — служба из таблицы служб.")
        expected = payload.get("expected_revision")
        if update and (isinstance(expected, bool) or not isinstance(expected, int) or expected < 1):
            errors.add("expected_revision", "Номер ревизии записи (из карточки).")
        if errors.fields:
            raise ValidationError(errors.fields)
        texts = {"title_" + lang: title}
        if zone:
            texts["zone_" + lang] = zone
        if detour:
            texts["detour_" + lang] = detour
        for key, text in lines.items():
            texts[f"why_{key}_{lang}"] = text
        return {"type": kind, "status": status, "work_kind": work_kind if kind == "work" else None,
                "utility": utility, "district": district, "lang": lang, "texts": texts,
                "start": start.isoformat() if isinstance(start, (date, datetime)) else start,
                "end": end.isoformat() if isinstance(end, datetime) else end,
                "planned_end": planned.isoformat() if planned else None,
                "forecast_end": forecast.isoformat() if forecast else None,
                "source": source, "geometry": geometry, "expected": expected,
                "service": service, "kind": kind_v2, "segments": segments, "place": place}

    @staticmethod
    def _v2_values(new: dict, old=None) -> tuple:
        """(service, kind, segments_json, place_json, geometry) для записи в базу.

        Не прислано (старая форма): участки и геометрия-линия остаются прежними; служба и вид, выбранные сотрудником,
        остаются, а выведенные по умолчанию следуют за новым видом работы (иначе «Освещение» осталось бы «Дорожной»).
        """
        def auto(row):
            return (default_service(row["type"], row["work_kind"], row["source"]),
                    default_kind(row["type"], row["work_kind"], row["utility"]))
        defaults = (default_service(new["type"], new["work_kind"], new["source"]),
                    default_kind(new["type"], new["work_kind"], new["utility"]))
        old_auto = auto(old) if old is not None else (None, None)
        values = []
        for i, name in enumerate(("service", "kind")):
            value = new[name]
            if value is _KEEP:
                value = old[name] if old is not None and old[name] is not None and old[name] != old_auto[i] else None
            values.append(value if value is not None else defaults[i])
        if new["type"] == "outage" and values[1] is not None and new["utility"] != "road_closure":
            values[1] = None  # отключение воды/тепла — не работа на улице (вид v2 пустой)
        segments, place, geometry = new["segments"], new["place"], new["geometry"]
        if segments is _KEEP:
            segments = _loads(old["segments_json"]) if old is not None and old["segments_json"] else None
            place = _loads(old["place_json"]) if old is not None and old["place_json"] else None
            old_geometry = _loads(old["geometry_json"]) if old is not None and old["geometry_json"] else None
            if geometry is None and segments and old_geometry and old_geometry.get("type") != "Point":
                geometry = old_geometry  # старая форма не знает линий: линия участка остаётся
        return (values[0], values[1], _dumps(segments) if segments else None, _dumps(place) if place else None,
                geometry)

    def create(self, actor, payload: dict) -> dict:
        new = self._clean(payload)
        service, kind_v2, segments_json, place_json, geometry = self._v2_values(new)
        now = iso(utc_now(self.clock))
        item_id = "w-" + secrets.token_hex(6)
        texts = dict(new["texts"], lang=new["lang"])
        with self.db.write() as conn:
            conn.execute(
                """INSERT INTO civic_nearby_items(id, type, status, work_kind, utility, district, texts_json, start_at,
                       end_at, planned_end, forecast_end, source, geometry_json, demo, revision, created_at, updated_at,
                       created_by, updated_by, service, kind, segments_json, place_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (item_id, new["type"], new["status"], new["work_kind"], new["utility"], new["district"],
                 _dumps(texts), new["start"], new["end"], new["planned_end"], new["forecast_end"], new["source"],
                 _dumps(geometry) if geometry else None, now, now, actor.user_id, actor.user_id,
                 service, kind_v2, segments_json, place_json))
            self._history(conn, item_id, 1, now, "create", actor)
            return {"item": self._item(self._row(conn, item_id), self.now(), staff=True)}

    def update(self, actor, item_id, payload: dict) -> dict:
        """Правка записи целиком (форма шлёт все поля). Тексты другого языка сохраняются, только если тексты
        на языке правки не изменились — иначе перевод устарел бы молча (покажем текст на языке записи).
        Поля v2, которых форма не прислала (форма FINAL-4), остаются прежними (_v2_values)."""
        new = self._clean(payload, update=True)
        now = iso(utc_now(self.clock))
        with self.db.write() as conn:
            row = self._row(conn, item_id)
            if row["revision"] != new["expected"]:
                raise Conflict("Запись уже изменил другой сотрудник: обновите карточку.", row["revision"])
            service, kind_v2, segments_json, place_json, geometry = self._v2_values(new, row)
            old = _loads(row["texts_json"]) or {}
            lang, other = new["lang"], "kk" if new["lang"] == "ru" else "ru"
            same = all(old.get(k) == v for k, v in new["texts"].items()) and \
                all(k in new["texts"] for k in old if k.endswith("_" + lang))
            texts = dict(new["texts"], lang=old.get("lang") or lang)
            if same:
                texts.update({k: v for k, v in old.items() if k.endswith("_" + other)})
            else:
                texts["lang"] = lang
            revision = row["revision"] + 1
            # Демо-запись после правки сотрудником становится обычной: сроки — те, что он ввёл.
            conn.execute(
                """UPDATE civic_nearby_items SET type = ?, status = ?, work_kind = ?, utility = ?, district = ?,
                       texts_json = ?, start_at = ?, end_at = ?, planned_end = ?, forecast_end = ?, source = ?,
                       geometry_json = ?, demo_rel_json = NULL, revision = ?, updated_at = ?, updated_by = ?,
                       service = ?, kind = ?, segments_json = ?, place_json = ?
                   WHERE id = ?""",
                (new["type"], new["status"], new["work_kind"], new["utility"], new["district"], _dumps(texts),
                 new["start"], new["end"], new["planned_end"], new["forecast_end"], new["source"],
                 _dumps(geometry) if geometry else None, revision, now, actor.user_id,
                 service, kind_v2, segments_json, place_json, item_id))
            self._history(conn, item_id, revision, now, "update", actor)
            return {"item": self._item(self._row(conn, item_id), self.now(), staff=True)}

    def remove(self, actor, item_id, payload: dict) -> dict:
        expected = (payload or {}).get("expected_revision")
        if isinstance(expected, bool) or not isinstance(expected, int):
            raise ValidationError({"expected_revision": "Номер ревизии записи (из карточки)."})
        now = iso(utc_now(self.clock))
        with self.db.write() as conn:
            row = self._row(conn, item_id)
            if row["revision"] != expected:
                raise Conflict("Запись уже изменил другой сотрудник: обновите карточку.", row["revision"])
            conn.execute("UPDATE civic_nearby_items SET removed = 1, revision = ?, updated_at = ?, updated_by = ? "
                         "WHERE id = ?", (row["revision"] + 1, now, actor.user_id, item_id))
            self._history(conn, item_id, row["revision"] + 1, now, "remove", actor)
        return {"removed": item_id}

    @staticmethod
    def _history(conn, item_id, revision, at, action, actor):
        row = conn.execute("SELECT * FROM civic_nearby_items WHERE id = ?", (item_id,)).fetchone()
        snapshot = {k: row[k] for k in row.keys() if k not in ("created_by", "updated_by")}
        conn.execute("""INSERT INTO civic_nearby_history(item_id, revision, at, action, snapshot_json, actor_user_id,
                            actor_label) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                     (item_id, revision, at, action, _dumps(snapshot), actor.user_id, actor.label))

    # --- демо ----------------------------------------------------------------------------

    def seed_demo(self, item: dict) -> str | None:
        """Демо-запись (demo=true) с относительными сроками. Уже есть запись с этим demo_key — ничего не делает."""
        key = item["demo_key"]
        now = iso(utc_now(self.clock))
        with self.db.write() as conn:
            if conn.execute("SELECT 1 FROM civic_nearby_items WHERE id = ?", (key,)).fetchone():
                return None
            # Служба и вид v2 — как у старых записей после миграции 10 (на свежей базе миграция прошла по пустой таблице).
            conn.execute(
                """INSERT INTO civic_nearby_items(id, type, status, work_kind, utility, district, texts_json, source,
                       geometry_json, demo, demo_rel_json, revision, created_at, updated_at, service, kind)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 1, ?, ?, ?, ?)""",
                (key, item["type"], item.get("status"), item.get("work_kind"), item.get("utility"), item["district"],
                 _dumps(dict(item["texts"], lang="ru")), item.get("source"),
                 _dumps(item["geometry"]) if item.get("geometry") else None, _dumps(item["rel"]), now, now,
                 default_service(item["type"], item.get("work_kind"), item.get("source")),
                 default_kind(item["type"], item.get("work_kind"), item.get("utility"))))
            conn.execute("""INSERT INTO civic_nearby_history(item_id, revision, at, action, snapshot_json, actor_user_id,
                                actor_label) VALUES (?, 1, ?, 'create', ?, NULL, 'seed-r14-demo')""",
                         (key, now, _dumps({"demo": True})))
        return key


def _demo_times(rel: dict, now: datetime, start, end, planned, forecast, updated):
    """Сроки демо-записи от сегодняшнего дня Астаны (как пример R08 fixtures/nearby_demo.json)."""
    today = now.date()
    if "when" in rel:
        w = rel["when"]
        day = today + timedelta(days=int(w.get("day", 0)))
        fh, fm = (int(v) for v in w["from"].split(":"))
        th, tm = (int(v) for v in w["to"].split(":"))
        s = datetime(day.year, day.month, day.day, fh, fm, tzinfo=ASTANA_TZ)
        e = datetime(day.year, day.month, day.day, th, tm, tzinfo=ASTANA_TZ)
        if e <= s:
            e += timedelta(days=1)  # ночное перекрытие 22:00–06:00
        start, end = s.isoformat(timespec="seconds"), e.isoformat(timespec="seconds")
    if "start_day" in rel:
        start = (today + timedelta(days=int(rel["start_day"]))).isoformat()
    if "planned_end_day" in rel:
        planned = (today + timedelta(days=int(rel["planned_end_day"]))).isoformat()
    if "forecast_end_day" in rel:
        forecast = (today + timedelta(days=int(rel["forecast_end_day"]))).isoformat()
    updated = (now - timedelta(minutes=int(rel.get("updated_ago_min", 0)))).isoformat(timespec="seconds")
    return start, end, planned, forecast, updated


def _date(value, path, errors, today, *, required=False):
    if value in (None, ""):
        if required:
            errors.add(path, "Укажите дату.")
        return None
    parsed = parse_date(value)
    if parsed is None:
        errors.add(path, "Дата ГГГГ-ММ-ДД.")
        return None
    if abs((parsed - today).days) > 3 * 366:
        errors.add(path, "Дата в пределах трёх лет от сегодня.")
        return None
    return parsed


def _moment(value, path, errors):
    """Время начала/конца отключения: ISO 8601; без часового пояса — время Астаны (UTC+5)."""
    if not isinstance(value, str) or not 10 <= len(value) <= 40:
        errors.add(path, "Дата и время, например 2026-10-13T10:00.")
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.add(path, "Дата и время, например 2026-10-13T10:00.")
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ASTANA_TZ)
    if not 2000 <= moment.year <= 2100:  # R15: и datetime.max/min не переполняются в astimezone
        errors.add(path, "Дата и время, например 2026-10-13T10:00.")
        return None
    return moment.astimezone(ASTANA_TZ).replace(microsecond=0)


__all__ = ["NEAR_RADIUS_M", "NearbyRepository", "SOURCES", "TYPES", "UTILITIES", "WHY_KEYS", "WORK_KINDS",
           "WORK_STATUSES", "default_kind", "default_service"]
