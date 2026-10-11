/*
 * R11 · первый кадр демо (акимат, «Шағымдар картасы»): значки районов и мест тепловой карты R07 не закрыты
 * легендой, панелями и кнопками поверх карты. Для каждого видимого .r07-badge — elementFromPoint в центре
 * кружка и в центре числа: сверху должен быть сам значок. Самое важное — район с наибольшим числом людей:
 * R07 прячет значок, которому нет свободного места, поэтому «самый большой значок» должен совпадать с первым в списке.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/badges_covered_check.cjs http://127.0.0.1:8627/ [папка-для-снимков]
 */
"use strict";
const path = require("path");
const { chromium } = require("playwright");
const [BASE, OUT] = process.argv.slice(2);
const SIZES = (process.env.SIZES || "1366x768,1280x720,375x812,360x800").split(",").map((s) => s.split("x").map(Number));

(async () => {
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  let bad = 0;
  for (const [w, h] of SIZES) for (const lang of (process.env.LANGS || "kk,ru").split(",")) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", "akimat"); } catch (e) {} }, lang);
    await p.goto(BASE);
    await p.waitForFunction(() => window.CivicShell && typeof mapReady !== "undefined" && mapReady && window.CivicShell.heat
      && window.CivicShell.heat.state && window.CivicShell.heat.state().status === "ready", null, { timeout: 45000 });
    await p.waitForTimeout(2500);
    const r = await p.evaluate(() => {
      const out = [];
      for (const b of document.querySelectorAll(".r07-badge")) {
        if (b.hidden || !b.getClientRects().length || getComputedStyle(b).visibility === "hidden") continue;
        const parts = [b.querySelector(".r07-badge__dot"), b.querySelector(".r07-badge__count")].filter(Boolean);
        const text = b.textContent.trim().replace(/\s+/g, " ");
        const covers = [];
        for (const el of parts.length ? parts : [b]) {
          const q = el.getBoundingClientRect(), x = q.left + q.width / 2, y = q.top + q.height / 2;
          if (!q.width || !q.height) continue; // у мини-значка кружка нет — только число
          if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) { covers.push("за краем экрана"); continue; }
          const top = document.elementFromPoint(x, y);
          // Холст карты лежит под маркерами и закрыть их не может: он «сверху» только там, где у части значка
          // pointer-events: none. Закрывают плашки и кнопки поверх карты и чужие значки.
          if (top && !b.contains(top) && !top.classList.contains("maplibregl-canvas")) {
            const owner = top.closest("[class]");
            covers.push(((owner && owner.className) || top.tagName).toString().split(" ")[0]);
          }
        }
        out.push({ text, kind: b.dataset.kind || "", n: parseInt((text.match(/(\d+)\s*$/) || [])[1] || "0", 10), covered: [...new Set(covers)] });
      }
      return out;
    });
    const covered = r.filter((x) => x.covered.length);
    const max = r.reduce((a, x) => (x.n > (a ? a.n : -1) ? x : a), null);
    // Значок, которого нет совсем (самый «горячий» район), не попадёт в r — сверяем со списком «Шағымы көп орындар».
    const top1 = await p.evaluate(() => { const it = document.querySelector(".r07-item"); return it ? it.textContent.trim().replace(/\s+/g, " ").slice(0, 40) : null; });
    const topName = await p.evaluate(() => { const it = document.querySelector(".r07-item .r07-item__title, .r07-item b, .r07-item strong"); return it ? it.textContent.trim() : null; });
    const lost = !!(max && topName && !max.text.startsWith(topName));
    bad += covered.length + (lost ? 1 : 0);
    if (lost) console.log(`   НЕТ ЗНАЧКА первого в списке: «${topName}» (на карте самый большой — «${max.text}»)`);
    console.log(`${w}×${h} ${lang}: значков ${r.length}, закрыто ${covered.length}` + (covered.length ? " — " + covered.map((x) => `«${x.text}» (${x.covered.join(", ")})`).join("; ") : "")
      + ` · первый в списке: ${top1} · самый большой значок: «${max ? max.text : "—"}»`);
    if (OUT && covered.length) await p.screenshot({ path: path.join(OUT, `badges-${w}x${h}-${lang}.png`) });
    await ctx.close();
  }
  console.log(bad ? `ИТОГ: закрытых значков — ${bad}` : "ИТОГ: все значки видны");
  await browser.close();
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
