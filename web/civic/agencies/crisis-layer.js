/*
 * Birge · слой карты «Кризис» и баннер жителям зоны (R17, раунд 15; VISUAL_BRIEF «вау» №5).
 *
 *   <script defer src="/civic/agencies/crisis-layer.js"></script>   (после birge.js и agencies.js)
 *   BirgeCrisisLayer.focus(id)   — «Показать на карте» из штаба: раздел «Карта», слой «Кризис», камера на зону
 *   BirgeCrisisLayer.refresh()   — перечитать идущие кризисы (после создания/закрытия в штабе)
 *
 * Слой — через BirgeShell.registerLayer (по умолчанию выключен; одновременно один дополнительный слой, CONTRACT §8).
 * Зона — контур района или дворов из OSM (сервер отдаёт форму в GET incidents/{id}); полигонов «от руки» нет.
 * Зона мягко «дышит» (прозрачность заливки 0.08 ↔ 0.2, 2.4 с); prefers-reduced-motion — без движения.
 * Слои ставятся ПОД значки тепловой карты R07: жалобы остаются главными.
 *
 * Баннер жителю (вид «Житель», раздел «Карта»; IA_ROUND15 §5.12): идущий кризис, если (а) сервер знает, что зона — его
 * (двор R16 или подписка R08 на район: GET incidents/updates с X-Birge-Device), или (б) житель сейчас смотрит на зону
 * (центр карты в её границах, масштаб ≥ 11). Одна строка «Буран в Нуре: <последнее обновление>», точка-пульс раз в 2 с,
 * «Подробнее» → раздел #crisis/<id> (публичная карточка, BirgeAgencies.mount section "crisis"); оболочка без раздела —
 * своя карточка. «Скрыть» — до конца сессии. Место — BirgeShell.alertSlot() (R01, §7.9), иначе свой контейнер.
 * Ссылка #incident=<id> (прежний вид) открывает ту же карточку.
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var API = "/api/civic/v2";
  var SRC = "r17-crisis";
  var LAYERS = ["r17-crisis-fill", "r17-crisis-line", "r17-crisis-point"];
  var COLOR = "#1f5fa8";            // --c-info ui-kit: синий — не цвет тепловой карты и не «исправлено»
  var POLL_MS = 60000;
  var DEVICE_KEY = "birge.device";  // тот же id устройства, что у R09, R08, R13 (localStorage)
  var HIDDEN_KEY = "birge.crisis.hidden";
  var SPRITE = ((doc.currentScript && doc.currentScript.src) || "").replace(/[^/]*$/, "") + "../ui-kit/icons.svg";
  var TEXT = {
    ru: { layer: "Кризис", more: "Подробнее", close: "Скрыть", zone: "Зона: {zone}", updates: "Обновления служб",
      none: "Пока без обновлений", show: "Показать зону", demo: "Пример", since: "с {time}", closed: "Кризис закрыт" },
    kk: { layer: "Төтенше жағдай", more: "Толығырақ", close: "Жасыру", zone: "Аймақ: {zone}", updates: "Қызметтердің жаңартулары",
      none: "Әзірге жаңарту жоқ", show: "Аймақты көрсету", demo: "Мысал", since: "{time} бастап", closed: "Төтенше жағдай аяқталды" },
  };

  var state = { incidents: [], details: {}, on: false, map: null, pulse: null, timer: null, banner: null, card: null,
    mine: {}, lastKey: "", label: null };

  function I() { return root.BirgeI18n || null; }
  function lang() { var i = I(); return i && i.getLang && i.getLang() === "kk" ? "kk" : "ru"; }
  function tr(key, params) {
    var i = I(), full = "crisis.map." + key;
    var text = i && i.has && i.has(full) ? i.t(full, params) : (TEXT[lang()] || TEXT.ru)[key] || key;
    return String(text).replace(/\{(\w+)\}/g, function (w, n) { return params && params[n] != null ? String(params[n]) : w; });
  }
  function pick(obj, base) {
    if (!obj) return "";
    var l = lang();
    return obj[base + "_" + l] || obj[base + "_" + (l === "kk" ? "ru" : "kk")] || "";
  }
  function fmtTime(iso) {
    var t = Date.parse(iso);
    if (!isFinite(t)) return "";
    var d = new Date(t + 5 * 3600000), pad = function (n) { return (n < 10 ? "0" : "") + n; };
    var i = I();
    var day = i && i.formatDate ? i.formatDate(iso) : d.getUTCDate() + "." + pad(d.getUTCMonth() + 1);
    return day + ", " + pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes());
  }
  function reducedMotion() {
    return root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }
  function h(tag, attrs, children) {
    var el = doc.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === "text") el.textContent = v;
      else if (k === "class") el.className = v;
      else if (k.slice(0, 2) === "on" && typeof v === "function") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    (children || []).forEach(function (c) { if (c != null && c !== false) el.appendChild(typeof c === "string" ? doc.createTextNode(c) : c); });
    return el;
  }
  function svg(id) {
    var NS = "http://www.w3.org/2000/svg", s = doc.createElementNS(NS, "svg"), use = doc.createElementNS(NS, "use");
    s.setAttribute("class", "ic");
    s.setAttribute("aria-hidden", "true");
    s.setAttribute("focusable", "false");
    use.setAttribute("href", SPRITE + "#" + id);
    s.appendChild(use);
    return s;
  }
  function device() {
    try {
      var id = root.localStorage.getItem(DEVICE_KEY);
      return id && /^[A-Za-z0-9_-]{16,80}$/.test(id) ? id : null;
    } catch (e) { return null; }
  }
  function hiddenSet() {
    try { return JSON.parse(root.sessionStorage.getItem(HIDDEN_KEY) || "[]"); } catch (e) { return []; }
  }
  function hide(id) {
    try { root.sessionStorage.setItem(HIDDEN_KEY, JSON.stringify(hiddenSet().concat([id]).slice(-20))); } catch (e) { /* без хранилища */ }
  }
  function get(path, headers) {
    return fetch(API + path, { headers: Object.assign({ Accept: "application/json" }, headers || {}), credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); });
  }
  function mapObject() {
    try { return typeof root.map !== "undefined" && root.map && typeof root.map.addLayer === "function" ? root.map : null; } catch (e) { return null; }
  }
  function globalMap() {
    // Карта MapLibre — глобальная переменная web/map.js (let map), не свойство window: берём через оболочку.
    try {
      // eslint-disable-next-line no-undef
      if (typeof map !== "undefined" && map && typeof map.addLayer === "function") return map;
    } catch (e) { /* нет карты */ }
    return mapObject();
  }

  // ------------------------------------------------------------------ данные
  function load() {
    return get("/incidents?status=active").then(function (d) {
      state.incidents = (d && d.items) || [];
      return Promise.all(state.incidents.map(function (inc) {
        return get("/incidents/" + encodeURIComponent(inc.id)).then(function (x) { state.details[inc.id] = x.incident; }, function () { /* без формы */ });
      }));
    }, function () { state.incidents = []; }).then(function () {
      var dev = device();
      if (!dev || !state.incidents.length) { state.mine = {}; return; }
      return get("/incidents/updates", { "X-Birge-Device": dev }).then(function (d) {
        var mine = {};
        ((d && d.items) || []).forEach(function (u) { mine[u.incident_id] = true; });
        state.mine = mine;
      }, function () { state.mine = {}; });
    }).then(function () {
      if (state.on) draw();
      renderBanner();
    });
  }

  // ------------------------------------------------------------------ слой карты
  function features() {
    var out = [];
    state.incidents.forEach(function (inc) {
      var detail = state.details[inc.id];
      ((detail && detail.geometry && detail.geometry.features) || []).forEach(function (f) {
        out.push({ type: "Feature", geometry: f.geometry, properties: { incident: inc.id, kind: (f.properties || {}).kind || "zone" } });
      });
    });
    return { type: "FeatureCollection", features: out };
  }
  function beforeId(m) {
    var layers = (m.getStyle() && m.getStyle().layers) || [];
    var heat = layers.filter(function (l) { return /^r07-heat/.test(l.id); })[0];
    if (heat) return heat.id;
    var sym = layers.filter(function (l) { return l.type === "symbol"; })[0];
    return sym ? sym.id : undefined;
  }
  function draw() {
    var m = globalMap();
    if (!m) return;
    state.map = m;
    var data = features();
    try {
      if (m.getSource(SRC)) m.getSource(SRC).setData(data);
      else {
        m.addSource(SRC, { type: "geojson", data: data });
        var before = beforeId(m);
        m.addLayer({ id: LAYERS[0], type: "fill", source: SRC, filter: ["==", ["geometry-type"], "Polygon"],
          paint: { "fill-color": COLOR, "fill-opacity": 0.14 } }, before);
        m.addLayer({ id: LAYERS[1], type: "line", source: SRC, filter: ["!=", ["geometry-type"], "Point"],
          paint: { "line-color": COLOR, "line-width": 2, "line-opacity": 0.85, "line-dasharray": [2, 1.5] } }, before);
        m.addLayer({ id: LAYERS[2], type: "circle", source: SRC, filter: ["==", ["geometry-type"], "Point"],
          paint: { "circle-color": COLOR, "circle-opacity": 0.25, "circle-radius": 14, "circle-stroke-color": COLOR,
            "circle-stroke-width": 2 } }, before);
      }
    } catch (e) {
      // Стиль ещё не разобран — повторим, когда карта загрузится.
      try { m.once("load", draw); } catch (x) { /* карты нет */ }
      return;
    }
    drawLabel(m);
    startPulse(m);
  }
  function clear() {
    var m = state.map || globalMap();
    stopPulse();
    if (state.label) { try { state.label.remove(); } catch (e) { /* уже убран */ } state.label = null; }
    if (!m) return;
    try {
      LAYERS.forEach(function (id) { if (m.getLayer(id)) m.removeLayer(id); });
      if (m.getSource(SRC)) m.removeSource(SRC);
    } catch (e) { /* стиль сменился — слоёв уже нет */ }
  }
  // Подпись зоны — HTML-метка (у запасного фона без интернета нет шрифтов для подписей MapLibre).
  function drawLabel(m) {
    if (state.label) { try { state.label.remove(); } catch (e) { /* */ } state.label = null; }
    var inc = state.incidents[0], detail = inc && state.details[inc.id];
    var gl = root.maplibregl;
    if (!inc || !detail || !detail.bbox || !gl || typeof gl.Marker !== "function") return;
    var b = detail.bbox;
    var el = h("div", { class: "bk-glass bk-glass--bar ag-zone-label" }, [svg("i-alert"), pick(inc, "title"),
      inc.demo ? h("span", { class: "ag-demo", text: tr("demo") }) : null]);
    el.style.cssText = "display:flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;font-size:13px;font-weight:600;color:#121a17;pointer-events:none";
    try { state.label = new gl.Marker({ element: el }).setLngLat([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]).addTo(m); } catch (e) { state.label = null; }
  }
  function startPulse(m) {
    stopPulse();
    if (reducedMotion()) return;
    var t0 = performance.now();
    var tick = function () {
      var phase = ((performance.now() - t0) % 2400) / 2400;
      var k = 0.5 - 0.5 * Math.cos(phase * Math.PI * 2);
      try {
        if (m.getLayer(LAYERS[0])) m.setPaintProperty(LAYERS[0], "fill-opacity", 0.08 + 0.12 * k);
        if (m.getLayer(LAYERS[2])) m.setPaintProperty(LAYERS[2], "circle-opacity", 0.15 + 0.2 * k);
      } catch (e) { stopPulse(); return; }
      state.pulse = setTimeout(tick, 80);      // ~12 кадров/с: плавно для «дыхания» и бережно к ноутбуку
    };
    tick();
  }
  function stopPulse() {
    if (state.pulse) clearTimeout(state.pulse);
    state.pulse = null;
  }
  function show() {
    state.on = true;
    load();
  }
  function hideLayer() {
    state.on = false;
    clear();
  }

  // ------------------------------------------------------------------ «Показать на карте» из штаба
  function focus(id) {
    var shell = root.BirgeShell;
    if (shell) {
      shell.setSection("map");
      if (shell.layer !== "crisis") shell.setLayer("crisis");
    }
    var go = function () {
      var detail = state.details[id];
      var m = globalMap();
      if (!detail || !detail.bbox || !m) return;
      var b = detail.bbox;
      try {
        m.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 80, duration: reducedMotion() ? 0 : 800, maxZoom: 15 });
      } catch (e) { /* карта ещё не готова */ }
    };
    if (state.details[id]) go();
    else load().then(go);
  }

  // ------------------------------------------------------------------ баннер жителю
  function relevant(inc) {
    if (hiddenSet().indexOf(inc.id) >= 0) return false;
    if (state.mine[inc.id]) return true;
    var detail = state.details[inc.id], m = globalMap();
    if (!detail || !detail.bbox || !m) return false;
    try {
      var c = m.getCenter(), b = detail.bbox;
      return m.getZoom() >= 11 && c.lng >= b[0] && c.lng <= b[2] && c.lat >= b[1] && c.lat <= b[3];
    } catch (e) { return false; }
  }
  function isResidentMap() {
    var d = doc.body && doc.body.dataset;
    return !!d && d.birgeMode === "resident" && (d.birgeSection || "map") === "map";
  }
  function bannerHost() {
    var shell = root.BirgeShell;
    if (shell && typeof shell.alertSlot === "function") {
      try { return { el: shell.alertSlot(), slot: true }; } catch (e) { /* оболочка без слота */ }
    }
    return { el: doc.body, slot: false };
  }
  // «Подробнее»: раздел оболочки #crisis/<id> (R01 раунда 15); если такого раздела нет — своя карточка поверх карты.
  function openPublic(id) {
    var shell = root.BirgeShell;
    if (shell && typeof shell.setSection === "function") {
      try { shell.setSection("crisis", { path: id }); } catch (e) { /* старая оболочка */ }
      if (shell.section === "crisis") return;
    }
    openCard(id);
  }
  function renderBanner() {
    var inc = isResidentMap() ? state.incidents.filter(relevant)[0] : null;
    var key = inc ? inc.id + "|" + lang() + "|" + ((inc.updates || [])[0] || {}).id : "";
    if (!inc) {
      if (state.banner) {
        state.banner.hidden = true;
        if (state.banner.parentNode && state.banner.parentNode.id === "birge-alert") state.banner.remove();
      }
      state.lastKey = "";
      return;
    }
    if (key === state.lastKey && state.banner && !state.banner.hidden && state.banner.isConnected) return;
    state.lastKey = key;
    var last = (inc.updates || [])[0];
    var host = bannerHost();
    var banner = state.banner || h("div", { class: "ag-banner bk-glass bk-glass--strong bk-app" });
    banner.classList.toggle("ag-banner--slot", host.slot);
    if (!host.slot) { banner.setAttribute("role", "status"); banner.setAttribute("aria-live", "polite"); }
    state.banner = banner;
    if (banner.parentNode !== host.el) {
      if (host.slot) host.el.replaceChildren(banner);   // в слоте — один баннер за раз
      else host.el.appendChild(banner);
    }
    banner.hidden = false;
    // Весь баннер — одна кнопка «Подробнее» (на телефоне подпись кнопки не помещается — остаётся стрелка), × — скрыть.
    banner.replaceChildren(
      h("button", { type: "button", class: "ag-banner__open", "aria-label": pick(inc, "title") + " — " + tr("more"),
        onclick: function () { openPublic(inc.id); } }, [
        h("span", { class: "ag-banner__dot", "aria-hidden": "true" }),
        h("span", { class: "ag-banner__main" }, [
          h("span", { class: "ag-banner__line" }, [h("strong", { text: pick(inc, "title") + (last ? ": " : "") }),
            last ? pick(last, "text") : ""]),
          inc.demo ? h("span", { class: "ag-demo", text: tr("demo") }) : null]),
        h("span", { class: "ag-banner__more" }, [h("span", { class: "ag-banner__more-text", text: tr("more") }), svg("i-chevron-right")])]),
      h("button", { type: "button", class: "ag-banner__close", "aria-label": tr("close"), title: tr("close"),
        onclick: function () { hide(inc.id); banner.hidden = true; } }, [svg("i-close")]));
  }
  function openCard(id) {
    var inc = state.details[id] || state.incidents.filter(function (x) { return x.id === id; })[0];
    if (!inc) {
      return get("/incidents/" + encodeURIComponent(id)).then(function (d) { state.details[id] = d.incident; openCard(id); }, function () { /* нет такого */ });
    }
    var card = state.card || h("section", { class: "ag-public bk-glass bk-glass--strong bk-app", role: "dialog", "aria-modal": "false" });
    state.card = card;
    if (!card.parentNode) doc.body.appendChild(card);
    var updates = inc.updates || [];
    var label = (inc.zone_label || {})[lang()] || "";
    var close = h("button", { type: "button", class: "ag-banner__close", "aria-label": tr("close"), onclick: closeCard }, [svg("i-close")]);
    card.setAttribute("aria-label", pick(inc, "title"));
    card.replaceChildren(
      h("div", { class: "ag-card__head" }, [
        h("span", { class: "ag-card__badge", "data-live": inc.status === "active" ? "" : null }, [svg("i-alert")]),
        h("div", { style: "flex:1;min-width:0" }, [
          h("h3", { class: "ag-card__title", text: pick(inc, "title") }),
          h("div", { class: "ag-card__sub" }, [label ? h("span", { text: tr("zone", { zone: label }) }) : null,
            h("span", { text: tr("since", { time: fmtTime(inc.started_at) }) }),
            inc.status === "closed" ? h("span", { text: tr("closed") }) : null,
            inc.demo ? h("span", { class: "ag-demo", text: tr("demo") }) : null])]),
        close]),
      h("p", { class: "ag-section-title", text: tr("updates") }),
      updates.length ? h("ul", { class: "ag-feed" }, updates.map(function (u) {
        return h("li", { class: "ag-upd" }, [h("div", { class: "ag-upd__meta" }, [h("span", { text: fmtTime(u.at) })]),
          h("p", { class: "ag-upd__text", text: pick(u, "text") })]);
      })) : h("p", { class: "ag-note", text: tr("none") }),
      inc.bbox ? h("div", { class: "ag-actions" }, [h("button", { type: "button", class: "bk-btn", onclick: function () {
        closeCard();
        focus(inc.id);
      } }, [svg("i-pin"), tr("show")])]) : null);
    card.hidden = false;
    close.focus();
  }
  function closeCard() {
    if (state.card) state.card.hidden = true;
  }
  doc.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && state.card && !state.card.hidden) closeCard();
  });
  // #crisis/<id> ведёт оболочка R01 раунда 15 (раздел «crisis»); старая оболочка его не знает — тогда своя карточка.
  // #incident=<id> — прежний вид ссылки (уведомления до 15 окт).
  function fromHash() {
    var hash = root.location.hash || "";
    var m = /^#incident=(inc-[a-z0-9-]{4,40})$/.exec(hash) || /^#crisis\/(inc-[a-z0-9-]{4,40})$/.exec(hash);
    if (!m) return;
    setTimeout(function () {
      var shell = root.BirgeShell;
      if (shell && shell.section === "crisis") return;
      openCard(m[1]);
    }, 0);
  }

  // ------------------------------------------------------------------ запуск
  function register() {
    var shell = root.BirgeShell;
    if (!shell || typeof shell.registerLayer !== "function") return;
    var spec = { id: "crisis", modes: ["akimat", "resident"], title: { ru: TEXT.ru.layer, kk: TEXT.kk.layer },
      show: show, hide: hideLayer };
    if (I() && I().has && I().has("shell.layers.crisis")) spec.titleKey = "shell.layers.crisis";
    shell.registerLayer(spec);
  }
  function watch() {
    // Баннер жителю: при смене вида/раздела/языка и раз в минуту (новое обновление службы).
    if (typeof MutationObserver === "function" && doc.body) {
      new MutationObserver(renderBanner).observe(doc.body, { attributes: true, attributeFilter: ["data-birge-mode", "data-birge-section"] });
    }
    if (I() && I().onChange) I().onChange(function () { state.lastKey = ""; renderBanner(); });
    var m = globalMap();
    if (m && m.on) m.on("moveend", renderBanner);
    else setTimeout(function () { var mm = globalMap(); if (mm && mm.on) mm.on("moveend", renderBanner); }, 3000);
    state.timer = setInterval(function () { if (!doc.hidden && (state.on || isResidentMap())) load(); }, POLL_MS);
  }
  function start() {
    register();
    watch();
    load();
    fromHash();
    root.addEventListener("hashchange", fromHash);
  }
  root.BirgeCrisisLayer = { focus: focus, refresh: load, openCard: openCard };
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", start);
  else start();
})(typeof self !== "undefined" ? self : this);
