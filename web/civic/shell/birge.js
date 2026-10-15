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
  // Схема R11 (IA_WAVE2 §1): «Ещё» — маленькое меню (≤ 4 пункта), не страница; у жителя — «Вопрос акиму»,
  // у акимата — «Вопросы жителей», «Работы и отключения», «QR-таблички», «Службы».
  const NAV = {
    resident: ["map", "mine", "nearby", "ideas", "more"],
    akimat: ["map", "day", "inbox", "projects", "more"],
  };
  // Экраны новых разделов (п. 2: свои экраны, не поверх карты). Модуль роли: window[global].mount(root, опции) →
  // {destroy?, setLang?}. Пункт меню виден, только когда модуль подключён; ?screens=all — показать все (разбор R11/R10).
  // modes — в каких видах раздел есть; пункт, которого нет в NAV этого вида, попадает в «Ещё».
  // key — подпись по виду (ключи словаря R11); адрес раздела — #<id> (IA_WAVE2 §1).
  const SCREENS = {
    inbox: { global: ["BirgeInbox", "BirgeComplaintList"], modes: ["akimat"], owner: "R09", key: { akimat: "common.nav.complaints" } },
    projects: { global: ["BirgeProjects", "BirgeIdeas"], modes: ["akimat"], owner: "R06 + R05" },
    nearby: { global: ["BirgeNearby"], modes: ["resident"], owner: "R08 + R06" },
    ideas: { global: ["BirgeIdeas"], modes: ["resident"], owner: "R06 + R05" },
    questions: { global: ["BirgeAsk", "BirgeQuestions"], modes: ["resident", "akimat"], owner: "R13",
      key: { resident: "common.nav.ask", akimat: "shell.nav.questions_staff" } },
    works: { global: ["BirgeWorks"], modes: ["akimat"], owner: "R06 + R08", key: { akimat: "shell.nav.works_staff" } },
    qr: { global: ["BirgeQr"], modes: ["akimat"], owner: "R12", key: { akimat: "shell.nav.qr" } },
    services: { global: ["BirgeServices"], modes: ["akimat"], owner: "R08", key: { akimat: "shell.nav.services" } },
  };
  const SECTIONS = ["map", "day", ...Object.keys(SCREENS)];
  // Прежние адреса волны 2 (до схемы R11) ведут в те же разделы.
  const ROUTE_ALIAS = { complaints: "inbox", ask: "questions" };
  const PHONE = 761;                         // как в shell.js: уже 761 px — телефонная схема
  // Кнопки карты из web/index.html и их ключи перевода (словари R11, shell.map.*).
  const MAP_BUTTONS = [["overview-map", "shell.map.fit_city"], ["zoom-in", "shell.map.zoom_in"],
    ["zoom-out", "shell.map.zoom_out"], ["toggle-3d", "shell.map.view3d"], ["rotate-map", "shell.map.rotate"],
    ["birge-locate", "common.map.locate"], ["birge-compass", "common.map.north"]];

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

  // Значок пункта меню (марафон, чек-лист №9): один набор ui-kit (icons.svg), рядом с подписью, тише текста.
  const MENU_ICONS = { map: "pin", day: "chart", inbox: "list", projects: "cube", mine: "list", nearby: "users", ideas: "bulb",
    questions: "info", works: "calendar", qr: "print", services: "building", staff: "user" };
  // Линейная иллюстрация ui-kit (icons.svg #ill-…) для пустых состояний листа (чек-лист №8, №12) — без innerHTML.
  function illustration(name) {
    const sprite = window.BirgeUI && window.BirgeUI.SPRITE;
    if (!sprite) return null;
    const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg"), use = document.createElementNS(NS, "use");
    svg.setAttribute("class", "bk-ill"); svg.setAttribute("aria-hidden", "true"); svg.setAttribute("focusable", "false");
    use.setAttribute("href", sprite + "#ill-" + name);
    svg.append(use);
    return svg;
  }
  function menuIcon(node, id) {
    const sprite = window.BirgeUI && window.BirgeUI.SPRITE, name = MENU_ICONS[id];
    if (!sprite || !name || !node) return node;
    const NS = "http://www.w3.org/2000/svg", svg = document.createElementNS(NS, "svg"), use = document.createElementNS(NS, "use");
    svg.setAttribute("class", "ic birge-menu-ic"); svg.setAttribute("aria-hidden", "true"); svg.setAttribute("focusable", "false");
    use.setAttribute("href", sprite + "#i-" + name);
    svg.append(use);
    node.prepend(svg);
    return node;
  }
  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === false || v == null) continue;
      if (k === "text") node.textContent = v; else node.setAttribute(k, v === true ? "" : v);
    }
    for (const child of children || []) if (child != null) node.append(child);  // null — части нет (нет ui-kit)
    return node;
  }
  function segButton(group, value, pressed) {
    return el("button", { type: "button", class: "birge-nav__item", ["data-" + group]: value, "aria-pressed": String(pressed) });
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
    return ids.filter((id, i) => ids.indexOf(id) === i && !NAV[mode].includes(id) && id !== "more" && available(id, mode)).slice(0, 4);
  }
  const navTitle = (id, mode = state.mode) => {
    const extra = state.extra.find((x) => x.id === id);
    if (extra?.titleKey) return t(extra.titleKey);
    if (extra?.title) return extra.title[lang()] || extra.title.ru || id;
    const key = SCREENS[id]?.key?.[mode];
    return t(key || "common.nav." + id);  // известный раздел (SCREENS) — ключ меню, даже если модуль зарегистрирован
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
          ? el("button", { type: "button", class: "birge-nav__item birge-mine-btn", "data-action": "mine", "aria-pressed": "false" })
          : segButton("section", id, id === state.section);
        if (id === "more") { b.setAttribute("aria-haspopup", "menu"); b.setAttribute("aria-expanded", "false"); }
      }
      b.hidden = !NAV[state.mode].includes(id) || !available(id, state.mode);
      return b;
    });
    nav.replaceChildren(...buttons);
  }

  // «Ещё» — маленькое меню (role="menu", ≤ 4 пункта; IA_WAVE2 §1), не отдельная страница. Ноутбук — под кнопкой,
  // телефон — в листе ≡ сразу под ней.
  const moreMenu = () => header?.querySelector(".birge-more-menu");
  const moreOpen = () => !!moreMenu() && !moreMenu().hidden;
  function toggleMore(button) {
    if (moreOpen()) { closeMore(true); return; }
    let menu = moreMenu();
    if (!menu) {
      menu = el("div", { class: "birge-more-menu bk-app", role: "menu", hidden: true });
      header.querySelector(".birge-nav").after(menu);
    }
    menu.replaceChildren(...moreItems(state.mode).map((id) => {
      const extra = state.extra.find((x) => x.id === id);
      const item = extra?.href
        ? el("a", { role: "menuitem", class: "birge-more-item", href: extra.href, target: extra.target || null, rel: extra.target ? "noopener" : null })
        : el("button", { type: "button", role: "menuitem", class: "birge-more-item", "data-section": id });
      item.textContent = navTitle(id);
      menuIcon(item, id);
      if (id === state.section) item.setAttribute("aria-current", "page");
      return item;
    }));
    const r = button.getBoundingClientRect(), box = header.getBoundingClientRect();
    menu.hidden = false;
    const nav = header.querySelector(".birge-nav");
    if (nav && getComputedStyle(nav).position === "fixed") {
      // Эталон A, ноутбук: капсула разделов «плавает» (position: fixed), у самой шапки коробки нет (0 × 0 справа вверху).
      // Меню считаем от экрана: под кнопкой «Ещё», правый край — не правее капсулы и не за краем окна. Раньше оно
      // считалось от пустой шапки и вставало в правый верхний угол — поверх «ҚАЗ · РУС» и «Распечатать» «Картины дня»
      // (VISUAL_BRIEF раунда 15 §3).
      const cap = nav.getBoundingClientRect(), w = menu.offsetWidth;
      const left = Math.max(8, Math.min(r.left, cap.right - w, innerWidth - w - 8));
      menu.dataset.place = "fixed";
      menu.style.setProperty("--more-left", Math.round(left) + "px");
      menu.style.setProperty("--more-top", Math.round(cap.bottom + 8) + "px");
      menu.style.transformOrigin = left < r.left - 1 ? "top right" : "top left";   // меню «растёт» из кнопки
    } else {
      // Прежняя шапка-полоса: под своей кнопкой, но не шире шапки (марафон: меню 260 px).
      delete menu.dataset.place;
      menu.style.removeProperty("--more-top");
      menu.style.transformOrigin = "";
      menu.style.setProperty("--more-left", Math.round(Math.max(0, Math.min(r.left - box.left, box.width - menu.offsetWidth))) + "px");
    }
    button.setAttribute("aria-expanded", "true");
    menu.querySelector("[role=menuitem]")?.focus();
  }
  function closeMore(focusButton) {
    const menu = moreMenu();
    if (!menu || menu.hidden) return;
    menu.hidden = true;
    const button = header.querySelector(".birge-nav [data-section=more]");
    button?.setAttribute("aria-expanded", "false");
    if (focusButton) button?.focus();
  }

  // ------------------------------------------------------------------ шапка
  let header = null;
  // Чистый дизайн (R11 CLEAN_PASS, решение владельца 12 окт): шапка — одна белая полоса: знак + «Birge» · поиск ·
  // разделы текстом · «ҚАЗ · РУС» текстом · круг-аватар. Вид «Акимат / Житель», «Для сотрудников» и «Выйти» — в меню
  // аватара; когда разделы в строку не помещаются (телефон, узкий ноутбук, длинный ҚАЗ) — они тоже в меню аватара,
  // первой группой (body[data-birge-header="compact"], birge.js placeHeader).
  let account = null, accountMenu = null;
  function buildHeader() {
    const actions = document.querySelector(".topbar .top-actions");
    if (!actions || document.getElementById("birge-header")) return;
    const avatar = el("button", { type: "button", class: "bk-avatar birge-avatar", "data-action": "account",
      "aria-controls": "birge-account" });
    avatar.innerHTML = '<svg class="ic" aria-hidden="true"><use href="/civic/ui-kit/icons.svg#i-user"></use></svg>';
    header = el("div", { id: "birge-header", class: "birge-header bk-app" }, [
      // Пункты меню обоих видов; чужие для текущего вида и разделы без модуля скрыты (buildNav).
      el("div", { class: "bk-nav birge-nav", role: "group", "data-group": "section" }),
      // «ҚАЗ · РУС» и аватар — одна капсула справа (эталон A, birge-ref.css); в прежнем виде обёртка без своей коробки.
      el("div", { class: "birge-me" }, [
        el("div", { class: "bk-langtext birge-lang", role: "group", "data-group": "lang" },
          ["kk", "ru"].map((l) => el("button", { type: "button", "data-lang": l, "aria-pressed": String(l === lang()) }))),
        avatar,
      ]),
    ]);
    actions.prepend(header);
    account = el("div", { id: "birge-account", class: "bk-menu birge-account bk-app", role: "menu", hidden: true });
    document.body.append(account);
    accountMenu = window.BirgeUI && typeof window.BirgeUI.menu === "function" ? window.BirgeUI.menu(avatar, account) : null;
    if (!accountMenu) {  // ui-kit не загрузился: простое открытие/закрытие
      avatar.addEventListener("click", () => { account.hidden = !account.hidden; avatar.setAttribute("aria-expanded", String(!account.hidden)); });
    }
    avatar.addEventListener("click", () => { if (!account.hidden) renderAccount(true); });
    buildNav();
    // Поле поиска видно и в разделах (R11 FINAL-3 №6): нажатие на него возвращает к карте, фокус остаётся в поле.
    document.addEventListener("focusin", (event) => {
      if (state.section !== "map" && event.target.closest?.(".civic-explore-field")) setSection("map");
    });
    // Знак Birge в шапке — «Карта» (R11 FINAL-3 №4): на телефоне из разделов к карте одним нажатием, без меню аватара.
    const brand = document.querySelector(".topbar .brand");
    if (brand) {
      const home = (event) => {
        if (!document.body.classList.contains("civic-mode")) return;
        if (event.type === "keydown" && event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        setSection("map");
      };
      brand.addEventListener("click", home);
      brand.addEventListener("keydown", home);
    }
    const act = (button) => {
      if (button.dataset.action === "mine") { setSection("map"); window.CivicShell?.openMine?.(); return; }
      if (button.dataset.action === "staff") { setSection("map"); window.CivicShell?.openEditor?.(); return; }
      if (button.dataset.action === "logout") { window.CivicShell?.api?.logout?.().then(renderAccount, renderAccount); return; }
      if (button.dataset.section === "more" && !button.closest(".birge-more-menu, .birge-account")) { toggleMore(button); return; }
      if (button.closest(".birge-more-menu")) closeMore();
      if (button.dataset.section) setSection(button.dataset.section);
      else if (button.dataset.mode) setMode(button.dataset.mode);
      else if (button.dataset.lang && i18n()) i18n().setLang(button.dataset.lang);
    };
    header.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button || !header.contains(button) || button === avatar) return;
      act(button);
    });
    account.addEventListener("click", (event) => {
      const item = event.target.closest(".bk-menu__item");
      if (item && item.tagName === "BUTTON") act(item);
      if (!accountMenu && item) { account.hidden = true; avatar.setAttribute("aria-expanded", "false"); }
    });
    document.addEventListener("keydown", (event) => { if (event.key === "Escape" && moreOpen()) closeMore(true); });
    // Окно изменило размер — капсула разделов сдвинулась (или ушла в меню аватара): открытое «Ещё» закрываем, а не
    // оставляем висеть на прежнем месте.
    window.addEventListener("resize", () => { if (moreOpen()) closeMore(); });
    document.addEventListener("click", (event) => {
      if (moreOpen() && !event.target.closest?.(".birge-more-menu, [data-section=more]")) closeMore();
    });
    window.CivicShell?.api?.onSession?.(() => renderAccount());
  }
  // Меню аватара: [разделы — только в компактной шапке] · «Чей вид»: Акимат / Житель · «Для сотрудников» (после входа —
  // «Кабинет сотрудника») · «Выйти» (только после входа).
  function renderAccount(focusFirst) {
    if (!account) return;
    const items = [];
    const item = (attrs, text) => { const b = el("button", { type: "button", class: "bk-menu__item", role: "menuitem", ...attrs }); b.textContent = text; return b; };
    if (document.body.dataset.birgeHeader === "compact") {
      for (const id of NAV[state.mode].filter((x) => x !== "more" && available(x, state.mode))) {
        const b = menuIcon(id === "mine" ? item({ "data-action": "mine" }, t("common.nav.mine")) : item({ "data-section": id }, navTitle(id)), id);
        if (id === state.section) b.setAttribute("aria-current", "page");
        if (id === "mine" && mineChanges > 0) {
          const badge = el("span", { class: "bk-nav__badge", "aria-hidden": "true" });
          badge.textContent = mineChanges > 9 ? "9+" : String(mineChanges);
          b.append(badge);
        }
        items.push(b);
      }
      for (const id of moreItems(state.mode)) {  // «Ещё» в меню аватара — сразу пунктами (вложенных меню нет)
        const extra = state.extra.find((x) => x.id === id);
        const b = extra?.href ? el("a", { role: "menuitem", class: "bk-menu__item", href: extra.href }) : item({ "data-section": id }, "");
        b.textContent = navTitle(id);
        menuIcon(b, id);
        if (id === state.section) b.setAttribute("aria-current", "page");
        items.push(b);
      }
      items.push(el("div", { class: "bk-menu__sep", role: "separator" }));
    }
    const label = el("p", { class: "bk-menu__label" }); label.textContent = t("common.role.label");
    items.push(label);
    for (const m of MODES) items.push(item({ "data-mode": m, role: "menuitemradio", "aria-checked": String(m === state.mode) }, t("common.role." + m)));
    items.push(el("div", { class: "bk-menu__sep", role: "separator" }));
    const signedIn = !!window.CivicShell?.api?.session?.authenticated;
    items.push(menuIcon(item({ "data-action": "staff" }, t(signedIn ? "staff.cabinet.title" : "shell.staff.open")), "staff"));
    if (signedIn) items.push(item({ "data-action": "logout" }, t("staff.login.logout")));
    account.replaceChildren(...items);
    account.setAttribute("aria-label", t("common.account.menu"));
    if (focusFirst && !account.hidden) account.querySelector(".bk-menu__item")?.focus();
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
      // Эталон A: на главной акимата панели нет — главное слева в сводке «Сегодня в Астане» (R08, birge-ref.js).
      const today = document.getElementById("birge-today");
      const todayShown = today && !today.hidden && today.getClientRects().length;
      const target = state.section === "day" ? document.getElementById("birge-day-title")
        : state.section !== "map" ? document.getElementById("birge-screen-title")
        : state.mode === "resident" && fab && getComputedStyle(fab).display !== "none" ? fab
        : todayShown ? today.querySelector("button, [tabindex]:not([tabindex='-1']), a[href]")
        : document.querySelector("#birge-heat-root button, #birge-heat-root [tabindex], #birge-heat-root a[href]");
      if (target) target.focus();
    });
    document.body.prepend(skip);
  }

  // «Мои обращения»: единственный бейдж меню (IA_WAVE2 §1) — число новых изменений по обращениям жителя. R09 шлёт
  // window "birge:complaint-changes" {detail: {n}} (после открытия «Мои обращения» n = 0). На телефоне — точка на ≡.
  let mineChanges = 0;
  function labelMine() {
    const mine = header && header.querySelector(".birge-mine-btn");
    if (!mine) return;
    mine.textContent = t("common.nav.mine");
    if (mineChanges > 0) {
      const badge = el("span", { class: "bk-nav__badge birge-badge", "aria-hidden": "true" });
      badge.textContent = mineChanges > 9 ? "9+" : String(mineChanges);
      mine.append(badge);
      mine.setAttribute("aria-label", t("common.nav.mine") + " · " + t("shell.nav.badge", { n: mineChanges }));
    } else mine.removeAttribute("aria-label");
    header.dataset.mineChanges = mineChanges > 0 ? "yes" : "no";
    // Компактная шапка: разделы в меню аватара — точка на аватаре (ui-kit .bk-avatar[data-badge]).
    const avatar = header.querySelector(".birge-avatar");
    if (avatar) { if (mineChanges > 0 && state.mode === "resident") avatar.dataset.badge = ""; else delete avatar.dataset.badge; }
  }
  window.addEventListener("birge:complaint-changes", (event) => {
    const n = Math.max(0, Math.floor(Number(event && event.detail && event.detail.n) || 0));
    if (n === mineChanges) return;
    mineChanges = n;
    labelMine();
  });

  function render() {
    if (skip) skip.textContent = t("common.action.skip_to_main");
    if (header) {
      header.querySelector(".birge-nav").setAttribute("aria-label", t("shell.nav.label"));
      header.querySelector(".birge-lang").setAttribute("aria-label", t("common.lang.label"));
      buildNav();
      labelMine();
      // Открыты «Мои обращения» (окно R09 поверх карты, html.bc-mine-open) — выбран этот пункт, а не «Карта».
      const mineOpen = document.documentElement.classList.contains("bc-mine-open") && state.section === "map";
      const mineBtn = header.querySelector(".birge-mine-btn");
      if (mineBtn) {
        mineBtn.setAttribute("aria-pressed", String(mineOpen));
        if (mineOpen) mineBtn.setAttribute("aria-current", "page"); else mineBtn.removeAttribute("aria-current");
      }
      for (const b of header.querySelectorAll(".birge-nav > [data-section]")) {
        b.textContent = navTitle(b.dataset.section);
        // «Ещё» подсвечен и на экранах, открытых из него.
        const current = (b.dataset.section === state.section && !(mineOpen && b.dataset.section === "map"))
          || (b.dataset.section === "more" && moreItems(state.mode).includes(state.section));
        b.setAttribute("aria-pressed", String(current));
        if (current) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
      }
      for (const b of header.querySelectorAll("[data-lang]")) {
        b.textContent = t("common.lang." + b.dataset.lang);
        b.setAttribute("aria-pressed", String(b.dataset.lang === lang()));
        b.setAttribute("lang", b.dataset.lang);
      }
      const avatar = header.querySelector(".birge-avatar");
      if (avatar) { avatar.setAttribute("aria-label", t("common.account.menu")); avatar.title = t("common.account.menu"); }
      renderAccount();
      requestAnimationFrame(placeHeader);
    }
    if (document.body.classList.contains("civic-mode")) {
      const title = document.querySelector(".brand-title");
      const sub = document.querySelector(".brand-sub");
      if (title) title.textContent = "Birge";
      document.body.classList.add("birge-ready");  // первый кадр до скриптов — birge.css (R07 M.10 R01-2)
      if (sub) sub.textContent = t("shell.brand.tagline");
      const brand = document.querySelector(".topbar .brand");
      if (brand) {
        brand.setAttribute("role", "link"); brand.tabIndex = 0;
        brand.setAttribute("aria-label", "Birge — " + t("common.nav.map")); brand.title = t("common.nav.map");
      }
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
    requestAnimationFrame(placeHeader);  // длина меню и языка меняет место для поиска в шапке
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
      illustration(kind === "error" ? "offline" : "list"),
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
      illustration(kind === "error" ? "offline" : "list"),
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
  function renderScreen() {
    if (!screen) return;
    const id = state.section;
    if (id === "map" || id === "day") return;
    screen.querySelector("#birge-screen-title").textContent = navTitle(id);
    const root = screen.querySelector("#birge-screen-root");
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

  // ------------------------------------------------------------------ шапка: поиск и разделы (чистый дизайн)
  // Поиск — одно поле между знаком и разделами, 200–520 px (R11 CLEAN_PASS №1–2): районы, места, улицы (explore.js).
  // Разделы в строку, если поле при этом не уже 200 px; иначе — в меню аватара (body[data-birge-header="compact"]).
  // Телефон: шапка всегда компактная — знак · поиск («Іздеу / Поиск», от 120 px) · ҚАЗ · РУС · аватар.
  const SEARCH_MIN = 200, SEARCH_MAX = 520, SEARCH_MIN_PHONE = 120;
  function placeHeader() {
    const box = document.querySelector(".civic-explore"), brand = document.querySelector(".topbar .brand");
    const d = document.body.dataset;
    if (!header || !brand || !document.body.classList.contains("civic-mode")) { d.birgeExplore = "map"; return; }
    const wasCompact = d.birgeHeader === "compact";
    if (d.birgeLayout === "ref") { if (innerWidth >= PHONE) placeRef(box, wasCompact); else placeRefPhone(box, wasCompact); return; }
    // Замер синхронно, до отрисовки кадра: промежуточная раскладка не мигает.
    if (innerWidth < PHONE) d.birgeHeader = "compact";
    else {
      delete d.birgeHeader;
      const gap = header.getBoundingClientRect().left - brand.getBoundingClientRect().right - 32;
      if (gap < SEARCH_MIN) d.birgeHeader = "compact";
    }
    if (wasCompact !== (d.birgeHeader === "compact")) renderAccount();
    // Поиска ещё нет (панель монтируется, когда готова карта) — место не решено: поле скрыто до первой раскладки
    // (birge.css), иначе на телефоне на кадр мелькала прежняя «Территория ▾».
    if (!box) { delete d.birgeExplore; return; }
    const phone = innerWidth < PHONE, pad = phone ? 8 : 16;
    const bar = brand.closest(".topbar").getBoundingClientRect();
    // Телефон: слово «Birge» в шапке с поиском скрыто (birge.css) — поле начинается сразу за знаком.
    const anchor = phone ? brand.querySelector(".brand-mark") || brand : brand;
    const left = anchor.getBoundingClientRect().right + pad, right = header.getBoundingClientRect().left - pad;
    if (right - left < (phone ? SEARCH_MIN_PHONE : SEARCH_MIN)) { d.birgeExplore = "map"; return; }
    d.birgeExplore = "header";
    box.style.setProperty("--be-left", Math.round(left) + "px");
    const width = Math.round(Math.min(SEARCH_MAX, right - left));
    box.style.setProperty("--be-width", width + "px");
    // Подсказка поля — по его ширине (как explore.js relabel): < 300 px — короткая «Поиск / Іздеу».
    const input = box.querySelector(".civic-explore-field input");
    if (input) input.placeholder = t(phone || width < 300 ? "common.search.short" : "common.search.placeholder_clean");
    box.style.setProperty("--be-top", Math.round(bar.top + (bar.height - 48) / 2) + "px");
  }
  // Эталон A (birge-ref.js, birge-ref.css), ноутбук: полосы шапки нет. Поиск — 20 / 20, до 388 px; «ҚАЗ · РУС» + аватар —
  // капсула справа; разделы — капсула по центру экрана, а если не помещается — по центру места между поиском и профилем.
  // Поиск сужается до 280 px; разделы не помещаются и тогда — в меню аватара (compact), как в прежней шапке.
  const REF_SEARCH = 388, REF_SEARCH_MIN = 280, REF_EDGE = 20, REF_GAP = 12;
  function placeRef(box, wasCompact) {
    const d = document.body.dataset;
    const nav = header.querySelector(".birge-nav"), me = header.querySelector(".birge-me");
    delete d.birgeHeader;   // капсула разделов видна — замер её ширины (синхронно, до кадра)
    delete d.birgeNav;
    const meLeft = me ? me.getBoundingClientRect().left : innerWidth - REF_EDGE;
    const roomFor = () => meLeft - REF_GAP - REF_EDGE - REF_GAP - (nav ? nav.getBoundingClientRect().width : 0);  // ширина поиску
    let room = roomFor();
    // Не помещается с полями кнопок 16 — пробуем поля 12 (VISUAL_BRIEF раунда 15 §3, 1024 px): так на 1024 РУС и на
    // 1100 ҚАЗ разделы остаются в капсуле, а не уходят в меню аватара. Не помещается и так — меню аватара, как раньше.
    if (room < REF_SEARCH_MIN && nav) {
      d.birgeNav = "tight";
      room = roomFor();
      if (room < REF_SEARCH_MIN) delete d.birgeNav;
    }
    let width = Math.min(REF_SEARCH, Math.floor(room));
    if (width < REF_SEARCH_MIN) {
      d.birgeHeader = "compact";
      width = Math.max(REF_SEARCH_MIN, Math.min(REF_SEARCH, Math.floor(meLeft - REF_GAP - REF_EDGE)));
      document.body.style.removeProperty("--birge-nav-left");
    } else {
      const navWidth = nav ? nav.getBoundingClientRect().width : 0;
      const from = REF_EDGE + width + REF_GAP, to = meLeft - REF_GAP, centre = innerWidth / 2;
      const fitsCentre = centre - navWidth / 2 >= from && centre + navWidth / 2 <= to;
      document.body.style.setProperty("--birge-nav-left", Math.round(fitsCentre ? centre : (from + to) / 2) + "px");
    }
    if (wasCompact !== (d.birgeHeader === "compact")) renderAccount();
    if (!box) { delete d.birgeExplore; return; }
    d.birgeExplore = "header";
    box.style.setProperty("--be-left", REF_EDGE + "px");
    box.style.setProperty("--be-top", REF_EDGE + "px");
    box.style.setProperty("--be-width", width + "px");
    fitPlaceholder(box.querySelector(".civic-explore-field input"));
  }
  // Подсказка поля — длинная «Улица, остановка или район», если помещается целиком; иначе «Поиск / Іздеу»
  // (обрезанная «Улица, остановка или рай…» на 1024 РУС выглядела ошибкой). Ширину текста меряем шрифтом поля.
  const LONG_HINT_MIN = 220;   // без canvas: уже 220 px длинная подсказка не помещается
  let measureCtx = null;
  function fitPlaceholder(input) {
    if (!input) return;
    const long = t("common.search.placeholder_clean");
    let fits = input.clientWidth >= LONG_HINT_MIN;
    try {
      measureCtx = measureCtx || document.createElement("canvas").getContext("2d");
      const cs = getComputedStyle(input);
      measureCtx.font = cs.fontWeight + " " + cs.fontSize + " " + cs.fontFamily;
      fits = measureCtx.measureText(long).width <= input.clientWidth - 4;
    } catch (e) { /* без canvas — по ширине поля */ }
    input.placeholder = fits ? long : t("common.search.short");
  }
  // Эталон A, телефон (экран «Житель, телефон», VISUAL_BRIEF раунда 15 §3): сверху одно поле поиска во всю ширину —
  // 8 от краёв и сверху, как прежняя капсула шапки (кнопки карты и легенда остаются на своих местах). В поле слева —
  // знак Birge (тот же домик, что на ноутбуке), справа — «ҚАЗ · РУС» (пока их нет в шторке R09) и аватар: они стоят
  // поверх правого края поля (birge-ref.css), поле оставляет под них место (--birge-me-w). Разделы — в меню аватара.
  const PHONE_EDGE = 8;
  function placeRefPhone(box, wasCompact) {
    const d = document.body.dataset;
    d.birgeHeader = "compact";
    delete d.birgeNav;
    document.body.style.removeProperty("--birge-nav-left");
    if (!wasCompact) renderAccount();
    if (!box) { delete d.birgeExplore; return; }
    d.birgeExplore = "header";
    const me = header.querySelector(".birge-me");
    box.style.setProperty("--be-left", PHONE_EDGE + "px");
    box.style.setProperty("--be-top", PHONE_EDGE + "px");
    box.style.setProperty("--be-width", Math.round(innerWidth - 2 * PHONE_EDGE) + "px");
    box.style.setProperty("--birge-me-w", (me ? Math.ceil(me.getBoundingClientRect().width) : 44) + "px");
    fitPlaceholder(box.querySelector(".civic-explore-field input"));
  }
  // Строка о запасном фоне карты (R11 CLEAN_PASS №7) гаснет через 6 с после показа или смены текста.
  function watchMapStatus() {
    const status = document.getElementById("map-status");
    if (!status || typeof MutationObserver !== "function") return;
    let timer = null, last = "";
    // Гаснет через 6 с (CLEAN_PASS R01 №7). Без интернета карта повторяет ошибку тайлов и переписывает тот же текст —
    // это не новое сообщение: таймер не сбрасываем (R11 FINAL-3 №5: плашка «висела» и на 375×667 закрывала место).
    const shown = () => {
      const text = status.classList.contains("hidden") ? "" : status.textContent.trim();
      if (text === last) return;
      last = text;
      clearTimeout(timer);
      delete status.dataset.faded;
      if (!text) return;
      timer = setTimeout(() => { status.dataset.faded = "1"; }, 6000);
    };
    new MutationObserver(shown).observe(status, { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ["class"] });
    shown();
    // Панель построена заново (возврат из «Учебной модели» / «Школ»): та же плашка снова видна 6 с.
    return () => { last = ""; shown(); };
  }
  // ------------------------------------------------------------------ стекло (R11 GLASS.md §4 R01, решение владельца 12 окт)
  // Классы ui-kit .bk-glass / .bk-glass--control — только вид (фон, размытие, край, тень); раскладку задаёт birge.css.
  // Не стекло: значки карты, формы, главные кнопки, тосты.
  const GLASS = [
    [".topbar", "bk-glass bk-glass--bar"],                       // №1 шапка — плавающая капсула
    ["#birge-account, .birge-more-menu, #birge-layer-list", "bk-glass bk-glass--menu"],   // №2 меню (радиус 18, ui-kit 58b28edc)
    // «?» легенды — не отдельное стекло: плоская кнопка внутри стеклянной строки (ui-kit R11 «стекло в стекле», R10 G-2).
    ["#birge-locate, #toggle-3d, #birge-layer-btn, #birge-compass, .map-tools .bk-mapctl__group", "bk-glass--control"],  // №3
    [".birge-legend-line", "bk-glass bk-glass--bar"],             // №4 строка легенды
    ["#civic-panel", "bk-glass"],                                 // №5 панель / шторка
    ["#birge-day, #birge-screen", "bk-glass"],                    // №6 лист раздела
    ["#map-status", "bk-glass bk-glass--bar"],                    // №7 плашка о запасном фоне
    [".civic-explore-registry", "bk-glass bk-glass--bar"],        // «Реестр пуст…» — строка над картой, не плашка раунда 13
  ];
  function glassify() {
    if (!document.body.classList.contains("civic-mode")) return;
    let moved = false;
    for (const [selector, classes] of GLASS)
      for (const node of document.querySelectorAll(selector)) {
        const list = classes.split(" ");
        if (list.every((c) => node.classList.contains(c))) continue;
        node.classList.add(...list);
        if (node.classList.contains("topbar")) moved = true;
      }
    if (moved) requestAnimationFrame(placeHeader);  // шапка стала капсулой — поле поиска заново по её середине
  }
  // №8: стекло дорогое для слабой видеокарты. Если карта при движении даёт < 30 кадров/с два раза подряд — непрозрачный
  // белый вид (html.bk-glass-off) до конца сессии, один раз, без мигания. ?glass=off / ?glass=on — вручную (проверки).
  function watchGlass() {
    const root = document.documentElement, q = /[?&]glass=(on|off)(&|$)/.exec(location.search);
    let stored = null;
    try { stored = sessionStorage.getItem("birge.glass"); } catch (e) { /* хранилище закрыто — без запоминания */ }
    if ((q && q[1] === "off") || (!q && stored === "off")) root.classList.add("bk-glass-off");
    glassify();
    if (typeof MutationObserver === "function") {
      let queued = false;
      new MutationObserver(() => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(() => { queued = false; glassify(); });
      }).observe(document.body, { childList: true, subtree: true });
    }
    if (q || root.classList.contains("bk-glass-off")) return;
    let slow = 0, timer = null;
    const watchMap = () => {
      const m = currentMapObject();
      if (!m || typeof m.on !== "function") { timer = setTimeout(watchMap, 1000); return; }
      let frames = 0, started = 0, running = false;
      const tick = () => { if (!running) return; frames++; requestAnimationFrame(tick); };
      m.on("movestart", () => { running = true; frames = 0; started = performance.now(); requestAnimationFrame(tick); });
      m.on("moveend", () => {
        running = false;
        const ms = performance.now() - started;
        if (ms < 600 || root.classList.contains("bk-glass-off")) return;   // короткий сдвиг — не мерило
        const fps = frames * 1000 / ms;
        slow = fps < 30 ? slow + 1 : 0;
        if (slow >= 2) {
          root.classList.add("bk-glass-off");
          try { sessionStorage.setItem("birge.glass", "off"); } catch (e) { /* без запоминания */ }
        }
      });
    };
    watchMap();
    void timer;
  }
  function watchExplore() {
    const reshowStatus = watchMapStatus() || (() => {});
    const again = () => requestAnimationFrame(placeHeader);
    window.addEventListener("resize", again);
    document.addEventListener("civic:mode", again);
    // Шрифт Inter догрузился — ширина разделов и подсказки поиска другая (fitPlaceholder, капсула разделов).
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(again, () => {});
    if (typeof ResizeObserver === "function" && header) {
      const ro = new ResizeObserver(again);
      ro.observe(header);
      // Телефон, эталон: «ҚАЗ · РУС» прячутся, пока видна шторка R09, — место в поле поиска меняется (placeRefPhone).
      const me = header.querySelector(".birge-me");
      if (me) ro.observe(me);
    }
    // Панель монтирует shell.js, когда готова карта: ловим её появление (и пересоздание при смене режима).
    const root = document.getElementById("civic-root") || document.body;
    const isExplore = (n) => n.nodeType === 1 && (n.classList?.contains("civic-explore") || n.querySelector?.(".civic-explore"));
    if (typeof MutationObserver === "function") new MutationObserver((records) => {
      // Сразу, до отрисовки кадра (наблюдатель — микрозадача): поле встаёт в шапку без промежуточного вида.
      if (records.some((r) => [...r.addedNodes].some(isExplore))) { placeHeader(); reshowStatus(); }
    }).observe(root, { childList: true, subtree: true });
    again();
  }

  // ------------------------------------------------------------------ кнопки карты капсулой (R11 CLEAN_PASS №5)
  // «Моё место» · [+ | −] одной капсулой · 3D · слои; компас вместо «Повернуть» — виден, только когда карта повёрнута
  // или наклонена (нажатие — на север и плоско). «Вся Астана» — пункт поиска в шапке, отдельной кнопки нет.
  // Телефон: пока как на ноутбуке (+/− и 3D скрыть — вопрос владельцу, R11 CLEAN_PASS §6.2).
  let compass = null, compassMap = null;
  function buildMapControls() {
    const tools = document.querySelector(".map-tools");
    if (!tools || tools.dataset.birgeCtl) return;
    tools.dataset.birgeCtl = "1";
    tools.classList.add("bk-mapctl");
    const icon = (name) => '<svg class="ic" aria-hidden="true"><use href="/civic/ui-kit/icons.svg#i-' + name + '"></use></svg>';
    const locate = el("button", { type: "button", id: "birge-locate", class: "icon-btn bk-mapbtn birge-locate" });
    locate.innerHTML = icon("locate");
    compass = el("button", { type: "button", id: "birge-compass", class: "icon-btn bk-mapbtn bk-compass birge-compass", hidden: true });
    compass.innerHTML = icon("compass");
    const zin = document.getElementById("zoom-in"), zout = document.getElementById("zoom-out");
    if (zin && zout) {
      const group = el("div", { class: "bk-mapctl__group birge-zoom" });
      zin.before(group);
      group.append(zin, zout);
    }
    tools.prepend(compass, locate);
    locate.addEventListener("click", () => {
      const m = currentMapObject();
      const fail = () => window.BirgeUI?.toast?.(t("shell.map.locate_failed"));
      if (!m || !navigator.geolocation) { fail(); return; }
      navigator.geolocation.getCurrentPosition((pos) => {
        m.easeTo({ center: [pos.coords.longitude, pos.coords.latitude], zoom: Math.max(m.getZoom(), 15), duration: 900 });
      }, fail, { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 });
    });
    compass.addEventListener("click", () => { currentMapObject()?.easeTo({ bearing: 0, pitch: 0, duration: 600 }); });
    bindCompass();
  }
  function syncCompass() {
    const m = compassMap;
    if (!compass || !m) return;
    const bearing = m.getBearing(), pitch = m.getPitch();
    compass.hidden = Math.abs(bearing) < 0.5 && pitch < 1;
    compass.style.setProperty("--bearing", (-bearing).toFixed(1) + "deg");
  }
  function bindCompass() {
    const m = currentMapObject();
    if (!m) { setTimeout(bindCompass, 500); return; }
    if (compassMap === m) return;
    compassMap = m;
    m.on("rotate", syncCompass);
    m.on("pitch", syncCompass);
    m.on("moveend", syncCompass);
    syncCompass();
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
      return el("label", { class: "birge-layer__opt bk-menu__radio" }, [input, el("span", { text })]);  // как пункт меню (R11 §11.1)
    };
    listBox.replaceChildren(el("span", { class: "birge-layer__title bk-menu__label", text: t("shell.layers.label") }),
      option("", t("shell.layers.none")), ...list.map((l) => option(l.id, layerTitle(l))));
  }

  function setSection(section, options) {
    section = ROUTE_ALIAS[section] || section;  // прежние имена (#complaints, #ask) — и из кода ролей
    if (!SECTIONS.includes(section)) section = "map";
    // «Картина дня» — экран акимата; житель всегда на карте. Раздел другого вида переключает вид (ссылка, «Ещё»).
    if (section === "day" && state.mode === "resident") setMode("akimat");
    else if (section !== "map" && section !== "day" && !screenModes(section).includes(state.mode)) {
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
    buildMapControls();
    watchExplore();
    watchGlass();
    // Карточка цели открылась (R07 «birge:heat-select») — панель/шторка с начала: на телефоне шторка оставалась
    // прокрученной списком, и первая строка карточки уходила под ручку (R11 марафон §9.1 e).
    document.addEventListener("birge:heat-select", (event) => {
      if (!event.detail || !event.detail.target) return;
      const scroll = document.getElementById("civic-scroll");
      if (scroll) scroll.scrollTop = 0;
    });
    // «Мои обращения» R09 открываются и закрываются сами (класс html.bc-mine-open) — пункт в шапке следует за ними.
    if (typeof MutationObserver === "function") {
      let mineWas = false;
      new MutationObserver(() => {
        const now = document.documentElement.classList.contains("bc-mine-open");
        if (now !== mineWas) { mineWas = now; render(); }
      }).observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    }
    // R12 волна 2 п. 6: QR-таблички — отдельная страница печати (web/civic/qr/print.html); пункт «Ещё → QR-таблички»
    // у акимата появляется, когда в сборке есть модуль QR R12 (report.js). Скрипты defer: проверяем после всех.
    const linkQr = () => { if (window.BirgeReport && !screenModule("qr")) registerScreen({ id: "qr", href: "/civic/qr/print.html" }); };
    if (document.readyState === "complete") linkQr();
    else { document.addEventListener("DOMContentLoaded", linkQr, { once: true }); window.addEventListener("load", linkQr, { once: true }); }
    // Разделы — адрес #day, #nearby, #ideas, #more…; прочие адреса (#object=, #target=, #school) — карта, как раньше.
    const routeOf = () => { const h = ROUTE_ALIAS[location.hash.slice(1)] || location.hash.slice(1); return SECTIONS.includes(h) ? h : "map"; };
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
    // Палитра команд (birge-ref.js): разделы «Ещё» этого вида и подпись раздела на языке интерфейса.
    moreItems: () => moreItems(state.mode),
    navTitle: (id) => navTitle(id),
    api: { v2, ApiError: BirgeApiError },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
