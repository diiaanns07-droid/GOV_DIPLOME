/*
 * R09 · волна 2 · Акимат · «Обращения» (R01 INTEGRATION §11.2 раздел #complaints; R11 IA_WAVE2 §2.5).
 * Список ЦЕЛЕЙ с открытыми обращениями, а не отдельных жалоб: группа = место + категория. Вкладки — Новые ·
 * В работе · Ждут проверки · Просрочено · Вернули жители (число в каждой). Строка: место · категория · уточнение ·
 * N человек · срок. Нажатие раскрывает группу: «Показать на карте» и действия сотрудника (complaint-staff.js) —
 * та же карточка действий, что встраивает R07 на карте. Второй карты на экране нет.
 *
 *   handle = BirgeComplaintList.mount(root, { api: {v2(method, path, body)}, lang, titleTag, openTarget(kind, id) })
 *     -> { destroy(), setLang(lang), refresh() }
 * Оболочка R01 отдаёт opts.api.v2 (CSRF сотрудника внутри); без неё — fetch на /api/civic/v2.
 */
(function () {
  "use strict";
  var TABS = ["new", "in_progress", "waiting_check", "overdue", "reopened"];
  var C = function () { return window.BirgeComplaint; };
  var t = function (key, params) { return C().t(key, params); };

  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      var value = attrs[key];
      if (value === null || value === undefined || value === false) return;
      if (key === "class") el.className = value;
      else if (key.slice(0, 2) === "on") el.addEventListener(key.slice(2), value);
      else el.setAttribute(key, value === true ? "" : value);
    });
    [].concat(children === undefined ? [] : children).forEach(function (child) {
      if (child === null || child === undefined || child === false) return;
      el.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return el;
  }

  // Иллюстрация ui-kit (через R09 complaint.js); если её нет — значок.
  function art(name, fallback) {
    var c = C();
    if (c.illustration) return c.illustration(name, fallback);
    return c.icon ? c.icon(fallback) : null;
  }

  function csrfToken() {
    var shell = window.CivicShell;
    return shell && typeof shell.csrfToken === "function" ? (shell.csrfToken() || "") : "";
  }

  // Клиент: оболочка R01 (тело ответа как есть) или свой fetch. -> Promise({ ok, data, status }).
  function client(opts) {
    if (opts.api && typeof opts.api.v2 === "function") {
      return function (method, path) {
        return opts.api.v2(method, path).then(function (body) {
          return { ok: !!(body && body.ok !== false), data: body && body.data, status: 200 };
        }, function (err) { return { ok: false, status: (err && err.status) || 0 }; });
      };
    }
    return function (method, path) {
      return fetch("/api/civic/v2" + path, { method: method, credentials: "same-origin",
        headers: { "Accept": "application/json", "X-CSRF-Token": csrfToken() } })
        .then(function (r) { return r.json().catch(function () { return null; }).then(function (j) {
          return { ok: r.ok && !!j && j.ok !== false, data: j && j.data, status: r.status };
        }); }, function () { return { ok: false, status: 0 }; });
    };
  }

  function deadlineNode(d) {
    if (!d || d.state === "answered") return null;
    if (d.state === "overdue") return h("span", { "class": "bc-deadline bc-deadline--danger" }, t("deadline.overdue", { n: d.overdue_working_days || 1 }));
    if (d.state === "today") return h("span", { "class": "bc-deadline bc-deadline--warn" }, t("deadline.today"));
    var left = d.working_days_left || 0;
    return h("span", { "class": "bc-deadline" + (left <= 1 ? " bc-deadline--warn" : "") }, t("deadline.left", { n: left }));
  }

  function mount(root, opts) {
    opts = opts || {};
    var call = client(opts);
    var box = h("section", { "class": "bc-inbox", "aria-labelledby": "bc-inbox-title" });
    root.appendChild(box);
    var state = { data: null, error: false, tab: null, open: null };
    var staffHandle = null;
    var alive = true;

    function closeStaff() {
      if (staffHandle) { try { staffHandle.destroy(); } catch (e) { /* компонент уже снят */ } }
      staffHandle = null;
    }

    function load() {
      state.error = false;
      render();
      return call("GET", "/complaints/inbox").then(function (res) {
        if (!alive) return;
        // 401/403 — не вошёл сотрудник (R11 разбор FINAL-3): это не «нет связи», а «войдите»
        if (!res.ok) { state.error = res.status === 401 || res.status === 403 ? "staff" : true; state.data = null; render(); return; }
        state.data = res.data;
        state.enter = true;   // новые данные — строки мягко появляются (раскрытие строки — без движения)
        if (!state.tab) {
          // По умолчанию — «Новые»; если там пусто — первая непустая вкладка.
          var counts = res.data.counts || {};
          state.tab = counts["new"] ? "new" : (TABS.filter(function (x) { return counts[x]; })[0] || "new");
        }
        render();
      });
    }

    function title() {
      var tag = opts.titleTag || "h2";
      return h(tag, { "class": "bc-inbox__title", id: "bc-inbox-title" }, t("shell.nav.inbox"));
    }

    // Число у вкладки; ноль скрыт стилем (data-zero) — видно, где есть работа (R11 INTEGRATION 11.6).
    function countBadge(n) {
      n = n || 0;
      return h("span", { "class": "bc-inbox__count", "data-zero": n ? null : "" }, " " + n);
    }

    function tabs() {
      var counts = (state.data && state.data.counts) || {};
      // Одним рядом с прокруткой (на 375 — без переноса в 3 ряда, R11 разбор 5 №4в; как вкладки «Рядом» R08).
      var bar = h("div", { "class": "bk-chips bc-inbox__tabs", role: "tablist" });
      TABS.forEach(function (id) {
        bar.appendChild(h("button", { "class": "bk-chip bc-inbox__tab", type: "button", role: "tab", "data-tab": id,
                                      "aria-selected": state.tab === id ? "true" : "false",
                                      "aria-pressed": state.tab === id ? "true" : "false",
                                      onclick: function () { state.tab = id; state.open = null; state.enter = true; closeStaff(); render(); } },
          [h("span", {}, t("inbox.tab." + id)), countBadge(counts[id])]));
      });
      return bar;
    }

    function row(group) {
      var expanded = state.open === group.key;
      var place = C().targetLabel(group.target);
      // Общая подпись «Примерное место» у нескольких строк неразличима (R11 разбор 5 №4б) — добавляем номер.
      if (group.target && group.target.approximate && place === t("complaint.step2.approximate") && group.complaints[0]) {
        place += " · " + group.complaints[0].code;
      }
      var what = C().categoryLabel(group.category) + (group.subtopic ? " · " + C().subtopicLabel(group.category, group.subtopic) : "");
      var due = deadlineNode(group.deadline);
      // Строка как в списке iOS (дизайн-марафон): слева — число людей в кружке цвета карты жалоб (1–2 / 3–5 / 6–9 / 10+),
      // в середине — место 17, категория 15, «N человек · срок» 13; справа — «›», при раскрытии поворачивается.
      var level = group.people >= 10 ? 4 : (group.people >= 6 ? 3 : (group.people >= 3 ? 2 : 1));
      var head = h("button", { "class": "bc-inbox__row", type: "button", "aria-expanded": expanded ? "true" : "false",
                               "data-key": group.key, onclick: function () { toggle(group); } }, [
        h("span", { "class": "bk-heat bc-inbox__heat", "data-level": String(level), "aria-hidden": "true" }, String(group.people)),
        h("span", { "class": "bc-inbox__text" }, [
          h("span", { "class": "bc-inbox__place" }, [h("strong", {}, place),
            // П. 8: акимат видит оригинал с пометкой (как карточка R07) — R10 B-064.
            group.rude ? h("span", { "class": "bk-tag bc-tag--rude" }, t("moderation.rude")) : null]),
          // Уточнение — вторая строка после категории (UX_SPEC §10), не отдельный бейдж.
          h("span", { "class": "bc-inbox__what" }, [C().icon && C().categoryIcon ? C().icon(C().categoryIcon(group.category)) : null, h("span", {}, what)]),
          h("span", { "class": "bc-meta" }, [t("inbox.people", { n: group.people }),
            group.complaints.length > 1 ? " · " + t("inbox.complaints", { n: group.complaints.length }) : "",
            due ? " · " : null, due])]),
        C().icon ? C().icon("chevron-right") : null]);
      var li = h("li", { "class": "bk-card bc-inbox__item" + (expanded ? " bc-inbox__item--open" : ""), "data-demo": group.demo ? "true" : null }, head);
      if (expanded) {
        var detail = h("div", { "class": "bc-inbox__detail" });
        if (typeof opts.openTarget === "function" && group.target && group.target.id) {
          detail.appendChild(h("button", { "class": "bk-btn bc-inbox__map", type: "button",
                                           onclick: function () { opts.openTarget(group.target.kind, group.target.id, 14); } },
            t("common.action.show_on_map")));
        }
        var main = group.complaints[0];
        if (group.complaints.length > 1) {
          detail.appendChild(h("p", { "class": "bc-meta" }, group.complaints.map(function (c) { return c.code; }).join(" · ")));
        }
        var holder = h("div", { "class": "bc-inbox__staff" });
        detail.appendChild(holder);
        li.appendChild(detail);
        if (main && !main.demo && window.BirgeComplaintStaff) {
          staffHandle = window.BirgeComplaintStaff.mount(holder, { complaintId: main.id, csrf: csrfToken,
            onChange: function () { refreshCounts(); } });
        } else if (main && main.demo) {
          // Примеры не меняются (как в карточке R07: «Это пример: статус примеров не меняется»).
          holder.appendChild(h("p", { "class": "bc-meta" }, t("heat.example_readonly")));
        }
      }
      return li;
    }

    function toggle(group) {
      state.open = state.open === group.key ? null : group.key;
      if (!state.open) closeStaff();
      render();
      if (state.open) {
        var opened = box.querySelector('.bc-inbox__row[data-key="' + state.open.replace(/"/g, "") + '"]');
        if (opened) opened.scrollIntoView({ block: "nearest" });
      }
    }

    // После действия сотрудника обновляем числа во вкладках, не закрывая открытую карточку.
    function refreshCounts() {
      call("GET", "/complaints/inbox").then(function (res) {
        if (!alive || !res.ok) return;
        state.data.counts = res.data.counts;
        box.querySelectorAll(".bc-inbox__tab").forEach(function (b) {
          var n = b.querySelector(".bc-inbox__count");
          if (n) n.replaceWith(countBadge(res.data.counts[b.getAttribute("data-tab")]));
        });
        state.pending = res.data;   // список перерисуем при смене вкладки, чтобы карточка не прыгала под рукой
      });
    }

    function render() {
      if (!alive) return;
      // Новые числа после действия сотрудника берём при следующей перерисовке (смена вкладки, раскрытие),
      // чтобы открытая карточка не прыгала под рукой.
      if (state.pending) { state.data = state.pending; state.pending = null; }
      closeStaff();
      box.innerHTML = "";
      box.appendChild(title());
      if (state.error === "staff") {
        var shell = window.CivicShell;
        // Одно состояние «войдите как сотрудник» на все разделы (R11 INTEGRATION 9.3 b): иллюстрация staff, подсказка,
        // «Войти» — главная: без входа карточки действий нет, это единственная кнопка экрана (10.3).
        box.appendChild(h("div", { "class": "bk-empty", role: "status" }, [art("staff", "user"),
          h("p", { "class": "bk-empty__title" }, t("proposal.need_staff")),
          h("p", { "class": "bk-empty__text" }, t("staff.login.note")),
          h("button", { "class": "bk-btn bk-btn--primary", type: "button",
            onclick: function () { if (window.BirgeShell) window.BirgeShell.setSection("map"); if (shell && shell.openEditor) shell.openEditor(); } }, t("staff.login.submit"))]));
        return;
      }
      if (state.error) {
        // Как BirgeUI.state(…, "error"): иллюстрация «нет связи», общая фраза, серая ⟳ «Повторить» (R11 10.3).
        box.appendChild(h("div", { "class": "bk-error", role: "alert" }, [art("offline", "wifi-off"),
          h("p", { "class": "bk-error__title" }, t("mine.error.title")),
          h("p", { "class": "bk-error__text" }, t("common.state.network_text")),
          h("button", { "class": "bk-btn", type: "button", onclick: load },
            [C().icon ? C().icon("refresh") : null, h("span", {}, t("complaint.error.retry"))])]));
        return;
      }
      if (!state.data) {
        // Скелетон строк (как у «Моих обращений»): место, категория, «N человек · срок».
        var skel = function () { return h("div", { "class": "bc-skel-card", "aria-hidden": "true" }, [
          h("span", { "class": "bk-skel bc-skel-line bc-skel-line--title" }), h("span", { "class": "bk-skel bc-skel-line bc-skel-line--status" }),
          h("span", { "class": "bk-skel bc-skel-line bc-skel-line--short" })]); };
        box.appendChild(h("div", { "class": "bc-loading", role: "status" }, [skel(), skel(), skel(),
          h("span", { "class": "bc-loading__text" }, t("mine.loading"))]));
        return;
      }
      box.appendChild(tabs());
      var items = (state.data.items || []).filter(function (g) { return g.tab === state.tab; });
      if (!items.length) {
        box.appendChild(h("div", { "class": "bk-empty" }, [art("done", "check"), h("p", { "class": "bk-empty__title" }, t("inbox.empty"))]));
        return;
      }
      box.appendChild(h("ul", { "class": "bc-inbox__list" + (state.enter ? " bc-list--enter" : ""), role: "tabpanel" }, items.map(row)));
      state.enter = false;
      if (items.some(function (g) { return g.demo; })) box.appendChild(h("p", { "class": "bk-footnote bc-demo-note" }, t("common.tag.demo_hint")));
    }

    // Язык: оболочка зовёт setLang(lang); словарь R11 грузится асинхронно и потом шлёт "birge:lang" — перерисуем и тогда.
    function onLang() { if (alive) render(); }
    window.addEventListener("birge:lang", onLang);
    load();
    return {
      refresh: load,
      setLang: function () { render(); },
      destroy: function () {
        alive = false; closeStaff(); window.removeEventListener("birge:lang", onLang);
        if (box.parentNode) box.parentNode.removeChild(box);
      }
    };
  }

  window.BirgeComplaintList = { mount: mount };
})();
