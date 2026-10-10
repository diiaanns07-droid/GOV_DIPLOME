/* R12 round 14 · I-04 (R01 BUGS) / R10 B-021: кабинет сотрудника по-казахски через ключи R11 (staff.*, works.*).
 * Словарь — настоящий R11 из ветки claude/r14-R11 @ 548510b (git show во временную папку; нет коммита — тест NOT_RUN).
 * Проверяет: форма входа и список на ҚАЗ без русских строк из проверки R10 (tests/e2e/demo_flow.cjs шаг 5),
 * «Вы вошли: имя» без роли и адресов сервера в режиме Birge, перерисовку при смене ҚАЗ/РУС без потери введённого.
 * Run:  node --test tests/civic/R12/editor/e2e_r12_kk.test.cjs     (R12_SHOTS=1 -> research/round-14-results/R12/screenshots/)
 */
"use strict";
const { describe, it, before, after } = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const fs = require("fs");
const os = require("os");
const { execFileSync } = require("child_process");
const { startStand } = require("./stand.cjs");
const { loadPlaywright, makeKit, fk } = require("./e2e_helpers.cjs");

const PW = loadPlaywright();
const REPO = path.resolve(__dirname, "../../../..");
const SHOTS = path.resolve(REPO, "research/round-14-results/R12/screenshots");
const R11_SHA = process.env.R12_R11_SHA || "548510bb";
// Те же выражения, что у R10 (demo_flow.cjs, шаг 5 «ҚАЗ: форма входа и кабинет сотрудника по-казахски»).
const RU_LOGIN = /Вход для сотрудника|Имя пользователя|Пароль|Войти\b|Учётную запись создаёт/g;
const RU_CABINET = /Кабинет редактора|Вы вошли|Новый объект|Обновить список|Черновики|Опубликованные|Архив|Выйти\b/g;
// Остальные русские подписи списка, которые были в коде до I-04.
const RU_LIST = /синтетические данные|без места на карте|окончание:|ред\. \d|тип не указан|Только мои|Дорожные работы|Запланировано|Черновик\b/g;
const TECH = /роль по данным сервера|\/staff\/meta|правила проверки/;

function r11Dicts() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "r12-i18n-"));
  try {
    for (const f of ["i18n.js", "ru.json", "kk.json"]) {
      const text = execFileSync("git", ["show", R11_SHA + ":web/civic/i18n/" + f], { cwd: REPO, maxBuffer: 16 << 20 });
      fs.writeFileSync(path.join(dir, f), text);
    }
    return dir;
  } catch (e) {
    return null;
  }
}

const DICT = PW ? r11Dicts() : null;
const SKIP = !PW ? "playwright not installed" : !DICT ? "словарь R11 " + R11_SHA + " недоступен в этом клоне (git fetch origin claude/r14-R11)" : false;

describe("R12 editor: staff cabinet in Kazakh (I-04, B-021)", { skip: SKIP }, () => {
  let stand, browser, K;
  const pages = [];
  before(async () => {
    stand = await startStand({ staticDirs: [{ prefix: "/web/civic/i18n/", dir: DICT }] });
    browser = await PW.chromium.launch({ args: ["--enable-unsafe-swiftshader"] });
    if (process.env.R12_SHOTS === "1") fs.mkdirSync(SHOTS, { recursive: true });
    K = makeKit({ stand, browser, pages, shotsDir: SHOTS });
  });
  after(async () => {
    for (const p of pages) for (const e of p.errors) console.error("pageerror:", e);
    if (browser) await browser.close();
    if (stand) await stand.close();
    if (DICT) fs.rmSync(DICT, { recursive: true, force: true });
  });
  const shot = async (p, name) => { if (process.env.R12_SHOTS === "1") await p.screenshot({ path: path.join(SHOTS, name + ".png") }); };

  // Страница стенда с i18n.js R11 перед редактором (как web/index.html сборки R01) и режимом оболочки Birge.
  async function openKk(viewport) {
    const p = await K.newPage(viewport);
    const html = fs.readFileSync(path.join(__dirname, "harness/index.html"), "utf8")
      .replace('<script src="/web/civic/editor/editor-core.js"></script>', '<script src="/web/civic/i18n/i18n.js"></script>\n  <script src="/web/civic/editor/editor-core.js"></script>');
    assert.ok(html.includes("/web/civic/i18n/i18n.js"), "i18n.js встроен в страницу стенда");
    await p.route((u) => new URL(u).pathname === "/", (r) => r.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: html }));
    await p.addInitScript(() => { document.addEventListener("DOMContentLoaded", () => { document.body.dataset.birgeTools = "off"; }); });
    K.H().reset();
    await p.goto(stand.url + "/?lang=kk");
    await p.waitForFunction(() => window.BirgeI18n && window.BirgeI18n.getLang() === "kk" && window.BirgeI18n.has("staff.login.title"));
    await p.waitForSelector(fk("login-user"));
    // словарь грузится асинхронно: форма перерисована на казахском
    await p.waitForFunction(() => /Қызметкерге кіру/.test(document.querySelector(".civic-r04").innerText));
    return p;
  }
  const text = (p) => p.evaluate(() => document.querySelector(".civic-r04").innerText);

  it("login form: Kazakh labels, no Russian strings R10 looks for; ҚАЗ ↔ РУС keeps what was typed", async () => {
    const p = await openKk();
    const t = await text(p);
    assert.deepEqual(t.match(RU_LOGIN) || [], [], t);
    assert.match(t, /Пайдаланушы аты/);
    assert.match(t, /Құпиясөз/);
    assert.equal((await p.textContent(fk("login-submit"))).trim(), "Кіру");
    await shot(p, "cabinet-kk-login-1366");
    // пустая форма -> понятная ошибка по-казахски
    await p.click(fk("login-submit"));
    await p.waitForFunction(() => /енгізіңіз/.test(document.querySelector(".civic-r04-err").textContent));
    // смена языка не стирает введённое имя и пароль, фокус остаётся в поле
    await p.fill(fk("login-user"), stand.creds.username);
    await p.fill(fk("login-pass"), stand.creds.password);
    await p.focus(fk("login-pass"));
    await p.evaluate(() => window.BirgeI18n.setLang("ru"));
    await p.waitForFunction(() => /Вход для сотрудника/.test(document.querySelector(".civic-r04").innerText));
    assert.equal(await K.value(p, "login-user"), stand.creds.username);
    assert.equal(await K.value(p, "login-pass"), stand.creds.password);
    assert.equal(await p.evaluate(() => document.activeElement.getAttribute("data-fk")), "login-pass");
    await p.evaluate(() => window.BirgeI18n.setLang("kk"));
    await p.waitForFunction(() => /Қызметкерге кіру/.test(document.querySelector(".civic-r04").innerText));
    assert.equal(await K.value(p, "login-pass"), stand.creds.password);
    await p.press(fk("login-pass"), "Enter");
    await p.waitForSelector(fk("new"));
    await p.close();
  });

  it("cabinet list: Kazakh head, tabs and rows; «Сіз кірдіңіз: имя» without role/server lines in Birge mode", async () => {
    const p = await openKk();  // openKk сбрасывает стенд — запись создаём после
    await K.seedDraft({ title: "Тест: жол жөндеу (R12)" });
    await K.login(p);
    await p.waitForSelector(fk("new"));
    await p.waitForSelector(".civic-r04-row");
    const t = await text(p);
    assert.deepEqual(t.match(RU_CABINET) || [], [], t);
    assert.deepEqual(t.match(RU_LIST) || [], [], t);
    assert.doesNotMatch(t, TECH, "служебная строка скрыта в режиме Birge");
    assert.match(t, /Қызметкер кабинеті/);
    assert.match(await p.textContent(".civic-r04-who"), /^Сіз кірдіңіз: Тестовый редактор$/);
    assert.equal((await p.textContent(fk("logout"))).trim(), "Шығу");
    assert.match(await p.textContent(fk("filter-draft")), /^Қаралама жазбалар · 1$/);
    const row = await p.textContent(".civic-r04-row");
    assert.match(row, /Жол жұмыстары · Жоспарланған · аяқталуы: 20/);
    assert.match(row, /Үлгі/);
    await shot(p, "cabinet-kk-list-1366");
    // без режима Birge (стенды, ?tools=all) служебная строка видна разработчику — как раньше
    await p.evaluate(() => { document.body.dataset.birgeTools = "all"; });
    assert.match(await p.innerText(".civic-r04-head"), TECH);
    // смена языка перерисовывает список
    await p.evaluate(() => window.BirgeI18n.setLang("ru"));
    await p.waitForFunction(() => /Кабинет сотрудника/.test(document.querySelector(".civic-r04").innerText));
    assert.match(await p.textContent(fk("filter-draft")), /^Черновики · 1$/);
    assert.match(await p.textContent(".civic-r04-row"), /Дорожные работы · Запланировано/);
    await p.close();
  });

  it("phone 375 px: Kazakh cabinet fits without horizontal scroll", async () => {
    const p = await openKk({ width: 375, height: 760 });
    await K.login(p);
    await p.waitForSelector(fk("new"));
    const m = await p.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
    assert.ok(m.sw <= m.cw + 1, JSON.stringify(m));
    await shot(p, "cabinet-kk-list-375");
    await p.close();
  });
});
