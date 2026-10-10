"""Обучение и применение трансформера (по умолчанию xlm-roberta-base) — простой цикл PyTorch без Trainer.

Почему без transformers.Trainer: меньше зависимость от версии библиотеки, явные взвешенные классы,
ранняя остановка по macro-F1 на validation и понятный лог — следующему разработчику проще читать.

Главные функции:
  fit(train, val, cfg, labels, log_path) -> TrainedModel   (лучшая эпоха по val macro-F1 уже загружена)
  predict_proba(model, texts) -> np.ndarray [n, 12]
  save(model, out_dir, meta) / load(out_dir)
Тест-набор сюда не передаётся никогда: выбор эпохи и порога — только по val.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ml.civic_classifier_v2.config import TrainConfig
from ml.civic_classifier_v2.metrics import choose_threshold, macro_f1_cm

META_NAME = "birge_meta.json"
META_FORMAT = "birge-civic-clf-v2"


def _torch():
    import torch  # импорт внутри: модуль data/metrics/эвристика работают и без torch
    return torch


def set_seed(seed: int) -> None:
    torch = _torch()
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def device_info() -> dict:
    torch = _torch()
    info = {"torch": torch.__version__, "cuda": bool(torch.cuda.is_available())}
    if info["cuda"]:
        info["gpu"] = torch.cuda.get_device_name(0)
        info["gpu_total_gb"] = round(torch.cuda.get_device_properties(0).total_memory / 2 ** 30, 2)
        info["cuda_version"] = torch.version.cuda
    try:
        import transformers
        info["transformers"] = transformers.__version__
    except ImportError:
        pass
    return info


def class_weights(y: list[int], k: int, mode: str) -> list[float]:
    """Веса классов для CrossEntropy. sqrt_inv — мягче, чем inv: редкие классы важнее, но без перекоса.
    Класс без примеров получает вес 0 (в функции потерь не встречается). Среднее по присутствующим = 1."""
    counts = np.bincount(np.asarray(y, dtype=int), minlength=k).astype(float)
    if mode == "none":
        w = np.where(counts > 0, 1.0, 0.0)
    else:
        n, present = counts.sum(), max(1, int((counts > 0).sum()))
        base = np.divide(n, present * counts, out=np.zeros(k), where=counts > 0)
        w = np.sqrt(base) if mode == "sqrt_inv" else base
    mean = w[counts > 0].mean() if (counts > 0).any() else 1.0
    return [round(float(v / mean), 4) for v in w]


def data_fingerprint(records: list[dict]) -> str:
    """sha256 обучающих данных (id, метка, текст) — для версии модели; сами тексты не сохраняются."""
    h = hashlib.sha256()
    for r in sorted(records, key=lambda r: r["id"]):
        h.update(f"{r['id']}\t{r['label']}\t{r['text']}\n".encode("utf-8"))
    return h.hexdigest()


@dataclass
class TrainedModel:
    model: object
    tokenizer: object
    labels: tuple[str, ...]
    cfg: TrainConfig
    device: str
    history: list = field(default_factory=list)
    best_epoch: int = 0
    best_val_macro_f1: float = 0.0
    threshold: dict = field(default_factory=dict)
    info: dict = field(default_factory=dict)


def _batches(n: int, size: int, shuffle: bool, gen) -> list[list[int]]:
    order = list(range(n))
    if shuffle:
        gen.shuffle(order)
    return [order[i:i + size] for i in range(0, n, size)]


def _encode(tokenizer, texts: list[str], max_length: int, device: str):
    enc = tokenizer(texts, padding=True, truncation=True, max_length=max_length, return_tensors="pt")
    return {k: v.to(device) for k, v in enc.items() if k in ("input_ids", "attention_mask")}


def predict_proba(tm: TrainedModel, texts: list[str], batch_size: int | None = None) -> np.ndarray:
    """Вероятности softmax [n, K]. Пустой список -> массив формы (0, K)."""
    torch = _torch()
    k = len(tm.labels)
    if not texts:
        return np.zeros((0, k))
    bs = batch_size or tm.cfg.eval_batch_size
    tm.model.eval()
    out = []
    use_amp = tm.device == "cuda" and tm.cfg.fp16
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            enc = _encode(tm.tokenizer, texts[i:i + bs], tm.cfg.max_length, tm.device)
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
                logits = tm.model(**enc).logits
            out.append(torch.softmax(logits.float(), dim=-1).cpu().numpy())
    return np.concatenate(out, axis=0)


def _val_metrics(tm: TrainedModel, val: list[dict]) -> tuple[float, float, np.ndarray]:
    k = len(tm.labels)
    index = {lab: i for i, lab in enumerate(tm.labels)}
    y = np.array([index[r["label"]] for r in val])
    proba = predict_proba(tm, [r["text"] for r in val])
    pred = proba.argmax(axis=1)
    cm = np.bincount(y * k + pred, minlength=k * k).reshape(k, k)
    return macro_f1_cm(cm), float((y == pred).mean()), proba


def fit(train: list[dict], val: list[dict], cfg: TrainConfig, labels: tuple[str, ...],
        log_path: Path | None = None, tag: str = "") -> TrainedModel:
    """Дообучение с ранней остановкой по macro-F1 на val. Возвращает модель лучшей эпохи."""
    torch = _torch()
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

    if not train:
        raise ValueError("пустой train")
    if not val:
        raise ValueError("пустой val: ранняя остановка и порог needs_review без validation невозможны")
    set_seed(cfg.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    k = len(labels)
    index = {lab: i for i, lab in enumerate(labels)}
    tokenizer = AutoTokenizer.from_pretrained(cfg.model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        cfg.model_name, num_labels=k, id2label={i: lab for i, lab in enumerate(labels)},
        label2id={lab: i for i, lab in enumerate(labels)}, ignore_mismatched_sizes=True)
    # Длина не больше, чем умеет модель: у RoBERTa-подобных позиции сдвинуты на 2 (у xlm-roberta-base 514 -> 512).
    max_pos = getattr(model.config, "max_position_embeddings", None)
    if max_pos and cfg.max_length > max_pos - 2:
        print(f"[civic_classifier_v2] max_length {cfg.max_length} > возможностей модели ({max_pos - 2}) — "
              f"уменьшаю до {max_pos - 2}", flush=True)
        cfg = cfg.override([f"max_length={max_pos - 2}"])
    if cfg.freeze_embeddings:
        emb = model.get_input_embeddings()
        emb.weight.requires_grad_(False)
    model.to(device)
    tm = TrainedModel(model, tokenizer, tuple(labels), cfg, device, info=device_info())
    tm.info["params_total"] = sum(p.numel() for p in model.parameters())
    tm.info["params_trainable"] = sum(p.numel() for p in model.parameters() if p.requires_grad)

    texts = [r["text"] for r in train]
    y = [index[r["label"]] for r in train]
    weights = class_weights(y, k, cfg.class_weight)
    loss_fn = torch.nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32, device=device),
                                        label_smoothing=cfg.label_smoothing)
    no_decay = ("bias", "LayerNorm.weight", "layer_norm.weight", "LayerNorm.bias")
    trainable = [(n, p) for n, p in model.named_parameters() if p.requires_grad]
    groups = [
        {"params": [p for n, p in trainable if not any(nd in n for nd in no_decay)], "weight_decay": cfg.weight_decay},
        {"params": [p for n, p in trainable if any(nd in n for nd in no_decay)], "weight_decay": 0.0},
    ]
    optim = torch.optim.AdamW(groups, lr=cfg.lr)
    steps_per_epoch = math.ceil(math.ceil(len(texts) / cfg.batch_size) / cfg.grad_accum)
    epochs = cfg.epochs
    if cfg.min_train_steps and steps_per_epoch * epochs < cfg.min_train_steps:
        epochs = max(epochs, min(cfg.max_epochs, math.ceil(cfg.min_train_steps / steps_per_epoch)))
    tm.info["epochs_planned"] = epochs
    tm.info["steps_per_epoch"] = steps_per_epoch
    total = max(1, steps_per_epoch * epochs)
    sched = get_linear_schedule_with_warmup(optim, int(cfg.warmup_ratio * total), total)
    use_amp = device == "cuda" and cfg.fp16
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    gen = random.Random(cfg.seed)
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()

    best_state, best_f1, best_epoch, bad, opt_steps = None, -1.0, 0, 0, 0
    log_fh = open(log_path, "a", encoding="utf-8") if log_path else None
    try:
        for epoch in range(1, epochs + 1):
            model.train()
            t0 = time.time()
            run_loss, n_seen = 0.0, 0
            optim.zero_grad(set_to_none=True)
            batches = _batches(len(texts), cfg.batch_size, True, gen)
            for step, idx in enumerate(batches, 1):
                enc = _encode(tokenizer, [texts[i] for i in idx], cfg.max_length, device)
                target = torch.tensor([y[i] for i in idx], dtype=torch.long, device=device)
                with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
                    logits = model(**enc).logits
                loss = loss_fn(logits.float(), target)
                scaler.scale(loss / cfg.grad_accum).backward()
                run_loss += float(loss.detach()) * len(idx)
                n_seen += len(idx)
                if step % cfg.grad_accum == 0 or step == len(batches):
                    scaler.unscale_(optim)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.max_grad_norm)
                    scaler.step(optim)
                    scaler.update()
                    sched.step()
                    optim.zero_grad(set_to_none=True)
                    opt_steps += 1
            val_f1, val_acc, _ = _val_metrics(tm, val)
            row = {"tag": tag, "epoch": epoch, "of": epochs, "steps": opt_steps,
                   "train_loss": round(run_loss / max(1, n_seen), 5),
                   "val_macro_f1": round(val_f1, 4), "val_accuracy": round(val_acc, 4),
                   "lr": float(sched.get_last_lr()[0]), "seconds": round(time.time() - t0, 1)}
            if device == "cuda":
                row["gpu_peak_gb"] = round(torch.cuda.max_memory_allocated() / 2 ** 30, 2)
            improved = val_f1 > best_f1 + cfg.min_delta
            row["improved"] = bool(improved)
            tm.history.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if log_fh:
                log_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                log_fh.flush()
            if improved:
                best_f1, best_epoch, bad = val_f1, epoch, 0
                # Лучшие веса держим в памяти CPU (≈1.1 ГБ для xlm-roberta-base), а не на диске.
                best_state = {n: t.detach().to("cpu", copy=True) for n, t in model.state_dict().items()}
            else:
                bad += 1
                if bad >= cfg.patience and opt_steps >= cfg.min_train_steps:
                    break
    finally:
        if log_fh:
            log_fh.close()
    if best_state is not None:
        model.load_state_dict(best_state)
    tm.best_epoch, tm.best_val_macro_f1 = best_epoch, round(best_f1, 4)
    # Порог needs_review — на val той же (лучшей) модели.
    _, _, proba = _val_metrics(tm, val)
    pred = proba.argmax(axis=1)
    yv = [index[r["label"]] for r in val]
    tm.threshold = choose_threshold([float(proba[i, p]) for i, p in enumerate(pred)],
                                    [int(p) == t for p, t in zip(pred, yv)],
                                    [labels[int(p)] == "other" for p in pred], cfg.review_target_precision)
    if device == "cuda":
        tm.info["gpu_peak_gb"] = round(torch.cuda.max_memory_allocated() / 2 ** 30, 2)
    return tm


def save(tm: TrainedModel, out_dir: Path, meta: dict) -> Path:
    """save_pretrained (safetensors) + токенизатор + birge_meta.json (метки, порог, конфиг, версия)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tm.model.save_pretrained(out_dir)
    tm.tokenizer.save_pretrained(out_dir)
    full = {"format": META_FORMAT, "labels": list(tm.labels), "threshold": tm.threshold.get("chosen", 1.0),
            "threshold_detail": tm.threshold, "train_config": tm.cfg.to_dict(), "best_epoch": tm.best_epoch,
            "best_val_macro_f1": tm.best_val_macro_f1, "history": tm.history, "env": tm.info, **meta}
    (out_dir / META_NAME).write_text(json.dumps(full, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out_dir


def load(model_dir: Path, device: str | None = None) -> TrainedModel:
    torch = _torch()
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    model_dir = Path(model_dir)
    meta = json.loads((model_dir / META_NAME).read_text(encoding="utf-8"))
    if meta.get("format") != META_FORMAT:
        raise ValueError(f"{model_dir}: не модель v2 ({meta.get('format')})")
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = AutoModelForSequenceClassification.from_pretrained(model_dir).to(device)
    model.eval()
    tok = AutoTokenizer.from_pretrained(model_dir)
    cfg = TrainConfig.from_dict(meta.get("train_config") or {})
    tm = TrainedModel(model, tok, tuple(meta["labels"]), cfg, device, history=meta.get("history") or [],
                      best_epoch=meta.get("best_epoch", 0), best_val_macro_f1=meta.get("best_val_macro_f1", 0.0),
                      threshold=meta.get("threshold_detail") or {"chosen": meta.get("threshold", 1.0)},
                      info=meta)
    return tm


def free(tm: TrainedModel | None) -> None:
    """Освободить GPU между фолдами."""
    if tm is None:
        return
    torch = _torch()
    tm.model.to("cpu")
    del tm.model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
