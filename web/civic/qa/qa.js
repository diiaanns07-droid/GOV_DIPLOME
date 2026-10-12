/*
 * Birge · «Вопрос акиму» (R13, волна 2 п. 9). Схема — R11 IA_WAVE2 §7.
 * Житель: «Ещё → Вопрос акиму»; акимат: «Ещё → Вопросы жителей». На карте вопросов нет.
 *
 *   <link rel="stylesheet" href="/civic/qa/qa.css">
 *   <script src="/civic/i18n/i18n.js"></script>
 *   <script src="/civic/qa/qa.js"></script>
 *   BirgeAsk.mount(element, { role: "resident" | "akimat", titleTag: "h2", api })  → { setLang, destroy }
 *
 * В оболочке R01 (INTEGRATION R01 §11.2, раздел #questions): opts.api.v2(method, path, body) — клиент шлюза
 * (CSRF сотрудника ставит сам), opts.role — вид. Без оболочки — свой fetch на /api/civic/v2.
 *
 * Данные (ui/civic_qa/service.py):
 *   GET  /questions?tab=top|new|answered&device_id=     житель; POST /questions; POST /questions/{id}/vote
 *   GET  /questions/staff?tab=queue|top|answered        сотрудник; POST /questions/{id}/publish|reject|answer
 * device_id — тот же, что у мастера жалобы R09 (localStorage "birge.device").
 *
 * Правила (IA_WAVE2 §7, UX_BRIEF): правило «раз в неделю — 5 вопросов» всегда видно; у жителя одна главная кнопка
 * «Задать вопрос» (в форме — «Отправить вопрос»); ответ акима свёрнут; у демо-записей — метка «Пример»;
 * без комментариев, имён жителей, рейтингов районов. Пусто — понятная строка, а не пустой экран.
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var DISTRICTS = ["almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"];
  var DEVICE_KEY = "birge.device"; // как у R09 (web/civic/feedback/complaint.js) и R08 «Рядом»
  var DISTRICT_KEY = "birge.qa.district";
  var NEARBY_DISTRICT_KEY = "birge.nearby.district"; // только чтение: район, который житель уже выбрал в «Рядом»
  var TEXT_MIN = 10;
  var TEXT_MAX = 300;
  var ANSWER_MAX = 1500;
  var NOTE_MAX = 200;
  var REASONS = ["personal_data", "rude", "not_question", "duplicate", "other"];
  var KK_LETTERS = /[әғқңөұүһіӘҒҚҢӨҰҮҺІ]/;
  var scriptBase = ((doc.currentScript && doc.currentScript.src) || "").replace(/[^/]*$/, "");
  var ICONS = scriptBase + "../ui-kit/icons.svg";

  // Ключи, которых пока нет в словаре R11 (запас до слияния; список для R11 — R13 INTEGRATION.txt §8.4).
  // Словарь главнее: есть ключ в BirgeI18n — берём его.
  var KEYS = {
    ru: {
      "ask.title": "Вопрос акиму",
      "ask.rule": "Раз в неделю аким отвечает на 5 вопросов с наибольшим числом голосов.",
      "ask.new": "Задать вопрос",
      "ask.tab.top": "Популярные",
      "ask.tab.new": "Новые",
      "ask.tab.answered": "С ответом",
      "ask.support": "Поддержать",
      "ask.supported": "Вы поддержали",
      "ask.votes": { one: "{n} голос", few: "{n} голоса", many: "{n} голосов" },
      "ask.answer": "Ответ акима",
      "ask.text": "Ваш вопрос",
      "ask.district": "Район",
      "ask.privacy": "Не пишите имя, телефон и ИИН — вопрос увидят все.",
      "ask.moderation": "Вопрос опубликуют после проверки",
      "ask.send": "Отправить вопрос",
      "ask.staff.queue": "На проверке",
      "ask.staff.top": "Топ-5 недели",
      "ask.staff.answered": "Отвечено",
      "ask.staff.publish": "Опубликовать",
      "ask.staff.reject": "Отклонить с причиной",
      "ask.staff.answer": "Ответить",
      "ask.tabs_label": "Какие вопросы показать",
      "ask.sent_title": "Вопрос отправлен",
      "ask.back": "К вопросам",
      "ask.district_choose": "Выберите район",
      "ask.empty.top": "Вопросов без ответа пока нет. Задайте первый",
      "ask.empty.new": "Вопросов пока нет. Задайте первый",
      "ask.empty.answered": "Ответов пока нет",
      "ask.error.short": "Напишите вопрос подробнее — хотя бы 10 символов",
      "ask.error.long": "Не больше 300 символов",
      "ask.error.too_many": "С этого устройства уже есть вопросы на проверке. Дождитесь, пока их проверят",
      "ask.error.action": "Не получилось. Попробуйте ещё раз",
      "ask.staff.title": "Вопросы жителей",
      "ask.staff.week": "На этой неделе отвечено: {n} из 5",
      "ask.staff.received": "поступил {date}",
      "ask.staff.pii": "Похоже на личные данные: {what}",
      "ask.staff.pii.phone": "телефон",
      "ask.staff.pii.iin": "ИИН",
      "ask.staff.pii.email": "почта",
      "ask.staff.rude": "Есть грубые слова",
      "ask.staff.reason_title": "Причина отказа",
      "ask.staff.reason.personal_data": "Личные данные",
      "ask.staff.reason.rude": "Грубые слова",
      "ask.staff.reason.not_question": "Это жалоба — её отправляют через «Сообщить о проблеме»",
      "ask.staff.reason.duplicate": "Такой вопрос уже есть",
      "ask.staff.reason.other": "Другое",
      "ask.staff.reason_needed": "Выберите причину",
      "ask.staff.note": "Пояснение (по желанию)",
      "ask.staff.reject_send": "Отклонить",
      "ask.staff.answer_ru": "Ответ на русском",
      "ask.staff.answer_kk": "Ответ на казахском",
      "ask.staff.answer_hint": "Достаточно одного языка, второй — по желанию. Ответ увидят все",
      "ask.staff.answer_send": "Опубликовать ответ",
      "ask.staff.answer_empty": "Напишите ответ хотя бы на одном языке — не короче 10 символов",
      "ask.staff.done.published": "Вопрос опубликован",
      "ask.staff.done.rejected": "Вопрос отклонён",
      "ask.staff.done.answered": "Ответ опубликован",
      "ask.staff.conflict": "Вопрос уже проверил другой сотрудник — список обновлён",
      "ask.staff.login": "Чтобы проверять вопросы и отвечать, войдите как сотрудник акимата",
      "ask.staff.login_btn": "Войти",
      "ask.staff.empty.queue": "Новых вопросов на проверке нет",
      "ask.staff.empty.top": "Вопросов без ответа нет",
    },
    kk: {
      "ask.title": "Әкімге сұрақ",
      "ask.rule": "Әкім аптасына бір рет ең көп дауыс жинаған 5 сұраққа жауап береді.",
      "ask.new": "Сұрақ қою",
      "ask.tab.top": "Танымал",
      "ask.tab.new": "Жаңа",
      "ask.tab.answered": "Жауап берілген",
      "ask.support": "Қолдау",
      "ask.supported": "Сіз қолдадыңыз",
      "ask.votes": "{n} дауыс",
      "ask.answer": "Әкімнің жауабы",
      "ask.text": "Сұрағыңыз",
      "ask.district": "Аудан",
      "ask.privacy": "Аты-жөніңізді, телефон мен ЖСН жазбаңыз — сұрақты бәрі көреді.",
      "ask.moderation": "Сұрақ тексерілгеннен кейін жарияланады",
      "ask.send": "Сұрақты жіберу",
      "ask.staff.queue": "Тексеруде",
      "ask.staff.top": "Аптаның үздік 5 сұрағы",
      "ask.staff.answered": "Жауап берілді",
      "ask.staff.publish": "Жариялау",
      "ask.staff.reject": "Себебін көрсетіп қабылдамау",
      "ask.staff.answer": "Жауап беру",
      "ask.tabs_label": "Қандай сұрақтарды көрсету",
      "ask.sent_title": "Сұрақ жіберілді",
      "ask.back": "Сұрақтарға оралу",
      "ask.district_choose": "Ауданды таңдаңыз",
      "ask.empty.top": "Әзірге жауапсыз сұрақ жоқ. Бірінші болып сұраңыз",
      "ask.empty.new": "Әзірге сұрақ жоқ. Бірінші болып сұраңыз",
      "ask.empty.answered": "Әзірге жауап жоқ",
      "ask.error.short": "Сұрақты толығырақ жазыңыз — кемінде 10 таңба",
      "ask.error.long": "300 таңбадан аспасын",
      "ask.error.too_many": "Бұл құрылғыдан жіберілген сұрақтар әлі тексеруде. Тексеріліп болғанын күтіңіз",
      "ask.error.action": "Болмады. Қайталап көріңіз",
      "ask.staff.title": "Тұрғындар сұрақтары",
      "ask.staff.week": "Осы аптада жауап берілгені: 5 ішінен {n}",
      "ask.staff.received": "түскені: {date}",
      "ask.staff.pii": "Жеке деректерге ұқсайды: {what}",
      "ask.staff.pii.phone": "телефон",
      "ask.staff.pii.iin": "ЖСН",
      "ask.staff.pii.email": "электрондық пошта",
      "ask.staff.rude": "Дөрекі сөздер бар",
      "ask.staff.reason_title": "Бас тарту себебі",
      "ask.staff.reason.personal_data": "Жеке деректер",
      "ask.staff.reason.rude": "Дөрекі сөздер",
      "ask.staff.reason.not_question": "Бұл — шағым, оны «Мәселе туралы хабарлау» арқылы жібереді",
      "ask.staff.reason.duplicate": "Мұндай сұрақ бұрыннан бар",
      "ask.staff.reason.other": "Басқа себеп",
      "ask.staff.reason_needed": "Себебін таңдаңыз",
      "ask.staff.note": "Түсініктеме (қалауыңызша)",
      "ask.staff.reject_send": "Қабылдамау",
      "ask.staff.answer_ru": "Орыс тіліндегі жауап",
      "ask.staff.answer_kk": "Қазақ тіліндегі жауап",
      "ask.staff.answer_hint": "Бір тіл жеткілікті, екіншісі — қалауыңызша. Жауапты бәрі көреді",
      "ask.staff.answer_send": "Жауапты жариялау",
      "ask.staff.answer_empty": "Жауапты кемінде бір тілде жазыңыз — 10 таңбадан қысқа болмасын",
      "ask.staff.done.published": "Сұрақ жарияланды",
      "ask.staff.done.rejected": "Сұрақ қабылданбады",
      "ask.staff.done.answered": "Жауап жарияланды",
      "ask.staff.conflict": "Сұрақты басқа қызметкер тексеріп қойған — тізім жаңартылды",
      "ask.staff.login": "Сұрақтарды тексеру және жауап беру үшін әкімдік қызметкері ретінде кіріңіз",
      "ask.staff.login_btn": "Кіру",
      "ask.staff.empty.queue": "Тексеруді күтетін жаңа сұрақ жоқ",
      "ask.staff.empty.top": "Жауапсыз сұрақ жоқ",
    },
  };
  // Общие ключи словаря R11 (common.*, district.*) — запас на случай страницы без словаря.
  var COMMON = {
    ru: {
      "common.tag.demo": "Пример", "common.tag.demo_hint": "Пример для показа, не настоящие данные",
      "common.action.cancel": "Отменить", "common.action.retry": "Повторить",
      "common.state.loading": "Загружаем…", "common.state.network_title": "Нет связи с сервером",
      "common.state.network_text": "Проверьте интернет и повторите.",
      "common.error.too_many": "Слишком много действий подряд. Повторите через минуту.",
      "district.almaty": "Алматы", "district.baikonur": "Байконур", "district.esil": "Есиль", "district.nura": "Нура",
      "district.saraishyk": "Сарайшык", "district.saryarka": "Сарыарка",
    },
    kk: {
      "common.tag.demo": "Үлгі", "common.tag.demo_hint": "Көрсетуге арналған үлгі, нақты дерек емес",
      "common.action.cancel": "Болдырмау", "common.action.retry": "Қайталау",
      "common.state.loading": "Жүктеліп жатыр…", "common.state.network_title": "Сервермен байланыс жоқ",
      "common.state.network_text": "Интернетті тексеріп, қайталап көріңіз.",
      "common.error.too_many": "Қатарынан тым көп әрекет жасалды. Бір минуттан кейін қайталаңыз.",
      "district.almaty": "Алматы", "district.baikonur": "Байқоңыр", "district.esil": "Есіл", "district.nura": "Нұра",
      "district.saraishyk": "Сарайшық", "district.saryarka": "Сарыарқа",
    },
  };

  function I() {
    return root.BirgeI18n || null;
  }
  function lang() {
    return I() ? I().getLang() : "ru";
  }
  function num(n) {
    return I() ? I().formatNumber(n) : String(n);
  }
  function plural(l, n) {
    if (I() && typeof I().plural === "function") return I().plural(l, n);
    if (l === "kk") return "other";
    var m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return "one";
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "few";
    return "many";
  }
  function tr(key, params) {
    var i18n = I();
    if (i18n && (i18n.has(key) || i18n.has(key, "ru"))) return i18n.t(key, params);
    var l = lang() === "kk" ? "kk" : "ru";
    var v = KEYS[l][key] != null ? KEYS[l][key] : COMMON[l][key] != null ? COMMON[l][key] : KEYS.ru[key];
    if (v == null) return i18n ? i18n.t(key, params) : key;
    if (typeof v === "object") {
      var n = params && params.n != null ? Number(params.n) : 0;
      v = v[plural(l, n)] || v.other || v.many;
    }
    return String(v).replace(/\{(\w+)\}/g, function (w, name) {
      if (!params || params[name] == null) return w;
      return typeof params[name] === "number" ? num(params[name]) : String(params[name]);
    });
  }
  function date(iso) {
    return I() ? I().formatDate(iso) : String(iso || "").slice(0, 10);
  }
  function relative(iso) {
    return I() && typeof I().formatRelative === "function" ? I().formatRelative(iso) : date(iso);
  }
  function h(tag, attrs, children) {
    var el = doc.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === "text") el.textContent = v;
      else if (k === "class") el.className = v;
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    (children || []).forEach(function (c) {
      if (c != null && c !== false) el.appendChild(typeof c === "string" ? doc.createTextNode(c) : c);
    });
    return el;
  }
  function icon(name) {
    var svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "ic");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var use = doc.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", ICONS + "#i-" + name);
    svg.appendChild(use);
    return svg;
  }
  function storage(key, value) {
    try {
      if (value === undefined) return root.localStorage.getItem(key);
      root.localStorage.setItem(key, value);
    } catch (e) {
      return null; // приватный режим — работаем без памяти
    }
    return null;
  }
  function randomHex(bytes) {
    var arr = new Uint8Array(bytes);
    if (root.crypto && root.crypto.getRandomValues) root.crypto.getRandomValues(arr);
    else for (var i = 0; i < bytes; i++) arr[i] = Math.floor(Math.random() * 256);
    return Array.prototype.map.call(arr, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }
  // Тот же id устройства, что у формы жалобы R09: «одно устройство — один голос» (R15 S08; в базе — только хэш).
  var memoryDevice = null; // хранилище недоступно — один id на страницу (как report.js R12), а не новый на каждый запрос
  function deviceId() {
    var id = storage(DEVICE_KEY);
    if (id && /^[A-Za-z0-9._:-]{8,128}$/.test(id)) return id;
    if (!memoryDevice) {
      memoryDevice = "d-" + randomHex(12);
      storage(DEVICE_KEY, memoryDevice);
    }
    return memoryDevice;
  }
  function toast(text, type) {
    if (root.BirgeUI && typeof root.BirgeUI.toast === "function") root.BirgeUI.toast(text, type ? { type: type } : {});
  }
  // Язык вопроса — по буквам (казахские ә, ғ, қ…), иначе язык интерфейса: экран чтения и перевод знают язык текста.
  function textLang(text) {
    return KK_LETTERS.test(text) ? "kk" : lang() === "kk" ? "kk" : "ru";
  }

  function mount(rootEl, options) {
    var opts = { apiBase: "/api/civic/v2", titleTag: "h2", role: "resident" };
    Object.keys(options || {}).forEach(function (k) {
      if (options[k] !== undefined) opts[k] = options[k];
    });
    var state = {
      role: opts.role === "akimat" ? "akimat" : "resident",
      view: "list", // житель: list | form | sent
      tab: null,
      status: "loading", // loading | ready | error | login
      data: null,
      request: 0,
      open: null, // сотрудник: {id, kind: "reject" | "answer"} — открыта одна форма
      draft: { text: "", district: "", requestId: null, error: null, field: null, busy: false },
      staffDraft: { reason: null, note: "", answer_ru: "", answer_kk: "", error: null, busy: false },
      busyVote: {},
      alive: true,
      lang: null,
    };
    var box = h("section", { class: "qa", "data-role": state.role });
    rootEl.appendChild(box);

    // Запрос к API: клиент оболочки R01 или свой fetch (отдельная страница). Ошибка — {status, error, message, field}.
    function call(method, path, body) {
      if (opts.api && typeof opts.api.v2 === "function") return opts.api.v2(method, path, body);
      var headers = { Accept: "application/json" };
      if (body !== undefined) headers["Content-Type"] = "application/json";
      var shell = root.CivicShell;
      var csrf = shell && typeof shell.csrfToken === "function" ? shell.csrfToken() : null;
      if (csrf && method !== "GET") headers["X-CSRF-Token"] = csrf;
      return root.fetch(opts.apiBase + path, {
        method: method, headers: headers, credentials: "same-origin",
        body: body !== undefined ? JSON.stringify(body) : undefined,
      }).then(function (r) {
        return r.text().then(function (text) {
          var data = null;
          try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
          if (!r.ok) throw { status: r.status, error: (data && data.error) || "error", message: data && data.message, field: data && data.field };
          return data;
        });
      }, function () {
        throw { status: 0, error: "network" };
      });
    }
    function defaultTab() {
      return state.role === "akimat" ? "queue" : "top";
    }
    function staff() {
      return state.role === "akimat";
    }

    // ---------------------------------------------------------------- загрузка
    function load(keepScroll) {
      var req = ++state.request;
      if (!state.tab) state.tab = defaultTab();
      if (!keepScroll || !state.data) {
        state.status = "loading";
        render();
      }
      var path = staff()
        ? "/questions/staff?tab=" + state.tab
        : "/questions?tab=" + state.tab + "&device_id=" + encodeURIComponent(deviceId());
      return call("GET", path).then(function (data) {
        if (!state.alive || req !== state.request) return;
        state.data = data || { items: [], counts: {} };
        state.status = "ready";
        render();
      }, function (err) {
        if (!state.alive || req !== state.request) return;
        state.status = staff() && err && (err.status === 401 || err.status === 403) ? "login" : "error";
        render();
      });
    }

    // ---------------------------------------------------------------- разметка
    function render() {
      if (!state.alive) return;
      var focusKey = doc.activeElement && box.contains(doc.activeElement) ? doc.activeElement.getAttribute("data-focus") : null;
      box.setAttribute("data-role", state.role);
      box.replaceChildren();
      state.lang = lang();
      box.appendChild(h(opts.titleTag || "h2", { class: "qa__title", id: "qa-title", tabindex: "-1", "data-focus": "title",
        text: tr(staff() ? "ask.staff.title" : "ask.title") }));
      box.appendChild(h("p", { class: "qa__rule" }, [icon("info"), h("span", { text: tr("ask.rule") })]));
      if (!staff() && state.view === "form") box.appendChild(renderForm());
      else if (!staff() && state.view === "sent") box.appendChild(renderSent());
      else {
        if (!staff()) {
          box.appendChild(h("div", { class: "qa__lead" }, [
            h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-focus": "new", onclick: openForm },
              [icon("plus"), tr("ask.new")]),
          ]));
        }
        box.appendChild(renderTabs());
        if (staff() && state.tab === "top" && state.status === "ready" && state.data && state.data.week) {
          box.appendChild(h("p", { class: "qa__week" }, [icon("calendar"),
            h("span", { text: tr("ask.staff.week", { n: state.data.week.answered || 0 }) })]));
        }
        box.appendChild(renderBody());
      }
      if (focusKey) {
        var again = box.querySelector('[data-focus="' + focusKey + '"]');
        if (again) again.focus();
      }
    }

    function renderTabs() {
      var tabs = staff() ? ["queue", "top", "answered"] : ["top", "new", "answered"];
      var counts = (state.data && state.data.counts) || {};
      var seg = h("div", { class: "bk-seg qa-tabs", role: "group", "aria-label": tr("ask.tabs_label") });
      tabs.forEach(function (id) {
        var label = tr(staff() ? "ask.staff." + id : "ask.tab." + id);
        var count = counts[id];
        seg.appendChild(h("button", {
          type: "button", "aria-pressed": String(state.tab === id), "data-focus": "tab-" + id,
          onclick: function () {
            if (state.tab === id) return;
            state.tab = id;
            state.open = null;
            load();
          },
        }, [h("span", { text: label }), count != null && state.status === "ready"
          ? h("span", { class: "qa-tabs__count", "aria-hidden": "true", text: num(count) }) : null]));
      });
      var wrap = h("div", { class: "qa-tabs-wrap" }, [seg]);
      // Не все вкладки помещаются (kk на 375): затухание справа — видно, что вкладок больше (R11, разбор 4 п. 1а);
      // выбранная вкладка прокручивается в видимую часть.
      function edge() {
        wrap.classList.toggle("qa-tabs-wrap--more", wrap.scrollWidth - wrap.clientWidth - wrap.scrollLeft > 2);
      }
      wrap.addEventListener("scroll", edge, { passive: true });
      (root.requestAnimationFrame || setTimeout)(function () {
        var active = seg.querySelector('[aria-pressed="true"]');
        if (active && wrap.scrollWidth > wrap.clientWidth) {
          var right = active.offsetLeft + active.offsetWidth - wrap.clientWidth + 24;
          if (right > wrap.scrollLeft) wrap.scrollLeft = right;
        }
        edge();
      });
      return wrap;
    }

    function stateBox(kind, title, text, action) {
      var el = h("div", { class: "qa-state" });
      if (root.BirgeUI && typeof root.BirgeUI.state === "function") {
        root.BirgeUI.state(el, kind, { title: title, text: text, action: action });
        return el;
      }
      el.appendChild(h("p", { class: kind === "error" ? "bk-error__title" : "bk-empty__title", text: title || "" }));
      if (text) el.appendChild(h("p", { class: "bk-meta", text: text }));
      if (action) el.appendChild(h("button", { type: "button", class: "bk-btn", onclick: action.onClick, text: action.label }));
      return el;
    }

    function renderBody() {
      if (state.status === "loading") {
        var wait = h("div", { class: "qa-state" });
        if (root.BirgeUI && root.BirgeUI.state) root.BirgeUI.state(wait, "loading");
        else wait.appendChild(h("p", { class: "bk-meta", role: "status", text: tr("common.state.loading") }));
        return wait;
      }
      if (state.status === "login") {
        var shell = root.CivicShell;
        var canLogin = shell && typeof shell.openEditor === "function";
        var login = h("div", { class: "bk-empty qa-login", role: "status" }, [
          h("p", { class: "bk-empty__title", text: tr("ask.staff.login") }),
        ]);
        var row = h("div", { class: "qa-card__actions" });
        if (canLogin) row.appendChild(h("button", { type: "button", class: "bk-btn", onclick: function () { shell.openEditor(); },
          text: tr("ask.staff.login_btn") }));
        row.appendChild(h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: function () { load(); } },
          [icon("refresh"), tr("common.action.retry")]));
        login.appendChild(row);
        return login;
      }
      if (state.status === "error") {
        return stateBox("error", tr("common.state.network_title"), tr("common.state.network_text"),
          { label: tr("common.action.retry"), onClick: function () { load(); } });
      }
      var items = (state.data && state.data.items) || [];
      if (!items.length) {
        var key = staff() ? (state.tab === "answered" ? "ask.empty.answered" : "ask.staff.empty." + state.tab) : "ask.empty." + state.tab;
        return h("div", { class: "bk-empty qa-empty", role: "status" }, [h("p", { class: "bk-empty__title", text: tr(key) })]);
      }
      var list = h("ul", { class: "qa-list", "aria-labelledby": "qa-title" });
      items.forEach(function (q) {
        list.appendChild(staff() ? staffCard(q) : residentCard(q));
      });
      return list;
    }

    function eyebrow(q, extra) {
      var parts = [];
      if (q.demo) parts.push(h("span", { class: "bk-tag bk-tag--demo", title: tr("common.tag.demo_hint"), text: tr("common.tag.demo") }));
      // Район и дата — одним текстом: при переносе на 375 разделитель «·» не встаёт в начало строки.
      parts.push(h("span", { class: "qa-card__place", text: tr("district." + q.district) + (extra ? " · " + extra : "") }));
      return h("p", { class: "qa-card__eyebrow" }, parts);
    }
    function questionText(q) {
      return h("p", { class: "qa-card__text", lang: q.lang === "kk" ? "kk" : "ru", text: "«" + q.text + "»" });
    }
    function answerBlock(q, open) {
      var a = q.answer;
      if (!a) return null;
      var l = lang();
      var text = a[l] || a[l === "kk" ? "ru" : "kk"];
      var textLangAttr = a[l] ? l : l === "kk" ? "ru" : "kk";
      return h("details", { class: "qa-answer", open: open ? true : null }, [
        h("summary", {}, [h("span", { text: tr("ask.answer") + " · " + date(a.answered_at) }), icon("chevron-down")]),
        // Ответ только на другом языке — честно говорим об этом (R11 разбор 15 №3)
        !a[l] && text ? h("p", { class: "qa-answer__lang", text: tr(l === "kk" ? "ask.answer.only_ru" : "ask.answer.only_kk") }) : null,
        h("p", { class: "qa-answer__text", lang: textLangAttr, text: text || "" }),
      ]);
    }

    // ---------------------------------------------------------------- житель
    function residentCard(q) {
      var votes = h("span", { class: "qa-card__votes" }, [icon("users"), h("span", { text: tr("ask.votes", { n: q.votes }) })]);
      var row = h("div", { class: "qa-card__row" }, [votes]);
      if (!q.answer) {
        var busy = !!state.busyVote[q.id];
        row.appendChild(q.my_vote
          ? h("span", { class: "qa-card__voted", role: "status" }, [icon("check"), h("span", { text: tr("ask.supported") })])
          : h("button", { type: "button", class: "bk-btn qa-card__vote", "data-focus": "vote-" + q.id,
              "aria-busy": busy ? "true" : null, "aria-disabled": busy ? "true" : null,
              onclick: function () { vote(q); } }, [icon("thumb-up"), tr("ask.support")]));
      }
      return h("li", { class: "bk-card qa-card", "data-id": q.id }, [
        eyebrow(q, q.published_at ? relative(q.published_at) : null),
        questionText(q),
        row,
        answerBlock(q, false),
      ]);
    }

    function vote(q) {
      if (state.busyVote[q.id]) return;
      state.busyVote[q.id] = true;
      // Сразу показываем «Вы поддержали»; ошибка — вернуть как было и сказать об этом.
      q.my_vote = true;
      q.votes += 1;
      render();
      call("POST", "/questions/" + encodeURIComponent(q.id) + "/vote", { device_id: deviceId() }).then(function (res) {
        delete state.busyVote[q.id];
        if (res && typeof res.votes === "number") q.votes = res.votes;
        render();
        var after = box.querySelector('[data-id="' + q.id + '"] .qa-card__voted');
        if (after) after.setAttribute("tabindex", "-1");
      }, function (err) {
        delete state.busyVote[q.id];
        q.my_vote = false;
        q.votes -= 1;
        render();
        toast(err && err.status === 429 ? tr("common.error.too_many") : tr("ask.error.action"), "error");
        if (err && (err.status === 404 || err.status === 409)) load(true); // вопрос сняли или уже ответили
      });
    }

    function openForm() {
      state.view = "form";
      var saved = storage(DISTRICT_KEY) || storage(NEARBY_DISTRICT_KEY);
      state.draft = { text: state.draft.text || "", district: DISTRICTS.indexOf(saved) >= 0 ? saved : "",
        requestId: "r-" + randomHex(10), error: null, field: null, busy: false };
      render();
      var area = box.querySelector("#qa-text");
      if (area) area.focus();
    }
    function closeForm() {
      state.view = "list";
      render();
      var btn = box.querySelector('[data-focus="new"]');
      if (btn) btn.focus();
    }

    function renderForm() {
      var d = state.draft;
      var textError = d.field === "text" ? d.error : null;
      var districtError = d.field === "district" ? d.error : null;
      var counter = h("span", { class: "qa-form__count", id: "qa-text-count", "aria-live": "polite",
        text: num(d.text.trim().length) + " / " + num(TEXT_MAX) });
      var area = h("textarea", { id: "qa-text", rows: "4", maxlength: String(TEXT_MAX), "aria-describedby": "qa-text-count qa-privacy" + (textError ? " qa-text-error" : ""),
        "aria-invalid": textError ? "true" : null, lang: textLang(d.text), placeholder: tr("ask.placeholder") }); // R11 разбор 15 №2
      area.value = d.text;
      area.addEventListener("input", function () {
        d.text = area.value;
        counter.textContent = num(d.text.trim().length) + " / " + num(TEXT_MAX);
        area.setAttribute("lang", textLang(d.text));
      });
      var select = h("select", { id: "qa-district", "aria-invalid": districtError ? "true" : null,
        "aria-describedby": districtError ? "qa-district-error" : null });
      select.appendChild(h("option", { value: "", text: tr("ask.district_choose") }));
      DISTRICTS.forEach(function (id) {
        var o = h("option", { value: id, text: tr("district." + id) });
        if (d.district === id) o.selected = true;
        select.appendChild(o);
      });
      select.addEventListener("change", function () { d.district = select.value; });
      var form = h("form", { class: "qa-form", novalidate: true, onsubmit: function (e) { e.preventDefault(); send(); } }, [
        h("div", { class: "bk-field" + (textError ? " bk-field--error" : "") }, [
          h("label", { class: "bk-field__label", for: "qa-text", text: tr("ask.text") }),
          area,
          h("div", { class: "qa-form__under" }, [
            textError ? h("span", { class: "bk-field__error", id: "qa-text-error", role: "alert", text: textError }) : h("span"),
            counter,
          ]),
        ]),
        h("div", { class: "bk-field" + (districtError ? " bk-field--error" : "") }, [
          h("label", { class: "bk-field__label", for: "qa-district", text: tr("ask.district") }),
          select,
          districtError ? h("span", { class: "bk-field__error", id: "qa-district-error", role: "alert", text: districtError }) : null,
        ]),
        h("p", { class: "qa-form__privacy", id: "qa-privacy" }, [icon("shield"), h("span", { text: tr("ask.privacy") })]),
        h("p", { class: "bk-meta", text: tr("ask.moderation") }),
        d.error && !d.field ? h("p", { class: "qa-form__error", role: "alert", text: d.error }) : null,
        h("div", { class: "qa-form__actions" }, [
          h("button", { type: "submit", class: "bk-btn bk-btn--primary", "aria-busy": d.busy ? "true" : null,
            "aria-disabled": d.busy ? "true" : null }, [icon("send"), tr("ask.send")]),
          h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: closeForm, text: tr("common.action.cancel") }),
        ]),
      ]);
      return form;
    }

    function send() {
      var d = state.draft;
      if (d.busy) return;
      var text = d.text.trim();
      d.error = null;
      d.field = null;
      if (text.length < TEXT_MIN) { d.field = "text"; d.error = tr("ask.error.short"); }
      else if (text.length > TEXT_MAX) { d.field = "text"; d.error = tr("ask.error.long"); }
      else if (DISTRICTS.indexOf(d.district) < 0) { d.field = "district"; d.error = tr("ask.district_choose"); }
      if (d.error) {
        render();
        var bad = box.querySelector(d.field === "text" ? "#qa-text" : "#qa-district");
        if (bad) bad.focus();
        return;
      }
      d.busy = true;
      render();
      call("POST", "/questions", { text: text, district: d.district, lang: textLang(text), device_id: deviceId(),
        request_id: d.requestId }).then(function () {
        storage(DISTRICT_KEY, d.district);
        state.draft = { text: "", district: d.district, requestId: null, error: null, field: null, busy: false };
        state.view = "sent";
        render();
        var title = box.querySelector("#qa-sent-title");
        if (title) title.focus();
      }, function (err) {
        d.busy = false;
        err = err || {};
        if (err.status === 422 && (err.field === "text" || err.field === "district")) {
          d.field = err.field;
          d.error = err.field === "district" ? tr("ask.district_choose")
            : err.error === "too_long" ? tr("ask.error.long") : tr("ask.error.short");
        } else if (err.status === 409) d.error = tr("ask.error.too_many");
        else if (err.status === 429) d.error = tr("common.error.too_many");
        else if (!err.status) d.error = tr("common.state.network_title") + ". " + tr("common.state.network_text");
        else d.error = tr("ask.error.action");
        render();
      });
    }

    function renderSent() {
      return h("div", { class: "bk-empty qa-sent", role: "status" }, [
        icon("check"),
        h("p", { class: "bk-empty__title", id: "qa-sent-title", tabindex: "-1", "data-focus": "sent-title", text: tr("ask.sent_title") }),
        h("p", { class: "bk-empty__text", text: tr("ask.moderation") }),
        h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-focus": "back", onclick: function () {
          state.view = "list";
          state.tab = "new";
          load();
        } }, [tr("ask.back")]),
      ]);
    }

    // ---------------------------------------------------------------- сотрудник
    function staffCard(q) {
      var when = state.tab === "queue" ? tr("ask.staff.received", { date: date(q.created_at) })
        : q.published_at ? date(q.published_at) : null;
      var warn = [];
      if (q.pii && q.pii.length) {
        warn.push(h("span", { class: "bk-tag bk-tag--warn" }, [icon("alert"), tr("ask.staff.pii", {
          what: q.pii.map(function (k) { return tr("ask.staff.pii." + k); }).join(", ") })]));
      }
      if (q.rude) warn.push(h("span", { class: "bk-tag bk-tag--warn" }, [icon("alert"), tr("ask.staff.rude")]));
      var card = h("li", { class: "bk-card qa-card", "data-id": q.id }, [
        eyebrow(q, when),
        questionText(q),
        warn.length ? h("p", { class: "qa-card__warn" }, warn) : null,
        state.tab !== "queue" ? h("div", { class: "qa-card__row" }, [h("span", { class: "qa-card__votes" },
          [icon("users"), h("span", { text: tr("ask.votes", { n: q.votes }) })])]) : null,
        answerBlock(q, state.tab === "answered"),
      ]);
      var open = state.open && state.open.id === q.id ? state.open.kind : null;
      if (open === "reject") card.appendChild(rejectPanel(q));
      else if (open === "answer") card.appendChild(answerPanel(q));
      else card.appendChild(staffActions(q));
      return card;
    }

    function staffActions(q) {
      var row = h("div", { class: "qa-card__actions" });
      if (state.tab === "queue") {
        row.appendChild(h("button", { type: "button", class: "bk-btn", "data-focus": "pub-" + q.id,
          onclick: function () { act(q, "publish", {}, "ask.staff.done.published"); } }, [icon("check"), tr("ask.staff.publish")]));
        row.appendChild(h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "rej-" + q.id,
          onclick: function () { openPanel(q, "reject"); }, text: tr("ask.staff.reject") }));
      } else if (state.tab === "top") {
        row.appendChild(h("button", { type: "button", class: "bk-btn", "data-focus": "ans-" + q.id,
          onclick: function () { openPanel(q, "answer"); } }, [icon("edit"), tr("ask.staff.answer")]));
        row.appendChild(h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "rej-" + q.id,
          onclick: function () { openPanel(q, "reject"); }, text: tr("ask.staff.reject") }));
      } else {
        row.appendChild(h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "ans-" + q.id,
          onclick: function () { openPanel(q, "answer"); } }, [icon("edit"), tr("ask.staff.answer")]));
        // Снять отвеченный вопрос можно только по причине «личные данные» (сервер отвечает 409 на другие причины).
        row.appendChild(h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "rej-" + q.id,
          onclick: function () { openPanel(q, "reject"); }, text: tr("ask.staff.reject") }));
      }
      return row;
    }

    function openPanel(q, kind) {
      state.open = { id: q.id, kind: kind };
      state.staffDraft = { reason: null, note: "", answer_ru: (q.answer && q.answer.ru) || "",
        answer_kk: (q.answer && q.answer.kk) || "", error: null, busy: false };
      render();
      var first = box.querySelector('[data-id="' + q.id + '"] .qa-panel input, [data-id="' + q.id + '"] .qa-panel textarea');
      if (first) first.focus();
    }
    function closePanel(q) {
      state.open = null;
      render();
      var back = box.querySelector('[data-id="' + q.id + '"] .qa-card__actions .bk-btn');
      if (back) back.focus();
    }

    function rejectPanel(q) {
      var d = state.staffDraft;
      var group = h("fieldset", { class: "qa-reasons" }, [h("legend", { class: "bk-field__label", text: tr("ask.staff.reason_title") })]);
      REASONS.forEach(function (r) {
        var input = h("input", { type: "radio", name: "qa-reason-" + q.id, value: r, checked: d.reason === r ? true : null });
        input.addEventListener("change", function () { d.reason = r; });
        group.appendChild(h("label", { class: "qa-reason" }, [input, h("span", { text: tr("ask.staff.reason." + r) })]));
      });
      var note = h("input", { type: "text", id: "qa-note-" + q.id, maxlength: String(NOTE_MAX) });
      note.value = d.note;
      note.addEventListener("input", function () { d.note = note.value; });
      return h("form", { class: "qa-panel", novalidate: true, onsubmit: function (e) {
        e.preventDefault();
        if (!d.reason) { d.error = tr("ask.staff.reason_needed"); render(); return; }
        act(q, "reject", { reason: d.reason, note: d.note.trim() || null }, "ask.staff.done.rejected");
      } }, [
        group,
        h("div", { class: "bk-field" }, [h("label", { class: "bk-field__label", for: "qa-note-" + q.id, text: tr("ask.staff.note") }), note]),
        d.error ? h("p", { class: "qa-form__error", role: "alert", text: d.error }) : null,
        h("div", { class: "qa-card__actions" }, [
          h("button", { type: "submit", class: "bk-btn bk-btn--danger", "aria-busy": d.busy ? "true" : null, text: tr("ask.staff.reject_send") }),
          h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: function () { closePanel(q); }, text: tr("common.action.cancel") }),
        ]),
      ]);
    }

    function answerPanel(q) {
      var d = state.staffDraft;
      function area(l) {
        var el = h("textarea", { id: "qa-ans-" + l + "-" + q.id, rows: "4", maxlength: String(ANSWER_MAX), lang: l });
        el.value = d["answer_" + l];
        el.addEventListener("input", function () { d["answer_" + l] = el.value; });
        return h("div", { class: "bk-field" }, [
          h("label", { class: "bk-field__label", for: "qa-ans-" + l + "-" + q.id, text: tr("ask.staff.answer_" + l) }), el]);
      }
      // Первым — язык интерфейса сотрудника.
      var order = lang() === "kk" ? ["kk", "ru"] : ["ru", "kk"];
      return h("form", { class: "qa-panel", novalidate: true, onsubmit: function (e) {
        e.preventDefault();
        var ru = d.answer_ru.trim(), kk = d.answer_kk.trim();
        if ((ru && ru.length < 10) || (kk && kk.length < 10) || (!ru && !kk)) {
          d.error = tr("ask.staff.answer_empty");
          render();
          return;
        }
        act(q, "answer", { answer_ru: ru || null, answer_kk: kk || null }, "ask.staff.done.answered");
      } }, [
        area(order[0]), area(order[1]),
        h("p", { class: "bk-meta", text: tr("ask.staff.answer_hint") }),
        d.error ? h("p", { class: "qa-form__error", role: "alert", text: d.error }) : null,
        h("div", { class: "qa-card__actions" }, [
          h("button", { type: "submit", class: "bk-btn bk-btn--primary", "aria-busy": d.busy ? "true" : null }, [icon("send"), tr("ask.staff.answer_send")]),
          h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: function () { closePanel(q); }, text: tr("common.action.cancel") }),
        ]),
      ]);
    }

    function act(q, action, body, doneKey) {
      var d = state.staffDraft;
      if (d.busy) return;
      d.busy = true;
      d.error = null;
      render();
      call("POST", "/questions/" + encodeURIComponent(q.id) + "/" + action, body).then(function () {
        state.open = null;
        toast(tr(doneKey), "ok");
        load(true).then(function () {
          var title = box.querySelector("#qa-title");
          if (title && !(doc.activeElement && box.contains(doc.activeElement))) title.focus();
        });
      }, function (err) {
        d.busy = false;
        err = err || {};
        if (err.status === 401 || err.status === 403) { state.status = "login"; state.open = null; render(); return; }
        if (err.status === 409 || err.status === 404) {
          state.open = null;
          toast(tr("ask.staff.conflict"), "error");
          load(true);
          return;
        }
        d.error = !err.status ? tr("common.state.network_title") : tr("ask.error.action");
        render();
      });
    }

    // ---------------------------------------------------------------- язык и вид
    // Перерисовка только при настоящей смене языка: оболочка зовёт setLang при каждой своей перерисовке,
    // а лишняя перерисовка сбрасывала бы фокус (заголовок «Вопрос отправлен») и введённый текст.
    function relang() {
      if (state.lang !== lang()) render();
    }
    var offLang = I() && typeof I().onChange === "function" ? I().onChange(relang) : null;
    function onMode(e) {
      var mode = e && e.detail && e.detail.mode;
      if ((mode === "akimat" || mode === "resident") && mode !== state.role) {
        state.role = mode;
        state.tab = null;
        state.view = "list";
        state.open = null;
        state.data = null;
        load();
      }
    }
    doc.addEventListener("birge:mode", onMode);

    if (I() && I().ready && typeof I().ready.then === "function") I().ready.then(function () { load(); }, function () { load(); });
    else load();

    return {
      setLang: relang,
      refresh: function () { return load(true); },
      destroy: function () {
        state.alive = false;
        if (offLang) offLang();
        doc.removeEventListener("birge:mode", onMode);
        if (box.parentNode) box.parentNode.removeChild(box);
      },
    };
  }

  root.BirgeAsk = { mount: mount, version: "r13-qa-1" };
})(typeof window !== "undefined" ? window : this);
