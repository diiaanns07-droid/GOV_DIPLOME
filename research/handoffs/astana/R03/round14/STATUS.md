# R03 · раунд 14 · handoff

Задача: R03 — классификатор v2 на трансформере (research/round-14/prompts/R03.txt).
Агент / город: Claude Code (облачная сессия), Астана, Birge.
Обновлено: 2026-10-10 (UTC; точное время — у коммита).
Статус: partial — код конвейера готов и проверен на крошечной модели; тесты, RUN.txt, MODEL_CARD в работе.
Рабочая ветка: claude/r14-R03 (создана от claude/round-14-package @ 3c5ac25). В claude/round-14-package не пушу.
Назначенные пути: ml/civic_classifier_v2/, tests/civic/R03/round14/ (старые tests/civic/R03/*.mjs раунда 13 —
другой модуль, не трогаю), research/round-14-results/R03/, этот файл.

## Что сделано
- [x] ml/civic_classifier_v2/: labels (из categories_v2.json), config (xlm-roberta-base, 128, fp16, batch 16×2),
      data (корпуса R02 + экспорт web/labeling), heuristic (12 категорий ru/kk), logreg (метод v1),
      transformer (цикл PyTorch: взвешенные классы, ранняя остановка по val macro-F1), metrics (бутстрэп, парная Δ),
      evaluate (RESULTS.md из JSON), experiments (5 режимов × 3 модели, k-fold по людям), train (итоговая модель),
      export_onnx (ONNX + int8 + сверка + скорость), predict (Classifier для R04), zeroshot (LLM без обучения).
- [x] Прогон конвейера в облаке на крошечной случайной модели (не результат): experiments, train, export_onnx,
      predict — работают; токенизация tokenizers == transformers.
- [ ] tests/civic/R03/round14/ (pytest)
- [ ] RUN.txt (точные команды для ноутбука), MODEL_CARD.md, INTEGRATION.txt, DELIVERY.json, RESULTS.md-заглушка

## Ждём
- Корпус v3 и llm_v1 от R02 (ml/datasets/synth_v3/, ml/datasets/llm_v1/ в ветке claude/r14-R02) — на 10 окт ещё нет.
- Разметка людей ≥ 200 текстов (владелец, private/).

## Следующий шаг
Тесты pytest → RUN.txt → MODEL_CARD.md → INTEGRATION/DELIVERY → push.
