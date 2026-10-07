"""Текстовые утилиты R06: нормализация, похожесть, подсказки о персональных данных.

Подсказки — только помощь модератору. Регулярные выражения не обеспечивают
надёжную деперсонализацию: имена, адреса и описания людей ими не находятся.
Решение о публикации всегда принимает человек.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# Управляющие символы, кроме перевода строки и табуляции, в сообщение не попадают.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁦-⁩]")
_SPACES = re.compile(r"[ \t]+")
_MANY_BREAKS = re.compile(r"\n{3,}")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_KAZAKH = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")

# Порядок важен: ИИН (ровно 12 цифр) проверяется до телефона.
PERSONAL_PATTERNS = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.UNICODE)),
    ("iin", re.compile(r"(?<!\d)\d{12}(?!\d)")),
    ("phone", re.compile(r"(?<![\w+])(?:\+?7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)")),
    ("long_number", re.compile(r"(?<!\d)\d(?:[\s\-]?\d){9,}(?!\d)")),
    ("url", re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)),
)
HINT_LABELS = {
    "email": "адрес электронной почты",
    "iin": "12 цифр подряд (возможно, ИИН)",
    "phone": "номер телефона",
    "long_number": "длинный номер",
    "url": "ссылка",
}
# Эти типы блокируют публикацию, пока модератор их не скроет.
BLOCKING_HINTS = frozenset({"email", "iin", "phone", "long_number"})
REDACTED = "[скрыто]"


def clean_text(value: str) -> str:
    """Каноническая форма пользовательского текста без изменения смысла."""
    text = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _MANY_BREAKS.sub("\n\n", "\n".join(lines)).strip()


def normalize_for_match(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    return " ".join(_WORD.findall(text))


def text_fingerprint(value: str) -> str:
    return hashlib.sha256(normalize_for_match(value).encode("utf-8")).hexdigest()


def tokens(value: str) -> set[str]:
    """Грубая основа слова (первые 5 букв) — без морфологического словаря."""
    return {word[:5] for word in normalize_for_match(value).split() if len(word) >= 3}


def similarity(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def detect_language(value: str) -> str:
    if any(ch in _KAZAKH for ch in value):
        return "kk"
    letters = [ch for ch in value if ch.isalpha()]
    if not letters:
        return "unknown"
    cyrillic = sum(1 for ch in letters if "Ѐ" <= ch <= "ӿ")
    return "ru" if cyrillic >= len(letters) / 2 else "unknown"


_LINK = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def links(value: str) -> list[str]:
    return _LINK.findall(value)


def personal_hints(value: str) -> list[dict]:
    """Найденные фрагменты, похожие на контакты/идентификаторы. Не гарантия полноты."""
    found: list[dict] = []
    taken: list[tuple[int, int]] = []
    for kind, pattern in PERSONAL_PATTERNS:
        for match in pattern.finditer(value):
            start, end = match.span()
            if any(start < other_end and other_start < end for other_start, other_end in taken):
                continue
            taken.append((start, end))
            found.append({"type": kind, "label": HINT_LABELS[kind], "start": start, "end": end})
    found.sort(key=lambda item: item["start"])
    return found


def blocking_hints(value: str) -> list[dict]:
    return [hint for hint in personal_hints(value) if hint["type"] in BLOCKING_HINTS]


def redact(value: str, hints: list[dict]) -> str:
    """Заменить указанные фрагменты на [скрыто]; вызывается по действию модератора."""
    result, cursor = [], 0
    for hint in sorted(hints, key=lambda item: item["start"]):
        if hint["start"] < cursor:
            continue
        result.append(value[cursor:hint["start"]])
        result.append(REDACTED)
        cursor = hint["end"]
    result.append(value[cursor:])
    return "".join(result)


_NAME_LIKE = re.compile(r"(?<![.!?\n]\s)(?<!^)\b[А-ЯЁӘҒҚҢӨҰҮҺІA-Z][а-яёәғқңөұүһіa-z]{2,}")


def hidden_fragments(original: str, published: str) -> set[str]:
    """Эвристика: фрагменты оригинала, которые модератор убрал из публикации.

    Берутся найденные контакты, числа от 4 цифр и слова с заглавной буквы не в
    начале предложения (возможные имена), отсутствующие в опубликованном тексте.
    Нужна, чтобы публичный ответ случайно не процитировал скрытое. Не полная защита.
    """
    kept = set(normalize_for_match(published).split())
    candidates: set[str] = set()
    for hint in personal_hints(original):
        candidates.update(normalize_for_match(original[hint["start"]:hint["end"]]).split())
        digits = re.sub(r"\D", "", original[hint["start"]:hint["end"]])
        if len(digits) >= 4:
            candidates.add(digits)
    candidates.update(word for word in normalize_for_match(original).split()
                      if word.isdigit() and len(word) >= 4)
    candidates.update(normalize_for_match(match.group(0)) for match in _NAME_LIKE.finditer(original))
    return {word for word in candidates if word not in kept and len(word) >= 4}


def mentions_any(value: str, fragments: set[str]) -> list[str]:
    if not fragments:
        return []
    words = normalize_for_match(value).split()
    stems = {word[:5] for word in words if len(word) >= 5 and not word.isdigit()}
    digits = re.sub(r"\D", "", value)
    found = []
    for item in fragments:
        if item.isdigit():
            hit = item in digits
        else:  # разные падежи имени: сравниваем первые 5 букв
            hit = item in words or (len(item) >= 5 and item[:5] in stems)
        if hit:
            found.append(item)
    return sorted(found)
