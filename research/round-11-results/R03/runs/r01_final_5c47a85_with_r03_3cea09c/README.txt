R03 final files inside R01's final integrated build (read-only for R01; nothing pushed to R01's branch).

Build: R01 branch claude/affectionate-ride-bol5v8 @ 5c47a85 ("R01 r11 final", CODE_SHA a5d184b), checked out in a
scratch git worktree. Only web/civic/map/{civic-map-core.js,civic-map.js,civic-map.css} were replaced by
R03 commit 3cea09c (byte-identical, verified with cmp). R01's own flow, unmodified:
  NODE_PATH=$(npm root -g) node tests/civic/R01/browser/p0_flow.cjs <out>
p0_flow.json                              49 PASS / 0 FAIL / 2 NOT_RUN (same counts as R01's final run)
p0_flow_without_r01_css_adapter.json      49 PASS / 0 FAIL / 2 NOT_RUN with R01's temporary adapter rule
                                          (.civic-r03-root .civic-r03-btn-primary {color:#fff} in shell.css)
                                          removed: «Задать вопрос по объекту» is rgb(255,255,255) on rgb(21,44,38).
NOT_RUN in both: OpenFreeMap basemap/3D buildings and mobile attribution (host blocked in this sandbox).
Screenshots 04/10/11 are from the run without the adapter.
