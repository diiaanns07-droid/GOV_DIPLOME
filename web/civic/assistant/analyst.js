/*
 * Birge · «Спросить Birge» — ИИ-аналитик акима (R03, раунд 15).
 * Вопрос словами → короткий ответ с числами из данных Birge и кнопкой «Показать на карте».
 *
 *   <link rel="stylesheet" href="/civic/assistant/analyst.css">
 *   <script src="/civic/assistant/analyst.js"></script>
 *   BirgeAnalyst.mount(element, { apiBase: "/api/civic/v2", api, lang, openTarget, openSection, titleTag })
 *     → { setLang, destroy, ask(question) }
 *
 * Имя window.BirgeAnalyst, а не BirgeAsk: BirgeAsk уже занят экраном R13 «Вопрос акиму» (web/civic/qa/qa.js).
 * В оболочке R01 экран регистрируется сам: BirgeShell.registerScreen({ id: "analyst", modes: ["akimat"] }) —
 * пункт в «Ещё» и в палитре Ctrl+K; место в меню решает R11.
 *
 * Данные: POST /api/civic/v2/assistant/ask {question, lang} → ответ schema birge-analyst-answer-v1
 * (agent/civic_assistant/analyst/core.py). Ответ содержит тексты ru и kk — смена ҚАЗ / РУС без нового запроса.
 * Числа считает сервер (код), экран их только показывает. Тексты — через textContent, без innerHTML.
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var VERSION = "r15-analyst-1";
  var SKELETON_DELAY = 150;   // скелетон не раньше 150 мс (COMMON «Качество»)
  var MAX_QUESTION = 500;
  var HISTORY = 5;
  var scriptBase = ((doc.currentScript && doc.currentScript.src) || "").replace(/[^/]*$/, "");
  var ICONS = scriptBase + "../ui-kit/icons.svg";

  // Ключи для словаря R11 (передаются в INTEGRATION.txt). Словарь главнее: есть ключ в BirgeI18n — берём его.
  var KEYS = {
    ru: {
      "analyst.title": "Спросить Birge",
      "analyst.subtitle": "Вопрос словами — ответ с числами из данных Birge",
      "analyst.input_label": "Ваш вопрос",
      "analyst.placeholder": "Например: где в Нуре больше всего жалоб на снег?",
      "analyst.ask": "Спросить",
      "analyst.clear": "Очистить",
      "analyst.chips_label": "Примеры вопросов",
      "analyst.empty_title": "Спросите о городе",
      "analyst.empty_text": "Горячие места, службы, кризис, работы, инициативы — ответ с числами за секунду.",
      "analyst.empty_action": "Главное за сегодня",
      "analyst.empty_question": "Что сегодня главное?",
      "analyst.loading": "Считаем по данным…",
      "analyst.offline": "Офлайн-режим",
      "analyst.offline_hint": "Ответ собран кодом по данным Birge, без языковой модели",
      "analyst.llm": "Текст — модель, числа — код",
      "analyst.llm_hint": "Языковая модель выбрала порядок и вводную фразу; все числа посчитал код",
      "analyst.how": "Как получен ответ",
      "analyst.how_summary": "{calls} · {ms}",
      "analyst.calls": { one: "{n} источник", few: "{n} источника", many: "{n} источников" },
      "analyst.ms": "{n} мс",
      "analyst.understood": "Как понят вопрос",
      "analyst.u.district": "район",
      "analyst.u.category": "тема",
      "analyst.u.service": "служба",
      "analyst.u.days": "период, дней",
      "analyst.u.lang": "язык вопроса",
      "analyst.u.lang.ru": "русский",
      "analyst.u.lang.kk": "казахский",
      "analyst.u.lang.mixed": "вперемешку",
      "analyst.status.ok": "есть данные",
      "analyst.status.empty": "данных за период нет",
      "analyst.status.not_ready": "пока нет данных",
      "analyst.status.error": "не ответил",
      "analyst.mode": "Режим",
      "analyst.reason.no_key": "ключ модели не задан",
      "analyst.reason.question_has_instructions": "в вопросе были инструкции — модель не вызывалась",
      "analyst.reason.llm_timeout": "модель не ответила за 8 секунд",
      "analyst.reason.llm_error": "модель недоступна",
      "analyst.reason.llm_busy": "модель занята",
      "analyst.reason.other": "ответ модели отклонён",
      "analyst.show_on_map": "Показать на карте",
      "analyst.open_place": "Показать «{name}» на карте",
      "analyst.history": "Недавние вопросы",
      "analyst.demo": "Пример",
      "analyst.demo_hint": "Пример для показа, не настоящие данные",
      "analyst.error.network_title": "Нет связи с сервером",
      "analyst.error.network_text": "Проверьте интернет и нажмите «Повторить».",
      "analyst.error.retry": "Повторить",
      "analyst.error.login_title": "Только для сотрудников акимата",
      "analyst.error.login_text": "Войдите как сотрудник: аватар → «Для сотрудников».",
      "analyst.error.rate_title": "Слишком много вопросов подряд",
      "analyst.error.rate_text": "Подождите минуту и спросите снова.",
      "analyst.error.not_ready_title": "«Спросить Birge» ещё не подключён",
      "analyst.error.not_ready_text": "Эта часть появится в следующей сборке.",
      "analyst.error.server_title": "Не удалось ответить",
      "analyst.error.server_text": "Попробуйте ещё раз через минуту.",
      "analyst.error.empty": "Напишите вопрос",
      "analyst.error.long": "Не больше 500 знаков",
    },
    kk: {
      "analyst.title": "Birge-ден сұрау",
      "analyst.subtitle": "Сұрақ сөзбен — жауап Birge деректеріндегі сандармен",
      "analyst.input_label": "Сұрағыңыз",
      "analyst.placeholder": "Мысалы: Нұрада қар туралы шағым қай жерде көп?",
      "analyst.ask": "Сұрау",
      "analyst.clear": "Тазалау",
      "analyst.chips_label": "Сұрақ үлгілері",
      "analyst.empty_title": "Қала туралы сұраңыз",
      "analyst.empty_text": "Шағымы көп орындар, қызметтер, дағдарыс, жұмыстар, бастамалар — сандармен жауап бір секундта.",
      "analyst.empty_action": "Бүгінгі басты жаңалық",
      "analyst.empty_question": "Бүгін не басты?",
      "analyst.loading": "Деректер бойынша есептеп жатырмыз…",
      "analyst.offline": "Офлайн режим",
      "analyst.offline_hint": "Жауапты код Birge деректері бойынша құрады, тілдік модельсіз",
      "analyst.llm": "Мәтін — модель, сандар — код",
      "analyst.llm_hint": "Тілдік модель тек реті мен кіріспе сөйлемді таңдады; барлық санды код есептеді",
      "analyst.how": "Жауап қалай алынды",
      "analyst.how_summary": "{calls} · {ms}",
      "analyst.calls": "{n} дереккөз",
      "analyst.ms": "{n} мс",
      "analyst.understood": "Сұрақ қалай түсінілді",
      "analyst.u.district": "аудан",
      "analyst.u.category": "тақырып",
      "analyst.u.service": "қызмет",
      "analyst.u.days": "кезең, күн",
      "analyst.u.lang": "сұрақ тілі",
      "analyst.u.lang.ru": "орысша",
      "analyst.u.lang.kk": "қазақша",
      "analyst.u.lang.mixed": "аралас",
      "analyst.status.ok": "дерек бар",
      "analyst.status.empty": "кезеңде дерек жоқ",
      "analyst.status.not_ready": "әзірге дерек жоқ",
      "analyst.status.error": "жауап бермеді",
      "analyst.mode": "Режим",
      "analyst.reason.no_key": "модель кілті берілмеген",
      "analyst.reason.question_has_instructions": "сұрақта нұсқаулар болды — модель шақырылмады",
      "analyst.reason.llm_timeout": "модель 8 секундта жауап бермеді",
      "analyst.reason.llm_error": "модель қолжетімсіз",
      "analyst.reason.llm_busy": "модель бос емес",
      "analyst.reason.other": "модель жауабы қабылданбады",
      "analyst.show_on_map": "Картадан көрсету",
      "analyst.open_place": "«{name}» картадан көрсету",
      "analyst.history": "Соңғы сұрақтар",
      "analyst.demo": "Үлгі",
      "analyst.demo_hint": "Көрсетуге арналған үлгі, нақты дерек емес",
      "analyst.error.network_title": "Сервермен байланыс жоқ",
      "analyst.error.network_text": "Интернетті тексеріп, «Қайталау» түймесін басыңыз.",
      "analyst.error.retry": "Қайталау",
      "analyst.error.login_title": "Тек әкімдік қызметкерлеріне",
      "analyst.error.login_text": "Қызметкер ретінде кіріңіз: аватар → «Қызметкерлерге».",
      "analyst.error.rate_title": "Қатарынан тым көп сұрақ",
      "analyst.error.rate_text": "Бір минут күтіп, қайта сұраңыз.",
      "analyst.error.not_ready_title": "«Birge-ден сұрау» әлі қосылмаған",
      "analyst.error.not_ready_text": "Бұл бөлім келесі жинақта пайда болады.",
      "analyst.error.server_title": "Жауап беру мүмкін болмады",
      "analyst.error.server_text": "Бір минуттан кейін қайталаңыз.",
      "analyst.error.empty": "Сұрақ жазыңыз",
      "analyst.error.long": "500 таңбадан аспасын",
    },
  };
  // Примеры вопросов (чипы): первые три — сцены демо (снег в Нуре, отстающие службы, буран).
  var SUGGESTIONS = [
    // short — подпись чипа в одну строку (R11: длинный вопрос делал чип двухстрочным); в поле уходит полный вопрос
    { ru: "Где в Нуре больше всего жалоб на снег за неделю?", kk: "Нұрада бір аптада қар туралы шағым қай жерде көп?",
      short: { ru: "Снег в Нуре, 7 дней", kk: "Нұрада қар, 7 күн" } },
    { ru: "Какие службы отстают?", kk: "Қай қызметтер артта қалып жатыр?" },
    { ru: "Что с бураном?", kk: "Боран бойынша не жағдай?" },
    { ru: "Какие темы растут за неделю?", kk: "Аптада қай тақырыптар өсті?" },
    { ru: "Сравни районы по жалобам", kk: "Аудандарды шағым бойынша салыстыр",
      short: { ru: "Сравнить районы", kk: "Аудандарды салыстыру" } },
    { ru: "Сколько обращений просрочено?", kk: "Қанша өтініштің мерзімі өтті?" },
  ];
  // Функции экранов соседей, которые открывают конкретную запись (сервер присылает opener {global, fn, arg}).
  // Вызываем только эти имена: ответ сервера не может заставить экран вызвать что-то другое.
  var OPENERS = { "BirgeAgencies.openCrisis": true, "BirgeWorksCalendar.openConflict": true };
  // Где в оболочке раздел, на который ведёт кнопка «Открыть …» (id разделов соседей; нет раздела — кнопки нет).
  var SECTION_ALIASES = { agencies: ["agencies", "services"], crisis: ["crisis", "agencies"],
    "works-calendar": ["works-calendar", "works"], together: ["together", "initiatives"], meetings: ["meetings", "questions"],
    day: ["day"], inbox: ["inbox"] };

  // ------------------------------------------------------------------ тексты
  function i18n() { return root.BirgeI18n || null; }
  function pluralRu(n) {
    var a = Math.abs(n) % 100, b = a % 10;
    if (a > 10 && a < 20) return "many";
    if (b === 1) return "one";
    if (b >= 2 && b <= 4) return "few";
    return "many";
  }
  function makeT(getLang) {
    return function t(key, params) {
      var I = i18n(), lang = getLang();
      if (I && typeof I.has === "function" && I.has(key)) return I.t(key, params);
      var val = (KEYS[lang] && KEYS[lang][key]) || KEYS.ru[key] || key;
      if (val && typeof val === "object") val = val[pluralRu(params && params.n || 0)] || val.many;
      return String(val).replace(/\{(\w+)\}/g, function (m, name) {
        return params && params[name] != null ? String(params[name]) : m;
      });
    };
  }

  // ------------------------------------------------------------------ DOM
  function el(tag, attrs, children) {
    var node = doc.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === false || v == null) return;
      if (k === "text") node.textContent = v;
      else if (k === "className") node.className = v;
      else node.setAttribute(k, v === true ? "" : v);
    });
    (children || []).forEach(function (c) { if (c != null) node.append(c); });
    return node;
  }
  function icon(name, cls) {
    var NS = "http://www.w3.org/2000/svg", svg = doc.createElementNS(NS, "svg"), use = doc.createElementNS(NS, "use");
    svg.setAttribute("class", "ic " + (cls || ""));
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    use.setAttribute("href", ((root.BirgeUI && root.BirgeUI.SPRITE) || ICONS) + "#i-" + name);
    svg.append(use);
    return svg;
  }
  function pick(obj, lang) {
    if (!obj || typeof obj !== "object") return obj == null ? "" : String(obj);
    return obj[lang] != null ? String(obj[lang]) : String(obj.ru || "");
  }
  function fmtMs(ms, t) {
    return ms >= 1000 ? (Math.round(ms / 100) / 10).toString().replace(".", ",") + " с" : t("analyst.ms", { n: Math.round(ms) });
  }

  // ------------------------------------------------------------------ сеть
  function request(opts, question, lang) {
    var body = { question: question, lang: lang };
    if (opts.api && typeof opts.api.v2 === "function") {
      return opts.api.v2("POST", "/assistant/ask", body).catch(function (e) {
        throw { status: e.status || 0, error: e.error || "network" };
      });
    }
    var headers = { "Content-Type": "application/json", Accept: "application/json" };
    var csrf = root.CivicShell && root.CivicShell.csrfToken ? root.CivicShell.csrfToken() : null;
    if (csrf) headers["X-CSRF-Token"] = csrf;
    return root.fetch((opts.apiBase || "/api/civic/v2") + "/assistant/ask", {
      method: "POST", headers: headers, credentials: "same-origin", body: JSON.stringify(body),
    }).then(function (res) {
      return res.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        if (!res.ok) throw { status: res.status, error: (data && data.error) || "error", field: data && data.field };
        if (!data) throw { status: 0, error: "network" };
        return data;
      });
    }, function () { throw { status: 0, error: "network" }; });
  }

  // ------------------------------------------------------------------ экран
  function mount(container, opts) {
    opts = opts || {};
    var state = {
      lang: opts.lang || (i18n() && i18n().getLang ? i18n().getLang() : "ru"),
      status: "idle", answer: null, error: null, question: "", history: [], seq: 0, skelTimer: null, destroyed: false,
    };
    var t = makeT(function () { return state.lang === "kk" ? "kk" : "ru"; });
    var titleTag = /^h[1-4]$/.test(opts.titleTag || "") ? opts.titleTag : "h2";

    var rootEl = el("div", { className: "ba", "data-lang": state.lang });
    var title = el(titleTag, { className: "ba-title", id: "ba-title" });
    var subtitle = el("p", { className: "ba-subtitle" });
    var label = el("label", { className: "bk-sr-only", for: "ba-input" });
    var input = el("input", { id: "ba-input", className: "ba-input", type: "text", maxlength: String(MAX_QUESTION),
      autocomplete: "off", spellcheck: "true", enterkeyhint: "send", "aria-describedby": "ba-field-error" });
    var clearBtn = el("button", { type: "button", className: "ba-clear", hidden: true }, [icon("close")]);
    var askBtn = el("button", { type: "submit", className: "ba-send" }, [icon("send"), el("span", { className: "ba-send__text" })]);
    var fieldError = el("p", { className: "ba-field-error", id: "ba-field-error", role: "alert", hidden: true });
    var form = el("form", { className: "ba-form", role: "search", novalidate: true },
      [label, el("div", { className: "ba-field" }, [icon("message", "ba-field__ic"), input, clearBtn, askBtn]), fieldError]);
    var chips = el("div", { className: "bk-chips ba-chips", role: "group" });
    var live = el("div", { className: "ba-live", "aria-live": "polite", "aria-busy": "false" });
    var historyBox = el("div", { className: "ba-history", hidden: true });
    rootEl.append(el("header", { className: "ba-head" }, [title, subtitle]), form, chips, live, historyBox);
    container.replaceChildren(rootEl);

    function renderStatic() {
      rootEl.dataset.lang = state.lang;
      title.textContent = t("analyst.title");
      subtitle.textContent = t("analyst.subtitle");
      label.textContent = t("analyst.input_label");
      input.placeholder = t("analyst.placeholder");
      input.setAttribute("aria-label", t("analyst.input_label"));
      clearBtn.setAttribute("aria-label", t("analyst.clear"));
      clearBtn.title = t("analyst.clear");
      askBtn.querySelector(".ba-send__text").textContent = t("analyst.ask");
      askBtn.setAttribute("aria-label", t("analyst.ask"));
      chips.setAttribute("aria-label", t("analyst.chips_label"));
      chips.replaceChildren.apply(chips, SUGGESTIONS.map(function (s, i) {
        var b = el("button", { type: "button", className: "bk-chip ba-chip" + (i > 3 ? " ba-chip--extra" : ""),
          text: pick(s.short || s, state.lang), title: pick(s, state.lang) });
        b.addEventListener("click", function () { input.value = pick(s, state.lang); syncClear(); submit(); });
        return b;
      }));
      renderHistory();
    }

    // Прошлые ответы строками под карточкой (IA R11 §5.6): вопрос и главное число; нажатие показывает тот ответ
    // сразу, без нового запроса (числа — на момент того вопроса, время видно в «Как получен ответ»).
    function renderHistory() {
      var items = state.history.filter(function (h) { return h.answer !== state.answer; }).slice(0, 3);
      historyBox.hidden = !items.length || state.status === "loading";
      if (historyBox.hidden) { historyBox.replaceChildren(); return; }
      var list = el("ul", { className: "bk-list ba-history__list" });
      items.forEach(function (h) {
        var n = ((h.answer.blocks || [])[0] || {}).numbers || [];
        var sub = n.length ? (n[0].text != null ? n[0].text : String(n[0].value)) + " " + pick(n[0].label, state.lang) : "";
        var row = el("button", { type: "button", className: "bk-list__item ba-history__item" }, [
          el("span", { className: "bk-list__main" }, [
            el("span", { className: "bk-list__title", text: h.q }),
            sub ? el("span", { className: "bk-list__sub", text: sub }) : null,
          ]),
          icon("chevron-right", "bk-list__chevron"),
        ]);
        row.addEventListener("click", function () {
          state.answer = h.answer; state.question = h.q; state.status = "ready";
          input.value = h.q; syncClear(); render();
        });
        list.append(el("li", null, [row]));
      });
      historyBox.replaceChildren(el("p", { className: "ba-history__title", text: t("analyst.history") }), list);
    }

    function syncClear() { clearBtn.hidden = !input.value; }

    // -------------------------------------------------------------- состояния
    // Пустое состояние по поправке владельца П1: один маленький монохромный значок набора R11 (48 px),
    // короткий текст и одна кнопка. Никаких иллюстраций «для красоты».
    function renderIdle() {
      var start = el("button", { type: "button", className: "bk-btn", text: t("analyst.empty_action") });
      start.addEventListener("click", function () { input.value = t("analyst.empty_question"); syncClear(); submit(); });
      live.replaceChildren(el("div", { className: "bk-empty ba-empty" }, [
        icon("message", "ic--48"),
        el("p", { className: "bk-empty__title", text: t("analyst.empty_title") }),
        el("p", { className: "bk-empty__text", text: t("analyst.empty_text") }),
        start,
      ]));
    }

    function renderSkeleton() {
      live.replaceChildren(el("div", { className: "ba-card ba-skel", "aria-hidden": "true" }, [
        el("span", { className: "bk-skel bk-skel--line ba-skel__eyebrow" }),
        el("span", { className: "bk-skel bk-skel--title" }),
        el("div", { className: "ba-nums" }, [0, 1, 2].map(function () { return el("span", { className: "bk-skel ba-skel__num" }); })),
        el("span", { className: "bk-skel bk-skel--line" }), el("span", { className: "bk-skel bk-skel--line ba-skel__short" }),
      ]), el("p", { className: "bk-sr-only", text: t("analyst.loading") }));
    }

    function renderError() {
      var e = state.error || {};
      var kind = e.status === 0 ? "network" : e.status === 401 || e.status === 403 ? "login"
        : e.status === 429 ? "rate" : e.status === 503 ? "not_ready" : "server";
      var box = el("div", { className: "bk-error ba-error", role: "alert" }, [
        icon(kind === "network" ? "wifi-off" : kind === "login" ? "user" : "alert", "ic--48"),
        el("p", { className: "bk-error__title", text: t("analyst.error." + kind + "_title") }),
        el("p", { className: "bk-error__text", text: t("analyst.error." + kind + "_text") }),
      ]);
      if (kind === "network" || kind === "server" || kind === "rate") {
        var retry = el("button", { type: "button", className: "bk-btn", text: t("analyst.error.retry") });
        retry.addEventListener("click", function () { submit(state.question); });
        box.append(retry);
      }
      live.replaceChildren(box);
    }

    // -------------------------------------------------------------- ответ
    function sectionAvailable(section) {
      var B = root.BirgeShell, ids = SECTION_ALIASES[section] || [section];
      if (typeof opts.openSection !== "function") return null;
      if (!B) return ids[0];
      var avail = [];
      try {
        avail = (B.navItems ? B.navItems() : []).concat(B.moreItems ? B.moreItems() : []);
      } catch (e) { avail = []; }
      for (var i = 0; i < ids.length; i++) if (avail.indexOf(ids[i]) >= 0) return ids[i];
      return null;
    }

    function focusOnMap(action) {
      var tg = action.target || {};
      if (!tg.kind || !tg.id) return;
      if (typeof opts.openTarget === "function") { opts.openTarget(tg.kind, tg.id, action.days); return; }
      var ev = new root.CustomEvent("birge:open-target", { cancelable: true, detail: { target: tg, days: action.days } });
      if (doc.dispatchEvent(ev)) {
        root.location.hash = "#target=" + encodeURIComponent(tg.kind) + ":" + encodeURIComponent(tg.id) +
          (action.days ? "&days=" + action.days : "");
      }
    }

    function actionButton(action, primary) {
      if (action.kind === "map.focus") {
        // Главная кнопка экрана — «Спросить» (IA R11 §5.6); действия ответа — вторичные.
        var b = el("button", { type: "button", className: "bk-btn ba-act", "data-action": "map" },
          [icon("pin"), el("span", { text: pick(action.label, state.lang) || t("analyst.show_on_map") })]);
        b.addEventListener("click", function () { focusOnMap(action); });
        return b;
      }
      if (action.kind === "open") {
        var section = sectionAvailable(action.section);
        if (!section) return null;
        var o = el("button", { type: "button", className: "bk-btn" + (primary ? "" : " bk-btn--ghost") + " ba-act",
          "data-action": "open" },
          [el("span", { text: pick(action.label, state.lang) }), icon("chevron-right")]);
        o.addEventListener("click", function () {
          var op = action.opener, key = op && op.global + "." + op.fn;
          var target = key && OPENERS[key] && root[op.global] && root[op.global][op.fn];
          // Экран соседа сам переключает раздел и открывает запись (кризис, конфликт работ); иначе — просто раздел.
          if (typeof target === "function") {
            try { target.call(root[op.global], op.arg); return; } catch (e) { /* откроем раздел ниже */ }
          }
          opts.openSection(section);
        });
        return o;
      }
      return null;
    }

    // Крупные числа — разметка ui-kit R11 «Спросить Birge» (.bk-answer__nums / __num с <b>).
    function numbersRow(numbers, small) {
      if (!numbers || !numbers.length) return null;
      return el("div", { className: "bk-answer__nums ba-nums" + (small ? " ba-nums--small" : "") },
        numbers.slice(0, 3).map(function (n) {
          return el("p", { className: "bk-answer__num ba-num", "data-tone": n.tone || "neutral" }, [
            el("b", { className: "ba-num__value", text: n.text != null ? n.text : String(n.value) }),
            el("span", { className: "ba-num__label", text: pick(n.label, state.lang) }),
          ]);
        }));
    }

    function itemsList(items) {
      if (!items || !items.length) return null;
      var list = el("ol", { className: "bk-list ba-items" });
      items.slice(0, 5).forEach(function (it) {
        var name = pick(it.label, state.lang);
        var main = el("span", { className: "bk-list__main" }, [
          el("span", { className: "bk-list__title", text: name }),
          (it.sub || it.value_text) ? el("span", { className: "bk-list__sub",
            text: [pick(it.value_text, state.lang), pick(it.sub, state.lang)].filter(Boolean).join(" · ") }) : null,
        ]);
        var dot = it.color ? el("span", { className: "ba-dot", style: "background:" + safeColor(it.color), "aria-hidden": "true" }) : null;
        var row;
        if (it.target && it.target.kind && it.target.id && ["object", "segment", "area"].indexOf(it.target.kind) >= 0) {
          row = el("button", { type: "button", className: "bk-list__item ba-item", "aria-label": t("analyst.open_place", { name: name }) },
            [dot, main, icon("chevron-right", "bk-list__chevron")]);
          row.addEventListener("click", function () { focusOnMap({ target: it.target, days: it.days || (state.answer && state.answer.understood && state.answer.understood.days) }); });
        } else if (it.service && sectionAvailable("agencies")) {
          // Строка службы ведёт на табло служб (R11 R03-7) — с шевроном, как строки мест.
          row = el("button", { type: "button", className: "bk-list__item ba-item" }, [main, icon("chevron-right", "bk-list__chevron")]);
          row.addEventListener("click", function () { opts.openSection(sectionAvailable("agencies")); });
        } else if (it.ask) {
          row = el("button", { type: "button", className: "bk-list__item ba-item" }, [main, icon("chevron-right", "bk-list__chevron")]);
          row.addEventListener("click", function () { input.value = pick(it.ask, state.lang); syncClear(); submit(); });
        } else {
          row = el("div", { className: "bk-list__item ba-item ba-item--static" }, [dot, main]);
        }
        list.append(el("li", null, [row]));
      });
      return list;
    }

    function safeColor(c) { return /^#[0-9a-fA-F]{3,8}$/.test(String(c)) ? c : "transparent"; }

    function blockView(b, first) {
      var lines = (b.lines && b.lines[state.lang]) || (b.lines && b.lines.ru) || [];
      var parts = [];
      if (!first) parts.push(el("h4", { className: "ba-block__title", text: pick(b.title, state.lang) }));
      parts.push(numbersRow(b.numbers, !first));
      var textLines = first ? lines.slice(0, 4) : lines.slice(0, 3);
      if (textLines.length) {
        parts.push(el("p", { className: first ? "bk-answer__text ba-lead" : "ba-text", text: textLines[0] }));
        if (textLines.length > 1) {
          parts.push(el("ul", { className: "ba-lines" }, textLines.slice(1).map(function (l) { return el("li", { text: l }); })));
        }
      }
      if (b.note) parts.push(el("p", { className: "ba-note" }, [icon("info"), el("span", { text: pick(b.note, state.lang) })]));
      parts.push(itemsList(b.items));
      return el("section", { className: "ba-block" + (first ? " ba-block--first" : "") + " ba-block--" + b.status,
        "data-kind": b.kind }, parts);
    }

    function howView(a) {
      var calls = a.calls || [];
      var summary = el("summary", { className: "ba-how__summary" }, [
        el("span", { className: "ba-how__label", text: t("analyst.how") }),
        el("span", { className: "ba-how__meta", text: t("analyst.how_summary", {
          calls: t("analyst.calls", { n: calls.length }), ms: fmtMs(a.ms || 0, t) }) }),
      ]);
      var rows = calls.map(function (c) {
        // На виду — название источника для акима; код модуля и функции — только в подсказке (R11 R03-3).
        return el("li", { className: "ba-call ba-call--" + c.status, title: c.role + " · " + c.module + "." + c.fn }, [
          el("span", { className: "ba-call__name", text: pick(c.name, state.lang) || c.role }),
          el("span", { className: "ba-call__status", text: t("analyst.status." + (c.status || "error")) }),
          el("span", { className: "ba-call__ms", text: fmtMs(c.ms || 0, t) }),
        ]);
      });
      var u = a.understood || {}, uRows = [];
      if (u.district) uRows.push([t("analyst.u.district"), pick(u.district, state.lang)]);
      if (u.category) uRows.push([t("analyst.u.category"), pick(u.category, state.lang)]);
      if (u.service) uRows.push([t("analyst.u.service"), pick(u.service, state.lang)]);
      if (u.days) uRows.push([t("analyst.u.days"), String(u.days)]);
      uRows.push([t("analyst.u.lang"), t("analyst.u.lang." + (a.question_lang || "ru"))]);
      var reason = a.offline_reason ? (KEYS.ru["analyst.reason." + a.offline_reason] ? t("analyst.reason." + a.offline_reason)
        : t("analyst.reason.other")) : null;
      uRows.push([t("analyst.mode"), (a.mode === "llm" ? t("analyst.llm") + (a.model ? " (" + a.model + ")" : "")
        : t("analyst.offline")) + (reason ? " — " + reason : "")]);
      var dl = el("dl", { className: "ba-understood" });
      uRows.forEach(function (r) { dl.append(el("dt", { text: r[0] }), el("dd", { text: r[1] })); });
      return el("details", { className: "bk-details ba-how" }, [summary,
        el("div", { className: "ba-how__body" }, [
          el("p", { className: "ba-how__title", text: t("analyst.understood") }), dl,
          el("ol", { className: "ba-calls" }, rows),
        ])]);
    }

    function renderAnswer() {
      var a = state.answer;
      if (!a) { renderIdle(); return; }
      var blocks = a.blocks || [];
      var first = blocks[0];
      // Разметка ui-kit R11 «Спросить Birge»: .bk-answer (+ __q, __nums, __text, __acts), .bk-details, .bk-tag.
      var q = el("p", { className: "bk-answer__q ba-q" }, [
        el("span", { className: "ba-q__text", text: "«" + a.question + "»" }),
        el("span", { className: "ba-q__src", text: " · " + (first ? pick(first.source && first.source.name, state.lang) : "") }),
        a.demo ? el("span", { className: "ba-demo", title: t("analyst.demo_hint"), text: " · " + t("analyst.demo") }) : null,
      ]);
      var head = el("h3", { className: "ba-answer__title", tabindex: "-1", text: pick(a.headline, state.lang) });
      var card = el("article", { className: "bk-answer ba-card ba-answer", "aria-labelledby": "ba-answer-title" }, [q, head]);
      head.id = "ba-answer-title";
      (a.notices || []).forEach(function (n) {
        card.append(el("p", { className: "ba-notice" }, [icon("info"), el("span", { text: pick(n, state.lang) })]));
      });
      blocks.forEach(function (b, i) { card.append(blockView(b, i === 0)); });
      // Llm-вводная (без чисел) — отдельной строкой над первым блоком, только если отличается от первой строки блока.
      if (a.mode === "llm" && a.lead && first && pick(a.lead, state.lang) &&
          pick(a.lead, state.lang) !== ((first.lines && first.lines[state.lang]) || [])[0]) {
        card.insertBefore(el("p", { className: "ba-intro", text: pick(a.lead, state.lang) }), card.children[2] || null);
      }
      var actions = (a.actions || []).map(function (act, i) { return actionButton(act, i === 0); }).filter(Boolean);
      actions.push(el("span", { className: "bk-tag ba-mode ba-mode--" + (a.mode === "llm" ? "llm" : "offline"),
        title: a.mode === "llm" ? t("analyst.llm_hint") : t("analyst.offline_hint"),
        text: a.mode === "llm" ? t("analyst.llm") : t("analyst.offline") }));
      card.append(el("div", { className: "bk-answer__acts ba-actions" }, actions));
      card.append(howView(a));
      live.replaceChildren(card);
    }

    function render() {
      clearTimeout(state.skelTimer);
      rootEl.dataset.state = state.status;   // после ответа чипы — одним рядом (analyst.css), ответ выше
      live.setAttribute("aria-busy", state.status === "loading" ? "true" : "false");
      if (state.status === "idle") renderIdle();
      else if (state.status === "error") renderError();
      else if (state.status === "ready") renderAnswer();
      renderHistory();
    }

    // -------------------------------------------------------------- вопрос
    function showFieldError(key) {
      fieldError.hidden = !key;
      fieldError.textContent = key ? t(key) : "";
      input.setAttribute("aria-invalid", key ? "true" : "false");
    }

    function submit(again) {
      var q = (again != null ? String(again) : input.value).replace(/\s+/g, " ").trim();
      if (!q) { showFieldError("analyst.error.empty"); input.focus(); return; }
      if (q.length > MAX_QUESTION) { showFieldError("analyst.error.long"); input.focus(); return; }
      showFieldError(null);
      var seq = ++state.seq;
      state.question = q;
      state.status = "loading";
      askBtn.setAttribute("aria-busy", "true");
      askBtn.disabled = true;
      live.setAttribute("aria-busy", "true");
      clearTimeout(state.skelTimer);
      state.skelTimer = setTimeout(function () { if (state.seq === seq && state.status === "loading") renderSkeleton(); },
        SKELETON_DELAY);
      renderHistory();
      request(opts, q, state.lang).then(function (answer) {
        if (state.destroyed || seq !== state.seq) return;
        state.answer = answer;
        state.status = "ready";
        state.history = [{ q: q, answer: answer }].concat(state.history.filter(function (h) { return h.q !== q; }))
          .slice(0, HISTORY);
        render();
        var h = live.querySelector(".ba-answer__title");
        if (h && doc.activeElement !== input) h.focus({ preventScroll: false });
      }, function (err) {
        if (state.destroyed || seq !== state.seq) return;
        if (err && err.status === 400) {
          state.status = state.answer ? "ready" : "idle";
          showFieldError(err.field === "question" && q.length > MAX_QUESTION ? "analyst.error.long" : "analyst.error.empty");
          render();
          return;
        }
        state.error = err || { status: 0 };
        state.status = "error";
        render();
      }).then(function () {
        if (seq !== state.seq) return;
        askBtn.removeAttribute("aria-busy");
        askBtn.disabled = false;
      });
    }

    form.addEventListener("submit", function (e) { e.preventDefault(); submit(); });
    input.addEventListener("input", function () { syncClear(); if (!fieldError.hidden) showFieldError(null); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && input.value) { e.stopPropagation(); input.value = ""; syncClear(); }
    });
    clearBtn.addEventListener("click", function () { input.value = ""; syncClear(); input.focus(); });

    function onLang(e) {
      var next = e && e.detail && (e.detail.lang || e.detail);
      if (next === "ru" || next === "kk") setLang(next);
    }
    function setLang(lang) {
      if (lang !== "ru" && lang !== "kk") return;
      state.lang = lang;
      renderStatic();
      render();
    }
    root.addEventListener("birge:lang", onLang);

    renderStatic();
    render();

    return {
      setLang: setLang,
      ask: function (question) { input.value = String(question || ""); syncClear(); submit(); },
      destroy: function () {
        state.destroyed = true;
        clearTimeout(state.skelTimer);
        root.removeEventListener("birge:lang", onLang);
        container.replaceChildren();
      },
      state: function () { return { status: state.status, lang: state.lang, question: state.question, answer: state.answer }; },
    };
  }

  // Команды палитры Ctrl+K (R01 может добавить их в gatherCommands — patch в INTEGRATION.txt R03).
  function commands() {
    var lang = i18n() && i18n().getLang ? i18n().getLang() : "ru";
    var t = makeT(function () { return lang === "kk" ? "kk" : "ru"; });
    var B = root.BirgeShell;
    function open(question) {
      return function () {
        pending = question || null;
        if (B && B.setSection) B.setSection("analyst");
        if (handle && question) handle.ask(question);
      };
    }
    return [{ id: "analyst.open", group: t("analyst.title"), title: t("analyst.title"), hint: "", run: open(null) }]
      .concat(SUGGESTIONS.slice(0, 3).map(function (s, i) {
        return { id: "analyst.q" + i, group: t("analyst.title"), title: pick(s, lang), hint: "", run: open(pick(s, lang)) };
      }));
  }

  // Экран в оболочке. Вопрос из палитры (commands) задаётся, как только экран смонтирован.
  var handle = null, pending = null;
  function shellMount(container, opts) {
    var h = mount(container, opts);
    handle = h;
    if (pending) { var q = pending; pending = null; h.ask(q); }
    return { setLang: h.setLang, ask: h.ask, state: h.state,
      destroy: function () { h.destroy(); if (handle === h) handle = null; } };
  }
  function register() {
    var B = root.BirgeShell;
    if (!B || typeof B.registerScreen !== "function") return false;
    // Раздел уже в таблице SCREENS оболочки (patch R01) — она сама найдёт window.BirgeAnalyst.mount.
    if (typeof B.navTitle === "function" && (B.moreItems ? B.moreItems() : []).indexOf("analyst") >= 0) return true;
    // Подпись — готовым текстом: titleKey без ключа в словаре R11 оболочка показала бы сам ключ «analyst.title».
    var spec = { id: "analyst", mount: shellMount, modes: ["akimat"],
      title: { ru: KEYS.ru["analyst.title"], kk: KEYS.kk["analyst.title"] } };
    var I = i18n();
    if (I && typeof I.has === "function" && I.has("analyst.title")) spec.titleKey = "analyst.title";
    var ok = B.registerScreen(spec);
    // Оболочка разбирает адрес до загрузки этого скрипта: прямая ссылка #analyst открывает экран сама.
    if (ok && root.location.hash === "#analyst" && B.section !== "analyst" && typeof B.setSection === "function") {
      B.setSection("analyst", { hash: false });
    }
    return ok;
  }

  // Палитра Ctrl+K (IA R11 §7.10): «Спросить Birge: <набранный текст>» — открыть экран и сразу задать вопрос.
  function askFromAnywhere(question) {
    var q = String(question || "").replace(/\s+/g, " ").trim().slice(0, MAX_QUESTION);
    if (handle) {
      if (root.BirgeShell && root.BirgeShell.section !== "analyst" && root.BirgeShell.setSection) root.BirgeShell.setSection("analyst");
      if (q) handle.ask(q);
      return true;
    }
    pending = q || null;
    if (root.BirgeShell && typeof root.BirgeShell.setSection === "function") { root.BirgeShell.setSection("analyst"); return true; }
    return false;
  }

  // mount для оболочки — та же обёртка (палитра знает открытый экран), для стенда и тестов — тоже.
  root.BirgeAnalyst = { mount: shellMount, commands: commands, ask: askFromAnywhere, version: VERSION, KEYS: KEYS };
  if (!register()) {
    if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", register, { once: true });
    else root.addEventListener("load", register, { once: true });
  }
})(window);
