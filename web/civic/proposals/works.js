/*
 * Birge · «Работы и отключения» — форма сотрудника для раздела жителя «Рядом» (R06 данные, волна 2 п. 4).
 * Акимат: «Ещё → Работы и отключения» (#works; SCREENS.works в birge.js R01 ищет window.BirgeWorks).
 *
 *   BirgeWorks.mount(root, {api: {v2}, titleTag}) → {destroy, setLang}
 * API: GET /works?district (список района с ревизиями), POST /works (новая), POST /works/{id} (правка целиком,
 * expected_revision), POST /works/{id}/remove. Названия служб — таблица служб R08 GET /akim/routing (только общие
 * названия: «Водоканал», «Теплосеть»; реальные организации не придумываем).
 *
 * Правила R11 (IA_WAVE2 §4) — и в форме, и на сервере: 4 строки «Зачем?» обязательны; у отключения — источник,
 * время начала и конца и «где». Задержки показываем: у работы — срок по плану и новый срок, если сдвинулся.
 * Тексты — на языке интерфейса; перевод — та же запись после переключения ҚАЗ / РУС.
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var API = "/api/civic/v2";
  var DISTRICTS = ["almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"];
  var DISTRICT_KEY = "birge.works.district";
  var WORK_STATUS = { in_progress: "nearby.tab.now", done: "nearby.tab.done", planned: "nearby.tab.planned" };
  var WORK_KINDS = ["roadworks", "construction", "landscaping", "lighting", "event", "other"];
  var UTILITIES = ["water", "heating", "power", "gas", "road_closure"];
  var WHY = ["problem", "reason", "result", "inconvenience"];
  var ASTANA_MS = 5 * 3600 * 1000;
  // Плитка-иллюстрация записи — значок ui-kit по виду работ / что отключат (дизайн-марафон).
  var KIND_ICON = { roadworks: "road", construction: "building", landscaping: "trees", lighting: "bulb", event: "calendar", other: "dots" };
  var UTILITY_ICON = { water: "droplet", heating: "droplet", power: "bulb", gas: "alert", road_closure: "road" };

  var KEYS = {
    ru: {
      "works.form.add": "Добавить запись",
      "works.form.new_title": "Новая запись для раздела «Рядом»",
      "works.form.edit_title": "Изменить запись",
      "works.form.type": "Что это",
      "works.form.type_work": "Работа",
      "works.form.type_outage": "Отключение или перекрытие",
      "works.form.status": "Стадия",
      "works.form.kind": "Вид работ",
      "works.form.utility": "Что отключат",
      "works.form.source": "Источник (служба)",
      "works.form.title": "Коротко: что происходит",
      "works.form.zone": "Где (улица, дома)",
      "works.form.detour": "Как обойти (по желанию)",
      "works.form.start": "Начало",
      "works.form.end": "Окончание",
      "works.form.planned_end": "Срок по плану",
      "works.form.forecast_end": "Новый срок, если сдвинулся (по желанию)",
      "works.form.why": "Зачем? — 4 строки, их увидят жители",
      "works.form.lang_hint": "Пишите на языке интерфейса. Перевод: переключите ҚАЗ / РУС и сохраните запись ещё раз.",
      "works.form.other_lang": "Текст записи пока только на другом языке — переведите поля или оставьте как есть.",
      "works.form.required": "Заполните это поле",
      "works.form.bad_time": "Окончание — позже начала и не дольше 14 дней",
      "works.form.bad_date": "Проверьте дату",
      "works.form.stale": "Запись уже изменил другой сотрудник — список обновлён",
      "works.form.remove": "Удалить",
      "works.form.remove_confirm": "Точно удалить",
      "works.form.removed": "Запись удалена",
      "works.form.empty": "В этом районе пока нет работ и отключений",
      "works.form.district": "Район",
      "works.form.until": "до {date}",
      "works.form.error": "Не получилось сохранить. Проверьте связь и повторите.",
    },
    kk: {
      "works.form.add": "Жазба қосу",
      "works.form.new_title": "«Маңайда» бөліміне жаңа жазба",
      "works.form.edit_title": "Жазбаны өзгерту",
      "works.form.type": "Бұл не",
      "works.form.type_work": "Жұмыс",
      "works.form.type_outage": "Өшіру немесе жол жабу",
      "works.form.status": "Кезеңі",
      "works.form.kind": "Жұмыс түрі",
      "works.form.utility": "Не өшіріледі",
      "works.form.source": "Дереккөз (қызмет)",
      "works.form.title": "Қысқаша: не болып жатыр",
      "works.form.zone": "Қай жерде (көше, үйлер)",
      "works.form.detour": "Қалай айналып өтуге болады (қаласаңыз)",
      "works.form.start": "Басталуы",
      "works.form.end": "Аяқталуы",
      "works.form.planned_end": "Жоспар бойынша мерзімі",
      "works.form.forecast_end": "Мерзімі ауысса — жаңа мерзімі (қаласаңыз)",
      "works.form.why": "Не үшін? — 4 жол, оларды тұрғындар көреді",
      "works.form.lang_hint": "Интерфейс тілінде жазыңыз. Аударма: ҚАЗ / РУС ауыстырып, жазбаны қайта сақтаңыз.",
      "works.form.other_lang": "Жазба мәтіні әзірге басқа тілде ғана — өрістерді аударыңыз немесе солай қалдырыңыз.",
      "works.form.required": "Бұл өрісті толтырыңыз",
      "works.form.bad_time": "Аяқталуы басталуынан кейін және 14 күннен аспауы керек",
      "works.form.bad_date": "Күнін тексеріңіз",
      "works.form.stale": "Жазбаны басқа қызметкер өзгертті — тізім жаңартылды",
      "works.form.remove": "Жою",
      "works.form.remove_confirm": "Нақты жою",
      "works.form.removed": "Жазба жойылды",
      "works.form.empty": "Бұл ауданда әзірге жұмыс пен өшіру жоқ",
      "works.form.district": "Аудан",
      "works.form.until": "мерзімі: {date}",
      "works.form.error": "Сақтау мүмкін болмады. Байланысты тексеріп, қайталаңыз.",
    },
  };

  function I() {
    return root.BirgeI18n || null;
  }
  function lang() {
    return I() && I().getLang() === "kk" ? "kk" : "ru";
  }
  function tr(key, params) {
    var i18n = I(), l = lang();
    if (i18n && i18n.has(key)) return i18n.t(key, params);
    var v = KEYS[l][key];
    if (v == null && i18n && i18n.has(key, "ru")) return i18n.t(key, params);
    if (v == null) v = KEYS.ru[key] != null ? KEYS.ru[key] : key;
    return String(v).replace(/\{(\w+)\}/g, function (w, n) { return params && params[n] != null ? String(params[n]) : w; });
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
  function icon(name) {
    var span = doc.createElement("span");
    span.innerHTML = root.BirgeUI ? root.BirgeUI.icon(name) : "";
    return span.firstChild || doc.createTextNode("");
  }
  function button(cls, label, ic, attrs) {
    return h("button", Object.assign({ type: "button", class: "bk-btn" + (cls ? " " + cls : "") }, attrs || {}),
      [ic ? icon(ic) : null, h("span", { text: label })]);
  }
  function toast(text, opts) {
    if (root.BirgeUI) root.BirgeUI.toast(text, opts);
  }
  function store(key, value) {
    try {
      if (value === undefined) return root.localStorage.getItem(key);
      root.localStorage.setItem(key, value);
    } catch (e) {
      return null;
    }
    return null;
  }
  function date(iso) {
    return I() && iso ? I().formatDate(iso) : iso || "";
  }
  // Время отключения хранится как время Астаны (+05:00); поле datetime-local — «2026-10-13T10:00» без пояса.
  function toLocalInput(iso) {
    if (!iso) return "";
    return new Date(new Date(iso).getTime() + ASTANA_MS).toISOString().slice(0, 16);
  }
  function kindLabel(item) {
    if (item.type === "outage") return tr("nearby.utility." + item.utility);
    if (item.work_kind === "lighting") return tr("proposal.kind.lighting");
    return tr("works.kind." + (item.work_kind || "other"));
  }

  function makeRequest(opts) {
    var v2 = opts.api && typeof opts.api.v2 === "function" ? opts.api.v2 : null;
    // Чтение для сотрудника (GET /staff/ideas, GET /works): шлюз R01 для staff-маршрутов требует CSRF-токен и на GET
    // (R15 route policy), а клиент оболочки шлёт его только в изменяющих запросах — такие GET идут напрямую с токеном.
    var staffGet = function (method, path) { return method === "GET" && /^\/(staff\/|works(\?|$))/.test(path); };
    // Все запросы сотрудника (чтение очереди, решения по идеям, записи «Рядом») — напрямую с токеном: не зависят от того,
    // успела ли оболочка узнать сессию после перезагрузки страницы.
    var staffPath = function (path) { return /^\/(staff\/|works(\/|\?|$))/.test(path) || /^\/ideas\/[^/]+\/decide$/.test(path); };
    // Токен сотрудника: у оболочки (CivicShell) — когда она уже узнала сессию; иначе (экран открыт сразу после
    // перезагрузки) — из GET /api/civic/v1/session, как у карточек R06 (proposals.js).
    var token = null;
    function csrf(fresh) {
      var shellToken = root.CivicShell && root.CivicShell.csrfToken ? root.CivicShell.csrfToken() : null;
      if (shellToken && !fresh) return Promise.resolve(shellToken);
      if (token && !fresh) return Promise.resolve(token);
      return root.fetch("/api/civic/v1/session", { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (j) { var d = (j && j.data) || j || {}; token = d.authenticated ? d.csrf_token || null : null; return token; },
          function () { return null; });
    }
    function direct(method, path, body, retried) {
      return csrf(retried).then(function (tok) {
        var headers = { Accept: "application/json" };
        if (body !== undefined) headers["Content-Type"] = "application/json";
        if (tok && (method !== "GET" || staffGet(method, path))) headers["X-CSRF-Token"] = tok;
        return root.fetch((opts.apiBase || API) + path, { method: method, headers: headers, credentials: "same-origin",
          body: body !== undefined ? JSON.stringify(body) : undefined });
      }).then(function (res) {
        return res.json().catch(function () { return null; }).then(function (json) {
          if (res.ok && json && json.ok === true) return json.data; // конверт стенда R06
          if (res.ok) return json;
          var e = (json && json.error) || {};
          var err = new Error((typeof e === "object" ? e.message : json && json.message) || "HTTP " + res.status);
          err.status = res.status;
          err.code = typeof e === "string" ? e : e.code;
          err.fields = (typeof e === "object" && e.fields) || (json && json.fields) || {};
          throw err;
        });
      }, function () {
        var err = new Error("network");
        err.status = 0;
        err.code = "network";
        throw err;
      }).catch(function (err) {
        if (!retried && err.code === "csrf_failed") return direct(method, path, body, true); // токен устарел — один повтор
        throw err;
      });
    }
    return function (method, path, body) {
      if (v2 && !staffPath(path)) {
        return Promise.resolve().then(function () { return v2(method, path, body); }).catch(function (err) {
          err.code = err.code || err.error;
          throw err;
        });
      }
      return direct(method, path, body, false);
    };
  }

  function mount(rootEl, options) {
    var opts = Object.assign({ titleTag: "h2" }, options || {});
    var request = makeRequest(opts);
    var saved = store(DISTRICT_KEY);
    var state = { district: DISTRICTS.indexOf(saved) >= 0 ? saved : "nura", items: null, error: null, services: null,
      view: "list", form: null, errors: {}, busy: false, confirm: null };
    var alive = true;
    rootEl.classList.add("rw");

    function load() {
      state.items = null;
      state.error = null;
      render();
      request("GET", "/works?district=" + encodeURIComponent(state.district)).then(function (data) {
        if (!alive) return;
        state.items = data.items || [];
        render();
      }, function (err) {
        if (!alive) return;
        state.error = err;
        render();
      });
    }
    function loadServices() {
      request("GET", "/akim/routing").then(function (data) {
        state.services = (data && data.services) || null;
        if (alive && state.view === "form") render();
      }, function () { state.services = null; });
    }
    function serviceName(id) {
      var s = state.services && state.services[id];
      return s ? s[lang()] || s.ru : id;
    }

    function render() {
      if (!alive) return;
      var focusKey = doc.activeElement && rootEl.contains(doc.activeElement) ? doc.activeElement.getAttribute("data-key") : null;
      rootEl.replaceChildren(h(opts.titleTag, { class: "bk-h1", text: tr("shell.nav.works_staff") }));
      if (state.view === "form") renderForm();
      else renderList();
      if (focusKey) {
        var again = rootEl.querySelector('[data-key="' + focusKey + '"]');
        if (again) again.focus();
      }
    }

    function renderList() {
      var select = h("select", { id: "rw-district", "data-key": "district", onchange: function (e) {
        state.district = e.target.value;
        store(DISTRICT_KEY, state.district);
        load();
      } }, DISTRICTS.map(function (d) {
        return h("option", { value: d, selected: d === state.district, text: tr("district." + d) });
      }));
      rootEl.appendChild(h("div", { class: "rw-head" }, [
        h("div", { class: "bk-field" }, [h("label", { class: "bk-field__label", for: "rw-district", text: tr("works.form.district") }), select]),
        button("bk-btn--primary", tr("works.form.add"), "plus", { "data-key": "add", onclick: function () { openForm(null); } }),
      ]));
      var list = h("div", { class: "rw-list" });
      if (state.error) {
        if (state.error.status === 401 || state.error.status === 403) root.BirgeUI.state(list, "empty", { title: tr("proposal.need_staff"), icon: "user" });
        else root.BirgeUI.state(list, "error", { action: { onClick: load } });
      } else if (!state.items) {
        root.BirgeUI.state(list, "loading");
      } else if (!state.items.length) {
        root.BirgeUI.state(list, "empty", { title: tr("works.form.empty"), icon: "calendar" });
      } else {
        state.items.forEach(function (item) { list.appendChild(card(item)); });
      }
      rootEl.appendChild(list);
    }

    // Строка записи (дизайн-марафон): плитка вида работ, тихая строка «вид · Пример», название, срок одной строкой.
    // Сдвинутый срок — «до / после»: плановый зачёркнут → новый, метка «срок перенесён». «Изменить» — капсула, «Удалить» — тихая.
    function tileOf(item) {
      var ic = item.type === "outage" ? UTILITY_ICON[item.utility] || "alert" : KIND_ICON[item.work_kind] || "dots";
      return h("span", { class: "ri-tile", "aria-hidden": "true" }, [icon(ic)]);
    }
    function whenLine(item) {
      if (item.type === "outage") {
        return h("p", { class: "rw-when" }, [date(item.start) + " " + (I() ? I().formatTime(item.start) + "–" + I().formatTime(item.end) : "")]);
      }
      var shifted = item.forecast_end && item.planned_end && item.forecast_end > item.planned_end;
      if (!shifted) {
        return h("p", { class: "rw-when" }, [tr(WORK_STATUS[item.status]) + " · " + tr("works.form.until", { date: date(item.forecast_end || item.planned_end) })]);
      }
      return h("p", { class: "rw-when" }, [
        h("span", { text: tr(WORK_STATUS[item.status]) + " ·" }),
        h("s", { text: tr("works.form.until", { date: date(item.planned_end) }) }),
        h("span", { "aria-hidden": "true", text: "→" }),
        h("span", { class: "rw-when__new", text: date(item.forecast_end) }),
        h("span", { class: "bk-tag bk-tag--warn", text: tr("works.shift_later") }),
      ]);
    }
    function card(item) {
      var l = lang();
      var title = item["title_" + l] || item.title_ru;
      var confirming = state.confirm === item.id;
      var meta = h("p", { class: "ri-meta" }, [h("span", { text: kindLabel(item) }),
        item.demo ? h("span", { class: "bk-tag bk-tag--demo", title: tr("common.tag.demo_hint"), text: tr("common.tag.demo") }) : null]);
      return h("article", { class: "bk-card rw-card", "data-work": item.id }, [
        h("div", { class: "ri-app" }, [tileOf(item), h("div", { class: "ri-app__body" }, [meta,
          h("h3", { class: "bk-card__title rw-title", lang: item["title_" + l] ? l : "ru", text: title }), whenLine(item)])]),
        item.type === "outage" && item.zone_ru ? h("p", { class: "rw-where", text: tr("nearby.outage.zone", { text: item["zone_" + l] || item.zone_ru }) }) : null,
        h("div", { class: "rw-foot" }, [
          button(confirming ? "bk-btn--danger" : "bk-btn--ghost rw-remove", tr(confirming ? "works.form.remove_confirm" : "works.form.remove"), "trash",
            { "data-key": "remove-" + item.id, onclick: function () { remove(item); } }),
          button("rw-capsule", tr("works.form.edit_title"), "edit", { "data-key": "edit-" + item.id, onclick: function () { openForm(item); } }),
        ]),
      ]);
    }

    function remove(item) {
      if (state.confirm !== item.id) {
        state.confirm = item.id;
        render();
        return;
      }
      state.confirm = null;
      request("POST", "/works/" + encodeURIComponent(item.id) + "/remove", { expected_revision: item.revision }).then(function () {
        toast(tr("works.form.removed"));
        load();
      }, failed);
    }

    // ── форма ──
    function openForm(item) {
      var l = lang();
      var texts = (item && item.texts) || {};
      var other = l === "kk" ? "ru" : "kk";
      var has = function (f) { return texts[f + "_" + l] != null; };
      var pick = function (f) { return texts[f + "_" + l] != null ? texts[f + "_" + l] : texts[f + "_" + other] || ""; };
      state.form = {
        id: item ? item.id : null, revision: item ? item.revision : null,
        otherLang: !!item && !has("title") && texts["title_" + other] != null,
        type: item ? item.type : "work", status: item && item.status || "in_progress", work_kind: item && item.work_kind || "roadworks",
        utility: item && item.utility || "water", source: item && item.source || "water", district: item ? item.district : state.district,
        title: pick("title"), zone: pick("zone"), detour: pick("detour"),
        start: item && item.type === "outage" ? toLocalInput(item.start) : "", end: item && item.type === "outage" ? toLocalInput(item.end) : "",
        planned_end: item && item.planned_end || "", forecast_end: item && item.forecast_end || "",
        why: { problem: pick("why_problem"), reason: pick("why_reason"), result: pick("why_result"), inconvenience: pick("why_inconvenience") },
      };
      state.errors = {};
      state.view = "form";
      if (!state.services) loadServices();
      render();
      var first = rootEl.querySelector("[data-key=type-work]");
      if (first) first.focus();
    }
    function input(name, labelKey, type, value, onInput, extra) {
      var id = "rw-" + name.replace(/\./g, "-");
      var err = state.errors[name];
      var el = type === "textarea" ? h("textarea", Object.assign({ id: id, rows: "2", maxlength: "200", "data-key": id }, extra || {}))
        : h("input", Object.assign({ id: id, type: type, "data-key": id }, extra || {}));
      el.value = value || "";
      if (err) {
        el.setAttribute("aria-invalid", "true");
        el.setAttribute("aria-describedby", id + "-err");
      }
      el.addEventListener("input", function () {
        onInput(el.value);
        // Поле исправляют — ошибка этого поля уходит сразу, без перерисовки формы.
        if (state.errors[name]) {
          delete state.errors[name];
          el.removeAttribute("aria-invalid");
          el.removeAttribute("aria-describedby");
          var box = el.parentNode, msg = box.querySelector(".bk-field__error");
          box.classList.remove("bk-field--error");
          if (msg) msg.remove();
        }
      });
      return h("div", { class: "bk-field" + (err ? " bk-field--error" : "") }, [
        h("label", { class: "bk-field__label", for: id, text: tr(labelKey) }), el,
        err ? h("p", { class: "bk-field__error", id: id + "-err", text: err }) : null]);
    }
    function select(name, labelKey, options, value, onChange) {
      var id = "rw-" + name;
      var el = h("select", { id: id, "data-key": id, onchange: function (e) { onChange(e.target.value); } },
        options.map(function (o) { return h("option", { value: o.value, selected: o.value === value, text: o.label }); }));
      return h("div", { class: "bk-field" + (state.errors[name] ? " bk-field--error" : "") }, [
        h("label", { class: "bk-field__label", for: id, text: tr(labelKey) }), el,
        state.errors[name] ? h("p", { class: "bk-field__error", text: state.errors[name] }) : null]);
    }
    function seg(name, legendKey, options, value, onChange) {
      var box = h("div", { class: "bk-seg", role: "radiogroup", "aria-label": tr(legendKey) });
      options.forEach(function (o) {
        box.appendChild(h("button", { type: "button", role: "radio", "aria-checked": String(value === o.value), "aria-pressed": String(value === o.value),
          "data-key": name + "-" + o.value, onclick: function () { onChange(o.value); render(); } }, [o.label]));
      });
      return h("fieldset", {}, [h("legend", { text: tr(legendKey) }), box]);
    }
    function renderForm() {
      var f = state.form;
      var form = h("form", { class: "bk-card rw-form", novalidate: true, onsubmit: function (e) { e.preventDefault(); save(); } });
      form.appendChild(h("h3", { class: "bk-h2", text: tr(f.id ? "works.form.edit_title" : "works.form.new_title") }));
      form.appendChild(h("p", { class: "bk-field__hint", text: tr(f.otherLang ? "works.form.other_lang" : "works.form.lang_hint") }));
      form.appendChild(seg("type", "works.form.type", [{ value: "work", label: tr("works.form.type_work") },
        { value: "outage", label: tr("works.form.type_outage") }], f.type, function (v) { f.type = v; }));
      form.appendChild(select("district", "works.form.district", DISTRICTS.map(function (d) { return { value: d, label: tr("district." + d) }; }),
        f.district, function (v) { f.district = v; }));
      form.appendChild(input("title", "works.form.title", "text", f.title, function (v) { f.title = v; }, { maxlength: "120", autocomplete: "off" }));
      var grid = h("div", { class: "rw-grid" });
      if (f.type === "work") {
        form.appendChild(seg("status", "works.form.status", Object.keys(WORK_STATUS).map(function (s) { return { value: s, label: tr(WORK_STATUS[s]) }; }),
          f.status, function (v) { f.status = v; }));
        grid.appendChild(select("work_kind", "works.form.kind", WORK_KINDS.map(function (k) {
          return { value: k, label: kindLabel({ type: "work", work_kind: k }) };
        }), f.work_kind, function (v) { f.work_kind = v; }));
        grid.appendChild(h("span"));
        grid.appendChild(input("planned_end", "works.form.planned_end", "date", f.planned_end, function (v) { f.planned_end = v; }));
        grid.appendChild(input("forecast_end", "works.form.forecast_end", "date", f.forecast_end, function (v) { f.forecast_end = v; }));
      } else {
        grid.appendChild(select("utility", "works.form.utility", UTILITIES.map(function (u) { return { value: u, label: tr("nearby.utility." + u) }; }),
          f.utility, function (v) { f.utility = v; }));
        var ids = state.services ? Object.keys(state.services) : [f.source];
        grid.appendChild(select("source", "works.form.source", ids.map(function (s) { return { value: s, label: serviceName(s) }; }),
          f.source, function (v) { f.source = v; }));
        grid.appendChild(input("start", "works.form.start", "datetime-local", f.start, function (v) { f.start = v; }));
        grid.appendChild(input("end", "works.form.end", "datetime-local", f.end, function (v) { f.end = v; }));
        grid.appendChild(input("zone", "works.form.zone", "text", f.zone, function (v) { f.zone = v; }, { maxlength: "200" }));
        grid.appendChild(input("detour", "works.form.detour", "text", f.detour, function (v) { f.detour = v; }, { maxlength: "200" }));
      }
      form.appendChild(grid);
      var whyGrid = h("div", { class: "rw-why" });
      var why = h("fieldset", {}, [h("legend", { text: tr("works.form.why") }), whyGrid]);
      WHY.forEach(function (k) {
        whyGrid.appendChild(input("why." + k, "nearby.why." + k, "textarea", f.why[k], function (v) { f.why[k] = v; }));
      });
      form.appendChild(why);
      form.appendChild(h("div", { class: "bk-actions" }, [
        h("button", { type: "submit", class: "bk-btn bk-btn--primary", "data-key": "save" }, [icon("check"), h("span", { text: tr("common.action.save") })]),
        button("bk-btn--ghost", tr("common.action.cancel"), "close", { onclick: function () { state.view = "list"; render(); } }),
      ]));
      rootEl.appendChild(form);
    }

    function body() {
      var f = state.form;
      var b = { type: f.type, district: f.district, lang: lang(), title: f.title.trim(), why: {} };
      WHY.forEach(function (k) { b.why[k] = f.why[k].trim(); });
      if (f.type === "work") {
        b.status = f.status;
        b.work_kind = f.work_kind;
        b.planned_end = f.planned_end || null;
        b.forecast_end = f.forecast_end || null;
      } else {
        b.utility = f.utility;
        b.source = f.source;
        b.start = f.start || null;
        b.end = f.end || null;
        b.zone = f.zone.trim() || null;
        b.detour = f.detour.trim() || null;
      }
      if (f.id) b.expected_revision = f.revision;
      return b;
    }
    // Проверка в форме — те же правила, что на сервере (сервер всё равно проверит сам).
    function check(b) {
      var e = {}, req = tr("works.form.required");
      if (!b.title) e.title = req;
      WHY.forEach(function (k) { if (!b.why[k]) e["why." + k] = req; });
      if (b.type === "work" && !b.planned_end) e.planned_end = req;
      if (b.type === "outage") {
        if (!b.zone) e.zone = req;
        if (!b.start) e.start = req;
        if (!b.end) e.end = req;
        if (b.start && b.end && (b.end <= b.start || (Date.parse(b.end) - Date.parse(b.start)) > 14 * 86400000)) e.end = tr("works.form.bad_time");
      }
      return e;
    }
    function save() {
      if (state.busy) return;
      var b = body();
      state.errors = check(b);
      if (Object.keys(state.errors).length) {
        render();
        var bad = rootEl.querySelector("[aria-invalid=true]");
        if (bad) bad.focus();
        return;
      }
      state.busy = true;
      var f = state.form;
      var call = f.id ? request("POST", "/works/" + encodeURIComponent(f.id), b) : request("POST", "/works", b);
      call.then(function () {
        state.busy = false;
        toast(tr("common.state.saved"));
        state.view = "list";
        if (b.district !== state.district) {
          state.district = b.district;
          store(DISTRICT_KEY, state.district);
        }
        load();
      }, function (err) {
        state.busy = false;
        if (err.status === 422 && err.fields) {
          state.errors = {};
          Object.keys(err.fields).forEach(function (k) {
            var name = k === "why" ? "why.problem" : k;
            state.errors[name] = name === "end" ? tr("works.form.bad_time") : /end|date|start/.test(name) ? tr("works.form.bad_date") : tr("works.form.required");
          });
          render();
          var bad = rootEl.querySelector("[aria-invalid=true]");
          if (bad) bad.focus();
          return;
        }
        failed(err);
      });
    }
    function failed(err) {
      if (err.status === 409) {
        toast(tr("works.form.stale"), { type: "error" });
        state.view = "list";
        load();
        return;
      }
      toast(tr(err.status === 401 || err.code === "csrf_failed" ? "proposal.need_staff" : "works.form.error"), { type: "error" });
    }

    var offLang = I() && I().onChange ? I().onChange(function () { render(); }) : null;
    if (I() && I().ready) I().ready.then(load, load);
    else load();
    return {
      setLang: function () { render(); },
      destroy: function () {
        alive = false;
        if (typeof offLang === "function") offLang();
        rootEl.classList.remove("rw");
        rootEl.replaceChildren();
      },
    };
  }

  root.BirgeWorks = { mount: mount, version: "works-r14-w2", KEYS: KEYS };
})(typeof self !== "undefined" ? self : this);
