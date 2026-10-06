# K06 round 9 — независимый математический оракул (HANDOFF)

Роль: K06 (не BUILD). Ветка: claude/ecstatic-curie-hzfzn0 (начало раунда от 58cf89973cf3578620e016329139697becaf860f).
Задание: origin/codex/research-import-2026-10-05 @ 0ab1667, research/round-9/tasks/K06.txt, CORE_SPEC.txt, REVIEW.txt.
**Проверенная сборка: claude/beautiful-clarke-sbzomj @ d865dd4a124291e10dd0b7bb1d9eada20d34c268**, prototypes/city-evidence/
(199 файлов извлечены побайтно, git blob id сверены; код = 3e1302a по git diff).
Мои r8-модули скопированы побайтно в `r8/` (MANIFEST.json, commit 58cf899).

## Этап 1 — 96 gold-задач через настоящий plan.js (готово)
- `run_plan_js.cjs` — адаптер: `validatePlanScenario` + `optimizePlans` из `<app-root>/web/plan.js`; меняет только форму
  контекста (records → places). plan.js и ожидания не меняются.
- `compare_plan_js.py` — ожидания из сохранённого независимого gold (r8) и свежего прогона оракула r8, НЕ из приложения;
  классы PASS / MATH / API_POLICY / REJECTED / MISSING / ERROR.
- Результат на d865dd4: **96/96 PASS** (87 optimal, 9 infeasible; победители mean/minimax/coverage с метриками, Парето,
  feasible_count совпадают). `out/plan_js_d865dd4_gold96.json`, `out/compare_d865dd4_gold96.json`.
- `mutation_check_stage1.py`: 9 испорченных выходов plan.js классифицированы верно (7 MATH, 1 API_POLICY, 1 REJECTED).
- `probe_api_policy.py` + `probe_validate.cjs`: 24 синтетических входа, принять/отклонить. Совпадает 21. Отличия — ПОЛИТИКА API:
  1. ID с пробелом / двоеточием: plan.js `bad_id` (набор символов BUILD: буквы любых алфавитов, цифры, _ . -), оракул K06
     принимал любую строку ≤ 64. По CORE_SPEC r9 правила ID — правила BUILD; кириллица NFC принимается обоими.
  2. Отсутствует weight: plan.js `bad_shape`, оракул K06 подставлял 1. CORE_SPEC: «default 1 при создании» — это UI;
     строгость plan.js при импорте/прямом вызове допустима.
  3. Коды ошибок различаются по имени при одинаковом решении (out_of_range ↔ bad_radius и т.п.).
  Математических ошибок нет.

Команды (из этой папки; `<app>` — извлечённая копия, напр. `python3 ../../round-6-results/K06/extract_build.py /tmp/r9 d865dd4…` из корня):
```
python3 r8/compare_candidate.py --problems r8/fixtures/gold_cases.json --export /tmp/p9.json
node run_plan_js.cjs <app> /tmp/p9.json out/plan_js_d865dd4_gold96.json d865dd4a124291e10dd0b7bb1d9eada20d34c268
python3 compare_plan_js.py --problems r8/fixtures/gold_cases.json --plan-js-json out/plan_js_d865dd4_gold96.json --json out/compare_d865dd4_gold96.json
python3 mutation_check_stage1.py --problems r8/fixtures/gold_cases.json --plan-js-json out/plan_js_d865dd4_gold96.json
python3 probe_api_policy.py --app-root <app> --json out/api_policy_d865dd4.json
```

## Этап 2 — Python reference city-resilience-v1 (готово)
- `resilience_oracle.py` (stdlib; геометрия и v2-ограничения из собственного r8 оракула, не из JS):
  `validate_envelope` (строгий JSON ≤ 256 KiB; ровно schema_version/plan/cases; без производных полей; 1..7 случаев +
  авто "base"; id ≠ "base", уникальны; label 1..120 code points без Cc; disabled — уникальные ID исходных записей
  категории, 1..N; candidate ID вместо source → candidate_not_source; > 12 кандидатов → too_many_candidates до расчёта),
  `evaluate_resilience` (per_case, worst_vector с null вместо ∞, worst_case_ids, feasible), `optimize_resilience`
  (nominal = v2 mean на base; robust = min (W, L_base, cost, ids); price в метрах или null с причиной; digest не зависит
  от порядка случаев).
- `resilience_gold.py` — независимый переборщик (метрики из r8 gold_bruteforce, ключи/W/выбор отдельно, битовые маски).
- `make_resilience_cases.py` → `fixtures/resilience_gold.json` (seed 920261006): 62 задачи — 12 именованных SYNTHETIC
  (обычный ≠ устойчивый, цена 0 при разных планах, все записи исключены, то же при budget 0, нет кандидатов, равные
  худшие случаи / дубль случая, симметричная ничья всех трёх случаев, required невыполним, required сохранён, unknown
  только в случае, ничья по стоимости, ничья по ID) + 30 SYNTHETIC случайных + 20 на РЕАЛЬНЫХ записях обоих городов
  (data.js d865dd4) с синтетическими точками/кандидатами/исключениями; 16 must_reject.
  59 optimal, 3 infeasible; обычный ≠ устойчивый в 12; несколько худших случаев в 21.
- `test_resilience.py`: оракул = gold на 62; 16 must_reject с ожидаемым кодом; ручной пример (цена 79,425 м =
  5·(2,5u − 1,5u)/7, замкнутая формула); строгий JSON / размер; в выводе нет Infinity. 5 OK.

**BUILD r9 с устойчивостью не опубликован** (ветка сборщика: последний коммит d865dd4, resilience.js нет) →
интеграция city-resilience-v1: NOT_RUN.

## Этап 3 — свойства, адаптер, мутации, повторная проверка (готово)
- `test_resilience_metamorphic.py` (9 тестов): перестановки точек/кандидатов/случаев/исключений/записей не меняют
  устойчивый выбор, W, worst_case_ids и digest; дубль случая не меняет выбор (дубль попадает в список худших);
  добавление случая не улучшает минимальный worst vector, nominal и его base-строка неизменны; W(robust) ≤ W(nominal),
  L_base(robust) ≥ L_base(nominal), цена ≥ 0; evaluate(robust) = W. Мутации эталона обнаруживаются gold-фикстурой:
  покомпонентный max вместо лексикографического, только первый худший случай, max=null как 0, обратная ничья по ID,
  игнор стоимости в ничьей.
- `run_resilience_js.cjs` — адаптер к будущему `web/resilience.js` (`validateResilience` + `optimizeResilience`);
  без модуля пишет NOT_RUN. `compare_resilience_js.py` — сравнение по математике (status, feasible_count, nominal и
  robust IDs, robust W и worst_case_ids, цена); NOT_RUN → код 2, никогда не PASS.
- `resilience_harness_selftest.py` (только тестовые эхо-модули, не реализации): эхо 62 PASS (код 0); испорченный робастный
  выбор + обрезанный список худших → ровно 2 FAIL (код 1); нет модуля → 62 NOT_RUN (код 2).
- Повторная проверка этапа 1 на свежем извлечении d865dd4: вывод plan.js побайтно тот же, 96/96 PASS.

## Итог по проверенному SHA d865dd4a124291e10dd0b7bb1d9eada20d34c268
| Проверка | Результат |
|---|---|
| plan.js, 96 независимых gold-задач city-plan-v2 | 96 PASS, 0 MATH |
| политика валидации (24 пробы) | 21 одинаково; 3 API_POLICY (символы ID, обязательный weight, имена кодов) |
| mutation_check_stage1 (9 порч вывода) | 9/9 верно классифицированы |
| city-resilience-v1 в BUILD | **NOT_RUN** — web/resilience.js нет (ветка сборщика на d865dd4 на момент проверки) |
| эталон устойчивости: test_resilience + test_resilience_metamorphic | 14 OK |
| конвейер JS-сравнения устойчивости (resilience_harness_selftest) | PASS |
Python 3.11.15, Node 22, Linux.

## Команды (из этой папки)
```
python3 -m unittest -v test_resilience test_resilience_metamorphic
python3 make_resilience_cases.py --app-root <app>            # пересборка fixture (детерминирована)
python3 compare_resilience_js.py --fixture fixtures/resilience_gold.json --export /tmp/rp.json
node run_resilience_js.cjs <app> /tmp/rp.json /tmp/res_out.json <SHA>
python3 compare_resilience_js.py --fixture fixtures/resilience_gold.json --candidate-json /tmp/res_out.json
python3 resilience_harness_selftest.py
```
Когда BUILD опубликует resilience.js: извлечь новый SHA и выполнить две последние команды с ним; ожидания не менять.
Если имена полей отличаются (например, другой ключ цены) — это API_POLICY, правится адаптер, не gold.

## Ограничения
- Исключения записей — допущения о данных, не закрытие объектов и не прогноз риска; веса — приоритеты, не население.
- Метаморфное «добавление случая» проверено на эталоне K06, не на BUILD (у BUILD нет модуля).
- Оракул K06 принимает ID шире, чем BUILD, и подставлял weight=1 — это отличия политики, не математики.
