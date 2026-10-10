"""Выбор оценщика и ленивая однократная загрузка (потокобезопасно, без сети).

Порядок (dedup_config.json -> prefer): e5-onnx, если есть файлы модели, библиотеки и подобранный
порог; иначе ngram-concept-v1 (стандартная библиотека). Почему e5 не загрузился — в deduper_info().
"""

from __future__ import annotations

import logging
import threading

from ml.civic_dedup import config as C
from ml.civic_dedup.scorers import NgramConceptScorer
from ml.civic_dedup.search import Deduper

LOGGER = logging.getLogger(__name__)
_lock = threading.Lock()
_state: dict = {}


def _build(conf: dict) -> tuple[Deduper, list[str]]:
    notes = []
    radius = float(conf.get("radius_m") or 200)
    for method in conf.get("prefer") or [C.FALLBACK_METHOD]:
        mconf = conf["methods"].get(method) or {}
        thr = mconf.get("threshold")
        if method == "e5-onnx":
            if thr is None:
                notes.append("e5-onnx: порог не подобран (запустите tune.py после LOCAL-экспорта)")
                continue
            try:
                from ml.civic_dedup.e5 import E5Scorer, E5Unavailable
            except ImportError as exc:  # numpy не установлен
                notes.append(f"e5-onnx: {exc}")
                continue
            try:
                scorer = E5Scorer.load(C.E5_DIR, alpha=float(mconf.get("alpha", 1.0)))
            except E5Unavailable as exc:
                notes.append(f"e5-onnx: {exc}")
                continue
            return Deduper(scorer, float(thr), radius_m=radius), notes
        if method == C.FALLBACK_METHOD:
            lo, hi = (mconf.get("ngram_range") or [3, 5])[:2]
            scorer = NgramConceptScorer(alpha=float(mconf.get("alpha", 0.5)), ngram_range=(int(lo), int(hi)))
            return Deduper(scorer, float(thr if thr is not None else 0.31), radius_m=radius), notes
        notes.append(f"{method}: неизвестный метод")
    # prefer испорчен — запасной путь всё равно работает.
    d = C.DEFAULTS["methods"][C.FALLBACK_METHOD]
    return Deduper(NgramConceptScorer(d["alpha"], tuple(d["ngram_range"])), d["threshold"], radius_m=radius), notes


def get_deduper() -> Deduper:
    dd = _state.get("deduper")
    if dd is not None:
        return dd
    with _lock:
        if "deduper" not in _state:
            conf = C.load_config()
            dd, notes = _build(conf)
            _state.update(deduper=dd, notes=notes, config=conf)
            for note in notes:
                LOGGER.info("civic_dedup: %s", note)
        return _state["deduper"]


def deduper_info() -> dict:
    dd = get_deduper()
    return {"method": dd.scorer.method, "version": dd.version, "threshold": dd.threshold,
            "radius_m": dd.radius_m, "default_days": int(_state["config"].get("default_days") or 14),
            "notes": list(_state.get("notes") or [])}


def reset() -> None:
    """Для тестов и после LOCAL-экспорта: следующая get_deduper() перечитает конфиг и файлы."""
    with _lock:
        _state.clear()
