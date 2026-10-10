# R12 · раунд 14 · Точность карты — handoff

- Роль: R12 (точность карты). Ветка сессии: `claude/tender-brahmagupta-ef5ztl`.
- Основа: `claude/round-14-package` @ af77b78 (ветка сессии переставлена на неё до начала работы; своих коммитов до этого не было).
- Примечание о запуске: сообщение пользователя называло роль R12, но ссылалось на prompts/R11.txt. Выполняется
  prompts/R12.txt: роль названа явно и аккаунт s8 в ROLES.json закреплён за R12.
- Мои пути: engine/civic_geo/, data/civic/astana/geo/, web/civic/map/, web/civic/editor/, tests/civic/R12/,
  research/round-14-results/R12/, этот файл.

## Checkpoint 1 — восстановление (PARTIAL)
- web/civic/map/{civic-map-core.js,civic-map.js,civic-map.css} из claude/zen-mendel-e79iiv код f0a52f7 (голова 7de5e0b);
  streets.json не менялся (база).
- web/civic/editor/* из claude/intelligent-sagan-7shpeh @ 9c996c6.
- Прочитаны: research/handoffs/astana/R03/round-13/STATUS.md, research/round-13-results/R03/{DELIVERY,INTEGRATION,RUN}
  (на 7de5e0b); research/handoffs/astana/R04/round-13/STATUS.md (на 9c996c6).
- Тесты раунда 13 перенесены в tests/civic/R12/map/ (из tests/civic/R03 @ f0a52f7) и tests/civic/R12/editor/
  (из tests/civic/R04 @ 9c996c6) — пути к репозиторию поправлены на одну папку глубже. В раунде 14 tests/civic/R03 и R04
  принадлежат другим ролям, поэтому там ничего не меняю.
- Проверено на этой ветке (Linux, Node 22, Playwright глобально, Chromium /opt/pw-browsers):
  map core 26/26, map browser 69/69, editor core+mock 40/40, editor e2e+e2e_r13 39/39 — PASS.

## Дальше
engine/civic_geo (граф, индекс, ближайшее ребро, участок улицы, targets, проверки точности, CLI) → data/civic/astana/geo
→ demo_snapped.json и отрисовка → инструмент «Участок улицы» в редакторе → /targets.
