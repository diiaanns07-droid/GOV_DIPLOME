// R06 волна 2 в НАСТОЯЩЕЙ сборке R01: «Идеи жителей» (п. 7), «Проекты и идеи» акимата, «Работы и отключения» (п. 4).
//
//   TR=$(mktemp -d); git archive origin/claude/sharp-dijkstra-0t87gl | tar -x -C $TR      # дерево сборки
//   cp -r ui/civic_store web/civic/proposals web/civic/ideas tests/civic/R06 → $TR (пути R06 этой ветки)
//   (cd $TR && patch -p1 < research/round-14-results/R06/r01_wave2_r06.patch)           # маршруты, файлы, index.html
//   NODE_PATH="$(npm root -g)" node tests/civic/R06/round14/app_r01_wave2.cjs $TR [папка-скриншотов]
//
// Сервер — python3 -B app.py дерева с CIVIC_DEMO=1 на временной базе (как run-city.bat) + сотрудник для проверки.
// На каждую пару (ширина, язык) — свежий сервер: прогон меняет демо-данные (публикует, отклоняет, создаёт проект).
// Демо-идеи и работы — synthetic, помечены «Пример»; ничего не пишется в базу владельца.
"use strict";
const { chromium } = require("playwright");
const { spawn, execSync } = require("child_process");
const net = require("net"), fs = require("fs"), path = require("path"), os = require("os"), crypto = require("crypto");

const ROOT = path.resolve(process.argv[2] || ".");
const OUT = process.argv[3] ? path.resolve(process.argv[3]) : null;
if (OUT) fs.mkdirSync(OUT, { recursive: true });
const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok: !!ok });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail && !ok ? " — " + String(detail).slice(0, 500) : ""));
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = () => new Promise((ok, no) => { const s = net.createServer().on("error", no); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => ok(port)); }); });
const PASSWORD = "Tulpar-" + crypto.randomBytes(9).toString("base64url") + "-2026";
// Слова, которых не должно быть в ҚАЗ (русские подписи и служебные слова).
const RU_WORDS = ["Поддержать", "Вы поддержали", "голос", "Пример", "Отклонена", "Стала проектом", "Идёт голосование",
  "Предложить идею", "Подробнее", "Показать на карте", "Идеи жителей", "Причина отказа", "Можно доработать", "На проверке",
  "Сквер", "Фонтан", "Беседка", "Спортплощадка", "Велопарковка"];
const TECH = ["undefined", "null", "NaN", "idea.", "works.", "proposal.", "[object", "Error:"];

async function start(port, db) {
  const env = { ...process.env, CIVIC_DB_PATH: db, CIVIC_DEMO: "1", PYTHONDONTWRITEBYTECODE: "1" };
  const run = (args, input) => execSync(`python3 -B -m ui.civic_store --db "${db}" ${args}`,
    { cwd: ROOT, env, input, stdio: [input ? "pipe" : "ignore", "ignore", "inherit"] });
  run("init");
  run("seed-demo --package data/civic/astana/demo_synthetic.json");
  run("seed-r14-demo");
  run("create-editor checker --password-stdin --public-label Акимат", PASSWORD + "\n");
  const srv = spawn("python3", ["-B", "app.py", "--host", "127.0.0.1", "--port", String(port)], { cwd: ROOT, env, stdio: ["ignore", "pipe", "pipe"] });
  srv.log = ""; srv.stdout.on("data", (d) => (srv.log += d)); srv.stderr.on("data", (d) => (srv.log += d));
  for (let i = 0; i < 150; i++) { try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return srv; } catch {} await sleep(200); }
  throw new Error("server did not start: " + srv.log.slice(-1500));
}

async function newPage(browser, width, lang, mode) {
  const ctx = await browser.newContext({ viewport: { width, height: width < 600 ? 812 : 768 }, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  await ctx.addInitScript(([m, l]) => { try { localStorage.setItem("birge.mode", m); localStorage.setItem("birge.lang", l); } catch (e) {} }, [mode, lang]);
  const page = await ctx.newPage();
  page.errs = [];
  page.on("pageerror", (e) => page.errs.push(e.message));
  return page;
}
async function shot(page, name) {
  if (OUT) await page.screenshot({ path: path.join(OUT, name + ".png"), fullPage: false });
}
// Видимый текст экрана раздела, ошибки вёрстки: горизонтальная прокрутка, мелкий шрифт, технические слова.
async function audit(page, sel) {
  return page.evaluate((sel) => {
    const root = document.querySelector(sel);
    const text = root ? root.innerText : "";
    const small = [];
    if (root) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const n = walker.currentNode, el = n.parentElement;
        if (!n.textContent.trim() || !el || !el.getClientRects().length) continue;
        const cs = getComputedStyle(el);
        if (cs.visibility === "hidden" || el.closest("[hidden]") || el.closest("details:not([open]) > :not(summary)")) continue;
        if (parseFloat(cs.fontSize) < 14) small.push(n.textContent.trim().slice(0, 30) + "@" + cs.fontSize);
      }
    }
    const primaries = root ? Array.from(root.querySelectorAll(".bk-btn--primary")).filter((b) => b.getClientRects().length).length : 0;
    return { text, small, primaries, overflow: document.scrollingElement.scrollWidth - innerWidth };
  }, sel);
}
const cardOf = (page, title) => page.locator(".ri-card", { hasText: title }).first();

async function resident(browser, base, width, lang, full) {
  const tag = `${width}-${lang}`;
  const T = lang === "kk"
    ? { title: "Тұрғындар идеялары", support: "Қолдау", supported: "Сіз қолдадыңыз", square: "Сығанақ көшесі маңындағы гүлзар",
      rejectedTab: "Қабылданбады", projectTab: "Жобаға айналды", fountain: "Аулада субұрқақ", reason: "Учаскеде су құбыры жоқ",
      improve: "Жетілдіруге болады", byRes: "Тұрғындар идеясы бойынша", honest: "шешімді әкімдік қабылдайды", newIdea: "Идея ұсыну",
      pick: "Картадан орын таңдау", review: "Тексерілуде", sent: "Идея жіберілді" }
    : { title: "Идеи жителей", support: "Поддержать", supported: "Вы поддержали", square: "Сквер у улицы Сыганак",
      rejectedTab: "Отклонена", projectTab: "Стала проектом", fountain: "Фонтан во дворе", reason: "нет водопровода",
      improve: "Можно доработать", byRes: "По идее жителей", honest: "решение принимает акимат", newIdea: "Предложить идею",
      pick: "Выбрать место на карте", review: "На проверке", sent: "Идея отправлена" };
  const page = await newPage(browser, width, lang, "resident");
  await page.goto(base + "#ideas");
  await page.waitForSelector(".ri .ri-card", { timeout: 30000 });
  await page.waitForTimeout(400);
  const a = await audit(page, ".ri");
  check(`${tag} житель: экран «${T.title}», честная строка всегда видна`, a.text.includes(T.title) && a.text.includes(T.honest), a.text.slice(0, 300));
  check(`${tag} житель: одна главная кнопка «${T.newIdea}»`, a.primaries === 1 && a.text.includes(T.newIdea), a.primaries);
  check(`${tag} житель: нет прокрутки вбок, текст ≥ 14 px`, a.overflow <= 1 && a.small.length === 0, a.overflow + " " + a.small.join(", "));
  check(`${tag} житель: нет технических слов`, !TECH.some((w) => a.text.includes(w)), TECH.filter((w) => a.text.includes(w)));
  if (lang === "kk") {
    const ru = RU_WORDS.filter((w) => a.text.includes(w));
    check(`${tag} житель: в ҚАЗ нет русских подписей и названий`, ru.length === 0, ru.join(", "));
  }
  check(`${tag} житель: карта по умолчанию без слоя идей`, await page.evaluate(() => !document.body.dataset.birgeLayer), "layer on");
  await shot(page, `w2-ideas-${tag}`);
  // Поддержка: +1 и обратно, счётчик с сервера.
  const card = cardOf(page, T.square);
  const votes = async () => Number(((await card.locator(".ri-votes").innerText()).match(/\d+/) || [0])[0]);
  const before = await votes();
  await card.locator(".ri-support").click();
  await page.waitForFunction((t) => Array.from(document.querySelectorAll(".ri-card")).some((c) => c.textContent.includes(t) && c.querySelector(".ri-support[aria-pressed=true]")), T.square);
  const after = await votes();
  check(`${tag} житель: «${T.support}» → ${before + 1}, «${T.supported}»`, after === before + 1 && (await card.innerText()).includes(T.supported), `${before} → ${after}`);
  await card.locator(".ri-support").click();
  await page.waitForFunction((t) => Array.from(document.querySelectorAll(".ri-card")).some((c) => c.textContent.includes(t) && c.querySelector(".ri-support[aria-pressed=false]")), T.square);
  check(`${tag} житель: повторное нажатие снимает поддержку`, (await votes()) === before, await votes());
  // Отклонённая — причина и «Можно доработать» видны сразу; проект — «По идее жителей».
  await page.locator(".ri-tabs button", { hasText: T.rejectedTab }).click();
  const rej = await cardOf(page, T.fountain).innerText();
  check(`${tag} житель: отказ с причиной и «${T.improve}»`, rej.includes(T.reason) && rej.includes(T.improve), rej);
  await page.locator(".ri-tabs button", { hasText: T.projectTab }).click();
  const proj = await page.locator(".ri-card").first().innerText();
  check(`${tag} житель: идея стала проектом — «${T.byRes} · 52»`, proj.includes(T.byRes) && proj.includes("52"), proj);
  // «Подробнее» — по клавиатуре (details/summary).
  await page.locator(".ri-card summary").first().focus();
  await page.keyboard.press("Enter");
  check(`${tag} житель: «Подробнее» раскрывается клавишей Enter`, await page.evaluate(() => !!document.querySelector(".ri-card details[open]")), "closed");
  if (full) {
    // Мастер: место на карте → название → объект → отправить → своя идея «на проверке».
    await page.locator(".ri-new .bk-btn--primary").click();
    await page.locator("[data-key=pick]").click();
    await page.waitForSelector(".ri-pick", { timeout: 10000 });
    await shot(page, `w2-pick-${tag}`);
    const box = await page.locator("#map canvas, #map").first().boundingBox();
    // Точка в Астане: центр видимой карты (стартовый вид — Нура).
    await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForFunction(() => !document.querySelector(".ri-pick .bk-btn--primary").disabled, null, { timeout: 5000 });
    await page.locator(".ri-pick .bk-btn--primary").click();
    await page.waitForSelector(".ri-wizard .ri-place", { timeout: 10000 });
    check(`${tag} мастер: после выбора места — снова «Идеи», место выбрано`, page.url().includes("#ideas") && !(await page.$(".ri-pick")), page.url());
    await page.locator("[data-key=next]").click();
    await page.fill("#ri-title", lang === "kk" ? "Аулаға орындықтар" : "Скамейки во дворе");
    await page.fill("#ri-text", lang === "kk" ? "Отыратын орын жоқ." : "Негде присесть.");
    await page.locator("[data-key=next]").click();
    await page.locator("[data-key=kind-square]").click();
    const step3 = await audit(page, ".ri");
    check(`${tag} мастер: шаг 3 — честная строка и «после проверки», одна главная`, step3.text.includes(T.honest) && step3.primaries === 1, step3.text.slice(0, 200));
    await shot(page, `w2-wizard3-${tag}`);
    await page.locator("[data-key=send]").click();
    await page.waitForSelector(".ri-sent", { timeout: 10000 });
    check(`${tag} мастер: «${T.sent}»`, (await page.locator(".ri-sent").innerText()).includes(T.sent), "no sent");
    await shot(page, `w2-sent-${tag}`);
    await page.locator("[data-key=back-list]").click();
    await page.waitForSelector(".ri-card", { timeout: 10000 });
    const first = await page.locator(".ri-card").first().innerText();
    check(`${tag} мастер: своя идея сверху с пометкой «${T.review}»`, first.includes(T.review), first);
  }
  check(`${tag} житель: нет ошибок JS`, page.errs.length === 0, page.errs.join(" | "));
  await page.context().close();
}

async function akimat(browser, base, width, lang) {
  const tag = `${width}-${lang}`;
  const T = lang === "kk"
    ? { open: "Тексеру", publish: "Дауыс беруге жариялау", bikes: "велотұрақ", gazebo: "Аулада беседка мен орындықтар",
      sports: "жасөспірімдерге спорт алаңы", make: "Жобаға айналдыру", reject: "Себебін көрсетіп бас тарту", confirm: "Идеядан бас тарту",
      byRes: "Тұрғындар идеясы бойынша · 12", square: "Гүлзар", projects: "Жобалар", works: "Жұмыстар мен өшірулер" }
    : { open: "Проверить", publish: "Опубликовать для голосования", bikes: "Велопарковка", gazebo: "Беседка и скамейки во дворе",
      sports: "Спортплощадка для подростков", make: "Сделать проектом", reject: "Отклонить с причиной", confirm: "Отклонить идею",
      byRes: "По идее жителей · 12", square: "Сквер", projects: "Проекты", works: "Работы и отключения" };
  const page = await newPage(browser, width, lang, "akimat");
  await page.goto(base);
  await page.evaluate(async (pw) => {
    await fetch("/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "checker", password: pw }) });
  }, PASSWORD);
  await page.goto(base + "#projects");
  await page.reload();
  await page.waitForSelector(".ri .ri-card", { timeout: 30000 });
  await page.waitForTimeout(400);
  const a = await audit(page, ".ri");
  // Новые (демо «Велопарковка» + идея, которую только что прислал житель) и 3 демо на голосовании — как в API сотрудника.
  const expected = await page.evaluate(async () => ((await (await fetch("/api/civic/v2/staff/ideas")).json()).items || []).length);
  check(`${tag} акимат: «Идеи на проверке» — все новые и на голосовании (${expected}), без главной кнопки до «${T.open}»`,
    expected >= 4 && a.primaries === 0 && (await page.locator(".ri-card").count()) === expected, a.text.slice(0, 200));
  check(`${tag} акимат: нет прокрутки вбок, текст ≥ 14 px`, a.overflow <= 1 && a.small.length === 0, a.overflow + " " + a.small.join(", "));
  // Опубликовать новую идею.
  await cardOf(page, T.bikes).locator("button", { hasText: T.open }).click();
  const opened = await audit(page, ".ri");
  check(`${tag} акимат: раскрыта одна идея — одна главная кнопка`, opened.primaries === 1, opened.primaries);
  await shot(page, `w2-akimat-review-${tag}`);
  await cardOf(page, T.bikes).locator("button", { hasText: T.publish }).click();
  await page.waitForFunction((t) => Array.from(document.querySelectorAll(".ri-card")).some((c) => c.textContent.includes(t) && c.querySelector(".bk-status[data-status=accepted]")), T.bikes, { timeout: 10000 });
  check(`${tag} акимат: «${T.publish}» → идёт голосование`, true);
  // Идея без объекта → выбрать «Сквер» → «Сделать проектом» → вкладка «Проекты» с «По идее жителей · 12».
  await cardOf(page, T.gazebo).locator("button", { hasText: T.open }).click();
  await page.locator(".ri-card--open .ri-checkform [data-key=check-land-yes]").click();
  await page.locator(".ri-card--open .bk-chip", { hasText: T.square }).click();
  await shot(page, `w2-akimat-check-${tag}`);
  await page.locator(".ri-card--open button", { hasText: T.make }).click();
  await page.waitForFunction((t) => document.body.innerText.includes(t), T.byRes, { timeout: 15000 });
  check(`${tag} акимат: «${T.make}» → проект «${T.byRes}»`, true);
  // Название проекта — «вид + улица рядом» (R12 /street-snap, near_street_* — patch R12 из INTEGRATION R06).
  const made = await page.locator(".r06-card", { hasText: T.byRes }).first().locator(".bk-card__title").innerText();
  check(`${tag} акимат: проект из идеи назван «вид + улица рядом»`, made.includes(lang === "kk" ? "Шыңғыс Айтматов" : "Чингиза Айтматова"), made);
  await shot(page, `w2-akimat-projects-${tag}`);
  // Отклонить с причиной (причина обязательна).
  await page.locator(".ri-tabs button").first().click();
  await cardOf(page, T.sports).locator("button", { hasText: T.open }).click();
  await page.locator(".ri-card--open button", { hasText: T.reject }).click();
  await page.locator(".ri-card--open .ri-reason .bk-btn--danger").click();
  check(`${tag} акимат: без причины отказ не отправляется`, (await page.locator(".ri-card", { hasText: T.sports }).count()) === 1, "sent without reason");
  await page.fill(".ri-card--open .ri-reason textarea", lang === "kk" ? "Учаскеде орын жоқ" : "Нет свободного участка");
  await page.locator(".ri-card--open .ri-reason .bk-btn--danger").click();
  await page.waitForFunction((t) => !Array.from(document.querySelectorAll(".ri-card")).some((c) => c.textContent.includes(t)), T.sports, { timeout: 10000 });
  const pub = await (await fetch(base + "api/civic/v2/ideas?status=rejected")).json();
  check(`${tag} акимат: отказ с причиной виден жителям`, (pub.items || []).some((i) => i.reason === (lang === "kk" ? "Учаскеде орын жоқ" : "Нет свободного участка")), JSON.stringify(pub).slice(0, 300));
  check(`${tag} акимат: нет ошибок JS (идеи)`, page.errs.length === 0, page.errs.join(" | "));
  // «Работы и отключения»: пустая форма не уходит; отключение с 4 строками «Зачем?» попадает в «Рядом» R08.
  await page.goto(base + "#works");
  await page.waitForSelector(".rw .bk-card", { timeout: 30000 });
  const w = await audit(page, ".rw");
  check(`${tag} работы: «${T.works}», демо-записи района, одна главная кнопка`, w.text.includes(T.works) && w.primaries === 1 && (await page.locator(".rw [data-work]").count()) >= 4, w.text.slice(0, 200));
  check(`${tag} работы: нет прокрутки вбок, текст ≥ 14 px`, w.overflow <= 1 && w.small.length === 0, w.overflow + " " + w.small.join(", "));
  await page.locator("[data-key=add]").click();
  await page.locator("[data-key=type-outage]").click();
  await page.locator("[data-key=save]").click();
  check(`${tag} работы: пустая форма — поля подсвечены, фокус на первом`, (await page.locator("[aria-invalid=true]").count()) >= 5 && (await page.evaluate(() => document.activeElement.getAttribute("aria-invalid"))) === "true", await page.locator("[aria-invalid=true]").count());
  const title = (lang === "kk" ? "Жылу 3 сағатқа өшіріледі " : "Отопление выключат на 3 часа ") + width;
  await page.fill("#rw-title", title);
  const day = new Date(Date.now() + 5 * 3600e3 + 86400e3).toISOString().slice(0, 10);
  await page.fill("#rw-start", day + "T09:00");
  await page.fill("#rw-end", day + "T12:00");
  await page.fill("#rw-zone", lang === "kk" ? "Сығанақ көшесі, 2–6" : "ул. Сыганак, 2–6");
  for (const k of ["problem", "reason", "result", "inconvenience"]) await page.fill("#rw-why-" + k, (lang === "kk" ? "Жол " : "Строка ") + k);
  await page.locator("#rw-utility").selectOption("heating");
  await shot(page, `w2-works-form-${tag}`);
  await page.locator("[data-key=save]").click();
  await page.waitForFunction((t) => Array.from(document.querySelectorAll(".rw [data-work]")).some((c) => c.textContent.includes(t)), title, { timeout: 10000 });
  const feed = await (await fetch(base + "api/civic/v2/nearby?district=nura")).json();
  const found = (feed.items || []).find((i) => (i.title_ru === title || i.title_kk === title));
  check(`${tag} работы: запись в ленте «Рядом» R08 — вкладка «Отключения», источник R06`, found && found.tab === "outages" && feed.sources.nearby === "r06", JSON.stringify(feed.sources));
  check(`${tag} работы: нет ошибок JS`, page.errs.length === 0, page.errs.join(" | "));
  await page.context().close();
}

(async () => {
  const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "r06-w2-"));
  try {
    for (const [width, lang, other] of [[1366, "ru", "kk"], [375, "kk", "ru"]]) {
      const port = await freePort();
      const srv = await start(port, path.join(tmp, `${width}-${lang}.sqlite3`));
      const base = `http://127.0.0.1:${port}/`;
      try {
        const api = await (await fetch(base + "api/civic/v2/ideas")).json();
        check(`${width}-${lang} API: демо-идеи в сборке (голосование 3, проект 1, отказ 1)`, api.counts && api.counts.voting === 3 && api.counts.project === 1 && api.counts.rejected === 1, JSON.stringify(api.counts));
        await resident(browser, base, width, other, false);   // второй язык — только чтение и поддержка
        await resident(browser, base, width, lang, true);
        await akimat(browser, base, width, lang);
      } catch (e) {
        check(`${width}-${lang} прогон без исключений`, false, e.stack || e);
      } finally {
        srv.kill();
      }
    }
  } finally {
    await browser.close();
  }
  const fail = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - fail}/${results.length} PASS`);
  process.exit(fail ? 1 : 0);
})();
