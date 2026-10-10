"""Обезличивание текстов жителей (R02, раунд 14) — только stdlib, без сети.

Заменяет на маркеры:
  [ссылка]   — http(s)://…, www.…, t.me/…
  [email]    — адреса почты
  [ИИН]      — 12 цифр подряд (ИИН/БИН)
  [номер]    — номера карт (13–19 цифр) и прочие длинные числа (≥ 9 цифр)
  [телефон]  — +7 / 8 / 7xx…, городские 2-2-2 через дефис
  [госномер] — номера машин РК: «123 ABC 01», «A 123 BCD»
  [адрес]    — номер дома/квартиры/подъезда/этажа: «д. 12, кв. 5», «Кенесары 40/1», «12-үй», «пәтер 15»
  [имя]      — имя после «меня зовут», «менің атым», подпись «С уважением, …», «Иванов И.И.»

Улицы, районы, школы «№12», ЖК и остановки НЕ удаляются: это публичные места, без них жалоба
теряет смысл. Имена удаляются только по явным шаблонам — поэтому import_form.py помечает строки
с оставшимися подозрительными числами для ручной проверки.

В отчёт попадают только счётчики и номера строк — никогда сами телефоны, адреса и имена.

Командная строка:
    python -m ml.labeling.anonymize private/raw.jsonl --out private/clean.jsonl
    python -m ml.labeling.anonymize "текст с номером +7 701 123 45 67"   # быстрый просмотр одной строки
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

from ml.labeling.text_utils import check_output_path

M_URL, M_EMAIL, M_IIN, M_NUM = "[ссылка]", "[email]", "[ИИН]", "[номер]"
M_PHONE, M_PLATE, M_ADDR, M_NAME = "[телефон]", "[госномер]", "[адрес]", "[имя]"
MARKERS = (M_URL, M_EMAIL, M_IIN, M_NUM, M_PHONE, M_PLATE, M_ADDR, M_NAME)

UP = "А-ЯЁӘҒҚҢӨҰҮҺІ"
LO = "а-яёәғқңөұүһі"
WORD_CHARS = UP + LO + "A-Za-z"

# ── 1. Ссылки и почта ─────────────────────────────────────────────────────────
_URL = re.compile(r"(?:https?://|www\.|t\.me/|instagram\.com/|wa\.me/)\S+", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# ── 2. Числовые идентификаторы ────────────────────────────────────────────────
_IIN = re.compile(r"(?<![\d+])\d{12}(?!\d)")
_CARD = re.compile(r"(?<!\d)(?:\d{4}[ \-]?){3}\d{1,7}(?!\d)")
# Телефон: +7 / 8 / 7 и ещё 10 цифр с любыми разделителями; либо мобильный 7xx без кода страны.
_PHONE = re.compile(
    r"(?<![\w+])(?:\+\s?7|8|7)[\s\-().]*\d{3}[\s\-().]*\d{3}[\s\-.]*\d{2}[\s\-.]*\d{2}(?!\d)"
    r"|(?<![\w+])\(?7\d{2}\)?[\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)"
)
# Городской номер только с дефисами: «57-12-34», «321-45-67» (даты пишут через точку — не задеваем).
_CITY_PHONE = re.compile(r"(?<![\d\-.])\d{2,3}-\d{2}-\d{2}(?![\d\-])")
_LONG_NUM = re.compile(r"(?<!\d)\d{9,}(?!\d)")

# ── 3. Госномера РК ───────────────────────────────────────────────────────────
# Новый формат «123 ABC 01» (латиница или похожая кириллица, регион 01–20), старый «A 123 BCD».
_PLATE_NEW = re.compile(r"(?<![\w])\d{3}\s?[A-ZА-Я]{2,3}\s?(?:0[1-9]|1\d|20)(?![\w])")
_PLATE_OLD = re.compile(r"(?<![\w])[A-Z]\s?\d{3}\s?[A-Z]{2,3}(?![\w])")

# ── 4. Адрес: номер дома / квартиры / подъезда ────────────────────────────────
# Регулярки собираются конкатенацией строк (не .format): в них много фигурных скобок {1,4}.
_LETTER_SUFFIX = r"(?:\s?[" + LO + r"a-z](?![" + LO + r"a-z]))?"            # «18а», «40 б»
_NUM = r"№?\s?\d{1,4}(?:\s?[/\-]\s?\d{1,4})?" + _LETTER_SUFFIX
_HOUSE_RU = (r"(?:дом(?:а|е|у|ом)?|д\.|кв(?:артир(?:а|е|у|ы|ой))?\.?|кв-р[аеыу]|подъезд(?:а|е|у)?|под\.|"
             r"корпус(?:а|е)?|корп\.|блок(?:а|е)?|этаж(?:а|е)?|офис(?:а|е)?)")
_NOT_AFTER_WORD = r"(?<![" + WORD_CHARS + r"])"
# цепочка «д. 12, кв. 5, подъезд 3» — одним маркером
_ADDR_CHAIN = re.compile(_NOT_AFTER_WORD + _HOUSE_RU + r"\s*" + _NUM + r"(?:\s*,?\s*" + _HOUSE_RU + r"\s*" + _NUM + r")*"
                         + r"(?!\s*этаж)", re.I)
# «на 2 этаже», «в 3 подъезде» — число ПЕРЕД словом
# «5 этажей» — это не адрес, поэтому только «этаже» и «подъезд(е)»
_ADDR_NUM_BEFORE = re.compile(r"(?<![\d\w])\d{1,3}(?:-?(?:м|ом|й))?\s+(?:подъезд(?:е|а|у)?|этаже)(?![" + LO + r"])", re.I)
# казахский: «12-үй», «№12 үй», «15-пәтер», «3-подъезд», «4-қабат»; и «үй 12», «пәтер 15»
_KK_UNITS = r"(?:үй|пәтер|кіреберіс|подъезд|қабат)[" + LO + r"]*"
_ADDR_KK_AFTER = re.compile(r"(?:№\s?)?\d{1,4}(?:/\d{1,4})?\s?[\-–]?\s?" + _KK_UNITS, re.I)
_ADDR_KK_BEFORE = re.compile(_NOT_AFTER_WORD + r"(?:үй|пәтер)\s*№?\s*\d{1,4}(?:/\d{1,4})?", re.I)
# После номера не должно идти то, что делает его НЕ номером дома: «5 минут», «3-й», «10%».
_NOT_HOUSE_TAIL = (r"(?!\s*(?:-?(?:й|го|ый|ая|ой|ші|шы)(?![" + LO + r"])|%|\d|"
                   r"(?:мин|час|дн|дня|дней|лет|год|раз|см|км|тг|тенге|₸|маршрут|автобус|этаж)))")
_HOUSE_NUM = r"(\d{1,4}(?:\s?/\s?\d{1,4})?" + _LETTER_SUFFIX + r")" + _NOT_HOUSE_TAIL
# улица + номер: «ул. Кенесары 40», «пр. Кабанбай батыра, 53/1», «Кенесары көшесі, 40»
_STREET_KW = (r"(?:ул\.|улиц[аеиу]|пр\.|пр-т|проспект[аеу]?|пер\.|переул(?:ок|ке)|шоссе|бульвар[аеу]?|б-р|"
              r"мкр\.?|микрорайон[аеу]?)")
_STREET_NUM = re.compile(
    r"(" + _STREET_KW + r"\s*(?:[" + UP + r"][" + WORD_CHARS + r"\-]*\.?\s+){0,2}[" + UP + r"][" + WORD_CHARS + r"\-]*\.?)"
    r"\s*,?\s*(?:д(?:ом)?\.?\s*)?" + _HOUSE_NUM, re.I)
_STREET_KK = re.compile(
    r"((?:[" + UP + r"][" + WORD_CHARS + r"\-]*\s+){1,3}(?:көшесі|даңғылы)[" + LO + r"]*)\s*,?\s*" + _HOUSE_NUM, re.I)
# «<Слово с большой буквы> <номер>/<номер>»: дробь почти всегда номер дома
_NAME_SLASH = re.compile(_NOT_AFTER_WORD + r"([" + UP + r"][" + LO + r"]+(?:\s+[" + UP + r"]?[" + LO + r"]+)?)\s+"
                         r"(\d{1,4}\s?/\s?\d{1,4}[" + LO + r"a-z]?)(?![\d/])")
# известные улицы Астаны + номер дома («Кенесары 40», «Сыганак 18а»)
KNOWN_STREETS = ("Абая", "Акмешит", "Байтурсынова", "Бейбитшилик", "Богенбай батыра", "Достык", "Жубанова",
                 "Иманова", "Кабанбай батыра", "Кенесары", "Кошкарбаева", "Мангилик Ел", "Момышулы", "Мухамедханова",
                 "Республики", "Сарыарка", "Сатпаева", "Сейфуллина", "Сыганак", "Тауелсиздик", "Туран", "Улы Дала",
                 "Хусейн бен Талал", "Шокана Валиханова", "Тлендиева", "Ауэзова", "Пушкина", "Петрова", "Жумабаева",
                 "Шарля де Голля", "Орынбор", "Анет баба", "Нажимеденова")
_KNOWN_STREET_NUM = re.compile(
    _NOT_AFTER_WORD + r"(" + "|".join(re.escape(x) for x in sorted(KNOWN_STREETS, key=len, reverse=True)) + r")"
    r"\s*,?\s*" + _HOUSE_NUM, re.I)

# ── 5. Имена по явным шаблонам ────────────────────────────────────────────────
_NAME_WORD = r"[" + UP + r"][" + LO + r"]+(?:-[" + UP + r"][" + LO + r"]+)?"
_INITIALS = r"[" + UP + r"]\.\s?(?:[" + UP + r"]\.)?"
_NAME_INTRO = re.compile(
    r"((?:меня зовут|мо[её] имя|я\s*[-—–]|менің атым|менің есімім|с уважением,?|құрметпен,?|"
    r"фио:?|автор:?|подпись:?)\s+)" + _NAME_WORD + r"(?:\s+" + _NAME_WORD + r"){0,2}(?:\s+" + _INITIALS + r")?",
    re.I)
_NAME_INITIALS = re.compile(_NOT_AFTER_WORD + _NAME_WORD + r"\s+[" + UP + r"]\.\s?[" + UP + r"]\.|" +
                            _NOT_AFTER_WORD + r"[" + UP + r"]\.\s?[" + UP + r"]\.\s?" + _NAME_WORD)

_SPACES = re.compile(r"[ \t]+")


def _sub(rx: re.Pattern, repl, text: str, counts: dict, marker: str) -> str:
    new, n = rx.subn(repl, text)
    if n:
        counts[marker] = counts.get(marker, 0) + n
    return new


def anonymize(text: str) -> tuple[str, dict]:
    """Текст → (обезличенный текст, {маркер: число замен}). Порядок важен: от точных шаблонов к общим."""
    counts: dict[str, int] = {}
    t = text
    t = _sub(_URL, M_URL, t, counts, M_URL)
    t = _sub(_EMAIL, M_EMAIL, t, counts, M_EMAIL)
    t = _sub(_IIN, M_IIN, t, counts, M_IIN)          # раньше телефона: 12 цифр подряд — не телефон
    t = _sub(_PHONE, M_PHONE, t, counts, M_PHONE)
    t = _sub(_CARD, M_NUM, t, counts, M_NUM)
    t = _sub(_LONG_NUM, M_NUM, t, counts, M_NUM)
    t = _sub(_CITY_PHONE, M_PHONE, t, counts, M_PHONE)
    t = _sub(_PLATE_NEW, M_PLATE, t, counts, M_PLATE)
    t = _sub(_PLATE_OLD, M_PLATE, t, counts, M_PLATE)
    t = _sub(_NAME_INTRO, lambda m: m.group(1) + M_NAME, t, counts, M_NAME)
    t = _sub(_NAME_INITIALS, M_NAME, t, counts, M_NAME)
    t = _sub(_ADDR_KK_AFTER, M_ADDR, t, counts, M_ADDR)
    t = _sub(_ADDR_KK_BEFORE, M_ADDR, t, counts, M_ADDR)
    t = _sub(_STREET_NUM, lambda m: m.group(1) + " " + M_ADDR, t, counts, M_ADDR)
    t = _sub(_STREET_KK, lambda m: m.group(1) + " " + M_ADDR, t, counts, M_ADDR)
    t = _sub(_KNOWN_STREET_NUM, lambda m: m.group(1) + " " + M_ADDR, t, counts, M_ADDR)
    t = _sub(_NAME_SLASH, lambda m: m.group(1) + " " + M_ADDR, t, counts, M_ADDR)
    t = _sub(_ADDR_CHAIN, M_ADDR, t, counts, M_ADDR)
    t = _sub(_ADDR_NUM_BEFORE, M_ADDR, t, counts, M_ADDR)
    # «[адрес], [адрес]» после цепочек — один маркер
    t = re.sub(r"\[адрес\](?:\s*,?\s*\[адрес\])+", M_ADDR, t)
    t = _SPACES.sub(" ", t).strip()
    return t, counts


# Что могло остаться: числа из 5+ цифр, «@», латиница с цифрами — показать человеку.
_SUSPICIOUS = re.compile(r"\d{5,}|@|\b[A-Za-z]+\d+[A-Za-z\d]*\b|\+\s?\d")


def needs_review(clean_text: str) -> bool:
    return bool(_SUSPICIOUS.search(clean_text))


def merge_counts(total: dict, part: dict) -> None:
    for k, v in part.items():
        total[k] = total.get(k, 0) + v


# ── чтение / запись ──────────────────────────────────────────────────────────

def read_records(path: Path, field: str = "text") -> list[dict]:
    raw = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() in (".csv", ".tsv"):
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t") if raw.strip() else csv.excel
        return list(csv.DictReader(io.StringIO(raw), dialect=dialect))
    rows = []
    for n, line in enumerate(raw.splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{n}: не JSON ({exc.msg})") from None
    return rows


def anonymize_records(rows: list[dict], field: str = "text") -> tuple[list[dict], dict]:
    """Обезличивает поле field у каждой записи. Отчёт — только счётчики и номера строк."""
    total: dict[str, int] = {}
    changed, review = 0, []
    out = []
    for i, row in enumerate(rows):
        row = dict(row)
        text = str(row.get(field) or "")
        clean, counts = anonymize(text)
        if counts:
            changed += 1
            merge_counts(total, counts)
        row[field] = clean
        row["anonymized"] = counts
        if needs_review(clean):
            review.append(i)
        out.append(row)
    report = {"rows": len(rows), "rows_changed": changed, "replaced": dict(sorted(total.items())),
              "rows_for_manual_review": review,
              "note": "в отчёте нет исходных значений; имена удаляются только по явным шаблонам — проверьте вручную"}
    return out, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Обезличивание текстов жителей → маркеры [телефон], [адрес] и т. п.")
    ap.add_argument("input", help="файл .jsonl/.csv или просто текст в кавычках")
    ap.add_argument("--out", type=Path, help="куда записать JSONL (по умолчанию — только отчёт)")
    ap.add_argument("--field", default="text", help="поле с текстом (по умолчанию text)")
    ap.add_argument("--report", type=Path, help="куда записать отчёт JSON (по умолчанию <out>.report.json)")
    ap.add_argument("--allow-outside-private", action="store_true", help="разрешить запись вне private/ (только синтетика)")
    args = ap.parse_args(argv)

    src = Path(args.input)
    if not src.exists():
        clean, counts = anonymize(args.input)
        print(clean)
        print(json.dumps(counts, ensure_ascii=False), file=sys.stderr)
        return 0
    rows = read_records(src, args.field)
    out_rows, report = anonymize_records(rows, args.field)
    report["input"] = src.name
    if args.out:
        check_output_path(args.out, args.allow_outside_private)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            for r in out_rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        rep = args.report or args.out.with_suffix(".report.json")
        check_output_path(rep, args.allow_outside_private)
        rep.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"записано: {args.out} ({len(out_rows)} строк), отчёт: {rep}")
    print(json.dumps({k: report[k] for k in ("rows", "rows_changed", "replaced")}, ensure_ascii=False))
    print(f"на ручную проверку: {len(report['rows_for_manual_review'])} строк")
    return 0


if __name__ == "__main__":
    sys.exit(main())
