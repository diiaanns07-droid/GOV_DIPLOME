/*
 * Birge · «Ситуационный центр» акимата (R08, раунд 15). Большой экран: 1920×1080 и 1366×768 без прокрутки,
 * читается с трёх метров. Тёмная тема — только здесь (VISUAL_BRIEF §2 п. 8).
 *
 * Страница — /civic/board/ (index.html подключает этот файл с data-autostart). В оболочке R01 — пункт меню акимата
 * по схеме R11 (IA_ROUND15), ссылкой: BirgeShell.registerScreen({id: "board", href: "/civic/board/", modes: ["akimat"],
 * titleKey: "board.title"}). Своё окно: BirgeBoard.mount(элемент, {apiBase}).
 *
 * Данные — GET {apiBase}/akim/board?district=<id> (ui/civic_akim/situation.py). Только сотрудник: ответ 401 —
 * экран входа прямо здесь (тот же вход R02, что «Для сотрудников» на главной); запрос несёт X-CSRF-Token сотрудника. Все числа считает сервер — те же,
 * что в «Картине дня» и на карте R07; блоки соседей (службы и кризис R17, жители R16, встречи и прогноз R13) — как есть.
 *
 * Экран: шапка (знак, название, район, «Пример», «Нужно решение акима», ҚАЗ · РУС, часы Астаны) · полоса кризиса,
 * если он идёт · 4 числа с мини-графиками · слева карта районов и горячие места · справа пульс и лента блоков.
 * Лента: блоки сменяются каждые 15 с (rotate_s сервера); наведение или фокус — пауза; ← → — соседний блок; пробел —
 * пауза; полоса под названием блока показывает, сколько осталось. prefers-reduced-motion — без анимаций.
 * Адрес: ?district=nura · ?block=agencies (закрепить блок, для кадров и показа) · ?rotate=0 (не сменять) · ?lang=kk.
 * Данные обновляются тихо раз в минуту (refresh_s); нет связи — прежние числа остаются, в подвале «нет связи».
 *
 * Тексты — словарь R11 (BirgeI18n). Ключей board.* в словаре ещё нет — запасной текст BOARD_KEYS ниже (ru и kk);
 * когда R11 добавит ключ, берётся словарь. Список ключей — research/round-15-results/R08/INTEGRATION.txt.
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var script = doc.currentScript;
  var scriptBase = ((script && script.src) || "").replace(/[^/]*$/, "");
  var ICONS = scriptBase + "../ui-kit/icons.svg";
  var ASTANA_OFFSET_MS = 5 * 3600 * 1000; // весь Казахстан — UTC+5 с 1 марта 2024
  var DISTRICT_IDS = ["almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"];
  var STAGE_IDS = ["crisis", "agencies", "together", "meetings", "forecast"];
  var STAGE_ICON = { crisis: "alert", agencies: "building", together: "users", meetings: "calendar", forecast: "chart" };
  var TIMEOUT_MS = 15000;
  var RETRY_MS = 30000;
  var TICK_MS = 250;

  // ───────────── тексты ─────────────
  // Запасной словарь board.* (ru, kk). Формы ru: one / few / many — как в словаре R11.
  var BOARD_KEYS = {
    ru: {
      "board.title": "Ситуационный центр",
      "board.city": "Астана",
      "board.scope.city": "весь город",
      "board.scope.district": "район {name}",
      "board.live": "В эфире",
      "board.updated": "Данные на {time}",
      "board.refresh_note": "обновление раз в минуту",
      "board.stale": "Нет связи — показаны данные на {time}",
      "board.keys": "← → — блоки · пробел — пауза",
      "board.demo_note": "Пример: обращения и дела жителей придуманы, улицы и дворы — OpenStreetMap",
      "board.kpi.new": "Новые сегодня",
      "board.kpi.verified": "проверено жителями: {n}",
      "board.kpi.week": "за 7 дней: {n}",
      "board.map.title": "Карта районов",
      "board.map.hint": "За 7 дней · сколько человек сообщили о нерешённом",
      "board.people": { one: "{n} человек", few: "{n} человека", many: "{n} человек" },
      "board.pulse.title": "Пульс города",
      "board.pulse.title_district": "Пульс района",
      "board.pulse.calm": "Резких всплесков нет — день идёт спокойно",
      "board.crisis.label": "Кризис",
      "board.crisis.open": "Открыть кризисный штаб",
      "board.crisis.create": "Кризисный штаб",
      "board.crisis.short": "Штаб",
      "board.crisis.hours": { one: "идёт {n} час", few: "идёт {n} часа", many: "идёт {n} часов" },
      "board.crisis.tasks": "задачи служб: {done} из {total}",
      "board.crisis.update": "Жителям: «{text}»",
      "board.crisis.zone": "{name}: весь район",
      "board.crisis.services": "Службы в штабе",
      "board.crisis.tasks_label": "задач служб выполнено",
      "board.crisis.closed": "Закрыт: {title}",
      "board.decisions": { one: "Нужно решение акима: {n} вопрос", few: "Нужно решение акима: {n} вопроса", many: "Нужно решение акима: {n} вопросов" },
      "board.stage.crisis": "Кризисный штаб",
      "board.stage.agencies": "Ведомства вместе",
      "board.stage.together": "Жители вместе",
      "board.stage.meetings": "Встречи с жителями",
      "board.stage.forecast": "Прогноз на неделю",
      "board.stage.forecast_month": "Прогноз на месяц",
      "board.stage.pause": "Пауза",
      "board.stage.play": "Продолжить",
      "board.stage.show": "Показать блок: {name}",
      "board.agencies.joint": { one: "совместное обращение в работе", few: "совместных обращения в работе", many: "совместных обращений в работе" },
      "board.agencies.handoffs": { one: "передача между службами за неделю", few: "передачи между службами за неделю", many: "передач между службами за неделю" },
      "board.agencies.service": "Служба",
      "board.agencies.open": "Открыто",
      "board.agencies.overdue": "Просрочено",
      "board.agencies.median": "Ответ, дн.",
      "board.agencies.verified": "Проверено жителями",
      "board.agencies.lagging": "Отстают",
      "board.together.stat_done": { one: "дело жители сделали вместе", few: "дела жители сделали вместе", many: "дел жители сделали вместе" },
      "board.together.stat_people": { one: "сосед участвовал", few: "соседа участвовали", many: "соседей участвовали" },
      "board.together.stat_upcoming": { one: "дело впереди на неделе", few: "дела впереди на неделе", many: "дел впереди на неделе" },
      "board.together.stat_verified": { one: "исправление проверили жители", few: "исправления проверили жители", many: "исправлений проверили жители" },
      "board.together.deeds": { one: "{n} дело", few: "{n} дела", many: "{n} дел" },
      "board.together.neighbours": { one: "{n} сосед", few: "{n} соседа", many: "{n} соседей" },
      "board.together.coming": { one: "придёт {n} сосед", few: "придут {n} соседа", many: "придут {n} соседей" },
      "board.together.yard": "Двор недели",
      "board.together.done_with": { one: "Сделано вместе: {n} сосед", few: "Сделано вместе: {n} соседа", many: "Сделано вместе: {n} соседей" },
      "board.together.supported": "Поддержано акиматом",
      "board.together.on_review": "на проверке: {n}",
      "board.meetings.orders": "Поручения встреч",
      "board.meetings.stat_done": "поручений встреч выполнено",
      "board.meetings.stat_overdue": { one: "поручение просрочено", few: "поручения просрочены", many: "поручений просрочено" },
      "board.meetings.stat_week": "срок на этой неделе",
      "board.meetings.done": "выполнено {done} из {total}",
      "board.meetings.overdue": "просрочено: {n}",
      "board.meetings.due_week": "срок на этой неделе: {n}",
      "board.meetings.next": "Следующая встреча",
      "board.meetings.registered": { one: "придёт {n} человек", few: "придут {n} человека", many: "придут {n} человек" },
      "board.meetings.due_in": { one: "через {n} день", few: "через {n} дня", many: "через {n} дней" },
      "board.meetings.due_today": "срок сегодня",
      "board.meetings.due_late": { one: "просрочено на {n} день", few: "просрочено на {n} дня", many: "просрочено на {n} дней" },
      "board.meetings.host": "Аким района с жителями",
      "board.forecast.badge": "Прототип · синтетика",
      "board.forecast.hint": "Где вероятнее рост жалоб — не реальная оценка риска",
      "board.calm.title": "Сегодня спокойно",
      "board.calm.text": "Соседние блоки появятся, когда у служб, жителей и встреч будут данные",
      "board.login.title": "Ситуационный центр — для сотрудников акимата",
      "board.login.text": "Войдите как сотрудник — тем же логином, что «Для сотрудников» на главной.",
      "board.login.user": "Логин",
      "board.login.password": "Пароль",
      "board.login.submit": "Войти",
      "board.login.error": "Логин или пароль не подошли",
      "board.login.busy": "Входим…",
      "board.error.title": "Нет связи с сервером",
      "board.error.text": "Повторим сами через 30 секунд.",
      "board.to_map": "На карту",
      "board.to_day": "Картина дня",
      "board.back": "В Birge",
      "board.fullscreen": "На весь экран",
      "board.fullscreen_exit": "Выйти из полноэкранного режима",
      "board.login.staff": "Войдите как сотрудник",
      "board.agencies.no_answer": "Нет ответа в срок",
      "board.agencies.period": "за {n} дней",
      "board.weekday": ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"],
    },
    kk: {
      "board.title": "Жағдаяттық орталық",
      "board.city": "Астана",
      "board.scope.city": "бүкіл қала",
      "board.scope.district": "{name} ауданы",
      "board.live": "Тікелей",
      "board.updated": "{time} кезіндегі деректер",
      "board.refresh_note": "минут сайын жаңарады",
      "board.stale": "Байланыс жоқ — {time} кезіндегі деректер",
      "board.keys": "← → — блоктар · бос орын — кідірту",
      "board.demo_note": "Үлгі: өтініштер мен тұрғындар істері ойдан құрастырылған, көшелер мен аулалар — OpenStreetMap",
      "board.kpi.new": "Бүгін жаңа",
      "board.kpi.verified": "тұрғындар тексерді: {n}",
      "board.kpi.week": "7 күнде: {n}",
      "board.map.title": "Аудандар картасы",
      "board.map.hint": "Соңғы 7 күн · шешілмеген мәселе туралы хабарлаған адам саны",
      "board.people": "{n} адам",
      "board.pulse.title": "Қала пульсі",
      "board.pulse.title_district": "Аудан пульсі",
      "board.pulse.calm": "Күрт өсу жоқ — күн тыныш өтіп жатыр",
      "board.crisis.label": "Дағдарыс",
      "board.crisis.open": "Жедел штабты ашу",
      "board.crisis.create": "Жедел штаб",
      "board.crisis.short": "Штаб",
      "board.crisis.hours": "{n} сағат жүріп жатыр",
      "board.crisis.tasks": "қызмет тапсырмалары: {total} ішінен {done}",
      "board.crisis.update": "Тұрғындарға: «{text}»",
      "board.crisis.zone": "{name}: бүкіл аудан",
      "board.crisis.services": "Штабтағы қызметтер",
      "board.crisis.tasks_label": "қызмет тапсырмасы орындалды",
      "board.crisis.closed": "Жабылды: {title}",
      "board.decisions": "Әкімнің шешімі керек: {n} мәселе",
      "board.stage.crisis": "Жедел штаб",
      "board.stage.agencies": "Ведомстволар бірге",
      "board.stage.together": "Тұрғындар бірге",
      "board.stage.meetings": "Тұрғындармен кездесулер",
      "board.stage.forecast": "Апталық болжам",
      "board.stage.forecast_month": "Айлық болжам",
      "board.stage.pause": "Кідірту",
      "board.stage.play": "Жалғастыру",
      "board.stage.show": "Блокты көрсету: {name}",
      "board.agencies.joint": "жұмыстағы бірлескен өтініш",
      "board.agencies.handoffs": "аптада қызметтер арасында берілген өтініш",
      "board.agencies.service": "Қызмет",
      "board.agencies.open": "Ашық",
      "board.agencies.overdue": "Мерзімі өткен",
      "board.agencies.median": "Жауап, күн",
      "board.agencies.verified": "Тұрғындар тексерді",
      "board.agencies.lagging": "Артта қалып жатыр",
      "board.together.stat_done": "тұрғындар бірге атқарған іс",
      "board.together.stat_people": "көрші қатысты",
      "board.together.stat_upcoming": "алдағы аптадағы іс",
      "board.together.stat_verified": "түзетуді тұрғындар тексерді",
      "board.together.deeds": "{n} іс",
      "board.together.neighbours": "{n} көрші",
      "board.together.coming": "{n} көрші келеді",
      "board.together.yard": "Апта ауласы",
      "board.together.done_with": "Бірге атқарылды: {n} көрші",
      "board.together.supported": "Әкімдік қолдады",
      "board.together.on_review": "тексерілуде: {n}",
      "board.meetings.orders": "Кездесу тапсырмалары",
      "board.meetings.stat_done": "кездесу тапсырмасы орындалды",
      "board.meetings.stat_overdue": "тапсырманың мерзімі өтті",
      "board.meetings.stat_week": "мерзімі осы аптада",
      "board.meetings.done": "{total} ішінен {done} орындалды",
      "board.meetings.overdue": "мерзімі өткен: {n}",
      "board.meetings.due_week": "осы аптадағы мерзім: {n}",
      "board.meetings.next": "Келесі кездесу",
      "board.meetings.registered": "{n} адам келеді",
      "board.meetings.due_in": "{n} күннен кейін",
      "board.meetings.due_today": "мерзімі бүгін",
      "board.meetings.due_late": "{n} күнге кешікті",
      "board.meetings.host": "Аудан әкімі тұрғындармен",
      "board.forecast.badge": "Прототип · синтетика",
      "board.forecast.hint": "Шағым көбеюі ықтимал орындар — нақты тәуекел бағасы емес",
      "board.calm.title": "Бүгін тыныш",
      "board.calm.text": "Қызметтер, тұрғындар және кездесулер бойынша деректер болғанда көрші блоктар шығады",
      "board.login.title": "Жағдаяттық орталық — әкімдік қызметкерлеріне арналған",
      "board.login.text": "Қызметкер ретінде кіріңіз — басты беттегі «Қызметкерлерге» бөліміндегі логинмен.",
      "board.login.user": "Логин",
      "board.login.password": "Құпиясөз",
      "board.login.submit": "Кіру",
      "board.login.error": "Логин немесе құпиясөз сәйкес келмеді",
      "board.login.busy": "Кіріп жатырмыз…",
      "board.error.title": "Сервермен байланыс жоқ",
      "board.error.text": "30 секундтан кейін өзіміз қайталаймыз.",
      "board.to_map": "Картаға",
      "board.to_day": "Күн қорытындысы",
      "board.back": "Birge-ге оралу",
      "board.fullscreen": "Толық экран",
      "board.fullscreen_exit": "Толық экраннан шығу",
      "board.login.staff": "Қызметкер ретінде кіріңіз",
      "board.agencies.no_answer": "Мерзімінде жауап жоқ",
      "board.agencies.period": "{n} күнде",
      "board.weekday": ["жексенбі", "дүйсенбі", "сейсенбі", "сәрсенбі", "бейсенбі", "жұма", "сенбі"],
    },
  };

  function I() {
    return root.BirgeI18n;
  }
  function lang() {
    return I() ? I().getLang() : "ru";
  }
  function num(n) {
    return I() ? I().formatNumber(n) : String(n);
  }
  function interpolate(text, params) {
    return String(text).replace(/\{(\w+)\}/g, function (whole, name) {
      if (!params || params[name] == null) return whole;
      return typeof params[name] === "number" ? num(params[name]) : String(params[name]);
    });
  }
  function fallback(key, params) {
    var l = lang() === "kk" ? "kk" : "ru";
    var v = BOARD_KEYS[l][key];
    if (v == null) v = BOARD_KEYS.ru[key];
    if (v == null) return null;
    if (typeof v === "object" && !Array.isArray(v)) {
      var n = params && params.n != null ? Number(params.n) : 0;
      var cat = I() ? I().plural(l, n) : "many";
      v = v[cat] || v.other || v.many || v.few || v.one;
    }
    return interpolate(v, params);
  }
  // Сначала словарь R11; ключа нет — запасной текст отсюда; нет и его — сам ключ (видно при проверке).
  function tr(key, params) {
    var i18n = I();
    if (i18n && (i18n.has(key) || i18n.has(key, "ru"))) return i18n.t(key, params);
    var own = fallback(key, params);
    if (own != null) return own;
    return i18n ? i18n.t(key, params) : interpolate(key, params);
  }

  // ───────────── мелкие помощники ─────────────
  function h(tag, attrs, children) {
    var el = doc.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v == null || v === false) return;
        if (k === "text") el.textContent = v;
        else if (k === "class") el.className = v;
        else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? "" : v);
      });
    }
    (children || []).forEach(function (c) {
      if (c == null || c === false) return;
      el.appendChild(typeof c === "string" ? doc.createTextNode(c) : c);
    });
    return el;
  }
  function svgEl(tag, attrs) {
    var el = doc.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] != null) el.setAttribute(k, attrs[k]);
    });
    return el;
  }
  function icon(name, cls) {
    var svg = svgEl("svg", { class: "ic sc-ic" + (cls ? " " + cls : ""), "aria-hidden": "true", focusable: "false" });
    svg.appendChild(svgEl("use", { href: ICONS + "#" + (name.indexOf("st-") === 0 ? name : "i-" + name) }));
    return svg;
  }
  // Какие значки есть в наборе R11 (новые i-expand, i-pause, i-play — с раунда 15). Нет значка — запасная форма CSS.
  var ICON_IDS = null;
  var iconsReady = typeof fetch === "function"
    ? fetch(ICONS, { credentials: "same-origin" }).then(function (r) { return r.ok ? r.text() : ""; }).then(function (t) {
        ICON_IDS = {};
        (t.match(/id="[a-z0-9-]+"/g) || []).forEach(function (m) { ICON_IDS[m.slice(4, -1)] = true; });
      }).catch(function () { ICON_IDS = {}; })
    : Promise.resolve();
  function hasIcon(name) {
    return !!(ICON_IDS && ICON_IDS["i-" + name]);
  }
  function label(obj, base) {
    if (!obj) return "";
    var l = lang();
    return obj[base + "_" + l] || obj[base + "_ru"] || "";
  }
  function districtName(id) {
    return id ? tr("district." + id) : "";
  }
  function catName(id) {
    return id && I() ? I().cat(id) : id || "";
  }
  function serviceName(svc) {
    if (!svc) return "";
    if (svc.name_edited) return svc[lang()] || svc.ru;
    return I() && I().has("service." + svc.id) ? tr("service." + svc.id) : svc[lang()] || svc.ru;
  }
  function reduced() {
    return !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }
  function astanaNow() {
    return new Date(Date.now() + ASTANA_OFFSET_MS);
  }
  function pad2(n) {
    return (n < 10 ? "0" : "") + n;
  }
  // Изменение к той же поре неделю назад — тем же языком, что «Картина дня» (ключи akim.delta.*).
  function deltaText(ch) {
    if (!ch || !ch.trend || ch.trend === "flat") return tr("akim.delta.same");
    if (ch.mode === "new") return tr("akim.delta.new");
    if (ch.mode === "ratio") return tr("akim.delta.ratio", { n: ch.ratio });
    var v = ch.mode === "pct" ? I().formatPercent(ch.pct) : num(ch.abs);
    return tr(ch.trend === "up" ? "akim.delta.more" : "akim.delta.less", { v: v });
  }
  // Мини-график 14 дней (последняя точка — сейчас). Только для глаза: словами изменение сказано строкой выше.
  function sparkline(series) {
    if (!series || series.length < 2) return null;
    var W = 240, H = 44, pad = 4;
    var max = Math.max.apply(null, series) || 1;
    var step = (W - 2 * pad) / (series.length - 1);
    var pts = series.map(function (v, i) {
      return [pad + i * step, H - pad - (Math.max(0, v) / max) * (H - 2 * pad)];
    });
    var line = pts.map(function (p, i) {
      return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1);
    }).join("");
    var last = pts[pts.length - 1];
    var svg = svgEl("svg", { class: "sc-spark", viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none", "aria-hidden": "true", focusable: "false" });
    svg.appendChild(svgEl("path", { class: "sc-spark__area", d: line + "L" + last[0].toFixed(1) + " " + (H - pad) + "L" + pad + " " + (H - pad) + "Z" }));
    svg.appendChild(svgEl("path", { class: "sc-spark__line", d: line, "vector-effect": "non-scaling-stroke" }));
    svg.appendChild(svgEl("circle", { class: "sc-spark__dot", cx: last[0].toFixed(1), cy: last[1].toFixed(1), r: "4" }));
    return svg;
  }

  // Контуры районов: data/civic/astana/geofence.json (OpenStreetMap, ODbL, не официальная граница), упрощено до
  // ~1 px при ширине 240 — те же, что у мини-карты «Картины дня». Подписи — в центре самого большого кольца района.
  var OUTLINE = {
    box: [71.2179735, 50.9306941, 71.7851913, 51.3511101],
    k: 423.1179,
    sy: 674.3911,
    w: 240,
    h: 284,
    d: {
      almaty: "M239 135L240 125L221 125L224 127L230 139L232 139ZM97 148L113 152L127 146L130 142L136 145L147 145L176 153L205 164L210 148L199 142L181 142L171 110L156 103L154 100L143 108L137 110L133 115L131 116L129 117L121 113L118 118L110 126L93 137Z",
      baikonur: "M50 54L43 38L37 41L38 50L34 53L39 59ZM186 23L192 28L193 27L191 25L192 23L203 11L207 2L204 1L203 3L201 2L202 0L197 0L190 8L179 13ZM97 112L94 116L87 117L90 133L89 134L93 137L110 126L118 118L121 113L129 117L131 116L133 115L137 110L143 108L154 100L151 88L170 69L159 50L148 63L146 69L144 69L141 73L107 59L119 45L119 41L109 44L106 49L98 54L89 52L77 56L71 33L58 36L63 54L49 57L36 78L58 89L63 96Z",
      esil: "M89 134L83 146L81 162L69 215L69 228L100 236L99 248L101 249L99 263L104 265L103 272L105 272L106 273L107 279L112 278L114 283L139 283L142 258L142 253L135 245L135 232L138 229L143 226L136 204L139 202L143 204L153 189L165 175L156 171L131 167L125 169L119 167L115 170L111 169L107 166L101 165L99 163L96 156L99 152L97 149L94 138Z",
      nura: "M48 222L50 224L69 228L69 215L81 162L83 146L89 134L86 129L80 131L75 127L59 126L53 120L51 119L48 120L46 117L43 117L34 113L31 109L23 110L22 113L27 116L20 119L15 118L15 130L10 130L10 134L9 134L8 136L8 147L5 154L5 159L0 162L12 191L14 191L16 194L16 204L27 220L30 222L42 221Z",
      saraishyk: "M136 168L156 171L165 175L168 170L195 179L196 176L198 174L199 175L201 174L202 176L204 176L205 174L208 174L208 172L207 171L210 170L212 170L214 167L216 167L219 172L222 168L221 166L206 161L205 164L176 153L147 145L136 145L130 142L127 146L113 152L97 148L99 152L96 156L99 164L102 166L108 166L111 169L115 170L120 167L125 169L130 167Z",
      saryarka: "M61 126L75 127L80 131L86 129L89 134L90 133L87 117L94 116L97 112L63 96L57 88L36 78L35 79L18 71L11 85L13 85L10 94L8 95L11 97L9 101L11 103L10 103L16 109L18 107L20 109L25 110L31 109L34 113L43 117L46 117L48 120L52 119L59 126Z",
    },
    // Центры подписей (центр масс самого большого кольца), чуть сдвинуты, чтобы не спорить с точками мест.
    labels: { almaty: [158, 128], baikonur: [104, 78], esil: [112, 214], nura: [42, 172], saraishyk: [168, 163], saryarka: [46, 100] },
  };
  function project(lonlat) {
    var b = OUTLINE.box;
    if (!lonlat || lonlat[0] < b[0] || lonlat[0] > b[2] || lonlat[1] < b[1] || lonlat[1] > b[3]) return null;
    return [(lonlat[0] - b[0]) * OUTLINE.k, (b[3] - lonlat[1]) * OUTLINE.sy];
  }

  // ───────────── модуль ─────────────
  function mount(rootEl, options) {
    options = options || {};
    var params = new URLSearchParams(root.location.search);
    var opts = {
      apiBase: options.apiBase || rootEl.getAttribute("data-api") || "/api/civic/v2",
      loginUrl: options.loginUrl || "/api/civic/v1/session/login",
      sessionUrl: options.sessionUrl || "/api/civic/v1/session",
      district: DISTRICT_IDS.indexOf(params.get("district")) >= 0 ? params.get("district") : options.district || null,
      pinned: STAGE_IDS.indexOf(params.get("block")) >= 0 ? params.get("block") : null,
      rotate: params.get("rotate") !== "0" && options.rotate !== false,
      // Кризисный штаб R17: событие "birge:open-crisis" (отменяемое — оболочка откроет у себя), иначе ссылка.
      crisisHref: options.crisisHref || "/#agencies/crisis={id}",
      crisisNewHref: options.crisisNewHref || "/#agencies/crisis=new&template={kind}&district={district}",
      backHref: options.backHref || "/",
      mapHref: options.mapHref || "/#target={kind}:{id}&days={days}",
    };
    var state = {
      status: "loading", data: null, error: null, loadedAt: 0, stale: false, request: 0, skeleton: false,
      stageId: opts.pinned, elapsed: 0, paused: false, hover: false, focusIn: false,
    };
    var timers = { refresh: null, retry: null, tick: null, clock: null };

    rootEl.classList.add("sc");
    rootEl.textContent = "";
    var head = h("header", { class: "sc-head" });
    var crisisBar = h("div", { class: "sc-crisis-slot" });
    var body = h("div", { class: "sc-body-grid" });
    var foot = h("footer", { class: "sc-foot" });
    rootEl.appendChild(head);
    rootEl.appendChild(crisisBar);
    rootEl.appendChild(body);
    rootEl.appendChild(foot);

    // ── загрузка ──
    // CSRF сотрудника: сборка R01 проверяет сессию R02 вместе с токеном и на чтении (V2Handler staff=True), поэтому
    // GET /akim/board идёт с X-CSRF-Token — из оболочки (CivicShell.csrfToken), из ответа входа или GET /session.
    // Отказ csrf_failed (токен сменился) — один повтор со свежим токеном; 401 / 403 — форма входа.
    var csrfToken = null;
    function csrf(fresh) {
      try {
        var shell = root.CivicShell && typeof root.CivicShell.csrfToken === "function" ? root.CivicShell.csrfToken() : null;
        if (shell && !fresh) return Promise.resolve(shell);
      } catch (e) {
        /* оболочки нет — страница открыта отдельно */
      }
      if (csrfToken && !fresh) return Promise.resolve(csrfToken);
      return fetch(opts.sessionUrl, { credentials: "same-origin", cache: "no-store", headers: { Accept: "application/json" } })
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(function (b) {
          var d = b && b.data && typeof b.data === "object" ? b.data : b || {};
          csrfToken = d.authenticated && typeof d.csrf_token === "string" ? d.csrf_token : null;
          return csrfToken;
        })
        .catch(function () {
          return null;
        });
    }
    function csrfFailed(body) {
      var e = body && body.error;
      return e === "csrf_failed" || !!(e && typeof e === "object" && e.code === "csrf_failed");
    }
    function load(silent, retried) {
      silent = silent === true && !!state.data;
      retried = retried === true;
      var again = false;
      var id = ++state.request;
      clearTimeout(timers.retry);
      if (!silent) {
        state.skeleton = false;
        setTimeout(function () {
          if (id === state.request && state.status === "loading") {
            state.skeleton = true;
            render();
          }
        }, 150);
      }
      var q = new URLSearchParams();
      if (opts.district) q.set("district", opts.district);
      var ctrl = typeof AbortController === "function" ? new AbortController() : null;
      var timer = setTimeout(function () {
        if (ctrl) ctrl.abort();
      }, TIMEOUT_MS);
      return csrf(retried)
        .then(function (token) {
          var headers = { Accept: "application/json" };
          if (token) headers["X-CSRF-Token"] = token;
          return fetch(opts.apiBase + "/akim/board" + (q.toString() ? "?" + q : ""), {
            headers: headers,
            credentials: "same-origin",
            cache: "no-store",
            signal: ctrl ? ctrl.signal : undefined,
          });
        })
        .then(function (r) {
          return r.json().catch(function () {
            return null;
          }).then(function (b) {
            return { ok: r.ok, status: r.status, body: b };
          });
        })
        .then(function (res) {
          if (id !== state.request) return;
          if (res.ok && res.body && res.body.kpi) {
            var first = !state.data;
            state.data = res.body;
            state.status = "ok";
            state.stale = false;
            state.loadedAt = Date.now();
            if (first) chooseStage(true);
            else keepStage();
          } else if (res.status === 403 && csrfFailed(res.body) && !retried) {
            again = true; // токен сессии сменился — ещё раз со свежим
          } else if (res.status === 401 || res.status === 403) {
            csrfToken = null;
            state.status = "login";
            state.data = null;
          } else if (state.data) {
            state.stale = true; // ошибка при тихом обновлении: прежние числа остаются
          } else {
            state.status = "error";
            state.error = res.status === 400 ? "bad_request" : "server";
          }
        })
        .catch(function () {
          if (id !== state.request) return;
          if (state.data) state.stale = true;
          else {
            state.status = "error";
            state.error = "network";
          }
        })
        .then(function () {
          clearTimeout(timer);
          if (id !== state.request) return;
          if (again) return load(silent, true);
          render();
          schedule();
        });
    }
    function schedule() {
      clearTimeout(timers.refresh);
      clearTimeout(timers.retry);
      if (state.status === "ok") {
        var every = ((state.data && state.data.refresh_s) || 60) * 1000;
        timers.refresh = setTimeout(function () {
          if (doc.visibilityState === "hidden") return schedule();
          load(true);
        }, state.stale ? Math.min(every, RETRY_MS) : every);
      } else if (state.status === "error") {
        timers.retry = setTimeout(function () {
          load();
        }, RETRY_MS);
      }
    }
    function onVisible() {
      if (doc.visibilityState === "visible" && state.status === "ok" && Date.now() - state.loadedAt > 60000) load(true);
    }
    doc.addEventListener("visibilitychange", onVisible);

    // ── лента блоков ──
    function stageList() {
      var d = state.data;
      var list = (d && d.stage) || [];
      return list.filter(function (id) {
        return STAGE_IDS.indexOf(id) >= 0;
      });
    }
    function chooseStage(reset) {
      var list = stageList();
      if (opts.pinned && list.indexOf(opts.pinned) >= 0) state.stageId = opts.pinned;
      else if (reset || list.indexOf(state.stageId) < 0) state.stageId = list[0] || null;
      state.elapsed = 0;
    }
    function keepStage() {
      if (stageList().indexOf(state.stageId) < 0) chooseStage(true);
    }
    function rotateMs() {
      return ((state.data && state.data.rotate_s) || 15) * 1000;
    }
    function step(dir) {
      var list = stageList();
      if (list.length < 2) return;
      var i = list.indexOf(state.stageId);
      state.stageId = list[(i + dir + list.length) % list.length];
      state.elapsed = 0;
      renderStage(true);
    }
    function frozen() {
      return state.paused || state.hover || state.focusIn || !opts.rotate || !!opts.pinned;
    }
    function tick() {
      if (state.status !== "ok" || stageList().length < 2 || frozen() || doc.visibilityState === "hidden") return;
      state.elapsed += TICK_MS;
      if (state.elapsed >= rotateMs()) step(1);
      else updateProgress();
    }
    timers.tick = setInterval(tick, TICK_MS);

    // ── часы Астаны ──
    var clockEls = { time: null, date: null, lastMinute: null };
    function updateClock() {
      if (!clockEls.time) return;
      var t = astanaNow();
      var minute = t.getUTCHours() * 60 + t.getUTCMinutes();
      if (minute === clockEls.lastMinute && clockEls.date.textContent) return;
      clockEls.lastMinute = minute;
      clockEls.time.textContent = pad2(t.getUTCHours()) + ":" + pad2(t.getUTCMinutes());
      clockEls.time.setAttribute("datetime", t.toISOString().slice(0, 16));
      var days = fallbackList("board.weekday");
      var date = I() ? I().formatDate(new Date(Date.now())) : t.toISOString().slice(0, 10);
      clockEls.date.textContent = (days ? days[t.getUTCDay()] + " · " : "") + date;
    }
    function fallbackList(key) {
      var i18n = I();
      if (i18n && i18n.has(key)) {
        var v = i18n.t(key);
        if (Array.isArray(v)) return v;
      }
      var l = lang() === "kk" ? "kk" : "ru";
      return BOARD_KEYS[l][key] || BOARD_KEYS.ru[key] || null;
    }
    timers.clock = setInterval(updateClock, 1000);

    // ── клавиатура: ← → — блоки, пробел — пауза ──
    function onKey(e) {
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      var tag = (e.target && e.target.tagName) || "";
      if (/^(INPUT|TEXTAREA|SELECT)$/.test(tag)) return;
      if (e.key === "Escape" && !doc.fullscreenElement) {
        e.preventDefault();
        if (!goBackNow()) root.location.href = opts.backHref;
        return;
      }
      if (state.status !== "ok") return;
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        step(e.key === "ArrowRight" ? 1 : -1);
      } else if ((e.key === " " || e.key === "Spacebar") && !/^(BUTTON|A)$/.test(tag)) {
        e.preventDefault();
        togglePause();
      }
    }
    doc.addEventListener("keydown", onKey);
    function goBackNow() {
      var ev = { prevented: false, preventDefault: function () { this.prevented = true; } };
      goBack(ev);
      return ev.prevented;
    }
    function togglePause() {
      state.paused = !state.paused;
      renderStageNav();
    }

    // «На весь экран» (Fullscreen API) и «← В Birge» (R11 IA_ROUND15 §5.9). Esc: в полноэкранном режиме браузер сам
    // выходит из него; иначе — назад в Birge (туда, откуда пришли, или на главную).
    function toggleFullscreen() {
      if (doc.fullscreenElement) doc.exitFullscreen && doc.exitFullscreen();
      else doc.documentElement.requestFullscreen && doc.documentElement.requestFullscreen().catch(function () {});
    }
    function onFullscreen() {
      renderHead();
      setTimeout(fitAll, 200);
    }
    doc.addEventListener("fullscreenchange", onFullscreen);
    function goBack(e) {
      var ref = doc.referrer || "";
      var same = ref && ref.indexOf(root.location.origin + "/") === 0 && ref.indexOf("/civic/board") < 0;
      if (same && root.history.length > 1) {
        if (e) e.preventDefault();
        root.history.back();
      }
    }

    // ───────────── отрисовка ─────────────
    function render() {
      rootEl.setAttribute("data-state", state.status);
      rootEl.setAttribute("aria-busy", state.status === "loading" ? "true" : "false");
      if (state.data && state.data.demo && state.data.demo.any) rootEl.setAttribute("data-demo", "");
      else rootEl.removeAttribute("data-demo");
      renderHead();
      crisisBar.textContent = "";
      body.textContent = "";
      foot.textContent = "";
      if (state.status === "loading") {
        if (state.skeleton) renderSkeleton();
        return;
      }
      if (state.status === "login") return renderLogin();
      if (state.status === "error") return renderError();
      renderCrisisBar();
      body.appendChild(renderKpis());
      // Три колонки: карта районов · пульс и горячие места · лента блоков.
      body.appendChild(h("div", { class: "sc-main" }, [renderMap(), h("div", { class: "sc-mid" }, [renderPulse(), renderHot()]), renderStageShell()]));
      renderStage(false);
      renderFoot();
      fitAll();
    }

    // Подгонка под высоту экрана: строки списка, которые не помещаются в панель, скрываются целиком (не обрезаются
    // посередине). Так один экран работает на 1920×1080, 1366×768 и любом другом большом экране без прокрутки.
    function fitAll() {
      Array.prototype.forEach.call(rootEl.querySelectorAll("[data-fit]"), function (list) {
        var rows = Array.prototype.slice.call(list.children);
        rows.forEach(function (r) {
          r.hidden = false;
        });
        var bound = list.closest("[data-fit-bound]") || list.closest(".sc-panel");
        if (!bound || !rows.length) return;
        var cs = root.getComputedStyle(bound);
        var limit = bound.getBoundingClientRect().bottom - (bound.hasAttribute("data-fit-bound") ? 0 : parseFloat(cs.paddingBottom) || 0);
        for (var i = rows.length - 1; i >= 1; i--) {
          if (rows[i].getBoundingClientRect().bottom <= limit + 0.5) break;
          rows[i].hidden = true;
        }
      });
    }
    var resizeTimer = null;
    function onResize() {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(fitAll, 120);
    }
    root.addEventListener("resize", onResize);
    if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(function () {
      fitAll();
    });

    // ── шапка ──
    function renderHead() {
      head.textContent = "";
      var d = state.data;
      var scope = opts.district ? tr("board.scope.district", { name: districtName(opts.district) }) : tr("board.scope.city");
      var brand = h("div", { class: "sc-brand" }, [
        h("span", { class: "sc-mark", "aria-hidden": "true", text: "B" }),
        h("div", { class: "sc-brand__text" }, [
          h("h1", { class: "sc-title", text: tr("board.title") }),
          h("p", { class: "sc-sub" }, [
            h("span", { class: "sc-live", "data-stale": state.stale ? "" : null }, [h("span", { class: "sc-live__dot", "aria-hidden": "true" }), tr("board.live")]),
            " · " + tr("board.city") + " · " + scope,
          ]),
        ]),
      ]);
      var mid = h("div", { class: "sc-head__mid" });
      if (d && d.decisions && d.decisions.count > 0) {
        mid.appendChild(h("span", { class: "sc-chip sc-chip--decision" }, [icon("alert"), tr("board.decisions", { n: d.decisions.count })]));
      }
      if (d && d.demo && d.demo.any) mid.appendChild(h("span", { class: "sc-chip sc-chip--demo", text: tr("common.demo") }));
      var seg = h("div", { class: "sc-lang", role: "group", "aria-label": tr("common.lang.label") });
      ["kk", "ru"].forEach(function (l) {
        seg.appendChild(h("button", {
          type: "button", lang: l, "aria-pressed": String(lang() === l), text: tr("common.lang." + l),
          onclick: function () {
            if (I()) I().setLang(l);
          },
        }));
      });
      clockEls.time = h("time", { class: "sc-clock__time" });
      clockEls.date = h("span", { class: "sc-clock__date" });
      clockEls.lastMinute = null;
      var clock = h("div", { class: "sc-clock", "aria-live": "off" }, [clockEls.time, clockEls.date]);
      var full = !!doc.fullscreenElement;
      var fsBtn = doc.documentElement.requestFullscreen ? h("button", {
        type: "button", class: "sc-icon-btn", "aria-pressed": String(full),
        "aria-label": tr(full ? "board.fullscreen_exit" : "board.fullscreen"), title: tr(full ? "board.fullscreen_exit" : "board.fullscreen"),
        onclick: toggleFullscreen,
      }, [hasIcon("expand") ? icon("expand") : h("span", { class: "sc-fs-ic", "data-on": full ? "" : null, "aria-hidden": "true" })]) : null;
      var back = h("a", { class: "sc-back", href: opts.backHref, onclick: goBack }, [icon("back"), tr("board.back")]);
      head.appendChild(brand);
      head.appendChild(mid);
      head.appendChild(h("div", { class: "sc-head__end" }, [seg, fsBtn, back, clock]));
      updateClock();
      doc.title = tr("board.title") + " · Birge";
    }

    // ── полоса кризиса (идёт кризис — видна всегда, не только в ленте) ──
    // Адрес штаба R17: из данных («#agencies/crisis=<id>»), иначе по шаблону; кризиса нет — форма с шаблоном.
    function crisisLink(c) {
      if (c.link && c.link.charAt(0) === "#") return "/" + c.link;
      return interpolate(opts.crisisHref, { id: encodeURIComponent(c.id) });
    }
    function crisisNewLink(n) {
      return interpolate(opts.crisisNewHref, { kind: encodeURIComponent(n.kind || "other"), district: encodeURIComponent(n.district || "") });
    }
    function openCrisis(e, c) {
      var ev = new CustomEvent("birge:open-crisis", { cancelable: true, detail: { id: c.id, from: "board" } });
      if (!doc.dispatchEvent(ev)) e.preventDefault();
    }
    function renderCrisisBar() {
      var c = state.data.crisis;
      var a = c && c.available && c.active;
      if (!a) return;
      var zone = (a.zone && a.zone.districts) || [];
      var where = zone.length === 1 ? tr("board.crisis.zone", { name: districtName(zone[0].id) }) :
        zone.map(function (z) {
          return districtName(z.id);
        }).join(", ");
      var upd = a.last_update ? tr("board.crisis.update", { text: label(a.last_update, "text") }) : null;
      crisisBar.appendChild(
        h("section", { class: "sc-crisis", "aria-label": tr("board.crisis.label") }, [
          h("span", { class: "sc-crisis__pulse", "aria-hidden": "true" }),
          h("span", { class: "sc-crisis__label", text: tr("board.crisis.label") }),
          h("strong", { class: "sc-crisis__title", text: label(a, "title") }),
          h("span", { class: "sc-crisis__meta", text: [where, a.hours != null ? tr("board.crisis.hours", { n: a.hours }) : null,
            tr("board.crisis.tasks", { done: a.tasks_done, total: a.tasks_total })].filter(Boolean).join(" · ") }),
          upd ? h("span", { class: "sc-crisis__update", text: upd }) : null,
          h("a", { class: "sc-crisis__open", href: crisisLink(a), onclick: function (e) { openCrisis(e, a); } }, [tr("board.crisis.open"), icon("chevron-right")]),
        ])
      );
    }

    // ── 4 числа ──
    function kpiTile(item, labelKey, goodWhenUp, extra) {
      var ch = item || {};
      var good = null;
      if (ch.trend && ch.trend !== "flat" && goodWhenUp != null) good = (ch.trend === "up") === goodWhenUp;
      return h("article", { class: "sc-panel sc-kpi", "data-kind": ch.id }, [
        h("p", { class: "sc-kpi__label", text: tr(labelKey) }),
        h("p", { class: "sc-kpi__value", text: ch.value == null ? "—" : num(ch.value) }),
        h("p", { class: "sc-kpi__delta", "data-trend": ch.trend || "flat", "data-good": good == null ? null : String(good) }, [
          h("span", { class: "sc-kpi__arrow", "aria-hidden": "true" }),
          deltaText(ch),
          h("span", { class: "sc-sr", text: " " + tr("akim.delta.vs_week") }),
        ]),
        extra ? h("p", { class: "sc-kpi__extra", text: extra }) : null,
        sparkline(ch.series),
      ]);
    }
    function renderKpis() {
      var k = state.data.kpi || {};
      var by = {};
      (k.items || []).forEach(function (it) {
        by[it.id] = it;
      });
      var fixed = by.fixed_week || {};
      var verifiedText = k.verification_available && fixed.verified != null ? tr("board.kpi.verified", { n: fixed.verified }) : null;
      var newWeek = k.new_week && k.new_week.value != null ? tr("board.kpi.week", { n: k.new_week.value }) : null;
      var waiting = by.in_progress && by.in_progress.waiting ? tr("akim.kpi.waiting", { n: by.in_progress.waiting }) : null;
      if (k.available === false) {
        return h("section", { class: "sc-kpis sc-kpis--off" }, [h("p", { class: "sc-panel sc-off", text: tr("akim.no_complaints") })]);
      }
      return h("section", { class: "sc-kpis", "aria-label": tr("akim.title") }, [
        kpiTile(by.new_day, "board.kpi.new", false, newWeek),
        kpiTile(by.in_progress, "akim.kpi.in_progress", null, waiting),
        kpiTile(by.overdue, "akim.kpi.overdue", false, tr("akim.kpi.overdue_hint")),
        kpiTile(fixed, "akim.kpi.fixed_week", true, verifiedText),
      ]);
    }

    // ── карта районов и горячие места ──
    function heatLevelOf(value, max) {
      if (!value) return 0;
      var share = value / (max || 1);
      return share >= 0.75 ? 3 : share >= 0.4 ? 2 : 1;
    }
    function mapLink(target) {
      return interpolate(opts.mapHref, { kind: encodeURIComponent(target.kind), id: encodeURIComponent(target.id), days: 7 });
    }
    function renderMap() {
      var d = state.data;
      var dist = (d.districts && d.districts.items) || [];
      var hot = (d.hot && d.hot.items) || [];
      var crisisZone = {};
      var a = d.crisis && d.crisis.available && d.crisis.active;
      ((a && a.zone && a.zone.districts) || []).forEach(function (z) {
        crisisZone[z.id] = true;
      });
      var values = {};
      var max = 0;
      dist.forEach(function (r) {
        values[r.district] = r.value || 0;
        max = Math.max(max, r.value || 0);
      });
      var svg = svgEl("svg", { class: "sc-map__svg", viewBox: "-6 -6 " + (OUTLINE.w + 12) + " " + (OUTLINE.h + 12), role: "img", "aria-label": tr("board.map.title") });
      Object.keys(OUTLINE.d).forEach(function (id) {
        var lvl = heatLevelOf(values[id], max);
        svg.appendChild(svgEl("path", {
          class: "sc-map__district" + (opts.district === id ? " is-current" : "") + (crisisZone[id] ? " is-crisis" : ""),
          d: OUTLINE.d[id], "data-level": String(lvl),
        }));
      });
      Object.keys(OUTLINE.labels).forEach(function (id) {
        var p = OUTLINE.labels[id];
        var t = svgEl("text", { class: "sc-map__label", x: String(p[0]), y: String(p[1]), "text-anchor": "middle" });
        t.appendChild(doc.createTextNode(districtName(id)));
        svg.appendChild(t);
        if (values[id] != null) {
          var n = svgEl("text", { class: "sc-map__count", x: String(p[0]), y: String(p[1] + 11), "text-anchor": "middle" });
          n.appendChild(doc.createTextNode(num(values[id])));
          svg.appendChild(n);
        }
      });
      hot.slice().reverse().forEach(function (it) {
        var p = project(it.anchor);
        if (!p) return;
        var g = svgEl("g", { class: "sc-map__place", "data-level": String(it.level || 1) });
        g.appendChild(svgEl("circle", { class: "sc-map__dot", cx: p[0].toFixed(1), cy: p[1].toFixed(1), r: "7.5" }));
        var t = svgEl("text", { class: "sc-map__rank", x: p[0].toFixed(1), y: (p[1] + 3).toFixed(1), "text-anchor": "middle" });
        t.appendChild(doc.createTextNode(String(it.rank)));
        g.appendChild(t);
        svg.appendChild(g);
      });
      return h("section", { class: "sc-panel sc-map", "aria-labelledby": "sc-map-title" }, [
        h("div", { class: "sc-panel__head" }, [h("h2", { class: "sc-h2", id: "sc-map-title", text: tr("board.map.title") })]),
        h("p", { class: "sc-hint sc-map__hint", text: tr("board.map.hint") }),
        h("div", { class: "sc-map__body" }, [h("figure", { class: "sc-map__figure" }, [svg, h("figcaption", { class: "sc-credit", text: "© OpenStreetMap" })])]),
      ]);
    }
    function renderHot() {
      var d = state.data;
      var hot = (d.hot && d.hot.items) || [];
      var list = h("ol", { class: "sc-hot", "data-fit": "" });
      hot.forEach(function (it) {
        list.appendChild(h("li", { class: "sc-hot__row" }, [
          h("span", { class: "sc-hot__rank", "data-level": String(it.level || 1), text: String(it.rank) }),
          h("span", { class: "sc-hot__main" }, [
            h("span", { class: "sc-hot__name", text: label(it.target, "label") || catName(it.category) }),
            h("span", { class: "sc-hot__meta", text: [catName(it.category), districtName(it.district)].filter(Boolean).join(" · ") }),
          ]),
          h("span", { class: "sc-hot__count", text: tr("board.people", { n: it.count }) }),
        ]));
      });
      return h("section", { class: "sc-panel sc-hotbox", "aria-labelledby": "sc-hot-title" }, [
        h("div", { class: "sc-panel__head" }, [
          h("h2", { class: "sc-h2", id: "sc-hot-title", text: tr("akim.hot.title") }),
          h("p", { class: "sc-hint", text: tr("akim.topics.hint") }),
        ]),
        hot.length ? list : h("p", { class: "sc-hint", text: tr("akim.hot.empty") }),
      ]);
    }

    // ── пульс ──
    function pulseTexts(a) {
      var cat = catName(a.category);
      var dist = districtName(a.district);
      var place = a.target ? label(a.target, "label") : "";
      if (a.kind === "spike") return [tr("akim.pulse.spike", { category: cat, district: dist, k: a.k }), tr("akim.pulse.reason.spike", { n: a.value, base: num(a.base >= 3 ? Math.round(a.base) : a.base) })];
      if (a.kind === "spike_new") return [tr("akim.pulse.spike_new", { category: cat, district: dist }), tr("akim.pulse.reason.spike_new", { n: a.value })];
      if (a.kind === "spike_city") {
        var names = (a.districts || []).slice(0, 3).map(function (x) {
          return districtName(x.district) + " — " + num(x.value);
        });
        return [tr("akim.pulse.spike_city", { category: cat, n: (a.districts || []).length, k: a.k }), tr("akim.pulse.reason.city", { list: names.join(", ") })];
      }
      if (a.kind === "new_hot") return [tr("akim.pulse.new_hot", { place: place }), tr("akim.pulse.reason.new_hot", { n: a.value })];
      return [tr("akim.pulse.metoo_growth", { place: place, n: a.value }), tr("akim.pulse.reason.metoo", { n: a.prev || 0 })];
    }
    function renderPulse() {
      var p = state.data.pulse || {};
      var items = p.items || [];
      var title = tr(opts.district ? "board.pulse.title_district" : "board.pulse.title");
      var box = h("section", { class: "sc-panel sc-pulse", "aria-labelledby": "sc-pulse-title" }, [
        h("div", { class: "sc-panel__head" }, [h("h2", { class: "sc-h2", id: "sc-pulse-title", text: title })]),
      ]);
      if (!p.available || !items.length) {
        box.appendChild(h("p", { class: "sc-pulse__calm" }, [icon("check"), tr("board.pulse.calm")]));
        return box;
      }
      var list = h("ul", { class: "sc-pulse__list", "data-fit": "" });
      items.forEach(function (a) {
        var t = pulseTexts(a);
        var ic = a.kind === "new_hot" || a.kind === "spike_new" ? "pin" : a.kind === "metoo" ? "users" : "chart";
        var target = a.crisis || a.crisis_new || null;
        var pill = target ? h("span", { class: "sc-pulse__crisis", "aria-hidden": "true" }, [icon("alert"), tr("board.crisis.short"), icon("chevron-right")]) : null;
        var parts = [
          h("span", { class: "sc-pulse__icon", "aria-hidden": "true" }, [icon(ic)]),
          h("span", { class: "sc-pulse__text" }, [
            h("span", { class: "sc-pulse__title", text: t[0] }),
            h("span", { class: "sc-pulse__sub" }, [h("span", { class: "sc-pulse__reason", text: t[1] }), pill]),
          ]),
        ];
        // Тревога по теме идущего кризиса — вся строка ведёт в кризисный штаб (кнопка «Открыть кризисный штаб», R17).
        if (target) {
          list.appendChild(h("li", { class: "sc-pulse__item has-crisis", "data-kind": a.kind }, [
            h("a", { class: "sc-pulse__link", href: a.crisis ? crisisLink(a.crisis) : crisisNewLink(a.crisis_new),
              "aria-label": t[0] + ". " + tr("board.crisis.open") + (a.crisis ? ": " + label(a.crisis, "title") : ""),
              onclick: function (e) { if (a.crisis) openCrisis(e, a.crisis); } }, parts),
          ]));
          return;
        }
        list.appendChild(h("li", { class: "sc-pulse__item", "data-kind": a.kind }, [h("span", { class: "sc-pulse__row" }, parts)]));
      });
      box.appendChild(list);
      return box;
    }

    // ── лента блоков ──
    var stageEl = null, stageBody = null, stageNav = null;
    function renderStageShell() {
      stageBody = h("div", { class: "sc-stage__body", "aria-live": "polite", "data-fit-bound": "" });
      stageNav = h("div", { class: "sc-stage__nav" });
      stageEl = h("section", { class: "sc-panel sc-stage", "aria-roledescription": "carousel", "aria-label": tr("board.title") }, [stageBody, stageNav]);
      stageEl.addEventListener("mouseenter", function () {
        state.hover = true;
        renderStageNav();
      });
      stageEl.addEventListener("mouseleave", function () {
        state.hover = false;
        renderStageNav();
      });
      stageEl.addEventListener("focusin", function () {
        state.focusIn = true;
        renderStageNav();
      });
      stageEl.addEventListener("focusout", function (e) {
        if (!stageEl.contains(e.relatedTarget)) {
          state.focusIn = false;
          renderStageNav();
        }
      });
      return stageEl;
    }
    function stageTitle(id) {
      if (id === "forecast" && state.data.forecast && state.data.forecast.period === "month") return tr("board.stage.forecast_month");
      return tr("board.stage." + id);
    }
    function renderStage(animate) {
      if (!stageBody) return;
      var id = state.stageId;
      stageBody.textContent = "";
      var content = id ? STAGE_RENDER[id](state.data[id] || {}) : null;
      // П1: пустое состояние — маленькая иконка R11, короткий текст и одна кнопка.
      if (!content) content = h("div", { class: "sc-calm" }, [
        icon("check", "sc-calm__ic"),
        h("p", { class: "sc-calm__title", text: tr("board.calm.title") }),
        h("p", { class: "sc-hint", text: tr("board.calm.text") }),
        h("a", { class: "sc-btn", href: "/#day" }, [tr("board.to_day")]),
      ]);
      var wrap = h("div", { class: "sc-block" + (animate && !reduced() ? " is-entering" : ""), "data-block": id || "calm" }, [
        id ? h("div", { class: "sc-block__head" }, [
          h("span", { class: "sc-block__icon", "aria-hidden": "true" }, [icon(STAGE_ICON[id])]),
          h("h2", { class: "sc-h2 sc-block__title", text: stageTitle(id) }),
          id === "forecast" ? h("span", { class: "sc-chip sc-chip--proto", text: tr("board.forecast.badge") }) : null,
          state.data[id] && state.data[id].demo && id !== "forecast" ? h("span", { class: "sc-chip sc-chip--demo", text: tr("common.demo") }) : null,
        ]) : null,
        content,
      ]);
      stageBody.appendChild(wrap);
      renderStageNav();
      fitAll();
    }
    function renderStageNav() {
      if (!stageNav) return;
      stageNav.textContent = "";
      var list = stageList();
      if (stageEl) stageEl.classList.toggle("is-paused", frozen());
      if (list.length < 1) return;
      list.forEach(function (id) {
        var cur = id === state.stageId;
        var bar = h("span", { class: "sc-tab__bar", "aria-hidden": "true" }, [h("span", { class: "sc-tab__fill" })]);
        stageNav.appendChild(h("button", {
          type: "button", class: "sc-tab", "aria-current": cur ? "true" : null, "data-block": id,
          "aria-label": tr("board.stage.show", { name: stageTitle(id) }),
          onclick: function () {
            state.stageId = id;
            state.elapsed = 0;
            renderStage(true);
          },
        }, [icon(STAGE_ICON[id]), h("span", { class: "sc-tab__name", text: stageTitle(id) }), cur ? bar : null]));
      });
      if (list.length > 1 && opts.rotate && !opts.pinned) {
        stageNav.appendChild(h("button", {
          type: "button", class: "sc-tab sc-tab--pause", "aria-pressed": String(state.paused),
          "aria-label": tr(state.paused ? "board.stage.play" : "board.stage.pause"),
          onclick: togglePause,
        }, [hasIcon("pause") && hasIcon("play") ? icon(state.paused ? "play" : "pause")
          : h("span", { class: "sc-pause-ic", "data-paused": state.paused ? "" : null, "aria-hidden": "true" })]));
      }
      updateProgress();
    }
    function updateProgress() {
      if (!stageNav) return;
      var fill = stageNav.querySelector('[aria-current="true"] .sc-tab__fill');
      if (!fill) return;
      var share = frozen() || stageList().length < 2 ? 0 : Math.min(1, state.elapsed / rotateMs());
      fill.style.transform = "scaleX(" + share.toFixed(3) + ")";
    }

    // ── блоки ленты ──
    function bigStat(value, labelText, mod) {
      return h("div", { class: "sc-stat" + (mod ? " sc-stat--" + mod : "") }, [
        h("span", { class: "sc-stat__value", text: value == null ? "—" : typeof value === "number" ? num(value) : value }),
        h("span", { class: "sc-stat__label", text: labelText }),
      ]);
    }
    function pct(share) {
      return share == null ? "—" : I().formatPercent(share, { fraction: true });
    }
    function days(v) {
      return v == null ? "—" : num(Math.round(v * 10) / 10);
    }
    var STAGE_RENDER = {
      crisis: function (c) {
        var a = c.active;
        if (!a) return null;
        var services = h("ul", { class: "sc-svc-chips", "data-fit": "" });
        (a.services || []).forEach(function (s) {
          var done = s.done === s.total;
          services.appendChild(h("li", { class: "sc-svc-chip" + (done ? " is-done" : "") }, [
            icon(done ? "st-done" : s.doing ? "st-half" : "st-ring"),
            h("span", { class: "sc-svc-chip__name", text: serviceName(s.service) }),
            h("span", { class: "sc-svc-chip__count", text: num(s.done) + "/" + num(s.total) }),
          ]));
        });
        var share = a.tasks_total ? a.tasks_done / a.tasks_total : 0;
        var ring = svgEl("svg", { class: "sc-ring", viewBox: "0 0 120 120", "aria-hidden": "true" });
        ring.appendChild(svgEl("circle", { class: "sc-ring__track", cx: "60", cy: "60", r: "52" }));
        ring.appendChild(svgEl("circle", { class: "sc-ring__fill", cx: "60", cy: "60", r: "52", pathLength: "100", "stroke-dasharray": (share * 100).toFixed(1) + " 100" }));
        var zone = (a.zone && a.zone.districts) || [];
        return h("div", { class: "sc-crisis-block" }, [
          h("div", { class: "sc-crisis-block__left" }, [
            h("p", { class: "sc-crisis-block__title", text: label(a, "title") }),
            h("p", { class: "sc-hint", text: [zone.length === 1 ? tr("board.crisis.zone", { name: districtName(zone[0].id) }) : zone.map(function (z) { return districtName(z.id); }).join(", "),
              a.hours != null ? tr("board.crisis.hours", { n: a.hours }) : null].filter(Boolean).join(" · ") }),
            h("div", { class: "sc-crisis-block__progress" }, [
              h("div", { class: "sc-ring-box" }, [ring, h("span", { class: "sc-ring__text", text: num(a.tasks_done) + "/" + num(a.tasks_total) })]),
              h("p", { class: "sc-crisis-block__tasks", text: tr("board.crisis.tasks_label") }),
            ]),
            h("a", { class: "sc-btn", href: crisisLink(a), onclick: function (e) { openCrisis(e, a); } }, [tr("board.crisis.open"), icon("chevron-right")]),
          ]),
          h("div", { class: "sc-crisis-block__right" }, [
            h("h3", { class: "sc-h3", text: tr("board.crisis.services") }),
            services,
            a.last_update ? h("blockquote", { class: "sc-quote" }, [
              h("p", { text: label(a.last_update, "text") }),
              h("footer", { class: "sc-hint", text: I().formatTime(a.last_update.at) }),
            ]) : null,
          ]),
        ]);
      },
      agencies: function (g) {
        var rows = g.board || [];
        if (!rows.length) return null;
        var maxOpen = rows.reduce(function (m, r) { return Math.max(m, r.open || 0); }, 0) || 1;
        var lagging = {};
        (g.lagging || []).forEach(function (r) { lagging[r.service.id] = true; });
        var table = h("table", { class: "sc-table" }, [
          h("thead", null, [h("tr", null, [
            h("th", { scope: "col", text: tr("board.agencies.service") }),
            h("th", { scope: "col", class: "sc-num", text: tr("board.agencies.open") }),
            h("th", { scope: "col", class: "sc-num", text: tr("board.agencies.no_answer") }),
            h("th", { scope: "col", class: "sc-num", text: tr("board.agencies.median") }),
            h("th", { scope: "col", class: "sc-num", text: tr("board.agencies.verified") }),
          ])]),
          h("tbody", { "data-fit": "" }, rows.map(function (r) {
            var lag = lagging[r.service.id];
            return h("tr", { class: lag ? "is-lagging" : null }, [
              h("th", { scope: "row" }, [h("span", { class: "sc-svc" }, [
                lag ? h("span", { class: "sc-svc__lag", title: tr("board.agencies.lagging") }, [h("span", { class: "sc-sr", text: tr("board.agencies.lagging") + ": " })]) : null,
                h("span", { class: "sc-svc__name", text: serviceName(r.service) }),
              ])]),
              // Полоса нагрузки — фоном ячейки «Открыто» (доля от самой загруженной службы на табло).
              h("td", { class: "sc-num sc-open", style: "--share:" + Math.round(((r.open || 0) / maxOpen) * 100) + "%", text: num(r.open || 0) }),
              h("td", { class: "sc-num" + ((r.overdue || 0) > 0 ? " is-bad" : ""), text: r.overdue == null ? "—" : num(r.overdue) }),
              h("td", { class: "sc-num", text: days(r.median_answer_days) }),
              h("td", { class: "sc-num is-good", text: pct(r.verified_share) }),
            ]);
          })),
        ]);
        return h("div", { class: "sc-agencies" }, [
          h("div", { class: "sc-stats sc-stats--row" }, [
            g.joint != null ? bigStat(g.joint, tr("board.agencies.joint", { n: g.joint })) : null,
            g.handoffs_week != null ? bigStat(g.handoffs_week, tr("board.agencies.handoffs", { n: g.handoffs_week })) : null,
          ]),
          table,
          g.board_days ? h("p", { class: "sc-hint sc-table-note", text: tr("board.agencies.period", { n: g.board_days }) }) : null,
        ]);
      },
      together: function (t) {
        var star = t.yard_of_week;
        var stats = h("div", { class: "sc-stats" }, [
          bigStat(t.done_week, tr("board.together.stat_done", { n: t.done_week }), "good"),
          bigStat(t.people_done, tr("board.together.stat_people", { n: t.people_done })),
          bigStat(t.upcoming, tr("board.together.stat_upcoming", { n: t.upcoming })),
          t.verified && t.verified.available ? bigStat(t.verified.value, tr("board.together.stat_verified", { n: t.verified.value }), "good") : null,
        ]);
        var card = star ? h("article", { class: "sc-yard" }, [
          h("p", { class: "sc-yard__eyebrow" }, [icon("home"), tr("board.together.yard")]),
          h("p", { class: "sc-yard__name", text: star.target ? label(star.target, "label") : label(star, "title") }),
          h("p", { class: "sc-yard__deed", text: label(star, "title") }),
          h("p", { class: "sc-yard__count" }, [
            icon("users"),
            star.status === "done" ? tr("board.together.done_with", { n: star.joined }) : tr("board.together.coming", { n: star.joined }),
          ]),
          star.supported ? h("span", { class: "sc-tag sc-tag--ok" }, [icon("check"), tr("board.together.supported")]) : null,
        ]) : null;
        var soon = h("ul", { class: "sc-list", "data-fit": "" });
        (t.upcoming_items || []).forEach(function (it) {
          soon.appendChild(h("li", { class: "sc-list__row sc-list__row--two" }, [
            icon("calendar"),
            h("span", { class: "sc-list__main" }, [
              h("span", { class: "sc-list__title", text: label(it, "title") }),
              h("span", { class: "sc-list__meta", text: [it.target ? label(it.target, "label") : null, it.starts_at ? I().formatDateTime(it.starts_at) : null].filter(Boolean).join(" · ") }),
              h("span", { class: "sc-list__meta sc-list__meta--strong", text: tr("board.together.coming", { n: it.joined }) }),
            ]),
          ]));
        });
        return h("div", { class: "sc-together" }, [stats, h("div", { class: "sc-together__row" }, [card, (t.upcoming_items || []).length ? soon : null])]);
      },
      meetings: function (m) {
        var o = m.orders || {};
        var list = h("ul", { class: "sc-list", "data-fit": "" });
        (m.items || []).forEach(function (it) {
          var due = it.overdue ? tr("board.meetings.due_late", { n: Math.abs(it.days_left) }) :
            it.days_left === 0 ? tr("board.meetings.due_today") : it.days_left != null ? tr("board.meetings.due_in", { n: it.days_left }) : "";
          list.appendChild(h("li", { class: "sc-list__row" + (it.overdue ? " is-late" : "") }, [
            icon(it.status === "in_progress" ? "st-half" : "st-ring"),
            h("span", { class: "sc-list__main" }, [
              h("span", { class: "sc-list__title", text: label(it, "text") }),
              h("span", { class: "sc-list__meta", text: [serviceName(it.service), it.meeting ? districtName(it.meeting.district) : null].filter(Boolean).join(" · ") }),
            ]),
            h("span", { class: "sc-list__end" + (it.overdue ? " is-bad" : ""), text: due }),
          ]));
        });
        var nxt = m.next;
        return h("div", { class: "sc-meetings" }, [
          h("div", { class: "sc-stats" }, [
            bigStat(o.done != null ? num(o.done) + "/" + num(o.total || 0) : null, tr("board.meetings.stat_done")),
            bigStat(o.overdue || 0, tr("board.meetings.stat_overdue", { n: o.overdue || 0 }), o.overdue ? "bad" : null),
            bigStat(o.due_week || 0, tr("board.meetings.stat_week")),
          ]),
          (m.items || []).length ? list : null,
          nxt ? h("p", { class: "sc-next" }, [
            icon("calendar"),
            h("strong", { text: tr("board.meetings.next") + ": " }),
            [districtName(nxt.district), I().formatDateTime(nxt.at), tr("board.meetings.registered", { n: nxt.registered })].filter(Boolean).join(" · "),
          ]) : null,
        ]);
      },
      forecast: function (f) {
        var items = f.items || [];
        if (!items.length) return null;
        var list = h("ol", { class: "sc-list sc-forecast", "data-fit": "" });
        items.forEach(function (it) {
          list.appendChild(h("li", { class: "sc-list__row" }, [
            h("span", { class: "sc-level", "data-level": it.level || "low", "aria-hidden": "true" }),
            h("span", { class: "sc-list__main" }, [
              h("span", { class: "sc-list__title", text: it.target ? label(it.target, "label") : catName(it.category) }),
              h("span", { class: "sc-list__meta", text: [catName(it.category), districtName(it.district), label(it, "reason")].filter(Boolean).join(" · ") }),
            ]),
            h("span", { class: "sc-list__end", text: it.level ? tr("forecast.level." + it.level) : "" }),
          ]));
        });
        return h("div", { class: "sc-forecast-block" }, [h("p", { class: "sc-hint", text: tr("board.forecast.hint") }), list]);
      },
    };

    // ── подвал ──
    function renderFoot() {
      var d = state.data;
      var bits = [
        h("span", { class: "sc-foot__time" + (state.stale ? " is-stale" : ""),
          text: state.stale ? tr("board.stale", { time: I().formatTime(d.as_of) }) : tr("board.updated", { time: I().formatTime(d.as_of) }) + " · " + tr("board.refresh_note") }),
        h("span", { class: "sc-foot__keys", text: tr("board.keys") }),
      ];
      if (d.demo && d.demo.any) bits.push(h("span", { class: "sc-foot__demo", text: tr("board.demo_note") }));
      bits.push(h("nav", { class: "sc-foot__nav" }, [
        h("a", { href: "/#day", text: tr("board.to_day") }),
        h("a", { href: "/", text: tr("board.to_map") }),
      ]));
      bits.forEach(function (b) {
        foot.appendChild(b);
      });
    }

    // ── состояния ──
    function renderSkeleton() {
      var kpis = h("section", { class: "sc-kpis" }, [0, 1, 2, 3].map(function () {
        return h("div", { class: "sc-panel sc-kpi sc-skel" });
      }));
      body.appendChild(kpis);
      body.appendChild(h("div", { class: "sc-main" }, [h("div", { class: "sc-panel sc-map sc-skel" }), h("div", { class: "sc-mid" }, [
        h("div", { class: "sc-panel sc-pulse sc-skel" }), h("div", { class: "sc-panel sc-hotbox sc-skel" })]), h("div", { class: "sc-panel sc-stage sc-skel" })]));
    }
    function renderError() {
      body.appendChild(h("div", { class: "sc-center" }, [
        h("div", { class: "sc-panel sc-message", role: "alert" }, [
          icon("wifi-off", "sc-message__ic"),
          h("h2", { class: "sc-h2", text: tr("board.error.title") }),
          h("p", { class: "sc-hint", text: tr("board.error.text") }),
          h("button", { type: "button", class: "sc-btn", onclick: function () { load(); }, text: tr("common.action.retry") }),
        ]),
      ]));
    }
    function renderLogin() {
      var err = h("p", { class: "sc-login__error", role: "alert" });
      var user = h("input", { class: "sc-input", name: "username", autocomplete: "username", required: true, id: "sc-user" });
      var pass = h("input", { class: "sc-input", name: "password", type: "password", autocomplete: "current-password", required: true, id: "sc-pass" });
      var btn = h("button", { type: "submit", class: "sc-btn sc-btn--primary", text: tr("board.login.submit") });
      var form = h("form", { class: "sc-panel sc-message sc-login", novalidate: true }, [
        icon("building", "sc-message__ic"),
        h("h2", { class: "sc-h2", text: tr("board.login.title") }),
        h("p", { class: "sc-hint", text: tr("board.login.text") }),
        h("label", { class: "sc-field", for: "sc-user" }, [h("span", { text: tr("board.login.user") }), user]),
        h("label", { class: "sc-field", for: "sc-pass" }, [h("span", { text: tr("board.login.password") }), pass]),
        err,
        btn,
        h("a", { class: "sc-link", href: opts.backHref, onclick: goBack }, ["← " + tr("board.back")]),
      ]);
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        if (!user.value || !pass.value) {
          err.textContent = tr("board.login.error");
          return;
        }
        btn.disabled = true;
        btn.textContent = tr("board.login.busy");
        err.textContent = "";
        fetch(opts.loginUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify({ username: user.value, password: pass.value }),
        })
          .then(function (r) {
            return r.json().catch(function () { return null; }).then(function (b) { return { ok: r.ok, body: b }; });
          })
          .then(function (res) {
            if (res.ok && res.body && res.body.ok !== false) {
              var d = res.body.data && typeof res.body.data === "object" ? res.body.data : res.body;
              csrfToken = typeof d.csrf_token === "string" ? d.csrf_token : null;
              state.status = "loading";
              render();
              load();
              return;
            }
            err.textContent = tr("board.login.error");
            btn.disabled = false;
            btn.textContent = tr("board.login.submit");
            pass.value = "";
            pass.focus();
          })
          .catch(function () {
            err.textContent = tr("board.error.title");
            btn.disabled = false;
            btn.textContent = tr("board.login.submit");
          });
      });
      body.appendChild(h("div", { class: "sc-center" }, [form]));
      setTimeout(function () {
        user.focus();
      }, 0);
    }

    var off = null;
    (I() ? I().ready : Promise.resolve()).then(function () {
      if (I()) off = I().onChange(function () {
        render();
      });
      render();
      load();
      iconsReady.then(function () {
        renderHead();
        renderStageNav();
      });
    });

    var handle = {
      reload: function () {
        return load();
      },
      refresh: function () {
        return load(true);
      },
      next: function () {
        step(1);
      },
      prev: function () {
        step(-1);
      },
      pause: function (on) {
        state.paused = on !== false;
        renderStageNav();
      },
      get state() {
        return { status: state.status, stage: state.stageId, stages: stageList(), paused: frozen(), stale: state.stale };
      },
      destroy: function () {
        if (off) off();
        Object.keys(timers).forEach(function (k) {
          clearTimeout(timers[k]);
          clearInterval(timers[k]);
        });
        doc.removeEventListener("keydown", onKey);
        doc.removeEventListener("fullscreenchange", onFullscreen);
        root.removeEventListener("resize", onResize);
        doc.removeEventListener("visibilitychange", onVisible);
        state.request++;
        rootEl.textContent = "";
        delete rootEl.birgeBoard;
      },
    };
    rootEl.birgeBoard = handle; // для оболочки и тестов: document.getElementById("board").birgeBoard.next()
    return handle;
  }

  root.BirgeBoard = { mount: mount, version: "board-r15", keys: BOARD_KEYS };

  // Своя страница (/civic/board/): <script src="board.js" data-autostart="board"> — смонтировать в #board.
  var auto = script && script.getAttribute("data-autostart");
  if (auto) {
    var start = function () {
      var el = doc.getElementById(auto);
      if (el) mount(el, {});
    };
    if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", start);
    else start();
  }
})(window);
