/*
 * Birge · «Разбор обращений» — ИИ-разбор пачки обращений (R04, П3, сцена 0 демо).
 *
 *   <link rel="stylesheet" href="/civic/intake/intake.css">
 *   <script src="/civic/i18n/i18n.js"></script>          (словари R11; без них — свой запасной словарь ниже)
 *   <script src="/civic/intake/intake.js"></script>
 *   BirgeIntake.mount(element, { api, apiBase, titleTag, openTarget, openSection }) -> { setLang, destroy }
 *
 * В оболочке R01: opts.api.v2(method, path, body) — клиент шлюза (CSRF сотрудника ставит сам), opts.openTarget(kind,
 * id) — «Показать на карте», opts.openSection("inbox", id) — «Обращения». Без оболочки — свой fetch на apiBase
 * (/api/civic/v2) с CivicShell.csrfToken(). Раздел регистрируется сам: BirgeShell.registerScreen({id: "intake"}).
 *
 * Данные (ui/civic_ml_api/intake.py; маршруты шлюза R01 — только сотрудник + CSRF):
 *   POST /intake/analyze {texts | sample: "night"} -> {batch_id, summary, tasks, services, method, demo}
 *   GET  /intake/sample                             -> {texts: [{id, text}], demo: true}
 *   POST /intake/commit {batch_id, task_ids?}       -> {created, existing, joined, skipped_no_address, records}
 *
 * Правила: числа итога — из summary (считает сервер), экран их не пересчитывает; П1 — без картинок и эмодзи, только
 * значки набора R11; у категории и служб — значок «ИИ» с подсказкой «Подсказка ИИ — проверьте»; срочные сверху;
 * у примера — метка «Пример». Esc сворачивает «Почему так»; Ctrl+Enter в поле — «Разобрать».
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var MAX_TEXTS = 500;
  var MAX_BYTES = 300 * 1024;
  var MAX_FILE = 2 * 1024 * 1024;          // файл больше — не читаем (300 КБ текста — предел разбора)
  var MIN_TEXT = 3;
  // Значок «ИИ» набора R11 (П3): i-ai и BirgeUI.aiTag() в ui-kit раунда 15+; в старой сборке ui-kit — i-sparkle.
  function aiIcon() {
    return root.BirgeUI && typeof root.BirgeUI.aiTag === "function" ? "ai" : "sparkle";
  }
  var scriptBase = ((doc.currentScript && doc.currentScript.src) || "").replace(/[^/]*$/, "");
  var ICONS = scriptBase + "../ui-kit/icons.svg";
  // Значки категорий — как в web/civic/ui-kit/categories_v2.json (R11).
  var CAT_ICON = {
    roads: "road", snow_ice: "snowflake", sidewalks: "walk", transport: "bus", lighting: "bulb", yards: "trees",
    waste: "trash", utilities: "droplet", smell_air: "wind", noise_safety: "shield", parking: "parking", other: "dots",
  };

  // Ключи, которых пока нет в словаре R11 (список для R11 — INTEGRATION R04 §9.5). Словарь главнее.
  var KEYS = {
    ru: {
      "intake.title": "Разбор обращений",
      "intake.ai_label": "ИИ-разбор",
      "common.ai.badge": "ИИ",
      "common.ai.hint": "Подсказка ИИ — проверьте",
      "intake.lead": "Вставьте обращения, пришедшие за ночь: одна строка — одно обращение. Birge разложит их по службам, склеит повторы, найдёт место на карте и поднимет срочные.",
      "intake.field": "Обращения — одна строка, одно обращение",
      "intake.placeholder": "На остановке Хан Шатыр сломан навес\nВо дворе ЖК Инжу Арена переполнены баки\nНа улице Сыганак открытый люк",
      "intake.count": { one: "{n} обращение", few: "{n} обращения", many: "{n} обращений" },
      "intake.size": "{kb} КБ из 300",
      "intake.limits": "До 500 обращений и 300 КБ за раз",
      "intake.file": "Файл .txt или .csv",
      "intake.sample": "Пример: обращения за ночь",
      "intake.sample_loading": "Загружаем пример…",
      "intake.analyze": "Разобрать",
      "intake.privacy": "Телефоны и ИИН закрываются до разбора. Тексты не уходят за пределы сервера Birge.",
      "intake.running": { one: "Разбираем {n} обращение…", few: "Разбираем {n} обращения…", many: "Разбираем {n} обращений…" },
      "intake.seconds": "{s} с",
      "intake.sum.texts": { one: "{n} обращение", few: "{n} обращения", many: "{n} обращений" },
      "intake.sum.tasks": { one: "{n} задача", few: "{n} задачи", many: "{n} задач" },
      "intake.sum.services": { one: "{n} служба", few: "{n} службы", many: "{n} служб" },
      "intake.sum.urgent": { one: "{n} срочная", few: "{n} срочные", many: "{n} срочных" },
      "intake.sum.merged": { one: "{n} повтор склеен", few: "{n} повтора склеено", many: "{n} повторов склеено" },
      "intake.sum.no_address": "без адреса: {n}",
      "intake.sum.existing": "к открытым обращениям: {n}",
      "intake.sum.pii": "личные данные закрыты: {n}",
      "intake.sum.time": "разобрано за {s} с",
      "intake.demo_note": "Пример: обращения придуманы, остановки, дворы и улицы — OpenStreetMap.",
      "intake.group.urgent": "Срочно",
      "intake.address_unknown": "Адрес уточнить",
      "intake.task.existing": "к {code}",
      "intake.task.services": { one: "{n} служба", few: "{n} службы", many: "{n} служб" },
      "intake.task.people": { one: "{n} обращение", few: "{n} обращения", many: "{n} обращений" },
      "intake.why": "Почему так",
      "intake.why.services": "Службы: {services}",
      "intake.why.place": "Место: {place}",
      "intake.why.repeats": "Повторов: {n}",
      "intake.why.repeats_reason": "одно место, одна категория, похожий текст",
      "intake.urgent": "Срочно",
      "intake.why.texts": "Обращения",
      "intake.why.more": { one: "и ещё {n} обращение", few: "и ещё {n} обращения", many: "и ещё {n} обращений" },
      "intake.why.single": "Одно обращение — повторов нет.",
      "intake.open_record": "Открыть {code}",
      "intake.create": "Создать задачи",
      "intake.create_none": "Нет задач с адресом",
      "intake.creating": "Создаём задачи…",
      "intake.created": { one: "Создана {n} задача в «Обращениях»", few: "Создано {n} задачи в «Обращениях»", many: "Создано {n} задач в «Обращениях»" },
      "intake.created_before": { one: "Эта задача уже создана", few: "Эти {n} задачи уже созданы", many: "Эти {n} задач уже созданы" },
      "intake.joined": { one: "{n} задача — к уже открытому обращению", few: "{n} задачи — к уже открытым обращениям", many: "{n} задач — к уже открытым обращениям" },
      "intake.skipped": { one: "{n} задача без адреса не создана — уточните место.", few: "{n} задачи без адреса не созданы — уточните место.", many: "{n} задач без адреса не создано — уточните место." },
      "intake.open_inbox": "Открыть «Обращения»",
      "intake.again": "Разобрать другие",
      "intake.method": "Как разбирали",
      "intake.method_note": "Числа итога считает код. ИИ подсказывает категорию и службы — сотрудник проверяет.",
      "intake.empty.title": "Вставьте обращения или откройте пример",
      "intake.error.too_big": "Слишком много за раз: не больше 500 обращений и 300 КБ",
      "intake.error.server_size": "Запрос слишком большой для сервера — разделите пачку на части.",
      "intake.error.file": "Файл не прочитался. Нужен текст .txt или .csv в кодировке UTF-8.",
      "intake.staff_only": "Разбор обращений — для сотрудников акимата",
      "intake.error.text": "Не удалось разобрать. Проверьте связь и повторите.",
      "intake.error.expired": "Разбор устарел (сервер перезапускался) — разберите ещё раз.",
      "intake.error.store": "Хранилище обращений не подключено — задачи не созданы.",
      "intake.error.commit": "Задачи не созданы. Повторите.",
      "intake.error.sample": "Пример не загрузился. Повторите.",
      "common.action.retry": "Повторить",
      "common.action.show_on_map": "Показать на карте",
      "common.tag.demo": "Пример",
      "common.tag.demo_hint": "Пример для показа, не настоящие данные",
      "common.state.network_title": "Нет связи с сервером",
      "common.state.network_text": "Проверьте интернет и повторите.",
      "joint.role.lead": "ведущая",
      "joint.role.partner": "участвует",
      "district.almaty": "Алматы", "district.baikonur": "Байконур", "district.esil": "Есиль", "district.nura": "Нура",
      "district.saraishyk": "Сарайшык", "district.saryarka": "Сарыарка",
    },
    kk: {
      "intake.title": "Өтініштерді талдау",
      "intake.ai_label": "ЖИ-талдау",
      "common.ai.badge": "ЖИ",
      "common.ai.hint": "Жасанды интеллект кеңесі — тексеріңіз",
      "intake.lead": "Түнде келген өтініштерді қойыңыз: бір жол — бір өтініш. Birge оларды қызметтерге бөледі, қайталанғандарын біріктіреді, картадан орнын табады және шұғылдарын жоғары шығарады.",
      "intake.field": "Өтініштер — бір жол, бір өтініш",
      "intake.placeholder": "Хан Шатыр аялдамасының күнқағары сынған\nІнжу Арена ауласында контейнерлер толып кетті\nСығанақ көшесінде люк ашық",
      "intake.count": "{n} өтініш",
      "intake.size": "300 КБ ішінен {kb} КБ",
      "intake.limits": "Бір ретте 500 өтінішке және 300 КБ-қа дейін",
      "intake.file": ".txt не .csv файлы",
      "intake.sample": "Үлгі: түнде түскен өтініштер",
      "intake.sample_loading": "Үлгі жүктеліп жатыр…",
      "intake.analyze": "Талдау",
      "intake.privacy": "Телефон мен ЖСН талдауға дейін жабылады. Мәтіндер Birge серверінен тыс жіберілмейді.",
      "intake.running": "{n} өтініш талданып жатыр…",
      "intake.seconds": "{s} с",
      "intake.sum.texts": "{n} өтініш",
      "intake.sum.tasks": "{n} тапсырма",
      "intake.sum.services": "{n} қызмет",
      "intake.sum.urgent": "{n} шұғыл",
      "intake.sum.merged": "{n} қайталау біріктірілді",
      "intake.sum.no_address": "мекенжайсыз: {n}",
      "intake.sum.existing": "ашық өтініштерге: {n}",
      "intake.sum.pii": "жеке деректер жабылды: {n}",
      "intake.sum.time": "{s} с ішінде талданды",
      "intake.demo_note": "Үлгі: өтініштер ойдан құрастырылған, аялдамалар, аулалар мен көшелер — OpenStreetMap.",
      "intake.group.urgent": "Шұғыл",
      "intake.address_unknown": "Мекенжайды нақтылау",
      "intake.task.existing": "{code} өтінішіне",
      "intake.task.services": "{n} қызмет",
      "intake.task.people": "{n} өтініш",
      "intake.why": "Неге солай",
      "intake.why.services": "Қызметтер: {services}",
      "intake.why.place": "Орны: {place}",
      "intake.why.repeats": "Қайталау: {n}",
      "intake.why.repeats_reason": "бір орын, бір санат, ұқсас мәтін",
      "intake.urgent": "Шұғыл",
      "intake.why.texts": "Өтініштер",
      "intake.why.more": "тағы {n} өтініш",
      "intake.why.single": "Бір өтініш — қайталау жоқ.",
      "intake.open_record": "{code} ашу",
      "intake.create": "Тапсырмаларды жасау",
      "intake.create_none": "Мекенжайы бар тапсырма жоқ",
      "intake.creating": "Тапсырмалар жасалып жатыр…",
      "intake.created": "«Өтініштер» бөлімінде {n} тапсырма жасалды",
      "intake.created_before": "Бұл {n} тапсырма бұрын жасалған",
      "intake.joined": "{n} тапсырма — ашық өтініштерге қосылды",
      "intake.skipped": "Мекенжайсыз {n} тапсырма жасалмады — орнын нақтылаңыз.",
      "intake.open_inbox": "«Өтініштер» бөлімін ашу",
      "intake.again": "Басқаларын талдау",
      "intake.method": "Қалай талданды",
      "intake.method_note": "Қорытынды сандарды код есептейді. ЖИ санат пен қызметті ұсынады — қызметкер тексереді.",
      "intake.empty.title": "Өтініштерді қойыңыз немесе үлгіні ашыңыз",
      "intake.error.too_big": "Бір ретте ең көбі — 500 өтініш және 300 КБ",
      "intake.error.server_size": "Сұрау сервер үшін тым үлкен — топтаманы бөліктерге бөліңіз.",
      "intake.error.file": "Файл оқылмады. UTF-8 кодтауындағы .txt не .csv мәтіні керек.",
      "intake.staff_only": "Өтініштерді талдау — әкімдік қызметкерлеріне арналған",
      "intake.error.text": "Талдау сәтсіз аяқталды. Байланысты тексеріп, қайталаңыз.",
      "intake.error.expired": "Талдау ескірді (сервер қайта іске қосылды) — қайта талдаңыз.",
      "intake.error.store": "Өтініштер қоймасы қосылмаған — тапсырмалар жасалмады.",
      "intake.error.commit": "Тапсырмалар жасалмады. Қайталаңыз.",
      "intake.error.sample": "Үлгі жүктелмеді. Қайталаңыз.",
      "common.action.retry": "Қайталау",
      "common.action.show_on_map": "Картадан көрсету",
      "common.tag.demo": "Үлгі",
      "common.tag.demo_hint": "Көрсетуге арналған үлгі, нақты дерек емес",
      "common.state.network_title": "Сервермен байланыс жоқ",
      "common.state.network_text": "Интернетті тексеріп, қайталап көріңіз.",
      "joint.role.lead": "жетекші",
      "joint.role.partner": "қатысады",
      "district.almaty": "Алматы", "district.baikonur": "Байқоңыр", "district.esil": "Есіл", "district.nura": "Нұра",
      "district.saraishyk": "Сарайшық", "district.saryarka": "Сарыарқа",
    },
  };

  // ------------------------------------------------------------------ текст
  function I() {
    return root.BirgeI18n || null;
  }
  function lang() {
    var l = I() && typeof I().getLang === "function" ? I().getLang() : "ru";
    return l === "kk" ? "kk" : "ru";
  }
  function num(n) {
    return I() && typeof I().formatNumber === "function" ? I().formatNumber(n) : String(n);
  }
  // «0,04 с» быстрее секунды, «2,3 с» — дольше; запятая — и в ru, и в kk.
  function seconds(ms) {
    var v = Math.max(0, ms) / 1000;
    return v.toFixed(v < 1 ? 2 : 1).replace(".", ",");
  }
  function plural(l, n) {
    if (I() && typeof I().plural === "function") return I().plural(l, n);
    if (l === "kk") return "other";
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return "one";
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "few";
    return "many";
  }
  // Свой (запасной) текст ключа; форма числа — для params.n.
  function ownTemplate(key, params) {
    var l = lang();
    var v = KEYS[l][key] != null ? KEYS[l][key] : KEYS.ru[key];
    if (v == null) return null;
    if (typeof v === "object") {
      var n = params && params.n != null ? Number(params.n) : 0;
      v = v[plural(l, n)] || v.other || v.many;
    }
    return String(v);
  }
  // Текст словаря — от другого смысла ключа (R10 B-134: словарь и экран разошлись): в нём остался «{…}» или пропали
  // данные, которые экран передаёт и показывает в своём тексте (службы, место, число).
  function lostData(text, own, params) {
    if (/\{\w+\}/.test(text)) return true;
    return Object.keys(params || {}).some(function (name) {
      var v = params[name];
      if (v == null || v === "" || own.indexOf("{" + name + "}") < 0) return false;
      return typeof v === "number" ? !/\d/.test(text) : text.indexOf(String(v)) < 0;
    });
  }
  function tr(key, params) {
    var i18n = I();
    var own = ownTemplate(key, params);
    if (i18n && typeof i18n.has === "function" && (i18n.has(key) || i18n.has(key, "ru"))) {
      var text = String(i18n.t(key, params));
      if (own == null || !lostData(text, own, params)) return text;      // словарь главнее
    }
    if (own == null) return key;
    return own.replace(/\{(\w+)\}/g, function (w, name) {
      if (!params || params[name] == null) return w;
      return typeof params[name] === "number" ? num(params[name]) : String(params[name]);
    });
  }
  function pick(pair) {
    if (!pair) return "";
    return (lang() === "kk" ? pair.kk : pair.ru) || pair.ru || "";
  }

  // ------------------------------------------------------------------ DOM
  var uid = 0;
  function h(tag, attrs, children) {
    var el = doc.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === "text") el.textContent = v;
      else if (k === "class") el.className = v;
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    (children || []).forEach(function (c) {
      if (c != null && c !== false) el.appendChild(typeof c === "string" ? doc.createTextNode(c) : c);
    });
    return el;
  }
  function icon(name, cls) {
    var NS = "http://www.w3.org/2000/svg";
    var svg = doc.createElementNS(NS, "svg");
    svg.setAttribute("class", "ic" + (cls ? " " + cls : ""));
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var use = doc.createElementNS(NS, "use");
    use.setAttribute("href", ICONS + "#i-" + name);
    svg.appendChild(use);
    return svg;
  }
  // Значок «ИИ»: монохромный, без свечения (П1); подсказка — title и текст для чтения с экрана.
  // Метка «ИИ» R11: серая плашка без свечения (П1), подсказка «Подсказка ИИ — проверьте» — title и текст для диктора.
  function aiTag(label) {
    if (root.BirgeUI && typeof root.BirgeUI.aiTag === "function") {
      try { return root.BirgeUI.aiTag(label ? { label: label } : undefined); } catch (e) { /* ниже — своя */ }
    }
    var hint = tr("common.ai.hint"), text = label || tr("common.ai.badge");
    return h("span", { class: "bk-ai bi-ai", title: hint }, [icon(aiIcon()), h("span", { class: "bk-ai__t", "aria-hidden": "true", text: text }),
      h("span", { class: "bk-sr-only", text: label ? label + ". " + hint : hint })]);
  }
  function toast(text, opts) {
    if (root.BirgeUI && typeof root.BirgeUI.toast === "function") root.BirgeUI.toast(text, opts || {});
  }
  function reducedMotion() {
    return !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }
  function utf8Bytes(text) {
    if (root.TextEncoder) return new root.TextEncoder().encode(text).length;
    return unescape(encodeURIComponent(text)).length; // старые браузеры
  }

  // ------------------------------------------------------------------ ввод: строки, файл .txt / .csv
  function lines(text) {
    return String(text || "").split(/\r?\n/).map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length >= MIN_TEXT; });
  }
  // CSV: столбец «text / текст / обращение / мәтін / өтініш», иначе единственный или самый длинный столбец строки.
  function csvRows(text) {
    var first = text.split(/\r?\n/, 1)[0] || "";
    var delim = [";", "\t", ","].reduce(function (best, d) {
      return first.split(d).length > first.split(best).length ? d : best;
    }, ",");
    var rows = [], row = [], cell = "", quoted = false;
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      if (quoted) {
        if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
        else if (ch === '"') quoted = false;
        else cell += ch === "\n" || ch === "\r" ? " " : ch;
      } else if (ch === '"') quoted = true;
      else if (ch === delim) { row.push(cell); cell = ""; }
      else if (ch === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
      else if (ch !== "\r") cell += ch;
    }
    if (cell || row.length) { row.push(cell); rows.push(row); }
    return rows;
  }
  function fromCsv(text) {
    var rows = csvRows(text);
    if (!rows.length) return "";
    var head = rows[0].map(function (c) { return c.trim().toLowerCase(); });
    var col = head.findIndex(function (c) { return /^(text|текст|обращение|жалоба|мәтін|өтініш|message)$/.test(c); });
    var body = col >= 0 ? rows.slice(1) : rows;
    return body.map(function (r) {
      if (col >= 0) return (r[col] || "").trim();
      if (r.length === 1) return r[0].trim();
      return r.reduce(function (a, b) { return b.trim().length > a.length ? b.trim() : a; }, "");
    }).filter(Boolean).join("\n");
  }

  // ------------------------------------------------------------------ экран
  function mount(rootEl, options) {
    var opts = { apiBase: "/api/civic/v2", titleTag: "h2" };
    Object.keys(options || {}).forEach(function (k) {
      if (options[k] !== undefined) opts[k] = options[k];
    });
    var id = "bi" + (++uid);
    var state = {
      view: "input",            // input | running | result
      text: "",
      sample: null,             // текст примера, как его вставили: не меняли — разбираем как пример (demo: true)
      sampleBusy: false,
      fieldError: null,
      error: null,              // {title, text, retry} — блок ошибки вместо экрана
      result: null,
      started: 0,
      runCount: 0,
      open: {},                 // раскрытые «Почему так»: id задачи -> true
      commit: null,             // {busy, done: ответ commit, error}
      records: {},              // id задачи -> {code, complaint_id} после «Создать задачи»
      request: 0,
      alive: true,
      lang: lang(),
      animate: false,
    };
    var timer = null;
    var box = h("section", { class: "bi", "aria-labelledby": id + "-title" });
    rootEl.appendChild(box);

    function call(method, path, body) {
      if (opts.api && typeof opts.api.v2 === "function") return opts.api.v2(method, path, body);
      var headers = { Accept: "application/json" };
      if (body !== undefined) headers["Content-Type"] = "application/json";
      var shell = root.CivicShell;
      var csrf = shell && typeof shell.csrfToken === "function" ? shell.csrfToken() : null;
      if (csrf) headers["X-CSRF-Token"] = csrf;
      return root.fetch(opts.apiBase + path, {
        method: method, headers: headers, credentials: "same-origin",
        body: body !== undefined ? JSON.stringify(body) : undefined,
      }).then(function (r) {
        return r.text().then(function (text) {
          var data = null;
          try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
          if (!r.ok) throw { status: r.status, error: (data && data.error) || "error", message: data && data.message };
          return data;
        });
      }, function () {
        throw { status: 0, error: "network" };
      });
    }
    // Ответ шлюза — сами данные или конверт {ok, data}.
    function unwrap(data) {
      return data && data.ok === true && data.data !== undefined ? data.data : data;
    }
    function errorInfo(err, fallbackKey) {
      var status = err && err.status;
      if (!status) return { title: tr("common.state.network_title"), text: tr("common.state.network_text") };
      if (status === 401 || status === 403) return { title: tr("intake.staff_only"), text: "", login: true };
      if (status === 413) return { title: tr("intake.error.server_size"), text: "" };
      if (status === 404) return { title: tr("intake.error.expired"), text: "", expired: true };
      if (status === 503) return { title: tr("intake.error.store"), text: "" };
      // 400: текст сервера — по-русски; на ҚАЗ и без текста (у оболочки тогда «request failed») — свой текст экрана.
      if (status === 400) {
        var msg = err.message && err.message !== "request failed" ? String(err.message) : "";
        return { title: msg && lang() === "ru" ? msg : tr(fallbackKey), text: "" };
      }
      return { title: tr(fallbackKey), text: "" };
    }

    // ---------------------------------------------------------------- действия
    function inputCheck() {
      var rows = lines(state.text);
      if (!rows.length) return { error: tr("intake.empty.title"), rows: rows };
      if (rows.length > MAX_TEXTS || utf8Bytes(state.text) > MAX_BYTES) return { error: tr("intake.error.too_big"), rows: rows };
      return { error: null, rows: rows };
    }
    function run() {
      var check = inputCheck();
      if (check.error) {
        state.fieldError = check.error;
        render();
        var field = box.querySelector(".bi-text");
        if (field) field.focus();
        return;
      }
      // Пример, который не правили, разбираем как пример: ответ и созданные записи — demo: true («Пример»).
      var asSample = state.sample != null && state.text === state.sample;
      analyze(asSample ? { sample: "night" } : { texts: check.rows }, check.rows.length);
    }
    function analyze(body, count) {
      var req = ++state.request;
      state.view = "running";
      state.error = null;
      state.fieldError = null;
      state.runCount = count;
      state.started = Date.now();
      render();
      tick();
      call("POST", "/intake/analyze", body).then(function (data) {
        if (!state.alive || req !== state.request) return;
        stopTick();
        state.result = unwrap(data);
        state.open = {};
        state.commit = null;
        state.records = {};
        state.view = "result";
        state.animate = !reducedMotion();
        render();
        var sum = box.querySelector(".bi-sum__line");
        if (sum) sum.focus();
      }, function (err) {
        if (!state.alive || req !== state.request) return;
        stopTick();
        state.view = "input";
        var info = errorInfo(err, "intake.error.text");
        if (err && err.status === 400) state.fieldError = info.title;
        else state.error = info;
        render();
      });
    }
    function tick() {
      stopTick();
      timer = root.setInterval(function () {
        var el = box.querySelector(".bi-run__time");
        if (el) el.textContent = tr("intake.seconds", { s: seconds(Date.now() - state.started) });
      }, 100);
    }
    function stopTick() {
      if (timer) root.clearInterval(timer);
      timer = null;
    }
    function loadSample() {
      if (state.sampleBusy) return;
      state.sampleBusy = true;
      state.error = null;
      render();
      call("GET", "/intake/sample").then(function (data) {
        if (!state.alive) return;
        data = unwrap(data) || {};
        var text = (data.texts || []).map(function (t) { return String(t.text || "").replace(/\s*\n\s*/g, " "); }).join("\n");
        state.text = text;
        state.sample = text;
        state.sampleBusy = false;
        state.fieldError = null;
        render();
        var run = box.querySelector("[data-act=run]");
        if (run) run.focus();
      }, function (err) {
        if (!state.alive) return;
        state.sampleBusy = false;
        var info = errorInfo(err, "intake.error.sample");
        state.error = info.login ? info : { title: tr("intake.error.sample"), text: info.text, retry: loadSample };
        render();
      });
    }
    function readFile(file) {
      if (!file) return;
      if (file.size > MAX_FILE) {
        state.fieldError = tr("intake.error.too_big");
        render();
        return;
      }
      var reader = new root.FileReader();
      reader.onload = function () {
        if (!state.alive) return;
        var text = String(reader.result || "").replace(/^﻿/, "");
        if (/\.csv$/i.test(file.name) || /csv/.test(file.type || "")) text = fromCsv(text);
        if (/�/.test(text) || !text.trim()) {
          state.fieldError = tr("intake.error.file");
        } else {
          state.text = text.split(/\r?\n/).map(function (s) { return s.trim(); }).filter(Boolean).join("\n");
          state.sample = null;
          state.fieldError = null;
        }
        render();
      };
      reader.onerror = function () {
        state.fieldError = tr("intake.error.file");
        render();
      };
      reader.readAsText(file, "utf-8");
    }
    function commit() {
      var res = state.result;
      if (!res || (state.commit && state.commit.busy)) return;
      state.commit = { busy: true };
      render();
      call("POST", "/intake/commit", { batch_id: res.batch_id }).then(function (data) {
        if (!state.alive) return;
        data = unwrap(data) || {};
        state.commit = { busy: false, done: data };
        (data.records || []).forEach(function (r) {
          if (r.complaint_id) state.records[r.task_id] = { code: r.code, complaint_id: r.complaint_id };
        });
        render();
        var text = doneTitle(data);
        var joined = Number(data.joined_existing) || 0;
        if (joined && (Number(data.created) || Number(data.existing))) text += " · " + tr("intake.joined", { n: joined });
        toast(text, { type: "ok", action: { label: tr("intake.open_inbox"), onClick: function () { openInbox(); } } });
        var banner = box.querySelector(".bi-done");
        if (banner) banner.focus();
      }, function (err) {
        if (!state.alive) return;
        var info = errorInfo(err, "intake.error.commit");
        state.commit = { busy: false, error: info };
        render();
        toast(info.title, { type: "error" });
      });
    }
    // «Создано N задач в «Обращениях»»; ничего нового — «уже созданы» или «к открытым обращениям».
    function doneTitle(data) {
      var created = Number(data.created) || 0, existing = Number(data.existing) || 0, joined = Number(data.joined_existing) || 0;
      if (created) return tr("intake.created", { n: created });
      if (existing) return tr("intake.created_before", { n: existing });
      return tr("intake.joined", { n: joined });
    }
    function openInbox(complaintId) {
      if (typeof opts.openSection === "function") opts.openSection("inbox", complaintId || undefined);
      else root.location.hash = "#inbox" + (complaintId ? "/" + encodeURIComponent(complaintId) : "");
    }
    function showOnMap(task) {
      if (!task.target) return;
      if (typeof opts.openTarget === "function") opts.openTarget(task.target.kind, task.target.id);
      else root.location.hash = "#target=" + encodeURIComponent(task.target.kind) + ":" + encodeURIComponent(task.target.id);
    }
    function again() {
      state.view = "input";
      state.result = null;
      state.commit = null;
      state.error = null;
      render();
      var field = box.querySelector(".bi-text");
      if (field) field.focus();
    }
    function toggle(taskId) {
      state.open[taskId] = !state.open[taskId];
      var row = box.querySelector('[data-task="' + taskId + '"]');
      if (!row) return render();
      var btn = row.querySelector(".bi-row");
      var why = row.querySelector(".bi-why");
      btn.setAttribute("aria-expanded", String(!!state.open[taskId]));
      why.hidden = !state.open[taskId];
      row.classList.toggle("is-open", !!state.open[taskId]);
    }

    // ---------------------------------------------------------------- отрисовка
    function head() {
      var demo = state.view === "result" && state.result && state.result.demo;
      return h("div", { class: "bi-head" }, [
        h(opts.titleTag === "h1" ? "h1" : "h2", { class: "bi-title", id: id + "-title", text: tr("intake.title") }),
        aiTag(tr("intake.ai_label")),
        demo ? h("span", { class: "bk-tag bk-tag--demo", title: tr("common.tag.demo_hint"), text: tr("common.tag.demo") }) : null,
      ]);
    }
    function errorBlock(info) {
      return h("div", { class: "bk-error bi-error", role: "alert" }, [
        h("p", { class: "bk-error__title", text: info.title }),
        info.text ? h("p", { class: "bk-error__text", text: info.text }) : null,
        info.retry ? h("button", { type: "button", class: "bk-btn", onclick: info.retry, text: tr("common.action.retry") }) : null,
      ]);
    }
    function inputView() {
      var rows = lines(state.text);
      var bytes = utf8Bytes(state.text);
      var over = rows.length > MAX_TEXTS || bytes > MAX_BYTES;
      var fieldId = id + "-text", hintId = id + "-hint", errId = id + "-err";
      var area = h("textarea", {
        id: fieldId, class: "bi-text", rows: "10", spellcheck: "false", placeholder: tr("intake.placeholder"),
        "aria-describedby": hintId + (state.fieldError ? " " + errId : ""), "aria-invalid": state.fieldError ? "true" : null,
      });
      area.value = state.text;
      area.addEventListener("input", function () {
        state.text = area.value;
        if (state.fieldError) {
          state.fieldError = null;
          var err = box.querySelector(".bk-field__error");
          if (err) err.remove();
          area.removeAttribute("aria-invalid");
          area.parentNode.classList.remove("bk-field--error");
        }
        updateMeter();
      });
      area.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(); }
      });
      var fileInput = h("input", { type: "file", class: "bk-sr-only", accept: ".txt,.csv,text/plain,text/csv", tabindex: "-1" });
      fileInput.addEventListener("change", function () { readFile(fileInput.files && fileInput.files[0]); fileInput.value = ""; });
      var fileBtn = h("button", { type: "button", class: "bk-btn bk-btn--ghost bk-btn--lg", onclick: function () { fileInput.click(); } },
        [icon("plus"), tr("intake.file")]);
      return [
        h("p", { class: "bi-lead", text: tr("intake.lead") }),
        state.error ? errorBlock(state.error) : null,
        h("div", { class: "bk-field bi-field" + (state.fieldError ? " bk-field--error" : "") }, [
          h("label", { class: "bk-field__label", for: fieldId, text: tr("intake.field") }),
          area,
          h("p", { class: "bi-meter" + (over ? " is-over" : ""), id: hintId, "aria-live": "polite" }, [
            h("span", { class: "bi-meter__count", text: tr("intake.count", { n: rows.length }) }),
            h("span", { class: "bi-meter__size", text: tr("intake.size", { kb: Math.ceil(bytes / 1024) }) }),
            h("span", { class: "bi-meter__limits", text: tr("intake.limits") }),
          ]),
          state.fieldError ? h("p", { class: "bk-field__error", id: errId, role: "alert", text: state.fieldError }) : null,
        ]),
        h("div", { class: "bi-actions" }, [
          h("button", { type: "button", class: "bk-btn bk-btn--primary bk-btn--lg", "data-act": "run", onclick: run }, [icon(aiIcon()), tr("intake.analyze")]),
          h("button", { type: "button", class: "bk-btn bk-btn--lg", "data-act": "sample", onclick: loadSample,
            "aria-busy": state.sampleBusy ? "true" : null, disabled: state.sampleBusy },
          [tr(state.sampleBusy ? "intake.sample_loading" : "intake.sample")]),
          fileBtn, fileInput,
        ]),
        h("p", { class: "bi-note" }, [icon("shield"), tr("intake.privacy")]),
      ];
    }
    function updateMeter() {
      var rows = lines(state.text), bytes = utf8Bytes(state.text);
      var meter = box.querySelector(".bi-meter");
      if (!meter) return;
      meter.classList.toggle("is-over", rows.length > MAX_TEXTS || bytes > MAX_BYTES);
      meter.querySelector(".bi-meter__count").textContent = tr("intake.count", { n: rows.length });
      meter.querySelector(".bi-meter__size").textContent = tr("intake.size", { kb: Math.ceil(bytes / 1024) });
    }
    function runningView() {
      return [
        h("div", { class: "bi-run", role: "status", "aria-live": "polite" }, [
          h("p", { class: "bi-run__count" }, [icon(aiIcon()), tr("intake.running", { n: state.runCount })]),
          h("p", { class: "bi-run__time", "aria-hidden": "true", text: tr("intake.seconds", { s: seconds(0) }) }),
          h("div", { class: "bi-run__bar", "aria-hidden": "true" }, [h("span")]),
        ]),
        skeleton(),
      ];
    }
    function skeleton() {
      var rows = [];
      for (var i = 0; i < 6; i++) {
        rows.push(h("div", { class: "bk-lrow bk-lrow--skel", "aria-hidden": "true" }, [
          h("span", { class: "bk-skel bk-skel--circle bi-skel-ic" }),
          h("span", { class: "bk-lrow__main" }, [h("span", { class: "bk-skel bk-skel--line", style: "width:" + (40 + (i * 17) % 45) + "%" })]),
        ]));
      }
      return h("div", { class: "bi-list" }, rows);
    }
    // Часть итога «127 задач»: число жирным, слово — в форме для показанного числа (и в кадрах счётчика: «95 обращений»,
    // а не «95 обращение» от итоговых 301). data-value у числа — итог из summary (по нему сверяют проверки).
    function fillPart(chunk, key, value, total) {
      var phrase = tr("intake.sum." + key, { n: value });
      var shown = num(value);
      var at = phrase.indexOf(shown);
      chunk.textContent = "";
      if (at < 0) {
        chunk.appendChild(doc.createTextNode(phrase));
        return;
      }
      if (at > 0) chunk.appendChild(doc.createTextNode(phrase.slice(0, at)));
      chunk.appendChild(h("b", { class: "bi-num" + (key === "urgent" && total ? " is-urgent" : ""), "data-value": String(total), text: shown }));
      chunk.appendChild(doc.createTextNode(phrase.slice(at + shown.length)));
    }
    // Итог: «312 обращений → 41 задача · 9 служб · 6 срочных · 37 повторов склеено» — числа из summary.
    function summaryLine(s) {
      var parts = [
        ["texts", s.total], ["tasks", s.tasks], ["services", s.services], ["urgent", s.urgent], ["merged", s.merged],
      ];
      var full = parts.map(function (p) { return tr("intake.sum." + p[0], { n: p[1] }); });
      var visible = h("span", { class: "bi-sum__text", "aria-hidden": "true" });
      parts.forEach(function (p, i) {
        if (i === 1) visible.appendChild(h("span", { class: "bi-sum__arrow", text: " → " }));
        else if (i > 1) visible.appendChild(h("span", { class: "bi-sum__dot", text: " · " }));
        var chunk = h("span", { class: "bi-sum__part", "data-key": p[0], "data-value": String(p[1]) });
        fillPart(chunk, p[0], p[1], p[1]);
        visible.appendChild(chunk);
      });
      var spoken = full[0] + " → " + full.slice(1).join(" · ");
      return h("p", { class: "bi-sum__line", tabindex: "-1" }, [visible, h("span", { class: "bk-sr-only", text: spoken })]);
    }
    function countUp() {
      if (!state.animate) return;
      state.animate = false;
      var parts = box.querySelectorAll(".bi-sum__line .bi-sum__part");
      var start = null, DURATION = 700;
      function frame(ts) {
        if (!state.alive) return;
        if (start == null) start = ts;
        var k = Math.min(1, (ts - start) / DURATION);
        var ease = 1 - Math.pow(1 - k, 3);
        Array.prototype.forEach.call(parts, function (el) {
          var v = Number(el.getAttribute("data-value")) || 0;
          fillPart(el, el.getAttribute("data-key"), Math.round(v * ease), v);
        });
        if (k < 1) root.requestAnimationFrame(frame);
      }
      if (root.requestAnimationFrame) root.requestAnimationFrame(frame);
    }
    // Уровни плашки — как в «Обращениях» R09 (complaint-list.js): та же группа там и здесь одного цвета.
    function level(people) {
      return people >= 10 ? "4" : people >= 6 ? "3" : people >= 3 ? "2" : "1";
    }
    // «Запах газа — сообщить в 104» при названии «Запах газа» -> «сообщить в 104»; «Нет отопления» -> ничего.
    function urgentNote(task, title) {
      var why = (lang() === "kk" ? task.urgent_why_kk : task.urgent_why_ru) || "";
      var low = title.toLowerCase(), cut = why.indexOf(" — ");
      if (cut > 0 && low.indexOf(why.slice(0, cut).toLowerCase()) >= 0) return why.slice(cut + 3);
      return low.indexOf(why.toLowerCase()) >= 0 ? "" : why;
    }
    function serviceNames(task) {
      return (task.services || []).map(function (s) { return lang() === "kk" ? s.name_kk || s.name_ru : s.name_ru; });
    }
    function taskRow(task, inUrgent) {
      var open = !!state.open[task.id];
      var whyId = id + "-why-" + task.id;
      // Строка под названием — только то, чего нет в названии и в заголовке группы: почему срочно, службы (в группе
      // службы — только участвующие), район.
      var title = lang() === "kk" ? task.title_kk : task.title_ru;
      var meta = [];
      if (task.urgent) meta.push(urgentNote(task, title));
      var names = serviceNames(task);
      meta.push(inUrgent ? names.join(" + ") : names.slice(1).map(function (n) { return "+ " + n; }).join(" "));
      if (task.district && tr("district." + task.district) !== "district." + task.district) meta.push(tr("district." + task.district));
      var record = state.records[task.id];
      var btn = h("button", {
        type: "button", class: "bk-lrow bi-row", "aria-expanded": String(open), "aria-controls": whyId,
        onclick: function () { toggle(task.id); },
      }, [
        h("span", { class: "bi-row__ic" + (task.urgent ? " is-urgent" : "") }, [icon(task.urgent ? "alert" : (CAT_ICON[task.category] || "dots"))]),
        h("span", { class: "bk-lrow__main" }, [
          h("span", { class: "bk-lrow__title", text: title }),
          h("span", { class: "bk-lrow__meta" }, [
            task.target ? null : h("span", { class: "bi-noaddr", text: tr("intake.address_unknown") }),
            task.target || !meta.filter(Boolean).length ? null : " · ",
            meta.filter(Boolean).join(" · "),
          ]),
        ]),
        record ? h("span", { class: "bk-tag bi-code", text: record.code })
          : task.existing && task.target ? h("span", { class: "bk-tag bi-code", title: pick(task.why_parts && task.why_parts.existing),
            text: tr("intake.task.existing", { code: task.existing.code || "" }) }) : null,
        h("span", { class: "bk-lrow__cnt", "data-level": level(task.people), title: tr("intake.task.people", { n: task.people }) }, [
          num(task.people), h("span", { class: "bk-sr-only", text: " — " + tr("intake.task.people", { n: task.people }) }),
        ]),
        h("span", { class: "bi-row__chev", "aria-hidden": "true" }, [icon("chevron-down")]),
      ]);
      return h("div", { class: "bi-task" + (open ? " is-open" : "") + (task.urgent ? " is-urgent" : ""), "data-task": task.id, role: "listitem" }, [
        btn, whyPanel(task, whyId, open),
      ]);
    }
    // «Почему так» — строками словаря R11: «Службы: …» (с меткой «ИИ»: службы подсказала модель), «Место: …»,
    // «Повторов: N — одно место, одна категория, похожий текст», «Срочно: …», уже открытое обращение той же цели.
    function whyPanel(task, whyId, open) {
      var p = task.why_parts || {};
      var svc = (task.services || []).map(function (s) {
        var name = lang() === "kk" ? s.name_kk || s.name_ru : s.name_ru;
        return name + " — " + tr("joint.role." + (s.role === "partner" ? "partner" : "lead"));
      }).join("; ");
      var place = pick(p.place).replace(/\.$/, "");
      var lines = [
        h("p", { class: "bi-why__line" }, [h("span", { class: "bi-why__svc", text: tr("intake.why.services", { services: svc }) }),
          " ", aiTag(), p.services ? h("span", { class: "bi-why__note", text: " " + pick(p.services) }) : null]),
        h("p", { class: "bi-why__line", text: tr("intake.why.place", { place: place }) }),
        h("p", { class: "bi-why__line", text: task.people > 1
          ? tr("intake.why.repeats", { n: task.people - 1 }) + " — " + tr("intake.why.repeats_reason") + "."
          : tr("intake.why.single") }),
        task.urgent ? h("p", { class: "bi-why__line bi-why__urgent", text: tr("intake.urgent") + ": " + pick(p.urgent) }) : null,
        p.existing ? h("p", { class: "bi-why__line bi-why__existing", text: pick(p.existing) }) : null,
      ];
      var texts = h("ul", { class: "bi-why__texts", "aria-label": tr("intake.why.texts") },
        (task.texts || []).map(function (t) { return h("li", {}, [h("span", { class: "bi-why__id", text: t.id }), " ", t.text]); }));
      var rest = task.people - (task.texts || []).length;
      var record = state.records[task.id];
      return h("div", { class: "bi-why", id: whyId, hidden: !open }, [
        h("p", { class: "bi-why__title", text: tr("intake.why") }),
        h("div", { class: "bi-why__facts" }, lines),
        texts,
        rest > 0 ? h("p", { class: "bi-why__more", text: tr("intake.why.more", { n: rest }) }) : null,
        h("div", { class: "bi-why__acts" }, [
          task.target ? h("button", { type: "button", class: "bk-btn", onclick: function () { showOnMap(task); } },
            [icon("pin"), tr("common.action.show_on_map")]) : null,
          record ? h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: function () { openInbox(record.complaint_id); } },
            [tr("intake.open_record", { code: record.code })]) : null,
        ]),
      ]);
    }
    // Срочные — своей группой сверху; остальные — по ведущей службе (больше людей — выше).
    function groups(tasks) {
      var out = [];
      var urgent = tasks.filter(function (t) { return t.urgent; });
      if (urgent.length) out.push({ key: "urgent", title: tr("intake.group.urgent"), icon: "alert", tasks: urgent });
      var bySvc = {}, order = [];
      tasks.forEach(function (t) {
        if (t.urgent) return;
        var lead = (t.services || [])[0] || { id: "other", name_ru: "—", name_kk: "—" };
        if (!bySvc[lead.id]) { bySvc[lead.id] = { key: lead.id, title: lang() === "kk" ? lead.name_kk || lead.name_ru : lead.name_ru, tasks: [], people: 0 }; order.push(lead.id); }
        bySvc[lead.id].tasks.push(t);
        bySvc[lead.id].people += t.people;
      });
      order.map(function (k) { return bySvc[k]; }).sort(function (a, b) { return b.people - a.people || b.tasks.length - a.tasks.length; })
        .forEach(function (g) { out.push(g); });
      return out;
    }
    function resultView() {
      var res = state.result || {};
      var s = res.summary || {};
      var tasks = res.tasks || [];
      var meta = [];
      if (s.no_address) meta.push(tr("intake.sum.no_address", { n: s.no_address }));
      if (s.to_existing) meta.push(tr("intake.sum.existing", { n: s.to_existing }));
      if (s.pii_masked) meta.push(tr("intake.sum.pii", { n: s.pii_masked }));
      meta.push(tr("intake.sum.time", { s: seconds(s.ms || 0) }));
      var c = state.commit || {};
      var ready = Number(s.ready != null ? s.ready : tasks.filter(function (t) { return t.target; }).length);
      var commitBtn = c.done ? h("button", { type: "button", class: "bk-btn bk-btn--primary bk-btn--lg", onclick: function () { openInbox(); } },
        [icon("list"), tr("intake.open_inbox")])
        : h("button", { type: "button", class: "bk-btn bk-btn--primary bk-btn--lg", "data-act": "commit", onclick: commit,
          disabled: c.busy || !ready, "aria-busy": c.busy ? "true" : null },
        [icon("check"), c.busy ? tr("intake.creating") : ready ? tr("intake.create") : tr("intake.create_none"),
          !c.busy && ready ? h("span", { class: "bk-btn__count", "aria-hidden": "true", text: num(ready) }) : null,
          !c.busy && ready ? h("span", { class: "bk-sr-only", text: " — " + tr("intake.sum.tasks", { n: ready }) }) : null]);
      var done = null;
      if (c.done) {
        var created = Number(c.done.created) || 0, existing = Number(c.done.existing) || 0;
        done = h("div", { class: "bk-banner bi-done", role: "status", tabindex: "-1" }, [
          h("p", { class: "bk-banner__title", text: doneTitle(c.done) }),
          c.done.joined_existing && (created || existing) ? h("p", { class: "bk-banner__note", text: tr("intake.joined", { n: c.done.joined_existing }) }) : null,
          c.done.skipped_no_address ? h("p", { class: "bk-banner__note", text: tr("intake.skipped", { n: c.done.skipped_no_address }) }) : null,
        ]);
      } else if (c.error) {
        done = errorBlock({ title: c.error.title, text: c.error.text, retry: c.error.expired ? again : commit });
      }
      // Группа — заголовок (служба или «Срочно») и свой список строк: читалка экрана называет группу у каждой строки.
      var list = h("div", { class: "bi-list" });
      groups(tasks).forEach(function (g, gi) {
        var hid = id + "-g" + gi;
        list.appendChild(h("div", { class: "bi-gsec" + (g.key === "urgent" ? " is-urgent" : ""), role: "group", "aria-labelledby": hid }, [
          h("div", { class: "bk-lgroup bi-group", id: hid }, [
            g.icon ? icon(g.icon) : null,
            h("span", { text: g.title }),
            h("span", { class: "bk-lgroup__count", text: num(g.tasks.length) }),
          ]),
          h("div", { class: "bi-rows", role: "list" }, g.tasks.map(function (t) { return taskRow(t, g.key === "urgent"); })),
        ]));
      });
      var method = res.method || {};
      var steps = (lang() === "kk" ? method.steps_kk : method.steps_ru) || [];
      return [
        h("div", { class: "bi-sum" }, [
          summaryLine(s),
          h("p", { class: "bi-sum__meta" }, [meta.join(" · ")]),
          res.demo ? h("p", { class: "bi-sum__demo", text: tr("intake.demo_note") }) : null,
          h("div", { class: "bi-actions" }, [
            commitBtn,
            h("button", { type: "button", class: "bk-btn bk-btn--lg", "data-act": "again", onclick: again }, [tr("intake.again")]),
          ]),
          done,
        ]),
        list,
        steps.length ? h("details", { class: "bi-method" }, [
          h("summary", {}, [aiTag(), " ", tr("intake.method")]),
          h("ol", {}, steps.map(function (st) { return h("li", { text: st }); })),
          h("p", { class: "bi-method__note", text: tr("intake.method_note") }),
        ]) : null,
      ];
    }
    function render() {
      state.lang = lang();
      var focusedAct = doc.activeElement && box.contains(doc.activeElement) && doc.activeElement.getAttribute("data-act");
      var body;
      if (state.view === "running") body = runningView();
      else if (state.view === "result") body = resultView();
      else body = inputView();
      box.setAttribute("data-view", state.view);
      box.replaceChildren.apply(box, [head()].concat(body.filter(Boolean)));
      if (state.view === "result") countUp();
      if (focusedAct) {
        var same = box.querySelector('[data-act="' + focusedAct + '"]');
        if (same && !same.disabled) same.focus();
      }
    }

    // Esc — свернуть последнее раскрытое «Почему так» (фокус — на его строку); остальное Esc — оболочке.
    function onKey(e) {
      if (e.key !== "Escape" || state.view !== "result") return;
      var openIds = Object.keys(state.open).filter(function (k) { return state.open[k]; });
      if (!openIds.length) return;
      var inside = doc.activeElement && doc.activeElement.closest ? doc.activeElement.closest(".bi-task") : null;
      var target = inside && box.contains(inside) ? inside.getAttribute("data-task") : openIds[openIds.length - 1];
      if (!state.open[target]) target = openIds[openIds.length - 1];
      e.preventDefault();
      e.stopPropagation();
      toggle(target);
      var row = box.querySelector('[data-task="' + target + '"] .bi-row');
      if (row) row.focus();
    }
    box.addEventListener("keydown", onKey);
    function relang() {
      if (state.lang !== lang()) render();
    }
    var offLang = I() && typeof I().onChange === "function" ? I().onChange(relang) : null;
    if (I() && I().ready && typeof I().ready.then === "function") I().ready.then(relang, relang);
    render();
    // #intake/sample (Ctrl+K «Сцена 0 · ИИ-разбор», R11 IA §11.1): пример уже в поле — остаётся «Разобрать».
    function setPath(path) {
      if (String(path || "").replace(/^\//, "") === "sample" && state.view === "input" && !state.sampleBusy) loadSample();
    }
    setPath(opts.path);

    return {
      setLang: relang,
      setPath: setPath,
      destroy: function () {
        state.alive = false;
        stopTick();
        if (offLang) offLang();
        box.removeEventListener("keydown", onKey);
        if (box.parentNode) box.parentNode.removeChild(box);
      },
    };
  }

  root.BirgeIntake = { mount: mount, version: "r04-intake-ui-3" };

  // Раздел оболочки R01 без правки оболочки: «Ещё → Разбор обращений» (вид «Акимат»), Ctrl+K находит по названию.
  function register() {
    var shell = root.BirgeShell;
    if (!shell || typeof shell.registerScreen !== "function") return false;
    shell.registerScreen({ id: "intake", mount: mount, modes: ["akimat"],
      title: { ru: KEYS.ru["intake.title"], kk: KEYS.kk["intake.title"] } });
    return true;
  }
  if (!register() && doc && doc.addEventListener) {
    doc.addEventListener("DOMContentLoaded", register, { once: true });
  }
})(typeof window !== "undefined" ? window : this);
