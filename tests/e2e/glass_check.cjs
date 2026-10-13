#!/usr/bin/env node
// R10 · раунд 14 · стекло «Apple Liquid Glass» (владелец 12 окт; правила — R11 GLASS.md, классы .bk-glass ui-kit).
// Что проверяется (нет стекла в сборке → ЖДЁТ):
//   1. Где стекло: backdrop-filter только у шапки, панелей, меню, кнопок карты, легенды и шторки — НЕ у значков карты,
//      не у полей и форм (мастер жалобы), не у главных кнопок и тостов; непрозрачность белого (для сведения: GLASS.md —
//      панели 80 %, кнопки 62 %; владелец — 72–80 % / 55–65 %).
//   2. Запасной вид: в CSS есть @media (prefers-reduced-transparency: reduce) и @supports not (backdrop-filter); в браузере —
//      при «уменьшить прозрачность» (эмуляция) и при html.bk-glass-off все .bk-glass непрозрачные и без размытия;
//      автовыключатель R01 (GLASS.md R01 №8: < 30 к/с → html.bk-glass-off один раз) — для сведения.
//   3. Контраст текста на стекле ≥ 4.5:1 (крупный ≥ 3:1) «на любом фоне карты»: под стекло подкладывается фон (слой в карте
//      и фон родителя стекла) — карта как есть, тёмно-зелёный, синий, красный (строго), чёрный и полосы (предельные →
//      СМОТРЕТЬ); текст на стекле на миг прозрачный — снимок — по пикселям под каждой надписью худший фон (5-й или 95-й
//      процентиль яркости) и контраст с настоящим цветом текста. Состояния: карта, карточка места, меню аватара, лист
//      раздела («Рядом» / «Картина дня»), «Мои обращения»; в мастере жалобы — только «форма без стекла».
//      Автовыключатель R01 на время замера контраста снимается (иначе в облаке стекла не видно).
//   4. Плавность карты (FPS): сдвиг и перелёт, без панели и с открытой карточкой, 1366 и 1024 — со стеклом и с
//      html.bk-glass-off на той же сборке (GLASS.md §5.3: падение > 20 % или < 30 к/с → R01 №8); с --control <сборка> —
//      ещё и другая сборка на этой машине. Программный WebGL (облако, < 10 к/с везде) — только ИНФО: мерить на ноутбуке.
//
//   NODE_PATH="$(npm root -g)" node tests/e2e/glass_check.cjs --root <сборка> --out <папка> [--sizes 1366x768,1024x768]
//        [--langs ru,kk] [--control <сборка без стекла>] [--fps-repeat 2] [--no-fps | --fps-only] [--force]
//        [--inject-css <файл>] [--inject-js <файл>]   (пробное стекло поверх сборки — самопроверка, не приёмка)
// Итог: <out>/GLASS.json, GLASS.md, кадры; код возврата 1 — при FAIL.
"use strict";
const fs = require("fs"), path = require("path"), os = require("os");
const { chromium } = require("playwright");
const L = require("./r10_lib.cjs");

const args = L.parseArgs(process.argv.slice(2));
const ROOT = path.resolve(String(args.root || path.join(__dirname, "../..")));
const OUT = path.resolve(String(args.out || path.join(os.tmpdir(), "r10-glass")));
const SIZES = String(args.sizes || "1366x768,1024x768").split(",").map((s) => s.split("x").map(Number));
const LANGS = String(args.langs || "ru,kk").split(",");
const CONTROL = args.control ? path.resolve(String(args.control)) : null;
// --inject-css <файл> — пробное стекло поверх сборки (самопроверка механики до поставки R11/R01; не приёмка сборки).
const INJECT = args["inject-css"] ? fs.readFileSync(path.resolve(String(args["inject-css"])), "utf8") : null;
const INJECT_JS = args["inject-js"] ? fs.readFileSync(path.resolve(String(args["inject-js"])), "utf8") : null;
const FPS_REPEAT = Math.max(1, Number(args["fps-repeat"] || 2));
const NO_FPS = !!args["no-fps"];
const FPS_ONLY = !!args["fps-only"];  // только плавность (отдельный прогон без другой нагрузки на машине)
const DICT = { ru: L.loadDict(ROOT, "ru"), kk: L.loadDict(ROOT, "kk") };
const word = (lang, key, ru, kk) => L.T(DICT[lang], key, lang === "kk" ? kk : ru);
const exactRe = (s) => new RegExp("^\\s*" + L.esc(s) + "\\s*$", "i");
const KHAN = [71.406553, 51.131155];
const results = [];
const add = (item, scope, name, status, detail, shot) => {
  results.push({ item, scope, name, status, detail: detail ?? null, shot: shot || null });
  console.log(`${status.padEnd(8)} ${item} ${scope} ${name}` + (detail ? " — " + JSON.stringify(detail).slice(0, 260) : ""));
};
const st = (ok) => (ok === null ? "NOT_RUN" : ok ? "PASS" : "FAIL");

// ------------------------------------------------------------------------------------------------ 1. CSS сборки
function cssFiles(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (!/^(vendor|node_modules|tests?)$/.test(e.name)) cssFiles(p, out); }
    else if (e.name.endsWith(".css")) out.push(p);
  }
  return out;
}
function staticCss() {
  const files = fs.existsSync(path.join(ROOT, "web")) ? cssFiles(path.join(ROOT, "web")) : [];
  const glass = [], reduced = [], nosupport = [];
  for (const f of files) {
    const s = fs.readFileSync(f, "utf8"), rel = path.relative(ROOT, f);
    if (/backdrop-filter\s*:|\.bk-glass\b/.test(s)) glass.push(rel);
    if (/@media[^{]*prefers-reduced-transparency\s*:\s*reduce/.test(s)) reduced.push(rel);
    if (/@supports\s+not\s*\(\s*\(?\s*(-webkit-)?backdrop-filter/.test(s)) nosupport.push(rel);
  }
  return { glass, reduced, nosupport };
}

// ------------------------------------------------------------------------------------------------ в странице
// Стеклянные поверхности и надписи на них. Надписи помечаются data-r10t=<n> (для снимка без текста).
const SCAN = () => {
  const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0.05 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; };
  const glassOf = (e) => { const s = getComputedStyle(e); const f = s.backdropFilter || s.webkitBackdropFilter || "none"; return f && f !== "none" ? f : null; };
  const rgba = (c) => { const m = String(c).match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; };
  const name = (e) => (e.getAttribute("aria-label") || e.innerText || e.className || e.tagName).toString().trim().replace(/\s+/g, " ").slice(0, 40);
  const surfaces = [];
  for (const e of document.querySelectorAll("body *")) {
    const f = glassOf(e); if (!f || !vis(e)) continue;
    const r = e.getBoundingClientRect(), bg = rgba(getComputedStyle(e).backgroundColor);
    surfaces.push({ name: name(e), tag: e.tagName.toLowerCase(), cls: String(e.className || "").slice(0, 60), filter: f, alpha: bg ? bg[3] : null,
      w: Math.round(r.width), h: Math.round(r.height), text_len: (e.innerText || "").trim().length,
      on_marker: !!e.closest(".maplibregl-marker, .r07-badge, .b3d-labels"), in_form: /^(INPUT|TEXTAREA|SELECT)$/.test(e.tagName) || !!e.closest("input, textarea, select"),
      primary: !!e.closest(".bk-btn--primary, .bc-fab, .bk-toast"),
      // Стекло закрыто своим непрозрачным фоном модуля (GLASS.md §4: «свои фоны у корня панели убрать»): доля площади.
      covered: (() => { let best = null; for (const d of e.querySelectorAll("*")) { const q = d.getBoundingClientRect(); if (q.width * q.height < r.width * r.height * 0.5) continue;
        const a = rgba(getComputedStyle(d).backgroundColor); if (a && a[3] >= 0.95) { const k = Math.round((q.width * q.height) / (r.width * r.height) * 100) / 100; if (!best || k > best.share) best = { share: Math.min(1, k), el: (d.id ? "#" + d.id : "") + "." + String(d.className).trim().split(/\s+/).slice(0, 2).join(".") }; } }
        return best; })() });
  }
  document.querySelectorAll("[data-r10t]").forEach((e) => e.removeAttribute("data-r10t"));
  const texts = []; let n = 0;
  for (const e of document.querySelectorAll("body *")) {
    const own = [...e.childNodes].filter((x) => x.nodeType === 3).map((x) => x.textContent).join("").trim();
    if (own.length < 2 || !vis(e) || e.closest("svg")) continue;
    let g = null; for (let p = e; p && p !== document.body; p = p.parentElement) if (glassOf(p)) { g = p; break; }
    if (!g) continue;
    // Рамка самих букв (узлы текста), без значков рядом в том же элементе («✓ исправлено»): иначе значок попадёт в «фон».
    const rg = document.createRange(); let r = null;
    for (const x of e.childNodes) if (x.nodeType === 3 && x.textContent.trim()) { rg.selectNodeContents(x); const q = rg.getBoundingClientRect();
      if (q.width > 0 && q.height > 0) r = r ? { left: Math.min(r.left, q.left), top: Math.min(r.top, q.top), right: Math.max(r.right, q.right), bottom: Math.max(r.bottom, q.bottom) } : { left: q.left, top: q.top, right: q.right, bottom: q.bottom }; }
    if (!r) continue;
    r.width = r.right - r.left; r.height = r.bottom - r.top;
    const cs = getComputedStyle(e), c = rgba(cs.color);
    // Надпись не обрезана прокруткой: ≥ 60 % её рамки внутри всех предков с overflow ≠ visible и внутри самого стекла;
    // не гаснет (прозрачность всех предков ≈ 1 — плашка карты гаснет через 6 с).
    let cl = { l: r.left, t: r.top, r: r.right, b: r.bottom }, fade = 1;
    for (let p = e; p && p !== document.documentElement; p = p.parentElement) {
      const ps = getComputedStyle(p); fade *= Number(ps.opacity);
      if (p === g || ps.overflow !== "visible" || ps.overflowX !== "visible" || ps.overflowY !== "visible") {
        const q = p.getBoundingClientRect(); cl = { l: Math.max(cl.l, q.left), t: Math.max(cl.t, q.top), r: Math.min(cl.r, q.right), b: Math.min(cl.b, q.bottom) };
      }
    }
    const shown = Math.max(0, cl.r - cl.l) * Math.max(0, cl.b - cl.t) / Math.max(1, r.width * r.height);
    if (shown < 0.6 || fade < 0.98) continue;
    // Надпись открыта целиком (не закрыта кнопкой, другой панелью): сетка 5 × 3 точек в видимой части — везде она сама.
    let open = true;
    for (let i = 0; i < 5 && open; i++) for (let j = 0; j < 3 && open; j++) {
      const hx = Math.min(Math.max(cl.l + (cl.r - cl.l) * (0.04 + 0.23 * i), 0), innerWidth - 1), hy = Math.min(Math.max(cl.t + (cl.b - cl.t) * (0.08 + 0.42 * j), 0), innerHeight - 1);
      const hit = document.elementFromPoint(hx, hy);
      if (!hit || !(hit === e || e.contains(hit) || hit.contains(e))) open = false;
    }
    if (!open) continue;
    e.setAttribute("data-r10t", String(n));
    texts.push({ n: n++, text: own.slice(0, 40), x: cl.l, y: cl.t, w: cl.r - cl.l, h: cl.b - cl.t, color: c, fs: parseFloat(cs.fontSize), bold: Number(cs.fontWeight) >= 600, glass: name(g) });
  }
  return { surfaces, texts };
};

// Худший фон под каждой надписью: снимок без текста → пиксели в рамке надписи (в отдельной пустой странице, без CSP сайта).
async function pixelContrast(ctx, png, texts, dpr) {
  const p = await ctx.newPage();
  try {
    await p.setContent("<canvas id=c></canvas>");
    return await p.evaluate(async ([b64, texts, dpr]) => {
      const img = new Image(); img.src = "data:image/png;base64," + b64; await img.decode();
      const c = document.getElementById("c"); c.width = img.width; c.height = img.height;
      const g = c.getContext("2d"); g.drawImage(img, 0, 0);
      const lin = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
      const lum = (r, gg, b) => 0.2126 * lin(r) + 0.7152 * lin(gg) + 0.0722 * lin(b);
      return texts.map((t) => {
        const x = Math.max(0, Math.round(t.x * dpr) + 1), y = Math.max(0, Math.round(t.y * dpr) + 1);
        const w = Math.max(1, Math.min(img.width - x, Math.round(t.w * dpr) - 2)), h = Math.max(1, Math.min(img.height - y, Math.round(t.h * dpr) - 2));
        const d = g.getImageData(x, y, w, h).data, ls = [];
        for (let i = 0; i < d.length; i += 4) ls.push(lum(d[i], d[i + 1], d[i + 2]));
        ls.sort((a, b) => a - b);
        const p5 = ls[Math.floor(ls.length * 0.05)], p95 = ls[Math.floor(ls.length * 0.95)], mean = ls.reduce((a, b) => a + b, 0) / ls.length;
        const col = t.color || [0, 0, 0, 1], lt = lum(col[0], col[1], col[2]);
        const lb = lt < mean ? p5 : p95;  // тёмный текст — худший самый тёмный фон, светлый — самый светлый
        const ratio = (Math.max(lt, lb) + 0.05) / (Math.min(lt, lb) + 0.05);
        const need = t.fs >= 24 || (t.bold && t.fs >= 18.66) ? 3 : 4.5;
        return { n: t.n, text: t.text, glass: t.glass, ratio: Math.round(ratio * 100) / 100, need, ok: ratio >= need };
      });
    }, [png.toString("base64"), texts, dpr]);
  } finally { await p.close(); }
}

// Фон под стеклом: слой поверх холста карты внутри .maplibregl-map (панели и шапка — над ним, их стекло размывает его).
// Строгие (FAIL): карта как есть, светлая подложка, пёстрый фон (дизайн-марафон: «светлый и пёстрый фон карты») и насыщенные
// цвета карты — парк, вода, «много жалоб». Предельные (СМОТРЕТЬ): чёрный и
// полосы чёрное/белое — так тёмной карта не бывает, но видно запас контраста.
const BACKGROUNDS = {
  "карта": null,
  // Светлая подложка (земля, дороги OSM): худший случай для белого и светлого текста на стекле.
  "светлый": "#f2efe9",
  // Пёстрый фон карты: парк, вода, дороги, жилые кварталы и цвета жалоб мелкими пятнами (как карта города в 3D/подложке).
  "пёстрый": "repeating-linear-gradient(30deg,#c8e6c9 0 14px,#a5d6f7 14px 26px,#ffffff 26px 34px,#e0dccf 34px 52px,#fac775 52px 60px,#e24b4a 60px 66px,#2e7d32 66px 80px,#90a4ae 80px 92px),repeating-linear-gradient(120deg,rgba(0,0,0,.25) 0 6px,rgba(255,255,255,0) 6px 40px)",
  "тёмно-зелёный": "#1b5e20",
  "синий": "#0d47a1",
  "красный": "#b71c1c",
  "чёрный": "#000",
  "полосы": "repeating-linear-gradient(45deg,#000 0 10px,#fff 10px 20px)",
};
const EXTREME = new Set(["чёрный", "полосы"]);
// Фон кладётся и в карту (слой над холстом), и родителю каждого стекла (если стекло не над картой — например, панель
// рядом с картой): тогда под стеклом гарантированно этот фон, где бы ни стояла панель.
const setBackground = (page, bg) => page.evaluate((bg) => {
  let d = document.getElementById("r10-stress");
  document.querySelectorAll("[data-r10bg]").forEach((p) => { p.style.background = p.getAttribute("data-r10bg"); p.removeAttribute("data-r10bg"); });
  if (!bg) { if (d) d.remove(); return true; }
  const m = document.querySelector(".maplibregl-map"); if (!m) return false;
  if (!d) { d = document.createElement("div"); d.id = "r10-stress"; d.style.cssText = "position:absolute;inset:0;z-index:1;pointer-events:none"; m.appendChild(d); }
  d.style.background = bg;
  const glassOf = (e) => { const s = getComputedStyle(e); const f = s.backdropFilter || s.webkitBackdropFilter || "none"; return f && f !== "none"; };
  for (const e of document.querySelectorAll("body *")) {
    if (!glassOf(e) || e.id === "r10-stress") continue;
    let nested = false; for (let q = e.parentElement; q && q !== document.documentElement; q = q.parentElement) if (glassOf(q)) { nested = true; break; }
    if (nested) continue;  // стекло внутри стекла: под ним — внешнее стекло, фон кладём только под внешнее
    const p = e.parentElement;
    if (!p || p.hasAttribute("data-r10bg") || p.contains(m) || m.contains(p)) continue;  // карта — уже слоем
    p.setAttribute("data-r10bg", p.style.background || ""); p.style.setProperty("background", bg, "important");
  }
  return true;
}, bg);

// Формы без стекла (GLASS.md §2 «Нет»): у формы (form, шаг мастера, форма сотрудника) между ней и ближайшим стеклом выше
// должна быть непрозрачная подложка (альфа ≥ 0.95) — иначе форма лежит на стекле.
const FORMSCAN = (withDialogs = false) => {
  const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none"; };
  const glassOf = (e) => { const s = getComputedStyle(e); const f = s.backdropFilter || s.webkitBackdropFilter || "none"; return f && f !== "none"; };
  const alpha = (e) => { const m = String(getComputedStyle(e).backgroundColor).match(/rgba?\(([^)]+)\)/); if (!m) return 0; const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return v.length > 3 ? v[3] : 1; };
  // Форма ввода — form / шаг мастера / форма сотрудника / диалог с текстовым полем, textarea или кнопкой отправки; одиночное
  // поле-фильтр (район, дата, поиск) — форма из одного поля: непрозрачным должно быть само поле (ui-kit .bk-glass input).
  const forms = new Set(), fields = [];
  const isInput = (c) => !!c.querySelector("textarea, input[type=text], input:not([type]), input[type=email], input[type=tel], input[type=file], input[type=password], button[type=submit]");
  for (const f of document.querySelectorAll("input:not([type=hidden]), textarea, select")) {
    if (!vis(f)) continue;
    const c = f.closest("form, [data-step], .r07-fixform, [role=dialog]");
    if (c && isInput(c)) forms.add(c); else fields.push(f);
  }
  // Шаг мастера — форма; «Мои обращения» R09 (.bc-panel[data-step="mine"]) — список на стекле, не форма (GLASS.md §4 R09).
  for (const c of document.querySelectorAll(withDialogs ? "[data-step], [role=dialog]" : "[data-step]"))
    if (vis(c) && c.getAttribute("data-step") !== "mine" && (withDialogs || isInput(c))) forms.add(c);
  const single = fields.map((f) => {
    let glass = null; for (let p = f; p && p !== document.documentElement; p = p.parentElement) if (glassOf(p)) { glass = p; break; }
    return { form: "поле " + (f.name || f.type || f.tagName.toLowerCase()), on_glass: !!glass && alpha(f) < 0.95, glass: glass ? (glass.id ? "#" + glass.id : glass.tagName.toLowerCase()) : null, opaque: alpha(f) >= 0.95 ? "само поле" : null, fields: 1 };
  });
  return single.concat([...forms].filter(Boolean).map((c) => {
    let opaque = null, glass = null;
    for (let p = c; p && p !== document.documentElement; p = p.parentElement) {
      if (glassOf(p)) { glass = p; break; }
      if (alpha(p) >= 0.95) { opaque = p; break; }
    }
    const nm = (e) => e ? (e.id ? "#" + e.id : "") + (e.className ? "." + String(e.className).trim().split(/\s+/).slice(0, 2).join(".") : "") || e.tagName.toLowerCase() : null;
    return { form: nm(c), on_glass: !!glass && !opaque, glass: nm(glass), opaque: nm(opaque), fields: c.querySelectorAll("input, textarea, select").length };
  }));
};

// Запасной вид в браузере: все .bk-glass / .bk-glass--control (по классу) — без размытия и с непрозрачным фоном.
const SOLIDSCAN = () => {
  const out = [];
  for (const e of document.querySelectorAll(".bk-glass, .bk-glass--control")) {
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    if (!(r.width > 0 && r.height > 0 && s.display !== "none" && s.visibility !== "hidden")) continue;
    const m = String(s.backgroundColor).match(/rgba?\(([^)]+)\)/), v = m ? m[1].split(/[ ,/]+/).filter(Boolean).map(Number) : [0, 0, 0, 0];
    const f = s.backdropFilter || s.webkitBackdropFilter || "none";
    // Плоская кнопка внутри стеклянной полосы (прозрачная, без размытия: «?» в строке легенды) — непрозрачна, если
    // непрозрачна полоса вокруг.
    let solid = (f === "none" || !f) && (v.length > 3 ? v[3] : 1) >= 0.99;
    if (!solid && (f === "none" || !f) && (v.length > 3 ? v[3] : 1) === 0) {
      const outer = e.parentElement && e.parentElement.closest(".bk-glass, .bk-glass--control");
      if (outer) { const os = getComputedStyle(outer), m2 = String(os.backgroundColor).match(/rgba?\(([^)]+)\)/), w = m2 ? m2[1].split(/[ ,/]+/).filter(Boolean).map(Number) : [0, 0, 0, 0];
        solid = (os.backdropFilter === "none" || !os.backdropFilter) && (w.length > 3 ? w[3] : 1) >= 0.99; }
    }
    out.push({ cls: String(e.className).slice(0, 50), filter: f, alpha: v.length > 3 ? v[3] : 1, solid });
  }
  return out;
};

const SMOOTH = async (stop) => {
  // eslint-disable-next-line no-undef
  const m = typeof map !== "undefined" && map && map.getStyle ? map : null;
  if (!m) return null;
  const wait = (ms) => new Promise((ok) => setTimeout(ok, ms));
  const frames = async (start, ms) => { const d = []; let last = performance.now(); const t0 = last; let run = true;
    const loop = (t) => { d.push(t - last); last = t; if (run) requestAnimationFrame(loop); };
    requestAnimationFrame(loop); start(); await wait(ms); run = false; await wait(50);
    const v = d.slice(1).sort((a, b) => a - b);
    return { fps: Math.round((v.length * 1000) / (performance.now() - t0)), p95_ms: Math.round(v[Math.floor(v.length * 0.95)] || 0), over50: v.filter((x) => x > 50).length }; };
  m.jumpTo({ center: stop, zoom: 15, pitch: 0, bearing: 0 }); await wait(2000);
  const pan = await frames(() => m.easeTo({ center: [stop[0] + 0.02, stop[1] + 0.006], duration: 2000 }), 2300);
  m.jumpTo({ center: stop, zoom: 12 }); await wait(1500);
  const fly = await frames(() => m.flyTo({ center: stop, zoom: 15, duration: 2000 }), 2300);
  return { pan, fly };
};

// glass: "keep" — снимать автовыключатель R01 (html.bk-glass-off) на время замера, "off" — выключить стекло классом,
// "auto" — как есть (замер автовыключателя); reduced — эмуляция «уменьшить прозрачность» системы.
async function openPage(browser, [w, h], lang, mode, { glass = "keep", reduced = false } = {}) {
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1 });
  await ctx.addInitScript(([l, m]) => { try { if (!sessionStorage.getItem("r10")) { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); sessionStorage.setItem("r10", "1"); } } catch (e) { /* пусто */ } }, [lang, mode]);
  if (INJECT) await ctx.addInitScript((css) => { const add = () => { const s = document.createElement("style"); s.id = "r10-inject"; s.textContent = css; document.head.appendChild(s); };
    if (document.head) add(); else document.addEventListener("DOMContentLoaded", add); }, INJECT);
  if (INJECT_JS) await ctx.addInitScript(INJECT_JS);
  await ctx.addInitScript((g) => {
    window.__r10_off = [];
    // Скрипт идёт до появления <html> — ждём его, затем держим класс (off) или снимаем выключатель R01 (keep).
    const watch = (h) => {
      if (g === "off") h.classList.add("bk-glass-off");
      new MutationObserver(() => {
        const on = h.classList.contains("bk-glass-off");
        if (g !== "off" && on) window.__r10_off.push(Math.round(performance.now()));
        if (g === "keep" && on) h.classList.remove("bk-glass-off");
        if (g === "off" && !on) h.classList.add("bk-glass-off");
      }).observe(h, { attributes: true, attributeFilter: ["class"] });
    };
    if (document.documentElement) watch(document.documentElement);
    else { const mo = new MutationObserver(() => { if (document.documentElement) { mo.disconnect(); watch(document.documentElement); } }); mo.observe(document, { childList: true }); }
  }, glass);
  const page = await ctx.newPage();
  if (reduced) {
    const cdp = await ctx.newCDPSession(page);
    await cdp.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-transparency", value: "reduce" }] }).catch(() => null);
  }
  return { ctx, page };
}
async function settle(page) {
  await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 50, null, { timeout: 40000 }).catch(() => null);
  await L.sleep(3500);
}

const shotOf = (page, n) => page.screenshot({ path: path.join(OUT, n.replace(/\s+/g, "_") + ".jpg"), type: "jpeg", quality: 70 }).then(() => n.replace(/\s+/g, "_") + ".jpg", () => null);

async function contrastRun(browser, base, size, lang, mode) {
  const tag = `${size[0]}-${lang}-${mode}`;
  const { ctx, page } = await openPage(browser, size, lang, mode);
  try {
    await page.goto(base); await settle(page);
    const states = [["карта", async () => true],
      ["карточка места", async () => { const p = await L.showPoint(page, KHAN, 17); if (p) await L.tap(page, p.x, p.y); await L.sleep(2500); return !!(await L.firstVisible(page.locator(".r07-card"))); }],
      ["меню аватара", async () => { await page.keyboard.press("Escape").catch(() => null); await L.sleep(500); const a = await L.firstVisible(page.locator(".birge-avatar"));
        if (!a) return false; await a.click().catch(() => null); await L.sleep(700); return !!(await L.firstVisible(page.locator("#birge-account"))); }]];
    // Разделы — с чистой страницы: лист раздела (стекло R01 №6) и «Мои обращения» (R09 на стекле); мастер — только «форма без стекла».
    const fresh = async () => { await page.goto(base); await settle(page); };
    const menuRe = exactRe(word(lang, "common.nav.menu", "Меню", "Мәзір"));
    const section = (key, ru, kk) => async () => { await fresh(); return L.headerClick(page, exactRe(word(lang, key, ru, kk)), { wait: 2500, menuRe }); };
    if (mode === "akimat") states.push(["лист «Картина дня»", section("common.nav.day", "Картина дня", "Күн қорытындысы")]);
    else states.push(["лист «Рядом»", section("common.nav.nearby", "Рядом", "Маңайда")], ["«Мои обращения»", section("common.nav.mine", "Мои обращения", "Менің өтініштерім")],
      ["мастер жалобы", async () => { await fresh(); const b = await L.firstVisible(page.locator(".bc-fab").or(page.getByRole("button", { name: new RegExp(L.esc(word(lang, "complaint.start.button", "Сообщить о проблеме", "Мәселе туралы хабарлау")), "i") })));
        if (!b) return false; await b.click().catch(() => null); await L.sleep(1500); return true; }]);
    for (const [sname, enter] of states) {
      const ok = await enter();
      if (!ok) { add("G-3", tag, `${sname}: открыть`, "NOT_RUN", "состояние не открылось"); continue; }
      if (sname === "мастер жалобы") {
        // Шаг «Где проблема?» (диалог), затем «Примерное место» → шаг с текстом: везде форма без стекла.
        const forms = await page.evaluate(FORMSCAN, true);
        const shot1 = await shotOf(page, `${tag}-wizard-1`);
        const pt = await L.showPoint(page, KHAN, 17); if (pt) await L.tap(page, (pt.near || pt).x, (pt.near || pt).y); await L.sleep(2500);
        const dlg = await L.firstVisible(page.getByRole("dialog"));
        const approx = dlg && (await L.firstVisible(dlg.getByRole("button", { name: new RegExp(L.esc(word(lang, "complaint.step2.approximate", "Примерное место", "Шамамен орны")), "i") })));
        if (approx) { await approx.click().catch(() => null); await L.sleep(1500); }
        const forms2 = await page.evaluate(FORMSCAN, true), all = forms.concat(forms2), bad = all.filter((f) => f.on_glass);
        add("G-1", tag, "мастер жалобы (шаги «Где проблема?» и текст) — форма без стекла (между формой и стеклом непрозрачная подложка)", all.length ? st(bad.length === 0) : "NOT_RUN",
          { forms: all.length, text_step: !!approx, bad: bad.slice(0, 4), ok: all.filter((f) => !f.on_glass).slice(0, 4) }, (await shotOf(page, `${tag}-wizard-2`)) || shot1);
        continue;
      }
      await page.addStyleTag({ content: "*,*::before,*::after{transition:none!important;animation:none!important}" }).then((h) => h.evaluate((e) => { e.id = "r10-freeze"; })).catch(() => null);
      await L.sleep(200);
      const scan = await page.evaluate(SCAN);
      const covered = scan.surfaces.filter((x) => x.covered && x.covered.share >= 0.6);
      if (covered.length) add("G-1", tag, `${sname}: стекло закрыто своим непрозрачным фоном модуля (стекла не видно; GLASS.md §4 — свой фон убрать)`, "INFO",
        covered.slice(0, 5).map((x) => ({ glass: x.name, by: x.covered.el, share: x.covered.share })));
      if (sname !== "карта") {
        const forms = (await page.evaluate(FORMSCAN)).filter((f) => f.on_glass);
        if (forms.length) add("G-1", tag, `${sname}: поля и формы без стекла`, "FAIL", { bad: forms.slice(0, 4) });
      }
      if (sname === "карта") {
        // 1. Где стекло: не на значках карты, не у полей форм; непрозрачность (для сведения).
        const bad = scan.surfaces.filter((s) => s.on_marker || s.in_form || s.primary);
        add("G-1", tag, "стекло (backdrop-filter) только на шапке, панелях, меню, кнопках карты, легенде, шторке — не на значках карты, не в полях, не на главных кнопках и тостах",
          scan.surfaces.length ? st(bad.length === 0) : "NOT_RUN", { surfaces: scan.surfaces.length, bad: bad.slice(0, 6) });
        add("G-1", tag, "непрозрачность стекла: панели с текстом / мелкие кнопки (GLASS.md: 72–80 % / 55–65 %)", "INFO",
          scan.surfaces.map((s) => ({ name: s.name, alpha: s.alpha, w: s.w, h: s.h, text: s.text_len > 20 })).slice(0, 12));
      }
      if (!scan.texts.length) { add("G-3", tag, `${sname}: надписей на стекле нет`, "NOT_RUN", { surfaces: scan.surfaces.length }); continue; }
      const worst = {};
      for (const [bname, bg] of Object.entries(BACKGROUNDS)) {
        if (!(await setBackground(page, bg))) continue;
        await L.sleep(400);
        await page.addStyleTag({ content: "[data-r10t]{color:transparent!important;text-shadow:none!important;-webkit-text-fill-color:transparent!important}" }).then((h) => h.evaluate((e) => { e.id = "r10-hide"; }));
        await L.sleep(150);
        const png = await page.screenshot({ type: "png" });
        // Надписи, которые пропали за время замера (плашка погасла, панель закрылась), не считаются.
        const alive = new Set(await page.evaluate(() => [...document.querySelectorAll("[data-r10t]")].filter((e) => {
          const r = e.getBoundingClientRect(); let o = 1; for (let p = e; p && p !== document.documentElement; p = p.parentElement) { const s = getComputedStyle(p); o *= Number(s.opacity); if (s.visibility === "hidden" || s.display === "none") o = 0; }
          if (!(r.width > 0 && r.height > 0 && o >= 0.98)) return false;
          // И всё ещё открыта целиком (поверх могло выехать что-то после разметки — главная кнопка, тост).
          for (let i = 0; i < 5; i++) for (let j = 0; j < 3; j++) {
            const hx = Math.min(Math.max(r.left + r.width * (0.04 + 0.23 * i), 0), innerWidth - 1), hy = Math.min(Math.max(r.top + r.height * (0.08 + 0.42 * j), 0), innerHeight - 1);
            const hit = document.elementFromPoint(hx, hy); if (!hit || !(hit === e || e.contains(hit) || hit.contains(e))) return false; }
          return true; }).map((e) => Number(e.getAttribute("data-r10t")))));
        await page.evaluate(() => { const e = document.getElementById("r10-hide"); if (e) e.remove(); });
        const res = await pixelContrast(ctx, png, scan.texts.filter((t) => alive.has(t.n)), 1);
        const fails = res.filter((r) => !r.ok);
        worst[bname] = { min: Math.min(...res.map((r) => r.ratio)), fails: fails.length };
        add("G-3", tag, `${sname} · фон «${bname}»${EXTREME.has(bname) ? " (предельный)" : ""}: контраст текста на стекле ≥ 4.5:1 (крупный ≥ 3:1)`,
          !res.length ? "NOT_RUN" : fails.length === 0 ? "PASS" : EXTREME.has(bname) ? "СМОТРЕТЬ" : "FAIL",
          { texts: res.length, min: worst[bname].min, fails: fails.slice(0, 5).map((f) => `${f.ratio}:1 «${f.text}» (${f.glass})`) },
          bname === "полосы" || bname === "пёстрый" || fails.length ? await page.screenshot({ path: path.join(OUT, `${tag}-${sname.replace(/\s+/g, "_")}-${bname}.jpg`), type: "jpeg", quality: 70 }).then(() => `${tag}-${sname.replace(/\s+/g, "_")}-${bname}.jpg`, () => null) : null);
      }
      await setBackground(page, null);
      await page.evaluate(() => { const e = document.getElementById("r10-freeze"); if (e) e.remove(); }).catch(() => null);
    }
  } finally { await ctx.close(); }
}

// Перетаскивание карты мышью (как житель): счётчик кадров в странице, 40 шагов мыши за ~1,6 с по свободной части карты.
async function dragFps(page) {
  const at = await page.evaluate(() => { // eslint-disable-next-line no-undef
    const m = typeof map !== "undefined" && map && map.getCanvas ? map : null; if (!m) return null;
    const c = m.getCanvas(), r = c.getBoundingClientRect();
    for (const fx of [0.3, 0.2, 0.45]) { const x = r.left + r.width * fx, y = r.top + r.height * 0.55; if (document.elementFromPoint(x, y) === c) return { x, y }; }
    return null; });
  if (!at) return null;
  await page.evaluate(() => { window.__r10f = []; let last = performance.now(); window.__r10run = true;
    const loop = (t) => { window.__r10f.push(t - last); last = t; if (window.__r10run) requestAnimationFrame(loop); }; requestAnimationFrame(loop); });
  const t0 = Date.now();
  await page.mouse.move(at.x, at.y); await page.mouse.down();
  for (let i = 1; i <= 40; i++) { await page.mouse.move(at.x + i * 6, at.y + i * 2); await L.sleep(40); }
  await page.mouse.up();
  const ms = Date.now() - t0;
  const d = await page.evaluate(() => { window.__r10run = false; return window.__r10f.slice(1); });
  const v = d.slice().sort((a, b) => a - b);
  return { fps: Math.round((d.length * 1000) / ms), p95_ms: Math.round(v[Math.floor(v.length * 0.95)] || 0), over50: v.filter((x) => x > 50).length };
}

async function fpsRun(browser, base, size, label, glass) {
  const runs = [];
  for (let i = 0; i < FPS_REPEAT; i++) {
    const { ctx, page } = await openPage(browser, size, "ru", "resident", { glass });
    try {
      await page.goto(base); await settle(page);
      const plain = await page.evaluate(SMOOTH, KHAN).catch((e) => ({ error: String(e.message).slice(0, 120) }));
      if (plain && !plain.error) plain.drag = await dragFps(page).catch(() => null);
      const p = await L.showPoint(page, KHAN, 17); if (p) await L.tap(page, p.x, p.y); await L.sleep(2500);
      const panel = !!(await L.firstVisible(page.locator(".r07-card")));
      const withPanel = await page.evaluate(SMOOTH, KHAN).catch((e) => ({ error: String(e.message).slice(0, 120) }));
      if (withPanel && !withPanel.error) withPanel.drag = await dragFps(page).catch(() => null);
      const glassOn = await page.evaluate(() => !document.documentElement.classList.contains("bk-glass-off") && [...document.querySelectorAll("body *")].some((e) => { const f = getComputedStyle(e).backdropFilter; return f && f !== "none"; }));
      runs.push({ plain, panel, withPanel, glassOn });
    } finally { await ctx.close(); }
  }
  // Медиана по повторам (кадры/с).
  const med = (key, k) => { const v = runs.map((r) => r[key] && r[key][k] && r[key][k].fps).filter((x) => x); return v.length ? L.median(v) : null; };
  return { label, glass, size: size.join("x"), runs, fps: { plain: { pan: med("plain", "pan"), fly: med("plain", "fly"), drag: med("plain", "drag") }, withPanel: { pan: med("withPanel", "pan"), fly: med("withPanel", "fly"), drag: med("withPanel", "drag") } },
    panel: runs.some((r) => r.panel), glassOn: runs.some((r) => r.glassOn) };
}
// Итог по FPS: программный WebGL (обе < 10 к/с) — ИНФО; иначе падение > 20 % → FAIL; < 30 к/с со стеклом при ≥ 30 без него →
// FAIL (R01 №8: включить bk-glass-off); < 30 к/с и без стекла — СМОТРЕТЬ (машина слабая, стекло ни при чём).
function fpsVerdict(now, was) {
  if (!now || !was) return "INFO";
  if (now < 10 && was < 10) return "INFO";
  if (now / was < 0.8) return "FAIL";
  if (now < 30) return was >= 30 ? "FAIL" : "СМОТРЕТЬ";
  return "PASS";
}

// Запасной вид в браузере: «уменьшить прозрачность» (эмуляция) и html.bk-glass-off; автовыключатель R01 — для сведения.
async function fallbackRun(browser, base, size) {
  const tag = size.join("x");
  for (const [mname, opts] of [["«уменьшить прозрачность» (эмуляция)", { glass: "keep", reduced: true }], ["html.bk-glass-off", { glass: "off" }]]) {
    const { ctx, page } = await openPage(browser, size, "ru", "resident", opts);
    try {
      await page.goto(base); await settle(page);
      if (opts.reduced && !(await page.evaluate(() => matchMedia("(prefers-reduced-transparency: reduce)").matches))) { add("G-2", tag, `${mname}: все стеклянные элементы непрозрачные, без размытия`, "NOT_RUN", "браузер не эмулирует prefers-reduced-transparency"); continue; }
      const p = await L.showPoint(page, KHAN, 17); if (p) await L.tap(page, p.x, p.y); await L.sleep(2000);
      const els = await page.evaluate(SOLIDSCAN), bad = els.filter((e) => !e.solid);
      add("G-2", tag, `${mname}: все стеклянные элементы (.bk-glass) непрозрачные, без размытия`, els.length ? st(bad.length === 0) : "NOT_RUN", { glass_elements: els.length, bad: bad.slice(0, 5) }, await shotOf(page, `${tag}-fallback-${opts.reduced ? "reduced" : "off"}`));
    } finally { await ctx.close(); }
  }
  const { ctx, page } = await openPage(browser, size, "ru", "resident", { glass: "auto" });
  try {
    await page.goto(base); await settle(page);
    // R01 меряет кадры при движении карты (≥ 600 мс, дважды) — двигаем карту три раза по 1,5 с.
    const before = await page.evaluate(() => document.documentElement.classList.contains("bk-glass-off"));
    await page.evaluate(async (p) => { const m = typeof map !== "undefined" && map && map.easeTo ? map : null; if (!m) return; // eslint-disable-line no-undef
      const wait = (ms) => new Promise((ok) => setTimeout(ok, ms));
      for (let i = 0; i < 3; i++) { m.easeTo({ center: [p[0] + 0.01 * (i % 2 ? -1 : 1), p[1]], duration: 1500 }); await wait(2200); } }, KHAN).catch(() => null);
    await L.sleep(1000);
    const off = await page.evaluate(() => ({ now: document.documentElement.classList.contains("bk-glass-off"), times: window.__r10_off || [] }));
    off.before_motion = before;
    add("G-2", tag, "автовыключатель R01 (GLASS.md R01 №8: < 30 к/с при движении карты → html.bk-glass-off один раз, без мигания)", "INFO",
      { off_before_motion: off.before_motion, off_after_motion: off.now, set_at_ms: off.times.slice(0, 5), set_times: off.times.length, note: "облако — программный WebGL (~5 к/с): после движения карты выключатель должен сработать один раз; на ноутбуке — нет" });
  } finally { await ctx.close(); }
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const css = staticCss();
  const delivered = css.glass.length > 0 || !!INJECT || !!INJECT_JS;
  const sha = L.buildSha(ROOT);
  if (!delivered && !args.force) add("G", "сборка", "стекло «Liquid Glass» — ЖДЁТ поставки (R11 GLASS.md / .bk-glass, затем R01, R07, R08, R09)", "PENDING", "в CSS сборки нет backdrop-filter / .bk-glass");
  else {
    add("G-2", "CSS", "запасной вид без стекла: @media (prefers-reduced-transparency: reduce) и @supports not (backdrop-filter) — непрозрачный белый",
      st(css.reduced.length > 0 && css.nosupport.length > 0), css);
  }
  const server = await L.startServer(ROOT);
  const ctl = CONTROL ? await L.startServer(CONTROL) : null;
  const browser = await chromium.launch();
  const fps = [];
  try {
    if ((delivered || args.force) && !FPS_ONLY) {
      for (const size of SIZES) for (const lang of LANGS) for (const mode of ["resident", "akimat"]) await contrastRun(browser, server.base, size, lang, mode);
      for (const size of SIZES) await fallbackRun(browser, server.base, size);
    }
    // 4. Плавность — 1366 и 1024 (телефон не меряем): стекло / bk-glass-off на этой сборке (если стекло есть) и --control.
    if (!NO_FPS) for (const size of SIZES.filter(([w]) => w >= 1000)) {
      const a = await fpsRun(browser, server.base, size, sha, "keep");
      const off = delivered || args.force ? await fpsRun(browser, server.base, size, sha + " bk-glass-off", "off") : null;
      const b = ctl ? await fpsRun(browser, ctl.base, size, L.buildSha(CONTROL), "keep") : null;
      fps.push(a); if (off) fps.push(off); if (b) fps.push(b);
      for (const [k, v] of [["drag", "перетаскивание мышью"], ["pan", "сдвиг"], ["fly", "перелёт"]]) for (const [state, key] of [["без панели", "plain"], ["с панелью", "withPanel"]]) {
        const now = a.fps[key][k];
        const refs = [[off, "без стекла (bk-glass-off)"], [b, b && b.label]].filter(([r]) => r);
        if (!refs.length) add("G-4", size.join("x"), `плавность карты, ${v} ${state}: ${now ?? "?"} к/с (стекла нет — замер для сравнения)`, "INFO", { now, repeats: FPS_REPEAT });
        for (const [ref, rname] of refs) {
          const was = ref.fps[key][k], verdict = fpsVerdict(now, was);
          add("G-4", size.join("x"), `плавность карты, ${v} ${state}: ${now ?? "?"} к/с против ${was ?? "?"} — ${rname}` + (verdict === "INFO" && now && now < 10 ? " · программный WebGL — мерить на ноутбуке (Codex М9)" : ""),
            verdict, { now, was, ratio: now && was ? Math.round((now / was) * 100) / 100 : null, glass_on: a.glassOn, repeats: FPS_REPEAT });
        }
      }
    }
  } finally { await browser.close(); await server.stop(); if (ctl) await ctl.stop(); }
  const counts = {}; results.forEach((r) => (counts[r.status] = (counts[r.status] || 0) + 1));
  const meta = { root: ROOT, sha, control: CONTROL, ...(INJECT || INJECT_JS ? { inject_css: args["inject-css"] ? String(args["inject-css"]) : null, inject_js: args["inject-js"] ? String(args["inject-js"]) : null, note: "С ПРОБНЫМ CSS/JS — не приёмка сборки" } : {}), when: new Date().toISOString(), sizes: SIZES.map((s) => s.join("x")), langs: LANGS, delivered, machine: L.machine ? L.machine() : null };
  fs.writeFileSync(path.join(OUT, "GLASS.json"), JSON.stringify({ meta, counts, css, fps, results }, null, 1));
  const md = [`# R10 · стекло «Liquid Glass» · ${sha}${delivered ? "" : args.force ? " · без стекла, --force (механика)" : " · стекла нет — ЖДЁТ"}`, "", "```", JSON.stringify(meta), "```", "",
    `Итого: ${Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(" · ")}`, "",
    "G-1 где стекло (и формы без стекла) · G-2 запасной вид (CSS, эмуляция, bk-glass-off, автовыключатель) · G-3 контраст текста на стекле над фонами (карта, тёмно-зелёный, синий, красный — строго; чёрный, полосы — предельные) · G-4 плавность (к/с): стекло против bk-glass-off и --control.", "",
    "| Пункт | Где | Проверка | Итог | Подробно | Кадр |", "|---|---|---|---|---|---|",
    ...results.map((r) => `| ${r.item} | ${r.scope} | ${r.name} | **${r.status === "PENDING" ? "ЖДЁТ" : r.status}** | ${r.detail ? JSON.stringify(r.detail).replace(/\|/g, "/").slice(0, 240) : ""} | ${r.shot || ""} |`)];
  fs.writeFileSync(path.join(OUT, "GLASS.md"), md.join("\n") + "\n");
  console.log("ИТОГ:", counts, "→", OUT);
  process.exit(counts.FAIL ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
