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
  var KIND_ICON = { square: "trees", playground: "playground", sports: "ball", stop: "bus", lighting: "bulb",
    benches: "bench", greening: "sprout", other: "pin" };   // + темы идей раунда 15 (значки R11 i-bench, i-sprout)
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
  var STATUS_LOOK = { review: "new", voting: "accepted", checking: "in_progress", project: "fixed", rejected: "rejected", hidden: "rejected" };

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
      "idea.topic.benches": "Скамейки",
      "idea.topic.greening": "Озеленение",
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
      // Раунд 15, задача 1: просмотр без входа (вид «Акимат») — I18N_R15_R06.json для R11
      "idea.public.staff_hint": "Проверять и публиковать идеи может сотрудник акимата после входа.",
      "idea.public.vote_residents": "Голосуют жители — в виде «Житель». Решение принимает акимат.",
      "idea.together.line": "Сделайте вместе — поддержим инвентарём",
      "idea.together.open": "Открыть дело",
      "idea.together.make": "Сделать инициативой",
      "idea.together.hint": "Жители могут сделать это сами — акимат поддержит инвентарём и вывозом.",
      "idea.together.can": "Если жители могут сделать это сами — сделайте инициативой, акимат поддержит инвентарём.",
      "idea.together.done": "Инициатива создана — её видно в «Сделаем вместе»",
      "idea.together.error": "Не получилось создать инициативу. Повторите позже.",
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
      "staff.login.note": "Учётную запись выдаёт администратор.",
      // Эталон 13 окт (REFERENCE.html, вариант A): тексты листа «Проекты и идеи» — переданы R11 (INTEGRATION.txt R06, раздел «Эталон»).
      "idea.tab.akimat_projects": "Проекты акимата", "idea.sub": "Идея жителей", "idea.sub_project": "Проект акимата",
      "idea.pill.review": "На проверке", "idea.pill.voting": "Сбор голосов", "idea.pill.checking": "Акимат проверяет",
      "idea.pill.project": "Принято в проект", "idea.pill.rejected": "Отклонена", "idea.pill.hidden": "Не опубликована",
      "idea.fact.supported": "поддержали", "idea.fact.year": "срок", "idea.fact.district": "район", "idea.fact.object": "объект", "idea.fact.against": "против", "idea.on_map": "На карте",
    },
    kk: {
      "idea.status.review": "Тексеруде",
      "idea.status.hidden": "Жарияланбады",
      "idea.hidden_note": "Идея тексеруден өтпеді: онда жеке деректер, дөрекі сөздер немесе жарнама бар.",
      "idea.mine": "Сіздің идеяңыз",
      "idea.kind_none": "Идея",
      "idea.topic.benches": "Орындықтар",
      "idea.topic.greening": "Көгалдандыру",
      "idea.place": "Бұл қай жерге керек?",
      "idea.place_pick": "Картадан орын таңдау",
      "idea.place_change": "Орынды өзгерту",
      "idea.place_hint": "Картадан идея керек орынды таңдап, «Дайын» түймесін басыңыз",
      "idea.place_chosen": "Орын таңдалды: {street}",
      "idea.place_chosen_plain": "Орын таңдалды",
      "idea.place_refine": "Дәлірек таңдауға немесе «Дайын» түймесін басуға болады",
      "idea.place_needed": "Алдымен картадан орын таңдаңыз",
      "idea.map_unavailable": "Карта қазір қолжетімсіз. Бетті жаңартыңыз.",
      "idea.sent_next": "Әзірге оны тек сіз көресіз — «Идеялар» тізімінде «Тексеруде» белгісімен.",
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
      "idea.check_close": "Жию",
      "idea.hide": "Жасыру: жеке деректер немесе дөрекі сөздер",
      "idea.hide_reason": "Неге жасыру керек (тек қызметкерлер көреді)",
      "idea.hide_confirm": "Идеяны жасыру",
      "idea.project_kind": "Қандай нысан қою керек",
      "idea.lighting_note": "Жарық көше бойымен қойылады: оны картадағы «Не салайық?» каталогынан қосыңыз.",
      "idea.project_done": "Жоба құрылды — ол картадағы «Жобалар» қабатында және «Жобалар» қойындысында",
      "idea.published": "Идея дауыс беруге жарияланды",
      "idea.rejected_done": "Идеядан бас тартылды, себебін тұрғындар көреді",
      "idea.hidden_done": "Идея жасырылды",
      "idea.checked": "Тексеру тізімі сақталды",
      "idea.check_save": "Тексеру тізімін сақтау",
      "idea.project_link": "Жоба: {title}",
      "idea.field_required": "Бұл өрісті толтырыңыз",
      "idea.empty.title": "Әзірге идея жоқ",
      "idea.public.staff_hint": "Идеяларды әкімдік қызметкері кіргеннен кейін тексеріп, жариялай алады.",
      "idea.public.vote_residents": "Тұрғындар дауыс береді — «Тұрғын» көрінісінде. Шешімді әкімдік қабылдайды.",
      "idea.together.line": "Бірге жасаңыз — құрал-жабдықпен қолдаймыз",
      "idea.together.open": "Істі ашу",
      "idea.together.make": "Бастамаға айналдыру",
      "idea.together.hint": "Тұрғындар мұны өздері жасай алады — әкімдік құрал-жабдықпен және қоқыс шығарумен қолдайды.",
      "idea.together.can": "Тұрғындар өздері жасай алса — бастамаға айналдырыңыз, әкімдік құрал-жабдықпен қолдайды.",
      "idea.together.done": "Бастама құрылды — ол «Бірге жасайық» бөлімінде көрінеді",
      "idea.together.error": "Бастаманы құру мүмкін болмады. Кейінірек қайталаңыз.",
      "idea.empty.text": "Біріншісін ұсыныңыз — көршілеріңіз қолдай алады.",
      "idea.empty.project": "Әзірге бірде-бір идея жобаға айналмады",
      "idea.empty.rejected": "Қабылданбаған идея жоқ",
      "idea.check.hint.land": "Жер учаскесі бос, оны пайдалануға болады",
      "idea.check.hint.networks": "Жер астындағы құбыр мен кабель кедергі емес",
      "idea.check.hint.access": "Жетуге болады, оның ішінде балалар арбасымен",
      "idea.check.hint.maintenance": "Тазалайтын және жөндейтін жауапты бар",
      "idea.check.progress": "«Иә»: {n}/4",
      "idea.check.ready": "Төртеуі де «иә»: жобаға айналдыруға болады",
      "idea.hide_short": "Жасыру",
      "staff.login.note": "Тіркелгіні әкімші береді.",
      "idea.tab.akimat_projects": "Әкімдік жобалары", "idea.sub": "Тұрғындар идеясы", "idea.sub_project": "Әкімдік жобасы",
      "idea.pill.review": "Тексерілуде", "idea.pill.voting": "Дауыс жинау", "idea.pill.checking": "Әкімдік тексеруде",
      "idea.pill.project": "Жобаға қабылданды", "idea.pill.rejected": "Қабылданбады", "idea.pill.hidden": "Жарияланбады",
      "idea.fact.supported": "қолдады", "idea.fact.year": "мерзімі", "idea.fact.district": "аудан", "idea.fact.object": "нысан", "idea.fact.against": "қарсы", "idea.on_map": "Картада",
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
  function hasIllustrations() {
    return !!(root.BirgeUI && typeof root.BirgeUI.illustration === "function");
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
    var staffPath = function (path) { return /^\/(staff\/|works(\/|\?|$))/.test(path) || /^\/ideas\/[^/]+\/(decide|to-initiative)$/.test(path); };
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

  // ── П1 (поправка владельца 15 окт, «Без ИИ-слопа»): у идеи и проекта — маленький монохромный значок вида объекта
  // (набор R11, одна толщина линии) на спокойной плитке 48 px вместо серой лампочки, сцен и 3D-рендеров. Сам объект в 3D
  // виден на карте (слои «Проекты» и «Идеи жителей»), больших картинок в списке и карточке нет.
  // Значков i-bench и i-sprout нет в ui-kit FINAL-4: пока спрайт без них — тот же рисунок R11 встроенным SVG.
  var INLINE_ICON = {
    bench: '<path d="M4 8.5h16M4 13h16"/><path d="M6 13v6.5M18 13v6.5M7 8.5V13M17 8.5V13"/>',
    sprout: '<path d="M12 20.5v-8"/><path d="M12 13C12 9 9.2 6.5 4.5 6.5c0 4 2.8 6.5 7.5 6.5Z"/><path d="M12 10.5c0-3.6 2.6-6 7.5-6 0 3.6-2.6 6-7.5 6Z"/>',
  };
  var spriteIds = null;
  (function loadSpriteIds() {
    var sprite = root.BirgeUI && root.BirgeUI.SPRITE;
    if (!sprite || !root.fetch) return;
    root.fetch(sprite, { credentials: "same-origin" }).then(function (r) { return r.ok ? r.text() : ""; }).then(function (text) {
      var ids = {};
      String(text || "").replace(/id="(i-[a-z0-9-]+)"/g, function (_, id) { ids[id] = true; return _; });
      spriteIds = ids;
    }, function () { /* без спрайта — значки запасные */ });
  })();
  function kindIcon(kind) {
    var name = KIND_ICON[kind] || KIND_ICON.other;
    if (INLINE_ICON[name] && !(spriteIds && spriteIds["i-" + name])) {
      var box = doc.createElement("span");
      box.innerHTML = '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + INLINE_ICON[name] + "</svg>";
      return box.firstChild;
    }
    return icon(name);
  }
  function kindTile(kind) {
    return h("span", { class: "ri-tile ri-kind", "data-kind": KIND_ICON[kind] ? kind : "other", "aria-hidden": "true" },
      [kindIcon(kind)]);
  }
  // Сердце «Поддержать» — как в эталоне (одна толщина линии с иконками ui-kit); заполненное — поддержано.
  var HEART = '<svg class="ri-heart" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z"/></svg>';
  function svgEl(markup, cls) {
    var span = doc.createElement("span");
    span.className = cls;
    span.setAttribute("aria-hidden", "true");
    span.innerHTML = markup;
    return span;
  }

  // ===================================================================================== экран
  function mount(rootEl, options) {
    var opts = Object.assign({ titleTag: "h2" }, options || {});
    // akimat — интерфейс сотрудника (очередь проверки, решения). Раунд 15, задача 1: без входа акимат видит те же
    // проекты и идеи, что житель, — только просмотр (readOnly: без голосов и решений), и тихую кнопку «Войти».
    var akimat = opts.section === "projects" || opts.role === "akimat";
    var readOnly = false;
    var request = makeRequest(opts);
    var state = {
      tab: "ideas", sel: null, selClosed: false, mode: null, more: false,
      items: null, counts: {}, projects: null, error: null, view: "list", busy: false,
      flash: pendingFocus, step: 1, sent: null,
    };
    // pendingFocus гасится, когда идея найдена в загруженном списке (load): оболочка может пересоздать экран до ответа.
    var alive = true;
    rootEl.classList.add("ri");
    // Адрес «#ideas/<id>» или «#projects/<id>» (ссылка из ленты) — открыть эту идею или проект. Оболочка раунда 15
    // передаёт путь в opts.path (и потом в handle.setPath), FINAL-4 — нет: тогда читаем адрес сами.
    var deep = ITEM_ID.test(opts.path || "") ? [null, opts.path]
      : /^#(?:ideas|projects)\/([A-Za-z0-9._:-]{1,64})$/.exec(root.location ? root.location.hash : "");
    if (deep && !pendingFocus) pendingFocus = deep[1];
    if (pendingFocus) state.flash = pendingFocus;
    if (!akimat && loadDraft() && draft.active) state.view = "new";
    if (state.view === "new") state.step = draft.step || 1;

    // ── загрузка ──
    function load() {
      state.error = null;
      // Акимат: на проверке и голосовании — сверху; решённые (отклонена, стала проектом) — свёрнуто внизу: их можно скрыть
      // (R15-S30: личные данные заметили позже, просьба автора).
      var q = akimat ? request("GET", "/staff/ideas?status=review,voting,checking,rejected,project")
        : request("GET", "/ideas?device_id=" + encodeURIComponent(deviceId()));
      var p = request("GET", "/proposals?device_id=" + encodeURIComponent(deviceId()));
      state.items = null;
      render();
      return Promise.all([q, p.catch(function () { return null; })]).then(function (res) {
        if (!alive) return;
        state.items = (res[0] && res[0].items) || [];
        state.counts = (res[0] && res[0].counts) || {};
        state.caps = (res[0] && res[0].capabilities) || {};   // раунд 15: to_initiative — есть ли R16 в сборке
        state.appear = true;
        state.projects = res[1] ? res[1].items || [] : [];
        if (state.flash) {
          focusIdea(state.flash);
          if (pendingFocus === state.flash) pendingFocus = null;
        }
        render();
      }, function (err) {
        if (!alive) return;
        if (akimat && (err.status === 401 || err.status === 403)) {
          akimat = false;   // сессии нет — открытый список жителя, только просмотр
          readOnly = true;
          load();
          return;
        }
        state.error = err;
        render();
      });
    }
    function staffLogin() {
      if (root.BirgeShell) root.BirgeShell.setSection("map");
      if (root.CivicShell && root.CivicShell.openEditor) root.CivicShell.openEditor();
    }
    // Нажатие на метку идеи на карте (или «Идея отправлена» → список): идея выбрана, её карточка открыта.
    function focusIdea(id) {
      var item = (state.items || []).filter(function (x) { return x.id === id; })[0];
      // Раунд 15: ссылка из ленты уведомлений может вести и на проект («Проект, за который вы голосовали, одобрен»).
      var project = !item && (state.projects || []).filter(function (x) { return x.id === id; })[0];
      if (!item && !project) return;
      state.tab = item ? "ideas" : "projects";
      state.sel = id;
      state.selClosed = false;
      state.mode = null;
      state.form = null;
    }
    function replace(item) {
      state.items = (state.items || []).map(function (x) { return x.id === item.id ? item : x; });
    }

    // ── отрисовка ──
    function render() {
      if (!alive) return;
      var focusKey = doc.activeElement && (rootEl.contains(doc.activeElement) || (detailHost && detailHost.contains(doc.activeElement)))
        ? doc.activeElement.getAttribute("data-key") : null;
      rootEl.replaceChildren();
      if (state.view === "new") {
        rootEl.appendChild(sheetHead());
        renderWizard();
        removeDetail();
      } else if (state.view === "sent") {
        rootEl.appendChild(sheetHead());
        renderSent();
        removeDetail();
      } else renderSheet();
      if (focusKey) {
        var again = rootEl.querySelector('[data-key="' + focusKey + '"]') || (detailHost && detailHost.querySelector('[data-key="' + focusKey + '"]'));
        if (again) again.focus();
      }
      // Подсветка идеи с метки на карте — когда список уже загружен (иначе её применит load).
      if (state.flash && state.items) {
        var card = rootEl.querySelector('[data-idea="' + state.flash + '"]');
        if (card) {
          card.classList.add("ri-card--flash");
          card.scrollIntoView({ block: "nearest" });
        }
        state.flash = null;
      }
    }

    // ===================== эталон (REFERENCE.html, вариант A): лист «Проекты и идеи» + карточка выбранного =====================
    // Лист: заголовок и ×, сегмент «Идеи жителей · N | Проекты акимата · M», карточки как в App Store (картинка 84, название,
    // одна строка, статус-плашка и капсула ♥ с числом — «Поддержать» прямо в списке). Выбранная карточка — в рамке 2 px,
    // справа от листа — её карточка (картинка, 3 цифры, одно предложение, главная и вторая кнопки, «это опрос, решает акимат»).
    // Ноутбук: карточка — отдельная стеклянная панель справа (вне листа оболочки); телефон — раскрывается под строкой списка.
    var wide = function () { return !root.matchMedia || root.matchMedia("(min-width: 761px)").matches; };
    // Карточка выбранного справа (эталон) — только когда лист узкий (412 слева, патч R01). Лист шире 440 (телефон или
    // прежний широкий лист раздела по центру) — карточка раскрывается под строкой списка, ничего не перекрывая (R11 §21.4).
    var sideCard = function () {
      if (!wide()) return false;
      var w = rootEl.getBoundingClientRect().width;
      return w > 0 && w <= 440;
    };
    var detailHost = null;
    var ORDER = { review: 0, hidden: 0, voting: 1, checking: 2, project: 3, rejected: 4 };

    function sheetHead() {
      var close = h("button", { type: "button", class: "bk-x ri-x", "data-key": "close", "aria-label": tr("common.action.close"), title: tr("common.action.close"),
        onclick: function () {
          if (state.view !== "list") { closeWizard(); return; }
          if (typeof opts.close === "function") opts.close();
          else if (shell()) shell().setSection("map");
        } }, [icon("close")]);
      return h("div", { class: "bk-psheet__hd ri-sheet-hd" }, [h(opts.titleTag, { class: "ri-sheet-title", text: tr("common.nav.projects") }), close]);
    }
    function ideasShown() {
      var list = (state.items || []).filter(function (x) { return akimat || x.status !== "hidden" || x.mine; });
      // свои на проверке — сверху; дальше по ходу решения (стабильная сортировка сохраняет порядок сервера внутри групп)
      return list.slice().sort(function (a, b) {
        return (b.mine ? 1 : 0) - (a.mine ? 1 : 0) || (ORDER[a.status] || 0) - (ORDER[b.status] || 0);
      });
    }
    function listOf(tab) {
      return tab === "projects" ? state.projects || [] : ideasShown();
    }
    function selected() {
      if (state.selClosed) return null;
      var list = listOf(state.tab);
      var s = state.sel && list.filter(function (x) { return x.id === state.sel; })[0];
      if (s) return s;
      if (!sideCard() && !state.sel) return null;  // телефон и широкий лист: ничего не раскрыто, пока не нажали
      var first = list.filter(function (x) { return !(akimat && isDecided(x)); })[0] || list[0] || null;
      state.sel = first ? first.id : null;
      return first;
    }
    function segControl() {
      var nIdeas = akimat ? ideasShown().filter(function (x) { return !isDecided(x); }).length : ideasShown().length;
      var row = h("div", { class: "ri-seg", role: "tablist", "aria-label": tr("common.nav.projects") });
      // Телефон: короткие подписи «Идеи · N | Проекты · M» — длинные казахские не переносятся в узком сегменте.
      var full = wide();
      [["ideas", tr(full ? "idea.title" : "common.nav.ideas") + " · " + nIdeas],
        ["projects", tr(full ? "idea.tab.akimat_projects" : "idea.tab.projects") + " · " + (state.projects || []).length]].forEach(function (t) {
        var on = state.tab === t[0];
        row.appendChild(h("button", { type: "button", role: "tab", value: t[0], "aria-selected": String(on), tabindex: on ? "0" : "-1",
          "data-key": "tab-" + t[0], onclick: function () { chooseTab(t[0]); } }, [t[1]]));
      });
      row.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        e.preventDefault();
        chooseTab(state.tab === "ideas" ? "projects" : "ideas");
        var b = rootEl.querySelector('[data-key="tab-' + state.tab + '"]');
        if (b) b.focus();
      });
      return row;
    }
    function chooseTab(id) {
      if (id === state.tab) return;
      state.tab = id;
      state.sel = null;
      state.selClosed = false;
      state.mode = null;
      state.form = null;
      state.more = false;
      state.appear = true;
      render();
    }
    function renderSheet() {
      rootEl.appendChild(sheetHead());
      var body = h("div", { class: "bk-plist ri-plist" });
      if (state.error) {
        removeDetail();
        if (akimat && (state.error.status === 401 || state.error.status === 403)) {
          // Одно состояние «войдите» на все разделы (R11 INTEGRATION §9.3 b, §9.5 a): рисунок «пропуск» ui-kit, подсказка, «Войти».
          stateBox(body, "empty", { title: tr("proposal.need_staff"), text: tr("staff.login.note"), illustration: "staff",
            icon: hasIllustrations() ? null : "user", action: { label: tr("staff.login.submit"),
            onClick: function () { if (root.BirgeShell) root.BirgeShell.setSection("map"); if (root.CivicShell && root.CivicShell.openEditor) root.CivicShell.openEditor(); } } });
        } else {
          stateBox(body, "error", { action: { onClick: load } });
        }
        rootEl.appendChild(body);
        return;
      }
      if (!state.items) {
        removeDetail();
        skeleton(body);
        rootEl.appendChild(body);
        return;
      }
      rootEl.appendChild(segControl());
      var sel = selected();
      var list = listOf(state.tab);
      if (state.tab === "projects") {
        if (!list.length) emptyBox(body, tr("akim.proposals.empty"), null, ["square", "sports"], "list");
        list.forEach(function (p) { body.appendChild(projectCard(p, sel)); });
      } else {
        var open = akimat ? list.filter(function (x) { return !isDecided(x); }) : list;
        if (!list.length) emptyBox(body, tr(akimat ? "idea.empty.review" : "idea.empty.title"), akimat || readOnly ? null : tr("idea.empty.text"), null, akimat ? "done" : "idea");
        else if (!open.length) emptyBox(body, tr("idea.empty.review"), null, ["check"], "done");
        open.forEach(function (x) { body.appendChild(ideaCard(x, sel)); });
        var decided = akimat ? list.filter(isDecided) : [];
        if (decided.length) {
          // Решённые — свёрнуто внизу (R15-S30: их можно скрыть).
          var box = h("details", { class: "bk-details ri-decided" }, [h("summary", { text: tr("idea.decided") + " · " + decided.length })]);
          if (state.decidedOpen || decided.some(function (x) { return sel && x.id === sel.id; })) box.open = true;
          box.addEventListener("toggle", function () { state.decidedOpen = box.open; });
          decided.forEach(function (x) { box.appendChild(ideaCard(x, sel)); });
          body.appendChild(box);
        }
      }
      if (state.appear) {
        body.classList.add("ri-body--in");
        Array.prototype.forEach.call(body.children, function (el, i) { el.style.setProperty("--ri-i", String(Math.min(i, 8))); });
        state.appear = false;
      }
      var demo = body.querySelector("[data-demo]");
      // Телефон: правило «это опрос, решает акимат» — одной строкой над карточками, видно сразу (R11 SCHEMES §4 п. 3);
      // на ноутбуке оно в карточке выбранного (эталон .pd).
      if (!sideCard()) body.insertBefore(h("p", { class: "bk-footnote ri-honest-note", text: tr("idea.honest") }), body.firstChild);
      if (demo) body.appendChild(h("p", { class: "bk-footnote ri-demo-note", text: tr("common.tag.demo_hint") }));
      rootEl.appendChild(body);
      if (!akimat && !readOnly) {
        rootEl.appendChild(h("div", { class: "ri-sheet-ft" }, [
          h("button", { type: "button", class: "bk-btn ri-newbtn", "data-key": "new", onclick: startWizard }, [
            h("span", { class: "ri-newbtn__ic", "aria-hidden": "true" }, [icon("plus")]), h("span", { text: tr("idea.new") })])]));
      } else if (readOnly) {
        // Просмотр без входа: подсказка одной строкой и тихая «Войти» (главного действия здесь нет — это витрина).
        rootEl.appendChild(h("div", { class: "ri-sheet-ft ri-sheet-ft--public" }, [
          h("p", { class: "bk-footnote ri-public-note", text: tr("idea.public.staff_hint") }),
          button("bk-btn--ghost ri-loginbtn", tr("staff.login.submit"), "user", { "data-key": "login", onclick: staffLogin })]));
      }
      placeDetail(sel);
      // Выбор сменился (нажатие, ↑↓, первая карточка после загрузки или смены вкладки) — карта плавно ведёт к объекту.
      if (sel && state.mapFor !== sel.id) {
        state.mapFor = sel.id;
        moveMap(sel, 0);
      }
    }

    // ── строка списка (карточка «как в App Store») ──
    function pill(text, tone) {
      return h("span", { class: "bk-pill ri-pill" + (PILL_KIT[tone] ? " " + PILL_KIT[tone] : ""), "data-tone": tone, text: text });
    }
    var PILL_KIT = { warn: "bk-pill--review", ok: "bk-pill--accepted" };
    var IDEA_TONE = { review: "warn", checking: "warn", voting: "neutral", project: "ok", rejected: "muted", hidden: "muted" };
    var PROJ_TONE = { proposal: "neutral", approved: "ok", rejected: "muted" };
    function districtShort(d) {
      return d ? tr("district." + d) : null;
    }
    function joinDot(parts) {
      return parts.filter(Boolean).join(" · ");
    }
    function voteCapsule(n, opts2) {
      var kids = [svgEl(HEART, "ri-heart-ic"), h("span", { class: "ri-vote__n bk-num" + (opts2.roll ? " ri-roll-" + opts2.roll : ""), text: I() ? I().formatNumber(n) : String(n) })];
      if (!opts2.onclick) {
        return h("span", { class: "bk-vote ri-vote ri-vote--static", role: "img", "aria-label": tr("idea.votes", { n: n }) }, kids);
      }
      return h("button", { type: "button", class: "bk-vote ri-vote" + (opts2.pop ? " ri-pop" : ""), "aria-pressed": String(!!opts2.pressed), "aria-label": opts2.label,
        title: opts2.label, "data-key": opts2.key, onclick: opts2.onclick }, kids);
    }
    function rowCard(id, attrs, kind, titleText, titleLang, sub, pillEl, capsule, sel, topic) {
      var on = !!(sel && sel.id === id);
      var card = h("article", Object.assign({ class: "bk-pc ri-pc", "aria-current": on ? "true" : null, "aria-labelledby": "ri-t-" + id }, attrs), [
        kindTile(topic || kind),
        h("div", { class: "bk-pc__body ri-pc__t" }, [
          h("h3", { class: "bk-pc__title ri-pc__title", id: "ri-t-" + id, lang: titleLang }, [
            h("button", { type: "button", class: "ri-pc__open", "data-key": "sel-" + id, "aria-expanded": String(on), onclick: function () { select(id); } }, [titleText])]),
          h("p", { class: "bk-pc__sub ri-pc__sub", text: sub }),
          h("div", { class: "bk-pc__foot ri-pc__f" }, [pillEl, capsule]),
        ]),
      ]);
      return card;
    }
    function ideaCard(item, sel) {
      var t = textOf(item, "title");
      var kind = item.object && item.object.kind;
      var capsule = null;
      var bump = state.bump && state.bump.id === item.id ? state.bump.dir : 0;
      if (!akimat && !readOnly && item.status === "voting") {
        capsule = voteCapsule(item.votes || 0, { pressed: item.my_support, label: tr(item.my_support ? "idea.supported" : "idea.support"), key: "support-" + item.id,
          roll: bump > 0 ? "up" : bump < 0 ? "down" : "", pop: !!bump, onclick: function () { support(item, !item.my_support); } });
      } else if (item.status !== "review" && item.status !== "hidden") {
        capsule = voteCapsule(item.votes || 0, {});
      }
      var sub = joinDot([item.mine ? tr("idea.mine") : tr("idea.sub"), districtShort(item.district)]);
      return rowCard(item.id, { "data-idea": item.id, "data-idea-status": item.status, "data-demo": item.demo ? "" : null,
        "data-topic": item.topic || null }, kind, t.text, t.lang, sub,
        pill(tr("idea.pill." + item.status), IDEA_TONE[item.status] || "neutral"), capsule, sel, item.topic);
    }
    function projTitle(p) {
      return lang() === "kk" && p.title_kk ? { text: p.title_kk, lang: "kk" } : { text: p.title_ru, lang: "ru" };
    }
    function projectCard(p, sel) {
      var t = projTitle(p);
      var bump = state.bump && state.bump.id === p.id ? state.bump.dir : 0;
      var capsule = !akimat && !readOnly && p.voting_open && p.status === "proposal"
        ? voteCapsule(p.votes_up || 0, { pressed: p.my_vote === 1, label: tr("proposal.vote_up"), key: "vote-" + p.id, roll: bump > 0 ? "up" : bump < 0 ? "down" : "",
          pop: !!bump, onclick: function () { voteProject(p, 1); } })
        : voteCapsule(p.votes_up || 0, {});
      var sub = p.idea ? tr("idea.by_residents", { n: p.idea.votes || 0 }) : joinDot([tr("idea.sub_project"), districtShort(p.district)]);
      return rowCard(p.id, { "data-proposal": p.id, "data-demo": p.demo ? "" : null }, p.kind, t.text, t.lang, sub,
        pill(tr("proposal.status." + p.status), PROJ_TONE[p.status] || "neutral"), capsule, sel);
    }

    // ── выбор: строка ↔ карточка ↔ карта ──
    function select(id) {
      if (state.sel === id && !state.selClosed) {
        if (!sideCard()) { state.selClosed = true; render(); }  // под строкой: повторное нажатие сворачивает
        return;
      }
      state.sel = id;
      state.selClosed = false;
      state.mode = null;
      state.form = null;
      state.more = false;
      render();
    }
    function closeDetail() {
      state.selClosed = true;
      state.mode = null;
      state.form = null;
      render();
      var b = state.sel && rootEl.querySelector('[data-key="sel-' + state.sel + '"]');
      if (b) b.focus();
    }
    function pointOf(x) {
      var g = x && x.geometry;
      if (!g || !g.coordinates) return null;
      if (g.type === "Point") return g.coordinates;
      var c = g.type === "LineString" ? g.coordinates : g.coordinates[0];
      return c && c.length ? c[Math.floor(c.length / 2)] : null;
    }
    // Карта плавно переходит к выбранному: объект — между листом и карточкой (бесшовно «список ↔ карта», как в 2ГИС).
    function moveMap(x, tries) {
      var m = mapObject(), p = pointOf(x);
      if (!p || !sideCard() || !alive) return;
      // Карта поднимается после оболочки: при открытии раздела по ссылке ждём её до ~12 с.
      if (!m && tries < 40) {
        setTimeout(function () { if (state.mapFor === x.id) moveMap(x, tries + 1); }, 300);
        return;
      }
      sectionLayer(0);
      if (!m) return;
      var reduce = root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches;
      try {
        m.easeTo({ center: p, zoom: Math.max(m.getZoom(), 15.5), duration: reduce ? 0 : 600,
          padding: { left: 452, right: detailHost && detailHost.isConnected ? 444 : 84, top: 84, bottom: 40 } });
      } catch (e) { /* карта не готова — без перехода */ }
    }
    // На карте — объекты открытой вкладки: «Идеи жителей» (метки «Идея · N», R05 setIdeas) или «Проекты» (метки
    // «Проект · 2027» лаймом и 3D, слой оболочки R01) — пока открыт раздел; закрыли раздел — карта как была (destroy).
    // Слой, выбранный жителем самим, не трогаем. Слои регистрируются, когда поднялся R05, — пробуем снова, до ~12 с.
    function sectionLayer(tries) {
      if (!alive || state.view !== "list") return;
      var want = state.tab === "projects" ? "projects" : "ideas";
      var cur = doc.body.dataset.birgeLayer || "";
      if (cur === want || (cur && cur !== state.layerMine)) return;
      var S = shell(), b = build3d();
      var ready = S && S.setLayer && b && (want === "projects" || typeof b.setIdeas === "function");
      if (ready) {
        S.setLayer(want);
        if (doc.body.dataset.birgeLayer === want) { state.layerMine = want; return; }
      }
      if (tries < 40) setTimeout(function () { sectionLayer(tries + 1); }, 300);
    }
    // ↑ ↓ / J K — по строкам списка, Enter — открыть, Esc — закрыть карточку (правило 2 эталона).
    function onKeys(e) {
      if (state.view !== "list" || e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
      var tag = (e.target && e.target.tagName) || "";
      if (/INPUT|TEXTAREA|SELECT/.test(tag)) return;
      if (e.key === "Escape" && state.sel && !state.selClosed) {
        e.preventDefault();
        e.stopPropagation();
        closeDetail();
        return;
      }
      var down = e.key === "ArrowDown" || e.key === "j" || e.key === "J", up = e.key === "ArrowUp" || e.key === "k" || e.key === "K";
      if (!down && !up) return;
      var ids = Array.prototype.map.call(rootEl.querySelectorAll(".ri-pc"), function (c) { return c.getAttribute("data-idea") || c.getAttribute("data-proposal"); });
      if (!ids.length) return;
      e.preventDefault();
      var i = ids.indexOf(state.sel);
      var next = ids[i < 0 ? 0 : Math.max(0, Math.min(ids.length - 1, i + (down ? 1 : -1)))];
      select(next);
      var b = rootEl.querySelector('[data-key="sel-' + next + '"]');
      if (b) { b.focus(); b.scrollIntoView({ block: "nearest" }); }
    }
    rootEl.addEventListener("keydown", onKeys);

    // ── карточка выбранного (эталон: картинка, 3 цифры, одно предложение, «Поддержать» / «Подробнее», «это опрос…») ──
    function removeDetail() {
      if (detailHost && detailHost.parentNode) detailHost.parentNode.removeChild(detailHost);
    }
    function placeDetail(sel) {
      if (!sel) { removeDetail(); return; }
      var card = detailCard(sel);
      if (sideCard()) {
        if (!detailHost) {
          detailHost = h("div", { class: "ri-pd-host bk-app" });
          detailHost.addEventListener("keydown", onKeys);
        }
        var fresh = !detailHost.isConnected || detailHost.getAttribute("data-for") !== sel.id;
        detailHost.setAttribute("data-for", sel.id);
        card.classList.toggle("ri-pd--in", fresh);
        detailHost.replaceChildren(card);
        if (!detailHost.isConnected) doc.body.appendChild(detailHost);
      } else {
        removeDetail();
        card.classList.add("ri-pd--inline");
        var row = rootEl.querySelector('.ri-pc[aria-current="true"]');
        if (row) row.after(card);
      }
    }
    // «Объект» в трёх цифрах идеи: вид из каталога, иначе тема по словам идеи (сервер, topic_of) — «Скамейки», «Сквер».
    function objectName(kind) {
      if (kind === "benches" || kind === "greening") return tr("idea.topic." + kind);
      return kind && kind !== "other" ? tr("proposal.kind." + kind) : tr("idea.kind_none");
    }
    function fact(value, label) {
      return h("div", { class: "ri-fact" }, [h("b", { class: "bk-num", text: value }), h("span", { text: label })]);
    }
    function detailCard(x) {
      var isProj = state.tab === "projects";
      var kind = isProj ? x.kind : x.object && x.object.kind;
      var t = isProj ? projTitle(x) : textOf(x, "title");
      var inner = h("div", { class: "bk-pd__in ri-pd__in" }, [h("h3", { class: "bk-pd__title ri-pd__title", id: "ri-pd-t", lang: t.lang, text: t.text })]);
      // П1: без большой картинки — название, три цифры, одно предложение и действие; значок вида — в строке списка.
      var card = h("section", { class: "bk-pd ri-pd bk-glass bk-glass--strong", role: "region", "aria-labelledby": "ri-pd-t",
        "data-pd": x.id, "data-pd-kind": isProj ? "project" : "idea" }, [inner]);
      if (isProj) {
        inner.appendChild(h("div", { class: "bk-facts ri-facts" }, [
          fact(I() ? I().formatNumber(x.votes_up || 0) : String(x.votes_up || 0), tr("idea.fact.supported")),
          fact(I() ? I().formatNumber(x.votes_down || 0) : String(x.votes_down || 0), tr("idea.fact.against")),
          fact(x.planned_year ? String(x.planned_year) : "—", tr("idea.fact.year"))]));
        // Одно предложение — как в карточке проекта на карте (proposals.js): статус словом и откуда проект.
        inner.appendChild(h("p", { class: "bk-quote ri-pd__text", text: joinDot([tr("proposal.status." + x.status), x.idea ? tr("idea.by_residents", { n: x.idea.votes || 0 })
          : joinDot([tr("proposal.kind." + x.kind), x.district ? tr("district.name", { name: tr("district." + x.district) }) : null])]) }));
        inner.appendChild(projectActions(x));
      } else {
        // Эталон: «поддержали · срок · оценка». Оценки стоимости в данных нет — третья цифра «объект» (STATUS.md, расхождения).
        var year = x.project && x.project.planned_year;
        inner.appendChild(h("div", { class: "bk-facts ri-facts" }, [
          fact(I() ? I().formatNumber(x.votes || 0) : String(x.votes || 0), tr("idea.fact.supported")),
          year ? fact(String(year), tr("idea.fact.year")) : fact(districtShort(x.district) || "—", tr("idea.fact.district")),
          fact(objectName(kind || x.topic), tr("idea.fact.object"))]));
        var decision = decisionBlock(x);
        if (decision) inner.appendChild(decision);
        else {
          var d = textOf(x, "description");
          if (d.text) inner.appendChild(h("p", { class: "bk-quote ri-pd__text" + (state.more ? " ri-pd__text--full" : ""), lang: d.lang, text: d.text }));
        }
        var together = togetherLine(x);
        if (together) inner.appendChild(together);
        if (akimat) inner.appendChild(staffActions(x));
        else inner.appendChild(residentActions(x));
        if (state.more) inner.appendChild(moreBlock(x));
      }
      inner.appendChild(h("p", { class: "bk-pd__note ri-pd__note", text: tr("idea.honest") }));
      return card;
    }
    function residentActions(item) {
      var row = h("div", { class: "bk-acts ri-pd__acts" });
      if (item.status === "voting" && !readOnly) {
        var on = !!item.my_support;
        row.appendChild(button("bk-btn--primary ri-pd__main", tr(on ? "idea.supported" : "idea.support"), on ? "check" : null,
          { "aria-pressed": String(on), "data-key": "pd-support", onclick: function () { support(item, !item.my_support); } }));
      } else if (item.status !== "hidden") {
        row.appendChild(button("bk-btn--primary ri-pd__main", tr("idea.on_map"), "pin", { "data-key": "pd-map", onclick: function () { showOnMap(item, opts); } }));
      }
      row.appendChild(button("ri-pd__second", tr(state.more ? "idea.check_close" : "common.action.more"), null,
        { "aria-expanded": String(!!state.more), "data-key": "pd-more", onclick: function () { state.more = !state.more; render(); } }));
      return row;
    }
    function moreBlock(item) {
      var box = h("div", { class: "ri-pd__more" });
      if (item.status === "voting") box.appendChild(button("bk-btn--ghost", tr("map.card.on_map"), "pin", { onclick: function () { showOnMap(item, opts); } }));
      if (item.object && item.object.kind && build3d() && build3d().view3dIdea && item.status !== "hidden") {
        box.appendChild(button("bk-btn--ghost ri-3d", tr("idea.view3d"), "cube", { onclick: function () { showOnMap(item, opts); build3d().view3dIdea(r05Idea(item)); } }));
      }
      if (item.check) box.appendChild(checklistView(item.check));
      box.appendChild(h("p", { class: "bk-meta", text: tr("proposal.one_vote") }));
      return box;
    }
    function staffActions(item) {
      var wrap = h("div", { class: "ri-pd__staff" });
      if (item.status === "review" && !(state.form && state.form.mode)) {
        var form = state.form || (state.form = { id: item.id, check: {}, kind: null, mode: null, reason: "", improve: "" });
        wrap.appendChild(h("div", { class: "bk-acts ri-pd__acts" }, [
          button("bk-btn--primary ri-pd__main", tr("ask.staff.publish"), "check", { "data-key": "publish", onclick: function () { decide(item, { action: "publish" }, "idea.published"); } }),
          button("ri-pd__second", tr("proposal.reject"), null, { "data-key": "pd-reject", onclick: function () { form.mode = "reject"; state.panelIn = item.id; render(); } }),
        ]));
        wrap.appendChild(button("bk-btn--ghost ri-hidebtn", tr("idea.hide"), null, { "data-key": "pd-hide", onclick: function () { form.mode = "hide"; state.panelIn = item.id; render(); } }));
        return wrap;
      }
      if ((item.status === "voting" || item.status === "checking") && state.mode !== "check" && !(state.form && state.form.mode)) {
        wrap.appendChild(h("div", { class: "bk-acts ri-pd__acts" }, [
          button("bk-btn--primary ri-pd__main", tr("idea.check_open"), "edit", { "data-key": "pd-check", onclick: function () { state.mode = "check"; state.panelIn = item.id; render(); } }),
          button("ri-pd__second", tr("idea.on_map"), "pin", { onclick: function () { showOnMap(item, opts); } }),
        ]));
        return wrap;
      }
      if (isDecided(item) && state.mode !== "hide" && !(state.form && state.form.mode)) {
        wrap.appendChild(h("div", { class: "bk-acts ri-pd__acts" }, [
          button("ri-pd__second", tr("idea.on_map"), "pin", { onclick: function () { showOnMap(item, opts); } }),
          button("bk-btn--ghost ri-hidebtn", tr("idea.hide_short"), null, { "data-key": "pd-hide", onclick: function () {
            state.form = null;
            state.panelIn = item.id;
            state.mode = "hide";
            render();
          } }),
        ]));
        return wrap;
      }
      wrap.appendChild(staffPanel(item));
      return wrap;
    }
    function projectActions(p) {
      var row = h("div", { class: "bk-acts ri-pd__acts" });
      if (akimat) {
        if (p.status === "proposal") {
          row.appendChild(button("bk-btn--primary ri-pd__main", tr("proposal.approve"), "check", { "data-key": "pd-approve", onclick: function (e) { decideProject(p, "approve", e.currentTarget); } }));
          row.appendChild(button("ri-pd__second", tr("proposal.reject"), null, { "data-key": "pd-reject", onclick: function (e) { decideProject(p, "reject", e.currentTarget); } }));
        } else {
          row.appendChild(h("p", { class: "ri-pd__text", text: tr("proposal.status." + p.status) }));
        }
      } else if (p.voting_open && p.status === "proposal" && readOnly) {
        row.appendChild(h("p", { class: "ri-pd__text", text: tr("idea.public.vote_residents") }));
      } else if (p.voting_open && p.status === "proposal") {
        row.appendChild(button("bk-btn--primary ri-pd__main", tr("proposal.vote_up"), "thumb-up",
          { "aria-pressed": String(p.my_vote === 1), "data-key": "pd-up", onclick: function () { voteProject(p, 1); } }));
        row.appendChild(button("ri-pd__second", tr("proposal.vote_down"), "thumb-down",
          { "aria-pressed": String(p.my_vote === -1), "data-key": "pd-down", onclick: function () { voteProject(p, -1); } }));
      } else {
        row.appendChild(h("p", { class: "ri-pd__text", text: tr("proposal.voting_closed") }));
      }
      return row;
    }
    // Голос за проект — тот же вызов R06 /proposals/{id}/vote, что у карточки на карте; число меняется сразу (правило 4).
    function voteProject(p, value) {
      var P = root.BirgeProposals && root.BirgeProposals.api;
      if (!P || state.busy) return;
      state.busy = true;
      var before = { up: p.votes_up, down: p.votes_down, mine: p.my_vote };
      var was = p.my_vote || 0;
      if (was !== value) {
        if (was === 1) p.votes_up = Math.max(0, (p.votes_up || 0) - 1);
        if (was === -1) p.votes_down = Math.max(0, (p.votes_down || 0) - 1);
        if (value === 1) p.votes_up = (p.votes_up || 0) + 1;
        if (value === -1) p.votes_down = (p.votes_down || 0) + 1;
        p.my_vote = value;
        state.bump = { id: p.id, dir: value === 1 ? 1 : 0 };
        render();
      }
      P.vote(p.id, value).then(function (data) {
        state.busy = false;
        if (data && data.item) replaceProject(data.item);
        render();
        setTimeout(function () { if (state.bump && state.bump.id === p.id) state.bump = null; }, 600);
        announce(tr(data && data.changed && data.previous ? "proposal.vote_changed" : "proposal.vote_saved"));
      }, function (err) {
        state.busy = false;
        p.votes_up = before.up;
        p.votes_down = before.down;
        p.my_vote = before.mine;
        state.bump = null;
        render();
        toast(err.status === 429 ? tr("proposal.vote_limit") : errorText(err, "proposal.vote_error"), { type: "error" });
      });
    }
    function decideProject(p, action, btn) {
      var P = root.BirgeProposals && root.BirgeProposals.api;
      if (!P || state.busy) return;
      state.busy = true;
      if (btn) btn.setAttribute("aria-busy", "true");
      P.decide(p.id, action).then(function (data) {
        state.busy = false;
        if (data && data.item) replaceProject(data.item);
        toast(tr("proposal.status." + ((data && data.item && data.item.status) || p.status)));
        render();
        if (build3d() && build3d().refresh) build3d().refresh();
      }, function (err) {
        state.busy = false;
        if (btn) btn.removeAttribute("aria-busy");
        toast(errorText(err, "proposal.vote_error"), { type: "error" });
      });
    }
    function replaceProject(item) {
      state.projects = (state.projects || []).map(function (x) { return x.id === item.id ? item : x; });
    }

    // ── общие части карточки ──
    // «Подпись: текст» — подпись жирным, текст обычным (раньше вся строка «Можно доработать: …» была жирной).
    function labeled(key, text, cls) {
      var mark = "\u0001", full = tr(key, { text: mark }), at = full.indexOf(mark);
      if (at < 0) return h("p", { class: cls, text: tr(key, { text: text }) });
      return h("p", { class: cls }, [h("strong", { text: full.slice(0, at).replace(/\s+$/, "") }), " " + text + full.slice(at + 1)]);
    }
    // ── раунд 15: идея → дело жителей (R16 «Сделаем вместе»; IA R11 §5.5) ──
    // Строка «Сделайте вместе — поддержим инвентарём» со ссылкой на дело — у идеи, ставшей инициативой; у сотрудника —
    // тихая «Сделать инициативой» для опубликованной идеи (главная кнопка карточки остаётся «Проверить»).
    // Нет R16 в сборке (ни экрана, ни capabilities.to_initiative) — ни строки, ни кнопки.
    function togetherAvailable() {
      return !!(root.BirgeTogether || (state.caps && state.caps.to_initiative));
    }
    function togetherLine(item) {
      if (item.initiative && item.initiative.id && togetherAvailable()) {
        return h("p", { class: "ri-together", "data-key": "together-line" }, [
          h("span", { class: "ri-together__ic", "aria-hidden": "true" }, [icon("heart")]),
          h("span", { class: "ri-together__text", text: tr("idea.together.line") }),
          h("a", { class: "ri-together__link", href: "#together/" + item.initiative.id, "data-key": "together-open",
            onclick: function (e) { e.preventDefault(); openTogether(item.initiative.id); } }, [tr("idea.together.open")])]);
      }
      if (akimat && state.caps && state.caps.to_initiative && !item.initiative
          && (item.status === "voting" || item.status === "checking" || item.status === "rejected")) {
        return h("div", { class: "ri-together ri-together--staff" }, [
          h("p", { class: "ri-together__text", text: tr(item.self_doable ? "idea.together.hint" : "idea.together.can") }),
          button("bk-btn--ghost ri-together__make", tr("idea.together.make"), "heart",
            { "data-key": "together-make", onclick: function () { makeTogether(item); } })]);
      }
      return null;
    }
    // Открыть дело R16: его BirgeTogether.open("initiative", id) (палитра R01, лента R06 — тот же вход); иначе адрес
    // «#together/<id>» (оболочка раунда 15 и R16 понимают его сами) или раздел + событие birge:open (FINAL-4).
    function openTogether(id) {
      var T = root.BirgeTogether;
      if (T && typeof T.open === "function" && T.open("initiative", id) !== false) return;
      var S = shell();
      if (S && typeof S.openLink === "function") { S.openLink("#together/" + id); return; }
      if (S && "path" in S) { root.location.hash = "#together/" + id; return; }
      if (S && S.setSection) S.setSection("together");
      doc.dispatchEvent(new CustomEvent("birge:open", { detail: { section: "together", path: id, link: "#together/" + id } }));
    }
    function makeTogether(item) {
      if (state.busy) return;
      state.busy = true;
      request("POST", "/ideas/" + encodeURIComponent(item.id) + "/to-initiative", {}).then(function (data) {
        state.busy = false;
        if (data && data.item) replace(data.item);
        toast(tr("idea.together.done"));
        render();
      }, function (err) {
        state.busy = false;
        if (err.status === 503) state.caps = { to_initiative: false };
        toast(tr("idea.together.error"), { type: "error" });
        render();
      });
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
    function checklistView(check) {
      return h("div", { class: "ri-check" }, [h("p", { class: "ri-check__title", text: tr("idea.check.title") })].concat(
        CHECK_KEYS.map(function (k) {
          return h("p", { class: "ri-check__row" }, [h("span", {}, [icon(CHECK_ICON[k]), h("span", { text: tr("idea.check." + k) })]),
            h("span", { class: "ri-check__answer", "data-answer": check[k], text: tr("idea.check.answer." + check[k]) })]);
        })));
    }
    // Поддержать — сразу: капсула и число меняются до ответа сервера (правило 4 эталона), ошибка возвращает как было.
    function support(item, on) {
      if (state.busy) return;
      state.busy = true;
      var before = { votes: item.votes || 0, mine: !!item.my_support };
      item.my_support = on;
      item.votes = Math.max(0, before.votes + (on ? 1 : -1));
      state.bump = { id: item.id, dir: on ? 1 : -1 };
      render();
      request("POST", "/ideas/" + encodeURIComponent(item.id) + "/support", { device_id: deviceId(), on: on }).then(function (data) {
        state.busy = false;
        if (data && data.item) {
          replace(data.item);
          render();
        }
        setTimeout(function () { if (state.bump && state.bump.id === item.id) state.bump = null; }, 600);
        // Подтверждение — сама капсула и число; для экранного диктора — та же фраза в живой области.
        announce(tr(on ? "idea.support_saved" : "idea.support_removed"));
      }, function (err) {
        state.busy = false;
        item.votes = before.votes;
        item.my_support = before.mine;
        state.bump = null;
        render();
        var retry = err.status === 0 || err.status >= 500;
        toast(errorText(err), retry ? { type: "error", action: { label: tr("common.action.retry"), onClick: function () { support(item, on); } } } : { type: "error" });
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
      // Скелетон — в форме карточек листа (картинка 84, две строки, плашка и капсула); виден не раньше 150 мс (ideas.css),
      // быстрый ответ сервера сразу рисует список без мигания (правило 4 эталона).
      body.setAttribute("aria-busy", "true");
      body.classList.add("ri-plist--skel");
      for (var i = 0; i < 3; i++) {
        body.appendChild(h("div", { class: "bk-pc ri-pc ri-skelcard", "aria-hidden": "true" }, [
          h("span", { class: "bk-skel bk-thumb ri-thumb" }),
          h("div", { class: "bk-pc__body ri-pc__t" }, [
            h("span", { class: "bk-skel bk-skel--title", style: "width:78%" }),
            h("span", { class: "bk-skel bk-skel--line", style: "width:46%" }),
            h("div", { class: "bk-pc__foot ri-pc__f" }, [h("span", { class: "bk-skel ri-skel-pill" }), h("span", { class: "bk-skel ri-skel-vote" })])]),
        ]));
      }
      body.appendChild(h("p", { class: "bk-sr-only", role: "status", text: tr("common.state.loading") }));
    }
    // Пусто: иллюстрация из линий ui-kit (три плитки видов объектов), заголовок и одна строка подсказки.
    function emptyBox(body, title, text, kinds, ill) {
      // П1: одна маленькая монохромная иконка (≤ 48 px) + заголовок + строка подсказки, без сценок.
      var art;
      if (hasIllustrations()) {
        art = h("span", { class: "ri-empty__ill", "aria-hidden": "true" });  // значок R11, размер ограничен в ideas.css
        art.innerHTML = root.BirgeUI.illustration(ill || "idea");
      } else {
        art = h("span", { class: "ri-tile", "aria-hidden": "true" }, [icon(KIND_ICON[(kinds || [])[0]] || "pin")]);
      }
      body.appendChild(h("div", { class: "ri-empty", role: "status" }, [
        art,
        h("p", { class: "ri-empty__title", text: title }),
        text ? h("p", { class: "ri-empty__text", text: text }) : null,
      ]));
    }

    // ── акимат: проверка идеи (карточка выбранного) ──
    function isDecided(item) {
      return item.status === "rejected" || item.status === "project";
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
      } else if (item.status === "review" && form.mode) {
        // «Отклонить» или «Скрыть» уже выбраны в строке карточки — ниже только причина.
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
          if (isDecided(item)) state.mode = null;  // «Отмена» — назад к кнопкам карточки (у проверки — к чек-листу)
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
        state.form = null;
        state.mode = null;
        if (data.proposal) {
          // Идея стала проектом: лист переходит на «Проекты акимата», выбран новый проект (его карточка справа).
          state.tab = "projects";
          state.sel = data.proposal.id;
        }
        load();
        if (data.proposal && build3d() && build3d().refresh) build3d().refresh();
      }, function (err) {
        state.busy = false;
        var fields = err.fields || {};
        toast(fields.kind ? tr("idea.project_kind") : fields.geometry ? tr("idea.lighting_note") : errorText(err), { type: "error" });
        if (err.code === "already_decided") load();
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
          // П1: маленький значок набора R11 (≤ 48 px) и одна строка, что делать; кнопка ниже — одна.
          content.appendChild(h("span", { class: "ri-tile", "aria-hidden": "true" }, [icon("pin")]));
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
            state.tab = "ideas";
            state.flash = state.sent && state.sent.id;
            load();
          } })]),
      ]));
    }

    var current = { render: render, focus: function (id) { state.flash = id; focusIdea(id); render(); } };
    mounted = current;
    var offLang = I() && I().onChange ? I().onChange(function () { render(); }) : null;
    // Телефон ↔ ноутбук (поворот, окно уже/шире): карточка выбранного переезжает справа ↔ под строку.
    var mq = root.matchMedia ? root.matchMedia("(min-width: 761px)") : null;
    var onWidth = function () { render(); };
    if (mq && mq.addEventListener) mq.addEventListener("change", onWidth);
    if (I() && I().ready) I().ready.then(load, load);
    else load();
    return {
      setLang: function () { render(); },
      // Оболочка раунда 15: тот же раздел, другой путь («#ideas/<id>» из ленты, назад/вперёд) — без перемонтажа.
      setPath: function (path) { if (ITEM_ID.test(path || "")) current.focus(path); },
      destroy: function () {
        alive = false;
        removeDetail();
        if (state.layerMine && doc.body.dataset.birgeLayer === state.layerMine && shell() && shell().setLayer) shell().setLayer(null);
        rootEl.removeEventListener("keydown", onKeys);
        if (live.parentNode) live.parentNode.removeChild(live);
        if (mounted === current) mounted = null;
        if (typeof offLang === "function") offLang();
        if (mq && mq.removeEventListener) mq.removeEventListener("change", onWidth);
        rootEl.classList.remove("ri");
        rootEl.replaceChildren();
      },
    };
  }

  var ITEM_ID = /^[A-Za-z0-9._:-]{1,64}$/;   // id идеи или проекта в адресе «#ideas/<id>»
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

  // Раунд 15: открыть идею или проект по ссылке («#ideas/<id>») — лента уведомлений R06 (событие birge:open от
  // BirgeNotify, пока оболочка не понимает адреса «#раздел/путь») и BirgeIdeas.open(id) для соседей.
  function openItem(id) {
    var S = shell();
    if (!id || !S) return;
    var section = S.mode === "akimat" ? "projects" : "ideas";
    if (mounted && S.section === section) {
      mounted.focus(id);
      return;
    }
    pendingFocus = id;
    S.setSection(section);
  }
  doc.addEventListener("birge:open", function (e) {
    var d = e.detail || {};
    if ((d.section === "ideas" || d.section === "projects") && ITEM_ID.test(d.path || "")) openItem(d.path);
  });

  // Карточка проекта R06 сама пишет «По идее жителей · N голосов» (proposals.js) — R05 свою строку не добавляет.
  root.BirgeIdeas = { mount: mount, open: openItem, version: "ideas-r15", KEYS: KEYS,
    cancelPick: function () { if (picker) picker.finish(false); } };
})(typeof self !== "undefined" ? self : this);
