/*
 * R08 · браузерная проверка «Ситуационного центра» (раунд 15, Playwright, Chromium).
 *
 *   python tests/civic/R08/demo_server.py --wave2-demo &            # http://127.0.0.1:8508 (соседи — фикстуры R08)
 *   NODE_PATH=$(npm root -g) node tests/civic/R08/board_check.cjs [base_url] [папка_кадров]
 *
 * Проверяет (prompt R08 п. 2, R11 IA_ROUND15 §5.9, VISUAL_BRIEF §4, поправка П1):
 *  1920×1080 и 1366×768, ru и kk — без прокрутки, ни одной обрезанной строки, нет ключей и «{…}», подписи ≥ 18 px и
 *  числа ≥ 48 px на 1920; часы Астаны; полоса кризиса со ссылкой на штаб R17; 5 блоков ленты; смена блока через 15 с
 *  (часы браузера), пауза при наведении, ← →, пробел; вход сотрудника (401), ошибка сети, «нет связи» при обновлении,
 *  без соседей — спокойный блок (иконка ≤ 48 px, текст, одна кнопка); prefers-reduced-motion — без анимаций;
 *  П1 — ровный фон без градиентов, больших картинок нет. Кадры — 1920/1366 × ru/kk, по блоку на кадр.
 * Итог — board_check.json в папке кадров; код выхода 1, если есть FAIL.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8508").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-15-results/R08/screens");
const PAGE = BASE + "/civic/board/";
const API = "**/api/civic/v2/akim/board*";
fs.mkdirSync(OUT, { recursive: true });

const results = [];
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: detail == null ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail != null && !ok ? " — " + JSON.stringify(detail).slice(0, 600) : ""));
}
const KEYLIKE = /\b(board|akim|common|district|service|forecast|status)\.[a-z_]+(\.[a-z_0-9]+)*\b/;

async function open(browser, { width, height, lang, query, reduced, route, clock }) {
  const ctx = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1, reducedMotion: reduced ? "reduce" : "no-preference" });
  await ctx.addInitScript((l) => { try { localStorage.setItem("birge.lang", l); } catch (e) { /* без хранилища */ } }, lang || "ru");
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
  if (clock) await page.clock.install();
  if (route) await page.route(API, route);
  await page.goto(PAGE + (query || "") + ((query || "").includes("?") ? "&" : "?") + "lang=" + (lang || "ru"), { waitUntil: "networkidle" });
  await page.waitForSelector('#board[data-state="ok"], #board[data-state="login"], #board[data-state="error"]', { timeout: 15000 });
  await page.waitForTimeout(400);
  return { ctx, page, errors };
}

(async () => {
  const browser = await chromium.launch();
  // ── 1. Кадры и раскладка: 1920 / 1366 × ru / kk ──
  for (const [width, height] of [[1920, 1080], [1366, 768]]) {
    for (const lang of ["ru", "kk"]) {
      const tag = `${width}-${lang}`;
      const { ctx, page, errors } = await open(browser, { width, height, lang, query: "?rotate=0" });
      const lay = await page.evaluate(() => {
        const d = document.documentElement;
        const cut = [];
        for (const el of document.querySelectorAll("#board *")) {
          if (!el.getClientRects().length || el.closest("svg") || el.classList.contains("sc-sr")) continue; // .sc-sr — только для чтения с экрана
          const own = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
          if (!own) continue;
          const cs = getComputedStyle(el);
          if ((cs.overflow === "hidden" || cs.textOverflow === "ellipsis") && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 2))
            cut.push(el.className + ": " + el.textContent.trim().slice(0, 40));
        }
        // Строки, спрятанные подгонкой (fitAll), — целиком; частично видимых быть не должно.
        const partial = [];
        for (const list of document.querySelectorAll("[data-fit]")) {
          const box = (list.closest("[data-fit-bound]") || list.closest(".sc-panel")).getBoundingClientRect();
          for (const row of list.children) {
            if (row.hidden) continue;
            const r = row.getBoundingClientRect();
            if (r.bottom > box.bottom + 1) partial.push(row.textContent.trim().slice(0, 40));
          }
        }
        const text = document.getElementById("board").innerText;
        return { sh: d.scrollHeight, ch: d.clientHeight, sw: d.scrollWidth, cw: d.clientWidth, cut, partial, text,
          title: document.querySelector(".sc-title").textContent, clock: document.querySelector(".sc-clock__time").textContent,
          stages: Array.from(document.querySelectorAll(".sc-tab[data-block]")).map((b) => b.getAttribute("data-block")),
          crisisHref: (document.querySelector(".sc-crisis__open") || {}).getAttribute ? document.querySelector(".sc-crisis__open").getAttribute("href") : null,
          bg: getComputedStyle(document.body).backgroundImage, bgColor: getComputedStyle(document.body).backgroundColor };
      });
      check(`${tag}: без прокрутки (по вертикали и горизонтали)`, lay.sh <= lay.ch && lay.sw <= lay.cw, { sh: lay.sh, ch: lay.ch, sw: lay.sw, cw: lay.cw });
      check(`${tag}: ни одной обрезанной строки (многоточием или скрытием)`, lay.cut.length === 0, lay.cut.slice(0, 6));
      check(`${tag}: строки списков — целиком (лишние скрыты подгонкой, а не обрезаны)`, lay.partial.length === 0, lay.partial);
      check(`${tag}: нет ключей перевода и «{…}»`, !KEYLIKE.test(lay.text) && !/\{[a-z_]+\}/.test(lay.text), (lay.text.match(KEYLIKE) || [])[0]);
      check(`${tag}: заголовок на своём языке`, lang === "kk" ? /Жағдаяттық орталық/.test(lay.title) : /Ситуационный центр/.test(lay.title), lay.title);
      check(`${tag}: часы Астаны ЧЧ:ММ`, /^\d\d:\d\d$/.test(lay.clock), lay.clock);
      check(`${tag}: 5 блоков ленты (кризис, ведомства, жители, встречи, прогноз)`, lay.stages.join() === "crisis,agencies,together,meetings,forecast", lay.stages);
      check(`${tag}: полоса кризиса ведёт в штаб R17 (#agencies/crisis=…)`, /#agencies\/crisis=/.test(lay.crisisHref || ""), lay.crisisHref);
      check(`${tag}: П1 — ровный тёмный фон без градиентов`, lay.bg === "none" && /rgb\(11, 16, 14\)/.test(lay.bgColor), { bg: lay.bg, c: lay.bgColor });
      if (width === 1920) {
        const sizes = await page.evaluate(() => {
          const small = [];
          for (const el of document.querySelectorAll("#board *")) {
            if (!el.getClientRects().length || el.closest("svg") || el.closest(".sc-foot") || el.classList.contains("sc-credit")) continue;
            if (!Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
            const fs = parseFloat(getComputedStyle(el).fontSize);
            if (fs < 17.9) small.push(el.className + ":" + fs.toFixed(1));
          }
          const nums = Array.from(document.querySelectorAll(".sc-kpi__value")).map((e) => parseFloat(getComputedStyle(e).fontSize));
          return { small, nums };
        });
        check(`${tag}: подписи от 18 px (R11 §5.9)`, sizes.small.length === 0, sizes.small.slice(0, 8));
        check(`${tag}: числа от 48 px`, sizes.nums.every((n) => n >= 48), sizes.nums);
      }
      check(`${tag}: без ошибок в консоли`, errors.length === 0, errors.slice(0, 3));
      // Кадры: по блоку ленты на кадр (кризис — общий вид), для R14 и «книги экранов» R11.
      for (const block of ["crisis", "agencies", "together", "meetings", "forecast"]) {
        await page.evaluate((b) => { document.querySelector(`.sc-tab[data-block="${b}"]`).click(); }, block);
        await page.waitForTimeout(350);
        await page.screenshot({ path: path.join(OUT, `board-${width}-${lang}-${block}.jpg`), type: "jpeg", quality: 82 });
      }
      await ctx.close();
    }
  }

  // ── 2. Лента: смена через 15 с (часы браузера), пауза при наведении, клавиши ──
  {
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru", clock: true });
    const st = () => page.evaluate(() => document.getElementById("board").birgeBoard.state);
    const s0 = await st();
    await page.clock.runFor(15600);
    const s1 = await st();
    check("лента: блок сменился через 15 с", s0.stage === "crisis" && s1.stage === "agencies", { s0: s0.stage, s1: s1.stage });
    await page.hover(".sc-stage");
    await page.clock.runFor(16000);
    const s2 = await st();
    check("лента: при наведении — пауза", s2.stage === s1.stage && s2.paused === true, s2);
    await page.mouse.move(5, 5);
    await page.keyboard.press("ArrowRight");
    const s3 = await st();
    await page.keyboard.press("ArrowLeft");
    const s4 = await st();
    check("лента: → и ← листают блоки", s3.stage === "together" && s4.stage === "agencies", { s3: s3.stage, s4: s4.stage });
    await page.keyboard.press("Space");
    const s5 = await st();
    await page.clock.runFor(16000);
    const s6 = await st();
    check("лента: пробел — пауза (блок не меняется)", s5.paused === true && s6.stage === s4.stage, { s5, s6 });
    const pauseBtn = await page.evaluate(() => { const b = document.querySelector(".sc-tab--pause"); return b ? { pressed: b.getAttribute("aria-pressed"), label: b.getAttribute("aria-label") } : null; });
    check("лента: кнопка паузы с подписью и состоянием", pauseBtn && pauseBtn.pressed === "true" && /Продолжить/.test(pauseBtn.label), pauseBtn);
    await ctx.close();
  }

  // ── 3. Вход сотрудника (401), ошибка сети, «нет связи» при обновлении ──
  {
    const deny = (route) => route.fulfill({ status: 401, json: { error: "staff_only", message: "только сотрудник" } });
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru", route: deny });
    const login = await page.evaluate(() => ({
      state: document.getElementById("board").getAttribute("data-state"),
      inputs: document.querySelectorAll(".sc-login input").length, back: !!document.querySelector(".sc-login .sc-link"),
      focus: document.activeElement && document.activeElement.id,
      text: document.getElementById("board").innerText,
    }));
    check("401: форма входа сотрудника, «← В Birge», фокус в поле логина", login.state === "login" && login.inputs === 2 && login.back && login.focus === "sc-user", login);
    await page.unroute(API);
    await page.fill("#sc-user", "operator");
    await page.fill("#sc-pass", "неверно");
    await page.click(".sc-login button[type=submit]");
    await page.waitForTimeout(600);
    const bad = await page.evaluate(() => document.querySelector(".sc-login__error").textContent);
    check("401: неверный пароль — понятная ошибка, форма остаётся", /не подошли/.test(bad), bad);
    await ctx.close();
  }
  {
    const fail = (route) => route.abort("failed");
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru", route: fail });
    const err = await page.evaluate(() => ({ state: document.getElementById("board").getAttribute("data-state"), text: document.getElementById("board").innerText,
      btn: !!document.querySelector(".sc-message .sc-btn") }));
    check("сеть: «Нет связи с сервером», повтор сам и кнопка «Повторить»", err.state === "error" && /Нет связи/.test(err.text) && err.btn, err);
    await page.unroute(API);
    await page.click(".sc-message .sc-btn");
    await page.waitForSelector('#board[data-state="ok"]', { timeout: 15000 });
    check("сеть: после «Повторить» — данные", true);
    await page.route(API, fail);
    await page.evaluate(() => document.getElementById("board").birgeBoard.refresh());
    await page.waitForTimeout(800);
    const stale = await page.evaluate(() => ({ state: document.getElementById("board").getAttribute("data-state"),
      foot: document.querySelector(".sc-foot__time").textContent, live: !!document.querySelector(".sc-live[data-stale]") }));
    check("сеть: при обновлении — прежние числа и «Нет связи — показаны данные на …»", stale.state === "ok" && /Нет связи/.test(stale.foot) && stale.live, stale);
    await ctx.close();
  }

  // ── 4. Без соседей (R17/R16/R13 нет): спокойный блок по П1 ──
  {
    const empty = async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      for (const k of ["agencies", "crisis", "together", "meetings", "forecast"]) body[k] = { available: false, reason: "module_not_ready" };
      body.stage = [];
      await route.fulfill({ response: res, json: body });
    };
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "kk", route: empty });
    const calm = await page.evaluate(() => {
      const ic = document.querySelector(".sc-calm .sc-ic");
      const r = ic ? ic.getBoundingClientRect() : null;
      return { has: !!document.querySelector(".sc-calm"), icon: r ? Math.max(r.width, r.height) : null,
        buttons: document.querySelectorAll(".sc-calm a, .sc-calm button").length, bar: !!document.querySelector(".sc-crisis"),
        sh: document.documentElement.scrollHeight, ch: document.documentElement.clientHeight };
    });
    check("без соседей: спокойный блок — иконка ≤ 48 px, текст, одна кнопка; полосы кризиса нет; без прокрутки",
      calm.has && calm.icon <= 48 && calm.buttons === 1 && !calm.bar && calm.sh <= calm.ch, calm);
    await page.screenshot({ path: path.join(OUT, "board-1366-kk-no-neighbours.jpg"), type: "jpeg", quality: 82 });
    await ctx.close();
  }

  // ── 5. Меньше движения ──
  {
    const { ctx, page } = await open(browser, { width: 1366, height: 768, lang: "ru", reduced: true });
    const anim = await page.evaluate(() => ["sc-live__dot", "sc-crisis__pulse"].map((c) => {
      const el = document.querySelector("." + c);
      return el ? getComputedStyle(el).animationName : "none";
    }));
    check("prefers-reduced-motion: точки «в эфире» и кризиса не пульсируют", anim.every((a) => a === "none"), anim);
    await ctx.close();
  }

  // ── 6. П1: ни одной большой картинки (img/svg больше 48 px — только карта районов и мини-графики с данными) ──
  {
    const { ctx, page } = await open(browser, { width: 1920, height: 1080, lang: "ru", query: "?rotate=0" });
    const pics = await page.evaluate(() => Array.from(document.querySelectorAll("#board img, #board svg")).filter((e) => {
      const r = e.getBoundingClientRect();
      return Math.max(r.width, r.height) > 48 && !e.closest(".sc-map__figure") && !e.classList.contains("sc-spark") && !e.classList.contains("sc-ring");
    }).map((e) => e.getAttribute("class")));
    check("П1: картинок больше 48 px нет (кроме карты районов, мини-графиков и кольца задач — это данные)", pics.length === 0, pics);
    await ctx.close();
  }

  await browser.close();
  const failed = results.filter((r) => r.status === "FAIL").length;
  fs.writeFileSync(path.join(OUT, "board_check.json"), JSON.stringify({ base: BASE, at: new Date().toISOString(), passed: results.length - failed, failed, results }, null, 2));
  console.log(`\n${results.length - failed} PASS · ${failed} FAIL → ${path.join(OUT, "board_check.json")}`);
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
