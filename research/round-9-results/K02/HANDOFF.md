# K02 r9 HANDOFF — объяснения по фактам (не BUILD)

Ветка: `claude/clever-mccarthy-pywscu`.
- **Закреплённая сборка** по `research/round-9/snapshots.json`: `d865dd4a124291e10dd0b7bb1d9eada20d34c268`. Код совпадает с `3e1302a`.
- **Дополнительный прогон** на появившемся коммите сборщика `fb768b25b5de5b151bb83ad9ce0af3b965ab2025`.
- Обе сборки извлечены побайтно, git blob сверен. Общий прототип не менялся.

## Этап 1. Действующие explainPlans/reportHtml сборки
Тест: `tests/s1_build_explain.cjs`, адаптер `tests/common.cjs` (фикстуры r8 → `makeContext`/`validatePlanScenario` сборки).

| Проверка | d865dd4 | fb768b2 |
|---|---|---|
| B0 ×14: `optimizePlans`/`evaluatePlan`/`sensitivity` = независимый Python-оракул K02 r8 | PASS | PASS |
| E1: числа объяснения взяты из сценария и результата | PASS | PASS |
| E2: неизвестное — «нет данных», а не 0 | PASS | PASS |
| E3: совпавшие стратегии подписаны | PASS | PASS |
| E4: старый digest → `stale_explanation` | PASS | PASS |
| E7: невыполнимость объяснена | PASS | PASS |
| E8: `reportHtml` экранирует; null → «нет данных» | PASS | PASS |
| **E5: результат другой задачи принят** | **FAIL** | **FAIL** |
| **E6: ручная оценка другого выбора принята** | **FAIL** | **FAIL** |

**Дефект E5/E6** (уровень публичного API; UI защищён проверкой в `plan-ui.js:443`).
- **Место:** `web/plan.js:338–340`, `explainPlans`. Digest считается только по переданным объектам, поэтому вызывающий может пересчитать его для чужого `result`/`manual`, и подмена пройдёт.
- **Минимальное воспроизведение:**
  ```js
  explainPlans(scB, manB, resultA, sensB, explanationDigest(scB, manB, resultA, sensB, F), F)
  ```
  возвращает текст, хотя `resultA.problem_digest ≠ problemDigest(scB)`.
- **Patch-предложение:** `patches/explain_binds_facts.patch`. Проверка `problem_digest` результата, `selected_ids` ручной оценки и бюджетов чувствительности. Плюс правка `tests/plan.cjs:193`: тест сборки сам передавал ручную оценку для `[]` при другом `selected_ids`.
- **Проверено на копии `d865dd4` + patch:**
  - `s1` — 22/22;
  - `plan.cjs`, `conformance`, `whatif`, `smoke`, `plan_smoke` — pass;
  - patch применяется к `d865dd4` и `fb768b2` (`git apply --check`).

  В сборку **не применён**; FIXED не заявляется.

## Этап 2. Факты и renderer устойчивости
Модуля устойчивости в `d865dd4` и `fb768b2` нет (`web/resilience.js` отсутствует).

**`resilience_facts.js` — основной результат.** API:
- **`buildResilienceCatalog(env, manualEval, opt, names, {F}, {resilience_problem_digest})`** → `{catalog, city, scenario, digest, resilience_problem_digest, status, …}`. Формат совместим с `facts.validatePlan` сборки.
  - **Вход:** `env = {sc, cases}` (base первым), `manualEval = evaluateResilience(...)`, `opt = optimizeResilience(...)` в формате CORE_SPEC r9: `status`, `nominal`, `robust`, `price_of_robustness_m`/`price_reason`, `evaluated`, `feasible_count`, `resilience_problem_digest`.
  - **Факты:**
    - `case.cN.excluded_count/excluded_ids` (с именами записей);
    - `case.cN.<manual|nominal|robust>.{weighted_mean, max, unknown_count, covered_weight, cost}`;
    - `plan.<p>.{selection, feasible, worst.unknown_count, worst.weighted_sum_mm, worst.max, worst.case_ids}`;
    - `price.robustness` (м или null с `missing_reason`: `infeasible`/`not_optimal`/`unknown_base_mean`);
    - `search.*`.

    У каждого факта есть `kind`/`unit`/`scope`/`hypothetical`.
  - **Проверки согласованности** (без пересчёта показываемых значений):
    - случаи и порядок совпадают с envelope;
    - худшие случаи взяты из envelope;
    - ручная оценка сделана для текущего выбора;
    - цена = разность средних base, при совпавших планах = 0;
    - при `status` ≠ `optimal` нет заявленных планов и цены.
- **`explain(built, lang, {F}, request)`** = `StubSelector` (заглушка, не LLM) → `facts.validatePlan` → `render`. Отказы: `stale_problem`, `tampered_catalog` (digest пересчитывается), `stale_catalog`, `duplicate_id`.
- **Текст:**
  - русский; казахский — черновик с явной пометкой «тілдік тексеруді қажет етеді»;
  - заголовок «шаблонное объяснение… не LLM и не AI»;
  - оговорка «не подтверждение закрытия»;
  - случаи с исключениями, дубль случаев;
  - таблица трёх планов по случаям, худший вектор и **все** худшие случаи;
  - цена устойчивости или «совпадают — цена 0 м, компромисса нет»;
  - пометка «НЕДОПУСТИМ, не рекомендуется» для ручного плана;
  - ограничения: без вероятностей и риска, вес ≠ жители, условная стоимость.

  Пользовательский текст (ID, метки, имена) выводится как простой текст. **UI обязан вставлять результат через `textContent`/экранирование, не через `innerHTML`/markdown.**

**`resilience_ref.js`** — генератор результатов для фикстур поверх `plan.js` сборки (`precompute`/`evaluatePlan`/`optimizePlans`/`feasibility`). Это не продукт и не второй движок; фильтрует копию ctx, исходный не мутирует.

**Фикстуры** (`make_resilience_fixtures.cjs` → `fixtures/res_*.json`):
- `res_shymkent_school`: 4 случая, включая дубль и «все записи»;
- `res_astana_clinic`: 2 случая, ручной план недопустим;
- две синтетические.

Реальные срезы — данные `data.js` сборки (provenance: SHA, sha256). Кандидаты, веса, стоимости и случаи — synthetic/пользовательские допущения.

## Этап 3. Независимая проверка и негативы
- **Оракул:** `oracle/resilience_oracle.py` (Python stdlib, своя реализация) → `expected/res_*.json`.
- **Негативы:** `fixtures/negative.json` — 18 мутаций с ожидаемыми кодами:
  - подмена факта или имени → `tampered_catalog`;
  - подмена случая или digest → `stale_problem`;
  - старый план → `stale_catalog`;
  - дубль факта → `duplicate_id`;
  - порядок случаев, худший случай не из envelope, ненулевая цена при одинаковых планах, несогласованная цена, `incomplete` с планами → `bad_result`;
  - честный `incomplete`;
  - чужой ручной выбор → `stale_explanation`;
  - `base`/дубль id → `duplicate_case`;
  - candidate ID как источник → `unknown_source`;
  - нет исходных записей → `bad_exclusion`;
  - 13 кандидатов → `too_many_candidates`.
- **Тест:** `tests/s3_negative_oracle.cjs`.
- **Мутации адаптера:**
  - отключение `tampered_catalog` → FAIL N01/N02;
  - отключение проверки худших случаев → FAIL N08;
  - отключение «совпавшие планы ⇒ цена 0» не ловится: ту же подмену отклоняет общая проверка согласованности цены (N09 проходит через неё). Проверка избыточна.
- **Примеры** обоих городов: `examples/shymkent.txt`, `examples/astana.txt` (`demo.cjs`): v2-объяснение сборки и устойчивость ru/kk.

## Команды
```bash
APP=<извлечённая prototypes/city-evidence @ d865dd4 или fb768b2>
cd research/round-9-results/K02
node tests/s1_build_explain.cjs   --app-root $APP --json runs/s1_<sha>.json
node make_resilience_fixtures.cjs --app-root $APP --build-sha <sha>   # детерминированно
python3 oracle/resilience_oracle.py
node tests/s2_resilience.cjs      --app-root $APP --json runs/s2_<sha>.json
node tests/s3_negative_oracle.cjs --app-root $APP --json runs/s3_<sha>.json
node demo.cjs --app-root $APP --out examples
```

## Итог прогонов (Node v22.22.0, Python 3.11.15)
| Набор | d865dd4 | fb768b2 |
|---|---|---|
| s1 | 20 PASS / 2 FAIL (E5, E6) | 20 PASS / 2 FAIL (E5, E6) |
| s2 | 8 PASS | 8 PASS |
| s3 | 22 PASS | 22 PASS |

Копия `d865dd4` + patch: s1 22/22, тесты сборки pass.

**NOT_RUN:**
- интеграция устойчивости в BUILD (модуля нет);
- браузерный UI устойчивости;
- LLM (не вызывалась, точность не заявляется).

## Ограничения
- s2/s3 проверяют адаптер K02 и генератор поверх `plan.js` сборки, а **не** продуктовый `resilience.js`: его ещё нет.
- Тексты причин недопустимости приходят из `plan.js` только на русском и попадают в kk-черновик как есть. Метка случая `base` — русская константа генератора.
- Расстояния по прямой; вес — приоритет, не жители; стоимость условная.

## Следующий шаг
1. BUILD применяет `patches/explain_binds_facts.patch`.
2. Когда появится `web/resilience.js`, подключить `resilience_facts.js` к его выводу (тот же формат API) и перезапустить s2/s3, подставив продуктовый `optimizeResilience`/`evaluateResilience` вместо `resilience_ref.js` в `tests/res_common.cjs`.
