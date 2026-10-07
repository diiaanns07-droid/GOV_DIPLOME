/* Round 13: браузерная проверка R06 на стенде с НАСТОЯЩИМ классификатором R08 (Chromium, Playwright).
 *
 *   node tests/civic/R06/browser_r13_r06.cjs [--screenshots DIR] [--classifier r08|none]
 *
 * Стенд tests/civic/R06/harness/serve_r06.py (FIXTURE-объекты и учётные записи, временная БД,
 * 127.0.0.1). С --classifier r08 стенд не стартует без ml/civic_classifier — подмены нет.
 * Проверяется: житель на экране 360 px (казахский текст) -> квитанция и ссылка -> перезагрузка ->
 * открытие ссылки «на другом устройстве» -> сотрудник видит подсказку без числа -> ответ ->
 * житель видит ответ и хронологию; конфликт двух сотрудников без потери текста; истёкшая
 * сессия; 429 с временем повтора; выход очищает черновики. Внешние сервисы не используются.
 */
"use strict";

const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

function loadPlaywright() {
  try {
    return require("playwright");
  } catch (e) {
    const globalRoot = require("child_process").execSync("npm root -g").toString().trim();
    return require(path.join(globalRoot, "playwright"));
  }
}

const ROOT = path.resolve(__dirname, "..", "..", "..");
const args = process.argv.slice(2);
const shotDir = args.includes("--screenshots") ? path.resolve(args[args.indexOf("--screenshots") + 1]) : null;
const classifier = args.includes("--classifier") ? args[args.indexOf("--classifier") + 1] : "r08";
const results = [];
const KK = "Аялдама маңында шамдар жанбайды, кешке жол қараңғы. Балалар қорқады.";

function check(name, condition, detail) {
  results.push({ name, status: condition ? "PASS" : "FAIL", detail: detail || null });
  if (!condition) console.error("FAIL:", name, detail || "");
}

function startHarness(port, dbDir, extra) {
  const proc = spawn("python3", [path.join(ROOT, "tests/civic/R06/harness/serve_r06.py"), "--port", String(port),
    "--db", path.join(dbDir, `feedback-${port}.sqlite3`), ...extra], { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"] });
  let stderr = "";
  proc.stderr.on("data", (chunk) => { stderr += chunk; });
  proc.lastError = () => stderr;
  return proc;
}

async function waitForServer(base, proc) {
  for (let i = 0; i < 100; i += 1) {
    try {
      const r = await fetch(base + "/harness/session");
      if (r.ok) return;
    } catch (e) { /* ещё стартует */ }
    if (proc.exitCode !== null) throw new Error("harness exited: " + proc.lastError());
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("harness did not start");
}

async function overflowX(page, selector) {
  return page.evaluate((sel) => {
    const node = sel ? document.querySelector(sel) : document.documentElement;
    return { scroll: node.scrollWidth, client: node.clientWidth, doc: document.documentElement.scrollWidth, win: window.innerWidth };
  }, selector);
}

async function fill(page, { text, category = "lighting", consent = true }) {
  const root = page.locator("#resident-root");
  await root.locator("select").selectOption(category);
  await root.locator("textarea").fill(text);
  await root.locator(`input[type=radio][value=${consent ? "true" : "false"}]`).check();
}

async function login(page, tab) {
  await page.click("#login-editor");
  await page.waitForFunction(() => document.getElementById("session").textContent.includes("editor"));
  if (tab) {
    await page.waitForSelector("#moderation-root .civic-r06-tab");
    await page.locator("#moderation-root .civic-r06-tab", { hasText: tab }).click();
  }
  await page.waitForSelector("#moderation-root .civic-r06-queue-item");
}

async function openFirst(page) {
  await page.locator("#moderation-root .civic-r06-queue-item").first().click();
  await page.waitForSelector("#moderation-root .civic-r06-handling");
}

(async () => {
  const dbDir = fs.mkdtempSync(path.join(os.tmpdir(), "r06-r13-browser-"));
  const port = 8900 + Math.floor(Math.random() * 100);
  const limitedPort = port + 100;
  const base = `http://127.0.0.1:${port}`;
  const limitedBase = `http://127.0.0.1:${limitedPort}`;
  const server = startHarness(port, dbDir, ["--classifier", classifier, "--per-sender-max", "20"]);
  const limited = startHarness(limitedPort, dbDir, ["--per-sender-max", "1"]);
  let browser;
  const pageErrors = [];
  try {
    await waitForServer(base, server);
    await waitForServer(limitedBase, limited);
    const { chromium } = loadPlaywright();
    browser = await chromium.launch();
    const watch = (page) => {
      page.on("pageerror", (e) => pageErrors.push(String(e)));
      page.on("dialog", (d) => { pageErrors.push("dialog: " + d.message()); d.dismiss(); });
      return page;
    };

    // 1. Житель, 360 px, казахский текст.
    const phoneContext = await browser.newContext({ viewport: { width: 360, height: 740 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
    const phone = watch(await phoneContext.newPage());
    await phone.goto(base + "/harness/");
    await phone.waitForSelector("body[data-r06-ready='1']");
    await phone.waitForSelector("#resident-root .civic-r06-form");
    let ov = await overflowX(phone, null);
    check("360px: form page has no horizontal scroll", ov.doc <= ov.win, JSON.stringify(ov));
    await fill(phone, { text: KK, category: "other" });
    await phone.locator("#resident-root button[type=submit]").click();
    await phone.waitForSelector("#resident-root .civic-r06-receipt .civic-r06-timeline li", { state: "attached" });
    const receiptId = (await phone.locator("#resident-root .civic-r06-receipt-id").innerText()).trim();
    const link = await phone.locator("#resident-root .civic-r06-receipt-link").inputValue();
    check("receipt link uses #fragment, not query", /^http:\/\/127\.0\.0\.1:\d+\/harness\/#civic-receipt=fbr_/.test(link) && !link.includes("?"), link);
    const receiptText = await phone.evaluate(() => document.querySelector("#resident-root .civic-r06-receipt").textContent);
    check("receipt shows status and timeline", receiptText.includes("Ожидает проверки модератором платформы") &&
      receiptText.includes("Новое") && receiptText.includes("Сообщение получено платформой"), receiptText);
    check("receipt does not mention model or category hint", !/R08|модел|civic-clf|подсказ/i.test(receiptText), receiptText);
    ov = await overflowX(phone, null);
    check("360px: receipt has no horizontal scroll", ov.doc <= ov.win, JSON.stringify(ov));
    if (shotDir) await phone.screenshot({ path: path.join(shotDir, "r13_receipt_360.png"), fullPage: true });
    const stored = await phone.evaluate(() => Object.keys(sessionStorage).map((k) => [k, sessionStorage.getItem(k)]));
    check("tab storage keeps receipt number, not message text", stored.every(([k, v]) => !v.includes("шамдар")) &&
      stored.some(([k, v]) => k.startsWith("civic-r06-receipts:") && v.includes(receiptId)), JSON.stringify(stored));

    // 2. Перезагрузка вкладки: житель снова видит квитанцию и статус.
    await phone.reload();
    await phone.waitForSelector("body[data-r06-ready='1']");
    await phone.waitForSelector("#resident-root .civic-r06-receipt .civic-r06-timeline li", { state: "attached" });
    check("reload shows the same receipt", (await phone.locator("#resident-root .civic-r06-receipt-id").innerText()).trim() === receiptId);

    // 3. Сотрудник (десктоп) видит подсказку без числа и с источником.
    const desk = watch(await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage());
    await desk.goto(base + "/harness/");
    await desk.waitForSelector("body[data-r06-ready='1']");
    await login(desk);
    await openFirst(desk);
    const detail = await desk.locator("#moderation-root .civic-r06-detail").innerText();
    const hint = await desk.locator("#moderation-root .civic-r06-classifier").innerText();
    check("staff sees kazakh text intact", detail.includes("қараңғы"), detail.slice(0, 200));
    if (classifier === "r08") {
      check("hint labelled as real R08 with synthetic warning", hint.includes("Модель R08") && hint.includes("синтетических") &&
        /AI-подсказка категории: «Освещение»/.test(hint), hint);
    } else {
      check("hint says model disabled", hint.includes("выключена"), hint);
    }
    check("hint shows no numeric score or percent", !/\d[.,]\d|%|вероятн[оа]ст[ьи] \d/.test(hint.replace(/civic-clf[^\s,]*/g, "")), hint);
    check("resident category kept (Другое) despite hint", detail.includes("категория жителя: Другое") && !detail.includes("→ сотрудник"), detail.slice(0, 400));
    if (shotDir) await desk.locator("#moderation-root").screenshot({ path: path.join(shotDir, "r13_staff_hint.png") });

    // 4. Конфликт: второй сотрудник открыл ту же карточку, первый сменил статус.
    const desk2 = watch(await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage());
    await desk2.goto(base + "/harness/");
    await desk2.waitForSelector("body[data-r06-ready='1']");
    await login(desk2);
    await openFirst(desk2);
    await desk.locator("#moderation-root .civic-r06-handling select").selectOption("in_review");
    await desk.locator("#moderation-root .civic-r06-handling textarea").last().fill("Первый сотрудник взял в работу");
    await desk.locator("#moderation-root .civic-r06-handling button[type=submit]").click();
    await desk.waitForFunction(() => /В работе/.test((document.querySelector("#moderation-root .civic-r06-handling-line")?.textContent || "")));
    const reply2 = "Ответ второго сотрудника: сообщение передано модератору района на платформе.";
    await desk2.locator("#moderation-root .civic-r06-handling select").selectOption("answered");
    await desk2.locator("#moderation-root .civic-r06-handling textarea").first().fill(reply2);
    await desk2.locator("#moderation-root .civic-r06-handling textarea").last().fill("Второй сотрудник отвечает");
    await desk2.locator("#moderation-root .civic-r06-handling button[type=submit]").click();
    await desk2.waitForSelector("#moderation-root .civic-r06-conflict");
    const conflict = await desk2.locator("#moderation-root .civic-r06-conflict").innerText();
    check("conflict banner names current state and author of change", conflict.includes("На рассмотрении") && conflict.includes("fixture-editor") &&
      conflict.includes("не сохранено"), conflict);
    check("typed reply carried into refreshed card", (await desk2.locator("#moderation-root .civic-r06-handling textarea").first().inputValue()) === reply2);
    const afterConflict = await desk2.evaluate(async () => {
      const r = await fetch("/api/civic/v1/staff/feedback?status=all&moderation=all", { credentials: "same-origin" });
      return (await r.json()).data.items[0];
    });
    check("server state not overwritten by stale form", afterConflict.handling_status === "in_review" && afterConflict.public_reply === null, JSON.stringify(afterConflict).slice(0, 200));
    if (shotDir) await desk2.locator("#moderation-root .civic-r06-detail").screenshot({ path: path.join(shotDir, "r13_conflict.png") });
    // Осознанная повторная отправка из обновлённой карточки проходит.
    await desk2.locator("#moderation-root .civic-r06-handling select").selectOption("answered");
    await desk2.locator("#moderation-root .civic-r06-handling button[type=submit]").click();
    await desk2.waitForFunction(() => /Дан ответ/.test((document.querySelector("#moderation-root .civic-r06-handling-line")?.textContent || "")));
    check("resubmission after conflict succeeds", true);

    // 5. Житель открывает ссылку «на другом устройстве» и видит ответ и хронологию.
    const other = watch(await (await browser.newContext({ viewport: { width: 360, height: 740 }, isMobile: true })).newPage());
    await other.goto(link);
    await other.waitForSelector("#receipt-root .civic-r06-receipt .civic-r06-receipt-reply:not([hidden])");
    // textContent: хронология в свёрнутом <details>, innerText её не включает.
    const viaLink = await other.evaluate(() => document.querySelector("#receipt-root .civic-r06-receipt").textContent);
    check("link on another device shows reply and status", viaLink.includes(reply2) && viaLink.includes("Дан ответ платформы") &&
      viaLink.includes("Ответ платформы обновлён"), viaLink);
    check("link view hides staff names, reasons and notes", !/fixture-editor|Второй сотрудник отвечает|Первый сотрудник/.test(viaLink), viaLink);
    ov = await overflowX(other, null);
    check("360px: link view has no horizontal scroll", ov.doc <= ov.win, JSON.stringify(ov));
    if (shotDir) await other.screenshot({ path: path.join(shotDir, "r13_link_reply_360.png"), fullPage: true });
    await phone.locator("#resident-root .civic-r06-receipt button", { hasText: "Обновить статус" }).click();
    await phone.waitForFunction((r) => (document.querySelector("#resident-root .civic-r06-receipt")?.textContent || "").includes(r), reply2);
    check("original tab sees reply after refresh", true);

    // 6. Истёкшая сессия сотрудника: действие не выполнено, текст в форме остаётся.
    await desk.click("#expire");
    await desk.evaluate(() => window.__r06.moderation.refresh());
    const closingReason = "Закрываю после ответа — попытка с истёкшей сессией";
    await desk.locator("#moderation-root .civic-r06-handling select").selectOption("closed").catch(() => null);
    await desk.locator("#moderation-root .civic-r06-handling textarea").last().fill(closingReason);
    await desk.locator("#moderation-root .civic-r06-handling button[type=submit]").click();
    await desk.waitForFunction(() => /истекла|Войдите снова|изменено/.test((document.querySelector("#moderation-root .civic-r06-detail")?.textContent || "")));
    check("expired session keeps typed reason", (await desk.locator("#moderation-root .civic-r06-handling textarea").last().inputValue()) === closingReason);

    // 7. Узкий экран кабинета сотрудника.
    const staffPhone = watch(await (await browser.newContext({ viewport: { width: 360, height: 740 } })).newPage());
    await staffPhone.goto(base + "/harness/");
    await staffPhone.waitForSelector("body[data-r06-ready='1']");
    await login(staffPhone, "С ответом");
    await openFirst(staffPhone);
    ov = await overflowX(staffPhone, null);
    check("360px: staff card has no horizontal scroll", ov.doc <= ov.win, JSON.stringify(ov));
    if (shotDir) await staffPhone.screenshot({ path: path.join(shotDir, "r13_staff_360.png"), fullPage: true });

    // 8. 429 от настоящего стенда с лимитом 1: понятное время повтора, текст не потерян.
    const lim = watch(await (await browser.newContext({ viewport: { width: 360, height: 740 } })).newPage());
    await lim.goto(limitedBase + "/harness/");
    await lim.waitForSelector("#resident-root .civic-r06-form");
    await fill(lim, { text: "Первое сообщение: яма у въезда во двор, машины объезжают." , category: "roads" });
    await lim.locator("#resident-root button[type=submit]").click();
    await lim.waitForSelector("#resident-root .civic-r06-receipt");
    await lim.locator("#resident-root button", { hasText: "Написать ещё одно сообщение" }).click();
    await lim.waitForSelector("#resident-root .civic-r06-form");
    const second = "Второе сообщение: на остановке нет навеса, люди мокнут.";
    await fill(lim, { text: second, category: "transport_stops" });
    await lim.locator("#resident-root button[type=submit]").click();
    await lim.waitForSelector("#resident-root .civic-r06-status-error");
    const limitText = await lim.locator("#resident-root .civic-r06-status").innerText();
    check("429 shows retry time and keeps text", /через \d+ (мин|с)/.test(limitText) && /общим/.test(limitText) &&
      (await lim.locator("#resident-root textarea").inputValue()) === second, limitText);

    // 9. Выход очищает черновики и номера квитанций вкладки.
    await lim.locator("#resident-root textarea").fill("Черновик, который должен исчезнуть после выхода из учётной записи.");
    await lim.click("#logout");
    await lim.waitForFunction(() => document.querySelector("#resident-root textarea") && document.querySelector("#resident-root textarea").value === "");
    const left = await lim.evaluate(() => Object.keys(sessionStorage).filter((k) => k.startsWith("civic-r06-")));
    check("logout clears drafts and receipts from tab storage", left.length === 0, JSON.stringify(left));
    check("no page errors", pageErrors.length === 0, pageErrors.join("; "));
  } catch (error) {
    check("browser run completed", false, String(error && error.stack || error));
  } finally {
    if (browser) await browser.close();
    server.kill();
    limited.kill();
    fs.rmSync(dbDir, { recursive: true, force: true });
  }
  const failed = results.filter((r) => r.status !== "PASS");
  console.log(JSON.stringify({ classifier, passed: results.length - failed.length, failed: failed.length, results }, null, 1));
  process.exit(failed.length ? 1 : 0);
})();
