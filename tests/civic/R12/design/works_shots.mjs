// R12 · дизайн-марафон: карточка работ (web/civic/map) в оболочке Birge по ссылке #object=<id> — 1366/375 × ru/kk.
//   NODE_PATH=$(npm root -g) node works_shots.mjs <base> <out> [id,id…]
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
const require = createRequire(path.join(process.env.NODE_PATH, "x.js"));
const pw = require("playwright");
const [BASE, OUT, IDS] = process.argv.slice(2);
const ids = (IDS || "demo-astana-roadworks-delay").split(",");
fs.mkdirSync(OUT, { recursive: true });
const SIZES = (process.env.R12_SIZES || "1366x768,375x812").split(",").map((x) => x.split("x").map(Number));
const b = await pw.chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });
const rep = [];
for (const id of ids) for (const [w, h] of SIZES) for (const lang of ["ru", "kk"]) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: w < 500 ? 2 : 1, hasTouch: w < 500 });
  const p = await ctx.newPage();
  const errs = []; p.on("pageerror", (e) => errs.push(e.message));
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.addInitScript(([l, m]) => { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); }, [lang, process.env.R12_MODE || "resident"]);
  await p.goto(BASE + "/#object=" + id);
  await p.waitForFunction(() => { const t = document.querySelector("#civic-map-root .civic-r03-card-title"); return t && !/Карточка объекта/.test(t.textContent) && t.getClientRects().length; }, null, { timeout: 40000 }).catch(() => null);
  await p.waitForTimeout(900);
  // в панели оболочки карточка работ лежит под содержимым R07 — прокручиваем к ней (замечание R01)
  await p.evaluate(() => document.querySelector("#civic-map-root .civic-r03-card")?.scrollIntoView({ block: "start" }));
  await p.waitForTimeout(300);
  const tag = id.replace(/^demo-astana-/, "");
  await p.screenshot({ path: path.join(OUT, `${tag}-${w}-${lang}.png`) });
  const more = p.locator("#civic-map-root .civic-r03-card details summary").first();
  if (await more.count()) { await more.click().catch(() => null); await p.waitForTimeout(400); await more.evaluate((e) => e.scrollIntoView({ block: "start" })); await p.waitForTimeout(200); await p.screenshot({ path: path.join(OUT, `${tag}-more-${w}-${lang}.png`) }); }
  const m = await p.evaluate(() => {
    const r = document.querySelector("#civic-map-root .civic-r03-card"); if (!r) return null;
    const vis = [...r.querySelectorAll("*")].filter((e) => e.getClientRects().length);
    const leaf = vis.filter((e) => e.childElementCount === 0 && e.textContent.trim());
    const sizes = {}; leaf.forEach((e) => { const s = getComputedStyle(e).fontSize; sizes[s] = (sizes[s] || 0) + 1; });
    const weights = [...new Set(leaf.map((e) => getComputedStyle(e).fontWeight))];
    const small = [...r.querySelectorAll("button, a, summary, input, select")].filter((e) => e.getClientRects().length)
      .map((e) => { const q = e.getBoundingClientRect(); return { t: (e.textContent || "").trim().slice(0, 24), h: Math.round(q.height), cls: String(e.className).slice(0, 40) }; }).filter((x) => x.h < 44);
    const bg = [...new Set(vis.map((e) => getComputedStyle(e).backgroundColor).filter((c) => c !== "rgba(0, 0, 0, 0)"))];
    const colors = [...new Set(leaf.map((e) => getComputedStyle(e).color))];
    return { sizes, weights, small, bg, colors };
  });
  rep.push({ id, w, lang, ...m, errors: errs.length });
  await ctx.close();
}
await b.close();
fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(rep, null, 1));
for (const r of rep) console.log(r.id.slice(12), r.w, r.lang, "sizes", JSON.stringify(r.sizes), "w", (r.weights || []).join(","), "small", JSON.stringify(r.small), "bg", (r.bg || []).length, "colors", (r.colors || []).join(" "), "err", r.errors);
