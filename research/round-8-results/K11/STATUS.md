# K11 round 8 — STATUS

Задание: `research/round-8/tasks/K11.txt` («Отзывчивость, Worker и переносимость»). Спецификация: `research/round-8/CORE_SPEC.txt` (`codex/research-import-2026-10-05` @ `c3f6c00`).
Ветка: `claude/save-work-handoff-fmjw6r`. Предыдущий результат: `aa9ce4f` (раунд 7).
Обновлено: 2026-10-05, UTC.

Целевая база: `claude/beautiful-clarke-sbzomj` @ `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d`; код = `4e93f30`, `git diff` по прототипу пуст. Извлечена побайтно. **`optimizePlans` и `city-plan-v2` в базе нет**: модули K11 изолированы, интеграция не заявляется.

| Этап | Статус |
|---|---|
| 1. Адаптер Worker/чанков: request_id/digest, прогресс, отмена, инвалидация; Node harness; браузерный пример | **done** |
| 2. Бенчмарк 16×25: отзывчивость, задержка отмены, память, освобождение ресурсов | следующий |
| 3. `file://` против localhost, запускалка Windows, Unicode-экспорт, инструкции, переносимые smoke | после этапа 2 |

## Этап 1 — сделано

- `src/plan_core.js`: возобновляемый движок по CORE_SPEC:
  - `haversine-mm-v1`, предвычисленные расстояния;
  - 3 лексикографические цели, Парето, чувствительность к бюджету;
  - `infeasible` с причиной;
  - digest, не зависящий от порядка массивов;
  - `evaluatePlan`, `validatePlanScenario`;
  - SHA-256 на чистом JS (сверен с `crypto` Node).
- `src/plan_runner.js`: оркестратор, см. `API.md`.
- `src/plan_worker.js`: протокол worker (браузер, Blob, `worker_threads`).
- `oracle/plan_oracle.py`: **независимый** Python-оракул (`itertools.combinations`, попарная проверка доминирования).
- `fixtures/`:
  - 8 синтетических: ничьи, пустой baseline, две причины `infeasible`, равные пары Парето, `required`/`excluded`, ID на кириллице, казахском и вне BMP, эталонный 16×25;
  - 3 реальных среза: исходные записи из `data.js` `a5b5e2d`, SHA-256 `bb2a7e66…`, точки, кандидаты и стоимости синтетические;
  - `expected_oracle.json`.
- `tests/harness.cjs`: Node без DOM. `tests/browser_example.cjs`: Playwright.
- `example/index.html` + `tools/make_worker_bundle.py`: браузерный пример (worker по URL на http, Blob-worker на `file://`).

## Реально выполненные проверки (Linux, Node v22.22.0, Python 3.11.15, Playwright 1.56.1 Chromium)

| Команда | Результат |
|---|---|
| `python3 fixtures/make_fixtures.py --app-root <a5b5e2d>/prototypes/city-evidence --app-sha a5b5e2d…` | 8 синтетических + 3 реальных |
| `python3 oracle/plan_oracle.py --write-expected fixtures/{synthetic,real}` | ожидаемые результаты 11 fixtures + чувствительность |
| `node tests/harness.cjs` | **20 PASS / 0 FAIL**: ядро = оракулу во всех 44 случаях; `chunks` и `worker_threads` = синхронному результату на 11 fixtures с чувствительностью; прогресс; отмена; вытеснение; устаревшие сообщения; зависший worker и перезапуск задачи; ошибки валидации; digest; откат `auto`; `evaluatePlan`. Процесс завершился сам (≈4,9 с): ресурсы освобождены |
| Проверка порчами (6 порченых копий) | 6/6 пойманы (`runs/stage1_mutation_check.txt`) |
| `NODE_PATH=$(npm root -g) node tests/browser_example.cjs` (http, свой сервер) | **7 PASS / 0 FAIL**: `worker`/`chunks`/`auto` = оракулу, реальный срез Шымкента + чувствительность, отмена, `infeasible` с причиной, нет ошибок и внешних запросов |

Отчёты: `runs/stage1_*`.

## Ограничения

- Модули не интегрированы в BUILD. Тесты проверяют модули K11, а не прототип.
- Реальные срезы — только исходные записи Overture из демо. Точки, кандидаты, веса и стоимости синтетические (условные единицы, не тенге). Это не городская статистика.
- Время в отчётах — измерения этой машины, не SLA.
- Windows не запускался.

## Следующий шаг

1. Этап 2: `bench/bench.cjs` (Node) и браузерный бенчмарк 16×25 — длинные задачи главного потока, задержка отмены, память, освобождение worker.
