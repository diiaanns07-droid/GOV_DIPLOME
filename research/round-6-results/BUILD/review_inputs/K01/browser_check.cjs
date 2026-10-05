// K01 round-5: load the BUILD page in headless Chromium and record every request.
// Usage: NODE_PATH=$(npm root -g) node browser_check.cjs <file:///.../web/index.html | http://127.0.0.1:PORT/>
const { chromium } = require("playwright");
(async () => {
  const target = process.argv[2];
  const local = (u) => u.startsWith("file://") || /^https?:\/\/(127\.0\.0\.1|localhost)(:\d+)?\//.test(u) || u.startsWith("data:") || u.startsWith("blob:");
  const browser = await chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {});
  const page = await browser.newPage();
  const requests = [], failed = [], consoleErrors = [];
  page.on("request", (r) => requests.push(r.url()));
  page.on("requestfailed", (r) => failed.push(r.url() + " " + (r.failure() || {}).errorText));
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
  page.on("pageerror", (e) => consoleErrors.push("pageerror: " + e.message));
  await page.route("**/*", (route) => (local(route.request().url()) ? route.continue() : route.abort()));
  await page.goto(target, { waitUntil: "load" });
  await page.waitForTimeout(1500);
  const title = await page.title();
  const hasData = await page.evaluate(() => !!(window.CITY_EVIDENCE && window.CITY_EVIDENCE.cities));
  await browser.close();
  const external = requests.filter((u) => !local(u));
  const out = { target, title, requests: requests.length, external, failed, console_errors: consoleErrors, has_data: hasData,
                ok: external.length === 0 && failed.length === 0 && consoleErrors.length === 0 && hasData };
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(2); });
