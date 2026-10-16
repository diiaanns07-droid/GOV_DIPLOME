// R05 · раунд 15+ (поправка П3) · экраны модуля 3D по чек-листу VISUAL_BRIEF §4 в собранном приложении:
// каталог «Что построить?», размещение, карточка проекта (сквер — шторка «Было / станет»; освещение — «День / Ночь»),
// подсказка жителя, метки «Проект · 2027» на карте (масштаб 16); 1366 / 1024 / 375 × ru / kk. Что меряется (только
// текст и кнопки R05; содержимое карточки R06 внутри панели — у R06, его размеры печатаются для сведения):
//   п. 3 — не мельче 13 px (ui-kit --fs-xs, решение владельца 12 окт) и не больше 3 размеров шрифта; казахский не обрезан;
//   п. 3 правил — одна главная кнопка; п. 9 — иконки только из набора ui-kit; п. 10 — зона нажатия ≥ 44 px и видимый
//   фокус (Tab); метка «Проект · 2027» на карте — тоже не мельче 13 px; размещение с обзорного вида начинается в городе.
// Запуск:  NODE_PATH=$(npm root -g) node tests/civic/R05/round15/app_visual_audit.mjs [--url http://127.0.0.1:8655] [--shots папка] [--stand подпись] [--out имя.json] [--only состояния]
// Отчёт — research/round-15-results/R05/runs/app_visual_audit.json.
import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const arg = (n, d) => { const i = process.argv.indexOf(n); return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
const URL0 = arg("--url", "http://127.0.0.1:8655");
const STAND = arg("--stand", "");
const OUT = arg("--out", "app_visual_audit.json");
const SHOTS = arg("--shots", "");  // папка кадров; без неё кадры не пишутся
const ONLY = arg("--only", "");    // только эти состояния через запятую (catalog,placing,…) — переснять часть
const { chromium } = require("playwright");

const results = [];
const record = (id, status, detail) => { results.push({ id, status, detail }); console.log(`${status}  ${id}${detail ? "  — " + JSON.stringify(detail) : ""}`); };
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const pageErrors = [];

const VIEWS = [
  { w: 1366, h: 768 }, { w: 1024, h: 768 }, { w: 375, h: 812, mobile: true },
];
const STATES = ["catalog", "placing", "card_square", "card_lighting_night", "hint", "labels_z16"].filter((x) => !ONLY || ONLY.split(",").includes(x));

async function open(view, lang, state) {
  const mode = state === "hint" ? "resident" : "akimat";
  const ctx = await browser.newContext({ viewport: { width: view.w, height: view.h }, deviceScaleFactor: 1, hasTouch: !!view.mobile, isMobile: !!view.mobile });
  await ctx.addInitScript((m) => { try { localStorage.setItem("birge.mode", m); } catch (e) { /* нет хранилища */ } }, mode);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => pageErrors.push(`${view.w} ${lang} ${state}: ${e.message}`));
  await page.goto(URL0 + "/?lang=" + lang);
  await page.waitForFunction(() => window.CivicShell?.build3d && window.BirgeShell, null, { timeout: 60000 });
  if (lang === "kk") await page.evaluate(() => window.BirgeI18n?.setLang?.("kk"));
  await page.evaluate(() => window.BirgeShell.setLayer("projects"));
  await page.waitForFunction(() => { const s = window.CivicShell.build3d.getState(); return s.phase === "ready" && s.count > 0; }, null, { timeout: 60000 });
  await page.waitForTimeout(600);
  if (state === "catalog" || state === "placing") {
    // Телефон: оболочка сама сворачивает шторку, когда открывается каталог (shell.js), — каталог над ней.
    await page.click(".birge-b3d-toggle");
    await page.waitForSelector('.b3d-dock[data-state="catalog"]', { timeout: 15000 });
    if (state === "placing") {
      await page.click('.b3d-dock[data-state="catalog"] .b3d-card');
      await page.waitForSelector('.b3d-dock[data-state="placing"]', { timeout: 15000 });
    }
  } else if (state.startsWith("card")) {
    const kind = state === "card_square" ? "square" : "lighting";
    await page.evaluate((k) => { const s = window.CivicShell.build3d.getState(); const p = s.proposals.find((x) => x.kind === k); window.CivicShell.build3d.select(p.id); }, kind);
    await page.waitForSelector('.b3d-dock[data-state="card"]', { timeout: 20000 });
    if (state === "card_lighting_night") {
      // Телефон: шторка «Было / станет» (и «День / Ночь» под ней) открывается кнопкой в карточке.
      const baBtn = await page.$('.b3d-dock .b3d-ba-toggle');
      if (baBtn && (await baBtn.isVisible())) { await baBtn.click(); await page.waitForTimeout(400); }
      await page.click('.b3d-dock .bk-seg button:last-child');
    }
  } else if (state === "hint") {
    await page.waitForSelector('.b3d-dock[data-state="hint"]', { timeout: 15000 });
  } else if (state === "labels_z16") {
    // Метки «Проект · 2027» табличками: карта у сквера на масштабе 16 (на обзорном масштабе они точки и группы с числом).
    // Проект — в свободную часть карты (выше центра холста): на телефоне центр холста у самой шторки, под кнопкой
    // «Что построить?» оболочки. Так его видит и человек — модуль поднимает выбранный объект над панелями (keepAboveDock).
    await page.evaluate(() => { const s = window.CivicShell.build3d.getState(); const p = s.proposals.find((x) => x.kind === "square") || s.proposals[0];
      map.easeTo({ center: p.geometry.coordinates, zoom: 16, offset: [0, -Math.round(innerHeight * 0.22)], duration: 0 }); });
  }
  // Камера долетела (у выбранного проекта метки уже табличками, а не точками обзорного масштаба). Карта — глобальная
  // `map` из web/interface.js (window.map — это div#map).
  await page.waitForFunction(() => typeof map !== "undefined" && map && typeof map.isMoving === "function" && !map.isMoving(), null, { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(1200);
  return { ctx, page };
}

// Мера одного экрана: текст R05 (без содержимого карточки R06 .b3d-r06), кнопки, иконки, метки на карте.
const measure = (page) => page.evaluate(() => {
  const dock = document.querySelector("#birge-build3d-root .b3d-dock") || document.createElement("div");
  const vis = (e) => { const s = getComputedStyle(e); const q = e.getBoundingClientRect(); return s.display !== "none" && s.visibility !== "hidden" && +s.opacity > 0.05 && q.width > 0 && q.height > 0; };
  const own = (e) => !e.closest(".b3d-r06") && !e.closest(".b3d-sr");
  const textEls = (root) => [...root.querySelectorAll("*")].filter(vis).filter((e) => [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()));
  const all = textEls(dock);
  const mine = all.filter(own);
  const px = (e) => parseFloat(getComputedStyle(e).fontSize);
  const sizes = [...new Set(mine.map(px))].sort((a, b) => a - b);
  const r06sizes = [...new Set(all.filter((e) => e.closest(".b3d-r06")).map(px))].sort((a, b) => a - b);
  const small = mine.filter((e) => px(e) < 13).map((e) => [px(e), e.textContent.trim().slice(0, 20)]);
  const trunc = mine.filter((e) => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflow !== "visible").map((e) => e.textContent.trim().slice(0, 24));
  const ctrls = [...dock.querySelectorAll("button, a[href], [role=slider], [role=button], input")].filter(vis).filter(own);
  const tiny = ctrls.map((e) => { const q = e.getBoundingClientRect(); return { t: (e.textContent || e.getAttribute("aria-label") || "").trim().slice(0, 20), w: Math.round(q.width), h: Math.round(q.height) }; }).filter((x) => x.w < 44 || x.h < 44);
  const primary = ctrls.filter((e) => e.classList.contains("bk-btn--primary")).length;
  const icons = [...dock.querySelectorAll("svg use")].map((u) => u.getAttribute("href") || u.getAttribute("xlink:href") || "").filter((h) => !/\/civic\/ui-kit\/icons\.svg#/.test(h));
  // Метки на карте — табличкой с текстом («Проект · 2027»); точки обзорного масштаба (.b3d-label--dot) без текста не в счёт.
  // Размещение начинается в городе (П3: на телефоне на обзорном виде призрак вставал «за пределами Астаны»).
  const g = window.CivicShell.build3d.getState().ghost;
  const ghostOutside = !!(g && g.valid && g.valid.ok === false && g.valid.reason === "outside_city");
  const labels = [...document.querySelectorAll(".b3d-labels .b3d-label:not(.b3d-label--dot) .b3d-label__pill")].filter(vis)
    .filter((e) => e.textContent.trim()).map((e) => parseFloat(getComputedStyle(e).fontSize));
  return { state: dock.dataset.state, sizes, r06sizes, small, trunc, tiny, primary, icons, labelSizes: [...new Set(labels)], ghostOutside };
});

// Видимый фокус: Tab по своим элементам панели — у каждого рамка (outline ≥ 2 px или тень).
async function focusRing(page) {
  await page.evaluate(() => { const d = document.querySelector("#birge-build3d-root .b3d-dock"); const f = d && [...d.querySelectorAll("button, [role=slider], [tabindex='0']")].find((e) => !e.closest(".b3d-r06") && e.offsetParent); f && f.focus(); });
  // Фокус из скрипта после щелчка мышью браузер не считает клавиатурным (:focus-visible нет) — шаг назад и вперёд Tab'ом,
  // как ходит человек с клавиатуры.
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Tab");
  const seen = new Map();
  for (let i = 0; i < 12; i++) {
    const r = await page.evaluate(() => {
      const e = document.activeElement, d = document.querySelector("#birge-build3d-root .b3d-dock");
      if (!e || !d || !d.contains(e) || e.closest(".b3d-r06")) return null;
      const s = getComputedStyle(e);
      const ring = (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) >= 2) || (s.boxShadow !== "none" && /rgb/.test(s.boxShadow));
      return { k: (e.className + "|" + (e.textContent || e.getAttribute("aria-label") || "")).slice(0, 60), ring };
    });
    if (r) seen.set(r.k, r.ring);
    await page.keyboard.press("Tab");
    await page.waitForTimeout(80);
  }
  return { n: seen.size, noRing: [...seen].filter(([, ring]) => !ring).map(([k]) => k) };
}

const table = {};
for (const view of VIEWS) {
  for (const lang of ["ru", "kk"]) {
    for (const state of STATES) {
      // Подсказка жителя на телефоне видна только над свёрнутой шторкой (её сворачивают пальцем) — здесь не меряем.
      if (state === "hint" && view.mobile) continue;
      const id = `${state}_${view.w}_${lang}`;
      let ctx;
      try {
        const o = await open(view, lang, state);
        ctx = o.ctx;
        const m = await measure(o.page);
        // Кадр — до прохода Tab'ом: после него фокус уходит из панели на чужие ссылки (рамка фокуса на кадре).
        if (SHOTS) { await mkdir(SHOTS, { recursive: true }); await o.page.screenshot({ path: path.join(SHOTS, `audit_${id}.png`) }); }
        const f = view.mobile || state === "labels_z16" ? { n: 0, noRing: [] } : await focusRing(o.page);
        const bad = [];
        if (m.small.length) bad.push("мельче 13 px: " + JSON.stringify(m.small));
        if (m.sizes.length > 3) bad.push("размеров шрифта R05 > 3: " + m.sizes.join("/"));
        if (m.trunc.length) bad.push("обрезано: " + m.trunc.join(", "));
        if (m.tiny.length) bad.push("зона < 44: " + JSON.stringify(m.tiny));
        if (m.primary > 1) bad.push("главных кнопок: " + m.primary);
        if (m.icons.length) bad.push("иконки не из ui-kit: " + m.icons.join(", "));
        if (m.labelSizes.some((x) => x < 13)) bad.push("метка на карте < 13 px: " + m.labelSizes.join("/"));
        if (f.noRing.length) bad.push("нет рамки фокуса: " + f.noRing.join(", "));
        if (m.ghostOutside) bad.push("размещение началось за городом («за пределами Астаны»)");
        table[id] = { state: m.state, r05_sizes: m.sizes, r06_sizes: m.r06sizes, label_sizes: m.labelSizes, focus_checked: f.n, primary: m.primary };
        if (state === "labels_z16" && !m.labelSizes.length) bad.push("на масштабе 16 нет меток-табличек — нечего мерить");
        record(id, bad.length ? "FAIL" : "PASS", bad.length ? bad : table[id]);
      } catch (e) {
        record(id, "FAIL", String(e.message || e).split("\n")[0]);
      } finally {
        if (ctx) await ctx.close();
      }
    }
  }
}
await browser.close();

const head = (() => { try { return execSync("git rev-parse --short=8 HEAD", { cwd: ROOT }).toString().trim(); } catch (e) { return null; } })();
const out = path.join(ROOT, "research/round-15-results/R05/runs", OUT);
await mkdir(path.dirname(out), { recursive: true });
await writeFile(out, JSON.stringify({ at: new Date().toISOString(), url: URL0, code_head: head, stand: STAND || null,
  env: "облако: Chromium headless + SwiftShader, упрощённый фон карты", checklist: "VISUAL_BRIEF §4 пп. 3, 9, 10 + правило 3 (одна главная кнопка)",
  results, pageErrors }, null, 1) + "\n");
const n = (s) => results.filter((r) => r.status === s).length;
console.log(`итог: ${n("PASS")} PASS / ${n("FAIL")} FAIL; ошибки страницы: ${pageErrors.length}`);
process.exit(n("FAIL") || pageErrors.length ? 1 : 0);
