# R03 · раунд 14 · handoff

Задача: R03 — классификатор v2 на трансформере (research/round-14/prompts/R03.txt).
Агент / город: Claude Code (облачная сессия), Астана, Birge.
Обновлено: 2026-10-10, вторая сессия — добавлен probe_v2 (UTC; точное время — у коммита).
Статус: **код готов (цель 12 окт выполнена 10 окт); ждём LOCAL-4 (обучение на GPU) и разметку людей.**
Рабочая ветка: claude/r14-R03 (от claude/round-14-package @ 3c5ac25). В claude/round-14-package не пушу.
Последний код: см. DELIVERY.json code_sha (= tested_sha). Push: OK.
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
- [x] Тесты: 65 PASS (tests/civic/R03/round14), без ML-библиотек 58 PASS + 7 NOT_RUN.
- [x] Честность режима «только люди»: на малых данных до 30 эпох, ранняя остановка не раньше 300 шагов.
- [x] Кривая обучения: experiments --human-fraction 0.25/0.5 (RUN.txt шаг 6б, по желанию).
- [x] Облако: базовые модели на корпусах R02 → results/RESULTS.md, experiments.json; модель размера xlm-r-base со
      случайными весами → results/cloud_check_2026-10-10.json (int8 266 МБ, 11–33 мс/текст).
- [x] DELIVERY.json, INTEGRATION.txt (R01 .gitignore, R04 подключение /classify, R10 тесты, LOCAL-4).
- [x] probe_v2 (R02 @ 73b97d2, ml/datasets/probe_v2/, 300 текстов агента вне шаблонов) — независимый тест:
      experiments (все режимы; human/mix — ансамбль моделей фолдов; аргумент --probe-v2), RESULTS.md (разделы 1б,
      «без обучения», колонка и «потеря шаблоны → probe» в разделе 2, парные Δ, 4б), train.py (probe_v2_eval в
      birge_meta.json), zero-shot на людях и probe, RUN.txt ($PROBE во всех командах). В обучение и выбор не входит,
      совпадающие тексты удаляются из обучения (spy-тест).

## Главные числа сейчас (не люди; трансформер — NOT_RUN, нет весов в облаке)
- Синтетика v3 test (шаблоны): словарь 0.731 [0.570–0.857]; логрегрессия (v3) 0.632 [0.494–0.771]; (v1→v2) 0.548.
- **probe_v2 (вне шаблонов):** словарь 0.684 [0.628–0.726]; логрегрессия (v3) **0.751** [0.696–0.795]; (v1→v2) 0.534.
  Логрегрессия − словарь: +0.067 [+0.026; +0.111] — вне шаблонов обученная модель лучше (на синтетическом test — нет).
  v3 − v1→v2 (логрегрессия): +0.217 [+0.162; +0.271].
- Слабые места: транслит (0.01–0.42), трудные случаи (0.51–0.57).

## Ждём
- LOCAL-4: Codex выполняет RUN.txt и пушит results в claude/r14-R03.
- R02/владелец: corpus_llm_v1.jsonl (LOCAL-8); разметка людей ≥ 200 (birge-labels-v1, private/).

## Следующий шаг
1. Когда в claude/r14-R03 появятся results от ноутбука: git pull; проверить experiments.json (статусы OK,
   probe_v2 оценён во всех режимах, onnx_export.json verdict три PASS, gpu_peak_gb), прогнать
   `python -m ml.civic_classifier_v2.evaluate render`, дописать в MODEL_CARD.md выводы: трансформер против словаря
   и логрегрессии на probe_v2 и на людях, потеря «шаблоны → probe» и «шаблоны → люди», вклад людей/синтетики;
   обновить DELIVERY.json (tested_sha, tests), push.
2. Если людей < 200 к 13 окт — оставить NOT_EVALUATED, всё остальное — по синтетике.
3. Если был шаг 6б — описать кривую обучения (lc_0.25 / lc_0.5 / experiments) в MODEL_CARD.md.
