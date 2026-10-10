// R06 раунд 14 · проверка карточек в настоящем браузере (Chromium, Playwright) на стенде serve_r14.py.
//
//   python3 tests/civic/R06/round14/serve_r14.py --port 8616 --age-days 16 > stand.json &
//   NODE_PATH="$(npm root -g)" node tests/civic/R06/round14/browser_r14.cjs stand.json [папка-скриншотов]
//
// Что проверяется (UX_BRIEF + prompts/R06.txt «ГОТОВО, КОГДА»):
//  - 375×812 и 1366×768, ru и kk: нет горизонтальной прокрутки, нет сырых ключей вида proposal.vote_up,
//    нет предупреждений [i18n], кнопки голосования ≥ 48 px, полоса из 6 этапов и «Отстаёт на…» видны;
//  - голос: «За» +1; повтор «За» — счёт тот же; «Против» — голос переходит; перезагрузка — голос на месте;
//  - акимат: «Одобрить» → статус «Одобрено», голосование закрыто;
//  - нет связи с API → состояние ошибки с кнопкой «Повторить».
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const stand = JSON.parse(fs.readFileSync(process.argv[2], "utf8").trim().split("\n")[0]);
const shots = process.argv[3] && !process.argv[3].startsWith("--") ? process.argv[3] : null;
// --build-set: стенд засеян набором сборки R01 (serve_r14.py --package data/civic/astana/demo_synthetic.json) без
// сдвига часов — «давно не обновлялось» показать нечем, эти проверки NOT_RUN (а не PASS и не FAIL).
const buildSet = process.argv.includes("--build-set");
const URL = stand.url;
const results = [];

function check(name, ok, detail) {
  results.push({ name, ok: !!ok, detail: detail || "" });
  console.log((ok ? "PASS " : "FAIL ") + name + (detail ? " — " + detail : ""));
}

async function openPage(browser, viewport, lang, query) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, locale: lang === "kk" ? "kk-KZ" : "ru-RU" });
  const page = await context.newPage();
  const warnings = [];
  page.on("console", (msg) => {
    if (msg.type() === "warning" || msg.type() === "error") warnings.push(msg.text());
  });
  page.on("pageerror", (err) => warnings.push("pageerror: " + err.message));
  await page.goto(URL + "?lang=" + lang + (query ? "&" + query : ""));
  await page.waitForSelector(".r06-card[data-proposal]", { timeout: 10000 });
  await page.waitForSelector(".r06-card[data-object]", { timeout: 10000 });
  await page.waitForTimeout(300);
  return { context, page, warnings };
}

async function layoutChecks(page, label, warnings) {
  const m = await page.evaluate(() => {
    const doc = document.documentElement;
    const text = document.body.innerText;
    const rawKeys = text.match(/\b(?:proposal|object|stage|common|district|status)\.[a-z_]+(?:\.[a-z_]+)*\b/g) || [];
    const voteBtns = Array.from(document.querySelectorAll(".r06-vote__btn")).map((b) => b.getBoundingClientRect().height);
    const cards = Array.from(document.querySelectorAll(".r06-card")).map((c) => c.getBoundingClientRect());
    return {
      scroll: doc.scrollWidth - window.innerWidth,
      rawKeys,
      minVote: Math.min.apply(null, voteBtns),
      overflowCards: cards.filter((r) => r.right > window.innerWidth + 0.5 || r.left < -0.5).length,
      stages: document.querySelectorAll(".r06-card[data-object] .bk-stages > li").length,
      late: Array.from(document.querySelectorAll(".bk-tag--warn")).map((e) => e.textContent.trim()),
      stale: document.body.innerText.match(/Не обновлялось|жаңартылмаған/g) || [],
      techTitles: Array.from(document.querySelectorAll(".bk-card__title")).map((e) => e.textContent).filter((t) => /Демо|синтетик/i.test(t)),
      lateCardsWithoutWarn: Array.from(document.querySelectorAll('[data-group="late"] .r06-card')).filter((c) => !c.querySelector(".bk-tag--warn")).length,
      staleCardsWithWarn: Array.from(document.querySelectorAll('[data-group="stale"] .r06-card')).filter((c) => c.querySelector(".bk-tag--warn")).length,
      staleGroup: document.querySelectorAll('[data-group="stale"] .r06-card').length,
      dup: (() => { const ids = Array.from(document.querySelectorAll("[data-group] .r06-card[data-object]")).map((c) => c.getAttribute("data-object")); return ids.length - new Set(ids).size; })(),
      titles: Array.from(document.querySelectorAll(".r06-card[data-proposal] .bk-card__title")).map((e) => e.textContent),
      objectTitles: Array.from(document.querySelectorAll(".r06-card[data-object] .bk-card__title")).map((e) => e.getAttribute("lang") + ":" + e.textContent),
      htmlLang: document.documentElement.lang,
      // UX_BRIEF «Восемь правил» и чек-лист: технические слова, кегль ≥ 14 px, контраст ≥ 4.5:1, анимации ≤ 800 мс.
      techWords: (text.match(/\b(ребр[оа]|рёбра|граф[а-я]*|геометри[а-я]*|сценари[а-я]*|payload|demo-ring|bbox|device_id|undefined|null|NaN)\b/gi) || []),
      small: (() => {
        const out = [];
        document.querySelectorAll(".r06-card *").forEach((el) => {
          const own = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
          if (!own || !el.offsetParent) return;
          const fs = parseFloat(getComputedStyle(el).fontSize);
          if (fs < 14) out.push(fs + "px «" + el.textContent.trim().slice(0, 24) + "»");
        });
        return out;
      })(),
      lowContrast: (() => {
        const rgb = (c) => (c.match(/[\d.]+/g) || []).map(Number);
        const lum = ([r, g, b]) => [r, g, b].map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); })
          .reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0);
        const bgOf = (el) => {
          for (let e = el; e; e = e.parentElement) {
            const c = rgb(getComputedStyle(e).backgroundColor);
            if (c.length >= 3 && (c.length < 4 || c[3] > 0.5)) return c;
          }
          return [255, 255, 255];
        };
        const out = [];
        document.querySelectorAll(".r06-card *").forEach((el) => {
          const own = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
          if (!own || !el.offsetParent) return;
          const st = getComputedStyle(el);
          const a = lum(rgb(st.color)), b = lum(bgOf(el));
          const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          const large = parseFloat(st.fontSize) >= 24 || (parseFloat(st.fontSize) >= 18.66 && Number(st.fontWeight) >= 700);
          if (ratio < (large ? 3 : 4.5)) out.push(ratio.toFixed(2) + " «" + el.textContent.trim().slice(0, 24) + "»");
        });
        return out;
      })(),
      slowMotion: (() => {
        const out = [];
        document.querySelectorAll(".r06-card, .r06-card *").forEach((el) => {
          const st = getComputedStyle(el);
          const longest = Math.max(...(st.transitionDuration + "," + st.animationDuration).split(",").map((v) => parseFloat(v) * (v.indexOf("ms") > 0 ? 0.001 : 1) || 0));
          if (longest > 0.8) out.push(el.className + " " + longest + "s");
        });
        return out;
      })(),
    };
  });
  check(label + ": нет горизонтальной прокрутки", m.scroll <= 0, "scrollWidth−width=" + m.scroll);
  check(label + ": карточки внутри экрана", m.overflowCards === 0, String(m.overflowCards));
  check(label + ": нет сырых ключей", m.rawKeys.length === 0, m.rawKeys.slice(0, 5).join(", "));
  const i18nWarn = warnings.filter((w) => w.indexOf("[i18n]") >= 0);
  check(label + ": нет предупреждений [i18n]", i18nWarn.length === 0, i18nWarn.slice(0, 3).join(" | "));
  const errors = warnings.filter((w) => w.indexOf("[i18n]") < 0 && !/404/.test(w));
  check(label + ": нет ошибок в консоли (кроме ожидаемого 404 «нет объекта»)", errors.length === 0, errors.slice(0, 3).join(" | "));
  check(label + ": кнопки «За/Против» ≥ 48 px", m.minVote >= 48, "min=" + m.minVote);
  check(label + ": полоса 6 этапов у каждого объекта", m.stages > 0 && m.stages % 6 === 0, "li=" + m.stages);
  check(label + ": значок «Отстаёт на N…» (цвет + слова)", m.late.length > 0 && /\d/.test(m.late[0]), m.late[0] || "");
  if (buildSet) console.log("NOT_RUN " + label + ": «давно не обновлялось» — набор сборки без сдвига часов");
  else check(label + ": «давно не обновлялось» видно", m.stale.length > 0, String(m.stale.length));
  check(label + ": п.15 — в названиях нет «Демо»/«синтетика»", m.techTitles.length === 0, m.techTitles.join(" | "));
  check(label + ": UX_BRIEF — нет технических слов", m.techWords.length === 0, m.techWords.slice(0, 5).join(", "));
  check(label + ": UX_BRIEF — текст карточек не мельче 14 px", m.small.length === 0, m.small.slice(0, 4).join(" | "));
  check(label + ": UX_BRIEF — контраст текста ≥ 4.5:1 (крупный ≥ 3:1)", m.lowContrast.length === 0, m.lowContrast.slice(0, 4).join(" | "));
  check(label + ": UX_BRIEF — анимации не длиннее 800 мс", m.slowMotion.length === 0, m.slowMotion.slice(0, 3).join(" | "));
  check(label + ": п.17 — «Отстают» только с «Отстаёт на…», «Давно не обновлялись» без него, без повторов",
        m.lateCardsWithoutWarn === 0 && m.staleCardsWithWarn === 0 && (buildSet || m.staleGroup > 0) && m.dup === 0,
        JSON.stringify({ lateNoWarn: m.lateCardsWithoutWarn, staleWarn: m.staleCardsWithWarn, stale: m.staleGroup, dup: m.dup }));
  if (m.htmlLang === "kk") {
    check(label + ": п.19 — kk-название сквера без «шағын аудандағы»",
          m.titles.indexOf("Шыңғыс Айтматов көшесі маңындағы гүлзар") >= 0 && !m.titles.some((t) => /шағын аудандағы гүлзар/.test(t)), m.titles.join(" | "));
    // Просьба R08 (день 3): у демо-объектов казахское название, lang="kk".
    // Набор R06 (demo_package) или сборки R01 (demo_synthetic.json, --package): у всех демо-объектов есть title_kk.
    check(label + ": kk-названия демо-объектов (title_kk, lang=kk)",
          m.objectTitles.length > 0 && m.objectTitles.every((t) => t.indexOf("kk:") === 0),
          m.objectTitles.join(" | "));
  } else {
    check(label + ": ru-названия объектов (lang=ru)", m.objectTitles.length > 0 && m.objectTitles.every((t) => t.indexOf("ru:") === 0),
          m.objectTitles.join(" | "));
  }
}

async function tabTo(page, selectorTest, max) {
  // Нажимает Tab, пока фокус не встанет на нужный элемент; возвращает {steps, ring, text} или null.
  for (let steps = 1; steps <= (max || 40); steps++) {
    await page.keyboard.press("Tab");
    const info = await page.evaluate((test) => {
      const a = document.activeElement;
      if (!a || !a.matches(test)) return null;
      const st = getComputedStyle(a);
      const ring = (st.outlineStyle !== "none" && parseFloat(st.outlineWidth) > 0) || (st.boxShadow && st.boxShadow !== "none");
      return { ring: !!ring, text: a.textContent.trim().replace(/\s+/g, " ").slice(0, 40), visible: a.getBoundingClientRect().height >= 44 };
    }, selectorTest);
    if (info) return { steps, ...info };
  }
  return null;
}

async function counts(page, id) {
  return page.evaluate((pid) => {
    const card = document.querySelector('.r06-card[data-proposal="' + pid + '"]');
    const btns = card.querySelectorAll(".r06-vote__btn");
    const num = (b) => Number(b.querySelector(".bk-btn__count").textContent.replace(/\s/g, ""));
    return { up: num(btns[0]), down: num(btns[1]), upPressed: btns[0].getAttribute("aria-pressed"), downPressed: btns[1].getAttribute("aria-pressed") };
  }, id);
}

async function clickVote(page, id, value) {
  const sel = '.r06-card[data-proposal="' + id + '"] .r06-vote__btn[data-value="' + value + '"]';
  const respond = page.waitForResponse((r) => r.url().indexOf("/vote") > 0);
  await page.click(sel);
  await respond;
  await page.waitForTimeout(150);
}

(async () => {
  const browser = await chromium.launch({ executablePath: fs.existsSync("/opt/pw-browsers/chromium") ? undefined : undefined });
  try {
    for (const lang of ["ru", "kk"]) {
      for (const vp of [{ width: 375, height: 812 }, { width: 1366, height: 768 }]) {
        const label = lang + " " + vp.width;
        const { context, page, warnings } = await openPage(browser, vp, lang);
        await layoutChecks(page, label, warnings);
        if (shots) {
          fs.mkdirSync(shots, { recursive: true });
          await page.screenshot({ path: path.join(shots, "r06-" + vp.width + "-" + lang + ".png"), fullPage: false });
          await page.screenshot({ path: path.join(shots, "r06-" + vp.width + "-" + lang + "-full.png"), fullPage: true });
        }
        await context.close();
      }
    }

    // Голосование: одно устройство (один контекст браузера = один localStorage).
    {
      const { context, page } = await openPage(browser, { width: 375, height: 812 }, "ru");
      // Карточка с открытым голосованием (на стенде после прошлых прогонов одна может быть уже одобрена).
      const id = await page.getAttribute(".r06-card[data-proposal]:has(.r06-vote__btn:not([disabled]))", "data-proposal");
      const start = await counts(page, id);
      await clickVote(page, id, 1);
      const a = await counts(page, id);
      check("голос «За» +1", a.up === start.up + 1 && a.upPressed === "true", JSON.stringify(a));
      await clickVote(page, id, 1);
      const b = await counts(page, id);
      check("повтор «За» не удваивает", b.up === a.up && b.down === a.down, JSON.stringify(b));
      await clickVote(page, id, -1);
      const c = await counts(page, id);
      check("«Против» меняет голос", c.up === start.up && c.down === start.down + 1 && c.downPressed === "true", JSON.stringify(c));
      const focused = await page.evaluate(() => document.activeElement && document.activeElement.getAttribute("data-value"));
      check("фокус остаётся на нажатой кнопке", focused === "-1", String(focused));
      await page.reload();
      await page.waitForSelector('.r06-card[data-proposal="' + id + '"]');
      const d = await counts(page, id);
      check("после перезагрузки голос на месте", d.down === c.down && d.downPressed === "true", JSON.stringify(d));
      if (shots) await page.screenshot({ path: path.join(shots, "r06-375-ru-voted.png") });
      await context.close();
      // Другое устройство видит те же числа, но без своего голоса.
      const other = await openPage(browser, { width: 375, height: 812 }, "ru");
      const e = await counts(other.page, id);
      check("другое устройство: те же счётчики, своего голоса нет", e.down === c.down && e.downPressed === "false", JSON.stringify(e));
      await other.context.close();
    }

    // UX_BRIEF чек-лист «Клавиатура»: Tab доходит до кнопки голоса, видна рамка фокуса, Space голосует.
    for (const lang of ["ru", "kk"]) {
      const { context, page } = await openPage(browser, { width: 1366, height: 768 }, lang);
      const got = await tabTo(page, ".r06-vote__btn:not([disabled])", 40);
      check("клавиатура " + lang + ": Tab до «За/Против», видна рамка фокуса", got && got.ring && got.visible, JSON.stringify(got));
      if (got) {
        const id = await page.evaluate(() => document.activeElement.closest("[data-proposal]").getAttribute("data-proposal"));
        const before = await counts(page, id);
        await page.keyboard.press("Space");
        await page.waitForTimeout(400);
        const after = await counts(page, id);
        check("клавиатура " + lang + ": Space на кнопке — голос учтён", after.up + after.down === before.up + before.down + 1, JSON.stringify({ before, after }));
      }
      await context.close();
    }

    // Акимат (UX_REVIEW R11, день 3, п. 16): голоса — только чтение, одна главная кнопка «Одобрить»; затем «Одобрить».
    async function staffPage(viewport, lang) {
      const opened = await openPage(browser, viewport, lang);
      const login = await opened.page.evaluate(async (cred) => {
        const r = await fetch("/api/civic/v1/session/login", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cred), credentials: "same-origin",
        });
        return r.status;
      }, { username: stand.username, password: stand.password });
      await opened.page.goto(URL + "?lang=" + lang + "&role=akimat");
      await opened.page.waitForSelector('.r06-card[data-proposal] [data-action="approve"]');
      await opened.page.waitForSelector(".r06-stage-editor select");
      await opened.page.waitForTimeout(300);
      return { ...opened, login };
    }
    for (const lang of ["ru", "kk"]) {
      for (const vp of [{ width: 375, height: 812 }, { width: 1366, height: 768 }]) {
        const { context, page, login } = await staffPage(vp, lang);
        const label = "акимат " + lang + " " + vp.width;
        const m = await page.evaluate(() => {
          const cards = Array.from(document.querySelectorAll(".r06-card[data-proposal]"));
          const open = cards.filter((c) => c.querySelector('[data-action="approve"]'));
          return {
            cards: cards.length,
            voteButtons: document.querySelectorAll(".r06-card[data-proposal] .r06-vote__btn").length,
            primaryPerOpen: open.map((c) => c.querySelectorAll(".bk-btn--primary").length),
            tally: cards.map((c) => (c.querySelector(".r06-tally") || {}).textContent || ""),
            scroll: document.documentElement.scrollWidth - window.innerWidth,
          };
        });
        check(label + ": вход сотрудника", login === 200, String(login));
        check(label + ": у акимата нет кнопок голосования (голоса — числами)", m.voteButtons === 0 && m.tally.every((x) => /\d/.test(x)), m.tally[0]);
        check(label + ": одна главная кнопка в карточке («Одобрить»)", m.primaryPerOpen.length > 0 && m.primaryPerOpen.every((n) => n === 1), JSON.stringify(m.primaryPerOpen));
        check(label + ": нет горизонтальной прокрутки", m.scroll <= 0, String(m.scroll));
        if (shots) {
          await page.screenshot({ path: path.join(shots, "r06-" + vp.width + "-" + lang + "-akimat.png") });
          await page.screenshot({ path: path.join(shots, "r06-" + vp.width + "-" + lang + "-akimat-full.png"), fullPage: true });
        }
        if (lang === "kk" && vp.width === 1366) {
          const id = await page.getAttribute('.r06-card[data-proposal]:has([data-action="approve"])', "data-proposal");
          const respond = page.waitForResponse((r) => r.url().indexOf("/approve") > 0);
          await page.click('.r06-card[data-proposal="' + id + '"] [data-action="approve"]');
          const res = await respond;
          await page.waitForTimeout(200);
          const st = await page.evaluate((pid) => {
            const card = document.querySelector('.r06-card[data-proposal="' + pid + '"]');
            return { status: card.querySelector(".bk-status").textContent, actions: card.querySelectorAll("[data-action]").length,
                     closed: card.textContent.indexOf("дауыс беру аяқталды") >= 0 };
          }, id);
          check("«Мақұлдау» → «Мақұлданды», голосование закрыто, кнопок решения нет", res.status() === 200 && st.status === "Мақұлданды" && st.actions === 0 && st.closed, JSON.stringify(st));
        }
        await context.close();
      }
    }

    // Клавиатура у акимата: Tab до главной кнопки «Одобрить», рамка фокуса видна.
    {
      const { context, page } = await staffPage({ width: 1366, height: 768 }, "ru");
      const got = await tabTo(page, '[data-action="approve"]', 60);
      check("клавиатура акимат: Tab до «Одобрить», видна рамка фокуса", got && got.ring && got.visible, JSON.stringify(got));
      await context.close();
    }

    // UX_REVIEW R11 (ночь, круг 2, п. 3): проект без названия, но с улицей (так ставит R05) — «вид + улица» в ru и kk.
    {
      const { context, page } = await staffPage({ width: 375, height: 812 }, "ru");
      const created = await page.evaluate(async () => {
        const s = await (await fetch("/api/civic/v1/session", { credentials: "same-origin" })).json();
        const r = await fetch("/api/civic/v2/proposals", {
          method: "POST", credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": s.data.csrf_token },
          body: JSON.stringify({ kind: "square", geometry: { type: "Point", coordinates: [71.4148, 51.1131] }, near_street: "улица Керей и Жанибек хандар" }),
        });
        return { status: r.status, item: (await r.json()).data.item };
      });
      check("новый проект без названия: сервер собрал «вид + улица»", created.status === 201 &&
            created.item.title_ru === "Сквер у улицы Керей и Жанибек хандар" && /^Гүлзар · .+ көшесі маңында$/.test(created.item.title_kk),
            JSON.stringify({ ru: created.item && created.item.title_ru, kk: created.item && created.item.title_kk }));
      await context.close();
      for (const lang of ["ru", "kk"]) {
        const o = await openPage(browser, { width: 375, height: 812 }, lang);
        const card = o.page.locator('.r06-card[data-proposal="' + created.item.id + '"]');
        await card.waitFor();
        const title = (await card.locator(".bk-card__title").textContent()).trim();
        check("новый проект " + lang + ": в карточке вид и улица", lang === "kk" ? /^Гүлзар · .+маңында$/.test(title) && !/улица/.test(title)
              : title === "Сквер у улицы Керей и Жанибек хандар", title);
        if (shots) await card.screenshot({ path: path.join(shots, "r06-375-" + lang + "-new-project.png") });
        await o.context.close();
      }
    }

    // UX_REVIEW п. 18: формат даты в поле этапа на ru/kk (Chromium берёт его из языка браузера).
    for (const lang of ["ru", "kk"]) {
      const { context, page } = await staffPage({ width: 1366, height: 768 }, lang);
      const field = page.locator('.r06-stage-editor .bk-field:has(input[name="planned_end"])').first();
      await field.scrollIntoViewIfNeeded();
      const value = await page.locator('.r06-stage-editor input[name="planned_end"]').first().inputValue();
      check("дата этапа " + lang + ": значение ISO в поле", /^\d{4}-\d{2}-\d{2}$/.test(value), value);
      // п.18: формат самого поля задаёт браузер (в облаке — 11/23/2026), поэтому под полем — дата словами.
      const words = await page.locator('.r06-stage-editor [data-words-for="planned_end"]').first().textContent();
      const monthRe = lang === "kk" ? /^\d{1,2}\s(қаңтар|ақпан|наурыз|сәуір|мамыр|маусым|шілде|тамыз|қыркүйек|қазан|қараша|желтоқсан)\s20\d\d$/
                                    : /^\d{1,2}\s(янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)\s20\d\d$/;
      check("дата этапа " + lang + ": под полем дата словами («" + words + "»)", monthRe.test(words.replace(/\u00a0/g, " ")), words);
      await page.locator('.r06-stage-editor input[name="planned_end"]').first().fill("2026-11-23");
      const after = await page.locator('.r06-stage-editor [data-words-for="planned_end"]').first().textContent();
      check("дата этапа " + lang + ": подпись обновляется при выборе (23 ноября)", /^23\s(ноя|қараша)\s2026$/.test(after.replace(/\u00a0/g, " ")), after);
      if (shots) await field.screenshot({ path: path.join(shots, "r06-date-" + lang + ".png") });
      await context.close();
    }

    // Сотрудник меняет этап объекта (блок «Этап работ», будущая вставка в редактор R12) + конфликт двух вкладок.
    {
      const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
      const page = await context.newPage();
      await page.goto(URL + "?lang=ru");
      await page.evaluate(async (cred) => {
        await fetch("/api/civic/v1/session/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cred) });
      }, { username: stand.username, password: stand.password });
      await page.goto(URL + "?lang=ru&role=akimat");
      await page.waitForSelector(".r06-stage-editor select");
      const second = await context.newPage(); // вторая вкладка того же сотрудника со старой формой
      await second.goto(URL + "?lang=ru&role=akimat");
      await second.waitForSelector(".r06-stage-editor select");
      const editor = page.locator(".r06-stage-editor").first();
      // Новый этап всегда отличается от текущего (стенд мог сохранить этап в прошлом прогоне).
      const before = await editor.locator("select").inputValue();
      const target = before === "acceptance" ? "construction" : "acceptance";
      const targetRu = target === "acceptance" ? "Приёмка" : "Строительство";
      await editor.locator("select").selectOption(target);
      await editor.locator('input[name="forecast_end"]').fill("");
      const saved = page.waitForResponse((r) => r.url().endsWith("/stage") && r.request().method() === "PUT");
      await editor.locator("[data-save]").click();
      const res = await saved;
      await page.waitForTimeout(400);
      const msg = await editor.locator("[data-msg]").textContent();
      const caption = await page.locator(".r06-card[data-object] .bk-stages__caption").first().textContent();
      check("сотрудник сохраняет этап → карточка объекта обновилась", res.status() === 200 && /сохранён/.test(msg) && caption.indexOf(targetRu) >= 0, msg + " | " + caption);
      if (shots) await page.screenshot({ path: path.join(shots, "r06-1366-ru-stage-editor.png") });
      const ed2 = second.locator(".r06-stage-editor").first();
      await ed2.locator("select").selectOption(target === "design" ? "planned" : "design");
      const conflict = second.waitForResponse((r) => r.url().endsWith("/stage") && r.request().method() === "PUT");
      await ed2.locator("[data-save]").click();
      const res2 = await conflict;
      await second.waitForTimeout(400);
      const msg2 = await ed2.locator("[data-msg]").textContent();
      const sel2 = await ed2.locator("select").inputValue();
      check("старая вкладка: 409 → понятное сообщение и свежая версия", res2.status() === 409 && /другой сотрудник/.test(msg2) && sel2 === target, res2.status() + " " + msg2 + " " + sel2);
      // Пустой этап → ошибка у поля, фокус на нём.
      await ed2.locator("select").selectOption("");
      const bad = second.waitForResponse((r) => r.url().endsWith("/stage") && r.request().method() === "PUT");
      await ed2.locator("[data-save]").click();
      const res3 = await bad;
      await second.waitForTimeout(300);
      const focusedName = await second.evaluate(() => document.activeElement && document.activeElement.getAttribute("name"));
      check("пустой этап → 422, ошибка у поля, фокус на поле", res3.status() === 422 && focusedName === "stage", res3.status() + " focus=" + focusedName);
      await context.close();
    }

    // Нет связи с API.
    {
      const context = await browser.newContext({ viewport: { width: 375, height: 812 } });
      const page = await context.newPage();
      await page.route("**/api/civic/v2/**", (route) => route.abort());
      await page.goto(URL + "?lang=ru");
      await page.waitForSelector(".bk-error, [role=alert], .bk-empty", { timeout: 8000 }).catch(() => null);
      await page.waitForTimeout(300);
      const txt = await page.evaluate(() => document.body.innerText);
      check("нет связи → «Нет связи с сервером» и «Повторить»", /Нет связи с сервером/.test(txt) && /Повторить/.test(txt), txt.slice(0, 160).replace(/\n/g, " / "));
      if (shots) await page.screenshot({ path: path.join(shots, "r06-375-ru-offline.png") });
      await context.close();
    }
  } finally {
    await browser.close();
  }
  const failed = results.filter((r) => !r.ok);
  console.log(JSON.stringify({ total: results.length, failed: failed.length }));
  if (shots) fs.writeFileSync(path.join(shots, "browser_r14.json"), JSON.stringify(results, null, 1));
  process.exit(failed.length ? 1 : 0);
})().catch((err) => {
  console.error(err);
  process.exit(2);
});
