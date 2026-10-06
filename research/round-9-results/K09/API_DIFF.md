# K09 r9, этап 1 — сверка r8 K09 с настоящим plan.js сборки d865dd4

Сравнивались:
- **BUILD:** `claude/beautiful-clarke-sbzomj` @ `d865dd4a124291e10dd0b7bb1d9eada20d34c268`. Дерево приложения `a5d85e6…` совпадает с кодом `3e1302a`, это подтверждено `git rev-parse`. Манифест — `inputs/BUILD_MANIFEST_d865dd4.json`.
- **r8 K09:** `claude/save-work-handoff-qho6eq` @ `e953ddc`. Модули `research/round-8-results/K09/k09plan` использовались только для чтения; r8 и T1 не изменялись.

Метод:
1. **Задачи.** `scripts/make_build_tasks.py` строит задачи из r8:
   - 34 задачи слепой проверки r8;
   - все 2610 сценариев v1;
   - все 3420 сценариев v2.

   Наборы для evaluatePlan: три точных плана r8, жадные планы G1 и G2 и пустой план.
2. **Прогон BUILD.** `adapter/build_plan_adapter.cjs` загружает **настоящие** `web/plan.js`, `whatif.js`, `facts.js` и `data.js` из байтовой копии BUILD и вызывает `makeContext`, `validatePlanScenario`, `optimizePlans`, `sensitivity` и `evaluatePlan`. Движок не копируется и не меняется.
3. **Сверка.** `scripts/compare_build.py` пересчитывает результат оракулом r8 и сверяет математические результаты. Внутренние digest не сравниваются.

## Итог по метрикам: расхождений 0

| Набор | Задач | Победители (3 цели) | Парето | feasible_count | Чувствительность к бюджету | evaluatePlan: метрики, допустимость, строки | Статус, причины infeasible |
|---|---|---|---|---|---|---|---|
| ind34 (r8, слепая проверка) | 34 | 28×3 = | 28 = | 28 = | 34 = | по 91 = | 34 =, 6 = |
| v1 (вся сетка r8) | 2610 | 2610×3 = | 2610 = | 2610 = | 2610 = | по 8482 = | 2610 = |
| v2 (вся сетка r8) | 3420 | 3420×3 = | 3420 = | 3420 = | 3420 = | по 10214 = | 3420 = |

«=» означает «совпало». Сравнивались ids, cost, unknown_count, weighted_sum_mm, max_mm и covered_weight. Строки evaluatePlan сверялись по before_mm, after_mm, delta_mm и nearest_after (kind:id). Подробности — `results/stage1/compare_d865dd4.json`.

Это означает:
- **Выводы r8 о жадных алгоритмах переносятся на BUILD.** Доли совпадения с оптимумом и разрывы r8 считались относительно exact, а exact в BUILD даёт те же планы и метрики на всех 6030 сценариях. Сами жадные G1 и G2 в BUILD отсутствуют: это алгоритмы эксперимента K09, а не функция продукта.
- **Исходные записи совпадают.** Shymkent/school — 15 записей, Astana/outpatient_clinic — 16. `data.js` на a5b5e2d и d865dd4 побайтно одинаков.

## Время BUILD

`optimizePlans`, Node v22.22.0, linux x64, минимум из 3 повторов, медиана / максимум в мс:

| Группа | n | BUILD JS | r8 Python (exact без Парето, медиана) |
|---|---|---|---|
| 6 кандидатов, max_selected = 3 | 810 / 1080 | 0.11 / 0.41 и 0.10 / 0.40 | 0.12–0.14 |
| 10 кандидатов, max_selected = 3 | 810 / 1080 | 0.28 / 0.87 и 0.20 / 0.80 | 0.56–0.77 |
| 16 кандидатов, max_selected = 3 | 900 / 1170 | 1.89 / 3.85 и 1.56 / 3.46 | 7.0–8.3 |
| 16 кандидатов, max_selected = 5 (v1, бюджет почти не ограничивает) | 30 | 10.6 / 12.1 | 47.9 |

**BUILD:**
- считает три цели и Парето за один проход;
- чувствительность к бюджету не входит в это время;
- браузер и Web Worker здесь не измерялись.

**Окружение и ограничения замеров:**
- окружение: `results/stage1/OUTPUT_HASHES.json`;
- замеры на одной машине;
- это не обещание для пользовательских устройств.

## Различия API: K09 r8 (Python) против BUILD plan.js

Ни одно из перечисленных различий не меняет числа.

| # | Аспект | BUILD d865dd4 | K09 r8 | Следствие для адаптера |
|---|---|---|---|---|
| 1 | Контекст | `makeContext(data, city, F)`: город целиком, `places` обеих категорий. `source_snapshot` = sha256 от [schema, city, release, sha файла, placesDigest, metric] | контекст на (город, категория, baseline); `k09r8-slice:` от sha data.js + город + категория (+ условие) | адаптер берёт snapshot из контекста BUILD |
| 2 | Исходные записи | `places` по group, **без** фильтра bbox | по group **внутри** bbox | на d865dd4 наборы совпадают: все записи внутри bbox |
| 3 | Условие «нет записей» | флага нет | `empty_synthetic_condition` | адаптер строит тестовый контекст без записей категории (другой snapshot). Это не данные продукта |
| 4 | ID | NFC; буквы любой письменности, цифры, `_ . -`; 1..64 code points; `:` запрещено | `[\w.:-]{1,64}`, `:` разрешено; NFC не проверяется | в задачах r8 ID вида `p00` и `c00`, различие не проявилось. В r9 следовать BUILD (CORE_SPEC r9: Unicode NFC) |
| 5 | Ошибки валидации | первая ошибка, typed `PlanError(code)`; коды `foreign_snapshot`, `too_many_candidates`, `bad_weight` … | список всех ошибок `{code, path}`, другие имена кодов | сравнивать по факту отказа и смыслу, а не по имени кода |
| 6 | Координаты | конечны, \|lon\| ≤ 180, \|lat\| ≤ 90, bbox | конечны, bbox | — |
| 7 | Результат optimize | `objectives[o].ids`; нет weighted_mean и coverage_fraction; `evaluated` = **все** просмотренные маски (2^free); `total_subsets`; `pareto_excluded_unknown`; `request_id` | `selected_ids`; есть weighted_mean_mm и coverage_fraction; `evaluated` = **допустимые** маски (= feasible_count); `subsets_total` | `evaluated` сравнивать нельзя: разные определения; feasible_count совпадает |
| 8 | infeasible | массив **всех** нарушенных причин; `required_exceeds_max_selected`, `required_cost_exceeds_budget` | одна причина (сначала число); `required_count_exceeds_max_selected` | карта кодов в `compare_build.py`; во всех 6 случаях причины совпали |
| 9 | Больше 16 кандидатов | валидатор: `too_many_candidates`. Сам `createSearch` размер не проверяет (находка K12 r8) | `status: too_large` до перебора | при вызове API в обход валидатора BUILD пойдёт в перебор. Исправление — задача BUILD |
| 10 | Статусы | optimal / infeasible / cancelled / incomplete (пошаговый поиск) | optimal / infeasible / too_large (синхронно) | — |
| 11 | evaluatePlan | строки в порядке входа, с before_m/after_m (м без округления), lon/lat/weight; блок baseline; коды допустимости over_budget / too_many / missing_required / has_excluded | строки по id, только мм; коды cost_exceeds_budget / count_exceeds_max_selected / missing_required / contains_excluded | карта кодов; строки сверяются по id точки |
| 12 | digest | JSON массива [schema, metric, city, snapshot, category, точки, кандидаты (id, lon, lat, cost), …]; sources не входят, их покрывает snapshot | канонический словарь, включает список sources, category и kind кандидатов | **побайтно не сравнимы** (CORE_SPEC). Оба не зависят от порядка, selected_ids в problem digest не входит |
| 13 | Ничьи | ключ цели, затем отсортированные ids; nearest: мм, затем source раньше hypothetical, затем id | то же | совпало на всех задачах |
| 14 | Чувствительность к бюджету | [0, ⌊B/2⌋, B]; reasons, objectives, feasible_count | то же множество бюджетов | совпало |

## Чего этот этап не проверял (SKIP / NOT_RUN)

- **UI plan-ui.js и браузерный путь.** Задача K09 — движок и эксперимент. UI проверяли K07 и K12.
- **Импорт и экспорт файлов BUILD.** `importPlanScenario` и `derived_results` проверял K10.
- **Ограничение createSearch.** Его отсутствие при прямом вызове — находка K12; здесь не воспроизводилось.
- **Время в браузере.**

## Воспроизведение

```
python3 scripts/pin_build.py --sha d865dd4a124291e10dd0b7bb1d9eada20d34c268 --out /tmp/k09_build_d865dd4
python3 scripts/make_build_tasks.py --out /tmp/k09_s1_tasks.jsonl                       # 6064 задачи, sha256 в OUTPUT_HASHES.json
node adapter/build_plan_adapter.cjs --web /tmp/k09_build_d865dd4/prototypes/city-evidence/web \
     --in /tmp/k09_s1_tasks.jsonl --out /tmp/k09_s1_build.jsonl --repeats 3
python3 scripts/compare_build.py /tmp/k09_s1_tasks.jsonl /tmp/k09_s1_build.jsonl results/stage1/compare_d865dd4.json   # exit 0 = 0 расхождений
```
