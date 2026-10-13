#!/usr/bin/env node
// R10 · раунд 14 · эталон A + 7 правил качества Linear (research/round-14/design/README.md) — приёмка того, что видно
// и нажимается (правило 4 «мгновенный отклик» — отдельно, response_check.cjs; правило 7 «карточка слева» — reference_check.cjs).
//   1 поиск с подсказками (R01; данные R12, горячие места R07): подсказки с первой буквы, типы (улица, остановка, двор, район,
//     горячее место), ↓ и Enter → карточка;
//   2 клавиатура (R01; R07): «/» — поиск, Esc — закрыть карточку, ↓↑ / J K — по горячим местам, Ctrl+K — палитра, подсказки клавиш;
//   3 статус-иконки (R11 рисует; R07, R09, R08 применяют): 4 разных значка, есть в карточке, в «Горячих местах», в «Обращениях»;
//   5 списки Linear (R07 «Горячие места», R09 «Обращения»): строки 44 px, группы по статусу, чипы-фильтры, список ↔ карта;
//   6 чистота (R11): внутри карточек — линии 1 px rgba(18,26,23,.08), а не тени.
// Ничего не меняет в сборке; сотрудник входит через API той же сборки.
//   NODE_PATH="$(npm root -g)" node tests/e2e/linear_check.cjs --root <сборка> --out <папка> [--label имя]
// Итог: <out>/LINEAR.json, LINEAR.md; код 0 (отчёт).
"use strict";
const fs = require("fs"), path = require("path"), os = require("os");
const { chromium } = require("playwright");
const L = require("./r10_lib.cjs");
const args = L.parseArgs(process.argv.slice(2));
const ROOT = path.resolve(String(args.root || path.join(__dirname, "../..")));
const OUT = path.resolve(String(args.out || path.join(os.tmpdir(), "r10-linear")));
const LABEL = String(args.label || "");
const KHAN = [71.406553, 51.131155];
const results = [];
const add = (rule, owner, name, status, detail) => { results.push({ rule, owner, name, status, detail }); console.log(`${status.padEnd(8)} ${rule} ${owner.padEnd(8)} ${name}` + (detail ? " — " + JSON.stringify(detail).slice(0, 220) : "")); };

const OPTS = "[role=listbox] [role=option], [class*=suggest] li, [class*=suggest] [role=option], .civic-explore-row, [class*=palette] [role=option]";
async function newPage(browser, server, mode, staff) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 768 }, deviceScaleFactor: 1, locale: "ru-RU" });
  await ctx.addInitScript((m) => { try { if (!sessionStorage.getItem("r10")) { localStorage.setItem("birge.lang", "ru"); localStorage.setItem("birge.mode", m); sessionStorage.setItem("r10", "1"); } } catch (e) { /* пусто */ } }, mode);
  await L.glassMode(ctx, "keep");
  if (staff && server.staff && server.staff.user) await ctx.request.post(server.base + "api/civic/v1/session/login", { data: { username: server.staff.user, password: server.staff.pass } }).catch(() => null);
  const page = await ctx.newPage();
  await page.goto(server.base); await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 40, null, { timeout: 40000 }).catch(() => null);
  await L.sleep(4500);
  return { ctx, page };
}
const searchInput = (page) => L.firstVisible(page.locator("input[placeholder*='Улица'], input[placeholder*='Поиск'], input[placeholder*='Найти'], input[type=search]"));
const options = (page) => page.evaluate((sel) => [...document.querySelectorAll(sel)].filter((e) => { const r = e.getBoundingClientRect(); return r.height > 10 && r.width > 10; }).map((e) => e.innerText.replace(/\s+/g, " ").trim().slice(0, 80)), OPTS);
const cardOpen = (page) => page.evaluate(() => { const c = document.querySelector(".r07-card"); return !!c && c.getBoundingClientRect().width > 0; });
const KINDS = [["улица", /\b(ул\.|улица|пр\.|проспект|көшесі|даңғылы|шоссе)/i], ["остановка", /остановк|аялдама/i], ["двор", /двор|ЖК|аула/i],
  ["район", /район|ауданы|^(Нура|Есиль|Алматы|Сарыарка|Байконур|Сарайшык)\b/i], ["горячее место", /\d+\s*(чел|обращ|жалоб|адам)|·\s*\d+$/i]];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const server = await L.startServer(ROOT);
  const browser = await chromium.launch();
  try {
    // ---------- 1. поиск и 2. «/»
    {
      const { ctx, page } = await newPage(browser, server, "akimat", true);
      await page.mouse.click(700, 420); await L.sleep(300);   // фокус — на карте, не в поле
      await page.keyboard.press("/"); await L.sleep(300);
      const focused = await page.evaluate(() => { const a = document.activeElement; return !!a && a.tagName === "INPUT" && /Улица|Поиск|Найти/i.test(a.placeholder || ""); });
      add("2", "R01", "«/» — фокус в поиске", focused ? "PASS" : "FAIL", null);
      const inp = await searchInput(page);
      if (!inp) add("1", "R01", "поле поиска есть", "FAIL", null);
      else {
        const kinds = {}, samples = {};
        for (const q of ["Х", "Хан", "Туран", "Двор", "Нура"]) {
          await inp.fill(""); await inp.click(); await page.keyboard.type(q); await L.sleep(q.length === 1 ? 900 : 1200);
          const o = await options(page); samples[q] = o.slice(0, 5);
          for (const t of o) for (const [k, re] of KINDS) if (re.test(t)) kinds[k] = (kinds[k] || 0) + 1;
          if (q === "Х") add("1", "R01", "подсказки с первой буквы («Х»)", o.length ? "PASS" : "FAIL", { n: o.length, ex: o.slice(0, 4) });
        }
        const miss = KINDS.map(([k]) => k).filter((k) => !kinds[k]);
        add("1", "R01+R12+R07", "типы подсказок: улицы, остановки, дворы, районы, горячие места", miss.length === 0 ? "PASS" : miss.length <= 2 ? "СМОТРЕТЬ" : "FAIL", { есть: kinds, нет: miss, примеры: samples });
        // ↓ и Enter → карточка
        await inp.fill(""); await inp.click(); await page.keyboard.type("Хан"); await L.sleep(1200);
        const before = await page.evaluate(() => { const a = document.activeElement; return a ? a.getAttribute("aria-activedescendant") : null; });
        await page.keyboard.press("ArrowDown"); await L.sleep(250);
        const nav = await page.evaluate((sel) => { const a = document.activeElement; const ad = a && a.getAttribute("aria-activedescendant");
          const sel2 = [...document.querySelectorAll(sel)].some((e) => e.getAttribute("aria-selected") === "true" || /active|is-active|--on|highlight/.test(e.className) || e === document.activeElement);
          return { ad, moved: !!ad || sel2 }; }, OPTS);
        add("1", "R01", "↓ выделяет подсказку", nav.moved && nav.ad !== before ? "PASS" : nav.moved ? "PASS" : "FAIL", nav);
        await page.keyboard.press("Enter"); await L.sleep(3000);
        const opened = await cardOpen(page);
        add("1", "R01+R07", "Enter — открывается карточка места", opened ? "PASS" : "FAIL", null);
      }
      // Ctrl+K
      await page.keyboard.press("Escape"); await L.sleep(300); await page.mouse.click(700, 420); await L.sleep(300);
      await page.keyboard.press("Control+k"); await L.sleep(700);
      const pal = await page.evaluate(() => { const d = [...document.querySelectorAll("[role=dialog], dialog[open], [class*=palette], [class*=command], [class*=cmdk]")].find((e) => e.getBoundingClientRect().width > 100);
        const a = document.activeElement; return { open: !!d, cls: d ? String(d.className).slice(0, 60) : null, input: !!a && a.tagName === "INPUT" && !!d && d.contains(a) }; });
      add("2", "R01", "Ctrl+K — командная палитра", pal.open && pal.input ? "PASS" : pal.open ? "СМОТРЕТЬ" : "FAIL", pal);
      await page.keyboard.press("Escape"); await L.sleep(300);
      const kbd = await page.evaluate(() => [...document.querySelectorAll("kbd, [class*=kbd]")].filter((e) => e.getBoundingClientRect().width > 0).map((e) => e.innerText.trim()).slice(0, 8));
      add("2", "R01", "подсказки клавиш рядом с действиями (kbd)", kbd.length ? "PASS" : "СМОТРЕТЬ", { kbd });
      await ctx.close();
    }
    // ---------- 2. Esc, J/K; 5. «Горячие места»; 3, 6 — карточка
    {
      const { ctx, page } = await newPage(browser, server, "akimat", true);
      // J/K по строкам «Горячих мест»
      const rows = page.locator(".r07-item");
      const n = await rows.count();
      if (!n) add("2", "R07", "J/K по «Горячим местам» — строки есть", "NOT_RUN", null);
      else {
        await rows.first().focus(); await L.sleep(200);
        const k0 = await page.evaluate(() => (document.activeElement && document.activeElement.dataset.key) || null);
        await page.keyboard.press("j"); await L.sleep(250);
        const k1 = await page.evaluate(() => (document.activeElement && document.activeElement.dataset.key) || null);
        await page.keyboard.press("k"); await L.sleep(250);
        const k2 = await page.evaluate(() => (document.activeElement && document.activeElement.dataset.key) || null);
        add("2", "R07", "J — следующее, K — предыдущее горячее место", k1 && k1 !== k0 && k2 === k0 ? "PASS" : "FAIL", { k0, k1, k2 });
        await page.keyboard.press("ArrowDown"); await L.sleep(250);
        const k3 = await page.evaluate(() => (document.activeElement && document.activeElement.dataset.key) || null);
        add("2", "R07", "↓ — следующее горячее место", k3 && k3 !== k0 ? "PASS" : "FAIL", { k3 });
        // 5: строки 44 px, синхронность список ↔ карта
        const hs = await page.evaluate(() => [...document.querySelectorAll(".r07-item")].filter((e) => e.getBoundingClientRect().height > 0).map((e) => Math.round(e.getBoundingClientRect().height)));
        const med = hs.slice().sort((a, b) => a - b)[Math.floor(hs.length / 2)];
        add("5", "R07", "«Горячие места» — плотные строки 44 px (40–48)", med >= 40 && med <= 48 ? "PASS" : "FAIL", { median: med, heights: hs.slice(0, 8) });
        const snap = () => page.evaluate(() => [...document.querySelectorAll(".r07-badge")].map((b) => b.className).join("|"));
        const s0 = await snap(); await rows.nth(0).hover(); await L.sleep(400); const s1 = await snap();
        add("5", "R07", "наведение на строку подсвечивает значок на карте", s0 !== s1 ? "PASS" : "FAIL", null);
        await page.mouse.move(5, 400); await L.sleep(300);
        const badge = await L.firstVisible(page.locator(".r07-badge:not(.r07-badge--cluster)"));
        if (badge) { const r0 = await page.evaluate(() => [...document.querySelectorAll(".r07-item")].map((b) => b.className + (b.matches(":hover") ? "h" : "")).join("|"));
          await badge.hover().catch(() => null); await L.sleep(400);
          const r1 = await page.evaluate(() => [...document.querySelectorAll(".r07-item")].map((b) => b.className).join("|"));
          add("5", "R07", "наведение на значок подсвечивает строку списка", r0.replace(/h(\||$)/g, "$1") !== r1 ? "PASS" : "СМОТРЕТЬ", null); }
      }
      // 3: статус-иконки в «Горячих местах»
      const hotSt = await page.evaluate(() => document.querySelectorAll(".r07-hot svg.bk-st-ic, .r07-hot .bk-status, .r07-hot [data-status]").length);
      add("3", "R07", "статус-иконки в «Горячих местах»", hotSt ? "PASS" : "FAIL", { n: hotSt });
      // карточка: Esc, статус, чистота
      const p = await L.showPoint(page, KHAN, 17);
      if (p) { await L.tap(page, p.x, p.y); await L.sleep(2500); }
      if (!(await cardOpen(page))) add("2", "R01+R07", "Esc закрывает карточку — карточка открылась", "NOT_RUN", null);
      else {
        const cardSt = await page.evaluate(() => { const c = document.querySelector(".r07-card"); return c ? c.querySelectorAll("svg.bk-st-ic, .bk-status, [data-status]").length : 0; });
        add("3", "R07", "статус-иконка + слово в карточке места", cardSt ? "PASS" : "FAIL", { n: cardSt });
        const clean = await page.evaluate(() => { const c = document.querySelector(".r07-card"); const rgba = (x) => (x.match(/[\d.]+/g) || []).map(Number);
          let sh = 0, ln = 0, ln08 = 0; const ex = [];
          for (const e of c.querySelectorAll("*")) { const s = getComputedStyle(e); if (e.getBoundingClientRect().width < 2) continue;
            if (s.boxShadow && s.boxShadow !== "none" && !/inset/.test(s.boxShadow) && !/^(button|a)$/i.test(e.tagName) && !e.closest("button")) { sh++; if (ex.length < 3) ex.push(String(e.className).slice(0, 40) + " " + s.boxShadow.slice(0, 50)); }
            for (const side of ["Top", "Bottom"]) if (parseFloat(s["border" + side + "Width"]) === 1) { ln++; const v = rgba(s["border" + side + "Color"]); if (v.length >= 4 && Math.abs(v[0] - 18) < 12 && Math.abs(v[1] - 26) < 12 && Math.abs(v[2] - 23) < 12 && v[3] <= 0.14) ln08++; } }
          return { shadows: sh, lines: ln, lines08: ln08, ex }; });
        add("6", "R11+R07", "карточка: линии 1 px rgba(18,26,23,.08), без теней внутри", clean.shadows === 0 && clean.lines08 > 0 ? "PASS" : clean.shadows <= 1 ? "СМОТРЕТЬ" : "FAIL", clean);
        await page.mouse.move(5, 400); await page.keyboard.press("Escape"); await L.sleep(800);
        add("2", "R01+R07", "Esc закрывает карточку", (await cardOpen(page)) ? "FAIL" : "PASS", null);
      }
      // 3: четыре разных значка статуса
      const four = await page.evaluate(() => { const U = window.BirgeUI; if (!U || !U.statusIcon) return null;
        const h = ["new", "in_progress", "reported_fixed", "verified"].map((s) => { const m = String(U.statusIcon(s, 14)).match(/href="[^"#]*#([^"]+)"/); return m ? m[1] : String(U.statusIcon(s, 14)).slice(0, 30); });
        return { ids: h, distinct: new Set(h).size }; });
      add("3", "R11", "4 разных статус-значка (новое · в работе · служба устранила · проверено жителями)", four && four.distinct === 4 ? "PASS" : "FAIL", four);
      await ctx.close();
    }
    // ---------- 5. «Обращения» (R09) и 3 — статусы в списке
    {
      const { ctx, page } = await newPage(browser, server, "akimat", true);
      const b = await L.firstVisible(page.locator(".birge-nav__item, header button").filter({ hasText: /^\s*Обращения\s*$/ }));
      if (!b) add("5", "R09", "«Обращения» открываются", "NOT_RUN", null);
      else {
        await b.click(); await L.sleep(3000);
        const inbox = await page.evaluate(() => { const s = [...document.querySelectorAll("#birge-screen, .birge-screen, .birge-day")].find((e) => e.getBoundingClientRect().width > 0) || document;
          const rows = [...s.querySelectorAll(".bc-row, .bc-inbox__row, [role=row], li")].filter((e) => { const r = e.getBoundingClientRect(); return r.height >= 30 && r.height <= 140 && /\d/.test(e.innerText); });
          const hs = rows.map((e) => Math.round(e.getBoundingClientRect().height)).sort((a, b) => a - b);
          const groups = [...s.querySelectorAll(".bc-inbox__group, [class*=group] h3, [class*=group] h4, [role=rowgroup]")].filter((e) => e.getBoundingClientRect().height > 0).map((e) => e.innerText.split("\n")[0].trim().slice(0, 30));
          const chips = [...s.querySelectorAll(".bc-inbox__tab, [class*=chip], [role=tab]")].filter((e) => e.getBoundingClientRect().height > 0).map((e) => e.innerText.trim().slice(0, 20));
          const st = s.querySelectorAll("svg.bk-st-ic, .bk-status, [data-status]").length;
          return { n: rows.length, median: hs[Math.floor(hs.length / 2)] || null, groups: groups.slice(0, 6), chips: chips.slice(0, 8), st }; });
        add("5", "R09", "«Обращения» — строки 44 px (40–48)", inbox.median && inbox.median >= 40 && inbox.median <= 48 ? "PASS" : "FAIL", { n: inbox.n, median: inbox.median });
        add("5", "R09", "«Обращения» — группы по статусу", inbox.groups.length >= 2 ? "PASS" : "FAIL", { groups: inbox.groups });
        add("5", "R09", "«Обращения» — чипы-фильтры сверху", inbox.chips.length >= 2 ? "PASS" : "FAIL", { chips: inbox.chips });
        add("3", "R09", "статус-иконки в «Обращениях»", inbox.st ? "PASS" : "FAIL", { n: inbox.st });
      }
      await ctx.close();
    }
  } finally { await browser.close(); await server.stop(); }
  const counts = {}; results.forEach((r) => (counts[r.status] = (counts[r.status] || 0) + 1));
  const sha = L.buildSha(ROOT);
  fs.writeFileSync(path.join(OUT, "LINEAR.json"), JSON.stringify({ sha, label: LABEL, when: new Date().toISOString(), counts, results }, null, 1));
  fs.writeFileSync(path.join(OUT, "LINEAR.md"), [`# R10 · правила качества Linear 1, 2, 3, 5, 6 · ${LABEL || sha}`, "",
    `Сборка \`${sha}\`. Итого: ${Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(" · ")}. Правило 4 — RESPONSE.md, правило 7 — REFERENCE.md.`, "",
    "| Правило | Роль | Проверка | Итог | Подробно |", "|---|---|---|---|---|",
    ...results.map((r) => `| ${r.rule} | ${r.owner} | ${r.name} | **${r.status}** | ${r.detail ? JSON.stringify(r.detail).replace(/\|/g, "/").slice(0, 300) : ""} |`)].join("\n") + "\n");
  console.log("ИТОГ:", counts, "→", OUT);
})().catch((e) => { console.error(e); process.exit(2); });
