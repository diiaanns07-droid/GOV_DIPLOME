# K11 round 4 — журнал реально выполненных команд

Среда: Linux (облачный контейнер), git 2.43.0, Python 3.11.15 / 3.12.3 / 3.13.14, Node v22.22.0, глобальный Playwright 1.56.1 с Chromium.
Снимки развёрнуты так, ветки не менялись:
- `git worktree add --detach <tmp>/wt-k07 6778ded…`, `wt-k10 ea703f1…`, `wt-k02 24c1750…`;
- для имитации Git for Windows: `git -c core.autocrlf=true worktree add --detach <tmp>/wt-*-crlf <SHA>`.

venv лежат во временном каталоге:
- K07: `python3.12 -m venv`, `pip install -r scripts/requirements.txt` → networkx 3.6.1, shapely 2.1.2, pyproj 3.8.0;
- K02: `python3.11 -m venv`, `pip install -r requirements.txt` → numpy 2.4.6.

Системные пакеты не устанавливались.

| # | Команда (cwd) | Результат |
|---|---|---|
| 1 | `python3.11 research/round-3-results/K10/scripts/offline_check.py` (корень wt-k10) | exit 0 |
| 2 | `python3.12 …/offline_check.py`, `python3.13 …/offline_check.py` | exit 0, exit 0 |
| 3 | `python3.11 -m unittest discover -s tests -v` (папка K10) | `Ran 8 tests … OK` |
| 4 | `PYTHONIOENCODING=cp1251` и `=cp1252 python3.11 scripts/offline_check.py > file` | exit 0, exit 0 |
| 5 | wt-k10-crlf: подсчёт CRLF | `selection/astana_bbox_selection.json` 91, `scripts/offline_check.py` 272, `data/astana/segments.geojson` 0 |
| 6 | wt-k10-crlf: `offline_check.py`; `unittest discover -s tests` | exit 0; OK |
| 7 | Python: `ntpath.relpath(ntpath.abspath(ntpath.join(PKG, p)), PKG)` для путей манифеста | `data\\astana\\connectors.geojson`; subset манифеста = **False**. У `posixpath` = True |
| 8 | wt-k07: `copy_inputs.py`; `graph_check.py`; `build_data.py` (venv 3.12) | «16 files copied; all byte-identical»; selftest passed; `data.js bytes 477038`; `git status` пуст |
| 9 | wt-k07: `node research/round-3-results/K07/tests/user_path.cjs` | `ALL 34 CHECKS PASSED`; изменён только `screenshots/02_astana_point_T2000.png` |
| 10 | wt-k07: `PYTHONIOENCODING=cp1251` и `=cp1252 graph_check.py > file` | exit 0, exit 0 |
| 11 | wt-k07-crlf: CRLF во входе; `graph_check.py`; `build_data.py`; sha256 выходов против blob HEAD | `astana_places_social_sample.jsonl` 105 CRLF; exit 0; exit 0; `data.js` и `graph_check.json` = blob (20906b2b…, d2f6e25b…) |
| 12 | Node: `"file://" + path.win32.join(K07, "prototype/index.html")` против `url.pathToFileURL(…, {windows:true})` | `file://C:\Users\…\index.html` против `file:///C:/Users/…/index.html` |
| 13 | wt-k07: `K07_VENV=<venv> bash research/round-3-results/K07/scripts/run_all.sh` | exit 0, `ALL 34 CHECKS PASSED`; снова изменён только тот же PNG |
| 14 | `git cat-file blob e91898d:research/next-round/K10/<16 входов K07>`: подсчёт `\r` | 16 файлов, 0 байт CR |
| 15 | `pip download --only-binary=:all: --platform win_amd64 --python-version 3.12/3.13 --no-deps networkx==3.6.1 shapely==2.1.2 pyproj==3.8.0` | есть `pyproj-3.8.0-cp312/cp313-win_amd64`, `shapely-2.1.2-cp312/cp313-win_amd64`, `networkx-3.6.1-py3-none-any` |
| 16 | то же для `"numpy>=1.24"` (py3.12) и `pyarrow==25.0.1 requests==2.34.2` (py3.12) | `numpy-2.5.3-cp312-win_amd64`; `pyarrow-25.0.1-cp312-win_amd64`, `requests-2.34.2-py3-none-any` |
| 17 | wt-k02: `python -m unittest research/round-3-results/K02/test_verified_explainer.py` (venv 3.11) | `Ran 16 tests … OK` |
| 18 | wt-k02: `demo.py --lang both`; `demo.py --lang ru --event E2`; `compare_current_filter.py`; `git apply --check kk_letters_anchor.patch` | exit 0 ×4; `git status` пуст (`compare_result.json` совпал) |
| 19 | wt-k02: те же `demo.py`/`compare` с `PYTHONIOENCODING=cp1251` | `demo --lang both` → **exit 1** `UnicodeEncodeError … '\u04e9'`; `demo --lang ru --event E2` → 0; compare → 0 |
| 20 | то же с `cp1252` | `demo --lang both` → **exit 1**; `demo --lang ru --event E2` → **exit 1**; compare → 0 |
| 21 | то же с `utf-8` | все exit 0 |
| 22 | wt-k02-crlf: CRLF в `agent/evidence.py` и патче; `git apply --check`; unittest | 319 и 11; exit 0; OK |

Сеть: использовались только PyPI (установка в venv и `pip download` метаданных и колёс) и `git fetch` из origin. Сторонние сайты и API не вызывались. Windows не запускался.
