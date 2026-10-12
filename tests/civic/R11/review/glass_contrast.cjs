/*
 * R11 · замер контраста текста на стекле (GLASS.md) по настоящим пикселям экрана.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/glass_contrast.cjs <url> [<url> …]
 *   GLASS_SIZES=1366x768,375x812  GLASS_SHOTS=<папка> — сохранить кадры «стекло без текста»
 * Как: на странице находим стекло (.bk-glass, .bk-glass--control или любой видимый элемент с backdrop-filter),
 * прячем всё, кроме карты и самих стеклянных элементов (их содержимое тоже) — остаётся только фон стекла поверх карты;
 * снимаем каждый элемент, берём САМЫЙ ТЁМНЫЙ пиксель внутри (без 3 px края с тенью и рамкой) и считаем контраст
 * с цветом текста: ink (#152c26) для всех, вторичный текст стекла (--glass-text-2) — только для панелей.
 * Норма — ≥ 4.5:1. Для кнопок карты (.bk-glass--control) — только ink.
 */
"use strict";
const fs = require("fs"), path = require("path"), zlib = require("zlib");
const { chromium } = require("playwright");

// Минимальный разбор PNG (8 бит, RGB/RGBA, без чересстрочности) — без сторонних пакетов
function decodePng(buf) {
  let pos = 8, w = 0, h = 0, ct = 0;
  const idat = [];
  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos), type = buf.toString("ascii", pos + 4, pos + 8), data = buf.subarray(pos + 8, pos + 8 + len);
    if (type === "IHDR") { w = data.readUInt32BE(0); h = data.readUInt32BE(4); ct = data[9]; if (data[8] !== 8 || data[12] !== 0) throw new Error("PNG: нужен 8 бит без чересстрочности"); }
    else if (type === "IDAT") idat.push(data);
    else if (type === "IEND") break;
    pos += 12 + len;
  }
  const bpp = ct === 6 ? 4 : ct === 2 ? 3 : (() => { throw new Error("PNG: тип цвета " + ct); })();
  const raw = zlib.inflateSync(Buffer.concat(idat)), stride = w * bpp, out = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)], src = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1)), row = y * stride;
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? out[row + x - bpp] : 0, b = y ? out[row - stride + x] : 0, c = x >= bpp && y ? out[row - stride + x - bpp] : 0;
      let v = src[x];
      if (f === 1) v += a; else if (f === 2) v += b; else if (f === 3) v += (a + b) >> 1;
      else if (f === 4) { const p = a + b - c, pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c); v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c; }
      out[row + x] = v & 255;
    }
  }
  return { w, h, bpp, px: out };
}
const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
const lum = (r, g, b) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const ratio = (l1, l2) => (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
const INK = lum(...hex("#152c26")), TEXT2 = lum(...hex("#3f4a46")); // --glass-text-2 ui-kit
// Что считать картой (остаётся видимым под стеклом): сборка — #map/MapLibre, макеты R11 — .pm-map/.cl-map
const MAP = process.env.GLASS_MAP || "#map, .maplibregl-map, .pm-map, .cl-map";

(async () => {
  const urls = process.argv.slice(2);
  if (!urls.length) { console.log("укажите адрес страницы"); process.exit(2); }
  const sizes = (process.env.GLASS_SIZES || "1366x768,375x812").split(",").map((s) => s.split("x").map(Number));
  const browser = await chromium.launch();
  let worst = Infinity, bad = 0;
  for (const url of urls) for (const [w, h] of sizes) {
    const page = await browser.newPage({ viewport: { width: w, height: h } });
    await page.goto(url, { waitUntil: "networkidle" }).catch(() => {});
    await page.waitForTimeout(2500);
    const boxes = await page.evaluate(() => {
      const els = [...document.querySelectorAll("body *")].filter((e) => {
        const s = getComputedStyle(e), b = e.getBoundingClientRect();
        const glass = e.matches(".bk-glass, .bk-glass--control") || (s.backdropFilter && s.backdropFilter !== "none") || (s.webkitBackdropFilter && s.webkitBackdropFilter !== "none");
        return glass && b.width > 24 && b.height > 24 && s.visibility !== "hidden" && s.display !== "none" && b.bottom > 0 && b.top < innerHeight;
      });
      return els.map((e, i) => {
        e.setAttribute("data-r11-glass", String(i));
        const b = e.getBoundingClientRect();
        return { i, kind: e.matches(".bk-glass--control") ? "кнопка" : "панель", name: (e.id ? "#" + e.id : "") + "." + [...e.classList].slice(0, 2).join("."),
          r: Math.min(parseFloat(getComputedStyle(e).borderTopLeftRadius) || 0, Math.min(b.width, b.height) / 2),
          x: Math.max(0, b.left), y: Math.max(0, b.top), w: Math.min(b.width, innerWidth - Math.max(0, b.left)), h: Math.min(b.height, innerHeight - Math.max(0, b.top)) };
      });
    });
    // Остаётся только карта и фон стекла: всё прочее (поле поиска, кнопка «Сообщить о проблеме», тосты поверх стекла,
    // содержимое стекла) прячем — иначе самым тёмным «фоном» окажется чужой элемент над стеклом (R01 INTEGRATION 24.5).
    await page.addStyleTag({ content: [
      "body * { visibility: hidden !important; }",
      MAP.split(",").map((m) => `${m.trim()}, ${m.trim()} *`).join(", ") + " { visibility: visible !important; }",
      "[data-r11-glass] { visibility: visible !important; color: transparent !important; }",
      // содержимое стекла прячем и там, где стекло лежит внутри карты (#map * сильнее по специфичности — легенда R01)
      ["[data-r11-glass] *", ...MAP.split(",").map((m) => `${m.trim()} [data-r11-glass] *`)].join(", ") + " { visibility: hidden !important; }",
    ].join("\n") });
    await page.waitForTimeout(300);
    for (const b of boxes) {
      if (b.w < 12 || b.h < 12) continue;
      const shot = await page.screenshot({ clip: { x: b.x, y: b.y, width: b.w, height: b.h } });
      if (process.env.GLASS_SHOTS) { fs.mkdirSync(process.env.GLASS_SHOTS, { recursive: true }); fs.writeFileSync(path.join(process.env.GLASS_SHOTS, `glass-${w}-${b.i}.png`), shot); }
      const img = decodePng(shot), m = 3, R = Math.max(0, Math.min(b.r, Math.min(img.w, img.h) / 2));
      let min = 1;
      for (let y = m; y < img.h - m; y++) for (let x = m; x < img.w - m; x++) {
        // только внутри скруглённого прямоугольника (углы за скруглением — это карта мимо стекла) с отступом m
        const dx = Math.max(R - x, x - (img.w - 1 - R), 0), dy = Math.max(R - y, y - (img.h - 1 - R), 0);
        if (dx > 0 && dy > 0 && Math.hypot(dx, dy) > R - m) continue;
        const o = (y * img.w + x) * img.bpp, l = lum(img.px[o], img.px[o + 1], img.px[o + 2]);
        if (l < min) min = l;
      }
      const inkC = ratio(INK, min), t2C = ratio(TEXT2, min);
      const need = b.kind === "панель" ? Math.min(inkC, t2C) : inkC;
      worst = Math.min(worst, need);
      const ok = need >= 4.5;
      if (!ok) bad++;
      console.log(`${ok ? "PASS" : "FAIL"} ${w} ${b.kind} ${b.name} — самый тёмный фон L=${min.toFixed(3)}: ink ${inkC.toFixed(2)}${b.kind === "панель" ? `, вторичный ${t2C.toFixed(2)}` : ""}`);
    }
    await page.close();
  }
  await browser.close();
  console.log(`ИТОГ: худший контраст ${worst === Infinity ? "—" : worst.toFixed(2)} (норма 4.5), ниже нормы: ${bad}`);
  process.exit(bad ? 1 : 0);
})();
