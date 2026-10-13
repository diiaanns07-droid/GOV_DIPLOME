#!/usr/bin/env node
// R10 · раунд 14 · «Дизайн по эталону — лучше 2ГИС» (research/round-14/design/README.md, вариант A REFERENCE.html):
// сравнение экранов сборки с эталоном 1366×768 и 375×812 — по каждому элементу «хрома» (поиск, чипы, навигация, профиль,
// кнопки карты, легенда, сводка, карточка объекта, лист проектов, шторка телефона, главная кнопка, значки): место и размер
// (Δ px), радиус, фон и стекло (прозрачность, размытие), тень, рамка, шрифт (размер, вес, цвет). Плюс кадры:
// «эталон | сборка» и «сборка с рамками эталона (синие) и сборки (красные)», и разница пикселей хрома.
// Элементы ищутся одинаково с обеих сторон: в эталоне — по классу (.search, .nav, .me, .ctl, .legend, .sum, .card…),
// в сборке — по тексту/подписи/роли (поле поиска по подсказке, «Карта»+«Картина дня», «ҚАЗ»+аватар, «Приблизить»…).
// Карта (подложка, данные) у эталона нарисована — её пиксели не сравниваются, только элементы поверх.
//
//   NODE_PATH="$(npm root -g)" node tests/e2e/reference_check.cjs --ref <REFERENCE.html> --root <сборка> --out <папка>
//        [--screens home,obj,proj,phone] [--label <имя сборки>] [--before <папка прошлого прогона>]
// Итог: <out>/REFERENCE.json, REFERENCE.md (расхождения по ролям), TOTALS.json, кадры <screen>-pair.jpg (эталон | сборка),
// -boxes.jpg (рамки), -crops.jpg (вырезки элементов и доля совпадающих пикселей), -diff.jpg (разница кадра),
// -ref-was-now.jpg (эталон | было | стало, с --before), -build.jpg (кадр сборки — «было» для следующего прогона).
"use strict";
const fs = require("fs"), path = require("path"), os = require("os");
const { chromium } = require("playwright");
const L = require("./r10_lib.cjs");

const args = L.parseArgs(process.argv.slice(2));
const REF = path.resolve(String(args.ref || ""));
const ROOT = path.resolve(String(args.root || path.join(__dirname, "../..")));
const OUT = path.resolve(String(args.out || path.join(os.tmpdir(), "r10-reference")));
const SCREENS = String(args.screens || "home,obj,proj,phone").split(",");
const LABEL = String(args.label || "сборка");
const KHAN = [71.406553, 51.131155];
if (!fs.existsSync(REF)) { console.error("нет файла эталона --ref"); process.exit(2); }

// Что сравниваем: id, роль-владелец, селектор в эталоне, поиск в сборке (имя функции FIND в странице), опции:
// pos:false — место не сравнивается (значки стоят по данным), bg:false — цвет фона по данным (уровень жалоб),
// text:true — сравнить текст, absent — в эталоне этого нет (постоянная панель, лишний элемент): найдено в сборке = «лишнее».
const SPEC = {
  home: [
    ["search", "R01", ".search", "search"], ["logo", "R01", ".search .logo", "logo"], ["chips", "R01", ".chips", "chips"],
    ["chip-on", "R01", ".chips .chip.on", "chipOn"], ["nav", "R01", ".nav", "nav"], ["nav-on", "R01", ".nav a.on", "navOn", { text: true }],
    ["me", "R01", ".me", "me"], ["avatar", "R01", ".me .ava", "avatar"], ["sum", "R08", ".sum", "sum"],
    ["ctl", "R01", ".ctl", "ctl"], ["zoom", "R01", ".ctl .cap", "zoom"], ["legend", "R01", ".legend", "legend"],
    ["pin", "R07", ".pin:not(.ok) .c", "pin", { pos: false, bg: false }], ["pin-count", "R07", ".pin:not(.ok) .n", "pinCount", { pos: false }],
    ["постоянная панель", "R01", null, "permPanel", { absent: "в эталоне постоянных панелей нет: слева только закрываемая карточка" }],
  ],
  obj: [
    ["search", "R01", ".search", "search"], ["nav", "R01", ".nav", "nav"], ["me", "R01", ".me", "me"],
    ["card", "R07", ".card", "card"], ["card-title", "R07", ".card h2", "cardTitle"], ["card-close", "R07", ".card .x", "cardClose"],
    ["card-count", "R07", ".card .big b", "cardCount"], ["card-btn-main", "R07", ".card .btn.p", "cardMain"],
    ["card-btn-2", "R07", ".card .btn.s", "cardSecond"], ["card-tabs", "R07", ".card .tabs", "cardTabs"],
    ["pin-sel", "R07", ".pin.sel .c", "pinSel", { pos: false, bg: false }], ["pin-dim", "R07", ".pin.dim .c", "pinDim", { pos: false, bg: false }], ["ctl", "R01", ".ctl", "ctl"],
  ],
  proj: [
    ["search", "R01", ".search", "search"], ["nav", "R01", ".nav", "nav"], ["nav-on", "R01", ".nav a.on", "navOn", { text: true }],
    ["sheet", "R06", ".sheet", "projSheet"], ["sheet-title", "R06", ".sheet .hd b", "projTitle", { text: true }], ["seg", "R06", ".sheet .seg", "projSeg"],
    ["pc", "R06", ".plist .pc", "projCard"], ["vote", "R06", ".plist .pc .vote", "projVote"], ["pd", "R06", ".pd", "projDetail"],
    ["tag", "R05", ".tag", "projTag", { pos: false }],
  ],
  phone: [
    ["p-search", "R01", ".p-search", "search"], ["p-sheet", "R09", ".p-sheet", "phoneSheet"], ["p-sheet-title", "R09", ".p-sheet b", "phoneSheetTitle", { text: true }],
    ["p-hot", "R09", ".p-sheet .hot", "phoneHot"], ["fab", "R09", ".fab", "fab", { text: true }], ["fab-icon", "R09", ".fab i", "fabIcon"],
    ["pin", "R07", ".pin .c", "pin", { pos: false, bg: false }],
    ["легенда сверху", "R01", null, "legend", { absent: "в эталоне телефона поверх карты только поиск, шторка и кнопка" }],
    ["кнопки карты", "R01", null, "ctl", { absent: "в эталоне телефона кнопок карты нет" }],
  ],
};

// В странице: рамка, стиль и поиск элементов сборки.
const PAGE = () => {
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 2 && r.height > 2 && s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0.02; };
  const rgba = (c) => { const m = String(c).match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [v[0], v[1], v[2], v.length > 3 ? v[3] : 1]; };
  const own = (e) => [...e.childNodes].filter((x) => x.nodeType === 3).map((x) => x.textContent).join(" ").replace(/\s+/g, " ").trim();
  // Ближайший предок-«коробка» (фон, стекло, тень, рамка). tight — не дальше, чем в 1,8 раза больше самого элемента
  // (иначе для навигации внутри общей шапки найдётся вся шапка): тогда возвращается сам элемент.
  const boxOf = (e, tight) => { const r0 = e.getBoundingClientRect();
    for (let p = e; p && p !== document.body; p = p.parentElement) { const s = getComputedStyle(p), bg = rgba(s.backgroundColor), r = p.getBoundingClientRect();
      if (tight && (r.width > r0.width * 1.8 + 48 || r.height > r0.height * 1.8 + 48)) return e;
      if ((bg && bg[3] >= 0.25) || (s.backdropFilter && s.backdropFilter !== "none") || (s.boxShadow && s.boxShadow !== "none" && !/^inset/.test(s.boxShadow.trim())) || parseFloat(s.borderTopWidth) >= 1) return p; } return e; };
  // Несколько элементов как один (навигация, «ҚАЗ · РУС» + аватар): рамка — объединение, стиль — у style.
  const union = (els, style) => { els = els.filter(Boolean); return els.length ? { els, style: style || els[0] } : null; };
  const all = (sel, root = document) => [...root.querySelectorAll(sel)].filter(vis);
  const byText = (re, root = document, tags = "*") => all(tags, root).filter((e) => re.test(own(e)) && !e.closest("svg")).sort((a, b) => a.getBoundingClientRect().width * a.getBoundingClientRect().height - b.getBoundingClientRect().width * b.getBoundingClientRect().height)[0] || null;
  const byAria = (re, root = document) => all("[aria-label]", root).find((e) => re.test(e.getAttribute("aria-label"))) || null;
  const lca = (a, b) => { if (!a || !b) return null; const pa = []; for (let p = a; p; p = p.parentElement) pa.push(p); for (let p = b; p; p = p.parentElement) if (pa.includes(p)) return p; return null; };
  const glassUp = (e) => { for (let p = e; p && p !== document.body; p = p.parentElement) { const f = getComputedStyle(p).backdropFilter; if (f && f !== "none") return p; } return null; };
  const btn = (re, root = document) => all("button, a, [role=button], [role=tab], [role=menuitem]", root).find((e) => re.test((e.innerText || e.getAttribute("aria-label") || "").trim().replace(/\s+/g, " "))) || null;
  const placeCard = () => { const t = byText(/Хан Шатыр/, document, "h1,h2,h3,h4,strong,b,p,div,span"); if (!t) return null; return glassUp(t) || boxOf(t); };
  const FIND = {
    search: () => { const i = all("input").find((x) => /Улица|Поиск|Іздеу|Көше|Найти|проект/i.test(x.placeholder || "")); return i ? boxOf(i) : null; },
    logo: () => all(".brand-mark, [class*=logo], [class*=brand] svg").find((e) => e.getBoundingClientRect().top < 120) || null,
    chips: () => { const a = btn(/^Все( категории)?$/); return a && a.getBoundingClientRect().top < 160 ? a.parentElement : null; },
    chipOn: () => { const a = btn(/^Все$/); return a && a.getBoundingClientRect().top < 160 ? boxOf(a) : null; },
    nav: () => { const a = btn(/^Карта$/), b = btn(/^Картина дня$/) || btn(/^Мои обращения$/); const c = lca(a, b); return c ? boxOf(c, true) : null; },
    navOn: () => all("button, a").find((e) => e.getBoundingClientRect().top < 100 && (e.matches("[aria-current], [aria-current=page], [aria-pressed=true], [aria-selected=true], .on, .active, .is-active")) && /^(Карта|Проекты( и идеи)?|Картина дня|Обращения|Ещё)$/.test((e.innerText || "").trim())) || null,
    me: () => { const a = btn(/ҚАЗ/) || byText(/ҚАЗ/), b = all(".birge-avatar, [aria-label*=рофил], .ava")[0]; if (!a || !b) return null;
      const c = lca(a, b), cb = c && boxOf(c, true); if (cb && cb.getBoundingClientRect().width < 400) return cb;
      const la = a.closest(".birge-lang, [class*=lang]") || a; return union([la, b], boxOf(la, true)); },
    avatar: () => all(".birge-avatar, [aria-label*=рофил], .ava")[0] || null,
    sum: () => { const t = byText(/Сегодня в Астане|Бүгін Астанада/); return t ? (glassUp(t) || boxOf(t)) : null; },
    // Постоянная панель: большая стеклянная/плотная панель на открытой главной (без нажатий), шире 300 и выше 400 px.
    permPanel: () => all("aside, section, div").filter((e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e), bg = rgba(s.backgroundColor);
      return r.width >= 300 && r.height >= 400 && r.width < innerWidth * 0.9 && ((s.backdropFilter && s.backdropFilter !== "none") || (bg && bg[3] >= 0.6)) && !e.closest(".maplibregl-map"); })
      .sort((a, b) => b.getBoundingClientRect().width * b.getBoundingClientRect().height - a.getBoundingClientRect().width * a.getBoundingClientRect().height)[0] || null,
    ctl: () => { const a = byAria(/Моё местоположение|Менің орным/), b = byAria(/Слой на карте|Картадағы қабат/) || btn(/^3D$/); return lca(a, b); },
    zoom: () => { const a = byAria(/Приблизить|Жақындату/), b = byAria(/Отдалить|Алыстату/); const c = lca(a, b); return c ? boxOf(c) : null; },
    legend: () => { const t = byText(/^мало$|^аз$/); return t ? boxOf(t.closest("#birge-legend, [class*=legend-line], [class*=legend]") || t) : null; },
    pin: () => { const b = all(".r07-badge:not(.r07-badge--mini):not(.r07-badge--cluster)")[0]; return b ? (b.querySelector(".r07-badge__dot") || b.querySelector(".r07-badge__inner") || b) : null; },
    pinCount: () => { const b = all(".r07-badge:not(.r07-badge--mini)")[0]; return b ? b.querySelector(".r07-badge__count") : null; },
    card: placeCard,
    cardTitle: () => byText(/Хан Шатыр/, placeCard() || document, "h1,h2,h3,h4,strong,b,div,span,p"),
    cardClose: () => { const c = placeCard(); return c ? btn(/^(×|Закрыть|Жабу)$/i, c) || byAria(/Закрыть|Жабу/, c) : null; },
    cardCount: () => { const c = placeCard(); return c ? all("*", c).find((e) => /^\d+$/.test(own(e)) && parseFloat(getComputedStyle(e).fontSize) >= 22) || null : null; },
    cardMain: () => { const c = placeCard(); if (!c) return null; return all("button, a.bk-btn", c).find((e) => { const bg = rgba(getComputedStyle(e).backgroundColor); return bg && bg[3] > 0.9 && bg[0] + bg[1] + bg[2] < 160; }) || null; },
    cardSecond: () => { const c = placeCard(); if (!c) return null; const main = FIND.cardMain(); const list = all("button", c).filter((e) => e !== main && e.getBoundingClientRect().height >= 36 && (e.innerText || "").trim().length > 2); return list.find((e) => main && Math.abs(e.getBoundingClientRect().top - main.getBoundingClientRect().top) < 30 || (main && e.getBoundingClientRect().top - main.getBoundingClientRect().bottom < 20 && e.getBoundingClientRect().top > main.getBoundingClientRect().top)) || null; },
    cardTabs: () => { const c = placeCard(); if (!c) return null; return all("[role=tablist]", c)[0] || (btn(/^Обзор$/, c) || {}).parentElement || null; },
    pinSel: () => { const b = all(".r07-badge--selected, .r07-badge[aria-pressed=true], .r07-badge[aria-current]")[0]; return b ? (b.querySelector(".r07-badge__dot") || b) : null; },
    // Бледный значок: итоговая прозрачность (с предками) у самого значка или его кружка < 0,9.
    pinDim: () => { const eff = (e) => { let o = 1; for (let p = e; p; p = p.parentElement) o *= Number(getComputedStyle(p).opacity); return o; };
      for (const b of all(".r07-badge:not(.r07-badge--selected)")) { const d = b.querySelector(".r07-badge__dot") || b; if (eff(d) < 0.9) return d; } return null; },
    projSheet: () => { const t = byText(/^Проекты и идеи$|^Жобалар мен идеялар$|^Идеи жителей$/, document, "h1,h2,h3,b,strong,div,span"); return t ? (glassUp(t) || boxOf(t)) : null; },
    projTitle: () => byText(/^Проекты и идеи$|^Идеи жителей$/, document, "h1,h2,h3,b,strong"),
    projSeg: () => { const s = FIND.projSheet(); const t = btn(/^Идеи (жителей|на проверке)/) || byText(/Идеи жителей ·|Голосование/); return t ? (t.closest("[role=tablist], .bk-tabs, [class*=seg]") || t.parentElement) : (s ? all("[role=tablist], .bk-tabs", s)[0] || null : null); },
    projCard: () => { const s = FIND.projSheet() || document; return all("article.bk-card, article, .ri-card, .r06-card", s).find((e) => e.getBoundingClientRect().height >= 60) || null; },
    projVote: () => btn(/Поддержать|Қолдау/) || (FIND.projCard() ? all(".ri-votes, [class*=vote]", FIND.projCard())[0] || null : null),
    projDetail: () => null,
    projTag: () => byText(/^Проект · 20\d\d$/),
    phoneSheet: () => all("#civic-panel, .civic-panel, [class*=sheet]").find((e) => e.getBoundingClientRect().top > 200) || null,
    phoneSheetTitle: () => { const s = FIND.phoneSheet(); return s ? all("h1,h2,h3,b,strong", s)[0] || null : null; },
    phoneHot: () => { const s = FIND.phoneSheet(); if (!s) return null; return all(".r07-item, .bc-item, li > button, [class*=item]", s).find((e) => { const h = e.getBoundingClientRect().height; return /\d/.test(e.innerText || "") && /[А-Яа-яӘә]{3}/.test(e.innerText || "") && h >= 40 && h <= 110; }) || null; },
    fab: () => btn(/Сообщить о проблеме|Мәселе туралы хабарлау/),
    fabIcon: () => { const b = FIND.fab(); if (!b) return null; return all("svg, i, [class*=icon]", b).map((x) => (x.tagName === "svg" || x.tagName === "SVG") && x.parentElement !== b ? x.parentElement : x)[0] || null; },
  };
  const desc = (e, frame) => {
    if (!e) return null;
    let r;
    if (e.els) { const rs = e.els.map((x) => x.getBoundingClientRect()); const l = Math.min(...rs.map((x) => x.left)), t = Math.min(...rs.map((x) => x.top));
      r = { left: l, top: t, width: Math.max(...rs.map((x) => x.right)) - l, height: Math.max(...rs.map((x) => x.bottom)) - t }; e = e.style; }
    else r = e.getBoundingClientRect();
    const o = frame ? frame.getBoundingClientRect() : { left: 0, top: 0 };
    const s = getComputedStyle(e), f = s.backdropFilter || "none";
    const tx = [e, ...e.querySelectorAll("*")].find((x) => own(x) && vis(x));
    const ts = tx ? getComputedStyle(tx) : null;
    return { x: Math.round(r.left - o.left), y: Math.round(r.top - o.top), w: Math.round(r.width), h: Math.round(r.height),
      radius: Math.round(parseFloat(s.borderTopLeftRadius)), bg: rgba(s.backgroundColor), blur: (f.match(/blur\(([\d.]+)px\)/) || [])[1] ? Number(f.match(/blur\(([\d.]+)px\)/)[1]) : 0,
      saturate: (f.match(/saturate\(([\d.]+)/) || [])[1] ? Number(f.match(/saturate\(([\d.]+)/)[1]) : null, shadow: s.boxShadow !== "none", border: parseFloat(s.borderTopWidth) || 0,
      opacity: (() => { let o = 1; for (let p = e; p && p.nodeType === 1; p = p.parentElement) o *= Number(getComputedStyle(p).opacity); return Math.round(o * 100) / 100; })(), font: ts ? { size: parseFloat(ts.fontSize), weight: Number(ts.fontWeight), color: rgba(ts.color), family: ts.fontFamily.split(",")[0].replace(/["']/g, "").trim() } : null,
      off: !frame && (r.top + r.height > innerHeight + 1 || r.left + r.width > innerWidth + 1 || r.top < -1),
      text: tx ? own(tx).slice(0, 40) : "", all: (e.innerText || e.textContent || "").replace(/\s+/g, " ").trim().slice(0, 60),
      cls: (e.id ? "#" + e.id : "") + (typeof e.className === "string" && e.className.trim() ? "." + e.className.trim().split(/\s+/).slice(0, 2).join(".") : "") || e.tagName.toLowerCase() };
  };
  return { FIND, desc };
};

async function refShots(browser) {
  const p = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
  await p.goto("file://" + REF); await p.waitForTimeout(600);
  await p.click('button[data-v="v-a"]').catch(() => null); await p.waitForTimeout(300);
  const out = {};
  for (const f of SCREENS) {
    await p.click(`button[data-f="${f}"]`).catch(() => null); await p.waitForTimeout(400);
    const sel = f === "phone" ? "#stagePhone .frame" : `#stage .frame[data-f="${f}"]`;
    const el = await p.$(sel); if (!el) continue;
    await el.evaluate((e) => { e.style.transform = "none"; e.parentElement.style.height = e.offsetHeight + "px"; e.parentElement.style.overflow = "visible"; });
    await p.waitForTimeout(250);
    const png = await el.screenshot();
    const items = await p.evaluate(([sel, spec, page]) => {
      const { desc } = eval("(" + page + ")")();
      const frame = document.querySelector(sel);
      return spec.map(([id, owner, rsel]) => ({ id, owner, ref: rsel ? desc(frame.querySelector(rsel), frame) : null }));
    }, [sel, SPEC[f], PAGE.toString()]);
    const tokens = f === "home" ? await p.evaluate(() => { const s = getComputedStyle(document.documentElement); return Object.fromEntries(["--ink", "--ink-2", "--ink-3", "--line", "--paper", "--brand", "--lime", "--glass", "--glass-strong", "--r-card", "--r-pill", "--r-ctl", "--font", "--ease"].map((k) => [k, s.getPropertyValue(k).trim()])); }) : null;
    out[f] = { png, items, tokens };
  }
  await p.close();
  return out;
}

async function buildShots(browser, server) {
  const out = {};
  for (const f of SCREENS) {
    const phone = f === "phone";
    const ctx = await browser.newContext({ viewport: phone ? { width: 375, height: 812 } : { width: 1366, height: 768 }, isMobile: phone, hasTouch: phone, deviceScaleFactor: 1, locale: "ru-RU" });
    await ctx.addInitScript((m) => { try { if (!sessionStorage.getItem("r10")) { localStorage.setItem("birge.lang", "ru"); localStorage.setItem("birge.mode", m); sessionStorage.setItem("r10", "1"); } } catch (e) { /* пусто */ } }, phone ? "resident" : "akimat");
    await L.glassMode(ctx, "keep");
    // Акимат в эталоне — сотрудник в кабинете (навигация «Картина дня · Обращения · Проекты»): вход через API той же сборки.
    let login = null;
    if (!phone && server.staff && server.staff.user) {
      const r = await ctx.request.post(server.base + "api/civic/v1/session/login", { data: { username: server.staff.user, password: server.staff.pass } }).catch((e) => ({ ok: () => false, status: () => String(e).slice(0, 80) }));
      login = r.ok() ? "ok" : "нет (" + r.status() + ")";
    }
    const page = await ctx.newPage();
    try {
      await page.goto(server.base); await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 40, null, { timeout: 40000 }).catch(() => null);
      await L.sleep(5000);
      let reached = true;
      if (f === "obj") { const pt = await L.showPoint(page, KHAN, 16); if (pt) { await L.tap(page, pt.x, pt.y); await L.sleep(2500); } reached = !!(await L.firstVisible(page.locator(".r07-card"))); }
      if (f === "proj") reached = await L.headerClick(page, /^\s*Проекты( и идеи)?\s*$/i, { wait: 3000, menuRe: /^\s*Меню\s*$/i });
      await page.evaluate(() => { const s = document.createElement("style"); s.textContent = "*,*::before,*::after{transition:none!important;animation:none!important}"; document.head.appendChild(s); });
      await L.sleep(400);
      const png = await page.screenshot();
      const items = await page.evaluate(([spec, src]) => { const { FIND, desc } = eval("(" + src + ")")(); return spec.map(([id, owner, rsel, fn]) => { let e = null, err = null; try { e = FIND[fn](); } catch (x) { e = null; err = String(x).slice(0, 120); } return { id, build: desc(e, null), err }; }); }, [SPEC[f], PAGE.toString()]);
      const tokens = f === "home" ? await page.evaluate(() => { const b = getComputedStyle(document.body); return { font: b.fontFamily.split(",")[0].replace(/["']/g, "").trim(), color: b.color, bg: b.backgroundColor }; }) : null;
      out[f] = { png, items, tokens, reached, login };
    } finally { await ctx.close(); }
  }
  return out;
}

const dist = (a, b) => (a && b ? Math.round(Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2])) : null);
const hex = (c) => (c ? "#" + c.slice(0, 3).map((x) => Math.round(x).toString(16).padStart(2, "0")).join("") + (c[3] < 1 ? `/${Math.round(c[3] * 100)}%` : "") : "—");
const norm = (t) => String(t || "").replace(/[«»"“”]/g, "").replace(/\s+/g, " ").trim().toLowerCase();
function compare(ref, bld, opt = {}) {
  if (opt.absent) return bld ? { status: "лишнее", notes: [`${opt.absent}; в сборке: ${bld.cls} ${bld.x},${bld.y} ${bld.w}×${bld.h}${bld.all ? ` «${bld.all.slice(0, 40)}»` : ""}`] } : { status: "совпадает", notes: [] };
  if (!ref) return { status: "нет в эталоне", notes: [] };
  if (!bld) return { status: "НЕТ В СБОРКЕ", notes: ["элемента нет"] };
  const notes = [];
  const d = opt.pos === false ? { w: bld.w - ref.w, h: bld.h - ref.h } : { x: bld.x - ref.x, y: bld.y - ref.y, w: bld.w - ref.w, h: bld.h - ref.h };
  const geo = Math.max(...Object.values(d).map(Math.abs));
  if (geo > 4) notes.push(opt.pos === false ? `размер: эталон ${ref.w}×${ref.h} → ${bld.w}×${bld.h} (место по данным не сравнивается)`
    : `место/размер: эталон ${ref.x},${ref.y} ${ref.w}×${ref.h} → ${bld.x},${bld.y} ${bld.w}×${bld.h} (Δx ${d.x}, Δy ${d.y}, Δw ${d.w}, Δh ${d.h})`);
  if (bld.off) notes.push(`за краем экрана ${bld.x},${bld.y} — не виден без прокрутки`);
  const fam = (x) => (/^(Inter|Birge Sans)$/i.test(x) ? "Inter" : x);
  if (ref.font && bld.font && fam(ref.font.family) !== fam(bld.font.family)) notes.push(`шрифт ${ref.font.family} → ${bld.font.family}`);
  if (opt.text && norm(ref.all) && norm(bld.all) && norm(ref.all) !== norm(bld.all)) notes.push(`текст «${ref.all.slice(0, 40)}» → «${bld.all.slice(0, 40)}»`);
  if (Math.abs((ref.border || 0) - (bld.border || 0)) > 1) notes.push(`рамка ${ref.border} → ${bld.border} px`);
  if (Math.abs(ref.radius - bld.radius) > 2 && !(ref.radius >= Math.min(ref.w, ref.h) / 2 - 1 && bld.radius >= Math.min(bld.w, bld.h) / 2 - 1)) notes.push(`радиус ${ref.radius} → ${bld.radius}`);
  const bg = dist(ref.bg, bld.bg), alpha = ref.bg && bld.bg ? Math.abs(ref.bg[3] - bld.bg[3]) : 0;
  if (opt.bg !== false && ((ref.bg && ref.bg[3] > 0.05) || (bld.bg && bld.bg[3] > 0.05))) if (bg > 24 || alpha > 0.08) notes.push(`фон ${hex(ref.bg)} → ${hex(bld.bg)}`);
  if (Math.abs((ref.blur || 0) - (bld.blur || 0)) > 3) notes.push(`стекло (размытие) ${ref.blur}px → ${bld.blur}px`);
  if (ref.shadow !== bld.shadow) notes.push(`тень ${ref.shadow ? "есть" : "нет"} → ${bld.shadow ? "есть" : "нет"}`);
  if (ref.font && bld.font) {
    if (Math.abs(ref.font.size - bld.font.size) > 0.6) notes.push(`шрифт ${ref.font.size} → ${bld.font.size} px`);
    if (ref.font.weight !== bld.font.weight) notes.push(`вес ${ref.font.weight} → ${bld.font.weight}`);
    if (dist(ref.font.color, bld.font.color) > 30) notes.push(`цвет текста ${hex(ref.font.color)} → ${hex(bld.font.color)}`);
  }
  if (Math.abs((ref.opacity ?? 1) - (bld.opacity ?? 1)) > 0.1) notes.push(`прозрачность ${ref.opacity} → ${bld.opacity}`);
  const status = !notes.length ? "совпадает" : geo <= 12 && notes.length <= 1 ? "близко" : "расходится";
  return { status, notes, geo };
}

// Кадры и пиксели: «эталон | сборка», рамки, вырезки элементов «эталон | сборка» с долей совпадающих пикселей
// (элемент сборки приводится к размеру эталона; пиксель совпадает, если каналы отличаются не больше чем на 24),
// карта разницы всего кадра и, если есть прошлый прогон (--before), «эталон | было | стало».
async function composites(browser, f, ref, bld, rows, before) {
  const p = await browser.newPage();
  await p.setContent("<html><body></body></html>");
  const res = await p.evaluate(async ([a, b, rows, before, beforeLabel, label]) => {
    const load = async (src) => { const im = new Image(); im.src = src; await im.decode(); return im; };
    const ia = await load("data:image/png;base64," + a), ib = await load("data:image/png;base64," + b), ic = before ? await load("data:image/jpeg;base64," + before) : null;
    const W = ia.width, H = ia.height, PAD = 10, HEAD = 30;
    const mk = (n, w = W, h = H) => { const c = document.createElement("canvas"); c.width = n * w + (n + 1) * PAD; c.height = h + HEAD + PAD; const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height); g.font = "600 16px sans-serif"; g.fillStyle = "#152c26"; return [c, g]; };
    const q = (c, k = 0.72) => c.toDataURL("image/jpeg", k).split(",")[1];
    const out = {};
    const [c1, g1] = mk(2); g1.fillText("Эталон A", PAD, 21); g1.fillText("Сборка · " + label, 2 * PAD + W, 21);
    g1.drawImage(ia, PAD, HEAD); g1.drawImage(ib, 2 * PAD + W, HEAD); out.pair = q(c1);
    const [c2, g2] = mk(1); g2.fillText("Сборка · рамки: синие — эталон, красные — сборка", PAD, 21); g2.drawImage(ib, PAD, HEAD);
    g2.lineWidth = 2; g2.font = "600 12px sans-serif";
    for (const r of rows) {
      if (r.ref) { g2.strokeStyle = "#1c5597"; g2.setLineDash([5, 3]); g2.strokeRect(PAD + r.ref.x, HEAD + r.ref.y, r.ref.w, r.ref.h); }
      if (r.build) { g2.strokeStyle = r.absent ? "#8e24aa" : "#c62828"; g2.setLineDash([]); g2.strokeRect(PAD + r.build.x, HEAD + r.build.y, r.build.w, r.build.h); g2.fillStyle = g2.strokeStyle; g2.fillText(r.id, PAD + r.build.x + 3, HEAD + r.build.y + 13); }
      else if (r.ref) { g2.fillStyle = "#1c5597"; g2.fillText(r.id + " — нет", PAD + r.ref.x + 3, HEAD + r.ref.y + 13); }
    }
    out.boxes = q(c2);
    // «Эталон | было | стало»: телефон — в ряд, 1366 — столбиком (в ряд три кадра 1366 не читаются).
    if (ic) { const vert = W > 800, c3 = document.createElement("canvas"); c3.width = vert ? W + 2 * PAD : 3 * W + 4 * PAD; c3.height = vert ? 3 * (H + HEAD) + PAD : H + HEAD + PAD;
      const g3 = c3.getContext("2d"); g3.fillStyle = "#fff"; g3.fillRect(0, 0, c3.width, c3.height); g3.font = "600 16px sans-serif"; g3.fillStyle = "#152c26";
      [[ia, "Эталон A"], [ic, "Было · " + beforeLabel], [ib, "Стало · " + label]].forEach(([im, t], i) => { const x = vert ? PAD : PAD + i * (W + PAD), y = vert ? i * (H + HEAD) : 0;
        g3.fillText(t, x, y + 21); g3.drawImage(im, x, y + HEAD, W, H); }); out.was = q(c3); }
    // Пиксели элементов.
    const px = (im, x, y, w, h, tw, th) => { const c = document.createElement("canvas"); c.width = tw; c.height = th; const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, tw, th);
      g.drawImage(im, Math.max(0, x), Math.max(0, y), Math.max(1, w), Math.max(1, h), 0, 0, tw, th); return g.getImageData(0, 0, tw, th).data; };
    const same = (da, db) => { let n = 0; for (let i = 0; i < da.length; i += 4) if (Math.max(Math.abs(da[i] - db[i]), Math.abs(da[i + 1] - db[i + 1]), Math.abs(da[i + 2] - db[i + 2])) <= 24) n++; return Math.round(100 * n / (da.length / 4)); };
    const sims = {};
    const list = rows.filter((r) => r.ref && r.build && !r.absent && r.ref.w > 2 && r.ref.h > 2 && r.build.w > 2 && r.build.h > 2);
    for (const r of list) { const s = Math.min(1, 240 / Math.max(r.ref.w, r.ref.h)); const tw = Math.max(4, Math.round(r.ref.w * s)), th = Math.max(4, Math.round(r.ref.h * s));
      sims[r.id] = same(px(ia, r.ref.x, r.ref.y, r.ref.w, r.ref.h, tw, th), px(ib, r.build.x, r.build.y, r.build.w, r.build.h, tw, th)); }
    // Лента вырезок: подпись | эталон | сборка (каждая вписана в 420×ROW, сборка — своим размером, не растянута).
    const ROW = 110, CW = 420, LW = 250;
    const c4 = document.createElement("canvas"); c4.width = LW + 2 * CW + 4 * PAD; c4.height = HEAD + Math.max(1, list.length) * (ROW + PAD) + PAD;
    const g4 = c4.getContext("2d"); g4.fillStyle = "#fff"; g4.fillRect(0, 0, c4.width, c4.height); g4.fillStyle = "#152c26"; g4.font = "600 15px sans-serif";
    g4.fillText("Элемент · роль · пиксели", PAD, 21); g4.fillText("Эталон A", LW + 2 * PAD, 21); g4.fillText("Сборка", LW + CW + 3 * PAD, 21);
    list.forEach((r, i) => { const y = HEAD + i * (ROW + PAD);
      g4.fillStyle = "#152c26"; g4.font = "600 14px sans-serif"; g4.fillText(r.id, PAD, y + 22); g4.font = "13px sans-serif"; g4.fillStyle = "#4b5752"; g4.fillText(`${r.owner} · ${sims[r.id]}% · ${r.status}`, PAD, y + 42);
      for (const [im, box, x0] of [[ia, r.ref, LW + 2 * PAD], [ib, r.build, LW + CW + 3 * PAD]]) { const s = Math.min(CW / box.w, ROW / box.h, 2);
        g4.fillStyle = "#eef0ee"; g4.fillRect(x0, y, CW, ROW); g4.drawImage(im, box.x, box.y, box.w, box.h, x0, y, box.w * s, box.h * s); } });
    out.crops = q(c4, 0.8);
    // Разница кадра целиком.
    const fa = px(ia, 0, 0, W, H, W, H), fb = px(ib, 0, 0, ib.width, ib.height, W, H);
    const [c5, g5] = mk(1); const d = g5.createImageData(W, H); let diff = 0;
    for (let i = 0; i < fa.length; i += 4) { const m = Math.max(Math.abs(fa[i] - fb[i]), Math.abs(fa[i + 1] - fb[i + 1]), Math.abs(fa[i + 2] - fb[i + 2])); const gr = 0.3 * fb[i] + 0.59 * fb[i + 1] + 0.11 * fb[i + 2];
      if (m > 32) { diff++; d.data[i] = 220; d.data[i + 1] = 40; d.data[i + 2] = 40; } else { d.data[i] = d.data[i + 1] = d.data[i + 2] = 200 + gr * 0.2; } d.data[i + 3] = 255; }
    g5.putImageData(d, PAD, HEAD); g5.fillStyle = "#152c26"; g5.fillText(`Разница с эталоном: красным — пиксели, отличающиеся больше чем на 32 (${Math.round(100 * diff / (W * H))}% кадра; карта и данные в эталоне нарисованы)`, PAD, 21);
    out.diff = q(c5); out.diffShare = Math.round(100 * diff / (W * H)); out.sims = sims;
    const jb = document.createElement("canvas"); jb.width = ib.width; jb.height = ib.height; jb.getContext("2d").drawImage(ib, 0, 0); out.buildJpg = q(jb, 0.85);
    return out;
  }, [ref.toString("base64"), bld.toString("base64"), rows, before ? before.jpg : null, before ? before.label : "", LABEL]);
  await p.close();
  for (const k of ["pair", "boxes", "crops", "diff"]) fs.writeFileSync(path.join(OUT, `${f}-${k}.jpg`), Buffer.from(res[k], "base64"));
  if (res.was) fs.writeFileSync(path.join(OUT, `${f}-ref-was-now.jpg`), Buffer.from(res.was, "base64"));
  fs.writeFileSync(path.join(OUT, `${f}-build.jpg`), Buffer.from(res.buildJpg, "base64"));
  return { sims: res.sims, diffShare: res.diffShare };
}

const NAMES = { home: "Главная акимата", obj: "Выбран объект", proj: "Проекты и идеи", phone: "Житель, телефон" };
const BAD = new Set(["расходится", "НЕТ В СБОРКЕ", "лишнее"]);
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  // Прошлый прогон («было»): его REFERENCE.json и кадры сборки <screen>-build.jpg.
  const BEFORE = args.before ? path.resolve(String(args.before)) : null;
  const was = BEFORE && fs.existsSync(path.join(BEFORE, "REFERENCE.json")) ? JSON.parse(fs.readFileSync(path.join(BEFORE, "REFERENCE.json"), "utf8")) : null;
  const browser = await chromium.launch();
  const server = await L.startServer(ROOT);
  const report = {};
  try {
    const R = await refShots(browser), B = await buildShots(browser, server);
    for (const f of SCREENS) {
      if (!R[f] || !B[f]) continue;
      fs.writeFileSync(path.join(OUT, `${f}-ref.png`), R[f].png);
      const rows = R[f].items.map((it, i) => ({ id: it.id, owner: it.owner, ref: it.ref, build: (B[f].items[i] || {}).build, err: (B[f].items[i] || {}).err }));
      SPEC[f].forEach((sp, i) => Object.assign(rows[i], compare(rows[i].ref, rows[i].build, sp[4] || {}), { absent: !!(sp[4] || {}).absent }));
      const bj = BEFORE && fs.existsSync(path.join(BEFORE, `${f}-build.jpg`)) ? { jpg: fs.readFileSync(path.join(BEFORE, `${f}-build.jpg`)).toString("base64"), label: was ? was.meta.label : "было" } : null;
      const px = await composites(browser, f, R[f].png, B[f].png, rows, bj);
      for (const r of rows) { r.pixels = px.sims[r.id] ?? null; const w = was && was.report[f] && was.report[f].rows.find((x) => x.id === r.id); r.was = w ? { status: w.status, pixels: w.pixels ?? null } : null; }
      report[f] = { reached: B[f].reached, login: B[f].login, rows, diffShare: px.diffShare, wasDiff: was && was.report[f] ? was.report[f].diffShare : null, tokens: { ref: R[f].tokens, build: B[f].tokens } };
      console.log(f, B[f].reached ? "" : "(состояние не открылось)", `разница ${px.diffShare}%`, rows.map((r) => `${r.id}:${r.status}${r.pixels !== null ? "/" + r.pixels + "%" : ""}`).join(" "));
    }
  } finally { await browser.close(); await server.stop(); }
  const sha = L.buildSha(ROOT);
  const meta = { ref: path.basename(REF), root: path.basename(ROOT), sha, label: LABEL, before: was ? was.meta.label : null, when: new Date().toISOString() };
  fs.writeFileSync(path.join(OUT, "REFERENCE.json"), JSON.stringify({ meta, report }, null, 1));
  // Счёт: элементов «совпадает/близко» из всех и средняя доля совпадающих пикселей вырезок (по сборке и по ролям).
  const rowsAll = Object.values(report).flatMap((r) => r.rows), good = (x) => x.status === "совпадает" || x.status === "близко";
  const pxs = rowsAll.map((x) => x.pixels).filter((x) => x !== null);
  const score = { ok: rowsAll.filter(good).length, total: rowsAll.length, pixels: pxs.length ? Math.round(10 * pxs.reduce((a, b) => a + b, 0) / pxs.length) / 10 : null,
    roles: Object.fromEntries([...new Set(rowsAll.map((x) => x.owner))].sort().map((o) => [o, `${rowsAll.filter((x) => x.owner === o && good(x)).length}/${rowsAll.filter((x) => x.owner === o).length}`])) };
  const md = [`# R10 · сборка против эталона A · ${meta.label}`, "", "```", JSON.stringify(meta), "```", "",
    `**Счёт: ${score.ok} из ${score.total} элементов совпадают или близки; пиксели вырезок в среднем ${score.pixels}%.** По ролям: ${Object.entries(score.roles).map(([o, v]) => `${o} ${v}`).join(" · ")}.`, "",
    "Совпадает — место и размер ±4 px, радиус ±2, фон, стекло, тень, рамка, шрифт как в эталоне; близко — одно небольшое расхождение;",
    "расходится — несколько; НЕТ В СБОРКЕ — элемента эталона нет; лишнее — в сборке есть то, чего в эталоне нет (постоянная панель и т. п.).",
    "Пиксели — доля совпадающих пикселей вырезки элемента (сборка приведена к размеру эталона, допуск 24 на канал).",
    "Кадры: `<экран>-pair.jpg` (эталон | сборка), `-boxes.jpg` (рамки), `-crops.jpg` (вырезки), `-diff.jpg` (разница кадра)" + (was ? ", `-ref-was-now.jpg` (эталон | было | стало)." : "."), ""];
  const byOwner = {}, totals = {};
  for (const [f, r] of Object.entries(report)) {
    const c = {}; r.rows.forEach((x) => (c[x.status] = (c[x.status] || 0) + 1));
    totals[f] = { ...c, diff: r.diffShare };
    md.push(`## ${NAMES[f] || f}${r.reached ? "" : " — состояние в сборке не открылось"}`, "",
      `Итог: ${Object.entries(c).map(([k, v]) => `${k} ${v}`).join(" · ")} · разница кадра ${r.diffShare}%${r.wasDiff !== null ? ` (было ${r.wasDiff}%)` : ""}${r.login ? ` · вход сотрудника: ${r.login}` : ""}`, "",
      `| Элемент | Роль | Модуль сборки | Итог | Пиксели |${was ? " Было |" : ""} Что не так |`, `|---|---|---|---|---:|${was ? "---|" : ""}---|`);
    for (const x of r.rows) {
      md.push(`| ${x.id} | ${x.owner} | ${x.build ? "`" + x.build.cls + "`" : "—"} | **${x.status}** | ${x.pixels !== null ? x.pixels + "%" : "—"} |${was ? ` ${x.was ? x.was.status + (x.was.pixels !== null ? " · " + x.was.pixels + "%" : "") : "—"} |` : ""} ${x.notes.join("; ").replace(/\|/g, "/")} |`);
      if (x.status !== "совпадает") (byOwner[x.owner] = byOwner[x.owner] || []).push(`${BAD.has(x.status) ? "" : "(мелко) "}${NAMES[f]} · ${x.id}: ${x.status}${x.notes.length ? " — " + x.notes.join("; ") : ""}`);
    }
    md.push("");
  }
  md.push("## Расхождения по ролям", "");
  for (const [o, list] of Object.entries(byOwner).sort()) { md.push(`### ${o} — ${list.filter((x) => !x.startsWith("(мелко)")).length} крупных, ${list.filter((x) => x.startsWith("(мелко)")).length} мелких`, "", ...list.map((x) => `- ${x}`), ""); }
  const t = (report.home || {}).tokens;
  if (t && t.ref) md.push("## Токены", "", `Эталон: шрифт ${t.ref["--font"]}, текст ${t.ref["--ink"]}, вторичный ${t.ref["--ink-2"]}, линия ${t.ref["--line"]}, стекло ${t.ref["--glass"]} / ${t.ref["--glass-strong"]}, радиусы карточки ${t.ref["--r-card"]}, кнопок ${t.ref["--r-ctl"]}, лайм ${t.ref["--lime"]}.`,
    `Сборка: шрифт ${t.build && t.build.font}, текст ${t.build && t.build.color}, фон страницы ${t.build && t.build.bg}.`, "");
  fs.writeFileSync(path.join(OUT, "REFERENCE.md"), md.join("\n") + "\n");
  fs.writeFileSync(path.join(OUT, "TOTALS.json"), JSON.stringify({ meta, score, totals, byOwner: Object.fromEntries(Object.entries(byOwner).map(([o, l]) => [o, { big: l.filter((x) => !x.startsWith("(мелко)")).length, small: l.filter((x) => x.startsWith("(мелко)")).length }])) }, null, 1));
  console.log("ГОТОВО →", OUT);
})().catch((e) => { console.error(e); process.exit(2); });
