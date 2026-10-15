/*
 * Birge · «Уведомления» — лента «Что нового для меня» (R06, раунд 15; CONTRACT §5.8, §7; схема R11 IA_ROUND15 §5.7, §7.7).
 *
 * Одна лента жителя: двор и инициативы (R16), кризис в районе (R17), встречи (R13), ответы на обращения (R09), идеи и
 * проекты, за которые житель голосовал, работы рядом (R06). Каждое уведомление открывает конкретное изменение.
 *
 * Подключение (R01, INTEGRATION R06 раздел D): /civic/notify/notify.css и /civic/notify/notify.js после ui-kit и i18n.
 *   BirgeNotify.attach(button, {apiBase, onOpen(link)}) — колокольчик в капсуле справа (кнопку ставит R01, только вид
 *     «Житель»): счётчик 1–9 / «9+», панель 360 px под кнопкой (плотное стекло), Esc закрывает, фокус — на кнопку;
 *   BirgeNotify.mount(root, opts) → {destroy, setLang} — та же лента экраном «Уведомления» (#notifications): телефон
 *     (пункт меню аватара) и «Ещё»; модуль сам регистрирует экран через BirgeShell.registerScreen;
 *   BirgeNotify.onCount(fn) — число непрочитанных (точка на аватаре и «Уведомления · N» в меню телефона), BirgeNotify.refresh().
 * Кнопки R01 ещё нет — модуль ставит свою в капсулу «.birge-me» (data-owner="R06"), только в виде «Житель»;
 * появилась кнопка R01 (data-action="notifications") — своя убирается.
 *
 * API: GET /notifications (X-Birge-Device — id устройства R09 «birge.device»; X-Birge-Ideas-Device — id голосов R06
 *   «birge.device_id»), POST /notifications/read {ids} | {all: true}.
 * П1 (поправка владельца 15 окт): только значки набора R11 (≤ 48 px, одна толщина), без рисунков и эмодзи.
 * Тексты — словарь R11 (shell.bell.*, notify.*); пока ключей нет — запасные ru/kk ниже (I18N_R15_R06.json).
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var API = "/api/civic/v2";
  var DEVICE_KEY = "birge.device";          // как у R09, R08, R13, R17 (web/civic/feedback/complaint.js)
  var IDEAS_DEVICE_KEY = "birge.device_id"; // голоса и идеи R06 (proposals.js, ideas.js)
  var POLL_MS = 60000;
  var SKELETON_MS = 150;
  // Значок строки по виду события (набор R11) и data-kind ленты ui-kit (.bk-feed__item[data-kind]).
  var KIND = {
    "yard.news": { kind: "yard", icon: "home", source: "notify.source.yard" },
    "initiative.update": { kind: "initiative", icon: "heart", source: "notify.source.together" },
    "incident.update": { kind: "crisis", icon: "alert", source: "notify.source.crisis" },
    "meeting.result": { kind: "meeting", icon: "message", source: "notify.source.meetings" },
    "complaint.update": { kind: "complaint", icon: "list", source: "notify.source.complaints" },
    "work.near": { kind: "work", icon: "road", source: "notify.source.works" },
    "idea.update": { kind: "idea", icon: "bulb", source: "notify.source.ideas" },
    "project.update": { kind: "project", icon: "cube", source: "notify.source.projects" },
  };
  var KEYS = {
    ru: {
      "shell.nav.notifications": "Уведомления",
      "shell.bell.label": "Уведомления",
      "shell.bell.new": { one: "{n} новое", few: "{n} новых", many: "{n} новых" },
      "shell.bell.empty": "Новых уведомлений нет",
      "notify.title": "Уведомления",
      "notify.read_all": "Прочитать все",
      "notify.group.new": "Новые",
      "notify.group.earlier": "Раньше",
      "notify.empty.title": "Пока тихо",
      "notify.empty.text": "Здесь появятся новости вашего двора, дел и обращений.",
      "notify.empty.yard": "Выбрать мой двор",
      "notify.error": "Не получилось загрузить уведомления. Проверьте связь.",
      "notify.retry": "Повторить",
      "notify.loading": "Загружаем уведомления",
      "notify.close": "Закрыть",
      "notify.unread": "Новое",
      "notify.demo": "Пример",
      "notify.ago.now": "только что",
      "notify.ago.min": "{n} мин назад",
      "notify.ago.hour": "{n} ч назад",
      "notify.ago.day": "{n} дн назад",
      "notify.source.yard": "Мой двор",
      "notify.source.together": "Сделаем вместе",
      "notify.source.crisis": "Кризис",
      "notify.source.meetings": "Встречи с акимом",
      "notify.source.complaints": "Мои обращения",
      "notify.source.works": "Работы рядом",
      "notify.source.ideas": "Идеи",
      "notify.source.projects": "Проекты",
    },
    kk: {
      "shell.nav.notifications": "Хабарламалар",
      "shell.bell.label": "Хабарламалар",
      "shell.bell.new": "{n} жаңа",
      "shell.bell.empty": "Жаңа хабарлама жоқ",
      "notify.title": "Хабарламалар",
      "notify.read_all": "Бәрін оқыдым",
      "notify.group.new": "Жаңа",
      "notify.group.earlier": "Бұрынғы",
      "notify.empty.title": "Әзірге тыныш",
      "notify.empty.text": "Мұнда ауланың, істердің және өтініштеріңіздің жаңалықтары пайда болады.",
      "notify.empty.yard": "Ауламды таңдау",
      "notify.error": "Хабарламаларды жүктеу мүмкін болмады. Байланысты тексеріңіз.",
      "notify.retry": "Қайталау",
      "notify.loading": "Хабарламалар жүктелуде",
      "notify.close": "Жабу",
      "notify.unread": "Жаңа",
      "notify.demo": "Үлгі",
      "notify.ago.now": "жаңа ғана",
      "notify.ago.min": "{n} мин бұрын",
      "notify.ago.hour": "{n} сағ бұрын",
      "notify.ago.day": "{n} күн бұрын",
      "notify.source.yard": "Менің аулам",
      "notify.source.together": "Бірге жасайық",
      "notify.source.crisis": "Төтенше жағдай",
      "notify.source.meetings": "Әкіммен кездесулер",
      "notify.source.complaints": "Менің өтініштерім",
      "notify.source.works": "Маңайдағы жұмыстар",
      "notify.source.ideas": "Идеялар",
      "notify.source.projects": "Жобалар",
    },
  };

  // ------------------------------------------------------------------ тексты, разметка
  function I() { return root.BirgeI18n || null; }
  function lang() { return I() && typeof I().getLang === "function" && I().getLang() === "kk" ? "kk" : "ru"; }
  function pluralRu(n) {
    var a = Math.abs(Number(n) || 0), m10 = a % 10, m100 = a % 100;
    if (m10 === 1 && m100 !== 11) return "one";
    return m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? "few" : "many";
  }
  function tr(key, params) {
    var i18n = I(), l = lang();
    if (i18n && typeof i18n.has === "function" && i18n.has(key)) return i18n.t(key, params);
    var v = KEYS[l][key] != null ? KEYS[l][key] : KEYS.ru[key] != null ? KEYS.ru[key] : key;
    if (v && typeof v === "object") v = v[pluralRu(params && params.n)] || v.many;   // формы числа — как словарь R11
    return String(v).replace(/\{(\w+)\}/g, function (w, n) { return params && params[n] != null ? String(params[n]) : w; });
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
    (children || []).forEach(function (c) {
      if (c != null && c !== false) el.appendChild(typeof c === "string" ? doc.createTextNode(c) : c);
    });
    return el;
  }
  // Значок набора ui-kit R11 (#i-…). Значок раунда 15 (i-bell), которого нет в спрайте сборки, — тот же рисунок R11
  // встроенным SVG (одна толщина и стиль .ic). Без ui-kit — пустой span той же ширины (строка не прыгает).
  var INLINE = { bell: '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15Z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>' };
  var spriteIds = null;
  (function loadSprite() {
    var sprite = root.BirgeUI && root.BirgeUI.SPRITE;
    if (!sprite || !root.fetch) return;
    root.fetch(sprite, { credentials: "same-origin" }).then(function (r) { return r.ok ? r.text() : ""; }).then(function (text) {
      var ids = {};
      String(text || "").replace(/id="(i-[a-z0-9-]+)"/g, function (all, id) { ids[id] = true; return all; });
      spriteIds = ids;
    }, function () { /* без спрайта — встроенные значки */ });
  })();
  function icon(name) {
    if (INLINE[name] && !(spriteIds && spriteIds["i-" + name])) {
      var box = doc.createElement("span");
      box.innerHTML = '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + INLINE[name] + "</svg>";
      return box.firstChild;
    }
    if (root.BirgeUI && typeof root.BirgeUI.icon === "function") {
      var span = doc.createElement("span");
      span.innerHTML = root.BirgeUI.icon(name);
      return span.firstChild || doc.createTextNode("");
    }
    return h("span", { class: "ic", "aria-hidden": "true" });
  }
  function store(key, value) {
    try {
      if (value === undefined) return root.localStorage.getItem(key);
      root.localStorage.setItem(key, value);
    } catch (e) { /* приватный режим: id живёт в памяти вкладки */ }
    return null;
  }
  var memoryDevice = null;
  function randomId(len) {
    var abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", out = "", bytes = new Uint8Array(len);
    (root.crypto || root.msCrypto).getRandomValues(bytes);
    for (var i = 0; i < len; i++) out += abc[bytes[i] % abc.length];
    return out;
  }
  // Тот же id и формат, что у мастера жалобы R09 («d-» + 24 символа): по нему соседи находят события жителя.
  function deviceId() {
    var id = store(DEVICE_KEY);
    if (!id || !/^[A-Za-z0-9_-]{16,80}$/.test(id)) {
      id = memoryDevice || "d-" + randomId(24);
      store(DEVICE_KEY, id);
      memoryDevice = id;
    }
    return id;
  }
  function ideasDeviceId() {
    var id = store(IDEAS_DEVICE_KEY);
    return id && /^[A-Za-z0-9._:-]{8,128}$/.test(id) ? id : null;
  }
  function reducedMotion() {
    return !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }
  function ago(iso, now) {
    var t = Date.parse(iso), n = now ? Date.parse(now) : Date.now();
    if (!isFinite(t)) return "";
    var min = Math.max(0, Math.round((n - t) / 60000));
    if (min < 1) return tr("notify.ago.now");
    if (min < 60) return tr("notify.ago.min", { n: min });
    var hours = Math.round(min / 60);
    if (hours < 24) return tr("notify.ago.hour", { n: hours });
    var days = Math.round(hours / 24);
    if (days <= 7) return tr("notify.ago.day", { n: days });
    return I() && typeof I().formatDate === "function" ? I().formatDate(iso) : String(iso).slice(0, 10);
  }

  // ------------------------------------------------------------------ данные (одно состояние на страницу)
  var apiBase = API;
  var state = { data: null, error: null, loading: false, at: 0 };
  var listeners = [];     // перерисовать открытые ленты (панель, экран)
  var countFns = [];      // onCount: точка на аватаре, пункт меню телефона
  var lastCount = -1;
  function request(method, path, body) {
    var headers = { Accept: "application/json", "X-Birge-Device": deviceId() };
    var ideas = ideasDeviceId();
    if (ideas) headers["X-Birge-Ideas-Device"] = ideas;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    return root.fetch(apiBase + path, { method: method, headers: headers, credentials: "same-origin",
      body: body !== undefined ? JSON.stringify(body) : undefined }).then(function (res) {
      return res.text().then(function (text) {
        var json = null;
        try { json = text ? JSON.parse(text) : null; } catch (e) { json = null; }
        if (json && json.ok === true && "data" in json) json = json.data;  // конверт стенда R06
        if (!res.ok) {
          var err = new Error((json && (json.message || (json.error && json.error.message))) || "HTTP " + res.status);
          err.status = res.status;
          throw err;
        }
        return json || {};
      });
    }, function () {
      var err = new Error("network");
      err.status = 0;
      throw err;
    });
  }
  function emit() {
    listeners.slice().forEach(function (fn) { try { fn(); } catch (e) { /* лента не ломает соседей */ } });
    var n = unread();
    if (n !== lastCount) {
      lastCount = n;
      countFns.slice().forEach(function (fn) { try { fn(n); } catch (e) { /* чужой обработчик */ } });
    }
  }
  function unread() {
    return state.data && typeof state.data.unread === "number" ? state.data.unread : 0;
  }
  function load() {
    if (state.loading) return state.promise;
    state.loading = true;
    state.error = null;
    emit();
    state.promise = request("GET", "/notifications").then(function (data) {
      state.data = data;
      state.at = Date.now();
      state.loading = false;
      emit();
      return data;
    }, function (err) {
      state.loading = false;
      state.error = err;
      emit();
      return null;
    });
    return state.promise;
  }
  function markRead(body) {
    return request("POST", "/notifications/read", body).then(function () { return load(); }, function () { return load(); });
  }
  function markIds(ids) {
    if (!ids.length) return Promise.resolve();
    // Сразу (не дожидаясь сервера): строка теряет точку, счётчик уменьшается (правило 4 эталона).
    if (state.data && state.data.items) {
      state.data.items.forEach(function (e) {
        if (ids.indexOf(e.id) >= 0 && !e.read) { e.read = true; state.data.unread = Math.max(0, (state.data.unread || 0) - 1); }
      });
      emit();
    }
    return markRead({ ids: ids });
  }

  // ------------------------------------------------------------------ открыть изменение
  var openHook = null;   // onOpen R01 (attach) — оболочка сама понимает #раздел/путь
  function openLink(link) {
    if (!link) return;
    if (typeof openHook === "function") { openHook(link); return; }
    var S = root.BirgeShell;
    if (S && typeof S.openLink === "function") { S.openLink(link); return; }
    var m = /^#([a-z][a-z0-9-]*)(?:([\/=])(.*))?$/.exec(link);
    if (!m) return;
    var section = m[1], sep = m[2] || "", path = m[3] || "";
    // Оболочка раунда 15 (IA_ROUND15 §7.3, у неё есть BirgeShell.path) сама разбирает «#раздел/путь» и передаёт путь
    // модулю (opts.path / handle.setPath); «#mine/event=…» (R09), «#incident=…» (R17) и адреса карты понимают их модули
    // по hashchange. Значит, достаточно поставить адрес.
    if (!S || "path" in S || sep === "=" || section === "mine" || typeof S.setSection !== "function") {
      setHash(link);
      return;
    }
    // Оболочка FINAL-4 знает только «#раздел»: открываем раздел и сообщаем модулю, что показать (событие birge:open).
    try { S.setSection(section); } catch (e) { setHash(link); return; }
    if (path && (section === "yard" || section === "together") && root.BirgeTogether && typeof root.BirgeTogether.open === "function") {
      root.BirgeTogether.open(section === "yard" || /^(yard|cell)-/.test(path) ? "yard" : "initiative", path);
    }
    doc.dispatchEvent(new CustomEvent("birge:open", { detail: { section: section, path: path, link: link } }));
  }
  // Тот же адрес ещё раз (житель второй раз нажал то же уведомление) — hashchange сам не придёт: шлём его.
  function setHash(link) {
    if (location.hash === link) {
      try { root.dispatchEvent(new HashChangeEvent("hashchange")); } catch (e) { /* старый браузер: адрес уже стоит */ }
    } else {
      location.hash = link;
    }
  }

  // ------------------------------------------------------------------ лента (панель и экран)
  function feedView(container, opts) {
    var options = opts || {};
    var timer = null;
    function item(e) {
      var look = KIND[e.kind] || { kind: "other", icon: "info", source: null };
      var title = (lang() === "kk" ? e.title_kk || e.title_ru : e.title_ru || e.title_kk) || "";
      var meta = [ago(e.at, state.data && state.data.now), look.source ? tr(look.source) : null, e.demo ? tr("notify.demo") : null]
        .filter(Boolean).join(" · ");
      var inner = [h("span", { class: "bk-feed__ic", "aria-hidden": "true" }, [icon(look.icon)]),
        h("span", { class: "bk-feed__main" }, [
          h("span", { class: "bk-feed__title", lang: lang() === "kk" && e.title_kk ? "kk" : "ru", text: title }),
          h("span", { class: "bk-feed__meta", text: meta })])];
      if (!e.read) inner.push(h("span", { class: "bk-sr-only", text: ", " + tr("notify.unread") }));
      var attrs = { class: "bk-feed__item", "data-kind": look.kind, "data-unread": e.read ? null : "true", "data-event": e.id };
      var node;
      if (e.link) {
        attrs.href = e.link;
        attrs.onclick = function (ev) {
          if (ev.ctrlKey || ev.metaKey || ev.shiftKey) return;   // новая вкладка — как обычная ссылка
          ev.preventDefault();
          if (!e.read) markIds([e.id]);
          if (typeof options.onOpen === "function") options.onOpen(e.link);
          openLink(e.link);
        };
        node = h("a", attrs, inner);
      } else {
        attrs.type = "button";
        attrs.onclick = function () { if (!e.read) markIds([e.id]); };
        node = h("button", attrs, inner);
      }
      return h("li", {}, [node]);
    }
    function render() {
      container.replaceChildren();
      var data = state.data;
      if (!data && state.error) {
        if (root.BirgeUI && root.BirgeUI.state) {
          root.BirgeUI.state(container, "error", { title: tr("notify.error"), action: { label: tr("notify.retry"), onClick: load } });
        } else {
          container.appendChild(h("p", { class: "rn-msg", role: "alert", text: tr("notify.error") }));
        }
        return;
      }
      if (!data) {
        // Скелетон — не раньше 150 мс (быстрая сеть не мигает).
        clearTimeout(timer);
        timer = setTimeout(function () {
          if (state.data || state.error) return;
          container.replaceChildren(h("div", { class: "rn-skeleton", role: "status", "aria-label": tr("notify.loading") },
            [0, 1, 2].map(function () { return h("span", { class: "bk-skel rn-skeleton__row" }); })));
        }, SKELETON_MS);
        return;
      }
      var items = data.items || [];
      if (!items.length) {
        // П1, правило 2: маленький значок (≤ 48 px) + коротко + одна кнопка.
        var hasYard = !!(root.BirgeTogether || (root.BirgeShell && root.BirgeShell.navItems && root.BirgeShell.navItems("resident").indexOf("yard") >= 0));
        container.appendChild(h("div", { class: "rn-empty", role: "status" }, [
          h("span", { class: "rn-empty__ic", "aria-hidden": "true" }, [icon("bell")]),
          h("p", { class: "rn-empty__title", text: tr("notify.empty.title") }),
          h("p", { class: "rn-empty__text", text: tr("notify.empty.text") }),
          hasYard ? h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-key": "notify-yard", onclick: function () {
            if (typeof options.onOpen === "function") options.onOpen("#yard");
            openLink("#yard");
          } }, [tr("notify.empty.yard")]) : null]));
        return;
      }
      var fresh = items.filter(function (e) { return !e.read; }), old = items.filter(function (e) { return e.read; });
      [[fresh, "notify.group.new"], [old, "notify.group.earlier"]].forEach(function (g) {
        if (!g[0].length) return;
        var head = h("p", { class: "bk-feed__group", text: tr(g[1]) });
        container.appendChild(head);
        container.appendChild(h("ol", { class: "bk-feed", "aria-label": tr(g[1]) }, g[0].map(item)));
      });
    }
    listeners.push(render);
    render();
    return {
      render: render,
      destroy: function () {
        clearTimeout(timer);
        var i = listeners.indexOf(render);
        if (i >= 0) listeners.splice(i, 1);
      },
    };
  }
  // «Прочитать все» — ровно то, что житель видит: до времени этой ленты (now ответа) и события «впереди часов» из неё
  // по id. Пришедшее после последнего обновления ленты останется новым (а не «прочитается» молча).
  function readAll() {
    var data = state.data;
    if (!data || !data.now) return markRead({ all: true });
    var ahead = (data.items || []).filter(function (e) { return !e.read && e.at > data.now; })
      .map(function (e) { return e.id; }).slice(0, 200);
    (data.items || []).forEach(function (e) { e.read = true; });   // сразу: точки гаснут, счётчик — 0 (правило 4 эталона)
    data.unread = 0;
    emit();
    return markRead(ahead.length ? { until: data.now, ids: ahead } : { until: data.now });
  }
  function readAllButton() {
    return h("button", { type: "button", class: "bk-notify__readall", "data-key": "notify-read-all",
      hidden: unread() ? null : true, onclick: function () { readAll(); } }, [tr("notify.read_all")]);
  }

  // ------------------------------------------------------------------ колокольчик и панель
  var bell = null;        // {button, panel, feed, opts}
  function setBadge() {
    if (!bell) return;
    var n = unread(), b = bell.button;
    var badge = b.querySelector(".bk-nav__badge");
    if (!badge) {
      badge = h("span", { class: "bk-nav__badge", "aria-hidden": "true" });
      b.appendChild(badge);
    }
    badge.textContent = n > 9 ? "9+" : String(n);
    badge.hidden = !n;
    // «Уведомления, 3 новых» (словарь R11: shell.bell.new — только число и слово, формы числа для ru)
    var label = n ? tr("shell.bell.label") + ", " + tr("shell.bell.new", { n: n }) : tr("shell.bell.label");
    b.setAttribute("aria-label", label);
    b.title = n ? label : tr("shell.bell.empty");
    if (bell.panel) {
      var all = bell.panel.querySelector(".bk-notify__readall");
      if (all) all.hidden = !n;
    }
  }
  function placePanel() {
    if (!bell || !bell.panel) return;
    var r = bell.button.getBoundingClientRect(), w = Math.min(360, innerWidth - 24);
    var left = Math.max(12, Math.min(r.right - w, innerWidth - w - 12));
    bell.panel.style.left = Math.round(left) + "px";
    bell.panel.style.top = Math.round(r.bottom + 8) + "px";
  }
  function openPanel() {
    if (!bell || bell.panel) return;
    var list = h("div", { class: "bk-notify__list" });
    var panel = h("section", { class: "bk-notify bk-glass bk-glass--strong rn-panel bk-app", role: "dialog",
      "aria-label": tr("notify.title"), tabindex: "-1" }, [
      h("header", { class: "bk-notify__hd" }, [h("h2", { class: "bk-notify__title", text: tr("notify.title") }), readAllButton()]),
      list]);
    if (!reducedMotion()) panel.classList.add("rn-in");
    doc.body.appendChild(panel);
    bell.panel = panel;
    bell.feed = feedView(list, { onOpen: function () { closePanel(false); } });
    bell.button.setAttribute("aria-expanded", "true");
    placePanel();
    setBadge();
    panel.focus();
    if (!state.data || Date.now() - state.at > 15000) load();
  }
  function closePanel(focusBack) {
    if (!bell || !bell.panel) return;
    bell.feed.destroy();
    bell.panel.remove();
    bell.panel = null;
    bell.button.setAttribute("aria-expanded", "false");
    if (focusBack !== false) bell.button.focus();
  }
  function onDocKey(e) {
    if (e.key === "Escape" && bell && bell.panel) {
      e.preventDefault();
      e.stopPropagation();
      closePanel(true);
    }
  }
  function onDocClick(e) {
    if (!bell || !bell.panel) return;
    if (bell.panel.contains(e.target) || bell.button.contains(e.target)) return;
    closePanel(false);
  }
  function attach(button, opts) {
    if (!button) return null;
    var options = opts || {};
    if (options.apiBase) apiBase = options.apiBase;
    if (typeof options.onOpen === "function") openHook = options.onOpen;
    if (bell && bell.button !== button) detach();
    if (!bell) {
      bell = { button: button, panel: null, feed: null };
      button.setAttribute("aria-haspopup", "dialog");
      button.setAttribute("aria-expanded", "false");
      button.classList.add("bk-bell");
      if (!button.querySelector(".ic")) button.insertBefore(icon("bell"), button.firstChild);
      bell.onClick = function (e) {
        e.preventDefault();
        if (bell.panel) closePanel(true);
        else openPanel();
      };
      button.addEventListener("click", bell.onClick);
      bell.onCount = setBadge;
      listeners.push(setBadge);
    }
    setBadge();
    start();
    return { open: openPanel, close: closePanel, refresh: load, detach: detach };
  }
  function detach() {
    if (!bell) return;
    closePanel(false);
    bell.button.removeEventListener("click", bell.onClick);
    var i = listeners.indexOf(setBadge);
    if (i >= 0) listeners.splice(i, 1);
    if (bell.button.getAttribute("data-owner") === "R06") bell.button.remove();
    bell = null;
  }

  // ------------------------------------------------------------------ экран (телефон, «Ещё»)
  function mount(rootEl, opts) {
    var options = opts || {};
    if (options.apiBase) apiBase = options.apiBase;
    rootEl.classList.add("rn");
    var head = h("div", { class: "rn-head" }, [h(options.titleTag || "h2", { class: "rn-title", text: tr("notify.title") }), readAllButton()]);
    var list = h("div", { class: "rn-list" });
    rootEl.replaceChildren(head, list);
    var feed = feedView(list, { onOpen: function () { /* оболочка сама сменит раздел */ } });
    var sync = function () {
      var all = head.querySelector(".bk-notify__readall");
      if (all) all.hidden = !unread();
    };
    listeners.push(sync);
    start();
    load();
    return {
      setLang: function () {
        head.querySelector(".rn-title").textContent = tr("notify.title");
        var all = head.querySelector(".bk-notify__readall");
        if (all) all.textContent = tr("notify.read_all");
        feed.render();
      },
      destroy: function () {
        feed.destroy();
        var i = listeners.indexOf(sync);
        if (i >= 0) listeners.splice(i, 1);
        rootEl.classList.remove("rn");
        rootEl.replaceChildren();
      },
    };
  }

  // ------------------------------------------------------------------ опрос, «Мои обращения», своя кнопка
  var started = false;
  var poll = null;
  function start() {
    if (started) return;
    started = true;
    load();
    poll = setInterval(function () { if (!doc.hidden) load(); }, POLL_MS);
    doc.addEventListener("visibilitychange", function () { if (!doc.hidden && Date.now() - state.at > 15000) load(); });
    doc.addEventListener("keydown", onDocKey, true);
    doc.addEventListener("click", onDocClick, true);
    root.addEventListener("resize", placePanel);
    // IA §5.7: «Мои обращения» R09 открылись — их события в ленте прочитаны (одно событие не висит двумя числами).
    if (typeof MutationObserver === "function") {
      new MutationObserver(function () {
        if (!doc.documentElement.classList.contains("bc-mine-open") || !state.data) return;
        var ids = (state.data.items || []).filter(function (e) { return !e.read && e.kind === "complaint.update"; })
          .map(function (e) { return e.id; });
        if (ids.length) markIds(ids);
      }).observe(doc.documentElement, { attributes: true, attributeFilter: ["class"] });
    }
    var I18N = I();
    if (I18N && typeof I18N.onChange === "function") I18N.onChange(function () { emit(); setBadge(); });
  }
  // Своя кнопка в капсуле справа, пока R01 не поставил свою (IA §7.7): только вид «Житель», ноутбук.
  function autoBell() {
    if (root.BIRGE_NOTIFY_AUTO === false) return;
    var shellBell = doc.querySelector('[data-action="notifications"]:not([data-owner="R06"])');
    if (shellBell) {
      if (!bell || bell.button !== shellBell) attach(shellBell, {});
      return;
    }
    var me = doc.querySelector(".birge-me");
    var resident = doc.body && doc.body.dataset.birgeMode === "resident";
    var phone = innerWidth < 761;
    var mine = doc.querySelector('[data-action="notifications"][data-owner="R06"]');
    if (!me || !resident || phone) {
      if (mine) detach();
      return;
    }
    if (!mine) {
      mine = h("button", { type: "button", class: "bk-iconbtn bk-bell birge-bell", "data-action": "notifications", "data-owner": "R06" });
      // Между «ҚАЗ · РУС» и аватаром (IA §7.7): аватар — прямой потомок капсулы.
      var avatar = me.querySelector(":scope > .birge-avatar, :scope > [data-action=account]");
      if (avatar) me.insertBefore(mine, avatar);
      else me.appendChild(mine);
      attach(mine, {});
    }
  }
  function registerScreen() {
    var S = root.BirgeShell;
    if (!S || typeof S.registerScreen !== "function") return false;
    S.registerScreen({ id: "notifications", mount: mount, modes: ["resident"], titleKey: "shell.nav.notifications" });
    // Страницу открыли по адресу «#notifications» (ссылка, пункт меню телефона): оболочка разобрала адрес раньше,
    // чем экран зарегистрировался, и открыла карту — открываем экран сами.
    if (root.location && root.location.hash === "#notifications" && S.section !== "notifications" && typeof S.setSection === "function") {
      S.setSection("notifications", { hash: false });
    }
    return true;
  }
  function boot() {
    if (!registerScreen()) setTimeout(registerScreen, 1000);
    autoBell();
    doc.addEventListener("birge:mode", autoBell);
    doc.addEventListener("civic:mode", autoBell);
    root.addEventListener("resize", function () { clearTimeout(boot.t); boot.t = setTimeout(autoBell, 200); });
    if (typeof MutationObserver === "function" && doc.body) {
      new MutationObserver(function () { clearTimeout(boot.m); boot.m = setTimeout(autoBell, 100); })
        .observe(doc.body, { attributes: true, attributeFilter: ["data-birge-mode"] });
    }
  }

  root.BirgeNotify = {
    attach: attach, mount: mount, refresh: load, openLink: openLink,
    onCount: function (fn) { if (typeof fn === "function") { countFns.push(fn); fn(unread()); } },
    get unread() { return unread(); },
    version: "notify-r15", KEYS: KEYS,
  };
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", function () { setTimeout(boot, 0); });
  else setTimeout(boot, 0);
})(typeof self !== "undefined" ? self : this);
