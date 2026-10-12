// Фокус с клавиатуры на экранах R12: Tab по первым N элементам внутри экрана — видно ли кольцо (outline или box-shadow).
import { createRequire } from "node:module"; import fs from "node:fs"; import path from "node:path";
const require = createRequire(path.join(process.env.NODE_PATH, "x.js"));
const pw = require("playwright");
const [BASE, PWF] = process.argv.slice(2); const PASS = fs.readFileSync(PWF, "utf8").trim();
const b = await pw.chromium.launch();
const ring = (rootSel) => { const a = document.activeElement; if (!a || !a.closest(rootSel)) return null; const cs = getComputedStyle(a);
  const vis = (cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 2) || (cs.boxShadow && cs.boxShadow !== "none");
  return { tag: a.tagName, t: (a.textContent || a.getAttribute("aria-label") || a.name || "").trim().slice(0, 22), vis, outline: cs.outlineStyle + " " + cs.outlineWidth + " " + cs.outlineColor }; };
const run = async (name, url, rootSel, prep) => {
  const p = await (await b.newContext({ viewport: { width: 1366, height: 768 } })).newPage();
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.addInitScript(() => { localStorage.setItem("birge.lang", "ru"); localStorage.setItem("birge.mode", "akimat"); });
  await p.goto(BASE + url); await p.waitForTimeout(1500);
  if (prep) await prep(p);
  await p.evaluate((s) => { const r = document.querySelector(s); const f = r && r.querySelector("button, a[href], input, select, textarea, summary, [tabindex='0']"); if (f) { f.focus(); f.blur(); } const x = document.createElement("button"); x.id = "__start"; r.prepend(x); x.focus(); }, rootSel);
  const out = [];
  for (let i = 0; i < 12; i++) { await p.keyboard.press("Tab"); const r = await p.evaluate(ring, rootSel); if (r) out.push(r); }
  const bad = out.filter((r) => !r.vis);
  console.log(name, "focused", out.length, "without ring", bad.length, JSON.stringify(bad.slice(0, 4)));
  await p.close();
};
await run("passport", "/?report=osm-node-4109037549", ".bq-report");
await run("print", "/civic/qr/print.html?ids=osm-node-4109037549", ".bqp");
await run("works", "/#object=demo-astana-roadworks-delay", "#civic-map-root .civic-r03-card", async (p) => { await p.waitForSelector("#civic-map-root .civic-r03-card-title"); });
await run("cabinet", "/", "#civic-editor .civic-r04", async (p) => {
  await p.click(".birge-avatar"); await p.click('#birge-account [data-action="staff"]'); await p.waitForSelector("#civic-editor .civic-r04-login");
  await p.fill("#civic-editor input[name=username]", "r12check"); await p.fill("#civic-editor input[name=password]", PASS); await p.press("#civic-editor input[name=password]", "Enter");
  await p.waitForSelector("#civic-editor .civic-r04-list"); await p.click("#civic-editor .civic-r04-toolbar .civic-r04-btn.primary"); await p.waitForSelector("#civic-editor .civic-r04-form"); });
await b.close();
