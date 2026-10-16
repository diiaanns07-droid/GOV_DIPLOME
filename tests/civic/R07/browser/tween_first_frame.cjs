// R07 раунд 15 · просьба R01 (B0.18, плавающее предупреждение r14_b2): метка кадра requestAnimationFrame бывает раньше
// performance.now() старта перекраски — k < 0, и цвет новой цели из белого уходил за 255 («#ffff100»):
// MapLibre «Could not parse color», значок на кадр без цвета. Проверка: кадры приходят на 50 мс «раньше» старта, после
// события birge:complaint все места новые (перекраска из белого) — каждый цвет, который модуль пишет в feature-state,
// правильный (#rrggbb или rgba с каналами 0…255), в консоли нет «Could not parse color».
// Запуск: python -m ui.civic_heat.devserver --port 8619 &   затем
//   NODE_PATH=$(npm root -g) R07_BASE=http://127.0.0.1:8619/civic/heat/demo.html node tests/civic/R07/browser/tween_first_frame.cjs
const { chromium } = require("playwright");

const BASE = process.env.R07_BASE || "http://127.0.0.1:8619/civic/heat/demo.html";
const okColor = (c) => {
  if (/^#[0-9a-f]{6}$/i.test(c)) return true;
  const m = /^rgba\((\d+),(\d+),(\d+),([0-9.]+)\)$/.exec(c);
  return !!m && [m[1], m[2], m[3]].every((v) => Number(v) <= 255) && Number(m[4]) <= 1;
};

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1 });
  const warns = [];
  page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") warns.push(m.text()); });
  page.on("pageerror", (e) => warns.push(String(e)));
  let fresh = false;
  await page.route(/\/api\/civic\/v2\/heat\?/, async (route) => {
    const res = await route.fetch();
    if (!fresh) return route.fulfill({ response: res });
    const body = await res.json();
    // все места — «новые» (другой id): перекраска каждого идёт из белого #ffffff, как у новой цели в R01 r14_b2
    (body.items || []).forEach((it) => { if (it.target.kind !== "district") it.target.id += "-new"; });
    return route.fulfill({ response: res, json: body });
  });
  await page.goto(`${BASE}?lang=ru&role=akimat&view=nura`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
  await page.waitForTimeout(800);
  await page.evaluate(() => {
    const raf = window.requestAnimationFrame.bind(window);
    window.requestAnimationFrame = (cb) => raf((t) => cb(t - 50));   // метка кадра на 50 мс раньше старта перекраски
    const map = window.__map, set = map.setFeatureState.bind(map);
    window.__colors = [];
    map.setFeatureState = (f, st) => { if (st && st.color !== undefined) window.__colors.push([f.id, st.color]); return set(f, st); };
  });
  fresh = true;
  await page.evaluate(() => window.dispatchEvent(new CustomEvent("birge:complaint", { detail: { type: "status" } })));
  await page.waitForTimeout(2000);
  const r = await page.evaluate(() => ({ colors: window.__colors, items: window.__heat.state().status }));
  const problems = [];
  const bad = r.colors.filter(([, c]) => !okColor(c));
  if (r.colors.length < 10) problems.push("перекраска не запустилась: записей цвета " + r.colors.length);
  if (bad.length) problems.push("неправильный цвет в feature-state: " + bad.slice(0, 3).map(([id, c]) => id + " → " + c).join(", ") + (bad.length > 3 ? " … всего " + bad.length : ""));
  const parse = warns.filter((w) => /Could not parse color/i.test(w));
  if (parse.length) problems.push("консоль: " + parse[0] + (parse.length > 1 ? " (×" + parse.length + ")" : ""));
  console.log((problems.length ? "FAIL" : "PASS") + " first-frame-before-start · записей цвета " + r.colors.length + (problems.length ? " · " + problems.join("; ") : ""));
  await browser.close();
  process.exit(problems.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
