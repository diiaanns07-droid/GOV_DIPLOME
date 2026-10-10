# R03 · раунд 14 · handoff

Задача: R03 — классификатор v2 на трансформере (research/round-14/prompts/R03.txt).
Агент / город: Claude Code (облачная сессия), Астана, Birge.
Обновлено: 2026-10-10 (UTC; точное время — у коммита).
Статус: **код готов (цель 12 окт выполнена 10 окт); ждём LOCAL-4 (обучение на GPU) и разметку людей.**
Рабочая ветка: claude/r14-R03 (от claude/round-14-package @ 3c5ac25). В claude/round-14-package не пушу.
Последний код: 30c1c09 (tested_sha). Push: OK.
Назначенные пути: ml/civic_classifier_v2/, tests/civic/R03/round14/ (старые tests/civic/R03/*.mjs раунда 13 —
другой модуль, не трогаю), research/round-14-results/R03/, этот файл.

## Что сделано
- [x] 1. ml/civic_classifier_v2/: config (FacebookAI/xlm-roberta-base, 128, fp16, batch 16×2, freeze_embeddings),
      data (корпуса R02, экспорт web/labeling, split по шаблонам, k-fold, удаление утечек), labels (из categories_v2.json),
      transformer + train (взвешенные классы, ранняя остановка по val macro-F1, seed, лог JSONL), evaluate
      (macro-F1, P/R/F1, матрица, бутстрэп 95%, ECE, срезы, RESULTS.md), predict (Classifier для R04).
- [x] 2. experiments.py: synth_v1 / synth_template / synth_llm / synth_all / human (5-fold) / mix × heuristic /
      logreg (метод v1) / transformer; zero-shot LLM (zeroshot.py, только локально) и v1 как есть; парные Δ.
- [x] 3. export_onnx.py: ONNX (torchscript, запасной dynamo) + int8 + сверка с PyTorch + скорость CPU.
- [x] 4. research/round-14-results/R03/RUN.txt — команды PowerShell для ноутбука (шаги 0–9), время, память.
- [x] 5. MODEL_CARD.md v2 (данные, протокол, текущие числа, ограничения).
- [x] Тесты: 62 PASS (tests/civic/R03/round14), без ML-библиотек 56 PASS + 6 NOT_RUN.
- [x] Облако: базовые модели на корпусах R02 → results/RESULTS.md, experiments.json; модель размера xlm-r-base со
      случайными весами → results/cloud_check_2026-10-10.json (int8 266 МБ, 11–33 мс/текст).
- [x] DELIVERY.json, INTEGRATION.txt (R01 .gitignore, R04 подключение /classify, R10 тесты, LOCAL-4).

## Главные числа сейчас (синтетика v3 test, не люди)
словарь 0.731 [0.570–0.857]; логрегрессия (v3) 0.632 [0.494–0.771]; логрегрессия (v1→v2) 0.548.
Слабые места: казахский ≈0.5, транслит 0.02–0.29. Трансформер — NOT_RUN (нет весов в облаке).

## Ждём
- LOCAL-4: Codex выполняет RUN.txt и пушит results в claude/r14-R03.
- R02/владелец: corpus_llm_v1.jsonl (LOCAL-8); разметка людей ≥ 200 (birge-labels-v1, private/).

## Следующий шаг
1. Когда в claude/r14-R03 появятся results от ноутбука: git pull; проверить experiments.json (статусы OK,
   onnx_export.json verdict три PASS, gpu_peak_gb), прогнать `python -m ml.civic_classifier_v2.evaluate render`,
   дописать в MODEL_CARD.md раздел «Результаты на людях» с выводами (потеря на людях, вклад людей/синтетики,
   трансформер против словаря), обновить DELIVERY.json (tested_sha, tests), push.
2. Если людей < 200 к 13 окт — оставить NOT_EVALUATED, всё остальное — по синтетике.
3. Необязательно (если останется время): кривая обучения «сколько текстов людей нужно» (mix с долями 25/50/100%).
