#!/usr/bin/env node
// R10 · раунд 14 · дизайн-марафон (DESIGN_MARATHON.md): «книга экранов» сборки — все экраны и состояния, 1366×768 и
// 375×812, ru и kk, кадр каждого состояния и автоматический замер по чек-листу качества (12 пунктов):
//   1 иерархия (сколько главных тёмных кнопок) · 2 сетка 8 pt (отступы/промежутки не кратны 4) · 3 типографика (размеры вне
//   шкалы 13/15/17/22/28, веса вне 400/600, сколько размеров на экране, строки > 70 знаков, обрезанный текст) · 4 цвет
//   (бежевые плашки, лишние яркие краски, рамки) · 5 стекло (где backdrop-filter; контраст — glass_check.cjs) · 6 глубина
//   (радиусы вне токенов, двойные тени) · 7 движение (длительности вне 200–350 мс; «уменьшить движение») · 8 состояния
//   (скелетон при загрузке, «пока пусто» с подсказкой и кнопкой, ошибка «что случилось + что делать») · 9 иконки (толщина
//   линии, кнопки-значки без подписи) · 10 нажатия (зоны ≥ 44, фокус виден, отклик на нажатие) · 11 тексты (технические
//   слова и канцелярит, длинные подписи кнопок) · 12 «вау» (анимации появления и пульса — для сведения).
// Логику не трогает: только смотрит. Владелец замечания — по классу модуля (r07- R07, akim-/nb- R08, bc- R09, ri-/rw-/r06-
// R06, qa- R13, bq-/editor R12, b3d- R05, остальное — оболочка R01; bk- — компонент ui-kit R11).
//
//   NODE_PATH="$(npm root -g)" node tests/e2e/design_book.cjs --root <сборка> --out <папка> [--sizes 1366x768,375x812]
//        [--langs ru,kk] [--only r-map,a-day] [--glass keep|off|auto]   (keep — по умолчанию: стекло видно и в облаке)
// Итог: <out>/BOOK.json, BOOK.md, кадры <размер>-<язык>/<id>.jpg; сравнение сборок — design_compare.cjs.
"use strict";
const fs = require("fs"), path = require("path"), os = require("os");
const { chromium } = require("playwright");
const L = require("./r10_lib.cjs");
const { uiAudit } = require("./ux_lib.cjs");

const args = L.parseArgs(process.argv.slice(2));
const ROOT = path.resolve(String(args.root || path.join(__dirname, "../..")));
const OUT = path.resolve(String(args.out || path.join(os.tmpdir(), "r10-design")));
const SIZES = String(args.sizes || "1366x768,375x812").split(",").map((s) => s.split("x").map(Number));
const LANGS = String(args.langs || "ru,kk").split(",");
const ONLY = args.only ? new Set(String(args.only).split(",")) : null;
const GLASS = args.glass === "auto" ? null : String(args.glass || "keep");
const DICT = { ru: L.loadDict(ROOT, "ru"), kk: L.loadDict(ROOT, "kk") };
const word = (lang, key, ru, kk) => L.T(DICT[lang], key, lang === "kk" ? kk : ru);
const exactRe = (s) => new RegExp("^\\s*(·\\s*)?" + L.esc(s) + "\\s*(·\\s*\\d+)?\\s*$", "i");
const partRe = (s) => new RegExp(L.esc(s), "i");
const KHAN = { id: "osm-node-4109037549", name: "Хан Шатыр", point: [71.406553, 51.131155] };

// ------------------------------------------------------------------------------------------------ замер в странице
const DESIGN = () => {
  const vis = (e) => { const r = e.getBoundingClientRect(); if (r.width < 1 || r.height < 1 || r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) return false;
    const s = getComputedStyle(e); return s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0.05; };
  const OWN = [[/^r07-/, "R07"], [/^(akim|nb)[-_]/, "R08"], [/^bc-/, "R09"], [/^(ri|rw|r06)-/, "R06"], [/^qa[-_]/, "R13"], [/^bq-/, "R12"], [/editor/i, "R12"], [/^b3d-/, "R05"]];
  const ownerOf = (e) => { for (let p = e; p && p !== document.body; p = p.parentElement) { const cls = [...(p.classList || [])].concat(p.id ? [p.id] : []);
    for (const c of cls) for (const [re, o] of OWN) if (re.test(c)) return o; } return "R01"; };
  const label = (e) => ((e.getAttribute && e.getAttribute("aria-label")) || e.innerText || e.textContent || "").trim().replace(/\s+/g, " ").slice(0, 48);
  const rgba = (c) => { const m = String(c).match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; };
  const hsl = ([r, g, b]) => { r /= 255; g /= 255; b /= 255; const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2; let h = 0, s = 0;
    if (mx !== mn) { const d = mx - mn; s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn); h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; h *= 60; }
    return [Math.round(h), Math.round(s * 100), Math.round(l * 100)]; };
  const lin = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
  const lum = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const hex = (c) => "#" + c.slice(0, 3).map((x) => Math.round(x).toString(16).padStart(2, "0")).join("");
  const push = (o, k, v, max = 8) => { (o[k] = o[k] || []); if (o[k].length < max) o[k].push(v); };
  const inMap = (e) => !!e.closest(".maplibregl-canvas-container, .maplibregl-ctrl-attrib, .maplibregl-marker");
  const all = [...document.querySelectorAll("body *")].filter((e) => !e.closest("svg") || e.tagName.toLowerCase() === "svg").filter(vis);
  const R = { owners: {} };
  const issue = (pt, owner, what) => { const o = (R.owners[owner] = R.owners[owner] || {}); if (!(o[pt] || []).includes(what)) push(o, pt, what, 6); };

  // 3. Типографика
  const SCALE = new Set([13, 15, 17, 22, 28]);
  const sizes = {}, weights = {}, offScale = [], longLines = [], cut = [];
  for (const e of all) {
    const own = [...e.childNodes].filter((x) => x.nodeType === 3 && /\p{L}|\d/u.test(x.textContent)).map((x) => x.textContent).join(" ").replace(/\s+/g, " ").trim();
    if (!own) continue;
    const s = getComputedStyle(e), fs = Math.round(parseFloat(s.fontSize) * 10) / 10, fw = Number(s.fontWeight);
    const map = inMap(e) || !!e.closest(".r07-badge");
    sizes[fs] = (sizes[fs] || 0) + 1; weights[fw] = (weights[fw] || 0) + 1;
    if (!SCALE.has(Math.round(fs)) && !e.closest(".maplibregl-ctrl-attrib")) { offScale.push({ fs, text: own.slice(0, 30), owner: ownerOf(e) }); issue("3 типографика", ownerOf(e), `${fs} px вне шкалы: «${own.slice(0, 24)}»`); }
    if (fw !== 400 && fw !== 600) issue("3 типографика", ownerOf(e), `вес ${fw}: «${own.slice(0, 24)}»`);
    if (own.length >= 60 && !map) {
      const rg = document.createRange(); const tops = new Set();
      for (const x of e.childNodes) if (x.nodeType === 3) { rg.selectNodeContents(x); for (const q of rg.getClientRects()) if (q.width > 2) tops.add(Math.round(q.top / 4)); }
      const lines = Math.max(1, tops.size), cpl = Math.round(own.length / lines);
      if (cpl > 75) { longLines.push({ cpl, lines, text: own.slice(0, 30), owner: ownerOf(e) }); issue("3 типографика", ownerOf(e), `строка ~${cpl} знаков (> 70): «${own.slice(0, 24)}»`); }
    }
    if ((s.textOverflow === "ellipsis" && e.scrollWidth > e.clientWidth + 1) || (/-webkit-box/.test(s.display) && e.scrollHeight > e.clientHeight + 2)) {
      cut.push({ text: own.slice(0, 30), owner: ownerOf(e) }); issue("3 типографика", ownerOf(e), `обрезано «…»: «${own.slice(0, 24)}»`); }
  }
  const sizeList = Object.keys(sizes).map(Number).sort((a, b) => a - b);
  R.type = { sizes, weights, distinct: sizeList.length, off_scale: offScale.slice(0, 12), long_lines: longLines.slice(0, 8), cut: cut.slice(0, 8) };

  // 1. Иерархия: главные кнопки — тёмная заливка (≈ #152c26) со светлым текстом; нажатые переключатели не считаются.
  const primaries = [];
  for (const e of all) {
    if (!e.matches("button, a, [role=button], input[type=submit]") || e.closest(".r07-badge, .maplibregl-marker")) continue;
    if (e.matches("[aria-pressed=true], [aria-expanded=true], [aria-checked=true], [aria-selected=true], [aria-current]")) continue;
    const s = getComputedStyle(e), bg = rgba(s.backgroundColor), fg = rgba(s.color), r = e.getBoundingClientRect();
    if (!bg || bg[3] < 0.9 || !fg || r.width < 60 || r.height < 30) continue;
    if (lum(bg) < 0.06 && lum(fg) > 0.6) primaries.push({ label: label(e), owner: ownerOf(e), w: Math.round(r.width) });
  }
  R.hierarchy = { primary: primaries.length, list: primaries.slice(0, 6) };
  if (primaries.length > 1) for (const p of primaries) issue("1 иерархия", p.owner, `главных кнопок ${primaries.length}: «${p.label}»`);

  // 4. Цвет и 6. Глубина: фоны, рамки, радиусы, тени
  const HEAT = ["#fac775", "#ef9f27", "#e24b4a", "#a32d2d", "#152c26"].map((h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)));
  const near = (c, d) => HEAT.some((h) => Math.abs(h[0] - c[0]) + Math.abs(h[1] - c[1]) + Math.abs(h[2] - c[2]) < d);
  const RADII = [0, 8, 10, 14, 20, 24, 28];
  const beige = [], accents = {}, radii = {}, offRadii = [], shadows = [], doubles = [], borders = {};
  for (const e of all) {
    if (inMap(e) && !e.closest(".r07-badge")) continue;
    const s = getComputedStyle(e), r = e.getBoundingClientRect(), bg = rgba(s.backgroundColor);
    const area = r.width * r.height, owner = ownerOf(e);
    if (bg && bg[3] >= 0.3 && area >= 300) {
      const [h, sat, l] = hsl(bg);
      // Бежевые и кремовые плашки (CLEAN_PASS: «без бежевых плашек»): тёплый оттенок, светлая заливка.
      if (h >= 25 && h <= 60 && sat >= 12 && l >= 80 && l <= 97) { beige.push({ c: hex(bg), owner, label: label(e).slice(0, 24) }); issue("4 цвет", owner, `бежевая плашка ${hex(bg)}: «${label(e).slice(0, 20)}»`); }
      if (sat >= 45 && l >= 20 && l <= 75 && !near(bg, 60)) accents[hex(bg)] = (accents[hex(bg)] || 0) + 1;
    }
    const bw = parseFloat(s.borderTopWidth) + parseFloat(s.borderRightWidth) + parseFloat(s.borderBottomWidth) + parseFloat(s.borderLeftWidth);
    const bc = rgba(s.borderTopColor);
    if (bw >= 1 && s.borderTopStyle !== "none" && bc && bc[3] > 0.15 && area >= 2000 && !e.matches("input, select, textarea, hr")) borders[owner] = (borders[owner] || 0) + 1;
    const rad = parseFloat(s.borderTopLeftRadius);
    if (rad > 0 && ((bg && bg[3] >= 0.3) || bw >= 1 || s.boxShadow !== "none")) {
      const pill = rad >= Math.min(r.width, r.height) / 2 - 1 || /%/.test(s.borderTopLeftRadius);
      const key = pill ? "капсула/круг" : String(Math.round(rad));
      radii[key] = (radii[key] || 0) + 1;
      if (!pill && !RADII.some((t) => Math.abs(t - rad) < 0.6) && r.width >= 24) { offRadii.push({ rad, owner, label: label(e).slice(0, 20) }); issue("6 глубина", owner, `радиус ${Math.round(rad)} px вне токенов: «${label(e).slice(0, 20)}»`); }
    }
    if (s.boxShadow && s.boxShadow !== "none" && !/^inset/.test(s.boxShadow.trim()) && area >= 1500) {
      shadows.push(e);
      for (let p = e.parentElement, k = 0; p && k < 3; p = p.parentElement, k++) {
        const ps = getComputedStyle(p); if (!ps.boxShadow || ps.boxShadow === "none" || /^inset/.test(ps.boxShadow.trim())) continue;
        const q = p.getBoundingClientRect();
        if (Math.abs(q.left - r.left) <= 12 && Math.abs(q.right - r.right) <= 12 && Math.abs(q.top - r.top) <= 12 && Math.abs(q.bottom - r.bottom) <= 12) {
          doubles.push({ owner, label: label(e).slice(0, 20) }); issue("6 глубина", owner, `двойная тень (элемент и родитель): «${label(e).slice(0, 20)}»`); break; }
      }
    }
  }
  const acc = Object.entries(accents).sort((a, b) => b[1] - a[1]);
  R.color = { beige: beige.slice(0, 8), extra_accents: acc.slice(0, 8), borders };
  R.depth = { radii, off_radii: offRadii.slice(0, 10), shadows: shadows.length, double_shadows: doubles.slice(0, 6) };

  // 2. Сетка 8 pt: отступы контейнеров и кнопок, промежутки flex/grid — не кратные 4 (4 — полшага).
  const offGrid = [];
  let grid = 0, gridOk = 0;
  for (const e of all) {
    if (inMap(e)) continue;
    const s = getComputedStyle(e), bg = rgba(s.backgroundColor);
    const box = (bg && bg[3] >= 0.3) || s.boxShadow !== "none" || parseFloat(s.borderTopWidth) >= 1 || e.matches("button, a.bk-btn, [role=button]") || /flex|grid/.test(s.display);
    if (!box) continue;
    const vals = [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft].map(parseFloat);
    if (/flex|grid/.test(s.display)) for (const g of [s.rowGap, s.columnGap]) if (g && g !== "normal") vals.push(parseFloat(g));
    for (const v of vals) { if (!(v > 2)) continue; /* 1–2 px — оптическая подгонка у рамок */ grid++; if (Math.abs(v / 4 - Math.round(v / 4)) < 0.05) gridOk++; else { offGrid.push({ v, owner: ownerOf(e), label: label(e).slice(0, 20) }); issue("2 сетка", ownerOf(e), `отступ ${v} px не кратен 4: «${label(e).slice(0, 20)}»`); } }
  }
  R.grid = { values: grid, on_grid: grid ? Math.round((gridOk / grid) * 100) : null, off: offGrid.slice(0, 10) };

  // 5. Стекло (где): элементы с backdrop-filter.
  R.glass = all.filter((e) => { const f = getComputedStyle(e).backdropFilter; return f && f !== "none"; }).map((e) => ({ owner: ownerOf(e), cls: String(e.className).slice(0, 40) })).slice(0, 20);
  R.glass_off = document.documentElement.classList.contains("bk-glass-off");

  // 9. Иконки: толщина линии (в px экрана), кнопки-значки без подписи.
  const strokes = {}, iconOnly = [];
  for (const svg of all.filter((e) => e.tagName.toLowerCase() === "svg")) {
    if (svg.closest(".maplibregl-canvas-container")) continue;
    const vb = svg.viewBox && svg.viewBox.baseVal, rr = svg.getBoundingClientRect(), k = vb && vb.width ? rr.width / vb.width : 1;
    for (const sh of svg.querySelectorAll("path, line, circle, rect, polyline, polygon")) {
      const ss = getComputedStyle(sh); if (!ss.stroke || ss.stroke === "none" || parseFloat(ss.strokeWidth) <= 0) continue;
      const w = Math.round(parseFloat(ss.strokeWidth) * k * 4) / 4; strokes[w] = (strokes[w] || 0) + 1;
    }
  }
  for (const b of all.filter((e) => e.matches("button, a[href], [role=button]"))) {
    const txt = (b.innerText || "").trim();
    if (txt || !b.querySelector("svg, img") || b.closest(".map-tools, .bk-mapctl, .maplibregl-ctrl, .r07-badge")) continue;
    iconOnly.push({ label: (b.getAttribute("aria-label") || b.title || "").slice(0, 30), owner: ownerOf(b) });
  }
  R.icons = { stroke_px: strokes, icon_only_buttons: iconOnly.slice(0, 10) };

  // 7. Движение: длительности переходов и анимаций видимых элементов.
  const durs = (v) => String(v).split(",").map((x) => (/ms/.test(x) ? parseFloat(x) : parseFloat(x) * 1000)).filter((x) => x > 0);
  const motion = {}, offMotion = [];
  for (const e of all) {
    const s = getComputedStyle(e);
    const td = durs(s.transitionDuration), ad = s.animationName && s.animationName !== "none" ? durs(s.animationDuration) : [];
    const inf = /infinite/.test(s.animationIterationCount);
    for (const d of td.concat(inf ? [] : ad)) {
      const key = `${Math.round(d)} мс`; motion[key] = (motion[key] || 0) + 1;
      if (d < 170 || d > 380) offMotion.push({ ms: Math.round(d), owner: ownerOf(e), what: (td.includes(d) ? "переход " + s.transitionProperty.slice(0, 30) : "анимация " + s.animationName), label: label(e).slice(0, 20) });
    }
    if (inf && ad.length) motion["∞ " + s.animationName] = (motion["∞ " + s.animationName] || 0) + 1;
  }
  R.motion = { durations: motion, off: offMotion.slice(0, 10), reduce: matchMedia("(prefers-reduced-motion: reduce)").matches };
  for (const m of offMotion.slice(0, 20)) issue("7 движение", m.owner, `${m.what} ${m.ms} мс (норма 200–350): «${m.label}»`);

  // 8. Состояния: скелетон, «пока пусто», ошибка.
  const skel = all.filter((e) => /skel|shimmer|placeholder|loading/i.test(String(e.className)) || e.getAttribute("aria-busy") === "true").length;
  const empties = all.filter((e) => /\b(bk-empty|empty)\b|__empty|-empty/.test(String(e.className))).map((e) => ({ owner: ownerOf(e), text: label(e).slice(0, 40), button: !!e.querySelector("button, a[href]") }));
  R.states = { skeleton: skel, empty: empties.slice(0, 4), busy: !!document.querySelector("[aria-busy=true]") };

  // 11. Тексты: технические слова и канцелярит; подписи кнопок длиннее 4 слов.
  const TECH = /\b(null|undefined|NaN|error|exception|API|JSON|token|osm-node-\d+|HTTP|404|500|503|id\s*\d+)\b|функционал|осуществл|посредством|вышеуказ|в целях|производится|является обязательн|данн(ый|ая|ое|ые) (объект|обращени|запрос)/i;
  const tech = [], longBtn = [];
  for (const e of all) {
    const own = [...e.childNodes].filter((x) => x.nodeType === 3).map((x) => x.textContent).join(" ").trim();
    if (own && TECH.test(own) && !e.closest(".maplibregl-ctrl-attrib, script, style")) { tech.push({ text: own.slice(0, 40), owner: ownerOf(e) }); issue("11 тексты", ownerOf(e), `техническое слово: «${own.slice(0, 30)}»`); }
  }
  for (const b of all.filter((e) => e.matches("button, [role=button], a.bk-btn"))) {
    const raw = (b.innerText || "").trim(), t = raw.replace(/\s+/g, " "), bh = b.getBoundingClientRect().height;
    if (/\n/.test(raw) || bh > 64 || b.querySelectorAll("*").length > 6) continue;  // строка списка / карточка-кнопка — не подпись
    if (t.split(" ").filter(Boolean).length > 4 && t.length > 28) { longBtn.push({ text: t.slice(0, 40), owner: ownerOf(b) }); issue("11 тексты", ownerOf(b), `длинная подпись кнопки: «${t.slice(0, 30)}»`); }
  }
  R.texts = { tech: tech.slice(0, 8), long_buttons: longBtn.slice(0, 8), buttons: all.filter((e) => e.matches("button, [role=button]")).map((b) => (b.innerText || b.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 30)).filter(Boolean).slice(0, 40) };

  // 12. «Вау» (для сведения): анимации появления и пульса на экране.
  R.wow = { animated: [...new Set(all.map((e) => getComputedStyle(e).animationName).filter((n) => n && n !== "none"))].slice(0, 10) };
  return R;
};

// Фокус с клавиатуры виден (10): Tab по первым 12 элементам — рамка (outline ≥ 2 px) или кольцо (box-shadow).
async function focusCheck(page) {
  await page.mouse.click(2, 2).catch(() => null);
  const res = [];
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab"); await L.sleep(120);
    res.push(await page.evaluate(() => { const e = document.activeElement; if (!e || e === document.body) return null; const s = getComputedStyle(e);
      const ring = (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) >= 2) || (s.boxShadow && s.boxShadow !== "none" && /\d+px/.test(s.boxShadow));
      return { label: ((e.getAttribute("aria-label") || e.innerText || e.tagName) + "").trim().replace(/\s+/g, " ").slice(0, 30), ring }; }));
  }
  const got = res.filter(Boolean);
  return { tabbed: got.length, with_ring: got.filter((x) => x.ring).length, without: got.filter((x) => !x.ring).map((x) => x.label).slice(0, 6) };
}
// Отклик на нажатие (10): у главной кнопки при нажатии меняется фон, тень, сжатие или прозрачность (без клика — отпускаем мимо).
async function pressCheck(page, re) {
  const b = await L.firstVisible(page.getByRole("button", { name: re }));
  if (!b) return null;
  const box = await b.boundingBox(); if (!box) return null;
  const read = () => b.evaluate((e) => { const s = getComputedStyle(e); return [s.backgroundColor, s.transform, s.boxShadow, s.opacity, s.filter].join("|"); });
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await L.sleep(300);
  const a = await read(); await page.mouse.down(); await L.sleep(300); const d = await read(); const box2 = await b.boundingBox();
  await page.mouse.move(2, 2); await page.mouse.up(); await L.sleep(200);
  // Отклик — да; но кнопка не должна «прыгать»: сдвиг рамки при нажатии больше 3 px — дефект (transform :active перебил свой).
  const jump = box2 ? Math.round(Math.max(Math.abs(box2.x - box.x), Math.abs(box2.y - box.y))) : null;
  return { feedback: a !== d, jump_px: jump, jumps: jump !== null && jump > 3, normal: a.slice(0, 80), pressed: d.slice(0, 80) };
}

// ------------------------------------------------------------------------------------------------ состояния
const header = (P, key, ru, kk, wait = 2500) => L.headerClick(P.page, exactRe(word(P.lang, key, ru, kk)), { wait, menuRe: exactRe(word(P.lang, "common.nav.menu", "Меню", "Мәзір")) });
const visible = async (page, sel) => !!(await L.firstVisible(page.locator(sel)));
// Раздел: кнопка шапки / меню аватара (header) или пункт меню «Ещё» на ноутбуке.
async function section(P, key, ru, kk) {
  if (await header(P, key, ru, kk)) return true;
  const more = await L.firstVisible(P.page.getByRole("button", { name: exactRe(word(P.lang, "common.nav.more", "Ещё", "Тағы")) }));
  if (!more) return false;
  await more.click().catch(() => null); await L.sleep(700);
  const re = exactRe(word(P.lang, key, ru, kk));
  for (const role of ["menuitem", "menuitemradio", "button", "link"]) {
    const it = await L.firstVisible(P.page.getByRole(role, { name: re }));
    if (it) { await it.click().catch(() => null); await L.sleep(2500); return true; }
  }
  return false;
}
async function openCard(P, stop = KHAN) {
  const p = await L.showPoint(P.page, stop.point, 17); if (!p) return false;
  await L.tap(P.page, p.x, p.y); await L.sleep(2500);
  return visible(P.page, ".r07-card");
}
async function startWizard(P) {
  const re = partRe(word(P.lang, "complaint.start.button", "Сообщить о проблеме", "Мәселе туралы хабарлау"));
  const b = await L.firstVisible(P.page.getByRole("button", { name: re }).or(P.page.locator(".bc-fab")));
  if (!b) return false; await b.click().catch(() => null); await L.sleep(1800);
  return !!(await L.firstVisible(P.page.getByRole("dialog")));
}
async function wizardText(P) {
  const pt = await L.showPoint(P.page, KHAN.point, 17);
  if (pt) { const at = pt.onCanvas || !pt.near ? pt : pt.near; await L.tap(P.page, at.x, at.y); await L.sleep(2500); }
  const dlg = (await L.firstVisible(P.page.getByRole("dialog"))) || P.page;
  const place = (await L.firstVisible(dlg.getByRole("button", { name: /Хан Шатыр|Хан Шатыр/i })))
    || (await L.firstVisible(dlg.getByRole("button", { name: partRe(word(P.lang, "complaint.step2.approximate", "Примерное место", "Шамамен орны")) })));
  if (!place) return false; await place.click().catch(() => null); await L.sleep(1800);
  const box = await L.firstVisible(((await L.firstVisible(P.page.getByRole("dialog"))) || P.page).getByRole("textbox"));
  if (!box) return false; await box.fill("Аялдамада жарық жоқ, вечером на остановке темно").catch(() => null); await L.sleep(3000);
  return true;
}
async function wizardNext(P) {
  const dlg = (await L.firstVisible(P.page.getByRole("dialog"))) || P.page;
  return (await L.clickText(dlg, exactRe(word(P.lang, "complaint.wizard.next", "Далее", "Әрі қарай")), { wait: 3000 }))
    || (await L.clickText(dlg, exactRe(word(P.lang, "complaint.step3.send", "Отправить", "Жіберу")), { wait: 3000 }));
}
async function wizardSend(P) {
  let dlg = (await L.firstVisible(P.page.getByRole("dialog"))) || P.page;
  // «Об этом уже сообщили» → «У меня другое» → «Проверьте перед отправкой» → «Отправить» (новое обращение — экран успеха).
  if (await L.clickText(dlg, exactRe(word(P.lang, "complaint.step4.different", "У меня другое", "Менде басқа мәселе")), { wait: 2500 })) dlg = (await L.firstVisible(P.page.getByRole("dialog"))) || P.page;
  return (await L.clickText(dlg, exactRe(word(P.lang, "complaint.step3.send", "Отправить", "Жіберу")), { wait: 3500 }))
    || (await L.clickText(dlg, exactRe(word(P.lang, ["complaint.review.send", "complaint.send"], "Отправить", "Жіберу")), { wait: 3500 }))
    || (await L.clickText(dlg, partRe(word(P.lang, "complaint.step4.new", "Это другая проблема", "Бұл басқа мәселе")), { wait: 3500 }));
}
async function staffLogin(P) {
  if (!P.staff || !P.staff.user) return false;
  if (!(await header(P, "shell.staff.open", "Для сотрудников", "Қызметкерлерге", 1800)) && !(await L.headerClick(P.page, P.lang === "kk" ? /Қызметкерлерге/i : /Для сотрудников/i, { wait: 1800 }))) return false;
  return visible(P.page, "input[type=password]");
}
async function staffSubmit(P) {
  const user = await L.firstVisible(P.page.locator("input[autocomplete=username], input[name=username]"));
  const pass = await L.firstVisible(P.page.locator("input[type=password]"));
  if (!user || !pass) return false;
  await user.fill(P.staff.user); await pass.fill(P.staff.pass); await pass.press("Enter"); await L.sleep(2800);
  return !!(await L.firstVisible(P.page.getByRole("button", { name: /^(Выйти|Шығу)$/i })));
}
async function closeCabinet(P) {
  if (!(await L.clickText(P.page, /^(Закрыть кабинет|Кабинетті жабу)$/i))) await P.page.keyboard.press("Escape").catch(() => null);
  await L.sleep(900); return true;
}

// Потоки: новая страница (свой контекст) → шаги по очереди; шаг не открылся — дальше по потоку не идём.
// mode — вид при загрузке; route — подмена сети до загрузки; url — путь вместо главной; ctx — опции контекста.
const FLOWS = [
  { mode: "resident", steps: [
    { id: "r-map", owner: "R01+R07", name: "Карта · житель", go: async () => true, extra: ["press", "focus"] },
    { id: "r-card", owner: "R07", name: "Карточка места (житель)", go: (P) => openCard(P) } ] },
  { mode: "resident", steps: [{ id: "r-legend", owner: "R07+R01", name: "Легенда «?» открыта", go: async (P) => L.clickText(P.page, /Что значат цвета|Түстер нені білдіреді/i, { wait: 1500 }) }] },
  { mode: "resident", steps: [{ id: "r-avatar", owner: "R01", name: "Меню аватара", go: async (P) => { const a = await L.firstVisible(P.page.locator(".birge-avatar")); if (!a) return false; await a.click().catch(() => null); await L.sleep(900); return visible(P.page, "#birge-account"); } }] },
  { mode: "resident", steps: [{ id: "r-layer", owner: "R01", name: "Меню «Слой на карте»", go: async (P) => { const b = await L.firstVisible(P.page.locator("#birge-layer-btn")); if (!b) return false; await b.click().catch(() => null); await L.sleep(900); return visible(P.page, "#birge-layer"); } }] },
  { mode: "resident", steps: [{ id: "r-mine-empty", owner: "R09", name: "«Мои обращения» — пока пусто", go: (P) => header(P, "common.nav.mine", "Мои обращения", "Менің өтініштерім") }] },
  { mode: "resident", steps: [{ id: "r-nearby", owner: "R08+R06", name: "«Рядом»", go: (P) => section(P, "common.nav.nearby", "Рядом", "Маңайда") }] },
  { mode: "resident", steps: [{ id: "r-ideas", owner: "R06", name: "«Идеи»", go: (P) => section(P, "common.nav.ideas", "Идеи", "Идеялар") }] },
  { mode: "resident", steps: [{ id: "r-ask", owner: "R13", name: "«Вопрос акиму»", go: (P) => section(P, "common.nav.ask", "Вопрос акиму", "Әкімге сұрақ") }] },
  { mode: "resident", url: `/?report=${KHAN.id}`, steps: [{ id: "r-qr", owner: "R12+R07", name: "QR-паспорт места (/?report=)", go: async () => true }] },
  { mode: "resident", route: async (page) => page.route("**/api/civic/v2/heat**", (r) => r.abort("internetdisconnected")),
    steps: [{ id: "r-offline", owner: "R07+R01", name: "Ошибка: нет связи (тепловая карта)", go: async () => { await L.sleep(3000); return true; } }] },
  { mode: "resident", route: async (page) => page.route("**/api/civic/**", async (r) => { await new Promise((ok) => setTimeout(ok, 4500)); r.continue().catch(() => null); }),
    quick: true, steps: [{ id: "r-loading", owner: "R01+R07", name: "Загрузка (сеть медленная, 1,5 с)", go: async () => true }] },
  { mode: "resident", ctx: { reducedMotion: "reduce" }, steps: [{ id: "r-reduce", owner: "R01+R07", name: "«Уменьшить движение»: карточка места", go: (P) => openCard(P) }] },
  { mode: "akimat", steps: [
    { id: "a-map", owner: "R01+R07", name: "Карта · акимат", go: async () => true },
    { id: "a-card", owner: "R07", name: "Карточка места (акимат, без входа)", go: (P) => openCard(P) }] },
  { mode: "akimat", steps: [{ id: "a-day", owner: "R08", name: "«Картина дня»", go: (P) => section(P, "common.nav.day", "Картина дня", "Күн қорытындысы") }] },
  { mode: "akimat", steps: [{ id: "a-inbox", owner: "R09", name: "«Обращения» (без входа)", go: (P) => section(P, "common.nav.complaints", "Обращения", "Өтініштер") }] },
  { mode: "akimat", steps: [{ id: "a-projects", owner: "R06+R05", name: "«Проекты и идеи»", go: (P) => section(P, "common.nav.projects", "Проекты и идеи", "Жобалар мен идеялар") }] },
  { mode: "resident", url: `/civic/qr/print.html?ids=${KHAN.id}`, steps: [{ id: "a-qrprint", owner: "R12", name: "Лист QR-табличек (печать)", go: async () => true }] },
  // Меняют данные — в конце варианта.
  { mode: "resident", steps: [
    { id: "r-wiz1", owner: "R09", name: "Мастер: «Где проблема?»", go: (P) => startWizard(P) },
    { id: "r-wiz2", owner: "R09", name: "Мастер: текст и категория", go: (P) => wizardText(P) },
    { id: "r-wiz3", owner: "R09", name: "Мастер: «Уже сообщили» / проверка", go: (P) => wizardNext(P) },
    { id: "r-wiz4", owner: "R09", name: "Мастер: отправлено", go: (P) => wizardSend(P) },
    { id: "r-mine", owner: "R09", name: "«Мои обращения» — после отправки", go: async (P) => { await P.page.keyboard.press("Escape").catch(() => null); await L.sleep(600); return header(P, "common.nav.mine", "Мои обращения", "Менің өтініштерім"); } }] },
  { mode: "akimat", steps: [
    { id: "a-login", owner: "R01+R12", name: "Вход «Для сотрудников»", go: (P) => staffLogin(P) },
    { id: "a-cabinet", owner: "R12", name: "Кабинет сотрудника", go: (P) => staffSubmit(P) },
    { id: "a-staff-card", owner: "R07", name: "Карточка места (сотрудник)", go: async (P) => (await closeCabinet(P)) && openCard(P) },
    { id: "a-fixform", owner: "R09+R07", name: "Форма «что сделали»", go: async (P) => {
      const card = await L.firstVisible(P.page.locator(".r07-card")); if (!card) return false;
      await L.clickText(card, partRe(word(P.lang, ["target.take", "heat.take"], "Взять в работу", "Жұмысқа алу")), { wait: 2000 });
      const c2 = (await L.firstVisible(P.page.locator(".r07-card"))) || P.page;
      if (!(await L.clickText(c2, partRe(word(P.lang, ["target.mark_fixed", "heat.mark_fixed"], "Отметить исправленным", "Түзетілді деп белгілеу")), { wait: 2000 }))) return false;
      return visible(P.page, ".r07-fixform, input[name=what_done]"); } }] },
];

// ------------------------------------------------------------------------------------------------ прогон
async function runVariant(browser, size, lang) {
  const tag = `${size[0]}-${lang}`, dir = path.join(OUT, tag);
  fs.mkdirSync(dir, { recursive: true });
  const server = await L.startServer(ROOT);
  const out = {};
  try {
    for (const flow of FLOWS) {
      if (ONLY && !flow.steps.some((s) => ONLY.has(s.id))) continue;
      const mobile = size[0] < 761;
      const ctx = await browser.newContext({ viewport: { width: size[0], height: size[1] }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1, locale: lang === "kk" ? "kk-KZ" : "ru-RU", ...(flow.ctx || {}) });
      await ctx.addInitScript(([l, m]) => { try { if (!sessionStorage.getItem("r10")) { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); sessionStorage.setItem("r10", "1"); } } catch (e) { /* пусто */ } }, [lang, flow.mode]);
      await L.glassMode(ctx, GLASS);
      const page = await ctx.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(e.message.slice(0, 140)));
      const P = { page, lang, size, staff: server.staff, base: server.base };
      try {
        if (flow.route) await flow.route(page);
        await page.goto(new URL(flow.url || "/", server.base).href, { waitUntil: flow.quick ? "domcontentloaded" : "load", timeout: 45000 }).catch(() => null);
        if (flow.quick) await L.sleep(1500);
        else { await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 40, null, { timeout: 40000 }).catch(() => null); await L.sleep(3500); }
        let alive = true;
        for (const st of flow.steps) {
          if (!alive) { out[st.id] = { ...meta(st), reached: false, why: "предыдущий шаг потока не открылся" }; continue; }
          const ok = await st.go(P).catch((e) => { errors.push("шаг: " + String(e.message).slice(0, 120)); return false; });
          if (!ok) { alive = false; out[st.id] = { ...meta(st), reached: false, why: "состояние не открылось", shot: await shot(page, dir, st.id + "-not") }; continue; }
          await L.sleep(1200);
          const file = await shot(page, dir, st.id);
          const design = await page.evaluate(DESIGN).catch((e) => ({ error: String(e.message).slice(0, 200) }));
          const ui = await uiAudit(page).catch((e) => ({ error: String(e.message).slice(0, 200) }));
          const rec = { ...meta(st), reached: true, shot: file, design, ui, glass_seen: await L.glassSeen(page) };
          const ex = [].concat(st.extra || []);
          if (ex.includes("press")) rec.press = await pressCheck(page, partRe(word(lang, "complaint.start.button", "Сообщить о проблеме", "Мәселе туралы хабарлау"))).catch(() => null);
          if (ex.includes("focus")) rec.focus = await focusCheck(page).catch(() => null);
          out[st.id] = rec;
          console.log(`${tag} ${st.id.padEnd(13)} ${summary(rec)}`);
        }
      } finally { out._errors = (out._errors || []).concat(errors.slice(0, 5)); await ctx.close(); }
    }
  } finally { await server.stop(); }
  return out;
}
const meta = (st) => ({ id: st.id, name: st.name, owner: st.owner });
const shot = (page, dir, id) => page.screenshot({ path: path.join(dir, id + ".jpg"), type: "jpeg", quality: 72 }).then(() => path.basename(dir) + "/" + id + ".jpg", () => null);
// Краткая строка по экрану: число замечаний по пунктам чек-листа.
function points(rec) {
  const p = {};
  const d = rec.design || {}, u = rec.ui || {};
  for (const o of Object.values(d.owners || {})) for (const [k, v] of Object.entries(o)) p[k] = (p[k] || 0) + v.length;
  if (u.fonts && u.fonts.length) p["3 типографика"] = (p["3 типографика"] || 0) + u.fonts.length;
  if (u.taps && u.taps.length) p["10 нажатия"] = (p["10 нажатия"] || 0) + u.taps.length;
  if (u.contrast && u.contrast.length) p["4 цвет"] = (p["4 цвет"] || 0) + u.contrast.length;
  if (u.keys && u.keys.length) p["11 тексты"] = (p["11 тексты"] || 0) + u.keys.length;
  if (u.cut && u.cut.length) p["3 типографика"] = (p["3 типографика"] || 0) + u.cut.length;
  if (rec.focus && rec.focus.without && rec.focus.without.length) p["10 нажатия"] = (p["10 нажатия"] || 0) + rec.focus.without.length;
  if (rec.press && (rec.press.feedback === false || rec.press.jumps)) p["10 нажатия"] = (p["10 нажатия"] || 0) + 1;
  return p;
}
const summary = (rec) => { const p = points(rec); const n = Object.values(p).reduce((a, b) => a + b, 0);
  return n ? `${n} замечаний: ` + Object.entries(p).map(([k, v]) => `${k.split(" ")[0]}×${v}`).join(" ") : "чисто"; };

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const variants = {};
  try {
    for (const size of SIZES) for (const lang of LANGS) variants[`${size[0]}-${lang}`] = await runVariant(browser, size, lang);
  } finally { await browser.close(); }
  const sha = L.buildSha(ROOT);
  const meta0 = { root: ROOT, sha, glass: GLASS || "auto", when: new Date().toISOString(), sizes: SIZES.map((s) => s.join("x")), langs: LANGS, machine: L.machine ? L.machine() : null };
  fs.writeFileSync(path.join(OUT, "BOOK.json"), JSON.stringify({ meta: meta0, variants }, null, 1));
  // BOOK.md: экраны × варианты — открылось ли и сколько замечаний; замечания по ролям.
  const ids = []; for (const f of FLOWS) for (const s of f.steps) if (!ONLY || ONLY.has(s.id)) ids.push(s);
  const tags = Object.keys(variants);
  const md = [`# R10 · книга экранов · ${sha}`, "", "```", JSON.stringify(meta0), "```", "",
    "Чек-лист DESIGN_MARATHON (12 пунктов): числа — замечания автоматического замера (1 иерархия, 2 сетка, 3 типографика, 4 цвет, 6 глубина, 7 движение, 10 нажатия, 11 тексты); «—» — состояние не открылось.", "",
    `| Экран | Роль | ${tags.join(" | ")} |`, `|---|---|${tags.map(() => "---").join("|")}|`];
  for (const s of ids) md.push(`| ${s.name} (\`${s.id}\`) | ${s.owner} | ${tags.map((t) => { const r = variants[t][s.id]; if (!r) return ""; if (!r.reached) return "—"; const p = points(r); const n = Object.values(p).reduce((a, b) => a + b, 0); return n ? `${n}: ${Object.entries(p).map(([k, v]) => k.split(" ")[0] + "×" + v).join(" ")}` : "чисто"; }).join(" | ")} |`);
  const byOwner = {};
  for (const t of tags) for (const s of ids) { const r = variants[t][s.id]; if (!r || !r.reached) continue;
    for (const [o, pts] of Object.entries((r.design && r.design.owners) || {})) for (const [k, list] of Object.entries(pts)) for (const w of list) {
      const key = `${k} · ${w}`; ((byOwner[o] = byOwner[o] || {})[key] = byOwner[o][key] || new Set()).add(`${t} ${s.id}`); } }
  md.push("", "## Замечания по ролям (автоматически; повторяющиеся — один раз, со списком экранов)", "");
  for (const [o, items] of Object.entries(byOwner).sort()) {
    md.push(`### ${o}`, "");
    for (const [k, where] of Object.entries(items).sort()) md.push(`- ${k} — ${[...where].slice(0, 6).join(", ")}${where.size > 6 ? ` и ещё ${where.size - 6}` : ""}`);
    md.push("");
  }
  fs.writeFileSync(path.join(OUT, "BOOK.md"), md.join("\n") + "\n");
  console.log("ГОТОВО →", OUT);
})().catch((e) => { console.error(e); process.exit(2); });
