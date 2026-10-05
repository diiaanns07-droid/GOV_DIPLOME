# K12, раунд 4, REVIEW: стресс-проверка missing и неполного учёта в модели данных K05

Слот K12, роль REVIEW. Ветка `claude/save-work-handoff-xuav3q`. Задание:
`research/round-4/review/K12.txt` @ `cadba4d`.

**Цель проверки:** модель `k05-obs-v1.1` из `claude/optimistic-davinci-1oiqs9` @ `d913554`:

- `research/round-3-results/K05/k05r3_contract.py`
- `research/round-3-results/K05/schema/k05-obs-v1.1.schema.json`
- `research/next-round/K05/k05_validator.py`

Код прочитан целиком до запуска. Все входы скопированы побайтно в `inputs/k05_d913554/`, sha256 — в
`MANIFEST.json`.

> **Все фикстуры синтетические.** `obs_id` начинаются с `SYNTHETIC-FIXTURE`, территории
> `kz.shymkent.fixture_*` не настоящие. `kind=observed` в части случаев нужен только для того,
> чтобы пройти по пути проверки измерений. Это не данные Шымкента или Астаны. Энергетика здесь не
> используется: местных энергопоказаний нет.

## Итог

- На `d913554` собственные тесты K05 проходят: 18 и 9, OK. Наш набор `FIXTURES.json` — 57 случаев.
- **Текущий код: 32 из 32 контролей совпали, 25 из 25 новых случаев — дефекты.** Работают как
  заявлено: `null ≠ 0`, явный `reported_zero`, ноль при неполном охвате, город и территория,
  единица из пробелов, тип значения, охват, смешение городов, периодов, единиц и видов данных в агрегате.
- **Исправленная копия:** 57 из 57. Это `patched/` = `d913554` +
  `patches/k05r3_contract_stress_fixes.patch`; меняется только `k05r3_contract.py`.
  - `git apply --check` на `d913554` — ok.
  - С patch проходят все 18 + 9 тестов K05.
  - Реальные примеры K05 обоих городов: 0 из 56 и 0 из 84 записей отклонено, ошибок набора нет.
  - Городские суммы прежние (56 и 114), но теперь с пометкой `geography_checked: false`.

## Дефекты (все воспроизводятся `stress_runner.py`, список закреплён тестом `test_defect_list_is_exact`)

| # | Случаи | Что происходит сейчас | Почему важно | Исправление в patch |
|---|---|---|---|---|
| 1 | R20–R23, A11 | `value` = NaN или ±Infinity при `reported` проходит jsonschema (`type: number`) и контракт. У `observed` нет **ни одного** предупреждения. `aggregate_sum` возвращает `value: NaN`, `reported`, `coverage_complete: true` | `dump()` адаптера пишет токен `NaN` (`json.dumps` по умолчанию), а `JSON.parse` в Node на нём падает с `SyntaxError`. Карта или страница не прочитает файл | `VALUE_NOT_FINITE` в `validate` и в `aggregate_sum` |
| 2 | J01–J05 | `json.loads` по умолчанию принимает `NaN`/`Infinity`. Строго валидный `1e999` даёт inf. При повторе ключа (`"value_status": "reported", …"missing"`) молча побеждает последний | Повтор ключа незаметно меняет смысл записи: число превращается в «нет данных» | `loads_strict()`: `JSON_NONFINITE`, `JSON_DUPLICATE_KEY` |
| 3 | A08, A09, A10 | Сумма «город целиком + его район» складывается (двойной счёт). Сумма 2 из 3 территорий выдаётся как полная (`n: 2/2`, `complete: true`). Полнота географии нигде не проверяется | Срез легко принять за город. **На реальных данных:** сумма K05 по Шымкенту — по 4 районам, а K03 (`44585de`, `boundary_registry.json`) держит открытым вопрос о пятом, Туранском, районе | `NESTED_UNIT`; параметр `expected_units` → `missing` с `missing_units`; без него `geography_checked: false` |
| 4 | A12 | Сумма 0 при неполном охвате (`+5` и `−5` у показателя-изменения) выдаётся как `reported_zero` | Противоречит собственному правилу `ZERO_ON_PARTIAL` для записи | → `missing`, `missing_reason: zero_in_partial_coverage` |
| 5 | S01–S03 | Повтор `obs_id` с разными значениями и две записи одной ячейки (город, территория, показатель, период, версия) не обнаруживаются: `validate` видит записи поодиночке, `aggregate_sum` — только равные `geo_unit_id` | Из двух противоречащих чисел в интерфейс попадёт случайное | `validate_dataset()`: `DUPLICATE_OBS_ID`, `CONFLICTING_OBSERVATION`, `DUPLICATE_RECORD` (предупреждение) |
| 6 | R25–R28 | Период `2025-02-30`, `2025-02-99`, `0000` (внутренняя замена unknown в K05) и интервал `2026/2025` проходят и regex, и схему. Давность для них молча не считается: `period_end` возвращает `None` | Запись со сломанной датой никогда не помечается как устаревшая | `period_bounds()`; `PERIOD_INVALID_DATE`, `PERIOD_REVERSED` |
| 7 | R30, R31 | `unit=count` при −3 или 2,5 принимается | Счётчик по определению — целое ≥ 0 | `COUNT_DOMAIN`; для других единиц, например `count_change`, отрицательные значения допустимы (контроль R32) |
| 8 | A07 | Территории из разных выпусков слоя границ при одной `data_version` суммируются, хотя docstring модуля обещает проверку «смешения периодов/границ в агрегате» | Риск сложить районы разных версий границ | `BOUNDARY_MIX` по слою: часть `boundary_version` до `r<id>@<версия>` |
| 9 | R33 | `source.retrieved_at = "вчера"` принимается: проверяется только непустота | Метаданные происхождения не проверяемы | `RETRIEVED_AT_INVALID` через `_parse_ts` из v1 |

**Латентный дефект, без исправления.** `k05r3_adapter.py` при сверке выборки с E02 считает
`sum(o["value"] or 0 …)`, то есть `null` превращается в 0. На текущих выходах это не срабатывает:
среди 28 + 42 записей `conf_ge_0_0` значений `null` нет. При первом пропуске района сверка молча
занизит сумму. Предлагаемое исправление: при любом `None` писать `district_sum = None`,
`consistent = None`. Адаптер не перезапускался (нужны shapely и pyproj).

## Собственная ошибка, найденная проверкой

Первая версия `BOUNDARY_MIX` сравнивала `boundary_version` целиком. Регрессионный прогон тестов
K05 с patch упал (`test_aggregate_keeps_partial_flag`): у K05 версия границы своя у каждой
территории (`…/osm:r19733918@16`, `…/osm:r3479876@35`), и проверка запретила бы любую настоящую
городскую сумму. Исправлено: сравнивается слой и выпуск. Фикстура A07 переделана, добавлен
контроль A13 — разные relation одного слоя суммируются.

## Что не делает patch

- **Схема не меняется:** NaN и Infinity в JSON Schema не выразить, поэтому защита — в загрузчике и
  контракте.
- Реестр «показатель → единица» не вводится. Разные написания единицы уже ловит `UNIT_MIX` в агрегате.
- `expected_units` нужно брать из реестра границ (K03), а не угадывать. Для Шымкента и реестр не
  доказывает полноту, пока открыт вопрос о Туранском районе.

## Рекомендации к шагу 3 интеграции K05 (REPORT K05 §6)

1. Загрузка: `loads_strict` → jsonschema → `validate` по записи → `validate_dataset` по набору.
2. Запись: `json.dumps(..., allow_nan=False)` в `dump()` адаптера.
3. Городские суммы — только с `expected_units` из реестра границ. Без него показывать «сумма по
   N территориям среза», а не «по городу».

## Проверки, которые реально выполнены (Python 3.11.15, jsonschema 4.26.0)

- Тесты K05 на `d913554` в отдельном detached worktree: `test_k05r3.py` — 18 OK,
  `test_k05_validator.py` — 9 OK. С применённым patch — тоже 18 и 9 OK.
- `git apply --check` patch на `d913554` — ok. sha256 результата применения равен `patched/…/k05r3_contract.py`.
- С patch реальные `examples/{shymkent,astana}/overture_place_record_counts.json` K05: отклонено
  0 из 56 и 0 из 84, ошибок `validate_dataset` 0.
- `python -m unittest discover -s tests`: 119 тестов, OK (expected failures = 25).
  - с jsonschema — OK;
  - с принудительно заблокированным импортом jsonschema — OK;
  - с `-W error::ResourceWarning` — OK.
- Повторная генерация `FIXTURES.json` и оба прогона раннера: sha256 `results/*.json` совпали.
- `python -m json.tool` по новым JSON: строгий JSON, без NaN.

**Не выполнялось:** запуск адаптера K05; чтение файлов в браузере продукта (проверено только
`JSON.parse` в Node); интеграция patch в ветку K05 — это решение K05 или координатора.

## Воспроизведение

```bash
cd research/round-4-results/K12
pip install jsonschema==4.26.0                                    # необязательно
python make_fixtures.py                                           # → FIXTURES.json
python stress_runner.py --impl inputs/k05_d913554 --label current # → results/current.json
python stress_runner.py --impl patched --label patched            # → results/patched.json
python -m unittest discover -s tests -v
# проверка patch на ветке K05 (в отдельном worktree):
git worktree add --detach /tmp/k05 d913554bf2617a74d921af260ab8c22743ccb4b5
git -C /tmp/k05 apply --check $PWD/patches/k05r3_contract_stress_fixes.patch
```
