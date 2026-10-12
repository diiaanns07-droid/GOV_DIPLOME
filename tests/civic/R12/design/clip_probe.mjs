// Обрезанный текст на экранах R12 (kk и ru, 375/1366): паспорт, лист QR, кабинет, карточка работ.
import { createRequire } from "node:module"; import fs from "node:fs"; import path from "node:path";
const require = createRequire(path.join(process.env.NODE_PATH, "x.js"));
const pw = require("playwright");
const [BASE, PWF] = process.argv.slice(2); const PASS = fs.readFileSync(PWF, "utf8").trim();
const clip = (rootSel) => {
  const root = document.querySelector(rootSel); if (!root) return ["no root " + rootSel];
  const out = [];
  for (const e of root.querySelectorAll("*")) {
    if (!e.getClientRects().length) continue;
    const cs = getComputedStyle(e);
    const text = [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!text && !["INPUT", "SELECT", "BUTTON"].includes(e.tagName)) continue;
    const hx = e.scrollWidth > e.clientWidth + 1 && cs.overflowX !== "visible";
    const hy = e.scrollHeight > e.clientHeight + 1 && (cs.overflowY === "hidden" || cs.overflowY === "clip");
    const ell = cs.textOverflow === "ellipsis" && e.scrollWidth > e.clientWidth + 1;
    if (hx || hy || ell) out.push(`${e.tagName}.${String(e.className).slice(0, 30)} «${(e.textContent || e.value || "").trim().slice(0, 40)}» ${e.scrollWidth}x${e.scrollHeight}>${e.clientWidth}x${e.clientHeight}`);
  }
  return out;
};
const b = await pw.chromium.launch();
const res = {};
for (const [w, h] of [[375, 812], [1366, 768]]) for (const lang of ["kk", "ru"]) {
  const mk = async (mode) => { const ctx = await b.newContext({ viewport: { width: w, height: h } }); const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.addInitScript(([l, m]) => { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); }, [lang, mode]); return { ctx, p }; };
  const k = `${w}-${lang}`;
  // паспорт: длинное kk
  { const { ctx, p } = await mk("resident"); await p.goto(BASE + "/?report=osm-node-2639491700"); await p.waitForSelector(".bq-report .bq-title", { timeout: 30000 }).catch(() => null); await p.waitForTimeout(600);
    await p.click(".bq-more summary").catch(() => null); await p.waitForTimeout(300); res[k + " passport"] = await p.evaluate(clip, ".bq-report"); await ctx.close(); }
  // лист QR
  { const { ctx, p } = await mk("akimat"); await p.goto(BASE + "/civic/qr/print.html?lang=" + lang + "&ids=osm-node-2639491700,osm-node-4109037549"); await p.waitForTimeout(1500);
    res[k + " print"] = await p.evaluate(clip, ".bqp"); await ctx.close(); }
  // карточка работ
  { const { ctx, p } = await mk("akimat"); await p.goto(BASE + "/#object=demo-astana-roadworks-delay"); await p.waitForSelector("#civic-map-root .civic-r03-card-title", { timeout: 30000 }).catch(() => null); await p.waitForTimeout(800);
    await p.click("#civic-map-root .civic-r03-card details summary").catch(() => null); await p.waitForTimeout(300); res[k + " works"] = await p.evaluate(clip, "#civic-map-root .civic-r03-card"); await ctx.close(); }
  // кабинет: новый объект + ошибки
  { const { ctx, p } = await mk("akimat"); await p.goto(BASE + "/"); await p.waitForSelector(".birge-avatar"); await p.waitForTimeout(800);
    await p.click(".birge-avatar"); await p.click('#birge-account [data-action="staff"]'); await p.waitForSelector("#civic-editor .civic-r04-login");
    res[k + " login"] = await p.evaluate(clip, "#civic-editor .civic-r04");
    await p.fill("#civic-editor input[name=username]", "r12check"); await p.fill("#civic-editor input[name=password]", PASS); await p.press("#civic-editor input[name=password]", "Enter");
    await p.waitForSelector("#civic-editor .civic-r04-list"); res[k + " list"] = await p.evaluate(clip, "#civic-editor .civic-r04");
    await p.click("#civic-editor .civic-r04-toolbar .civic-r04-btn.primary"); await p.waitForSelector("#civic-editor .civic-r04-form");
    await p.click('#civic-editor [data-fk="save"]').catch(() => null); await p.waitForTimeout(400); res[k + " form"] = await p.evaluate(clip, "#civic-editor .civic-r04"); await ctx.close(); }
}
await b.close();
for (const [k, v] of Object.entries(res)) console.log(k, v.length, v.slice(0, 6).join(" | "));
