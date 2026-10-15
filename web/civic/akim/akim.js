/*
 * Birge · «Картина дня» для акима (R08, раунд 14).
 *
 * Подключение (после ui-kit и i18n):
 *   <link rel="stylesheet" href="/civic/akim/akim.css">
 *   <script src="/civic/i18n/i18n.js"></script>
 *   <script src="/civic/akim/akim.js"></script>
 *   BirgeAkim.mount(document.getElementById("akim"), { apiBase: "/api/civic/v2" });
 *   Опции: mapHref, syncUrl, refreshMs (тихое обновление, 0 — выкл.), titleTag ("h1"; в оболочке со своим h1 — "h2"),
 *   objectHref (null — строки объектов не ссылки; "/#object={id}" — открыть объект на карте, событие "birge:open-object").
 *
 * Данные: GET {apiBase}/akim/summary?date=YYYY-MM-DD&district=<id> (ui/civic_akim, R08). Все числа
 * считает сервер; здесь только показ. Текст сводки приходит сразу на ru и kk — смена языка без запроса.
 *
 * Переход на карту: клик по горячему месту → событие "birge:open-target" {target, days} (отменяемое:
 * оболочка R01 может открыть цель у себя и вызвать preventDefault). Иначе — ссылка opts.mapHref
 * (по умолчанию "/#target={kind}:{id}&days={days}").
 *
 * Тексты: только ключи общего словаря R11 (web/civic/i18n, ветка claude/r14-R11) — свой akim.i18n.json
 * больше не нужен, все ключи akim.* перенесены R11 (UX_REVIEW, день 2).
 * Волна 2 (схема R11 IA_WAVE2 §5): «Нужно решение акима» (нет случаев — блока нет), «Пульс района»
 * (нет тревог — одна строка), вторая строка плитки «Исправлено» (akim.verify.split). Ключи, которых в словаре
 * R11 ещё нет, — в WAVE2_KEYS ниже (запасной текст до слияния; список для R11 — INTEGRATION.txt §8).
 * «Выбрать» вариант: POST {apiBase}/akim/decisions/<id> {option}, сотрудник, X-CSRF-Token как у R05/R06.
 * FINAL-3, чистый дизайн (R11 CLEAN_PASS §3 R08): заголовок 28/600 и одна строка мета; «данные — пример» — серая
 * строка внизу экрана (.bk-footnote); дата и район — поля с заливкой (.bk-field), «Распечатать» — .bk-btn--ghost;
 * KPI без карточек: число, подпись, ОДНА строка изменения, остальное — в «Подробнее» (.bk-details); «Коротко о дне» —
 * обычный абзац 17; «Нужно решение» — список с разделителями, «Выбрать» — .bk-btn--ghost, выбранный — точка + слово;
 * пустые блоки не показываем (ни «Резких всплесков нет», ни «Пока пусто»).
 */
(function (root) {
  "use strict";

  var DEFAULTS = {
    apiBase: "/api/civic/v2",
    mapHref: "/#target={kind}:{id}&days={days}",
    // Объект R06 → карта с его карточкой и этапами, напр. "/#object={id}". По умолчанию выключено: в оболочке Birge
    // (FINAL 0a7a346) выбор по #object= не показывает карточку с этапами — переход был бы «в никуда». R01 включит,
    // когда карточка объекта будет видна (INTEGRATION 4е).
    objectHref: null,
    syncUrl: true, // хранить дату и район в адресе: F5, печать и ссылка показывают то же
    refreshMs: 120000, // тихое обновление, пока вкладка видна (0 — выключить)
    titleTag: "h1", // в оболочке со своим h1 передайте "h2" — на странице будет один заголовок первого уровня
    weekHref: "/civic/akim/week.html", // раунд 15: «Картина недели» (отчёт A4)
  };
  var STALE_ON_RETURN_MS = 60000; // вернулись на вкладку, а данным больше минуты — обновить
  var TIMEOUT_MS = 15000;
  var LATE_VISIBLE = 5;
  var ASTANA_OFFSET_MS = 5 * 3600 * 1000; // весь Казахстан — UTC+5 с 1 марта 2024
  var DISTRICT_IDS = ["almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"];

  var doc = root.document;
  var scriptBase = ((doc.currentScript && doc.currentScript.src) || "").replace(/[^/]*$/, "");
  var ICONS = scriptBase + "../ui-kit/icons.svg";
  var STAGES = ["planned", "design", "procurement", "construction", "acceptance", "operating"];

  // ───────────── перевод ─────────────

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
  // Ключи волны 2, которых ещё нет в словаре R11: показываем этот текст, пока R11 не добавит ключ к себе.
  // Как только ключ есть в словаре — берётся словарь (вычитанный kk), этот запас не используется.
  var WAVE2_KEYS = {
    ru: {
      "akim.pulse.spike_new": "{category} · {district}: новое",
      "akim.pulse.spike_city": { one: "{category}: всплеск в {n} районе, ×{k}", few: "{category}: всплеск в {n} районах, ×{k}", many: "{category}: всплеск в {n} районах, ×{k}" },
      "akim.pulse.reason.spike": { one: "{n} сообщение за 7 дней, обычно {base} в неделю", few: "{n} сообщения за 7 дней, обычно {base} в неделю", many: "{n} сообщений за 7 дней, обычно {base} в неделю" },
      "akim.pulse.reason.spike_new": { one: "{n} сообщение за 7 дней, раньше — ни одного", few: "{n} сообщения за 7 дней, раньше — ни одного", many: "{n} сообщений за 7 дней, раньше — ни одного" },
      "akim.pulse.reason.city": "Больше всего: {list}",
      "akim.pulse.reason.new_hot": { one: "{n} человек за 7 дней, неделю назад места на карте не было", few: "{n} человека за 7 дней, неделю назад места на карте не было", many: "{n} человек за 7 дней, неделю назад места на карте не было" },
      "akim.pulse.reason.metoo": "Неделей раньше — {n}",
      "akim.pulse.more": { one: "Ещё {n} тревога", few: "Ещё {n} тревоги", many: "Ещё {n} тревог" },
      "akim.overdue.longest": "Дольше всех: {place}",
      "akim.decision.no_options": "Варианты не предложены — служба должна их подготовить",
      "akim.decision.forbidden": "Выбрать вариант может только сотрудник акимата",
      "akim.decision.save_error": "Выбор не сохранился — попробуйте ещё раз",
      "akim.empty.yesterday": "Показать вчера",
      // Раунд 15, «Картина дня» 2.0 (R11 IA_ROUND15 §5.10)
      "akim.decision.more": "Подробнее",
      "akim.crisis.open": "Открыть кризисный штаб",
      "akim.trio.open": "Открыть",
      "akim.trio.support": "Поддержать",
      "akim.trio.agencies": "Ведомства",
      "akim.trio.agencies_num": { one: "совместное обращение за неделю", few: "совместных обращения за неделю", many: "совместных обращений за неделю" },
      "akim.trio.agencies_lagging": "Больше всего просроченных ответов: {list}",
      "akim.trio.agencies_handoffs": { one: "{n} передача между службами", few: "{n} передачи между службами", many: "{n} передач между службами" },
      "akim.trio.agencies_staff": "Табло служб видно сотрудникам акимата: аватар → «Для сотрудников».",
      "akim.trio.together": "Жители вместе",
      "akim.trio.together_num": { one: "дело соседей впереди", few: "дела соседей впереди", many: "дел соседей впереди" },
      "akim.trio.together_people": { one: "{n} сосед придёт", few: "{n} соседа придут", many: "{n} соседей придут" },
      "akim.trio.together_done": { one: "Сделано вместе: {n} дело", few: "Сделано вместе: {n} дела", many: "Сделано вместе: {n} дел" },
      "akim.trio.together_none": "Ближайших дел пока нет",
      "akim.trio.together_now": "идёт сейчас",
      "akim.pulse.title_city": "Пульс города",
      "akim.trio.meetings": "Встречи",
      "akim.trio.meetings_num": { one: "поручение в работе", few: "поручения в работе", many: "поручений в работе" },
      "akim.trio.meetings_overdue": "Просрочено: {n}",
      "akim.trio.meetings_done": "Сделано: {n} из {total}",
      "akim.trio.meetings_next": "Следующая встреча: {date}",
      "akim.trio.due": "срок {date}",
      "akim.forecast.week": "Прогноз на неделю",
      "akim.forecast.month": "Прогноз на месяц",
      "akim.forecast.badge": "прототип",
      "akim.forecast.note": "Прототип: модель обучена на синтетической истории, это не настоящая оценка риска.",
      "akim.week.open": "Картина недели",
    },
    kk: {
      "akim.pulse.spike_new": "{category} · {district}: жаңа",
      "akim.pulse.spike_city": "{category}: {n} ауданда күрт өсу, ×{k}",
      "akim.pulse.reason.spike": "7 күнде {n} хабарлама, әдетте аптасына {base}",
      "akim.pulse.reason.spike_new": "7 күнде {n} хабарлама, бұрын бірде-бір болмаған",
      "akim.pulse.reason.city": "Ең көбі: {list}",
      "akim.pulse.reason.new_hot": "7 күнде {n} адам, бір апта бұрын бұл орын картада болмаған",
      "akim.pulse.reason.metoo": "Алдыңғы аптада — {n}",
      "akim.pulse.more": "Тағы {n}",
      "akim.overdue.longest": "Ең ұзақ кешіккені: {place}",
      "akim.decision.no_options": "Нұсқалар ұсынылмаған — оларды қызмет дайындауы керек",
      "akim.decision.forbidden": "Нұсқаны тек әкімдік қызметкері таңдай алады",
      "akim.decision.save_error": "Таңдау сақталмады — қайталап көріңіз",
      "akim.empty.yesterday": "Кешегі күнді көрсету",
      "akim.decision.more": "Толығырақ",
      "akim.crisis.open": "Дағдарыс штабын ашу",
      "akim.trio.open": "Ашу",
      "akim.trio.support": "Қолдау",
      "akim.trio.agencies": "Ведомстволар",
      "akim.trio.agencies_num": "апта ішіндегі бірлескен өтініш",
      "akim.trio.agencies_lagging": "Жауап мерзімі өткені көп: {list}",
      "akim.trio.agencies_handoffs": "Қызметтер арасында берілгені: {n}",
      "akim.trio.agencies_staff": "Қызметтер тақтасы әкімдік қызметкерлеріне көрінеді: аватар → «Қызметкерлерге».",
      "akim.trio.together": "Тұрғындар бірге",
      "akim.trio.together_num": "алдағы көршілер ісі",
      "akim.trio.together_people": "{n} көрші келеді",
      "akim.trio.together_done": "Бірге атқарылды: {n}",
      "akim.trio.together_none": "Жақын арада іс жоқ",
      "akim.trio.together_now": "қазір өтіп жатыр",
      "akim.pulse.title_city": "Қала пульсі",
      "akim.trio.meetings": "Кездесулер",
      "akim.trio.meetings_num": "орындалудағы тапсырма",
      "akim.trio.meetings_overdue": "Мерзімі өткені: {n}",
      "akim.trio.meetings_done": "Орындалды: {n}/{total}",
      "akim.trio.meetings_next": "Келесі кездесу: {date}",
      "akim.trio.due": "мерзімі {date}",
      "akim.forecast.week": "Апталық болжам",
      "akim.forecast.month": "Айлық болжам",
      "akim.forecast.badge": "прототип",
      "akim.forecast.note": "Прототип: модель синтетикалық тарихта оқытылған, бұл нақты тәуекел бағасы емес.",
      "akim.week.open": "Апта қорытындысы",
    },
  };
  function wave2(key, params) {
    var l = lang() === "kk" ? "kk" : "ru";
    var v = WAVE2_KEYS[l][key];
    if (v == null) return null;
    if (typeof v === "object") {
      var n = params && params.n != null ? Number(params.n) : 0;
      var cat = I() ? I().plural(l, n) : "many";
      v = v[cat] || v.other || v.many || v.few || v.one;
    }
    return interpolate(v, params);
  }
  function tr(key, params) {
    var i18n = I();
    if (!i18n) return wave2(key, params) || interpolate(key, params);
    if (!i18n.has(key) && !i18n.has(key, "ru") && WAVE2_KEYS.ru[key] != null) return wave2(key, params);
    var t = i18n.t(key, params);
    // Ключ словаря с тем же именем, но другим смыслом (ждёт подстановку, которой нет) — свой текст раунда 15.
    if (/\{[A-Za-z_]+\}/.test(t) && WAVE2_KEYS.ru[key] != null) return wave2(key, params);
    return t;
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
  function icon(name, size) {
    var svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "ic" + (size ? " ic--" + size : ""));
    svg.setAttribute("aria-hidden", "true");
    var use = doc.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", ICONS + "#i-" + name);
    svg.appendChild(use);
    return svg;
  }
  // Поправка П1 (раунд 15, «без ИИ-слопа»): в пустых состояниях и ошибках — одна маленькая монохромная иконка
  // набора ui-kit (40 px, линия той же толщины, что у значков), а не большая иллюстрация.
  function stateIcon(name) {
    var svg = svgEl("svg", { class: "ic akim-state-ic", "aria-hidden": "true", focusable: "false" });
    svg.appendChild(svgEl("use", { href: ICONS + "#i-" + name }));
    return svg;
  }
  function svgEl(tag, attrs) {
    var el = doc.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.keys(attrs || {}).forEach(function (k) {
      el.setAttribute(k, attrs[k]);
    });
    return el;
  }
  // Мини-график под числом (дизайн-марафон): 14 дней, последний — сегодня. Шкала от нуля — маленькое изменение
  // не выглядит обвалом. Только для глаза (aria-hidden): словами изменение уже сказано строкой под числом.
  function sparkline(series) {
    if (!series || series.length < 2) return null;
    var W = 160, H = 36, pad = 3;
    var max = Math.max.apply(null, series) || 1;
    var step = (W - 2 * pad) / (series.length - 1);
    var pts = series.map(function (v, i) {
      return [pad + i * step, H - pad - (Math.max(0, v) / max) * (H - 2 * pad)];
    });
    var line = pts
      .map(function (p, i) {
        return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1);
      })
      .join("");
    var last = pts[pts.length - 1];
    var svg = svgEl("svg", { class: "akim-spark", viewBox: "0 0 " + W + " " + H, "aria-hidden": "true", focusable: "false" });
    svg.appendChild(svgEl("path", { class: "akim-spark__area", d: line + "L" + last[0].toFixed(1) + " " + (H - pad) + "L" + pad + " " + (H - pad) + "Z" }));
    svg.appendChild(svgEl("path", { class: "akim-spark__line", d: line, pathLength: "1" }));
    svg.appendChild(svgEl("circle", { class: "akim-spark__dot", cx: last[0].toFixed(1), cy: last[1].toFixed(1), r: "3" }));
    return svg;
  }
  // Контуры районов для мини-карты «Горячих мест» (дизайн-марафон): data/civic/astana/geofence.json — OpenStreetMap,
  // ODbL, не официальная граница; упрощено до ~1 px при ширине 240 (проекция: долгота × cos широты). Только для глаза.
  var ASTANA_OUTLINE = {
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
      saryarka: "M61 126L75 127L80 131L86 129L89 134L90 133L87 117L94 116L97 112L63 96L57 88L36 78L35 79L18 71L11 85L13 85L10 94L8 95L11 97L9 101L11 103L10 103L16 109L18 107L20 109L25 110L31 109L34 113L43 117L46 117L48 120L52 119L59 126Z"
    },
  };
  function project(lonlat) {
    var b = ASTANA_OUTLINE.box;
    if (!lonlat || lonlat[0] < b[0] || lonlat[0] > b[2] || lonlat[1] < b[1] || lonlat[1] > b[3]) return null;
    return [(lonlat[0] - b[0]) * ASTANA_OUTLINE.k, (b[3] - lonlat[1]) * ASTANA_OUTLINE.sy];
  }
  function todayAstana() {
    return new Date(Date.now() + ASTANA_OFFSET_MS).toISOString().slice(0, 10);
  }
  function yesterdayAstana() {
    return new Date(Date.now() + ASTANA_OFFSET_MS - 86400000).toISOString().slice(0, 10);
  }
  // Подпись на текущем языке: label_kk / title_kk, если есть, иначе русская.
  // kindPrefix: если казахского названия нет (сервер ставит title_kk_missing), в ҚАЗ показываем вид объекта
  // по-казахски из словаря R11 («object.kind.roadworks» → «Жол жөндеу»), а не русскую строку (R10 B-018).
  function label(obj, base, kindPrefix) {
    var l = lang();
    if (!obj) return "";
    if (l !== "ru" && obj[base + "_" + l + "_missing"] && kindPrefix && obj.kind && I() && I().has(kindPrefix + obj.kind)) {
      return tr(kindPrefix + obj.kind);
    }
    return obj[base + "_" + l] || obj[base + "_ru"] || "";
  }
  function districtName(id) {
    return id ? tr("district." + id) : tr("akim.district.all_city");
  }

  // Изменение к прошлой неделе: стрелка (CSS) + слово. Цвет никогда не один.
  // «в 6,9 раза»: у дробных по-русски форма как у 2–4. В словаре R11 у akim.delta.ratio нет формы other,
  // а i18n.js для дробных берёт many («раз») — поэтому форму выбираем по 2 и подставляем настоящее число.
  // Когда R11 добавит ru other «в {n} раза больше» (INTEGRATION.txt п. 7), обход ничего не меняет.
  function ratioText(n) {
    if (n % 1 === 0 || lang() !== "ru") return tr("akim.delta.ratio", { n: n });
    var probe = tr("akim.delta.ratio", { n: 2 });
    return probe.indexOf(num(2)) >= 0 ? probe.replace(num(2), num(n)) : tr("akim.delta.ratio", { n: n });
  }
  function deltaText(ch) {
    if (!ch || ch.trend === "flat") return tr("akim.delta.same");
    if (ch.mode === "new") return tr("akim.delta.new");
    if (ch.mode === "ratio") return ratioText(ch.ratio);
    var v = ch.mode === "pct" ? I().formatPercent(ch.pct) : num(ch.abs);
    return tr(ch.trend === "up" ? "akim.delta.more" : "akim.delta.less", { v: v });
  }
  function deltaEl(ch, goodWhenUp) {
    var good = null;
    if (ch && ch.trend !== "flat" && goodWhenUp != null) good = (ch.trend === "up") === goodWhenUp;
    return h("span", {
      class: "bk-kpi__delta",
      "data-trend": ch ? ch.trend : "flat",
      "data-good": good == null ? null : String(good),
      text: deltaText(ch),
    });
  }
  function needsVs(ch) {
    return ch && ch.trend !== "flat" && ch.mode !== "new";
  }

  // ───────────── модуль ─────────────

  function mount(rootEl, options) {
    var opts = {};
    Object.keys(DEFAULTS).forEach(function (k) {
      opts[k] = options && options[k] != null ? options[k] : DEFAULTS[k];
    });
    var params = new URLSearchParams(root.location.search);
    var state = {
      date: /^\d{4}-\d{2}-\d{2}$/.test(params.get("date") || "") ? params.get("date") : null,
      district: DISTRICT_IDS.indexOf(params.get("district")) >= 0 ? params.get("district") : null,
      status: "loading",
      data: null,
      error: null,
      request: 0,
      keep: false, // смена даты/района при показанных числах: прежние приглушены, без скелета
      skeleton: false, // скелет показан (ответ дольше 150 мс)
      board: null, // раунд 15: блок «Ведомства» из GET akim/board (только сотрудник; R17 считает, R08 показывает)
      boardStatus: null, // 200 | 401/403 (нужен вход) | 0 (нет маршрута/связи) | null (ещё не спрашивали)
    };
    if (state.date && state.date > todayAstana()) state.date = null;

    rootEl.classList.add("akim");
    var top = h("div", { class: "akim__top" });
    var body = h("div", { class: "akim__body", "aria-live": "polite", "aria-busy": "true" });
    // Компактная стеклянная полоса раздела (дизайн-марафон): появляется, когда большой заголовок ушёл вверх, как в iOS;
    // нажатие — к началу «Картины дня». Диктору не нужна — заголовок и так первый (aria-hidden, без фокуса).
    var barBtn = h("button", {
      type: "button",
      class: "akim__bar-btn bk-glass bk-glass--bar",
      tabindex: "-1",
      onclick: function () {
        var still = root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches;
        top.scrollIntoView({ block: "start", behavior: still ? "auto" : "smooth" });
      },
    });
    var bar = h("div", { class: "akim__bar", "aria-hidden": "true" }, [barBtn]);
    rootEl.textContent = "";
    rootEl.appendChild(bar);
    rootEl.appendChild(top);
    rootEl.appendChild(body);
    var barIO = null;
    if (typeof root.IntersectionObserver === "function") {
      barIO = new root.IntersectionObserver(function (entries) {
        var e = entries[entries.length - 1];
        // Заголовок не виден и ушёл вверх (а не ещё не прокручен) — показываем полосу.
        var gone = !e.isIntersecting && e.boundingClientRect.bottom < (root.innerHeight || 800) / 2;
        if (gone) rootEl.setAttribute("data-scrolled", "");
        else rootEl.removeAttribute("data-scrolled");
      });
      barIO.observe(top);
    }

    function syncUrl() {
      if (!opts.syncUrl || !root.history || !root.history.replaceState) return;
      var q = new URLSearchParams(root.location.search);
      if (state.date && state.date !== todayAstana()) q.set("date", state.date);
      else q.delete("date");
      if (state.district) q.set("district", state.district);
      else q.delete("district");
      var s = q.toString();
      root.history.replaceState(root.history.state, "", root.location.pathname + (s ? "?" + s : "") + root.location.hash);
    }

    // silent: тихое обновление поверх показанных данных — без скелетона; при ошибке старые числа остаются.
    function load(silent) {
      silent = silent === true && state.status === "ok";
      var id = ++state.request;
      if (!silent) {
        // Дата или район сменились при показанных числах — не мигаем скелетом: прежние числа приглушены, под
        // заголовком тонкая полоса загрузки, потом новые мягко проявляются (дизайн-марафон, чек-лист п. 7–8).
        state.keep = state.status === "ok" && !!state.data;
        state.status = "loading";
        // Правило Linear 4: быстрый ответ — без мигания скелетом. Первые 150 мс — пустое тело, потом скелет.
        state.skeleton = false;
        setTimeout(function () {
          if (id === state.request && state.status === "loading" && !state.keep) {
            state.skeleton = true;
            render();
          }
        }, 150);
        render();
      }
      var q = new URLSearchParams();
      if (state.date) q.set("date", state.date);
      if (state.district) q.set("district", state.district);
      var ctrl = typeof AbortController === "function" ? new AbortController() : null;
      var timer = setTimeout(function () {
        if (ctrl) ctrl.abort();
      }, TIMEOUT_MS);
      fetch(opts.apiBase + "/akim/summary" + (q.toString() ? "?" + q : ""), {
        headers: { Accept: "application/json" },
        signal: ctrl ? ctrl.signal : undefined,
      })
        .then(function (r) {
          return r
            .json()
            .catch(function () {
              return null;
            })
            .then(function (b) {
              return { ok: r.ok, status: r.status, body: b };
            });
        })
        .then(function (res) {
          if (id !== state.request) return; // пришёл ответ на старый запрос
          if (silent) {
            if (res.ok && res.body && res.body.kpi) applySilent(res.body);
            return;
          }
          if (res.ok && res.body && res.body.kpi) {
            state.status = "ok";
            state.data = res.body;
            state.loadedAt = Date.now();
          } else {
            state.status = "error";
            state.error = res.status === 400 && res.body && res.body.field === "date" ? "date" : "server";
          }
        })
        .catch(function () {
          if (id !== state.request || silent) return; // тихое обновление не сменяет числа ошибкой
          state.status = "error";
          state.error = "network";
        })
        .then(function () {
          clearTimeout(timer);
          if (id === state.request && !silent) {
            state.keep = false;
            render();
          }
          if (id === state.request && state.status === "ok") loadBoard(id);
        });
    }

    // «Ведомства» (раунд 15): табло служб R17 — только сотруднику, поэтому отдельным запросом к akim/board.
    // Нет входа (401/403) — карточка подсказывает, как войти; нет маршрута или связи — карточки нет. Числа «Картины
    // дня» от этого не зависят. Прошедший день — табло не спрашиваем (R17 знает только «сейчас»).
    function loadBoard(id) {
      if (state.date) {
        state.board = null;
        state.boardStatus = null;
        return;
      }
      var q = state.district ? "?district=" + encodeURIComponent(state.district) : "";
      fetch(opts.apiBase + "/akim/board" + q, { headers: { Accept: "application/json" }, credentials: "same-origin" })
        .then(function (r) {
          return r.json().catch(function () { return null; }).then(function (b) { return { status: r.status, body: b }; });
        })
        .then(function (res) {
          if (id !== state.request) return;
          var services = res.status === 200 && res.body && res.body.services ? res.body.services : null;
          var status = res.status === 200 ? 200 : res.status === 401 || res.status === 403 ? 403 : 0;
          if (status === state.boardStatus && JSON.stringify(services) === JSON.stringify(state.board)) return;
          state.board = services;
          state.boardStatus = status;
          keepPlace(render);
        })
        .catch(function () {
          if (id !== state.request || state.boardStatus === 0) return;
          state.board = null;
          state.boardStatus = 0;
          keepPlace(render);
        });
    }
    // Перерисовать, не сдвинув экран и не потеряв фокус (как тихое обновление).
    function keepPlace(fn) {
      var key = focusKey();
      var y = root.scrollY;
      fn();
      if (key) {
        var again = rootEl.querySelector(key);
        if (again) again.focus({ preventScroll: true });
      }
      if (root.scrollY !== y) root.scrollTo(root.scrollX, y);
    }

    // Новые данные при тихом обновлении: перерисовываем, только если что-то изменилось (иначе — лишь «Данные на …»),
    // и возвращаем фокус туда же — экран не прыгает под руками.
    function sameData(a, b) {
      function strip(d) {
        var c = {};
        Object.keys(d || {}).forEach(function (k) {
          if (["generated_at", "as_of", "compare_to", "compute_ms"].indexOf(k) < 0) c[k] = d[k];
        });
        return JSON.stringify(c);
      }
      return strip(a) === strip(b);
    }
    function focusKey() {
      var el = doc.activeElement;
      if (!el || el === doc.body || !rootEl.contains(el)) return null;
      return el.id ? "#" + el.id : el.getAttribute("data-key") ? '[data-key="' + el.getAttribute("data-key") + '"]' : null;
    }
    function applySilent(data) {
      var changed = !sameData(state.data, data);
      state.data = data;
      state.loadedAt = Date.now();
      if (!changed) {
        renderTop();
        return;
      }
      var key = focusKey();
      var y = root.scrollY;
      render();
      if (key) {
        var again = rootEl.querySelector(key);
        if (again) again.focus({ preventScroll: true });
      }
      if (root.scrollY !== y) root.scrollTo(root.scrollX, y);
    }
    function refreshIfVisible() {
      if (doc.visibilityState === "hidden" || state.status !== "ok") return;
      load(true);
    }
    function onVisible() {
      if (doc.visibilityState === "visible" && state.status === "ok" && Date.now() - (state.loadedAt || 0) > STALE_ON_RETURN_MS)
        load(true);
    }
    var refreshTimer = opts.refreshMs > 0 ? setInterval(refreshIfVisible, opts.refreshMs) : null;
    doc.addEventListener("visibilitychange", onVisible);

    function setDate(value) {
      var today = todayAstana();
      state.date = !value || value >= today ? null : value;
      syncUrl();
      load();
    }
    function setDistrict(value) {
      state.district = DISTRICT_IDS.indexOf(value) >= 0 ? value : null;
      syncUrl();
      load();
    }

    // ── шапка страницы: заголовок, дата, район, печать ──
    function renderTop() {
      var d = state.data;
      var date = state.date || todayAstana();
      var isToday = date === todayAstana();
      top.textContent = "";
      var meta = [districtName(state.district)];
      if (d && state.status === "ok") {
        meta.push(d.is_today ? tr("akim.updated", { time: I().formatTime(d.as_of) }) : tr("akim.updated_end"));
        meta.push(tr("akim.compare_to", { date: I().formatDate(d.compare_to) }));
      }
      var title = h("div", { class: "akim__titlebox" }, [
        h(/^h[1-3]$/.test(opts.titleTag) ? opts.titleTag : "h1", { class: "akim__title" }, [
          tr("akim.title") + " ",
          // На телефоне дата — своей строкой и без точки (иначе в ҚАЗ строка начиналась с «· 12 қазан»).
          h("span", { class: "akim__title-date" }, [h("span", { class: "akim__title-sep", text: "· " }), I().formatDate(date)]),
        ]),
        // Одна строка мета 13 серым; «данные — пример» — серой строкой внизу экрана (CLEAN_PASS §3 R08 п. 1).
        h("p", { class: "akim__meta bk-meta", text: meta.join(" · ") }),
      ]);

      var dateInput = h("input", {
        type: "date",
        id: "akim-date",
        value: date,
        max: todayAstana(),
        onchange: function (e) {
          setDate(e.target.value);
        },
      });
      var districtSelect = h(
        "select",
        {
          id: "akim-district",
          onchange: function (e) {
            setDistrict(e.target.value);
          },
        },
        [h("option", { value: "", text: districtName(null) })].concat(
          DISTRICT_IDS.map(function (id) {
            return h("option", { value: id, text: tr("district." + id), selected: state.district === id });
          })
        )
      );
      var controls = h("div", { class: "akim__controls" }, [
        h("label", { class: "bk-field akim__field", for: "akim-date" }, [h("span", { class: "akim__field-label", text: tr("akim.date") }), dateInput]),
        isToday
          ? null
          : h("button", {
              type: "button",
              class: "bk-btn akim__today",
              text: tr("akim.date.today"),
              onclick: function () {
                setDate(null);
              },
            }),
        h("label", { class: "bk-field akim__field", for: "akim-district" }, [
          h("span", { class: "akim__field-label", text: tr("heat.filter.district") }),
          districtSelect,
        ]),
        h(
          "button",
          {
            type: "button",
            class: "bk-btn bk-btn--ghost akim__print",
            onclick: function () {
              printPage();
            },
          },
          [icon("print"), tr("common.action.print")]
        ),
      ]);
      top.appendChild(title);
      top.appendChild(controls);
      barBtn.textContent = tr("akim.title") + " · " + I().formatDate(date) + (state.district ? " · " + districtName(state.district) : "");
    }

    // ── состояния ──
    // Загрузка — скелет той же формы, что экран: 4 числа с подписью и графиком, абзац сводки, первый блок
    // (дизайн-марафон, чек-лист п. 8). Слова «Собираем картину дня…» — для чтения с экрана.
    function renderLoading() {
      var kpis = h("div", { class: "bk-kpis akim-kpis akim-skel", "aria-hidden": "true" });
      for (var i = 0; i < 4; i++)
        kpis.appendChild(
          h("div", { class: "bk-kpi akim-kpi" }, [
            h("span", { class: "bk-skel akim-skel__num" }),
            h("span", { class: "bk-skel bk-skel--line akim-skel__label" }),
            h("span", { class: "bk-skel bk-skel--line akim-skel__delta" }),
            h("span", { class: "bk-skel akim-skel__spark" }),
          ])
        );
      body.appendChild(kpis);
      body.appendChild(
        h("div", { class: "akim-skel akim-skel__summary", "aria-hidden": "true" }, [
          h("span", { class: "bk-skel bk-skel--line" }),
          h("span", { class: "bk-skel bk-skel--line" }),
          h("span", { class: "bk-skel bk-skel--line" }),
        ])
      );
      body.appendChild(
        h("div", { class: "bk-card akim-card akim-loading" }, [
          h("span", { class: "bk-skel bk-skel--title", "aria-hidden": "true" }),
          h("span", { class: "bk-skel bk-skel--line", "aria-hidden": "true" }),
          h("span", { class: "bk-skel bk-skel--line", "aria-hidden": "true" }),
          h("p", { class: "bk-sr-only", role: "status", text: tr("akim.loading") }),
        ])
      );
    }
    function renderError() {
      var kind = state.error;
      // Как у остальных разделов (R11 марафон §10.2): без карточки (на стекле листа и так подложка), иллюстрация
      // ui-kit, «Повторить» — обычная кнопка (главное на экране — сами данные, а не повтор).
      var box = h("div", { class: "akim-card akim-error" }, [
        h("div", { class: "bk-error", role: "alert" }, [
          stateIcon(kind === "network" ? "wifi-off" : kind === "date" ? "calendar" : "info"),
          h("p", {
            class: "bk-error__title",
            text: kind === "network" ? tr("common.state.network_title") : kind === "date" ? tr("akim.bad_date") : tr("common.state.error_title"),
          }),
          kind === "date"
            ? null
            : h("p", { class: "bk-error__text", text: kind === "network" ? tr("common.state.network_text") : tr("common.state.error_text") }),
          h(
            "button",
            {
              type: "button",
              class: "bk-btn",
              onclick: function () {
                if (kind === "date") setDate(null);
                else load();
              },
            },
            kind === "date" ? [tr("akim.date.today")] : [icon("refresh"), tr("common.action.retry")]
          ),
        ]),
      ]);
      body.appendChild(box);
    }

    // ── четыре крупных числа ──
    // Чистый дизайн: число 28/600, подпись 15 и ОДНА строка изменения 13 («▲ больше на 41 %»). «С чем сравниваем»
    // показано один раз — строкой под заголовком («сравнение с 5 окт»), а не в каждой плитке; для чтения с экрана
    // слова «чем неделю назад» остаются (скрытым текстом .bk-sr-only).
    function kpiCard(kind, ch, labelKey, goodWhenUp) {
      var delta = deltaEl(ch, goodWhenUp);
      if (needsVs(ch)) delta.appendChild(h("span", { class: "bk-sr-only", text: " " + tr("akim.delta.vs_week") }));
      return h("article", { class: "bk-kpi akim-kpi", "data-kind": kind }, [
        h("span", { class: "bk-kpi__value", text: num(ch.value) }),
        h("span", { class: "bk-kpi__label", text: tr(labelKey) }),
        delta,
        sparkline(ch.series),
      ]);
    }
    function renderKpis(d) {
      var k = d.kpi;
      return h("section", { class: "bk-kpis akim-kpis", "aria-label": tr("akim.title") }, [
        kpiCard("new", k.new_day, "akim.kpi.new", false),
        kpiCard("in_progress", k.in_progress, "akim.kpi.in_progress", null),
        kpiCard("overdue", k.overdue, "akim.kpi.overdue", false),
        kpiCard("fixed", k.fixed_week, "akim.kpi.fixed_week", true),
      ]);
    }
    // Остальное о числах — в «Подробнее» под плитками (CLEAN_PASS §3 R08 п. 3): за 7 дней, ждут ответа, самое давнее
    // просроченное место (волна мелочей п. 6), «служба сообщила · жители проверили · вернули» (волна 2 п. 1).
    function renderKpiMore(d) {
      var k = d.kpi;
      var rows = [];
      rows.push(h("li", { "data-kind": "new" }, [tr("akim.kpi.week", { n: k.new_week.value }) + " · ", deltaEl(k.new_week, false)]));
      if (k.in_progress.waiting) rows.push(h("li", { "data-kind": "in_progress", text: tr("akim.kpi.waiting", { n: k.in_progress.waiting }) }));
      var o = d.overdue && d.overdue.items && d.overdue.items[0];
      if (o)
        rows.push(
          h("li", { "data-kind": "overdue" }, [
            tr("akim.overdue.longest", { place: placeName(o) }) + " · ",
            h("span", { class: "akim-late-days", text: timerText(o.timer) }),
          ])
        );
      if (k.verification_available)
        rows.push(h("li", { "data-kind": "fixed", text: tr("akim.verify.split", { a: k.fixed_week.awaiting, b: k.fixed_week.verified, c: k.fixed_week.reopened || 0 }) }));
      return h("details", { class: "bk-details akim-kpi-more" }, [
        h("summary", { "data-key": "kpi-more", text: tr("common.action.more") }),
        h("ul", { class: "akim-kpi-more__list" }, rows),
      ]);
    }
    function placeName(x) {
      var l = lang();
      if (x["place_" + l] || x.place_ru) return x["place_" + l] || x.place_ru;
      if (x.subtopic && x.subtopic.id) return tr("subtopic." + x.subtopic.id);
      return x.category ? I().cat(x.category) : "";
    }
    function timerText(t) {
      if (!t) return "";
      if (t.state === "overdue") return tr("deadline.overdue", { n: t.overdue_by });
      if (t.state === "today") return tr("deadline.today");
      return tr("deadline.left", { n: t.left });
    }
    function serviceName(svc) {
      if (!svc) return "";
      if (svc.name_edited) return svc[lang()] || svc.ru; // акимат переименовал службу — его название как есть
      return I() && I().has("service." + svc.id) ? tr("service." + svc.id) : svc[lang()] || svc.ru;
    }

    // ── «Нужно решение акима» (волна 2 п. 5) ──
    var csrfCache = null;
    function csrf() {
      try {
        var shell = root.CivicShell && typeof root.CivicShell.csrfToken === "function" ? root.CivicShell.csrfToken() : null;
        if (shell) return Promise.resolve(shell);
      } catch (e) {
        /* оболочки нет */
      }
      if (csrfCache) return Promise.resolve(csrfCache);
      return fetch("/api/civic/v1/session", { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) {
          return r.json();
        })
        .then(function (b) {
          var data = b && b.data && typeof b.data === "object" ? b.data : b || {};
          csrfCache = data.authenticated && typeof data.csrf_token === "string" ? data.csrf_token : null;
          return csrfCache;
        })
        .catch(function () {
          return null;
        });
    }
    var justChosen = null;
    function chooseOption(item, n, statusEl) {
      statusEl.textContent = "";
      return csrf()
        .then(function (token) {
          var headers = { Accept: "application/json", "Content-Type": "application/json" };
          if (token) headers["X-CSRF-Token"] = token;
          return fetch(opts.apiBase + "/akim/decisions/" + encodeURIComponent(item.id), {
            method: "POST",
            credentials: "same-origin",
            headers: headers,
            body: JSON.stringify({ option: n }),
          });
        })
        .then(function (r) {
          if (r.ok) {
            item.chosen = { option: n };
            justChosen = item.id; // подтверждение мягко «проявится» один раз — сразу после нажатия
            render();
            justChosen = null;
            var again = rootEl.querySelector('[data-key="decision:' + item.id + '"]');
            if (again) again.focus({ preventScroll: true });
            load(true);
            return;
          }
          statusEl.textContent = tr(r.status === 401 || r.status === 403 ? "akim.decision.forbidden" : "akim.decision.save_error");
        })
        .catch(function () {
          statusEl.textContent = tr("akim.decision.save_error");
        });
    }
    function renderDecisions(d) {
      var items = (d.decisions && d.decisions.items) || [];
      if (!items.length) return null; // нет случаев — блока нет (IA_WAVE2 §5)
      var card = h("section", { class: "bk-card akim-card akim-decisions", "aria-labelledby": "akim-decisions-title" }, [
        h("h2", { class: "bk-h2", id: "akim-decisions-title", text: tr("akim.decision.title") }),
      ]);
      var list = h("ol", { class: "akim-decisions__list" });
      items.forEach(function (it) {
        var l = lang();
        var where = [placeName(it), it.district ? tr("district." + it.district) : null].filter(Boolean).join(" · ");
        var status = h("p", { class: "akim-decision__status", role: "status" });
        var opts2 = h("ol", { class: "akim-decision__options" });
        (it.options || []).forEach(function (o, i) {
          var n = i + 1;
          var chosen = it.chosen && it.chosen.option === n;
          opts2.appendChild(
            h("li", { class: "akim-decision__option" + (chosen ? " is-chosen" : "") }, [
              h("span", { class: "akim-decision__option-text", text: tr("akim.decision.option", { n: n, text: o[l] || o.ru }) }),
              chosen
                ? h("span", {
                    class: "bk-status akim-decision__chosen",
                    "data-status": "fixed",
                    "data-just": justChosen === it.id ? "" : null,
                    text: tr("akim.decision.chosen", { n: n }),
                  })
                : h("button", {
                    type: "button",
                    class: "bk-btn bk-btn--ghost akim-decision__choose",
                    "data-key": "decision:" + it.id + ":" + n,
                    "aria-label": tr("akim.decision.choose") + ": " + tr("akim.decision.option", { n: n, text: o[l] || o.ru }),
                    text: tr("akim.decision.choose"),
                    onclick: function () {
                      chooseOption(it, n, status);
                    },
                  }),
            ])
          );
        });
        // Раунд 15 (VISUAL_BRIEF §3): коротко — проблема → вариант → кнопка. Слева проблема одной строкой и где /
        // сколько просрочено / какая служба; справа два варианта с «Выбрать». «Что мешает», временная мера и «что нужно
        // от акима» — свёрнуты в «Подробнее» (ничего не потеряно, но на экране нет длинных абзацев).
        var more = [
          it.decision_ru ? h("p", { class: "akim-decision__needed", text: tr("akim.decision.needed", { text: it["decision_" + l] || it.decision_ru }) }) : null,
          it.blocker_ru ? h("p", { class: "akim-decision__blocker", text: tr("akim.decision.blocker", { text: it["blocker_" + l] || it.blocker_ru }) }) : null,
          it.temp_measure_ru ? h("p", { class: "bk-meta", text: tr("passport.temp_measure", { text: it["temp_measure_" + l] || it.temp_measure_ru }) }) : null,
        ].filter(Boolean);
        list.appendChild(
          h("li", { class: "akim-decision akim-decision--short", tabindex: "-1", "data-key": "decision:" + it.id }, [
            h("div", { class: "akim-decision__info" }, [
              h("p", { class: "akim-decision__problem" }, [h("strong", { text: it["problem_" + l] || it.problem_ru })]),
              h("p", { class: "akim-decision__meta bk-meta" }, [
                where ? where + " · " : "",
                h("span", { class: "akim-late-days", text: timerText(it.timer) }),
                " · " + tr("service.assigned", { service: serviceName(it.service) }),
              ]),
              more.length
                ? h("details", { class: "bk-details akim-decision__more" }, [h("summary", { "data-key": "decision-more:" + it.id, text: tr("akim.decision.more") })].concat(more))
                : null,
            ]),
            h("div", { class: "akim-decision__choice" }, [
              it.options && it.options.length ? opts2 : h("p", { class: "akim-decision__blocker bk-meta", text: tr("akim.decision.no_options") }),
              status,
            ]),
          ])
        );
      });
      card.appendChild(list);
      return card;
    }

    // ── «Пульс района» (волна 2 п. 8) ──
    function fmtK(k) {
      return num(k);
    }
    function pulseRow(a) {
      var l = lang();
      var cat = a.category ? I().cat(a.category) : "";
      var dist = a.district ? tr("district." + a.district) : "";
      var place = a.target ? label(a.target, "label") || (I().has("heat.kind." + a.target.kind) ? tr("heat.kind." + a.target.kind) : "") : "";
      var title, reason;
      if (a.kind === "spike") {
        title = tr("akim.pulse.spike", { category: cat, district: dist, k: fmtK(a.k) });
        reason = tr("akim.pulse.reason.spike", { n: a.value, base: num(a.base >= 3 ? Math.round(a.base) : a.base) });
      } else if (a.kind === "spike_new") {
        title = tr("akim.pulse.spike_new", { category: cat, district: dist });
        reason = tr("akim.pulse.reason.spike_new", { n: a.value });
      } else if (a.kind === "spike_city") {
        var names = (a.districts || []).slice(0, 3).map(function (x) {
          return tr("district." + x.district) + " — " + num(x.value);
        });
        title = tr("akim.pulse.spike_city", { category: cat, n: (a.districts || []).length, k: fmtK(a.k) });
        reason = tr("akim.pulse.reason.city", { list: names.join(", ") });
      } else if (a.kind === "new_hot") {
        title = tr("akim.pulse.new_hot", { place: place });
        reason = tr("akim.pulse.reason.new_hot", { n: a.value });
      } else {
        title = tr("akim.pulse.metoo_growth", { place: place, n: a.value });
        reason = tr("akim.pulse.reason.metoo", { n: a.prev || 0 });
      }
      var link = a.target
        ? h("a", {
            class: "akim-pulse__map",
            href: mapLink(a.target, (d0() && d0().hot && d0().hot.days) || 7),
            "data-key": "pulse:" + a.kind + ":" + (a.category || "") + ":" + (a.district || "") + ":" + a.target.id,
            onclick: function (e) {
              var ev = new CustomEvent("birge:open-target", { cancelable: true, detail: { target: a.target, days: 7, from: "akim-pulse" } });
              if (!doc.dispatchEvent(ev)) e.preventDefault();
            },
          }, [icon("pin", 18), tr("common.action.show_on_map")])
        : null;
      // Раунд 15: тревога «тема растёт» (снег, ЖКХ) или тревога в районе, где уже идёт кризис, — кнопка штаба R17.
      // Событие "birge:open-crisis" отменяемое: оболочка или R17 открывают штаб у себя; иначе — переход по ссылке.
      // Одна главная кнопка (VISUAL_BRIEF §2 п. 3): кнопка штаба — только у первой такой тревоги, у остальных — карта.
      var firstCrisis = ((d0() && d0().pulse && d0().pulse.items) || []).filter(function (x) { return x.crisis && x.crisis.link; })[0];
      var crisisBtn = a.crisis && a.crisis.link && firstCrisis === a
        ? h("a", {
            class: "bk-btn bk-btn--danger akim-pulse__crisis",
            href: a.crisis.link,
            "data-key": "crisis:" + a.kind + ":" + (a.category || "") + ":" + (a.district || ""),
            onclick: function (e) {
              var ev = new CustomEvent("birge:open-crisis", { cancelable: true,
                detail: { incident: a.crisis.incident, kind: a.crisis.kind, district: a.district || null, link: a.crisis.link } });
              if (!doc.dispatchEvent(ev)) e.preventDefault();
            },
          }, [icon("alert", 18), tr("akim.crisis.open")])
        : null;
      // Значок вида тревоги в мягком круге (дизайн-марафон): рост — график, новое место — метка, «Я тоже» — люди.
      var ic = a.kind === "new_hot" || a.kind === "spike_new" ? "pin" : a.kind === "metoo_growth" ? "users" : "chart";
      return h("li", { class: "akim-pulse__item", "data-kind": a.kind }, [
        h("span", { class: "akim-pulse__icon", "aria-hidden": "true" }, [icon(ic, 18)]),
        h("span", { class: "akim-pulse__title", text: title }),
        h("span", { class: "akim-pulse__reason bk-meta", text: reason }),
        crisisBtn || link,
      ]);
    }
    function d0() {
      return state.data;
    }
    function renderPulse(d) {
      var p = d.pulse;
      if (!p || !p.available) return null;
      var items = p.items || [];
      if (!items.length) return null; // пустое не показываем (CLEAN_PASS §2.6, §3 R08 п. 6)
      var card = h("section", { class: "bk-card akim-card akim-pulse", "aria-labelledby": "akim-pulse-title" }, [
        // Весь город — «Пульс города» (как на Ситуационном центре), выбран район — «Пульс района».
        h("h2", { class: "bk-h2", id: "akim-pulse-title", text: tr(state.district ? "akim.pulse.title" : "akim.pulse.title_city") }),
      ]);
      var first = h("ul", { class: "akim-pulse__list" });
      items.slice(0, 3).forEach(function (a) {
        first.appendChild(pulseRow(a));
      });
      card.appendChild(first);
      if (items.length > 3) {
        var rest = h("ul", { class: "akim-pulse__list" });
        items.slice(3).forEach(function (a) {
          rest.appendChild(pulseRow(a));
        });
        card.appendChild(
          h("details", { class: "bk-details akim-pulse__more" }, [h("summary", { text: tr("akim.pulse.more", { n: items.length - 3 }) }), rest])
        );
      }
      return card;
    }

    function cardHead(titleKey, hintKey, extra) {
      return h("div", { class: "akim-card__head" }, [
        h("h2", { class: "bk-h2", text: tr(titleKey) }),
        extra || null,
        hintKey ? h("p", { class: "akim-card__hint bk-meta", text: tr(hintKey) }) : null,
      ]);
    }
    function unavailable() {
      return h("div", { class: "akim-unavailable" }, [icon("alert"), h("span", { text: tr("akim.unavailable") })]);
    }

    // ── горячие места ──
    function mapLink(target, days) {
      return opts.mapHref
        .replace("{kind}", encodeURIComponent(target.kind))
        .replace("{id}", encodeURIComponent(target.id))
        .replace("{days}", String(days));
    }
    function renderHot(d) {
      var card = h("section", { class: "bk-card akim-card akim-hot", "aria-labelledby": "akim-hot-title" }, [cardHead("akim.hot.title", "akim.hot.hint")]);
      card.firstChild.firstChild.id = "akim-hot-title";
      if (!d.hot.available) {
        card.appendChild(unavailable());
        return card;
      }
      if (!d.hot.items.length) return null; // пустое не показываем
      var map = miniMap(d.hot.items, state.district);
      if (map) {
        card.classList.add("akim-hot--map");
        card.appendChild(map);
      }
      var list = h("ol", { class: "bk-list akim-hot__list" });
      d.hot.items.forEach(function (it) {
        // Подписи нет (новая цель без названия) — вид места из словаря R11, а не пустая строка.
        var name = label(it.target, "label") || (I() && I().has("heat.kind." + it.target.kind) ? tr("heat.kind." + it.target.kind) : "");
        // Волна мелочей п. 12: не просто «Дороги», а что именно — уточнение, которое чаще всего выбрали жители.
        var what = it.subtopic && it.subtopic.id ? tr("subtopic." + it.subtopic.id) : it.category ? I().cat(it.category) : null;
        var sub = [what, it.district ? tr("district." + it.district) : null].filter(Boolean).join(" · ");
        var a = h(
          "a",
          {
            class: "bk-list__item akim-hot__item",
            "data-key": "hot:" + it.target.kind + ":" + it.target.id,
            href: mapLink(it.target, d.hot.days),
            "aria-label": tr("akim.hot.open", { name: name }) + ". " + tr("common.people", { n: it.count }),
            onclick: function (e) {
              var ev = new CustomEvent("birge:open-target", { cancelable: true, detail: { target: it.target, days: d.hot.days, from: "akim" } });
              if (!doc.dispatchEvent(ev)) e.preventDefault(); // оболочка открыла цель сама
            },
          },
          [
            h("span", { class: "bk-heat", "data-level": String(it.level), "aria-hidden": "true", text: num(it.count) }),
            h("span", { class: "bk-list__main" }, [
              h("span", { class: "bk-list__title", text: name }),
              h("span", { class: "bk-list__sub akim-hot__sub" }, [
                sub,
                it.status && it.status !== "new" ? h("span", { class: "bk-status", "data-status": it.status, text: tr("status." + it.status) }) : null,
                it.approximate ? h("span", { class: "bk-tag bk-tag--approx", text: tr("common.tag.approx") }) : null,
              ]),
            ]),
            icon("chevron-right"),
          ]
        );
        // Строка списка ↔ точка на мини-карте: при наведении и фокусе точка крупнее и сверху. То же событие, что у сводки
        // «Сегодня в Астане» (birge:hover-target), — карта R07 под листом может подсветить значок (правило Linear 5).
        var dotKey = "dot:" + it.target.kind + ":" + it.target.id;
        var mark = function (on) {
          doc.dispatchEvent(new CustomEvent("birge:hover-target", { detail: { target: it.target, on: on, from: "akim" } }));
          var dot = map && map.querySelector('[data-key="' + dotKey.replace(/"/g, "") + '"]');
          if (!dot) return;
          if (on) {
            dot.parentNode.appendChild(dot);
            dot.setAttribute("data-active", "");
          } else dot.removeAttribute("data-active");
        };
        a.addEventListener("mouseenter", function () { mark(true); });
        a.addEventListener("mouseleave", function () { mark(false); });
        a.addEventListener("focus", function () { mark(true); });
        a.addEventListener("blur", function () { mark(false); });
        list.appendChild(h("li", null, [a]));
      });
      // ↑ ↓ и J K — по местам (правило Linear 2), фокус не уходит из списка.
      list.addEventListener("keydown", function (e) {
        var down = e.key === "ArrowDown" || e.key === "j" || e.key === "J";
        var up = e.key === "ArrowUp" || e.key === "k" || e.key === "K";
        if (!down && !up) return;
        var rows = Array.prototype.slice.call(list.querySelectorAll(".akim-hot__item"));
        var i = rows.indexOf(doc.activeElement);
        if (i < 0) return;
        e.preventDefault();
        rows[(i + (down ? 1 : rows.length - 1)) % rows.length].focus();
      });
      card.appendChild(list);
      return card;
    }
    // Мини-карта «Горячих мест»: контуры районов и точки мест цветом карты жалоб (top-3 — крупнее). Только для глаза:
    // всё то же есть в списке рядом; подпись OpenStreetMap — условие ODbL.
    function miniMap(items, district) {
      var O = ASTANA_OUTLINE;
      var svg = svgEl("svg", { class: "akim-minimap__svg", viewBox: "0 0 " + O.w + " " + O.h, focusable: "false", "aria-hidden": "true" });
      Object.keys(O.d).forEach(function (id) {
        svg.appendChild(svgEl("path", { class: "akim-minimap__district" + (district === id ? " is-current" : ""), d: O.d[id] }));
      });
      var dots = 0;
      items
        .slice()
        .reverse()
        .forEach(function (it) {
          var p = project(it.anchor);
          if (!p) return;
          dots++;
          svg.appendChild(
            svgEl("circle", {
              class: "akim-minimap__dot",
              cx: p[0].toFixed(1),
              cy: p[1].toFixed(1),
              r: it.rank <= 3 ? "9" : "6.5",
              "data-level": String(it.level),
              "data-key": "dot:" + it.target.kind + ":" + it.target.id,
            })
          );
        });
      if (!dots) return null;
      return h("figure", { class: "akim-minimap", "aria-hidden": "true" }, [svg, h("figcaption", { class: "akim-minimap__credit", text: "© OpenStreetMap" })]);
    }

    // ── темы и районы ──
    function bars(rows, opts2) {
      var max = rows.reduce(function (m, r) {
        return Math.max(m, r.value);
      }, 0);
      var ul = h("ul", { class: "bk-bars akim-bars" });
      rows.forEach(function (r) {
        var width = max ? Math.max(2, Math.round((r.value / max) * 100)) : 0;
        var inner = [
          h("span", { class: "bk-bar__label" }, [r.icon ? icon(r.icon, 18) : null, h("span", { text: r.name }), r.badge || null]),
          h("span", { class: "bk-bar__track", "aria-hidden": "true" }, [h("span", { class: "bk-bar__fill", style: "width:" + width + "%" })]),
          h("span", { class: "bk-bar__value", text: num(r.value) }),
        ];
        if (opts2 && opts2.onPick) {
          ul.appendChild(
            h("li", null, [
              h(
                "button",
                {
                  type: "button",
                  class: "bk-bar akim-bar-btn",
                  "data-key": "district:" + r.id,
                  "aria-pressed": r.selected ? "true" : "false",
                  "aria-label": tr("akim.districts.pick", { name: r.name }) + ": " + tr("common.people", { n: r.value }),
                  onclick: function () {
                    opts2.onPick(r.id);
                  },
                },
                inner
              ),
            ])
          );
        } else {
          ul.appendChild(h("li", { class: "bk-bar" }, inner));
        }
      });
      return ul;
    }
    function renderTopics(d) {
      var card = h("section", { class: "bk-card akim-card akim-topics" }, [cardHead("akim.topics.title", "akim.topics.hint")]);
      if (d.topics.available && !d.topics.items.length) return null; // пустое не показываем
      if (!d.topics.available) card.appendChild(unavailable());
      else
        card.appendChild(
          bars(
            d.topics.items.map(function (t) {
              return { name: I().cat(t.category), value: t.value, icon: t.icon };
            })
          )
        );
      return card;
    }
    function renderDistricts(d) {
      var card = h("section", { class: "bk-card akim-card akim-districts" }, [cardHead("akim.districts.title", "akim.districts.hint")]);
      if (!d.districts.available) {
        card.appendChild(unavailable());
        return card;
      }
      var anyDistrict = d.districts.items.some(function (r) {
        return r.value > 0;
      });
      if (!anyDistrict) return null; // все районы по нулям — блок не показываем
      card.appendChild(
        bars(
          d.districts.items.map(function (r) {
            var selected = d.districts.selected === r.district;
            return {
              id: r.district,
              name: tr("district." + r.district),
              value: r.value,
              selected: selected,
              badge: selected ? h("span", { class: "bk-tag akim-selected", text: tr("akim.districts.selected") }) : null,
            };
          }),
          {
            onPick: function (id) {
              setDistrict(state.district === id ? null : id);
            },
          }
        )
      );
      return card;
    }

    // ── объекты (R06) ──
    function objectRow(o) {
      var tags = [];
      // Отставание и «давно не обновлялось» — словами без плашек (дизайн-марафон: без бежевых плашек, CLEAN_PASS §2.2).
      if (o.delay_days > 0) tags.push(h("span", { class: "akim-obj__late", text: tr("object.late", { n: o.delay_days }) }));
      if (o.stale && o.days_since_update != null)
        tags.push(h("span", { class: "akim-stale", text: tr("object.stale_days", { n: o.days_since_update }) }));
      var title = label(o, "title", "object.kind.");
      var main = [h("span", { class: "bk-list__title", text: title })];
      if (o.district) main.push(h("span", { class: "bk-list__sub", text: tr("district." + o.district) }));
      main.push(stagesEl(o));
      var inner = [h("span", { class: "bk-list__main" }, main), h("span", { class: "akim-obj__tags" }, tags)];
      // Нет места на карте или оболочка не умеет показать объект — обычная строка.
      if (!opts.objectHref || !o.has_place || !o.id) return h("li", { class: "akim-obj" }, inner);
      // R11 (ночь 6, п. 4): строка нажимается, как «Горячие места», — карта с карточкой объекта и этапами.
      inner.push(icon("chevron-right"));
      return h("li", null, [
        h(
          "a",
          {
            class: "akim-obj akim-obj--link",
            "data-key": "object:" + o.id,
            href: opts.objectHref.replace("{id}", encodeURIComponent(o.id)),
            "aria-label": tr("akim.hot.open", { name: title }),
            onclick: function (e) {
              var ev = new CustomEvent("birge:open-object", { cancelable: true, detail: { id: o.id, from: "akim" } });
              if (!doc.dispatchEvent(ev)) {
                e.preventDefault(); // оболочка открыла объект сама
                return;
              }
              // Оболочка R01 разбирает #object=<id> (выбор на карте), но раздел «Картина дня» сама не закрывает.
              if (root.BirgeShell && typeof root.BirgeShell.setSection === "function") root.BirgeShell.setSection("map");
            },
          },
          inner
        ),
      ]);
    }
    // Полоса 6 этапов ui-kit (.bk-stages--compact) + «Этап 4 из 6: Строительство» — как в макете day.html.
    function stagesEl(o) {
      var at = STAGES.indexOf(o.stage);
      if (at < 0) return o.stage ? h("span", { class: "bk-list__sub", text: tr("akim.late.stage", { name: tr("stage." + o.stage) }) }) : null;
      var caption = tr("stage.caption", { i: at + 1, total: STAGES.length, name: tr("stage." + o.stage) });
      return h("span", { class: "akim-obj__stages" }, [
        h(
          "ol",
          { class: "bk-stages bk-stages--compact" + (o.delay_days > 0 ? " bk-stages--late" : ""), "aria-hidden": "true" },
          // Точки без скрытых подписей: полоса только для глаз (aria-hidden), этап словами — в подписи ниже.
          STAGES.map(function (st, i) {
            return h("li", { "data-state": i < at ? "done" : i === at ? "current" : "todo" });
          })
        ),
        h("span", { class: "bk-stages__caption", text: caption }),
      ]);
    }
    function renderObjects(d) {
      var o = d.objects || {};
      // Нет реестра R06 — блока нет (это не «карта жалоб не отвечает»).
      if (!o.available) return null;
      var card = h("section", { class: "bk-card akim-card akim-objects" }, [cardHead("akim.late.title", null)]);
      // Пустое не показываем: нет объектов или все по графику и все обновлялись — блока нет (CLEAN_PASS §3 R08 п. 6).
      if (!o.total || (!o.late.length && !o.stale.length)) return null;
      if (o.late.length) {
        var ul = h("ul", { class: "bk-list akim-obj__list" });
        o.late.slice(0, LATE_VISIBLE).forEach(function (x) {
          ul.appendChild(objectRow(x));
        });
        card.appendChild(ul);
      }
      var lateIds = o.late.slice(0, LATE_VISIBLE).map(function (x) {
        return x.id;
      });
      var staleOnly = o.stale.filter(function (x) {
        return lateIds.indexOf(x.id) < 0;
      });
      if (staleOnly.length) {
        card.appendChild(h("h3", { class: "akim-card__sub", text: tr("akim.late.stale_title") }));
        var ul2 = h("ul", { class: "bk-list akim-obj__list" });
        staleOnly.slice(0, LATE_VISIBLE).forEach(function (x) {
          ul2.appendChild(objectRow(x));
        });
        card.appendChild(ul2);
      }
      return card;
    }

    // ── предложения и голоса (R06) ──
    function renderProposals(d) {
      var p = d.proposals || {};
      var card = h("section", { class: "bk-card akim-card akim-proposals" }, [cardHead("akim.proposals.title", null)]);
      if (!p.available) return null; // нет данных R06 — блока нет
      if (!p.top.length) return null; // пустое не показываем
      card.appendChild(h("p", { class: "akim-proposals__new", text: tr("akim.proposals.new", { n: p.new_count }) }));
      var ul = h("ul", { class: "bk-list akim-obj__list" });
      p.top.forEach(function (x) {
        ul.appendChild(
          h("li", { class: "akim-obj" }, [
            h("span", { class: "bk-list__main" }, [
              h("span", { class: "bk-list__title" }, [
                label(x, "title", "proposal.kind."),
                x.is_new ? h("span", { class: "bk-tag bk-tag--project akim-new", text: tr("akim.proposals.new_badge") }) : null,
              ]),
              h("span", { class: "bk-list__sub", text: tr("akim.proposals.votes", { up: x.votes_up, down: x.votes_down }) }),
            ]),
          ])
        );
      });
      card.appendChild(ul);
      return card;
    }

    // ── «Картина дня» 2.0 (раунд 15): соседи — только показ, числа считают R17 / R16 / R13 ──
    function demoBadge(flag) {
      return flag && !(d0() && d0().demo && d0().demo.complaints) ? h("span", { class: "bk-tag bk-tag--demo", text: tr("common.demo") }) : null;
    }
    function trioCard(id, titleKey, number, numLabel, lines, link, linkKey, demo) {
      return h("section", { class: "bk-card akim-card akim-mini", "data-block": id, "aria-labelledby": "akim-mini-" + id }, [
        h("div", { class: "akim-mini__head" }, [h("h2", { class: "bk-h2", id: "akim-mini-" + id, text: tr(titleKey) }), demoBadge(demo)]),
        number == null ? null : h("p", { class: "akim-mini__num" }, [h("span", { class: "akim-mini__value", text: num(number) }),
          h("span", { class: "akim-mini__label", text: numLabel })]),
        h("div", { class: "akim-mini__lines" }, lines.filter(Boolean).slice(0, 2).map(function (t) {
          return typeof t === "string" ? h("p", { class: "akim-mini__line", text: t }) : t;
        })),
        link ? h("a", { class: "bk-btn bk-btn--ghost akim-mini__open", href: link, "data-key": "trio:" + id }, [tr(linkKey || "akim.trio.open"),
          icon("chevron-right", 18)]) : null,
      ]);
    }
    function agenciesCard() {
      if (state.date) return null;
      if (state.boardStatus === 403)
        return trioCard("agencies", "akim.trio.agencies", null, "", [tr("akim.trio.agencies_staff")], "#agencies");
      var sv = state.board;
      if (state.boardStatus !== 200 || !sv || !sv.available || !(sv.items || []).length) return null;
      var rows = {};
      (sv.items || []).forEach(function (r) { rows[r.service] = r; });
      var lag = (sv.lagging || []).filter(function (id) { return rows[id]; }).map(function (id) {
        return serviceName({ id: id, ru: rows[id].ru, kk: rows[id].kk, name_edited: rows[id].name_edited }) + " — " + num(rows[id].overdue || 0);
      });
      var joint = sv.joint && sv.joint.week != null ? sv.joint.week : sv.joint && sv.joint.open;
      return trioCard("agencies", "akim.trio.agencies", joint, tr("akim.trio.agencies_num", { n: joint || 0 }), [
        lag.length ? tr("akim.trio.agencies_lagging", { list: lag.join(", ") }) : null,
        sv.handoffs && sv.handoffs.week != null ? tr("akim.trio.agencies_handoffs", { n: sv.handoffs.week }) : null,
      ], "#agencies", null, sv.demo);
    }
    function shortWhen(iso) {
      return I() && I().formatDateTime ? I().formatDateTime(iso) : iso;
    }
    function togetherCard(d) {
      var t = d.together;
      if (!t || !t.available) return null;
      var c = t.counts || {};
      var now = Date.now();
      function started(x) { var s = Date.parse(x.starts_at || ""); return isFinite(s) && s <= now; }
      // Показываем дело, которое ещё можно поддержать: ближайшее не начатое без поддержки акимата (сцена 7 —
      // «Субботник в субботу»), иначе ближайшее не начатое, иначе идущее сейчас.
      var open = (t.top || []).filter(function (x) { return x.status !== "done"; });
      var ahead = open.filter(function (x) { return !started(x); });
      var next = ahead.filter(function (x) { return !x.supported; })[0] || ahead[0] || open[0];
      var nextLine = next ? h("p", { class: "akim-mini__line" }, [h("strong", { lang: next.lang === "kk" ? "kk" : next.lang === "ru" ? "ru" : null, text: next.title }),
        " · " + (started(next) ? tr("akim.trio.together_now") : shortWhen(next.starts_at)) + " · " + tr("akim.trio.together_people", { n: next.joined || 0 })]) : tr("akim.trio.together_none");
      var doneLine = c.done != null ? tr("akim.trio.together_done", { n: c.done }) : null;
      // Сцена 7 демо: ближайшее дело ещё без поддержки акимата — главное действие карточки «Поддержать».
      var support = next && !next.supported && !started(next);
      return trioCard("together", "akim.trio.together", c.upcoming != null ? c.upcoming : null, tr("akim.trio.together_num", { n: c.upcoming || 0 }),
        [nextLine, doneLine], support && next.id ? "#together/" + encodeURIComponent(next.id) : "#together",
        support ? "akim.trio.support" : null, t.demo);
    }
    function meetingsCard(d) {
      var m = d.meetings;
      if (!m || !m.available) return null;
      var c = m.counts || {};
      var open = (c.todo || 0) + (c.in_progress || 0);
      var first = (m.orders || [])[0];
      // Красное — только срок просроченного поручения, не весь текст (правило «Картины дня»: блок целиком не красим).
      var orderLine = first ? h("p", { class: "akim-mini__line" }, [
        h("strong", { text: first["text_" + lang()] || first.text_ru }),
        first.due ? " · " : "",
        first.due ? h("span", { class: first.overdue ? "akim-late-days" : null,
          text: tr("akim.trio.due", { date: I() ? I().formatDate(first.due) : first.due }) }) : null,
      ]) : null;
      var summary = [c.overdue ? tr("akim.trio.meetings_overdue", { n: c.overdue }) : null,
        c.total ? tr("akim.trio.meetings_done", { n: c.done || 0, total: c.total }) : null].filter(Boolean).join(" · ");
      var nextLine = m.next && m.next.at ? tr("akim.trio.meetings_next", { date: shortWhen(m.next.at) }) : null;
      if (!c.total && !m.next) return null;
      return trioCard("meetings", "akim.trio.meetings", open, tr("akim.trio.meetings_num", { n: open }),
        [orderLine || nextLine, summary || nextLine], "#meetings", null, m.demo);
    }
    function forecastCard(d) {
      var f = d.forecast;
      if (!f || !f.available || !(f.items || []).length) return null;
      var l = lang();
      var list = h("ol", { class: "bk-list akim-forecast__list" }, f.items.slice(0, 3).map(function (it, i) {
        var where = [it.district ? tr("district." + it.district) : null, it["reason_" + l] || it.reason_ru].filter(Boolean).join(" · ");
        return h("li", { class: "bk-list__item akim-forecast__item" }, [
          h("span", { class: "akim-forecast__rank", "aria-hidden": "true", text: num(i + 1) }),
          h("span", { class: "bk-list__main" }, [
            h("span", { class: "bk-list__title", text: it["label_" + l] || it.label_ru || where }),
            h("span", { class: "bk-list__sub", text: where }),
          ]),
        ]);
      }));
      return h("section", { class: "bk-card akim-card akim-forecast", "aria-labelledby": "akim-forecast-title" }, [
        h("div", { class: "akim-mini__head" }, [
          h("h2", { class: "bk-h2", id: "akim-forecast-title", text: tr(f.horizon === "week" ? "akim.forecast.week" : "akim.forecast.month") }),
          h("span", { class: "bk-tag akim-forecast__badge", text: tr("akim.forecast.badge") }),
        ]),
        list,
        h("p", { class: "bk-meta akim-forecast__note", text: f["method_" + l] || f.method_ru || tr("akim.forecast.note") }),
      ]);
    }

    function renderOk(d) {
      // Нет источника жалоб — не четыре нуля и не отдельный блок-заглушка (CLEAN_PASS §3 R08 п. 6): чисел нет,
      // а сводка ниже прямо говорит «Данные об обращениях пока не подключены».
      if (d.complaints_available !== false) {
        body.appendChild(renderKpis(d));
        body.appendChild(renderKpiMore(d));
      }
      // Пустые блоки не показываем (CLEAN_PASS §3 R08 п. 6); если ниже чисел пусто всё — одно состояние «пусто» ui-kit.
      var decisionsEl = renderDecisions(d);
      var pulseEl = renderPulse(d);
      // Две колонки на ноутбуке: слева «Горячие места» и объекты, справа темы, районы, предложения.
      // На телефоне колонки «растворяются» (display: contents), порядок задаёт CSS order.
      var main = [renderHot(d), renderObjects(d)].filter(Boolean);
      var side = [renderTopics(d), renderDistricts(d), renderProposals(d)].filter(Boolean);
      var nothing = d.empty && !decisionsEl && !pulseEl && !main.length && !side.length;
      if (nothing)
        body.appendChild(
          // П1: значок + короткий текст + одна кнопка (сегодня пусто — посмотреть вчера; прошлый день — вернуться к сегодня).
          h("div", { class: "bk-empty akim-empty", role: "status" }, [
            stateIcon("check"),
            h("p", { class: "bk-empty__title", text: tr(d.is_today === false ? "akim.empty_day" : "akim.empty") }),
            h("p", { class: "bk-empty__text", text: tr("akim.empty_hint") }),
            h("button", { type: "button", class: "bk-btn",
              onclick: function () { setDate(d.is_today === false ? null : yesterdayAstana()); } },
              [icon("calendar"), d.is_today === false ? tr("akim.date.today") : (wave2("akim.empty.yesterday") || tr("akim.date.today"))]),
          ])
        );
      // «Коротко о дне» — обычный абзац 17 без плашки; заголовок — только для чтения с экрана (CLEAN_PASS §3 R08 п. 4).
      else
        body.appendChild(
          h("section", { class: "akim-summary", "aria-labelledby": "akim-summary-title" }, [
            h("h2", { class: "akim-summary__title bk-sr-only", id: "akim-summary-title", text: tr("akim.summary.title") }),
            summaryText(d),
          ])
        );
      // Порядок по схеме R11 (IA_WAVE2 §5): KPI → сводка → «Нужно решение акима» → «Пульс» → прежние блоки.
      if (decisionsEl) body.appendChild(decisionsEl);
      if (pulseEl) body.appendChild(pulseEl);
      // «Картина дня» 2.0 (R11 IA_ROUND15 §5.10): ниже первого экрана — три одинаковые карточки соседей и прогноз.
      // День совсем пустой (одно состояние «пусто», CLEAN_PASS) — без них: числа служб без обращений были бы противоречием.
      var trio = nothing ? [] : [agenciesCard(), togetherCard(d), meetingsCard(d)].filter(Boolean);
      if (trio.length) body.appendChild(h("div", { class: "akim-trio", "data-count": String(trio.length) }, trio));
      var forecastEl = nothing ? null : forecastCard(d);
      if (forecastEl) body.appendChild(forecastEl);
      if (main.length || side.length)
        body.appendChild(
          h("div", { class: "akim-grid" + (main.length && side.length ? "" : " akim-grid--one") }, [
            main.length ? h("div", { class: "akim-col akim-col--main" }, main) : null,
            side.length ? h("div", { class: "akim-col akim-col--side" }, side) : null,
          ])
        );
      body.appendChild(
        h("button", { type: "button", class: "bk-btn bk-btn--ghost bk-btn--block akim-print-bottom", onclick: function () { printPage(); } }, [
          icon("print"),
          tr("common.action.print"),
        ])
      );
      // Раунд 15: «Картина недели» — отчёт A4 для совещания (week.html), та же дата и район.
      var wq = new URLSearchParams();
      if (state.date) wq.set("date", state.date);
      if (state.district) wq.set("district", state.district);
      body.appendChild(
        h("a", { class: "bk-btn bk-btn--ghost bk-btn--block akim-week-link", "data-key": "week-link",
          href: opts.weekHref + (wq.toString() ? "?" + wq : "") }, [icon("calendar"), tr("akim.week.open")])
      );
      // «Данные — пример» — одна серая строка внизу экрана (CLEAN_PASS §2.9, §3 R08 п. 1).
      if (d.demo && d.demo.any) body.appendChild(h("p", { class: "bk-footnote akim-demo", text: tr("common.demo_footnote") }));
    }

    // Сводка текстом; фраза о главной проблеме — жирным, чтобы глаз сразу нашёл её.
    function summaryText(d) {
      var textLang = lang() === "kk" ? "kk" : "ru";
      var parts = d.text_parts && d.text_parts[textLang];
      var p = h("p", { class: "akim-summary__text", lang: textLang });
      if (!parts || !parts.length) {
        p.textContent = (d.text && (d.text[textLang] || d.text.ru)) || "";
        return p;
      }
      parts.forEach(function (part, i) {
        if (i) p.appendChild(doc.createTextNode(" "));
        p.appendChild(h(part.role === "main" ? "strong" : "span", { class: "akim-summary__" + part.role, text: part.text }));
      });
      return p;
    }

    var shownStatus = null;
    function render() {
      renderTop();
      body.textContent = "";
      body.setAttribute("aria-busy", state.status === "loading" ? "true" : "false");
      var pending = state.status === "loading" && state.keep && !!state.data;
      if (pending) renderOk(state.data);
      else if (state.status === "loading") {
        if (state.skeleton) renderLoading();
      }
      else if (state.status === "error") renderError();
      else renderOk(state.data);
      if (pending) rootEl.setAttribute("data-pending", "");
      else rootEl.removeAttribute("data-pending");
      // Блоки мягко поднимаются, только когда экран сменил состояние (загрузка → данные), а не при тихом обновлении
      // и смене языка; prefers-reduced-motion выключает (akim.css).
      if (state.status !== shownStatus && state.status !== "loading") {
        body.setAttribute("data-enter", "");
        setTimeout(function () {
          body.removeAttribute("data-enter");
        }, 700);
      }
      shownStatus = state.status;
      rootEl.setAttribute("data-state", state.status);
    }

    // ── печать ──
    // В оболочке R01 «Картина дня» — прокручиваемая панель фиксированной высоты поверх карты: браузер напечатал бы
    // только видимую часть и шапку с картой. Перед печатью помечаем свою ветку DOM (от элемента до body), а печатные
    // стили akim.css прячут всё остальное и снимают ограничения высоты. После печати метки снимаются.
    var openedForPrint = [];
    function preparePrint() {
      if (!rootEl.isConnected || !rootEl.getClientRects().length) return; // экран скрыт — печатает тот, кто на виду
      // На бумаге «Ещё N тревог» не раскрыть — раскрываем перед печатью и сворачиваем после.
      Array.prototype.forEach.call(rootEl.querySelectorAll("details:not([open])"), function (el) {
        el.open = true;
        openedForPrint.push(el);
      });
      doc.documentElement.classList.add("akim-printing");
      for (var el = rootEl.parentElement; el && el !== doc.documentElement; el = el.parentElement) el.classList.add("akim-print-path");
    }
    function cleanupPrint() {
      openedForPrint.splice(0).forEach(function (el) {
        el.open = false;
      });
      doc.documentElement.classList.remove("akim-printing");
      Array.prototype.forEach.call(doc.querySelectorAll(".akim-print-path"), function (el) {
        el.classList.remove("akim-print-path");
      });
    }
    function printPage() {
      preparePrint();
      root.print();
    }
    root.addEventListener("beforeprint", preparePrint); // Ctrl+P тоже
    root.addEventListener("afterprint", cleanupPrint);

    var off = null;
    (I() ? I().ready : Promise.resolve())
      .then(function () {
        // Подписка на смену языка — после загрузки словаря, иначе первый кадр покажет ключи.
        if (I()) off = I().onChange(render);
        syncUrl();
        load();
      });

    var handle = {
      reload: load,
      setDate: setDate,
      setDistrict: setDistrict,
      get state() {
        return { date: state.date, district: state.district, status: state.status };
      },
      print: printPage,
      refresh: function () {
        load(true);
      },
      destroy: function () {
        if (off) off();
        if (barIO) barIO.disconnect();
        if (refreshTimer) clearInterval(refreshTimer);
        doc.removeEventListener("visibilitychange", onVisible);
        root.removeEventListener("beforeprint", preparePrint);
        root.removeEventListener("afterprint", cleanupPrint);
        cleanupPrint();
        state.request++;
        rootEl.textContent = "";
        delete rootEl.birgeAkim;
      },
    };
    rootEl.birgeAkim = handle; // для оболочки и тестов: document.getElementById("akim").birgeAkim.refresh()
    return handle;
  }

  root.BirgeAkim = { mount: mount, version: "akim-r15-day2" };
})(window);
