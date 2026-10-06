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
  const server = spawn("python3", [path.join(ROOT, "tests/civic/R06/harness/serve_r06.py"), "--port", String(PORT),
    "--db", path.join(dbDir, "feedback.sqlite3")], { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"] });
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
    await page.locator("#moderation-root .civic-r06-tab", { hasText: "Ожидают" }).click();
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
