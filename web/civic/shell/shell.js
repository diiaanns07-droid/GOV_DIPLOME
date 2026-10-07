/* Civic shell (round 11, R01): default Astana city mode on the SAME MapLibre map.
 *
 * Owns: api.request (CSRF, error normalisation), session state in memory, the three
 * page modes (civic | school | training), mount points and module lifecycle.
 * Role modules plug in through the civic-v1 globals (CONTRACT.txt §4):
 *   CivicMap, CivicEditor, CivicFeedback, CivicScenarios, CivicAssistant.
 * A role module that is missing is reported in place (no hidden substitute implementation).
 * Untrusted text is rendered with textContent only.
 */
(function () {
  "use strict";
  const API_BASE = "/api/civic/v1";
  const MODES = ["civic", "school", "training"];
  const MODE_KEY = "civic.mode.v1";
  const $c = (id) => document.getElementById(id);
  const el = (tag, attrs, text) => {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {}))
      if (value !== null && value !== undefined && value !== false) node.setAttribute(key, value === true ? "" : value);
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  };

  // ---------------------------------------------------------------- api.request
  // Safe, structured error details modules may rely on (R04 conflict merge, R06 receipts, rate limits).
  // Only these keys, type-checked; server text beyond `message` (stack traces, SQL) is never copied.
  const ERROR_DETAILS = {
    current_revision: (v) => Number.isInteger(v) && v >= 0,
    retry_after: (v) => Number.isInteger(v) && v >= 0 && v <= 86400,
    can_confirm: (v) => typeof v === "boolean",
    allowed: (v) => Array.isArray(v) && v.length <= 20 && v.every((x) => typeof x === "string" && x.length <= 40),
    previous_receipt: (v) => v && typeof v === "object" && !Array.isArray(v) && JSON.stringify(v).length <= 2000,
  };
  class CivicApiError extends Error {
    constructor(status, code, message, fields, details) {
      super(message || "Запрос не выполнен.");
      this.name = "CivicApiError";
      this.status = status;
      this.code = code || "error";
      this.fields = fields || null;
      // Same facts in both shapes modules read: err.current_revision and err.error.current_revision.
      const error = { code: this.code, message: this.message, fields: this.fields };
      for (const [key, ok] of Object.entries(ERROR_DETAILS)) {
        if (details && Object.prototype.hasOwnProperty.call(details, key) && ok(details[key])) error[key] = this[key] = details[key];
      }
      this.error = error;
    }
  }
  const session = { checked: false, authenticated: false, user: null, csrfToken: null };
  const sessionListeners = new Set();
  function applySession(data) {
    const authenticated = !!(data && data.authenticated === true && data.user);
    session.checked = true;
    session.authenticated = authenticated;
    session.user = authenticated ? { name: String(data.user.name ?? ""), role: String(data.user.role ?? "") } : null;
    // The token lives only in memory: never localStorage/sessionStorage.
    session.csrfToken = authenticated && typeof data.csrf_token === "string" ? data.csrf_token : null;
    for (const listener of [...sessionListeners]) {
      try { listener(publicSession()); } catch (error) { console.error(error); }
    }
  }
  const publicSession = () => ({ checked: session.checked, authenticated: session.authenticated,
    user: session.user ? { ...session.user } : null });

  function checkPath(path) {
    if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//") || path.length > 1800
        || /[\s\\#]/.test(path) || /(^|\/)\.\.?(\/|$|\?)/.test(path) || /^[a-z]+:/i.test(path))
      throw new CivicApiError(0, "bad_path", "Некорректный адрес API.");
  }
  async function send(method, path, body, options) {
    const headers = { Accept: "application/json" };
    let payload;
    if (method === "POST") {
      headers["Content-Type"] = "application/json";
      if (session.csrfToken) headers["X-CSRF-Token"] = session.csrfToken;
      // Stable key from the caller (R04 create) lets R02 return the same object on a repeated POST.
      if (typeof options?.idempotencyKey === "string" && /^[A-Za-z0-9._:-]{8,64}$/.test(options.idempotencyKey))
        headers["Idempotency-Key"] = options.idempotencyKey;
      payload = JSON.stringify(body ?? {});
    }
    const controller = new AbortController();
    const outer = options?.signal;
    const onAbort = () => controller.abort();
    if (outer) {
      if (outer.aborted) controller.abort();
      else outer.addEventListener("abort", onAbort, { once: true });
    }
    const timer = setTimeout(() => controller.abort(), options?.timeoutMs || 15000);
    let response;
    try {
      response = await fetch(API_BASE + path, { method, headers, body: payload, credentials: "same-origin",
        cache: "no-store", redirect: "error", signal: controller.signal });
    } catch (error) {
      if (outer?.aborted) throw new CivicApiError(0, "aborted", "Запрос отменён.");
      throw error?.name === "AbortError"
        ? new CivicApiError(0, "timeout", "Сервер не ответил вовремя. Повторите попытку.")
        : new CivicApiError(0, "network", "Нет соединения с сервером приложения.");
    } finally {
      clearTimeout(timer);
      outer?.removeEventListener("abort", onAbort);
    }
    let envelope = null;
    try { envelope = await response.json(); } catch { envelope = null; }
    if (!envelope || typeof envelope !== "object" || typeof envelope.ok !== "boolean")
      throw new CivicApiError(response.status, "bad_response", "Сервер вернул нечитаемый ответ.");
    if (!envelope.ok || !response.ok) {
      const error = envelope.error && typeof envelope.error === "object" ? envelope.error : {};
      const details = { ...error };
      // Retry-After header (seconds) when the body does not carry retry_after itself.
      const header = Number.parseInt(response.headers.get("Retry-After") || "", 10);
      if (!Number.isInteger(details.retry_after) && Number.isInteger(header)) details.retry_after = header;
      throw new CivicApiError(response.status, String(error.code || "error"),
        typeof error.message === "string" ? error.message : "Запрос не выполнен.",
        error.fields && typeof error.fields === "object" ? error.fields : null, details);
    }
    return envelope.data;
  }
  let sessionSeq = 0;
  async function request(method, path, body, options) {
    method = String(method || "GET").toUpperCase();
    if (method !== "GET" && method !== "POST") throw new CivicApiError(0, "bad_method", "Метод не поддерживается.");
    checkPath(path);
    // The public map never needs staff data: refuse /staff calls without a session.
    if (path.startsWith("/staff") && session.checked && !session.authenticated)
      throw new CivicApiError(401, "unauthenticated", "Войдите как сотрудник, чтобы продолжить.");
    const isSessionPath = path === "/session" || path === "/session/login" || path === "/session/logout";
    // Only the latest /session-family request may change the session (no stale overwrite).
    const seq = isSessionPath ? ++sessionSeq : 0;
    let data;
    try {
      data = await send(method, path, body, options);
    } catch (error) {
      if (error instanceof CivicApiError && error.status === 401 && session.authenticated)
        applySession(null);
      // CSRF/session token rotated (restart, other tab): refresh once and retry.
      // Safe to repeat: a 403 CSRF rejection means the server did not act.
      if (error instanceof CivicApiError && error.status === 403 && /csrf/i.test(error.code)
          && method === "POST" && !options?.retried) {
        await refreshSession().catch(() => null);
        if (session.authenticated) return request(method, path, body, { ...options, retried: true });
      }
      throw error;
    }
    if (isSessionPath && seq === sessionSeq) applySession(data);
    return data;
  }
  const refreshSession = () => request("GET", "/session");
  const api = {
    request,
    login: (username, password) => request("POST", "/session/login", { username, password }),
    logout: () => request("POST", "/session/logout", {}),
    refreshSession,
    get session() { return publicSession(); },
    onSession(listener) { sessionListeners.add(listener); return () => sessionListeners.delete(listener); },
    CivicApiError,
  };

  // ---------------------------------------------------------------- page modes
  const S = { keepSeq: 0, frameSeq: 0, view: null, recordCount: null, mode: null, mapState: "pending", modules: null, mounted: {}, selected: null, assistantSeq: 0, editorTool: false,
    panelOpen: true, sheet: "half", started: false };
  const originalTitle = document.title;
  const brandTitle = document.querySelector(".brand-title");
  const brandSub = document.querySelector(".brand-sub");
  const originalBrand = brandTitle ? brandTitle.innerHTML : "";
  const originalSub = brandSub ? brandSub.textContent : "";

  // DOM: one root with the public panel, editor drawer and scenarios drawer.
  const root = el("section", { id: "civic-root", hidden: true, "aria-label": "Городская платформа Астаны" });
  root.innerHTML = `
    <div id="civic-panel" class="civic-panel" data-sheet="half">
      <button type="button" id="civic-sheet-handle" class="civic-sheet-handle" aria-label="Развернуть панель" aria-expanded="false"><i></i></button>
      <header class="civic-head">
        <span class="eyebrow">Астана · городские работы и события</span>
        <h1>Что меняется в городе</h1>
        <p id="civic-data-note" class="civic-data-note"></p>
      </header>
      <div id="civic-state" class="civic-state" role="status" aria-live="polite"></div>
      <div id="civic-scroll" class="civic-scroll">
        <div id="civic-map-root" class="civic-slot"></div>
        <section id="civic-feedback-box" class="civic-box" hidden aria-label="Сообщение жителя">
          <div class="civic-box-head"><h2>Сообщить о проблеме или предложении</h2><button type="button" class="civic-close" data-close="feedback" aria-label="Закрыть форму">×</button></div>
          <div id="civic-feedback-root" class="civic-slot"></div>
        </section>
        <section id="civic-assistant-box" class="civic-box" hidden aria-label="Вопрос по объекту">
          <div id="civic-assistant-root" class="civic-slot"></div>
        </section>
      </div>
      <footer class="civic-foot">
        <button type="button" id="civic-staff-button" class="btn">Для сотрудников</button>
        <button type="button" id="civic-scenarios-button" class="btn">Сравнить ограничения</button>
        <button type="button" id="civic-moderation-button" class="btn" hidden>Сообщения жителей</button>
      </footer>
    </div>
    <section id="civic-editor" class="civic-drawer" hidden aria-label="Кабинет сотрудника">
      <div class="civic-box-head"><h2>Кабинет сотрудника</h2><button type="button" class="civic-close" data-close="editor" aria-label="Закрыть кабинет">×</button></div>
      <div id="civic-editor-root" class="civic-slot civic-drawer-body"></div>
    </section>
    <section id="civic-moderation" class="civic-drawer" hidden aria-label="Сообщения жителей">
      <div class="civic-box-head"><h2>Сообщения жителей</h2><button type="button" class="civic-close" data-close="moderation" aria-label="Закрыть модерацию">×</button></div>
      <div id="civic-moderation-root" class="civic-slot civic-drawer-body"></div>
    </section>
    <section id="civic-scenarios" class="civic-drawer" hidden aria-label="Сравнение ограничений">
      <div class="civic-box-head"><h2>Сравнение ограничений</h2><button type="button" class="civic-close" data-close="scenarios" aria-label="Закрыть сравнение">×</button></div>
      <p class="civic-note civic-scenario-limits">Сравните два варианта перекрытия на пешеходной сети. Расчёт показывает изменение длины пути; неизвестный доступ исключён. Это гипотеза, не прогноз пробок и не официальное перекрытие.</p>
      <div id="civic-scenarios-root" class="civic-slot civic-drawer-body"></div>
      <p class="civic-attribution">© участники OpenStreetMap (ODbL-1.0). Дата и источник — у выбранной сети. Старый срез K03: Overture Maps Foundation, выпуск 2026-09-23.1.</p>
    </section>`;
  document.body.append(root);

  // Role modules only (R03 map, R04 editor, R06 feedback, R07 scenarios, R09 assistant). The R01
  // fallbacks used before the deliveries were removed once the modules were integrated: one
  // implementation per function. A missing module is reported, never silently replaced.
  const moduleFor = (name) => ({
    map: window.CivicMap, editor: window.CivicEditor, feedback: window.CivicFeedback,
    scenarios: window.CivicScenarios, assistant: window.CivicAssistant,
  })[name] || null;
  const isFallback = () => false;
  const MODULE_MISSING = {
    map: "Модуль карты и карточек (R03) не загружен.", editor: "Кабинет редактора (R04) не загружен.",
    feedback: "Форма сообщений (R06) не загружена.", scenarios: "Модуль сравнения (R07) не загружен.",
    assistant: "Помощник (R09) не загружен.",
  };

  function currentMap() {
    return typeof mapReady !== "undefined" && mapReady && typeof map !== "undefined" ? map : null;
  }
  function stateLine(text, kind) {
    const box = $c("civic-state");
    box.replaceChildren();
    if (!text) { box.hidden = true; return; }
    box.hidden = false;
    box.dataset.kind = kind || "info";
    box.append(el("span", null, text));
    if (kind === "error") {
      const retry = el("button", { type: "button", class: "text-button" }, "Повторить");
      retry.addEventListener("click", () => { void loadModules().then(() => remountAll()); });
      box.append(retry);
    }
  }
  function destroyMounted(name) {
    const handle = S.mounted[name];
    delete S.mounted[name];
    if (handle && typeof handle.destroy === "function") {
      try { handle.destroy(); } catch (error) { console.error("civic destroy", name, error); }
    }
  }
  function mount(name, rootNode, options) {
    destroyMounted(name);
    const module = moduleFor(name);
    if (!module || typeof module.mount !== "function") {
      rootNode.replaceChildren(el("p", { class: "civic-error" }, MODULE_MISSING[name] || "Модуль не загружен."));
      return null;
    }
    try {
      const handle = module.mount({ root: rootNode, api, ...options });
      S.mounted[name] = handle || {};
      return S.mounted[name];
    } catch (error) {
      console.error("civic mount", name, error);
      rootNode.replaceChildren(el("p", { class: "civic-error" }, "Модуль не запустился. Обновите страницу или вернитесь позже."));
      return null;
    }
  }

  async function loadModules() {
    try {
      const data = await request("GET", "/modules");
      S.modules = data && data.modules ? data.modules : null;
    } catch (error) {
      S.modules = null;
    }
    return S.modules;
  }
  function describeData() {
    const note = $c("civic-data-note");
    const store = S.modules?.store?.status;
    if (store === "ready") note.textContent = "Показаны только опубликованные записи. У каждой карточки — источник, тип сведений и история сроков.";
    else note.textContent = "";
    if (!S.modules) stateLine("Сервер городской платформы не отвечает.", "error");
    else if (store !== "ready") stateLine("Сервис объектов не подключён в этой сборке: карта работ пока пуста. Учебная модель и школы доступны в переключателе сверху.", "warn");
    else stateLine("");
    $c("civic-staff-button").hidden = store !== "ready";
    const scenarios = S.modules?.scenarios?.status === "ready" && !!moduleFor("scenarios");
    $c("civic-scenarios-button").hidden = !scenarios;
    syncModerationButton();
  }

  function mountPublic() {
    if (S.mode !== "civic") return;
    describeData();
    // Wait for the map (or its definitive failure) so layers attach to the one instance.
    if (S.mapState === "pending" || !S.modules) return;
    if (S.modules?.store?.status !== "ready") { destroyMounted("map"); $c("civic-map-root").replaceChildren(); return; }
    mount("map", $c("civic-map-root"), {
      map: currentMap(),
      fitOnLoad: false,  // Open the city; fitting the small demo list is an explicit action.
      onData: (items) => { S.recordCount = items.length; S.mounted.explore?.updateRecords?.(items); },
      onSelect: (item) => onSelect(item),
      onFeedback: (target) => openFeedback(target),
    });
    if (S.selected) S.mounted.map?.selectObject?.(S.selected);
  }
  function remountAll() {
    if (S.mode !== "civic") return;
    mountPublic();
  }

  function onSelect(item) {
    const id = item && typeof item === "object" ? item.id : item;
    S.selected = typeof id === "string" ? id : null;
    if (S.selected && window.CivicExplore) {
      // A permalink selects before R03's list has loaded ({id} only): read the public geometry then.
      const id = S.selected;
      const located = item?.geometry ? Promise.resolve(item)
        : request("GET", "/objects/" + encodeURIComponent(id)).then((data) => data?.item || null, () => null);
      located.then((it) => {
        if (S.selected !== id) return;
        if (!item?.title && it?.title) S.mounted.explore?.setView?.("Открыта запись: " + it.title, "object");
        const box = it?.geometry ? window.CivicExplore.bounds(it.geometry) : null;
        if (box) keepVisible([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]);
      });
    }
    if (S.selected) S.mounted.explore?.setView?.("Открыта запись" + (item?.title ? ": " + item.title : ""), "object");
    else S.mounted.explore?.setView?.(S.view?.text || "", S.view?.kind || "");
    const hash = S.selected ? "#object=" + encodeURIComponent(S.selected) : "";
    if (location.hash !== hash) history.replaceState(null, "", location.pathname + location.search + hash);
    closeFeedback();
    destroyMounted("assistant");
    $c("civic-assistant-box").hidden = true;
    const assistant = moduleFor("assistant");
    if (S.selected && assistant && S.modules?.assistant?.status === "ready") {
      // Mount R09 only for an object confirmed public (permalinks may name drafts/unknown ids).
      const id = S.selected, seq = ++S.assistantSeq;
      request("GET", "/objects/" + encodeURIComponent(id)).then(() => {
        if (seq !== S.assistantSeq || S.selected !== id || S.mode !== "civic") return;
        $c("civic-assistant-box").hidden = false;
        mount("assistant", $c("civic-assistant-root"), { objectId: id });
      }).catch((error) => {
        if (seq !== S.assistantSeq || S.selected !== id) return;
        if (error?.status === 404) {
          S.selected = null;
          if (location.hash.startsWith("#object=")) history.replaceState(null, "", location.pathname + location.search);
        }
      });
    }
    if (S.selected && innerWidth < 761 && S.sheet === "peek") setSheet("half");
  }
  function openFeedback(target) {
    if (S.modules?.feedback?.status !== "ready") {
      toastSafe("Отправка сообщений пока не подключена в этой сборке.");
      return;
    }
    const objectId = target && typeof target === "object" ? (target.objectId ?? target.object_id ?? target.id ?? null) : (typeof target === "string" ? target : null);
    const geometry = target && typeof target === "object" && target.geometry ? target.geometry : null;
    $c("civic-feedback-box").hidden = false;
    mount("feedback", $c("civic-feedback-root"), { objectId, geometry });
    $c("civic-feedback-box").scrollIntoView({ block: "nearest", behavior: motionSafe() ? "smooth" : "auto" });
    if (innerWidth < 761) setSheet("full");
  }
  function closeFeedback() {
    destroyMounted("feedback");
    $c("civic-feedback-root").replaceChildren();
    $c("civic-feedback-box").hidden = true;
  }
  function openEditor(objectId) {
    if (!$c("civic-moderation").hidden) closeModeration();
    if (!$c("civic-scenarios").hidden) closeScenarios();
    $c("civic-editor").hidden = false;
    syncDrawerFlag();
    document.body.classList.add("civic-editor-open");
    const handle = S.mounted.editor || mount("editor", $c("civic-editor-root"), {
      map: currentMap(),
      onPublished: (item) => {
        S.mounted.map?.refresh?.();
        if (item?.id) { S.selected = item.id; S.mounted.map?.selectObject?.(item.id); }
      },
    });
    if (objectId && handle?.openObject) handle.openObject(objectId);
    $c("civic-editor").querySelector(".civic-close")?.focus();
  }
  // Resident messages (R06 mountModeration): own staff-only drawer, as proposed in R06's
  // r01_integration.patch. The button exists only for a signed-in editor; the server still decides.
  const moderationReady = () => S.modules?.feedback?.status === "ready" && typeof window.CivicFeedback?.mountModeration === "function";
  function syncModerationButton() {
    $c("civic-moderation-button").hidden = !(moderationReady() && session.authenticated && S.mode === "civic");
    // Session end hides only the launcher: an open drawer stays so R06 can show "сессия истекла"
    // and keep the moderator's text; the server refuses further staff actions anyway.
  }
  function openModeration() {
    if (!$c("civic-editor").hidden) closeEditor();
    if (!$c("civic-scenarios").hidden) closeScenarios();
    $c("civic-moderation").hidden = false;
    syncDrawerFlag();
    destroyMounted("moderation");
    try {
      S.mounted.moderation = window.CivicFeedback.mountModeration({ root: $c("civic-moderation-root"), api, map: currentMap(),
        onOpenObject: (objectId) => { closeModeration(); S.selected = objectId; S.mounted.map?.selectObject?.(objectId); } }) || {};
    } catch (error) {
      console.error("civic moderation", error);
      $c("civic-moderation-root").replaceChildren(el("p", { class: "civic-error" }, "Очередь сообщений не запустилась."));
    }
    $c("civic-moderation").querySelector(".civic-close")?.focus();
  }
  function closeModeration() {
    destroyMounted("moderation");
    $c("civic-moderation-root").replaceChildren();
    $c("civic-moderation").hidden = true;
    syncDrawerFlag();
  }
  $c("civic-moderation-button").addEventListener("click", openModeration);
  sessionListeners.add(() => syncModerationButton());
  function syncDrawerFlag() {
    const open = ["civic-editor", "civic-moderation", "civic-scenarios"].some((id) => !$c(id).hidden);
    if (open) document.body.dataset.civicDrawer = "open"; else delete document.body.dataset.civicDrawer;
  }
  function closeEditor() {
    S.editorTool = false;
    destroyMounted("editor");
    $c("civic-editor").hidden = true;
    syncDrawerFlag();
    document.body.classList.remove("civic-editor-open");
    $c("civic-staff-button").focus();
  }
  function openScenarios() {
    if (!$c("civic-editor").hidden) closeEditor();
    if (!$c("civic-moderation").hidden) closeModeration();
    $c("civic-scenarios").hidden = false;
    syncDrawerFlag();
    // R07 review: the shell's api.request already adds /api/civic/v1 -> empty apiPrefix.
    mount("scenarios", $c("civic-scenarios-root"), { map: currentMap(), apiPrefix: "" });
  }
  function closeScenarios() {
    destroyMounted("scenarios");
    $c("civic-scenarios-root").replaceChildren();
    $c("civic-scenarios").hidden = true;
    syncDrawerFlag();
  }
  function setSheet(stateName) {
    S.sheet = ["peek", "half", "full"].includes(stateName) ? stateName : "half";
    $c("civic-panel").dataset.sheet = S.sheet;
    document.body.dataset.civicSheet = S.sheet;
    const handle = $c("civic-sheet-handle");
    handle.setAttribute("aria-expanded", String(S.sheet === "full"));
    handle.setAttribute("aria-label", S.sheet === "full" ? "Свернуть панель" : "Развернуть панель");
  }
  root.addEventListener("click", (event) => {
    const close = event.target.closest("[data-close]");
    if (!close) return;
    ({ feedback: closeFeedback, editor: closeEditor, scenarios: closeScenarios, moderation: closeModeration })[close.dataset.close]?.();
  });
  $c("civic-staff-button").addEventListener("click", () => openEditor());
  $c("civic-scenarios-button").addEventListener("click", openScenarios);
  // peek -> half -> full -> half: a lowered sheet comes back to its usual height first.
  $c("civic-sheet-handle").addEventListener("click", () => setSheet(S.sheet === "half" ? "full" : "half"));

  function toastSafe(text) {
    if (typeof toast === "function") toast(text);
  }
  const motionSafe = () => !matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Training district layers/markers: hidden while the civic mode owns the map.
  function trainingLayers(visible) {
    const m = currentMap();
    if (!m) return;
    for (const id of ["district-fill", "district-outline", "district-selected"])
      if (m.getLayer(id)) m.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
    if (typeof markers !== "undefined") for (const { el: marker } of markers) marker.style.display = visible ? "" : "none";
    if (!visible && typeof popup !== "undefined") popup?.remove();
  }
  // The part of the map not covered by the top bar, navigation box, map tools, panel/sheet or an open
  // drawer, as MapLibre padding. Measured from the live layout, so sheet size and box height count.
  function freeArea() {
    const m = currentMap();
    const c = m.getContainer().getBoundingClientRect();
    const pad = { top: 12, right: 12, bottom: 12, left: 12 };
    const mobile = innerWidth < 761;
    const shown = (el) => el && el.getClientRects().length && getComputedStyle(el).visibility !== "hidden" ? el.getBoundingClientRect() : null;
    for (const el of [document.querySelector(".topbar"), root.querySelector(".civic-explore")]) {
      const r = shown(el);
      if (r && r.top < c.top + c.height / 2) pad.top = Math.max(pad.top, r.bottom - c.top + 12);
    }
    const tools = shown(document.querySelector(".map-tools"));
    if (tools) pad.right = Math.max(pad.right, c.right - tools.left + 10);
    const panel = shown($c("civic-panel"));
    if (panel) {
      if (mobile) pad.bottom = Math.max(pad.bottom, c.bottom - panel.top + 12);
      else pad.left = Math.max(pad.left, panel.right - c.left + 20);
    }
    for (const id of ["civic-editor", "civic-moderation", "civic-scenarios"]) {
      const r = shown($c(id));
      if (!r) continue;
      if (mobile) pad.bottom = Math.max(pad.bottom, c.bottom - r.top + 12);
      else pad.right = Math.max(pad.right, c.right - r.left + 16);
    }
    // Never ask for more than the map has: keep at least a 120px free window each way.
    const fit = (a, b, size) => { const max = Math.max(0, size - 120); if (pad[a] + pad[b] > max) { const k = max / (pad[a] + pad[b]); pad[a] = Math.floor(pad[a] * k); pad[b] = Math.floor(pad[b] * k); } };
    fit("left", "right", c.width); fit("top", "bottom", c.height);
    return pad;
  }
  // Pitch for camera moves started by the shell: the intended 3D state, not a mid-animation value.
  const intendedPitch = () => (typeof state !== "undefined" && state?.threeD ? 45 : 0);
  const intendedBearing = () => (typeof state !== "undefined" && state?.threeD ? -14 : 0);

  // R03's fitAll frames with its own padding (it does not know the navigation box) and the current,
  // possibly mid-animation pitch. Until R03 accepts a padding callback (see INTEGRATION.txt), its one
  // synchronous fitBounds call gets the shell's free area and intended tilt; the map is restored after.
  function fitAllObjects() {
    const m = currentMap(), r03 = S.mounted.map;
    if (!m || typeof r03?.fitAll !== "function") return false;
    const original = m.fitBounds;
    m.fitBounds = function (bounds, options) {
      const pitch = intendedPitch();
      return original.call(this, bounds, Object.assign({}, options, { padding: freeArea(), pitch, bearing: pitch ? intendedBearing() : 0 }));
    };
    try { return r03.fitAll(); } finally { m.fitBounds = original; }
  }
  // After R03's own selection camera settles, the selected place must not sit under the shell's
  // overlays (navigation box, sheet, drawers); if it does, pan it into the free area.
  function keepVisible(lngLat) {
    const m = currentMap();
    if (!m || !lngLat) return;
    const seq = ++S.keepSeq;
    const run = () => {
      if (seq !== S.keepSeq || m.isMoving()) return;
      const pad = freeArea(), c = m.getContainer().getBoundingClientRect();
      let p;
      try { p = m.project(lngLat); } catch { return; }
      const free = { l: pad.left, t: pad.top, r: c.width - pad.right, b: c.height - pad.bottom };
      if (p.x >= free.l && p.x <= free.r && p.y >= free.t && p.y <= free.b) return;
      m.panBy([p.x - (free.l + free.r) / 2, p.y - (free.t + free.b) / 2], { duration: motionSafe() ? 350 : 0 });
    };
    m.once("moveend", () => setTimeout(run, 60));
    setTimeout(run, 1600);  // R03 may not move the camera at all
  }

  // The navigation box names what the camera shows; an open record overrides it until the card closes.
  function showView(text, kind) {
    S.view = { text, kind };
    if (!S.selected) S.mounted.explore?.setView?.(text, kind);
  }
  function civicCamera() {
    const m = currentMap();
    if (!m) return;
    showView("Обзор: вся Астана", "city");
    const padding = freeArea();
    try {
      const bounds = typeof cityBounds === "function" ? cityBounds() : null;
      if (bounds) m.fitBounds(bounds, { padding, maxZoom: 12.2, pitch: intendedPitch(),
        bearing: intendedBearing(), duration: S.started ? 700 * (motionSafe() ? 1 : 0) : 0 });
    } catch (error) { console.warn("civic camera", error); }
  }

  // The map's status notice (map.js writes it, e.g. "basemap unavailable") lives inside the navigation
  // box while the city mode is on, so the box can never cover it; it goes back for the other modes.
  const mapStatus = document.getElementById("map-status");
  const mapStatusHome = document.createComment("map-status home");
  mapStatus?.after(mapStatusHome);
  function placeMapStatus(inside) {
    if (!mapStatus) return;
    const slot = inside ? S.mounted.explore?.noticeSlot : null;
    if (slot) { if (mapStatus.parentNode !== slot) slot.append(mapStatus); }
    else if (mapStatus.parentNode !== mapStatusHome.parentNode) mapStatusHome.before(mapStatus);
  }

  function mountExplore() {
    if (S.mounted.explore) { placeMapStatus(true); return; }
    if (!currentMap() || !window.CivicExplore) return;
    // After a district/street is framed, say how many published records are in frame; zero in frame
    // is stated as "none published here", never as "no works here".
    const reportFrame = (label, kind) => {
      const m = currentMap(), seq = ++S.frameSeq;
      m?.once("moveend", () => setTimeout(() => {
        if (seq !== S.frameSeq || S.view?.kind !== kind) return;
        const layers = (S.mounted.map?.layerIds?.() || []).filter((id) => m.getLayer(id));
        let n = 0;
        try { n = new Set(m.queryRenderedFeatures({ layers }).map((f) => f.properties?.cid).filter(Boolean)).size; } catch { n = 0; }
        if (S.recordCount === 0) showView(label + " · реестр пуст", kind);
        else showView(label + (n ? ` · записей в кадре: ${n}` : " · в кадре опубликованных записей нет (это не значит, что работ нет)"), kind);
      }, 120));
    };
    const frame = (b, maxZoom) => {
      // Measure after the navigation box has updated its status line (its height changes).
      requestAnimationFrame(() => {
        const m = currentMap();
        if (!m || !b) return;
        const pitch = intendedPitch();
        m.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: freeArea(), maxZoom,
          pitch, bearing: pitch ? m.getBearing() || intendedBearing() : 0, duration: motionSafe() ? 800 : 0 });
      });
    };
    // Phones: exploring the map lowers the sheet to its peek height first, otherwise the free map
    // window between the navigation box and a half sheet is ~120px; framing waits for the sheet.
    const roomy = (fn) => {
      if (innerWidth < 761 && S.sheet !== "peek") { setSheet("peek"); setTimeout(fn, motionSafe() ? 300 : 0); }
      else fn();
    };
    S.mounted.explore = window.CivicExplore.mount({ root, map: currentMap(),
      districts: typeof geojson !== "undefined" ? geojson : null,
      onNavigate: (feature) => {
        S.mounted.map?.selectObject?.(null);
        S.mounted.map?.setFilters?.({ area: !!feature });
        if (!feature) { civicCamera(); return; }
        const b = window.CivicExplore.bounds(feature.geometry);
        const label = `Район ${feature.properties.name} (граница OSM)`;
        showView(label, "district");
        reportFrame(label, "district");
        roomy(() => frame(b, 13.7));
      },
      onStreet: (street) => {
        S.mounted.map?.selectObject?.(null);
        S.mounted.map?.setFilters?.({ area: true });
        showView(`Улица: ${street.name}`, "street");
        reportFrame(`Улица: ${street.name}`, "street");
        roomy(() => frame(street.bbox, 16));
      },
      onObjects: () => {
        S.mounted.explore?.reset?.();
        S.mounted.map?.selectObject?.(null);
        S.mounted.map?.setFilters?.({ area: false });
        roomy(() => {
          if (fitAllObjects()) showView("Все опубликованные записи на карте", "objects");
          else toastSafe(S.recordCount === 0 ? "В реестре пока нет опубликованных записей." : "Нет объектов с координатами для выбранных фильтров.");
        });
      },
    });
    placeMapStatus(true);
  }

  function syncModeButtons() {
    document.querySelectorAll("#civic-modes [data-mode]").forEach((button) => {
      const on = button.dataset.mode === S.mode;
      button.setAttribute("aria-pressed", String(on));
    });
  }
  function activateCivic() {
    document.body.classList.add("civic-mode");
    root.hidden = false;
    if (brandTitle) brandTitle.textContent = "Астана.";
    if (brandSub) brandSub.textContent = "Городские работы, сроки и сообщения жителей";
    document.title = "Астана · городские работы и события";
    $c("map")?.setAttribute("aria-label", "Карта городских работ и событий Астаны");
    trainingLayers(false);
    mountExplore();
    civicCamera();
    setSheet("half");
    void loadModules().then(() => mountPublic());
  }
  function deactivateCivic() {
    placeMapStatus(false);  // before the navigation box (its current parent) is destroyed
    for (const name of Object.keys(S.mounted)) destroyMounted(name);
    for (const id of ["civic-map-root", "civic-feedback-root", "civic-assistant-root", "civic-editor-root", "civic-moderation-root", "civic-scenarios-root"])
      $c(id).replaceChildren();
    $c("civic-feedback-box").hidden = $c("civic-assistant-box").hidden = true;
    $c("civic-editor").hidden = $c("civic-scenarios").hidden = $c("civic-moderation").hidden = true;
    syncDrawerFlag();
    $c("civic-moderation-button").hidden = true;
    document.body.classList.remove("civic-mode", "civic-editor-open");
    delete document.body.dataset.civicSheet;
    root.hidden = true;
    if (brandTitle) brandTitle.innerHTML = originalBrand;
    if (brandSub) brandSub.textContent = originalSub;
    document.title = originalTitle;
    $c("map")?.setAttribute("aria-label", "Интерактивная карта районов Астаны");
    if (location.hash.startsWith("#object=")) history.replaceState(null, "", location.pathname + location.search);
  }
  function setMode(mode, options) {
    if (!MODES.includes(mode)) mode = "civic";
    if (S.mode === mode) return;
    const previous = S.mode;
    S.mode = mode;
    if (previous === "civic") deactivateCivic();
    const gov = window.GOVTECH;
    if (mode === "school") {
      if (gov) { gov.setActive(true); gov.setSchool(true); }
    } else if (gov?.active) {
      gov.setActive(false);
    }
    if (mode === "training") {
      trainingLayers(true);
      if (typeof flyOverview === "function" && previous) flyOverview();
    }
    if (mode === "civic") activateCivic();
    else document.body.classList.remove("civic-mode");
    syncModeButtons();
    if (options?.persist !== false) {
      try { localStorage.setItem(MODE_KEY, mode); } catch { /* per-viewer convenience only */ }
    }
  }
  document.querySelectorAll("#civic-modes [data-mode]").forEach((button) =>
    button.addEventListener("click", () => setMode(button.dataset.mode)));
  // GOVTECH's own "back to simulator" button leaves school mode for training.
  $c("govtech-toggle")?.addEventListener("click", () => {
    setTimeout(() => { if (!window.GOVTECH?.active && S.mode === "school") { S.mode = "training"; syncModeButtons(); } }, 0);
  });
  // R04 announces its map drawing tool; while it is active, Escape cancels the tool, not the cabinet.
  root.addEventListener("civic-editor:tool", (event) => { S.editorTool = !!event.detail?.active; });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || S.mode !== "civic") return;
    // A module that handled Escape itself (confirmation, tool, menu) calls preventDefault.
    if (event.defaultPrevented) return;
    if (!$c("civic-editor").hidden) {
      if (S.editorTool || $c("civic-editor").querySelector("[aria-modal='true'], .civic-r04-confirm-box")) return;
      closeEditor();
    }
    else if (!$c("civic-moderation").hidden) closeModeration();
    else if (!$c("civic-scenarios").hidden) closeScenarios();
    else if (!$c("civic-feedback-box").hidden) closeFeedback();
  });

  function initialMode() {
    const hash = location.hash.replace(/^#/, "");
    if (hash === "training" || hash === "school") return hash;
    if (hash.startsWith("object=")) {
      try { S.selected = decodeURIComponent(hash.slice(7)) || null; } catch { S.selected = null; }
      return "civic";
    }
    try {
      const saved = localStorage.getItem(MODE_KEY);
      if (MODES.includes(saved)) return saved;
    } catch { /* storage may be blocked */ }
    return "civic";
  }

  // map.js calls these hooks; civic is independent of the GOVTECH/district handlers.
  function onMapReady() {
    S.mapState = "ready";
    if (S.mode === "civic") { trainingLayers(false); mountExplore(); civicCamera(); remountAll(); }
    S.started = true;
  }
  function onMapUnavailable() {
    if (S.mapState !== "pending") return;
    S.mapState = "unavailable";
    if (S.mode === "civic" && !S.mounted.map) remountAll();
  }

  window.CivicShell = {
    version: "civic-shell-v1",
    api,
    get active() { return S.mode === "civic"; },
    get mode() { return S.mode; },
    get selected() { return S.selected; },
    get modules() { return S.modules ? JSON.parse(JSON.stringify(S.modules)) : null; },
    isFallback,
    setMode, openEditor, closeEditor, openFeedback, closeFeedback, onMapReady, onMapUnavailable,
    selectObject(id) { S.selected = id; S.mounted.map?.selectObject?.(id); },
    refresh() { S.mounted.map?.refresh?.(); },
  };
  // The overview button frames the city for the civic map instead of the district view.
  $c("overview-map")?.addEventListener("click", (event) => {
    if (S.mode !== "civic") return;
    event.stopImmediatePropagation();
    S.mounted.explore?.reset?.();
    S.mounted.map?.selectObject?.(null);
    S.mounted.map?.setFilters?.({ area: false });
    civicCamera();
  }, true);
  // Start after interface.js has registered its own DOMContentLoaded boot.
  const start = () => {
    setMode(initialMode(), { persist: false });
    if (currentMap()) onMapReady();
    // The HttpOnly session cookie may already be valid (F5, new tab): learn it once on boot.
    void refreshSession().catch(() => null);
  };
  // In-page navigation to #object=<id>, #training or #school (links, back/forward).
  window.addEventListener("hashchange", () => {
    const hash = location.hash.replace(/^#/, "");
    if (hash === "training" || hash === "school" || hash === "civic") { setMode(hash); return; }
    if (!hash.startsWith("object=")) return;
    let id = null;
    try { id = decodeURIComponent(hash.slice(7)) || null; } catch { id = null; }
    // Same id is a no-op only while its card is on screen (S.selected survives other modes).
    if (!id || (id === S.selected && S.mode === "civic")) return;
    S.selected = id;
    if (S.mode !== "civic") setMode("civic");
    else S.mounted.map?.selectObject?.(id);
  });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
