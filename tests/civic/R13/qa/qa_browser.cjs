// R13 · «Вопрос акиму» (волна 2 п. 9) в оболочке Birge R01: раздел #questions, житель и акимат, 375/1366 × ru/kk.
// Запускает свой сервер (CIVIC_DEMO=1, временная база), создаёт сотрудника, проходит пути и делает снимки.
//
//   BIRGE_REPO=<сборка R01 с patch R13> node tests/civic/R13/qa/qa_browser.cjs <папка_снимков>
//
// Проверяет (схема R11 IA_WAVE2 §7, UX_BRIEF): правило «5 вопросов в неделю» видно; у жителя одна главная кнопка;
// вкладки; метка «Пример» у демо; «Ещё → Вопрос акиму» / «Вопросы жителей»; голос «Поддержать» → «Вы поддержали»
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
  && [...document.querySelectorAll(".qa *")].every((e) => e.getBoundingClientRect().right <= innerWidth + 1 || e.closest(".qa-tabs-wrap")));
const openSection = async (page, base, mode, lang) => {
  await page.goto(`${base}/#questions`);
  await page.waitForSelector(".qa", { timeout: 40000 });
  await page.waitForSelector(".qa-card, .qa-empty, .qa-login", { timeout: 20000 });
  await page.waitForTimeout(400);
};

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
          demoTags: document.querySelectorAll(".qa-card .bk-tag--demo").length,
          votes: document.querySelectorAll(".qa-card__vote").length,
          inMap: document.querySelectorAll("#map .qa, #map [class^='qa-']").length,
          more: window.BirgeShell?.navItems("resident") || [],
        }));
        check(`${tag} житель: экран открыт, правило видно`, r.title && r.rule, r.title);
        check(`${tag} житель: одна главная кнопка`, r.primary === 1, r.primary);
        check(`${tag} житель: 3 вкладки, карточки с меткой «Пример»`, r.tabs === 3 && r.cards >= 5 && r.demoTags === r.cards, r);
        check(`${tag} житель: на карте ничего нового`, r.inMap === 0, r.inMap);
        check(`${tag} житель: «Ещё» в меню`, r.more.includes("more"), r.more);
        check(`${tag} житель: нет прокрутки вбок`, await noSideScroll(page));
        await page.screenshot({ path: path.join(OUT, `${tag}-resident-top.png`) });

        if (w === 1366) {
          // «Ещё → Вопрос акиму» в меню жителя.
          await page.goto(`${base}/#map`);
          await page.waitForSelector("#birge-header [data-section=more]", { state: "visible", timeout: 20000 });
          await page.click("#birge-header [data-section=more]");
          const items = await page.$$eval(".birge-more-menu [role=menuitem]", (els) => els.map((e) => [e.dataset.section, e.textContent]));
          check(`${tag} житель: «Ещё» → «Вопрос акиму»`, items.some(([id]) => id === "questions"), items);
          await page.click(".birge-more-menu [data-section=questions]");
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
          const kept = await page.$eval(".qa-card", (c) => !!c.querySelector(".qa-card__voted"));
          check("375-ru житель: «Поддержать» → «Вы поддержали», голос сохранён", before !== after && kept, { before, after, kept });
        }
        if (w === 375) {
          // Форма: пустой текст — ошибка у поля; отправка — «Вопрос отправлен», «Опубликуют после проверки».
          await page.click(".qa__lead .bk-btn--primary");
          await page.waitForSelector("#qa-text");
          check(`${tag} форма: фокус в поле вопроса`, await page.evaluate(() => document.activeElement?.id === "qa-text"));
          await page.screenshot({ path: path.join(OUT, `${tag}-resident-form.png`) });
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
        // «С ответом»: ответ свёрнут, раскрывается.
        await page.click(".qa-tabs > button:nth-child(3)");
        await page.waitForSelector(".qa-answer", { timeout: 10000 });
        const closed = await page.$eval(".qa-answer", (d) => !d.open);
        await page.click(".qa-answer > summary");
        const text = await page.$eval(".qa-answer .qa-answer__text", (p) => p.textContent);
        check(`${tag} житель: ответ акима свёрнут и раскрывается`, closed && text.length > 20, text.slice(0, 60));
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
          pii: [...document.querySelectorAll(".qa-card__warn .bk-tag--warn")].map((t) => t.textContent),
          primary: [...document.querySelectorAll("#birge-screen .bk-btn--primary")].filter((b) => b.offsetParent).length,
        }));
        check(`${tag} акимат: очередь на проверке, подсказка о личных данных`, a.cards >= 1 && a.pii.length >= 1, a);
        check(`${tag} акимат: без главной кнопки в списке`, a.primary === 0, a.primary);
        check(`${tag} акимат: нет прокрутки вбок`, await noSideScroll(sp));
        await sp.screenshot({ path: path.join(OUT, `${tag}-akimat-queue.png`) });
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
          await sp.click(".qa-tabs > button:nth-child(2)");
          await sp.waitForSelector(".qa__week", { timeout: 10000 });
          const topCount = await sp.$$eval(".qa-card", (c) => c.length);
          const topId = await sp.$eval(".qa-card", (c) => c.dataset.id);
          await sp.click(`.qa-card[data-id="${topId}"] .qa-card__actions .bk-btn:not(.bk-btn--ghost)`);
          await sp.fill(`.qa-card[data-id="${topId}"] textarea[lang=${lang}]`, lang === "kk" ? "Бағдаршам қараша айында орнатылады, жоба келісілді." : "Светофор поставят в ноябре, проект согласован.");
          await sp.screenshot({ path: path.join(OUT, `${tag}-akimat-answer.png`) });
          await sp.click(`.qa-card[data-id="${topId}"] .qa-panel button[type=submit]`);
          await sp.waitForFunction((id) => !document.querySelector(`.qa-card[data-id="${id}"] .qa-panel`), topId, { timeout: 10000 });
          await sp.click(".qa-tabs > button:nth-child(3)");
          await sp.waitForSelector(`.qa-card[data-id="${topId}"] .qa-answer[open]`, { timeout: 10000 });
          const week = await sp.evaluate(async () => (await (await fetch("/api/civic/v2/questions/staff?tab=top")).json()).week.answered);
          check(`${tag} акимат: топ-5 ≤ 5, ответ виден в «Отвечено», неделя +1`, topCount <= 5 && week >= 1, { topCount, week });
          await sp.screenshot({ path: path.join(OUT, `${tag}-akimat-answered.png`) });
          // Ответ виден жителю.
          const pub = await sp.evaluate(async (id) => (await (await fetch("/api/civic/v2/questions?tab=answered")).json()).items.some((q) => q.id === id), topId);
          check(`${tag} ответ виден всем во вкладке «С ответом»`, pub);
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
