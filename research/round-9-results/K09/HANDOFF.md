# K09 · раунд 9 · «Диплом: проверяемый эксперимент устойчивости» — STATUS / HANDOFF

| Поле | Значение |
|---|---|
| Задание | `research/round-9/tasks/K09.txt`, CORE_SPEC r9, REVIEW (`codex/research-import-2026-10-05` @ `0ab1667`) |
| Ветка | `claude/save-work-handoff-qho6eq`; входной снимок r8 — `e953ddc`; по `snapshots.json` r9 это K09 |
| Не менялось | `prototypes/city-evidence`, main, чужие ветки, T1 (`research/round-3-results/K09`), r8 (`research/round-8-results/K09`) |
| Статус | этапы 1–3 выполнены; ready_for_review |

## Проверенные SHA

| BUILD | Что | Манифест |
|---|---|---|
| `d865dd4a124291e10dd0b7bb1d9eada20d34c268` | закреплённая база r9 (код = `3e1302a`, дерево `a5d85e6`) | `inputs/BUILD_MANIFEST_d865dd4.json` |
| `33cc635ec212e522b3e17fb0b598fad0ad602f71` | BUILD r9, этап 2 (resilience.js = `7077ff7`) | `inputs/BUILD_MANIFEST_33cc635.json` |
| `d18847f9e7c18fcfae3349c0b223b023d359a838` | BUILD r9, этап 4 (код `e82214e`); дополнительный прогон | `inputs/BUILD_MANIFEST_d18847f.json` |

Все три получены байтовыми копиями (`scripts/pin_build.py`). Код BUILD прочитан до запуска: чистые модули без I/O.

## Этап 1 — ГОТОВ: r8 против настоящего plan.js d865dd4

**Сверка 6064 задач — 0 расхождений.** Задачи: 34 задачи слепой проверки r8 и вся сетка r8 (v1 2610 + v2 3420). Совпало:
- статусы и причины infeasible;
- feasible_count;
- три победителя;
- Парето;
- чувствительность к бюджету;
- 18 787 вызовов evaluatePlan (метрики, допустимость, строки по точкам).

**Различия API** — 14 пунктов, ни одно не меняет числа; описаны в `API_DIFF.md`.

**Время BUILD** (Node, 16 кандидатов, max_selected = 3): 1.6–1.9 мс.

**Файлы этапа:**
- адаптер `adapter/build_plan_adapter.cjs`;
- скрипты `scripts/make_build_tasks.py`, `scripts/compare_build.py`;
- результаты `results/stage1/`.

## Этап 2 — ГОТОВ: протокол T3 предрегистрирован (`f6ac93c`, до прогона)

**Протокол** — `T3_PROTOCOL.md`, `config/t3_config.json`, `config/t3_attribute_sets.json`:
- 1340 задач;
- семейства исключений single, pair, cluster (k = 1/3/7), attribute (Overture confidence < 0.5; QA BUILD), all_disabled;
- размеры S, M, L до 12×25; бюджеты 0.5 и 1.0;
- stress 12×25×8, max_selected = 5.

**Оракул** `k09res/resilience.py` — независимая реализация CORE_SPEC r9:
- строгий envelope;
- предел до предвычислений;
- baseline и строки по каждому случаю;
- nominal и robust, W и worst_case_ids, цена;
- digest задачи, сценария и исключений.

## Этап 3 — ГОТОВ: эксперимент и интеграция с BUILD r9

**Эксперимент:** `scripts/run_t3.py` → `results/stage3/` (`t3_runs.csv`, `t3_summary.json`, `t3_timing.json`). Таблицы — `results/stage3/t3_tables.md`, итоги — **`T3_RESULTS.md`**:
- устойчивый план совпадает с обычным в 67.1% задач (кластерный 95% ДИ по 20 геометриям: 63.1–71.2%);
- случайные семейства — 74.5%, attribute — 59.2%, «все записи исключены» — 8.3%;
- цена устойчивости равна 0 в 75.8% задач; p90 9.3 м; максимум 84.7 м;
- больше случаев — реже совпадение. Sign-flip по геометриям: p 0.003–0.04 для k = 1 против k = 7.

**Интеграция:**
- BUILD resilience.js @ 33cc635 и @ d18847f против оракула K09 на 1340 задачах — **0 расхождений**, включая строки по точкам в каждом случае;
- слепая JS-реализация по одному тексту CORE_SPEC — **0 расхождений**.

**Валидация.** 60 входов: 0 настоящих расхождений; 4 различия политики, где BUILD строже.

**Находки по BUILD** — `BUILD_FINDINGS.md`:
- F1 medium — обход пределов через getter или Proxy в прямом JS API;
- F2 — U+FFFD в метке ломает круг экспорт→импорт;
- F3 — нет защиты объяснения от устаревшего результата;
- F4 — selectedIds не проверяется;
- F5 — невидимые и bidi-символы в метке.

Все воспроизведены на 33cc635 и d18847f.

**Патч** `patches/build_33cc635_k09.patch`:
- применяется к обоим SHA;
- регрессия `patches/test_build_r9_patch.cjs`: 14 FAIL до патча → 17/17 PASS после;
- тесты BUILD resilience, plan и whatif после патча проходят;
- T3 после патча — 0 расхождений.

**Независимая проверка** — workflow `wf_6017987f-133`, 3 агента, аудит путей чистый. Результаты в `results/stage3/independent/`. 10 замечаний обзора оракула учтены — см. `T3_RESULTS.md` §6.

## Команды и PASS / FAIL / SKIP / NOT_RUN

Все команды — из `research/round-9-results/K09`.

| Команда | Результат |
|---|---|
| `python3 -m unittest discover -s tests` | **PASS** 21/21 (Python 3.11.15) |
| `python3 scripts/pin_build.py --sha <SHA> --out <tmp>` | 3 SHA закреплены |
| `make_build_tasks.py` → `node adapter/build_plan_adapter.cjs` → `compare_build.py` | **PASS**: d865dd4, 6064 задачи, 0 расхождений |
| `python3 scripts/run_t3.py` | **PASS**: 1340 задач, инварианты, детерминированные sha256 в `results/stage3/DETERMINISTIC_SHA256.txt` |
| `run_t3.py --emit-envelopes` → `node adapter/build_resilience_adapter.cjs --repeats 3` → `compare_t3_build.py` | **PASS**: 33cc635 и d18847f, 0 расхождений |
| `compare_t3_build.py ... --oracle <blind out.jsonl>` | **PASS**: слепая JS, 0 расхождений |
| `validation_conformance.py make` → `adapter --validate` → `validation_conformance.py compare` | **PASS**: 0 DISAGREE (54 / 2 / 4) |
| `node patches/test_build_r9_patch.cjs <web>` | **FAIL** на 33cc635 и d18847f (14 — находки BUILD воспроизводятся); **PASS** 17/17 с патчем |
| Тесты BUILD `tests/resilience.cjs`, `plan.cjs`, `whatif.cjs` | **PASS** на обоих SHA, с патчем и без |
| `python3 scripts/t3_tables.py` | таблицы сгенерированы |

**SKIP:**
- браузер, UI-панель устойчивости и smoke-тесты BUILD (проверяли BUILD, K07 и K12);
- check_all.py BUILD с патчем;
- время в браузере и Web Worker;
- Windows.

**NOT_RUN:** нет. Интеграция с r9 BUILD выполнена на явно закреплённых SHA.

**Окружение:** Python 3.11.15, Node v22.22.0, linux x64, 4 CPU. Сеть не использовалась.

## Минимальные воспроизведения

```
# T3 через BUILD (замените <web> на копию BUILD)
python3 scripts/run_t3.py --emit-envelopes /tmp/env.jsonl
node adapter/build_resilience_adapter.cjs --web <web> --in /tmp/env.jsonl --out /tmp/b.jsonl
python3 scripts/compare_t3_build.py /tmp/env.jsonl /tmp/b.jsonl /tmp/cmp.json          # exit 0 — 0 расхождений

# Находки BUILD
node patches/test_build_r9_patch.cjs <web>                                            # 14 FAIL без патча
```

## Ограничения

- **Данные.** Точки, веса, кандидаты, стоимости и исключения — synthetic/hypothetical. Исходные записи — observed_secondary (Overture).
- **Смысл частот.** Частоты — свойства метода на синтетических задачах. Это не вероятности городских событий.
- **Статистика.** Независимых геометрий 20, поэтому выводы — по кластерному анализу. Предрегистрированные Wilson и McNemar завышают уверенность и приведены как описательные.
- **Происхождение реализаций.** BUILD, оракул K09 и слепая JS-реализация написаны моделями одного семейства по одной спецификации.
- **Время.** Замер на одной машине; браузер не измерялся.
- **Патч.** Применять его или нет — решение BUILD; общий прототип K09 не менял.

## Следующий шаг

1. BUILD решает по `BUILD_FINDINGS.md`: применить патч или исправить F1, F2, F4, F5 иначе. Затем прогнать `patches/test_build_r9_patch.cjs` и T3-сверку на новом SHA.
2. Для диплома — T3 с вложенными наборами случаев (одна последовательность из 7 случаев, первые k) и больше seeds: 20 геометрий дают широкие интервалы.
3. Добавить в CORE_SPEC стоимостную сторону цены устойчивости — §4 T3_RESULTS.
