/*
 * R11 · защита от перегруза (POLISH_WAVE_2, п. 1, 2, 7): первый кадр карты не должен стать сложнее FINAL-кандидата.
 * Снимает «подпись» первого кадра акимата и жителя (1366×768 и 375×812, kk): пункты меню, плашки поверх карты,
 * пункты легенды, виды маркеров на карте. С эталоном (JSON прошлого прогона) — печатает отличия.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/first_frame_check.cjs http://127.0.0.1:8628/ <out.json> [эталон.json]
 * Эталон волны 2 — research/round-14-results/R11/first_frame_8e67c65.json (FINAL-кандидат R01 8e67c65).
 * Код выхода 1: в меню больше 5 пунктов раздела, на карте по умолчанию новая плашка или новый вид маркеров.
 */
"use strict";
const fs = require("fs");
const { chromium } = require("playwright");
const [BASE, OUT, BASELINE] = process.argv.slice(2);

async function frame(browser, mode, w, h) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const p = await ctx.newPage();
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.addInitScript((m) => { try { localStorage.setItem("birge.lang", "kk"); localStorage.setItem("birge.mode", m); } catch (e) {} }, mode);
  await p.goto(BASE);
  await p.waitForFunction(() => window.CivicShell && typeof mapReady !== "undefined" && mapReady && window.CivicShell.heat
    && window.CivicShell.heat.state && window.CivicShell.heat.state().status === "ready", null, { timeout: 45000 });
  await p.waitForTimeout(2500);
  const menuBtn = await p.$(".birge-menu-btn");
  if (menuBtn && (await menuBtn.isVisible())) { await menuBtn.click(); await p.waitForTimeout(400); }
  const r = await p.evaluate(() => {
    const vis = (e) => !!(e && e.getClientRects().length && getComputedStyle(e).visibility !== "hidden" && Number(getComputedStyle(e).opacity) > 0.05);
    const label = (e) => (e.id ? "#" + e.id : "") + ([...e.classList].length ? "." + [...e.classList].filter((c) => !/^(is-|bk-btn$)/.test(c)).slice(0, 2).join(".") : "");
    const header = document.querySelector("#birge-header") || document.querySelector("header");
    // Разделы меню: кнопки data-section и data-action (кроме языка и режима), видимые на ноутбуке или в открытом меню.
    const nav = header ? [...header.querySelectorAll("[data-section], [data-action]")].filter(vis).map((e) => e.textContent.trim().replace(/\s+/g, " ")) : [];
    const mapEl = document.getElementById("map"), map = mapEl.getBoundingClientRect();
    const over = new Set();
    for (const e of document.body.querySelectorAll("*")) {
      if (!vis(e) || e === mapEl) continue;
      const cs = getComputedStyle(e);
      if (cs.position !== "fixed" && cs.position !== "absolute") continue;
      if (e.closest(".maplibregl-canvas-container, .maplibregl-marker, .maplibregl-popup, #birge-header, header.topbar") && !e.matches("header.topbar")) continue;
      if (e.matches(".map-vignette, .maplibregl-canvas, .maplibregl-control-container")) continue;
      const q = e.getBoundingClientRect();
      if (q.width < 20 || q.height < 16) continue;
      if (q.right < map.left || q.left > map.right || q.bottom < map.top || q.top > map.bottom) continue;
      let anc = e.parentElement, nested = false; // только верхний уровень над картой
      while (anc && anc !== document.body && anc !== mapEl) {
        const c = getComputedStyle(anc);
        if ((c.position === "fixed" || c.position === "absolute") && vis(anc) && !anc.matches(".maplibregl-control-container")) { nested = true; break; }
        anc = anc.parentElement;
      }
      if (!nested) over.add(label(e));
    }
    for (const e of document.querySelectorAll(".maplibregl-ctrl-group, .maplibregl-ctrl-attrib, .r07-maplegend")) if (vis(e)) over.add(label(e));
    const legend = document.querySelector(".r07-maplegend");
    const legendItems = legend && vis(legend) ? [...legend.querySelectorAll("li, [class*='item']")].filter(vis).map((e) => e.textContent.trim()).filter(Boolean) : [];
    const markers = {};
    for (const e of document.querySelectorAll(".maplibregl-marker")) {
      if (!vis(e) || e.hidden) continue;
      const k = [...e.classList].find((c) => !c.startsWith("maplibregl")) || "marker";
      markers[k] = (markers[k] || 0) + 1;
    }
    const layers = [...document.querySelectorAll(".b3d-label")].filter(vis).length;
    return { nav, overlays: [...over].sort(), legend: legendItems, markers, b3dLabels: layers };
  });
  await ctx.close();
  return r;
}

(async () => {
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const res = {};
  for (const mode of ["akimat", "resident"]) for (const [w, h] of [[1366, 768], [375, 812]]) res[`${mode}-${w}`] = await frame(browser, mode, w, h);
  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify(res, null, 1));
  let bad = 0;
  const base = BASELINE && fs.existsSync(BASELINE) ? JSON.parse(fs.readFileSync(BASELINE, "utf8")) : null;
  for (const [k, r] of Object.entries(res)) {
    const lines = [];
    if (r.nav.length > 5) { bad++; lines.push(`меню: ${r.nav.length} пунктов (${r.nav.join(" · ")}) — больше 5 разделов`); }
    if (base && base[k]) {
      const b = base[k];
      const newOver = r.overlays.filter((x) => !b.overlays.includes(x));
      if (newOver.length) { bad++; lines.push("НОВОЕ ПОВЕРХ КАРТЫ: " + newOver.join(", ")); }
      const gone = b.overlays.filter((x) => !r.overlays.includes(x));
      if (gone.length) lines.push("пропало с карты: " + gone.join(", "));
      const newKinds = Object.keys(r.markers).filter((x) => !(x in b.markers));
      if (newKinds.length) { bad++; lines.push("НОВЫЙ ВИД МАРКЕРОВ ПО УМОЛЧАНИЮ: " + newKinds.map((x) => `${x} ×${r.markers[x]}`).join(", ")); }
      if (r.legend.length > b.legend.length) lines.push(`легенда: ${b.legend.length} → ${r.legend.length} пунктов (${r.legend.join(" · ")})`);
      if (r.nav.join("|") !== b.nav.join("|")) lines.push(`меню: ${b.nav.join(" · ")} → ${r.nav.join(" · ")}`);
    }
    console.log(`${k}: меню ${r.nav.length}, плашек над картой ${r.overlays.length}, легенда ${r.legend.length}, маркеры ${JSON.stringify(r.markers)}`
      + (lines.length ? "\n   " + lines.join("\n   ") : ""));
  }
  console.log(bad ? `ИТОГ: первый кадр стал сложнее — ${bad}` : base ? "ИТОГ: первый кадр как в эталоне" : "ИТОГ: эталон записан (сравнения не было)");
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
