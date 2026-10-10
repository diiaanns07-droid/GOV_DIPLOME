"""Birge · классификатор обращений v2 (R03, раунд 14): 12 категорий из categories_v2.json, RU/KK/смешанный.

Модули:
  labels      — категории из research/round-14/categories_v2.json (не копируются в код);
  data        — загрузка синтетики R02 (шаблонная v3, LLM llm_v1) и разметки людей, split, k-fold;
  heuristic   — словарная эвристика (базовая модель, не обучается);
  logreg      — «v1-метод»: логрегрессия на символьных n-граммах + словарь (базовая модель);
  transformer — дообучение трансформера (xlm-roberta-base), ранняя остановка по macro-F1;
  experiments — режимы обучения × модели, оценка на одном наборе текстов людей -> results/RESULTS.md;
  train       — итоговая модель -> artifacts/final;  export_onnx — ONNX int8 -> artifacts/onnx;
  predict     — Classifier.classify(text) для R04 (POST /api/civic/v2/classify);
  zeroshot    — LLM без обучения (только локально, ключ из переменной окружения).
Импорт пакета не требует torch: тяжёлые библиотеки загружаются внутри функций.
"""

__all__ = ["labels", "data", "heuristic", "metrics"]
