/* R07 · Тепловая карта объектов (раунд 14, Birge).
 *
 * Подключение (R01, см. research/round-14-results/R07/INTEGRATION.txt):
 *   <link rel="stylesheet" href="/civic/heat/heat.css">  <script src="/civic/heat/heat.js"></script>
 *   const heat = window.CivicHeat.mount({ root, map, role: "akimat" | "resident" });
 *   heat.destroy();
 *
 * Что рисуется на карте MapLibre:
 *   объект (остановка) — кружок-ореол, растущий с весом, и значок «иконка + число»;
 *   участок улицы      — линия ТОЧНО по форме ребра OSM (геометрия приходит с сервера, здесь не меняется);
 *   двор / квартал     — заливка с контуром; «примерное место» — пунктирный контур;
 *   мелкий масштаб     — районы (заливка + значок с числом).
 * Цвет никогда не один: на каждом значке число людей, в карточке — слово уровня.
 * Все данные — GET /api/civic/v2/heat (ui/civic_heat). Тексты жалоб и точки жителей сюда не приходят.
 */
(function () {
  "use strict";

  const VERSION = "r07-round14-1";
  const NBSP = " ";
  const ANIM_MS = 800;           // перетекание цвета при новой жалобе (UX_BRIEF: ~0.8 с)
  const BADGE_W = 64, BADGE_H = 40;
  const DISTRICT_ZOOM = 12;      // меньше — районы (CONTRACT §6); сервер присылает то же значение в meta

  // ---------- Тексты ru / kk ----------
  // Ключи heat.* переданы R11 (INTEGRATION.txt, блок I18N_KEYS). Если общий Birge.i18n уже подключён
  // и знает ключ — берём его перевод, иначе — этот запасной словарь. Казахский проверяет владелец.
  const DICT = {
    ru: {
      "heat.title": "Карта жалоб",
      "heat.subtitle": "Где жители сообщают о проблемах",
      "heat.top_line": "Больше всего жалоб: {target} · {people}",
      "heat.demo_note": "Демо-данные: жалобы придуманы, улицы и остановки настоящие (OpenStreetMap).",
      "heat.demo_tag": "Демо",
      "heat.filters": "Фильтры",
      "heat.category_all": "Все категории",
      "heat.period": "Период",
      "heat.days": { one: "{count} день", few: "{count} дня", many: "{count} дней" },
      "heat.district": "Район",
      "heat.district_all": "Все районы",
      "heat.reset": "Сбросить",
      "heat.legend": "Сколько человек сообщили",
      "heat.legend_hint": "Свежие жалобы ярче: за 2 недели жалоба «остывает» вдвое.",
      "heat.fixed": "исправлено",
      "heat.hot_title": "Горячие места",
      "heat.people_short": { one: "{count} чел.", few: "{count} чел.", many: "{count} чел." },
      "heat.reported": { one: "Сообщил {count} человек", few: "Сообщили {count} человека", many: "Сообщили {count} человек" },
      "heat.reported_fixed": { one: "Сообщал {count} человек", few: "Сообщали {count} человека", many: "Сообщали {count} человек" },
      "heat.for_days": { one: "за {count} день", few: "за {count} дня", many: "за {count} дней" },
      "heat.level_word.1": "Немного жалоб", "heat.level_word.2": "Заметно", "heat.level_word.3": "Много жалоб", "heat.level_word.4": "Очень много жалоб",
      "heat.fixed_word": "Исправлено",
      "heat.fixed_until": "На карте зелёным до {date}",
      "heat.chart": "Жалобы по дням",
      "heat.chart_from": "14 дн. назад",
      "heat.chart_to": "сегодня",
      "heat.topics": "О чём сообщают",
      "heat.status": "Статус",
      "heat.status.new": "Новое", "heat.status.accepted": "Принято", "heat.status.in_progress": "В работе", "heat.status.fixed": "Исправлено",
      "heat.kind.object": "Объект", "heat.kind.segment": "Участок улицы", "heat.kind.area": "Двор или квартал", "heat.kind.district": "Район",
      "heat.approximate": "Примерное место: точный объект не выбран, показана область.",
      "heat.take": "Взять в работу",
      "heat.mark_fixed": "Отметить исправленным",
      "heat.metoo": "Я тоже",
      "heat.metoo_done": { one: "Вы с нами. Сообщил {count} человек", few: "Вы с нами. Сообщили {count} человека", many: "Вы с нами. Сообщили {count} человек" },
      "heat.metoo_already": "Вы уже отметились",
      "heat.toast_taken": "Взято в работу",
      "heat.toast_fixed": "Отмечено как исправленное",
      "heat.toast_metoo": "Спасибо. Ваш голос учтён",
      "heat.toast_new": "Новая жалоба: {target}",
      "heat.action_failed": "Не получилось сохранить. Проверьте связь и попробуйте ещё раз",
      "heat.back": "Горячие места",
      "heat.close": "Закрыть",
      "heat.loading": "Загружаем карту жалоб…",
      "heat.empty_title": "Жалоб нет",
      "heat.empty_hint": "Здесь жалоб нет {period}. Измените период или район.",
      "heat.error_title": "Нет связи с сервером",
      "heat.error_hint": "Проверьте интернет и нажмите «Повторить».",
      "heat.not_ready": "Тепловая карта ещё не подключена к серверу",
      "heat.retry": "Повторить",
      "heat.zoom_hint": "Приблизьте карту, чтобы увидеть улицы, дворы и остановки",
      "heat.badge_label": "{target}: {reported}",
      "heat.open_on_map": "Показать на карте",
      "heat.district_targets": { one: "{count} место с жалобами", few: "{count} места с жалобами", many: "{count} мест с жалобами" },
      "heat.kind.bus_stop": "Остановка", "heat.kind.playground": "Детская площадка", "heat.kind.pitch": "Спортплощадка",
      "heat.kind.park": "Парк", "heat.kind.garden": "Сквер", "heat.kind.waste_disposal": "Контейнерная площадка",
      "heat.kind.recycling": "Приём вторсырья", "heat.kind.street_lamp": "Фонарь", "heat.kind.school": "Школа",
      "heat.kind.kindergarten": "Детский сад", "heat.kind.yard": "Двор",
      "heat.role.akimat": "Акимат", "heat.role.resident": "Житель",
    },
    kk: {
      "heat.title": "Шағымдар картасы",
      "heat.subtitle": "Тұрғындар қай жерде мәселе туралы хабарлайды",
      "heat.top_line": "Ең көп шағым: {target} · {people}",
      "heat.demo_note": "Демо-деректер: шағымдар ойдан жасалған, көшелер мен аялдамалар нақты (OpenStreetMap).",
      "heat.demo_tag": "Демо",
      "heat.filters": "Сүзгілер",
      "heat.category_all": "Барлық санат",
      "heat.period": "Кезең",
      "heat.days": { other: "{count} күн" },
      "heat.district": "Аудан",
      "heat.district_all": "Барлық аудан",
      "heat.reset": "Тазарту",
      "heat.legend": "Қанша адам хабарлады",
      "heat.legend_hint": "Жаңа шағымдар ашығырақ: 2 аптада шағымның салмағы екі есе азаяды.",
      "heat.fixed": "түзетілді",
      "heat.hot_title": "Шағымы көп орындар",
      "heat.people_short": { other: "{count} адам" },
      "heat.reported": { other: "{count} адам хабарлады" },
      "heat.reported_fixed": { other: "{count} адам хабарлаған" },
      "heat.for_days": { other: "соңғы {count} күнде" },
      "heat.level_word.1": "Шағым аз", "heat.level_word.2": "Шағым бар", "heat.level_word.3": "Шағым көп", "heat.level_word.4": "Шағым өте көп",
      "heat.fixed_word": "Түзетілді",
      "heat.fixed_until": "Картада жасыл түспен көрсетіледі (соңғы күні: {date})",
      "heat.chart": "Күндер бойынша шағымдар",
      "heat.chart_from": "14 күн бұрын",
      "heat.chart_to": "бүгін",
      "heat.topics": "Не туралы хабарлайды",
      "heat.status": "Мәртебесі",
      "heat.status.new": "Жаңа", "heat.status.accepted": "Қабылданды", "heat.status.in_progress": "Орындалуда", "heat.status.fixed": "Түзетілді",
      "heat.kind.object": "Нысан", "heat.kind.segment": "Көше бөлігі", "heat.kind.area": "Аула немесе орам", "heat.kind.district": "Аудан",
      "heat.approximate": "Шамамен көрсетілген орын: нақты нысан таңдалмаған, аумақ көрсетілген.",
      "heat.take": "Жұмысқа алу",
      "heat.mark_fixed": "Түзетілді деп белгілеу",
      "heat.metoo": "Мен де",
      "heat.metoo_done": { other: "Сіз бізбен біргесіз. {count} адам хабарлады" },
      "heat.metoo_already": "Сіз белгі қойдыңыз",
      "heat.toast_taken": "Жұмысқа алынды",
      "heat.toast_fixed": "Түзетілді деп белгіленді",
      "heat.toast_metoo": "Рақмет. Даусыңыз есептелді",
      "heat.toast_new": "Жаңа шағым: {target}",
      "heat.action_failed": "Сақталмады. Байланысты тексеріп, қайталап көріңіз",
      "heat.back": "Шағымы көп орындар",
      "heat.close": "Жабу",
      "heat.loading": "Шағымдар картасы жүктеліп жатыр…",
      "heat.empty_title": "Шағым жоқ",
      "heat.empty_hint": "Бұл жерде {period} шағым түспеген. Кезеңді немесе ауданды өзгертіңіз.",
      "heat.error_title": "Сервермен байланыс жоқ",
      "heat.error_hint": "Интернетті тексеріп, «Қайталау» түймесін басыңыз.",
      "heat.not_ready": "Шағымдар картасы серверге әлі қосылмаған",
      "heat.retry": "Қайталау",
      "heat.zoom_hint": "Көшелерді, аулалар мен аялдамаларды көру үшін картаны жақындатыңыз",
      "heat.badge_label": "{target}: {reported}",
      "heat.open_on_map": "Картадан көрсету",
      "heat.district_targets": { other: "{count} орында шағым бар" },
      "heat.kind.bus_stop": "Аялдама", "heat.kind.playground": "Балалар алаңы", "heat.kind.pitch": "Спорт алаңы",
      "heat.kind.park": "Саябақ", "heat.kind.garden": "Гүлзар", "heat.kind.waste_disposal": "Қоқыс алаңы",
      "heat.kind.recycling": "Қайта өңдеу пункті", "heat.kind.street_lamp": "Көше шамы", "heat.kind.school": "Мектеп",
      "heat.kind.kindergarten": "Балабақша", "heat.kind.yard": "Аула",
      "heat.role.akimat": "Әкімдік", "heat.role.resident": "Тұрғын",
    },
  };

  const MONTHS = {
    ru: ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
    kk: ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"],
  };

  // Иконки 24×24 (те же рисунки, что в ui-kit R11). Ключ — поле icon из categories_v2.json.
  const ICONS = {
    road: '<path d="M8 3 4 21M16 3l4 18"/><path d="M12 4v2.5M12 10.5v3M12 17.5V20"/>',
    snowflake: '<path d="M12 2v20M3.3 7l17.4 10M3.3 17 20.7 7"/><path d="m9.5 3.5 2.5 2 2.5-2M9.5 20.5l2.5-2 2.5 2"/>',
    walk: '<circle cx="13.5" cy="4" r="2"/><path d="m9 21 3-7 3 3v4M12 14l1-5.5M13 8.5l-4 1.5-1.5 4M13 8.5l2.5 3 3 1"/>',
    bus: '<rect x="4" y="3" width="16" height="15" rx="3"/><path d="M4 11h16M7 18v2.5M17 18v2.5M9 6.5h6"/>',
    bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.1V16h5v-.1c0-.8.4-1.6 1.1-2.1A6 6 0 0 0 12 3z"/>',
    trees: '<path d="M8 21v-4M8 3 3.5 11h2.5L3 15.5h10L10 11h2.5z"/><path d="M17 21v-6"/><circle cx="17" cy="11" r="4"/>',
    trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13M10 11v6M14 11v6"/>',
    droplet: '<path d="M12 3s6 6.6 6 11a6 6 0 0 1-12 0c0-4.4 6-11 6-11z"/>',
    wind: '<path d="M3 8h10a3 3 0 1 0-3-3M3 12h15a3 3 0 1 1-3 3M3 16h7"/>',
    shield: '<path d="M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6z"/><path d="m9 12 2 2 4-4"/>',
    parking: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M10 17V7h3a3 3 0 0 1 0 6h-3"/>',
    dots: '<circle cx="5.5" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="18.5" cy="12" r="1.6" fill="currentColor"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7"/>',
    playground: '<path d="M3 21 7 4h10l4 17M10 4v9M14 4v9M9 13h6"/>',
    ball: '<circle cx="12" cy="12" r="9"/><path d="m12 7.5 3.8 2.8-1.5 4.4H9.7l-1.5-4.4zM12 3v4.5M15.8 10.3l4.6-1.6M14.3 14.7l2.8 3.6M9.7 14.7l-2.8 3.6M8.2 10.3 3.6 8.7"/>',
    back: '<path d="M15 5l-7 7 7 7"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><circle cx="17" cy="9" r="2.5"/><path d="M16.5 14.1A5 5 0 0 1 21.5 19"/>',
    pin: '<path d="M12 21s-7-6.1-7-11.5a7 7 0 0 1 14 0C19 14.9 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    home: '<path d="M3 11.5 12 4l9 7.5M5.5 9.5V20h13V9.5M10 20v-5.5h4V20"/>',
    alert: '<path d="M10.3 4.2 2.6 17.5a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4M12 17h.01"/>',
    wifi_off: '<path d="M3 3l18 18M8.5 16.5a5 5 0 0 1 7 0M5 12.6a10 10 0 0 1 5.1-2.6M19 12.6a10 10 0 0 0-2.3-1.7M12 20h.01"/>',
  };
  const KIND_ICON = { object: "pin", segment: "road", area: "home", district: "pin" };
  // Подтип реального объекта OSM (ui/civic_heat/osm_objects.py) → иконка в карточке
  const SUBTYPE_ICON = { bus_stop: "bus", playground: "playground", pitch: "ball", park: "trees", garden: "trees",
    waste_disposal: "trash", recycling: "trash", street_lamp: "bulb", school: "home", kindergarten: "home", yard: "home" };

  function svgIcon(name, size) {
    const s = size || 20;
    return '<svg class="r07-ic" viewBox="0 0 24 24" width="' + s + '" height="' + s + '" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || ICONS.dots) + "</svg>";
  }

  // ---------- Мелкие помощники ----------
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
  function fmtDate(iso, lang) {
    const d = new Date(iso);
    if (isNaN(d)) return "";
    const t = new Date(d.getTime() + 5 * 3600 * 1000); // время Астаны, UTC+5
    return t.getUTCDate() + " " + MONTHS[lang][t.getUTCMonth()];
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }
  function hexToRgb(h) {
    const m = /^#?([0-9a-f]{6})$/i.exec(h || "");
    if (!m) return [200, 200, 200];
    const v = parseInt(m[1], 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }
  function mix(a, b, t) {
    const x = hexToRgb(a), y = hexToRgb(b);
    const c = x.map((v, i) => Math.round(v + (y[i] - v) * t));
    return "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
  }
  function keyOf(target) { return target.kind + ":" + target.id; }
  function deviceId() {
    // Тот же ключ, что у формы жалобы R09: один голос «Я тоже» с устройства.
    try {
      let id = localStorage.getItem("birge.device_id");
      if (!id) { id = "dev-" + Math.random().toString(36).slice(2) + Date.now().toString(36); localStorage.setItem("birge.device_id", id); }
      return id;
    } catch (e) { return "dev-anon"; }
  }
  function metooDone(targetKey) {
    try { return JSON.parse(localStorage.getItem("birge.heat.metoo") || "{}")[targetKey] === true; } catch (e) { return false; }
  }
  function rememberMetoo(targetKey) {
    try {
      const all = JSON.parse(localStorage.getItem("birge.heat.metoo") || "{}");
      all[targetKey] = true;
      localStorage.setItem("birge.heat.metoo", JSON.stringify(all));
    } catch (e) { /* приватный режим — не страшно */ }
  }

  // ---------- Модуль ----------
  function mount(options) {
    const opts = options || {};
    const root = opts.root;
    const map = opts.map || null;
    const apiBase = (opts.apiBase || "/api/civic/v2").replace(/\/$/, "");
    const fetchFn = opts.fetch || window.fetch.bind(window);
    if (!root) throw new Error("CivicHeat.mount: нужен root");

    const S = {
      role: opts.role === "resident" ? "resident" : "akimat",
      lang: opts.lang || (window.Birge && window.Birge.i18n ? window.Birge.i18n.lang() : document.documentElement.lang === "kk" ? "kk" : "ru"),
      filters: { category: null, days: 30, district: null },
      meta: null,
      data: null,
      mode: "targets",
      status: "loading",      // loading | ready | error | not_ready
      selected: null,         // ключ выбранной цели
      catsOpen: false,        // раскрыт ли список категорий
      prevColors: new Map(),  // ключ → цвет до обновления (для плавного перехода)
      markers: new Map(),     // ключ → { marker, el, item }
      anim: null,
      reqSeq: 0,
      destroyed: false,
    };
    const userMoved = { value: false };

    function t(key, params) {
      const p = params || {};
      const g = window.Birge && window.Birge.i18n;
      if (g && typeof g.has === "function" && g.has(key, S.lang)) return g.t(key, p, S.lang);
      let v = (DICT[S.lang] && DICT[S.lang][key]) || DICT.ru[key];
      if (v == null) { console.warn("[heat] нет текста", key); return key; }
      if (typeof v === "object") v = v[pluralForm(S.lang, Number(p.count))] || v.other || v.many || "";
      return v.replace(/\{(\w+)\}/g, (w, name) => (name in p ? (typeof p[name] === "number" ? fmtNum(p[name]) : p[name]) : w));
    }
    const label = (target) => (S.lang === "kk" ? target.label_kk || target.label_ru : target.label_ru) || "";
    const catName = (id) => {
      const c = S.meta && S.meta.categories.find((x) => x.id === id);
      return c ? (S.lang === "kk" ? c.kk : c.ru) : id;
    };
    const catIcon = (id) => {
      const c = S.meta && S.meta.categories.find((x) => x.id === id);
      return (c && c.icon) || "dots";
    };
    const levelWord = (it) => (it.level === "fixed" ? t("heat.fixed_word") : t("heat.level_word." + it.level));
    const legendLabel = (lv) => (S.lang === "kk" ? lv.kk : lv.ru);

    // ----- разметка панели -----
    root.classList.add("r07-root");
    root.dataset.role = S.role;
    root.innerHTML = '<div class="r07-panel" aria-live="polite"></div><div class="r07-sr" role="status" aria-live="polite"></div><div class="r07-toasts" role="status" aria-live="polite"></div>';
    const panel = root.querySelector(".r07-panel");
    const srBox = root.querySelector(".r07-sr");
    const toastBox = root.querySelector(".r07-toasts");

    function toast(text, kind) {
      const el = document.createElement("div");
      el.className = "r07-toast" + (kind === "error" ? " r07-toast--error" : "");
      el.textContent = text;
      toastBox.append(el);
      setTimeout(() => { el.classList.add("r07-toast--out"); setTimeout(() => el.remove(), 300); }, 3600);
    }

    // ----- загрузка -----
    async function getJson(path) {
      const res = await fetchFn(apiBase + path, { headers: { Accept: "application/json" } });
      let body = null;
      try { body = await res.json(); } catch (e) { body = null; }
      if (!res.ok) {
        const err = new Error((body && (body.message || (body.error && body.error.message))) || "HTTP " + res.status);
        err.status = res.status;
        err.body = body;
        throw err;
      }
      // Шлюз R01 может завернуть ответ в конверт {ok, data} (как в civic-v1) — принимаем оба вида.
      if (body && body.ok === true && body.data && !body.items && !body.categories) return body.data;
      return body;
    }

    function zoomNow() { return map ? map.getZoom() : 14; }
    function modeFor(z) { return z < ((S.meta && S.meta.district_zoom_max) || DISTRICT_ZOOM) ? "districts" : "targets"; }

    async function load(reason) {
      const seq = ++S.reqSeq;
      if (!S.data) { S.status = "loading"; render(); }
      try {
        if (!S.meta) S.meta = await getJson("/heat/meta");
        const q = new URLSearchParams();
        q.set("days", String(S.filters.days));
        if (S.filters.category) q.set("category", S.filters.category);
        if (S.filters.district) q.set("district", S.filters.district);
        q.set("zoom", String(Math.floor(zoomNow() * 10) / 10));
        const data = await getJson("/heat?" + q.toString());
        if (seq !== S.reqSeq || S.destroyed) return;   // пришёл устаревший ответ — пропускаем
        S.prevColors = new Map((S.data ? S.data.items : []).map((it) => [keyOf(it.target), it.color]));
        S.data = data;
        S.mode = data.mode;
        S.status = "ready";
        if (S.selected && !findItem(S.selected) && S.mode === "targets") S.selected = null;
        draw(reason === "event");
        render();
      } catch (err) {
        if (seq !== S.reqSeq || S.destroyed) return;
        S.status = err.status === 503 ? "not_ready" : "error";
        if (!S.data) render(); else toast(S.status === "not_ready" ? t("heat.not_ready") : t("heat.error_title"), "error");
      }
    }
    function findItem(key) { return S.data ? S.data.items.find((it) => keyOf(it.target) === key) : null; }

    // ----- слои карты -----
    const SRC = "r07-heat", SRC_PTS = "r07-heat-pts";
    let layersReady = false;

    function beforeLayerId() {
      if (opts.beforeId) return opts.beforeId;
      const layers = (map.getStyle() && map.getStyle().layers) || [];
      const sym = layers.find((l) => l.type === "symbol");
      return sym ? sym.id : undefined;
    }

    function ensureLayers() {
      if (!map || layersReady) return;
      // isStyleLoaded() ждёт ещё и все источники подложки; слои же можно добавлять, как только
      // разобран сам стиль. Пробуем; если стиль ещё не готов — повторим на событии load.
      try {
        addLayers();
        layersReady = true;
      } catch (err) {
        if (map.getSource(SRC)) removeLayers();
        if (!waitingLoad) { waitingLoad = true; map.once("load", () => { waitingLoad = false; draw(false); }); }
      }
    }
    let waitingLoad = false;
    let handlersBound = false;   // обработчики кликов по слоям вешаются один раз (слои пересоздаются при смене роли)

    function addLayers() {
      const soft = S.role === "resident" ? 0.75 : 1;   // жителю — та же карта, но мягче
      map.addSource(SRC, { type: "geojson", data: { type: "FeatureCollection", features: [] }, promoteId: "key" });
      map.addSource(SRC_PTS, { type: "geojson", data: { type: "FeatureCollection", features: [] }, promoteId: "key" });
      const color = ["coalesce", ["feature-state", "color"], ["get", "color"]];
      const before = beforeLayerId();
      const add = (layer) => map.addLayer(layer, before);
      // Районы (мелкий масштаб)
      add({ id: "r07-district-fill", type: "fill", source: SRC, filter: ["==", ["get", "kind"], "district"],
        paint: { "fill-color": color, "fill-opacity": ["case", ["==", ["get", "level"], 0], 0, 0.28 * soft] } });
      add({ id: "r07-district-line", type: "line", source: SRC, filter: ["==", ["get", "kind"], "district"],
        paint: { "line-color": color, "line-width": 2, "line-opacity": 0.8 } });
      // Дворы и кварталы
      // Мягкая ячейка: размытая кайма + полупрозрачная заливка, чтобы квартал не выглядел жёстким квадратом.
      const AREA = ["in", ["get", "kind"], ["literal", ["area", "object_area"]]];
      add({ id: "r07-area-glow", type: "line", source: SRC, filter: AREA,
        paint: { "line-color": color, "line-width": ["interpolate", ["linear"], ["zoom"], 12, 4, 17, 18], "line-blur": ["interpolate", ["linear"], ["zoom"], 12, 3, 17, 14], "line-opacity": 0.45 * soft } });
      add({ id: "r07-area-fill", type: "fill", source: SRC, filter: AREA,
        paint: { "fill-color": color, "fill-opacity": ["case", ["get", "fixed"], 0.2, 0.34 * soft] } });
      add({ id: "r07-area-line", type: "line", source: SRC, filter: ["all", AREA, ["!", ["get", "approx"]]],
        paint: { "line-color": color, "line-width": 1.5, "line-opacity": 0.9 } });
      add({ id: "r07-area-approx", type: "line", source: SRC, filter: ["all", AREA, ["get", "approx"]],
        paint: { "line-color": color, "line-width": 2, "line-dasharray": [2, 1.5] } });
      // Выделение выбранной цели: двор / площадка — тонкий тёмный контур поверх заливки
      add({ id: "r07-sel-outline", type: "line", source: SRC, filter: ["==", ["get", "key"], ""],
        paint: { "line-color": "#152c26", "line-width": 3 } });
      // участок улицы — тёмная подложка под цветной линией
      add({ id: "r07-sel-line", type: "line", source: SRC, filter: ["==", ["get", "key"], ""],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#152c26", "line-width": ["interpolate", ["linear"], ["zoom"], 11, ["+", 7, ["*", ["get", "w"], 0.25]], 17, ["+", 14, ["*", ["get", "w"], 1.1]]] } });
      // Участки улиц: белая подложка + цветная линия, толщина растёт с весом. Форма — из OSM как есть.
      add({ id: "r07-seg-casing", type: "line", source: SRC, filter: ["==", ["get", "kind"], "segment"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#ffffff", "line-width": ["interpolate", ["linear"], ["zoom"], 11, ["+", 4, ["*", ["get", "w"], 0.25 * soft]], 17, ["+", 9, ["*", ["get", "w"], 1.1 * soft]]] } });
      add({ id: "r07-seg", type: "line", source: SRC, filter: ["==", ["get", "kind"], "segment"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": color, "line-width": ["interpolate", ["linear"], ["zoom"], 11, ["+", 2, ["*", ["get", "w"], 0.2 * soft]], 17, ["+", 5, ["*", ["get", "w"], 0.9 * soft]]] } });
      // Объекты: ореол растёт с весом; на среднем масштабе — точка (значок появится ближе)
      add({ id: "r07-obj-halo", type: "circle", source: SRC_PTS, minzoom: 12,
        paint: { "circle-color": color, "circle-opacity": 0.32 * soft, "circle-blur": 0.45,
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, ["+", 8, ["*", ["get", "w"], 1.2 * soft]], 17, ["+", 20, ["*", ["get", "w"], 4 * soft]]] } });
      add({ id: "r07-obj-dot", type: "circle", source: SRC_PTS, minzoom: 12,
        paint: { "circle-color": color, "circle-radius": 6, "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });

      if (handlersBound) return;
      handlersBound = true;
      const clickable = ["r07-seg", "r07-area-fill", "r07-obj-dot", "r07-district-fill"];
      clickable.forEach((id) => {
        map.on("click", id, onFeatureClick);
        map.on("mouseenter", id, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", id, () => { map.getCanvas().style.cursor = ""; });
      });
    }

    function onFeatureClick(e) {
      const f = e.features && e.features[0];
      if (!f) return;
      const key = f.properties.key;
      if (f.properties.kind === "district") {
        // По району: приблизить к нему (это действие пользователя, не самопроизвольный прыжок).
        const it = findItem(key);
        if (it && it.anchor) map.easeTo({ center: it.anchor, zoom: 13, duration: 700 });
        return;
      }
      select(key, false);
    }

    function featureCollections() {
      const feats = [], pts = [];
      (S.data ? S.data.items : []).forEach((it) => {
        const key = keyOf(it.target);
        const w = Math.min(Number(it.weight) || 0, 12);
        const props = { key, kind: it.target.kind, level: it.level === "fixed" ? 5 : it.level, color: it.color || "#999999",
          w: it.state === "fixed" ? 1 : w, fixed: it.state === "fixed", approx: !!it.approximate };
        if (it.target.kind === "object") {
          // Ореол и точка — в центре объекта; если объект в OSM — многоугольник (площадка), рисуем и его контур.
          const point = it.geometry.type === "Point" ? it.geometry : (it.anchor ? { type: "Point", coordinates: it.anchor } : null);
          if (point) pts.push({ type: "Feature", properties: props, geometry: point });
          if (it.geometry.type !== "Point") feats.push({ type: "Feature", properties: Object.assign({}, props, { kind: "object_area" }), geometry: it.geometry });
        } else feats.push({ type: "Feature", properties: props, geometry: it.geometry });
      });
      return [{ type: "FeatureCollection", features: feats }, { type: "FeatureCollection", features: pts }];
    }

    function draw(animate) {
      if (map) {
        ensureLayers();
        if (layersReady) {
          const [fc, pc] = featureCollections();
          map.getSource(SRC).setData(fc);
          map.getSource(SRC_PTS).setData(pc);
          updateSelectionLayer();
          if (animate) animateColors();
        }
      }
      drawBadges();
    }

    // Плавное перетекание цвета целей, у которых сменился уровень (feature-state, ~0.8 с).
    function animateColors() {
      if (!map || !S.data) return;
      const changes = [];
      S.data.items.forEach((it) => {
        const key = keyOf(it.target);
        const before = S.prevColors.get(key);
        const src = it.target.kind === "object" ? SRC_PTS : SRC;
        if (it.color && before !== it.color) changes.push({ key, src, from: before || "#ffffff", to: it.color });
      });
      if (!changes.length) return;
      if (S.anim) cancelAnimationFrame(S.anim);
      const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const started = performance.now();
      const step = (now) => {
        const k = reduce ? 1 : Math.min(1, (now - started) / ANIM_MS);
        const eased = 1 - Math.pow(1 - k, 3);
        changes.forEach((c) => map.setFeatureState({ source: c.src, id: c.key }, { color: mix(c.from, c.to, eased) }));
        if (k < 1) S.anim = requestAnimationFrame(step);
        else { changes.forEach((c) => map.removeFeatureState({ source: c.src, id: c.key }, "color")); S.anim = null; }
      };
      S.anim = requestAnimationFrame(step);
    }

    function updateSelectionLayer() {
      if (!map || !layersReady) return;
      const key = S.selected || "";
      map.setFilter("r07-sel-line", ["all", ["==", ["get", "key"], key], ["==", ["get", "kind"], "segment"]]);
      map.setFilter("r07-sel-outline", ["all", ["==", ["get", "key"], key], ["in", ["get", "kind"], ["literal", ["area", "object_area"]]]]);
    }

    // ----- значки с числом (DOM-маркеры: работают без шрифтов карты и доступны с клавиатуры) -----
    function drawBadges() {
      if (!map || !window.maplibregl) return;
      const items = S.data ? S.data.items : [];
      const keep = new Set();
      items.forEach((it) => {
        if (!it.anchor || (it.target.kind === "district" && !it.count)) return;
        const key = keyOf(it.target);
        keep.add(key);
        let m = S.markers.get(key);
        if (!m) {
          const el = document.createElement("button");
          el.type = "button";
          el.className = "r07-badge";
          el.addEventListener("click", (ev) => { ev.stopPropagation(); onBadgeClick(key); });
          const marker = new window.maplibregl.Marker({ element: el, anchor: "center" }).setLngLat(it.anchor).addTo(map);
          m = { marker, el, item: it };
          S.markers.set(key, m);
        }
        m.item = it;
        m.marker.setLngLat(it.anchor);
        fillBadge(m.el, it);
      });
      for (const [key, m] of S.markers) {
        if (!keep.has(key)) { m.marker.remove(); S.markers.delete(key); }
      }
      declutter();
    }

    function fillBadge(el, it) {
      const fixed = it.state === "fixed";
      const district = it.target.kind === "district";
      const icon = fixed ? "check" : district ? "pin" : catIcon(Object.keys(it.by_category || {})[0] || "other");
      el.dataset.level = fixed ? "fixed" : String(it.level);
      el.dataset.kind = it.target.kind;
      el.classList.toggle("r07-badge--selected", S.selected === keyOf(it.target));
      const reported = t(fixed ? "heat.reported_fixed" : "heat.reported", { count: it.count });
      el.setAttribute("aria-label", t("heat.badge_label", { target: label(it.target), reported }) + (fixed ? ". " + t("heat.fixed_word") : ""));
      el.title = label(it.target);
      el.innerHTML = '<span class="r07-badge__dot" style="--r07-c:' + esc(it.color || "#999") + '">' + svgIcon(icon, 18) + "</span>" +
        '<span class="r07-badge__count">' + (district ? esc(label(it.target)) + " · " : "") + fmtNum(it.count) + "</span>";
    }

    // Значки не налезают друг на друга: сначала самые горячие, остальные прячутся до приближения.
    function declutter() {
      if (!map) return;
      const z = map.getZoom();
      const placed = [];
      const list = [...S.markers.values()].sort((a, b) => (b.item.weight || 0) - (a.item.weight || 0) || (b.item.count || 0) - (a.item.count || 0));
      list.forEach((m) => {
        const it = m.item;
        // Объекты со значком — с 15-го масштаба; на 12–15 их видно точкой и ореолом (CONTRACT §6).
        let visible = !(it.target.kind === "object" && z < 15 && it.level !== 4 && keyOf(it.target) !== S.selected);
        if (visible) {
          const p = map.project(it.anchor);
          const box = [p.x - BADGE_W / 2, p.y - BADGE_H / 2, p.x + BADGE_W / 2, p.y + BADGE_H / 2];
          const hit = placed.some((b) => !(box[2] < b[0] || b[2] < box[0] || box[3] < b[1] || b[3] < box[1]));
          if (hit && keyOf(it.target) !== S.selected) visible = false;
          else placed.push(box);
        }
        m.el.hidden = !visible;
        m.el.tabIndex = visible ? 0 : -1;
      });
    }

    function onBadgeClick(key) {
      const it = findItem(key);
      if (!it) return;
      if (it.target.kind === "district") {
        map.easeTo({ center: it.anchor, zoom: 13, duration: 700 });
        return;
      }
      select(key, false);
    }

    function select(key, moveMap) {
      S.selected = key;
      updateSelectionLayer();
      for (const [k, m] of S.markers) m.el.classList.toggle("r07-badge--selected", k === key);
      const it = findItem(key);
      if (it && moveMap && map && it.anchor) {
        // Плавно и только по просьбе пользователя (клик в списке). Наклон и поворот не трогаем.
        map.easeTo({ center: it.anchor, zoom: Math.max(map.getZoom(), it.target.kind === "object" ? 16 : 15), duration: 600 });
      }
      render();
      const heading = panel.querySelector(".r07-card__title");
      if (heading) heading.focus({ preventScroll: true });
      root.dispatchEvent(new CustomEvent("birge:heat-select", { bubbles: true, detail: { target: it ? it.target : null } }));
    }

    // Пульс-кольцо на цели при новой жалобе
    function pulse(key) {
      const it = findItem(key);
      if (!map || !it || !it.anchor || !window.maplibregl) return;
      const el = document.createElement("div");
      el.className = "r07-pulse";
      el.style.setProperty("--r07-c", it.color || "#E24B4A");
      const marker = new window.maplibregl.Marker({ element: el, anchor: "center" }).setLngLat(it.anchor).addTo(map);
      setTimeout(() => marker.remove(), 2600);
      srBox.textContent = t("heat.toast_new", { target: label(it.target) }) + ". " + t("heat.reported", { count: it.count });
    }

    // ----- действия -----
    async function post(path, body) {
      const res = await fetchFn(apiBase + path, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(body || {}) });
      if (!res.ok) throw new Error("HTTP " + res.status);
      try { return await res.json(); } catch (e) { return null; }
    }
    async function setStatus(it, status, btn) {
      btn.setAttribute("aria-busy", "true");
      btn.disabled = true;
      try {
        for (const id of it.open_ids || []) await post("/complaints/" + encodeURIComponent(id) + "/status", { status });
        toast(status === "fixed" ? t("heat.toast_fixed") : t("heat.toast_taken"));
        await load("event");
      } catch (e) {
        toast(t("heat.action_failed"), "error");
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
      }
    }
    async function metoo(it, btn) {
      const id = (it.open_ids || [])[0];
      if (!id) return;
      btn.setAttribute("aria-busy", "true");
      btn.disabled = true;
      try {
        await post("/complaints/" + encodeURIComponent(id) + "/metoo", { device_id: deviceId() });
        rememberMetoo(keyOf(it.target));
        toast(t("heat.toast_metoo"));
        await load("event");
        pulse(keyOf(it.target));
      } catch (e) {
        toast(t("heat.action_failed"), "error");
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
      }
    }

    // ----- панель -----
    function render() {
      if (S.destroyed) return;
      root.dataset.role = S.role;
      const parts = [];
      // Подзаголовок — главное за 10 секунд: самое горячее место (на телефоне видно даже в свёрнутой шторке).
      const top = S.data && S.data.items.find((x) => x.state === "active" && x.count > 0);
      const sub = top ? t("heat.top_line", { target: label(top.target), people: t("heat.people_short", { count: top.count }) }) : t("heat.subtitle");
      parts.push('<header class="r07-head"><div><h2 class="r07-h">' + esc(t("heat.title")) + '</h2><p class="r07-sub">' + esc(sub) + "</p></div></header>");
      const cardItem = S.selected && findItem(S.selected);
      // В карточке цели фильтры не нужны: так кнопки действий видны без прокрутки.
      if (!cardItem) {
        if ((S.data && S.data.demo) || (S.meta && S.meta.demo)) parts.push('<p class="r07-note r07-note--demo">' + esc(t("heat.demo_note")) + "</p>");
        parts.push(filtersHtml());
      }
      if (S.status === "loading" && !S.data) parts.push(skeletonHtml());
      else if ((S.status === "error" || S.status === "not_ready") && !S.data) parts.push(errorHtml());
      else {
        const it = S.selected && findItem(S.selected);
        parts.push(it ? cardHtml(it) : listHtml());
      }
      parts.push(legendHtml());
      panel.innerHTML = parts.join("");
      bindPanel();
    }

    function filtersHtml() {
      // Категории спрятаны за одной кнопкой: 12 чипов сразу заняли бы пол-экрана и вытеснили список.
      const cats = (S.meta ? S.meta.categories : []).map((c) =>
        '<button type="button" class="r07-chip" data-cat="' + esc(c.id) + '" aria-pressed="' + (S.filters.category === c.id) + '">' +
        svgIcon(c.icon, 18) + "<span>" + esc(S.lang === "kk" ? c.kk : c.ru) + "</span></button>").join("");
      const all = '<button type="button" class="r07-chip" data-cat="" aria-pressed="' + (!S.filters.category) + '"><span>' + esc(t("heat.category_all")) + "</span></button>";
      const current = S.filters.category
        ? svgIcon(catIcon(S.filters.category), 20) + "<span>" + esc(catName(S.filters.category)) + "</span>"
        : "<span>" + esc(t("heat.category_all")) + "</span>";
      const periods = ((S.meta && S.meta.periods) || [7, 30, 90]).map((d) =>
        '<button type="button" data-days="' + d + '" aria-pressed="' + (S.filters.days === d) + '">' + esc(t("heat.days", { count: d })) + "</button>").join("");
      const districts = ((S.meta && S.meta.districts) || []).slice().sort((a, b) => (a.ru > b.ru ? 1 : -1)).map((d) =>
        '<option value="' + esc(d.id) + '"' + (S.filters.district === d.id ? " selected" : "") + ">" + esc(S.lang === "kk" ? d.kk : d.ru) + "</option>").join("");
      const dirty = S.filters.category || S.filters.district || S.filters.days !== ((S.meta && S.meta.default_days) || 30);
      return '<section class="r07-filters" aria-label="' + esc(t("heat.filters")) + '">' +
        '<div class="r07-row"><button type="button" class="r07-btn r07-cat-toggle' + (S.filters.category ? " r07-cat-toggle--on" : "") + '" data-cats-toggle aria-expanded="' + S.catsOpen + '" aria-controls="r07-cats">' +
        current + svgIcon("back", 18).replace('class="r07-ic"', 'class="r07-ic r07-ic--down"') + "</button>" +
        '<label class="r07-select"><span class="r07-vh">' + esc(t("heat.district")) + '</span><select data-district aria-label="' + esc(t("heat.district")) + '"><option value="">' + esc(t("heat.district_all")) + "</option>" + districts + "</select></label></div>" +
        '<div class="r07-chips" id="r07-cats" role="group" aria-label="' + esc(t("heat.category_all")) + '"' + (S.catsOpen ? "" : " hidden") + ">" + all + cats + "</div>" +
        '<div class="r07-row"><div class="r07-seg" role="group" aria-label="' + esc(t("heat.period")) + '">' + periods + "</div>" +
        (dirty ? '<button type="button" class="r07-btn r07-btn--ghost" data-reset>' + esc(t("heat.reset")) + "</button>" : "") + "</div></section>";
    }

    function legendHtml() {
      const lg = (S.data && S.data.legend) || (S.meta && S.meta.legend);
      if (!lg) return "";
      const rows = lg.levels.filter((lv) => lv.level > 0).map((lv) =>
        '<li><i class="r07-sw" style="background:' + esc(lv.color) + '"></i>' + esc(legendLabel(lv)) + "</li>").join("") +
        '<li><i class="r07-sw" style="background:' + esc(lg.fixed.color) + '"></i>' + esc(S.lang === "kk" ? lg.fixed.kk : lg.fixed.ru) + "</li>";
      const zoomHint = S.mode === "districts" ? '<p class="r07-legend__hint">' + esc(t("heat.zoom_hint")) + "</p>" : "";
      return '<section class="r07-legend" aria-label="' + esc(t("heat.legend")) + '"><h3 class="r07-legend__title">' + esc(t("heat.legend")) + "</h3><ul>" + rows + '</ul><p class="r07-legend__hint">' + esc(t("heat.legend_hint")) + "</p>" + zoomHint + "</section>";
    }

    function skeletonHtml() {
      return '<div class="r07-skeleton" aria-busy="true" aria-label="' + esc(t("heat.loading")) + '"><i></i><i></i><i></i><i></i></div>';
    }
    function errorHtml() {
      const notReady = S.status === "not_ready";
      return '<div class="r07-error" role="alert">' + svgIcon(notReady ? "alert" : "wifi_off", 40) + '<p class="r07-error__title">' +
        esc(notReady ? t("heat.not_ready") : t("heat.error_title")) + "</p>" + (notReady ? "" : '<p class="r07-error__hint">' + esc(t("heat.error_hint")) + "</p>") +
        '<button type="button" class="r07-btn" data-retry>' + esc(t("heat.retry")) + "</button></div>";
    }

    function listHtml() {
      const items = (S.data ? S.data.items : []).filter((it) => it.state === "active" && it.count > 0);
      if (!items.length) {
        return '<div class="r07-empty">' + svgIcon("check", 40) + '<p class="r07-empty__title">' + esc(t("heat.empty_title")) + '</p><p class="r07-empty__hint">' +
          esc(t("heat.empty_hint", { period: t("heat.for_days", { count: S.filters.days }) })) + "</p>" +
          (S.filters.category || S.filters.district ? '<button type="button" class="r07-btn" data-reset>' + esc(t("heat.reset")) + "</button>" : "") + "</div>";
      }
      const rows = items.slice(0, 10).map((it, i) => {
        const top = Object.keys(it.by_category || {})[0];
        const meta = it.target.kind === "district"
          ? t("heat.district_targets", { count: it.targets || 0 })
          : (top ? catName(top) + " · " : "") + t("heat.people_short", { count: it.count });
        return '<li><button type="button" class="r07-item" data-key="' + esc(keyOf(it.target)) + '">' +
          '<span class="r07-item__rank">' + (i + 1) + "</span>" +
          '<span class="r07-mini" data-level="' + esc(it.level) + '" style="--r07-c:' + esc(it.color) + '">' + fmtNum(it.count) + "</span>" +
          '<span class="r07-item__text"><span class="r07-item__title">' + esc(label(it.target)) + '</span><span class="r07-item__meta">' + esc(meta) + "</span></span>" +
          svgIcon("back", 18).replace('class="r07-ic"', 'class="r07-ic r07-ic--flip"') + "</button></li>";
      }).join("");
      return '<section class="r07-hot"><h3 class="r07-h3">' + esc(t("heat.hot_title")) + ' <span class="r07-muted">' + esc(t("heat.for_days", { count: S.filters.days })) + '</span></h3><ol class="r07-list">' + rows + "</ol></section>";
    }

    function cardHtml(it) {
      const fixed = it.state === "fixed";
      const key = keyOf(it.target);
      const maxDay = Math.max(1, ...(it.daily || [0]));
      const bars = (it.daily || []).map((n) => '<i style="height:' + Math.max(n ? 8 : 2, Math.round((n / maxDay) * 100)) + '%" title="' + n + '"></i>').join("");
      const topics = Object.entries(it.by_category || {}).map(([c, n]) =>
        "<li>" + svgIcon(catIcon(c), 20) + "<span>" + esc(catName(c)) + "</span><b>" + fmtNum(n) + "</b></li>").join("");
      let actions = "";
      if (!fixed && S.role === "akimat") {
        actions = (it.status !== "in_progress" ? '<button type="button" class="r07-btn r07-btn--primary" data-act="take">' + esc(t("heat.take")) + "</button>" : "") +
          '<button type="button" class="r07-btn' + (it.status === "in_progress" ? " r07-btn--primary" : "") + '" data-act="fixed">' + svgIcon("check", 20) + esc(t("heat.mark_fixed")) + "</button>";
      } else if (!fixed && S.role === "resident") {
        const done = metooDone(key);
        actions = done
          ? '<button type="button" class="r07-btn" disabled>' + svgIcon("check", 20) + esc(t("heat.metoo_already")) + "</button>"
          : '<button type="button" class="r07-btn r07-btn--primary r07-btn--lg" data-act="metoo">' + svgIcon("users", 22) + esc(t("heat.metoo")) + "</button>";
      }
      const levelBadge = '<span class="r07-level" data-level="' + esc(it.level) + '"><span class="r07-mini" data-level="' + esc(it.level) + '" style="--r07-c:' + esc(it.color) + '">' +
        (fixed ? svgIcon("check", 14) : fmtNum(it.count)) + "</span>" + esc(levelWord(it)) + "</span>";
      const statusPill = '<span class="r07-status" data-status="' + esc(it.status) + '">' + esc(t("heat.status." + it.status)) + "</span>";
      return '<article class="r07-card">' +
        '<div class="r07-card__nav"><button type="button" class="r07-btn r07-btn--ghost" data-back>' + svgIcon("back", 20) + esc(t("heat.back")) + "</button>" +
        '<button type="button" class="r07-icon-btn" data-back aria-label="' + esc(t("heat.close")) + '" title="' + esc(t("heat.close")) + '">' + svgIcon("close", 22) + "</button></div>" +
        '<p class="r07-eyebrow">' + svgIcon(SUBTYPE_ICON[it.target.subtype] || KIND_ICON[it.target.kind] || "pin", 16) +
          esc(t("heat.kind." + (it.target.subtype || it.target.kind))) + (it.demo ? ' <span class="r07-tag">' + esc(t("heat.demo_tag")) + "</span>" : "") + "</p>" +
        '<h3 class="r07-card__title" tabindex="-1">' + esc(label(it.target)) + "</h3>" +
        levelBadge +
        '<p class="r07-card__reported">' + esc(t(fixed ? "heat.reported_fixed" : "heat.reported", { count: it.count })) + " · " + esc(t("heat.for_days", { count: S.filters.days })) + "</p>" +
        (fixed && it.fixed_until ? '<p class="r07-note r07-note--ok">' + esc(t("heat.fixed_until", { date: fmtDate(it.fixed_until, S.lang) })) + "</p>" : "") +
        (it.approximate ? '<p class="r07-note r07-note--warn">' + esc(t("heat.approximate")) + "</p>" : "") +
        (!fixed ? '<div class="r07-chart" aria-label="' + esc(t("heat.chart")) + '"><h4 class="r07-h4">' + esc(t("heat.chart")) + '</h4><div class="r07-spark">' + bars +
          '</div><div class="r07-axis"><span>' + esc(t("heat.chart_from")) + "</span><span>" + esc(t("heat.chart_to")) + "</span></div></div>" : "") +
        (topics ? '<h4 class="r07-h4">' + esc(t("heat.topics")) + '</h4><ul class="r07-topics">' + topics + "</ul>" : "") +
        '<p class="r07-card__status">' + esc(t("heat.status")) + ": " + statusPill + "</p>" +
        (actions ? '<div class="r07-actions">' + actions + "</div>" : "") +
        "</article>";
    }

    function bindPanel() {
      panel.querySelectorAll("[data-cat]").forEach((b) => b.addEventListener("click", () => {
        S.filters.category = b.dataset.cat || null; S.selected = null; S.catsOpen = false; void load();
      }));
      panel.querySelectorAll("[data-cats-toggle]").forEach((b) => b.addEventListener("click", () => {
        S.catsOpen = !S.catsOpen; render();
        const first = panel.querySelector(S.catsOpen ? "#r07-cats .r07-chip" : "[data-cats-toggle]");
        if (first) first.focus();
      }));
      panel.querySelectorAll("[data-days]").forEach((b) => b.addEventListener("click", () => {
        S.filters.days = Number(b.dataset.days); void load();
      }));
      const sel = panel.querySelector("[data-district]");
      if (sel) sel.addEventListener("change", () => {
        S.filters.district = sel.value || null; S.selected = null; void load();
        const d = S.meta && S.meta.districts.find((x) => x.id === sel.value);
        if (d && map && d.bbox) map.fitBounds([[d.bbox[0], d.bbox[1]], [d.bbox[2], d.bbox[3]]], { padding: 40, duration: 700 });
      });
      panel.querySelectorAll("[data-reset]").forEach((b) => b.addEventListener("click", () => {
        S.filters = { category: null, days: (S.meta && S.meta.default_days) || 30, district: null }; S.selected = null; void load();
      }));
      panel.querySelectorAll("[data-retry]").forEach((b) => b.addEventListener("click", () => { S.meta = null; void load(); }));
      panel.querySelectorAll(".r07-item").forEach((b) => b.addEventListener("click", () => {
        const it = findItem(b.dataset.key);
        if (it && it.target.kind === "district") { map && map.easeTo({ center: it.anchor, zoom: 13, duration: 700 }); return; }
        select(b.dataset.key, true);
      }));
      panel.querySelectorAll("[data-back]").forEach((b) => b.addEventListener("click", () => {
        S.selected = null; updateSelectionLayer(); render(); drawBadges();
      }));
      panel.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => {
        const it = findItem(S.selected);
        if (!it) return;
        if (b.dataset.act === "take") void setStatus(it, "in_progress", b);
        if (b.dataset.act === "fixed") void setStatus(it, "fixed", b);
        if (b.dataset.act === "metoo") void metoo(it, b);
      }));
    }

    // ----- события -----
    let moveTimer = null;
    function onMoveEnd() {
      declutter();
      const nextMode = modeFor(zoomNow());
      if (nextMode !== S.mode) {
        clearTimeout(moveTimer);
        moveTimer = setTimeout(() => void load(), 150);
      }
    }
    function onStyleData() {
      // После смены стиля карты (например, переход на офлайн-подложку) наши источники пропадают — добавляем заново.
      if (layersReady && !map.getSource(SRC)) layersReady = false;
      if (!layersReady && S.data) draw(false);
    }
    function onComplaintEvent(ev) {
      // R09 после create / metoo / status: window.dispatchEvent(new CustomEvent("birge:complaint", {detail:{type, target}}))
      const d = (ev && ev.detail) || {};
      void load("event").then(() => { if (d.target && d.target.id && d.type !== "status") pulse(keyOf(d.target)); });
    }
    function onLang(ev) {
      const next = ev && ev.detail && ev.detail.lang;
      if (next && next !== S.lang) { S.lang = next; render(); drawBadges(); }
    }
    function onKey(ev) {
      if (ev.key === "Escape" && S.selected) { S.selected = null; updateSelectionLayer(); render(); drawBadges(); }
    }
    if (map) {
      map.on("moveend", onMoveEnd);
      map.on("styledata", onStyleData);
      map.on("dragstart", () => { userMoved.value = true; });
    }
    window.addEventListener("birge:complaint", onComplaintEvent);
    window.addEventListener("birge:lang", onLang);
    document.addEventListener("keydown", onKey);

    render();
    void load();

    return {
      version: VERSION,
      refresh: () => load("event"),
      pulse: (target) => pulse(typeof target === "string" ? target : keyOf(target)),
      focusTarget: (kind, id) => select(kind + ":" + id, true),
      setRole: (role) => { S.role = role === "resident" ? "resident" : "akimat"; if (map && layersReady) { removeLayers(); } draw(false); render(); },
      setLang: (lang) => { S.lang = lang === "kk" ? "kk" : "ru"; render(); drawBadges(); },
      setFilters: (f) => { Object.assign(S.filters, f || {}); void load(); },
      state: () => ({ role: S.role, lang: S.lang, filters: { ...S.filters }, selected: S.selected, mode: S.mode, status: S.status, items: S.data ? S.data.items.length : 0 }),
      destroy,
    };

    function removeLayers() {
      ["r07-district-fill", "r07-district-line", "r07-area-glow", "r07-area-fill", "r07-area-line", "r07-area-approx", "r07-sel-outline", "r07-sel-line", "r07-seg-casing", "r07-seg", "r07-obj-halo", "r07-obj-dot"]
        .forEach((id) => { try { if (map.getLayer(id)) map.removeLayer(id); } catch (e) { /* стиль сменился */ } });
      [SRC, SRC_PTS].forEach((id) => { try { if (map.getSource(id)) map.removeSource(id); } catch (e) { /* стиль сменился */ } });
      layersReady = false;
    }
    function destroy() {
      S.destroyed = true;
      if (S.anim) cancelAnimationFrame(S.anim);
      window.removeEventListener("birge:complaint", onComplaintEvent);
      window.removeEventListener("birge:lang", onLang);
      document.removeEventListener("keydown", onKey);
      for (const m of S.markers.values()) m.marker.remove();
      S.markers.clear();
      if (map) {
        map.off("moveend", onMoveEnd);
        map.off("styledata", onStyleData);
        try { removeLayers(); } catch (e) { /* стиль уже сменился */ }
      }
      root.innerHTML = "";
      root.classList.remove("r07-root");
    }
  }

  // messages — запасной словарь ru/kk (R11 переносит ключи heat.* в общие ru.json / kk.json).
  window.CivicHeat = { mount, version: VERSION, schema: "civic-v2", messages: DICT };
})();
