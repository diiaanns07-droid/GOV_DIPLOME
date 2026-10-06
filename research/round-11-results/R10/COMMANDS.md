# R10 журнал команд (раунд 11)

Время UTC. Машинные прогоны набора дополнительно пишут `journal` (каждый процесс, exit code) в runs/*.json.
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
| 15:43 | `python3 -I -B app.py --port 18501` (base_b2cb2e0) | 1 | ModuleNotFoundError ui: `-I` не добавляет каталог скрипта; для app.py нужен `-E -s -B` |
| 15:44 | `python3 -E -s -B app.py --port 18501` (base_b2cb2e0) | — | сервер 200 на / |
| 15:46 | `node tests/civic/R10/browser/probe.cjs --url http://127.0.0.1:18501/ …` | 0 | baseline: 1 canvas, светлый фон, attribution OSM видна, подложка заблокирована (уведомление есть), staff-вызовов нет |
