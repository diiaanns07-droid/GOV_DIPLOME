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
      return function (method, path, body) {
        return opts.api.v2(method, path, body).then(function (res) {
          return { ok: !!(res && res.ok !== false), data: res && res.data, status: 200 };
        }, function (err) { return { ok: false, status: (err && err.status) || 0 }; });
      };
    }
    return function (method, path, body) {
      var headers = { "Accept": "application/json", "X-CSRF-Token": csrfToken() };
      if (body !== undefined) headers["Content-Type"] = "application/json";
      return fetch("/api/civic/v2" + path, { method: method, credentials: "same-origin", headers: headers,
        body: body === undefined ? undefined : JSON.stringify(body) })
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
    // tab: "all" — все группы по статусу (как в Linear); или одна вкладка-фильтр. menu — ключ строки с открытым меню статуса.
    var state = { data: null, error: false, tab: "all", open: null, openFix: false, menu: null, slow: false, hover: null };
    var staffHandle = null;
    var alive = true;

    function closeStaff() {
      if (staffHandle) { try { staffHandle.destroy(); } catch (e) { /* компонент уже снят */ } }
      staffHandle = null;
    }

    // Мгновенный отклик (правило 4 эталона): пока данные уже есть — список не гаснет и не мигает скелетоном, а
    // обновляется на месте; скелетон — только при первой загрузке и только если ответ дольше 150 мс.
    function load(silent) {
      state.error = false;
      if (!silent || !state.data) {
        state.slow = false;
        render();
        setTimeout(function () { if (alive && !state.data && !state.error) { state.slow = true; render(); } }, 150);
      }
      return call("GET", "/complaints/inbox").then(function (res) {
        if (!alive) return;
        // 401/403 — не вошёл сотрудник (R11 разбор FINAL-3): это не «нет связи», а «войдите»
        if (!res.ok) {
          if (silent && state.data) return;   // фоновое обновление не роняет список, который уже на экране
          state.error = res.status === 401 || res.status === 403 ? "staff" : true; state.data = null; render(); return;
        }
        state.enter = !state.data;   // первые данные — строки мягко появляются; обновление на месте — без движения
        state.data = res.data;
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
      // bk-scroll-x + scrollFade ui-kit R11: на телефоне справа мягкое затухание, пока есть что прокрутить (R11 16.4).
      var bar = h("div", { "class": "bk-chips bk-scroll-x bc-inbox__tabs", role: "tablist" });
      if (window.BirgeUI && typeof window.BirgeUI.scrollFade === "function") window.BirgeUI.scrollFade(bar);
      var total = TABS.reduce(function (n, id) { return n + (counts[id] || 0); }, 0);
      ["all"].concat(TABS).forEach(function (id) {
        bar.appendChild(h("button", { "class": "bk-chip bc-inbox__tab", type: "button", role: "tab", "data-tab": id,
                                      "aria-selected": state.tab === id ? "true" : "false",
                                      "aria-pressed": state.tab === id ? "true" : "false",
                                      onclick: function () { state.tab = id; state.open = null; state.menu = null; closeStaff(); render(); } },
          [h("span", {}, id === "all" ? t("staff.cabinet.tab.all") : t("inbox.tab." + id)), countBadge(id === "all" ? total : counts[id])]));
      });
      return bar;
    }

    // Статус группы для значка — по самой срочной жалобе группы (сервер сортирует их по срочности вкладки).
    function groupStatus(group) {
      if (group.tab === "waiting_check") return "reported_fixed";
      if (group.tab === "new" || group.tab === "in_progress") return group.tab;
      return (group.complaints[0] || {}).status === "new" ? "new" : "in_progress";   // просрочено / вернули жители
    }
    function tabStatus(tab) {
      return { "new": "new", waiting_check: "reported_fixed" }[tab] || "in_progress";
    }
    function idsWith(group, statuses) {
      return group.complaints.filter(function (c) { return !c.demo && statuses.indexOf(c.status) >= 0; })
        .map(function (c) { return c.id; });
    }
    function sicon(status) { return C().statusIcon ? C().statusIcon(status) : null; }

    // Смена статуса прямо из строки (правило 5 эталона, как в Linear): значок статуса — кнопка, меню из того, что можно
    // сделать сейчас: «Взять в работу» (сразу, с мгновенным откликом) и «Отметить исправленным» (форма в строке).
    function statusControl(group) {
      var st = groupStatus(group);
      var canTake = idsWith(group, ["new", "accepted"]).length > 0;
      var canFix = idsWith(group, ["new", "accepted", "in_progress"]).length > 0;
      if (!canTake && !canFix) {
        return h("span", { "class": "bc-inbox__status", title: t("status." + st) }, sicon(st));
      }
      var open = state.menu === group.key;
      var btn = h("button", { "class": "bc-inbox__status bc-inbox__status--btn", type: "button", "aria-haspopup": "menu",
                              "aria-expanded": open ? "true" : "false", "data-key": group.key,
                              "aria-label": t("inbox.status_menu") + ": " + t("status." + st),
                              onclick: function (e) { e.stopPropagation(); state.menu = open ? null : group.key; render(); } }, sicon(st));
      var menu = null;
      if (open) {
        var item = function (label, status, act) {
          return h("button", { "class": "bk-menu__item bc-inbox__menu-item", type: "button", role: "menuitem",
                               onclick: function (e) { e.stopPropagation(); act(); } }, [sicon(status), h("span", {}, label)]);
        };
        menu = h("div", { "class": "bk-menu bc-inbox__menu", role: "menu", "aria-label": t("inbox.status_menu") }, [
          canTake ? item(t("heat.take"), "in_progress", function () { take(group); }) : null,
          canFix ? item(t("heat.mark_fixed"), "reported_fixed", function () { startFix(group); }) : null]);
      }
      return h("span", { "class": "bc-inbox__status-wrap" }, [btn, menu]);
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
      // Плотная строка 44 px, как в Linear: значок статуса · место · категория · «N человек · срок» · «›».
      var head = h("button", { "class": "bc-inbox__row", type: "button", "aria-expanded": expanded ? "true" : "false",
                               "data-key": group.key, onclick: function () { toggle(group); },
                               onmouseenter: function () { hover(group, true); }, onmouseleave: function () { hover(group, false); },
                               onfocus: function () { hover(group, true); }, onblur: function () { hover(group, false); } }, [
        h("span", { "class": "bc-inbox__text" }, [
          h("span", { "class": "bc-inbox__place" }, [h("strong", {}, place),
            // П. 8: акимат видит оригинал с пометкой (как карточка R07) — R10 B-064.
            group.rude ? h("span", { "class": "bk-tag bc-tag--rude" }, t("moderation.rude")) : null]),
          // Уточнение — после категории (UX_SPEC §10), не отдельный бейдж.
          h("span", { "class": "bc-inbox__what" }, [C().icon && C().categoryIcon ? C().icon(C().categoryIcon(group.category)) : null, h("span", {}, what)])]),
        h("span", { "class": "bc-inbox__meta" }, [t("inbox.people", { n: group.people }),
          group.complaints.length > 1 ? " · " + t("inbox.complaints", { n: group.complaints.length }) : "",
          due ? " · " : null, due]),
        C().icon ? C().icon("chevron-right") : null]);
      var li = h("li", { "class": "bc-inbox__item" + (expanded ? " bc-inbox__item--open" : "") +
                                  (state.hover && group.target && state.hover === group.target.id ? " bc-inbox__item--hover" : "") +
                                  (state.flash === group.key ? " bc-inbox__item--flash" : ""),
                         "data-demo": group.demo ? "true" : null, "data-key": group.key, "data-target": (group.target || {}).id || null },
        h("div", { "class": "bc-inbox__line" }, [statusControl(group), head]));
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
          staffHandle = window.BirgeComplaintStaff.mount(holder, { complaintId: main.id, csrf: csrfToken, openFix: state.openFix,
            onChange: function () { refreshCounts(); } });
          state.openFix = false;
        } else if (main && main.demo) {
          // Примеры не меняются (как в карточке R07: «Это пример: статус примеров не меняется»).
          holder.appendChild(h("p", { "class": "bc-meta" }, t("heat.example_readonly")));
        }
      }
      return li;
    }

    // Список ↔ карта (правило 5): наведение или фокус на строке — событие для карты (R07 подсвечивает значок цели);
    // с карты приходит то же событие — строка этой цели подсвечивается. detail: { kind, id, source } или null.
    function hover(group, on) {
      var target = group.target || {};
      if (!target.id) return;
      window.dispatchEvent(new CustomEvent("birge:target-hover", { detail: on ? { kind: target.kind, id: target.id, source: "inbox" } : null }));
    }
    function onMapHover(e) {
      var d = e.detail;
      if (d && d.source === "inbox") return;
      state.hover = d && d.id ? d.id : null;
      box.querySelectorAll(".bc-inbox__item").forEach(function (li) {
        li.classList.toggle("bc-inbox__item--hover", !!state.hover && li.getAttribute("data-target") === state.hover);
      });
    }

    function notify(text, isError, retry) {
      if (window.BirgeUI && typeof window.BirgeUI.toast === "function") {
        window.BirgeUI.toast(text, { type: isError ? "error" : "ok", action: retry ? { onClick: retry } : undefined });
        return;
      }
      var note = box.querySelector(".bc-inbox__note");
      if (note) { note.textContent = text; note.classList.toggle("bc-inbox__note--error", !!isError); }
    }

    // «Взять в работу» из строки: строка сразу переезжает в «В работе» (оптимистично), запросы — следом; если ни один не
    // прошёл — всё как было и сообщение с «Повторить». 404/409/422 по отдельной жалобе не обрывают остальные (как R07).
    function take(group) {
      state.menu = null;
      var ids = idsWith(group, ["new", "accepted"]);
      if (!ids.length) { render(); return; }
      var before = JSON.stringify(state.data);
      group.complaints.forEach(function (c) { if (ids.indexOf(c.id) >= 0) c.status = "in_progress"; });
      var counts = state.data.counts || (state.data.counts = {});
      if (group.tab === "new") {
        counts["new"] = Math.max(0, (counts["new"] || 0) - 1);
        counts.in_progress = (counts.in_progress || 0) + 1;
        group.tab = "in_progress";
      }
      state.flash = group.key;
      render();
      notify(t("heat.toast_taken"));
      ids.reduce(function (chain, id) {
        return chain.then(function (acc) {
          return call("POST", "/complaints/" + encodeURIComponent(id) + "/status", { status: "in_progress" }).then(function (r) {
            if (r.ok) acc.done += 1; else if (r.status === 404 || r.status === 409 || r.status === 422) acc.skipped += 1; else acc.failed += 1;
            return acc;
          });
        });
      }, Promise.resolve({ done: 0, skipped: 0, failed: 0 })).then(function (acc) {
        if (!alive) return;
        state.flash = null;
        if (!acc.done && acc.failed) {
          state.data = JSON.parse(before);
          render();
          var again = state.data.items.filter(function (g) { return g.key === group.key; })[0];
          notify(t("heat.action_failed"), true, again ? function () { take(again); } : null);
          return;
        }
        load(true);
      });
    }

    function startFix(group) {
      state.menu = null;
      state.open = group.key;
      state.openFix = true;
      render();
      var what = box.querySelector(".bc-inbox__item--open [name=what_done]");
      if (what) what.focus();
    }

    function toggle(group) {
      state.menu = null;
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
        var openLogin = function () { if (window.BirgeShell) window.BirgeShell.setSection("map"); if (shell && shell.openEditor) shell.openEditor(); };
        // Одно состояние «войдите как сотрудник» на все разделы — BirgeUI.loginState ui-kit R11 (16.3); без него — своё такое же.
        if (window.BirgeUI && typeof window.BirgeUI.loginState === "function") {
          var holder = h("div", { "class": "bc-inbox__login" });
          box.appendChild(holder);
          window.BirgeUI.loginState(holder, openLogin);
          return;
        }
        // Тот же вид (R11 INTEGRATION 9.3 b): иллюстрация staff, подсказка, «Войти» — главная: без входа карточки действий
        // нет, это единственная кнопка экрана (10.3).
        box.appendChild(h("div", { "class": "bk-empty", role: "status" }, [art("staff", "user"),
          h("p", { "class": "bk-empty__title" }, t("proposal.need_staff")),
          h("p", { "class": "bk-empty__text" }, t("staff.login.note")),
          h("button", { "class": "bk-btn bk-btn--primary", type: "button", onclick: openLogin }, t("staff.login.submit"))]));
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
        // Скелетон строк — только если ответ дольше 150 мс (быстрый ответ не мигает серыми полосами).
        if (!state.slow) { box.appendChild(h("div", { "class": "bc-loading", role: "status" }, h("span", { "class": "bc-loading__text bc-sr" }, t("mine.loading")))); return; }
        var skel = function () { return h("div", { "class": "bc-skel-row", "aria-hidden": "true" }, [
          h("span", { "class": "bk-skel bc-skel-dot" }), h("span", { "class": "bk-skel bc-skel-line bc-skel-line--title" }),
          h("span", { "class": "bk-skel bc-skel-line bc-skel-line--short" })]); };
        box.appendChild(h("div", { "class": "bc-loading bc-loading--rows", role: "status" }, [skel(), skel(), skel(), skel(),
          h("span", { "class": "bc-loading__text" }, t("mine.loading"))]));
        return;
      }
      box.appendChild(tabs());
      box.appendChild(h("p", { "class": "bc-inbox__note bc-sr", role: "status" }));
      var items = (state.data.items || []).filter(function (g) { return state.tab === "all" || g.tab === state.tab; });
      if (!items.length) {
        box.appendChild(h("div", { "class": "bk-empty" }, [art("done", "check"), h("p", { "class": "bk-empty__title" }, t("inbox.empty"))]));
        return;
      }
      // Группы по статусу, как в Linear: заголовок группы — значок статуса, название, число; строки — плотный список.
      var groups = h("div", { "class": "bc-inbox__groups" + (state.enter ? " bc-list--enter" : ""), role: "tabpanel" });
      TABS.forEach(function (tab) {
        var list = items.filter(function (g) { return g.tab === tab; });
        if (!list.length) return;
        var gid = "bc-inbox-g-" + tab;
        groups.appendChild(h("section", { "class": "bc-inbox__group", "data-group": tab, "aria-labelledby": gid }, [
          h("h3", { "class": "bc-inbox__ghead", id: gid }, [sicon(tabStatus(tab)), h("span", {}, t("inbox.tab." + tab)),
            h("span", { "class": "bc-inbox__gcount" }, String(list.length))]),
          h("ul", { "class": "bc-inbox__list" }, list.map(row))]));
      });
      box.appendChild(groups);
      state.enter = false;
      if (items.some(function (g) { return g.demo; })) box.appendChild(h("p", { "class": "bk-footnote bc-demo-note" }, t("common.tag.demo_hint")));
      if (state.menu) {
        var first = box.querySelector(".bc-inbox__menu .bc-inbox__menu-item");
        if (first) first.focus();
      }
    }

    // Клавиатура списка (как в Linear): ↑ ↓ (и J K) — по строкам, Esc — закрыть меню статуса; в меню — ↑ ↓ по пунктам.
    function onKey(e) {
      var row = e.target.closest && e.target.closest(".bc-inbox__row, .bc-inbox__menu-item");
      if (e.key === "Escape" && state.menu) {
        var key = state.menu; state.menu = null; render();
        var back = box.querySelector('.bc-inbox__status--btn[data-key="' + key.replace(/"/g, "") + '"]');
        if (back) back.focus();
        e.preventDefault(); return;
      }
      if (!row || e.altKey || e.ctrlKey || e.metaKey) return;
      var down = e.key === "ArrowDown" || e.key === "j" || e.key === "J";
      var up = e.key === "ArrowUp" || e.key === "k" || e.key === "K";
      if (!down && !up) return;
      var all = Array.prototype.slice.call(box.querySelectorAll(row.classList.contains("bc-inbox__menu-item") ? ".bc-inbox__menu-item" : ".bc-inbox__row"));
      var next = all[all.indexOf(row) + (down ? 1 : -1)];
      if (next) { next.focus(); next.scrollIntoView({ block: "nearest" }); }
      e.preventDefault();
    }
    function onOutside(e) {
      if (state.menu && !(e.target.closest && e.target.closest(".bc-inbox__status-wrap"))) { state.menu = null; render(); }
    }
    box.addEventListener("keydown", onKey);
    document.addEventListener("click", onOutside);
    window.addEventListener("birge:target-hover", onMapHover);

    // Язык: оболочка зовёт setLang(lang); словарь R11 грузится асинхронно и потом шлёт "birge:lang" — перерисуем и тогда.
    function onLang() { if (alive) render(); }
    window.addEventListener("birge:lang", onLang);
    load();
    return {
      refresh: function () { return load(true); },
      setLang: function () { render(); },
      destroy: function () {
        alive = false; closeStaff(); window.removeEventListener("birge:lang", onLang);
        document.removeEventListener("click", onOutside); window.removeEventListener("birge:target-hover", onMapHover);
        if (box.parentNode) box.parentNode.removeChild(box);
      }
    };
  }

  window.BirgeComplaintList = { mount: mount };
})();
