# K10, раунд 8: пакеты сценариев city-plan-v2 на двух реальных срезах — передача

**Слот:** K10, ветка `claude/save-work-handoff-j7pc05`. Задание: `research/round-8/tasks/K10.txt` @ `c3f6c00`.

**Все три этапа выполнены** (см. `STATUS.md`). Общий прототип не изменялся. Все выходы лежат в `research/round-8-results/K10/`.

**Проверенные сборки BUILD** (`claude/beautiful-clarke-sbzomj`, извлечены из git байтами):

| Сборка | Что это | Результат |
|---|---|---|
| `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d` | база раунда, `plan.js` нет | данные, оракул, CLI — PASS; модуль v2 — SKIP |
| `60f44d93c691c2feaa2a67e6660c55ea9677b5b2` | BUILD r8 stage 2 | всё PASS; экспорта ещё нет |
| `d865dd4a124291e10dd0b7bb1d9eada20d34c268` | BUILD r8 stage 4, последняя на момент проверки | всё PASS, включая импорт и экспорт файлов |

Проверялись только функции `web/plan.js` без DOM. Интерфейс в браузере в этом раунде не проверялся.

## Состав

| Путь | Назначение |
|---|---|
| `k10plan/oracle.py` | Независимый Python-оракул по `CORE_SPEC.txt`, только stdlib; не перевод JS |
| `k10plan/slice.py` | Чтение реального среза из app root (только чтение), `source_snapshot` как в BUILD, манифест входов |
| `k10plan/packs.py` | Генератор пакетов по правилам `RULES`, заданным до расчёта; ожидаемое — только из оракула |
| `k10plan/cli.py` | Предпросмотр, запуск файла сценария, экспорт неверного файла, проверка неизменности входов |
| `packs/*.json` | 37 пакетов (формат `k10-plan-pack-v1`) |
| `packs/scenarios/*.json` | Чистые входы `city-plan-v2` для импорта, 35 файлов |
| `packs/scenarios/invalid/<pack>/*.json` | Неверные файлы. `too_large` создаётся командой `export-case` |
| `packs/INDEX.json` | Список, sha256, правила, `not_built`, манифест входов |
| `tests/test_oracle.py` | 23 теста оракула на ручной синтетике |
| `tests/test_cli.py` | 10 тестов CLI; 3 из них только с `K10_APP_ROOT` |
| `tests/check_packs.py` | Проверки SOURCE / VALID / ORDER / HAND / RECOMPUTE / INDEX / JS / IMMUTABLE |
| `tests/xcheck_build.cjs` | Миллиметры и отпечаток, посчитанные JS самой сборки |
| `tests/run_build_v2.cjs` | Прогон пакетов через `web/plan.js` сборки |
| `tests/run_mutants.py`, `tests/run_build_mutants.py` | Ловят ли тесты и пакеты внесённые ошибки правил: оракул 13/13, `plan.js` 15/15 |
| `tests/run_build_suite.py` | Все проверки против одной сборки → `results/<sha7>/summary.json` |
| `results/a5b5e2d/`, `results/60f44d9/`, `results/d865dd4/` | Фактические прогоны |
| `results/mutants.json` | Мутанты оракула |
| `results/preview/` | Текстовые предпросмотры всех пакетов и два HTML |

## API

### Python: `k10plan.oracle`

Вход и выход — JSON-совместимые dict.

- `parse_strict(text|bytes)` отклоняет:
  - больше 256 KiB (`too_large`);
  - повтор ключа (`duplicate_key`);
  - `NaN`, `±Infinity`, `1e999`, целое за пределами double (`non_finite`);
  - мусор после JSON (`bad_json`).
- `validate_plan_scenario(obj, context)` возвращает нормализованный сценарий: списки ID отсортированы, `derived_results` отброшен. При ошибке — `PlanError(code, detail)`:
  - коды формы: `missing_field`, `unexpected_field`, `bad_shape`, `bad_schema_version`;
  - город, срез и категория: `bad_city`, `foreign_snapshot`, `bad_category`;
  - координаты: `out_of_bbox`, `bad_coordinate`;
  - количество и ID: `bad_point_count`, `bad_candidate_count`, `duplicate_id`, `bad_id`, `unknown_candidate`;
  - значения и кандидаты: `bad_value`, `candidate_category_mismatch`, `candidate_not_hypothetical`, `required_excluded_overlap`.
- `context = {city_id, bbox, source_snapshot, records:[{id, lon, lat, group, ...}]}`. Флаг `synthetic: True` разрешает синтетический `city_id`.
- `evaluate_plan(context, scenario, selected_ids)` возвращает:
  - `rows[]`: `control_point_id`, `weight`, `before_mm`, `nearest_before{kind:"source", id}`, `after_mm`, `nearest_after{kind, id}`, `delta_mm`;
  - `metrics`: `unknown_count`, `weighted_sum_mm`, `weighted_mean_mm`, `max_mm`, `covered_weight`, `coverage_fraction`, `cost`, `selected_ids`;
  - `feasibility{feasible, reasons}`;
  - `baseline_records_in_category`.
- `optimize_plans(context, scenario, {sensitivity: bool})` возвращает:
  - `status`: `optimal` или `infeasible`;
  - `metric_version`, `problem_digest`;
  - `evaluated`: подмножества в пределах `max_selected`, с учётом required и excluded;
  - `feasible_count`, `objectives{mean, minimax, coverage}`;
  - `pareto[{cost, weighted_sum_mm, selected_ids}]`, `pareto_note`;
  - `infeasible_reasons`, `sensitivity[{budget, status, objectives, infeasible_reasons}]`.
- `problem_digest(sc)` и `scenario_digest(sc)` не зависят от порядка массивов. `selected_ids` входят только в `scenario_digest`.

### Python: `k10plan.slice`

- `load_context(app_root, city)` возвращает контекст оракула с QA-флагами из `web/evidence.js`.
- `source_snapshot(city, city_data, fmt)`:
  - `plan-v2` (по умолчанию) — как `web/plan.js` с 60f44d9;
  - `whatif-v1` — как `web/whatif.js`.
- `input_manifest(app_root)`: файлы данных (`DATA_FILES`) и кода (`CODE_FILES`, справочно).

### Формат пакета

Общие поля:

- `scenario` — вход v2;
- `expected` — результат оракула:
  - `optimize`;
  - `plans`: оценка ручного плана, пустого плана и победителей; одинаковые наборы хранятся один раз, а `plan_refs` ссылается на них;
- `observations` — совпали ли цели и сколько разных наборов;
- `rules` — правила, по которым построены точки и кандидаты.

Реальные пакеты дополнительно содержат:

- `provenance`: сборка, sha256 файлов, release, bbox, компоненты отпечатка, отпечаток v1 того же среза;
- `source_copy`: копия записей категории только для чтения, с QA-флагами.

Синтетические пакеты дополнительно содержат:

- `synthetic_slice`;
- `design.hand_expectation` — ручной расчёт, который сверяется с оракулом.

Пакеты неверного ввода дополнительно содержат `invalid_cases[{case_id, raw, expected, note, pad_to_bytes?}]`.

## Пакеты: что получилось

Колонка «Перебрано / допустимо»: сколько наборов перебрал K10 и сколько из них проходят бюджет. BUILD считает перебранные наборы иначе (2^свободных), поэтому сравнивается только «допустимо».

| Пакет | Статус | Перебрано / допустимо | Победители | Цели совпали | Точек Парето |
|---|---|---|---|---|---|
| `shymkent-school-base` | optimal | 299/143 | все три: c01+c03+c07 | да | 7 |
| `shymkent-school-zero-budget` | optimal | 299/1 | все три: пусто | да | 1 |
| `shymkent-school-tight-budget` | optimal | 299/2 | все три: c07 | да | 2 |
| `shymkent-school-required-excluded` | optimal | 37/12 | mean, minimax c02+c10+c12; coverage c04+c12 | нет | 4 |
| `shymkent-school-seeded` | optimal | 1471/371 | все три: r09+r12+r14 | да | 7 |
| `shymkent-school-qa-nearest` | optimal | 299/143 | все три: c01+c03+c07; cp_qa1 — ничья 3 школ, ближайшая «Reklama 8888» `CATEGORY_DOUBT,COLOCATED` | да | 7 |
| `shymkent-outpatient_clinic-base` | optimal | 299/143 | mean, minimax c02+c03+c12; coverage c01+c12 | нет | 10 |
| `shymkent-outpatient_clinic-zero-budget` | optimal | 299/1 | пусто | да | 1 |
| `shymkent-outpatient_clinic-tight-budget` | optimal | 299/2 | пусто: единственный доступный c07 нигде не ближе существующих | да | 1 |
| `shymkent-outpatient_clinic-required-excluded` | optimal | 46/16 | все три: c01+c12 | да | 4 |
| `shymkent-outpatient_clinic-seeded` | optimal | 1471/682 | все три: r04+r06+r11+r14 | да | 13 |
| `shymkent-outpatient_clinic-qa-nearest` | optimal | 299/143 | как base; cp_qa1 — ничья 4 поликлиник `COLOCATED` | нет | 10 |
| `astana-school-base` | optimal | 299/143 | mean c03+c07+c12; minimax c11+c12; coverage c02+c07+c12 | нет, 3 набора | 6 |
| `astana-school-zero-budget` | optimal | 299/1 | пусто | да | 1 |
| `astana-school-tight-budget` | optimal | 299/2 | c07 | да | 2 |
| `astana-school-required-excluded` | optimal | 46/13 | mean, minimax c11+c12; coverage c08+c12 | нет | 5 |
| `astana-school-seeded` | optimal | 1471/537 | 3 разных набора | нет | 14 |
| `astana-outpatient_clinic-base` | optimal | 299/143 | mean c03+c10+c12; minimax, coverage c08+c12 | нет | 9 |
| `astana-outpatient_clinic-zero-budget` | optimal | 299/1 | пусто | да | 1 |
| `astana-outpatient_clinic-tight-budget` | optimal | 299/2 | c07 | да | 2 |
| `astana-outpatient_clinic-required-excluded` | optimal | 46/14 | mean c01+c12; minimax, coverage c08+c12 | нет | 5 |
| `astana-outpatient_clinic-seeded` | optimal | 1471/259 | mean, minimax r03+r04+r08+r11; coverage r01+r04+r11 | нет | 13 |
| `*-conflict-budget` (4) | infeasible | 11/0 | `required_cost_exceeds_budget` | — | 0 |
| `*-conflict-count` (4) | infeasible | 0/0 | `required_count_exceeds_max_selected` | — | 0 |
| `shymkent-school-invalid-inputs`, `astana-school-invalid-inputs` | — | — | 45 случаев: 43 отказа, 2 принять (`derived_results_forged`, `html_in_ids`) | — | — |
| `synthetic-objectives-differ` | optimal | 5/5 | mean e, minimax c, coverage b (задумано вручную) | нет | 4 |
| `synthetic-empty-baseline` | optimal | 37/36 | mean, minimax k1+k4; coverage k1+k5 (разница среднего 0,1 мм) | нет | 8 |
| `synthetic-ties` | optimal | 4/4 | t1; источник выигрывает ничью у `a0`; точка ровно на радиусе покрыта | да | 2 |
| `synthetic-mean-tiebreak` | optimal | 3/3 | mean, minimax B; coverage A; B не на Парето | нет | 2 |
| `synthetic-minimax-tiebreak` | optimal | 4/4 | X+Y | да | 3 |

Совпадение или расхождение целей на реальных срезах получилось само: правила и seed заданы до расчёта и не подбирались.

**Не построено:** QA-пакеты для Астаны. В `web/evidence.js` нет групп `colocated` со школами или поликлиниками; флаги есть только у госучреждений и вузов (`INDEX.json → not_built`).

## Правила и seed (`packs.py → RULES`, копия в каждом пакете)

- **Контрольные точки** — сетка 4×4 по долям bbox, точки cp01..cp16. Вес точки k равен `1 + (3k mod 5)`.
- **Кандидаты** — c01..c12, x ∈ {1/8, 3/8, 5/8, 7/8}, y ∈ {1/6, 1/2, 5/6}. Стоимость кандидата k равна `100 + 50·(5k mod 7)`.
- **Base:** бюджет 700, `max_selected` 3, радиус 400 м, ручной план c06+c07.
- **Варианты:**
  - `zero-budget`: бюджет 0;
  - `tight-budget`: бюджет = минимальная стоимость кандидата;
  - `required-excluded`: обязателен c12, исключён победитель mean из base;
  - `conflict-budget`: два самых дорогих кандидата обязательны, бюджет = их сумма − 1;
  - `conflict-count`: обязательны c01..c04 при `max_selected` 3;
  - QA: дополнительная точка на каждой группе `colocated`.
- **Seeded:** LCG `x = (1103515245·x + 12345) mod 2^31`, seed = `20261005 + i`, где i — порядок пар shymkent/school, shymkent/outpatient_clinic, astana/school, astana/outpatient_clinic. Генерируются 20 точек и 14 кандидатов, бюджет 900, `max_selected` 4, радиус 300 м.
  - В JS: 1103515245·x превышает 2^53, поэтому нужен BigInt.
- **Неверный ввод:** нужный код записан до расчёта. Если оракул ответил иначе, генерация останавливается.

## Команды

```bash
# 1. сборка из git байтами (из корня репозитория)
python3 research/round-5-results/K10/tools/extract_build.py --sha d865dd4 --out /tmp/b
cd research/round-8-results/K10
# 2. пакеты (детерминированно; повторная генерация даёт те же файлы)
python3 -m k10plan.packs --app-root /tmp/b/prototypes/city-evidence --commit a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d --out packs
# 3. все проверки против одной сборки -> results/<sha7>/summary.json
python3 tests/run_build_suite.py --app-root /tmp/b/prototypes/city-evidence --commit $(git rev-parse d865dd4)
# по отдельности
python3 tests/check_packs.py --app-root /tmp/b/prototypes/city-evidence
K10_APP_ROOT=/tmp/b/prototypes/city-evidence python3 -m unittest discover -s tests -p "test_*.py" -v
node tests/run_build_v2.cjs /tmp/b/prototypes/city-evidence packs/*-*.json
python3 tests/run_mutants.py --json results/mutants.json
# предпросмотр и файлы
python3 -m k10plan.cli preview packs/astana-school-base.json --app-root /tmp/b/prototypes/city-evidence [--plan minimax] [--format html --out x.html]
python3 -m k10plan.cli run packs/scenarios/astana-school-base.json --app-root /tmp/b/prototypes/city-evidence [--city astana]
python3 -m k10plan.cli export-case packs/shymkent-school-invalid-inputs.json too_large --out big.json
python3 -m k10plan.cli verify-inputs --app-root /tmp/b/prototypes/city-evidence --index packs/INDEX.json --git-sha d865dd4 --k10-package ../../round-3-results/K10
```

Пакеты генерировались из app root a5b5e2d. В 60f44d9 и d865dd4 `web/data.js` и `web/evidence.js` побайтно те же, проверено `verify-inputs` и git-блобами.

## Результаты (фактические прогоны, `results/<sha7>/summary.json`)

| Проверка | a5b5e2d | 60f44d9 | d865dd4 |
|---|---|---|---|
| `check_packs`: SOURCE, VALID, ORDER, HAND, RECOMPUTE, INDEX, JS, IMMUTABLE | PASS (37) | PASS (37) | PASS (37) |
| unit-тесты, 33 с app root | PASS | PASS | PASS |
| `verify-inputs`: данные = INDEX = git-блоб коммита = пакет K10 | PASS | PASS | PASS |
| `plan.js`: статус, цели с метриками, Парето, feasible_count, чувствительность, строки и метрики планов, порядок, дайджесты, прерванный поиск | SKIP (нет `plan.js`) | PASS (37) | PASS (37) |
| Экспорт BUILD → импорт BUILD; экспорт BUILD → оракул K10, тот же оптимум | SKIP | SKIP (нет экспорта) | PASS (30/30) |
| Мутанты `plan.js`: пакеты ловят внесённые ошибки | SKIP | 15/15 | 15/15 |
| Мутанты оракула (тесты K10) | 13/13 | | |

## Различия с BUILD (не ошибки, задокументированы в адаптере)

1. **Названия кодов** (`too_many`, `over_budget`, `required_exceeds_max_selected` и др.) у BUILD свои. Адаптер сравнивает смысл через таблицу соответствия.
2. **`evaluated`** считается по-разному (см. «Пакеты: что получилось»). Сравнивается `feasible_count`, он совпал везде.
3. **`html_in_ids`:** BUILD отклоняет ID с `< > = "` и пробелами (`bad_id`). Это строже, чем «до 64 символов» в спецификации. Оракул K10 такой ID принимает и требует показывать его как текст. CLI K10 экранирует его в HTML — тест `test_html_escapes_ids_and_names`.
4. **`derived_results_forged`:** BUILD d865dd4 отклоняет `derived_results`, не совпавшие с пересчётом (`forged_derived`). Оракул K10 их игнорирует. Оба варианта не доверяют файлу.
5. **Наблюдение (низкая важность):** шаблонное объяснение BUILD d865dd4 округляет до 0,01 км. На `synthetic-empty-baseline` оно пишет «среднее при этом 1,22 км → 1,22 км» для разных планов (разница 0,1 мм). Текст верен в пределах округления, но может читаться как «одинаково». Предпросмотр K10 пишет «длиннее на 0.1 мм».

## Источники и версии

- **Данные:** K10 round-3 package, Overture Maps places release `2026-09-23.1`, лицензии в `source_copy[].sources` и `web/data.js`. Повторно не скачивались.
  - Шымкент: `places_social.geojson` sha256 `e0959270…b003e7`.
  - Астана: `places_social.geojson` sha256 `f5722c44…00e343`.
- **source_snapshot** (`provenance.source_snapshot` и `provenance.whatif_v1_snapshot_same_slice` в каждом пакете):

  | Город | `plan-v2` (в пакетах) | `whatif-v1` того же среза |
  |---|---|---|
  | Шымкент | `sha256:a9326b56…d8d7ff3e` | `sha256:282cf187…81bd36ec2` |
  | Астана | `sha256:67a40b96…82f04c6d` | `sha256:2ad03235…be771c9d` |

  Python совпадает с `web/plan.js` (60f44d9, d865dd4) и `web/whatif.js` (все три сборки), проверено node.
- **Окружение:** Python 3.11.15, Node v22.22.0. Внешних зависимостей нет; Playwright использовался только для снимка HTML-предпросмотра.

## Ограничения (что пакеты не утверждают)

- **SYNTHETIC:** точки, веса, места кандидатов, стоимости (условные единицы, не тенге и не смета), бюджеты, `max_selected`, радиус. Пакеты `synthetic-*` — геометрия на экваторе, не данные городов. Население, вместимость и сметы не придумывались.
- **Оптимум** — только среди введённых кандидатов и условий. Расстояния — по прямой до записей среза Overture, который неполон. Ближайшая запись в срезе — не обязательно ближайшее учреждение города.
- **QA-флаг** — повод проверить запись, а не доказанная ошибка. Записи не удаляются и не меняются.
- **Интеграция с BUILD** проверена на функциях `plan.js` трёх перечисленных SHA, без браузера и UI. Новые коммиты BUILD нужно прогонять заново командой `run_build_suite.py`.
- **Мутации** доказывают только, что пакеты ловят перечисленные ошибки правил, а не отсутствие всех ошибок.
