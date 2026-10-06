Trial of the R03 review fixes inside R01's integrated application (read-only for R01).

What ran: R01's own browser flow tests/civic/R01/browser/p0_flow.cjs, unmodified, in a scratch
`git worktree` of R01's branch claude/affectionate-ride-bol5v8 @ 8c6add9 (R02 3d2b8b9, R04 da46e1c,
R05 e477e5d, R06 91f2508, R07 22fa413, R09 f895c30 as integrated by R01), with ONLY the three R03 files
web/civic/map/{civic-map-core.js,civic-map.js,civic-map.css} replaced by R03 commit 161467d.
Nothing was committed or pushed to R01's branch. Command (inside the worktree):
  NODE_PATH=$(npm root -g) node tests/civic/R01/browser/p0_flow.cjs <out_dir>
Result 2026-10-06T16:46Z: 47 PASS / 0 FAIL / 2 NOT_RUN (OpenFreeMap basemap + attribution: host blocked in
this sandbox) — identical counts to R01's own run with R03 f73745c (cp10), so the review fixes did not
break the integrated P0 path. p0_flow.json is the flow's own output; screenshots are from the same run.
Real R02 timestamps (UTC) are now shown in Astana time ("21:46 (время Астаны)" for 16:46Z).
Observation for R01 (not an R03 file): at 1440x900 the third footer button «Сообщения…» is cut off by
the panel edge (.civic-foot in web/civic/shell/shell.css).

Re-run with the final R03 files of commit 1c75a96 (161467d + one CSS rule hiding the empty list header above
an embedded card): 47 PASS / 0 FAIL / 2 NOT_RUN, same NOT_RUN reasons.
