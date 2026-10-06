# K05 round 9 — точный устойчивый поиск: STATUS (итог)

Ветка `claude/optimistic-davinci-1oiqs9`. Задание `research/round-9/tasks/K05.txt`, CORE_SPEC r9 @ codex/research-import-2026-10-05 (0ab1667). Мой r8: `1804f5b`.
**Проверенные сборки** (`claude/beautiful-clarke-sbzomj`, извлечены `git archive` во временный каталог; общий прототип не менялся):
- `d865dd4a124291e10dd0b7bb1d9eada20d34c268` — закреплённая база раунда (дерево = 3e1302a);
- `33cc635ec212e522b3e17fb0b598fad0ad602f71` — новый BUILD r9 этапа 2 (появился во время работы; свой `web/resilience.js` и исправление API-guard), проверен дополнительно, на явном SHA.

| Этап | Статус |
|---|---|
| 1. r8 oracle/fixtures против plan.js через адаптер; API-guard repro | **done** |
| 2. resilience.js поверх API BUILD | **done** (модуль K05 — независимая вторая реализация; у BUILD теперь своя) |
| 3. gold K06, ручные gold, свойства, перебор, benchmark, повторная проверка | **done** |

## Результаты (все реально запущены; Node v22.22.0, Python 3.11.15, Linux)
| Проверка | d865dd4 | 33cc635 |
|---|---|---|
| `stage1/adapter_r8_vs_build.cjs` — 28 задач r8 + 3 ручные (три оптимума, tie-break, пустой план) через plan.js BUILD | 31 PASS / 0 FAIL | 31 PASS / 0 FAIL |
| r8 Python-оракул на ответах plan.js BUILD | 28/28 | 28/28 |
| `stage1/repro_api_guard.cjs` (дочерние процессы, таймаут 8 с) | **FAIL продукта**: прямой `createSearch` без валидации — 2^20/2^22, 2^30 таймаут; мутация проверенного объекта обходит лимит | **исправлено BUILD**: все >16 → `too_many_candidates`, зависаний нет |
| plan.js + мой `plan_api_guard.patch` (копия d865dd4): repro / `tests/plan.cjs` / `whatif.cjs` / `conformance.cjs` / браузер `plan_smoke.cjs` | исправлено / passed / passed / passed / 52 PASS (как без patch) | — (BUILD исправил сам, эквивалентно: публичные точки входа валидируют, `PL.internal` для проверенного пути) |
| K06 gold (62 задачи: 59 optimal + 3 infeasible, 20 на реальных записях) против **resilience.js K05** | 62/62 PASS | — |
| K06 gold против **resilience.js BUILD** | NOT_RUN (модуля нет) | **62/62 PASS** |
| K06 must_reject (16) | K05: 16/16 отвергнуты, коды совпали 12 | BUILD: 16/16 отвергнуты, коды совпали 12 |
| `stage3/cross_build_vs_k05.cjs` — две независимые JS-реализации, 96 случайных конвертов (оба города/категории; 31 с robust≠nominal, 18 с несколькими худшими случаями) | — | **96/96** одинаковая математика (89 optimal, 7 infeasible) |
| `tests/test_resilience.cjs` (модуль K05, 17 тестов) | 17/0 | 17/0 |
| `tests/test_stage3.cjs` (модуль K05: 4 ручных gold, 8 сверок с перебором через PL.evaluatePlan, 5 свойств, benchmark) | 18/0 | 18/0 |
| Мутации модуля K05 против gold K06: покомпонентный max / только первый худший | 2 FAIL / 21 FAIL (пойманы) | — |

Benchmark модуля K05 (12 кандидатов × 25 точек × 8 случаев, ≤5): 4096 подмножеств, синхронно 11–20 мс, max async-чанк (256) ≤ 4,1 мс; `runs/benchmark_resilience_*.json`.

## Что отмечено как ошибки моего кода/тестов (не продукта), исправлены
- массивы из vm-realm в проверенной копии (валидатор теперь создаёт новый массив);
- ручной gold 1: A помогал p1 в случае x — пример перестроен (модуль не менялся);
- адаптер формы для K06 перезаписывал цену BUILD на null — исправлен (`stage3/map_to_k06.py`);
- для plan.js ≥33cc635 модуль K05 использует `PL.internal.evaluate` (публичный `evaluatePlan` больше не принимает `pre`).

## API_POLICY (не математика)
Имена кодов при одинаковом решении: K06 `bad_disabled`/`unexpected_field`/`bad_case`/`out_of_range` ↔ BUILD/K05 `bad_exclusions`/`unknown_field`(K05)·`derived_not_allowed`/`bad_shape`(BUILD)/`bad_budget`. Поле цены: BUILD/K06 `price_of_robustness_m`, K05 `price_of_resilience_m`. Форма W: объект (BUILD/K05) ↔ массив (K06) — адаптер.

## Предложения (не применены к прототипу)
- `patches/plan_api_guard.patch` — для d865dd4; в 33cc635 BUILD сделал эквивалентное исправление → **устарел**.
- `patches/add_web_resilience_js.patch` — для d865dd4; в 33cc635 у BUILD свой `web/resilience.js` → **устарел**; модуль K05 полезен как независимая реализация для перекрёстной сверки.

## Ограничения
Точки, кандидаты, стоимости, веса и исключения — SYNTHETIC; реальные только записи срезов (observed_secondary, не реестр). Исключения — допущения о данных, не закрытие учреждений. UI вкладки «Устойчивость» и браузерный импорт BUILD 33cc635 мной не проверялись (NOT_RUN): проверены модули и математика.

## Команды
См. `HANDOFF.md`.
