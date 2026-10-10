// R02 · раунд 14 · инструмент разметки web/labeling/ в настоящем Chromium (file://, без сервера и сети).
//   node --test tests/civic/R02/round14/labeling_browser.test.mjs
//   R02_SHOTS=research/round-14-results/R02/screens node --test tests/civic/R02/round14/labeling_browser.test.mjs
// Фикстуры — синтетика (выдуманные тексты, телефон и ИИН ненастоящие).
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../../../..");
const PAGE = pathToFileURL(path.join(ROOT, "web/labeling/index.html")).href;
const FIX = path.join(HERE, "fixtures");
function loadPlaywright() {
  try { return createRequire(import.meta.url)("playwright"); } catch (e) { /* дальше глобальный */ }
  try { return createRequire(path.join(execSync("npm root -g", { encoding: "utf8" }).trim(), "x.js"))("playwright"); } catch (e) { return null; }
}
const pw = loadPlaywright();
const SKIP = pw ? false : "playwright не установлен (NOT_RUN)";
const SHOTS = process.env.R02_SHOTS ? path.resolve(ROOT, process.env.R02_SHOTS) : null;
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

let browser;
before(async () => {
  if (!pw) return;
  const opts = { headless: true };
  try { browser = await pw.chromium.launch(opts); }
  catch (e) { browser = await pw.chromium.launch({ ...opts, executablePath: "/opt/pw-browsers/chromium" }); }
});
after(async () => { if (browser) await browser.close(); });

async function newPage(viewport = { width: 1366, height: 768 }) {
  const ctx = await browser.newContext({ viewport, acceptDownloads: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  // Любой запрос не к file:// — нарушение офлайн-требования.
  const net = [];
  page.on("request", (r) => { if (!r.url().startsWith("file:") && !r.url().startsWith("blob:") && !r.url().startsWith("data:")) net.push(r.url()); });
  await page.goto(PAGE);
  return { ctx, page, errors, net };
}

async function openFixture(page, name) {
  await page.setInputFiles("#fileInput", path.join(FIX, name));
  await page.waitForSelector("#workScreen:not([hidden])");
}

async function shot(page, name) {
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, name), fullPage: false });
}

async function noHorizontalScroll(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
}

test("первый разметчик: только клавиатура, отмена, пропуск, экспорт", { skip: SKIP }, async () => {
  const { ctx, page, errors, net } = await newPage();
  await shot(page, "01_start_ru_1366.png");
  await openFixture(page, "texts_sample.jsonl");
  // 13 строк: одна нечитаемая, один повтор id → 12 текстов
  assert.equal(await page.textContent("#progressText"), "0 / 12");
  assert.match(await page.textContent("#itemText"), /Яма на дороге/);
  // Метка из чужого файла (s-003 label=transport) НЕ должна считаться готовой: разметка вслепую.
  await shot(page, "02_work_ru_1366.png");
  await page.keyboard.press("Digit1");               // roads
  assert.equal(await page.textContent("#progressText"), "1 / 12");
  assert.match(await page.textContent("#itemText"), /көктайғақ/);
  await page.keyboard.press("Digit2");               // snow_ice
  await page.keyboard.press("KeyF");                 // сомневаюсь — до выбора
  assert.equal(await page.isVisible("#unsureChip"), true);
  await page.keyboard.press("Digit4");               // s-003 transport + unsure
  await page.keyboard.press("Space");                // s-004 пропуск
  assert.match(await page.textContent("#itemText"), /балалар алаңы/);
  await page.keyboard.press("Backspace");            // отмена пропуска → снова s-004
  assert.match(await page.textContent("#itemText"), /фонари во дворе/);
  await page.keyboard.press("Digit5");               // lighting
  await page.keyboard.press("Digit6");               // s-005 yards
  await page.keyboard.press("Digit7");               // s-006 waste
  await page.keyboard.press("Digit8");               // s-007 utilities
  await page.keyboard.press("Digit9");               // s-008 smell_air
  await page.keyboard.press("Digit0");               // s-009 noise_safety
  await page.keyboard.press("Minus");                // s-010 parking
  await page.keyboard.press("Equal");                // s-011 other
  await page.keyboard.press("KeyN");                 // s-012 не жалоба
  assert.equal(await page.isVisible("#finishCard"), true);
  assert.equal(await page.textContent("#progressText"), "12 / 12");
  await shot(page, "03_finish_ru_1366.png");

  const [dl] = await Promise.all([page.waitForEvent("download"), page.keyboard.press("Control+KeyS")]);
  const text = readFileSync(await dl.path(), "utf8");
  const rows = text.trim().split("\n").map((l) => JSON.parse(l));
  assert.equal(rows.length, 12);
  const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
  assert.equal(byId["s-001"].label, "roads");
  assert.equal(byId["s-002"].label, "snow_ice");
  assert.equal(byId["s-003"].label, "transport");
  assert.equal(byId["s-003"].unsure, true);
  assert.equal(byId["s-004"].label, "lighting");
  assert.equal(byId["s-010"].label, "parking");
  assert.equal(byId["s-011"].label, "other");
  assert.equal(byId["s-012"].label, "not_complaint");
  assert.ok(rows.every((r) => r.schema === "birge-labels-v1" && r.role === "first" && r.annotator === "A"));
  assert.match(dl.suggestedFilename(), /^birge-labels_A_first_texts_sample_\d{8}-\d{4}\.jsonl$/);
  assert.deepEqual(errors, []);
  assert.deepEqual(net, []);
  await ctx.close();
});

test("казахская раскладка: event.key = «ә», event.code = Digit2 → вторая категория", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await newPage();
  await openFixture(page, "texts_sample.jsonl");
  // Эмулируем нажатие в казахской раскладке: символ другой, физическая клавиша та же.
  await page.evaluate(() => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "ә", code: "Digit2", bubbles: true, cancelable: true }));
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "т", code: "KeyN", bubbles: true, cancelable: true }));
  });
  const st = await page.evaluate(() => window.BirgeLabeling.state());
  assert.equal(st.labels["s-001"].label, "snow_ice");
  assert.equal(st.labels["s-002"].label, "not_complaint");
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("автосохранение: перезагрузка страницы → «Продолжить» с той же позиции", { skip: SKIP }, async () => {
  const { ctx, page } = await newPage();
  await openFixture(page, "texts_sample.jsonl");
  await page.keyboard.press("Digit1");
  await page.keyboard.press("Digit3");
  await page.reload();
  await page.waitForSelector("#resumeBox:not([hidden])");
  await page.click("#resumeList .resume-btn");
  await page.waitForSelector("#workScreen:not([hidden])");
  assert.equal(await page.textContent("#progressText"), "2 / 12");
  assert.match(await page.textContent("#itemText"), /разбито стекло/);
  // Повторное открытие того же файла тоже продолжает, а не начинает заново.
  await page.click("#closeBtn");
  await openFixture(page, "texts_sample.jsonl");
  assert.equal(await page.textContent("#progressText"), "2 / 12");
  await ctx.close();
});

test("второй разметчик: детерминированный поднабор, метки первого не видны, отдельное хранение", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await newPage();
  // Сначала первый разметчик размечает всё и скачивает файл с метками.
  await openFixture(page, "texts_sample.jsonl");
  for (let i = 0; i < 12; i++) await page.keyboard.press("Digit1");
  const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#finishExport")]);
  const exported = await dl.path();
  await page.click("#closeBtn");
  // Второй разметчик открывает ЭКСПОРТ первого (там есть метки) — они не должны просочиться.
  await page.check('input[name="role"][value="second"]');
  assert.equal(await page.inputValue("#annotatorInput"), "B");
  await page.fill("#subsetSize", "5");
  await page.fill("#subsetSeed", "test-seed");
  await page.setInputFiles("#fileInput", exported);
  await page.waitForSelector("#workScreen:not([hidden])");
  assert.equal(await page.textContent("#progressText"), "0 / 5");
  assert.equal(await page.isVisible("#labelChip"), false);
  const chosen = await page.evaluate(() => document.querySelectorAll(".cat.chosen").length);
  assert.equal(chosen, 0);
  const st = await page.evaluate(() => window.BirgeLabeling.state());
  assert.equal(Object.keys(st.labels).length, 0);
  assert.ok(st.items.every((it) => !("prior" in it) && !("label" in it)));
  const ids1 = st.items.map((i) => i.id);
  await shot(page, "04_second_ru_1366.png");
  for (let i = 0; i < 5; i++) await page.keyboard.press("Digit2");
  const [dl2] = await Promise.all([page.waitForEvent("download"), page.keyboard.press("Control+KeyS")]);
  const rows = readFileSync(await dl2.path(), "utf8").trim().split("\n").map((l) => JSON.parse(l));
  assert.equal(rows.length, 5);
  assert.ok(rows.every((r) => r.role === "second" && r.annotator === "B" && r.label === "snow_ice" && r.subset.seed === "test-seed"));
  // Сквозная проверка: оба экспорта читаются ml/labeling/agreement.py (5 общих текстов, все — несогласие).
  const py = process.env.PYTHON || "python3";
  const report = execSync(`${py} -m ml.labeling.agreement "${exported}" "${await dl2.path()}" --bootstrap 50`, { cwd: ROOT, encoding: "utf8" });
  assert.match(report, /общих текстов: 5/);
  assert.match(report, /roads ↔ snow_ice ×5/);
  // Тот же файл + тот же ключ → тот же поднабор (сравниваем с исходным JSONL — id одинаковые).
  await page.click("#closeBtn");
  await page.check('input[name="role"][value="second"]');
  await page.fill("#subsetSize", "5");
  await page.fill("#subsetSeed", "test-seed");
  await openFixture(page, "texts_sample.jsonl");
  const ids2 = await page.evaluate(() => window.BirgeLabeling.state().items.map((i) => i.id));
  assert.deepEqual(ids2, ids1);
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("CSV из Google-формы открывается напрямую; казахский интерфейс; 375 px без горизонтальной прокрутки", { skip: SKIP }, async () => {
  const { ctx, page, errors } = await newPage({ width: 375, height: 812 });
  await page.click('.lang[data-lang="kk"]');
  assert.equal(await page.textContent("#openBtn"), "Файлды ашу");
  await shot(page, "05_start_kk_375.png");
  assert.equal(await noHorizontalScroll(page), true);
  await openFixture(page, "form_sample.csv");
  // 8 строк: одна пустая → 7 текстов (обезличивание — дело import_form.py, здесь только показ)
  assert.equal(await page.textContent("#progressText"), "0 / 7");
  assert.equal(await page.textContent("#notComplaintBtn span:not(.sr)"), "Шағым емес");
  assert.equal(await noHorizontalScroll(page), true);
  await shot(page, "06_work_kk_375.png");
  // Кнопки категорий ≥ 48 px по высоте и ширине на телефоне
  const sizes = await page.$$eval(".cat, .btn.act", (els) => els.map((e) => { const r = e.getBoundingClientRect(); return [r.width, r.height]; }));
  assert.ok(sizes.every(([w, h]) => w >= 48 && h >= 48), JSON.stringify(sizes));
  await page.click('.cat[data-cat="roads"]');
  assert.equal(await page.textContent("#progressText"), "1 / 7");
  // Справка открывается и закрывается с клавиатуры
  await page.keyboard.press("Shift+Slash");
  assert.equal(await page.isVisible("#helpOverlay"), true);
  await shot(page, "07_help_kk_375.png");
  await page.keyboard.press("Escape");
  assert.equal(await page.isVisible("#helpOverlay"), false);
  // Язык интерфейса запоминается
  await page.reload();
  assert.equal(await page.textContent("#openBtn"), "Файлды ашу");
  assert.deepEqual(errors, []);
  await ctx.close();
});

test("1366×768: текст, 12 кнопок и действия помещаются без прокрутки", { skip: SKIP }, async () => {
  const { ctx, page } = await newPage({ width: 1366, height: 768 });
  await openFixture(page, "texts_sample.jsonl");
  const bottom = await page.evaluate(() => document.querySelector(".actions").getBoundingClientRect().bottom);
  assert.ok(bottom <= 768, `нижний край действий ${bottom}`);
  assert.equal(await page.$$eval(".cat", (els) => els.length), 12);
  assert.equal(await noHorizontalScroll(page), true);
  await ctx.close();
});

test("пустой файл → понятная ошибка, а не белый экран", { skip: SKIP }, async () => {
  const { ctx, page } = await newPage();
  await page.setInputFiles("#fileInput", { name: "empty.csv", mimeType: "text/csv", buffer: Buffer.from("text\n\n") });
  await page.waitForSelector("#startError:not([hidden])");
  assert.match(await page.textContent("#startError"), /ни одного текста/);
  assert.equal(await page.isVisible("#startScreen"), true);
  await ctx.close();
});
