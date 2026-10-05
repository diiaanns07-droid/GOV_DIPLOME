# Журнал реально выполненных проверок (BUILD r5, 2026-10-05, Linux)

Окружение: контейнер Claude Code, Linux; Python 3.11 (системный, без shapely) и venv Python 3.11 с shapely 2.1.2, pyproj 3.7.2 (+numpy, pytest — только для тестов K02); Node 22; Playwright 1.56.1 + Chromium (headless). Внешняя сеть для проверок не использовалась. **Windows не запускался.**

## Baseline (старая сборка 0bf27de, документирует дефекты, не тест новой сборки)
- `python3 tools/repro_baseline.py` → `baseline_repro.json`: NaN, +Infinity, −Infinity приняты валидатором v1.1; `json.loads` даёт `nan`/`inf` для `NaN`/`1e999`; повторный ключ молча меняет `value_status`; `json.dumps` пишет `NaN`.
- K03 `k03_assign_v1` на 45 fixtures K03 r4: 3 расхождения (`AST-HOLE-in0.5`, `AST-HOLE-out0.5` → unmatched вместо ambiguous; `AST-VER-D2` → matched вместо ambiguous).

## Новая сборка, чистый временный клон `9284a27` (только закоммиченные файлы)
| Команда | Результат | Файл |
|---|---|---|
| `python3 tools/check_all.py` (без shapely) | 12 passed, 1 skipped (пересборка evidence.js), 0 failed | `clean_checkout/check_all_no_shapely.json` |
| `<venv>/python tools/check_all.py` | 13 passed, 0 skipped, 0 failed | `clean_checkout/check_all_full.json` |
| `NODE_PATH=$(npm root -g) node tests/smoke.cjs <dir>` | 23/23 PASS, 0 ошибок консоли, 0 сетевых запросов | `clean_checkout/smoke_result.json` |
| `git status` клона после всех проверок | пусто (проверки ничего не меняют в рабочем дереве) | — |

`check_all` включает:
- входы: 40 + 82 копий по sha256, манифесты пропатченных копий, атрибуция = K08, якорь `package_manifest.json`;
- пакет K10: `offline_check.py` отдельным процессом;
- сборка: `data.js` и `evidence.js` побайтно равны пересборке; `evidence.js` проходит контракт;
- факты: 7 эталонных объяснений Python; JS conformance — 37 проверок;
- unit-тесты: 28 (contract 11, inputs 17, из них 3 K03 требуют shapely).

## Дополнительно (рабочее дерево, тот же код)
- Тесты K02 r3 на неизменённом модуле раунда 3 (раунд 4): 16 passed — к новой сборке не применяются (план без отпечатка отклоняется намеренно, см. MIGRATION.md).
- `serve.py`: HTTP 200 на 127.0.0.1.
- Скриншоты просмотрены глазами: 1280 px и 380 px. По ним исправлены наложение подписей QA и выход значка за карточку.

## Не выполнялось
- Запуск на Windows / macOS; `run-demo.bat`.
- Проверка средством чтения экрана (ARIA-правки K07 A1 сделаны по спецификации).
- Юридическая проверка лицензий и официальности границ — тесты кода её не заменяют.
