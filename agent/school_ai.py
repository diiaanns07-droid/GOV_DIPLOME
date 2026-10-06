"""AI-шов школьного кейса (CONTRACT r10, «Граница AI»).

Браузер присылает вопрос и каталог фактов текущего кейса (id, метрика, значение), привязанный к request_id и
case_digest. Модель может только выбрать намерение, ID фактов и разрешённые действия показа. Числа и публичный текст
собирает браузер из своих фактов; свободный текст модели не возвращается. Любая ошибка схемы, неизвестный ID или чужой
digest → отказ и помеченный шаблонный ответ (source = fallback).

Ограничение: в локальном однопользовательском приложении сервер не удостоверяет числа, пришедшие из браузера. Это не
архитектура доверенного многопользовательского сервиса. Ключи читаются только на сервере и не попадают в ответы и логи.
"""

from __future__ import annotations

import json
import logging
import re

LOGGER = logging.getLogger(__name__)
REQUEST_SCHEMA = "school-ai-request-v1"
RESPONSE_SCHEMA = "school-ai-response-v1"
INTENTS = ("compare_variants", "explain_metric", "point_detail", "data_limits", "method", "unsupported")
TOOLS = {"show_view": {"view": ("current", "A", "B")}, "select_origin": {"origin_id": None}, "open_limits": {}}
MAX_FACTS = 400
MAX_QUESTION = 600
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/\-]{0,160}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SYSTEM = (
    "Ты помогаешь понять сравнение доступности школ на маленьком участке города. Числа уже посчитаны кодом; "
    "ты их не пересчитываешь и не придумываешь. Верни ТОЛЬКО JSON-объект с ключами: "
    "intent (одно из: " + ", ".join(INTENTS) + "), fact_ids (до 6 ID из присланного каталога, которые отвечают на вопрос), "
    "tool_calls (список до 2 объектов {name, args}; name из: show_view{view: current|A|B}, select_origin{origin_id}, open_limits{}), "
    "needs_clarification (строка-вопрос пользователю или null). Не пиши других ключей и никакого текста вне JSON. "
    "Если вопрос о строительстве, бюджете, населении, пробках или вместимости — intent=unsupported или data_limits: "
    "этих данных в кейсе нет."
)


class SchoolAIError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def validate_request(body: dict) -> dict:
    if not isinstance(body, dict) or body.get("schema_version") != REQUEST_SCHEMA:
        raise SchoolAIError("bad_request", "ожидается " + REQUEST_SCHEMA)
    rid, digest, question = body.get("request_id"), body.get("case_digest"), body.get("question")
    if not isinstance(rid, str) or not ID_RE.match(rid):
        raise SchoolAIError("bad_request", "request_id")
    if not isinstance(digest, str) or not DIGEST_RE.match(digest):
        raise SchoolAIError("bad_request", "case_digest")
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION:
        raise SchoolAIError("bad_request", f"вопрос — непустая строка до {MAX_QUESTION} символов")
    facts = body.get("facts")
    if not isinstance(facts, list) or not facts or len(facts) > MAX_FACTS:
        raise SchoolAIError("bad_request", f"facts: 1…{MAX_FACTS}")
    clean, ids = [], set()
    for f in facts:
        if not isinstance(f, dict) or not isinstance(f.get("id"), str) or not ID_RE.match(f["id"]) or f["id"] in ids:
            raise SchoolAIError("bad_request", "факт без допустимого уникального id")
        value = f.get("value")
        if not (value is None or isinstance(value, (int, float, str, list)) and not isinstance(value, bool)):
            raise SchoolAIError("bad_request", "значение факта " + f["id"])
        ids.add(f["id"])
        clean.append({k: f.get(k) for k in ("id", "metric", "value", "unit", "plan_id", "origin_id")})
    origins = body.get("origin_ids") or []
    if not isinstance(origins, list) or not all(isinstance(o, str) and ID_RE.match(o) for o in origins):
        raise SchoolAIError("bad_request", "origin_ids")
    views = body.get("views") or ["current"]
    if not isinstance(views, list) or not all(v in ("current", "A", "B") for v in views):
        raise SchoolAIError("bad_request", "views")
    return {"request_id": rid, "case_digest": digest, "question": question.strip(), "facts": clean,
            "origin_ids": origins, "views": views}


def validate_model_output(raw: str, req: dict) -> dict:
    """Strict check of the model JSON. Unknown keys, IDs, intents or tools are rejected (no partial acceptance)."""
    try:
        out = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise SchoolAIError("model_not_json", "ответ модели не JSON") from exc
    if not isinstance(out, dict) or set(out) - {"intent", "fact_ids", "tool_calls", "needs_clarification"}:
        raise SchoolAIError("model_schema", "лишние или отсутствующие ключи")
    intent = out.get("intent")
    if intent not in INTENTS:
        raise SchoolAIError("model_schema", "intent")
    known = {f["id"] for f in req["facts"]}
    fact_ids = out.get("fact_ids") or []
    if not isinstance(fact_ids, list) or len(fact_ids) > 6 or not all(isinstance(i, str) and i in known for i in fact_ids):
        raise SchoolAIError("model_unknown_fact", "fact_ids вне каталога текущего кейса")
    calls = out.get("tool_calls") or []
    if not isinstance(calls, list) or len(calls) > 2:
        raise SchoolAIError("model_schema", "tool_calls")
    clean_calls = []
    for c in calls:
        if not isinstance(c, dict) or c.get("name") not in TOOLS or set(c) - {"name", "args"}:
            raise SchoolAIError("model_tool", "недопустимое действие")
        args = c.get("args") or {}
        if not isinstance(args, dict) or set(args) != set(TOOLS[c["name"]]):
            raise SchoolAIError("model_tool", "аргументы " + str(c.get("name")))
        if c["name"] == "show_view" and args["view"] not in req["views"]:
            raise SchoolAIError("model_tool", "вид недоступен в текущем кейсе")
        if c["name"] == "select_origin" and args["origin_id"] not in req["origin_ids"]:
            raise SchoolAIError("model_tool", "неизвестная точка")
        clean_calls.append({"name": c["name"], "args": args})
    clar = out.get("needs_clarification")
    if clar is not None and (not isinstance(clar, str) or len(clar) > 300 or re.search(r"\d", clar)):
        raise SchoolAIError("model_schema", "уточнение — короткая строка без чисел или null")
    return {"intent": intent, "fact_ids": fact_ids, "tool_calls": clean_calls, "needs_clarification": clar}


_KEYWORDS = (
    ("data_limits", ("строит", "бюджет", "стоим", "денег", "населен", "жител", "дет", "мест в школ", "вместим", "пробк", "трафик")),
    ("method", ("прям", "маршрут", "улиц", "пешком", "пеш", "граф")),
    ("point_detail", ("точк", "дальше всего", "худш", "самая дальн")),
    ("explain_metric", ("средн", "порог", "в пределах", "показател", "что значит")),
    ("compare_variants", ("лучше", "сравн", "a или b", "а или б", "выбрать", "вариант")),
)


def fallback_choice(req: dict) -> dict:
    """Шаблонный выбор без модели: ключевые слова → намерение; факты — по фиксированным правилам."""
    q = req["question"].lower()
    intent = next((name for name, words in _KEYWORDS if any(w in q for w in words)), "compare_variants")
    by_id = {f["id"]: f for f in req["facts"]}
    plans = [v for v in ("A", "B") if v in req["views"]]
    pick = []
    if intent in ("compare_variants", "explain_metric"):
        # metric-major order: every plan gets the same metrics before the 6-fact limit cuts anything
        for metric in ("mean_distance_mm", "within_threshold_count", "max_distance_mm", "unknown_count"):
            for p in ["current", *plans]:
                if f"{p}/{metric}" in by_id:
                    pick.append(f"{p}/{metric}")
    elif intent == "point_detail":
        pick = [i for i in (f"{p}/max_distance_mm" for p in ["current", *plans]) if i in by_id]
    calls = [{"name": "show_view", "args": {"view": plans[0]}}] if intent == "compare_variants" and plans else []
    if intent == "data_limits":
        calls = [{"name": "open_limits", "args": {}}]
    return {"intent": intent, "fact_ids": pick[:6], "tool_calls": calls, "needs_clarification": None}


def _settings():
    # Тот же источник настроек, что у советника учебного режима; значения не логируются и не возвращаются.
    from agent.advisor import read_settings
    return read_settings()


def answer(body: dict, client_factory=None) -> dict:
    req = validate_request(body)
    base = {"schema_version": RESPONSE_SCHEMA, "request_id": req["request_id"], "case_digest": req["case_digest"]}

    def fallback(code, reason):
        return {**base, **fallback_choice(req), "source": "fallback", "reason_code": code, "reason": reason, "model": None}

    try:
        settings = _settings()
    except Exception:  # noqa: BLE001 — dotenv/настройки недоступны
        return fallback("settings_unavailable", "Настройки провайдера недоступны на сервере.")
    if not settings.get("OPENAI_API_KEY"):
        return fallback("missing_key", "Провайдер AI не настроен на сервере (нет ключа). Показан шаблонный ответ.")
    if not settings.get("OPENAI_MODEL"):
        return fallback("missing_model", "Не указана модель провайдера на сервере. Показан шаблонный ответ.")
    client = None
    try:
        if client_factory is None:
            from agent.advisor import _create_client
            client = _create_client(settings)
        else:
            client = client_factory(settings)
        catalog = [{k: f[k] for k in ("id", "metric", "plan_id", "origin_id")} for f in req["facts"]]
        user = json.dumps({"question": req["question"], "facts": catalog, "views": req["views"], "origin_ids": req["origin_ids"]},
                          ensure_ascii=False)
        resp = client.chat.completions.create(model=settings["OPENAI_MODEL"], temperature=0,
                                              messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
        raw = resp.choices[0].message.content or ""
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        out = validate_model_output(raw, req)
        return {**base, **out, "source": "model", "reason_code": "", "reason": "", "model": settings["OPENAI_MODEL"]}
    except SchoolAIError as exc:
        LOGGER.warning("Ответ модели отклонён (%s)", exc.code)
        return fallback(exc.code, "Ответ модели не прошёл проверку (" + exc.code + "). Показан шаблонный ответ.")
    except Exception as exc:  # noqa: BLE001 — сетевые/API ошибки: текст исключения может содержать настройки
        LOGGER.warning("Провайдер AI недоступен (%s)", type(exc).__name__)
        return fallback("api_error", "Провайдер AI недоступен или ответил ошибкой. Показан шаблонный ответ.")
    finally:
        if client is not None and hasattr(client, "close"):
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
