# R03 · round 12 · Публичная карта, полезные карточки и понятные фильтры — handoff

- Role: R03. Branch: `claude/zen-mendel-e79iiv` (session branch). Origin: https://github.com/diiaanns07-droid/GOV_DIPLOME
- CODE_BASE_SHA: `56538a3a7504d4589c38ab4d3c5107f12aa7f8a6` (codex/govtech-main-interface). Round-12 package read from origin/codex/govtech-main-interface @ 19f90e6.
- Base switch: the session branch (round 11 on old main) was brought onto CODE_BASE_SHA by a normal merge commit `0b5bd2c`
  (no reset, no force push). The only conflict, web/civic/map/civic-map.js, was resolved to the base version
  (= R03 3cea09c + coordinator's onData call). After the merge the branch differs from 56538a3 only by R03 round-11
  result files; the round-12 patch is `git diff 56538a3a -- web/civic/map tests/civic/R03`.
- Owned paths: web/civic/map/ (except streets.json), tests/civic/R03/, research/round-12-results/R03/, this file.

## Status: PARTIAL — checkpoint 1

Done:
- Honest empty state when a street/district is chosen (shell calls setFilters({area:true})) and no record is there:
  «В видимой части карты нет опубликованных записей. Это не значит, что здесь не ведутся работы: реестр неполный…»
  with «Показать записи по всему городу». Demo note says plainly that no confirmed real works are in the registry.
- Bug fixed: setFilters({area:true}) without a later map move left the view box unset, so the list silently showed
  the whole city under the "visible part" filter.
- Stand moved into my path: tests/civic/R03/stand/ (served by tests/civic/R03/serve.mjs).
- Tests: core 24/24; browser 44/44 (+1 r12 test); R02 read-only 2/2.

Next step: card — short summary first, «изначально / сейчас / фактически», cost/responsible only with a source.
