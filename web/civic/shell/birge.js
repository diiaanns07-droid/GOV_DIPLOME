/*
 * Birge · шапка и общие настройки оболочки (R01, раунд 14).
 *
 * Что делает этот файл:
 *  - шапка: логотип Birge, разделы «Карта | Картина дня», «Акимат | Житель», «ҚАЗ | РУС» (UX_SPEC R11 §1);
 *  - язык — через BirgeI18n (R11, web/civic/i18n/). Ключа ещё нет в словаре R11 — берём запасной текст
 *    из shell-text.js (ключи переданы R11 в research/round-14-results/R01/INTEGRATION.txt);
 *  - режим «Акимат / Житель»: body[data-birge-mode], событие document "birge:mode", выбор запоминается;
 *  - раздел «Картина дня»: модуль R08 (window.BirgeAkim.mount), пока его нет — понятное «скоро будет»;
 *  - клиент API v2 для модулей: BirgeShell.api.v2(method, path, body).
 *
 * Карта, карточки, жалобы и редактор остаются в shell.js (раунд 13) — этот файл их не трогает.
 */
(function () {
  "use strict";

  const MODE_KEY = "birge.mode";            // akimat | resident (выбор запоминается в этом браузере)
  const MODES = ["akimat", "resident"];
  // Меню по виду (POLISH_WAVE_2, «Защита интерфейса от перегруза», п. 2): не больше 5 пунктов, редкое — в «Ещё».
  // «mine» — не экран, а окно «Мои обращения» модуля R09 поверх карты (как раньше).
  const NAV = {
    resident: ["map", "mine", "nearby", "ideas", "more"],
    akimat: ["map", "day", "complaints", "projects", "more"],
  };
  // Экраны новых разделов (п. 2: свои экраны, не поверх карты). Модуль роли: window[global].mount(root, опции) →
  // {destroy?, setLang?}. Пункт меню виден, только когда модуль подключён; ?screens=all — показать все (разбор R11/R10).
  // modes — в каких видах раздел есть; пункт, которого нет в NAV этого вида, попадает в «Ещё».
  const SCREENS = {
    complaints: { global: ["BirgeComplaintList"], modes: ["akimat"], owner: "R09" },
    projects: { global: ["BirgeProjects", "BirgeIdeas"], modes: ["akimat"], owner: "R06 + R05" },
    nearby: { global: ["BirgeNearby"], modes: ["resident", "akimat"], owner: "R08 + R06" },
    ideas: { global: ["BirgeIdeas"], modes: ["resident"], owner: "R06 + R05" },
    ask: { global: ["BirgeAsk"], modes: ["resident", "akimat"], owner: "R13" },
  };
  const SECTIONS = ["map", "day", "more", ...Object.keys(SCREENS)];
  const PHONE = 761;                         // как в shell.js: уже 761 px — телефонная схема
  // Кнопки карты из web/index.html и их ключи перевода (словари R11, shell.map.*).
  const MAP_BUTTONS = [["overview-map", "shell.map.fit_city"], ["zoom-in", "shell.map.zoom_in"],
    ["zoom-out", "shell.map.zoom_out"], ["toggle-3d", "shell.map.view3d"], ["rotate-map", "shell.map.rotate"]];

  // Тексты: сначала словари R11 (BirgeI18n), затем запасной словарь оболочки (shell-text.js, ru + kk).
  const i18n = () => window.BirgeI18n || null;
  const lang = () => (i18n() && typeof i18n().getLang === "function" ? i18n().getLang() : "ru");
  function t(key, params) {
    const I = i18n();
    if (I && typeof I.has === "function" && I.has(key)) return I.t(key, params);
    const T = window.BirgeShellText;
    return T ? T.text(key, params, lang()) : key;
  }

  // ------------------------------------------------------------------ API v2
  // Тот же адрес сервера, JSON, без cookies третьих сайтов. CSRF-токен сотрудника берётся из оболочки
  // раунда 13 (CivicShell.api.session), если сотрудник вошёл: шлюз требует его для маршрутов [С].
  class BirgeApiError extends Error {
    constructor(status, body) {
      super((body && body.message) || "request failed");
      this.status = status;
      this.error = (body && body.error) || "network";
      this.module = body && body.module;
      this.field = body && body.field;
    }
  }
  async function v2(method, path, body) {
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const csrf = window.CivicShell && window.CivicShell.csrfToken ? window.CivicShell.csrfToken() : null;
    if (csrf && method !== "GET") headers["X-CSRF-Token"] = csrf;
    let response;
    try {
      response = await fetch("/api/civic/v2" + path, {
        method, headers, credentials: "same-origin",
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (e) {
      throw new BirgeApiError(0, { error: "network" });   // нет связи: модули показывают «Нет связи. Повторить»
    }
    // Пустое тело — null; оборванное (страница перезагружается, связь пропала) или не-JSON при 2xx — та же ошибка
    // «нет связи», что и у fetch: иначе модули получали null и писали «неверный ответ» (R05 bad_response в r14_shell).
    let text = "";
    try { text = await response.text(); } catch (e) { throw new BirgeApiError(0, { error: "network" }); }
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch (e) {
        if (response.ok) throw new BirgeApiError(0, { error: "network" });
        data = null;
      }
    }
    if (!response.ok) throw new BirgeApiError(response.status, data);
    return data;
  }

  // ------------------------------------------------------------------ состояние
  const state = { mode: null, section: "map", dayHandle: null, screenHandle: null, extra: [], layers: [], layer: null };
  const screensAll = () => /[?&]screens=all(&|$)/.test(location.search);

  function savedMode() {
    try { const v = localStorage.getItem(MODE_KEY); return MODES.includes(v) ? v : null; } catch (e) { return null; }
  }
  // По умолчанию: ноутбук — акимат (главный зритель демо), телефон — житель.
  function defaultMode() { return innerWidth < PHONE ? "resident" : "akimat"; }

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === false || v == null) continue;
      if (k === "text") node.textContent = v; else node.setAttribute(k, v === true ? "" : v);
    }
    for (const child of children || []) node.append(child);
    return node;
  }
  function segButton(group, value, pressed) {
    return el("button", { type: "button", class: "bk-seg__btn", ["data-" + group]: value, "aria-pressed": String(pressed) });
  }

  // ------------------------------------------------------------------ разделы
  // Модуль экрана: первый подключённый из SCREENS[id].global или зарегистрированный через registerScreen.
  function screenModule(id) {
    const extra = state.extra.find((x) => x.id === id);
    if (extra) return extra;
    for (const name of SCREENS[id]?.global || []) {
      const mod = window[name];
      if (mod && typeof mod.mount === "function") return mod;
    }
    return null;
  }
  const screenModes = (id) => SCREENS[id]?.modes || state.extra.find((x) => x.id === id)?.modes || MODES;
  // Есть ли раздел в этом виде: «Карта» и «Мои обращения»/«Картина дня» — всегда; новый экран — когда модуль подключён.
  function available(id, mode) {
    if (id === "map") return true;
    if (id === "mine") return mode === "resident";
    if (id === "day") return mode === "akimat";
    if (id === "more") return moreItems(mode).length > 0;
    if (!screenModes(id).includes(mode)) return false;
    return screensAll() || !!screenModule(id) || !!state.extra.find((x) => x.id === id && x.href);
  }
  // «Ещё»: разделы этого вида, которых нет в его главном меню (п. 2: «Вопрос акиму» и прочее редкое).
  function moreItems(mode) {
    const ids = [...Object.keys(SCREENS), ...state.extra.map((x) => x.id)];
    return ids.filter((id, i) => ids.indexOf(id) === i && !NAV[mode].includes(id) && id !== "more" && available(id, mode));
  }
  const navTitle = (id) => {
    const extra = state.extra.find((x) => x.id === id);
    if (extra?.titleKey) return t(extra.titleKey);
    if (extra?.title) return extra.title[lang()] || extra.title.ru || id;
    return t("common.nav." + id);  // известный раздел (SCREENS) — ключ меню, даже если модуль зарегистрирован
  };
  // Кнопки меню: порядок — NAV текущего вида; кнопки другого вида остаются в DOM скрытыми (проверки R11 нажимают
  // [data-section=day] из кода и в виде «Житель» — оболочка сама переключит вид).
  function buildNav() {
    const nav = header?.querySelector(".birge-nav");
    if (!nav) return;
    const order = [...NAV[state.mode], ...NAV[state.mode === "akimat" ? "resident" : "akimat"]];
    const ids = order.filter((id, i) => order.indexOf(id) === i);
    const have = new Map([...nav.children].map((b) => [b.dataset.section || b.dataset.action, b]));
    const buttons = ids.map((id) => {
      let b = have.get(id);
      if (!b) {
        b = id === "mine"
          ? el("button", { type: "button", class: "bk-seg__btn birge-mine-btn", "data-action": "mine", "aria-pressed": "false" })
          : segButton("section", id, id === state.section);
      }
      b.hidden = !NAV[state.mode].includes(id) || !available(id, state.mode);
      return b;
    });
    nav.replaceChildren(...buttons);
  }

  // ------------------------------------------------------------------ шапка
  let header = null;
  function buildHeader() {
    const actions = document.querySelector(".topbar .top-actions");
    if (!actions || document.getElementById("birge-header")) return;
    // На телефоне разделы и «Акимат / Житель» уходят в меню ≡ (UX_SPEC §1), ҚАЗ/РУС видны всегда.
    // На ноутбуке .birge-menu — display: contents, кнопка меню скрыта (birge.css).
    const menuButton = el("button", { type: "button", class: "bk-btn birge-menu-btn", "aria-expanded": "false",
      "aria-controls": "birge-menu" });
    menuButton.innerHTML = '<svg class="ic" aria-hidden="true"><use href="/civic/ui-kit/icons.svg#i-menu"></use></svg><span></span>';
    header = el("div", { id: "birge-header", class: "birge-header bk-app" }, [
      menuButton,
      el("div", { id: "birge-menu", class: "birge-menu" }, [
        // Пункты меню обоих видов; чужие для текущего вида и разделы без модуля скрыты (renderNav).
        el("div", { class: "bk-seg birge-nav", role: "group", "data-group": "section" }),
        el("div", { class: "bk-seg birge-role", role: "group", "data-group": "mode" },
          MODES.map((m) => segButton("mode", m, m === state.mode))),
      ]),
      el("div", { class: "bk-seg birge-lang", role: "group", "data-group": "lang" },
        ["kk", "ru"].map((l) => segButton("lang", l, l === lang()))),
    ]);
    actions.prepend(header);
    buildNav();
    header.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button || !header.contains(button)) return;
      if (button === menuButton) { setMenu(header.dataset.menu !== "open"); return; }
      if (button.dataset.action === "mine") { setSection("map"); setMenu(false); window.CivicShell?.openMine?.(); return; }
      if (button.dataset.section) setSection(button.dataset.section);
      else if (button.dataset.mode) setMode(button.dataset.mode);
      else if (button.dataset.lang && i18n()) i18n().setLang(button.dataset.lang);
      if (!button.dataset.lang) setMenu(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && header.dataset.menu === "open") { setMenu(false); menuButton.focus(); }
    });
    document.addEventListener("click", (event) => {
      if (header.dataset.menu === "open" && !header.contains(event.target)) setMenu(false);
    });
  }
  // Первая точка Tab — «Перейти к главной кнопке» (ui-kit .bk-skip, ключ R11): житель — «Сообщить о проблеме» (R09),
  // акимат — «Карта жалоб» (R07) в панели. Без неё до главной кнопки было > 40 нажатий Tab (R10 B-025, LOCAL_B2 №7).
  let skip = null;
  function buildSkip() {
    if (skip || !document.body) return;
    skip = el("a", { class: "bk-skip birge-skip", href: "#birge-main" });
    skip.addEventListener("click", (event) => {
      event.preventDefault();
      const fab = document.querySelector(".bc-fab");
      const target = state.section === "day" ? document.getElementById("birge-day-title")
        : state.section !== "map" ? document.getElementById("birge-screen-title")
        : state.mode === "resident" && fab && getComputedStyle(fab).display !== "none" ? fab
        : document.querySelector("#birge-heat-root button, #birge-heat-root [tabindex], #birge-heat-root a[href]");
      if (target) target.focus();
    });
    document.body.prepend(skip);
  }
  function setMenu(open) {
    if (!header) return;
    header.dataset.menu = open ? "open" : "closed";
    document.body.dataset.birgeMenu = open ? "open" : "closed";  // birge.css поднимает шапку над панелями карты
    header.querySelector(".birge-menu-btn").setAttribute("aria-expanded", String(open));
  }

  function render() {
    if (skip) skip.textContent = t("common.action.skip_to_main");
    if (header) {
      header.querySelector(".birge-nav").setAttribute("aria-label", t("shell.nav.label"));
      header.querySelector(".birge-role").setAttribute("aria-label", t("common.role.label"));
      header.querySelector(".birge-lang").setAttribute("aria-label", t("common.lang.label"));
      const menuLabel = header.querySelector(".birge-menu-btn span");
      if (menuLabel) menuLabel.textContent = t("common.nav.menu");
      buildNav();
      const mine = header.querySelector(".birge-mine-btn");
      if (mine) mine.textContent = t("common.nav.mine");
      for (const b of header.querySelectorAll("[data-section]")) {
        b.textContent = navTitle(b.dataset.section);
        // «Ещё» подсвечен и на экранах, открытых из него.
        const current = b.dataset.section === state.section
          || (b.dataset.section === "more" && moreItems(state.mode).includes(state.section));
        b.setAttribute("aria-pressed", String(current));
      }
      for (const b of header.querySelectorAll("[data-mode]")) {
        b.textContent = t("common.role." + b.dataset.mode);
        b.setAttribute("aria-pressed", String(b.dataset.mode === state.mode));
      }
      for (const b of header.querySelectorAll("[data-lang]")) {
        b.textContent = t("common.lang." + b.dataset.lang);
        b.setAttribute("aria-pressed", String(b.dataset.lang === lang()));
        b.setAttribute("lang", b.dataset.lang);
      }
    }
    if (document.body.classList.contains("civic-mode")) {
      const title = document.querySelector(".brand-title");
      const sub = document.querySelector(".brand-sub");
      if (title) title.textContent = "Birge";
      if (sub) sub.textContent = t("shell.brand.tagline");
      document.title = t("shell.title");
      document.getElementById("map")?.setAttribute("aria-label", t("shell.map.label"));
      // Кнопки карты (web/index.html) и плашка запасного фона (web/map.js) — на языке страницы (UX_REVIEW R11 B1 п. 5–6).
      for (const [id, key] of MAP_BUTTONS) {
        const button = document.getElementById(id);
        if (button) { button.setAttribute("aria-label", t(key)); button.title = t(key); }
      }
      const status = document.getElementById("map-status");
      if (status && document.body.classList.contains("offline-basemap")) status.textContent = t("shell.map.basemap_offline");
    }
    renderDay();
    renderScreen();
    renderLayers();
    requestAnimationFrame(placeExplore);  // длина меню и языка меняет место для панели в шапке
  }

  // ------------------------------------------------------------------ режим
  function setMode(mode, options) {
    if (!MODES.includes(mode)) mode = defaultMode();
    const changed = state.mode !== mode;
    state.mode = mode;
    document.body.dataset.birgeMode = mode;
    if (options?.persist !== false) { try { localStorage.setItem(MODE_KEY, mode); } catch (e) { /* только удобство */ } }
    // Раздел, которого нет в новом виде (например, «Идеи» у акимата), — назад на карту.
    if (changed && state.section !== "map" && state.section !== "day" && !available(state.section, mode)) setSection("map");
    if (changed && state.layer && !state.layers.find((l) => l.id === state.layer)?.modes.includes(mode)) setLayer(null);
    render();
    if (changed) document.dispatchEvent(new CustomEvent("birge:mode", { detail: { mode } }));
  }

  // ------------------------------------------------------------------ «Картина дня»
  let day = null;
  function buildDay() {
    if (document.getElementById("birge-day")) return;
    day = el("section", { id: "birge-day", class: "birge-day bk-app", hidden: true, "aria-labelledby": "birge-day-title" }, [
      el("h1", { id: "birge-day-title", class: "birge-day-title" }),
      el("div", { id: "birge-day-root", class: "birge-day-root" }),
    ]);
    document.body.append(day);
  }
  function emptyDay(kind) {
    // Состояния по UX_BRIEF правило 7: «пока пусто» с подсказкой или ошибка с действием — не белый экран.
    const box = el("div", { class: kind === "error" ? "bk-error birge-day-empty" : "bk-empty birge-day-empty" }, [
      el("h2", { class: "bk-empty__title", text: t(kind === "error" ? "shell.day.error_title" : "shell.day.soon_title") }),
      el("p", { class: "bk-empty__text", text: t(kind === "error" ? "shell.day.error_text" : "shell.day.soon_text") }),
    ]);
    const back = el("button", { type: "button", class: "bk-btn bk-btn--primary", text: t("shell.day.back") });
    back.addEventListener("click", () => setSection("map"));
    box.append(back);
    return box;
  }
  function renderDay() {
    if (!day) return;
    day.querySelector("#birge-day-title").textContent = t("akim.title");
    const root = day.querySelector("#birge-day-root");
    if (state.section !== "day") return;
    const akim = window.BirgeAkim;
    if (akim && typeof akim.mount === "function") {
      if (!state.dayHandle) {
        try {
          // R08 @ 9f1d9c0: mount(элемент, опции); адрес страницы меняет оболочка, не модуль (syncUrl: false).
          state.dayHandle = akim.mount(root, { apiBase: "/api/civic/v2", mapHref: "/#target={kind}:{id}&days={days}",
            syncUrl: false, titleTag: "h2" }) || {};  // R08 4д: свой h1 у оболочки, заголовок модуля — h2
          day.classList.add("birge-day--module");  // у модуля свой заголовок с датой — наш остаётся только для чтения с экрана
        } catch (e) {
          console.error(e);
          state.dayHandle = null;
          root.replaceChildren(emptyDay("error"));
        }
      }
      return;
    }
    root.replaceChildren(emptyDay("soon"));
  }
  // ------------------------------------------------------------------ экраны разделов (волна 2)
  // Один контейнер на все новые разделы: заголовок оболочки + место модуля роли. Карта под ним живая (как у «Картины дня»).
  let screen = null;
  function buildScreen() {
    if (document.getElementById("birge-screen")) return;
    screen = el("section", { id: "birge-screen", class: "birge-day birge-screen bk-app", hidden: true, "aria-labelledby": "birge-screen-title" }, [
      el("h1", { id: "birge-screen-title", class: "birge-day-title", tabindex: "-1" }),
      el("div", { id: "birge-screen-root", class: "birge-day-root birge-screen-root" }),
    ]);
    document.body.append(screen);
  }
  function emptyScreen(kind) {
    const box = el("div", { class: kind === "error" ? "bk-error birge-day-empty" : "bk-empty birge-day-empty" }, [
      el("h2", { class: "bk-empty__title", text: t(kind === "error" ? "shell.screen.error_title" : "shell.screen.soon_title") }),
      el("p", { class: "bk-empty__text", text: t(kind === "error" ? "shell.screen.error_text" : "shell.screen.soon_text") }),
    ]);
    const back = el("button", { type: "button", class: "bk-btn bk-btn--primary", text: t("shell.day.back") });
    back.addEventListener("click", () => setSection("map"));
    box.append(back);
    return box;
  }
  function destroyScreen() {
    if (state.screenHandle) {
      try { state.screenHandle.destroy?.(); } catch (e) { /* модуль роли не ломает оболочку */ }
    }
    state.screenHandle = null;
    screen?.classList.remove("birge-day--module");
    screen?.querySelector("#birge-screen-root")?.replaceChildren();
    if (screen) screen.dataset.screen = "";
  }
  // Опции модулю экрана (контракт — INTEGRATION.txt §11): тот же клиент API, язык, вид; переходы делает оболочка.
  function screenOptions(id) {
    return {
      api: { v2, ApiError: BirgeApiError }, apiBase: "/api/civic/v2", lang: lang(), role: state.mode, section: id,
      titleTag: "h2", syncUrl: false, t,
      // Показать цель на карте (карточка R07): оболочка переключает раздел и ставит #target=… (как «Картина дня»).
      openTarget: (kind, targetId, days) => {
        setSection("map");
        location.hash = "#target=" + encodeURIComponent(kind) + ":" + encodeURIComponent(targetId) + (days ? "&days=" + days : "");
      },
      openSection: (other) => setSection(other),
      close: () => setSection("map"),
    };
  }
  function renderMore(root) {
    const list = el("ul", { class: "birge-more-list" });
    for (const id of moreItems(state.mode)) {
      const extra = state.extra.find((x) => x.id === id);
      const item = extra?.href
        ? el("a", { class: "bk-btn birge-more-item", href: extra.href, target: extra.target || null, rel: extra.target ? "noopener" : null, text: navTitle(id) })
        : el("button", { type: "button", class: "bk-btn birge-more-item", "data-section": id, text: navTitle(id) });
      if (!extra?.href) item.addEventListener("click", () => setSection(id));
      list.append(el("li", {}, [item]));
    }
    root.replaceChildren(list);
  }
  function renderScreen() {
    if (!screen) return;
    const id = state.section;
    if (id === "map" || id === "day") return;
    screen.querySelector("#birge-screen-title").textContent = id === "more" ? t("common.nav.more") : navTitle(id);
    const root = screen.querySelector("#birge-screen-root");
    if (id === "more") { screen.dataset.screen = "more"; renderMore(root); return; }
    if (state.screenHandle && screen.dataset.screen === id) {
      try { state.screenHandle.setLang?.(lang()); } catch (e) { /* язык модуль может менять сам по birge:lang */ }
      return;
    }
    destroyScreen();
    screen.dataset.screen = id;
    const mod = screenModule(id);
    if (!mod) { root.replaceChildren(emptyScreen("soon")); return; }
    try {
      state.screenHandle = mod.mount(root, screenOptions(id)) || {};
      screen.classList.add("birge-day--module");  // у модуля свой заголовок; наш — для чтения с экрана
    } catch (e) {
      console.error("birge screen " + id, e);
      state.screenHandle = null;
      root.replaceChildren(emptyScreen("error"));
    }
  }
  // Роли без правки оболочки: BirgeShell.registerScreen({id, mount, modes, titleKey | title:{ru,kk}}) — экран в «Ещё»;
  // {id, href, modes, titleKey} — ссылка в «Ещё» (например, листы QR для печати, R12 web/civic/qr/).
  function registerScreen(spec) {
    if (!spec || !/^[a-z][a-z0-9-]{1,30}$/.test(spec.id || "") || ["map", "day", "more", "mine"].includes(spec.id)) return false;
    if (!spec.href && typeof spec.mount !== "function") return false;
    if (SCREENS[spec.id]) {  // известный раздел: модуль регистрируется вместо глобального имени
      state.extra = state.extra.filter((x) => x.id !== spec.id).concat([{ ...spec, modes: SCREENS[spec.id].modes }]);
    } else {
      state.extra = state.extra.filter((x) => x.id !== spec.id).concat([{ ...spec, modes: (spec.modes || MODES).filter((m) => MODES.includes(m)) }]);
      if (!SECTIONS.includes(spec.id)) SECTIONS.push(spec.id);
    }
    render();
    return true;
  }

  // ------------------------------------------------------------------ «Территория» и поиск в шапке (читаемость п. 3)
  // Ноутбук (≥ 1024 px): панель района и поиска улицы встаёт в шапку между логотипом и меню, если там ≥ 300 px —
  // карта свободна от панели. Места мало (узкий экран, длинное меню) или телефон — панель остаётся на карте, как была.
  function placeExplore() {
    const box = document.querySelector(".civic-explore"), brand = document.querySelector(".topbar .brand");
    const civic = document.body.classList.contains("civic-mode");
    if (!box || !brand || !header || !civic || innerWidth < 1024) { document.body.dataset.birgeExplore = "map"; return; }
    const bar = brand.closest(".topbar").getBoundingClientRect();
    const left = brand.getBoundingClientRect().right + 16, right = header.getBoundingClientRect().left - 16;
    if (right - left < 300) { document.body.dataset.birgeExplore = "map"; return; }
    document.body.dataset.birgeExplore = "header";
    box.style.setProperty("--be-left", Math.round(left) + "px");
    box.style.setProperty("--be-width", Math.round(Math.min(460, right - left)) + "px");
    box.style.setProperty("--be-top", Math.round(bar.top + (bar.height - 48) / 2) + "px");
  }
  function watchExplore() {
    const again = () => requestAnimationFrame(placeExplore);
    window.addEventListener("resize", again);
    document.addEventListener("civic:mode", again);
    if (typeof ResizeObserver === "function" && header) new ResizeObserver(again).observe(header);
    // Панель монтирует shell.js, когда готова карта: ловим её появление (и пересоздание при смене режима).
    const root = document.getElementById("civic-root") || document.body;
    const isExplore = (n) => n.nodeType === 1 && (n.classList?.contains("civic-explore") || n.querySelector?.(".civic-explore"));
    if (typeof MutationObserver === "function") new MutationObserver((records) => {
      if (records.some((r) => [...r.addedNodes].some(isExplore))) again();
    }).observe(root, { childList: true, subtree: true });
    again();
  }

  // ------------------------------------------------------------------ один дополнительный слой карты (защита п. 1)
  // По умолчанию на карте только тепловая карта объектов и работы города. «Рядом», «Идеи», «Объявления» — слои
  // по одному переключателю, одновременно не больше одного; слой грузит данные только когда включён (п. 5).
  // BirgeShell.registerLayer({id, titleKey | title:{ru,kk}, modes, show(map), hide(map)}).
  let layerBox = null;
  function currentMapObject() {
    try { return typeof map !== "undefined" && map && typeof map.addLayer === "function" ? map : null; } catch (e) { return null; }  // eslint-disable-line no-undef
  }
  function registerLayer(spec) {
    if (!spec || !/^[a-z][a-z0-9-]{1,30}$/.test(spec.id || "") || typeof spec.show !== "function") return false;
    state.layers = state.layers.filter((l) => l.id !== spec.id).concat([{ ...spec, modes: (spec.modes || MODES).filter((m) => MODES.includes(m)) }]);
    render();
    return true;
  }
  const layerTitle = (l) => (l.titleKey ? t(l.titleKey) : (l.title?.[lang()] || l.title?.ru || l.id));
  function setLayer(id) {
    // Карта MapLibre — глобальная переменная web/map.js (window.map — это элемент #map, не карта).
    // eslint-disable-next-line no-undef
    const map = currentMapObject();
    const prev = state.layers.find((l) => l.id === state.layer);
    const next = state.layers.find((l) => l.id === id) || null;
    if (prev && prev !== next) { try { prev.hide?.(map); } catch (e) { console.error("birge layer " + prev.id, e); } }
    state.layer = next ? next.id : null;
    if (next && next !== prev) { try { next.show(map); } catch (e) { console.error("birge layer " + next.id, e); state.layer = null; } }
    document.body.dataset.birgeLayer = state.layer || "";
    renderLayers();
  }
  // Кнопка «слои» — последняя в колонке кнопок карты; по нажатию — список «Только жалобы / Рядом / Идеи…».
  function renderLayers() {
    const list = state.layers.filter((l) => l.modes.includes(state.mode));
    const tools = document.querySelector(".map-tools");
    if (!list.length || !tools || !document.body.classList.contains("civic-mode")) { if (layerBox) layerBox.hidden = true; return; }
    if (!layerBox) {
      const button = el("button", { type: "button", id: "birge-layer-btn", class: "icon-btn birge-layer-btn", "aria-expanded": "false",
        "aria-controls": "birge-layer-list" });
      button.innerHTML = '<svg class="ic" aria-hidden="true"><use href="/civic/ui-kit/icons.svg#i-layers"></use></svg>';
      const listBox = el("div", { id: "birge-layer-list", class: "birge-layer__list", role: "radiogroup", hidden: true });
      layerBox = el("div", { id: "birge-layer", class: "birge-layer bk-app" }, [button, listBox]);
      button.addEventListener("click", () => {
        const open = listBox.hidden;
        listBox.hidden = !open;
        button.setAttribute("aria-expanded", String(open));
      });
      listBox.addEventListener("change", (event) => {
        if (event.target.name !== "birge-layer") return;
        setLayer(event.target.value || null);
        listBox.hidden = true;
        button.setAttribute("aria-expanded", "false");
      });
      tools.append(layerBox);
    }
    layerBox.hidden = false;
    const button = layerBox.querySelector("#birge-layer-btn"), listBox = layerBox.querySelector("#birge-layer-list");
    button.setAttribute("aria-label", t("shell.layers.label"));
    button.title = t("shell.layers.label");
    button.setAttribute("aria-pressed", String(!!state.layer));
    listBox.setAttribute("aria-label", t("shell.layers.label"));
    const option = (value, text) => {
      const input = el("input", { type: "radio", name: "birge-layer", value });
      input.checked = (state.layer || "") === value;
      return el("label", { class: "birge-layer__opt" }, [input, el("span", { text })]);
    };
    listBox.replaceChildren(el("span", { class: "birge-layer__title", text: t("shell.layers.label") }),
      option("", t("shell.layers.none")), ...list.map((l) => option(l.id, layerTitle(l))));
  }

  function setSection(section, options) {
    if (!SECTIONS.includes(section)) section = "map";
    // «Картина дня» — экран акимата; житель всегда на карте. Раздел другого вида переключает вид (ссылка, «Ещё»).
    if (section === "day" && state.mode === "resident") setMode("akimat");
    else if (section !== "map" && section !== "day" && section !== "more" && !screenModes(section).includes(state.mode)) {
      setMode(screenModes(section)[0]);
    }
    state.section = section;
    document.body.dataset.birgeSection = section;
    if (day) day.hidden = section !== "day";
    if (screen) screen.hidden = section === "map" || section === "day";
    if (section !== "day" && state.dayHandle) {
      try { state.dayHandle.destroy?.(); } catch (e) { /* модуль R08 не ломает оболочку */ }
      state.dayHandle = null;
      day?.classList.remove("birge-day--module");
      day?.querySelector("#birge-day-root")?.replaceChildren();
    }
    if (section === "map" || section === "day") destroyScreen();
    if (options?.hash !== false) {
      const routed = /^#[a-z][a-z0-9-]*$/.test(location.hash) && SECTIONS.includes(location.hash.slice(1));
      if (section !== "map" && location.hash !== "#" + section) history.pushState(null, "", location.pathname + location.search + "#" + section);
      else if (section === "map" && routed) history.pushState(null, "", location.pathname + location.search);
    }
    render();
    if (section === "day") day?.querySelector("#birge-day-title")?.focus?.();
    else if (section !== "map") screen?.querySelector("#birge-screen-title")?.focus?.();
  }

  // ------------------------------------------------------------------ запуск
  function start() {
    // Сравнение перекрытий и помощник по объекту (модули раунда 13) в сценарий демо Birge не входят:
    // скрыты, код и API v1 целы. ?tools=all в адресе возвращает их (проверки ролей, показ сотрудникам).
    document.body.dataset.birgeTools = /[?&]tools=all(&|$)/.test(location.search) ? "all" : "off";
    state.mode = savedMode() || defaultMode();
    // QR-паспорт объекта (R12, /?report=<target_id>) сканирует житель: вид «Житель» на этот заход, выбор не запоминаем;
    // язык не трогаем (сохранённый выбор, POLISH_WAVE_2 «не переключать язык после ссылки или QR»).
    if (/[?&]report=/.test(location.search)) { state.mode = "resident"; }
    document.body.dataset.birgeMode = state.mode;
    buildSkip();
    buildHeader();
    buildDay();
    buildScreen();
    watchExplore();
    // Разделы — адрес #day, #nearby, #ideas, #more…; прочие адреса (#object=, #target=, #school) — карта, как раньше.
    const routeOf = () => { const h = location.hash.slice(1); return SECTIONS.includes(h) ? h : "map"; };
    setSection(routeOf(), { hash: false });
    window.addEventListener("hashchange", () => {
      const route = routeOf();
      if (route !== "map") setSection(route, { hash: false });
      else if (state.section !== "map") setSection("map", { hash: false });
    });
    const I = i18n();
    if (I) {
      I.onChange(() => render());
      // "birge:lang" на window для R07 и R09 i18n R11 (>= cc77761) шлёт сам — своя пересылка убрана (R09 рисовал дважды).
      if (I.ready && typeof I.ready.then === "function") I.ready.then(render, render);
    }
    // shell.js переключает режимы старого приложения; при возврате на карту перерисовываем бренд.
    document.addEventListener("civic:mode", render);
  }

  window.BirgeShell = {
    t, lang,
    get mode() { return state.mode; },
    get section() { return state.section; },
    get toolsVisible() { return document.body.dataset.birgeTools === "all"; },
    get layer() { return state.layer; },
    setMode, setSection, registerScreen, registerLayer, setLayer,
    // Для проверок: какие пункты меню видны в этом виде.
    navItems: (mode) => NAV[MODES.includes(mode) ? mode : state.mode].filter((id) => available(id, MODES.includes(mode) ? mode : state.mode)),
    api: { v2, ApiError: BirgeApiError },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
