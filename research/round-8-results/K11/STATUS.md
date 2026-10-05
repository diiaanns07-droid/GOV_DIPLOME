# K11 round 8 — STATUS

Задание: `research/round-8/tasks/K11.txt` («Отзывчивость, Worker и переносимость»). Спецификация: `research/round-8/CORE_SPEC.txt` (`codex/research-import-2026-10-05` @ `c3f6c00`).
Ветка: `claude/save-work-handoff-fmjw6r`. Предыдущий результат: `aa9ce4f` (раунд 7).
Обновлено: 2026-10-05, UTC.

Целевая база: `claude/beautiful-clarke-sbzomj` @ `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d`; код = `4e93f30`, `git diff` по прототипу пуст. Извлечена побайтно. **`optimizePlans` и `city-plan-v2` в базе нет**: модули K11 изолированы, интеграция не заявляется.

| Этап | Статус |
|---|---|
| 1. Адаптер Worker/чанков: request_id/digest, прогресс, отмена, инвалидация; Node harness; браузерный пример | **done** |
| 2. Бенчмарк 16×25: отзывчивость, задержка отмены, память, освобождение ресурсов | **done** |
| 3. `file://` против localhost, запускалка Windows, Unicode-экспорт, инструкции, переносимые smoke | **done** (Windows: modeled/not_run) |

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

## Этап 3 — сделано

Реально выполнено на Linux (Node v22.22.0, Python 3.11.15, Chromium 141.0.7390.37 из Playwright 1.56.1). Windows здесь нет: пункты про Windows — модель или `NOT_RUN`.

Источники и базы:
- спецификация `research/round-8/CORE_SPEC.txt` @ `c3f6c00`;
- BUILD `a5b5e2ddbe087c4eab8e947748cdf69dbae84a0d` (`git archive`, 191 файл, blob-хэши совпали);
- `data.js` SHA-256 `bb2a7e66…` (из этапа 1).

**`file://` против http** — `tests/protocol_matrix.cjs` → **9/9 PASS**:
- на `file://` `new Worker(url)` даёт `SecurityError`, `auto` уходит в чанки, явный `worker` даёт `error`, Blob-worker работает;
- если `.js` отдаётся как `text/plain` (модель реестра Windows), страница грузится, но `importScripts` не работает; `auto` уходит в чанки, Blob-worker работает.

**`serve.py` и MIME** — `tests/serve_mime_modeled.py` (модель):
- BUILD `a5b5e2d` → **FAIL**: `app.js` уходит как `text/plain`;
- копия с `proposed_serve_mime.patch` → **PASS**.

`git apply --check` на `a5b5e2d` проходит.

**Запускалка Windows** — `tests/launcher_check.py`:
- статически `run-demo.bat` и `serve.py` + реальный запуск `serve.py` на этой ОС;
- BUILD `a5b5e2d`: **11 PASS / 1 FAIL / 2 INFO / 2 NOT_RUN**. FAIL — нет явного MIME для `.js`;
- копия с патчем: 12 PASS / 0 FAIL;
- негативный контроль: испорченный `.bat` даёт 6 FAIL.

Проверено:
- CRLF и только ASCII;
- `cd /d "%~dp0"`, `chcp 65001`, `py -3` → `python`, `pause`;
- `.gitattributes` `* -text`, только `127.0.0.1`;
- запуск из папки `Қала демо К11` и из другой cwd;
- консоль только ASCII;
- занятый порт: на Linux `OSError: [Errno 98]` — traceback, не подсказка (INFO).

NOT_RUN: двойной щелчок в `cmd.exe` и гипотеза о повторном занятии порта на Windows (`allow_reuse_address=1`).

**Unicode-экспорт** — `src/plan_export.js` + `tests/export_unicode.cjs` → **30 PASS / 0 FAIL / 0 NOT_RUN**:
- экспорт: UTF-8 без BOM, LF, буквы без `\u`;
- все 11 fixtures проходят круг «файл в папке с казахским именем → байты → тот же сценарий и digest»;
- «Блокнот»: BOM+CRLF и UTF-16 LE принимаются;
- Windows-1251 → `not_utf8`, потерянная декодировка → `replacement_char`;
- строгий JSON;
- NaN и непарный суррогат не попадают в файл;
- подделанные `derived_results` игнорируются;
- имена файлов по правилам Windows;
- Python-оракул решает экспортированный файл из другой cwd, также при `LC_ALL=C`;
- браузер (http и `file://`): настоящая загрузка `план_Шымкент_школы.json` байт-в-байт и `<input type=file>`.

Проверка порчами: **9/9 пойманы** (`runs/stage3_export_mutation_check.txt`).

**Наблюдение:** Chromium на Linux в локали `C` называет загрузку `download`, байты верные. В `C.UTF-8` имя сохраняется.

**Переносимый smoke** — `smoke/portable_smoke.py` (stdlib):

| Запуск | Результат |
|---|---|
| Из копии K11 в папке `портативті К11 тексеру`, `--app-root` = BUILD `a5b5e2d` | 6 PASS / **2 FAIL** (`launcher`, `serve_mime` — та же MIME-находка) |
| То же с копией, где применён патч | 8 PASS / 0 FAIL |
| Без `node` в PATH | 2 PASS / 6 NOT_RUN, exit 0 |
| `--quick` | 4 PASS / 4 NOT_RUN |
| Устаревший bundle | `bundle_fresh` FAIL |

**Документы:**
- `INTEGRATION.md` — файлы, порядок скриптов, фабрика по протоколу, патч MIME, правила UI, файл сценария, ручной чек-лист Windows;
- `API.md` — раздел `plan_export.js` и исправленное описание уступки worker.

Повторные прогоны после изменений этапа 3:
- `harness` → 21 PASS;
- `browser_example --file` → 15 PASS (http + `file://`);
- `protocol_matrix` → 9 PASS.

## Итоговый пакет (команды из `research/round-8-results/K11`)

```bash
python3 smoke/portable_smoke.py [--app-root <BUILD>/prototypes/city-evidence] [--out report.json] [--quick]
node tests/harness.cjs                                           # 21 проверка, без DOM
NODE_PATH="$(npm root -g)" node tests/export_unicode.cjs         # 30 проверок; без Python/Playwright -> NOT_RUN
NODE_PATH="$(npm root -g)" node tests/browser_example.cjs --file # 15 проверок
NODE_PATH="$(npm root -g)" node tests/protocol_matrix.cjs        # 9 проверок
python3 tests/launcher_check.py --app-root <BUILD>/prototypes/city-evidence
python3 tests/serve_mime_modeled.py --app-root <BUILD>/prototypes/city-evidence
node --expose-gc bench/bench_node.cjs --repeat 7 ; NODE_PATH="$(npm root -g)" node bench/bench_browser.cjs --repeat 5
python3 tools/make_worker_bundle.py                              # после правки src/plan_core.js или plan_worker.js
```

Отчёты: `runs/stage1_*`, `runs/stage2_*`, `runs/stage3_*`.

## Ограничения

- Модули не интегрированы в BUILD; в `a5b5e2d` нет `optimizePlans`. Тесты проверяют модули K11 и `example/`, а не страницу прототипа.
- Реальные срезы — только исходные записи Overture из демо. Точки, кандидаты, веса и стоимости синтетические (условные единицы, не тенге). Это не городская статистика.
- Время в отчётах — измерения этой машины, не SLA.
- Windows не запускался:
  - реестр смоделирован через `sitecustomize`;
  - `.bat` проверен статически;
  - поведение порта на Windows — гипотеза.
- Браузер: только Chromium. Firefox и WebKit — `NOT_RUN`.

## Следующий шаг

1. BUILD: внедрить по `INTEGRATION.md` (если `optimizePlans` берётся у K11) и применить `proposed_serve_mime.patch`.
2. Человек с Windows: выполнить раздел 7 `INTEGRATION.md`, приложить `smoke_windows.json`.
3. Проверяющий: после внедрения запустить `smoke/portable_smoke.py --app-root` на SHA сборки и написать браузерный тест страницы BUILD.
