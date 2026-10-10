"""E5Scorer — сходство по эмбеддингам intfloat/multilingual-e5 в ONNX (CPU, без сети).

Файлы (LOCAL-задача, export_e5.py на ноутбуке владельца) — в ml/civic_dedup/artifacts/e5/:
    model.int8.onnx (или model.onnx)  — выход "embedding" (уже усреднён и нормирован)
                                         или "last_hidden_state" (усредняем здесь по attention_mask);
    tokenizer.json                    — быстрый токенизатор (библиотека tokenizers);
    e5_meta.json                      — модель, ревизия, префикс, max_length, проверка совпадения с PyTorch.
Нужны numpy, onnxruntime, tokenizers (они же нужны модели v2 R03). Нет чего-то — E5Unavailable,
и loader берёт запасной путь n-грамм.

Префикс "query: " для обоих текстов — так рекомендует карточка e5 для симметричных задач
(сходство двух фраз). alpha < 1 смешивает косинус e5 с косинусом понятий concepts.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ml.civic_dedup.concepts import concepts
from ml.civic_dedup.normalize import normalize
from ml.civic_dedup.scorers import concept_cosine

META_NAME = "e5_meta.json"
DEFAULT_PREFIX = "query: "
DEFAULT_MAX_LENGTH = 128
MAX_TEXT = 2000


class E5Unavailable(RuntimeError):
    """Нет файлов модели или библиотек — используем запасной путь."""


@dataclass(frozen=True)
class E5Features:
    vector: np.ndarray        # L2-нормированный эмбеддинг
    concepts: frozenset


def mean_pool(hidden: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Среднее по токенам с учётом маски + L2-нормировка (как в карточке e5)."""
    m = mask.astype(np.float32)[..., None]
    summed = (hidden.astype(np.float32) * m).sum(axis=1)
    counts = np.clip(m.sum(axis=1), 1e-9, None)
    return l2_normalize(summed / counts)


def l2_normalize(x: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(x, axis=-1, keepdims=True)
    return x / np.clip(norms, 1e-12, None)


class E5Scorer:
    method = "e5-onnx"

    def __init__(self, session, tokenizer, *, meta: dict | None = None, alpha: float = 1.0):
        """session — onnxruntime.InferenceSession (или подставной объект с run/get_inputs/get_outputs);
        tokenizer — tokenizers.Tokenizer (encode_batch -> объекты с ids и attention_mask)."""
        if not 0.0 <= alpha <= 1.0:
            raise ValueError("alpha must be in [0, 1]")
        self.session = session
        self.tokenizer = tokenizer
        self.meta = dict(meta or {})
        self.alpha = float(alpha)
        self.prefix = self.meta.get("prefix", DEFAULT_PREFIX)
        self.max_length = int(self.meta.get("max_length", DEFAULT_MAX_LENGTH))
        self.pad_id = int(self.meta.get("pad_id", 1))
        self.input_names = {i.name for i in session.get_inputs()}
        outputs = [o.name for o in session.get_outputs()]
        self.output = "embedding" if "embedding" in outputs else outputs[0]

    @property
    def version(self) -> str:
        name = str(self.meta.get("model_id", "multilingual-e5")).split("/")[-1]
        rev = str(self.meta.get("revision", ""))[:7]
        quant = self.meta.get("quantization", "")
        base = f"{self.method}-{name}" + (f"@{rev}" if rev else "") + (f"-{quant}" if quant else "")
        return base if self.alpha >= 1.0 else f"{base}-a{self.alpha:g}"

    @classmethod
    def load(cls, model_dir: Path, *, alpha: float = 1.0, threads: int | None = None,
             onnx_name: str | None = None) -> "E5Scorer":
        """onnx_name — конкретный файл (проверка fp32 против int8); по умолчанию int8, затем fp32."""
        model_dir = Path(model_dir)
        meta_path = model_dir / META_NAME
        if not meta_path.exists():
            raise E5Unavailable(f"нет {META_NAME} в {model_dir.name}/ (LOCAL-задача export_e5.py)")
        names = (onnx_name,) if onnx_name else ("model.int8.onnx", "model.onnx")
        onnx_file = next((model_dir / n for n in names if (model_dir / n).exists()), None)
        if onnx_file is None:
            raise E5Unavailable(f"нет {' / '.join(names)} в {model_dir.name}/")
        if not (model_dir / "tokenizer.json").exists():
            raise E5Unavailable(f"нет tokenizer.json в {model_dir.name}/")
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise E5Unavailable(f"не установлена библиотека: {exc.name}") from exc
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            so = ort.SessionOptions()
            if threads:
                so.intra_op_num_threads = threads
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            session = ort.InferenceSession(str(onnx_file), so, providers=["CPUExecutionProvider"])
            tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        except Exception as exc:  # повреждённый файл не должен ронять сервер
            raise E5Unavailable(f"модель не загрузилась: {type(exc).__name__}: {exc}") from exc
        max_len = int(meta.get("max_length", DEFAULT_MAX_LENGTH))
        tok.enable_truncation(max_length=max_len)
        tok.no_padding()
        meta["file"] = onnx_file.name
        return cls(session, tok, meta=meta, alpha=alpha)

    # ------------------------------------------------------------------ эмбеддинги
    def _feed(self, texts: list[str]) -> tuple[dict, np.ndarray]:
        encs = self.tokenizer.encode_batch([self.prefix + str(t)[:MAX_TEXT] for t in texts])
        width = max(1, max(len(e.ids) for e in encs))
        ids = np.full((len(texts), width), self.pad_id, dtype=np.int64)
        mask = np.zeros((len(texts), width), dtype=np.int64)
        for i, e in enumerate(encs):
            n = len(e.ids)
            ids[i, :n] = e.ids
            mask[i, :n] = 1
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.input_names:
            feed["token_type_ids"] = np.zeros_like(ids)
        return {k: v for k, v in feed.items() if k in self.input_names}, mask

    def embed(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        if not texts:
            return np.zeros((0, int(self.meta.get("dim", 768))), dtype=np.float32)
        chunks = []
        for i in range(0, len(texts), batch_size):
            feed, mask = self._feed(texts[i:i + batch_size])
            out = self.session.run([self.output], feed)[0]
            chunks.append(l2_normalize(out.astype(np.float32)) if out.ndim == 2 else mean_pool(out, mask))
        return np.concatenate(chunks, axis=0)

    def encode(self, text: str) -> E5Features:
        return self.encode_many([text])[0]

    def encode_many(self, texts: list[str]) -> list[E5Features]:
        vecs = self.embed(list(texts))
        return [E5Features(vecs[i], concepts(normalize(t))) for i, t in enumerate(texts)]

    def score(self, a: E5Features, b: E5Features) -> float:
        cos = float(np.dot(a.vector, b.vector))
        if self.alpha < 1.0:
            cc = concept_cosine(a.concepts, b.concepts)
            if cc is not None:
                cos = self.alpha * cos + (1.0 - self.alpha) * cc
        return max(0.0, min(1.0, cos))
