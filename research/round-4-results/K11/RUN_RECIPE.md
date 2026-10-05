# Рецепт запуска K07, K10, K02 (раунд 3) на Linux и Windows

Метки:
- **[RUN-linux]** — эта команда выполнена здесь на Linux, указан результат;
- **[SIM-win]** — поведение Windows смоделировано на Linux;
- **[READ]** — только прочитано, не выполнялось.

Все команды для Windows ниже имеют метку [READ]: Windows в среде проверки не было.

Общее для обеих ОС: снимки берутся по SHA, без merge веток.

```
git fetch origin claude/save-work-handoff-ku3ej3 claude/save-work-handoff-j7pc05 claude/clever-mccarthy-pywscu
git worktree add --detach ../k07 6778deda6d3f3a7f27698f651c1b0046d2a9aae9
git worktree add --detach ../k10 ea703f1ddd3a411430a981164a78a7dda64ec909
git worktree add --detach ../k02 24c1750f70d9e444ae551030d116bb6aa8ce5b7b
```

Настройка `core.autocrlf` у Git for Windows для этих трёх пакетов результата не меняет [SIM-win]:
- K10 сверяет хэши только однострочных GeoJSON;
- выходы K07 совпали с коммитом на выгрузке с CRLF;
- патч K02 применяется.

## K10: офлайн-проверка геопакета (только stdlib)

**Linux** [RUN-linux]: Python 3.11.15, 3.12.3 и 3.13.14 → exit 0; unittest → 8 tests OK.

```bash
cd ../k10
python3 research/round-3-results/K10/scripts/offline_check.py
cd research/round-3-results/K10 && python3 -m unittest discover -s tests -v
```

**Windows** (cmd или PowerShell) [READ]:

```
cd ..\k10
py -3 research\round-3-results\K10\scripts\offline_check.py
cd research\round-3-results\K10
py -3 -m unittest discover -s tests -v
```

Ожидание на Windows:
- `offline_check.py` проходит [SIM-win: cp1251/cp1252 и autocrlf → exit 0];
- в unittest **ожидается 1 падение** `test_only_manifest_files_opened` из-за путей с `\` (W01) [SIM-win через `ntpath`]. Остальные 7 тестов затронуть не должно [READ].

Не запускать без сырых файлов раунда 2 (W11):
- `scripts/download.py` — сеть;
- `selection/select_bbox.py`, `selection/crosscheck_round2.py`.

## K07: прототип карты доступности

Просмотр без сборки, обе ОС: открыть `research/round-3-results/K07/prototype/index.html` в браузере [READ].

**Linux, полная пересборка** [RUN-linux]: `run_all.sh` → exit 0.
- `copy_inputs`: 16 файлов побайтно.
- `graph_check`: самотест пройден.
- `build_data`: `data.js` и `graph_check.json` побайтно совпали с коммитом.
- `user_path.cjs`: **34/34**.
- Побайтно меняется только `prototype/screenshots/02_astana_point_T2000.png` (недетерминированный рендер).
- Использованы Python 3.12.3 и глобальный Playwright 1.56.1 с Chromium.

```bash
cd ../k07
python3.12 -m venv /tmp/k07venv
K07_VENV=/tmp/k07venv bash research/round-3-results/K07/scripts/run_all.sh
# Без глобального playwright: в любой отдельной папке
#   npm i playwright@1.56.1 && npx playwright install chromium   (нужна сеть)
# и NODE_PATH=<эта папка>/node_modules перед node.
```

**Windows** [READ]. `run_all.sh` не запускается (W02), шаги выполняются вручную:

```
cd ..\k07
py -3.12 -m venv %TEMP%\k07venv
%TEMP%\k07venv\Scripts\python -m pip install -r research\round-3-results\K07\scripts\requirements.txt
%TEMP%\k07venv\Scripts\python research\round-3-results\K07\scripts\copy_inputs.py
%TEMP%\k07venv\Scripts\python research\round-3-results\K07\scripts\graph_check.py > NUL
%TEMP%\k07venv\Scripts\python research\round-3-results\K07\scripts\build_data.py
```

- В PowerShell вместо `%TEMP%` писать `$env:TEMP`.
- Колёса `networkx 3.6.1`, `shapely 2.1.2`, `pyproj 3.8.0` для `win_amd64` есть на PyPI для Python 3.12 и 3.13. Проверено `pip download --platform win_amd64 --only-binary=:all:`, установка на Windows не проверялась.
- Ожидаемое отличие: `MANIFEST.json`, `graph_check.json`, `data.js` будут записаны с CRLF (W05) [READ]. При `core.autocrlf=true` Git этого не покажет; при `false` покажет изменение всего файла.
- Браузерный тест `node research\round-3-results\K07\tests\user_path.cjs` на Windows, вероятно, не откроет страницу: URL собран как `file://C:\...` (W03) [SIM-win: строка]. Для проверки пути пользователя на Windows пока надёжнее открыть `index.html` вручную или запустить тест в WSL/Linux.

## K02: проверяемое объяснение AI

**Linux** [RUN-linux], Python 3.11.15, numpy 2.4.6:
- unittest: 16 tests OK;
- `demo.py --lang both` и `--lang ru --event E2`: exit 0;
- `compare_current_filter.py`: exit 0, `compare_result.json` побайтно совпал;
- `git apply --check`: exit 0.

```bash
cd ../k02
python3 -m venv /tmp/k02 && /tmp/k02/bin/pip install -r requirements.txt
/tmp/k02/bin/python -m unittest research/round-3-results/K02/test_verified_explainer.py
/tmp/k02/bin/python research/round-3-results/K02/demo.py --lang both
/tmp/k02/bin/python research/round-3-results/K02/demo.py --lang ru --event E2
/tmp/k02/bin/python research/round-3-results/K02/compare_current_filter.py
git apply --check research/round-3-results/K02/kk_letters_anchor.patch
```

**Windows** [READ]. Обязательно задать кодировку вывода, иначе казахский текст при перенаправлении падает (W08):

```
cd ..\k02
py -3 -m venv %TEMP%\k02
%TEMP%\k02\Scripts\python -m pip install -r requirements.txt
set PYTHONIOENCODING=utf-8
%TEMP%\k02\Scripts\python -m unittest research\round-3-results\K02\test_verified_explainer.py
%TEMP%\k02\Scripts\python research\round-3-results\K02\demo.py --lang both
%TEMP%\k02\Scripts\python research\round-3-results\K02\demo.py --lang ru --event E2
%TEMP%\k02\Scripts\python research\round-3-results\K02\compare_current_filter.py
git apply --check research\round-3-results\K02\kk_letters_anchor.patch
```

- В PowerShell: `$env:PYTHONIOENCODING = "utf-8"`.
- [SIM-win]: без этой переменной `demo.py --lang both` при выводе в cp1251 → `UnicodeEncodeError` на `ө` (exit 1). При cp1252 падает и `--lang ru`. С utf-8 → exit 0. `compare_current_filter.py` проходит во всех трёх кодировках.
- `requirements.txt` в корне не закрепляет версию (`numpy>=1.24`). На Python 3.11 установился numpy 2.4.6, для Windows Python 3.12 pip выбирает 2.5.3. Результат на другой версии numpy не проверялся.
