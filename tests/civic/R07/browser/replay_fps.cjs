// R07 раунд 15: плавность «Хроники города» при 1 000 целей (VISUAL_BRIEF п. 1: 60 к/с на ноутбуке).
// Стенд: python -m ui.civic_heat.devserver --world city1000 --port 8618
// Запуск: NODE_PATH=$(npm root -g) node tests/civic/R07/browser/replay_fps.cjs [http://127.0.0.1:8618]
// Печатает JSON: для обзора города (районы) и для мест (масштаб 12,6 и 14) — fps и p95 кадра всей страницы, сколько
// мс кадра тратит код хроники (tween_ms_per_frame) и смена дня (day_switch_ms), сколько целей. Для сравнения — fps
// самой карты при перелёте (easeTo) без хроники: в облаке (программный WebGL) это 11–12 к/с, на ноутбуке ~60.
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8618").replace(/\/$/, "");
(async () => {
  const browser = await chromium.launch();
  const out = { base: BASE, ua: null, runs: [] };
  for (const [label, z] of [["город (районы)", ""], ["места, масштаб 12,6", "12.6"], ["места, масштаб 14", "14"]]) {
    const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    out.ua = out.ua || (await page.evaluate(() => navigator.userAgent));
    const errs = [];
    page.on("pageerror", (e) => errs.push(e.message));
    await page.goto(`${BASE}/civic/heat/demo.html?view=city${z ? "&z=" + z : ""}&lang=ru`, { waitUntil: "load" });
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.waitForTimeout(800);
    // fps самой карты при перелёте — та же машина, тот же браузер
    const mapFps = await page.evaluate(() => new Promise((res) => {
      const m = window.__map, c = m.getCenter(), d = []; let last = performance.now();
      m.easeTo({ center: [c.lng + 0.03, c.lat + 0.01], duration: 2000 });
      const end = last + 1900;
      const f = (t) => { d.push(t - last); last = t; if (t < end) requestAnimationFrame(f); else { const avg = d.reduce((a, b) => a + b, 0) / d.length; res(+(1000 / avg).toFixed(1)); } };
      requestAnimationFrame(f);
    }));
    await page.waitForTimeout(400);
    await page.evaluate(() => window.BirgeReplay.open({ map: window.__map, heat: window.__heat, container: document.getElementById("replay-slot"), days: 7 }));
    await page.waitForFunction(() => window.BirgeReplay.active && window.BirgeReplay.active.state().status === "ready", null, { timeout: 30000 });
    const t0 = Date.now();
    await page.waitForFunction(() => window.BirgeReplay.active.state().ended, null, { timeout: 90000, polling: 250 });
    const stats = await page.evaluate(() => window.BirgeReplay.active.stats());
    const st = await page.evaluate(() => window.__heat.state());
    out.runs.push({ label, played_s: +((Date.now() - t0) / 1000).toFixed(1), map_ease_fps: mapFps, replay_fps: stats.fps, p95_ms: stats.p95_ms,
      worst_ms: stats.worst_ms, tween_ms_per_frame: stats.heat && stats.heat.tween_ms_per_frame, day_switch_ms: stats.heat && stats.heat.day_switch_ms,
      mode: st.mode, items: st.items, errors: errs });
    await page.close();
  }
  // Перемещение карты при 1 000 целей (задача R07 №4): fps перелёта с тепловой картой и без неё (та же страница)
  out.pan = [];
  for (const z of ["12.6", "15"]) {
    const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
    await page.goto(`${BASE}/civic/heat/demo.html?view=city&z=${z}&lang=ru`, { waitUntil: "load" });
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.waitForTimeout(1000);
    const pan = () => page.evaluate(() => new Promise((res) => {
      const m = window.__map, c = m.getCenter(), d = []; let last = performance.now();
      m.easeTo({ center: [c.lng + 0.04, c.lat + 0.015], duration: 2500 });
      const end = last + 2400;
      const f = (t) => { d.push(t - last); last = t; if (t < end) requestAnimationFrame(f); else { d.sort((a, b) => a - b); const avg = d.reduce((a, b) => a + b, 0) / d.length; res({ fps: +(1000 / avg).toFixed(1), p95_ms: +d[Math.floor(d.length * 0.95)].toFixed(1) }); } };
      requestAnimationFrame(f);
    }));
    const markers = await page.evaluate(() => ({ in_dom: document.querySelectorAll(".r07-badge").length, items: window.__heat.state().items }));
    const withHeat = await pan();
    await page.waitForTimeout(500);
    await page.evaluate(() => window.__heat.destroy());
    const without = await pan();
    out.pan.push({ zoom: z, targets: markers.items, badges_in_dom: markers.in_dom, with_heat: withHeat, without_heat: without });
    await page.close();
  }
  console.log(JSON.stringify(out, null, 1));
  await browser.close();
})();
