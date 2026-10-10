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
  var DRAFT_KEY = "birge.complaint.draft";
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

  function targetLabel(target) {
    if (!target) return "";
    var lang = currentLang();
    var label = target["label_" + lang] || target.label_ru || target.label_kk;
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

  function request(method, path, body, timeoutMs) {
    var controller = window.AbortController ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, timeoutMs || NET_TIMEOUT_MS) : null;
    var headers = { "Accept": "application/json", "X-Birge-Device": deviceId() };
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

  function statusBadge(status) {
    return h("span", { "class": "bk-status", "data-status": status }, t("status." + status));
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
    residentSteps(complaint).forEach(function (step) {
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
    els.fab = h("button", { "class": "bk-btn bk-btn--primary bc-fab", type: "button", onclick: function () { open(); } },
      [icon("plus"), h("span", { "class": "bc-fab__label" })]);
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

    function freshState() {
      var draft = null;
      try { draft = JSON.parse(storageGet("sessionStorage", DRAFT_KEY) || "null"); } catch (e) { draft = null; }
      return {
        view: "wizard", step: 2,
        point: null, candidates: null, candidatesLoading: false, target: null, geometry: null,
        text: (draft && typeof draft.text === "string") ? draft.text : "",
        category: null, categorySource: null, model: null, suggestion: null, gridOpen: false,
        similar: null, similarChecked: false,
        sending: false, requestId: (draft && draft.requestId) || ("r-" + randomId(20)),
        result: null, mine: null, mineError: false, locating: false
      };
    }

    function saveDraft() {
      storageSet("sessionStorage", DRAFT_KEY, state && state.text
        ? JSON.stringify({ text: state.text, requestId: state.requestId }) : null);
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
      request("GET", "/targets?lon=" + state.point[0] + "&lat=" + state.point[1], undefined, TARGETS_TIMEOUT_MS)
        .then(function (res) {
          if (seq !== state.pickSeq) return;
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
      var seq = state.pickSeq;
      request("GET", "/complaints/place?lon=" + state.point[0] + "&lat=" + state.point[1]).then(function (res) {
        if (seq !== state.pickSeq) return;
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
      navigator.geolocation.getCurrentPosition(function (pos) {
        state.locating = false;
        var point = [pos.coords.longitude, pos.coords.latitude];
        if (map.flyTo) map.flyTo(point, visibleOffset());
        pickPoint(point);
      }, function () {
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
        // Точка внутри двора/площадки (0 м) — «Вы здесь», а не «0 м» и не пусто (R11 B2 №3).
        var here = typeof d === "number" && d < 1;
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
      classifyTimer = setTimeout(function () {
        var seq = ++classifySeq;
        request("POST", "/classify", { text: state.text }, ML_TIMEOUT_MS).then(function (res) {
          if (seq !== classifySeq || !state || state.categorySource === "resident") return;
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
            state.category = data.category; state.categorySource = "model"; state.gridOpen = false;
          } else if (!state.category) {
            state.gridOpen = true;
          }
          renderCategory();
          updateSendButton();
        });
      }, CLASSIFY_DEBOUNCE_MS);
    }

    function pickCategory(id) {
      // Выбор в сетке — всегда решение жителя («resident»), даже если совпал с подсказкой модели.
      state.category = id; state.categorySource = "resident";
      state.gridOpen = false;
      renderCategory();
      updateSendButton();
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
                        onclick: function () { state.gridOpen = true; renderCategory(); } }, t("complaint.step3.change"))
        ]));
        return;
      }
      if (!state.gridOpen && !state.category) {
        // Пока модель думает или текста мало — кнопка выбора вручную (без «загрузки модели»).
        box.appendChild(h("button", { "class": "bk-btn bk-btn--ghost bc-change", type: "button",
                                      onclick: function () { state.gridOpen = true; renderCategory(); } },
          t("complaint.step3.choose")));
        return;
      }
      box.appendChild(h("p", { "class": "bc-label", id: "bc-cat-title" }, t("complaint.step3.choose")));
      // Сетка ui-kit R11: иконка слева + подпись, колонки ≥ 150 px (2 на телефоне), казахские слова не рвутся.
      var grid = h("div", { "class": "bk-catgrid", role: "group", "aria-labelledby": "bc-cat-title" });
      categories().forEach(function (c) {
        grid.appendChild(h("button", { type: "button",
                                       "aria-pressed": state.category === c.id ? "true" : "false",
                                       "data-suggested": c.id === state.suggestion ? "true" : null,
                                       onclick: function () { pickCategory(c.id); } },
          [icon(c.icon), h("span", {}, categoryLabel(c.id))]));
      });
      box.appendChild(grid);
    }

    function updateSendButton() {
      if (!els.send) return;
      var ready = state.text.trim().length >= 3 && !!state.category && !state.sending;
      els.send.disabled = !ready;
      els.send.querySelector("span").textContent = state.sending ? t("complaint.step3.sending") : t("complaint.step3.send");
    }

    function renderText(body) {
      if (state.target || state.approximateOnly) {
        body.appendChild(h("p", { "class": "bc-place" }, [icon("pin"),
          h("span", {}, t("complaint.step2.selected", { label: targetLabel(state.target || { approximate: true }) }))]));
      }
      var example = t("complaint.example." + (state.category || "roads"));
      body.appendChild(h("label", { "class": "bc-label", "for": "bc-text" }, t("complaint.step3.label")));
      if (!els.textarea) {
        els.textarea = h("textarea", { id: "bc-text", "class": "bc-textarea", rows: "4", maxlength: "2000" });
        els.textarea.addEventListener("input", function () {
          state.text = els.textarea.value;
          saveDraft();
          updateSendButton();
          scheduleClassify();
        });
      }
      els.textarea.value = state.text;
      els.textarea.setAttribute("placeholder", t("complaint.step3.example", { example: example }));
      body.appendChild(els.textarea);
      body.appendChild(h("p", { "class": "bc-meta" }, t("complaint.step3.privacy")));
      els.categoryBox = h("div", { "class": "bc-category", "aria-live": "polite" });
      body.appendChild(els.categoryBox);
      renderCategory();
      els.send = h("button", { "class": "bk-btn bk-btn--primary bk-btn--block bc-send", type: "button",
                               onclick: checkSimilarThenSend }, [icon("send"), h("span")]);
      body.appendChild(els.send);
      updateSendButton();
      if (state.text) scheduleClassify();
    }

    // ---------------------------------------------------------------- шаг 4: похожие
    function checkSimilarThenSend() {
      if (state.sending) return;
      state.sending = true; updateSendButton();
      findSimilar().then(function (match) {
        state.sending = false;
        state.similarChecked = true;
        if (match && match.reporters > 0) {
          state.similar = match; state.step = 4; render();
        } else {
          send();
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
          return request("GET", "/complaints/" + encodeURIComponent(matches[0].complaint_id)).then(function (r) {
            return r.ok && r.data && r.data.complaint ? r.data.complaint : null;
          });
        });
      return byText.then(function (found) {
        if (found && found.status !== "fixed" && found.status !== "rejected") return found;
        if (!state.target || !state.target.id) return null;
        var q = "/complaints/summary?target_id=" + encodeURIComponent(state.target.id) +
                "&category=" + encodeURIComponent(state.category) + "&days=14";
        return request("GET", q, undefined, ML_TIMEOUT_MS).then(function (res) {
          return res.ok && res.data && res.data.top ? res.data.top : null;
        });
      }).catch(function () { return null; });
    }

    function renderSimilar(body) {
      var match = state.similar;
      var ago = daysAgo(match.created_at);
      body.appendChild(h("div", { "class": "bc-similar" }, [
        h("p", { "class": "bc-similar__count" }, [h("span", { "class": "bk-heat bc-similar__badge", "data-level": String(heatLevel(match.reporters)) },
          String(match.reporters)), h("span", {}, categoryLabel(match.category))]),
        h("p", { "class": "bc-meta" }, [targetLabel(match.target),
          " · ", ago === 0 ? t("complaint.step4.today") : t("complaint.step4.ago_days", { n: ago })]),
        h("div", { "class": "bc-similar__status" }, statusBadge(match.status))
      ]));
      body.appendChild(h("p", { "class": "bc-hint" }, t("complaint.step4.hint")));
      body.appendChild(h("button", { "class": "bk-btn bk-btn--primary bk-btn--block", type: "button",
                                     onclick: function (e) { metoo(match, e.currentTarget); } },
        [icon("users"), h("span", {}, t("complaint.step4.metoo"))]));
      body.appendChild(h("button", { "class": "bk-btn bk-btn--block bc-different", type: "button", onclick: function () { send(); } },
        t("complaint.step4.different")));
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
      request("POST", "/complaints/" + encodeURIComponent(match.id) + "/metoo", {}).then(function (res) {
        if (button) button.disabled = false;
        if (!res.ok) { toast(t("complaint.error.send"), function () { metoo(match); }); return; }
        state.result = { kind: "metoo", outcome: res.data.result, complaint: res.data.complaint };
        if (res.data.result === "added") announce("metoo", res.data.complaint);
        clearDraft();
        state.step = 5; render();
      });
    }

    // ---------------------------------------------------------------- отправка
    function clearDraft() {
      storageSet("sessionStorage", DRAFT_KEY, null);
    }

    function send() {
      if (state.sending) return;
      state.sending = true;
      if (state.step !== 3) { state.step = 3; render(); }
      updateSendButton();
      var body = { text: state.text, category: state.category, category_source: state.categorySource || "resident",
                   model: state.model, point: state.point, target: state.target, request_id: state.requestId };
      request("POST", "/complaints", body).then(function (res) {
        state.sending = false;
        if (res.ok && res.data && res.data.complaint) {
          state.result = { kind: "created", complaint: res.data.complaint };
          if (!res.data.replayed) announce("created", res.data.complaint);
          clearDraft();
          state.step = 5; render();
          return;
        }
        updateSendButton();
        var code = res.error && res.error.code;
        if (res.status === 429) toast(t("complaint.error.too_many"));
        else if (code === "invalid" && res.error.fields && res.error.fields.point) toast(t("complaint.error.outside"));
        else toast(t("complaint.error.send"), send);   // текст остаётся в поле и в черновике
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
      if (result.kind === "metoo") {
        var message = result.outcome === "added"
          ? t("complaint.step5.metoo_count", { n: complaint.reporters })
          : (result.outcome === "author" ? t("complaint.step5.author") : t("complaint.step5.already"));
        body.appendChild(h("p", { "class": "bc-lead" }, message));
      } else {
        body.appendChild(h("p", { "class": "bc-code" }, [
          h("span", {}, t("complaint.step5.code_label") + " "),
          h("strong", { "class": "bc-code__value" }, complaint.code),
          h("button", { "class": "bk-btn bk-btn--ghost", type: "button",
                        onclick: function (e) { copyCode(complaint.code, e.currentTarget); } }, t("complaint.step5.copy"))]));
        if (complaint.due_at) body.appendChild(h("p", { "class": "bc-meta" }, t("complaint.step5.due", { date: formatDate(complaint.due_at) })));
      }
      body.appendChild(h("p", { "class": "bc-place" }, [icon("pin"), h("span", {}, targetLabel(complaint.target))]));
      body.appendChild(stepsBar(complaint));
      body.appendChild(h("button", { "class": "bk-btn bk-btn--primary bk-btn--block", type: "button", onclick: openMine },
        [icon("list"), h("span", {}, t("complaint.step5.mine"))]));
      body.appendChild(h("button", { "class": "bk-btn bk-btn--block", type: "button", onclick: close },
        t("complaint.step5.to_map")));
    }

    // ---------------------------------------------------------------- «Мои обращения»
    function loadMine() {
      state.mine = null; state.mineError = false; render();
      request("GET", "/complaints/mine").then(function (res) {
        if (!state || state.view !== "mine") return;
        if (!res.ok) { state.mineError = true; render(); return; }
        state.mine = res.data.items || [];
        render();
      });
    }

    function renderMine(body) {
      if (state.mineError) {
        body.appendChild(h("div", { "class": "bk-error", role: "alert" }, [icon("wifi-off"),
          h("p", { "class": "bk-error__title" }, t("mine.error.title")),
          h("p", {}, t("mine.error.hint")),
          h("button", { "class": "bk-btn", type: "button", onclick: loadMine }, [icon("refresh"), h("span", {}, t("complaint.error.retry"))])]));
        return;
      }
      if (state.mine === null) {
        body.appendChild(h("div", { "class": "bc-loading", role: "status" }, [
          h("span", { "class": "bk-skel bc-skel-card" }), h("span", { "class": "bk-skel bc-skel-card" }),
          h("span", { "class": "bc-loading__text" }, t("mine.loading"))]));
        return;
      }
      if (!state.mine.length) {
        body.appendChild(h("div", { "class": "bk-empty" }, [icon("list"),
          h("p", { "class": "bk-empty__title" }, t("mine.empty.title")),
          h("p", {}, t("mine.empty.hint")),
          h("button", { "class": "bk-btn bk-btn--primary", type: "button", onclick: function () { open(); } },
            [icon("plus"), h("span", {}, t("complaint.start.button"))])]));
        return;
      }
      var list = h("ul", { "class": "bc-mine" });
      state.mine.forEach(function (item) {
        var c = category(item.category);
        var overdue = item.status === "new" && item.due_at && new Date(item.due_at).getTime() < Date.now();
        list.appendChild(h("li", { "class": "bk-card bc-mine__card" }, [
          h("div", { "class": "bc-mine__head" }, [
            h("span", { "class": "bc-mine__cat" }, [icon(c ? c.icon : "dots"), h("span", {}, categoryLabel(item.category))]),
            statusBadge(item.status)]),
          h("p", { "class": "bc-meta" }, [targetLabel(item.target), " · ", formatDate(item.created_at),
            item.code ? " · " : "", item.code ? h("span", { "class": "bc-nowrap" }, item.code) : null]),
          item.demo ? h("span", { "class": "bk-tag bk-tag--demo" }, t("common.demo")) : null,
          item.relation === "metoo" ? h("p", { "class": "bc-meta" }, t("mine.metoo_badge")) : null,
          h("p", { "class": "bc-meta" }, t("mine.reporters", { n: item.reporters || 1 })),
          overdue ? h("p", { "class": "bc-overdue" }, [icon("clock"), h("span", {}, t("mine.overdue"))]) : null,
          stepsBar(item)]));
      });
      body.appendChild(list);
    }

    // ---------------------------------------------------------------- каркас панели
    function render() {
      if (!state) return;
      var panel = els.panel;
      panel.innerHTML = "";
      var mine = state.view === "mine";
      // Шаг 2 на телефоне: пока места нет — низкая шторка (вопрос и «Моё местоположение»), карта почти вся видна
      // (R11 B1 №2); когда пришли варианты — до половины; дальше — полная.
      var snap = mine || state.step !== 2 ? "full" : (state.candidates || state.candidatesLoading ? "half" : "peek");
      panel.setAttribute("data-snap", snap);
      panel.setAttribute("data-step", mine ? "mine" : String(state.step));
      var canBack = !mine && state.step > 2 && state.step < 5;
      var head = h("header", { "class": "bc-head" }, [
        canBack ? h("button", { "class": "bk-btn bk-btn--ghost bc-back", type: "button", onclick: back },
          [icon("back"), h("span", {}, t("complaint.wizard.back"))]) : h("span", { "class": "bc-head__spacer" }),
        h("button", { "class": "bk-btn bk-btn--ghost bc-close", type: "button", "aria-label": t("complaint.wizard.close"),
                      onclick: close }, [icon("close"), h("span", { "class": "bc-close__label" }, t("complaint.wizard.close"))])]);
      panel.appendChild(h("div", { "class": "bc-handle", "aria-hidden": "true" }));
      panel.appendChild(head);
      if (!mine) {
        var dots = h("div", { "class": "bk-wizard" }, [h("span", { "class": "bk-wizard__label" },
          t("complaint.wizard.step", { n: state.step, total: TOTAL_STEPS }))]);
        var track = h("span", { "class": "bk-wizard__dots", "aria-hidden": "true" });
        for (var i = 1; i <= TOTAL_STEPS; i++) track.appendChild(h("span", { "data-state": i < state.step ? "done" : (i === state.step ? "current" : "todo") }));
        dots.appendChild(track);
        panel.appendChild(dots);
      }
      var titles = { 2: "complaint.step2.title", 3: "complaint.step3.title", 4: "complaint.step4.title", 5: "complaint.step5.title" };
      var title = mine ? (state.mine && state.mine.length ? t("mine.count", { n: state.mine.length }) : t("mine.title"))
        : (state.step === 4 ? t("complaint.step4.title", { n: state.similar.reporters })
          : (state.step === 5 && state.result.kind === "metoo" ? t("complaint.step5.metoo_title") : t(titles[state.step])));
      panel.appendChild(h("h2", { id: "bc-title", "class": "bc-title", tabindex: "-1" }, title));
      var body = h("div", { "class": "bc-body" });
      panel.appendChild(body);
      if (mine) renderMine(body);
      else if (state.step === 2) renderPlace(body);
      else if (state.step === 3) renderText(body);
      else if (state.step === 4) renderSimilar(body);
      else renderDone(body);
      setPicking(!mine && state.step === 2);
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
      if (state.step === 4) state.step = 3;
      else if (state.step === 3) { state.step = 2; state.candidatesLoading = false; }
      render();
    }

    function open() {
      var keepText = state && state.view === "wizard" && state.step < 5 ? state : null;
      state = keepText || freshState();
      state.view = "wizard";
      if (state.step === 5) state = freshState();
      els.textarea = null;
      // Сначала рисуем (высота шторки уже нужная), потом показываем — без прыжка «полная → половина».
      render();
      els.panel.hidden = false;
      els.fab.hidden = true;
      document.documentElement.classList.add("bc-open");
      focusTitle();
    }

    function openMine() {
      if (!state) state = freshState();
      if (state.step === 5) { var keep = freshState(); keep.mine = null; state = keep; }
      state.view = "mine";
      if (map.clear) map.clear();
      loadMine();
      els.panel.hidden = false;
      els.fab.hidden = true;
      document.documentElement.classList.add("bc-open");
      focusTitle();
    }

    function close() {
      setPicking(false);
      if (map.clear) map.clear();
      els.panel.hidden = true;
      els.fab.hidden = opts.fab === false;
      document.documentElement.classList.remove("bc-open");
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

    return {
      open: open, openMine: openMine, close: close, relabel: relabel,
      state: function () { return state; },
      destroy: function () {
        setPicking(false);
        document.removeEventListener("keydown", onKey);
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
    t: t, pluralForm: pluralForm, residentSteps: residentSteps, formatDate: formatDate, version: "r09-round14-1"
  };
})();
