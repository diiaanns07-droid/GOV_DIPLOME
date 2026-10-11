/*
 * R11 · шаги 6–7 DEMO_SCRIPT (FINAL-2): житель «Мен де» у «Хан Шатыр» → акимат «Жұмысқа алу» → «Түзетілді деп
 * белгілеу» (если открылась форма R09 — одна строка «Не істелді» и «Тұрғындарға хабарлау») → житель «Менің
 * өтініштерім»: «Қызмет түзетілгенін хабарлады» и «Сіздің тексеруіңізді күтуде» → «Иә, түзетілді» → «Тұрғындар тексерді».
 * Одно устройство (localStorage) на весь путь; кадры step67-*.png. Пишет в базу стенда (тестовую) и «тратит» демо:
 * после «Иә, түзетілді» у «Хан Шатыр» нет открытых жалоб, шаг «Мен де» больше не появится — один прогон на свежую базу
 * (как и показ: перед демо — свежий засев). По умолчанию 1366 kk; COMBO=375x812:ru — другой размер и язык.
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/demo_step67_check.cjs http://127.0.0.1:<порт>/ <папка> <файл-пароля>
 */
"use strict";
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const [BASE, OUT, PWFILE] = process.argv.slice(2);
const PASSWORD = fs.readFileSync(PWFILE, "utf8").trim();
const T = { kk: { metoo: "Мен де", yes: "Иә, түзетілді", reported: "Қызмет түзетілгенін хабарлады", verified: "Тұрғындар тексерді", wait: "Сіздің тексеруіңізді күтуде", send: "Тұрғындарға хабарлау" },
            ru: { metoo: "Я тоже", yes: "Да, исправлено", reported: "Служба сообщила об устранении", verified: "Проверено жителями", wait: "Ждут вашей проверки", send: "Сообщить жителям" } };
const ready = (p) => p.waitForFunction(() => window.CivicShell && window.CivicShell.heat && window.CivicShell.heat.state && window.CivicShell.heat.state().status === "ready", null, { timeout: 45000 });
const text = (p) => p.evaluate(() => document.body.innerText.replace(/\s+/g, " "));

(async () => {
  const b = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  let bad = 0;
  const [size, comboLang] = (process.env.COMBO || "1366x768:kk").split(":");
  for (const [w, h, lang] of [[...size.split("x").map(Number), comboLang]]) {
    const L = T[lang], res = { w, lang };
    const ctx = await b.newContext({ viewport: { width: w, height: h } }); const p = await ctx.newPage();
    await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
    await p.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); if (!sessionStorage.getItem("r11")) { localStorage.setItem("birge.mode", "resident"); sessionStorage.setItem("r11", "1"); } } catch (e) {} }, lang);
    try {
      await p.goto(BASE); await ready(p); await p.waitForTimeout(1200);
      res.stage = "1-2";
      // Шаги 1–2: жалоба у «Хан Шатыр» → «Мен де» (как demo_step2_check.cjs)
      const target = await p.evaluate(async () => { const d = await (await fetch("/api/civic/v2/heat?days=30&zoom=16")).json(); const it = (d.data || d).items.find((x) => /Хан Шатыр/.test(x.target.label_ru || "")); return it && { anchor: it.anchor, kind: it.target.kind, id: it.target.id }; });
      if (!(await p.isVisible(".bc-fab"))) await p.keyboard.press("Escape");
      await p.click(".bc-fab"); await p.waitForSelector(".bc-panel[data-step='2']"); await p.waitForTimeout(500);
      const xy = await p.evaluate((a) => { map.jumpTo({ center: a, zoom: 17 }); const c = map.getCanvas().getBoundingClientRect(), r = map.project(a);
        const want = innerWidth < 1024 ? { x: innerWidth / 2, y: 240 } : { x: 400, y: 380 }; map.panBy([r.x + c.left - want.x, r.y + c.top - want.y], { animate: false });
        const r2 = map.project(a); return { x: c.left + r2.x, y: c.top + r2.y }; }, target.anchor);
      await p.waitForTimeout(600); await p.mouse.click(xy.x, xy.y); await p.waitForTimeout(1500);
      const khan = await p.$("xpath=//button[contains(@class,'bc-option')][.//*[contains(text(),'Хан Шатыр')]]");
      if (khan) await khan.click(); else await p.click(".bc-option--first");
      await p.waitForSelector(".bc-panel[data-step='3']", { timeout: 8000 });
      await p.fill("#bc-text", "Аялдамада жарық жоқ, вечером на остановке темно"); await p.waitForTimeout(3500);
      await p.click(".bc-send"); await p.waitForTimeout(2500);
      await p.click(`.bc-panel button:has-text("${L.metoo}")`); await p.waitForTimeout(2000);
      res.metoo = (await text(p)).includes(lang === "kk" ? "есепке алынды" : "учтён");
      await p.keyboard.press("Escape"); await p.waitForTimeout(600);
      res.stage = "6";
      // Шаг 6: акимат — «Жұмысқа алу» → «Түзетілді деп белгілеу» (+ форма R09, если есть)
      await p.evaluate((pw) => window.CivicShell.api.login("operator", pw), PASSWORD);
      await p.evaluate(() => { const b = document.querySelector("#birge-header [data-mode=akimat]"); if (b) b.click(); }); await p.waitForTimeout(1200);
      await p.evaluate((t) => window.CivicShell.heat.focusTarget(t.kind, t.id), target);
      await p.waitForSelector("[data-act='take'], [data-act='fixed']", { timeout: 10000 });
      if (await p.$("[data-act='take']")) { await p.click("[data-act='take']"); await p.waitForTimeout(1200); }
      await p.click("[data-act='fixed']"); await p.waitForTimeout(1500);
      const form = await p.$("textarea[name='what_done'], input[name='what_done'], [data-field='what_done'] textarea, [data-field='what_done'] input");
      res.fixForm = !!form;
      if (form) { await form.fill(lang === "kk" ? "Шам ауыстырылды" : "Заменили лампу"); await p.click(`button:has-text("${L.send}")`); await p.waitForTimeout(1500); }
      await p.screenshot({ path: path.join(OUT, `step67-${w}-${lang}-1-fixed.png`) });
      res.stage = "7";
      // Шаг 7: житель — «Менің өтініштерім» → «Иә, түзетілді»
      await p.keyboard.press("Escape");
      await p.evaluate(() => { const b = document.querySelector("#birge-header [data-mode=resident]"); if (b) b.click(); }); await p.waitForTimeout(1200);
      res.badge = await p.evaluate(() => { const m = document.querySelector("#birge-header [data-action=mine]"); return m ? (m.getAttribute("aria-label") || m.textContent).replace(/\s+/g, " ").trim().slice(0, 60) : null; });
      await p.evaluate(() => { const b = document.querySelector("#birge-header [data-action=mine]"); if (b) b.click(); }); await p.waitForTimeout(2500);
      const before = await text(p);
      res.reported = before.includes(L.reported); res.waitBlock = before.includes(L.wait);
      await p.screenshot({ path: path.join(OUT, `step67-${w}-${lang}-2-verify.png`) });
      res.stage = "7-yes";
      await p.click(`button:has-text("${L.yes}")`); await p.waitForTimeout(2500);
      res.verified = (await text(p)).includes(L.verified);
      await p.screenshot({ path: path.join(OUT, `step67-${w}-${lang}-3-verified.png`) });
    } catch (e) { res.error = e.message.split("\n")[0].slice(0, 160); await p.screenshot({ path: path.join(OUT, `step67-${w}-${lang}-FAIL.png`) }).catch(() => {}); }
    const ok = res.metoo && res.reported && res.waitBlock && res.verified && !res.error;
    if (!ok) bad++;
    console.log((ok ? "PASS " : "FAIL ") + JSON.stringify(res));
    await ctx.close();
  }
  await b.close();
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
