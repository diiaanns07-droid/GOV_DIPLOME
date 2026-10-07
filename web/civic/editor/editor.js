/* R04 staff editor UI (round 11, civic-v1).
 * window.CivicEditor.mount({root, map, api, onPublished}) -> {openObject, destroy}
 *   root        element given to the editor (it owns the children, never document.body);
 *   map         the one shared MapLibre instance, or null (coordinates can then be typed);
 *   api         R01 adapter: api.request(method, path, body) -> Promise<data>; cookies and CSRF are its job;
 *   onPublished (publicItem, {action}) after the public version changed: publish, edit of a published record, archive.
 * Optional: apiPrefix (default "", paths are relative to /api/civic/v1), internalNotes:true, now() for tests.
 * The server decides rights. The UI never derives rights from a browser role and keeps no session in storage.
 * Unsaved text (RECOVERY) lives in this page's memory and, to survive a reload or a tab crash, in this tab's
 * sessionStorage: form fields only (never passwords, tokens or the CSRF value), bound to the signed-in user,
 * removed after a successful save, on "Удалить из памяти" and on logout. It is a local copy, not the server record.
 */
(function () {
  "use strict";
  const NS = (window.CivicEditor = window.CivicEditor || {});
  const C = NS.core;
  if (!C) { console.error("CivicEditor: load web/civic/editor/editor-core.js before editor.js"); return; }

  const RECOVERY = new Map();  // object id | "new" -> {base, form, at, title, revision}; this tab only
  const STORE_KEY = "civic-r04-unsaved:v1";
  const STORE = (() => {
    try { const s = window.sessionStorage, k = "civic-r04-probe"; s.setItem(k, k); s.removeItem(k); return s; } catch (e) { return null; }
  })();
  let storeUser = null;  // the user whose unsaved edits RECOVERY currently holds
  function persistRecovery() {
    if (!STORE) return;
    try {
      if (!storeUser || !RECOVERY.size) { STORE.removeItem(STORE_KEY); return; }
      STORE.setItem(STORE_KEY, JSON.stringify({ v: 1, user: storeUser, entries: Object.fromEntries(RECOVERY) }));
    } catch (e) { /* quota or privacy mode: memory copy still works */ }
  }
  // After the server confirms who is signed in: keep only that user's local copies.
  function loadRecovery(user) {
    if (storeUser && storeUser !== user) RECOVERY.clear();
    storeUser = user || null;
    if (!STORE || !storeUser) return;
    try {
      const d = JSON.parse(STORE.getItem(STORE_KEY) || "null");
      if (!d || d.v !== 1 || d.user !== storeUser || !d.entries || typeof d.entries !== "object") { if (d) STORE.removeItem(STORE_KEY); return; }
      for (const [k, r] of Object.entries(d.entries)) if (!RECOVERY.has(k) && r && r.form && typeof r.form === "object") RECOVERY.set(k, r);
    } catch (e) { try { STORE.removeItem(STORE_KEY); } catch (x) { /* ignore */ } }
  }
  function dropRecovery(key) { if (RECOVERY.delete(key)) persistRecovery(); }
  function clearRecovery() { RECOVERY.clear(); storeUser = null; persistRecovery(); }
  let seq = 0;
  const FORM_LABEL = {
    title: "Название", kind: "Тип", status: "Статус работ", description: "Описание",
    planned_start: "Плановое начало", original_planned_end: "Первоначальный плановый срок", current_planned_end: "Актуальный плановый срок",
    actual_end: "Фактически завершено", geometry: "Место", geometry_precision: "Точность места", organization: "Организация",
    public_contact: "Публичный контакт", amount: "Стоимость", basis: "Основание суммы", budget_source_id: "Источник суммы",
    evidence_type: "Достоверность", evidence_notes: "Пояснение к достоверности", internal_notes: "Внутренняя заметка", sources: "Источники",
    reason: "Причина",
  };
  const HISTORY_LABEL = Object.assign({}, C.PATH_LABEL, { publication: "Публикация", schedule: "Сроки", budget: "Стоимость", responsible: "Ответственный" });
  const ACTION_LABEL = { create: "создание", update: "изменение", publish: "публикация", archive: "архив", import_create: "импорт", import_update: "импорт" };
  const FILTERS = [["draft", "Черновики"], ["published", "Опубликованные"], ["archived", "Архив"], ["all", "Все"]];

  const clone = (x) => (x === null || x === undefined ? x : JSON.parse(JSON.stringify(x)));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const enc = encodeURIComponent;
  const round6 = (x) => Math.round(x * 1e6) / 1e6;
  const reduced = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const cssEsc = (s) => (window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/["\\]/g, "\\$&"));
  function el(tag, attrs, kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : String(v));
    }
    for (const c of [].concat(kids === undefined ? [] : kids)) {
      if (c === null || c === undefined || c === false) continue;
      e.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return e;
  }
  function newKey() {
    const c = window.crypto;
    if (c && typeof c.randomUUID === "function") return c.randomUUID();
    const a = new Uint8Array(16);
    c.getRandomValues(a);
    return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
  }
  const badge = (text, kind) => el("span", { class: "civic-r04-badge civic-r04-badge-" + kind }, text);

  function mount(opts) {
    const o = opts || {};
    const root = o.root, api = o.api, map = o.map || null;
    if (!root || root.nodeType !== 1) throw new TypeError("CivicEditor.mount: root element is required");
    if (!api || typeof api.request !== "function") throw new TypeError("CivicEditor.mount: api.request is required");
    const P = "civic-r04-" + ++seq + "-";
    const apiPrefix = typeof o.apiPrefix === "string" ? o.apiPrefix : "";
    const onPublished = typeof o.onPublished === "function" ? o.onPublished : null;
    const now = typeof o.now === "function" ? o.now : () => new Date();
    const STALE = Object.freeze({ stale: true });
    const SRC = P + "geom", LAYERS = [P + "geom-line", P + "geom-pt"];
    const S = {
      epoch: 0, alive: true, session: null, view: "loading", alert: null,
      list: { items: [], next: null, filter: "draft", mine: false, loaded: false, loading: false },
      item: null, history: [], form: null, saved: null, mirror: false, internalNotes: o.internalNotes === true,
      errors: {}, warnings: {}, server: {}, touched: {}, tried: false, busy: null, confirm: null, reason: "", reasonErr: null,
      conflict: null, reauth: false, uncertain: null, createKey: null, dup: null, restore: null, tool: null, cursor: "", preview: false, publicCopy: null,
      notice: null, logoutAsk: false, lastDirty: false, mapOn: false, diffOpen: true,
    };
    const F = {};            // field key -> {control, err, warn}
    const V = {};            // edit view containers
    const domListeners = []; // [target, type, fn] outside root (window/document)
    const mapHandlers = [];  // [type, fn]
    const timers = new Set();

    // ---------- shell ----------
    const head = el("header", { class: "civic-r04-head" });
    const live = el("div", { class: "civic-r04-sr", role: "status", "aria-live": "polite" });
    const liveErr = el("div", { class: "civic-r04-sr", role: "alert" });
    const body = el("div", { class: "civic-r04-body" });
    const shell = el("section", { class: "civic-r04", "aria-labelledby": P + "h" }, [head, live, liveErr, body]);
    shell.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if (S.tool) { e.preventDefault(); closeTool(); focusKey("tool-point"); }
      else if (S.confirm && !S.busy) { e.preventDefault(); cancelConfirm(); }
      else if (S.logoutAsk) { e.preventDefault(); S.logoutAsk = false; renderHead(); focusKey("logout"); }
    });
    root.replaceChildren(shell);

    function onDom(target, type, fn) { target.addEventListener(type, fn); domListeners.push([target, type, fn]); }
    function offDom(target, type, fn) {
      target.removeEventListener(type, fn);
      const i = domListeners.findIndex((x) => x[0] === target && x[1] === type && x[2] === fn);
      if (i >= 0) domListeners.splice(i, 1);
    }
    function onMap(type, fn) { if (!map) return; map.on(type, fn); mapHandlers.push([type, fn]); }
    function offMap(type, fn) {
      if (!map) return;
      map.off(type, fn);
      const i = mapHandlers.findIndex((x) => x[0] === type && x[1] === fn);
      if (i >= 0) mapHandlers.splice(i, 1);
    }
    function later(fn, ms) { const t = setTimeout(() => { timers.delete(t); if (S.alive) fn(); }, ms); timers.add(t); }
    function say(text, assertive) {
      const box = assertive ? liveErr : live;
      box.textContent = "";
      later(() => { box.textContent = text; }, 30);
    }
    onDom(window, "beforeunload", (e) => {
      if (isDirty() || RECOVERY.size) { e.preventDefault(); e.returnValue = ""; }
    });

    // ---------- API ----------
    async function call(method, path, body, extra) {
      const ep = S.epoch;
      let data;
      try { data = C.unwrap(await (extra ? api.request(method, apiPrefix + path, body, extra) : api.request(method, apiPrefix + path, body))); }
      catch (e) { if (ep !== S.epoch || !S.alive) throw STALE; throw e; }
      if (ep !== S.epoch || !S.alive) throw STALE;
      return data;
    }
    function setCsrf(token) {
      if (typeof api.setCsrfToken === "function") { try { api.setCsrfToken(token || null); } catch (e) { /* adapter-specific */ } }
    }
    function applySession(d) {
      S.session = { authenticated: !!(d && d.authenticated), user: (d && d.user) || null };
      setCsrf(d && d.csrf_token);
      if (S.session.authenticated) loadRecovery(S.session.user && S.session.user.name ? String(S.session.user.name) : "?");
    }

    // ---------- small UI helpers ----------
    function btn(label, fn, cls, fk, extra) {
      return el("button", Object.assign({ type: "button", class: "civic-r04-btn" + (cls ? " " + cls : ""), "data-fk": fk || null, onclick: fn }, extra || {}), label);
    }
    function focusKey(k) {
      const x = shell.querySelector('[data-fk="' + cssEsc(k) + '"]');
      if (x && !x.disabled) x.focus();
    }
    // Replace children and keep keyboard focus/caret on the "same" control (data-fk).
    function rebuild(container, kids) {
      const a = document.activeElement;
      const fk = a && container.contains(a) ? a.getAttribute("data-fk") : null;
      let sel = null;
      if (fk) { try { if (typeof a.selectionStart === "number") sel = [a.selectionStart, a.selectionEnd]; } catch (e) { sel = null; } }
      container.replaceChildren(...kids.filter(Boolean));
      if (fk) {
        const b = container.querySelector('[data-fk="' + cssEsc(fk) + '"]');
        if (b && !b.disabled) { b.focus(); if (sel) { try { b.setSelectionRange(sel[0], sel[1]); } catch (e) { /* not a text control */ } } }
      }
    }
    function msgBlock(n) {
      if (!n) return null;
      const kids = [el("p", {}, n.text)];
      if (n.detail) kids.push(el("p", { class: "civic-r04-detail" }, "Сервер: " + n.detail));
      if (n.actions && n.actions.length) kids.push(el("p", { class: "civic-r04-row-btns" }, n.actions.map((a) => btn(a.label, a.fn, a.cls || "", a.fk))));
      return el("div", { class: "civic-r04-msg civic-r04-msg-" + n.type, tabindex: "-1", "data-fk": "msg" }, kids);
    }
    function setNotice(type, x, actions) {
      const n = typeof x === "string" ? { text: x, detail: "" } : { text: x.text, detail: x.detail || "" };
      S.notice = Object.assign(n, { type, actions: actions || [] });
      say(n.text, type === "error");
      if (S.view === "edit" && V.msg) V.msg.replaceChildren(...[msgBlock(S.notice)].filter(Boolean));
      else { S.alert = S.notice; renderAlertOnly(); }
    }
    function renderAlertOnly() {
      const box = body.querySelector(".civic-r04-topmsg");
      if (box) box.replaceChildren(...[msgBlock(S.alert)].filter(Boolean));
    }

    // ---------- views ----------
    function render() {
      if (!S.alive) return;
      renderHead();
      if (S.view === "loading") body.replaceChildren(el("p", { class: "civic-r04-muted" }, "Загрузка…"));
      else if (S.view === "login") renderLogin();
      else if (S.view === "list") renderList();
      else if (S.view === "edit") buildEditor();
    }
    function renderHead() {
      const kids = [el("h2", { id: P + "h" }, "Кабинет редактора")];
      if (S.session && S.session.authenticated) {
        const u = S.session.user || {};
        kids.push(el("p", { class: "civic-r04-who" }, ["Вы вошли: ", el("b", {}, u.name || "сотрудник"), u.role ? " · роль по данным сервера: " + u.role : ""]));
        if (S.logoutAsk) {
          kids.push(el("div", { class: "civic-r04-ask", role: "group", "aria-label": "Подтверждение выхода" }, [
            el("p", {}, "Есть несохранённые правки. При выходе они будут удалены из памяти вкладки."),
            btn("Выйти без сохранения", doLogout, "danger", "logout-confirm"),
            btn("Остаться", () => { S.logoutAsk = false; renderHead(); focusKey("logout"); }, "", "logout-cancel")]));
        } else kids.push(btn("Выйти", askLogout, "ghost", "logout"));
      }
      head.replaceChildren(...kids);
    }

    function showLogin(alert) {
      detachMap();
      S.view = "login";
      if (alert) S.alert = alert;
      render();
      focusKey("login-user");
    }
    function loginForm(reauth) {
      const u = el("input", { id: P + (reauth ? "re-" : "") + "user", name: "username", autocomplete: "username", autocapitalize: "none", spellcheck: "false", "data-fk": reauth ? "relogin-user" : "login-user" });
      const p = el("input", { id: P + (reauth ? "re-" : "") + "pass", name: "password", type: "password", autocomplete: "current-password", "data-fk": reauth ? "relogin-pass" : "login-pass" });
      const err = el("p", { class: "civic-r04-err", id: p.id + "-err" });
      p.setAttribute("aria-describedby", err.id);
      const submit = el("button", { type: "submit", class: "civic-r04-btn primary", "data-fk": reauth ? "relogin-submit" : "login-submit" }, "Войти");
      const hid = P + (reauth ? "re-" : "") + "login-h";
      const f = el("form", { class: "civic-r04-login" + (reauth ? " civic-r04-reauth" : ""), novalidate: true, "aria-labelledby": hid }, [
        el(reauth ? "h4" : "h3", { id: hid, tabindex: "-1", "data-fk": reauth ? "relogin-h" : "login-h" }, reauth ? "Сессия истекла — войдите снова" : "Вход для сотрудника"),
        el("p", { class: "civic-r04-help" }, reauth
          ? "Ваши правки остались в форме. После входа нажмите «Сохранить» ещё раз — повторная отправка не создаст копию."
          : "Учётную запись создаёт администратор сервера. Сессия хранится сервером в защищённой cookie, не в браузерном хранилище."),
        el("div", { class: "civic-r04-field" }, [el("label", { for: u.id }, "Имя пользователя"), u]),
        el("div", { class: "civic-r04-field" }, [el("label", { for: p.id }, "Пароль"), p, err]),
        el("p", { class: "civic-r04-row-btns" }, [submit]),
      ]);
      f.addEventListener("submit", (ev) => { ev.preventDefault(); login(u, p, err, submit, reauth); });
      return f;
    }
    async function login(u, p, err, submit, reauth) {
      if (S.busy) return;
      err.textContent = "";
      p.removeAttribute("aria-invalid");
      if (!u.value.trim() || !p.value) { err.textContent = "Введите имя пользователя и пароль."; (u.value.trim() ? p : u).focus(); return; }
      const creds = { username: u.value.trim(), password: p.value };
      p.value = "";  // the password does not stay in the page after sending
      setBusy("login");
      submit.disabled = true;
      try {
        applySession(await call("POST", "/session/login", creds));
      } catch (e) {
        if (e === STALE) return;
        const n = C.normalizeError(e);
        err.textContent = n.kind === "auth" || n.kind === "validation" ? "Неверное имя пользователя или пароль." : n.text;
        p.setAttribute("aria-invalid", "true");
        say(err.textContent, true);
        p.focus();
        return;
      } finally {
        if (S.alive) { setBusy(null); submit.disabled = false; }
      }
      if (!S.session.authenticated) { err.textContent = "Сервер не подтвердил вход."; return; }
      S.alert = null;
      renderHead();
      if (reauth) {
        S.reauth = false;
        renderReauth();
        setNotice("ok", "Вы снова вошли. Правки на месте — нажмите «Сохранить» ещё раз.");
        renderButtons();
        focusKey("save");
      } else await showList(true);
    }
    function renderLogin() {
      body.replaceChildren(el("div", { class: "civic-r04-topmsg" }, [msgBlock(S.alert)].filter(Boolean)), loginForm(false));
    }

    async function showList(reload) {
      stashIfDirty();
      detachMap();
      Object.assign(S, { view: "list", item: null, form: null, saved: null, history: [], confirm: null, conflict: null, reauth: false, preview: false, notice: null });
      render();
      if (reload || !S.list.loaded) await loadList(false);
    }
    async function loadList(more) {
      const L = S.list;
      if (L.loading) return;
      L.loading = true;
      if (S.view === "list") renderList();
      try {
        const d = await call("GET", "/staff/objects" + (more && L.next ? "?cursor=" + enc(L.next) : ""));
        const items = Array.isArray(d && d.items) ? d.items : [];
        L.items = more ? L.items.concat(items) : items;
        L.next = (d && d.next_cursor) || null;
        L.loaded = true;
        if (items.some((it) => it && Object.prototype.hasOwnProperty.call(it, "internal_notes"))) S.internalNotes = true;
      } catch (e) {
        if (e === STALE) return;
        handleError(e);
      } finally { L.loading = false; }
      if (S.view === "list") renderList();
    }
    function renderList() {
      const L = S.list;
      const me = S.session && S.session.user && S.session.user.name;
      const mineKnown = L.items.some((it) => it && it.created_by && it.created_by.name);
      const pass = (it, f) => (f === "all" || it.publication === f) && (!L.mine || !mineKnown || (it.created_by && it.created_by.name === me));
      const shown = L.items.filter((it) => it && pass(it, L.filter));
      const tabs = el("div", { class: "civic-r04-tabs", role: "group", "aria-label": "Какие записи показать" }, FILTERS.map(([k, label]) =>
        el("button", { type: "button", "aria-pressed": String(L.filter === k), "data-fk": "filter-" + k,
          onclick: () => { L.filter = k; renderList(); focusKey("filter-" + k); } }, label + " · " + L.items.filter((it) => it && pass(it, k)).length)));
      const mine = mineKnown ? el("label", { class: "civic-r04-check" }, [
        el("input", { type: "checkbox", "data-fk": "mine", checked: L.mine, onchange: (e) => { L.mine = e.target.checked; renderList(); focusKey("mine"); } }), " Только мои"]) : null;
      const rec = RECOVERY.size ? el("div", { class: "civic-r04-msg civic-r04-msg-warn" }, [
        el("p", {}, "Несохранённые правки в этой вкладке — локальная копия, не на сервере (переживёт перезагрузку страницы, пропадёт при закрытии вкладки или выходе):"),
        el("ul", {}, [...RECOVERY.entries()].map(([key, r]) => el("li", {}, [
          "«" + r.title + "», " + C.fmtDateTime(r.at) + " ",
          btn("Вернуться к правке", () => (key === "new" ? newObject() : openObject(key)), "link", "rec-" + key)])))]) : null;
      const rows = shown.map((it) => {
        const sc = it.schedule || {};
        const badges = [badge(C.PUBLICATION[it.publication] || String(it.publication), "pub-" + it.publication)];
        if (it.evidence_type === "synthetic") badges.push(badge("синтетические данные", "synthetic"));
        if (!it.geometry) badges.push(badge("без места на карте", "muted"));
        if (C.pendingInfo(it).pending) badges.push(badge("есть неопубликованные изменения", "warn"));
        if (RECOVERY.has(it.id)) badges.push(badge("есть несохранённые правки", "warn"));
        return el("li", {}, el("button", { type: "button", class: "civic-r04-row", "data-fk": "row-" + it.id, onclick: () => openObject(it.id) }, [
          el("span", { class: "civic-r04-row-title" }, it.title || "(без названия)"),
          el("span", { class: "civic-r04-row-meta" }, (C.KINDS[it.kind] || it.kind || "тип не указан") + " · " + (C.STATUSES[it.status] || "статус неизвестен")
            + " · окончание: " + C.fmtDate(sc.current_planned_end) + " · ред. " + (it.revision === undefined ? "?" : it.revision)),
          el("span", { class: "civic-r04-badges" }, badges)]));
      });
      body.replaceChildren(el("div", { class: "civic-r04-listview" }, [
        el("div", { class: "civic-r04-topmsg" }, [msgBlock(S.alert)].filter(Boolean)),
        el("div", { class: "civic-r04-toolbar" }, [
          btn("+ Новый объект", newObject, "primary", "new"),
          btn(L.loading ? "Обновляем…" : "Обновить список", () => loadList(false), "ghost", "refresh", { disabled: L.loading })]),
        rec, tabs, mine,
        L.loaded || !L.loading ? null : el("p", { class: "civic-r04-muted" }, "Загрузка списка…"),
        shown.length ? el("ul", { class: "civic-r04-list", "aria-label": "Записи" }, rows)
          : L.loaded ? el("p", { class: "civic-r04-muted" }, L.filter === "draft" ? "Черновиков нет. Создайте объект кнопкой выше." : "Записей в этом разделе нет.") : null,
        L.next ? btn("Показать ещё", () => loadList(true), "ghost", "more", { disabled: L.loading }) : null,
      ].filter(Boolean)));
    }
    function updateListCache(item) {
      const L = S.list, i = L.items.findIndex((x) => x && x.id === item.id);
      if (i >= 0) L.items[i] = item; else L.items.unshift(item);
    }

    // ---------- open / new ----------
    function newObject() {
      if (!S.session || !S.session.authenticated) { showLogin(); return; }
      stashIfDirty();
      openEditor(null, []);
    }
    async function openObject(objectId) {
      if (!S.alive) return false;
      if (!S.session || !S.session.authenticated) { showLogin(); return false; }
      if (typeof objectId !== "string" || !objectId) return false;
      stashIfDirty();
      detachMap();
      S.view = "loading";
      render();
      try {
        const d = await call("GET", "/staff/objects/" + enc(objectId));
        if (!d || !d.item) throw Object.assign(new Error("Пустой ответ"), { status: 404 });
        openEditor(d.item, d.history);
        return true;
      } catch (e) {
        if (e === STALE) return false;
        const n = handleError(e);
        if (n.kind !== "auth") await showList(false);
        if (n.kind !== "auth") { S.alert = Object.assign({ type: "error", actions: [] }, n); renderAlertOnly(); }
        return false;
      }
    }
    function openEditor(item, history) {
      detachMap();
      S.item = item || null;
      S.history = Array.isArray(history) ? history : [];
      if (item && Object.prototype.hasOwnProperty.call(item, "internal_notes")) S.internalNotes = true;
      S.form = C.formFromItem(item);
      S.saved = clone(S.form);
      S.mirror = !item || (item.publication === "draft" && S.form.current_planned_end === S.form.original_planned_end);
      Object.assign(S, { errors: {}, warnings: {}, server: {}, touched: {}, tried: false, confirm: null, reason: "", reasonErr: null,
        conflict: null, notice: null, preview: false, publicCopy: null, dup: null, lastDirty: false, alert: null });
      S.restore = RECOVERY.get(item ? item.id : "new") || null;
      S.view = "edit";
      renderHead();
      buildEditor();
      attachMap();
      focusKey("edit-h");
    }
    function stashIfDirty(quiet) {
      if (S.view !== "edit" || !S.form || !isDirty()) return;
      const key = S.item ? S.item.id : "new";
      const title = S.form.title.trim() || (S.item && S.item.title) || "Новый объект";
      RECOVERY.set(key, { base: clone(S.item), form: clone(S.form), at: now().toISOString(), title, revision: S.item ? S.item.revision : null });
      persistRecovery();
      if (!quiet) say("Несохранённые правки «" + title + "» остались в памяти этой вкладки.");
    }
    // Keep the tab copy current while typing, so a reload or a crash does not lose the form.
    let liveTimer = null;
    function scheduleLiveStash() {
      if (liveTimer) { clearTimeout(liveTimer); timers.delete(liveTimer); }
      liveTimer = setTimeout(() => {
        timers.delete(liveTimer); liveTimer = null;
        if (!S.alive || S.view !== "edit" || !S.form) return;
        if (isDirty()) stashIfDirty(true);
        else if (!S.restore) dropRecovery(S.item ? S.item.id : "new");
      }, 600);
      timers.add(liveTimer);
    }
    function isDirty() { return S.view === "edit" && !!S.form && !same(S.form, S.saved); }
    function currentFields() { return C.fieldsFromForm(S.form, { internalNotes: S.internalNotes }); }
    function today() { return C.todayIso(now()); }

    // ---------- editor ----------
    function field(key, label, control, help, extra) {
      const id = P + "f-" + key.replace(/[^a-zA-Z0-9_-]/g, "-");
      control.id = id;
      control.setAttribute("data-fk", key);
      const helpEl = help ? el("p", { class: "civic-r04-help", id: id + "-help" }, help) : null;
      const err = el("p", { class: "civic-r04-err", id: id + "-err" });
      const warn = el("p", { class: "civic-r04-warn", id: id + "-warn" });
      control.setAttribute("aria-describedby", [helpEl && helpEl.id, err.id, warn.id].filter(Boolean).join(" "));
      F[key] = { control, err, warn };
      return el("div", { class: "civic-r04-field" }, [el("label", { for: id }, label), extra ? el("div", { class: "civic-r04-inline" }, [control, extra]) : control, helpEl, err, warn]);
    }
    function input(key, attrs) {
      const x = el("input", Object.assign({ type: "text", autocomplete: "off" }, attrs || {}));
      x.value = S.form[key] || "";
      const upd = () => { S.form[key] = x.value; changed(key); };
      x.addEventListener("input", upd);
      x.addEventListener("change", upd);
      x.addEventListener("blur", () => touch(key));
      return x;
    }
    function textarea(key, rows) {
      const x = el("textarea", { rows: rows || 3 });
      x.value = S.form[key] || "";
      x.addEventListener("input", () => { S.form[key] = x.value; changed(key); });
      x.addEventListener("blur", () => touch(key));
      return x;
    }
    function select(key, options, placeholder) {
      const x = el("select", {}, [placeholder ? el("option", { value: "" }, placeholder) : null].concat(Object.entries(options).map(([v, l]) => el("option", { value: v }, l))));
      x.value = S.form[key] || "";
      x.addEventListener("change", () => { S.form[key] = x.value; changed(key); touch(key); });
      return x;
    }
    function dateField(key, label, help, readonly) {
      const x = input(key, { type: "date", min: "1990-01-01", max: "2100-12-31", readonly: !!readonly, "aria-readonly": readonly ? "true" : null });
      const clear = readonly ? null : btn("× неизвестно", () => { x.value = ""; S.form[key] = ""; changed(key); x.focus(); }, "mini", "clear-" + key, { "aria-label": "Очистить: " + label + " (неизвестно)" });
      return field(key, label, x, help, clear);
    }
    function section(title, kids, cls) {
      return el("fieldset", { class: "civic-r04-sec" + (cls ? " " + cls : "") }, [el("legend", {}, title)].concat(kids));
    }

    function buildEditor() {
      const it = S.item, acts = C.allowedActions(it, S.session), locked = C.isOriginalLocked(it);
      for (const k of Object.keys(F)) delete F[k];
      for (const k of ["reauth", "restore", "conflict", "geom", "sources", "diff", "reason", "buttons", "msg", "preview", "history"]) V[k] = el("div", { class: "civic-r04-slot-" + k });
      V.msg.setAttribute("class", "civic-r04-slot-msg");
      const meta = it
        ? el("p", { class: "civic-r04-meta" }, [badge(C.PUBLICATION[it.publication] || String(it.publication), "pub-" + it.publication),
          " ред. " + it.revision + " · обновлено " + C.fmtDateTime(it.updated_at) + " · ID " + it.id])
        : el("p", { class: "civic-r04-meta" }, [badge("Будет черновиком", "pub-draft"), " ID и номер редакции назначит сервер. Жители черновик не видят."]);
      const banner = !it ? null
        : it.publication === "archived" ? el("p", { class: "civic-r04-msg civic-r04-msg-info" }, "Запись в архиве: только просмотр. Возврат из архива в civic-v1 не предусмотрен.")
        : it.publication === "published" && C.pendingInfo(it).pending ? el("p", { class: "civic-r04-msg civic-r04-msg-warn" }, "Есть сохранённые, но не опубликованные изменения: жители видят прежнюю версию" + (it.staff.published_revision ? " (ред. " + it.staff.published_revision + ")" : "") + ". Нажмите «Опубликовать изменения…».")
        : it.publication === "published" && C.pendingInfo(it).known ? el("p", { class: "civic-r04-msg civic-r04-msg-info" }, "Запись опубликована. Сохранённые правки станут видны жителям после «Опубликовать изменения…»; причина попадёт в историю.")
        : it.publication === "published" ? el("p", { class: "civic-r04-msg civic-r04-msg-info" }, "Запись опубликована. Сохранённые изменения сразу видны жителям и записываются в историю с причиной.")
        : null;

      const sec1 = section("1. Что это", [
        field("title", "Название *", input("title"), "Повторяющиеся названия допустимы: запись различает серверный ID."),
        field("kind", "Тип объекта *", select("kind", C.KINDS, "— выберите тип —")),
        field("status", "Статус работ", select("status", C.STATUSES), "Не знаете — оставьте «Статус неизвестен». Публикация записи не означает, что работы идут."),
        field("description", "Описание для жителей", textarea("description", 4), "Обычный текст без разметки: что делается и как это влияет на проход и проезд."),
      ]);
      const origHelp = locked
        ? "Зафиксирован при первой публикации" + (S.form.original_planned_end ? " (" + C.fmtDate(S.form.original_planned_end) + ")" : "") + " и не меняется. Переносите актуальный срок."
        : "Обещанная дата окончания. После первой публикации останется в карточке как исходное обещание.";
      const sec2 = section("2. Сроки", [
        el("p", { class: "civic-r04-help" }, "Плановый срок — дата по плану. «Фактически завершено» — только когда работы действительно закончены. Пустое поле = «неизвестно»: сегодняшняя дата сама не подставляется."),
        el("div", { class: "civic-r04-grid" }, [
          dateField("planned_start", "Плановое начало"),
          dateField("original_planned_end", "Плановое окончание — первоначальное", origHelp, locked),
          dateField("current_planned_end", "Плановое окончание — актуальное",
            locked ? "Перенос опубликованного срока сохраняется в истории вместе с причиной." : "Пока даты совпадают, поле повторяет первоначальное; измените его, если срок уже перенесён."),
          dateField("actual_end", "Фактически завершено", "Только при статусе «Завершено» и только по факту. Будущая дата не принимается."),
        ]),
      ]);
      const sec3 = section("3. Место на карте", [V.geom]);
      const amountCtl = input("amount", { inputmode: "decimal", placeholder: "неизвестно" });
      const srcSel = select("budget_source_id", {}, "— нет источника —");
      const sec4 = section("4. Ответственный и стоимость", [
        el("div", { class: "civic-r04-grid" }, [
          field("organization", "Ответственная организация", input("organization"), "Как в источнике. Пусто = не указано."),
          field("public_contact", "Публичный контакт", input("public_contact"), "Телефон приёмной или сайт организации — не личный номер сотрудника."),
          field("amount", "Стоимость, ₸", amountCtl, "Пусто = неизвестно (не ноль). Сумма сохраняется только с основанием и источником."),
          field("basis", "Что это за сумма", select("basis", C.BASIS)),
          field("budget_source_id", "Источник суммы", srcSel, "Выберите из источников в разделе 5."),
        ]),
      ]);
      const ev = el("fieldset", { class: "civic-r04-radios", id: P + "f-evidence_type", "aria-describedby": P + "f-evidence_type-err" }, [el("legend", {}, "Насколько сведения подтверждены *")]
        .concat(Object.entries(C.EVIDENCE).map(([v, l], i) => {
          const r = el("input", { type: "radio", name: P + "evidence", value: v, id: P + "ev-" + v, "data-fk": i === 0 ? "evidence_type" : "ev-" + v, checked: S.form.evidence_type === v });
          r.addEventListener("change", () => { if (r.checked) { S.form.evidence_type = v; changed("evidence_type"); touch("evidence_type"); } });
          return el("label", { class: "civic-r04-radio", for: r.id }, [r, " ", l]);
        })));
      const evErr = el("p", { class: "civic-r04-err", id: P + "f-evidence_type-err" }), evWarn = el("p", { class: "civic-r04-warn" });
      F.evidence_type = { control: ev.querySelector("input"), err: evErr, warn: evWarn };
      const sec5 = section("5. Источники и достоверность", [
        el("div", { class: "civic-r04-field" }, [ev, evErr, evWarn]),
        el("p", { class: "civic-r04-help" }, "Тип выбираете вы — система его не подставляет. Ввод сотрудником не означает «официально подтверждено»."),
        el("details", { class: "civic-r04-hint" }, [el("summary", {}, "Как указать источник"), el("ul", {}, [
          el("li", {}, "Ссылка на официальную страницу или документ (gov.kz, решение акимата, извещение о закупке)."),
          el("li", {}, "«Дата публикации» — когда источник опубликован; «Когда вы его открыли» — дата проверки."),
          el("li", {}, "Отметьте, что именно он подтверждает: сроки, место, стоимость. Старый план не доказывает, что работы идут сейчас."),
          el("li", {}, "Если страница не открылась — так и укажите «Недоступен»: это не доказательство отсутствия данных."),
        ])]),
        V.sources,
        field("evidence_notes", "Пояснение к достоверности (видно жителям)", textarea("evidence_notes", 2), "Например: «сроки по объявлению от 01.10.2026, фактическое состояние не проверено»."),
        S.internalNotes ? field("internal_notes", "Внутренняя заметка — не публикуется", textarea("internal_notes", 2), "Видна только редакторам; не попадает в карточку жителя и публичную историю.") : null,
      ].filter(Boolean));

      const ro = !acts.edit;
      const form = el("form", { class: "civic-r04-form", novalidate: true, "aria-labelledby": P + "edit-h" }, [
        el("fieldset", { class: "civic-r04-plain", disabled: ro }, [sec1, sec2, sec3, sec4, sec5])]);
      form.addEventListener("submit", (e) => { e.preventDefault(); save(); });
      const actions = el("div", { class: "civic-r04-actions", role: "region", "aria-label": "Сохранение и публикация" }, [V.diff, V.reason, V.msg, V.buttons]);
      body.replaceChildren(el("div", { class: "civic-r04-edit" }, [
        el("div", { class: "civic-r04-bar" }, [
          btn("← Все записи", () => showList(true), "link", "back"),
          el("h3", { id: P + "edit-h", tabindex: "-1", "data-fk": "edit-h" }, it ? it.title || "(без названия)" : "Новый объект"), meta]),
        V.reauth, V.restore, V.conflict, banner, form, V.preview, V.history, actions].filter(Boolean)));
      renderGeometry(); renderSources(); renderReauth(); renderRestore(); renderConflict(); renderPreview(); renderHistory();
      renderDiff(); renderReason(); renderButtons();
      V.msg.replaceChildren(...[msgBlock(S.notice)].filter(Boolean));
      revalidate();
    }

    function touch(key) { if (!S.touched[key]) { S.touched[key] = true; paintErrors(); } }
    function changed(key) {
      delete S.server[key];
      if (key === "current_planned_end") S.mirror = false;
      if (key === "original_planned_end" && S.mirror) {
        S.form.current_planned_end = S.form.original_planned_end;
        if (F.current_planned_end) F.current_planned_end.control.value = S.form.current_planned_end;
        delete S.server.current_planned_end;
      }
      if (/^sources\.\d+\.(url|publisher)$/.test(key)) renderBudgetSourceOptions();
      revalidate();
      refreshDirty();
    }
    function revalidate() {
      if (!S.form) return;
      const r = C.validateForm(S.form, { today: today(), item: S.item });
      S.errors = r.errors;
      S.warnings = r.warnings;
      paintErrors();
    }
    function errorOf(k) { return S.server[k] || (S.tried || S.touched[k] ? S.errors[k] : "") || ""; }
    function paintErrors() {
      for (const [k, f] of Object.entries(F)) {
        const msg = errorOf(k);
        f.err.textContent = msg;
        f.warn.textContent = msg ? "" : S.warnings[k] || "";
        if (f.control) { if (msg) f.control.setAttribute("aria-invalid", "true"); else f.control.removeAttribute("aria-invalid"); }
      }
    }
    function refreshDirty() {
      scheduleLiveStash();
      const d = isDirty();
      if (d !== S.lastDirty) { S.lastDirty = d; renderReason(); renderButtons(); }
      renderDiff();
      if (S.preview) renderPreview();
    }

    // ----- place (Point / LineString on the shared map) -----
    function renderGeometry() {
      if (!V.geom) return;
      const g = S.form.geometry, t = S.tool, ro = !C.allowedActions(S.item, S.session).edit;
      delete F.geometry; delete F.geometry_precision; delete F.geometry_confirmed;
      const kids = [el("p", { class: "civic-r04-help" }, "Нет достоверного места — оставьте пустым: запись сохранится и будет показана жителям списком, без точки на карте.")];
      if (!map) kids.push(el("p", { class: "civic-r04-warn" }, "Карта недоступна — введите координаты вручную."));
      if (t) {
        kids.push(el("p", { class: "civic-r04-tool", role: "status" }, t.mode === "point"
          ? "Щёлкните по карте в месте работ. Esc — отмена."
          : "Щёлкайте по карте вдоль участка работ. Точек: " + t.vertices.length + ". «Готово» — минимум две. Esc — отмена."));
        kids.push(el("p", { class: "civic-r04-row-btns" }, [
          t.mode === "line" ? btn("Готово", finishLine, "primary", "tool-done", { disabled: t.vertices.length < 2 }) : null,
          t.mode === "line" ? btn("Убрать последнюю точку", () => { t.vertices.pop(); renderGeometry(); syncMap(); }, "", "tool-undo", { disabled: !t.vertices.length }) : null,
          btn("Отмена", () => { closeTool(); focusKey("tool-point"); }, "ghost", "tool-cancel")].filter(Boolean)));
      } else {
        kids.push(el("p", { class: "civic-r04-row-btns" }, [
          btn(g ? "Поставить точку заново" : "Указать точку на карте", () => startTool("point"), "", "tool-point", { disabled: !map || ro }),
          btn("Отметить участок (линия)", () => startTool("line"), "", "tool-line", { disabled: !map || ro }),
          g ? btn("Показать на карте", fitToGeometry, "ghost", "geo-show", { disabled: !map }) : null,
          g ? btn("Удалить место", () => { setGeometry(null); say("Место удалено: запись будет без координат."); focusKey("tool-point"); }, "danger", "geo-remove", { disabled: ro }) : null,
        ].filter(Boolean)));
      }
      const pt = g && g.type === "Point" ? g.coordinates : null;
      const lat = el("input", { type: "text", inputmode: "decimal", autocomplete: "off", id: P + "lat", "data-fk": "geometry", placeholder: "51.12825" });
      const lon = el("input", { type: "text", inputmode: "decimal", autocomplete: "off", id: P + "lon", "data-fk": "geo-lon", placeholder: "71.43042" });
      lat.value = pt ? String(pt[1]) : "";
      lon.value = pt ? String(pt[0]) : "";
      const err = el("p", { class: "civic-r04-err", id: P + "geo-err" }), warn = el("p", { class: "civic-r04-warn" });
      lat.setAttribute("aria-describedby", err.id); lon.setAttribute("aria-describedby", err.id);
      const apply = () => {
        const la = C.parseCoord(lat.value), lo = C.parseCoord(lon.value);
        if (!Number.isFinite(la) || !Number.isFinite(lo)) { S.server.geometry = "Введите числа: широта ≈ 51.1, долгота ≈ 71.4 (точка или запятая)."; paintErrors(); lat.focus(); return; }
        setGeometry({ type: "Point", coordinates: [round6(lo), round6(la)] });
        say("Точка задана координатами. Подтвердите расположение.");
        focusKey("geometry_confirmed");
      };
      for (const x of [lat, lon]) x.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); apply(); } });
      kids.push(el("fieldset", { class: "civic-r04-coords" }, [
        el("legend", {}, g && g.type !== "Point" ? "Задать вместо участка одну точку (WGS84)" : "Координаты точки (WGS84)"),
        el("div", { class: "civic-r04-grid" }, [
          el("div", { class: "civic-r04-field" }, [el("label", { for: lat.id }, "Широта"), lat]),
          el("div", { class: "civic-r04-field" }, [el("label", { for: lon.id }, "Долгота"), lon])]),
        el("p", { class: "civic-r04-row-btns" }, [btn("Применить координаты", apply, "", "geo-apply", { disabled: ro })]),
        err, warn]));
      F.geometry = { control: lat, err, warn };
      if (g && g.type !== "Point") {
        kids.push(el("p", { class: "civic-r04-help" }, (g.type === "LineString" ? "Участок работ" : "Контур") + ", точек: " + C.positionsOf(g).length + ". Чтобы изменить — отметьте участок заново."));
        kids.push(el("ol", { class: "civic-r04-vertices" }, C.positionsOf(g).map((p) => el("li", {}, p[1].toFixed(5) + ", " + p[0].toFixed(5)))));
      }
      if (g) {
        const cb = el("input", { type: "checkbox", id: P + "f-geometry_confirmed", "data-fk": "geometry_confirmed", checked: S.form.geometry_confirmed });
        cb.addEventListener("change", () => { S.form.geometry_confirmed = cb.checked; delete S.server.geometry; revalidate(); refreshDirty(); });
        kids.push(el("label", { class: "civic-r04-check civic-r04-confirm", for: cb.id }, [cb, " Расположение проверено: место на карте соответствует источнику или осмотру"]));
        kids.push(field("geometry_precision", "Точность места", select("geometry_precision", C.PRECISION), "«Точно по источнику» — только если источник даёт координаты или адрес; поставленная вручную точка — «Приблизительно»."));
      }
      rebuild(V.geom, kids);
      paintErrors();
    }
    function setGeometry(g) {
      S.form.geometry = g;
      S.form.geometry_confirmed = false;
      if (g && S.form.geometry_precision === "unknown") S.form.geometry_precision = "approximate";
      if (!g) S.form.geometry_precision = "unknown";
      delete S.server.geometry; delete S.server.geometry_precision;
      renderGeometry(); syncMap(); revalidate(); refreshDirty();
    }
    function toolGeometry() {
      const v = S.tool.vertices;
      if (!v.length) return null;
      return S.tool.mode === "point" || v.length === 1 ? { type: "Point", coordinates: v[v.length - 1] } : { type: "LineString", coordinates: v.slice() };
    }
    function geomData() {
      const g = S.tool ? toolGeometry() : S.form && S.form.geometry;
      const features = [];
      if (g) {
        features.push({ type: "Feature", geometry: g, properties: {} });
        if (g.type !== "Point") for (const p of C.positionsOf(g)) features.push({ type: "Feature", geometry: { type: "Point", coordinates: p }, properties: { vertex: true } });
      }
      return { type: "FeatureCollection", features };
    }
    function syncMap() {
      if (!map || !S.mapOn) return;
      try {
        const src = map.getSource(SRC);
        if (src) { src.setData(geomData()); return; }
        map.addSource(SRC, { type: "geojson", data: geomData() });
        map.addLayer({ id: LAYERS[0], type: "line", source: SRC, filter: ["==", ["geometry-type"], "LineString"],
          paint: { "line-color": "#c17238", "line-width": 5, "line-opacity": 0.9 } });
        map.addLayer({ id: LAYERS[1], type: "circle", source: SRC, filter: ["==", ["geometry-type"], "Point"],
          paint: { "circle-radius": 7, "circle-color": "#c17238", "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
      } catch (e) { /* style not ready: the styledata handler retries */ }
    }
    function attachMap() {
      if (!map || S.mapOn) return;
      S.mapOn = true;
      onMap("styledata", syncMap);
      syncMap();
    }
    function detachMap() {
      closeTool();
      if (!map || !S.mapOn) return;
      S.mapOn = false;
      offMap("styledata", syncMap);
      try {
        for (const l of LAYERS) if (map.getLayer(l)) map.removeLayer(l);
        if (map.getSource(SRC)) map.removeSource(SRC);
      } catch (e) { /* map already removed by its owner */ }
    }
    function startTool(mode) {
      if (!map || S.busy || !C.allowedActions(S.item, S.session).edit) return;
      closeTool();
      S.tool = { mode, vertices: [] };
      try { S.cursor = map.getCanvas().style.cursor; map.getCanvas().style.cursor = "crosshair"; } catch (e) { S.cursor = ""; }
      onMap("click", onMapClick);
      onDom(document, "keydown", onToolKey);
      shell.dispatchEvent(new CustomEvent("civic-editor:tool", { bubbles: true, detail: { active: true, mode } }));
      renderGeometry(); syncMap();
      focusKey(mode === "line" ? "tool-cancel" : "tool-cancel");
      say(mode === "point" ? "Режим точки: щёлкните по карте. Esc — отмена." : "Режим участка: щёлкайте по карте вдоль участка. Esc — отмена.");
    }
    function onMapClick(e) {
      if (!S.tool || !e || !e.lngLat) return;
      const p = [round6(e.lngLat.lng), round6(e.lngLat.lat)];
      if (S.tool.mode === "point") {
        closeTool(true);
        setGeometry({ type: "Point", coordinates: p });
        say("Точка поставлена: " + p[1].toFixed(5) + ", " + p[0].toFixed(5) + ". Подтвердите расположение.");
        focusKey("geometry_confirmed");
        return;
      }
      S.tool.vertices.push(p);
      renderGeometry(); syncMap();
    }
    function finishLine() {
      if (!S.tool || S.tool.vertices.length < 2) return;
      const v = S.tool.vertices.slice();
      closeTool(true);
      setGeometry({ type: "LineString", coordinates: v });
      say("Участок отмечен, точек: " + v.length + ". Подтвердите расположение.");
      focusKey("geometry_confirmed");
    }
    function onToolKey(e) { if (e.key === "Escape" && S.tool) { e.preventDefault(); closeTool(); focusKey("tool-point"); } }
    function closeTool(quiet) {
      if (!S.tool) return;
      S.tool = null;
      offMap("click", onMapClick);
      offDom(document, "keydown", onToolKey);
      try { if (map) map.getCanvas().style.cursor = S.cursor || ""; } catch (e) { /* map gone */ }
      shell.dispatchEvent(new CustomEvent("civic-editor:tool", { bubbles: true, detail: { active: false } }));
      if (!quiet && S.view === "edit" && V.geom && S.form) { renderGeometry(); syncMap(); }
    }
    function fitToGeometry() {
      const pos = C.positionsOf(S.form && S.form.geometry);
      if (!map || !pos.length) return;
      const dur = reduced() ? 0 : 600;
      try {
        if (pos.length === 1) map.easeTo({ center: pos[0], zoom: Math.max(map.getZoom(), 15), duration: dur });
        else {
          const lons = pos.map((p) => p[0]), lats = pos.map((p) => p[1]);
          map.fitBounds([[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]], { padding: 80, maxZoom: 16, duration: dur });
        }
      } catch (e) { /* camera errors are not fatal */ }
    }

    // ----- sources -----
    function renderSources() {
      if (!V.sources) return;
      for (const k of Object.keys(F)) if (k.startsWith("sources.")) delete F[k];
      const list = S.form.sources;
      const kids = list.map((s, i) => {
        const k = (f) => "sources." + i + "." + f;
        const bindSrc = (f, x) => {
          x.value = s[f] || "";
          const upd = () => { s[f] = x.value; changed(k(f)); };
          x.addEventListener("input", upd); x.addEventListener("change", upd);
          x.addEventListener("blur", () => touch(k(f)));
          return x;
        };
        const sel = el("select", {}, Object.entries(C.ACCESS).map(([v, l]) => el("option", { value: v }, l)));
        const boxes = Object.entries(C.SOURCE_FIELDS).map(([v, l]) => {
          const cb = el("input", { type: "checkbox", value: v, "data-fk": k("fields") + "." + v, checked: (s.fields || []).includes(v) });
          cb.addEventListener("change", () => {
            s.fields = Object.keys(C.SOURCE_FIELDS).filter((f) => (f === v ? cb.checked : (s.fields || []).includes(f)));
            changed(k("fields"));
          });
          return el("label", { class: "civic-r04-check" }, [cb, " " + l]);
        });
        const fe = el("p", { class: "civic-r04-err" }), fw = el("p", { class: "civic-r04-warn" });
        F[k("fields")] = { control: null, err: fe, warn: fw };
        return el("fieldset", { class: "civic-r04-source" }, [
          el("legend", {}, "Источник " + (i + 1) + " · " + s.id),
          el("div", { class: "civic-r04-grid" }, [
            field(k("url"), "Адрес (URL) *", bindSrc("url", el("input", { type: "url", inputmode: "url", autocomplete: "off", placeholder: "https://www.gov.kz/…" }))),
            field(k("publisher"), "Кто опубликовал", bindSrc("publisher", el("input", { type: "text", autocomplete: "off", placeholder: "например, акимат Астаны" }))),
            field(k("published_on"), "Дата публикации", bindSrc("published_on", el("input", { type: "date" }))),
            field(k("retrieved_at"), "Когда вы его открыли", bindSrc("retrieved_at", el("input", { type: "date" }))),
            field(k("access_status"), "Доступ к источнику", bindSrc("access_status", sel)),
            field(k("license"), "Лицензия (если указана)", bindSrc("license", el("input", { type: "text", autocomplete: "off" }))),
          ]),
          el("fieldset", { class: "civic-r04-checks" }, [el("legend", {}, "Что подтверждает этот источник")].concat(boxes)), fe, fw,
          el("p", { class: "civic-r04-row-btns" }, [btn("Удалить источник " + (i + 1), () => removeSource(i), "danger", "src-del-" + i)]),
        ]);
      });
      kids.push(el("p", { class: "civic-r04-row-btns" }, [btn("+ Добавить источник", addSource, "", "src-add")]));
      rebuild(V.sources, kids);
      renderBudgetSourceOptions();
      paintErrors();
    }
    function addSource() {
      S.form.sources.push(C.newSource(S.form.sources));
      renderSources(); revalidate(); refreshDirty();
      focusKey("sources." + (S.form.sources.length - 1) + ".url");
    }
    function removeSource(i) {
      const s = S.form.sources[i];
      S.form.sources.splice(i, 1);
      if (s && S.form.budget_source_id === s.id) {
        S.form.budget_source_id = "";
        say("Источник суммы был удалён — выберите другой или очистите сумму.", true);
      }
      for (const k of Object.keys(S.server)) if (k.startsWith("sources.")) delete S.server[k];
      renderSources(); revalidate(); refreshDirty();
      focusKey("src-add");
    }
    function renderBudgetSourceOptions() {
      const f = F.budget_source_id;
      if (!f) return;
      const x = f.control, val = S.form.budget_source_id;
      x.replaceChildren(el("option", { value: "" }, "— нет источника —"), ...S.form.sources.map((s) => {
        let host = "";
        try { host = s.url ? new URL(s.url).hostname : ""; } catch (e) { host = ""; }
        return el("option", { value: s.id }, s.id + " — " + (s.publisher || host || "адрес не указан"));
      }));
      if (val && !S.form.sources.some((s) => s.id === val)) x.append(el("option", { value: val }, val + " — не найден"));
      x.value = val || "";
    }

    // ----- side panels -----
    function renderReauth() {
      if (!V.reauth) return;
      V.reauth.replaceChildren(...(S.reauth ? [loginForm(true)] : []));
    }
    function renderRestore() {
      if (!V.restore) return;
      const r = S.restore;
      if (!r) { V.restore.replaceChildren(); return; }
      V.restore.replaceChildren(el("div", { class: "civic-r04-msg civic-r04-msg-warn", role: "group", "aria-label": "Несохранённые правки" }, [
        el("p", {}, "В этой вкладке есть несохранённые правки этой записи от " + C.fmtDateTime(r.at) + (r.revision ? " (на основе ред. " + r.revision + ")" : "") + "."),
        el("p", { class: "civic-r04-help" }, "Это локальная копия в браузере, не запись на сервере: жители и другие редакторы её не видят, пока вы не сохраните."),
        el("p", { class: "civic-r04-row-btns" }, [btn("Восстановить правки", restoreDraft, "primary", "restore"),
          btn("Удалить из памяти", () => { dropRecovery(S.item ? S.item.id : "new"); S.restore = null; renderRestore(); focusKey("edit-h"); }, "ghost", "restore-drop")])]));
    }
    function restoreDraft() {
      const r = S.restore;
      if (!r) return;
      const res = C.rebaseForm(r.base ? C.formFromItem(r.base) : C.emptyForm(), Object.assign(C.emptyForm(), r.form), S.saved);
      dropRecovery(S.item ? S.item.id : "new");
      S.restore = null;
      S.form = res.form;
      S.mirror = false;
      buildEditor(); syncMap(); refreshDirty();
      setNotice(res.conflicts.length ? "warn" : "info", res.conflicts.length
        ? "Правки восстановлены. Эти поля за это время изменились и на сервере — оставлено ваше значение, проверьте: " + res.conflicts.map((k) => FORM_LABEL[k] || k).join(", ") + "."
        : "Правки восстановлены. Проверьте «было/станет» и сохраните.");
      focusKey("msg");
    }
    function renderConflict() {
      if (!V.conflict) return;
      if (S.dup) {
        const d = S.dup;
        V.conflict.replaceChildren(el("div", { class: "civic-r04-msg civic-r04-msg-warn", role: "group", "aria-label": "Возможный дубликат" }, [
          el("p", {}, "Связь прервалась при создании, а сервер, похоже, успел создать черновик: «" + (d.title || "") + "», ред. " + d.revision + ", " + C.fmtDateTime(d.updated_at) + "."),
          el("p", {}, "Чтобы не появилась копия, откройте его — ваши правки перенесутся в форму."),
          el("p", { class: "civic-r04-row-btns" }, [btn("Открыть найденный и перенести правки", adoptDuplicate, "primary", "dup-open"),
            btn("Это другой объект — создать новый", () => { S.dup = null; S.uncertain = null; S.createKey = null; renderConflict(); save(); }, "ghost", "dup-new")])]));
        return;
      }
      const c = S.conflict;
      if (!c) { V.conflict.replaceChildren(); return; }
      const L = c.latest, last = (c.history || []).slice().sort((a, b) => (b.revision || 0) - (a.revision || 0))[0];
      const names = (ks) => ks.map((k) => FORM_LABEL[k] || k).join(", ");
      V.conflict.replaceChildren(el("div", { class: "civic-r04-msg civic-r04-msg-error", role: "group", "aria-label": "Конфликт версий" }, [
        el("p", {}, el("b", {}, "Запись уже изменена: на сервере ред. " + L.revision + ", у вас была ред. " + (S.item && S.item.revision) + ".")),
        last ? el("p", {}, "Последнее изменение: " + C.fmtDateTime(last.at) + (last.reason ? " — «" + last.reason + "»" : "")) : null,
        c.rebase.theirs.length ? el("p", {}, "Изменено на сервере: " + names(c.rebase.theirs) + ".") : null,
        c.rebase.kept.length ? el("p", {}, "Ваши правки (сохранены в форме): " + names(c.rebase.kept) + ".") : el("p", {}, "У вас не было несохранённых правок."),
        c.rebase.conflicts.length ? el("p", { class: "civic-r04-err" }, "Изменены обеими сторонами: " + names(c.rebase.conflicts) + ". При переносе останется ваше значение — проверьте.") : null,
        L.publication !== (S.item && S.item.publication) ? el("p", {}, "Состояние публикации теперь: " + (C.PUBLICATION[L.publication] || L.publication) + ".") : null,
        el("p", { class: "civic-r04-row-btns" }, [
          c.rebase.kept.length ? btn("Перенести мои правки на новую версию", applyRebase, "primary", "rebase") : null,
          btn(c.rebase.kept.length ? "Отказаться от моих правок" : "Открыть новую версию", () => { S.conflict = null; dropRecovery(L.id); openEditor(L, c.history); setNotice("info", "Открыта актуальная версия ред. " + L.revision + "."); }, "ghost", "rebase-drop"),
        ].filter(Boolean)),
      ].filter(Boolean)));
    }
    function applyRebase() {
      const c = S.conflict;
      if (!c) return;
      S.conflict = null;
      S.item = c.latest;
      S.history = c.history || [];
      S.saved = C.formFromItem(c.latest);
      S.form = c.rebase.form;
      S.mirror = false;
      S.server = {};
      buildEditor(); syncMap(); refreshDirty();
      setNotice("info", "Ваши правки перенесены на ред. " + c.latest.revision + ". Проверьте «было/станет» и сохраните ещё раз.");
      focusKey("msg");
    }
    async function adoptDuplicate() {
      const d = S.dup, mine = clone(S.form);
      if (!d || S.busy) return;
      setBusy("open");
      try {
        const r = await call("GET", "/staff/objects/" + enc(d.id));
        S.dup = null; S.uncertain = null;
        setBusy(null);
        openEditor(r.item, r.history);
        dropRecovery("new");
        S.form = mine;
        S.mirror = false;
        buildEditor(); syncMap(); refreshDirty();
        setNotice("info", "Открыт найденный черновик, ваши правки в форме. Если «было/станет» пусто — всё уже сохранено.");
        focusKey("msg");
      } catch (e) {
        if (e === STALE) return;
        onActionError(e, "open");
      } finally { if (S.alive && S.busy === "open") setBusy(null); }
    }

    function publicCard(dto, note) {
      const sc = dto.schedule || {}, b = dto.budget || {}, r = dto.responsible || {};
      const shift = C.scheduleShift(sc);
      const badges = [badge(C.KINDS[dto.kind] || "тип не указан", "kind"), badge(C.STATUSES[dto.status] || "Статус неизвестен", "status")];
      if (dto.evidence_type === "synthetic") badges.push(badge("Синтетические данные — не сведения о реальных работах", "synthetic"));
      else if (dto.evidence_type === "hypothesis") badges.push(badge("Предположение, не подтверждено", "warn"));
      const row = (k, v) => [el("dt", {}, k), el("dd", {}, v)];
      const sources = (dto.source_refs || []).map((s) => {
        let href = null, host = "";
        try { const u = new URL(s.url); if (u.protocol === "https:" || u.protocol === "http:") { href = u.href; host = u.hostname; } } catch (e) { href = null; }
        const label = s.publisher || host || "источник";
        return el("li", {}, [href ? el("a", { href, target: "_blank", rel: "noopener noreferrer" }, label) : label,
          s.published_on ? ", опубликовано " + C.fmtDate(s.published_on) : "", " · " + (C.ACCESS[s.access_status] || "доступ неизвестен")]);
      });
      return el("article", { class: "civic-r04-card", "aria-label": "Карточка для жителей" }, [
        note ? el("p", { class: "civic-r04-card-note" }, note) : null,
        el("p", { class: "civic-r04-badges" }, badges),
        el("h4", {}, dto.title || "(без названия)"),
        dto.description ? el("p", {}, dto.description) : null,
        el("dl", {}, [].concat(
          row("Плановые сроки", C.fmtDate(sc.planned_start) + " — " + C.fmtDate(sc.current_planned_end)),
          shift ? row("Перенос срока", "было " + C.fmtDate(shift.from) + ", стало " + C.fmtDate(shift.to)) : [],
          row("Фактически завершено", sc.actual_end ? C.fmtDate(sc.actual_end) : "нет сведений"),
          row("Место", dto.geometry ? (dto.geometry.type === "Point" ? "точка на карте" : "участок на карте") + " · " + (C.PRECISION[dto.geometry_precision] || "точность неизвестна") : "без точки на карте"),
          row("Ответственный", r.organization || "не указан"),
          r.public_contact ? row("Контакт", r.public_contact) : [],
          row("Стоимость", b.amount_kzt === null || b.amount_kzt === undefined ? "неизвестно" : C.fmtMoney(b.amount_kzt) + " · " + (C.BASIS[b.basis] || b.basis)),
          row("Достоверность", C.EVIDENCE[dto.evidence_type] || "не указана"),
        )),
        dto.evidence_notes ? el("p", { class: "civic-r04-muted" }, dto.evidence_notes) : null,
        el("p", {}, el("b", {}, "Источники")),
        sources.length ? el("ul", {}, sources) : el("p", { class: "civic-r04-muted" }, "Источник не указан."),
        el("p", { class: "civic-r04-muted" }, dto.updated_at ? "Обновлено " + C.fmtDateTime(dto.updated_at) + " · ред. " + dto.revision : "Дату обновления и редакцию назначит сервер при сохранении."),
      ].filter(Boolean));
    }
    function renderPreview() {
      if (!V.preview) return;
      if (!S.preview && S.confirm !== "publish") { V.preview.replaceChildren(); return; }
      const publishing = S.confirm === "publish";
      const dto = C.previewFromForm(S.item, S.form, publishing ? { publication: "published" } : null);
      const kids = [el("h4", {}, publishing ? "Так запись увидят жители после публикации" : "Предпросмотр карточки жителя")];
      if (isDirty()) kids.push(el("p", { class: "civic-r04-warn" }, "С учётом несохранённых правок. Жители увидят их только после сохранения."));
      if (dto.publication !== "published") kids.push(el("p", { class: "civic-r04-msg civic-r04-msg-info" }, dto.publication === "archived" ? "Запись в архиве: жители её не видят." : "Черновик: жители не видят эту запись, пока вы её не опубликуете."));
      kids.push(publicCard(dto, "Внутренние заметки и служебные поля сюда не попадают."));
      const pend = C.pendingInfo(S.item);
      if (pend.publicItem && (publishing || pend.pending)) {
        const d = C.diffFields(C.pickPublic(pend.publicItem), C.pickPublic(dto));
        kids.push(el("h4", {}, "Было у жителей / станет после публикации"));
        kids.push(d.length ? el("div", { class: "civic-r04-tablewrap civic-r04-diff" }, el("table", {}, [
          el("thead", {}, el("tr", {}, [el("th", { scope: "col" }, "Поле"), el("th", { scope: "col" }, "Сейчас у жителей"), el("th", { scope: "col" }, "Станет")])),
          el("tbody", {}, d.map((x) => el("tr", {}, [el("th", { scope: "row" }, x.label), el("td", {}, C.fmtValue(x.path, x.before)), el("td", {}, C.fmtValue(x.path, x.after))])))]))
          : el("p", { class: "civic-r04-muted" }, "Публичная версия уже совпадает с сохранённой."));
        if (!publishing) kids.push(publicCard(C.pickPublic(pend.publicItem), "Сейчас у жителей (опубликованная версия)."));
      }
      if (S.item && S.item.publication === "published") {
        kids.push(el("p", { class: "civic-r04-row-btns" }, [btn("Сверить с публичной версией на сервере", loadPublicCopy, "ghost", "public-copy")]));
        if (S.publicCopy) kids.push(S.publicCopy.item ? publicCard(C.pickPublic(S.publicCopy.item), "Сейчас у жителей (ответ публичного API).") : el("p", { class: "civic-r04-err" }, S.publicCopy.error));
      }
      V.preview.replaceChildren(el("section", { class: "civic-r04-preview", "aria-label": "Предпросмотр" }, kids));
    }
    async function loadPublicCopy() {
      if (!S.item) return;
      try {
        const d = await call("GET", "/objects/" + enc(S.item.id));
        S.publicCopy = { item: d && d.item };
      } catch (e) {
        if (e === STALE) return;
        const n = C.normalizeError(e);
        S.publicCopy = { error: n.kind === "not_found" ? "Публичный API не отдаёт эту запись (не опубликована или скрыта)." : n.text };
      }
      renderPreview();
      focusKey("public-copy");
    }
    function renderHistory() {
      if (!V.history) return;
      const h = (S.history || []).slice().sort((a, b) => (b.revision || 0) - (a.revision || 0));
      if (!S.item) { V.history.replaceChildren(); return; }
      V.history.replaceChildren(el("details", { class: "civic-r04-history" }, [
        el("summary", {}, "История изменений · " + h.length),
        el("p", { class: "civic-r04-help" }, "Редакторская история. Жителям сервер показывает только опубликованные изменения публичных полей."),
        h.length ? el("ol", { reversed: true }, h.map((x) => el("li", {}, [
          el("p", {}, el("b", {}, "ред. " + x.revision + " · " + C.fmtDateTime(x.at)), ),
          el("p", {}, (x.public_actor_label || "Редактор") + (x.actor_label || x.actor ? " (" + (x.actor_label || x.actor) + ")" : "") + (x.action ? " · " + (ACTION_LABEL[x.action] || x.action) : "")
            + (typeof x.is_public === "boolean" ? (x.is_public ? " · видно жителям" : " · только редакторам") : "")),
          el("p", {}, "Причина: " + (x.reason || "не указана")),
          (x.changed_fields || []).length ? el("p", { class: "civic-r04-muted" }, "Поля: " + x.changed_fields.map((f) => HISTORY_LABEL[f] || f).join(", ")) : null,
        ].filter(Boolean)))) : el("p", { class: "civic-r04-muted" }, "Записей истории пока нет."),
      ]));
    }
    function renderDiff() {
      if (!V.diff) return;
      if (!S.item || !S.form) { V.diff.replaceChildren(); return; }
      const d = C.diffFields(S.item, currentFields());
      if (!d.length) { V.diff.replaceChildren(el("p", { class: "civic-r04-muted" }, "Несохранённых изменений нет.")); return; }
      const det = el("details", { class: "civic-r04-diff", open: S.diffOpen }, [
        el("summary", {}, "Изменения: " + d.length + " — было / станет"),
        el("div", { class: "civic-r04-tablewrap" }, el("table", {}, [
          el("thead", {}, el("tr", {}, [el("th", { scope: "col" }, "Поле"), el("th", { scope: "col" }, "Было"), el("th", { scope: "col" }, "Станет")])),
          el("tbody", {}, d.map((x) => el("tr", { class: x.path === "schedule.current_planned_end" ? "civic-r04-shift" : null }, [
            el("th", { scope: "row" }, x.label), el("td", {}, C.fmtValue(x.path, x.before)), el("td", {}, C.fmtValue(x.path, x.after))])))]))]);
      det.addEventListener("toggle", () => { S.diffOpen = det.open; });
      V.diff.replaceChildren(det);
    }
    function reasonNeeded() {
      if (S.confirm) return C.reasonRule(S.item, S.confirm);
      if (S.item && isDirty()) return C.reasonRule(S.item, "update");
      return { required: false };
    }
    function renderReason() {
      if (!V.reason) return;
      const rule = reasonNeeded();
      if (!rule.required) { rebuild(V.reason, []); return; }
      const ta = el("textarea", { id: P + "reason", rows: 2, "data-fk": "reason", "aria-describedby": P + "reason-err" });
      ta.value = S.reason;
      ta.addEventListener("input", () => {
        S.reason = ta.value;
        if (S.reasonErr) { S.reasonErr = null; err.textContent = ""; ta.removeAttribute("aria-invalid"); }
      });
      const err = el("p", { class: "civic-r04-err", id: P + "reason-err" }, S.reasonErr || "");
      if (S.reasonErr) ta.setAttribute("aria-invalid", "true");
      const shifted = S.item && isDirty() && C.diffFields(S.item, currentFields()).some((x) => x.path === "schedule.current_planned_end");
      const chips = (shifted ? ["Перенос срока: "] : []).concat(rule.suggestions || []).filter((v, i, a) => a.indexOf(v) === i);
      const oe = S.form.original_planned_end, ce = S.form.current_planned_end;
      const fixed = oe ? "Первоначальный срок окончания будет зафиксирован: " + C.fmtDate(oe) + "."
        : ce ? "Первоначальный срок не указан — сервер зафиксирует как первоначальный актуальный срок " + C.fmtDate(ce) + "."
        : "Сроки неизвестны — в карточке будет «неизвестно».";
      const intro = S.confirm === "publish"
        ? "После публикации запись увидят жители" + (S.form.geometry ? " на карте" : " в списке (без точки на карте)") + ". " + fixed
        : S.confirm === "archive" ? "Запись исчезнет из публичного списка. Физического удаления нет — история сохраняется."
        : "Запись опубликована: причину увидят в истории изменений.";
      const kids = [
        S.confirm ? el("h4", { id: P + "confirm-h" }, S.confirm === "publish" ? "Публикация" : "Перенос в архив") : null,
        el("p", { class: "civic-r04-help" }, intro),
        el("label", { for: ta.id }, rule.title + " *"), ta,
        el("p", { class: "civic-r04-chips", "aria-label": "Быстрый выбор причины" }, chips.map((c, i) => btn(c.trim(), () => {
          S.reason = c; ta.value = c; S.reasonErr = null; err.textContent = ""; ta.removeAttribute("aria-invalid");
          ta.focus(); ta.setSelectionRange(c.length, c.length);
        }, "chip", "chip-" + i))),
        err,
      ];
      rebuild(V.reason, [el("div", { class: "civic-r04-reason" + (S.confirm ? " civic-r04-confirm-box" : ""), role: S.confirm ? "group" : null, "aria-labelledby": S.confirm ? P + "confirm-h" : null }, kids.filter(Boolean))]);
    }
    function renderButtons() {
      if (!V.buttons || S.view !== "edit") return;
      const it = S.item, acts = C.allowedActions(it, S.session), dirty = isDirty(), busy = !!S.busy || S.reauth;
      let kids;
      if (S.confirm) {
        kids = [btn(S.busy === S.confirm ? "Отправляем…" : S.confirm === "publish" ? "Подтвердить публикацию" : "Перенести в архив", () => doTransition(S.confirm), S.confirm === "publish" ? "primary" : "danger", "confirm", { disabled: busy, "aria-busy": S.busy ? "true" : null }),
          btn("Отмена", cancelConfirm, "ghost", "confirm-cancel", { disabled: !!S.busy })];
      } else {
        const saveLabel = S.busy === "save" ? "Сохраняем…" : !it ? "Создать черновик" : it.publication === "published" ? "Сохранить изменения" : "Сохранить черновик";
        kids = [
          acts.edit ? btn(saveLabel, save, "primary", "save", { disabled: busy || (it && !dirty), "aria-busy": S.busy === "save" ? "true" : null }) : null,
          btn(S.preview ? "Скрыть предпросмотр" : "Как увидят жители", () => { S.preview = !S.preview; renderPreview(); renderButtons(); focusKey("preview"); }, "", "preview", { "aria-expanded": String(!!S.preview) }),
          acts.publish && it ? btn(it.publication === "published" ? "Опубликовать изменения…" : "Опубликовать…", () => askConfirm("publish"), "", "publish", { disabled: busy || dirty }) : null,
          acts.archive && it ? btn("В архив…", () => askConfirm("archive"), "ghost", "archive", { disabled: busy || dirty }) : null,
        ].filter(Boolean);
        if (dirty && it && (acts.publish || acts.archive)) kids.push(el("p", { class: "civic-r04-help" }, "Публикация и архив доступны после сохранения изменений."));
      }
      rebuild(V.buttons, [el("div", { class: "civic-r04-row-btns" }, kids)]);
    }
    function setBusy(kind) {
      S.busy = kind;
      shell.setAttribute("aria-busy", kind ? "true" : "false");
      if (S.view === "edit") renderButtons();
    }
    function askConfirm(action) {
      if (S.busy || isDirty() || !S.item) return;
      S.confirm = action; S.reason = ""; S.reasonErr = null;
      renderPreview(); renderReason(); renderButtons();
      focusKey("reason");
    }
    function cancelConfirm() {
      const a = S.confirm;
      S.confirm = null; S.reason = ""; S.reasonErr = null;
      renderPreview(); renderReason(); renderButtons();
      focusKey(a || "save");
    }

    // ---------- save / publish / archive ----------
    function firstErrorKey() { return Object.keys(F).find((k) => errorOf(k)); }
    function focusField(k) {
      const f = F[k];
      if (f && f.control && !f.control.disabled) { f.control.focus(); if (f.control.scrollIntoView) f.control.scrollIntoView({ block: "center", behavior: reduced() ? "auto" : "smooth" }); }
    }
    async function save() {
      if (S.busy || !S.form || S.view !== "edit") return;
      const it = S.item;
      if (!C.allowedActions(it, S.session).edit) return;
      S.tried = true;
      revalidate();
      const fields = currentFields();
      const rule = it ? C.reasonRule(it, "update") : { required: false };
      let changes = null;
      if (it) {
        changes = C.buildChanges(it, fields);
        if (!Object.keys(changes).length) { setNotice("info", "Изменений нет — сохранять нечего."); return; }
      }
      S.reasonErr = rule.required ? C.validateReason(S.reason) : S.reason.trim() ? C.validateReason(S.reason) : null;
      const bad = Object.keys(S.errors);
      if (bad.length || S.reasonErr) {
        renderReason();
        const keys = bad.concat(S.reasonErr ? ["reason"] : []);
        setNotice("error", "Не сохранено: исправьте отмеченные поля (" + keys.length + "). Введённый текст на месте.", keys.slice(0, 6).map((k) => ({
          label: FORM_LABEL[k] || FORM_LABEL[k.split(".")[0]] || k, fk: "goto-" + k, cls: "link", fn: () => (k === "reason" ? focusKey("reason") : focusField(k)) })));
        if (bad.length) focusField(firstErrorKey() || bad[0]); else focusKey("reason");
        return;
      }
      setBusy("save");
      try {
        let item, ignored = [];
        if (!it) {
          if (S.uncertain) {
            const d = await call("GET", "/staff/objects");
            const dup = C.findPossibleDuplicate(d && d.items, fields, S.uncertain.since);
            if (dup) { S.dup = dup; renderConflict(); setNotice("warn", "Найден похожий черновик — выберите, что сделать, чтобы не создать копию."); focusKey("dup-open"); return; }
          }
          // One key per submitted content: a replay of the same attempt (lost answer, browser transport retry) can be
          // recognised by a server that supports Idempotency-Key (contract_delta); changed content gets a new key.
          const fp = JSON.stringify(fields);
          if (!S.createKey || S.createKey.fp !== fp) S.createKey = { key: newKey(), fp };
          const d = await call("POST", "/staff/objects", fields, { idempotencyKey: S.createKey.key });
          item = d && d.item;
          ignored = d && Array.isArray(d.ignored_fields) ? d.ignored_fields : [];
          S.uncertain = null;
          S.createKey = null;
          dropRecovery("new");
        } else {
          const reason = S.reason.trim() || null;
          const d = await call("POST", "/staff/objects/" + enc(it.id) + "/update", { expected_revision: it.revision, changes, reason });
          item = d && d.item;
          ignored = d && Array.isArray(d.ignored_fields) ? d.ignored_fields : [];
          dropRecovery(it.id);
        }
        if (!item || !item.id) throw Object.assign(new Error("Сервер не вернул сохранённую запись"), { status: 500 });
        const wasPublic = !!it && it.publication === "published";
        const pend = C.pendingInfo(item);
        S.reason = "";
        await reloadDetail(item);
        const msg = !it ? "Черновик создан (ред. " + item.revision + "). Жители его не видят."
          : "Сохранено (ред. " + item.revision + ")." + (!wasPublic ? "" : pend.known
            ? " Жители пока видят опубликованную версию — чтобы показать правки, нажмите «Опубликовать изменения…»."
            : " Изменение видно жителям и записано в историю.");
        if (ignored.length) setNotice("warn", msg + " Сервер не принял поля: " + ignored.join(", ") + " — они не сохранены.");
        else setNotice("ok", msg);
        focusKey("msg");
        if (wasPublic && !pend.known) notifyPublished(item, "update");
        updateListCache(item);
      } catch (e) {
        if (e === STALE) return;
        const n = C.normalizeError(e);
        if (!it && (n.kind === "network" || n.kind === "server")) S.uncertain = { since: new Date(now().getTime() - 10 * 60 * 1000).toISOString() };
        onActionError(e, "save");
      } finally {
        if (S.alive && S.busy === "save") setBusy(null);
      }
    }
    async function doTransition(action) {
      if (S.busy || !S.item || isDirty()) return;
      S.reasonErr = C.validateReason(S.reason);
      if (S.reasonErr) { renderReason(); focusKey("reason"); say(S.reasonErr, true); return; }
      const it = S.item, wasPublic = it.publication === "published";
      setBusy(action);
      try {
        const d = await call("POST", "/staff/objects/" + enc(it.id) + "/" + action, { expected_revision: it.revision, reason: S.reason.trim() });
        const item = d && d.item;
        if (!item || !item.id) throw Object.assign(new Error("Сервер не вернул запись"), { status: 500 });
        S.confirm = null; S.reason = "";
        await reloadDetail(item);
        setNotice("ok", action === "publish"
          ? (wasPublic ? "Изменения опубликованы (ред. " + item.revision + ")." : item.geometry ? "Опубликовано: жители видят запись на карте." : "Опубликовано: жители видят запись в списке, без точки на карте.")
          : "Запись в архиве и скрыта из публичного списка. История сохранена.");
        focusKey("msg");
        if (action === "publish" || wasPublic) notifyPublished(item, action);
        updateListCache(item);
      } catch (e) {
        if (e === STALE) return;
        onActionError(e, action);
      } finally {
        if (S.alive && S.busy === action) setBusy(null);
      }
    }
    async function reloadDetail(item) {
      let it = item, hist = S.history;
      try {
        const d = await call("GET", "/staff/objects/" + enc(item.id));
        if (d && d.item) { it = d.item; hist = d.history || []; }
      } catch (e) {
        if (e === STALE) throw e;
        /* the action itself succeeded; history refresh can wait */
      }
      const notice = S.notice;
      setBusy(null);
      openEditor(it, hist);
      S.notice = notice;
    }
    function notifyPublished(item, action) {
      if (!onPublished) return;
      try { onPublished(C.pickPublic(item), { action }); } catch (e) { console.error("CivicEditor onPublished:", e); }
    }
    async function loadConflict(n, action) {
      const it = S.item;
      try {
        const d = await call("GET", "/staff/objects/" + enc(it.id));
        const latest = d.item;
        S.conflict = { latest, history: d.history || [], rebase: C.rebaseForm(S.saved, S.form, C.formFromItem(latest)) };
        S.confirm = null;
        renderConflict(); renderReason(); renderPreview(); renderButtons();
        setNotice("error", action === "save" ? n : { text: "Запись изменилась на сервере — возможно, действие уже выполнено при обрыве связи. Проверьте состояние ниже." });
        focusKey(S.conflict.rebase.kept.length ? "rebase" : "rebase-drop");
      } catch (e) {
        if (e === STALE) return;
        setNotice("error", C.normalizeError(e));
      }
    }
    function onActionError(e, action) {
      const n = C.normalizeError(e);
      const retry = { label: "Повторить", fk: "retry", fn: () => (action === "save" ? save() : action === "publish" || action === "archive" ? doTransition(action) : null) };
      if (n.kind === "auth") {
        S.reauth = true;
        renderReauth(); renderButtons();
        setNotice("error", n);
        focusKey("relogin-user");
        return;
      }
      if (n.kind === "conflict") { loadConflict(n, action); return; }
      if (n.kind === "validation") {
        S.server = {};
        for (const [k, m] of Object.entries(n.fields)) { if (k === "reason") S.reasonErr = m; else if (k !== "_form") S.server[k] = m; }
        paintErrors(); renderReason();
        setNotice("error", { text: n.text, detail: n.fields._form || n.detail });
        const k = firstErrorKey();
        if (k) focusField(k); else if (S.reasonErr) focusKey("reason"); else focusKey("msg");
        return;
      }
      if (n.kind === "csrf") {
        call("GET", "/session").then(applySession, () => {});
        setNotice("error", n, [retry]);
        focusKey("msg");
        return;
      }
      if (n.kind === "transition" || n.kind === "not_found") {
        setNotice("error", n);
        if (S.item && n.kind === "transition") loadConflict(n, action);
        return;
      }
      if (S.uncertain && action === "save") {
        setNotice("error", { text: n.text + " Сервер мог успеть создать черновик: при повторе сначала проверим список, чтобы не появилась копия.", detail: n.detail }, [retry]);
      } else setNotice("error", n, n.kind === "network" || n.kind === "server" ? [retry] : []);
      focusKey("msg");
    }
    function handleError(e) {
      const n = C.normalizeError(e);
      if (n.kind === "auth") {
        if (S.view === "edit") { S.reauth = true; renderReauth(); renderButtons(); setNotice("error", n); focusKey("relogin-user"); }
        else { S.session = { authenticated: false, user: null }; showLogin(Object.assign({ type: "error", actions: [] }, n, { text: "Сессия истекла или не начата. Войдите снова." })); }
      } else if (S.view === "edit") setNotice("error", n);
      else { S.alert = Object.assign({ type: "error", actions: [] }, n); renderAlertOnly(); say(n.text, true); }
      return n;
    }

    // ---------- logout / destroy ----------
    function askLogout() {
      if (isDirty()) { S.logoutAsk = true; renderHead(); focusKey("logout-confirm"); }
      else doLogout();
    }
    async function doLogout() {
      S.epoch++;  // answers to requests of the closed session are ignored from here on
      detachMap();
      clearRecovery();
      Object.assign(S, { session: { authenticated: false, user: null }, view: "login", item: null, form: null, saved: null, history: [],
        list: { items: [], next: null, filter: "draft", mine: false, loaded: false, loading: false }, busy: null, confirm: null, reason: "",
        conflict: null, reauth: false, uncertain: null, createKey: null, dup: null, restore: null, preview: false, publicCopy: null, notice: null, alert: null, logoutAsk: false });
      shell.setAttribute("aria-busy", "false");
      render();
      say("Вы вышли. Редакторские действия закрыты.");
      focusKey("login-user");
      try {
        await call("POST", "/session/logout", {});
        setCsrf(null);
      } catch (e) {
        if (e === STALE) return;
        const n = C.normalizeError(e);
        if (n.kind === "auth") { setCsrf(null); return; }
        S.alert = { type: "error", text: "Сервер не подтвердил выход (" + n.text + ") Редактор в этой вкладке закрыт, но серверная сессия может действовать до истечения срока.", detail: n.detail,
          actions: [{ label: "Повторить выход", fk: "logout-retry", fn: doLogout }] };
        renderAlertOnly();
        say(S.alert.text, true);
      }
    }
    function destroy() {
      if (!S.alive) return;
      stashIfDirty();  // unsaved text stays in this page's memory for the next mount
      detachMap();
      S.alive = false;
      S.epoch++;
      for (const [t, type, fn] of domListeners.splice(0)) t.removeEventListener(type, fn);
      if (map) for (const [type, fn] of mapHandlers.splice(0)) map.off(type, fn);
      for (const t of timers) clearTimeout(t);
      timers.clear();
      root.replaceChildren();
    }

    // ---------- start ----------
    (async function boot() {
      render();
      try { applySession(await call("GET", "/session")); }
      catch (e) {
        if (e === STALE) return;
        S.session = { authenticated: false, user: null };
        S.alert = Object.assign({ type: "error", actions: [{ label: "Повторить", fk: "boot-retry", fn: () => { S.alert = null; boot(); } }] }, C.normalizeError(e));
      }
      if (S.session.authenticated) await showList(true); else showLogin();
    })();

    return {
      openObject: (id) => openObject(id),
      destroy,
    };
  }

  NS.mount = mount;
})();
