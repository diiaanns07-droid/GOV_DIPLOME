"""moderate(text, lang?) -> {text_public, flags, …} — очистка текстов сообщества до публикации (CONTRACT §10).

Кому: R16 (инициативы и «старший по двору»), R13 (вопросы к встрече), R17 (обновления кризиса) — вызов в процессе:

    from ui.civic_ml_api import moderate
    m = moderate("Субботник в 10:00, звоните 8 701 123 45 67, Айгуль")
    m["text_public"]   # "Субботник в 10:00, звоните ***, Айгуль" — это видят все
    m["flags"]         # [{"kind": "phone", "group": "pii", "count": 1, "label_ru": "Телефон", …}] — для сотрудника
    m["clean"]         # True — ничего не нашли
    m["action"]        # "publish" (чисто) | "review" (есть находки: сотрудник смотрит оригинал до публикации)

И маршрут POST /api/civic/v2/moderate {text, lang?} — предпросмотр в форме: житель сразу видит, что увидят все.

Что ищем (без сети и моделей, только re; цель — < 5 мс на текст):
  rude      — мат и оскорбления: ui.civic_ml_api.profanity (раунд 14; первая буква слова остаётся: «б*****»);
  phone     — телефоны Казахстана: +7 / 8 / 7 и 10–11 цифр с пробелами, дефисами, скобками («+7 (701) 123-45-67»,
              «8 701 1234567», «87011234567»); городские «21-34-56», «521-34-56» — только с дефисами или пробелами по парам;
  iin       — ИИН / БИН: 12 цифр; контрольная цифра по алгоритму РК (веса 1–11, при остатке 10 — 3–11, 1, 2) —
              в флаге checksum_ok (сколько номеров с верной цифрой). Номер с опечаткой в контрольной цифре всё равно
              скрываем и зовём iin: соседи (R16, R17) блокируют и показывают сотруднику именно этот вид;
  card      — номер карты: 13–19 цифр подряд или группами (проверка Луна — в флаге luhn_ok);
  iban      — счёт KZ… (20 знаков, с пробелами или без);
  email     — адрес e-mail, в том числе «name собака mail.ru», «name (at) gmail (dot) com»;
  apartment — номер квартиры («кв. 45», «квартира 45», «45-пәтер», «пәтер 45»): точный адрес жителя не публикуем;
  contact   — ник в мессенджере (@nick) и ссылки t.me / wa.me / instagram.com / vk.com.
Найденное заменяется на «***». Числа, которые не похожи на личные данные (время 10:00, дата 12.10.2026, «дом 15»,
«1 000 000 тенге», индекс 010000), не трогаем.

Ложные срабатывания проверяются тестами tests/civic/R04/round15/test_r04_moderate.py (корпуса R02, словари R11).
"""

from __future__ import annotations

import re
import time
import unicodedata

from ui.civic_ml_api import profanity

VERSION = "r04-moderate-1"
MAX_TEXT = 5000
MASK = "***"

LABELS = {
    "phone": ("Телефон", "Телефон"),
    "iin": ("ИИН или БИН", "ЖСН не БСН"),
    "id_number": ("Длинный номер (возможно, ИИН или документ)", "Ұзын нөмір (ЖСН не құжат болуы мүмкін)"),
    "card": ("Номер карты", "Карта нөмірі"),
    "iban": ("Номер счёта", "Шот нөмірі"),
    "email": ("E-mail", "E-mail"),
    "apartment": ("Номер квартиры", "Пәтер нөмірі"),
    "contact": ("Контакт в мессенджере", "Мессенджердегі байланыс"),
    "rude": ("Грубые слова", "Дөрекі сөздер"),
}
_PII_ORDER = ("iin", "card", "iban", "phone", "email", "apartment", "contact", "id_number")

# ---------------------------------------------------------------- шаблоны
# Цепочка цифр с разделителями (пробел, дефис, скобки) — кандидат в телефон, ИИН, карту. Точка и «/» не разделители:
# так даты «12.10.2026» и дроби не склеиваются в длинный номер.
# Перед номером не может стоять буква, цифра, дефис, «/», «.», «#»: «osm-node-7127598060», «cand-r12-13-07-2026» —
# идентификаторы, а не телефоны (ложные срабатывания на data/civic/astana).
_DIGIT_RUN = re.compile(r"(?<![\w+\-/.#])\+?\d(?:[ \t\-()\xa0]{0,3}\d)+(?![\w\-/])")
# R15-S48: подпись вплотную к номеру через точку или дефис («Тел.87011234567», «ИИН-900101300126») — номер ищем
# после подписи отдельно (сам _DIGIT_RUN после «.» и «-» не начинается: это защита от id «osm-node-7127598060»).
_LABELED_RUN = re.compile(r"(?<![\w])(?:тел|т|моб|сот|ватсап|whatsapp|tel|phone|иин|жсн|бин|iin)[.\-:]\s*"
                          r"(\+?\d(?:[ \t\-()\xa0]{0,3}\d)+)(?![\w\-/])", re.IGNORECASE)
# R15-S48: мобильный через точки «8.701.123.45.67» — дата «12.10.2026» сюда не подходит (2-2-4, а не 1-3-3-2-2).
_DOTTED_PHONE = re.compile(r"(?<![\w.])(?:\+?7|8)\.\d{3}\.\d{3}\.\d{2}\.\d{2}(?![\w.])")
_THOUSANDS = re.compile(r"^\d{1,3}(?:[ \xa0]\d{3})+$")
_LOCAL_PHONE = re.compile(r"^\d{2,3}-\d{2}-\d{2}$")    # городской — только с дефисами: «дома 15 17 18» не телефон
_EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}(?![\w-])")
_EMAIL_OBF = re.compile(
    r"(?<![\w.+-])[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}\s*(?:@|\(\s*at\s*\)|\[\s*at\s*\]|\s(?:at|собака|собачка)\s)\s*"
    r"[A-Za-z0-9-]{2,63}\s*(?:\.|\(\s*dot\s*\)|\[\s*dot\s*\]|\s(?:dot|точка)\s)\s*"
    r"(?:ru|kz|com|net|org|info|mail|ua|by|рф|кз|ру)(?![\w])", re.IGNORECASE)
_IBAN = re.compile(r"(?<![\w])KZ\d{2}(?:[ ]?[A-Z0-9]){16}(?![\w])", re.IGNORECASE)
_APARTMENT = re.compile(
    r"(?P<pre>\b(?:кв\.?|квартир[аеуыой]{1,2}|пәтер|патер|апарт\w*)\s*№?\s*)(?P<num>\d{1,4}[а-яa-z]?)\b"
    r"|(?P<num2>\b\d{1,4})(?P<post>\s*-?\s*(?:пәтер|патер)\w*)", re.IGNORECASE)
_HANDLE = re.compile(r"(?<![\w@.])@[A-Za-z][A-Za-z0-9_]{3,31}(?![\w@])")
_LINK = re.compile(r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me|wa\.me|api\.whatsapp\.com|instagram\.com|vk\.com|"
                   r"facebook\.com|fb\.com|tiktok\.com)/[^\s,;)]+", re.IGNORECASE)


def iin_checksum_ok(digits: str) -> bool:
    """Контрольная цифра ИИН/БИН РК: веса 1..11; остаток 10 -> веса 3..11,1,2; снова 10 -> номер недействителен."""
    if len(digits) != 12 or not digits.isdigit():
        return False
    d = [int(ch) for ch in digits]
    s = sum(d[i] * (i + 1) for i in range(11)) % 11
    if s == 10:
        weights = (3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2)
        s = sum(d[i] * weights[i] for i in range(11)) % 11
        if s == 10:
            return False
    return s == d[11]


def luhn_ok(digits: str) -> bool:
    total, double = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if double:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        double = not double
    return total % 10 == 0


def ascii_digits(raw: str) -> str:
    """Цифры строки как ASCII: полноширинные «８７０…» и другие десятичные цифры Юникода — тоже (R15-S48)."""
    return "".join(str(unicodedata.decimal(ch)) for ch in raw if unicodedata.decimal(ch, None) is not None)


def _classify_run(raw: str) -> str | None:
    """Вид цепочки цифр: phone | iin | card | None (обычное число)."""
    digits = ascii_digits(raw)
    n = len(digits)
    # Скобка — только после кода страны или восьмёрки («+7 (701)», «8 (7172)»), а «2025-2029 (2025-2026» — годы.
    if "(" in raw and len(re.sub(r"\D", "", raw.split("(", 1)[0])) > 2:
        return None
    plus = raw.lstrip().startswith("+")
    thousands = bool(_THOUSANDS.match(raw.strip()))
    if n == 11 and digits[0] in "78" and not thousands:
        return "phone"
    if n == 11 and plus:
        return "phone"
    if n == 10 and digits[0] == "7" and not thousands:
        return "phone"                     # 701 123 45 67 без восьмёрки
    if n == 12:
        # «1 000 000 000 000» — сумма, а не ИИН, если контрольная цифра не сходится.
        return None if thousands and not iin_checksum_ok(digits) else "iin"
    if 13 <= n <= 19:
        return None if thousands and not luhn_ok(digits) else "card"
    if n in (6, 7) and _LOCAL_PHONE.match(raw.strip()):
        return "phone"
    return None


def _pii_spans(text: str) -> list[tuple[int, int, str]]:
    """[(start, end, kind)] личных данных в исходном тексте, без пересечений (раньше найденное важнее)."""
    spans: list[tuple[int, int, str]] = []

    def add(start: int, end: int, kind: str) -> None:
        if start < end and not any(a < end and start < b for a, b, _k in spans):
            spans.append((start, end, kind))

    for m in _LINK.finditer(text):
        add(m.start(), m.end(), "contact")
    for m in _EMAIL.finditer(text):
        add(m.start(), m.end(), "email")
    for m in _EMAIL_OBF.finditer(text):
        add(m.start(), m.end(), "email")
    for m in _IBAN.finditer(text):
        add(m.start(), m.end(), "iban")
    # Сначала номер после подписи и номер через точки: «моб-8 701 123 45 67» целиком, а не «8» + остаток.
    for m in _LABELED_RUN.finditer(text):
        kind = _classify_run(m.group(1))
        if kind:
            add(m.start(1), m.end(1), kind)
    for m in _DOTTED_PHONE.finditer(text):
        add(m.start(), m.end(), "phone")
    for m in _DIGIT_RUN.finditer(text):
        raw = m.group()
        # Скобка в конце цепочки («(8 701 …)») — не часть номера.
        start, end = m.start(), m.end()
        while end > start and text[end - 1] in " -(\t\xa0":
            end -= 1
        kind = _classify_run(text[start:end])
        if kind:
            add(start, end, kind)
        del raw
    for m in _APARTMENT.finditer(text):
        if m.group("num"):
            add(m.start("num"), m.end("num"), "apartment")
        elif m.group("num2"):
            add(m.start("num2"), m.end("num2"), "apartment")
    for m in _HANDLE.finditer(text):
        add(m.start(), m.end(), "contact")
    spans.sort()
    return spans


def _hint(kinds: list[str], rude: bool) -> tuple[str | None, str | None]:
    """Подсказка для формы жителя (предпросмотр «Это увидят все»)."""
    if not kinds and not rude:
        return None, None
    ru, kk = [], []
    if kinds:
        names_ru = ", ".join(LABELS[k][0].lower() if k not in ("email",) else LABELS[k][0] for k in kinds)
        names_kk = ", ".join(LABELS[k][1].lower() if k not in ("email",) else LABELS[k][1] for k in kinds)
        ru.append(f"Личные данные скрыты ({names_ru}): их увидят только сотрудники акимата.")
        kk.append(f"Жеке деректер жасырылды ({names_kk}): оларды тек әкімдік қызметкерлері көреді.")
    if rude:
        ru.append("Грубые слова скрыты звёздочками.")
        kk.append("Дөрекі сөздер жұлдызшамен жасырылды.")
    return " ".join(ru), " ".join(kk)


def _text(value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError("text: нужна строка.")
    if len(value) > MAX_TEXT:
        raise ValueError(f"text: не длиннее {MAX_TEXT} символов.")
    return value


def moderate(text=None, lang=None, body=None, **_ignored) -> dict:
    """Публичный текст и находки для сотрудника. body — тело POST целиком (шлюз R01: {"body": body}).

    Ответ: {text_public, clean, action, flags:[{kind, group, count, label_ru, label_kk}], rude, pii,
            hint_ru, hint_kk, version, ms}. Оригинал текста в ответ не входит.
    """
    started = time.perf_counter()
    if isinstance(body, dict):
        text = body.get("text", text)
        lang = body.get("lang", lang)
    text = _text(text)
    if lang not in (None, "", "ru", "kk", "mixed"):
        raise ValueError("lang: ru, kk или mixed.")
    pii = _pii_spans(text) if text else []
    verdict = profanity.check(text) if text else profanity.Verdict(False, masked=text)
    rude_spans = [(a, b) for a, b, _k in verdict.spans if not any(x < b and a < y for x, y, _kk in pii)]

    # Собираем публичный текст справа налево: личные данные -> «***», грубые слова -> маска profanity.
    pieces = [(a, b, MASK) for a, b, _k in pii]
    for a, b in rude_spans:
        piece = text[a:b]
        pieces.append((a, b, piece[0] + "".join(profanity.MASK_CHAR if (ch.isalnum() or ch in "@$") else ch
                                                for ch in piece[1:])))
    public = text
    for a, b, repl in sorted(pieces, reverse=True):
        public = public[:a] + repl + public[b:]

    counts: dict[str, int] = {}
    valid: dict[str, int] = {}
    for a, b, kind in pii:
        counts[kind] = counts.get(kind, 0) + 1
        digits = ascii_digits(text[a:b])
        if (kind == "iin" and iin_checksum_ok(digits)) or (kind == "card" and luhn_ok(digits)):
            valid[kind] = valid.get(kind, 0) + 1
    kinds = [k for k in _PII_ORDER if k in counts]
    flags = []
    for k in kinds:
        flag = {"kind": k, "group": "pii", "count": counts[k], "label_ru": LABELS[k][0], "label_kk": LABELS[k][1]}
        if k == "iin":
            flag["checksum_ok"] = valid.get(k, 0)      # сколько из них — настоящий ИИН/БИН по контрольной цифре
        elif k == "card":
            flag["luhn_ok"] = valid.get(k, 0)
        flags.append(flag)
    if rude_spans:
        flags.append({"kind": "rude", "group": "rude", "count": len(rude_spans), "label_ru": LABELS["rude"][0],
                      "label_kk": LABELS["rude"][1], "kinds": verdict.kinds})
    hint_ru, hint_kk = _hint(kinds, bool(rude_spans))
    clean = not flags
    return {
        "text_public": public,
        "clean": clean,
        "action": "publish" if clean else "review",
        "flags": flags,
        "rude": bool(rude_spans),
        "pii": bool(kinds),
        "hint_ru": hint_ru, "hint_kk": hint_kk,
        "version": VERSION,
        "ms": round((time.perf_counter() - started) * 1000, 3),
    }


def public_text(text) -> str:
    """Только публичный текст (для подписи, заголовка, «старшего по двору»). Не строка — как есть."""
    if not isinstance(text, str) or not text:
        return text
    return moderate(text[:MAX_TEXT])["text_public"]


def moderation_record(result: dict) -> dict:
    """Поле moderation для записи соседа (как в раунде 14): без текста и без самих найденных данных."""
    return {"rude": bool(result.get("rude")), "pii": bool(result.get("pii")),
            "kinds": [f["kind"] for f in result.get("flags") or []],
            "count": sum(int(f.get("count") or 0) for f in result.get("flags") or []),
            "version": VERSION}
