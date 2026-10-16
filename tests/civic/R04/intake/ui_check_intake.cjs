// R04 П3: проверка экрана «Разбор обращений» в оболочке R01 на стенде (Playwright, Chromium из /opt/pw-browsers).
// Не входит в pytest: нужен запущенный стенд с маршрутами intake/* (research/round-15-results/R04/RUN.txt).
//   R04_STAND=http://127.0.0.1:8655 node tests/civic/R04/intake/ui_check_intake.cjs <папка-для-снимков>
// Проверяет 1366 / 1024 / 375 × ru / kk: числа итога = summary ответа, «Почему так» открывается и Esc его сворачивает,
// Tab из поля доходит до «Разобрать», Ctrl+Enter разбирает, нет картинок и эмодзи, нет горизонтальной прокрутки,
// «Создать задачи» -> «Создано N задач в «Обращениях»» (N = summary.ready), повтор — «уже созданы».
// С 16 окт 19:50 (R10 B-134 / B-135): нет «{n}» и сырых ключей, кнопка — подпись и одно число, «Почему так» — с данными,
// контраст текста ≥ 4,5 : 1, в кадрах счётчика итога слово — в форме для показанного числа.
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
      // Кадры счётчика (~0,7 с): слово — в форме для показанного числа («95 обращений», не «95 обращение»; R10 §16 п. 4).
      const frames = await page.evaluate(async () => {
        const I = window.BirgeI18n, bad = [], seen = new Set();
        const strip = (x) => String(x).replace(/[\d\s\u00a0\u202f]/g, "");
        const t0 = performance.now();
        while (performance.now() - t0 < 900) {
          document.querySelectorAll(".bi-sum__line .bi-sum__part").forEach((el) => {
            const b = el.querySelector(".bi-num");
            if (!b) return;
            const n = Number(b.textContent.replace(/\D/g, ""));
            if (el.getAttribute("data-key") === "texts") seen.add(n);
            const want = I.t("intake.sum." + el.getAttribute("data-key"), { n });
            if (strip(el.textContent) !== strip(want)) bad.push([el.textContent, want]);
          });
          await new Promise((r) => requestAnimationFrame(r));
        }
        return { bad: bad.slice(0, 4), values: seen.size };
      });
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
  await browser.close();
  const ok = results.filter((r) => r[1]).length;
  console.log(`SUMMARY ${ok} / ${results.length}`);
  process.exit(ok === results.length ? 0 : 1);
})().catch((e) => { console.error("FAILED", e); process.exit(1); });
