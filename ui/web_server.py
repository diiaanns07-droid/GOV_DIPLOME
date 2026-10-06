"""Локальный HTTP-интерфейс: только движок считает, браузер отображает ответы.

Статические файлы доступны по белому списку. Ключи и исходники проекта
никогда не раздаются браузеру. Состояние каждого пользователя живёт в его вкладке.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs, urlsplit
import webbrowser

import engine


ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
MAX_BODY = 128 * 1024
CLIENT_DISCONNECTED = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/interface.js": ("interface.js", "text/javascript; charset=utf-8"),
    "/map.js": ("map.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/vendor/maplibre-gl.js": ("vendor/maplibre-gl.js", "text/javascript; charset=utf-8"),
    "/vendor/maplibre-gl.css": ("vendor/maplibre-gl.css", "text/css; charset=utf-8"),
}
POST_ROUTES = {
    "/api/validate", "/api/simulate", "/api/plan-status", "/api/optimize",
    "/api/robustness", "/api/compare", "/api/advisor", "/api/school-ai",
}

# Explicit public assets only: no directory serving, source code, or local settings.
for _asset in ("shell.js", "shell.css", "core/data.js", "core/evidence.js",
               "core/facts.js", "core/whatif.js", "core/plan.js", "core/resilience.js",
               "core/plan-ui.js", "core/resilience-ui.js", "core/attribution/ATTRIBUTION.md",
               "core/attribution/attribution.json", "core/attribution/LICENSES/Apache-2.0.txt",
               "core/attribution/LICENSES/CDLA-Permissive-2.0.txt", "core/attribution/LICENSES/ODbL-1.0.txt",
               "school/case.js", "school/note.js", "school/school-ui.js", "school/school.css",
               "school/cases/shymkent.case.json", "school/cases/shymkent.case.meta.json",
               "school/cases/astana.case.json", "school/cases/astana.match-review.json", "school/SCHOOL_MANIFEST.json",
               # K03 r10: pedestrian-v1 routing (module, ODbL graphs, hash manifest)
               "k03/routing.js", "k03/school-access-routing.js", "k03/shymkent.graph.json", "k03/astana.graph.json",
               "k03/K03_MANIFEST.json"):
    _mime = {".js": "text/javascript", ".css": "text/css", ".json": "application/json"}.get(Path(_asset).suffix, "text/plain")
    ASSETS["/govtech/" + _asset] = ("govtech/" + _asset, _mime + "; charset=utf-8")

# Round 11 civic-v1 frontend: explicit files only (R01 shell; role modules are added
# here by R01 when their reviewed delivery is imported). No directory serving.
CIVIC_ASSETS = ("shell/shell.js", "shell/shell.css",
                "feedback/feedback.js", "feedback/feedback.css",      # R06 @eaa113d
                "scenarios/scenarios.js", "scenarios/scenarios.css",  # R07 @22fa413 (graphs only via API)
                "map/civic-map-core.js", "map/civic-map.js", "map/civic-map.css",  # R03 @f73745c
                "editor/editor-core.js", "editor/editor.js", "editor/editor.css")  # R04 @da46e1c
for _asset in CIVIC_ASSETS:
    _mime = {".js": "text/javascript", ".css": "text/css", ".json": "application/json"}.get(Path(_asset).suffix, "text/plain")
    ASSETS["/civic/" + _asset] = ("civic/" + _asset, _mime + "; charset=utf-8")


# ---------------------------------------------------------------------------
# civic-v1 gateway (round 11, R01). Role services stay in their own packages:
#   R02 ui.civic_store.CivicService      R06 ui.civic_feedback.FeedbackService
#   R07 engine.civic_scenarios.compare    R09 agent.civic_assistant.build_answer
# The gateway owns only transport: explicit routes, Host/Origin, size, JSON envelope.
# A route whose module is not delivered answers 503 — it is never silently open.
CIVIC_PREFIX = "/api/civic/v1"
CIVIC_MAX_BODY = 64 * 1024
CIVIC_MAX_QUERY = 2048
CIVIC_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
# Order matters: /objects/{id}/feedback must win over /objects/{id}.
CIVIC_ROUTES = (
    ("GET", ("modules",), "gateway"),
    ("GET", ("session",), "store"),
    ("POST", ("session", "login"), "store"),
    ("POST", ("session", "logout"), "store"),
    ("GET", ("objects",), "store"),
    ("GET", ("objects", "{id}", "feedback"), "feedback"),
    ("GET", ("objects", "{id}"), "store"),
    ("GET", ("staff", "objects"), "store"),
    ("POST", ("staff", "objects"), "store"),
    ("GET", ("staff", "objects", "{id}"), "store"),
    ("POST", ("staff", "objects", "{id}", "update"), "store"),
    ("POST", ("staff", "objects", "{id}", "publish"), "store"),
    ("POST", ("staff", "objects", "{id}", "archive"), "store"),
    ("POST", ("feedback",), "feedback"),
    ("GET", ("staff", "feedback"), "feedback"),
    ("POST", ("staff", "feedback", "{id}", "moderate"), "feedback"),
    # R06 contract_delta (compatible additions, accepted by R01): moderator card, receipt status,
    # consent withdrawal by receipt number (receipt in the body, not in the URL).
    ("GET", ("staff", "feedback", "{id}"), "feedback"),
    ("POST", ("feedback", "receipt"), "feedback"),
    ("POST", ("feedback", "withdraw-consent"), "feedback"),
    # R07 contract_delta (accepted): graph list / graph geometry / prepared cases, read-only.
    ("GET", ("scenarios", "graphs"), "scenarios"),
    ("GET", ("scenarios", "graphs", "{id}"), "scenarios"),
    ("GET", ("scenarios", "cases"), "scenarios"),
    ("POST", ("scenarios", "compare"), "scenarios"),
    ("POST", ("assistant",), "assistant"),
)
CIVIC_MODULE_LABELS = {
    "store": "Объекты и доступ редактора (R02)",
    "feedback": "Сообщения жителей (R06)",
    "scenarios": "Сравнение ограничений (R07)",
    "assistant": "Помощник по фактам (R09)",
}
# R07 compare can return megabytes for a small request: at most two run at once.
SCENARIO_SLOTS = threading.BoundedSemaphore(2)
# R02 review M1: the login rate-limit check and failure record are not atomic in R02 @92f7aba,
# so parallel wrong passwords could all get 401. Logins are serialised here until R02 fixes it.
LOGIN_LOCK = threading.Lock()
# Headers a role service may set on its response; everything else is dropped.
CIVIC_SERVICE_HEADERS = {"set-cookie", "retry-after", "vary"}


def _restrict_db_files(db_path: Path):
    """R02 review: runtime DB holds password hashes and sessions — owner-only where supported."""
    for path in (db_path.parent, db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
        try:
            if path.exists():
                os.chmod(path, 0o700 if path.is_dir() else 0o600)
        except OSError:
            pass


def civic_error(status, code, message, fields=None):
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return {"status": status, "headers": {}, "body": {"ok": False, "error": error}}


def match_civic_route(method, segments):
    """Returns (owner, params) or raises LookupError('not_found'|'method')."""
    allowed = []
    for route_method, pattern, owner in CIVIC_ROUTES:
        if len(pattern) != len(segments):
            continue
        params = {}
        for part, value in zip(pattern, segments):
            if part == "{id}":
                if not CIVIC_ID.match(value):
                    break
                params["id"] = value
            elif part != value:
                break
        else:
            if route_method == method:
                return owner, params
            allowed.append(route_method)
    raise LookupError(",".join(sorted(set(allowed))) if allowed else "")


class CivicGateway:
    """Explicit civic-v1 routing to role services; services are created lazily.

    Lazy creation keeps unrelated checks (ui.web_check) free of a runtime DB.
    Each factory returns the service or raises ImportError when not delivered.
    """

    def __init__(self, factories=None):
        self._factories = dict(factories or {})
        self._services = {}
        self._failed = {}
        self._lock = threading.Lock()

    @classmethod
    def for_project(cls, project: Path, db_path: Path | None = None):
        db_path = Path(db_path) if db_path else project / ".runtime" / "civic.sqlite3"

        def store():
            module = importlib.import_module("ui.civic_store")
            # R02 exports CivicService from ui.civic_store.service (package __init__ may not re-export).
            service_class = getattr(module, "CivicService", None) or \
                importlib.import_module("ui.civic_store.service").CivicService
            db_path.parent.mkdir(parents=True, exist_ok=True)
            service = service_class(str(db_path))
            _restrict_db_files(db_path)
            return service

        def feedback():
            # R06 on the same SQLite file (own feedback_* tables). Object lookup via R02's staff
            # read; R06 itself requires city=astana and publication=published for residents.
            integration = importlib.import_module("ui.civic_feedback.integration")
            store_service = gateway.service("store")
            if store_service is None:
                raise ImportError("feedback needs the object store")
            db_path.parent.mkdir(parents=True, exist_ok=True)
            # classifier=None: the R08 model is not integrated/verified in this build.
            return integration.build_feedback_service(str(db_path), store_service, classifier=None)

        def scenarios():
            # R07 @22fa413: graphs only by id from its MANIFEST; every graph is hashed at start so a
            # corrupted file makes the module init_failed instead of a false "ready".
            module = importlib.import_module("engine.civic_scenarios.http")
            registry = importlib.import_module("engine.civic_scenarios.registry")
            for item in registry.manifest()["graphs"]:
                registry.load_graph(item["id"])
            return module

        gateway = cls({"store": store, "feedback": feedback, "scenarios": scenarios})
        return gateway

    def service(self, name):
        if name in self._services:
            return self._services[name]
        factory = self._factories.get(name)
        if factory is None:
            return None
        with self._lock:
            if name in self._services:
                return self._services[name]
            if name in self._failed:
                return None
            try:
                self._services[name] = factory()
            except ImportError as exc:
                # Not delivered yet: recorded once, reported as module_unavailable.
                self._failed[name] = "not_delivered"
                LOGGER.info("civic module %s unavailable: %s", name, exc.__class__.__name__)
                return None
            except Exception:
                self._failed[name] = "init_failed"
                LOGGER.exception("civic module %s failed to start", name)
                return None
            return self._services[name]

    def modules(self):
        result = {}
        for name, label in CIVIC_MODULE_LABELS.items():
            ready = self.service(name) is not None
            result[name] = {"label": label, "status": "ready" if ready else
                            ("init_failed" if self._failed.get(name) == "init_failed" else "unavailable")}
        return result

    def public_object(self, object_id):
        """Object lookup for R06: the published public DTO only (never drafts)."""
        store = self.service("store")
        if store is None or not isinstance(object_id, str) or not CIVIC_ID.match(object_id):
            return None
        reply = store.handle("GET", CIVIC_PREFIX + "/objects/" + object_id, "", None,
                             {"headers": {}, "client_ip": None, "host_allowed": True,
                              "is_same_origin": None, "is_https": False})
        if not reply or reply.get("status") != 200:
            return None
        data = (reply.get("body") or {}).get("data") or {}
        return data.get("item")

    @staticmethod
    def _scenarios(service, method, full_path, query, body):
        """R07 handle(method, path, query, body): stateless, no session; guarded per R01 review."""
        if method == "POST" and not isinstance(body.get("graph_id"), str):
            return civic_error(422, "invalid_payload", "graph_id должен быть строкой.",
                               {"graph_id": "строковый идентификатор графа из списка"})
        if method == "POST" and not SCENARIO_SLOTS.acquire(blocking=False):
            reply = civic_error(503, "busy", "Сравнение уже выполняется. Повторите через пару секунд.")
            reply["headers"]["Retry-After"] = "2"
            return reply
        try:
            return service.handle(method, full_path, query, body)
        except OverflowError:
            return civic_error(422, "invalid_payload", "Недопустимая дата или время.",
                               {"analysis_at": "дата вне допустимого диапазона"})
        finally:
            if method == "POST":
                SCENARIO_SLOTS.release()

    def handle(self, method, rel_path, query, body, context):
        segments = rel_path.strip("/").split("/") if rel_path.strip("/") else []
        if rel_path != "/" + "/".join(segments) or any(not s for s in segments):
            return civic_error(404, "not_found", "Адрес API не найден.")
        try:
            owner, params = match_civic_route(method, segments)
        except LookupError as exc:
            if str(exc):
                reply = civic_error(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
                reply["headers"]["Allow"] = str(exc)
                return reply
            return civic_error(404, "not_found", "Адрес API не найден.")
        if owner == "gateway":
            return {"status": 200, "headers": {}, "body": {"ok": True, "data": {"modules": self.modules()}}}
        service = self.service(owner)
        if service is None:
            return civic_error(503, "module_unavailable",
                               f"Модуль «{CIVIC_MODULE_LABELS[owner]}» не подключён в этой сборке.")
        # Services receive the full path (R02 convention: "/api/civic/v1/objects/...").
        full_path = CIVIC_PREFIX + rel_path
        if owner == "store":
            if rel_path == "/session/login":
                with LOGIN_LOCK:
                    return service.handle(method, full_path, query, body, context)
            return service.handle(method, full_path, query, body, context)
        if owner == "scenarios":
            return self._scenarios(service, method, full_path, query, body)
        if owner == "feedback":
            store = self.service("store")
            principal = store.resolve_principal(context) if store is not None else None
            return service.handle(method, full_path, query, body, principal, context)
        return civic_error(503, "module_unavailable",
                           f"Модуль «{CIVIC_MODULE_LABELS[owner]}» не подключён в этой сборке.")


def event_id(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Код события должен быть короткой строкой или null.")
    return value.strip().upper() or None


def decisions(body):
    """Проверяем размер транспорта; содержимое и правила проверяет validate()."""
    result = body.get("decisions")
    if not isinstance(result, list) or len(result) > 30:
        raise ValueError("Передайте decisions — список решений, не более 30 записей.")
    return deepcopy(result)


class Backend:
    def __init__(self, project: Path = ROOT):
        self.project = project.resolve()
        self.data = engine.load_data(self.project / "data" / "city_data.json")
        self.catalog = deepcopy(self.data.raw)
        self.events = engine.list_events(data=self.data)["events"]
        self.optimize_lock = threading.Lock()
        # Геометрия необязательна: районы и расчёты доступны без карты.
        try:
            geometry = json.loads((self.project / "data" / "astana_districts.geojson").read_text(encoding="utf-8-sig"))
            self.geojson = geometry if (isinstance(geometry, dict)
                and geometry.get("type") == "FeatureCollection"
                and isinstance(geometry.get("features"), list)) else None
        except (OSError, ValueError):
            self.geojson = None

    def baseline(self, selected_event=None):
        return engine.baseline(data=self.data, event_id=event_id(selected_event))

    def bootstrap(self, selected_event=None):
        baseline = self.baseline(selected_event)
        if baseline.get("valid") is False:
            raise ValueError(" ".join(baseline["errors"]))
        # Административная карта и учебный датасет имеют разный охват.
        # Наличие полигона не означает наличие показателей для расчёта Score.
        modeled = [row["id"] for row in baseline["districts"]]
        features = (self.geojson or {}).get("features", [])
        geographic = [f.get("properties", {}).get("id") for f in features]
        geographic = list(dict.fromkeys(item for item in geographic if item))
        unmodeled = [item for item in geographic if item not in modeled]
        sources = list(dict.fromkeys(f.get("properties", {}).get("source_url", "")
                                    for f in features))
        return {"baseline": baseline, "catalog": self.catalog, "geojson": self.geojson,
                "events": self.events, "mode": "live",
                "model_scope": {"district_ids": modeled,
                    "geographic_district_ids": geographic,
                    "unmodeled_district_ids": unmodeled,
                    "notice": "Расчёт использует районы и показатели датасета задания. "
                              "Районы без исходных показателей показаны на карте без оценки."},
                "geography": {"sources": [url for url in sources if url],
                    "has_approximate": any(f.get("properties", {}).get("source") == "fallback_approx"
                                           for f in features),
                    "feature_count": len(features), "modeled_count": len(modeled)}}

    def plan_status(self, plan, selected_event):
        # simulate возвращает стоимость и бюджет даже у неполного плана.
        # Поэтому JS не содержит вторую реализацию расчёта денег.
        report = engine.simulate(plan, data=self.data, event_id=selected_event)
        validation = engine.validate(plan, data=self.data, event_id=selected_event)
        can_complete = None
        if len(plan) == self.data.num_decisions - 1:
            can_complete = False
            for mid, measure in self.data.measures.items():
                targets = self.data.districts if measure["scope"] == "district" else (None,)
                for target in targets:
                    candidate = [*plan, {"measure": mid, "district": target}]
                    if engine.validate(candidate, data=self.data, event_id=selected_event)["valid"]:
                        can_complete = True
                        break
                if can_complete:
                    break
        return {key: report.get(key) for key in ("cost", "budget", "budget_left")} | {
            "count": len(plan), "can_complete": can_complete,
            "validation": validation, "errors": validation["errors"],
        }

    def post(self, path, body):
        selected_event = event_id(body.get("event_id"))
        if path in ("/api/validate", "/api/simulate"):
            function = engine.validate if path.endswith("validate") else engine.simulate
            return function(decisions(body), data=self.data, event_id=selected_event)
        if path == "/api/plan-status":
            return self.plan_status(decisions(body), selected_event)
        if path == "/api/optimize":
            top_n = body.get("top_n", 5)
            if isinstance(top_n, bool) or not isinstance(top_n, int) or not 1 <= top_n <= 5:
                raise ValueError("Число лучших планов должно быть целым от 1 до 5.")
            robust = body.get("robust", False)
            if not isinstance(robust, bool):
                raise ValueError("Режим устойчивого поиска должен быть true или false.")
            # Не запускаем параллельно тяжёлые переборы после повторных кликов.
            with self.optimize_lock:
                return engine.optimize(top_n=top_n, constraints=body.get("constraints"),
                                       robust=robust, data=self.data, event_id=selected_event)
        if path == "/api/robustness":
            # Официальный контракт: план выбран ДО события; события не складываются.
            return engine.robustness(decisions(body), data=self.data)
        if path == "/api/compare":
            plans = body.get("plans")
            if not isinstance(plans, dict) or not 1 <= len(plans) <= 10:
                raise ValueError("Для сравнения передайте от одного до десяти именованных планов.")
            for name, plan in plans.items():
                if len(name) > 120:
                    raise ValueError("Название плана слишком длинное.")
                decisions(plan if isinstance(plan, dict) else {"decisions": plan})
            return engine.compare(plans, data=self.data, event_id=selected_event)
        if path == "/api/school-ai":
            # Школьный кейс: модель выбирает только ID фактов/действия; числа и текст собирает браузер.
            from agent.school_ai import answer

            return answer(body)
        if path == "/api/advisor":
            # Браузер присылает только решения: его Score и тексты не являются фактами.
            from agent.advisor import ask_advisor

            plan = decisions(body)
            question = body.get("question", "")
            if not isinstance(question, str) or len(question) > 4000:
                raise ValueError("Вопрос должен быть строкой не длиннее 4000 символов.")
            history = body.get("history", [])
            checked = body.get("checked_plans", [])
            if not isinstance(history, list) or not isinstance(checked, list):
                raise ValueError("История и проверенные планы должны быть списками.")
            # ask_advisor сам пересчитает этот состав перед любым ответом LLM.
            return ask_advisor(question, {"decisions": plan}, history=history[-6:],
                               checked_plans=checked[-6:], event_id=selected_event)
        raise KeyError(path)


class Handler(BaseHTTPRequestHandler):
    server_version = "Akim/2.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def handle(self):
        try:
            super().handle()
        except CLIENT_DISCONNECTED:
            # Обновление страницы может оборвать чтение запроса или flush ответа.
            self.close_connection = True

    def send_bytes(self, status, data, content_type):
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except CLIENT_DISCONNECTED:
            # Заголовки тоже пишут в сокет. В закрытое соединение не отправляем 500.
            self.close_connection = True

    def json_reply(self, status, value):
        self.send_bytes(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                        "application/json; charset=utf-8")

    def error_reply(self, status, message):
        self.json_reply(status, {"valid": False, "errors": [message], "score": None})

    def discard_body(self):
        # Непрочитанное тело при закрытии сокета заставляет Windows послать
        # TCP reset раньше ответа об ошибке. Дочитываем только допустимый размер.
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return
        if 0 < length <= MAX_BODY:
            self.rfile.read(length)

    def do_HEAD(self):
        self.do_GET()

    # --- civic-v1 transport -------------------------------------------------
    def host_allowed(self):
        """Same rule as the legacy POST guard: loopback or this server's address."""
        try:
            host = urlsplit("http://" + self.headers.get("Host", "")).hostname
            if host in {"localhost", "127.0.0.1", "::1", self.server.server_address[0]}:
                return True
            if self.server.server_address[0] == "0.0.0.0":
                return ipaddress.ip_address(host).is_private
        except ValueError:
            return False
        return False

    def same_origin(self):
        origin = self.headers.get("Origin")
        if not origin:
            return False
        try:
            parsed = urlsplit(origin)
        except ValueError:
            return False
        host = self.headers.get("Host") or ""
        # This server speaks plain HTTP on loopback; "null" and https origins are foreign.
        return parsed.scheme == "http" and parsed.netloc.lower() == host.lower() and not parsed.path

    def origin_state(self):
        """False on any cross-origin signal; True when Origin/Sec-Fetch-Site confirm same origin;
        None when the client sent neither (services then rely on the CSRF token)."""
        site = self.headers.get("Sec-Fetch-Site")
        if site in ("same-site", "cross-site"):
            return False
        if self.headers.get("Origin"):
            return self.same_origin()
        if site in ("same-origin", "none"):
            return True
        return None

    def civic_send(self, reply):
        status = reply.get("status") if isinstance(reply, dict) else None
        body = reply.get("body") if isinstance(reply, dict) else None
        if (not isinstance(status, int) or isinstance(status, bool) or not 200 <= status <= 599
                or not isinstance(body, dict) or not isinstance(body.get("ok"), bool)):
            LOGGER.error("civic service returned a malformed response")
            reply = civic_error(500, "bad_service_response", "Сервис вернул некорректный ответ.")
            status, body = reply["status"], reply["body"]
        try:
            data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError):
            LOGGER.error("civic service response is not JSON-serialisable")
            reply = civic_error(500, "bad_service_response", "Сервис вернул некорректный ответ.")
            status, data = 500, json.dumps(reply["body"], ensure_ascii=False).encode("utf-8")
        extra = []
        for name, value in (reply.get("headers") or {}).items():
            key = str(name).lower()
            if key in CIVIC_SERVICE_HEADERS or (key == "allow" and status == 405):
                for item in (value if isinstance(value, (list, tuple)) else [value]):
                    text = str(item)
                    if "\r" not in text and "\n" not in text:
                        extra.append((str(name), text))
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            for name, value in extra:
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except CLIENT_DISCONNECTED:
            self.close_connection = True

    def civic_request(self, method):
        parsed = urlsplit(self.path)
        rel_path = parsed.path[len(CIVIC_PREFIX):] or "/"
        if not self.host_allowed():
            if method == "POST":
                self.discard_body()
            self.civic_send(civic_error(403, "forbidden_host", "Откройте интерфейс через адрес этого сервера."))
            return
        if method == "POST":
            if self.origin_state() is False:
                self.discard_body()
                self.civic_send(civic_error(403, "cross_origin", "Запрос с другого сайта отклонён."))
                return
        if len(parsed.query) > CIVIC_MAX_QUERY:
            if method == "POST":
                self.discard_body()
            self.civic_send(civic_error(400, "query_too_long", "Слишком длинная строка запроса."))
            return
        query = parsed.query  # raw; each service parses and bounds it (R02 parse_query)
        body = None
        if self.headers.get("Transfer-Encoding"):
            # Content-Length only; a chunked body would stay in the stream (adopted from R02 adapter).
            self.close_connection = True
            self.civic_send(civic_error(411, "length_required", "Нужен Content-Length; chunked не поддерживается."))
            return
        if method == "POST":
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if not 0 < length <= CIVIC_MAX_BODY:
                if CIVIC_MAX_BODY < length <= CIVIC_MAX_BODY * 2:
                    self.rfile.read(length)
                self.close_connection = True
                code = 413 if length > CIVIC_MAX_BODY else 400
                self.civic_send(civic_error(code, "too_large" if code == 413 else "empty_body",
                                            "Слишком большой запрос." if code == 413 else "Пустой запрос."))
                return
            if self.headers.get_content_type() != "application/json":
                self.rfile.read(length)
                self.civic_send(civic_error(415, "unsupported_media_type", "Ожидается Content-Type: application/json."))
                return
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"), parse_constant=_invalid_number)
            except CLIENT_DISCONNECTED:
                self.close_connection = True
                return
            except (ValueError, UnicodeDecodeError):
                self.civic_send(civic_error(400, "invalid_json", "Тело запроса должно быть корректным JSON."))
                return
            if not isinstance(body, dict):
                self.civic_send(civic_error(400, "invalid_json", "Тело запроса должно быть JSON-объектом."))
                return
        cookies = {}
        try:
            jar = SimpleCookie()
            jar.load(self.headers.get("Cookie", ""))
            cookies = {key: morsel.value for key, morsel in jar.items()}
        except CookieError:
            cookies = {}
        context = {
            "method": method, "path": rel_path,
            "headers": {key.lower(): value for key, value in self.headers.items()},
            "cookies": cookies, "client_ip": self.client_address[0] if self.client_address else None,
            # host_allowed is always True here: other hosts were rejected above.
            "host_allowed": True, "is_same_origin": self.origin_state(), "is_https": False,
            "host": self.headers.get("Host"),
        }
        try:
            reply = self.server.civic.handle(method, rel_path, query, body, context)
        except Exception:
            # No body, cookies or provider details in the log or the reply.
            LOGGER.exception("civic handler failed for %s %s", method, rel_path)
            reply = civic_error(500, "internal", "Не удалось выполнить запрос. Попробуйте ещё раз.")
        if reply is None:
            reply = civic_error(404, "not_found", "Адрес API не найден.")
        self.civic_send(reply)

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == CIVIC_PREFIX or path.startswith(CIVIC_PREFIX + "/"):
            self.civic_request("GET")
            return
        if path == "/api/health":
            self.json_reply(200, {"status": "ok"})
            return
        try:
            selected_event = parse_qs(parsed.query).get("event_id", [None])[0]
            if path == "/api/bootstrap":
                self.json_reply(200, self.server.backend.bootstrap(selected_event))
            elif path == "/api/baseline":
                self.json_reply(200, self.server.backend.baseline(selected_event))
            elif path == "/api/events":
                self.json_reply(200, {"events": self.server.backend.events})
            elif path in ASSETS:
                filename, content_type = ASSETS[path]
                asset = self.server.backend.project / "web" / filename
                if not asset.is_file():
                    self.error_reply(404, "Файл интерфейса не найден.")
                else:
                    self.send_bytes(200, asset.read_bytes(), content_type)
            else:
                self.error_reply(404, "Страница не найдена.")
        except ValueError as exc:
            self.error_reply(400, str(exc))
        except Exception:
            LOGGER.exception("Ошибка загрузки данных интерфейса")
            self.error_reply(500, "Не удалось загрузить данные движка.")

    def do_POST(self):
        path = urlsplit(self.path).path
        if path == CIVIC_PREFIX or path.startswith(CIVIC_PREFIX + "/"):
            self.civic_request("POST")
            return
        if path not in POST_ROUTES:
            self.discard_body()
            self.error_reply(404, "Метод не найден.")
            return
        # HTML и API на одном origin; сторонние страницы не должны расходовать ключ.
        origin = self.headers.get("Origin")
        try:
            host = urlsplit("http://" + self.headers.get("Host", "")).hostname
            allowed_host = host in {"localhost", "127.0.0.1", "::1", self.server.server_address[0]}
            if not allowed_host and self.server.server_address[0] == "0.0.0.0":
                # При явном сетевом запуске допускаем обращение по адресу машины.
                allowed_host = ipaddress.ip_address(host).is_private
            if not allowed_host:
                raise ValueError("Неизвестный адрес сервера")
            parsed = urlsplit(origin) if origin else None
            if parsed and (parsed.scheme not in ("http", "https") or parsed.netloc != self.headers.get("Host")):
                raise ValueError("Сторонний источник запроса")
        except ValueError:
            self.discard_body()
            self.error_reply(403, "Откройте интерфейс через адрес этого сервера.")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                # Небольшое превышение дочитываем перед закрытием соединения:
                # иначе Windows может послать TCP reset раньше ответа 413.
                if MAX_BODY < length <= MAX_BODY * 2:
                    self.rfile.read(length)
                self.error_reply(413, "Пустой или слишком большой запрос.")
                return
            if self.headers.get_content_type() != "application/json":
                self.discard_body()
                self.error_reply(415, "Ожидается Content-Type: application/json.")
                return
            body = json.loads(self.rfile.read(length).decode("utf-8-sig"), parse_constant=_invalid_number)
            if not isinstance(body, dict):
                raise ValueError("Тело запроса должно быть JSON-объектом.")
            self.json_reply(200, self.server.backend.post(path, body))
        except CLIENT_DISCONNECTED:
            # Клиент мог уйти со страницы до окончания чтения тела запроса.
            self.close_connection = True
        except (ValueError, UnicodeDecodeError) as exc:
            self.error_reply(400, str(exc))
        except Exception:
            # Не выводим body, настройки провайдера или содержимое .env.
            LOGGER.exception("Ошибка обработчика %s", path)
            self.error_reply(500, "Не удалось выполнить запрос. Попробуйте ещё раз.")


    def do_unsupported(self):
        """PUT/PATCH/DELETE: civic answers 405 in its envelope; the rest keeps a JSON 405."""
        path = urlsplit(self.path).path
        self.discard_body()
        self.close_connection = True
        if path == CIVIC_PREFIX or path.startswith(CIVIC_PREFIX + "/"):
            self.civic_send(civic_error(405, "method_not_allowed", "Метод не поддерживается."))
        else:
            self.error_reply(405, "Метод не поддерживается.")

    do_PUT = do_PATCH = do_DELETE = do_unsupported


def _invalid_number(value):
    raise ValueError("JSON должен содержать только конечные числа.")


def create_server(project: Path = ROOT, port: int = 8501, host: str = "127.0.0.1",
                  civic: CivicGateway | None = None, civic_db: Path | None = None):
    backend = Backend(project)
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.backend = backend
    server.civic = civic if civic is not None else CivicGateway.for_project(Path(project), civic_db)
    return server


def main():
    parser = argparse.ArgumentParser(description="Аким на 5 часов — городской симулятор")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--open", action="store_true", help="Открыть браузер после запуска")
    parser.add_argument("--civic-db", default=os.environ.get("CIVIC_DB_PATH") or os.environ.get("CIVIC_DB"),
                        help="SQLite городских объектов (по умолчанию .runtime/civic.sqlite3)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Порт должен быть от 1 до 65535.")
    try:
        server = create_server(port=args.port, host=args.host,
                               civic_db=Path(args.civic_db) if args.civic_db else None)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10048 or getattr(exc, "errno", None) in (48, 98, 10048):
            parser.exit(1, "Порт занят. Закройте прежнее приложение или задайте другой PORT.\n")
        raise
    address = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    url = f"http://{address}:{args.port}"
    modules = server.civic.modules()
    print("civic-v1: " + ", ".join(f"{name}={item['status']}" for name, item in modules.items()), flush=True)
    print(f"Аким на 5 часов: {url}\nОстановить — Ctrl+C", flush=True)
    if args.open:
        opener = threading.Timer(0.3, webbrowser.open, args=(url,))
        opener.daemon = True
        opener.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
