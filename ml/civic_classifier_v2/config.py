"""Настройки обучения трансформера v2 и пути по умолчанию.

Значения подобраны под RTX 4060 Laptop (8 ГБ): xlm-roberta-base, длина 128 токенов, fp16,
batch 16 × накопление 2 = эффективный batch 32. Пиковая память GPU при этом ≈ 4–5 ГБ
(оценка; фактическое значение train.py пишет в лог: torch.cuda.max_memory_allocated).
Если не хватает памяти — уменьшить batch_size до 8 и поставить grad_accum 4: эффективный batch тот же.

Все поля можно переопределить из командной строки train.py / experiments.py (--set key=value).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parents[1]
# Большие файлы (веса, ONNX, кэш LLM) — только здесь; папка в .gitignore (INTEGRATION.txt для R01).
ARTIFACTS_DIR = PKG_DIR / "artifacts"
# Метрики и таблицы (маленькие JSON/Markdown) — в Git.
RESULTS_DIR = PKG_DIR / "results"
# Реальные тексты людей лежат только здесь (папка вне Git, см. ml/labeling/import_form.py у R02).
PRIVATE_DIR = REPO_ROOT / "private"

# Корпуса R02 (раунд 14). Точные имена файлов — в ml/datasets/README.md у R02; data.py ищет
# JSONL в этих папках, если путь не задан явно.
SYNTH_V3_DIR = REPO_ROOT / "ml" / "datasets" / "synth_v3"
LLM_V1_DIR = REPO_ROOT / "ml" / "datasets" / "llm_v1"

DEFAULT_SEED = 20261011


@dataclass
class TrainConfig:
    model_name: str = "xlm-roberta-base"   # имя на HuggingFace или путь к локальной папке модели
    max_length: int = 128                  # токенов; длиннее — обрезается (жалобы обычно < 80 токенов)
    batch_size: int = 16
    grad_accum: int = 2                    # эффективный batch = batch_size * grad_accum
    eval_batch_size: int = 64
    lr: float = 2e-5
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    epochs: int = 8                        # максимум; обычно останавливается раньше
    patience: int = 2                      # ранняя остановка: столько эпох без роста val macro-F1
    min_delta: float = 0.001               # «рост» = больше чем на min_delta
    fp16: bool = True                      # только на CUDA; на CPU игнорируется
    class_weight: str = "sqrt_inv"         # none | inv | sqrt_inv — вес класса в CrossEntropy
    label_smoothing: float = 0.0
    max_grad_norm: float = 1.0
    seed: int = DEFAULT_SEED
    num_workers: int = 0                   # 0 — надёжно на Windows
    # Политика needs_review (порог подбирается на validation, не на тесте).
    review_target_precision: float = 0.90
    extra: dict = field(default_factory=dict)  # свободные пометки (не влияют на обучение)

    @property
    def effective_batch(self) -> int:
        return self.batch_size * self.grad_accum

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TrainConfig":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def override(self, pairs: list[str] | None) -> "TrainConfig":
        """--set key=value (значение разбирается как JSON, иначе строка): --set lr=3e-5 --set fp16=false."""
        data = self.to_dict()
        types = {f.name: f.type for f in fields(self)}
        for pair in pairs or []:
            if "=" not in pair:
                raise ValueError(f"--set ожидает key=value, получено {pair!r}")
            key, raw = pair.split("=", 1)
            key = key.strip()
            if key not in types:
                raise ValueError(f"неизвестный параметр {key!r}; есть: {', '.join(sorted(types))}")
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                value = raw
            data[key] = value
        return TrainConfig.from_dict(data)


# Быстрый режим для проверки конвейера (облако/CPU, крошечная модель): не для результатов.
SMOKE_OVERRIDES = {"epochs": 2, "batch_size": 8, "grad_accum": 1, "eval_batch_size": 16, "patience": 1,
                   "fp16": False, "max_length": 48, "lr": 1e-3}
