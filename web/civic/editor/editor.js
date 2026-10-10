/* R04 staff editor UI (round 11, civic-v1).
 * window.CivicEditor.mount({root, map, api, onPublished}) -> {openObject, setMap, destroy}
 *   map: a MapLibre map, null, or a function returning the map once it is ready (looked up again before drawing).
 *   root        element given to the editor (it owns the children, never document.body);
 *   map         the one shared MapLibre instance, or null (coordinates can then be typed);
 *   api         R01 adapter: api.request(method, path, body) -> Promise<data>; cookies and CSRF are its job;
 *   onPublished (publicItem, {action, visible}) after the public version changed: publish, edit of a published record,
 *               archive (visible:false — do not open it on the public map).
 * Optional: apiPrefix (default "", paths are relative to /api/civic/v1), internalNotes:true, now() for tests.
 * The server decides rights. The UI never derives rights from a browser role and keeps no session in storage.
 * Unsaved text (RECOVERY) lives in this page's memory and, to survive a reload or a tab crash, in this tab's
 * sessionStorage: form fields only (never passwords, tokens or the CSRF value), kept per signed-in user (another
 * user signing in in this tab never sees them), removed after a successful save, on "Удалить из памяти" and on
 * logout of that user. It is a local copy, not the server record.
 */
(function () {
  "use strict";
  const NS = (window.CivicEditor = window.CivicEditor || {});
  const C = NS.core;
  if (!C) { console.error("CivicEditor: load web/civic/editor/editor-core.js before editor.js"); return; }

  const RECOVERY = new Map();  // object id | "new" -> {base, form, at, title, revision}; this tab only
  const STORE_KEY = "civic-r04-unsaved:v1";  // value format v2: {v:2, users:{<user>: {<id|"new">: copy}}}
  const STORE = (() => {
    try { const s = window.sessionStorage, k = "civic-r04-probe"; s.setItem(k, k); s.removeItem(k); return s; } catch (e) { return null; }
  })();
  let storeUser = null;  // the user whose unsaved edits RECOVERY currently holds
  function readStore() {
    try {
      const d = JSON.parse(STORE.getItem(STORE_KEY) || "null");
      if (d && d.v === 2 && d.users && typeof d.users === "object") return d;
      if (d && d.v === 1 && typeof d.user === "string" && d.entries && typeof d.entries === "object") return { v: 2, users: { [d.user]: d.entries } };
    } catch (e) { /* damaged copy: start empty */ }
    return { v: 2, users: {} };
  }
  function persistRecovery() {
    if (!STORE) return;
    try {
      const all = readStore();
      if (storeUser) { if (RECOVERY.size) all.users[storeUser] = Object.fromEntries(RECOVERY); else delete all.users[storeUser]; }
      if (Object.keys(all.users).length) STORE.setItem(STORE_KEY, JSON.stringify(all)); else STORE.removeItem(STORE_KEY);
    } catch (e) { /* quota or privacy mode: memory copy still works */ }
  }
  // After the server confirms who is signed in: RECOVERY holds only that user's local copies.
  function loadRecovery(user) {
    if (storeUser !== (user || null)) RECOVERY.clear();
    storeUser = user || null;
    if (!STORE || !storeUser) return;
    const mine = readStore().users[storeUser] || {};
    for (const [k, r] of Object.entries(mine)) if (!RECOVERY.has(k) && r && r.form && typeof r.form === "object") RECOVERY.set(k, r);
  }
  function dropRecovery(key) { if (RECOVERY.delete(key)) persistRecovery(); }
  function clearRecovery() { RECOVERY.clear(); persistRecovery(); storeUser = null; }  // logout: this user's copies only
  let seq = 0;
  // streets.json (≈280 KB, served with no-store) is fetched once per page, on the first use of the street search.
  const STREETS = { state: "idle", list: [], snapshot: null, url: null, promise: null };
  function loadStreetsFrom(url) {
    if (STREETS.promise && STREETS.url === url) return STREETS.promise;
    STREETS.url = url; STREETS.state = "loading";
    STREETS.promise = fetch(url, { credentials: "same-origin" }).then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then((d) => {
        STREETS.list = Array.isArray(d && d.streets) ? d.streets : [];
        STREETS.snapshot = d && d.source && d.source.snapshot_at ? d.source.snapshot_at : null;
        STREETS.state = STREETS.list.length ? "ok" : "unavailable";
      }, () => { STREETS.state = "unavailable"; STREETS.promise = null; });
    return STREETS.promise;
  }
  // R12 (раунд 14): привязка к улицам и объектам OSM — функции engine/civic_geo, маршруты подключает R01
  // под /api/civic/v2 (research/round-14-results/R12/INTEGRATION.txt). Ответ с ошибкой -> Error с .status/.code/.message.
  function geoClient(prefix) {
    const get = (path, params) => fetch(prefix + path + "?" + new URLSearchParams(params), { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(async (r) => {
        let body = null;
        try { body = await r.json(); } catch (e) { body = null; }
        if (r.ok && body) return body;
        const err = new Error((body && body.error && body.error.message) || "HTTP " + r.status);
        err.status = r.status; err.code = body && body.error ? body.error.code : null;
        throw err;
      });
    const kindOf = (kind) => (kind === "foot" ? { kind: "foot" } : { kind: "road" });
    return {
      snap: (p, kind) => get("/street-snap", Object.assign({ lon: p[0], lat: p[1] }, kindOf(kind))),
      segment: (a, b, kind) => get("/street-segment", Object.assign({ from: a.join(","), to: b.join(",") }, kindOf(kind))),
      near: (p) => get("/objects-near", { lon: p[0], lat: p[1] }),
      yard: (p) => get("/yard", { lon: p[0], lat: p[1] }),
    };
  }
  // R11 i18n (раунд 14): новые строки R12 идут через ключи BirgeI18n, если словарь подключён и ключ в нём есть
  // (ключи и черновик kk — research/round-14-results/R12/INTEGRATION.txt §7); иначе — русский текст как раньше.
  function tr(key, ru, params) {
    const B = typeof window !== "undefined" ? window.BirgeI18n : null;
    if (B && typeof B.t === "function" && typeof B.has === "function" && (B.has(key) || B.has(key, "ru"))) return B.t(key, params);
    return params ? String(ru).replace(/\{(\w+)\}/g, (w, n) => (params[n] == null ? w : String(params[n]))) : ru;
  }
  const metres = (n) => Math.round(Number(n) || 0).toLocaleString("ru-RU");  // «1 666», как просит UX_BRIEF
  // Понятный текст ошибки привязки (без «Ошибка:» и без технических слов).
  function geoErrorText(err) {
    if (!err) return "Не получилось. Повторите.";
    if (err.status === 404 || err.status === 405) return tr("editor.geo.not_wired", "Привязка к улицам на этом сервере не подключена. Отметьте точку или площадь.");
    if (err.status === 400 && err.message && !/^HTTP/.test(err.message)) return err.message;
    if (err.status >= 500) return "Сервер не ответил. Повторите через минуту.";
    return "Нет связи с сервером. Проверьте подключение и повторите.";
  }
  // Synchronous view of "is an editor drawing on the map right now" for neighbours (R03 click/hover, R01 Escape):
  // window.CivicEditor.isDrawing() / activeTool(), and <html data-civic-editor-tool="point|line|area|edit">.
  // The 'civic-editor:tool' event carries the same state; the attribute and getters do not depend on listener order.
  let ACTIVE_TOOL = null;
  function setActiveTool(mode) {
    ACTIVE_TOOL = mode || null;
    try {
      if (ACTIVE_TOOL) document.documentElement.setAttribute("data-civic-editor-tool", ACTIVE_TOOL);
      else document.documentElement.removeAttribute("data-civic-editor-tool");
    } catch (e) { /* no document */ }
  }
  NS.isDrawing = () => !!ACTIVE_TOOL;
  NS.activeTool = () => ACTIVE_TOOL;
  const FORM_LABEL = {
    title: "Название", kind: "Тип", status: "Статус работ", description: "Описание",
    planned_start: "Плановое начало", original_planned_end: "Первоначальный плановый срок", current_planned_end: "Актуальный плановый срок",
    actual_end: "Фактически завершено", geometry: "Место", geometry_precision: "Точность места", place: "Что известно о месте", organization: "Организация",
    public_contact: "Публичный контакт", amount: "Стоимость", basis: "Основание суммы", budget_source_id: "Источник суммы",
    evidence_type: "Достоверность", evidence_notes: "Пояснение к достоверности", internal_notes: "Внутренняя заметка", sources: "Источники",
    reason: "Причина",
  };
  const HISTORY_LABEL = Object.assign({}, C.PATH_LABEL, { publication: "Публикация", schedule: "Сроки", budget: "Стоимость", responsible: "Ответственный" });
  const ACTION_LABEL = { create: "создание", update: "изменение", publish: "публикация", archive: "архив", import_create: "импорт", import_update: "импорт" };
  // Подписи вкладок — ключи словаря R11 (staff.cabinet.tab.*); текст берётся при отрисовке, когда словарь уже загружен.
  const FILTERS = [["draft", "Черновики"], ["published", "Опубликованные"], ["archived", "Архив"], ["all", "Все"]];
  const FILTER_KEYS = { draft: "staff.cabinet.tab.draft", published: "staff.cabinet.tab.published", archived: "staff.cabinet.tab.archive", all: "staff.cabinet.tab.all" };

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
    const root = o.root, api = o.api;
    const mapGetter = typeof o.map === "function" ? o.map : null;
    let map = mapGetter ? null : o.map || null;
    if (!root || root.nodeType !== 1) throw new TypeError("CivicEditor.mount: root element is required");
    if (!api || typeof api.request !== "function") throw new TypeError("CivicEditor.mount: api.request is required");
    const P = "civic-r04-" + ++seq + "-";
    const apiPrefix = typeof o.apiPrefix === "string" ? o.apiPrefix : "";
    const onPublished = typeof o.onPublished === "function" ? o.onPublished : null;
    const now = typeof o.now === "function" ? o.now : () => new Date();
    const STALE = Object.freeze({ stale: true });
    const SRC = P + "geom", LAYERS = [P + "geom-line", P + "geom-pt", P + "geom-fill"];
    const SRC_STREET = P + "street", LAYER_STREET = P + "street-box";  // dashed frame of a found street (approximate)
    const streetsUrl = typeof o.streetsUrl === "string" ? o.streetsUrl : "/civic/map/streets.json";
    // R12: o.geo === false — без привязки (инструмент «Участок улицы» выключен); o.geo = {snap, segment, near, yard} — свой клиент.
    const geoApi = o.geo === false ? null : o.geo && typeof o.geo.segment === "function" ? o.geo
      : geoClient(typeof o.geoPrefix === "string" ? o.geoPrefix : "/api/civic/v2");
    const S = {
      epoch: 0, alive: true, session: null, view: "loading", alert: null,
      list: { items: [], next: null, filter: "draft", mine: false, loaded: false, loading: false },
      item: null, history: [], form: null, saved: null, mirror: false, internalNotes: o.internalNotes === true,
      errors: {}, warnings: {}, server: {}, touched: {}, tried: false, busy: null, confirm: null, reason: "", reasonErr: null,
      conflict: null, reauth: false, uncertain: null, createKey: null, dup: null, restore: null, tool: null, cursor: "", preview: false, publicCopy: null,
      notice: null, logoutAsk: false, lastDirty: false, mapOn: false, diffOpen: true,
      near: null, linked: null, segKind: "road",
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
      else if (S.view === "edit" && (S.reauth || S.conflict || S.dup || (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)))) {
        e.preventDefault();  // keep the cabinet open; it closes by its button or Escape outside a field
        say("Escape в поле не закрывает кабинет. Закрыть — кнопкой закрытия или Escape вне поля.");
      }
    });
    root.replaceChildren(shell);

    function onDom(target, type, fn) { target.addEventListener(type, fn); domListeners.push([target, type, fn]); }
    function offDom(target, type, fn) {
      target.removeEventListener(type, fn);
      const i = domListeners.findIndex((x) => x[0] === target && x[1] === type && x[2] === fn);
      if (i >= 0) domListeners.splice(i, 1);
    }
    function onMap(type, fn) { if (!map) return; map.on(type, fn); mapHandlers.push([type, fn]); }
    // The cabinet may open before the map is ready (R01 passes map=null then): look the map up again lazily.
    let resolving = false;
    function resolveMap() {
      if (!mapGetter || !S.alive || resolving) return map;
      let m = null;
      try { m = mapGetter(); } catch (e) { m = null; }
      if (!(m && typeof m.on === "function")) return map;  // not (yet) available: keep what we have
      if (m === map) return map;
      resolving = true;
      try {
        if (map) setMap(m);  // the host rebuilt its map: move layers and listeners to the new instance
        else { map = m; if (S.view === "edit" && S.form) attachMap(); }
      } finally { resolving = false; }
      return map;
    }
    function setMap(m) {
      const next = m && typeof m.on === "function" ? m : null;
      if (!S.alive || next === map) return;
      detachMap();
      for (const [type, fn] of mapHandlers.splice(0)) { try { map.off(type, fn); } catch (e) { /* old map gone */ } }
      map = next;
      if (S.view === "edit" && S.form) { attachMap(); renderGeometry(); }
    }
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
    const userKey = (sess) => (sess && sess.authenticated ? (sess.user && sess.user.name ? String(sess.user.name) : "?") : null);
    // Returns true when the tab is now signed in as a DIFFERENT user (e.g. a login in another tab replaced the cookie).
    function applySession(d) {
      const prev = S.session;
      const next = { authenticated: !!(d && d.authenticated), user: (d && d.user) || null };
      const switched = !!(prev && prev.authenticated && next.authenticated && userKey(prev) !== userKey(next));
      if (switched) {
        S.epoch++;  // answers and retries of the previous user's requests are dropped
        stashIfDirty(true);  // the previous user's unsaved form stays in HIS bucket of the tab copy
        closeTool();
      }
      S.session = next;
      setCsrf(d && d.csrf_token);
      if (next.authenticated) { loadRecovery(userKey(next)); loadRules(); }
      if (switched) {
        S.switchedFrom = userKey(prev);
        if (pendingOpen) { pendingOpen.resolve(false); pendingOpen = null; }
      }
      return switched;
    }
    // Rules of validation: from GET /staff/meta when the server routes it, else the editor's copy of R02's rules.
    // Asked once per mount; a 404 is reported as "local copy", never as a working endpoint.
    function loadRules() {
      if (S.rules) return;
      S.rules = { source: "checking" };
      api.request("GET", apiPrefix + "/staff/meta").then((d) => {
        const r = C.applyServerMeta(C.unwrap(d));
        S.rules = r ? { source: "server", changed: r.changed } : { source: "local", why: "ответ /staff/meta не распознан" };
      }, (e) => {
        const n = C.normalizeError(e);
        S.rules = { source: "local", why: n.status === 404 || n.status === 405 ? "сервер не отдаёт /staff/meta" : "не удалось получить /staff/meta (" + n.text + ")" };
      }).then(() => { if (S.alive) { renderHead(); if (S.view === "edit" && S.form) revalidate(); } });
    }
    // Before every write: is this tab still signed in as the same user? (A login in another tab replaces the cookie,
    // and the R01 adapter re-sends a CSRF-rejected POST after refreshing the session — that must never carry the
    // previous user's form.) Not signed in -> let the write get its 401 and the in-place re-login.
    async function sameUserBeforeWrite() {
      let d = null;
      try { d = await call("GET", "/session"); } catch (e) { if (e === STALE) throw e; return true; }  // network: the write reports it
      if (!d || !d.authenticated) return true;
      if (applySession(d)) { await afterSwitch(); return false; }
      return true;
    }
    function afterSwitch() {  // the form of the previous user is never shown to (or saved as) the new one
      const who = S.switchedFrom;
      S.switchedFrom = null;
      detachMap();
      S.internalNotes = o.internalNotes === true;
      // drop the previous user's form from the page before anything can stash it into the new user's copy
      Object.assign(S, { view: "loading", item: null, form: null, saved: null, history: [], confirm: null, conflict: null, reauth: false,
        uncertain: null, createKey: null, dup: null, restore: null, preview: false, publicCopy: null, notice: null, logoutAsk: false,
        list: { items: [], next: null, filter: "draft", mine: false, loaded: false, loading: false } });
      S.alert = { type: "warn", text: "В этой вкладке теперь вход «" + userKey(S.session) + "» (сессия сменилась, например, после входа в другой вкладке). "
        + "Форма пользователя «" + who + "» закрыта и не отправлена; его несохранённые правки остались в этой вкладке и вернутся, когда он снова войдёт.", actions: [] };
      return showList(true);
    }
    // Navigation token: an answer that arrives after the user went elsewhere does not open anything.
    let navSeq = 0;
    const nav = () => ++navSeq;
    // openObject() called before the session check of mount finished: its promise waits for that one request.
    // While signed out it resolves false at once (contract) but the record is still opened right after login.
    let pendingOpen = null;  // {id, resolve}
    const noop = () => {};
    function deferOpen(id) {
      if (pendingOpen) pendingOpen.resolve(false);
      return new Promise((resolve) => { pendingOpen = { id, resolve }; });
    }
    function rememberOpen(id) {
      if (pendingOpen) pendingOpen.resolve(false);
      pendingOpen = { id, resolve: noop };
    }
    async function takePendingOpen() {
      const p = pendingOpen;
      pendingOpen = null;
      if (!p) return false;
      const ok = await openObject(p.id);
      p.resolve(ok);
      return true;
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
      if (S.view === "loading") body.replaceChildren(el("p", { class: "civic-r04-muted" }, tr("staff.cabinet.loading", "Загрузка…")));
      else if (S.view === "login") renderLogin();
      else if (S.view === "list") renderList();
      else if (S.view === "edit") buildEditor();
    }
    function renderHead() {
      const kids = [el("h2", { id: P + "h" }, tr("staff.cabinet.title", "Кабинет сотрудника"))];
      if (S.session && S.session.authenticated) {
        const u = S.session.user || {};
        const rules = S.rules && S.rules.source !== "checking" ? el("span", { class: "civic-r04-rules", "data-fk": "rules",
          title: S.rules.source === "server" ? "Лимиты, границы и поля источников получены с сервера." : "Окончательно решает сервер при сохранении." },
          S.rules.source === "server" ? " · правила проверки с сервера (/staff/meta)" : " · правила проверки: локальная копия правил R02 (" + S.rules.why + ")") : null;
        kids.push(el("p", { class: "civic-r04-who" }, ["Вы вошли: ", el("b", {}, u.name || "сотрудник"), u.role ? " · роль по данным сервера: " + u.role : "", rules].filter(Boolean)));
        if (S.logoutAsk) {
          kids.push(el("div", { class: "civic-r04-ask", role: "group", "aria-label": tr("staff.logout.confirm_title", "Выйти без сохранения?") }, [
            el("p", {}, tr("staff.logout.confirm_text", "Есть несохранённые правки. Если выйти, они пропадут.")),
            btn(tr("staff.logout.discard", "Выйти без сохранения"), doLogout, "danger", "logout-confirm"),
            btn(tr("staff.logout.stay", "Остаться"), () => { S.logoutAsk = false; renderHead(); focusKey("logout"); }, "", "logout-cancel")]));
        } else kids.push(btn(tr("staff.login.logout", "Выйти"), askLogout, "ghost", "logout"));
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
      const submit = el("button", { type: "submit", class: "civic-r04-btn primary", "data-fk": reauth ? "relogin-submit" : "login-submit" }, tr("staff.login.submit", "Войти"));
      const hid = P + (reauth ? "re-" : "") + "login-h";
      const f = el("form", { class: "civic-r04-login" + (reauth ? " civic-r04-reauth" : ""), novalidate: true, "aria-labelledby": hid }, [
        el(reauth ? "h4" : "h3", { id: hid, tabindex: "-1", "data-fk": reauth ? "relogin-h" : "login-h" }, reauth ? tr("staff.login.expired", "Сессия истекла — войдите снова") : tr("staff.login.title", "Вход для сотрудника")),
        el("p", { class: "civic-r04-help" }, reauth
          ? tr("staff.login.kept", "Ваши правки остались в форме. После входа нажмите «Сохранить» ещё раз.")
          : tr("staff.login.note", "Учётную запись выдаёт администратор.")),
        el("div", { class: "civic-r04-field" }, [el("label", { for: u.id }, tr("staff.login.username", "Имя пользователя")), u]),
        el("div", { class: "civic-r04-field" }, [el("label", { for: p.id }, tr("staff.login.password", "Пароль")), p, err]),
        el("p", { class: "civic-r04-row-btns" }, [submit]),
      ]);
      f.addEventListener("submit", (ev) => { ev.preventDefault(); login(u, p, err, submit, reauth); });
      return f;
    }
    async function login(u, p, err, submit, reauth) {
      if (S.busy) return;
      err.textContent = "";
      p.removeAttribute("aria-invalid");
      if (!u.value.trim() || !p.value) { err.textContent = tr("staff.login.empty", "Введите имя пользователя и пароль."); (u.value.trim() ? p : u).focus(); return; }
      const creds = { username: u.value.trim(), password: p.value };
      p.value = "";  // the password does not stay in the page after sending
      setBusy("login");
      submit.disabled = true;
      let switched = false;
      try {
        switched = applySession(await call("POST", "/session/login", creds));
      } catch (e) {
        if (e === STALE) return;
        const n = C.normalizeError(e);
        err.textContent = n.kind === "auth" || n.kind === "validation" ? tr("staff.login.wrong", "Неверное имя пользователя или пароль.") : n.text;
        p.setAttribute("aria-invalid", "true");
        say(err.textContent, true);
        p.focus();
        return;
      } finally {
        if (S.alive) { setBusy(null); submit.disabled = false; }
      }
      if (!S.session.authenticated) { err.textContent = tr("staff.login.failed", "Сервер не подтвердил вход."); return; }
      S.alert = null;
      renderHead();
      if (switched) { S.reauth = false; await afterSwitch(); return; }
      if (reauth) {
        S.reauth = false;
        renderReauth();
        setNotice("ok", tr("staff.login.again", "Вы снова вошли. Правки на месте — нажмите «Сохранить» ещё раз."));
        renderButtons();
        focusKey("save");
      } else if (!(await takePendingOpen())) await showList(true);
    }
    function renderLogin() {
      body.replaceChildren(el("div", { class: "civic-r04-topmsg" }, [msgBlock(S.alert)].filter(Boolean)), loginForm(false));
    }

    async function showList(reload) {
      nav();
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
          onclick: () => { L.filter = k; renderList(); focusKey("filter-" + k); } }, tr(FILTER_KEYS[k], label) + " · " + L.items.filter((it) => it && pass(it, k)).length)));
      const mine = mineKnown ? el("label", { class: "civic-r04-check" }, [
        el("input", { type: "checkbox", "data-fk": "mine", checked: L.mine, onchange: (e) => { L.mine = e.target.checked; renderList(); focusKey("mine"); } }), " Только мои"]) : null;
      const rec = RECOVERY.size ? el("div", { class: "civic-r04-msg civic-r04-msg-warn" }, [
        el("p", {}, "Несохранённые правки в этой вкладке — локальная копия, не на сервере (переживёт перезагрузку страницы, пропадёт при закрытии вкладки или выходе):"),
        el("ul", {}, [...RECOVERY.entries()].map(([key, r]) => el("li", {}, [
          "«" + r.title + "», " + C.fmtDateTime(r.at) + " ",
          btn(tr("staff.cabinet.back_to_edit", "Вернуться к правке"), () => (key === "new" ? newObject() : openObject(key)), "link", "rec-" + key)])))]) : null;
      const rows = shown.map((it) => {
        const sc = it.schedule || {};
        const badges = [badge(tr("staff.pub." + it.publication, C.PUBLICATION[it.publication] || String(it.publication)), "pub-" + it.publication)];
        if (it.evidence_type === "synthetic") badges.push(badge(tr("common.tag.demo", "синтетические данные"), "synthetic"));
        if (!it.geometry) badges.push(badge(tr("works.not_on_map", "без места на карте"), "muted"));
        if (C.pendingInfo(it).pending) badges.push(badge(tr("staff.row.pending", "есть неопубликованные изменения"), "warn"));
        if (RECOVERY.has(it.id)) badges.push(badge(tr("staff.row.unsaved", "есть несохранённые правки"), "warn"));
        return el("li", {}, el("button", { type: "button", class: "civic-r04-row", "data-fk": "row-" + it.id, onclick: () => openObject(it.id) }, [
          el("span", { class: "civic-r04-row-title" }, it.title || tr("staff.cabinet.untitled", "(без названия)")),
          el("span", { class: "civic-r04-row-meta" }, (C.KINDS[it.kind] ? tr("works.kind." + it.kind, C.KINDS[it.kind]) : it.kind || "тип не указан") + " · " + (C.STATUSES[it.status] ? tr("works.status." + it.status, C.STATUSES[it.status]) : tr("works.status.unknown", "статус неизвестен"))
            + " · окончание: " + C.fmtDate(sc.current_planned_end) + " · ред. " + (it.revision === undefined ? "?" : it.revision)),
          el("span", { class: "civic-r04-badges" }, badges)]));
      });
      body.replaceChildren(el("div", { class: "civic-r04-listview" }, [
        el("div", { class: "civic-r04-topmsg" }, [msgBlock(S.alert)].filter(Boolean)),
        el("div", { class: "civic-r04-toolbar" }, [
          btn("+ " + tr("staff.cabinet.new_object", "Новый объект"), newObject, "primary", "new"),
          btn(L.loading ? tr("staff.cabinet.refreshing", "Обновляем…") : tr("staff.cabinet.refresh", "Обновить список"), () => loadList(false), "ghost", "refresh", { disabled: L.loading })]),
        rec, tabs, mine,
        L.loaded || !L.loading ? null : el("p", { class: "civic-r04-muted" }, tr("staff.cabinet.list_loading", "Загрузка списка…")),
        shown.length ? el("ul", { class: "civic-r04-list", "aria-label": tr("staff.cabinet.list_label", "Записи") }, rows)
          : L.loaded ? el("p", { class: "civic-r04-muted" }, L.filter === "draft" ? tr("staff.cabinet.no_drafts", "Черновиков нет. Создайте объект кнопкой выше.") : "Записей в этом разделе нет.") : null,
        L.next ? btn(tr("staff.cabinet.show_more", "Показать ещё"), () => loadList(true), "ghost", "more", { disabled: L.loading }) : null,
      ].filter(Boolean)));
    }
    function updateListCache(item) {
      const L = S.list, i = L.items.findIndex((x) => x && x.id === item.id);
      if (i >= 0) L.items[i] = item; else L.items.unshift(item);
    }

    // ---------- open / new ----------
    function newObject() {
      if (!S.session || !S.session.authenticated) { showLogin(); return; }
      if (pendingOpen) { pendingOpen.resolve(false); pendingOpen = null; }
      nav();
      stashIfDirty();
      openEditor(null, []);
    }
    async function openObject(objectId) {
      if (!S.alive) return false;
      if (typeof objectId !== "string" || !objectId) return false;
      if (!S.session) return deferOpen(objectId);  // mount's GET /session still running: open right after it
      if (!S.session.authenticated) {
        rememberOpen(objectId);
        showLogin({ type: "info", text: "Войдите, чтобы открыть запись.", actions: [] });
        return false;
      }
      if (pendingOpen && pendingOpen.id !== objectId) { pendingOpen.resolve(false); pendingOpen = null; }
      const my = nav();
      stashIfDirty();
      detachMap();
      // nothing of the previous record stays in memory while the next one is requested (a refusal shows no fields)
      Object.assign(S, { view: "loading", item: null, form: null, saved: null, history: [], confirm: null, conflict: null, preview: false, publicCopy: null });
      render();
      try {
        const d = await call("GET", "/staff/objects/" + enc(objectId));
        if (my !== navSeq) return false;  // the user went elsewhere meanwhile
        if (!d || !d.item) throw Object.assign(new Error("Пустой ответ"), { status: 404 });
        openEditor(d.item, d.history);
        return true;
      } catch (e) {
        if (e === STALE || my !== navSeq) return false;
        const n = handleError(e);
        if (n.kind !== "auth") await showList(false);
        if (n.kind !== "auth") { S.alert = Object.assign({ type: "error", actions: [] }, n); renderAlertOnly(); }
        return false;
      }
    }
    function openEditor(item, history) {
      detachMap();
      mapTries = 0;
      S.item = item || null;
      S.history = Array.isArray(history) ? history : [];
      if (item && Object.prototype.hasOwnProperty.call(item, "internal_notes")) S.internalNotes = true;
      S.form = C.formFromItem(item);
      S.saved = clone(S.form);
      S.mirror = !item || (item.publication === "draft" && S.form.current_planned_end === S.form.original_planned_end);
      Object.assign(S, { errors: {}, warnings: {}, server: {}, touched: {}, tried: false, confirm: null, reason: "", reasonErr: null,
        conflict: null, notice: null, preview: false, publicCopy: null, dup: null, lastDirty: false, alert: null, coordDraft: null,
        cands: { state: "idle", items: [] }, confirmCand: null, streetQ: "", streetPick: null });
      S.restore = RECOVERY.get(item ? item.id : "new") || null;
      S.view = "edit";
      renderHead();
      buildEditor();
      attachMap();
      focusKey("edit-h");
      if (pendingCandidates(item)) loadCandidates();
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
    function isDirty() { return S.view === "edit" && !!S.form && (!same(S.form, S.saved) || !!S.coordDraft); }
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
      // Length counter (as the server counts) from 80% of the limit: long official names/descriptions are not cut silently.
      const lim = C.LIMITS[key.split(".").pop()];
      const count = lim && (control.tagName === "TEXTAREA" || control.type === "text" || control.type === "url") ? el("p", { class: "civic-r04-count", "data-fk": "count-" + key }) : null;
      if (count) {
        const upd = () => {
          const n = C.textLength(control.value);
          count.textContent = n >= lim * 0.8 ? n + " / " + lim + (n > lim ? " — длиннее на " + (n - lim) : "") : "";
          count.classList.toggle("civic-r04-count-over", n > lim);
        };
        control.addEventListener("input", upd);
        upd();
      }
      return el("div", { class: "civic-r04-field" }, [el("label", { for: id }, label), extra ? el("div", { class: "civic-r04-inline" }, [control, extra]) : control, err, warn, count, helpEl]);  // the error right under the input
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
      // A half-typed date gives value "" (validity.badInput): re-check on every key so it is never saved as «unknown».
      x.addEventListener("keyup", () => revalidate());
      x.addEventListener("blur", () => revalidate());
      return field(key, label, x, help, clear);
    }
    function section(title, kids, cls) {
      return el("fieldset", { class: "civic-r04-sec" + (cls ? " " + cls : "") }, [el("legend", {}, title)].concat(kids));
    }

    function buildEditor() {
      const it = S.item, acts = C.allowedActions(it, S.session), locked = C.isOriginalLocked(it);
      for (const k of Object.keys(F)) delete F[k];
      for (const k of ["reauth", "restore", "conflict", "srcreview", "geom", "sources", "sched", "diff", "reason", "buttons", "msg", "preview", "history", "rare", "stage"]) V[k] = el("div", { class: "civic-r04-slot-" + k });
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
      const sec3 = section("3. Сроки", [
        el("p", { class: "civic-r04-help" }, "Плановый срок — дата по плану. «Фактически завершено» — только когда работы действительно закончены. Пустое поле = «неизвестно»: сегодняшняя дата сама не подставляется."),
        el("div", { class: "civic-r04-grid" }, [
          dateField("planned_start", "Плановое начало"),
          dateField("original_planned_end", "Плановое окончание — первоначальное", origHelp, locked),
          dateField("current_planned_end", "Плановое окончание — актуальное",
            locked ? "Перенос опубликованного срока сохраняется в истории вместе с причиной." : "Пока даты совпадают, поле повторяет первоначальное; измените его, если срок уже перенесён."),
          V.sched,
          dateField("actual_end", "Фактически завершено", "Только при статусе «Завершено» и только по факту. Будущая дата не принимается."),
        ]),
      ]);
      const sec2 = section("2. Место на карте", [V.geom]);
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
      // Diff and reason sit in the page flow; the sticky bar keeps only messages and buttons, so it never hides the form.
      const review = el("div", { class: "civic-r04-review" }, [V.diff, V.reason, V.rare]);
      const actions = el("div", { class: "civic-r04-actions", role: "region", "aria-label": "Сохранение и публикация" }, [V.buttons, V.msg]);  // buttons first: always reachable in a capped bar
      body.replaceChildren(el("div", { class: "civic-r04-edit" }, [
        el("div", { class: "civic-r04-bar" }, [
          btn(tr("staff.cabinet.back_to_list", "← Все записи"), () => showList(true), "link", "back"),
          el("h3", { id: P + "edit-h", tabindex: "-1", "data-fk": "edit-h" }, it ? it.title || "(без названия)" : "Новый объект"), meta]),
        V.reauth, V.restore, V.conflict, banner, V.srcreview, form, V.stage, V.preview, V.history, review, actions].filter(Boolean)));
      // R06 раунд 14: этап работ — отдельный блок со своей кнопкой и ревизией (web/civic/proposals/stage-editor.js),
      // форма и сохранение редактора не меняются. Только у сохранённой записи: у новой ещё нет ID.
      if (it && window.BirgeStageEditor) window.BirgeStageEditor.mount(V.stage, { objectId: it.id, readOnly: !acts.edit });
      renderGeometry(); renderSources(); renderSchedNote(); renderSrcReview(); renderReauth(); renderRestore(); renderConflict(); renderPreview(); renderHistory();
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
      if (key === "evidence_type") delete S.server.sources;
      if (/planned|actual_end/.test(key)) renderSchedNote();
      revalidate();
      refreshDirty();
    }
    function partialDates() {
      return Object.keys(F).filter((k) => { const c = F[k].control; return c && c.type === "date" && c.validity && c.validity.badInput; });
    }
    function revalidate() {
      if (!S.form) return;
      const r = C.validateForm(S.form, { today: today(), item: S.item, partialDates: partialDates() });
      if (S.coordDraft && placeNow() !== "unknown")  // more precise than "no mark yet": the user did type a point
        r.errors.geometry = "Координаты введены, но не применены — нажмите «Применить координаты» (или Enter) либо очистите оба поля.";
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
      refreshFixNotice();
    }
    // A "Не сохранено: исправьте …" message must not outlive the problems it lists.
    function refreshFixNotice() {
      const n = S.notice;
      if (!n || !n.fixKeys || S.view !== "edit" || !V.msg) return;
      const left = n.fixKeys.filter((k) => (k === "reason" ? reasonNeeded().required && !!C.validateReason(S.reason) : !!errorOf(k)));
      if (left.length) return;
      S.notice = { type: "info", text: "Отмеченные ошибки исправлены — можно сохранять.", detail: "", actions: [] };
      V.msg.replaceChildren(msgBlock(S.notice));
    }
    function renderSchedNote() {
      if (!V.sched || !S.form) return;
      const n = C.scheduleNote(S.form, S.item);
      V.sched.replaceChildren(el("p", { class: "civic-r04-note", "data-fk": "sched-note" }, n.resident),
        ...(n.change ? [el("p", { class: "civic-r04-note civic-r04-note-change", "data-fk": "sched-change" }, n.change)] : []));
    }
    function refreshDirty() {
      scheduleLiveStash();
      const d = isDirty();
      if (d !== S.lastDirty) { S.lastDirty = d; renderReason(); renderButtons(); if (S.cands && S.cands.items && S.cands.items.length) renderSrcReview(); }
      renderDiff();
      if (S.preview) renderPreview();
    }

    // ----- place: what is known, then Point / LineString / Polygon on the shared map -----
    const TOOL_TEXT = {
      edit: "Щёлкните по вершине на карте (или выберите её в списке), затем щёлкните, куда её перенести. Стрелки — сдвиг на ≈5 м, Delete — удалить вершину, Ctrl+Z — отменить шаг, Enter — готово, Esc — отмена без изменений.",
      point: "Щёлкните по карте в месте работ. Esc — отмена.",
      line: "Щёлкайте по карте вдоль участка улицы (не обязательно по каждому повороту). «Готово» — от двух точек. Esc — отмена.",
      segment: "Нажмите на улицу в начале участка — точка встанет на ось улицы. Затем нажмите на конец участка: линия пройдёт точно по улице. Esc — отмена.",
      yard: "Нажмите внутри двора на карте — выделится весь двор по карте OSM. Esc — отмена.",
      area: "Щёлкайте по карте по углам двора, сквера или площадки — по порядку обхода. «Готово» — от трёх точек, контур замкнётся сам. Esc — отмена.",
    };
    const TOOL_KEYS = { segment: "editor.seg.hint", yard: "editor.yard.hint" };
    const toolText = (mode) => (TOOL_KEYS[mode] ? tr(TOOL_KEYS[mode], TOOL_TEXT[mode]) : TOOL_TEXT[mode]);
    function placeNow() { return S.form.place || C.placeOf(S.form.geometry, S.form.geometry_precision); }
    function setPlace(v) {
      S.form.place = v;
      delete S.server.place; delete S.server.geometry;
      if (v !== "unknown" && S.form.geometry && !S.form.geometry_confirmed) S.form.geometry_confirmed = false;
      if (v === "unknown") closeTool();
      renderGeometry(); syncMap(); revalidate(); refreshDirty();
    }
    // With a map getter: re-check a few times with back-off (about a minute in total per opened record), then only on
    // a click on a drawing button or via setMap(). No endless polling; nothing runs outside the edit view.
    const MAP_WAIT_MS = [1000, 2000, 4000, 8000, 15000, 30000];
    let mapWait = null, mapTries = 0;
    function waitForMap() {
      if (mapWait || map || !mapGetter || mapTries >= MAP_WAIT_MS.length) return;
      mapWait = setTimeout(() => {
        timers.delete(mapWait); mapWait = null; mapTries++;
        if (!S.alive || S.view !== "edit") return;
        if (resolveMap()) renderGeometry(); else waitForMap();
      }, MAP_WAIT_MS[mapTries]);
      timers.add(mapWait);
    }
    function stopMapWait() { if (mapWait) { clearTimeout(mapWait); timers.delete(mapWait); mapWait = null; } }
    function renderGeometry() {
      if (!V.geom) return;
      if (!resolveMap()) waitForMap();
      const g = S.form.geometry, t = S.tool, ro = !C.allowedActions(S.item, S.session).edit, place = placeNow();
      delete F.geometry; delete F.geometry_precision; delete F.geometry_confirmed; delete F.place;
      const kids = [];
      // 1) What is known about the place: explicit, never guessed.
      const radios = el("fieldset", { class: "civic-r04-radios civic-r04-place", id: P + "f-place", "aria-describedby": P + "f-place-err " + P + "f-place-warn" },
        [el("legend", {}, "Что известно о месте *")].concat(Object.entries(C.PLACE).map(([v, l], i) => {
          const r = el("input", { type: "radio", name: P + "place", value: v, id: P + "pl-" + v, "data-fk": "place-" + v, checked: place === v, disabled: ro });
          r.addEventListener("change", () => { if (r.checked) { setPlace(v); touch("place"); } });
          return el("label", { class: "civic-r04-radio", for: r.id }, [r, " ", l]);
        })));
      const placeErr = el("p", { class: "civic-r04-err", id: P + "f-place-err" }), placeWarn = el("p", { class: "civic-r04-warn", id: P + "f-place-warn" });
      F.place = { control: radios.querySelector("input"), err: placeErr, warn: placeWarn };
      kids.push(radios, placeErr, placeWarn);
      if (!ro && !t) kids.push(streetSearch());
      const drawRow = (withMarkTools) => el("p", { class: "civic-r04-row-btns" }, [
        btn(g && g.type === "Point" && withMarkTools ? "Поставить точку заново" : "Точка", () => startTool("point"), "", "tool-point", { disabled: (!map && !mapGetter) || ro, title: "Объект в одном месте: здание, остановка, перекрёсток" }),
        // R12: линии — только по улице (два нажатия), «от руки» линию больше не рисуем (CONTRACT §8.1).
        btn(g && g.type === "LineString" && withMarkTools ? tr("editor.tool.segment_again", "Выбрать участок улицы заново") : tr("editor.tool.segment", "Участок улицы"), () => startTool("segment"), "", "tool-segment",
          { disabled: (!map && !mapGetter) || ro || !geoApi, title: geoApi ? "Ремонт или перекрытие вдоль улицы: нажмите на начало и на конец участка" : "Привязка к улицам не подключена" }),
        btn(tr("editor.tool.yard", "Выбрать двор"), () => startTool("yard"), "", "tool-yard", { disabled: (!map && !mapGetter) || ro || !geoApi, title: "Двор целиком по карте OSM" }),
        btn(g && g.type === "Polygon" && withMarkTools ? "Отметить площадь заново" : tr("editor.tool.area_corners", "Площадь по углам"), () => startTool("area"), "", "tool-area", { disabled: (!map && !mapGetter) || ro, title: "Сквер, площадка: углы по порядку обхода" }),
        g && withMarkTools && g.type === "Polygon" ? btn("Изменить вершины", () => startTool("edit"), "", "tool-edit", { disabled: (!map && !mapGetter) || ro, title: "Передвинуть, удалить вершины; отменить шаг" }) : null,
        g && withMarkTools ? btn("Показать на карте", fitToGeometry, "ghost", "geo-show", { disabled: !map }) : null,
        g && withMarkTools ? btn("Удалить отметку", () => { setGeometry(null); say("Отметка удалена."); focusKey("tool-point"); }, "danger", "geo-remove", { disabled: ro }) : null,
      ].filter(Boolean));
      if (place === "unknown") {
        kids.push(el("p", { class: "civic-r04-help" }, "Запись сохранится и будет показана жителям списком, без точки на карте. Точку можно добавить позже, когда место станет известно."));
        if (g) kids.push(el("p", { class: "civic-r04-help" }, "Ранее отмеченное место (" + C.describeGeometry(g) + ") осталось в форме, но не будет отправлено. Выберите другой вариант, чтобы вернуть его."));
        // drawing stays one click away: starting a tool switches the choice to «приблизительно» (said aloud and in the form)
        kids.push(el("p", { class: "civic-r04-help" }, "Если место известно хотя бы приблизительно — отметьте его на карте, выбор сменится на «приблизительно»."));
        kids.push(drawRow(false));
        rebuild(V.geom, kids); paintErrors(); return;
      }
      if (place === "exact") kids.push(el("p", { class: "civic-r04-help" }, "Отметьте место так, как оно указано в источнике, и отметьте у этого источника «Место» в разделе «Источники»."));
      if (!map) kids.push(el("p", { class: "civic-r04-warn", "data-fk": "map-wait" }, mapGetter
        ? "Карта ещё загружается. Кнопки рисования заработают, когда она будет готова; можно сразу ввести координаты точки ниже."
        : "Карта недоступна — введите координаты точки вручную ниже."));
      // 2) Drawing on the map.
      if (t && t.mode === "edit") {
        const min = t.type === "Polygon" ? 3 : 2;
        kids.push(el("p", { class: "civic-r04-tool", role: "status" }, TOOL_TEXT.edit));
        if (t.problem) kids.push(el("p", { class: "civic-r04-err", role: "alert" }, t.problem));
        kids.push(el("ol", { class: "civic-r04-vertices civic-r04-vxlist", "aria-label": "Вершины" }, t.vertices.map((v, i) => el("li", {},
          btn("Вершина " + (i + 1) + ": " + v[1].toFixed(5) + ", " + v[0].toFixed(5), () => { t.selected = i; t.problem = null; renderGeometry(); syncMap(); focusKey("vx-" + i); },
            "link", "vx-" + i, { "aria-pressed": String(t.selected === i) })))));
        kids.push(el("p", { class: "civic-r04-row-btns" }, [
          btn("Готово", finishEdit, "primary", "tool-done"),
          btn("Отменить шаг", undoEdit, "", "tool-undo", { disabled: !t.undo.length }),
          btn("Удалить вершину", deleteVertex, "", "vx-del", { disabled: t.selected === null || t.vertices.length <= min }),
          btn("Отмена", () => { closeTool(); focusKey("tool-edit"); }, "ghost", "tool-cancel")]));
      } else if (t && (t.mode === "segment" || t.mode === "yard")) {
        kids.push(el("p", { class: "civic-r04-tool", role: "status" }, toolText(t.mode)));
        if (t.mode === "segment") {
          // Смена вида отменяет и ответ, который ещё в пути (t.seq++), — иначе начало «прилипнет» к старому виду.
          const kindBtn = (k, label) => btn(label, () => { if (S.segKind !== k) { S.segKind = k; t.seq++; t.pending = false; t.start = null; t.result = null; t.problem = null; renderGeometry(); syncMap(); } }, S.segKind === k ? "primary" : "", "seg-kind-" + k, { "aria-pressed": String(S.segKind === k) });
          kids.push(el("p", { class: "civic-r04-row-btns", role: "group", "aria-label": tr("editor.seg.kind.label", "Что ремонтируют") },
            [kindBtn("road", tr("editor.seg.kind.road", "Проезжая часть")), kindBtn("foot", tr("editor.seg.kind.foot", "Тротуар"))]));
          const step = t.pending ? tr("editor.seg.pending", "Строим участок по улице…") : t.result
            ? tr("editor.seg.done", "Участок: {street}, {n} м. Можно нажать на другой конец — участок перестроится.", { street: t.result.street_ru || tr("editor.seg.noname", "улица без названия"), n: metres(t.result.length_m) })
            : t.start ? tr("editor.seg.start", "Начало: {street}. Теперь нажмите на конец участка.", { street: t.start.street_ru || t.start.label_ru })
              : tr("editor.seg.first", "Нажмите на начало участка.");
          kids.push(el("p", { class: "civic-r04-step", "data-fk": "seg-step", "aria-live": "polite" }, step));
          if (t.result && !t.result.same_street && t.result.names && t.result.names.length > 1)
            kids.push(el("p", { class: "civic-r04-warn" }, tr("editor.seg.many_streets", "Участок проходит по нескольким улицам: {list}. Проверьте концы.", { list: t.result.names.join(", ") })));
        } else {
          kids.push(el("p", { class: "civic-r04-step", "data-fk": "yard-step", "aria-live": "polite" }, t.pending ? tr("editor.yard.pending", "Ищем двор…") : t.yard ? tr("editor.yard.picked", "Выбран: {name}.", { name: t.yard.label_ru }) : tr("editor.yard.first", "Нажмите внутри двора.")));
        }
        if (t.problem) kids.push(el("p", { class: "civic-r04-err", role: "alert" }, t.problem));
        kids.push(el("p", { class: "civic-r04-row-btns" }, [
          btn("Готово", finishShape, "primary", "tool-done", { disabled: !(t.mode === "segment" ? t.result : t.yard) || t.pending }),
          t.mode === "segment" ? btn(tr("editor.seg.restart", "Начать заново"), () => { t.start = null; t.result = null; t.problem = null; t.seq++; t.pending = false; renderGeometry(); syncMap(); }, "", "tool-undo", { disabled: !t.start }) : null,
          btn("Отмена", () => { closeTool(); focusKey("tool-point"); }, "ghost", "tool-cancel")].filter(Boolean)));
      } else if (t) {
        const n = t.vertices.length;
        const need = t.mode === "area" ? 3 : 2;
        kids.push(el("p", { class: "civic-r04-tool", role: "status" }, [TOOL_TEXT[t.mode], t.mode === "point" ? "" : " Точек: " + n + "."]));
        if (t.problem) kids.push(el("p", { class: "civic-r04-err", role: "alert" }, t.problem));
        kids.push(el("p", { class: "civic-r04-row-btns" }, [
          t.mode !== "point" ? btn("Готово", finishShape, "primary", "tool-done", { disabled: n < need }) : null,
          t.mode !== "point" ? btn("Убрать последнюю точку", () => { t.vertices.pop(); t.problem = null; renderGeometry(); syncMap(); }, "", "tool-undo", { disabled: !n }) : null,
          btn("Отмена", () => { closeTool(); focusKey("tool-point"); }, "ghost", "tool-cancel")].filter(Boolean)));
      } else {
        kids.push(el("p", { class: "civic-r04-help" }, g ? "Отмечено: " + C.describeGeometry(g) + "." : "Выберите, как отметить место:"));
        kids.push(drawRow(true));
        kids.push(el("p", { class: "civic-r04-help" }, "Участок улицы строится по карте OSM: линия идёт точно по улице и не режет дома. Отметка не меняет маршруты симулятора."));
        const near = nearFor(g);
        if (near && !ro) kids.push(el("div", { class: "civic-r04-near", "data-fk": "near" }, [
          el("p", {}, tr("editor.near.title", "Рядом есть объект на карте OSM:")),
          el("ul", { class: "civic-r04-near-list" }, near.map((x, i) => el("li", {}, btn(x.label_ru + " — " + Math.round(x.distance_m) + " м", () => linkObject(x), "link", "near-" + i)))),
          el("p", { class: "civic-r04-muted" }, "Нажмите, чтобы поставить точку точно на этот объект. © участники OpenStreetMap.")]));
        if (S.linked && g && g.type === "Point" && S.linked.point[0] === g.coordinates[0] && S.linked.point[1] === g.coordinates[1])
          kids.push(el("p", { class: "civic-r04-ok", "data-fk": "linked" }, tr("editor.near.linked", "Точка стоит на объекте OSM: {name}.", { name: S.linked.label_ru })));
      }
      // 3) Manual coordinates for specialists (collapsed by default).
      const pt = g && g.type === "Point" ? g.coordinates : null;
      const lat = el("input", { type: "text", inputmode: "decimal", autocomplete: "off", id: P + "lat", "data-fk": "geometry", placeholder: "51.12825" });
      const lon = el("input", { type: "text", inputmode: "decimal", autocomplete: "off", id: P + "lon", "data-fk": "geo-lon", placeholder: "71.43042" });
      lat.value = S.coordDraft ? S.coordDraft.lat : pt ? String(pt[1]) : "";
      lon.value = S.coordDraft ? S.coordDraft.lon : pt ? String(pt[0]) : "";
      const draft = () => {
        const a = lat.value.trim(), b = lon.value.trim();
        const unchanged = pt ? a === String(pt[1]) && b === String(pt[0]) : !a && !b;
        S.coordDraft = unchanged ? null : { lat: lat.value, lon: lon.value };
        revalidate(); refreshDirty();
      };
      lat.addEventListener("input", draft); lon.addEventListener("input", draft);
      const err = el("p", { class: "civic-r04-err", id: P + "geo-err" }), warn = el("p", { class: "civic-r04-warn" });
      lat.setAttribute("aria-describedby", err.id); lon.setAttribute("aria-describedby", err.id);
      const apply = () => {
        const la = C.parseCoord(lat.value), lo = C.parseCoord(lon.value);
        if (!Number.isFinite(la) || !Number.isFinite(lo)) { S.server.geometry = "Введите числа: широта ≈ 51.1, долгота ≈ 71.4 (точка или запятая)."; paintErrors(); lat.focus(); return; }
        if (!C.inAstana(round6(lo), round6(la))) { S.server.geometry = "Точка вне Астаны: проверьте, не перепутаны ли широта (≈ 51) и долгота (≈ 71)."; paintErrors(); lat.focus(); return; }
        S.coordDraft = null;
        setGeometry({ type: "Point", coordinates: [round6(lo), round6(la)] });
        say("Точка задана координатами. Подтвердите расположение.");
        focusKey("geometry_confirmed");
      };
      for (const x of [lat, lon]) x.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); apply(); } });
      const manualOpen = !map || S.coordsOpen || (S.server.geometry && /числа/.test(S.server.geometry));
      const coords = el("details", { class: "civic-r04-coords-wrap", open: manualOpen ? true : null }, [
        el("summary", { "data-fk": "coords-open" }, "Ввести координаты точки вручную (для специалистов)"),
        el("fieldset", { class: "civic-r04-coords" }, [
          el("legend", {}, g && g.type !== "Point" ? "Заменить отметку одной точкой (WGS84)" : "Координаты точки (WGS84)"),
          el("div", { class: "civic-r04-grid" }, [
            el("div", { class: "civic-r04-field" }, [el("label", { for: lat.id }, "Широта"), lat]),
            el("div", { class: "civic-r04-field" }, [el("label", { for: lon.id }, "Долгота"), lon])]),
          el("p", { class: "civic-r04-row-btns" }, [btn("Применить координаты", apply, "", "geo-apply", { disabled: ro })])])]);
      coords.addEventListener("toggle", () => { S.coordsOpen = coords.open; });  // survives redraws of this block
      kids.push(coords, err, warn);
      F.geometry = { control: lat, err, warn };  // focus target refined below: never a control hidden in the collapsed panel
      if (g && g.type !== "Point") {
        kids.push(el("details", { class: "civic-r04-hint" }, [el("summary", {}, "Вершины (" + C.positionsOf(g).length + ")"),
          el("ol", { class: "civic-r04-vertices" }, C.positionsOf(g).map((p) => el("li", {}, p[1].toFixed(5) + ", " + p[0].toFixed(5))))]));
      }
      if (g) {
        const cb = el("input", { type: "checkbox", id: P + "f-geometry_confirmed", "data-fk": "geometry_confirmed", checked: S.form.geometry_confirmed, disabled: ro });
        cb.addEventListener("change", () => { S.form.geometry_confirmed = cb.checked; delete S.server.geometry; revalidate(); refreshDirty(); });
        kids.push(el("label", { class: "civic-r04-check civic-r04-confirm", for: cb.id }, [cb, " Расположение проверено: отметка соответствует источнику или осмотру"]));
        if (!coords.open) F.geometry.control = cb;
      } else if (!coords.open) {
        const first = kids.map((k) => k.querySelector && k.querySelector('[data-fk="tool-point"]')).find(Boolean);
        if (first && !first.disabled) F.geometry.control = first;
      }
      rebuild(V.geom, kids);
      paintErrors();
    }
    // ----- approximate street search (public streets.json of R07; read-only, loaded on first use) -----
    function streetSearch() {
      const q = el("input", { type: "search", id: P + "street-q", autocomplete: "off", "data-fk": "street-q", placeholder: "например, Кенесары или Абылай хан",
        "aria-describedby": P + "street-help", value: S.streetQ || "" });
      q.value = S.streetQ || "";
      const list = el("ul", { class: "civic-r04-street-list", id: P + "street-list", "aria-label": "Найденные улицы" });
      const note = el("div", { class: "civic-r04-street-note", "data-fk": "street-note", role: "status" });
      const paint = () => {
        const st = STREETS.state;
        if (st === "unavailable") { list.replaceChildren(); note.replaceChildren(el("p", { class: "civic-r04-muted" }, "Поиск улиц недоступен на этом сервере — отметьте место на карте или введите координаты.")); return; }
        if (st === "loading") { list.replaceChildren(); note.replaceChildren(el("p", { class: "civic-r04-muted" }, "Загружаем названия улиц…")); return; }
        const found = st === "ok" ? C.searchStreets(STREETS.list, q.value, 8) : [];
        list.replaceChildren(...found.map((x, i) => el("li", {}, btn(x.label || x.name, () => pickStreet(x), "link", "street-" + i))));
        if (S.streetPick) note.replaceChildren(
          el("p", {}, "«" + (S.streetPick.label || S.streetPick.name) + "»: на карте показан прямоугольник, охватывающий улицу целиком. Это не адрес и не точка работ — щёлкните по карте в точном месте («Точка» или «Линия»)."),
          el("p", { class: "civic-r04-muted" }, "Названия улиц: © участники OpenStreetMap, ODbL-1.0" + (STREETS.snapshot ? "; снимок " + C.fmtDate(String(STREETS.snapshot).slice(0, 10)) : "") + "."));
        else note.replaceChildren(...(q.value.trim().length >= 2 && st === "ok" && !found.length ? [el("p", { class: "civic-r04-muted" }, "Улица не найдена в снимке OSM. Отметьте место на карте.")] : []));
      };
      q.addEventListener("focus", () => { if (STREETS.state === "idle") loadStreets().then(() => { if (S.alive) paint(); }); });
      q.addEventListener("input", () => {
        S.streetQ = q.value;
        if (S.streetPick) { S.streetPick = null; syncMap(); }  // a new search replaces the previous street frame
        if (STREETS.state === "idle") loadStreets().then(() => { if (S.alive) paint(); });
        paint();
      });
      paint();
      return el("div", { class: "civic-r04-street" }, [
        el("label", { for: q.id }, "Найти улицу (приблизительно)"), q,
        el("p", { class: "civic-r04-help", id: P + "street-help" }, "Покажет улицу на карте; точное место отмечаете вы. Адресов и номеров домов в этом поиске нет."),
        list, note]);
    }
    function loadStreets() { return loadStreetsFrom(streetsUrl); }
    function pickStreet(x) {
      S.streetPick = { name: x.name, label: x.label, bbox: x.bbox.slice() };
      syncMap();
      if (map) {
        try { map.fitBounds([[x.bbox[0], x.bbox[1]], [x.bbox[2], x.bbox[3]]], { padding: 60, maxZoom: 17, duration: reduced() ? 0 : 600 }); } catch (e) { /* camera errors are not fatal */ }
      }
      renderGeometry();
      say("Улица показана на карте приблизительно. Отметьте точное место щелчком по карте.");
      focusKey("tool-point");
    }
    function setGeometry(g) {
      S.coordDraft = null;  // a map click or «Удалить отметку» replaces whatever was typed
      S.form.geometry = g;
      S.form.geometry_confirmed = false;
      if (g && placeNow() === "unknown") S.form.place = "approximate";
      delete S.server.geometry; delete S.server.place;
      renderGeometry(); syncMap(); revalidate(); refreshDirty();
    }
    function toolGeometry() {
      const t = S.tool, v = t.vertices;
      if (t.mode === "segment") return t.result ? t.result.geometry : t.start ? { type: "Point", coordinates: t.start.point } : null;
      if (t.mode === "yard") return t.yard ? t.yard.geometry : null;
      if (!v.length) return null;
      if (t.mode === "edit") return C.geometryFromVertices(t.type, v);
      if (t.mode === "point" || v.length === 1) return { type: "Point", coordinates: v[v.length - 1] };
      if (t.mode === "area" && v.length >= 3) return C.polygonFromVertices(v);
      return { type: "LineString", coordinates: v.slice() };
    }
    function geomData() {
      const g = S.tool ? toolGeometry() : S.form && placeNow() !== "unknown" ? S.form.geometry : null;
      const features = [];
      if (g) {
        features.push({ type: "Feature", geometry: g, properties: {} });
        // У линии по улице десятки вершин OSM — показываем только начало и конец участка.
        const corners = S.tool && S.tool.mode === "edit" ? S.tool.vertices : g.type === "LineString" ? [g.coordinates[0], g.coordinates[g.coordinates.length - 1]]
          : g.type === "Polygon" && !(S.tool && S.tool.mode === "yard") ? C.positionsOf(g) : [];
        corners.forEach((p, i) => features.push({ type: "Feature", geometry: { type: "Point", coordinates: p },
          properties: { vertex: true, selected: !!(S.tool && S.tool.mode === "edit" && S.tool.selected === i) } }));
      }
      return { type: "FeatureCollection", features };
    }
    function streetData() {
      const b = S.streetPick && S.streetPick.bbox;
      return { type: "FeatureCollection", features: b ? [{ type: "Feature", properties: {},
        geometry: { type: "Polygon", coordinates: [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]] } }] : [] };
    }
    function syncMap() {
      if (!map || !S.mapOn) return;
      try {
        const ss = map.getSource(SRC_STREET);
        if (ss) ss.setData(streetData());
        else {
          map.addSource(SRC_STREET, { type: "geojson", data: streetData() });
          map.addLayer({ id: LAYER_STREET, type: "line", source: SRC_STREET, paint: { "line-color": "#1f5fa8", "line-width": 2, "line-dasharray": [2, 2], "line-opacity": 0.85 } });
        }
      } catch (e) { /* style not ready */ }
      try {
        const src = map.getSource(SRC);
        if (src) { src.setData(geomData()); return; }
        map.addSource(SRC, { type: "geojson", data: geomData() });
        map.addLayer({ id: LAYERS[2], type: "fill", source: SRC, filter: ["==", ["geometry-type"], "Polygon"],
          paint: { "fill-color": "#c17238", "fill-opacity": 0.18 } });
        map.addLayer({ id: LAYERS[0], type: "line", source: SRC, filter: ["in", ["geometry-type"], ["literal", ["LineString", "Polygon"]]],
          paint: { "line-color": "#c17238", "line-width": 4, "line-opacity": 0.9 } });
        map.addLayer({ id: LAYERS[1], type: "circle", source: SRC, filter: ["==", ["geometry-type"], "Point"],
          paint: { "circle-radius": ["case", ["==", ["get", "selected"], true], 9, ["has", "vertex"], 5, 7],
            "circle-color": ["case", ["==", ["get", "selected"], true], "#1f5fa8", "#c17238"], "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
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
      stopMapWait();
      if (!map || !S.mapOn) return;
      S.mapOn = false;
      offMap("styledata", syncMap);
      try {
        for (const l of LAYERS.concat(LAYER_STREET)) if (map.getLayer(l)) map.removeLayer(l);
        if (map.getSource(SRC)) map.removeSource(SRC);
        if (map.getSource(SRC_STREET)) map.removeSource(SRC_STREET);
      } catch (e) { /* map already removed by its owner */ }
    }
    function startTool(mode) {
      if (!resolveMap() && mapGetter) {
        say("Карта ещё не готова. Попробуйте через несколько секунд или введите координаты точки вручную.", true);
        mapTries = 0; waitForMap();
        return;
      }
      if (!map || S.busy || !C.allowedActions(S.item, S.session).edit) return;
      closeTool();
      const prevPlace = S.form.place;
      if (placeNow() === "unknown") S.form.place = "approximate";
      S.tool = { mode, vertices: [], problem: null, dblZoom: false, prevPlace, seq: 0, start: null, result: null, yard: null, pending: false };
      if (mode === "edit") Object.assign(S.tool, { type: S.form.geometry.type, vertices: C.editableVertices(S.form.geometry), selected: null, undo: [] });
      // A double click while drawing must not zoom the map (and must not add a zero-length segment).
      try { if (map.doubleClickZoom && map.doubleClickZoom.isEnabled()) { map.doubleClickZoom.disable(); S.tool.dblZoom = true; } } catch (e) { /* optional API */ }
      try { S.cursor = map.getCanvas().style.cursor; map.getCanvas().style.cursor = "crosshair"; } catch (e) { S.cursor = ""; }
      onMap("click", onMapClick);
      onDom(document, "keydown", onToolKey);
      announceTool(true, mode);
      renderGeometry(); syncMap();
      focusKey("tool-cancel");
      say(toolText(mode));
    }
    function onMapClick(e) {
      if (!S.tool || !e || !e.lngLat) return;
      if (S.tool.mode === "edit") { editClick(e); return; }
      const p = [round6(e.lngLat.lng), round6(e.lngLat.lat)];
      if (!C.inAstana(p[0], p[1])) { S.tool.problem = "Эта точка за пределами Астаны — щёлкните внутри города."; renderGeometry(); say(S.tool.problem, true); return; }
      if (S.tool.mode === "point") {
        closeTool(true, true);
        setGeometry({ type: "Point", coordinates: p });
        say("Точка поставлена: " + p[1].toFixed(5) + ", " + p[0].toFixed(5) + ". Подтвердите расположение.");
        focusKey("geometry_confirmed");
        suggestObjects(p);
        return;
      }
      if (S.tool.mode === "segment") { segmentClick(p); return; }
      if (S.tool.mode === "yard") { yardClick(p); return; }
      const last = S.tool.vertices[S.tool.vertices.length - 1];
      if (last && last[0] === p[0] && last[1] === p[1]) return;  // a double click adds no zero-length segment
      S.tool.vertices.push(p);
      S.tool.problem = null;
      renderGeometry(); syncMap();
      say("Точек: " + S.tool.vertices.length + ".");
    }
    // ----- R12: участок улицы двумя нажатиями, двор выбором полигона, точка -> объект OSM -----
    // Каждый ответ сервера применяется, только если инструмент тот же и после запроса не было нового нажатия.
    async function segmentClick(p) {
      const t = S.tool, my = ++t.seq;
      t.problem = null; t.pending = true; renderGeometry();
      try {
        if (!t.start) {
          const r = await geoApi.snap(p, S.segKind);
          if (S.tool !== t || t.seq !== my) return;
          t.start = r;
          say("Начало участка: " + (r.street_ru || r.label_ru) + ". Нажмите на конец участка.");
        } else {
          const r = await geoApi.segment(t.start.point, p, S.segKind);
          if (S.tool !== t || t.seq !== my) return;
          t.result = r;
          say("Участок построен по улице: " + (r.street_ru || "без названия") + ", " + metres(r.length_m) + " м. «Готово» — сохранить.");
        }
      } catch (err) {
        if (S.tool !== t || t.seq !== my) return;
        t.problem = geoErrorText(err);
        say(t.problem, true);
      } finally {
        if (S.tool === t && t.seq === my) { t.pending = false; if (S.alive) { renderGeometry(); syncMap(); if (t.result) focusKey("tool-done"); } }
      }
    }
    async function yardClick(p) {
      const t = S.tool, my = ++t.seq;
      t.problem = null; t.pending = true; renderGeometry();
      try {
        const r = await geoApi.yard(p);
        if (S.tool !== t || t.seq !== my) return;
        if (r && r.yard) { t.yard = r.yard; say("Выбран двор: " + r.yard.label_ru + ". «Готово» — сохранить."); }
        else {
          t.yard = null;
          t.problem = r && r.reason === "no_yards_data"
            ? tr("editor.yard.no_data", "Дворов на карте пока нет (данные OSM ещё не загружены). Отметьте площадь по углам.")
            : tr("editor.yard.none", "Здесь нет двора на карте OSM. Нажмите внутри жилого двора или отметьте площадь по углам.");
          say(t.problem, true);
        }
      } catch (err) {
        if (S.tool !== t || t.seq !== my) return;
        t.problem = geoErrorText(err); say(t.problem, true);
      } finally {
        if (S.tool === t && t.seq === my) { t.pending = false; if (S.alive) { renderGeometry(); syncMap(); if (t.yard) focusKey("tool-done"); } }
      }
    }
    // После точки — предложение поставить её точно на объект OSM рядом (остановка, площадка, парк).
    async function suggestObjects(p) {
      if (!geoApi || typeof geoApi.near !== "function") return;
      const ask = (S.near = { at: p, items: null });
      try {
        const r = await geoApi.near(p);
        if (S.near !== ask || !S.alive) return;
        ask.items = Array.isArray(r && r.objects) ? r.objects.filter((x) => x && Array.isArray(x.point) && typeof x.label_ru === "string") : [];
        if (ask.items.length && S.view === "edit") renderGeometry();
      } catch (e) { if (S.near === ask) S.near = null; }  // без подсказки точка остаётся как есть
    }
    function nearFor(g) {
      if (!g || g.type !== "Point" || !S.near || !S.near.items || !S.near.items.length) return null;
      const [x, y] = S.near.at;
      return g.coordinates[0] === x && g.coordinates[1] === y ? S.near.items : null;
    }
    function linkObject(x) {
      S.near = null;
      S.linked = { label_ru: x.label_ru, point: [round6(x.point[0]), round6(x.point[1])] };
      setGeometry({ type: "Point", coordinates: S.linked.point });
      say("Точка поставлена на объект: " + x.label_ru + ". Подтвердите расположение.");
      focusKey("geometry_confirmed");
    }
    function finishShape() {
      const t = S.tool;
      if (!t || t.mode === "point") return;
      if (t.mode === "segment" || t.mode === "yard") {
        const g = t.mode === "segment" ? t.result && t.result.geometry : t.yard && t.yard.geometry;
        if (!g || t.pending) return;
        const what = t.mode === "segment" ? "участок улицы " + (t.result.street_ru || "без названия") + ", " + metres(t.result.length_m) + " м" : t.yard.label_ru;
        closeTool(true);
        setGeometry({ type: g.type, coordinates: JSON.parse(JSON.stringify(g.coordinates)) });
        say("Отмечено: " + what + ". Подтвердите расположение.");
        focusKey("geometry_confirmed");
        return;
      }
      const v = t.vertices.slice();
      const g = t.mode === "area" ? C.polygonFromVertices(v) : { type: "LineString", coordinates: v };
      const problem = C.geometryProblem(g);
      if (problem) { t.problem = problem + " Уберите лишнюю точку или нажмите «Отмена»."; renderGeometry(); focusKey("tool-undo"); say(t.problem, true); return; }
      closeTool(true);
      setGeometry(g);
      say("Отмечено: " + C.describeGeometry(g) + ". Подтвердите расположение.");
      focusKey("geometry_confirmed");
    }
    // ----- vertex editing of the record's own line/area: select -> move (click, arrows) -> undo/delete -> validate -----
    function editClick(e) {
      const t = S.tool;
      let hit = null, best = 15;  // px
      try {
        t.vertices.forEach((v, i) => { const q = map.project(v), d = Math.hypot(q.x - e.point.x, q.y - e.point.y); if (d < best) { best = d; hit = i; } });
      } catch (x) { hit = null; }
      if (hit !== null) { t.selected = hit; t.problem = null; renderGeometry(); syncMap(); say("Выбрана вершина " + (hit + 1) + ". Щёлкните, куда её перенести."); return; }
      if (t.selected === null) { t.problem = "Сначала выберите вершину: щёлкните по ней на карте или в списке."; renderGeometry(); return; }
      moveVertex(t.selected, [round6(e.lngLat.lng), round6(e.lngLat.lat)]);
    }
    function moveVertex(i, p) {
      const t = S.tool;
      if (!C.inAstana(p[0], p[1])) { t.problem = "Эта точка за пределами Астаны — вершину туда перенести нельзя."; renderGeometry(); say(t.problem, true); return; }
      t.undo.push(t.vertices.map((v) => v.slice()));
      t.vertices[i] = p;
      t.problem = C.geometryProblem(toolGeometry());
      renderGeometry(); syncMap();
      say("Вершина " + (i + 1) + " перенесена." + (t.problem ? " " + t.problem : ""), !!t.problem);
    }
    function deleteVertex() {
      const t = S.tool, min = t.type === "Polygon" ? 3 : 2;
      if (t.selected === null || t.vertices.length <= min) return;
      t.undo.push(t.vertices.map((v) => v.slice()));
      t.vertices.splice(t.selected, 1);
      t.selected = null;
      t.problem = C.geometryProblem(toolGeometry());
      renderGeometry(); syncMap(); say("Вершина удалена.");
    }
    function undoEdit() {
      const t = S.tool;
      if (!t.undo.length) return;
      t.vertices = t.undo.pop();
      t.problem = C.geometryProblem(toolGeometry());
      renderGeometry(); syncMap(); say("Шаг отменён.");
    }
    function finishEdit() {
      const t = S.tool, g = toolGeometry(), problem = C.geometryProblem(g);
      if (problem) { t.problem = problem + " Исправьте вершины, отмените шаг или нажмите «Отмена»."; renderGeometry(); say(t.problem, true); return; }
      closeTool(true);
      setGeometry(g);  // a changed mark needs a fresh «Расположение проверено»
      say("Вершины изменены: " + C.describeGeometry(g) + ". Подтвердите расположение.");
      focusKey("geometry_confirmed");
    }
    function onToolKey(e) {
      if (!S.tool) return;
      const typing = e.target && /^(TEXTAREA|INPUT|SELECT)$/.test(e.target.tagName);
      if (S.tool.mode === "edit") {
        const t = S.tool, step = { ArrowUp: [0, 1], ArrowDown: [0, -1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] }[e.key];
        if (e.key === "Escape") { e.preventDefault(); closeTool(); focusKey("tool-edit"); }
        else if (typing) return;
        else if (e.key === "Enter") { e.preventDefault(); finishEdit(); }
        else if (step && t.selected !== null) { e.preventDefault(); const v = t.vertices[t.selected]; moveVertex(t.selected, [round6(v[0] + step[0] * C.NUDGE.lon), round6(v[1] + step[1] * C.NUDGE.lat)]); }
        else if ((e.key === "Delete" || e.key === "Backspace") && t.selected !== null) { e.preventDefault(); deleteVertex(); }
        else if (e.key === "z" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); undoEdit(); }
        return;
      }
      if (e.key === "Escape") { e.preventDefault(); closeTool(); focusKey("tool-point"); }
      else if (e.key === "Enter" && S.tool.mode !== "point" && !(e.target && /^(TEXTAREA|INPUT|SELECT)$/.test(e.target.tagName))) { e.preventDefault(); finishShape(); }
      else if ((S.tool.mode === "segment" || S.tool.mode === "yard")) return;
      else if ((e.key === "Backspace" || (e.key === "z" && (e.ctrlKey || e.metaKey))) && S.tool.vertices.length && !(e.target && /^(TEXTAREA|INPUT|SELECT)$/.test(e.target.tagName))) {
        e.preventDefault(); S.tool.vertices.pop(); S.tool.problem = null; renderGeometry(); syncMap();
      }
    }
    // Every start is followed by exactly one {active:false}. When a map click ends the tool, the release is announced
    // after that click has been handled by all listeners (a neighbour's click handler still sees "drawing").
    let releaseTimer = null;
    function announceTool(active, mode) {
      if (releaseTimer) { clearTimeout(releaseTimer); releaseTimer = null; fireTool(false); }
      if (active) { setActiveTool(mode); fireTool(true, mode); }
    }
    function fireTool(active, mode) {
      if (!active) setActiveTool(null);
      const ev = () => new CustomEvent("civic-editor:tool", { bubbles: true, detail: active ? { active: true, mode } : { active: false } });
      shell.dispatchEvent(ev());
      if (!shell.isConnected) { try { document.dispatchEvent(ev()); } catch (e) { /* no document */ } }  // detached root: still tell the page
    }
    function releaseTool(afterEvent) {
      if (!afterEvent) { if (releaseTimer) { clearTimeout(releaseTimer); releaseTimer = null; } fireTool(false); return; }
      if (releaseTimer) return;
      releaseTimer = setTimeout(() => { releaseTimer = null; fireTool(false); }, 0);  // not in `timers`: destroy flushes it itself
    }
    function closeTool(quiet, afterMapClick) {
      if (!S.tool) return;
      const t = S.tool;
      if (t.dblZoom) { try { map.doubleClickZoom.enable(); } catch (e) { /* map gone */ } }
      S.tool = null;
      // cancelled without a result: the place choice goes back to what it was before the tool started
      if (!quiet && S.form && t.prevPlace !== undefined && !S.form.geometry) S.form.place = t.prevPlace;
      offMap("click", onMapClick);
      offDom(document, "keydown", onToolKey);
      try { if (map) map.getCanvas().style.cursor = S.cursor || ""; } catch (e) { /* map gone */ }
      releaseTool(!!afterMapClick && S.alive);
      if (!quiet && S.view === "edit" && V.geom && S.form) { renderGeometry(); syncMap(); revalidate(); refreshDirty(); }
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
          // an imported date-time (retrieved_at) is shown as its date and kept exactly until the user picks another date
          const stamped = x.type === "date" && typeof s[f] === "string" && s[f].length > 10 && C.isIsoTimestamp(s[f]);
          x.value = stamped ? s[f].slice(0, 10) : s[f] || "";
          const upd = () => { if (stamped && x.value === s[f].slice(0, 10)) return; s[f] = x.value; changed(k(f)); };
          x.addEventListener("input", upd); x.addEventListener("change", upd);
          x.addEventListener("blur", () => touch(k(f)));
          return x;
        };
        const sel = el("select", {}, Object.entries(C.ACCESS).map(([v, l]) => el("option", { value: v }, l)));
        const boxes = Object.entries(C.SOURCE_FIELDS).map(([v, l]) => {
          const cb = el("input", { type: "checkbox", value: v, "data-fk": k("fields") + "." + v, checked: (s.fields || []).includes(v) });
          cb.addEventListener("change", () => {
            const others = (s.fields || []).filter((f) => !Object.prototype.hasOwnProperty.call(C.SOURCE_FIELDS, f));  // e.g. "title", "schedule.current_planned_end"
            s.fields = Object.keys(C.SOURCE_FIELDS).filter((f) => (f === v ? cb.checked : (s.fields || []).includes(f))).concat(others);
            changed(k("fields"));
          });
          return el("label", { class: "civic-r04-check" }, [cb, " " + l]);
        });
        const extra = (s.fields || []).filter((f) => !Object.prototype.hasOwnProperty.call(C.SOURCE_FIELDS, f));
        if (extra.length) boxes.push(el("p", { class: "civic-r04-help", "data-fk": k("fields") + ".extra" },
          "Также подтверждает (из импорта, сохраняется как есть): " + extra.map((f) => C.PATH_LABEL[f] || f).join(", ") + "."));
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
      const addBtn = btn("+ Добавить источник", addSource, "", "src-add");
      const se = el("p", { class: "civic-r04-err", id: P + "sources-err", role: "alert" }), sw = el("p", { class: "civic-r04-warn" });
      addBtn.setAttribute("aria-describedby", se.id);
      F.sources = { control: addBtn, err: se, warn: sw };  // R02 reports "source_refs" (e.g. no source for publication) here
      kids.push(se, sw, el("p", { class: "civic-r04-row-btns" }, [addBtn]));
      rebuild(V.sources, kids);
      renderBudgetSourceOptions();
      paintErrors();
    }
    function addSource() {
      delete S.server.sources;
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
      // a copy made on an older revision: show what changed on the server meanwhile before anything is restored
      const newer = r.revision && S.item && r.revision !== S.item.revision;
      const rb = newer ? C.rebaseForm(r.base ? C.formFromItem(r.base) : C.emptyForm(), Object.assign(C.emptyForm(), r.form), S.saved) : null;
      V.restore.replaceChildren(el("div", { class: "civic-r04-msg civic-r04-msg-warn", role: "group", "aria-label": "Несохранённые правки" }, [
        el("p", {}, "В этой вкладке есть несохранённые правки этой записи от " + C.fmtDateTime(r.at) + (r.revision ? " (на основе ред. " + r.revision + ")" : "") + "."),
        el("p", { class: "civic-r04-help" }, "Это локальная копия в браузере, не запись на сервере: жители и другие редакторы её не видят, пока вы не сохраните."),
        newer ? el("p", {}, "С тех пор запись изменилась на сервере (сейчас ред. " + S.item.revision + "). Сравните перед восстановлением"
          + (rb.conflicts.length ? "; в полях, изменённых обеими сторонами, останется ваше значение." : ".")) : null,
        newer ? compareTable(r.base ? C.formFromItem(r.base) : C.emptyForm(), S.saved, Object.assign(C.emptyForm(), r.form), rb, [r.revision, S.item.revision, "Ваша копия"]) : null,
        el("p", { class: "civic-r04-row-btns" }, [btn(newer ? "Восстановить мои правки на новой версии" : "Восстановить правки", restoreDraft, "primary", "restore"),
          btn("Удалить из памяти", () => { dropRecovery(S.item ? S.item.id : "new"); S.restore = null; renderRestore(); focusKey("edit-h"); }, "ghost", "restore-drop")])].filter(Boolean)));
    }
    function restoreDraft() {
      const r = S.restore;
      if (!r) return;
      closeTool();
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
    // ----- changed source (R02 import candidates): compare, then accept or dismiss — never applied automatically -----
    const pendingCandidates = (it) => (it && it.staff && Number.isInteger(it.staff.pending_import_candidates) ? it.staff.pending_import_candidates : 0);
    let candRoute = null;  // false after a 404: this server does not route /import-candidates (R01 gateway at 56538a3)
    async function loadCandidates() {
      const it = S.item;
      if (!it) return;
      if (candRoute === false) { S.cands = { state: "unavailable", items: [] }; renderSrcReview(); return; }
      const my = navSeq;
      S.cands = { state: "loading", items: [] };
      renderSrcReview();
      try {
        const d = await call("GET", "/staff/objects/" + enc(it.id) + "/import-candidates");
        if (my !== navSeq || !S.item || S.item.id !== it.id) return;
        candRoute = true;
        S.cands = { state: "ok", items: (d && Array.isArray(d.items) ? d.items : []).filter((c) => c && !c.resolved_at) };
      } catch (e) {
        if (e === STALE || my !== navSeq) return;
        const n = C.normalizeError(e);
        if (n.status === 404 || n.status === 405) { candRoute = false; S.cands = { state: "unavailable", items: [] }; }
        else S.cands = { state: "error", items: [], text: n.text };
      }
      renderSrcReview();
    }
    function renderSrcReview() {
      if (!V.srcreview) return;
      const it = S.item, c = S.cands || { state: "idle" }, n = pendingCandidates(it);
      if (!it || (c.state === "idle" && !n)) { V.srcreview.replaceChildren(); return; }
      const box = (cls, kids) => el("div", { class: "civic-r04-msg civic-r04-msg-" + cls + " civic-r04-srcreview", role: "group", "aria-label": "Изменения источника", "data-fk": "srcreview" }, kids);
      if (c.state === "loading" || c.state === "idle") { V.srcreview.replaceChildren(box("info", [el("p", {}, "Источник изменился — загружаем сравнение…")])); return; }
      if (c.state === "unavailable") {
        V.srcreview.replaceChildren(box("warn", [
          el("p", {}, "По данным сервера есть " + n + " непросмотренн" + (n === 1 ? "ое изменение" : "ых изменения") + " источника для этой записи."),
          el("p", { class: "civic-r04-help" }, "Посмотреть и принять их здесь нельзя: этот сервер не отдаёт сравнение (маршрут /import-candidates не подключён). Запись не меняется, пока изменения не приняты.")]));
        return;
      }
      if (c.state === "error") {
        V.srcreview.replaceChildren(box("warn", [el("p", {}, "Не удалось загрузить изменения источника: " + c.text),
          el("p", { class: "civic-r04-row-btns" }, [btn("Повторить", loadCandidates, "", "srcreview-retry")])]));
        return;
      }
      if (!c.items.length) { V.srcreview.replaceChildren(); return; }
      const dirty = isDirty();
      V.srcreview.replaceChildren(...c.items.map((cand, i) => {
        const rows = C.candidateRows(cand);
        const head = el("p", {}, [el("b", {}, "Источник изменился"), " · «" + (cand.source || "источник") + "»" + (cand.external_id ? ", " + cand.external_id : "")
          + " · получено " + C.fmtDateTime(cand.created_at) + "."]);
        const rev = el("p", { class: "civic-r04-help" }, "Сравнение с текущей версией записи (ред. " + it.revision + ", включая несохранённые для жителей правки). Ничего не применяется без вашего решения; принятие заменяет поля записи значениями источника целиком.");
        const locked = cand.original_planned_end_locked ? el("p", { class: "civic-r04-help" }, "Первоначальный срок зафиксирован при первой публикации и не меняется: источник может изменить только актуальный срок.") : null;
        const table = rows.length ? el("table", { class: "civic-r04-difftable civic-r04-candtable" }, [
          el("thead", {}, el("tr", {}, [el("th", { scope: "col" }, "Поле"), el("th", { scope: "col" }, "Сейчас (ред. " + it.revision + ")"),
            el("th", { scope: "col" }, "По источнику"), el("th", { scope: "col" }, "Что подтверждает")])),
          el("tbody", {}, rows.map((r) => el("tr", { class: r.path === "schedule.current_planned_end" ? "civic-r04-shift" : null }, [
            el("th", { scope: "row" }, r.label), el("td", {}, C.fmtValue(r.path, r.before)), el("td", {}, C.fmtValue(r.path, r.after)),
            el("td", {}, r.by.length ? r.by.map((x) => C.describeRef(x)).join("; ") : r.path === "source_refs" ? "список источников" : "источник не указал это поле")])))])
          : el("p", {}, "Источник совпадает с записью — изменений нет.");
        return el("div", { class: "civic-r04-msg civic-r04-msg-warn civic-r04-srcreview", role: "group", "aria-label": "Изменения источника " + (i + 1), "data-fk": i === 0 ? "srcreview" : "srcreview-" + i }, [
          head, rev, locked, table,
          dirty ? el("p", { class: "civic-r04-help" }, "Сначала сохраните или отмените свои правки: принятие источника заменит поля записи.") : null,
          el("p", { class: "civic-r04-row-btns" }, [
            rows.length ? btn("Принять изменения источника…", () => askConfirm("apply", cand), "primary", "cand-apply-" + i, { disabled: !!S.busy || dirty || !!S.confirm }) : null,
            btn("Отклонить…", () => askConfirm("dismiss", cand), "ghost", "cand-dismiss-" + i, { disabled: !!S.busy || !!S.confirm })].filter(Boolean)),
        ].filter(Boolean));
      }));
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
        c.base ? compareTable(c.base, c.latestForm, S.form, c.rebase, [S.item ? S.item.revision : "?", L.revision]) : null,
        el("p", { class: "civic-r04-help" }, "Ничего не перезаписано автоматически: ваш ввод остаётся в форме, пока вы не выберете вариант."),
        L.publication !== (S.item && S.item.publication) ? el("p", {}, "Состояние публикации теперь: " + (C.PUBLICATION[L.publication] || L.publication) + ".") : null,
        el("p", { class: "civic-r04-row-btns" }, [
          c.rebase.kept.length ? btn("Перенести мои правки на новую версию", applyRebase, "primary", "rebase") : null,
          c.dropAsk ? null : btn(c.rebase.kept.length ? "Отказаться от моих правок…" : "Открыть новую версию", () => {
            if (c.base) c.rebase = C.rebaseForm(c.base, S.form, c.latestForm);  // typed after the conflict appeared counts too
            if (c.rebase.kept.length) { c.dropAsk = true; renderConflict(); focusKey("rebase-drop-yes"); return; }
            S.conflict = null; dropRecovery(L.id); openEditor(L, c.history); setNotice("info", "Открыта актуальная версия ред. " + L.revision + ".");
          }, "ghost", "rebase-drop"),
        ].filter(Boolean)),
        c.dropAsk ? el("p", { class: "civic-r04-row-btns" }, [
          el("span", {}, "Ваши правки (" + names(c.rebase.kept) + ") будут потеряны. Точно?"),
          btn("Да, открыть версию сервера", () => { S.conflict = null; dropRecovery(L.id); openEditor(L, c.history); setNotice("info", "Ваши правки отброшены. Открыта актуальная версия ред. " + L.revision + "."); }, "danger", "rebase-drop-yes"),
          btn("Нет, вернуться", () => { c.dropAsk = false; renderConflict(); focusKey("rebase"); }, "ghost", "rebase-drop-no")]) : null,
      ].filter(Boolean)));
    }
    // Per-field comparison: what it was when the form was opened, what the server has now, what the user typed.
    function compareTable(base, server, mine, rb, revs) {
      const keys = [...new Set(rb.conflicts.concat(rb.theirs, rb.kept))].filter((k) => k !== "geometry_confirmed");
      if (!keys.length) return null;
      return el("table", { class: "civic-r04-difftable civic-r04-cmptable", "data-fk": "compare" }, [
        el("thead", {}, el("tr", {}, [el("th", { scope: "col" }, "Поле"), el("th", { scope: "col" }, "Было (ред. " + revs[0] + ")"),
          el("th", { scope: "col" }, "На сервере (ред. " + revs[1] + ")"), el("th", { scope: "col" }, revs[2] || "Ваша правка")])),
        el("tbody", {}, keys.map((k) => el("tr", { class: rb.conflicts.includes(k) ? "civic-r04-both" : null }, [
          el("th", { scope: "row" }, (FORM_LABEL[k] || k) + (rb.conflicts.includes(k) ? " — изменено обеими сторонами" : "")),
          el("td", {}, C.fmtFormValue(k, base[k])),
          el("td", {}, rb.theirs.includes(k) || rb.conflicts.includes(k) ? C.fmtFormValue(k, server[k]) : "без изменений"),
          el("td", {}, rb.kept.includes(k) ? C.fmtFormValue(k, mine[k]) : "без изменений")])))]);
    }
    function applyRebase() {
      const c = S.conflict;
      if (!c) return;
      closeTool();
      if (c.base) c.rebase = C.rebaseForm(c.base, S.form, c.latestForm);  // includes what was typed while the panel was open
      S.conflict = null;
      S.item = c.latest;
      S.history = c.history || [];
      S.saved = C.formFromItem(c.latest);
      renderButtons();
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

    // The resident card rows come from residentView(): R03's own CivicMapCore rules when the page has it (the app),
    // the same rules in editor-core otherwise. Only the layout is the editor's.
    function publicCard(dto, note, pending) {
      const v = C.residentView(dto, window.CivicMapCore || null);
      if (!v) return el("p", { class: "civic-r04-err" }, "Карточку построить не удалось.");
      const row = (k, t) => [el("dt", {}, k), el("dd", {}, t === C.NO_DATA ? el("span", { class: "civic-r04-nodata" }, t) : t)];
      const sources = v.sources.map((s) => el("li", {}, [
        s.href ? el("a", { href: s.href, target: "_blank", rel: "noopener noreferrer nofollow" }, [s.name, el("span", { class: "civic-r04-sr" }, " (откроется в новой вкладке)")]) : s.name,
        s.published ? " · " + s.published : "", s.access ? " · " + s.access : ""]));
      return el("article", { class: "civic-r04-card", "aria-label": "Карточка для жителей", "data-engine": v.engine }, [
        note ? el("p", { class: "civic-r04-card-note" }, note) : null,
        v.banner ? el("p", { class: "civic-r04-card-banner" + (v.banner.demo ? " civic-r04-card-demo" : ""), role: "note" }, v.banner.text) : null,
        el("p", { class: "civic-r04-badges" }, [badge(v.kind, "kind")]),
        el("h4", {}, v.title),
        v.description ? el("p", {}, v.description) : null,
        el("dl", {}, [].concat(...v.rows.map(([k, t]) => row(k, t)))),
        v.evidenceNotes ? el("p", { class: "civic-r04-muted" }, "Примечание: " + v.evidenceNotes) : null,
        el("p", {}, el("b", {}, "Источники")),
        sources.length ? el("ul", {}, sources) : el("p", { class: "civic-r04-muted" }, v.noSources),
        el("p", { class: "civic-r04-muted" }, pending || !dto.updated_at ? "Дату обновления и редакцию назначит сервер при сохранении."
          : "Запись обновлена: " + C.fmtDateTime(dto.updated_at) + " · ред. " + dto.revision),
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
      kids.push(publicCard(dto, "Внутренние заметки и служебные поля сюда не попадают.", isDirty() || !S.item));
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
          ...(x.action === "create" || x.action === "import_create" || !x.diff || typeof x.diff !== "object" ? [] : Object.keys(x.diff)
            .filter((k) => /^schedule\.|^status$|^budget\.amount_kzt$|^geometry_precision$/.test(k) && x.diff[k] && typeof x.diff[k] === "object")
            .map((k) => el("p", { class: "civic-r04-hist-change" }, (HISTORY_LABEL[k] || k) + ": было " + C.fmtValue(k, x.diff[k].before) + " → стало " + C.fmtValue(k, x.diff[k].after)))),
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
      if (!rule.required && !S.confirm) { rebuild(V.reason, []); return; }
      const ta = el("textarea", { id: P + "reason", rows: 2, "data-fk": "reason", "aria-describedby": P + "reason-err" });
      ta.value = S.reason;
      ta.addEventListener("input", () => {
        S.reason = ta.value;
        if (S.reasonErr) { S.reasonErr = null; err.textContent = ""; ta.removeAttribute("aria-invalid"); }
        refreshFixNotice();
      });
      const err = el("p", { class: "civic-r04-err", id: P + "reason-err" }, S.reasonErr || "");
      if (S.reasonErr) ta.setAttribute("aria-invalid", "true");
      const shifted = (S.item && isDirty() && C.diffFields(S.item, currentFields()).some((x) => x.path === "schedule.current_planned_end"))
        || (S.confirm === "publish" && !!C.publicDeadlineMove(S.item));
      const chips = (shifted ? ["Перенос срока: "] : []).concat((rule.suggestions || []).filter((v) => !(shifted && /^Перенос срока/.test(v))))
        .filter((v, i, a) => a.indexOf(v) === i);
      const oe = S.form.original_planned_end, ce = S.form.current_planned_end;
      const fixed = oe ? "Первоначальный срок окончания будет зафиксирован: " + C.fmtDate(oe) + "."
        : ce ? "Первоначальный срок не указан — сервер зафиксирует как первоначальный актуальный срок " + C.fmtDate(ce) + "."
        : "Сроки неизвестны — в карточке будет «неизвестно».";
      const pend = S.item ? C.pendingInfo(S.item) : { known: false };
      const republish = S.item && S.item.publication === "published";
      const move = S.confirm === "publish" ? C.publicDeadlineMove(S.item) : !S.confirm && !pend.known && S.item ? C.publicDeadlineMove(S.item, currentFields()) : null;
      const intro = S.confirm === "apply"
        ? (republish && pend.known ? "Значения источника станут текущей версией записи. Жители увидят их только после «Опубликовать изменения…» — там понадобится понятная публичная причина."
          : republish ? "Значения источника заменят поля опубликованной записи." : "Значения источника заменят поля черновика.")
        : S.confirm === "dismiss" ? "Запись не изменится; предложение источника будет отмечено как отклонённое."
        : S.confirm === "publish" && republish && move
        ? "Жители увидят новый срок окончания " + C.fmtDate(move.to) + " (был " + C.fmtDate(move.from) + "), первоначальный срок и эту причину в публичной истории. Внутренняя заметка не публикуется."
        : S.confirm === "publish" && republish
        ? "Жители сейчас видят прежнюю версию. После подтверждения они увидят изменения из таблицы ниже; причина попадёт в публичную историю."
        : S.confirm === "publish"
        ? "После публикации запись увидят жители" + (currentFields().geometry ? " на карте" : " в списке (без точки на карте)") + ". " + fixed
        : S.confirm === "archive" ? "Запись исчезнет из публичного списка. Физического удаления нет — история сохраняется."
        : pend.known ? "Запись опубликована. Причина останется в служебной истории; жители увидят правки после «Опубликовать изменения…»."
        : "Запись опубликована: причину увидят в истории изменений.";
      const title = { publish: "Публикация", archive: "Перенос в архив", apply: "Принять изменения источника", dismiss: "Отклонить изменения источника" }[S.confirm];
      const label = S.confirm === "publish" ? (move ? "Причина переноса срока для жителей (видна в публичной истории)" : rule.title + " (видна жителям в истории)")
        : !S.confirm && move ? "Причина переноса срока (видна жителям в истории)" : rule.title;
      const kids = [
        S.confirm ? el("h4", { id: P + "confirm-h" }, title) : null,
        el("p", { class: "civic-r04-help" }, intro),
        el("label", { for: ta.id }, label + (rule.required ? " *" : "")), ta,
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
      const it = S.item, acts = C.allowedActions(it, S.session), dirty = isDirty(), busy = !!S.busy || S.reauth || !!S.conflict;
      let kids;
      if (S.confirm) {
        if (V.rare) rebuild(V.rare, []);
        const cl = { publish: "Подтвердить публикацию", archive: "Перенести в архив", apply: "Принять изменения источника", dismiss: "Отклонить предложение" }[S.confirm];
        kids = [btn(S.busy === S.confirm ? "Отправляем…" : cl, () => doTransition(S.confirm), S.confirm === "archive" ? "danger" : "primary", "confirm", { disabled: busy, "aria-busy": S.busy ? "true" : null }),
          btn("Отмена", cancelConfirm, "ghost", "confirm-cancel", { disabled: !!S.busy })];
      } else {
        const saveLabel = S.busy === "save" ? "Сохраняем…" : !it ? "Создать черновик" : it.publication === "published" ? "Сохранить изменения" : "Сохранить черновик";
        kids = [
          acts.edit ? btn(saveLabel, save, "primary", "save", { disabled: busy || (it && !dirty), "aria-busy": S.busy === "save" ? "true" : null }) : null,
          btn(S.preview ? "Скрыть предпросмотр" : "Как увидят жители", () => { S.preview = !S.preview; renderPreview(); renderButtons(); focusKey("preview"); }, "", "preview", { "aria-expanded": String(!!S.preview) }),
          // with unsaved edits these are hidden (not just disabled): the line below explains, and the sticky bar stays short
          acts.publish && it && !dirty ? btn(it.publication === "published" ? "Опубликовать изменения…" : "Опубликовать…", () => askConfirm("publish"), "", "publish", { disabled: busy }) : null,
        ].filter(Boolean);
        rebuild(V.rare, acts.archive && it && !dirty ? [el("p", { class: "civic-r04-row-btns civic-r04-rare" }, [
          btn("В архив…", () => askConfirm("archive"), "ghost", "archive", { disabled: busy })])] : []);
        if (S.conflict) kids.push(el("p", { class: "civic-r04-help" }, "Сначала выберите вариант в блоке «Запись уже изменена» выше."));
        else if (dirty && it && (acts.publish || acts.archive)) kids.push(el("p", { class: "civic-r04-help" }, "Публикация и архив доступны после сохранения изменений."));
      }
      rebuild(V.buttons, [el("div", { class: "civic-r04-row-btns" }, kids)]);
    }
    function setBusy(kind) {
      S.busy = kind;
      shell.setAttribute("aria-busy", kind ? "true" : "false");
      if (S.view === "edit") renderButtons();
    }
    function askConfirm(action, cand) {
      if (S.busy || !S.item) return;
      if (S.tool) {
        setNotice("error", "Рисование не завершено: нажмите «Готово» или «Отмена» (Esc), затем повторите.");
        focusKey(S.tool.mode !== "point" && S.tool.vertices.length ? "tool-done" : "tool-cancel");
        return;
      }
      if (isDirty()) {
        if (action === "apply") { setNotice("error", "Сначала сохраните или отмените свои правки: принятие источника заменит поля записи."); focusKey("msg"); }
        return;
      }
      S.confirmCand = action === "apply" || action === "dismiss" ? cand || null : null;
      if (action === "publish") {
        const pp = C.publishProblems(currentFields());
        if (Object.keys(pp).length) {
          Object.assign(S.server, pp);
          paintErrors();
          setNotice("error", "Публиковать пока нельзя. " + Object.values(pp).join(" "), [{ label: "К источникам", fk: "goto-sources", cls: "link", fn: () => focusField("sources") }]);
          focusKey("msg");
          return;
        }
      }
      S.confirm = action; S.reason = ""; S.reasonErr = null;
      renderPreview(); renderReason(); renderButtons(); renderSrcReview();
      focusKey("reason");
    }
    function cancelConfirm() {
      const a = S.confirm;
      S.confirm = null; S.reason = ""; S.reasonErr = null; S.confirmCand = null;
      renderPreview(); renderReason(); renderButtons(); renderSrcReview();
      focusKey(a === "apply" ? "cand-apply-0" : a === "dismiss" ? "cand-dismiss-0" : a || "save");
    }

    // ---------- save / publish / archive ----------
    function firstErrorKey() {  // in screen order, not in the order the blocks were built
      const ks = Object.keys(F).filter((k) => errorOf(k) && F[k].control);
      ks.sort((a, b) => (F[a].control.compareDocumentPosition(F[b].control) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
      return ks[0] || Object.keys(F).find((k) => errorOf(k));
    }
    function focusField(k) {
      const f = F[k];
      if (f && f.control && !f.control.disabled) { f.control.focus(); if (f.control.scrollIntoView) f.control.scrollIntoView({ block: "center", behavior: reduced() ? "auto" : "smooth" }); }
    }
    async function save() {
      if (S.busy || !S.form || S.view !== "edit") return;
      const it = S.item;
      if (!C.allowedActions(it, S.session).edit) return;
      if (S.tool) {  // an unfinished drawing is neither saved silently nor thrown away silently
        setNotice("error", "Рисование не завершено: нажмите «Готово», чтобы принять отметку, или «Отмена» (Esc), чтобы её не менять. Ничего не отправлено.");
        focusKey(S.tool.mode !== "point" && S.tool.vertices.length ? "tool-done" : "tool-cancel");
        return;
      }
      S.tried = true;
      revalidate();
      const fields = currentFields();
      const rule = it ? C.reasonRule(it, "update") : { required: false };
      let changes = null;
      if (it) {
        changes = C.buildChanges(it, fields);
        if (!Object.keys(changes).length) { setNotice("info", "Изменений нет — сохранять нечего."); return; }
      }
      // without R02's pending model the update of a published record is public at once: a deadline move needs a resident-readable reason
      const pubMove = it && !C.pendingInfo(it).known ? C.publicDeadlineMove(it, fields) : null;
      S.reasonErr = rule.required ? (pubMove ? C.validatePublicReason(S.reason, { deadlineMoved: true }) : C.validateReason(S.reason))
        : S.reason.trim() ? C.validateReason(S.reason) : null;
      const bad = Object.keys(S.errors);
      if (bad.length || S.reasonErr) {
        renderReason();
        const keys = bad.concat(S.reasonErr ? ["reason"] : []);
        setNotice("error", "Не сохранено: исправьте отмеченные поля (" + keys.length + "). Введённый текст на месте.", keys.slice(0, 6).map((k) => ({
          label: FORM_LABEL[k] || FORM_LABEL[k.split(".")[0]] || k, fk: "goto-" + k, cls: "link", fn: () => (k === "reason" ? focusKey("reason") : focusField(k)) })));
        S.notice.fixKeys = keys;
        if (bad.length) focusField(firstErrorKey() || bad[0]); else focusKey("reason");
        return;
      }
      setBusy("save");
      const nav0 = navSeq;
      try {
        if (!(await sameUserBeforeWrite())) return;
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
        const fresh = await reloadDetail(item, nav0);
        const msg = !it ? "Черновик создан (ред. " + item.revision + "). Жители его не видят."
          : "Сохранено (ред. " + item.revision + ")." + (!wasPublic ? "" : pend.known
            ? " Жители пока видят опубликованную версию — чтобы показать правки, нажмите «Опубликовать изменения…»."
            : " Изменение видно жителям и записано в историю.");
        if (!fresh) say(msg);  // the user is elsewhere now: announce, do not repaint another record's message
        else if (ignored.length) setNotice("warn", msg + " Сервер не принял поля: " + ignored.join(", ") + " — они не сохранены.");
        else setNotice("ok", msg);
        if (fresh) focusKey("msg");
        // only a change residents can see moves the public map (an internal note alone does not)
        if (wasPublic && !pend.known && C.diffFields(it, item).some((d) => d.path !== "internal_notes")) notifyPublished(item, "update");
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
      const rule = C.reasonRule(S.item, action), cand = S.confirmCand;
      if (action === "publish") S.reasonErr = C.validatePublicReason(S.reason, { deadlineMoved: !!C.publicDeadlineMove(S.item) });
      else if (rule.required || S.reason.trim()) S.reasonErr = C.validateReason(S.reason);
      else S.reasonErr = null;
      if (S.reasonErr) { renderReason(); focusKey("reason"); say(S.reasonErr, true); return; }
      if ((action === "apply" || action === "dismiss") && (!cand || cand.id === undefined)) return;
      const it = S.item, wasPublic = it.publication === "published", pendKnown = C.pendingInfo(it).known;
      setBusy(action);
      const nav0 = navSeq;
      try {
        if (!(await sameUserBeforeWrite())) return;
        const path = action === "apply" || action === "dismiss"
          ? "/staff/objects/" + enc(it.id) + "/import-candidates/" + enc(String(cand.id)) + "/" + action
          : "/staff/objects/" + enc(it.id) + "/" + action;
        const d = await call("POST", path, { expected_revision: it.revision, reason: S.reason.trim() });
        const item = d && d.item;
        if (!item || !item.id) throw Object.assign(new Error("Сервер не вернул запись"), { status: 500 });
        S.confirm = null; S.reason = ""; S.confirmCand = null;
        const fresh = await reloadDetail(item, nav0);
        const shown = fresh && S.item ? S.item : item;
        (fresh ? (t) => setNotice("ok", t) : (t) => say(t))(action === "publish"
          ? (wasPublic ? "Изменения опубликованы (ред. " + item.revision + ")." : item.geometry ? "Опубликовано: жители видят запись на карте." : "Опубликовано: жители видят запись в списке, без точки на карте.")
          : action === "apply"
          ? (shown.revision === it.revision ? "Источник совпадал с записью — изменений нет; предложение закрыто."
            : wasPublic && pendKnown ? "Изменения источника приняты (ред. " + shown.revision + "). Жители их пока не видят — нажмите «Опубликовать изменения…» и объясните причину."
            : "Изменения источника приняты (ред. " + shown.revision + ").")
          : action === "dismiss" ? "Предложение источника отклонено. Запись не изменилась."
          : "Запись в архиве и скрыта из публичного списка. История сохранена.");
        if (fresh) focusKey("msg");
        if (action === "publish" || action === "archive" ? (action === "publish" || wasPublic) : action === "apply" && wasPublic && !pendKnown) notifyPublished(item, action === "apply" ? "update" : action);
        updateListCache(item);  // the comparison is reloaded by openEditor() while candidates are pending
      } catch (e) {
        if (e === STALE) return;
        onActionError(e, action);
      } finally {
        if (S.alive && S.busy === action) setBusy(null);
      }
    }
    // nav0: navigation token taken when the action started; if the user has opened something else since, the finished
    // action does not pull the old record back onto the screen (returns false; the caller only announces the result).
    async function reloadDetail(item, nav0) {
      if (nav0 !== undefined && nav0 !== navSeq) { if (S.busy) setBusy(null); return false; }
      let it = item, hist = S.history;
      try {
        const d = await call("GET", "/staff/objects/" + enc(item.id));
        if (d && d.item) { it = d.item; hist = d.history || []; }
      } catch (e) {
        if (e === STALE) throw e;
        /* the action itself succeeded; history refresh can wait */
      }
      if (nav0 !== undefined && nav0 !== navSeq) { if (S.busy) setBusy(null); return false; }
      const notice = S.notice;
      setBusy(null);
      openEditor(it, hist);
      S.notice = notice;
      return true;
    }
    // info.visible: is the record public after this action? false after archive — the host must not open it on the
    // public map (R03 would show «Объект не найден»); refresh the map instead.
    function notifyPublished(item, action) {
      if (!onPublished) return;
      const visible = action !== "archive" && item && item.publication === "published";
      try { onPublished(C.pickPublic(item), { action, visible }); } catch (e) { console.error("CivicEditor onPublished:", e); }
    }
    async function loadConflict(n, action) {
      const it = S.item;
      try {
        const d = await call("GET", "/staff/objects/" + enc(it.id));
        const latest = d && d.item;
        if (!latest || !latest.id) throw Object.assign(new Error("Сервер не вернул запись"), { status: 404 });
        closeTool();
        // publish/archive whose answer was lost: the server shows it happened -> tell the map anyway
        if ((action === "publish" || action === "archive") && latest.publication !== it.publication
          && (action === "publish" ? latest.publication === "published" : latest.publication === "archived")) notifyPublished(latest, action);
        const latestForm = C.formFromItem(latest);
        S.conflict = { latest, history: d.history || [], base: clone(S.saved), latestForm, rebase: C.rebaseForm(S.saved, S.form, latestForm) };
        S.confirm = null;
        renderConflict(); renderReason(); renderPreview(); renderButtons();
        setNotice("error", action === "save" ? n : { text: "Запись изменилась на сервере — возможно, действие уже выполнено при обрыве связи. Проверьте состояние ниже." });
        focusKey(S.conflict.rebase.kept.length ? "rebase" : "rebase-drop");
      } catch (e) {
        if (e === STALE) return;
        const n = C.normalizeError(e);
        if (n.kind === "auth") { closeTool(); S.reauth = true; renderReauth(); renderButtons(); setNotice("error", n); focusKey("relogin-user"); return; }
        setNotice("error", n);
      }
    }
    function onActionError(e, action) {
      const n = C.normalizeError(e);
      const retry = { label: "Повторить", fk: "retry", fn: () => (action === "save" ? save() : action === "publish" || action === "archive" ? doTransition(action) : null) };
      if (n.kind === "auth") {
        closeTool();
        S.reauth = true;
        renderReauth(); renderButtons();
        setNotice("error", n);
        focusKey("relogin-user");
        return;
      }
      if (n.kind === "conflict" && (action === "apply" || action === "dismiss")) {
        S.confirm = null; S.confirmCand = null; S.reason = "";
        const it = S.item;
        reloadDetail(it).then(() => {
          setNotice("error", "Запись или предложение источника изменились (сейчас ред. " + (S.item ? S.item.revision : "?") + "). Сравнение обновлено, ничего не применено — проверьте и решите заново.");
          focusKey("srcreview");
        }, () => {});
        return;
      }
      if (n.kind === "conflict") { loadConflict(n, action); return; }
      if (n.kind === "validation") {
        S.server = {};
        for (const [k, m] of Object.entries(n.fields)) { if (k === "reason") S.reasonErr = m; else if (k !== "_form") S.server[k] = m; }
        paintErrors(); renderReason();
        const lost = Object.entries(S.server).filter(([k]) => !F[k]).map(([k, m]) => (FORM_LABEL[k] || FORM_LABEL[k.split(".")[0]] || k) + ": " + m);
        const shown = Object.keys(S.server).some((k) => F[k]) || !!S.reasonErr;
        setNotice("error", { text: shown ? n.text : "Сервер не принял запись. Причина:", detail: [n.fields._form].concat(lost).filter(Boolean).join(" ") || n.detail });
        const k = firstErrorKey();
        if (k) focusField(k); else if (S.reasonErr) focusKey("reason"); else focusKey("msg");
        return;
      }
      if (n.kind === "csrf") {
        call("GET", "/session").then((d) => { if (applySession(d)) afterSwitch(); else renderHead(); }, () => {});
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
        if (S.view === "edit") { closeTool(); S.reauth = true; renderReauth(); renderButtons(); setNotice("error", n); focusKey("relogin-user"); }
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
      nav();
      if (pendingOpen) { pendingOpen.resolve(false); pendingOpen = null; }
      detachMap();
      clearRecovery();
      S.internalNotes = o.internalNotes === true;
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
      if (pendingOpen) { pendingOpen.resolve(false); pendingOpen = null; }
      detachMap();
      if (releaseTimer) { clearTimeout(releaseTimer); releaseTimer = null; fireTool(false); }
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
      try { if (applySession(await call("GET", "/session"))) { await afterSwitch(); return; } }
      catch (e) {
        if (e === STALE) return;
        S.session = { authenticated: false, user: null };
        S.alert = Object.assign({ type: "error", actions: [{ label: "Повторить", fk: "boot-retry", fn: () => { S.alert = null; boot(); } }] }, C.normalizeError(e));
      }
      if (S.session.authenticated) { if (!(await takePendingOpen())) await showList(true); }
      else {
        if (pendingOpen) { pendingOpen.resolve(false); pendingOpen.resolve = noop; }  // not signed in: false now, open after login
        showLogin(pendingOpen ? { type: "info", text: "Войдите, чтобы открыть запись.", actions: [] } : undefined);
      }
    })();

    return {
      openObject: (id) => openObject(id),
      setMap,
      destroy,
    };
  }

  NS.mount = mount;
})();
