#!/usr/bin/env node
// R10 · раунд 14 · стекло «Apple Liquid Glass» (владелец 12 окт; правила — R11 GLASS.md и класс .bk-glass ui-kit).
// Что проверяется (написано до поставки — нет стекла в сборке → ЖДЁТ):
//   1. Где стекло: backdrop-filter только у шапки, панелей, меню, кнопок карты и шторки — НЕ у значков карты и не у полей
//      форм; непрозрачность белого: панели с текстом 72–80 %, мелкие кнопки 55–65 % (для сведения — точные цифры у R11).
//   2. Запасной вид: в CSS есть @media (prefers-reduced-transparency: reduce) и @supports not (backdrop-filter) с непрозрачным
//      белым (браузеры без стекла и «уменьшить прозрачность» в системе).
//   3. Контраст текста на стекле ≥ 4.5:1 (крупный ≥ 3:1) «на любом фоне карты»: под стекло подкладывается фон — карта как есть,
//      чёрный, тёмно-зелёный, синий, красный, полосы чёрное/белое; текст на стекле на миг прозрачный — снимок — по пикселям
//      под каждой надписью берётся худший фон (5-й или 95-й процентиль яркости) и считается контраст с цветом текста.
//   4. Плавность карты (FPS): кадры при сдвиге и перелёте карты, с открытой стеклянной панелью и без, 1366 и 1024; с
//      --control <сборка> — то же на другой сборке (например, FINAL-3 до стекла) на этой же машине, сравнение FPS.
//
//   NODE_PATH="$(npm root -g)" node tests/e2e/glass_check.cjs --root <сборка> --out <папка> [--sizes 1366x768,1024x768]
//        [--langs ru,kk] [--control <сборка без стекла>] [--force]   (--force — проверять и без стекла: механика, не приёмка)
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
      on_marker: !!e.closest(".maplibregl-marker, .r07-badge, .b3d-labels"), in_form: /^(INPUT|TEXTAREA|SELECT)$/.test(e.tagName) || !!e.closest("input, textarea, select") });
  }
  document.querySelectorAll("[data-r10t]").forEach((e) => e.removeAttribute("data-r10t"));
  const texts = []; let n = 0;
  for (const e of document.querySelectorAll("body *")) {
    const own = [...e.childNodes].filter((x) => x.nodeType === 3).map((x) => x.textContent).join("").trim();
    if (own.length < 2 || !vis(e) || e.closest("svg")) continue;
    let g = null; for (let p = e; p && p !== document.body; p = p.parentElement) if (glassOf(p)) { g = p; break; }
    if (!g) continue;
    const r = e.getBoundingClientRect(), cs = getComputedStyle(e), c = rgba(cs.color);
    // Надпись видна сверху (не прокручена за край панели и не закрыта): в середине — она сама.
    const hx = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1), hy = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
    const hit = document.elementFromPoint(hx, hy);
    if (!hit || !(hit === e || e.contains(hit) || hit.contains(e))) continue;
    e.setAttribute("data-r10t", String(n));
    texts.push({ n: n++, text: own.slice(0, 40), x: r.left, y: r.top, w: r.width, h: r.height, color: c, fs: parseFloat(cs.fontSize), bold: Number(cs.fontWeight) >= 600, glass: name(g) });
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
// Строгие (FAIL): карта как есть и насыщенные цвета карты — парк, вода, «много жалоб». Предельные (СМОТРЕТЬ): чёрный и
// полосы чёрное/белое — так тёмной карта не бывает, но видно запас контраста.
const BACKGROUNDS = {
  "карта": null,
  "тёмно-зелёный": "#1b5e20",
  "синий": "#0d47a1",
  "красный": "#b71c1c",
  "чёрный": "#000",
  "полосы": "repeating-linear-gradient(45deg,#000 0 10px,#fff 10px 20px)",
};
const EXTREME = new Set(["чёрный", "полосы"]);
const setBackground = (page, bg) => page.evaluate((bg) => {
  let d = document.getElementById("r10-stress");
  if (!bg) { if (d) d.remove(); return true; }
  const m = document.querySelector(".maplibregl-map"); if (!m) return false;
  if (!d) { d = document.createElement("div"); d.id = "r10-stress"; d.style.cssText = "position:absolute;inset:0;z-index:1;pointer-events:none"; m.appendChild(d); }
  d.style.background = bg; return true;
}, bg);

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

async function openPage(browser, [w, h], lang, mode) {
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1 });
  await ctx.addInitScript(([l, m]) => { try { if (!sessionStorage.getItem("r10")) { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); sessionStorage.setItem("r10", "1"); } } catch (e) { /* пусто */ } }, [lang, mode]);
  if (INJECT) await ctx.addInitScript((css) => { const add = () => { const s = document.createElement("style"); s.id = "r10-inject"; s.textContent = css; document.head.appendChild(s); };
    if (document.head) add(); else document.addEventListener("DOMContentLoaded", add); }, INJECT);
  const page = await ctx.newPage();
  return { ctx, page };
}
async function settle(page) {
  await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 50, null, { timeout: 40000 }).catch(() => null);
  await L.sleep(3500);
}

async function contrastRun(browser, base, size, lang, mode) {
  const tag = `${size[0]}-${lang}-${mode}`;
  const { ctx, page } = await openPage(browser, size, lang, mode);
  try {
    await page.goto(base); await settle(page);
    const states = [["карта", async () => true],
      ["карточка места", async () => { const p = await L.showPoint(page, KHAN, 17); if (p) await L.tap(page, p.x, p.y); await L.sleep(2500); return !!(await L.firstVisible(page.locator(".r07-card"))); }],
      ["меню аватара", async () => { await page.keyboard.press("Escape").catch(() => null); await L.sleep(500); const a = await L.firstVisible(page.locator(".birge-avatar"));
        if (!a) return false; await a.click().catch(() => null); await L.sleep(700); return !!(await L.firstVisible(page.locator("#birge-account"))); }]];
    for (const [sname, enter] of states) {
      const ok = await enter();
      if (!ok) { add("G-3", tag, `${sname}: открыть`, "NOT_RUN", "состояние не открылось"); continue; }
      const scan = await page.evaluate(SCAN);
      if (sname === "карта") {
        // 1. Где стекло: не на значках карты, не у полей форм; непрозрачность (для сведения).
        const bad = scan.surfaces.filter((s) => s.on_marker || s.in_form);
        add("G-1", tag, "стекло (backdrop-filter) только на шапке, панелях, меню, кнопках карты, шторке — не на значках карты и не в полях форм",
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
        await page.evaluate(() => { const e = document.getElementById("r10-hide"); if (e) e.remove(); });
        const res = await pixelContrast(ctx, png, scan.texts, 1);
        const fails = res.filter((r) => !r.ok);
        worst[bname] = { min: Math.min(...res.map((r) => r.ratio)), fails: fails.length };
        add("G-3", tag, `${sname} · фон «${bname}»${EXTREME.has(bname) ? " (предельный)" : ""}: контраст текста на стекле ≥ 4.5:1 (крупный ≥ 3:1)`,
          fails.length === 0 ? "PASS" : EXTREME.has(bname) ? "СМОТРЕТЬ" : "FAIL",
          { texts: res.length, min: worst[bname].min, fails: fails.slice(0, 5).map((f) => `${f.ratio}:1 «${f.text}» (${f.glass})`) },
          bname === "полосы" || fails.length ? await page.screenshot({ path: path.join(OUT, `${tag}-${sname.replace(/\s+/g, "_")}-${bname}.jpg`), type: "jpeg", quality: 70 }).then(() => `${tag}-${sname.replace(/\s+/g, "_")}-${bname}.jpg`, () => null) : null);
      }
      await setBackground(page, null);
    }
  } finally { await ctx.close(); }
}

async function fpsRun(browser, base, size, label) {
  const { ctx, page } = await openPage(browser, size, "ru", "resident");
  try {
    await page.goto(base); await settle(page);
    const plain = await page.evaluate(SMOOTH, KHAN).catch((e) => ({ error: String(e.message).slice(0, 120) }));
    const p = await L.showPoint(page, KHAN, 17); if (p) await L.tap(page, p.x, p.y); await L.sleep(2500);
    const panel = !!(await L.firstVisible(page.locator(".r07-card")));
    const withPanel = await page.evaluate(SMOOTH, KHAN).catch((e) => ({ error: String(e.message).slice(0, 120) }));
    return { label, size: size.join("x"), plain, panel, withPanel };
  } finally { await ctx.close(); }
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const css = staticCss();
  const delivered = css.glass.length > 0 || !!INJECT;
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
    if (delivered || args.force) for (const size of SIZES) for (const lang of LANGS) for (const mode of ["resident", "akimat"]) await contrastRun(browser, server.base, size, lang, mode);
    // 4. Плавность — всегда (до стекла это эталон для сравнения); с --control — обе сборки по очереди на этой машине.
    for (const size of SIZES) {
      const a = await fpsRun(browser, server.base, size, sha);
      const b = ctl ? await fpsRun(browser, ctl.base, size, L.buildSha(CONTROL)) : null;
      fps.push(a); if (b) fps.push(b);
      const f = (x, k) => (x && x[k] && x[k].fps) || null;
      for (const [k, v] of [["pan", "сдвиг"], ["fly", "перелёт"]]) for (const [state, key] of [["без панели", "plain"], ["с панелью", "withPanel"]]) {
        const now = f(a[key], k), was = b ? f(b[key], k) : null;
        const ratio = now && was ? now / was : null;
        add("G-4", size.join("x"), `плавность карты, ${v} ${state}: ${now ?? "?"} fps` + (b ? ` (было ${was ?? "?"} на ${b.label})` : ""),
          ratio === null ? "INFO" : ratio >= 0.8 ? "PASS" : "FAIL", { now: a[key] && a[key][k], was: b && b[key] && b[key][k], ratio: ratio && Math.round(ratio * 100) / 100 });
      }
    }
  } finally { await browser.close(); await server.stop(); if (ctl) await ctl.stop(); }
  const counts = {}; results.forEach((r) => (counts[r.status] = (counts[r.status] || 0) + 1));
  const meta = { root: ROOT, sha, control: CONTROL, ...(INJECT ? { inject_css: String(args["inject-css"]), note: "С ПРОБНЫМ CSS — не приёмка сборки" } : {}), when: new Date().toISOString(), sizes: SIZES.map((s) => s.join("x")), langs: LANGS, delivered, machine: L.machine ? L.machine() : null };
  fs.writeFileSync(path.join(OUT, "GLASS.json"), JSON.stringify({ meta, counts, css, fps, results }, null, 1));
  const md = [`# R10 · стекло «Liquid Glass» · ${sha}${delivered ? "" : args.force ? " · без стекла, --force (механика)" : " · стекла нет — ЖДЁТ"}`, "", "```", JSON.stringify(meta), "```", "",
    `Итого: ${Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(" · ")}`, "",
    "G-1 где стекло · G-2 запасной вид · G-3 контраст текста на стекле над фонами (карта, чёрный, зелёный, синий, красный, полосы) · G-4 плавность (FPS).", "",
    "| Пункт | Где | Проверка | Итог | Подробно | Кадр |", "|---|---|---|---|---|---|",
    ...results.map((r) => `| ${r.item} | ${r.scope} | ${r.name} | **${r.status === "PENDING" ? "ЖДЁТ" : r.status}** | ${r.detail ? JSON.stringify(r.detail).replace(/\|/g, "/").slice(0, 240) : ""} | ${r.shot || ""} |`)];
  fs.writeFileSync(path.join(OUT, "GLASS.md"), md.join("\n") + "\n");
  console.log("ИТОГ:", counts, "→", OUT);
  process.exit(counts.FAIL ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
