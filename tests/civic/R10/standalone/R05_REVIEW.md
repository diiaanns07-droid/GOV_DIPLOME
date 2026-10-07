# R10 independent review of R05: Astana data, sources and licences (round 11, M04)

- **Pinned SHA:** `e477e5d31ab232cc0e7a9e7310e0ce56c70f387b`. This was the head of `origin/claude/intelligent-sagan-7shpeh` when fetched on 2026-10-06. It is newer than the `eebb1a1` named in the task and adds checkpoints 2–4 plus `NEXT_SOURCES.md`.
- **Expectations:** `9c2f5c0:research/round-11/CONTRACT.txt` §1 and §7, and `9c2f5c0:research/round-11/prompts/R05.txt`.
- **Isolation:**
  - Detached worktree at `<scratchpad>/wt-r05-e477e5d`. It stayed clean after all runs (`git status --short` showed 0 lines).
  - Product code ran only under `python3 -I -B` with cwd = worktree and `sys.path[0]` = worktree.
  - Imported modules:
    - `data/civic/astana/tools/civic_v1.py`
    - `build_slice.py`
    - `import_helper.py`
    - `build_geofence.py`
    - `schedule_diff.py`

    All paths are under the worktree.
  - Every tool was read before it ran. They are stdlib only, with no shell and no network.
  - `build_slice.main()` writes into the package and was never called. Only `build()` (read-only) was used, on temp copies made with `tempfile.mkdtemp()`, which were removed afterwards.
  - `probe_sources.py` is the network tool. It was neither imported nor run.
- **Files written by R10:**
  - `tests/civic/R10/standalone/r05_driver.py`
  - `tests/civic/R10/standalone/standalone_r05.py`
  - this file

## Commands and exit codes

| # | Command (cwd) | Exit | Result |
|---|---|---|---|
| 1 | `git -C /home/user/GOV_DIPLOME fetch origin claude/intelligent-sagan-7shpeh` | 0 | head e477e5d |
| 2 | `git worktree add --detach <sp>/wt-r05-e477e5d e477e5d…` | 0 | |
| 3 | (wt) `<sp>/venv-pytest/bin/python -I -B -m pytest -p no:cacheprovider tests/civic/R05 -q` | 0 | **84 passed** (their claim re-run) |
| 4 | (wt) `python3 -I -B -m unittest discover -s tests/civic/R05 -t tests/civic/R05` | 0 | Ran 84, OK |
| 5 | (wt) `python3 -I -B data/civic/astana/tools/build_slice.py --check` | 0 | `valid:true, changed:[]`, counts 0/0/9 |
| 6 | `curl -sS -m 20` against 8 official pages: openstreetmap.org/copyright, ODbL, OSMF attribution guidelines, openfreemap.org, openmaptiles.org, docs.overturemaps.org, gov.kz, astana.gov.kz | 56 | proxy `CONNECT tunnel failed, response 403` on all 8 |
| 7 | `curl -sS -m 25`, one try each, against the 7 raw.githubusercontent.com URLs that R05 marks `fetched` | 0 | 200 on all 7. sha256 identical to `sources.json`. Manifest: `<sp>/r05-lic-fetch/manifest.json` |
| 8 | (wt) `python3 -I -B tests/civic/R10/standalone/r05_driver.py <wt> <manifest>` | 0 | JSON observations |
| 9 | (repo) `R10_R05_ROOT=<wt> R10_R05_SHA=e477e5d… R10_R05_LICFETCH=<manifest> python3 -I -B tests/civic/R10/standalone/standalone_r05.py -v` | 1 | 20 run: 16 ok, 3 FAIL, 1 skipped (NOT_RUN) |
| 10 | (repo) same command without env | 0 | 20 skipped with "NOT_RUN: R10_R05_ROOT is not set" |

Note: `python3 -I -m unittest standalone_r05` cannot import the module, because `-I` drops cwd from `sys.path`. Use the script form shown in row 9.

**Their tests:** 84/84 pass, which matches STATUS.md checkpoint 4. `DELIVERY.json` still records the checkpoint-1 result ("32 passed"); see D3.

## R10 checks

| ID | Check | Result | Evidence |
|---|---|---|---|
| R10-R05-01 | PACK fixture under R05's contract/demo profiles and under R10 | PASS | sha `e2ba1de7…` matches. contract and demo profiles: 0 errors. R10: []. Real profile: `synthetic_in_real` |
| R10-R05-02 | R10 BAD_VARIANTS (22) | PASS | All 20 clear contract violations are rejected. The 2 disagreements fall where the contract is silent (table below) |
| R10-R05-03 | HTML in title; source_ref without `license` key | PASS | `text_html`, `missing_field` |
| R10-R05-04 | observed without a fetched source is refused for real data | PASS | Real profile: `no_fetched_source`. A hash-consistent smuggled `objects.json` is rejected at import |
| R10-R05-05 | Expected end never becomes `actual_end` | PASS | Validator: `actual_end_after_publication` / `actual_end_in_future`. Builder: IntakeError. schedule_diff: `rejected_actual`, `auto_applied:false`, `original_planned_end` never proposed |
| R10-R05-06 | Old announcement is not shown as current | PASS | `stale_status` (source from 2025-03-01). Old planned item is rejected by import_helper. An old completion goes to `historical.json` |
| R10-R05-07 | Future announcement does not produce a current in_progress/completed status | **FAIL** | See D1 |
| R10-R05-08 | Budget/geometry provenance | PASS | `budget_unlinked` + `unfetched_support`; `budget_zero`; `proprietary_geometry` (2gis); IntakeError on an unfetched source. Control records pass |
| R10-R05-09 | Import creates drafts only | PASS | Actions = {create}, `publication_after` = draft, no publish/archive action. `create_body` has no id/revision/updated_at/publication |
| R10-R05-10 | Re-import is idempotent | PASS | Build is deterministic. Committed files equal a rebuild. Digests are stable. Re-import gives `skip_unchanged` |
| R10-R05-11 | No overwrite and no auto-archive | PASS | Changed published or hand-edited records go to `editor_review`. A record absent from the package gets `report_missing` |
| R10-R05-12 | Smuggled records (consistent hash) | PASS | synthetic → `synthetic_in_real`; swapped coordinates → `geometry_swapped` |
| R10-R05-13 | Fail closed without geofence | **FAIL** | See D2 |
| R10-R05-14 | Geofence is plausible | PASS | bbox [71.218, 50.931, 71.785, 51.351]. 9 rings, all closed, all 2D, lon>lat throughout. outer = bbox ± 0.05. ODbL + OSM attribution present |
| R10-R05-15 | Geofence point checks and rebuild | PASS | Baiterek, Khan Shatyr and Ak Orda are inside. Almaty, Karaganda, Kokshetau and swapped Baiterek are outside, with R05 and an independent R10 ray-casting agreeing. `build()` rebuilds the committed file exactly. Input sha `9092aebb…` matches |
| R10-R05-16 | Sources match the fetch audit | PASS | 28 sources: 7 fetched, 21 not_fetched. Required keys are present. 0 mismatches against `fetch_audit_a/b` (status, sha256, retrieved_at). No host that got 403 is marked fetched |
| R10-R05-17 | No unbacked real records; licence register consistent | PASS | objects/historical contain 0 items. All 9 demo records are synthetic, labelled "Демо", with no source_refs and no budget. Licence register: 0 status or sha inconsistencies |
| R10-R05-18 | R10 re-fetch of licence texts | PASS | 7/7 sha256 identical (fetched 2026-10-06T15:56:54Z) |
| R10-R05-19 | Official licence pages | NOT_RUN | proxy 403 on all 8 official pages. Nothing compared, nothing assumed |
| R10-R05-20 | DELIVERY.json is current | **FAIL** | See D3 |

## Validator cross-check: R05 `civic_v1` vs R10 `contract.check_object`

R05 was run with profile=contract and the geofence loaded.

| Variant | R05 | R10 | Contract says | Decision |
|---|---|---|---|---|
| end before start (`current_planned_end` < `planned_start`) | warning `schedule_order` | reject | nothing about date order | Contract is silent. Both readings are acceptable; R05 does surface it |
| `basis=contract` with `amount_kzt` null | warning (contract profile), error (real profile) | reject | the basis/amount pair is not defined | Contract is silent. R05's real profile is strict |
| `geometry=null` with `precision=source` (extra variant) | warning (contract), error (real) | reject | silent | Contract is silent |
| observed with `source_refs=[]` (extra) | **accept** (contract profile); real profile rejects | reject | "Отсутствие … provenance не маскировать" | **R10's reading is safer.** See D4 (low) |
| observed supported only by a not_fetched source (extra) | warning (contract), error (real) | accept | the R05 prompt says observed means fetched content | R05's real profile is right; R10 misses this |
| HTML in title (extra) | reject `text_html` | **accept** | "plain text, без HTML" | **R05 is right.** Gap in R10's checker: `TAG_RE` is defined but never used |
| 3D position `[lon, lat, alt]` (extra) | reject | accept | "[longitude,latitude]" | R05 follows the literal text |
| phone number in description; fetched source without `retrieved_at` (extra) | reject | accept | not explicit | R05 is stricter; reasonable |
| swapped coordinates / other city, with **no geofence** | **accept** | reject (fixed bbox) | city=astana, [lon,lat] | R10 is right. See D2 |

## Licence table

"Official page" status is NOT_RUN wherever proxy 403 blocked the page, so nothing on those pages was compared or assumed. The GitHub texts come from branch heads (main/master), not pinned commits. Identity holds only for 2026-10-06 15:56Z.

| Component | What R05 claims | R10 status | Basis |
|---|---|---|---|
| OSM data | ODbL-1.0. Attribution "© OpenStreetMap contributors" with a link to /copyright. ODbL §4.2/4.3/4.4/4.6 obligations | **CLAIMED** | openstreetmap.org/copyright: NOT_RUN (403). Saved ODbL text at `b2cb2e0` has sha `77d2692c…`, which matches the register. The attribution form is VERIFIED in the OpenMapTiles LICENSE.md example and the OpenFreeMap README |
| ODbL legal text | ODbL-1.0 | NOT_RUN (official page); saved copy identity VERIFIED | opendatacommons.org: 403 |
| OSMF tile servers | No bulk scraping; not used by the project | NOT_RUN | 403. R05 itself marks this `not_verified`, which is honest |
| OpenFreeMap | Attribution required (added automatically by MapLibre); MIT; data from OSM | **VERIFIED** (GitHub README/LICENSE); site NOT_RUN | Same sha. Text: "Attribution is required. If you are using MapLibre, they are automatically added" |
| OpenMapTiles | Code BSD-3-Clause; design CC-BY-4.0; visible credit "© OpenMapTiles" | **VERIFIED** (GitHub LICENSE.md); openmaptiles.org NOT_RUN | Same sha. Text: "need to visibly credit … OpenMapTiles … link to http://openmaptiles.org/" |
| Overture | "© OpenStreetMap contributors, Overture Maps Foundation" | **VERIFIED** (attribution.mdx); docs site NOT_RUN | Same sha |
| Overture per-theme licences | places: CDLA-Permissive-2.0 (meta) and Apache-2.0; TomTom present | **CLAIMED** | Consistent with the saved `web/govtech/core/attribution/attribution.json` at `b2cb2e0`. `_generated_attribution.mdx` was not fetched |
| MapLibre GL JS | BSD-3-Clause | **VERIFIED** | Same sha |
| gov.kz / news terms (real objects) | Unknown → `needs_rights_check`, cite only, do not copy | NOT_RUN | 403. R05 marks this `not_verified`, which is honest |
| Google/2GIS/Yandex | Prohibited as a geometry source | n/a (rule) | Enforced by `proprietary_geometry` |

Checked against the `b2cb2e0` app snapshot, `ATTRIBUTION.txt` and the R01 integration notes are accurate:
- `#gov-attribution` text is "Данные: Overture Maps · OSM · Meta · TomTom".
- The OpenFreeMap style in `web/map.js` is `liberty`.
- `plan-ui.js:526` and `resilience-ui.js:151` point to `web/attribution/ATTRIBUTION.md`, but the file is actually at `web/govtech/core/attribution/`.

## Sources: other notes (no defect)

- `src-osm-copyright` is not_fetched but carries `license: "ODbL-1.0"` with `license_status: from_saved_copy_and_secondary_official_texts`. The basis is stated, so the status is CLAIMED, not fetched.
- 8 not_fetched portal sources have `publisher: null` (honest "unknown"). CONTRACT §1 explicitly allows null only for `license`. This is harmless today because none of them appears in any `source_refs`.
- 4 audit URLs are not in the registry: github.com, api.github.com, and two 404 OSM-operations paths. These were probes, not sources.
- The demo slice carries `publication` = published/draft/archived as a suggestion only. import_helper always plans `create` → draft.

## DEFECT candidates

**D1. Medium: a future announcement can enter the current slice as `status=in_progress`.**
- **Repro.** On a temp copy of the package:
  1. Add a source `src-r10-future` to `sources.json` with `access_status=fetched`, `published_on=2026-10-01`, `retrieved_at`, `sha256`.
  2. Add `intake/real/r10-0.json` with `id=ast-r05-roadworks-r10-future` and two claims, both of type `expected` with quote "работы начнутся 1 ноября":
     - `{"field":"status","value":"in_progress","claim_type":"expected"}`
     - `{"field":"schedule.planned_start","value":"2026-11-01","claim_type":"expected"}`
  3. Run `build_slice.build(pkg)`, then `import_helper.load_package(pkg)`.

  The same gap shows directly in `civic_v1.validate_object(profile="real", as_of="2026-10-06")` for:
  - `status=in_progress` with `planned_start=2026-11-01`;
  - `status=completed` with `planned_start=2026-12-01`.
- **Expected.** These quotes govern:
  - CONTRACT §1: "Публикация старого плана не доказывает фактическое состояние или завершение работ".
  - R05.txt: "Без подтверждения состояния status=unknown"; "Различай фактическое завершение и прошлую ожидаемую дату".

  An `expected` claim cannot set a current state other than `planned`. A start date after `as_of` contradicts in_progress/completed.
- **Actual.**
  - `objects.json` contains `status:"in_progress"`, `planned_start:"2026-11-01"`.
  - `validation.valid: true`, no error codes.
  - import_helper puts it in `items` (create), with `rejected: []`.
  - The validator returns no errors for either status variant (only an `original_end_unknown` warning).
  - Only `status=completed` requires `reported_actual` (build_slice.py:155).
- **Mitigation present.** The record arrives as a draft, so an editor still has to publish it.

**D2. Low: validation and import fail open when `geofence.json` is missing.**
- **Repro.**
  1. Copy the package and delete `geofence.json`.
  2. Put a real record into `objects.json`: observed, fetched source, geometry `Point [51.17, 71.43]` (lat/lon swapped), `precision=approximate`.
  3. Recompute `slice.content_sha256` and `version` with the README formula.
  4. Run `import_helper.load_package(copy)`.
- **Expected.** CONTRACT §1 says "WGS84 [longitude,latitude]" and `city: "astana"`. R05's README says "перепутанные lon/lat — ошибка". With the geofence present, the same record is rejected with `geometry_swapped`.
- **Actual.** `{"items":["ast-r05-roadworks-r10-test"],"rejected":[]}`. `cv.load_geofence()` returns None silently, and every geofence rule is skipped. The CLI `--geofence <bad path>` behaves the same way.

**D3. Low: `DELIVERY.json` is stale against the delivered head (CONTRACT §7).**
- **Repro.** `git show e477e5d:research/round-11-results/R05/DELIVERY.json`
- **Expected.** It should describe the delivery: `integration_notes` pointing at existing notes, and current `checks`.
- **Actual.**
  - `integration_notes`: "research/round-11-results/R05/INTEGRATION.txt (to be written)", although the file exists since b2c7c8e.
  - `checks` holds only the checkpoint-1 entry "32 passed" (now 84).
  - `code_commit: null`.
  - `next_step` lists work that is already done.

  R01 MATRIX could import a wrong state.

**D4. Low: the `contract` profile accepts `evidence_type=observed` with no source_refs.**
- **Repro.** `cv.validate_object(PACK fixture with evidence_type="observed", profile="contract", fence=geofence)`
- **Expected.** CONTRACT §1: "Отсутствие budget/status/provenance не маскировать". `civic_v1.py`'s docstring says this profile is "what any civic-v1 consumer such as R02 must accept or reject".
- **Actual.** No error and no warning. With only a not_fetched supporting source, it gives just the warning `unfetched_support`. The real profile and import_helper do reject both cases, so the impact is limited to consumers that use profile=contract as their gate.

## Gaps on R10's side (not R05 defects)

These are for the R10 lead:
- `r10lib/contract.check_object` does not reject HTML in title/description. `TAG_RE` is defined but never used, although CONTRACT says "без HTML".
- It accepts 3-element positions, although CONTRACT says `[longitude,latitude]`.
- It does not flag observed records backed only by not_fetched sources.
