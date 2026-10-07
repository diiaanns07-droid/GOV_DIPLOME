# R03 · round 12 · Публичная карта, полезные карточки и понятные фильтры — handoff

- Role: R03. Branch: `claude/zen-mendel-e79iiv` (session branch). Origin: https://github.com/diiaanns07-droid/GOV_DIPLOME
- CODE_BASE_SHA: `56538a3a7504d4589c38ab4d3c5107f12aa7f8a6` (codex/govtech-main-interface). Round-12 package read from origin/codex/govtech-main-interface @ 19f90e6.
- Base switch: the session branch (round 11 on old main) was brought onto CODE_BASE_SHA by a normal merge commit `0b5bd2c`
  (no reset, no force push). The only conflict, web/civic/map/civic-map.js, was resolved to the base version
  (= R03 3cea09c + coordinator's onData call). After the merge the branch differs from 56538a3 only by R03 round-11
  result files; the round-12 patch is `git diff 56538a3a -- web/civic/map tests/civic/R03`.
- Owned paths: web/civic/map/ (except streets.json), tests/civic/R03/, research/round-12-results/R03/, this file.

## Status: DONE (round 12) — final code b83df899b6eb2e6d9afcd3cb4a7fad23ffacfae1

Final (after checkpoint 5):
- Adversarial review of the round-12 diff (4 finders + verifiers): 35 findings, all fixed or documented —
  research/round-12-results/R03/REVIEW_FINDINGS.json. Main ones: the 400/422 retry without `limit` never ran
  (list would read «опубликованных объектов нет»); the area empty state claimed «нет опубликованных записей» when
  other filters hid records; a street pick flashed a false «нет записей» before R01's camera move; «завершено» without
  a date showed a future plan; the past-plan filter hid overdue works in progress; list scroll/focus lost in R01's
  panel and via the chooser; chooser unusable on 320px phones.
- Tests at b83df89: core 26/26, browser 60/60, R02 read-only 2/2 — PASS. R01 P0 flow with this module: 57/2/2,
  identical to the clean base (both FAIL R01-owned). OpenFreeMap/3D NOT_RUN (proxy 403).
- Correction: the checkpoint-4 note «browser 53/53» was a miscount (52 tests then). The density test checks that all
  objects with geometry reach the map source and that a sample click works; it does not click every object.
- DELIVERY.json, RUN.txt, INTEGRATION.txt updated to b83df89. Transfer by path only (the branch also carries R03's
  round-11 results).
- Push: see the section «Push» at the end of this file.

## Earlier: checkpoint 4

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

- Checkpoint 5 (d5ee758): RUN.txt, INTEGRATION.txt, after-screenshots of the real app.

Next step: round 13 (research/handoffs/astana/R03/round-13/STATUS.md).

## Push

- Last successfully pushed SHA before the final commits: d5ee7586592b743db0e4ab31a057e53bc4bc7fab (checkpoint 5).
- b83df89 (final code): `git push -u origin claude/zen-mendel-e79iiv` failed 6 times at 2026-10-07 ~16:59–17:02Z with
  `! [remote rejected] claude/zen-mendel-e79iiv -> claude/zen-mendel-e79iiv (Internal Server Error)` (GitHub request
  ID 2036:88825:1011611:151165A:6AC67A71). Repository access check: push allowed. b83df89 is pushed together with
  the commit carrying this file; the actual result is recorded in research/handoffs/astana/R03/round-13/STATUS.md.
