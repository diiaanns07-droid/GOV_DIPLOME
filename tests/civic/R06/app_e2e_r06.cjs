/* Сквозной браузерный сценарий R06 в собранном приложении R01 (не в FIXTURE-стенде).
 *
 *   R06_BASE=http://127.0.0.1:8501 R06_USER=<editor> R06_PASS=<пароль> R06_OBJECT_ID=<опубликованный id> \
 *     node tests/civic/R06/app_e2e_r06.cjs [--screenshots DIR]
 *
 * Требует: сервер R01 с R02 (CivicService) и R06, применённый research/round-11-results/R06/
 * r01_integration.patch (или эквивалент), существующую учётную запись редактора и опубликованный
 * объект. Пароль только из окружения — в Git его нет. Пишет в БД одно тестовое сообщение
 * (синтетический текст с пометкой R06-E2E); запускать на тестовой, а не рабочей базе.
 *
 * Round 13 (необязательные переменные):
 *   R06_EXPECT_CLASSIFIER=r08|disabled — какой источник подсказки должен быть у шлюза;
 *   R06_R01_R13_PATCH=1 — применён research/round-13-results/R06/r01_r13_integration.patch:
 *     ссылка #civic-receipt=… открывает квитанцию, выход очищает черновики. Без переменной эти
 *     проверки помечаются NOT_RUN, а не PASS.
 */
"use strict";

const path = require("path");

function loadPlaywright() {
  try {
    return require("playwright");
  } catch (e) {
    const globalRoot = require("child_process").execSync("npm root -g").toString().trim();
    return require(path.join(globalRoot, "playwright"));
  }
}

const BASE = process.env.R06_BASE;
const USER = process.env.R06_USER;
const PASS = process.env.R06_PASS;
const OBJECT_ID = process.env.R06_OBJECT_ID;
const args = process.argv.slice(2);
const shotDir = args.includes("--screenshots") ? path.resolve(args[args.indexOf("--screenshots") + 1]) : null;
const EXPECT_CLASSIFIER = process.env.R06_EXPECT_CLASSIFIER || null;
const R01_PATCH = process.env.R06_R01_R13_PATCH === "1";
const results = [];
const check = (name, ok, detail) => {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: detail || null });
  if (!ok) console.error("FAIL:", name, detail || "");
};
const notRun = (name, reason) => results.push({ name, status: "NOT_RUN", detail: reason });

(async () => {
  if (!BASE || !USER || !PASS || !OBJECT_ID) {
    console.log(JSON.stringify({ status: "NOT_RUN", reason: "set R06_BASE, R06_USER, R06_PASS, R06_OBJECT_ID" }));
    process.exit(2);
  }
  // Без длинных цифр: 10+ цифр подряд R06 считает возможным персональным номером и не публикует.
  const marker = "R06-E2E-" + Date.now().toString(36);
  const xss = '<img src=x onerror="window.__r06xss=1">';
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("dialog", (d) => { errors.push("dialog: " + d.message()); d.dismiss(); });
    await page.goto(BASE + "/");
    await page.waitForFunction(() => window.CivicShell && window.CivicFeedback && window.CivicShell.modules, null, { timeout: 15000 });
    const modules = await page.evaluate(() => window.CivicShell.modules);
    check("feedback module ready in gateway", modules && modules.feedback && modules.feedback.status === "ready", JSON.stringify(modules));

    // Житель: форма из shell (как из onFeedback карты R03).
    await page.evaluate((id) => window.CivicShell.openFeedback({ objectId: id }), OBJECT_ID);
    const root = page.locator("#civic-feedback-root");
    await root.locator(".civic-r06-form").waitFor();
    check("official notice in app form", (await root.innerText()).includes("официальная регистрация не выполняется"));
    await root.locator("select").selectOption("sidewalks");
    await root.locator("textarea").fill(marker + " " + xss + " нет прохода вдоль ограждения.");
    await root.locator("input[type=radio][value=true]").check();
    await root.locator("button[type=submit]").click();
    await root.locator(".civic-r06-receipt").waitFor({ timeout: 10000 });
    check("receipt in app", /fbr_/.test(await root.innerText()));
    const receiptId = (await root.locator(".civic-r06-receipt-id").innerText()).trim();
    if (shotDir) await page.locator("#civic-feedback-box").screenshot({ path: path.join(shotDir, "r06_app_receipt.png") });

    // Сотрудник: вход через api shell, кнопка модерации, решение.
    check("moderation button hidden for anonymous", await page.locator("#civic-moderation-button").isHidden());
    await page.evaluate(([u, p]) => window.CivicShell.api.login(u, p), [USER, PASS]);
    await page.locator("#civic-moderation-button").waitFor({ state: "visible", timeout: 10000 });
    await page.click("#civic-moderation-button");
    const mod = page.locator("#civic-moderation-root");
    await mod.locator(".civic-r06-queue-item").first().waitFor({ timeout: 10000 });
    await mod.locator(".civic-r06-queue-item", { hasText: marker }).first().click();
    await mod.locator(".civic-r06-decision").waitFor();
    const detail = await mod.locator(".civic-r06-detail").innerText();
    check("detail route served by gateway (history available)", !detail.includes("Карточка собрана из очереди"));
    // Round 13: источник подсказки и отсутствие числа — по данным шлюза, а не по ожиданию.
    const clf = await page.evaluate(async (m) => {
      const data = await window.CivicShell.api.request("GET", "/staff/feedback?status=all&moderation=all&q=" + encodeURIComponent(m));
      const item = (data.items || [])[0] || {};
      return { info: data.classifier || null, item: item.classifier || null };
    }, marker);
    if (EXPECT_CLASSIFIER) {
      check("r13 classifier source reported by gateway", clf.info && clf.info.source === EXPECT_CLASSIFIER, JSON.stringify(clf));
    } else notRun("r13 classifier source reported by gateway", "R06_EXPECT_CLASSIFIER не задан: " + JSON.stringify(clf.info));
    check("r13 hint has no numeric score", !clf.item || !clf.item.suggestion || clf.item.suggestion.score === null, JSON.stringify(clf.item));
    const hintText = await mod.locator(".civic-r06-classifier").innerText();
    check("r13 hint text has no number", !/\d[.,]\d|%/.test(hintText.replace(/civic-clf[^\s,]*/g, "")), hintText);
    await mod.locator(".civic-r06-decision textarea").first().fill("R06-E2E проверка модерации");
    await mod.locator(".civic-r06-decision textarea").last().fill("Спасибо, сообщение проверено модератором платформы.");
    if (shotDir) await page.locator("#civic-moderation").screenshot({ path: path.join(shotDir, "r06_app_moderation.png") });
    await mod.locator(".civic-r06-decision button[type=submit]").click();
    await page.waitForFunction(() => {
      const h4 = document.querySelector("#civic-moderation-root .civic-r06-detail h4")?.textContent || "";
      const status = document.querySelector("#civic-moderation-root .civic-r06-decision .civic-r06-status")?.textContent || "";
      return /Проверено модератором/.test(h4) || (status && status !== "Сохраняем…");
    }, null, { timeout: 10000 });
    const decisionStatus = await page.evaluate(() => ({
      h4: document.querySelector("#civic-moderation-root .civic-r06-detail h4")?.textContent || "",
      status: document.querySelector("#civic-moderation-root .civic-r06-decision .civic-r06-status")?.textContent || "" }));
    check("approved in app", /Проверено модератором/.test(decisionStatus.h4), JSON.stringify(decisionStatus));
    // Round 12: решение с ответом переводит новое сообщение в «Дан ответ»; заметка видна только сотруднику.
    await page.waitForFunction(() => /Дан ответ/.test(document.querySelector("#civic-moderation-root .civic-r06-handling-line")?.textContent || ""), null, { timeout: 10000 });
    check("handling status answered in app", true);
    const note = marker + " служебная заметка";
    await mod.locator(".civic-r06-note textarea").fill(note);
    await mod.locator(".civic-r06-note button[type=submit]").click();
    await page.waitForFunction((n) => (document.querySelector("#civic-moderation-root .civic-r06-history")?.textContent || "").includes(n), note, { timeout: 10000 });
    check("staff note saved in app", true);
    if (shotDir) await page.locator("#civic-moderation").screenshot({ path: path.join(shotDir, "r06_app_moderation_r12.png") });

    // Публичная карточка: XSS как текст.
    await page.click("#civic-moderation [data-close=moderation]");
    await page.evaluate((id) => { window.CivicShell.closeFeedback(); window.CivicShell.openFeedback({ objectId: id }); }, OBJECT_ID);
    await root.locator(".civic-r06-public-item", { hasText: marker }).waitFor({ timeout: 10000 });
    const injected = await page.evaluate(() => ({
      imgs: document.querySelectorAll("#civic-feedback-root img").length, flag: window.__r06xss || null }));
    check("public card shows XSS as text", injected.imgs === 0 && injected.flag === null, JSON.stringify(injected));
    const publicText = await root.locator(".civic-r06-public-item", { hasText: marker }).innerText();
    check("public card has no staff note", !publicText.includes("служебная заметка"));

    // Round 13: ссылка из квитанции «на другом устройстве» показывает ответ платформы.
    if (R01_PATCH) {
      const other = await (await browser.newContext({ viewport: { width: 360, height: 740 }, isMobile: true })).newPage();
      other.on("pageerror", (e) => errors.push(String(e)));
      await other.goto(BASE + "/#civic-receipt=" + encodeURIComponent(receiptId));
      await other.locator("#civic-feedback-root .civic-r06-receipt .civic-r06-receipt-reply:not([hidden])").waitFor({ timeout: 15000 });
      const viaLink = await other.evaluate(() => document.querySelector("#civic-feedback-root .civic-r06-receipt").textContent);
      check("r13 receipt link in app shows reply", viaLink.includes("Спасибо, сообщение проверено модератором платформы.") &&
        viaLink.includes("Дан ответ платформы") && !viaLink.includes("R06-E2E проверка модерации"), viaLink.slice(0, 300));
      const overflow = await other.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      check("r13 receipt link at 360px has no horizontal scroll", overflow <= 0, String(overflow));
      if (shotDir) await other.screenshot({ path: path.join(shotDir, "r13_app_receipt_link_360.png"), fullPage: false });
      await other.close();
      // Черновик в форме жителя до выхода из учётной записи.
      await page.evaluate((id) => { window.CivicShell.closeFeedback(); window.CivicShell.openFeedback({ objectId: id }); }, OBJECT_ID);
      const again = root.locator("button", { hasText: "Написать ещё одно сообщение" });
      if (await again.count()) await again.click();
      await root.locator(".civic-r06-form textarea").fill(marker + " черновик до выхода");
    } else {
      notRun("r13 receipt link in app shows reply", "R01 shell без r01_r13_integration.patch");
    }

    // Выход: кнопка модерации скрывается, staff-запрос отклоняется.
    await page.evaluate(() => window.CivicShell.api.logout());
    await page.locator("#civic-moderation-button").waitFor({ state: "hidden", timeout: 10000 });
    const after = await page.evaluate(async () => {
      try { await window.CivicShell.api.request("GET", "/staff/feedback"); return "allowed"; }
      catch (e) { return e.status; }
    });
    check("staff queue refused after logout", after === 401, String(after));
    if (R01_PATCH) {
      const left = await page.evaluate(() => Object.keys(sessionStorage).filter((k) => k.startsWith("civic-r06-")));
      check("r13 logout clears resident drafts and receipts", left.length === 0, JSON.stringify(left));
    } else notRun("r13 logout clears resident drafts and receipts", "R01 shell без r01_r13_integration.patch");
    check("no page errors", errors.length === 0, errors.join("; "));
  } catch (error) {
    check("app run completed", false, String((error && error.stack) || error));
  } finally {
    await browser.close();
  }
  const failed = results.filter((r) => r.status === "FAIL");
  const skipped = results.filter((r) => r.status === "NOT_RUN");
  console.log(JSON.stringify({ passed: results.length - failed.length - skipped.length, failed: failed.length,
    not_run: skipped.length, results }, null, 1));
  process.exit(failed.length ? 1 : 0);
})();
