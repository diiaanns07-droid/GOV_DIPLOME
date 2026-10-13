// R12 · эталон A: паспорт QR в приложении (с предложенной карточкой R01 слева) — кадры «стало» 1366/375 × ru/kk × состояния.
//   NODE_PATH=$(npm root -g) node ref_compare.mjs <base> <out> <card.css> [state,state…]
import { createRequire } from "node:module"; import fs from "node:fs"; import path from "node:path";
const require = createRequire(path.join(process.env.NODE_PATH, "x.js"));
const pw = require("playwright");
const [BASE, OUT, CSS, ONLY] = process.argv.slice(2);
const css = fs.readFileSync(CSS, "utf8");
fs.mkdirSync(OUT, { recursive: true });
const STATES = { open: "osm-node-4109037549", cases: "osm-node-4109037549", history: "osm-node-4109037549", metoo: "osm-node-4109037549",
  empty: "osm-node-2691137163", notfound: "osm-node-1", longkk: "osm-node-2639491700" };
const only = ONLY ? ONLY.split(",") : Object.keys(STATES);
const b = await pw.chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });
const rep = [];
for (const st of only) for (const [w, h] of [[1366, 768], [375, 812]]) for (const lang of ["ru", "kk"]) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: w < 500 ? 2 : 1, hasTouch: w < 500 });
  const p = await ctx.newPage(); const errs = []; p.on("pageerror", (e) => errs.push(e.message));
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.addInitScript((l) => { localStorage.setItem("birge.lang", l); }, lang);
  await p.goto(BASE + "/?report=" + STATES[st]);
  await p.addStyleTag({ content: css });
  await p.waitForSelector(".bq-report[data-state=ready], .bq-report[data-state=error]", { timeout: 30000 }).catch(() => null);
  await p.waitForTimeout(700);
  if (st === "cases" || st === "history") { await p.click(`.bq-tab[data-tab="${st}"]`).catch(() => null); await p.waitForTimeout(900); }
  if (st === "metoo") { await p.click('.bq-report [data-act="metoo"]').catch(() => null); await p.waitForSelector(".bq-notice", { timeout: 8000 }).catch(() => null); await p.waitForTimeout(700); }
  await p.screenshot({ path: path.join(OUT, `${st}-${w}-${lang}.png`) });
  const m = await p.evaluate(() => {
    const r = document.querySelector(".bq-report"); if (!r) return null;
    const leaf = [...r.querySelectorAll("*")].filter((e) => e.getClientRects().length && [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()));
    const sizes = [...new Set(leaf.map((e) => getComputedStyle(e).fontSize))];
    const weights = [...new Set(leaf.map((e) => getComputedStyle(e).fontWeight))];
    const small = [...r.querySelectorAll("button, a, summary, [role=tab]")].filter((e) => e.getClientRects().length).map((e) => { const q = e.getBoundingClientRect(); return { t: (e.textContent || e.getAttribute("aria-label") || "").trim().slice(0, 18), w: Math.round(q.width), h: Math.round(q.height) }; }).filter((x) => x.h < 44 || x.w < 24);
    const box = r.getBoundingClientRect(), panel = r.closest(".civic-panel")?.getBoundingClientRect();
    return { sizes, weights, small, card: panel ? [Math.round(panel.left), Math.round(panel.top), Math.round(panel.width), Math.round(panel.height)] : null, h: Math.round(box.height) };
  });
  rep.push({ st, w, lang, ...m, errors: errs.length });
  await ctx.close();
}
await b.close();
fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(rep, null, 1));
for (const r of rep) console.log(r.st, r.w, r.lang, "sizes", (r.sizes || []).join(" "), "w", (r.weights || []).join(" "), "small", JSON.stringify(r.small), "card", JSON.stringify(r.card), "err", r.errors);
