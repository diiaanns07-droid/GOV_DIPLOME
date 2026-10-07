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
import threading

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
PROVIDER_WORKERS = 4
_POOL = cf.ThreadPoolExecutor(max_workers=PROVIDER_WORKERS, thread_name_prefix="civic-assistant-provider")
# Свободные слоты пула. Зависший провайдер держит поток и после тайм-аута ответа; если слотов нет,
# вопрос сразу получает шаблон с честным provider_busy, а не ждёт в очереди и не пишет ложный provider_timeout.
_SLOTS = threading.BoundedSemaphore(PROVIDER_WORKERS)

_KK_LETTERS = re.compile(r"[әғқңөұүһіӘҒҚҢӨҰҮҺІ]")
_KK_WORDS = re.compile(r"\b(?:кім|неге|неліктен|қашан|жатыр|қанша|мерзім|қайда|қайдан|мен|бойынша|туралы|"
                       r"жоспар\w*|салыстыр\w*|болып|жасалып|бар ма|жоқ па|жол|мына|нысан\w*|жабыл\w*|"
                       r"жарияла\w*|ма|ме|ба|бе)\b", re.IGNORECASE)

# Порядок важен: более узкие намерения раньше общих. Ключи — основы слов RU/KK/EN.
_RULES = (
    # Просьбы что-то изменить/опубликовать: у помощника нет инструментов записи — отказ, а не «сделано».
    ("unsupported", ("парол", "пароль", "логин", "токен", "token", "password", "секрет", "secret", "api key",
                     "api-key", "ключ api", "cookie", "sql", "select ", "drop ", "shell", "bash", "sudo",
                     "опубликуй", "публикуй", "удали", "измени ", "измените", "измени статус", "поменяй", "смени",
                     "исправь", "отредактируй", "сотри", "добавь", "запиши", "сохрани", "отправь", "одобри",
                     "утверди", "смени роль", "права админ", "админк", "internal_notes", "служебн",
                     "жарияла ", "жариялаңыз", "өшір", "құпия сөз", "пробк", "трафик", "кептеліс", "co2", "выброс",
                     "экологи", "машин", "автомобил", "publish", "delete")),
    ("scenario_compare", ("сравн", "вариант a", "вариант b", "план a", "план b", "a или b", "а или б", "a и b",
                          "а и б", "a/b", "салыстыр", "лучше", "хуже", "выгодн", "какой вариант", "какой план",
                          "compare")),
    ("delay_reason", ("почему перен", "почему сдвин", "почему продл", "почему отлож", "причина перенос",
                      "причин", "почему срок", "почему задерж", "перенесли", "отложили", "продлили",
                      "перенос", "перенес", "неге ауыс", "неліктен ауыс", "ауыстыр", "кейінге қалдыр", "шегер", "неге кешік",
                      "себеб", "неге жылжы", "задерж", "из-за чего", "почему так долго", "почему долго",
                      "почему до сих пор", "неліктен", "неге ұзарт", "why")),
    # «Какие сведения отсутствуют?» — список пустых полей карточки, а не обзор.
    ("missing_data", ("сведения отсутств", "сведений нет", "каких сведений не", "чего не хватает", "не хватает",
                      "что неизвестно", "данные неизвест", "неизвестные данные", "каких данных нет",
                      "чего нет в карточке", "что не указано", "пустые поля", "поля пуст",
                      "мәліметтер жоқ", "мәлімет жоқ", "деректер жоқ", "не белгісіз", "жетіспей", "missing")),
    # «Насколько свежие данные?» — даты данных с основой, а не сроки работ. Раньше schedule: «когда обновили».
    ("freshness", ("свеж", "актуальны ли", "актуальность", "насколько актуальн", "данные актуальн",
                   "сведения актуальн", "когда обновил", "когда обновлял", "когда обновлен", "обновлялась",
                   "обновлялись", "последнее обновление", "устарел", "дата данных", "на какую дату", "снимок",
                   "по числу участков", "по числу ребер", "по числу рёбер", "доля неизвестн", "долю неизвестн",
                   "неизвестным доступом", "неизвестный доступ", "доля по длине", "жаңартыл", "өзекті", "ескір",
                   "белгісіз үлес", "fresh", "up to date")),
    ("schedule", ("когда", "срок", "до какого", "дата", "сколько продл", "на сколько сдвин", "на сколько продл",
                  "неше күн", "ұзарт", "созыл", "қашан", "мерзім", "күні", "when", "deadline")),
    ("status", ("законч", "заверш", "уже сделал", "готов ли", "готово", "сдали", "уже идут", "идут ли",
                "начали ли", "уже начали", "ведутся", "аяқталды ма", "аяқталды", "бітті", "басталды ма",
                "жүріп жатыр ма", "finished", "done")),
    ("responsible", ("кто отвеча", "кто делает", "кто ведёт", "кто ведет", "подрядчик", "исполнитель",
                     "ответствен", "заказчик", "куда обращ", "куда жалов", "куда пожалов", "жалоб", "куда писать",
                     "куда звонить", "контакт", "телефон", "обращ", "позвонить", "связаться", "кім", "жауапты", "шағым", "хабарлас",
                     "who")),
    ("budget", ("сколько сто", "сколько это сто", "во сколько обош", "стоимост", "бюджет", "сумм", "деньг", "тенге", "потрат", "затрат", "освоен", "смет", "₸", "қанша тұр", "ақша", "сома",
                "құн", "cost", "budget")),
    ("sources", ("источник", "откуда данн", "откуда эти", "откуда это", "откуда информац", "откуда сведен",
                 "откуда вы знаете", "на основании", "основан", "где взяли", "ссылк", "реальн", "это настоящ",
                 "настоящий ремонт", "настоящие данн", "достоверн", "синтетич", "выдуман", "демонстрац",
                 "это демо", "демо-", "правда ли",
                 "дереккөз", "қайдан", "нақты дерек", "шын ба", "рас па", "source")),
    ("history", ("истори", "что измен", "что поменял", "что менял", "изменени", "ревизи", "тарих", "өзгер", "history")),
    ("access_impact", ("доступн", "недоступ", "проезд", "проход", "пройти", "проехать", "объезд", "перекрыт", "обход",
                       "как добраться", "маршрут", "пешеход", "обойти", "пройду", "өту", "жабыл", "жол жабы",
                       "access", "detour")),
    ("location", ("где", "адрес", "место", "в каком месте", "располож", "қайда", "қай жерде", "орны", "where")),
    ("overview", ("что происходит", "что здесь", "что тут", "что это", "что за", "что делают", "делают",
                  "что строят", "расскажи про", "расскажи о", "расскажи об", "не болып", "не істеп", "не салы", "what")),
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


def _stem_pattern(words) -> re.Pattern:
    """Ключ совпадает только с НАЧАЛА слова: «сумм» — в «сумма», но не в «рассуммировать»; «когда» — не в «никогда»."""
    parts = []
    for w in words:
        w = w.casefold().replace("ё", "е")
        parts.append((r"(?<!\w)" if re.match(r"\w", w) else "") + re.escape(w))
    return re.compile("|".join(parts))


_RULE_PATTERNS = tuple((intent, _stem_pattern(words)) for intent, words in _RULES)


def classify(question: str, available: dict) -> tuple[str, list[str]]:
    """Шаблонный выбор намерения. Возвращает (intent, warnings).

    Нераспознанный вопрос получает «clarify» (что помощник умеет), а не уверенный обзор наугад.
    """
    q = " " + question.casefold().replace("ё", "е") + " "
    for intent, pattern in _RULE_PATTERNS:
        if pattern.search(q):
            return intent, []
    return "clarify", ["intent_unrecognized"]


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
    if not _SLOTS.acquire(blocking=False):
        raise ProviderRejected("provider_busy")
    try:
        future = _POOL.submit(provider.choose, request, timeout_s=timeout_s)
    except BaseException:
        _SLOTS.release()
        raise
    future.add_done_callback(lambda _f: _SLOTS.release())
    try:
        return future.result(timeout=timeout_s)
    except cf.TimeoutError as exc:
        future.cancel()
        raise ProviderRejected("provider_timeout") from exc
    except BaseException as exc:
        # Исключение самого провайдера (в т.ч. CancelledError/SystemExit из его потока) — отказ
        # провайдера, а не падение ответа. Прерывание, пришедшее во время ожидания, пробрасываем.
        if future.done() and not future.cancelled() and future.exception() is exc:
            raise ProviderRejected("provider_error") from exc
        raise


def _public_sources(statements, facts) -> list[dict]:
    """Описание источников, на которые ссылаются фразы, — для подписи человеку (не только ID).

    Значения уже прошли проверку при сборке контекста: ссылка только http(s), текст без управляющих символов.
    """
    out = []
    cited = [sid for s in statements for sid in s.get("source_ids", [])]
    cited += [fid[len("source."):] for s in statements for fid in s.get("fact_ids", []) if fid.startswith("source.")]
    for sid in dict.fromkeys(cited):
        ref = (facts.get("source." + sid) or {}).get("value")
        if isinstance(ref, dict):
            out.append({k: ref.get(k) for k in ("id", "publisher", "published_on", "retrieved_at", "access_status",
                                                "license", "url")})
    return out


def _card_version(facts) -> dict:
    rev = (facts.get("object.revision") or {}).get("value") if facts else None
    upd = (facts.get("object.updated_at") or {}).get("value") if facts else None
    return {"object_revision": rev if isinstance(rev, int) else None,
            "object_updated_at": upd if isinstance(upd, str) else None}


def _result(source, intent, lang, statements, ctx, warnings, mode, model=None, facts=None):
    if facts is not None:
        statements, dropped = audit_statements(statements, facts)
        warnings = list(warnings) + dropped
    fact_ids = list(dict.fromkeys(fid for s in statements for fid in s["fact_ids"]))
    version = _card_version(facts)
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
        # Раунд 12: по какой редакции карточки собран ответ и какие источники он цитирует.
        "object_revision": version["object_revision"],
        "object_updated_at": version["object_updated_at"],
        "sources": _public_sources(statements, facts) if facts else [],
    }


# Тексты отказа по коду: расчёт пользователя и объект — разные причины, текст не должен их путать.
_UNAVAILABLE_TEXT = {"scenario_result_expired": "unavailable_result_expired",
                     "scenario_result_unknown": "unavailable_result_unknown",
                     "scenario_not_found": "unavailable_scenario"}


def unavailable_text(lang: str, code: str) -> str:
    return T[lang][_UNAVAILABLE_TEXT.get(code, "unavailable")]


def unavailable_answer(lang: str = "ru", code: str = "context_unavailable") -> dict:
    st = [{"text": unavailable_text(lang, code), "kind": "notice", "fact_ids": [], "source_ids": []}]
    return _result("unavailable", None, lang, st, None, [code], mode="unavailable")


def stale_revision_answer(lang: str, object_id: str, current_revision, updated_at=None) -> dict:
    """Клиент спросил о редакции, которой уже нет: фактов не выдаём, называем текущую редакцию."""
    rev = current_revision if isinstance(current_revision, int) and not isinstance(current_revision, bool) else None
    text = T[lang]["revision_changed"].format(r=rev if rev is not None else T[lang]["unknown_value"])
    st = [{"text": text, "kind": "notice", "fact_ids": [], "source_ids": []}]
    out = _result("unavailable", None, lang, st, {"object_id": object_id}, ["object_revision_changed"],
                  mode="unavailable")
    out["object_revision"] = rev
    out["object_updated_at"] = clean_text(updated_at, 40)
    return out


def prepend_notice(answer: dict, code: str) -> dict:
    """Добавить в начало ответа пометку об отсутствующем расчёте (текст без чисел и без фактов)."""
    note = {"text": unavailable_text(answer.get("language") or "ru", code), "kind": "notice", "fact_ids": [],
            "source_ids": []}
    answer["statements"] = [note] + list(answer.get("statements") or [])
    answer["text"] = " ".join(s["text"] for s in answer["statements"])
    return answer


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
