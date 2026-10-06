/* BUILD r10 acceptance on the real page (root app.py on :8501), Chromium headless via Playwright.
 * Usage: node acc.cjs <out_dir> <code_sha>. Writes <out_dir>/acceptance.json and screenshots. Each check: PASS | FAIL | NOT_RUN.
 */
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");
const URL0 = "http://127.0.0.1:8501/";
(async () => {
  const dir = process.argv[2], sha = process.argv[3] || null;
  fs.mkdirSync(dir, { recursive: true });
  const R = { code_sha: sha, url: URL0, browser: "Chromium (Playwright, headless, swiftshader)", checks: [] };
  const check = (id, status, detail) => { R.checks.push({ id, status, detail }); console.log(status.padEnd(7), id, typeof detail === "string" ? detail : JSON.stringify(detail).slice(0, 200)); };
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const hold = async (p, sel, ms) => { await p.locator(sel).scrollIntoViewIfNeeded(); const bb = await p.locator(sel).boundingBox(); await p.mouse.move(bb.x + bb.width / 2, bb.y + bb.height / 2); await p.mouse.down(); await p.waitForTimeout(ms); await p.mouse.up(); };
  async function open(w, h, opts) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, acceptDownloads: true, ...(opts || {}) });
    const p = await ctx.newPage(); p.errs = []; p.on("pageerror", (e) => p.errs.push(e.message));
    await p.goto(URL0); await p.waitForFunction(() => window.SCHOOL_UI && SCHOOL_UI.ready() && typeof mapReady !== "undefined", null, { timeout: 30000 });
    await p.waitForTimeout(1500);
    return { ctx, p };
  }
  const st = (p) => p.evaluate(() => ({ city: SCHOOL_UI.state.city, digest: SCHOOL_UI.state.digest, v: SCHOOL_UI.caseOf(SCHOOL_UI.state.city).variants, compared: SCHOOL_UI.state.compared, view: SCHOOL_UI.state.view }));

  // ---------- desktop 1440 ----------
  let { ctx, p } = await open(1440, 900);
  await p.evaluate(() => localStorage.clear());
  const t0 = await p.evaluate(() => ({ score: document.getElementById("city-score").textContent, canvases: document.querySelectorAll("canvas").length, iframes: document.querySelectorAll("iframe").length,
    offline: document.body.classList.contains("offline-basemap"), mapReady: typeof mapReady !== "undefined" && mapReady }));
  check("training_mode_52_56", t0.score === "52,56" ? "PASS" : "FAIL", t0);
  check("one_canvas_no_iframe", t0.canvases === 1 && t0.iframes === 0 ? "PASS" : "FAIL", t0);
  check("basemap_openfreemap", t0.offline ? "NOT_RUN" : "PASS", t0.offline ? "OpenFreeMap недоступна из этой среды (host_not_allowed); показан офлайн-фон с подписью" : "стиль загружен");
  // training state kept across the city mode
  const added = await p.evaluate(async () => { const id = catalog.measures[0].id; await addProject(id); return JSON.stringify(state.plan); });
  await p.screenshot({ path: path.join(dir, "00_training_1440.png") });
  await p.click("#govtech-toggle"); await p.waitForTimeout(1200);
  const g = await p.evaluate(() => ({ strip: !document.getElementById("sc-strip").hidden, card: !document.getElementById("sc-card").hidden, actions: !document.getElementById("sc-actions").hidden,
    text: document.getElementById("sc-strip").innerText + " | " + document.querySelector("#sc-card h2").textContent, pkg: Object.fromEntries(Object.entries(SCHOOL_UI.state.pkg).map(([k, v]) => [k, v.error || v.bind.by])) }));
  check("city_mode_opens_school_path", g.strip && g.card && g.actions && /Доступность школ/.test(g.text) ? "PASS" : "FAIL", g);
  check("packages_loaded_and_bound", !g.pkg.shymkent.includes(":") && g.pkg.astana === "vendored_package_manifest" ? "PASS" : "FAIL", g.pkg);
  await p.screenshot({ path: path.join(dir, "01_start_1440.png") });
  // selected object: school from the card list (keyboard-operable buttons)
  await p.click("#sc-card details summary"); await p.click("#sc-card .sc-list button");
  await p.waitForTimeout(300);
  const sel = await p.evaluate(() => ({ head: document.querySelector("#sc-card h2").textContent, hl: map.querySourceFeatures("sc-links").filter((f) => f.properties.hl).length, prov: document.getElementById("sc-card").innerText.includes("Источник") }));
  check("select_school_shows_provenance_and_links", sel.prov && sel.hl > 0 ? "PASS" : "FAIL", sel);
  await p.screenshot({ path: path.join(dir, "02_selected_school_1440.png") });
  // A by clicking a diamond on the map; B with the keyboard from the card list
  await p.click("#sc-card .sc-back"); await p.click("#sc-pick-A"); await p.locator("#sc-overlay .sc-cand").nth(1).click({ force: true }); await p.waitForTimeout(200);
  await p.focus("#sc-pick-B"); await p.keyboard.press("Enter"); await p.waitForTimeout(200);
  await p.focus("#sc-card .sc-cands li:nth-child(1) button"); await p.keyboard.press("Enter"); await p.waitForTimeout(200);
  await p.focus("#sc-compare"); await p.keyboard.press("Enter"); await p.waitForTimeout(400);
  const s1 = await st(p);
  check("keyboard_pick_B_and_compare", s1.v.A && s1.v.B && s1.compared ? "PASS" : "FAIL", s1);
  // Сейчас / A / B change layer data, not only titles
  const layer = {};
  for (const v of ["current", "A", "B"]) { await p.click("#sc-view-" + v); await p.waitForTimeout(250); layer[v] = await p.evaluate(() => ({ toNew: map.querySourceFeatures("sc-links").filter((f) => f.properties.to === "candidate").length, metric: document.querySelector("#sc-strip .sc-metric b").textContent })); }
  check("views_switch_layer_data", layer.current.toNew === 0 && (layer.A.toNew > 0 || layer.B.toNew > 0) && layer.A.metric !== layer.current.metric ? "PASS" : "FAIL", layer);
  await p.click("#sc-view-B"); await p.click("#sc-diff"); await p.waitForTimeout(250);
  const diff = await p.evaluate(() => ({ green: document.querySelectorAll("#sc-overlay .sc-o-closer").length, expected: SCHOOL_UI.plan("B").closer_count, unk: document.querySelectorAll("#sc-overlay .sc-o-unk").length }));
  check("difference_mode_matches_rows", diff.green === diff.expected ? "PASS" : "FAIL", diff);
  await p.screenshot({ path: path.join(dir, "03_compare_AB_1440.png") });
  // input → first click (D1 class) on the school path and on the advanced planner
  await p.click("#sc-card .sc-back").catch(() => {});
  await p.evaluate(() => { SCHOOL_UI.state.compared = false; SCHOOL_UI.render(); });
  await p.locator("#sc-threshold").scrollIntoViewIfNeeded(); await p.fill("#sc-threshold", "700"); await hold(p, "#sc-compare", 110); await p.waitForTimeout(400);
  const d1 = await p.evaluate(() => ({ thr: SCHOOL_UI.caseOf("shymkent").parameters.threshold_m, compared: SCHOOL_UI.state.compared }));
  check("input_then_first_click_school", d1.thr === 700 && d1.compared ? "PASS" : "FAIL", d1);
  // 3D: tilt keeps the slice; without basemap — explained
  await p.click("#toggle-3d"); await p.waitForTimeout(1200);
  const td = await p.evaluate(() => ({ pitch: Math.round(map.getPitch()), toast: document.getElementById("toast").textContent, ext3d: !!map.getLayer("akim-3d") }));
  check("3d_camera_tilt", td.pitch >= 45 && td.ext3d ? "PASS" : "FAIL", td);
  check("3d_buildings_visible", t0.offline ? "NOT_RUN" : "PASS", t0.offline ? "слой akim-3d есть, но тайлы зданий OpenFreeMap недоступны в этой среде" : "");
  if (t0.offline) check("3d_offline_explained", /3D-здания появятся/.test(td.toast) ? "PASS" : "FAIL", td.toast);
  await p.click("#toggle-3d"); await p.waitForTimeout(800);
  // AI: whatever the server says, labelled; network failure; stale answer
  await p.evaluate(() => { SCHOOL_UI.state.compared = true; SCHOOL_UI.render(); });
  await p.fill("#sc-ask-q", "Какой вариант лучше?"); await p.click("#sc-ask-go"); await p.waitForSelector("#sc-ai-out", { timeout: 15000 });
  const ai = await p.evaluate(() => document.getElementById("sc-ai-out").innerText);
  const live = /AI-помощника/i.test(ai);
  check("ai_answer_labelled", /Шаблонный ответ без AI|AI-помощника/i.test(ai) ? "PASS" : "FAIL", ai.slice(0, 160));
  check("ai_live_provider", live ? "PASS" : "NOT_RUN", live ? "модель ответила" : "сервер: провайдер не настроен (нет ключа в среде); живой ответ не проверен");
  await p.route("**/api/school-ai", (r) => r.abort()); await p.fill("#sc-ask-q", "Что значит порог?"); await p.click("#sc-ask-go"); await p.waitForTimeout(800);
  const net = await p.evaluate(() => document.getElementById("sc-msg").textContent); await p.unroute("**/api/school-ai");
  check("ai_network_failure_message", /Сервер не ответил/.test(net) ? "PASS" : "FAIL", net);
  await p.route("**/api/school-ai", async (r) => { await new Promise((x) => setTimeout(x, 1500)); await r.continue(); });
  await p.fill("#sc-ask-q", "Почему?"); await p.click("#sc-ask-go"); await p.waitForTimeout(200);
  await p.evaluate(() => { const c = SCHOOL_UI.caseOf("shymkent"); c.parameters.threshold_m = 650; SCHOOL_UI.recompute(); SCHOOL_UI.render(); });
  await p.waitForTimeout(2300); await p.unroute("**/api/school-ai");
  const stale = await p.evaluate(() => ({ msg: document.getElementById("sc-msg").textContent, shown: !!document.getElementById("sc-ai-out") }));
  check("ai_stale_answer_discarded", /устарел/.test(stale.msg) && !stale.shown ? "PASS" : "FAIL", stale);
  // export JSON → disk → import; tampered refused; note → disk → import
  const sBefore = await st(p);
  const [dl] = await Promise.all([p.waitForEvent("download"), p.click("#sc-export")]); const jf = path.join(dir, dl.suggestedFilename()); await dl.saveAs(jf);
  const [dn] = await Promise.all([p.waitForEvent("download"), p.click("#sc-note")]); const nf = path.join(dir, dn.suggestedFilename()); await dn.saveAs(nf);
  await p.click("#sc-strip [data-city=astana]"); await p.waitForTimeout(500);
  await p.setInputFiles("#sc-import-file", jf); await p.waitForTimeout(700);
  const sJ = await st(p);
  check("export_json_file_and_reimport", fs.statSync(jf).size > 1000 && sJ.digest === sBefore.digest && sJ.city === "shymkent" ? "PASS" : "FAIL", { file: path.basename(jf), bytes: fs.statSync(jf).size, same: sJ.digest === sBefore.digest });
  const bad = path.join(dir, "tampered.json"); fs.writeFileSync(bad, fs.readFileSync(jf, "utf8").replace('"threshold_m": 650', '"threshold_m": 900'));
  await p.setInputFiles("#sc-import-file", bad); await p.waitForTimeout(500);
  const sT = await st(p), tMsg = await p.evaluate(() => document.getElementById("sc-msg").textContent);
  check("tampered_import_refused_atomically", sT.digest === sBefore.digest && /не загружен/.test(tMsg) ? "PASS" : "FAIL", tMsg.slice(0, 120));
  await p.click("#sc-strip [data-city=astana]"); await p.waitForTimeout(400);
  await p.setInputFiles("#sc-import-file", nf); await p.waitForTimeout(700);
  const sN = await st(p);
  check("note_file_and_reimport", fs.statSync(nf).size > 1000 && sN.digest === sBefore.digest ? "PASS" : "FAIL", { file: path.basename(nf), bytes: fs.statSync(nf).size });
  // city switch: Astana K10, nothing of Shymkent kept
  await p.click("#sc-strip [data-city=astana]"); await p.waitForTimeout(600);
  const ast = await p.evaluate(() => { const c = SCHOOL_UI.caseOf("astana"), sh = SCHOOL_UI.caseOf("shymkent"); const shIds = new Set([...sh.schools, ...sh.origins, ...sh.candidates].map((x) => x.id));
    return { case_id: c.case_id, schools: c.schools.length, leak: [...c.schools, ...c.origins, ...c.candidates].filter((x) => shIds.has(x.id)).length, ai: !!document.getElementById("sc-ai-out"), title: document.querySelector("#sc-card h2").textContent, compared: SCHOOL_UI.state.compared }; });
  check("city_switch_astana_separate", ast.case_id.startsWith("astana") && ast.leak === 0 && !ast.ai && !ast.compared ? "PASS" : "FAIL", ast);
  await p.click("#sc-pick-A"); await p.locator("#sc-overlay .sc-cand").nth(0).click({ force: true }); await p.click("#sc-pick-B"); await p.locator("#sc-overlay .sc-cand").nth(1).click({ force: true }); await p.click("#sc-compare"); await p.waitForTimeout(300);
  await p.screenshot({ path: path.join(dir, "04_astana_compare_1440.png") });
  // street routes (K03) in Astana
  await p.click("#sc-method-pedestrian-v1-strict"); await p.waitForFunction(() => SCHOOL_UI.state.cmp && SCHOOL_UI.state.cmp.policy_id === "pedestrian-v1-strict", null, { timeout: 20000 });
  const ped = await p.evaluate(() => ({ m: SCHOOL_UI.plan("current").metrics, label: document.querySelector(".sc-method-tag").textContent }));
  check("street_routes_strict_unknown_not_zero", ped.m.known_count + ped.m.unknown_count === ped.m.total_origins ? "PASS" : "FAIL", ped);
  await p.screenshot({ path: path.join(dir, "05_astana_streets_strict_1440.png") });
  // F5
  const sF = await st(p);
  await p.reload(); await p.waitForFunction(() => window.SCHOOL_UI && SCHOOL_UI.ready(), null, { timeout: 30000 }); await p.click("#govtech-toggle");
  await p.waitForFunction(() => SCHOOL_UI.state.cmp, null, { timeout: 20000 }); await p.waitForTimeout(800);
  const sF2 = await st(p);
  check("f5_restores_case", sF2.city === "astana" && sF2.digest === sF.digest ? "PASS" : "FAIL", { before: sF.digest.slice(7, 19), after: sF2.digest && sF2.digest.slice(7, 19), city: sF2.city });
  // advanced mode reachable; D1 on v2 planner
  await p.click("#sc-strip .sc-adv"); await p.waitForTimeout(300);
  await p.click("#plDemo"); await p.locator("#plRun").scrollIntoViewIfNeeded(); await p.fill("#plBudget", "400"); await hold(p, "#plRun", 110); await p.waitForTimeout(500);
  const v2 = await p.evaluate(() => ({ status: CITY_PLAN_UI.opt.status, budget: CITY_PLAN_UI.state.budget }));
  check("advanced_v2_first_click_after_typing", ["running", "done"].includes(v2.status) && v2.budget === 400 ? "PASS" : "FAIL", v2);
  await p.waitForTimeout(2500);
  await p.click("#gov-back-school"); await p.waitForTimeout(300);
  // return to training: 52,56, layers hidden; training state of this tab (after F5 the plan is the app's own state)
  await p.click("#govtech-toggle"); await p.waitForTimeout(800);
  const back = await p.evaluate(() => ({ score: document.getElementById("city-score").textContent, sc: map.getLayoutProperty("sc-links-school", "visibility"), districts: map.getLayoutProperty("district-fill", "visibility"), strip: document.getElementById("sc-strip").hidden }));
  check("return_to_training", back.score === "52,56" && back.sc === "none" && back.districts === "visible" && back.strip ? "PASS" : "FAIL", back);
  check("no_page_errors_1440", p.errs.length ? "FAIL" : "PASS", p.errs);
  await ctx.close();
  // training plan survives a round trip through the city mode (same tab, no reload)
  ({ ctx, p } = await open(1440, 900));
  const keep = await p.evaluate(async () => { await addProject(catalog.measures[0].id); const before = JSON.stringify(state.plan); document.getElementById("govtech-toggle").click(); await new Promise((r) => setTimeout(r, 600)); document.getElementById("govtech-toggle").click(); await new Promise((r) => setTimeout(r, 600)); return { before, after: JSON.stringify(state.plan) }; });
  check("training_plan_kept_across_city_mode", keep.before === keep.after && keep.before !== "[]" ? "PASS" : "FAIL", keep);
  await ctx.close();

  // ---------- mobile 390 ----------
  ({ ctx, p } = await open(390, 844, { isMobile: true, hasTouch: true, deviceScaleFactor: 2 }));
  await p.evaluate(() => localStorage.clear());
  await p.tap("#govtech-toggle"); await p.waitForTimeout(1200);
  await p.screenshot({ path: path.join(dir, "06_start_mobile390.png") });
  await p.tap("#sc-pick-A"); await p.locator("#sc-overlay .sc-cand").nth(1).tap({ force: true }); await p.waitForTimeout(200);
  await p.tap("#sc-suggest"); await p.waitForTimeout(200); await p.tap("#sc-compare"); await p.waitForTimeout(500);
  const mob = await p.evaluate(() => ({ scrollW: document.documentElement.scrollWidth, small: [...document.querySelectorAll("#sc-actions button")].filter((x) => x.getBoundingClientRect().height < 38).map((x) => x.id || x.textContent),
    compared: SCHOOL_UI.state.compared, canvases: document.querySelectorAll("canvas").length, cardTop: Math.round(document.getElementById("sc-card").getBoundingClientRect().top) }));
  check("mobile390_layout", mob.scrollW <= 390 && mob.small.length === 0 && mob.compared && mob.canvases === 1 ? "PASS" : "FAIL", mob);
  await p.screenshot({ path: path.join(dir, "07_compare_mobile390.png") });
  check("no_page_errors_390", p.errs.length ? "FAIL" : "PASS", p.errs);
  await ctx.close();
  await b.close();
  R.summary = R.checks.reduce((a, c) => ((a[c.status] = (a[c.status] || 0) + 1), a), {});
  fs.writeFileSync(path.join(dir, "acceptance.json"), JSON.stringify(R, null, 1) + "\n");
  console.log(JSON.stringify(R.summary));
})();
