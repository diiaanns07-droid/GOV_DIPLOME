/*
 * R12 · раунд 14, волна 2 п. 6 · QR-паспорт объекта: ссылка /?report=<target_id> → лёгкая карточка объекта.
 *
 * Что на экране (UX: одна главная кнопка, остальное свёрнуто — POLISH_WAVE_2 «Защита от перегруза» п. 3–4):
 *   что это (остановка / перекрёсток / участок улицы / двор) и номер объекта; сколько людей сообщили и статус;
 *   ГЛАВНАЯ кнопка: «Я тоже», если есть открытые обращения, иначе «Сообщить о проблеме здесь»;
 *   вторая — «Сообщить о другом» (только рядом с «Я тоже»); «Подробнее»: жалобы по дням, темы, «На карту».
 * Тексты — ключи словаря R11 (IA_WAVE2 §6): report.here/other, qr.object_no, target.*, map.card.not_found*, status.*.
 * Карту не трогает и слоёв не добавляет: карточка живёт в панели/шторке, которую даёт оболочка R01.
 *
 * Данные — те же API, что у карточки тепловой карты (числа совпадут):
 *   GET  /api/civic/v2/target?id=…               R12: что за объект, подпись ru/kk, номер, точка (404 — устаревший QR)
 *   GET  /api/civic/v2/heat/target?kind&id&days   R07: сколько сообщили, статус, по дням, темы, open_ids (404 — жалоб нет)
 *   POST /api/civic/v2/complaints/{id}/metoo      R09: «Я тоже» ({device_id} — тот же ключ "birge.device", что у R07/R09)
 *
 * Подключение (R01):
 *   <link rel="stylesheet" href="/civic/qr/report.css"><script src="/civic/qr/report.js"></script>
 *   const id = BirgeReport.parseReportId(location.search);           // null — обычный запуск
 *   if (id) BirgeReport.mount({ root: panelEl, onReport: (p) => complaintUi.open(p), onOpenMap: (t) => heat.focusTarget(t.kind, t.id),
 *                               onClose: () => history.replaceState(null, "", location.pathname) }).open(id);
 *   onReport({target, point, geometry}) — открыть мастер жалобы R09 с этим местом (patch R09 в INTEGRATION; без него — open()).
 * Язык не переключает: берёт текущий из BirgeI18n (ссылка/QR не меняет выбор жителя — POLISH_WAVE_2 «мелочи»).
 */
(function (root, factory) {
  "use strict";
  var api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BirgeReport = api;
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var API = "/api/civic/v2";
  var DAYS = 30;
  var DEVICE_KEY = "birge.device";
  var DEVICE_RE = /^[A-Za-z0-9_-]{16,80}$/;
  var METOO_KEY = "birge.heat.metoo"; // общий с тепловой картой R07: «Я тоже» одно на устройство
  // Те же формы id, что принимает сервер (engine/civic_geo.REPORT_ID_RE): в ссылке — только id цели.
  var REPORT_ID_RE = /^(osm-(node|way|relation)-[0-9]{1,15}|osm-w[0-9]{1,15}-[0-9]{1,6}|yard-r?[0-9]{1,15}(-[0-9]{1,3})?|cell--?[0-9]{1,6}--?[0-9]{1,6})$/;

  // Тексты — только ключи словаря R11 (IA_WAVE2 §6, UX_REVIEW волна 2 п. 4); новых ключей паспорт не вводит.
  // Ниже — те же тексты на случай, если словарь не загрузился (стенд, старая сборка): словарь всегда побеждает.
  var PENDING = {
    ru: {
      "common.tag.demo": "Пример", "common.tag.approx": "Примерное место",
      "qr.object_no": "Объект № {id}",
      "common.period.last_days": "за {n} дней",
      "target.metoo": "Я тоже", "target.metoo_done": "Вы отметили «Я тоже»", "heat.toast_metoo": "Спасибо. Ваш голос учтён",
      "report.here": "Сообщить о проблеме здесь", "report.other": "Сообщить о другом",
      "common.action.more": "Подробнее", "target.by_day": "Жалобы по дням", "heat.topics": "О чём сообщают",
      "complaint.step5.to_map": "На карту",
      // Эталон A (13 окт): вкладки и строки карточки «Выбран объект».
      "passport.tab.overview": "Обзор", "common.nav.complaints": "Обращения", "passport.top": "Чаще всего",
      "passport.answer": "Ответ службы", "passport.sign_no": "Номер на табличке", "passport.until": "до {date}",
      "passport.no_open": "Открытых обращений нет", "passport.cases_error": "Обращения не загрузились. Попробуйте ещё раз через минуту.",
      "district.name": "район {name}", "district.esil": "Есиль", "district.nura": "Нура", "district.almaty": "Алматы",
      "district.baikonur": "Байконур", "district.saryarka": "Сарыарка", "district.saraishyk": "Сарайшык",
      "cat.lighting": "Освещение", "cat.noise_safety": "Шум и безопасность", "cat.other": "Другое", "cat.parking": "Парковки",
      "cat.roads": "Дороги", "cat.sidewalks": "Тротуары", "cat.smell_air": "Запахи и воздух", "cat.snow_ice": "Снег и гололёд",
      "cat.transport": "Остановки и транспорт", "cat.utilities": "ЖКХ: тепло и вода", "cat.waste": "Мусор", "cat.yards": "Дворы и площадки",
      "map.card.loading": "Загружаем карточку…",
      "map.card.not_found": "Объект не найден",
      "map.card.not_found_hint": "Возможно, его сняли с публикации или ссылка устарела.",
      "common.state.network_title": "Нет связи с сервером",
      "map.card.error": "Не удалось загрузить карточку.",
      "complaint.send_error": "Не удалось отправить. Проверьте связь и повторите.",
      "target.type.stop": "Остановка", "target.type.traffic_signal": "Светофор", "target.type.crossing": "Пешеходный переход",
      "target.type.intersection": "Перекрёсток", "target.type.segment": "Участок улицы", "target.type.yard": "Двор",
      "status.new": "Новое", "status.accepted": "Принято", "status.in_progress": "В работе", "status.fixed": "Исправлено",
      "status.rejected": "Отклонено", "status.reported_fixed": "Служба сообщила об устранении",
      "status.verified": "Проверено жителями", "status.reopened": "Проблема осталась — снова в работе", "status.label": "Статус",
      "common.action.close": "Закрыть", "common.action.retry": "Повторить",
      "qr.card.complaints": "Обращения здесь", "passport.history": "История", "passport.answer_due": "Ответ службы до {date}",
      "target.type.playground": "Детская площадка", "target.type.pitch": "Спортплощадка", "target.type.park": "Парк или сквер",
      "target.type.waste": "Контейнерная площадка", "target.kind.cell": "Примерное место",
      "common.state.network_text": "Проверьте интернет и повторите.", "common.state.error_text": "Попробуйте ещё раз через минуту.",
      "heat.fixed_until": "На карте зелёным до {date}",
    },
    kk: {
      "common.tag.demo": "Үлгі", "common.tag.approx": "Шамамен көрсетілген орын",
      "qr.object_no": "Нысан № {id}",
      "common.period.last_days": "соңғы {n} күнде",
      "target.metoo": "Мен де", "target.metoo_done": "Сіз «Мен де» деп белгіледіңіз", "heat.toast_metoo": "Рақмет. Дауысыңыз есепке алынды",
      "report.here": "Осы жердегі мәселе туралы хабарлау", "report.other": "Басқа мәселе туралы хабарлау",
      "common.action.more": "Толығырақ", "target.by_day": "Күндер бойынша шағымдар", "heat.topics": "Не туралы хабарлайды",
      "complaint.step5.to_map": "Картаға",
      "passport.tab.overview": "Шолу", "common.nav.complaints": "Өтініштер", "passport.top": "Ең жиі",
      "passport.answer": "Қызмет жауабы", "passport.sign_no": "Тақтайшадағы нөмір", "passport.until": "{date} дейін",
      "passport.no_open": "Ашық өтініштер жоқ", "passport.cases_error": "Өтініштер жүктелмеді. Бір минуттан кейін қайталап көріңіз.",
      "district.name": "{name} ауданы", "district.esil": "Есіл", "district.nura": "Нұра", "district.almaty": "Алматы",
      "district.baikonur": "Байқоңыр", "district.saryarka": "Сарыарқа", "district.saraishyk": "Сарайшық",
      "cat.lighting": "Жарықтандыру", "cat.noise_safety": "Шу және қауіпсіздік", "cat.other": "Басқа", "cat.parking": "Тұрақтар",
      "cat.roads": "Жолдар", "cat.sidewalks": "Жаяу жүргіншілер жолы", "cat.smell_air": "Иіс және ауа", "cat.snow_ice": "Қар және көктайғақ",
      "cat.transport": "Аялдамалар мен көлік", "cat.utilities": "ТКШ: жылу мен су", "cat.waste": "Қоқыс", "cat.yards": "Аулалар мен алаңдар",
      "map.card.loading": "Карточка жүктеліп жатыр…",
      "map.card.not_found": "Нысан табылмады",
      "map.card.not_found_hint": "Мүмкін, ол жарияланымнан алынған немесе сілтеме ескірген.",
      "common.state.network_title": "Сервермен байланыс жоқ",
      "map.card.error": "Карточканы жүктеу мүмкін болмады.",
      "complaint.send_error": "Жіберу мүмкін болмады. Байланысты тексеріп, қайталаңыз.",
      "target.type.stop": "Аялдама", "target.type.traffic_signal": "Бағдаршам", "target.type.crossing": "Жаяу жүргіншілер өткелі",
      "target.type.intersection": "Қиылыс", "target.type.segment": "Көше бөлігі", "target.type.yard": "Аула",
      "status.new": "Жаңа", "status.accepted": "Қабылданды", "status.in_progress": "Орындалуда", "status.fixed": "Түзетілді",
      "status.rejected": "Қабылданбады", "status.reported_fixed": "Қызмет түзетілгенін хабарлады",
      "status.verified": "Тұрғындар тексерді", "status.reopened": "Мәселе қалды — қайта жұмыста", "status.label": "Мәртебесі",
      "common.action.close": "Жабу", "common.action.retry": "Қайталау",
      "qr.card.complaints": "Осы жердегі өтініштер", "passport.history": "Тарих", "passport.answer_due": "Қызмет жауабының мерзімі: {date}",
      "target.type.playground": "Балалар алаңы", "target.type.pitch": "Спорт алаңы", "target.type.park": "Саябақ немесе гүлзар",
      "target.type.waste": "Контейнер алаңы", "target.kind.cell": "Шамамен көрсетілген орын",
      "common.state.network_text": "Интернетті тексеріп, қайталап көріңіз.", "common.state.error_text": "Бір минуттан кейін қайталап көріңіз.",
      "heat.fixed_until": "Жасыл түспен көрсетілу мерзімі: {date}",
    },
  };
  // Подпись «за 30 дней»: в ru — формы числа, как в словаре R11.
  function plural(n, forms) {
    var m10 = n % 10, m100 = n % 100;
    return m10 === 1 && m100 !== 11 ? forms[0] : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? forms[1] : forms[2];
  }

  function i18n() { return root && root.BirgeI18n && typeof root.BirgeI18n.t === "function" ? root.BirgeI18n : null; }
  function lang() {
    var B = i18n();
    var l = B && B.getLang ? B.getLang() : (root.document && root.document.documentElement.lang) || "ru";
    return l === "kk" ? "kk" : "ru";
  }
  function fill(text, params) {
    return params ? String(text).replace(/\{(\w+)\}/g, function (w, n) { return params[n] == null ? w : String(params[n]); }) : text;
  }
  // Ключ словаря R11, если он там есть; иначе запасной текст нужного языка (без предупреждений в консоли).
  function t(key, params) {
    var B = i18n(), l = lang();
    // Словарь на языке жителя → свой запасной текст на том же языке → русский словарь (а не наоборот: без русского в ҚАЗ).
    if (B && B.has && B.has(key, l)) return B.t(key, params);
    if (B && B.has && !(PENDING[l] && PENDING[l][key]) && B.has(key, "ru")) return B.t(key, params);
    if (key === "common.period.last_days" && l === "ru" && params) return "за " + params.n + " " + plural(params.n, ["день", "дня", "дней"]);
    return fill((PENDING[l] && PENDING[l][key]) || PENDING.ru[key] || key, params);
  }
  // Номер объекта группами по 3 цифры («4 109 037 549» — продиктовать оператору); Д-…/К-… как есть.
  function groupDigits(num) {
    var s = String(num == null ? "" : num);
    return /^[0-9]{5,}$/.test(s) ? s.replace(/\B(?=([0-9]{3})+(?![0-9]))/g, "\u00a0") : s;
  }
  function reportedText(n) {
    var B = i18n();
    if (B && B.has && B.has("target.reported")) return B.t("target.reported", { n: n });
    if (lang() === "kk") return n + " адам хабарлады";
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return "Сообщил " + n + " человек";
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "Сообщили " + n + " человека";
    return "Сообщили " + n + " человек";
  }
  // Дата «11 окт» / «11 қаз» — BirgeI18n.formatDate (UX_BRIEF); без словаря — ГГГГ-ММ-ДД из записи.
  function fmtDate(value) {
    var B = i18n();
    if (B && typeof B.formatDate === "function") return B.formatDate(value);
    return String(value || "").slice(0, 10);
  }
  // Что было с обращениями места (публичные поля R09: status_history, resolution) — новые сверху, не больше 5.
  function historyRows(complaints) {
    var seen = {}, rows = [];
    (complaints || []).forEach(function (c) {
      (c.status_history || []).forEach(function (e) { rows.push({ at: e.at, status: e.status }); });
      var r = c.resolution || {};
      if (r.reported_at) rows.push({ at: r.reported_at, status: "reported_fixed" });
      if (r.verified_at) rows.push({ at: r.verified_at, status: "verified_fixed" });
      if (r.reopened_at) rows.push({ at: r.reopened_at, status: "reopened" });
    });
    rows.sort(function (a, b) { return String(b.at).localeCompare(String(a.at)); });
    return rows.filter(function (e) {
      var k = String(e.at).slice(0, 10) + "|" + e.status;
      if (!e.at || seen[k]) return false;
      seen[k] = true;
      return true;
    }).slice(0, 5);
  }
  function catName(id) {
    var name = t("cat." + id);
    return name === "cat." + id ? id : name;
  }
  // Эталон A: «6 человек сообщили» (число крупно, слова — рядом) и «Ещё 5 обращений» — формы числа как в словаре R11.
  function peopleWords(n) {
    var B = i18n();
    if (B && B.has && B.has("passport.people", lang())) return B.t("passport.people", { n: n });
    if (lang() === "kk") return "адам хабарлады";
    return plural(n, ["человек сообщил", "человека сообщили", "человек сообщили"]);
  }
  function moreCases(n) {
    var B = i18n();
    if (B && B.has && B.has("passport.more_cases", lang())) return B.t("passport.more_cases", { n: n });
    if (lang() === "kk") return "Тағы " + n + " өтініш";
    return "Ещё " + n + " " + plural(n, ["обращение", "обращения", "обращений"]);
  }

  // ---------- чистые функции (проверяются в Node) ----------
  function parseReportId(search) {
    var m = /(?:^|[?&])report=([^&#]*)/.exec(String(search || ""));
    if (!m) return null;
    var id;
    try { id = decodeURIComponent(m[1].replace(/\+/g, " ")); } catch (e) { return null; }
    return REPORT_ID_RE.test(id) ? id : null;
  }
  // Слово вида над заголовком — ключ target.type.* словаря R11 (площадки, парки, контейнеры — ключи R12, запасной текст выше).
  var TYPE_KEY = { bus_stop: "stop", traffic_signal: "traffic_signal", crossing: "crossing", intersection: "intersection",
    playground: "playground", pitch: "pitch", park: "park", waste: "waste" };
  var KIND_ICON = { bus_stop: "bus", crossing: "walk", traffic_signal: "road", intersection: "road", playground: "playground", pitch: "ball",
    park: "trees", waste: "trash" };
  var KIND_CAT = { bus_stop: "transport", traffic_signal: "roads", intersection: "roads", crossing: "sidewalks", playground: "yards",
    pitch: "yards", waste: "waste" };
  var CAT_ICON = { lighting: "bulb", snow_ice: "snowflake", utilities: "droplet", smell_air: "wind", noise_safety: "shield", parking: "parking",
    roads: "road", sidewalks: "walk", transport: "bus", waste: "trash", yards: "playground", other: "dots" };
  function kindCat(target) {
    if (!target) return null;
    if (target.kind === "object") return KIND_CAT[target.object_kind] || null;
    if (target.kind === "segment") return "roads";
    return String(target.id || "").indexOf("yard-") === 0 ? "yards" : null;
  }
  // Цвет плитки слева от названия — по уровню значка на карте (как в эталоне: светлый фон, тёмная иконка того же тона).
  function tileTone(it) {
    if (!it || !(it.count > 0)) return "none";
    if (isFixed(it)) return "ok";
    return it.level >= 3 ? "red" : it.level === 2 ? "orange" : "amber";
  }
  function kindKey(target) {
    if (!target) return null;
    if (target.kind === "object") return TYPE_KEY[target.object_kind] ? "target.type." + TYPE_KEY[target.object_kind] : null;
    if (target.kind === "segment") return "target.type.segment";
    var id = String(target.id || "");
    return id.indexOf("yard-") === 0 ? "target.type.yard" : id.indexOf("cell-") === 0 ? "target.kind.cell" : null;
  }
  function kindIcon(target) {
    if (!target) return "pin";
    if (target.kind === "segment") return "road";
    if (target.kind === "object") return KIND_ICON[target.object_kind] || "pin";
    return String(target.id || "").indexOf("yard-") === 0 ? "building" : "pin";
  }
  // Состояния волны 2 (categories_v2 heat_states): verified_fixed → «Проверено жителями».
  function statusKey(status) { return "status." + (status === "verified_fixed" ? "verified" : status || "new"); }
  function isFixed(it) { return !!it && (it.status === "fixed" || it.status === "verified_fixed" || it.state === "fixed"); }
  function metooKey(target) { return target.kind + ":" + target.id; }
  function metooDone(target) {
    try { return JSON.parse(root.localStorage.getItem(METOO_KEY) || "{}")[metooKey(target)] === true; } catch (e) { return false; }
  }
  function rememberMetoo(target) {
    try {
      var all = JSON.parse(root.localStorage.getItem(METOO_KEY) || "{}");
      all[metooKey(target)] = true;
      root.localStorage.setItem(METOO_KEY, JSON.stringify(all));
    } catch (e) { /* приватный режим: отметка останется до перезагрузки */ }
  }
  var memoryDevice = null;
  function deviceId() {
    try {
      var id = root.localStorage.getItem(DEVICE_KEY);
      if (id && DEVICE_RE.test(id)) return id;
    } catch (e) { /* нет хранилища */ }
    if (!memoryDevice) {
      var abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", buf = new Uint8Array(24);
      root.crypto.getRandomValues(buf);
      memoryDevice = "d-" + Array.prototype.map.call(buf, function (b) { return abc[b % abc.length]; }).join("");
      try { root.localStorage.setItem(DEVICE_KEY, memoryDevice); } catch (e) { /* только в памяти */ }
    }
    return memoryDevice;
  }
  // Главная кнопка: «Я тоже» — если есть открытые обращения и житель ещё не отмечался; иначе «Сообщить».
  function mainAction(heatItem, target) {
    var open = heatItem && !isFixed(heatItem) && (heatItem.open_ids || []).length > 0;
    if (open && !metooDone(target)) return "metoo";
    return "report";
  }

  // ---------- DOM ----------
  function h(tag, attrs, kids) {
    var e = root.document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = String(v);
      else if (k.indexOf("on") === 0 && typeof v === "function") e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : String(v));
    });
    (kids || []).forEach(function (c) { if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : root.document.createTextNode(String(c))); });
    return e;
  }
  // Подпись кнопки рядом со значком: в две строки (длинное kk) — текст остаётся у значка, а не по центру кнопки.
  function btnText(text) { return h("span", { class: "bq-btn__text", text: text }); }
  function icon(name, sprite) {
    var NS = "http://www.w3.org/2000/svg";
    var svg = root.document.createElementNS(NS, "svg");
    svg.setAttribute("class", "ic");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var use = root.document.createElementNS(NS, "use");
    use.setAttribute("href", sprite + "#i-" + name);
    svg.appendChild(use);
    return svg;
  }

  function mount(options) {
    var opts = options || {};
    var host = opts.root;
    if (!host || host.nodeType !== 1) throw new TypeError("BirgeReport.mount: root element is required");
    var api = opts.api || API;
    var sprite = opts.iconSprite || "/civic/ui-kit/icons.svg";
    var fetchFn = opts.fetch || (root.fetch && root.fetch.bind(root));
    var S = { id: null, info: null, heat: null, state: "idle", error: null, seq: 0, notice: null, busy: false, tab: "overview",
      cases: null,  // cases: {key, rows} — обращения места (R09, публичный вид), грузятся только при раскрытии «Подробнее»
      enter: false };  // enter: карточка только что открылась — один раз мягко «поднимается» (bk-rise, reduced-motion — без)
    var box = h("section", { class: "bq-report", "aria-live": "polite", "data-state": "idle" });
    host.appendChild(box);
    var destroyed = false;

    function getJson(path) {
      return fetchFn(api + path, { credentials: "same-origin", headers: { Accept: "application/json" } }).then(function (r) {
        return r.json().catch(function () { return null; }).then(function (body) {
          if (r.ok) return body;
          var err = new Error((body && body.error && body.error.message) || "HTTP " + r.status);
          err.status = r.status;
          err.code = body && body.error && (body.error.code || body.error);
          throw err;
        });
      });
    }
    function postJson(path, body) {
      // Id устройства — и в теле, и в заголовке X-Birge-Device (так шлёт R07; R09 принимает оба).
      return fetchFn(api + path, { method: "POST", credentials: "same-origin",
        headers: { Accept: "application/json", "Content-Type": "application/json", "X-Birge-Device": body.device_id || "" }, body: JSON.stringify(body) })
        .then(function (r) { if (!r.ok) { var e = new Error("HTTP " + r.status); e.status = r.status; throw e; } return r.json().catch(function () { return {}; }); });
    }

    function open(id) {
      var my = ++S.seq;
      S.id = id; S.info = null; S.heat = null; S.notice = null; S.error = null; S.enter = true; S.tab = "overview"; S.cases = null;
      if (!REPORT_ID_RE.test(String(id || ""))) { S.state = "error"; S.error = "bad_link"; render(); return Promise.resolve(false); }
      S.state = "loading"; render();
      return getJson("/target?id=" + encodeURIComponent(id)).then(function (info) {
        if (destroyed || my !== S.seq) return false;
        S.info = info;
        return loadHeat(my).then(function () { return true; });
      }).catch(function (err) {
        if (destroyed || my !== S.seq) return false;
        S.state = "error";
        S.error = err && err.status === 404 ? "not_found" : err && err.status === 400 ? "bad_link" : err && err.status >= 500 ? "server" : "network";
        render();
        return false;
      });
    }
    // Числа и статус — как у тепловой карты R07; 404 = за период жалоб нет (это не ошибка).
    function loadHeat(my) {
      var tg = S.info.target;
      var q = "kind=" + encodeURIComponent(tg.kind) + "&id=" + encodeURIComponent(tg.id) + "&days=" + DAYS;
      return getJson("/heat/target?" + q).then(function (res) {
        if (destroyed || my !== S.seq) return;
        S.heat = res && res.item ? res.item : null;
        S.cases = null;
        S.state = "ready"; render();
        if (S.tab !== "overview") loadCases();
      }, function (err) {
        if (destroyed || my !== S.seq) return;
        S.heat = null;
        S.state = "ready";
        // Тепловая карта недоступна (сеть/модуль) — карточку объекта всё равно показываем, без чисел.
        S.heatUnavailable = !(err && err.status === 404);
        render();
      });
    }

    // «История, текущие обращения» (POLISH_WAVE_2 п. 6, IA_WAVE2 §6.1) — в «Подробнее»: до 3 открытых обращений места.
    function loadCases() {
      var ids = ((S.heat && S.heat.open_ids) || []).slice(0, 3), key = S.id + "|" + ids.join(","), my = S.seq;
      if (!ids.length || (S.cases && S.cases.key === key)) return;
      S.cases = { key: key, rows: null };
      Promise.all(ids.map(function (id) {
        return getJson("/complaints/" + encodeURIComponent(id)).then(function (b) {
          var c = b && (b.data ? b.data.complaint : b.complaint);
          return c && typeof c === "object" ? c : null;
        }, function () { return null; });
      })).then(function (rows) {
        if (destroyed || my !== S.seq || !S.cases || S.cases.key !== key) return;
        S.cases.rows = rows.filter(Boolean);
        render();
      });
    }
    function metoo() {
      var it = S.heat, tg = S.info.target, id = it && (it.open_ids || [])[0];
      if (!id || S.busy) return;
      S.busy = true; S.notice = null; render();
      postJson("/complaints/" + encodeURIComponent(id) + "/metoo", { device_id: deviceId() }).then(function () {
        if (destroyed) return;
        rememberMetoo(tg);
        S.busy = false; S.notice = { ok: true, text: t("heat.toast_metoo") }; S.bump = true;
        // R07 слушает это событие и перерисует тепловую карту (как после «Я тоже» в мастере R09).
        try { root.dispatchEvent(new root.CustomEvent("birge:complaint", { detail: { type: "metoo", complaint_id: id, target: tg } })); } catch (e) { /* */ }
        return loadHeat(S.seq);
      }, function () {
        if (destroyed) return;
        S.busy = false; S.notice = { ok: false, text: t("complaint.send_error") }; render();
      });
    }
    function report() {
      if (typeof opts.onReport === "function") opts.onReport({ target: S.info.target, point: S.info.point, geometry: S.info.geometry,
        approximate: !!S.info.approximate });
    }

    function render() {
      if (destroyed) return;
      box.setAttribute("data-state", S.state);
      // Стекло (GLASS.md R11 §4: «QR-паспорт — bk-glass на карточке»): своё — только вне панели оболочки. В панели R01
      // (.civic-panel, по GLASS.md §4 №5 — стекло) паспорт лежит на её стекле: второе стекло или карточка в карточке не нужны.
      box.classList.toggle("bk-glass", !(box.parentElement && box.parentElement.closest && box.parentElement.closest(".bk-glass, .civic-panel")));
      box.lang = lang();
      var kids;
      if (S.state === "loading" || S.state === "idle") {
        // Скелетон повторяет карточку: строка вида, заголовок, строка статуса, кнопка — ничего не «прыгает», когда придут данные.
        kids = [head(h("i", { class: "bk-skel bq-tile bq-skel__tile" }), [h("i", { class: "bk-skel bk-skel--title bq-skel__title" }),
            h("i", { class: "bk-skel bk-skel--line bq-skel__sub" })]),
          h("div", { class: "bq-skel", "aria-busy": "true" }, [
            h("span", { class: "bk-sr-only", text: t("map.card.loading") }),
            h("i", { class: "bk-skel bk-skel--title bq-skel__big" }), h("i", { class: "bk-skel bk-skel--line bq-skel__st" }),
            h("div", { class: "bq-skel__acts" }, [h("i", { class: "bk-skel bq-skel__button" }), h("i", { class: "bk-skel bq-skel__button bq-skel__button--s" })])])];
      } else if (S.state === "error") {
        kids = [top()].concat(errorView());
      } else {
        kids = card();
        if (S.enter) { box.classList.add("bq-enter"); S.enter = false; } else box.classList.remove("bq-enter");
      }
      // Фокус клавиатуры не теряется при перерисовке («Я тоже», «Подробнее», «Повторить»): если он был в карточке —
      // на ту же кнопку, если она осталась и доступна, иначе на заголовок (tabindex=-1). Снаружи карточки — не трогаем.
      var doc = root.document, act = doc.activeElement;
      var had = !!(act && act !== doc.body && box.contains(act));
      var was = had ? (act.getAttribute("data-tab") ? "tab" : act.getAttribute("data-act")) : null;
      box.replaceChildren.apply(box, kids);
      if (had && !box.contains(doc.activeElement)) {
        var same = was === "tab" ? box.querySelector('.bq-tab[aria-selected="true"]') : was ? box.querySelector('[data-act="' + was + '"]') : null;
        var to = same && !same.disabled ? same : box.querySelector(".bq-title") || box.querySelector("button:not([disabled])");
        if (to) { try { to.focus({ preventScroll: true }); } catch (e) { to.focus(); } }
      }
    }
    function closeBtn() {
      return h("button", { type: "button", class: "bq-x bq-report__close", "aria-label": t("common.action.close"), title: t("common.action.close"),
        onclick: function () { if (typeof opts.onClose === "function") opts.onClose(); destroy(); } }, [icon("close", sprite)]);
    }
    // Шапка карточки эталона: плитка 48 с иконкой, название 19/600 и подпись, крестик 32 в круге (зона нажатия 44).
    function head(tile, text) { return h("div", { class: "bq-hd" }, [tile, h("div", { class: "bq-hd__text" }, text), closeBtn()]); }
    // Верхняя строка состояний ошибки: только крестик справа.
    function top() { return h("div", { class: "bq-top" }, [closeBtn()]); }
    // Ошибка = что случилось + что делать (DESIGN_MARATHON п. 8): значок, заголовок, подсказка, одна главная кнопка.
    function errorView() {
      var retry = S.error === "network" || S.error === "server";
      // Неизвестный или испорченный номер — «Объект не найден» + подсказка и «На карту» (IA_WAVE2 §6.1), не пустая карта.
      var gone = !retry;
      var big = icon(gone ? "search" : S.error === "network" ? "wifi-off" : "alert", sprite);
      big.setAttribute("class", "ic ic--48");
      return [h("div", { class: "bk-error bq-error", role: "alert", "data-error": S.error }, [big,
        h("p", { class: "bk-error__title", text: t(gone ? "map.card.not_found" : S.error === "server" ? "map.card.error" : "common.state.network_title") }),
        h("p", { class: "bk-error__text", text: t(gone ? "map.card.not_found_hint" : S.error === "server" ? "common.state.error_text" : "common.state.network_text") }),
        h("div", { class: "bq-actions" }, [
          retry ? h("button", { type: "button", class: "bk-btn bk-btn--primary bk-btn--block", "data-act": "retry", onclick: function () { open(S.id); } }, [icon("refresh", sprite), btnText(t("common.action.retry"))]) : null,
          typeof opts.onOpenMap === "function" ? h("button", { type: "button", class: "bk-btn bk-btn--block " + (retry ? "bk-btn--ghost" : "bk-btn--primary"),
            "data-act": "map", onclick: function () { opts.onOpenMap(null); } }, [icon("pin", sprite), btnText(t("complaint.step5.to_map"))]) : null])])];
    }

    function setTab(tab, focus) {
      S.tab = tab; S.tabAnim = true;
      if (tab !== "overview") loadCases();
      render();
      if (focus) { var b = box.querySelector('[data-tab="' + tab + '"]'); if (b) b.focus(); }
    }
    // Строка как в эталоне: значок в серой плитке 30, подпись слева, значение справа.
    function row(iconName, label, value, attrs) {
      return h("div", Object.assign({ class: "bq-row" }, attrs || {}), [h("span", { class: "bq-row__ic", "aria-hidden": "true" }, [icon(iconName, sprite)]),
        h("span", { class: "bq-row__label", text: label }), value == null ? null : h("b", { class: "bq-row__value" }, [value])]);
    }
    function skelRows(n) {
      var out = [];
      for (var i = 0; i < n; i++) out.push(h("div", { class: "bq-row bq-row--skel", "aria-hidden": "true" }, [h("i", { class: "bk-skel bq-row__ic" }), h("i", { class: "bk-skel bk-skel--line" })]));
      return out;
    }

    // Карточка = эталон A «Выбран объект» (research/round-14/design/REFERENCE.html): главное сверху — что это, сколько
    // людей, статус и одна главная кнопка; подробности — во вкладках «Обзор · Обращения · История», а не простынёй текста.
    function card() {
      var info = S.info, tg = info.target, it = S.heat, l = lang();
      var title = (l === "kk" ? tg.label_kk : tg.label_ru) || tg.label_ru;
      var demo = !!(it && it.demo), has = !!(it && it.count > 0), fixed = isFixed(it);
      var kk = kindKey(tg), kindWord = kk ? t(kk) : "", cat = kindCat(tg);
      // Подпись как в эталоне: «Остановки и транспорт · пр. Туран» — улица рядом (R12 /target), иначе район.
      var subParts = [cat ? catName(cat) : kindWord];
      if (info.street && (info.street.ru || info.street.kk)) subParts.push(l === "kk" ? info.street.kk || info.street.ru : info.street.ru);
      else if (it && it.district) subParts.push(t("district.name", { name: t("district." + it.district) }));
      var sub = h("p", { class: "bq-sub" }, [subParts.filter(Boolean).join(" · "),
        demo ? h("span", { class: "bk-tag bk-tag--demo bq-demo", text: t("common.tag.demo") }) : null]);
      var tile = h("span", { class: "bq-tile", "data-tone": tileTone(it), "aria-hidden": "true" }, [icon(kindIcon(tg), sprite)]);
      var out = [head(tile, [h("h2", { class: "bq-title", tabindex: "-1", text: title }), sub])];
      if (info.approximate) out.push(h("p", { class: "bk-tag bk-tag--approx bq-approx", text: t("common.tag.approx") }));
      if (has) {
        // Сразу после «Я тоже» число один раз мягко «подпрыгивает» — видно, что голос учтён (только движение).
        var bump = S.bump && S.notice && S.notice.ok; S.bump = false;
        out.push(h("p", { class: "bq-big bq-reported", "aria-label": reportedText(it.count) + " · " + t("common.period.last_days", { n: DAYS }) }, [
          h("b", { class: bump ? "bq-bump" : null, text: String(it.count) }), h("span", { text: peopleWords(it.count) + " · " + t("common.period.last_days", { n: DAYS }) })]));
        var due = !fixed && it.due && it.due.at ? t("passport.until", { date: fmtDate(it.due.at) }) : fixed && it.fixed_until ? t("heat.fixed_until", { date: fmtDate(it.fixed_until) }) : null;
        out.push(h("div", { class: "bq-st bq-statusline" }, [h("span", { class: "bk-status", "data-status": it.status === "verified_fixed" ? "verified" : it.status,
          "aria-label": t("status.label") + ": " + t(statusKey(it.status)), text: t(statusKey(it.status)) }), due ? h("small", { text: due }) : null]));
      }
      // Одна главная кнопка (UX_BRIEF п. 3) и рядом вторая — как «Отметить исправленным · Ответить» в эталоне.
      var main = mainAction(it, tg), actions = [];
      if (main === "metoo") {
        actions.push(h("button", { type: "button", class: "bk-btn bk-btn--primary bq-btn bq-btn--p", "data-act": "metoo",
          "aria-busy": S.busy ? "true" : null, disabled: S.busy, onclick: metoo }, [icon("users", sprite), btnText(t("target.metoo"))]));
        actions.push(h("button", { type: "button", class: "bk-btn bq-btn bq-btn--s", "data-act": "report-other", onclick: report }, [btnText(t("report.other"))]));
      } else {
        // Одно подтверждение: сразу после «Я тоже» — «Спасибо…» (ниже), иначе — тихая строка «Вы отметили «Я тоже»».
        if (it && !fixed && (it.open_ids || []).length && metooDone(tg) && !(S.notice && S.notice.ok)) {
          out.push(h("p", { class: "bq-done" }, [icon("check", sprite), t("target.metoo_done")]));
        }
        actions.push(h("button", { type: "button", class: "bk-btn bk-btn--primary bq-btn bq-btn--p", "data-act": "report", onclick: report },
          [icon("send", sprite), btnText(t(has && !fixed ? "report.other" : "report.here"))]));
      }
      // Подтверждение или ошибка — над кнопками, где житель смотрит (на телефоне ниже кнопки его не видно).
      if (S.notice) out.push(h("p", { class: "bq-notice" + (S.notice.ok ? " bq-notice--ok" : " bq-notice--error"), role: S.notice.ok ? "status" : "alert" },
        [icon(S.notice.ok ? "check" : "alert", sprite), h("span", { text: S.notice.text })]));
      out.push(h("div", { class: "bq-actions" }, actions));

      var number = row("pin", t("passport.sign_no"), "№ " + groupDigits(info.number));
      var toMap = typeof opts.onOpenMap === "function" ? h("button", { type: "button", class: "bq-link", "data-act": "map", onclick: function () { opts.onOpenMap(tg); } },
        [icon("pin", sprite), t("complaint.step5.to_map")]) : null;
      if (!has) {
        // Жалоб нет — вкладки не нужны: номер с таблички и «На карту».
        out.push(h("div", { class: "bq-rows bq-rows--top" }, [number, toMap ? h("div", { class: "bq-row bq-row--link" }, [toMap]) : null]));
        return out;
      }
      var openN = (it.open_ids || []).length;
      var TABS = [["overview", t("passport.tab.overview")], ["cases", t("common.nav.complaints") + (openN ? " · " + openN : "")], ["history", t("passport.history")]];
      var tabs = h("div", { class: "bq-tabs", role: "tablist", "aria-label": title }, TABS.map(function (tb, i) {
        var on = S.tab === tb[0];
        var b = h("button", { type: "button", role: "tab", class: "bq-tab", id: "bq-tab-" + tb[0], "data-tab": tb[0], "aria-selected": on ? "true" : "false",
          "aria-controls": "bq-panel", tabindex: on ? "0" : "-1", onclick: function () { setTab(tb[0]); } }, [tb[1]]);
        // Стрелки ←/→ (и Home/End) — между вкладками, как в ARIA tabs.
        b.addEventListener("keydown", function (e) {
          var k = e.key, j = k === "ArrowRight" ? i + 1 : k === "ArrowLeft" ? i - 1 : k === "Home" ? 0 : k === "End" ? TABS.length - 1 : null;
          if (j === null) return;
          e.preventDefault(); setTab(TABS[(j + TABS.length) % TABS.length][0], true);
        });
        return b;
      }));
      out.push(tabs);
      var panel = [];
      if (S.tab === "overview") {
        var topCat = null, topN = -1;
        Object.keys(it.by_category || {}).forEach(function (c) { if (it.by_category[c] > topN) { topN = it.by_category[c]; topCat = c; } });
        if (topCat) panel.push(row(CAT_ICON[topCat] || "dots", t("passport.top"), catName(topCat)));
        if (!fixed && it.due && it.due.at) panel.push(row("clock", t("passport.answer"), t("passport.until", { date: fmtDate(it.due.at) })));
        panel.push(number);
        var g = it.texts && it.texts.groups && it.texts.groups[0];
        if (g && g.text) {
          var rest = Math.max(0, it.count - (g.people || 1));
          panel.push(h("div", { class: "bq-row bq-row--quote" }, [h("p", { class: "bq-quote", text: "«" + g.text + "»" }),
            rest ? h("button", { type: "button", class: "bq-link", "data-act": "cases", onclick: function () { setTab("cases", true); } }, [moreCases(rest)]) : null]));
        }
        if (toMap) panel.push(h("div", { class: "bq-row bq-row--link" }, [toMap]));
      } else {
        // Открытых обращений нет — грузить нечего; иначе скелетон строк, пока R09 отвечает (без «прыжка»).
        var cases = openN ? S.cases && S.cases.rows : [];
        if (!cases) panel = skelRows(S.tab === "cases" ? Math.min(3, openN) : 2);
        else if (S.tab === "cases") {
          panel = cases.length ? [h("ul", { class: "bq-list bq-cases" }, cases.map(function (c) {
            var st = c.heat_state || c.status, open = !isFixed({ status: st }) && c.status !== "rejected";
            return h("li", { class: "bq-row bq-case" }, [h("span", { class: "bq-row__ic", "aria-hidden": "true" }, [icon(CAT_ICON[c.category] || "dots", sprite)]),
              h("span", { class: "bq-case__what" }, [h("span", { class: "bq-case__cat", text: catName(c.category) }),
                h("small", { class: "bq-case__meta", text: reportedText(c.reporters || 1) + (open && c.due_at ? " · " + t("passport.until", { date: fmtDate(c.due_at) }) : "") })]),
              h("span", { class: "bk-status bq-case__status", "data-status": st === "verified_fixed" ? "verified" : st, text: t(statusKey(st)) })]);
          }))] : [h("p", { class: "bq-empty", text: t(openN ? "passport.cases_error" : "passport.no_open") })];
        } else {
          var hist = historyRows(cases);
          if (it.daily && it.daily.length) {
            var max = Math.max.apply(null, it.daily.concat([1]));
            panel.push(h("div", { class: "bq-sec" }, [h("p", { class: "bq-h3", text: t("target.by_day") }),
              h("div", { class: "bk-spark bq-spark", "aria-hidden": "true" }, it.daily.map(function (n) {
                var bar = h("i"); bar.style.height = Math.max(n ? 8 : 2, Math.round((n / max) * 100)) + "%"; return bar; }))]));
          }
          if (hist.length) panel.push(h("ol", { class: "bq-list bq-history" }, hist.map(function (e) {
            return h("li", { class: "bq-row bq-hist" }, [h("time", { datetime: String(e.at), text: fmtDate(e.at) }),
              h("span", { class: "bk-status", "data-status": e.status === "verified_fixed" ? "verified" : e.status, text: t(statusKey(e.status)) })]);
          })));
        }
      }
      var anim = S.tabAnim; S.tabAnim = false;
      out.push(h("div", { class: "bq-panel bq-rows" + (anim ? " bq-panel--in" : ""), id: "bq-panel", role: "tabpanel", "aria-labelledby": "bq-tab-" + S.tab, "data-tab": S.tab }, panel));
      return out;
    }

    function onLang() { render(); }
    root.addEventListener && root.addEventListener("birge:lang", onLang);
    var unsub = i18n() && i18n().onChange ? i18n().onChange(onLang) : null;
    function destroy() {
      if (destroyed) return;
      destroyed = true;
      S.seq++;
      root.removeEventListener && root.removeEventListener("birge:lang", onLang);
      if (typeof unsub === "function") unsub();
      if (box.parentNode) box.parentNode.removeChild(box);
    }
    render();
    return { open: open, destroy: destroy, info: function () { return S.info; }, state: function () { return { id: S.id, state: S.state, error: S.error, main: S.info ? mainAction(S.heat, S.info.target) : null }; } };
  }

  return { mount: mount, parseReportId: parseReportId, kindKey: kindKey, mainAction: mainAction, REPORT_ID_RE: REPORT_ID_RE,
    statusKey: statusKey, groupDigits: groupDigits, kindCat: kindCat, tileTone: tileTone, historyRows: historyRows, kindIcon: kindIcon, PENDING: PENDING, version: "r12-reference-a-1" };
});
