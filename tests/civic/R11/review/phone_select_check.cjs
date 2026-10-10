/*
 * R11 · телефон: выбранное место не прячется под шторкой карточки (R01 night 7b, r12_city 360×800).
 * Акимат → «Шағымы көп орындар» → первые места списка по очереди → через 2,5 с значок выбранного места
 * (.r07-badge--selected) должен быть в свободной части карты: ниже шапки и выше верхнего края шторки (#civic-panel).
 * и ничем не закрыт сверху (elementFromPoint в центре значка — сам значок).
 * Пункт без значка (район «Нұра · 27 орында шағым бар») — пропуск, не ошибка.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/phone_select_check.cjs http://127.0.0.1:8626/ [папка-для-снимков]
 */
"use strict";
const path = require("path");
const { chromium } = require("playwright");
const [BASE, OUT] = process.argv.slice(2);
const SIZES = [[360, 800], [375, 667]];
const N = Number(process.env.N || 4);

(async () => {
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  let bad = 0;
  for (const [w, h] of SIZES) for (const lang of ["kk", "ru"]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", "akimat"); } catch (e) {} }, lang);
    await p.goto(BASE);
    await p.waitForFunction(() => window.CivicShell && typeof mapReady !== "undefined" && mapReady && window.CivicShell.heat
      && window.CivicShell.heat.state && window.CivicShell.heat.state().status === "ready", null, { timeout: 45000 });
    await p.waitForTimeout(1200);
    const res = [];
    for (let i = 0; i < N; i++) {
      await p.keyboard.press("Escape"); await p.waitForTimeout(700);
      const items = await p.$$(".r07-item");
      if (!items[i]) { res.push({ i, err: "нет пункта списка" }); break; }
      const title = (await items[i].textContent()).trim().slice(0, 40);
      await items[i].click();
      await p.waitForTimeout(2500);
      const r = await p.evaluate(() => {
        const vis = (el) => el && el.getClientRects().length && getComputedStyle(el).visibility !== "hidden" ? el.getBoundingClientRect() : null;
        const badge = vis(document.querySelector(".r07-badge--selected"));
        const panel = vis(document.getElementById("civic-panel")) || vis(document.querySelector(".civic-panel"));
        const top = vis(document.querySelector(".topbar")) || vis(document.querySelector("#birge-header"));
        if (!badge) return { skip: "без значка (район или квартал — у него нет точки)", ok: true };
        const cx = Math.round(badge.left + badge.width / 2), cy = Math.round(badge.top + badge.height / 2);
        // Сверху над центром значка должен быть сам значок, а не кнопка поверх карты («Не салайық?», R11 ночь, круг 16).
        const over = document.elementFromPoint(cx, cy), el = document.querySelector(".r07-badge--selected");
        const covered = over && !el.contains(over) ? (over.className || over.tagName) + " «" + over.textContent.trim().slice(0, 20) + "»" : null;
        return { cy, sheetTop: panel ? Math.round(panel.top) : null, headBottom: top ? Math.round(top.bottom) : 0, covered,
          ok: (!panel || cy < panel.top) && cy > (top ? top.bottom : 0) && !covered };
      });
      if (!r.ok) bad++;
      res.push({ i, title, ...r });
      if (OUT && !r.ok) await p.screenshot({ path: path.join(OUT, `sel-${w}x${h}-${lang}-${i}.png`) });
    }
    console.log(`${w}×${h} ${lang}`, JSON.stringify(res));
    await ctx.close();
  }
  console.log(bad ? `ИТОГ: выбранное место закрыто (шторкой или кнопкой) — ${bad}` : "ИТОГ: выбранное место всегда видно над шторкой и ничем не закрыто");
  await browser.close();
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
