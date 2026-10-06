// R07 браузерная проверка демо-страницы модуля (реальный Chromium через Playwright).
// node research/round-11-results/R07/browser_check.cjs [baseUrl]  — нужен запущенный devserver.
const { chromium } = require(process.env.PW_MODULE || "playwright");
const base = process.argv[2] || "http://127.0.0.1:8517";
const out = process.env.OUT_DIR || __dirname;
(async () => {
  const res = { base, checks: [] };
  const ok = (name, pass, detail) => res.checks.push({ name, status: pass ? "PASS" : "FAIL", detail });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1360, height: 860 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(base + "/civic/scenarios/demo.html?basemap=none");
  await page.waitForSelector(".civic-r07-graphinfo .civic-r07-badge", { timeout: 15000 });
  ok("graph_loaded_with_evidence_badge", true, await page.textContent(".civic-r07-graphinfo .civic-r07-badge"));
  ok("driving_marked_not_ready", (await page.locator("option[disabled]").allTextContents()).some((t) => t.includes("NOT_READY")), null);
  await page.click(".civic-r07-primary");
  await page.waitForSelector(".civic-r07-table tbody tr", { timeout: 15000 });
  const rows = await page.locator(".civic-r07-table tbody tr").count();
  ok("result_table_rows", rows === 18, rows);
  await page.locator(".civic-r07-table tbody tr").nth(0).click();
  await page.waitForTimeout(500);
  const nRoutes = await page.evaluate(() => window.__map.getSource("civic-r07-routes").serialize().data.features.length);
  ok("pair_routes_drawn_base_A_B", nRoutes === 3, nRoutes);
  ok("cards_rendered", (await page.locator(".civic-r07-card").count()) === 2, null);
  ok("hypothesis_notice_visible", (await page.textContent(".civic-r07-notice")).includes("не официальное"), null);
  await page.screenshot({ path: out + "/screenshot_k03_ab.png" });
  // мобильная ширина
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(400);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  ok("mobile_no_horizontal_overflow", !overflow, null);
  await page.screenshot({ path: out + "/screenshot_mobile.png", fullPage: false });
  // синтетика: клик-закрытие ребра на карте
  await page.setViewportSize({ width: 1360, height: 860 });
  await page.selectOption(".civic-r07-panel select[aria-label='Граф']", "synthetic-tiny-v1");
  await page.waitForFunction(() => document.querySelector(".civic-r07-graphinfo").textContent.includes("СИНТЕТИКА"));
  await page.selectOption(".civic-r07-panel select[aria-label='Кейс']", "synthetic-tiny-v1-demo");
  await page.waitForTimeout(800);
  const before = await page.textContent(".civic-r07-tab:nth-child(1)");
  ok("synthetic_case_loaded", before.includes("2 рёбер"), before);
  // реальный клик по линии ребра e_be (B(71.402,51.1)–E(71.402,51.1015)) в режиме «закрыть»
  const pt = await page.evaluate(() => window.__map.project([71.402, 51.10075]));
  const box = await page.locator("#map").boundingBox();
  await page.mouse.click(box.x + pt.x, box.y + pt.y);
  await page.waitForTimeout(300);
  const after = await page.textContent(".civic-r07-tab:nth-child(1)");
  ok("map_click_closes_graph_edge", after.includes("3 рёбер"), after);
  // клик по пустому месту карты не создаёт «дорожный объект»
  await page.mouse.click(box.x + 20, box.y + 20);
  await page.waitForTimeout(200);
  ok("click_off_graph_ignored", (await page.textContent(".civic-r07-tab:nth-child(1)")).includes("3 рёбер"), null);
  await page.click(".civic-r07-primary");
  await page.waitForSelector(".civic-r07-table tbody tr");
  const txt = await page.textContent(".civic-r07-table");
  ok("synthetic_unreachable_label", txt.includes("нет пути в модели"), null);
  ok("synthetic_unknown_label", txt.includes("нет данных о доступе"), null);
  await page.screenshot({ path: out + "/screenshot_synthetic.png" });
  // ошибка валидации показывается пользователю: интервал end <= start
  await page.evaluate(() => { const i = document.querySelectorAll(".civic-r07-closure input[aria-label='Конец']")[0]; i.value = "2026-10-07T07:00"; i.dispatchEvent(new Event("change")); });
  await page.click(".civic-r07-primary");
  await page.waitForSelector(".civic-r07-error:not([hidden])", { timeout: 5000 });
  ok("validation_error_shown", (await page.textContent(".civic-r07-error")).includes("invalid_payload"), await page.textContent(".civic-r07-error"));
  // destroy снимает слои
  const left = await page.evaluate(() => { window.R07.destroy(); return document.querySelectorAll(".civic-r07-panel").length; });
  ok("destroy_removes_panel", left === 0, left);
  ok("no_page_errors", errors.length === 0, errors);
  await browser.close();
  res.verdict = res.checks.every((c) => c.status === "PASS") ? "PASS" : "FAIL";
  console.log(JSON.stringify(res, null, 1));
})().catch((e) => { console.error(e); process.exit(2); });
