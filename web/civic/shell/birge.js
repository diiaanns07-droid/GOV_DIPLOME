/*
 * Birge · шапка и общие настройки оболочки (R01, раунд 14).
 *
 * Что делает этот файл:
 *  - шапка: логотип Birge, разделы «Карта | Картина дня», «Акимат | Житель», «ҚАЗ | РУС» (UX_SPEC R11 §1);
 *  - язык — через BirgeI18n (R11, web/civic/i18n/). Ключа ещё нет в словаре R11 — берём запасной текст
 *    из SHELL_TEXT ниже (ключи переданы R11 в research/round-14-results/R01/INTEGRATION.txt);
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
  const SECTIONS = ["map", "day"];
  const PHONE = 761;                         // как в shell.js: уже 761 px — телефонная схема

  // Запасные тексты оболочки. Источник истины — словари R11 (web/civic/i18n/ru.json, kk.json):
  // когда ключ там появится, используется он. Казахский — предложение R01, проверяет R11 и владелец.
  const SHELL_TEXT = {
    ru: {
      "shell.brand.tagline": "Город и жители вместе",
      "shell.title": "Birge · Астана",
      "shell.nav.label": "Разделы",
      "common.nav.map": "Карта",
      "common.nav.day": "Картина дня",
      "common.nav.menu": "Меню",
      "shell.day.soon_title": "Картина дня скоро появится",
      "shell.day.soon_text": "Здесь будет сводка за день: темы обращений, районы, горячие места, просрочки и объекты с отставанием.",
      "shell.day.back": "Вернуться к карте",
      "shell.day.error_title": "Картину дня не удалось открыть",
      "shell.day.error_text": "Попробуйте ещё раз через минуту.",
      "shell.map.label": "Карта Астаны",
      "common.lang.label": "Язык интерфейса",
      "common.lang.ru": "РУС",
      "common.lang.kk": "ҚАЗ",
      "common.role.label": "Чей вид",
      "common.role.akimat": "Акимат",
      "common.role.resident": "Житель",
      "common.action.retry": "Повторить",
      "akim.title": "Картина дня",
    },
    kk: {
      "shell.brand.tagline": "Қала мен тұрғындар бірге",
      "shell.title": "Birge · Астана",
      "shell.nav.label": "Бөлімдер",
      "common.nav.map": "Карта",
      "common.nav.day": "Күн қорытындысы",
      "common.nav.menu": "Мәзір",
      "shell.day.soon_title": "Күн қорытындысы жақында қосылады",
      "shell.day.soon_text": "Мұнда күн қорытындысы болады: өтініш тақырыптары, аудандар, шағымы көп орындар, мерзімі өткен және кестеден қалып жатқан нысандар.",
      "shell.day.back": "Картаға оралу",
      "shell.day.error_title": "Күн қорытындысы ашылмады",
      "shell.day.error_text": "Бір минуттан кейін қайталап көріңіз.",
      "shell.map.label": "Астана картасы",
      "common.lang.label": "Интерфейс тілі",
      "common.lang.ru": "РУС",
      "common.lang.kk": "ҚАЗ",
      "common.role.label": "Кімнің көрінісі",
      "common.role.akimat": "Әкімдік",
      "common.role.resident": "Тұрғын",
      "common.action.retry": "Қайталау",
      "akim.title": "Күн қорытындысы",
    },
  };

  const i18n = () => window.BirgeI18n || null;
  const lang = () => (i18n() && typeof i18n().getLang === "function" ? i18n().getLang() : "ru");
  function t(key, params) {
    const I = i18n();
    if (I && typeof I.has === "function" && I.has(key)) return I.t(key, params);
    const l = lang();
    return (SHELL_TEXT[l] && SHELL_TEXT[l][key]) || SHELL_TEXT.ru[key] || key;
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
    let data = null;
    try { data = await response.json(); } catch (e) { data = null; }
    if (!response.ok) throw new BirgeApiError(response.status, data);
    return data;
  }

  // ------------------------------------------------------------------ состояние
  const state = { mode: null, section: "map", dayHandle: null };

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
    header = el("div", { id: "birge-header", class: "birge-header" }, [
      menuButton,
      el("div", { id: "birge-menu", class: "birge-menu" }, [
        el("div", { class: "bk-seg birge-nav", role: "group", "data-group": "section" },
          SECTIONS.map((s) => segButton("section", s, s === state.section))),
        el("div", { class: "bk-seg birge-role", role: "group", "data-group": "mode" },
          MODES.map((m) => segButton("mode", m, m === state.mode))),
      ]),
      el("div", { class: "bk-seg birge-lang", role: "group", "data-group": "lang" },
        ["kk", "ru"].map((l) => segButton("lang", l, l === lang()))),
    ]);
    actions.prepend(header);
    header.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button || !header.contains(button)) return;
      if (button === menuButton) { setMenu(header.dataset.menu !== "open"); return; }
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
  function setMenu(open) {
    if (!header) return;
    header.dataset.menu = open ? "open" : "closed";
    document.body.dataset.birgeMenu = open ? "open" : "closed";  // birge.css поднимает шапку над панелями карты
    header.querySelector(".birge-menu-btn").setAttribute("aria-expanded", String(open));
  }

  function render() {
    if (header) {
      header.querySelector(".birge-nav").setAttribute("aria-label", t("shell.nav.label"));
      header.querySelector(".birge-role").setAttribute("aria-label", t("common.role.label"));
      header.querySelector(".birge-lang").setAttribute("aria-label", t("common.lang.label"));
      const menuLabel = header.querySelector(".birge-menu-btn span");
      if (menuLabel) menuLabel.textContent = t("common.nav.menu");
      for (const b of header.querySelectorAll("[data-section]")) {
        b.textContent = t("common.nav." + b.dataset.section);
        b.setAttribute("aria-pressed", String(b.dataset.section === state.section));
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
    }
    renderDay();
  }

  // ------------------------------------------------------------------ режим
  function setMode(mode, options) {
    if (!MODES.includes(mode)) mode = defaultMode();
    const changed = state.mode !== mode;
    state.mode = mode;
    document.body.dataset.birgeMode = mode;
    if (options?.persist !== false) { try { localStorage.setItem(MODE_KEY, mode); } catch (e) { /* только удобство */ } }
    render();
    if (changed) document.dispatchEvent(new CustomEvent("birge:mode", { detail: { mode } }));
  }

  // ------------------------------------------------------------------ «Картина дня»
  let day = null;
  function buildDay() {
    if (document.getElementById("birge-day")) return;
    day = el("section", { id: "birge-day", class: "birge-day", hidden: true, "aria-labelledby": "birge-day-title" }, [
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
          state.dayHandle = akim.mount({ root, api: { v2 }, lang: lang(), mode: state.mode }) || {};
        } catch (e) {
          console.error(e);
          state.dayHandle = null;
          root.replaceChildren(emptyDay("error"));
        }
      } else if (typeof state.dayHandle.update === "function") {
        state.dayHandle.update({ lang: lang(), mode: state.mode });
      }
      return;
    }
    root.replaceChildren(emptyDay("soon"));
  }
  function setSection(section, options) {
    if (!SECTIONS.includes(section)) section = "map";
    // «Картина дня» — экран акимата; житель всегда на карте.
    if (section === "day" && state.mode === "resident") setMode("akimat");
    state.section = section;
    document.body.dataset.birgeSection = section;
    if (day) day.hidden = section !== "day";
    if (section !== "day" && state.dayHandle) {
      try { state.dayHandle.destroy?.(); } catch (e) { /* модуль R08 не ломает оболочку */ }
      state.dayHandle = null;
      day?.querySelector("#birge-day-root")?.replaceChildren();
    }
    if (options?.hash !== false) {
      const hash = section === "day" ? "#day" : "";
      if (section === "day" && location.hash !== hash) history.pushState(null, "", location.pathname + location.search + hash);
      else if (section === "map" && location.hash === "#day") history.pushState(null, "", location.pathname + location.search);
    }
    render();
    if (section === "day") day?.querySelector("#birge-day-title")?.focus?.();
  }

  // ------------------------------------------------------------------ запуск
  function start() {
    state.mode = savedMode() || defaultMode();
    document.body.dataset.birgeMode = state.mode;
    buildHeader();
    buildDay();
    setSection(location.hash === "#day" ? "day" : "map", { hash: false });
    window.addEventListener("hashchange", () => {
      if (location.hash === "#day") setSection("day", { hash: false });
      else if (state.section === "day") setSection("map", { hash: false });
    });
    const I = i18n();
    if (I) {
      I.onChange(() => render());
      if (I.ready && typeof I.ready.then === "function") I.ready.then(render, render);
    }
    // shell.js переключает режимы старого приложения; при возврате на карту перерисовываем бренд.
    document.addEventListener("civic:mode", render);
  }

  window.BirgeShell = {
    t, lang,
    get mode() { return state.mode; },
    get section() { return state.section; },
    setMode, setSection,
    api: { v2, ApiError: BirgeApiError },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
