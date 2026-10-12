// R12 · FINAL-3 · UX_REVIEW R11 п. 11: кабинет сотрудника в панели оболочки — один заголовок, без цветной полосы.
//   NODE_PATH=$(npm root -g) node tests/civic/R12/editor/app_cabinet_title.mjs http://127.0.0.1:<порт> <папка> <файл-пароля>
// Нужен сотрудник «r12check» во временной базе (ui.civic_store create-editor r12check --password-stdin < файл-пароля).
// Вход — через меню аватара (чистый дизайн). Печатает JSON: видимые заголовки панели до и после входа, ошибки страницы.
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
const require = createRequire(path.join(process.env.NODE_PATH, "x.js"));
const pw = require("playwright");
const [BASE, OUT, PWF] = process.argv.slice(2);
const PASS = fs.readFileSync(PWF, "utf8").trim();
const b = await pw.chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });
const res = [];
for (const [w, h, lang] of [[375, 812, "ru"], [1366, 768, "kk"]]) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, hasTouch: w < 500 });
  const p = await ctx.newPage();
  const errs = []; p.on("pageerror", (e) => errs.push(e.message));
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.addInitScript((l) => localStorage.setItem("birge.lang", l), lang);
  await p.goto(BASE + "/");
  await p.waitForSelector(".birge-avatar", { timeout: 30000 });
  await p.click(".birge-avatar");
  await p.click('#birge-account [data-action="staff"]');
  await p.waitForSelector("#civic-editor:not([hidden]) .civic-r04-login", { timeout: 15000 });
  const vis = async () => p.evaluate(() => [...document.querySelectorAll("#civic-editor h2, #civic-editor h3")].filter((e) => e.getClientRects().length && getComputedStyle(e).visibility !== "hidden").map((e) => e.tagName + ":" + e.textContent.trim()));
  const band = async () => p.evaluate(() => { const hd = document.querySelector("#civic-editor .civic-r04-head"); return hd ? { shown: !!hd.getClientRects().length, bg: getComputedStyle(hd).backgroundImage } : null; });
  const before = { headings: await vis(), head: await band() };
  await p.screenshot({ path: path.join(OUT, `cabinet-login-${w}-${lang}.png`) });
  await p.fill("#civic-editor .civic-r04-login input[autocomplete=username], #civic-editor .civic-r04-login input[type=text]", "r12check");
  await p.fill("#civic-editor .civic-r04-login input[type=password]", PASS);
  await p.press("#civic-editor .civic-r04-login input[type=password]", "Enter");
  await p.waitForSelector("#civic-editor .civic-r04-who", { timeout: 15000 });
  await p.waitForTimeout(500);
  const after = { headings: await vis(), head: await band(), who: await p.locator("#civic-editor .civic-r04-who").innerText() };
  await p.screenshot({ path: path.join(OUT, `cabinet-signed-in-${w}-${lang}.png`) });
  res.push({ w, lang, before, after, errors: errs });
  await ctx.close();
}
await b.close();
console.log(JSON.stringify(res, null, 1));
