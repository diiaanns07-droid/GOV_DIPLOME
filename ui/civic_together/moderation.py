"""Модерация текстов инициатив (CONTRACT §10): мат, телефоны, ИИН, e-mail, номера карт — до публикации.

Главный путь — функция R04 ui.civic_ml_api.moderate(text, lang) -> {"text_public", "flags"} (раунд 15).
Пока её нет в сборке — запасной вариант здесь: фильтр мата R04 (profanity.check, уже есть с раунда 14) и простые
шаблоны личных данных. Запасной вариант НЕ публикует сам: инициатива всегда ждёт сотрудника («на проверке»),
а сотрудник видит пометки «похоже на телефон», «грубые слова».

Пометки (flags) — короткие строки: rude, phone, iin, email, card, link. Публичный текст — с «***» вместо найденного.
"""

from __future__ import annotations

import logging
import re

LOGGER = logging.getLogger("civic_together")
MASK = "***"

# Телефон Казахстана: +7 / 8 / 7, затем 10 цифр с пробелами, скобками и дефисами. Короткие городские номера
# («55-12-34») не ищем: такой шаблон закрывал бы и даты «17-10-26». Порядок важен: сначала длинные номера карт
# (16–19 цифр), потом ИИН (12 цифр подряд), потом телефон — иначе карта распалась бы на «телефон» и остаток.
_PATTERNS = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("card", re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)")),
    ("iin", re.compile(r"(?<!\d)\d{12}(?!\d)")),
    ("phone", re.compile(r"(?<![\d+])(?:\+\s*7|8|7)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)")),
    ("link", re.compile(r"(?i)\b(?:https?://|www\.|t\.me/|wa\.me/)\S+")),
)


def _r04_moderate():
    try:
        from ui.civic_ml_api import moderate  # R04, раунд 15
    except Exception:
        return None
    return moderate if callable(moderate) else None


def available() -> bool:
    """Есть ли в сборке модерация R04 (для пометки источника и для правила автопубликации)."""
    return _r04_moderate() is not None


def _normalize_flags(raw) -> list[str]:
    """R04 может вернуть флаги строками или объектами {kind|type|code: …} — приводим к списку строк."""
    out = []
    for item in raw or []:
        if isinstance(item, str):
            kind = item
        elif isinstance(item, dict):
            kind = item.get("kind") or item.get("type") or item.get("code") or item.get("flag")
        else:
            kind = None
        if isinstance(kind, str) and kind and kind not in out:
            out.append(kind[:32])
    return out


def local_check(text: str) -> dict:
    """Запасной вариант: мат (profanity R04, если есть) + личные данные шаблонами. Тот же формат ответа."""
    flags: list[str] = []
    public = text or ""
    try:
        from ui.civic_ml_api import profanity
        verdict = profanity.check(public)
        if verdict.rude:
            flags.append("rude")
            public = verdict.masked
    except Exception:
        pass
    for kind, rx in _PATTERNS:
        if rx.search(public):
            if kind not in flags:
                flags.append(kind)
            public = rx.sub(MASK, public)
    return {"text_public": public, "flags": flags, "source": "local"}


def check(text: str, lang: str | None = None) -> dict:
    """{"text_public", "flags", "source": "r04" | "local"}. Сбой R04 — запасной вариант, не ошибка жителю."""
    if not text:
        return {"text_public": text or "", "flags": [], "source": "none"}
    fn = _r04_moderate()
    if fn is not None:
        try:
            result = fn(text, lang) if lang else fn(text)
            if isinstance(result, dict) and isinstance(result.get("text_public"), str):
                flags = _normalize_flags(result.get("flags"))
                # R04 мог не знать о наших шаблонах (номер карты, ссылка) — добиваем запасным вариантом.
                extra = local_check(result["text_public"])
                for kind in extra["flags"]:
                    if kind not in flags:
                        flags.append(kind)
                return {"text_public": extra["text_public"], "flags": flags, "source": "r04"}
        except Exception:
            LOGGER.exception("модерация R04 не сработала — запасная проверка R16")
    return local_check(text)


def hints(text: str) -> list[str]:
    """Подсказка автору до отправки («уберите телефон»): только виды личных данных, без мата."""
    return [kind for kind in local_check(text)["flags"] if kind in ("phone", "iin", "email", "card")]
