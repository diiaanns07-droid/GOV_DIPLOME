/*
 * R11 · дизайн-марафон, п. 7: при системной настройке «уменьшить движение» (prefers-reduced-motion: reduce) на экранах нет
 * движения — у видимых элементов transition/animation не длиннее 50 мс (цвет/прозрачность до 50 мс допустимы).
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/reduced_motion_check.cjs http://127.0.0.1:<порт>/
 * Экраны: карта акимата/жителя, меню аватара, разделы меню (BirgeShell.setSection); 1366 и 375. Итог — по классам.
 */
"use strict";
const { chromium } = require("playwright");
const BASE = process.argv[2] || "http://127.0.0.1:8772/";
const ms = (v) => Math.max(0, ...String(v).split(",").map((x) => parseFloat(x) * (/ms/.test(x) ? 1 : 1000) || 0));

(async () => {
  const browser = await chromium.launch();
  const found = {};
  for (const [w, h] of [[1366, 768], [375, 812]]) for (const mode of ["akimat", "resident"]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, reducedMotion: process.env.NO_REDUCE ? "no-preference" : "reduce" }); // NO_REDUCE=1 — проверка самого инструмента: без настройки движение находится
    await ctx.addInitScript((m) => { try { localStorage.setItem("birge.lang", "kk"); localStorage.setItem("birge.mode", m); } catch (e) {} }, mode);
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.goto(BASE, { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 }).catch(() => {});
    await p.waitForTimeout(800);
    const scan = (tag) => p.evaluate(([t, src]) => {
      const msf = new Function("v", src);
      const out = [];
      for (const e of document.querySelectorAll("body *")) {
        const r = e.getBoundingClientRect(); if (r.width < 2 || r.height < 2) continue;
        const s = getComputedStyle(e); if (s.display === "none" || s.visibility === "hidden") continue;
        const props = s.transitionProperty, td = msf(s.transitionDuration), ad = s.animationName !== "none" ? msf(s.animationDuration) : 0;
        const moving = (td > 50 && /all|transform|translate|scale|top|left|right|bottom|height|width|margin/.test(props)) || ad > 50;
        if (moving && !e.closest(".maplibregl-canvas-container")) out.push(`${(typeof e.className === "string" && e.className.trim().split(/\s+/).slice(0, 2).join(".")) || e.tagName.toLowerCase()} · ${td > 50 ? "transition " + props.slice(0, 40) + " " + td : "animation " + s.animationName + " " + ad}ms`);
      }
      return out.map((x) => t + " · " + x);
    }, [tag, "return Math.max(0, ...String(v).split(',').map((x) => parseFloat(x) * (/ms/.test(x) ? 1 : 1000) || 0));"]);
    const add = (list) => list.forEach((x) => { const k = x.split(" · ").slice(1).join(" · "); (found[k] = found[k] || []).push(x.split(" · ")[0]); });
    add(await scan(`${mode}-${w} карта`));
    const av = await p.$(".birge-avatar"); if (av) { await av.click().catch(() => {}); await p.waitForTimeout(300); add(await scan(`${mode}-${w} меню`)); await p.keyboard.press("Escape"); }
    const ids = await p.evaluate(() => (window.BirgeShell?.navItems?.() || []).filter((id) => id !== "map" && id !== "more" && id !== "mine"));
    for (const id of ids) { await p.evaluate((s) => window.BirgeShell.setSection(s), id); await p.waitForTimeout(1800); add(await scan(`${mode}-${w} ${id}`)); }
    await ctx.close();
  }
  await browser.close();
  const rows = Object.entries(found);
  console.log(`== движение при «уменьшить движение»: ${rows.length} видов`);
  for (const [k, v] of rows.sort((a, b) => b[1].length - a[1].length).slice(0, 25)) console.log(`  ${v.length}× ${k} [${[...new Set(v)].slice(0, 3).join(", ")}]`);
  process.exit(rows.length ? 1 : 0);
})();
