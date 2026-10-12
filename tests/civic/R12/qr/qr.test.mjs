// R12 · волна 2 п. 6 · QR-паспорт объекта и лист печати — браузерные проверки на стенде (настоящий engine/civic_geo,
// жалобы — СИНТЕТИКА heat_fixture.json, генератор QR — тестовая заглушка, пока нет LOCAL-11).
//   node --test --test-concurrency=1 tests/civic/R12/qr/qr.test.mjs
//   R12_SHOTS=research/round-14-results/R12/screenshots/wave2 node --test ... — скриншоты 375/1366 ru/kk
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { execSync, spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../../../..");
function loadPlaywright() {
  try { return createRequire(import.meta.url)("playwright"); } catch (e) { /* fall through */ }
  try { return createRequire(path.join(execSync("npm root -g", { encoding: "utf8" }).trim(), "x.js"))("playwright"); } catch (e) { return null; }
}
const pw = loadPlaywright();
const SKIP = pw ? false : "playwright is not installed (NOT_RUN)";
const SHOTS = process.env.R12_SHOTS ? path.resolve(ROOT, process.env.R12_SHOTS) : null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const STOP = "osm-node-10272524280";        // остановка «Исатай батыр» (OSM); 3 синтетические жалобы
const SIGNAL = "osm-node-10185771782";      // светофор на перекрёстке пр. Богенбай Батыра и ул. Щорса; «исправлено»
const QUIET = "osm-node-1466676039";        // перекрёсток без жалоб

let srv, base, browser;
before(async () => {
  if (!pw) return;
  srv = spawn("python3", ["-B", path.join(HERE, "qr_stand.py")], { cwd: ROOT, stdio: ["ignore", "pipe", "inherit"] });
  base = await new Promise((ok, fail) => {
    const tm = setTimeout(() => fail(new Error("stand did not start")), 60000);
    srv.stdout.on("data", (d) => { const m = /READY (\d+)/.exec(String(d)); if (m) { clearTimeout(tm); ok("http://127.0.0.1:" + m[1]); } });
  });
  browser = await pw.chromium.launch();
});
after(async () => { if (browser) await browser.close(); if (srv) srv.kill(); });

const set = (q) => fetch(base + "/api/test/set?" + q).then((r) => r.json());
async function open(query, o = {}) {
  const ctx = await browser.newContext({ viewport: o.viewport || { width: 1366, height: 768 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
  if (o.lang) await page.addInitScript((l) => localStorage.setItem("birge.lang", l), o.lang);
  await page.goto(base + (o.path || "/stand/stand.html") + query);
  return { ctx, page, errors };
}
const ready = (page) => page.waitForFunction(() => /ready|error/.test(document.querySelector(".bq-report")?.dataset.state || ""), null, { timeout: 20000 });
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
async function shot(page, name) { if (SHOTS) await page.screenshot({ path: path.join(SHOTS, name + ".png") }); }

test("QR: stop with open complaints — what, number, how many, status, one main button «Я тоже» and «Сообщить о другом»", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open("?report=" + STOP);
  await ready(page);
  const card = await page.locator(".bq-report").innerText();
  assert.match(card, /Остановка/);
  assert.match(card, /Исатай батыр/);
  assert.match(card, /Объект № 10\s272\s524\s280/);
  assert.match(card, /Сообщили 3 человека/);
  assert.match(card, /В работе|Новое/);
  assert.match(card, /Пример/, "демо-данные помечены");
  assert.equal(await page.locator(".bk-btn--primary").count(), 1, "одна главная кнопка");
  assert.match(await page.locator(".bk-btn--primary").innerText(), /Я тоже/);
  assert.equal(await page.locator('[data-act="report-other"]').count(), 1);
  assert.equal(await page.locator("details.bq-more").getAttribute("open"), null, "подробности свёрнуты");
  assert.doesNotMatch(card, /qr\.|osm-node|ребр|граф/i, "ни ключей, ни технических слов");
  await shot(page, "qr-passport-stop-1366-ru");
  // «Я тоже» → POST с id устройства, спасибо, событие для тепловой карты, кнопка меняется
  await page.click('[data-act="metoo"]');
  await page.waitForSelector(".bq-notice--ok");
  const calls = (await fetch(base + "/api/test/calls").then((r) => r.json())).calls;
  assert.equal(calls.at(-1).complaint_id, "c-demo-qr-1");
  assert.match(calls.at(-1).device_id, /^[A-Za-z0-9_-]{16,80}$/);
  assert.deepEqual((await page.evaluate(() => window.__events.at(-1))).type, "metoo");
  await page.waitForFunction(() => /Сообщили 4 человека/.test(document.querySelector(".bq-report").innerText));
  assert.match(await page.locator(".bk-btn--primary").innerText(), /Сообщить о другом/);
  assert.match(await page.locator(".bq-report").innerText(), /Вы отметили «Я тоже»/);
  // «Сообщить о другом» отдаёт оболочке цель, точку и форму (мастер R09 откроется с этим местом)
  await page.click('[data-act="report"]');
  const rep = await page.evaluate(() => window.__reports.at(-1));
  assert.equal(rep.target.id, STOP);
  assert.equal(rep.target.object_kind, "bus_stop");
  assert.equal(rep.geometry.type, "Point");
  // «Подробнее» (POLISH_WAVE_2 п. 6: «история, текущие обращения») — грузится только при раскрытии
  assert.equal(await page.locator(".bq-cases").count(), 0, "до раскрытия обращения не грузятся");
  await page.click("details.bq-more > summary");
  await page.waitForSelector(".bq-cases li");
  const more = await page.locator("details.bq-more").innerText();
  assert.match(more, /Обращения здесь[\s\S]*Остановки и транспорт[^\n]*В работе[\s\S]*Освещение[^\n]*Новое/);
  assert.match(more, /Ответ службы до 15/);
  assert.match(more, /История[\s\S]*Новое/);
  assert.equal(await page.locator(".bq-history li").count(), 4, "4 события двух обращений, новые сверху");
  assert.doesNotMatch(more, /c-demo|osm-node/);
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("QR: object without complaints — no empty block (IA_WAVE2 §0 п. 6), main button «Сообщить о проблеме здесь»; details open the map", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await open("?report=" + QUIET);
  await ready(page);
  const card = await page.locator(".bq-report").innerText();
  assert.match(card, /Перекрёсток пр\. Богенбай Батыра и ул\. Щорса/);
  assert.doesNotMatch(card, /Сообщил|Статус/, "жалоб нет — блока с числом и статусом нет");
  assert.match(await page.locator(".bk-btn--primary").innerText(), /Сообщить о проблеме здесь/);
  await page.click('[data-act="report"]');
  assert.equal((await page.evaluate(() => window.__reports.at(-1))).target.object_kind, "intersection");
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("QR: fixed object — status «Исправлено», no «Я тоже», main button reports a new problem; history and topics folded", { skip: SKIP }, async () => {
  const { ctx, page } = await open("?report=" + SIGNAL);
  await ready(page);
  const card = await page.locator(".bq-report").innerText();
  assert.match(card, /Светофор на перекрёстке/);
  assert.match(card, /Исправлено/);
  assert.equal(await page.locator('[data-act="metoo"]').count(), 0);
  assert.match(await page.locator(".bk-btn--primary").innerText(), /Сообщить о проблеме здесь/);
  await page.click("details.bq-more > summary");
  assert.match(await page.locator("details.bq-more").innerText(), /Жалобы по дням[\s\S]*О чём сообщают[\s\S]*Дороги/);
  await page.click('[data-act="map"]');
  assert.equal((await page.evaluate(() => window.__maps.at(-1))).id, SIGNAL);
  await ctx.close();
});

test("QR: unknown, malformed and failing links say what happened and what to do", { skip: SKIP }, async () => {
  let r = await open("?report=osm-node-1");
  await ready(r.page);
  assert.match(await r.page.locator(".bq-report").innerText(), /Объект не найден[\s\S]*ссылка устарела/);
  assert.equal(await r.page.locator('[data-act="map"]').count(), 1);
  await r.ctx.close();
  r = await open("?report=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E");
  await ready(r.page);
  assert.equal(await r.page.evaluate(() => window.__parsed), null);
  assert.match(await r.page.locator(".bq-report").innerText(), /Объект не найден/);
  assert.equal(await r.page.locator(".bq-report img").count(), 0);
  await r.ctx.close();
  await set("fail_target=1");
  r = await open("?report=" + STOP);
  await ready(r.page);
  assert.match(await r.page.locator(".bq-report").innerText(), /Не удалось загрузить карточку/);
  await r.page.click('[data-act="retry"]');
  await r.page.waitForFunction(() => /Исатай батыр/.test(document.querySelector(".bq-report").innerText));
  await r.ctx.close();
  // тепловая карта недоступна — карточка объекта всё равно есть, без выдуманных чисел
  await set("fail_heat=1");
  r = await open("?report=" + STOP);
  await ready(r.page);
  const txt = await r.page.locator(".bq-report").innerText();
  assert.match(txt, /Исатай батыр/);
  assert.doesNotMatch(txt, /Сообщили/);
  assert.match(await r.page.locator(".bk-btn--primary").innerText(), /Сообщить о проблеме здесь/);
  await r.ctx.close();
});

test("QR: Kazakh and phone 375 px — no keys, main button visible without scrolling, no horizontal scroll", { skip: SKIP }, async () => {
  for (const [lang, vp] of [["kk", { width: 375, height: 740 }], ["ru", { width: 375, height: 740 }], ["kk", { width: 1366, height: 768 }]]) {
    const { ctx, page, errors } = await open("?report=" + STOP, { lang, viewport: vp });
    await ready(page);
    const txt = await page.locator(".bq-report").innerText();
    if (lang === "kk") {
      assert.match(txt, /Аялдама/);
      assert.match(txt, /Нысан № 10\s272\s524\s280/);
      assert.match(txt, /Мен де/);
      assert.match(txt, /\d адам хабарлады/);  // первый тест мог уже нажать «Я тоже»
    }
    assert.doesNotMatch(txt, /qr\.[a-z]/);
    assert.ok((await overflow(page)) <= 0, lang + " " + vp.width);
    const btn = await page.locator(".bk-btn--primary").boundingBox();
    assert.ok(btn.height >= 48 && btn.y + btn.height <= vp.height, "главная кнопка видна без прокрутки: " + JSON.stringify(btn));
    assert.equal(await page.evaluate(() => document.documentElement.lang), lang, "ссылка не переключила язык");
    await shot(page, `qr-passport-stop-${vp.width}-${lang}`);
    assert.deepEqual(errors, []);
    await ctx.close();
  }
});

test("print sheet: QR + domain + bilingual address + number; bad and unknown ids reported; no print without a real generator", { skip: SKIP }, async () => {
  await set("fake_qr=1");
  const ids = [STOP, SIGNAL, "osm-node-1", "<x>"].join(",");
  let r = await open("?ids=" + encodeURIComponent(ids) + "&base=" + encodeURIComponent("https://birge.example.kz"), { path: "/civic/qr/print.html" });
  await r.page.waitForSelector(".bqp-sign");
  const signs = await r.page.locator(".bqp-sign").count();
  assert.equal(signs, 2);
  const first = await r.page.locator(".bqp-sign").first().innerText();
  assert.match(first, /birge\.example\.kz/);
  assert.match(first, /«Исатай батыр» аялдамасы/);
  assert.match(first, /Остановка «Исатай батыр»/);
  assert.match(first, /Нысан № 10\s272\s524\s280 · Объект № 10\s272\s524\s280/);
  assert.match(first, /https:\/\/birge\.example\.kz\/\?report=osm-node-10272524280/);
  assert.equal(await r.page.locator(".bqp-sign path").count(), 2, "QR нарисован (тестовая заглушка генератора)");
  const msgs = await r.page.locator(".bqp-status").innerText();
  assert.match(msgs, /«<x>» — не номер объекта/);
  assert.match(msgs, /Объект osm-node-1 не найден/);
  // R15-S25: адрес сайта из ссылки не совпадает с этим сервером — предупреждение до печати
  assert.match(msgs, /birge\.example\.kz — это не адрес этого сервера/);
  assert.equal(await r.page.locator('[data-act="print"]').isVisible(), true);
  assert.equal(await r.page.locator(".bqp-buttons .bk-btn--primary").count(), 1, "одна главная кнопка: «Распечатать QR»");
  assert.match(await r.page.locator(".bqp-buttons .bk-btn--primary").innerText(), /Распечатать QR/);
  assert.ok((await overflow(r.page)) <= 0);
  await shot(r.page, "qr-print-sheet-1366-ru");
  await r.page.emulateMedia({ media: "print" });
  assert.equal(await r.page.locator(".bqp-form").isVisible(), false, "в печать идут только таблички");
  // IA_WAVE2 §6.2: A4, одна табличка на лист, QR ≥ 6 см, название ≥ 28 pt, без чисел жалоб и статусов
  const pm = await r.page.evaluate(() => ({ qr: document.querySelector(".bqp-qr").getBoundingClientRect().width,
    title: parseFloat(getComputedStyle(document.querySelector(".bqp-sign__title")).fontSize),
    brk: getComputedStyle(document.querySelector(".bqp-sign")).breakAfter }));
  assert.ok(pm.qr >= (6 / 2.54) * 96, "QR " + pm.qr + " px");
  assert.ok(pm.title >= (28 * 96) / 72 - 0.5, "название " + pm.title + " px");
  assert.equal(pm.brk, "page");
  assert.doesNotMatch(first, /Сообщил|Статус|адам хабарлады|Мәртебе/);
  await r.ctx.close();
  // без генератора QR — честное предупреждение, печать не предлагается
  await set("fake_qr=0");
  r = await open("?ids=" + STOP, { path: "/civic/qr/print.html" });
  await r.page.waitForSelector(".bqp-sign");
  assert.match(await r.page.locator(".bqp-status").innerText(), /Генератор QR ещё не подключён/);
  assert.doesNotMatch(await r.page.locator(".bqp-status").innerText(), /не адрес этого сервера/, "адрес этого сервера — без предупреждения");
  assert.equal(await r.page.locator('[data-act="print"]').isVisible(), false);
  assert.match(await r.page.locator(".bqp-sign").innerText(), /\/\?report=osm-node-10272524280/);
  // адрес сайта с путём или чужой схемой — отказ
  await r.page.fill("#bqp-base", "javascript:alert(1)");
  await r.page.click('[data-act="show"]');
  assert.match(await r.page.locator(".bqp-status").innerText(), /Адрес сайта должен начинаться/);
  assert.equal(await r.page.locator(".bqp-sign").count(), 0);
  await r.ctx.close();
});
