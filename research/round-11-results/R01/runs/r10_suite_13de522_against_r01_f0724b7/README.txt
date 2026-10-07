Набор независимой приёмки R10 (ветка claude/fervent-dijkstra-1cqrg5 @13de522, СТАТУС R10: WIP, не вердикт)
запущен R01 против своей сборки HEAD f0724b7 (код eb7b0cd) в изолированной копии `git archive`:
  R10_TARGET=command R10_CODE_ROOT=<copy> \
  R10_START_CMD="{python} -B app.py --host 127.0.0.1 --port {port} --civic-db {db}" \
  R10_CREATE_EDITOR_CMD="{python} -B -m ui.civic_store --db {db} create-editor {username}" \
  python3 -I -B tests/civic/R10/run_acceptance.py --pattern 'test_*.py'
Редактор создавался через pty/getpass (пароль не в argv/env). Результат: 63 PASS / 1 NOT_RUN / 0 FAIL
(r01_all.json; NOT_RUN — мутация входа compare() наблюдаема только в процессе, так задумано R10).
code_sha в JSON = null, потому что в копии нет .git; сборка — f0724b7.
Окончательная приёмка — VERDICT.json R10 на финальном CODE_SHA.
