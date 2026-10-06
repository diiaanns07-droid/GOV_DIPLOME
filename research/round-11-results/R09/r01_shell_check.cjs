// R09 внутри настоящего shell R01 (с r01_integration.patch): node r01_shell_check.cjs <baseUrl> <title> <outDir>
"use strict";
const path = require("path");
const { chromium } = require("playwright");
const [base, title, outDir] = process.argv.slice(2);
const checks = [];
const rec = (name, ok, detail) => checks.push({ name, status: ok ? "PASS" : "FAIL", detail: String(detail || "").slice(0, 300) });

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: "ru-RU" });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  try {
    const modules = await (await page.request.get(base + "/api/civic/v1/modules")).json();
    rec("modules_assistant_ready", modules?.data?.modules?.assistant?.status === "ready", JSON.stringify(modules?.data?.modules?.assistant));
    await page.goto(base);
    await page.waitForSelector("#civic-map-root .civic-item", { timeout: 20000 });
    await page.click(`#civic-map-root .civic-item:has-text("${title}")`);
    await page.waitForSelector("#civic-assistant-root .civic-r09", { timeout: 10000 });
    rec("assistant_mounted_in_card", await page.isVisible("#civic-assistant-box"), "");
    await page.click("#civic-assistant-root .civic-r09-chip >> text=Почему перенесли срок?");
    await page.waitForSelector("#civic-assistant-root .civic-r09-answer .civic-r09-badge", { timeout: 10000 });
    const text = await page.textContent("#civic-assistant-root .civic-r09-answer");
    rec("delay_answer_from_published_facts", text.includes("05.11.2026") && text.includes("20.10.2026") &&
      text.includes("задержка поставки плитки") && !text.includes("СЛУЖЕБНО"), text);
    rec("synthetic_marked", /синтетическ/i.test(text), "");
    await page.click("#civic-assistant-root .civic-r09-chip >> text=Сколько это стоит и откуда сумма?");
    await page.waitForFunction(() => /нет данных/.test(document.querySelector("#civic-assistant-root .civic-r09-answer")?.textContent || ""), null, { timeout: 10000 });
    rec("unknown_budget_no_data", true, "");
    await page.locator("#civic-assistant-box").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(outDir, "r01_shell_assistant_1440.png") });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator("#civic-assistant-box").scrollIntoViewIfNeeded();
    const ov = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, vw: innerWidth }));
    rec("mobile_390_no_horizontal_scroll", ov.doc <= ov.vw, JSON.stringify(ov));
    await page.screenshot({ path: path.join(outDir, "r01_shell_assistant_390.png") });
    // Ошибки загрузки внешних ресурсов (подложка карты за прокси среды) — не ошибки компонента;
    // они отмечаются отдельно и не подтверждают работу 3D-карты.
    const pageErrors = errors.filter((e) => !/Failed to load resource/.test(e));
    rec("no_page_script_errors", pageErrors.length === 0, pageErrors.join(" | "));
    checks.push({ name: "external_resources_blocked_info", status: "NOT_RUN",
      detail: (errors.length - pageErrors.length) + " resource loads failed (basemap/network policy); map rendering not claimed" });
  } catch (e) {
    rec("exception", false, e && e.stack || e);
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify({ checks }));
})();
