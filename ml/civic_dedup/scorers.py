"""Оценщики сходства двух текстов обращений: encode(text) -> признаки, score(a, b) -> число 0..1.

NgramConceptScorer — запасной путь, работает всегда (только стандартная библиотека):
    score = alpha · cos(n-граммы) + (1 − alpha) · cos(понятия), если понятия есть в ОБОИХ текстах;
    score = cos(n-граммы), если хотя бы в одном тексте понятий нет (словарь не знает этих слов).
    n-граммы — символьные 3–5-граммы внутри слов (с границами слова), вес 1 + ln(tf), L2-нормировка.
    Понятия — concepts.py (яма = шұңқыр, навес = шатыр …): дают совпадение русского и казахского текста.

E5Scorer (ml/civic_dedup/e5.py) — основной путь, если на ноутбуке выполнена LOCAL-задача с весами
multilingual-e5: косинус эмбеддингов, по желанию с той же добавкой понятий.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ml.civic_dedup.concepts import concepts
from ml.civic_dedup.normalize import normalize


def _ngram_vector(norm_text: str, lo: int, hi: int) -> dict[str, float]:
    counts: dict[str, int] = {}
    for word in norm_text.split():
        padded = f" {word} "
        for n in range(lo, hi + 1):
            for i in range(len(padded) - n + 1):
                g = padded[i:i + n]
                counts[g] = counts.get(g, 0) + 1
    vec = {g: 1.0 + math.log(c) for g, c in counts.items()}
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {g: v / norm for g, v in vec.items()}


def sparse_cosine(a: dict[str, float], b: dict[str, float]) -> float:
    """Скалярное произведение L2-нормированных разреженных векторов (= косинус)."""
    if len(a) > len(b):
        a, b = b, a
    get = b.get
    return sum(v * get(k, 0.0) for k, v in a.items())


def concept_cosine(a: frozenset, b: frozenset) -> float | None:
    """Косинус множеств понятий; None, если в одном из текстов понятий нет."""
    if not a or not b:
        return None
    return len(a & b) / math.sqrt(len(a) * len(b))


@dataclass(frozen=True)
class NgramFeatures:
    ngrams: dict
    concepts: frozenset


class NgramConceptScorer:
    method = "ngram-concept-v1"

    def __init__(self, alpha: float = 0.5, ngram_range: tuple[int, int] = (3, 5)):
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("alpha must be in [0, 1]")
        self.alpha = float(alpha)
        self.ngram_range = (int(ngram_range[0]), int(ngram_range[1]))

    @property
    def version(self) -> str:
        lo, hi = self.ngram_range
        return f"{self.method}-a{self.alpha:g}-n{lo}{hi}"

    def encode(self, text: str) -> NgramFeatures:
        norm = normalize(text)
        return NgramFeatures(_ngram_vector(norm, *self.ngram_range), concepts(norm))

    def encode_many(self, texts: list[str]) -> list[NgramFeatures]:
        return [self.encode(t) for t in texts]

    def score(self, a: NgramFeatures, b: NgramFeatures) -> float:
        ng = sparse_cosine(a.ngrams, b.ngrams)
        cc = concept_cosine(a.concepts, b.concepts)
        s = ng if cc is None else self.alpha * ng + (1.0 - self.alpha) * cc
        return max(0.0, min(1.0, s))
