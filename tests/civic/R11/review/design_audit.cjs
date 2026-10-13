/*
 * R11 · дизайн-марафон: автоматическая часть чек-листа качества (research/round-14/DESIGN_MARATHON.md) по экранам сборки.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/design_audit.cjs http://127.0.0.1:<порт>/ <out.json>
 * Экраны: карта акимата/жителя, карточка цели, разделы меню (BirgeShell.setSection), мастер жалобы; 1366 и 375; ru.
 * Пункты чек-листа (номер — как в DESIGN_MARATHON):
 *   3  типографика — размеры шрифта видимого текста (эталон A 13 окт: шкала 12/13/14/15/16/18/19/22/34), веса не
 *      400/500/600 (700 — только числа в плашках и значках), строки длиннее 70 знаков (блоки текста);
 *   2  сетка — в эталоне A отступы свои (18, 10, 13, 7…), поэтому кратность 4 только считается для справки, не ошибка;
 *   6  глубина — тень внутри тени (элемент с box-shadow внутри предка с box-shadow, кроме стекла и фокуса);
 *   7  движение — transition/animation длиннее 350 мс (кроме пульса bk-pulse/r07-pulse);
 *   9  иконки — видимая толщина линии svg.ic (линия × размер / 24) вне 1,4–2,4 px (кроме .ic--48 и иллюстраций .bk-ill);
 *   10 нажатия — кнопки/ссылки меньше 44 px по меньшей стороне; кнопки без видимой подписи и без aria-label.
 * Итог — по пунктам и классам (первые 2 класса), с примером текста.
 */
"use strict";
const fs = require("fs");
const { chromium } = require("playwright");
const BASE = process.argv[2] || "http://127.0.0.1:8752/";
const OUT = process.argv[3] || "design_audit.json";
const SCALE = new Set([12, 13, 14, 15, 16, 18, 19, 22, 34]); // эталон A (REFERENCE.html, 13 окт)

const ready = (p) => p.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady
  && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 }).then(() => p.waitForTimeout(1500));

async function audit(p) {
  return p.evaluate((scale) => {
    const S = new Set(scale);
    const vis = (e) => { const b = e.getBoundingClientRect(), s = getComputedStyle(e); return b.width > 1 && b.height > 1 && /* 1×1 — текст для диктора */ b.bottom > 0 && b.top < innerHeight && b.right > 0 && b.left < innerWidth && s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0.05; };
    const key = (e) => (typeof e.className === "string" && e.className.trim() ? e.className.trim().split(/\s+/).slice(0, 2).join(".") : e.tagName.toLowerCase());
    const skip = (e) => e.closest(".maplibregl-canvas-container, .maplibregl-ctrl-attrib, script, style, code, .maplibregl-marker, .bk-sr-only");
    const ms = (v) => Math.max(0, ...String(v).split(",").map((x) => parseFloat(x) * (/ms/.test(x) ? 1 : 1000) || 0));
    const out = { sizes: {}, offscale: {}, weight: {}, long: {}, grid: {}, shadow2: {}, motion: {}, icon: {}, small: {}, unnamed: {} };
    const add = (b, k, ex) => { const r = out[b][k] || (out[b][k] = { n: 0, ex: "" }); r.n++; if (!r.ex && ex) r.ex = String(ex).slice(0, 60); };
    for (const e of document.querySelectorAll("body *")) {
      if (!vis(e) || skip(e)) continue;
      const s = getComputedStyle(e), k = key(e);
      const own = [...e.childNodes].filter((c) => c.nodeType === 3).map((c) => c.textContent).join("").trim();
      if (own) {
        const fs = Math.round(parseFloat(s.fontSize));
        out.sizes[fs] = (out.sizes[fs] || 0) + 1;
        if (!S.has(fs) && fs !== 16) add("offscale", `${k} · ${fs}px`, own); // 16 — поля ввода (iOS не увеличивает)
        const numPlate = s.fontWeight === "700" && /^[\d\s✓·+]+$/.test(own); // числа в плашках и значках — 700 (эталон .n/.cnt)
        if (!["400", "500", "600"].includes(s.fontWeight) && !numPlate) add("weight", `${k} · ${s.fontWeight}`, own);
        if (own.length > 70 && e.getBoundingClientRect().width / (parseFloat(s.fontSize) * 0.5) > 80) add("long", `${k} · ${Math.round(e.getBoundingClientRect().width)}px`, own);
      }
      for (const prop of ["paddingTop", "paddingLeft", "rowGap", "columnGap"]) {
        const v = parseFloat(s[prop]);
        if (v > 0 && v % 4 !== 0 && !(prop.endsWith("Gap") && s.display.indexOf("flex") < 0 && s.display.indexOf("grid") < 0)) { add("grid", `${k} · ${prop} ${v}px`, own); break; }
      }
      if (s.boxShadow !== "none" && !/inset/.test(s.boxShadow) && !e.matches(".bk-glass, .bk-glass--control, :focus, :focus-visible")) {
        let a = e.parentElement;
        while (a && a !== document.body) {
          const as = getComputedStyle(a);
          if (as.boxShadow !== "none" && !/^inset/.test(as.boxShadow) && !a.matches(".bk-glass, .bk-glass--control") && !(as.boxShadow.match(/inset/g) || []).length) { add("shadow2", `${k} в ${key(a)}`, own); break; }
          a = a.parentElement;
        }
      }
      const td = ms(s.transitionDuration), ad = s.animationName !== "none" ? ms(s.animationDuration) : 0;
      // Linear (правило 6): движение 150–250 мс; порог 300 (эталон: «карточка выезжает за 300 мс») — длиннее считаем
      if ((td > 300 || ad > 300) && !/pulse|spin|skel|shimmer/i.test(s.animationName + " " + k)) add("motion", `${k} · ${td > 300 ? "transition " + td : "animation " + s.animationName + " " + ad}ms`, own);
      if (e.matches("svg.ic:not(.ic--48)")) { /* видимая толщина = линия × размер / 24 (viewBox): у значка 20 px при линии 2 — 1,67 px; норма 1,4–2,4 px; 48 px в пустых состояниях — крупный рисунок (ui-kit) */ const w = parseFloat(s.strokeWidth), px = w * e.getBoundingClientRect().width / 24; if (w && (px < 1.4 || px > 2.4)) add("icon", `${key(e.parentElement)} · линия ${w} → ${px.toFixed(1)} px`, ""); }
      if (e.matches("button, a[href], [role=button], [role=tab], [role=menuitem], [role=menuitemradio], summary")) {
        const b = e.getBoundingClientRect();
        // невидимое расширение зоны нажатия (ui-kit: ::after с отрицательным inset — сегмент 30, «Поддержать» 32, × 32 → 44)
        const a = getComputedStyle(e, "::after"), neg = (v) => Math.max(0, -parseFloat(v) || 0);
        const ext = a.content !== "none" && a.position === "absolute"
          ? { w: neg(a.left) + neg(a.right), h: neg(a.top) + neg(a.bottom) } : { w: 0, h: 0 };
        if (Math.min(b.width + ext.w, b.height + ext.h) < 43.5 && !e.closest(".maplibregl-marker")) add("small", `${k} · ${Math.round(b.width)}×${Math.round(b.height)}`, e.textContent.trim() || e.getAttribute("aria-label"));
        if (!e.textContent.trim() && !e.getAttribute("aria-label") && !e.getAttribute("title") && !e.getAttribute("aria-labelledby")) add("unnamed", k, "");
      }
    }
    return out;
  }, [...SCALE]);
}

(async () => {
  const browser = await chromium.launch();
  const screens = {};
  const total = {};
  const merge = (name, r) => {
    screens[name] = { sizes: Object.keys(r.sizes).map(Number).sort((a, b) => a - b) };
    for (const [b, items] of Object.entries(r)) {
      if (b === "sizes") continue;
      for (const [k, v] of Object.entries(items)) {
        const t = (total[b] = total[b] || {})[k] || (total[b][k] = { n: 0, ex: v.ex, screens: [] });
        t.n += v.n; if (!t.screens.includes(name)) t.screens.push(name);
      }
    }
  };
  for (const [w, h] of [[1366, 768], [375, 812]]) for (const mode of ["akimat", "resident"]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    await ctx.addInitScript((m) => { try { localStorage.setItem("birge.lang", "ru"); localStorage.setItem("birge.mode", m); } catch (e) {} }, mode);
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.goto(BASE, { waitUntil: "domcontentloaded" });
    await ready(p).catch(() => {});
    const tag = `${mode}-${w}`;
    merge(`${tag} карта`, await audit(p));
    if (await p.evaluate(() => { const b = document.querySelector(".r07-item[data-key]"); if (b) { b.click(); return true; } return false; })) {
      await p.waitForTimeout(2500); merge(`${tag} карточка`, await audit(p)); await p.keyboard.press("Escape"); await p.waitForTimeout(600);
    }
    const ids = await p.evaluate(() => (window.BirgeShell?.navItems?.() || []).filter((id) => id !== "map" && id !== "more"));
    for (const id of ids) {
      await p.evaluate((sid) => { if (sid === "mine") { window.BirgeShell.setSection("map"); window.CivicShell?.openMine?.(); } else window.BirgeShell.setSection(sid); }, id);
      await p.waitForTimeout(2600);
      merge(`${tag} ${id}`, await audit(p));
      await p.evaluate(() => window.BirgeShell.setSection("map")); await p.waitForTimeout(600);
    }
    if (mode === "resident") {
      const fab = await p.$(".bc-fab"); if (fab) { await fab.click().catch(() => {}); await p.waitForTimeout(1500); merge(`${tag} мастер`, await audit(p)); }
    }
    await ctx.close();
  }
  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify({ screens, total }, null, 1));
  const names = { offscale: "3 размер вне шкалы", weight: "3 вес не 400/500/600", long: "3 строка > 70 знаков", grid: "2 отступ не кратен 4 (справка)", shadow2: "6 тень в тени",
    motion: "7 движение > 300 мс", icon: "9 видимая толщина иконки вне 1,4–2,4 px", small: "10 зона < 44 px", unnamed: "10 кнопка без подписи" };
  for (const [b, title] of Object.entries(names)) {
    const rows = Object.entries(total[b] || {}).sort((a, c) => c[1].n - a[1].n);
    console.log(`\n== ${title}: ${rows.length} видов, ${rows.reduce((a, r) => a + r[1].n, 0)} элементов`);
    for (const [k, v] of rows.slice(0, 14)) console.log(`  ${v.n}× ${k} — «${v.ex}» [${v.screens.slice(0, 3).join(", ")}${v.screens.length > 3 ? ", …" : ""}]`);
  }
  console.log("\n== размеры шрифта по экранам");
  for (const [n, v] of Object.entries(screens)) console.log(`  ${n}: ${v.sizes.join(" / ")}`);
})();
