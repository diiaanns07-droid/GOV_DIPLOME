"""Настройки поиска дублей: dedup_config.json рядом с модулем (в Git, маленький).

Пороги записывает tune.py (подбор на dev-парах R02). Метод без подобранного порога
(threshold = null) не используется: модель без проверенного порога в приложение не попадает.
"""

from __future__ import annotations

import json
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parents[1]
CONFIG_PATH = PKG_DIR / "dedup_config.json"
# Веса e5 (LOCAL-задача): ONNX + tokenizer.json + e5_meta.json. Папка не в Git (> 50 МБ).
E5_DIR = PKG_DIR / "artifacts" / "e5"
RESULTS_DIR = PKG_DIR / "results"
PAIRS_PATH = REPO_ROOT / "ml" / "datasets" / "synth_v3" / "data" / "paraphrase_pairs_v3.jsonl"

FALLBACK_METHOD = "ngram-concept-v1"
# Если файла нет или он испорчен — безопасные значения запасного пути (подобраны 10 окт., см. RESULTS.md).
DEFAULTS = {
    "version": "civic-dedup-config-v1",
    "radius_m": 200,
    "default_days": 14,
    "methods": {
        FALLBACK_METHOD: {"threshold": 0.31, "alpha": 0.5, "ngram_range": [3, 5]},
        "e5-onnx": {"threshold": None, "alpha": 1.0},
    },
    "prefer": ["e5-onnx", FALLBACK_METHOD],
}


def load_config(path: Path | None = None) -> dict:
    path = CONFIG_PATH if path is None else Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("methods"), dict):
            raise ValueError("bad config")
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULTS))
    merged = json.loads(json.dumps(DEFAULTS))
    merged.update({k: v for k, v in data.items() if k != "methods"})
    for name, conf in data["methods"].items():
        if isinstance(conf, dict):
            merged["methods"].setdefault(name, {}).update(conf)
    return merged


def save_config(config: dict, path: Path | None = None) -> None:
    path = CONFIG_PATH if path is None else Path(path)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
