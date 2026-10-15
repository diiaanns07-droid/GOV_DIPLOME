/*
 * R12 · волна 2 п. 6 · Лист печати QR-табличек для акимата (web/civic/qr/print.html).
 * Для каждого объекта: QR-код ссылки <сайт>/?report=<id>, крупно — короткий адрес (ru и kk), номер объекта и адрес сайта.
 * Табличка висит на улице, поэтому всегда на двух языках (независимо от языка интерфейса).
 *
 * Генератор QR — qrcode-generator 1.4.4 (Kazuhiko Arase, MIT) в web/vendor/qrcode/qrcode.js (задача LOCAL-11).
 * Пока его нет — вместо кода честная заглушка и ссылка крупным шрифтом; печатать такие листы не предлагаем.
 * Защита от подмены (R15): в QR только адрес сайта + ?report=<id> (id проверяется тем же правилом, что на сервере);
 * под кодом крупно напечатан адрес сайта — житель видит, куда ведёт код.
 *
 * Параметры страницы: ?ids=osm-node-1,osm-way-2&base=https://birge.astana.kz (base — только схема и хост).
 */
(function (root, factory) {
  "use strict";
  var api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BirgeQrPrint = api;
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var API = "/api/civic/v2";
  var MAX_IDS = 24;
  var ID_RE = /^(osm-(node|way|relation)-[0-9]{1,15}|osm-w[0-9]{1,15}-[0-9]{1,6}|yard-r?[0-9]{1,15}(-[0-9]{1,3})?|cell--?[0-9]{1,6}--?[0-9]{1,6})$/;

  // Тексты. Ключи словаря R11 (qr.title, qr.print, qr.call, qr.object_no — IA_WAVE2 §6.2) берутся из BirgeI18n;
  // остальное — форма для сотрудника (ключи qr.form.* переданы R11 в i18n_keys.json). Табличка — всегда kk + ru.
  var TEXT = {
    ru: {
      "qr.title": "QR-таблички объектов", "qr.print": "Распечатать QR", "qr.call": "Есть проблема с этим местом? Наведите камеру телефона на код",
      "qr.object_no": "Объект № {id}",
      "qr.form.lead": "Распечатайте и повесьте на остановке, площадке или у перекрёстка. Житель наводит камеру — открывается карточка объекта.",
      "qr.form.ids": "Номера объектов", "qr.form.ids_hint": "Через запятую или с новой строки, например osm-node-10185771782. Не больше 24.",
      "qr.form.base": "Адрес сайта на табличке", "qr.form.base_hint": "Только адрес сайта, например https://birge.astana.kz",
      "qr.form.show": "Показать таблички", "qr.form.none": "Добавьте номера объектов, чтобы увидеть таблички.",
      "qr.form.not_found": "Объект {id} не найден — табличка не будет напечатана.", "qr.form.bad_id": "«{id}» — не номер объекта.",
      "qr.form.too_many": "Не больше {n} объектов за раз.", "qr.form.bad_base": "Адрес сайта должен начинаться с https:// или http:// и не содержать пути.",
      "qr.form.no_qr": "Генератор QR ещё не подключён. Пока на табличке будет только ссылка.",
      "qr.form.network": "Нет связи. Повторите.", "qr.form.loading": "Загружаем…", "qr.form.ready": "Готово табличек: {n}",
      "qr.form.updated": "Номер {old} обновлён по свежей карте OSM: на табличке — {id}.",
      "qr.form.gone": "Объекта {id} нет в свежей карте OSM — проверьте на месте перед печатью.",
      "qr.form.base_other": "QR на табличках поведёт на {base} — это не адрес этого сервера. Проверьте адрес перед печатью.",
      "qr.sign.call": "Сообщите о проблеме", "qr.sign.how": "Наведите камеру телефона на код",
      "qr.form.size": "Размер таблички", "qr.form.size_a5": "A5 · 148 × 210 мм", "qr.form.size_a6": "A6 · 105 × 148 мм",
      "qr.form.size_hint": "Печать на листах A4: две таблички A5 или четыре A6 — разрезать по пунктиру.",
    },
    kk: {
      "qr.title": "Нысандардың QR-тақтайшалары", "qr.print": "QR басып шығару", "qr.call": "Осы жерде мәселе бар ма? Телефон камерасын кодқа бағыттаңыз",
      "qr.object_no": "Нысан № {id}",
      "qr.form.lead": "Басып шығарып, аялдамаға, алаңға немесе қиылысқа іліңіз. Тұрғын камераны бағыттайды — нысан карточкасы ашылады.",
      "qr.form.ids": "Нысан нөмірлері", "qr.form.ids_hint": "Үтір арқылы немесе жаңа жолдан, мысалы osm-node-10185771782. 24-тен аспасын.",
      "qr.form.base": "Тақтайшадағы сайт мекенжайы", "qr.form.base_hint": "Тек сайт мекенжайы, мысалы https://birge.astana.kz",
      "qr.form.show": "Тақтайшаларды көрсету", "qr.form.none": "Тақтайшаларды көру үшін нысан нөмірлерін қосыңыз.",
      "qr.form.not_found": "{id} нысаны табылмады — тақтайша басылмайды.", "qr.form.bad_id": "«{id}» — нысан нөмірі емес.",
      "qr.form.too_many": "Бір ретте {n} нысаннан аспасын.", "qr.form.bad_base": "Сайт мекенжайы https:// немесе http:// деп басталып, жолсыз болуы керек.",
      "qr.form.no_qr": "QR генераторы әлі қосылмаған. Әзірге тақтайшада тек сілтеме болады.",
      "qr.form.network": "Байланыс жоқ. Қайталаңыз.", "qr.form.loading": "Жүктелуде…", "qr.form.ready": "Дайын тақтайшалар: {n}",
      "qr.form.updated": "{old} нөмірі OSM-нің жаңа картасы бойынша жаңартылды: тақтайшада — {id}.",
      "qr.form.gone": "{id} нысаны OSM-нің жаңа картасында жоқ — басып шығарар алдында орнында тексеріңіз.",
      "qr.form.base_other": "Тақтайшадағы QR {base} мекенжайына апарады — бұл осы сервердің мекенжайы емес. Басып шығарар алдында тексеріңіз.",
      "qr.sign.call": "Мәселе туралы хабарлаңыз", "qr.sign.how": "Телефон камерасын кодқа бағыттаңыз",
      "qr.form.size": "Тақтайша өлшемі", "qr.form.size_a5": "A5 · 148 × 210 мм", "qr.form.size_a6": "A6 · 105 × 148 мм",
      "qr.form.size_hint": "A4 парағына басылады: екі A5 немесе төрт A6 тақтайша — үзік сызық бойымен қиыңыз.",
    },
  };

  function lang() {
    var B = root.BirgeI18n;
    var l = B && B.getLang ? B.getLang() : (root.document && root.document.documentElement.lang) || "ru";
    return l === "kk" ? "kk" : "ru";
  }
  // l — язык явно (табличка печатается на обоих языках сразу); без него — язык интерфейса.
  function tx(key, params, l) {
    var B = root.BirgeI18n, use = l || lang();
    if (B && B.has && B.has(key, use) && typeof B.t === "function") return B.t(key, params, use);
    var s = (TEXT[use] || TEXT.ru)[key] || TEXT.ru[key] || key;
    return params ? s.replace(/\{(\w+)\}/g, function (w, n) { return params[n] == null ? w : String(params[n]); }) : s;
  }

  // ---------- чистые функции ----------
  function parseIds(text) {
    var out = [], bad = [];
    String(text || "").split(/[\s,;]+/).forEach(function (raw) {
      var id = raw.trim();
      if (!id) return;
      if (!ID_RE.test(id)) { bad.push(id.slice(0, 60)); return; }
      if (out.indexOf(id) < 0) out.push(id);
    });
    return { ids: out, bad: bad };
  }
  // Только схема и хост (с портом): «https://birge.astana.kz». Путь, запрос, логин в адресе — отказ.
  function normalizeBase(text) {
    var s = String(text || "").trim().replace(/\/+$/, "");
    var m = /^(https?):\/\/([A-Za-z0-9.-]+(?::[0-9]{1,5})?)$/.exec(s);
    return m ? m[1].toLowerCase() + "://" + m[2].toLowerCase() : null;
  }
  // Номер объекта крупно — группами по 3 цифры («10 272 524 280», UX_REVIEW R11 волна 2 разбор 2 п. 3); Д-…/К-… как есть.
  function groupDigits(num) {
    var s = String(num == null ? "" : num);
    return /^[0-9]{5,}$/.test(s) ? s.replace(/\B(?=([0-9]{3})+(?![0-9]))/g, "\u00a0") : s;
  }
  function reportUrl(base, id) { return base + "/?report=" + encodeURIComponent(id); }
  function domainOf(base) { return base.replace(/^https?:\/\//, ""); }

  // QR как SVG из квадратиков (а не строкой createSvgTag): ничего чужого не попадает в разметку.
  function qrSvg(doc, text) {
    var gen = root.qrcode;
    if (typeof gen !== "function") return null;
    var qr = gen(0, "M");  // 0 — размер подбирается сам; M — 15% восстановления (табличка пачкается)
    qr.addData(text);
    qr.make();
    var n = qr.getModuleCount(), q = 4; // тихая зона 4 модуля (стандарт QR)
    var NS = "http://www.w3.org/2000/svg";
    var svg = doc.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + (n + 2 * q) + " " + (n + 2 * q));
    svg.setAttribute("class", "bqp-qr__svg");
    svg.setAttribute("role", "img");
    svg.setAttribute("shape-rendering", "crispEdges");
    var bg = doc.createElementNS(NS, "rect");
    bg.setAttribute("width", String(n + 2 * q)); bg.setAttribute("height", String(n + 2 * q)); bg.setAttribute("fill", "#fff");
    svg.appendChild(bg);
    var d = "";
    for (var r = 0; r < n; r++) for (var c = 0; c < n; c++) if (qr.isDark(r, c)) d += "M" + (c + q) + " " + (r + q) + "h1v1h-1z";
    var path = doc.createElementNS(NS, "path");
    path.setAttribute("d", d); path.setAttribute("fill", "#000");
    svg.appendChild(path);
    return svg;
  }

  function h(doc, tag, attrs, kids) {
    var e = doc.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = String(v);
      else if (k.indexOf("on") === 0 && typeof v === "function") e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : String(v));
    });
    (kids || []).forEach(function (c) { if (c !== null && c !== undefined && c !== false) e.append(c.nodeType ? c : doc.createTextNode(String(c))); });
    return e;
  }

  // Уличная табличка (дизайн-марафон, IA_WAVE2 §6.2): тёмная полоса Birge с призывом kk и ru, крупный QR (≥ 6 см и на A6),
  // как навести камеру, адрес сайта (видно, куда ведёт код — защита от подмены), название kk и ru, номер объекта.
  // Чисел жалоб и статусов нет — табличка висит годами. Размеры — от ширины таблички (cqw), поэтому A5 и A6 одинаковы по виду.
  var SIZES = { a5: { w: 148, h: 210 }, a6: { w: 105, h: 148 } };
  function normalizeSize(v) { return v === "a6" ? "a6" : "a5"; }
  function svgIcon(doc, name) {
    var NS = "http://www.w3.org/2000/svg", svg = doc.createElementNS(NS, "svg"), use = doc.createElementNS(NS, "use");
    svg.setAttribute("class", "ic"); svg.setAttribute("aria-hidden", "true"); svg.setAttribute("focusable", "false");
    use.setAttribute("href", "/civic/ui-kit/icons.svg#i-" + name);
    svg.appendChild(use);
    return svg;
  }
  function sign(doc, info, base, size) {
    var url = reportUrl(base, info.target.id);
    var qr = qrSvg(doc, url);
    if (qr) qr.setAttribute("aria-label", "QR: " + url);
    var ru = info.target.label_ru, kk = info.target.label_kk || ru;
    var num = groupDigits(info.number);
    return h(doc, "article", { class: "bqp-sign", "data-id": info.target.id, "data-size": size, "data-long": kk.length > 40 ? "1" : null }, [
      h(doc, "header", { class: "bqp-sign__band" }, [
        h(doc, "p", { class: "bqp-sign__brand" }, [h(doc, "span", { class: "bqp-sign__mark" }, [svgIcon(doc, "building")]), "Birge"]),
        h(doc, "p", { class: "bqp-sign__call", lang: "kk", text: tx("qr.sign.call", null, "kk") }),
        h(doc, "p", { class: "bqp-sign__call bqp-sign__call--ru", lang: "ru", text: tx("qr.sign.call", null, "ru") })]),
      h(doc, "div", { class: "bqp-sign__body" }, [
        h(doc, "div", { class: "bqp-qr" + (qr ? "" : " bqp-qr--missing") }, [qr || h(doc, "p", { class: "bqp-qr__missing", text: tx("qr.form.no_qr") })]),
        h(doc, "p", { class: "bqp-sign__how" }, [h(doc, "span", { lang: "kk", text: tx("qr.sign.how", null, "kk") }),
          h(doc, "span", { lang: "ru", text: tx("qr.sign.how", null, "ru") })]),
        h(doc, "p", { class: "bqp-sign__domain", text: domainOf(base) }),
        h(doc, "div", { class: "bqp-sign__place" }, [
          h(doc, "h2", { class: "bqp-sign__title", lang: "kk", text: kk }),
          kk !== ru ? h(doc, "p", { class: "bqp-sign__title-ru", lang: "ru", text: ru }) : null,
          h(doc, "p", { class: "bqp-sign__number" }, [tx("qr.object_no", { id: num }, "kk") + " · " + tx("qr.object_no", { id: num }, "ru")])])]),
      // Полная ссылка — для чтения с экрана и проверки (на самой табличке крупно только адрес сайта).
      h(doc, "p", { class: "bk-sr-only bqp-sign__url", text: url })]);
  }
  // Название не влезло (длинные kk и ru) — уменьшаем блок названия шагами, пока табличка не перестанет переполняться.
  function fitSign(el) {
    var place = el.querySelector(".bqp-sign__place");
    if (!place) return 1;
    var k = 1;
    place.style.removeProperty("--fit");
    while (el.scrollHeight > el.clientHeight + 1 && k > 0.6) {
      k = Math.round((k - 0.05) * 100) / 100;
      place.style.setProperty("--fit", String(k));
    }
    return k;
  }
  // Страница печати под размер: A5 — две на A4 альбомном, A6 — четыре на A4 книжном; поля 0, резать по пунктиру.
  function pageCss(size) {
    return size === "a6" ? "@page { size: A4 portrait; margin: 0; }" : "@page { size: A4 landscape; margin: 0; }";
  }

  function mount(options) {
    var opts = options || {};
    var doc = root.document, host = opts.root;
    var fetchFn = opts.fetch || root.fetch.bind(root);
    var api = opts.api || API;
    var params = new root.URLSearchParams(root.location.search);
    var S = { seq: 0, signs: [], messages: [], state: "idle" };

    var idsField = h(doc, "textarea", { id: "bqp-ids", rows: "3", "aria-describedby": "bqp-ids-hint", spellcheck: "false", autocomplete: "off" });
    idsField.value = (params.get("ids") || "").split(",").join("\n");
    var baseField = h(doc, "input", { id: "bqp-base", type: "url", inputmode: "url", "aria-describedby": "bqp-base-hint", autocomplete: "off" });
    baseField.value = params.get("base") || root.location.origin;
    var size = normalizeSize(params.get("size"));
    var pageStyle = doc.getElementById("bqp-page") || h(doc, "style", { id: "bqp-page" });
    if (!pageStyle.parentNode) doc.head.appendChild(pageStyle);
    pageStyle.textContent = pageCss(size);
    var sizeBtns = ["a5", "a6"].map(function (v) {
      return h(doc, "button", { type: "button", "data-size": v, "aria-pressed": String(v === size), onclick: function () { setSize(v); } }, [tx("qr.form.size_" + v)]);
    });
    var status = h(doc, "div", { class: "bqp-status", role: "status", "aria-live": "polite" });
    var sheet = h(doc, "div", { class: "bqp-sheet" });
    var showBtn = h(doc, "button", { type: "submit", class: "bk-btn bk-btn--primary", "data-act": "show" }, [tx("qr.form.show")]);
    var printBtn = h(doc, "button", { type: "button", class: "bk-btn bqp-print", "data-act": "print", onclick: function () { root.print(); } }, [tx("qr.print")]);
    var form = h(doc, "form", { class: "bqp-form no-print", novalidate: true }, [
      h(doc, "h1", { class: "bqp-h1", text: tx("qr.title") }),
      h(doc, "p", { class: "bqp-lead", text: tx("qr.form.lead") }),
      h(doc, "div", { class: "bk-field bqp-field" }, [h(doc, "label", { for: "bqp-ids", class: "bk-field__label", text: tx("qr.form.ids") }), idsField,
        h(doc, "p", { id: "bqp-ids-hint", class: "bk-field__hint", text: tx("qr.form.ids_hint") })]),
      h(doc, "div", { class: "bk-field bqp-field" }, [h(doc, "label", { for: "bqp-base", class: "bk-field__label", text: tx("qr.form.base") }), baseField,
        h(doc, "p", { id: "bqp-base-hint", class: "bk-field__hint", text: tx("qr.form.base_hint") })]),
      h(doc, "div", { class: "bk-field bqp-field", role: "group", "aria-labelledby": "bqp-size-l" }, [
        h(doc, "p", { id: "bqp-size-l", class: "bk-field__label", text: tx("qr.form.size") }),
        h(doc, "div", { class: "bk-seg bqp-size" }, sizeBtns),
        h(doc, "p", { class: "bk-field__hint", text: tx("qr.form.size_hint") })]),
      h(doc, "div", { class: "bqp-buttons" }, [
        showBtn, printBtn]),
      status]);
    form.addEventListener("submit", function (e) { e.preventDefault(); load(); });
    host.replaceChildren(form, sheet);
    doc.title = "Birge · " + tx("qr.title");
    function fitAll() { Array.prototype.forEach.call(sheet.children, fitSign); }
    // Шрифт мог догрузиться после первой раскладки — подбираем ещё раз.
    if (doc.fonts && doc.fonts.ready && typeof doc.fonts.ready.then === "function") doc.fonts.ready.then(function () { fitAll(); });
    function setSize(v) {
      size = normalizeSize(v);
      pageStyle.textContent = pageCss(size);
      sizeBtns.forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-size") === size)); });
      sheet.setAttribute("data-size", size);
      Array.prototype.forEach.call(sheet.children, function (el) { el.setAttribute("data-size", size); });
      fitAll();
    }
    sheet.setAttribute("data-size", size);

    function paintStatus() {
      status.replaceChildren.apply(status, S.messages.map(function (m) { return h(doc, "p", { class: "bqp-msg bqp-msg--" + m.kind, text: m.text }); }));
      // Печатать имеет смысл только готовые таблички с настоящим QR — иначе главная кнопка «Показать».
      printBtn.hidden = !(S.signs.length && typeof root.qrcode === "function");
      printBtn.className = "bk-btn bqp-print" + (printBtn.hidden ? "" : " bk-btn--primary");
      // Одна главная кнопка на экране: когда можно печатать, главная — «Печать», «Показать» становится обычной.
      showBtn.className = "bk-btn " + (printBtn.hidden ? "bk-btn--primary" : "bk-btn--ghost");
    }

    function load() {
      var my = ++S.seq, parsed = parseIds(idsField.value), base = normalizeBase(baseField.value);
      S.messages = parsed.bad.map(function (b) { return { kind: "error", text: tx("qr.form.bad_id", { id: b }) }; });
      if (!base) S.messages.push({ kind: "error", text: tx("qr.form.bad_base") });
      // R15-S25: адрес сайта мог прийти из ссылки (?base=). Подменённая ссылка напечатала бы QR на чужой сайт —
      // если это не адрес этого сервера, сотрудник видит предупреждение до печати.
      if (base && base !== normalizeBase(root.location.origin)) {
        S.messages.push({ kind: "warn", text: tx("qr.form.base_other", { base: domainOf(base) }) });
      }
      if (parsed.ids.length > MAX_IDS) S.messages.push({ kind: "error", text: tx("qr.form.too_many", { n: MAX_IDS }) });
      if (typeof root.qrcode !== "function") S.messages.push({ kind: "warn", text: tx("qr.form.no_qr") });
      S.signs = [];
      if (!base || !parsed.ids.length || parsed.ids.length > MAX_IDS) {
        if (!parsed.ids.length && !parsed.bad.length) S.messages.push({ kind: "info", text: tx("qr.form.none") });
        sheet.replaceChildren(); paintStatus(); return Promise.resolve(false);
      }
      S.state = "loading";
      S.messages.push({ kind: "info", text: tx("qr.form.loading") });
      paintStatus();
      function fetchTarget(id) {
        return fetchFn(api + "/target?id=" + encodeURIComponent(id), { credentials: "same-origin", headers: { Accept: "application/json" } })
          .then(function (r) { return r.json().catch(function () { return null; }).then(function (b) { return { id: id, status: r.status, body: b }; }); },
            function () { return { id: id, status: 0, body: null }; });
      }
      // R10 B-103: узла нет в свежем снимке OSM (retired). Есть замена рядом (replaced_by) — табличка на неё (жалобы по
      // QR идут к живому объекту), сотрудник видит, что номер обновлён; замены нет — табличка старая, но с предупреждением.
      // Сообщения этой загрузки копятся отдельно и попадают на экран, только если загрузку не сменила новая.
      var notes = [];
      function fresh(row) {
        var b = row.body;
        if (row.status !== 200 || !b || !b.retired) return Promise.resolve(row);
        if (!b.replaced_by) {
          notes.push({ kind: "warn", text: tx("qr.form.gone", { id: row.id }) });
          return Promise.resolve(row);
        }
        return fetchTarget(b.replaced_by).then(function (got) {
          // Замену не удалось получить (нет связи, 5xx) — не печатаем устаревшую табличку молча: это сбой связи.
          if (got.status !== 200 || !got.body || !got.body.target) return { id: row.id, status: got.status === 404 ? 404 : 0, body: null };
          notes.push({ kind: "info", text: tx("qr.form.updated", { old: row.id, id: b.replaced_by }) });
          return got;
        });
      }
      return Promise.all(parsed.ids.map(function (id) { return fetchTarget(id).then(fresh); })).then(function (rows) {
        if (my !== S.seq) return false;
        S.messages = S.messages.filter(function (m) { return m.text !== tx("qr.form.loading"); }).concat(notes);
        var offline = false, seen = {};
        rows.forEach(function (row) {
          if (row.status === 200 && row.body && row.body.target) {
            // Одна табличка на объект: замена могла совпасть с другим номером списка или с заменой другого номера.
            var key = row.body.target.id;
            if (seen[key]) return;
            seen[key] = true;
            S.signs.push(row.body);
          }
          else if (row.status === 404 || row.status === 400) S.messages.push({ kind: "error", text: tx("qr.form.not_found", { id: row.id }) });
          else offline = true;
        });
        if (offline) S.messages.push({ kind: "error", text: tx("qr.form.network") });
        if (S.signs.length) S.messages.push({ kind: "ok", text: tx("qr.form.ready", { n: S.signs.length }) });
        sheet.replaceChildren.apply(sheet, S.signs.map(function (info) { return sign(doc, info, base, size); }));
        fitAll();
        S.state = "ready";
        paintStatus();
        return true;
      });
    }
    paintStatus();
    if (params.get("ids")) load();
    return { load: load, setSize: setSize, state: function () { return { signs: S.signs.length, messages: S.messages.slice(), state: S.state, size: size }; } };
  }

  // Страница print.html: <main id="bqp-root" data-autostart> — запуск без встроенного скрипта (CSP R01 script-src 'self').
  function autostart() {
    var doc = root.document, el = doc && doc.getElementById && doc.getElementById("bqp-root");
    if (!el || !el.hasAttribute("data-autostart") || el.getAttribute("data-started")) return;
    el.setAttribute("data-started", "1");
    var B = root.BirgeI18n, go = function () { mount({ root: el }); };
    if (B && B.ready && typeof B.ready.then === "function") B.ready.then(go, go); else go();
  }
  if (root.document && root.document.getElementById) {
    if (root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", autostart);
    else autostart();
  }

  return { mount: mount, parseIds: parseIds, normalizeBase: normalizeBase, reportUrl: reportUrl, qrSvg: qrSvg, ID_RE: ID_RE, MAX_IDS: MAX_IDS,
    groupDigits: groupDigits, normalizeSize: normalizeSize, SIZES: SIZES, fitSign: fitSign,
    TEXT: TEXT };
});
