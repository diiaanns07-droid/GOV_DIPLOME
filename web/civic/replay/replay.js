/* R07 · «Хроника города» (раунд 15, Birge): неделя или месяц тепловой карты за 10–20 секунд.
 *
 * Подключение (R01, research/round-15-results/R07/INTEGRATION.txt):
 *   <link rel="stylesheet" href="/civic/replay/replay.css">  <script src="/civic/replay/replay.js"></script>  (после heat.js)
 *   const rp = window.BirgeReplay.mount(root, { map, apiBase: "/api/civic/v2", heat: CivicShell.heat, lang, onClose });
 *   rp.play() · rp.pause() · rp.seek(i) · rp.setLang("kk") · rp.close() · rp.destroy() · rp.stats()
 *   BirgeReplay.open({ map, heat })      — сам создаёт место над картой и запускает неделю (кнопка, Ctrl+K, ?replay=7)
 *   BirgeReplay.attach({ map, heat, tools }) — кнопка «Хроника» в колонке кнопок карты + ?replay=7|30 в адресе
 *
 * Что видно: крупная дата, «Сообщили N · Исправлено M», шкала дней с графиком жалоб и отметками событий («Буран»),
 * ▶ / ❚❚, скорость 1× / 2×, чипы «7 дней / 30 дней», ×. Карта — те же значки и слои тепловой карты (heat.js replay.*):
 * цвет, ореол и число перетекают от дня к дню. Клавиши: Пробел — пуск / пауза, ← → — день, Home / End, Esc — закрыть.
 * «Меньше движения» — дни сменяются шагами, без перетекания. Закрыли — карта возвращается к «сегодня» без мигания
 * (последний кадр хроники = «сегодня», heat.js replay.end).
 * Все числа и отметки — с сервера (GET /api/civic/v2/heat/replay, ui/civic_heat/replay.py): здесь ничего не считается,
 * кроме промежуточных значений перетекания.
 */
(function () {
  "use strict";

  const VERSION = "r07-replay-round15";
  const NBSP = " ";
  const TOTAL_MS = { 7: 10500, 30: 15000 };   // вся хроника при 1×: неделя — 10,5 с, месяц — 15 с (IDEA: 10–20 с)
  const HOLD_MS = 700;                        // первый день стоит чуть дольше: зритель успевает понять, что это
  const SKELETON_AFTER_MS = 150;              // скелетон — не раньше 150 мс (COMMON, «Качество»)
  const reduce = () => Boolean(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  const DICT = {
    ru: {
      "replay.title": "Хроника города",
      "replay.open": "Хроника города",
      "replay.open_hint": "Неделя за 10 секунд",
      "replay.close": "Закрыть хронику",
      "replay.play": "Смотреть",
      "replay.pause": "Пауза",
      "replay.again": "Сначала",
      "replay.speed": "Скорость",
      "replay.period": "Период хроники",
      "replay.days": { one: "{n} день", few: "{n} дня", many: "{n} дней" },
      "replay.today": "сегодня",
      "replay.people": { one: "Сообщил {n} человек", few: "Сообщили {n} человека", many: "Сообщили {n} человек" },
      "replay.fixed": { one: "{n} место исправлено", few: "{n} места исправлено", many: "{n} мест исправлено" },
      "replay.slider": "День хроники",
      "replay.loading": "Загружаем хронику…",
      "replay.error": "Не удалось загрузить хронику",
      "replay.error_hint": "Проверьте связь и нажмите «Повторить».",
      "replay.retry": "Повторить",
      "replay.not_ready": "Хроника ещё не подключена к серверу",
      "replay.no_map": "Карта жалоб ещё не загрузилась",
      "replay.empty": "За эти дни жалоб нет",
      "replay.empty_hint": "Попробуйте 30 дней",
      "replay.demo": "Пример",
      "replay.keys": "Пробел — пауза · ← → — день · Esc — закрыть",
      "replay.event_in": "{title} · {district}",
      "replay.sr_day": "{date}. {people}. {fixed}",
    },
    kk: {
      "replay.title": "Қала шежіресі",
      "replay.open": "Қала шежіресі",
      "replay.open_hint": "Бір апта 10 секундта",
      "replay.close": "Шежірені жабу",
      "replay.play": "Көру",
      "replay.pause": "Үзіліс",
      "replay.again": "Басынан",
      "replay.speed": "Жылдамдық",
      "replay.period": "Шежіре кезеңі",
      "replay.days": { other: "{n} күн" },
      "replay.today": "бүгін",
      "replay.people": { other: "{n} адам хабарлады" },
      "replay.fixed": { other: "{n} орын түзетілді" },
      "replay.slider": "Шежіре күні",
      "replay.loading": "Шежіре жүктелуде…",
      "replay.error": "Шежірені жүктеу мүмкін болмады",
      "replay.error_hint": "Байланысты тексеріп, «Қайталау» түймесін басыңыз.",
      "replay.retry": "Қайталау",
      "replay.not_ready": "Шежіре серверге әлі қосылмаған",
      "replay.no_map": "Шағымдар картасы әлі жүктелген жоқ",
      "replay.empty": "Бұл күндері шағым болған жоқ",
      "replay.empty_hint": "30 күнді көріңіз",
      "replay.demo": "Үлгі",
      "replay.keys": "Бос орын — үзіліс · ← → — күн · Esc — жабу",
      "replay.event_in": "{title} · {district}",
      "replay.sr_day": "{date}. {people}. {fixed}",
    },
  };
  const MONTHS_FULL = {
    ru: ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"],
    kk: ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"],
  };
  const MONTHS_SHORT = {
    ru: ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
    kk: ["қаң", "ақп", "нау", "сәу", "мам", "мау", "шіл", "там", "қыр", "қаз", "қар", "жел"],
  };
  const WEEKDAYS = {
    ru: ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"],
    kk: ["жексенбі", "дүйсенбі", "сейсенбі", "сәрсенбі", "бейсенбі", "жұма", "сенбі"],
  };
  // Иконки одной толщины с ui-kit (1,9): ▶, ❚❚, ×, снежинка (буран), капля, пламя, волны, тревога, часы
  const ICONS = {
    play: '<path d="M8 5.5v13l10.5-6.5z" fill="currentColor" stroke="none"/>',
    pause: '<rect x="7" y="5.5" width="3.6" height="13" rx="1" fill="currentColor" stroke="none"/><rect x="13.4" y="5.5" width="3.6" height="13" rx="1" fill="currentColor" stroke="none"/>',
    again: '<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3"/><path d="M4.5 4.5v4h4"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    blizzard: '<path d="M12 2v20M3.3 7l17.4 10M3.3 17 20.7 7"/><path d="m9.5 3.5 2.5 2 2.5-2M9.5 20.5l2.5-2 2.5 2"/>',
    water_outage: '<path d="M12 3s6 6.6 6 11a6 6 0 0 1-12 0c0-4.4 6-11 6-11z"/>',
    // радиатор — тот же рисунок, что i-radiator набора R11 (раунд 15): отопительный сезон и авария на теплосети
    season: '<rect x="4" y="5" width="4" height="14" rx="2"/><rect x="10" y="5" width="4" height="14" rx="2"/><rect x="16" y="5" width="4" height="14" rx="2"/><path d="M2 16.5h2M20 16.5h2"/>',
    heat_outage: '<rect x="4" y="5" width="4" height="14" rx="2"/><rect x="10" y="5" width="4" height="14" rx="2"/><rect x="16" y="5" width="4" height="14" rx="2"/><path d="M2 16.5h2M20 16.5h2"/>',
    flood: '<path d="M3 15c2 0 2-1.5 4.5-1.5S9.5 15 12 15s2-1.5 4.5-1.5S18.5 15 21 15M3 19.5c2 0 2-1.5 4.5-1.5S9.5 19.5 12 19.5s2-1.5 4.5-1.5 2 1.5 4.5 1.5"/><path d="M12 3v8M8.5 7.5 12 11l3.5-3.5"/>',
    other: '<path d="M10.3 4.2 2.6 17.5a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4M12 17h.01"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
    replay: '<path d="M4.5 12a7.5 7.5 0 1 0 2.4-5.5"/><path d="M4.5 4.8v3.9h3.9"/><path d="M10.5 9.2v5.6l4.5-2.8z" fill="currentColor" stroke="none"/>',
  };

  // Поправка П1: один набор иконок R11. В оболочке — значки из спрайта ui-kit (у кого он есть), без неё — те же рисунки
  // здесь. ▶ / ❚❚ и радиатор (i-play, i-pause, i-radiator) R11 добавил в раунде 15: спрайт внешний (<use href="…#i-…">),
  // а пустой <use> не виден — поэтому их берём из спрайта, только когда символ в нём есть (checkSprite); иначе — свои.
  const SPRITE_IDS = { close: "close", blizzard: "snowflake", water_outage: "droplet", flood: "droplet", other: "alert",
    clock: "clock", again: "refresh", replay: "clock" };
  const SPRITE_NEW = { play: "play", pause: "pause", season: "radiator", heat_outage: "radiator" };
  const FILLED = { play: 1, pause: 1 };
  const ICON_ALIAS = { snow: "blizzard", ice: "blizzard" };   // снег и гололёд — та же снежинка, что у бурана
  let spriteCheck = null;
  function checkSprite() {
    if (spriteCheck) return spriteCheck;
    const ui = window.BirgeUI;
    const m = ui && typeof ui.icon === "function" ? /href="([^"#]+)#/.exec(ui.icon("close")) : null;
    if (!m || typeof fetch !== "function") return (spriteCheck = Promise.resolve(false));
    spriteCheck = fetch(m[1]).then((r) => (r.ok ? r.text() : "")).then((txt) => {
      Object.keys(SPRITE_NEW).forEach((k) => { if (txt.indexOf('id="i-' + SPRITE_NEW[k] + '"') >= 0) SPRITE_IDS[k] = SPRITE_NEW[k]; });
      return true;
    }).catch(() => false);
    return spriteCheck;
  }
  function svg(icon, size) {
    const name = ICON_ALIAS[icon] || icon;
    const s = size || 20;
    const ui = window.BirgeUI;
    if (ui && typeof ui.icon === "function" && SPRITE_IDS[name]) {
      return '<span class="rp-ic rp-ic--sprite' + (FILLED[name] ? " rp-ic--fill" : "") + '" style="width:' + s + "px;height:" + s + 'px" aria-hidden="true">' +
        ui.icon(SPRITE_IDS[name]) + "</span>";
    }
    return '<svg class="rp-ic" viewBox="0 0 24 24" width="' + s + '" height="' + s + '" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || ICONS.other) + "</svg>";
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }
  function pluralForm(lang, n) {
    if (lang !== "ru") return "other";
    const a = Math.abs(n), n10 = a % 10, n100 = a % 100;
    if (Math.floor(a) !== a) return "other";
    if (n10 === 1 && n100 !== 11) return "one";
    if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return "few";
    return "many";
  }
  function fmtNum(n) {
    const s = String(Math.round(Number(n) || 0));
    return s.length > 3 ? s.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP) : s;
  }
  // День кадра — строка ГГГГ-ММ-ДД по Астане (сервер уже перевёл): разбираем без часовых поясов браузера
  function ymd(s) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || "");
    return m ? { y: +m[1], m: +m[2] - 1, d: +m[3], wd: new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay() } : null;
  }
  function unwrap(body) {
    return body && body.ok === true && body.data && !body.frames ? body.data : body;
  }
  // Карта MapLibre оболочки — глобальная переменная web/map.js (window.map — это элемент #map, не карта)
  function globalMap() {
    try { return typeof map !== "undefined" && map && typeof map.addLayer === "function" ? map : null; } catch (e) { return null; }  // eslint-disable-line no-undef
  }
  function heatHandle(opts) {
    if (opts.heat && opts.heat.replay) return opts.heat;
    const shell = window.CivicShell && window.CivicShell.heat;
    if (shell && shell.replay) return shell;
    const cur = window.CivicHeat && window.CivicHeat.current;
    return cur && cur.replay ? cur : null;
  }

  // ---------------------------------------------------------------- кадры: компактный ответ → дни целиком
  // Сервер шлёт формы целей один раз (targets), в первом кадре — все цели, дальше только изменения. Здесь собираем
  // для каждого дня полный список в виде элементов /heat — их рисует heat.js теми же значками.
  function buildDays(body) {
    const targets = body.targets || {};
    const asItem = (c) => {
      const st = targets[c.key] || {};
      const item = {
        target: st.target || { kind: c.key.split(":")[0], id: c.key.slice(c.key.indexOf(":") + 1) },
        geometry: st.geometry, anchor: st.anchor, district: st.district, approximate: !!st.approximate,
        weight: c.w, level: c.level, color: c.color, count: c.count, state: c.state,
        fixed_kind: c.fixed_kind || null, reopened: !!c.reopened, by_category: st.cat ? { [st.cat]: c.count } : {},
      };
      if (c.targets != null) item.targets = c.targets;
      return item;
    };
    const order = (a, b) => (b.state === "active") - (a.state === "active") || (b.weight || 0) - (a.weight || 0) || (b.count || 0) - (a.count || 0);
    let items = new Map(), districts = new Map();
    return (body.frames || []).map((f) => {
      if (f.items) {
        items = new Map(f.items.map((c) => [c.key, c]));
        districts = new Map((f.districts || []).map((c) => [c.key, c]));
      } else {
        items = new Map(items);
        districts = new Map(districts);
        (f.removed || []).forEach((k) => items.delete(k));
        (f.changed || []).forEach((c) => items.set(c.key, c));
        (f.districts_removed || []).forEach((k) => districts.delete(k));
        (f.districts_changed || []).forEach((c) => districts.set(c.key, c));
      }
      return {
        date: f.date, at: f.at, totals: f.totals || {}, demo: body.demo,
        items: [...items.values()].map(asItem).filter((it) => it.anchor || it.geometry).sort(order),
        districts: [...districts.values()].map(asItem).sort(order),
      };
    });
  }

  // ---------------------------------------------------------------- модуль
  function mount(root, options) {
    if (!root) throw new Error("BirgeReplay.mount: нужен root");
    const opts = options || {};
    const map = opts.map || globalMap();
    const heat = heatHandle(opts);
    const apiBase = String(opts.apiBase || (heat && heat.replay.apiBase) || "/api/civic/v2").replace(/\/$/, "");
    const fetchFn = opts.fetch || (heat && heat.replay.fetch) || window.fetch.bind(window);
    const S = {
      lang: opts.lang || (heat && heat.replay.lang && heat.replay.lang()) || (window.Birge && window.Birge.i18n ? window.Birge.i18n.lang() : document.documentElement.lang === "kk" ? "kk" : "ru"),
      period: opts.days === 30 ? 30 : 7,
      speed: 1,
      status: "loading",   // loading | ready | error | not_ready | no_map | empty
      body: null, days: [], index: 0, pos: 0, playing: false, ended: false, began: false,
      raf: null, stepStart: 0, stepMs: 0, holdUntil: 0, reqSeq: 0, destroyed: false,
      fps: { frames: 0, since: 0, worst: 0, last: 0, samples: [] },
      shownPeople: null, shownFixed: null, counter: null,
    };

    function t(key, params) {
      const p = params || {};
      const g = window.Birge && window.Birge.i18n;
      if (g && typeof g.has === "function" && g.has(key, S.lang)) return g.t(key, p, S.lang);
      let v = (DICT[S.lang] && DICT[S.lang][key]) || DICT.ru[key];
      if (v == null) return key;
      if (typeof v === "object") v = v[pluralForm(S.lang, Number(p.n))] || v.other || v.many || "";
      return v.replace(/\{(\w+)\}/g, (w, name) => (name in p ? (typeof p[name] === "number" ? fmtNum(p[name]) : p[name]) : w));
    }
    const day = (i) => S.days[Math.max(0, Math.min(S.days.length - 1, i))] || null;
    const isToday = (i) => i === S.days.length - 1;
    function bigDate(d) {
      const x = ymd(d && d.date);
      return x ? x.d + NBSP + MONTHS_FULL[S.lang][x.m] : "";
    }
    function shortDate(d) {
      const x = ymd(d && d.date);
      return x ? x.d + NBSP + MONTHS_SHORT[S.lang][x.m] : "";
    }
    function weekday(d) {
      const x = ymd(d && d.date);
      return x ? WEEKDAYS[S.lang][x.wd] : "";
    }
    // Район у отметки — только если его ещё нет в названии («Буран в Нуре» уже о Нуре; «Буран · Нура» — нет)
    const districtName = (ev) => {
      const d = (S.lang === "kk" ? ev.district_kk || ev.district_ru : ev.district_ru) || "";
      const title = ((S.lang === "kk" ? ev.title_kk || ev.title_ru : ev.title_ru) || "").toLocaleLowerCase();
      const stem = d.toLocaleLowerCase().slice(0, Math.max(3, d.length - 1));
      return d && !title.includes(stem) ? d : "";
    };
    const eventTitle = (ev) => (S.lang === "kk" ? ev.title_kk || ev.title_ru : ev.title_ru) || "";

    // ----- место полосы: не поверх плашек оболочки у нижнего края карты (строка легенды, карточка слева / справа) -----
    // Свои отступы оболочка может задать сама (--rp-left / --rp-right на .rp-host); иначе считаем по плашкам, которые
    // заходят в нижнюю полосу карты. Телефон — полоса во всю ширину (CSS), отступы не нужны.
    const AVOID = "#birge-legend, .birge-legend-line, #civic-panel, .r07-maplegend, [data-rp-avoid]" + (opts.avoid ? ", " + opts.avoid : "");
    function placeBar() {
      const host = root.closest(".rp-host") || root;
      const box = (host.parentElement || document.body).getBoundingClientRect();
      if (!box.width || innerWidth <= 760 || opts.place === false) return;
      const band = box.bottom - 200;
      let left = 0, right = 0;
      document.querySelectorAll(AVOID).forEach((el) => {
        if (root.contains(el) || !el.getClientRects().length || getComputedStyle(el).visibility === "hidden") return;
        const r = el.getBoundingClientRect();
        if (!r.width || r.bottom < band || r.top > box.bottom || r.right < box.left || r.left > box.right) return;
        if (r.left + r.width / 2 < box.left + box.width / 2) left = Math.max(left, r.right - box.left + 12);
        else right = Math.max(right, box.right - r.left + 12);
      });
      if (!host.style.getPropertyValue("--rp-left-fixed")) host.style.setProperty("--rp-left", Math.round(left) + "px");
      if (!host.style.getPropertyValue("--rp-right-fixed")) host.style.setProperty("--rp-right", Math.round(right) + "px");
    }
    const placeTimer = setInterval(() => { if (!S.destroyed) placeBar(); }, 1000);
    window.addEventListener("resize", placeBar);

    // ----- разметка -----
    root.classList.add("rp-root", "bk-app");
    root.innerHTML = '<section class="rp" role="region"><div class="rp-bar bk-glass bk-glass--strong"></div>' +
      '<p class="rp-sr" role="status" aria-live="polite"></p></section>';
    const box = root.querySelector(".rp");
    const bar = root.querySelector(".rp-bar");
    const sr = root.querySelector(".rp-sr");
    const opener = document.activeElement;
    document.body.classList.add("birge-replay-open");
    placeBar();

    function render() {
      if (S.destroyed) return;
      box.setAttribute("aria-label", t("replay.title"));
      box.dataset.status = S.status;
      if (S.status !== "ready") { bar.innerHTML = stateHtml(); bindState(); return; }
      const d = day(S.index);
      const tail = S.days.length - 1;
      const periodBtn = (n) => '<button type="button" class="rp-chip" data-period="' + n + '" aria-pressed="' + (S.period === n) + '">' + esc(t("replay.days", { n })) + "</button>";
      // Две строки: дата · что происходит · кнопки; ниже — шкала на всю ширину (главный элемент хроники).
      bar.innerHTML =
        '<div class="rp-date">' +
          '<span class="rp-title">' + esc(t("replay.title")) + "</span>" +
          '<b class="rp-day" aria-hidden="true"></b><span class="rp-wd" aria-hidden="true"></span>' +
        "</div>" +
        '<div class="rp-head">' +
          '<div class="rp-head__top"><span class="rp-event" hidden></span>' +
            (S.body && S.body.demo ? '<span class="rp-tag bk-tag bk-tag--demo">' + esc(t("replay.demo")) + "</span>" : "") + "</div>" +
          '<div class="rp-nums"><span class="rp-num rp-num--people"><i aria-hidden="true"></i><span class="rp-people"></span></span>' +
            '<span class="rp-num rp-num--fixed"><i aria-hidden="true"></i><span class="rp-fixed"></span></span></div>' +
        "</div>" +
        '<div class="rp-period" role="group" aria-label="' + esc(t("replay.period")) + '">' + periodBtn(7) + periodBtn(30) + "</div>" +
        '<div class="rp-ctl">' +
          '<button type="button" class="rp-speed" aria-label="' + esc(t("replay.speed")) + '" title="' + esc(t("replay.speed")) + '">' + S.speed + "×</button>" +
          '<button type="button" class="rp-play" aria-keyshortcuts="Space"></button>' +
          '<button type="button" class="rp-x" aria-keyshortcuts="Escape" aria-label="' + esc(t("replay.close")) + '" title="' + esc(t("replay.close")) + ' · Esc">' + svg("close", 18) + "</button>" +
        "</div>" +
        '<div class="rp-track" role="slider" tabindex="0" aria-keyshortcuts="ArrowLeft ArrowRight Home End" title="' + esc(t("replay.keys")) + '" aria-label="' +
          esc(t("replay.slider")) + '" aria-valuemin="0" aria-valuemax="' + tail + '">' +
          sparkHtml() + marksHtml() + '<div class="rp-rail"><i class="rp-fill"></i></div>' + ticksHtml() +
          '<i class="rp-thumb" aria-hidden="true"></i>' +
        "</div>";
      bindBar();
      updateBar(true);
      void d;
    }

    function stateHtml() {
      const close = '<button type="button" class="rp-x" aria-label="' + esc(t("replay.close")) + '" title="' + esc(t("replay.close")) + '">' + svg("close", 18) + "</button>";
      if (S.status === "loading") {
        return '<div class="rp-skel" aria-busy="true" aria-label="' + esc(t("replay.loading")) + '"' + (S.showSkeleton ? "" : ' data-wait="1"') + '>' +
          '<i class="rp-skel__date"></i><span class="rp-skel__main"><i></i><i></i></span><i class="rp-skel__btn"></i></div>' + close;
      }
      const msg = { error: ["replay.error", "replay.error_hint"], not_ready: ["replay.not_ready", null], no_map: ["replay.no_map", null],
        empty: ["replay.empty", S.period === 7 ? "replay.empty_hint" : null] }[S.status] || ["replay.error", null];
      const action = S.status === "error" ? '<button type="button" class="rp-btn" data-retry>' + esc(t("replay.retry")) + "</button>"
        : S.status === "empty" && S.period === 7 ? '<button type="button" class="rp-btn" data-period="30">' + esc(t("replay.days", { n: 30 })) + "</button>" : "";
      return '<div class="rp-msg" role="' + (S.status === "error" ? "alert" : "status") + '">' + svg(S.status === "empty" ? "clock" : "other", 22) +
        '<span class="rp-msg__text"><b>' + esc(t(msg[0])) + "</b>" + (msg[1] ? "<span>" + esc(t(msg[1])) + "</span>" : "") + "</span>" + action + "</div>" + close;
    }
    function bindState() {
      bar.querySelector(".rp-x")?.addEventListener("click", () => close());
      bar.querySelector("[data-retry]")?.addEventListener("click", () => void load());
      bar.querySelectorAll("[data-period]").forEach((b) => b.addEventListener("click", () => setPeriod(Number(b.dataset.period))));
    }

    // График жалоб по дням под шкалой: всплеск бурана виден ещё до запуска
    function sparkHtml() {
      const vals = S.days.map((d) => Number(d.totals.people) || 0);
      const max = Math.max(1, ...vals);
      if (vals.length < 2) return "";
      const pts = vals.map((v, i) => [(i / (vals.length - 1)) * 100, 100 - (v / max) * 100]);
      const line = pts.map(([x, y], i) => (i ? "L" : "M") + x.toFixed(2) + " " + y.toFixed(2)).join(" ");
      return '<svg class="rp-spark" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path class="rp-spark__area" d="' + line +
        ' L100 100 L0 100 Z"/><path class="rp-spark__line" d="' + line + '" vector-effect="non-scaling-stroke"/></svg>';
    }
    function dayIndex(dateStr) {
      return S.days.findIndex((d) => d.date === dateStr);
    }
    // Отметки событий: полоса от начала до конца события (или до сегодня, если идёт), подпись — сверху
    function marksHtml() {
      const evs = (S.body && S.body.events) || [];
      if (!evs.length || S.days.length < 2) return "";
      const tail = S.days.length - 1;
      const first = S.days[0].date, last = S.days[tail].date;
      const ranked = evs.slice().sort(byRank);
      return '<div class="rp-marks">' + evs.map((ev) => {
        const a = ev.start < first ? 0 : dayIndex(ev.start);
        const b = !ev.end || ev.end > last ? tail : dayIndex(ev.end);
        if (a < 0 || b < 0) return "";
        const left = (a / tail) * 100, width = Math.max(((b - a) / tail) * 100, 0);
        const title = eventTitle(ev);
        return '<span class="rp-mark rp-mark--' + esc(ev.kind) + (ev.kind === "season" ? " rp-mark--background" : "") + '" data-rank="' + ranked.indexOf(ev) +
          '" style="left:' + left.toFixed(2) + "%;width:" + width.toFixed(2) + '%" title="' +
          esc(title + (districtName(ev) ? " · " + districtName(ev) : "")) + '"><span class="rp-mark__label">' + svg(ev.kind, 14) + '<span class="rp-mark__text">' + esc(title) + "</span></span></span>";
      }).join("") + "</div>";
    }
    function ticksHtml() {
      const n = S.days.length;
      if (!n) return "";
      const tail = n - 1;
      const out = [];
      for (let i = 0; i < n; i++) {
        // неделя — каждый день; месяц — первый день и раз в неделю от сегодня назад (не ближе 4 дней к краям)
        const showLabel = n <= 8 || i === 0 || i === tail || ((tail - i) % 7 === 0 && i >= 4);
        const text = isToday(i) ? t("replay.today") : n <= 8 && i ? String(ymd(S.days[i].date).d) : shortDate(S.days[i]);
        // день перед «сегодня» — без подписи на узкой шкале (телефон): «14» налезало на «сегодня»
        out.push('<i class="rp-tick' + (showLabel ? " rp-tick--label" : "") + (i === tail - 1 ? " rp-tick--prev" : "") + '" style="left:' + ((tail ? i / tail : 0) * 100).toFixed(2) + '%">' +
          (showLabel ? "<span>" + esc(text) + "</span>" : "") + "</i>");
      }
      return '<div class="rp-ticks" aria-hidden="true">' + out.join("") + "</div>";
    }

    function bindBar() {
      bar.querySelector(".rp-play").addEventListener("click", () => (S.playing ? pause() : play()));
      bar.querySelector(".rp-x").addEventListener("click", () => close());
      bar.querySelector(".rp-speed").addEventListener("click", () => {
        S.speed = S.speed === 1 ? 2 : 1;
        bar.querySelector(".rp-speed").textContent = S.speed + "×";
        if (S.playing) { S.stepMs = stepMs(); }
      });
      bar.querySelectorAll("[data-period]").forEach((b) => b.addEventListener("click", () => setPeriod(Number(b.dataset.period))));
      const track = bar.querySelector(".rp-track");
      let dragging = false;
      const seekAt = (ev) => {
        const r = track.getBoundingClientRect();
        const k = Math.max(0, Math.min(1, (ev.clientX - r.left) / Math.max(1, r.width)));
        seek(Math.round(k * (S.days.length - 1)));
      };
      track.addEventListener("pointerdown", (ev) => {
        dragging = true;
        try { track.setPointerCapture(ev.pointerId); } catch (e) { /* старый браузер */ }
        pause();
        seekAt(ev);
      });
      track.addEventListener("pointermove", (ev) => { if (dragging) seekAt(ev); });
      const stop = () => { dragging = false; };
      track.addEventListener("pointerup", stop);
      track.addEventListener("pointercancel", stop);
    }

    // Обновление шкалы и чисел (каждый кадр анимации — только стили, без пересборки разметки)
    function updateBar(full) {
      if (S.status !== "ready") return;
      const tail = Math.max(1, S.days.length - 1);
      const pos = Math.max(0, Math.min(S.days.length - 1, S.pos));
      const pct = (pos / tail) * 100;
      const fill = bar.querySelector(".rp-fill"), thumb = bar.querySelector(".rp-thumb");
      if (fill) fill.style.transform = "scaleX(" + (pos / tail).toFixed(4) + ")";
      if (thumb) thumb.style.left = pct.toFixed(3) + "%";
      if (!full) return;
      const d = day(S.index);
      const track = bar.querySelector(".rp-track");
      track.setAttribute("aria-valuenow", String(S.index));
      track.setAttribute("aria-valuetext", bigDate(d) + (isToday(S.index) ? " (" + t("replay.today") + ")" : ""));
      bar.querySelector(".rp-day").textContent = bigDate(d);
      bar.querySelector(".rp-wd").textContent = isToday(S.index) ? t("replay.today") : weekday(d);
      const play = bar.querySelector(".rp-play");
      const label = S.playing ? t("replay.pause") : S.ended ? t("replay.again") : t("replay.play");
      play.innerHTML = svg(S.playing ? "pause" : S.ended ? "again" : "play", 20) + '<span class="rp-play__text">' + esc(label) + "</span>";
      play.setAttribute("aria-label", label);
      play.title = label + " · " + (S.lang === "kk" ? "Бос орын" : "Пробел");
      play.classList.toggle("rp-play--on", S.playing);
      // Событие, которое идёт в этот день: «Буран · Нура» у даты
      const ev = activeEvent(d);
      const evEl = bar.querySelector(".rp-event");
      if (ev) {
        evEl.hidden = false;
        evEl.className = "rp-event rp-event--" + ev.kind;
        evEl.innerHTML = svg(ev.kind, 14) + "<span>" + esc(districtName(ev) ? t("replay.event_in", { title: eventTitle(ev), district: districtName(ev) }) : eventTitle(ev)) + "</span>";
      } else evEl.hidden = true;
      bar.querySelectorAll(".rp-mark").forEach((m, i) => m.classList.toggle("rp-mark--on", ((S.body.events || [])[i] || null) === ev));
      if (full === true) fitMarkLabels();
      countTo(Number(d.totals.people) || 0, Number(d.totals.fixed) || 0);
    }
    // Событие дня для подписи у даты и на шкале: фоновое («отопительный сезон», kind season) — последним; событие с
    // кризисом R17 или сценой демо («Буран в Нуре», сцена 9) важнее остальных; дальше короткое важнее долгого, свежее — давнего
    function eventRank(ev) {
      const last = S.days.length ? S.days[S.days.length - 1].date : ev.start;
      const span = (Date.parse(ev.end || last) - Date.parse(ev.start)) / 86400000 || 0;
      return [ev.kind === "season" ? 1 : 0, ev.incident || ev.scene ? 0 : 1, span, -Date.parse(ev.start)];
    }
    const byRank = (a, b) => { const x = eventRank(a), y = eventRank(b); return x[0] - y[0] || x[1] - y[1] || x[2] - y[2] || x[3] - y[3]; };
    // Подписи событий на шкале не налезают: важнее (data-rank меньше) — с названием; менее важной, если тесно, — только
    // значок события (название — у даты, когда день дойдёт до полосы); нет места и значку — только полоса.
    // У правого края подпись не выходит за шкалу — сдвигается влево над своей полосой.
    function fitMarkLabels() {
      const track = bar.querySelector(".rp-track");
      if (!track) return;
      const edge = track.getBoundingClientRect().right;
      const marks = [...bar.querySelectorAll(".rp-mark")].sort((a, b) => Number(a.dataset.rank) - Number(b.dataset.rank));
      const placed = [];
      const place = (label) => {
        label.style.transform = "";
        const r = label.getBoundingClientRect();
        const over = Math.ceil(r.right - edge);
        if (over <= 0) return { left: r.left, right: r.right };
        label.style.transform = "translateX(" + -over + "px)";
        return { left: r.left - over, right: r.right - over };
      };
      const free = (r) => !placed.some((q) => !(r.right + 4 < q.left || q.right + 4 < r.left));
      marks.forEach((m) => {
        const label = m.querySelector(".rp-mark__label");
        m.classList.remove("rp-mark--nolabel", "rp-mark--icon");
        let r = place(label);
        if (free(r)) { placed.push(r); return; }
        m.classList.add("rp-mark--icon");
        r = place(label);
        if (free(r)) { placed.push(r); return; }
        m.classList.remove("rp-mark--icon");
        m.classList.add("rp-mark--nolabel");
      });
    }
    function activeEvent(d) {
      if (!d) return null;
      return ((S.body && S.body.events) || []).filter((ev) => ev.start <= d.date && (!ev.end || ev.end >= d.date)).sort(byRank)[0] || null;
    }
    // «Сообщили 230 человек» и «21 место исправлено» перетекают вместе с картой
    function countTo(people, fixed) {
      const pe = bar.querySelector(".rp-people"), fe = bar.querySelector(".rp-fixed");
      if (!pe || !fe) return;
      const fromP = S.shownPeople == null ? people : S.shownPeople, fromF = S.shownFixed == null ? fixed : S.shownFixed;
      if (S.counter) cancelAnimationFrame(S.counter);
      const dur = reduce() ? 0 : Math.min(600, S.stepMs || 600);
      const started = performance.now();
      const paint = (k) => {
        const e = 1 - Math.pow(1 - k, 3);
        const p = Math.round(fromP + (people - fromP) * e), f = Math.round(fromF + (fixed - fromF) * e);
        pe.textContent = t("replay.people", { n: p });
        fe.textContent = t("replay.fixed", { n: f });
        S.shownPeople = p; S.shownFixed = f;
      };
      if (!dur || (fromP === people && fromF === fixed)) { paint(1); return; }
      const step = (now) => {
        const k = Math.min(1, (now - started) / dur);
        paint(k);
        S.counter = k < 1 ? requestAnimationFrame(step) : null;
      };
      S.counter = requestAnimationFrame(step);
    }

    // ----- загрузка -----
    async function load() {
      const seq = ++S.reqSeq;
      if (!heat || !map) { S.status = "no_map"; render(); return; }
      S.status = "loading";
      S.showSkeleton = false;
      render();
      const skel = setTimeout(() => { if (S.status === "loading" && seq === S.reqSeq) { S.showSkeleton = true; render(); } }, SKELETON_AFTER_MS);
      const f = (heat.replay.filters && heat.replay.filters()) || {};
      const q = new URLSearchParams();
      q.set("last", String(S.period));
      if (f.days) q.set("days", String(f.days));
      if (f.category) q.set("category", f.category);
      if (f.district) q.set("district", f.district);
      const sprite = checkSprite();
      try {
        const res = await fetchFn(apiBase + "/heat/replay?" + q.toString(), { headers: { Accept: "application/json" } });
        let body = null;
        try { body = await res.json(); } catch (e) { body = null; }
        if (seq !== S.reqSeq || S.destroyed) return;
        if (!res.ok) { S.status = res.status === 503 ? "not_ready" : "error"; render(); return; }
        body = unwrap(body);
        S.body = body;
        S.days = buildDays(body);
        if (!S.days.length || S.days.every((d) => !d.items.length && !(d.totals.people > 0))) { S.status = "empty"; render(); return; }
        // значки ▶ / ❚❚ — до первой отрисовки полосы (спрайт обычно уже в кэше); не дождались — подменятся при ответе
        await Promise.race([sprite, new Promise((r) => setTimeout(r, 300))]);
        if (seq !== S.reqSeq || S.destroyed) return;
        sprite.then(() => { if (seq === S.reqSeq && !S.destroyed) updateBar(); });
        S.status = "ready";
        heat.replay.begin();
        S.began = true;
        placeBar();   // своя легенда тепловой карты на время хроники спрятана — место полосы считаем заново
        S.index = 0; S.pos = 0; S.ended = false;
        S.shownPeople = null; S.shownFixed = null;
        render();
        show(0, 0);
        announce();
        if (opts.autoplay !== false) play(true);
        else focusPlay();
      } catch (err) {
        if (seq !== S.reqSeq || S.destroyed) return;
        S.status = "error";
        render();
      } finally {
        clearTimeout(skel);
      }
    }

    // ----- воспроизведение -----
    function stepMs() {
      const n = Math.max(2, S.days.length);
      return (TOTAL_MS[S.period] || TOTAL_MS[7]) / (n - 1) / S.speed;
    }
    function show(i, ms) {
      S.index = Math.max(0, Math.min(S.days.length - 1, i));
      heat.replay.frame(S.days[S.index], { ms: reduce() ? 0 : ms });
      updateBar(true);
    }
    function play(fromOpen) {
      if (S.status !== "ready") return;
      if (S.ended || S.index >= S.days.length - 1) { S.ended = false; S.pos = 0; show(0, 400); }
      S.playing = true;
      S.stepMs = stepMs();
      const now = performance.now();
      S.holdUntil = now + (S.index === 0 ? HOLD_MS : 0);
      S.stepStart = Math.max(now, S.holdUntil);
      S.fps = { frames: 0, since: now, worst: 0, last: now, samples: [] };
      updateBar(true);
      if (!fromOpen) focusPlay();
      tick(now);
    }
    function pause() {
      if (!S.playing) return;
      S.playing = false;
      if (S.raf) cancelAnimationFrame(S.raf);
      S.raf = null;
      S.pos = S.index;
      updateBar(false);
      updateBar(true);
    }
    // Один цикл requestAnimationFrame: шкала едет плавно, новый день — когда доехали до его отметки.
    // «Меньше движения»: тот же темп, но день сменяется шагом и шкала прыгает по дням.
    function tick(now) {
      if (!S.playing || S.destroyed) return;
      const f = S.fps;
      const dt = now - f.last;
      if (f.frames > 0) { f.worst = Math.max(f.worst, dt); f.samples.push(dt); if (f.samples.length > 600) f.samples.shift(); }
      f.frames += 1; f.last = now;
      if (now >= S.holdUntil) {
        const k = (now - S.stepStart) / S.stepMs;
        if (k >= 1) {
          if (S.index >= S.days.length - 1) { finish(); return; }
          S.stepStart = now;
          show(S.index + 1, S.stepMs * 0.92);
          announce();
        }
        const into = Math.min(1, (now - S.stepStart) / S.stepMs);
        S.pos = reduce() ? S.index : S.index - 1 + Math.min(1, into / 0.92);
        if (S.index === 0) S.pos = 0;
        updateBar(false);
      }
      S.raf = requestAnimationFrame(tick);
    }
    function finish() {
      S.playing = false;
      S.ended = true;
      S.raf = null;
      S.pos = S.days.length - 1;
      updateBar(false);
      updateBar(true);
    }
    function seek(i) {
      if (S.status !== "ready") return;
      const was = S.playing;
      if (was) pause();
      const next = Math.max(0, Math.min(S.days.length - 1, i));
      S.ended = next === S.days.length - 1;
      S.pos = next;
      if (next !== S.index) { show(next, 350); announce(); } else updateBar(true);
      updateBar(false);
    }
    function setPeriod(n) {
      if (n !== 7 && n !== 30) return;
      if (S.period === n && S.status === "ready") return;
      S.period = n;
      pause();
      void load();
    }
    function announce() {
      const d = day(S.index);
      if (!d) return;
      sr.textContent = t("replay.sr_day", { date: bigDate(d), people: t("replay.people", { n: d.totals.people || 0 }), fixed: t("replay.fixed", { n: d.totals.fixed || 0 }) });
    }
    function focusPlay() {
      const b = bar.querySelector(".rp-play");
      if (b && document.activeElement !== b) b.focus({ preventScroll: true });
    }

    // ----- клавиатура: Пробел, ← →, Home / End, Esc (фаза захвата — Esc не закрывает заодно карточку оболочки) -----
    function onKey(ev) {
      if (S.destroyed || ev.defaultPrevented || ev.altKey || ev.ctrlKey || ev.metaKey) return;
      const tag = (ev.target && ev.target.tagName) || "";
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag) || (ev.target && ev.target.isContentEditable)) return;
      if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); close(); return; }
      if (S.status !== "ready") return;
      const onButton = tag === "BUTTON" && root.contains(ev.target);
      if (ev.key === " " || ev.code === "Space") {
        if (onButton) return;   // Пробел на кнопке нажмёт саму кнопку
        ev.preventDefault();
        S.playing ? pause() : play();
        return;
      }
      const moves = { ArrowLeft: -1, ArrowRight: 1 };
      if (ev.key in moves) { ev.preventDefault(); ev.stopPropagation(); seek(S.index + moves[ev.key]); return; }
      if (ev.key === "Home") { ev.preventDefault(); seek(0); return; }
      if (ev.key === "End") { ev.preventDefault(); seek(S.days.length - 1); }
    }
    document.addEventListener("keydown", onKey, true);
    function onLang(ev) {
      const next = ev && ev.detail && ev.detail.lang;
      if (next && next !== S.lang) setLang(next);
    }
    window.addEventListener("birge:lang", onLang);
    document.addEventListener("birge:lang", onLang);

    function setLang(lang) {
      S.lang = lang === "kk" ? "kk" : "ru";
      S.shownPeople = null; S.shownFixed = null;
      render();
      if (S.status === "ready") updateBar(false);
    }

    // ----- закрытие: карта возвращается к «сегодня» тем же перетеканием, фокус — туда, откуда открыли -----
    // Закрытие идёт 200 мс (полоса уходит вниз); открыть снова в это время можно — open() дозакрывает её сразу (finish).
    let closed = false, finished = false, closeTimer = 0;
    function finishClose(focusOpener) {
      if (finished) return;
      finished = true;
      clearTimeout(closeTimer);
      if (!S.destroyed) destroyDom();
      if (focusOpener && opener && opener.isConnected && typeof opener.focus === "function") opener.focus({ preventScroll: true });
      if (typeof opts.onClose === "function") opts.onClose();
    }
    function close() {
      if (closed) return;
      closed = true;
      pause();
      if (S.began && heat) heat.replay.end({ ms: reduce() ? 0 : 700 });
      S.began = false;
      box.classList.add("rp--out");
      if (reduce()) finishClose(true); else closeTimer = setTimeout(() => finishClose(true), 200);
    }
    function destroyDom() {
      S.destroyed = true;
      S.reqSeq++;
      if (S.raf) cancelAnimationFrame(S.raf);
      if (S.counter) cancelAnimationFrame(S.counter);
      document.removeEventListener("keydown", onKey, true);
      clearInterval(placeTimer);
      window.removeEventListener("resize", placeBar);
      window.removeEventListener("birge:lang", onLang);
      document.removeEventListener("birge:lang", onLang);
      document.body.classList.remove("birge-replay-open");
      root.innerHTML = "";
      root.classList.remove("rp-root");
      if (active === handle) active = null;
    }

    const handle = {
      version: VERSION,
      play: () => play(),
      pause: () => pause(),
      seek: (i) => seek(i),
      setPeriod: (n) => setPeriod(n),
      setLang: (lang) => setLang(lang),
      close: () => close(),
      closing: () => closed && !finished,
      destroy: () => { if (!closed) { closed = true; pause(); if (S.began && heat) heat.replay.end({ ms: 0 }); S.began = false; } finishClose(false); },
      // Для проверок (R10, тесты R07): состояние и замер плавности последнего воспроизведения
      state: () => ({ status: S.status, period: S.period, index: S.index, days: S.days.map((d) => d.date), playing: S.playing,
        ended: S.ended, speed: S.speed, events: ((S.body && S.body.events) || []).map((e) => e.id),
        people: S.days.map((d) => Number(d.totals.people) || 0), fixed: S.days.map((d) => Number(d.totals.fixed) || 0) }),
      stats: () => {
        const sm = S.fps.samples.slice().sort((a, b) => a - b);
        const avg = sm.length ? sm.reduce((a, b) => a + b, 0) / sm.length : 0;
        return { frames: S.fps.frames, avg_ms: Math.round(avg * 10) / 10, fps: avg ? Math.round(10000 / avg) / 10 : 0,
          p95_ms: sm.length ? Math.round(sm[Math.floor(sm.length * 0.95)] * 10) / 10 : 0, worst_ms: Math.round(S.fps.worst * 10) / 10,
          heat: heat && heat.replay.cost ? heat.replay.cost() : null };
      },
    };
    active = handle;
    void load();
    return handle;
  }

  // ---------------------------------------------------------------- открыть над картой (кнопка, Ctrl+K, ?replay=)
  let active = null;
  const openNow = () => (active && !active.closing() ? active : null);   // закрывающаяся (200 мс) — уже не открытая
  function open(options) {
    const o = options || {};
    if (active && active.closing()) active.destroy();   // открыли снова во время закрытия — дозакрыть сразу, открыть новую
    if (active) { if (o.days) active.setPeriod(o.days); return active; }
    const m = o.map || globalMap();
    const container = o.container || (m && m.getContainer && m.getContainer()) || document.body;
    let root = container.querySelector(":scope > .rp-host");
    if (!root) {
      root = document.createElement("div");
      root.className = "rp-host";
      container.append(root);
    }
    return mount(root, Object.assign({}, o, { map: m, onClose: () => { root.remove(); if (typeof o.onClose === "function") o.onClose(); } }));
  }

  // Кнопка «Хроника» в колонке кнопок карты (место — схема R11; R01 вызывает attach один раз) и ?replay=7|30 в адресе.
  function attach(options) {
    const o = options || {};
    const lang = () => (window.Birge && window.Birge.i18n ? window.Birge.i18n.lang() : document.documentElement.lang === "kk" ? "kk" : "ru");
    const text = (key) => {
      const g = window.Birge && window.Birge.i18n;
      if (g && typeof g.has === "function" && g.has(key, lang())) return g.t(key, {}, lang());
      return (DICT[lang()] || DICT.ru)[key] || DICT.ru[key];
    };
    let button = null;
    const tools = typeof o.tools === "string" ? document.querySelector(o.tools) : o.tools;
    if (tools && !tools.querySelector(".rp-open")) {
      button = document.createElement("button");
      button.type = "button";
      button.className = "icon-btn rp-open bk-glass--control";
      button.innerHTML = svg("replay", 22);
      const label = () => { button.setAttribute("aria-label", text("replay.open") + " · " + text("replay.open_hint")); button.title = text("replay.open") + " · " + text("replay.open_hint"); };
      label();
      button.addEventListener("click", () => {
        if (openNow()) { active.close(); return; }
        open({ map: o.map, heat: o.heat || (window.CivicShell && window.CivicShell.heat), days: 7 });
      });
      document.addEventListener("birge:lang", label);
      window.addEventListener("birge:lang", label);
      tools.append(button);
    }
    const p = new URLSearchParams(location.search);
    const days = Number(p.get("replay"));
    if (days === 7 || days === 30) {
      // Ждём, пока тепловая карта загрузит «сегодня» (иначе хронике нечего возвращать после закрытия)
      let tries = 0;
      const wait = () => {
        const heat = heatHandle(o);
        const ready = heat && heat.state && heat.state().status === "ready";
        if (ready) open({ map: o.map, heat, days, autoplay: p.get("autoplay") !== "0" });
        else if (++tries < 100) setTimeout(wait, 200);
      };
      wait();
    }
    document.addEventListener("birge:replay-open", (ev) => open(Object.assign({ map: o.map, heat: o.heat }, (ev && ev.detail) || {})));
    return { button };
  }

  window.BirgeReplay = { mount, open, attach, version: VERSION, messages: DICT, get active() { return openNow(); }, _buildDays: buildDays };
})();
