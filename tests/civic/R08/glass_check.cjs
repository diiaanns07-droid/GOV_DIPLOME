/*
 * R08 · экраны R08 на стекле (R11 GLASS.md §4 R08): «Картина дня», «Рядом», «Службы» внутри листа раздела R01.
 *
 *   Сборка R01 + ui-kit R11 с .bk-glass (claude/r14-R11 ≥ 7117132b), CIVIC_DEMO=1.
 *   NODE_PATH=$(npm root -g) node tests/civic/R08/glass_check.cjs http://127.0.0.1:8634 [папка_кадров]
 *
 * Если R01 ещё не поставил стекло на лист раздела (GLASS.md §4 R01 №6), проверка ставит его сама — класс bk-glass на
 * #birge-day / #birge-screen и фон стекла ui-kit вместо белого фона листа — и пишет об этом в итоге (simulated: true).
 * Проверяет, 1366/375 × ru/kk:
 *   - контраст каждого видимого текста R08 в худшем случае — под стеклом чёрная карта: фон = стекло 80 % над #000,
 *     сверху — свои фоны предков текста (подложки .bk-card и т. п.); норма 4,5:1 (крупный текст — 3:1);
 *   - внутри R08 нет второго стекла (backdrop-filter) — стекло только у листа R01 и у компактной полосы раздела
 *     «Картины дня» (.akim__bar-btn, появляется при прокрутке — GLASS.md §2 «шапка»);
 *   - «Службы» — форма: непрозрачный белый контейнер (GLASS.md G-1, R11 марафон §11.5);
 *   - числа «Картины дня» без подложки (CLEAN_PASS п. 3), поля даты/района/выбора службы — непрозрачные;
 *   - в печати лист белый (ui-kit @media print).
 * Итог — glass_check.json в папке кадров.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8634").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-14-results/R08/screens/glass");
fs.mkdirSync(OUT, { recursive: true });
const results = [];
let simulated = false;
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: ok ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail != null ? " — " + JSON.stringify(detail).slice(0, 500) : ""));
}

// Ставит стекло на лист раздела, если R01 его ещё не поставил (как в GLASS.md §4 R01 №6).
async function ensureGlass(page, sheetSel) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return { found: false };
    const had = el.classList.contains("bk-glass");
    if (!had) {
      el.classList.add("bk-glass");
      if (!document.getElementById("r08-glass-sim")) {
        const st = document.createElement("style");
        st.id = "r08-glass-sim";
        st.textContent = ".birge-day.bk-glass{background-color:var(--glass-panel);background-image:var(--glass-highlight);border-radius:var(--r-glass)}";
        document.head.appendChild(st);
      }
    }
    const cs = getComputedStyle(el);
    return { found: true, had, bg: cs.backgroundColor, filter: cs.backdropFilter || cs.webkitBackdropFilter || "" };
  }, sheetSel);
}

// Худший контраст текста внутри root: стекло листа над чёрной картой + свои фоны предков.
async function contrast(page, rootSel, sheetSel) {
  return page.evaluate(([rootSel, sheetSel]) => {
    const parse = (c) => {
      const m = c.match(/rgba?\(([^)]+)\)/);
      if (!m) return [0, 0, 0, 0];
      const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
      return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    };
    const over = (top, bot) => [0, 1, 2].map((i) => top[i] * top[3] + bot[i] * (1 - top[3])).concat(1);
    const lum = (c) => {
      const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
      return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
    };
    const ratio = (a, b) => { const la = lum(a), lb = lum(b); return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05); };
    const sheet = document.querySelector(sheetSel), root = document.querySelector(rootSel);
    if (!sheet || !root) return { error: "нет листа или корня" };
    const sheetBg = parse(getComputedStyle(sheet).backgroundColor);
    const out = { checked: 0, worst: null, fails: [], nested: [] };
    for (const el of root.querySelectorAll("*")) {
      if (!el.getClientRects().length) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === "hidden" || cs.display === "none") continue;
      // Разрешено одно: компактная полоса раздела «Картины дня» (.akim__bar-btn — шапка раздела, GLASS.md §2 «шапка»).
      if (((cs.backdropFilter && cs.backdropFilter !== "none") || (cs.webkitBackdropFilter && cs.webkitBackdropFilter !== "none"))
        && !el.classList.contains("akim__bar-btn"))
        out.nested.push(el.className.toString().slice(0, 40));
      const own = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
      if (!own) continue;
      const r = el.getBoundingClientRect();
      if (r.width <= 1 && r.height <= 1) continue; // только для экранного диктора
      // фон: чёрная карта → стекло листа → фоны предков от листа к тексту
      const chain = [];
      for (let p = el; p && p !== sheet; p = p.parentElement) chain.push(parse(getComputedStyle(p).backgroundColor));
      let bg = over(sheetBg, [0, 0, 0, 1]);
      for (const c of chain.reverse()) if (c[3] > 0) bg = over(c, bg);
      const fg = over(parse(cs.color), bg);
      const k = ratio(fg, bg);
      const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 600;
      const need = size >= 24 || (bold && size >= 18.66) ? 3 : 4.5;
      out.checked++;
      const item = { k: Math.round(k * 100) / 100, need, cls: el.className.toString().slice(0, 40), text: el.textContent.trim().slice(0, 30) };
      if (!out.worst || k / need < out.worst.k / out.worst.need) out.worst = item;
      if (k < need) out.fails.push(item);
    }
    return out;
  }, [rootSel, sheetSel]);
}

async function open(browser, { w, h, lang, mode, hash }) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript(([l, m]) => {
    try { localStorage.setItem("birge.lang", l); localStorage.setItem("birge.mode", m); } catch (e) { /* */ }
  }, [lang, mode]);
  await page.goto(BASE + "/" + hash);
  return { ctx, page, errors };
}

(async () => {
  const browser = await chromium.launch();
  const screens = [
    { name: "day", mode: "akimat", hash: "#day", sheet: "#birge-day", root: "#birge-day-root", ready: "#birge-day-root.akim[data-state=ok]" },
    { name: "nearby", mode: "resident", hash: "#nearby", sheet: "#birge-screen", root: "#birge-screen-root", ready: "#birge-screen-root.nb[data-state=ok]" },
    { name: "services", mode: "akimat", hash: "#services", sheet: "#birge-screen", root: "#birge-screen-root", ready: "#birge-screen-root.svc[data-state=ok]" },
  ];
  for (const s of screens) {
    for (const [w, h] of [[1366, 768], [375, 812]]) {
      for (const lang of ["ru", "kk"]) {
        if (s.name === "services" && (w === 375 || lang === "kk") && !(w === 375 && lang === "kk")) continue; // «Службы»: 1366-ru и 375-kk
        const tag = `${s.name}-${w}-${lang}`;
        const { ctx, page, errors } = await open(browser, { w, h, lang, mode: s.mode, hash: s.hash });
        try {
          await page.waitForSelector(s.ready, { timeout: 60000 });
        } catch (e) {
          check(`${tag}: экран открылся`, false, "нет " + s.ready + " — " + e.message.slice(0, 80));
          await ctx.close();
          continue;
        }
        const g = await ensureGlass(page, s.sheet);
        if (!g.had) simulated = true;
        await page.waitForTimeout(700);
        check(`${tag}: лист раздела — стекло (${g.had ? "R01" : "поставлено проверкой"}: фон ${g.bg}, ${g.filter || "без размытия"})`,
          g.found && /blur/.test(g.filter) && /rgba\(255, 255, 255, 0\.[78]/.test(g.bg), g);
        await page.screenshot({ path: path.join(OUT, `${tag}.png`) });
        const c = await contrast(page, s.root, s.sheet);
        check(`${tag}: текст R08 на стекле над чёрной картой ≥ 4,5:1 (крупный ≥ 3:1) — проверено ${c.checked}, худший ${c.worst && c.worst.k}`,
          !c.error && c.checked > 20 && c.fails.length === 0, c.error || c.fails.slice(0, 5));
        check(`${tag}: внутри R08 нет второго стекла (backdrop-filter только у листа)`, (c.nested || []).length === 0, c.nested);
        if (s.name === "day") {
          const d = await page.evaluate(() => ({
            kpi: Array.from(document.querySelectorAll("#birge-day-root .akim-kpi")).map((k) => getComputedStyle(k).backgroundColor),
            fields: Array.from(document.querySelectorAll("#birge-day-root .akim__field input, #birge-day-root .akim__field select")).map((f) => getComputedStyle(f).backgroundColor),
          }));
          check(`${tag}: числа без подложки, поля даты и района непрозрачные`,
            d.kpi.length === 4 && d.kpi.every((b) => /rgba\(0, 0, 0, 0\)|transparent/.test(b)) && d.fields.length === 2 && d.fields.every((b) => /^rgb\(/.test(b)), d);
          if (w === 1366 && lang === "ru") {
            await page.emulateMedia({ media: "print" });
            const pr = await page.evaluate(() => getComputedStyle(document.querySelector("#birge-day")).backgroundColor);
            check(`${tag}: в печати лист белый`, pr === "rgb(255, 255, 255)", pr);
            await page.emulateMedia({ media: "screen" });
          }
        } else {
          const f = await page.evaluate((root) => Array.from(document.querySelectorAll(root + " select")).filter((e) => e.getClientRects().length)
            .map((e) => getComputedStyle(e).backgroundColor), s.root);
          check(`${tag}: поля выбора непрозрачные`, f.length >= 1 && f.every((b) => /^rgb\(/.test(b)), f.slice(0, 3));
          if (s.name === "services") {
            const bg = await page.evaluate(() => getComputedStyle(document.querySelector("#birge-screen-root > .svc, #birge-screen-root.svc")).backgroundColor);
            check(`${tag}: «Службы» — форма в непрозрачном белом контейнере (не стекло)`, bg === "rgb(255, 255, 255)", bg);
          }
        }
        check(`${tag}: без ошибок JS`, errors.length === 0, errors.slice(0, 3));
        await ctx.close();
      }
    }
  }
  await browser.close();
  const failed = results.filter((r) => r.status === "FAIL").length;
  fs.writeFileSync(path.join(OUT, "glass_check.json"), JSON.stringify({ base: BASE, simulated_r01_glass: simulated, total: results.length, failed, results }, null, 1));
  console.log(`\n${results.length - failed}/${results.length} PASS` + (simulated ? " (стекло листа поставлено проверкой — R01 №6 ещё не в сборке)" : ""));
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
