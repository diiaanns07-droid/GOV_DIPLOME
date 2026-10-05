# K11 round 8 — инструкция внедрения для BUILD

Цель: `prototypes/city-evidence/` на базе `claude/beautiful-clarke-sbzomj` @ `a5b5e2d`. **Не внедрено.** В базе нет `optimizePlans`, поэтому интеграция в BUILD не проверялась. Ниже — что сделать сборщику и как проверить. Общий прототип меняет только BUILD.

## 1. Файлы и порядок подключения

Скопировать в `prototypes/city-evidence/web/`:

| Файл K11 | Назначение | Нужен, если |
|---|---|---|
| `src/plan_core.js` | движок `CITY_PLAN_CORE` | у BUILD нет своего решателя; иначе передать свой движок в `engine` |
| `src/plan_runner.js` | оркестратор `CITY_PLAN_RUNNER` | всегда |
| `src/plan_worker.js` | код worker, делает `importScripts("plan_core.js")` из той же папки | http(s) |
| `src/plan_export.js` | файл сценария `CITY_PLAN_EXPORT` | нужны «Сохранить» и «Открыть» для `city-plan-v2` |
| `worker_bundle.js` | `CITY_PLAN_WORKER_SOURCES` для Blob-worker | страница открывается как `file://` |

`worker_bundle.js` генерируется, руками не правится. `tools/make_worker_bundle.py` пишет его в `example/` K11 вместе с `fixture_data.js`. BUILD нужен только `worker_bundle.js`: скопировать его или поменять папку вывода в своей копии скрипта. Пересобирать после каждой правки `plan_core.js`/`plan_worker.js`. Устаревший bundle ловит шаг `bundle_fresh` в `smoke/portable_smoke.py`: там записаны SHA-256 исходников.

Порядок в `index.html`: движок до runner, bundle до кода приложения.

```html
<script src="data.js"></script>
<script src="evidence.js"></script>
<script src="facts.js"></script>
<script src="whatif.js"></script>
<script src="plan_core.js"></script>
<script src="plan_runner.js"></script>
<script src="plan_export.js"></script>
<script src="worker_bundle.js"></script>
<script src="app.js"></script>
```

## 2. Фабрика worker по протоколу

```js
const RUN = window.CITY_PLAN_RUNNER;
const factory = location.protocol === "file:"
  ? RUN.blobWorkerFactory(window.CITY_PLAN_WORKER_SOURCES)   // file://: new Worker(url) запрещён (SecurityError)
  : RUN.urlWorkerFactory("plan_worker.js");
const runner = RUN.createPlanRunner({ engine: window.CITY_PLAN_CORE, mode: "auto", workerFactory: factory, sliceMs: 8,
  onProgress: (e) => { /* полоса прогресса: e.fraction */ } });
```

Проверено в `tests/protocol_matrix.cjs` (Chromium):

| Протокол | `new Worker(url)` | `auto` + URL-фабрика | Blob-фабрика |
|---|---|---|---|
| `http://127.0.0.1`, `.js` = `text/javascript` | работает | `worker` | работает |
| `http`, `.js` = `text/plain` (модель реестра Windows) | `importScripts` падает | `chunks`, причина в `env.fallback` | работает |
| `file://` | `SecurityError` | `chunks`, причина в `env.fallback` | работает |

`auto` не ломает страницу, но теряет worker; это видно только в `env.mode`/`env.fallback`. Поэтому:
- показывать `env.mode` и `env.fallback` в строке статуса;
- Blob-фабрику можно использовать и на http. Тогда MIME-проблема не мешает, но при будущем CSP понадобится `worker-src blob:`. Сейчас CSP в `index.html` BUILD нет.

## 3. `serve.py`: явный MIME для `.js`

`SimpleHTTPRequestHandler` берёт тип из `mimetypes`, а на Windows тот читает реестр. Если там `.js` = `text/plain`, worker по URL не стартует. Применить `proposed_serve_mime.patch` из корня репозитория BUILD (файл патча взять из ветки K11):

```bash
git apply --check <K11>/proposed_serve_mime.patch   # на a5b5e2d: OK
git apply <K11>/proposed_serve_mime.patch
```

Проверка (модель, не Windows): `tests/serve_mime_modeled.py`. На `a5b5e2d` — FAIL (`app.js` уходит как `text/plain`), на копии с патчем — PASS.

## 4. Правила UI

- Один runner на страницу, переиспользовать. Холодный worker стоит примерно +30–70 мс (`BENCHMARK.md`).
- Никогда не вызывать `optimizePlansSync` из UI: на 16×25 с чувствительностью это блокировки 74–84 мс.
- Новый запуск сам вытесняет старый (`superseded`). Кнопка «Отмена» вызывает `runner.cancel()`.
- Применять результат только по кнопке пользователя и только если `runner.isCurrent(env)`, иначе «предложение устарело».
- `env.status`: `optimal` / `infeasible` (+ `result.reasons`) / `cancelled` / `superseded` / `error` (+ `code`). Каждому — отдельный текст.

## 5. Сохранение и открытие файла сценария

```js
const EXP = window.CITY_PLAN_EXPORT, CORE = window.CITY_PLAN_CORE;
// сохранить: derived_results только для optimal-результата этой же задачи
const sc = CORE.validatePlanScenario(currentScenario, context);
const env = last && last.status === "optimal" && last.problem_digest === CORE.problemDigest(sc) ? last : null;
EXP.downloadPlanFile(EXP.exportPlanFile(sc, env));                 // имя: план_Шымкент_школы.json
// открыть: только байты, не File.text()
input.onchange = async () => {
  try { const r = await EXP.readPlanFile(input.files[0], context, CORE); /* r.scenario; r.derived_ignored */ }
  catch (e) { /* e.code: not_utf8, bad_json, duplicate_key, bad_city, bad_snapshot, ... — показать по-русски */ }
};
```

- CORE_SPEC v2 не ограничивает алфавит ID (`≤ 64 символов`). В `city-whatif-v1` ID были только ASCII (`ID_RE`). При кириллических или казахских ID `File.text()` превращает файл в Windows-1251 в кракозябры **без ошибки**. `readPlanFile` даёт `not_utf8`.
- Импорт `whatif-v1` в BUILD (`f.text()`) для v1 безопасен: все проверяемые поля ASCII.
- Перевод кодов ошибок на русский — в `example/index.html`, функция `importFile`.

## 6. Проверка после внедрения

```bash
cd research/round-8-results/K11
python3 smoke/portable_smoke.py --app-root ../../../prototypes/city-evidence --out smoke_report.json
```

Шаги smoke:
- `oracle`, `bundle_fresh` — только Python;
- `harness`, `export` — Node;
- `browser`, `protocols` — Playwright: `NODE_PATH` или `npm root -g`; ничего не устанавливается;
- `launcher`, `serve_mime` — нужен `--app-root`.

Без инструмента шаг получает `NOT_RUN`, не `PASS`.

Тесты K11 проверяют модули K11 и пример `example/index.html`, а не страницу BUILD. После внедрения сборщику нужен свой браузерный тест страницы. Сценарии брать из `tests/browser_example.cjs` и `tests/export_unicode.cjs`, часть 9.

## 7. Ручная проверка на Windows (здесь не выполнялась)

1. Распаковать проект в папку с кириллицей и пробелом, например `C:\Users\<имя>\Рабочий стол\Қала демо`. Двойной щелчок по `run-demo.bat` → страница открылась.
2. DevTools → Network: `plan_worker.js` отдаётся как `text/javascript`, статус поиска показывает режим `worker`.
3. Запустить `run-demo.bat` второй раз, пока работает первый. Записать, что произошло. **Гипотеза:** на Windows второй сервер может занять тот же порт (`allow_reuse_address=1`, семантика `SO_REUSEADDR`). На Linux второй запуск падает с `OSError: [Errno 98]`.
4. Открыть `web/index.html` двойным щелчком (`file://`) → поиск работает в режиме `worker` (Blob).
5. «Сохранить сценарий» → в «Загрузках» файл `план_Шымкент_школы.json`.
6. Открыть его в Блокноте:
   - сохранить как ANSI → «Открыть сценарий» → сообщение «файл не в UTF-8»;
   - сохранить как UTF-8 (с BOM) → файл принят.
7. `py -3 smoke\portable_smoke.py --app-root ..\..\..\prototypes\city-evidence --out smoke_windows.json` → приложить отчёт.
