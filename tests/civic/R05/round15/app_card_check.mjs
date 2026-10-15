// R05 · раунд 15 · карточка проекта в собранном приложении: шторка «Было / станет» по превью, «День / Ночь» у
// освещения, «белый макет» (поправка П1), каталог «Что построить?». 1366 / 375 × ru / kk, клавиатура, палец, отказ
// картинки «было», «уменьшить движение».
//
// Нужен стенд (COMMON «КАК ПОДНЯТЬ СТЕНД») с патчем R05 для R01: patches/R01_web_server_assets.patch (картинки
// data/previews/*-before@2x.png, lighting-*@2x.png в CIVIC_ASSETS).
// Запуск:  NODE_PATH=$(npm root -g) node tests/civic/R05/round15/app_card_check.mjs [--url http://127.0.0.1:8655] [--shots папка] [--stand подпись] [--out имя.json]
// Отчёт — research/round-15-results/R05/runs/app_card_check.json.
import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const arg = (n, d) => { const i = process.argv.indexOf(n); return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
const URL0 = arg("--url", "http://127.0.0.1:8655");
const STAND = arg("--stand", "");  // подпись стенда в отчёте: сборка R01 + код R05 (если стенд не из этой ветки)
const OUT = arg("--out", "app_card_check.json");
const SHOTS = arg("--shots", path.join(ROOT, "research/round-15-results/R05/screens"));
const { chromium } = require("playwright");

const results = [];
const record = (id, status, detail) => { results.push({ id, status, detail }); console.log(`${status}  ${id}${detail ? "  — " + (typeof detail === "string" ? detail : JSON.stringify(detail)) : ""}`); };
async function check(id, fn) {
  try { const r = await fn(); if (r && r.status) record(id, r.status, r.detail); else record(id, r === false ? "FAIL" : "PASS", r && r !== true ? r : undefined); }
  catch (e) { record(id, "FAIL", String(e.message || e).split("\n")[0]); }
}
const assert = (c, m) => { if (!c) throw new Error(m); };
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const pageErrors = [];
async function openCard(viewport, lang, kind, extra = {}, route) {
  const ctx = await browser.newContext(Object.assign({ viewport, deviceScaleFactor: 1 }, extra));
  const page = await ctx.newPage();
  if (route) await page.route(route, (r) => r.fulfill({ status: 404, body: "" }));
  page.on("pageerror", (e) => pageErrors.push(`${viewport.width} ${lang} ${kind}: ${e.message}`));
  await page.goto(URL0 + "/?lang=" + lang);
  await page.waitForFunction(() => window.CivicShell?.build3d && window.BirgeShell, null, { timeout: 60000 });
  if (lang === "kk") await page.evaluate(() => window.BirgeI18n?.setLang?.("kk"));
  await page.evaluate(() => window.BirgeShell.setLayer("projects"));
  await page.waitForFunction(() => { const s = window.CivicShell.build3d.getState(); return s.phase === "ready" && s.count > 0; }, null, { timeout: 60000 });
  const id = await page.evaluate((k) => { const s = window.CivicShell.build3d.getState(); const p = s.proposals.find((x) => x.kind === k); window.CivicShell.build3d.select(p.id); return p.id; }, kind);
  await page.waitForSelector('.b3d-dock[data-state="card"]', { timeout: 20000 });
  await page.waitForTimeout(900);
  return { page, id };
}
const slider = (page) => page.evaluate(() => {
  const f = document.querySelector(".b3d-ba"), h = f && f.querySelector(".b3d-ba__handle");
  if (!f) return null;
  const r = f.getBoundingClientRect(), hr = h.getBoundingClientRect();
  const imgs = [...f.querySelectorAll("img")].map((i) => i.getAttribute("src").replace(/^.*previews\//, ""));
  return { w: Math.round(r.width), h: Math.round(r.height), handle: [Math.round(hr.width), Math.round(hr.height)], now: +h.getAttribute("aria-valuenow"),
    role: h.getAttribute("role"), label: h.getAttribute("aria-label"), text: h.getAttribute("aria-valuetext"),
    tags: [...f.querySelectorAll(".b3d-ba__tag")].map((t) => [t.textContent, getComputedStyle(t).opacity]), imgs, night: f.classList.contains("b3d-ba--night"),
    before_bg: getComputedStyle(f.querySelector(".b3d-ba__before")).backgroundColor };
});
// Кадр — после того как оболочка R01 сама погасит плашку «Карта улиц не загрузилась» (только облако, гаснет через 6 с):
// иначе она закрывает низ карточки и каталога. Ничего не прячем — ждём настоящий вид.
async function shot(page, name) {
  await page.waitForFunction(() => { const s = document.getElementById("map-status");
    return !s || s.classList.contains("hidden") || s.dataset.faded === "1"; }, null, { timeout: 9000 }).catch(() => {});
  await page.waitForTimeout(450);
  await mkdir(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + ".png") });
}

await check("card_slider_1366_ru", async () => {
  const { page } = await openCard({ width: 1366, height: 768 }, "ru", "playground");
  const s = await slider(page);
  assert(s, "нет шторки в карточке");
  assert(Math.abs(s.w / s.h - 1.5) < 0.02, "картинка не 3 : 2: " + s.w + "×" + s.h);
  assert(s.handle[0] >= 44 && s.handle[1] >= 44, "ручка меньше 44 px: " + s.handle);
  assert(s.role === "slider" && s.now === 50 && /было/i.test(s.text), "aria: " + JSON.stringify(s));
  assert(s.tags[0][0] === "Было" && s.tags[1][0] === "Станет", "подписи: " + JSON.stringify(s.tags));
  assert(s.imgs.includes("playground@2x.png") && s.imgs.includes("playground-before@2x.png"), "картинки: " + s.imgs);
  assert(s.before_bg !== "rgba(0, 0, 0, 0)", "слой «было» прозрачный — сквозь него видно «станет»");
  await shot(page, "card_ba_1366_ru");
  // Клавиатура: ← ← (шаг 5), End, Home; стрелки не двигают карту.
  const cam0 = await page.evaluate(() => map.getCenter().toArray().join());
  await page.focus(".b3d-ba__handle");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  const k1 = (await slider(page)).now;
  await page.keyboard.press("End");
  await page.waitForTimeout(250); // подпись гаснет за 150 мс (переход)
  const k2 = await slider(page);
  await page.keyboard.press("Home");
  const k3 = (await slider(page)).now;
  await page.keyboard.press("Shift+ArrowRight");
  const k4 = (await slider(page)).now;
  const cam1 = await page.evaluate(() => map.getCenter().toArray().join());
  assert(k1 === 40 && k2.now === 100 && k3 === 0 && k4 === 20, `клавиши: ${k1} ${k2.now} ${k3} ${k4}`);
  assert(k2.tags[1][1] === "0", "при «только было» подпись «Станет» не спрятана: " + JSON.stringify(k2.tags));
  assert(cam0 === cam1, "стрелки сдвинули карту");
  // Палец/мышь: нажать в 80 % ширины.
  const box = await page.locator(".b3d-ba").boundingBox();
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.8, box.y + box.height * 0.5, { steps: 6 });
  await page.mouse.up();
  const d = (await slider(page)).now;
  assert(Math.abs(d - 80) <= 2, "перетаскивание: " + d);
  await page.context().close();
  return { keys: [k1, k2.now, k3, k4], drag: d };
});

for (const [w, h, lang, kind] of [[1366, 768, "kk", "square"], [375, 812, "ru", "stop"], [375, 812, "kk", "sports"]]) {
  await check(`card_slider_${w}_${lang}_${kind}`, async () => {
    const { page } = await openCard({ width: w, height: h }, lang, kind);
    if (w < 761) {
      // Телефон: картинки нет (кнопки карты и сам проект видны — правило раунда 14), шторку открывает кнопка.
      const closed = await page.evaluate(() => {
        const im = document.querySelector(".b3d-pd__im--r06"), btn = document.querySelector(".b3d-ba-toggle"), t3 = document.querySelector("#toggle-3d");
        const r = t3 && t3.getBoundingClientRect(), hit = r && document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        return { picture: im ? getComputedStyle(im).display : null, btn: btn ? [btn.textContent, btn.getAttribute("aria-expanded"), Math.round(btn.getBoundingClientRect().height)] : null, map3dFree: !t3 || (!!hit && t3.contains(hit)) };
      });
      assert(closed.picture === "none" && closed.btn && closed.btn[1] === "false" && closed.btn[2] >= 44, "телефон, по умолчанию: " + JSON.stringify(closed));
      assert(closed.map3dFree, "карточка закрывает кнопку «3D» карты");
      await page.click(".b3d-ba-toggle");
      await page.waitForTimeout(300);
    }
    const s = await slider(page);
    assert(s && Math.abs(s.w / s.h - 1.5) < 0.02, "шторка: " + JSON.stringify(s));
    if (w < 761) assert(s.h === 120, "телефон: высота картинки " + s.h);
    if (lang === "kk") assert(s.tags[0][0] === "Бұрын" && s.tags[1][0] === "Кейін", "kk подписи: " + JSON.stringify(s.tags));
    await shot(page, `card_ba_${w}_${lang}_${kind}`);
    await page.context().close();
    return { size: [s.w, s.h], tags: s.tags.map((t) => t[0]) };
  });
}

for (const [w, h, lang] of [[1366, 768, "ru"], [375, 812, "kk"]]) {
  await check(`lighting_day_night_${w}_${lang}`, async () => {
    const { page } = await openCard({ width: w, height: h }, lang, "lighting");
    if (w < 761) { await page.click(".b3d-ba-toggle"); await page.waitForTimeout(300); }
    const s0 = await slider(page);
    assert(s0.imgs.includes("lighting-after@2x.png") && s0.imgs.includes("lighting-before@2x.png"), "день: " + s0.imgs);
    const btns = await page.evaluate(() => [...document.querySelectorAll(".b3d-time button")].map((b) => [b.dataset.time, b.textContent, b.getAttribute("aria-pressed"), Math.round(b.getBoundingClientRect().height)]));
    assert(btns.length === 2 && btns[0][2] === "true", "переключатель: " + JSON.stringify(btns));
    await shot(page, `card_day_${w}_${lang}`);
    await page.click('.b3d-time button[data-time="night"]');
    await page.waitForTimeout(500);
    const s1 = await slider(page);
    const bg = await page.evaluate(() => getComputedStyle(document.querySelector(".b3d-pd__im")).backgroundColor);
    assert(s1.night && s1.imgs.includes("lighting-night-after@2x.png") && s1.imgs.includes("lighting-night-before@2x.png"), "ночь: " + JSON.stringify(s1));
    assert(bg === "rgb(37, 40, 42)", "поле ночью не тёмно-серое: " + bg);
    const pressed = await page.evaluate(() => [...document.querySelectorAll(".b3d-time button")].map((b) => b.getAttribute("aria-pressed")));
    assert(pressed[0] === "false" && pressed[1] === "true", "aria-pressed: " + pressed);
    // «×» карточки поверх тёмной ночной картинки — в светлом круге (на телефоне без круга тёмный «×» не был виден).
    const x = await page.evaluate(() => { const b = document.querySelector('.b3d-dock [data-action="close-card"]'); if (!b) return null;
      const m = getComputedStyle(b).backgroundColor.match(/rgba?\(([^)]+)\)/), v = m ? m[1].split(/[ ,/]+/).filter(Boolean).map(Number) : [];
      return { rgb: v.slice(0, 3), alpha: v.length > 3 ? v[3] : (v.length ? 1 : 0) }; });
    assert(x && x.alpha >= 0.5 && Math.min(...x.rgb) >= 200, "«×» над ночной картинкой без светлого круга: " + JSON.stringify(x));
    await shot(page, `card_night_${w}_${lang}`);
    await page.context().close();
    return { buttons: btns.map((b) => b[1]), night: s1.imgs };
  });
}

await check("host_api_previewOf_before_after_and_beforeAfter_element", async () => {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const page = await ctx.newPage();
  await page.goto(URL0 + "/?lang=ru");
  await page.waitForFunction(() => window.CivicShell?.build3d?.previewOf, null, { timeout: 60000 });
  const r = await page.evaluate(() => {
    const b = window.CivicShell.build3d;
    const pv = b.previewOf("square");
    const el = b.beforeAfter && b.beforeAfter("playground");
    if (el) document.body.appendChild(el);
    return { before: pv.before && pv.before.src, after: pv.after && pv.after.src, el: el ? el.className : null, handle: !!(el && el.querySelector('[role="slider"]')), unknown: b.beforeAfter ? b.beforeAfter("tower") : "нет API" };
  });
  await ctx.close();
  assert(/square-before@2x\.png$/.test(r.before) && /square@2x\.png$/.test(r.after), "previewOf: " + JSON.stringify(r));
  assert(r.el === "b3d-ba" && r.handle && r.unknown === null, "beforeAfter(kind): " + JSON.stringify(r));
  return r;
});

await check("before_image_missing_falls_back_to_preview", async () => {
  const { page } = await openCard({ width: 1366, height: 768 }, "ru", "playground", {}, "**/previews/*-before@2x.png");
  await page.waitForTimeout(800);
  const r = await page.evaluate(() => ({ slider: !!document.querySelector(".b3d-ba"), img: !!document.querySelector(".b3d-pd__im img") }));
  await page.context().close();
  assert(!r.slider && r.img, "без картинки «было» должна остаться обычная превью: " + JSON.stringify(r));
  return r;
});

await check("reduced_motion_no_transitions", async () => {
  const { page } = await openCard({ width: 1366, height: 768 }, "ru", "square", { reducedMotion: "reduce" });
  const t = await page.evaluate(() => getComputedStyle(document.querySelector(".b3d-ba__tag")).transitionDuration);
  await page.context().close();
  assert(t === "0s", "переход подписи при «уменьшить движение»: " + t);
  return t;
});

await check("catalog_white_model_previews", async () => {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  const page = await ctx.newPage();
  await page.goto(URL0 + "/?lang=ru");
  await page.waitForFunction(() => window.CivicShell?.build3d && window.BirgeShell, null, { timeout: 60000 });
  await page.evaluate(() => window.BirgeShell.setLayer("projects"));
  await page.waitForFunction(() => window.CivicShell.build3d.getState().phase === "ready", null, { timeout: 60000 });
  const btn = page.locator(".birge-b3d-toggle");
  if (!(await btn.count())) { await ctx.close(); return { status: "NOT_RUN", detail: "кнопки «Что построить?» нет в этом виде (житель)" }; }
  await btn.click();
  await page.waitForSelector('.b3d-dock[data-state="catalog"] .b3d-card img', { timeout: 15000 });
  await page.waitForTimeout(700);
  const tints = await page.evaluate(() => [...document.querySelectorAll('.b3d-dock[data-state="catalog"] .b3d-card img')].map((i) => i.naturalWidth));
  await shot(page, "catalog_white_model_1366_ru");
  await ctx.close();
  assert(tints.length === 5 && tints.every((w) => w > 0), "превью каталога: " + tints);
  return { previews: tints.length };
});

// 1024 (оболочка R01 даёт каталогу ~588 px): пять плиток в строку без прокрутки — пятая («Освещение улицы») не обрезана.
for (const lang of ["ru", "kk"]) {
  await check(`catalog_fits_row_1024_${lang}`, async () => {
    const ctx = await browser.newContext({ viewport: { width: 1024, height: 768 } });
    await ctx.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); } catch (e) {} }, lang);
    const page = await ctx.newPage();
    await page.goto(URL0 + "/?lang=" + lang);
    await page.waitForFunction(() => window.CivicShell?.build3d && window.BirgeShell, null, { timeout: 60000 });
    if (lang === "kk") await page.evaluate(() => window.BirgeI18n?.setLang?.("kk"));
    await page.evaluate(() => window.BirgeShell.setLayer("projects"));
    await page.waitForFunction(() => window.CivicShell.build3d.getState().phase === "ready", null, { timeout: 60000 });
    const btn = page.locator(".birge-b3d-toggle");
    if (!(await btn.count())) { await ctx.close(); return { status: "NOT_RUN", detail: "кнопки «Что построить?» нет в этом виде (житель)" }; }
    await btn.click();
    await page.waitForSelector('.b3d-dock[data-state="catalog"] .b3d-card', { timeout: 15000 });
    await page.waitForTimeout(500);
    const r = await page.evaluate(() => {
      const row = document.querySelector('.b3d-dock[data-state="catalog"] .b3d-cards'), cards = [...row.querySelectorAll(".b3d-card")];
      const a = row.getBoundingClientRect(), last = cards[cards.length - 1].getBoundingClientRect();
      return { cards: cards.length, scroll: [row.scrollWidth, row.clientWidth], last_right: Math.round(last.right), row_right: Math.round(a.right),
        labels: cards.map((c) => c.textContent.trim()) };
    });
    await ctx.close();
    assert(r.cards === 5 && r.scroll[0] <= r.scroll[1] + 1 && r.last_right <= r.row_right + 1, "каталог 1024 не помещается: " + JSON.stringify(r));
    return r;
  });
}

let sha = "?";
try { sha = execSync("git rev-parse --short HEAD", { cwd: ROOT }).toString().trim(); } catch (e) {}
const report = { at: new Date().toISOString(), url: URL0, code_head: sha, stand: STAND || undefined, env: "облако: Chromium headless + SwiftShader, упрощённый фон карты", results, pageErrors };
await mkdir(path.join(ROOT, "research/round-15-results/R05/runs"), { recursive: true });
await writeFile(path.join(ROOT, "research/round-15-results/R05/runs", OUT), JSON.stringify(report, null, 1));
const fails = results.filter((r) => r.status === "FAIL").length;
console.log(`итог: ${results.filter((r) => r.status === "PASS").length} PASS / ${fails} FAIL / ${results.filter((r) => r.status === "NOT_RUN").length} NOT_RUN; ошибки страницы: ${pageErrors.length}`);
if (pageErrors.length) console.log(pageErrors.slice(0, 5).join("\n"));
await browser.close();
process.exit(fails ? 1 : 0);
