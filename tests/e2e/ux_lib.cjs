// R10 · раунд 14 · общие проверки UX_BRIEF / UX_SPEC §8 для любого экрана (используют demo_flow.cjs и ux_screens.cjs).
"use strict";

// Шум среды: нет интернета для подложки, программный WebGL в headless Chromium.
const NOISE = /openfreemap|Failed to load resource|ERR_TUNNEL|AJAXError|GL Driver|GPU stall|style diff|swiftshader|GroupMarkerNotSet|WebGL/i;
// UX_BRIEF правило 4 + UX_SPEC §8: таких слов в интерфейсе быть не должно.
const TECH_WORDS = /(?<![\p{L}-])(ребро|рёбра|граф|графа|геометри\p{L}*|сценари\p{L}*|payload|demo-ring|target|null|undefined|NaN|editor|api|json|sqlite|\/(?:api|staff)\/[\w/.-]+)(?![\p{L}-])/iu;
// Ключ перевода, попавший на экран: «complaint.step2.title».
const RAW_KEY = /\b(shell|common|complaint|heat|akim|target|proposal|build3d|mine|status|stage|cat|district)\.[a-z_]+(\.[a-z_0-9]+)*\b/;
// Имена собственные и слова, одинаковые в ru и kk, — не считаются «непереведёнными».
const SAME_IN_BOTH = /^(Астана|Нура|Есиль|Алматы|Сарыарка|Байконур|Сарайшык|Birge|3D|Карта|РУС|ҚАЗ|[\d\s.,:%–—+-]+)$/i;

// Правила UX_BRIEF для того, что сейчас на экране: прокрутка, ключи, тех. слова, шрифт, зоны нажатия.
function uiScreen(page) {
  return page.evaluate(({ tech, raw }) => {
    const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
      return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0"
        && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; };
    const text = document.body.innerText;
    const small = [], tiny = [];
    for (const el of document.querySelectorAll("body *")) {
      // Строка лицензии «© OpenStreetMap contributors» — служебная подпись карты, правило 16/14 px к ней не относится.
      if (!vis(el) || el.children.length || !el.textContent.trim() || el.closest("svg, .maplibregl-ctrl-attrib") || /©/.test(el.textContent)) continue;
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs === 0) continue;  // текст спрятан намеренно (табличка-точка 3D-проекта на мелком масштабе)
      if (fs < 14) tiny.push(`${fs}px «${el.textContent.trim().slice(0, 30)}»`);
      else if (fs < 16) small.push(`${fs}px «${el.textContent.trim().slice(0, 30)}»`);
    }
    // Значки и таблички НА КАРТЕ (маркеры MapLibre, подписи 3D-проектов) UX_SPEC §5 разрешает 24–36 px — их считаем отдельно.
    const onMap = (e) => !!e.closest(".maplibregl-marker, .b3d-labels");
    const all = [...document.querySelectorAll("button, a[href], [role=button], input, select, summary, textarea")].filter(vis)
      .filter((e) => !e.closest(".maplibregl-ctrl-attrib"));
    const mapBadges = all.filter(onMap).map((e) => Math.round(e.getBoundingClientRect().height));
    const targets = all.filter((e) => !onMap(e))
      .map((e) => {
        // У флажка зона нажатия — вся подпись <label>, а не 18-пиксельный квадрат.
        const box = (/^(checkbox|radio)$/.test(e.type) && e.closest("label")) || e;
        const r = box.getBoundingClientRect();
        return { h: Math.round(r.height), w: Math.round(r.width), t: (box.innerText || e.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 24) };
      });
    return {
      scrollW: document.documentElement.scrollWidth, innerW: innerWidth, lang: document.documentElement.lang,
      tech: (text.match(new RegExp(tech, "igu")) || []).slice(0, 8), raw: (text.match(new RegExp(raw, "g")) || []).slice(0, 8),
      tiny: tiny.slice(0, 8), tinyN: tiny.length, small: small.slice(0, 6), smallN: small.length,
      under40: targets.filter((t) => t.h < 40 || t.w < 40).slice(0, 8), under40N: targets.filter((t) => t.h < 40 || t.w < 40).length,
      under48N: targets.filter((t) => t.h < 48).length, targetsN: targets.length,
      mapBadges: mapBadges.length, mapBadgesUnder24: mapBadges.filter((h) => h < 24).length,
    };
  }, { tech: TECH_WORDS.source, raw: RAW_KEY.source });
}

// Строки экрана с кириллицей (для сравнения ru и kk).
async function cyrLines(page) {
  return (await page.evaluate(() => document.body.innerText)).split("\n").map((x) => x.trim()).filter((x) => /[а-яё]{3,}/i.test(x));
}
// Строки kk-экрана, совпавшие со строками ru-экрана, — непереведённые.
function untranslated(kkLines, ruLines) {
  const ru = new Set(ruLines);
  return kkLines.filter((x) => ru.has(x) && !SAME_IN_BOTH.test(x));
}

// Клавиатура: Tab доходит до главной кнопки (.bk-btn--primary или текст), рамка фокуса видна.
async function focusToPrimary(page, labelRe, maxTabs = 40) {
  await page.mouse.click(2, 2).catch(() => null);
  for (let i = 1; i <= maxTabs; i++) {
    await page.keyboard.press("Tab");
    const st = await page.evaluate((src) => {
      const e = document.activeElement; if (!e || e === document.body) return null;
      const re = src ? new RegExp(src, "i") : null;
      const s = getComputedStyle(e);
      const ring = (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) >= 2) || (s.boxShadow && s.boxShadow !== "none");
      const primary = e.classList.contains("bk-btn--primary") || (re && re.test((e.innerText || e.getAttribute("aria-label") || "").trim()));
      return { primary, ring, text: (e.innerText || e.getAttribute("aria-label") || e.tagName).trim().slice(0, 40) };
    }, labelRe ? labelRe.source : null);
    if (st && st.primary) return { tabs: i, ...st };
  }
  return { tabs: null, primary: false, ring: false };
}

module.exports = { NOISE, TECH_WORDS, RAW_KEY, SAME_IN_BOTH, uiScreen, cyrLines, untranslated, focusToPrimary };
