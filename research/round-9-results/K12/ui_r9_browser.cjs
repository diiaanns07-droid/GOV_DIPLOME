// K12 round 9: browser checks on the ACTUAL build (file://, every non-file request aborted and counted).
//  group B (stage 2): city-resilience-v1 envelopes are refused by the v2 and v1 file imports without any state change;
//                     slice data (CITY_EVIDENCE) unchanged; a resilience UI, if present, is reported separately (NOT_RUN here).
//  group L (stage 3): late results — an optimum is not applied after a change of the selected plan / city made during or
//                     after the search; the template explanation is dropped when the manual selection changes.
//   NODE_PATH="$(npm root -g)" node ui_r9_browser.cjs --app-root <copy> [--groups B,L] [--out r.json]
// Page API used (BUILD d865dd4): CITY_PLAN_UI.{importText,startSearch,cancelSearch,applyPlan,toggleSelected,explainNow,opt,state},
// CITY_APP.{wiImportText,wiScenario,switchCity,ui.F}. If BUILD renames it, update this file (test error, not product error).
"use strict";
const fs = require("fs"), path = require("path");
const { pathToFileURL } = require("url");
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const APP = path.resolve(opt("--app-root", ""));
const GROUPS = new Set(opt("--groups", "B,L").split(","));
const OUT = opt("--out");
const HERE = __dirname;
const INDEX = path.join(APP, "web", "index.html");
if (!fs.existsSync(INDEX)) { console.error("usage: node ui_r9_browser.cjs --app-root <dir>"); process.exit(2); }
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { console.log(JSON.stringify({ verdict: "NOT_RUN", reason: "playwright not installed (NODE_PATH)" })); process.exit(0); }
const RS = JSON.parse(fs.readFileSync(path.join(HERE, "FIXTURES_RS_INDEX.json"), "utf8"));
const R8 = path.join(HERE, "..", "..", "round-8-results", "K12");
const R8IDX = JSON.parse(fs.readFileSync(path.join(R8, "FIXTURES_V2_INDEX.json"), "utf8"));
const r8fx = (id) => fs.readFileSync(path.join(R8, R8IDX.fixtures.find((f) => f.id === id).file), "utf8");

const results = [];
const check = (group, id, title, status, detail) => { results.push({ group, id, title, status, detail: detail === undefined ? null : detail });
  console.log(`${status.padEnd(7)} ${group}/${id} ${title}${status === "PASS" ? "" : " — " + JSON.stringify(detail).slice(0, 260)}`); };

(async () => {
  const browser = await chromium.launch(process.env.K12_CHROMIUM ? { executablePath: process.env.K12_CHROMIUM } : {});
  const page = await browser.newPage();
  const external = [], errors = [];
  await page.route("**/*", (route) => { const u = route.request().url();
    if (u.startsWith("file://") || u.startsWith("data:") || u.startsWith("blob:")) return route.continue();
    external.push(u); return route.abort(); });
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(pathToFileURL(INDEX).href);
  await page.waitForFunction(() => window.CITY_PLAN_UI && window.CITY_PLAN && window.CITY_APP);
  const v2btn = await page.$('#toolSeg button[data-tool="v2"]');
  if (v2btn) await v2btn.click();
  const snap = await page.evaluate(() => ({ shymkent: CITY_PLAN.sourceSnapshot(CITY_EVIDENCE, "shymkent", CITY_APP.ui.F),
                                            astana: CITY_PLAN.sourceSnapshot(CITY_EVIDENCE, "astana", CITY_APP.ui.F) }));
  const other = { shymkent: "astana", astana: "shymkent" };
  const sub = (t, city) => t.split('"__SNAPSHOT__"').join(JSON.stringify(snap[city])).split('"__SNAPSHOT_OTHER_CITY__"').join(JSON.stringify(snap[other[city]]));
  const dataHash = () => page.evaluate(() => CITY_APP.ui.F.sha256hex(JSON.stringify(CITY_EVIDENCE)));
  const planState = () => page.evaluate(() => { const U = CITY_PLAN_UI.state;
    return JSON.stringify(["category", "points", "cands", "budget", "max_selected", "radius", "required", "excluded", "selected"].map((k) => U[k])) + "|" + CITY_APP.state.city; });
  const hash0 = await dataHash();

  if (GROUPS.has("B")) {
    await page.evaluate((t) => CITY_PLAN_UI.importText(t), sub(r8fx("V01"), "shymkent"));   // a known v2 state to protect
    const s0 = await planState();
    const v1before = await page.evaluate(() => JSON.stringify(CITY_APP.wiScenario()));
    const bad2 = [], bad1 = [];
    for (const f of RS.fixtures.filter((x) => !x.recipe)) {
      const t = sub(fs.readFileSync(path.join(HERE, f.file), "utf8"), f.city);
      const r2 = await page.evaluate((x) => CITY_PLAN_UI.importText(x), t);
      if (r2 !== false || (await planState()) !== s0) bad2.push(f.id);
      const r1 = await page.evaluate((x) => CITY_APP.wiImportText(x), t);
      if (r1 !== false || (await page.evaluate(() => JSON.stringify(CITY_APP.wiScenario()))) !== v1before) bad1.push(f.id);
    }
    const n = RS.fixtures.filter((x) => !x.recipe).length;
    const msg = await page.evaluate(() => CITY_PLAN_UI.state.msg);
    check("B", "B1", `v2-импорт в UI отклоняет ${n} конвертов city-resilience-v1, план v2 и город не меняются, есть сообщение`,
      bad2.length === 0 && /не принят/.test(msg) ? "PASS" : "FAIL", { bad: bad2, msg: msg.slice(0, 120) });
    check("B", "B2", `v1-импорт в UI отклоняет те же ${n} конвертов, сценарий v1 не меняется`, bad1.length === 0 ? "PASS" : "FAIL", { bad: bad1 });
    check("B", "B3", "данные среза на странице (CITY_EVIDENCE) не изменились", (await dataHash()) === hash0 ? "PASS" : "FAIL");
    const hasRs = await page.evaluate(() => !!(window.CITY_RESILIENCE || window.CITY_RESILIENCE_UI));
    check("B", "B4", "панель «Устойчивость к допущениям»: отображение label только текстом, отмена, смена города",
      hasRs ? "FAIL" : "NOT_RUN", hasRs ? "модуль есть, а проверки для него ещё не подключены — обновить ui_r9_browser.cjs" : "в этой сборке нет UI устойчивости");
  }

  if (GROUPS.has("L")) {
    const V04 = sub(r8fx("V04"), "shymkent");       // 16 candidates: a search takes long enough to interleave
    // L1: selected plan changed DURING the search: the problem is the same (selected_ids is not in problem_digest), so
    //     the optimum may be shown, but applying it must use the current problem and the explanation must be recomputed
    await page.evaluate((t) => CITY_PLAN_UI.importText(t), V04);
    const l1 = await page.evaluate(() => new Promise((resolve) => {
      const U = CITY_PLAN_UI; U.startSearch(); const rid = U.opt.request_id;
      setTimeout(() => { const before = U.state.selected.slice(); { const id = U.state.cands[0].id; U.toggleSelected(id, !U.state.selected.includes(id)); }
        const poll = () => { if (U.opt.status === "running") return setTimeout(poll, 20);
          resolve({ status: U.opt.status, rid, ridNow: U.opt.request_id, changedSel: JSON.stringify(before) !== JSON.stringify(U.state.selected),
                    resultDigest: U.opt.result && U.opt.result.problem_digest }); };
        poll(); }, 30);
    }));
    const curDigest = await page.evaluate(() => CITY_PLAN.problemDigest(CITY_PLAN_UI.scenario(), CITY_APP.ui.F));
    check("L", "L1", "смена ручного выбора во время поиска: задача та же — результат допустим только для текущего problem_digest",
      l1.changedSel && (l1.status === "done" ? l1.resultDigest === curDigest : l1.status === "stale") ? "PASS" : "FAIL", { ...l1, curDigest });
    // L2: the explanation is bound to the manual plan: after a selection change the old text is not shown
    await page.evaluate(() => CITY_PLAN_UI.explainNow());
    const e1 = await page.evaluate(() => !!(CITY_PLAN_UI.state.expl && document.getElementById("plExplainText")));
    await page.evaluate(() => { const U = CITY_PLAN_UI, id = U.state.cands[1].id; U.toggleSelected(id, !U.state.selected.includes(id)); });
    const e2 = await page.evaluate(() => !!document.getElementById("plExplainText"));
    check("L", "L2", "объяснение после смены ручного выбора не показывается (старый текст отброшен)", e1 && !e2 ? "PASS" : "FAIL", { shown_before: e1, shown_after: e2 });
    // L3: city switched after the search finished: the optimum is not applicable in the new city
    await page.evaluate((t) => CITY_PLAN_UI.importText(t), V04);
    await page.evaluate(() => CITY_PLAN_UI.startSearch());
    await page.waitForFunction(() => CITY_PLAN_UI.opt.status !== "running", null, { timeout: 20000 });
    const doneBefore = await page.evaluate(() => CITY_PLAN_UI.opt.status);
    await page.evaluate(() => CITY_APP.switchCity("astana"));
    const l3 = await page.evaluate(() => ({ status: CITY_PLAN_UI.opt.status, hasResult: !!CITY_PLAN_UI.opt.result, applied: CITY_PLAN_UI.applyPlan("mean"),
      selected: CITY_PLAN_UI.state.selected.slice(), city: CITY_APP.state.city }));
    check("L", "L3", "смена города после завершённого поиска: результат сброшен, применить нельзя", doneBefore === "done" && !l3.hasResult && l3.applied === false && l3.city === "astana" ? "PASS" : "FAIL", { doneBefore, ...l3 });
    await page.evaluate(() => CITY_APP.switchCity("shymkent"));
    // L4: a result computed BEFORE a selection change can still be applied (same problem) and replaces only the selection
    await page.evaluate((t) => CITY_PLAN_UI.importText(t), V04);
    await page.evaluate(() => CITY_PLAN_UI.startSearch());
    await page.waitForFunction(() => CITY_PLAN_UI.opt.status !== "running", null, { timeout: 20000 });
    const l4 = await page.evaluate(() => { const U = CITY_PLAN_UI, id2 = U.state.cands[2].id; U.toggleSelected(id2, !U.state.selected.includes(id2));
      const ok = U.applyPlan("minimax"); return { ok, selected: U.state.selected.slice(), want: U.opt.result && U.opt.result.objectives.minimax.ids, status: U.opt.status }; });
    check("L", "L4", "после смены ручного выбора оптимум той же задачи применяется только кнопкой и ставит ровно свои ID", l4.ok && JSON.stringify(l4.selected) === JSON.stringify(l4.want) ? "PASS" : "FAIL", l4);
    // L5: budget change between "done" and "apply": refused (covered in r8 U2b, repeated here on the same build)
    const l5 = await page.evaluate(() => { const U = CITY_PLAN_UI; U.setNumber("budget", String(U.state.budget - 1), 0, 1000000, (v) => { U.state.budget = v; });
      return { status: U.opt.status, applied: U.applyPlan("mean") }; });
    check("L", "L5", "смена бюджета после поиска: результат устарел, применить нельзя", l5.status === "stale" && l5.applied === false ? "PASS" : "FAIL", l5);
  }
  check("Z", "Z1", "нет внешних запросов и ошибок страницы", external.length === 0 && errors.length === 0 ? "PASS" : "FAIL", { external: external.slice(0, 5), errors: errors.slice(0, 5) });
  check("Z", "Z2", "данные среза на странице не изменились за весь прогон", (await dataHash()) === hash0 ? "PASS" : "FAIL");
  await browser.close();
  const count = (s) => results.filter((r) => r.status === s).length;
  const summary = { app_root: path.basename(APP), groups: [...GROUPS], total: results.length, pass: count("PASS"),
    fail: results.filter((r) => r.status === "FAIL").map((r) => `${r.group}/${r.id}`), not_run: count("NOT_RUN"), external_requests: external.length };
  summary.verdict = summary.fail.length ? "FAIL" : "PASS";
  console.log(JSON.stringify(summary));
  if (OUT) fs.writeFileSync(OUT, JSON.stringify({ summary, results }, null, 1) + "\n");
  process.exit(summary.fail.length ? 1 : 0);
})().catch((e) => { console.error("ui_r9_browser error:", e && e.message); process.exit(3); });
