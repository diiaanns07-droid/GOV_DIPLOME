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
    # B2: three.js 0.169.0 (LOCAL-2) для 3D-превью R05; грузится модулем build3d только при монтировании.
    "/vendor/three/three.module.min.js": ("vendor/three/three.module.min.js", "text/javascript; charset=utf-8"),
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
CIVIC_ASSETS = ("shell/shell.js", "shell/shell.css", "shell/explore.js", "map/streets.json",
                "feedback/feedback.js", "feedback/feedback.css",      # R06 @eaa113d
                "scenarios/scenarios.js", "scenarios/scenarios.css",  # R07 @22fa413 (graphs only via API)
                "map/civic-map-core.js", "map/civic-map.js", "map/civic-map.css",  # R03 @f73745c
                "editor/editor-core.js", "editor/editor.js", "editor/editor.css",  # R04 @da46e1c
                "assistant/assistant.js", "assistant/assistant.css",  # R09 @f895c30 (demo.html not served)
                # Раунд 14: шапка Birge (R01); ui-kit, шрифт Inter и переводы R11 (поставка claude/r14-R11 @ ba8758b).
                "shell/shell-text.js", "shell/birge.js", "shell/birge.css",
                "ui-kit/tokens.css", "ui-kit/components.css", "ui-kit/ui-kit.js", "ui-kit/icons.svg",
                "ui-kit/categories_v2.json", "ui-kit/index.html",
                "ui-kit/fonts/Inter-Regular.woff2", "ui-kit/fonts/Inter-SemiBold.woff2", "ui-kit/fonts/Inter-Bold.woff2",
                "ui-kit/fonts/OFL.txt",
                "i18n/i18n.js", "i18n/ru.json", "i18n/kk.json",
                # B1: R07 тепловая карта @ 5a97636, R09 путь жителя v2 @ da295be, R08 «Картина дня» @ 9f1d9c0.
                "heat/heat.js", "heat/heat.css",
                "feedback/categories_v2.js", "feedback/complaint-strings.js", "feedback/complaint.js",
                "feedback/complaint.css",
                "akim/index.html", "akim/akim.js", "akim/akim.css", "akim/akim.i18n.json",
                "map/demo_snapped.json",  # B2: R12 демо-линии, привязанные к улицам OSM
                "proposals/proposals.js", "proposals/proposals.css", "proposals/stage-editor.js",  # B2: R06
                # B2: R05 3D-превью @ b0353ee. demo.html и data/demo-basemap.json не отдаём (только для демо R05).
                "build3d/build3d-core.js", "build3d/build3d-models.js", "build3d/build3d.js", "build3d/build3d.css",
                "build3d/data/nura-streets.json", "build3d/data/astana-districts.json",
                "build3d/data/astana-existing.json", "build3d/data/proposals.fixture.json")
# Тип по расширению; шрифт — двоичный, без charset (иначе браузер может отказаться его применять).
CIVIC_MIME = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
              ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml; charset=utf-8",
              ".html": "text/html; charset=utf-8", ".woff2": "font/woff2"}
for _asset in CIVIC_ASSETS:
    ASSETS["/civic/" + _asset] = ("civic/" + _asset, CIVIC_MIME.get(Path(_asset).suffix, "text/plain; charset=utf-8"))


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
    # R02 round 13 (compatible additions): editor reference data, audit page, import candidates.
    ("GET", ("staff", "meta"), "store"),
    ("GET", ("staff", "audit"), "store"),
    ("GET", ("staff", "objects", "{id}", "import-candidates"), "store"),
    ("POST", ("staff", "objects", "{id}", "import-candidates", "{id}", "apply"), "store"),
    ("POST", ("staff", "objects", "{id}", "import-candidates", "{id}", "dismiss"), "store"),
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
    # R09 contract_delta (accepted): editor-only extraction draft from supplied publication text.
    ("POST", ("staff", "assistant", "extract"), "assistant"),
)
CIVIC_MODULE_LABELS = {
    "store": "Объекты и доступ редактора (R02)",
    "feedback": "Сообщения жителей (R06)",
    "scenarios": "Сравнение ограничений (R07)",
    "assistant": "Помощник по фактам (R09)",
}
# R07 compare can return megabytes for a small request: at most two run at once.
SCENARIO_SLOTS = threading.BoundedSemaphore(2)
# R09 ScenarioResultCache (round 13): only the server's own successful /scenarios/compare results are
# kept for the assistant; bounded in count, age and size (a citywide result with routes can be large).
SCENARIO_CACHE_ITEMS = 16
SCENARIO_CACHE_TTL_S = 3600.0
SCENARIO_CACHE_MAX_BYTES = 1_000_000
# R02 review M1: the login rate-limit check and failure record are not atomic in R02 @92f7aba,
# so parallel wrong passwords could all get 401. Logins are serialised here until R02 fixes it.
LOGIN_LOCK = threading.Lock()
# Headers a role service may set on its response; everything else is dropped.
CIVIC_SERVICE_HEADERS = {"set-cookie", "retry-after", "vary"}


def _restrict_db_files(db_path: Path, own_parent: bool = False):
    """R02 review: runtime DB holds password hashes and sessions — owner-only where supported.

    The parent directory is tightened only when R01 created it (own_parent): a --civic-db in an
    existing shared folder must not change that folder's permissions."""
    paths = (db_path.parent,) if own_parent else ()
    for path in paths + (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
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


# Role packages: only a missing package itself means "not delivered"; any other ImportError
# (a broken dependency inside a delivered module) is an init failure and is logged.
CIVIC_ROLE_PACKAGES = {"ui.civic_store", "ui.civic_feedback", "engine.civic_scenarios", "agent.civic_assistant"}


class ModuleNotDelivered(Exception):
    """A factory precondition: the module this service depends on is not delivered."""


def _role_package_missing(exc):
    name = getattr(exc, "name", None) or ""
    return isinstance(exc, ModuleNotFoundError) and any(
        name == package or package.startswith(name + ".") for package in CIVIC_ROLE_PACKAGES)


def resolve_db_path(value):
    """CLI/env value -> absolute path (~ expanded), so the startup line and chmod name one file."""
    return Path(value).expanduser().resolve() if value else None


class CivicGateway:
    """Explicit civic-v1 routing to role services; services are created lazily.

    Lazy creation keeps unrelated checks (ui.web_check) free of a runtime DB.
    Each factory returns the service; a missing role package or ModuleNotDelivered means
    "not delivered", any other exception means "init_failed".
    """

    def __init__(self, factories=None):
        self._factories = dict(factories or {})
        self._services = {}
        self._failed = {}
        self.db_path = None  # for_project задаёт путь к SQLite; API v2 (R09) пишет в тот же файл
        # Re-entrant: the feedback/assistant factories ask for the store while the lock is held.
        self._lock = threading.RLock()
        # R08 via R06: what the feedback service was started with (no resident texts here).
        self.classifier_status = {"enabled": False, "available": False, "reason": "off"}
        self._scenario_results = None  # R09 cache of server-computed A/B results (created on first use)

    def scenario_results(self):
        """Shared R09 ScenarioResultCache, or None when the assistant package (or the cache) is absent."""
        with self._lock:
            if self._scenario_results is None:
                try:
                    api = importlib.import_module("agent.civic_assistant.api")
                except ModuleNotFoundError as exc:
                    if not _role_package_missing(exc):
                        raise
                    return None
                cache_class = getattr(api, "ScenarioResultCache", None)
                if cache_class is None:
                    return None
                self._scenario_results = cache_class(max_items=SCENARIO_CACHE_ITEMS, ttl_s=SCENARIO_CACHE_TTL_S)
            return self._scenario_results

    def _remember_scenario(self, payload, result):
        """After a successful compare: keep the server's result for the assistant (never client numbers).
        R09 checks schema, result digest format and that payload is this result's input (payload_digest)."""
        try:
            size = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        except (TypeError, ValueError):
            return None
        if size > SCENARIO_CACHE_MAX_BYTES:
            LOGGER.info("scenario result not cached for the assistant: %d bytes > %d", size, SCENARIO_CACHE_MAX_BYTES)
            return None
        cache = self.scenario_results()
        if cache is None:
            return None
        try:
            return cache.remember(payload, result)
        except Exception:  # the compare answer must not fail because of the explanation cache
            LOGGER.exception("scenario result cache failed")
            return None

    @classmethod
    def for_project(cls, project: Path, db_path: Path | None = None, classifier: str | None = None):
        db_path = resolve_db_path(db_path) or Path(project).resolve() / ".runtime" / "civic.sqlite3"
        # R08 is opt-in (round 13): --civic-classifier r08 or CIVIC_R08_CLASSIFIER=1. Default off.
        classifier = classifier or ("r08" if os.environ.get("CIVIC_R08_CLASSIFIER") == "1" else "off")

        def ensure_parent():
            created = not db_path.parent.exists()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return created

        def store():
            module = importlib.import_module("ui.civic_store")
            # R02 exports CivicService from ui.civic_store.service (package __init__ may not re-export).
            service_class = getattr(module, "CivicService", None) or \
                importlib.import_module("ui.civic_store.service").CivicService
            created = ensure_parent()
            service = service_class(str(db_path))
            _restrict_db_files(db_path, own_parent=created)
            # R06 раунд 14: функции API v2 (предложения, голоса, этапы) работают с этой же базой и сессиями.
            try:
                importlib.import_module("ui.civic_store.v2").bind(service)
            except ModuleNotFoundError:
                pass  # хранилище раунда 13 без v2 — маршруты R06 ответят 503 module_not_ready
            return service

        def feedback():
            # R06 on the same SQLite file (own feedback_* tables). Residents must be checked against
            # what they see: a published object is looked up through R02's PUBLIC view, so an
            # unpublished staff edit (e.g. a moved point) cannot change the location check. Only
            # objects without a public version fall back to the staff read, and R06 rejects those
            # for residents (publication != published); staff moderation still sees their summary.
            integration = importlib.import_module("ui.civic_feedback.integration")
            service_module = importlib.import_module("ui.civic_feedback.service")
            store_service = gateway.service("store")
            if store_service is None:
                raise ModuleNotDelivered("feedback needs the object store")
            ensure_parent()
            # R02 >= 9b005be exposes both lookups without an HTTP context; older R02 via handle()/staff read.
            public_lookup = getattr(store_service, "lookup_public_object", None) or gateway.public_object
            staff_lookup = getattr(store_service, "lookup_staff_object", None) or \
                integration.object_lookup_from_civic_service(store_service)

            def lookup(object_id):
                if not isinstance(object_id, str) or not CIVIC_ID.match(object_id):
                    return None
                item = public_lookup(object_id)
                if item is not None:
                    return item
                staff_item = staff_lookup(object_id)
                if isinstance(staff_item, dict) and staff_item.get("publication") == "published":
                    return None  # published but no public view: never fall back to the staff copy
                return staff_item

            # R08 through R06's adapter, only when switched on. The adapter imports the model and probes
            # the civic-v1 contract with a timeout; a missing, failing, hanging or off-contract model gives
            # no classifier, and messages are still saved (R06 also bounds each call, 2 s). The model is
            # trained on synthetic data only: it suggests a category for staff (needs_review), never decides.
            fn = None
            if classifier == "r08":
                adapter = importlib.import_module("ui.civic_feedback.classifier_adapter")
                status = adapter.r08_status(timeout_s=3.0)
                gateway.classifier_status = {"enabled": True, "available": bool(status.get("available")),
                                             "reason": status.get("reason"), "model_version": status.get("model_version"),
                                             "training_data_status": status.get("training_data_status"),
                                             "score_kind": status.get("score_kind")}
                fn = status.get("classify") if status.get("available") else None
            # classifier_source="r08" (R06 r13 patch): staff and reports see that the hint came from the R08 model.
            return service_module.FeedbackService(str(db_path), lookup, getattr(store_service, "clock", None),
                                                  classifier=fn,
                                                  classifier_source="r08" if fn is not None else None)

        def scenarios():
            # R07 @22fa413: graphs only by id from its MANIFEST; every graph is hashed at start so a
            # corrupted file makes the module init_failed instead of a false "ready".
            module = importlib.import_module("engine.civic_scenarios.http")
            registry = importlib.import_module("engine.civic_scenarios.registry")
            for item in registry.manifest()["graphs"]:
                registry.load_graph(item["id"])
            return module

        def assistant():
            # R09 @f895c30: template answers from verified server facts (no key, no network). Facts come
            # from R02's PUBLIC object view and R07 prepared cases; provider/extractor stay None
            # (no live LLM in this build). Client-supplied facts are rejected by R09 (400).
            api = importlib.import_module("agent.civic_assistant.api")
            store_service = gateway.service("store")
            if store_service is None:
                raise ModuleNotDelivered("assistant needs the object store")
            load_scenario = None
            try:
                scen_registry = importlib.import_module("engine.civic_scenarios.registry")
                scen_compare = importlib.import_module("engine.civic_scenarios.compare")
                load_scenario = api.r07_case_loader(scen_registry.list_cases, scen_registry.load_graph,
                                                    scen_compare.compare, result_cache=gateway.scenario_results())
            except ModuleNotFoundError as exc:
                if not _role_package_missing(exc):
                    raise
                load_scenario = None
            return api.AssistantEndpoint(load_public_object=api.r02_public_loader(store_service),
                                         load_scenario_result=load_scenario, provider=None, extractor=None,
                                         resolve_principal=store_service.resolve_principal)

        gateway = cls({"store": store, "feedback": feedback, "scenarios": scenarios, "assistant": assistant})
        gateway.db_path = db_path  # раунд 14: та же база для жалоб v2 (R09)
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
            except (ModuleNotFoundError, ModuleNotDelivered) as exc:
                if not (isinstance(exc, ModuleNotDelivered) or _role_package_missing(exc)):
                    self._failed[name] = "init_failed"
                    LOGGER.exception("civic module %s failed to start", name)
                    return None
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
        if "feedback" in result:
            result["feedback"]["classifier"] = dict(self.classifier_status)
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
            reply = self._scenarios(service, method, full_path, query, body)
            if (method == "POST" and rel_path == "/scenarios/compare" and isinstance(reply, dict)
                    and reply.get("status") == 200):
                # The assistant may explain exactly this computation as scenario_id "result:<result_digest>".
                self._remember_scenario(body, (reply.get("body") or {}).get("data"))
            return reply
        if owner == "assistant":
            if rel_path.startswith("/staff/"):
                # Staff extraction: the gateway enforces R02 session + CSRF + origin like other staff POSTs.
                store = self.service("store")
                if store is None:
                    return civic_error(503, "module_unavailable", "Модуль доступа редактора не подключён.")
                _, denied = store.require_staff(context, unsafe=True)
                if denied:
                    return denied
            return service.handle(method, full_path, query, body, context)
        if owner == "feedback":
            store = self.service("store")
            principal = store.resolve_principal(context) if store is not None else None
            return service.handle(method, full_path, query, body, principal, context)
        return civic_error(503, "module_unavailable",
                           f"Модуль «{CIVIC_MODULE_LABELS[owner]}» не подключён в этой сборке.")


# ---------------------------------------------------------------------------
# API v2 (раунд 14, research/round-14/CONTRACT.md §7). Всё под /api/civic/v2/.
#
# Шлюз владеет только транспортом: адреса, Host/Origin, размер, разбор и проверка параметров.
# Считают модули ролей — обычные Python-функции. Для каждого маршрута ниже записано, у какой роли,
# в каком модуле и под каким именем шлюз ищет функцию. Нет модуля или функции — ответ 503
# {"error": "module_not_ready", "module": ..., "role": ...}; приложение при этом работает дальше.
#
# Формат v2 проще, чем у v1: успешный ответ — сам JSON из функции (без обёртки ok/data),
# ошибка — {"error": код, "message": текст по-русски, ...}.
#
# Как функция сообщает об ошибке (подробно — research/round-14-results/R01/INTEGRATION.txt):
#   return {...}                      -> 200 и этот объект
#   return (201, {...})               -> свой код ответа
#   raise ValueError("текст")         -> 400 bad_request
#   raise LookupError / KeyError      -> 404 not_found
#   raise PermissionError             -> 403 forbidden
#   исключение с атрибутами status (int 400..599) и code (str) -> этот код; message — атрибут message или str(exc)
#   любое другое исключение           -> 500 internal (подробности только в журнале сервера)
# Необязательные именованные параметры context (заголовки, cookies, адрес) и principal
# ({"username", "role"} сотрудника или None) передаются, только если функция их объявила.
CIVIC_V2_PREFIX = "/api/civic/v2"
CATEGORIES_V2_FILE = ROOT / "research" / "round-14" / "categories_v2.json"
# Город с запасом: координаты вне этого прямоугольника — точно ошибка ввода (CONTRACT §8).
ASTANA_BOUNDS = (70.9, 50.9, 71.9, 51.4)
V2_TEXT_MAX = 5000
V2_DEVICE_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
V2_DISTRICT = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")
V2_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class V2Handler:
    """Где живёт функция маршрута: роль, модули-кандидаты (первый найденный), имя функции, вид вызова.

    kind="function" — функция по CONTRACT §7, шлюз заранее проверяет параметры (R04, R06, R12);
    kind="raw"      — роль сама разбирает запрос: fn(path, parse_qs(query)) -> (status, body) (R07, R08);
    kind="service"  — сервис роли отвечает целиком: make_service(db_path).handle(method, path, query, body,
                      principal, context) -> {"status","headers","body"} в конверте ok/data (R09; его фронтенд
                      ждёт этот конверт). Сотрудника и CSRF такой сервис проверяет сам по principal R02.
    """

    def __init__(self, role, modules, function, staff=False, kind="function", strip_prefix=False):
        self.role, self.modules, self.function, self.staff = role, tuple(modules), function, staff
        self.kind = kind
        # strip_prefix: raw-обработчик ждёт путь без /api/civic/v2 (R12 engine.civic_geo.api.handle).
        self.strip_prefix = strip_prefix


# (метод, шаблон пути, ключ маршрута). {id} проверяется тем же правилом CIVIC_ID, что и в v1.
V2_ROUTES = (
    ("GET", ("modules",), "modules"),
    ("POST", ("classify",), "classify"),
    ("POST", ("similar",), "similar"),
    ("GET", ("targets",), "targets"),
    # R09 жалобы v2 (ui.civic_feedback.v2.integration.ROUTES @ da295be). Порядок важен: точные пути раньше {id}.
    ("GET", ("categories",), "complaints.categories"),
    ("GET", ("complaints",), "complaints.list"),
    ("POST", ("complaints",), "complaints.create"),
    ("GET", ("complaints", "mine"), "complaints.mine"),
    ("GET", ("complaints", "events"), "complaints.events"),
    ("GET", ("complaints", "summary"), "complaints.summary"),
    ("GET", ("complaints", "place"), "complaints.place"),
    ("GET", ("complaints", "{id}"), "complaints.get"),
    ("POST", ("complaints", "{id}", "metoo"), "complaints.metoo"),
    ("POST", ("complaints", "{id}", "status"), "complaints.status"),
    ("POST", ("complaints", "{id}", "duplicate"), "complaints.duplicate"),
    # R07 тепловая карта @ 5a97636 (ui.civic_heat.api.handle_get) и R08 «Картина дня» @ 9f1d9c0.
    ("GET", ("heat",), "heat"),
    ("GET", ("heat", "meta"), "heat.meta"),
    ("GET", ("heat", "target"), "heat.target"),
    ("GET", ("akim", "summary"), "akim.summary"),
    # R12 точность карты @ d13f49a: привязка к улицам и дворам для редактора и формы (только чтение).
    ("GET", ("street-segment",), "geo.segment"),
    ("GET", ("street-snap",), "geo.snap"),
    ("GET", ("objects-near",), "geo.objects"),
    ("GET", ("yard",), "geo.yard"),
    ("GET", ("geo", "status"), "geo.status"),
    ("GET", ("proposals",), "proposals.list"),
    ("POST", ("proposals",), "proposals.create"),
    # R06 @ 7031afa: точные пути (summary, lagging) — раньше шаблонов с {id}.
    ("GET", ("proposals", "summary"), "proposals.summary"),
    ("GET", ("proposals", "{id}"), "proposals.get"),
    ("POST", ("proposals", "{id}", "vote"), "proposals.vote"),
    ("POST", ("proposals", "{id}", "approve"), "proposals.approve"),
    ("POST", ("proposals", "{id}", "reject"), "proposals.reject"),
    ("POST", ("proposals", "{id}", "withdraw"), "proposals.withdraw"),
    ("GET", ("objects",), "objects.list"),
    ("GET", ("objects", "lagging"), "objects.lagging"),
    ("GET", ("objects", "{id}"), "objects.get"),
    ("PUT", ("objects", "{id}", "stage"), "objects.stage"),
    ("GET", ("staff", "objects", "{id}", "stage"), "objects.stage.get"),
    # R13 @ 8705829: прогноз проблемных территорий (прототип на синтетике, evidence_type="synthetic").
    ("GET", ("forecast",), "forecast"),
)
# Ожидаемые имена. Если роль назвала функцию иначе — она пишет это в своём INTEGRATION.txt, R01 правит таблицу.
V2_HANDLERS = {
    "classify": V2Handler("R04", ("ui.civic_ml_api",), "classify"),
    "similar": V2Handler("R04", ("ui.civic_ml_api",), "similar"),
    "targets": V2Handler("R12", ("engine.civic_geo",), "targets"),
    **{key: V2Handler("R09", ("ui.civic_feedback.v2.integration",), "make_service", kind="service") for key in (
        "complaints.categories", "complaints.list", "complaints.create", "complaints.mine", "complaints.events",
        "complaints.summary", "complaints.place", "complaints.get", "complaints.metoo", "complaints.status",
        "complaints.duplicate")},
    **{key: V2Handler("R07", ("ui.civic_heat.api",), "handle_get", kind="raw") for key in ("heat", "heat.meta", "heat.target")},
    "akim.summary": V2Handler("R08", ("ui.civic_akim.api",), "handle_get", kind="raw"),
    **{key: V2Handler("R12", ("engine.civic_geo.api",), "handle", kind="raw", strip_prefix=True)
       for key in ("geo.segment", "geo.snap", "geo.objects", "geo.yard", "geo.status")},
    "proposals.list": V2Handler("R06", ("ui.civic_store.v2", "ui.civic_store"), "list_proposals"),
    "proposals.create": V2Handler("R06", ("ui.civic_store.v2", "ui.civic_store"), "create_proposal", staff=True),
    "proposals.vote": V2Handler("R06", ("ui.civic_store.v2", "ui.civic_store"), "vote_proposal"),
    "objects.list": V2Handler("R06", ("ui.civic_store.v2", "ui.civic_store"), "list_objects"),
    "objects.stage": V2Handler("R06", ("ui.civic_store.v2", "ui.civic_store"), "set_object_stage", staff=True),
    "proposals.summary": V2Handler("R06", ("ui.civic_store.v2",), "proposals_summary"),
    "proposals.get": V2Handler("R06", ("ui.civic_store.v2",), "get_proposal"),
    "proposals.approve": V2Handler("R06", ("ui.civic_store.v2",), "decide_proposal", staff=True),
    "proposals.reject": V2Handler("R06", ("ui.civic_store.v2",), "decide_proposal", staff=True),
    "proposals.withdraw": V2Handler("R06", ("ui.civic_store.v2",), "decide_proposal", staff=True),
    "objects.lagging": V2Handler("R06", ("ui.civic_store.v2",), "lagging_objects"),
    "objects.get": V2Handler("R06", ("ui.civic_store.v2",), "get_object"),
    "objects.stage.get": V2Handler("R06", ("ui.civic_store.v2",), "get_object_stage", staff=True),
    "forecast": V2Handler("R13", ("ui.civic_forecast",), "forecast_response"),
}


def v2_error(status, code, message, **extra):
    body = {"error": code, "message": message}
    body.update(extra)
    return {"status": status, "headers": {}, "body": body}


class V2BadRequest(ValueError):
    """Неверный параметр запроса: field — имя параметра, message — что исправить (по-русски)."""

    def __init__(self, field, message):
        super().__init__(message)
        self.field, self.message = field, message


def load_category_ids(path=CATEGORIES_V2_FILE):
    """Id категорий v2 из единого источника (CONTRACT §3). Нет файла — проверка категории отключается."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return frozenset(item["id"] for item in data["categories"])
    except (OSError, ValueError, KeyError, TypeError):
        LOGGER.warning("categories_v2.json не прочитан: категория в API v2 не проверяется")
        return None


def _v2_number(raw, field, low, high):
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise V2BadRequest(field, f"{field}: нужно число.") from None
    if not (low <= value <= high):  # NaN тоже не проходит это сравнение
        raise V2BadRequest(field, f"{field}: число вне допустимого диапазона.")
    return value


def _v2_int(raw, field, low, high):
    if isinstance(raw, bool) or (isinstance(raw, float) and not raw.is_integer()):
        raise V2BadRequest(field, f"{field}: нужно целое число.")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise V2BadRequest(field, f"{field}: нужно целое число.") from None
    if not low <= value <= high:
        raise V2BadRequest(field, f"{field}: число вне допустимого диапазона.")
    return value


def _v2_bbox(raw):
    """bbox=minLon,minLat,maxLon,maxLat -> кортеж из 4 чисел внутри Астаны (с запасом)."""
    parts = str(raw).split(",")
    if len(parts) != 4:
        raise V2BadRequest("bbox", "bbox: четыре числа через запятую: minLon,minLat,maxLon,maxLat.")
    lon1, lat1, lon2, lat2 = (_v2_number(p, "bbox", -180, 180) for p in parts)
    if lon1 >= lon2 or lat1 >= lat2:
        raise V2BadRequest("bbox", "bbox: сначала меньшие координаты, потом большие.")
    w, s, e, n = ASTANA_BOUNDS
    if lon2 < w or lon1 > e or lat2 < s or lat1 > n:
        raise V2BadRequest("bbox", "bbox: область вне Астаны.")
    return (lon1, lat1, lon2, lat2)


def _v2_point(raw, field="point"):
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise V2BadRequest(field, f"{field}: нужна пара [долгота, широта].")
    lon = _v2_number(raw[0], field, ASTANA_BOUNDS[0], ASTANA_BOUNDS[2])
    lat = _v2_number(raw[1], field, ASTANA_BOUNDS[1], ASTANA_BOUNDS[3])
    return [lon, lat]


def _v2_text(raw, field="text"):
    if not isinstance(raw, str) or not raw.strip():
        raise V2BadRequest(field, "Напишите текст обращения.")
    if len(raw) > V2_TEXT_MAX:
        raise V2BadRequest(field, f"Текст длиннее {V2_TEXT_MAX} символов.")
    return raw


class CivicV2Gateway:
    """Маршрутизатор API v2: проверяет параметры и вызывает функцию модуля роли."""

    def __init__(self, store_gateway=None, modules=None, category_ids=None, db_path=None, demo=None):
        # store_gateway — шлюз v1: из него берётся R02 для проверки сессии сотрудника.
        self.store_gateway = store_gateway
        # Та же SQLite, что у v1 (R09 хранит жалобы v2 в своих таблицах рядом с v1).
        self.db_path = db_path if db_path is not None else getattr(store_gateway, "db_path", None)
        # Демо-сборка (run-city.bat, CIVIC_DEMO=1): к жалобам R09 добавляется синтетический набор R07 (demo: true).
        self.demo = (os.environ.get("CIVIC_DEMO") == "1") if demo is None else bool(demo)
        # modules: {имя_модуля: объект} — подмена для тестов; иначе importlib.
        self._override = dict(modules) if modules is not None else None
        self._resolved = {}  # route_key -> (callable | None, причина, имя модуля)
        self._services = {}  # модуль -> экземпляр сервиса (kind="service")
        self._lock = threading.RLock()
        self._wired = False
        self.category_ids = load_category_ids() if category_ids is None else frozenset(category_ids)

    # --- поиск функций модулей ---------------------------------------------
    def _import(self, name):
        if self._override is not None:
            return self._override.get(name)
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            missing = getattr(exc, "name", None) or ""
            # Нет самого модуля (или его пакета) — «ещё не сдан». Нет зависимости внутри модуля — сбой.
            if name == missing or name.startswith(missing + "."):
                return None
            raise

    def resolve(self, key):
        """(функция | None, причина, модуль). Причина: ready | module_not_ready | module_failed."""
        with self._lock:
            if key in self._resolved:
                return self._resolved[key]
            handler = V2_HANDLERS[key]
            result = (None, "module_not_ready", handler.modules[0])
            for name in handler.modules:
                try:
                    module = self._import(name)
                except Exception:
                    LOGGER.exception("API v2: модуль %s (%s) не загрузился", name, handler.role)
                    result = (None, "module_failed", name)
                    break
                fn = getattr(module, handler.function, None) if module is not None else None
                if callable(fn) and handler.kind == "service":
                    service = self._service(name, fn)
                    fn = getattr(service, "handle", None)
                    if not callable(fn):
                        result = (None, "module_failed" if self.db_path else "module_not_ready", name)
                        break
                if callable(fn):
                    result = (fn, "ready", name)
                    break
            self._resolved[key] = result
            return result

    def _service(self, name, factory):
        """Один экземпляр сервиса роли на процесс (R09: make_service(db_path)); None — нет базы или сбой."""
        if name in self._services:
            return self._services[name]
        service = None
        if self.db_path is not None:
            try:
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
                service = factory(str(self.db_path))
            except Exception:
                LOGGER.exception("API v2: сервис %s не запустился", name)
        self._services[name] = service
        return service

    def wire(self):
        """Связать модули раунда 14 (один раз): жалобы R09 -> тепловая карта R07 -> «Картина дня» R08.

        - Источник жалоб для карты — хранилище R09 (те же записи, что видит житель); в демо-сборке к нему
          добавляется синтетический набор R07 (demo: true), чтобы карта не была пустой.
        - Новая жалоба, «Я тоже», смена статуса (подписка R09) сбрасывают кэш карты — цвет меняется сразу.
        - R08 берёт записи у того же сервиса карты, поэтому числа «Картины дня» совпадают с картой.
        Подмена модулей в тестах (modules=...) связку не трогает.
        """
        with self._lock:
            if self._wired or self._override is not None:
                return
            self._wired = True
        complaints, _reason, _module = self.resolve("complaints.list")
        store = getattr(getattr(complaints, "__self__", None), "store", None)
        try:
            heat = self._import("ui.civic_heat")
        except Exception:
            LOGGER.exception("API v2: тепловая карта (R07) не загрузилась")
            heat = None
        if heat is not None and store is not None:
            demo_records = []
            if self.demo:
                try:
                    from datetime import datetime, timezone
                    demo_records = list(importlib.import_module("ui.civic_heat.demo_seed").demo_records(
                        now=datetime.now(timezone.utc)))
                except Exception:
                    LOGGER.exception("API v2: демо-набор R07 не построен")

            def source(since):
                return demo_records + store.list(since=since)

            heat.configure(source=source, **self._cell_resolver())
            store.subscribe(lambda _event: heat.invalidate())
            LOGGER.info("civic-v2: heat <- R09 complaints%s", " + R07 demo set" if demo_records else "")
        try:
            akim = self._import("ui.civic_akim")
            if akim is not None and hasattr(akim, "configure"):
                akim.configure()
        except Exception:
            LOGGER.exception("API v2: «Картина дня» (R08) не настроилась")

    def _cell_resolver(self):
        """Ячейки «примерного места» R09 рисуются там, где их посчитал R09.

        R09 (автор id ячейки) и R07 считают сетку 150 м от разных углов (70.9/50.8 и 71.0/50.8) — без этого
        адаптера жалоба из Нуры попадала на карту на ~7 км восточнее. Цели R09 помечены approximate: true;
        для них контур — ui.civic_feedback.v2.record.cell_polygon и подпись «примерное место» (CONTRACT §8.4).
        Остальные цели (в т. ч. демо-ячейки R07) R07 решает сам. Передано R07/R09: договориться об одной сетке.
        """
        try:
            targets = self._import("ui.civic_heat.targets")
            record = self._import("ui.civic_feedback.v2.record")
        except Exception:
            return {}
        if targets is None or record is None or not hasattr(record, "cell_polygon"):
            return {}

        class R09CellResolver(targets.TargetResolver):
            def _resolve(self, kind, tid, target, point):
                if kind == "area" and tid.startswith("cell-") and (target or {}).get("approximate") is True:
                    ring = record.cell_polygon(tid)
                    if ring:
                        return {"geometry": {"type": "Polygon", "coordinates": [ring]}, "label_ru": "Примерное место",
                                "label_kk": "Шамамен орны", "approximate": True, "source": "r09-cell"}
                return super()._resolve(kind, tid, target, point)

        return {"resolver": R09CellResolver()}

    def modules(self):
        """Состояние каждого маршрута v2 — для оболочки и приёмки (R10)."""
        out = {}
        for _method, _pattern, key in V2_ROUTES:
            if key == "modules":
                continue
            handler = V2_HANDLERS[key]
            fn, reason, module = self.resolve(key)
            out[key] = {"role": handler.role, "module": module, "function": handler.function,
                        "status": "ready" if fn else reason}
        return out

    # --- разбор параметров маршрутов -------------------------------------------
    def _category(self, raw, required=False):
        if raw in (None, ""):
            if required:
                raise V2BadRequest("category", "category: выберите категорию.")
            return None
        if not isinstance(raw, str) or (self.category_ids is not None and raw not in self.category_ids):
            raise V2BadRequest("category", "category: неизвестная категория.")
        return raw

    def arguments(self, key, params, query, body):
        """Именованные аргументы функции (только kind="function"). Ошибка ввода — V2BadRequest (ответ 400)."""
        q = {k: v[-1] for k, v in parse_qs(query or "", keep_blank_values=True).items()}
        body = body if isinstance(body, dict) else {}
        opt = lambda name: q.get(name) not in (None, "")  # noqa: E731 — короткая проверка «параметр задан»
        if key == "classify":
            return {"text": _v2_text(body.get("text"))}
        if key == "similar":
            args = {"text": _v2_text(body.get("text"))}
            args["point"] = _v2_point(body["point"]) if body.get("point") is not None else None
            args["days"] = _v2_int(body["days"], "days", 1, 365) if body.get("days") is not None else None
            return args
        if key == "targets":
            if not (opt("lon") and opt("lat")):
                raise V2BadRequest("lon", "Нужны lon и lat точки.")
            return {"lon": _v2_number(q["lon"], "lon", ASTANA_BOUNDS[0], ASTANA_BOUNDS[2]),
                    "lat": _v2_number(q["lat"], "lat", ASTANA_BOUNDS[1], ASTANA_BOUNDS[3]),
                    "category": self._category(q.get("category"))}
        district = q.get("district") or None
        if district is not None and not V2_DISTRICT.match(district):
            raise V2BadRequest("district", "district: неизвестный район.")
        if key == "forecast":
            month = q.get("month") or None
            if month is not None and not re.match(r"^20\d{2}-(0[1-9]|1[0-2])$", month):
                raise V2BadRequest("month", "month: месяц в формате ГГГГ-ММ.")
            return {"month": month, "district": district, "k": _v2_int(q["k"], "k", 1, 50) if opt("k") else 10}
        if key == "proposals.list":
            device = q.get("device_id") or None
            if device is not None and not V2_DEVICE_ID.match(device):
                raise V2BadRequest("device_id", "device_id: строка 8–128 символов.")
            status = q.get("status") or None
            if status is not None and not re.fullmatch(r"[a-z_,]{1,60}", status):
                raise V2BadRequest("status", "status: неизвестный статус.")
            return {"bbox": _v2_bbox(q["bbox"]) if opt("bbox") else None, "district": district,
                    "status": status, "device_id": device}
        if key == "objects.list":
            return {"bbox": _v2_bbox(q["bbox"]) if opt("bbox") else None, "district": district}
        if key == "objects.lagging":
            return {"district": district}
        if key == "proposals.summary":
            since = q.get("since") or None
            if since is not None and not V2_DATE.match(since):
                raise V2BadRequest("since", "since: дата в формате ГГГГ-ММ-ДД.")
            return {"since": since}
        if key == "proposals.get":
            device = q.get("device_id") or None
            if device is not None and not V2_DEVICE_ID.match(device):
                raise V2BadRequest("device_id", "device_id: строка 8–128 символов.")
            return {"proposal_id": params["id"], "device_id": device}
        if key in ("proposals.approve", "proposals.reject", "proposals.withdraw"):
            return {"proposal_id": params["id"], "action": key.split(".")[1], "body": body}
        if key in ("objects.get", "objects.stage.get"):
            return {"object_id": params["id"]}
        if key == "proposals.create":
            return {"body": body}
        if key == "proposals.vote":
            value = body.get("value")
            if isinstance(value, bool) or value not in (1, -1):
                raise V2BadRequest("value", "value: 1 (за) или -1 (против).")
            device = body.get("device_id")
            if not isinstance(device, str) or not V2_DEVICE_ID.match(device):
                raise V2BadRequest("device_id", "device_id: строка 8–128 символов.")
            return {"proposal_id": params["id"], "value": value, "device_id": device}
        if key == "objects.stage":
            return {"object_id": params["id"], "body": body}
        return {}

    # --- вызов ------------------------------------------------------------------
    def _staff(self, context):
        """(principal_dict, None) или (None, ответ-ошибка) — сессия сотрудника R02 (как в v1)."""
        store = self.store_gateway.service("store") if self.store_gateway is not None else None
        if store is None or not hasattr(store, "require_staff"):
            return None, v2_error(503, "module_not_ready", "Вход сотрудника пока не подключён.",
                                  module="ui.civic_store", role="R06")
        principal, denied = store.require_staff(context, unsafe=True)
        if denied:
            error = (denied.get("body") or {}).get("error") or {}
            return None, v2_error(denied.get("status", 403), error.get("code", "forbidden"),
                                  error.get("message", "Недостаточно прав."))
        return {"username": principal.username, "role": principal.role}, None

    @staticmethod
    def _call(fn, args, context, principal):
        import inspect  # локально: нужен только здесь
        try:
            accepted = inspect.signature(fn).parameters
            takes_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in accepted.values())
        except (TypeError, ValueError):
            accepted, takes_kwargs = {}, False
        for name, value in (("context", context), ("principal", principal)):
            if takes_kwargs or name in accepted:
                args[name] = value
        if accepted and not takes_kwargs:
            # Функция со старой сигнатурой (без нового необязательного параметра, напр. district) не должна падать.
            args = {k: v for k, v in args.items() if k in accepted}
        return fn(**args)

    def handle(self, method, rel_path, query, body, context):
        segments = rel_path.strip("/").split("/") if rel_path.strip("/") else []
        if rel_path != "/" + "/".join(segments) or any(not s for s in segments):
            return v2_error(404, "not_found", "Адрес API не найден.")
        allowed, found = set(), None
        for route_method, pattern, key in V2_ROUTES:
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
                    found = (key, params)
                    break
                allowed.add(route_method)
        if found is None:
            if allowed:
                reply = v2_error(405, "method_not_allowed", "Метод не поддерживается для этого адреса.")
                reply["headers"]["Allow"] = ",".join(sorted(allowed))
                return reply
            return v2_error(404, "not_found", "Адрес API не найден.")
        key, params = found
        if key == "modules":
            return {"status": 200, "headers": {}, "body": {"modules": self.modules()}}
        handler = V2_HANDLERS[key]
        if handler.kind != "function":
            self.wire()
        fn, reason, module = self.resolve(key)
        if fn is None:
            message = ("Модуль не загрузился, подробности в журнале сервера." if reason == "module_failed"
                       else "Эта часть ещё не подключена в сборке.")
            return v2_error(503, reason, message, module=module, role=handler.role)
        if handler.kind == "raw":
            return self._raw(fn, key, rel_path if handler.strip_prefix else CIVIC_V2_PREFIX + rel_path, query, module, handler)
        if handler.kind == "service":
            return self._delegate(fn, method, rel_path, query, body, context, module, handler)
        try:
            args = self.arguments(key, params, query, body)
        except V2BadRequest as exc:
            return v2_error(400, "bad_request", exc.message, field=exc.field)
        principal = None
        if handler.staff:
            principal, denied = self._staff(context)
            if denied:
                return denied
        try:
            result = self._call(fn, args, context, principal)
        except V2BadRequest as exc:
            return v2_error(400, "bad_request", exc.message, field=exc.field)
        except PermissionError as exc:
            return v2_error(403, "forbidden", str(exc) or "Недостаточно прав.")
        except Exception as exc:  # ошибки модуля -> понятный ответ, приложение не падает
            status = getattr(exc, "status", None)
            if isinstance(status, int) and not isinstance(status, bool) and 400 <= status <= 599:
                code = getattr(exc, "code", None)
                extra = {}
                # R06: поля с ошибкой (422) и текущая ревизия (409) — форма подсвечивает поле и показывает новую версию.
                if isinstance(getattr(exc, "fields", None), dict) and exc.fields:
                    extra["fields"] = exc.fields
                if isinstance(getattr(exc, "current_revision", None), int):
                    extra["current_revision"] = exc.current_revision
                return v2_error(status, code if isinstance(code, str) and code else "error",
                                str(getattr(exc, "message", None) or exc)[:300], **extra)
            if isinstance(exc, (LookupError,)):
                return v2_error(404, "not_found", "Запись не найдена.")
            if isinstance(exc, ValueError):
                return v2_error(400, "bad_request", str(exc)[:300] or "Неверные данные запроса.")
            LOGGER.exception("API v2: %s (%s.%s) упал", key, module, handler.function)
            return v2_error(500, "internal", "Не удалось выполнить запрос. Попробуйте ещё раз.")
        status = 200
        if (isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], int)
                and not isinstance(result[0], bool)):
            status, result = result
        if not isinstance(result, dict) or not 200 <= status <= 599:
            LOGGER.error("API v2: %s вернул не объект JSON", key)
            return v2_error(500, "bad_module_response", "Модуль вернул некорректный ответ.")
        return {"status": status, "headers": {}, "body": result}

    @staticmethod
    def _raw(fn, key, path, query, module, handler):
        """R07/R08/R12: fn(path, parse_qs(query)) -> (status, body) | None; роль сама проверяет параметры."""
        try:
            reply = fn(path, parse_qs(query or "", keep_blank_values=True))
            if reply is None:
                return v2_error(404, "not_found", "Адрес API не найден.")
            status, body = reply
        except Exception:
            LOGGER.exception("API v2: %s (%s.%s) упал", key, module, handler.function)
            return v2_error(500, "internal", "Не удалось выполнить запрос. Попробуйте ещё раз.")
        if (not isinstance(status, int) or isinstance(status, bool) or not 200 <= status <= 599
                or not isinstance(body, dict)):
            LOGGER.error("API v2: %s вернул некорректный ответ", key)
            return v2_error(500, "bad_module_response", "Модуль вернул некорректный ответ.")
        return {"status": status, "headers": {}, "body": body}

    def _delegate(self, service_handle, method, rel_path, query, body, context, module, handler):
        """R09: сервис отвечает целиком (конверт ok/data). principal — сессия R02 или None."""
        store = self.store_gateway.service("store") if self.store_gateway is not None else None
        principal = store.resolve_principal(context) if store is not None and hasattr(store, "resolve_principal") else None
        try:
            reply = service_handle(method, CIVIC_V2_PREFIX + rel_path, query or "", body, principal, context or {})
        except Exception:
            LOGGER.exception("API v2: %s.%s упал", module, handler.function)
            return v2_error(500, "internal", "Не удалось выполнить запрос. Попробуйте ещё раз.")
        if reply is None:
            return v2_error(404, "not_found", "Адрес API не найден.")
        if (not isinstance(reply, dict) or not isinstance(reply.get("status"), int)
                or not isinstance(reply.get("body"), dict)):
            LOGGER.error("API v2: %s вернул некорректный ответ", module)
            return v2_error(500, "bad_module_response", "Модуль вернул некорректный ответ.")
        return {"status": reply["status"], "headers": dict(reply.get("headers") or {}), "body": reply["body"]}


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
            # The page carries staff actions: no framing by another (e.g. neighbour loopback) origin.
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
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

    def civic_send(self, reply, v2=False):
        status = reply.get("status") if isinstance(reply, dict) else None
        body = reply.get("body") if isinstance(reply, dict) else None
        if (not isinstance(status, int) or isinstance(status, bool) or not 200 <= status <= 599
                or not isinstance(body, dict) or (not v2 and not isinstance(body.get("ok"), bool))):
            LOGGER.error("civic service returned a malformed response")
            reply = (v2_error if v2 else civic_error)(500, "bad_service_response", "Сервис вернул некорректный ответ.")
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
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            for name, value in extra:
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except CLIENT_DISCONNECTED:
            self.close_connection = True

    def civic_request(self, method, v2=False):
        """Общий транспорт v1 и v2 (раунд 14): те же проверки Host/Origin/размера/JSON, разный формат ответа."""
        parsed = urlsplit(self.path)
        rel_path = parsed.path[len(CIVIC_V2_PREFIX if v2 else CIVIC_PREFIX):] or "/"
        error = v2_error if v2 else civic_error
        send = (lambda reply: self.civic_send(reply, v2=True)) if v2 else self.civic_send
        has_body = method in ("POST", "PUT")
        if not self.host_allowed():
            if has_body:
                self.discard_body()
            send(error(403, "forbidden_host", "Откройте интерфейс через адрес этого сервера."))
            return
        if has_body:
            if self.origin_state() is False:
                self.discard_body()
                send(error(403, "cross_origin", "Запрос с другого сайта отклонён."))
                return
        if len(parsed.query) > CIVIC_MAX_QUERY:
            if has_body:
                self.discard_body()
            send(error(400, "query_too_long", "Слишком длинная строка запроса."))
            return
        query = parsed.query  # raw; each service parses and bounds it (R02 parse_query)
        body = None
        if self.headers.get("Transfer-Encoding"):
            # Content-Length only; a chunked body would stay in the stream (adopted from R02 adapter).
            self.close_connection = True
            send(error(411, "length_required", "Нужен Content-Length; chunked не поддерживается."))
            return
        if has_body:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if not 0 < length <= CIVIC_MAX_BODY:
                if CIVIC_MAX_BODY < length <= CIVIC_MAX_BODY * 2:
                    self.rfile.read(length)
                self.close_connection = True
                code = 413 if length > CIVIC_MAX_BODY else 400
                send(error(code, "too_large" if code == 413 else "empty_body",
                           "Слишком большой запрос." if code == 413 else "Пустой запрос."))
                return
            if self.headers.get_content_type() != "application/json":
                self.rfile.read(length)
                send(error(415, "unsupported_media_type", "Ожидается Content-Type: application/json."))
                return
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"), parse_constant=_invalid_number)
            except CLIENT_DISCONNECTED:
                self.close_connection = True
                return
            except (ValueError, UnicodeDecodeError, RecursionError):
                # RecursionError: pathologically nested JSON within the size limit.
                send(error(400, "invalid_json", "Тело запроса должно быть корректным JSON."))
                return
            if not isinstance(body, dict):
                send(error(400, "invalid_json", "Тело запроса должно быть JSON-объектом."))
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
        gateway = self.server.civic_v2 if v2 else self.server.civic
        try:
            reply = gateway.handle(method, rel_path, query, body, context)
        except Exception:
            # No body, cookies or provider details in the log or the reply.
            LOGGER.exception("civic handler failed for %s %s", method, rel_path)
            reply = error(500, "internal", "Не удалось выполнить запрос. Попробуйте ещё раз.")
        if reply is None:
            reply = error(404, "not_found", "Адрес API не найден.")
        send(reply)

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == CIVIC_PREFIX or path.startswith(CIVIC_PREFIX + "/"):
            self.civic_request("GET")
            return
        if path == CIVIC_V2_PREFIX or path.startswith(CIVIC_V2_PREFIX + "/"):
            self.civic_request("GET", v2=True)
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
        if path == CIVIC_V2_PREFIX or path.startswith(CIVIC_V2_PREFIX + "/"):
            self.civic_request("POST", v2=True)
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


    def _is_civic_path(self):
        raw = getattr(self, "path", "") or ""
        if not raw:
            # Protocol errors (e.g. 505) happen before parse_request stores self.path; a 414 is sent
            # before even requestline is set, so the raw bytes are the last resort.
            line = getattr(self, "requestline", "") or ""
            if not line:
                raw_line = getattr(self, "raw_requestline", b"") or b""
                line = raw_line[:4096].decode("iso-8859-1", "replace")
            words = line.split()
            raw = words[1] if len(words) >= 2 else ""
        try:
            path = urlsplit(raw).path
        except ValueError:
            return False
        if path == CIVIC_V2_PREFIX or path.startswith(CIVIC_V2_PREFIX + "/"):
            return "v2"
        return path == CIVIC_PREFIX or path.startswith(CIVIC_PREFIX + "/")

    def do_unsupported(self):
        """PUT/PATCH/DELETE/OPTIONS/TRACE: on civic paths the route table decides (404 for an unknown
        path, 405 with Allow for a known one, never a service call); elsewhere a JSON 405."""
        self.discard_body()
        self.close_connection = True
        civic = self._is_civic_path()
        if civic == "v2":
            rel_path = urlsplit(self.path).path[len(CIVIC_V2_PREFIX):] or "/"
            self.civic_send(self.server.civic_v2.handle(self.command, rel_path, "", None, {}), v2=True)
        elif civic:
            rel_path = urlsplit(self.path).path[len(CIVIC_PREFIX):] or "/"
            # No route accepts these methods, so handle() only produces 404/405 envelopes.
            self.civic_send(self.server.civic.handle(self.command, rel_path, "", None, {}))
        else:
            self.error_reply(405, "Метод не поддерживается.")

    def do_PUT(self):
        # PUT есть только в API v2 (PUT /objects/{id}/stage, CONTRACT §7); остальное — как прежде.
        if self._is_civic_path() == "v2":
            self.civic_request("PUT", v2=True)
        else:
            self.do_unsupported()

    do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_unsupported

    def send_error(self, code, message=None, explain=None):
        """Protocol errors raised by BaseHTTPRequestHandler (unknown method, 400/414/431/505) are
        answered with the civic JSON envelope on civic paths instead of an HTML page."""
        if not self._is_civic_path():
            return super().send_error(code, message, explain)
        self.close_connection = True
        # Python 3.13 leaves HTTP/0.9 here for an unsupported protocol version;
        # that suppresses all response headers, including our JSON content type.
        if self.request_version == "HTTP/0.9":
            self.request_version = "HTTP/1.0"
        v2 = self._is_civic_path() == "v2"
        error = v2_error if v2 else civic_error
        if code == 501:  # unknown method: semantically "not allowed on this resource"
            reply = error(405, "method_not_allowed", "Метод не поддерживается.")
        else:
            reply = error(code, "bad_request" if code == 400 else "http_error",
                          "Некорректный HTTP-запрос.")
        if not hasattr(self, "headers") or self.headers is None:
            self.headers = {}
        self.civic_send(reply, v2=v2)


def _invalid_number(value):
    raise ValueError("JSON должен содержать только конечные числа.")


def create_server(project: Path = ROOT, port: int = 8501, host: str = "127.0.0.1",
                  civic: CivicGateway | None = None, civic_db: Path | None = None, classifier: str | None = None,
                  civic_v2: "CivicV2Gateway | None" = None):
    backend = Backend(project)
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.backend = backend
    server.civic = civic if civic is not None else CivicGateway.for_project(Path(project), civic_db, classifier)
    # API v2 (раунд 14): сессию сотрудника проверяет тот же R02 из шлюза v1.
    server.civic_v2 = civic_v2 if civic_v2 is not None else CivicV2Gateway(server.civic)
    return server


def main():
    parser = argparse.ArgumentParser(description="Birge — обратная связь жителей и акимата Астаны")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--open", action="store_true", help="Открыть браузер после запуска")
    parser.add_argument("--civic-db", default=os.environ.get("CIVIC_DB_PATH") or os.environ.get("CIVIC_DB"),
                        help="SQLite городских объектов (по умолчанию .runtime/civic.sqlite3)")
    parser.add_argument("--civic-classifier", choices=("off", "r08"),
                        default="r08" if os.environ.get("CIVIC_R08_CLASSIFIER") == "1" else "off",
                        help="Подсказка категории сообщений (R08, обучена только на синтетике). По умолчанию off")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Порт должен быть от 1 до 65535.")
    try:
        server = create_server(port=args.port, host=args.host,
                               civic_db=resolve_db_path(args.civic_db), classifier=args.civic_classifier)
        # R12: граф улиц и дворы грузятся ~2 с — прогреваем в фоне, чтобы первый житель не ждал.
        try:
            threading.Thread(target=importlib.import_module("engine.civic_geo.api").warm_up, daemon=True).start()
        except Exception:  # R12 не сдан или сломан — /targets ответит 503, приложение работает
            LOGGER.info("civic-v2: R12 warm-up skipped")
    except OSError as exc:
        if getattr(exc, "winerror", None) == 10048 or getattr(exc, "errno", None) in (48, 98, 10048):
            parser.exit(1, "Порт занят. Закройте прежнее приложение или задайте другой PORT.\n")
        raise
    address = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    url = f"http://{address}:{args.port}"
    modules = server.civic.modules()
    print("civic-v1: " + ", ".join(f"{name}={item['status']}" for name, item in modules.items()), flush=True)
    ready_v2 = sorted({item["role"] for item in server.civic_v2.modules().values() if item["status"] == "ready"})
    print("civic-v2: ready " + (", ".join(ready_v2) if ready_v2 else "none yet"), flush=True)
    cls = server.civic.classifier_status
    print("classifier: " + ("off" if not cls["enabled"] else
          f"r08 {'connected' if cls['available'] else 'unavailable: ' + str(cls['reason'])}"
          + (f" ({cls.get('model_version')}, {cls.get('training_data_status')})" if cls["available"] else "")), flush=True)
    print(f"Birge: {url}\nОстановить — Ctrl+C", flush=True)
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
