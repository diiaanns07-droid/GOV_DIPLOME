/*
 * R12 · раунд 14, волна 2 п. 6 · QR-паспорт объекта: ссылка /?report=<target_id> → лёгкая карточка объекта.
 *
 * Что на экране (UX: одна главная кнопка, остальное свёрнуто — POLISH_WAVE_2 «Защита от перегруза» п. 3–4):
 *   что это (остановка / перекрёсток / участок улицы / двор) и номер объекта; сколько людей сообщили и статус;
 *   ГЛАВНАЯ кнопка: «Я тоже», если есть открытые обращения, иначе «Сообщить о проблеме здесь»;
 *   вторая — «Сообщить о другом» (только рядом с «Я тоже»); «Подробнее»: жалобы по дням, темы, «Открыть на карте».
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

  // Запасные тексты, пока ключей нет в словарях R11 (как только ключ появится в ru.json/kk.json — побеждает словарь).
  var PENDING = {
    ru: {
      "qr.card.eyebrow_qr": "По QR-коду",
      "qr.kind.bus_stop": "Остановка", "qr.kind.playground": "Детская площадка", "qr.kind.pitch": "Спортплощадка",
      "qr.kind.park": "Парк или сквер", "qr.kind.waste": "Контейнерная площадка", "qr.kind.traffic_signal": "Светофор",
      "qr.kind.crossing": "Пешеходный переход", "qr.kind.intersection": "Перекрёсток", "qr.kind.segment": "Участок улицы",
      "qr.kind.yard": "Двор", "qr.kind.cell": "Примерное место", "qr.kind.object": "Объект",
      "qr.card.number": "Объект № {number}",
      "qr.card.none": "Здесь пока никто не сообщал о проблемах",
      "qr.card.for_days": "за {n} дней",
      "qr.card.metoo": "Я тоже", "qr.card.metoo_done": "Вы уже отметились — сообщим о ходе решения",
      "qr.card.metoo_thanks": "Спасибо. Будем сообщать о ходе решения",
      "qr.card.report_here": "Сообщить о проблеме здесь", "qr.card.report_other": "Сообщить о другом",
      "qr.card.more": "Подробнее", "qr.card.by_day": "Жалобы по дням", "qr.card.topics": "О чём сообщают",
      "qr.card.open_map": "Открыть на карте", "qr.card.approximate": "Место примерное — показано областью",
      "qr.card.demo": "Пример", "qr.card.demo_note": "Демонстрационные данные, не реальные обращения",
      "qr.card.loading": "Загружаем объект…",
      "qr.error.not_found": "Объект не найден. Возможно, QR-код устарел.",
      "qr.error.bad_link": "В ссылке неверный номер объекта.",
      "qr.error.network": "Нет связи. Проверьте интернет и повторите.",
      "qr.error.server": "Сервер не ответил. Повторите через минуту.",
      "qr.error.metoo": "Не удалось отметиться. Повторите.",
      "qr.error.open_map": "Открыть карту",
      "status.new": "Новое", "status.accepted": "Принято", "status.in_progress": "В работе", "status.fixed": "Исправлено",
      "status.rejected": "Отклонено", "status.label": "Статус",
      "common.action.close": "Закрыть", "common.action.retry": "Повторить",
    },
    kk: {
      "qr.card.eyebrow_qr": "QR-код бойынша",
      "qr.kind.bus_stop": "Аялдама", "qr.kind.playground": "Балалар алаңы", "qr.kind.pitch": "Спорт алаңы",
      "qr.kind.park": "Саябақ немесе гүлзар", "qr.kind.waste": "Қоқыс алаңы", "qr.kind.traffic_signal": "Бағдаршам",
      "qr.kind.crossing": "Жаяу жүргіншілер өткелі", "qr.kind.intersection": "Қиылыс", "qr.kind.segment": "Көше бөлігі",
      "qr.kind.yard": "Аула", "qr.kind.cell": "Шамамен орны", "qr.kind.object": "Нысан",
      "qr.card.number": "Нысан № {number}",
      "qr.card.none": "Мұнда әзірге ешкім мәселе туралы хабарламаған",
      "qr.card.for_days": "{n} күнде",
      "qr.card.metoo": "Мен де", "qr.card.metoo_done": "Сіз белгі қойғансыз — шешілу барысын хабарлаймыз",
      "qr.card.metoo_thanks": "Рақмет. Шешілу барысын хабарлап отырамыз",
      "qr.card.report_here": "Осы жердегі мәселе туралы хабарлау", "qr.card.report_other": "Басқа мәселе туралы хабарлау",
      "qr.card.more": "Толығырақ", "qr.card.by_day": "Күндер бойынша шағымдар", "qr.card.topics": "Не туралы хабарлайды",
      "qr.card.open_map": "Картадан ашу", "qr.card.approximate": "Орны шамамен — аймақпен көрсетілген",
      "qr.card.demo": "Мысал", "qr.card.demo_note": "Демонстрациялық деректер, нақты өтініштер емес",
      "qr.card.loading": "Нысан жүктелуде…",
      "qr.error.not_found": "Нысан табылмады. QR-код ескірген болуы мүмкін.",
      "qr.error.bad_link": "Сілтемеде нысан нөмірі қате.",
      "qr.error.network": "Байланыс жоқ. Интернетті тексеріп, қайталаңыз.",
      "qr.error.server": "Сервер жауап бермеді. Бір минуттан соң қайталаңыз.",
      "qr.error.metoo": "Белгі қою мүмкін болмады. Қайталаңыз.",
      "qr.error.open_map": "Картаны ашу",
      "status.new": "Жаңа", "status.accepted": "Қабылданды", "status.in_progress": "Орындалуда", "status.fixed": "Түзетілді",
      "status.rejected": "Қабылданбады", "status.label": "Мәртебе",
      "common.action.close": "Жабу", "common.action.retry": "Қайталау",
    },
  };

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
    var B = i18n();
    if (B && B.has && (B.has(key) || B.has(key, "ru"))) return B.t(key, params);
    var l = lang();
    return fill((PENDING[l] && PENDING[l][key]) || PENDING.ru[key] || key, params);
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
  function kindKey(target) {
    if (!target) return "qr.kind.object";
    if (target.kind === "object") return "qr.kind." + (target.object_kind || "object");
    if (target.kind === "segment") return "qr.kind.segment";
    return String(target.id || "").indexOf("cell-") === 0 ? "qr.kind.cell" : "qr.kind.yard";
  }
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
    var open = heatItem && heatItem.status !== "fixed" && (heatItem.open_ids || []).length > 0;
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
    var S = { id: null, info: null, heat: null, state: "idle", error: null, seq: 0, notice: null, busy: false, detailsOpen: false };
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
      return fetchFn(api + path, { method: "POST", credentials: "same-origin",
        headers: { Accept: "application/json", "Content-Type": "application/json" }, body: JSON.stringify(body) })
        .then(function (r) { if (!r.ok) { var e = new Error("HTTP " + r.status); e.status = r.status; throw e; } return r.json().catch(function () { return {}; }); });
    }

    function open(id) {
      var my = ++S.seq;
      S.id = id; S.info = null; S.heat = null; S.notice = null; S.error = null;
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
        S.state = "ready"; render();
      }, function (err) {
        if (destroyed || my !== S.seq) return;
        S.heat = null;
        S.state = "ready";
        // Тепловая карта недоступна (сеть/модуль) — карточку объекта всё равно показываем, без чисел.
        S.heatUnavailable = !(err && err.status === 404);
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
        S.busy = false; S.notice = { ok: true, text: t("qr.card.metoo_thanks") };
        // R07 слушает это событие и перерисует тепловую карту (как после «Я тоже» в мастере R09).
        try { root.dispatchEvent(new root.CustomEvent("birge:complaint", { detail: { type: "metoo", complaint_id: id, target: tg } })); } catch (e) { /* */ }
        return loadHeat(S.seq);
      }, function () {
        if (destroyed) return;
        S.busy = false; S.notice = { ok: false, text: t("qr.error.metoo") }; render();
      });
    }
    function report() {
      if (typeof opts.onReport === "function") opts.onReport({ target: S.info.target, point: S.info.point, geometry: S.info.geometry,
        approximate: !!S.info.approximate });
    }

    function render() {
      if (destroyed) return;
      box.setAttribute("data-state", S.state);
      box.lang = lang();
      var kids = [];
      var head = h("div", { class: "bq-report__nav" }, [
        h("button", { type: "button", class: "bk-iconbtn bq-report__close", "aria-label": t("common.action.close"), title: t("common.action.close"),
          onclick: function () { if (typeof opts.onClose === "function") opts.onClose(); destroy(); } }, [icon("close", sprite)])]);
      kids.push(head);
      if (S.state === "loading" || S.state === "idle") {
        kids.push(h("div", { class: "bq-skel", "aria-busy": "true" }, [
          h("span", { class: "bk-sr-only", text: t("qr.card.loading") }),
          h("i", { class: "bk-skel bk-skel--line" }), h("i", { class: "bk-skel bk-skel--title" }), h("i", { class: "bk-skel bk-skel--block" })]));
      } else if (S.state === "error") {
        var retry = S.error === "network" || S.error === "server";
        kids.push(h("div", { class: "bk-error bq-error", role: "alert" }, [
          h("p", { class: "bk-error__title", text: t("qr.error." + S.error) }),
          h("div", { class: "bq-actions" }, [
            retry ? h("button", { type: "button", class: "bk-btn bk-btn--primary bk-btn--block", "data-act": "retry", onclick: function () { open(S.id); } }, [icon("refresh", sprite), t("common.action.retry")]) : null,
            typeof opts.onOpenMap === "function" ? h("button", { type: "button", class: "bk-btn bk-btn--ghost bk-btn--block", "data-act": "map",
              onclick: function () { opts.onOpenMap(null); } }, [t("qr.error.open_map")]) : null])]));
      } else {
        kids = kids.concat(card());
      }
      box.replaceChildren.apply(box, kids);
    }

    function card() {
      var info = S.info, tg = info.target, it = S.heat, l = lang();
      var title = (l === "kk" ? tg.label_kk : tg.label_ru) || tg.label_ru;
      var demo = !!(it && it.demo);
      var out = [];
      out.push(h("p", { class: "bk-card__eyebrow bq-eyebrow" }, [
        icon(tg.kind === "segment" ? "road" : tg.kind === "area" ? "pin" : tg.object_kind === "bus_stop" ? "bus" : "pin", sprite),
        t(kindKey(tg)), h("span", { class: "bq-sep", text: "·" }), t("qr.card.eyebrow_qr"),
        demo ? h("span", { class: "bk-tag bk-tag--demo", text: t("qr.card.demo") }) : null]));
      out.push(h("h2", { class: "bq-title", tabindex: "-1", text: title }));
      out.push(h("p", { class: "bq-number", text: t("qr.card.number", { number: info.number }) }));
      if (info.approximate) out.push(h("p", { class: "bk-tag bk-tag--approx bq-approx", text: t("qr.card.approximate") }));
      // Сколько людей и статус — сразу под заголовком: видно без прокрутки на 375 px.
      if (it && it.count > 0) {
        out.push(h("p", { class: "bq-reported" }, [h("b", { text: reportedText(it.count) }), " · " + t("qr.card.for_days", { n: DAYS })]));
        out.push(h("p", { class: "bq-status" }, [t("status.label") + ": ",
          h("span", { class: "bk-status", "data-status": it.status, text: t("status." + it.status) })]));
      } else if (!S.heatUnavailable) {
        out.push(h("p", { class: "bq-none", text: t("qr.card.none") }));
      }
      if (demo) out.push(h("p", { class: "bq-demo-note", text: t("qr.card.demo_note") }));
      // Одна главная кнопка (UX_BRIEF п. 3, POLISH_WAVE_2 защита п. 4).
      var main = mainAction(it, tg), actions = [];
      if (main === "metoo") {
        actions.push(h("button", { type: "button", class: "bk-btn bk-btn--primary bk-btn--lg bk-btn--block", "data-act": "metoo",
          "aria-busy": S.busy ? "true" : null, disabled: S.busy, onclick: metoo }, [icon("users", sprite), t("qr.card.metoo")]));
        actions.push(h("button", { type: "button", class: "bk-btn bk-btn--ghost bk-btn--block", "data-act": "report-other", onclick: report },
          [t("qr.card.report_other")]));
      } else {
        if (it && it.status !== "fixed" && (it.open_ids || []).length && metooDone(tg)) {
          out.push(h("p", { class: "bq-done" }, [icon("check", sprite), t("qr.card.metoo_done")]));
        }
        actions.push(h("button", { type: "button", class: "bk-btn bk-btn--primary bk-btn--lg bk-btn--block", "data-act": "report", onclick: report },
          [icon("send", sprite), t(it && it.count > 0 && it.status !== "fixed" ? "qr.card.report_other" : "qr.card.report_here")]));
      }
      out.push(h("div", { class: "bq-actions" }, actions));
      if (S.notice) out.push(h("p", { class: "bq-notice" + (S.notice.ok ? " bq-notice--ok" : " bq-notice--error"), role: S.notice.ok ? "status" : "alert", text: S.notice.text }));
      // Остальное — свёрнуто.
      var more = [];
      if (it && (it.daily || []).length) {
        var max = Math.max.apply(null, it.daily.concat([1]));
        more.push(h("h3", { class: "bq-h3", text: t("qr.card.by_day") }));
        more.push(h("div", { class: "bk-spark bq-spark", "aria-hidden": "true" }, it.daily.map(function (n) {
          var bar = h("i"); bar.style.height = Math.max(n ? 8 : 2, Math.round((n / max) * 100)) + "%"; return bar; })));
      }
      var topics = it && it.by_category ? Object.keys(it.by_category) : [];
      if (topics.length) {
        more.push(h("h3", { class: "bq-h3", text: t("qr.card.topics") }));
        more.push(h("ul", { class: "bq-topics" }, topics.map(function (c) { return h("li", {}, [h("span", { text: catName(c) }), h("b", { text: String(it.by_category[c]) })]); })));
      }
      if (typeof opts.onOpenMap === "function") {
        more.push(h("button", { type: "button", class: "bk-btn bk-btn--ghost bq-map", "data-act": "map", onclick: function () { opts.onOpenMap(tg); } },
          [icon("pin", sprite), t("qr.card.open_map")]));
      }
      if (more.length) {
        var det = h("details", { class: "bq-more", open: S.detailsOpen ? true : null }, [h("summary", { text: t("qr.card.more") })].concat(more));
        det.addEventListener("toggle", function () { S.detailsOpen = det.open; });
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
    return { open: open, destroy: destroy, state: function () { return { id: S.id, state: S.state, error: S.error, main: S.info ? mainAction(S.heat, S.info.target) : null }; } };
  }

  return { mount: mount, parseReportId: parseReportId, kindKey: kindKey, mainAction: mainAction, REPORT_ID_RE: REPORT_ID_RE,
    PENDING: PENDING, version: "r12-wave2-qr-1" };
});
