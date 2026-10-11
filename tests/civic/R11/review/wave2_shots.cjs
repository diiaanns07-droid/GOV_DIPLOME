/*
 * R11 · волна 2: снимки всех разделов меню (IA_WAVE2 §1) — акимат и житель, 1366×768 и 375×812, kk и ru.
 * Для каждого раздела: кадр, слова-ключи вместо текста, русские строки в ҚАЗ (как ru_kk_same), главные кнопки,
 * прокрутка вбок, ошибки консоли. Плюс кадр открытого меню и списка «Слой на карте».
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/wave2_shots.cjs http://127.0.0.1:8629/ <папка>
 * ALL=1 — открыть с ?screens=all (R01: разделы видны, даже если модуль роли ещё не в сборке — заглушка «скоро»).
 */
"use strict";
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const [BASE, OUT] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const KEYLIKE = /\b[a-z][a-z0-9_]*(\.[a-z0-9_]+){2,}\b/;

async function open(browser, mode, lang, w, h) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  p.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|openfreemap|net::ERR/i.test(m.text())) errors.push(m.text()); });
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.addInitScript(({ l, m }) => { try { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); } catch (e) {} }, { l: lang, m: mode });
  await p.goto(BASE + (process.env.ALL ? "?screens=all" : ""));
  await p.waitForFunction(() => window.CivicShell && typeof mapReady !== "undefined" && mapReady, null, { timeout: 45000 });
  await p.waitForTimeout(1800);
  return { ctx, p, errors };
}
const facts = (p) => p.evaluate((src) => {
  const KEY = new RegExp(src);
  const vis = (e) => e.getClientRects().length && getComputedStyle(e).visibility !== "hidden";
  const scr = document.querySelector("#birge-screen:not([hidden]), [data-screen]:not([hidden])") || document.body;
  const texts = [];
  const walk = (n) => { for (const c of n.childNodes) { if (c.nodeType === 3 && c.textContent.trim() && c.parentElement && vis(c.parentElement)) texts.push(c.textContent.trim()); else if (c.nodeType === 1 && !/SCRIPT|STYLE/.test(c.tagName)) walk(c); } };
  walk(scr);
  const primaries = [...scr.querySelectorAll(".bk-btn--primary")].filter(vis).map((b) => b.textContent.trim().slice(0, 40));
  return { keys: texts.filter((t) => KEY.test(t)).slice(0, 10), cyr: texts, primaries, hscroll: document.documentElement.scrollWidth > innerWidth + 1,
    small: [...scr.querySelectorAll("button, a, [role=button], input, select")].filter(vis).filter((b) => { const r = b.getBoundingClientRect(); return r.height < 40 && r.width > 0; }).map((b) => (b.textContent.trim() || b.getAttribute("aria-label") || b.tagName).slice(0, 30)).slice(0, 8) };
}, KEYLIKE.source);

(async () => {
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const report = {};
  for (const [w, h] of [[1366, 768], [375, 812]]) for (const lang of ["kk", "ru"]) for (const mode of ["akimat", "resident"]) {
    const { ctx, p, errors } = await open(browser, mode, lang, w, h);
    const tag = `${mode}-${w}-${lang}`;
    const menuBtn = await p.$(".birge-menu-btn");
    if (menuBtn && (await menuBtn.isVisible())) { await menuBtn.click(); await p.waitForTimeout(400); }
    await p.screenshot({ path: path.join(OUT, `w2-${tag}-0-menu.png`) });
    const sections = await p.evaluate(() => [...document.querySelectorAll("#birge-header [data-section]")]
      .filter((b) => b.getClientRects().length && getComputedStyle(b).visibility !== "hidden").map((b) => ({ id: b.dataset.section, text: b.textContent.trim() })));
    report[tag] = { sections, screens: {} };
    if (menuBtn && (await menuBtn.isVisible())) { await p.keyboard.press("Escape"); await p.waitForTimeout(300); }
    // «Слой на карте»
    const layerBtn = await p.$("#birge-layer-btn");
    if (layerBtn && (await layerBtn.isVisible())) { await layerBtn.click(); await p.waitForTimeout(400); await p.screenshot({ path: path.join(OUT, `w2-${tag}-0-layers.png`) }); report[tag].layers = await p.evaluate(() => [...document.querySelectorAll("#birge-layer-list label")].map((l) => l.textContent.trim())); await layerBtn.click(); }
    const ids = sections.map((s) => s.id).filter((id) => id !== "map");
    const more = [];
    for (const id of ids) {
      await p.evaluate((sid) => { const b = document.querySelector(`#birge-header [data-section="${sid}"]`); if (b) b.click(); }, id);
      await p.waitForTimeout(2200);
      await p.screenshot({ path: path.join(OUT, `w2-${tag}-${id}.png`), fullPage: true });
      report[tag].screens[id] = await facts(p);
      if (id === "more") more.push(...(await p.evaluate(() => [...document.querySelectorAll(".birge-more-item[data-section]")].map((b) => b.dataset.section))));
    }
    for (const id of more) {
      await p.evaluate((sid) => { const b = document.querySelector(`#birge-header [data-section="more"]`); if (b) b.click(); }, id);
      await p.waitForTimeout(800);
      await p.evaluate((sid) => { const b = document.querySelector(`.birge-more-item[data-section="${sid}"]`); if (b) b.click(); }, id);
      await p.waitForTimeout(2200);
      await p.screenshot({ path: path.join(OUT, `w2-${tag}-more-${id}.png`), fullPage: true });
      report[tag].screens["more/" + id] = await facts(p);
    }
    report[tag].errors = [...new Set(errors)].slice(0, 6);
    await ctx.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, "wave2.json"), JSON.stringify(report, null, 1));
  // ru в ҚАЗ: строка из ru-прогона, которая дословно стоит и в kk-прогоне того же экрана
  for (const [tag, r] of Object.entries(report)) {
    const ruTag = tag.replace(/-kk$/, "-ru");
    console.log(`${tag}: меню ${r.sections.map((s) => s.text).join(" · ")}` + (r.layers ? ` · слои: ${r.layers.join(" / ")}` : "") + (r.errors.length ? ` · ОШИБКИ: ${r.errors.join(" | ").slice(0, 200)}` : ""));
    for (const [id, f] of Object.entries(r.screens)) {
      const notes = [];
      if (f.keys.length) notes.push("КЛЮЧИ: " + f.keys.join(", "));
      if (f.primaries.length > 1) notes.push("главных кнопок " + f.primaries.length + ": " + f.primaries.join(" / "));
      if (f.hscroll) notes.push("прокрутка вбок");
      if (f.small.length) notes.push("ниже 40 px: " + f.small.join(", "));
      if (tag.endsWith("-kk") && report[ruTag] && report[ruTag].screens[id]) {
        const ru = new Set(report[ruTag].screens[id].cyr.filter((t) => /[а-яё]{3,}/i.test(t) && !/[әғқңөұүһі]/i.test(t)));
        const same = f.cyr.filter((t) => ru.has(t) && t.length > 3);
        if (same.length) notes.push("русские строки в ҚАЗ: " + [...new Set(same)].slice(0, 6).join(" | "));
      }
      console.log(`   ${id}: ${notes.length ? notes.join(" · ") : "ок"}`);
    }
  }
})().catch((e) => { console.error(e); process.exit(2); });
