// K07 round 9: N2 assessment — is the horizontal scroll of the Pareto table at 390 px an accessibility problem?
// REVIEW r9: a local horizontal scroll is not an error by itself; judge keyboard access and loss of information.
// Usage: node k07r9_n2_scroll.cjs --app-root <BUILD extraction> [--label …] [--sha …] [--out …]
// Checks (390×844, Chromium): N2a the table really overflows (precondition); N2b no data loss — every cell has text, none is
// clipped by text-overflow, each cell can be scrolled fully into the visible part of its scroll container; N2c keyboard —
// the scroll container is reached by Tab from «Найти точные оптимумы» and ArrowRight scrolls it; N2d (advisory, not a
// verdict) — the container has a role and an accessible name. Data: BUILD's own SYNTHETIC demo set.
const path = require("path"), fs = require("fs"), { pathToFileURL } = require("url");
const { chromium } = require("playwright");
const a = process.argv.slice(2), OPT = { label: "n2", sha: null, out: null, appRoot: null };
for (let i = 0; i < a.length; i++) { const k = a[i], v = a[i + 1]; if (k === "--app-root") { OPT.appRoot = v; i++; } else if (k === "--label") { OPT.label = v; i++; } else if (k === "--sha") { OPT.sha = v; i++; } else if (k === "--out") { OPT.out = v; i++; } else { console.error("unknown argument " + k); process.exit(2); } }
const ROOT = path.resolve(OPT.appRoot), WEB = fs.existsSync(path.join(ROOT, "web")) ? path.join(ROOT, "web") : ROOT;
const OUT = path.resolve(OPT.out || path.join(__dirname, "..", "results", OPT.label));
const checks = [];
const check = (id, expect, ok, observed, pre) => checks.push({ id, expect, verdict: pre === false ? "TEST_INCOMPATIBLE" : ok ? "PASS" : "FAIL", observed });

(async () => {
  fs.mkdirSync(path.join(OUT, "screenshots"), { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } }), p = await ctx.newPage(), errors = [];
  p.on("pageerror", (e) => errors.push(String(e)));
  await p.goto(pathToFileURL(path.join(WEB, "index.html")).href);
  await p.waitForSelector("#map g[data-id]");
  await p.click('#toolSeg button[data-tool="v2"]');
  await p.click("#plDemo");
  await p.click("#plRun");
  await p.waitForFunction(() => window.CITY_PLAN_UI.opt.status === "done", null, { timeout: 20000 });
  const info = await p.evaluate(() => {
    const t = document.getElementById("plPareto"); if (!t) return null;
    // the nearest ancestor that scrolls horizontally (BUILD: div.tablewrap)
    let w = t.parentElement; while (w && w !== document.body && !(w.scrollWidth > w.clientWidth + 1 && /auto|scroll/.test(getComputedStyle(w).overflowX))) w = w.parentElement;
    const scroller = w && w !== document.body ? w : null;
    if (scroller) scroller.setAttribute("data-k07-scroller", "1");
    return { overflow: !!scroller, scrollWidth: scroller && scroller.scrollWidth, clientWidth: scroller && scroller.clientWidth,
      role: scroller && scroller.getAttribute("role"), name: scroller && (scroller.getAttribute("aria-label") || scroller.getAttribute("aria-labelledby")), tabindex: scroller && scroller.getAttribute("tabindex"),
      tableName: t.getAttribute("aria-label"), cells: t.querySelectorAll("td").length };
  });
  check("N2a", "precondition: at 390 px the Pareto table overflows its card horizontally (otherwise N2 does not apply)", !!info && info.overflow, info, !!info);
  if (info && info.overflow) {
    // N2b: no data loss — every cell can be brought fully into view inside the scroller
    const loss = await p.evaluate(() => {
      const s = document.querySelector("[data-k07-scroller]"), sr = s.getBoundingClientRect(), bad = [], empty = [];
      for (const td of document.querySelectorAll("#plPareto td, #plPareto th")) {
        const cs = getComputedStyle(td);
        if (!td.textContent.trim() && td.tagName === "TD") empty.push(td.cellIndex);  // e.g. «Совпадает с целью»: empty = no strategy; reported, not a loss
        if (cs.textOverflow === "ellipsis" || (cs.overflow === "hidden" && td.scrollWidth > td.clientWidth + 1)) bad.push({ cell: td.cellIndex, text: td.textContent.slice(0, 20), why: "clipped" });
        s.scrollLeft = Math.max(0, td.offsetLeft - 4);
        const r = td.getBoundingClientRect(), vis = s.getBoundingClientRect();
        if (r.width > vis.width + 1) bad.push({ cell: td.cellIndex, why: "wider than the visible area" });
        else if (r.left < vis.left - 1 || r.right > vis.right + 1) {
          s.scrollLeft = Math.max(0, td.offsetLeft + r.width - vis.width + 4);
          const r2 = td.getBoundingClientRect();
          if (r2.left < vis.left - 1 || r2.right > vis.right + 1) bad.push({ cell: td.cellIndex, text: td.textContent.slice(0, 20), why: "cannot be scrolled fully into view" });
        }
      }
      s.scrollLeft = 0;
      return { bad: bad.slice(0, 10), n: bad.length, visibleWidth: Math.round(sr.width), emptyCellsByColumn: empty.reduce((o, c) => (o[c] = (o[c] || 0) + 1, o), {}) };
    });
    check("N2b", "no information loss: no Pareto cell is clipped and every cell can be scrolled fully into view (empty cells are reported, not counted)", loss.n === 0, loss);
    // N2c: keyboard — Tab from «Найти точные оптимумы» reaches the scroller (or a focusable element inside), ArrowRight scrolls it
    await p.focus("#plRun");
    let tabs = 0, reached = false;
    for (; tabs < 40; tabs++) {
      await p.keyboard.press("Tab");
      reached = await p.evaluate(() => { const s = document.querySelector("[data-k07-scroller]"); return !!s && (document.activeElement === s || s.contains(document.activeElement)); });
      if (reached) break;
    }
    const x0 = await p.evaluate(() => document.querySelector("[data-k07-scroller]").scrollLeft);
    const focused = await p.evaluate(() => { const e = document.activeElement; return e.tagName + (e.className ? "." + e.className : ""); });
    if (reached) { for (let i = 0; i < 3; i++) await p.keyboard.press("ArrowRight"); await p.waitForTimeout(500); }  // keyboard scrolling may animate
    const x1 = await p.evaluate(() => document.querySelector("[data-k07-scroller]").scrollLeft);
    check("N2c", "keyboard: the scroll container is reached by Tab from «Найти точные оптимумы» and ArrowRight scrolls it horizontally", reached && x1 > x0, { tabs: reached ? tabs + 1 : ">40", focused, scrollLeft: [x0, x1], focusableByAttribute: info.tabindex, note: "Chromium ≥130 makes scrollers without focusable children keyboard-focusable; other browsers need tabindex=0" });
    await p.locator("[data-k07-scroller]").scrollIntoViewIfNeeded();
    await p.screenshot({ path: path.join(OUT, "screenshots", "N2_390_pareto.png") });
  }
  await browser.close();
  const advisory = info && info.overflow ? { role: info.role, name: info.name, tabindex: info.tabindex, recommended: !(info.role && info.name && info.tabindex === "0"), text: "for screen readers and non-Chromium keyboards: role=region, aria-label and tabindex=0 on the scroll container" } : null;
  const by = (v) => checks.filter((c) => c.verdict === v).map((c) => c.id);
  const out = { kind: "K07 r9 N2 assessment (horizontal scroll of the Pareto table at 390 px)", label: OPT.label, sha: OPT.sha, app_root: path.basename(ROOT),
    total: checks.length, pass: by("PASS"), fail: by("FAIL"), test_incompatible: by("TEST_INCOMPATIBLE"), advisory_N2d: advisory, errors, checks };
  fs.writeFileSync(path.join(OUT, "result.json"), JSON.stringify(out, null, 1) + "\n");
  for (const c of checks) console.log(`${c.verdict} ${c.id} ${c.expect}${c.verdict === "PASS" ? "" : "  -> " + JSON.stringify(c.observed).slice(0, 300)}`);
  console.log("N2d (advisory): " + JSON.stringify(advisory));
  console.log(`PASS ${out.pass.length} · FAIL ${out.fail.length} · TEST_INCOMPATIBLE ${out.test_incompatible.length} of ${out.total}`);
  process.exitCode = out.fail.length ? 1 : 0;
})().catch((e) => { console.error(e); process.exit(2); });
