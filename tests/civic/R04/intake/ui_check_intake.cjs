// R04 П3: проверка экрана «Разбор обращений» в оболочке R01 на стенде (Playwright, Chromium из /opt/pw-browsers).
// Не входит в pytest: нужен запущенный стенд с маршрутами intake/* (research/round-15-results/R04/RUN.txt).
//   R04_STAND=http://127.0.0.1:8655 node tests/civic/R04/intake/ui_check_intake.cjs <папка-для-снимков>
// Проверяет 1366 / 1024 / 375 × ru / kk: числа итога = summary ответа, «Почему так» открывается и Esc его сворачивает,
// Tab из поля доходит до «Разобрать», Ctrl+Enter разбирает, нет картинок и эмодзи, нет горизонтальной прокрутки,
// «Создать задачи» -> «Создано N задач в «Обращениях»» (N = summary.ready), повтор — «уже созданы».
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
function check(name, ok, detail) {
  results.push([name, !!ok]);
  console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : "  " + JSON.stringify(detail).slice(0, 300)));
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
      await page.focus(".bi-text");
      await page.keyboard.press("Control+Enter");
      const res = await (await apiRes).json();
      const data = res && res.ok === true && res.data ? res.data : res;
      await page.waitForSelector(".bi-sum__line", { timeout: 15000 });
      await page.waitForTimeout(900);   // счёт чисел до итога
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
      if (OUT) await page.screenshot({ path: path.join(OUT, `${tag}-3-result.png`) });

      const target = await page.$$(".bi-row");
      await target[Math.min(7, target.length - 1)].click();
      check(`${tag} «Почему так» opens`, await page.$$eval(".bi-task.is-open .bi-why:not([hidden])", (e) => e.length) === 1);
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
        check(`${tag} commit: created + existing = ready`, done.created + done.existing === s.ready && done.failed === 0, done);
        check(`${tag} commit banner`, done.created ? banner.includes(String(done.created)) && /Создан|құрылды/.test(banner)
          : /уже создан|бұрын құрылған/.test(banner), banner);
        if (OUT) await page.screenshot({ path: path.join(OUT, `${tag}-5-commit.png`) });
      }
      check(`${tag} no page errors`, pageErrors.length === 0, pageErrors);
      await ctx.close();
    }
  }
  await browser.close();
  const ok = results.filter((r) => r[1]).length;
  console.log(`SUMMARY ${ok} / ${results.length}`);
  process.exit(ok === results.length ? 0 : 1);
})().catch((e) => { console.error("FAILED", e); process.exit(1); });
