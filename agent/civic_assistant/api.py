"""Пример безопасного HTTP-обработчика помощника для R01 (CONTRACT раздел 6).

    endpoint = AssistantEndpoint(load_public_object, load_scenario_result=None, provider=None)
    endpoint.handle(method, path, query, body, context) -> None | {status, headers, body}

None — путь не относится к помощнику. Ответ — конверт {ok:true,data} | {ok:false,error}.

POST /api/civic/v1/assistant  {question, object_id|null, scenario_id|null}
    Публичный. Тело принимает ровно эти три ключа: facts/context/answer/role и любые
    другие поля отклоняются (400) — клиент не передаёт доверенных фактов.
    Объект берётся только через load_public_object (тот же публичный маршрут, что у
    браузера, без cookie редактора). Черновик и несуществующий объект неразличимы:
    оба дают source=unavailable.
POST /api/civic/v1/staff/assistant/extract  — см. extract.py (только редактор, same-origin).

Модуль не открывает .env и не создаёт провайдера сам: R01 передаёт готовый provider
(или None — тогда честный шаблон).
"""

from __future__ import annotations

import threading
import time
from urllib.parse import quote

from agent.civic_assistant.answer import AssistantInputError, build_answer, detect_language, unavailable_answer
from agent.civic_assistant.facts import ID_RE, ContextError, build_verified_context

API_PREFIX = "/api/civic/v1"
ASSISTANT_PATH = API_PREFIX + "/assistant"
EXTRACT_PATH = API_PREFIX + "/staff/assistant/extract"
# Шлюз R01 передаёт сервисам путь без префикса (/assistant); принимаем обе формы.
_ASSISTANT_PATHS = (ASSISTANT_PATH, "/assistant")
_EXTRACT_PATHS = (EXTRACT_PATH, "/staff/assistant/extract")
HEADERS = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}
ALLOWED_KEYS = {"question", "object_id", "scenario_id"}
RATE_LIMIT = (20, 60.0)  # запросов на IP за окно, секунд


def _ok(data, status=200):
    return {"status": status, "headers": dict(HEADERS), "body": {"ok": True, "data": data}}


def _err(status, code, message, fields=None):
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return {"status": status, "headers": dict(HEADERS), "body": {"ok": False, "error": error}}


class RateLimiter:
    def __init__(self, limit: int, window_s: float, clock=time.monotonic):
        self.limit, self.window_s, self.clock = limit, window_s, clock
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self.clock()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self.window_s]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 10000:
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window_s}
            return True


def r02_public_loader(service, prefix: str = API_PREFIX):
    """Чтение объекта через ПУБЛИЧНЫЙ маршрут R02 GET /objects/{id} без сессии редактора.

    Сначала полный путь (/api/civic/v1/objects/{id}), затем относительный (/objects/{id}):
    R02 и шлюз R01 пока используют разные формы; None или 404 -> пробуем вторую форму.
    """
    def load(object_id: str):
        context = {"headers": {}, "client_ip": None, "is_same_origin": False, "cookies": {}}
        resp = None
        for base in dict.fromkeys((prefix, "")):
            resp = service.handle("GET", f"{base}/objects/{quote(object_id, safe='')}", {}, None, context)
            if isinstance(resp, dict) and resp.get("status") != 404:
                break
        if not isinstance(resp, dict) or resp.get("status") != 200:
            return None
        body = resp.get("body") or {}
        data = body.get("data") if body.get("ok") else None
        if not isinstance(data, dict) or not isinstance(data.get("item"), dict):
            return None
        return data["item"], data.get("history")
    return load


def r07_case_loader(list_cases, load_graph, compare):
    """scenario_id = case_id подготовленного кейса R07; payload/граф берёт сервер, не клиент."""
    cache: dict[str, dict] = {}
    lock = threading.Lock()

    def load(scenario_id: str):
        with lock:
            if scenario_id in cache:
                return cache[scenario_id]
        for case in list_cases():
            if isinstance(case, dict) and case.get("case_id") == scenario_id:
                payload = case["payload"]
                result = compare(payload, load_graph(payload["graph_id"]))
                with lock:
                    cache[scenario_id] = result
                return result
        return None
    return load


class AssistantEndpoint:
    def __init__(self, load_public_object, load_scenario_result=None, provider=None, *, extractor=None,
                 resolve_principal=None, rate_limiter=None, timeout_s: float = 8.0):
        self.load_public_object = load_public_object
        self.load_scenario_result = load_scenario_result
        self.provider = provider
        self.extractor = extractor
        self.resolve_principal = resolve_principal
        self.rate_limiter = rate_limiter or RateLimiter(*RATE_LIMIT)
        self.timeout_s = timeout_s

    def handle(self, method, path, query=None, body=None, context=None):
        if path not in _ASSISTANT_PATHS + _EXTRACT_PATHS:
            return None
        if method != "POST":
            return _err(405, "method_not_allowed", "только POST")
        context = context if isinstance(context, dict) else {}
        if not self.rate_limiter.allow(str(context.get("client_ip") or "unknown")):
            return _err(429, "rate_limited", "Слишком много вопросов подряд. Повторите через минуту.")
        if path in _EXTRACT_PATHS:
            from agent.civic_assistant.extract import handle_extract  # редакторский путь
            return handle_extract(body, context, self.resolve_principal, self.extractor, _ok, _err)
        return self._assistant(body)

    def _assistant(self, body):
        if not isinstance(body, dict):
            return _err(400, "invalid_body", "ожидается JSON-объект")
        extra = sorted(set(body) - ALLOWED_KEYS)
        if extra:
            return _err(400, "unexpected_fields", "клиент не передаёт факты или служебные поля", extra[:10])
        object_id, scenario_id = body.get("object_id"), body.get("scenario_id")
        for name, value in (("object_id", object_id), ("scenario_id", scenario_id)):
            if value is not None and (not isinstance(value, str) or not ID_RE.match(value)):
                return _err(422, "invalid_id", "недопустимый идентификатор", [name])
        if object_id is None and scenario_id is None:
            return _err(422, "missing_target", "нужен object_id или scenario_id", ["object_id", "scenario_id"])
        question = body.get("question")
        try:
            from agent.civic_assistant.answer import normalize_question
            lang = detect_language(normalize_question(question))
        except AssistantInputError as exc:
            status = 413 if exc.code == "question_too_long" else 422
            return _err(status, exc.code, "вопрос — непустая строка до 500 символов", ["question"])

        warnings = []
        item = history = scenario = None
        if object_id is not None:
            try:
                loaded = self.load_public_object(object_id)
            except Exception:  # noqa: BLE001 — хранилище недоступно: не раскрываем детали
                loaded = None
                warnings.append("object_store_error")
            if not loaded:
                return _ok(unavailable_answer(lang, "object_not_public_or_missing"))
            item, history = loaded
        if scenario_id is not None:
            try:
                scenario = self.load_scenario_result(scenario_id) if self.load_scenario_result else None
            except Exception:  # noqa: BLE001
                scenario = None
            if scenario is None:
                if item is None:
                    return _ok(unavailable_answer(lang, "scenario_not_found"))
                warnings.append("scenario_not_found")
                scenario_id = None
        try:
            ctx = build_verified_context(item, history, scenario, audience="public", scenario_id=scenario_id)
        except ContextError as exc:
            return _ok(unavailable_answer(lang, exc.code))
        answer = build_answer(question, ctx, self.provider, timeout_s=self.timeout_s)
        if warnings:
            answer["warnings"] = sorted(set(answer["warnings"]) | set(warnings))
        return _ok(answer)
