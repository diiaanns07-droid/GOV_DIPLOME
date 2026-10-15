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
// Видимый текст экрана раздела (лист и карточка выбранного), ошибки вёрстки: горизонтальная прокрутка, мелкий шрифт
// (эталон 13 окт: подписи под числами, плашки и строка «это опрос» — 12 px, ниже нельзя), технические слова.
async function audit(page, sel, minPx = 12) {
  return page.evaluate(([sel, minPx]) => {
    const roots = Array.from(document.querySelectorAll(sel));
    const text = roots.map((r) => r.innerText).join("\n");
    const small = [];
    for (const root of roots) {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const n = walker.currentNode, el = n.parentElement;
        if (!n.textContent.trim() || !el || !el.getClientRects().length) continue;
        const cs = getComputedStyle(el);
        if (cs.visibility === "hidden" || el.closest("[hidden]") || el.closest("details:not([open]) > :not(summary)")) continue;
        if (parseFloat(cs.fontSize) < minPx) small.push(n.textContent.trim().slice(0, 30) + "@" + cs.fontSize);
      }
    }
    const primaries = roots.flatMap((r) => Array.from(r.querySelectorAll(".bk-btn--primary"))).filter((b) => b.getClientRects().length).length;
    return { text, small, primaries, overflow: document.scrollingElement.scrollWidth - innerWidth };
  }, [sel, minPx]);
}
// Карточка списка по названию; выбрать — нажать на название (вся карточка — зона нажатия).
const cardOf = (page, title) => page.locator(".ri-pc", { hasText: title }).first();
const pick = async (page, title) => { await cardOf(page, title).locator(".ri-pc__open").click(); await page.waitForSelector(".ri-pd", { timeout: 5000 }); };
// Контраст двух цветов CSS «rgb(a)(…)» (WCAG). Полупрозрачный фон кладётся на белый (карточка на плотном стекле).
function contrast(bg, fg) {
  const rgb = (c) => {
    const v = (c.match(/[\d.]+/g) || [0, 0, 0]).map(Number);
    const a = v.length > 3 ? v[3] : 1;
    return v.slice(0, 3).map((x) => x * a + 255 * (1 - a));
  };
  const lum = (c) => {
    const [r, g, b] = rgb(c).map((v) => {
      const x = v / 255;
      return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const [a, b] = [lum(bg), lum(fg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

async function resident(browser, base, width, lang, full) {
  const tag = `${width}-${lang}`;
  const T = lang === "kk"
    ? { sheet: "Жобалар мен идеялар", support: "Қолдау", supported: "Сіз қолдадыңыз", square: "Сығанақ көшесі маңындағы гүлзар",
      fountain: "Аулада субұрқақ", light: "Ілияс Омаров көшесіне жарық", reason: "Учаскеде су құбыры жоқ",
      improve: "Жетілдіруге болады", byRes: "Тұрғындар идеясы бойынша", honest: "шешімді әкімдік қабылдайды", newIdea: "Идея ұсыну",
      rejectedPill: "Қабылданбады", projectPill: "Жобаға қабылданды", more: "Толығырақ", oneVote: "бір",
      // «На проверке» — «Тексерілуде» (словарь R11, KK_REVIEW №38); старый словарь сборки мог дать «Тексеруде»
      pick: "Картадан орын таңдау", review: "Тексерілуде", reviewAlt: "Тексеруде", sent: "Идея жіберілді", privacyWord: "ЖСН" }
    : { sheet: "Проекты и идеи", support: "Поддержать", supported: "Вы поддержали", square: "Сквер у улицы Сыганак",
      fountain: "Фонтан во дворе", light: "Свет на улице Ильяса Омарова", reason: "нет водопровода",
      improve: "Можно доработать", byRes: "По идее жителей", honest: "решение принимает акимат", newIdea: "Предложить идею",
      rejectedPill: "Отклонена", projectPill: "Принято в проект", more: "Подробнее", oneVote: "один",
      pick: "Выбрать место на карте", review: "На проверке", sent: "Идея отправлена", privacyWord: "ИИН" };
  const page = await newPage(browser, width, lang, "resident");
  await page.goto(base);
  await page.waitForTimeout(800);
  check(`${tag} житель: карта по умолчанию без слоя идей`, await page.evaluate(() => !document.body.dataset.birgeLayer), "layer on");
  await page.goto(base + "#ideas");
  await page.waitForSelector(".ri .ri-pc", { timeout: 30000 });
  await page.waitForTimeout(700);
  // Карточка выбранного справа — только на узком листе 412 (патч R01 r01_projects_sheet.css); без патча и на телефоне —
  // под строкой списка (R11 §21.4).
  const wide = width > 760 && await page.evaluate(() => document.querySelector(".ri").getBoundingClientRect().width <= 440);
  const a = await audit(page, ".ri, .ri-pd-host");
  check(`${tag} житель: лист «${T.sheet}», честная строка видна сразу`, a.text.includes(T.sheet) && a.text.includes(T.honest), a.text.slice(0, 300));
  // Правило видно без прокрутки (R11 SCHEMES §4 п. 3): ноутбук — в карточке выбранного, телефон — строкой над списком.
  check(`${tag} житель: правило на первом экране`, await page.evaluate(() => {
    const n = document.querySelector(".ri-pd-host .ri-pd__note, .ri-honest-note"); if (!n) return false;
    const r = n.getBoundingClientRect(); return r.bottom <= innerHeight && r.top >= 0; }));
  // Одна главная кнопка на экране (эталон): «Поддержать» в карточке выбранного; «Предложить идею» внизу листа — второстепенная.
  check(`${tag} житель: главная кнопка — одна (${wide ? "«" + T.support + "» в карточке" : "нет, пока ничего не выбрано"}), «${T.newIdea}» внизу листа`,
    a.primaries === (wide ? 1 : 0) && (await page.locator(".ri-sheet-ft [data-key=new]").innerText()).includes(T.newIdea), a.primaries);
  check(`${tag} житель: нет прокрутки вбок, текст ≥ 12 px`, a.overflow <= 1 && a.small.length === 0, a.overflow + " " + a.small.join(", "));
  check(`${tag} житель: нет технических слов`, !TECH.some((w) => a.text.includes(w)), TECH.filter((w) => a.text.includes(w)));
  if (lang === "kk") {
    const ru = RU_WORDS.filter((w) => a.text.includes(w));
    check(`${tag} житель: в ҚАЗ нет русских подписей и названий`, ru.length === 0, ru.join(", "));
  }
  // Эталон: ноутбук — первая карточка выбрана (рамка), справа её карточка, карта ведёт к ней (слой идей включён на время раздела).
  if (wide) {
    check(`${tag} житель: выбрана первая карточка — справа её карточка`, await page.evaluate(() => {
      const sel = document.querySelector(".ri-pc[aria-current=true]"); const pd = document.querySelector(".ri-pd-host .ri-pd");
      return !!sel && !!pd && pd.getAttribute("data-pd") === sel.getAttribute("data-idea"); }));
    // Карта и 3D-модуль R05 поднимаются после оболочки — слой включается, когда они готовы (до ~12 с).
    const layer = await page.waitForFunction(() => document.body.dataset.birgeLayer === "ideas", null, { timeout: 15000 }).then(() => true, () => false);
    check(`${tag} житель: на карте — слой идей, пока открыт раздел`, layer, "no layer");
  } else {
    check(`${tag} житель: телефон — ничего не раскрыто до нажатия`, (await page.locator(".ri-pd").count()) === 0);
  }
  await shot(page, `w2-ideas-${tag}`);
  // Поддержка прямо в списке: +1 сразу (оптимистично) и с сервера, капсула нажата; повторно — обратно.
  const card = cardOf(page, T.square);
  const votes = async () => Number(((await cardOf(page, T.square).locator(".ri-vote__n").innerText()).match(/\d+/) || [0])[0]);
  const before = await votes();
  await card.locator("[data-key^=support-]").click();
  await page.waitForFunction((t) => Array.from(document.querySelectorAll(".ri-pc")).some((c) => c.textContent.includes(t) && c.querySelector(".ri-vote[aria-pressed=true]")), T.square);
  await page.waitForTimeout(400);
  const after = await votes();
  const label = await cardOf(page, T.square).locator(".ri-vote").getAttribute("aria-label");
  check(`${tag} житель: ♥ «${T.support}» в списке → ${before + 1}, «${T.supported}»`, after === before + 1 && label === T.supported, `${before} → ${after}, ${label}`);
  // Поддержано — светлая капсула с заполненным сердцем (ui-kit R11 .bk-vote[aria-pressed]), число читается (≥ 4.5:1).
  const look = await page.evaluate((t) => {
    const c = Array.from(document.querySelectorAll(".ri-pc")).find((x) => x.textContent.includes(t));
    const b = c && c.querySelector(".ri-vote[aria-pressed=true]");
    if (!b) return { bg: "", fg: "", heart: "" };
    const cs = getComputedStyle(b);
    return { bg: cs.backgroundColor, fg: cs.color, heart: getComputedStyle(b.querySelector(".ri-heart path") || b).fill };
  }, T.square);
  check(`${tag} житель: «${T.supported}» — сердце заполнено, число читается (≥ 4.5:1)`, look.heart && look.heart !== "none" && contrast(look.bg, look.fg) >= 4.5, JSON.stringify(look));
  // Карточка выбранного: «Поддержать» / «Вы поддержали» — то же состояние, что в списке.
  await pick(page, T.square);
  check(`${tag} житель: в карточке — «${T.supported}»`, (await page.locator(".ri-pd [data-key=pd-support]").innerText()).includes(T.supported));
  await page.locator(".ri-pd [data-key=pd-more]").click();
  const more = await page.locator(".ri-pd .ri-pd__more").innerText().catch(() => "");
  check(`${tag} житель: «${T.more}» — правило «один голос» и чек-лист/3D по месту`, more.toLowerCase().includes(T.oneVote), more);
  await cardOf(page, T.square).locator("[data-key^=support-]").click();
  await page.waitForFunction((t) => Array.from(document.querySelectorAll(".ri-pc")).some((c) => c.textContent.includes(t) && c.querySelector(".ri-vote[aria-pressed=false]")), T.square);
  await page.waitForTimeout(400);
  check(`${tag} житель: повторное нажатие снимает поддержку`, (await votes()) === before, await votes());
  // Отклонённая — плашка «Отклонена», в карточке причина и «Можно доработать»; проект — «Принято в проект», «По идее жителей».
  check(`${tag} житель: плашки «${T.rejectedPill}» и «${T.projectPill}» в списке`,
    (await cardOf(page, T.fountain).locator(".ri-pill").innerText()) === T.rejectedPill && (await cardOf(page, T.light).locator(".ri-pill").innerText()) === T.projectPill);
  await pick(page, T.fountain);
  const rej = await page.locator(".ri-pd").innerText();
  check(`${tag} житель: отказ с причиной и «${T.improve}»`, rej.includes(T.reason) && rej.includes(T.improve), rej);
  await pick(page, T.light);
  const proj = await page.locator(".ri-pd").innerText();
  check(`${tag} житель: идея стала проектом — «${T.byRes} · 52»`, proj.includes(T.byRes) && proj.includes("52"), proj);
  // Клавиатура (правило 2): ↓ — следующая карточка, Esc — карточка выбранного закрывается.
  await cardOf(page, T.light).locator(".ri-pc__open").focus();
  const selBefore = await page.evaluate(() => document.querySelector(".ri-pc[aria-current=true]")?.getAttribute("data-idea"));
  await page.keyboard.press("ArrowDown");
  const selAfter = await page.evaluate(() => document.querySelector(".ri-pc[aria-current=true]")?.getAttribute("data-idea"));
  check(`${tag} житель: ↓ выбирает следующую карточку`, selAfter && selAfter !== selBefore, `${selBefore} → ${selAfter}`);
  await page.keyboard.press("Escape");
  check(`${tag} житель: Esc закрывает карточку выбранного`, (await page.locator(".ri-pd").count()) === 0);
  // Вкладка «Проекты акимата»: проекты с ♥ (голос «За») и карточкой.
  await page.locator("[data-key=tab-projects]").click();
  await page.waitForSelector(".ri-pc[data-proposal]", { timeout: 5000 });
  check(`${tag} житель: «Проекты акимата» — карточки проектов`, (await page.locator(".ri-pc[data-proposal]").count()) >= 3);
  await page.locator("[data-key=tab-ideas]").click();
  if (full) {
    // Мастер: место на карте → название → объект → отправить → своя идея «на проверке».
    await page.locator("[data-key=new]").click();
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
    // Телефон в названии (R15-S31) — ошибка у поля, шаг 2 не пройден; исправили — ошибка уходит.
    await page.fill("#ri-title", (lang === "kk" ? "Хабарласыңыз " : "Звоните ") + "+7 701 123 45 67");
    await page.locator("[data-key=next]").click();
    check(`${tag} мастер: телефон в названии — ошибка у поля «${T.privacyWord}», дальше не пускает`,
      (await page.locator("#ri-title[aria-invalid=true]").count()) === 1 && (await page.locator("#ri-title-err").innerText()).includes(T.privacyWord));
    await page.fill("#ri-title", lang === "kk" ? "Аулаға орындықтар" : "Скамейки во дворе");
    check(`${tag} мастер: исправили — ошибка ушла`, (await page.locator("#ri-title-err").count()) === 0);
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
    await page.waitForSelector(".ri-pc", { timeout: 10000 });
    const first = await page.locator(".ri-pc").first().innerText();
    check(`${tag} мастер: своя идея сверху с плашкой «${T.review}»`, (first.includes(T.review) || (T.reviewAlt && first.includes(T.reviewAlt)))
      && first.includes(lang === "kk" ? "Аулаға орындықтар" : "Скамейки во дворе"), first);
  }
  // Закрыли раздел (×) — карта как была: слой идей, включённый на время раздела, выключен.
  await page.locator(".ri [data-key=close]").click();
  await page.waitForTimeout(400);
  check(`${tag} житель: × закрывает лист и карточку, слой идей выключен`, (await page.locator(".ri-pd-host").count()) === 0
    && await page.evaluate(() => !document.body.dataset.birgeLayer), await page.evaluate(() => document.body.dataset.birgeLayer));
  check(`${tag} житель: нет ошибок JS`, page.errs.length === 0, page.errs.join(" | "));
  await page.context().close();
}

async function akimat(browser, base, width, lang) {
  const tag = `${width}-${lang}`;
  const T = lang === "kk"
    ? { open: "Тексеру", publish: "Жариялау", decided: "Шешім қабылданған идеялар", bikes: "велотұрақ", gazebo: "Аулада беседка мен орындықтар",
      sports: "жасөспірімдерге спорт алаңы", make: "Жобаға айналдыру", reject: "Себебін көрсетіп бас тарту", voting: "Дауыс жинау",
      byRes: "Тұрғындар идеясы бойынша · 12", square: "Гүлзар", projects: "Жобалар", works: "Жұмыстар мен өшірулер" }
    : { open: "Проверить", publish: "Опубликовать", decided: "Решённые идеи", bikes: "Велопарковка", gazebo: "Беседка и скамейки во дворе",
      sports: "Спортплощадка для подростков", make: "Сделать проектом", reject: "Отклонить с причиной", voting: "Сбор голосов",
      byRes: "По идее жителей · 12", square: "Сквер", projects: "Проекты", works: "Работы и отключения" };
  const page = await newPage(browser, width, lang, "akimat");
  await page.goto(base);
  await page.evaluate(async (pw) => {
    await fetch("/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: "checker", password: pw }) });
  }, PASSWORD);
  await page.goto(base + "#projects");
  await page.reload();
  await page.waitForSelector(".ri .ri-pc", { timeout: 30000 });
  await page.waitForTimeout(500);
  const a = await audit(page, ".ri");
  // Новые (демо «Велопарковка» + идея, которую только что прислал житель) и 3 демо на голосовании — как в API сотрудника.
  const expected = await page.evaluate(async () => {
    const session = await (await fetch("/api/civic/v1/session")).json();
    const token = (session.data || session).csrf_token;
    return ((await (await fetch("/api/civic/v2/staff/ideas", { headers: { "X-CSRF-Token": token } })).json()).items || []).length;
  });
  check(`${tag} акимат: «Идеи жителей» — все новые и на голосовании (${expected}), в листе нет главной кнопки`,
    expected >= 4 && a.primaries === 0 && (await page.locator(".ri-plist > .ri-pc[data-idea]").count()) === expected, a.text.slice(0, 200));
  // Решённые идеи — свёрнуто внизу (R15-S30: их можно скрыть); в демо 2 — отклонённая и ставшая проектом.
  const decided = page.locator(".ri-decided");
  check(`${tag} акимат: «${T.decided} · 2» свёрнуто внизу`, (await decided.count()) === 1 && !(await decided.evaluate((d) => d.open))
    && (await decided.locator("summary").innerText()).includes(T.decided + " · 2"), await decided.count());
  check(`${tag} акимат: нет прокрутки вбок, текст ≥ 12 px`, a.overflow <= 1 && a.small.length === 0, a.overflow + " " + a.small.join(", "));
  // Опубликовать новую идею: выбрать → в карточке «Опубликовать» (одна главная кнопка).
  await pick(page, T.bikes);
  const opened = await audit(page, ".ri-pd");
  check(`${tag} акимат: карточка выбранной идеи — одна главная кнопка`, opened.primaries === 1, opened.primaries);
  await shot(page, `w2-akimat-review-${tag}`);
  await page.locator(".ri-pd [data-key=publish]").click();
  await page.waitForFunction((t) => Array.from(document.querySelectorAll(".ri-pc")).some((c) => c.textContent.includes(t) && c.getAttribute("data-idea-status") === "voting"), T.bikes, { timeout: 10000 });
  check(`${tag} акимат: «${T.publish}» → «${T.voting}»`, (await cardOf(page, T.bikes).locator(".ri-pill").innerText()) === T.voting);
  // Идея без объекта → «Проверить» → «Сквер» → 4 × «да» → «Сделать проектом» → «Проекты акимата», «По идее жителей · 12».
  await pick(page, T.gazebo);
  await page.locator(".ri-pd [data-key=pd-check]").click();
  await page.locator(".ri-pd .bk-chip", { hasText: T.square }).click();
  check(`${tag} акимат: «${T.make}» недоступна, пока не все 4 пункта «да» (подсказка рядом)`,
    await page.locator(".ri-pd [data-key=project]").isDisabled() && (await page.locator(".ri-pd .ri-hint").count()) === 1);
  for (const k of ["land", "networks", "access", "maintenance"]) await page.locator(`.ri-pd [data-key=check-${k}-yes]`).click();
  await shot(page, `w2-akimat-check-${tag}`);
  await page.locator(".ri-pd button", { hasText: T.make }).click();
  await page.waitForFunction((t) => document.body.innerText.includes(t), T.byRes, { timeout: 15000 });
  check(`${tag} акимат: «${T.make}» → проект «${T.byRes}», выбран во вкладке проектов`,
    (await page.locator("[data-key=tab-projects][aria-selected=true]").count()) === 1 && (await page.locator(".ri-pc[data-proposal][aria-current=true]").innerText()).includes(T.byRes));
  // Название проекта — «вид + улица рядом» (R12 /street-snap, near_street_* — patch R12 из INTEGRATION R06).
  const made = await page.locator(".ri-pc[data-proposal]", { hasText: T.byRes }).first().locator(".ri-pc__title").innerText();
  check(`${tag} акимат: проект из идеи назван «вид + улица рядом»`, made.includes(lang === "kk" ? "Шыңғыс Айтматов" : "Чингиза Айтматова"), made);
  await shot(page, `w2-akimat-projects-${tag}`);
  // Отклонить с причиной (причина обязательна).
  await page.locator("[data-key=tab-ideas]").click();
  await pick(page, T.sports);
  await page.locator(".ri-pd [data-key=pd-check]").click();
  await page.locator(".ri-pd button", { hasText: T.reject }).click();
  await page.locator(".ri-pd .ri-reason .bk-btn--danger").click();
  check(`${tag} акимат: без причины отказ не отправляется`, (await page.locator(".ri-plist > .ri-pc", { hasText: T.sports }).count()) === 1, "sent without reason");
  await page.fill(".ri-pd .ri-reason textarea", lang === "kk" ? "Учаскеде орын жоқ" : "Нет свободного участка");
  await page.locator(".ri-pd .ri-reason .bk-btn--danger").click();
  // Отклонённая идея уходит из списка в свёрнутые «Решённые идеи» (там её можно скрыть, R15-S30).
  await page.waitForFunction((t) => !Array.from(document.querySelectorAll(".ri-plist > .ri-pc")).some((c) => c.textContent.includes(t))
    && Array.from(document.querySelectorAll(".ri-decided .ri-pc")).some((c) => c.textContent.includes(t)), T.sports, { timeout: 10000 });
  const pub = await (await fetch(base + "api/civic/v2/ideas?status=rejected")).json();
  check(`${tag} акимат: отказ с причиной виден жителям`, (pub.items || []).some((i) => i.reason === (lang === "kk" ? "Учаскеде орын жоқ" : "Нет свободного участка")), JSON.stringify(pub).slice(0, 300));
  check(`${tag} акимат: нет ошибок JS (идеи)`, page.errs.length === 0, page.errs.join(" | "));
  // «Работы и отключения»: пустая форма не уходит; отключение с 4 строками «Зачем?» попадает в «Рядом» R08.
  await page.goto(base + "#works");
  // Ждать записей, а не «.bk-card»: заглушка загрузки ui-kit — тоже .bk-card (скелет), иначе гонка с ответом /works.
  await page.waitForSelector(".rw [data-work]", { timeout: 30000 });
  const w = await audit(page, ".rw", 13);
  check(`${tag} работы: «${T.works}», демо-записи района, одна главная кнопка`, w.text.includes(T.works) && w.primaries === 1 && (await page.locator(".rw [data-work]").count()) >= 4, w.text.slice(0, 200));
  check(`${tag} работы: нет прокрутки вбок, текст ≥ 13 px`, w.overflow <= 1 && w.small.length === 0, w.overflow + " " + w.small.join(", "));
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
