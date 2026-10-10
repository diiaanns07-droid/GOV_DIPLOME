# tests/e2e — приёмка Birge (R10, раунд 14)

| Файл | Что делает |
|---|---|
| `run_acceptance.cjs` | **всё одной командой** для сборки R01 (B1/B2/FINAL): сервер с временной базой → точность карты → сценарий демо → UX по экранам → `SUMMARY.md` |
| `demo_flow.cjs` | 6 шагов CONTRACT §0 двумя слоями: **API** v2 (какой модуль не подключён) и **UI** в Chromium, 1366×768 и 375×812, ҚАЗ и РУС |
| `ux_screens.cjs` | UX-чек-лист UX_BRIEF по списку экранов (`screens_build.json` для сборки; для стендов ролей — свой JSON) |
| `ux_lib.cjs` | общие правила экрана: прокрутка вбок, ключи перевода, технические слова, шрифт < 14 px, зоны нажатия < 40 px (значки на карте ≥ 24 px), русские строки в ҚАЗ, Tab до главной кнопки |
| `screens_build.json` | экраны сборки: главная карта, «Картина дня» (`#day`), страницы модулей (если сервер их отдаёт; иначе NOT_RUN) |

Элементы ищутся по видимым словам из словарей R11 (`web/civic/i18n/*.json`), а не по классам — тест не ломается от
вёрстки. Реальная точка сценария — остановка «Хан Шатыр» (`osm-node-4109037549`, Нура); тексты жалоб синтетические.

    # Python 3.11+ с pytest, Node 20+, Playwright с Chromium
    NODE_PATH="$(npm root -g)" node tests/e2e/run_acceptance.cjs --root <папка сборки> --out <папка отчёта> --label B1
    NODE_PATH="$(npm root -g)" node tests/e2e/demo_flow.cjs --root <сборка> --out <папка>          # только сценарий
    NODE_PATH="$(npm root -g)" node tests/e2e/ux_screens.cjs --screens tests/e2e/screens_build.json --base http://127.0.0.1:8611/ --out <папка>
    # Windows: $env:PYTHON = "<сборка>\.venv\Scripts\python.exe"

Ничего не пишут в репозиторий; база — временная. Код возврата demo_flow — 1 при любом FAIL.
Точность карты (CONTRACT §8) — `tests/civic/R10/` (`python3 tests/civic/R10/accuracy.py --root <сборка>`).
Подробно — `research/round-14-results/R10/RUN.txt`; задание Codex на приёмку FINAL — `CODEX_ACCEPTANCE_PROMPT.txt` там же.
