"""CSV из Google-формы → JSONL для разметки, с обезличиванием (R02, раунд 14).

Форма (research/round-14/LOCAL_TASKS.md, LOCAL-6): «Текст жалобы / Шағым мәтіні», «Язык / Тіл»,
«Район Астаны / Аудан», флажок согласия. Столбцы находятся по словам в заголовке (ru/kk/en),
поэтому переименование вопроса в форме не ломает импорт.

Что делает:
  1. оставляет только строки с отмеченным согласием и непустым текстом (≥ 3 букв);
  2. обезличивает текст (ml/labeling/anonymize.py) ДО всего остального;
  3. убирает точные повторы (после нормализации регистра, ё/е, пунктуации);
  4. язык: ответ формы → ru/kk/mixed, плюс автоопределение (lang_auto) для сравнения;
  5. от времени ответа оставляет только дату (меньше риск узнать человека);
  6. id = "f-" + хеш обезличенного текста: тот же текст → тот же id при повторном импорте;
  7. перемешивает порядок с фиксированным зерном (ответы одного человека не идут подряд).

Выход — ТОЛЬКО в private/ (папка вне Git): JSONL, отчёт .report.json (только числа) и
.review.txt — строки, где после обезличивания остались подозрительные числа/латиница: их
нужно просмотреть глазами до разметки.

    python -m ml.labeling.import_form private/form.csv
    python -m ml.labeling.import_form private/form.csv --out private/form_2026-10-13.jsonl
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import re
import sys
from datetime import date
from pathlib import Path

from ml.labeling.anonymize import anonymize, merge_counts, needs_review
from ml.labeling.text_utils import PRIVATE, check_output_path, guess_lang, normalize

SCHEMA = "birge-form-v1"
MIN_LETTERS = 3

# Слова в заголовках столбцов (в нижнем регистре). Первое совпадение выигрывает.
COLUMNS = {
    "text": ("текст жалобы", "шағым мәтіні", "текст", "мәтін", "жалоба", "шағым", "complaint", "text"),
    "lang": ("язык", "тіл", "language", "lang"),
    "district": ("район", "аудан", "district"),
    "consent": ("согласен", "согласна", "согласие", "келісемін", "келісім", "consent", "agree"),
    "timestamp": ("отметка времени", "уақыт белгісі", "timestamp", "время", "дата"),
}
LANG_MAP = {"қазақша": "kk", "казахский": "kk", "kk": "kk", "kz": "kk", "қаз": "kk",
            "русский": "ru", "орысша": "ru", "ru": "ru", "рус": "ru",
            "аралас": "mixed", "смешанный": "mixed", "mixed": "mixed", "вперемешку": "mixed"}
DISTRICTS = {"алматы": "almaty", "байконур": "baikonur", "байқоңыр": "baikonur", "есиль": "yesil", "есіл": "yesil",
             "нура": "nura", "нұра": "nura", "сарайшык": "saraishyk", "сарайшық": "saraishyk",
             "сарыарка": "saryarka", "сарыарқа": "saryarka"}
NO_ANSWERS = {"", "нет", "жоқ", "no", "false", "0"}


def find_columns(header: list[str]) -> dict[str, int | None]:
    low = [h.lower().strip() for h in header]
    found: dict[str, int | None] = {}
    for key, words in COLUMNS.items():
        found[key] = None
        for w in words:
            idx = next((i for i, h in enumerate(low) if w in h and i not in found.values()), None)
            if idx is not None:
                found[key] = idx
                break
    return found


def read_csv(path: Path) -> list[list[str]]:
    raw = path.read_text(encoding="utf-8-sig")
    if not raw.strip():
        return []
    try:
        dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [r for r in csv.reader(io.StringIO(raw), dialect) if any(c.strip() for c in r)]


def norm_lang(answer: str) -> str:
    a = answer.lower().strip()
    for k, v in LANG_MAP.items():
        if a.startswith(k):
            return v
    return ""


def norm_district(answer: str) -> str:
    a = answer.lower().strip()
    if not a:
        return ""
    for k, v in DISTRICTS.items():
        if a.startswith(k):
            return v
    return "other"


def parse_date(stamp: str) -> str:
    """Только дата. Google Forms: «11.10.2026 10:01:12» (ru), «10/11/2026 10:01:12» (en-US), ISO."""
    s = stamp.strip()
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:
        d, mo, y = map(int, m.groups())
    else:
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
        if m:
            mo, d, y = map(int, m.groups())
        else:
            m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
            if not m:
                return ""
            y, mo, d = map(int, m.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return ""


def form_id(clean_text: str) -> str:
    return "f-" + hashlib.sha1(normalize(clean_text).encode("utf-8")).hexdigest()[:10]


def convert(rows: list[list[str]], shuffle_seed: int = 2026) -> tuple[list[dict], dict, list[dict]]:
    """Строки CSV (с заголовком) → (записи, отчёт с числами, строки на ручную проверку)."""
    if not rows:
        return [], {"rows": 0, "kept": 0}, []
    header, body = rows[0], rows[1:]
    cols = find_columns(header)
    if cols["text"] is None:
        raise SystemExit("Не найден столбец с текстом жалобы. Заголовки: " + " | ".join(header))
    rep = {"rows": len(body), "kept": 0, "no_consent": 0, "empty_or_short": 0, "duplicates": 0,
           "replaced": {}, "rows_changed_by_anonymizer": 0, "for_manual_review": 0,
           "lang_form": {}, "lang_auto": {}, "lang_disagree": 0, "district": {},
           "consent_column": header[cols["consent"]] if cols["consent"] is not None else None,
           "text_column": header[cols["text"]]}
    out, review, seen = [], [], set()

    def cell(r: list[str], key: str) -> str:
        i = cols[key]
        return r[i].strip() if i is not None and i < len(r) else ""

    for r in body:
        if cols["consent"] is not None and cell(r, "consent").lower() in NO_ANSWERS:
            rep["no_consent"] += 1
            continue
        text = re.sub(r"\s+", " ", cell(r, "text")).strip()
        if sum(ch.isalpha() for ch in text) < MIN_LETTERS:
            rep["empty_or_short"] += 1
            continue
        clean, counts = anonymize(text)
        key = normalize(clean)
        if key in seen:
            rep["duplicates"] += 1
            continue
        seen.add(key)
        if counts:
            rep["rows_changed_by_anonymizer"] += 1
            merge_counts(rep["replaced"], counts)
        lang_form, lang_auto = norm_lang(cell(r, "lang")), guess_lang(clean)
        rec = {"schema": SCHEMA, "id": form_id(clean), "text": clean, "lang": lang_form or lang_auto,
               "lang_form": lang_form, "lang_auto": lang_auto, "district": norm_district(cell(r, "district")),
               "date": parse_date(cell(r, "timestamp")), "source": "google_form", "consent": True,
               "anonymized": counts, "evidence": "real_human_text"}
        for k, v in (("lang_form", lang_form or "—"), ("lang_auto", lang_auto or "—"), ("district", rec["district"] or "—")):
            rep[k][v] = rep[k].get(v, 0) + 1
        if lang_form and lang_auto and lang_form != lang_auto:
            rep["lang_disagree"] += 1
        if needs_review(clean):
            review.append(rec)
        out.append(rec)
    if shuffle_seed:
        random.Random(shuffle_seed).shuffle(out)
    rep["kept"] = len(out)
    rep["for_manual_review"] = len(review)
    rep["replaced"] = dict(sorted(rep["replaced"].items()))
    rep["shuffle_seed"] = shuffle_seed
    rep["note"] = "только числа; исходные телефоны, адреса и имена в отчёт не попадают"
    return out, rep, review


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Google-форма (CSV) → обезличенный JSONL в private/")
    ap.add_argument("csv", type=Path, help="CSV, скачанный из Google-формы (лежит в private/)")
    ap.add_argument("--out", type=Path, help=f"по умолчанию {PRIVATE.name}/form_<дата>.jsonl")
    ap.add_argument("--shuffle-seed", type=int, default=2026, help="0 — не перемешивать")
    ap.add_argument("--allow-outside-private", action="store_true", help="только для синтетических проверок")
    args = ap.parse_args(argv)

    out_path = args.out or PRIVATE / f"form_{date.today().isoformat()}.jsonl"
    check_output_path(out_path, args.allow_outside_private)
    records, report, review = convert(read_csv(args.csv), args.shuffle_seed)
    if not records:
        print("Нет ни одной строки с согласием и текстом. Проверьте файл и столбец согласия.", file=sys.stderr)
        print(json.dumps(report, ensure_ascii=False, indent=1), file=sys.stderr)
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    report["input"] = args.csv.name
    report["output"] = out_path.name
    rep_path = out_path.with_suffix(".report.json")
    rep_path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    rev_path = out_path.with_suffix(".review.txt")
    with open(rev_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# Просмотрите эти строки до разметки: после обезличивания остались подозрительные числа/латиница.\n")
        fh.write("# Если там персональные данные — поправьте текст в JSONL вручную (id не меняйте).\n")
        for rec in review:
            fh.write(f"{rec['id']}\t{rec['text']}\n")
    print(f"готово: {out_path} — {report['kept']} из {report['rows']} строк")
    print(f"  без согласия: {report['no_consent']}, пустые/короткие: {report['empty_or_short']}, повторы: {report['duplicates']}")
    print(f"  обезличено строк: {report['rows_changed_by_anonymizer']} {report['replaced']}")
    print(f"  на ручную проверку: {report['for_manual_review']} → {rev_path.name}")
    print(f"  язык (форма): {report['lang_form']}; расхождений с автоопределением: {report['lang_disagree']}")
    print(f"Дальше: откройте web/labeling/index.html и выберите файл {out_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
