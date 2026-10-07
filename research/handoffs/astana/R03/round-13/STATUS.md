# R03 · round 13 · Карта без конфликтов инструментов, удобные карточки и 3D — handoff

- Role: R03. Branch: `claude/zen-mendel-e79iiv` (same session branch, continued; no reset).
- Pinned start (round-13 prompt): d5ee7586592b743db0e4ab31a057e53bc4bc7fab (round-12 checkpoint 5).
- REFERENCE_BASE_SHA: 56538a3a7504d4589c38ab4d3c5107f12aa7f8a6 (comparison base, not a reset target).
- Round-13 package read from origin/codex/govtech-main-interface @ c076569 (ROLES, DELIVERIES, BASELINE, CHECKS).
- Neighbour sources read (not executed, not merged): R01 code 223296e (head 6dc1660) shell.js — fitBounds adapter,
  keepVisible, civic-editor:tool listener; R04 code 69d5691 (head 6d5cd71) editor.js + editor_mount_contract.json.
- Owned paths: web/civic/map/ (except streets.json), tests/civic/R03/, research/round-13-results/R03/, this file.

## Status: PARTIAL — checkpoint 1

### 0. Round 12 closed first (as the prompt asks)
- Round-12 code after the adversarial review: b83df899b6eb2e6d9afcd3cb4a7fad23ffacfae1; docs c69a7c0 (DELIVERY with
  code_sha, RUN, INTEGRATION, handoff DONE, review log). Pushed: origin/claude/zen-mendel-e79iiv = c69a7c0.
  (b83df89 alone was refused 6× by GitHub with `remote rejected … (Internal Server Error)` at ~17:00Z; access check
  said push allowed; the next push of c69a7c0 went through and carried b83df89.)

### 1. Contract fixed before implementation
research/round-13-results/R03/CONTRACT.txt — A) getPadding/getPitch/getBearing, Б) never fly over a host/resident
camera move, В) input ownership: handle.setInteractionEnabled(enabled, owner) + built-in civic-editor:tool /
civic-scenarios:tool listeners, Г) idempotent style reload with styleimagemissing.

### 2. Implemented (checkpoint 1)
- getPadding()/getPitch()/getBearing() options; validated (four finite numbers >= 0 / range), invalid -> own
  padding + one warning; clamped on low/narrow screens; also used for the «видимая часть карты» measurement.
- Own camera moves carry eventData {civicR03:true}; a foreign movestart cancels pending module moves (phone sheet
  delay, late fly after a deep-link card, chooser spot) and late fitOnLoad.
- setInteractionEnabled(enabled, owner) with an owner set; getState().interaction; document listeners for
  civic-editor:tool (R04, existing) and civic-scenarios:tool (proposal for R07), removed in destroy; an owner whose
  announcing element left the DOM is dropped on the next map input. While off: no select/chooser/onSelect (so no
  #object= change in R01), no tooltip, cursor left to the owner.
- styleimagemissing re-adds civic-r03-demo-ring.
- Tests (r13, 3 new): host padding/pitch/bearing + invalid fallback; host street fit cancels the pending phone fly;
  render -> setStyle(diff:false)+refresh race -> editor draws (crosshair kept, no select/onSelect/tooltip) -> second
  owner -> cancel -> select; detached editor does not lock; no listener growth over 3 remounts. Each test was
  mutation-checked (fails when the corresponding code is removed).

### 3. Checkpoint 2 (f514ff3) — real neighbours, not fixtures
- tests/civic/R03/r02_contract.test.mjs on R02's real CivicService bd7a911 (R02 round-12 code): 241 published
  records (11 R03 fixtures + 230 explicitly synthetic test records in a temp DB) by cursor in pages of 100; slow
  answer + filter chosen during loading; two refreshes in a row; object archived while its card is open; deep
  link + reload + «больше не опубликован»; identical points; no request per map move — 4/4 PASS.
- Chooser: records at exactly the same point no longer get «приблизьте карту» (zooming never separates them).
- tests/civic/R03/app_acceptance.mjs on the real app (app.py, base R01/R02/R04/R06 + this module): render -> 3D ->
  host style swap -> R04 editor draws a line over a public object -> Esc -> the same click selects; deep link ->
  reload; not-published link; phone. Branch: 12 PASS / 0 FAIL / 1 NOT_RUN (OpenFreeMap). Same script on the base
  module 56538a3: 2 FAIL (card opened and pointer cursor while drawing) — runs/ and screenshots before/after.

### 4. Checkpoint 3 (1428b08)
- onDetail(obj): the loaded card's public copy with geometry (R01's ask: deep link before the list) — no second
  onSelect. 3D test: click-select at pitch 55, fly keeps the tilt; three quick style swaps + remount mid-swap ->
  exactly 13 layers, demo ring symbol kept, no missing-image warning.
- INTEGRATION.txt, RUN.txt (run-city.bat read: PORT 8611, CIVIC_DEMO init+seed-demo; cloud equivalent),
  proposed_r01_shell.patch (to R01 223296e shell.js; R01's file untouched; `git apply --check` OK).

### Next
R01's own browser checks on 223296e with this module (with/without the patch), an independent review of the
round-13 diff, full suites on the final SHA, DELIVERY.json.
