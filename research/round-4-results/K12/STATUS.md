# STATUS — K12, раунд 4, REVIEW: стресс-проверка missing и неполного учёта

- **Роль:** REVIEW (не BUILD). Слот K12. Ветка `claude/save-work-handoff-xuav3q`.
- **Задание:** `research/round-4/review/K12.txt` @ `codex/research-import-2026-10-05` `cadba4d`.
- **Статус: `partial`.** Этап 1 готов (фикстуры и прогон текущего кода). Этап 2 (patch и тесты) в работе.
- **Входы:** K05 `claude/optimistic-davinci-1oiqs9` @ `d913554bf2617a74d921af260ab8c22743ccb4b5`:
  - `research/round-3-results/K05/k05r3_contract.py`
  - `research/round-3-results/K05/schema/k05-obs-v1.1.schema.json`
  - `research/next-round/K05/k05_validator.py`
  - два выхода адаптера

  Скопированы в `inputs/k05_d913554/` через `git show` + `write_bytes`; sha256 и git blob — в
  `inputs/k05_d913554/MANIFEST.json`. Мой предыдущий результат K12 — `70faa0f`. Другие ветки не
  сливались.

## Этап 1 — сделано

- Прочитаны `k05r3_contract.py` и `k05_validator.py` целиком, а также схема, STATUS и разделы 6–7
  REPORT K05. Тесты, случаи и REPORT K05 найденные случаи не покрывают (проверено `grep`).
- `make_fixtures.py` → `FIXTURES.json`: **синтетика**, 56 случаев. Все `obs_id` начинаются с
  `SYNTHETIC-FIXTURE`, территории `kz.<город>.fixture_*` не настоящие.
  - записи — 34;
  - JSON-текст — 6;
  - агрегат — 12;
  - набор — 4.
- `stress_runner.py` → `results/current.json`: прогон текущего кода K05.
  - **Контроли:** совпали 31 из 31.
  - **Новые случаи:** 25 расхождений — это дефекты, см. таблицу.

| Группа | Расхождения (`results/current.json`) |
|---|---|
| NaN/±Infinity как `reported`: `observed` проходит схему и контракт без единого предупреждения | R20–R23 |
| JSON-загрузка: токены NaN/Infinity, `1e999` → inf, повтор ключа (последний молча побеждает) | J01–J05 |
| Несуществующие даты периода (`2025-02-30`, `2025-02-99`, `0000`), интервал наоборот | R25–R28 |
| Счётчик (`unit=count`) отрицательный или дробный | R30, R31 |
| `retrieved_at = "вчера"` принят | R33 |
| `aggregate_sum`: смешение границ (обещано в docstring, не реализовано) | A07 |
| `aggregate_sum`: город + свой район — двойной счёт | A08 |
| `aggregate_sum`: 2 из 3 территорий выдаются как полная сумма; полнота географии не проверяется | A09, A10 |
| `aggregate_sum`: NaN → `reported` NaN, `coverage_complete=true` | A11 |
| `aggregate_sum`: 0 при неполном охвате → `reported_zero` | A12 |
| Нет проверки набора: повтор `obs_id`, конфликт двух записей одной ячейки | S01–S03 |

- **Латентный дефект (чтение кода).** Адаптер K05 при сверке выборки с E02 считает
  `sum(o["value"] or 0 …)`, то есть `null` превращается в 0. На текущих выходах не срабатывает:
  среди 28 + 42 записей `conf_ge_0_0` значений `null` нет (проверено).

## Проверки, которые реально выполнены

- Тесты K05 на `d913554` в отдельном detached worktree (jsonschema 4.26.0, Python 3.11.15):
  `test_k05r3.py` — 18 OK, `test_k05_validator.py` — 9 OK.
- `python3 -m json.tool FIXTURES.json` — строгий JSON.
- `stress_runner.py --impl inputs/k05_d913554 --label current` — результат в таблице выше.

## Следующий шаг

Этап 2: исправленная копия контракта в `patched/`, `patches/*.patch` с проверкой `git apply --check`
на `d913554`, тесты (текущий код — `expectedFailure`, исправленный — проходит), прогон тестов K05 с
patch, `REPORT.md`.

## Продолжение

```
cd research/round-4-results/K12
python make_fixtures.py
python stress_runner.py --impl inputs/k05_d913554 --label current
```

Нужен `pip install jsonschema==4.26.0`; без него структурный слой будет `skipped`.
