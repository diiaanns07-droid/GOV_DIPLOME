/*
 * Birge · эталон A «лучше 2ГИС» (решение владельца 13 окт) — хром экрана R01.
 * Эталон: research/round-14/design/README.md и REFERENCE.html (вариант A); ui-kit R11 §20.1; что ждут роли — их INTEGRATION.
 *
 * Что делает этот файл (только раскладка и поведение оболочки; содержимое карточек — модули ролей):
 *  1. Вид экрана: <body data-birge-layout="ref"> (по умолчанию, стоит в index.html) или "classic" — прежняя шапка-полоса
 *     и панель справа. Переключение адресом: ?layout=classic / ?layout=ref (запоминается до конца вкладки).
 *  2. Слева — ОДНА закрываемая карточка (README: «убрать все постоянные панели»). Что в ней, решает leftState():
 *     report (паспорт по QR) → card (карточка места R07 или работ R12) → list («Горячие места» R07, открыт явно) →
 *     summary (сводка «Сегодня в Астане» R08 на главной акимата) → near (шторка «Рядом с вами» R09, телефон жителя) →
 *     none. Состояние — <body data-birge-left>; где и как видно — birge-ref.css.
 *     Закрытие: × в карточке (R07/R08/R12 рисуют сами), Esc, нажатие на пустую карту.
 *  3. Чипы тем под поиском (3 темы с самыми свежими жалобами + «Все» + «Ещё»): открывают «Горячие места» с этой темой.
 *  4. Клавиатура (правило Linear 2): «/» — поиск, J / K — горячие места, Esc — закрыть карточку, Ctrl+K — палитра команд.
 *  5. Палитра команд: разделы, вид, язык, горячие места и «Взять в работу / Отметить исправленным» (R07), команды
 *     «Обращений» (R09). Только текст (textContent), введённое — лишь фильтр списка, ничего не исполняется (R15 правило 4).
 * Сервер не трогаем: смена статуса — те же кнопки и запросы модулей ролей (CSRF, проверка сотрудника — на сервере).
 */
(function () {
  "use strict";
  const PHONE = 761;                                  // как в birge.js и shell.js: уже 761 px — телефонная схема
  const KEY = "birge.layout";
  const body = document.body;

  // ------------------------------------------------------------------ 1. вид экрана
  const asked = /[?&]layout=(classic|ref)(?:&|$)/.exec(location.search);
  let stored = null;
  try { stored = sessionStorage.getItem(KEY); } catch (e) { /* хранилище закрыто — без запоминания */ }
  if (asked) { try { sessionStorage.setItem(KEY, asked[1]); } catch (e) { /* без запоминания */ } }
  const layout = asked ? asked[1] : stored === "classic" ? "classic" : "ref";
  body.dataset.birgeLayout = layout;
  if (layout !== "ref") { window.BirgeRef = { layout, state: () => "classic" }; return; }

  const S = { listOpen: false, todayClosed: false, today: null, todayEl: null, chipsEl: null, cats: null, near: null,
    nearEl: null, palette: null, queued: false, mapBound: false };
  try { S.todayClosed = sessionStorage.getItem("birge.today.closed") === "1"; } catch (e) { /* сводка снова видна */ }

  const desktop = () => innerWidth >= PHONE;
  const t = (key, params) => (window.BirgeShell && typeof window.BirgeShell.t === "function" ? window.BirgeShell.t(key, params) : key);
  const heat = () => (window.CivicShell && window.CivicShell.heat) || null;
  const mode = () => body.dataset.birgeMode || (window.BirgeShell && window.BirgeShell.mode) || "akimat";
  const section = () => body.dataset.birgeSection || "map";
  const civic = () => body.classList.contains("civic-mode");
  function mapObject() {
    try { return typeof map !== "undefined" && map && typeof map.on === "function" ? map : null; } catch (e) { return null; }  // eslint-disable-line no-undef
  }
  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "text") node.textContent = v; else node.setAttribute(k, v === true ? "" : String(v));
    }
    for (const c of children || []) if (c) node.append(c);
    return node;
  }
  function icon(name, size) {
    const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg"), use = document.createElementNS(NS, "use");
    svg.setAttribute("class", "ic"); svg.setAttribute("aria-hidden", "true");
    if (size) { svg.setAttribute("width", size); svg.setAttribute("height", size); }
    use.setAttribute("href", "/civic/ui-kit/icons.svg#i-" + name);
    svg.append(use);
    return svg;
  }

  // ------------------------------------------------------------------ 2. что слева
  function hasCard() {
    const root = document.getElementById("birge-heat-root");
    if (root && root.querySelector(".r07-card")) return true;
    // Карточка работ R12 (нажатие на работу на карте) и старые окна раунда 13 — тоже в панели.
    return !!document.querySelector("#civic-map-root .civic-r03-card:not([hidden]), #civic-feedback-box:not([hidden]), #civic-assistant-box:not([hidden])");
  }
  function leftState() {
    if (!civic() || section() !== "map") return "none";
    if (body.classList.contains("birge-report-open")) return "report";
    if (hasCard()) return "card";
    if (S.listOpen) return "list";
    // Нет связи с тепловой картой: значков нет — слева «Карта жалоб» R07 с понятным сообщением и «Повторить» (приёмка R10 E).
    const h = heat();
    try { if (h && h.state && h.state().status === "error") return "list"; } catch (e) { /* R07 ещё не готов */ }
    if (desktop() && mode() === "akimat" && !S.todayClosed && window.BirgeToday) return "summary";
    if (!desktop() && mode() === "resident" && window.BirgeComplaint && typeof window.BirgeComplaint.mountNear === "function") return "near";
    return "none";
  }
  function sync() {
    S.queued = false;
    const st = leftState();
    if (body.dataset.birgeLeft !== st) body.dataset.birgeLeft = st;
    syncToday(st === "summary");
    syncNear(st === "near");
    syncChips();
    syncGlass();
    bindMap();
  }
  function queue() {
    if (S.queued) return;
    S.queued = true;
    requestAnimationFrame(sync);
  }

  // «Горячие места» R07 в карточке слева — открыть (с темой или без) и закрыть.
  function openList(category) {
    const h = heat();
    if (!h) return false;
    if (window.BirgeShell && section() !== "map") window.BirgeShell.setSection("map");
    if (category !== undefined && typeof h.setFilters === "function") h.setFilters({ category: category || null });
    if (h.state && h.state().selected && typeof h.close === "function") h.close();
    S.listOpen = true;
    queue();
    return true;
  }
  // Закрыть то, что слева. true — что-то было открыто.
  //  all = false (Esc): один слой — карточка места или работ; открыта из «Горячих мест» — снова виден список
  //    (как «назад»: ведущий идёт по списку Esc → следующее место); нет карточки — закрывается список.
  //  all = true (нажатие на пустую карту, знак Birge): карточка и список сразу.
  function closeLeft(all) {
    let did = false;
    const h = heat();
    if (h && h.state && h.state().selected && typeof h.close === "function") { h.close(); did = true; }
    const works = document.querySelector("#civic-map-root .civic-r03-card:not([hidden]) [data-close], #civic-map-root .civic-r03-card:not([hidden]) .civic-close");
    if (works) { works.click(); did = true; }
    if (S.listOpen && (all || !did)) { S.listOpen = false; did = true; }
    queue();
    return did;
  }

  // Сводка «Сегодня в Астане» (R08, INTEGRATION §11.1): на главной акимата, пока слева нет карточки.
  function syncToday(show) {
    if (!show) { if (S.todayEl) S.todayEl.hidden = true; return; }
    if (!window.BirgeToday || typeof window.BirgeToday.mount !== "function") return;
    if (!S.todayEl) {
      S.todayEl = el("section", { id: "birge-today", class: "birge-today" });
      document.body.append(S.todayEl);
      try {
        S.today = window.BirgeToday.mount(S.todayEl, { apiBase: "/api/civic/v2", onClose() {
          S.todayClosed = true;
          try { sessionStorage.setItem("birge.today.closed", "1"); } catch (e) { /* закрыта до перезагрузки */ }
          queue();
        } });
      } catch (error) { console.error("birge today mount", error); S.todayClosed = true; return; }
    } else if (S.todayEl.hidden && S.today && typeof S.today.reload === "function") S.today.reload();
    S.todayEl.hidden = false;
  }

  // Шторка «Рядом с вами» (R09 mountNear, R11 §21.2): телефон жителя, раздел «Карта», пока нет карточки.
  function syncNear(show) {
    if (!show) { if (S.nearEl) S.nearEl.hidden = true; return; }
    const m = mapObject();
    if (!S.nearEl) {
      if (!m || !window.BirgeComplaint || typeof window.BirgeComplaint.mountNear !== "function") return;
      S.nearEl = el("section", { id: "birge-near", class: "birge-near" });
      document.body.append(S.nearEl);
      try {
        S.near = window.BirgeComplaint.mountNear(S.nearEl, { map: m, limit: 3,
          onOpen: (target) => { if (target && target.kind && target.id) heat()?.focusTarget?.(target.kind, target.id); },
          onAll: () => openList(null) });
      } catch (error) { console.error("birge near mount", error); S.nearEl.remove(); S.nearEl = null; return; }
    } else if (S.nearEl.hidden && S.near && typeof S.near.refresh === "function") S.near.refresh();
    S.nearEl.hidden = false;
  }

  // ------------------------------------------------------------------ стекло деталей хрома (ui-kit R11 §20.1 b)
  // Ноутбук: шапки-полосы нет — стекло у поиска (плотное 86 %), капсулы разделов и «ҚАЗ · РУС + аватар».
  // Телефон: прежняя капсула шапки (стекло на ней), внутри — без своего стекла (стекло в стекле не размывает фон).
  function syncGlass() {
    const on = desktop();
    const set = (node, classes) => { if (node) for (const c of classes) node.classList.toggle(c, on); };
    set(document.querySelector("#birge-header .birge-nav"), ["bk-glass", "bk-navpill"]);
    set(document.querySelector("#birge-header .birge-me"), ["bk-glass", "bk-me"]);
    set(document.querySelector(".civic-explore-field"), ["bk-glass", "bk-glass--strong", "bk-searchbar"]);
    // Карточка слева — плотное стекло 86 % (эталон: «текст — на плотном стекле»).
    set(document.getElementById("civic-panel"), ["bk-glass--strong"]);
    decorateSearch();
  }
  // Знак Birge и подсказка клавиши «/» внутри поля поиска (эталон .search: знак 30 слева, «/» справа).
  function decorateSearch() {
    const field = document.querySelector(".civic-explore-field");
    if (!field || field.querySelector(".birge-ref-logo")) return;
    const input = field.querySelector("input");
    const logo = el("button", { type: "button", class: "bk-logo birge-ref-logo", "aria-label": "Birge — " + t("common.nav.map"), title: t("common.nav.map") }, [icon("home", 18)]);
    logo.addEventListener("click", () => { if (window.BirgeShell) window.BirgeShell.setSection("map"); closeLeft(true); });
    const glass = el("span", { class: "birge-ref-search-ic", "aria-hidden": "true" }, [icon("search", 18)]);
    const kbd = el("kbd", { class: "bk-kbd birge-ref-kbd", "aria-hidden": "true", text: "/" });
    field.prepend(logo, glass);
    if (input) input.after(kbd);
  }

  // ------------------------------------------------------------------ 3. чипы тем под поиском
  function catLabel(id) {
    const short = t("shell.ref.cat." + id);
    if (short && short !== "shell.ref.cat." + id) return short;
    const I = window.BirgeI18n;
    return I && typeof I.cat === "function" ? I.cat(id) : id;
  }
  function loadChips() {
    if (S.cats || typeof fetch !== "function") return;
    S.cats = [];
    fetch("/api/civic/v2/heat?days=30", { headers: { Accept: "application/json" } }).then((r) => (r.ok ? r.json() : null)).then((data) => {
      const items = ((data && (data.data || data).items) || []).filter((it) => it && it.state === "active" && it.target && it.target.kind !== "district");
      const sum = new Map();
      for (const it of items) {
        const by = it.by_category || {};
        const top = Object.keys(by).sort((a, b) => by[b] - by[a])[0];
        for (const [id, n] of Object.entries(by)) {
          const row = sum.get(id) || { id, count: 0, level: 0 };
          row.count += Number(n) || 0;
          if (id === top) row.level = Math.max(row.level, Number(it.level) || 0);
          sum.set(id, row);
        }
      }
      S.cats = [...sum.values()].filter((c) => c.id !== "other" && c.count > 0).sort((a, b) => b.count - a.count).slice(0, 3);
      renderChips();
    }).catch(() => { S.cats = []; renderChips(); });
  }
  function renderChips() {
    if (!S.chipsEl) {
      S.chipsEl = el("div", { id: "birge-chips", class: "birge-chips", role: "group" });
      S.chipsEl.addEventListener("click", (event) => {
        const b = event.target.closest && event.target.closest("button[data-chip]");
        if (!b) return;
        if (b.dataset.chip === "more") openList(undefined);
        else openList(b.dataset.chip === "all" ? null : b.dataset.chip);
      });
      document.body.append(S.chipsEl);
    }
    S.chipsEl.setAttribute("aria-label", t("heat.filter.category"));
    const current = (heat() && heat().state && heat().state().filters.category) || null;
    const chips = [{ id: "all", label: t("shell.ref.chip_all") }]
      .concat((S.cats || []).map((c) => ({ id: c.id, label: catLabel(c.id), level: c.level })))
      .concat([{ id: "more", label: t("common.nav.more") }]);
    S.chipsEl.replaceChildren(...chips.map((c) => {
      const pressed = c.id === "all" ? !current : c.id !== "more" && c.id === current;
      // Видимая «таблетка» 34 px — внутренний span; сама кнопка 44 px по высоте (зона нажатия, как у R07 R.8a: проверки
      // R10 «≥ 40» и R01 «≥ 36» меряют кнопку, а не ::after).
      const b = el("button", { type: "button", class: "birge-chip", "data-chip": c.id, "aria-pressed": String(pressed) });
      const face = el("span", { class: "birge-chip__face" });
      if (c.level) face.append(el("span", { class: "birge-chip__dot", "data-level": String(Math.min(4, Math.max(1, c.level))), "aria-hidden": "true" }));
      face.append(document.createTextNode(c.label));
      b.append(face);
      return b;
    }));
  }
  function syncChips() {
    loadChips();
    if (!S.chipsEl) renderChips();
    const st = body.dataset.birgeLeft;
    S.chipsEl.hidden = !(desktop() && civic() && section() === "map" && (st === "none" || st === "summary"));
  }

  // ------------------------------------------------------------------ нажатие на пустую карту закрывает карточку
  function bindMap() {
    const m = mapObject();
    if (S.mapBound || !m) return;
    S.mapBound = true;
    m.on("click", (event) => {
      if (!civic() || section() !== "map") return;
      const st = body.dataset.birgeLeft;
      if (st !== "card" && st !== "list") return;
      // Пока выбирают место жалобы (R09) или ставят проект (R05), нажатие на карту — их выбор, не «закрыть».
      if (body.classList.contains("birge-picking") || document.querySelector(".b3d-dock[data-state='placing']")) return;
      const h = heat();
      const before = h && h.state ? h.state().selected : null;
      let hit = false;
      try {
        hit = m.queryRenderedFeatures(event.point).some((f) => f.layer && /^(r07|civic|r12|r03|r05|b3d|heat|works)/i.test(f.layer.id));
      } catch (e) { hit = false; }
      // Модуль под пальцем (значок, участок, объект) выбирает своё сам — ждём его, и если выбор не сменился — закрываем.
      setTimeout(() => {
        const after = h && h.state ? h.state().selected : null;
        if (!hit && after === before) closeLeft(true);
      }, 80);
    });
  }

  // ------------------------------------------------------------------ 4. клавиатура
  function typing(node) {
    if (!node || node === document.body) return false;
    const tag = node.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || node.isContentEditable;
  }
  function menuOpen() {
    return !!document.querySelector("#birge-account:not([hidden]), .birge-more-menu:not([hidden]), #birge-layer-list:not([hidden]), html.bc-open");
  }
  document.addEventListener("keydown", (event) => {
    const k = event.key, code = event.code;
    if ((event.ctrlKey || event.metaKey) && !event.altKey && (code === "KeyK" || k === "k" || k === "K")) {
      if (!civic()) return;
      event.preventDefault();
      togglePalette();
      return;
    }
    if (event.defaultPrevented || (S.palette && !S.palette.hidden)) return;
    if (event.ctrlKey || event.metaKey || event.altKey || typing(event.target) || !civic()) return;
    if ((k === "/" || (code === "Slash" && !event.shiftKey))) {
      const input = document.querySelector(".civic-explore-field input");
      if (!input) return;
      event.preventDefault();
      if (window.BirgeShell && section() !== "map") window.BirgeShell.setSection("map");
      input.focus();
      return;
    }
    if (section() !== "map" || menuOpen()) return;
    if (code === "KeyJ" || code === "KeyK") {
      const h = heat();
      if (!h || typeof h.stepHot !== "function") return;
      event.preventDefault();
      h.stepHot(code === "KeyJ" ? 1 : -1);
      return;
    }
    if (k === "Escape" && closeLeft()) event.preventDefault();
  });

  // ------------------------------------------------------------------ 5. палитра команд (Ctrl+K)
  const norm = (s) => String(s || "").toLowerCase().replace(/ё/g, "е").replace(/[«»"]/g, "").trim();
  let paletteItems = [], paletteActive = 0, paletteSeq = 0;
  function buildPalette() {
    const input = el("input", { type: "text", class: "birge-palette__input", autocomplete: "off", spellcheck: "false",
      role: "combobox", "aria-expanded": "true", "aria-controls": "birge-palette-list", "aria-autocomplete": "list" });
    const list = el("ul", { id: "birge-palette-list", class: "birge-palette__list", role: "listbox" });
    const foot = el("p", { class: "birge-palette__foot" });
    const box = el("div", { class: "birge-palette__box bk-glass bk-glass--strong" }, [input, list, foot]);
    const wrap = el("div", { class: "birge-palette", role: "dialog", "aria-modal": "true", hidden: true }, [box]);
    wrap.addEventListener("pointerdown", (event) => { if (event.target === wrap) closePalette(); });
    input.addEventListener("input", () => renderPalette(input.value));
    input.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        movePalette(event.key === "ArrowDown" ? 1 : -1);
      } else if (event.key === "Enter") {
        event.preventDefault();
        runPalette(paletteItems[paletteActive]);
      } else if (event.key === "Escape") {
        event.preventDefault();
        closePalette();
      } else if (event.key === "Tab") event.preventDefault();   // фокус остаётся в поле палитры
    });
    document.body.append(wrap);
    S.palette = wrap;
  }
  async function gatherCommands() {
    const out = [];
    const sections = t("shell.palette.sections");
    const seen = new Set();
    for (const b of document.querySelectorAll("#birge-header .birge-nav > [data-section]")) {
      const id = b.dataset.section;
      if (!id || id === "more" || b.hidden || seen.has(id)) continue;
      seen.add(id);
      out.push({ group: sections, title: (b.textContent || "").trim(), run: () => window.BirgeShell && window.BirgeShell.setSection(id) });
    }
    // Разделы из «Ещё» (меню строится при открытии — берём список у оболочки).
    const B = window.BirgeShell;
    if (B && typeof B.moreItems === "function" && typeof B.navTitle === "function") {
      for (const id of B.moreItems() || []) {
        if (seen.has(id)) continue;
        seen.add(id);
        out.push({ group: sections, title: B.navTitle(id), run: () => B.setSection(id) });
      }
    }
    const view = t("shell.palette.view");
    for (const m of ["akimat", "resident"]) if (m !== mode()) out.push({ group: view, title: t("common.role." + m), run: () => window.BirgeShell && window.BirgeShell.setMode(m) });
    const I = window.BirgeI18n;
    if (I && typeof I.setLang === "function") {
      const other = I.getLang && I.getLang() === "kk" ? "ru" : "kk";
      out.push({ group: t("common.lang.label"), title: other === "kk" ? "Қазақша" : "Русский", run: () => I.setLang(other) });
    }
    const h = heat();
    if (h && typeof h.commands === "function") {
      try { for (const c of h.commands() || []) out.push({ group: c.group, title: c.title, hint: c.hint, run: () => { openListIfNeeded(); c.run(); } }); } catch (e) { /* без команд R07 */ }
    }
    const L = window.BirgeComplaintList;
    if (mode() === "akimat" && L && typeof L.commands === "function" && window.BirgeShell) {
      try {
        const list = await L.commands({ api: window.BirgeShell.api });
        for (const c of list || []) out.push({ group: t("common.nav.complaints"), title: c.title, hint: c.hint, run: c.run });
      } catch (e) { /* без команд R09: нет входа сотрудника или нет сети */ }
    }
    return out;
  }
  // Горячее место из палитры открывает карточку — карточка слева всё равно видна (card), список не нужен.
  function openListIfNeeded() { if (window.BirgeShell && section() !== "map") window.BirgeShell.setSection("map"); }
  function renderPalette(query) {
    const list = S.palette.querySelector(".birge-palette__list");
    const q = norm(query);
    const found = (S.paletteAll || []).filter((c) => !q || norm(c.title + " " + (c.group || "") + " " + (c.hint || "")).includes(q)).slice(0, 14);
    paletteItems = found;
    paletteActive = 0;
    const rows = [];
    let group = null;
    found.forEach((c, i) => {
      if (c.group && c.group !== group) { group = c.group; rows.push(el("li", { class: "birge-palette__group", role: "presentation", text: group })); }
      const li = el("li", { id: "birge-palette-opt-" + i, class: "birge-palette__item", role: "option", "aria-selected": String(i === 0) },
        [el("span", { class: "birge-palette__title", text: c.title }), c.hint ? el("span", { class: "birge-palette__hint", text: c.hint }) : null]);
      li.addEventListener("pointerdown", (event) => event.preventDefault());
      li.addEventListener("click", () => runPalette(c));
      rows.push(li);
    });
    if (!found.length) rows.push(el("li", { class: "birge-palette__empty", role: "presentation", text: t("shell.palette.empty") }));
    list.replaceChildren(...rows);
    const input = S.palette.querySelector(".birge-palette__input");
    if (found.length) input.setAttribute("aria-activedescendant", "birge-palette-opt-0"); else input.removeAttribute("aria-activedescendant");
  }
  function movePalette(d) {
    if (!paletteItems.length) return;
    paletteActive = (paletteActive + d + paletteItems.length) % paletteItems.length;
    S.palette.querySelectorAll(".birge-palette__item").forEach((li, i) => li.setAttribute("aria-selected", String(i === paletteActive)));
    const li = document.getElementById("birge-palette-opt-" + paletteActive);
    S.palette.querySelector(".birge-palette__input").setAttribute("aria-activedescendant", li.id);
    li.scrollIntoView({ block: "nearest" });
  }
  function runPalette(c) {
    if (!c || typeof c.run !== "function") return;
    closePalette();
    try { c.run(); } catch (error) { console.error("birge palette", error); }
  }
  async function openPalette() {
    if (!S.palette) buildPalette();
    const seq = ++paletteSeq;
    const input = S.palette.querySelector(".birge-palette__input");
    S.palette.setAttribute("aria-label", t("shell.palette.title"));
    input.setAttribute("aria-label", t("shell.palette.title"));
    input.placeholder = t("shell.palette.placeholder");
    S.palette.querySelector(".birge-palette__foot").textContent = t("shell.palette.keys");
    input.value = "";
    S.paletteAll = [];
    S.palette.hidden = false;
    S.paletteReturn = document.activeElement;
    input.focus();
    renderPalette("");
    const all = await gatherCommands();
    if (seq !== paletteSeq || S.palette.hidden) return;
    S.paletteAll = all;
    renderPalette(input.value);
  }
  function closePalette() {
    if (!S.palette || S.palette.hidden) return;
    S.palette.hidden = true;
    paletteSeq++;
    const back = S.paletteReturn;
    S.paletteReturn = null;
    if (back && typeof back.focus === "function" && document.contains(back)) back.focus();
  }
  function togglePalette() { if (S.palette && !S.palette.hidden) closePalette(); else void openPalette(); }

  // ------------------------------------------------------------------ события ролей и наблюдение за раскладкой
  // «Все горячие места» в сводке R08 → список R07 слева.
  document.addEventListener("birge:open-hot-list", (event) => { if (openList(undefined)) event.preventDefault(); });
  // Наведение на строку сводки R08 ("birge:hover-target" на document) → подсветка значка R07 ("birge:target-hover" на window).
  document.addEventListener("birge:hover-target", (event) => {
    const d = event.detail || {};
    const target = d.on && d.target && d.target.kind && d.target.id ? { kind: d.target.kind, id: d.target.id, source: "today" } : null;
    window.dispatchEvent(new CustomEvent("birge:target-hover", { detail: target }));
  });
  // × в «Горячих местах» R07 (mount closable) — список закрыт.
  window.addEventListener("birge:heat-close", () => { S.listOpen = false; queue(); });
  // Язык: сводка и шторка перерисовываются; чипы — заново.
  function relang() {
    if (S.today && typeof S.today.setLang === "function") S.today.setLang();
    if (S.near && typeof S.near.setLang === "function") S.near.setLang();
    renderChips();
  }
  if (window.BirgeI18n && typeof window.BirgeI18n.onChange === "function") window.BirgeI18n.onChange(relang);
  window.addEventListener("resize", queue);
  // Наблюдаем узко: атрибуты body (вид, раздел, классы) и его прямые дети (монтаж #civic-root), затем — #civic-root
  // (карточка R07 / работ R12 / паспорт появились или ушли). Значки карты (их много и они двигаются) сюда не попадают.
  let rootWatched = false;
  function watchRoot() {
    const r = document.getElementById("civic-root");
    if (rootWatched || !r || typeof MutationObserver !== "function") return;
    rootWatched = true;
    new MutationObserver(queue).observe(r, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
  }
  if (typeof MutationObserver === "function") {
    new MutationObserver(() => { watchRoot(); queue(); }).observe(body, { attributes: true, childList: true,
      attributeFilter: ["class", "data-birge-section", "data-birge-mode"] });
  }
  watchRoot();
  queue();

  window.BirgeRef = {
    layout,
    state: () => body.dataset.birgeLeft || "none",
    openList, closeLeft, openPalette, closePalette,
    get listOpen() { return S.listOpen; },
  };
})();
