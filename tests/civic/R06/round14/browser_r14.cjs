// R06 раунд 14 · проверка карточек в настоящем браузере (Chromium, Playwright) на стенде serve_r14.py.
//
//   python3 tests/civic/R06/round14/serve_r14.py --port 8616 --age-days 16 > stand.json &
//   NODE_PATH="$(npm root -g)" node tests/civic/R06/round14/browser_r14.cjs stand.json [папка-скриншотов]
//
// Что проверяется (UX_BRIEF + prompts/R06.txt «ГОТОВО, КОГДА»):
//  - 375×812 и 1366×768, ru и kk: нет горизонтальной прокрутки, нет сырых ключей вида proposal.vote_up,
//    нет предупреждений [i18n], кнопки голосования ≥ 48 px, полоса из 6 этапов и «Отстаёт на…» видны;
//  - голос: «За» +1; повтор «За» — счёт тот же; «Против» — голос переходит; перезагрузка — голос на месте;
//  - акимат: «Одобрить» → статус «Одобрено», голосование закрыто;
//  - нет связи с API → состояние ошибки с кнопкой «Повторить».
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const stand = JSON.parse(fs.readFileSync(process.argv[2], "utf8").trim().split("\n")[0]);
const shots = process.argv[3] || null;
const URL = stand.url;
const results = [];

function check(name, ok, detail) {
  results.push({ name, ok: !!ok, detail: detail || "" });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? " — " + detail : ""));
}

async function openPage(browser, viewport, lang, query) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  const page = await context.newPage();
  const warnings = [];
  page.on("console", (msg) => {
    if (msg.type() === "warning" || msg.type() === "error") warnings.push(msg.text());
  });
  page.on("pageerror", (err) => warnings.push("pageerror: " + err.message));
  await page.goto(URL + "?lang=" + lang + (query ? "&" + query : ""));
  await page.waitForSelector(".r06-card[data-proposal]", { timeout: 10000 });
  await page.waitForSelector(".r06-card[data-object]", { timeout: 10000 });
  await page.waitForTimeout(300);
  return { context, page, warnings };
}

async function layoutChecks(page, label, warnings) {
  const m = await page.evaluate(() => {
    const doc = document.documentElement;
    const text = document.body.innerText;
    const rawKeys = text.match(/\b(?:proposal|object|stage|common|district|status)\.[a-z_]+(?:\.[a-z_]+)*\b/g) || [];
    const voteBtns = Array.from(document.querySelectorAll(".r06-vote__btn")).map((b) => b.getBoundingClientRect().height);
    const cards = Array.from(document.querySelectorAll(".r06-card")).map((c) => c.getBoundingClientRect());
    return {
      scroll: doc.scrollWidth - window.innerWidth,
      rawKeys,
      minVote: Math.min.apply(null, voteBtns),
      overflowCards: cards.filter((r) => r.right > window.innerWidth + 0.5 || r.left < -0.5).length,
      stages: document.querySelectorAll(".r06-card[data-object] .bk-stages > li").length,
      late: Array.from(document.querySelectorAll(".bk-tag--warn")).map((e) => e.textContent.trim()),
      stale: document.body.innerText.match(/Не обновлялось|жаңартылмаған/g) || [],
      htmlLang: document.documentElement.lang,
    };
  });
  check(label + ": нет горизонтальной прокрутки", m.scroll <= 0, "scrollWidth−width=" + m.scroll);
  check(label + ": карточки внутри экрана", m.overflowCards === 0, String(m.overflowCards));
  check(label + ": нет сырых ключей", m.rawKeys.length === 0, m.rawKeys.slice(0, 5).join(", "));
  const i18nWarn = warnings.filter((w) => w.indexOf("[i18n]") >= 0);
  check(label + ": нет предупреждений [i18n]", i18nWarn.length === 0, i18nWarn.slice(0, 3).join(" | "));
  const errors = warnings.filter((w) => w.indexOf("[i18n]") < 0 && !/404/.test(w));
  check(label + ": нет ошибок в консоли (кроме ожидаемого 404 «нет объекта»)", errors.length === 0, errors.slice(0, 3).join(" | "));
  check(label + ": кнопки «За/Против» ≥ 48 px", m.minVote >= 48, "min=" + m.minVote);
  check(label + ": полоса 6 этапов у каждого объекта", m.stages > 0 && m.stages % 6 === 0, "li=" + m.stages);
  check(label + ": значок «Отстаёт на N…» (цвет + слова)", m.late.length > 0 && /\d/.test(m.late[0]), m.late[0] || "");
  check(label + ": «давно не обновлялось» видно", m.stale.length > 0, String(m.stale.length));
}

async function counts(page, id) {
  return page.evaluate((pid) => {
    const card = document.querySelector('.r06-card[data-proposal="' + pid + '"]');
    const btns = card.querySelectorAll(".r06-vote__btn");
    const num = (b) => Number(b.querySelector(".bk-btn__count").textContent.replace(/\s/g, ""));
    return { up: num(btns[0]), down: num(btns[1]), upPressed: btns[0].getAttribute("aria-pressed"), downPressed: btns[1].getAttribute("aria-pressed") };
  }, id);
}

async function clickVote(page, id, value) {
  const sel = '.r06-card[data-proposal="' + id + '"] .r06-vote__btn[data-value="' + value + '"]';
  const respond = page.waitForResponse((r) => r.url().indexOf("/vote") > 0);
  await page.click(sel);
  await respond;
  await page.waitForTimeout(150);
}

(async () => {
  const browser = await chromium.launch({ executablePath: fs.existsSync("/opt/pw-browsers/chromium") ? undefined : undefined });
  try {
    for (const lang of ["ru", "kk"]) {
      for (const vp of [{ width: 375, height: 812 }, { width: 1366, height: 768 }]) {
        const label = lang + " " + vp.width;
        const { context, page, warnings } = await openPage(browser, vp, lang);
        await layoutChecks(page, label, warnings);
        if (shots) {
          fs.mkdirSync(shots, { recursive: true });
          await page.screenshot({ path: path.join(shots, "r06-" + vp.width + "-" + lang + ".png"), fullPage: false });
          await page.screenshot({ path: path.join(shots, "r06-" + vp.width + "-" + lang + "-full.png"), fullPage: true });
        }
        await context.close();
      }
    }

    // Голосование: одно устройство (один контекст браузера = один localStorage).
    {
      const { context, page } = await openPage(browser, { width: 375, height: 812 }, "ru");
      // Карточка с открытым голосованием (на стенде после прошлых прогонов одна может быть уже одобрена).
      const id = await page.getAttribute(".r06-card[data-proposal]:has(.r06-vote__btn:not([disabled]))", "data-proposal");
      const start = await counts(page, id);
      await clickVote(page, id, 1);
      const a = await counts(page, id);
      check("голос «За» +1", a.up === start.up + 1 && a.upPressed === "true", JSON.stringify(a));
      await clickVote(page, id, 1);
      const b = await counts(page, id);
      check("повтор «За» не удваивает", b.up === a.up && b.down === a.down, JSON.stringify(b));
      await clickVote(page, id, -1);
      const c = await counts(page, id);
      check("«Против» меняет голос", c.up === start.up && c.down === start.down + 1 && c.downPressed === "true", JSON.stringify(c));
      const focused = await page.evaluate(() => document.activeElement && document.activeElement.getAttribute("data-value"));
      check("фокус остаётся на нажатой кнопке", focused === "-1", String(focused));
      await page.reload();
      await page.waitForSelector('.r06-card[data-proposal="' + id + '"]');
      const d = await counts(page, id);
      check("после перезагрузки голос на месте", d.down === c.down && d.downPressed === "true", JSON.stringify(d));
      if (shots) await page.screenshot({ path: path.join(shots, "r06-375-ru-voted.png") });
      await context.close();
      // Другое устройство видит те же числа, но без своего голоса.
      const other = await openPage(browser, { width: 375, height: 812 }, "ru");
      const e = await counts(other.page, id);
      check("другое устройство: те же счётчики, своего голоса нет", e.down === c.down && e.downPressed === "false", JSON.stringify(e));
      await other.context.close();
    }

    // Акимат: вход сотрудника, «Одобрить».
    {
      const { context, page } = await openPage(browser, { width: 1366, height: 768 }, "kk");
      const login = await page.evaluate(async (cred) => {
        const r = await fetch("/api/civic/v1/session/login", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cred), credentials: "same-origin",
        });
        return r.status;
      }, { username: stand.username, password: stand.password });
      check("вход сотрудника акимата", login === 200, String(login));
      await page.goto(URL + "?lang=kk&role=akimat");
      await page.waitForSelector('.r06-card[data-proposal] [data-action="approve"]');
      const id = await page.getAttribute('.r06-card[data-proposal]:has([data-action="approve"])', "data-proposal");
      if (shots) await page.screenshot({ path: path.join(shots, "r06-1366-kk-akimat.png") });
      const respond = page.waitForResponse((r) => r.url().indexOf("/approve") > 0);
      await page.click('.r06-card[data-proposal="' + id + '"] [data-action="approve"]');
      const res = await respond;
      await page.waitForTimeout(200);
      const st = await page.evaluate((pid) => {
        const card = document.querySelector('.r06-card[data-proposal="' + pid + '"]');
        return { status: card.querySelector(".bk-status").textContent, disabled: card.querySelector(".r06-vote__btn").disabled, actions: card.querySelectorAll("[data-action]").length };
      }, id);
      check("«Мақұлдау» → статус «Мақұлданды», голосование закрыто", res.status() === 200 && st.status === "Мақұлданды" && st.disabled && st.actions === 0, JSON.stringify(st));
      await context.close();
    }

    // Нет связи с API.
    {
      const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
      const page = await context.newPage();
      await page.route("**/api/civic/v2/**", (route) => route.abort());
      await page.goto(URL + "?lang=ru");
      await page.waitForSelector(".bk-error, [role=alert], .bk-empty", { timeout: 8000 }).catch(() => null);
      await page.waitForTimeout(300);
      const txt = await page.evaluate(() => document.body.innerText);
      check("нет связи → «Нет связи с сервером» и «Повторить»", /Нет связи с сервером/.test(txt) && /Повторить/.test(txt), txt.slice(0, 160).replace(/\n/g, " / "));
      if (shots) await page.screenshot({ path: path.join(shots, "r06-375-ru-offline.png") });
      await context.close();
    }
  } finally {
    await browser.close();
  }
  const failed = results.filter((r) => !r.ok);
  console.log(JSON.stringify({ total: results.length, failed: failed.length }));
  if (shots) fs.writeFileSync(path.join(shots, "browser_r14.json"), JSON.stringify(results, null, 1));
  process.exit(failed.length ? 1 : 0);
})().catch((err) => {
  console.error(err);
  process.exit(2);
});
