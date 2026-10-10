/*
 * R11 · кабинет сотрудника в ҚАЗ (R10 B-021): «Қызметкерлерге» → форма входа → кабинет; в консоль — русские строки,
 * найденные в форме и в кабинете (ожидается пусто), кадры 1366/375 в <папка>.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/staff_kk_check.cjs http://127.0.0.1:<порт>/ <папка> <файл-пароля>
 */
const fs = require("fs");
const { chromium } = require("playwright");
(async () => {
  const pw = fs.readFileSync(process.argv[4], "utf8").trim();
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  for (const w of [1366, 375]) {
    const ctx = await b.newContext({ viewport: w === 1366 ? { width: 1366, height: 768 } : { width: 375, height: 812 } });
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.addInitScript(() => { localStorage.setItem("birge.lang", "kk"); localStorage.setItem("birge.mode", "akimat"); });
    await p.goto(process.argv[2]);
    await p.waitForFunction(() => window.CivicShell && window.CivicShell.heat && window.CivicShell.heat.state && window.CivicShell.heat.state().status === "ready", null, { timeout: 45000 }); await p.waitForTimeout(1200);
    const staffBtn = await p.$("text=Қызметкерлерге");
    if (!staffBtn) { console.log(w, "нет кнопки Қызметкерлерге"); await ctx.close(); continue; }
    await staffBtn.click(); await p.waitForTimeout(1500);
    await p.screenshot({ path: `${process.argv[3]}/staff-login-${w}-kk.png` });
    const ru1 = (await p.evaluate(() => document.body.innerText)).match(/Вход для сотрудника|Имя пользователя|Пароль\b|Войти\b|Учётную запись|Кабинет редактора/g) || [];
    await p.fill("input[name=username]", "operator"); await p.fill("input[name=password]", pw);
    await p.click("button[type=submit]"); await p.waitForTimeout(2500);
    await p.screenshot({ path: `${process.argv[3]}/staff-cabinet-${w}-kk.png` });
    const ru2 = (await p.evaluate(() => document.body.innerText)).match(/Кабинет редактора|Вы вошли|Новый объект|Обновить список|Черновики|Опубликованные|Архив\b|Выйти\b|роль по данным|staff\/meta/g) || [];
    console.log(w, "ru в форме:", JSON.stringify(ru1), "ru в кабинете:", JSON.stringify([...new Set(ru2)]));
    await ctx.close();
  }
  await b.close();
})();
