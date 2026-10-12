// R07 волны 1–2 в браузере: «служба сообщила» (пунктир) / «проверено жителями» / «вернули жители» (↺), легенда растёт
// только по делу, серые районы «нет свежих данных», срок ответа в рабочих днях, светофор / переход / перекрёсток,
// статус по каждому обращению (404/422 у одного не обрывают остальные).
// Запуск: python -m ui.civic_heat.devserver &   затем
//   NODE_PATH=$(npm root -g) node tests/civic/R07/browser/wave2.js [папка]
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.R07_BASE || "http://127.0.0.1:8617/civic/heat/demo.html";
const API = BASE.replace(/\/civic\/heat\/demo\.html.*$/, "") + "/api/civic/v2";
const OUT = process.argv[2] || path.join(__dirname, "..", "..", "..", "..", "research", "round-14-results", "R07", "screens", "wave2");
fs.mkdirSync(OUT, { recursive: true });
const SIZES = { 1366: { width: 1366, height: 768 }, 375: { width: 375, height: 812 } };
const results = [];
const check = (name, problems, extra) => {
  results.push({ name, pass: !problems.length, problems, extra });
  console.log((problems.length ? "FAIL " : "PASS ") + name + (problems.length ? " · " + problems.join("; ") : ""));
};

async function open(browser, size, lang, query) {
  const page = await browser.newPage({ viewport: SIZES[size], deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${BASE}?lang=${lang}&role=akimat${query || ""}`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
  await page.waitForTimeout(800);
  return { page, errors };
}
const card = (page) => page.evaluate(() => ({
  status: document.querySelector(".r07-card .r07-status")?.dataset.status || null,
  statusText: document.querySelector(".r07-card .r07-status")?.innerText || "",
  // Чистый дизайн (FINAL-3): статус один раз — точка + слово + одна строка пояснения (.r07-statusline__note)
  statuses: document.querySelectorAll(".r07-card .bk-status").length,
  notes: [...document.querySelectorAll(".r07-card .r07-statusline__note")].map((n) => n.innerText),
  due: document.querySelector(".r07-card .r07-statusline__note")?.innerText || null,
  eyebrow: document.querySelector(".r07-eyebrow")?.textContent || "",
  // уточнение: в «О чём сообщают» (тем больше одной) или в строке «Тема · Сообщили …» (одна тема)
  topics: [...document.querySelectorAll(".r07-topics__sub, .r07-card__topic")].map((x) => x.innerText),
  legend: [...document.querySelectorAll(".r07-maplegend li")].map((l) => l.dataset.extra || "base"),
  badge: (() => { const b = document.querySelector(".r07-badge--selected"); return b ? { fixed: b.dataset.fixed || null, mark: !!b.querySelector(".r07-badge__mark"),
    border: getComputedStyle(b.querySelector(".r07-badge__dot")).borderStyle, aria: b.getAttribute("aria-label") } : null; })(),
}));

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
  const items = (await (await fetch(API + "/heat?days=30&zoom=15")).json()).items;
  const keyOf = (it) => it.target.kind + ":" + it.target.id;
  const pick = {
    reported: items.find((it) => it.state === "fixed" && it.fixed_kind === "reported" && it.target.kind === "object"),
    verified: items.find((it) => it.state === "fixed" && it.fixed_kind === "verified"),
    reopened: items.find((it) => it.reopened),
    signal: items.find((it) => it.target.subtype === "traffic_signal"),
    crossing: items.find((it) => it.target.subtype === "crossing"),
    intersection: items.find((it) => it.target.subtype === "intersection"),
    due: items.find((it) => it.due && it.status === "new"),
  };
  const missing = Object.entries(pick).filter(([, v]) => !v).map(([k]) => k);
  check("demo-has-all-states", missing.length ? ["в демо нет: " + missing.join(", ")] : [], Object.fromEntries(Object.entries(pick).map(([k, v]) => [k, v && keyOf(v)])));

  for (const size of [1366, 375]) for (const lang of ["ru", "kk"]) {
    const tag = `${size}-${lang}`;
    for (const [name, it] of Object.entries(pick)) {
      if (!it) continue;
      const { page, errors } = await open(browser, size, lang, "&view=nura" + (size === 375 ? "&sheet=full" : ""));
      await page.evaluate(([k, id]) => window.__heat.focusTarget(k, id), [it.target.kind, it.target.id]);
      await page.waitForTimeout(2200);
      const c = await card(page);
      const p = [];
      if (c.statuses !== 1) p.push("статус в карточке не один раз: " + c.statuses);
      if (name === "reported") {
        if (c.status !== "reported_fixed") p.push("статус не «служба сообщила»: " + c.status);
        if (!c.badge || c.badge.fixed !== "reported" || c.badge.border !== "dashed") p.push("значок без пунктира: " + JSON.stringify(c.badge));
        if (!c.legend.includes("reported")) p.push("в легенде нет «сообщили об устранении», хотя такая цель на карте");
        if (!c.notes.some((n) => (lang === "kk" ? /тексеруін күтуде/i : /ждёт проверки/i).test(n))) p.push("нет строки «ждёт проверки»");
        // до проверки жителями — без «На карте зелёным до …» (R10 W2-1, R11 разбор 13 п. 2)
        if (c.notes.some((n) => (lang === "kk" ? /Жасыл түспен/ : /зелёным до/).test(n))) p.push("до проверки обещает «зелёным до …»");
      }
      if (name === "verified") {
        if (c.status !== "verified") p.push("статус не «проверено жителями»: " + c.status);
        if (!c.badge || c.badge.fixed !== "verified" || c.badge.border === "dashed") p.push("значок проверенного с пунктиром");
        if (!c.notes.some((n) => (lang === "kk" ? /растады/ : /Подтвердил/).test(n))) p.push("нет строки «подтвердили N жителей»");
      }
      if (name === "reopened") {
        if (!c.badge || !c.badge.mark) p.push("нет отметки ↺ на значке");
        if (!c.notes.some((n) => (lang === "kk" ? /қайтарды/ : /вернули жители/).test(n))) p.push("нет строки «вернули жители»");
        if (!c.badge || !(lang === "kk" ? /қайтарды/ : /вернули/).test(c.badge.aria)) p.push("aria-label без «вернули жители»");
      }
      if (["signal", "crossing", "intersection"].includes(name)) {
        const word = { signal: lang === "kk" ? /Бағдаршам/ : /Светофор/, crossing: lang === "kk" ? /өткелі/ : /переход/i, intersection: lang === "kk" ? /Қиылыс/ : /Перекрёсток/ }[name];
        if (!word.test(c.eyebrow)) p.push("над названием не тот тип: " + c.eyebrow);
        const sub = it.top_subtopic && it.top_subtopic[lang];
        if (!c.topics.length || (sub && !c.topics.some((x) => x.includes(sub)))) p.push("в карточке нет уточнения «" + sub + "»: " + c.topics.join(" | "));
      }
      if (name === "due") {
        if (!c.due || !(lang === "kk" ? /жұмыс күні|бүгін|кешікті/ : /рабоч|сегодня|Просрочено/).test(c.due)) p.push("нет строки срока: " + c.due);
      }
      await page.screenshot({ path: path.join(OUT, `${tag}-${name}.png`) });
      check(`${name}-${tag}`, p.concat(errors), c);
      await page.close();
    }
    // серые районы: фильтр «Запахи» → на обзоре города районы без жалоб серые, в легенде «нет свежих данных»
    {
      const { page, errors } = await open(browser, size, lang, "&view=city" + (size === 375 ? "&sheet=peek" : ""));
      await page.evaluate(() => document.querySelector("[data-cats-toggle]").click());
      await page.waitForTimeout(300);
      await page.click('[data-cat="smell_air"]');
      await page.waitForTimeout(1500);
      await page.evaluate(() => window.__map.jumpTo({ center: [71.43, 51.135], zoom: 10 }));
      await page.waitForTimeout(2000);
      const r = await page.evaluate(() => ({ mode: window.__heat.state().mode,
        legend: [...document.querySelectorAll(".r07-maplegend li")].map((l) => l.dataset.extra || "base"),
        badges: window.__heat.badges().map((b) => b.key), fill: window.__map.getPaintProperty("r07-district-fill", "fill-opacity") }));
      const nodata = (await (await fetch(API + "/heat?days=30&zoom=10&category=smell_air")).json()).items.filter((x) => x.state === "no_data").map(keyOf);
      const p = [];
      if (r.mode !== "districts") p.push("не обзор города");
      if (!nodata.length) p.push("в данных нет районов без жалоб");
      if (!r.legend.includes("nodata")) p.push("в легенде нет «нет свежих данных»");
      if (r.badges.some((k) => nodata.includes(k))) p.push("у серого района есть значок с числом");
      await page.screenshot({ path: path.join(OUT, `${tag}-nodata.png`) });
      check(`nodata-${tag}`, p.concat(errors), { nodata: nodata.length });
      await page.close();
    }
  }
  // Первый кадр: легенда как прежде (5 пунктов), новых пунктов по умолчанию нет
  for (const size of [1366, 375]) {
    const { page, errors } = await open(browser, size, "kk", size === 375 ? "&sheet=peek" : "");
    await page.waitForTimeout(1500);
    const legend = await page.evaluate(() => [...document.querySelectorAll(".r07-maplegend li")].map((l) => l.dataset.extra || "base"));
    check(`first-frame-legend-${size}`, legend.length === 5 && !legend.some((x) => x !== "base") ? errors : ["легенда первого кадра: " + legend.join(",")].concat(errors), { legend });
    await page.close();
  }
  // Смена роли пересоздаёт слои: без предупреждений MapLibre «source cannot be removed» (тесты R01 ловят любые warning)
  {
    const page = await browser.newPage({ viewport: SIZES[1366] });
    const warns = [];
    // шум среды (WebGL в облаке) — не про модуль; ловим предупреждения карты и модуля
    page.on("console", (m) => { if ((m.type() === "warning" || m.type() === "error") && !/WebGL|GroupMarkerNotSet|swiftshader/i.test(m.text())) warns.push(m.text()); });
    await page.goto(`${BASE}?lang=ru&role=akimat&view=nura`, { waitUntil: "networkidle" });
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.evaluate(() => { window.__heat.setRole("resident"); window.__heat.setRole("akimat"); });
    await page.waitForTimeout(1200);
    const layers = await page.evaluate(() => window.__map.getStyle().layers.filter((l) => l.id.startsWith("r07-")).length);
    check("role-switch-no-warnings", warns.length || layers < 10 ? ["предупреждения: " + warns.slice(0, 3).join(" | ") + ", слоёв r07: " + layers] : [], { layers });
    await page.close();
  }
  // Статус по каждому обращению (R12): 404 у первого не обрывает остальные; все 422 — «статус уже изменён»
  for (const mode of ["first404", "all422"]) {
    const { page, errors } = await open(browser, 1366, "ru", "&view=nura");
    let posts = 0;
    await page.route(/\/complaints\/[^/]+\/status/, async (r) => {
      posts += 1;
      if (mode === "all422" || posts === 1) return r.fulfill({ status: mode === "all422" ? 422 : 404, contentType: "application/json", body: '{"error":"x"}' });
      return r.continue();
    });
    // разные цели: первая проверка меняет статус на стенде (сервер помнит)
    const cands = items.filter((it) => it.state === "active" && (it.open_ids || []).length >= 2 && it.status !== "in_progress");
    const many = cands[mode === "first404" ? 0 : 1];
    await page.evaluate(([k, id]) => window.__heat.focusTarget(k, id), [many.target.kind, many.target.id]);
    await page.waitForTimeout(1800);
    await page.click(mode === "first404" ? '[data-act="take"]' : '[data-act="fixed"]');
    await page.waitForTimeout(1500);
    const toastText = await page.evaluate(() => [...document.querySelectorAll(".r07-toast, .bk-toast, [role=status]")].map((x) => x.innerText).join(" | "));
    const p = [];
    if (posts < many.open_ids.length) p.push(`отправлено ${posts} из ${many.open_ids.length}`);
    if (mode === "first404" && !/работ/i.test(toastText)) p.push("нет сообщения об успехе: " + toastText);
    if (mode === "first404" && /не найдено/i.test(toastText)) p.push("показано «не найдено», хотя остальные обновились");
    if (mode === "all422" && !/уже изменён/.test(toastText)) p.push("нет «статус уже изменён»: " + toastText);
    if (/Проверьте связь/.test(toastText)) p.push("показано «Проверьте связь»");
    // ответы 404/422 подставлены самим тестом — их строка в консоли браузера не ошибка модуля
    check(`status-per-id-${mode}`, p.concat(errors.filter((e) => !/status of (404|422)/.test(e))), { posts, open: many.open_ids.length });
    await page.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, "wave2.json"), JSON.stringify(results, null, 1));
  const failed = results.filter((r) => !r.pass).length;
  console.log(failed ? `FAIL ${failed}/${results.length}` : `PASS ${results.length}/${results.length}`);
  process.exit(failed ? 1 : 0);
})();
