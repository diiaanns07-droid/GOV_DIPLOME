/*
 * Birge · «Бірге: жители вместе» (R16, раунд 15): «Мой двор» и «Сделаем вместе».
 *
 *   <link rel="stylesheet" href="/civic/together/together.css">
 *   <script src="/civic/together/together-text.js"></script>
 *   <script src="/civic/together/together.js"></script>
 *   BirgeTogether.mount(element, { view: "yard" | "initiatives", role: "resident" | "akimat", apiBase })
 *     -> { setLang, destroy, open(kind, id) }
 *   BirgeTogether.open("yard", "yard-…") | open("initiative", "i-…") — переход из палитры (сцена 7), ленты R06, R08.
 *
 * Оболочка R01: скрипт сам регистрирует разделы BirgeShell.registerScreen — «yard» («Мой двор», житель) и «together»
 * («Сделаем вместе»: житель — дела соседей, акимат — проверка и поддержка) и слой карты «Инициативы» (registerLayer,
 * по умолчанию выключен). Место в меню — схема R11 IA_ROUND15, ставит R01. Адреса «#together/i-…» и «#yard/yard-…»
 * (ссылки ленты уведомлений, CONTRACT §5.8) открывают нужную карточку.
 *
 * Данные — ui/civic_together (маршруты /api/civic/v2/together/*), двор по точке — R12 GET /yard. Житель — заголовок
 * X-Birge-Device (тот же id устройства, что у жалоб R09 и вопросов R13: localStorage «birge.device»). Сотрудник —
 * сессия R02 + X-CSRF-Token (CivicShell.csrfToken).
 *
 * Правила: одна главная кнопка на экран; у демо-записей — «Пример»; соседи — только числом, без имён и списков людей;
 * нет чатов и комментариев; всё видимое — ключами R11 (запасной текст — together-text.js); все состояния (загрузка —
 * скелетон не раньше 150 мс, пусто — с подсказкой и кнопкой, ошибка — «что случилось + Повторить», успех — тост).
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var DEVICE_KEY = "birge.device";         // как у R09 (complaint.js) и R13 (qa.js)
  var YARD_KEY = "birge.together.yard";    // последний открытый «мой» двор — только удобство в этом браузере
  var SKELETON_DELAY = 150;
  var NET_TIMEOUT = 12000;
  var KINDS = ["cleanup", "greening", "snow", "repair", "help", "other"];
  // Значок вида дела: первый, который есть в спрайте ui-kit (R11 добавляет i-broom, i-sprout, i-wrench в раунде 15).
  var KIND_ICONS = { cleanup: ["broom", "trash"], greening: ["sprout", "trees"], snow: ["snowflake"], repair: ["wrench", "edit"],
    help: ["heart"], other: ["dots"] };
  var spriteIds = null;   // id символов icons.svg после загрузки
  function kindIcon(kind) {
    var options = KIND_ICONS[kind] || KIND_ICONS.other;
    for (var i = 0; spriteIds && i < options.length; i++) if (spriteIds["i-" + options[i]]) return options[i];
    return options[options.length - 1];
  }
  var TIMES = ["09:00", "10:00", "11:00", "12:00", "15:00", "17:00", "18:00"];
  var HOURS = [1, 2, 3, 4];
  var REASONS = ["personal_data", "rude", "spam", "duplicate", "not_initiative", "other"];
  var PHOTO_MAX = 46000;     // байт после сжатия: тело запроса шлюза ≤ 64 КБ (photos.py)
  var THUMB_MAX = 9000;
  var scriptBase = ((doc && doc.currentScript && doc.currentScript.src) || "").replace(/[^/]*$/, "");
  var ICONS = scriptBase + "../ui-kit/icons.svg";
  var PII = [
    ["email", /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/],
    ["card", /(?:^|\D)(?:\d[ -]?){15,18}\d(?!\d)/],
    ["iin", /(?:^|\D)(?:\d[ -]?){11}\d(?!\d)/],   // как на сервере (R15-S46): и с пробелами
    ["phone", /(?:^|[^\d+])(?:\+\s*7|8|7)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)/],
    ["phone", /(?:^|[^\d+])\(?7\d{2}\)?[\s-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)/],
  ];
  var KK_LETTERS = /[әғқңөұүһіӘҒҚҢӨҰҮҺІ]/;

  // ------------------------------------------------------------------ тексты
  function lang() {
    var I = root.BirgeI18n;
    if (I && typeof I.getLang === "function") return I.getLang() === "kk" ? "kk" : "ru";
    var S = root.BirgeShell;
    return S && typeof S.lang === "function" && S.lang() === "kk" ? "kk" : "ru";
  }
  function dict(l) { return ((root.BirgeTogetherText || {})[l]) || {}; }
  function pluralRu(n) {
    var a = Math.abs(n) % 100, b = a % 10;
    if (a > 10 && a < 20) return "many";
    if (b > 1 && b < 5) return "few";
    return b === 1 ? "one" : "many";
  }
  function formatNumber(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }
  function interpolate(text, params) {
    return String(text).replace(/\{(\w+)\}/g, function (m, name) {
      if (!params || params[name] === undefined || params[name] === null) return m;
      return typeof params[name] === "number" ? formatNumber(params[name]) : String(params[name]);
    });
  }
  // Словарь R11 главнее; ключа нет — запасной текст модуля; нет и его — общий словарь оболочки (common.*).
  function t(key, params) {
    var I = root.BirgeI18n;
    if (I && typeof I.has === "function" && I.has(key)) return I.t(key, params);
    var value = dict(lang())[key];
    if (value === undefined) value = dict("ru")[key];
    if (value === undefined) {
      var S = root.BirgeShell;
      return S && typeof S.t === "function" ? S.t(key, params) : key;
    }
    if (value && typeof value === "object" && !Array.isArray(value)) {
      var n = params && params.n != null ? Number(params.n) : 0;
      value = lang() === "ru" ? (value[pluralRu(n)] || value.many || value.other) : (value.other || value.many || value.one);
    }
    return interpolate(value, params);
  }
  function list(key) {
    var value = dict(lang())[key];
    return Array.isArray(value) ? value : (Array.isArray(dict("ru")[key]) ? dict("ru")[key] : []);
  }
  // Подпись двора/цели на языке интерфейса (у демо — оба языка; у настоящих — что есть).
  function label(obj, base) {
    if (!obj) return "";
    base = base || "label";
    return (lang() === "kk" ? obj[base + "_kk"] || obj[base + "_ru"] : obj[base + "_ru"] || obj[base + "_kk"]) || "";
  }

  // ------------------------------------------------------------------ время (Астана, UTC+5)
  var ASTANA_MS = 5 * 3600 * 1000;
  function parts(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return null;
    var u = new Date(d.getTime() + ASTANA_MS);
    return { y: u.getUTCFullYear(), mo: u.getUTCMonth(), d: u.getUTCDate(), wd: u.getUTCDay(),
      h: u.getUTCHours(), mi: u.getUTCMinutes(), ms: d.getTime() };
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function dayKey(p) { return p.y + "-" + pad(p.mo + 1) + "-" + pad(p.d); }
  function nowParts() { return parts(new Date().toISOString()); }
  function dayLabel(iso) {
    var p = parts(iso), now = nowParts();
    if (!p) return "";
    var tomorrow = parts(new Date(Date.now() + 86400000).toISOString());
    if (dayKey(p) === dayKey(now)) return t("together.today");
    if (dayKey(p) === dayKey(tomorrow)) return t("together.tomorrow");
    var wd = list("together.wd")[p.wd] || "", mon = list("together.months")[p.mo] || "";
    return lang() === "kk" ? p.d + " " + mon + ", " + wd : wd + ", " + p.d + " " + mon;
  }
  function timeLabel(iso) { var p = parts(iso); return p ? pad(p.h) + ":" + pad(p.mi) : ""; }
  function whenLabel(item) {
    if (!item || !item.starts_at) return "";
    if (item.ends_at && parts(item.ends_at)) {
      return t("together.range", { day: dayLabel(item.starts_at), from: timeLabel(item.starts_at), to: timeLabel(item.ends_at) });
    }
    return t("together.at", { day: dayLabel(item.starts_at), time: timeLabel(item.starts_at) });
  }
  function isPast(item) {
    var end = parts(item.ends_at || item.starts_at);
    return !!end && end.ms < Date.now();
  }
  function shortDate(iso) {
    var p = parts(iso);
    if (!p) return "";
    return p.d + " " + (list("together.months")[p.mo] || "");
  }
  function isoAstana(y, mo, d, hhmm) {
    return y + "-" + pad(mo + 1) + "-" + pad(d) + "T" + hhmm + ":00+05:00";
  }

  // ------------------------------------------------------------------ DOM
  function h(tag, attrs, children) {
    var node = doc.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === false || v === null || v === undefined) return;
      if (k === "text") node.textContent = v;
      else if (k === "class") node.className = v;
      else if (k.slice(0, 2) === "on" && typeof v === "function") node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    });
    (children || []).forEach(function (c) {
      if (c === null || c === undefined || c === false) return;
      node.appendChild(typeof c === "string" || typeof c === "number" ? doc.createTextNode(String(c)) : c);
    });
    return node;
  }
  var SVG_NS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs, children) {
    var node = doc.createElementNS(SVG_NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }
  function icon(name, cls) {
    var node = svg("svg", { class: "ic" + (cls ? " " + cls : ""), "aria-hidden": "true", focusable: "false" });
    var use = svg("use", {});
    use.setAttribute("href", ICONS + "#i-" + name);
    node.appendChild(use);
    return node;
  }
  function demoTag() {
    return h("span", { class: "bk-tag bk-tag--demo tg-demo" }, [t("common.demo")]);
  }
  function toast(text, type) {
    if (root.BirgeUI && typeof root.BirgeUI.toast === "function") root.BirgeUI.toast(text, type ? { type: type } : {});
  }
  function reducedMotion() {
    return !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  // ------------------------------------------------------------------ значок вида дела
  // Поправка владельца П1 («без ИИ-слопа»): никаких иллюстраций и «сценок» — значок вида из набора R11 и слово.
  function kindBadge(kind, big) {
    return h("span", { class: "tg-kindbadge" + (big ? " tg-kindbadge--big" : ""), "data-kind": kind }, [
      h("span", { class: "tg-kindbadge__ic" }, [icon(kindIcon(kind))]),
      h("span", { class: "tg-kindbadge__label", text: t("together.kind." + kind) }),
    ]);
  }
  // Фото «после» — только настоящее (загружено жителем или сотрудником, data URL с сервера).
  function realPhotos(item) {
    return ((item.report && item.report.photos) || []).filter(function (p) { return !!p.data_url; });
  }

  // ------------------------------------------------------------------ устройство и API
  function storage(key, value) {
    try {
      if (value === undefined) return root.localStorage.getItem(key);
      if (value === null) root.localStorage.removeItem(key);
      else root.localStorage.setItem(key, value);
    } catch (e) { /* хранилище закрыто — без запоминания */ }
    return null;
  }
  var memoryDevice = null;
  function randomHex(bytes) {
    var arr = new Uint8Array(bytes);
    if (root.crypto && root.crypto.getRandomValues) root.crypto.getRandomValues(arr);
    else for (var i = 0; i < bytes; i++) arr[i] = Math.floor(Math.random() * 256);
    return Array.prototype.map.call(arr, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }
  // Тот же id устройства, что у мастера жалобы R09: «Я приду» — одно на устройство (в базе — только солёный хэш).
  function deviceId() {
    var id = storage(DEVICE_KEY);
    if (id && /^[A-Za-z0-9._:-]{8,128}$/.test(id)) return id;
    if (!memoryDevice) {
      memoryDevice = "d-" + randomHex(12);
      storage(DEVICE_KEY, memoryDevice);
    }
    return memoryDevice;
  }
  function csrf() {
    var shell = root.CivicShell;
    return shell && typeof shell.csrfToken === "function" ? shell.csrfToken() : null;
  }
  function ApiError(status, body) {
    this.status = status;
    this.code = (body && body.error && (body.error.code || body.error)) || (status === 0 ? "network" : "http_" + status);
    if (typeof this.code !== "string") this.code = "http_" + status;
    this.message = (body && (body.message || (body.error && body.error.message))) || "";
    this.field = body && body.field;
    this.retryAfter = body && body.retry_after;
  }
  function request(base, method, path, body) {
    var controller = root.AbortController ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, NET_TIMEOUT) : null;
    var headers = { Accept: "application/json", "X-Birge-Device": deviceId() };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    var token = csrf();
    if (token) headers["X-CSRF-Token"] = token;   // и в GET: маршруты сотрудника шлюз проверяет с CSRF (staff=True)
    return fetch(base + path, {
      method: method, headers: headers, credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller ? controller.signal : undefined,
    }).then(function (res) {
      return res.text().then(function (text) {
        var json = null;
        try { json = text ? JSON.parse(text) : null; } catch (e) { json = null; }
        // R09-конверт {ok, data} тоже понимаем — шлюз может обернуть ответ.
        if (json && json.ok === true && json.data !== undefined) json = json.data;
        if (!res.ok || (json && json.ok === false)) throw new ApiError(res.status, json);
        if (json === null) throw new ApiError(0, null);
        return json;
      });
    }, function () {
      throw new ApiError(0, null);
    }).finally(function () { if (timer) clearTimeout(timer); });
  }
  function errorText(err) {
    if (!err) return t("together.error.action");
    if (err.status === 0) return t("together.error.text");
    var key = "together.err." + err.code;
    var own = dict(lang())[key] || (root.BirgeI18n && root.BirgeI18n.has && root.BirgeI18n.has(key));
    if (own) return t(key);
    if (err.status === 429) return t("together.error.limit");
    // Сообщение сервера — по-русски; на казахском — общий текст.
    return lang() === "ru" && err.message ? err.message : t("together.error.action");
  }
  function piiKinds(text) {
    return PII.filter(function (p) { return p[1].test(text || ""); }).map(function (p) { return p[0]; });
  }
  function textLang(text) { return KK_LETTERS.test(text || "") ? "kk" : lang(); }

  // ------------------------------------------------------------------ что есть в сборке
  // Маршруты [доп.] R16 (список дворов, «старший по двору») R01 мог ещё не поставить: спрашиваем шлюз один раз
  // (GET /modules) и прячем то, чего нет, — вместо ошибки 404 на экране. Нет ответа — считаем, что всё есть.
  var routes = null;
  function loadRoutes(base) {
    if (routes) return routes;
    routes = request(base, "GET", "/modules").then(function (data) {
      var have = {};
      Object.keys((data && data.modules) || {}).forEach(function (k) { have[k] = data.modules[k].status === "ready"; });
      return have;
    }, function () { return null; });
    return routes;
  }
  var routeOk = { "together.yards.list": true, "together.yards.captain": true };
  function loadSprite() {
    if (spriteIds || !root.fetch) return;
    spriteIds = {};
    root.fetch(ICONS).then(function (r) { return r.text(); }).then(function (txt) {
      (txt.match(/id="i-[a-z0-9-]+"/g) || []).forEach(function (m) { spriteIds[m.slice(4, -1)] = true; });
      mounted.forEach(function (c) { if (c.rerender) c.rerender(); });
    }).catch(function () { /* без спрайта — прежние значки */ });
  }

  // ------------------------------------------------------------------ фото «после»: сжатие в браузере
  // canvas перекодирует JPEG — EXIF и GPS отпадают (сервер чистит ещё раз). Размер подбираем под тело запроса.
  function shrink(file) {
    return new Promise(function (resolve, reject) {
      if (!file || !/^image\//.test(file.type || "")) { reject(new Error("type")); return; }
      var url = root.URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        root.URL.revokeObjectURL(url);
        function encode(maxSide, limit) {
          var scale = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
          var w = Math.max(1, Math.round(img.naturalWidth * scale)), hh = Math.max(1, Math.round(img.naturalHeight * scale));
          var canvas = doc.createElement("canvas");
          canvas.width = w;
          canvas.height = hh;
          canvas.getContext("2d").drawImage(img, 0, 0, w, hh);
          for (var q = 0.82; q >= 0.34; q -= 0.08) {
            var dataUrl = canvas.toDataURL("image/jpeg", q);
            if ((dataUrl.length - 23) * 0.75 <= limit) return { data_url: dataUrl, width: w, height: hh };
          }
          return null;
        }
        var full = null;
        for (var side = 960; side >= 480 && !full; side -= 160) full = encode(side, PHOTO_MAX);
        var thumb = encode(320, THUMB_MAX) || encode(240, THUMB_MAX);
        if (!full) { reject(new Error("size")); return; }
        resolve({ data_url: full.data_url, width: full.width, height: full.height, thumb: thumb ? thumb.data_url : undefined });
      };
      img.onerror = function () { root.URL.revokeObjectURL(url); reject(new Error("decode")); };
      img.src = url;
    });
  }

  // ------------------------------------------------------------------ общие кусочки экрана
  function skeleton(rows) {
    var out = [];
    for (var i = 0; i < (rows || 3); i++) {
      out.push(h("div", { class: "tg-skel-card" }, [
        h("span", { class: "bk-skel bk-skel--block" }),
        h("span", { class: "bk-skel bk-skel--title" }),
        h("span", { class: "bk-skel bk-skel--line" }),
      ]));
    }
    return h("div", { class: "tg-skel", "aria-busy": "true", role: "status", "aria-label": t("together.loading") }, out);
  }
  // Пусто (П1, правило 2): один маленький значок набора R11 (≤ 48 px) + короткий текст + одна кнопка.
  function emptyState(title, text, action, iconName) {
    return h("div", { class: "bk-empty tg-empty", role: "status" }, [
      h("span", { class: "tg-empty__ic" }, [icon(iconName || "users")]),
      h("p", { class: "bk-empty__title", text: title }),
      text ? h("p", { class: "bk-empty__text", text: text }) : null,
      action || null,
    ]);
  }
  function errorState(err, retry) {
    return h("div", { class: "bk-error tg-error", role: "alert" }, [
      icon("wifi-off", "ic--48"),
      h("p", { class: "bk-error__title", text: t("together.error.title") }),
      h("p", { class: "bk-error__text", text: err && err.status !== 0 ? errorText(err) : t("together.error.text") }),
      h("button", { type: "button", class: "bk-btn", onclick: retry }, [icon("refresh"), t("common.action.retry")]),
    ]);
  }
  function noDataBlock() {
    return h("div", { class: "tg-nodata", role: "note" }, [
      icon("info"),
      h("div", {}, [h("p", { class: "tg-nodata__title", text: t("together.block.no_data") }),
        h("p", { class: "tg-nodata__text", text: t("together.block.no_data_text") })]),
    ]);
  }
  function statusText(item) {
    if (item.status === "published" && isPast(item)) return t("together.status.past");
    return t("together.status." + item.status);
  }

  // Счётчик «Я приду»: число перекатывается снизу вверх (250 мс), без движения — просто меняется.
  // live — объявлять новое число (только крупный счётчик карточки дела, не каждый в списке).
  function counter(n, cls, live) {
    var box = h("span", { class: "tg-count" + (cls ? " " + cls : "") }, [
      icon("users"),
      h("span", { class: "tg-count__num", "aria-hidden": "true" }, [h("span", { class: "tg-count__n", text: formatNumber(n) })]),
      h("span", { class: "tg-count__label", "aria-hidden": "true", text: t("together.count", { n: n }).replace(/^[\d\s ]+/, "") }),
      h("span", { class: "bk-sr-only", "aria-live": live ? "polite" : null, text: t("together.count", { n: n }) }),
    ]);
    box.dataset.n = String(n);
    return box;
  }
  function bump(box, n) {
    if (!box) return;
    var old = Number(box.dataset.n);
    box.dataset.n = String(n);
    var num = box.querySelector(".tg-count__num");
    box.querySelector(".tg-count__label").textContent = t("together.count", { n: n }).replace(/^[\d\s ]+/, "");
    box.querySelector(".bk-sr-only").textContent = t("together.count", { n: n });
    if (!num) return;
    if (reducedMotion() || old === n || isNaN(old)) {
      num.replaceChildren(h("span", { class: "tg-count__n", text: formatNumber(n) }));
      return;
    }
    var up = n > old;
    var leaving = num.querySelector(".tg-count__n");
    var coming = h("span", { class: "tg-count__n tg-count__n--in" + (up ? "" : " tg-count__n--down"), text: formatNumber(n) });
    if (leaving) leaving.classList.add("tg-count__n--out", up ? "tg-up" : "tg-down");
    num.appendChild(coming);
    box.classList.remove("tg-pop");
    void box.offsetWidth;  // перезапуск анимации «+1»
    box.classList.add("tg-pop");
    setTimeout(function () {
      if (leaving && leaving.parentNode) leaving.parentNode.removeChild(leaving);
      coming.classList.remove("tg-count__n--in", "tg-count__n--down");
    }, 320);
  }
  function supportBadge(support) {
    if (!support || !support.by_akimat) return null;
    var what = [];
    if (support.inventory) what.push(t("together.support.inventory"));
    if (support.pickup_service) what.push(t("together.support.pickup"));
    return h("span", { class: "tg-support", title: support.note || "" }, [icon("check"), t("together.supported"),
      what.length ? h("span", { class: "tg-support__what", text: " · " + what.join(" · ") }) : null]);
  }
  // ------------------------------------------------------------------ модуль экрана
  var mounted = [];   // смонтированные экраны (для open() из палитры и ссылок ленты)
  var pending = null; // {kind, id} — открыть после монтирования

  function mount(rootEl, options) {
    var opts = { apiBase: "/api/civic/v2", role: "resident", titleTag: "h2" };
    Object.keys(options || {}).forEach(function (k) { if (options[k] !== undefined) opts[k] = options[k]; });
    var api = function (method, path, body) { return request(opts.apiBase, method, path, body); };
    // Раздел оболочки R01 (IA R11 §5): opts.section — «yard» или «together»; свой вызов — opts.view.
    var viewName = opts.view || (opts.section === "yard" ? "yard" : "initiatives");
    var S = {
      role: opts.role === "akimat" ? "akimat" : "resident",
      view: viewName === "yard" ? "yard" : "initiatives",
      stack: [],
      cache: {},           // ключ -> {status, data, error}
      busy: {},            // id -> true, пока идёт действие
      staffTab: "queue",
      filter: "city",
      open: null,          // сотрудник: {id, kind: "hide" | "support" | "report"}
      forms: {},           // черновики форм сотрудника по id
      wizard: null,
      destroyed: false,
    };
    var host = h("div", { class: "tg bk-app", "data-view": S.view, "data-role": S.role });
    rootEl.replaceChildren(host);
    var off = [];
    loadSprite();
    loadRoutes(opts.apiBase).then(function (have) {
      if (!have || S.destroyed) return;
      Object.keys(routeOk).forEach(function (k) { routeOk[k] = have[k] !== undefined ? have[k] : false; });
      render();
    });

    function route() { return S.stack[S.stack.length - 1] || baseRoute(); }
    function baseRoute() {
      if (S.view === "yard") {
        var yid = storage(YARD_KEY);
        return yid && /^(yard|cell)-[A-Za-z0-9_-]{1,60}$/.test(yid) ? { name: "yard", id: yid, base: true } : { name: "picker", base: true };
      }
      return S.role === "akimat" ? { name: "staff", base: true } : { name: "list", base: true };
    }
    function go(next) { S.stack.push(next); S.wizardError = null; render(true); syncPath(); }
    function back() {
      if (S.stack.length) { S.stack.pop(); render(true); syncPath(); return true; }
      return false;
    }
    function reset(next) { S.stack = next ? [next] : []; render(true); syncPath(); }

    // --- путь в адресе (оболочка R01, IA R11 §7.3): #yard/<двор>, #yard/<двор>/<дело>, #together/<дело>.
    // Модуль переходит по пути сам (setPath — «Назад» браузера, ссылка ленты) и сообщает оболочке свой путь (navigate).
    // Оболочка FINAL-4 путей не знает: тогда адрес не меняется, работает свой стек экрана.
    var nav = typeof opts.navigate === "function" ? opts.navigate : null;
    var currentPath = typeof opts.path === "string" ? opts.path : "";
    var echo = false;
    var YARD_RE = /^(yard|cell)-[A-Za-z0-9_-]{1,60}$/, ITEM_RE = /^i-[a-z0-9-]{4,40}$/;
    function pathOf(r) {
      if (r.name === "wizard" || r.name === "sent") return null;   // черновик в адрес не пишем
      if (S.view === "yard") {
        if (r.name === "picker") return "";
        if (r.name === "yard") return r.base ? "" : r.id;
        if (r.name === "initiative") return r.yard ? r.yard + "/" + r.id : null;
        return null;
      }
      if (r.name === "initiative") return r.id;
      if (r.name === "yard") return r.id;
      return r.name === "list" || r.name === "staff" ? "" : null;
    }
    function stackFromPath(path) {
      var parts = String(path || "").split("/").filter(Boolean);
      if (S.view === "yard") {
        if (!parts.length || !YARD_RE.test(parts[0])) return [];
        var out = [{ name: "yard", id: parts[0] }];
        if (parts[1] && ITEM_RE.test(parts[1])) out.push({ name: "initiative", id: parts[1], yard: parts[0] });
        return out;
      }
      if (parts[0] && ITEM_RE.test(parts[0])) return [{ name: "initiative", id: parts[0] }];
      if (parts[0] && YARD_RE.test(parts[0])) return [{ name: "yard", id: parts[0] }];
      return [];
    }
    function syncPath() {
      if (!nav || S.destroyed) return;
      var p = pathOf(route());
      if (p === null || p === currentPath) return;
      currentPath = p;
      echo = true;
      try { nav(p); } catch (e) { /* оболочка без путей */ } finally { echo = false; }
    }
    function setPath(path) {
      path = typeof path === "string" ? path : "";
      if (echo) { currentPath = path; return; }      // наш же navigate вернулся эхом — уже на месте
      if (path === currentPath && path !== "") return;
      currentPath = path;
      S.stack = stackFromPath(path);
      S.open = null;
      S.wizard = null;
      render(true);
    }
    if (currentPath) S.stack = stackFromPath(currentPath);

    // --- загрузка с кэшем: скелетон не раньше 150 мс, повторное открытие — сразу прежние данные и тихое обновление
    function load(key, path, force) {
      var entry = S.cache[key];
      // Готово или ошибка — не грузим заново при каждой отрисовке: после ошибки повтор только по «Повторить»
      // (иначе при 503 экран засыпал бы сервер запросами). «stale» — тихое обновление поверх прежних данных.
      if (entry && (entry.status === "ready" || entry.status === "error") && !force) return;
      if (entry && entry.loading) return;
      entry = S.cache[key] = entry || { status: "loading" };
      entry.loading = true;
      entry.slow = false;
      var timer = setTimeout(function () { entry.slow = true; if (entry.loading && entry.status === "loading") render(); }, SKELETON_DELAY);
      api("GET", path).then(function (data) {
        entry.status = "ready";
        entry.data = data;
        entry.error = null;
      }, function (err) {
        if (entry.status !== "ready") entry.status = "error";
        entry.error = err;
      }).then(function () {
        clearTimeout(timer);
        entry.loading = false;
        if (!S.destroyed) render();
      });
    }
    function invalidate(prefix) {
      Object.keys(S.cache).forEach(function (k) { if (k.indexOf(prefix) === 0) S.cache[k].status = "stale"; });
    }
    function entryState(key) {
      var e = S.cache[key];
      if (!e) return { status: "loading", slow: false };
      if (e.status === "stale") return { status: "ready", data: e.data };
      return e;
    }

    // --- отрисовка: фокус на заголовке нового экрана; прокрутка листа — в начало
    function render(moved) {
      if (S.destroyed) return;
      var r = route();
      host.dataset.route = r.name;
      var active = doc.activeElement;
      var focusKey = active && host.contains(active) ? active.getAttribute("data-focus") : null;
      var view;
      try {
        view = ({ picker: viewPicker, yard: viewYard, list: viewList, initiative: viewInitiative, wizard: viewWizard,
          sent: viewSent, staff: viewStaff })[r.name](r);
      } catch (e) {
        if (root.console) console.error("together render", e);
        view = errorState(null, function () { render(); });
      }
      host.replaceChildren(view);
      if (moved) {
        var scroller = host.closest(".birge-day") || host.parentNode;
        if (scroller && scroller.scrollTo) scroller.scrollTo({ top: 0 });
        var head = host.querySelector("[data-autofocus]");
        if (head && head.focus) head.focus({ preventScroll: true });
      } else if (focusKey) {
        var again = host.querySelector('[data-focus="' + focusKey + '"]');
        if (again && again.focus) again.focus({ preventScroll: true });
      }
    }
    function title(text, extra) {
      return h(opts.titleTag || "h2", { class: "tg-title", tabindex: "-1", "data-autofocus": "1" }, [text].concat(extra || []));
    }
    function backButton(text) {
      return h("button", { type: "button", class: "bk-btn bk-btn--ghost tg-back", "data-focus": "back", onclick: back },
        [icon("back"), text || t("together.back")]);
    }

    // ================================================================ двор: выбор
    function viewPicker() {
      var key = "yards";
      var rows;
      var e = { status: "ready", data: { items: [] } };
      if (routeOk["together.yards.list"]) { load(key, "/together/yards"); e = entryState(key); }
      if (e.status === "loading") rows = e.slow ? skeleton(3) : h("div", { class: "tg-wait" });
      else if (e.status === "error" && e.error && (e.error.status === 404 || e.error.status === 503)) rows = null;  // нет в сборке
      else if (e.status === "error") rows = errorState(e.error, function () { load(key, "/together/yards", true); });
      else {
        var items = (e.data && e.data.items) || [];
        rows = items.length ? h("ul", { class: "tg-yardlist" }, items.map(function (y) {
          return h("li", {}, [h("button", { type: "button", class: "tg-yardrow", "data-focus": "yard-" + y.id,
            onclick: function () { openYard(y.id); } }, [
            h("span", { class: "tg-yardrow__ic" }, [icon("home")]),
            h("span", { class: "tg-yardrow__main" }, [
              h("span", { class: "tg-yardrow__name", text: label(y) || y.id }),
              h("span", { class: "tg-yardrow__meta", text: t("together.pick.row", {
                members: formatNumber(y.members) + " " + t("together.kpi.members", { n: y.members }),
                initiatives: formatNumber(y.initiatives) + " " + t("together.kpi.initiatives", { n: y.initiatives }) }) }),
            ]),
            y.demo ? demoTag() : null,
            icon("chevron-right", "tg-yardrow__go"),
          ])]);
        })) : null;
      }
      // Карта оболочки может появиться позже экрана (оболочка R01 создаёт её после загрузки стиля): кнопка есть всегда,
      // когда есть оболочка или карта; саму карту берём в момент нажатия.
      var canPick = !!(opts.map || mapObject() || root.BirgeShell);
      return h("section", { class: "tg-picker" }, [
        h("div", { class: "tg-hero" }, [
          h("span", { class: "tg-empty__ic" }, [icon("pin")]),
          h("div", { class: "tg-hero__text" }, [
            title(t("together.pick.title")),
            h("p", { class: "tg-lead", text: t("together.pick.text") }),
            h("div", { class: "tg-wnav tg-hero__actions" }, [
              canPick ? h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-focus": "pick-map", onclick: function () {
                var base = opts.apiBase;
                if (typeof opts.close === "function") opts.close();
                else if (root.BirgeShell && root.BirgeShell.setSection) root.BirgeShell.setSection("map");
                whenMap(opts.map, function (m) { startPick(m, base); });
              } }, [icon("pin"), t("together.pick.on_map")]) : null,
              h("button", { type: "button", class: "bk-btn" + (canPick ? "" : " bk-btn--primary"), "data-focus": "locate",
                "aria-busy": S.locating ? "true" : null, disabled: S.locating || null, onclick: locate },
                [icon("locate"), S.locating ? t("together.pick.locating") : t("together.pick.locate")]),
            ]),
            S.locateError ? h("p", { class: "tg-note", role: "status", text: S.locateError }) : null,
          ]),
        ]),
        rows ? h("h3", { class: "tg-h3", text: t("together.pick.list") }) : null,
        rows,
      ]);
    }
    function locate() {
      S.locateError = null;
      if (!root.navigator || !root.navigator.geolocation) { S.locateError = t("together.pick.geo_failed"); render(); return; }
      S.locating = true;
      render();
      root.navigator.geolocation.getCurrentPosition(function (pos) {
        api("GET", "/yard?lon=" + pos.coords.longitude.toFixed(6) + "&lat=" + pos.coords.latitude.toFixed(6)).then(function (data) {
          S.locating = false;
          if (data && data.yard && data.yard.id) openYard(data.yard.id);
          else { S.locateError = t("together.pick.not_found"); render(); }
        }, function () { S.locating = false; S.locateError = t("together.pick.geo_failed"); render(); });
      }, function () { S.locating = false; S.locateError = t("together.pick.geo_failed"); render(); },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 });
    }
    function openYard(id, tab) {
      // Житель в «Сделаем вместе» → раздел «Мой двор» оболочки со своим адресом (#yard/<двор>), если оболочка умеет пути.
      if (S.view !== "yard" && S.role === "resident" && nav && typeof opts.openSection === "function") {
        opts.openSection("yard", id);
        return;
      }
      var r = route();
      if (r.name === "picker" && r.base) { S.stack = [{ name: "yard", id: id, tab: tab }]; render(true); syncPath(); return; }
      go({ name: "yard", id: id, tab: tab });
    }

    // ================================================================ двор: страница
    function viewYard(r) {
      var key = "yard:" + r.id;
      load(key, "/together/yards/" + encodeURIComponent(r.id));
      var e = entryState(key);
      if (e.status === "loading") return h("section", { class: "tg-yard" }, [e.slow ? skeleton(2) : h("div", { class: "tg-wait" })]);
      if (e.status === "error") {
        // Запомненный двор пропал (база демо пересоздана) — снова выбор двора, без ошибки.
        if (e.error && e.error.status === 404 && r.base) { storage(YARD_KEY, null); return viewPicker(); }
        return h("section", { class: "tg-yard" }, [S.stack.length ? backButton() : null,
          errorState(e.error, function () { load(key, "/together/yards/" + encodeURIComponent(r.id), true); })]);
      }
      var page = e.data;
      var yard = page.yard;
      var tab = r.tab || "overview";
      // Двор-пример: метка «Пример» одна, в шапке — строки ленты и проблем её не повторяют.
      S.pageDemo = !!yard.demo;
      var counts = page.counts || {};
      var mine = page.me && page.me.member;
      var kpis = h("div", { class: "bk-kpis bk-kpis--3 tg-kpis" }, [
        kpi(counts.members, "together.kpi.members"),
        kpi(counts.problems, "together.kpi.problems", function () { setTab("problems"); }),
        kpi(counts.initiatives, "together.kpi.initiatives", function () { setTab("initiatives"); }),
      ]);
      function setTab(next) { r.tab = next; render(); var b = host.querySelector('[data-focus="tab-' + next + '"]'); if (b) b.focus(); }
      var main = S.role === "akimat" ? null : mine
        ? h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-focus": "propose", onclick: function () { startWizard(page); } },
          [icon("plus"), t("together.yard.propose")])
        : h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-focus": "join-yard", "aria-busy": S.busy.yard ? "true" : null,
          disabled: S.busy.yard || null, onclick: function () { yardMembership(page, true); } }, [icon("home"), t("together.yard.join")]);
      var header = h("header", { class: "tg-yardhead" }, [
        h("div", { class: "tg-yardhead__text" }, [
          title(label(yard) || yard.id),
          h("p", { class: "tg-yardhead__meta" }, [
            yard.district ? h("span", { text: districtName(yard.district) }) : null,
            yard.street ? h("span", { text: " · " + (lang() === "kk" ? yard.street.kk || yard.street.ru : yard.street.ru || yard.street.kk) }) : null,
            yard.approximate ? h("span", { class: "bk-tag bk-tag--approx", text: t("together.yard.approx") }) : null,
            yard.demo ? demoTag() : null,
          ]),
          yard.captain ? h("p", { class: "tg-captain" }, [icon("user"), t("together.yard.captain", { name: yard.captain.display_name })]) : null,
          kpis,
          h("div", { class: "tg-yardhead__actions" }, [
            main,
            mine ? h("span", { class: "tg-member" }, [icon("check"), t("together.yard.member")]) : null,
          ]),
        ]),
      ]);
      var tabs = h("div", { class: "bk-tabs tg-tabs", role: "tablist", "aria-label": t("together.tabs_label") },
        ["overview", "problems", "initiatives", "works"].map(function (id) {
          var n = id === "problems" ? counts.problems : id === "initiatives" ? counts.initiatives : null;
          return h("button", { type: "button", role: "tab", id: "tg-tab-" + id, "aria-selected": String(tab === id),
            "aria-controls": "tg-panel", tabindex: tab === id ? "0" : "-1", "data-focus": "tab-" + id,
            onclick: function () { setTab(id); }, onkeydown: tabKeys },
            [t("together.tab." + id), typeof n === "number" ? h("span", { class: "bk-num", text: formatNumber(n) }) : null]);
        }));
      var panel = h("div", { class: "tg-panel", id: "tg-panel", role: "tabpanel", "aria-labelledby": "tg-tab-" + tab },
        [({ overview: yardOverview, problems: yardProblems, initiatives: yardInitiatives, works: yardWorks })[tab](page)]);
      var foot = S.role === "akimat" ? null : h("div", { class: "tg-yardfoot" }, [
        mine ? h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "leave-yard",
          onclick: function () { yardMembership(page, false); } }, [t("together.yard.leave")]) : null,
        h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "other-yard",
          onclick: function () { storage(YARD_KEY, null); reset(S.view === "yard" ? null : { name: "picker" }); } }, [t("together.yard.other")]),
        mine && routeOk["together.yards.captain"] ? captainBlock(page) : null,
      ]);
      return h("section", { class: "tg-yard" }, [S.stack.length ? backButton() : null, header, tabs, panel, foot]);
    }
    function tabKeys(event) {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
      var tabs = Array.prototype.slice.call(event.currentTarget.parentNode.querySelectorAll('[role="tab"]'));
      var i = tabs.indexOf(event.currentTarget) + (event.key === "ArrowRight" ? 1 : -1);
      var next = tabs[(i + tabs.length) % tabs.length];
      if (next) { next.click(); }
      event.preventDefault();
    }
    function kpi(value, key, onClick) {
      var known = typeof value === "number";
      var content = [h("span", { class: "bk-kpi__value", text: known ? formatNumber(value) : "—" }),
        h("span", { class: "bk-kpi__label", text: known ? t(key, { n: value }) : t("together.kpi.no_data") })];
      return onClick && known ? h("button", { type: "button", class: "bk-kpi tg-kpi tg-kpi--btn", onclick: onClick }, content)
        : h("div", { class: "bk-kpi tg-kpi" }, content);
    }
    function districtName(id) {
      var names = { almaty: ["Алматы", "Алматы"], baikonur: ["Байконур", "Байқоңыр"], esil: ["Есиль", "Есіл"], nura: ["Нура", "Нұра"],
        saraishyk: ["Сарайшык", "Сарайшық"], saryarka: ["Сарыарка", "Сарыарқа"] };
      var key = "common.district." + id;
      if (root.BirgeI18n && root.BirgeI18n.has && root.BirgeI18n.has(key)) return root.BirgeI18n.t(key);
      return names[id] ? names[id][lang() === "kk" ? 1 : 0] : id;
    }
    function yardOverview(page) {
      var upcoming = (page.initiatives && page.initiatives.items) || [];
      var next = upcoming.filter(function (i) { return !isPast(i); })[0];
      var blocks = [];
      blocks.push(h("div", { class: "tg-col" }, [
        h("h3", { class: "tg-h3", text: t("together.next.title") }),
        next ? card(next, { wide: true }) : emptyState(t("together.empty.title"), t("together.empty.text"),
          page.me && page.me.member ? h("button", { type: "button", class: "bk-btn", onclick: function () { startWizard(page); } },
            [icon("plus"), t("together.yard.propose")]) : null, "calendar"),
        h("h3", { class: "tg-h3", text: t("together.problems.title") }),
        problemsList(page.problems, 3),
      ]));
      blocks.push(h("aside", { class: "tg-col tg-col--side" }, [
        h("h3", { class: "tg-h3", text: t("together.feed.title") }),
        feedList((page.feed || []).slice(0, 5)),
      ]));
      return h("div", { class: "tg-overview" }, blocks);
    }
    function problemsList(block, limit) {
      if (!block || block.status !== "ok") return noDataBlock();
      var items = block.items || [];
      if (!items.length && !(block.fixed || []).length) {
        return h("p", { class: "tg-calm" }, [icon("check"), t("together.problems.empty")]);
      }
      var shown = limit ? items.slice(0, limit) : items;
      var out = [h("ul", { class: "tg-rows" }, shown.map(problemRow))];
      if (limit && items.length > limit) {
        out.push(h("button", { type: "button", class: "bk-btn bk-btn--ghost tg-more", onclick: function () {
          var r = route(); r.tab = "problems"; render(); } }, [t("together.problems.all"), icon("chevron-right")]));
      }
      if (!limit && (block.fixed || []).length) {
        out.push(h("h3", { class: "tg-h3", text: t("together.problems.fixed") }));
        out.push(h("ul", { class: "tg-rows" }, block.fixed.map(problemRow)));
      }
      return h("div", {}, out);
    }
    function problemRow(p) {
      var fixed = p.state === "fixed";
      var sub = p.subtopic ? (lang() === "kk" ? p.subtopic.kk || p.subtopic.ru : p.subtopic.ru || p.subtopic.kk) : "";
      var badge = h("span", { class: "tg-level" + (fixed ? " tg-level--fixed" : ""), "data-level": String(p.level || 0),
        style: !fixed && p.color ? "--tg-level:" + p.color : null }, [fixed ? icon("check") : formatNumber(p.count)]);
      return h("li", {}, [h("button", { type: "button", class: "tg-row", onclick: function () {
        if (typeof opts.openTarget === "function" && p.target) opts.openTarget(p.target.kind, p.target.id);
      } }, [
        badge,
        h("span", { class: "tg-row__main" }, [
          h("span", { class: "tg-row__title", text: sub || label(p.target) }),
          h("span", { class: "tg-row__meta", text: (sub ? label(p.target) + " · " : "") +
            (fixed ? t("together.feed.kind.problem.fixed") : t("together.problems.people", { n: p.count })) }),
        ]),
        p.demo && !S.pageDemo ? demoTag() : null,
        h("span", { class: "tg-row__go" }, [icon("pin"), h("span", { class: "tg-row__golabel", text: t("together.show_map") })]),
      ])]);
    }
    function feedList(feed) {
      if (!feed.length) return h("p", { class: "tg-muted", text: t("together.feed.empty") });
      return h("ol", { class: "tg-feed" }, feed.map(function (e) {
        var kindIcon = e.kind === "problem.fixed" ? "check" : e.kind === "problem.new" ? "alert" :
          e.kind === "initiative.done" ? "heart" : e.kind === "initiative.supported" ? "building" : "users";
        var text = lang() === "kk" ? e.title_kk || e.title_ru : e.title_ru || e.title_kk;
        var inner = [h("span", { class: "tg-feed__ic", "data-kind": e.kind }, [icon(kindIcon)]),
          h("span", { class: "tg-feed__main" }, [h("span", { class: "tg-feed__text", text: text }),
            h("span", { class: "tg-feed__when", text: shortDate(e.at) + " · " + timeLabel(e.at) })]),
          e.demo && !S.pageDemo ? demoTag() : null];
        var go = e.initiative_id ? function () { openInitiative(e.initiative_id); }
          : e.target && typeof opts.openTarget === "function" ? function () { opts.openTarget(e.target.kind, e.target.id); } : null;
        return h("li", {}, [go ? h("button", { type: "button", class: "tg-feed__row", onclick: go }, inner)
          : h("div", { class: "tg-feed__row" }, inner)]);
      }));
    }
    function yardProblems(page) {
      return h("div", {}, [h("p", { class: "tg-muted", text: t("together.problems.hint") }), problemsList(page.problems, 0)]);
    }
    function yardInitiatives(page) {
      var block = page.initiatives || {};
      var items = block.items || [], done = block.done || [];
      if (!items.length && !done.length) {
        return emptyState(t("together.empty.title"), t("together.empty.text"), page.me && page.me.member
          ? h("button", { type: "button", class: "bk-btn bk-btn--primary", onclick: function () { startWizard(page); } },
            [icon("plus"), t("together.yard.propose")]) : null, "users");
      }
      return h("div", {}, [
        items.length ? h("h3", { class: "tg-h3", text: t("together.list.soon") }) : null,
        items.length ? h("div", { class: "tg-grid" }, items.map(function (i) { return card(i); })) : null,
        done.length ? h("h3", { class: "tg-h3", text: t("together.list.done") }) : null,
        done.length ? h("div", { class: "tg-grid" }, done.map(function (i) { return card(i); })) : null,
      ]);
    }
    function yardWorks(page) {
      var ideas = page.ideas || {}, works = page.works || {};
      var out = [h("h3", { class: "tg-h3", text: t("together.works.title") })];
      if (works.status !== "ok") out.push(noDataBlock());
      else if (!(works.items || []).length) out.push(h("p", { class: "tg-calm" }, [icon("check"), t("together.works.empty")]));
      else out.push(h("ul", { class: "tg-rows" }, works.items.map(function (w) {
        return h("li", {}, [h("div", { class: "tg-row tg-row--static" }, [
          h("span", { class: "tg-level tg-level--work" }, [icon(w.type === "outage" ? "alert" : "calendar")]),
          h("span", { class: "tg-row__main" }, [h("span", { class: "tg-row__title", text: label(w, "title") }),
            h("span", { class: "tg-row__meta", text: [w.start ? shortDate(w.start) : "", w.end ? "— " + shortDate(w.end) : ""].join(" ").trim() })]),
          w.demo ? demoTag() : null,
        ])]);
      })));
      if (ideas.status === "ok" && (ideas.items || []).length) {
        out.push(h("h3", { class: "tg-h3", text: t("together.ideas.title") }));
        out.push(h("ul", { class: "tg-rows" }, ideas.items.map(function (i) {
          return h("li", {}, [h("div", { class: "tg-row tg-row--static" }, [
            h("span", { class: "tg-level tg-level--idea" }, [icon("bulb")]),
            h("span", { class: "tg-row__main" }, [h("span", { class: "tg-row__title", text: label(i, "title") }),
              h("span", { class: "tg-row__meta", text: t("together.ideas.votes", { n: i.votes || 0 }) })]),
            i.demo ? demoTag() : null,
          ])]);
        })));
      }
      return h("div", {}, out);
    }
    function yardMembership(page, join) {
      S.busy.yard = true;
      render();
      api("POST", "/together/yards/" + encodeURIComponent(page.yard.id) + (join ? "/join" : "/leave"), {}).then(function (res) {
        S.busy.yard = false;
        page.me.member = !!res.member;
        page.counts.members = res.members;
        page.yard.members = res.members;
        if (join) storage(YARD_KEY, page.yard.id);
        else if (storage(YARD_KEY) === page.yard.id) storage(YARD_KEY, null);
        invalidate("yards");
        toast(join ? t("together.yard.joined_toast") : t("together.yard.left_toast"), "ok");
        render();
      }, function (err) {
        S.busy.yard = false;
        toast(errorText(err), "error");
        render();
      });
    }
    function captainBlock(page) {
      var me = page.me || {};
      if (me.captain) {
        return h("div", { class: "tg-captainbox" }, [
          me.captain_status === "on_review" ? h("p", { class: "tg-muted", text: t("together.yard.captain_review") }) : null,
          h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: function () {
            api("POST", "/together/yards/" + encodeURIComponent(page.yard.id) + "/captain", { remove: true }).then(function () {
              invalidate("yard:"); load("yard:" + page.yard.id, "/together/yards/" + encodeURIComponent(page.yard.id), true);
            }, function (err) { toast(errorText(err), "error"); });
          } }, [t("together.yard.captain_remove")]),
        ]);
      }
      if (page.yard.captain) return null;
      if (!S.captainOpen) {
        return h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: function () { S.captainOpen = true; render(); } },
          [icon("user"), t("together.yard.captain_become")]);
      }
      var input = h("input", { type: "text", maxlength: "40", autocomplete: "given-name", id: "tg-captain-name", "data-focus": "captain-name" });
      return h("form", { class: "tg-captainbox", onsubmit: function (ev) {
        ev.preventDefault();
        api("POST", "/together/yards/" + encodeURIComponent(page.yard.id) + "/captain", { display_name: input.value }).then(function () {
          S.captainOpen = false;
          load("yard:" + page.yard.id, "/together/yards/" + encodeURIComponent(page.yard.id), true);
        }, function (err) { toast(errorText(err), "error"); });
      } }, [
        h("label", { class: "bk-field" }, [h("span", { class: "bk-field__label", text: t("together.yard.captain_name") }), input,
          h("span", { class: "bk-field__hint", text: t("together.yard.captain_hint") })]),
        h("button", { type: "submit", class: "bk-btn" }, [t("together.yard.captain_send")]),
      ]);
    }

    // ================================================================ инициативы: список
    function viewList() {
      var myYard = storage(YARD_KEY);
      var filter = S.filter === "yard" && myYard ? "yard" : "city";
      var key = "list:" + filter;
      var path = "/together/initiatives" + (filter === "yard" ? "?yard=" + encodeURIComponent(myYard) : "");
      load(key, path);
      load("mine", "/together/initiatives?view=mine");
      var e = entryState(key);
      var body;
      if (e.status === "loading") body = e.slow ? skeleton(3) : h("div", { class: "tg-wait" });
      else if (e.status === "error") body = errorState(e.error, function () { load(key, path, true); });
      else {
        var items = (e.data && e.data.items) || [];
        var soon = items.filter(function (i) { return i.status === "published" && !isPast(i); });
        var done = items.filter(function (i) { return i.status === "done"; });
        body = !soon.length && !done.length
          ? emptyState(t("together.empty.title"), t("together.empty.city"), proposeButton(false))
          : h("div", {}, [
            soon.length ? h("h3", { class: "tg-h3", text: t("together.list.soon") }) : null,
            soon.length ? h("div", { class: "tg-grid" }, soon.map(function (i) { return card(i); })) : null,
            done.length ? h("h3", { class: "tg-h3", text: t("together.list.done") }) : null,
            done.length ? h("div", { class: "tg-grid" }, done.map(function (i) { return card(i); })) : null,
          ]);
      }
      var mine = entryState("mine");
      var own = mine.status === "ready" ? ((mine.data && mine.data.items) || []).filter(function (i) {
        return i.status === "on_review" || i.status === "hidden" || i.report_status === "on_review"; }) : [];
      return h("section", { class: "tg-list" }, [
        h("header", { class: "tg-listhead" }, [
          h("div", {}, [title(t("together.list.title")), h("p", { class: "tg-lead", text: t("together.list.lead") })]),
          proposeButton(true),
        ]),
        myYard ? h("div", { class: "bk-seg tg-filter", role: "group", "aria-label": t("together.list.filter") }, [
          h("button", { type: "button", "aria-pressed": String(filter === "city"), onclick: function () { S.filter = "city"; render(); } },
            [t("together.list.all_city")]),
          h("button", { type: "button", "aria-pressed": String(filter === "yard"), onclick: function () { S.filter = "yard"; render(); } },
            [t("together.list.my_yard")]),
        ]) : null,
        own.length ? h("div", { class: "tg-mine" }, [h("h3", { class: "tg-h3", text: t("together.list.mine") }),
          h("ul", { class: "tg-rows" }, own.map(mineRow))]) : null,
        body,
      ]);
    }
    function proposeButton(primary) {
      return h("button", { type: "button", class: "bk-btn" + (primary ? " bk-btn--primary" : ""), "data-focus": "propose-" + primary,
        onclick: function () { startWizard(null); } }, [icon("plus"), t("together.yard.propose")]);
    }
    function mineRow(i) {
      var status = i.report_status === "on_review" ? t("together.report_review") : statusText(i);
      return h("li", {}, [h("button", { type: "button", class: "tg-row", onclick: function () { openInitiative(i.id); } }, [
        h("span", { class: "tg-level tg-level--kind", "data-kind": i.kind }, [icon(kindIcon(i.kind))]),
        h("span", { class: "tg-row__main" }, [h("span", { class: "tg-row__title", text: i.title }),
          h("span", { class: "tg-row__meta", text: whenLabel(i) })]),
        h("span", { class: "tg-status", "data-status": i.status }, [status]),
      ])]);
    }

    // Карточка дела «как в App Store»: обложка с видом, название, когда и где, счётчик, плашка акимата, «Я приду».
    function card(item, cardOpts) {
      cardOpts = cardOpts || {};
      var upcoming = item.status === "published" && !isPast(item);
      var count = item.status === "done"
        ? h("span", { class: "tg-count tg-count--done" }, [icon("heart"), t("together.done_count", { n: item.report && item.report.joined || item.joined })])
        : counter(item.joined);
      var photo = realPhotos(item)[0];
      var node = h("article", { class: "tg-card" + (cardOpts.wide ? " tg-card--wide" : ""), "data-kind": item.kind,
        "data-status": item.status, "data-id": item.id }, [
        photo ? h("img", { class: "tg-card__photo", src: photo.data_url, alt: t("together.after"), loading: "lazy" }) : null,
        h("div", { class: "tg-card__body" }, [
          h("div", { class: "tg-card__head" }, [kindBadge(item.kind), item.demo ? demoTag() : null]),
          h("p", { class: "tg-card__eyebrow" }, [h("span", { text: item.status === "done" ? t("together.status.done") : whenLabel(item) })]),
          h("h3", { class: "tg-card__title" }, [h("button", { type: "button", class: "tg-card__open", "data-focus": "open-" + item.id,
            onclick: function () { openInitiative(item.id); } }, [item.title])]),
          h("p", { class: "tg-card__meta" }, [icon("pin"), label(item.target) || districtName(item.district)]),
          h("div", { class: "tg-card__foot" }, [
            count,
            supportBadge(item.support),
            upcoming && S.role === "resident" ? joinButton(item, node) : null,
          ]),
        ]),
      ]);
      return node;
    }
    function joinButton(item, cardNode) {
      var on = !!item.my_join;
      return h("button", { type: "button", class: "bk-btn tg-join" + (on ? " tg-join--on" : " bk-btn--primary"),
        "aria-pressed": String(on), "data-focus": "join-" + item.id, "aria-busy": S.busy[item.id] ? "true" : null,
        onclick: function (ev) { ev.stopPropagation(); toggleJoin(item, cardNode); } },
      [on ? icon("check") : null, on ? t("together.joined") : t("together.join")]);
    }
    // Оптимистично: число и кнопка меняются сразу; ошибка — возврат и тост «Не получилось».
    function toggleJoin(item, scope) {
      if (S.busy[item.id]) return;
      var join = !item.my_join;
      var before = { joined: item.joined, my: item.my_join };
      item.my_join = join;
      item.joined = Math.max(0, item.joined + (join ? 1 : -1));
      S.busy[item.id] = true;
      paintJoin(item, scope);
      api("POST", "/together/initiatives/" + encodeURIComponent(item.id) + (join ? "/join" : "/leave"), {}).then(function (res) {
        item.joined = res.joined;
        item.my_join = !!res.my_join;
        // Подтверждение — сама кнопка «Вы придёте ✓» и счётчик; тост закрыл бы счётчик внизу экрана.
        syncItem(item);
      }, function (err) {
        item.joined = before.joined;
        item.my_join = before.my;
        toast(errorText(err), "error");
      }).then(function () {
        S.busy[item.id] = false;
        paintJoin(item, scope);
      });
    }
    function paintJoin(item, scope) {
      var nodes = scope ? [scope] : [];
      Array.prototype.forEach.call(host.querySelectorAll('[data-id="' + item.id + '"]'), function (n) {
        if (nodes.indexOf(n) < 0) nodes.push(n);
      });
      nodes.forEach(function (n) {
        bump(n.querySelector(".tg-count:not(.tg-count--done)"), item.joined);
        var btn = n.querySelector(".tg-join");
        if (btn) {
          var fresh = joinButton(item, n);
          btn.replaceWith(fresh);
          if (doc.activeElement === btn || doc.activeElement === doc.body) fresh.focus({ preventScroll: true });
        }
        var unjoin = n.querySelector(".tg-unjoin");
        if (unjoin) unjoin.hidden = !item.my_join;
      });
    }
    // То же дело в других кэшах (двор, список) — то же число.
    function syncItem(item) {
      Object.keys(S.cache).forEach(function (k) {
        var data = S.cache[k].data;
        if (!data) return;
        var lists = [data.items, data.initiatives && data.initiatives.items, data.initiative ? [data.initiative] : null];
        lists.forEach(function (arr) {
          (arr || []).forEach(function (x) { if (x.id === item.id) { x.joined = item.joined; x.my_join = item.my_join; } });
        });
      });
    }
    function openInitiative(id) {
      var r = route();
      go({ name: "initiative", id: id, yard: S.view === "yard" ? (r.name === "yard" ? r.id : r.yard || null) : null });
    }

    // ================================================================ инициатива: карточка
    function viewInitiative(r) {
      var key = "item:" + r.id;
      var staff = S.role === "akimat";
      var path = "/together/initiatives/" + encodeURIComponent(r.id) + (staff ? "?view=staff" : "");
      load(key, path);
      var e = entryState(key);
      if (e.status === "loading") return h("section", { class: "tg-detail" }, [backButton(), e.slow ? skeleton(1) : h("div", { class: "tg-wait" })]);
      if (e.status === "error") return h("section", { class: "tg-detail" }, [backButton(), errorState(e.error, function () { load(key, path, true); })]);
      var item = e.data.initiative;
      var upcoming = item.status === "published" && !isPast(item);
      var facts = h("dl", { class: "tg-facts" }, [
        h("div", { class: "tg-fact" }, [h("dt", {}, [icon("calendar"), t("together.when")]), h("dd", { text: whenLabel(item) })]),
        h("div", { class: "tg-fact" }, [h("dt", {}, [icon("pin"), t("together.where")]), h("dd", {}, [
          h("span", { text: label(item.target) || districtName(item.district) }),
          h("span", { class: "tg-fact__links" }, [
            typeof opts.openTarget === "function" && item.target ? h("button", { type: "button", class: "bk-btn bk-btn--ghost tg-link",
              onclick: function () { opts.openTarget(item.target.kind, item.target.id); } }, [icon("pin"), t("together.show_map")]) : null,
            item.target && item.target.id ? h("button", { type: "button", class: "bk-btn bk-btn--ghost tg-link",
              onclick: function () { openYard(item.target.id); } }, [icon("home"), t("together.open_yard")]) : null,
          ]),
        ])]),
        (item.bring || []).length ? h("div", { class: "tg-fact" }, [h("dt", {}, [icon("list"), t("together.bring")]),
          h("dd", {}, [h("span", { class: "bk-chips bk-chips--wrap tg-bring" }, item.bring.map(function (b) {
            return h("span", { class: "bk-chip tg-chip-static", text: b }); }))])]) : null,
      ]);
      var support = item.support && item.support.by_akimat ? h("div", { class: "tg-supportbox" }, [
        supportBadge(item.support), item.support.note ? h("p", { class: "tg-supportbox__note", text: item.support.note }) : null]) : null;
      var photos = realPhotos(item);
      var photoBlock = photos.length ? h("div", { class: "tg-photos" }, photos.map(function (p) {
        return h("figure", { class: "tg-photo" }, [h("img", { src: p.data_url, alt: t("together.after"), loading: "lazy" }),
          h("figcaption", { text: t("together.after") })]);
      })) : (item.status === "published" || item.status === "done")
        // П1: в демо-мире фото нет — только строка (нарисованное «фото» было бы подделкой). Для прошедшего дела —
        // «пока не добавили»: «появится после дела» про уже сделанное звучало бы как ошибка.
        ? h("p", { class: "tg-afterline" }, [icon("camera"), t(item.status === "done" ? "together.after_none" : "together.after_soon")])
        : null;
      var report = item.report ? h("section", { class: "tg-report" }, [
        h("p", { class: "tg-report__big" }, [icon("heart"), t("together.done_count", { n: item.report.joined || item.joined })]),
        item.report.text ? h("p", { class: "tg-report__text", text: item.report.text }) : null,
        photoBlock,
      ]) : null;
      var bar = upcoming && !staff ? h("div", { class: "tg-actionbar", "data-id": item.id }, [
        counter(item.joined, "tg-count--lg", true),
        joinButton(item, null),
        h("button", { type: "button", class: "bk-btn bk-btn--ghost tg-unjoin", hidden: !item.my_join || null,
          onclick: function () { if (item.my_join) toggleJoin(item, null); } }, [t("together.unjoin")]),
      ]) : null;
      var ownNote = item.mine && item.status === "on_review" ? h("p", { class: "bk-banner tg-banner" }, [icon("clock"), t("together.review.moderation")])
        : item.mine && item.status === "hidden" ? h("p", { class: "bk-banner bk-banner--warn tg-banner" }, [icon("alert"),
          t("together.status.hidden") + (item.hide_reason ? " · " + t("together.reason." + item.hide_reason) : "")])
        : item.mine && item.report_status === "on_review" ? h("p", { class: "bk-banner tg-banner" }, [icon("clock"), t("together.report_review")]) : null;
      var authorReport = item.mine && item.status === "published" && isPastStart(item) && !item.report_status && !staff
        ? reportForm(item, false) : null;
      return h("section", { class: "tg-detail", "data-id": item.id }, [
        backButton(),
        h("div", { class: "tg-detail__head" }, [
          h("div", { class: "tg-card__head" }, [kindBadge(item.kind, true),
            h("span", { class: "tg-status", "data-status": item.status, text: statusText(item) }), item.demo ? demoTag() : null]),
          title(item.title),
        ]),
        ownNote,
        item.text ? h("p", { class: "tg-detail__text", text: item.text }) : null,
        facts,
        support,
        report || (photoBlock && item.status === "published" ? h("section", { class: "tg-after" }, [
          h("p", { class: "tg-h3 tg-report__label", text: t("together.after") }), photoBlock]) : null),
        authorReport,
        staff ? staffActions(item, true) : null,
        bar,
      ]);
    }
    function isPastStart(item) { var p = parts(item.starts_at); return !!p && p.ms - 3600000 <= Date.now(); }

    // ================================================================ мастер инициативы
    function startWizard(page) {
      var yard = page ? page.yard : null;
      var sat = nextSaturday();
      S.wizard = { step: 1, yard: yard, yardGeo: yard ? yard.geometry : null, kind: null, title: "", text: "",
        point: yard && yard.point ? yard.point.slice() : null, placed: false, day: sat, time: "10:00", hours: 3,
        bring: [], custom: "", requestId: "r-" + randomHex(8), similar: null, similarChecked: false, sending: false };
      if (!yard) {
        var yid = storage(YARD_KEY);
        if (yid) {
          var cached = S.cache["yard:" + yid];
          if (cached && cached.data) { S.wizard.yard = cached.data.yard; S.wizard.yardGeo = cached.data.yard.geometry;
            S.wizard.point = cached.data.yard.point ? cached.data.yard.point.slice() : null; }
          else {
            api("GET", "/together/yards/" + encodeURIComponent(yid)).then(function (data) {
              if (S.wizard && !S.wizard.yard) { S.wizard.yard = data.yard; S.wizard.yardGeo = data.yard.geometry;
                S.wizard.point = data.yard.point ? data.yard.point.slice() : null; render(); }
            }, function () { /* без двора — выбор в шаге 2 */ });
          }
        }
      }
      go({ name: "wizard" });
    }
    function nextSaturday() {
      var now = nowParts();
      var add = (6 - now.wd + 7) % 7;
      if (add === 0 && now.h >= 9) add = 7;
      var d = new Date(Date.UTC(now.y, now.mo, now.d + add));
      return { y: d.getUTCFullYear(), mo: d.getUTCMonth(), d: d.getUTCDate() };
    }
    function viewWizard() {
      var w = S.wizard;
      if (!w) return viewList();
      var steps = w.step > 3 ? null : h("div", { class: "bk-wizard tg-wizard__progress" }, [
        h("span", { class: "bk-wizard__label", text: t("together.wizard.step", { n: w.step }) }),
        h("span", { class: "bk-wizard__dots", "aria-hidden": "true" }, [1, 2, 3].map(function (n) {
          return h("i", { "data-state": n < w.step ? "done" : n === w.step ? "current" : "todo" });
        })),
      ]);
      var body = w.step === 1 ? wizardWhat(w) : w.step === 2 ? wizardWhere(w) : w.step === 3 ? wizardBring(w) : wizardReview(w);
      var heading = w.step === 1 ? t("together.wizard.step1") : w.step === 2 ? t("together.wizard.step2")
        : w.step === 3 ? t("together.wizard.step3") : t("together.review.title");
      return h("section", { class: "tg-wizard" }, [
        h("div", { class: "tg-wizard__top" }, [
          h("button", { type: "button", class: "bk-btn bk-btn--ghost tg-back", "data-focus": "wback", onclick: function () {
            if (w.step > 1) { w.step -= 1; render(true); } else { S.wizard = null; back(); }
          } }, [icon("back"), w.step > 1 ? t("together.back") : t("together.close")]),
          h("span", { class: "tg-wizard__name", text: t("together.wizard.title") }),
        ]),
        steps,
        title(heading),
        S.wizardError ? h("p", { class: "bk-field__error tg-werror", role: "alert", text: S.wizardError }) : null,
        body,
      ]);
    }
    function wizardNext(w) {
      S.wizardError = null;
      if (w.step === 1) {
        if (!w.kind) { S.wizardError = t("together.wizard.need_kind"); render(); return; }
        if ((w.title || "").trim().length < 5) { S.wizardError = t("together.wizard.need_name"); render(); focusField("wname"); return; }
      }
      if (w.step === 2) {
        if (!w.yard) { S.wizardError = t("together.wizard.need_yard"); render(); return; }
        if (!w.point) { S.wizardError = t("together.wizard.need_place"); render(); return; }
        var starts = new Date(isoAstana(w.day.y, w.day.mo, w.day.d, w.time));
        if (starts.getTime() < Date.now()) { S.wizardError = errorText({ code: "in_past", status: 422 }); render(); return; }
      }
      w.step += 1;
      if (w.step === 4) checkSimilar(w);
      render(true);
    }
    function focusField(key) { var n = host.querySelector('[data-focus="' + key + '"]'); if (n) n.focus(); }
    function wizardWhat(w) {
      var name = h("input", { type: "text", id: "tg-wname", maxlength: "80", value: w.title, "data-focus": "wname",
        placeholder: t("together.wizard.name_ph." + (w.kind || "other")), oninput: function (ev) { w.title = ev.target.value; } });
      var text = h("textarea", { id: "tg-wtext", maxlength: "600", rows: "3", "data-focus": "wtext",
        oninput: function (ev) { w.text = ev.target.value; } });
      text.value = w.text;
      return h("div", { class: "tg-wstep" }, [
        h("div", { class: "tg-kinds", role: "radiogroup", "aria-label": t("together.wizard.kind") }, KINDS.map(function (k) {
          return h("button", { type: "button", role: "radio", class: "tg-kind", "aria-checked": String(w.kind === k), "data-kind": k,
            "data-focus": "kind-" + k, onclick: function () {
              w.kind = k;
              if (!w.bringTouched) w.bring = list("together.bring." + k).slice(0, 2);
              render();
            } }, [h("span", { class: "tg-kind__ic" }, [icon(kindIcon(k))]), h("span", { text: t("together.kind." + k) })]);
        })),
        h("label", { class: "bk-field", for: "tg-wname" }, [h("span", { class: "bk-field__label", text: t("together.wizard.name") }), name]),
        h("label", { class: "bk-field", for: "tg-wtext" }, [h("span", { class: "bk-field__label", text: t("together.wizard.text") }), text,
          h("span", { class: "bk-field__hint", text: t("together.wizard.text_hint") })]),
        nextButton(w),
      ]);
    }
    function nextButton(w, labelKey) {
      return h("div", { class: "tg-wnav" }, [h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-focus": "wnext",
        onclick: function () { wizardNext(w); } }, [t(labelKey || "together.wizard.next"), icon("forward")])]);
    }
    function wizardWhere(w) {
      var out = [];
      if (!w.yard) {
        var e = entryState("yards");
        load("yards", "/together/yards");
        out.push(h("p", { class: "tg-muted", text: t("together.wizard.need_yard") }));
        if (e.status === "ready") {
          out.push(h("ul", { class: "tg-yardlist" }, ((e.data && e.data.items) || []).slice(0, 8).map(function (y) {
            return h("li", {}, [h("button", { type: "button", class: "tg-yardrow", onclick: function () {
              api("GET", "/together/yards/" + encodeURIComponent(y.id)).then(function (data) {
                w.yard = data.yard; w.yardGeo = data.yard.geometry; w.point = data.yard.point ? data.yard.point.slice() : null;
                render();
              }, function (err) { toast(errorText(err), "error"); });
            } }, [h("span", { class: "tg-yardrow__ic" }, [icon("home")]), h("span", { class: "tg-yardrow__main" }, [
              h("span", { class: "tg-yardrow__name", text: label(y) })]), icon("chevron-right", "tg-yardrow__go")])]);
          })));
        }
        return h("div", { class: "tg-wstep" }, out);
      }
      out.push(h("div", { class: "bk-field" }, [
        h("span", { class: "bk-field__label", text: t("together.wizard.place") + " · " + label(w.yard) }),
        yardPicker(w),
        h("span", { class: "bk-field__hint", text: w.placed ? t("together.wizard.place_set") : t("together.wizard.place_hint") }),
      ]));
      out.push(dayPicker(w));
      out.push(h("div", { class: "bk-field" }, [h("span", { class: "bk-field__label", text: t("together.wizard.time") }),
        h("div", { class: "bk-chips bk-chips--wrap", role: "radiogroup", "aria-label": t("together.wizard.time") }, TIMES.map(function (time) {
          return h("button", { type: "button", role: "radio", class: "bk-chip", "aria-checked": String(w.time === time),
            onclick: function () { w.time = time; render(); } }, [time]);
        }))]));
      out.push(h("div", { class: "bk-field" }, [h("span", { class: "bk-field__label", text: t("together.wizard.duration") }),
        h("div", { class: "bk-seg", role: "group", "aria-label": t("together.wizard.duration") }, HOURS.map(function (n) {
          return h("button", { type: "button", "aria-pressed": String(w.hours === n), onclick: function () { w.hours = n; render(); } },
            [t("together.wizard.hours", { n: n })]);
        }))]));
      out.push(nextButton(w));
      return h("div", { class: "tg-wstep" }, out);
    }
    // Схема двора по форме OSM (R12): нажатие ставит точку сбора. Нет формы — точка двора, выбор не нужен.
    function yardPicker(w) {
      var ring = w.yardGeo && w.yardGeo.type === "Polygon" && w.yardGeo.coordinates && w.yardGeo.coordinates[0];
      if (!ring || ring.length < 4) {
        return h("p", { class: "tg-note" }, [icon("pin"), label(w.yard)]);
      }
      var lat0 = ring.reduce(function (s, p) { return s + p[1]; }, 0) / ring.length;
      var k = Math.cos(lat0 * Math.PI / 180);
      var xs = ring.map(function (p) { return p[0] * k; }), ys = ring.map(function (p) { return p[1]; });
      var minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs), minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
      var span = Math.max(maxX - minX, maxY - minY) || 1e-4;
      var W = 320, H = 200, padPx = 16;
      var scale = Math.min((W - 2 * padPx) / ((maxX - minX) || span), (H - 2 * padPx) / ((maxY - minY) || span));
      var ox = (W - (maxX - minX) * scale) / 2, oy = (H - (maxY - minY) * scale) / 2;
      function toXY(p) { return [ox + (p[0] * k - minX) * scale, oy + (maxY - p[1]) * scale]; }
      function toLonLat(x, y) { return [((x - ox) / scale + minX) / k, maxY - (y - oy) / scale]; }
      var d = ring.map(function (p, i) { var xy = toXY(p); return (i ? "L" : "M") + xy[0].toFixed(1) + " " + xy[1].toFixed(1); }).join("") + "Z";
      var pin = w.point ? toXY(w.point) : null;
      var node = svg("svg", { class: "tg-yardmap", viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": t("together.wizard.place_hint"),
        tabindex: "0" }, [
        svg("path", { d: d, class: "tg-yardmap__area" }),
        pin ? svg("g", { class: "tg-yardmap__pin", transform: "translate(" + pin[0].toFixed(1) + " " + pin[1].toFixed(1) + ")" }, [
          svg("circle", { r: "14", class: "tg-yardmap__halo" }), svg("circle", { r: "7", class: "tg-yardmap__dot" })]) : null,
      ]);
      node.addEventListener("click", function (ev) {
        var box = node.getBoundingClientRect();
        var x = (ev.clientX - box.left) * (W / box.width), y = (ev.clientY - box.top) * (H / box.height);
        var p = toLonLat(x, y);
        if (!insideRing([p[0], p[1]], ring)) return;   // точка сбора — во дворе (R16: «место во дворе»)
        w.point = [Number(p[0].toFixed(6)), Number(p[1].toFixed(6))];
        w.placed = true;
        render();
      });
      return node;
    }
    function insideRing(pt, ring) {
      var inside = false;
      for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        var xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
        if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < (xj - xi) * (pt[1] - yi) / ((yj - yi) || 1e-12) + xi) inside = !inside;
      }
      return inside;
    }
    function dayPicker(w) {
      var days = [];
      var now = nowParts();
      for (var i = 0; i < 9; i++) {
        var d = new Date(Date.UTC(now.y, now.mo, now.d + i));
        days.push({ y: d.getUTCFullYear(), mo: d.getUTCMonth(), d: d.getUTCDate() });
      }
      var same = function (a, b) { return a && b && a.y === b.y && a.mo === b.mo && a.d === b.d; };
      if (!days.some(function (d) { return same(d, w.day); })) days.push(w.day);
      return h("div", { class: "bk-field" }, [h("span", { class: "bk-field__label", text: t("together.wizard.day") }),
        h("div", { class: "bk-chips bk-chips--wrap", role: "radiogroup", "aria-label": t("together.wizard.day") }, days.map(function (d) {
          return h("button", { type: "button", role: "radio", class: "bk-chip", "aria-checked": String(same(d, w.day)),
            onclick: function () { w.day = d; render(); } }, [dayLabel(isoAstana(d.y, d.mo, d.d, "12:00"))]);
        }))]);
    }
    function wizardBring(w) {
      var suggestions = list("together.bring." + (w.kind || "other"));
      var all = suggestions.concat(w.bring.filter(function (b) { return suggestions.indexOf(b) < 0; }));
      var input = h("input", { type: "text", maxlength: "40", placeholder: t("together.wizard.bring_ph"), value: w.custom,
        "data-focus": "bring-input", oninput: function (ev) { w.custom = ev.target.value; },
        onkeydown: function (ev) { if (ev.key === "Enter") { ev.preventDefault(); addBring(); } } });
      function addBring() {
        var v = (w.custom || "").trim();
        if (v && w.bring.length < 8 && w.bring.indexOf(v) < 0) { w.bring.push(v); w.bringTouched = true; }
        w.custom = "";
        render();
        focusField("bring-input");
      }
      return h("div", { class: "tg-wstep" }, [
        h("p", { class: "tg-muted", text: t("together.wizard.bring_hint") }),
        h("div", { class: "bk-chips bk-chips--wrap" }, all.map(function (b) {
          var on = w.bring.indexOf(b) >= 0;
          return h("button", { type: "button", class: "bk-chip", "aria-pressed": String(on), onclick: function () {
            w.bringTouched = true;
            if (on) w.bring = w.bring.filter(function (x) { return x !== b; });
            else if (w.bring.length < 8) w.bring.push(b);
            render();
          } }, [on ? icon("check") : icon("plus"), b]);
        })),
        h("div", { class: "tg-bringadd" }, [h("label", { class: "bk-field" }, [input]),
          h("button", { type: "button", class: "bk-btn", onclick: addBring }, [icon("plus"), t("together.wizard.bring_add")])]),
        nextButton(w, "together.wizard.review"),
      ]);
    }
    function draftItem(w) {
      var starts = isoAstana(w.day.y, w.day.mo, w.day.d, w.time);
      var end = new Date(new Date(starts).getTime() + w.hours * 3600000).toISOString();
      return { id: "preview", kind: w.kind, title: (w.title || "").trim(), text: (w.text || "").trim(), status: "published",
        starts_at: starts, ends_at: end, bring: w.bring.slice(), joined: 0, my_join: false,
        target: w.yard ? { kind: "area", id: w.yard.id, label_ru: w.yard.label_ru, label_kk: w.yard.label_kk } : null,
        district: w.yard && w.yard.district, demo: false };
    }
    function checkSimilar(w) {
      w.similar = null;
      w.similarChecked = false;
      if (!w.point) return;
      api("GET", "/together/initiatives?similar=1&lon=" + w.point[0] + "&lat=" + w.point[1] + "&kind=" + encodeURIComponent(w.kind) +
        "&title=" + encodeURIComponent((w.title || "").slice(0, 80))).then(function (data) {
        w.similar = (data && data.items) || [];
      }, function () { w.similar = []; }).then(function () { w.similarChecked = true; if (S.wizard === w) render(); });
    }
    function wizardReview(w) {
      var item = draftItem(w);
      var pii = piiKinds([item.title, item.text].concat(item.bring).join("\n"));   // и «что взять» (R15-S47)
      pii = pii.filter(function (k, i) { return pii.indexOf(k) === i; });
      var preview = card(item);
      preview.classList.add("tg-card--preview");
      Array.prototype.forEach.call(preview.querySelectorAll("button"), function (b) { b.disabled = true; b.tabIndex = -1; });
      var similar = (w.similar || []).filter(function (s) { return !w.ignoreSimilar; });
      return h("div", { class: "tg-wstep" }, [
        similar.length ? h("div", { class: "bk-banner bk-banner--warn tg-similar", role: "status" }, [
          h("p", { class: "bk-banner__title", text: t("together.similar.title") }),
          h("p", { text: t("together.similar.text") }),
          card(similar[0]),
          h("div", { class: "tg-wnav" }, [
            h("button", { type: "button", class: "bk-btn bk-btn--primary", onclick: function () {
              var id = similar[0].id; S.wizard = null; S.stack.pop(); openInitiative(id);
            } }, [t("together.similar.join")]),
            h("button", { type: "button", class: "bk-btn", onclick: function () { w.ignoreSimilar = true; render(); } },
              [t("together.similar.anyway")]),
          ]),
        ]) : null,
        h("p", { class: "bk-banner tg-banner" }, [icon("info"), t("together.review.privacy")]),
        pii.length ? h("p", { class: "bk-banner bk-banner--warn tg-banner", role: "alert" }, [icon("alert"),
          t("together.review.pii", { what: pii.map(function (k) { return t("together.pii." + k); }).join(", ") })]) : null,
        preview,
        h("p", { class: "tg-muted", text: t("together.review.moderation") }),
        similar.length ? null : h("div", { class: "tg-wnav" }, [
          h("button", { type: "button", class: "bk-btn", onclick: function () { w.step = 1; render(true); } }, [icon("edit"), t("together.review.edit")]),
          h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-focus": "wsend", "aria-busy": w.sending ? "true" : null,
            disabled: w.sending || null, onclick: function () { sendWizard(w, item); } }, [icon("send"), t("together.review.send")]),
        ]),
      ]);
    }
    function sendWizard(w, item) {
      if (w.sending) return;
      w.sending = true;
      render();
      api("POST", "/together/initiatives", { kind: item.kind, title: item.title, text: item.text, lang: textLang(item.title + " " + item.text),
        point: w.point, target: item.target ? { kind: "area", id: item.target.id } : null, starts_at: item.starts_at,
        ends_at: item.ends_at, bring: item.bring, request_id: w.requestId }).then(function (res) {
        S.wizard = null;
        invalidate("list:");
        invalidate("mine");
        invalidate("yard:");
        S.stack.pop();
        go({ name: "sent", item: res.initiative });
      }, function (err) {
        w.sending = false;
        S.wizardError = errorText(err);
        if (err.field === "title") w.step = 1;
        else if (err.field === "starts_at" || err.field === "point" || err.field === "target") w.step = 2;
        render(true);
      });
    }
    function viewSent(r) {
      var item = r.item || {};
      var published = item.status === "published";
      return h("section", { class: "tg-sent" }, [
        h("div", { class: "bk-empty tg-empty", role: "status" }, [
          h("span", { class: "tg-sent__ic" }, [icon(published ? "check" : "clock")]),
          title(published ? t("together.sent.published") : t("together.sent.title")),
          h("p", { class: "bk-empty__text", text: t("together.sent.text") }),
          h("div", { class: "tg-wnav" }, [
            h("button", { type: "button", class: "bk-btn bk-btn--primary", onclick: function () { reset(null); } }, [t("together.back_list")]),
            item.id ? h("button", { type: "button", class: "bk-btn", onclick: function () { S.stack = []; openInitiative(item.id); } },
              [t("together.sent.mine")]) : null,
          ]),
        ]),
      ]);
    }

    // ================================================================ акимат
    function viewStaff() {
      var tab = S.staffTab;
      var key = "staff:" + tab;
      var path = "/together/initiatives?view=staff&tab=" + tab;   // queue | waiting | going | done
      load(key, path);
      var e = entryState(key);
      var counts = (e.data && e.data.counts) || (S.cache["staff:queue"] && S.cache["staff:queue"].data && S.cache["staff:queue"].data.counts) || {};
      var body;
      if (e.status === "loading") body = e.slow ? skeleton(3) : h("div", { class: "tg-wait" });
      else if (e.status === "error") {
        body = e.error && (e.error.status === 401 || e.error.status === 403) ? loginPrompt(function () { load(key, path, true); })
          : errorState(e.error, function () { load(key, path, true); });
      } else body = staffBody(e.data, tab);
      return h("section", { class: "tg-staff" }, [
        h("header", { class: "tg-listhead" }, [h("div", {}, [title(t("together.staff.title")),
          h("p", { class: "tg-lead", text: t("together.staff.lead") })])]),
        h("div", { class: "bk-tabs tg-tabs", role: "tablist", "aria-label": t("together.staff.title") },
          ["queue", "waiting", "going", "done"].map(function (id) {
            return h("button", { type: "button", role: "tab", "aria-selected": String(tab === id), tabindex: tab === id ? "0" : "-1",
              "data-focus": "stab-" + id, onkeydown: tabKeys, onclick: function () { S.staffTab = id; S.open = null; render(); } },
            [t("together.staff." + id), typeof counts[id] === "number" ? h("span", { class: "bk-num", text: formatNumber(counts[id]) }) : null]);
          })),
        body,
      ]);
    }
    function loginPrompt(retry) {
      var shell = root.CivicShell;
      return h("div", { class: "bk-empty tg-empty", role: "status" }, [
        h("span", { class: "tg-sent__ic" }, [icon("user")]),
        h("p", { class: "bk-empty__title", text: t("together.staff.login") }),
        h("div", { class: "tg-wnav" }, [
          shell && typeof shell.openEditor === "function" ? h("button", { type: "button", class: "bk-btn bk-btn--primary",
            onclick: function () { shell.openEditor(); } }, [t("together.staff.login_btn")]) : null,
          h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: retry }, [icon("refresh"), t("common.action.retry")]),
        ]),
      ]);
    }
    function staffBody(data, tab) {
      var items = data.items || [];
      var out = [];
      if (tab === "queue") {
        if (!items.length && !(data.reports || []).length && !(data.captains || []).length) {
          return emptyState(t("together.staff.empty_queue"), null, null, "check");
        }
        if (items.length) out.push(h("ul", { class: "tg-staffrows" }, items.map(function (i) { return h("li", {}, [staffRow(i, tab)]); })));
        if ((data.reports || []).length) {
          out.push(h("h3", { class: "tg-h3", text: t("together.staff.reports") }));
          out.push(h("ul", { class: "tg-staffrows" }, data.reports.map(function (i) { return h("li", {}, [reportRow(i)]); })));
        }
        if ((data.captains || []).length) {
          out.push(h("h3", { class: "tg-h3", text: t("together.staff.captains") }));
          out.push(h("ul", { class: "tg-staffrows" }, data.captains.map(function (c) { return h("li", {}, [captainRow(c)]); })));
        }
        return h("div", {}, out);
      }
      if (!items.length) return emptyState(t("together.staff.empty"), null, null, "list");
      return h("ul", { class: "tg-staffrows" }, items.map(function (i) { return h("li", {}, [staffRow(i, tab)]); }));
    }
    function flagsLine(flags) {
      if (!flags || !flags.length) return null;
      // Вид пометки без своей подписи (новый у R04) — «личные данные», а не ключ словаря.
      var known = dict("ru");
      return h("p", { class: "tg-flags", role: "note" }, [icon("alert"),
        t("together.staff.flags", { what: flags.map(function (f) {
          return t(known["together.pii." + f] ? "together.pii." + f : "together.pii.other"); })
          .filter(function (x, i, a) { return a.indexOf(x) === i; }).join(", ") })]);
    }
    function staffRow(item, tab) {
      var original = item.original || {};
      var changed = original.title && (original.title !== item.title || (original.text || "") !== (item.text || ""));
      return h("article", { class: "tg-staffrow", "data-id": item.id, "data-status": item.status }, [
        h("div", { class: "tg-staffrow__head" }, [
          h("span", { class: "tg-level tg-level--kind", "data-kind": item.kind }, [icon(kindIcon(item.kind))]),
          h("div", { class: "tg-row__main" }, [
            h("button", { type: "button", class: "tg-staffrow__title", onclick: function () { openInitiative(item.id); } },
              [tab === "queue" ? original.title || item.title : item.title]),
            h("span", { class: "tg-row__meta", text: [label(item.target) || districtName(item.district), whenLabel(item),
              tab === "queue" && item.created_at ? t("together.staff.received", { date: shortDate(item.created_at) }) : ""].filter(Boolean).join(" · ") }),
          ]),
          item.demo ? demoTag() : null,
          tab !== "queue" ? counter(item.joined) : null,
        ]),
        tab === "queue" ? flagsLine(item.flags) : null,
        tab === "queue" && (original.text || item.text) ? h("p", { class: "tg-quote", text: original.text || item.text }) : null,
        tab === "queue" && changed ? h("p", { class: "tg-muted", text: t("together.staff.original") }) : null,
        item.support ? supportBadge(item.support) : null,
        tab === "hidden" && item.hide_reason ? h("p", { class: "tg-muted", text: t("together.reason." + item.hide_reason) }) : null,
        tab === "done" && item.report ? h("p", { class: "tg-muted" }, [t("together.done_count", { n: item.report.joined || item.joined })]) : null,
        staffActions(item, false),
      ]);
    }
    function staffActions(item, inDetail) {
      if (S.role !== "akimat") return null;
      var open = S.open && S.open.id === item.id ? S.open.kind : null;
      var buttons = [];
      if (item.status === "on_review") {
        buttons.push(actionButton(item, "publish", t("together.staff.publish"), true));
        buttons.push(h("button", { type: "button", class: "bk-btn", onclick: function () { toggleOpen(item.id, "hide"); } }, [t("together.staff.hide")]));
      } else if (item.status === "published") {
        var supported = item.support && item.support.by_akimat;
        buttons.push(h("button", { type: "button", class: "bk-btn" + (supported ? "" : " bk-btn--primary"), "data-focus": "support-" + item.id,
          onclick: function () { toggleOpen(item.id, "support"); } }, [icon("building"), supported ? t("together.staff.support_more") : t("together.staff.support")]));
        buttons.push(h("button", { type: "button", class: "bk-btn" + (supported ? " bk-btn--primary" : ""), "data-focus": "done-" + item.id,
          onclick: function () { toggleOpen(item.id, "report"); } }, [icon("check"), t("together.staff.done_btn")]));
        buttons.push(h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: function () { toggleOpen(item.id, "hide"); } }, [t("together.staff.hide")]));
      }
      if (!buttons.length) return null;
      var form = open === "hide" ? hideForm(item) : open === "support" ? supportForm(item) : open === "report" ? reportForm(item, true) : null;
      return h("div", { class: "tg-staffactions" + (inDetail ? " tg-staffactions--detail" : "") }, [h("div", { class: "tg-wnav" }, buttons), form]);
    }
    function toggleOpen(id, kind) {
      S.open = S.open && S.open.id === id && S.open.kind === kind ? null : { id: id, kind: kind };
      render();
      var first = host.querySelector(".tg-form [data-first]");
      if (first) first.focus();
    }
    function actionButton(item, action, text, primary) {
      return h("button", { type: "button", class: "bk-btn" + (primary ? " bk-btn--primary" : ""), "aria-busy": S.busy[item.id] ? "true" : null,
        disabled: S.busy[item.id] || null, onclick: function () { moderate(item, { action: action }); } }, [text]);
    }
    function moderate(item, body, toastText) {
      S.busy[item.id] = true;
      render();
      api("POST", "/together/initiatives/" + encodeURIComponent(item.id) + "/moderate", body).then(function () {
        S.open = null;
        toast(toastText || (body.action === "hide" ? t("together.staff.hidden_toast") : t("together.staff.published_toast")), "ok");
        refreshStaff(item.id);
      }, function (err) { toast(errorText(err), "error"); }).then(function () { S.busy[item.id] = false; render(); });
    }
    function refreshStaff(id) {
      invalidate("staff:");
      invalidate("item:" + id);
      invalidate("list:");
      invalidate("yard:");
      load("staff:" + S.staffTab, "/together/initiatives?view=staff&tab=" + S.staffTab, true);
      if (route().name === "initiative") load("item:" + id, "/together/initiatives/" + encodeURIComponent(id) + "?view=staff", true);
    }
    function hideForm(item) {
      var form = S.forms[item.id + ":hide"] = S.forms[item.id + ":hide"] || { reason: null };
      return h("div", { class: "tg-form" }, [
        h("div", { class: "bk-chips bk-chips--wrap", role: "radiogroup" }, REASONS.map(function (r, n) {
          return h("button", { type: "button", role: "radio", class: "bk-chip", "aria-checked": String(form.reason === r), "data-first": n === 0 || null,
            onclick: function () { form.reason = r; render(); } }, [t("together.reason." + r)]);
        })),
        h("button", { type: "button", class: "bk-btn bk-btn--danger", disabled: !form.reason || S.busy[item.id] || null,
          onclick: function () { moderate(item, { action: "hide", reason: form.reason }); } }, [t("together.staff.hide_send")]),
      ]);
    }
    function supportForm(item) {
      var current = item.support || {};
      var form = S.forms[item.id + ":support"] = S.forms[item.id + ":support"] || {
        inventory: current.by_akimat ? !!current.inventory : true, pickup: current.by_akimat ? !!current.pickup_service : true,
        note: current.note || "" };
      var note = h("input", { type: "text", maxlength: "200", value: form.note, placeholder: t("together.staff.note_ph"),
        oninput: function (ev) { form.note = ev.target.value; } });
      return h("form", { class: "tg-form", onsubmit: function (ev) {
        ev.preventDefault();
        S.busy[item.id] = true;
        render();
        api("POST", "/together/initiatives/" + encodeURIComponent(item.id) + "/support", { inventory: form.inventory,
          pickup_service: form.pickup ? "waste" : null, note: form.note }).then(function () {
          S.open = null;
          toast(t("together.staff.supported_toast"), "ok");
          refreshStaff(item.id);
        }, function (err) { toast(errorText(err), "error"); }).then(function () { S.busy[item.id] = false; render(); });
      } }, [
        h("p", { class: "tg-form__title", text: t("together.staff.support_title") }),
        checkbox(form, "inventory", t("together.staff.inventory"), true),
        checkbox(form, "pickup", t("together.staff.pickup")),
        h("label", { class: "bk-field" }, [h("span", { class: "bk-field__label", text: t("together.staff.note") }), note]),
        h("button", { type: "submit", class: "bk-btn bk-btn--primary", disabled: (!form.inventory && !form.pickup) || S.busy[item.id] || null,
          "aria-busy": S.busy[item.id] ? "true" : null }, [icon("building"), t("together.staff.support_send")]),
      ]);
    }
    function checkbox(form, field, text, first) {
      var input = h("input", { type: "checkbox", "data-first": first || null });
      input.checked = !!form[field];
      input.addEventListener("change", function () { form[field] = input.checked; render(); });
      return h("label", { class: "tg-check" }, [input, h("span", { text: text })]);
    }
    function reportForm(item, staff) {
      var form = S.forms[item.id + ":report"] = S.forms[item.id + ":report"] || { text: "", photo: null, busy: false, error: null };
      var text = h("textarea", { rows: "3", maxlength: "600", placeholder: t("together.staff.report_ph"), "data-first": "1",
        oninput: function (ev) { form.text = ev.target.value; } });
      text.value = form.text;
      var file = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", class: "bk-sr-only", id: "tg-photo-" + item.id,
        onchange: function (ev) {
          var f = ev.target.files && ev.target.files[0];
          if (!f) return;
          shrink(f).then(function (photo) { form.photo = photo; form.error = null; render(); },
            function () { form.error = t("together.err.bad_photo"); render(); });
        } });
      return h("form", { class: "tg-form", onsubmit: function (ev) {
        ev.preventDefault();
        if (form.busy) return;
        form.busy = true;
        render();
        var body = { text: form.text || undefined };
        if (form.photo) body.photo = form.photo;
        api("POST", "/together/initiatives/" + encodeURIComponent(item.id) + "/report", body).then(function () {
          S.open = null;
          delete S.forms[item.id + ":report"];
          toast(staff ? t("together.staff.done_toast") : t("together.report_review"), "ok");
          if (staff) refreshStaff(item.id);
          else { invalidate("item:" + item.id); invalidate("mine"); load("item:" + item.id, "/together/initiatives/" + encodeURIComponent(item.id), true); }
        }, function (err) { form.error = errorText(err); }).then(function () { form.busy = false; render(); });
      } }, [
        h("p", { class: "tg-form__title", text: t("together.staff.report_title") }),
        h("label", { class: "bk-field" }, [h("span", { class: "bk-field__label", text: t("together.staff.report_text") }), text]),
        h("div", { class: "tg-photoadd" }, [
          file,
          h("label", { class: "bk-btn", for: "tg-photo-" + item.id, tabindex: "0", onkeydown: function (ev) {
            if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); file.click(); } } }, [icon("camera"), t("together.staff.photo_add")]),
          form.photo ? h("img", { class: "tg-photoadd__thumb", src: form.photo.thumb || form.photo.data_url, alt: t("together.staff.photo_ready") }) : null,
          h("span", { class: "bk-field__hint", text: t("together.staff.photo_hint") }),
        ]),
        form.error ? h("p", { class: "bk-field__error", role: "alert", text: form.error }) : null,
        h("button", { type: "submit", class: "bk-btn bk-btn--primary", disabled: form.busy || null, "aria-busy": form.busy ? "true" : null },
          [icon("check"), staff ? t("together.staff.report_send") : t("together.review.send")]),
      ]);
    }
    function reportRow(item) {
      var draft = item.report_draft || {};
      return h("article", { class: "tg-staffrow", "data-id": item.id }, [
        h("div", { class: "tg-staffrow__head" }, [
          h("span", { class: "tg-level tg-level--kind", "data-kind": item.kind }, [icon("heart")]),
          h("div", { class: "tg-row__main" }, [h("span", { class: "tg-staffrow__title", text: item.title }),
            h("span", { class: "tg-row__meta", text: label(item.target) })]),
        ]),
        flagsLine(draft.flags),
        draft.text ? h("p", { class: "tg-quote", text: draft.text }) : null,
        (draft.photos || []).length ? h("div", { class: "tg-photos tg-photos--small" }, draft.photos.map(function (p) {
          return h("img", { src: p.data_url || p.src, alt: t("together.after") }); })) : null,
        h("div", { class: "tg-wnav" }, [
          h("button", { type: "button", class: "bk-btn bk-btn--primary", onclick: function () {
            moderate(item, { action: "publish_report" }, t("together.staff.done_toast")); } }, [t("together.staff.report_publish")]),
          h("button", { type: "button", class: "bk-btn", onclick: function () { moderate(item, { action: "hide_report" }); } },
            [t("together.staff.report_hide")]),
        ]),
      ]);
    }
    function captainRow(c) {
      function decide(action) {
        api("POST", "/together/yards/" + encodeURIComponent(c.yard_id) + "/moderate", { action: action }).then(function () {
          toast(action === "publish" ? t("together.staff.published_toast") : t("together.staff.hidden_toast"), "ok");
          refreshStaff("");
        }, function (err) { toast(errorText(err), "error"); });
      }
      return h("article", { class: "tg-staffrow" }, [
        h("div", { class: "tg-staffrow__head" }, [h("span", { class: "tg-level tg-level--kind" }, [icon("user")]),
          h("div", { class: "tg-row__main" }, [h("span", { class: "tg-staffrow__title", text: c.display_name }),
            h("span", { class: "tg-row__meta", text: label(c) })])]),
        flagsLine(c.flags),
        h("div", { class: "tg-wnav" }, [
          h("button", { type: "button", class: "bk-btn bk-btn--primary", onclick: function () { decide("publish"); } }, [t("together.staff.publish")]),
          h("button", { type: "button", class: "bk-btn", onclick: function () { decide("hide"); } }, [t("together.staff.hide_send")]),
        ]),
      ]);
    }

    // ================================================================ клавиатура, язык, внешнее открытие
    function onKey(event) {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      var r = route();
      if (S.open) { S.open = null; render(); event.preventDefault(); return; }
      if (r.name === "wizard" && S.wizard && S.wizard.step > 1) { S.wizard.step -= 1; render(true); event.preventDefault(); return; }
      if (S.stack.length) {
        if (r.name === "wizard") S.wizard = null;
        back();
        event.preventDefault();
        event.stopPropagation();   // Esc закрывает один слой: карточку, а не весь раздел (как в эталоне)
      }
    }
    host.addEventListener("keydown", onKey);
    var I18n = root.BirgeI18n;
    var langOff = null;
    if (I18n && typeof I18n.onChange === "function") {
      var listener = function () { render(); };
      var ret = I18n.onChange(listener);
      langOff = typeof ret === "function" ? ret : null;
    }
    function openExternal(kind, id) {
      S.stack = [{ name: kind === "yard" ? "yard" : "initiative", id: id }];
      S.open = null;
      render(true);
      syncPath();
    }
    var controller = {
      setLang: function () { render(); },
      setPath: setPath,
      rerender: function () { render(); },
      open: openExternal,
      refresh: function () { Object.keys(S.cache).forEach(function (k) { S.cache[k].status = "stale"; }); render(); },
      destroy: function () {
        S.destroyed = true;
        host.removeEventListener("keydown", onKey);
        if (langOff) langOff();
        off.forEach(function (fn) { fn(); });
        mounted = mounted.filter(function (m) { return m !== controller; });
        controller.view = null;
      },
      view: S.view,
      role: S.role,
    };
    mounted.push(controller);
    if (pending && pending.screen === S.view) {
      var p = pending;
      pending = null;
      // Оболочка с путями уже передала путь (opts.path) — тот же переход, повторять не нужно.
      if (currentPath && pathOf(route()) !== null) render(true);
      else openExternal(p.kind, p.id);
    } else {
      render(true);
    }
    return controller;
  }

  // ------------------------------------------------------------------ выбор двора на карте (IA R11 §5.1)
  // Экран закрывается, сверху — строка «Нажмите на свой двор»; нажатие внутри двора OSM (R12 /yard) открывает «Мой двор».
  // Esc или «Отмена» — выход. Карта сама не двигается.
  function mapObject() {
    try {
      // eslint-disable-next-line no-undef
      return typeof map !== "undefined" && map && typeof map.on === "function" && typeof map.project === "function" ? map : null;
    } catch (e) { return null; }
  }
  // Карта есть сразу или появится в течение нескольких секунд (оболочка создаёт её после загрузки стиля).
  function whenMap(given, done) {
    var tries = 0;
    (function check() {
      var m = given && typeof given.on === "function" ? given : mapObject();
      if (m) { done(m); return; }
      if (++tries < 40) setTimeout(check, 100);
    })();
  }
  var picking = null;
  function stopPick() {
    if (!picking) return;
    try { picking.map.off("click", picking.onClick); } catch (e) { /* карта снята */ }
    doc.removeEventListener("keydown", picking.onKey, true);
    if (picking.bar.parentNode) picking.bar.parentNode.removeChild(picking.bar);
    if (picking.canvas) picking.canvas.style.cursor = "";
    picking = null;
  }
  function startPick(mapObj, base) {
    stopPick();
    var text = h("span", { class: "tg-pickbar__text", text: t("together.pick.on_map_hint") });
    var bar = h("div", { class: "tg-pickbar bk-app", role: "status", "aria-live": "polite" }, [
      icon("pin"), text,
      h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: stopPick }, [t("common.action.cancel")]),
    ]);
    doc.body.appendChild(bar);
    var canvas = mapObj.getCanvas ? mapObj.getCanvas() : null;
    if (canvas) canvas.style.cursor = "crosshair";
    function onClick(ev) {
      var ll = ev.lngLat;
      if (!ll) return;
      request(base || "/api/civic/v2", "GET", "/yard?lon=" + ll.lng.toFixed(6) + "&lat=" + ll.lat.toFixed(6)).then(function (data) {
        if (data && data.yard && data.yard.id) { stopPick(); open("yard", data.yard.id); }
        else text.textContent = t("together.pick.not_found_map");
      }, function () { text.textContent = t("together.error.text"); });
    }
    function onKey(ev) { if (ev.key === "Escape") { stopPick(); ev.preventDefault(); ev.stopPropagation(); } }
    mapObj.on("click", onClick);
    doc.addEventListener("keydown", onKey, true);
    picking = { map: mapObj, onClick: onClick, onKey: onKey, bar: bar, canvas: canvas };
  }

  // ------------------------------------------------------------------ слой карты «Инициативы»
  // Капсула ui-kit (иконка вида + число «придут»); «сделано» — зелёная галочка. По умолчанию выключен (CONTRACT §8).
  // Капсулы не наползают: на мелком масштабе видна важная (ближайшее дело, больше соседей), остальные — при приближении.
  var layerState = { markers: [], token: 0, map: null, onMove: null };
  function showLayer(map) {
    hideLayer();
    var token = ++layerState.token;
    if (!map || !root.maplibregl || typeof root.maplibregl.Marker !== "function") return;
    request("/api/civic/v2", "GET", "/together/initiatives?limit=60").then(function (data) {
      if (token !== layerState.token) return;
      ((data && data.items) || []).forEach(function (item) {
        if (!item.point) return;
        var done = item.status === "done";
        if (item.status === "published" && isPast(item)) return;
        var n = done ? (item.report && item.report.joined || item.joined) : item.joined;
        // Капсула ui-kit «дата · число» со значком вида (IA R11 §5.2); «сделано» — галочка и число соседей.
        var el = h("button", { type: "button", class: "tg-pin" + (done ? " tg-pin--done" : ""), "data-kind": item.kind,
          "aria-label": item.title + " · " + (done ? t("together.done_count", { n: n }) : whenLabel(item) + " · " + t("together.count", { n: n })),
          title: item.title }, [icon(done ? "check" : kindIcon(item.kind)),
          done ? null : h("span", { class: "tg-pin__date", text: shortDate(item.starts_at) }),
          h("span", { class: "tg-pin__n", text: formatNumber(n) })]);
        el.addEventListener("click", function (ev) { ev.stopPropagation(); open("initiative", item.id); });
        var marker = new root.maplibregl.Marker({ element: el, anchor: "bottom" }).setLngLat(item.point).addTo(map);
        // Под значками тепловой карты: значки R07 — тоже HTML-метки, порядок в DOM = порядок слоёв.
        var firstMarker = el.parentNode && el.parentNode.querySelector(".maplibregl-marker");
        if (firstMarker && firstMarker !== el) el.parentNode.insertBefore(el, firstMarker);
        // Важнее — предстоящее дело (по дате), затем больше соседей; «сделано» — после предстоящих.
        marker.tgRank = [done ? 1 : 0, done ? 0 : Date.parse(item.starts_at) || 0, -n];
        layerState.markers.push(marker);
      });
      layerState.map = map;
      layerState.onMove = function () { declutter(map); };
      map.on("moveend", layerState.onMove);
      declutter(map);
    }, function () {
      toast(t("together.error.text"), "error");
    });
  }
  function declutter(map) {
    var placed = [];
    layerState.markers.slice().sort(function (a, b) {
      for (var i = 0; i < 3; i++) if (a.tgRank[i] !== b.tgRank[i]) return a.tgRank[i] - b.tgRank[i];
      return 0;
    }).forEach(function (marker) {
      var el = marker.getElement();
      var p = map.project(marker.getLngLat());
      var w = el.offsetWidth || 56, hh = el.offsetHeight || 30;
      var box = [p.x - w / 2 - 4, p.y - hh - 4, p.x + w / 2 + 4, p.y + 4];
      var hit = placed.some(function (b) { return !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]); });
      el.style.visibility = hit ? "hidden" : "";
      el.tabIndex = hit ? -1 : 0;
      if (hit) el.setAttribute("aria-hidden", "true"); else el.removeAttribute("aria-hidden");
      if (!hit) placed.push(box);
    });
  }
  function hideLayer() {
    layerState.token++;
    if (layerState.map && layerState.onMove) { try { layerState.map.off("moveend", layerState.onMove); } catch (e) { /* карта снята */ } }
    layerState.map = null;
    layerState.onMove = null;
    layerState.markers.forEach(function (m) { try { m.remove(); } catch (e) { /* карта уже снята */ } });
    layerState.markers = [];
  }

  // ------------------------------------------------------------------ оболочка: разделы, слой, ссылки
  function title2(key) { return { ru: dict("ru")[key], kk: dict("kk")[key] }; }
  var registered = false;
  function register(attempt) {
    var shell = root.BirgeShell;
    if (registered) return;
    if (!shell || typeof shell.registerScreen !== "function") {
      if ((attempt || 0) < 40) setTimeout(function () { register((attempt || 0) + 1); }, 250);
      return;
    }
    registered = true;
    // Подписи — {ru, kk}, а не titleKey: словарь R11 может загрузиться позже, меню не должно показать «together.nav.yard».
    shell.registerScreen({ id: "yard", modes: ["resident"], title: title2("together.nav.yard"),
      mount: function (el, o) { return mount(el, Object.assign({}, o, { view: "yard" })); } });
    shell.registerScreen({ id: "together", modes: ["resident", "akimat"], title: title2("together.nav.initiatives"),
      mount: function (el, o) { return mount(el, Object.assign({}, o, { view: "initiatives" })); } });
    if (typeof shell.registerLayer === "function") {
      shell.registerLayer({ id: "initiatives", modes: ["resident", "akimat"], title: title2("together.layer"), show: showLayer, hide: hideLayer });
    }
    // Оболочка стартует раньше нас (birge.js выполняется до этого файла): адрес «#yard» / «#together» она увела на
    // карту, раздела ещё не было. Теперь раздел есть — открываем его, не добавляя запись в историю.
    var m = /^#(yard|together)$/.exec(root.location.hash || "");
    if (m && shell.section === "map" && typeof shell.setSection === "function") shell.setSection(m[1], { hash: false });
  }
  // Открыть двор или дело: из палитры R01 (сцена 7), ленты R06, «Ситуационного центра» R08.
  function open(kind, id) {
    if (!/^(yard|initiative)$/.test(kind) || !/^[A-Za-z0-9._:-]{3,96}$/.test(String(id || ""))) return false;
    var shell = root.BirgeShell;
    // Акимат открывает двор внутри «Инициатив жителей» (пункта «Мой двор» у акимата нет — IA R11 §5.1).
    var screen = kind === "yard" && (!shell || shell.mode !== "akimat") ? "yard" : "initiatives";
    var section = screen === "yard" ? "yard" : "together";
    var live = mounted.filter(function (m) { return m.view === screen; })[0];
    if (live && shell && shell.section === section) { live.open(kind, id); return true; }
    pending = { kind: kind, id: id, screen: screen };
    // Оболочка R01 раунда 15 понимает путь (#together/i-…); FINAL-4 — нет, тогда сработает pending.
    if (shell && typeof shell.setSection === "function") shell.setSection(section, { path: id });
    return true;
  }
  // «#together/i-…» и «#yard/yard-…» (CONTRACT §5.8 link) — после обработчиков оболочки (она такие адреса не знает).
  function followHash() {
    var m = /^#(together|yard)\/([A-Za-z0-9._:-]{3,96})$/.exec(root.location.hash || "");
    if (!m) return;
    var kind = m[1] === "yard" ? "yard" : (/^yard-|^cell-/.test(m[2]) ? "yard" : "initiative");
    setTimeout(function () {
      var shell = root.BirgeShell;
      // Оболочка с путями (R01, раунд 15) уже открыла раздел и передала путь модулю — второй переход не нужен.
      if (shell && shell.section === m[1]) return;
      open(kind, m[2]);
      try { root.history.replaceState(null, "", root.location.pathname + root.location.search + "#" + (kind === "yard" && (!root.BirgeShell || root.BirgeShell.mode !== "akimat") ? "yard" : "together")); } catch (e) { /* без адреса */ }
    }, 0);
  }

  root.BirgeTogether = { mount: mount, open: open, version: "r15-1", _layer: { show: showLayer, hide: hideLayer } };
  if (doc) {
    // Сразу, если birge.js уже выполнен (defer по порядку): разделы есть до старта оболочки, адрес «#yard» открывается
    // с первой загрузки. Иначе — после разбора страницы (и повтор, пока оболочка не появится).
    if (root.BirgeShell && typeof root.BirgeShell.registerScreen === "function") register(0);
    else if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", function () { register(0); });
    else register(0);
    root.addEventListener("hashchange", followHash);
    // «#together/i-…» — после старта оболочки (она такой адрес сначала ведёт на карту).
    if (doc.readyState === "complete") followHash();
    else root.addEventListener("load", followHash);
  }
})(typeof self !== "undefined" ? self : this);
