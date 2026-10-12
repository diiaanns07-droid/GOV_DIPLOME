// круг 4: крайние случаи строки «открывается»: (a) обычный путь — до карточки; (b) перелёт прервали колесом — кольцо
// снимается; (c) запрос цели упал — кольцо снимается, список прежний.
const { chromium } = require("/opt/node-tools/node_modules/playwright");
const BASE = process.argv[2] || "http://127.0.0.1:8614/";
(async () => {
  const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium", args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const res = {};
  for (const mode of (process.argv[3] || "normal,interrupt,target-fails").split(",")) {
    const ctx = await b.newContext({ viewport: { width: 1366, height: 768 } });
    await ctx.addInitScript(() => { try { localStorage.setItem("birge.mode", "akimat"); localStorage.setItem("birge.lang", "ru"); } catch (e) {} });
    const p = await ctx.newPage();
    const errs = []; p.on("pageerror", (e) => errs.push(String(e).slice(0, 120)));
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    if (mode === "target-fails") await p.route(/\/heat\/target/, (r) => r.fulfill({ status: 502, contentType: "application/json", body: "{}" }));
    if (mode === "interrupt") await p.route(/\/heat\/target/, async (r) => { await new Promise((x) => setTimeout(x, 300)); r.continue().catch(() => {}); });
    await p.goto(BASE, { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => window.CivicShell?.heat?.state?.().status === "ready", null, { timeout: 45000 });
    await p.waitForTimeout(2500);
    await p.evaluate(() => {
      window.__log = []; const t0 = performance.now();
      const snap = () => { const busy = document.querySelectorAll(".r07-item--busy").length; const v = document.querySelector(".r07-card") ? "card" : "list";
        const k = busy + v; if (k !== window.__k) { window.__k = k; window.__log.push([Math.round(performance.now() - t0), busy, v]); } };
      new MutationObserver(snap).observe(document.getElementById("birge-heat-root"), { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
      snap();
      document.querySelector(".r07-hot .r07-item").click();
    });
    if (mode === "interrupt") {
      // как жест пользователя (у события есть originalEvent): перелёт прерывается сдвигом карты
      const moving = await p.waitForFunction(() => map.isMoving(), null, { timeout: 15000, polling: 20 }).then(() => true).catch(() => false);
      await p.evaluate(() => map.panBy([160, 0], { duration: 300 }, { originalEvent: new Event("pointermove") }));
      console.log("  перелёт шёл:", moving);
    }
    await p.waitForTimeout(mode === "normal" ? 12000 : 9000);
    const fin = await p.evaluate(() => ({ busy: document.querySelectorAll(".r07-item--busy").length, card: !!document.querySelector(".r07-card"), zoom: Math.round(map.getZoom() * 10) / 10, mode: window.CivicShell.heat.state().mode }));
    res[mode] = { log: await p.evaluate(() => window.__log), fin, errs };
    console.log(mode, JSON.stringify(res[mode]));
    await ctx.close();
  }
  await b.close();
})();
