"""«Штаб ведомств» для шлюза R01 (kind="service"): make_service(db_path).handle(...) -> {"status", "headers", "body"}.

Маршруты (префикс /api/civic/v2; CONTRACT §7):
  GET  /agencies                         все: профили 20 служб (§5.4) с названиями R08; сотруднику — ещё шаблоны кризисов
  GET  /agencies/board?days&district&service   сотрудник: табло служб (metrics.py); service= — открытые обращения службы
  GET  /agencies/joint?days&district     сотрудник: совместные обращения (две и более служб)
  GET  /agencies/handoffs?days&district  сотрудник: журнал передач, пары «откуда → куда», передачи по кругу
  GET  /incidents?status&district        все: кризисы (жителю — публичная часть, сотруднику — с задачами)
  GET  /incidents/{id}                   все: кризис + форма зоны для карты (geometry, bbox)
  GET  /incidents/updates?since&district&yard   житель: публичные обновления кризисов его зоны (X-Birge-Device)
  POST /incidents                        сотрудник: новый кризис {kind, title_ru?, title_kk?, zone, tasks?, update?}
  POST /incidents/{id}/task              сотрудник: {service, text_ru, text_kk} — новая задача; {task_id, status} — статус
  POST /incidents/{id}/update            сотрудник: {text_ru, text_kk, public}
  POST /incidents/{id}/close             сотрудник: {result_ru, result_kk}

Сотрудник — сессия R02 (principal от шлюза) + для записи X-CSRF-Token и свой Origin (как R09, R13, R15 S05).
Ответ ошибки — {"error": код, "message": текст по-русски, "field"?: поле}.
Жителю не отдаём: задачи служб, заметки штаба, журнал, пометки модерации, роли сотрудников.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from urllib.parse import parse_qs

from . import metrics as calc
from . import crisis, geo, profiles, sources
from .store import AgencyStore, Conflict, NotFound, iso, parse_iso

PREFIX = "/api/civic/v2"
DAYS_DEFAULT, DAYS_MAX = 30, 365
ID_RE = re.compile(r"inc-[a-z0-9-]{4,40}\Z")
TASK_ID_RE = re.compile(r"t-[a-z0-9-]{4,40}\Z")
DEVICE_RE = re.compile(r"[A-Za-z0-9._:-]{8,128}\Z")
YARD_RE = re.compile(r"yard-[0-9]{1,15}\Z")
LANGS = ("ru", "kk")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.field = status, code, message, field


def _reply(status: int, body: dict) -> dict:
    return {"status": status, "headers": {}, "body": body}


def _header(context, name: str):
    headers = (context or {}).get("headers") or {}
    return headers.get(name.lower()) or headers.get(name)


def _is_staff(principal) -> bool:
    if principal is None:
        return False
    flag = getattr(principal, "is_staff", None)
    if isinstance(flag, bool):
        return flag
    role = getattr(principal, "role", None) or (principal.get("role") if isinstance(principal, dict) else None)
    return role in ("editor", "admin", "staff")


def _role(principal) -> str:
    """Кто сделал действие в журнале штаба — только роль (CONTRACT §10), без логина и имени."""
    role = getattr(principal, "role", None) or (principal.get("role") if isinstance(principal, dict) else None)
    return str(role or "staff")[:32]


class AgencyService:
    def __init__(self, store: AgencyStore, *, demo: bool | None = None):
        self.store = store
        self.demo = demo

    # ------------------------------------------------------------------ вход
    def handle(self, method, path, query=None, body=None, principal=None, context=None):
        try:
            return self._route(method.upper(), path, query, body, principal, context or {})
        except ApiError as exc:
            out = {"error": exc.code, "message": exc.message}
            if exc.field:
                out["field"] = exc.field
            return _reply(exc.status, out)
        except crisis.InputError as exc:
            return _reply(exc.status, {"error": exc.code, "message": exc.message, "field": exc.field})
        except Conflict as exc:
            out = {"error": exc.code, "message": exc.message}
            if exc.current is not None:
                out["current"] = exc.current
            return _reply(409, out)
        except (NotFound, LookupError):
            return _reply(404, {"error": "not_found", "message": "Кризис или задача не найдены."})

    def _route(self, method, path, query, body, principal, context):
        rel = path[len(PREFIX):] if path.startswith(PREFIX) else path
        rel = rel.split("?", 1)[0]
        parts = [p for p in rel.strip("/").split("/") if p]
        q = self._query(query)
        body = body if isinstance(body, dict) else {}
        if not parts or parts[0] not in ("agencies", "incidents"):
            return None
        if parts[0] == "agencies":
            if method != "GET":
                raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
            if parts == ["agencies"]:
                return self.list_agencies(principal)
            if len(parts) == 2 and parts[1] in ("board", "joint", "handoffs"):
                self._require_staff(principal, context, unsafe=False)
                return {"board": self.board, "joint": self.joint, "handoffs": self.handoffs}[parts[1]](q)
            raise ApiError(404, "not_found", "Адрес API не найден.")
        # incidents
        if parts == ["incidents"]:
            if method == "GET":
                return self.list_incidents(q, principal)
            if method == "POST":
                self._require_staff(principal, context, unsafe=True)
                return self.create_incident(body, principal)
            raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
        if parts == ["incidents", "updates"]:
            if method != "GET":
                raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
            return self.resident_updates(q, context)
        if len(parts) >= 2 and not ID_RE.match(parts[1]):
            raise LookupError(parts[1])
        if len(parts) == 2:
            if method != "GET":
                raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
            return self.get_incident(parts[1], principal)
        if len(parts) == 3 and parts[2] in ("task", "update", "close"):
            if method != "POST":
                raise ApiError(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
            self._require_staff(principal, context, unsafe=True)
            return {"task": self.task, "update": self.update, "close": self.close}[parts[2]](parts[1], body, principal)
        raise ApiError(404, "not_found", "Адрес API не найден.")

    @staticmethod
    def _query(query) -> dict:
        if isinstance(query, bytes):
            query = query.decode("utf-8", "replace")
        if isinstance(query, str):
            query = parse_qs(query.lstrip("?"), keep_blank_values=True)
        out = {}
        for key, value in (query or {}).items():
            if isinstance(value, (list, tuple)):
                value = value[-1] if value else ""
            out[str(key)] = "" if value is None else str(value)
        return out

    @staticmethod
    def _require_staff(principal, context, *, unsafe: bool):
        if context.get("host_allowed") is False:
            raise ApiError(403, "forbidden_host", "Откройте интерфейс через адрес этого сервера.")
        if principal is None:
            raise ApiError(401, "unauthenticated", "Войдите как сотрудник акимата.")
        if not _is_staff(principal):
            raise ApiError(403, "forbidden", "Раздел доступен только сотрудникам акимата.")
        if unsafe:
            if context.get("is_same_origin") is False:
                raise ApiError(403, "cross_origin", "Запрос с чужого сайта отклонён.")
            check = getattr(principal, "check_csrf", None)
            # Нет проверки CSRF у principal (другой формат сессии) — отказ, а не пропуск (R15 S05).
            if not callable(check) or not check(_header(context, "X-CSRF-Token")):
                raise ApiError(403, "csrf_failed", "Сессия устарела. Обновите страницу.")

    @staticmethod
    def _days(q: dict) -> int:
        raw = q.get("days") or ""
        if raw == "":
            return DAYS_DEFAULT
        if not raw.isdigit() or not 1 <= int(raw) <= DAYS_MAX:
            raise ApiError(400, "bad_request", f"days: целое число от 1 до {DAYS_MAX}.", "days")
        return int(raw)

    @staticmethod
    def _district(q: dict) -> str | None:
        value = q.get("district") or ""
        if value in ("", "all"):
            return None
        if value not in geo.DISTRICTS:
            raise ApiError(400, "bad_request", "Неизвестный район.", "district")
        return value

    def _now(self) -> datetime:
        return self.store.now().astimezone(calc.ASTANA)

    def _records(self, now: datetime) -> tuple[list[dict], str]:
        return sources.load(self.store.db_path, now=now, demo=self.demo)

    # ------------------------------------------------------------------ службы и табло
    def list_agencies(self, principal) -> dict:
        body = {"services": profiles.all_profiles(), "kinds": profiles.kinds(),
                "note": "Общие названия служб из таблицы акимата (R08); реальные организации не указаны."}
        if _is_staff(principal):
            body["templates"] = crisis.templates_view()
            body["districts"] = [{"id": d, **geo.DISTRICT_NAMES[d]} for d in geo.DISTRICTS]
            # Дворы R12 для зоны «отдельные дворы» (без контуров: форма — в GET incidents/{id}).
            body["yards"] = sorted(({"id": y["id"], "label_ru": y["label_ru"], "label_kk": y["label_kk"],
                                     "district": y["district"]} for y in geo.yards().values() if y["district"]),
                                   key=lambda y: (y["district"], y["label_ru"], y["id"]))
        return _reply(200, body)

    def board(self, q: dict) -> dict:
        days, district = self._days(q), self._district(q)
        service = q.get("service") or None
        if service is not None and service not in profiles.PROFILES:
            raise ApiError(400, "bad_request", "Неизвестная служба.", "service")
        now = self._now()
        records, source = self._records(now)
        lookup = sources.r08_lookup()
        body = calc.board(records, now, days=days, district=district, lookup=lookup)
        body["source"] = source
        body["profiles"] = profiles.all_profiles()
        body["method"] = METHOD
        # Вывоз после дел жителей, поддержанных акиматом (R16) — задачи службы (обычно «Оператор вывоза мусора»).
        tasks = sources.pickups(self.store.db_path, district)
        counts: dict[str, int] = {}
        for task in tasks:
            counts[task["service"]] = counts.get(task["service"], 0) + 1
        body["pickups"] = counts
        if service is not None:
            body["service"] = service
            body["items"] = self._service_items(records, now, service, district, lookup)
            body["pickup_items"] = [t for t in tasks if t["service"] == service]
        return _reply(200, body)

    @staticmethod
    def _service_items(records, now, service, district, lookup) -> list[dict]:
        """Открытые обращения службы — для списка под строкой табло (без текстов жителей)."""
        items = []
        for record in calc._usable(records, district):
            parts = calc.parts_of(record, lookup)
            part = next((p for p in parts if p["service"] == service), None)
            if part is None or part["status"] in calc.PART_CLOSED:
                continue
            target = record.get("target") or {}
            items.append({"id": record.get("id"), "code": record.get("code"), "category": record.get("category"),
                          "subtopic": record.get("subtopic"), "district": record.get("district"),
                          "created_at": record.get("created_at"), "status": record.get("status"),
                          "part": part, "joint": len(parts) >= 2, "tab": calc.inbox_tab(record, now),
                          "deadline": calc.deadline_state(record, now),
                          "overdue_fix": calc.fix_overdue(record, now),
                          "target": {k: target.get(k) for k in ("kind", "id", "label_ru", "label_kk", "approximate")
                                     if k in target},
                          "demo": bool(record.get("demo"))})
        rank = {"overdue": 0, "reopened": 1, "new": 2, "in_progress": 3, "waiting_check": 4}
        items.sort(key=lambda x: (rank.get(x["tab"], 5), x["created_at"] or ""))
        return items[:100]

    def joint(self, q: dict) -> dict:
        days, district = self._days(q), self._district(q)
        now = self._now()
        records, source = self._records(now)
        body = calc.joint(records, now, days=days, district=district, lookup=sources.r08_lookup())
        body["source"] = source
        return _reply(200, body)

    def handoffs(self, q: dict) -> dict:
        days, district = self._days(q), self._district(q)
        now = self._now()
        records, source = self._records(now)
        body = calc.handoff_log(records, now, days=days, district=district)
        body["source"] = source
        return _reply(200, body)

    # ------------------------------------------------------------------ кризисы: чтение
    def list_incidents(self, q: dict, principal) -> dict:
        status = q.get("status") or "all"
        if status not in ("active", "closed", "all"):
            raise ApiError(400, "bad_request", "status: active, closed или all.", "status")
        district = self._district(q)
        rows = self.store.list(status=None if status == "all" else status, district=district)
        staff = _is_staff(principal)
        items = [crisis.staff_view(r) if staff else crisis.public_view(r) for r in rows]
        return _reply(200, {"items": items, "counts": {"active": sum(1 for r in rows if r["status"] == "active"),
                                                       "closed": sum(1 for r in rows if r["status"] == "closed")},
                            "status": status, "district": district})

    def get_incident(self, incident_id: str, principal) -> dict:
        incident = self.store.get(incident_id)
        if _is_staff(principal):
            view = crisis.staff_view(incident, journal=self.store.journal(incident_id), with_geometry=True)
        else:
            view = crisis.public_view(incident, with_geometry=True)
        return _reply(200, {"incident": view})

    def resident_updates(self, q: dict, context) -> dict:
        """Обновления кризисов для зоны жителя: район/двор из запроса + двор R16 и подписки R08 по устройству."""
        since = q.get("since") or None
        if since is not None and parse_iso(since) is None and parse_iso(since.replace(" ", "+")) is not None:
            since = since.replace(" ", "+")   # «+05:00» без кодирования в адресе приходит пробелом
        if since is not None and parse_iso(since) is None:
            raise ApiError(400, "bad_request", "since: дата и время ISO 8601.", "since")
        districts, yards = set(), set()
        district = self._district(q)
        if district:
            districts.add(district)
        yard = q.get("yard") or ""
        if yard:
            if not YARD_RE.match(yard):
                raise ApiError(400, "bad_request", "yard: id двора yard-<число>.", "yard")
            yards.add(yard)
        device = _header(context, "X-Birge-Device") or q.get("device_id") or None
        if device is not None and (not isinstance(device, str) or not DEVICE_RE.match(device)):
            raise ApiError(400, "bad_request", "X-Birge-Device: строка 8–128 символов.", "device_id")
        if device:
            more_d, more_y = device_places(device)
            districts |= more_d
            yards |= more_y
        items = resident_feed(self.store, districts, yards, since)
        return _reply(200, {"items": items, "zone_known": bool(districts or yards), "since": since})

    # ------------------------------------------------------------------ кризисы: запись (сотрудник)
    def create_incident(self, body: dict, principal) -> dict:
        kind = body.get("kind")
        if kind not in crisis.TEMPLATES:
            raise crisis.InputError("kind", "Выберите вид кризиса.")
        tpl = crisis.TEMPLATES[kind]
        title_ru = crisis.clean_text(body.get("title_ru"), field="title_ru", high=crisis.TITLE_MAX, required=False)
        title_kk = crisis.clean_text(body.get("title_kk"), field="title_kk", high=crisis.TITLE_MAX, required=False)
        zone, district = crisis.parse_zone(body.get("zone"))
        tasks = crisis.parse_tasks(body.get("tasks")) if "tasks" in body else [
            {"service": s, "text_ru": ru, "text_kk": kk, "status": "todo"} for s, ru, kk in tpl["tasks"]]
        # Одно активное событие на зону: второй «Буран в Нуре» путал бы жителей и табло.
        for other in self.store.list(status="active", district=district):
            if other["kind"] == kind and other["zone"] == zone:
                raise Conflict("duplicate", "Такой кризис в этой зоне уже ведётся — откройте его.", other["id"])
        update = body.get("update") if isinstance(body.get("update"), dict) else None
        texts = None
        if update:
            texts = self._texts(update, public=True)
        incident, _created = self.store.create(
            kind=kind, title_ru=title_ru or tpl["title_ru"], title_kk=title_kk or tpl["title_kk"], zone=zone,
            # Демо-сборка (CIVIC_DEMO=1) — стенд для показа: созданный на нём кризис тоже «Пример» (demo: true).
            district=district, tasks=tasks, by_role=_role(principal), demo=bool(self.demo))
        if texts:
            incident = self.store.add_update(incident["id"], text_ru=texts["ru"], text_kk=texts["kk"], public=True,
                                             by_role=_role(principal), moderation=texts["moderation"])
        return _reply(201, {"incident": crisis.staff_view(incident, journal=self.store.journal(incident["id"]),
                                                          with_geometry=True)})

    def task(self, incident_id: str, body: dict, principal) -> dict:
        task_id = body.get("task_id") or body.get("id")
        if task_id is not None:
            if not isinstance(task_id, str) or not TASK_ID_RE.match(task_id):
                raise LookupError(task_id)
            status = body.get("status")
            if status not in ("todo", "doing", "done"):
                raise crisis.InputError("status", "Статус задачи: todo, doing или done.")
            expected = body.get("expected") if body.get("expected") in ("todo", "doing", "done") else None
            incident = self.store.set_task(incident_id, task_id, status=status, by_role=_role(principal),
                                           expected=expected)
        else:
            if body.get("service") not in profiles.PROFILES:
                raise crisis.InputError("service", "Выберите службу из справочника.")
            ru = crisis.clean_text(body.get("text_ru"), field="text_ru", high=200, required=False)
            kk = crisis.clean_text(body.get("text_kk"), field="text_kk", high=200, required=False)
            if not ru and not kk:
                raise crisis.InputError("text_ru", "Опишите задачу хотя бы на одном языке.")
            incident = self.store.add_task(incident_id, service=body["service"], text_ru=ru or kk, text_kk=kk or ru,
                                           by_role=_role(principal))
        return _reply(200, {"incident": crisis.staff_view(incident, journal=self.store.journal(incident_id))})

    @staticmethod
    def _texts(body: dict, *, public: bool, prefix: str = "text_") -> dict:
        ru = crisis.clean_text(body.get(prefix + "ru"), field=prefix + "ru", required=False)
        kk = crisis.clean_text(body.get(prefix + "kk"), field=prefix + "kk", required=False)
        if public and (not ru or not kk):
            # Жители зоны читают на своём языке: публичное обновление — на обоих (CONTRACT §5.5, сцена 9).
            raise crisis.InputError(prefix + ("ru" if not ru else "kk"),
                                    "Для жителей напишите обновление на двух языках: ҚАЗ и РУС.")
        if not ru and not kk:
            raise crisis.InputError(prefix + "ru", "Напишите текст хотя бы на одном языке.")
        moderation = crisis.check_public_texts({"ru": ru, "kk": kk}) if public else None
        return {"ru": ru, "kk": kk, "moderation": moderation}

    def update(self, incident_id: str, body: dict, principal) -> dict:
        public = body.get("public", True) is not False
        texts = self._texts(body, public=public)
        incident = self.store.add_update(incident_id, text_ru=texts["ru"], text_kk=texts["kk"], public=public,
                                         by_role=_role(principal), moderation=texts["moderation"])
        return _reply(200, {"incident": crisis.staff_view(incident, journal=self.store.journal(incident_id))})

    def close(self, incident_id: str, body: dict, principal) -> dict:
        texts = self._texts(body, public=True, prefix="result_")
        incident = self.store.close(incident_id, result_ru=texts["ru"], result_kk=texts["kk"],
                                    by_role=_role(principal), moderation=texts["moderation"])
        return _reply(200, {"incident": crisis.staff_view(incident, journal=self.store.journal(incident_id),
                                                          with_geometry=True)})


# Метод расчёта табло — коротко для ответа API и DELIVERY (подробно — шапка metrics.py).
METHOD = {
    "unit": "обращение (жалоба), дубли не считаются",
    "open": "открытая часть службы сейчас (не done, не rejected), любой давности",
    "overdue": "открытая часть, обращение во вкладке R09 «Просрочено» (срок ответа прошёл без ответа или прошла "
               "обещанная дата обновления); передача срок не обнуляет; в итогах то же — overdue_answer",
    "overdue_fix": "открытая часть, срок ИСПРАВЛЕНИЯ R08 прошёл (ui.civic_akim.deadlines.due, демо-норматив R08); "
                   "в итогах — обращения new/accepted/in_progress с прошедшим сроком, как kpi.overdue «Картины дня»; "
                   "нет R08 — null",
    "period": "received, median_answer_days, fixed, verified, returned, joint — обращения, поданные за days дней; "
              "передачи — по времени передачи",
    "median_answer_days": "медиана рабочих дней РК (календарь R09) от подачи до первого ответа; только ведущая служба",
    "verified_share": "verified / fixed; нет fixed — null",
    "returned": "ведущая служба; у обращения был возврат жителями (reopen_count > 0)",
}


# ---------------------------------------------------------------------- жители: зона и лента
def device_places(device: str) -> tuple[set, set]:
    """(районы, дворы) жителя по устройству — только чтение у соседей; модуля нет — пусто.

    R16: дворы «Я живу здесь» (имена функций ниже — по prompt R16, сверка в INTEGRATION.txt);
    R08: подписки «Рядом» на район (ui.civic_akim.nearby.subscriptions).
    """
    districts, yards = set(), set()
    try:
        import importlib
        together = importlib.import_module("ui.civic_together")
        for name in ("yards_of_device", "device_yards", "my_yards", "yards_for_device"):
            fn = getattr(together, name, None)
            if callable(fn):
                for item in fn(device) or []:
                    yid = item.get("id") if isinstance(item, dict) else item
                    if isinstance(yid, str) and YARD_RE.match(yid):
                        yards.add(yid)
                break
    except Exception:  # noqa: BLE001 — R16 нет в сборке
        pass
    try:
        from ui.civic_akim.nearby import subscriptions  # type: ignore
        for sub in subscriptions(device) or []:
            if sub.get("scope") == "district" and sub.get("id") in geo.DISTRICTS:
                districts.add(sub["id"])
    except Exception:  # noqa: BLE001 — R08 нет или устройство без подписок
        pass
    return districts, yards


def resident_feed(store: AgencyStore, districts: set, yards: set, since: str | None, limit: int = 30) -> list[dict]:
    if not districts and not yards:
        return []
    out, cache = [], {}
    for item in store.public_updates_since(since, limit=200):
        incident = cache.get(item["incident_id"])
        if incident is None:
            incident = cache[item["incident_id"]] = {"zone": item["zone"]}
        if not crisis.in_zone(incident, districts, yards):
            continue
        out.append({"id": item["id"], "at": item["at"], "kind": item["kind"], "incident_id": item["incident_id"],
                    "incident_kind": item["incident_kind"], "title_ru": item["incident_title_ru"],
                    "title_kk": item["incident_title_kk"], "text_ru": item["text_ru"], "text_kk": item["text_kk"],
                    "district": item["district"], "status": item["incident_status"], "demo": item["incident_demo"]})
        if len(out) >= limit:
            break
    return out


def make_service(db_path, *, clock=None, demo: bool | None = None) -> AgencyService:
    """Сервис на базе шлюза. demo=None — по CIVIC_DEMO=1: тогда засевается пример кризиса (если нет демо-мира R02).

    Один сервис на базу в процессе: шлюз R01 и соседи (R08 neighbors.py зовёт make_service, если шлюз ещё не создал
    сервис) получают тот же экземпляр. Иначе второй вызов заново засеял бы демо-кризисы и стёр правки оператора
    посреди показа. Свои часы (clock) — только в тестах: тогда всегда новый сервис.
    """
    import os
    from . import api_state
    current = api_state.current()
    if clock is None and current is not None and current.store.db_path == str(db_path):
        return current
    store = AgencyStore(db_path, clock=clock) if clock else AgencyStore(db_path)
    demo_flag = (os.environ.get("CIVIC_DEMO") == "1") if demo is None else bool(demo)
    service = AgencyService(store, demo=demo_flag)
    if demo_flag and os.environ.get("CIVIC_DEMO_WORLD") != "1":
        from .demo import seed_demo_incidents
        seed_demo_incidents(store)
    api_state.register(service)
    return service
