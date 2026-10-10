"""Общие мелочи для разметки: язык текста, нормализация, папка private/ (только stdlib)."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / "private"

KK_LETTERS = set("әғқңөұүһі")
# Русские служебные слова, которых нет в казахском как отдельных слов («не» по-казахски «что» — не берём).
RU_WORDS = {"нет", "уже", "что", "очень", "просим", "когда", "почему", "и", "в", "на", "это", "как", "опять",
            "снова", "или", "но", "у", "с", "по"}
# Частые казахские слова без «особых» букв и отрицание глагола (-байды/-майды/…).
KK_WORDS = {"аулада", "аула", "шам", "жол", "жолда", "жоқ", "бар", "емес", "мен", "бен", "пен", "су", "жылу",
            "сынған", "жанында", "бойында", "қала", "тұрғындар"}
KK_SUFFIX = re.compile(r"(байды|бейді|майды|мейді|пайды|пейді)$")
_WORD = re.compile(r"[a-zа-яёәғқңөұүһі]+")


def guess_lang(text: str) -> str:
    """ru / kk / mixed / '' — та же грубая эвристика, что в web/labeling/core.js (guessLang)."""
    low = text.lower()
    words = _WORD.findall(low)
    kk = any(ch in KK_LETTERS for ch in low) or any(w in KK_WORDS or KK_SUFFIX.search(w) for w in words)
    ru = any(w in RU_WORDS for w in words)
    if kk:
        return "mixed" if ru else "kk"
    if re.search(r"[а-яё]", low):
        return "ru"
    return ""


def normalize(text: str) -> str:
    """Для поиска точных повторов: регистр, ё→е, пунктуация и пробелы не важны."""
    text = unicodedata.normalize("NFC", text).casefold().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def ensure_private_dir(path: Path = PRIVATE) -> Path:
    """Создаёт private/ с собственным .gitignore ('*'): реальные тексты не попадут в Git,
    даже если корневой .gitignore ещё не обновлён (см. R02/INTEGRATION.txt)."""
    path.mkdir(parents=True, exist_ok=True)
    gi = path / ".gitignore"
    if not gi.exists():
        gi.write_text("# Реальные тексты жителей — никогда в Git (R02, раунд 14)\n*\n", encoding="utf-8")
    return path


def is_inside_private(path: Path) -> bool:
    try:
        path.resolve().relative_to(PRIVATE.resolve())
        return True
    except ValueError:
        return False


def check_output_path(path: Path, allow_outside_private: bool) -> None:
    """Файлы с реальными текстами пишем только в private/. Для синтетики есть явный флаг."""
    if is_inside_private(path):
        ensure_private_dir()
        return
    if not allow_outside_private:
        raise SystemExit(
            f"Отказ: {path} вне private/. Реальные тексты жителей пишутся только в private/ "
            "(папка не попадает в Git). Для синтетики добавьте --allow-outside-private.")
