/*
 * R11 · разбор сборки раунда 15 (B1, B2, FINAL-5) одной командой: разделы IA_ROUND15 × 1366 / 1024 / 375 × ru / kk.
 *
 *   NODE_PATH="$(npm root -g)" node tests/civic/R11/review/r15_screens.cjs <BASE> <OUT> <файл-пароля> [--only kk] [--quick]
 *     BASE — сервер сборки (CIVIC_DEMO=1, CIVIC_DEMO_WORLD=1, сотрудник operator создан), напр. http://127.0.0.1:8656
 *     файл-пароля — пароль сотрудника operator; читается из файла и нигде не печатается
 *     --quick — только 1366 и 375; --only kk — один язык
 *
 * На каждый кадр: <OUT>/<ширина>-<язык>-<вид>-<раздел>.jpg и проверки —
 *   scroll   горизонтальная прокрутка страницы;
 *   cut      обрезанный текст (overflow/ellipsis/line-clamp, scrollWidth > clientWidth) вне строк, которые прокручиваются
 *            сами (.bk-tabs, .bk-scroll-x, [data-more]) — критерий «казахский не обрезается на 375»;
 *   keys     «сырые» ключи словаря на экране (common.*, shell.*, together.* …);
 *   ru_in_kk (только ҚАЗ) русские подписи элементов интерфейса: кнопки, вкладки, заголовки, подписи полей, чипы, шапки
 *            таблиц (содержимое обращений и примеров — по-русски можно, оно не проверяется);
 *   nav      пункты капсулы меню против IA_ROUND15 §2–3 (на 1366 и 1024; на телефоне меню — в аватаре).
 * Итог: <OUT>/r15_screens.json и строки «ПРОБЛЕМА …» в выводе; код выхода 1, если есть scroll/keys/nav или cut на 375 kk.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const [BASE, OUT, PWFILE] = process.argv.slice(2);
if (!BASE || !OUT || !PWFILE) { console.error("node r15_screens.cjs <BASE> <OUT> <файл-пароля> [--only kk] [--quick]"); process.exit(2); }
const args = process.argv.slice(5);
const ONLY = args.includes("--only") ? args[args.indexOf("--only") + 1] : null;
const QUICK = args.includes("--quick");
const PASSWORD = fs.readFileSync(PWFILE, "utf8").trim();
fs.mkdirSync(OUT, { recursive: true });

const SIZES = QUICK ? [[1366, 768, 1], [375, 812, 2]] : [[1366, 768, 1], [1024, 768, 1], [375, 812, 2]];
const LANGS = ONLY ? [ONLY] : ["ru", "kk"];
// Разделы по IA_ROUND15 §2–5 (адрес #раздел/путь, R01 c2df555a). Нет модуля роли в сборке — кадр «раздел не подключён».
const ROUTES = {
  resident: ["map", "mine", "yard", "together", "meetings", "ideas", "crisis"],
  akimat: ["day", "inbox", "agencies", "agencies/joint", "agencies/handoffs", "agencies/calendar", "agencies/crisis",
    "together", "meetings", "analyst"],
};
// Капсула меню (IA §2–3): что ждём на 1366 и 1024; «Мой двор» / «Ведомства» — когда модуль роли в сборке.
const NAV = {
  resident: { ru: ["Карта", "Мои обращения", ["Мой двор", "Рядом"], "Идеи", "Ещё"],
    kk: ["Карта", "Менің өтініштерім", ["Менің аулам", "Маңайда"], "Идеялар", "Тағы"] },
  akimat: { ru: ["Карта", "Картина дня", "Обращения", ["Ведомства", "Проекты и идеи"], "Ещё"],
    kk: ["Карта", "Күн қорытындысы", "Өтініштер", ["Ведомстволар", "Жобалар мен идеялар"], "Тағы"] },
};
const KEY_RE = /\b(common|shell|together|agencies|crisis|wcal|meet|board|replay|analyst|notify|idea|works|joint|mine|inbox|complaint|staff|heat|akim|reply|handoff)\.[a-z0-9_]+(\.[a-z0-9_]+)*\b/;

async function shellReady(page) {
  await page.waitForFunction(() => window.BirgeShell && document.querySelector("#birge-header"), null, { timeout: 40000 });
  await page.evaluate(async () => { const I = window.BirgeI18n; if (I && I.ready) await I.ready; });
}

async function audit(page, lang, w, ruOnly) {
  return page.evaluate(({ lang, w, keySrc, ruOnly }) => {
    const KEY = new RegExp(keySrc);
    const RU = new Set(ruOnly);
    const vis = (e) => { if (!e.getClientRects().length) return false; const cs = getComputedStyle(e);
      return cs.visibility !== "hidden" && cs.display !== "none" && +cs.opacity !== 0; };
    const CHROME = "button, [role=tab], [role=menuitem], h1, h2, h3, label, th, .bk-chip, .bk-btn, .bk-tag, legend, summary";
    const out = { scroll: Math.max(0, document.documentElement.scrollWidth - innerWidth), cut: [], cut_rows: [], keys: [], ru_in_kk: [] };
    const scope = [...document.querySelectorAll("#birge-header, #birge-screen:not([hidden]), #birge-day:not([hidden]), #birge-alert, .bk-notify, #civic-root")];
    const seen = new Set();
    for (const root of scope) for (const e of root.querySelectorAll("*")) {
      if (seen.has(e) || e.closest("svg, canvas, .maplibregl-map, [aria-hidden=true]")) continue; seen.add(e);
      if (!vis(e)) continue;
      const cs = getComputedStyle(e);
      const rect = e.getBoundingClientRect();
      if (rect.width <= 2 || rect.height <= 2 || (cs.clip && cs.clip !== "auto") || /inset\(50%/.test(cs.clipPath || "")) continue;  // только для диктора
      const own = [...e.childNodes].filter((n) => n.nodeType === 3).map((n) => n.nodeValue).join(" ").replace(/\s+/g, " ").trim();
      // обрезка — только у элемента, в котором сам текст (не у контейнера со скруглением и overflow: hidden)
      // многоточие без overflow: hidden ничего не режет (у R09 на телефоне название переносится, overflow: visible)
      const clips = /hidden|clip/.test(cs.overflowX) || /hidden|clip/.test(cs.overflow);
      const hCut = clips && e.clientWidth > 0 && e.scrollWidth > e.clientWidth + 1;
      const vCut = cs.webkitLineClamp !== "none" && e.scrollHeight > e.clientHeight + 2;
      if (own && (hCut || vCut) && !e.closest(".bk-tabs, .bk-scroll-x, [data-more]")) {
        const item = ((e.className && e.className.toString()) || e.tagName).slice(0, 40) + ": " + e.textContent.trim().slice(0, 50);
        // подпись интерфейса (кнопка, вкладка, заголовок, поле, чип) — обрезать нельзя; строка данных с многоточием — смотреть глазами
        const ctl = e.closest("button, [role=tab], label, th, h1, h2, h3");
        (e.matches(CHROME) || (ctl && ctl.textContent.trim() === e.textContent.trim()) ? out.cut : out.cut_rows).push(item);
      }
      if (own && KEY.test(own)) out.keys.push(own.slice(0, 60));
      // ҚАЗ: подпись интерфейса совпадает с русским значением словаря (у ключа есть другой казахский) — не переведено
      if (lang === "kk" && own && RU.has(own)) out.ru_in_kk.push(own.slice(0, 50));
    }
    out.cut = [...new Set(out.cut)].slice(0, 12); out.cut_rows = [...new Set(out.cut_rows)].slice(0, 12); out.keys = [...new Set(out.keys)].slice(0, 12); out.ru_in_kk = [...new Set(out.ru_in_kk)].slice(0, 12);
    out.nav = [...document.querySelectorAll("#birge-header .birge-nav > button")].filter(vis).map((b) => b.textContent.trim());
    out.header = document.body.dataset.birgeHeader || "inline";
    out.section = window.BirgeShell && BirgeShell.section;
    out.title = (document.querySelector("#birge-screen:not([hidden]) #birge-screen-title, #birge-day:not([hidden]) #birge-day-title") || {}).textContent || "";
    return out;
  }, { lang, w, keySrc: KEY_RE.source, ruOnly });
}

function navProblem(mode, lang, nav) {
  const want = NAV[mode][lang];
  if (nav.length !== want.length) return `ожидалось ${want.length} пунктов, есть ${nav.length}: ${nav.join(" · ")}`;
  for (let i = 0; i < want.length; i++) {
    const ok = Array.isArray(want[i]) ? want[i].includes(nav[i]) : want[i] === nav[i];
    if (!ok) return `пункт ${i + 1}: «${nav[i]}», ожидалось «${[].concat(want[i]).join(" / ")}»`;
  }
  return null;
}

(async () => {
  const browser = await chromium.launch();
  const report = { base: BASE, when: new Date().toISOString(), frames: {}, problems: [] };
  const probe = await browser.newPage();
  await probe.goto(BASE + "/civic/i18n/ru.json");
  const ruOnly = await probe.evaluate(async () => {
    const [ru, kk] = await Promise.all(["ru", "kk"].map((l) => fetch(`/civic/i18n/${l}.json`).then((r) => r.json())));
    const out = new Set();
    for (const k of Object.keys(ru)) {
      const z = kk[k], vals = typeof ru[k] === "string" ? [ru[k]] : Object.values(ru[k] || {});
      const zs = typeof z === "string" ? [z] : Object.values(z || {});
      for (const v of vals) if (typeof v === "string" && v.trim().length >= 3 && !v.includes("{") && !zs.includes(v)) out.add(v.trim());
    }
    return [...out];
  });
  await probe.close();
  for (const [w, h, dpr] of SIZES) for (const lang of LANGS) for (const mode of ["resident", "akimat"]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: dpr });
    await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); localStorage.setItem("birge.i18n.lang", l); } catch (e) { /* приватный режим */ } }, [mode, lang]);
    const page = await ctx.newPage();
    const errors = []; page.on("pageerror", (e) => errors.push(String(e).slice(0, 160)));
    await page.goto(BASE + "/"); await shellReady(page);
    if (mode === "akimat") {
      const ok = await page.evaluate(async (pw) => (await fetch("/api/civic/v1/session/login", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "operator", password: pw }) })).ok, PASSWORD);
      if (!ok) report.problems.push(`${w}-${lang}: вход сотрудника не удался`);
    }
    for (const route of ROUTES[mode]) {
      const tag = `${w}-${lang}-${mode}-${route.replace(/\//g, "_")}`;
      await page.goto(BASE + "/#" + route); await shellReady(page);
      await page.evaluate((l) => { const I = window.BirgeI18n; if (I && I.getLang && I.getLang() !== l && I.setLang) I.setLang(l); }, lang);
      await page.waitForTimeout(1600);
      await page.screenshot({ path: path.join(OUT, tag + ".jpg"), type: "jpeg", quality: 78 });
      const a = await audit(page, lang, w, ruOnly);
      a.errors = errors.splice(0);
      report.frames[tag] = a;
      if (a.scroll) report.problems.push(`${tag}: горизонтальная прокрутка ${a.scroll} px`);
      if (a.keys.length) report.problems.push(`${tag}: сырые ключи ${a.keys.join(" | ")}`);
      if (a.cut.length && (w === 375 && lang === "kk")) report.problems.push(`${tag}: обрезано ${a.cut.join(" | ")}`);
      if (a.errors.length) report.problems.push(`${tag}: ошибки JS ${a.errors.join(" | ")}`);
      if (w !== 375 && route === ROUTES[mode][0]) {
        const p = a.header === "compact" ? "разделы ушли в меню аватара (data-birge-header=compact)" : navProblem(mode, lang, a.nav);
        if (p) report.problems.push(`${tag}: меню — ${p}`);
      }
    }
    await ctx.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, "r15_screens.json"), JSON.stringify(report, null, 1));
  const frames = Object.keys(report.frames).length;
  for (const p of report.problems) console.log("ПРОБЛЕМА " + p);
  const soft = Object.entries(report.frames).filter(([, a]) => a.cut.length || a.cut_rows.length || a.ru_in_kk.length);
  for (const [tag, a] of soft) console.log(`смотреть ${tag}:` + (a.cut.length ? ` обрезано [${a.cut.join(" | ")}]` : "")
    + (a.cut_rows.length ? ` строки с многоточием [${a.cut_rows.slice(0, 4).join(" | ")}]` : "") + (a.ru_in_kk.length ? ` русские подписи [${a.ru_in_kk.join(" | ")}]` : ""));
  console.log(`кадров ${frames}, проблем ${report.problems.length}; кадров «смотреть глазами»: ${soft.length}`);
  process.exit(report.problems.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
