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
  // Тексты (раунд 14): словари R11 через BirgeShell.t, запасной словарь — shell-text.js. Русский — дословно прежний.
  const T = (key, params) => (window.BirgeShell ? window.BirgeShell.t(key, params)
    : window.BirgeShellText ? window.BirgeShellText.text(key, params, "ru") : key);
  // Вид «Акимат / Житель» и язык из шапки Birge (birge.js).
  const birgeMode = () => window.BirgeShell?.mode || "akimat";
  const birgeLang = () => window.BirgeShell?.lang?.() || "ru";
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
      super(message || T("shell.api.failed"));
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
        ? new CivicApiError(0, "timeout", T("shell.api.timeout"))
        : new CivicApiError(0, "network", T("shell.api.network"));
    } finally {
      clearTimeout(timer);
      outer?.removeEventListener("abort", onAbort);
    }
    let envelope = null;
    try { envelope = await response.json(); } catch { envelope = null; }
    if (!envelope || typeof envelope !== "object" || typeof envelope.ok !== "boolean")
      throw new CivicApiError(response.status, "bad_response", T("shell.api.bad_response"));
    if (!envelope.ok || !response.ok) {
      const error = envelope.error && typeof envelope.error === "object" ? envelope.error : {};
      const details = { ...error };
      // Retry-After header (seconds) when the body does not carry retry_after itself.
      const header = Number.parseInt(response.headers.get("Retry-After") || "", 10);
      if (!Number.isInteger(details.retry_after) && Number.isInteger(header)) details.retry_after = header;
      throw new CivicApiError(response.status, String(error.code || "error"),
        typeof error.message === "string" ? error.message : T("shell.api.failed"),
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
      throw new CivicApiError(401, "unauthenticated", T("shell.api.unauthenticated"));
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
        const who = session.user?.name || null;
        await refreshSession().catch(() => null);
        // R04 r13 patch: never re-send a staff POST as a different user (another tab signed in).
        if (session.authenticated && (session.user?.name || null) === who) return request(method, path, body, { ...options, retried: true });
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
    // R06 round 13: drafts and receipt numbers of this tab are dropped on logout.
    logout: () => request("POST", "/session/logout", {}).finally(() => { try { window.CivicFeedback?.clearDrafts?.(); } catch { /* optional module */ } }),
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
  const root = el("section", { id: "civic-root", hidden: true, "data-t-attr": "aria-label:shell.root.label" });
  root.innerHTML = `
    <div id="civic-panel" class="civic-panel" data-sheet="half">
      <button type="button" id="civic-sheet-handle" class="civic-sheet-handle" aria-expanded="false"><i></i></button>
      <div id="civic-state" class="civic-state" role="status" aria-live="polite"></div>
      <div id="civic-scroll" class="civic-scroll">
        <!-- B1: «Карта жалоб» (R07) — главное содержимое панели Birge; ниже — реестр работ раунда 13. -->
        <div id="birge-heat-root" class="civic-slot birge-heat-slot"></div>
        <section class="civic-works" aria-labelledby="civic-works-title">
          <header class="civic-head">
            <span class="eyebrow" data-t="shell.panel.eyebrow"></span>
            <h2 id="civic-works-title" data-t="shell.panel.title"></h2>
            <p id="civic-data-note" class="civic-data-note"></p>
          </header>
          <div id="civic-map-root" class="civic-slot"></div>
        </section>
        <section id="civic-feedback-box" class="civic-box" hidden data-t-attr="aria-label:shell.feedback.label">
          <div class="civic-box-head"><h2 data-t="shell.feedback.title"></h2><button type="button" class="civic-close" data-close="feedback" data-t-attr="aria-label:shell.feedback.close">×</button></div>
          <div id="civic-feedback-root" class="civic-slot"></div>
        </section>
        <section id="civic-assistant-box" class="civic-box" hidden data-t-attr="aria-label:shell.assistant.label">
          <div id="civic-assistant-root" class="civic-slot"></div>
        </section>
      </div>
      <footer class="civic-foot">
        <button type="button" id="civic-staff-button" class="btn" data-t="shell.staff.open"></button>
        <button type="button" id="civic-scenarios-button" class="btn" data-t="shell.scenarios.open"></button>
        <button type="button" id="civic-moderation-button" class="btn" hidden data-t="shell.moderation.open"></button>
      </footer>
    </div>
    <!-- B3: кнопка «Сообщить о проблеме», мастер и тосты R09 (position: fixed) — вне панели: внутри её слоя (z 5)
         мастер на телефоне оказывался под панелью «Территория» (z 6) — UX_REVIEW R11 B1 п. 1. -->
    <div id="birge-complaint-root" class="birge-complaint-root"></div>
    <!-- B2: 3D-превью предложений (R05) — каталог акимата и карточка «За/Против» над картой, слева от панели. -->
    <div id="birge-build3d-root" class="birge-build3d-root"></div>
    <section id="civic-editor" class="civic-drawer" hidden data-t-attr="aria-label:shell.editor.title">
      <div class="civic-box-head"><h2 data-t="shell.editor.title"></h2><button type="button" class="civic-close" data-close="editor" data-t-attr="aria-label:shell.editor.close">×</button></div>
      <div id="civic-editor-root" class="civic-slot civic-drawer-body"></div>
    </section>
    <section id="civic-moderation" class="civic-drawer" hidden data-t-attr="aria-label:shell.moderation.title">
      <div class="civic-box-head"><h2 data-t="shell.moderation.title"></h2><button type="button" class="civic-close" data-close="moderation" data-t-attr="aria-label:shell.moderation.close">×</button></div>
      <div id="civic-moderation-root" class="civic-slot civic-drawer-body"></div>
    </section>
    <section id="civic-scenarios" class="civic-drawer" hidden data-t-attr="aria-label:shell.scenarios.title">
      <div class="civic-box-head"><h2 data-t="shell.scenarios.title"></h2><button type="button" class="civic-close" data-close="scenarios" data-t-attr="aria-label:shell.scenarios.close">×</button></div>
      <p class="civic-note civic-scenario-limits">Сравните два варианта перекрытия на пешеходной сети. Расчёт показывает изменение длины пути; неизвестный доступ исключён. Это гипотеза, не прогноз пробок и не официальное перекрытие.</p>
      <div class="civic-drawer-body">
        <div id="civic-scenarios-root" class="civic-slot"></div>
        <section id="civic-scenario-explain" class="civic-scenario-explain" hidden aria-label="Объяснение расчёта A/B">
          <h3>Объяснение этого расчёта</h3>
          <p class="civic-note">Помощник объясняет результат, который посчитал сервер для показанных вариантов; цифры из браузера не принимаются. Изменили варианты — нажмите «Сравнить» снова.</p>
          <div id="civic-scenario-explain-root"></div>
        </section>
      </div>
      <p class="civic-attribution">© участники OpenStreetMap (ODbL-1.0). Дата и источник — у выбранной сети. Старый срез K03: Overture Maps Foundation, выпуск 2026-09-23.1.</p>
    </section>`;
  document.body.append(root);
  // Порядок Tab: корень формы жалобы R09 стоял в самом конце страницы — после значков карты, шапки, кнопок карты и
  // всей панели (> 40 нажатий, R10 B-025). Ставим его сразу за картой (#map): «Сообщить о проблеме» идёт следом за
  // значками на карте и раньше шапки и панели; с начала страницы — ссылка «Перейти к главной кнопке» (birge.js).
  // Положение на экране не меняется (position: fixed); вне режима civic корень скрыт (birge.css).
  const complaintRootNode = $c("birge-complaint-root");
  if (complaintRootNode && $c("map")) $c("map").after(complaintRootNode);

  // ---------------------------------------------------------------- тексты на языке интерфейса (раунд 14)
  // Строка «Открыта запись: …» на текущем языке.
  function selectedViewText() {
    return S.selectedTitle ? T("shell.view.object", { title: S.selectedTitle }) : T("shell.view.object_untitled");
  }
  // Подписи оболочки ([data-t], [data-t-attr]) и строки состояния; при ҚАЗ/РУС — заново.
  // Модули ролей внутри панели перерисовывают свои тексты сами (BirgeI18n.onChange).
  function relabelShell() {
    for (const node of [root, ...root.querySelectorAll("[data-t-attr]")]) {
      if (!node.dataset?.tAttr) continue;
      for (const pair of node.dataset.tAttr.split(";")) {
        const [attr, key] = pair.split(":");
        node.setAttribute(attr, T(key));
      }
    }
    for (const node of root.querySelectorAll("[data-t]")) node.textContent = T(node.dataset.t);
    const handle = $c("civic-sheet-handle");
    handle?.setAttribute("aria-label", T(S.sheet === "full" ? "shell.sheet.collapse" : "shell.sheet.expand"));
    S.mounted.heat?.setLang?.(birgeLang());
    const build3dRoot = $c("birge-build3d-root");
    if (build3dRoot?.dataset.catalog) setBuild3dCatalog(build3dRoot.dataset.catalog === "open");
    if (S.mode !== "civic") return;
    describeData();
    if (S.selected) S.mounted.explore?.setView?.(selectedViewText(), "object");
    else if (S.view) S.mounted.explore?.setView?.(S.view.render(), S.view.kind);
  }
  relabelShell();
  window.BirgeI18n?.onChange?.(relabelShell);

  // Role modules only (R03 map, R04 editor, R06 feedback, R07 scenarios, R09 assistant). The R01
  // fallbacks used before the deliveries were removed once the modules were integrated: one
  // implementation per function. A missing module is reported, never silently replaced.
  const moduleFor = (name) => ({
    map: window.CivicMap, editor: window.CivicEditor, feedback: window.CivicFeedback,
    scenarios: window.CivicScenarios, assistant: window.CivicAssistant, scenarioAssistant: window.CivicAssistant,
    heat: window.CivicHeat, complaint: window.BirgeComplaint,  // B1: R07, R09 (раунд 14)
  })[name] || null;
  const isFallback = () => false;
  // Нет файла модуля / модуль упал при запуске: без технических слов (UX_BRIEF правило 4); подробности — в консоли.
  const errorLine = (key) => el("p", { class: "civic-error", "data-t": key }, T(key));

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
      const retry = el("button", { type: "button", class: "text-button" }, T("common.action.retry"));
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
      console.warn("civic module not loaded:", name);
      rootNode.replaceChildren(errorLine("shell.module.missing"));
      return null;
    }
    try {
      const handle = module.mount({ root: rootNode, api, ...options });
      S.mounted[name] = handle || {};
      return S.mounted[name];
    } catch (error) {
      console.error("civic mount", name, error);
      rootNode.replaceChildren(errorLine("shell.module.failed"));
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
    if (store === "ready") note.textContent = T("shell.panel.note");
    else note.textContent = "";
    if (!S.modules) stateLine(T("shell.state.no_server"), "error");
    else if (store !== "ready") stateLine(T("shell.state.no_store"), "warn");
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
      onData: (items) => { S.recordCount = items.length; S.mounted.explore?.updateRecords?.(items); refreshAssistantRevision(); },
      onSelect: (item, info) => onSelect(item, info),
      // Proposed R03 option (INTEGRATION.txt): camera padding from the host's live layout. An R03
      // that does not know it ignores it; the shell's fitAll adapter/keepVisible cover that case.
      getPadding: () => freeArea(),
      // R03 round 13 (proposed_r01_shell.patch, CONTRACT.txt): the module frames its camera with the
      // shell's tilt and reports the loaded card's geometry. Older modules ignore these options.
      getPitch: () => intendedPitch(),
      getBearing: () => (intendedPitch() ? intendedBearing() : 0),
      onDetail: (detail) => onDetail(detail),
      onFeedback: (target) => openFeedback(target),
    });
    if (S.selected) S.mounted.map?.selectObject?.(S.selected);
    mountBirgeModules();
  }
  // ---------------------------------------------------------------- модули раунда 14 (B1)
  // Запросы модулей раунда 14 (опция fetch R07 и R05): сотруднику — X-CSRF-Token (R09 требует его для «Взять
  // в работу» и «Исправлено», R06 — для предложений). Id устройства для «Я тоже» (X-Birge-Device, ключ
  // birge.device — общий с формой жалобы R09) R07 @ 306074b ставит сам.
  function birgeFetch(url, init = {}) {
    if (String(init.method || "GET").toUpperCase() === "GET") return fetch(url, init);
    const headers = new Headers(init.headers || {});
    if (session.authenticated && session.csrfToken) headers.set("X-CSRF-Token", session.csrfToken);
    return fetch(url, { ...init, headers, credentials: "same-origin" });
  }
  // Плашки поверх карты, под которыми значкам тепловой карты не место: 3D-каталог R05, кнопка и панель жалобы R09.
  function birgeOverlayRects() {
    const rects = [];
    for (const id of ["birge-build3d-root", "birge-complaint-root"]) {
      for (const el of $c(id)?.children || []) {
        if (!el.getClientRects().length || getComputedStyle(el).visibility === "hidden") continue;
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) rects.push(r);
      }
    }
    return rects;
  }
  // R07 «Карта жалоб» в панели и R09 «Сообщить о проблеме» (кнопка видна только жителю, birge.css).
  function mountBirgeModules() {
    if (!S.mounted.heat && moduleFor("heat")) {
      mount("heat", $c("birge-heat-root"), {
        map: currentMap(), role: birgeMode(), lang: birgeLang(), fetch: birgeFetch,
        // Стартовая подгонка под горячие места — в свободную часть карты (без шапки, панели, кнопок карты).
        fitPadding: () => freeArea(),
        avoidRects: birgeOverlayRects,
        // Ссылку #target=… и событие «Картины дня» разбирает оболочка (переключает раздел) — не модуль.
        hash: false, handleOpenTarget: false,
      });
      openTargetFromLink();
    }
    if (!S.mounted.complaint && moduleFor("complaint")) {
      const m = currentMap(), complaint = window.BirgeComplaint;
      let adapter;
      if (m && typeof complaint.maplibreAdapter === "function") {
        adapter = complaint.maplibreAdapter(m);
        // Пока житель выбирает место, карта записей не открывает свои карточки по нажатию.
        const setPickMode = adapter.setPickMode;
        adapter.setPickMode = (on) => {
          S.mounted.map?.setInteractionEnabled?.(!on, "birge-complaint");
          // Значки тепловой карты (R07) и подписи проектов (R05) — HTML поверх карты: во время выбора места нажатие
          // на них должно дойти до карты, иначе мастер молчит (UX_REVIEW R11 B1 п. 3; birge.css .birge-picking).
          document.body.classList.toggle("birge-picking", !!on);
          return typeof setPickMode === "function" ? setPickMode.call(adapter, on) : undefined;
        };
      }
      // Свой контейнер: модуль ставит туда кнопку, панель и тост (position: fixed).
      try {
        S.mounted.complaint = complaint.mount({ root: $c("birge-complaint-root"), map: adapter, fab: true }) || {};
      } catch (error) {
        console.error("birge complaint mount", error);
      }
    }
    mountBuild3d();
  }
  // ---------------------------------------------------------------- 3D-превью предложений (R05 + R06)
  // R06 @ b42e790 (поставка 2) сам понимает тело клиента R05: year/near_street/target/status, служебные поля
  // игнорирует, отвечает {item, proposal} с полем year — поэтому тело и ответ больше не переводятся.
  // Остаток адаптера нужен только клиенту R05 @ b0353ee (INTEGRATION.txt §10): он снимает предложение через
  // DELETE /proposals/{id} (в CONTRACT §7 и в шлюзе нет — переводим в POST …/withdraw) и не передаёт device_id
  // в список (без него R06 не вернёт my_vote этого устройства). Клиент R05 под R06 поставки 2 делает это сам —
  // тогда build3dFetch убирается целиком.
  const B3D_PROPOSALS = /\/api\/civic\/v2\/proposals$/;
  const B3D_ONE = /\/api\/civic\/v2\/proposals\/[^/]+$/;
  function build3dDevice() {
    try { return localStorage.getItem("birge.device_id"); } catch { return null; }  // ключ R05/R06 (голос «За/Против»)
  }
  function build3dFetch(url, init = {}) {
    const target = new URL(url, location.href);
    let method = String(init.method || "GET").toUpperCase(), body = init.body;
    if (method === "GET" && B3D_PROPOSALS.test(target.pathname) && !target.searchParams.has("device_id")) {
      const device = build3dDevice();
      if (device) target.searchParams.set("device_id", device);  // R06 вернёт my_vote этого устройства
    } else if (method === "DELETE" && B3D_ONE.test(target.pathname)) {
      method = "POST"; target.pathname += "/withdraw"; body = "{}";
    }
    const headers = new Headers(init.headers || {});
    if (body !== undefined) headers.set("Content-Type", "application/json");
    return birgeFetch(target.toString(), { ...init, method, body, headers });
  }
  // Каталог «Что построить?» акимата свёрнут в одну кнопку: открытый постоянно, он закрывал легенду тепловой карты
  // и спорил с главной кнопкой экрана (UX_BRIEF правила 1 и 3). Размещение и карточку проекта R05 показывает всегда —
  // скрывается только сам каталог (birge.css, [data-catalog="closed"]).
  function build3dToggle(root) {
    let button = root.querySelector(".birge-b3d-toggle");
    if (!button) {
      button = el("button", { type: "button", class: "bk-btn birge-b3d-toggle", "aria-expanded": "false" });
      button.addEventListener("click", () => {
        const open = root.dataset.catalog !== "open";
        // Телефон: каталог помещается только над опущенной шторкой — опускаем её сами (R10 B-022).
        if (open && innerWidth < 761 && S.sheet !== "peek") setSheet("peek");
        setBuild3dCatalog(open, { focus: true });
      });
      root.prepend(button);
    }
    return button;
  }
  function setBuild3dCatalog(open, { focus = false } = {}) {
    const root = $c("birge-build3d-root");
    if (!root) return;
    root.dataset.catalog = open ? "open" : "closed";
    const button = build3dToggle(root);
    button.setAttribute("aria-expanded", String(open));
    button.textContent = open ? T("common.action.close") : T("proposal.catalog.title");
    if (open && focus) requestAnimationFrame(() => root.querySelector('.b3d-dock[data-state="catalog"] .b3d-card')?.focus?.({ preventScroll: true }));
  }
  function mountBuild3d() {
    const lib = window.CivicBuild3D, core = window.CivicBuild3DCore, m = currentMap();
    if (S.mounted.build3d || !lib || typeof lib.mount !== "function" || !m) return;
    setBuild3dCatalog(false);
    try {
      S.mounted.build3d = lib.mount({
        map: m, root: $c("birge-build3d-root"), role: birgeMode() === "resident" ? "resident" : "akimat",
        // Хранилище — API R06 через адаптер; нет R06 (404/503) — R05 сам переходит на заглушку этого устройства.
        store: typeof core?.createAutoStore === "function" ? core.createAutoStore({ prefix: "/api/civic/v2", fetch: build3dFetch }) : "auto",
        // Пока акимат ставит объект, щелчок по карте принадлежит R05, а не карточкам карты записей.
        onToolChange: (active) => S.mounted.map?.setInteractionEnabled?.(!active, "birge-build3d"),
      }) || null;
    } catch (error) {
      console.error("birge build3d mount", error);
      S.mounted.build3d = null;
    }
  }
  function remountBuild3d() {
    if (!S.mounted.build3d) return;
    try { S.mounted.build3d.destroy?.(); } catch { /* модуль R05 не ломает оболочку */ }
    S.mounted.map?.setInteractionEnabled?.(true, "birge-build3d");
    S.mounted.build3d = null;
    mountBuild3d();
  }
  // Ссылка «#target=<kind>:<id>&days=N» (R08 «Картина дня», R07): открыть цель на тепловой карте.
  function openTargetFromLink(hash = location.hash) {
    const m = /^#target=([a-z]+):([^&]+)(?:&days=(\d+))?$/.exec(hash || "");
    if (!m || !S.mounted.heat) return false;
    let id = m[2];
    try { id = decodeURIComponent(id); } catch { /* как есть */ }
    // Период — в том же вызове (R07 >= 306074b): один запрос вместо «фильтр, затем цель».
    S.mounted.heat.focusTarget?.(m[1], id, m[3] ? { days: Number(m[3]) } : undefined);
    return true;
  }
  function remountAll() {
    if (S.mode !== "civic") return;
    mountPublic();
  }
  // R03 >= round 13 sends the loaded card (with geometry) here; no second GET /objects/{id} needed.
  function onDetail(detail) {
    if (!detail || detail.id !== S.selected) return;
    if (detail.title) { S.selectedTitle = detail.title; S.mounted.explore?.setView?.(T("shell.view.object", { title: detail.title }), "object"); }
  }
  // Признак модуля карты раунда 13: он сам держит камеру (getPadding/getPitch) и ввод (setInteractionEnabled).
  const r03Camera = () => typeof S.mounted.map?.setInteractionEnabled === "function";

  // A map click belongs to the active tool: R04 drawing (civic-editor:tool) or the open scenario drawer
  // (R07 picks closures/points by clicking the map). R03 does not know these tools, so a click that
  // also hit a public object is undone here; list/card/permalink selections are not affected.
  const mapToolActive = () => S.editorTool || !$c("civic-scenarios").hidden;
  // An R03 with the proposed setInteractive() lock stops selecting/hovering by itself; the undo in
  // onSelect stays as the fallback for R03 versions without it.
  const syncMapInteractive = () => S.mounted.map?.setInteractive?.(!mapToolActive());
  function onSelect(item, info) {
    if (item && info?.source === "map" && mapToolActive()) {
      setTimeout(() => S.mounted.map?.selectObject?.(null), 0);  // not inside R03's own selectObject
      if (!S.toolHintShown) { S.toolHintShown = true; toastSafe(T("shell.tool.click_hint")); }
      return;
    }
    const id = item && typeof item === "object" ? item.id : item;
    S.selected = typeof id === "string" ? id : null;
    // Лента работ раунда 13 в Birge скрыта (birge.css), карточку выбранного на карте объекта работ — показываем.
    document.body.dataset.birgeWorks = S.selected ? "card" : "list";
    if (S.selected && window.CivicExplore && !r03Camera()) {
      // A permalink selects before R03's list has loaded ({id} only): read the public geometry then.
      const id = S.selected;
      const located = item?.geometry ? Promise.resolve(item)
        : request("GET", "/objects/" + encodeURIComponent(id)).then((data) => data?.item || null, () => null);
      located.then((it) => {
        if (S.selected !== id) return;
        if (!item?.title && it?.title) { S.selectedTitle = it.title; S.mounted.explore?.setView?.(T("shell.view.object", { title: it.title }), "object"); }
        const box = it?.geometry ? window.CivicExplore.bounds(it.geometry) : null;
        if (box) keepVisible([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]);
      });
    }
    S.selectedTitle = S.selected ? item?.title || null : null;
    if (S.selected) S.mounted.explore?.setView?.(selectedViewText(), "object");
    else S.mounted.explore?.setView?.(S.view?.render?.() || "", S.view?.kind || "");
    const hash = S.selected ? "#object=" + encodeURIComponent(S.selected) : "";
    if (location.hash !== hash) history.replaceState(null, "", location.pathname + location.search + hash);
    closeFeedback();
    destroyMounted("assistant");
    $c("civic-assistant-box").hidden = true;
    const assistant = moduleFor("assistant");
    const toolsVisible = window.BirgeShell ? window.BirgeShell.toolsVisible : true;
    if (S.selected && assistant && toolsVisible && S.modules?.assistant?.status === "ready") {
      // Mount R09 only for an object confirmed public (permalinks may name drafts/unknown ids).
      const id = S.selected, seq = ++S.assistantSeq;
      request("GET", "/objects/" + encodeURIComponent(id)).then((data) => {
        if (seq !== S.assistantSeq || S.selected !== id || S.mode !== "civic") return;
        $c("civic-assistant-box").hidden = false;
        // R09: the card's revision on screen; an answer built for another revision is not shown.
        // onStale (R09 r13 patch): сервер ответил object_revision_changed — перечитываем карточку,
        // чтобы и карточка, и помощник показывали текущую редакцию.
        mount("assistant", $c("civic-assistant-root"), { objectId: id, revision: revisionOf(data),
          onStale: () => { if (seq === S.assistantSeq && S.selected === id) onSelect({ id }); } });
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
  const revisionOf = (data) => (Number.isInteger(data?.item?.revision) ? data.item.revision : undefined);
  // Data changed (R03 refresh, a publish from the cabinet): the assistant learns the current revision of
  // the open card, so an answer prepared for the previous revision is withdrawn by R09 itself.
  function refreshAssistantRevision() {
    const id = S.selected, handle = S.mounted.assistant;
    if (!id || typeof handle?.update !== "function") return;
    const seq = S.assistantSeq;
    request("GET", "/objects/" + encodeURIComponent(id)).then((data) => {
      if (seq === S.assistantSeq && S.selected === id && S.mounted.assistant === handle) handle.update({ revision: revisionOf(data) });
    }, () => null);
  }
  function openFeedback(target) {
    if (S.modules?.feedback?.status !== "ready") {
      toastSafe(T("shell.feedback.unavailable"));
      return;
    }
    const objectId = target && typeof target === "object" ? (target.objectId ?? target.object_id ?? target.id ?? null) : (typeof target === "string" ? target : null);
    const geometry = target && typeof target === "object" && target.geometry ? target.geometry : null;
    $c("civic-feedback-box").hidden = false;
    mount("feedback", $c("civic-feedback-root"), { objectId, geometry });
    $c("civic-feedback-box").scrollIntoView({ block: "nearest", behavior: motionSafe() ? "smooth" : "auto" });
    if (innerWidth < 761) setSheet("full");
  }
  // R06 round 13: a receipt link (#civic-receipt=fbr_…, fragment never reaches the server) opens the
  // resident's status card: platform status, platform reply and timeline without staff data.
  function openReceiptFromLink() {
    const feedback = window.CivicFeedback;
    if (S.modules?.feedback?.status !== "ready" || typeof feedback?.mountReceipt !== "function") return false;
    if (!feedback.receiptFromLocation?.()) return false;
    destroyMounted("feedback");
    $c("civic-feedback-box").hidden = false;
    S.mounted.feedback = feedback.mountReceipt({ root: $c("civic-feedback-root"), api }) || {};
    if (innerWidth < 761) setSheet("full");
    return true;
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
    // R04 boots with its own GET /session; openObject before that answer shows the login form and
    // gives up. A freshly mounted cabinet opens the object after that /session reply was applied.
    const fresh = !S.mounted.editor;
    const sessionApplied = fresh && objectId ? nextSessionReply(8000) : Promise.resolve();
    const handle = S.mounted.editor || mount("editor", $c("civic-editor-root"), {
      // A getter: a cabinet opened before the map loads is not left with map=null (R04 resolves it).
      map: () => currentMap(),
      onPublished: (item, info) => onEditorPublished(item, info),
    });
    if (objectId && handle?.openObject) {
      sessionApplied.then(async () => {
        if (S.mounted.editor !== handle) return;
        const opened = await handle.openObject(objectId);
        // Still booting (slow /session): one more try once its reply is in.
        if (opened === false && session.authenticated && S.mounted.editor === handle)
          nextSessionReply(4000).then(() => { if (S.mounted.editor === handle) handle.openObject(objectId); });
      });
    }
    $c("civic-editor").querySelector(".civic-close")?.focus();
  }
  // Resolves after the next /session-family reply has been applied by everyone (macrotask later).
  function nextSessionReply(timeoutMs) {
    return new Promise((resolve) => {
      let done = false;
      const finish = () => { if (done) return; done = true; sessionListeners.delete(listener); setTimeout(resolve, 0); };
      const listener = () => finish();
      sessionListeners.add(listener);
      setTimeout(finish, timeoutMs);
    });
  }
  // R04 calls onPublished(publicItem, {action}) for publish, an edit of a published record and archive.
  // Residents are shown only what is public now: an archived (or not published) record is never
  // selected as public; if it was open, its card is closed.
  function onEditorPublished(item, info) {
    S.mounted.map?.refresh?.();
    refreshAssistantRevision();
    const id = typeof item?.id === "string" ? item.id : null;
    if (!id) return;
    const isPublic = info?.action !== "archive" && item.publication === "published";
    if (isPublic) { S.selected = id; S.mounted.map?.selectObject?.(id); }
    else if (S.selected === id) { S.selected = null; S.mounted.map?.selectObject?.(null); }
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
      $c("civic-moderation-root").replaceChildren(errorLine("shell.moderation.failed"));
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
  // R03 answers a click on overlapping objects with its own chooser ("pick") without calling onSelect,
  // so a click made for a tool can leave it open behind the drawer. When the tool ends, a pick view
  // that nobody chose is closed (R03 interaction lock proposed in INTEGRATION.txt).
  function clearToolPick() {
    S.toolHintShown = false;
    syncMapInteractive();
    if (S.mounted.map?.getState?.().view === "pick" && !S.selected) S.mounted.map.selectObject?.(null);
  }
  function closeEditor() {
    S.editorTool = false;
    clearToolPick();
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
    syncMapInteractive();
    // R07 review: the shell's api.request already adds /api/civic/v1 -> empty apiPrefix.
    mount("scenarios", $c("civic-scenarios-root"), { map: currentMap(), apiPrefix: "", api: scenarioApi() });
    watchScenarioResult();
  }
  // R09 x R07 (round 13): R07 has no result callback, so the shell watches the requests it makes through
  // the shell API. A successful server compare is explained by the assistant as scenario_id
  // "result:<result_digest>" (the gateway keeps that server result; the browser sends no numbers).
  // A new compare, or R07 clearing its result after the inputs changed, withdraws the old explanation.
  function scenarioApi() {
    return { ...api, request: async (method, path, body, options) => {
      const compare = String(method).toUpperCase() === "POST" && /\/scenarios\/compare$/.test(path);
      if (compare) explainScenario(null);
      const data = await api.request(method, path, body, options);
      if (compare && typeof data?.result_digest === "string" && /^[0-9a-f]{16,64}$/.test(data.result_digest)) explainScenario(data.result_digest);
      return data;
    } };
  }
  function explainScenario(digest) {
    if (digest === S.scenarioDigest && S.mounted.scenarioAssistant) return;
    S.scenarioDigest = digest || null;
    destroyMounted("scenarioAssistant");
    $c("civic-scenario-explain-root").replaceChildren();
    const ready = !!digest && !!moduleFor("assistant") && S.modules?.assistant?.status === "ready" && !$c("civic-scenarios").hidden;
    $c("civic-scenario-explain").hidden = !ready;
    if (ready) mount("scenarioAssistant", $c("civic-scenario-explain-root"), { objectId: null, scenarioId: "result:" + digest });
  }
  function watchScenarioResult() {
    S.scenarioObserver?.disconnect();
    const out = $c("civic-scenarios-root").querySelector(".civic-r07-result");
    if (!out || typeof MutationObserver !== "function") return;
    S.scenarioObserver = new MutationObserver(() => { if (!out.childElementCount && S.scenarioDigest) explainScenario(null); });
    S.scenarioObserver.observe(out, { childList: true });
  }
  function closeScenarios() {
    S.scenarioObserver?.disconnect(); S.scenarioObserver = null;
    explainScenario(null);
    destroyMounted("scenarios");
    $c("civic-scenarios-root").replaceChildren();
    $c("civic-scenarios").hidden = true;
    clearToolPick();  // after hiding: the map is interactive again
    syncDrawerFlag();
  }
  function setSheet(stateName) {
    S.sheet = ["peek", "half", "full"].includes(stateName) ? stateName : "half";
    $c("civic-panel").dataset.sheet = S.sheet;
    document.body.dataset.civicSheet = S.sheet;
    const handle = $c("civic-sheet-handle");
    handle.setAttribute("aria-expanded", String(S.sheet === "full"));
    handle.setAttribute("aria-label", T(S.sheet === "full" ? "shell.sheet.collapse" : "shell.sheet.expand"));
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
      else pad.right = Math.max(pad.right, c.right - panel.left + 20);  // раунд 14: панель справа (UX_SPEC §1)
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
    if (r03Camera()) return r03.fitAll();  // getPadding/getPitch already passed at mount: no fitBounds swap
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
  // render — функция, дающая строку на текущем языке: при ҚАЗ/РУС строка пересчитывается (relabelShell).
  function showView(render, kind) {
    S.view = { render: typeof render === "function" ? render : () => render, kind };
    if (!S.selected) S.mounted.explore?.setView?.(S.view.render(), kind);
  }
  function civicCamera() {
    const m = currentMap();
    if (!m) return;
    showView(() => T("shell.view.city"), "city");
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
        if (S.recordCount === 0) showView(() => T("shell.view.registry_empty", { label: label() }), kind);
        else showView(() => T(n ? "shell.view.in_frame" : "shell.view.none_in_frame", { label: label(), n }), kind);
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
        const label = () => {
          const key = "district." + feature.properties.id, name = T(key);
          return T("shell.view.district", { name: name !== key ? name : feature.properties.name });
        };
        showView(label, "district");
        reportFrame(label, "district");
        roomy(() => frame(b, 13.7));
      },
      onStreet: (street) => {
        S.mounted.map?.selectObject?.(null);
        S.mounted.map?.setFilters?.({ area: true });
        const label = () => T("shell.view.street", { name: street.name });
        showView(label, "street");
        reportFrame(label, "street");
        roomy(() => frame(street.bbox, 16));
      },
      onObjects: () => {
        S.mounted.explore?.reset?.();
        S.mounted.map?.selectObject?.(null);
        S.mounted.map?.setFilters?.({ area: false });
        roomy(() => {
          if (fitAllObjects()) showView(() => T("shell.view.objects"), "objects");
          else toastSafe(T(S.recordCount === 0 ? "shell.objects.none" : "shell.objects.no_coords"));
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
    // Раунд 14: бренд Birge, подпись и заголовок вкладки на выбранном языке — их ставит birge.js (BirgeShell).
    const birge = window.BirgeShell;
    if (brandTitle) brandTitle.textContent = "Birge";
    if (brandSub) brandSub.textContent = birge ? birge.t("shell.brand.tagline") : "Город и жители вместе";
    document.title = birge ? birge.t("shell.title") : "Birge · Астана";
    $c("map")?.setAttribute("aria-label", birge ? birge.t("shell.map.label") : "Карта Астаны");
    // Возврат кнопкой «Город» из #training/#school: убираем старую ссылку, чтобы F5 открыл карту.
    if (location.hash === "#training" || location.hash === "#school") history.replaceState(null, "", location.pathname + location.search);
    trainingLayers(false);
    mountExplore();
    civicCamera();
    setSheet("half");
    void loadModules().then(() => { mountPublic(); openReceiptFromLink(); });
  }
  function deactivateCivic() {
    placeMapStatus(false);  // before the navigation box (its current parent) is destroyed
    for (const name of Object.keys(S.mounted)) destroyMounted(name);
    S.scenarioObserver?.disconnect(); S.scenarioObserver = null; S.scenarioDigest = null;
    $c("civic-scenario-explain").hidden = true;
    for (const id of ["civic-map-root", "civic-feedback-root", "civic-assistant-root", "civic-editor-root", "civic-moderation-root", "civic-scenarios-root", "civic-scenario-explain-root"])
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
    document.dispatchEvent(new CustomEvent("civic:mode", { detail: { mode } }));  // birge.js перерисует шапку
  }
  document.querySelectorAll("#civic-modes [data-mode]").forEach((button) =>
    button.addEventListener("click", () => setMode(button.dataset.mode)));
  // GOVTECH's own "back to simulator" button leaves school mode for training.
  $c("govtech-toggle")?.addEventListener("click", () => {
    setTimeout(() => { if (!window.GOVTECH?.active && S.mode === "school") { S.mode = "training"; syncModeButtons(); } }, 0);
  });
  // Раунд 14: в виде «Житель» инструменты акимата скрыты (birge.css) — открытые ящики тоже закрываем.
  // B1: «Горячее место» в «Картине дня» (R08) открывает цель здесь, без перезагрузки страницы.
  document.addEventListener("birge:open-target", (event) => {
    const target = event.detail?.target;
    if (!target?.kind || !target?.id || S.mode !== "civic" || !S.mounted.heat) return;
    event.preventDefault();
    window.BirgeShell?.setSection?.("map");
    S.mounted.heat.focusTarget?.(target.kind, target.id, event.detail.days ? { days: Number(event.detail.days) } : undefined);
  });
  document.addEventListener("birge:mode", (event) => {
    S.mounted.heat?.setRole?.(event.detail?.mode);
    remountBuild3d();  // у R05 нет setRole: каталог акимата ↔ только просмотр и голос жителя
    // Вид «Акимат»: панель жителя (форма жалобы, «Мои обращения») закрывается — она перекрыла бы карточку цели.
    if (event.detail?.mode === "akimat") S.mounted.complaint?.close?.();
    if (event.detail?.mode !== "resident") return;
    if (!$c("civic-scenarios").hidden) closeScenarios();
    if (!$c("civic-moderation").hidden) closeModeration();
  });
  // R04 announces its map drawing tool; while it is active, Escape cancels the tool, not the cabinet.
  root.addEventListener("civic-editor:tool", (event) => { S.editorTool = !!event.detail?.active; if (S.editorTool) syncMapInteractive(); else clearToolPick(); });
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
    if (hash.startsWith("civic-receipt=")) return "civic";   // R06 receipt link opens the civic map
    if (hash.startsWith("target=")) return "civic";          // B1: цель тепловой карты (R07/R08)
    if (hash.startsWith("object=")) {
      try { S.selected = decodeURIComponent(hash.slice(7)) || null; } catch { S.selected = null; }
      return "civic";
    }
    // Раунд 14: «Школы» и «Учебная модель» убраны из главного меню — открываются только ссылкой
    // #school / #training. Сохранённый когда-то старый режим больше не открывается сам при запуске.
    return "civic";
  }

  // map.js calls these hooks; civic is independent of the GOVTECH/district handlers.
  function onMapReady() {
    S.mapState = "ready";
    if (S.mode === "civic") { trainingLayers(false); mountExplore(); civicCamera(); remountAll(); }
    S.mounted.editor?.setMap?.(currentMap());  // a cabinet opened before the map gets it now
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
    get mapView() { return S.mounted.map?.getState?.().view || null; },  // R03 view: list | card | pick (read-only)
    get modules() { return S.modules ? JSON.parse(JSON.stringify(S.modules)) : null; },
    // B1: «Мои обращения» жителя (R09) — из шапки Birge.
    openMine() { S.mounted.complaint?.openMine?.(); },
    get heat() { return S.mounted.heat || null; },
    get build3d() { return S.mounted.build3d || null; },  // B2: R05 3D-превью (приёмка R10, проверки R01)
    // Раунд 14: CSRF-токен вошедшего сотрудника для клиента API v2 (birge.js); null, если не вошёл.
    csrfToken() { return session.authenticated ? session.csrfToken : null; },
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
    if (hash.startsWith("civic-receipt=")) { if (S.mode !== "civic") setMode("civic"); else openReceiptFromLink(); return; }
    if (hash.startsWith("target=")) { if (S.mode !== "civic") setMode("civic"); else openTargetFromLink(); return; }
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
