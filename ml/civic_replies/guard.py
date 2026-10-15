"""Языковая модель для черновика — только «пригладить» шаблон, и только без новых фактов (как agent/evidence.py).

    from ml.civic_replies.guard import polish
    text, accepted, reason = polish(template_text, "ru", llm=my_llm)   # my_llm(text, lang) -> str

Текст модели принимается, если в нём:
  - нет чисел, которых не было в шаблоне (номер, сроки, «9 рабочих дней» — только из записи);
  - нет числительных словами («три дня», «екі күн») и названий месяцев, которых не было в шаблоне;
  - нет названий служб, которых не было в шаблоне (модель не «передаёт» обращение сама);
  - длина не больше полутора шаблонов и не меньше половины.
Иначе — шаблон как есть и причина (её видит сотрудник). Без llm — шаблон (по умолчанию модель выключена;
в облаке и в тестах сети нет). Сеть здесь не используется: llm — функция, которую передаёт вызывающий.
"""

from __future__ import annotations

import re

from ml.civic_replies.templates import MONTHS_KK, MONTHS_RU

_DIGITS = re.compile(r"\d+")
_NUMERAL_WORDS = frozenset("""
один одна одно одного одной одному одну двух два две три трёх трех четыре четырёх четырех пять пяти шесть шести семь
семи восемь восьми девять девяти десять десяти одиннадцать двенадцать пятнадцать двадцать тридцать сорок пятьдесят сто
неделю недели неделя недель месяц месяца месяцев сутки суток
бір екі үш төрт бес алты жеті сегіз тоғыз он жиырма отыз апта ай
""".split())
_WORD = re.compile(r"[\wәғқңөұүһі]+", re.IGNORECASE)


def _words(text: str) -> list[str]:
    return [w.casefold().replace("ё", "е") for w in _WORD.findall(text)]


def check(template: str, candidate: str, service_names: list[str] | None = None) -> str | None:
    """None — кандидат годится; иначе причина отказа (по-русски, для сотрудника)."""
    if not isinstance(candidate, str) or not candidate.strip():
        return "модель вернула пустой текст"
    if not 0.5 * len(template) <= len(candidate) <= 1.5 * len(template) + 40:
        return "модель сильно изменила длину текста"
    new_numbers = set(_DIGITS.findall(candidate)) - set(_DIGITS.findall(template))
    if new_numbers:
        return "модель добавила числа: " + ", ".join(sorted(new_numbers))
    base_words = set(_words(template))
    cand_words = _words(candidate)
    bad = sorted({w for w in cand_words if w in _NUMERAL_WORDS and w not in base_words})
    if bad:
        return "модель добавила числительные: " + ", ".join(bad)
    months = {m.casefold() for m in MONTHS_RU + MONTHS_KK}
    new_months = sorted({w for w in cand_words if w in months and w not in base_words})
    if new_months:
        return "модель добавила даты: " + ", ".join(new_months)
    low_t, low_c = template.casefold(), candidate.casefold()
    for name in service_names or []:
        if name and name.casefold() in low_c and name.casefold() not in low_t:
            return "модель назвала службу, которой нет в записи: " + name
    return None


def polish(template: str, lang: str, llm=None, service_names: list[str] | None = None) -> tuple[str, bool, str | None]:
    """(текст, принят ли текст модели, причина отказа). llm(text, lang) -> str; сбой модели — шаблон."""
    if llm is None:
        return template, False, None
    try:
        candidate = llm(template, lang)
    except Exception as exc:  # noqa: BLE001 — модель недоступна: шаблон
        return template, False, f"модель недоступна: {type(exc).__name__}"
    reason = check(template, candidate, service_names)
    return (candidate.strip(), True, None) if reason is None else (template, False, reason)
