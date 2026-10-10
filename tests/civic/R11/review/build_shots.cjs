/*
 * R11 · UX-разбор сборки R01 (B1/B2/FINAL) по сценарию демо (DEMO_SCRIPT.md R01): акимат → карта жалоб → карточка →
 * «Картина дня» → житель → «Сообщить о проблеме» (шаги 2, 3, 5) → «Мои обращения» → «Взять в работу» → «Исправлено».
 * Сервер сборки поднимается заранее (как в tests/civic/R01/browser/r14_b1.cjs: CIVIC_DEMO=1, временная база, сотрудник):
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/build_shots.cjs http://127.0.0.1:8611 <папка> <метка> <файл-пароля>
 * Пароль сотрудника читается из файла и нигде не печатается.
 */
"use strict";
const fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const { measure, brief, consoleCollector } = require("./measure.cjs");
const [BASE, OUT, TAG, PWFILE] = process.argv.slice(2);
const PASSWORD = PWFILE ? fs.readFileSync(PWFILE, "utf8").trim() : null;
const NURA = [71.4148, 51.1131];
fs.mkdirSync(OUT, { recursive: true });

const ready = (p) => p.waitForFunction(() => window.CivicShell && window.CivicShell.mode === "civic" && typeof mapReady !== "undefined" && mapReady
  && window.CivicShell.heat && window.CivicShell.heat.state && window.CivicShell.heat.state().status === "ready", null, { timeout: 45000 }).then(() => p.waitForTimeout(900));
const clickHidden = (p, sel) => p.evaluate((s) => { const el = document.querySelector(s); if (!el) throw new Error("нет " + s); el.click(); }, sel);
// Клик по карте в видимой части (не под шторкой мастера, панелью «Территория», баннером подложки) и мимо значков
// тепловой карты: значок в режиме выбора места перехватывает нажатие (ошибка сборки, UX_REVIEW день 4).
// Свободную точку ищем по elementFromPoint: самый длинный вертикальный отрезок, где сверху лежит сам canvas карты.
async function clickMapAt(p, ll) {
  const want = await p.evaluate(() => {
    const panel = document.querySelector(".bc-panel:not([hidden])");
    const pr = panel && panel.getBoundingClientRect(), phone = pr && pr.width > innerWidth * 0.9;
    const bottom = phone ? pr.top : innerHeight, right = pr && !phone ? pr.left : innerWidth; // телефон — шторка снизу, ПК — панель справа
    let best = null, free = 0, all = 0; // доля карты над мастером, где сверху сам canvas (сетка 12 px)
    for (let y = 40; y < bottom - 6; y += 12) for (let x = 6; x < right - 6; x += 12) {
      const e = document.elementFromPoint(x, y); all++; if (e && e.classList.contains("maplibregl-canvas")) free++;
    }
    for (const fx of [0.5, 0.7, 0.3]) { // только средняя часть: щель у края экрана — не место для пальца
      const x = Math.round(right * fx); let run = null;
      for (let y = 40; y < bottom - 6; y += 6) {
        const e = document.elementFromPoint(x, y);
        if (e && e.classList.contains("maplibregl-canvas")) { run = run || { x, y0: y }; run.y1 = y; if (!best || run.y1 - run.y0 > best.y1 - best.y0) best = { ...run }; }
        else run = null;
      }
    }
    return best && { x: best.x, y: Math.round((best.y0 + best.y1) / 2), h: best.y1 - best.y0, share: Math.round(100 * free / Math.max(1, all)), top: Math.round(bottom) };
  });
  if (!want || want.h < 24) throw new Error("свободной карты над мастером нет (" + (want ? want.h + " px" : "0 px") + ")");
  for (let k = 0; k < 6; k++) {
    const q = [ll[0] + k * 0.0012, ll[1]];
    const xy = await p.evaluate(({ q, want }) => {
      const c = map.getCanvas().getBoundingClientRect();
      map.jumpTo({ center: q, zoom: 15 });
      const r = map.project(q);
      map.panBy([r.x + c.left - want.x, r.y + c.top - want.y], { animate: false });
      const r2 = map.project(q);
      return { x: c.left + r2.x, y: c.top + r2.y };
    }, { q, want });
    await p.waitForTimeout(400);
    const free = await p.evaluate(({ x, y }) => { const e = document.elementFromPoint(x, y); return !!(e && e.classList.contains("maplibregl-canvas")); }, xy);
    if (!free) continue;
    await p.mouse.click(xy.x, xy.y);
    return want;
  }
  throw new Error("не нашли свободную точку карты для клика");
}

(async () => {
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
  const report = {};
  for (const size of (process.env.SIZES || "1366,375").split(",").map(Number)) { // SIZES=375 — только телефон
    for (const lang of (process.env.LANGS || "ru,kk").split(",")) {
      const ctx = await browser.newContext({ viewport: size === 1366 ? { width: 1366, height: 768 } : { width: 375, height: 812 } });
      const p = await ctx.newPage();
      const logs = consoleCollector(p);
      await p.route(/^https?:\/\/(?!127\.0\.0\.1)/, (r) => r.abort());
      await p.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); if (!sessionStorage.getItem("r11")) { localStorage.setItem("birge.mode", "akimat"); sessionStorage.setItem("r11", "1"); } } catch (e) {} }, lang);
      const shot = async (name, full) => {
        await p.waitForTimeout(500);
        const tag = `${TAG}-${name}-${size}-${lang}`;
        await p.screenshot({ path: path.join(OUT, `b-${tag}.png`), fullPage: !!full });
        const m = await measure(p, null);
        report[tag] = { m, brief: brief(m), console: [...new Set(logs.splice(0))].slice(0, 8) };
      };
      const step = async (name, fn, full) => { try { await fn(); await shot(name, full); } catch (e) {
        await p.screenshot({ path: path.join(OUT, `b-${TAG}-${name}-${size}-${lang}-FAIL.png`) }).catch(() => {});
        const why = e.message.split("\n").filter((l) => /intercepts|not visible|not stable|disabled|outside|НЕ |«/.test(l)).slice(0, 2).join(" | ");
        report[`${TAG}-${name}-${size}-${lang}`] = { brief: "НЕ ПРОШЛО: " + e.message.split("\n")[0].slice(0, 160) + (why ? " · " + why.slice(0, 200) : ""), console: [...new Set(logs.splice(0))].slice(0, 8) }; } };
      await p.goto(BASE + "/");
      try { await ready(p); } catch (e) { logs.push("не дождались готовности карты"); }
      await step("1-akimat-map", async () => {});
      await step("2-akimat-card", async () => { await p.click(".r07-item"); await p.waitForTimeout(1200); });
      await step("3-day", async () => { await clickHidden(p, "#birge-header [data-section=day]"); await p.waitForSelector("#birge-day .akim-hot__item", { timeout: 15000 }); }, true);
      await step("4-hot-to-map", async () => { await p.click("#birge-day .akim-hot__item"); await p.waitForTimeout(1200); });
      await step("5-resident", async () => { await clickHidden(p, "#birge-header [data-mode=resident]"); await p.waitForTimeout(1200); });
      await step("6-wizard-place", async () => {
        // С B3 на телефоне кнопка скрыта, пока открыта карточка места (у карточки своя «Я тоже») — закрываем карточку.
        if (!(await p.isVisible(".bc-fab"))) { await p.keyboard.press("Escape"); await p.waitForTimeout(700); }
        await p.click(".bc-fab"); await p.waitForSelector(".bc-panel[data-step='2']", { timeout: 8000 }); await p.waitForTimeout(500);
        const w = await clickMapAt(p, NURA); logs.push(`R11: над мастером (до y=${w.top}) свободно ${w.share}% карты, самый длинный отрезок ${w.h} px`); await p.waitForSelector(".bc-panel[data-step='3'], .bc-option", { timeout: 10000 }); await p.waitForTimeout(600);
      });
      await step("7-wizard-text", async () => {
        // Житель берёт первую предложенную цель («Это здесь?»); без целей (B1: /targets 503) — «Другое место».
        if (await p.$(".bc-panel[data-step='2'] .bc-option--first")) { logs.push("R11: место — " + (await p.textContent(".bc-option--first .bc-option__label"))); await p.click(".bc-option--first"); }
        else if (await p.$(".bc-panel[data-step='2'] .bc-option.bk-btn--ghost")) { logs.push("R11: место — примерное"); await p.click(".bc-option.bk-btn--ghost"); }
        await p.waitForSelector(".bc-panel[data-step='3']", { timeout: 10000 });
        await p.fill("#bc-text", lang === "kk" ? "Аялдамада кешке қараңғы, шамдар жанбайды" : "На остановке вечером темно, не горят фонари");
        await p.waitForTimeout(3200); // ML нет — через 2,5 с открывается сетка категорий
      });
      await step("8-wizard-done", async () => {
        // Категория «Освещение» (5-я): сетка R09 B1 — .bc-grid, с B2 — .bk-catgrid ui-kit.
        if (await p.$(".bk-catgrid")) await p.click(".bk-catgrid > button:nth-child(5)");
        else if (await p.$(".bc-grid")) await p.click(".bc-grid__chip:nth-child(5)");
        await p.click(".bc-send");
        await p.waitForSelector(".bc-panel[data-step='4'], .bc-panel[data-step='5']", { timeout: 15000 });
        if (await p.$(".bc-panel[data-step='4']")) await p.click(".bc-different");
        await p.waitForSelector(".bc-panel[data-step='5']", { timeout: 15000 });
      });
      await step("9-mine", async () => { await p.keyboard.press("Escape"); await clickHidden(p, "#birge-header [data-action=mine]"); await p.waitForSelector(".bc-mine__card", { timeout: 8000 }); });
      if (size === 1366 && PASSWORD) {
        await step("10-fixed", async () => {
          await p.keyboard.press("Escape");
          await clickHidden(p, "#birge-header [data-mode=akimat]"); await p.waitForTimeout(800);
          await p.evaluate((pw) => window.CivicShell.api.login("operator", pw), PASSWORD);
          const own = await p.evaluate(async () => { const r = await fetch("/api/civic/v2/complaints/mine", { headers: { "X-Birge-Device": localStorage.getItem("birge.device") || "" } }); const b = await r.json(); const it = (b.data && (b.data.items || b.data)) || []; return it[0] && it[0].target; });
          await p.evaluate((t) => window.CivicShell.heat.focusTarget(t.kind, t.id), own);
          await p.waitForSelector("[data-act='take'], [data-act='fixed']", { timeout: 10000 });
          if (await p.$("[data-act='take']")) { await p.click("[data-act='take']"); await p.waitForTimeout(1200); }
          await p.click("[data-act='fixed']"); await p.waitForTimeout(1500);
        });
      }
      // Шаг 5 демо (с B2): каталог «Что построить?» → сквер → «Поставить» → житель голосует (ноутбук, сотрудник уже вошёл).
      if (size === 1366 && PASSWORD && !process.env.NO3D) {
        await step("11-catalog", async () => {
          await p.keyboard.press("Escape");
          await clickHidden(p, "#birge-header [data-mode=akimat]"); await p.waitForTimeout(900);
          if (!(await p.$(".birge-b3d-toggle"))) throw new Error("нет кнопки «Что построить?»");
          await p.click(".birge-b3d-toggle"); await p.waitForSelector(".b3d-card[data-kind=square]", { timeout: 10000 });
        });
        await step("12-placed", async () => {
          await p.click(".b3d-card[data-kind=square]"); await p.waitForTimeout(500);
          // Место, где проект уже стоит (прошлый прогон на той же базе), R05 честно не даёт занять — сдвигаемся восточнее.
          let st = null;
          for (let k = 0; k < 5; k++) {
            await clickMapAt(p, [71.4185 + k * 0.0016, 51.1150 - k * 0.0006]); await p.waitForSelector("[data-action=place]", { timeout: 8000 });
            await p.waitForTimeout(300);
            st = await p.evaluate(() => { const b = document.querySelector("[data-action=place]");
              return { disabled: b.disabled || b.getAttribute("aria-disabled") === "true", hint: ((document.querySelector(".b3d-dock") || {}).innerText || "").split("\n").slice(0, 3).join(" · ") }; });
            if (!st.disabled) break;
            logs.push("R11: «Поставить» неактивна — " + st.hint.slice(0, 120));
          }
          if (st.disabled) throw new Error("«Поставить» неактивна: " + st.hint.slice(0, 120));
          await p.click("[data-action=place]", { timeout: 8000 }); await p.waitForTimeout(4500);
        });
        await step("13-vote", async () => {
          await clickHidden(p, "#birge-header [data-mode=resident]"); await p.waitForTimeout(1500);
          // Подпись «Проект · 2027» у только что поставленного проекта; на мелком масштабе — точка (b3d-label--dot).
          await p.waitForSelector(".b3d-label", { timeout: 10000 }).catch(() => {});
          const ok = await p.evaluate(() => {
            const labs = [...document.querySelectorAll(".b3d-label:not(.b3d-label--hidden)")].filter((b) => b.getBoundingClientRect().width > 0);
            if (labs.length) { labs[labs.length - 1].click(); return "label"; }
            const h = window.CivicShell && window.CivicShell.build3d, st = h && h.getState && h.getState();
            const list = st && (Array.isArray(st.items) ? st.items : Array.isArray(st.proposals) ? st.proposals : []);
            const it = list && list[list.length - 1];
            if (it) { h.select(it.id); return "select"; }
            return null;
          });
          if (!ok) throw new Error("нет проекта ни на карте, ни в getState()");
          if (ok === "select") logs.push("R11: подписи проекта на карте нет — карточка открыта через select()");
          // Карточка голосования: R05 (data-action=vote-up) или R06 (.r06-vote__btn[data-value="1"]) — в зависимости от сборки.
          const UP = "[data-action=vote-up], .r06-vote__btn[data-value='1']";
          await p.waitForSelector(UP, { timeout: 8000 });
          logs.push("R11: карточка голоса — " + ((await p.$("[data-action=vote-up]")) ? "R05" : "R06"));
          await p.click(UP); await p.waitForTimeout(1200);
        });
      }
      await ctx.close();
    }
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, `b-${TAG}-measure.json`), JSON.stringify(report, null, 1));
  for (const [k, v] of Object.entries(report)) console.log(k.padEnd(30), v.brief, v.console && v.console.length ? " | консоль: " + v.console.join(" ; ").slice(0, 260) : "");
})().catch((e) => { console.error(e); process.exit(1); });
