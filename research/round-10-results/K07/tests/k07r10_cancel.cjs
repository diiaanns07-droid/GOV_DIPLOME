// K07 r10: отмена поиска в «Дополнительно → План с бюджетом»: «Найти» → сразу «Отменить поиск» (клик, затем клавиатура).
// Usage: node k07r10_cancel.cjs --url http://127.0.0.1:8502/ --out result.json
"use strict";
const { chromium } = require("playwright");
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const URL = arg("--url", "http://127.0.0.1:8502/");
const results = []; const check = (id, ok, info) => { results.push({ id, ok: !!ok, info }); console.log(`${ok ? "PASS" : "FAIL"} ${id} ${info ? JSON.stringify(info).slice(0, 240) : ""}`); };
(async () => {
  const b = await chromium.launch(); const pg = await b.newPage({ viewport: { width: 1440, height: 900 } }); const errs = [];
  pg.on("pageerror", (e) => errs.push(String(e)));
  await pg.goto(URL, { waitUntil: "load" }); await pg.waitForTimeout(800);
  await pg.click("#govtech-toggle"); await pg.waitForTimeout(300);
  await pg.evaluate(() => GOVTECH.setPage("plan"));
  await pg.click("#plDemo"); await pg.waitForTimeout(150);
  // полный набор: 16 кандидатов, чтобы поиск не успел закончиться мгновенно
  await pg.evaluate(() => { const U = CITY_PLAN_UI; for (let i = U.state.cands.length; i < 16; i++) { const c = U.state.cands[i % 8]; U.state.cands.push({ id: "X" + i, lon: c.lon + 1e-4 * i, lat: c.lat, cost: 50 }); } U.state.max_selected = 5; U.state.budget = 1000000; U.changed(""); });
  const seq = await pg.evaluate(async () => { const U = CITY_PLAN_UI, out = [];
    document.getElementById("plRun").click(); out.push(U.opt.status);
    await new Promise((r) => setTimeout(r, 30));
    const c = document.getElementById("plCancel"); out.push(c && !c.disabled ? "cancel-enabled" : "cancel-disabled");
    if (c && !c.disabled) c.click(); out.push(U.opt.status);
    await new Promise((r) => setTimeout(r, 300)); out.push(U.opt.status, document.activeElement?.id || null);
    return out; });
  check("cancel_search_by_click", seq[0] === "running" && seq[1] === "cancel-enabled" && seq[2] !== "running" && seq[3] !== "done", { seq });
  // клавиатура: фокус на «Найти», Enter, затем Enter на «Отменить поиск» (фокус переносится сам — K07 r8 K5)
  await pg.focus("#plRun"); await pg.keyboard.press("Enter"); await pg.waitForTimeout(20);
  const f = await pg.evaluate(() => ({ status: CITY_PLAN_UI.opt.status, focus: document.activeElement?.id }));
  if (f.focus === "plCancel") await pg.keyboard.press("Enter");
  await pg.waitForTimeout(300);
  const after = await pg.evaluate(() => ({ status: CITY_PLAN_UI.opt.status, msg: CITY_PLAN_UI.opt.msg, focus: document.activeElement?.id }));
  check("cancel_search_by_keyboard", f.focus === "plCancel" && after.status !== "done", { before: f, after });
  check("cancel_no_page_errors", errs.length === 0, errs.slice(0, 3));
  await b.close();
  const out = arg("--out", null); if (out) require("fs").writeFileSync(out, JSON.stringify({ url: URL, results }, null, 1));
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})();
