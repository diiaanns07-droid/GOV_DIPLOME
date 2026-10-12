// R12 · дизайн-марафон: кабинет сотрудника (редактор) — вход, список, новый объект, ошибки, опубликованная запись
//   (верх, «Как увидят жители», история) — 1366/375 × ru/kk. Метрики (размеры, веса, зоны < 44, фоны) — по последнему экрану.
//   NODE_PATH=$(npm root -g) node editor_shots.mjs <base> <out> <файл-пароля> [логин]
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
const require = createRequire(path.join(process.env.NODE_PATH, "x.js"));
const pw = require("playwright");
const [BASE, OUT, PWF, USER] = process.argv.slice(2);
const PASS = fs.readFileSync(PWF, "utf8").trim();
fs.mkdirSync(OUT, { recursive: true });
const b = await pw.chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });
const rep = [];
// R12_SIZES=1366x768,1024x768,375x812 — другие размеры экрана (проектор 1024); по умолчанию 1366 и 375.
const SIZES = (process.env.R12_SIZES || "1366x768,375x812").split(",").map((x) => x.split("x").map(Number));
for (const [w, h] of SIZES) for (const lang of ["ru", "kk"]) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, hasTouch: w < 500 });
  const p = await ctx.newPage();
  const errs = []; p.on("pageerror", (e) => errs.push(e.message));
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.addInitScript((l) => { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", "akimat"); }, lang);
  await p.goto(BASE + "/");
  await p.waitForSelector(".birge-avatar", { timeout: 30000 });
  await p.waitForTimeout(800);
  await p.click(".birge-avatar");
  await p.click('#birge-account [data-action="staff"]');
  await p.waitForSelector("#civic-editor:not([hidden]) .civic-r04-login", { timeout: 15000 });
  await p.waitForTimeout(400);
  const shot = async (name) => { await p.waitForTimeout(350); await p.screenshot({ path: path.join(OUT, `${name}-${w}-${lang}.png`) }); };
  const scrollBody = async (where) => p.evaluate((wh) => { const bd = document.querySelector("#civic-editor .civic-r04-body"); if (bd) bd.scrollTop = wh === "end" ? bd.scrollHeight : wh === "mid" ? bd.scrollHeight / 2 - bd.clientHeight / 2 : 0; }, where);
  await shot("login");
  await p.fill("#civic-editor .civic-r04-login input[name=username]", USER || "r12check");
  await p.fill("#civic-editor .civic-r04-login input[name=password]", PASS);
  await p.press("#civic-editor .civic-r04-login input[name=password]", "Enter");
  await p.waitForSelector("#civic-editor .civic-r04-list", { timeout: 15000 });
  await shot("list");
  // новый объект
  await p.click("#civic-editor .civic-r04-toolbar .civic-r04-btn.primary, #civic-editor .civic-r04-toolbar button >> nth=0");
  await p.waitForSelector("#civic-editor .civic-r04-form", { timeout: 10000 });
  await scrollBody("top"); await shot("new-top");
  await scrollBody("mid"); await shot("new-mid");
  await scrollBody("end"); await shot("new-end");
  // проверка: «Сохранить» с пустой формой
  await p.click('#civic-editor [data-fk="save"]').catch(() => null);
  await p.waitForTimeout(500);
  await shot("new-errors");
  // опубликованная запись: верх (карточка, сообщение), предпросмотр «Как увидят жители», низ (история)
  await p.click('#civic-editor [data-fk="back"]').catch(() => null);
  await p.waitForSelector("#civic-editor .civic-r04-list", { timeout: 10000 }).catch(() => null);
  await p.click("#civic-editor .civic-r04-tabs button >> nth=1").catch(() => null);
  await p.waitForTimeout(300);
  await p.click("#civic-editor .civic-r04-list .civic-r04-row >> nth=0").catch(() => null);
  await p.waitForSelector("#civic-editor .civic-r04-form", { timeout: 10000 }).catch(() => null);
  await scrollBody("top"); await shot("edit-top");
  await p.click('#civic-editor [data-fk="preview"]').catch(() => null);
  await p.waitForTimeout(300);
  await p.evaluate(() => { const e = document.querySelector("#civic-editor .civic-r04-preview"); if (e) e.scrollIntoView({ block: "start" }); });
  await shot("edit-preview");
  await scrollBody("end"); await shot("edit-end");
  const m = await p.evaluate(() => {
    const r = document.querySelector("#civic-editor .civic-r04"); if (!r) return null;
    const vis = [...r.querySelectorAll("*")].filter((e) => e.getClientRects().length);
    const leaf = vis.filter((e) => e.childElementCount === 0 && e.textContent.trim());
    const sizes = {}; leaf.forEach((e) => { const s = getComputedStyle(e).fontSize; sizes[s] = (sizes[s] || 0) + 1; });
    const weights = [...new Set(leaf.map((e) => getComputedStyle(e).fontWeight))];
    const small = [...r.querySelectorAll("button, input, select, textarea, summary, label.civic-r04-check, label.civic-r04-radio")].filter((e) => e.getClientRects().length)
      .map((e) => { const q = e.getBoundingClientRect(); return { t: (e.textContent || e.getAttribute("aria-label") || e.name || "").trim().slice(0, 20), h: Math.round(q.height) }; }).filter((x) => x.h < 44);
    const bg = [...new Set(vis.map((e) => getComputedStyle(e).backgroundColor).filter((c) => c !== "rgba(0, 0, 0, 0)"))];
    return { sizes, weights, small: small.slice(0, 12), smallCount: small.length, bg };
  });
  rep.push({ w, lang, ...m, errors: errs });
  await ctx.close();
}
await b.close();
fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(rep, null, 1));
for (const r of rep) console.log(r.w, r.lang, "sizes", JSON.stringify(r.sizes), "weights", r.weights.join(","), "small<44:", r.smallCount, JSON.stringify(r.small.slice(0, 5)), "bg", r.bg.length, "err", r.errors.length);
