/*
 * R08 · браузерная проверка экрана «Что делают рядом» (волна 2 п. 4, схема R11 IA_WAVE2 §4): web/civic/nearby/.
 *
 *   python tests/civic/R08/demo_server.py --kit-dir <папка R11> &
 *   NODE_PATH=$(npm root -g) node tests/civic/R08/nearby_check.cjs [base_url] [папка_скриншотов]
 *
 * 1366×768 и 375×812, ru/kk: нет горизонтальной прокрутки страницы, ключей перевода и предупреждений; зоны нажатия
 * ≥ 44 px; вкладки в одну строку (на 375 в kk — прокрутка вкладок, без переноса); баннеров отключений ≤ 2, у отключения
 * — где, когда, источник и «обновлено …»; задержка видна («срок перенесён»); «Зачем?» раскрывает 4 строки с клавиатуры;
 * одна главная кнопка; подписка на район и на карточку (POST с номером устройства, как у R09) остаётся после
 * перезагрузки; пустой район — «Рядом сейчас ничего не делают»; нет связи — «Повторить»; геолокацию не спрашиваем.
 * Итог — nearby_check.json; код выхода 1, если есть FAIL.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = (process.argv[2] || "http://127.0.0.1:8508").replace(/\/$/, "");
const OUT = process.argv[3] || path.join(__dirname, "../../../research/round-14-results/R08/screens");
const PAGE = BASE + "/civic/nearby/";
fs.mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail) {
  results.push({ name, status: ok ? "PASS" : "FAIL", detail: ok ? undefined : detail });
  console.log((ok ? "PASS " : "FAIL ") + name + (!ok && detail != null ? " — " + JSON.stringify(detail) : ""));
}
const KEYLIKE = /\b(nearby|works|common|service|district|heat|map)\.[a-z_]+(\.[a-z_]+)*\b/;

async function open(browser, w, h, lang, extra) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, permissions: [] });
  const page = await ctx.newPage();
  const logs = [];
  page.on("console", (m) => ["warning", "error"].includes(m.type()) && logs.push(m.text()));
  page.on("pageerror", (e) => logs.push(e.message));
  await page.addInitScript(() => {
    window.__geo = 0;
    if (navigator.geolocation) navigator.geolocation.getCurrentPosition = () => { window.__geo++; };
  });
  if (extra) await extra(page);
  await page.goto(PAGE + "?lang=" + lang);
  return { ctx, page, logs };
}

(async () => {
  const browser = await chromium.launch();
  for (const [w, h] of [[1366, 768], [375, 812]]) {
    for (const lang of ["ru", "kk"]) {
      const tag = `${w}-${lang}`;
      const { ctx, page, logs } = await open(browser, w, h, lang);
      await page.waitForSelector(".nb[data-state=ok]");
      await page.screenshot({ path: path.join(OUT, `nearby-${tag}.png`) });
      await page.screenshot({ path: path.join(OUT, `nearby-${tag}-full.jpg`), fullPage: true, type: "jpeg", quality: 70 });
      const info = await page.evaluate(() => {
        const q = (s) => Array.from(document.querySelectorAll(s));
        const tabs = q(".nb-tabs > button");
        return {
          hscroll: document.documentElement.scrollWidth - innerWidth,
          text: document.querySelector(".nb").innerText,
          banners: q(".nb-banner").map((b) => b.innerText),
          tabs: tabs.length,
          tabHeights: tabs.map((b) => Math.round(b.getBoundingClientRect().height)),
          tiny: q(".nb a, .nb button, .nb select, .nb summary").filter((e) => e.getClientRects().length && e.getBoundingClientRect().height < 44)
            .map((e) => e.className || e.tagName),
          primary: q(".bk-btn--primary").length,
          late: q(".nb-card__late").length,
          small: q(".nb *").filter((e) => Array.from(e.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 13)
            .map((e) => e.textContent.trim().slice(0, 20)),
          geo: window.__geo,
        };
      });
      const kk = lang === "kk";
      check(`${tag}: нет горизонтальной прокрутки страницы`, info.hscroll <= 0, info.hscroll);
      check(`${tag}: нет ключей перевода и предупреждений`, !KEYLIKE.test(info.text) && logs.length === 0, [(info.text.match(KEYLIKE) || [])[0], logs]);
      check(`${tag}: зоны нажатия ≥ 44 px, шрифт ≥ 13 px (шкала R11)`, info.tiny.length === 0 && info.small.length === 0, [info.tiny, info.small]);
      check(`${tag}: 4 вкладки в одну строку`, info.tabs === 4 && info.tabHeights.every((x) => x <= 48), info.tabHeights);
      check(`${tag}: баннеров отключений ≤ 2, в баннере где, когда, источник и «обновлено»`,
        info.banners.length >= 1 && info.banners.length <= 2 &&
          info.banners.every((b) => (kk ? /Қай жерде: .+[\s\S]*Дереккөз: .+жаңартылды/ : /Где: .+[\s\S]*Источник: .+обновлено/).test(b) && /\d\d:\d\d–\d\d:\d\d/.test(b)),
        info.banners);
      check(`${tag}: задержки видны — «${kk ? "мерзімі ауыстырылды" : "срок перенесён"}»`, info.late >= 1 && info.text.includes(kk ? "мерзімі ауыстырылды" : "срок перенесён"), info.late);
      check(`${tag}: одна главная кнопка — «${kk ? "Ауданды бақылау" : "Следить за районом"}»`, info.primary === 1 && info.text.includes(kk ? "Ауданды бақылау" : "Следить за районом"), info.primary);
      check(`${tag}: геолокацию не спрашиваем`, info.geo === 0, info.geo);
      // Чистый стиль R11 (CLEAN_PASS §2, разбор FINAL-3 п. 9): вкладки .bk-tabs (role=tab), «Зачем?» — .bk-details,
      // строки без карточек, поле района с заливкой, «Пример» — одна строка внизу.
      const clean = await page.evaluate(() => {
        const q = (s) => Array.from(document.querySelectorAll(s));
        const sel = getComputedStyle(document.querySelector(".nb__select"));
        const foot = document.querySelector(".nb .bk-footnote");
        const last = Array.from(document.querySelector(".nb").children).pop();
        return { tabs: q(".nb .bk-tabs[role=tablist] > [role=tab]").length, selected: q(".nb [role=tab][aria-selected=true]").length,
                 panel: !!document.querySelector(".nb [role=tabpanel]"), why: q(".nb-why").every((d) => d.classList.contains("bk-details")),
                 cards: q(".nb .bk-card").length, demoTags: q(".nb .bk-tag--demo, .nb .bk-tag").length,
                 selectBorder: sel.borderTopColor, selectBg: sel.backgroundColor, foot: foot ? foot.textContent : "", footLast: last === foot };
      });
      check(`${tag}: чистый стиль — вкладки bk-tabs, «${kk ? "Не үшін?" : "Зачем?"}» bk-details, без карточек и плашек, «Пример» одной строкой внизу`,
        clean.tabs === 4 && clean.selected === 1 && clean.panel && clean.why && clean.cards === 0 && clean.demoTags === 0
          && /rgba\(0, 0, 0, 0\)|transparent/.test(clean.selectBorder) && clean.footLast
          && clean.foot === (kk ? "Көрсетуге арналған үлгі, нақты дерек емес" : "Пример для показа, не настоящие данные"), clean);
      // «Зачем?» с клавиатуры: фокус на summary, Enter раскрывает 4 строки
      await page.focus(".nb-why summary");
      await page.keyboard.press("Enter");
      const why = await page.$$eval(".nb-why[open] dt", (els) => els.map((e) => e.textContent));
      check(`${tag}: «${kk ? "Не үшін?" : "Зачем?"}» с клавиатуры — 4 строки`, why.length === 4, why);
      // Вкладки с клавиатуры: ← / → (BirgeUI.tabs)
      await page.focus('.nb [role=tab][aria-selected=true]');
      const before = await page.getAttribute('.nb [role=tab][aria-selected=true]', "data-value");
      await page.keyboard.press("ArrowRight");
      const afterKey = await page.evaluate(() => [document.querySelector('.nb [role=tab][aria-selected=true]').getAttribute("data-value"),
        document.activeElement && document.activeElement.getAttribute("data-value")]);
      check(`${tag}: вкладки стрелкой → — следующая вкладка выбрана и в фокусе`, afterKey[0] !== before && afterKey[0] === afterKey[1], [before, afterKey]);
      // Вкладка «Отключения»
      await page.click('[data-key="tab:outages"]');
      const outs = await page.$$eval('.nb-card[data-tab="outages"]', (els) => els.map((e) => e.innerText));
      check(`${tag}: вкладка «Отключения» — зона, время, источник`, outs.length >= 1 && outs.every((t) => (kk ? /Қашан: .+\d\d:\d\d[\s\S]*Қай жерде:[\s\S]*Дереккөз:/ : /Когда: .+\d\d:\d\d[\s\S]*Где:[\s\S]*Источник:/).test(t)), outs.map((t) => t.slice(0, 80)));
      if (w === 375) await page.screenshot({ path: path.join(OUT, `nearby-${tag}-outages.png`) });
      await ctx.close();
    }
  }
  {
    // Смена района при показанной ленте: без мигания скелетом — прежнее приглушено, полоса загрузки, потом новое.
    const { ctx, page } = await open(browser, 1366, 768, "ru");
    await page.waitForSelector(".nb[data-state=ok]");
    await page.route("**/api/civic/v2/nearby?**", async (route) => { await new Promise((r) => setTimeout(r, 900)); await route.continue(); });
    const other = await page.evaluate(() => Array.from(document.querySelectorAll("#nb-district option")).map((o) => o.value).find((v) => v !== document.querySelector("#nb-district").value));
    await page.selectOption("#nb-district", other);
    await page.waitForTimeout(250);
    const mid = await page.evaluate(() => ({ state: document.querySelector(".nb").dataset.state, pending: document.querySelector(".nb").hasAttribute("data-pending"),
      skel: document.querySelectorAll(".nb .bk-skel").length, tabs: document.querySelectorAll(".nb [role=tab]").length,
      op: getComputedStyle(document.querySelector(".nb [role=tablist]")).opacity }));
    await page.waitForSelector(".nb[data-state=ok]");
    const end = await page.evaluate(() => document.querySelector(".nb").hasAttribute("data-pending"));
    check("смена района: без мигания — прежняя лента приглушена, без скелета, затем новая", mid.state === "loading" && mid.pending && mid.skel === 0
      && mid.tabs === 4 && parseFloat(mid.op) < 0.6 && !end, { mid, end });
    await ctx.close();
  }
  {
    // Подписка на карточку и на район: POST с номером устройства R09, видно после перезагрузки.
    const { ctx, page } = await open(browser, 1366, 768, "ru");
    await page.waitForSelector(".nb[data-state=ok]");
    const posts = [];
    page.on("request", (r) => r.method() === "POST" && r.url().includes("/nearby/subscriptions") && posts.push(JSON.parse(r.postData())));
    const first = await page.getAttribute(".nb-card__sub >> nth=0", "data-key");
    await page.click(".nb-card__sub >> nth=0");
    await page.waitForSelector(`[data-key="${first}"][aria-pressed="true"]`);
    await page.click('[data-key="follow"]');
    await page.waitForSelector(".nb-follow__done");
    await page.reload();
    await page.waitForSelector(".nb[data-state=ok]");
    const after = await page.evaluate((k) => ({ item: document.querySelector(`[data-key="${k}"]`).getAttribute("aria-pressed"),
      district: !!document.querySelector(".nb-follow__done"), device: localStorage.getItem("birge.device") }), first);
    check("подписка: карточка и район, номер устройства как у R09, остаётся после перезагрузки",
      posts.length === 2 && posts.every((p) => p.device_id === after.device && /^[A-Za-z0-9_-]{16,80}$/.test(p.device_id)) &&
        posts[0].scope === "item" && posts[1].scope === "district" && after.item === "true" && after.district,
      { posts, after });
    await page.screenshot({ path: path.join(OUT, "nearby-1366-ru-subscribed.png") });
    // отписаться — вернуть стенд как было
    await page.click('[data-key="follow"]');
    await page.waitForSelector(".nb-follow .bk-btn--primary");
    await page.click(`[data-key="${first}"]`);
    await page.waitForSelector(`[data-key="${first}"][aria-pressed="false"]`);
    check("подписка: «Отписаться» возвращает главную кнопку", (await page.$$(".bk-btn--primary")).length === 1);
    await ctx.close();
  }
  {
    // Пустой район и нет связи.
    const { ctx, page } = await open(browser, 375, 812, "kk", (p) =>
      p.route("**/api/civic/v2/nearby?*", (route) => route.fulfill({ json: { district: "saraishyk", tabs: { now: 0, done: 0, planned: 0, outages: 0 }, items: [], banners: [], demo: false } })));
    await page.waitForSelector(".nb[data-state=ok]");
    const t = await page.textContent(".nb");
    check("пусто: «Қазір маңайда жұмыс жүріп жатқан жоқ», без баннеров", t.includes("Қазір маңайда жұмыс жүріп жатқан жоқ") && !(await page.$(".nb-banner")), t.slice(0, 120));
    await page.screenshot({ path: path.join(OUT, "nearby-375-kk-empty.png") });
    await ctx.close();
    let fail = true;
    const r = await open(browser, 1366, 768, "ru", (p) => p.route("**/api/civic/v2/nearby?*", (route) => (fail ? route.abort("internetdisconnected") : route.continue())));
    await r.page.waitForSelector(".nb[data-state=error]");
    fail = false;
    await r.page.click(".bk-error .bk-btn");
    await r.page.waitForSelector(".nb[data-state=ok]");
    check("нет связи: понятный текст и «Повторить» возвращает ленту", (await r.page.$$(".nb-card")).length > 0);
    await r.ctx.close();
  }
  await browser.close();
  const failed = results.filter((r) => r.status === "FAIL").length;
  fs.writeFileSync(path.join(OUT, "nearby_check.json"), JSON.stringify({ base: BASE, total: results.length, failed, results }, null, 1));
  console.log(`\n${results.length - failed}/${results.length} PASS`);
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error(e);
  process.exit(2);
});
