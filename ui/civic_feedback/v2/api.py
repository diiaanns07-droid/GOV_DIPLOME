"""HTTP-слой жалоб v2: /api/civic/v2/... (CONTRACT §7, владелец R09).

Тот же конверт, что у v1 и шлюза R01: {"status", "headers", "body": {"ok", "data"|"error"}}.
handle(...) возвращает None для чужих путей — шлюз может опрашивать сервисы по очереди.

Маршруты (подключает R01 в ui/web_server.py, см. research/round-14-results/R09/INTEGRATION.txt):
  GET  /categories                       категории v2, сроки ответа, уровни тепловой карты
  POST /complaints                       новая жалоба (заголовок X-Birge-Device)
  GET  /complaints?bbox&since&category&status&days   список для карты (без текстов)
  GET  /complaints/mine                  «Мои обращения» этого устройства (свои тексты)
  GET  /complaints/events?after=N        события created/metoo/status/duplicate (для R07)
  GET  /complaints/summary?target_id&category&days   сколько человек сообщили о цели
  GET  /complaints/place?lon&lat         запасное «примерное место» (ячейка ~150 м)
  GET  /complaints/{id}                  одна жалоба (житель — без текста; автор и акимат — с текстом)
  POST /complaints/{id}/metoo            «Я тоже» (одно на устройство)
  POST /complaints/{id}/status           смена статуса (только сотрудник)
  POST /complaints/{id}/duplicate        отметить дублем {of} (только сотрудник)
Волны 1–2 (POLISH_WAVE.md, POLISH_WAVE_2.md):
  GET  /complaints/changes?since=ISO     «Что изменилось с вашим участием» (устройство)
  POST /complaints/{id}/verify           житель проверяет ремонт {answer: yes|no|cant} (автор и «Я тоже»)
  POST /complaints/{id}/passport         паспорт решения (сотрудник): service, next_step, fix_eta, delay_*
  POST /complaints/{id}/update           одно обновление всем «Я тоже» {text} (сотрудник)
  POST /complaints/{id}/unduplicate      «Это разные проблемы» — разъединить (сотрудник)
  POST /complaints/{id}/photos           начать загрузку фото {kind: resident|after, size}
  POST /complaints/{id}/photos/{upload}  часть фото {offset, data: base64} (≤ 36 000 байт)
  GET  /complaints/{id}/photos/{photo}   фото data:URL — акимат; автор — свои и «после»; «Я тоже» — «после»
  POST /complaints/{id}/status           + what_done, photos при status=fixed («служба сообщила об устранении»)
  POST /complaints/{id}/unsubscribe      «Отписаться» от «Я тоже» (голос остаётся, обновлений нет)
  GET  /complaints/merged?target_id      что объединено с жалобами цели: дубли и «Я тоже» с текстом (сотрудник, R04)
  POST /complaints/{id}/separate         «Это разные проблемы»: id дубля (c-…) или «Я тоже» (mt-…) (сотрудник, R04)
  GET  /complaints/inbox?tab=            акимат: цели с открытыми обращениями по вкладкам (new, in_progress,
                                         waiting_check, overdue, reopened) — экран «Обращения» (#complaints)
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import timedelta
from urllib.parse import parse_qs, unquote, urlsplit

import base64
import binascii

from . import categories, lifecycle
from . import record as rec
from .record import RecordError
from .store import ComplaintStore, Conflict, LimitError, NotFound

LOGGER = logging.getLogger(__name__)
API_PREFIX = "/api/civic/v2"
DEVICE_HEADER = "X-Birge-Device"
MAX_BODY = 60 * 1024   # часть фото 36 000 байт в base64 ≈ 48 КБ; шлюз R01 пропускает ≤ 64 КБ


class ApiError(Exception):
    def __init__(self, status, code, message, fields=None, headers=None):
        super().__init__(message)
        self.status, self.code, self.message, self.fields, self.headers = status, code, message, fields, headers


def _ok(status, data):
    return {"status": status, "headers": {"Cache-Control": "no-store"}, "body": {"ok": True, "data": data}}


def _error(exc: ApiError):
    error = {"code": exc.code, "message": exc.message}
    if exc.fields:
        error["fields"] = exc.fields
    headers = {"Cache-Control": "no-store", **(exc.headers or {})}
    return {"status": exc.status, "headers": headers, "body": {"ok": False, "error": error}}


def _header(context, name):
    headers = (context or {}).get("headers") or {}
    lowered = name.lower()
    try:
        for key, value in headers.items():
            if str(key).lower() == lowered:
                return value
    except AttributeError:
        return None
    return None


def _is_staff(principal) -> bool:
    if principal is None:
        return False
    if isinstance(principal, dict):
        return bool(principal.get("is_staff"))
    return bool(getattr(principal, "is_staff", False))


def _actor(principal) -> str | None:
    if isinstance(principal, dict):
        return principal.get("username") or principal.get("name")
    return getattr(principal, "username", None)


class ComplaintsV2Service:
    def __init__(self, store: ComplaintStore):
        self.store = store

    # ------------------------------------------------------------ вход
    def handle(self, method, path, query, body, principal, context):
        method = (method or "").upper()
        if not isinstance(path, str):
            return None
        raw = urlsplit(path).path
        if not raw.startswith(API_PREFIX + "/"):
            return None
        parts = [unquote(p) for p in raw[len(API_PREFIX):].split("/") if p]
        if not parts or parts[0] not in ("categories", "complaints"):
            return None
        context = context if isinstance(context, dict) else {}
        try:
            if context.get("host_allowed") is False:
                raise ApiError(403, "host_not_allowed", "Откройте Birge через адрес этого сервера.")
            if method == "POST" and context.get("is_same_origin") is False:
                raise ApiError(403, "cross_origin", "Запрос с чужого сайта отклонён.")
            params = self._query(query, path)
            handler, args = self._route(method, parts)
            return handler(*args, params=params, body=body, principal=principal, context=context)
        except ApiError as exc:
            return _error(exc)
        except LimitError as exc:
            minutes = max(1, (exc.retry_after_s + 59) // 60)
            return _error(ApiError(429, "too_many", f"Слишком много обращений подряд. Повторите через {minutes} мин.",
                                   headers={"Retry-After": str(exc.retry_after_s)}))
        except NotFound as exc:
            return _error(ApiError(404, "not_found", str(exc)))
        except Conflict as exc:
            return _error(ApiError(409, "conflict", str(exc), exc.fields))
        except RecordError as exc:
            return _error(ApiError(422, "invalid", str(exc), exc.fields))
        except sqlite3.Error:
            LOGGER.exception("complaints v2 storage error")
            return _error(ApiError(503, "storage_unavailable", "Хранилище временно недоступно. Повторите позже."))
        except Exception:  # наружу только конверт, без traceback
            LOGGER.exception("complaints v2 handler failed")
            return _error(ApiError(500, "internal_error", "Не удалось выполнить запрос. Повторите."))

    def _route(self, method, parts):
        def need(allowed, handler, *args):
            if method not in allowed and not (method == "HEAD" and "GET" in allowed):
                raise ApiError(405, "method_not_allowed", "Метод не поддерживается.",
                               headers={"Allow": ", ".join(allowed)})
            return handler, args

        if parts == ["categories"]:
            return need(("GET",), self._categories)
        if parts == ["complaints"]:
            return need(("GET", "POST"), self._list if method in ("GET", "HEAD") else self._create)
        if len(parts) == 2:
            special = {"mine": self._mine, "events": self._events, "summary": self._summary, "place": self._place,
                       "changes": self._changes, "inbox": self._inbox, "merged": self._merged}
            if parts[1] in special:
                return need(("GET",), special[parts[1]])
            return need(("GET",), self._detail, parts[1])
        if len(parts) == 3:
            action = {"metoo": self._metoo, "status": self._status, "duplicate": self._duplicate,
                      "verify": self._verify, "passport": self._passport, "update": self._update,
                      "unduplicate": self._unduplicate, "photos": self._photo_start,
                      "unsubscribe": self._unsubscribe, "separate": self._separate}.get(parts[2])
            if action:
                return need(("POST",), action, parts[1])
        if len(parts) == 4 and parts[2] == "photos":
            if parts[3].startswith("u-"):
                return need(("POST",), self._photo_chunk, parts[1], parts[3])
            return need(("GET",), self._photo_get, parts[1], parts[3])
        raise ApiError(404, "not_found", "Адрес не найден.")

    # ------------------------------------------------------------ разбор
    @staticmethod
    def _query(query, path) -> dict:
        if query is None:
            query = urlsplit(path).query
        if isinstance(query, bytes):
            query = query.decode()
        if isinstance(query, str):
            query = parse_qs(query)
        result = {}
        for key, value in (query or {}).items():
            if isinstance(value, (list, tuple)):
                value = value[0] if value else ""
            result[str(key)] = "" if value is None else str(value)
        return result

    @staticmethod
    def _json(body) -> dict:
        if isinstance(body, dict):
            return body
        if isinstance(body, (bytes, str)) and body:
            if len(body) > MAX_BODY:
                raise ApiError(413, "too_large", "Слишком большой запрос.")
            try:
                data = json.loads(body)
            except ValueError:
                raise ApiError(400, "invalid_body", "Ожидается JSON-объект.") from None
            if isinstance(data, dict):
                return data
        if body in (None, b"", ""):
            return {}
        raise ApiError(400, "invalid_body", "Ожидается JSON-объект.")

    @staticmethod
    def _device(context, body=None):
        return _header(context, DEVICE_HEADER) or (body or {}).get("device_id")

    @staticmethod
    def _require_staff(principal, context):
        if not _is_staff(principal):
            raise ApiError(403, "forbidden", "Действие доступно только сотрудникам акимата.")
        check = getattr(principal, "check_csrf", None)
        # R15-S05: нет проверки CSRF у principal (другой формат сессии) — отказ, а не пропуск.
        if not callable(check) or not check(_header(context, "X-CSRF-Token")):
            raise ApiError(403, "csrf_failed", "Сессия устарела. Обновите страницу.")

    @staticmethod
    def _bbox(value):
        if not value:
            return None
        try:
            parts = [float(v) for v in value.split(",")]
        except ValueError:
            raise ApiError(422, "invalid", "Неверная область.", {"bbox": "lon_min,lat_min,lon_max,lat_max"}) from None
        if len(parts) != 4 or parts[0] > parts[2] or parts[1] > parts[3]:
            raise ApiError(422, "invalid", "Неверная область.", {"bbox": "lon_min,lat_min,lon_max,lat_max"})
        return parts

    def _view(self, record, principal, context):
        if _is_staff(principal):
            return self._staff(record)
        relation = self.store.participant(record["id"], self._device(context)) if self._device(context) else None
        return self._resident(record, relation, self._device(context))

    # ------------------------------------------------------------ проекции волн 1–2
    def _public(self, record):
        """Карта и чужие жители: + уточнение, состояние проверки ремонта и heat_state для R07 (без текстов и имён)."""
        view = rec.public_view(record)
        view["subtopic"] = record.get("subtopic")
        view["resolution"] = lifecycle.public_resolution(record)
        view["heat_state"] = lifecycle.heat_state(record, self.store._now())
        return view

    def _resident(self, record, relation, device):
        """Автор — свой текст; «Я тоже» — как публичная, но с паспортом, обновлениями и проверкой ремонта."""
        if relation is None:
            return self._public(record)
        view = rec.author_view(record) if relation == "author" else self._public(record)
        if relation == "author":
            view.update({"subtopic": record.get("subtopic"), "heat_state": lifecycle.heat_state(record, self.store._now())})
            view["photos"] = [p for p in record.get("photos") or [] if p.get("kind") == "resident"]
            view["emergency"] = record.get("emergency")
        else:
            view["steps"] = rec.resident_steps(record)
        view["relation"] = relation
        view["resolution"] = lifecycle.participant_resolution(record)
        view["passport"] = lifecycle.passport_view(record, self.store._now(), self.store.assignee_lookup)
        view["passport"].pop("decision_choice", None)   # выбор акима — служебное (R15-S28: кто выбрал — не наружу)
        view["history"] = lifecycle.history(record)
        # Обновления без имён сотрудников: «что сделали», следующий шаг, сообщения службы.
        view["updates"] = [{"at": u["at"], "kind": u["kind"], "text": u.get("text")} for u in record.get("updates") or []]
        view["can_verify"] = bool(device) and self.store.can_verify(record["id"], device)
        return view

    def _staff(self, record):
        view = rec.staff_view(record)
        # LOCAL_FINAL №1: у ответа сотруднику то же поле «сколько человек сообщили», что у публичного.
        view["reporters"] = rec.reporters(record)
        now = self.store._now()
        view["heat_state"] = lifecycle.heat_state(record, now)
        view["passport_view"] = lifecycle.passport_view(record, now, self.store.assignee_lookup,
                                                        getattr(self.store, "decision_lookup", None))
        view["history"] = lifecycle.history(record)
        view["deadline"] = lifecycle.deadline(record, now)
        # «Увидят N человек» до действия (R11 §2.3: fix.will_see) — автор и «Я тоже» без «Отписаться».
        view["subscribers"] = self.store.subscribers(record["id"])
        view["inbox_tab"] = lifecycle.inbox_tab(record, now)
        return view

    # ------------------------------------------------------------ обработчики
    def _categories(self, *, params, body, principal, context):
        return _ok(200, categories.public_payload())

    def _create(self, *, params, body, principal, context):
        data = self._json(body)
        record, created = self.store.create(data, self._device(context, data))
        return _ok(201 if created else 200, {"complaint": self._resident(record, "author", self._device(context, data)),
                                             "replayed": not created})

    def _list(self, *, params, body, principal, context):
        since = params.get("since") or None
        if params.get("days"):
            try:
                days = max(1, min(int(params["days"]), 365))
            except ValueError:
                raise ApiError(422, "invalid", "Неверный период.", {"days": "число дней"}) from None
            since = self.store._now() - timedelta(days=days)
        category = [c for c in params.get("category", "").split(",") if c] or None
        if category and not all(categories.is_category(c) for c in category):
            raise ApiError(422, "invalid", "Неизвестная категория.", {"category": ",".join(categories.ids())})
        status = [s for s in params.get("status", "").split(",") if s] or None
        if status and not all(s in rec.STATUSES for s in status):
            raise ApiError(422, "invalid", "Неизвестный статус.", {"status": ",".join(rec.STATUSES)})
        items = self.store.list(self._bbox(params.get("bbox")), since, category, status=status,
                                include_duplicates=params.get("duplicates") == "1")
        view = self._staff if _is_staff(principal) else self._public
        return _ok(200, {"items": [view(r) for r in items], "count": len(items),
                         "generated_at": rec.iso(self.store._now())})

    def _mine(self, *, params, body, principal, context):
        items = []
        device = self._device(context)
        for record in self.store.mine(device):
            relation = record.pop("relation")
            view = self._resident(record, relation, device)
            view["place_reporters"] = self.store.place_reporters(record)
            if relation == "metoo":
                view["metoo_at"] = record.get("metoo_at")
            items.append(view)
        return _ok(200, {"items": items, "count": len(items)})

    def _events(self, *, params, body, principal, context):
        try:
            after = int(params.get("after") or 0)
        except ValueError:
            raise ApiError(422, "invalid", "Неверный номер события.", {"after": "целое число"}) from None
        events = self.store.events_since(after)
        return _ok(200, {"events": events, "last": events[-1]["seq"] if events else after})

    def _summary(self, *, params, body, principal, context):
        target_id = params.get("target_id") or ""
        if not target_id or len(target_id) > 100:
            raise ApiError(422, "invalid", "Не указана цель.", {"target_id": "id объекта, участка или двора"})
        category = params.get("category") or None
        if category and not categories.is_category(category):
            raise ApiError(422, "invalid", "Неизвестная категория.", {"category": ",".join(categories.ids())})
        # R15-S06: только ASCII-цифры: str.isdigit() пропускает «²», а int() на нём падает (500).
        raw_days = params.get("days", "")
        days = int(raw_days) if re.fullmatch(r"[0-9]{1,4}", raw_days) else 14
        return _ok(200, self.store.target_summary(target_id, days=max(1, min(days, 90)), category=category))

    def _place(self, *, params, body, principal, context):
        try:
            point = rec.parse_point([float(params.get("lon", "")), float(params.get("lat", ""))])
        except ValueError:
            raise ApiError(422, "invalid", "Неверное место.", {"lon": "число", "lat": "число"}) from None
        target = rec.cell_target(*point)
        return _ok(200, {"target": target, "geometry": {"type": "Polygon",
                                                        "coordinates": [rec.cell_polygon(target["id"])]}})

    def _detail(self, complaint_id, *, params, body, principal, context):
        record = self.store.get(complaint_id) or self.store.get_by_code(complaint_id)
        if record is None:
            raise ApiError(404, "not_found", "Обращение не найдено.")
        # LOCAL_FINAL №1: мастер жителя (шаг «Я тоже») просит ?view=public — тот же ответ, что у любого жителя,
        # даже если в этом браузере уже вошёл сотрудник. Права это не расширяет: публичная проекция — минимум.
        if params.get("view") == "public":
            return _ok(200, {"complaint": self._public(record)})
        return _ok(200, {"complaint": self._view(record, principal, context)})

    def _metoo(self, complaint_id, *, params, body, principal, context):
        data = self._json(body)
        record, result = self.store.metoo(complaint_id, self._device(context, data), note=data.get("note"))
        return _ok(200, {"result": result, "complaint": self._public(record)})

    def _status(self, complaint_id, *, params, body, principal, context):
        self._require_staff(principal, context)
        data = self._json(body)
        record = self.store.set_status(complaint_id, data.get("status"), actor=_actor(principal),
                                       note=data.get("note"), expected=data.get("expected"),
                                       what_done=data.get("what_done"), photos=data.get("photos"))
        return _ok(200, {"complaint": self._staff(record), "notified": self.store.subscribers(record["id"])})

    def _duplicate(self, complaint_id, *, params, body, principal, context):
        self._require_staff(principal, context)
        data = self._json(body)
        if not isinstance(data.get("of"), str):
            raise ApiError(422, "invalid", "Укажите исходное обращение.", {"of": "id обращения"})
        record = self.store.mark_duplicate(complaint_id, data["of"], actor=_actor(principal))
        return _ok(200, {"complaint": rec.staff_view(record)})

    # ------------------------------------------------------------ волны 1–2
    def _changes(self, *, params, body, principal, context):
        since = params.get("since") or None
        if since and rec.parse_iso(since) is None:
            raise ApiError(422, "invalid", "Неверная дата.", {"since": "ISO-дата"})
        data = self.store.changes(self._device(context), since)
        # Подписки «Рядом» (R08, волна 2 п. 4): их обновления — в том же «Что изменилось» (R10 W2-4).
        nearby = self._nearby_updates(self._device(context), since)
        if nearby:
            data["items"] = sorted(data["items"] + nearby, key=lambda e: e.get("at") or "", reverse=True)
        return _ok(200, data)

    def _nearby_updates(self, device, since) -> list[dict]:
        lookup = getattr(self.store, "nearby_lookup", None)
        if lookup is None or not device:
            return []
        try:
            found = lookup(device, since) or []
        except Exception:  # noqa: BLE001 — «Рядом» R08 недоступен: «Что изменилось» по своим жалобам
            LOGGER.warning("nearby updates unavailable", exc_info=True)
            return []
        return [{"id": "nearby." + str(item.get("id")), "kind": "nearby", "at": item.get("updated_at"),
                 "tab": item.get("tab"), "title_ru": item.get("title_ru"), "title_kk": item.get("title_kk"),
                 "demo": bool(item.get("demo"))} for item in found if item.get("updated_at")][:20]

    def _inbox(self, *, params, body, principal, context):
        """Акимат · «Обращения»: цели с открытыми обращениями по вкладкам (R11 IA_WAVE2 §2.5, R01 #complaints)."""
        if not _is_staff(principal):
            raise ApiError(403, "forbidden", "Действие доступно только сотрудникам акимата.")
        tab = params.get("tab") or None
        if tab is not None and tab not in lifecycle.INBOX_TABS:
            raise ApiError(422, "invalid", "Неизвестная вкладка.", {"tab": ",".join(lifecycle.INBOX_TABS)})
        records = self.store.list(status=list(rec.OPEN_STATUSES) + ["fixed"])
        data = lifecycle.inbox(records, self.store._now(), tab)
        data["tab"] = tab
        return _ok(200, data)

    # ------------------------------------------------------------ «Это разные проблемы» (п. 9, R04 + R09)
    def _merged(self, *, params, body, principal, context):
        if not _is_staff(principal):  # тексты жителей — только акимату (чтение: без CSRF, как список)
            raise ApiError(403, "forbidden", "Действие доступно только сотрудникам акимата.")
        target_id = params.get("target_id") or ""
        if not target_id or len(target_id) > 100:
            raise ApiError(422, "invalid", "Не указана цель.", {"target_id": "id объекта, участка или двора"})
        items = self.store.merged(target_id)
        return _ok(200, {"items": items, "count": len(items)})

    def _separate(self, item_id, *, params, body, principal, context):
        self._require_staff(principal, context)
        separated, original = self.store.separate(item_id, actor=_actor(principal))
        return _ok(200, {"complaint": self._staff(separated),
                         "original": self._staff(original) if original else None})

    def _unsubscribe(self, complaint_id, *, params, body, principal, context):
        data = self._json(body)
        result = self.store.unsubscribe(complaint_id, self._device(context, data))
        return _ok(200, {"result": result})

    def _verify(self, complaint_id, *, params, body, principal, context):
        data = self._json(body)
        record, result = self.store.verify(complaint_id, self._device(context, data), data.get("answer"))
        device = self._device(context, data)
        return _ok(200, {"result": result,
                         "complaint": self._resident(record, self.store.participant(record["id"], device), device)})

    def _passport(self, complaint_id, *, params, body, principal, context):
        self._require_staff(principal, context)
        record, notified = self.store.update_passport(complaint_id, self._json(body), actor=_actor(principal))
        return _ok(200, {"complaint": self._staff(record), "notified": notified})

    def _update(self, complaint_id, *, params, body, principal, context):
        self._require_staff(principal, context)
        record, notified = self.store.post_update(complaint_id, self._json(body).get("text"), actor=_actor(principal))
        return _ok(200, {"complaint": self._staff(record), "notified": notified})

    def _unduplicate(self, complaint_id, *, params, body, principal, context):
        self._require_staff(principal, context)
        record = self.store.unmark_duplicate(complaint_id, actor=_actor(principal))
        return _ok(200, {"complaint": self._staff(record)})

    def _photo_start(self, complaint_id, *, params, body, principal, context):
        data = self._json(body)
        kind = data.get("kind")
        if kind == "after":
            self._require_staff(principal, context)
        result = self.store.start_upload(complaint_id, kind, data.get("size"),
                                         device_id=self._device(context, data), actor=_actor(principal))
        return _ok(201, result)

    def _photo_chunk(self, complaint_id, upload_id, *, params, body, principal, context):
        data = self._json(body)
        try:
            chunk = base64.b64decode(data.get("data") or "", validate=True)
        except (binascii.Error, TypeError, ValueError):
            raise ApiError(422, "invalid", "Часть фото повреждена.", {"data": "base64"}) from None
        actor = _actor(principal) if _is_staff(principal) else None
        if actor is not None:
            self._require_staff(principal, context)
        result = self.store.upload_chunk(complaint_id, upload_id, data.get("offset"), chunk,
                                         device_id=self._device(context, data), actor=actor)
        return _ok(201 if result.get("done") else 200, result)

    def _photo_get(self, complaint_id, photo_id, *, params, body, principal, context):
        photo = self.store.get_photo(complaint_id, photo_id)
        if photo is None:
            raise ApiError(404, "not_found", "Фото не найдено.")
        if not _is_staff(principal):
            # Фото жителя — только акимат и сам автор; фото «после» — ещё и «Я тоже» (они проверяют ремонт).
            relation = self.store.participant(complaint_id, self._device(context))
            allowed = relation == "author" or (relation == "metoo" and photo["kind"] == "after")
            if not allowed:
                raise ApiError(403, "forbidden", "Фото видит только служба и автор обращения.")
        encoded = base64.b64encode(photo["data"]).decode("ascii")
        return _ok(200, {"photo": {"id": photo["id"], "kind": photo["kind"], "mime": photo["mime"],
                                   "data_url": f"data:{photo['mime']};base64,{encoded}"}})
