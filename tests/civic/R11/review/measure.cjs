/*
 * R11 · общие замеры для UX-разбора экранов ролей (используют r07/r08/r06/r05 *_shots.cjs).
 * measure(page, rootSelector) → { scroll, small, low, keys, tech, demo, clipped, lang }
 *   small  — видимый текст < 14 px (UX_BRIEF: основной 16, мета 14)
 *   low    — кнопки/ссылки-кнопки ниже 44 px (чипы 40 + зона 48 считаются отдельно, порог 39.5)
 *   keys   — «сырые» ключи вида heat.card.title на экране
 *   tech   — технические слова (UX_BRIEF, правило 4)
 *   demo   — слово «демо/demo» в видимом тексте (должно быть «Пример / Үлгі»)
 *   clipped— текст обрезан многоточием/overflow (часто казахский)
 */
"use strict";

async function measure(page, rootSelector) {
  return page.evaluate((sel) => {
    const root = sel ? document.querySelector(sel) || document.body : document.body;
    const vis = (el) => {
      const b = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return b.width > 0 && b.height > 0 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0" &&
        b.bottom > 0 && b.top < innerHeight && b.right > 0 && b.left < innerWidth;
    };
    const out = { small: {}, low: [], keys: [], tech: [], demo: [], clipped: [] };
    out.scroll = document.documentElement.scrollWidth - innerWidth;
    out.lang = document.documentElement.lang;
    const TECH = /\b(ребр|граф(?!ик)|геометри|сценари|payload|demo-ring|undefined|null|NaN|segment|target|osm-w\d|osm-node)/i;
    root.querySelectorAll("*").forEach((el) => {
      if (!vis(el) || el.closest("svg,code,script,style,.maplibregl-ctrl-attrib")) return;
      const own = Array.from(el.childNodes).filter((c) => c.nodeType === 3).map((c) => c.textContent).join("").trim();
      const cs = getComputedStyle(el);
      if (own) {
        const fs = parseFloat(cs.fontSize);
        if (fs < 13.9) { const k = Math.round(fs * 2) / 2 + "px"; (out.small[k] = out.small[k] || []).push(own.slice(0, 32)); }
        if (/^[a-z0-9_]+(\.[a-z0-9_]+){1,}$/.test(own)) out.keys.push(own);
        const m = own.match(TECH); if (m) out.tech.push(m[0] + " «" + own.slice(0, 40) + "»");
        if (/(^|[^а-яёa-z])(демо|demo)/i.test(own)) out.demo.push(own.slice(0, 50));
        if ((cs.textOverflow === "ellipsis" || cs.webkitLineClamp !== "none") && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)) out.clipped.push(own.slice(0, 40));
      }
      ["aria-label", "title", "placeholder"].forEach((a) => {
        const v = el.getAttribute(a);
        if (v && /^[a-z0-9_]+(\.[a-z0-9_]+){1,}$/.test(v)) out.keys.push(a + "=" + v);
      });
      if (el.matches("button, [role=button], a.bk-btn, select, input[type=checkbox], input[type=radio]")) {
        const b = el.getBoundingClientRect();
        if (b.height < 39.5 || (b.height < 43.5 && !el.matches(".bk-chip, [class*=chip], .bk-seg > button"))) {
          out.low.push(Math.round(b.width) + "×" + Math.round(b.height) + " «" + (el.innerText || el.getAttribute("aria-label") || el.className || "").trim().slice(0, 28) + "»");
        }
      }
    });
    for (const k of Object.keys(out.small)) out.small[k] = [...new Set(out.small[k])].slice(0, 8);
    ["low", "keys", "tech", "demo", "clipped"].forEach((k) => (out[k] = [...new Set(out[k])].slice(0, 15)));
    return out;
  }, rootSelector);
}

// Краткая строка для отчёта
function brief(m) {
  const bits = [];
  if (m.scroll > 0) bits.push("прокрутка вбок " + m.scroll + "px");
  const smallN = Object.values(m.small).reduce((s, a) => s + a.length, 0);
  if (smallN) bits.push("мелкий текст: " + Object.entries(m.small).map(([k, v]) => k + "×" + v.length).join(", "));
  if (m.low.length) bits.push("низкие кнопки: " + m.low.length);
  if (m.keys.length) bits.push("КЛЮЧИ: " + m.keys.join(", "));
  if (m.tech.length) bits.push("тех. слова: " + m.tech.length);
  if (m.demo.length) bits.push("«демо»: " + m.demo.length);
  if (m.clipped.length) bits.push("обрезано: " + m.clipped.length);
  return bits.join(" · ") || "чисто";
}

function consoleCollector(page) {
  const logs = [];
  page.on("console", (m) => {
    const t = m.text();
    if (/GroupMarkerNotSet|GPU stall|swiftshader|WebGL-0x|software WebGL/i.test(t)) return; // шум программного WebGL
    if (m.type() === "error" || m.type() === "warning") logs.push(m.type() + ": " + t.slice(0, 200));
  });
  page.on("pageerror", (e) => logs.push("pageerror: " + String(e.message).slice(0, 200)));
  return logs;
}

module.exports = { measure, brief, consoleCollector };
