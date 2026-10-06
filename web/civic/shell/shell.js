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
  class CivicApiError extends Error {
    constructor(status, code, message, fields) {
      super(message || "Запрос не выполнен.");
      this.name = "CivicApiError";
      this.status = status;
      this.code = code || "error";
      this.fields = fields || null;
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
      throw new CivicApiError(response.status, String(error.code || "error"),
        typeof error.message === "string" ? error.message : "Запрос не выполнен.",
        error.fields && typeof error.fields === "object" ? error.fields : null);
    }
    return envelope.data;
  }
  async function request(method, path, body, options) {
    method = String(method || "GET").toUpperCase();
    if (method !== "GET" && method !== "POST") throw new CivicApiError(0, "bad_method", "Метод не поддерживается.");
    checkPath(path);
    // The public map never needs staff data: refuse /staff calls without a session.
    if (path.startsWith("/staff") && session.checked && !session.authenticated)
      throw new CivicApiError(401, "unauthenticated", "Войдите как сотрудник, чтобы продолжить.");
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
    if (path === "/session" || path === "/session/login" || path === "/session/logout") applySession(data);
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
  const S = { mode: null, mapState: "pending", modules: null, mounted: {}, selected: null,
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
      </footer>
    </div>
    <section id="civic-editor" class="civic-drawer" hidden aria-label="Кабинет сотрудника">
      <div class="civic-box-head"><h2>Кабинет сотрудника</h2><button type="button" class="civic-close" data-close="editor" aria-label="Закрыть кабинет">×</button></div>
      <div id="civic-staff-tabs" class="civic-tabs" role="group" aria-label="Разделы кабинета" hidden>
        <button type="button" data-staff-tab="records" aria-pressed="true">Записи</button><button type="button" data-staff-tab="messages" aria-pressed="false">Сообщения жителей</button>
      </div>
      <div id="civic-editor-root" class="civic-slot civic-drawer-body"></div>
      <div id="civic-moderation-root" class="civic-slot civic-drawer-body" hidden></div>
    </section>
    <section id="civic-scenarios" class="civic-drawer" hidden aria-label="Сравнение ограничений">
      <div class="civic-box-head"><h2>Сравнение ограничений</h2><button type="button" class="civic-close" data-close="scenarios" aria-label="Закрыть сравнение">×</button></div>
      <p class="civic-note civic-scenario-limits">Модель для гипотез, не официальное перекрытие. Только пешеходный граф (участок центра), только длина пути в метрах: без времени в пути, пробок и выбросов. Автомобильный граф не подтверждён. Рёбра с неизвестным доступом не считаются открытыми.</p>
      <div id="civic-scenarios-root" class="civic-slot civic-drawer-body"></div>
      <p class="civic-attribution">Граф: © участники OpenStreetMap (ODbL-1.0); Overture Maps Foundation, выпуск 2026-09-23.1. Синтетический граф помечен «СИНТЕТИКА».</p>
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
  }

  function mountPublic() {
    if (S.mode !== "civic") return;
    describeData();
    // Wait for the map (or its definitive failure) so layers attach to the one instance.
    if (S.mapState === "pending" || !S.modules) return;
    if (S.modules?.store?.status !== "ready") { destroyMounted("map"); $c("civic-map-root").replaceChildren(); return; }
    mount("map", $c("civic-map-root"), {
      map: currentMap(),
      fitOnLoad: !S.selected,  // R03 option: frame published objects (city overview otherwise too far out)
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
    const hash = S.selected ? "#object=" + encodeURIComponent(S.selected) : "";
    if (location.hash !== hash) history.replaceState(null, "", location.pathname + location.search + hash);
    closeFeedback();
    const assistant = moduleFor("assistant");
    if (S.selected && assistant && S.modules?.assistant?.status === "ready") {
      $c("civic-assistant-box").hidden = false;
      mount("assistant", $c("civic-assistant-root"), { objectId: S.selected });
    } else {
      destroyMounted("assistant");
      $c("civic-assistant-box").hidden = true;
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
    $c("civic-editor").hidden = false;
    document.body.classList.add("civic-editor-open");
    const handle = S.mounted.editor || mount("editor", $c("civic-editor-root"), {
      map: currentMap(),
      onPublished: (item) => {
        S.mounted.map?.refresh?.();
        if (item?.id) { S.selected = item.id; S.mounted.map?.selectObject?.(item.id); }
      },
    });
    if (objectId && handle?.openObject) handle.openObject(objectId);
    syncStaffTabs();
    setStaffTab(S.staffTab || "records");
    $c("civic-editor").querySelector(".civic-close")?.focus();
  }
  // Resident messages (R06 mountModeration) live next to the records in the staff drawer.
  const moderationReady = () => S.modules?.feedback?.status === "ready" && typeof window.CivicFeedback?.mountModeration === "function";
  function syncStaffTabs() {
    const tabs = $c("civic-staff-tabs");
    tabs.hidden = !(moderationReady() && session.authenticated);
    if (tabs.hidden && S.staffTab === "messages") setStaffTab("records");
  }
  function setStaffTab(tab) {
    S.staffTab = tab === "messages" && moderationReady() ? "messages" : "records";
    document.querySelectorAll("#civic-staff-tabs [data-staff-tab]").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.staffTab === S.staffTab)));
    $c("civic-editor-root").hidden = S.staffTab !== "records";
    $c("civic-moderation-root").hidden = S.staffTab !== "messages";
    if (S.staffTab === "messages") {
      if (!S.mounted.moderation) {
        const module = window.CivicFeedback;
        try {
          S.mounted.moderation = module.mountModeration({ root: $c("civic-moderation-root"), api, map: currentMap(),
            onOpenObject: (id) => { setStaffTab("records"); S.mounted.editor?.openObject?.(id); } }) || {};
        } catch (error) {
          console.error("civic moderation", error);
          $c("civic-moderation-root").replaceChildren(el("p", { class: "civic-error" }, "Очередь сообщений не запустилась."));
        }
      } else S.mounted.moderation.refresh?.();
    }
  }
  document.querySelectorAll("#civic-staff-tabs [data-staff-tab]").forEach((b) =>
    b.addEventListener("click", () => setStaffTab(b.dataset.staffTab)));
  sessionListeners.add(() => {
    syncStaffTabs();
    if (!session.authenticated && S.mounted.moderation) {
      destroyMounted("moderation");
      $c("civic-moderation-root").replaceChildren();
    }
  });
  function closeEditor() {
    destroyMounted("editor");
    destroyMounted("moderation");
    $c("civic-moderation-root").replaceChildren();
    S.staffTab = "records";
    $c("civic-editor").hidden = true;
    document.body.classList.remove("civic-editor-open");
    $c("civic-staff-button").focus();
  }
  function openScenarios() {
    $c("civic-scenarios").hidden = false;
    // R07 review: the shell's api.request already adds /api/civic/v1 -> empty apiPrefix.
    mount("scenarios", $c("civic-scenarios-root"), { map: currentMap(), apiPrefix: "" });
  }
  function closeScenarios() {
    destroyMounted("scenarios");
    $c("civic-scenarios-root").replaceChildren();
    $c("civic-scenarios").hidden = true;
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
    ({ feedback: closeFeedback, editor: closeEditor, scenarios: closeScenarios })[close.dataset.close]?.();
  });
  $c("civic-staff-button").addEventListener("click", () => openEditor());
  $c("civic-scenarios-button").addEventListener("click", openScenarios);
  $c("civic-sheet-handle").addEventListener("click", () => setSheet(S.sheet === "full" ? "half" : "full"));

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
  function civicCamera() {
    const m = currentMap();
    if (!m) return;
    const mobile = innerWidth < 761;
    const padding = mobile ? { top: 90, left: 20, right: 60, bottom: Math.round(innerHeight * 0.48) }
      : { top: 120, left: 470, right: 90, bottom: 60 };
    try {
      const bounds = typeof cityBounds === "function" ? cityBounds() : null;
      if (bounds) m.fitBounds(bounds, { padding, maxZoom: 12.2, pitch: state?.threeD ? 45 : 0,
        bearing: state?.threeD ? -14 : 0, duration: S.started ? 700 * (motionSafe() ? 1 : 0) : 0 });
    } catch (error) { console.warn("civic camera", error); }
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
    civicCamera();
    setSheet("half");
    void loadModules().then(() => mountPublic());
  }
  function deactivateCivic() {
    for (const name of Object.keys(S.mounted)) destroyMounted(name);
    for (const id of ["civic-map-root", "civic-feedback-root", "civic-assistant-root", "civic-editor-root", "civic-moderation-root", "civic-scenarios-root"])
      $c(id).replaceChildren();
    $c("civic-feedback-box").hidden = $c("civic-assistant-box").hidden = true;
    $c("civic-editor").hidden = $c("civic-scenarios").hidden = true;
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
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || S.mode !== "civic") return;
    if (!$c("civic-editor").hidden) closeEditor();
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
    if (S.mode === "civic") { trainingLayers(false); civicCamera(); remountAll(); }
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
    civicCamera();
  }, true);
  // Start after interface.js has registered its own DOMContentLoaded boot.
  const start = () => {
    setMode(initialMode(), { persist: false });
    if (currentMap()) onMapReady();
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
