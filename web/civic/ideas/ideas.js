/*
 * Birge · «Идеи жителей» (R06, волна 2 п. 7; схема экранов — R11 IA_WAVE2 §8). Без библиотек.
 *
 * Житель — пункт меню «Идеи» (#ideas): честная строка «Это опрос для выбора концепции, решение принимает акимат»,
 *   главная кнопка «Предложить идею», вкладки «Идёт голосование | Стала проектом | Отклонена», карточки с
 *   «Поддержать» (одна поддержка с устройства) и «Показать на карте». Свои идеи на проверке — сверху, с пометкой.
 * Акимат — «Проекты и идеи» (#projects): вкладки «Идеи на проверке | Проекты». Идея раскрывается кнопкой «Проверить»:
 *   опубликовать / чек-лист реализуемости (участок, сети, доступность, содержание) → «Сделать проектом» или
 *   «Отклонить с причиной» («Можно доработать» — по желанию). Проекты — карточки R06 BirgeProposals (одобрить / отклонить).
 * Слой карты «Идеи жителей» (BirgeShell.registerLayer, один дополнительный слой за раз; по умолчанию выключен):
 *   метки идей рисует 3D-модуль R05 (CivicShell.build3d.setIdeas); нажатие на метку открывает карточку здесь.
 *
 * Подключение (R01, INTEGRATION R06 «Волна 2»): /civic/ideas/ideas.css и /civic/ideas/ideas.js после ui-kit, i18n
 * и proposals.js. Оболочка сама найдёт window.BirgeIdeas (SCREENS.ideas и SCREENS.projects в birge.js).
 *   BirgeIdeas.mount(root, {api: {v2}, role, section, titleTag, close, openSection}) → {destroy, setLang}
 * API (CONTRACT §7, волна 2): GET/POST /ideas, POST /ideas/{id}/support, POST /ideas/{id}/decide, GET /staff/ideas.
 *
 * Тексты — словарь R11 (idea.*); новые ключи — в KEYS ниже (запас ru/kk до словаря; список — INTEGRATION R06).
 * Текст жителя показывается как написан (lang у идеи), у демо-идей — на языке интерфейса.
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var API = "/api/civic/v2";
  var DEVICE_KEY = "birge.device_id"; // тот же id устройства, что у голосов за проекты (proposals.js)
  var DRAFT_KEY = "birge.idea.draft";
  var KINDS = ["square", "playground", "sports", "stop", "lighting"];
  var KIND_ICON = { square: "trees", playground: "playground", sports: "ball", stop: "bus", lighting: "bulb" };
  var CHECK_KEYS = ["land", "networks", "access", "maintenance"];
  var CHECK_ICON = { land: "pin", networks: "droplet", access: "walk", maintenance: "building" };
  var ANSWERS = ["yes", "no", "unknown"];
  // R15-S31: телефон, почта, ИИН — те же шаблоны, что у сервера (ui/civic_store/ideas.py _PERSONAL, жалобы R09).
  // Мастер ловит их сам, до отправки: житель видит, какое поле исправить. Сервер всё равно проверит (422).
  var PERSONAL = [/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/, /(^|\D)\d{12}(?!\d)/,
    /(^|[^\w+])(?:\+?7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)/];
  function hasPersonal(text) {
    return PERSONAL.some(function (rx) { return rx.test(String(text || "")); });
  }
  var TITLE_MAX = 60;
  var TEXT_MAX = 300;
  var RESIDENT_TABS = ["voting", "project", "rejected"];
  var STATUS_LOOK = { review: "new", voting: "accepted", checking: "in_progress", project: "fixed", rejected: "rejected", hidden: "rejected" };
  // Вкладка жителя по статусу (R11 SCHEMES §2.1): «Акимат проверяет» остаётся в «Голосовании», голосование закрыто.
  var TAB_OF = { voting: "voting", checking: "voting", project: "project", rejected: "rejected" };

  // Ключи, которых пока нет в словаре R11 (переданы в INTEGRATION.txt R06, раздел «Ключи волны 2»).
  // Ключи схемы R11 (SCHEMES_R06_R13 §2.7) — их тексты из словаря R11 2b8f72e: в словаре сборки FINAL-2 их ещё нет.
  var R11_KEYS = {
    ru: {
      "idea.tab.voting": "Голосование", "idea.tab.project": "Стали проектами", "idea.tab.rejected": "Отклонены",
      "idea.status.checking": "Акимат проверяет", "idea.object_none": "Без объекта",
      "idea.step.place": "Где? Нажмите на карту", "idea.step.text": "Что предлагаете?",
      "idea.name_hint": "До 60 знаков, например: «Сквер у школы № 45»",
      "idea.privacy": "Не пишите имя, телефон и ИИН — идею увидят все.", "idea.send": "Отправить идею",
      "idea.sent_title": "Идея отправлена",
      "idea.empty": "Идей пока нет. Предложите первую — соседи смогут её поддержать.",
      "idea.pb_note": "Крупные идеи можно подать и в программу «Бюджет участия» — это отдельная программа акимата.",
      "idea.staff.reason_label": "Причина (увидят все)", "idea.staff.improve_label": "Что можно доработать (по желанию)",
      "idea.staff.check_hint": "«Сделать проектом» станет доступно, когда по всем четырём пунктам — «да».",
      "common.chars_left": "Осталось знаков: {n}", "complaint.step_of": "Шаг {i} из {total}", "map.card.on_map": "На карте",
      "ask.staff.publish": "Опубликовать", "ask.staff.reject": "Отклонить с причиной",
    },
    kk: {
      "idea.tab.voting": "Дауыс беру", "idea.tab.project": "Жоба болды", "idea.tab.rejected": "Қабылданбады",
      "idea.status.checking": "Әкімдік тексеруде", "idea.object_none": "Нысансыз",
      "idea.step.place": "Қай жерде? Картаны басыңыз", "idea.step.text": "Не ұсынасыз?",
      "idea.name_hint": "60 таңбаға дейін, мысалы: «№ 45 мектеп жанындағы гүлзар»",
      "idea.privacy": "Аты-жөніңізді, телефон мен ЖСН жазбаңыз — идеяны бәрі көреді.", "idea.send": "Идеяны жіберу",
      "idea.sent_title": "Идея жіберілді",
      "idea.empty": "Әзірге идея жоқ. Біріншісін ұсыныңыз — көршілеріңіз қолдай алады.",
      "idea.pb_note": "Ірі идеяларды «Қатысу бюджеті» бағдарламасына да беруге болады — бұл әкімдіктің жеке бағдарламасы.",
      "idea.staff.reason_label": "Себебі (бәрі көреді)", "idea.staff.improve_label": "Нені жетілдіруге болады (қаласаңыз)",
      "idea.staff.check_hint": "Төрт тармақтың бәрі «иә» болғанда, «Жобаға айналдыру» қолжетімді болады.",
      "common.chars_left": "Қалған таңба: {n}", "complaint.step_of": "Қадам {i}/{total}", "map.card.on_map": "Картада",
      "ask.staff.publish": "Жариялау", "ask.staff.reject": "Себебін көрсетіп қабылдамау",
    },
  };
  var KEYS = {
    ru: {
      "idea.status.review": "На проверке",
      "idea.status.hidden": "Не опубликована",
      "idea.hidden_note": "Идея не прошла проверку: в ней личные данные, грубые слова или реклама.",
      "idea.mine": "Ваша идея",
      "idea.kind_none": "Идея",
      "idea.place": "Где это нужно?",
      "idea.place_pick": "Выбрать место на карте",
      "idea.place_change": "Изменить место",
      "idea.place_hint": "Нажмите на карту там, где нужна идея, затем «Готово»",
      "idea.place_chosen": "Место выбрано: {street}",
      "idea.place_chosen_plain": "Место выбрано",
      "idea.place_refine": "Можно нажать точнее или «Готово»",
      "idea.place_needed": "Сначала выберите место на карте",
      "idea.map_unavailable": "Карта сейчас недоступна. Обновите страницу.",
      "idea.sent_next": "Пока её видите только вы — в списке «Идеи» с пометкой «На проверке».",
      "idea.support_saved": "Поддержка учтена",
      "idea.support_removed": "Поддержка снята",
      "idea.limit_support": "С этого устройства или сети уже много голосов за эту идею. Попробуйте завтра.",
      "idea.limit_new": "С этого устройства или сети уже много новых идей. Попробуйте позже.",
      "idea.limit_review": "У вас уже 3 идеи на проверке. Дождитесь ответа акимата.",
      "idea.voting_closed": "Голосование по этой идее закрыто",
      "idea.error": "Не получилось сохранить. Проверьте связь и повторите.",
      "idea.not_found": "Идея не найдена",
      "idea.empty.review": "Новых идей на проверке нет",
      "idea.decided": "Решённые идеи",
      "idea.check_open": "Проверить",
      "idea.check_close": "Свернуть",
      "idea.hide": "Скрыть: личные данные или грубые слова",
      "idea.hide_reason": "Почему скрыть (видят только сотрудники)",
      "idea.hide_confirm": "Скрыть идею",
      "idea.project_kind": "Какой объект поставить",
      "idea.lighting_note": "Освещение ставится вдоль улицы: добавьте его в каталоге «Что построить?» на карте.",
      "idea.project_done": "Проект создан — он в слое «Проекты» на карте и во вкладке «Проекты»",
      "idea.published": "Идея опубликована для голосования",
      "idea.rejected_done": "Идея отклонена, причина видна жителям",
      "idea.hidden_done": "Идея скрыта",
      "idea.checked": "Чек-лист сохранён",
      "idea.check_save": "Сохранить чек-лист",
      "idea.project_link": "Проект: {title}",
      "idea.field_required": "Заполните это поле",
      // Дизайн-марафон (12–14 окт): пустые вкладки, пояснения чек-листа, прогресс — I18N_DESIGN_R06.json для R11.
      "idea.empty.title": "Идей пока нет",
      "idea.empty.text": "Предложите первую — соседи смогут её поддержать.",
      "idea.empty.project": "Пока ни одна идея не стала проектом",
      "idea.empty.rejected": "Отклонённых идей нет",
      "idea.check.hint.land": "Участок свободен, его можно занять",
      "idea.check.hint.networks": "Трубы и кабели под землёй не мешают",
      "idea.check.hint.access": "Можно подойти, в том числе с коляской",
      "idea.check.hint.maintenance": "Есть кому убирать и чинить",
      "idea.check.progress": "«Да»: {n} из 4",
      "idea.check.ready": "Все четыре — «да»: можно делать проектом",
      "idea.hide_short": "Скрыть",
    },
    kk: {
      "idea.status.review": "Тексерілуде",
      "idea.status.hidden": "Жарияланбады",
      "idea.hidden_note": "Идея тексеруден өтпеді: онда жеке деректер, дөрекі сөздер немесе жарнама бар.",
      "idea.mine": "Сіздің идеяңыз",
      "idea.kind_none": "Идея",
      "idea.place": "Бұл қай жерге керек?",
      "idea.place_pick": "Картадан орын таңдау",
      "idea.place_change": "Орынды өзгерту",
      "idea.place_hint": "Идея керек жерді картадан басыңыз, содан кейін «Дайын» түймесін басыңыз",
      "idea.place_chosen": "Орын таңдалды: {street}",
      "idea.place_chosen_plain": "Орын таңдалды",
      "idea.place_refine": "Дәлірек басуға немесе «Дайын» түймесін басуға болады",
      "idea.place_needed": "Алдымен картадан орын таңдаңыз",
      "idea.map_unavailable": "Карта қазір қолжетімсіз. Бетті жаңартыңыз.",
      "idea.sent_next": "Әзірге оны тек сіз көресіз — «Идеялар» тізімінде «Тексерілуде» белгісімен.",
      "idea.support_saved": "Қолдауыңыз есепке алынды",
      "idea.support_removed": "Қолдау алынды",
      "idea.limit_support": "Бұл құрылғыдан немесе желіден осы идеяға дауыс көп берілді. Ертең қайталап көріңіз.",
      "idea.limit_new": "Бұл құрылғыдан немесе желіден жаңа идея көп жіберілді. Кейінірек қайталап көріңіз.",
      "idea.limit_review": "Сізде тексерудегі 3 идея бар. Әкімдіктің жауабын күтіңіз.",
      "idea.voting_closed": "Бұл идея бойынша дауыс беру жабылды",
      "idea.error": "Сақтау мүмкін болмады. Байланысты тексеріп, қайталаңыз.",
      "idea.not_found": "Идея табылмады",
      "idea.empty.review": "Тексерудегі жаңа идея жоқ",
      "idea.decided": "Шешім қабылданған идеялар",
      "idea.check_open": "Тексеру",
      "idea.check_close": "Жасыру",
      "idea.hide": "Жасыру: жеке деректер немесе дөрекі сөздер",
      "idea.hide_reason": "Неге жасыру керек (тек қызметкерлер көреді)",
      "idea.hide_confirm": "Идеяны жасыру",
      "idea.project_kind": "Қандай нысан қою керек",
      "idea.lighting_note": "Жарық көше бойымен қойылады: оны картадағы «Не салайық?» каталогынан қосыңыз.",
      "idea.project_done": "Жоба құрылды — ол картадағы «Жобалар» қабатында және «Жобалар» қойындысында",
      "idea.published": "Идея дауыс беруге жарияланды",
      "idea.rejected_done": "Идеядан бас тартылды, себебін тұрғындар көреді",
      "idea.hidden_done": "Идея жасырылды",
      "idea.checked": "Тексеру парағы сақталды",
      "idea.check_save": "Тексеру парағын сақтау",
      "idea.project_link": "Жоба: {title}",
      "idea.field_required": "Бұл өрісті толтырыңыз",
      "idea.empty.title": "Әзірге идея жоқ",
      "idea.empty.text": "Біріншісін ұсыныңыз — көршілеріңіз қолдай алады.",
      "idea.empty.project": "Әзірге бірде-бір идея жобаға айналмады",
      "idea.empty.rejected": "Қабылданбаған идея жоқ",
      "idea.check.hint.land": "Учаске бос, оны алуға болады",
      "idea.check.hint.networks": "Жер астындағы құбыр мен кабель кедергі емес",
      "idea.check.hint.access": "Балалар арбасымен де жетуге болады",
      "idea.check.hint.maintenance": "Тазалап, жөндейтін жауапты бар",
      "idea.check.progress": "«Иә»: {n}/4",
      "idea.check.ready": "Төртеуі де «иә»: жобаға айналдыруға болады",
      "idea.hide_short": "Жасыру",
    },
  };

  // ── тексты ──
  function I() {
    return root.BirgeI18n || null;
  }
  function lang() {
    return I() ? I().getLang() : "ru";
  }
  function pluralRu(n) {
    var a = Math.abs(n), m10 = a % 10, m100 = a % 100;
    if (m10 === 1 && m100 !== 11) return "one";
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "few";
    return "many";
  }
  function fill(text, params) {
    return String(text).replace(/\{(\w+)\}/g, function (whole, name) {
      if (!params || params[name] == null) return whole;
      var v = params[name];
      return typeof v === "number" && I() ? I().formatNumber(v) : String(v);
    });
  }
  // Словарь R11 на языке интерфейса → запас из KEYS → словарь R11 на ru → сам ключ.
  function tr(key, params) {
    var i18n = I(), l = lang() === "kk" ? "kk" : "ru";
    if (i18n && i18n.has(key)) return i18n.t(key, params);
    var v = R11_KEYS[l][key] != null ? R11_KEYS[l][key] : KEYS[l][key] != null ? KEYS[l][key] : null;
    if (v == null && i18n && i18n.has(key, "ru")) return i18n.t(key, params);
    if (v == null) v = KEYS.ru[key] != null ? KEYS.ru[key] : key;
    if (typeof v === "object") v = v[l === "ru" ? pluralRu(params && params.n || 0) : "other"] || v.many || v.other;
    return fill(v, params);
  }
  // Текст жителя или демо: на языке интерфейса, если есть; иначе как написан (с lang для экранного диктора).
  function textOf(item, field) {
    var l = lang();
    var own = item[field + "_" + l];
    if (item.demo || item.lang === l) return { text: own || item[field] || "", lang: own ? l : item.lang || "ru" };
    return { text: item[field] || own || "", lang: item.lang || "ru" };
  }

  // ── DOM ──
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
    var span = doc.createElement("span");
    span.style.display = "contents";
    span.innerHTML = root.BirgeUI ? root.BirgeUI.icon(name) : "";
    return span.firstChild || doc.createTextNode("");
  }
  // «вид · район · Пример»: точка прилипает к слову слева (неразрывный пробел), перенос — только после точки.
  function metaParts(parts) {
    var out = [];
    parts.forEach(function (p, i) {
      if (i) out.push(doc.createTextNode("\u00a0· "));
      out.push(p);
    });
    return out;
  }
  function button(cls, label, ic, attrs) {
    return h("button", Object.assign({ type: "button", class: "bk-btn" + (cls ? " " + cls : "") }, attrs || {}),
      [ic ? icon(ic) : null, h("span", { text: label })]);
  }
  function toast(text, opts) {
    if (root.BirgeUI) root.BirgeUI.toast(text, opts);
  }
  function stateBox(el, kind, opts) {
    if (root.BirgeUI) return root.BirgeUI.state(el, kind, opts || {});
    el.textContent = (opts && opts.title) || tr(kind === "error" ? "common.state.error_title" : "common.state.empty_title");
  }
  function store(key, value) {
    try {
      if (value === undefined) return root.localStorage.getItem(key);
      if (value === null) root.localStorage.removeItem(key);
      else root.localStorage.setItem(key, value);
    } catch (e) {
      return null; // приватный режим — без памяти
    }
    return null;
  }

  // ── устройство: тот же id, что у голосов за проекты ──
  function deviceId() {
    if (root.BirgeProposals && root.BirgeProposals.deviceId) return root.BirgeProposals.deviceId();
    var id = store(DEVICE_KEY);
    if (!id || !/^[A-Za-z0-9._:-]{16,128}$/.test(id)) {
      var bytes = new Uint8Array(16);
      root.crypto.getRandomValues(bytes);
      id = "dev-" + Array.prototype.map.call(bytes, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
      store(DEVICE_KEY, id);
    }
    return id;
  }

  // ── запросы: клиент оболочки R01 (api.v2) или fetch на отдельной странице ──
  function makeRequest(opts) {
    var v2 = opts.api && typeof opts.api.v2 === "function" ? opts.api.v2 : null;
    // Чтение для сотрудника (GET /staff/ideas, GET /works): шлюз R01 для staff-маршрутов требует CSRF-токен и на GET
    // (R15 route policy), а клиент оболочки шлёт его только в изменяющих запросах — такие GET идут напрямую с токеном.
    var staffGet = function (method, path) { return method === "GET" && /^\/(staff\/|works(\?|$))/.test(path); };
    // Все запросы сотрудника (чтение очереди, решения по идеям, записи «Рядом») — напрямую с токеном: не зависят от того,
    // успела ли оболочка узнать сессию после перезагрузки страницы.
    var staffPath = function (path) { return /^\/(staff\/|works(\/|\?|$))/.test(path) || /^\/ideas\/[^/]+\/decide$/.test(path); };
    // Токен сотрудника: у оболочки (CivicShell) — когда она уже узнала сессию; иначе (экран открыт сразу после
    // перезагрузки) — из GET /api/civic/v1/session, как у карточек R06 (proposals.js).
    var token = null;
    function csrf(fresh) {
      var shellToken = root.CivicShell && root.CivicShell.csrfToken ? root.CivicShell.csrfToken() : null;
      if (shellToken && !fresh) return Promise.resolve(shellToken);
      if (token && !fresh) return Promise.resolve(token);
      return root.fetch("/api/civic/v1/session", { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (j) { var d = (j && j.data) || j || {}; token = d.authenticated ? d.csrf_token || null : null; return token; },
          function () { return null; });
    }
    function direct(method, path, body, retried) {
      return csrf(retried).then(function (tok) {
        var headers = { Accept: "application/json" };
        if (body !== undefined) headers["Content-Type"] = "application/json";
        if (tok && (method !== "GET" || staffGet(method, path))) headers["X-CSRF-Token"] = tok;
        return root.fetch((opts.apiBase || API) + path, { method: method, headers: headers, credentials: "same-origin",
          body: body !== undefined ? JSON.stringify(body) : undefined });
      }).then(function (res) {
        return res.json().catch(function () { return null; }).then(function (json) {
          if (res.ok && json && json.ok === true) return json.data; // конверт стенда R06
          if (res.ok) return json;
          var e = (json && json.error) || {};
          var err = new Error((typeof e === "object" ? e.message : json && json.message) || "HTTP " + res.status);
          err.status = res.status;
          err.code = typeof e === "string" ? e : e.code;
          err.fields = (typeof e === "object" && e.fields) || (json && json.fields) || {};
          throw err;
        });
      }, function () {
        var err = new Error("network");
        err.status = 0;
        err.code = "network";
        throw err;
      }).catch(function (err) {
        if (!retried && err.code === "csrf_failed") return direct(method, path, body, true); // токен устарел — один повтор
        throw err;
      });
    }
    return function (method, path, body) {
      if (v2 && !staffPath(path)) {
        return Promise.resolve().then(function () { return v2(method, path, body); }).catch(function (err) {
          err.code = err.code || err.error;
          throw err;
        });
      }
      return direct(method, path, body, false);
    };
  }
  function errorText(err, fallbackKey) {
    if (err.status === 429) return tr("idea.limit_support"); // лимит новых идей мастер показывает сам (idea.limit_new)
    if (err.code === "limit") return tr("idea.limit_review");
    if (err.code === "voting_closed") return tr("idea.voting_closed");
    if (err.code === "already_decided") return tr("proposal.already_decided");
    if (err.status === 401 || err.code === "csrf_failed" || err.code === "unauthenticated") return tr("proposal.need_staff");
    if (err.status === 404) return tr("idea.not_found");
    return tr(fallbackKey || "idea.error");
  }

  // ── карта (MapLibre — глобальная переменная web/map.js; window.map — это элемент #map) ──
  function mapObject() {
    try {
      // eslint-disable-next-line no-undef
      return typeof mapReady !== "undefined" && mapReady && typeof map !== "undefined" && map && typeof map.on === "function" ? map : null;
    } catch (e) {
      return null;
    }
  }
  function shell() {
    return root.BirgeShell || null;
  }
  function build3d() {
    return root.CivicShell && root.CivicShell.build3d ? root.CivicShell.build3d : null;
  }
  function showOnMap(item, opts) {
    var p = item && item.geometry && item.geometry.coordinates;
    if (!p) return;
    if (opts && typeof opts.close === "function") opts.close();
    else if (shell()) shell().setSection("map");
    // Метка идеи видна в слое «Идеи жителей» (R05); без 3D-модуля — просто камера к месту.
    if (shell() && shell().setLayer && build3d() && build3d().setIdeas) shell().setLayer("ideas");
    var m = mapObject();
    if (m) m.easeTo({ center: p, zoom: Math.max(m.getZoom(), 16.5), duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 600 });
  }

  // Улица с названием из ответа R12 /street-snap: сама улица или (у безымянного проезда) улица рядом —
  // near_street_* (patch R12 в INTEGRATION R06). Нет названия — null: подписи и название проекта без улицы.
  function streetOf(s) {
    if (!s) return null;
    if (s.street_ru) return { ru: s.street_ru, kk: s.street_kk || null };
    if (s.near_street_ru) return { ru: s.near_street_ru, kk: s.near_street_kk || null };
    return null;
  }

  // ── черновик новой идеи: живёт дольше экрана (выбор места уводит на карту, экран пересоздаётся) ──
  var draft = null;
  function loadDraft() {
    if (draft) return draft;
    try {
      draft = JSON.parse(store(DRAFT_KEY) || "null");
    } catch (e) {
      draft = null;
    }
    return draft;
  }
  function saveDraft() {
    store(DRAFT_KEY, draft ? JSON.stringify(draft) : null);
  }

  // ── выбор места на карте (мастер, шаг 1) ──
  var picker = null;
  function startPick(onDone) {
    var m = mapObject();
    if (!m || !shell()) {
      toast(tr("idea.map_unavailable"), { type: "error" });
      return;
    }
    shell().setSection("map");
    var point = null, marker = null;
    var done = button("bk-btn--primary", tr("common.action.done"), "check", { disabled: true });
    var cancel = button("bk-btn--ghost", tr("common.action.cancel"), "close");
    var hint = h("p", { class: "ri-pick__hint", role: "status", text: tr("idea.place_hint") });
    // Плавающая панель над картой — стекло ui-kit (GLASS.md); без стекла в ui-kit — белая (ideas.css, :where).
    var bar = h("div", { class: "ri-pick bk-app bk-glass", role: "dialog", "aria-label": tr("idea.place") }, [hint, h("div", { class: "bk-actions" }, [done, cancel])]);
    doc.body.appendChild(bar);
    // Свой класс, не birge-picking оболочки: при нём значки R07 ловят нажатие для мастера жалобы (heat.css).
    // ri-picking: шторка и значки не мешают — нажатие доходит до карты (ideas.css).
    doc.body.classList.add("ri-picking");
    m.getCanvas().style.cursor = "crosshair";
    function onClick(e) {
      point = [Math.round(e.lngLat.lng * 1e6) / 1e6, Math.round(e.lngLat.lat * 1e6) / 1e6];
      if (root.maplibregl && root.maplibregl.Marker) {
        // Булавка места — цвет слоя идей ui-kit (--idea, одна краска), а не синий по умолчанию.
        var ideaColor = (root.getComputedStyle(doc.documentElement).getPropertyValue("--idea") || "").trim() || "#152c26";
        if (!marker) marker = new root.maplibregl.Marker({ color: ideaColor });
        marker.setLngLat(point).addTo(m);
      }
      // На обзоре города точка неточная: приближаем к ней до улиц — второе нажатие уточняет место.
      if (m.getZoom() < 15.5) {
        m.easeTo({ center: point, zoom: 16.5, duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 500 });
      }
      done.disabled = false;
      hint.textContent = tr("idea.place_chosen_plain") + ". " + tr("idea.place_refine");
      done.focus();
    }
    function finish(ok) {
      m.off("click", onClick);
      m.getCanvas().style.cursor = "";
      if (marker) marker.remove();
      bar.remove();
      doc.body.classList.remove("ri-picking");
      doc.removeEventListener("keydown", onKey, true);
      picker = null;
      onDone(ok ? point : null);
    }
    function onKey(e) {
      if (e.key === "Escape") finish(false);
    }
    m.on("click", onClick);
    doc.addEventListener("keydown", onKey, true);
    done.addEventListener("click", function () { if (point) finish(true); });
    cancel.addEventListener("click", function () { finish(false); });
    picker = { finish: finish };
    setTimeout(function () { cancel.focus(); }, 0);
  }

  // ===================================================================================== экран
  function mount(rootEl, options) {
    var opts = Object.assign({ titleTag: "h2" }, options || {});
    var akimat = opts.section === "projects" || opts.role === "akimat";
    var request = makeRequest(opts);
    var state = {
      tab: akimat ? "review" : "voting",
      items: null, counts: {}, projects: null, error: null, view: "list", open: null, busy: false,
      flash: pendingFocus, step: 1, sent: null,
    };
    pendingFocus = null;
    var alive = true;
    rootEl.classList.add("ri");
    if (!akimat && loadDraft() && draft.active) state.view = "new";
    if (state.view === "new") state.step = draft.step || 1;

    // ── загрузка ──
    function load() {
      state.error = null;
      // Акимат: на проверке и голосовании — сверху; решённые (отклонена, стала проектом) — свёрнуто внизу: их можно скрыть
      // (R15-S30: личные данные заметили позже, просьба автора).
      var q = akimat ? request("GET", "/staff/ideas?status=review,voting,checking,rejected,project")
        : request("GET", "/ideas?device_id=" + encodeURIComponent(deviceId()));
      var p = akimat ? request("GET", "/proposals?device_id=" + encodeURIComponent(deviceId())) : Promise.resolve(null);
      state.items = null;
      render();
      return Promise.all([q, p.catch(function () { return null; })]).then(function (res) {
        if (!alive) return;
        state.items = (res[0] && res[0].items) || [];
        state.counts = (res[0] && res[0].counts) || {};
        state.appear = true;
        state.projects = res[1] ? res[1].items || [] : [];
        if (state.flash) focusIdea(state.flash);
        render();
      }, function (err) {
        if (!alive) return;
        state.error = err;
        render();
      });
    }
    function focusIdea(id) {
      var item = (state.items || []).filter(function (x) { return x.id === id; })[0];
      if (!item) return;
      if (akimat) {
        state.tab = "review";
        state.open = id;
      } else if (TAB_OF[item.status]) state.tab = TAB_OF[item.status];
    }
    function replace(item) {
      state.items = (state.items || []).map(function (x) { return x.id === item.id ? item : x; });
    }

    // ── отрисовка ──
    function render() {
      if (!alive) return;
      var focusKey = doc.activeElement && rootEl.contains(doc.activeElement) ? doc.activeElement.getAttribute("data-key") : null;
      rootEl.replaceChildren(h(opts.titleTag, { class: "bk-h1 ri-title", text: tr(akimat ? "common.nav.projects" : "idea.title") }));
      if (state.view === "new") renderWizard();
      else if (state.view === "sent") renderSent();
      else renderList();
      if (focusKey) {
        var again = rootEl.querySelector('[data-key="' + focusKey + '"]');
        if (again) again.focus();
      }
      if (state.flash && rootEl.querySelector('[data-idea="' + state.flash + '"]')) {
        var card = rootEl.querySelector('[data-idea="' + state.flash + '"]');
        card.classList.add("ri-card--flash");
        card.scrollIntoView({ block: "center" });
        state.flash = null;
      }
    }

    // Правило — всегда видно (R11 SCHEMES §2.1): ⓘ и серый текст (bk-banner чистого дизайна), под ним — «Бюджет участия»
    // только текстом (без ссылки: это отдельная программа акимата, не подключённый сервис).
    function honest() {
      return h("div", { class: "ri-rule" }, [
        h("div", { class: "bk-banner ri-honest", role: "note" }, [icon("info"), h("p", { class: "bk-banner__title", text: tr("idea.honest") })]),
        h("p", { class: "bk-meta ri-pb", text: tr("idea.pb_note") }),
      ]);
    }

    // Вкладки ui-kit R11 (bk-tabs, role=tablist/tab, стрелки, затухание края на 375). Без BirgeUI.tabs (ui-kit до 12 окт) —
    // та же разметка, нажатие и стрелки — здесь.
    function tabs(list) {
      var row = h("div", { class: "bk-tabs ri-tabs", role: "tablist", "aria-label": tr(akimat ? "common.nav.projects" : "idea.title") });
      list.forEach(function (t) {
        var on = state.tab === t.id;
        row.appendChild(h("button", { type: "button", role: "tab", value: t.id, "aria-selected": String(on), tabindex: on ? "0" : "-1",
          "data-key": "tab-" + t.id }, [t.label, t.n != null ? h("span", { class: "bk-num", text: " " + t.n }) : null]));
      });
      function choose(id) {
        if (id && id !== state.tab) {
          state.tab = id;
          state.open = null;
          state.appear = true;
          render();
        }
      }
      if (root.BirgeUI && typeof root.BirgeUI.tabs === "function") root.BirgeUI.tabs(row, choose);
      else {
        row.addEventListener("click", function (e) {
          var b = e.target.closest && e.target.closest("[role=tab]");
          if (b) choose(b.value);
        });
        row.addEventListener("keydown", function (e) {
          if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
          var all = Array.prototype.slice.call(row.querySelectorAll("[role=tab]")), i = all.indexOf(doc.activeElement);
          if (i < 0) return;
          e.preventDefault();
          choose(all[(i + (e.key === "ArrowRight" ? 1 : all.length - 1)) % all.length].value);
        });
      }
      return row;
    }

    function renderList() {
      if (!akimat) {
        rootEl.appendChild(honest());
        rootEl.appendChild(h("div", { class: "bk-actions ri-new" }, [
          button("bk-btn--primary", tr("idea.new"), "plus", { "data-key": "new", onclick: startWizard })]));
      }
      var body = h("div", { class: "ri-body" });
      if (state.error) {
        if (akimat && (state.error.status === 401 || state.error.status === 403)) {
          // R11 разбор FINAL-3: кнопка входа прямо здесь (иначе вход спрятан в меню аватара)
          stateBox(body, "empty", { title: tr("proposal.need_staff"), icon: "user", action: { label: tr("staff.login.submit"),
            onClick: function () { if (root.BirgeShell) root.BirgeShell.setSection("map"); if (root.CivicShell && root.CivicShell.openEditor) root.CivicShell.openEditor(); } } });
        } else {
          stateBox(body, "error", { action: { onClick: load } });
        }
        rootEl.appendChild(body);
        return;
      }
      if (!state.items) {
        skeleton(body);
        rootEl.appendChild(body);
        return;
      }
      if (akimat) {
        var review = state.items.filter(function (x) { return x.status === "review" || x.status === "voting" || x.status === "checking"; });
        var projects = (state.projects || []);
        rootEl.appendChild(tabs([{ id: "review", label: tr("idea.tab.review"), n: review.length },
          { id: "projects", label: tr("idea.tab.projects"), n: projects.length }]));
        if (state.tab === "projects") renderProjects(body, projects);
        else renderStaffIdeas(body, review);
      } else {
        if (!state.items.length) {
          // Идей нет совсем — без пустых вкладок «0 · 0 · 0»: иллюстрация и подсказка (главная кнопка — выше).
          emptyBox(body, tr("idea.empty.title"), tr("idea.empty.text"));
          rootEl.appendChild(body);
          return;
        }
        var counts = {};
        RESIDENT_TABS.forEach(function (s) { counts[s] = state.items.filter(function (x) { return TAB_OF[x.status] === s; }).length; });
        rootEl.appendChild(tabs(RESIDENT_TABS.map(function (s) { return { id: s, label: tr("idea.tab." + s), n: counts[s] }; })));
        var shown = state.items.filter(function (x) {
          return TAB_OF[x.status] === state.tab || (state.tab === "voting" && x.mine && (x.status === "review" || x.status === "hidden"));
        });
        // Правило голоса — один раз над списком (раньше — под каждой «Поддержать»); кнопки ссылаются на него (aria-describedby).
        if (shown.some(function (x) { return x.status === "voting"; })) {
          rootEl.appendChild(h("p", { class: "bk-meta ri-onevote", id: "ri-onevote" }, [icon("info"), h("span", { text: tr("proposal.one_vote") })]));
        }
        if (!shown.length) {
          if (state.tab === "project") emptyBox(body, tr("idea.empty.project"), null, ["square", "sports"]);
          else if (state.tab === "rejected") emptyBox(body, tr("idea.empty.rejected"), null, ["check"]);
          else emptyBox(body, tr("idea.empty.title"), tr("idea.empty.text"));
        }
        shown.forEach(function (item) { body.appendChild(residentCard(item)); });
      }
      // Карточки мягко появляются одна за другой (40 мс) — только после загрузки и смены вкладки, не при каждой перерисовке.
      if (state.appear) {
        body.classList.add("ri-body--in");
        Array.prototype.forEach.call(body.children, function (el, i) { el.style.setProperty("--ri-i", String(Math.min(i, 8))); });
        state.appear = false;
      }
      rootEl.appendChild(body);
    }

    // ── карточка (дизайн-марафон: «как в App Store») ──
    // Плитка-иллюстрация вида объекта слева, справа — тихая строка «вид · район · Пример», название и одна строка статуса.
    // Внизу — число голосов (перекатывается при поддержке), «На карте» и капсула «Поддержать» / «Проверить».
    function tile(item) {
      var kind = item.object && item.object.kind;
      return h("span", { class: "ri-tile", "data-kind": kind || "none", "data-idea-status": item.status, "aria-hidden": "true" }, [
        icon(kind ? KIND_ICON[kind] : "pin"),
        item.status === "project" ? h("span", { class: "ri-tile__badge" }, [icon("check")]) : null,
      ]);
    }
    function metaLine(item) {
      var kind = item.object && item.object.kind;
      var parts = [h("span", { text: kind ? tr("proposal.kind." + kind) : tr("idea.kind_none") })];
      if (item.district) parts.push(h("span", { text: tr("district.name", { name: tr("district." + item.district) }) }));
      if (item.demo) parts.push(h("span", { class: "bk-tag bk-tag--demo", title: tr("common.tag.demo_hint"), text: tr("common.tag.demo") }));
      var row = h("p", { class: "ri-meta" }, metaParts(parts));
      if (item.mine) row.appendChild(h("span", { class: "bk-tag ri-mine", text: tr("idea.mine") }));
      return row;
    }
    // Статус идеи — своя точка (одна краска, R11 data-status оставлен для тестов и запасного вида ui-kit).
    function statusLine(item) {
      return h("p", { class: "ri-line" }, [h("span", { class: "bk-status", "data-status": STATUS_LOOK[item.status] || "new",
        "data-idea-status": item.status, text: tr("idea.status." + item.status) })]);
    }
    function titleEl(item) {
      var t = textOf(item, "title");
      return h("h3", { class: "bk-card__title ri-title-text", id: "ri-t-" + item.id, lang: t.lang, text: t.text });
    }
    function head(item) {
      return h("div", { class: "ri-app" }, [tile(item), h("div", { class: "ri-app__body" }, [metaLine(item), titleEl(item), statusLine(item)])]);
    }
    // «47 голосов»: число — отдельным элементом, чтобы при поддержке оно «перекатилось» (+1 снизу, −1 сверху).
    function votesEl(item) {
      var n = item.votes || 0;
      var full = tr("idea.votes", { n: n }), num = I() ? I().formatNumber(n) : String(n), at = full.indexOf(num);
      var bump = state.bump && state.bump.id === item.id ? state.bump.dir : 0;
      var numEl = h("span", { class: "ri-votes__n bk-num" + (bump > 0 ? " ri-roll-up" : bump < 0 ? " ri-roll-down" : ""), text: num });
      // Число сверху крупно, слово под ним мелко (как оценки в App Store) — узкая колонка, капсула на телефоне в той же строке.
      if (at === 0) return h("p", { class: "ri-votes ri-votes--stack" }, [numEl, h("span", { class: "ri-votes__w", text: full.slice(num.length).trim() })]);
      return h("p", { class: "ri-votes" }, at < 0 ? [full] : [full.slice(0, at), numEl, full.slice(at + num.length)]);
    }
    // «Подпись: текст» — подпись жирным, текст обычным (раньше вся строка «Можно доработать: …» была жирной).
    function labeled(key, text, cls) {
      var mark = "\u0001", full = tr(key, { text: mark }), at = full.indexOf(mark);
      if (at < 0) return h("p", { class: cls, text: tr(key, { text: text }) });
      return h("p", { class: cls }, [h("strong", { text: full.slice(0, at).replace(/\s+$/, "") }), " " + text + full.slice(at + 1)]);
    }
    function decisionBlock(item) {
      if (item.status === "rejected") {
        var l = lang();
        return h("div", { class: "ri-decision" }, [
          labeled("idea.reason", item["reason_" + l] || item.reason || "", "ri-reason-text"),
          item.can_improve ? labeled("idea.can_improve", item["can_improve_" + l] || item.can_improve, "ri-improve") : null,
        ]);
      }
      if (item.status === "project" && item.project) {
        // «До → после»: идея жителей с голосами → проект (лента из двух шагов).
        var title = lang() === "kk" && item.project.title_kk ? item.project.title_kk : item.project.title_ru;
        return h("ol", { class: "ri-path" }, [
          h("li", {}, [h("p", { text: tr("idea.by_residents", { n: item.votes_at_decision || item.votes }) })]),
          h("li", { "data-state": "now" }, [h("p", { text: tr("idea.project_link", { title: title }) })]),
        ]);
      }
      if (item.status === "hidden") return h("p", { class: "ri-decision", text: tr("idea.hidden_note") });
      return null;
    }
    function details(item) {
      var d = textOf(item, "description");
      var kids = [h("summary", { text: tr("common.action.more") })];
      if (d.text) kids.push(h("p", { class: "ri-text", lang: d.lang, text: d.text }));
      if (item.object && item.object.kind && build3d() && build3d().view3dIdea && item.status !== "hidden") {
        // «Лёгкая карточка раньше 3D» (R05): 3D — только по кнопке.
        kids.push(button("bk-btn--ghost ri-3d", tr("idea.view3d"), "cube", { onclick: function () {
          showOnMap(item, opts);
          build3d().view3dIdea(r05Idea(item));
        } }));
      }
      if (item.check) kids.push(checklistView(item.check));
      return kids.length > 1 ? h("details", { class: "bk-details ri-more" }, kids) : null;
    }
    function checklistView(check) {
      return h("div", { class: "ri-check" }, [h("p", { class: "ri-check__title", text: tr("idea.check.title") })].concat(
        CHECK_KEYS.map(function (k) {
          return h("p", { class: "ri-check__row" }, [h("span", {}, [icon(CHECK_ICON[k]), h("span", { text: tr("idea.check." + k) })]),
            h("span", { class: "ri-check__answer", "data-answer": check[k], text: tr("idea.check.answer." + check[k]) })]);
        })));
    }
    function mapButton(item) {
      // На телефоне — только значок (подпись остаётся для диктора и подсказкой), на ноутбуке — значок и «На карте».
      return button("bk-btn--ghost ri-mapbtn", tr("map.card.on_map"), "pin",
        { "data-key": "map-" + item.id, title: tr("map.card.on_map"), onclick: function () { showOnMap(item, opts); } });
    }
    function residentCard(item) {
      var supportBtn = null;
      if (item.status === "voting") {
        var on = !!item.my_support, popped = state.bump && state.bump.id === item.id;
        supportBtn = button("ri-support" + (popped ? " ri-pop" : ""), tr(on ? "idea.supported" : "idea.support"), on ? "check" : "thumb-up",
          { "aria-pressed": String(on), "data-key": "support-" + item.id, "aria-describedby": "ri-t-" + item.id + " ri-onevote",
            onclick: function () { support(item, !item.my_support, supportBtn); } });
      }
      // Голоса — у идей на голосовании и отклонённых; у проекта они уже в ленте «По идее жителей · N голосов».
      var counted = item.status !== "review" && item.status !== "hidden" && item.status !== "project";
      var foot = h("div", { class: "ri-foot" }, [counted ? votesEl(item) : h("span", { class: "ri-foot__space" }),
        item.status !== "hidden" ? mapButton(item) : null, supportBtn]);
      return h("article", { class: "bk-card ri-card", "data-idea": item.id, "data-idea-status": item.status, "aria-labelledby": "ri-t-" + item.id }, [
        head(item), decisionBlock(item), foot, details(item),
      ]);
    }
    function support(item, on, btn) {
      if (state.busy) return;
      state.busy = true;
      btn.setAttribute("aria-busy", "true");
      request("POST", "/ideas/" + encodeURIComponent(item.id) + "/support", { device_id: deviceId(), on: on }).then(function (data) {
        state.busy = false;
        var was = item.votes || 0;
        replace(data.item);
        // Отклик: капсула чуть «подпрыгивает», число перекатывается на новое значение (один раз, без мигания при перерисовке).
        state.bump = { id: item.id, dir: (data.item.votes || 0) >= was ? 1 : -1 };
        render();
        setTimeout(function () { if (state.bump && state.bump.id === item.id) state.bump = null; }, 600);
        // Подтверждение — сама капсула («Вы поддержали», галочка) и число; тост внизу экрана не закрывает список.
        // Для экранного диктора — та же фраза в живой области.
        announce(tr(on ? "idea.support_saved" : "idea.support_removed"));
      }, function (err) {
        state.busy = false;
        btn.removeAttribute("aria-busy");
        var retry = err.status === 0 || err.status >= 500;
        toast(errorText(err), retry ? { type: "error", action: { label: tr("common.action.retry"), onClick: function () { support(item, on, btn); } } } : { type: "error" });
        if (err.code === "voting_closed") load();
      });
    }

    // Живая область для диктора (вне перерисовываемого списка — иначе новая область с текстом не читается).
    var live = h("p", { class: "bk-sr-only", role: "status", "aria-live": "polite" });
    function announce(text) {
      if (!live.isConnected) doc.body.appendChild(live);
      live.textContent = "";
      setTimeout(function () { live.textContent = text; }, 60);
    }

    // ── состояния списка: скелетон, пусто ──
    function skeleton(body) {
      body.setAttribute("aria-busy", "true");
      for (var i = 0; i < 3; i++) {
        body.appendChild(h("div", { class: "bk-card ri-skelcard", "aria-hidden": "true" }, [
          h("div", { class: "ri-app" }, [h("span", { class: "bk-skel ri-tile" }), h("div", { class: "ri-app__body" }, [
            h("span", { class: "bk-skel bk-skel--line", style: "width:40%" }), h("span", { class: "bk-skel bk-skel--title" }),
            h("span", { class: "bk-skel bk-skel--line", style: "width:30%" })])]),
          h("div", { class: "ri-foot" }, [h("span", { class: "bk-skel bk-skel--line", style: "width:22%" }), h("span", { class: "bk-skel ri-skel-pill" })]),
        ]));
      }
      body.appendChild(h("p", { class: "bk-sr-only", role: "status", text: tr("common.state.loading") }));
    }
    // Пусто: иллюстрация из линий ui-kit (три плитки видов объектов), заголовок и одна строка подсказки.
    function emptyBox(body, title, text, kinds) {
      body.appendChild(h("div", { class: "ri-empty", role: "status" }, [
        h("div", { class: "ri-empty__art", "aria-hidden": "true" }, (kinds || ["square", "playground", "lighting"]).map(function (k) {
          return h("span", { class: "ri-tile", "data-kind": k }, [icon(KIND_ICON[k] || k)]);
        })),
        h("p", { class: "ri-empty__title", text: title }),
        text ? h("p", { class: "ri-empty__text", text: text }) : null,
      ]));
    }

    // ── акимат: идеи на проверке ──
    function renderStaffIdeas(body, list) {
      if (!list.length) emptyBox(body, tr("idea.empty.review"), null, ["check"]);  // «Новых идей на проверке нет»
      list.forEach(function (item) { body.appendChild(staffCard(item)); });
      var decided = (state.items || []).filter(function (x) { return x.status === "rejected" || x.status === "project"; });
      if (!decided.length) return;
      var box = h("details", { class: "bk-details ri-decided" }, [h("summary", { text: tr("idea.decided") + " · " + decided.length })]);
      if (state.decidedOpen || decided.some(function (x) { return x.id === state.open; })) box.open = true;
      box.addEventListener("toggle", function () { state.decidedOpen = box.open; });
      decided.forEach(function (item) { box.appendChild(staffCard(item)); });
      body.appendChild(box);
    }
    function isDecided(item) {
      return item.status === "rejected" || item.status === "project";
    }
    function staffCard(item) {
      var open = state.open === item.id;
      var d = textOf(item, "description");
      var toggle;
      if (isDecided(item)) {
        // Решённую идею проверять нечего — сразу тихая «Скрыть» (R15-S30: личные данные заметили позже, просьба автора).
        // Короткое «Скрыть» в строке карточки; почему скрывают (личные данные, грубые слова) — в подписи поля причины.
        toggle = button("bk-btn--ghost ri-hidebtn", tr(open ? "idea.check_close" : "idea.hide_short"), open ? "chevron-down" : null,
          { "aria-expanded": String(open), "data-key": "open-" + item.id, onclick: function () {
            state.open = open ? null : item.id;
            state.panelIn = state.open;
            state.form = null;
            render();
          } });
      } else {
        toggle = button("ri-capsule" + (open ? " bk-btn--ghost" : ""), tr(open ? "idea.check_close" : "idea.check_open"), open ? "chevron-down" : "edit",
          { "aria-expanded": String(open), "data-key": "open-" + item.id, onclick: function () {
            state.open = open ? null : item.id;
            state.panelIn = state.open;
            state.form = null;
            render();
          } });
      }
      var counted = item.status !== "review" && item.status !== "hidden";
      var kids = [head(item)];
      if (d.text) kids.push(h("p", { class: "ri-text", lang: d.lang, text: d.text }));
      kids.push(h("div", { class: "ri-foot" }, [counted ? votesEl(item) : h("span", { class: "ri-foot__space" }), mapButton(item), toggle]));
      if (open) kids.push(staffPanel(item));
      return h("article", { class: "bk-card ri-card" + (open ? " ri-card--open" : ""), "data-idea": item.id, "data-idea-status": item.status,
        "aria-labelledby": "ri-t-" + item.id }, kids);
    }
    // Чек-лист реализуемости: у каждого пункта значок, название и что проверить; «да» — тёмная капсула с галочкой,
    // «нет» — красным, «не знаю» — белая. Сверху — «Да: n из 4» и полоса из четырёх сегментов.
    function checkForm(item, form) {
      var yes = CHECK_KEYS.filter(function (k) { return form.check[k] === "yes"; }).length;
      var fs = h("fieldset", { class: "ri-checkform" }, [
        h("legend", { class: "ri-checkform__legend" }, [h("span", { text: tr("idea.check.title") }),
          h("span", { class: "bk-meta ri-checkform__count", text: tr("idea.check.progress", { n: yes }) })]),
        h("div", { class: "ri-meter", "aria-hidden": "true" }, CHECK_KEYS.map(function (k) { return h("i", { "data-answer": form.check[k] }); })),
      ]);
      CHECK_KEYS.forEach(function (k) {
        var seg = h("div", { class: "bk-seg ri-answer", role: "radiogroup", "aria-label": tr("idea.check." + k) });
        ANSWERS.forEach(function (a) {
          var on = form.check[k] === a;
          seg.appendChild(h("button", { type: "button", role: "radio", "aria-checked": String(on), "aria-pressed": String(on), "data-answer": a,
            "data-key": "check-" + k + "-" + a, onclick: function () { form.check[k] = a; render(); } },
            [on && a === "yes" ? icon("check") : null, tr("idea.check.answer." + a)]));
        });
        fs.appendChild(h("div", { class: "ri-checkform__row", "data-answer": form.check[k] }, [
          h("span", { class: "ri-checkform__icon", "aria-hidden": "true" }, [icon(CHECK_ICON[k])]),
          h("span", { class: "ri-checkform__text" }, [h("span", { class: "ri-checkform__name", text: tr("idea.check." + k) }),
            h("span", { class: "bk-meta", text: tr("idea.check.hint." + k) })]),
          seg]));
      });
      return fs;
    }
    function staffPanel(item) {
      var form = state.form || (state.form = { id: item.id, check: Object.assign({ land: "unknown", networks: "unknown", access: "unknown", maintenance: "unknown" }, item.check || {}),
        kind: item.object && item.object.kind || null, mode: isDecided(item) ? "hide" : null, reason: "", improve: "" });
      // Панель раскрывается мягко — только в момент открытия (ответы чек-листа перерисовывают её без движения).
      var panel = h("div", { class: "ri-panel" + (state.panelIn === item.id ? " ri-step-in ri-step-in--down" : "") });
      if (state.panelIn === item.id) state.panelIn = null;
      if (isDecided(item)) {
        // R15-S30: уже решённую идею можно скрыть — сразу форма причины (кнопка «Скрыть» — в строке карточки).
        form.mode = "hide";
      } else if (item.status === "review") {
        // Модерация до голосования (R11 SCHEMES §2.3): «Опубликовать» / «Отклонить с причиной»; третья, тихая кнопка —
        // «Скрыть» для личных данных и грубых слов (отклонённая идея видна всем, скрытая — нет).
        panel.appendChild(h("div", { class: "bk-actions ri-decide" }, [
          button("bk-btn--primary", tr("ask.staff.publish"), "check", { "data-key": "publish", onclick: function () { decide(item, { action: "publish" }, "idea.published"); } }),
          button("", tr("ask.staff.reject"), "close", { onclick: function () { form.mode = "reject"; render(); } }),
        ]));
        panel.appendChild(button("bk-btn--ghost ri-hidebtn", tr("idea.hide"), null, { onclick: function () { form.mode = "hide"; render(); } }));
      } else {
        panel.appendChild(checkForm(item, form));
        panel.appendChild(button("bk-btn--ghost ri-savecheck", tr("idea.check_save"), "check", { onclick: function () { decide(item, { action: "check", check: form.check }, "idea.checked", true); } }));
        if (!(item.object && item.object.kind)) {
          var chips = h("div", { class: "bk-chips bk-chips--wrap", role: "radiogroup", "aria-label": tr("idea.project_kind") });
          KINDS.forEach(function (k) {
            chips.appendChild(h("button", { type: "button", class: "bk-chip", role: "radio", "aria-checked": String(form.kind === k),
              onclick: function () { form.kind = k; render(); } }, [icon(KIND_ICON[k]), tr("proposal.kind." + k)]));
          });
          panel.appendChild(h("p", { class: "ri-label", text: tr("idea.project_kind") }));
          panel.appendChild(chips);
        }
        var lighting = form.kind === "lighting";
        // «Сделать проектом» — только при четырёх «да» (R11 SCHEMES §2.3; сервер проверяет то же).
        var allYes = CHECK_KEYS.every(function (k) { return form.check[k] === "yes"; });
        if (!allYes) panel.appendChild(h("p", { class: "bk-meta ri-hint", id: "ri-hint-" + item.id, text: tr("idea.staff.check_hint") }));
        else panel.appendChild(h("p", { class: "ri-ready", role: "status" }, [icon("check"), h("span", { text: tr("idea.check.ready") })]));
        if (lighting) panel.appendChild(h("p", { class: "bk-meta", text: tr("idea.lighting_note") }));
        panel.appendChild(h("div", { class: "bk-actions ri-decide" }, [
          button("bk-btn--primary", tr("idea.make_project"), "check", { "data-key": "project", disabled: !allYes || !form.kind || lighting,
            "aria-describedby": allYes ? null : "ri-hint-" + item.id, onclick: function () { makeProject(item, form); } }),
          button("", tr("idea.reject"), "close", { onclick: function () { form.mode = "reject"; render(); } }),
        ]));
      }
      if (form.mode === "reject" || form.mode === "hide") panel.appendChild(reasonForm(item, form));
      return panel;
    }
    function field(id, labelKey, value, max, onInput, rows) {
      var input = rows ? h("textarea", { id: id, rows: String(rows), maxlength: String(max) }) : h("input", { id: id, type: "text", maxlength: String(max) });
      input.value = value || "";
      input.addEventListener("input", function () { onInput(input.value); });
      return h("div", { class: "bk-field" }, [h("label", { class: "bk-field__label", for: id, text: tr(labelKey) }), input]);
    }
    function reasonForm(item, form) {
      var hide = form.mode === "hide";
      var box = h("div", { class: "ri-reason" }, [field("ri-reason-" + item.id, hide ? "idea.hide_reason" : "idea.staff.reason_label", form.reason, 300,
        function (v) { form.reason = v; }, 2)]);
      if (!hide) box.appendChild(field("ri-improve-" + item.id, "idea.staff.improve_label", form.improve, 300, function (v) { form.improve = v; }, 2));
      box.appendChild(h("div", { class: "bk-actions" }, [
        button("bk-btn--danger", tr(hide ? "idea.hide_confirm" : "common.action.save"), hide ? "close" : "check", { onclick: function () {
          if (!form.reason.trim()) {
            toast(tr("idea.field_required"), { type: "error" });
            var el = doc.getElementById("ri-reason-" + item.id);
            if (el) el.focus();
            return;
          }
          var body = hide ? { action: "hide", reason: form.reason } : { action: "reject", reason: form.reason, can_improve: form.improve || null };
          if (!hide && item.status !== "review") body.check = form.check;
          decide(item, body, hide ? "idea.hidden_done" : "idea.rejected_done");
        } }),
        button("bk-btn--ghost", tr("common.action.cancel"), null, { onclick: function () {
          form.mode = null;
          if (isDecided(item)) state.open = null;  // у решённой идеи, кроме «Скрыть», делать нечего — карточка сворачивается
          render();
        } }),
      ]));
      setTimeout(function () { var el = doc.getElementById("ri-reason-" + item.id); if (el && !el.value) el.focus(); }, 0);
      return box;
    }
    // Название проекта — «вид + улица рядом» (как у демо-проектов): улицу даёт R12 /street-snap по точке идеи
    // (эскиз жителя R05 уже несёт near_street). Нет улицы рядом или R12 недоступен — просто вид объекта.
    function makeProject(item, form) {
      var body = { action: "project", kind: form.kind, check: form.check };
      var obj = item.object || {};
      if (obj.near_street) {
        decide(item, body, "idea.project_done");
        return;
      }
      var p = item.geometry && item.geometry.coordinates;
      request("GET", "/street-snap?lon=" + p[0] + "&lat=" + p[1]).then(function (s) {
        var st = streetOf(s);
        if (st) {
          body.near_street = st.ru;
          if (st.kk) body.near_street_kk = st.kk;
        }
      }, function () { /* без улицы */ }).then(function () { decide(item, body, "idea.project_done"); });
    }
    function decide(item, body, doneKey, keepOpen) {
      if (state.busy) return;
      state.busy = true;
      request("POST", "/ideas/" + encodeURIComponent(item.id) + "/decide", body).then(function (data) {
        state.busy = false;
        toast(tr(doneKey));
        if (keepOpen) {
          replace(data.item);
          state.form = null;
          render();
          return;
        }
        state.open = null;
        state.form = null;
        if (data.proposal) state.tab = "projects";
        load();
        if (data.proposal && build3d() && build3d().refresh) build3d().refresh();
      }, function (err) {
        state.busy = false;
        var fields = err.fields || {};
        toast(fields.kind ? tr("idea.project_kind") : fields.geometry ? tr("idea.lighting_note") : errorText(err), { type: "error" });
        if (err.code === "already_decided") load();
      });
    }

    // ── акимат: проекты (карточки R06 BirgeProposals: одобрить / отклонить, голоса числами) ──
    function renderProjects(body, list) {
      body.classList.add("ri-body--grid");
      if (!list.length) {
        stateBox(body, "empty", { title: tr("akim.proposals.empty"), icon: "trees" });
        return;
      }
      list.forEach(function (p) {
        var cell = h("div", { class: "ri-project" });
        body.appendChild(cell);
        // list: в списке из нескольких карточек «Одобрить» — не главная кнопка (одна главная на экран, CLEAN_PASS).
        if (root.BirgeProposals && root.BirgeProposals.renderProposal) root.BirgeProposals.renderProposal(cell, p, { role: "akimat", list: true });
        else cell.appendChild(h("p", { class: "bk-card", text: lang() === "kk" && p.title_kk ? p.title_kk : p.title_ru }));
      });
    }

    // ── мастер новой идеи: место → название и описание → объект (по желанию) ──
    function startWizard() {
      draft = { active: true, step: 1, point: null, street: null, title: "", text: "", kind: null };
      saveDraft();
      state.view = "new";
      state.step = 1;
      state.shownStep = null;
      render();
      var first = rootEl.querySelector("[data-key=pick]");
      if (first) first.focus();
    }
    function closeWizard() {
      draft = null;
      saveDraft();
      state.view = "list";
      render();
    }
    function renderWizard() {
      var step = state.step;
      // Шаг сменился — содержимое мягко въезжает (CSS ri-step-in); перерисовка того же шага (выбор объекта, ошибки) — без движения.
      var moved = state.shownStep !== step;
      state.shownStep = step;
      // Сверху мастера — «‹ Назад» и «Отменить» (тихие), полоса из трёх шагов; внизу — одна главная кнопка шага.
      var top = h("div", { class: "ri-wtop" }, [
        step > 1 ? button("bk-btn--ghost ri-wback", tr("common.action.back"), "back", { "data-key": "back", onclick: function () { go(step - 1); } }) : h("span"),
        button("bk-btn--ghost ri-cancel", tr("common.action.cancel"), "close", { "data-key": "cancel", onclick: closeWizard }),
      ]);
      var bar = h("div", { class: "ri-progress", "aria-hidden": "true" }, [1, 2, 3].map(function (i) { return h("i", { "data-on": String(i <= step) }); }));
      var box = h("section", { class: "bk-card ri-wizard", "data-step": String(step), "aria-labelledby": "ri-step" }, [top, bar,
        h("p", { class: "bk-meta ri-stepno", id: "ri-step", text: tr("complaint.step_of", { i: step, total: 3 }) })]);
      var content = h("div", { class: "ri-wbody" + (moved ? " ri-step-in" : "") });
      var primary = null;
      if (step === 1) {
        content.appendChild(h("h3", { class: "bk-h2", text: tr("idea.step.place") }));
        var street = draft.street && (lang() === "kk" ? draft.street.kk || draft.street.ru : draft.street.ru);
        if (draft.point) {
          content.appendChild(h("div", { class: "ri-place", role: "status" }, [
            h("span", { class: "ri-tile ri-tile--sm", "aria-hidden": "true" }, [icon("pin")]),
            h("span", { class: "ri-place__text", text: street ? tr("idea.place_chosen", { street: street }) : tr("idea.place_chosen_plain") }),
            button("bk-btn--ghost", tr("idea.place_change"), null, { "data-key": "pick", onclick: pick }),
          ]));
          primary = button("bk-btn--primary", tr("common.action.next"), "forward", { "data-key": "next", onclick: function () { go(2); } });
        } else {
          // Иллюстрация «булавка на карте» из линий ui-kit и одна строка, что делать.
          content.appendChild(h("div", { class: "ri-pickart", "aria-hidden": "true" }, [h("span", { class: "ri-pickart__pin" }, [icon("pin")])]));
          content.appendChild(h("p", { class: "ri-lead", text: tr("idea.place_hint") }));
          primary = button("bk-btn--primary", tr("idea.place_pick"), "pin", { "data-key": "pick", onclick: pick });
        }
      } else if (step === 2) {
        content.appendChild(h("h3", { class: "bk-h2", text: tr("idea.step.text") }));
        // Про личные данные — один раз, над полями (ошибка у самого поля — тем же текстом).
        content.appendChild(h("p", { class: "ri-privacy" }, [icon("shield"), h("span", { text: tr("idea.privacy") })]));
        content.appendChild(counted("ri-title", "idea.name", draft.title, TITLE_MAX, function (v) { draft.title = v; saveDraft(); }, 0, "idea.name_hint"));
        content.appendChild(counted("ri-text", "idea.description", draft.text, TEXT_MAX, function (v) { draft.text = v; saveDraft(); }, 4));
        // Ошибки полей (короткое название, телефон/почта/ИИН) — у самого поля, фокус на первом (как форма R09).
        primary = button("bk-btn--primary", tr("common.action.next"), "forward", { "data-key": "next", onclick: function () {
          var errs = {};
          if (draft.title.trim().length < 3) errs["ri-title"] = tr("idea.field_required");
          else if (hasPersonal(draft.title)) errs["ri-title"] = tr("idea.privacy");
          if (hasPersonal(draft.text)) errs["ri-text"] = tr("idea.privacy");
          if (showFieldErrors(errs)) return;
          go(3);
        } });
      } else {
        content.appendChild(h("h3", { class: "bk-h2", id: "ri-kind", text: tr("idea.object") }));
        var chips = h("div", { class: "bk-chips bk-chips--wrap", role: "radiogroup", "aria-labelledby": "ri-kind" });
        [null].concat(KINDS).forEach(function (k) {
          chips.appendChild(h("button", { type: "button", class: "bk-chip", role: "radio", "aria-checked": String(draft.kind === k),
            "data-key": "kind-" + (k || "none"), onclick: function () { draft.kind = k; saveDraft(); render(); } },
            [k ? icon(KIND_ICON[k]) : null, k ? tr("proposal.kind." + k) : tr("idea.object_none")]));
        });
        content.appendChild(chips);
        content.appendChild(h("div", { class: "ri-note" }, [icon("info"), h("div", {}, [
          h("p", { class: "ri-honest-line", text: tr("idea.honest") }),
          h("p", { class: "bk-meta", text: tr("idea.moderation") })])]));
        primary = button("bk-btn--primary", tr("idea.send"), "send", { "data-key": "send", onclick: send });
      }
      content.appendChild(h("div", { class: "bk-actions ri-wactions" }, [primary]));
      box.appendChild(content);
      rootEl.appendChild(box);
    }
    // Ошибки полей мастера: {id поля: текст}. Перерисовка с подсветкой; true — ошибки есть (фокус на первом поле).
    function showFieldErrors(errs) {
      state.fieldErrors = errs;
      var first = Object.keys(errs)[0];
      if (!first) return false;
      render();
      var el = doc.getElementById(first);
      if (el) el.focus();
      return true;
    }
    function counted(id, labelKey, value, max, onInput, rows, hintKey) {
      var left = h("span", { class: "bk-field__hint ri-left", "aria-live": "polite", text: tr("common.chars_left", { n: max - (value || "").length }) });
      var input = rows ? h("textarea", { id: id, rows: String(rows), maxlength: String(max), "data-key": id })
        : h("input", { id: id, type: "text", maxlength: String(max), "data-key": id, autocomplete: "off" });
      input.value = value || "";
      var errors = state.fieldErrors || {};
      var err = errors[id] ? h("p", { class: "bk-field__error", id: id + "-err", text: errors[id] }) : null;
      var field = h("div", { class: "bk-field" + (err ? " bk-field--error" : "") });
      input.addEventListener("input", function () {
        left.textContent = tr("common.chars_left", { n: max - input.value.length });
        onInput(input.value);
        if (errors[id]) {  // поле исправляют — ошибка уходит сразу, без перерисовки
          delete errors[id];
          field.classList.remove("bk-field--error");
          input.removeAttribute("aria-invalid");
          input.setAttribute("aria-describedby", hintKey ? id + "-hint" : "");
          if (err) err.remove();
        }
      });
      var hint = hintKey ? h("p", { class: "bk-field__hint", id: id + "-hint", text: tr(hintKey) }) : null;
      var described = [hint ? id + "-hint" : null, err ? id + "-err" : null].filter(Boolean).join(" ");
      if (described) input.setAttribute("aria-describedby", described);
      if (err) input.setAttribute("aria-invalid", "true");
      [h("label", { class: "bk-field__label", for: id, text: tr(labelKey) }), hint, input, err, left].forEach(function (c) {
        if (c) field.appendChild(c);
      });
      return field;
    }
    function go(step) {
      state.fieldErrors = {};
      state.step = draft.step = step;
      saveDraft();
      render();
      var focus = rootEl.querySelector(step === 2 ? "#ri-title" : step === 3 ? "[data-key=kind-none]" : "[data-key=pick]");
      if (focus) focus.focus();
    }
    function pick() {
      draft.step = 1;
      saveDraft();
      startPick(function (point) {
        if (point) {
          draft.point = point;
          draft.street = null;
          saveDraft();
          // Улица рядом (R12 /street-snap) — только подпись «Место выбрано: …»; без неё мастер работает так же.
          request("GET", "/street-snap?lon=" + point[0] + "&lat=" + point[1]).then(function (s) {
            var st = streetOf(s);
            if (draft && st) {
              draft.street = st;
              saveDraft();
              if (current) current.render();
            }
          }, function () { /* нет улицы рядом — без подписи */ });
        }
        if (shell()) shell().setSection(opts.section || "ideas");
      });
    }
    function send() {
      if (state.busy) return;
      if (!draft.point) {
        toast(tr("idea.place_needed"), { type: "error" });
        go(1);
        return;
      }
      state.busy = true;
      var btn = rootEl.querySelector("[data-key=send]");
      if (btn) btn.setAttribute("aria-busy", "true");
      var body = { title: draft.title.trim(), description: draft.text.trim() || null,
        geometry: { type: "Point", coordinates: draft.point }, device_id: deviceId(), lang: lang() === "kk" ? "kk" : "ru" };
      if (draft.kind) body.object = { kind: draft.kind };
      request("POST", "/ideas", body).then(function (data) {
        state.busy = false;
        draft = null;
        saveDraft();
        state.sent = data.item;
        state.view = "sent";
        render();
        var back = rootEl.querySelector("[data-key=back-list]");
        if (back) back.focus();
      }, function (err) {
        state.busy = false;
        if (btn) btn.removeAttribute("aria-busy");
        var fields = err.fields || {};
        if (fields.title || fields.description) {
          // R15-S31: телефон, почта или ИИН (или короткое название) — вернуть на шаг 2 с ошибкой у поля, не «нет связи».
          var personal = function (m) { return /ИИН|e-mail|телефон/i.test(String(m || "")); };
          var errs = {};
          if (fields.title) errs["ri-title"] = personal(fields.title) ? tr("idea.privacy") : tr("idea.field_required");
          if (fields.description) errs["ri-text"] = personal(fields.description) ? tr("idea.privacy") : tr("idea.field_required");
          state.step = draft.step = 2;
          saveDraft();
          showFieldErrors(errs);
          return;
        }
        if (fields.geometry) go(1);
        var retry = err.status === 0 || err.status >= 500;
        toast(fields.geometry ? tr("idea.place_needed") : err.status === 429 ? tr("idea.limit_new") : errorText(err),
          retry ? { type: "error", action: { label: tr("common.action.retry"), onClick: send } } : { type: "error" });
      });
    }
    // Галочка, которая «рисуется» (обводка круга, затем галочка; без движения при reduced-motion) — статичная разметка.
    var SENT_MARK = '<svg viewBox="0 0 56 56" aria-hidden="true" focusable="false"><circle cx="28" cy="28" r="25"/><path d="M17 29.5l7.5 7.5L40 21"/></svg>';
    function renderSent() {
      var mark = h("span", { class: "ri-sent__mark", "aria-hidden": "true" });
      mark.innerHTML = SENT_MARK;
      rootEl.appendChild(h("section", { class: "bk-card ri-sent", role: "status" }, [
        mark,
        h("h3", { class: "bk-h2" }, [h("span", { text: tr("idea.sent_title") })]),
        h("p", { text: tr("idea.moderation") }),
        h("p", { class: "bk-meta", text: tr("idea.sent_next") }),
        // После отправки — «Карта» и «Идеи», обе второстепенные (R11 SCHEMES §2.2): главной кнопки на экране нет.
        h("div", { class: "bk-actions" }, [
          button("", tr("common.nav.map"), "pin", { "data-key": "to-map", onclick: function () {
            state.view = "list";
            if (typeof opts.close === "function") opts.close();
            else if (shell()) shell().setSection("map");
          } }),
          button("", tr("common.nav.ideas"), "list", { "data-key": "back-list", onclick: function () {
            state.view = "list";
            state.tab = "voting";
            state.flash = state.sent && state.sent.id;
            load();
          } })]),
      ]));
    }

    var current = { render: render, focus: function (id) { state.flash = id; focusIdea(id); render(); } };
    mounted = current;
    var offLang = I() && I().onChange ? I().onChange(function () { render(); }) : null;
    if (I() && I().ready) I().ready.then(load, load);
    else load();
    return {
      setLang: function () { render(); },
      destroy: function () {
        alive = false;
        if (live.parentNode) live.parentNode.removeChild(live);
        if (mounted === current) mounted = null;
        if (typeof offLang === "function") offLang();
        rootEl.classList.remove("ri");
        rootEl.replaceChildren();
      },
    };
  }

  var mounted = null;     // открытый экран (для нажатия на метку идеи на карте)
  var pendingFocus = null; // id идеи, которую открыть, когда экран смонтируется

  // Идея в формате R05 (метка «Идея · 47», 3D-модель, если житель выбрал объект каталога).
  function r05Idea(item) {
    var t = textOf(item, "title");
    return { id: item.id, title: t.text, geometry: item.geometry, object: item.object, votes: item.votes, status: item.status, demo: item.demo };
  }

  // ── слой карты «Идеи жителей» (по умолчанию выключен; данные грузятся только при включении) ──
  // Слой регистрируется, только когда 3D-модуль R05 умеет рисовать идеи (setIdeas, R05 ≥ 395d9ea): пустого пункта
  // «Идеи жителей» в «Слой на карте» быть не должно. Модуль R05 монтируется после карты — ждём его до 30 с.
  var layerTries = 0;
  function registerLayer() {
    var S = shell();
    if (registerLayer.done || registerLayer.waiting) return;
    var b = build3d();
    if (!S || !S.registerLayer || !b || typeof b.setIdeas !== "function") {
      if (layerTries++ < 30) {
        registerLayer.waiting = true;
        setTimeout(function () { registerLayer.waiting = false; registerLayer(); }, 1000);
      }
      return;
    }
    registerLayer.done = true;
    var request = makeRequest({ api: S.api || null });
    var ticket = 0;
    S.registerLayer({
      id: "ideas", titleKey: "shell.layers.ideas", modes: ["resident", "akimat"],
      show: function () {
        var my = ++ticket;
        request("GET", "/ideas?status=voting,project").then(function (data) {
          if (my === ticket && build3d()) build3d().setIdeas((data.items || []).map(r05Idea));
        }, function () { /* нет связи — слой пустой */ });
      },
      hide: function () {
        ticket++;
        var b = build3d();
        if (b && b.setIdeas) b.setIdeas(null);
      },
    });
  }
  // Нажатие на метку идеи (R05: событие civic-build3d:idea) — открыть её карточку в разделе.
  doc.addEventListener("civic-build3d:idea", function (e) {
    var id = e.detail && e.detail.id;
    var S = shell();
    if (!id || !S) return;
    var section = S.mode === "akimat" ? "projects" : "ideas";
    if (mounted && S.section === section) {
      mounted.focus(id);
      return;
    }
    pendingFocus = id;
    S.setSection(section);
  });
  if (doc.readyState === "complete") registerLayer();
  else root.addEventListener("load", registerLayer);

  // Карточка проекта R06 сама пишет «По идее жителей · N голосов» (proposals.js) — R05 свою строку не добавляет.
  root.BirgeIdeas = { mount: mount, version: "ideas-r14-w2", KEYS: KEYS, cancelPick: function () { if (picker) picker.finish(false); } };
})(typeof self !== "undefined" ? self : this);
