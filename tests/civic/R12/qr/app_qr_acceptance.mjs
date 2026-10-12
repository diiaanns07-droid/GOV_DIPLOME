// R12 · волна 2 п. 6 · приёмка QR-паспорта в НАСТОЯЩЕМ приложении (сборка R01 + R12 + patch R01/R09 из INTEGRATION).
//   NODE_PATH=$(npm root -g) node tests/civic/R12/qr/app_qr_acceptance.mjs http://127.0.0.1:8611 <out_dir>
// Объект — остановка «Хан Шатыр» (osm-node-4109037549): у неё демо-жалобы R09/R07 при CIVIC_DEMO=1.
// Итог — <out_dir>/qr_acceptance.json (PASS/FAIL/NOT_RUN) и скриншоты 1366/375, ru/kk.
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const BASE = process.argv[2] || "http://127.0.0.1:8611";
const OUT = process.argv[3] || "qr-acceptance";
fs.mkdirSync(OUT, { recursive: true });
const require = createRequire(import.meta.url);
let pw;
try { pw = require("playwright"); } catch (e) { pw = createRequire(path.join(execSync("npm root -g", { encoding: "utf8" }).trim(), "x.js"))("playwright"); }
const STOP = "osm-node-4109037549";
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, status: ok ? "PASS" : "FAIL", detail }); console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : " — " + JSON.stringify(detail))); };

const browser = await pw.chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader"] });
async function page(viewport, lang, url) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, hasTouch: viewport.width < 500 });
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
  await p.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); } catch (e) { /* */ } }, lang);
  await p.goto(BASE + url);
  return { ctx, p, errors };
}
// Место объекта на карте видно: не под панелью/шторкой и не за краем (IA_WAVE2 §6.1 «карта на объекте»).
async function pointVisible(p, lngLat) {
  await p.waitForFunction(() => typeof map !== "undefined" && map && !map.isMoving(), null, { timeout: 10000 }).catch(() => null);
  await p.waitForTimeout(700);
  return p.evaluate((ll) => {
    const q = map.project(ll), c = map.getCanvas().getBoundingClientRect();
    const x = c.left + q.x, y = c.top + q.y;
    const under = [document.getElementById("civic-panel"), document.querySelector(".topbar")].some((el) => {
      if (!el || !el.getClientRects().length) return false;
      const r = el.getBoundingClientRect();
      return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
    });
    return { x: Math.round(x), y: Math.round(y), inside: x > c.left && x < c.right && y > c.top && y < c.bottom, under };
  }, lngLat);
}
const STOP_LL = [71.4065528, 51.1311545];  // точка остановки в data/civic/astana/geo/objects.json
const reportState = (p) => p.waitForFunction(() => /ready|error/.test(document.querySelector("#birge-report-root .bq-report")?.dataset.state || ""), null, { timeout: 30000 });

try {
  // 1. Ноутбук, ru: скан → паспорт → «Я тоже» → «Сообщить о другом» → мастер R09 с этим местом
  {
    const { ctx, p, errors } = await page({ width: 1366, height: 768 }, "ru", "/?report=" + STOP);
    await reportState(p);
    const card = await p.locator("#birge-report-root").innerText();
    check("ссылка ?report открывает паспорт остановки в панели", /Хан Шатыр/.test(card) && /Объект № 4\s109\s037\s549/.test(card), card.slice(0, 200));
    check("в паспорте видно, сколько людей сообщили, и статус", /Сообщил/.test(card) && /Статус/.test(card), card.slice(0, 300));
    check("одна главная кнопка в паспорте", (await p.locator("#birge-report-root .bk-btn--primary").count()) === 1, null);
    check("«Карта жалоб» спрятана, пока открыт паспорт (одна карточка)", !(await p.locator("#birge-heat-root").isVisible()), null);
    check("ссылка открывается в виде «Житель» (IA_WAVE2 §6.1), выбор не запоминается",
      (await p.evaluate(() => document.body.dataset.birgeMode)) === "resident" && (await p.evaluate(() => localStorage.getItem("birge.mode"))) === null,
      await p.evaluate(() => [document.body.dataset.birgeMode, localStorage.getItem("birge.mode")]));
    const vis = await pointVisible(p, STOP_LL);
    check("ноутбук: остановка на карте видна, не под панелью", vis.inside && !vis.under, vis);
    await p.screenshot({ path: path.join(OUT, "app-qr-1366-ru.png") });
    // «Подробнее»: текущие обращения и история (POLISH_WAVE_2 п. 6) — из публичного вида настоящего R09
    await p.click("#birge-report-root details.bq-more > summary");
    const casesOk = await p.waitForSelector("#birge-report-root .bq-cases li", { timeout: 10000 }).then(() => true, () => false);
    const more = await p.locator("#birge-report-root details.bq-more").innerText();
    check("«Подробнее»: «Обращения здесь» и «История» из R09, без текстов жителей и id",
      casesOk && /Обращения здесь/.test(more) && /История/.test(more) && /Освещение/.test(more) && !/c-demo|osm-node/.test(more), more.slice(0, 400));
    await p.screenshot({ path: path.join(OUT, "app-qr-details-1366-ru.png") });
    await p.click("#birge-report-root details.bq-more > summary");
    if (await p.locator('#birge-report-root [data-act="metoo"]').count()) {
      await p.click('#birge-report-root [data-act="metoo"]');
      const ok = await p.waitForSelector("#birge-report-root .bq-notice--ok", { timeout: 10000 }).then(() => true, () => false);
      check("«Я тоже» из паспорта принято сервером R09", ok, await p.locator("#birge-report-root").innerText().catch(() => ""));
    } else checks.push({ name: "«Я тоже» из паспорта", status: "NOT_RUN", detail: "на устройстве уже отмечено" });
    await p.click('#birge-report-root [data-act="report"], #birge-report-root [data-act="report-other"]');
    await p.waitForTimeout(600);
    const wizard = await p.locator("#birge-complaint-root").innerText();
    check("«Сообщить» открывает мастер R09 сразу с этим местом (без выбора на карте)", /Хан Шатыр/.test(wizard), wizard.slice(0, 300));
    await p.screenshot({ path: path.join(OUT, "app-qr-report-wizard-1366-ru.png") });
    await p.keyboard.press("Escape");
    await p.click("#birge-report-root .bq-report__close");
    await p.waitForTimeout(300);
    check("закрыли паспорт — обычная карта, адрес без ?report", (await p.locator("#birge-heat-root").isVisible()) && !/report=/.test(p.url()), p.url());
    check("нет ошибок страницы (ноутбук)", errors.length === 0, errors.slice(0, 3));
    await ctx.close();
  }
  // 2. Телефон, kk: язык не меняется ссылкой; главная кнопка видна
  {
    const { ctx, p, errors } = await page({ width: 375, height: 740 }, "kk", "/?report=" + STOP);
    await reportState(p);
    const card = await p.locator("#birge-report-root").innerText();
    check("телефон, kk: паспорт по-казахски", /аялдамасы/.test(card) && /Нысан № 4\s109\s037\s549/.test(card), card.slice(0, 200));
    check("ссылка не переключила язык", (await p.evaluate(() => document.documentElement.lang)) === "kk", null);
    const btn = await p.locator("#birge-report-root .bk-btn--primary").boundingBox();
    check("главная кнопка видна без прокрутки страницы", !!btn && btn.y + btn.height <= 740 && btn.height >= 44, btn);
    check("телефон: шторка наполовину (IA_WAVE2 §6.1)", (await p.locator("#civic-panel").getAttribute("data-sheet")) === "half",
      await p.locator("#civic-panel").getAttribute("data-sheet"));
    const vis = await pointVisible(p, STOP_LL);
    check("телефон: остановка на карте видна над шторкой", vis.inside && !vis.under, vis);
    const over = await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check("нет горизонтальной прокрутки на 375 px", over <= 0, over);
    await p.screenshot({ path: path.join(OUT, "app-qr-375-kk.png") });
    check("нет ошибок страницы (телефон)", errors.length === 0, errors.slice(0, 3));
    await ctx.close();
  }
  // 3. Подменённая ссылка — понятная ошибка, разметка не исполняется
  {
    const { ctx, p, errors } = await page({ width: 1366, height: 768 }, "ru", "/?report=%3Cimg%20src%3Dx%20onerror%3Dwindow.__x%3D1%3E");
    await reportState(p);
    const card = await p.locator("#birge-report-root").innerText();
    check("подменённая ссылка: «Объект не найден» + «На карту», ничего не исполняется",
      /Объект не найден/.test(card) && /На карту/.test(card) && !(await p.evaluate(() => window.__x)), card.slice(0, 200));
    await p.click('#birge-report-root [data-act="map"]');
    await p.waitForTimeout(300);
    check("«На карту» — обычная карта жалоб, не пустой экран", (await p.locator("#birge-heat-root").isVisible()) && !/report=/.test(p.url()), p.url());
    check("нет ошибок страницы (подмена)", errors.length === 0, errors.slice(0, 3));
    await ctx.close();
  }
  // 4. Карта по умолчанию (без ?report) — как была: паспорт скрыт, новых слоёв на карте нет
  {
    const { ctx, p, errors } = await page({ width: 1366, height: 768 }, "ru", "/");
    // карта web/map.js — глобальная переменная `map` (не window.map: так называется и элемент #map)
    await p.waitForFunction(() => typeof map !== "undefined" && map && map.getStyle && (map.getStyle()?.layers || []).length > 0, null, { timeout: 30000 }).catch(() => null);
    await p.waitForTimeout(1500);
    const st = await p.evaluate(() => ({ hidden: document.getElementById("birge-report-root")?.hidden,
      layers: typeof map !== "undefined" && map && map.getStyle ? (map.getStyle()?.layers || []).filter((l) => /report|qr/i.test(l.id)).length : -1 }));
    check("без ссылки паспорт скрыт и слоёв QR на карте нет", st.hidden === true && st.layers === 0, st);
    check("нет ошибок страницы (карта по умолчанию)", errors.length === 0, errors.slice(0, 3));
    await ctx.close();
  }
  // 4б. Акимат (ноутбук по умолчанию): в карточке места R07 — ссылка «Распечатать QR» (IA_WAVE2 §6.2, patch R07); лист печати под CSP R01
  {
    const { ctx, p, errors } = await page({ width: 1366, height: 768 }, "ru", "/");
    const csp = [];
    // Нарушения CSP. «Refused … MIME type» от /vendor/qrcode/qrcode.js — это 404, пока нет LOCAL-11 (лист честно предупреждает).
    p.on("console", (m) => { if (/Content Security Policy/.test(m.text())) csp.push(m.text()); });
    await p.waitForFunction(() => document.querySelector("#birge-heat-root .r07-item, #birge-heat-root .r07-list"), null, { timeout: 30000 }).catch(() => null);
    await p.goto(BASE + "/#target=object:" + STOP);
    const link = await p.waitForSelector("#birge-heat-root .r07-qr a", { timeout: 20000 }).then((h) => h.getAttribute("href"), () => null);
    check("акимат: в карточке места есть «Распечатать QR» на лист этого объекта", link === "/civic/qr/print.html?ids=" + STOP, link);
    const prim = await p.locator("#birge-heat-root .r07-card .r07-btn--primary").count();
    check("в карточке места по-прежнему одна главная кнопка", prim <= 1, prim);
    await p.screenshot({ path: path.join(OUT, "app-r07-card-qr-link-1366-ru.png") });
    await p.goto(BASE + "/civic/qr/print.html?ids=" + STOP);
    await p.waitForSelector(".bqp-sign", { timeout: 20000 }).catch(() => null);
    const sheet = await p.locator("#bqp-root").innerText().catch(() => "");
    check("лист QR открывается в приложении: табличка остановки", /Хан Шатыр/.test(await p.locator(".bqp-sheet").innerText().catch(() => "")), sheet.slice(0, 300));
    check("лист QR без нарушений CSP R01 (встроенных скриптов нет)", csp.length === 0, csp);
    await p.screenshot({ path: path.join(OUT, "app-qr-print-1366-ru.png") });
    check("нет ошибок страницы (акимат, лист QR)", errors.length === 0, errors.slice(0, 3));
    await ctx.close();
  }
  // 5. POLISH_WAVE п. 1 в мастере R09: нажали у перекрёстка — «Это здесь?» предлагает светофор этого перекрёстка
  {
    const { ctx, p, errors } = await page({ width: 1366, height: 768 }, "ru", "/");
    await p.waitForFunction(() => typeof map !== "undefined" && map && map.getStyle && document.querySelector(".bc-fab"), null, { timeout: 30000 });
    await p.click(".bc-fab").catch(async () => { await p.click("text=Житель"); await p.click(".bc-fab"); });
    await p.waitForTimeout(400);
    await p.evaluate(() => map.jumpTo({ center: [71.40335, 51.17485], zoom: 17 }));
    await p.waitForTimeout(800);
    const pt = await p.evaluate(() => { const q = map.project([71.40335, 51.17485]), r = map.getCanvas().getBoundingClientRect(); return { x: r.left + q.x, y: r.top + q.y }; });
    await p.mouse.click(pt.x, pt.y);
    const ok = await p.waitForFunction(() => /Светофор на перекрёстке пр\. Богенбай Батыра и ул\. Щорса/.test(document.getElementById("birge-complaint-root")?.innerText || ""), null, { timeout: 15000 }).then(() => true, () => false);
    check("мастер R09: у перекрёстка предлагается светофор этого перекрёстка", ok, (await p.locator("#birge-complaint-root").innerText()).slice(0, 400));
    await p.screenshot({ path: path.join(OUT, "app-wizard-traffic-signal-1366-ru.png") });
    check("нет ошибок страницы (мастер)", errors.length === 0, errors.slice(0, 3));
    await ctx.close();
  }
} catch (e) {
  checks.push({ name: "приёмка дошла до конца", status: "FAIL", detail: String(e && e.message || e) });
  console.log("FAIL", e);
}
await browser.close();
const sum = { pass: checks.filter((c) => c.status === "PASS").length, fail: checks.filter((c) => c.status === "FAIL").length, not_run: checks.filter((c) => c.status === "NOT_RUN").length };
fs.writeFileSync(path.join(OUT, "qr_acceptance.json"), JSON.stringify({ base: BASE, summary: sum, checks }, null, 1));
console.log(JSON.stringify(sum));
