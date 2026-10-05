# K01 раунд 5 — STATUS

- **Роль:** REVIEW, слот K01; ветка `claude/loving-thompson-nmajdo` (вход в snapshot: e2c704f).
- **Статус: done** для минимума задания (check `--app-root/--url`, baseline-прогон, regression test). Исправление только предложено.
- **Входы:** `origin/codex/research-import-2026-10-05` @ `2883aeb` (`round-5/snapshots.json`, `REVIEW.txt`, `review/K01.txt`);
  BUILD K04 `claude/beautiful-clarke-sbzomj` @ `0bf27deb8549b325b34a9610402613d745544edb`, `prototypes/city-evidence/`.

## Сделано
- Прочитаны `serve.py`, `README.md`, `tests/*`, `tools/build_data.py`, `tools/copy_inputs.py`, `source_manifest.json`, `web/index.html`, поиск URL в `web/*.js`.
- Написаны `extract_build.py` (git-объекты → temp, sha256), `check_build.py` (I1–I4, S1–S3, N1, B1), `browser_check.cjs`, `test_socket_side_effect.py`.
- Прогон на 0bf27de в режимах `--app-root`, `--app-root --url`, `--url`; итог и 7 находок — `REPRO.md`.

## Реально выполненные проверки
- `check_build.py --app-root … --browser` → 8 PASS, N1 FAIL (ожидаемо на baseline), exit 1.
- `check_build.py --url … --app-root … --browser` → то же; `--url` только → PASS.
- `test_socket_side_effect.py` на 0bf27de → 2 FAIL (ожидаемо), 1 PASS; на временной пропатченной копии → 3/3 OK.
- Тесты BUILD на извлечённой копии: unittest 7 OK (2 skipped без shapely), `conformance.cjs` all passed, `smoke.cjs` exit 0.

## Ограничения
- Только Linux; shapely/pyproj не установлены → K03-тесты и воспроизводимость `evidence.js` не проверены.
- Не проверялись научные выводы и данные; только целостность, запуск и изоляция сборки.
- `prototypes/city-evidence/` в своей ветке не менялся; patch — предложение, не FIXED.

## Следующий шаг
Сборщику: применить `patches/offline_check_restore_socket.patch` (согласовав с K10 или пометив локальную правку в `source_manifest.json`),
сменить вывод `smoke.cjs` по умолчанию на tmp; затем повторить `REPRO.md` команду с новым SHA.
