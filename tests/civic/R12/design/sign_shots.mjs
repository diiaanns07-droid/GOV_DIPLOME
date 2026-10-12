// R12 · дизайн-марафон: лист QR-табличек — форма, таблички на экране, печать (PDF) — 1366/375 × ru/kk.
//   NODE_PATH=$(npm root -g) node sign_shots.mjs <base> <out> [size]
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
const require = createRequire(path.join(process.env.NODE_PATH, "x.js"));
const pw = require("playwright");
const [BASE, OUT, SIZE] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const IDS = ["osm-node-4109037549", "osm-node-2639491700", "osm-node-2691137163"].join(",");
const b = await pw.chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });
const rep = [];
for (const [w, h] of [[1366, 768], [375, 812]]) for (const lang of ["ru", "kk"]) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const p = await ctx.newPage();
  const errs = []; p.on("pageerror", (e) => errs.push(e.message));
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.addInitScript((l) => localStorage.setItem("birge.lang", l), lang);
  await p.goto(BASE + "/civic/qr/print.html");
  await p.waitForSelector("#bqp-root form", { timeout: 20000 });
  await p.screenshot({ path: path.join(OUT, `form-empty-${w}-${lang}.png`), fullPage: false });
  await p.goto(BASE + "/civic/qr/print.html?ids=" + encodeURIComponent(IDS) + (SIZE ? "&size=" + SIZE : ""));
  await p.waitForSelector(".bqp-sign", { timeout: 20000 });
  await p.waitForTimeout(500);
  await p.screenshot({ path: path.join(OUT, `form-signs-${w}-${lang}.png`), fullPage: true });
  const fit = await p.evaluate(() => [...document.querySelectorAll(".bqp-sign")].map((el) => ({ id: el.dataset.id, over: el.scrollHeight - el.clientHeight })));
  const first = p.locator(".bqp-sign").first();
  await first.screenshot({ path: path.join(OUT, `sign-${w}-${lang}.png`) });
  let printFit = null;
  if (w === 1366) {
    await p.emulateMedia({ media: "print" });
    printFit = await p.evaluate(() => [...document.querySelectorAll(".bqp-sign")].map((el) => { const q = el.querySelector(".bqp-qr").getBoundingClientRect(), t = getComputedStyle(el.querySelector(".bqp-sign__title"));
      return { over: el.scrollHeight - el.clientHeight, qr_mm: Math.round(q.width / 96 * 25.4), title_pt: Math.round(parseFloat(t.fontSize) * 72 / 96 * 10) / 10 }; }));
    await p.pdf({ path: path.join(OUT, `print-${lang}.pdf`), preferCSSPageSize: true, printBackground: true });
    await p.emulateMedia({ media: "screen" });
  }
  rep.push({ w, lang, fit, printFit, errors: errs });
  await ctx.close();
}
await b.close();
console.log(JSON.stringify(rep));
