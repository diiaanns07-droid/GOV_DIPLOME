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
    var B = i18n();
    if (B && B.has && B.has("cat." + id)) return B.t("cat." + id);
    return id;
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
  var KIND_ICON = { bus_stop: "bus", crossing: "walk", intersection: "road", playground: "playground", pitch: "ball",
    park: "trees", waste: "trash" };
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
    var S = { id: null, info: null, heat: null, state: "idle", error: null, seq: 0, notice: null, busy: false, detailsOpen: false,
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
      S.id = id; S.info = null; S.heat = null; S.notice = null; S.error = null; S.enter = true;
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
        if (S.detailsOpen) loadCases();
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
        S.busy = false; S.notice = { ok: true, text: t("heat.toast_metoo") };
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
        kids = [top([h("i", { class: "bk-skel bk-skel--line bq-skel__eyebrow" })]),
          h("div", { class: "bq-skel", "aria-busy": "true" }, [
            h("span", { class: "bk-sr-only", text: t("map.card.loading") }),
            h("i", { class: "bk-skel bk-skel--title" }), h("i", { class: "bk-skel bk-skel--line bq-skel__short" }),
            h("i", { class: "bk-skel bk-skel--line" }), h("i", { class: "bk-skel bq-skel__button" })])];
      } else if (S.state === "error") {
        kids = [top([])].concat(errorView());
      } else {
        kids = card();
        if (S.enter) { box.classList.add("bq-enter"); S.enter = false; } else box.classList.remove("bq-enter");
      }
      box.replaceChildren.apply(box, kids);
    }
    // Верхняя строка во всех состояниях: вид объекта слева, крестик справа (не поверх скелетона и текста).
    function top(content) {
      return h("div", { class: "bq-top" }, [h("p", { class: "bq-eyebrow" }, content),
        h("button", { type: "button", class: "bk-iconbtn bq-report__close", "aria-label": t("common.action.close"), title: t("common.action.close"),
          onclick: function () { if (typeof opts.onClose === "function") opts.onClose(); destroy(); } }, [icon("close", sprite)])]);
    }
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
          retry ? h("button", { type: "button", class: "bk-btn bk-btn--primary bk-btn--block", "data-act": "retry", onclick: function () { open(S.id); } }, [icon("refresh", sprite), t("common.action.retry")]) : null,
          typeof opts.onOpenMap === "function" ? h("button", { type: "button", class: "bk-btn bk-btn--block " + (retry ? "bk-btn--ghost" : "bk-btn--primary"),
            "data-act": "map", onclick: function () { opts.onOpenMap(null); } }, [icon("pin", sprite), t("complaint.step5.to_map")]) : null])])];
    }

    function card() {
      var info = S.info, tg = info.target, it = S.heat, l = lang();
      var title = (l === "kk" ? tg.label_kk : tg.label_ru) || tg.label_ru;
      var demo = !!(it && it.demo);
      var kk = kindKey(tg), kindWord = kk ? t(kk) : "";
      // Слово вида не повторяем, если заголовок с него начинается («Светофор на перекрёстке…», «Контейнерная площадка»).
      if (kindWord && title.toLowerCase().indexOf(kindWord.toLowerCase()) === 0) kindWord = "";
      var out = [top([icon(kindIcon(tg), sprite), kindWord ? h("span", { text: kindWord }) : null,
        demo ? h("span", { class: "bk-tag bk-tag--demo", text: t("common.tag.demo") }) : null])];
      out.push(h("h2", { class: "bq-title", tabindex: "-1", text: title }));
      out.push(h("p", { class: "bq-number", text: t("qr.object_no", { id: groupDigits(info.number) }) }));
      if (info.approximate) out.push(h("p", { class: "bk-tag bk-tag--approx bq-approx", text: t("common.tag.approx") }));
      // Статус и сколько людей — сразу под заголовком (видно без прокрутки на 375 px), как строка статуса ui-kit:
      // «● Новое» / «Сообщили 5 человек · за 30 дней». Жалоб нет — блока нет (IA_WAVE2 §0 п. 6).
      if (it && it.count > 0) {
        var notes = [h("span", { class: "bk-statusline__note bq-reported" }, [h("b", { text: reportedText(it.count) }), " · " + t("common.period.last_days", { n: DAYS })])];
        if (isFixed(it) && it.fixed_until) notes.push(h("span", { class: "bk-statusline__note", text: t("heat.fixed_until", { date: fmtDate(it.fixed_until) }) }));
        out.push(h("div", { class: "bk-statusline bq-statusline" }, [h("span", { class: "bk-status", "data-status": it.status === "verified_fixed" ? "verified" : it.status,
          "aria-label": t("status.label") + ": " + t(statusKey(it.status)), text: t(statusKey(it.status)) })].concat(notes)));
      }
      // Одна главная кнопка (UX_BRIEF п. 3, POLISH_WAVE_2 защита п. 4).
      var main = mainAction(it, tg), actions = [];
      if (main === "metoo") {
        actions.push(h("button", { type: "button", class: "bk-btn bk-btn--primary bk-btn--lg bk-btn--block", "data-act": "metoo",
          "aria-busy": S.busy ? "true" : null, disabled: S.busy, onclick: metoo }, [icon("users", sprite), t("target.metoo")]));
        actions.push(h("button", { type: "button", class: "bk-btn bk-btn--ghost bk-btn--block", "data-act": "report-other", onclick: report },
          [t("report.other")]));
      } else {
        // Одно подтверждение: сразу после «Я тоже» — «Спасибо…» (ниже), иначе — тихая строка «Вы отметили «Я тоже»».
        if (it && !isFixed(it) && (it.open_ids || []).length && metooDone(tg) && !(S.notice && S.notice.ok)) {
          out.push(h("p", { class: "bq-done" }, [icon("check", sprite), t("target.metoo_done")]));
        }
        actions.push(h("button", { type: "button", class: "bk-btn bk-btn--primary bk-btn--lg bk-btn--block", "data-act": "report", onclick: report },
          [icon("send", sprite), t(it && it.count > 0 && !isFixed(it) ? "report.other" : "report.here")]));
      }
      // Подтверждение или ошибка — над кнопкой, где житель смотрит (на телефоне ниже кнопки его не видно).
      if (S.notice) out.push(h("p", { class: "bq-notice" + (S.notice.ok ? " bq-notice--ok" : " bq-notice--error"), role: S.notice.ok ? "status" : "alert" },
        [icon(S.notice.ok ? "check" : "alert", sprite), h("span", { text: S.notice.text })]));
      out.push(h("div", { class: "bq-actions" }, actions));
      // Остальное — свёрнуто (ui-kit .bk-details: стрелка, 48 px).
      var more = [];
      var section = function (key, body) { more.push(h("section", { class: "bq-sec" }, [h("h3", { class: "bq-h3", text: t(key) })].concat(body))); };
      if (it && (it.daily || []).length) {
        var max = Math.max.apply(null, it.daily.concat([1]));
        section("target.by_day", [h("div", { class: "bk-spark bq-spark", "aria-hidden": "true" }, it.daily.map(function (n) {
          var bar = h("i"); bar.style.height = Math.max(n ? 8 : 2, Math.round((n / max) * 100)) + "%"; return bar; }))]);
      }
      var topics = it && it.by_category ? Object.keys(it.by_category) : [];
      if (topics.length) {
        section("heat.topics", [h("ul", { class: "bq-rows" }, topics.map(function (c) {
          return h("li", { class: "bq-row" }, [h("span", { text: catName(c) }), h("b", { class: "bq-row__num", text: String(it.by_category[c]) })]); }))]);
      }
      var cases = S.cases && S.cases.rows;
      if (cases && cases.length) {
        section("qr.card.complaints", [h("ul", { class: "bq-rows bq-cases" }, cases.map(function (c) {
          var st = c.heat_state || c.status, open = !isFixed({ status: st }) && c.status !== "rejected";
          return h("li", { class: "bq-case" }, [h("span", { class: "bq-case__what" }, [catName(c.category) + " · ",
              h("span", { class: "bk-status bq-case__status", "data-status": st === "verified_fixed" ? "verified" : st, text: t(statusKey(st)) })]),
            h("span", { class: "bq-case__meta", text: reportedText(c.reporters || 1) +
              (open && c.due_at ? " · " + t("passport.answer_due", { date: fmtDate(c.due_at) }) : "") })]);
        }))]);
        var hist = historyRows(cases);
        if (hist.length) {
          section("passport.history", [h("ol", { class: "bq-rows bq-history" }, hist.map(function (e) {
            return h("li", { class: "bq-hist" }, [h("time", { datetime: String(e.at), text: fmtDate(e.at) }), h("span", { text: t(statusKey(e.status)) })]);
          }))]);
        }
      }
      if (typeof opts.onOpenMap === "function") {
        more.push(h("button", { type: "button", class: "bk-btn bk-btn--ghost bq-map", "data-act": "map", onclick: function () { opts.onOpenMap(tg); } },
          [icon("pin", sprite), t("complaint.step5.to_map")]));
      }
      if (more.length) {
        var det = h("details", { class: "bk-details bq-more", open: S.detailsOpen ? true : null }, [h("summary", { text: t("common.action.more") })].concat(more));
        det.addEventListener("toggle", function () { S.detailsOpen = det.open; if (det.open) loadCases(); });
        out.push(det);
      }
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
    statusKey: statusKey, groupDigits: groupDigits, historyRows: historyRows, kindIcon: kindIcon, PENDING: PENDING, version: "r12-marathon-qr-3" };
});
