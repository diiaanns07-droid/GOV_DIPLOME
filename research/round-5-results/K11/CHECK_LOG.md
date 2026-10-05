# K11 round 5 — журнал реально выполненных команд

Среда: Linux (облачный контейнер), git 2.43.0, Python 3.11.15, Node v22.22.0, глобальный Playwright 1.56.1 + Chromium (`NODE_PATH=$(npm root -g)`). Системные пакеты не устанавливались, сеть для проверок не нужна. `<tmp>` — временный каталог проверяющего.

| # | Команда | Результат |
|---|---|---|
| 1 | `git fetch origin claude/beautiful-clarke-sbzomj`; `git rev-parse` | на момент проверки ветка указывала на `0bf27de`; позже `fd43f9a` |
| 2 | `python3 extract_build.py --sha 0bf27deb… --out <tmp>/b0` | 57 files, blob mismatches: 0 |
| 3 | `NODE_PATH=… python3 k11_demo_smoke.py --app-root <tmp>/b0/prototypes/city-evidence --browser --out …` (финальная версия скрипта) | exit 1; 15 pass, 4 fail (S4 S5 S6 S8), modeled_fail M2 M3, modeled_pass M1, info H3 L3, not_run W1 → `baseline_0bf27de.*` |
| 4 | M2 деталь: `PYTHONIOENCODING=cp1252 python serve.py <port>` | exit 1 до `serve_forever`: `UnicodeEncodeError: 'charmap' codec can't encode characters in position 0-8` |
| 5 | L2/L3 деталь baseline: SIGINT группе процессов | процесс завершён (код −2), порт свободен; stderr: трассировка `KeyboardInterrupt` |
| 6 | H8: сырые запросы `/../serve.py`, `/%2e%2e/serve.py`, `/..%2fserve.py`, `/../README.md` | все 404, утечек нет |
| 7 | H9: подключение к LAN-адресу контейнера на порт сервера | недоступен (бинд только 127.0.0.1) |
| 8 | B1: Chromium по `http://127.0.0.1:<port>/` и `pathToFileURL(web/index.html)` | оба: загружено, `CITY_EVIDENCE` с `astana`, `shymkent`, ошибок консоли 0, внешних запросов 0 |
| 9 | Временный git-репозиторий с копией `0bf27de`; `make_proposal.py` (правки 4 файлов); `git diff --cached --binary` → `proposed_launch_fix.patch` | 4 files changed, 35 insertions, 6 deletions |
| 10 | `git worktree add --detach <tmp>/wt-build 0bf27de` + `git apply --check proposed_launch_fix.patch`; затем `git worktree remove` | OK |
| 11 | `k11_demo_smoke.py --app-root <копия с патчем> --browser` | exit 0; 19 pass, 3 modeled_pass, 2 info, not_run W1 → `proposal_on_0bf27de.*`; SIGINT → код 0, без трассировки |
| 12 | В копии с патчем: `NODE_PATH=… node tests/smoke.cjs` (тест сборщика) | exit 0, 16 PASS, 0 FAIL; результаты в `tests/_smoke_out/` |
| 13 | `python3 serve.py <port>` из `0bf27de` отдельно; `k11_demo_smoke.py --url http://127.0.0.1:<port>/ --browser`; затем SIGINT серверу | exit 0; 8 pass, 1 info → `url_mode_0bf27de.*`; сервер остановлен (−2) |
| 14 | `extract_build.py --sha fd43f9a…`; `k11_demo_smoke.py --app-root … --browser` | 150 files, 0 mismatches; exit 1; те же 4 fail и 2 modeled_fail → `info_fd43f9a.*` |
| 15 | Регулярное выражение S6 на 8 строках-образцах | `py serve.py`, `py -3 serve.py 8765`, `run-demo.bat`, `> .\run-demo.bat`, `python serve.py` → да; `python3 serve.py`, `run.bat`, прозаическое упоминание `run.bat` → нет |

Исправленные ошибки самого теста (до финальных прогонов):
1. Заголовки HTTP искались с учётом регистра (`Content-type`).
2. S6 засчитывал упоминание `run.bat` основного сайта.
3. Node-скрипт браузера читал `process.argv[1]` вместо `[2]`.
4. M3 не зависел от того, что нашёл S4.
5. Заголовок B1 в режиме `--url` упоминал `file://`.
