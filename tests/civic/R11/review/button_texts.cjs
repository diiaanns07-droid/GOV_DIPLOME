/*
 * R11 · дизайн-марафон, п. 11: надписи кнопок на всех экранах (ru и kk) — глагол ли, и не называется ли одно действие
 * по-разному в разных разделах. Экраны: карта, карточка цели, разделы меню, мастер жалобы; 1366; акимат и житель.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/button_texts.cjs http://127.0.0.1:<порт>/ [ru|kk]
 */
"use strict";
const { chromium } = require("playwright");
const [BASE = "http://127.0.0.1:8773/", LANG = "ru"] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch();
  const seen = {};
  for (const mode of ["akimat", "resident"]) {
    const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
    await ctx.addInitScript(([l, m]) => { try { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); } catch (e) {} }, [LANG, mode]);
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.goto(BASE, { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 }).catch(() => {});
    await p.waitForTimeout(800);
    const grab = (where) => p.evaluate((wh) => [...document.querySelectorAll("button, a.bk-btn, [role=button], summary")].filter((e) => {
      const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 2 && r.height > 2 && s.visibility !== "hidden" && !e.closest("#birge-header, .topbar, .map-tools, .maplibregl-ctrl, .bk-tabs, [role=tablist]");
    }).map((e) => [(e.innerText || e.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim(), (typeof e.className === "string" ? e.className.split(/\s+/)[0] : "") + (e.tagName === "SUMMARY" ? " (summary)" : ""), wh]), where);
    const add = (list) => list.forEach(([t, c, w]) => { if (!t || /^\d+$/.test(t)) return; const k = t.length > 40 ? t.slice(0, 40) + "…" : t; const r = seen[k] || (seen[k] = { n: 0, where: new Set(), cls: new Set() }); r.n++; r.where.add(w); r.cls.add(c); });
    add(await grab(`${mode} карта`));
    if (await p.evaluate(() => { const b = document.querySelector(".r07-item[data-key]"); if (b) { b.click(); return true; } return false; })) { await p.waitForTimeout(2000); add(await grab(`${mode} карточка`)); await p.keyboard.press("Escape"); await p.waitForTimeout(500); }
    const ids = await p.evaluate(() => (window.BirgeShell?.navItems?.() || []).filter((id) => id !== "map" && id !== "more"));
    for (const id of [...ids, "questions", "works", "services"]) {
      await p.evaluate((s) => { try { if (s === "mine") { window.BirgeShell.setSection("map"); window.CivicShell?.openMine?.(); } else window.BirgeShell.setSection(s); } catch (e) {} }, id);
      await p.waitForTimeout(2200); add(await grab(`${mode} ${id}`));
      await p.evaluate(() => window.BirgeShell.setSection("map")); await p.waitForTimeout(400);
    }
    if (mode === "resident") { const fab = await p.$(".bc-fab"); if (fab) { await fab.click().catch(() => {}); await p.waitForTimeout(1500); add(await grab("житель мастер")); } }
    await ctx.close();
  }
  await browser.close();
  const rows = Object.entries(seen).sort((a, b) => a[0].localeCompare(b[0], LANG));
  console.log(`== ${LANG}: ${rows.length} разных надписей кнопок`);
  for (const [t, r] of rows) console.log(`  «${t}» ×${r.n} · ${[...r.cls].join(",")} · ${[...r.where].slice(0, 3).join("; ")}`);
})();
