/*
 * R11 · аудит единства чистого стиля (CLEAN_PASS, решение владельца 12 окт) на сборке R01.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/clean_audit.cjs http://127.0.0.1:<порт>/ <out.json>
 * Экраны: карта (акимат/житель), открытая карточка цели, «Картина дня», мастер жалобы, «Мои обращения» и разделы меню
 * (через BirgeShell.setSection), 1366 и 375, ru. Для каждого видимого элемента с собственным текстом или заливкой:
 *   legacy  — цвет текста/фона/рамки близок к старой палитре (лайм, бежевый, зелёный #176b4a, голубые плашки R07…);
 *   weight  — вес шрифта не 400/600;
 *   tiny    — текст < 13 px;
 *   framed  — плашка/карточка с рамкой 1–2 px (не поле ввода и не фокус) — в чистом дизайне рамок нет.
 * Итог — по классу элемента (первые 2 класса): сколько раз и пример текста. Срочный баннер 104/112 — исключение.
 */
"use strict";
const fs = require("fs");
const { chromium } = require("playwright");
const BASE = process.argv[2] || "http://127.0.0.1:8732/";
const OUT = process.argv[3] || "clean_audit.json";

const LEGACY = {
  "#176b4a": "старый зелёный бренд", "#125d40": "старый зелёный (наведение)", "#d7f57c": "лайм", "#f1fbd6": "лайм светлый",
  "#f1fbd3": "лайм светлый", "#b6d65a": "лайм (рамка)", "#f7f8f4": "старая бумага (беж-зелёный)", "#f1efe6": "бежевая плашка R07",
  "#eaf2fb": "голубая плашка R07", "#e6f1eb": "старый brand-soft", "#eef2ea": "серо-зелёная подложка R07", "#c9d4c5": "зеленоватая рамка",
  "#f3efe6": "бежевый", "#f6f3ea": "бежевый", "#eef1ea": "зеленоватая подложка", "#7e9b68": "оливковый раунда 13",
};
const hex2rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const LEG = Object.entries(LEGACY).map(([h, name]) => ({ h, name, rgb: hex2rgb(h) }));

const ready = (p) => p.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady
  && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 }).then(() => p.waitForTimeout(1200));

async function scan(p) {
  return p.evaluate((leg) => {
    const parse = (c) => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return v.length >= 3 && (v[3] === undefined || v[3] > 0.05) ? v.slice(0, 3) : null; };
    const near = (rgb) => { if (!rgb) return null; for (const l of leg) { if (Math.abs(rgb[0] - l.rgb[0]) + Math.abs(rgb[1] - l.rgb[1]) + Math.abs(rgb[2] - l.rgb[2]) <= 4) return l; } return null; };
    const vis = (e) => { const b = e.getBoundingClientRect(), s = getComputedStyle(e); return b.width > 0 && b.height > 0 && b.bottom > 0 && b.top < innerHeight && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0"; };
    const key = (e) => (e.className && typeof e.className === "string" ? e.className.trim().split(/\s+/).slice(0, 2).join(".") : e.tagName.toLowerCase()) || e.tagName.toLowerCase();
    const out = { legacy: {}, weight: {}, tiny: {}, framed: {} };
    const add = (bucket, k, ex) => { const r = bucket[k] || (bucket[k] = { n: 0, ex: "" }); r.n++; if (!r.ex && ex) r.ex = ex.slice(0, 50); };
    for (const e of document.querySelectorAll("body *")) {
      if (!vis(e) || e.closest("svg, canvas, .maplibregl-canvas-container, .maplibregl-ctrl-attrib, script, style, .bc-emergency, .bk-banner--danger")) continue;
      const s = getComputedStyle(e);
      const own = [...e.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim());
      const text = own ? e.textContent.trim() : "";
      const k = key(e);
      for (const [prop, val] of [["color", own ? s.color : null], ["background", s.backgroundColor], ["border", parseFloat(s.borderTopWidth) > 0 ? s.borderTopColor : null]]) {
        const l = near(parse(val)); if (l) add(out.legacy, `${k} · ${prop} ${l.h} (${l.name})`, text);
      }
      if (own) {
        const w = s.fontWeight; if (w !== "400" && w !== "600") add(out.weight, `${k} · ${w}`, text);
        if (parseFloat(s.fontSize) < 13) add(out.tiny, `${k} · ${s.fontSize}`, text);
      }
      const bw = parseFloat(s.borderTopWidth), bc = parse(s.borderTopColor);
      const isField = /INPUT|SELECT|TEXTAREA/.test(e.tagName);
      if (!isField && bw >= 1 && bw <= 2 && bc && s.borderTopStyle !== "none" && parseFloat(s.borderRightWidth) >= 1 && parseFloat(s.borderBottomWidth) >= 1
        && parseFloat(s.borderRadius) >= 6 && e.getBoundingClientRect().width > 60) add(out.framed, k, e.textContent.trim());
    }
    return out;
  }, LEG);
}

(async () => {
  const browser = await chromium.launch();
  const total = { legacy: {}, weight: {}, tiny: {}, framed: {} };
  const perScreen = {};
  const merge = (r, screen) => {
    for (const b of Object.keys(total)) for (const [k, v] of Object.entries(r[b])) {
      const t = total[b][k] || (total[b][k] = { n: 0, ex: v.ex, screens: [] });
      t.n += v.n; if (!t.screens.includes(screen)) t.screens.push(screen);
    }
    perScreen[screen] = Object.fromEntries(Object.keys(total).map((b) => [b, Object.values(r[b]).reduce((a, v) => a + v.n, 0)]));
  };
  for (const [w, h] of [[1366, 768], [375, 812]]) for (const mode of ["akimat", "resident"]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    await ctx.addInitScript((m) => { try { localStorage.setItem("birge.lang", "ru"); localStorage.setItem("birge.mode", m); } catch (e) {} }, mode);
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.goto(BASE, { waitUntil: "domcontentloaded" });
    await ready(p).catch(() => {});
    const tag = `${mode}-${w}`;
    merge(await scan(p), `${tag} карта`);
    // карточка первой цели из «Горячих мест»
    const opened = await p.evaluate(() => { const b = document.querySelector(".r07-item[data-key]"); if (b) { b.click(); return true; } return false; });
    if (opened) { await p.waitForTimeout(2500); merge(await scan(p), `${tag} карточка`); await p.keyboard.press("Escape"); await p.waitForTimeout(600); }
    const ids = await p.evaluate(() => (window.BirgeShell?.navItems?.() || []).filter((id) => id !== "map" && id !== "more"));
    for (const id of ids) {
      await p.evaluate((sid) => { if (sid === "mine") { window.BirgeShell.setSection("map"); window.CivicShell?.openMine?.(); } else window.BirgeShell.setSection(sid); }, id);
      await p.waitForTimeout(2600);
      merge(await scan(p), `${tag} ${id}`);
      await p.evaluate(() => window.BirgeShell.setSection("map")); await p.waitForTimeout(600);
    }
    if (mode === "resident") { // мастер жалобы, шаг 1
      const fab = await p.$(".bc-fab"); if (fab) { await fab.click().catch(() => {}); await p.waitForTimeout(1500); merge(await scan(p), `${tag} мастер`); }
    }
    await ctx.close();
  }
  await browser.close();
  const top = (b) => Object.entries(total[b]).sort((a, c) => c[1].n - a[1].n);
  fs.writeFileSync(OUT, JSON.stringify({ perScreen, total }, null, 1));
  for (const b of ["legacy", "weight", "tiny", "framed"]) {
    const rows = top(b);
    console.log(`\n== ${b}: ${rows.length} видов, ${rows.reduce((a, r) => a + r[1].n, 0)} элементов`);
    for (const [k, v] of rows.slice(0, 18)) console.log(`  ${v.n}× ${k} — «${v.ex}» [${v.screens.slice(0, 3).join(", ")}${v.screens.length > 3 ? ", …" : ""}]`);
  }
})();
