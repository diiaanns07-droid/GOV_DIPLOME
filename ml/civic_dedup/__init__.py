"""Birge · поиск похожих обращений («Я тоже»), R04 раунд 14.

    from ml.civic_dedup import get_deduper
    dd = get_deduper()                         # e5 (если LOCAL-веса есть и порог подобран) или n-граммы
    dd.find("Не убран снег на остановке", records, point=[71.43, 51.12], days=14)
    # -> [Match(complaint_id="c-…", score=0.62, target={…}, metoo=6, …)]

Модули:
  normalize — нижний регистр, латиница -> кириллица, казахские буквы -> русские двойники;
  concepts  — двуязычный словарь понятий проблем (яма = шұңқыр);
  scorers   — NgramConceptScorer (стандартная библиотека, работает всегда);
  e5        — E5Scorer: multilingual-e5 в ONNX (onnxruntime + tokenizers + numpy, веса — LOCAL);
  search    — Deduper: фильтры места/времени/статуса + порог + кэш признаков;
  config    — dedup_config.json: пороги, подобранные tune.py на парах R02 (dev);
  tune      — подбор порога и отчёт precision/recall на test;  bench — замер скорости;
  export_e5 — LOCAL: экспорт multilingual-e5 в ONNX int8 на ноутбуке владельца.
Импорт пакета не требует numpy/onnxruntime и не обращается к сети.
"""

from ml.civic_dedup.loader import deduper_info, get_deduper, reset
from ml.civic_dedup.search import DEFAULT_DAYS, DEFAULT_RADIUS_M, OPEN_STATUSES, Deduper, Match

__all__ = ["DEFAULT_DAYS", "DEFAULT_RADIUS_M", "OPEN_STATUSES", "Deduper", "Match", "deduper_info",
           "get_deduper", "reset"]
