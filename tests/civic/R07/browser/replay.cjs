// R07 раунд 15: «Хроника города» в браузере — открыть, клавиши, неделя за 10–20 с, Esc без мигания, состояния
// (ошибка, не подключено, пусто), «меньше движения», 1366 / 1024 / 375 × ru / kk, кадры для R14 и R10.
// Стенд: python -m ui.civic_heat.devserver --world        (мини-мир R07: буран в Нуре 6–3 дня назад)
// Запуск: NODE_PATH=$(npm root -g) node tests/civic/R07/browser/replay.cjs [папка кадров]
// R07_BASE — адрес страницы (по умолчанию стенд R07 на 8617). Итог — строки PASS / FAIL и report.json в папке кадров.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.R07_BASE || "http://127.0.0.1:8617/civic/heat/demo.html";
const OUT = process.argv[2] || path.join(__dirname, "..", "..", "..", "..", "research", "round-15-results", "R07", "screens");
fs.mkdirSync(OUT, { recursive: true });
const SIZES = { 1366: { width: 1366, height: 768 }, 1024: { width: 1024, height: 768 }, 375: { width: 375, height: 812 } };
const results = [];
const check = (name, problems, extra) => {
  results.push({ name, pass: !problems.length, problems, extra });
  console.log((problems.length ? "FAIL " : "PASS ") + name + (problems.length ? " · " + problems.join("; ") : ""));
};

async function open(browser, size, lang, query, opts) {
  const ctx = await browser.newContext({ viewport: SIZES[size], deviceScaleFactor: 1, reducedMotion: (opts && opts.reduced) ? "reduce" : "no-preference" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
  if (opts && opts.route) await page.route("**/api/civic/v2/heat/replay**", opts.route);
  await page.goto(`${BASE}?lang=${lang}&role=akimat&view=city${query || ""}`, { waitUntil: "load" });
  await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
  await page.waitForTimeout(600);
  return { ctx, page, errors };
}
const openReplay = (page, extra) => page.evaluate((x) => {
  window.__rp = window.BirgeReplay.open(Object.assign({ map: window.__map, heat: window.__heat, container: document.getElementById("replay-slot"), days: 7 }, x || {}));
  return true;
}, extra || {});
const ready = (page) => page.waitForFunction(() => window.BirgeReplay.active && window.BirgeReplay.active.state().status !== "loading", null, { timeout: 30000 });
const rpState = (page) => page.evaluate(() => window.BirgeReplay.active ? window.BirgeReplay.active.state() : null);

(async () => {
  const browser = await chromium.launch();

  // ---- 1366 ru: открыть кнопкой, что видно, клавиши ----
  {
    const { ctx, page, errors } = await open(browser, 1366, "ru");
    const liveBadges = await page.evaluate(() => window.__heat.badges().map((b) => b.key).sort());
    await page.click(".mapbtns .rp-open");
    await ready(page);
    await page.evaluate(() => window.BirgeReplay.active.pause());
    const view = await page.evaluate(() => {
      const bar = document.querySelector(".rp-bar"), r = bar.getBoundingClientRect();
      return { day: document.querySelector(".rp-day").textContent, ticks: document.querySelectorAll(".rp-tick").length,
        marks: [...document.querySelectorAll(".rp-mark")].map((m) => m.textContent.trim()), people: document.querySelector(".rp-people").textContent,
        fixed: document.querySelector(".rp-fixed").textContent, demo: !!document.querySelector(".rp-tag"), focus: document.activeElement && document.activeElement.className,
        inside: r.left >= 0 && r.right <= innerWidth && r.bottom <= innerHeight, replaying: window.__heat.replay.active,
        buttons: [...document.querySelectorAll(".rp-bar button")].map((b) => { const q = b.getBoundingClientRect(); return [b.className, Math.round(q.width), Math.round(q.height)]; }),
        emoji: /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(bar.textContent) };
    });
    const st = await rpState(page);
    const p = [];
    if (st.days.length !== 7) p.push("дней не 7: " + st.days.length);
    if (view.ticks !== 7) p.push("отметок дней не 7");
    if (!view.marks.some((m) => /Буран/.test(m))) p.push("нет отметки «Буран» на шкале: " + view.marks.join(", "));
    if (!/Сообщил/.test(view.people) || !/исправлен/.test(view.fixed)) p.push("нет чисел дня: " + view.people + " / " + view.fixed);
    if (!view.demo) p.push("нет пометки «Пример»");
    if (!view.inside) p.push("полоса выходит за экран");
    if (!view.replaying) p.push("карта не в режиме хроники");
    if (view.emoji) p.push("эмодзи в интерфейсе (П1)");
    view.buttons.forEach(([c, w, h]) => { if (h < 44 && !/rp-chip/.test(c)) p.push("кнопка ниже 44 px: " + c + " " + w + "×" + h); });
    check("open-1366-ru", p, view);

    // клавиши: → ← End Home Пробел
    const k = [];
    await page.keyboard.press("ArrowRight"); if ((await rpState(page)).index !== 1) k.push("→ не на день 1");
    await page.keyboard.press("End"); if ((await rpState(page)).index !== 6) k.push("End не на сегодня");
    await page.keyboard.press("ArrowLeft"); if ((await rpState(page)).index !== 5) k.push("← не на день 5");
    await page.keyboard.press("Home"); if ((await rpState(page)).index !== 0) k.push("Home не на день 0");
    await page.locator(".rp-track").focus();
    await page.keyboard.press(" "); if (!(await rpState(page)).playing) k.push("Пробел не запустил");
    await page.keyboard.press(" "); if ((await rpState(page)).playing) k.push("Пробел не поставил паузу");
    check("keys-1366-ru", k);

    // неделя целиком: 10–20 с; затем Esc — «сегодня» без мигания
    await page.evaluate(() => window.BirgeReplay.active.seek(0));
    const t0 = Date.now();
    await page.evaluate(() => window.BirgeReplay.active.play());
    await page.waitForFunction(() => window.BirgeReplay.active.state().ended, null, { timeout: 40000, polling: 100 });
    const played = (Date.now() - t0) / 1000;
    const stats = await page.evaluate(() => window.BirgeReplay.active.stats());
    const again = await page.evaluate(() => document.querySelector(".rp-play").getAttribute("aria-label"));
    const w = [];
    if (played < 10 || played > 20) w.push("неделя за " + played.toFixed(1) + " с (нужно 10–20)");
    if (!/Сначала/.test(again)) w.push("после конца кнопка не «Сначала»: " + again);
    check("week-10-20s-1366", w, { played_s: +played.toFixed(1), stats });

    await page.evaluate(() => { window.__min = 1e9; window.__sampling = true; const tick = () => { const n = document.querySelectorAll(".r07-badge:not([hidden])").length; window.__min = Math.min(window.__min, n); if (window.__sampling) requestAnimationFrame(tick); }; requestAnimationFrame(tick); });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(1200);
    const after = await page.evaluate(() => { window.__sampling = false; return { min: window.__min, active: !!window.BirgeReplay.active, replay: window.__heat.replay.active,
      badges: window.__heat.badges().map((b) => b.key).sort(), cls: document.body.classList.contains("birge-replay-open"), focus: document.activeElement && document.activeElement.className }; });
    const c = [];
    if (after.active || after.replay || after.cls) c.push("хроника не закрылась");
    if (after.min < Math.min(liveBadges.length, 1)) c.push("значки пропадали при закрытии (минимум " + after.min + ")");
    if (JSON.stringify(after.badges) !== JSON.stringify(liveBadges)) c.push("после закрытия значки не как «сегодня»");
    if (!/rp-open/.test(after.focus || "")) c.push("фокус не вернулся на кнопку «Хроника»: " + after.focus);
    check("esc-today-no-flash-1366", c, { min_badges: after.min, live: liveBadges.length });
    if (errors.length) check("console-1366-ru", errors.slice(0, 5));
    else check("console-1366-ru", []);
    await ctx.close();
  }

  // ---- кадры для R14 и ролика R10: начало, буран (пик), после — 1366 / 1024 / 375 × ru / kk ----
  for (const size of [1366, 1024, 375]) {
    for (const lang of ["ru", "kk"]) {
      // открываем кнопкой стенда (на телефоне она сворачивает шторку, как сделает оболочка R01)
      const { ctx, page, errors } = await open(browser, size, lang, "&autoplay=0");
      await page.click(".mapbtns .rp-open");
      await ready(page);
      const st = await rpState(page);
      const peak = st.people.indexOf(Math.max(...st.people));
      const shots = [["start", 0], ["buran", peak], ["after", st.days.length - 1]];
      const p = [];
      for (const [name, i] of shots) {
        await page.evaluate((k) => window.BirgeReplay.active.seek(k), i);
        await page.waitForTimeout(900);
        await page.mouse.move(5, 5);
        await page.screenshot({ path: path.join(OUT, `replay_${size}_${lang}_${name}.png`) });
      }
      const fit = await page.evaluate(() => {
        const bar = document.querySelector(".rp-bar").getBoundingClientRect();
        const labels = [...document.querySelectorAll(".rp-tick span")].map((s) => s.getBoundingClientRect()).filter((r) => r.width > 0);   // скрытые подписи не в счёт
        let overlap = 0;
        for (let i = 1; i < labels.length; i++) if (labels[i].left < labels[i - 1].right - 1) overlap++;
        // обрезанный текст: элемент или его рамка (.rp-num, .rp-event) уже содержимого
        const cut = [...document.querySelectorAll(".rp-day, .rp-num, .rp-event")].filter((el) => el.offsetParent && el.scrollWidth > el.clientWidth + 1).map((el) => el.className);
        return { inside: bar.left >= 0 && bar.right <= innerWidth + 0.5, hscroll: document.documentElement.scrollWidth > innerWidth, overlap, cut };
      });
      if (!fit.inside || fit.hscroll) p.push("полоса шире экрана");
      if (fit.overlap) p.push("подписи дней налезают: " + fit.overlap);
      if (fit.cut.length) p.push("обрезан текст: " + fit.cut.join(", "));
      if (errors.length) p.push("ошибки консоли: " + errors.slice(0, 2).join(" | "));
      check(`frames-${size}-${lang}`, p, { peak_day: st.days[peak], people: st.people });
      await ctx.close();
    }
  }

  // ---- состояния: нет связи (500), не подключено (503), пусто ----
  for (const [name, route, expect] of [
    ["error-500", (r) => r.fulfill({ status: 500, contentType: "application/json", body: '{"error":"internal"}' }), /Не удалось загрузить хронику/],
    ["not-ready-503", (r) => r.fulfill({ status: 503, contentType: "application/json", body: '{"error":"module_not_ready"}' }), /ещё не подключена/],
    ["empty", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ frames: [{ date: "2026-10-15", at: "2026-10-15T12:00:00+05:00", totals: { people: 0 }, items: [], districts: [] }], targets: {}, events: [], legend: {}, demo: true }) }), /жалоб нет/],
  ]) {
    const { ctx, page } = await open(browser, 1366, "ru", "", { route });
    await openReplay(page);
    await page.waitForFunction(() => window.BirgeReplay.active && window.BirgeReplay.active.state().status !== "loading", null, { timeout: 15000 });
    const v = await page.evaluate(() => ({ text: (document.querySelector(".rp-msg") || {}).textContent || "", buttons: document.querySelectorAll(".rp-msg button").length,
      replay: window.__heat.replay.active, icon: (() => { const i = document.querySelector(".rp-msg .rp-ic"); if (!i) return 0; const r = i.getBoundingClientRect(); return Math.max(r.width, r.height); })() }));
    const p = [];
    if (!expect.test(v.text)) p.push("нет понятного текста: " + v.text);
    if (v.buttons > 1) p.push("больше одной кнопки (П1)");
    if (v.icon > 48) p.push("значок больше 48 px (П1)");
    if (v.replay) p.push("карта ушла в хронику без данных");
    if (name === "error-500" && v.buttons !== 1) p.push("нет «Повторить»");
    await page.screenshot({ path: path.join(OUT, `replay_state_${name}.png`) });
    await page.keyboard.press("Escape");
    await page.waitForTimeout(400);
    if (await page.evaluate(() => !!window.BirgeReplay.active)) p.push("Esc не закрыл состояние");
    check("state-" + name, p, v);
    await ctx.close();
  }

  // ---- «меньше движения»: дни сменяются шагами, без перетекания ----
  {
    const { ctx, page } = await open(browser, 1366, "ru", "", { reduced: true });
    await openReplay(page, { autoplay: false });
    await ready(page);
    await page.evaluate(() => window.BirgeReplay.active.seek(3));
    await page.waitForTimeout(300);
    const cost = await page.evaluate(() => window.__heat.replay.cost());
    const p = [];
    if (cost.tween_ms_per_frame !== 0) p.push("при «меньше движения» есть перетекание (кадров перетекания > 0)");
    check("reduced-motion-steps", p, cost);
    await ctx.close();
  }

  // ---- лёгкий вход (R10 B-113): replay-attach.js вместо replay.js + replay.css — так стенд, как оболочка R01 при
  //      ленивой загрузке; до первого открытия полная хроника не грузится, кнопка открывает и закрывает её ----
  {
    const ctx = await browser.newContext({ viewport: SIZES[1366], deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    const errors = [];
    const asked = { js: 0, css: 0 };
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
    page.on("request", (r) => { if (/\/civic\/replay\/replay\.js/.test(r.url())) asked.js++; if (/\/civic\/replay\/replay\.css/.test(r.url())) asked.css++; });
    await page.route(/\/civic\/heat\/demo\.html/, async (route) => {
      const res = await route.fetch();
      const html = (await res.text())
        .replace('<link rel="stylesheet" href="/civic/replay/replay.css" />', "")
        .replace('<script src="/civic/replay/replay.js"></script>', '<script src="/civic/replay/replay-attach.js"></script>');
      await route.fulfill({ response: res, body: html });
    });
    await page.goto(`${BASE}?lang=ru&role=akimat&view=city`, { waitUntil: "load" });
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    const p = [];
    const before = { ...asked };
    const lazy = await page.evaluate(() => !!(window.BirgeReplay && window.BirgeReplay.lazy && !window.BirgeReplay.mount));
    if (!lazy) p.push("на странице не лёгкий вход");
    if (before.js || before.css) p.push(`полная хроника загружена до открытия (js ${before.js}, css ${before.css})`);
    const btn = page.locator(".mapbtns .rp-open");
    if (await btn.count() !== 1) p.push("нет кнопки «Хроника» у кнопок карты");
    else {
      const label = await btn.getAttribute("aria-label");
      if (!/Хроника города/.test(label || "")) p.push("подпись кнопки: " + label);
      await btn.click();
      await page.waitForFunction(() => window.BirgeReplay.active && window.BirgeReplay.active.state().status === "ready", null, { timeout: 30000 });
      const st = await page.evaluate(() => ({ days: window.BirgeReplay.active.state().days.length, full: typeof window.BirgeReplay.mount === "function" }));
      if (!st.full || st.days !== 7) p.push("после нажатия нет полной хроники на 7 дней: " + JSON.stringify(st));
      await page.keyboard.press("Escape");
      await page.waitForFunction(() => !window.BirgeReplay.active, null, { timeout: 10000 });
      await btn.click();   // второй раз — без новой загрузки
      await page.waitForFunction(() => window.BirgeReplay.active && window.BirgeReplay.active.state().status === "ready", null, { timeout: 30000 });
      await page.evaluate(() => window.BirgeReplay.active.close());
      if (asked.js !== 1 || asked.css !== 1) p.push(`загрузок полной хроники: js ${asked.js}, css ${asked.css} (ожидалась одна)`);
    }
    if (errors.length) p.push("ошибки в консоли: " + errors.slice(0, 3).join(" | "));
    check("lazy-entry-1366", p, { before, after: asked });
    await ctx.close();
  }

  await browser.close();
  const fails = results.filter((r) => !r.pass).length;
  fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify({ base: BASE, at: new Date().toISOString(), pass: results.length - fails, fail: fails, results }, null, 1));
  console.log(`${results.length - fails}/${results.length}`);
  process.exit(fails ? 1 : 0);
})();
