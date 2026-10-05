# K11 round 8 — STATUS

Задание: `research/round-8/tasks/K11.txt` («Отзывчивость, Worker и переносимость»). Спецификация: `research/round-8/CORE_SPEC.txt` (`codex/research-import-2026-10-05` @ `c3f6c00`).
Ветка: `claude/save-work-handoff-fmjw6r`. Предыдущий результат: `aa9ce4f` (раунд 7).
Обновлено: 2026-10-05, UTC.

Целевая база: `claude/beautiful-clarke-sbzomj` @ `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d`; код = `4e93f30`, `git diff` по прототипу пуст. Извлечена побайтно. **`optimizePlans` и `city-plan-v2` в базе нет**: модули K11 изолированы, интеграция не заявляется.

| Этап | Статус |
|---|---|
| 1. Адаптер Worker/чанков: request_id/digest, прогресс, отмена, инвалидация; Node harness; браузерный пример | **done** |
| 2. Бенчмарк 16×25: отзывчивость, задержка отмены, память, освобождение ресурсов | **done** |
| 3. `file://` против localhost, запускалка Windows, Unicode-экспорт, инструкции, переносимые smoke | **в работе** (промежуточный push) |

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

## Этап 2 — сделано

- `bench/bench_node.cjs`:
  - синхронно, чанки 4/8/16 мс, worker холодный и тёплый;
  - блокировка цикла событий: опоздание таймера + `monitorEventLoopDelay`;
  - отмена на 10/50/90 %;
  - 30 циклов: память, worker создано/завершено, active handles.
- `bench/bench_browser.cjs` (Chromium): длинные задачи, опоздание таймера, кадры rAF, отмена, куча JS и баланс worker за 20 циклов.
- **Найдены и исправлены два дефекта:**
  - `setTimeout(0)` в worker зажимался до 4 мс: worker с чувствительностью 331 → 74 мс;
  - поздняя отмена без подтверждения вела к жёсткому завершению исправного worker. Добавлен тест 12, проверен порчей.
- `BENCHMARK.md`: таблицы и выводы. Отчёты: `runs/stage2_*`, включая `*_before_fix.json` и три повторных прогона Node.

Проверки этапа 2 (реально выполнены):
- `node tests/harness.cjs` → **21 PASS / 0 FAIL**;
- `node --expose-gc bench/bench_node.cjs --repeat 7` → exit 0, и 3 повтора;
- `node bench/bench_browser.cjs --repeat 5` → exit 0, ошибок страницы нет;
- `node tests/browser_example.cjs` → 7 PASS.

Итоги:
- **worker:** длинных задач 0, опоздание таймера ≤ 2,3 мс;
- **чанки 8 мс:** длинных задач 0, опоздание ≤ 17 мс;
- **синхронно:** длинные задачи 74–84 мс — это положительный контроль;
- **отмена:** promise ≤ 0,6 мс, подтверждение ≤ 13 мс, жёстких завершений 0;
- **память:** рост кучи ≤ 0,02 МБ, worker 30/30 и 20/20.

Один выброс 51,5 мс в Node не воспроизвёлся в трёх повторах; описан в `BENCHMARK.md`.

## Ограничения

- Модули не интегрированы в BUILD. Тесты проверяют модули K11, а не прототип.
- Реальные срезы — только исходные записи Overture из демо. Точки, кандидаты, веса и стоимости синтетические (условные единицы, не тенге). Это не городская статистика.
- Время в отчётах — измерения этой машины, не SLA.
- Windows не запускался.

## Этап 3 — промежуточный результат

Реально выполнено (Linux, Chromium из Playwright 1.56.1, Python 3.11.15):
- `tests/protocol_matrix.cjs` → **9/9 PASS**. На `file://` `new Worker(url)` даёт SecurityError, `auto` переходит на чанки, Blob-worker работает. Если `.js` отдаётся как `text/plain` (модель реестра Windows), страница открывается, но `importScripts` не срабатывает; `auto` переходит на чанки, Blob-worker работает.
- `tests/serve_mime_modeled.py` (модель, не Windows): `serve.py` BUILD `a5b5e2d` при отравленном `mimetypes` отдаёт `app.js` как `text/plain` → **FAIL**. С `proposed_serve_mime.patch` (копия, не BUILD) → **PASS**.
- `src/plan_export.js`: экспорт и импорт сценария в UTF-8.
  - Байтовый импорт: Windows-1251 даёт ошибку `not_utf8`, а не кракозябры. UTF-16 с BOM читается, строгий JSON.
  - Имена файлов безопасны для Windows.
  - `tests/export_unicode.cjs` → **30 PASS / 0 FAIL / 0 NOT_RUN**: Node; Python-оракул из другой cwd по пути с казахскими буквами, также при `LC_ALL=C`; браузер http и `file://` (настоящая загрузка и `<input type=file>`). Проверка порчами: 9/9 пойманы.
- Найдено: Chromium на Linux в локали `C` заменяет кириллическое имя загрузки на `download`, байты при этом верные. В `C.UTF-8` имя сохраняется (наблюдение 9d).
- `example/index.html`: кнопки «Сохранить сценарий» / «Открыть сценарий». Повторные прогоны: `harness` 21 PASS, `browser_example --file` 15 PASS.

## Следующий шаг

1. Этап 3 (остаток): статическая и модельная проверка `run-demo.bat`/`serve.py`, переносимый smoke `smoke/portable_smoke.py`, `INTEGRATION.md`, итоговый пакет.
