// R07: скриншоты и проверки тепловой карты в настоящем Chromium (Playwright).
// Запуск: python -m ui.civic_heat.devserver &   затем
//   NODE_PATH=$(npm root -g) node tests/civic/R07/browser/shots.js [папка_для_скриншотов]
// Общие проверки каждого кадра: нет ошибок консоли, нет горизонтальной прокрутки, нет ключей heat.* вместо текста,
// нет слова «демо» в видимом тексте, зоны нажатия ≥ 48 px (с невидимой каймой ::after), главные кнопки ≥ 4,5:1.
// Отдельные сценарии — замечания UX_REVIEW R11, день 3 (№ в имени проверки).
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.env.R07_BASE || "http://127.0.0.1:8617/civic/heat/demo.html";
const API = BASE.replace(/\/civic\/heat\/demo\.html.*$/, "") + "/api/civic/v2";
const OUT = process.argv[2] || path.join(__dirname, "..", "..", "..", "..", "research", "round-14-results", "R07", "screens");
fs.mkdirSync(OUT, { recursive: true });

const SIZES = { desktop: { width: 1366, height: 768 }, phone: { width: 375, height: 812 } };
const results = [];

// Общие замеры страницы (выполняются в браузере)
async function measure(page) {
  return page.evaluate(() => {
    const lum = (rgb) => {
      const c = rgb.match(/\d+(\.\d+)?/g).slice(0, 3).map(Number).map((v) => v / 255)
        .map((v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
      return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    };
    const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
    const visible = (el) => { const r = el.getBoundingClientRect(); return el.offsetParent !== null && r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden"; };
    // Высота зоны нажатия: сам элемент + невидимая кайма ::after (inset с минусом)
    const hitHeight = (el) => {
      const r = el.getBoundingClientRect();
      const a = getComputedStyle(el, "::after");
      let extra = 0;
      if (a.content && a.content !== "none" && a.position === "absolute") {
        const top = parseFloat(a.top), bottom = parseFloat(a.bottom);
        extra = (top < 0 ? -top : 0) + (bottom < 0 ? -bottom : 0);
      }
      return r.height + extra;
    };
    const buttons = [...document.querySelectorAll("button, select")].filter(visible);
    const small = buttons.map((b) => ({ t: (b.innerText || b.getAttribute("aria-label") || "").trim().slice(0, 30), h: Math.round(hitHeight(b)) }))
      .filter((b) => b.h < 48);
    // R11 (ночь 5): видимый размер кнопок и переключателей ≥ 44 px (значки на карте — отдельно: ≥ 24 px + кайма 48)
    const smallVisible = buttons.filter((b) => !b.closest(".r07-badge") && b.getBoundingClientRect().height < 43.5)
      .map((b) => ({ t: (b.innerText || b.getAttribute("aria-label") || "").trim().slice(0, 30), h: Math.round(b.getBoundingClientRect().height) }));
    const primary = [...document.querySelectorAll(".r07-btn--primary")].filter(visible).map((b) => {
      const cs = getComputedStyle(b);
      return { t: b.innerText.trim().slice(0, 30), ratio: Math.round(contrast(cs.color, cs.backgroundColor) * 100) / 100 };
    });
    const doc = document.documentElement;
    const text = document.body.innerText;
    return {
      hscroll: doc.scrollWidth > doc.clientWidth + 1,
      rawKeys: text.match(/heat\.[a-z_.0-9]+/g) || [],
      demoWord: /демо/i.test(text),
      smallButtons: small,
      smallVisible,
      primary,
      badges: [...document.querySelectorAll(".r07-badge")].filter((b) => !b.hidden).length,
      legendOnMap: (() => { const l = document.querySelector(".r07-maplegend"); if (!l || !visible(l)) return false; const r = l.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0; })(),
      state: window.__heat ? window.__heat.state() : null,
    };
  });
}

async function open(browser, size, query) {
  const page = await browser.newPage({ viewport: SIZES[size], deviceScaleFactor: 1 });
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error" || (m.type() === "warning" && m.text().includes("[heat]"))) errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(BASE + query, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
  await page.waitForTimeout(900);
  return { page, errors };
}

async function shot(browser, name, size, query, after, check) {
  const { page, errors } = await open(browser, size, query);
  let extra = {};
  if (after) extra = (await after(page)) || {};
  await page.waitForTimeout(500);
  const m = await measure(page);
  const problems = [];
  if (errors.length) problems.push("console: " + errors.join(" | "));
  if (m.hscroll) problems.push("горизонтальная прокрутка");
  if (m.rawKeys.length) problems.push("ключи без перевода: " + m.rawKeys.join(","));
  if (m.demoWord) problems.push("слово «демо» в интерфейсе (№7)");
  if (m.smallButtons.length) problems.push("зона нажатия < 48 (№6): " + JSON.stringify(m.smallButtons));
  if (m.smallVisible.length) problems.push("видимая высота < 44 (R11): " + JSON.stringify(m.smallVisible));
  const lowContrast = m.primary.filter((b) => b.ratio < 4.5);
  if (lowContrast.length) problems.push("контраст главной кнопки < 4,5 (№1): " + JSON.stringify(lowContrast));
  if (m.state && m.state.mode === "targets" && !m.legendOnMap) problems.push("легенды нет на карте (№3)");
  if (check) problems.push(...((await check(page, m, extra)) || []));
  await page.screenshot({ path: path.join(OUT, name + ".jpg"), type: "jpeg", quality: 82 });
  results.push({ name, size, query, problems, badges: m.badges, primary: m.primary, extra });
  await page.close();
}

// №2: на масштабе 12–15 ни одного объекта, переданного только цветом; у видимых целей — значок с числом
async function colorOnlyCheck(page) {
  return page.evaluate(() => {
    const map = window.__map;
    const out = [];
    const z = map.getZoom();
    const feats = map.queryRenderedFeatures({ layers: ["r07-obj-halo-lo", "r07-obj-halo", "r07-obj-dot"].filter((l) => map.getLayer(l)) });
    const shown = new Set([...document.querySelectorAll(".r07-badge")].filter((b) => !b.hidden).map((b) => b.title));
    if (z < 15) {
      const low = feats.filter((f) => f.properties.level < 3);
      if (low.length) out.push("на " + z.toFixed(1) + " видны объекты уровней 1–2 без числа: " + low.length);
    }
    return out;
  });
}

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome" });
  const apiItems = async (days) => (await (await fetch(API + "/heat?days=" + days + "&zoom=15")).json()).items;

  for (const lang of ["ru", "kk"]) {
    // Старт карты акимата: 1366 и 375 (№2, №3, №5)
    await shot(browser, `nura-akimat-1366-${lang}`, "desktop", `?lang=${lang}&role=akimat&view=nura`, null, colorOnlyCheck);
    await shot(browser, `nura-akimat-375-${lang}`, "phone", `?lang=${lang}&role=akimat&view=nura`, null, async (page, m) => {
      const out = await colorOnlyCheck(page);
      // №5: горячие места, под которые подогнана карта, целиком видны — не за краем и не под шторкой
      const bad = await page.evaluate(async () => {
        const sheetTop = document.getElementById("panel").getBoundingClientRect().top;
        const keys = window.__heat.state().fittedKeys;
        const d = await (await fetch("/api/civic/v2/heat?days=30&zoom=15")).json();
        const labels = d.items.filter((x) => keys.includes(x.target.kind + ":" + x.target.id)).map((x) => x.target.label_ru);
        const badges = [...document.querySelectorAll(".r07-badge")].filter((b) => !b.hidden && labels.includes(b.title));
        const outside = badges.filter((b) => { const r = b.getBoundingClientRect(); return r.left < 0 || r.right > innerWidth || r.bottom > sheetTop || r.top < 56; });
        return { fitted: keys.length, shown: badges.length, outside: outside.map((b) => b.title) };
      });
      if (bad.fitted < 2) out.push("карта не подогнана под горячие места (№5)");
      if (bad.outside.length) out.push("горячие значки за краем или под шторкой (№5): " + bad.outside.join(", "));
      const inView = await page.evaluate(() => {
        const sheetTop = document.getElementById("panel").getBoundingClientRect().top;
        return [...document.querySelectorAll(".r07-badge")].filter((b) => !b.hidden && b.getBoundingClientRect().bottom < sheetTop && b.getBoundingClientRect().top > 56).length;
      });
      if (inView < 4) out.push("над шторкой видно мало значков (№5): " + inView);
      return out;
    });
    // Карточка акимата: контраст «Взять в работу» и «Что пишут жители» (№1, №4)
    await shot(browser, `card-akimat-1366-${lang}`, "desktop", `?lang=${lang}&view=nura`, async (page) => {
      await page.click(".r07-item");
      await page.waitForSelector(".r07-quotes, .r07-texts .r07-note", { timeout: 6000 });
    }, async (page) => {
      const out = [];
      const q = await page.evaluate(() => ({ quotes: document.querySelectorAll(".r07-quotes li").length,
        tag: [...document.querySelectorAll(".r07-quotes .r07-tag")].map((t) => t.innerText),
        actionTop: (document.querySelector('[data-act]') || {}).getBoundingClientRect?.().bottom || 9999,
        acts: document.querySelectorAll('.r07-card [data-act="take"], .r07-card [data-act="fixed"]').length }));
      if (!q.quotes) out.push("нет «Что пишут жители» (№4)");
      if (!q.acts) out.push("у акимата нет кнопок «Взять в работу» / «Отметить исправленным» на стенде");
      if (!q.tag.length) out.push("у примеров нет метки «Пример»/«Үлгі»");
      if (q.actionTop > 768) out.push("главная кнопка ниже экрана");
      return out;
    });
    await shot(browser, `card-akimat-375-${lang}`, "phone", `?lang=${lang}&view=nura&sheet=full`, async (page) => {
      await page.click(".r07-item");
      await page.waitForSelector(".r07-quotes, .r07-texts .r07-note", { timeout: 6000 });
    });
    // Житель: мягче, «Я тоже», БЕЗ текстов жителей
    await shot(browser, `card-resident-375-${lang}`, "phone", `?lang=${lang}&role=resident&view=nura&sheet=full`, async (page) => {
      await page.click(".r07-item");
      await page.waitForTimeout(900);
    }, async (page) => {
      const n = await page.evaluate(() => document.querySelectorAll(".r07-texts, .r07-quotes").length);
      return n ? ["жителю показаны тексты жалоб"] : [];
    });
    await shot(browser, `card-resident-1366-${lang}`, "desktop", `?lang=${lang}&role=resident&view=nura`, async (page) => {
      await page.click(".r07-item");
      await page.waitForTimeout(900);
    });
    // Весь город: районы с числами
    await shot(browser, `city-districts-1366-${lang}`, "desktop", `?lang=${lang}&view=city`);
    await shot(browser, `city-districts-375-${lang}`, "phone", `?lang=${lang}&view=city&sheet=peek`, null, async (page) => {
      // районы целиком на экране, ни один значок не под легендой и не за краем
      const r = await page.evaluate(() => {
        const leg = document.querySelector(".r07-maplegend").getBoundingClientRect();
        const sheetTop = document.getElementById("panel").getBoundingClientRect().top;
        const all = [...document.querySelectorAll('.r07-badge[data-kind="district"]')];
        const shown = all.filter((b) => !b.hidden);
        const bad = shown.filter((b) => { const x = b.getBoundingClientRect();
          const underLegend = !(x.right < leg.left || leg.right < x.left || x.bottom < leg.top || leg.bottom < x.top);
          return x.left < 0 || x.right > innerWidth || x.bottom > sheetTop || underLegend; });
        return { total: all.length, shown: shown.length, bad: bad.map((b) => b.title) };
      });
      const out = [];
      if (r.shown < r.total) out.push(`видно районов ${r.shown} из ${r.total}`);
      if (r.bad.length) out.push("значок района за краем / под легендой: " + r.bad.join(", "));
      return out;
    });
    // Пустой фильтр (№8): «За 7 дней жалоб нет» + «Показать 30 дней», без зелёной галочки
    for (const size of ["desktop", "phone"]) {
      await shot(browser, `empty-filter-${size === "desktop" ? 1366 : 375}-${lang}`, size, `?lang=${lang}&view=nura&sheet=full`, async (page) => {
        await page.evaluate(async () => {
          const meta = await (await fetch("/api/civic/v2/heat/meta")).json();
          for (const c of meta.categories) {
            const d = await (await fetch("/api/civic/v2/heat?days=7&zoom=15&category=" + c.id)).json();
            if (!d.items.some((x) => x.state === "active")) { window.__heat.setFilters({ category: c.id, days: 7 }); return; }
          }
        });
        await page.waitForSelector(".r07-empty", { timeout: 6000 });
      }, async (page) => {
        const e = await page.evaluate(() => ({ title: document.querySelector(".r07-empty__title").innerText,
          next: !!document.querySelector("[data-days-next]"), reset: !!document.querySelector(".r07-empty [data-reset]"),
          check: !!document.querySelector('.r07-empty svg path[d="m5 12.5 4.5 4.5L19 7"]') }));
        const out = [];
        if (!/7/.test(e.title)) out.push("заголовок пустого фильтра без периода: " + e.title);
        if (!e.next || !e.reset) out.push("нет «Показать 30 дней» / «Сбросить фильтры»");
        if (e.check) out.push("зелёная галочка в пустом состоянии");
        return out;
      });
    }
  }

  // Исправленная остановка (зелёная) — карточка через API, как переход из «Картины дня»
  for (const lang of ["ru", "kk"]) {
    await shot(browser, `stop-fixed-1366-${lang}`, "desktop", `?lang=${lang}&view=nura`, async (page) => {
      await page.evaluate(async () => {
        const d = await (await fetch("/api/civic/v2/heat?days=30&zoom=15")).json();
        const it = d.items.find((x) => x.state === "fixed" && x.target.subtype === "bus_stop") || d.items.find((x) => x.state === "fixed");
        if (it) await window.__heat.focusTarget(it.target.kind, it.target.id);
      });
      await page.waitForSelector(".r07-card", { timeout: 6000 });
      await page.waitForTimeout(900);
    });
  }

  // №12: ссылка «Картины дня» #target=kind:id&days=7 — карточка открыта, период 7 дней, число = числу из API за 7 дней
  {
    const items7 = await apiItems(7);
    const top = items7.find((x) => x.state === "active" && x.target.kind !== "district");
    for (const [lang, size] of [["ru", "desktop"], ["kk", "phone"]]) {
      await shot(browser, `deeplink-days7-${size === "desktop" ? 1366 : 375}-${lang}`, size,
        `?lang=${lang}&view=city&sheet=full#target=${top.target.kind}:${top.target.id}&days=7`, async (page) => {
          await page.waitForSelector(".r07-card", { timeout: 10000 });
          await page.waitForTimeout(700);
        }, async (page) => {
          const st = await page.evaluate(() => ({ s: window.__heat.state(), text: document.querySelector(".r07-card__reported").innerText }));
          const out = [];
          if (st.s.filters.days !== 7) out.push("период не 7 дней: " + st.s.filters.days);
          if (st.s.selected !== top.target.kind + ":" + top.target.id) out.push("открыта не та цель: " + st.s.selected);
          if (!st.text.includes(String(top.count))) out.push(`в карточке не ${top.count}: ${st.text}`);
          return out;
        });
    }
  }

  // Реальная детская площадка OSM (многоугольник) — значок внутри контура
  await shot(browser, "playground-real-osm-1366-kk", "desktop", "?lang=kk&view=nura", async (page) => {
    await page.evaluate(async () => {
      const d = await (await fetch("/api/civic/v2/heat?days=30&zoom=15")).json();
      const it = d.items.find((x) => x.target.subtype === "playground");
      if (it) await window.__heat.focusTarget(it.target.kind, it.target.id);
    });
    await page.waitForSelector(".r07-card", { timeout: 6000 });
    await page.waitForTimeout(900);
  });
  // Пульс после новой жалобы
  await shot(browser, "pulse-new-complaint-1366-ru", "desktop", "?lang=ru&view=nura", async (page) => {
    await page.click(".r07-item");
    await page.waitForTimeout(700);
    await page.click("#demo-new");
    await page.waitForSelector(".r07-pulse", { timeout: 5000 });
    await page.waitForTimeout(350);
  });
  await shot(browser, "filter-snow-7days-1366-kk", "desktop", "?lang=kk&view=nura", async (page) => {
    await page.click("[data-cats-toggle]");
    await page.click('[data-cat="snow_ice"]');
    await page.waitForTimeout(500);
    await page.click('[data-days="7"]');
    await page.waitForTimeout(700);
  });

  // R10 B-019 / R11 B1 п.3 / LOCAL_B2 P1: житель выбирает место — нажатие на значок = щелчок по карте в точке цели.
  // Стенд как в оболочке B3: класс body.birge-picking + правило birge.css «pointer-events: none» для значков;
  // слушатель map.on("click") — как адаптер R09 (complaint.js maplibreAdapter).
  for (const [size, lang] of [["desktop", "ru"], ["desktop", "kk"], ["phone", "ru"], ["phone", "kk"]]) {
    const w = size === "desktop" ? "1366" : "375";
    await shot(browser, `pick-badge-${w}-${lang}`, size, `?lang=${lang}&role=resident&view=nura`, async (page) => {
      const pre = await page.evaluate(async () => {
        const map = window.__map;
        const css = document.createElement("style");
        css.textContent = "body.birge-picking .r07-badge, body.birge-picking .r07-maplegend { pointer-events: none; }";
        document.head.append(css);
        document.body.classList.add("birge-picking");
        window.__picked = [];
        map.on("click", (e) => window.__picked.push([e.lngLat.lng, e.lngLat.lat]));
        const sheetTop = document.getElementById("panel") ? document.getElementById("panel").getBoundingClientRect().top : innerHeight;
        const badge = [...document.querySelectorAll('.r07-badge[data-kind="object"]')].find((b) => {
          const r = b.getBoundingClientRect();
          return !b.hidden && r.left > 0 && r.right < innerWidth && r.bottom < Math.min(innerHeight, innerWidth < 700 ? sheetTop : innerHeight) && r.top > 60;
        });
        if (!badge) return { error: "нет значка объекта в видимой части карты" };
        badge.id = "pick-me";
        const d = await (await fetch("/api/civic/v2/heat?days=30&zoom=15")).json();
        const it = d.items.find((x) => x.target.label_ru === badge.title || x.target.label_kk === badge.title);
        const r = badge.getBoundingClientRect();
        // нажатие ближе к краю значка (не в центр) — всё равно точно в цель
        return { x: r.left + r.width * 0.8, y: r.top + r.height * 0.5, anchor: it && it.anchor, title: badge.title };
      });
      if (pre.error) return pre;
      const hit = await page.evaluate((p) => { const el = document.elementFromPoint(p.x, p.y); const b = document.getElementById("pick-me"); return el === b || b.contains(el); }, pre);
      await page.mouse.click(pre.x, pre.y);
      await page.waitForTimeout(300);
      const after = await page.evaluate(async () => {
        const map = window.__map;
        const got = window.__picked[0];
        if (got) new window.maplibregl.Marker({ color: "#176b4a" }).setLngLat(got).addTo(map);
        // щелчок по линии участка улицы в режиме выбора тоже не открывает карточку
        const seg = map.queryRenderedFeatures({ layers: ["r07-seg"] })[0];
        if (seg) {
          const c = seg.geometry.coordinates[Math.floor(seg.geometry.coordinates.length / 2)];
          map.fire("click", { lngLat: new window.maplibregl.LngLat(c[0], c[1]), point: map.project(c), originalEvent: new MouseEvent("click") });
          await new Promise((ok) => setTimeout(ok, 300));
        }
        return { picked: got, card: !!document.querySelector(".r07-card"), clicks: window.__picked.length, seg: !!seg };
      });
      return { ...pre, hit, ...after };
    }, async (page, m, x) => {
      const out = [];
      if (x.error) return [x.error];
      if (!x.hit) out.push("нажатие на значок не дошло до значка (перехвачено)");
      if (!x.picked) out.push("мастер не получил щелчок по карте");
      else if (!x.anchor || Math.abs(x.picked[0] - x.anchor[0]) > 1e-6 || Math.abs(x.picked[1] - x.anchor[1]) > 1e-6)
        out.push("щелчок не в точке цели: " + JSON.stringify([x.picked, x.anchor]));
      if (x.card) out.push("в режиме выбора открылась карточка цели");
      return out;
    });
  }

  // Вместе с новым R09 (ветка R09 night, complaint.js): класс html.bc-picking и свой перехват нажатий по маркерам
  // в фазе захвата. Нажатие по значку должно дать ровно ОДИН выбор места, карточка R07 не открывается.
  await shot(browser, "pick-with-r09-capture-1366-ru", "desktop", "?lang=ru&role=resident&view=nura", async (page) => {
    const pre = await page.evaluate(() => {
      const map = window.__map, container = map.getContainer();
      document.documentElement.classList.add("bc-picking");
      window.__picks = [];
      map.on("click", (e) => window.__picks.push(["map", e.lngLat.lng, e.lngLat.lat]));
      container.addEventListener("click", (e) => {            // как onMarkerClick у R09
        const marker = e.target.closest && e.target.closest(".maplibregl-marker");
        if (!marker || !container.contains(marker)) return;
        e.preventDefault(); e.stopPropagation();
        const b = marker.getBoundingClientRect(), c = map.getCanvas().getBoundingClientRect();
        const at = map.unproject([b.left + b.width / 2 - c.left, b.top + b.height / 2 - c.top]);
        window.__picks.push(["r09-capture", at.lng, at.lat]);
      }, true);
      const badge = [...document.querySelectorAll('.r07-badge[data-kind="object"]')].find((b) => {
        const r = b.getBoundingClientRect(); return !b.hidden && r.left > 0 && r.right < innerWidth - 420 && r.top > 70 && r.bottom < innerHeight; });
      if (!badge) return { error: "нет значка объекта" };
      const r = badge.getBoundingClientRect();
      return { x: r.left + r.width * 0.5, y: r.top + r.height * 0.5 };
    });
    if (pre.error) return pre;
    await page.mouse.click(pre.x, pre.y);
    await page.waitForTimeout(300);
    return page.evaluate(() => ({ picks: window.__picks, card: !!document.querySelector(".r07-card") }));
  }, async (page, m, x) => {
    if (x.error) return [x.error];
    const out = [];
    if (!x.picks || x.picks.length !== 1) out.push("выборов места не один: " + JSON.stringify(x.picks));
    if (x.card) out.push("в режиме выбора открылась карточка цели");
    return out;
  });

  // R10 B-025: значки — одна остановка Tab, между ними — стрелки; Enter открывает карточку
  {
    const { page, errors } = await open(browser, "desktop", "?lang=ru&role=akimat&view=nura");
    const r = await page.evaluate(() => {
      const vis = [...document.querySelectorAll(".r07-badge")].filter((b) => !b.hidden);
      return { visible: vis.length, tabbable: vis.filter((b) => b.tabIndex === 0).length };
    });
    await page.focus('.r07-badge[tabindex="0"]');
    const first = await page.evaluate(() => document.activeElement.title);
    await page.keyboard.press("ArrowRight");
    const second = await page.evaluate(() => ({ title: document.activeElement.title, badge: document.activeElement.classList.contains("r07-badge"),
      tabbable: [...document.querySelectorAll(".r07-badge")].filter((b) => b.tabIndex === 0).length }));
    await page.keyboard.press("Enter");
    await page.waitForTimeout(500);
    const card = await page.evaluate(() => document.querySelector(".r07-card__title")?.innerText || "");
    const problems = [];
    if (r.visible < 3 || r.tabbable !== 1) problems.push("значков в порядке Tab: " + r.tabbable + " из " + r.visible + " (нужно 1)");
    if (!second.badge || second.title === first || second.tabbable !== 1) problems.push("стрелка не перевела фокус на соседний значок");
    if (!card) problems.push("Enter на значке не открыл карточку");
    results.push({ name: "keyboard-badges-roving-1366-ru", size: "desktop", query: "", problems: problems.concat(errors), badges: r.visible, extra: { first, second: second.title, card } });
    await page.close();
  }

  // R10 B-023: в оболочке тост — общий ui-kit R11 (BirgeUI.toast, z 60 над каталогом R05), не свой внизу под каталогом
  {
    const { page, errors } = await open(browser, "desktop", "?lang=kk&role=akimat&view=nura");
    await page.evaluate(() => { window.__toasts = []; window.BirgeUI = { toast: (t, o) => window.__toasts.push([t, o && o.type]) }; });
    await page.click(".r07-item");
    await page.waitForSelector('[data-act="take"], [data-act="fixed"]');
    await page.click('[data-act="take"], [data-act="fixed"]');
    await page.waitForTimeout(900);
    const x = await page.evaluate(() => ({ toasts: window.__toasts, own: document.querySelectorAll(".r07-toast").length }));
    const problems = [];
    if (!x.toasts.length || !/алынды|белгіленді/.test(x.toasts[0][0]) || x.toasts[0][1] !== "ok") problems.push("тост не ушёл в BirgeUI.toast: " + JSON.stringify(x.toasts));
    if (x.own) problems.push("свой тост R07 тоже показан");
    results.push({ name: "toast-ui-kit-1366-kk", size: "desktop", query: "", problems: problems.concat(errors), badges: 0, extra: x });
    await page.close();
  }

  // UX_BRIEF «Точность»: при наклоне и повороте карты значки стоят на своих местах и не налезают друг на друга
  for (const [size, lang] of [["desktop", "ru"], ["phone", "kk"]]) {
    await shot(browser, `tilt-3d-${size === "phone" ? 375 : 1366}-${lang}`, size, `?lang=${lang}&role=akimat&view=nura`, async (page) => {
      await page.evaluate(() => new Promise((ok) => { const m = window.__map; m.once("moveend", ok); m.jumpTo({ pitch: 60, bearing: -30, zoom: 15.3 }); }));
      await page.waitForTimeout(900);
      return page.evaluate(() => {
        const map = window.__map;
        const host = map.getContainer().getBoundingClientRect();
        const vis = [...document.querySelectorAll(".r07-badge")].filter((b) => !b.hidden && b.offsetParent !== null);
        const boxes = vis.map((b) => ({ b, r: b.getBoundingClientRect() }));
        let overlaps = 0;
        for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
          const a = boxes[i].r, c = boxes[j].r;
          const ix = Math.min(a.right, c.right) - Math.max(a.left, c.left), iy = Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top);
          if (ix > 4 && iy > 4) overlaps++;
        }
        // где должен стоять значок: проекция его точки на карте (MapLibre ставит центр значка в неё)
        const placed = window.__heat.badges();
        const far = placed.filter((x) => { const p = map.project(x.spot); return Math.hypot(p.x + host.left - x.cx, p.y + host.top - x.cy) > 2; });
        return { pitch: map.getPitch(), bearing: map.getBearing(), visible: vis.length, overlaps, checked: placed.length, far: far.map((x) => x.key) };
      });
    }, async (page, m, x) => {
      const out = [];
      if (Math.round(x.pitch) !== 60) out.push("наклон не применился");
      if (x.visible < 3) out.push("мало значков на наклонённой карте: " + x.visible);
      if (x.overlaps) out.push("значки налезают друг на друга при наклоне: " + x.overlaps);
      if (!x.checked) out.push("нет данных о точках значков");
      if (x.far.length) out.push("значок не в своей точке (> 2 px): " + x.far.join(", "));
      return out;
    });
  }

  // UX_BRIEF правило 7 и «Тексты»: загрузка, ошибка с действием, ошибка обновления и действия — у каждой «Повторить»
  async function rawPage(size, query, setup) {
    const page = await browser.newPage({ viewport: SIZES[size], deviceScaleFactor: 1 });
    const errors = [];
    // отказ сети здесь подстроен самим тестом — такие строки консоли не ошибка модуля
    page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|ERR_FAILED|status of 50/.test(m.text())) errors.push(m.text()); });
    page.on("pageerror", (e) => errors.push(String(e)));
    if (setup) await setup(page);
    await page.goto(BASE + query, { waitUntil: "domcontentloaded" });
    return { page, errors };
  }
  async function finish(page, errors, name, size, problems, extra) {
    const m = await measure(page);
    if (errors.length) problems.push("console: " + errors.join(" | "));
    if (m.hscroll) problems.push("горизонтальная прокрутка");
    if (m.rawKeys.length) problems.push("ключи без перевода: " + m.rawKeys.join(","));
    if (m.demoWord) problems.push("слово «демо» в интерфейсе");
    if (m.smallButtons.length) problems.push("зона нажатия < 48: " + JSON.stringify(m.smallButtons));
    if (m.smallVisible.length) problems.push("видимая высота < 44 (R11): " + JSON.stringify(m.smallVisible));
    await page.screenshot({ path: path.join(OUT, name + ".jpg"), type: "jpeg", quality: 82 });
    results.push({ name, size, query: "", problems, badges: m.badges, extra });
    await page.close();
  }
  const HEAT_GET = (u) => /\/api\/civic\/v2\/heat\?/.test(u.toString());

  // загрузка: скелетон, а не пустая панель
  for (const [size, lang] of [["phone", "kk"], ["desktop", "ru"]]) {
    const { page, errors } = await rawPage(size, `?lang=${lang}&view=nura`, (pg) =>
      pg.route(HEAT_GET, async (r) => { await new Promise((ok) => setTimeout(ok, 4000)); await r.continue(); }));
    await page.waitForTimeout(1200);
    const x = await page.evaluate(() => { const sk = document.querySelector(".r07-skeleton"); return { skeleton: !!sk && sk.getBoundingClientRect().height > 40, busy: sk && sk.getAttribute("aria-busy"), label: sk && sk.getAttribute("aria-label") }; });
    const problems = [];
    if (!x.skeleton || x.busy !== "true" || !x.label) problems.push("нет скелетона загрузки: " + JSON.stringify(x));
    await finish(page, errors, `state-loading-${size === "phone" ? 375 : 1366}-${lang}`, size, problems, x);
  }

  // ошибка первой загрузки: что случилось + что сделать + «Повторить», после связи — карта
  // на телефоне — как в проверке R10 B-034: оборваны все запросы карты, и /heat, и /heat/meta
  for (const [size, lang] of [["desktop", "ru"], ["phone", "kk"]]) {
    let fail = true;
    const pattern = size === "phone" ? /\/api\/civic\/v2\/heat/ : HEAT_GET;
    const { page, errors } = await rawPage(size, `?lang=${lang}&view=nura`, (pg) =>
      pg.route(pattern, (r) => (fail ? r.abort() : r.continue())));
    await page.waitForSelector(".r07-error", { timeout: 15000 }).catch(() => {});
    const x = await page.evaluate(() => {
      const e = document.querySelector(".r07-error");
      if (!e) return null;
      const r = e.getBoundingClientRect(), b = e.querySelector("[data-retry]").getBoundingClientRect();
      const l = document.querySelector(".r07-maplegend");
      return { text: e.innerText, retry: !!e.querySelector("[data-retry]"), retryVisible: b.bottom <= innerHeight && b.top >= 0, top: Math.round(r.top),
               emptyLegend: !!l && !l.hidden && l.getBoundingClientRect().height > 0 && !l.innerText.trim() };
    });
    const problems = [];
    if (!x || !x.retry || x.text.split("\n").filter(Boolean).length < 3) problems.push("нет понятной ошибки с действием: " + JSON.stringify(x));
    if (x && !x.retryVisible) problems.push("«Повторить» не видно без прокрутки (R10 B-034): " + JSON.stringify(x));
    if (x && x.emptyLegend) problems.push("пустая плашка легенды над картой (R10 B-034)");
    if (x && /Ошибка:|!/.test(x.text)) problems.push("в тексте ошибки «Ошибка:» или «!»");
    const name = `state-error-${size === "phone" ? 375 : 1366}-${lang}`;
    await page.screenshot({ path: path.join(OUT, name + ".jpg"), type: "jpeg", quality: 82 });
    fail = false;
    await page.click("[data-retry]");
    const ok = await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready" && window.__heat.state().items > 0, null, { timeout: 15000 }).then(() => true, () => false);
    if (!ok) problems.push("«Повторить» не загрузил карту");
    results.push({ name, size, query: "", problems: problems.concat(errors), badges: 0, extra: x });
    await page.close();
  }

  // ошибка обновления (данные уже есть): тост с «Повторить»; ошибка действия «Взять в работу»: тост с «Қайталау»
  {
    let fail = false;
    const { page, errors } = await rawPage("desktop", "?lang=ru&role=akimat&view=nura", (pg) =>
      pg.route(HEAT_GET, (r) => (fail ? r.abort() : r.continue())));
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.waitForTimeout(600);
    fail = true;
    await page.click('[data-days="7"]');
    await page.waitForSelector(".r07-toast__action", { timeout: 10000 }).catch(() => {});
    const x = await page.evaluate(() => { const t = document.querySelector(".r07-toast--error"); return t ? { text: t.innerText, role: t.getAttribute("role"), action: t.querySelector(".r07-toast__action")?.innerText } : null; });
    const problems = [];
    if (!x || x.action !== "Повторить" || x.role !== "alert") problems.push("тост ошибки обновления без «Повторить»: " + JSON.stringify(x));
    await page.screenshot({ path: path.join(OUT, "refresh-error-toast-1366-ru.jpg"), type: "jpeg", quality: 82 });
    fail = false;
    await page.click(".r07-toast__action");
    const ok = await page.waitForFunction(() => window.__heat.state().status === "ready" && window.__heat.state().filters.days === 7, null, { timeout: 10000 }).then(() => true, () => false);
    if (!ok) problems.push("«Повторить» в тосте не загрузил 7 дней");
    results.push({ name: "refresh-error-toast-1366-ru", size: "desktop", query: "", problems: problems.concat(errors), badges: 0, extra: x });
    await page.close();
  }
  {
    const { page, errors } = await rawPage("phone", "?lang=kk&role=akimat&view=nura&sheet=full", (pg) =>
      pg.route(/\/complaints\/[^/]+\/status/, (r) => r.fulfill({ status: 500, contentType: "application/json", body: '{"error":"x"}' })));
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.click(".r07-item");
    await page.waitForSelector('[data-act="take"], [data-act="fixed"]');
    await page.click('[data-act="take"], [data-act="fixed"]');
    await page.waitForSelector(".r07-toast__action", { timeout: 10000 }).catch(() => {});
    const x = await page.evaluate(() => { const t = document.querySelector(".r07-toast--error"); const b = document.querySelector('[data-act="take"], [data-act="fixed"]'); return { text: t && t.innerText, action: t && t.querySelector(".r07-toast__action")?.innerText, btnEnabled: b && !b.disabled }; });
    const problems = [];
    if (x.action !== "Қайталау" || !/Байланысты тексеріп/.test(x.text || "")) problems.push("тост ошибки действия: " + JSON.stringify(x));
    if (!x.btnEnabled) problems.push("кнопка осталась заблокированной после ошибки");
    await finish(page, errors, "action-error-toast-375-kk", "phone", problems, x);
  }

  // R15 U1: лимит (429) и нет входа (403) — понятный текст без «Повторить» (повтор не поможет)
  for (const [code, lang, act, want] of [[429, "ru", "metoo", "Слишком много действий подряд"], [403, "kk", "take", "қызметкері ретінде кіріп"]]) {
    const role = act === "metoo" ? "resident" : "akimat";
    const { page, errors } = await rawPage("phone", `?lang=${lang}&role=${role}&view=nura&sheet=full`, (pg) =>
      pg.route(act === "metoo" ? /\/complaints\/[^/]+\/metoo/ : /\/complaints\/[^/]+\/status/, (r) => r.fulfill({ status: code, contentType: "application/json", body: '{"error":"x"}' })));
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.evaluate(() => localStorage.removeItem("birge.heat.metoo"));
    await page.click(".r07-item");
    const sel = act === "metoo" ? '[data-act="metoo"]' : '[data-act="take"], [data-act="fixed"]';
    await page.waitForSelector(sel);
    await page.click(sel);
    await page.waitForSelector(".r07-toast--error", { timeout: 10000 }).catch(() => {});
    const x = await page.evaluate(() => { const t = document.querySelector(".r07-toast--error"); return { text: t && t.innerText, action: !!(t && t.querySelector(".r07-toast__action")) }; });
    const problems = [];
    if (!x.text || !x.text.includes(want)) problems.push(code + ": непонятный текст: " + JSON.stringify(x));
    if (x.action) problems.push(code + ": «Повторить» не должно быть");
    await finish(page, errors, `action-${code}-375-${lang}`, "phone", problems, x);
  }

  // R11 ночь 4 п.1: на телефоне легенда — одна строка, подсказка о масштабе — один тост, а не строка поверх карты
  for (const lang of ["ru", "kk"]) {
    const { page, errors } = await rawPage("phone", `?lang=${lang}&role=akimat&view=city`);
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.waitForTimeout(700);
    const x = await page.evaluate(() => {
      const l = document.querySelector(".r07-maplegend");
      const r = l.getBoundingClientRect();
      const tops = new Set([...l.querySelectorAll("li")].map((li) => Math.round(li.getBoundingClientRect().top)));
      const zoomInLegend = [...l.querySelectorAll(".r07-legend__zoom")].some((z) => z.offsetParent !== null);
      const btns = [...document.querySelectorAll(".mapbtns button")].map((b) => b.getBoundingClientRect());
      const under = btns.some((b) => !(r.right <= b.left || b.right <= r.left || r.bottom <= b.top || b.bottom <= r.top));
      const toasts = [...document.querySelectorAll(".r07-toast")].map((t) => t.innerText);
      const hint = document.querySelector(".r07-zoomhint");
      return { h: Math.round(r.height), rows: tops.size, right: Math.round(r.right), zoomInLegend, under, toasts,
               hint: hint && hint.offsetParent !== null ? hint.innerText : "" };
    });
    // R10 B-038: смена языка — подсказка сразу на новом языке (она в шторке, а не тостом поверх главной кнопки)
    const other = lang === "ru" ? "kk" : "ru";
    await page.evaluate((l) => document.dispatchEvent(new CustomEvent("birge:lang", { detail: { lang: l } })), other);
    await page.waitForTimeout(50);
    const after = await page.evaluate(() => document.querySelector(".r07-zoomhint")?.innerText || "");
    await page.evaluate((l) => document.dispatchEvent(new CustomEvent("birge:lang", { detail: { lang: l } })), lang);
    await page.waitForTimeout(200);
    x.hintAfterSwitch = after;
    const problems = [];
    const want = { ru: /Приблизьте карту/, kk: /картаны жақындатыңыз/ };
    if (x.rows !== 1 || x.h > 40) problems.push("легенда не в одну строку: " + JSON.stringify(x));
    if (x.zoomInLegend) problems.push("подсказка о масштабе строкой в легенде");
    if (x.under) problems.push("легенда под кнопками карты");
    if (x.toasts.length) problems.push("подсказка о масштабе тостом (над главной кнопкой): " + JSON.stringify(x.toasts));
    if (!want[lang].test(x.hint)) problems.push("нет подсказки о масштабе в шторке: " + x.hint);
    if (!want[other].test(after)) problems.push("после смены языка подсказка не на новом языке (B-038): " + after);
    await finish(page, errors, `legend-phone-375-${lang}`, "phone", problems, x);
  }

  // R11 ночь 7 п.1: горячее место вне Нуры (двор у ул. Коксенгир, Байконур) на офлайн-подложке — на улицах, не в пустом поле
  for (const [size, lang] of [["desktop", "kk"], ["phone", "ru"]]) {
    await shot(browser, `hot-outside-nura-${size === "phone" ? 375 : 1366}-${lang}`, size, `?lang=${lang}&role=akimat&view=nura#target=area:yard-1071933339&days=7`, async (page) => {
      await page.waitForFunction(() => window.__heat.state().selected === "area:yard-1071933339", null, { timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(1500);
      return page.evaluate(() => {
        const map = window.__map;
        const streets = map.queryRenderedFeatures({ layers: ["nura-street", "nura-minor"].filter((l) => map.getLayer(l)) }).length;
        return { selected: window.__heat.state().selected, zoom: Math.round(map.getZoom() * 10) / 10, streets };
      });
    }, async (page, m, x) => {
      const out = [];
      if (x.selected !== "area:yard-1071933339") out.push("цель не открылась: " + x.selected);
      if (x.streets < 20) out.push("вокруг горячего места почти нет улиц на офлайн-подложке: " + x.streets);
      return out;
    });
  }

  // UX_BRIEF правило 8: «меньше движения» в системе — карта не пролетает, пульса и анимаций нет
  {
    const page = await browser.newPage({ viewport: SIZES.desktop, deviceScaleFactor: 1, reducedMotion: "reduce" });
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    await page.goto(BASE + "?lang=ru&role=akimat&view=nura", { waitUntil: "networkidle" });
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.waitForTimeout(600);
    await page.click(".r07-item");
    await page.waitForTimeout(80);
    const x = await page.evaluate(async () => {
      const map = window.__map;
      const moving = map.isMoving();
      const key = window.__heat.state().selected;
      window.__heat.pulse(key);
      await new Promise((ok) => setTimeout(ok, 50));
      const pulse = document.querySelector(".r07-pulse");
      const anim = pulse ? getComputedStyle(pulse, "::before").animationName + "/" + getComputedStyle(pulse, "::after").animationName : "нет пульса";
      return { moving, key, anim, sr: document.querySelector(".r07-sr").textContent };
    });
    const problems = [];
    if (x.moving) problems.push("карта ещё летит при «меньше движения»");
    if (!x.key) problems.push("цель не выбрана");
    if (x.anim !== "none/none" && x.anim !== "нет пульса") problems.push("пульс анимируется: " + x.anim);
    if (!/^Новая жалоба: .+\. Сообщил/.test(x.sr || "")) problems.push("экранный диктор не услышит новую жалобу: " + x.sr);
    await page.screenshot({ path: path.join(OUT, "reduced-motion-1366-ru.jpg"), type: "jpeg", quality: 82 });
    results.push({ name: "reduced-motion-1366-ru", size: "desktop", query: "", problems: problems.concat(errors), badges: 0, extra: x });
    await page.close();
  }

  // Ревью кода (ночь): 1) прокрученная панель не прячет значки; 2) ошибка обновления — один тост, успех его закрывает;
  // 3) «Повторить» после перерисовки панели (смена языка) повторяет действие
  {
    const { page, errors } = await rawPage("phone", "?lang=ru&role=akimat&view=nura");
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.waitForTimeout(800);
    const pan = () => page.evaluate(() => new Promise((ok) => { const m = window.__map; m.once("moveend", ok); m.panBy([4, 0], { duration: 0 }); }));
    const count = () => page.evaluate(() => window.__heat.badges().length);
    const before = await count();
    await page.evaluate(() => { document.getElementById("panel").scrollTop = 400; });
    await pan();
    await page.waitForTimeout(300);
    const after = await count();
    const problems = [];
    if (!before || after < before - 2) problems.push("после прокрутки панели значки пропали: " + before + " → " + after);
    await finish(page, errors, "panel-scrolled-375-ru", "phone", problems, { before, after });
  }
  {
    let fail = false;
    const { page, errors } = await rawPage("desktop", "?lang=ru&role=akimat&view=nura", (pg) =>
      pg.route(HEAT_GET, (r) => (fail ? r.abort() : r.continue())));
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.waitForTimeout(500);
    fail = true;
    for (const d of ["7", "90", "30"]) { await page.click(`[data-days="${d}"]`); await page.waitForTimeout(700); }
    const stacked = await page.evaluate(() => document.querySelectorAll(".r07-toast--error").length);
    fail = false;
    await page.click('[data-days="7"]');
    await page.waitForFunction(() => window.__heat.state().status === "ready" && window.__heat.state().filters.days === 7, null, { timeout: 10000 }).catch(() => {});
    await page.waitForTimeout(500);
    const left = await page.evaluate(() => [...document.querySelectorAll(".r07-toast--error")].filter((t) => !t.classList.contains("r07-toast--out")).length);
    const problems = [];
    if (stacked !== 1) problems.push("тостов ошибки сразу: " + stacked + " (нужен один)");
    if (left !== 0) problems.push("после удачной загрузки тост ошибки остался");
    results.push({ name: "error-toast-once-1366-ru", size: "desktop", query: "", problems: problems.concat(errors), badges: 0, extra: { stacked, left } });
    await page.close();
  }
  {
    let posts = 0;
    const { page, errors } = await rawPage("desktop", "?lang=ru&role=akimat&view=nura", (pg) =>
      pg.route(/\/complaints\/[^/]+\/status/, (r) => { posts++; return posts === 1 ? r.fulfill({ status: 500, contentType: "application/json", body: "{}" }) : r.continue(); }));
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.click(".r07-item");
    await page.waitForSelector('[data-act="take"], [data-act="fixed"]');
    await page.click('[data-act="take"], [data-act="fixed"]');
    await page.waitForSelector(".r07-toast__action", { timeout: 10000 }).catch(() => {});
    await page.evaluate(() => document.dispatchEvent(new CustomEvent("birge:lang", { detail: { lang: "kk" } })));   // панель перерисована
    await page.waitForTimeout(300);
    const firstPosts = posts;
    await page.click(".r07-toast__action");
    await page.waitForTimeout(1200);
    const ok = await page.evaluate(() => [...document.querySelectorAll(".r07-toast:not(.r07-toast--error)")].map((t) => t.innerText).join(" | "));
    const problems = [];
    if (posts <= firstPosts) problems.push("«Повторить» после перерисовки ничего не отправил");
    if (!/алынды|белгіленді/.test(ok)) problems.push("нет сообщения об успехе после повтора: " + ok);
    results.push({ name: "retry-after-rerender-1366-kk", size: "desktop", query: "", problems: problems.concat(errors), badges: 0, extra: { posts, ok } });
    await page.close();
  }

  // R10 B-037: у цели только с примерами R07 (общая сборка, CIVIC_DEMO) — пометка вместо кнопок; 404 — не «проверьте связь»
  for (const [size, lang] of [["desktop", "ru"], ["phone", "kk"]]) {
    const { page, errors } = await rawPage(size, `?lang=${lang}&role=akimat&view=nura&sheet=full`, (pg) =>
      pg.route(HEAT_GET, async (r) => {
        const res = await r.fetch();
        const d = await res.json();
        const it = d.items.find((x) => x.state === "active");
        if (it) { it.examples_open = it.open_ids.length; it.open_ids = []; }
        await r.fulfill({ response: res, json: d });
      }));
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.click(".r07-item");
    await page.waitForSelector(".r07-card");
    await page.waitForTimeout(400);
    const x = await page.evaluate(() => ({ note: document.querySelector(".r07-card .r07-note--demo")?.innerText || "",
      buttons: document.querySelectorAll('.r07-card [data-act="take"], .r07-card [data-act="fixed"]').length }));
    const problems = [];
    if (x.buttons) problems.push("у цели только с примерами есть кнопки статуса");
    if (!(lang === "kk" ? /үлгі/i : /пример/i).test(x.note)) problems.push("нет пометки о примере: " + JSON.stringify(x));
    await finish(page, errors, `card-examples-only-${size === "phone" ? 375 : 1366}-${lang}`, size, problems, x);
  }
  {
    const { page, errors } = await rawPage("desktop", "?lang=ru&role=akimat&view=nura", (pg) =>
      pg.route(/\/complaints\/[^/]+\/status/, (r) => r.fulfill({ status: 404, contentType: "application/json", body: '{"error":"not_found"}' })));
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.click(".r07-item");
    await page.waitForSelector('[data-act="take"], [data-act="fixed"]');
    await page.click('[data-act="take"], [data-act="fixed"]');
    await page.waitForSelector(".r07-toast--error", { timeout: 10000 }).catch(() => {});
    const text = await page.evaluate(() => document.querySelector(".r07-toast--error")?.innerText || "");
    const problems = [];
    if (!/не найдено/.test(text) || /связь/.test(text)) problems.push("404 показан не так: " + text);
    results.push({ name: "action-404-1366-ru", size: "desktop", query: "", problems: problems.concat(errors), badges: 0, extra: { text } });
    await page.close();
  }

  // «Примерное место»: в карточке «Область на карте» + пометка, а не «Двор или квартал»
  for (const [size, lang] of [["desktop", "ru"], ["phone", "kk"]]) {
    const { page, errors } = await rawPage(size, `?lang=${lang}&role=akimat&view=nura&sheet=full`, (pg) =>
      pg.route(HEAT_GET, async (r) => {
        const res = await r.fetch();
        const d = await res.json();
        const it = d.items.find((x) => x.target.kind === "area");
        if (it) { it.approximate = true; it.target.label_ru = "Примерное место"; it.target.label_kk = "Шамамен көрсетілген орын"; }
        await r.fulfill({ response: res, json: d });
      }));
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.evaluate(() => { const b = [...document.querySelectorAll(".r07-item")].find((x) => /Примерное место|Шамамен/.test(x.innerText)); if (b) b.click(); });
    await page.waitForSelector(".r07-card", { timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(400);
    const x = await page.evaluate(() => ({ eyebrow: document.querySelector(".r07-eyebrow")?.textContent, note: document.querySelector(".r07-note--warn")?.innerText }));
    const want = lang === "kk" ? "Картадағы аумақ" : "Область на карте";
    const problems = [];
    if (!x.eyebrow || !x.eyebrow.includes(want) || !x.note) problems.push("карточка примерного места: " + JSON.stringify(x));
    await finish(page, errors, `card-approximate-${size === "phone" ? 375 : 1366}-${lang}`, size, problems, x);
  }

  // Клавиатура: Tab до главной кнопки, рамка фокуса, Esc закрывает карточку
  {
    const { page, errors } = await open(browser, "desktop", "?lang=ru&view=nura");
    await page.focus(".r07-item");
    await page.keyboard.press("Enter");
    await page.waitForSelector(".r07-card");
    let reached = false, outline = "";
    for (let i = 0; i < 20 && !reached; i++) {
      await page.keyboard.press("Tab");
      reached = await page.evaluate(() => document.activeElement && ["take", "fixed"].includes(document.activeElement.dataset.act));
    }
    if (reached) outline = await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle + " " + getComputedStyle(document.activeElement).outlineWidth);
    await page.keyboard.press("Escape");
    const closed = await page.evaluate(() => !document.querySelector(".r07-card"));
    const problems = reached && closed && outline.startsWith("solid") ? [] : ["Tab/Esc: reached=" + reached + " outline=" + outline + " closed=" + closed];
    results.push({ name: "keyboard-card-1366-ru", size: "desktop", query: "", problems: problems.concat(errors), badges: 0 });
    await page.close();
  }

  // Язык через событие на document (так шлёт i18n R11) и id устройства R09 + заголовок X-Birge-Device
  {
    const { page, errors } = await open(browser, "phone", "?lang=ru&role=resident&view=nura&sheet=full");
    // R15 S16: слабый id 3D-превью R05 в старом ключе "birge.device_id" не должен стать "birge.device"
    await page.evaluate(() => { localStorage.clear(); localStorage.setItem("birge.device_id", "dev-1760000000000-4fzyo82mvyq"); });
    await page.reload({ waitUntil: "networkidle" });
    await page.waitForFunction(() => window.__heat && window.__heat.state().status === "ready", null, { timeout: 30000 });
    await page.waitForTimeout(600);
    const headers = [];
    page.on("request", (r) => { if (r.url().includes("/metoo")) headers.push(r.headers()["x-birge-device"] || ""); });
    await page.evaluate(() => document.dispatchEvent(new CustomEvent("birge:lang", { detail: { lang: "kk" } })));
    await page.waitForTimeout(300);
    const kk = await page.evaluate(() => window.__heat.state().lang === "kk" && document.querySelector(".r07-h").innerText === "Шағымдар картасы");
    await page.click(".r07-item");
    await page.waitForSelector('[data-act="metoo"]');
    await page.click('[data-act="metoo"]');
    await page.waitForTimeout(900);
    const dev = await page.evaluate(() => localStorage.getItem("birge.device"));
    const problems = [];
    if (!kk) problems.push("birge:lang на document не переключил язык");
    if (!/^[A-Za-z0-9_-]{16,80}$/.test(dev || "")) problems.push("нет id устройства R09 в birge.device: " + dev);
    if (dev === "dev-1760000000000-4fzyo82mvyq" || !/^d-[A-Za-z0-9]{24}$/.test(dev || "")) problems.push("взят слабый id R05 из birge.device_id (R15 S16): " + dev);
    if (!headers.length || headers[0] !== dev) problems.push("«Я тоже» без заголовка X-Birge-Device: " + JSON.stringify(headers));
    results.push({ name: "lang-document-and-device-375", size: "phone", query: "", problems: problems.concat(errors), badges: 0 });
    await page.close();
  }

  await browser.close();
  fs.writeFileSync(path.join(OUT, "CHECKS.json"), JSON.stringify(results, null, 1));
  let bad = 0;
  for (const r of results) {
    if (r.problems.length) bad++;
    console.log((r.problems.length ? "FAIL " : "PASS ") + r.name + " · значков " + r.badges + (r.problems.length ? " · " + r.problems.join("; ") : ""));
  }
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
