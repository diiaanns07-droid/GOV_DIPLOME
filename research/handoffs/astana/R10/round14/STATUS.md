# R10 — раунд 14 (Birge): приёмка · handoff

Задача: R10 «Приёмка: сценарий демо, точность, UX» (research/round-14/prompts/R10.txt).
Агент: Claude Code (облачная сессия), Астана. Аккаунт b10 (s11), бюджет недели ограничен — тяжёлые прогоны → Codex.
Рабочая ветка: **`claude/r14-R10`** (от `claude/round-14-package` @ 4bbf456). В `claude/round-14-package` не пушу.
Свои пути: `tests/civic/R10/`, `tests/e2e/`, `research/round-14-results/R10/`, этот файл.
Обновлено: 2026-10-10, вечер (UTC; точное время — у коммита).
Статус: partial (начато раньше плана по просьбе владельца: проверка поставок по отдельности и текущей ветки R01).

## Что сделано
1. Проверка поставок ролей по отдельности → `research/round-14-results/R10/DELIVERIES_CHECK.md`:
   владение путями (все чисто), повтор тестов R03, R05, R06, R07, R08, R09, R11, R12 (совпадают с DELIVERY),
   прямая проверка API R04.
2. Текущая сборка R01 (`claude/sharp-dijkstra-0t87gl` @ bc7c961) запущена, сценарий демо пока не проходит (ожидаемо до B1).
3. Дефекты → `research/round-14-results/R10/BUGS.md` (B-001…B-006).

## Следующий шаг
1. `tests/civic/R10/accuracy.py` + `test_r10_accuracy.py` — независимая проверка CONTRACT §8 по данным всех модулей
   (граф OSM как эталон, граница — `data/civic/astana/geofence.json`).
2. `tests/e2e/demo_flow.cjs` — 6 шагов сценария, 1366/375 × ru/kk, скриншоты; прогон на текущей R01 → `ACCEPTANCE_PRE_B1.md`.
3. UX-чек-лист по экранам; `CODEX_ACCEPTANCE_PROMPT.txt`; DELIVERY.json, RUN.txt, INTEGRATION.txt.
4. 13 окт вечер — B1 (SHA в STATUS.md R01) → `ACCEPTANCE_B1.md`; 14-го B2; 15-го FINAL.

## Как воспроизвести мои проверки
- Ветки ролей — в `DELIVERIES_CHECK.md` (SHA). Каждую — в отдельный worktree: `git worktree add --detach <папка> origin/<ветка>`.
- pytest нужен в том же Python, что и `python3` (`pip install --user pytest`), Playwright — глобальный npm
  (`NODE_PATH=$(npm root -g)`).
- Стенды: R07 `python3 -m ui.civic_heat.devserver` (8617); R08 `python3 tests/civic/R08/demo_server.py` (8508, нужен R07 —
  запускать из сборки R01); R06 `serve_r14.py --port 8616 --age-days 16 --kit-dir <выгрузка web/civic/ui-kit и i18n из R11>`.
