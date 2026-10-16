// R04 П3: проверка экрана «Разбор обращений» в оболочке R01 на стенде (Playwright, Chromium из /opt/pw-browsers).
// Не входит в pytest: нужен запущенный стенд с маршрутами intake/* (research/round-15-results/R04/RUN.txt).
//   R04_STAND=http://127.0.0.1:8655 node tests/civic/R04/intake/ui_check_intake.cjs <папка-для-снимков>
// Проверяет 1366 / 1024 / 375 × ru / kk: числа итога = summary ответа, «Почему так» открывается и Esc его сворачивает,
// Tab из поля доходит до «Разобрать», Ctrl+Enter разбирает, нет картинок и эмодзи, нет горизонтальной прокрутки,
// «Создать задачи» -> «Создано N задач в «Обращениях»» (N = summary.ready), повтор — «уже созданы».
// С 16 окт 19:50 (R10 B-134 / B-135): нет «{n}» и сырых ключей, кнопка — подпись и одно число, «Почему так» — с данными,
// контраст текста ≥ 4,5 : 1, в кадрах счётчика итога слово — в форме для показанного числа.
// С 16 окт 20:40 — состояния (1366-ru, 375-kk): не сотрудник, файл .txt / .csv / не UTF-8, 501 строка, идёт разбор,
// «Разобрать другие», ошибки разбора 500 / 413 / 403 / нет связи / 400, пример не загрузился, «Создать задачи» 404 / 503.
const path = require("path");
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) { ({ chromium } = require("/opt/node22/lib/node_modules/playwright")); }
const BASE = process.env.R04_STAND || "http://127.0.0.1:8655";
const PASSWORD = process.env.R04_STAND_PASSWORD || "parol-r04-test";
const OUT = process.argv[2] || null;
const CHROME = process.env.R04_CHROME || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";
const SIZES = [[1366, 900], [1024, 768], [375, 812]];
const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;
const results = [];

// Текст экрана и его фон (с полупрозрачными слоями): контраст WCAG — мелкий текст ≥ 4,5 : 1, крупный (≥ 24 px или
// ≥ 18,66 px жирный) ≥ 3 : 1. Скрытое для глаз (bk-sr-only), выключенные кнопки и фон-картинки не проверяем.
async function lowContrast(page) {
  return page.evaluate(() => {
    const parse = (c) => { const m = /rgba?\(([^)]+)\)/.exec(c || ""); if (!m) return null;
      const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
    const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    const lum = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
    const blend = (t, u) => [0, 1, 2].map((i) => t[i] * t[3] + u[i] * (1 - t[3])).concat([1]);
    const bgOf = (el) => {
      const stack = [];
      for (let e = el; e; e = e.parentElement) {
        const cs = getComputedStyle(e);
        if (cs.backgroundImage && cs.backgroundImage !== "none") return null;
        const c = parse(cs.backgroundColor);
        if (c && c[3] > 0) { stack.push(c); if (c[3] >= 1) break; }
      }
      let base = [255, 255, 255, 1];
      for (let i = stack.length - 1; i >= 0; i--) base = blend(stack[i], base);
      return base;
    };
    const out = [];
    document.querySelectorAll(".bi *").forEach((el) => {
      if (!Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim())) return;
      if (el.closest(".bk-sr-only, [hidden], [disabled], [aria-disabled=true]")) return;
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return;
      const cs = getComputedStyle(el);
      if (cs.visibility === "hidden") return;
      const bg = bgOf(el), c = parse(cs.color);
      if (!bg || !c) return;
      const fg = blend([c[0], c[1], c[2], c[3] * Number(cs.opacity || 1)], bg);
      const a = lum(fg), b = lum(bg), ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
      const size = parseFloat(cs.fontSize), bold = Number(cs.fontWeight) >= 700;
      if (ratio < (size >= 24 || (bold && size >= 18.66) ? 3 : 4.5)) {
        out.push({ text: el.textContent.trim().slice(0, 40), cls: String(el.className || ""), ratio: Math.round(ratio * 100) / 100, size });
      }
    });
    return out.slice(0, 6);
  });
}
function check(name, ok, detail) {
  results.push([name, !!ok]);
  console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : "  " + JSON.stringify(detail).slice(0, 300)));
}

// ---------------------------------------------------------------- состояния экрана (П3: «все состояния»)
// Ожидаемый текст — из словаря оболочки (он главнее запасных текстов экрана); нет ключа — null (сверяем мягче).
async function T(page, key, params) {
  return page.evaluate(([k, p]) => {
    const I = window.BirgeI18n;
    if (typeof I.has === "function" && !I.has(k)) return null;
    return I.t(k, p || {});
  }, [key, params || null]);
}
function same(shown, want) {
  shown = String(shown || "").replace(/\s+/g, " ").trim();
  return want == null ? shown.length > 0 && !/[{}]|\bintake\./.test(shown) : shown === String(want).replace(/\s+/g, " ").trim();
}
async function openIntake(page, lang) {
  const login = await page.request.post(BASE + "/api/civic/v1/session/login",
    { data: { username: "operator", password: PASSWORD }, headers: { Origin: BASE } });
  if (login.status() !== 200) throw new Error("login " + login.status());
  await page.goto(BASE + "/", { waitUntil: "load" });
  await page.waitForFunction(() => window.BirgeShell && window.BirgeIntake && window.BirgeI18n, null, { timeout: 30000 });
  await page.evaluate(async (l) => { await window.BirgeI18n.ready; window.BirgeI18n.setLang(l); }, lang);
  await page.evaluate(() => window.BirgeShell.setMode("akimat"));
  await page.waitForTimeout(400);
  await page.evaluate(() => window.BirgeShell.setSection("intake"));
  await page.waitForSelector(".bi .bi-text", { timeout: 15000 });
}
const ANALYZE = "**/api/civic/v2/intake/analyze", SAMPLE = "**/api/civic/v2/intake/sample", COMMIT = "**/api/civic/v2/intake/commit";
const json = (status, body) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
async function errorTitle(page) {
  await page.waitForSelector(".bi .bi-error", { timeout: 15000 });
  return page.textContent(".bi .bi-error .bk-error__title");
}
async function fieldError(page) {
  await page.waitForSelector(".bi .bk-field__error", { timeout: 15000 });
  return page.textContent(".bi .bk-field__error");
}

async function checkStates(browser, w, hgt, lang) {
  const tag = `states ${w}-${lang}`;
  // 1) Не сотрудник (сессии нет): «для сотрудников акимата», без падений.
  let ctx = await browser.newContext({ viewport: { width: w, height: hgt } });
  let page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await openIntake(page, lang);
  await ctx.clearCookies();
  await page.click(".bi [data-act=sample]");
  check(`${tag} not staff -> staff_only`, same(await errorTitle(page), await T(page, "intake.staff_only")), await page.textContent(".bi .bi-error"));
  await ctx.close();

  ctx = await browser.newContext({ viewport: { width: w, height: hgt } });
  page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  let analyzeCalls = 0;
  page.on("request", (r) => { if (r.url().endsWith("/intake/analyze")) analyzeCalls++; });
  await openIntake(page, lang);
  const field = ".bi .bi-text";

  // 2) Файл .txt: строка = обращение, пустые строки — мимо; счётчик.
  await page.setInputFiles(".bi input[type=file]", { name: "night.txt", mimeType: "text/plain",
    buffer: Buffer.from("﻿Яма на дороге у дома 5\r\nНе вывозят мусор третий день\r\n\r\nСломана скамейка в парке\r\n") });
  await page.waitForFunction(() => (document.querySelector(".bi .bi-text") || {}).value.split("\n").length === 3, null, { timeout: 5000 }).catch(() => null);
  const txt = await page.inputValue(field);
  check(`${tag} file .txt -> 3 lines + count`, txt === "Яма на дороге у дома 5\nНе вывозят мусор третий день\nСломана скамейка в парке"
    && same(await page.textContent(".bi .bi-meter__count"), await T(page, "intake.count", { n: 3 })), txt);

  // 3) Файл .csv: столбец «text», кавычки с разделителем внутри.
  await page.setInputFiles(".bi input[type=file]", { name: "night.csv", mimeType: "text/csv",
    buffer: Buffer.from('id;text;district\n1;Яма на дороге у дома 5;Есиль\n2;"Не горит свет; в подъезде темно";Алматы\n') });
  await page.waitForFunction(() => (document.querySelector(".bi .bi-text") || {}).value.startsWith("Яма на дороге у дома 5\nНе горит"), null, { timeout: 5000 }).catch(() => null);
  const csv = await page.inputValue(field);
  check(`${tag} file .csv -> text column`, csv === "Яма на дороге у дома 5\nНе горит свет; в подъезде темно", csv);

  // 4) Не UTF-8 -> «файл не прочитался», текст в поле не тронут.
  await page.setInputFiles(".bi input[type=file]", { name: "bad.txt", mimeType: "text/plain", buffer: Buffer.from([0x59, 0xc3, 0x28, 0xa0, 0xa1, 0x0a]) });
  check(`${tag} bad file -> error.file`, same(await fieldError(page), await T(page, "intake.error.file")) && await page.inputValue(field) === csv);

  // 5) Больше 500 обращений: счётчик красный, «Разобрать» — подсказка, запроса нет.
  const many = Array.from({ length: 501 }, (_, i) => `Обращение номер ${i + 1}: яма на дороге`).join("\n");
  await page.fill(field, many);
  const before = analyzeCalls;
  check(`${tag} 501 lines -> meter over`, await page.$(".bi .bi-meter.is-over") !== null);
  await page.click(".bi [data-act=run]");
  check(`${tag} 501 lines -> error.too_big, no request`, same(await fieldError(page), await T(page, "intake.error.too_big")) && analyzeCalls === before,
    { calls: analyzeCalls - before });

  // 6) Идёт разбор: «Разбираем N обращений…», секунды идут, заготовка списка; затем итог.
  const three = "Яма на дороге у дома 5\nНе вывозят мусор третий день\nСломана скамейка в парке";
  await page.fill(field, three);
  await page.route(ANALYZE, async (route) => { await new Promise((r) => setTimeout(r, 1500)); await route.continue(); });
  await page.click(".bi [data-act=run]");
  await page.waitForSelector(".bi[data-view=running]", { timeout: 5000 });
  const t1 = await page.textContent(".bi .bi-run__time");
  await page.waitForTimeout(500);
  const t2 = await page.textContent(".bi .bi-run__time");
  check(`${tag} running: count, ticking seconds, skeleton`, same(await page.textContent(".bi .bi-run__count"), await T(page, "intake.running", { n: 3 }))
    && t1 !== t2 && (await page.$$(".bi .bk-lrow--skel")).length >= 3, { t1, t2 });
  await page.waitForSelector(".bi-sum__line", { timeout: 15000 });
  await page.unroute(ANALYZE);
  const total = await page.$eval(".bi-sum__line .bi-num", (e) => Number(e.getAttribute("data-value")));
  check(`${tag} running -> result (3 texts)`, total === 3, total);

  // 7) «Разобрать другие» — снова поле, текст на месте, фокус в поле.
  await page.click(".bi [data-act=again]");
  await page.waitForSelector(".bi[data-view=input]", { timeout: 5000 });
  check(`${tag} again -> input, text kept, focus`, await page.inputValue(field) === three
    && await page.evaluate(() => document.activeElement && document.activeElement.classList.contains("bi-text")));

  // 8) Ошибки разбора: 500, 413, 403, нет связи — блок ошибки, текст в поле не потерян; 400 — подсказка поля.
  for (const [name, reply, key] of [["500", json(500, { ok: false, error: "internal" }), "intake.error.text"],
                                    ["413", json(413, { ok: false, error: "payload_too_large" }), "intake.error.server_size"],
                                    ["403", json(403, { ok: false, error: "forbidden" }), "intake.staff_only"],
                                    ["network", null, "common.state.network_title"]]) {
    await page.route(ANALYZE, (route) => (reply ? route.fulfill(reply) : route.abort("connectionrefused")));
    await page.click(".bi [data-act=run]");
    const title = await errorTitle(page);
    check(`${tag} analyze ${name} -> ${key}`, same(title, await T(page, key)) && await page.inputValue(field) === three, title);
    await page.unroute(ANALYZE);
  }
  const msg = "Не больше 500 обращений за раз.";
  await page.route(ANALYZE, (route) => route.fulfill(json(400, { ok: false, error: "bad_request", message: msg })));
  await page.click(".bi [data-act=run]");
  const e400 = await fieldError(page);
  check(`${tag} analyze 400 -> server text (ru) / own text (kk)`, same(e400, lang === "ru" ? msg : await T(page, "intake.error.text")), e400);
  await page.unroute(ANALYZE);
  await page.route(ANALYZE, (route) => route.fulfill({ status: 400, contentType: "text/plain", body: "" }));
  await page.fill(field, three + "\nЕщё одно обращение про яму");
  await page.click(".bi [data-act=run]");
  const e400b = await fieldError(page);
  check(`${tag} analyze 400 without text -> no «request failed»`, same(e400b, await T(page, "intake.error.text")), e400b);
  await page.unroute(ANALYZE);

  // 9) Пример не загрузился: ошибка с «Повторить»; повтор — пример в поле.
  await page.route(SAMPLE, (route) => route.fulfill(json(500, { ok: false, error: "internal" })));
  await page.click(".bi [data-act=sample]");
  const se = await errorTitle(page);
  const retry = await page.$(".bi .bi-error .bk-btn");
  check(`${tag} sample 500 -> error.sample + retry`, same(se, await T(page, "intake.error.sample")) && retry !== null, se);
  await page.unroute(SAMPLE);
  if (retry) await retry.click();
  await page.waitForFunction(() => (document.querySelector(".bi .bi-text") || {}).value.length > 100, null, { timeout: 15000 }).catch(() => null);
  check(`${tag} sample retry -> sample in the field`, (await page.inputValue(field)).length > 100);

  // 10) «Создать задачи»: 404 — разбор устарел (повтор — к полю), 503 — хранилище (повтор — создаёт).
  await page.click(".bi [data-act=run]");
  await page.waitForSelector(".bi-sum__line", { timeout: 15000 });
  await page.route(COMMIT, (route) => route.fulfill(json(404, { ok: false, error: "not_found" })));
  await page.click(".bi [data-act=commit]");
  check(`${tag} commit 404 -> error.expired`, same(await errorTitle(page), await T(page, "intake.error.expired")));
  await page.unroute(COMMIT);
  await page.click(".bi .bi-error .bk-btn");
  await page.waitForSelector(".bi[data-view=input]", { timeout: 5000 }).catch(() => null);
  check(`${tag} expired retry -> input`, await page.getAttribute(".bi", "data-view") === "input");
  await page.click(".bi [data-act=run]");
  await page.waitForSelector(".bi-sum__line", { timeout: 15000 });
  await page.route(COMMIT, (route) => route.fulfill(json(503, { ok: false, error: "unavailable" })));
  await page.click(".bi [data-act=commit]");
  check(`${tag} commit 503 -> error.store`, same(await errorTitle(page), await T(page, "intake.error.store")));
  await page.unroute(COMMIT);
  await page.click(".bi .bi-error .bk-btn");
  await page.waitForSelector(".bi .bi-done", { timeout: 15000 }).catch(() => null);
  check(`${tag} store retry -> created / already created`, await page.$(".bi .bi-done") !== null);
  check(`${tag} no page errors`, errors.length === 0, errors);
  await ctx.close();
}

(async () => {
  const browser = await chromium.launch(require("fs").existsSync(CHROME) ? { executablePath: CHROME } : {});
  for (const [w, h] of SIZES) {
    for (const lang of ["ru", "kk"]) {
      const tag = `${w}-${lang}`;
      const ctx = await browser.newContext({ viewport: { width: w, height: h } });
      const page = await ctx.newPage();
      const pageErrors = [];
      page.on("pageerror", (e) => pageErrors.push(e.message));
      const login = await page.request.post(BASE + "/api/civic/v1/session/login",
        { data: { username: "operator", password: PASSWORD }, headers: { Origin: BASE } });
      check(`${tag} staff login`, login.status() === 200, login.status());
      await page.goto(BASE + "/", { waitUntil: "load" });
      await page.waitForFunction(() => window.BirgeShell && window.BirgeIntake && window.BirgeI18n, null, { timeout: 30000 });
      await page.evaluate(async (l) => { await window.BirgeI18n.ready; window.BirgeI18n.setLang(l); }, lang);
      await page.evaluate(() => window.BirgeShell.setMode("akimat"));
      await page.waitForTimeout(400);
      await page.evaluate(() => window.BirgeShell.setSection("intake"));
      await page.waitForSelector(".bi .bi-text", { timeout: 15000 });
      const title = await page.textContent(".bi-title");
      check(`${tag} title`, title === (lang === "kk" ? "Өтініштерді талдау" : "Разбор обращений"), title);
      if (OUT) await page.screenshot({ path: path.join(OUT, `${tag}-1-input.png`) });

      // Tab из поля — к «Разобрать»; пустое поле -> подсказка, без запроса
      await page.focus(".bi-text");
      await page.keyboard.press("Tab");
      const focused = await page.evaluate(() => document.activeElement && document.activeElement.getAttribute("data-act"));
      check(`${tag} Tab: field -> «Разобрать»`, focused === "run", focused);
      await page.keyboard.press("Enter");
      check(`${tag} empty -> field error`, await page.isVisible(".bi .bk-field__error"));

      await page.click(".bi [data-act=sample]");
      await page.waitForFunction(() => (document.querySelector(".bi-text") || {}).value.length > 100);
      if (OUT) await page.screenshot({ path: path.join(OUT, `${tag}-2-sample.png`) });
      const apiRes = page.waitForResponse((r) => r.url().endsWith("/intake/analyze") && r.request().method() === "POST");
      // Кадры счётчика (~0,7 с) смотрит сама страница — с каждого кадра, ещё до ответа сервера (иначе под нагрузкой
      // проверка начинала смотреть после конца анимации). Слово — в форме для показанного числа (R10 §16 п. 4).
      await page.evaluate(() => {
        const I = window.BirgeI18n, rec = { bad: [], seen: [] };
        const strip = (x) => String(x).replace(/[\d\s\u00a0\u202f]/g, "");
        window.__r04frames = rec;
        const t0 = performance.now();
        (function loop() {
          document.querySelectorAll(".bi-sum__line .bi-sum__part").forEach((el) => {
            const b = el.querySelector(".bi-num");
            if (!b) return;
            const n = Number(b.textContent.replace(/\D/g, ""));
            if (el.getAttribute("data-key") === "texts" && !rec.seen.includes(n)) rec.seen.push(n);
            const want = I.t("intake.sum." + el.getAttribute("data-key"), { n });
            if (strip(el.textContent) !== strip(want) && rec.bad.length < 4) rec.bad.push([el.textContent, want]);
          });
          if (performance.now() - t0 < 8000) requestAnimationFrame(loop);
        })();
      });
      await page.focus(".bi-text");
      await page.keyboard.press("Control+Enter");
      const res = await (await apiRes).json();
      const data = res && res.ok === true && res.data ? res.data : res;
      await page.waitForSelector(".bi-sum__line", { timeout: 15000 });
      await page.waitForTimeout(900);   // счёт чисел до итога
      const frames = await page.evaluate(() => ({ bad: window.__r04frames.bad, values: window.__r04frames.seen.length }));
      check(`${tag} count-up: word form follows the shown number`, frames.bad.length === 0 && frames.values >= 3, frames);
      const shown = await page.$$eval(".bi-sum__line .bi-num", (els) => els.map((e) => Number(e.getAttribute("data-value"))));
      const s = data.summary;
      check(`${tag} summary numbers = API summary`, JSON.stringify(shown) === JSON.stringify([s.total, s.tasks, s.services, s.urgent, s.merged]), { shown, s });
      check(`${tag} demo label`, data.demo === true && await page.isVisible(".bi-head .bk-tag--demo"));
      const rows = await page.$$eval(".bi-row", (els) => els.length);
      check(`${tag} one row per task`, rows === data.tasks.length, { rows, tasks: data.tasks.length });
      const urgentFirst = await page.$eval(".bi-gsec", (el) => el.classList.contains("is-urgent"));
      check(`${tag} urgent group first`, s.urgent ? urgentFirst : true);
      const media = await page.$$eval(".bi img, .bi picture, .bi canvas, .bi video", (els) => els.length);
      const text = await page.textContent(".bi");
      check(`${tag} no images or emoji (P1)`, media === 0 && !EMOJI.test(text), { media });
      check(`${tag} no PII on screen`, !/87011234567|880101300123/.test(text));
      const seenText = await page.innerText(".bi");
      check(`${tag} no {placeholders} or raw keys (B-134)`, !/\{[a-z_]+\}|\bintake\.[a-z_.]+/.test(seenText),
        (seenText.match(/.{0,30}(\{[a-z_]+\}|\bintake\.[a-z_.]+).{0,30}/) || [])[0]);
      const btn = await page.$eval(".bi [data-act=commit]", (b) => {   // видимая подпись: без текста для читалки экрана
        const c = b.cloneNode(true);
        c.querySelectorAll(".bk-sr-only").forEach((e) => e.remove());
        return c.textContent.replace(/\s+/g, " ").trim();
      });
      check(`${tag} create button: label + one number (B-134)`, !/[{}]/.test(btn) && (btn.match(/\d[\d\s\u00a0\u202f]*/g) || []).length === 1
        && Number(btn.replace(/\D/g, "")) === s.ready, btn);
      check(`${tag} small text contrast ≥ 4.5:1 (B-135)`, (await lowContrast(page)).length === 0, await lowContrast(page));
      if (OUT) await page.screenshot({ path: path.join(OUT, `${tag}-3-result.png`) });

      const target = await page.$$(".bi-row");
      await target[Math.min(7, target.length - 1)].click();
      check(`${tag} «Почему так» opens`, await page.$$eval(".bi-task.is-open .bi-why:not([hidden])", (e) => e.length) === 1);
      const why = await page.$$eval(".bi-task.is-open .bi-why__line", (els) => els.map((e) => e.textContent.replace(/\s+/g, " ").trim()));
      check(`${tag} «Почему так» lines carry data (B-134)`, why.length >= 3 && /:\s*\S{2,}/.test(why[0]) && /:\s*\S{2,}/.test(why[1])
        && !why.some((l) => /[{}]/.test(l)), why);
      check(`${tag} «Почему так» contrast ≥ 4.5:1`, (await lowContrast(page)).length === 0, await lowContrast(page));
      if (OUT) {
        await (await page.$(".bi-task.is-open")).scrollIntoViewIfNeeded();
        await page.screenshot({ path: path.join(OUT, `${tag}-4-why.png`) });
      }
      await page.keyboard.press("Escape");
      check(`${tag} Esc collapses`, await page.$$eval(".bi-task.is-open", (e) => e.length) === 0);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      check(`${tag} no horizontal scroll`, overflow <= 0, overflow);

      if (w === 1366) {
        const commitRes = page.waitForResponse((r) => r.url().endsWith("/intake/commit"));
        await page.click(".bi [data-act=commit]");
        const raw = await (await commitRes).json();
        const done = raw && raw.ok === true && raw.data ? raw.data : raw;
        await page.waitForSelector(".bi-done", { timeout: 15000 });
        const banner = await page.textContent(".bi-done .bk-banner__title");
        // ready = новые записи (created; при повторе — existing) + задачи к уже открытым обращениям (joined_existing)
        check(`${tag} commit: created + existing + joined_existing = ready`,
          done.created + done.existing + (done.joined_existing || 0) === s.ready && done.failed === 0, done);
        check(`${tag} commit banner`, done.created ? banner.includes(String(done.created)) && /Создан|жасалды|құрылды/.test(banner)
          : done.existing ? /уже создан|бұрын жасалған|бұрын құрылған/.test(banner) : /открыт|ашық/.test(banner), banner);
        if (OUT) await page.screenshot({ path: path.join(OUT, `${tag}-5-commit.png`) });
      }
      check(`${tag} no page errors`, pageErrors.length === 0, pageErrors);
      await ctx.close();
    }
  }
  for (const [w, hgt, lang] of [[1366, 900, "ru"], [375, 812, "kk"]]) await checkStates(browser, w, hgt, lang);
  await browser.close();
  const ok = results.filter((r) => r[1]).length;
  console.log(`SUMMARY ${ok} / ${results.length}`);
  process.exit(ok === results.length ? 0 : 1);
})().catch((e) => { console.error("FAILED", e); process.exit(1); });
