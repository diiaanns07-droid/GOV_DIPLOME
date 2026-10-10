"""Загрузка данных для v2: синтетика R02 (шаблонная v3 и LLM llm_v1) и разметка людей.

Единая запись после загрузки (dict):
  id, text, label (id категории v2), lang (ru|kk|mixed|…), group (шаблон или id — для бутстрэпа и split),
  split (train|val|test|None), source (synth_v3|llm_v1|v1_in_v2|human), evidence (synthetic_template|
  synthetic_llm|real_human_text|…), unsure (сомнение разметчика), style и hard (трудный случай) — если есть.

Форматы на входе (все — JSONL, одна запись на строку; плохие строки пропускаются и считаются):
  * корпуса R02: {"id","text","label" или "category", "lang"/"language", "template_id", "split", "style", "hard"};
    split вне train/val/test (например excluded_near_dup) -> строка пропускается;
  * разметка людей — экспорт web/labeling (schema birge-labels-v1):
    {"id","text","lang","label","unsure","annotator","role",…}; метка 'not_complaint' исключается
    (LABELING_GUIDE_v2 п. 5; опыт «как other» — --not-complaint other). Подходит и CSV с колонками id,text,label.

Реальные тексты людей лежат только в private/ (вне Git). Модуль их не копирует и в отчёты
не пишет — в results/ попадают только числа и id.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from ml.civic_classifier_v2 import labels as L

KAZAKH_LETTERS = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.U)
SPLITS = ("train", "val", "test")


# ---------- чтение файлов ----------

def read_rows(path: Path) -> tuple[list[dict], int]:
    """JSONL/JSON/CSV -> (строки, число пропущенных плохих строк)."""
    raw = Path(path).read_text(encoding="utf-8-sig")
    suffix = Path(path).suffix.lower()
    if suffix in (".csv", ".tsv"):
        try:
            dialect = csv.Sniffer().sniff(raw[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        return list(csv.DictReader(io.StringIO(raw), dialect=dialect)), 0
    if suffix == ".json":
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("records") or data.get("items") or []
        return [r for r in data if isinstance(r, dict)], 0
    rows, bad = [], 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(obj, dict):
            rows.append(obj)
        else:
            bad += 1
    return rows, bad


def corpus_files(path: Path) -> list[Path]:
    """Путь к файлу -> [файл]; к папке -> её JSONL-корпуса.

    В папке R02 рядом с корпусом могут лежать пары перефразов для R04 (pairs*.jsonl) и отчёты —
    их не берём. Если есть corpus*.jsonl — берём только их.
    """
    path = Path(path)
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"нет файла или папки: {path}")
    files = sorted(p for p in path.glob("*.jsonl") if "pair" not in p.name.lower())
    if not files and (path / "data").is_dir():  # R02 кладёт корпус в synth_v3/data/
        return corpus_files(path / "data")
    preferred = [p for p in files if p.name.lower().startswith("corpus")]
    files = preferred or files
    if not files:
        raise FileNotFoundError(f"в {path} нет JSONL-корпуса")
    return files


# ---------- нормализация ----------

def norm_key(text: str) -> str:
    """Ключ для поиска дублей: NFC, регистр, ё->е, без пунктуации, цифры -> 0, пробелы схлопнуты."""
    t = unicodedata.normalize("NFC", str(text)).casefold().replace("ё", "е")
    t = _PUNCT.sub(" ", t)
    t = re.sub(r"\d+", "0", t)
    return _SPACE.sub(" ", t).strip()


def clean_text(text) -> str:
    """Текст для модели: NFC, без управляющих символов, пробелы схлопнуты. Регистр и пунктуация сохраняются."""
    t = unicodedata.normalize("NFC", str(text or ""))
    t = "".join(ch if ch.isprintable() or ch in "\n\t" else " " for ch in t)
    return _SPACE.sub(" ", t).strip()


def guess_lang(text: str) -> str:
    """Грубо: kk — есть казахские буквы; ru — кириллица; latin — транслит; mixed — kk-буквы + много ru-слов.

    Только для срезов в отчёте, если язык не указан в записи.
    """
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return "unknown"
    cyr = sum(1 for ch in letters if "Ѐ" <= ch <= "ӿ")
    if cyr < len(letters) / 2:
        return "latin"
    if any(ch in KAZAKH_LETTERS for ch in text):
        return "kk"
    return "ru"


def _lang(row: dict, text: str) -> str:
    lang = str(row.get("lang") or row.get("language") or "").strip().lower()
    if lang in ("ru", "kk", "mixed", "latin"):
        return lang
    if lang in ("аралас", "смешанный", "mix"):
        return "mixed"
    return guess_lang(text)


def _id(row: dict, text: str, prefix: str) -> str:
    rid = str(row.get("id") or "").strip()
    if rid:
        return rid
    return f"{prefix}-" + hashlib.sha1(norm_key(text).encode("utf-8")).hexdigest()[:12]


# ---------- корпуса ----------

def load_corpus(path: Path, *, source: str, evidence: str, not_complaint: str = "drop") -> tuple[list[dict], dict]:
    """Синтетический корпус R02 -> (записи, отчёт). Метка из 'label' или 'category'."""
    records, report = [], Counter()
    for f in corpus_files(path):
        rows, bad = read_rows(f)
        report["bad_lines"] += bad
        for row in rows:
            text = clean_text(row.get("text"))
            label = L.normalize_label(row.get("label", row.get("category")), not_complaint=not_complaint)
            if not text:
                report["empty_text"] += 1
                continue
            if label is None:
                report["unknown_label"] += 1
                continue
            split = str(row.get("split") or "").strip().lower() or None
            if split in ("dev", "valid", "validation"):
                split = "val"
            if split is not None and split not in SPLITS:
                # R02 помечает почти-дубли val/test как excluded_near_dup: такие строки не берём никуда
                # (иначе ensure_splits назначил бы им новый split и вернул утечку).
                report["excluded_split_" + split] += 1
                continue
            rid = _id(row, text, source)
            records.append({
                "id": rid, "text": text, "label": label, "lang": _lang(row, text),
                "group": str(row.get("template_id") or row.get("group") or rid),
                "split": split, "source": source,
                "evidence": str(row.get("evidence") or evidence),
                "unsure": False, "style": str(row.get("style") or row.get("family") or ""),
                "hard": bool(row.get("hard") or row.get("ambiguous")),
            })
    report["files"] = len(corpus_files(path))
    report["records"] = len(records)
    return records, dict(report)


def load_human(paths: list[Path], *, not_complaint: str = "drop", drop_unsure: bool = False) -> tuple[list[dict], dict]:
    """Разметка людей (web/labeling или CSV). Один id в нескольких файлах -> берётся ПЕРВЫЙ файл
    (первым указывайте разметку владельца), расхождения считаются в отчёте."""
    by_id: dict[str, dict] = {}
    report = Counter()
    for path in paths:
        rows, bad = read_rows(Path(path))
        report["bad_lines"] += bad
        for row in rows:
            text = clean_text(row.get("text"))
            raw_label = row.get("label", row.get("category"))
            if not text:
                report["empty_text"] += 1
                continue
            if str(raw_label or "").strip() == L.NOT_COMPLAINT:
                report["not_complaint"] += 1
            label = L.normalize_label(raw_label, not_complaint=not_complaint)
            if label is None:
                report["skipped_or_unknown_label"] += 1
                continue
            unsure = str(row.get("unsure", "")).strip().lower() in ("true", "1", "yes")
            if unsure and drop_unsure:
                report["dropped_unsure"] += 1
                continue
            rid = _id(row, text, "h")
            if rid in by_id:
                report["duplicate_id"] += 1
                if by_id[rid]["label"] != label:
                    report["duplicate_id_label_conflict"] += 1
                continue
            by_id[rid] = {"id": rid, "text": text, "label": label, "lang": _lang(row, text), "group": rid,
                          "split": None, "source": "human", "evidence": "real_human_text", "unsure": unsure,
                          "style": ""}
    records = list(by_id.values())
    # Точные дубли текста среди людей (один человек отправил дважды) — оставляем первый.
    seen, uniq = set(), []
    for r in records:
        k = norm_key(r["text"])
        if k in seen:
            report["duplicate_text"] += 1
            continue
        seen.add(k)
        uniq.append(r)
    report["records"] = len(uniq)
    return uniq, dict(report)


# ---------- разбиения ----------

def _stable_hash(value: str, seed: int) -> int:
    return int(hashlib.sha1(f"{seed}:{value}".encode("utf-8")).hexdigest()[:12], 16)


def ensure_splits(records: list[dict], seed: int, ratios=(0.7, 0.15, 0.15)) -> dict:
    """Если в корпусе нет поля split — детерминированный split ПО ГРУППАМ (шаблонам): один шаблон
    целиком в train, val или test (иначе val/test почти совпадали бы с train)."""
    missing = [r for r in records if r["split"] is None]
    if not missing:
        return {"assigned": 0}
    for r in missing:
        u = (_stable_hash(r["group"], seed) % 10_000) / 10_000
        r["split"] = "train" if u < ratios[0] else "val" if u < ratios[0] + ratios[1] else "test"
    return {"assigned": len(missing), "rule": f"group hash split {ratios}, seed {seed}"}


def stratified_kfold(records: list[dict], k: int, seed: int) -> list[list[int]]:
    """Индексы k фолдов, стратифицировано по метке; детерминированно (seed)."""
    if k < 2:
        raise ValueError("k >= 2")
    by_label: dict[str, list[int]] = {}
    for i, r in enumerate(records):
        by_label.setdefault(r["label"], []).append(i)
    folds: list[list[int]] = [[] for _ in range(k)]
    rng = random.Random(seed)
    offset = 0
    for lab in sorted(by_label):
        idx = by_label[lab][:]
        rng.shuffle(idx)
        for j, i in enumerate(idx):
            folds[(j + offset) % k].append(i)
        offset += len(idx)  # редкие классы не скапливаются в первом фолде
    return [sorted(f) for f in folds]


def stratified_split(records: list[dict], val_ratio: float, seed: int) -> tuple[list[dict], list[dict]]:
    """train/val внутри обучающей части (для ранней остановки и порога). Класс с 1 примером — в train."""
    by_label: dict[str, list[dict]] = {}
    for r in records:
        by_label.setdefault(r["label"], []).append(r)
    rng = random.Random(seed)
    tr, va = [], []
    for lab in sorted(by_label):
        items = by_label[lab][:]
        rng.shuffle(items)
        n_val = int(round(len(items) * val_ratio))
        if len(items) >= 2:
            n_val = max(1, min(n_val, len(items) - 1))
        else:
            n_val = 0
        va.extend(items[:n_val])
        tr.extend(items[n_val:])
    return tr, va


def drop_leaks(train: list[dict], evaluation: list[dict]) -> tuple[list[dict], int]:
    """Убирает из обучения тексты, совпадающие (после norm_key) с оценочными. Возвращает (train, сколько убрано)."""
    keys = {norm_key(r["text"]) for r in evaluation}
    kept = [r for r in train if norm_key(r["text"]) not in keys]
    return kept, len(train) - len(kept)


def summary(records: list[dict]) -> dict:
    """Счётчики без текстов — можно класть в results/."""
    return {
        "n": len(records),
        "by_label": dict(sorted(Counter(r["label"] for r in records).items())),
        "by_lang": dict(sorted(Counter(r["lang"] for r in records).items())),
        "by_split": dict(sorted(Counter(str(r["split"]) for r in records).items())),
        "by_source": dict(sorted(Counter(r["source"] for r in records).items())),
        "unsure": sum(1 for r in records if r.get("unsure")),
    }


def warn(msg: str) -> None:
    print(f"[civic_classifier_v2] {msg}", file=sys.stderr)
