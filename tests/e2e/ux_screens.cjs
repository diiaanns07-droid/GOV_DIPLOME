// R10 · раунд 14 · UX-чек-лист по каждому экрану (UX_BRIEF «Проверка каждого экрана» + UX_SPEC §8).
//
//   node tests/e2e/ux_screens.cjs --screens <screens.json> --out <папка> [--sizes 1366x768,375x812]
//
// screens.json: [{"name": "Тепловая карта · акимат", "owner": "R07",
//                 "url": "http://127.0.0.1:8617/civic/heat/demo.html?lang={lang}&role=akimat&view=nura",
//                 "primary": "Взять в работу|Жұмысқа алу",         // подпись главной кнопки (необязательно)
//                 "optional": true}]                                 // страницы может не быть (404 → NOT_RUN)
// {lang} заменяется на ru / kk, {base} — на --base. Экран открывается в обоих языках; kk сравнивается с ru построчно.
// Проверки на каждом размере: прокрутка вбок, ключи перевода, тех. слова, шрифт < 14 px, зоны нажатия < 40 px,
// русские строки в kk, ошибки консоли; на 1366 — Tab до главной кнопки и видимая рамка фокуса.
// Состояния «загрузка / пусто / ошибка» здесь не проверяются (их проверяют тесты ролей и demo_flow) — NOT_RUN.
// Итог: <out>/UX_RESULT.md, UX_RESULT.json, кадры <экран>-<размер>-<язык>.jpg. Нужен NODE_PATH="$(npm root -g)".
"use strict";
const { chromium } = require("playwright");
const fs = require("fs"), path = require("path");
const { NOISE, uiScreen, cyrLines, untranslated, focusToPrimary } = require("./ux_lib.cjs");

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith("--")) acc.push([a.slice(2), all[i + 1] && !all[i + 1].startsWith("--") ? all[i + 1] : true]);
  return acc;
}, []));
const OUT = path.resolve(args.out || "ux-out");
const SIZES = String(args.sizes || "1366x768,375x812").split(",").map((s) => s.split("x").map(Number));
const SCREENS = JSON.parse(fs.readFileSync(args.screens, "utf8"));
// {base} в адресах экранов — корень сервера сборки (--base http://127.0.0.1:8611/).
const BASE = String(args.base || "http://127.0.0.1:8611/");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9а-яәғқңөұүһі]+/gi, "-").replace(/^-|-$/g, "").slice(0, 40);

const rows = [];
const add = (screen, size, lang, check, status, detail, shot) => {
  rows.push({ screen: screen.name, owner: screen.owner, size, lang, check, status, detail: detail ?? null, shot: shot || null });
  console.log(`${status.padEnd(7)} ${screen.owner} ${screen.name} ${size} ${lang} · ${check}` + (status === "FAIL" && detail ? " — " + JSON.stringify(detail).slice(0, 240) : ""));
};

async function open(browser, url, w, h, lang) {
  const mobile = w < 761;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1,
    locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push("pageerror: " + e.message));
  page.on("console", (m) => { if (["error", "warning"].includes(m.type()) && !NOISE.test(m.text())) page.errs.push(m.type() + ": " + m.text().slice(0, 200)); });
  const res = await page.goto(url.replace("{lang}", lang).replace("{base}", BASE)).catch((e) => { page.errs.push("goto: " + e.message); return null; });
  page.httpStatus = res ? res.status() : 0;
  await sleep(3000);
  // Экраны без ?lang= (оболочка R01): язык выбирается кнопкой ҚАЗ / РУС в шапке.
  const btn = page.getByRole("button", { name: lang === "kk" ? /^ҚАЗ$/ : /^РУС$/ }).first();
  if (await btn.isVisible().catch(() => false)) { await btn.click().catch(() => null); await sleep(1000); }
  return { ctx, page };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  try {
    for (const screen of SCREENS) for (const [w, h] of SIZES) {
      const size = `${w}`;
      // Сначала ru (эталон строк), затем kk.
      const ru = await open(browser, screen.url, w, h, "ru");
      // "optional": true — страницы может не быть в этой сборке (404) → NOT_RUN, а не FAIL.
      if (screen.optional && ru.page.httpStatus >= 400) {
        add(screen, size, "ru+kk", "страница есть в сборке", "NOT_RUN", { http: ru.page.httpStatus });
        await ru.ctx.close();
        continue;
      }
      const ruLines = await cyrLines(ru.page);
      await ru.ctx.close();
      for (const lang of ["ru", "kk"]) {
        const { ctx, page } = await open(browser, screen.url, w, h, lang);
        const shot = `${slug(screen.owner + "-" + screen.name)}-${w}-${lang}.jpg`;
        await page.screenshot({ path: path.join(OUT, shot), type: "jpeg", quality: 70 }).catch(() => null);
        const s = await uiScreen(page);
        add(screen, size, lang, "открылся, язык страницы верный", s.lang === lang ? "PASS" : "FAIL", { lang: s.lang }, shot);
        add(screen, size, lang, "нет горизонтальной прокрутки", s.scrollW <= s.innerW ? "PASS" : "FAIL", { scrollW: s.scrollW, w: s.innerW });
        add(screen, size, lang, "нет ключей перевода и технических слов", !s.raw.length && !s.tech.length ? "PASS" : "FAIL", { raw: s.raw, tech: s.tech });
        add(screen, size, lang, "шрифт ≥ 14 px (основной 16)", s.tinyN === 0 ? "PASS" : "FAIL", { tiny: s.tinyN, ex: s.tiny, under16: s.smallN });
        add(screen, size, lang, "зоны нажатия ≥ 40 px (цель 48)", s.under40N === 0 ? "PASS" : "FAIL", { under40: s.under40N, ex: s.under40, under48: `${s.under48N}/${s.targetsN}` });
        if (s.mapBadges) add(screen, size, lang, "значки на карте ≥ 24 px (UX_SPEC §5)", s.mapBadgesUnder24 === 0 ? "PASS" : "FAIL", { badges: s.mapBadges, under24: s.mapBadgesUnder24 });
        if (lang === "kk") {
          const same = untranslated(await cyrLines(page), ruLines);
          add(screen, size, lang, "казахский полный (нет русских строк)", same.length === 0 ? "PASS" : "FAIL", { n: same.length, ex: same.slice(0, 6) });
        }
        if (w >= 1024 && screen.primary) {
          const f = await focusToPrimary(page, new RegExp(screen.primary, "i"));
          add(screen, size, lang, "Tab до главной кнопки, рамка фокуса видна", f.primary && f.ring ? "PASS" : "FAIL", f);
        }
        add(screen, size, lang, "консоль без ошибок", page.errs.length === 0 ? "PASS" : "FAIL", page.errs.slice(0, 4));
        await ctx.close();
      }
    }
  } finally { await browser.close(); }
  const counts = { PASS: 0, FAIL: 0, NOT_RUN: 0 };
  rows.forEach((r) => counts[r.status]++);
  fs.writeFileSync(path.join(OUT, "UX_RESULT.json"), JSON.stringify({ when: new Date().toISOString(), counts, rows }, null, 1));
  // Сводка: экран × размер × язык → число FAIL и какие пункты
  const keyOf = (r) => `${r.owner} · ${r.screen} · ${r.size} · ${r.lang}`;
  const groups = {};
  rows.forEach((r) => { (groups[keyOf(r)] = groups[keyOf(r)] || []).push(r); });
  const md = ["# R10 · UX-чек-лист по экранам", "", `Итого: PASS ${counts.PASS}, FAIL ${counts.FAIL}, NOT_RUN ${counts.NOT_RUN}. «Загрузка/пусто/ошибка» — NOT_RUN здесь (см. тесты ролей).`, "",
    "| Экран | FAIL | Что не так | Кадр |", "|---|---|---|---|",
    ...Object.entries(groups).map(([k, rs]) => {
      const bad = rs.filter((r) => r.status === "FAIL");
      return `| ${k} | ${bad.length} | ${bad.map((r) => r.check + (r.detail ? " " + JSON.stringify(r.detail).replace(/\|/g, "/").slice(0, 160) : "")).join("<br>")} | ${rs[0].shot || ""} |`;
    })];
  fs.writeFileSync(path.join(OUT, "UX_RESULT.md"), md.join("\n") + "\n");
  console.log("ИТОГ:", counts, "→", OUT);
})().catch((e) => { console.error(e); process.exit(2); });
