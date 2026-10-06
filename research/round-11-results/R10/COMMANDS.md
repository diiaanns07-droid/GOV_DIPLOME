# R10 журнал команд (раунд 11)

Время UTC; до 15:50 строки записаны вручную с точностью ±2 мин (точное время коммитов — `git log`), далее время берётся из `date -u` в той же команде. Машинные прогоны набора дополнительно пишут `journal` (каждый процесс, exit code) в runs/*.json.
Рабочая копия: /home/user/GOV_DIPLOME (ветка claude/fervent-dijkstra-1cqrg5). Изолированные копии — `git worktree add --detach` во временном каталоге сессии.

| UTC | Команда | Exit | Результат |
|-----|---------|------|-----------|
| 15:29 | `git fetch origin` | 0 | PACK_SHA = 9c2f5c0dae14b46c0697a9dfc7f854351bfd570d; поставок round-11 нет |
| 15:29 | `curl https://tiles.openfreemap.org/styles/liberty` | 56 | CONNECT 403 (политика прокси) → подложка/3D NOT_RUN |
| 15:31 | `git worktree add --detach <tmp>/base_b2cb2e0 b2cb2e02c602` | 0 | исходник приложения для сравнения |
| 15:33 | `git show 9c2f5c0:research/round-11/fixtures/civic_object.json \| sha256sum` | 0 | e2ba1de7… = CHECKS.json |
| 15:36 | `python3 -I -B -m unittest discover -s tests/civic/R10 -p test_fixture_contract.py -v` | 0 | 11 tests OK |
| 15:39 | `git commit` + `git push -u origin claude/fervent-dijkstra-1cqrg5` | 0 | checkpoint 1 = 1028316, push OK |
| 15:41 | `git fetch origin; python3 -I -B tests/civic/R10/delivery_scan.py --out …/DELIVERIES_SCAN.json` | 0 | DELIVERY: R02 a95f857, R04 597b14c, R05 eebb1a1, R09 cbae337 (все partial) |
| 15:42 | `python3 -I -B app.py --port 18501` (base_b2cb2e0) | 1 | ModuleNotFoundError ui: `-I` не добавляет каталог скрипта; для app.py нужен `-E -s -B` |
| 15:43 | `python3 -E -s -B app.py --port 18501` (base_b2cb2e0) | — | сервер 200 на / |
| 15:44 | `node tests/civic/R10/browser/probe.cjs --url http://127.0.0.1:18501/ …` | 0 | baseline: 1 canvas, светлый фон, attribution OSM видна, подложка заблокирована (уведомление есть), staff-вызовов нет |
| 15:46 | `git status --porcelain --ignored .runtime` (b2cb2e0 worktree, после `touch .runtime/civic.sqlite3`) | 0 | `?? .runtime/` — не игнорируется (R10-D001) |
| 15:47 | то же после патча `.gitignore` | 0 | `!! .runtime/` — игнорируется; `git apply --check patches/R01-gitignore-runtime.patch` OK |
| 15:46 | `git commit` + `git push` | 0 | checkpoint 2 = 8c676dc, push OK |
| 15:47 | `git commit` + `git push` | 0 | R10-D001 = 753bcf4, push OK |
| 15:51 | `git worktree add --detach <tmp>/wt-r07-d77ec45 d77ec45` | 0 | R07 DELIVERY status=ready, code_commit d77ec45 |
| 15:52 | `python3 -I -B tests/civic/R10/standalone/r07_typefuzz.py <wt-r07-d77ec45>` | 0 | 5/210 некорректных payload дают исключение (graph_id list/dict) → R10-D002 |
| 15:53 | то же после patches/R07-graph-id-type.patch (во временной копии, затем откат) | 0 | 0/210 |
| 15:49 | повторный прогон фаззера на чистом d77ec45 | 0 | воспроизводится: 5/210 |
| 15:50 | `git worktree add --detach … 6a28de2` (R02) и `… d8aff46` (R06) | 0 | изолированные копии для standalone |
| 15:50 | standalone smoke: R10_TARGET=command, standalone_server.py serve --root <R02> --feedback-root <R06> | 0 | create-editor через pty/getpass ×2 OK; draft→404 публично; publish; DTO allowlist OK; feedback 201 pending |
| 15:51 | R02 update/publish semantics probe | 0 | правка опубликованного = рабочая копия до повторной публикации; reason обязателен (422); публичная история несёт reason публикации → R10-O001 |
