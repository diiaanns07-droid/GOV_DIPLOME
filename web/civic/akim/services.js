/*
 * Birge · «Службы» — кому передаются обращения (R08, волна мелочей п. 7; меню акимата «Ещё → Службы», R11 IA_WAVE2 §1).
 *
 *   <link rel="stylesheet" href="/civic/akim/services.css">
 *   <script src="/civic/i18n/i18n.js"></script>
 *   <script src="/civic/akim/services.js"></script>
 *   BirgeServices.mount(document.getElementById("services"), { apiBase: "/api/civic/v2", titleTag: "h1" });
 *
 * Данные: GET {apiBase}/akim/routing → {services, rules:[{key, category, subtopic, service, own, edited}]};
 * сохранение: PUT {apiBase}/akim/routing {rules: {ключ: служба | null}} — только изменённые строки, сотрудник
 * (X-CSRF-Token: из оболочки CivicShell.csrfToken() или GET /api/civic/v1/session — как у R05/R06).
 * Названия служб — t("service.<id>") из словаря R11; если акимат переименовал службу (edited) — его название.
 * Одна главная кнопка — «Сохранить». Уточнения категории свёрнуты в «Уточнения (N)».
 * В оболочке R01 экран встаёт в «Ещё» акимата сам: при загрузке файла вызывается
 * BirgeShell.registerScreen({id: "services", mount, modes: ["akimat"], titleKey: "shell.nav.services"})
 * (R01 INTEGRATION §11.2); opts.api.v2 — клиент шлюза оболочки (CSRF сотрудника).
 */
(function (root) {
  "use strict";

  var doc = root.document;
  // Ключи этого экрана, которых пока нет в словаре R11 (запас до слияния; список — INTEGRATION.txt §8).
  var KEYS = {
    ru: {
      "services.title": "Службы",
      "services.hint": "Кому передаётся обращение. Названия общие — акимат может выбрать другую службу.",
      "services.subtopics": "Уточнения ({n})",
      "services.same": "Как у категории",
      "services.edited": "изменено акиматом",
      "services.saved": "Сохранено",
      "services.nothing": "Изменений нет",
      "services.forbidden": "Менять таблицу может только сотрудник акимата",
      "services.save_error": "Не сохранилось — попробуйте ещё раз",
      "services.for": "Служба для «{name}»",
    },
    kk: {
      "services.title": "Қызметтер",
      "services.hint": "Өтініш кімге жіберіледі. Атаулар жалпы — әкімдік басқа қызметті таңдай алады.",
      "services.subtopics": "Нақтылаулар ({n})",
      "services.same": "Санаттағыдай",
      "services.edited": "әкімдік өзгертті",
      "services.saved": "Сақталды",
      "services.nothing": "Өзгеріс жоқ",
      "services.forbidden": "Кестені тек әкімдік қызметкері өзгерте алады",
      "services.save_error": "Сақталмады — қайталап көріңіз",
      "services.for": "«{name}» үшін қызмет",
    },
  };

  function I() {
    return root.BirgeI18n;
  }
  function lang() {
    return I() ? I().getLang() : "ru";
  }
  function tr(key, params) {
    var i18n = I();
    if (i18n && (i18n.has(key) || i18n.has(key, "ru"))) return i18n.t(key, params);
    var v = (KEYS[lang() === "kk" ? "kk" : "ru"] || {})[key] || KEYS.ru[key] || key;
    return String(v).replace(/\{(\w+)\}/g, function (w, n) {
      return params && params[n] != null ? String(params[n]) : w;
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

  function mount(rootEl, options) {
    var opts = { apiBase: "/api/civic/v2", titleTag: "h1" };
    Object.keys(options || {}).forEach(function (k) {
      if (options[k] != null) opts[k] = options[k];
    });
    var state = { status: "loading", data: null, changes: {}, message: "", messageKind: "" };
    rootEl.classList.add("svc");
    var api = opts.api && typeof opts.api.v2 === "function" ? opts.api.v2 : null;

    function serviceName(id) {
      var svc = state.data && state.data.services[id];
      if (svc && svc.edited) return svc[lang()] || svc.ru;
      return I() && I().has("service." + id) ? I().t("service." + id) : (svc && (svc[lang()] || svc.ru)) || id;
    }
    function rowLabel(r) {
      if (r.subtopic) return I() && I().has("subtopic." + r.subtopic) ? I().t("subtopic." + r.subtopic) : r[lang()] || r.ru;
      return I() ? I().cat(r.category) : r.ru;
    }
    function current(r) {
      return Object.prototype.hasOwnProperty.call(state.changes, r.key) ? state.changes[r.key] : r.own === false ? null : r.service;
    }

    function load() {
      state.status = "loading";
      render();
      (api
        ? Promise.resolve().then(function () { return api("GET", "/akim/routing"); })
        : fetch(opts.apiBase + "/akim/routing", { headers: { Accept: "application/json" }, credentials: "same-origin" }).then(function (r) {
            return r.ok ? r.json() : Promise.reject(r.status);
          })
      )
        .then(function (d) {
          state.data = d;
          state.status = "ok";
          state.changes = {};
          render();
        })
        .catch(function () {
          state.status = "error";
          render();
        });
    }

    var csrfCache = null;
    function csrf() {
      try {
        var s = root.CivicShell && typeof root.CivicShell.csrfToken === "function" ? root.CivicShell.csrfToken() : null;
        if (s) return Promise.resolve(s);
      } catch (e) {
        /* оболочки нет */
      }
      if (csrfCache) return Promise.resolve(csrfCache);
      return fetch("/api/civic/v1/session", { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) {
          return r.json();
        })
        .then(function (b) {
          var d = b && b.data && typeof b.data === "object" ? b.data : b || {};
          csrfCache = d.authenticated && typeof d.csrf_token === "string" ? d.csrf_token : null;
          return csrfCache;
        })
        .catch(function () {
          return null;
        });
    }

    function save() {
      var keys = Object.keys(state.changes);
      if (!keys.length) {
        say(tr("services.nothing"), "info");
        return;
      }
      if (api) {
        // Клиент оболочки сам ставит CSRF сотрудника; ошибка — объект со status.
        Promise.resolve()
          .then(function () {
            return api("PUT", "/akim/routing", { rules: state.changes });
          })
          .then(function (d) {
            state.data = d;
            state.changes = {};
            render();
            say(tr("services.saved"), "ok");
          })
          .catch(function (err) {
            var st = err && err.status;
            say(tr(st === 401 || st === 403 ? "services.forbidden" : "services.save_error"), "error");
          });
        return;
      }
      csrf()
        .then(function (token) {
          var headers = { Accept: "application/json", "Content-Type": "application/json" };
          if (token) headers["X-CSRF-Token"] = token;
          return fetch(opts.apiBase + "/akim/routing", {
            method: "PUT",
            credentials: "same-origin",
            headers: headers,
            body: JSON.stringify({ rules: state.changes }),
          });
        })
        .then(function (r) {
          if (r.ok)
            return r.json().then(function (d) {
              state.data = d;
              state.changes = {};
              render();
              say(tr("services.saved"), "ok");
            });
          say(tr(r.status === 401 || r.status === 403 ? "services.forbidden" : "services.save_error"), "error");
        })
        .catch(function () {
          say(tr("services.save_error"), "error");
        });
    }
    function say(text, kind) {
      state.message = text;
      state.messageKind = kind;
      var el = rootEl.querySelector(".svc__status");
      if (el) {
        el.textContent = text;
        el.setAttribute("data-kind", kind);
      }
    }

    function fieldId(r) {
      return "svc-" + r.key.replace(/[^a-z0-9]/gi, "-");
    }
    function select(r, catService) {
      var value = current(r);
      var id = fieldId(r);
      var ids = Object.keys(state.data.services);
      ids.sort(function (a, b) {
        return serviceName(a).localeCompare(serviceName(b), lang());
      });
      var choices = (r.subtopic ? [h("option", { value: "", text: tr("services.same") + " — " + serviceName(catService), selected: value == null })] : []).concat(
        ids.map(function (sid) {
          return h("option", { value: sid, text: serviceName(sid), selected: value === sid });
        })
      );
      var sel = h(
        "select",
        {
          id: id,
          class: "svc__select",
          "aria-label": tr("services.for", { name: rowLabel(r) }),
          onchange: function (e) {
            // «Как у категории» у уточнения со своим правилом по умолчанию — явно служба категории
            // (null на сервере значит «вернуть умолчание», а оно у такого уточнения своё).
            var v = e.target.value || (r.own ? catService : null);
            var original = r.subtopic && r.own === false ? null : r.service;
            if (v === original) delete state.changes[r.key];
            else state.changes[r.key] = v;
            say("", "");
            if (!r.subtopic) render(); // «Как у категории — …» у уточнений показывает новую службу категории
          },
        },
        choices
      );
      return sel;
    }

    function render() {
      rootEl.textContent = "";
      rootEl.setAttribute("data-state", state.status);
      var tag = /^h[1-3]$/.test(opts.titleTag) ? opts.titleTag : "h1";
      rootEl.appendChild(h(tag, { class: "svc__title", text: tr("services.title") }));
      rootEl.appendChild(h("p", { class: "svc__hint bk-meta", text: tr("services.hint") }));
      if (state.status === "loading") {
        rootEl.appendChild(h("div", { class: "bk-card" }, [h("div", { class: "bk-skel bk-skel--line" }), h("div", { class: "bk-skel bk-skel--line" })]));
        return;
      }
      if (state.status === "error") {
        rootEl.appendChild(
          h("div", { class: "bk-card bk-error", role: "alert" }, [
            h("p", { class: "bk-error__title", text: tr("common.state.error_title") }),
            h("button", { type: "button", class: "bk-btn bk-btn--primary", text: tr("common.action.retry"), onclick: load }),
          ])
        );
        return;
      }
      var rows = state.data.rules;
      var list = h("ul", { class: "svc__list" });
      rows
        .filter(function (r) {
          return !r.subtopic;
        })
        .forEach(function (cat) {
          var catService = Object.prototype.hasOwnProperty.call(state.changes, cat.key) ? state.changes[cat.key] : cat.service;
          var subs = rows.filter(function (r) {
            return r.category === cat.category && r.subtopic;
          });
          var subList = h(
            "ul",
            { class: "svc__subs" },
            subs.map(function (r) {
              return h("li", { class: "svc__row svc__row--sub" }, [
                h("label", { class: "svc__label", for: fieldId(r), text: rowLabel(r) }),
                select(r, catService),
                r.edited ? h("span", { class: "bk-tag svc__edited", text: tr("services.edited") }) : null,
              ]);
            })
          );
          list.appendChild(
            // Строка списка с линией между темами, не карточка в панели (чистый стиль R11 §2.3).
            h("li", { class: "svc__cat", "data-key": cat.key }, [
              h("div", { class: "svc__row" }, [
                h("label", { class: "svc__label svc__label--cat", for: fieldId(cat), text: rowLabel(cat) }),
                select(cat, catService),
                cat.edited ? h("span", { class: "bk-tag svc__edited", text: tr("services.edited") }) : null,
              ]),
              subs.length
                ? h("details", { class: "bk-details svc__details" }, [h("summary", { text: tr("services.subtopics", { n: subs.length }) }), subList])
                : null,
            ])
          );
        });
      rootEl.appendChild(list);
      rootEl.appendChild(
        h("div", { class: "svc__actions" }, [
          h("button", { type: "button", class: "bk-btn bk-btn--primary svc__save", text: tr("common.action.save"), onclick: save }),
          h("p", { class: "svc__status", role: "status", "data-kind": state.messageKind, text: state.message }),
        ])
      );
    }

    var off = null;
    (I() ? I().ready : Promise.resolve()).then(function () {
      if (I()) off = I().onChange(render);
      load();
    });
    var handle = {
      reload: load,
      destroy: function () {
        if (off) off();
        rootEl.textContent = "";
        delete rootEl.birgeServices;
      },
    };
    rootEl.birgeServices = handle;
    return handle;
  }

  root.BirgeServices = { mount: mount, version: "services-r14-w1" };
  // Оболочка R01: экран «Службы» — в «Ещё» акимата (контракт R01 INTEGRATION §11.2).
  function register() {
    var shell = root.BirgeShell;
    if (shell && typeof shell.registerScreen === "function") {
      return shell.registerScreen({ id: "services", mount: mount, modes: ["akimat"], titleKey: "shell.nav.services" });
    }
    return false;
  }
  root.BirgeServices.register = register;
  // birge.js может загрузиться позже (defer по порядку): тогда — после разбора страницы.
  if (!register() && doc.readyState !== "complete") doc.addEventListener("DOMContentLoaded", register);
})(window);
