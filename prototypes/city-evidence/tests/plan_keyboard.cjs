// Keyboard / focus / 390 px checks of the v2 planner (round 9; reproduces K07 r8 K2–K5 and N2 on BUILD d865dd4).
// Usage:  NODE_PATH="$(npm root -g)" node tests/plan_keyboard.cjs [outdir]
const { chromium } = require("playwright");
const path = require("path"), fs = require("fs");
const { pathToFileURL } = require("url");
const APP = path.resolve(__dirname, "..");
const out = path.resolve(process.argv[2] || path.join(APP, "tests", "out"));
fs.mkdirSync(out, { recursive: true });
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok: !!ok, detail: ok ? undefined : detail }); console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail ? " — " + String(detail).slice(0, 300) : "")); };
const active = (page) => page.evaluate(() => { const a = document.activeElement; return { id: a && a.id, tag: a && a.tagName, inPlan: !!(a && a.closest && a.closest("#planCard")) }; });

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(pathToFileURL(path.join(APP, "web", "index.html")).href);
  await page.click('#toolSeg button[data-tool="v2"]');
  await page.click("#plDemo");

  // K2: in placement mode the scenario card is reachable from the map with few Tab presses (roads / records leave the order)
  await page.click("#plModePoints");
  await page.focus("#map");
  let n = 0, reached = false;
  for (; n < 80; n++) { await page.keyboard.press("Tab"); if ((await active(page)).inPlan) { reached = true; break; } }
  check(`K2 placement mode: map → v2 card in ${n + 1} Tab presses (≤ 30)`, reached && n < 30, `presses ${n + 1}, reached ${reached}`);
  const tabStops = await page.evaluate(() => document.querySelectorAll('#map [tabindex="0"]').length);
  check(`K2 no road / record Tab stops while placing (${tabStops})`, tabStops === 0, String(tabStops));
  await page.keyboard.press("Escape");
  const tabAfter = await page.evaluate(() => document.querySelectorAll('#map [tabindex="0"]').length);
  check("K2 outside placement mode roads and records stay keyboard-reachable", tabAfter > 100, String(tabAfter));

  // K3: typing a value and Tab moves the focus to the next field (value applied, focus not lost to <body>)
  await page.focus("#plBudget"); await page.fill("#plBudget", "650"); await page.keyboard.press("Tab");
  await page.waitForTimeout(50);
  const a3 = await active(page);
  check("K3 budget + Tab: value applied, focus on «Максимум объектов»", a3.id === "plMax" && (await page.evaluate(() => CITY_PLAN_UI.state.budget)) === 650, JSON.stringify(a3));
  await page.fill("#plMax", "9"); await page.keyboard.press("Tab"); await page.waitForTimeout(50);
  const a3b = await active(page);
  check("K3 invalid value + Tab: rejected, focus still moves on", a3b.id === "plRadius" && (await page.evaluate(() => CITY_PLAN_UI.state.max_selected)) === 3, JSON.stringify(a3b));

  // K4: «Удалить» from the keyboard keeps the focus inside the card
  await page.click("#plSecPoints > summary");  // a user toggle (remembered across re-renders)
  await page.focus('[data-plan-item="P3"] button'); await page.keyboard.press("Enter");
  const a4 = await active(page);
  check("K4 delete point by keyboard: focus on the neighbouring «Удалить»", a4.inPlan && a4.tag === "BUTTON" && /^plDelP_/.test(a4.id || ""), JSON.stringify(a4));
  await page.click("#plSecCands > summary");
  await page.focus('[data-plan-cand-item="K8"] button[aria-label^="Удалить"]'); await page.keyboard.press("Enter");
  const a4b = await active(page);
  check("K4 delete last candidate by keyboard: focus on the previous candidate's «Удалить»", a4b.id === "plDelK_K7", JSON.stringify(a4b));

  // K5: Enter on «Найти» → focus on «Отменить поиск» while running → back on «Найти» when done
  await page.focus("#plRun"); await page.keyboard.press("Enter");
  const a5 = await active(page);
  const running = await page.evaluate(() => CITY_PLAN_UI.opt.status);
  check("K5 during the search the focus is on «Отменить поиск»", a5.id === "plCancel" || running !== "running", JSON.stringify({ a5, running }));
  await page.waitForFunction(() => CITY_PLAN_UI.opt.status !== "running");
  await page.waitForTimeout(50);
  const a5b = await active(page);
  check("K5 after the search the focus is on «Найти точные оптимумы»", a5b.id === "plRun", JSON.stringify(a5b));
  // keyboard apply
  await page.focus("#plApply_mean"); await page.keyboard.press("Enter");
  const a5c = await active(page);
  check("apply by keyboard keeps the focus in the card", a5c.inPlan, JSON.stringify(a5c));

  // round 9 race: type a value and press «Найти» immediately — the search must use the typed value and finish (not «stale»)
  await page.fill("#plBudget", "640"); await page.click("#plRun");
  await page.waitForFunction(() => CITY_PLAN_UI.opt.status !== "running", null, { timeout: 15000 });
  const race = await page.evaluate(() => ({ st: CITY_PLAN_UI.opt.status, budget: CITY_PLAN_UI.opt.result && CITY_PLAN_UI.opt.result.budget, state: CITY_PLAN_UI.state.budget }));
  check("typed budget + immediate «Найти»: search uses the new value and is not stale", race.st === "done" && race.budget === 640 && race.state === 640, JSON.stringify(race));
  await page.fill("#plBudget", "620"); await page.click("#plExport").catch(() => {});
  check("typed value + immediate export: value applied first", (await page.evaluate(() => CITY_PLAN_UI.state.budget)) === 620);
  await page.click("#plRun"); await page.waitForFunction(() => CITY_PLAN_UI.opt.status === "done", null, { timeout: 15000 });
  // N2: 390 px — Pareto / sensitivity tables readable without hidden columns (no inner horizontal scroll)
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(100);
  const n2 = await page.evaluate(() => ["plPareto", "plSens"].map((id) => { const t = document.getElementById(id); if (!t) return { id, missing: true };
    const card = document.getElementById("planCard").getBoundingClientRect();
    const over = [...t.querySelectorAll("th, td")].filter((c) => c.getBoundingClientRect().right > card.right + 1 || c.scrollWidth > c.clientWidth + 1).length;
    return { id, tw: Math.round(t.getBoundingClientRect().width), card: Math.round(card.width), over }; }));
  check("N2 390 px: Pareto and sensitivity tables fit the card, no clipped cells", n2.every((x) => !x.missing && x.over === 0 && x.tw <= x.card), JSON.stringify(n2));
  const cardOver = await page.evaluate(() => { const b = document.getElementById("planCard"); return { sw: b.scrollWidth, cw: b.clientWidth,
    culprits: [...b.querySelectorAll("*")].filter((e) => e.getBoundingClientRect().right > b.getBoundingClientRect().right + 1).slice(0, 5).map((e) => e.tagName + "#" + e.id + "." + e.className) }; });
  check("390 px: the v2 card itself has no horizontal overflow", cardOver.sw <= cardOver.cw + 1, JSON.stringify(cardOver));
  const doc = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
  check("390 px: no page-level horizontal scroll", doc.sw <= doc.cw + 1, JSON.stringify(doc));
  await page.screenshot({ path: path.join(out, "k1_390_pareto.png"), fullPage: false });
  check("no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
  fs.writeFileSync(path.join(out, "plan_keyboard_result.json"), JSON.stringify({ results }, null, 1) + "\n");
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})().catch((e) => { console.error(e); process.exit(2); });
