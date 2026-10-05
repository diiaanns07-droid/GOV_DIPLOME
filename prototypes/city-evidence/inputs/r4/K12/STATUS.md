# STATUS — K12, раунд 4, REVIEW: стресс-проверка missing и неполного учёта

- **Роль:** REVIEW (не BUILD). Слот K12. Ветка `claude/save-work-handoff-xuav3q`.
- **Задание:** `research/round-4/review/K12.txt` @ `codex/research-import-2026-10-05` `cadba4d`.
- **Статус: `done`** для объёма задания: фикстуры, проверка валидатора, новые воспроизводимые
  крайние случаи, `FIXTURES.json`, тесты и patch. Интеграция patch в K05 — не моя задача.

## Входы

| Вход | Ветка / SHA | Как использован |
|---|---|---|
| Модель данных K05 раунда 3 | `claude/optimistic-davinci-1oiqs9` @ `d913554bf2617a74d921af260ab8c22743ccb4b5` | `k05r3_contract.py`, схема, `next-round/K05/k05_validator.py`, 2 выхода адаптера → `inputs/k05_d913554/` побайтно (`git show` → `write_bytes`), sha256 и blob в `MANIFEST.json` |
| Реестр границ K03 | `claude/epic-curie-iitc43` @ `44585de31be01dd131ecb7677c462fc85b4d4cc4` | прочитан `boundary_registry.json` через `git show`: у Шымкента 4 района, вопрос о Туранском районе открыт. Не копировался |
| Мой предыдущий результат | `70faa0f` | контекст: missing ≠ 0 в энергоимпортёре |

Другие ветки не сливались. `prototypes/city-evidence/`, `main` и папка сборки не менялись.

## Сделано

- `make_fixtures.py` → `FIXTURES.json`: **синтетика**, 57 случаев.
  - записи — 34;
  - JSON-текст — 6;
  - агрегат — 13;
  - набор — 4.
- `stress_runner.py` → `results/current.json` (код K05) и `results/patched.json`.
- `patched/`, `patches/k05r3_contract_stress_fixes.patch`: исправления 9 групп дефектов.
- `tests/test_k05_stress.py`: 119 тестов.
- `REPORT.md`: таблица дефектов, влияние на реальные данные, своя исправленная ошибка, рекомендации.

**Результат:**

- Текущий код K05: 32 из 32 контролей совпали, 25 новых дефектов.
- Исправленная копия: 57 из 57.
- Собственные тесты K05 с patch: 18 + 9 OK.

## Проверки, которые реально выполнены

- Тесты K05 на `d913554` в detached worktree: 18 и 9 OK — без patch и с patch.
- `git apply --check` на `d913554`: ok. sha256 результата равен `patched/…/k05r3_contract.py`.
- С patch: реальные примеры K05 — отклонено 0 из 56 и 0 из 84, ошибок набора 0. Суммы 56 и 114
  прежние, с `geography_checked: false`.
- `python -m unittest discover -s tests`: 119 OK (expected failures = 25). То же с jsonschema
  4.26.0, без него (импорт заблокирован) и с `-W error::ResourceWarning`.
- Повторный прогон: `results/*.json` побайтно те же. `json.tool` по новым JSON — ok.
- Проверено чтением кода и запуском: `dump()` адаптера пишет `NaN`; `JSON.parse` в Node → `SyntaxError`.

**Не выполнялось:** запуск адаптера K05 (shapely/pyproj); проверка в браузере продукта.

## Ограничения

- Фикстуры выдуманы. «Ожидание» в них — моё прочтение собственных правил K05 (REPORT, docstrings),
  а не внешний стандарт.
- Латентный `null → 0` в адаптере K05 описан, но не исправлен: на текущих выходах не срабатывает.
- Пример по Шымкенту (4 района против открытого вопроса о пятом) — наблюдение по реестру K03,
  а не установленный факт о городе.

## Следующий шаг

1. K05 или координатор решают, применять ли `patches/k05r3_contract_stress_fixes.patch` в ветке K05.
2. Затем снимают `expectedFailure` в `CurrentK05`: после применения тест покажет unexpected
   success. Городские суммы при интеграции передают `expected_units` из реестра K03.

## Продолжение / воспроизведение

```
cd research/round-4-results/K12 && python -m unittest discover -s tests -v
```

Полностью — `REPORT.md`, раздел «Воспроизведение».
