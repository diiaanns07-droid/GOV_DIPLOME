// K12 round 9: browser checks on the ACTUAL build (file://, every non-file request aborted and counted).
//  group B (stage 2): city-resilience-v1 envelopes are refused by the v2 and v1 file imports without any state change;
//                     slice data (CITY_EVIDENCE) unchanged; a resilience UI, if present, is reported separately (NOT_RUN here).
//  group R (stage 3): resilience UI (CITY_RESILIENCE_UI): atomic import, late answers after case/label/city/budget changes,
//                     cancel, apply only by button, label as text, export/import/report, UI = K12 oracle; NOT_RUN without the UI.
//  group L (stage 3): late results — an optimum is not applied after a change of the selected plan / city made during or
//                     after the search; the template explanation is dropped when the manual selection changes.
//   NODE_PATH="$(npm root -g)" node ui_r9_browser.cjs --app-root <copy> [--groups B,L,R] [--out r.json]
// Page API used (BUILD d865dd4): CITY_PLAN_UI.{importText,startSearch,cancelSearch,applyPlan,toggleSelected,explainNow,opt,state},
// CITY_APP.{wiImportText,wiScenario,switchCity,ui.F}. If BUILD renames it, update this file (test error, not product error).
"use strict";
const fs = require("fs"), path = require("path");
const { pathToFileURL } = require("url");
const args = process.argv.slice(2);
const opt = (n, d) => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : d; };
const APP = path.resolve(opt("--app-root", ""));
const GROUPS = new Set(opt("--groups", "B,L,R").split(","));
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
    const hasRsUi = await page.evaluate(() => !!window.CITY_RESILIENCE_UI);
    if (!hasRsUi) check("B", "B4", "панель «Устойчивость к допущениям» (группа R)", "NOT_RUN", "в этой сборке нет UI устойчивости (window.CITY_RESILIENCE_UI)");
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
  if (GROUPS.has("R")) {
    const has = await page.evaluate(() => !!window.CITY_RESILIENCE_UI);
    if (!has) check("R", "R0", "UI устойчивости (window.CITY_RESILIENCE_UI)", "NOT_RUN", "в этой сборке нет UI устойчивости");
    else {
      await page.evaluate(() => CITY_APP.switchCity("shymkent"));
      const rsText = (id) => { const f = RS.fixtures.find((x) => x.id === id); return sub(fs.readFileSync(path.join(HERE, f.file), "utf8"), f.city); };
      const EXP = JSON.parse(fs.readFileSync(path.join(HERE, "expected", "rs_oracle_d865dd4.json"), "utf8"));
      const rsState = () => page.evaluate(() => { const S = CITY_RESILIENCE_UI.state, P = CITY_PLAN_UI.state;
        return JSON.stringify([S.cases.map((c) => [c.id, c.label, [...c.ids].sort()]), ["category", "points", "cands", "budget", "max_selected", "radius", "required", "excluded", "selected"].map((k) => P[k]), CITY_APP.state.city]); });
      const waitRs = (ms = 30000) => page.waitForFunction(() => CITY_RESILIENCE_UI.state.status !== "running", null, { timeout: ms }).catch(() => null);
      // R1: atomic refusal of every negative fixture in the resilience UI
      await page.evaluate((t) => CITY_RESILIENCE_UI.importText(t), rsText("A01"));
      const r0 = await rsState(), badR = [];
      for (const f of RS.fixtures.filter((x) => x.expect === "reject" && !x.recipe && !x.policy)) {
        const ok = await page.evaluate((t) => CITY_RESILIENCE_UI.importText(t), sub(fs.readFileSync(path.join(HERE, f.file), "utf8"), f.city));
        if (ok !== false || (await rsState()) !== r0) badR.push(f.id);
      }
      const msgR = await page.evaluate(() => CITY_RESILIENCE_UI.state.msg);
      check("R", "R1", "импорт в UI устойчивости: недопустимые конверты отклонены, план, случаи и город прежние, есть сообщение",
        badR.length === 0 && /не принят/.test(msgR) ? "PASS" : "FAIL", { bad: badR, msg: msgR.slice(0, 100) });
      const pol = {};
      for (const id of ["N35", "N49"]) pol[id] = await page.evaluate((t) => CITY_RESILIENCE_UI.importText(t), rsText(id));
      check("R", "R1p", "policy: label с U+202E / одиночным суррогатом", pol.N35 === false && pol.N49 === false ? "PASS" : "ADVISORY", pol);
      // R2: full comparison in the UI equals the independent K12 oracle (A04: 12 candidates x 25 points x 7 cases)
      await page.evaluate((t) => CITY_RESILIENCE_UI.importText(t), rsText("A04"));
      const gaps = await page.evaluate(() => new Promise((resolve) => {
        let last = performance.now(), maxGap = 0; const iv = setInterval(() => { const n = performance.now(); maxGap = Math.max(maxGap, n - last); last = n; }, 10);
        const t0 = performance.now(); CITY_RESILIENCE_UI.start();
        const poll = () => { if (CITY_RESILIENCE_UI.state.status === "running") return setTimeout(poll, 20);
          clearInterval(iv); const r = CITY_RESILIENCE_UI.state.result;
          resolve({ maxGap: Math.round(maxGap), ms: Math.round(performance.now() - t0), status: CITY_RESILIENCE_UI.state.status,
            nominal: r && r.nominal && r.nominal.selected_ids, robust: r && r.robust && r.robust.selected_ids, evaluated: r && r.evaluated, price: r && r.price_of_robustness_m }); };
        setTimeout(poll, 20); }));
      const x = EXP.results.find((y) => y.name === "A04");
      check("R", "R2", "UI: 12×25×7 полностью, результат = оракул K12 (nominal, robust, наборы, цена), страница отвечает (разрыв < 200 мс)",
        gaps.status === "done" && JSON.stringify(gaps.nominal) === JSON.stringify(x.nominal.ids) && JSON.stringify(gaps.robust) === JSON.stringify(x.robust.ids)
          && gaps.evaluated === x.evaluated && Math.abs(gaps.price - x.price_of_robustness_m) < 1e-9 && gaps.maxGap < 200 ? "PASS" : "FAIL", gaps);
      // R3: apply only by button; robust replaces exactly the selection
      const ap = await page.evaluate(() => { const before = CITY_PLAN_UI.state.selected.slice(); const ok = CITY_RESILIENCE_UI.apply("robust");
        return { before, ok, after: CITY_PLAN_UI.state.selected.slice(), want: CITY_RESILIENCE_UI.state.result && CITY_RESILIENCE_UI.state.result.robust.selected_ids }; });
      check("R", "R3", "до «Применить» ручной план не меняется; «Применить» ставит ровно устойчивый план", ap.ok && JSON.stringify(ap.before) === JSON.stringify(JSON.parse(rsText("A04")).plan.selected_ids) && JSON.stringify(ap.after) === JSON.stringify(ap.want) ? "PASS" : "FAIL", ap);
      // R4..R7: late answers after a change made DURING the search
      const during = async (mutate) => {
        await page.evaluate((t) => CITY_RESILIENCE_UI.importText(t), rsText("A04"));
        const r = await page.evaluate((m) => new Promise((resolve) => { const U = CITY_RESILIENCE_UI, P = CITY_PLAN_UI; U.start(); const rid = U.state.request_id;
          const act = {   // named actions (no code strings evaluated in the page)
            exclusion: () => { const c = U.state.cases[0]; const id = U.sources().find((p) => !c.ids.has(p.id)).id; U.toggleRecord(c.id, id, true); },
            label: () => U.setLabel(U.state.cases[0].id, "Новое название"),
            city: () => CITY_APP.switchCity("astana"),
            budget: () => P.setNumber("budget", String(P.state.budget - 1), 0, 1000000, (v) => { P.state.budget = v; }),
            cancel: () => U.cancel() };
          setTimeout(() => { const running = U.state.status === "running"; act[m]();
            setTimeout(() => resolve({ running, status: U.state.status, hasResult: !!U.state.result, ridChanged: U.state.request_id !== rid }), 2500); }, 40); }), mutate);
        return r;
      };
      const r4 = await during("exclusion");
      check("R", "R4", "изменение исключений случая во время сравнения: ответ отброшен (stale, без результата)", r4.running && r4.status === "stale" && !r4.hasResult ? "PASS" : "FAIL", r4);
      const r5 = await during("label");
      check("R", "R5", "переименование случая во время сравнения: ответ отброшен (label входит в digest)", r5.running && r5.status === "stale" && !r5.hasResult ? "PASS" : "FAIL", r5);
      const r6 = await during("city");
      const r6c = await page.evaluate(() => CITY_RESILIENCE_UI.state.cases.length);
      check("R", "R6", "смена города во время сравнения: случаи сброшены, ответ не показан", r6.running && !r6.hasResult && r6c === 0 ? "PASS" : "FAIL", { ...r6, cases: r6c });
      await page.evaluate(() => CITY_APP.switchCity("shymkent"));
      const r7 = await during("budget");
      check("R", "R7", "смена бюджета плана v2 во время сравнения: ответ отброшен", r7.running && r7.status === "stale" && !r7.hasResult ? "PASS" : "FAIL", r7);
      const r8 = await during("cancel");
      check("R", "R8", "отмена: cancelled, неполный результат не показан и позже", r8.running && r8.status === "cancelled" && !r8.hasResult ? "PASS" : "FAIL", r8);
      // R9: manual selection change after "done": same problem -> result kept; the explanation is recomputed, not reused
      await page.evaluate((t) => CITY_RESILIENCE_UI.importText(t), rsText("A04"));
      await page.evaluate(() => CITY_RESILIENCE_UI.start()); await waitRs();
      await page.evaluate(() => CITY_RESILIENCE_UI.explain());
      const e1 = await page.evaluate(() => !!document.getElementById("rsExplainText"));
      await page.evaluate(() => { const P = CITY_PLAN_UI, id = P.state.cands[0].id; P.toggleSelected(id, !P.state.selected.includes(id)); });
      await page.waitForTimeout(50);
      const r9 = await page.evaluate(() => ({ status: CITY_RESILIENCE_UI.state.status, hasResult: !!CITY_RESILIENCE_UI.state.result, expl: !!document.getElementById("rsExplainText") }));
      check("R", "R9", "смена ручного выбора: результат той же задачи сохранён, старое объяснение не показывается", e1 && r9.status === "done" && r9.hasResult && !r9.expl ? "PASS" : "FAIL", { e1, ...r9 });
      // R10: label shown as text (HTML/script in a label), no element injected
      await page.evaluate((t) => CITY_RESILIENCE_UI.importText(t), rsText("A07"));
      await page.waitForTimeout(50);
      const r10 = await page.evaluate(() => { const card = document.getElementById("resCard");
        return { scripts: card.querySelectorAll("script, b, img, iframe").length, text: card.textContent.includes("<script>alert(1)</script>") }; });
      check("R", "R10", "label с HTML/скриптом отображается текстом, элементы не создаются", r10.scripts === 0 && r10.text ? "PASS" : "FAIL", r10);
      // R11: export = input only; round trip; report without scripts, label escaped
      const r11 = await page.evaluate(() => { const U = CITY_RESILIENCE_UI, t = U.exportText(), o = JSON.parse(t), before = JSON.stringify(U.envelope());
        const ok = U.importText(t), html = U.reportText();
        return { keys: Object.keys(o).sort().join(","), planKeys: Object.keys(o.plan).includes("derived_results"), ok, same: JSON.stringify(U.envelope()) === before,
          script: /<script/i.test(html), escaped: html.includes("&lt;script&gt;"), csp: html.includes("default-src 'none'"), url: /https?:\/\//.test(html) }; });
      check("R", "R11", "экспорт только вход (schema_version, plan, cases); круг экспорт→импорт; отчёт без скриптов, label экранирован, CSP, без URL",
        r11.keys === "cases,plan,schema_version" && !r11.planKeys && r11.ok && r11.same && !r11.script && r11.escaped && r11.csp && !r11.url ? "PASS" : "FAIL", r11);
      // R12: UI label check vs module check (U+2028 accepted by the UI edit box, refused by validateResilience)
      const r12 = await page.evaluate(() => { const U = CITY_RESILIENCE_UI, id = U.state.cases[0].id; U.setLabel(id, "a\u2028b");
        const kept = U.state.cases[0].label === "a\u2028b"; let code = null; try { CITY_RESILIENCE.validateResilience(U.envelope(), CITY_PLAN_UI.ctxOf(CITY_APP.state.city)); } catch (e) { code = e.code; }
        return { uiAccepted: kept, moduleCode: code }; });
      check("R", "R12", "одинаковые правила названия в поле UI и в модуле (U+2028)", !(r12.uiAccepted && r12.moduleCode) ? "PASS" : "ADVISORY", r12);
    }
  }
  check("Z", "Z1", "нет внешних запросов и ошибок страницы", external.length === 0 && errors.length === 0 ? "PASS" : "FAIL", { external: external.slice(0, 5), errors: errors.slice(0, 5) });
  check("Z", "Z2", "данные среза на странице не изменились за весь прогон", (await dataHash()) === hash0 ? "PASS" : "FAIL");
  await browser.close();
  const count = (s) => results.filter((r) => r.status === s).length;
  const summary = { app_root: path.basename(APP), groups: [...GROUPS], total: results.length, pass: count("PASS"), advisory: results.filter((r) => r.status === "ADVISORY").map((r) => `${r.group}/${r.id}`),
    fail: results.filter((r) => r.status === "FAIL").map((r) => `${r.group}/${r.id}`), not_run: count("NOT_RUN"), external_requests: external.length };
  summary.verdict = summary.fail.length ? "FAIL" : "PASS";
  console.log(JSON.stringify(summary));
  if (OUT) fs.writeFileSync(OUT, JSON.stringify({ summary, results }, null, 1) + "\n");
  process.exit(summary.fail.length ? 1 : 0);
})().catch((e) => { console.error("ui_r9_browser error:", e && e.message); process.exit(3); });
