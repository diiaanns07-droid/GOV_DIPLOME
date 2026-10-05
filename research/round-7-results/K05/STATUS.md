# K05 round 7 — расчёт before/after как отдельный модуль: STATUS

Ветка `claude/optimistic-davinci-1oiqs9`. Статус: **ready_for_integration** (модуль + тесты; в прототип НЕ интегрирован — это делает сборщик).
Задание: `research/round-7/tasks/K05.txt`, спецификация `research/round-7/FEATURE_SPEC.txt` @ codex/research-import-2026-10-05 (7927fa8).
Данные для проверки: сборка `c58a3b2b175cf978ad785fef7f88d8fd9b1338f2` (`claude/beautiful-clarke-sbzomj`, `prototypes/city-evidence/web/data.js`, `evidence.js`), извлечена `git archive` во временный каталог. Общий прототип не менялся.

## Сделано
- `whatif.js` — чистый модуль (браузер/Node, без DOM и сети): гаверсинус, before/after/delta, null-baseline, ничья по id, QA-флаги, валидация city-whatif-v1, строгий импорт ≤256 KiB, экспорт, шаблонное объяснение с digest, сброс при смене города/категории, отпечаток среза из фактических записей.
- `whatif_ref.py` — независимый Python-эталон расчёта и отпечатка.
- `tests/test_whatif.cjs --app-root` — 30 ручных тестов (оба города, обе категории, все случаи спецификации); `tests/crosscheck.py --app-root` — сверка JS↔Python.
- `API.md` — API, JSON результата, коды ошибок, подключение.

## Проверки (реально выполнены на c58a3b2, node 22, Python 3.11)
- `node tests/test_whatif.cjs --app-root <c58a3b2>/prototypes/city-evidence` → 30 passed, 0 failed (`runs/test_whatif_c58a3b2.json`).
  Первый прогон: 28/2 — обе ошибки в тестах (несимметричная «ничья» во float; передан qa вместо записи города), исправлены, повтор 30/0.
- `python tests/crosscheck.py --app-root …` → 8 сценариев, 80 строк, отпечатки 4/4 совпали, max |Δ| = 1.1e-13 м (`runs/crosscheck_c58a3b2.json`).
- Мутация эталона (R = 6371000) → сверка падает (165 расхождений): сверка не вырожденная.
- Не запускалось: браузер/интерфейс (модуль не подключён к странице); тесты сборки (`check_all.py`) — прототип не менялся.

## Следующий шаг
Сборщику: подключить `whatif.js` к `web/` по API.md, построить UI (точки, проект, таблица), затем повторить `node research/round-7-results/K05/tests/test_whatif.cjs --app-root <новый SHA>/prototypes/city-evidence` и сообщить SHA.
