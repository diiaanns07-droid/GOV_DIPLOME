/*
 * R09 · раунд 14 · Путь жителя v2: «Сообщить о проблеме» → место → текст и категория →
 * «Я тоже» (если уже сообщали) → отправлено + статус. И раздел «Мои обращения».
 *
 * Подключение (R01):
 *   <script src="/civic/feedback/categories_v2.js"></script>      // сгенерирован из categories_v2.json
 *   <script src="/civic/feedback/complaint-strings.js"></script>  // запасные тексты, если нет i18n R11
 *   <script src="/civic/feedback/complaint.js"></script>
 *   const ui = BirgeComplaint.mount({
 *     root: document.querySelector("#app"),            // куда встроить панель/шторку и главную кнопку
 *     map: BirgeComplaint.maplibreAdapter(maplibreMap) // или свой адаптер (см. ниже)
 *   });
 *   ui.open(); ui.openMine(); ui.close(); ui.destroy();
 *
 * Адаптер карты — объект с методами (все необязательны, кроме onPick):
 *   onPick(cb) -> отписка   cb({lon, lat}) при нажатии на карту, пока идёт выбор места
 *   setPickMode(bool)       курсор-прицел
 *   highlight(target, geometry, point)  точная подсветка выбранной цели (GeoJSON geometry)
 *   clear()                 снять подсветку
 *   flyTo([lon, lat])       только по действию жителя («Моё местоположение»)
 *
 * Сервисы (CONTRACT §7): R12 GET /targets, R04 POST /classify и /similar, R09 /complaints.
 * Без /classify и /similar форма работает: категория выбирается вручную, ошибок житель не видит.
 * Событие для тепловой карты (R07): window "birge:complaint" {type: "created"|"metoo", complaint_id,
 * target, category, reporters} — сразу после успешной отправки или «Я тоже».
 */
(function () {
  "use strict";

  var API = "/api/civic/v2";
  var ML_TIMEOUT_MS = 2500;      // подсказки модели не должны задерживать жителя
  var NET_TIMEOUT_MS = 12000;
  var CLASSIFY_DEBOUNCE_MS = 700;
  var CLASSIFY_MIN_CHARS = 8;
  // R12 /targets: первая загрузка графа на холодном сервере ~2–4 с (R01 прогревает при старте). Место —
  // главный шаг, поэтому ждём дольше, чем подсказки модели; не дождались — «примерное место».
  var TARGETS_TIMEOUT_MS = 5000;
  var DEVICE_KEY = "birge.device";
  var LANG_KEY = "birge.lang";
  var DRAFT_KEY = "birge.complaint.draft";      // черновик на устройстве (волна 1, п. 10): переживает закрытие вкладки
  var DRAFT_DAYS = 7;
  var OUTBOX_KEY = "birge.complaint.outbox";    // очередь отправки без сети
  var SEEN_KEY = "birge.complaint.changes_seen"; // когда житель последний раз видел «Что изменилось»
  var RETRY_DELAYS = [5000, 15000, 30000, 60000];
  var TOTAL_STEPS = 5;
  var MOBILE_QUERY = "(max-width: 1023px)";
  // Запасные названия месяцев (основной формат — BirgeI18n.formatDate R11). kk — полные: «қаз» читается как «гусь».
  var MONTHS = {
    ru: ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
    kk: ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"]
  };
  var NBSP = "\u00a0";
  // Подписи ячейки «примерное место» без уточнения (record.cell_target R09 и R12 без улицы рядом).
  var GENERIC_APPROX = { "Примерное место": true, "Шамамен орны": true };
  var KIND_FALLBACK = {
    ru: { object: "объект", segment: "участок улицы", area: "двор" },
    kk: { object: "нысан", segment: "көше бөлігі", area: "аула" }
  };

  // ------------------------------------------------------------------ язык и тексты
  var warned = {};

  function storageGet(store, key) {
    try { return window[store].getItem(key); } catch (e) { return null; }
  }
  function storageSet(store, key, value) {
    try { if (value === null) window[store].removeItem(key); else window[store].setItem(key, value); } catch (e) { /* блокировано */ }
  }

  function currentLang() {
    var i18n = window.BirgeI18n;
    var value = i18n && (typeof i18n.lang === "function" ? i18n.lang() : (i18n.getLang ? i18n.getLang() : null));
    value = value || storageGet("localStorage", LANG_KEY) || document.documentElement.lang || "ru";
    return value === "kk" ? "kk" : "ru";
  }

  // Форма числа: ru one/few/many; kk — одна строка.
  function pluralForm(n, lang) {
    if (lang !== "ru") return "many";
    var mod10 = n % 10, mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return "one";
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "few";
    return "many";
  }

  function formatNumber(n) {
    // «1 666» с неразрывным пробелом (UX_BRIEF «Тексты»); общий формат — BirgeI18n.formatNumber R11.
    var i18n = window.BirgeI18n;
    if (i18n && typeof i18n.formatNumber === "function") return i18n.formatNumber(Math.round(n));
    return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  }

  function fill(template, params) {
    return String(template).replace(/\{(\w+)\}/g, function (all, name) {
      if (!params || params[name] === undefined || params[name] === null) return all;
      return typeof params[name] === "number" ? formatNumber(params[name]) : String(params[name]);
    });
  }

  function t(key, params) {
    var lang = currentLang();
    var i18n = window.BirgeI18n;
    if (i18n && typeof i18n.t === "function" && (!i18n.has || i18n.has(key))) {
      var value = i18n.t(key, params);
      if (value && value !== key) return value;
    }
    var strings = window.BirgeComplaintStrings || {};
    var entry = (strings[lang] || {})[key];
    if (entry === undefined) entry = (strings.ru || {})[key];
    if (entry === undefined) {
      if (!warned[key]) { warned[key] = true; console.warn("[i18n] нет ключа " + key); }
      return "";
    }
    if (typeof entry === "object") {
      var n = params && typeof params.n === "number" ? params.n : 0;
      entry = entry[pluralForm(n, lang)] || entry.many;
    }
    return fill(entry, params);
  }

  function formatDate(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    // Один формат дат во всём продукте — BirgeI18n.formatDate R11 («11 окт», «11 қазан»; год — если не текущий).
    var i18n = window.BirgeI18n;
    if (i18n && typeof i18n.formatDate === "function") {
      var shared = i18n.formatDate(iso);
      if (shared && shared !== "—") return shared;
    }
    // Запасной путь: по Астане (UTC+5), а не по часовому поясу браузера.
    var local = new Date(d.getTime() + 5 * 3600 * 1000);
    var now = new Date(Date.now() + 5 * 3600 * 1000);
    var year = local.getUTCFullYear() !== now.getUTCFullYear() ? NBSP + local.getUTCFullYear() : "";
    return local.getUTCDate() + NBSP + MONTHS[currentLang()][local.getUTCMonth()] + year;
  }

  function daysAgo(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return null;
    return Math.max(0, Math.floor((Date.now() - d.getTime()) / 86400000));
  }

  // Уровень значка по числу сообщивших — пороги heat_levels из categories_v2.json (цвет + число).
  function heatLevel(count) {
    var levels = ((window.BirgeCategoriesV2 || {}).heat_levels) || [];
    var level = 0;
    levels.forEach(function (l) { if (count >= l.min_weight) level = l.level; });
    return level;
  }

  // Сколько человек сообщили: автор + «Я тоже». Не полагаемся на одно поле ответа (LOCAL_FINAL №1: ответ для
  // сотрудника не содержал reporters, и шаг «Я тоже» пропускался).
  function reportersOf(c) {
    if (!c) return 0;
    if (typeof c.reporters === "number" && c.reporters > 0) return c.reporters;
    return 1 + (Number(c.metoo) || 0);
  }

  function categories() {
    return ((window.BirgeCategoriesV2 || {}).categories) || [];
  }
  function category(id) {
    var list = categories();
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  }
  function categoryLabel(id) {
    var fromI18n = window.BirgeI18n ? t("cat." + id) : "";
    if (fromI18n) return fromI18n;
    var c = category(id);
    return c ? (c[currentLang()] || c.ru) : "";
  }

  // ------------------------------------------------------------------ уточнения и сезон (волна 1, п. 2 и 11)
  function subtopicsOf(catId) {
    var c = category(catId);
    return (c && c.subtopics) || [];
  }
  function hasKey(key) {
    var strings = window.BirgeComplaintStrings || {};
    return !!((window.BirgeI18n && typeof window.BirgeI18n.has === "function" && window.BirgeI18n.has(key)) ||
              (strings.ru && strings.ru[key] !== undefined));
  }
  function subtopicLabel(catId, subId) {
    var key = "subtopic." + subId;
    if (hasKey(key)) return t(key);           // словарь R11 (kk вычитан), запасной — из /categories
    var list = subtopicsOf(catId);
    for (var i = 0; i < list.length; i++) if (list[i].id === subId) return list[i][currentLang()] || list[i].ru;
    return "";
  }

  // С ноября по март «Снег и гололёд» первым в сетке, с апреля по октябрь — «Дороги». Если есть ui-kit R11 —
  // его BirgeUI.seasonOrder (один порядок для мастера, фильтра карты и «Картины дня», UX_SPEC §10).
  function seasonalCategories(nowMs) {
    var at = typeof nowMs === "number" ? nowMs : Date.now();
    if (window.BirgeUI && typeof window.BirgeUI.seasonOrder === "function") return window.BirgeUI.seasonOrder(categories(), new Date(at));
    var month = new Date(at + 5 * 3600 * 1000).getUTCMonth() + 1;   // месяц по Астане (UTC+5)
    var first = (month >= 11 || month <= 3) ? "snow_ice" : "roads";
    var list = categories();
    return list.filter(function (c) { return c.id === first; }).concat(list.filter(function (c) { return c.id !== first; }));
  }

  // ------------------------------------------------------------------ срочные случаи (волна 1, п. 3)
  // Та же логика, что lifecycle.emergency на сервере (pytest сверяет оба на одном наборе фраз).
  // В JS \b не работает с кириллицей — границы слова задаём набором букв.
  var WL = "A-Za-z0-9_А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі";
  var B = "(?:^|[^" + WL + "])", E = "(?=$|[^" + WL + "])";
  var RX_GAS = new RegExp(B + "газ(?:а|ом|у)?" + E + "|" + B + "газ\\S* утечк|" + B + "утечк\\S* газ|" + B + "газ иіс|" + B + "газдың иіс", "i");
  var RX_FIRE = new RegExp(B + "пожар|" + B + "задымлен|" + B + "дым" + E + "|" + B + "дымит|" + B + "өрт|" + B + "түтін|" + B + "жанып жатыр", "i");
  var RX_BURNS = new RegExp("(^|[^" + WL + "])(гор(?:ит|ят))" + E + "|" + B + "загорел", "i");
  var RX_LIGHT = new RegExp("фонар|свет|ламп|освещ|" + B + "шам" + E + "|шамдар|жарық", "i");
  var RX_WIRE = /оборван\S* провод|провод\S* оборван|обрыв\S* провод|провод\S* (?:лежит|висит|упал)|сым үзіл|үзілген сым|сым жерде/i;

  function emergency(catId, subId, text) {
    var list = subtopicsOf(catId);
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === subId && list[i].emergency_phone) return { phone: list[i].emergency_phone, reason: "subtopic" };
    }
    var value = String(text || "").replace(/ё/g, "е").replace(/Ё/g, "Е");
    if (RX_GAS.test(value)) return { phone: "104", reason: "text" };
    if (RX_WIRE.test(value) || RX_FIRE.test(value)) return { phone: "112", reason: "text" };
    var burns = RX_BURNS.exec(value);
    // «не горят фонари», «фонарь горит днём» — жалобы на свет, не пожар.
    if (burns && !/не\s*$/i.test(value.slice(0, burns.index + (burns[1] || "").length)) && !RX_LIGHT.test(value)) {
      return { phone: "112", reason: "text" };
    }
    return null;
  }

  // ------------------------------------------------------------------ фото (волна 1, п. 5)
  var PHOTO_MAX = 3, PHOTO_SIDE = 1600, PHOTO_QUALITY = 0.82;
  // Уменьшаем до 1600 px и перекодируем в JPEG через canvas: метаданные (EXIF, GPS) при этом не переносятся.
  // Сервер всё равно чистит ещё раз (photos.py) — интерфейсу не доверяет.
  function shrinkPhoto(file) {
    return new Promise(function (resolve, reject) {
      if (!file || !/^image\//.test(file.type || "")) { reject(new Error("not an image")); return; }
      var draw = function (source, width, height) {
        var scale = Math.min(1, PHOTO_SIDE / Math.max(width, height));
        var canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(width * scale));
        canvas.height = Math.max(1, Math.round(height * scale));
        canvas.getContext("2d").drawImage(source, 0, 0, canvas.width, canvas.height);
        canvas.toBlob(function (blob) {
          if (!blob) { reject(new Error("encode failed")); return; }
          resolve({ blob: blob, url: URL.createObjectURL(blob) });
        }, "image/jpeg", PHOTO_QUALITY);
      };
      if (window.createImageBitmap) {
        createImageBitmap(file, { imageOrientation: "from-image" }).then(function (bmp) {
          draw(bmp, bmp.width, bmp.height);
        }, function () { reject(new Error("decode failed")); });
        return;
      }
      var img = new Image();
      var url = URL.createObjectURL(file);
      img.onload = function () { URL.revokeObjectURL(url); draw(img, img.naturalWidth, img.naturalHeight); };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error("decode failed")); };
      img.src = url;
    });
  }

  function bytesToBase64(bytes) {
    var out = "", step = 0x8000;
    for (var i = 0; i < bytes.length; i += step) out += String.fromCharCode.apply(null, bytes.subarray(i, i + step));
    return btoa(out);
  }

  function blobBytes(blob) {
    if (blob.arrayBuffer) return blob.arrayBuffer().then(function (b) { return new Uint8Array(b); });
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () { resolve(new Uint8Array(reader.result)); };
      reader.onerror = reject;
      reader.readAsArrayBuffer(blob);
    });
  }

  // Загрузка частями: шлюз R01 пропускает в /api/civic/v2 не больше 64 КБ тела, фото — сотни КБ.
  function uploadPhoto(complaintId, blob, kind, csrf) {
    var base = "/complaints/" + encodeURIComponent(complaintId) + "/photos";
    var extra = csrf ? { "X-CSRF-Token": csrf } : undefined;   // фото «после» грузит сотрудник (сессия R02)
    return blobBytes(blob).then(function (bytes) {
      return request("POST", base, { kind: kind || "resident", size: bytes.length }, undefined, extra).then(function (res) {
        if (!res.ok) throw new Error("start");
        var chunk = res.data.chunk_bytes || 36000, upload = res.data.upload_id;
        var offset = 0;
        function next() {
          if (offset >= bytes.length) return Promise.resolve(null);
          var part = bytes.subarray(offset, offset + chunk);
          return request("POST", base + "/" + encodeURIComponent(upload), { offset: offset, data: bytesToBase64(part) }, undefined, extra)
            .then(function (r) {
              if (!r.ok) throw new Error("chunk");
              offset += part.length;
              return r.data && r.data.done ? r.data.photo : next();
            });
        }
        return next();
      });
    });
  }

  function dataUrlToBlob(dataUrl) {
    var parts = String(dataUrl).split(","), mime = (parts[0].match(/data:([^;]+)/) || [])[1] || "image/jpeg";
    var bin = atob(parts[1] || ""), bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: mime });
  }

  // Тип места дважды (R10 B-071): имя из OSM уже со словом типа, а шаблон добавил его ещё раз —
  // kk «Ғашықтар саябағы» саябағы → «Ғашықтар саябағы», ru Парк «Парк Победы» → «Парк Победы». Подпись делают R12/R07;
  // здесь — только показ (запись не меняется).
  function dedupeKind(label) {
    return String(label)
      .replace(/^«([^«»]*\s(\S+))» \2$/i, "«$1»")
      .replace(/^(\S+) «(\1\s[^«»]+)»$/i, "«$2»");
  }

  function targetLabel(target) {
    if (!target) return "";
    var lang = currentLang();
    var label = target["label_" + lang] || target.label_ru || target.label_kk;
    if (label) label = dedupeKind(label);
    // «Примерное место»: подробную подпись R12 («Примерное место — проспект Кабанбай Батыра») показываем как есть;
    // общую подпись (своя ячейка R09 или её нет) — из словаря, чтобы перевод был единым с R11.
    if (target.approximate && (!label || GENERIC_APPROX[label])) return t("complaint.step2.approximate");
    return label || KIND_FALLBACK[lang][target.kind] || "";
  }

  // ------------------------------------------------------------------ устройство и сеть
  var memoryDevice = null;
  function randomId(len) {
    var abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    var out = "", bytes = new Uint8Array(len);
    (window.crypto || window.msCrypto).getRandomValues(bytes);
    for (var i = 0; i < len; i++) out += abc[bytes[i] % abc.length];
    return out;
  }
  function deviceId() {
    // Случайный id устройства: «Я тоже» — одно на устройство, «Мои обращения» — по нему.
    // Хранится только в браузере; на сервере — солёный хэш.
    var id = storageGet("localStorage", DEVICE_KEY);
    if (!id || !/^[A-Za-z0-9_-]{16,80}$/.test(id)) {
      id = memoryDevice || ("d-" + randomId(24));
      storageSet("localStorage", DEVICE_KEY, id);
      memoryDevice = id;
    }
    return id;
  }

  // «Мои обращения» с прошлого открытия (в этой вкладке браузера): при новом открытии список виден сразу и тихо
  // обновляется (правило 4 эталона — без мигающей перезагрузки). Любое своё действие с обращениями — заново с сервера.
  var mineCache = null;

  function request(method, path, body, timeoutMs, extraHeaders) {
    if (method !== "GET" && /^\/complaints/.test(path)) mineCache = null;
    var controller = window.AbortController ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, timeoutMs || NET_TIMEOUT_MS) : null;
    var headers = Object.assign({ "Accept": "application/json", "X-Birge-Device": deviceId() }, extraHeaders || {});
    if (body !== undefined) headers["Content-Type"] = "application/json";
    return fetch(API + path, {
      method: method, headers: headers, credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller ? controller.signal : undefined
    }).then(function (res) {
      return res.json().catch(function () { return null; }).then(function (json) {
        var ok = res.ok && json && json.ok !== false;
        return { ok: ok, status: res.status, data: ok ? (json.data !== undefined ? json.data : json) : null,
                 error: ok ? null : ((json && json.error) || { code: "http_" + res.status }) };
      });
    }).catch(function () {
      return { ok: false, status: 0, data: null, error: { code: "network" } };
    }).then(function (result) {
      if (timer) clearTimeout(timer);
      return result;
    });
  }

  // ------------------------------------------------------------------ DOM
  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined || value === false) return;
      if (key === "class") el.className = value;
      else if (key === "text") el.textContent = value;
      else if (key.slice(0, 2) === "on") el.addEventListener(key.slice(2), value);
      else el.setAttribute(key, value === true ? "" : value);
    });
    (Array.isArray(children) ? children : (children === undefined ? [] : [children])).forEach(function (child) {
      if (child === null || child === undefined || child === false) return;
      el.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return el;
  }

  function icon(name) {
    // Иконки ui-kit R11. Если файла нет — пустой значок, подпись рядом всё равно есть (правило 3).
    var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "ic");
    svg.setAttribute("aria-hidden", "true");
    var use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "/civic/ui-kit/icons.svg#i-" + name);
    svg.appendChild(use);
    return svg;
  }

  // Пустое состояние / ошибка (поправка владельца П1, 15 окт: «без ИИ-слопа»): одна маленькая монохромная иконка набора
  // R11 (48 px, та же толщина линий) + короткий текст + одна кнопка. Больших рисованных иллюстраций (ill-*) больше нет.
  // name — прежний вид иллюстрации (offline | list | done | staff …), fallback — иконка набора R11 для него.
  var STATE_ICON = { offline: "wifi-off", list: "list", done: "check", staff: "user", search: "search", map: "pin",
                     idea: "bulb", question: "message" };
  function illustration(name, fallback) {
    var svg = icon(STATE_ICON[name] || fallback || "list");
    svg.setAttribute("class", "ic ic--48 bc-state-ic");
    return svg;
  }

  // Статус значком, как в Linear (правило качества 3 эталона): пустой кружок — новое, наполовину заполненный — в работе,
  // кружок с галочкой — служба сообщила об устранении, заполненный зелёный с галочкой — проверено жителями.
  // Иконка всегда рядом со словом. Рисует R11 в ui-kit; пока его значков нет — эти (те же 4 состояния, 16 px, линия 1,5).
  function statusIcon(status) {
    // ui-kit R11 (эталон, 13 окт): BirgeUI.statusIcon → разметка спрайта; собираем её без innerHTML (DOMParser).
    if (window.BirgeUI && typeof window.BirgeUI.statusIcon === "function" && window.DOMParser) {
      var doc = new DOMParser().parseFromString(window.BirgeUI.statusIcon(status, 14), "text/html");
      var node = doc && doc.body && doc.body.firstElementChild;
      if (node && node.namespaceURI === "http://www.w3.org/2000/svg") return document.importNode(node, true);
    }
    var kind = { "new": "new", accepted: "progress", in_progress: "progress", reopened: "progress",
                 fixed: "reported", reported_fixed: "reported", verified: "verified" }[status] || "new";
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", "bc-sicon bc-sicon--" + kind);
    svg.setAttribute("viewBox", "0 0 16 16"); svg.setAttribute("aria-hidden", "true"); svg.setAttribute("focusable", "false");
    function el(tag, attrs) {
      var n = document.createElementNS(ns, tag);
      Object.keys(attrs).forEach(function (k) { n.setAttribute(k, attrs[k]); });
      svg.appendChild(n);
    }
    el("circle", { cx: "8", cy: "8", r: "6.25", "class": "bc-sicon__ring" });
    if (kind === "progress") el("path", { d: "M8 3.5a4.5 4.5 0 0 1 0 9Z", "class": "bc-sicon__fill" });
    if (kind === "reported" || kind === "verified") el("path", { d: "m5.4 8.2 1.8 1.8 3.5-3.7", "class": "bc-sicon__tick" });
    return svg;
  }

  function statusBadge(status) {
    return h("span", { "class": "bk-status", "data-status": status }, t("status." + status));
  }

  // Статус для жителя с учётом проверки ремонта (R11 IA_WAVE2 §2.2): «Служба сообщила об устранении»,
  // «Проверено жителями», «Проблема осталась — снова в работе» — свои цвета ui-kit (.bk-status[data-status]).
  function displayStatus(item) {
    var state = (item.resolution || {}).state;
    if (item.status === "fixed" && state === "verified") return "verified";
    if (item.status === "fixed" && state === "reported") return "reported_fixed";
    if (state === "reopened" && (item.status === "accepted" || item.status === "in_progress" || item.status === "new")) return "reopened";
    return item.status;
  }

  // Шкала жителя: принято → в работе → исправлено (как record.resident_steps на сервере).
  function residentSteps(complaint) {
    var status = complaint.status;
    if (status === "rejected") {
      return [{ status: "accepted", state: "done" }, { status: "rejected", state: "current" }];
    }
    var current = { "new": 0, accepted: 0, in_progress: 1, fixed: 2 }[status] || 0;
    return ["accepted", "in_progress", "fixed"].map(function (step, index) {
      var state = index < current || (index === current && status === "fixed") ? "done"
        : (index === current ? "current" : "todo");
      return { status: step, state: state };
    });
  }

  function stepsBar(complaint) {
    // Точки шкалы рисует ui-kit (li::before, пройденные закрашены) — своей «✓» нет (R11 день 2 №9):
    // лишний значок сдвигал подписи вниз.
    var list = h("ol", { "class": "bk-steps" + (complaint.status === "fixed" ? " bk-steps--fixed" : ""),
                         "aria-label": t("status." + complaint.status) });
    var steps = residentSteps(complaint);
    // Служба сообщила, жители ещё не проверили: «Исправлено» — текущий шаг, а не пройденный (волна 2, п. 1).
    if (displayStatus(complaint) === "reported_fixed") steps[steps.length - 1].state = "current";
    steps.forEach(function (step) {
      list.appendChild(h("li", { "class": "bk-steps__item", "data-state": step.state, "data-status": step.status,
                                 "aria-current": step.state === "current" ? "step" : null },
        h("span", { "class": "bk-steps__label" }, t("status." + step.status))));
    });
    return list;
  }

  // ------------------------------------------------------------------ адаптер MapLibre
  function maplibreAdapter(map) {
    var SRC = "bc-target";
    var picking = false, listeners = [];
    var empty = { type: "FeatureCollection", features: [] };
    var current = empty;   // последняя подсветка (для проверок и повторной отрисовки после смены стиля)

    function ensureLayers() {
      if (!map.getSource || map.getSource(SRC)) return;
      map.addSource(SRC, { type: "geojson", data: empty });
      // Выбор цели — цветом бренда (не цветом тепловой карты: он занят уровнем жалоб).
      map.addLayer({ id: "bc-area", type: "fill", source: SRC, filter: ["==", ["geometry-type"], "Polygon"],
                     paint: { "fill-color": "#176b4a", "fill-opacity": 0.22 } });
      // Точная область — сплошной контур, «примерное место» — пунктир (dasharray не принимает выражения по данным).
      map.addLayer({ id: "bc-area-line", type: "line", source: SRC,
                     filter: ["all", ["==", ["geometry-type"], "Polygon"], ["!", ["get", "approximate"]]],
                     paint: { "line-color": "#176b4a", "line-width": 2 } });
      map.addLayer({ id: "bc-area-approx", type: "line", source: SRC,
                     filter: ["all", ["==", ["geometry-type"], "Polygon"], ["get", "approximate"]],
                     paint: { "line-color": "#176b4a", "line-width": 2, "line-dasharray": [2, 2] } });
      map.addLayer({ id: "bc-line-casing", type: "line", source: SRC, filter: ["==", ["geometry-type"], "LineString"],
                     layout: { "line-cap": "round", "line-join": "round" },
                     paint: { "line-color": "#ffffff", "line-width": 12 } });
      map.addLayer({ id: "bc-line", type: "line", source: SRC, filter: ["==", ["geometry-type"], "LineString"],
                     layout: { "line-cap": "round", "line-join": "round" },
                     paint: { "line-color": "#176b4a", "line-width": 7 } });
      // Цель (остановка, объект) — крупный круг 11 px с белой обводкой, точка нажатия — маленькая 6 px поверх.
      // coalesce: без свойства pick выражение ["get","pick"] даёт null и предупреждение MapLibre.
      map.addLayer({ id: "bc-point", type: "circle", source: SRC, filter: ["==", ["geometry-type"], "Point"],
                     paint: { "circle-radius": ["case", ["coalesce", ["get", "pick"], false], 6, 11], "circle-color": "#176b4a",
                              "circle-stroke-color": "#ffffff", "circle-stroke-width": 3 } });
    }

    function onClick(e) {
      if (!picking) return;
      listeners.forEach(function (cb) { cb({ lon: e.lngLat.lng, lat: e.lngLat.lat }); });
    }
    map.on("click", onClick);

    // R10 B-019 / R11 B1 №3: значок тепловой карты R07 — маркер MapLibre (элемент поверх холста) — гасит нажатие,
    // и житель, нажав прямо на «горящую» остановку, не получал «Это здесь?». Пока идёт выбор места, нажатие по
    // любому маркеру — это нажатие по карте в точке значка (центр элемента: у R07 anchor "center").
    // Значок района (data-kind="district") лишь приближает карту: район — не место жалобы.
    // Ловим на фазе захвата у контейнера карты, поэтому обработчик самого значка в этот момент не срабатывает.
    var container = map.getContainer ? map.getContainer() : null;
    function onMarkerClick(e) {
      if (!picking || !container) return;
      var marker = e.target && e.target.closest ? e.target.closest(".maplibregl-marker") : null;
      if (!marker || !container.contains(marker)) return;
      e.preventDefault();
      e.stopPropagation();
      var box = marker.getBoundingClientRect(), canvas = map.getCanvas().getBoundingClientRect();
      var at = map.unproject([box.left + box.width / 2 - canvas.left, box.top + box.height / 2 - canvas.top]);
      var kind = marker.getAttribute("data-kind") || (marker.querySelector("[data-kind]") || { getAttribute: function () { return null; } })
        .getAttribute("data-kind");
      if (kind === "district") {
        map.easeTo({ center: [at.lng, at.lat], zoom: Math.max(map.getZoom() + 2, 15), duration: 500 });
        return;
      }
      listeners.forEach(function (cb) { cb({ lon: at.lng, lat: at.lat }); });
    }
    if (container) container.addEventListener("click", onMarkerClick, true);

    // isStyleLoaded() = false и пока грузится любой источник (например, слой улиц хоста), а «load»
    // уже не повторится. Поэтому пробуем сразу и только при ошибке ждём, пока карта станет «idle».
    function whenReady(fn) {
      try { fn(); } catch (e) { map.once("idle", function () { try { fn(); } catch (err) { console.error(err); } }); }
    }

    return {
      onPick: function (cb) {
        listeners.push(cb);
        return function () { listeners = listeners.filter(function (x) { return x !== cb; }); };
      },
      setPickMode: function (on) {
        picking = !!on;
        map.getCanvas().style.cursor = on ? "crosshair" : "";
        // Признак для оболочки и соседей (R01, R07): идёт выбор места жалобы.
        document.documentElement.classList.toggle("bc-picking", picking);
      },
      // Телефон, шаги 4–5: место — посередине видимой карты над шторкой (как Apple Maps). Сдвиг через offset —
      // отступы карты (padding) оболочки R01 не трогаем; масштаб не меняем.
      // Место — в середину видимой части карты (area: { top, bottom, left, right } в координатах окна); onlyIfHidden —
      // не двигать, если место и так видно (ноутбук: карта не «плывёт» без нужды, эталон — «никаких рывков карты»).
      reveal: function (point, area) {
        if (!point || !map.easeTo || !area) return;
        var box = map.getContainer().getBoundingClientRect();
        if (area.onlyIfHidden && map.project) {
          var q = map.project(point), x = box.left + q.x, y = box.top + q.y;
          if (x > area.left + 32 && x < area.right - 32 && y > area.top + 32 && y < area.bottom - 32) return;
        }
        var dx = (area.left + area.right) / 2 - (box.left + box.right) / 2;
        var dy = (area.top + area.bottom) / 2 - (box.top + box.bottom) / 2;
        var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        try { map.easeTo({ center: point, offset: [dx, dy], duration: still ? 0 : 300 }); } catch (e) { /* карта ещё грузится */ }
      },
      highlight: function (target, geometry, point) {
        var features = [];
        if (geometry) features.push({ type: "Feature", geometry: geometry,
                                      properties: { approximate: !!(target && target.approximate), pick: false } });
        if (point) features.push({ type: "Feature", geometry: { type: "Point", coordinates: point },
                                   properties: { pick: true } });
        current = { type: "FeatureCollection", features: features };
        var data = current;
        whenReady(function () {
          ensureLayers();
          if (data === current) map.getSource(SRC).setData(data);
        });
      },
      clear: function () {
        current = empty;
        whenReady(function () { if (map.getSource(SRC)) map.getSource(SRC).setData(empty); });
      },
      flyTo: function (point, offset) {
        // offset не сохраняется в камере карты (в отличие от padding) — чужой модуль карты не задеваем.
        map.easeTo({ center: point, zoom: Math.max(map.getZoom(), 16), duration: 600, offset: offset || [0, 0] });
      },
      current: function () { return current; },
      destroy: function () {
        map.off("click", onClick);
        if (container) container.removeEventListener("click", onMarkerClick, true);
        document.documentElement.classList.remove("bc-picking");
        listeners = [];
      }
    };
  }

  // ------------------------------------------------------------------ мастер
  // ---------------------------------------------------------------- телефон: шторка «Рядом с вами» (эталон A)
  // Решение R11 (INTEGRATION §21.2, кадр эталона «Житель, телефон»): на главной телефона — шторка «Рядом с вами»:
  // ручка, заголовок 19/600 + «ҚАЗ · РУС», 3 ближайших к центру карты горячих места строками .bk-hot (плашка числа
  // цвета уровня; исправленное службой — значок «галочка» R11 и «… · проверьте»), «Все горячие места». Разметка — R09, данные — те же,
  // что у карты жалоб R07 (GET /heat, без текстов жалоб), разметка ui-kit R11 (.bk-phsheet, .bk-hot, .bk-more).
  //   mountNear(root, { map, onOpen(target, anchor), onAll(), limit }) -> { refresh(), setLang(), destroy() }
  function mountNear(root, opts) {
    opts = opts || {};
    var limit = opts.limit || 3;
    var alive = true, items = null, failed = false, slow = false, moveTimer = null;
    var sheet = h("section", { "class": "bk-phsheet bk-glass bk-glass--strong bk-glass--sheet bc-near", "aria-labelledby": "bc-near-title" });
    root.appendChild(sheet);

    function center() {
      try { var c = opts.map && opts.map.getCenter && opts.map.getCenter(); return c ? [c.lng, c.lat] : null; } catch (e) { return null; }
    }
    function far(a, c) { var dx = (a[0] - c[0]) * Math.cos(c[1] * Math.PI / 180), dy = a[1] - c[1]; return dx * dx + dy * dy; }
    function nearest() {
      var list = (items || []).filter(function (it) {
        return it.target && it.target.kind !== "district" && it.count > 0 && it.anchor &&
               (it.state === "active" || (it.state === "fixed" && it.fixed_kind === "reported"));
      });
      var c = center();
      if (c) list.sort(function (a, b) { return far(a.anchor, c) - far(b.anchor, c); });
      return list.slice(0, limit);
    }
    function topic(it) {
      var st = it.top_subtopic;
      if (st) return currentLang() === "kk" ? (st.kk || st.ru) : (st.ru || st.kk);
      var cats = Object.keys(it.by_category || {});
      return cats.length ? categoryLabel(cats[0]) : "";
    }
    function lower(text) { return text ? text.charAt(0).toLocaleLowerCase() + text.slice(1) : text; }
    function subline(it) {
      if (it.state === "fixed") return topic(it) + " · " + t("home.near.check");
      var word = it.status && it.status !== "new" && hasKey("status." + it.status) ? lower(t("status." + it.status)) : "";
      return word ? topic(it) + " · " + word : topic(it);
    }
    function row(it) {
      var fixed = it.state === "fixed";
      var name = targetLabel(it.target);
      return h("li", { "class": "bc-near__item" }, h("button", {
        "class": "bk-hot bc-near__row", type: "button", "data-key": it.target.kind + ":" + it.target.id,
        "aria-label": name + ", " + (fixed ? t("status.reported_fixed") : t("inbox.people", { n: it.count })) + ", " + subline(it),
        onclick: function () { if (opts.onOpen) opts.onOpen(it.target, it.anchor); } }, [
        h("span", { "class": "bk-hot__cnt", "data-level": fixed ? "fixed" : String(it.level || 1), "aria-hidden": "true" },
          fixed ? icon("check") : formatNumber(it.count)),   // П1: значок набора R11, а не глиф «✓»
        h("span", { "class": "bk-hot__name" }, [name, h("small", {}, subline(it))])]));
    }
    function render() {
      if (!alive) return;
      sheet.innerHTML = "";
      sheet.appendChild(h("div", { "class": "bk-handle", "aria-hidden": "true" }));
      var lang = h("div", { "class": "bc-near__lang" });
      var head = h("header", { "class": "bk-phsheet__hd" }, [h("h2", { "class": "bk-phsheet__title", id: "bc-near-title" }, t("home.near.title")), lang]);
      sheet.appendChild(head);
      if (window.BirgeUI && typeof window.BirgeUI.langSwitch === "function") window.BirgeUI.langSwitch(lang, { text: true });
      else head.removeChild(lang);
      if (failed) {
        sheet.appendChild(h("div", { "class": "bc-near__state", role: "alert" }, [h("span", {}, t("mine.error.title")),
          h("button", { "class": "bk-more", type: "button", onclick: function () { load(); } }, t("complaint.error.retry"))]));
        return;
      }
      if (items === null) {
        // Скелетон — только если ответ дольше 150 мс (правило 4 эталона).
        if (slow) sheet.appendChild(h("ul", { "class": "bc-near__list", "aria-hidden": "true" }, [1, 2, 3].map(function () {
          return h("li", { "class": "bk-hot bc-near__skel" }, [h("span", { "class": "bk-skel bc-near__skel-cnt" }), h("span", { "class": "bk-skel bc-near__skel-line" })]);
        })));
        return;
      }
      var list = nearest();
      if (!list.length) sheet.appendChild(h("p", { "class": "bc-near__state" }, t("home.near.empty")));
      else sheet.appendChild(h("ul", { "class": "bc-near__list" }, list.map(row)));
      if (opts.onAll) sheet.appendChild(h("button", { "class": "bk-more bc-near__all", type: "button", onclick: function () { opts.onAll(); } },
        t("home.near.all_hot")));
    }
    function load() {
      failed = false; slow = false;
      if (items === null) setTimeout(function () { if (alive && items === null && !failed) { slow = true; render(); } }, 150);
      render();
      return request("GET", "/heat?days=30&zoom=15").then(function (res) {
        if (!alive) return;
        if (!res.ok) { if (items === null) failed = true; render(); return; }
        items = (res.data && res.data.items) || [];
        render();
      });
    }
    // Карту подвинули — ближайшие пересчитываются на месте, без запроса (данные те же).
    function onMove() { clearTimeout(moveTimer); moveTimer = setTimeout(render, 200); }
    function onLang() { render(); }
    if (opts.map && opts.map.on) opts.map.on("moveend", onMove);
    window.addEventListener("birge:lang", onLang);
    load();
    return {
      refresh: load,
      setLang: function () { render(); },
      destroy: function () {
        alive = false; clearTimeout(moveTimer);
        if (opts.map && opts.map.off) opts.map.off("moveend", onMove);
        window.removeEventListener("birge:lang", onLang);
        if (sheet.parentNode) sheet.parentNode.removeChild(sheet);
      }
    };
  }

  function mount(opts) {
    opts = opts || {};
    var root = opts.root || document.body;
    var map = opts.map || { onPick: function () { return function () {}; } };
    var mql = window.matchMedia ? window.matchMedia(MOBILE_QUERY) : null;
    var state = null;
    var els = {};
    var classifyTimer = null, classifySeq = 0;
    var unpick = null;

    // Главная кнопка «Сообщить о проблеме» (одна на экран).
    // Эталон A (.fab): компонент .bk-fab ui-kit R11 — почти чёрная кнопка 54 px с «+» в лаймовой плитке.
    els.fab = h("button", { "class": "bk-fab bc-fab", type: "button", onclick: function () { open(); } },
      [h("i", { "class": "bk-fab__ic bc-fab__mark", "aria-hidden": "true" }, icon("plus")), h("span", { "class": "bc-fab__label" })]);
    if (opts.fab !== false) root.appendChild(els.fab);

    els.panel = h("section", { "class": "bc-panel", role: "dialog", "aria-modal": "false", hidden: true,
                               "aria-labelledby": "bc-title", "data-snap": "full" });
    els.toast = h("div", { "class": "bk-toast bc-toast", hidden: true });
    root.appendChild(els.panel);
    root.appendChild(els.toast);
    // Escape закрывает открытую панель, где бы ни был фокус (R01 INTEGRATION §8: фокус мог остаться на карте).
    function onKey(e) {
      if (e.key === "Escape" && !els.panel.hidden && !e.defaultPrevented) { e.preventDefault(); close(); }
    }
    document.addEventListener("keydown", onKey);

    function loadDraft() {
      var draft = null;
      try { draft = JSON.parse(storageGet("localStorage", DRAFT_KEY) || "null"); } catch (e) { draft = null; }
      if (!draft || typeof draft !== "object") return null;
      if (!draft.saved_at || Date.now() - draft.saved_at > DRAFT_DAYS * 86400000) { storageSet("localStorage", DRAFT_KEY, null); return null; }
      return draft;
    }

    function freshState() {
      var draft = loadDraft();
      var cat = draft && category(draft.category) ? draft.category : null;
      return {
        view: "wizard", step: 2,
        point: null, candidates: null, candidatesLoading: false, target: null, geometry: null,
        text: (draft && typeof draft.text === "string") ? draft.text : "",
        category: cat, categorySource: cat ? "resident" : null, model: null, suggestion: null, gridOpen: false,
        subtopic: cat && draft.subtopic ? draft.subtopic : null,
        photos: [], photoBusy: false, emergencyShown: false,
        similar: null, similarChecked: false, reviewing: false,
        sending: false, uploading: null, requestId: (draft && draft.requestId) || ("r-" + randomId(20)),
        result: null, mine: null, mineError: false, locating: false
      };
    }

    // Черновик (текст, категория, уточнение, номер запроса) — на устройстве, 7 дней: случайно закрыли — не потеряли.
    function saveDraft() {
      storageSet("localStorage", DRAFT_KEY, state && state.text ? JSON.stringify({
        text: state.text, requestId: state.requestId, category: state.category, subtopic: state.subtopic,
        saved_at: Date.now() }) : null);
    }

    // Тост по разметке ui-kit R11 (.bk-toast: текст | ✕, «Повторить» под текстом; ширина до 480 px):
    // ошибка с «Повторить» висит, пока житель не нажмёт «Повторить» или ✕ (R11 день 2 №8).
    function toast(message, retry) {
      els.toast.innerHTML = "";
      els.toast.className = "bk-toast bc-toast" + (retry ? " bk-toast--error" : "");
      els.toast.setAttribute("role", retry ? "alert" : "status");
      if (retry) els.toast.appendChild(icon("wifi-off"));
      els.toast.appendChild(h("span", { "class": "bk-toast__text", text: message }));
      if (retry) {
        els.toast.appendChild(h("button", { "class": "bk-btn bk-btn--ghost", type: "button",
          onclick: function () { els.toast.hidden = true; retry(); } }, t("complaint.error.retry")));
      }
      els.toast.appendChild(h("button", { "class": "bk-iconbtn bc-toast__close", type: "button",
        "aria-label": t("complaint.wizard.close"), onclick: function () { els.toast.hidden = true; } }, icon("close")));
      els.toast.hidden = false;
      clearTimeout(els.toastTimer);
      if (!retry) els.toastTimer = setTimeout(function () { els.toast.hidden = true; }, 4000);
    }

    function setPicking(on) {
      if (map.setPickMode) map.setPickMode(on);
      if (on && !unpick) unpick = map.onPick(function (p) { pickPoint([p.lon, p.lat]); });
      if (!on && unpick) { unpick(); unpick = null; }
    }

    // ---------------------------------------------------------------- шаг 2: место
    function pickPoint(point) {
      state.point = [Math.round(point[0] * 1e6) / 1e6, Math.round(point[1] * 1e6) / 1e6];
      state.target = null; state.geometry = null; state.candidates = null; state.candidatesLoading = true;
      if (map.highlight) map.highlight(null, null, state.point);
      render();
      var seq = state.pickSeq = (state.pickSeq || 0) + 1;
      var owner = state;
      request("GET", "/targets?lon=" + state.point[0] + "&lat=" + state.point[1], undefined, TARGETS_TIMEOUT_MS)
        .then(function (res) {
          if (state !== owner || seq !== state.pickSeq) return;
          var list = res.ok && res.data && Array.isArray(res.data.candidates) ? res.data.candidates : [];
          state.candidates = list.filter(function (c) { return c && c.target && c.target.kind && c.target.id; }).slice(0, 3);
          state.candidatesLoading = false;
          if (!state.candidates.length) return chooseApproximate();
          // Только «примерное место» (рядом нет ни объекта, ни улицы) — выбирать нечего: сразу шаг ③.
          if (state.candidates.every(function (c) { return c.approximate || (c.target && c.target.approximate); })) {
            return chooseCandidate(state.candidates[0]);
          }
          render();
        });
    }

    function chooseCandidate(candidate) {
      // R12 ставит признак «примерное место» на кандидате, а не внутри target: переносим, чтобы подпись,
      // пунктир на карте и запись жалобы знали, что место неточное (CONTRACT §8.4).
      state.target = Object.assign({}, candidate.target, candidate.approximate ? { approximate: true } : {});
      state.geometry = candidate.geometry || null;
      if (map.highlight) map.highlight(state.target, state.geometry, state.point);
      state.step = 3;
      render();
    }

    function chooseApproximate() {
      // «Другое место» / нет кандидатов R12: область ~150 м с подписью «примерное место».
      state.candidatesLoading = true;
      render();
      var seq = state.pickSeq, owner = state;
      request("GET", "/complaints/place?lon=" + state.point[0] + "&lat=" + state.point[1]).then(function (res) {
        if (state !== owner || seq !== state.pickSeq) return;
        state.candidatesLoading = false;
        if (!res.ok) {
          if (res.error && res.error.code === "invalid") { toast(t("complaint.error.outside")); state.point = null; render(); return; }
          // Сервер недоступен — цель посчитает сервер при отправке; показываем только точку.
          state.target = null; state.geometry = null;
          state.approximateOnly = true;
        } else {
          state.target = res.data.target; state.geometry = res.data.geometry;
        }
        if (map.highlight) map.highlight(state.target || { approximate: true }, state.geometry, state.point);
        state.step = 3;
        render();
      });
    }

    // Сдвиг центра карты, чтобы точка была видна рядом с панелью, а не под ней.
    function visibleOffset() {
      var rect = els.panel.getBoundingClientRect();
      if (els.panel.hidden || !rect.width) return [0, 0];
      return mql && mql.matches ? [0, -rect.height / 2] : [-(rect.width + 12) / 2, 0];
    }

    function locate() {
      if (!navigator.geolocation) { toast(t("complaint.step2.locate_failed")); return; }
      state.locating = true; render();
      var owner = state;
      navigator.geolocation.getCurrentPosition(function (pos) {
        if (state !== owner) return;
        state.locating = false;
        var point = [pos.coords.longitude, pos.coords.latitude];
        if (map.flyTo) map.flyTo(point, visibleOffset());
        pickPoint(point);
      }, function () {
        if (state !== owner) return;
        state.locating = false; render();
        toast(t("complaint.step2.locate_failed"));
      }, { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 });
    }

    function renderPlace(body) {
      var locateButton = h("button", { "class": "bk-btn bk-btn--block", type: "button", disabled: state.locating || null,
                                       onclick: locate },
        [icon("locate"), h("span", {}, state.locating ? t("complaint.step2.locating") : t("complaint.step2.locate"))]);
      if (!state.candidates || state.candidatesLoading) {
        // Точка ещё не выбрана: подсказка и «Моё местоположение» сверху.
        body.appendChild(h("p", { "class": "bc-hint" }, t("complaint.step2.hint")));
        body.appendChild(locateButton);
      }
      if (state.candidatesLoading) {
        body.appendChild(h("div", { "class": "bc-loading", role: "status" },
          [h("span", { "class": "bk-skel bc-skel-line" }), h("span", { "class": "bk-skel bc-skel-line" }),
           h("span", { "class": "bc-loading__text" }, t("complaint.step2.loading"))]));
        return;
      }
      if (!state.candidates) return;
      var first = state.candidates[0];
      // Подписи целей приходят от R12 с заглавной буквы («Остановка «…»»), поэтому вопрос без вставки подписи.
      body.appendChild(h("h3", { "class": "bc-question" }, first ? t("complaint.step2.question") : t("complaint.step2.choose")));
      var list = h("div", { "class": "bc-options", role: "group" });
      var labelCount = {};
      state.candidates.forEach(function (c) { var l = targetLabel(c.target); labelCount[l] = (labelCount[l] || 0) + 1; });
      state.candidates.forEach(function (candidate, index) {
        // «в 0 м» выглядит странно: расстояние показываем от 5 м — но всегда, если подписи совпали
        // (две остановки с одним названием по разные стороны улицы), иначе кнопки не различить.
        var d = candidate.distance_m;
        var same = labelCount[targetLabel(candidate.target)] > 1;
        var meters = typeof d === "number" && (d >= 5 || same) ? Math.max(1, Math.round(d)) : null;
        // Точка внутри двора/площадки (0 м) — «Вы здесь», а не «0 м» и не пусто (R11 B2 №3). У «примерного места»
        // точка всегда внутри своей ячейки — там «Вы здесь» ничего не добавляет и только путает.
        var approx = candidate.approximate || (candidate.target && candidate.target.approximate);
        var here = typeof d === "number" && d < 1 && !approx;
        list.appendChild(h("button", { "class": "bk-btn bk-btn--block bc-option" + (index === 0 ? " bc-option--first" : ""),
                                       type: "button", onclick: function () { chooseCandidate(candidate); } },
          [icon(candidate.approximate ? "pin" : (candidate.target.kind === "segment" ? "road" : (candidate.target.kind === "area" ? "trees" : "pin"))),
           h("span", { "class": "bc-option__label" }, targetLabel(candidate.target)),
           here ? h("span", { "class": "bc-option__meta" }, t("complaint.step2.here"))
             : (meters !== null ? h("span", { "class": "bc-option__meta" }, t("complaint.step2.distance", { n: meters })) : null)]));
      });
      // «Другое место» = примерная область. Если R12 уже предложил её своим вариантом (с улицей в подписи),
      // вторую такую кнопку не показываем.
      var hasApprox = state.candidates.some(function (c) { return c.approximate || (c.target && c.target.approximate); });
      if (!hasApprox) {
        list.appendChild(h("button", { "class": "bk-btn bk-btn--block bk-btn--ghost bc-option", type: "button",
                                       onclick: chooseApproximate },
          [icon("pin"), h("span", { "class": "bc-option__label" }, t("complaint.step2.other_place"))]));
      }
      body.appendChild(list);
      // Варианты уже на экране — им место сверху шторки, остальное ниже (меньше прокрутки на телефоне).
      body.appendChild(h("p", { "class": "bc-meta" }, t("complaint.step2.pick_again")));
      body.appendChild(locateButton);
    }

    // ---------------------------------------------------------------- шаг 3: текст и категория
    function scheduleClassify() {
      clearTimeout(classifyTimer);
      if (state.categorySource === "resident") return;   // житель выбрал сам — модель не спорит
      if (state.text.trim().length < CLASSIFY_MIN_CHARS) return;
      var owner = state;
      classifyTimer = setTimeout(function () {
        // LOCAL_FINAL №2: мастер могли закрыть (state = null) или открыть заново, пока шёл таймер.
        if (state !== owner || !state) return;
        var seq = ++classifySeq;
        request("POST", "/classify", { text: state.text }, ML_TIMEOUT_MS).then(function (res) {
          if (seq !== classifySeq || !state || state !== owner || state.categorySource === "resident") return;
          var data = res.ok ? res.data : null;
          if (!data || !category(data.category)) {
            // Модель недоступна или ответ странный — молча открываем сетку категорий.
            if (!state.category) { state.gridOpen = true; renderCategory(); }
            return;
          }
          state.model = { label: data.category, score: typeof data.score === "number" ? data.score : null,
                          version: data.model_version || null, needs_review: !!data.needs_review };
          state.suggestion = data.category;
          // R04: needs_review — пометка для сотрудника (сейчас всегда true), жителю подсказку показываем по
          // suggest. Если поставщик не знает suggest — старое правило «нет needs_review».
          var suggest = typeof data.suggest === "boolean" ? data.suggest : !data.needs_review;
          if (suggest) {
            if (state.category !== data.category) state.subtopic = null;   // уточнение другой категории не подходит
            state.category = data.category; state.categorySource = "model"; state.gridOpen = false;
          } else if (!state.category) {
            state.gridOpen = true;
          }
          renderCategory();
          renderEmergency();
          updateSendButton();
        });
      }, CLASSIFY_DEBOUNCE_MS);
    }

    function pickCategory(id) {
      // Выбор в сетке — всегда решение жителя («resident»), даже если совпал с подсказкой модели.
      if (state.category !== id) state.subtopic = null;
      state.category = id; state.categorySource = "resident";
      state.gridOpen = false;
      saveDraft();
      renderCategory();
      renderEmergency();
      updateSendButton();
    }

    function pickSubtopic(id) {
      // Повторное нажатие или «Без уточнения» снимает уточнение (оно необязательно).
      state.subtopic = id && state.subtopic !== id ? id : null;
      saveDraft();
      renderCategory();
      renderEmergency();
    }

    // Баннер «Звоните N» до отправки (волна 1, п. 3): по уточнению или словам в тексте. Отправить всё равно можно.
    function renderEmergency() {
      var box = els.emergencyBox;
      if (!box) return;
      box.innerHTML = "";
      var found = emergency(state.category, state.subtopic, state.text);
      if (els.send) els.send.classList.toggle("bk-btn--primary", !found);
      if (!found) return;
      state.emergencyShown = true;
      // UX_SPEC §10: баннер .bk-banner--danger в потоке; ГЛАВНАЯ кнопка экрана — звонок, «Далее/Отправить» —
      // второстепенная (одна главная кнопка). Кто ответит — мелко под номером. Баннер не прячется сам.
      box.appendChild(h("div", { "class": "bk-banner bk-banner--danger bc-emergency", role: "alert" }, [
        h("p", { "class": "bk-banner__title" }, [icon("alert"), h("span", {}, t("complaint.emergency.title"))]),
        h("p", { "class": "bc-emergency__text" }, t("complaint.emergency.text", { phone: found.phone })),
        h("a", { "class": "bk-btn bk-btn--primary bk-btn--block bc-emergency__call", href: "tel:" + found.phone },
          [icon("phone"), h("span", {}, t("complaint.emergency.call", { phone: found.phone }))]),
        h("p", { "class": "bk-banner__note" }, t("emergency.service." + found.phone)),
        h("p", { "class": "bk-banner__note" }, t("complaint.emergency.still_send"))]));
    }

    function emergencyNow() {
      return !!emergency(state.category, state.subtopic, state.text);
    }

    // ---------------------------------------------------------------- фото жителя (волна 1, п. 5)
    function addPhotos(files) {
      var free = PHOTO_MAX - state.photos.length;
      var list = Array.prototype.slice.call(files || [], 0, Math.max(0, free));
      if (!list.length) return;
      var owner = state;
      state.photoBusy = true; renderPhotos();
      list.reduce(function (chain, file) {
        return chain.then(function () {
          return shrinkPhoto(file).then(function (photo) {
            if (state === owner && state.photos.length < PHOTO_MAX) state.photos.push(photo);
          }, function () { toast(t("complaint.photo.bad_type")); });
        });
      }, Promise.resolve()).then(function () {
        if (state !== owner) return;
        state.photoBusy = false; renderPhotos();
      });
    }

    function removePhoto(index) {
      var removed = state.photos.splice(index, 1)[0];
      if (removed && removed.url) URL.revokeObjectURL(removed.url);
      renderPhotos();
    }

    function renderPhotos() {
      var box = els.photoBox;
      if (!box) return;
      box.innerHTML = "";
      var input = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", multiple: true,
                               "class": "bc-photo-input", id: "bc-photo-input", tabindex: "-1", "aria-hidden": "true" });
      input.addEventListener("change", function () { addPhotos(input.files); input.value = ""; });
      var thumbs = h("ul", { "class": "bc-thumbs" });
      state.photos.forEach(function (photo, index) {
        thumbs.appendChild(h("li", { "class": "bc-thumb" }, [
          h("img", { src: photo.url, alt: "" }),
          h("button", { "class": "bk-iconbtn bc-thumb__remove", type: "button", "aria-label": t("complaint.photo.remove"),
                        onclick: function () { removePhoto(index); } }, icon("close"))]));
      });
      box.appendChild(input);
      if (state.photos.length) box.appendChild(thumbs);
      if (state.photos.length < PHOTO_MAX) {
        box.appendChild(h("button", { "class": "bk-btn bc-photo-add", type: "button", disabled: state.photoBusy || null,
                                      onclick: function () { input.click(); } },
          [icon("camera"), h("span", {}, state.photos.length ? t("complaint.photo.count", { n: state.photos.length })
                                                             : t("complaint.photo.add"))]));
      }
      box.appendChild(h("p", { "class": "bc-meta" }, t("complaint.photo.limit") + " · " + t("complaint.photo.private")));
    }

    function renderCategory() {
      var box = els.categoryBox;
      if (!box) return;
      box.innerHTML = "";
      if (state.category && !state.gridOpen) {
        var c = category(state.category);
        box.appendChild(h("div", { "class": "bc-cat-row" }, [
          h("span", { "class": "bc-cat-row__label" },
            state.categorySource === "model" ? t("complaint.step3.suggested") : t("complaint.step3.chosen")),
          h("button", { "class": "bk-chip", type: "button", "aria-pressed": "true",
                        onclick: function () { state.gridOpen = true; renderCategory(); } },
            // Галочку у выбранного чипа рисует ui-kit (.bk-chip[aria-pressed=true]::before) — своей не добавляем.
            [icon(c ? c.icon : "dots"), h("span", {}, categoryLabel(state.category))]),
          h("button", { "class": "bk-btn bk-btn--ghost bc-change", type: "button",
                        onclick: function () { state.gridOpen = true; renderCategory(); } }, [icon("edit"), h("span", {}, t("complaint.step3.change"))])
        ]));
        // Уточнение — одним нажатием, по желанию (волна 1, п. 2). Модель уточнение не предсказывает.
        var subs = subtopicsOf(state.category);
        if (subs.length) {
          box.appendChild(h("p", { "class": "bc-label", id: "bc-sub-title" }, t("complaint.subtopic.title")));
          var chips = h("div", { "class": "bk-chips bk-chips--wrap bc-subtopics", role: "group", "aria-labelledby": "bc-sub-title" });
          subs.forEach(function (sub) {
            chips.appendChild(h("button", { "class": "bk-chip bc-subtopic", type: "button", "data-subtopic": sub.id,
                                            "aria-pressed": state.subtopic === sub.id ? "true" : "false",
                                            onclick: function () { pickSubtopic(sub.id); } },
              h("span", {}, subtopicLabel(state.category, sub.id))));
          });
          // Последний чип — «Без уточнения» (UX_SPEC §10): уточнение необязательно.
          chips.appendChild(h("button", { "class": "bk-chip bc-subtopic", type: "button", "data-subtopic": "",
                                          "aria-pressed": state.subtopic ? "false" : "true",
                                          onclick: function () { pickSubtopic(null); } },
            h("span", {}, t("complaint.subtopic.none"))));
          box.appendChild(chips);
        }
        return;
      }
      if (!state.gridOpen && !state.category) {
        // Пока модель думает или текста мало — кнопка выбора вручную (без «загрузки модели»).
        // Строка-кнопка как в iOS: значок, подпись, «›» — видно, что её нажимают (дизайн-марафон).
        box.appendChild(h("button", { "class": "bk-btn bk-btn--block bc-change bc-change--pick", type: "button",
                                      onclick: function () { state.gridOpen = true; renderCategory(); } },
          [icon("list"), h("span", { "class": "bc-change__label" }, t("complaint.step3.choose")), icon("chevron-right")]));
        return;
      }
      box.appendChild(h("p", { "class": "bc-label", id: "bc-cat-title" }, t("complaint.step3.choose")));
      // Сетка ui-kit R11: иконка слева + подпись, колонки ≥ 150 px (2 на телефоне), казахские слова не рвутся.
      var grid = h("div", { "class": "bk-catgrid", role: "group", "aria-labelledby": "bc-cat-title" });
      // Сезонный порядок (волна 1, п. 11): зимой «Снег и гололёд» первым, летом — «Дороги».
      seasonalCategories(opts.now ? opts.now() : Date.now()).forEach(function (c) {
        grid.appendChild(h("button", { type: "button", "data-category": c.id,
                                       "aria-pressed": state.category === c.id ? "true" : "false",
                                       "data-suggested": c.id === state.suggestion ? "true" : null,
                                       onclick: function () { pickCategory(c.id); } },
          [icon(c.icon), h("span", {}, categoryLabel(c.id))]));
      });
      box.appendChild(grid);
    }

    function updateSendButton() {
      if (!els.send) return;
      var ready = state.text.trim().length >= 3 && !!state.category && !state.sending && !state.checking && !state.photoBusy;
      els.send.disabled = !ready;
      // Срочный случай: главная кнопка — звонок, «Далее/Отправить» второстепенная (UX_SPEC §10, одна главная).
      els.send.classList.toggle("bk-btn--primary", !emergencyNow());
      // Шаг ③ — «Далее» (дальше «Я тоже» или проверка перед отправкой); проверка — «Отправить».
      var label = state.uploading ? t("complaint.photo.uploading", state.uploading)
        : (state.sending ? t("complaint.step3.sending") : (state.reviewing ? t("complaint.step3.send") : t("complaint.wizard.next")));
      els.send.querySelector("span").textContent = label;
    }

    function renderText(body) {
      if (state.target || state.approximateOnly) {
        body.appendChild(h("p", { "class": "bc-place" }, [icon("pin"),
          h("span", {}, t("complaint.step2.selected", { label: targetLabel(state.target || { approximate: true }) }))]));
      }
      var example = t("complaint.example." + (state.category || "roads"));
      // Поле — .bk-field ui-kit (заливка, рамка только у фокуса; R11 CLEAN_PASS R09 №3).
      var field = h("div", { "class": "bk-field bc-field" }, [
        h("label", { "class": "bk-field__label bc-label", "for": "bc-text" }, t("complaint.step3.label"))]);
      body.appendChild(field);
      if (!els.textarea) {
        els.textarea = h("textarea", { id: "bc-text", "class": "bc-textarea", rows: "4", maxlength: "2000" });
        els.textarea.addEventListener("input", function () {
          state.text = els.textarea.value;
          saveDraft();
          updateSendButton();
          renderEmergency();
          scheduleClassify();
        });
      }
      els.textarea.value = state.text;
      els.textarea.setAttribute("placeholder", t("complaint.step3.example", { example: example }));
      field.appendChild(els.textarea);
      body.appendChild(h("p", { "class": "bc-meta" }, t("complaint.step3.privacy")));
      // Срочный случай — сразу под полем, пока житель пишет (а не под категориями, ниже края экрана телефона).
      els.emergencyBox = h("div", { "class": "bc-emergency-box" });
      body.appendChild(els.emergencyBox);
      els.categoryBox = h("div", { "class": "bc-category", "aria-live": "polite" });
      body.appendChild(els.categoryBox);
      renderCategory();
      renderEmergency();
      els.photoBox = h("div", { "class": "bc-photos" });
      body.appendChild(els.photoBox);
      renderPhotos();
      els.send = h("button", { "class": "bk-btn bk-btn--primary bk-btn--block bc-send", type: "button",
                               onclick: checkSimilarThenSend }, [icon("forward"), h("span")]);
      body.appendChild(els.send);
      updateSendButton();
      if (state.text) scheduleClassify();
    }

    // ---------------------------------------------------------------- шаг 4: похожие
    function checkSimilarThenSend() {
      if (state.sending || state.checking) return;
      state.checking = true; updateSendButton();
      var owner = state;
      findSimilar().then(function (match) {
        if (state !== owner) return;
        state.checking = false;
        state.similarChecked = true;
        if (match && placeCount(match) > 0) {
          state.similar = match; state.reviewing = false; state.step = 4; render();
        } else {
          openReview();
        }
      });
    }

    function findSimilar() {
      // 1) R04 /similar по тексту и месту; 2) запасной путь без ML — та же цель и та же категория.
      // Цель шага ② передаём R04: «та же цель» надёжнее точки (участок улицы бывает длиннее 200 м).
      var body = { text: state.text, point: state.point, days: 14 };
      if (state.target && state.target.id) body.target = { kind: state.target.kind, id: state.target.id };
      var byText = request("POST", "/similar", body, ML_TIMEOUT_MS)
        .then(function (res) {
          var matches = res.ok && res.data && Array.isArray(res.data.matches) ? res.data.matches : [];
          // Порог и порядок — забота R04: все matches уже прошли его порог (в режиме «понятий» дубль
          // начинается с 0.18), список упорядочен. Повторно по score не фильтруем — берём первое.
          matches = matches.filter(function (m) { return m && m.complaint_id; });
          if (!matches.length) return null;
          // view=public: мастер жителя всегда получает ответ «как житель», даже если в браузере вошёл сотрудник.
          return request("GET", "/complaints/" + encodeURIComponent(matches[0].complaint_id) + "?view=public").then(function (r) {
            return r.ok && r.data && r.data.complaint ? r.data.complaint : null;
          });
        });
      return byText.then(function (found) {
        if (found && found.status !== "fixed" && found.status !== "rejected") return withPlaceCount(found);
        if (!state.target || !state.target.id) return null;
        return placeSummary(state.target.id, state.category).then(function (sum) {
          return sum && sum.top ? withCount(sum.top, sum.reporters) : null;
        });
      }).catch(function () { return null; });
    }

    // «Об этом уже сообщили N человек» — все люди, сообщившие о том же на этом месте: открытые жалобы той же цели
    // и категории за 14 дней (как число на значке карты). Так N честный, даже если о проблеме подали несколько
    // отдельных жалоб, а не одну с «Я тоже». «Я тоже» присоединяет к самой похожей из них.
    function placeSummary(targetId, category) {
      var q = "/complaints/summary?target_id=" + encodeURIComponent(targetId) +
              "&category=" + encodeURIComponent(category || "") + "&days=14";
      return request("GET", q, undefined, ML_TIMEOUT_MS).then(function (res) {
        return res.ok && res.data ? res.data : null;
      });
    }

    function withCount(match, placeReporters) {
      match.reporters = reportersOf(match);
      match.placeReporters = Math.max(match.reporters, Number(placeReporters) || 0);
      return match;
    }

    function withPlaceCount(match) {
      if (!match.target || !match.target.id || !match.category) return match;
      return placeSummary(match.target.id, match.category)
        .then(function (sum) { return withCount(match, sum && sum.reporters); }, function () { return match; });
    }

    function placeCount(match) {
      return match.placeReporters || reportersOf(match);
    }

    function renderSimilar(body) {
      var match = state.similar;
      var ago = daysAgo(match.created_at);
      body.appendChild(h("div", { "class": "bc-similar" }, [
        h("p", { "class": "bc-similar__count" }, [h("span", { "class": "bk-heat bc-similar__badge", "data-level": String(heatLevel(placeCount(match))) },
          formatNumber(placeCount(match))), h("span", {}, categoryLabel(match.category))]),
        h("p", { "class": "bc-meta" }, [targetLabel(match.target),
          " · ", ago === 0 ? t("complaint.step4.today") : t("complaint.step4.ago_days", { n: ago })]),
        h("div", { "class": "bc-similar__status" }, [statusBadge(match.status),
          // Синтетическая жалоба для показа — с меткой «Пример», как на карте (UX_BRIEF: синтетика помечена).
          match.demo ? h("span", { "class": "bk-tag bk-tag--demo" }, t("common.demo")) : null])
      ]));
      body.appendChild(h("p", { "class": "bc-hint" }, t("complaint.step4.hint")));
      body.appendChild(h("button", { "class": "bk-btn bk-btn--primary bk-btn--block", type: "button",
                                     onclick: function (e) { metoo(match, e.currentTarget); } },
        [icon("users"), h("span", {}, t("complaint.step4.metoo"))]));
      // «Я тоже» = подписка на общий случай (волна 2, п. 3): одно обновление службы видят все.
      body.appendChild(h("p", { "class": "bc-meta bc-metoo-caption" }, t("broadcast.metoo_hint")));
      // R04: текст при «Я тоже» тоже сохраняется — только для службы (обязательная мелочь «кто что увидит»).
      if (state.text && state.text.trim().length >= 3) {
        body.appendChild(h("p", { "class": "bc-meta bc-metoo-private" }, t("complaint.step4.note_private")));
      }
      body.appendChild(h("button", { "class": "bk-btn bk-btn--block bc-different", type: "button", onclick: openReview },
        t("complaint.step4.different")));
    }

    // ---------------------------------------------------------------- проверка перед отправкой (волна 2, мелочи)
    function openReview() {
      state.reviewing = true;
      state.step = 4;
      render();
    }

    function reviewRow(label, value) {
      return h("div", { "class": "bc-review__row" }, [h("dt", {}, label), h("dd", {}, value)]);
    }

    function renderReview(body) {
      var what = categoryLabel(state.category) + (state.subtopic ? " · " + subtopicLabel(state.category, state.subtopic) : "");
      var thumbs = state.photos.length ? h("ul", { "class": "bc-thumbs bc-thumbs--small" }, state.photos.map(function (p) {
        return h("li", { "class": "bc-thumb" }, h("img", { src: p.url, alt: "" }));
      })) : t("complaint.review.no_photos");
      body.appendChild(h("dl", { "class": "bc-review" }, [
        reviewRow(t("complaint.review.place"), targetLabel(state.target || { approximate: true })),
        reviewRow(t("complaint.review.what"), what),
        reviewRow(t("complaint.review.text"), h("span", { "class": "bc-review__text" }, state.text)),
        reviewRow(t("complaint.review.photos"), thumbs)]));
      // Кто что увидит (волна 2, мелочи): публичное — место, категория, число людей; текст и фото — только служба.
      body.appendChild(h("div", { "class": "bc-visibility" }, [
        h("p", {}, [icon("users"), h("span", {}, t("complaint.review.public"))]),
        h("p", {}, [icon("shield"), h("span", {}, t("complaint.review.private"))]),
        h("p", { "class": "bc-meta" }, t("complaint.review.personal"))]));
      els.emergencyBox = h("div", { "class": "bc-emergency-box" });
      body.appendChild(els.emergencyBox);
      renderEmergency();
      els.send = h("button", { "class": "bk-btn bk-btn--primary bk-btn--block bc-send", type: "button", onclick: send },
        [icon("send"), h("span")]);
      body.appendChild(els.send);
      body.appendChild(h("button", { "class": "bk-btn bk-btn--block bc-edit", type: "button",
                                     onclick: function () { state.reviewing = false; state.step = 3; render(); } },
        t("complaint.review.edit")));
      updateSendButton();
    }

    function announce(type, complaint) {
      var detail = { type: type, complaint_id: complaint.id, target: complaint.target, category: complaint.category,
                     reporters: complaint.reporters || (1 + (complaint.metoo || 0)), status: complaint.status,
                     demo: !!complaint.demo };
      try { window.dispatchEvent(new CustomEvent("birge:complaint", { detail: detail })); } catch (e) { /* старый браузер */ }
      if (typeof opts.onEvent === "function") { try { opts.onEvent(detail); } catch (e) { console.error(e); } }
    }

    function metoo(match, button) {
      if (button) button.disabled = true;
      var owner = state;
      // Волна мелочей п. 9 (R04): текст и место жителя уходят вместе с «Я тоже» — их видит только служба; если «Похоже
      // на» ошиблось, сотрудник одним действием выделит это в отдельную жалобу жителя («Это разные проблемы»).
      var note = state.text && state.text.trim().length >= 3
        ? { text: state.text, point: state.point, target: state.target, category: state.category } : undefined;
      request("POST", "/complaints/" + encodeURIComponent(match.id) + "/metoo", note ? { note: note } : {}).then(function (res) {
        if (button) button.disabled = false;
        if (state !== owner) return;
        // Лимит (429, R15): повтор снова упрётся в лимит — сообщаем без «Повторить», как при отправке жалобы.
        if (!res.ok && res.status === 429) { toast(t("complaint.error.too_many")); return; }
        if (!res.ok) { toast(t("complaint.error.send"), function () { metoo(match); }); return; }
        // Сколько людей теперь сообщили об этом на месте: прежнее N + этот житель (если «Я тоже» засчитан).
        var joined = res.data.complaint, place = placeCount(match) + Math.max(0, reportersOf(joined) - reportersOf(match));
        state.result = { kind: "metoo", outcome: res.data.result, complaint: joined, place: place };
        if (res.data.result === "added") announce("metoo", res.data.complaint);
        clearDraft();
        state.step = 5; render();
      });
    }

    // ---------------------------------------------------------------- отправка
    function clearDraft() {
      storageSet("localStorage", DRAFT_KEY, null);
      storageSet("sessionStorage", DRAFT_KEY, null);   // черновик старых версий (раньше — только вкладка)
    }

    function complaintBody() {
      return { text: state.text, category: state.category, category_source: state.categorySource || "resident",
               subtopic: state.subtopic || undefined, emergency_shown: state.emergencyShown || undefined,
               model: state.model, point: state.point, target: state.target, request_id: state.requestId };
    }

    function uploadAll(complaintId, blobs, progress) {
      var failed = 0;
      return blobs.reduce(function (chain, blob, index) {
        return chain.then(function () {
          if (progress) progress(index + 1, blobs.length);
          return uploadPhoto(complaintId, blob, "resident").catch(function () { failed += 1; });
        });
      }, Promise.resolve()).then(function () { return failed; });
    }

    function send() {
      if (state.sending) return;
      state.sending = true;
      if (state.step !== 4 || !state.reviewing) { state.reviewing = true; state.step = 4; render(); }
      updateSendButton();
      var body = complaintBody();
      var owner = state;
      request("POST", "/complaints", body).then(function (res) {
        if (state !== owner) return;   // мастер закрыли во время отправки: жалоба на сервере, экран не трогаем
        if (res.ok && res.data && res.data.complaint) {
          var complaint = res.data.complaint;
          if (!res.data.replayed) announce("created", complaint);
          clearDraft();
          var blobs = res.data.replayed ? [] : state.photos.map(function (p) { return p.blob; });
          return uploadAll(complaint.id, blobs, function (n, total) {
            if (state !== owner) return;
            state.uploading = { n: n, total: total }; updateSendButton();
          }).then(function (failed) {
            if (state !== owner) return;
            state.sending = false; state.uploading = null;
            state.result = { kind: "created", complaint: complaint, photoFailed: failed > 0 };
            state.step = 5; render();
            if (failed) toast(t("complaint.photo.failed"));
          });
        }
        state.sending = false;
        updateSendButton();
        var code = res.error && res.error.code;
        if (res.status === 429) toast(t("complaint.error.too_many"));
        else if (code === "invalid" && res.error.fields && res.error.fields.point) toast(t("complaint.error.outside"));
        else if (res.status === 0) queueAndShow(body);   // нет сети: очередь и автоповтор (волна 1, п. 10)
        else toast(t("complaint.error.send"), send);     // текст остаётся в поле и в черновике
      });
    }

    // ---------------------------------------------------------------- очередь без сети (волна 1, п. 10)
    function readOutbox() {
      try { var list = JSON.parse(storageGet("localStorage", OUTBOX_KEY) || "[]"); return Array.isArray(list) ? list : []; }
      catch (e) { return []; }
    }
    function writeOutbox(list) {
      try { window.localStorage.setItem(OUTBOX_KEY, JSON.stringify(list)); return true; } catch (e) { return false; }
    }

    function queueAndShow(body) {
      var owner = state;
      var photos = state.photos.slice();
      Promise.all(photos.map(function (p) {
        return blobBytes(p.blob).then(function (b) { return "data:image/jpeg;base64," + bytesToBase64(b); });
      })).then(function (urls) {
        var list = readOutbox().filter(function (item) { return item.body.request_id !== body.request_id; });
        var entry = { body: body, photos: urls, queued_at: new Date().toISOString(),
                      label: targetLabel(state.target || { approximate: true }), category: state.category };
        list.push(entry);
        // Фото могут не влезть в память браузера — тогда очередь без фото, жалоба важнее.
        if (!writeOutbox(list)) { entry.photos = []; entry.photos_dropped = true; writeOutbox(list); }
        clearDraft();
        if (state !== owner) return;
        state.sending = false;
        state.result = { kind: "queued", entry: entry };
        state.step = 5; render();
        scheduleFlush(0);
      });
    }

    var flushTimer = null, flushAttempt = 0, flushing = false;
    function scheduleFlush(attempt) {
      clearTimeout(flushTimer);
      if (!readOutbox().length) return;
      flushAttempt = attempt;
      flushTimer = setTimeout(flushOutbox, RETRY_DELAYS[Math.min(attempt, RETRY_DELAYS.length - 1)]);
    }

    // Отправить всё из очереди по порядку. Повтор безопасен: тот же request_id сервер не дублирует.
    function flushOutbox() {
      if (flushing) return Promise.resolve();
      var list = readOutbox();
      if (!list.length) return Promise.resolve();
      flushing = true;
      var entry = list[0];
      return request("POST", "/complaints", entry.body).then(function (res) {
        if (res.ok && res.data && res.data.complaint) {
          var complaint = res.data.complaint;
          writeOutbox(readOutbox().filter(function (item) { return item.body.request_id !== entry.body.request_id; }));
          if (!res.data.replayed) announce("created", complaint);
          return uploadAll(complaint.id, (entry.photos || []).map(dataUrlToBlob)).then(function () {
            flushing = false;
            toast(t("complaint.queue.sent", { code: complaint.code }));
            if (state && state.result && state.result.kind === "queued" && state.result.entry.body.request_id === entry.body.request_id) {
              state.result = { kind: "created", complaint: complaint };
              render();
            } else if (state && state.view === "mine") loadMine();
            return flushOutbox();
          });
        }
        flushing = false;
        if (res.status === 0 || res.status === 429 || res.status >= 500) { scheduleFlush(flushAttempt + 1); return null; }
        // Сервер отклонил (данные устарели): убираем из очереди, чтобы не повторять вечно.
        writeOutbox(readOutbox().filter(function (item) { return item.body.request_id !== entry.body.request_id; }));
        toast(t("complaint.error.send"));
        return flushOutbox();
      });
    }

    // ---------------------------------------------------------------- шаг 5: готово
    function copyCode(code, button) {
      function done() { toast(t("complaint.step5.copied")); }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(code).then(done, function () { selectFallback(); });
      } else selectFallback();
      function selectFallback() {
        var node = button.parentNode.querySelector(".bc-code__value");
        var range = document.createRange(); range.selectNodeContents(node);
        var sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
      }
    }

    function renderDone(body) {
      var result = state.result, complaint = result.complaint;
      if (result.kind === "queued") {
        body.appendChild(h("p", { "class": "bc-lead" }, t("complaint.queue.offline")));
        body.appendChild(h("p", { "class": "bc-place" }, [icon("pin"), h("span", {}, result.entry.label)]));
        body.appendChild(h("button", { "class": "bk-btn bk-btn--primary bk-btn--block", type: "button",
                                       onclick: function () { flushOutbox(); } },
          [icon("refresh"), h("span", {}, t("complaint.queue.send_now"))]));
        body.appendChild(h("button", { "class": "bk-btn bk-btn--block", type: "button", onclick: close }, t("complaint.step5.to_map")));
        return;
      }
      if (result.kind === "metoo") {
        var message = result.outcome === "added"
          ? t("complaint.step5.metoo_count", { n: result.place || complaint.reporters })
          : (result.outcome === "author" ? t("complaint.step5.author") : t("complaint.step5.already"));
        body.appendChild(h("p", { "class": "bc-lead" }, message));
      } else {
        // Номер — главное на экране успеха: подпись мелко сверху, номер крупно, «Скопировать» рядом.
        body.appendChild(h("div", { "class": "bc-code" }, [
          h("span", { "class": "bc-code__label" }, t("complaint.step5.code_label").replace(/[:\s]+$/, "")),
          h("div", { "class": "bc-code__row" }, [
            h("strong", { "class": "bc-code__value" }, complaint.code),
            h("button", { "class": "bk-btn bk-btn--ghost bc-code__copy", type: "button",
                          onclick: function (e) { copyCode(complaint.code, e.currentTarget); } }, [icon("copy"), h("span", {}, t("complaint.step5.copy"))])])]));
        // После отправки — что дальше и как найти обращение снова (волна 2, мелочи).
        if (complaint.due_at) body.appendChild(h("p", { "class": "bc-next" }, t("complaint.step5.next", { date: formatDate(complaint.due_at) })));
        body.appendChild(h("p", { "class": "bc-meta bc-find" }, t("complaint.step5.find", { code: complaint.code })));
      }
      if (result.kind === "metoo" && result.outcome === "added") {
        body.appendChild(h("p", { "class": "bc-meta" }, t("complaint.step5.metoo_follow")));
      }
      body.appendChild(h("p", { "class": "bc-place" }, [icon("pin"), h("span", {}, targetLabel(complaint.target))]));
      body.appendChild(stepsBar(complaint));
      body.appendChild(h("button", { "class": "bk-btn bk-btn--primary bk-btn--block", type: "button", onclick: openMine },
        [icon("list"), h("span", {}, t("complaint.step5.mine"))]));
      body.appendChild(h("button", { "class": "bk-btn bk-btn--block", type: "button", onclick: close },
        t("complaint.step5.to_map")));
      // Раунд 15 (R16 «Мой двор»): тихая ссылка — что ещё происходит во дворе. Только если модуль R16 есть в сборке;
      // жалоба на двор открывает этот двор, иначе — экран «Мой двор» (двор выбирает R16).
      var together = window.BirgeTogether;
      if (together && (typeof together.open === "function" || typeof together.mount === "function")) {
        var yard = complaint.target && complaint.target.kind === "area" && /^yard-/.test(complaint.target.id || "") ? complaint.target.id : null;
        body.appendChild(h("button", { "class": "bc-link bc-yard-link", type: "button", onclick: function () {
          close();
          if (typeof together.open === "function") { try { together.open("yard", yard || undefined); return; } catch (e) { /* адрес ниже */ } }
          window.location.hash = yard ? "#yard/" + yard : "#yard";
        } }, [icon("home"), h("span", {}, t("complaint.step5.yard"))]));
      }
    }

    // ---------------------------------------------------------------- «Мои обращения»
    function loadMine(focusCode, focusEvent) {
      // Повторное открытие — сразу из памяти (и пустой список тоже: правило 4 «мгновенный отклик», R10 §9), затем обновление.
      var cached = mineCache;
      state.mine = cached ? cached.items : null; state.mineError = false; state.changes = cached ? cached.changes : null;
      state.changesAll = false; state.mineSlow = false; state.mineStale = false;
      if (focusCode) state.focusCode = focusCode;
      if (focusEvent) { state.focusEvent = focusEvent; state.changesAll = true; }
      render();
      if (cached) focusCard();
      var owner = state;
      // Скелетон — только если ответа нет дольше 150 мс (быстрый ответ не мигает серыми полосами).
      if (!cached) setTimeout(function () {
        if (state === owner && state.view === "mine" && state.mine === null && !state.mineError) { state.mineSlow = true; render(); }
      }, 150);
      var seen = storageGet("localStorage", SEEN_KEY);
      Promise.all([request("GET", "/complaints/mine"),
                   seen ? request("GET", "/complaints/changes?since=" + encodeURIComponent(seen)) : Promise.resolve(null)])
        .then(function (replies) {
          var res = replies[0], changes = replies[1];
          if (!state || state !== owner || state.view !== "mine") return;
          if (!res.ok) {
            // Список уже на экране — не убираем его: сверху «Нет связи» с «Повторить», ниже — то, что было.
            if (cached) { state.mineStale = true; render(); return; }
            state.mineError = true; render(); return;
          }
          state.mineStale = false;
          state.mine = res.data.items || [];
          state.mineEnter = !cached;   // первые данные — карточки мягко появляются; обновление на месте — без движения
          var fresh = changes && changes.ok ? changes.data : null;
          // «Что изменилось» уже показано в этом открытии — не гасим его, если с прошлого запроса нового нет.
          state.changes = fresh && (fresh.items || []).length ? fresh : (cached ? cached.changes : fresh);
          mineCache = { items: state.mine, changes: state.changes };
          // «Что изменилось» — с прошлого визита; первый визит только запоминает момент.
          storageSet("localStorage", SEEN_KEY, new Date().toISOString());
          announceChanges(0);   // житель увидел изменения — значок у «Мои обращения» гаснет
          render();
          focusCard();
        });
    }

    // Карточка из ссылки/уведомления остаётся выделенной и раскрытой и после перерисовки (язык, ответ «Да/Осталось»);
    // прокрутка к ней — один раз.
    function focusCard() {
      if (state && state.focusEvent) {
        var row = els.panel.querySelector('.bc-changes__item[data-event="' + state.focusEvent.replace(/"/g, "") + '"]');
        if (row) row.classList.add("bc-changes__item--focus");
      }
      if (!state || !state.focusCode) return;
      var code = state.focusCode;
      state.focusCode = null;
      var card = els.panel.querySelector('.bc-mine__card[data-code="' + code.replace(/"/g, "") + '"]');
      if (!card) return;
      state.focused = code;
      card.classList.add("bc-mine__card--focus");
      var more = card.querySelector("details");
      if (more) more.open = true;
      card.scrollIntoView({ block: "start", behavior: "auto" });
    }

    var CHANGE_TEXT = { reopened: "mine.changes.reopened", verified: "mine.changes.verified", note: "mine.changes.note",
                        passport: "mine.changes.passport" };
    var CHANGES_SHOWN = 3;

    // «Что изменилось» (волна 2, п. 10; R11 IA_WAVE2 §2.1): только если есть новое, ≤ 3 строки, остальное — «Ещё N».
    function renderChanges(body) {
      var data = state.changes;
      if (!data || !data.items || !data.items.length) return;
      var box = h("section", { "class": "bk-card bc-changes", "aria-labelledby": "bc-changes-title" }, [
        h("h3", { "class": "bc-changes__title", id: "bc-changes-title" }, t("mine.changes.title"))]);
      var list = h("ul", { "class": "bc-changes__list" });
      var shown = state.changesAll ? data.items : data.items.slice(0, CHANGES_SHOWN);
      shown.forEach(function (item) {
        var row;
        if (item.kind === "nearby") {
          // Подписка «Рядом» (R08): нажатие ведёт в раздел «Рядом» оболочки R01 (#nearby).
          var title = (currentLang() === "kk" ? item.title_kk : item.title_ru) || item.title_ru || item.title_kk || "";
          row = h("button", { "class": "bc-changes__item bc-changes__item--nearby", type: "button", "data-event": item.id || "",
                              onclick: function () { close(); window.location.hash = "#nearby"; } },
            [h("strong", {}, title), h("span", {}, " — " + t("nearby.tab." + (item.tab || "now"))),
             h("span", { "class": "bc-meta" }, " · " + formatDate(item.at))]);
        } else {
          // «Исправлено» — это когда проверили жители; шаг службы — «Служба сообщила об устранении» (как на карте R07).
          var what = item.kind === "status" ? (item.status === "fixed" ? t("mine.update.fixed") : t("mine.changes.status", { status: t("status." + item.status) }))
            : item.kind === "handoff" || item.kind === "services" || item.kind === "part" ? historyTitle(item)
            : t(CHANGE_TEXT[item.kind]);
          row = h("button", { "class": "bc-changes__item" + (state.focusEvent === item.id ? " bc-changes__item--focus" : ""),
                              type: "button", "data-event": item.id || "",
                              onclick: function () { state.focusCode = item.code; focusCard(); } },
            [h("strong", {}, targetLabel(item.target)), h("span", {}, " — " + what + (item.text ? ": " + item.text : "")),
             h("span", { "class": "bc-meta" }, " · " + formatDate(item.at))]);
        }
        list.appendChild(h("li", {}, row));
      });
      box.appendChild(list);
      if (!state.changesAll && data.items.length > CHANGES_SHOWN) {
        box.appendChild(h("button", { "class": "bk-btn bk-btn--ghost bc-changes__more", type: "button",
                                      onclick: function () { state.changesAll = true; render(); } },
          t("mine.changes.more", { n: data.items.length - CHANGES_SHOWN })));
      }
      if (data.summary && data.summary.waiting > 0) {
        box.appendChild(h("p", { "class": "bc-meta" }, t("mine.waiting", { n: data.summary.waiting })));
      }
      body.appendChild(box);
    }

    function renderPending(body) {
      var list = readOutbox();
      if (!list.length) return;
      var ul = h("ul", { "class": "bc-mine" });
      list.forEach(function (entry) {
        ul.appendChild(h("li", { "class": "bk-card bc-mine__card bc-mine__card--pending" }, [
          h("div", { "class": "bc-mine__head" }, [
            h("span", { "class": "bc-mine__cat" }, h("span", {}, categoryLabel(entry.category))),
            h("span", { "class": "bk-status", "data-status": "pending" }, t("mine.pending"))]),
          h("p", { "class": "bc-meta" }, entry.label + " · " + formatDate(entry.queued_at)),
          h("button", { "class": "bk-btn bk-btn--block", type: "button", onclick: function () { flushOutbox(); } },
            [icon("refresh"), h("span", {}, t("complaint.queue.send_now"))])]));
      });
      body.appendChild(ul);
    }

    function verify(item, answer, button) {
      if (button) button.disabled = true;
      var owner = state;
      request("POST", "/complaints/" + encodeURIComponent(item.id) + "/verify", { answer: answer }).then(function (res) {
        if (state !== owner) return;
        if (!res.ok) { if (button) button.disabled = false; toast(t("complaint.error.send"), function () { verify(item, answer); }); return; }
        toast(t(answer === "no" ? "verify.reopened_toast" : "verify.thanks"));
        if (answer !== "cant" && res.data.result === "recorded") announce(answer === "yes" ? "verified" : "reopened", res.data.complaint);
        // Переход «служба сообщила → проверено жителями» — мягкий «отклик» точки статуса у этой карточки (один раз).
        if (answer === "yes") state.justVerified = item.id;
        loadMine();
      });
    }

    function unsubscribe(item, button) {
      if (button) button.disabled = true;
      var owner = state;
      request("POST", "/complaints/" + encodeURIComponent(item.id) + "/unsubscribe", {}).then(function (res) {
        if (state !== owner) return;
        if (!res.ok) { if (button) button.disabled = false; toast(t("complaint.error.send"), function () { unsubscribe(item); }); return; }
        toast(t("mine.unsubscribed"));
        loadMine();
      });
    }

    function photoThumb(complaintId, photoId) {
      // Фото грузим только когда их показывают (свёрнутые блоки не тянут сотни КБ).
      var img = h("img", { alt: "", loading: "lazy" });
      request("GET", "/complaints/" + encodeURIComponent(complaintId) + "/photos/" + encodeURIComponent(photoId)).then(function (res) {
        if (res.ok && res.data && res.data.photo) img.src = res.data.photo.data_url;
      });
      return h("li", { "class": "bc-thumb" }, img);
    }

    // «Ждут вашей проверки» (волна 2, п. 1; R11 §2.1): служба сообщила — автор и все «Я тоже» отвечают.
    // Главная кнопка экрана — «Да, исправлено» в первом блоке; если проверять нечего — главной кнопки нет.
    function verifyCard(item, primary) {
      var resolution = item.resolution || {};
      var after = resolution.photos_after || [];
      var box = h("li", { "class": "bc-verify", "data-code": item.code || "" }, [
        h("p", { "class": "bc-verify__place" }, [icon("pin"), h("strong", {}, targetLabel(item.target))]),
        h("p", { "class": "bc-verify__reported" }, t("verify.reported", { date: formatDate(resolution.reported_at || item.updated_at) })),
        resolution.what_done ? h("p", {}, t("verify.what_done", { text: resolution.what_done })) : null,
        after.length ? h("ul", { "class": "bc-thumbs bc-thumbs--small", "aria-label": t("verify.after_photo") },
          after.map(function (id) { return photoThumb(item.id, id); })) : null,
        h("p", { "class": "bc-verify__question" }, t("verify.question"))]);
      var buttons = h("div", { "class": "bc-verify__buttons" });
      // Три большие кнопки (дизайн-марафон), главная одна: «Да, исправлено» — тёмная; «Проблема осталась» — серая;
      // «Не могу проверить» — большая, но тихая, без заливки (R11 разбор 9 №3: не похожа на вторую главную).
      [["yes", "verify.yes", "bk-btn bk-btn--block" + (primary ? " bk-btn--primary" : ""), "check"],
       ["no", "verify.no", "bk-btn bk-btn--block", "refresh"],
       ["cant", "verify.cant", "bk-btn bk-btn--ghost bk-btn--block bc-verify__quiet", "info"]]
        .forEach(function (b) {
          buttons.appendChild(h("button", { "class": b[2] + " bc-verify__" + b[0], type: "button",
                                            onclick: function (e) { verify(item, b[0], e.currentTarget); } },
            [icon(b[3]), h("span", {}, t(b[1]))]));
        });
      box.appendChild(buttons);
      return box;
    }

    function renderWaitCheck(body) {
      var waiting = state.mine.filter(function (item) { return item.can_verify; });
      if (!waiting.length) return;
      body.appendChild(h("section", { "class": "bk-card bc-wait", "aria-labelledby": "bc-wait-title" }, [
        h("h3", { "class": "bc-changes__title", id: "bc-wait-title" }, t("verify.wait_title")),
        h("ul", { "class": "bc-wait__list" }, waiting.map(function (item, index) { return verifyCard(item, index === 0); }))]));
    }

    // Название службы на языке жителя: ключ словаря service.<id> (R08 ids, kk вычитан R11); если акимат
    // переименовал службу — его название как есть.
    function serviceName(p) {
      if (p.assignee_id && !p.assignee_custom && hasKey("service." + p.assignee_id)) return t("service." + p.assignee_id);
      return currentLang() === "kk" && p.assignee_kk ? p.assignee_kk : p.assignee;
    }

    // Срок в рабочих днях (волна 1, п. 6; UX_SPEC §10): цвет + слово, не только цвет.
    function deadlineNode(d) {
      if (!d || d.state === "answered") return null;
      if (d.state === "overdue") return h("span", { "class": "bc-deadline bc-deadline--danger" }, t("deadline.overdue", { n: d.overdue_working_days || 1 }));
      if (d.state === "today") return h("span", { "class": "bc-deadline bc-deadline--warn" }, t("deadline.today"));
      var left = d.working_days_left || 0;
      return h("span", { "class": "bc-deadline" + (left <= 1 ? " bc-deadline--warn" : "") }, t("deadline.left", { n: left }));
    }

    // Строка паспорта на карточке (R11 §2.1): «Передано: служба · Осталось N рабочих дней».
    // Раунд 15: у совместного обращения — «Работают 2 службы: ◉ Водоканал — сделано · ◐ Дорожная служба — в работе»
    // (статус-иконки ui-kit + слово; ведущая первой). Причины передач житель не видит — их нет в ответе API.
    function passportLine(item) {
      var p = item.passport || {};
      if (item.status === "rejected") return null;
      var joint = jointLine(item);
      if (joint) return joint;
      if (!p.assignee && !p.assignee_id) return null;
      return h("span", { "class": "bk-statusline__note bc-assignee" }, t("service.assigned", { service: serviceName(p) }));
    }

    var PART_ICON = { todo: "new", in_progress: "in_progress", done: "reported_fixed" };
    function partService(sid) { return hasKey("service." + sid) ? t("service." + sid) : sid; }
    function jointLine(item) {
      var j = item.joint;
      if (!j || !j.joint || !(j.services || []).length) return null;
      return h("div", { "class": "bk-statusline__note bc-joint-line" }, [
        h("span", { "class": "bc-joint-line__title" }, t("joint.resident.title", { n: j.services.length })),
        h("ul", { "class": "bc-joint-line__list" }, j.services.map(function (part) {
          // Служба и её статус — одним текстом: длинное казахское название переносится словами, «— орындалды» не
          // уезжает отдельной строкой; значок — слева, по первой строке.
          return h("li", { "class": "bc-joint-line__part", "data-status": part.status }, [statusIcon(PART_ICON[part.status] || "new"),
            h("span", { "class": "bc-joint-line__text" }, [h("span", { "class": "bc-joint-line__name" }, partService(part.service)),
              h("span", { "class": "bc-joint-line__state" }, " — " + t("joint.part." + part.status))])]);
        }))]);
    }

    // Статус — один раз (R11 CLEAN_PASS, правило 5), как строка статуса карточки эталона (.st): иконка + слово, ниже —
    // «Передано: служба»; срок ответа — справа мелко («Осталось 3 рабочих дня»).
    function statusLine(item) {
      var p = item.passport || {};
      var due = item.status === "new" ? deadlineNode(p.deadline) : null;
      return h("div", { "class": "bk-statusline bc-mine__status" }, [
        h("div", { "class": "bc-mine__stline" }, [statusBadge(displayStatus(item)), due ? h("small", { "class": "bc-mine__due" }, due) : null]),
        passportLine(item)]);
    }

    // Задержка — баннер-предупреждение в карточке (R11 §2.2): причина · временная мера · следующее обновление.
    function delayBanner(item) {
      var delay = (item.passport || {}).delay;
      if (!delay || (item.status !== "accepted" && item.status !== "in_progress" && item.status !== "new")) return null;
      var parts = [];
      if (delay.reason) parts.push(t("passport.delay_reason", { text: delay.reason }));
      if (delay.temp_measure) parts.push(t("passport.temp_measure", { text: delay.temp_measure }));
      if (delay.next_update_at) parts.push(t("passport.next_update", { date: formatDate(delay.next_update_at + "T12:00:00+05:00") }));
      if (!parts.length) return null;
      return h("p", { "class": "bk-banner bk-banner--warn bc-delay" }, parts.join(" · "));
    }

    // «Подробнее»: паспорт целиком и история (свёрнуто — карточка не растёт, защита от перегруза п. 3).
    function detailsBlock(item, open) {
      var p = item.passport || {};
      var lines = [t("passport.next", { text: p.next_step || t("mine.passport.next_default." + item.status) })];
      if (item.status === "new" && p.response_due) lines.push(t("passport.answer_due", { date: formatDate(p.response_due) }));
      if (item.status !== "rejected") {
        lines.push(p.fix_eta ? t("passport.fix_eta", { date: formatDate(p.fix_eta + "T12:00:00+05:00") }) : t("passport.fix_unknown"));
      }
      // «Подробнее» (статус в карточке — один раз, R11 CLEAN_PASS R09 №6): лента статусов — как отслеживание заказа в iOS
      // (дизайн-марафон): точки на линии, пройденное — тёмным, следующий шаг — серым; ниже — паспорт решения.
      var more = h("details", { "class": "bk-details bc-more", open: open || null }, [h("summary", {}, t("common.action.more"))]);
      if (item.demo) more.appendChild(h("span", { "class": "bk-tag bk-tag--demo bc-more__demo" }, t("common.demo")));
      // «История» (R11 IA_WAVE2 §2.2, R10 W2-2): сообщили → в работе → служба сообщила → проверили / вернули.
      var steps = item.history || (item.updates || []).map(function (u) { return u; });
      if (steps.length) {
        more.appendChild(h("p", { "class": "bc-label" }, t("passport.history")));
        var line = h("ol", { "class": "bc-updates bc-history bc-timeline" }, steps.map(function (u, i) {
          return h("li", { "class": "bc-timeline__item", "data-kind": u.kind, "data-state": i === steps.length - 1 ? "current" : "done" }, [
            h("span", { "class": "bc-timeline__dot", "aria-hidden": "true" }),
            h("div", { "class": "bc-timeline__body" }, [
              h("span", { "class": "bc-timeline__title" }, historyTitle(u)),
              historyDetail(u, item) ? h("span", { "class": "bc-timeline__text" }, historyDetail(u, item)) : null,
              h("span", { "class": "bc-meta" }, formatDate(u.at))])]);
        }));
        var next = nextStage(item);
        if (next) {
          line.appendChild(h("li", { "class": "bc-timeline__item", "data-state": "next" }, [
            h("span", { "class": "bc-timeline__dot", "aria-hidden": "true" }),
            h("div", { "class": "bc-timeline__body" }, [h("span", { "class": "bc-timeline__title" }, t("status." + next))])]));
        }
        more.appendChild(line);
      }
      more.appendChild(h("p", { "class": "bc-label" }, t("passport.title")));
      more.appendChild(h("ul", { "class": "bc-passport" }, lines.map(function (line) { return h("li", {}, line); })));
      var own = item.photos || [];
      if (own.length) {
        more.appendChild(h("p", { "class": "bc-label" }, t("mine.photos.title")));
        var ul = h("ul", { "class": "bc-thumbs bc-thumbs--small" });
        var load = function () {
          if (!more.open || ul.childNodes.length) return;
          own.forEach(function (ph) { ul.appendChild(photoThumb(item.id, ph.id)); });
        };
        more.addEventListener("toggle", load);
        more.appendChild(ul);
        if (open) setTimeout(load, 0);
      }
      return more;
    }

    // Строка ленты: заголовок — что произошло, ниже — подробность (что сделали, текст службы).
    function historyTitle(u) {
      if (u.kind === "created") return t("mine.history.created");
      if (u.kind === "status") return t("status." + u.status);
      if (u.kind === "verified") return t("mine.changes.verified");
      if (u.kind === "handoff") return t("mine.update.handoff", { service: partService(u.service) });
      if (u.kind === "services") return t("mine.update.services", { list: (u.services || []).map(partService).join(", ") });
      if (u.kind === "part") return t("mine.update.part", { service: partService(u.service), status: t("joint.part." + (u.part_status || "in_progress")) });
      return t("mine.update." + u.kind);
    }
    // Передача: «Срок ответа тот же — до 6 нояб» (житель видит, что передача срок не обнулила).
    function historyDetail(u, item) {
      if (u.kind === "handoff") {
        var due = item && item.passport && item.passport.response_due;
        return due && item.status === "new" ? t("joint.handoff.same_due", { date: formatDate(due) }) : "";
      }
      if (!u.text || u.kind === "created" || u.kind === "status" || u.kind === "verified" || u.kind === "services") return "";
      return u.kind === "fixed" ? t("verify.what_done", { text: u.text }) : u.text;
    }
    // Следующий этап на ленте (серым): новое → в работе → служба сообщила → проверено жителями.
    function nextStage(item) {
      var shown = displayStatus(item);
      return { "new": "in_progress", accepted: "in_progress", in_progress: "reported_fixed", reopened: "reported_fixed",
               reported_fixed: "verified" }[shown] || null;
    }


    // «Подписки (N)» — свёрнуто внизу (R11 §2.1): «Я тоже» = подписка; «Отписаться» — голос остаётся.
    function renderSubscriptions(body) {
      var subs = state.mine.filter(function (item) { return item.relation === "metoo"; });
      if (!subs.length) return;
      var more = h("details", { "class": "bk-details bc-more bc-subs" }, [
        h("summary", {}, t("mine.subscriptions") + " (" + subs.length + ")"),
        h("ul", { "class": "bc-subs__list" }, subs.map(function (item) {
          return h("li", { "class": "bc-subs__item" }, [
            h("span", {}, [h("strong", {}, categoryLabel(item.category)), " · ", targetLabel(item.target)]),
            h("button", { "class": "bk-btn bk-btn--ghost bc-unsubscribe", type: "button",
                          onclick: function (e) { unsubscribe(item, e.currentTarget); } }, t("mine.unsubscribe"))]);
        }))]);
      body.appendChild(more);
    }

    function renderMine(body) {
      if (state.mineError) {
        // Как BirgeUI.state(…, "error") у всех разделов: иллюстрация «нет связи», общая фраза, серая ⟳ «Повторить».
        body.appendChild(h("div", { "class": "bk-error", role: "alert" }, [illustration("offline", "wifi-off"),
          h("p", { "class": "bk-error__title" }, t("mine.error.title")),
          h("p", { "class": "bk-error__text" }, t("common.state.network_text")),
          h("button", { "class": "bk-btn", type: "button", onclick: function () { loadMine(); } }, [icon("refresh"), h("span", {}, t("complaint.error.retry"))])]));
        renderPending(body);
        return;
      }
      if (state.mine === null && !state.mineSlow) {
        body.appendChild(h("p", { "class": "bc-sr", role: "status" }, t("mine.loading")));
        return;
      }
      if (state.mine === null) {
        // Скелетон повторяет карточку: категория, статус, строка «Передано…», мета (а не серые прямоугольники).
        var skel = function () { return h("div", { "class": "bc-skel-card", "aria-hidden": "true" }, [
          h("span", { "class": "bk-skel bc-skel-line bc-skel-line--title" }), h("span", { "class": "bk-skel bc-skel-line bc-skel-line--status" }),
          h("span", { "class": "bk-skel bc-skel-line" }), h("span", { "class": "bk-skel bc-skel-line bc-skel-line--short" })]); };
        body.appendChild(h("div", { "class": "bc-loading", role: "status" }, [skel(), skel(),
          h("span", { "class": "bc-loading__text" }, t("mine.loading"))]));
        return;
      }
      if (state.mineStale) {
        body.appendChild(h("div", { "class": "bk-error bc-stale", role: "alert" }, [
          h("p", { "class": "bk-error__title" }, t("mine.error.title")),
          h("button", { "class": "bk-btn", type: "button", onclick: function () { loadMine(); } }, [icon("refresh"), h("span", {}, t("complaint.error.retry"))])]));
      }
      renderChanges(body);
      renderPending(body);
      if (!state.mine.length && !readOutbox().length) {
        body.appendChild(h("div", { "class": "bk-empty" }, [illustration("list", "list"),
          h("p", { "class": "bk-empty__title" }, t("mine.empty.title")),
          h("p", { "class": "bk-empty__text" }, t("mine.empty.hint")),
          h("button", { "class": "bk-btn bk-btn--primary", type: "button", onclick: function () { open(); } },
            [icon("plus"), h("span", {}, t("complaint.start.button"))])]));
        return;
      }
      renderWaitCheck(body);
      var list = h("ul", { "class": "bc-mine" + (state.mineEnter ? " bc-list--enter" : "") });
      state.mineEnter = false;
      state.mine.forEach(function (item) {
        var c = category(item.category);
        var title = categoryLabel(item.category) + (item.subtopic ? " · " + subtopicLabel(item.category, item.subtopic) : "");
        var focused = !!item.code && state.focused === item.code;
        var fresh = state.justVerified === item.id && displayStatus(item) === "verified";
        list.appendChild(h("li", { "class": "bk-card bc-mine__card" + (focused ? " bc-mine__card--focus" : "") + (fresh ? " bc-mine__card--verified-now" : ""),
                                   "data-code": item.code || "", "data-id": item.id }, [
          // Как карточка эталона A («5 секунд»): плитка категории 48 · название · «место · дата · номер»; ниже — статус
          // иконкой и словом с ответственным, срок справа; затем число людей и «Подробнее».
          h("div", { "class": "bc-mine__head" }, [
            h("span", { "class": "bk-tile bc-mine__tile", "aria-hidden": "true" }, icon(c ? c.icon : "dots")),
            h("div", { "class": "bc-mine__headtext" }, [
              h("span", { "class": "bc-mine__cat" }, title),
              h("p", { "class": "bc-meta bc-mine__sub" }, [targetLabel(item.target), " · ", formatDate(item.created_at),
                item.code ? " · " : "", item.code ? h("span", { "class": "bc-nowrap" }, item.code) : null])])]),
          statusLine(item),
          item.relation === "metoo" ? h("p", { "class": "bc-meta" }, t("mine.metoo_badge")) : null,
          // Все люди, сообщившие о том же на этом месте (как на шаге «Я тоже»), а не только по этой жалобе.
          h("p", { "class": "bc-meta" }, t("mine.reporters", { n: item.place_reporters || reportersOf(item) || 1 })),
          delayBanner(item),
          detailsBlock(item, focused)]));
      });
      body.appendChild(list);
      if (state.mine) state.justVerified = null;
      renderSubscriptions(body);
      demoFootnote(body, state.mine.some(function (item) { return item.demo; }) ||
        !!(state.changes && (state.changes.items || []).some(function (item) { return item.demo; })));
    }

    // «Пример» — не у каждой карточки: одна серая строка внизу списка (R11 D-5, как в «Рядом»); у карточки, открытой
    // в «Подробнее», и у похожей на шаге «Я тоже» метка остаётся рядом с содержимым (честная пометка, R15).
    function demoFootnote(body, any) {
      if (any) body.appendChild(h("p", { "class": "bk-footnote bc-demo-note" }, t("common.tag.demo_hint")));
    }

    // Галочка успеха: круг и «✓» рисуются линией (stroke-dashoffset), цвет — акцент #152c26 (не зелёный: зелёный
    // в Birge — только «исправлено»). Без движения при prefers-reduced-motion. П1: значок 48 px той же толщины, что
    // иконки набора R11 — отметка «отправлено», а не картинка.
    function successMark() {
      var ns = "http://www.w3.org/2000/svg";
      var svg = document.createElementNS(ns, "svg");
      svg.setAttribute("class", "bk-check-draw bc-success__mark"); svg.setAttribute("viewBox", "0 0 24 24");
      svg.setAttribute("aria-hidden", "true"); svg.setAttribute("focusable", "false");
      var circle = document.createElementNS(ns, "circle");
      circle.setAttribute("class", "bc-success__circle"); circle.setAttribute("cx", "12"); circle.setAttribute("cy", "12"); circle.setAttribute("r", "8.5");
      var tick = document.createElementNS(ns, "path");
      tick.setAttribute("class", "bc-success__tick"); tick.setAttribute("d", "m8.2 12.3 2.6 2.6 5-5.4");
      svg.appendChild(circle); svg.appendChild(tick);
      return h("div", { "class": "bc-success" }, svg);
    }

    // ---------------------------------------------------------------- каркас панели
    function render() {
      if (!state) return;
      var panel = els.panel;
      panel.innerHTML = "";
      var mine = state.view === "mine";
      // Шаг 2 на телефоне: пока места нет — низкая шторка (вопрос и «Моё местоположение»), карта почти вся видна
      // (R11 B1 №2); когда пришли варианты — до половины; дальше — полная. «Мои обращения»: список — по содержимому (круг 8),
      // загрузка — половина (скелетон), «пока пусто» и «нет связи» — по содержимому, без пустого белого низа.
      // Шаги 4–5 (похожие, проверка, успех) — шторка по содержимому (как «средняя» шторка iOS): над ней видно место
      // на карте, внизу нет пустого белого; текст (шаг 3) — полная, под клавиатуру.
      // Круг 8: список «Моих обращений» — тоже по содержимому (fit): одна-две карточки не тянут пустую шторку на весь
      // экран, над ней видна карта; длинный список упирается в 92 % и прокручивается.
      var snap = mine ? (state.mineError || (state.mine && !state.mine.length) ? "peek" : (state.mine ? "fit" : "half"))
        : (state.step === 2 ? (state.candidates || state.candidatesLoading ? "half" : "peek") : (state.step === 3 ? "full" : "fit"));
      panel.setAttribute("data-snap", snap);
      panel.setAttribute("data-step", mine ? "mine" : String(state.step));
      // Стекло (R11 GLASS.md, R09): «Мои обращения» — стеклянная панель/шторка над картой; мастер жалобы — форма,
      // остаётся непрозрачным. Без ui-kit со стеклом — непрозрачный белый (complaint.css, :where).
      panel.classList.toggle("bk-glass", mine);
      panel.classList.toggle("bk-glass--strong", mine);   // эталон: стекло с текстом — плотное 86 %
      // Под стеклом «Моих обращений» — одна карта, без второй панели (список R07 размытыми пятнами): complaint.css.
      document.documentElement.classList.toggle("bc-mine-open", mine);
      if (!mine && state.reviewing && state.step === 4) panel.setAttribute("data-review", "1");
      else panel.removeAttribute("data-review");
      var canBack = !mine && state.step > 2 && state.step < 5;
      // Закрыть — круглая «×» 32 px на светлой подложке в правом верхнем углу, как у карточки эталона A (.x); зона
      // нажатия 44, подпись «Закрыть» — для чтения с экрана. «Мои обращения»: заголовок — в той же строке, слева.
      var closeBtn = h("button", { "class": "bc-close", type: "button", "aria-label": t("complaint.wizard.close"), onclick: close },
        [h("span", { "class": "bc-x", "aria-hidden": "true" }, icon("close")), h("span", { "class": "bc-close__label" }, t("complaint.wizard.close"))]);
      var head = h("header", { "class": "bc-head" + (mine ? " bc-head--title" : "") }, [
        canBack ? h("button", { "class": "bk-btn bk-btn--ghost bc-back", type: "button", onclick: back },
          [icon("back"), h("span", {}, t("complaint.wizard.back"))]) : h("span", { "class": "bc-head__spacer" }),
        closeBtn]);
      panel.appendChild(h("div", { "class": "bc-handle", "aria-hidden": "true" }));
      panel.appendChild(head);
      // Успех — без «Шаг 5 из 5»: крупная галочка рисуется (≈ 0,6 с) над заголовком, как в iOS.
      var success = !mine && state.step === 5 && state.result && state.result.kind !== "queued";
      if (success) panel.appendChild(successMark());
      if (!mine && state.step !== 5) {
        var dots = h("div", { "class": "bk-wizard" }, [h("span", { "class": "bk-wizard__label" },
          t("complaint.wizard.step", { n: state.step, total: TOTAL_STEPS }))]);
        var track = h("span", { "class": "bk-wizard__dots", "aria-hidden": "true" });
        // Точки шага — <i>, как в ui-kit R11 (.bk-wizard__dots > i): со <span> ui-kit их не рисовал.
        for (var i = 1; i <= TOTAL_STEPS; i++) track.appendChild(h("i", { "data-state": i < state.step ? "done" : (i === state.step ? "current" : "todo") }));
        dots.appendChild(track);
        panel.appendChild(dots);
      }
      var titles = { 2: "complaint.step2.title", 3: "complaint.step3.title", 4: "complaint.step4.title", 5: "complaint.step5.title" };
      var title = mine ? (state.mine && state.mine.length ? t("mine.count", { n: state.mine.length }) : t("mine.title"))
        : (state.step === 4 ? (state.reviewing ? t("complaint.review.title") : t("complaint.step4.title", { n: placeCount(state.similar) }))
          : (state.step === 5 && state.result.kind === "metoo" ? t("complaint.step5.metoo_title")
            : (state.step === 5 && state.result.kind === "queued" ? t("complaint.queue.title") : t(titles[state.step]))));
      var heading = h("h2", { id: "bc-title", "class": "bc-title", tabindex: "-1" }, title);
      if (mine) head.replaceChild(heading, head.firstChild);   // «Мои обращения (1)» и «×» — одна строка, как в эталоне
      else panel.appendChild(heading);
      var body = h("div", { "class": "bc-body" });
      // Смена шага — мягкий въезд содержимого (240 мс, вперёд справа, назад слева); перерисовка того же шага (язык,
      // подсказка категории) — без движения. prefers-reduced-motion — без анимации (complaint.css).
      var animKey = mine ? "mine" : state.step + (state.reviewing ? "r" : "");
      if (state.animKey !== animKey) {
        var from = state.animKey;
        if (from !== undefined) {   // первое открытие — панель сама выезжает, содержимое не двигаем второй раз
          body.classList.add("bc-body--enter");
          body.setAttribute("data-dir", from !== "mine" && animKey !== "mine" && parseInt(animKey, 10) < parseInt(from, 10) ? "back" : "fwd");
        }
        state.animKey = animKey;
      }
      panel.appendChild(body);
      if (mine) renderMine(body);
      else if (state.step === 2) renderPlace(body);
      else if (state.step === 3) renderText(body);
      else if (state.step === 4) { if (state.reviewing) renderReview(body); else renderSimilar(body); }
      else renderDone(body);
      setPicking(!mine && state.step === 2);
      // Шаги 4–5: выбранное место видно — телефон: над шторкой (всегда, один раз при входе в шаг); ноутбук: справа от
      // карточки слева (эталон A), только если место ушло под карточку.
      if (body.classList.contains("bc-body--enter") && !mine && state.step >= 4 && map.reveal) {
        var where = state.point || (state.target && state.result && state.result.complaint && state.result.complaint.point);
        if (where) requestAnimationFrame(function () {
          if (panel.hidden) return;
          var r = panel.getBoundingClientRect();
          var header = document.querySelector(".topbar, #birge-header");
          var top = header ? header.getBoundingClientRect().bottom : 0;
          if (window.innerWidth < 1024) map.reveal(where, { top: top, bottom: r.top, left: 0, right: window.innerWidth });
          else map.reveal(where, { top: top, bottom: window.innerHeight, left: r.right, right: window.innerWidth - 72, onlyIfHidden: true });
        });
      }
      if (state.lastFocusStep !== panel.getAttribute("data-step")) {
        state.lastFocusStep = panel.getAttribute("data-step");
        focusTitle();
      }
    }

    function focusTitle() {
      var heading = els.panel.querySelector("#bc-title");
      if (heading && !els.panel.hidden) heading.focus({ preventScroll: true });
    }

    function back() {
      if (state.step === 4) { state.step = 3; state.reviewing = false; }
      else if (state.step === 3) { state.step = 2; state.candidatesLoading = false; }
      render();
    }

    // preset (R12 QR-паспорт): {target, point, geometry, approximate} — место уже известно, сразу шаг ③ (текст).
    function open(preset) {
      var keepText = state && state.view === "wizard" && state.step < 5 ? state : null;
      state = keepText || freshState();
      state.view = "wizard";
      if (state.step === 5) state = freshState();
      if (preset && preset.target && preset.target.kind && preset.target.id && Array.isArray(preset.point)) {
        state.point = [Number(preset.point[0]), Number(preset.point[1])];
        state.target = Object.assign({}, preset.target, preset.approximate ? { approximate: true } : {});
        state.geometry = preset.geometry || null;
        state.candidates = null; state.candidatesLoading = false;
        state.step = 3;
        if (map.highlight) map.highlight(state.target, state.geometry, state.point);
      }
      els.textarea = null;
      // Сначала рисуем (высота шторки уже нужная), потом показываем — без прыжка «полная → половина».
      render();
      els.panel.hidden = false;
      els.fab.hidden = true;
      document.documentElement.classList.add("bc-open");
      focusTitle();
    }

    function openMine(focusCode, focusEvent) {
      if (!state) state = freshState();
      if (state.step === 5) { var keep = freshState(); keep.mine = null; state = keep; }
      state.view = "mine";
      if (map.clear) map.clear();
      loadMine(typeof focusCode === "string" ? focusCode : null, typeof focusEvent === "string" ? focusEvent : null);
      els.panel.hidden = false;
      els.fab.hidden = true;
      document.documentElement.classList.add("bc-open");
      focusTitle();
    }

    function close() {
      // LOCAL_FINAL №2: отложенная подсказка модели не должна сработать после закрытия.
      clearTimeout(classifyTimer);
      classifySeq++;
      setPicking(false);
      if (map.clear) map.clear();
      els.panel.hidden = true;
      els.fab.hidden = opts.fab === false;
      document.documentElement.classList.remove("bc-open", "bc-mine-open");
      if (state && (state.step === 5 || state.view === "mine")) state = null;
      els.fab.focus({ preventScroll: true });
    }

    function relabel() {
      els.fab.querySelector(".bc-fab__label").textContent = t("complaint.start.button");
      if (!els.panel.hidden) { var text = state && state.text; render(); if (els.textarea && text) els.textarea.value = text; }
    }

    function onLang() { relabel(); }
    window.addEventListener("birge:lang", onLang);
    // Словари R11 грузятся асинхронно: после загрузки перерисовываем тексты из общего словаря.
    if (window.BirgeI18n && window.BirgeI18n.ready && typeof window.BirgeI18n.ready.then === "function") {
      window.BirgeI18n.ready.then(onLang, function () { /* остаётся запасной словарь R09 */ });
    }
    if (mql && mql.addEventListener) mql.addEventListener("change", render);
    relabel();

    // Уведомление/ссылка открывает конкретное изменение (волна 2, мелочи; R11 IA_WAVE2 §2.1):
    //   #mine/event=B-0001.verified.20261011T2303 — «Мои обращения», строка изменения подсвечена, карточка раскрыта;
    //   #complaint=B-0001 — карточка обращения; #mine — экран «Мои обращения».
    // Язык не трогаем — он остаётся выбранным жителем (защита: «не переключать язык по ссылке»).
    function linkFromHash() {
      var hash = window.location.hash || "";
      var ev = /^#mine\/event=([A-Za-z0-9.-]{3,80})$/.exec(hash);
      if (ev) return { code: ev[1].split(".")[0], event: ev[1] };
      var m = /(?:^#|&)complaint=([A-Za-z0-9-]{3,40})(?:&|$)/.exec(hash);
      if (m) return { code: m[1] };
      return hash === "#mine" ? {} : null;
    }
    function onHash() {
      var link = linkFromHash();
      if (link) openMine(link.code || null, link.event || null);
    }
    window.addEventListener("hashchange", onHash);
    if (linkFromHash()) setTimeout(onHash, 0);

    // Значок у пункта меню «Мои обращения» (R11 IA_WAVE2 §1: единственный бейдж — число новых изменений).
    // Оболочка R01 слушает window "birge:complaint-changes" {n} или спрашивает ui.changesCount().
    var lastChanges = 0;
    function announceChanges(n) {
      lastChanges = n;
      try { window.dispatchEvent(new CustomEvent("birge:complaint-changes", { detail: { n: n } })); } catch (e) { /* старый браузер */ }
    }
    function changesCount() {
      var seen = storageGet("localStorage", SEEN_KEY);
      if (!seen) return Promise.resolve(0);           // первый визит ещё не было — сравнивать не с чем
      return request("GET", "/complaints/changes?since=" + encodeURIComponent(seen)).then(function (res) {
        var n = res.ok && res.data && res.data.items ? res.data.items.length : lastChanges;
        if (n !== lastChanges) announceChanges(n);
        return n;
      });
    }
    setTimeout(function () { changesCount(); }, 0);

    // Очередь без сети: при открытии страницы и когда сеть вернулась.
    function onOnline() { scheduleFlush(0); flushOutbox(); }
    window.addEventListener("online", onOnline);
    if (readOutbox().length) setTimeout(function () { flushOutbox(); }, 0);

    // Эталон A, телефон: в шторке «Рядом с вами» (R07/R01) строка «✓ Двор у ул. Сыганак — Снег убран · проверьте» —
    // обращения этого жителя, где служба сообщила об устранении и ждут его проверки. → Promise<[{ id, code, place,
    // category, status, open() }]>; open() — «Мои обращения» с этой карточкой. Те же данные, что «Ждут вашей проверки».
    function waitingChecks() {
      return request("GET", "/complaints/mine").then(function (res) {
        if (!res.ok) return [];
        return (res.data.items || []).filter(function (item) { return item.can_verify; }).map(function (item) {
          return { id: item.id, code: item.code, place: targetLabel(item.target), category: categoryLabel(item.category),
                   status: "reported_fixed", open: function () { openMine(item.code || undefined); } };
        });
      });
    }

    return {
      open: open, openMine: openMine, close: close, relabel: relabel,
      openComplaint: function (code) { openMine(code); },
      waitingChecks: waitingChecks,
      changesCount: changesCount,
      flushOutbox: flushOutbox,
      state: function () { return state; },
      destroy: function () {
        setPicking(false);
        document.documentElement.classList.remove("bc-open", "bc-mine-open");
        document.removeEventListener("keydown", onKey);
        window.removeEventListener("hashchange", onHash);
        window.removeEventListener("online", onOnline);
        clearTimeout(flushTimer);
        window.removeEventListener("birge:lang", onLang);
        if (mql && mql.removeEventListener) mql.removeEventListener("change", render);
        [els.fab, els.panel, els.toast].forEach(function (node) { if (node.parentNode) node.parentNode.removeChild(node); });
        state = null;
      }
    };
  }

  function setLang(lang) {
    lang = lang === "kk" ? "kk" : "ru";
    if (window.BirgeI18n && typeof window.BirgeI18n.setLang === "function") window.BirgeI18n.setLang(lang);
    storageSet("localStorage", LANG_KEY, lang);
    document.documentElement.lang = lang;
    try { window.dispatchEvent(new CustomEvent("birge:lang", { detail: { lang: lang } })); } catch (e) { /* */ }
  }

  window.BirgeComplaint = {
    mount: mount, maplibreAdapter: maplibreAdapter, setLang: setLang, lang: currentLang,
    t: t, pluralForm: pluralForm, residentSteps: residentSteps, formatDate: formatDate,
    emergency: emergency, seasonalCategories: seasonalCategories, version: "r09-round15-joint",
    // Для компонентов сотрудника и списка акимата (complaint-staff.js, complaint-list.js) — те же подписи.
    displayStatus: displayStatus, categoryLabel: categoryLabel, subtopicLabel: subtopicLabel,
    targetLabel: targetLabel, statusBadge: statusBadge, statusIcon: statusIcon, icon: icon, illustration: illustration,
    categoryIcon: function (id) { var c = category(id); return c ? c.icon : "dots"; },
    mountNear: mountNear
  };
  // Помощники фото для компонента сотрудника (complaint-staff.js): то же уменьшение и загрузка частями.
  window.BirgeComplaintPhotos = {
    shrink: shrinkPhoto,
    upload: function (complaintId, blob, kind, csrf) { return uploadPhoto(complaintId, blob, kind, csrf); }
  };
})();
