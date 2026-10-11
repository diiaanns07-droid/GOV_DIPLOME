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

  // Тексты листа. Табличка — всегда ru + kk; интерфейс страницы — на языке BirgeI18n (если подключён).
  var TEXT = {
    ru: {
      title: "QR-таблички для объектов", lead: "Распечатайте и повесьте на остановке, площадке или у перекрёстка. Житель наводит камеру — открывается карточка объекта.",
      ids: "Номера объектов", ids_hint: "Через запятую или с новой строки, например osm-node-10185771782. Не больше 24.",
      base: "Адрес сайта на табличке", base_hint: "Только адрес сайта, например https://birge.astana.kz",
      show: "Показать таблички", print: "Печать", none: "Добавьте номера объектов, чтобы увидеть таблички.",
      not_found: "Объект {id} не найден — табличка не будет напечатана.", bad_id: "«{id}» — не номер объекта.",
      too_many: "Не больше {n} объектов за раз.", bad_base: "Адрес сайта должен начинаться с https:// или http:// и не содержать пути.",
      no_qr: "Генератор QR ещё не подключён (LOCAL-11). Пока на табличке будет только ссылка.",
      network: "Нет связи. Повторите.", retry: "Повторить", loading: "Загружаем…", ready: "Готово табличек: {n}",
    },
    kk: {
      title: "Нысандарға арналған QR-тақтайшалар", lead: "Басып шығарып, аялдамаға, алаңға немесе қиылысқа іліңіз. Тұрғын камераны бағыттайды — нысан картасы ашылады.",
      ids: "Нысан нөмірлері", ids_hint: "Үтір арқылы немесе жаңа жолдан, мысалы osm-node-10185771782. 24-тен аспасын.",
      base: "Тақтайшадағы сайт мекенжайы", base_hint: "Тек сайт мекенжайы, мысалы https://birge.astana.kz",
      show: "Тақтайшаларды көрсету", print: "Басып шығару", none: "Тақтайшаларды көру үшін нысан нөмірлерін қосыңыз.",
      not_found: "{id} нысаны табылмады — тақтайша басылмайды.", bad_id: "«{id}» — нысан нөмірі емес.",
      too_many: "Бір реттен {n} нысаннан аспасын.", bad_base: "Сайт мекенжайы https:// немесе http:// деп басталып, жолсыз болуы керек.",
      no_qr: "QR генераторы әлі қосылмаған (LOCAL-11). Әзірге тақтайшада тек сілтеме болады.",
      network: "Байланыс жоқ. Қайталаңыз.", retry: "Қайталау", loading: "Жүктелуде…", ready: "Дайын тақтайшалар: {n}",
    },
  };
  // Надпись на самой табличке (оба языка сразу).
  var SIGN = {
    ru: "Есть проблема с этим местом? Наведите камеру телефона на код",
    kk: "Осы жерде мәселе бар ма? Телефон камерасын кодқа бағыттаңыз",
    number_ru: "Объект № {n}", number_kk: "Нысан № {n}",
  };

  function lang() {
    var B = root.BirgeI18n;
    var l = B && B.getLang ? B.getLang() : (root.document && root.document.documentElement.lang) || "ru";
    return l === "kk" ? "kk" : "ru";
  }
  function tx(key, params) {
    var s = (TEXT[lang()] || TEXT.ru)[key] || TEXT.ru[key] || key;
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

  function sign(doc, info, base) {
    var url = reportUrl(base, info.target.id);
    var qr = qrSvg(doc, url);
    if (qr) qr.setAttribute("aria-label", "QR: " + url);
    var fill = function (s) { return s.replace("{n}", info.number); };
    return h(doc, "article", { class: "bqp-sign", "data-id": info.target.id }, [
      h(doc, "p", { class: "bqp-sign__call", lang: "kk", text: SIGN.kk }),
      h(doc, "p", { class: "bqp-sign__call", lang: "ru", text: SIGN.ru }),
      h(doc, "div", { class: "bqp-qr" + (qr ? "" : " bqp-qr--missing") }, [qr || h(doc, "p", { class: "bqp-qr__missing", text: tx("no_qr") })]),
      h(doc, "p", { class: "bqp-sign__domain", text: domainOf(base) }),
      h(doc, "h2", { class: "bqp-sign__title", lang: "kk", text: info.target.label_kk || info.target.label_ru }),
      h(doc, "p", { class: "bqp-sign__title-ru", lang: "ru", text: info.target.label_ru }),
      h(doc, "p", { class: "bqp-sign__number" }, [fill(SIGN.number_kk) + " · " + fill(SIGN.number_ru)]),
      h(doc, "p", { class: "bqp-sign__url", text: url }),
    ]);
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
    var status = h(doc, "div", { class: "bqp-status", role: "status", "aria-live": "polite" });
    var sheet = h(doc, "div", { class: "bqp-sheet" });
    var showBtn = h(doc, "button", { type: "submit", class: "bk-btn bk-btn--primary", "data-act": "show" }, [tx("show")]);
    var printBtn = h(doc, "button", { type: "button", class: "bk-btn bqp-print", "data-act": "print", onclick: function () { root.print(); } }, [tx("print")]);
    var form = h(doc, "form", { class: "bqp-form no-print", novalidate: true }, [
      h(doc, "h1", { class: "bqp-h1", text: tx("title") }),
      h(doc, "p", { class: "bqp-lead", text: tx("lead") }),
      h(doc, "label", { for: "bqp-ids", class: "bqp-label", text: tx("ids") }), idsField,
      h(doc, "p", { id: "bqp-ids-hint", class: "bqp-hint", text: tx("ids_hint") }),
      h(doc, "label", { for: "bqp-base", class: "bqp-label", text: tx("base") }), baseField,
      h(doc, "p", { id: "bqp-base-hint", class: "bqp-hint", text: tx("base_hint") }),
      h(doc, "div", { class: "bqp-buttons" }, [
        showBtn, printBtn]),
      status]);
    form.addEventListener("submit", function (e) { e.preventDefault(); load(); });
    host.replaceChildren(form, sheet);

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
      S.messages = parsed.bad.map(function (b) { return { kind: "error", text: tx("bad_id", { id: b }) }; });
      if (!base) S.messages.push({ kind: "error", text: tx("bad_base") });
      if (parsed.ids.length > MAX_IDS) S.messages.push({ kind: "error", text: tx("too_many", { n: MAX_IDS }) });
      if (typeof root.qrcode !== "function") S.messages.push({ kind: "warn", text: tx("no_qr") });
      S.signs = [];
      if (!base || !parsed.ids.length || parsed.ids.length > MAX_IDS) {
        if (!parsed.ids.length && !parsed.bad.length) S.messages.push({ kind: "info", text: tx("none") });
        sheet.replaceChildren(); paintStatus(); return Promise.resolve(false);
      }
      S.state = "loading";
      S.messages.push({ kind: "info", text: tx("loading") });
      paintStatus();
      return Promise.all(parsed.ids.map(function (id) {
        return fetchFn(api + "/target?id=" + encodeURIComponent(id), { credentials: "same-origin", headers: { Accept: "application/json" } })
          .then(function (r) { return r.json().catch(function () { return null; }).then(function (b) { return { id: id, status: r.status, body: b }; }); },
            function () { return { id: id, status: 0, body: null }; });
      })).then(function (rows) {
        if (my !== S.seq) return false;
        S.messages = S.messages.filter(function (m) { return m.text !== tx("loading"); });
        var offline = false;
        rows.forEach(function (row) {
          if (row.status === 200 && row.body && row.body.target) S.signs.push(row.body);
          else if (row.status === 404 || row.status === 400) S.messages.push({ kind: "error", text: tx("not_found", { id: row.id }) });
          else offline = true;
        });
        if (offline) S.messages.push({ kind: "error", text: tx("network") });
        if (S.signs.length) S.messages.push({ kind: "ok", text: tx("ready", { n: S.signs.length }) });
        sheet.replaceChildren.apply(sheet, S.signs.map(function (info) { return sign(doc, info, base); }));
        S.state = "ready";
        paintStatus();
        return true;
      });
    }
    paintStatus();
    if (params.get("ids")) load();
    return { load: load, state: function () { return { signs: S.signs.length, messages: S.messages.slice(), state: S.state }; } };
  }

  return { mount: mount, parseIds: parseIds, normalizeBase: normalizeBase, reportUrl: reportUrl, qrSvg: qrSvg, ID_RE: ID_RE, MAX_IDS: MAX_IDS };
});
