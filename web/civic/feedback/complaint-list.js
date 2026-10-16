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
 *
 * Раунд 15: у совместного обращения под строкой — части служб («◐ Водоканал · ○ Дорожная служба»), статус части
 * меняется прямо отсюда (меню «ждёт · в работе · сделано»). Фильтр одной службы — #complaints/service=<id> (ссылка
 * из «Штаба ведомств» R17) или opts.service. Жалобы демо-мира R02 (world) — рабочие: на них идут сцены 7–9.
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

  // Подпись вкладки. «Просрочено» у R09 — СРОК ПЕРВОГО ОТВЕТА (жалоба «Новое»), у R08/R17 — срок исправления: разные числа,
  // поэтому и подписи разные (предложение R02 §3): «Ответ просрочен» / «Жауап мерзімі өтті».
  function tabLabel(id) {
    if (id === "overdue") { var label = t("inbox.tab.overdue_answer"); if (label) return label; }
    return t("inbox.tab." + id);
  }

  // #complaints/service=water — «Обращения» одной службы (R17). Только id из справочника (буквы и _).
  function serviceFromHash() {
    var m = /[#/&?]service=([a-z_]{2,30})(?:$|[&/])/.exec(window.location.hash || "");
    return m ? m[1] : null;
  }
  // #complaints/district=nura — «Обращения» района (те же числа, что «Нура · N» на карте и в «Картине дня»).
  function districtFromHash() {
    var m = /[#/&?]district=([a-z][a-z0-9_-]{1,39})(?:$|[&/])/.exec(window.location.hash || "");
    return m ? m[1] : null;
  }
  // R17 «Штаб ведомств» → «Открыть в «Обращениях»» (INTEGRATION R17 §4): перед переходом в раздел кладёт
  // sessionStorage["birge.inbox.filter"] = {service, ids} и шлёт на document событие "birge:inbox-filter" с тем же
  // detail. Фильтр берём один раз (ключ удаляем): следующий заход в «Обращения» — снова все службы.
  var FILTER_KEY = "birge.inbox.filter";
  function cleanFilter(value) {
    if (!value || typeof value !== "object") return null;
    var service = typeof value.service === "string" && /^[a-z_]{2,30}$/.test(value.service) ? value.service : null;
    var ids = (Array.isArray(value.ids) ? value.ids : []).filter(function (id) {
      return typeof id === "string" && /^[A-Za-z0-9_-]{1,80}$/.test(id);
    }).slice(0, 200);
    return service || ids.length ? { service: service, ids: ids } : null;
  }
  function takeStoredFilter() {
    var raw = null;
    try { raw = window.sessionStorage.getItem(FILTER_KEY); window.sessionStorage.removeItem(FILTER_KEY); } catch (e) { return null; }
    if (!raw) return null;
    try { return cleanFilter(JSON.parse(raw)); } catch (e) { return null; }
  }
  // Путь раздела оболочки R01 (IA_ROUND15 §7.3, opts.path и handle.setPath): #inbox/<id жалобы> — открыть это обращение
  // (сцена 8 — #inbox/c-w1500010); #inbox/service=water, #inbox/district=nura — «Обращения» службы или района.
  function parsePath(path) {
    var p = typeof path === "string" ? path.replace(/^\/+|\/+$/g, "") : "";
    if (/^c-[A-Za-z0-9_-]{1,80}$/.test(p)) return { id: p };
    var m = /^service=([a-z_]{2,30})$/.exec(p);
    if (m) return { service: m[1] };
    m = /^district=([a-z][a-z0-9_-]{1,39})$/.exec(p);
    return m ? { district: m[1] } : null;
  }
  var live = null;   // смонтированный экран — для BirgeComplaintList.setPath (по нему оболочка видит, что путь понятен)
  // Название района: словарь R11 (district.<id>), иначе id как есть.
  function districtLabel(id) {
    var key = "district." + id;
    var label = C().t(key);
    return label && label !== key ? label : id;
  }

  function deadlineNode(d) {
    if (!d || d.state === "answered") return null;
    if (d.state === "overdue") return h("span", { "class": "bc-deadline bc-deadline--danger" }, t("deadline.overdue", { n: d.overdue_working_days || 1 }));
    if (d.state === "today") return h("span", { "class": "bc-deadline bc-deadline--warn" }, t("deadline.today"));
    var left = d.working_days_left || 0;
    return h("span", { "class": "bc-deadline" + (left <= 1 ? " bc-deadline--warn" : "") }, t("deadline.left", { n: left }));
  }

  // Команды для палитры Ctrl+K оболочки R01 (правило 2 эталона: «сменить статус» из палитры). Только действия, которые
  // и так есть в строке «Обращений»: «Взять в работу — <место>» (сразу) и «Отметить исправленным — <место>» (открывает
  // строку с формой «что сделали»). commands({ api }) → Promise<[{ id, title, hint, run() }]>; примеры (demo) не меняются.
  var pendingOpen = null;   // { key, fix } — какую строку открыть, когда список смонтируют / загрузят
  // Пример, который нельзя менять: синтетика шага 2 демо («Хан Шатыр»). Жалобы демо-мира (world) и «ИИ-разбора пачки»
  // (intake, П3: пример пачки — тоже demo) — рабочие.
  function readonly(c) { return !!(c && c.demo && !c.world && !c.intake); }
  function commands(opts) {
    opts = opts || {};
    var call = client(opts);
    var ids = function (g, statuses) {
      return g.complaints.filter(function (c) { return !readonly(c) && statuses.indexOf(c.status) >= 0; }).map(function (c) { return c.id; });
    };
    return call("GET", "/complaints/inbox").then(function (res) {
      if (!res.ok) return [];
      var out = [];
      (res.data.items || []).forEach(function (g) {
        if (g.demo && !g.world && !g.intake) return;
        var place = C().targetLabel(g.target), hint = C().categoryLabel(g.category) + " · " + t("inbox.people", { n: g.people });
        var take = ids(g, ["new", "accepted"]), fix = ids(g, ["new", "accepted", "in_progress"]);
        if (take.length) out.push({ id: "take:" + g.key, title: t("heat.take") + " — " + place, hint: hint, run: function () {
          return take.reduce(function (chain, id) {
            return chain.then(function () { return call("POST", "/complaints/" + encodeURIComponent(id) + "/status", { status: "in_progress" }); });
          }, Promise.resolve()).then(function () { window.dispatchEvent(new CustomEvent("birge:inbox-changed")); });
        } });
        if (fix.length) out.push({ id: "fix:" + g.key, title: t("heat.mark_fixed") + " — " + place, hint: hint, run: function () {
          pendingOpen = { key: g.key, fix: true };
          if (window.BirgeShell && typeof window.BirgeShell.setSection === "function") window.BirgeShell.setSection("complaints");
          window.dispatchEvent(new CustomEvent("birge:inbox-open", { detail: pendingOpen }));
        } });
      });
      return out;
    });
  }

  function mount(root, opts) {
    opts = opts || {};
    var call = client(opts);
    var box = h("section", { "class": "bc-inbox", "aria-labelledby": "bc-inbox-title" });
    root.appendChild(box);
    // tab: "all" — все группы по статусу (как в Linear); или одна вкладка-фильтр. menu — ключ строки с открытым меню статуса.
    var asked = takeStoredFilter();
    var fromPath = parsePath(opts.path) || {};
    var state = { data: null, error: false, tab: "all", open: null, openFix: false, menu: null, slow: false, hover: null,
                  service: opts.service || serviceFromHash() || fromPath.service || (asked && asked.service) || null,
                  district: opts.district || districtFromHash() || fromPath.district || null, partMenu: null };
    // Одно обращение — из пути оболочки (#inbox/c-…) или из табло R17 (строка «Совместные»): после загрузки сразу
    // открыть его строку и прокрутить к ней (scrollOpen).
    var askedId = fromPath.id || (asked && asked.ids.length === 1 ? asked.ids[0] : null);
    var scrollOpen = false;
    var staffHandle = null;
    var alive = true;
    // П3 (кадр 05 review_final51): «Обращения» — на всю ширину листа оболочки, без пустых полей. На ≥ 1200 px — две
    // колонки, как в почте: список | карточка, у каждой своя прокрутка (экран — ровно по высоте листа). Ниже — одна колонка,
    // лист прокручивается как прежде, а липкая плашка группы встаёт к самому краю листа: над ней не видно уехавших строк.
    var splitMq = window.matchMedia ? window.matchMedia("(min-width: 1200px)") : null;
    var layout = { split: false };

    function scrollParent() {
      for (var el = box.parentElement; el && el !== document.body && el !== document.documentElement; el = el.parentElement) {
        var oy = window.getComputedStyle(el).overflowY;
        if ((oy === "auto" || oy === "scroll") && el.clientHeight > 0) return el;
      }
      return null;
    }
    // Замер листа: его отступ сверху (плашке группы — top: -отступ) и сколько высоты остаётся экрану. -> сменилась ли
    // раскладка (одна колонка ↔ две): перерисовываем только тогда.
    function measure() {
      var sheet = scrollParent(), pad = 0, fit = 0;
      if (sheet) {
        var cs = window.getComputedStyle(sheet);
        pad = parseFloat(cs.paddingTop) || 0;
        var top = box.getBoundingClientRect().top - sheet.getBoundingClientRect().top - sheet.clientTop + sheet.scrollTop;
        fit = Math.floor(sheet.clientHeight - top - (parseFloat(cs.paddingBottom) || 0));
      }
      box.style.setProperty("--bc-stick", (-pad) + "px");
      var split = !!(splitMq && splitMq.matches) && box.clientWidth >= 860 && fit >= 360;
      if (split) box.style.setProperty("--bc-fit-h", fit + "px"); else box.style.removeProperty("--bc-fit-h");
      var changed = split !== layout.split;
      layout.split = split;
      return changed;
    }
    var relayoutTimer = null;
    function relayout() {
      clearTimeout(relayoutTimer);
      relayoutTimer = setTimeout(function () { if (alive && measure()) render(); }, 100);
    }

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
      return call("GET", inboxPath()).then(function (res) {
        if (!alive) return;
        // 401/403 — не вошёл сотрудник (R11 разбор FINAL-3): это не «нет связи», а «войдите»
        if (!res.ok) {
          if (silent && state.data) return;   // фоновое обновление не роняет список, который уже на экране
          state.error = res.status === 401 || res.status === 403 ? "staff" : true; state.data = null; render(); return;
        }
        state.enter = !state.data;   // первые данные — строки мягко появляются; обновление на месте — без движения
        state.data = res.data;
        takePending();
        openAsked();
        render();
      });
    }

    function title() {
      var tag = opts.titleTag || "h2";
      var heading = h(tag, { "class": "bc-inbox__title", id: "bc-inbox-title" }, t("shell.nav.inbox"));
      // П3: «Разобрать пачку» — вход в «ИИ-разбор пачки обращений» R04 (раздел #intake оболочки R01; R11 IA §11.1:
      // шапка списка справа, вторичная .bk-btn со значком i-ai). Только когда экран R04 есть в сборке (window.BirgeIntake):
      // в FINAL-5.1 кнопки нет.
      if (!(window.BirgeIntake && typeof window.BirgeIntake.mount === "function")) return heading;
      var open = function () {
        if (typeof opts.openSection === "function") { opts.openSection("intake"); return; }
        if (window.BirgeShell && typeof window.BirgeShell.setSection === "function") { window.BirgeShell.setSection("intake"); return; }
        window.location.hash = "#intake";
      };
      return h("div", { "class": "bc-inbox__head" }, [heading,
        h("button", { "class": "bk-btn bc-inbox__intake", type: "button", onclick: open },
          [C().icon ? C().icon("ai") : null, h("span", {}, t("inbox.intake.open"))])]);
    }

    // Фильтр одной службы (R17 «Штаб ведомств» → строка службы): чип «Служба: Водоканал ×» над вкладками.
    function inboxPath() {
      var q = [];
      if (state.service) q.push("service=" + encodeURIComponent(state.service));
      if (state.district) q.push("district=" + encodeURIComponent(state.district));
      return "/complaints/inbox" + (q.length ? "?" + q.join("&") : "");
    }
    // Чипы фильтров над вкладками: «Служба: Водоканал ×» (R17), «Район: Нура ×» (карта R07, «Картина дня» R08).
    function serviceFilter() {
      if (!state.service && !state.district) return null;
      var chip = function (key, label, clearLabel) {
        return h("button", { "class": "bk-chip bc-inbox__filter-chip", type: "button", "aria-pressed": "true", "data-filter": key,
                             "aria-label": clearLabel,
                             onclick: function () {
                               state[key] = null;
                               if (new RegExp(key + "=").test(window.location.hash)) {
                                 // Раздел оставляем тем же (#inbox оболочки R01 или прежний #complaints), снимаем только фильтр.
                                 var base = (window.location.hash || "").split("/")[0] || "#complaints";
                                 try { history.replaceState(null, "", window.location.pathname + window.location.search + base); } catch (e) { /* */ }
                               }
                               state.data = null; load();
                             } },
          [h("span", {}, label), C().icon ? C().icon("close") : null]);
      };
      return h("div", { "class": "bk-chips bc-inbox__filter" }, [
        state.service ? chip("service", t("inbox.filter.service", { service: t("service." + state.service) || state.service }),
                             t("inbox.filter.clear")) : null,
        state.district ? chip("district", t("inbox.filter.district", { district: districtLabel(state.district) }),
                              t("inbox.filter.clear_district")) : null]);
    }
    function onHash() {
      var sid = serviceFromHash(), did = districtFromHash();
      if ((sid && sid !== state.service) || (did && did !== state.district)) {
        state.service = sid || state.service; state.district = did || state.district; state.data = null; load();
      }
    }
    // Фильтр R17 событием (список уже смонтирован): служба — перезагрузить «Обращения» этой службы; одно обращение — открыть.
    function onFilter(e) {
      try { window.sessionStorage.removeItem(FILTER_KEY); } catch (err) { /* без хранилища */ }
      var f = cleanFilter(e && e.detail);
      if (!f) return;
      askedId = f.ids.length === 1 ? f.ids[0] : null;
      if (f.service && f.service !== state.service) { state.service = f.service; state.data = null; load(); return; }
      if (openAsked()) render();
    }
    function openAsked() {
      if (!askedId || !state.data) return false;
      var want = askedId, found = null;
      (state.data.items || []).some(function (g) {
        if ((g.complaints || []).some(function (c) { return c.id === want; })) { found = g; return true; }
        return false;
      });
      if (!found) return false;
      askedId = null;
      state.tab = "all"; state.menu = null; state.open = found.key; state.openFix = false;
      scrollOpen = true;
      return true;
    }
    // Оболочка R01 сменила путь раздела без перемонтажа (handle.setPath): обращение — открыть, служба/район — фильтр.
    function setPath(path) {
      var p = parsePath(path);
      if (!p) return;
      if (p.id) { askedId = p.id; if (openAsked()) render(); return; }
      if ((p.service && p.service !== state.service) || (p.district && p.district !== state.district)) {
        state.service = p.service || state.service; state.district = p.district || state.district;
        state.data = null; load();
      }
    }

    // Части служб совместного обращения — под строкой: значок статуса · служба; нажатие — меню статуса части.
    function partsLine(group) {
      if (!group.joint || !(group.services || []).length) return null;
      var main = group.complaints[0];
      var editable = main && !readonly(main) && ["new", "accepted", "in_progress"].indexOf(main.status) >= 0;
      return h("ul", { "class": "bc-inbox__parts", "aria-label": t("joint.title") }, group.services.map(function (part) {
        var label = (t("service." + part.service) || part.service) + " — " + t("joint.part." + part.status);
        var key = group.key + "|" + part.service;
        var open = state.partMenu === key;
        var chip = editable
          ? h("button", { "class": "bc-inbox__part", type: "button", "data-service": part.service, "data-status": part.status,
                          "aria-haspopup": "menu", "aria-expanded": open ? "true" : "false",
                          "aria-label": t("joint.part.menu", { service: t("service." + part.service) || part.service }) + ": " + t("joint.part." + part.status),
                          onclick: function (e) { e.stopPropagation(); state.partMenu = open ? null : key; state.menu = null; render(); } },
              [partIcon(part.status), h("span", {}, label)])
          : h("span", { "class": "bc-inbox__part", "data-service": part.service, "data-status": part.status },
              [partIcon(part.status), h("span", {}, label)]);
        var menu = null;
        if (open) {
          menu = h("div", { "class": "bk-menu bc-inbox__menu bc-inbox__partmenu", role: "menu",
                            "aria-label": t("joint.part.menu", { service: t("service." + part.service) || part.service }) },
            ["todo", "in_progress", "done"].map(function (st) {
              return h("button", { "class": "bk-menu__item bc-inbox__menu-item", type: "button", role: "menuitem",
                                   "aria-checked": part.status === st ? "true" : "false",
                                   onclick: function (e) { e.stopPropagation(); setPart(group, part, st); } },
                [partIcon(st), h("span", {}, t("joint.part." + st))]);
            }));
        }
        return h("li", { "class": "bc-inbox__partwrap" }, [chip, menu]);
      }));
    }

    // Карточка сотрудника изменила службы (подсказка R04, совместное исполнение, передача, часть) — строка частей под
    // строкой обновляется на месте: список не перерисовывается, открытая карточка и её форма не прыгают.
    function syncParts(group, complaint) {
      var j = complaint && complaint.joint;
      if (!j || !j.services) return;
      group.services = j.services.map(function (p) { return { service: p.service, role: p.role, status: p.status }; });
      group.joint = group.services.length > 1;
      if (group.complaints[0] && complaint.status) group.complaints[0].status = complaint.status;
      var li = box.querySelector('.bc-inbox__item[data-key="' + String(group.key).replace(/"/g, "") + '"]');
      if (!li) return;
      var old = li.querySelector(":scope > .bc-inbox__parts");
      var fresh = partsLine(group);
      if (old && fresh) li.replaceChild(fresh, old);
      else if (old) li.removeChild(old);
      else if (fresh) li.insertBefore(fresh, li.querySelector(":scope > .bc-inbox__detail"));
    }

    // Статус части из строки: сразу на экране (оптимистично), запрос — следом; ошибка — как было и «Повторить».
    function setPart(group, part, status) {
      state.partMenu = null;
      if (part.status === status) { render(); return; }
      // «Сделано» — с обязательной строкой «что сделала служба»: открываем карточку с формой заметки этой службы.
      if (status === "done") {
        state.open = group.key; state.openPart = part.service; render();
        var note = box.querySelector(".bc-inbox__detail [name=part_note]");
        if (note) note.focus();
        return;
      }
      var before = JSON.stringify(state.data);
      var was = part.status;
      part.status = status;
      state.flash = group.key;
      render();
      call("POST", "/complaints/" + encodeURIComponent(group.complaints[0].id) + "/part",
           { service: part.service, status: status, expected: was }).then(function (r) {
        if (!alive) return;
        state.flash = null;
        if (!r.ok) {
          state.data = JSON.parse(before); render();
          notify(t("heat.action_failed"), true, function () {
            var again = (state.data.items || []).filter(function (g) { return g.key === group.key; })[0];
            var p2 = again && (again.services || []).filter(function (p) { return p.service === part.service; })[0];
            if (again && p2) setPart(again, p2, status);
          });
          return;
        }
        notify(t("joint.part.saved", { service: t("service." + part.service) || part.service, status: t("joint.part." + status) }));
        load(true);
      });
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
          [h("span", {}, id === "all" ? t("staff.cabinet.tab.all") : tabLabel(id)), countBadge(id === "all" ? total : counts[id])]));
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
      return group.complaints.filter(function (c) { return !readonly(c) && statuses.indexOf(c.status) >= 0; })
        .map(function (c) { return c.id; });
    }
    function sicon(status) { return C().statusIcon ? C().statusIcon(status) : null; }
    function partIcon(status) { return sicon({ todo: "new", in_progress: "in_progress", done: "reported_fixed" }[status] || "new"); }

    // Смена статуса прямо из строки (правило 5 эталона, как в Linear): значок статуса — кнопка, меню из того, что можно
    // сделать сейчас: «Взять в работу» (сразу, с мгновенным откликом) и «Отметить исправленным» (форма в строке).
    function statusControl(group) {
      var st = groupStatus(group);
      var canTake = idsWith(group, ["new", "accepted"]).length > 0;
      var canFix = idsWith(group, ["new", "accepted", "in_progress"]).length > 0;
      if (!canTake && !canFix) {
        return h("span", { "class": "bk-lrow__st bc-inbox__status", title: t("status." + st) }, sicon(st));
      }
      var open = state.menu === group.key;
      var btn = h("button", { "class": "bk-lrow__st bc-inbox__status bc-inbox__status--btn", type: "button", "aria-haspopup": "menu",
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

    function placeLabel(group) {
      var place = C().targetLabel(group.target);
      // Общая подпись «Примерное место» у нескольких строк неразличима (R11 разбор 5 №4б) — добавляем номер.
      if (group.target && group.target.approximate && place === t("complaint.step2.approximate") && group.complaints[0]) {
        place += " · " + group.complaints[0].code;
      }
      return place;
    }

    // Раскрытая группа: «Показать на карте», номера жалоб группы и карточка действий сотрудника (complaint-staff.js).
    // Одна колонка — под строкой; две колонки (≥ 1200 px) — справа, с названием места сверху.
    function detailNode(group, inPane) {
      var detail = h("div", { "class": "bc-inbox__detail", "data-key": group.key });
      if (inPane) detail.appendChild(h("h3", { "class": "bc-inbox__pane-title" }, placeLabel(group)));
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
      if (main && !readonly(main) && window.BirgeComplaintStaff) {
        staffHandle = window.BirgeComplaintStaff.mount(holder, { complaintId: main.id, csrf: csrfToken, openFix: state.openFix,
          openPart: state.openPart || null,
          onChange: function (complaint) { syncParts(group, complaint); refreshCounts(); } });
        state.openFix = false; state.openPart = null;
      } else if (main && readonly(main)) {
        // Примеры не меняются (как в карточке R07: «Это пример: статус примеров не меняется»).
        holder.appendChild(h("p", { "class": "bc-meta" }, t("heat.example_readonly")));
      }
      return detail;
    }

    function row(group) {
      var expanded = state.open === group.key;
      var place = placeLabel(group);
      var what = C().categoryLabel(group.category) + (group.subtopic ? " · " + C().subtopicLabel(group.category, group.subtopic) : "") +
        (group.complaints.length > 1 ? " · " + t("inbox.complaints", { n: group.complaints.length }) : "");
      var due = deadlineNode(group.deadline);
      var level = group.people >= 10 ? 4 : (group.people >= 6 ? 3 : (group.people >= 3 ? 2 : 1));
      var people = t("inbox.people", { n: group.people });
      // Строка Linear ui-kit R11 (.bk-lrow, правило 5): значок статуса · место (500) · «категория · уточнение» серым ·
      // число людей плашкой цвета карты (.bk-lrow__cnt) · срок (.bk-lrow__time) · «›».
      var head = h("button", { "class": "bc-inbox__row", type: "button", "aria-expanded": expanded ? "true" : "false",
                               "data-key": group.key, onclick: function () { toggle(group); },
                               onmouseenter: function () { hover(group, true); }, onmouseleave: function () { hover(group, false); },
                               onfocus: function () { hover(group, true); }, onblur: function () { hover(group, false); } }, [
        h("span", { "class": "bk-lrow__main bc-inbox__text" }, [
          h("span", { "class": "bk-lrow__title bc-inbox__place" }, [place,
            // П. 8: акимат видит оригинал с пометкой (как карточка R07) — R10 B-064.
            group.rude ? h("span", { "class": "bk-tag bc-tag--rude" }, t("moderation.rude")) : null,
            // П3: задача создана «ИИ-разбором пачки» R04 — тихая пометка источника (в карточке — «Источник: …»).
            group.intake ? h("span", { "class": "bk-tag bc-tag--intake", title: t("inbox.source.intake") },
              t("inbox.source.intake_short")) : null]),
          // Уточнение — после категории (UX_SPEC §10), не отдельный бейдж.
          h("span", { "class": "bk-lrow__meta bc-inbox__what" }, what)]),
        h("span", { "class": "bk-lrow__cnt bc-inbox__cnt", "data-level": String(level), title: people },
          [h("span", { "aria-hidden": "true" }, String(group.people)), h("span", { "class": "bc-sr" }, people)]),
        h("span", { "class": "bk-lrow__time bc-inbox__meta" }, due || ""),
        C().icon ? C().icon("chevron-right") : null]);
      var li = h("li", { "class": "bc-inbox__item" + (expanded ? " bc-inbox__item--open" : "") +
                                  (state.flash === group.key ? " bc-inbox__item--flash" : ""),
                         "data-demo": group.demo ? "true" : null, "data-world": group.world ? "true" : null,
                         "data-key": group.key, "data-target": (group.target || {}).id || null },
        h("div", { "class": "bk-lrow bc-inbox__line" + (state.hover && group.target && state.hover === group.target.id ? " is-hover" : "") },
          [statusControl(group), head]));
      var partsNode = partsLine(group);
      if (partsNode) li.appendChild(partsNode);
      if (expanded && !layout.split) li.appendChild(detailNode(group, false));
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
        var line = li.querySelector(".bk-lrow");
        if (line) line.classList.toggle("is-hover", !!state.hover && li.getAttribute("data-target") === state.hover);
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

    // Строку попросили открыть из палитры команд (или до того, как список смонтировали).
    function takePending() {
      if (!pendingOpen || !state.data) return false;
      var want = pendingOpen;
      var found = (state.data.items || []).some(function (g) { return g.key === want.key; });
      if (!found) return false;
      pendingOpen = null;
      state.tab = "all"; state.menu = null; state.open = want.key; state.openFix = !!want.fix;
      return true;
    }
    function onOpenRequest() { if (takePending()) { render(); var what = box.querySelector(".bc-inbox__detail [name=what_done]"); if (what) what.focus(); } }
    function onChanged() { load(true); }

    function startFix(group) {
      state.menu = null;
      state.open = group.key;
      state.openFix = true;
      render();
      var what = box.querySelector(".bc-inbox__detail [name=what_done]");
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
      call("GET", inboxPath()).then(function (res) {
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
      measure();
      // Две колонки: список и карточка — свои прокрутки; перерисовка не сбрасывает их на начало.
      var oldList = box.querySelector(".bc-inbox__groups"), oldPane = box.querySelector(".bc-inbox__pane");
      var keepList = layout.split && oldList ? oldList.scrollTop : 0;
      var keepPane = layout.split && oldPane && oldPane.getAttribute("data-key") === (state.open || "") ? oldPane.scrollTop : 0;
      box.innerHTML = "";
      if (layout.split) box.setAttribute("data-split", ""); else box.removeAttribute("data-split");
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
        var skel = function () { return h("div", { "class": "bk-lrow bk-lrow--skel bc-skel-row", "aria-hidden": "true" }, [
          h("span", { "class": "bk-skel bc-skel-dot" }), h("span", { "class": "bk-skel bc-skel-line bc-skel-line--title" }),
          h("span", { "class": "bk-skel bc-skel-line bc-skel-line--short" })]); };
        box.appendChild(h("div", { "class": "bc-loading bc-loading--rows", role: "status" }, [skel(), skel(), skel(), skel(),
          h("span", { "class": "bc-loading__text" }, t("mine.loading"))]));
        return;
      }
      var filter = serviceFilter();
      if (filter) box.appendChild(filter);
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
          h("h3", { "class": "bk-lgroup bc-inbox__ghead", id: gid }, [sicon(tabStatus(tab)), h("span", {}, tabLabel(tab)),
            h("span", { "class": "bk-lgroup__count bc-inbox__gcount" }, String(list.length))]),
          h("ul", { "class": "bk-llist bc-inbox__list" }, list.map(row))]));
      });
      if (layout.split) {
        var openGroup = null;
        items.some(function (g) { if (g.key === state.open) { openGroup = g; return true; } return false; });
        var pane = h("div", { "class": "bc-inbox__pane", "data-key": openGroup ? openGroup.key : null, role: "region",
                              "aria-label": openGroup ? placeLabel(openGroup) : t("inbox.pane.empty") },
          openGroup ? detailNode(openGroup, true) : h("p", { "class": "bc-inbox__pane-empty" }, t("inbox.pane.empty")));
        box.appendChild(h("div", { "class": "bc-inbox__body" }, [groups, pane]));
        if (keepList) groups.scrollTop = keepList;
        if (keepPane) pane.scrollTop = keepPane;
      } else {
        box.appendChild(groups);
      }
      state.enter = false;
      if (scrollOpen) {   // открыто по пути или из табло R17 — строка в видимой части экрана, а не ниже края
        scrollOpen = false;
        var opened = box.querySelector(".bc-inbox__item--open");
        if (opened && opened.scrollIntoView) opened.scrollIntoView({ block: "start" });
      }
      if (items.some(function (g) { return g.demo; })) box.appendChild(h("p", { "class": "bk-footnote bc-demo-note" }, t("common.tag.demo_hint")));
      if (state.menu || state.partMenu) {
        var first = box.querySelector(".bc-inbox__menu .bc-inbox__menu-item[aria-checked=false], .bc-inbox__menu .bc-inbox__menu-item");
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
      if (e.key === "Escape" && state.partMenu) {
        var service = state.partMenu.split("|").pop(); state.partMenu = null; render();
        var chip = box.querySelector('.bc-inbox__part[data-service="' + service.replace(/"/g, "") + '"]');
        if (chip) chip.focus();
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
      if (state.partMenu && !(e.target.closest && e.target.closest(".bc-inbox__partwrap"))) { state.partMenu = null; render(); }
    }
    box.addEventListener("keydown", onKey);
    window.addEventListener("resize", relayout);
    if (splitMq && splitMq.addEventListener) splitMq.addEventListener("change", relayout);
    else if (splitMq && splitMq.addListener) splitMq.addListener(relayout);
    var sizeWatch = window.ResizeObserver ? new window.ResizeObserver(relayout) : null;
    if (sizeWatch) sizeWatch.observe(box);
    document.addEventListener("click", onOutside);
    window.addEventListener("birge:target-hover", onMapHover);
    window.addEventListener("birge:inbox-open", onOpenRequest);
    window.addEventListener("birge:inbox-changed", onChanged);
    window.addEventListener("hashchange", onHash);
    document.addEventListener("birge:inbox-filter", onFilter);

    // Язык: оболочка зовёт setLang(lang); словарь R11 грузится асинхронно и потом шлёт "birge:lang" — перерисуем и тогда.
    function onLang() { if (alive) render(); }
    window.addEventListener("birge:lang", onLang);
    load();
    var handle = {
      refresh: function () { return load(true); },
      setLang: function () { render(); },
      setPath: setPath,
      destroy: function () {
        alive = false; closeStaff(); window.removeEventListener("birge:lang", onLang);
        clearTimeout(relayoutTimer); window.removeEventListener("resize", relayout);
        if (splitMq && splitMq.removeEventListener) splitMq.removeEventListener("change", relayout);
        else if (splitMq && splitMq.removeListener) splitMq.removeListener(relayout);
        if (sizeWatch) sizeWatch.disconnect();
        if (live === handle) live = null;
        document.removeEventListener("click", onOutside); window.removeEventListener("birge:target-hover", onMapHover);
        window.removeEventListener("birge:inbox-open", onOpenRequest); window.removeEventListener("birge:inbox-changed", onChanged);
        window.removeEventListener("hashchange", onHash);
        document.removeEventListener("birge:inbox-filter", onFilter);
        if (box.parentNode) box.parentNode.removeChild(box);
      }
    };
    live = handle;
    return handle;
  }

  window.BirgeComplaintList = { mount: mount, commands: commands,
                                setPath: function (path) { if (live) live.setPath(path); } };
})();
