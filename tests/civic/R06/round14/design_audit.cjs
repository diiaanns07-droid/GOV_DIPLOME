// R06 · дизайн-марафон: аудит экранов R06 в НАСТОЯЩЕЙ сборке R01 по чек-листу DESIGN_MARATHON.md (12 пунктов —
// то, что можно измерить): типографика (кегль ≥ 13, только веса 400/600, не больше 4 размеров в разделе без заголовка
// экрана), одна главная кнопка, зоны нажатия ≥ 44, нет рамок у плашек и старых цветов (как clean_audit R11), нет
// прокрутки вбок, reduced-motion выключает анимации, на стекле капсула «Вы поддержали» читается (≥ 4.5:1).
//
//   NODE_PATH="$(npm root -g)" node tests/civic/R06/round14/design_audit.cjs <дерево сборки> [out.json]
//
// Сервер — python3 -B app.py дерева с CIVIC_DEMO=1 на временной базе (как app_r01_wave2.cjs), сотрудник со случайным
// паролем. Экраны: «Идеи» (список, «Подробнее», мастер 1–3, отправлено), «Проекты и идеи» (очередь, чек-лист, проекты),
// «Работы и отключения» (список, форма) — 1366×768 и 375×812, ru и kk. Демо — synthetic.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os"), crypto = require("crypto");

const ROOT = path.resolve(process.argv[2] || ".");
const OUT = process.argv[3] ? path.resolve(process.argv[3]) : null;
const PASSWORD = "Bayterek-" + crypto.randomBytes(9).toString("base64url") + "-2026";
const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok, detail: ok ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail && !ok ? " — " + String(typeof detail === "string" ? detail : JSON.stringify(detail)).slice(0, 400) : ""));
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });

async function start(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: ROOT, env, input, stdio: [input ? "pipe" : "ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  run("seed-r14-demo");
  run("create-editor auditor --password-stdin --public-label Акимат", PASSWORD + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

// Замер раздела: только внутри корня R06 (.ri / .rw) и полосы выбора места; заголовок экрана (h1) — отдельно.
async function measure(page, sel) {
  return page.evaluate((sel) => {
    const LEGACY = ["#176b4a", "#125d40", "#d7f57c", "#f1fbd6", "#b6d65a", "#f7f8f4", "#f1efe6", "#eaf2fb", "#e6f1eb", "#eef2ea", "#c9d4c5", "#f3efe6", "#f6f3ea", "#eef1ea"]
      .map((h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)));
    const parse = (c) => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return v.length >= 3 && (v[3] === undefined || v[3] > 0.05) ? v.slice(0, 3) : null; };
    const legacy = (c) => { const v = parse(c); return v && LEGACY.some((l) => Math.abs(v[0] - l[0]) + Math.abs(v[1] - l[1]) + Math.abs(v[2] - l[2]) <= 4); };
    const roots = Array.from(document.querySelectorAll(sel));
    const out = { sizes: {}, tiny: [], weight: [], framed: [], legacy: [], small: [], clipped: [], primaries: 0, anim: 0, overflow: document.scrollingElement.scrollWidth - innerWidth };
    const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && !e.closest("details:not([open]) > :not(summary)"); };
    for (const root of roots) for (const e of root.querySelectorAll("*")) {
      if (!vis(e) || e.closest("svg")) continue;
      const s = getComputedStyle(e);
      const own = [...e.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim());
      const text = own ? e.textContent.trim().slice(0, 30) : "";
      if (own && !e.closest(".bk-sr-only") && !/^H1$/.test(e.tagName) && !e.classList.contains("bk-h1")) {
        out.sizes[s.fontSize] = (out.sizes[s.fontSize] || 0) + 1;
        if (parseFloat(s.fontSize) < 13) out.tiny.push(s.fontSize + " «" + text + "»");
        if (s.fontWeight !== "400" && s.fontWeight !== "600") out.weight.push(s.fontWeight + " «" + text + "»");
        if (legacy(s.color)) out.legacy.push("color «" + text + "»");
      }
      if (legacy(s.backgroundColor)) out.legacy.push("background " + (e.className || e.tagName));
      const bw = parseFloat(s.borderTopWidth);
      if (!/INPUT|SELECT|TEXTAREA/.test(e.tagName) && bw >= 1 && bw <= 2 && s.borderTopStyle !== "none" && parseFloat(s.borderRightWidth) >= 1
        && parseFloat(s.borderBottomWidth) >= 1 && parseFloat(s.borderRadius) >= 6 && e.getBoundingClientRect().width > 60 && parse(s.borderTopColor)
        && s.borderTopColor !== s.backgroundColor  // рамка цвета заливки (главная кнопка, выбранный чип) — не рамка
        && !e.classList.contains("bk-btn--danger")) out.framed.push(String(e.className || e.tagName).slice(0, 40));
      if (/^(BUTTON|SUMMARY|A|SELECT|INPUT)$/.test(e.tagName) || e.getAttribute("role") === "tab") {
        const r = e.getBoundingClientRect();
        // Зона нажатия = видимая высота + невидимое расширение ::after (ui-kit: чип и сегмент 40 px + 4 px сверху и снизу).
        const a = getComputedStyle(e, "::after");
        const zone = a.content !== "none" && a.position === "absolute" ? r.height - Math.min(0, parseFloat(a.top) || 0) - Math.min(0, parseFloat(a.bottom) || 0) : r.height;
        if (zone < 43.5 && !(e.tagName === "INPUT" && /checkbox|radio/.test(e.type))) out.small.push(Math.round(r.height) + "px «" + (e.innerText || e.getAttribute("aria-label") || "").trim().slice(0, 20) + "»");
      }
      // Обрезано краем: кнопка или подпись выходит за правый край раздела (а не в прокручиваемой строке вкладок).
      if (/^(BUTTON|LABEL|SUMMARY|H2|H3|P)$/.test(e.tagName)) {
        const r = e.getBoundingClientRect(), box = root.getBoundingClientRect();
        let scroller = false;
        for (let a = e.parentElement; a && a !== root; a = a.parentElement) { const ox = getComputedStyle(a).overflowX; if (ox === "auto" || ox === "scroll") { scroller = true; break; } }
        if (!scroller && r.right > box.right + 1) out.clipped.push(Math.round(r.right - box.right) + "px «" + (e.innerText || "").trim().slice(0, 20) + "»");
      }
      if (e.classList.contains("bk-btn--primary")) out.primaries++;
      if (s.animationName !== "none" && parseFloat(s.animationDuration) > 0.01) out.anim++;
    }
    return out;
  }, sel);
}
function verdict(tag, m, opts) {
  const sizes = Object.keys(m.sizes).sort((a, b) => parseFloat(a) - parseFloat(b));
  check(`${tag}: кегль ≥ 13, веса 400/600`, m.tiny.length === 0 && m.weight.length === 0, m.tiny.concat(m.weight).slice(0, 6));
  check(`${tag}: размеров шрифта ≤ ${opts.sizes || 4} (без заголовка экрана) — ${sizes.join(" / ")}`, sizes.length <= (opts.sizes || 4), m.sizes);
  check(`${tag}: без рамок у плашек и старых цветов`, m.framed.length === 0 && m.legacy.length === 0, m.framed.concat(m.legacy).slice(0, 6));
  check(`${tag}: зоны нажатия ≥ 44 px`, m.small.length === 0, m.small.slice(0, 6));
  check(`${tag}: главных кнопок — ${opts.primaries}`, m.primaries === opts.primaries, m.primaries);
  check(`${tag}: нет прокрутки вбок и ничего не обрезано краем`, m.overflow <= 1 && m.clipped.length === 0, { overflow: m.overflow, clipped: m.clipped.slice(0, 6) });
}

async function newPage(browser, width, lang, mode, opts) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 600 ? 812 : 768 }, reducedMotion: opts && opts.reduced ? "reduce" : "no-preference" });
  await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); } catch (e) {} }, [mode, lang]);
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push(e.message));
  return page;
}

async function resident(browser, base, width, lang) {
  const tag = `${width}-${lang} «Идеи»`;
  const page = await newPage(browser, width, lang, "resident");
  await page.goto(base + "#ideas");
  await page.waitForSelector(".ri .ri-card", { timeout: 30000 });
  await page.waitForTimeout(700);
  verdict(tag + " список", await measure(page, ".ri"), { primaries: 1 });
  const card = page.locator(".ri-card", { has: page.locator(".ri-support") }).first();
  await card.locator(".ri-support").click();
  await page.waitForFunction(() => document.querySelector(".ri-support[aria-pressed=true]"));
  // Цвета — у текущей кнопки в странице (после ответа карточка перерисовывается).
  const look = await page.waitForFunction(() => {
    const b = document.querySelector(".ri-support[aria-pressed=true]");
    const cs = b && b.isConnected ? getComputedStyle(b) : null;
    return cs && cs.backgroundColor ? { bg: cs.backgroundColor, fg: cs.color } : null;
  }, null, { timeout: 5000 }).then((h) => h.jsonValue()).catch(() => ({ bg: "", fg: "" }));
  check(`${tag}: «Вы поддержали» — сплошная тёмная капсула (${look.bg})`, /^rgb\(/.test(look.bg) && contrastOf(look.bg, look.fg) >= 4.5, look);
  const rolled = await page.locator(".ri-votes__n.ri-roll-up").count();
  check(`${tag}: число голосов «перекатилось» (+1)`, rolled === 1, rolled);
  await page.locator(".ri-card summary").first().click();
  await page.waitForTimeout(400);
  verdict(tag + " «Подробнее»", await measure(page, ".ri"), { primaries: 1 });
  await page.locator("[data-key=new]").click();
  await page.waitForSelector(".ri-wizard");
  verdict(tag + " мастер 1", await measure(page, ".ri"), { primaries: 1 });
  check(`${tag}: мастер — полоса из 3 шагов, «Отменить» сверху`, (await page.locator(".ri-progress > i").count()) === 3 && (await page.locator(".ri-wtop [data-key=cancel]").count()) === 1);
  // шаг 2 и 3 — без выбора места (черновик мастера), только вид
  await page.evaluate(() => { const d = JSON.parse(localStorage.getItem("birge.idea.draft")); d.point = [71.40, 51.09]; d.step = 2; localStorage.setItem("birge.idea.draft", JSON.stringify(d)); });
  await page.reload();
  await page.waitForSelector(".ri-wizard #ri-title");
  verdict(tag + " мастер 2", await measure(page, ".ri"), { primaries: 1 });
  check(`${tag}: подсказка про личные данные — один раз`, (await page.locator(".ri-privacy").count()) === 1 && (await page.locator(".ri-wizard .bk-field__hint", { hasText: lang === "kk" ? "ЖСН" : "ИИН" }).count()) === 0);
  await page.fill("#ri-title", lang === "kk" ? "Аулаға орындықтар" : "Скамейки во дворе");
  await page.locator("[data-key=next]").click();
  await page.waitForSelector("[data-key=send]");
  verdict(tag + " мастер 3", await measure(page, ".ri"), { primaries: 1 });
  check(`${tag}: нет ошибок JS`, page.errs.length === 0, page.errs);
  await page.evaluate(() => localStorage.removeItem("birge.idea.draft"));
  await page.context().close();
  // reduced-motion: ни одной анимации в разделе
  const calm = await newPage(browser, width, lang, "resident", { reduced: true });
  await calm.goto(base + "#ideas");
  await calm.waitForSelector(".ri .ri-card", { timeout: 30000 });
  await calm.waitForTimeout(300);
  const m = await measure(calm, ".ri");
  check(`${tag}: prefers-reduced-motion — анимаций нет`, m.anim === 0, m.anim);
  await calm.context().close();
}

async function akimat(browser, base, width, lang) {
  const tag = `${width}-${lang} «Проекты и идеи»`;
  const page = await newPage(browser, width, lang, "akimat");
  await page.goto(base);
  await page.evaluate(async (pw) => {
    await fetch("/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "auditor", password: pw }) });
  }, PASSWORD);
  await page.goto(base + "#projects");
  await page.reload();
  await page.waitForSelector(".ri .ri-card", { timeout: 30000 });
  await page.waitForTimeout(700);
  verdict(tag + " очередь", await measure(page, ".ri"), { primaries: 0 });
  const voting = page.locator(".ri-card", { has: page.locator('.bk-status[data-idea-status="voting"]') }).first();
  await voting.locator("button[data-key^=open-]").click();
  await page.waitForSelector(".ri-checkform");
  verdict(tag + " чек-лист", await measure(page, ".ri"), { primaries: 1, sizes: 5 });
  check(`${tag}: чек-лист — 4 пункта с пояснением и полоса из 4 сегментов`, (await page.locator(".ri-checkform__row .bk-meta").count()) === 4 && (await page.locator(".ri-meter > i").count()) === 4);
  await page.locator("[data-key=tab-projects]").click();
  await page.waitForSelector(".r06-card");
  await page.waitForTimeout(500);
  verdict(tag + " проекты", await measure(page, ".ri"), { primaries: 0, sizes: 5 });
  await page.goto(base + "#works");
  await page.waitForSelector(".rw [data-work]", { timeout: 30000 });
  await page.waitForTimeout(500);
  verdict(`${width}-${lang} «Работы и отключения» список`, await measure(page, ".rw"), { primaries: 1 });
  await page.locator("[data-key=add]").click();
  await page.waitForSelector(".rw-form");
  verdict(`${width}-${lang} «Работы и отключения» форма`, await measure(page, ".rw"), { primaries: 1, sizes: 5 });
  // Даты на одной линии на ноутбуке (подпись «Новый срок…» в две строки не сдвигает поле).
  if (width > 760) {
    const tops = await page.evaluate(() => ["#rw-planned_end", "#rw-forecast_end"].map((s) => Math.round(document.querySelector(s).getBoundingClientRect().top)));
    check(`${width}-${lang} «Работы»: поля сроков на одной линии`, Math.abs(tops[0] - tops[1]) <= 1, tops);
  }
  check(`${tag}: нет ошибок JS`, page.errs.length === 0, page.errs);
  await page.context().close();
}

function contrastOf(bg, fg) {
  const lum = (c) => { const [r, g, b] = (c.match(/[\d.]+/g) || [0, 0, 0]).slice(0, 3).map((v) => { const x = Number(v) / 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const [a, b] = [lum(bg), lum(fg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

(async () => {
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  for (const [width, lang] of [[1366, "ru"], [375, "kk"], [1366, "kk"], [375, "ru"]]) {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r06-design-"));
    const port = await freePort();
    const srv = await start(port, path.join(tmp, "civic.sqlite3"));
    try {
      await resident(browser, `http://127.0.0.1:${port}/`, width, lang).catch((e) => check(`${width}-${lang} житель: прогон`, false, e.message.split("\n")[0]));
      await akimat(browser, `http://127.0.0.1:${port}/`, width, lang).catch((e) => check(`${width}-${lang} акимат: прогон`, false, e.message.split("\n")[0]));
    } finally {
      srv.kill();
      fs.rmSync(tmp, { recursive: true, force: true });
    }
  }
  await browser.close();
  const failed = results.filter((r) => !r.ok).length;
  if (OUT) fs.writeFileSync(OUT, JSON.stringify({ total: results.length, failed, results }, null, 1));
  console.log(`\n${results.length - failed}/${results.length} PASS`);
  process.exit(failed ? 1 : 0);
})();
