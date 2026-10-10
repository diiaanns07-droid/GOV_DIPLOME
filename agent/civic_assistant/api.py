"""Пример безопасного HTTP-обработчика помощника для R01 (CONTRACT раздел 6).

    endpoint = AssistantEndpoint(load_public_object, load_scenario_result=None, provider=None)
    endpoint.handle(method, path, query, body, context) -> None | {status, headers, body}

None — путь не относится к помощнику. Ответ — конверт {ok:true,data} | {ok:false,error}.

POST /api/civic/v1/assistant  {question, object_id|null, scenario_id|null, revision?}
    Публичный. Тело принимает только эти ключи: facts/context/answer/role и любые
    другие поля отклоняются (400) — клиент не передаёт доверенных фактов. revision —
    редакция карточки на экране; если опубликована другая, ответ — object_revision_changed.
    Объект берётся только через load_public_object (тот же публичный маршрут, что у
    браузера, без cookie редактора). Черновик и несуществующий объект неразличимы:
    оба дают source=unavailable.
POST /api/civic/v1/staff/assistant/extract  — см. extract.py (только редактор, same-origin).

Модуль не открывает .env и не создаёт провайдера сам: R01 передаёт готовый provider
(или None — тогда честный шаблон).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import sys
import threading
import time
from urllib.parse import quote

from agent.civic_assistant.answer import (AssistantInputError, build_answer, detect_language, prepend_notice,
                                          stale_revision_answer, unavailable_answer)
from agent.civic_assistant.facts import ID_RE, ContextError, build_verified_context

API_PREFIX = "/api/civic/v1"
ASSISTANT_PATH = API_PREFIX + "/assistant"
EXTRACT_PATH = API_PREFIX + "/staff/assistant/extract"
# Шлюз R01 передаёт сервисам путь без префикса (/assistant); принимаем обе формы.
_ASSISTANT_PATHS = (ASSISTANT_PATH, "/assistant")
_EXTRACT_PATHS = (EXTRACT_PATH, "/staff/assistant/extract")
HEADERS = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}
ALLOWED_KEYS = {"question", "object_id", "scenario_id", "revision"}
RATE_LIMIT = (20, 60.0)  # запросов на IP за окно, секунд
SCENARIO_INPUT_SCHEMA = "civic-assistant-scenario-input-v1"


def _reject_constant(value):
    raise ValueError("non-finite number " + value)


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


def _manifest_graph_info(manifest):
    """graph_id -> запись MANIFEST R07 (подпись, источник/дата снимка, лицензия) или None."""
    def info(graph_id):
        if manifest is None:
            return None
        try:
            entries = manifest().get("graphs") or []
        except Exception:  # noqa: BLE001 — сведения о сети необязательны для ответа
            return None
        return next((g for g in entries if isinstance(g, dict) and g.get("id") == graph_id), None)
    return info


def _scenario_input(result, payload, graph):
    return {"schema": SCENARIO_INPUT_SCHEMA, "result": result, "payload": payload, "graph": graph}


class ScenarioResultCache:
    """Результаты POST /scenarios/compare, посчитанные САМИМ сервером, для объяснения сравнения A/B.

    scenario_id = "result:" + result_digest движка. Клиент не передаёт метрик: шлюз R01 после успешного
    расчёта вызывает remember(payload, result). Сохраняется только проверенный ответ движка на этот вход
    (scenario.verify_user_result: result_digest, payload_digest, граф/режим/момент/точки/планы) и только
    компактная запись (scenario.make_entry: без edge_ids/node_ids маршрутов). Ограничения: число записей,
    TTL, размер одной записи и общий объём. Истёкший/вытесненный результат отличается от неизвестного
    (status() -> "expired"), но в обоих случаях помощник просит пересчитать, а не подставляет кейс.
    """

    def __init__(self, graph_info=None, *, max_items: int = 64, ttl_s: float = 3600.0,
                 max_entry_bytes: int = 64 * 1024, max_total_bytes: int = 2 * 1024 * 1024,
                 max_tombstones: int = 512, clock=time.monotonic, wall_clock=None):
        self.graph_info = graph_info  # None -> r07_case_loader подставит сведения MANIFEST
        self.max_items, self.ttl_s, self.clock = max_items, ttl_s, clock
        self.max_entry_bytes, self.max_total_bytes, self.max_tombstones = max_entry_bytes, max_total_bytes, max_tombstones
        self.wall_clock = wall_clock or (lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self._items: dict[str, tuple[float, int, dict]] = {}  # key -> (время, байты, запись)
        self._tombstones: dict[str, float] = {}
        self._rejected: dict[str, str] = {}  # "result:<digest>" -> код отказа: клиенту «не сохранён», а не «не найден»
        self._bytes = 0
        self._lock = threading.Lock()
        self.rejections: dict[str, int] = {}
        self.last_rejection: str | None = None

    def _reject(self, code, result=None):
        self.last_rejection = code
        self.rejections[code] = self.rejections.get(code, 0) + 1
        digest = result.get("result_digest") if isinstance(result, dict) else None
        if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
            with self._lock:
                self._rejected["result:" + digest] = code
                while len(self._rejected) > self.max_tombstones:
                    self._rejected.pop(next(iter(self._rejected)))
        return None

    def _drop(self, key, now):
        _t, size, _e = self._items.pop(key)
        self._bytes -= size
        self._tombstones[key] = now
        while len(self._tombstones) > self.max_tombstones:
            self._tombstones.pop(next(iter(self._tombstones)))

    def _expire(self, now):
        for key in [k for k, (t, _s, _e) in self._items.items() if now - t > self.ttl_s]:
            self._drop(key, now)

    def remember(self, payload, result) -> str | None:
        from agent.civic_assistant.scenario import make_entry, verify_user_result
        code = verify_user_result(payload, result)
        if code:
            return self._reject(code, result)
        inp = result["input"]
        graph = self.graph_info(inp.get("graph_id")) if self.graph_info else None
        entry = make_entry(result, payload, graph, kind="user_result", stored_at=self.wall_clock())
        size = len(json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if size > self.max_entry_bytes:
            return self._reject("entry_too_large", result)
        key = "result:" + result["result_digest"]
        with self._lock:
            now = self.clock()
            self._expire(now)
            if key in self._items:
                _t, old, _e = self._items.pop(key)
                self._bytes -= old
            self._items[key] = (now, size, entry)
            self._bytes += size
            self._tombstones.pop(key, None)
            self._rejected.pop(key, None)
            while self._items and (len(self._items) > self.max_items or self._bytes > self.max_total_bytes):
                self._drop(next(iter(self._items)), now)
        self.last_rejection = None
        return key

    def status(self, scenario_id) -> str:
        """"ok" | "expired" (хранился, но истёк/вытеснен) | "rejected" (сервер посчитал, но не сохранил: проверка
        или лимит размера) | "unknown" (сервер такого не считал или забыл давно)."""
        with self._lock:
            now = self.clock()
            self._expire(now)
            if scenario_id in self._items:
                return "ok"
            if scenario_id in self._tombstones:
                return "expired"
            return "rejected" if scenario_id in self._rejected else "unknown"

    def get(self, scenario_id):
        with self._lock:
            now = self.clock()
            self._expire(now)
            item = self._items.get(scenario_id)
            return item[2] if item else None

    def stats(self) -> dict:
        with self._lock:
            return {"items": len(self._items), "bytes": self._bytes, "tombstones": len(self._tombstones),
                    "rejections": dict(self.rejections)}


def remember_compare_response(cache: ScenarioResultCache, payload, response) -> str | None:
    """Для шлюза, у которого R07 http.handle без on_result (база 56538a3): после ответа POST /scenarios/compare.

    Берётся конверт, который сервер сам отдал клиенту ({ok:true,data:result+timing_ms}); timing_ms вне digest.
    С R07 1.1.0 то же делает http.handle(..., on_result=cache.remember).
    """
    if not isinstance(response, dict) or response.get("status") != 200:
        return None
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    data = body.get("data") if body.get("ok") is True else None
    return cache.remember(payload, data) if isinstance(data, dict) else None


def r07_case_loader(list_cases, load_graph, compare, manifest=None, *, result_cache=None):
    """scenario_id = case_id подготовленного кейса R07 или "result:<digest>" из ScenarioResultCache.

    payload/граф берёт сервер, не клиент. "result:..." ищется ТОЛЬКО в кэше пользовательских результатов:
    отсутствующий или истёкший результат никогда не заменяется подготовленным кейсом. load.status(id)
    сообщает "ok" | "expired" | "unknown" для честного ответа «пересчитайте».
    """
    from agent.civic_assistant.scenario import make_entry
    if manifest is None:
        module = sys.modules.get(getattr(load_graph, "__module__", "") or "")
        manifest = getattr(module, "manifest", None)
    graph_info = _manifest_graph_info(manifest)
    if result_cache is not None and getattr(result_cache, "graph_info", None) is None:
        result_cache.graph_info = graph_info
    cache: dict[str, dict] = {}
    lock = threading.Lock()

    def _case(scenario_id):
        for case in list_cases():
            if isinstance(case, dict) and case.get("case_id") == scenario_id:
                return case
        return None

    def load(scenario_id: str):
        if scenario_id.startswith("result:"):
            return result_cache.get(scenario_id) if result_cache is not None else None
        with lock:
            if scenario_id in cache:
                return cache[scenario_id]
        case = _case(scenario_id)
        if case is None:
            return None
        payload = case["payload"]
        result = compare(payload, load_graph(payload["graph_id"]))
        entry = make_entry(result, payload, graph_info(payload.get("graph_id")), kind="prepared_case")
        with lock:
            cache[scenario_id] = entry
        return entry

    def status(scenario_id: str) -> str:
        if scenario_id.startswith("result:"):
            return result_cache.status(scenario_id) if result_cache is not None else "unknown"
        with lock:
            if scenario_id in cache:
                return "ok"
        return "ok" if _case(scenario_id) is not None else "unknown"

    load.graph_info = graph_info
    load.status = status
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
        if isinstance(body, (bytes, bytearray)):
            # Соглашение R02: сервис может получить сырое тело; разбираем строго (без NaN/Infinity).
            try:
                body = json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
            except (ValueError, UnicodeDecodeError):
                return _err(400, "invalid_json", "тело запроса — корректный JSON")
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
        revision = body.get("revision")
        if revision is not None and (not isinstance(revision, int) or isinstance(revision, bool) or revision < 1
                                     or object_id is None):
            return _err(422, "invalid_revision", "revision — целое ≥ 1 и только вместе с object_id", ["revision"])
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
            if not loaded or not isinstance(loaded, (tuple, list)) or len(loaded) != 2:
                return _ok(unavailable_answer(lang, "object_not_public_or_missing"))
            item, history = loaded
            if not isinstance(item, dict) or item.get("id") != object_id:
                # Загрузчик вернул другой объект (ошибка интеграции): ответ про чужую карточку не выдаём.
                return _ok(unavailable_answer(lang, "object_mismatch"))
            # Раунд 13: ответ о конкретной редакции — только если она всё ещё текущая.
            if revision is not None and isinstance(item, dict) and item.get("revision") != revision:
                return _ok(stale_revision_answer(lang, object_id, item.get("revision"), item.get("updated_at")))
        missing_scenario = None
        if scenario_id is not None:
            try:
                scenario = self.load_scenario_result(scenario_id) if self.load_scenario_result else None
            except Exception:  # noqa: BLE001
                scenario = None
            if scenario is None:
                missing_scenario = self._missing_scenario_code(scenario_id)
                if item is None:
                    return _ok(unavailable_answer(lang, missing_scenario))
                warnings.append(missing_scenario)
                scenario_id = None
        try:
            ctx = build_verified_context(item, history, scenario, audience="public", scenario_id=scenario_id)
        except ContextError as exc:
            return _ok(unavailable_answer(lang, exc.code))
        answer = build_answer(question, ctx, self.provider, timeout_s=self.timeout_s)
        if missing_scenario:
            # Вопрос задан и про расчёт: честно говорим, что расчёта нет, и отвечаем только по карточке.
            prepend_notice(answer, missing_scenario)
        if warnings:
            answer["warnings"] = sorted(set(answer["warnings"]) | set(warnings))
        return _ok(answer)

    def _missing_scenario_code(self, scenario_id: str) -> str:
        if not scenario_id.startswith("result:"):
            return "scenario_not_found"
        status = getattr(self.load_scenario_result, "status", None)
        try:
            state = status(scenario_id) if callable(status) else "unknown"
        except Exception:  # noqa: BLE001
            state = "unknown"
        return {"expired": "scenario_result_expired", "rejected": "scenario_result_not_stored"}.get(
            state, "scenario_result_unknown")
