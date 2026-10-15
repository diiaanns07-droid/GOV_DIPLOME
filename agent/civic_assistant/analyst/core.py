"""ask(question, lang, principal) — «Спросить Birge» для сотрудника акимата (CONTRACT §7: POST assistant/ask).

Путь ответа (всё в одном процессе, без сети):
    1) вопрос проверяется (строка 1–500 знаков) и разбирается правилами ru/kk/вперемешку (intents.py);
    2) для каждого намерения вызываются функции модулей-соседей (sources.py) — каждый вызов в журнале;
    3) код собирает блоки ru/kk с числами из ответов соседей (blocks.py) и действия «Показать на карте» / «Открыть»;
    4) по желанию языковая модель меняет порядок блоков и вводную фразу без чисел (llm.py); иначе — офлайн.

Ответ (schema birge-analyst-answer-v1): см. research/round-15-results/R03/INTEGRATION.txt, раздел «Формат ответа».
Ошибки для шлюза R01: ValueError → 400, PermissionError → 403, исключение со status=429 → 429.
warm_up() — прогрев кэшей соседей при старте сервера (R10 B-107), без сотрудника и без языковой модели.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import threading
import time

from . import blocks as B
from . import intents as I
from . import llm as L
from . import sources as S
from .texts import DISTRICTS, both, category_name, district_name, service_name

SCHEMA = "birge-analyst-answer-v1"
RATE = (30, 60.0)  # вопросов на сотрудника за минуту: защита модулей и (если включена) платной модели
_AUTO = object()
LOGGER = logging.getLogger(__name__)
# Вопросы прогрева: карта R07 (Нура, 7 и 30 дней), «Картина дня» R08 (район и весь город), табло и кризис R17.
WARM_UP_QUESTIONS = (
    "Где в Нуре больше всего жалоб на снег за неделю и какие службы отстают?",
    "Какие службы отстают?",
    "Что с бураном?",
    "Сколько жалоб в Нуре за 30 дней?",
)


class TooManyQuestions(Exception):
    status = 429
    code = "too_many_requests"
    message = "Слишком много вопросов подряд. Повторите через минуту."

    def __str__(self):
        return self.message


class _Limiter:
    def __init__(self, limit: int, window_s: float):
        self.limit, self.window_s = limit, window_s
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self.window_s]
            ok = len(hits) < self.limit
            if ok:
                hits.append(now)
            self._hits[key] = hits
            if len(self._hits) > 5000:
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window_s}
            return ok


_LIMITER = _Limiter(*RATE)
_CONFIG: dict = {}
_CONFIG_LOCK = threading.Lock()


def configure(**overrides) -> None:
    """R01 или тесты подключают источники явно (иначе — сами, по именам соседей):

        heat=HeatService | None, akim_summary=fn(district) | None, agencies_board=fn(**kw), agencies_incidents=fn(**kw),
        works_conflicts=fn(**kw), together_initiatives=fn(**kw), meetings_list=fn(**kw), forecast=fn(**kw),
        provider=объект с complete(messages, timeout_s) | None (None — всегда офлайн), llm_timeout_s=8.0,
        clock=() -> datetime, rate=(лимит, окно_с).
    Повторный вызов заменяет только переданные ключи; reset() — вернуть всё по умолчанию.
    """
    global _LIMITER
    with _CONFIG_LOCK:
        _CONFIG.update(overrides)
        if "rate" in overrides:
            _LIMITER = _Limiter(*overrides["rate"])


def reset() -> None:
    global _LIMITER
    with _CONFIG_LOCK:
        _CONFIG.clear()
        _LIMITER = _Limiter(*RATE)


class _Sources:
    """Источники одного ответа: подменённые через configure или найденные у соседей."""

    def __init__(self, cfg: dict):
        self.heat = cfg["heat"] if "heat" in cfg else S.heat_service()
        self.akim_summary = cfg["akim_summary"] if "akim_summary" in cfg else S.akim_summary_fn()
        # Подменённый источник вызывается так же, как настоящий сосед (sources.adapt).
        def pick(key, default):
            return S.adapt(cfg[key], key) if callable(cfg.get(key)) else default
        self.agencies_board = pick("agencies_board", S.agencies_board)
        self.agencies_incidents = pick("agencies_incidents", S.agencies_incidents)
        self.works_conflicts = pick("works_conflicts", S.works_conflicts)
        self.together_initiatives = pick("together_initiatives", S.together_initiatives)
        self.meetings_list = pick("meetings_list", S.meetings_list)
        self.forecast = pick("forecast", S.forecast)


class _Ctx:
    def __init__(self, parsed, src: _Sources, now: datetime):
        self.parsed, self.src, self.now = parsed, src, now
        self.log = S.CallLog()
        self._summaries: dict = {}

    def call(self, role, module, fn_name, fn, args):
        return self.log.run(role, module, fn_name, fn, args)

    def summary(self, district):
        """«Картина дня» R08 — один вызов на район за ответ (её используют несколько блоков)."""
        if district not in self._summaries:
            self._summaries[district] = self.call("R08", "ui.civic_akim", "summary", S.akim_summary,
                                                  {"fn": self.src.akim_summary, "district": district})
        return self._summaries[district]


# ---------------------------------------------------------------- пометки безопасности и подсказки

NOTICES = {
    "injection": both("Инструкции внутри вопроса не выполняю — отвечаю только по данным Birge.",
                      "Сұрақ ішіндегі нұсқауларды орындамаймын — тек Birge деректері бойынша жауап беремін."),
    "fabricate": both("Числа не придумываю: всё, что ниже, посчитано по данным Birge.",
                      "Сандарды ойдан шығармаймын: төмендегінің бәрі Birge деректері бойынша есептелді."),
    "write": both("Я только читаю данные и ничего не меняю. Статусы и решения — в разделах «Обращения» и «Картина дня».",
                  "Мен деректерді тек оқимын, ештеңені өзгертпеймін. Мәртебелер мен шешімдер — «Өтініштер» мен "
                  "«Күн қорытындысы» бөлімдерінде."),
    "personal": both("Персональные данные жителей (имена, телефоны, ИИН, адреса) не показываю — только числа.",
                     "Тұрғындардың жеке деректерін (аты-жөні, телефон, ЖСН, мекенжай) көрсетпеймін — тек сандар."),
}
NO_DATA_NOTICE = both("Без чисел из данных ответить на это не могу.", "Деректердегі сандарсыз бұған жауап бере алмаймын.")

SUGGESTIONS = (
    both("Где в Нуре больше всего жалоб на снег за неделю?", "Нұрада бір аптада қар туралы шағым қай жерде көп?"),
    both("Какие службы отстают?", "Қай қызметтер артта қалып жатыр?"),
    both("Что с бураном?", "Боран бойынша не жағдай?"),
    both("Какие темы растут за неделю?", "Аптада қай тақырыптар өсті?"),
    both("Сравни районы по жалобам", "Аудандарды шағым бойынша салыстыр"),
    both("Сколько обращений просрочено?", "Қанша өтініштің мерзімі өтті?"),
)


def _clarify_block() -> dict:
    lines = {"ru": ["Я считаю по данным Birge: горячие места, рост жалоб, районы, просрочки, службы, кризис, "
                    "работы, инициативы жителей, поручения после встреч.", "Попробуйте спросить так:"],
             "kk": ["Мен Birge деректері бойынша есептеймін: шағымы көп орындар, шағымдардың өсуі, аудандар, мерзімі "
                    "өткен өтініштер, қызметтер, төтенше жағдай, жұмыстар, тұрғындар бастамалары, кездесулерден кейінгі "
                    "тапсырмалар.", "Былай сұрап көріңіз:"]}
    return {"id": "clarify", "kind": "clarify", "status": "empty", "title": both("Что я умею", "Мен не істей аламын"),
            "numbers": [], "lines": lines, "items": [{"label": s, "value": None, "ask": s} for s in SUGGESTIONS[:4]],
            "actions": [], "source": {"role": "R03", "name": both("Спросить Birge", "Birge-ден сұрау"), "demo": False},
            "facts": []}


def _understood(parsed, district_from_context=False) -> dict:
    out = {"days": parsed.days, "days_given": parsed.days_given}
    if parsed.district:
        out["district"] = {"id": parsed.district, "ru": district_name(parsed.district, "ru"),
                           "kk": district_name(parsed.district, "kk")}
        if district_from_context:
            out["district"]["from"] = "context"
    if len(parsed.districts) > 1:
        out["districts"] = [{"id": d, "ru": district_name(d, "ru"), "kk": district_name(d, "kk")}
                            for d in parsed.districts]
    if parsed.category:
        out["category"] = {"id": parsed.category, "ru": category_name(parsed.category, "ru"),
                           "kk": category_name(parsed.category, "kk")}
    if parsed.service:
        out["service"] = {"id": parsed.service, "ru": service_name(parsed.service, "ru"),
                          "kk": service_name(parsed.service, "kk")}
    return out


def _primary_actions(blocks: list[dict]) -> list[dict]:
    """Главная кнопка — первая «Показать на карте» из блоков с данными; затем одно «Открыть …»."""
    focus = next((a for b in blocks if b["status"] == "ok" for a in b["actions"] if a["kind"] == "map.focus"), None)
    opened = next((a for b in blocks if b["status"] in ("ok", "empty") for a in b["actions"] if a["kind"] == "open"),
                  None)
    return [a for a in (focus, opened) if a]


def _lead(blocks: list[dict]) -> dict:
    first = next((b for b in blocks if b["status"] == "ok"), None) or (blocks[0] if blocks else None)
    if not first:
        return both("", "")
    return {lang: (first["lines"][lang][0] if first["lines"][lang] else "") for lang in ("ru", "kk")}


def _check_principal(principal) -> None:
    """Защита в глубину: шлюз уже проверил сессию и CSRF (staff=True), модуль проверяет ещё раз."""
    if principal is None:
        raise PermissionError("«Спросить Birge» — только для сотрудника акимата. Войдите как сотрудник.")
    role = principal.get("role") if isinstance(principal, dict) else getattr(principal, "role", None)
    if role in (None, "", "resident", "anonymous"):
        raise PermissionError("«Спросить Birge» — только для сотрудника акимата.")


def _who(principal) -> str:
    if isinstance(principal, dict):
        return str(principal.get("username") or principal.get("role") or "staff")
    return str(getattr(principal, "username", None) or "staff")


def ask(question=None, lang=None, principal=None, context=None, body=None, district=None, *, now=None,
        provider=_AUTO) -> dict:
    """Главная функция роли R03 для маршрута POST /api/civic/v2/assistant/ask.

    lang — язык интерфейса (ru, kk; mixed или пусто — по вопросу). district — район, открытый у сотрудника: он
    подставляется, только если в вопросе своего района нет и это не сравнение районов (виден в «Как понят вопрос»).
    """
    if isinstance(body, dict):
        question = question if question is not None else body.get("question")
        lang = lang if lang is not None else body.get("lang")
        district = district if district is not None else body.get("district")
    _check_principal(principal)
    text = I.normalize_question(question)
    if lang == "mixed":
        lang = None
    if lang not in (None, "", "ru", "kk"):
        raise ValueError("lang: ru, kk или mixed.")
    if district in ("",):
        district = None
    if district is not None and district not in DISTRICTS:
        raise ValueError("district: неизвестный район.")
    with _CONFIG_LOCK:
        cfg = dict(_CONFIG)
    if not _LIMITER.allow(_who(principal)):
        raise TooManyQuestions()
    llm = cfg["provider"] if "provider" in cfg else (L.provider_from_env() if provider is _AUTO else provider)
    if provider is not _AUTO:
        llm = provider
    return _answer(text, lang, district, cfg, now, llm)


def warm_up(questions=WARM_UP_QUESTIONS) -> dict:
    """Прогрев при старте сервера (R10 B-107): первый вызов карты R07 и «Картины дня» R08 грузит данные 3–4 с.

    Аналитик сам задаёт себе вопросы сцен — без сотрудника, без лимита и без языковой модели (наружу ничего не
    уходит); ответы выбрасываются, остаются тёплые кэши соседей — первый вопрос акима отвечается сразу. Сбой соседа
    сервер не роняет: его честно покажет первый настоящий вопрос. R01 зовёт в фоне после wire() и засева мира.
    """
    started = time.perf_counter()
    with _CONFIG_LOCK:
        cfg = dict(_CONFIG)
    answered, failed = 0, 0
    for question in questions:
        try:
            _answer(I.normalize_question(question), "ru", None, cfg, None, None)
            answered += 1
        except Exception:  # noqa: BLE001 — прогрев не должен ронять сервер; подробности — в журнале
            failed += 1
            LOGGER.warning("analyst warm-up: вопрос не прогрет", exc_info=True)
    ms = round((time.perf_counter() - started) * 1000, 1)
    LOGGER.info("analyst warm-up: %d вопросов за %.0f мс (сбоев %d)", answered, ms, failed)
    return {"questions": answered, "failed": failed, "ms": ms}


def _answer(text, lang, district, cfg, now, llm) -> dict:
    """Ответ на уже проверенный вопрос: разбор, вызовы соседей, блоки, (по желанию) модель."""
    started = time.perf_counter()
    clock = cfg.get("clock")
    moment = now or (clock() if callable(clock) else datetime.now(timezone.utc))
    parsed = I.parse(text)
    district_from_context = bool(district and not parsed.districts and "district_compare" not in parsed.intents)
    if district_from_context:
        parsed.district, parsed.districts = district, [district]
    answer_lang = I.answer_language(parsed.question_lang, lang or None, text)
    ctx = _Ctx(parsed, _Sources(cfg), B.now_astana(moment))

    built = []
    for intent in parsed.intents:
        built.append(B.BUILDERS[intent](ctx).to_dict())
    if not built:
        built.append(_clarify_block())
    notices = [NOTICES[f] for f in parsed.flags if f in NOTICES]
    if parsed.flags and not parsed.intents:
        notices.append(NO_DATA_NOTICE)

    # Языковая модель — только если настроена, в вопросе нет ни одного флага безопасности (инструкция, «придумай»,
    # «удали», личные данные — R15 S44: иначе её вводная фраза без чисел показывалась бы как есть) и есть что упорядочить.
    mode, offline_reason, model, lead = "offline", None, None, _lead(built)
    if llm is None:
        offline_reason = "no_key"
    elif parsed.flags:
        offline_reason = "question_has_instructions"
    elif not parsed.intents:
        offline_reason = "nothing_to_refine"
    else:
        try:
            choice = L.refine(llm, text, answer_lang, built, timeout_s=float(cfg.get("llm_timeout_s", L.TIMEOUT_S)))
            order = choice["order"] + [b["id"] for b in built if b["id"] not in choice["order"]]
            built.sort(key=lambda b: order.index(b["id"]))
            if choice["lead"]:
                lead = dict(lead, **{answer_lang: choice["lead"]})
            mode, model = "llm", getattr(llm, "model", None)
            if choice["numbers_dropped"]:
                notices.append(both("Числа из текста модели вычеркнуты: числа даёт только код.",
                                    "Модель мәтініндегі сандар өшірілді: сандарды тек код береді."))
        except L.LLMRejected as exc:
            offline_reason = exc.code

    first = next((b for b in built if b["status"] == "ok"), built[0])
    facts = [f for b in built for f in b["facts"]]
    demo = any(b["source"]["demo"] for b in built)
    answer = {
        "schema": SCHEMA,
        "question": text,
        "question_lang": parsed.question_lang,
        "lang": answer_lang,
        "intents": [b["kind"] for b in built],
        "understood": _understood(parsed, district_from_context),
        "headline": first["title"],
        "lead": lead,
        "numbers": first["numbers"][:3],
        "blocks": built,
        "actions": _primary_actions(built),
        "notices": notices,
        "flags": list(parsed.flags),
        "facts": facts,
        "calls": ctx.log.rows,
        "mode": mode,
        "offline": mode == "offline",
        "offline_reason": offline_reason,
        "model": model,
        "demo": demo,
        "generated_at": ctx.now.isoformat(timespec="seconds"),
    }
    answer["ms"] = round((time.perf_counter() - started) * 1000, 1)
    return answer
