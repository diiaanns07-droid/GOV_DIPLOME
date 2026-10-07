/* Браузерная проверка R06 на FIXTURE-стенде (реальный Chromium через Playwright).
 *
 *   node tests/civic/R06/browser_r06.cjs [--screenshots DIR]
 *
 * Запускает tests/civic/R06/harness/serve_r06.py на 127.0.0.1 со временной БД,
 * проверяет форму жителя, квитанцию, сохранение текста при ошибках, однократную
 * отправку, предупреждение о дубликате, модерацию, XSS как текст, logout/истёкшую
 * сессию и мобильную ширину. Внешние сервисы не используются.
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
const PORT = 8700 + Math.floor(Math.random() * 200);
const BASE = `http://127.0.0.1:${PORT}`;
const XSS = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script> https://evil.example/?q=<b>';
const results = [];

function check(name, condition, detail) {
  results.push({ name, status: condition ? "PASS" : "FAIL", detail: detail || null });
  if (!condition) console.error("FAIL:", name, detail || "");
}

async function waitForServer(proc) {
  for (let i = 0; i < 50; i += 1) {
    try {
      const r = await fetch(BASE + "/harness/session");
      if (r.ok) return;
    } catch (e) { /* ещё стартует */ }
    if (proc.exitCode !== null) throw new Error("harness exited");
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error("harness did not start");
}

async function apiQueue(page, moderation) {
  return page.evaluate(async (m) => {
    const r = await fetch("/api/civic/v1/staff/feedback?moderation=" + m + "&limit=50", { credentials: "same-origin" });
    return { status: r.status, body: await r.json() };
  }, moderation);
}

async function fillForm(page, { category = "sidewalks", text, consent = true, kind = "problem" }) {
  const root = page.locator("#resident-root");
  await root.locator(`input[type=radio][value=${kind}]`).check();
  await root.locator("select").selectOption(category);
  await root.locator("textarea").fill(text);
  await root.locator(`input[type=radio][value=${consent ? "true" : "false"}]`).check();
}

(async () => {
  const dbDir = fs.mkdtempSync(path.join(os.tmpdir(), "r06-browser-"));
  // Лимит частоты поднят только для длинного сценария; сам лимит проверяют тесты Python (429).
  const server = spawn("python3", [path.join(ROOT, "tests/civic/R06/harness/serve_r06.py"), "--port", String(PORT),
    "--db", path.join(dbDir, "feedback.sqlite3"), "--per-sender-max", "20"], { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"] });
  let browser;
  try {
    await waitForServer(server);
    const { chromium } = loadPlaywright();
    browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const dialogs = [];
    const consoleErrors = [];
    page.on("dialog", (d) => { dialogs.push(d.message()); d.dismiss(); });
    page.on("pageerror", (e) => consoleErrors.push(String(e)));
    await page.goto(BASE + "/harness/");
    await page.waitForSelector("body[data-r06-ready='1']");
    await page.waitForSelector("#resident-root .civic-r06-public");

    // 1. Пустой публичный список и пояснение об официальной регистрации.
    const formText = await page.locator("#resident-root").innerText();
    check("official notice shown in form", formText.includes("официальная регистрация не выполняется"));
    check("empty public list", formText.includes("Пока нет опубликованных сообщений"));
    check("consent not preselected", (await page.locator("#resident-root input[type=radio][value=true]").isChecked()) === false);

    // 2. Локальная валидация не теряет текст и не отправляет запрос.
    await page.locator("#resident-root textarea").fill("Коротко");
    await page.locator("#resident-root button[type=submit]").click();
    check("client validation shows errors", (await page.locator("#resident-root .civic-r06-field-error").count()) >= 2);
    check("text kept after validation error", (await page.locator("#resident-root textarea").inputValue()) === "Коротко");

    // 3. Сетевой сбой: текст сохраняется, повтор с тем же client_request_id создаёт одно сообщение.
    await fillForm(page, { text: XSS + " Нет прохода вдоль ограждения." });
    await page.route("**/api/civic/v1/feedback", (route) => route.abort());
    await page.locator("#resident-root button[type=submit]").click();
    await page.waitForSelector("#resident-root .civic-r06-status-error");
    const netError = await page.locator("#resident-root .civic-r06-status").innerText();
    check("network error message keeps text", netError.includes("Текст сохранён") &&
      (await page.locator("#resident-root textarea").inputValue()).startsWith("<img"), netError);
    await page.unroute("**/api/civic/v1/feedback");

    // 4. Двойной клик: одна отправка, квитанция без обещаний исполнения.
    await page.locator("#resident-root button[type=submit]").dblclick();
    await page.waitForSelector("#resident-root .civic-r06-receipt");
    const receiptText = await page.locator("#resident-root .civic-r06-receipt").innerText();
    check("receipt shows id and pending label", /fbr_/.test(receiptText) && receiptText.includes("Ожидает проверки модератором платформы"));
    check("receipt states no official registration", receiptText.includes("Официальная регистрация обращения не выполняется"));
    check("receipt does not promise execution", !/принят[оа]? в работу|исполнен/i.test(receiptText));
    if (shotDir) await page.locator("#resident-root").screenshot({ path: path.join(shotDir, "r06_receipt.png") });

    // 5. Повтор того же текста → предупреждение о дубликате, а не тихая копия.
    await page.locator("#resident-root button", { hasText: "Написать ещё одно сообщение" }).click();
    await fillForm(page, { text: XSS + " Нет прохода вдоль ограждения." });
    await page.locator("#resident-root button[type=submit]").click();
    await page.waitForSelector("#resident-root .civic-r06-status-warning");
    check("duplicate warning with confirm", (await page.locator("#resident-root button", { hasText: "Всё равно отправить" }).count()) === 1);

    // 6. Черновик объекта: ошибка от сервера, текст в форме.
    await page.selectOption("#target", "object:demo-astana-draft-04");
    await page.waitForSelector("#resident-root .civic-r06-form");
    await fillForm(page, { text: "Сообщение к черновику объекта, который не опубликован.", category: "roads" });
    await page.locator("#resident-root button[type=submit]").click();
    await page.waitForSelector("#resident-root .civic-r06-status-error");
    const draftErr = await page.locator("#resident-root").innerText();
    check("draft object rejected without revealing draft", draftErr.includes("Объект не найден") && !draftErr.includes("Черновик редактора"));
    check("text kept after server error", (await page.locator("#resident-root textarea").inputValue()).startsWith("Сообщение к черновику"));

    // 7. Сообщение о месте без объекта, без согласия на публикацию.
    await page.selectOption("#target", "point:71.45,51.16");
    await page.waitForSelector("#resident-root .civic-r06-form");
    await fillForm(page, { text: "Предлагаю поставить скамейки у остановки, звоните +7 701 123 45 67.", consent: false, kind: "suggestion", category: "transport_stops" });
    await page.locator("#resident-root button[type=submit]").click();
    await page.waitForSelector("#resident-root .civic-r06-receipt");
    check("place-only receipt warns about contacts", (await page.locator("#resident-root .civic-r06-receipt").innerText()).includes("не будут опубликованы"));

    // 8. Аноним не видит очередь.
    const anonymousQueue = await apiQueue(page, "pending");
    check("anonymous queue is 401", anonymousQueue.status === 401);
    check("moderation UI shows login error", (await page.locator("#moderation-root").innerText()).includes("Войдите снова"));

    // 9. Житель (fixture) не может модерировать.
    await page.click("#login-resident");
    await page.waitForFunction(() => document.getElementById("session").textContent.includes("resident"));
    check("resident queue is 403", (await apiQueue(page, "pending")).status === 403);

    // 10. Редактор одобряет сообщение с XSS-текстом и XSS-ответом.
    await page.click("#login-editor");
    await page.waitForFunction(() => document.getElementById("session").textContent.includes("editor"));
    await page.waitForSelector("#moderation-root .civic-r06-queue-item");
    const pendingCount = (await apiQueue(page, "pending")).body.data.items.length;
    check("double click created one message (2 pending total)", pendingCount === 2, String(pendingCount));
    await page.locator("#moderation-root .civic-r06-queue-item").first().click();
    await page.waitForSelector("#moderation-root .civic-r06-decision");
    const detailText = await page.locator("#moderation-root .civic-r06-detail").innerText();
    check("staff detail shows object and synthetic badge", detailText.includes("Демонстрационный ремонт прохода") && detailText.includes("синтетические данные"));
    await page.locator("#moderation-root .civic-r06-decision textarea").first().fill("Проверено: по теме объекта");
    await page.locator("#moderation-root .civic-r06-decision textarea").last().fill(XSS);
    if (shotDir) await page.locator("#moderation-root").screenshot({ path: path.join(shotDir, "r06_moderation.png") });
    await page.locator("#moderation-root .civic-r06-decision button[type=submit]").click();
    await page.waitForFunction(() => document.querySelector("#moderation-root .civic-r06-detail h4") &&
      document.querySelector("#moderation-root .civic-r06-detail h4").textContent.includes("Проверено модератором"));
    check("approved via UI", (await apiQueue(page, "approved")).body.data.items.length === 1);

    // 11. Публичная карточка показывает XSS как текст.
    await page.selectOption("#target", "object:demo-astana-park-02");
    await page.selectOption("#target", "object:demo-astana-work-01");
    await page.waitForSelector("#resident-root .civic-r06-public-item");
    const publicText = await page.locator("#resident-root .civic-r06-public-item").innerText();
    const injected = await page.evaluate(() => ({
      imgs: document.querySelectorAll("#resident-root img, #moderation-root img").length,
      scripts: document.querySelectorAll("#resident-root script, #moderation-root script").length,
      bold: document.querySelectorAll("#resident-root b, #moderation-root b").length,
      flag: window.__xss || null,
    }));
    check("xss payload rendered as literal text", publicText.includes('<img src=x onerror="window.__xss=1">') && publicText.includes("<script>"));
    check("xss payload not executed or parsed", injected.imgs === 0 && injected.scripts === 0 && injected.bold === 0 && injected.flag === null && dialogs.length === 0, JSON.stringify(injected));
    if (shotDir) await page.locator("#resident-root").screenshot({ path: path.join(shotDir, "r06_public_card.png") });

    // 12. Logout: открытая форма модерации не выполняет действие.
    await page.locator("#moderation-root .civic-r06-tab", { hasText: "Новые" }).click();
    await page.waitForSelector("#moderation-root .civic-r06-queue-item");
    await page.locator("#moderation-root .civic-r06-queue-item").first().click();
    await page.waitForSelector("#moderation-root .civic-r06-decision");
    await page.click("#logout");
    await page.waitForFunction(() => document.getElementById("session").textContent.includes("не вошли"));
    await page.locator("#moderation-root .civic-r06-decision textarea").first().fill("Попытка после выхода");
    await page.locator("#moderation-root .civic-r06-decision button[type=submit]").click();
    await page.waitForFunction(() => /Войдите снова|не выполнено/.test(document.querySelector("#moderation-root .civic-r06-decision .civic-r06-status").textContent));
    check("logout blocks moderation in open form", true);

    // 13. Истёкшая сессия тоже не выполняет действие.
    await page.click("#login-editor");
    await page.waitForFunction(() => document.getElementById("session").textContent.includes("editor"));
    await page.waitForSelector("#moderation-root .civic-r06-queue-item");
    await page.locator("#moderation-root .civic-r06-queue-item").first().click();
    await page.waitForSelector("#moderation-root .civic-r06-decision");
    await page.click("#expire");
    await page.locator("#moderation-root .civic-r06-decision textarea").first().fill("Попытка с истёкшей сессией");
    await page.locator("#moderation-root .civic-r06-decision button[type=submit]").click();
    await page.waitForFunction(() => /истекла/.test(document.querySelector("#moderation-root .civic-r06-decision .civic-r06-status").textContent));
    await page.click("#login-editor");
    await page.waitForFunction(() => document.getElementById("session").textContent.includes("editor"));
    check("pending unchanged after logout/expired attempts", (await apiQueue(page, "pending")).body.data.items.length === 1);

    // 14a. Шлюз без маршрута GET /staff/feedback/{id}: карточка из очереди, решение доступно.
    await page.route(/\/api\/civic\/v1\/staff\/feedback\/\d+$/, (route) => route.request().method() === "GET"
      ? route.fulfill({ status: 404, contentType: "application/json",
          body: JSON.stringify({ ok: false, error: { code: "not_found", message: "Адрес API не найден." } }) })
      : route.continue());
    await page.evaluate(() => window.__r06.moderation.refresh());
    await page.waitForSelector("#moderation-root .civic-r06-queue-item");
    await page.locator("#moderation-root .civic-r06-queue-item").first().click();
    await page.waitForSelector("#moderation-root .civic-r06-decision");
    const degraded = await page.locator("#moderation-root .civic-r06-detail").innerText();
    check("degraded detail without detail route", degraded.includes("Карточка собрана из очереди") && degraded.includes("Предлагаю поставить скамейки"));
    await page.unroute(/\/api\/civic\/v1\/staff\/feedback\/\d+$/);

    // 14b. Вызов как из R03 onFeedback: objectId + Polygon объекта; Polygon без объекта не отправляется.
    const r03 = await page.evaluate(async () => {
      const api = window.CivicFeedback.createFetchApi("/api/civic/v1");
      const box = document.createElement("div");
      document.getElementById("resident-root").after(box);
      const polygon = { type: "Polygon", coordinates: [[[71.40, 51.12], [71.41, 51.12], [71.41, 51.13], [71.40, 51.12]]] };
      const withObject = window.CivicFeedback.mount({ root: box, api, objectId: "demo-astana-park-02", geometry: polygon });
      box.querySelector("select").value = "landscaping";
      box.querySelector("select").dispatchEvent(new Event("change"));
      box.querySelector("textarea").value = "Сломаны скамейки в сквере, нужен ремонт.";
      box.querySelector("textarea").dispatchEvent(new Event("input"));
      box.querySelectorAll("input[type=radio][value=false]")[0].click();
      box.querySelector("form").requestSubmit();
      for (let i = 0; i < 50 && !box.querySelector(".civic-r06-receipt"); i += 1) await new Promise((r) => setTimeout(r, 50));
      const okReceipt = Boolean(box.querySelector(".civic-r06-receipt"));
      withObject.destroy();
      const noObject = window.CivicFeedback.mount({ root: box, api, objectId: null, geometry: polygon });
      const noPlaceText = box.textContent.includes("Выберите объект или точку");
      noObject.destroy();
      box.remove();
      return { okReceipt, noPlaceText };
    });
    check("R03-style mount with object polygon submits", r03.okReceipt, JSON.stringify(r03));
    check("polygon without object is not treated as a place", r03.noPlaceText, JSON.stringify(r03));

    // 14. destroy() снимает разметку и класс.
    const destroyed = await page.evaluate(() => {
      window.__r06.resident.destroy();
      const root = document.getElementById("resident-root");
      return { children: root.childElementCount, cls: root.className };
    });
    check("destroy clears root", destroyed.children === 0 && !destroyed.cls.includes("civic-r06"), JSON.stringify(destroyed));

    // 15. Мобильная ширина: нет горизонтального переполнения формы.
    const mobile = await browser.newPage({ viewport: { width: 375, height: 780 } });
    mobile.on("dialog", (d) => { dialogs.push(d.message()); d.dismiss(); });
    await mobile.goto(BASE + "/harness/");
    await mobile.waitForSelector("#resident-root .civic-r06-form");
    const overflow = await mobile.evaluate(() => {
      const root = document.getElementById("resident-root");
      return root.scrollWidth - root.clientWidth;
    });
    check("mobile form has no horizontal overflow", overflow <= 1, String(overflow));
    if (shotDir) await mobile.locator("#resident-root").screenshot({ path: path.join(shotDir, "r06_form_mobile.png") });

    // ---------------- Round 12: черновик, потерянный ответ, конфликт версии, обработка, заметки
    const p2 = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    p2.on("pageerror", (e) => consoleErrors.push(String(e)));
    p2.on("dialog", (d) => { dialogs.push(d.message()); d.dismiss(); });
    const ready = async () => { await p2.waitForSelector("body[data-r06-ready='1']"); };
    const park = async () => { await p2.selectOption("#target", "object:demo-astana-park-02"); await p2.waitForSelector("#resident-root .civic-r06-form"); };
    const submitBtn = "#resident-root button[type=submit]";
    await p2.goto(BASE + "/harness/");
    await ready();
    await park();
    const draftText = "R12 черновик: сломана скамейка у входа в сквер, сидеть нельзя.";
    await fillForm(p2, { text: draftText, category: "landscaping", consent: true });
    await p2.reload();
    await ready();
    await park();
    check("r12 draft survives page reload (same tab)", (await p2.locator("#resident-root textarea").inputValue()) === draftText &&
      (await p2.locator("#resident-root select").inputValue()) === "landscaping" &&
      (await p2.locator("#resident-root input[type=radio][value=true]").isChecked()));
    // Сервер сохранил, но ответ потерян; затем двойной клик — одна запись, та же квитанция.
    await p2.route("**/api/civic/v1/feedback", async (route) => { await route.fetch(); await route.abort(); }, { times: 1 });
    await p2.locator(submitBtn).click();
    await p2.waitForSelector("#resident-root .civic-r06-status-error");
    await p2.locator(submitBtn).dblclick();
    await p2.waitForSelector("#resident-root .civic-r06-receipt");
    const firstReceipt = (await p2.locator("#resident-root .civic-r06-receipt-id").innerText()).trim();
    await p2.reload();
    await ready();
    await p2.selectOption("#target", "object:demo-astana-park-02");
    // Round 13: после перезагрузки вкладки житель снова видит квитанцию и статус, а не пустую форму.
    await p2.waitForSelector("#resident-root .civic-r06-receipt .civic-r06-receipt-handling:not(:empty)");
    check("r13 receipt card restored after reload", (await p2.locator("#resident-root .civic-r06-receipt-id").innerText()).trim() === firstReceipt);
    await p2.locator("#resident-root button", { hasText: "Написать ещё одно сообщение" }).click();
    await park();
    check("r12 draft cleared after successful send", (await p2.locator("#resident-root textarea").inputValue()) === "");
    // Ответ потерян, автор исправил текст: понятное предупреждение с прежней квитанцией, копия только по явному выбору.
    await fillForm(p2, { text: "R12 вторая версия: нет освещения на дорожке в сквере вечером.", category: "lighting", consent: false });
    await p2.route("**/api/civic/v1/feedback", async (route) => { await route.fetch(); await route.abort(); }, { times: 1 });
    await p2.locator(submitBtn).click();
    await p2.waitForSelector("#resident-root .civic-r06-status-error");
    await p2.locator("#resident-root textarea").fill("R12 вторая версия: нет освещения на дорожке в сквере вечером, совсем темно.");
    await p2.locator(submitBtn).click();
    await p2.waitForSelector("#resident-root .civic-r06-status-warning");
    const conflictText = await p2.locator("#resident-root .civic-r06-status").innerText();
    check("r12 edited resend shows saved previous receipt", conflictText.includes("Предыдущая версия уже сохранена") && /fbr_/.test(conflictText), conflictText);
    await p2.locator("#resident-root button", { hasText: "Отправить изменённый текст отдельным сообщением" }).click();
    await p2.waitForSelector("#resident-root .civic-r06-receipt");
    await p2.click("#login-editor");
    await p2.waitForFunction(() => document.getElementById("session").textContent.includes("editor"));
    const r12 = await p2.evaluate(async () => {
      const r = await fetch("/api/civic/v1/staff/feedback?status=all&q=" + encodeURIComponent("R12") + "&limit=50", { credentials: "same-origin" });
      return (await r.json()).data.items.map((i) => i.text);
    });
    check("r12 lost response + double click = one message", r12.filter((t) => t === draftText).length === 1, JSON.stringify(r12));
    check("r12 edited version saved only by explicit choice (2 versions)", r12.filter((t) => t.startsWith("R12 вторая версия")).length === 2, JSON.stringify(r12));
    check("r12 receipt shown after replayed send", /^fbr_/.test(firstReceipt), firstReceipt);
    // Сотрудник: поиск, статус «В работе», служебная заметка, журнал.
    await p2.waitForSelector("#moderation-root .civic-r06-queue-item");
    await p2.locator("#moderation-root input[type=search]").fill("скамейка");
    await p2.waitForFunction(() => document.querySelectorAll("#moderation-root .civic-r06-queue-item").length === 1);
    check("r12 queue search finds by word", (await p2.locator("#moderation-root .civic-r06-queue-item").innerText()).includes("скамейка"));
    await p2.locator("#moderation-root .civic-r06-queue-item").first().click();
    await p2.waitForSelector("#moderation-root .civic-r06-handling");
    check("r12 classifier absence is explicit", (await p2.locator("#moderation-root .civic-r06-classifier").innerText()).includes("модель не подключена"));
    await p2.locator("#moderation-root .civic-r06-handling select").selectOption("in_review");
    await p2.locator("#moderation-root .civic-r06-handling textarea").last().fill("Взято в работу сотрудником платформы");
    await p2.locator("#moderation-root .civic-r06-handling button[type=submit]").click();
    await p2.waitForFunction(() => /В работе/.test(document.querySelector("#moderation-root .civic-r06-handling-line").textContent));
    check("r12 status changed via UI", true);
    const note = "R12 служебно: уточнить у балансодержателя сквера";
    await p2.locator("#moderation-root .civic-r06-note textarea").fill(note);
    await p2.locator("#moderation-root .civic-r06-note button[type=submit]").click();
    await p2.waitForFunction((n) => document.querySelector("#moderation-root .civic-r06-history") &&
      document.querySelector("#moderation-root .civic-r06-history").textContent.includes(n), note);
    check("r12 note visible in staff history", true);
    if (shotDir) await p2.locator("#moderation-root").screenshot({ path: path.join(shotDir, "r06_r12_moderation.png") });
    const publicDump = await p2.evaluate(async () => {
      const r = await fetch("/api/civic/v1/objects/demo-astana-park-02/feedback", { credentials: "same-origin" });
      return await r.text();
    });
    check("r12 note and staff names never in public list", !publicDump.includes("R12 служебно") && !publicDump.includes("fixture-editor"));
    check("no page errors", consoleErrors.length === 0, consoleErrors.join("; "));
  } catch (error) {
    check("browser run completed", false, String(error && error.stack || error));
  } finally {
    if (browser) await browser.close();
    server.kill();
    fs.rmSync(dbDir, { recursive: true, force: true });
  }
  const failed = results.filter((r) => r.status !== "PASS");
  console.log(JSON.stringify({ passed: results.length - failed.length, failed: failed.length, results }, null, 1));
  process.exit(failed.length ? 1 : 0);
})();
