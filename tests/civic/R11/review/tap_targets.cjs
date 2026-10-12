/*
 * R11 · зоны нажатия на первом кадре сборки (LOCAL_FINAL P3: «второстепенные кнопки 40–47 px, цель — 48»).
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/tap_targets.cjs http://127.0.0.1:<порт>/ <out.json>
 *   TAP_CSS=<файл.css> — подмешать CSS патча перед замером (проверка патча без пересборки)
 * Для 1366×768 и 375×812, ru/kk, «Акимат» и «Житель»: все видимые элементы управления (кнопки, ссылки, поля, summary,
 * role=button/tab/menuitem). Размер — рамка элемента; «зона» — с учётом расширения нажатия (::after и т. п.):
 * проверяем щелчком-зондом (elementFromPoint) на 4 px за верхним/нижним краем. Мелкие = зона < 48 по меньшей стороне.
 * Значки тепловой карты (маркеры MapLibre) — отдельной строкой: у них своя норма ≥ 24 px (UX_BRIEF).
 */
"use strict";
const { chromium } = require("playwright");
const fs = require("fs");
const BASE = process.argv[2] || "http://127.0.0.1:8721/";
const OUT = process.argv[3] || "tap_targets.json";

const ready = (page) => page.waitForFunction(() => window.CivicShell?.mode === "civic" && typeof mapReady !== "undefined" && mapReady
  && window.CivicShell.heat?.state?.().status === "ready", null, { timeout: 45000 }).then(() => page.waitForTimeout(1200));

async function scan(page) {
  return page.evaluate(() => {
    const SEL = "button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button], [role=tab], [role=menuitem], [role=switch]";
    const vis = (el) => {
      const b = el.getBoundingClientRect(), s = getComputedStyle(el);
      return b.width > 0 && b.height > 0 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0" &&
        b.bottom > 0 && b.top < innerHeight && b.right > 0 && b.left < innerWidth && !el.closest("[inert],[aria-hidden=true]");
    };
    const hits = (el, x, y) => { const h = document.elementFromPoint(x, y); return !!h && (h === el || el.contains(h)); };
    const label = (el) => (el.getAttribute("aria-label") || el.textContent || el.getAttribute("title") || el.className || el.tagName)
      .toString().replace(/\s+/g, " ").trim().slice(0, 40);
    const rows = [], markers = [];
    document.querySelectorAll(SEL).forEach((el) => {
      if (!vis(el)) return;
      const b = el.getBoundingClientRect();
      const cx = b.left + b.width / 2, cy = b.top + b.height / 2;
      if (!hits(el, cx, cy)) return;                       // закрыт другим элементом — не зона нажатия
      const marker = !!el.closest(".maplibregl-marker");
      // Расширение зоны: шаг 2 px наружу до 12 px (чего нет у рамки, но щелчок попадает в элемент)
      let up = 0, down = 0, left = 0, right = 0;
      for (let d = 2; d <= 12; d += 2) { if (hits(el, cx, b.top - d)) up = d; else break; }
      for (let d = 2; d <= 12; d += 2) { if (hits(el, cx, b.bottom + d - 0.5)) down = d; else break; }
      for (let d = 2; d <= 12; d += 2) { if (hits(el, b.left - d, cy)) left = d; else break; }
      for (let d = 2; d <= 12; d += 2) { if (hits(el, b.right + d - 0.5, cy)) right = d; else break; }
      const zone = [Math.round(b.width + left + right), Math.round(b.height + up + down)];
      const row = { label: label(el), cls: (el.className && el.className.baseVal === undefined ? el.className : "").toString().slice(0, 60),
        box: [Math.round(b.width), Math.round(b.height)], zone, at: [Math.round(b.left), Math.round(b.top)] };
      (marker ? markers : rows).push(row);
    });
    return { rows, small: rows.filter((r) => Math.min(...r.zone) < 47.5), markersSmall: markers.filter((r) => Math.min(...r.box) < 24).length,
      markers: markers.length };
  });
}

(async () => {
  const browser = await chromium.launch();
  const result = {};
  for (const [w, h] of [[1366, 768], [375, 812]]) {
    for (const lang of ["ru", "kk"]) {
      for (const role of ["akimat", "resident"]) {
        const ctx = await browser.newContext({ viewport: { width: w, height: h } });
        await ctx.addInitScript(([l, r]) => { try { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", r); } catch (e) {} }, [lang, role]);
        const page = await ctx.newPage();
        await page.goto(BASE + "?lang=" + lang, { waitUntil: "domcontentloaded" });
        await ready(page).catch(() => {});
        if (process.env.TAP_CSS) await page.addStyleTag({ content: fs.readFileSync(process.env.TAP_CSS, "utf8") }); // проверка патча
        const r = await scan(page);
        const key = `${w}-${lang}-${role}`;
        result[key] = r;
        console.log(`${key}: элементов ${r.rows.length}, зона < 48: ${r.small.length}` +
          (r.small.length ? " — " + r.small.map((x) => `${x.label} ${x.zone.join("×")}`).join("; ") : "") +
          ` · значков карты ${r.markers}, < 24 px: ${r.markersSmall}`);
        await ctx.close();
      }
    }
  }
  fs.writeFileSync(OUT, JSON.stringify(result, null, 1));
  await browser.close();
})();
