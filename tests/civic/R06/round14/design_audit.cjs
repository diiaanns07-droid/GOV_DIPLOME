// R06 · эталон 13 окт (research/round-14/design/REFERENCE.html, вариант A + 7 правил Linear): аудит экранов R06 в
// НАСТОЯЩЕЙ сборке R01. Нормы эталона: кегли только из шкалы эталона (12/13/14/15/16/18/19, «Работы» — от 13), веса
// 400/500/600; лист «Проекты и идеи» и карточка выбранного — размеры эталона (картинка 84 и 150, поля 10, радиусы
// 12/16/18, капсула ♥ 32, кнопки 44, карточка 340 справа 84 сверху 132); одна главная кнопка; зоны нажатия ≥ 44; без
// рамок у плашек (стекло — своя кромка) и старых цветов; лайм — только значок «Предложить идею»; нет прокрутки вбок;
// reduced-motion выключает анимации; поддержка — сразу (до ответа сервера).
//
//   NODE_PATH="$(npm root -g)" node tests/civic/R06/round14/design_audit.cjs <дерево сборки> [out.json]
//
// Сервер — python3 -B app.py дерева с CIVIC_DEMO=1 на временной базе (как app_r01_wave2.cjs), сотрудник со случайным
// паролем. Экраны: «Проекты и идеи» жителя (лист, карточка выбранного, «Подробнее», мастер 1–3), акимата (лист, проверка,
// проекты), «Работы и отключения» (список, форма) — 1366×768 и 375×812, ru и kk. Демо — synthetic.
// Лист 412 слева — патч R01 (research/round-14-results/R06/reference/r01_projects_sheet.css): без него место листа — NOT_RUN.
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
async function measure(page, sel, minPx = 12) {
  // Указатель — с экрана: кнопка под ним в середине перехода «наведение» (фон и кромка меняются с разной скоростью) — не рамка.
  await page.mouse.move(1, 1);
  await page.waitForTimeout(250);
  return page.evaluate(([sel, minPx]) => {
    const LIME = [215, 245, 124];
    const LEGACY = ["#176b4a", "#125d40", "#f1fbd6", "#b6d65a", "#f7f8f4", "#f1efe6", "#eaf2fb", "#e6f1eb", "#eef2ea", "#c9d4c5", "#f3efe6", "#f6f3ea", "#eef1ea"]
      .map((h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)));
    const parse = (c) => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const v = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return v.length >= 3 && (v[3] === undefined || v[3] > 0.05) ? v.slice(0, 3) : null; };
    const legacy = (c) => { const v = parse(c); return v && LEGACY.some((l) => Math.abs(v[0] - l[0]) + Math.abs(v[1] - l[1]) + Math.abs(v[2] - l[2]) <= 4); };
    const roots = Array.from(document.querySelectorAll(sel));
    const out = { sizes: {}, tiny: [], weight: [], framed: [], legacy: [], lime: [], small: [], clipped: [], primaries: 0, anim: 0, overflow: document.scrollingElement.scrollWidth - innerWidth };
    const lime = (c) => { const v = parse(c); return v && Math.abs(v[0] - LIME[0]) + Math.abs(v[1] - LIME[1]) + Math.abs(v[2] - LIME[2]) <= 4; };
    const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && !e.closest("details:not([open]) > :not(summary)"); };
    for (const root of roots) for (const e of root.querySelectorAll("*")) {
      if (!vis(e) || e.closest("svg")) continue;
      const s = getComputedStyle(e);
      const own = [...e.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim());
      const text = own ? e.textContent.trim().slice(0, 30) : "";
      if (own && !e.closest(".bk-sr-only") && !/^H1$/.test(e.tagName) && !e.classList.contains("bk-h1")) {
        out.sizes[s.fontSize] = (out.sizes[s.fontSize] || 0) + 1;
        if (parseFloat(s.fontSize) < minPx) out.tiny.push(s.fontSize + " «" + text + "»");
        if (!["400", "500", "600"].includes(s.fontWeight)) out.weight.push(s.fontWeight + " «" + text + "»");
        if (legacy(s.color)) out.legacy.push("color «" + text + "»");
      }
      if (legacy(s.backgroundColor)) out.legacy.push("background " + (e.className || e.tagName));
      if (lime(s.backgroundColor) && !e.closest(".ri-newbtn__ic")) out.lime.push(String(e.className || e.tagName).slice(0, 40));
      const bw = parseFloat(s.borderTopWidth);
      if (!/INPUT|SELECT|TEXTAREA/.test(e.tagName) && bw >= 1 && bw <= 2 && s.borderTopStyle !== "none" && parseFloat(s.borderRightWidth) >= 1
        && parseFloat(s.borderBottomWidth) >= 1 && parseFloat(s.borderRadius) >= 6 && e.getBoundingClientRect().width > 60 && parse(s.borderTopColor)
        && s.borderTopColor !== s.backgroundColor  // рамка цвета заливки (главная кнопка, выбранный чип) — не рамка
        && !e.classList.contains("bk-btn--danger") && !e.classList.contains("bk-glass")) out.framed.push(String(e.className || e.tagName).slice(0, 40));
      if (/^(BUTTON|SUMMARY|A|SELECT|INPUT)$/.test(e.tagName) || e.getAttribute("role") === "tab") {
        const r = e.getBoundingClientRect();
        // Зона нажатия = видимая высота + невидимое расширение ::after (ui-kit: чип и сегмент 40 px + 4 px сверху и снизу).
        const a = getComputedStyle(e, "::after");
        let zone = a.content !== "none" && a.position === "absolute" ? r.height - Math.min(0, parseFloat(a.top) || 0) - Math.min(0, parseFloat(a.bottom) || 0) : r.height;
        // Название карточки списка — растянутая зона на всю карточку (::after inset 0 от .ri-pc).
        if (e.classList.contains("ri-pc__open")) zone = e.closest(".ri-pc").getBoundingClientRect().height;
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
  }, [sel, minPx]);
}
// Шкала кеглей эталона (REFERENCE.html вариант A и токены R11 3890fa74): 12 подписи, 13 мета/сегмент, 14 текст, 15 названия и
// кнопки, 16 цифры, 18 заголовок карточки, 19 заголовок листа; формы мастера и «Работ» — ещё 17 (поля ui-kit) и 22 (шаг).
const SCALE = ["12px", "13px", "14px", "15px", "16px", "18px", "19px"];
function verdict(tag, m, opts) {
  const sizes = Object.keys(m.sizes).sort((a, b) => parseFloat(a) - parseFloat(b));
  const scale = SCALE.concat(opts.extra || []);
  const off = sizes.filter((x) => !scale.includes(x));
  check(`${tag}: кегли из шкалы эталона (${sizes.join(" / ")}), ≥ ${opts.min || 12}, веса 400/500/600`, off.length === 0 && m.tiny.length === 0 && m.weight.length === 0,
    { off, tiny: m.tiny.slice(0, 4), weight: m.weight.slice(0, 4) });
  check(`${tag}: без рамок у плашек и старых цветов, лайм — только значок «Предложить идею»`, m.framed.length === 0 && m.legacy.length === 0 && m.lime.length === 0,
    m.framed.concat(m.legacy, m.lime).slice(0, 6));
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

// Размеры эталона «Проекты и идеи» (кадр 3 REFERENCE.html): лист, сегмент, карточки списка, капсула ♥, карточка выбранного.
async function geometry(page, tag, wideScreen, wide) {
  const g = await page.evaluate(() => {
    const r = (e) => e && e.getBoundingClientRect();
    const cs = (e) => e && getComputedStyle(e);
    const sheet = document.querySelector("#birge-screen");
    const cards = Array.from(document.querySelectorAll(".ri-plist > .ri-pc")).filter((c) => r(c).height > 0);
    const c0 = cards[0], c1 = cards[1];
    const sel = document.querySelector(".ri-pc[aria-current=true]");
    const seg = document.querySelector(".ri-seg > button[aria-selected=true]");
    const title = document.querySelector(".ri-sheet-title");
    const thumb = c0 && c0.querySelector(".ri-kind"), vote = document.querySelector(".ri-plist .ri-vote"), pill = c0 && c0.querySelector(".ri-pill");
    const pd = document.querySelector(".ri-pd-host .ri-pd") || document.querySelector(".ri-pd");
    const im = pd && pd.querySelector(".ri-pd__im"), facts = pd ? pd.querySelectorAll(".ri-fact").length : 0;
    const acts = pd ? Array.from(pd.querySelectorAll(".ri-pd__acts > .bk-btn")).map((b) => Math.round(r(b).height)) : [];
    const text = pd && pd.querySelector(".ri-pd__text"), note = pd && pd.querySelector(".ri-pd__note"), h3 = pd && pd.querySelector(".ri-pd__title");
    return {
      fsXs: getComputedStyle(document.documentElement).getPropertyValue("--fs-xs").trim() || "12px",
      sheet: sheet && { l: Math.round(r(sheet).left), t: Math.round(r(sheet).top), w: Math.round(r(sheet).width), rad: cs(sheet).borderTopLeftRadius },
      title: title && [cs(title).fontSize, cs(title).fontWeight],
      seg: seg && [cs(seg).fontSize, cs(seg).fontWeight],
      card: c0 && { pad: cs(c0).paddingTop, rad: cs(c0).borderTopLeftRadius, gap: c1 ? Math.round(r(c1).top - r(c0).bottom) : 10,
        title: [cs(c0.querySelector(".ri-pc__title")).fontSize, cs(c0.querySelector(".ri-pc__title")).fontWeight], sub: cs(c0.querySelector(".ri-pc__sub")).fontSize },
      thumb: thumb && [Math.round(r(thumb).width), Math.round(r(thumb).height), cs(thumb).borderTopLeftRadius],
      pill: pill && [cs(pill).fontSize, cs(pill).fontWeight],
      vote: vote && [Math.round(r(vote).height), cs(vote).fontSize, cs(vote).fontWeight],
      ring: sel && cs(sel).boxShadow,
      pd: pd && { l: Math.round(r(pd).left), t: Math.round(r(pd).top), w: Math.round(r(pd).width), right: Math.round(innerWidth - r(pd).right),
        im: im && Math.round(r(im).height), facts, acts, h3: h3 && [cs(h3).fontSize, cs(h3).fontWeight],
        text: text && [cs(text).fontSize, cs(text).webkitLineClamp], note: note && cs(note).fontSize },
    };
  });
  if (wideScreen && g.sheet && g.sheet.w === 412) {
    check(`${tag}: лист 412 слева под поиском (20, 84, радиус 18)`, g.sheet.l === 20 && g.sheet.t === 84 && g.sheet.rad === "18px", g.sheet);
  } else if (wideScreen) {
    console.log(`NOT_RUN ${tag}: лист 412 — нет патча R01 (r01_projects_sheet.css), лист ${JSON.stringify(g.sheet)}`);
  }
  check(`${tag}: заголовок листа 19/600, сегмент 13/500`, g.title && g.title.join() === "19px,600" && g.seg && g.seg.join() === "13px,500", { title: g.title, seg: g.seg });
  check(`${tag}: карточка — поля 10, радиус 16, промежуток 10; название 15/600, строка 13`, g.card && g.card.pad === "10px" && g.card.rad === "16px"
    && g.card.gap === 10 && g.card.title.join() === "15px,600" && g.card.sub === "13px", g.card);
  // П1 (поправка владельца 15 окт): вместо картинки 84 — плитка 48 со значком вида объекта (набор R11).
  // Кегль плашки — токен --fs-xs сборки: 12 в ui-kit FINAL-4, 13 у R11 раунда 15 («мельче 13 px текста нет», B-112).
  check(`${tag}: значок вида 48 × 48, радиус 12; плашка ${g.fsXs}/600; капсула ♥ 32, 13/600`, g.thumb && g.thumb.join() === "48,48,12px" && g.pill && g.pill.join() === g.fsXs + ",600"
    && (!g.vote || g.vote.join() === "32,13px,600"), { thumb: g.thumb, pill: g.pill, vote: g.vote });
  if (wide) {
    check(`${tag}: выбранная — рамка 2 px цвета текста`, /0px 0px 0px 2px/.test(g.ring || ""), g.ring);
    // П1: в карточке выбранного больших картинок нет (было — картинка 150 эталона A).
    check(`${tag}: карточка выбранного 340 — справа 84, сверху 132; без картинки, 3 цифры, кнопки 44`, g.pd && g.pd.w === 340 && g.pd.right === 84 && g.pd.t === 132
      && !g.pd.im && g.pd.facts === 3 && g.pd.acts.length >= 1 && g.pd.acts.every((x) => x === 44), g.pd);
    check(`${tag}: заголовок карточки 18/600, одно предложение 14 (≤ 2 строк), строка «это опрос» ${g.fsXs}`, g.pd && g.pd.h3.join() === "18px,600" && g.pd.note === g.fsXs
      && (!g.pd.text || (g.pd.text[0] === "14px" && g.pd.text[1] === "2")), g.pd);
  }
}

async function resident(browser, base, width, lang) {
  const tag = `${width}-${lang} «Проекты и идеи» житель`;
  const page = await newPage(browser, width, lang, "resident");
  await page.goto(base + "#ideas");
  await page.waitForSelector(".ri .ri-pc", { timeout: 30000 });
  await page.waitForTimeout(900);
  // Карточка выбранного справа — на листе 412 (патч R01); иначе — под строкой списка (R11 §21.4).
  const wide = width > 760 && await page.evaluate(() => document.querySelector(".ri").getBoundingClientRect().width <= 440);
  verdict(tag + " лист", await measure(page, ".ri, .ri-pd-host"), { primaries: wide ? 1 : 0 });
  await geometry(page, tag, width > 760, wide);
  // Поддержать в списке — сразу (оптимистично): число и капсула меняются до ответа сервера (правило 4 эталона).
  await page.route("**/support", async (route) => { await sleep(700); await route.continue(); });
  const n0 = await page.locator(".ri-plist [data-key^=support-] .ri-vote__n").first().innerText();
  await page.locator(".ri-plist [data-key^=support-]").first().click();
  await page.waitForTimeout(120);
  const quick = await page.evaluate(() => { const b = document.querySelector(".ri-plist [data-key^=support-]"); return b && [b.getAttribute("aria-pressed"), b.querySelector(".ri-vote__n").textContent]; });
  check(`${tag}: «Поддержать» — отклик сразу, до ответа сервера (${n0} → ${quick && quick[1]})`, quick && quick[0] === "true" && quick[1] !== n0, quick);
  await page.waitForFunction(() => !document.querySelector(".ri-plist .ri-roll-up") || true);
  await page.waitForTimeout(900);
  await page.unroute("**/support");
  const look = await page.evaluate(() => {
    const b = document.querySelector(".ri-plist .ri-vote[aria-pressed=true]");
    const cs = b ? getComputedStyle(b) : null;
    return cs ? { bg: cs.backgroundColor, fg: cs.color, heart: getComputedStyle(b.querySelector(".ri-heart path")).fill } : { bg: "", fg: "", heart: "" };
  });
  check(`${tag}: «Вы поддержали» — сердце заполнено, число читается (≥ 4.5:1)`, look.heart && look.heart !== "none" && contrastOf(look.bg, look.fg) >= 4.5, look);
  if (!wide) {
    await page.locator(".ri-plist .ri-pc__open").first().click();
    await page.waitForSelector(".ri-pd--inline");
    await page.waitForTimeout(300);
    verdict(tag + " карточка под строкой", await measure(page, ".ri"), { primaries: 1 });
  }
  await page.locator(".ri-pd [data-key=pd-more]").click();
  await page.waitForTimeout(400);
  verdict(tag + " «Подробнее»", await measure(page, ".ri, .ri-pd-host"), { primaries: 1 });
  await page.locator("[data-key=new]").click();
  await page.waitForSelector(".ri-wizard");
  verdict(tag + " мастер 1", await measure(page, ".ri, .ri-pd-host"), { primaries: 1, extra: ["17px", "22px"] });
  check(`${tag}: мастер — полоса из 3 шагов, «Отменить» сверху, карточки выбранного нет`, (await page.locator(".ri-progress > i").count()) === 3
    && (await page.locator(".ri-wtop [data-key=cancel]").count()) === 1 && (await page.locator(".ri-pd-host").count()) === 0);
  // шаг 2 и 3 — без выбора места (черновик мастера), только вид
  await page.evaluate(() => { const d = JSON.parse(localStorage.getItem("birge.idea.draft")); d.point = [71.40, 51.09]; d.step = 2; localStorage.setItem("birge.idea.draft", JSON.stringify(d)); });
  await page.reload();
  await page.waitForSelector(".ri-wizard #ri-title");
  verdict(tag + " мастер 2", await measure(page, ".ri"), { primaries: 1, extra: ["17px", "22px"] });
  check(`${tag}: подсказка про личные данные — один раз`, (await page.locator(".ri-privacy").count()) === 1 && (await page.locator(".ri-wizard .bk-field__hint", { hasText: lang === "kk" ? "ЖСН" : "ИИН" }).count()) === 0);
  await page.fill("#ri-title", lang === "kk" ? "Аулаға орындықтар" : "Скамейки во дворе");
  await page.locator("[data-key=next]").click();
  await page.waitForSelector("[data-key=send]");
  verdict(tag + " мастер 3", await measure(page, ".ri"), { primaries: 1, extra: ["17px", "22px"] });
  check(`${tag}: нет ошибок JS`, page.errs.length === 0, page.errs);
  await page.evaluate(() => localStorage.removeItem("birge.idea.draft"));
  await page.context().close();
  // reduced-motion: ни одной анимации в разделе (и у карточки выбранного)
  const calm = await newPage(browser, width, lang, "resident", { reduced: true });
  await calm.goto(base + "#ideas");
  await calm.waitForSelector(".ri .ri-pc", { timeout: 30000 });
  await calm.waitForTimeout(400);
  const m = await measure(calm, ".ri, .ri-pd-host");
  check(`${tag}: prefers-reduced-motion — анимаций нет`, m.anim === 0, m.anim);
  await calm.context().close();
}

async function akimat(browser, base, width, lang) {
  const tag = `${width}-${lang} «Проекты и идеи» акимат`;
  let wide = width > 760;
  const page = await newPage(browser, width, lang, "akimat");
  await page.goto(base);
  await page.evaluate(async (pw) => {
    await fetch("/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "auditor", password: pw }) });
  }, PASSWORD);
  await page.goto(base + "#projects");
  await page.reload();
  await page.waitForSelector(".ri .ri-pc", { timeout: 30000 });
  await page.waitForTimeout(900);
  wide = wide && await page.evaluate(() => document.querySelector(".ri").getBoundingClientRect().width <= 440);
  verdict(tag + " лист", await measure(page, ".ri, .ri-pd-host"), { primaries: wide ? 1 : 0 });
  await geometry(page, tag, width > 760, wide);
  // Идея на голосовании → «Проверить» → чек-лист в карточке выбранного.
  await page.locator(".ri-pc[data-idea-status=voting] .ri-pc__open").first().click();
  await page.locator(".ri-pd [data-key=pd-check]").click();
  await page.waitForSelector(".ri-pd .ri-checkform");
  verdict(tag + " чек-лист", await measure(page, ".ri, .ri-pd-host"), { primaries: 1 });
  check(`${tag}: чек-лист — 4 пункта с пояснением и полоса из 4 сегментов`, (await page.locator(".ri-checkform__row .bk-meta").count()) === 4 && (await page.locator(".ri-meter > i").count()) === 4);
  await page.locator("[data-key=tab-projects]").click();
  await page.waitForSelector(".ri-pc[data-proposal]");
  await page.waitForTimeout(500);
  verdict(tag + " проекты", await measure(page, ".ri, .ri-pd-host"), { primaries: wide ? 1 : 0 });
  await page.goto(base + "#works");
  await page.waitForSelector(".rw [data-work]", { timeout: 30000 });
  await page.waitForTimeout(500);
  verdict(`${width}-${lang} «Работы и отключения» список`, await measure(page, ".rw", 13), { primaries: 1, min: 13, extra: ["17px", "22px"] });
  await page.locator("[data-key=add]").click();
  await page.waitForSelector(".rw-form");
  verdict(`${width}-${lang} «Работы и отключения» форма`, await measure(page, ".rw", 13), { primaries: 1, min: 13, extra: ["17px", "22px"] });
  // Даты на одной линии на ноутбуке (подпись «Новый срок…» в две строки не сдвигает поле).
  if (width > 760) {
    const tops = await page.evaluate(() => ["#rw-planned_end", "#rw-forecast_end"].map((s) => Math.round(document.querySelector(s).getBoundingClientRect().top)));
    check(`${width}-${lang} «Работы»: поля сроков на одной линии`, Math.abs(tops[0] - tops[1]) <= 1, tops);
  }
  check(`${tag}: нет ошибок JS`, page.errs.length === 0, page.errs);
  await page.context().close();
}

// Контраст WCAG; полупрозрачный фон кладётся на белый (капсула на карточке листа).
function contrastOf(bg, fg) {
  const rgb = (c) => { const v = (c.match(/[\d.]+/g) || [0, 0, 0]).map(Number); const a = v.length > 3 ? v[3] : 1; return v.slice(0, 3).map((x) => x * a + 255 * (1 - a)); };
  const lum = (c) => { const [r, g, b] = rgb(c).map((v) => { const x = v / 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
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
