/*
 * R11 · «книга экранов» (DESIGN_BOOK.md): экраны сотрудника после входа — «Обращения» (список и первое обращение),
 * «Проекты и идеи», «Вопрос акиму» (проверка), 1366 и 375, ru и kk.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/book_staff.cjs http://127.0.0.1:<порт>/ <папка> <файл-пароля>
 * Вход — как человек: аватар → «Для сотрудников» → имя operator и пароль из файла (пароль не печатается).
 */
"use strict";
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const [BASE, OUT, PWFILE] = process.argv.slice(2);

(async () => {
  const pw = fs.readFileSync(PWFILE, "utf8").trim();
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  for (const [w, h] of [[1366, 768], [375, 812]]) for (const lang of ["ru", "kk"]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", "akimat"); } catch (e) {} }, lang);
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.goto(BASE, { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 }).catch(() => {});
    await p.addStyleTag({ content: "#map-status { visibility: hidden !important; }" });
    await p.waitForTimeout(800);
    const tag = `${w}-${lang}`;
    try {
      await p.click(".birge-avatar"); await p.waitForTimeout(400);
      await p.screenshot({ path: path.join(OUT, `avatar-menu-akimat-${tag}.png`) });
      await p.click(`text=${lang === "kk" ? "Қызметкерлерге" : "Для сотрудников"}`); await p.waitForTimeout(1200);
      await p.screenshot({ path: path.join(OUT, `staff-login-${tag}.png`) });
      await p.fill("input[name=username]", "operator"); await p.fill("input[name=password]", pw);
      await p.click("button[type=submit]"); await p.waitForTimeout(2500);
      await p.keyboard.press("Escape"); await p.waitForTimeout(500);
    } catch (e) { console.log(tag, "вход:", e.message.split("\n")[0]); }
    for (const sec of ["inbox", "projects", "questions"]) {
      await p.evaluate((s) => window.BirgeShell.setSection(s), sec); await p.waitForTimeout(3000);
      await p.screenshot({ path: path.join(OUT, `${sec}-staff-${tag}.png`) });
      if (sec === "inbox") {
        const row = await p.$("#birge-screen .bc-inbox__item, #birge-screen .bc-inbox [role=button], #birge-screen .bc-inbox li button");
        if (row) { await row.click().catch(() => {}); await p.waitForTimeout(1500); await p.screenshot({ path: path.join(OUT, `inbox-item-staff-${tag}.png`) }); }
      }
    }
    console.log(tag, "готово");
    await ctx.close();
  }
  await browser.close();
})();
