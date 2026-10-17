/*
 * R11 · раунд 15+ (П3): кадры и автопроверка сцены 0 «Разбор обращений» (R04 BirgeIntake) по шагам —
 * пусто → «Пример: обращения за ночь» → «Разобрать» → итог → «Почему так» → «Создать задачи».
 *
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/r15_intake.cjs <BASE> <OUT> <файл-пароля> [--quick] [--no-commit]
 *     --quick — только 1366 и 375; --no-commit — не создавать задачи (стенд без записи в «Обращения»)
 *
 * Проверки как у r15_screens.cjs (прокрутка, сырые ключи, русские подписи в ҚАЗ, обрезанные подписи, ошибки JS) и свои:
 * время разбора примера (П3: ≤ 10 с на 300), одна главная кнопка на шаг, метка «ИИ» у заголовка, «Срочно» — первой группой.
 * Пароль сотрудника читается из файла и не печатается.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const { audit, shellReady, ruOnlyTexts } = require("./r15_screens.cjs");

const [BASE, OUT, PWFILE] = process.argv.slice(2);
if (!BASE || !OUT || !PWFILE) { console.error("node r15_intake.cjs <BASE> <OUT> <файл-пароля> [--quick] [--no-commit]"); process.exit(2); }
const args = process.argv.slice(5);
const QUICK = args.includes("--quick");
const COMMIT = !args.includes("--no-commit");
const PASSWORD = fs.readFileSync(PWFILE, "utf8").trim();
fs.mkdirSync(OUT, { recursive: true });
const SIZES = QUICK ? [[1366, 768, 1], [375, 812, 2]] : [[1366, 768, 1], [1024, 768, 1], [375, 812, 2]];

async function shot(page, report, tag, lang, w, ruOnly, errors, extra) {
  // курсор — в угол над картой: после нажатия он оставался над строкой списка, и в кадре была подсветка наведения
  await page.mouse.move(4, 4);
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(OUT, tag + ".jpg"), type: "jpeg", quality: 80 });
  const a = await audit(page, lang, w, ruOnly);
  Object.assign(a, extra || {}, await page.evaluate(() => {
    const box = document.querySelector("#birge-screen:not([hidden])") || document;
    const vis = (e) => !!e && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== "hidden";
    const head = box.querySelector(".bi-head");
    return {
      ai_in_head: !!(head && [...head.querySelectorAll(".bk-ai, .bi-aitag, [title]")].some((e) => vis(e) && /ИИ|ЖИ/.test(e.textContent))),
      groups: [...box.querySelectorAll(".bi-gsec")].map((g) => (g.querySelector("h3, h4, .bi-gsec__title, [id]") || g).textContent.trim().slice(0, 40)),
      sum: (box.querySelector(".bi-sum__text") || {}).textContent || "",
      sheet_w: Math.round((box.getBoundingClientRect && box.getBoundingClientRect().width) || 0),
    };
  }));
  a.errors = errors.splice(0);
  report.frames[tag] = a;
  if (a.scroll) report.problems.push(`${tag}: горизонтальная прокрутка ${a.scroll} px`);
  if (a.keys.length) report.problems.push(`${tag}: сырые ключи ${a.keys.join(" | ")}`);
  if (a.cut.length && w === 375 && lang === "kk") report.problems.push(`${tag}: обрезано ${a.cut.join(" | ")}`);
  if (a.errors.length) report.problems.push(`${tag}: ошибки JS ${a.errors.join(" | ")}`);
  if (lang === "kk" && a.ru_in_kk.length) report.problems.push(`${tag}: русские подписи в ҚАЗ ${a.ru_in_kk.join(" | ")}`);
  return a;
}

(async () => {
  const browser = await chromium.launch({ env: { ...process.env, LANG: "ru_RU.UTF-8", LC_ALL: "ru_RU.UTF-8" } });
  const report = { base: BASE, when: new Date().toISOString(), frames: {}, timings: {}, problems: [] };
  const ruOnly = await ruOnlyTexts(browser, BASE);
  for (const [w, h, dpr] of SIZES) for (const lang of ["ru", "kk"]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); localStorage.setItem("birge.i18n.lang", l); } catch (e) { /* приватный режим */ } }, lang);
    // вход — до загрузки страницы (как ui_check_intake R04): оболочка при старте берёт сессию и CSRF сотрудника;
    // fetch изнутри уже открытой страницы + смена только #адреса оставляли оболочку без CSRF (POST intake/analyze — 403)
    const login = await ctx.request.post(BASE + "/api/civic/v1/session/login", { data: { username: "operator", password: PASSWORD }, headers: { Origin: BASE } });
    if (login.status() !== 200) { report.problems.push(`${w}-${lang}: вход сотрудника не удался (${login.status()})`); await ctx.close(); continue; }
    const page = await ctx.newPage();
    const errors = []; page.on("pageerror", (e) => errors.push(String(e).slice(0, 160)));
    const pre = `intake-${w}-${lang}`;
    await page.goto(BASE + "/#intake"); await shellReady(page);
    await page.evaluate((l) => { const I = window.BirgeI18n; if (I && I.getLang && I.getLang() !== l && I.setLang) I.setLang(l); }, lang);
    try { await page.waitForSelector("[data-act=sample]", { timeout: 15000 }); } catch (e) { report.problems.push(`${pre}: экран разбора не открылся`); }
    const a0 = await shot(page, report, `${pre}-1-empty`, lang, w, ruOnly, errors);
    if (!a0.ai_in_head) report.problems.push(`${pre}-1-empty: нет метки «ИИ» у заголовка (П3)`);
    // шаг 2: пример «обращения за ночь»
    await page.click("[data-act=sample]");
    await page.waitForFunction(() => { const t = document.querySelector(".bi-text"); return t && t.value.split("\n").filter((x) => x.trim()).length > 5; }, null, { timeout: 15000 }).catch(() => report.problems.push(`${pre}: пример не загрузился`));
    const lines = await page.evaluate(() => (document.querySelector(".bi-text") || { value: "" }).value.split("\n").filter((x) => x.trim()).length);
    await shot(page, report, `${pre}-2-sample`, lang, w, ruOnly, errors, { lines });
    // шаг 3: «Разобрать» — до строки итога
    const t0 = Date.now();
    await page.click("[data-act=run]");
    await page.waitForSelector(".bi-sum__line, .bi-error", { timeout: 30000 }).catch(() => null);
    const ms = Date.now() - t0;
    const fail = await page.evaluate(() => { const e = document.querySelector(".bi-error"); return e ? e.textContent.trim().replace(/\s+/g, " ").slice(0, 120) : null; });
    const done = await page.$(".bi-sum__line");
    if (fail) report.problems.push(`${pre}: ошибка разбора — ${fail}`);
    else if (!done) report.problems.push(`${pre}: итог не появился за 30 с`);
    report.timings[`${pre}`] = { lines, ms, ok: !!done };
    if (done && ms > 10000) report.problems.push(`${pre}: разбор ${lines} обращений — ${ms} мс (> 10 с, П3)`);
    await page.waitForTimeout(1500);   // счётчики итога добегают
    const a3 = await shot(page, report, `${pre}-3-result`, lang, w, ruOnly, errors, { ms });
    if (a3.groups.length && !/Срочно|Шұғыл/.test(a3.groups[0])) report.problems.push(`${pre}-3-result: первая группа «${a3.groups[0]}», ожидалось «Срочно»`);
    if ((a3.main || []).length > 1) report.problems.push(`${pre}-3-result: главных кнопок ${a3.main.length} [${a3.main.join(" | ")}]`);
    // шаг 3б: список задач ниже итога (прокрутка листа)
    await page.evaluate(() => { const r = document.querySelector(".bi-list"); if (r) r.scrollIntoView({ block: "start" }); });
    await shot(page, report, `${pre}-3b-list`, lang, w, ruOnly, errors);
    // шаг 4: «Почему так» у первой задачи
    const row = await page.$(".bi-task .bi-row");
    if (row) { await row.click(); await page.waitForTimeout(400); await page.evaluate(() => { const o = document.querySelector(".bi-task.is-open"); if (o) o.scrollIntoView({ block: "start" }); }); }
    await shot(page, report, `${pre}-4-why`, lang, w, ruOnly, errors);
    // шаг 5: «Создать задачи» — тост со ссылкой на «Обращения»
    if (COMMIT) {
      await page.evaluate(() => { const b = document.querySelector("[data-act=commit]"); if (b) b.scrollIntoView({ block: "center" }); });
      const c = await page.$("[data-act=commit]:not([disabled])");
      if (c) {
        await c.click();
        // подтверждение — строка экрана («Создано N задач в «Обращениях»») или тост; пустой контейнер тостов не считается
        await page.waitForFunction(() => [...document.querySelectorAll(".bk-toast, .bi-done")].some((e) => e.textContent.trim().length > 3),
          null, { timeout: 20000 }).catch(() => report.problems.push(`${pre}: нет подтверждения после «Создать задачи»`));
        const toast = await page.evaluate(() => [...document.querySelectorAll(".bk-toast, .bi-done")].map((e) => e.textContent.trim().replace(/\s+/g, " ")).join(" | "));
        await shot(page, report, `${pre}-5-created`, lang, w, ruOnly, errors, { toast });
      } else report.problems.push(`${pre}: кнопка «Создать задачи» неактивна`);
    }
    await ctx.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, "r15_intake.json"), JSON.stringify(report, null, 1));
  for (const p of report.problems) console.log("ПРОБЛЕМА " + p);
  for (const [k, t] of Object.entries(report.timings)) console.log(`время ${k}: ${t.lines} обращений — ${t.ms} мс`);
  const soft = Object.entries(report.frames).filter(([, a]) => a.cut.length || a.cut_rows.length);
  for (const [tag, a] of soft) console.log(`смотреть ${tag}:` + (a.cut.length ? ` обрезано [${a.cut.join(" | ")}]` : "")
    + (a.cut_rows.length ? ` строки с многоточием [${a.cut_rows.slice(0, 4).join(" | ")}]` : ""));
  console.log(`кадров ${Object.keys(report.frames).length}, проблем ${report.problems.length}`);
  process.exit(report.problems.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
