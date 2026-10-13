// R12 · дизайн-марафон: паспорт объекта по QR во всех состояниях — 375/1366 × ru/kk.
//   NODE_PATH=$(npm root -g) node passport_shots.mjs <base> <out> [state,state…]
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
const require = createRequire(path.join(process.env.NODE_PATH, "x.js"));
const pw = require("playwright");
const [BASE, OUT, ONLY] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const STOP = "osm-node-4109037549";
// R12_SIZES=375x812,1024x768,1366x768 — другие размеры экрана (проектор 1024); по умолчанию 375 и 1366.
const SIZES = (process.env.R12_SIZES || "375x812,1366x768").split(",").map((x) => x.split("x").map(Number));
const STATES = {
  loading: { id: STOP, route: "hold" },
  open: { id: STOP },
  details: { id: STOP, act: "details" },
  metoo: { id: STOP, act: "metoo" },
  empty: { id: "osm-node-2691137163" },
  fixed: { id: "osm-node-13335403725" },
  notfound: { id: "osm-node-1" },
  offline: { id: STOP, route: "abort" },
  longkk: { id: "osm-node-2639491700" },
};
const only = ONLY ? ONLY.split(",") : Object.keys(STATES);
const b = await pw.chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });
const report = [];
for (const name of only) {
  const st = STATES[name];
  for (const [w, h] of SIZES) for (const lang of ["ru", "kk"]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h }, hasTouch: w < 500, deviceScaleFactor: w < 500 ? 2 : 1 });
    const p = await ctx.newPage();
    const errs = []; p.on("pageerror", (e) => errs.push(e.message));
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    if (st.route === "hold") await p.route(/\/api\/civic\/v2\/target\?/, async (r) => { await new Promise((ok) => setTimeout(ok, 6000)); r.continue().catch(() => {}); });
    if (st.route === "abort") await p.route(/\/api\/civic\/v2\/target\?/, (r) => r.abort("internetdisconnected"));
    await p.addInitScript((l) => localStorage.setItem("birge.lang", l), lang);
    await p.goto(BASE + "/?report=" + st.id);
    if (st.route === "hold") { await p.waitForSelector("#birge-report-root .bq-report", { timeout: 30000 }); await p.waitForTimeout(700); }
    else await p.waitForFunction(() => /ready|error/.test(document.querySelector("#birge-report-root .bq-report")?.dataset.state || ""), null, { timeout: 30000 });
    await p.waitForTimeout(900);
    if (st.act === "details") { await p.click('#birge-report-root .bq-tab[data-tab="cases"]'); await p.waitForSelector("#birge-report-root .bq-cases li", { timeout: 8000 }).catch(() => null); await p.waitForTimeout(300);
      await p.evaluate(() => document.querySelector("#birge-report-root .bq-tabs")?.scrollIntoView({ block: "start" })); await p.waitForTimeout(300); }
    if (st.act === "metoo") { await p.click('#birge-report-root [data-act="metoo"]').catch(() => null); await p.waitForSelector("#birge-report-root .bq-notice", { timeout: 8000 }).catch(() => null); await p.waitForTimeout(400); }
    const file = `${name}-${w}-${lang}.png`;
    await p.screenshot({ path: path.join(OUT, file) });
    const m = await p.evaluate(() => {
      const r = document.querySelector("#birge-report-root .bq-report"); if (!r) return null;
      const all = [...r.querySelectorAll("*")].filter((e) => e.childElementCount === 0 && e.textContent.trim() && e.getClientRects().length);
      const sizes = [...new Set(all.map((e) => getComputedStyle(e).fontSize))];
      const weights = [...new Set(all.map((e) => getComputedStyle(e).fontWeight))];
      const small = [...r.querySelectorAll("button, a, summary, [role=tab]")].filter((e) => e.getClientRects().length).map((e) => { const q = e.getBoundingClientRect(); return { t: (e.textContent || e.getAttribute("aria-label") || "").trim().slice(0, 24), h: Math.round(q.height), w: Math.round(q.width) }; }).filter((x) => x.h < 44 || x.w < 44);
      const primary = r.querySelectorAll(".bk-btn--primary").length;
      return { sizes, weights, small, primary, state: r.dataset.state };
    });
    report.push({ name, w, lang, file, ...m, errors: errs.length });
    await ctx.close();
  }
}
await b.close();
fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 1));
for (const r of report) console.log(r.name, r.w, r.lang, "sizes", (r.sizes || []).join(" "), "weights", (r.weights || []).join(" "), "small", JSON.stringify(r.small), "primary", r.primary, "err", r.errors);
