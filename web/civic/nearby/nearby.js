/*
 * Birge · «Что делают рядом» (R08, волна 2 п. 4) — раздел жителя «Рядом» (меню жителя, пункт 3; схема R11 IA_WAVE2 §4).
 *
 *   <link rel="stylesheet" href="/civic/nearby/nearby.css">
 *   <script src="/civic/i18n/i18n.js"></script>
 *   <script src="/civic/nearby/nearby.js"></script>
 *   BirgeNearby.mount(document.getElementById("nearby"), { apiBase: "/api/civic/v2", titleTag: "h1" });
 *   Опции: mapHref ("/#target={kind}:{id}&days=7"; у объекта R06 — objectHref, по умолчанию null: оболочка пока не
 *   показывает карточку объекта по #object=, кнопку «На карте» у объекта не рисуем), district (по умолчанию — запомненный).
 *   В оболочке R01 (INTEGRATION R01 §11.2, раздел #nearby): api.v2 — клиент шлюза, openTarget(kind, id, days) —
 *   показать цель на карте; handle.setLang(lang), handle.destroy().
 *
 * Данные: GET {apiBase}/nearby?district=<id> (ui/civic_akim/nearby.py): вкладки now | done | planned | outages,
 * баннеры отключений (≤ 2). Подписка: POST {apiBase}/nearby/subscriptions {device_id, scope: district|item, id, on}
 * (device_id — тот же, что у мастера жалобы R09: localStorage "birge.device"). События подписки показывает R09
 * в «Мои обращения → Что изменилось».
 * Правила R11 §4: только выбранный район (без ленты города), без запроса геолокации, без карты внутри экрана,
 * задержки показываем («срок перенесён»), у отключения — зона, время, обход, источник, «обновлено N мин назад».
 * Одна главная кнопка — «Следить за районом» (если подписки нет). Карточка свёрнута; «Зачем?» раскрывает 4 строки.
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var DISTRICTS = ["almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"];
  var TABS = ["now", "done", "planned", "outages"];
  var DISTRICT_KEY = "birge.nearby.district";
  var DEVICE_KEY = "birge.device"; // как у R09 (web/civic/feedback/complaint.js)
  var SUBS_KEY = "birge.nearby.subs";
  var ASTANA_MS = 5 * 3600 * 1000;
  var scriptBase = ((doc.currentScript && doc.currentScript.src) || "").replace(/[^/]*$/, "");
  var ICONS = scriptBase + "../ui-kit/icons.svg";
  var UTILITY_ICON = { water: "droplet", heating: "alert", power: "bulb", gas: "wind", road_closure: "road" };

  // Ключи, которых пока нет в словаре R11 (запас до слияния; список для R11 — INTEGRATION.txt §8).
  var KEYS = {
    ru: {
      "nearby.subscribe_district": "Следить за районом",
      "nearby.subscribed_district": "Вы следите за районом {name}",
      "nearby.unsubscribe": "Отписаться",
      "nearby.notify_hint": "Изменения появятся в «Моих обращениях»",
      "nearby.subscribe_error": "Не получилось — попробуйте ещё раз",
      "nearby.done_on": "завершено {date}",
      "nearby.starts": "начало {date}",
      "nearby.utility.water": "Вода",
      "nearby.utility.heating": "Тепло",
      "nearby.utility.power": "Свет",
      "nearby.utility.gas": "Газ",
      "nearby.utility.road_closure": "Перекрытие",
      "common.time.tomorrow": "завтра",
      "common.time.minutes_ago": { one: "{n} минуту назад", few: "{n} минуты назад", many: "{n} минут назад" },
      "common.time.hours_ago": { one: "{n} час назад", few: "{n} часа назад", many: "{n} часов назад" },
    },
    kk: {
      "nearby.subscribe_district": "Ауданды бақылау",
      "nearby.subscribed_district": "Сіз {name} ауданын бақылап отырсыз",
      "nearby.unsubscribe": "Жазылымнан шығу",
      "nearby.notify_hint": "Өзгерістер «Менің өтініштерім» бөлімінде көрінеді",
      "nearby.subscribe_error": "Болмады — қайталап көріңіз",
      "nearby.done_on": "{date} аяқталды",
      "nearby.starts": "басталуы: {date}",
      "nearby.utility.water": "Су",
      "nearby.utility.heating": "Жылу",
      "nearby.utility.power": "Жарық",
      "nearby.utility.gas": "Газ",
      "nearby.utility.road_closure": "Жол жабылады",
      "common.time.tomorrow": "ертең",
      "common.time.minutes_ago": "{n} минут бұрын",
      "common.time.hours_ago": "{n} сағат бұрын",
    },
  };

  function I() {
    return root.BirgeI18n;
  }
  function lang() {
    return I() ? I().getLang() : "ru";
  }
  function num(n) {
    return I() ? I().formatNumber(n) : String(n);
  }
  function tr(key, params) {
    var i18n = I();
    if (i18n && (i18n.has(key) || i18n.has(key, "ru"))) return i18n.t(key, params);
    var l = lang() === "kk" ? "kk" : "ru";
    var v = KEYS[l][key] != null ? KEYS[l][key] : KEYS.ru[key];
    if (v == null) return i18n ? i18n.t(key, params) : key;
    if (typeof v === "object") {
      var n = params && params.n != null ? Number(params.n) : 0;
      v = v[i18n ? i18n.plural(l, n) : "many"] || v.other || v.many;
    }
    return String(v).replace(/\{(\w+)\}/g, function (w, name) {
      if (!params || params[name] == null) return w;
      return typeof params[name] === "number" ? num(params[name]) : String(params[name]);
    });
  }
  function h(tag, attrs, children) {
    var el = doc.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === "text") el.textContent = v;
      else if (k === "class") el.className = v;
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    (children || []).forEach(function (c) {
      if (c != null && c !== false) el.appendChild(typeof c === "string" ? doc.createTextNode(c) : c);
    });
    return el;
  }
  // Состояние «нет связи» — маленькая монохромная иконка набора R11 (≤ 48 px), без больших иллюстраций
  // (поправка владельца П1 «Без ИИ-слопа», правило 2).
  function stateIcon(name) {
    var svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "ic nearby-state-ic");
    svg.setAttribute("aria-hidden", "true");
    var use = doc.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", ICONS + "#i-" + name);
    svg.appendChild(use);
    return svg;
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
  function store(kind, key, value) {
    try {
      if (value === undefined) return root.localStorage.getItem(key);
      if (value === null) root.localStorage.removeItem(key);
      else root.localStorage.setItem(key, value);
    } catch (e) {
      return null; // приватный режим — работаем без памяти
    }
    return null;
  }
  function deviceId() {
    var id = store("get", DEVICE_KEY);
    if (!id || !/^[A-Za-z0-9_-]{16,80}$/.test(id)) {
      var bytes = new Uint8Array(12);
      (root.crypto || {}).getRandomValues ? root.crypto.getRandomValues(bytes) : bytes.forEach(function (_, i) { bytes[i] = Math.floor(Math.random() * 256); });
      id = "d-" + Array.prototype.map.call(bytes, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
      store("set", DEVICE_KEY, id);
    }
    return id;
  }
  function label(x, base) {
    var l = lang();
    return x[base + "_" + l] || x[base + "_ru"] || "";
  }
  function astanaDay(iso) {
    return new Date(new Date(iso).getTime() + ASTANA_MS).toISOString().slice(0, 10);
  }
  function dayWord(iso) {
    var today = new Date(Date.now() + ASTANA_MS).toISOString().slice(0, 10);
    var tomorrow = new Date(Date.now() + ASTANA_MS + 86400000).toISOString().slice(0, 10);
    var d = astanaDay(iso);
    if (d === today) return tr("common.time.today");
    if (d === tomorrow) return tr("common.time.tomorrow");
    return I().formatDate(iso);
  }
  function timeRange(x) {
    // «завтра 10:00–16:00»; ночное перекрытие — «14 окт 22:00–06:00»
    return dayWord(x.start) + " " + I().formatTime(x.start) + "–" + I().formatTime(x.end);
  }
  function ago(min) {
    if (min == null) return "";
    if (min < 60) return tr("common.time.minutes_ago", { n: Math.max(1, min) });
    if (min < 24 * 60) return tr("common.time.hours_ago", { n: Math.floor(min / 60) });
    return I().formatRelative(new Date(Date.now() - min * 60000).toISOString());
  }
  // Вид объекта R06 → вид работ из словаря R11 (works.kind.*): у объектов свои виды (school, road, square…).
  var KIND_MAP = {
    road: "roadworks", roadworks: "roadworks", sidewalk: "roadworks",
    school: "construction", kindergarten: "construction", clinic: "construction", building: "construction",
    construction: "construction", stop: "construction",
    square: "landscaping", park: "landscaping", yard: "landscaping", playground: "landscaping", landscaping: "landscaping",
    event: "event",
  };
  function kindTag(x) {
    if (x.type === "outage") return tr("nearby.utility." + (x.utility || "water"));
    var k = KIND_MAP[x.work_kind] || x.work_kind;
    if (!k) return null;
    if (I().has("works.kind." + k)) return tr("works.kind." + k);
    if (I().has("object.kind." + k)) return tr("object.kind." + k);
    return null;
  }

  function mount(rootEl, options) {
    var opts = { apiBase: "/api/civic/v2", titleTag: "h1", mapHref: "/#target={kind}:{id}&days=7", objectHref: null };
    Object.keys(options || {}).forEach(function (k) {
      if (options[k] !== undefined) opts[k] = options[k];
    });
    var saved = store("get", DISTRICT_KEY);
    var state = {
      district: DISTRICTS.indexOf(opts.district) >= 0 ? opts.district : DISTRICTS.indexOf(saved) >= 0 ? saved : "nura",
      tab: "now",
      status: "loading",
      data: null,
      subs: readSubs(),
      message: "",
      request: 0,
    };
    rootEl.classList.add("nb");
    var api = opts.api && typeof opts.api.v2 === "function" ? opts.api.v2 : null;
    // Запрос к API: клиент оболочки R01 (тот же шлюз, ошибки «network») или fetch на отдельной странице.
    function request(method, path, body) {
      if (api) return Promise.resolve().then(function () { return api(method, path, body); });
      return fetch(opts.apiBase + path, {
        method: method,
        credentials: "same-origin",
        headers: body !== undefined ? { Accept: "application/json", "Content-Type": "application/json" } : { Accept: "application/json" },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      }).then(function (r) {
        return r.ok ? r.json() : Promise.reject(r.status);
      });
    }

    function readSubs() {
      try {
        var v = JSON.parse(store("get", SUBS_KEY) || "[]");
        return Array.isArray(v) ? v : [];
      } catch (e) {
        return [];
      }
    }
    function isSub(scope, id) {
      return state.subs.some(function (s) {
        return s.scope === scope && s.id === id;
      });
    }
    function setSub(scope, id, on) {
      state.message = "";
      return request("POST", "/nearby/subscriptions", { device_id: deviceId(), scope: scope, id: id, on: on })
        .then(function (b) {
          state.subs = (b.items || []).map(function (s) {
            return { scope: s.scope, id: s.id };
          });
          store("set", SUBS_KEY, JSON.stringify(state.subs));
        })
        .catch(function () {
          state.message = tr("nearby.subscribe_error");
        })
        .then(function () {
          var key = (doc.activeElement && doc.activeElement.getAttribute("data-key")) || null;
          render();
          var again = key && rootEl.querySelector('[data-key="' + key + '"]');
          if (again) again.focus();
        });
    }

    function load() {
      var id = ++state.request;
      // Смена района при показанной ленте — без мигания скелетом: прежнее приглушено, полоса загрузки (как в «Картине дня»).
      state.keep = state.status === "ok" && !!state.data;
      state.status = "loading";
      render();
      request("GET", "/nearby?district=" + encodeURIComponent(state.district))
        .then(function (d) {
          if (id !== state.request) return;
          state.data = d;
          state.status = "ok";
          state.keep = false;
          // Первая непустая вкладка, если в выбранной пусто (житель не видит пустую ленту при полном районе).
          if (!d.tabs[state.tab]) {
            var first = TABS.filter(function (t) {
              return d.tabs[t];
            })[0];
            if (first) state.tab = first;
          }
          render();
        })
        .catch(function () {
          if (id !== state.request) return;
          state.status = "error";
          state.keep = false;
          render();
        });
    }

    function card(x) {
      var tag = kindTag(x);
      var head = h("p", { class: "nb-card__eyebrow" }, [
        tag ? h("span", { class: "nb-card__kind" }, [x.type === "outage" ? icon(UTILITY_ICON[x.utility] || "alert", 18) : null, tag]) : null,
      ]);
      var lines = [];
      if (x.type === "outage") {
        lines.push(h("p", { class: "nb-card__when", text: tr("nearby.outage.time", { text: timeRange(x) }) }));
        if (label(x, "zone")) lines.push(h("p", { text: tr("nearby.outage.zone", { text: label(x, "zone") }) }));
        if (label(x, "detour") && label(x, "detour") !== "—") lines.push(h("p", { text: tr("nearby.outage.detour", { text: label(x, "detour") }) }));
        var src = x.source ? (I().has("service." + x.source) ? tr("service." + x.source) : x.source) : null;
        lines.push(
          h("p", { class: "bk-meta" }, [
            src ? tr("nearby.outage.source", { text: src }) + " · " : "",
            tr("nearby.updated", { ago: ago(x.updated_min_ago) }),
          ])
        );
      } else {
        var status = x.status === "in_progress" ? "works.status.in_progress" : x.status === "done" ? "works.status.completed" : "works.status.planned";
        var end = x.forecast_end || x.planned_end || x.end;
        var when =
          x.status === "done" && end ? tr("nearby.done_on", { date: I().formatDate(end) })
            : x.status === "planned" && x.start ? tr("nearby.starts", { date: I().formatDate(x.start) })
            : end ? tr("works.until", { date: I().formatDate(end) }) : tr("works.no_dates");
        lines.push(
          h("p", { class: "nb-card__status" }, [
            h("span", { class: "nb-card__status-word", text: tr(status) }),
            " · " + when,
            // Задержка — словом в той же строке, без плашки (чистый стиль R11 §2.5).
            x.delayed && x.status !== "done" ? " · " : null,
            x.delayed && x.status !== "done" ? h("span", { class: "nb-card__late", text: tr("works.shift_later") }) : null,
          ])
        );
        if (x.updated_min_ago != null) lines.push(h("p", { class: "bk-meta", text: tr("nearby.updated", { ago: ago(x.updated_min_ago) }) }));
      }
      var why = null;
      if (x.why) {
        var l = lang();
        var rows = ["problem", "reason", "result", "inconvenience"]
          .filter(function (k) {
            return x.why[k + "_" + l] || x.why[k + "_ru"];
          })
          .map(function (k) {
            return [h("dt", { text: tr("nearby.why." + k) }), h("dd", { text: x.why[k + "_" + l] || x.why[k + "_ru"] })];
          });
        why = h("details", { class: "bk-details nb-why" }, [
          h("summary", { "data-key": "why:" + x.id, text: tr("nearby.why") }),
          h("dl", null, [].concat.apply([], rows)),
        ]);
      }
      var actions = [];
      var href = null;
      if (x.target && x.target.kind === "object") href = opts.objectHref ? opts.objectHref.replace("{id}", encodeURIComponent(x.target.id)) : null;
      else if (x.target) href = opts.mapHref.replace("{kind}", encodeURIComponent(x.target.kind)).replace("{id}", encodeURIComponent(x.target.id));
      if (href)
        actions.push(
          h(
            "a",
            {
              class: "bk-btn bk-btn--ghost nb-card__map",
              href: href,
              onclick: function (e) {
                // В оболочке R01 — её переход на карту с карточкой цели (openTarget), а не перезагрузка страницы.
                if (typeof opts.openTarget === "function" && x.target && x.target.kind !== "object") {
                  e.preventDefault();
                  opts.openTarget(x.target.kind, x.target.id, 7);
                }
              },
            },
            [icon("pin", 18), tr("map.card.on_map")]
          )
        );
      var subbed = isSub("item", x.id);
      actions.push(
        h(
          "button",
          {
            type: "button",
            class: "bk-btn bk-btn--ghost nb-card__sub",
            "data-key": "sub:" + x.id,
            "aria-pressed": subbed ? "true" : "false",
            onclick: function () {
              setSub("item", x.id, !subbed);
            },
          },
          [icon(subbed ? "check" : "plus", 18), tr(subbed ? "nearby.subscribed" : "nearby.subscribe")]
        )
      );
      // Строка списка с линией между строками, не карточка в панели (чистый стиль R11 §2.3).
      return h("li", { class: "nb-card", "data-key": "card:" + x.id, "data-tab": x.tab }, [
        head,
        h("h3", { class: "nb-card__title", text: label(x, "title") }),
      ].concat(lines, [why, h("div", { class: "nb-card__actions" }, actions)]));
    }

    var fadeTab = false;
    // Словарь ещё грузится (оболочка открыла #nearby сразу по адресу и уже зовёт setLang/render) — рисуем только
    // скелет без слов: иначе мелькают ключи без перевода и в консоли «неизвестный ключ» (R01 r14_wave2, INFO).
    var textReady = !I();
    function render() {
      rootEl.textContent = "";
      if (!textReady) {
        rootEl.setAttribute("data-state", "loading");
        rootEl.appendChild(
          h("div", { class: "bk-card nb-loading", "aria-hidden": "true" }, [
            h("div", { class: "bk-skel bk-skel--title" }),
            h("div", { class: "bk-skel bk-skel--line" }),
            h("div", { class: "bk-skel bk-skel--line" }),
          ])
        );
        return;
      }
      rootEl.setAttribute("data-state", state.status);
      var tagName = /^h[1-3]$/.test(opts.titleTag) ? opts.titleTag : "h1";
      rootEl.appendChild(h(tagName, { class: "nb__title", text: tr("nearby.title") }));
      var select = h(
        "select",
        {
          id: "nb-district",
          class: "nb__select",
          onchange: function (e) {
            state.district = e.target.value;
            store("set", DISTRICT_KEY, state.district);
            load();
          },
        },
        DISTRICTS.map(function (d) {
          return h("option", { value: d, text: tr("district." + d), selected: d === state.district });
        })
      );
      // Поле района — с заливкой ui-kit (.bk-field), без рамки.
      rootEl.appendChild(
        h("label", { class: "bk-field nb__district", for: "nb-district" }, [
          h("span", { class: "bk-field__label nb__district-label", text: tr("heat.filter.district") }),
          select,
        ])
      );
      var pending = state.status === "loading" && state.keep && !!state.data;
      if (pending) rootEl.setAttribute("data-pending", "");
      else rootEl.removeAttribute("data-pending");
      if (state.status === "loading" && !pending) {
        // Скелет той же формы, что лента: строка вкладок и две строки (дизайн-марафон, чек-лист п. 8).
        rootEl.appendChild(
          h("div", { class: "nb-loading", role: "status", "aria-label": tr("nearby.title") }, [
            h("div", { class: "bk-skel nb-skel__tabs" }),
            h("div", { class: "nb-skel__row" }, [h("div", { class: "bk-skel nb-skel__eyebrow" }), h("div", { class: "bk-skel bk-skel--title" }), h("div", { class: "bk-skel bk-skel--line" })]),
            h("div", { class: "nb-skel__row" }, [h("div", { class: "bk-skel nb-skel__eyebrow" }), h("div", { class: "bk-skel bk-skel--title" }), h("div", { class: "bk-skel bk-skel--line" })]),
          ])
        );
        return;
      }
      if (state.status === "error") {
        rootEl.appendChild(
          // «Нет связи» как у остальных разделов (R11 марафон §10): маленькая иконка R11 (П1), без карточки, обычная кнопка.
          h("div", { class: "bk-error", role: "alert" }, [
            stateIcon("wifi-off"),
            h("p", { class: "bk-error__title", text: tr("common.state.network_title") }),
            h("p", { class: "bk-error__text", text: tr("common.state.network_text") }),
            h("button", { type: "button", class: "bk-btn", onclick: load }, [icon("refresh"), tr("common.action.retry")]),
          ])
        );
        return;
      }
      var d = state.data;
      // Баннеры отключений: идут сейчас или завтра, не больше 2.
      (d.banners || []).forEach(function (b) {
        rootEl.appendChild(
          h("section", { class: "bk-banner bk-banner--warn nb-banner", "aria-label": label(b, "title") }, [
            h("p", { class: "bk-banner__title" }, [icon(UTILITY_ICON[b.utility] || "alert"), label(b, "title") + " · " + timeRange(b)]),
            label(b, "zone") ? h("p", { class: "nb-banner__zone", text: tr("nearby.outage.zone", { text: label(b, "zone") }) }) : null,
            h("p", { class: "bk-banner__note" }, [
              b.source && I().has("service." + b.source) ? tr("nearby.outage.source", { text: tr("service." + b.source) }) + " · " : "",
              tr("nearby.updated", { ago: ago(b.updated_min_ago) }),
            ]),
          ])
        );
      });
      // Вкладки — .bk-tabs ui-kit (разбор R11 FINAL-3 п. 9): role=tab, стрелки ←/→ — BirgeUI.tabs, если он есть.
      function pickTab(t, focus) {
        if (!t || t === state.tab) return;
        state.tab = t;
        fadeTab = true;
        render();
        var again = rootEl.querySelector('[data-key="tab:' + t + '"]');
        if (again && focus) again.focus();
      }
      var seg = h(
        "div",
        { class: "bk-tabs nb-tabs", role: "tablist", "aria-label": tr("nearby.title") },
        TABS.map(function (t) {
          return h(
            "button",
            {
              type: "button",
              role: "tab",
              id: "nb-tab-" + t,
              "aria-controls": "nb-panel",
              "aria-selected": state.tab === t ? "true" : "false",
              tabindex: state.tab === t ? "0" : "-1",
              "data-key": "tab:" + t,
              "data-value": t,
            },
            [tr("nearby.tab." + t), d.tabs[t] ? h("span", { class: "bk-num nb-tabs__count", text: num(d.tabs[t]) }) : null]
          );
        })
      );
      var UI = root.BirgeUI;
      if (UI && typeof UI.tabs === "function")
        UI.tabs(seg, function (t) {
          pickTab(t, true);
        });
      else
        seg.addEventListener("click", function (e) {
          var b = e.target.closest && e.target.closest('[role="tab"]');
          if (b) pickTab(b.getAttribute("data-value"), true);
        });
      rootEl.appendChild(seg);
      var items = (d.items || []).filter(function (x) {
        return x.tab === state.tab;
      });
      // Смена вкладки — список мягко проявляется (220 мс); подписка и язык перерисовывают без движения.
      var panel = h("div", { id: "nb-panel", role: "tabpanel", "aria-labelledby": "nb-tab-" + state.tab, "data-enter": fadeTab ? "" : null });
      fadeTab = false;
      if (!items.length) {
        panel.appendChild(h("div", { class: "bk-empty nb-empty" }, [icon("check", 48), h("p", { class: "bk-empty__title", text: tr("nearby.empty") })]));
      } else {
        var list = h("ul", { class: "nb-list" });
        items.forEach(function (x) {
          list.appendChild(card(x));
        });
        panel.appendChild(list);
      }
      rootEl.appendChild(panel);
      // Главная кнопка экрана — подписка на район; подписан — строка и «Отписаться» (второстепенная).
      var subbed = isSub("district", state.district);
      var name = tr("district." + state.district);
      rootEl.appendChild(
        h("div", { class: "nb-follow" }, [
          subbed
            ? h("p", { class: "nb-follow__done" }, [icon("check", 18), tr("nearby.subscribed_district", { name: name })])
            : null,
          h(
            "button",
            {
              type: "button",
              "data-key": "follow",
              class: subbed ? "bk-btn" : "bk-btn bk-btn--primary",
              onclick: function () {
                setSub("district", state.district, !subbed);
              },
            },
            subbed ? [tr("nearby.unsubscribe")] : [icon("plus", 18), tr("nearby.subscribe_district")]
          ),
          h("p", { class: "bk-meta nb-follow__hint", text: tr("nearby.notify_hint") }),
          state.message ? h("p", { class: "nb-follow__error", role: "alert", text: state.message }) : null,
        ])
      );
      // «Пример» — одна серая строка внизу, а не метка у каждой карточки (чистый стиль R11 §2.9).
      if (d.demo || (d.banners || []).some(function (b) { return b.demo; }))
        rootEl.appendChild(h("p", { class: "bk-footnote nb-demo", text: tr("common.tag.demo_hint") }));
    }

    var off = null;
    (I() ? I().ready : Promise.resolve()).then(function () {
      textReady = true;
      if (I()) off = I().onChange(render);
      load();
    });
    var handle = {
      reload: load,
      setLang: function () {
        render(); // язык уже сменил BirgeI18n; перерисовать подписи
      },
      setDistrict: function (d) {
        if (DISTRICTS.indexOf(d) >= 0) {
          state.district = d;
          load();
        }
      },
      get state() {
        return { district: state.district, tab: state.tab, status: state.status };
      },
      destroy: function () {
        if (off) off();
        state.request++;
        rootEl.textContent = "";
        delete rootEl.birgeNearby;
      },
    };
    rootEl.birgeNearby = handle;
    return handle;
  }

  root.BirgeNearby = { mount: mount, version: "nearby-r14-clean" };
})(window);
