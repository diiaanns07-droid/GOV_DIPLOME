// R10 · раунд 14 · общие проверки UX_BRIEF / UX_SPEC §8 для любого экрана (используют demo_flow.cjs и ux_screens.cjs).
"use strict";

// Шум среды: нет интернета для подложки, программный WebGL в headless Chromium.
const NOISE = /openfreemap|Failed to load resource|ERR_TUNNEL|AJAXError|GL Driver|GPU stall|style diff|swiftshader|GroupMarkerNotSet|WebGL/i;
// UX_BRIEF правило 4 + UX_SPEC §8: таких слов в интерфейсе быть не должно.
const TECH_WORDS = /(?<![\p{L}-])(ребро|рёбра|граф|графа|геометри\p{L}*|сценари\p{L}*|payload|demo-ring|target|null|undefined|NaN|editor|api|json|sqlite|\/(?:api|staff)\/[\w/.-]+)(?![\p{L}-])/iu;
// Ключ перевода, попавший на экран: «complaint.step2.title».
const RAW_KEY = /\b(shell|common|complaint|heat|akim|target|proposal|build3d|mine|status|stage|cat|district)\.[a-z_]+(\.[a-z_0-9]+)*\b/;
// Имена собственные и слова, одинаковые в ru и kk, — не считаются «непереведёнными».
const SAME_IN_BOTH = /^((Астана|Нура|Есиль|Алматы|Сарыарка|Байконур|Сарайшык|Birge|3D|Карта|РУС|ҚАЗ)( ·( \d+)?)?|[\d\s.,:%–—+-]+)$/i;  // «Алматы · 5» — подпись района с числом

// Правила UX_BRIEF для того, что сейчас на экране: прокрутка, ключи, тех. слова, шрифт, зоны нажатия.
function uiScreen(page) {
  return page.evaluate(({ tech, raw }) => {
    // Элемент виден человеку, только если сверху в его середине — он сам (или его часть): закрытое другой панелью
    // (например, карта под «Картиной дня») не считаем. Слои с pointer-events: none elementFromPoint пропускает.
    const onTop = (e) => { const r = e.getBoundingClientRect();
      const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1), y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
      const h = document.elementFromPoint(x, y); return !h || h === e || e.contains(h) || h.contains(e); };
    const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
      return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0"
        && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth && onTop(e); };
    const text = document.body.innerText;
    const small = [], tiny = [];
    for (const el of document.querySelectorAll("body *")) {
      // Строка лицензии «© OpenStreetMap contributors» — служебная подпись карты, правило 16/14 px к ней не относится.
      if (!vis(el) || el.children.length || !el.textContent.trim() || el.closest("svg, .maplibregl-ctrl-attrib") || /©/.test(el.textContent)) continue;
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs === 0) continue;  // текст спрятан намеренно (табличка-точка 3D-проекта на мелком масштабе)
      // Пороги — решение владельца 12 окт (R11 CLEAN_PASS §4, шкала 13/15/17): мелкий текст < 13 px, основной < 15 px.
      if (fs < 13) tiny.push(`${fs}px «${el.textContent.trim().slice(0, 30)}»`);
      else if (fs < 15) small.push(`${fs}px «${el.textContent.trim().slice(0, 30)}»`);
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
    // Текст, который ЧАСТИЧНО закрыт чужим элементом (одна панель наехала на другую, как B-039): у надписи есть видимые
    // и закрытые точки. Полностью закрытое (панель под «Картиной дня») и значки на карте не считаем.
    const onMapLayer = (e) => !!(e && e.closest && e.closest(".maplibregl-marker, .b3d-labels, .maplibregl-canvas-container, .maplibregl-ctrl-attrib"));
    const clipped = [];
    for (const el of document.querySelectorAll("body *")) {
      const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
      if (own.length < 3 || onMapLayer(el)) continue;
      if (el.closest("details:not([open])") && !el.closest("summary")) continue;  // содержимое свёрнутого <details> не рисуется
      const r = el.getBoundingClientRect(), st = getComputedStyle(el);
      if (r.width < 20 || r.height < 8 || st.visibility === "hidden" || st.opacity === "0" || r.top < 0 || r.bottom > innerHeight || r.left < 0 || r.right > innerWidth) continue;
      const y = r.top + r.height / 2, pts = [r.left + 3, r.left + r.width / 2, r.right - 3];
      let seen = 0, hidden = 0, by = null;
      for (const x of pts) {
        const h = document.elementFromPoint(x, y);
        if (!h || h === el || el.contains(h) || h.contains(el)) seen++;
        else if (!onMapLayer(h)) { hidden++; by = by || h; }
      }
      if (seen && hidden) clipped.push(`«${own.slice(0, 28)}» под «${(by.innerText || by.getAttribute("aria-label") || by.tagName).trim().replace(/\s+/g, " ").slice(0, 28)}»`);
    }
    // Короткая надпись, обрезанная многоточием (text-overflow: ellipsis): «Bir…» вместо «Birge» (B-042). Строки длиннее
    // 24 знаков (адрес, название места в списке) обрезать можно — это приём вёрстки, смысл виден в карточке.
    const cut = [];
    for (const el of document.querySelectorAll("body *")) {
      if (el.scrollWidth <= el.clientWidth + 1 || getComputedStyle(el).textOverflow !== "ellipsis" || !vis(el)) continue;
      const t = (el.textContent || "").trim().replace(/\s+/g, " ");
      if (t && t.length <= 24) cut.push(`«${t}» видно ${el.clientWidth} из ${el.scrollWidth} px`);
    }
    // Контраст текста ≥ 4.5:1 (UX_BRIEF правило 2; крупный текст ≥ 24 px или ≥ 18.66 px полужирный — 3:1, WCAG).
    // Фон — первый непрозрачный слой вверх по предкам (полупрозрачные смешиваются). Текст поверх карты (фона нет
    // до холста), картинки и градиенты, полупрозрачные предки и неактивные кнопки не оцениваем.
    const rgba = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
      return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; };
    const lum = (c) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
      return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
    const over = (top, bot) => { const a = top[3]; return [0, 1, 2].map((i) => top[i] * a + bot[i] * (1 - a)).concat(1); };
    const bgOf = (e) => {
      const layers = [];
      for (let n = e; n && n.nodeType === 1; n = n.parentElement) {
        const cs = getComputedStyle(n);
        if (Number(cs.opacity) < 0.99) return null;
        if (cs.backgroundImage && cs.backgroundImage !== "none") return null;
        if (n.classList.contains("maplibregl-map") || n.classList.contains("maplibregl-canvas-container")) return null;
        const c = rgba(cs.backgroundColor);
        if (c && c[3] > 0) { layers.push(c); if (c[3] >= 0.99) break; }
        if (n === document.documentElement && (!c || c[3] < 0.99)) layers.push([255, 255, 255, 1]);
      }
      if (!layers.length) return null;
      let col = layers[layers.length - 1]; if (col[3] < 0.99) col = over(col, [255, 255, 255, 1]);
      for (let i = layers.length - 2; i >= 0; i--) col = over(layers[i], col);
      return col;
    };
    const lowContrast = [];
    for (const el of document.querySelectorAll("body *")) {
      const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
      if (own.length < 2 || !vis(el) || el.closest("svg, .maplibregl-ctrl-attrib, [disabled], [aria-disabled=true]")) continue;
      const cs = getComputedStyle(el); const fg = rgba(cs.color); const bg = bgOf(el);
      if (!fg || !bg) continue;
      const f = fg[3] < 0.99 ? over(fg, bg) : fg;
      const L1 = lum(f), L2 = lum(bg), ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
      const fs = parseFloat(cs.fontSize), bold = Number(cs.fontWeight) >= 700;
      const need = fs >= 24 || (bold && fs >= 18.66) ? 3 : 4.5;
      if (ratio < need) lowContrast.push(`${ratio.toFixed(2)}:1 «${own.slice(0, 26)}» ${cs.color} на rgb(${bg.slice(0, 3).map(Math.round).join(",")})`);
    }
    return {
      lowContrast: lowContrast.slice(0, 6), lowContrastN: lowContrast.length,
      cut: cut.slice(0, 6), cutN: cut.length,
      clipped: clipped.slice(0, 6), clippedN: clipped.length,
      scrollW: document.documentElement.scrollWidth, innerW: innerWidth, lang: document.documentElement.lang,
      tech: (text.match(new RegExp(tech, "igu")) || []).slice(0, 8), raw: (text.match(new RegExp(raw, "g")) || []).slice(0, 8),
      tiny: tiny.slice(0, 8), tinyN: tiny.length, small: small.slice(0, 6), smallN: small.length,
      under40: targets.filter((t) => t.h < 40 || t.w < 40).slice(0, 8), under40N: targets.filter((t) => t.h < 40 || t.w < 40).length,
      under48N: targets.filter((t) => t.h < 48).length, targetsN: targets.length,
      mapBadges: mapBadges.length, mapBadgesUnder24: mapBadges.filter((h) => h < 24).length,
    };
  }, { tech: TECH_WORDS.source, raw: RAW_KEY.source });
}

// Строки экрана с кириллицей (для сравнения ru и kk): только текст, который человек видит, — элемент не скрыт,
// в пределах окна и не закрыт другой панелью (в середине элемента сверху он сам). Текст в прокручиваемой панели
// ниже видимой части тоже не считается — его покажет прокрутка (такие экраны проверяются отдельно).
async function cyrLines(page, opts = {}) {
  // opts.all — весь текст страницы, включая скрытое прокруткой панелей (то, до чего человек докрутит).
  if (opts.all) return (await page.evaluate(() => document.body.innerText)).split("\n").map((x) => x.trim()).filter((x) => /[а-яё]{3,}/i.test(x));
  return page.evaluate(() => {
    const out = [];
    for (const el of document.querySelectorAll("body *")) {
      const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(" ").replace(/\s+/g, " ").trim();
      if (!/[а-яё]{3,}/i.test(own)) continue;
      const r = el.getBoundingClientRect(), s = getComputedStyle(el);
      if (!(r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.opacity !== "0" && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth)) continue;
      // Видимая часть с учётом обрезки прокручиваемыми родителями (overflow).
      let top = Math.max(r.top, 0), bottom = Math.min(r.bottom, innerHeight);
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        const ps = getComputedStyle(p);
        if (/(auto|scroll|hidden)/.test(ps.overflowY)) { const pr = p.getBoundingClientRect(); top = Math.max(top, pr.top); bottom = Math.min(bottom, pr.bottom); }
      }
      if (bottom - top < 4) continue;
      const x = Math.min(Math.max(r.left + Math.min(r.width / 2, 20), 0), innerWidth - 1), y = (top + bottom) / 2;
      const h = document.elementFromPoint(x, y);
      if (h && h !== el && !el.contains(h) && !h.contains(el)) continue;
      out.push(own);
    }
    return out;
  });
}
// Строки kk-экрана, совпавшие со строками ru-экрана, — непереведённые.
function untranslated(kkLines, ruLines) {
  const ru = new Set(ruLines);
  return kkLines.filter((x) => ru.has(x) && !SAME_IN_BOTH.test(x));
}

// Клавиатура: Tab доходит до главной кнопки (.bk-btn--primary или текст), рамка фокуса видна.
// TAB_LIMIT — сколько нажатий Tab допустимо до главной кнопки; считаем до 80, чтобы в отчёте было точное число.
const TAB_LIMIT = 40;
async function focusToPrimary(page, labelRe, maxTabs = 80) {
  // Начать обход с самого начала документа (как после загрузки): фокус на body без следа клика.
  await page.evaluate(() => { const b = document.body; b.setAttribute("tabindex", "-1"); b.focus(); b.removeAttribute("tabindex");
    window.getSelection && window.getSelection().removeAllRanges(); }).catch(() => null);
  for (let i = 1; i <= maxTabs; i++) {
    await page.keyboard.press("Tab");
    // Ссылка «Перейти к главной кнопке» (ui-kit .bk-skip) в первых нажатиях: Enter должен привести фокус к главной кнопке.
    if (i <= 3) {
      const skip = await page.evaluate(() => { const e = document.activeElement;
        return !!e && (e.classList.contains("bk-skip") || /^(Перейти к главной кнопке|Негізгі түймеге өту)$/i.test((e.innerText || "").trim())); });
      if (skip) {
        await page.keyboard.press("Enter");
        await new Promise((ok) => setTimeout(ok, 400));
        const st = await page.evaluate((src) => {
          const e = document.activeElement; if (!e || e === document.body) return null;
          const s = getComputedStyle(e);
          const ring = (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) >= 2) || (s.boxShadow && s.boxShadow !== "none");
          const primary = e.classList.contains("bk-btn--primary") || (src && new RegExp(src, "i").test((e.innerText || e.getAttribute("aria-label") || "").trim()));
          return { primary, ring, text: (e.innerText || e.getAttribute("aria-label") || e.tagName).trim().slice(0, 40) };
        }, labelRe ? labelRe.source : null);
        if (st && st.primary) return { tabs: i, via: "skip-link + Enter", ...st };
      }
    }
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

// Сверка «FINAL-3 против эталона» (владелец, 12 окт): на каждом кадре сценария — шрифт < 13 px, зона нажатия < 44 px,
// контраст, ключи и заготовки вместо текста, обрезанный текст и список видимых строк (что пропало по сравнению с эталоном).
// Зона нажатия — не только рамка элемента: в 4 точках на 22 px от середины (влево, вправо, вверх, вниз) проверяем, что
// нажатие попадёт в него (так учитываются прозрачные поля и ::before у значков на карте). У флажка/переключателя — <label>.
const AUDIT_FONT_MIN = 13, AUDIT_TAP_MIN = 44;
function uiAudit(page) {
  return page.evaluate(({ raw, FONT, TAP }) => {
    const onTop = (e) => { const r = e.getBoundingClientRect();
      const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1), y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
      const h = document.elementFromPoint(x, y); return !h || h === e || e.contains(h) || h.contains(e); };
    const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
      return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0.05
        && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth && onTop(e); };
    const clean = (t) => String(t || "").replace(/\s+/g, " ").trim();
    const where = (e) => { const z = e.closest(".maplibregl-marker, .b3d-labels") ? "карта" : e.closest(".maplibregl-ctrl") ? "кнопки карты"
      : e.closest("[role=dialog], dialog, .bk-sheet, .bc-panel, .r07-card, aside") ? "панель" : e.closest("header, nav, .birge-nav, .bk-topbar") ? "шапка" : "экран";
      return z; };
    // innerText пуст, пока блок разворачивается (переход высоты), — тогда имя по textContent.
    const nameOf = (e) => clean(e.getAttribute("aria-label") || e.innerText || e.textContent || e.getAttribute("title") || e.value || "").slice(0, 40);
    // 1. Шрифт
    const fonts = [];
    for (const el of document.querySelectorAll("body *")) {
      const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
      if (!own || el.closest("svg, .maplibregl-ctrl-attrib") || /©/.test(own) || !vis(el)) continue;
      const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs > 0 && fs < FONT) fonts.push({ px: fs, text: clean(own).slice(0, 40), where: where(el) });
    }
    // 2. Зоны нажатия
    const sel = "button, a[href], [role=button], [role=tab], [role=menuitem], [role=radio], [role=checkbox], [role=switch], [role=option], input:not([type=hidden]), select, summary, textarea";
    const seen = new Set(), taps = [];
    let tapsN = 0;
    for (let e of document.querySelectorAll(sel)) {
      if (/^(checkbox|radio)$/.test(e.type || "") && (e.closest("label") || (e.id && document.querySelector(`label[for="${e.id}"]`)))) e = e.closest("label") || document.querySelector(`label[for="${e.id}"]`);
      if (seen.has(e) || !vis(e)) continue;
      seen.add(e); tapsN++;
      const r = e.getBoundingClientRect();
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2, d = TAP / 2 - 0.5;
      const hit = (x, y) => { if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return false; const h = document.elementFromPoint(x, y); return !!h && (h === e || e.contains(h)); };
      const wOk = r.width >= TAP || (hit(cx - d, cy) && hit(cx + d, cy));
      const hOk = r.height >= TAP || (hit(cx, cy - d) && hit(cx, cy + d));
      if (wOk && hOk) continue;
      // Ссылка внутри строки текста — исключение WCAG 2.5.8 (inline): отмечаем, но не как кнопку.
      const inline = e.tagName === "A" && getComputedStyle(e).display === "inline" && clean(e.parentElement && e.parentElement.innerText).length > clean(e.innerText).length + 10;
      taps.push({ w: Math.round(r.width), h: Math.round(r.height), name: nameOf(e) || e.tagName.toLowerCase(), where: where(e),
        vendor: !!e.closest(".maplibregl-ctrl-attrib, .maplibregl-ctrl-logo"), inline });
    }
    // 3. Контраст (та же формула, что в uiScreen: фон — первый непрозрачный слой вверх по предкам)
    const rgba = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
      return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; };
    const lum = (c) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
      return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
    const over = (top, bot) => { const a = top[3]; return [0, 1, 2].map((i) => top[i] * a + bot[i] * (1 - a)).concat(1); };
    const bgOf = (e) => { const layers = [];
      for (let n = e; n && n.nodeType === 1; n = n.parentElement) { const cs = getComputedStyle(n);
        if (Number(cs.opacity) < 0.99 || (cs.backgroundImage && cs.backgroundImage !== "none")) return null;
        if (n.classList.contains("maplibregl-map") || n.classList.contains("maplibregl-canvas-container")) return null;
        const c = rgba(cs.backgroundColor); if (c && c[3] > 0) { layers.push(c); if (c[3] >= 0.99) break; }
        if (n === document.documentElement && (!c || c[3] < 0.99)) layers.push([255, 255, 255, 1]); }
      if (!layers.length) return null;
      let col = layers[layers.length - 1]; if (col[3] < 0.99) col = over(col, [255, 255, 255, 1]);
      for (let i = layers.length - 2; i >= 0; i--) col = over(layers[i], col); return col; };
    const contrast = [];
    for (const el of document.querySelectorAll("body *")) {
      const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
      if (own.length < 2 || el.closest("svg, .maplibregl-ctrl-attrib, [disabled], [aria-disabled=true]") || !vis(el)) continue;
      const cs = getComputedStyle(el); const fg = rgba(cs.color); const bg = bgOf(el); if (!fg || !bg) continue;
      const f = fg[3] < 0.99 ? over(fg, bg) : fg; const L1 = lum(f), L2 = lum(bg), ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
      const fs = parseFloat(cs.fontSize), bold = Number(cs.fontWeight) >= 700, need = fs >= 24 || (bold && fs >= 18.66) ? 3 : 4.5;
      if (ratio < need) contrast.push({ ratio: Math.round(ratio * 100) / 100, need, text: clean(own).slice(0, 36), where: where(el) });
    }
    // 4. Тексты: видимые строки; ключи перевода и заготовки вместо текста; кнопки без имени; обрезанное многоточием
    const lines = new Set();
    for (const el of document.querySelectorAll("body *")) {
      const own = clean([...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(" "));
      if (own.length < 2 || el.closest("script, style, svg") || !vis(el)) continue;
      lines.add(own.slice(0, 80));
    }
    const all = [...lines];
    const keys = all.filter((t) => new RegExp(raw).test(t)).slice(0, 10);
    const junk = all.filter((t) => /\{[a-z_]+\}|\bundefined\b|\bNaN\b|\[object Object\]|\bnull\b/.test(t)).slice(0, 10);
    // Кнопка без подписи: разметка и текст вокруг — чтобы владелец нашёл её без повторного прогона.
    const noName = [...seen].filter((e) => !nameOf(e) && !e.querySelector("img[alt]:not([alt=''])"))
      .map((e) => `${e.tagName.toLowerCase()}.${String(e.className || "").trim().replace(/\s+/g, ".")} в «${clean(e.parentElement && e.parentElement.innerText).slice(0, 40)}» ${e.outerHTML.slice(0, 120)}`).slice(0, 10);
    const cut = [];
    for (const el of document.querySelectorAll("body *")) {
      if (el.scrollWidth <= el.clientWidth + 1 || getComputedStyle(el).textOverflow !== "ellipsis" || !vis(el)) continue;
      const t = clean(el.textContent); if (t && t.length <= 24) cut.push(t);
    }
    return { w: innerWidth, h: innerHeight, fonts, taps, tapsN, contrast, keys, junk, noName, cut, texts: all.slice(0, 600) };
  }, { raw: RAW_KEY.source, FONT: AUDIT_FONT_MIN, TAP: AUDIT_TAP_MIN });
}

module.exports = { NOISE, TECH_WORDS, RAW_KEY, SAME_IN_BOTH, TAB_LIMIT, AUDIT_FONT_MIN, AUDIT_TAP_MIN, uiScreen, uiAudit, cyrLines, untranslated, focusToPrimary };
