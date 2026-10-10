"""Базовая модель №2 — «v1 логрегрессия», переобучаемая на 12 категориях v2 в каждом режиме эксперимента.

Признаки — те же, что у v1 (ml/civic_classifier/text.py, ветка claude/wizardly-ptolemy-qy8ltw @ 14c3384):
символьные 2–5-граммы внутри слов (с границами) + префиксы слов из 5 букв, log1p и L2-нормировка,
плюс (как у выбранной модели v1 «logreg+словарь») совпадения словаря эвристики по категориям.
Код v1 не импортируется и не меняется: в v1 список из 6 меток зашит в модуль, поэтому функция признаков
повторена здесь. Оптимизатор — sklearn LogisticRegression (lbfgs) вместо самописного SGD v1: на корпусах
в 10+ тысяч текстов чистый Python слишком медленный. Отбор C / class_weight / словаря — только по validation.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np

from ml.civic_classifier_v2 import heuristic
from ml.civic_classifier_v2 import labels as L
from ml.civic_classifier_v2.metrics import macro_f1_cm

_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+?[78][\s\-()]*)?(?:\d[\s\-()]*){10}(?!\d)")
_LONG_NUM = re.compile(r"\b\d{9,}\b")
_NON_WORD = re.compile(r"[^\w\s]", re.U)
_DIGITS = re.compile(r"\d+")
_SPACE = re.compile(r"\s+")

CHAR_NGRAMS = (2, 5)
WORD_PREFIX = 5
MIN_DF = 2
# Сетка отбора (по validation). Признаки словаря включены всегда: в облачном прогоне 10.10 на корпусах R02
# вариант без словаря был хуже при каждом C и class_weight (v3: 0.674 против 0.728 на val; v1→v2: 0.623 против
# 0.759) — так же, как у v1 в раунде 12. Убрали его, чтобы k-fold на ноутбуке шёл вдвое быстрее.
GRID = [{"C": c, "class_weight": cw, "keyword_scale": 1.0} for c in (1.0, 4.0, 16.0, 64.0) for cw in (None, "balanced")]


def v1_normalize(text: str) -> str:
    """Как v1 normalize(): NFC, маркеры вместо телефонов/почты/ссылок, регистр, ё->е, без пунктуации, цифры->0."""
    t = unicodedata.normalize("NFC", str(text))
    t = _URL.sub(" url ", t)
    t = _EMAIL.sub(" email ", t)
    t = _LONG_NUM.sub(" id ", t)
    t = _PHONE.sub(" phone ", t)
    t = t.casefold().replace("ё", "е")
    t = _NON_WORD.sub(" ", t)
    t = _DIGITS.sub("0", t)
    return _SPACE.sub(" ", t).strip()


def v1_features(text: str) -> dict[str, float]:
    """Счётчики: 'c:'+n-грамма внутри слова с пробелами по краям, 'w:'+префикс слова (≥ 3 букв)."""
    feats: dict[str, float] = {}
    lo, hi = CHAR_NGRAMS
    for word in v1_normalize(text).split():
        padded = f" {word} "
        for n in range(lo, hi + 1):
            for i in range(len(padded) - n + 1):
                g = "c:" + padded[i:i + n]
                feats[g] = feats.get(g, 0.0) + 1.0
        if len(word) >= 3:
            w = "w:" + word[:WORD_PREFIX]
            feats[w] = feats.get(w, 0.0) + 1.0
    return feats


@dataclass
class LogRegModel:
    labels: tuple[str, ...]
    vocab: dict[str, int]
    keyword_scale: float
    clf: object
    hyper: dict = field(default_factory=dict)

    def _matrix(self, texts: list[str]):
        from scipy.sparse import csr_matrix
        k_off = len(self.vocab)
        n_kw = len(self.labels) + 1 if self.keyword_scale else 0
        rows, cols, vals = [], [], []
        for r, t in enumerate(texts):
            vec = {self.vocab[f]: math.log1p(v) for f, v in v1_features(t).items() if f in self.vocab}
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            for c, v in vec.items():
                rows.append(r)
                cols.append(c)
                vals.append(v / norm)
            if n_kw:
                hits = heuristic.keyword_hits(t)
                any_hit = False
                for j, lab in enumerate(self.labels):
                    h = hits.get(lab, 0)
                    if h:
                        any_hit = True
                        rows.append(r)
                        cols.append(k_off + j)
                        vals.append(min(h, 3) * self.keyword_scale)
                if not any_hit:  # отдельный признак «словарь молчит»
                    rows.append(r)
                    cols.append(k_off + len(self.labels))
                    vals.append(self.keyword_scale)
        return csr_matrix((vals, (rows, cols)), shape=(len(texts), k_off + n_kw), dtype=np.float64)

    def predict_proba(self, texts: list[str]) -> np.ndarray:
        """Вероятности по всем 12 меткам (классы, которых не было в обучении, получают 0)."""
        proba = self.clf.predict_proba(self._matrix(texts))
        out = np.zeros((len(texts), len(self.labels)))
        for j, cls in enumerate(self.clf.classes_):
            out[:, int(cls)] = proba[:, j]
        return out

    def predict(self, texts: list[str]) -> list[int]:
        return [int(i) for i in self.predict_proba(texts).argmax(axis=1)]


def build_vocab(texts: list[str]) -> dict[str, int]:
    df: dict[str, int] = {}
    for t in texts:
        for f in v1_features(t):
            df[f] = df.get(f, 0) + 1
    return {f: i for i, f in enumerate(sorted(f for f, n in df.items() if n >= MIN_DF))}


def fit(train: list[dict], val: list[dict], seed: int, grid: list[dict] | None = None,
        labels: tuple[str, ...] | None = None) -> tuple[LogRegModel, dict]:
    """Перебор сетки, выбор по macro-F1 на val. Возвращает (лучшая модель, журнал отбора)."""
    from sklearn.linear_model import LogisticRegression

    labels = labels or L.labels()
    index = {lab: i for i, lab in enumerate(labels)}
    texts_tr = [r["text"] for r in train]
    y_tr = np.array([index[r["label"]] for r in train])
    y_va = np.array([index[r["label"]] for r in val])
    vocab = build_vocab(texts_tr)
    log, best = [], None
    for hyper in grid or GRID:
        model = LogRegModel(labels, vocab, hyper["keyword_scale"], None, dict(hyper))
        X = model._matrix(texts_tr)
        clf = LogisticRegression(C=hyper["C"], class_weight=hyper["class_weight"], max_iter=2000,
                                 random_state=seed)
        clf.fit(X, y_tr)
        model.clf = clf
        if len(val):
            pred = np.array(model.predict([r["text"] for r in val]))
            k = len(labels)
            cm = np.bincount(y_va * k + pred, minlength=k * k).reshape(k, k)
            score = macro_f1_cm(cm)
        else:
            score = 0.0
        log.append({"hyper": hyper, "val_macro_f1": round(score, 4)})
        if best is None or score > best[0] + 1e-9:
            best = (score, model)
    chosen = best[1]
    return chosen, {"metric": "validation macro-F1", "vocab_size": len(vocab), "chosen": chosen.hyper,
                    "candidates": log}
