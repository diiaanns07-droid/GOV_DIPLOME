# K10, раунд 9 — передача: демо-сценарии двух городов, регрессия, city-resilience-v1

**Слот:** K10, ветка `claude/save-work-handoff-j7pc05`. Задание: `research/round-9/tasks/K10.txt` @ `0ab1667`.

**Все три этапа выполнены.** Общий прототип, main и чужие ветки не менялись. Все выходы лежат в `research/round-9-results/K10/` и `research/handoffs/shared/K10/round-9/STATUS.md`.

## Проверенные сборки (`claude/beautiful-clarke-sbzomj`, извлечение из git побайтно)

| SHA | Что это | `regress.py` |
|---|---|---|
| `d865dd4a124291e10dd0b7bb1d9eada20d34c268` | база раунда, `resilience.js` нет | всё PASS; BUILD_RESILIENCE **NOT_RUN** |
| `33cc635ec212e522b3e17fb0b598fad0ad602f71` | BUILD r9 stage 2: модуль `resilience.js`, панели нет | всё PASS; BUILD_RESILIENCE_UI NOT_RUN |
| `e1cbc3fa84518a84698c03d014dc153f71338d54` | BUILD r9 stage 3: панель «Устойчивость к допущениям»; последняя на момент проверки | всё PASS, включая импорт в настоящем UI (103/103) |

Обе сборки r9 (`33cc635` и `e1cbc3f`) опубликованы во время работы. Каждая проверена на явно записанном SHA.

## Одна команда для нового SHA

```bash
python3 research/round-9-results/K10/regress.py --sha <BUILD sha>     # из корня репозитория; нужны git, python3, node
```

Итог пишется в `results/<sha7>/summary.json`. Ожидания никогда не пересоздаются из BUILD.

| Шаг | Что проверяет |
|---|---|
| EXTRACT | Побайтная копия `prototypes/city-evidence` с пересчётом git blob id; манифест в `extract_manifest.json` |
| FROZEN_PACKS | 161 файл пакетов r8 побайтно равен `frozen/r8_packs.json` (коммит `c8df74b`) |
| SOURCE_HASHES | sha256 двух `places_social.geojson` и `package_manifest.json` равны значениям пакета K10 (git `602f0c0`); `data.js` ссылается на те же sha256 |
| SOURCE_IDS | `data.js`: те же ID и группы, что в пакете K10; lon/lat = значения пакета, округлённые до 6 знаков. Шымкент 55 записей, Астана 65 |
| R8_SUITE | 37 пакетов v2 r8: данные, пересчёт оракулом, JS-геометрия, тесты, `verify-inputs`, `plan.js`, круг экспорта, мутанты `plan.js` |
| R9_ENVELOPES | 19 пакетов устойчивости против данных сборки (`check_envelopes.py`) |
| R9_PROPOSAL_ON_PLAN_JS | Предложение K10 `proposals/resilience.js` поверх `plan.js` этой сборки |
| BUILD_RESILIENCE | Собственный `web/resilience.js` сборки на 19 пакетах. Плюс её экспорты, перепроверенные оракулом K10, и мутации её модуля. NOT_RUN, если модуля нет |
| BUILD_RESILIENCE_UI | Chromium (Playwright), страница `file://`. 10 реальных конвертов загружаются кнопкой «Загрузить» панели, запускается «Сравнить три плана», результат и отображение сверяются с оракулом K10. Неверные файлы должны отклоняться без изменения состояния. NOT_RUN, если панели нет |

Время прогона: около 17 с на d865dd4, 24 с на 33cc635, 46 с на e1cbc3f.

## Этап 2: конверты `city-resilience-v1` на реальных срезах

```bash
cd research/round-9-results/K10
python3 -m k10res.envelopes --app-root <сборка>/prototypes/city-evidence --commit d865dd4a124291e10dd0b7bb1d9eada20d34c268 --out envelopes
python3 tests/check_envelopes.py --app-root <сборка>/prototypes/city-evidence
```

- **Подлинное:** ID, имена и координаты исходных записей, QA-флаги, bbox, snapshot (формат `plan.js`), sha256 файлов. Повторно ничего не скачивалось.
- **SYNTHETIC:** контрольные точки, веса, кандидаты, стоимости (условные единицы, не тенге), бюджет, `max_selected`, радиус. План взят из базового пакета r8.
- **Выбор исключаемых записей** — по правилам, заданным до расчёта (`RULES`, копия в каждом пакете):
  - `relied` — записи, ближайшие к наибольшему весу точек: случаи top1, top2, second;
  - `seeded` — LCG, seed 20261006 + индекс (+1000·K для случая sK), 1–3 записи;
  - `qa` — только Шымкент: все записи с QA-флагом и крупнейшая группа с одинаковыми координатами.
- **Подпись каждого пакета:** «Условно исключаем из расчёта; это не подтверждение закрытия».

| Конверт | Обычный | Устойчивый | Совпали | Цена, м |
|---|---|---|---|---|
| `astana-outpatient_clinic-relied` | c03+c10+c12 | c07+c09+c12 | нет | 10.585 |
| `astana-outpatient_clinic-seeded` | c03+c10+c12 | c07+c10+c12 | нет | 9.264 |
| `astana-school-relied`, `-seeded` | c03+c07+c12 | = | да | 0 |
| `shymkent-school-relied`, `-seeded`, `-qa` | c01+c03+c07 | = | да | 0 |
| `shymkent-outpatient_clinic-relied`, `-seeded`, `-qa` | c02+c03+c12 | = | да | 0 |

Устойчивый план отличается только у поликлиник Астаны. Это вышло само; ни правила, ни seed не подбирались. Для Астаны QA-конвертов нет: у её школ и поликлиник нет QA-флагов (`envelopes/INDEX.json → not_built`).

## Этап 3: синтетические крайние случаи и отказы

Каждый синтетический пакет сверяется с ручным расчётом (`design.hand_expectation`). Генерация останавливается, если оракул ответил иначе.

| Пакет | Что показывает |
|---|---|
| `synthetic-robust-differs` | Обычный A опирается на запись S, устойчивый B; цена 333.333 м |
| `synthetic-plans-coincide` | Исключённая запись никому не ближайшая; планы совпали, цена 0, худшие случаи — оба (ничья) |
| `synthetic-all-sources-left-out` | Исключены все школы плюс случай-дубль. У пустого плана W = (2, 0, null). Устойчивый L+M при цене 0 м: дороже, среднее на base то же. BUILD сообщает дубль в `duplicate_case_groups` |
| `synthetic-infeasible-budget` | Обязательный кандидат дороже бюджета: `infeasible`, цена null с причиной, ручной план недопустим |
| `synthetic-unknown-worst` | `max_selected` 0: худший случай остаётся неизвестным и показан как неизвестный, а не 0 |
| `synthetic-robust-tiebreak` | Одинаковый W: решает потеря на base, а не меньшая стоимость |
| `synthetic-unknown-base-refused` | Пустая категория: ни один случай не может назвать запись, поэтому отказ |
| `shymkent-school-invalid-envelopes`, `astana-school-invalid-envelopes` | По 34 случая: 29 отказов с кодом, записанным до расчёта, 5 «принять» |

Случаи «принять»: кириллический NFC id, метка ровно 120 символов, HTML в метке как текст, два случая с одинаковым набором, исключение всех записей категории.

**Честный статус «неизвестной базы».** В корректном конверте случай `base` всегда содержит хотя бы одну запись: каждый пользовательский случай обязан назвать существующую запись категории. Поэтому «до» на base всегда известно, и цена устойчивости бывает null только при `infeasible`. Пустую категорию K10 проверяет как отказ.

## Модули и API (K10)

### `k10res/oracle_res.py` — независимый оракул устойчивости

Геометрия, строгий JSON и правила плана v2 берутся из оракула K10 r8. Слой устойчивости написан по `round-9/CORE_SPEC.txt`, не переведён из кода BUILD.

- `validate_resilience(obj, ctx)` возвращает чистый конверт: первым идёт автоматический `base`, остальные случаи отсортированы по id. При ошибке — `ResError(code)`.
- `evaluate_resilience(ctx, env, ids)` возвращает:
  - `per_case[]`: метрики, `loss` и строки before/after/delta/nearest внутри случая;
  - `worst_vector`, `worst_case_ids`, `feasibility`.
- `optimize_resilience(ctx, env)` возвращает:
  - `status`, `manual`, `nominal`, `robust`, `plans_identical`;
  - `price_of_robustness_m`, `price_reason`;
  - `evaluated`, `feasible_count`;
  - `resilience_problem_digest`, `resilience_scenario_digest`, `exclusions_digest`, `source_snapshot`.

Порядок сравнения:

- L = (unknown, sum, max); null-max считается +∞ только внутри сравнения.
- W = лексикографический максимум L по всем случаям.
- Обычный план — минимум (L_base, cost, ids).
- Устойчивый план — минимум (W, L_base, cost, ids).

### Генераторы

- `k10res/envelopes.py` — реальные пакеты.
- `k10res/edgecases.py` — синтетика и отказы. `context_of(pack)` и `run_case(pack, case)` — для проверок.

### `proposals/resilience.js` — предложение для BUILD, не часть сборки

Тонкий слой поверх `plan.js` с API из CORE_SPEC: `validateResilience`, `evaluateResilience`, `createResilienceSearch`, `optimizeResilience`. Независимая вторая JS-реализация. BUILD написал свою, поэтому предложение остаётся эталоном для перекрёстной проверки.

### Проверки

| Скрипт | Что делает |
|---|---|
| `tests/check_envelopes.py` | SOURCE, VALID, RECOMPUTE, ORDER, CROSS_R8 (по каждому случаю оракул r8 на копии среза без исключённых записей + полный перебор устойчивого оптимума), HAND, INDEX, IMMUTABLE |
| `tests/run_build_resilience.cjs` | Пакеты через `web/resilience.js` сборки; сравнение по смыслу и по id случая |
| `tests/run_res_adapter.cjs` | Пакеты через предложение K10 на `plan.js` сборки |
| `tests/run_build_res_mutants.py`, `tests/run_adapter_mutants.py`, `tests/run_res_mutants.py` | Ловят ли пакеты и тесты внесённые ошибки правил |
| `tests/test_res_oracle.py` (13), `tests/test_regress.py` (5) | unit-тесты |

## Результаты (фактические прогоны, файлы в `results/`)

| Проверка | d865dd4 | 33cc635 | e1cbc3f |
|---|---|---|---|
| `regress.py`: EXTRACT, FROZEN_PACKS, SOURCE_HASHES, SOURCE_IDS, R8_SUITE (6 подшагов) | PASS | PASS | PASS |
| R9_ENVELOPES (19 пакетов) | PASS | PASS | PASS |
| Предложение K10 на `plan.js` (19 пакетов) | PASS; мутанты 16/16 | PASS | PASS |
| `resilience.js` BUILD: 19 пакетов | NOT_RUN (нет модуля) | PASS | PASS |
| `resilience.js` BUILD: экспорт ↔ импорт | NOT_RUN | 10/10 | 10/10 |
| `resilience.js` BUILD: экспорты BUILD → оракул K10 | NOT_RUN | 10/10, тот же результат | 10/10 |
| `resilience.js` BUILD: мутанты | NOT_RUN | 18/18 | 18/18 |
| UI устойчивости: импорт, расчёт и показ в браузере | NOT_RUN | NOT_RUN (панели нет) | PASS 103/103 |
| unit: `test_res_oracle` + `test_regress` (от сборки не зависят) | 18 OK | — | — |
| мутанты оракула K10 (от сборки не зависят) | 17/17 | — | — |

**Что проверяет UI-тест на e1cbc3f (`tests/ui_import.cjs`, `results/e1cbc3f/ui_import.json`):**

- Каждый из 10 реальных конвертов: после импорта совпадают город, категория, случаи (id, метки, исключённые ID) и ручной план. Результат страницы (обычный и устойчивый план, худшие векторы и случаи, цена, `same_plan`, `feasible_count`) равен оракулу K10.
- На странице 3 карточки, столько строк, сколько случаев, правильное число отметок ▲, цена в формате страницы (например «+10,6 м») и предупреждение «не подтверждение закрытия».
- 2×34 файла ввода: отказы с сообщением «не принят» и без изменения случаев, плана и города; принятые файлы загружаются. Метка с `<img …>` показана буквально: элемент не создаётся.
- Исходные записи не меняются, ошибок страницы нет, сетевых запросов нет.
- **Отрицательный контроль:** копия сборки с подменённым правилом устойчивого плана даёт 4 FAIL.

### Расхождения с BUILD 33cc635

Это не ошибки: смысл совпадает, отличаются только названия кодов или строгость.

- **Коды ошибок** называются иначе: `bad_json` вместо `duplicate_key`/`non_finite`, `unknown_field`, `wrong_version`, `bad_cases`, `reserved_id`, `duplicate_id`, `bad_exclusions`, `candidate_not_source`, `unknown_source`. Отказ/принятие совпали во всех 70 случаях.
- **17 кандидатов:** BUILD проверяет лимит 12 до валидации v2 (`too_many_candidates`), K10 — после (`bad_candidate_count`). Оба отказывают до расчёта.
- **Метки:** BUILD дополнительно отклоняет U+2028/U+2029 (разделители строк) — строже K10, который отклоняет категорию Cc. В пакетах этого случая нет, спецификация его прямо не называет.
- **Порядок:** BUILD выдаёт случаи в порядке ввода, K10 сортирует. `worst_case_ids` у обоих отсортированы. Дайджесты независимы и побайтно не сравниваются (так требует CORE_SPEC).

## Ограничения

- Все конверты — анализ допущений о данных. Это не прогноз закрытия, риска, нагрузки или потребностей жителей. QA-флаг — повод проверить запись, а не доказанная ошибка.
- Оптимум — только среди введённых кандидатов. Расстояния — по прямой до записей среза Overture `2026-09-23.1`, который неполон.
- Мутации показывают, что пакеты ловят перечисленные ошибки, а не отсутствие всех ошибок.
- Строковые сравнения: Python сортирует по кодовым точкам, JS — по UTF-16. Для ID из BMP порядок одинаков; для символов вне BMP может отличаться. В пакетах таких ID нет.
- Новая сборка BUILD требует нового прогона `regress.py --sha <sha>`. Результат здесь относится только к двум перечисленным SHA.
