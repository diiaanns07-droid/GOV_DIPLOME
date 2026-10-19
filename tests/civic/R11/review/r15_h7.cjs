/*
 * R11 · кадр-герой H7 книги экранов «Спросить Birge: ответ числами» — ответ на готовый вопрос (чип) с меткой «ИИ» (П3).
 *
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/r15_h7.cjs <BASE> <OUT> <файл-пароля> [--sizes 1366,375]
 *
 * Акимат, вход сотрудника до загрузки страницы; #analyst → первый чип («Где в Нуре больше всего жалоб на снег за неделю?»)
 * → ждём карточку ответа. Кадры: <OUT>/h7-analyst-<ширина>-<язык>.jpg; итог <OUT>/h7.json (метка «ИИ», числа, ошибки JS).
 * Демо-данные не меняет: вопрос — только чтение. Пароль читается из файла и не печатается.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const { shellReady } = require("./r15_screens.cjs");

const [BASE, OUT, PWFILE] = process.argv.slice(2);
if (!BASE || !OUT || !PWFILE) { console.error("node r15_h7.cjs <BASE> <OUT> <файл-пароля> [--sizes 1366,375]"); process.exit(2); }
const args = process.argv.slice(5);
const SIZES = (args.includes("--sizes") ? args[args.indexOf("--sizes") + 1] : "1366,375").split(",").map(Number);
const PASSWORD = fs.readFileSync(PWFILE, "utf8").trim();
fs.mkdirSync(OUT, { recursive: true });
const VIEW = { 1366: [1366, 768, 1], 1024: [1024, 768, 1], 375: [375, 812, 2] };

(async () => {
  const browser = await chromium.launch({ env: { ...process.env, LANG: "ru_RU.UTF-8", LC_ALL: "ru_RU.UTF-8" } });
  const report = { base: BASE, when: new Date().toISOString(), frames: [], problems: [] };
  for (const w of SIZES) for (const lang of ["ru", "kk"]) {
    const [vw, vh, dpr] = VIEW[w];
    const ctx = await browser.newContext({ viewport: { width: vw, height: vh }, deviceScaleFactor: dpr, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", l); localStorage.setItem("birge.i18n.lang", l); } catch (e) { /* приватный режим */ } }, lang);
    const login = await ctx.request.post(BASE + "/api/civic/v1/session/login", { data: { username: "operator", password: PASSWORD }, headers: { Origin: BASE } });
    const tag = `h7-analyst-${w}-${lang}`;
    if (login.status() !== 200) { report.problems.push(`${tag}: вход сотрудника не удался (${login.status()})`); await ctx.close(); continue; }
    const page = await ctx.newPage();
    const errors = []; page.on("pageerror", (e) => errors.push(String(e).slice(0, 160)));
    await page.goto(BASE + "/#analyst"); await shellReady(page);
    // чипы перерисовываются при загрузке словаря — нажимаем через локатор (он находит элемент заново)
    const chip = page.locator(".ba-chip").first();
    if (!(await chip.waitFor({ timeout: 20000 }).then(() => true, () => false))) { report.problems.push(`${tag}: нет готовых вопросов`); await ctx.close(); continue; }
    await page.waitForTimeout(500);
    await chip.click();
    await page.waitForSelector(".ba-answer .ba-answer__title", { timeout: 20000 }).catch(() => report.problems.push(`${tag}: нет ответа за 20 с`));
    await page.waitForTimeout(800);
    await page.evaluate((w) => { const c = document.querySelector(".ba-answer"); if (c) c.scrollIntoView({ block: w < 700 ? "start" : "center" }); }, w);
    await page.mouse.move(4, 4);   // курсор с чипа — в угол над картой (без подсветки наведения в кадре)
    await page.waitForTimeout(300);
    const file = tag + ".jpg";
    await page.screenshot({ path: path.join(OUT, file), type: "jpeg", quality: 82 });
    const st = await page.evaluate(() => {
      const vis = (e) => !!e && e.getClientRects().length > 0 && getComputedStyle(e).visibility !== "hidden";
      const card = document.querySelector(".ba-answer");
      const ai = card && card.querySelector(".bk-ai");
      return {
        question: ((card && card.querySelector(".ba-q__text")) || {}).textContent || "",
        headline: ((card && card.querySelector(".ba-answer__title")) || {}).textContent || "",
        ai: ai && vis(ai) ? (ai.querySelector(".bk-ai__t") || ai).textContent.trim() : null,
        ai_hint: ai ? ai.getAttribute("title") : null,
        numbers: card ? [...card.querySelectorAll(".ba-num__value")].map((n) => n.textContent.trim()) : [],
        scroll: Math.max(0, document.documentElement.scrollWidth - window.innerWidth),
      };
    });
    report.frames.push({ file, width: w, lang, ...st, errors });
    if (!st.ai) report.problems.push(`${tag}: нет метки «ИИ» у ответа (П3)`);
    if (st.scroll) report.problems.push(`${tag}: горизонтальная прокрутка ${st.scroll} px`);
    if (errors.length) report.problems.push(`${tag}: ошибки JS ${errors.join(" | ")}`);
    console.log(`${file} · «${st.headline.trim().slice(0, 60)}» · ИИ: ${st.ai || "—"} · числа: ${st.numbers.join(", ")}`);
    await ctx.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, "h7.json"), JSON.stringify(report, null, 1));
  for (const p of report.problems) console.log("ПРОБЛЕМА " + p);
  console.log(`кадров ${report.frames.length}, проблем ${report.problems.length}`);
  process.exit(report.problems.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
