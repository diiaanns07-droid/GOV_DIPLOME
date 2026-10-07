# R03 · round 11 · Публичная карта, карточки и светлый интерфейс — handoff

- Role: R03 (only this role). City: Astana.
- Branch: `claude/zen-mendel-e79iiv` (session branch; origin https://github.com/diiaanns07-droid/GOV_DIPLOME)
- Base HEAD at start: `834a25fb860dd5514d02c9274b70d7bf8a53a79c` (main snapshot; no reset/merge done)
- PACK_SHA: `9c2f5c0dae14b46c0697a9dfc7f854351bfd570d` (origin/codex/govtech-main-interface, fetched 2026-10-06; PACK_STATUS=READY)
- Source app compared: `b2cb2e02c602c166ba6d47c02d8e902e5478c791` (claude/beautiful-clarke-sbzomj) — read via `git show`, not checked out.
- Owned paths: `web/civic/map/`, `tests/civic/R03/`, `research/round-11-results/R03/`, this file.

## Status: DONE (ready for R01 re-import) — checkpoint 8

Code: `web/civic/map/` @ **3cea09c** (DELIVERY `code_commit`). The documentation commit after it changes no code.

What works (module):
- `window.CivicMap.mount({root,map,api,onSelect,onFeedback}) -> {refresh,selectObject,destroy}` on the one MapLibre map; auto layout:
  overlay (own side panel / bottom sheet) when root is a child of <body>, embedded inside R01's `#civic-map-root`.
- Find an object: map (Point/LineString/Polygon; null geometry list-only) or list with search, kind chips, status, planned period, visible part.
- What changed with the deadline: first vs current planned end, shift in days, reason from the published history, history timeline,
  comparison of two revisions; historical plans and synthetic records marked in list, card and map.
- Card: purpose, status (with source date if a source covers it), dates, organisation/contact, money with basis and source (never for
  synthetic records), place precision, safe source links, notes, «запись обновлена» in Astana time, «Задать вопрос» -> onFeedback.
- States: loading / error + retry / empty / reset; stale responses dropped and superseded requests aborted; mount/destroy leak-free.

Verified (all PASS, commands in DELIVERY.json):
- core 24/24, browser stand 43/43, R02 CivicService read-only 2/2 (`node --test ... tests/civic/R03/*.test.mjs`).
- R01's own P0 flow on R01's final build 5c47a85 with these files: 49 PASS / 0 FAIL / 2 NOT_RUN, also without R01's CSS adapter.
- Two adversarial review passes (14 agents): 46 confirmed findings fixed; which ones have discriminating tests is measured in
  `research/round-11-results/R03/REVIEW_FINDINGS.json`.

NOT_RUN: OpenFreeMap basemap, attribution text and 3D buildings (sandbox proxy 403).
Remaining risk: R01 currently ships R03 1bc9c48 (before the second pass) until it re-imports 3cea09c; real Astana data not shown
(all synthetic); client-side filtering is sized for city-level lists (≤ 20 API pages).

Next step: R01 re-imports the three files @3cea09c per `research/round-11-results/R03/INTEGRATION.txt` §0 and removes its
`.civic-r03-btn-primary` adapter; R10 checks the integrated CODE_SHA.
