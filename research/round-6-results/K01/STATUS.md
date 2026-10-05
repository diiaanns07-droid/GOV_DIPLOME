# K01 раунд 6 — STATUS (REVIEW: запуск и изоляция)

- **Target:** `claude/beautiful-clarke-sbzomj` @ **`064ed25368341edaa50289bc29e21dda7bdd9440`**, `prototypes/city-evidence/` (174 файла).
  Старая сборка 0bf27de как новая не перепроверялась.
- **Test source:** инструменты раунда 5 из `claude/loving-thompson-nmajdo` @ `295b356` (извлечены `git show`, без изменений);
  адаптер раунда 6 `check_r6.py` и `repro_defects.py` — в этой папке.
- **Snapshots:** `research/round-6/snapshots.json` @ `codex/research-import-2026-10-05` `edee718`.
- **Статус: done**. Вердикт: **не принято как полностью изолированное**: запуск, раздача и сетевая изоляция PASS, но 2 дефекта (D1, D2).

## Итог по инвариантам (подробно — `ACCEPTANCE.json`)
| Инвариант | Вердикт |
|---|---|
| I1–I4 входы/манифест K10/symlink/пересборка data.js (инструмент r5) | PASS |
| S1–S3 serve.py из чужой cwd, traversal, нет чтений вне web/ и соединений (r5) | PASS |
| B1 Chromium file://, нет внешних запросов (r5) | PASS |
| N1 r5 + test_socket_side_effect | **TEST_INCOMPATIBLE**: тест импортирует архивный offline_check в своём процессе; сборка так больше не делает |
| P1 нет импорта offline_check в процессе (AST) | PASS |
| P2 родитель после `check_all.step_package()`: socket не изменён, localhost работает | PASS |
| P3 сеть заблокирована внутри подпроцесса offline_check | PASS |
| M1 извлечённая копия == blobs 064ed25 | PASS |
| M2 каждый файл inputs/ закреплён хэшем | **FAIL** (D2) |
| M3 `check_all.py` на изолированном прототипе | **FAIL** (D1); в полном дереве 064ed25: 12 pass, 1 skip, 0 fail |
| T1–T3 запись вне TMPDIR / остатки temp / изменения app root | PASS (только `__pycache__`) |
| smoke.cjs с явной папкой вывода | PASS (exit 0, 23 PASS) |
| Пересборка evidence.js | SKIP (нет shapely/pyproj) |

## Дефекты (минимальный repro: `python3 repro_defects.py --app-root $APP`, exit 0 = оба воспроизведены)
- **D1** `inputs/k02v4/verified_explainer.py:29`: ищет `agent/evidence.py` в родительских папках, то есть в хакатонном сайте вне прототипа; этот файл не закреплён манифестом. Вне репозитория шаг `facts` в `check_all` падает с `StopIteration`. На работу сайта не влияет.
- **D2** `inputs/k03v2_root/`: 10 неизменённых файлов K03 v2 не проверяются по хэшу (`MANIFEST_K03V2.json` перечисляет только patched-файл). Изменение байта в `data/astana_districts.geojson` не замечает ни одна из 6 проверок inputs.
- **D3** (низкая) `tests/smoke.cjs:8`: папка вывода по умолчанию лежит вне app root (находка r5 #3 всё ещё открыта).

## Реально выполненные команды
См. `ACCEPTANCE.json.commands`; выходы — `runs/` (временные пути заменены на `<TMP>`).
Повтор на новом SHA: `APP=$(python3 extract_build.py --sha <SHA>)`, затем `python3 research/round-6-results/K01/check_r6.py --app-root $APP --extract-manifest <dest>/EXTRACT_MANIFEST.json`.

## Ограничения
Только Linux; shapely/pyproj не установлены → пересборка evidence.js и K03-тесты не выполнялись (skip ≠ pass). Windows `run-demo.bat` не проверялся.
Прототип не изменялся; исправления только предложены (см. `fix_proposal` в ACCEPTANCE.json).

## Следующий шаг
Сборщику: устранить D1 (взять `format_value` из закреплённой копии), D2 (сверять k03v2_root с k03_root или хэшировать все файлы), D3; затем повторить `check_r6.py` и `repro_defects.py` (ожидается exit 1 = не воспроизводится) с новым SHA.
