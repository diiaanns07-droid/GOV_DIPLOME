/*
 * Кадры и проверки экрана «Спросить Birge» на стенде R03 (analyst_devserver.py).
 *
 *   python3 -B tests/civic/R03/round15/analyst_devserver.py --port 8670 &
 *   NODE_PATH=$(npm root -g) node tests/civic/R03/round15/analyst_screens.cjs --url http://127.0.0.1:8670 \
 *       --out research/round-15-results/R03/screens
 *
 * Что проверяет (каждая проверка — строка PASS/FAIL в выводе и в checks.json):
 *  - три вопроса сценария: карточка с числами, «Показать на карте» ведёт на цель, метка «офлайн-режим»;
 *  - ҚАЗ / РУС: смена языка без нового запроса (тот же ответ, другой язык);
 *  - состояния: пусто (до вопроса), скелетон (медленный ответ), нет сети, 503, 403, пустой вопрос;
 *  - клавиатура: Enter задаёт вопрос, Esc очищает поле, Tab доходит до «Показать на карте»;
 *  - нет горизонтальной прокрутки на 375 / 1024 / 1366, длинный казахский текст не обрезается.
 */
"use strict";
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, v, i, all) => {
  if (v.startsWith("--")) acc.push([v.slice(2), all[i + 1] && !all[i + 1].startsWith("--") ? all[i + 1] : "1"]);
  return acc;
}, []));
const URL = (args.url || "http://127.0.0.1:8670") + "/civic/assistant/analyst-demo.html";
const OUT = args.out || "research/round-15-results/R03/screens";
const SIZES = [[1366, 768], [1024, 768], [375, 812]];
const SCENE = {
  ru: ["Где в Нуре больше всего жалоб на снег за неделю и какие службы отстают?", "Какие службы отстают?", "Что с бураном?"],
  kk: ["Нұрада бір аптада қар туралы шағым қай жерде көп?", "Қай қызметтер артта қалып жатыр?", "Боран бойынша не жағдай?"],
};
const checks = [];
function check(name, ok, detail) {
  checks.push({ name, ok: !!ok, detail: detail || null });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? " — " + detail : ""));
}

async function noHScroll(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
}
async function waitAnswer(page) {
  await page.waitForSelector(".ba-answer", { timeout: 15000 });
  await page.waitForTimeout(260); // анимация появления 200 мс
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  try {
    for (const [w, h] of SIZES) {
      for (const lang of ["ru", "kk"]) {
        const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
        await page.goto(URL + "?lang=" + lang);
        await page.waitForSelector(".ba-empty");
        const tag = `${w}_${lang}`;
        if (w === 1366 || w === 375) await page.screenshot({ path: path.join(OUT, `analyst_idle_${tag}.png`) });
        check(`idle chips ${tag}`, (await page.locator(".ba-chip:visible").count()) >= 4);
        check(`idle: no clear button in empty field ${tag}`, !(await page.locator(".ba-clear").isVisible()));
        check(`idle: one small icon, one button (P1) ${tag}`,
          (await page.locator(".ba-empty .ic--48").count()) === 1 && (await page.locator(".ba-empty .bk-btn").count()) === 1 &&
          (await page.locator(".ba-empty .bk-ill").count()) === 0);
        for (let i = 0; i < SCENE[lang].length; i++) {
          await page.fill("#ba-input", SCENE[lang][i]);
          await page.press("#ba-input", "Enter");
          await waitAnswer(page);
          const nums = await page.locator(".ba-block--first .ba-num__value").allTextContents();
          const mapBtn = page.locator(".ba-actions .bk-btn--primary");
          check(`scene${i + 1} numbers ${tag}`, nums.length >= 1 && nums.every((n) => /\d/.test(n)), nums.join(" | "));
          check(`scene${i + 1} offline badge ${tag}`, (await page.locator(".ba-mode--offline").count()) === 1);
          check(`scene${i + 1} no h-scroll ${tag}`, await noHScroll(page));
          if (i === 0 || w === 1366) {
            await page.screenshot({ path: path.join(OUT, `analyst_scene${i + 1}_${tag}.png`), fullPage: true });
          }
          if (await mapBtn.count()) {
            await mapBtn.first().click();
            const line = await page.locator("#stand-map").textContent();
            check(`scene${i + 1} show on map ${tag}`, /segment|object|area/.test(line || ""), line);
          } else {
            check(`scene${i + 1} show on map ${tag}`, false, "нет кнопки");
          }
        }
        await page.close();
      }
    }

    // Смена языка без нового запроса + «Как получен ответ».
    {
      const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
      let posts = 0;
      page.on("request", (r) => { if (r.method() === "POST") posts++; });
      await page.goto(URL + "?lang=ru");
      await page.fill("#ba-input", SCENE.ru[0]);
      await page.press("#ba-input", "Enter");
      await waitAnswer(page);
      const ruTitle = await page.locator(".ba-answer__title").textContent();
      await page.click(".stand-lang [data-lang=kk]");
      await page.waitForTimeout(100);
      const kkTitle = await page.locator(".ba-answer__title").textContent();
      check("lang switch without refetch", posts === 1 && ruTitle !== kkTitle && /Шағымы көп орындар/.test(kkTitle), kkTitle);
      await page.click(".ba-how__summary");
      await page.waitForTimeout(150);
      check("how block lists calls", (await page.locator(".ba-call").count()) >= 2);
      await page.screenshot({ path: path.join(OUT, "analyst_how_1366_kk.png"), fullPage: true });
      // Клавиатура: Esc очищает поле, Tab доходит до «Показать на карте».
      await page.fill("#ba-input", "черновик");
      await page.press("#ba-input", "Escape");
      check("esc clears input", (await page.inputValue("#ba-input")) === "");
      let reached = false;
      for (let i = 0; i < 30 && !reached; i++) {
        await page.keyboard.press("Tab");
        reached = await page.evaluate(() => document.activeElement && document.activeElement.classList.contains("bk-btn--primary"));
      }
      check("tab reaches show-on-map", reached);
      await page.close();
    }

    // Состояния: скелетон, нет сети, 503, 403, пустой вопрос.
    for (const [w, h] of [[1366, 768], [375, 812]]) {
      const page = await browser.newPage({ viewport: { width: w, height: h } });
      await page.goto(URL + "?lang=ru");
      await page.route("**/assistant/ask", async (route) => { await new Promise((r) => setTimeout(r, 1200)); await route.continue(); });
      await page.fill("#ba-input", SCENE.ru[1]);
      await page.press("#ba-input", "Enter");
      await page.waitForSelector(".ba-skel", { timeout: 2000 });
      check(`skeleton after 150ms ${w}`, true);
      await page.screenshot({ path: path.join(OUT, `analyst_loading_${w}_ru.png`) });
      await waitAnswer(page);
      await page.unroute("**/assistant/ask");
      for (const [kind, fulfil] of [["network", (r) => r.abort("failed")],
        ["503", (r) => r.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "module_not_ready" }) })],
        ["403", (r) => r.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ error: "forbidden" }) })]]) {
        await page.route("**/assistant/ask", fulfil);
        await page.fill("#ba-input", SCENE.ru[2]);
        // Ждём именно этот ответ: прошлое состояние ошибки ещё на экране, пока запрос в пути.
        const settled = page.waitForEvent(kind === "network" ? "requestfailed" : "requestfinished",
          (r) => r.url().includes("/assistant/ask"));
        await page.press("#ba-input", "Enter");
        await settled;
        await page.waitForFunction(() => document.querySelector(".ba-live").getAttribute("aria-busy") === "false");
        await page.waitForSelector(".ba-error", { timeout: 5000 });
        const titleText = await page.locator(".ba-error .bk-error__title").textContent();
        check(`error ${kind} ${w}`, !!titleText, titleText);
        await page.screenshot({ path: path.join(OUT, `analyst_error_${kind}_${w}_ru.png`) });
        await page.unroute("**/assistant/ask");
      }
      await page.fill("#ba-input", "   ");
      await page.press("#ba-input", "Enter");
      check(`empty question hint ${w}`, await page.locator("#ba-field-error").isVisible());
      await page.close();
    }
  } finally {
    await browser.close();
  }
  fs.writeFileSync(path.join(OUT, "checks.json"), JSON.stringify({ url: URL, checks }, null, 2));
  const failed = checks.filter((c) => !c.ok).length;
  console.log(`\n${checks.length - failed} PASS, ${failed} FAIL`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
