"""Проверка каждой фразы ответа перед выдачей (defense in depth).

Основная защита архитектурная: текст собирает код, модель выбирает только ID.
Этот аудит дополнительно ловит ошибки шаблонов и будущих правок:
- в фразе не должно остаться ни одной цифры, которую нельзя вывести из фактов,
  на которые фраза ссылается (даты, суммы, сдвиг в днях, ревизии, метрики);
- цитата «…» дословно совпадает со строкой из указанного факта;
- без факта нет качественных утверждений: «официально одобрено», «утверждено»,
  «гарантировано», а «завершено/закончены» — только при status=completed.
Фраза, не прошедшая аудит, удаляется из ответа, в warnings пишется код.
"""

from __future__ import annotations

import re

from agent.civic_assistant.render import fmt_at, fmt_date, fmt_money, T

# Слова-утверждения, которым в civic-v1 нет соответствующего поля.
UNBACKED_QUALITATIVE = re.compile(
    r"одобрен|утвержд|гарантир|официальн|согласован|без задерж|в срок\b|точно\s+законч|"
    r"ресми|бекітіл|мақұлдан|кепілд|approved|official|guarantee",
    re.IGNORECASE,
)
COMPLETION = re.compile(r"(?<![\w-])(?:завершено|завершены|закончены|закончено|аяқталды|бітті|completed)(?![\w-])",
                        re.IGNORECASE)
# Фиксированные фразы, где слово «закончены» стоит в отрицании.
NEGATED_COMPLETION = tuple(T[lang][key] for lang in T for key in ("planned_not_actual",))


def _strings(value):
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)
    elif isinstance(value, (int, float)):
        yield str(value)
        yield fmt_money(abs(value))
        yield str(abs(value))
    elif isinstance(value, str):
        yield value
        for lang in ("ru", "kk"):
            yield fmt_at(value, lang)


def allowed_renderings(fact: dict) -> set[str]:
    out = set(_strings(fact.get("value")))
    if fact.get("kind") == "date" and fact.get("value"):
        out.add(fmt_date(fact["value"], "ru"))
    meta = fact.get("meta") or {}
    out.update(_strings(meta.get("display")))
    return {s for s in out if s and s not in ("нет данных", "деректер жоқ")}


def _strip(text: str, renderings: set[str]) -> str:
    """Удаляем разрешённые записи; числовые — только целым токеном («1» не съедает «11»)."""
    for s in sorted(renderings, key=len, reverse=True):
        if re.search(r"\d", s):
            text = re.sub(r"(?<![\d.,\u202f])" + re.escape(s) + r"(?![\d]|[.,\u202f]\d)", " ", text)
        else:
            text = text.replace(s, " ")
    return text


def statement_violations(st: dict, facts: dict) -> list[str]:
    refs = [facts[i] for i in st.get("fact_ids", []) if i in facts]
    if len(refs) != len(st.get("fact_ids", [])):
        return ["unknown_fact_ref"]
    allowed = set()
    for f in refs:
        allowed |= allowed_renderings(f)
    text = st["text"]
    problems = []
    if st.get("kind") == "quote":
        m = re.search(r"«(.*)»", text, re.S)
        quoted = m.group(1) if m else None
        if not quoted or quoted not in {s for f in refs for s in _strings(f.get("value"))}:
            problems.append("quote_mismatch")
        text = text.replace(quoted or "", " ")
    rest = _strip(text, allowed)
    if re.search(r"\d", rest):
        problems.append("unbacked_number")
    if UNBACKED_QUALITATIVE.search(rest):
        problems.append("unbacked_qualitative")
    for neg in NEGATED_COMPLETION:
        rest = rest.replace(neg, " ")
    if COMPLETION.search(rest):
        status = next((f["value"] for f in refs if f["id"] == "object.status"), None)
        if status != "completed":
            problems.append("unbacked_completion")
    return problems


def audit_statements(statements: list[dict], facts: dict) -> tuple[list[dict], list[str]]:
    kept, codes = [], []
    for st in statements:
        problems = statement_violations(st, facts)
        if problems:
            codes += ["audit_dropped:" + p for p in problems]
        else:
            kept.append(st)
    return kept, sorted(set(codes))
