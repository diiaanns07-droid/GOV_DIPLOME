R03 · round 11 · Публичная карта, карточки и светлый интерфейс (Астана)

PRODUCT CODE (import these three, see INTEGRATION.txt)
  web/civic/map/civic-map-core.js   civic-v1 logic: normalisation, dates/money/time, filters, history, geometry checks
  web/civic/map/civic-map.js        window.CivicMap.mount({root,map,api,onSelect,onFeedback}) -> {refresh,selectObject,destroy}
  web/civic/map/civic-map.css       scoped .civic-r03-* styles on top of the original light UI tokens

TWO RESIDENT PATHS THE MODULE SERVES
  «Найти объект»: map or list (search, kind chips, status, planned period, visible part) -> card -> «На карте».
  «Что изменилось со сроком»: list badge «срок перенесён» -> card: first and current planned end, shift in days,
  reason from the published history, history timeline, comparison of two revisions.

VERIFICATION STAND (not the product; contract mock or R02 read-only)
  node tests/civic/R03/serve.mjs 8765
  http://127.0.0.1:8765/research/round-11-results/R03/stand/?today=2026-10-06
  params: basemap=offline | fail=list|card|all | empty=1 | hostile=1&leak=1 | extra=format | host=r01 | permalink=1 | persist=0
  R02 read-only: python3 -I tests/civic/R03/r02_readonly_server.py --r02-root <git archive of R02 ui/civic_store> ; open .../stand/?api=real

EVIDENCE INDEX
  DELIVERY.json                    checks PASS/NOT_RUN with commands
  INTEGRATION.txt                  files, server allowlist, index.html order, hook, events, API, map layers, styles
  REVIEW_FINDINGS.json             25 confirmed adversarial-review findings, how each was fixed, regression check
  screenshots/                     real Chromium screenshots of the stand (mock data or R02 read-only; OpenFreeMap blocked
                                   -> honest plain fallback). They show the module, not the integrated product.
  runs/r01_build_8c6add9_with_r03_161467d/   R01's own P0 flow on R01's integrated build with these R03 files (47/0/2)
  ../../handoffs/astana/R03/round-11/STATUS.md   handoff

TESTS
  node --test tests/civic/R03/core.test.mjs
  node --test --test-concurrency=1 tests/civic/R03/browser.test.mjs
  node --test --test-concurrency=1 tests/civic/R03/r02_readonly.test.mjs
  R03_SHOTS=research/round-11-results/R03/screenshots <same commands>   (re-generates the screenshots)

NOT_RUN: OpenFreeMap basemap streets and 3D buildings (sandbox proxy refuses the host). No facades, heights or traffic
are drawn by R03 in any case.
