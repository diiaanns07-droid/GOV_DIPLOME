"""build_answer(question, verified_context, provider=None) — ответ помощника civic-v1.

Путь ответа всегда соответствует полю source:
- template: тип ответа выбран правилами по ключевым словам; текст собран кодом;
- llm: провайдер вернул строгий JSON {intent, fact_ids}, который прошёл проверку;
  текст и числа всё равно собирает код из каталога фактов;
- unavailable: доверенного контекста нет/он повреждён — ответа по объекту нет.
Ошибка провайдера (не JSON, лишние ключи, свободный текст, неизвестный ID, чужой
для типа ответа факт, тайм-аут) не принимается частично: ответ строится шаблоном,
source=template, в warnings указан код отказа.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import logging
import re

from agent.civic_assistant.audit import audit_statements
from agent.civic_assistant.facts import FACTS_VERSION, ContextError, check_context, clean_text
from agent.civic_assistant.render import INTENT_FACT_PREFIXES, INTENTS, T, render

LOGGER = logging.getLogger(__name__)
ANSWER_SCHEMA = "civic-assistant-answer-v1"
CHOICE_REQUEST_SCHEMA = "civic-assistant-choice-request-v1"
MAX_QUESTION = 500
MAX_PROVIDER_RAW = 4000
MAX_FACT_IDS = 8
PROVIDER_TIMEOUT_S = 8.0
_POOL = cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="civic-assistant-provider")

_KK_LETTERS = re.compile(r"[әғқңөұүһіӘҒҚҢӨҰҮҺІ]")
_KK_WORDS = re.compile(r"\b(?:кім|неге|неліктен|қашан|жатыр|қанша|мерзім|қайда|қайдан|мен|бойынша|туралы|"
                       r"жоспар\w*|салыстыр\w*|болып|жасалып|бар ма|жоқ па)\b", re.IGNORECASE)

# Порядок важен: более узкие намерения раньше общих. Ключи — основы слов RU/KK/EN.
_RULES = (
    ("unsupported", ("парол", "пароль", "логин", "токен", "token", "password", "секрет", "secret", "api key",
                     "api-key", "ключ api", "cookie", "sql", "select ", "drop ", "shell", "bash", "sudo",
                     "опубликуй", "публикуй", "удали", "измени статус", "смени роль", "права админ", "админк",
                     "құпия сөз", "пробк", "трафик", "кептеліс", "co2", "выброс", "экологи")),
    ("scenario_compare", ("сравн", "вариант a", "вариант b", "план a", "план b", "a или b", "а или б", "a и b",
                          "а и б", "a/b", "салыстыр", "лучше", "хуже", "выгодн", "какой вариант", "какой план",
                          "compare")),
    ("delay_reason", ("почему перен", "почему сдвин", "почему продл", "почему отлож", "причина перенос",
                      "причин", "почему срок", "почему задерж", "перенесли", "отложили", "продлили",
                      "перенос", "перенес", "неге ауыс", "неліктен ауыс", "ауыстыр", "кейінге қалдыр", "шегер", "неге кешік",
                      "себеб", "неге жылжы", "why")),
    ("schedule", ("когда", "срок", "до какого", "дата", "сколько продл", "қашан", "мерзім", "күні", "when",
                  "deadline")),
    ("status", ("законч", "заверш", "уже сделал", "готов ли", "готово", "сдали", "аяқталды ма", "аяқталды",
                "бітті", "finished", "done")),
    ("responsible", ("кто отвеча", "кто делает", "кто ведёт", "кто ведет", "подрядчик", "исполнитель",
                     "ответствен", "заказчик", "куда обращ", "контакт", "кім", "жауапты", "who")),
    ("budget", ("сколько сто", "стоимост", "бюджет", "сумм", "деньг", "тенге", "потрат", "затрат", "освоен", "смет", "₸", "қанша тұр", "ақша", "сома",
                "cost", "budget")),
    ("sources", ("источник", "откуда данн", "откуда эти", "откуда это", "откуда информац", "откуда сведен",
                 "откуда вы знаете", "на основании", "где взяли", "ссылк",
                 "дереккөз", "қайдан", "source")),
    ("history", ("истори", "что измен", "что поменял", "что менял", "изменени", "ревизи", "тарих", "өзгер", "history")),
    ("access_impact", ("доступн", "проезд", "проход", "пройти", "проехать", "объезд", "перекрыт", "обход",
                       "как добраться", "маршрут", "пешеход", "өту", "жабыл", "жол жабы", "access", "detour")),
    ("location", ("где", "адрес", "место", "располож", "қайда", "орны", "where")),
    ("overview", ("что происходит", "что здесь", "что это", "что за", "что делают", "что строят", "расскажи",
                  "не болып", "не салы", "what")),
)


class AssistantInputError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class ProviderRejected(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def detect_language(question: str) -> str:
    return "kk" if _KK_LETTERS.search(question) or _KK_WORDS.search(question) else "ru"


def normalize_question(question) -> str:
    if not isinstance(question, str):
        raise AssistantInputError("question_type", "вопрос — строка")
    if len(question) > MAX_QUESTION * 4:
        raise AssistantInputError("question_too_long", f"до {MAX_QUESTION} символов")
    text = clean_text(question, limit=10 ** 6)
    if not text:
        raise AssistantInputError("question_empty")
    if len(text) > MAX_QUESTION:
        raise AssistantInputError("question_too_long", f"до {MAX_QUESTION} символов")
    return text


def classify(question: str, available: dict) -> tuple[str, list[str]]:
    """Шаблонный выбор намерения. Возвращает (intent, warnings)."""
    q = " " + question.casefold().replace("ё", "е") + " "
    has_scenario = any(fid.startswith("scenario.") for fid in available)
    has_object = "object.title" in available
    for intent, words in _RULES:
        if any(w.replace("ё", "е") in q for w in words):
            return intent, []
    if has_object:
        return "overview", ["intent_guessed"]
    if has_scenario:
        return "scenario_compare", ["intent_guessed"]
    return "unsupported", ["intent_guessed"]


def provider_catalog(facts: dict) -> list[dict]:
    """Что видит модель: ID, подпись и признак known. Значений нет — числа и цитаты не уходят в промпт."""
    return [{"id": f["id"], "label": f["label_key"], "known": bool(f["known"])} for f in facts.values()]


def choice_request(question: str, lang: str, facts: dict) -> dict:
    return {
        "schema": CHOICE_REQUEST_SCHEMA,
        "question": question,
        "language": lang,
        "intents": list(INTENTS),
        "facts": provider_catalog(facts),
        "max_fact_ids": MAX_FACT_IDS,
        "output": {"intent": "one of intents", "fact_ids": "list of ids from facts, may be empty"},
    }


def validate_choice(raw, facts: dict) -> dict:
    """Строгая проверка ответа провайдера; частичного принятия нет."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        raise ProviderRejected("provider_type")
    if len(raw) > MAX_PROVIDER_RAW:
        raise ProviderRejected("provider_too_long")
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        out = json.loads(text)
    except ValueError as exc:
        raise ProviderRejected("provider_not_json") from exc
    if not isinstance(out, dict):
        raise ProviderRejected("provider_schema")
    extra = set(out) - {"intent", "fact_ids"}
    if extra:
        # «text», «answer», «comment» и т. п. — попытка вернуть свободный текст.
        raise ProviderRejected("provider_free_text" if extra & {"text", "answer", "comment", "message", "reply"}
                               else "provider_schema")
    intent = out.get("intent")
    if not isinstance(intent, str) or intent not in INTENTS:
        raise ProviderRejected("provider_intent")
    ids = out.get("fact_ids", [])
    if not isinstance(ids, list) or len(ids) > MAX_FACT_IDS or not all(isinstance(i, str) for i in ids):
        raise ProviderRejected("provider_schema")
    if any(i not in facts for i in ids):
        raise ProviderRejected("provider_unknown_fact")
    allowed = INTENT_FACT_PREFIXES[intent]
    if any(not i.startswith(allowed) for i in ids) if allowed else ids:
        raise ProviderRejected("provider_fact_not_for_intent")
    return {"intent": intent, "fact_ids": list(dict.fromkeys(ids))}


def _call_provider(provider, request: dict, timeout_s: float):
    future = _POOL.submit(provider.choose, request, timeout_s=timeout_s)
    try:
        return future.result(timeout=timeout_s)
    except cf.TimeoutError as exc:
        future.cancel()
        raise ProviderRejected("provider_timeout") from exc


def _result(source, intent, lang, statements, ctx, warnings, mode, model=None, facts=None):
    if facts is not None:
        statements, dropped = audit_statements(statements, facts)
        warnings = list(warnings) + dropped
    fact_ids = list(dict.fromkeys(fid for s in statements for fid in s["fact_ids"]))
    return {
        "schema": ANSWER_SCHEMA,
        "source": source,
        "mode": mode,
        "model": model,
        "intent": intent,
        "language": lang,
        "text": " ".join(s["text"] for s in statements),
        "statements": statements,
        "fact_ids": fact_ids,
        "warnings": sorted(set(warnings)),
        "object_id": ctx.get("object_id") if isinstance(ctx, dict) else None,
        "scenario_id": ctx.get("scenario_id") if isinstance(ctx, dict) else None,
        "context_digest": ctx.get("digest") if isinstance(ctx, dict) else None,
        "facts_version": FACTS_VERSION,
    }


def unavailable_answer(lang: str = "ru", code: str = "context_unavailable") -> dict:
    st = [{"text": T[lang]["unavailable"], "kind": "notice", "fact_ids": [], "source_ids": []}]
    return _result("unavailable", None, lang, st, None, [code], mode="unavailable")


def build_answer(question, verified_context, provider=None, *, timeout_s: float = PROVIDER_TIMEOUT_S) -> dict:
    """Главная функция роли R09. question проверяется; контекст обязан быть серверным."""
    q = normalize_question(question)
    lang = detect_language(q)
    try:
        facts = check_context(verified_context)
    except ContextError as exc:
        return unavailable_answer(lang, exc.code)
    warnings = list(verified_context.get("warnings", []))
    template_intent, cw = classify(q, facts)
    if provider is None:
        st = render(template_intent, facts, lang)
        return _result("template", template_intent, lang, st, verified_context, warnings + cw, mode="template",
                       facts=facts)
    name = getattr(provider, "name", "provider")
    try:
        raw = _call_provider(provider, choice_request(q, lang, facts), timeout_s)
        choice = validate_choice(raw, facts)
    except ProviderRejected as exc:
        LOGGER.warning("civic assistant: provider output rejected (%s)", exc.code)
        st = render(template_intent, facts, lang)
        return _result("template", template_intent, lang, st, verified_context,
                       warnings + cw + [exc.code], mode="template-fallback", facts=facts)
    except Exception as exc:  # noqa: BLE001 — сетевые/API ошибки; текст исключения может содержать настройки
        LOGGER.warning("civic assistant: provider error (%s)", type(exc).__name__)
        st = render(template_intent, facts, lang)
        return _result("template", template_intent, lang, st, verified_context,
                       warnings + cw + ["provider_error"], mode="template-fallback", facts=facts)
    # Модель не может заставить ответить на «покажи пароли»: правило безопасности шаблона сильнее.
    intent = "unsupported" if template_intent == "unsupported" else choice["intent"]
    extra = ["provider_overridden_unsupported"] if intent != choice["intent"] else []
    if extra:
        st = render(template_intent, facts, lang)
        return _result("template", template_intent, lang, st, verified_context,
                       warnings + cw + extra, mode="template-fallback", facts=facts)
    st = render(intent, facts, lang, choice["fact_ids"])
    return _result("llm", intent, lang, st, verified_context, warnings + extra, mode="llm:" + str(name),
                   model=getattr(provider, "model", None), facts=facts)
