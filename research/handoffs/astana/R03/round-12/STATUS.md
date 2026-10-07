# R03 · round 12 · Публичная карта, полезные карточки и понятные фильтры — handoff

- Role: R03. Branch: `claude/zen-mendel-e79iiv` (session branch). Origin: https://github.com/diiaanns07-droid/GOV_DIPLOME
- CODE_BASE_SHA: `56538a3a7504d4589c38ab4d3c5107f12aa7f8a6` (codex/govtech-main-interface). Round-12 package read from origin/codex/govtech-main-interface @ 19f90e6.
- Base switch: the session branch (round 11 on old main) was brought onto CODE_BASE_SHA by a normal merge commit `0b5bd2c`
  (no reset, no force push). The only conflict, web/civic/map/civic-map.js, was resolved to the base version
  (= R03 3cea09c + coordinator's onData call). After the merge the branch differs from 56538a3 only by R03 round-11
  result files; the round-12 patch is `git diff 56538a3a -- web/civic/map tests/civic/R03`.
- Owned paths: web/civic/map/ (except streets.json), tests/civic/R03/, research/round-12-results/R03/, this file.

## Status: PARTIAL — checkpoint 4

Done:
- Checkpoint 1 (d72058a): honest empty state for a street/district without records; area filter measured on setFilters; stand in tests/civic/R03/stand/.
- Card: «Коротко» block first — Сейчас (status, «по источнику от …» or «по записи», plan-passed warning) / Когда закончат
  (до …, «перенесён на N дней», завершено/отменено, «новый срок не опубликован») / Кто отвечает / Откуда сведения;
  moved deadline with its reason right under it; dates «Начало / Изначально — до / Сейчас — до / Фактически».
- Cost and responsible only when a source covers them (budget.source_id or source fields; «responsible» covers its children);
  otherwise plain text («не подтверждено источником», «сумма … источник не указан — не показываем»).
- Sources: short list (name, date, safe link); technical provenance (received, access, licence, covered fields, type,
  notes, record updated/revision) folded into «Подробнее о сведениях».
- «Скопировать ссылку» always available; default link format is the R01 shell's #object=<id> (host may pass linkFor);
  clipboard failure shows a selectable field.
- Before screenshots of the real app (base 56538a3, R05 demo slice): research/round-12-results/R03/screenshots/before-app-*.png
- Tests: core 25/25, browser 45/45, R02 read-only 2/2.

- Checkpoint 3: filters folded by default (≥3 objects visible at 1440x900 without scrolling); active filters as removable
  pills; new filters «Сведения» (с источником / демонстрационные / без источника) and «Скрыть планы с прошедшим сроком»;
  counts in status and «Сведения» options and kind chips follow all other filters (status counts add up to the list);
  list badge «С источником»; overlapping objects: a click on several objects opens «Здесь N объектов рядом» in the panel
  (keyboard, Escape/«Отмена» back to the previous card/list, «Приблизить все», candidates outlined on the map);
  back to the list restores scroll position and focus.
- Tests: core 25/25, browser 49/49, R02 read-only 2/2.

- Checkpoint 4: list requests limit=100 (R02 max; retried without it on 400/422) — before, R02's default 50 × 20 pages
  silently truncated the list at 1000 records. Density (synthetic, generated inside the test only, never in a registry):
  500 objects load 69 ms, 2000 objects 380 ms (21 pages incl. initial load); filter change 11–29 ms; list renders 200 rows
  with «Показать ещё»; every object with geometry is drawn and stays clickable. onData contract kept (one call per
  successful load, {evidence} only). 320x640 phone: no horizontal scroll.
- R01's own P0 flow in this branch (= base + R03): 57 PASS / 2 FAIL / 2 NOT_RUN — identical to the clean base 56538a3
  (same 2 FAIL in R01-owned explore buttons / attribution slot): research/round-12-results/R03/runs/.
- Tests: core 25/25, browser 53/53, R02 read-only 2/2.

Next step: adversarial review of the round-12 diff; after-screenshots of the real app; RUN.txt, INTEGRATION.txt, DELIVERY.
