# K11, раунд 4 (REVIEW). Переносимость запуска K07, K10, K02 (раунд 3)

Входы по `research/round-4/snapshots.json` (`codex/research-import-2026-10-05` @ `cadba4d`):

| Слот | Ветка | SHA | Папка |
|---|---|---|---|
| K07 | `claude/save-work-handoff-ku3ej3` | `6778deda6d3f3a7f27698f651c1b0046d2a9aae9` | `research/round-3-results/K07/` |
| K10 | `claude/save-work-handoff-j7pc05` | `ea703f1ddd3a411430a981164a78a7dda64ec909` | `research/round-3-results/K10/` |
| K02 | `claude/clever-mccarthy-pywscu` | `24c1750f70d9e444ae551030d116bb6aa8ce5b7b` | `research/round-3-results/K02/` |

Снимки развёрнуты в отдельные detached worktree во временном каталоге. Чужие ветки не менялись, ничего не сливалось.

Метки:
- **[RUN-linux]** — запущено здесь на Linux, результат приведён;
- **[SIM-win]** — воспроизведено на Linux средствами, моделирующими Windows: `ntpath`, `PYTHONIOENCODING=cp1251`, выгрузка с `core.autocrlf=true`. **Это не запуск на Windows**;
- **[READ]** — только прочитано, не запускалось.

Настоящего Windows в этой среде нет. Ни одна команда для Windows здесь не исполнялась.

## Проблемы

| ID | Где | Проблема | Последствие на Windows | Метка |
|---|---|---|---|---|
| W01 | K10 `scripts/offline_check.py` L254 + `tests/test_package.py` L32–35 | `files_opened` строится через `os.path.relpath`, а тест сравнивает его с путями манифеста через `/` (`data/astana/...`) | на Windows `relpath` даёт `data\astana\...`, `set(files_opened) <= allowed` ложно, тест `test_only_manifest_files_opened` падает. Сам `offline_check.py` проходит, у него своя проверка через `abspath` | [SIM-win] через `ntpath.relpath`: `subset = False`, у `posixpath` `True` |
| W02 | K07 `scripts/run_all.sh` (весь файл) | bash: `set -euo pipefail`, `command -v python3.12`, `${TMPDIR:-/tmp}`, `$VENV/bin/python`, `$VENV/bin/pip`, `> /dev/null` | в cmd/PowerShell не запускается. В venv на Windows нужно `Scripts\python.exe`, вместо `python3.12` — `py -3.12` | [READ] |
| W03 | K07 `tests/user_path.cjs` L9 | `"file://" + path.join(K07, "prototype/index.html")` | на Windows получится `file://C:\...\index.html`, нужен `url.pathToFileURL(...)`. Открытие страницы в Playwright может не сработать | [READ] |
| W04 | K07 `tests/user_path.cjs` L6, README «preinstalled Chromium» | `require("playwright")` без `package.json` и закреплённой версии. Здесь работает глобальный Playwright 1.56.1 со встроенным Chromium | на чистой машине: `npm i playwright@1.56.1` в отдельной папке и `npx playwright install chromium`. Скачивание браузера требует сети | [READ] (версия: [RUN-linux] `require('playwright/package.json').version`) |
| W05 | K07 `scripts/copy_inputs.py` L51, `graph_check.py` L284, `build_data.py` L169 | `Path.write_text(..., encoding="utf-8")` без `newline="\n"` | в Windows `\n` записывается как `\r\n`. `inputs/MANIFEST.json`, `results/graph_check.json` и `prototype/data.js` побайтно отличаются от закоммиченных. При `core.autocrlf=false` Git покажет изменение всего файла | [READ] |
| W06 | K07 README «Python 3.12 venv», `scripts/requirements.txt` | закреплены `networkx==3.6.1`, `shapely==2.1.2`, `pyproj==3.8.0`, интерпретатор строго 3.12 (`run_all.sh` ищет `python3.12`) | без Python 3.12 сценарий останавливается. Наличие Windows-колёс см. в разделе «Проверки» | [READ] |
| W07 | K02 `REPORT.md` L111–116 | рецепт: `python3 -m venv /tmp/k02 && /tmp/k02/bin/pip ...` | путь `/tmp` и `bin/` только для Linux. На Windows `%TEMP%\k02\Scripts\python.exe` | [READ] |
| W08 | K02 `demo.py` L28–29, `compare_current_filter.py` L85–88 | печать казахского текста в stdout (`--lang kk`/`both`) | при перенаправлении вывода в файл или конвейер Python на Windows берёт кодировку локали (cp1251/cp1252). Буквы ә ғ қ ң ө ұ ү һ і в cp1251 отсутствуют → возможен `UnicodeEncodeError`. В интерактивной консоли проблемы нет. Лечение: `set PYTHONUTF8=1` или `PYTHONIOENCODING=utf-8` | [READ], проверка запуском — следующий этап |
| W09 | K02 `kk_letters_anchor.patch` | патч для `agent/evidence.py` с LF-окончаниями | при `core.autocrlf=true` рабочая копия `agent/evidence.py` будет с CRLF, и `git apply --check` может не пройти | [READ], проверка — следующий этап |
| W10 | K10 `scripts/download.py` L35 | скрытый абсолютный путь `/root/.ccr/ca-bundle.crt` по умолчанию для `REQUESTS_CA_BUNDLE` | на Windows файла нет, срабатывает запасной вариант `verify=True`. Не ломает, но это след песочницы автора. Скрипт к тому же сетевой | [READ] |
| W11 | K10 `selection/select_bbox.py`, `selection/crosscheck_round2.py` | нужны незакоммиченные сырые выгрузки раунда 2 (`<raw_dir>`, `<places.jsonl>`, до 47 МБ). Это признаёт и сам K10 (`STATUS.md` L73) | ни на одной ОС не запускаются из клона без пересоздания сырья скриптом раунда 2 | [READ] |
| W12 | все три README | команды записаны как `python3 ...` | на Windows обычно `py -3` или `python`. `python3` может оказаться заглушкой Microsoft Store | [READ] |

## Подтверждённо переносимое

| Что | Почему переносимо | Метка |
|---|---|---|
| K10 `python3 scripts/offline_check.py` | только stdlib. Все текстовые чтения с `encoding="utf-8"`. Пути через `os.path`. Отчёт печатается ASCII-текстом | [RUN-linux] Python 3.11, 3.12, 3.13: exit 0. [SIM-win] stdout=cp1251 и cp1252: exit 0. [SIM-win] выгрузка с `core.autocrlf=true`: exit 0 |
| K10 данные под `core.autocrlf=true` | файлы `data/*/*.geojson` записаны одной строкой без `\n`, CRLF-конвертация их не меняет, SHA256 из манифеста совпадают. CRLF получают только `selection/*.json` (91 строка), но их хэш `offline_check` не проверяет | [SIM-win] |
| K10 `python -m unittest discover -s tests -v` (из папки пакета) | stdlib | [RUN-linux] 8 tests OK. [SIM-win] на выгрузке `core.autocrlf=true`: OK. Исключение — W01, это семантика путей Windows, а не байты |
| K07 `copy_inputs.py`: побайтность | копирует через `git cat-file blob` и `write_bytes`, сравнивает id blob через `git hash-object`. Исходные blob K10 (`e91898d`) не содержат CR, поэтому фильтр autocrlf в `hash-object` их id не меняет | [READ] + [RUN-linux]: подсчёт CR во всех 16 исходных blob = 0 |
| K07 `prototype/index.html` двойным щелчком | данные в `data.js`, сеть не нужна (README) | [READ] |
