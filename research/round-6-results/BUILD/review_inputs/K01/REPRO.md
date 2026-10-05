# K01 раунд 5 (REVIEW): воспроизводимость BUILD `prototypes/city-evidence`

Проверяемая сборка: **K04 `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`**,
путь `prototypes/city-evidence/` (55 файлов). Снимок: `research/round-5/snapshots.json` на
`origin/codex/research-import-2026-10-05` @ `2883aeb`. Прогон 2026-10-05, Linux, Python 3.11.15, Node 22, Playwright Chromium.

## Воспроизводимая команда (для исправленной версии подставить новый SHA)
```bash
git fetch origin claude/beautiful-clarke-sbzomj
APP=$(python3 research/round-5-results/K01/extract_build.py --sha <SHA>)     # байтовая копия во временную папку
cd /tmp && python3 <repo>/research/round-5-results/K01/check_build.py --app-root "$APP" --browser --json report.json
K01_APP_ROOT="$APP" python3 -m unittest discover -s <repo>/research/round-5-results/K01 -p test_socket_side_effect.py -v
# уже запущенный сервер:
python3 check_build.py --url http://127.0.0.1:8765/ [--app-root "$APP"] [--browser]
```
`--browser` требует `node` и глобальный `playwright` (`NODE_PATH=$(npm root -g)`), иначе B1 помечается skipped.

## Результат на закреплённой сборке 0bf27de
| ID | Проверка | Итог |
|---|---|---|
| I1 | 40 входов против `source_manifest.json` (bytes + sha256) | PASS |
| I2 | 6 файлов данных K10 против `package_manifest.json` (+ число объектов) | PASS |
| I3 | нет symlink в app root | PASS |
| I4 | `tools/build_data.py` на временной копии → `web/data.js` побайтно равен закоммиченному | PASS |
| S1 | `serve.py`, запущенный из чужой cwd: `index.html` + 4 `<script src>` побайтно равны `web/` | PASS |
| S2 | обход каталога `/../serve.py`, `%2e%2e/…`, `..%2f…` | PASS (404) |
| S3 | audit hook на `serve.py`: открытия вне `web/` и Python-установки, `socket.connect`, subprocess | PASS (нет) |
| N1 | localhost-соединение после возврата `offline_check.run()` | **FAIL — ожидаемо на baseline** |
| B1 | headless Chromium, `file://web/index.html` и `--url`: внешних запросов, ошибок консоли нет | PASS |

Режим `--url` (сервер запущен отдельно): S1/S2/B1 PASS; только `--url` без app-root: S1 PASS.
Логи: `baseline/check_0bf27de.{json,log}`, `baseline/check_0bf27de_url.{json,log}`, `baseline/check_0bf27de_url_only.txt`.

Собственные тесты BUILD на извлечённой копии (cwd=/tmp):
- `python3 -m unittest discover -s $APP/tests -t $APP/tests` — 7 тестов, OK, **2 skipped** (K03: нет shapely/pyproj);
- `node $APP/tests/conformance.cjs` — all passed, exit 0;
- `NODE_PATH=$(npm root -g) node $APP/tests/smoke.cjs <tmp>` — exit 0, 6 скриншотов, «no network requests».

## Regression test `test_socket_side_effect.py`
Каждый тест в отдельном subprocess. На 0bf27de: `test_connect_after_run` **FAIL (ожидаемо)**,
`test_socket_attrs_restored` **FAIL (ожидаемо)**, `test_network_blocked_during_run` PASS → `baseline/regression_0bf27de.txt`.
Третий тест страхует от «исправления», которое просто убирает блокировку сети.

## Находки
1. **N1: блокировка `socket` остаётся после `offline_check.run()`** (подтверждено на BUILD). `install_guards()` восстанавливает
   в `finally` только `builtins.open`. Любой процесс, импортирующий проверку (тесты, сборка), теряет сеть до выхода.
   Предложение: `patches/offline_check_restore_socket.patch`. **Не FIXED в BUILD**: проверено только на временной
   пропатченной копии (`baseline/regression_patched_tempcopy.txt`: 3/3 OK; `offline_check.py` exit 0).
2. **Исправление N1 в BUILD конфликтует с закреплёнными входами.** `inputs/k10/scripts/offline_check.py` хэширован в
   `source_manifest.json` как побайтная копия K10 @ ea703f1; на пропатченной копии I1 падает (проверено). Нужно либо
   исправление у K10 и новый `copy_inputs.py` с новым SHA, либо явная запись «локальная правка» в манифесте.
3. **`tests/smoke.cjs` по умолчанию пишет за пределы app root**: `path.join(__dirname, "..","..","..","research","round-4-results","BUILD","smoke")`.
   В извлечённой копии это чужая папка над приложением; без аргумента тест зависит от раскладки репозитория.
   Обход: передавать каталог аргументом (так и запускалось). Предложение: по умолчанию `os.tmpdir()`.
4. **`web/evidence.js` не перепроверен на воспроизводимость**: `build_evidence.py` и K03-тесты требуют shapely/pyproj,
   которых в среде нет (не устанавливались — сеть и новые зависимости вне задачи). I4 покрывает только `data.js`.
5. **`tools/copy_inputs.py` зависит от клона репозитория** (`ROOT = parents[3]`, `git show` с `cwd=ROOT`): из извлечённой
   копии вне клона пересборка входов невозможна. Для запуска сайта это не нужно; для аудита входов — да.
6. **Не найдено**: внешних URL/CDN/тайлов в `web/` (кроме SVG namespace), внешних запросов браузера, чтения файлов
   вне `web/` сервером, обхода каталога, зависимости `serve.py` от cwd.
7. Не проверялось: Windows/macOS, `run.bat`, долгий запуск сервера, LLM-режим (его нет).

## Файлы
`extract_build.py`, `check_build.py`, `browser_check.cjs`, `test_socket_side_effect.py`,
`patches/offline_check_restore_socket.patch`, `baseline/*` (фактические выходы, временные пути заменены на `<TMP>`).
Пакет в Git повторно не копировался — извлекается во временную папку по SHA.
