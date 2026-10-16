// R13 · «Вопрос акиму» (волна 2 п. 9) в оболочке Birge R01: раздел #questions, житель и акимат, 375/1366 × ru/kk.
// Запускает свой сервер (CIVIC_DEMO=1, временная база), создаёт сотрудника, проходит пути и делает снимки.
//
//   BIRGE_REPO=<сборка R01 с patch R13> node tests/civic/R13/qa/qa_browser.cjs <папка_снимков>
//
// Проверяет (схема R11 IA_WAVE2 §7, UX_BRIEF): правило «5 вопросов в неделю» видно; у жителя одна главная кнопка;
// вкладки-сегменты; «Пример» в строке под демо-вопросом; «N голосов» словами; «Ещё → Вопрос акиму» / «Вопросы жителей»; голос «Поддержать» → «Вы поддержали»
// и держится после перезагрузки; форма: ошибка на пустом поле, отправка → «Вопрос отправлен»; сотрудник: подсказка
// «похоже на личные данные», «Опубликовать», «Отклонить с причиной», ответ → «С ответом»; без прокрутки вбок;
// карта по умолчанию не изменилась (в #map нет элементов «Вопроса акиму»); нет ошибок JS.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os");

const REPO = path.resolve(process.env.BIRGE_REPO || path.join(__dirname, "../../../.."));
const OUT = path.resolve(process.argv[2] || "r13-qa-out");
const NOISE = /openfreemap|Failed to load resource|GL Driver|style diff|swiftshader|GroupMarkerNotSet|ERR_TUNNEL|net::ERR/i;
const checks = [];
const check = (name, ok, detail) => {
  checks.push({ name, status: ok ? "PASS" : "FAIL", detail: detail ?? null });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail != null ? " — " + JSON.stringify(detail).slice(0, 300) : ""));
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });
const STAFF = { user: "qa.check", pass: "qa-check-pass-2026" };

async function startServer(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`, { cwd: REPO, env, input, stdio: [input ? "pipe" : "ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  run(`create-editor ${STAFF.user} --password-stdin`, STAFF.pass + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: REPO, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

async function newPage(ctx) {
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error" && !NOISE.test(m.text())) page.errs.push(m.text()); });
  return page;
}
const noSideScroll = (page) => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1
  && [...document.querySelectorAll(".qa *")].every((e) => e.getBoundingClientRect().right <= innerWidth + 1 || e.closest(".qa-tabs-wrap, .bk-tabs")));
// QA_GLASS=1 — стекло R11 (GLASS.md №6) на листе раздела #birge-screen, если оболочка R01 его ещё не поставила.
const GLASS = process.env.QA_GLASS === "1";
// После смены вкладки прежний список виден приглушённым (.qa-list--busy), пока не придёт новый — ждём новый.
const idle = (page) => page.waitForFunction(() => !document.querySelector(".qa-list--busy, .qa-skeleton"), null, { timeout: 15000 });
const openSection = async (page, base, mode, lang) => {
  await page.goto(`${base}/#questions`);
  await page.waitForSelector(".qa", { timeout: 40000 });
  await page.waitForSelector(".qa-card, .qa-empty, .qa-login", { timeout: 20000 });
  if (GLASS) await page.evaluate(() => document.getElementById("birge-screen")?.classList.add("bk-glass"));
  await page.waitForTimeout(400);
};
// Стекло (GLASS.md §2): у корня .qa своего фона нет; формы (вопрос, отказ, ответ) — непрозрачные.
const glassRules = (page) => page.evaluate(() => {
  const alpha = (c) => { const m = /rgba?\(([^)]+)\)/.exec(c); if (!m) return 1; const p = m[1].split(",").map(Number); return p.length > 3 ? p[3] : 1; };
  const root = document.querySelector(".qa");
  const forms = [...document.querySelectorAll(".qa-form, .qa-panel")].map((f) => alpha(getComputedStyle(f).backgroundColor));
  return { rootClear: alpha(getComputedStyle(root).backgroundColor) === 0, formsOpaque: forms.every((a) => a === 1), forms };
});
// Контраст текста экрана в худшем случае: под стеклом листа — чёрная карта. Фоны от листа до элемента
// накладываются по прозрачности; крупный текст (≥ 24 px или ≥ 18,66 px жирный) — норма 3, остальной — 4,5.
const worstContrast = (page) => page.evaluate(() => {
  const parse = (c) => { const m = /rgba?\(([^)]+)\)/.exec(c || ""); if (!m) return null; const p = m[1].split(",").map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  const lum = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const sheet = document.getElementById("birge-screen");
  let worst = { ratio: 99 }, bad = [];
  for (const el of document.querySelectorAll(".qa *")) {
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (!own || !r.width || cs.visibility === "hidden" || cs.display === "none") continue;
    const chain = [];
    for (let a = el; a; a = a.parentElement) { chain.unshift(a); if (a === sheet) break; }
    let bg = [0, 0, 0];  // худший случай: чёрная карта под стеклом
    for (const a of chain) {
      const c = parse(getComputedStyle(a).backgroundColor);
      if (c && c[3] > 0) bg = [0, 1, 2].map((i) => c[i] * c[3] + bg[i] * (1 - c[3]));
    }
    const fg = parse(cs.color), l1 = lum(fg), l2 = lum(bg);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const size = parseFloat(cs.fontSize), large = size >= 24 || (size >= 18.66 && Number(cs.fontWeight) >= 700);
    const need = large ? 3 : 4.5;
    if (ratio < worst.ratio) worst = { ratio: Math.round(ratio * 100) / 100, text: el.textContent.trim().slice(0, 40), color: cs.color };
    if (ratio < need) bad.push({ text: el.textContent.trim().slice(0, 40), ratio: Math.round(ratio * 100) / 100, color: cs.color });
  }
  return { worst, bad: bad.slice(0, 5), glass: !!sheet && sheet.classList.contains("bk-glass") };
});

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const port = await freePort(), base = `http://127.0.0.1:${port}`;
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r13-qa-"));
  const srv = await startServer(port, path.join(tmp, "civic.sqlite3"));
  const browser = await chromium.launch(fs.existsSync("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    ? { executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" } : {});
  try {
    for (const lang of ["ru", "kk"]) {
      for (const [w, hgt] of [[375, 812], [1366, 768]]) {
        const tag = `${w}-${lang}`;
        // ---------------- житель
        const ctx = await browser.newContext({ viewport: { width: w, height: hgt }, deviceScaleFactor: w < 500 ? 2 : 1 });
        await ctx.addInitScript(([l]) => { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); }, [lang]);
        const page = await newPage(ctx);
        await openSection(page, base, "resident", lang);
        const r = await page.evaluate(() => ({
          title: document.querySelector(".qa__title")?.textContent,
          rule: !!document.querySelector(".qa__rule") && document.querySelector(".qa__rule").getBoundingClientRect().height > 0,
          primary: [...document.querySelectorAll("#birge-screen .bk-btn--primary")].filter((b) => b.offsetParent).length,
          tabs: document.querySelectorAll(".qa-tabs > button").length,
          cards: document.querySelectorAll(".qa-card").length,
          // эталон A: «Пример» — первое слово строки под вопросом («Пример · Нура · 6 дней назад»), а не отдельная метка
          demoTags: [...document.querySelectorAll(".qa-card .qa-card__meta")].filter((m) => /^(Пример|Үлгі) · /.test(m.textContent)).length,
          // «34 голоса» словами есть в тексте страницы (для диктора; приёмка R10 W2-9 ищет «N голос/дауыс»)
          votesText: (document.body.innerText.match(/\d+\s*(голос|дауыс)/g) || []).length,
          votes: document.querySelectorAll(".qa-card__vote").length,
          inMap: document.querySelectorAll("#map .qa, #map [class^='qa-']").length,
          more: window.BirgeShell?.navItems("resident") || [],
        }));
        check(`${tag} житель: экран открыт, правило видно`, r.title && r.rule, r.title);
        if (w === 1366) {
          // Движение (чек-лист марафона п. 7): карточки появляются анимацией qa-in и через 0,6 с непрозрачны;
          // при «уменьшить движение» в системе анимации нет.
          const motion = await page.evaluate(() => new Promise((ok) => {
            const li = document.querySelector(".qa-list > li");
            const name = li ? getComputedStyle(li).animationName : null;
            setTimeout(() => ok({ name, opacity: li ? getComputedStyle(li).opacity : null }), 600);
          }));
          const rctx = await browser.newContext({ viewport: { width: w, height: hgt }, reducedMotion: "reduce" });
          await rctx.addInitScript(([l]) => { localStorage.setItem("birge.mode", "resident"); localStorage.setItem("birge.lang", l); }, [lang]);
          const rp = await rctx.newPage();
          await openSection(rp, base, "resident", lang);
          const reduced = await rp.evaluate(() => getComputedStyle(document.querySelector(".qa-list > li")).animationName);
          await rctx.close();
          check(`${tag} движение: карточки появляются мягко, при «уменьшить движение» — без анимации`,
            motion.opacity === "1" && reduced === "none", { motion, reduced });
        }
        check(`${tag} житель: одна главная кнопка`, r.primary === 1, r.primary);
        check(`${tag} житель: 3 вкладки, карточки с меткой «Пример»`, r.tabs === 3 && r.cards >= 5 && r.demoTags === r.cards, r);
        check(`${tag} житель: «N голосов» словами в тексте страницы (W2-9 R10)`, r.votesText >= 3, r.votesText);
        check(`${tag} житель: на карте ничего нового`, r.inMap === 0, r.inMap);
        check(`${tag} житель: «Ещё» в меню`, r.more.includes("more"), r.more);
        check(`${tag} житель: нет прокрутки вбок`, await noSideScroll(page));
        await page.screenshot({ path: path.join(OUT, `${tag}-resident-top.png`) });
        const gr = await glassRules(page);
        check(`${tag} стекло: у корня экрана своего фона нет`, gr.rootClear, gr);
        if (GLASS) {
          const wc = await worstContrast(page);
          check(`${tag} стекло: контраст текста ≥ 4,5 над чёрной картой (житель)`, wc.glass && !wc.bad.length, wc);
        }

        if (w === 1366) {
          // «Ещё → Вопрос акиму» в меню жителя.
          await page.goto(`${base}/#map`);
          await page.waitForSelector("#birge-header [data-section=more]", { state: "visible", timeout: 20000 });
          await page.click("#birge-header [data-section=more]");
          const items = await page.$$eval(".birge-more-menu [role=menuitem]", (els) => els.map((e) => [e.dataset.section, e.textContent]));
          // IA раунда 15 (R11 §5.3): «Вопрос акиму» — вкладка «Вопросы» раздела «Вопросы и встречи», своего пункта нет
          const hasQa = items.some(([id]) => id === "questions"), hasMeetings = items.some(([id]) => id === "meetings");
          check(`${tag} житель: «Ещё» → «Вопрос акиму» (раунд 15: «Вопросы и встречи» → «Вопросы»)`, hasQa || hasMeetings, items);
          if (hasQa) await page.click(".birge-more-menu [data-section=questions]");
          else {
            await page.click(".birge-more-menu [data-section=meetings]");
            await page.waitForSelector('.mt-seg [role=tab][value="questions"]', { timeout: 20000 });
            await page.click('.mt-seg [role=tab][value="questions"]');
          }
          await page.waitForSelector(".qa-card", { timeout: 20000 });
        }
        if (w === 375 && lang === "ru") {
          // Голос: «Поддержать» → «Вы поддержали», число +1, после перезагрузки — то же.
          const before = await page.$eval(".qa-card", (c) => c.querySelector(".qa-card__votes").textContent);
          await page.click(".qa-card .qa-card__vote");
          await page.waitForSelector(".qa-card .qa-card__voted", { timeout: 10000 });
          const after = await page.$eval(".qa-card", (c) => c.querySelector(".qa-card__votes").textContent);
          await page.reload();
          await page.waitForSelector(".qa-card", { timeout: 30000 });
          if (GLASS) await page.evaluate(() => document.getElementById("birge-screen")?.classList.add("bk-glass"));
          const kept = await page.$eval(".qa-card", (c) => !!c.querySelector(".qa-card__voted"));
          check("375-ru житель: «Поддержать» → «Вы поддержали», голос сохранён", before !== after && kept, { before, after, kept });
        }
        if (w === 375) {
          // Форма: пустой текст — ошибка у поля; отправка — «Вопрос отправлен», «Опубликуют после проверки».
          await page.click(".qa__lead .bk-btn--primary");
          await page.waitForSelector("#qa-text");
          check(`${tag} форма: фокус в поле вопроса`, await page.evaluate(() => document.activeElement?.id === "qa-text"));
          await page.screenshot({ path: path.join(OUT, `${tag}-resident-form.png`) });
          const fr = await glassRules(page);
          check(`${tag} форма вопроса непрозрачная (не стекло)`, fr.formsOpaque && fr.forms.length === 1, fr);
          if (GLASS) {
            const wcf = await worstContrast(page);
            check(`${tag} стекло: контраст текста формы`, !wcf.bad.length, wcf);
          }
          await page.click(".qa-form button[type=submit]");
          const err = await page.$eval("#qa-text-error", (e) => e.textContent).catch(() => null);
          check(`${tag} форма: ошибка у пустого поля`, !!err, err);
          await page.fill("#qa-text", lang === "kk" ? "Аулада балаларға арналған мұз айдыны қашан ашылады?" : "Когда во дворе зальют каток для детей?");
          await page.selectOption("#qa-district", "esil");
          await page.click(".qa-form button[type=submit]");
          await page.waitForSelector(".qa-sent", { timeout: 10000 });
          check(`${tag} форма: вопрос отправлен, «после проверки»`, await page.evaluate(() => document.activeElement?.id === "qa-sent-title"));
          await page.screenshot({ path: path.join(OUT, `${tag}-resident-sent.png`) });
          await page.click(".qa-sent .bk-btn--primary");
          await page.waitForSelector(".qa-card", { timeout: 10000 });
        }
        // Эталон A: ответ акима — цитата в 2 строки (.quote) и «Читать полностью»; нажатие раскрывает весь текст.
        await page.click(".qa-tabs > button:nth-child(2)"); await idle(page);
        await page.waitForSelector(".qa-answer", { timeout: 10000 });
        // «Читать полностью» есть ровно у тех цитат, что не влезли в 2 строки (на телефоне kk — у коротких тоже)
        const fit = await page.evaluate(() => [...document.querySelectorAll(".qa-answer")].map((d) => {
          const t = d.querySelector(".qa-answer__text"), more = d.querySelector(".qa-answer__more");
          return [t.scrollHeight > t.clientHeight + 1, !!more && !more.hidden];
        }));
        check(`${tag} житель: «Читать полностью» — у всех и только у обрезанных цитат`, fit.length >= 1 && fit.every(([cut, shown]) => cut === shown), fit);
        const longId = await page.evaluate(() => {
          const d = [...document.querySelectorAll(".qa-answer")].find((x) => !x.querySelector(".qa-answer__more").hidden);
          return d ? d.closest(".qa-card").dataset.id : null;
        });
        if (!longId) {
          // широкая колонка (лист оболочки без patch §12.1): все цитаты влезли в 2 строки — раскрывать нечего
          check(`${tag} житель: ответ акима — 2 строки и «Читать полностью», нажатие раскрывает`, fit.every(([cut]) => !cut), { allFit: true });
        } else {
          const sel = `.qa-card[data-id="${longId}"] .qa-answer`;
          const clamp = await page.$eval(sel, (d) => {
            const t = d.querySelector(".qa-answer__text"), more = d.querySelector(".qa-answer__more");
            return { open: d.classList.contains("qa-answer--open"), lines: Math.round(t.getBoundingClientRect().height / parseFloat(getComputedStyle(t).lineHeight)),
              more: more ? more.getAttribute("aria-expanded") : null };
          });
          await page.click(`${sel} .qa-answer__more`);
          const opened = await page.$eval(sel, (d) => {
            const t = d.querySelector(".qa-answer__text");
            return { open: d.classList.contains("qa-answer--open"), expanded: d.querySelector(".qa-answer__more").getAttribute("aria-expanded"),
              lines: Math.round(t.getBoundingClientRect().height / parseFloat(getComputedStyle(t).lineHeight)), text: t.textContent.length };
          });
          check(`${tag} житель: ответ акима — 2 строки и «Читать полностью», нажатие раскрывает`,
            !clamp.open && clamp.lines === 2 && clamp.more === "false" && opened.open && opened.expanded === "true" && opened.lines > 2, { clamp, opened });
        }
        await page.click(".qa-tabs > button:nth-child(3)"); await idle(page);
        await page.waitForSelector(".qa-answer", { timeout: 10000 });
        const signs = await page.evaluate(() => [...document.querySelectorAll(".qa-answer")].map((d) => [(d.querySelector(".qa-answer__sign") || {}).textContent || "",
          (d.querySelector(".qa-answer__text") || {}).textContent || ""]));
        check(`${tag} житель: в «С ответом» у ответов подпись и дата`, signs.length >= 2 && signs.every(([sg, t]) => /·/.test(sg) && t.length > 20), signs.slice(0, 2));
        await page.screenshot({ path: path.join(OUT, `${tag}-resident-answered.png`) });
        check(`${tag} житель: нет ошибок JS`, page.errs.length === 0, page.errs.slice(0, 3));
        await ctx.close();

        // ---------------- акимат
        const sctx = await browser.newContext({ viewport: { width: w, height: hgt }, deviceScaleFactor: w < 500 ? 2 : 1 });
        await sctx.addInitScript(([l]) => { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); }, [lang]);
        const sp = await newPage(sctx);
        // Без входа — понятная просьба войти, а не ошибка.
        await openSection(sp, base, "akimat", lang);
        check(`${tag} акимат без входа: просьба войти`, !!(await sp.$(".qa-login")));
        await sp.evaluate(async (s) => {
          await fetch("/api/civic/v1/session/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: s.user, password: s.pass }) });
        }, STAFF);
        await sp.reload();
        await sp.waitForFunction(() => window.CivicShell && typeof window.CivicShell.csrfToken === "function" && window.CivicShell.csrfToken(), null, { timeout: 20000 });
        await openSection(sp, base, "akimat", lang);
        const a = await sp.evaluate(() => ({
          title: document.querySelector(".qa__title")?.textContent,
          cards: document.querySelectorAll(".qa-card").length,
          pii: [...document.querySelectorAll(".qa-card__warn .qa-pill--warn")].map((t) => t.textContent),
          primary: [...document.querySelectorAll("#birge-screen .bk-btn--primary")].filter((b) => b.offsetParent).length,
        }));
        check(`${tag} акимат: очередь на проверке, подсказка о личных данных`, a.cards >= 1 && a.pii.length >= 1, a);
        check(`${tag} акимат: без главной кнопки в списке`, a.primary === 0, a.primary);
        check(`${tag} акимат: нет прокрутки вбок`, await noSideScroll(sp));
        await sp.screenshot({ path: path.join(OUT, `${tag}-akimat-queue.png`) });
        if (GLASS) {
          const wcs = await worstContrast(sp);
          check(`${tag} стекло: контраст текста ≥ 4,5 над чёрной картой (акимат)`, wcs.glass && !wcs.bad.length, wcs);
        }
        if (w === 375 && lang === "ru" || w === 1366 && lang === "kk") {
          // Опубликовать первый; отклонить с причиной следующий.
          const firstId = await sp.$eval(".qa-card", (c) => c.dataset.id);
          await sp.click(`.qa-card[data-id="${firstId}"] .qa-card__actions .bk-btn:not(.bk-btn--ghost)`);
          await sp.waitForFunction((id) => !document.querySelector(`.qa-card[data-id="${id}"]`), firstId, { timeout: 10000 });
          check(`${tag} акимат: «Опубликовать» убирает вопрос из очереди`, true);
          const next = await sp.$eval(".qa-card", (c) => c.dataset.id).catch(() => null);
          if (next) {
            await sp.click(`.qa-card[data-id="${next}"] .qa-card__actions .bk-btn--ghost`);
            await sp.click(`.qa-card[data-id="${next}"] .qa-panel button[type=submit]`);
            const need = await sp.$eval(`.qa-card[data-id="${next}"] .qa-form__error`, (e) => e.textContent).catch(() => null);
            await sp.click(`.qa-card[data-id="${next}"] .qa-reason input`);
            await sp.screenshot({ path: path.join(OUT, `${tag}-akimat-reject.png`) });
            await sp.click(`.qa-card[data-id="${next}"] .qa-panel button[type=submit]`);
            await sp.waitForFunction((id) => !document.querySelector(`.qa-card[data-id="${id}"]`), next, { timeout: 10000 });
            check(`${tag} акимат: отказ только с причиной`, !!need, need);
          }
          // Топ-5 недели: ответить на первый.
          await sp.click(".qa-tabs > button:nth-child(2)"); await idle(sp);
          await sp.waitForSelector(".qa__week", { timeout: 10000 });
          const topCount = await sp.$$eval(".qa-card", (c) => c.length);
          const topId = await sp.$eval(".qa-card", (c) => c.dataset.id);
          await sp.click(`.qa-card[data-id="${topId}"] .qa-card__actions .bk-btn:not(.bk-btn--ghost)`);
          await sp.fill(`.qa-card[data-id="${topId}"] textarea[lang=${lang}]`, lang === "kk" ? "Бағдаршам қараша айында орнатылады, жоба келісілді." : "Светофор поставят в ноябре, проект согласован.");
          await sp.screenshot({ path: path.join(OUT, `${tag}-akimat-answer.png`) });
          const ar = await glassRules(sp);
          check(`${tag} форма ответа акима непрозрачная`, ar.formsOpaque && ar.forms.length === 1, ar);
          await sp.click(`.qa-card[data-id="${topId}"] .qa-panel button[type=submit]`);
          await sp.waitForFunction((id) => !document.querySelector(`.qa-card[data-id="${id}"] .qa-panel`), topId, { timeout: 10000 });
          await sp.click(".qa-tabs > button:nth-child(3)"); await idle(sp);
          await sp.waitForSelector(`.qa-card[data-id="${topId}"] .qa-answer`, { timeout: 10000 });
          const week = await sp.evaluate(async () => (await (await fetch("/api/civic/v2/questions/staff?tab=top")).json()).week.answered);
          check(`${tag} акимат: топ-5 ≤ 5, ответ виден в «Отвечено», неделя +1`, topCount <= 5 && week >= 1, { topCount, week });
          await sp.screenshot({ path: path.join(OUT, `${tag}-akimat-answered.png`) });
          // Ответ виден жителю.
          const pub = await sp.evaluate(async (id) => (await (await fetch("/api/civic/v2/questions?tab=answered")).json()).items.some((q) => q.id === id), topId);
          check(`${tag} ответ виден всем во вкладке «С ответом»`, pub);
          // Правка ответа видна всем (R15 S39): «изменён …» в строке «Ответ акима».
          await sp.click(`.qa-card[data-id="${topId}"] .qa-card__actions .bk-btn:first-child`);
          await sp.fill(`.qa-card[data-id="${topId}"] textarea[lang=${lang}]`, lang === "kk" ? "Бағдаршам қарашаның соңында орнатылады." : "Светофор поставят в конце ноября.");
          await sp.click(`.qa-card[data-id="${topId}"] .qa-panel button[type=submit]`);
          await sp.waitForFunction((id) => !document.querySelector(`.qa-card[data-id="${id}"] .qa-panel`), topId, { timeout: 10000 });
          await sp.waitForSelector(`.qa-card[data-id="${topId}"] .qa-answer`, { timeout: 10000 });
          const edited = await sp.evaluate(async (id) => {
            const q = (await (await fetch("/api/civic/v2/questions?tab=answered")).json()).items.find((x) => x.id === id);
            const sum = document.querySelector(`.qa-card[data-id="${id}"] .qa-answer__sign`).textContent;
            return { api: !!(q && q.answer.edited_at), shown: sum.split(" · ").length === 3, sum };
          }, topId);
          check(`${tag} правка ответа: дата правки в API и на экране`, edited.api && edited.shown, edited);
          // Отвеченный вопрос снимают только из-за личных данных (R15 S35): в форме одна причина, она уже выбрана.
          await sp.click(`.qa-card[data-id="${topId}"] .qa-card__actions .bk-btn:nth-child(2)`);
          const reasons = await sp.$$eval(`.qa-card[data-id="${topId}"] .qa-reason input`, (els) => els.map((e) => [e.value, e.checked]));
          check(`${tag} отвеченный: снять можно только из-за личных данных`, reasons.length === 1 && reasons[0][0] === "personal_data" && reasons[0][1], reasons);
          await sp.screenshot({ path: path.join(OUT, `${tag}-akimat-answered-reject.png`) });
          await sp.click(`.qa-card[data-id="${topId}"] .qa-panel .qa-card__actions .bk-btn:last-child`);
        }
        check(`${tag} акимат: нет ошибок JS`, sp.errs.length === 0, sp.errs.slice(0, 3));
        await sctx.close();
      }
    }
  } catch (e) {
    check("сценарий прошёл без исключений", false, String(e && e.stack || e).slice(0, 600));
  } finally {
    await browser.close();
    srv.kill();
    const failed = checks.filter((c) => c.status === "FAIL").length;
    fs.writeFileSync(path.join(OUT, "QA_BROWSER.json"), JSON.stringify({ repo: REPO, passed: checks.length - failed, failed, checks }, null, 1));
    console.log(`\nR13 qa_browser: ${checks.length - failed}/${checks.length} PASS`);
    process.exit(failed ? 1 : 0);
  }
})();
