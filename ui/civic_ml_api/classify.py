"""classify(text) — подсказка категории обращения (CONTRACT §7: POST /api/civic/v2/classify).

Цепочка моделей (prompts/R04.txt п. 1), берётся первая доступная:
  1. «v2»  — модель R03 (ml/civic_classifier_v2, ONNX int8; файлы — после LOCAL-4 на ноутбуке);
  2. «v1+kw» — v1 (ml/civic_classifier, 6 меток -> v2 по v1_to_v2) вместе со словарём 12 категорий R03
     (ml/civic_classifier_v2/heuristic.py, только стандартная библиотека). v1 не знает 6 новых категорий
     (снег, мусор, ЖКХ, запахи, шум, парковки), поэтому решает словарь, если нашёл слова темы,
     иначе — v1. Замер на синтетике R02 (RESULTS.md): v1 одна 0.49, словарь 0.65, вместе 0.69 (val);
  3. «kw»  — только словарь R03 (если файла модели v1 нет);
  4. «v1-heuristic» — словарь v1 (6 меток), если нет и кода R03; иначе «other».
Перед v1 и словарём латиница из чатов переводится в кириллицу (to_cyrillic): транслит 0.07 -> 0.63 (val).

Ответ: {category, score, needs_review, model_version, top3:[{category, score}]} + сверх контракта:
  suggest    — можно заранее выделить чип «Похоже на: …» (житель подтверждает или меняет);
  source     — кто решил: v2 | v1 | kw | v1-heuristic | none;
  score_kind — softmax (v2) | softmax_uncalibrated (v1) | keyword_share (доля совпадений словаря) | none.
needs_review — для сотрудника: подсказку нужно проверить. Пока модели не проверены на текстах людей,
он всегда true (как у v1 и R03). suggest — для жителя: словарь с ≥ 2 совпадениями точен на 94 % (val).

Загрузка ленивая, один раз, под блокировкой; ошибка загрузки запоминается (файл не перечитывается
на каждый запрос). Сеть не используется. Сбой модели во время запроса -> следующий уровень цепочки.
"""

from __future__ import annotations

import logging
import threading

from ml.civic_dedup.normalize import letters, to_cyrillic
from ui.civic_ml_api import categories as C

LOGGER = logging.getLogger(__name__)

MAX_TEXT = 5000
MIN_LETTERS = 3
KW_VERSION = "civic-kw12-r03"
V1_HEURISTIC_VERSION = "civic-clf-heuristic-fallback-v1"
NONE_VERSION = "none"
# Порог «можно выделить чип» для словаря: ≥ 2 совпадения — точность 0.939 при покрытии 29 % (val R02).
SUGGEST_KW_HITS = 2
# После стольких сбоев подряд модель v2 выключается до перезапуска (не тормозить каждый запрос).
V2_MAX_FAILURES = 3


class _Chain:
    """Состояние моделей: name -> ("ok", объект) | ("error", причина)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state: dict[str, tuple[str, object]] = {}
        self._v2_failures = 0

    def _get(self, name, loader):
        item = self._state.get(name)
        if item is None:
            with self._lock:
                item = self._state.get(name)
                if item is None:
                    try:
                        item = ("ok", loader())
                    except Exception as exc:  # нет файла/библиотеки/повреждён — следующий уровень цепочки
                        # Пути сервера в причине — относительно репозитория (status() может уйти наружу).
                        reason = f"{type(exc).__name__}: {exc}".replace(str(C.REPO_ROOT) + "/", "")
                        item = ("error", reason[:300])
                        LOGGER.info("civic_ml_api: %s недоступна (%s)", name, item[1])
                    self._state[name] = item
        return item[1] if item[0] == "ok" else None

    # --- загрузчики -------------------------------------------------------------
    @staticmethod
    def _load_v2():
        from ml.civic_classifier_v2.predict import get_default  # numpy/onnxruntime нужны только здесь
        return get_default()

    @staticmethod
    def _load_v1():
        from ml.civic_classifier.labels import LABELS
        from ml.civic_classifier.model import load_model, predict_scores
        model = load_model()  # проверка формата, меток и sha256 — внутри v1
        mapping = C.v1_to_v2()
        if not set(LABELS) <= set(mapping) or not set(mapping.values()) <= set(C.ids()):
            raise ValueError("v1_to_v2 не покрывает метки v1")
        return {"model": model, "labels": LABELS, "predict": predict_scores, "map": mapping,
                "version": model["version"], "training_data_status": model.get("training_data_status")}

    @staticmethod
    def _load_kw():
        from ml.civic_classifier_v2 import heuristic
        if set(heuristic.PRIORITY) != set(C.ids()):
            raise ValueError("словарь R03 не совпадает с categories_v2.json")
        return heuristic

    @staticmethod
    def _load_v1_heuristic():
        from ml.civic_classifier import heuristic
        return heuristic

    def v2(self):
        return self._get("v2", self._load_v2)

    def v1(self):
        return self._get("v1", self._load_v1)

    def kw(self):
        return self._get("kw", self._load_kw)

    def v1_heuristic(self):
        return self._get("v1_heuristic", self._load_v1_heuristic)

    def v2_failed(self, exc: Exception) -> None:
        LOGGER.warning("civic_ml_api: модель v2 упала на запросе (%s: %s)", type(exc).__name__, exc)
        with self._lock:
            self._v2_failures += 1
            if self._v2_failures >= V2_MAX_FAILURES:
                self._state["v2"] = ("error", f"выключена после {V2_MAX_FAILURES} сбоев подряд: {exc}"[:300])

    def v2_ok(self) -> None:
        self._v2_failures = 0

    def status(self) -> dict:
        self.v2(), self.v1(), self.kw(), self.v1_heuristic()
        return {name: ("ready" if item[0] == "ok" else "unavailable: " + str(item[1]))
                for name, item in sorted(self._state.items())}

    def version(self) -> str:
        """Версия цепочки, которая сейчас отвечает (одна на конфигурацию, не на текст)."""
        v2 = self.v2()
        return v2.model_version if v2 is not None else self.fallback_version()

    def fallback_version(self) -> str:
        """Версия цепочки без v2 (её ответ, если v2 нет или упала на запросе)."""
        v1, kw = self.v1(), self.kw()
        if v1 is not None and kw is not None:
            return f"{v1['version']}+{KW_VERSION}"
        if v1 is not None:
            return v1["version"]
        if kw is not None:
            return KW_VERSION
        return V1_HEURISTIC_VERSION if self.v1_heuristic() is not None else NONE_VERSION


CHAIN = _Chain()


def _round(x) -> float:
    return round(float(x), 4)


def _empty(version: str) -> dict:
    return {"category": C.OTHER, "score": 0.0, "needs_review": True, "model_version": version, "top3": [],
            "suggest": False, "source": "none", "score_kind": "none"}


def _from_v2(v2, text: str) -> dict:
    res = v2.classify(text)
    out = {
        "category": res["category"], "score": _round(res.get("score") or 0.0),
        "needs_review": bool(res.get("needs_review", True)), "model_version": res.get("model_version") or v2.model_version,
        "top3": [{"category": t["category"], "score": _round(t["score"])} for t in (res.get("top3") or [])][:3],
    }
    # Порог R03 подобран на validation; для чипа жителя он и есть «уверенно».
    out["suggest"] = bool(out["category"] != C.OTHER and out["score"] >= float(getattr(v2, "threshold", 1.0)))
    out["source"], out["score_kind"] = "v2", "softmax"
    if out["category"] not in C.ids():
        raise ValueError(f"модель v2 вернула неизвестную категорию {out['category']!r}")
    return out


def _kw_result(hits: dict, order: tuple) -> tuple[str, float, list, int]:
    """(категория, доля совпадений, top3, число совпадений лучшей) по словарю."""
    total = sum(hits.values())
    ranked = sorted((lab for lab in order if hits.get(lab)), key=lambda lab: (-hits[lab], order.index(lab)))
    if not ranked:
        return C.OTHER, 0.0, [], 0
    top3 = [{"category": lab, "score": _round(hits[lab] / total)} for lab in ranked[:3]]
    return ranked[0], top3[0]["score"], top3, hits[ranked[0]]


def _v1_probs(v1, text: str) -> dict[str, float]:
    probs = v1["predict"](text, v1["model"])
    out: dict[str, float] = {}
    for lab, p in zip(v1["labels"], probs):
        cat = v1["map"][lab]
        out[cat] = out.get(cat, 0.0) + float(p)
    return out


def classify(text) -> dict:
    """Подсказка категории. text — строка (шлюз R01 уже проверил: непустая, ≤ 5000 символов)."""
    if not isinstance(text, str):
        raise ValueError("text: нужна строка с текстом обращения.")
    text = text.strip()[:MAX_TEXT]
    version = CHAIN.version()
    if letters(text) < MIN_LETTERS:
        return _empty(version)  # «...», «123», пусто: модель не применяем

    v2 = CHAIN.v2()
    if v2 is not None:
        try:
            out = _from_v2(v2, text)
            CHAIN.v2_ok()
            return out
        except Exception as exc:
            CHAIN.v2_failed(exc)
        version = CHAIN.fallback_version()

    cyr = to_cyrillic(text)
    kw, v1 = CHAIN.kw(), CHAIN.v1()
    if kw is not None:
        cat, score, top3, best = _kw_result(kw.keyword_hits(cyr), tuple(kw.PRIORITY))
        if best >= 1 or v1 is None:
            return {"category": cat, "score": score, "needs_review": True, "model_version": version, "top3": top3,
                    "suggest": best >= SUGGEST_KW_HITS, "source": "kw",
                    "score_kind": "keyword_share" if best else "none"}
    if v1 is not None:
        try:
            probs = _v1_probs(v1, cyr)
            ranked = sorted(probs, key=lambda c: (-probs[c], C.ids().index(c)))
            return {"category": ranked[0], "score": _round(probs[ranked[0]]), "needs_review": True,
                    "model_version": version,
                    "top3": [{"category": c, "score": _round(probs[c])} for c in ranked[:3]],
                    "suggest": False, "source": "v1", "score_kind": "softmax_uncalibrated"}
        except Exception as exc:  # повреждённая модель v1 не должна ронять ответ
            LOGGER.warning("civic_ml_api: v1 упала на запросе (%s)", exc)
    h1 = CHAIN.v1_heuristic()
    if h1 is not None:
        label, hits = h1.heuristic_label(cyr)
        cat = C.v1_to_v2().get(label, C.OTHER)
        return {"category": cat, "score": 0.0, "needs_review": True, "model_version": V1_HEURISTIC_VERSION,
                "top3": [{"category": cat, "score": 0.0}] if hits else [], "suggest": False,
                "source": "v1-heuristic", "score_kind": "none"}
    return _empty(NONE_VERSION)
