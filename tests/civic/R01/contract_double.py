"""TEST DOUBLE of the civic-v1 store (R02) and feedback (R06) services.

NOT A BACKEND. In-memory only, nothing survives a restart, accounts exist only in
the test process. It exists so that R01 can (a) drive the shell/fallback UI end to
end before R02/R06 deliver and (b) run the same HTTP acceptance suite against the
double and, later, against the real services. Behaviour follows CONTRACT.txt
(PACK_SHA 9c2f5c0); where the contract is silent the choice is marked "double:".
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import hmac
import itertools
import math
import re
import secrets
import threading

KINDS = {"construction", "roadworks", "landscaping", "event"}
STATUSES = {"planned", "in_progress", "completed", "cancelled", "unknown"}
EVIDENCE = {"observed", "derived", "hypothesis", "synthetic"}
PRECISION = {"source", "approximate", "unknown"}
BASIS = {"planned", "contract", "spent", "unknown"}
CATEGORIES = {"roads", "sidewalks", "transport_stops", "lighting", "landscaping", "other"}
PUBLIC_FIELDS = ("schema_version", "id", "city", "kind", "title", "description", "status", "publication",
                 "geometry", "geometry_precision", "schedule", "budget", "responsible", "evidence_type",
                 "source_refs", "evidence_notes", "updated_at", "revision")
EDITABLE = {"kind", "title", "description", "status", "geometry", "geometry_precision", "schedule", "budget",
            "responsible", "evidence_type", "source_refs", "evidence_notes"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COOKIE = "civic_session"


def reply(status, data=None, *, code=None, message=None, fields=None, headers=None):
    if status < 400:
        body = {"ok": True, "data": data}
    else:
        body = {"ok": False, "error": {"code": code, "message": message or code}}
        if fields:
            body["error"]["fields"] = fields
    return {"status": status, "headers": headers or {}, "body": body}


PREFIX = "/api/civic/v1"


def _parts(path):
    """Gateway passes the full path (R02 convention)."""
    if not isinstance(path, str) or not path.startswith(PREFIX + "/"):
        return None
    return path[len(PREFIX) + 1:].split("/")


def _query(query):
    from urllib.parse import parse_qs
    if isinstance(query, dict):
        return query
    return {k: v[-1] for k, v in parse_qs(query or "", keep_blank_values=True).items()}


class Invalid(Exception):
    def __init__(self, fields):
        super().__init__("invalid")
        self.fields = fields


def _date(value, name, fields):
    if value is None:
        return None
    if not isinstance(value, str) or not DATE.match(value):
        fields[name] = "YYYY-MM-DD или null"
        return None
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        fields[name] = "несуществующая дата"
    return value


def _text(value, name, fields, limit, required=False):
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        fields[name] = f"строка до {limit} символов" + (", обязательно" if required else "")
        return ""
    return value.strip()


def _geometry(value, fields):
    if value is None:
        return None
    def point(p):
        return (isinstance(p, list) and len(p) == 2 and all(isinstance(c, (int, float)) and not isinstance(c, bool)
                and math.isfinite(c) for c in p) and -180 <= p[0] <= 180 and -90 <= p[1] <= 90)
    ok = isinstance(value, dict) and set(value) <= {"type", "coordinates"}
    kind = value.get("type") if ok else None
    coords = value.get("coordinates") if ok else None
    if kind == "Point":
        ok = point(coords)
    elif kind == "LineString":
        ok = isinstance(coords, list) and 2 <= len(coords) <= 500 and all(point(p) for p in coords)
    elif kind == "Polygon":
        ok = (isinstance(coords, list) and len(coords) == 1 and isinstance(coords[0], list) and 4 <= len(coords[0]) <= 500
              and all(point(p) for p in coords[0]) and coords[0][0] == coords[0][-1])
    else:
        ok = False
    if not ok:
        fields["geometry"] = "GeoJSON Point/LineString/Polygon в WGS84 или null"
        return None
    return copy.deepcopy(value)


def validate_object(src, *, partial=False):
    """Returns a cleaned dict of editable fields; raises Invalid(fields)."""
    fields, out = {}, {}
    unknown = set(src) - EDITABLE
    if unknown:
        # double: server-owned fields (id, revision, publication, actor...) are ignored, not errors.
        src = {k: v for k, v in src.items() if k in EDITABLE}
    def has(key):
        return key in src or not partial
    if has("title"):
        out["title"] = _text(src.get("title"), "title", fields, 200, required=True)
    if has("description"):
        out["description"] = _text(src.get("description"), "description", fields, 4000)
    if has("evidence_notes"):
        out["evidence_notes"] = _text(src.get("evidence_notes"), "evidence_notes", fields, 2000)
    for key, allowed, default in (("kind", KINDS, None), ("status", STATUSES, "unknown"),
                                  ("evidence_type", EVIDENCE, None), ("geometry_precision", PRECISION, "unknown")):
        if has(key):
            value = src.get(key, default)
            if value not in allowed:
                fields[key] = "одно из: " + ", ".join(sorted(allowed))
            out[key] = value
    if has("geometry"):
        out["geometry"] = _geometry(src.get("geometry"), fields)
    if has("schedule"):
        schedule = src.get("schedule") or {}
        if not isinstance(schedule, dict):
            fields["schedule"] = "объект"
            schedule = {}
        out["schedule"] = {key: _date(schedule.get(key), "schedule." + key, fields)
                           for key in ("planned_start", "original_planned_end", "current_planned_end", "actual_end")}
        out["_schedule_keys"] = set(schedule)
    if has("budget"):
        budget = src.get("budget") or {}
        amount = budget.get("amount_kzt") if isinstance(budget, dict) else None
        if amount is not None and (isinstance(amount, bool) or not isinstance(amount, (int, float))
                                   or not math.isfinite(amount) or amount < 0):
            fields["budget.amount_kzt"] = "неотрицательное конечное число или null"
        basis = budget.get("basis", "unknown") if isinstance(budget, dict) else "unknown"
        if basis not in BASIS:
            fields["budget.basis"] = "planned|contract|spent|unknown"
        source = budget.get("source_id") if isinstance(budget, dict) else None
        out["budget"] = {"amount_kzt": amount, "basis": basis if amount is not None or basis in BASIS else "unknown",
                         "source_id": source if isinstance(source, str) else None}
    if has("responsible"):
        responsible = src.get("responsible") or {}
        out["responsible"] = {key: (_text(responsible.get(key), "responsible." + key, fields, 200) or None)
                              for key in ("organization", "public_contact")}
    if has("source_refs"):
        refs = src.get("source_refs") or []
        if not isinstance(refs, list) or len(refs) > 20:
            fields["source_refs"] = "список до 20 ссылок"
            refs = []
        out["source_refs"] = copy.deepcopy(refs)
    if fields:
        raise Invalid(fields)
    return out


class CivicStoreDouble:
    def __init__(self, clock=None):
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        self.lock = threading.RLock()
        self.objects, self.history, self.users, self.sessions = {}, [], {}, {}
        self.ids = itertools.count(1)

    # --- accounts (test-process only) ---------------------------------------
    def add_editor(self, username, password, name="Редактор (тест)"):
        salt = secrets.token_bytes(16)
        self.users[username] = (salt, hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000), name)

    def _now(self):
        return self.clock().replace(microsecond=0).isoformat()

    def _session(self, context):
        token = (context.get("cookies") or {}).get(COOKIE)
        return self.sessions.get(token) if token else None

    def resolve_principal(self, context):
        session = self._session(context)
        if session:
            return {"role": "editor", "name": session["name"], "csrf": session["csrf"]}
        return {"role": "anonymous", "name": None}

    def _staff(self, context, mutate):
        session = self._session(context)
        if not session:
            return None, reply(401, code="unauthenticated", message="Нужен вход сотрудника.")
        if mutate:
            token = (context.get("headers") or {}).get("x-csrf-token", "")
            # Same rule as R02: reject an explicit cross-origin; absent Origin falls to CSRF.
            if context.get("is_same_origin") is False or not hmac.compare_digest(token, session["csrf"]):
                return None, reply(403, code="csrf_invalid", message="Проверка CSRF не пройдена.")
        return session, None

    # --- DTO ------------------------------------------------------------------
    # Mirrors R02's model (ui/civic_store @6a28de2): the editor works on a staff copy;
    # residents see the public projection captured at the last publish. Editing a
    # published object needs a reason and becomes public only after "publish" again.
    @staticmethod
    def public(item):
        return {key: copy.deepcopy(item[key]) for key in PUBLIC_FIELDS}

    @staticmethod
    def _content(item):
        return {key: item[key] for key in EDITABLE}

    def _staff_item(self, item):
        out = {k: copy.deepcopy(v) for k, v in item.items() if not k.startswith("_")}
        published = item.get("_public")
        out["staff"] = {"has_unpublished_changes": published is None or
                        self._content(published) != self._content(item),
                        "public_item": copy.deepcopy(published),
                        "original_planned_end_locked": bool(item.get("_first_published"))}
        return out

    def _public_history(self, object_id):
        return [{key: entry[key] for key in ("id", "object_id", "revision", "at", "changed_fields", "reason",
                                             "public_actor_label")}
                for entry in self.history if entry["object_id"] == object_id and entry["public"]]

    def seed(self, item):
        """Load a fixture as-is (published), e.g. the coordinator's synthetic object."""
        with self.lock:
            clean = copy.deepcopy(item)
            clean.setdefault("internal_notes", "")
            clean["_first_published"] = clean["publication"] == "published"
            clean["_public"] = self.public(clean) if clean["publication"] == "published" else None
            self.objects[clean["id"]] = clean
            self.history.append({"id": f"h{len(self.history) + 1}", "object_id": clean["id"], "revision": clean["revision"],
                                 "at": clean["updated_at"], "changed_fields": ["seed"], "reason": "Загрузка fixture",
                                 "public_actor_label": "Тестовая загрузка", "public": clean["publication"] == "published"})

    # --- routing ----------------------------------------------------------------
    def handle(self, method, path, query, body, context):
        parts = _parts(path)
        if parts is None:
            return None
        with self.lock:
            try:
                return self._route(method, parts, _query(query), body, context)
            except Invalid as exc:
                return reply(422, code="validation", message="Проверьте поля.", fields=exc.fields)

    def _route(self, method, parts, query, body, context):
        if parts == ["session"] and method == "GET":
            return reply(200, self._session_data(self._session(context)))
        if parts == ["session", "login"] and method == "POST":
            return self._login(body or {})
        if parts == ["session", "logout"] and method == "POST":
            session, error = self._staff(context, True)
            if error:
                return error
            self.sessions = {k: v for k, v in self.sessions.items() if v is not session}
            return reply(200, self._session_data(None), headers={"Set-Cookie": f"{COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict"})
        if parts == ["objects"] and method == "GET":
            return self._list(query, public=True)
        if len(parts) == 2 and parts[0] == "objects" and method == "GET":
            item = self.objects.get(parts[1])
            if not item or not item.get("_public"):
                return reply(404, code="not_found", message="Запись не найдена.")
            return reply(200, {"item": copy.deepcopy(item["_public"]), "history": self._public_history(item["id"])})
        if parts[0] != "staff" or len(parts) < 2 or parts[1] != "objects":
            return None
        session, error = self._staff(context, method == "POST")
        if error:
            return error
        if parts == ["staff", "objects"]:
            return self._list(query, public=False) if method == "GET" else self._create(body or {}, session)
        item = self.objects.get(parts[2])
        if not item:
            return reply(404, code="not_found", message="Запись не найдена.")
        if len(parts) == 3 and method == "GET":
            return reply(200, {"item": self._staff_item(item),
                               "history": [copy.deepcopy(h) for h in self.history if h["object_id"] == item["id"]]})
        if len(parts) == 4 and method == "POST":
            return self._change(item, parts[3], body or {}, session)
        return None

    def _session_data(self, session):
        if not session:
            return {"authenticated": False, "user": None, "csrf_token": None}
        return {"authenticated": True, "user": {"name": session["name"], "role": "editor"}, "csrf_token": session["csrf"]}

    def _login(self, body):
        username, password = body.get("username"), body.get("password")
        record = self.users.get(username) if isinstance(username, str) else None
        if not record or not isinstance(password, str) or not hmac.compare_digest(
                hashlib.pbkdf2_hmac("sha256", password.encode(), record[0], 120_000), record[1]):
            return reply(401, code="invalid_credentials", message="Неверный логин или пароль.")
        token = secrets.token_urlsafe(32)
        session = {"name": record[2], "csrf": secrets.token_urlsafe(24), "user": username}
        self.sessions[token] = session
        return reply(200, self._session_data(session),
                     headers={"Set-Cookie": f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict"})

    def _list(self, query, public):
        if public:
            items = [copy.deepcopy(i["_public"]) for i in self.objects.values() if i.get("_public")]
        else:
            items = [self._staff_item(i) for i in self.objects.values()]
        for key in ("kind", "status"):
            if query.get(key):
                items = [i for i in items if i[key] == query[key]]
        start, end = query.get("from") or None, query.get("to") or None
        if start or end:
            def overlaps(item):
                s = item["schedule"]
                begin, finish = s.get("planned_start"), s.get("current_planned_end")
                if begin is None and finish is None:
                    return False
                return (not end or (begin or finish) <= end) and (not start or (finish or begin) >= start)
            items = [i for i in items if overlaps(i)]
        items.sort(key=lambda i: i["id"])
        offset = int(query.get("cursor") or 0) if str(query.get("cursor") or "0").isdigit() else 0
        page = items[offset:offset + 50]
        next_cursor = str(offset + 50) if offset + 50 < len(items) else None
        return reply(200, {"items": page, "next_cursor": next_cursor})

    def _create(self, body, session):
        clean = validate_object(body)
        clean.pop("_schedule_keys", None)
        object_id = f"astana-obj-{next(self.ids):04d}"
        now = self._now()
        item = {"schema_version": "civic-v1", "id": object_id, "city": "astana", "publication": "draft",
                **clean, "updated_at": now, "revision": 1, "internal_notes": "", "_first_published": False,
                "_public": None}
        self.objects[object_id] = item
        self.history.append({"id": f"h{len(self.history) + 1}", "object_id": object_id, "revision": 1, "at": now,
                             "changed_fields": sorted(clean), "reason": "Создан черновик", "public_actor_label": "Редакция",
                             "actor": session["user"], "public": False})
        return reply(201, {"item": self._staff_item(item)})

    def _change(self, item, action, body, session):
        expected = body.get("expected_revision")
        if not isinstance(expected, int) or isinstance(expected, bool):
            raise Invalid({"expected_revision": "целое число"})
        if expected != item["revision"]:
            return reply(409, code="stale_revision", message="Запись уже изменена. Обновите её.")
        reason = body.get("reason")
        reason = reason.strip() if isinstance(reason, str) else ""
        if len(reason) > 500:
            raise Invalid({"reason": "до 500 символов"})
        public_entry = False
        if action == "update":
            changes = body.get("changes")
            if not isinstance(changes, dict) or not changes:
                raise Invalid({"changes": "непустой объект"})
            clean = validate_object(changes, partial=True)
            keys = clean.pop("_schedule_keys", set())
            if "schedule" in clean:
                merged = dict(item["schedule"])
                for key in keys:
                    merged[key] = clean["schedule"][key]
                if item.get("_first_published") and merged["original_planned_end"] != item["schedule"]["original_planned_end"]:
                    raise Invalid({"schedule.original_planned_end": "первоначальный срок после публикации не меняется"})
                clean["schedule"] = merged
            changed = sorted(k for k, v in clean.items() if item.get(k) != v)
            if not changed:
                return reply(200, {"item": self._staff_item(item)})
            if item.get("_first_published") and not reason:
                raise Invalid({"reason": "обязательна для опубликованной записи"})
            item.update(copy.deepcopy(clean))
        elif action == "publish":
            if not reason:
                raise Invalid({"reason": "обязательна"})
            published = item.get("_public")
            if item["publication"] == "published" and published and self._content(published) == self._content(item):
                return reply(200, {"item": self._staff_item(item)})
            if not item.get("_first_published"):
                item["_first_published"] = True
                if item["schedule"]["original_planned_end"] is None:
                    item["schedule"]["original_planned_end"] = item["schedule"]["current_planned_end"]
            changed = sorted(k for k in EDITABLE if not published or published.get(k) != item.get(k))
            if item["publication"] != "published":
                changed = sorted(set(changed) | {"publication"})
            item["publication"] = "published"
            public_entry = True
        elif action == "archive":
            if item["publication"] == "archived":
                return reply(200, {"item": self._staff_item(item)})
            if not reason:
                raise Invalid({"reason": "обязательна"})
            item["publication"] = "archived"
            item["_public"] = None
            changed = ["publication"]
        else:
            return None
        item["revision"] += 1
        item["updated_at"] = self._now()
        if public_entry:
            item["_public"] = self.public(item)
        self.history.append({"id": f"h{len(self.history) + 1}", "object_id": item["id"], "revision": item["revision"],
                             "at": item["updated_at"], "changed_fields": changed, "reason": reason or None,
                             "public_actor_label": "Редакция", "actor": session["user"], "public": public_entry})
        return reply(200, {"item": self._staff_item(item)})


class FeedbackDouble:
    def __init__(self, store: CivicStoreDouble, object_lookup, clock=None):
        self.store, self.lookup = store, object_lookup
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        self.items, self.lock, self.ids = {}, threading.RLock(), itertools.count(1)

    def handle(self, method, path, query, body, principal, context):
        parts = _parts(path)
        if parts is None:
            return None
        with self.lock:
            if parts == ["feedback"] and method == "POST":
                return self._submit(body or {})
            if len(parts) == 3 and parts[0] == "objects" and parts[2] == "feedback" and method == "GET":
                if not self.lookup(parts[1]):
                    return reply(404, code="not_found", message="Запись не найдена.")
                items = [{"id": f["id"], "object_id": f["object_id"], "category": f["category"], "text": f["text"],
                          "public_reply": f["public_reply"], "created_at": f["created_at"]}
                         for f in self.items.values()
                         if f["object_id"] == parts[1] and f["moderation"] == "approved" and f["consent_public"]]
                return reply(200, {"items": items})
            if parts[:2] == ["staff", "feedback"]:
                if (principal or {}).get("role") != "editor":
                    return reply(401, code="unauthenticated", message="Нужен вход сотрудника.")
                if method == "POST":
                    token = (context.get("headers") or {}).get("x-csrf-token", "")
                    if context.get("is_same_origin") is False or not hmac.compare_digest(token, principal.get("csrf") or "-"):
                        return reply(403, code="csrf_invalid", message="Проверка CSRF не пройдена.")
                if parts == ["staff", "feedback"] and method == "GET":
                    return reply(200, {"items": [copy.deepcopy(f) for f in self.items.values()], "next_cursor": None})
                if len(parts) == 4 and parts[3] == "moderate" and method == "POST":
                    return self._moderate(parts[2], body or {})
        return None

    def _submit(self, body):
        fields = {}
        object_id, geometry = body.get("object_id"), body.get("geometry")
        if object_id is None and geometry is None:
            fields["object_id"] = "нужен объект или место"
        if object_id is not None and not self.lookup(object_id):
            fields["object_id"] = "опубликованная запись не найдена"
        geo_fields = {}
        geometry = _geometry(geometry, geo_fields)
        fields.update(geo_fields)
        if body.get("category") not in CATEGORIES:
            fields["category"] = "одна из категорий"
        text = body.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            fields["text"] = "текст до 2000 символов"
        if not isinstance(body.get("consent_public"), bool):
            fields["consent_public"] = "true или false"
        if fields:
            return reply(422, code="validation", message="Проверьте поля.", fields=fields)
        receipt = f"fb-{next(self.ids):05d}"
        self.items[receipt] = {"id": receipt, "object_id": object_id, "geometry": geometry, "category": body["category"],
                               "text": text.strip(), "consent_public": body["consent_public"], "moderation": "pending",
                               "public_reply": None, "revision": 1,
                               "created_at": self.clock().replace(microsecond=0).isoformat()}
        return reply(201, {"receipt_id": receipt, "moderation": "pending"})

    def _moderate(self, feedback_id, body):
        item = self.items.get(feedback_id)
        if not item:
            return reply(404, code="not_found", message="Сообщение не найдено.")
        if body.get("expected_revision") != item["revision"]:
            return reply(409, code="stale_revision", message="Сообщение уже рассмотрено.")
        if body.get("action") not in ("approve", "reject") or not isinstance(body.get("reason"), str) or not body["reason"].strip():
            return reply(422, code="validation", message="Проверьте поля.", fields={"action": "approve|reject", "reason": "обязательно"})
        reply_text = body.get("public_reply")
        if reply_text is not None and (not isinstance(reply_text, str) or len(reply_text) > 1000):
            return reply(422, code="validation", message="Проверьте поля.", fields={"public_reply": "строка до 1000"})
        item["moderation"] = "approved" if body["action"] == "approve" else "rejected"
        item["public_reply"] = reply_text.strip() if isinstance(reply_text, str) and reply_text.strip() else None
        item["revision"] += 1
        return reply(200, {"item": copy.deepcopy(item)})


def make_double_gateway(seed=None):
    """Gateway wired to the doubles; returns (gateway, store)."""
    from ui.web_server import CivicGateway

    store = CivicStoreDouble()
    for item in seed or []:
        store.seed(item)
    holder = {}

    def lookup(object_id):
        return holder["gateway"].public_object(object_id)

    gateway = CivicGateway({"store": lambda: store, "feedback": lambda: FeedbackDouble(store, lookup)})
    holder["gateway"] = gateway
    return gateway, store
