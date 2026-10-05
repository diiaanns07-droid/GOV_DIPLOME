# Доказательство: офлайн-проверка работает только на закоммиченных входах

Выполнено 2026-10-05 около 06:23 UTC (время записи логов). Коммит пакета: `602f0c0b6d5db741d20909082086982b3c812c07`, уже отправлен в `origin/claude/save-work-handoff-j7pc05`.

## Что сделано

1. **Чистый клон с GitHub.** `git clone --depth 1 --branch claude/save-work-handoff-j7pc05` в пустую папку scratchpad. `HEAD = 602f0c0…`, `git status --porcelain` пуст. В клоне нет сырых выгрузок, venv и файлов рабочей копии автора.
2. **Изоляция от сети.** Запуск через `unshare -rn`: новое сетевое пространство без интерфейсов, плюс `env -i`, то есть без `HTTPS_PROXY` и без venv. Внутри проверено: `curl https://github.com` не соединяется, `socket.create_connection` даёт `Network is unreachable`.
3. **Двойная защита внутри скрипта.** `scripts/offline_check.py` сам блокирует `socket.connect` и `socket.create_connection` и записывает каждый `open()`. Открытие файла вне манифеста — ошибка проверки.
4. **Результат на клоне:** `offline_check_exit=0`, `ok=True`, `errors=[]`. Открыты только `package_manifest.json` и 6 файлов `data/*/*.geojson`. Отчёт: `results/offline_check_clean_clone_602f0c0.json`.
5. **Тесты на клоне:** `python3 -m unittest discover -s tests -v` → 8 тестов, OK. Среди них тест подмены одного байта в копии (обнаруживается по SHA256) и тест блокировки сети.
6. **SHA256** всех 6 файлов данных в клоне совпали с `package_manifest.json`. После запусков `git status --porcelain` пуст.
7. **Чтение другим агентом (рецепт из `INPUT_FOR_K07.md`).** `git show 602f0c0:research/round-3-results/K10/<path> > inputs/K10/<path>` для 10 файлов в пустую папку, затем `unshare -rn … python3 inputs/K10/scripts/offline_check.py` → exit 0, `ok=True`.

## Почему SHA не зависят от платформы

В файлах данных нет символов `\n` и `\r`: это одна строка компактного JSON. Перевод строк при checkout (`core.autocrlf`) не может их изменить. В `.gitattributes` правил для `*.geojson` и `*.json` нет.

## Что не доказано

- Проверка шла на Linux, Python 3.11.15. Запуск на Windows и macOS не выполнялся.
- `download.py` в этой проверке не запускался: ему нужна сеть. Пересборка зависит от наличия выпуска `2026-09-23.1` в S3.

## Сырые логи

```text
## clone
git clone --depth 1 --branch claude/save-work-handoff-j7pc05 https://github.com/diiaanns07-droid/GOV_DIPLOME
HEAD=602f0c0b6d5db741d20909082086982b3c812c07
porcelain_lines=0

## network namespace check (should fail to reach GitHub)
0
curl: (7) Failed to connect to 127.0.0.1 port 40479 after 0 ms: Couldn't connect to server
OSError: [Errno 101] Network is unreachable

## offline_check inside unshare -rn (no network interfaces), plain python3 without venv
offline_check_exit=0
ok= True errors= []
files_opened= ['data/astana/connectors.geojson', 'data/astana/places_social.geojson', 'data/astana/segments.geojson', 'data/shymkent/connectors.geojson', 'data/shymkent/places_social.geojson', 'data/shymkent/segments.geojson', 'package_manifest.json']

## unittest inside unshare -rn
test_counts_and_graph (test_package.ControlCounts.test_counts_and_graph) ... ok
test_edge_objects (test_package.ControlCounts.test_edge_objects) ... ok
test_no_duplicates_and_referential_integrity (test_package.ControlCounts.test_no_duplicates_and_referential_integrity) ... ok
test_network_blocked (test_package.PackageIntegrity.test_network_blocked) ... ok
test_offline_check_passes (test_package.PackageIntegrity.test_offline_check_passes) ... ok
test_only_manifest_files_opened (test_package.PackageIntegrity.test_only_manifest_files_opened) ... ok
test_release_pinned (test_package.PackageIntegrity.test_release_pinned) ... ok
test_modified_copy_fails (test_package.TamperDetection.test_modified_copy_fails) ... ok

----------------------------------------------------------------------
Ran 8 tests in 0.155s

OK
## sha256 of data files vs manifest
shymkent places_social True e0959270b962362a
shymkent segments True 055b0e7aaef8d5b4
shymkent connectors True 8bbd25959eef559a
astana places_social True f5722c4455ca37d7
astana segments True 5fc1b3b5f6cabad6
astana connectors True 74a77d2ed250d6a5
porcelain_after=0

## K07 recipe: git show $SHA:path > inputs/K10/path (bash), then offline_check
inputs/K10/data/astana/connectors.geojson
inputs/K10/data/astana/places_social.geojson
inputs/K10/data/astana/segments.geojson
inputs/K10/data/shymkent/connectors.geojson
inputs/K10/data/shymkent/places_social.geojson
inputs/K10/data/shymkent/segments.geojson
inputs/K10/package_manifest.json
inputs/K10/scripts/geo_util.py
inputs/K10/scripts/k10_rules.py
inputs/K10/scripts/offline_check.py
k07_recipe_offline_check_exit=0
ok= True errors= []
```
