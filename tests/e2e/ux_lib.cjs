// R10 · раунд 14 · общие проверки UX_BRIEF / UX_SPEC §8 для любого экрана (используют demo_flow.cjs и ux_screens.cjs).
"use strict";

// Шум среды: нет интернета для подложки, программный WebGL в headless Chromium.
const NOISE = /openfreemap|Failed to load resource|ERR_TUNNEL|AJAXError|GL Driver|GPU stall|style diff|swiftshader|GroupMarkerNotSet|WebGL/i;
// UX_BRIEF правило 4 + UX_SPEC §8: таких слов в интерфейсе быть не должно.
const TECH_WORDS = /(?<![\p{L}-])(ребро|рёбра|граф|графа|геометри\p{L}*|сценари\p{L}*|payload|demo-ring|target|null|undefined|NaN|editor|api|json|sqlite|\/(?:api|staff)\/[\w/.-]+)(?![\p{L}-])/iu;
// Ключ перевода, попавший на экран: «complaint.step2.title».
// Раунд 15: и ключи новых модулей (R16 together/yard, R17 agencies/crisis, R12 works, R13 meetings, R03 analyst, R06 notify,
// R07 replay, R08 board).
const RAW_KEY = /\b(shell|common|complaint|heat|akim|target|proposal|build3d|mine|status|stage|cat|district|together|yard|initiative|agencies|agency|crisis|incident|works|calendar|meetings|meeting|analyst|assistant|notify|notifications|replay|board|ideas|idea)\.[a-z_]+(\.[a-z_0-9]+)*\b/;
// Имена собственные и слова, одинаковые в ru и kk, — не считаются «непереведёнными».
// «Алматы · 5» — подпись района с числом; пробел может быть неразрывным (R07 13 окт: «Алматы\u00a0·»).
const SAME_IN_BOTH = /^((Астана|Нура|Есиль|Алматы|Сарыарка|Байконур|Сарайшык|Birge|3D|Карта|РУС|ҚАЗ)(\s*·(\s*\d+)?)?|[\d\s.,:%–—+-]+)$/i;

// Правила UX_BRIEF для того, что сейчас на экране: прокрутка, ключи, тех. слова, шрифт, зоны нажатия.
function uiScreen(page) {
  return page.evaluate(({ tech, raw }) => {
    // Элемент виден человеку, только если сверху в его середине — он сам (или его часть): закрытое другой панелью
    // (например, карта под «Картиной дня») не считаем. Слои с pointer-events: none elementFromPoint пропускает.
    const onTop = (e) => { const r = e.getBoundingClientRect();
      const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1), y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
      const h = document.elementFromPoint(x, y); return !h || h === e || e.contains(h) || h.contains(e); };
    // Текст только для экранного диктора (.bk-sr-only R11 и подобные: 1×1 px, clip) человек не видит — не оцениваем.
    const srOnly = (e) => { const r = e.getBoundingClientRect(); if (r.width <= 1 || r.height <= 1) return true;
      for (let n = e; n && n.nodeType === 1; n = n.parentElement) {
        if (n.classList && (n.classList.contains("bk-sr-only") || n.classList.contains("sr-only") || n.classList.contains("visually-hidden"))) return true;
        const cs = getComputedStyle(n);
        if (cs.clip === "rect(0px, 0px, 0px, 0px)" || /inset\(50%\)/.test(cs.clipPath || "")) return true;
      }
      return false; };
    const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
      return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0"
        && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth && onTop(e) && !srOnly(e); };
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
    // Зона нажатия — рамка плюс то, что ловит нажатие вокруг неё: ui-kit R11 расширяет мелкие кнопки псевдоэлементом
    // (.bk-chip 34 px и .bk-join 32 px — ::after «inset: -5 / -6px 0» → 44 px; .bk-seg, .bk-x, .bk-vote), роли — прозрачной
    // рамкой. Точки за краем рамки, которые elementFromPoint отдаёт той же кнопке, — её зона (до 12 px с каждой стороны).
    // До 16 окт мерилась только рамка — «Я приду» 32 px и «▶ Хроника» 34 px были ложными FAIL (BUGS B-114, B-125).
    const hitBox = (box) => {
      const r = box.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      // За краем экрана elementFromPoint ничего не видит — там берём зону, заявленную псевдоэлементом (::after «inset: -6px 0»).
      const own = (x, y) => { if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return "out";
        const h = document.elementFromPoint(x, y); return !!h && (h === box || box.contains(h)); };
      const declared = (side) => { let best = 0;
        for (const pe of ["::before", "::after"]) { const cs = getComputedStyle(box, pe);
          if (cs.content === "none" || cs.position !== "absolute" || cs.pointerEvents === "none") continue;
          const v = parseFloat(cs[side]); if (Number.isFinite(v) && v < 0) best = Math.max(best, -v); }
        return Math.min(best, 12); };
      const grow = (f, side) => { let k = 0; while (k < 12) { const o = f(k + 1); if (o === "out") return Math.max(k, declared(side)); if (!o) break; k++; } return k; };
      const dh = grow((k) => own(cx, r.top - k), "top") + grow((k) => own(cx, r.bottom - 1 + k), "bottom");
      const dw = grow((k) => own(r.left - k, cy), "left") + grow((k) => own(r.right - 1 + k, cy), "right");
      return { h: Math.round(r.height + dh), w: Math.round(r.width + dw), ...(dh || dw ? { frame: `${Math.round(r.width)}×${Math.round(r.height)}` } : {}) };
    };
    const targets = all.filter((e) => !onMap(e))
      .map((e) => {
        // У флажка зона нажатия — вся подпись <label>, а не 18-пиксельный квадрат.
        const box = (/^(checkbox|radio)$/.test(e.type) && e.closest("label")) || e;
        return { ...hitBox(box), t: (box.innerText || e.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 24) };
      });
    // Текст, который ЧАСТИЧНО закрыт чужим элементом (одна панель наехала на другую, как B-039): у надписи есть видимые
    // и закрытые точки. Полностью закрытое (панель под «Картиной дня») и значки на карте не считаем.
    const onMapLayer = (e) => !!(e && e.closest && e.closest(".maplibregl-marker, .b3d-labels, .maplibregl-canvas-container, .maplibregl-ctrl-attrib"));
    const clipped = [];
    // Прозрачная зона нажатия (поля ссылки или кнопки, расширенные до 44 px): поверх соседнего текста ничего не рисует —
    // не «закрывает», если в этой точке нет её собственного текста (R13 «Картада» под строкой времени, ложный FAIL).
    const clearAt = (h, x, y) => {
      const cs = getComputedStyle(h);
      const clear = /^(transparent|rgba\(0, 0, 0, 0\))$/.test(cs.backgroundColor) && cs.backgroundImage === "none" && cs.boxShadow === "none"
        && !parseFloat(cs.borderTopWidth) && !parseFloat(cs.borderBottomWidth) && (!cs.backdropFilter || cs.backdropFilter === "none");
      if (!clear) return false;
      const rg = document.createRange(); rg.selectNodeContents(h);
      return ![...rg.getClientRects()].some((q) => x >= q.left && x <= q.right && y >= q.top && y <= q.bottom);
    };
    for (const el of document.querySelectorAll("body *")) {
      const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
      if (own.length < 3 || onMapLayer(el)) continue;
      if (el.closest("details:not([open])") && !el.closest("summary")) continue;  // содержимое свёрнутого <details> не рисуется
      const r = el.getBoundingClientRect(), st = getComputedStyle(el);
      if (r.width < 20 || r.height < 8 || st.visibility === "hidden" || st.opacity === "0" || r.top < 0 || r.bottom > innerHeight || r.left < 0 || r.right > innerWidth) continue;
      // Точки — по строкам самого текста (Range), не по коробке элемента: у ячейки в две строки середина коробки может
      // прийтись на пустую вторую строку под плашкой («қаз» и «бүгін» в календаре R12 — ложный FAIL).
      const lines = [];
      for (const tn of el.childNodes) {
        if (tn.nodeType !== 3 || !tn.textContent.trim()) continue;
        const rg = document.createRange(); rg.selectNodeContents(tn);
        for (const q of rg.getClientRects()) if (q.width > 2 && q.height > 2) lines.push(q);
      }
      const pts = (lines.length ? lines.slice(0, 3) : [r]).flatMap((q) => {
        const y = q.top + q.height / 2;
        return [[q.left + 2, y], [q.left + q.width / 2, y], [q.right - 2, y]];
      });
      // Прокрутка — не наложение: часть строки ушла за край своего прокручиваемого контейнера или под его липкую шапку
      // (position: sticky) — R12 «Қабанбай Батыр даңғылы» под углом шапки шкалы календаря на B0.20, ложный FAIL.
      let clip = { left: 0, top: 0, right: innerWidth, bottom: innerHeight }, sc = null;
      for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) {
        const cs = getComputedStyle(n);
        if (cs.overflowX === "visible" && cs.overflowY === "visible") continue;
        const q = n.getBoundingClientRect();
        clip = { left: Math.max(clip.left, q.left), top: Math.max(clip.top, q.top), right: Math.min(clip.right, q.right), bottom: Math.min(clip.bottom, q.bottom) };
        if (!sc && /(auto|scroll)/.test(cs.overflowX + " " + cs.overflowY)) sc = n;
      }
      const inClip = ([x, y]) => x >= clip.left && x <= clip.right && y >= clip.top && y <= clip.bottom;
      const stickyIn = (h) => { if (!sc || !sc.contains(h)) return false;
        for (let n = h; n && n !== sc; n = n.parentElement) if (getComputedStyle(n).position === "sticky") return true; return false; };
      let seen = 0, hidden = 0, by = null;
      for (const [x, y] of pts.filter(inClip)) {
        const h = document.elementFromPoint(x, y);
        if (!h || h === el || el.contains(h) || h.contains(el) || clearAt(h, x, y)) seen++;
        else if (!onMapLayer(h) && !stickyIn(h)) { hidden++; by = by || h; }
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
// нажатие попадёт в него (так учитываются прозрачные поля и ::before у значков на карте), а если нет — меряем фактическую
// протяжённость зоны по оси (13 окт: несимметричное поле ::after, напр. вкладки R07). У флажка/переключателя — <label>.
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
      // Фактическая зона по оси: от середины в обе стороны (шаг 2 px), пока нажатие попадает в элемент. Так считается и
      // несимметричная зона ::after (например, вкладка 30 px с полем 14 px сверху — 44 px), а не только ±22 px от центра.
      const span = (dx, dy) => { let a = 0, b = 0; while (a < TAP && hit(cx - dx * (a + 2), cy - dy * (a + 2))) a += 2; while (a + b < TAP && hit(cx + dx * (b + 2), cy + dy * (b + 2))) b += 2; return a + b + 1; };
      const wOk = r.width >= TAP || (hit(cx - d, cy) && hit(cx + d, cy)) || span(1, 0) >= TAP - 1;
      const hOk = r.height >= TAP || (hit(cx, cy - d) && hit(cx, cy + d)) || span(0, 1) >= TAP - 1;
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

// П3 (AMENDMENTS 16 окт, кадры research/round-15-results/R14/review_final51/): то, что координатор увидел глазами жюри.
// Лист раздела (корень sel): 1) над липкой плашкой группы при прокрутке не видны строки списка, в начале плашка не наезжает
// на строку (кадр 05, «Новые 21»); 2) кнопка действия не обрезана краем листа — в начальном виде (WARN) и даже в конце
// прокрутки (FAIL; кадр 07, «+ Открыть кризисный штаб»); 3) лист не шире содержимого — без пустых полей слева и справа
// на ширине ≥ 1200 (кадр 05; задача R01); 4) нет серого квадрата с крошечным значком — «пропавшей картинки» (кадр 04, П1).
function sheetMetrics(page, sel) {
  return page.evaluate(async (s) => {
    const root = document.querySelector(s);
    if (!root) return null;
    const frame = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    const vis = (e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
      return r.width > 1 && r.height > 1 && cs.visibility !== "hidden" && cs.display !== "none" && cs.opacity !== "0"; };
    const clean = (t) => String(t || "").trim().replace(/\s+/g, " ");
    const scroller = (e) => { for (let n = e.parentElement; n && n !== document.body; n = n.parentElement) {
      const cs = getComputedStyle(n); if (/(auto|scroll)/.test(cs.overflowY) && n.scrollHeight > n.clientHeight + 4) return n; } return null; };
    const out = { stickyPeek: [], stickyOver: [], cutEnd: [], cutNow: [], margins: null, placeholder: [] };
    // 1. Липкие плашки
    // Липкие сверху (top задан); липкая снизу панель «Сохранить» (top: auto) — не плашка группы.
    const stickies = [...root.querySelectorAll("*")].filter((e) => { const cs = getComputedStyle(e);
      return cs.position === "sticky" && cs.top !== "auto" && vis(e); }).slice(0, 8);
    for (const st of stickies) {
      const sc = scroller(st);
      if (!sc) continue;
      const label = clean(st.innerText).slice(0, 30);
      const keep = sc.scrollTop;
      const r0 = st.getBoundingClientRect();
      // Плашка группы — во всю ширину листа и с заливкой; узкий чип или прозрачная полоса с плавающим заголовком
      // («Картина дня · 16 окт», R08 .akim__bar) — приём вида: строки под ним и вокруг видны по замыслу.
      const scs = getComputedStyle(st), bgA = scs.backgroundColor.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
      const filled = (bgA && (bgA[4] === undefined || +bgA[4] >= 0.1)) || (scs.backdropFilter && scs.backdropFilter !== "none");
      if (r0.width < sc.clientWidth * 0.6 || !filled) continue;
      // «Наезжает на строку» — только пока плашка стоит на своём месте (не прилипла): экран, открытый уже прокрученным
      // (карточка жалобы по ссылке), законно прячет строки под прилипшей плашкой.
      const pos0 = st.style.position;
      st.style.position = "static";
      const atPlace = Math.abs(st.getBoundingClientRect().top - r0.top) <= 2;
      st.style.position = pos0;
      const next = st.nextElementSibling;
      if (atPlace && next && vis(next) && getComputedStyle(next).position !== "sticky" && label && !clean(next.innerText).startsWith(label)) {
        const rn = next.getBoundingClientRect();
        if (rn.top < r0.bottom - 2 && rn.bottom > r0.top + 2 && clean(next.innerText)) out.stickyOver.push({ sticky: label, row: clean(next.innerText).slice(0, 30), overlap: Math.round(r0.bottom - rn.top) });
      }
      const scTop = sc.getBoundingClientRect().top;
      sc.scrollTop = keep + Math.max(0, r0.top - scTop) + 120;
      await frame();
      const cr = sc.getBoundingClientRect(), r = st.getBoundingClientRect();
      const clipTop = cr.top + (parseFloat(getComputedStyle(sc).borderTopWidth) || 0);
      // Плашка действительно «прилипла»: без sticky она была бы выше (уехала с прокруткой). Последняя плашка в конце
      // списка (прокрутка упёрлась) стоит на своём месте — строки над ней видны законно.
      const prevPos = st.style.position;
      st.style.position = "static";
      const natural = st.getBoundingClientRect().top;
      st.style.position = prevPos;
      const stuck = natural < r.top - 2;
      if (stuck && r.top - clipTop > 3 && r.top >= clipTop && r.top < cr.bottom - 20) {
        // Видна строка списка: в полосе над плашкой точка попадает в строку — ближайший элемент с текстом размером со строку
        // (≤ 150 px, ≤ 240 знаков). Фон контейнера списка (его innerText — весь список) не в счёт: так выходил ложный FAIL.
        const rowAt = (x, y) => {
          const h = document.elementFromPoint(x, y);
          if (!h || h === sc || !sc.contains(h)) return null;
          for (let n = h; n && n !== sc; n = n.parentElement) if (getComputedStyle(n).position === "sticky") return null;
          for (let n = h; n && n !== sc; n = n.parentElement) {
            const txt = clean(n.innerText);
            if (!txt) continue;
            const q = n.getBoundingClientRect();
            return q.height <= 150 && txt.length <= 240 ? txt.slice(0, 36) : null;
          }
          return null;
        };
        let peek = null;
        for (let y = clipTop + 2; y < r.top - 1 && !peek; y += 4) {
          for (let x = r.left + 16; x < r.right - 16 && !peek; x += 36) {
            const txt = rowAt(x, y);
            if (txt) peek = { y: Math.round(y - clipTop), text: txt };
          }
        }
        if (peek) out.stickyPeek.push({ sticky: label, gap: Math.round(r.top - clipTop), peek });
      }
      sc.scrollTop = keep;
      await frame();
    }
    // 2. Кнопки действий у края листа (строки списков и кнопки-значки не считаются: последняя строка списка всегда видна частично).
    const clipOf = (e) => { for (let n = e.parentElement; n && n !== document.body; n = n.parentElement) {
      if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(n).overflowY)) return n; } return null; };
    const actions = [...root.querySelectorAll("button, a[href], [role=button]")].filter((b) => {
      if (!vis(b) || b.closest("li, ul, ol, table, [role=list], [role=listitem], [role=tablist], .maplibregl-map")) return false;
      const t = clean(b.innerText); const r = b.getBoundingClientRect();
      return t && t.length <= 40 && !/\n/.test((b.innerText || "").trim()) && r.height <= 64; });
    const frac = (b, c) => { const r = b.getBoundingClientRect(), cr = c ? c.getBoundingClientRect() : { top: 0, bottom: innerHeight };
      const top = Math.max(r.top, cr.top, 0), bottom = Math.min(r.bottom, cr.bottom, innerHeight); return Math.max(0, bottom - top) / r.height; };
    const cutNow = actions.map((b) => ({ b, c: clipOf(b) })).filter(({ b, c }) => { const f = frac(b, c); return f > 0.05 && f < 0.95; });
    for (const { b, c } of cutNow.slice(0, 6)) {
      const sc = c && c.scrollHeight > c.clientHeight + 4 ? c : null;
      let fEnd = frac(b, c);
      if (sc) { const keep = sc.scrollTop; sc.scrollTop = sc.scrollHeight; await frame(); fEnd = frac(b, c); sc.scrollTop = keep; await frame(); }
      const item = { t: clean(b.innerText).slice(0, 32), visible: Math.round(frac(b, c) * 100) + "%", atEnd: Math.round(fEnd * 100) + "%", scroll: !!sc };
      (fEnd < 0.95 ? out.cutEnd : out.cutNow).push(item);
    }
    // 3. Поля листа на широком экране: содержимое (текст и элементы управления) — узкая колонка посреди белого листа.
    const rr = root.getBoundingClientRect();
    if (innerWidth >= 1200 && rr.width >= 900) {
      const cs = getComputedStyle(root);
      const inL = rr.left + (parseFloat(cs.paddingLeft) || 0), inR = rr.right - (parseFloat(cs.paddingRight) || 0);
      // Края колонки — по большинству элементов (5-й и 95-й перцентили), а не по одной кнопке панели у правого края.
      const ls = [], rs = [];
      for (const e of root.querySelectorAll("*")) {
        const own = [...e.childNodes].some((x) => x.nodeType === 3 && x.textContent.trim());
        if (!(own || /^(BUTTON|INPUT|SELECT|TEXTAREA|IMG|CANVAS)$/.test(e.tagName)) || !vis(e)) continue;
        const r = e.getBoundingClientRect();
        if (r.bottom < rr.top || r.top > rr.bottom || r.right < rr.left || r.left > rr.right) continue;
        ls.push(r.left); rs.push(r.right);
      }
      if (ls.length >= 5) {
        ls.sort((a, b) => a - b); rs.sort((a, b) => a - b);
        const left = ls[Math.floor(ls.length * 0.05)], right = rs[Math.min(rs.length - 1, Math.floor(rs.length * 0.95))];
        out.margins = { sheet: Math.round(rr.width), content: Math.round(right - left), left: Math.round(left - inL), right: Math.round(inR - right), n: ls.length };
      }
    }
    // 4. Серый квадрат с маленьким значком — «пропавшая картинка» (П1: значок вида — в строке, без квадрата).
    // Видимый текст: подпись для читалки (.bk-sr-only, 1×1 px) не в счёт — у квадрата R16 она есть («Субботник»).
    const seenText = (e) => { const w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
      for (let n = w.nextNode(); n; n = w.nextNode()) { const pr = n.parentElement && n.parentElement.getBoundingClientRect();
        if (n.textContent.trim() && pr && pr.width > 4 && pr.height > 4) return true; } return false; };
    for (const e of root.querySelectorAll("div, span, figure, i")) {
      if (!vis(e) || seenText(e)) continue;
      const r = e.getBoundingClientRect();
      if (r.width < 56 || r.height < 56 || r.width > 200 || r.height > 200 || Math.abs(r.width - r.height) / Math.max(r.width, r.height) > 0.3) continue;
      const cs = getComputedStyle(e);
      if (parseFloat(cs.borderTopLeftRadius) >= r.width * 0.4) continue;
      const m = cs.backgroundColor.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
      if (!m || (m[4] !== undefined && +m[4] < 0.05) || cs.backgroundImage !== "none") continue;
      const lum = (0.2126 * m[1] + 0.7152 * m[2] + 0.0722 * m[3]) / 255;
      if (lum > 0.985) continue;
      const icons = [...e.querySelectorAll("svg, img, i")].filter(vis);
      if (!icons.length) continue;
      const area = icons.reduce((a, x) => { const q = x.getBoundingClientRect(); return a + q.width * q.height; }, 0);
      if (area / (r.width * r.height) < 0.25) out.placeholder.push({ box: `${Math.round(r.width)}×${Math.round(r.height)}`, bg: cs.backgroundColor,
        icon: Math.round(Math.sqrt(area)) + " px", near: clean(e.parentElement && e.parentElement.innerText).slice(0, 40) });
      if (out.placeholder.length >= 4) break;
    }
    return out;
  }, sel);
}

// Значок «ИИ» у подсказки ИИ (П3, R11): маленький монохромный значок с подсказкой «Подсказка ИИ — проверьте».
// Ищется в блоке вокруг текста подсказки: title / aria-label / data-tooltip со словом «ИИ» (ҚАЗ «ЖИ», «жасанды»),
// свой текст «ИИ» / «ЖИ» / «AI» или значок набора с «ai» в имени. → {hint: найден ли текст, mark: как найден значок | null}.
function aiMark(page, hintRe, rootSel = "body") {
  return page.evaluate(({ src, flags, rs }) => {
    const re = new RegExp(src, flags), root = document.querySelector(rs) || document.body;
    const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden"; };
    let hint = null;
    for (const e of root.querySelectorAll("*")) {
      const own = [...e.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(" ");
      if (re.test(own) && vis(e)) { hint = e; break; }
    }
    if (!hint) return { hint: false, mark: null };
    const MARK = /(^|[^А-Яа-яЁё])(ИИ|ЖИ)([^А-Яа-яЁё]|$)|\bAI\b|жасанды|искусствен/i;
    let block = hint;
    for (let i = 0; i < 4 && block.parentElement && block.parentElement !== root; i++) {
      block = block.parentElement;
      const r = block.getBoundingClientRect();
      if (r.height > 260) break;
    }
    for (const e of [block, ...block.querySelectorAll("*")]) {
      for (const a of ["title", "aria-label", "data-tooltip", "data-tip", "data-title"]) {
        const v = e.getAttribute && e.getAttribute(a);
        if (v && MARK.test(v)) return { hint: true, mark: `${a}: «${v.slice(0, 40)}»` };
      }
      const own = [...(e.childNodes || [])].filter((n) => n.nodeType === 3).map((n) => n.textContent).join("").trim();
      if (/^(ИИ|ЖИ|AI)$/.test(own)) return { hint: true, mark: `текст «${own}»` };
      const use = e.tagName === "use" ? (e.getAttribute("href") || e.getAttribute("xlink:href") || "") : "";
      const cls = String((e.getAttribute && e.getAttribute("class")) || "");
      if (/(^|[#\s_-])(i-)?ai([\s_-]|$)|[#-]ai$/.test(use + " " + cls)) return { hint: true, mark: `значок ${(use || cls).slice(0, 30)}` };
    }
    return { hint: true, mark: null, near: (block.innerText || "").trim().replace(/\s+/g, " ").slice(0, 60) };
  }, { src: hintRe.source, flags: hintRe.flags, rs: rootSel });
}

// Карта: перехват экземпляра MapLibre (оболочка его наружу не отдаёт) — для вопроса «чьи это слои». Только наблюдение:
// класс Map подменяется наследником, который запоминает экземпляр; поведение карты то же. Ставится через addInitScript.
function mapHook() {
  let ml;
  Object.defineProperty(window, "maplibregl", { configurable: true, get() { return ml; }, set(v) {
    ml = v;
    try {
      const Orig = v && v.Map;
      if (Orig && !Orig.__r10) {
        class R10Map extends Orig { constructor(...a) { super(...a); (window.__r10maps = window.__r10maps || []).push(this); } }
        R10Map.__r10 = true;
        v.Map = R10Map;
      }
    } catch (e) { /* карта без перехвата — проверка будет NOT_RUN */ }
  } });
}

// Обзорный масштаб (< 13; кадры 02, 08): какие слои кроме значков районов R07 рисуют точки и где они наезжают друг на друга.
function mapOverview(page) {
  return page.evaluate(() => {
    const map = (window.__r10maps || [])[0];
    if (!map || !map.isStyleLoaded || !map.getZoom) return null;
    const z = map.getZoom();
    const c = map.getCanvas().getBoundingClientRect();
    const feats = map.queryRenderedFeatures().filter((f) => /^(circle|symbol)$/.test(f.layer.type) && !/^offline-|^r07-|(^|[-_])(label|place|poi|road|street)s?([-_]|$)/i.test(f.layer.id)
      && f.geometry && f.geometry.type === "Point");
    const pts = [];
    for (const f of feats) {
      const p = map.project(f.geometry.coordinates);
      if (p.x < 0 || p.y < 0 || p.x > c.width || p.y > c.height) continue;
      pts.push({ layer: f.layer.id, id: String(f.properties.id || f.id || ""), name: String(f.properties.name_ru || f.properties.label_ru || f.properties.title || "").slice(0, 40), x: Math.round(p.x), y: Math.round(p.y) });
    }
    // точки одного объекта в разных слоях (кольцо + ореол + пунктир) — одна точка
    const byObj = new Map();
    for (const p of pts) { const k = p.id || `${p.x},${p.y}`; if (!byObj.has(k)) byObj.set(k, { ...p, layers: new Set([p.layer]) }); else byObj.get(k).layers.add(p.layer); }
    const objs = [...byObj.values()].map((o) => ({ ...o, layers: [...o.layers] }));
    const close = [];
    for (let i = 0; i < objs.length; i++) for (let j = i + 1; j < objs.length; j++) {
      const d = Math.hypot(objs[i].x - objs[j].x, objs[i].y - objs[j].y);
      if (d < 28) close.push([objs[i].name || objs[i].id, objs[j].name || objs[j].id, Math.round(d)]);
    }
    const badges = [...document.querySelectorAll(".maplibregl-marker")].map((m) => m.getBoundingClientRect()).filter((r) => r.width > 0);
    const underBadge = objs.filter((o) => badges.some((b) => o.x + c.left >= b.left - 6 && o.x + c.left <= b.right + 6 && o.y + c.top >= b.top - 6 && o.y + c.top <= b.bottom + 6));
    const seen = {};
    for (const f of map.queryRenderedFeatures()) seen[f.layer.id] = (seen[f.layer.id] || 0) + 1;
    return { zoom: Math.round(z * 100) / 100, points: objs.length, layers: [...new Set(pts.map((p) => p.layer))], close: close.slice(0, 6), seen,
      underBadge: underBadge.map((o) => o.name || o.id).slice(0, 4), sample: objs.slice(0, 4).map((o) => `${o.name || o.id} [${o.layers.join(", ")}]`) };
  });
}

// Шаблон без подстановки на экране: «Создать {n} задач» (ключ словаря с {n}, а экран числа не подставил) — виден жюри.
function placeholders(page, sel = "body") {
  return page.evaluate((s) => {
    const root = document.querySelector(s) || document.body, out = [];
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n && out.length < 6; n = w.nextNode()) {
      const m = n.textContent.match(/\{[a-z_]{1,24}\}/i);
      if (!m || n.parentElement.closest("code, pre, script, style, textarea")) continue;
      const r = n.parentElement.getBoundingClientRect();
      if (r.width > 1 && r.height > 1) out.push(n.textContent.trim().replace(/\s+/g, " ").slice(0, 50));
    }
    return out;
  }, sel);
}

module.exports = { NOISE, TECH_WORDS, RAW_KEY, SAME_IN_BOTH, TAB_LIMIT, AUDIT_FONT_MIN, AUDIT_TAP_MIN, uiScreen, uiAudit, cyrLines, untranslated, focusToPrimary,
  sheetMetrics, aiMark, mapHook, mapOverview, placeholders };
