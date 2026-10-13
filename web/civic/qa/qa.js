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
      "ask.placeholder": "Например: «Когда поставят светофор на улице Е-308?»",
      "ask.answer.only_ru": "Ответ дан на русском языке",
      "ask.answer.only_kk": "Ответ дан на казахском языке",
      "ask.answer.edited": "изменён {date}",
      "ask.answer.sign": "Аким · {date}",
      "ask.status.waiting": "Ждёт ответа",
      "ask.staff.week_caption": "отвечено на этой неделе",
      "ask.status.answered": "Есть ответ",
      "ask.answer.more": "Читать полностью",
      "ask.answer.less": "Свернуть",
      "ask.empty.top_title": "Вопросов без ответа пока нет",
      "ask.empty.new_title": "Вопросов пока нет",
      "ask.sent_hint": "Вопрос опубликуют после проверки. Тогда его увидят и смогут поддержать соседи.",
      "ask.empty.ask_hint": "Задайте свой вопрос — раз в неделю аким отвечает на самые поддержанные.",
      "ask.empty.answered_hint": "Поддержите вопросы, которые важны вам, — так они попадут в пятёрку недели.",
      "ask.empty.to_top": "Посмотреть популярные",
      "ask.staff.empty.queue_hint": "Новые вопросы жителей появятся здесь.",
      "ask.staff.empty.top_hint": "Когда жители поддержат опубликованные вопросы, здесь появится пятёрка недели.",
      "ask.staff.empty.answered_hint": "Ответьте на вопросы из «Топ-5 недели» — ответы увидят все.",
      "ask.staff.empty.to_top": "Открыть топ-5 недели",
      "ask.staff.edit_answer": "Изменить ответ",
      "ask.staff.reason_answered": "На вопрос уже ответили: снять его можно только из-за личных данных",
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
      "ask.placeholder": "Мысалы: «Е-308 көшесіне бағдаршам қашан қойылады?»",
      "ask.answer.only_ru": "Жауап орыс тілінде берілген",
      "ask.answer.only_kk": "Жауап қазақ тілінде берілген",
      "ask.answer.edited": "өзгертілді: {date}",
      "ask.answer.sign": "Әкім · {date}",
      "ask.status.waiting": "Жауап күтуде",
      "ask.staff.week_caption": "осы аптада жауап берілді",
      "ask.status.answered": "Жауабы бар",
      "ask.answer.more": "Толық оқу",
      "ask.answer.less": "Жасыру",
      "ask.empty.top_title": "Әзірге жауапсыз сұрақ жоқ",
      "ask.empty.new_title": "Әзірге сұрақ жоқ",
      "ask.sent_hint": "Сұрақ тексерілгеннен кейін жарияланады. Сонда оны көршілер көріп, қолдай алады.",
      "ask.empty.ask_hint": "Сұрағыңызды қойыңыз — әкім аптасына бір рет ең көп қолдау тапқан сұрақтарға жауап береді.",
      "ask.empty.answered_hint": "Өзіңізге маңызды сұрақтарды қолдаңыз — сонда олар аптаның бестігіне енеді.",
      "ask.empty.to_top": "Танымал сұрақтарды көру",
      "ask.staff.empty.queue_hint": "Тұрғындардың жаңа сұрақтары осында көрінеді.",
      "ask.staff.empty.top_hint": "Тұрғындар жарияланған сұрақтарды қолдағанда, мұнда аптаның бестігі шығады.",
      "ask.staff.empty.answered_hint": "«Аптаның үздік 5 сұрағына» жауап беріңіз — жауапты бәрі көреді.",
      "ask.staff.empty.to_top": "Аптаның үздік 5 сұрағын ашу",
      "ask.staff.edit_answer": "Жауапты өзгерту",
      "ask.staff.reason_answered": "Сұраққа жауап берілген: оны тек жеке деректерге байланысты алып тастауға болады",
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
  // Значков, которых нет в спрайте ui-kit, — путь из эталона (research/round-14/design/REFERENCE.html), та же толщина.
  // Когда R11 добавит их в icons.svg, строку можно убрать: спрайт главнее.
  var INLINE = { heart: "M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z" };
  function icon(name) {
    var NS = "http://www.w3.org/2000/svg";
    var svg = doc.createElementNS(NS, "svg");
    svg.setAttribute("class", "ic");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    if (INLINE[name]) {
      svg.setAttribute("viewBox", "0 0 24 24");
      var path = doc.createElementNS(NS, "path");
      path.setAttribute("d", INLINE[name]);
      svg.appendChild(path);
      return svg;
    }
    var use = doc.createElementNS(NS, "use");
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
      openAnswer: {}, // какие ответы акима раскрыты «Читать полностью»
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
    // keepScroll — тихо обновить тот же список (после голоса или действия сотрудника); soft — смена вкладки: прежний
    // список остаётся приглушённым, пока не придёт новый (без мигания скелетоном).
    function load(keepScroll, soft) {
      var req = ++state.request;
      if (!state.tab) state.tab = defaultTab();
      if (soft && state.data && state.status === "ready") {
        state.switching = true;
        render();
      } else if (!keepScroll || !state.data) {
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
        state.enter = !keepScroll; // новый список — мягкое появление карточек; тихое обновление — без движения
        state.switching = false;
        render();
        state.enter = false;
      }, function (err) {
        if (!state.alive || req !== state.request) return;
        state.switching = false;
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
      // Шапка листа как в эталоне (лист «Проекты и идеи»): заголовок 19/600 и круглая «×» справа — закрыть раздел
      // (то же, что Esc и «Карта»; без оболочки кнопки нет).
      // Правило «раз в неделю…» — подзаголовок 13 под названием (как «Остановка · …» у карточки эталона).
      box.appendChild(h("div", { class: "qa__head" }, [
        h("div", { class: "qa__ttl" }, [
          h(opts.titleTag || "h2", { class: "qa__title", id: "qa-title", tabindex: "-1", "data-focus": "title",
            text: tr(staff() ? "ask.staff.title" : "ask.title") }),
          h("p", { class: "qa__rule", text: tr("ask.rule") }),
        ]),
        typeof opts.close === "function" ? h("button", { type: "button", class: "qa__close bk-x", "aria-label": tr("common.action.close"),
          "data-focus": "close", onclick: function () { opts.close(); } }, [icon("close")]) : null,
      ]));
      if (!staff() && state.view === "form") box.appendChild(renderForm());
      else if (!staff() && state.view === "sent") box.appendChild(renderSent());
      else {
        if (!staff()) {
          box.appendChild(h("div", { class: "qa__lead" }, [
            h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-focus": "new", onclick: openForm, text: tr("ask.new") }),
          ]));
        }
        box.appendChild(renderTabs());
        if (staff() && state.tab === "top" && state.status === "ready" && !state.switching && state.data && state.data.week) {
          // Крупное число карточки эталона (.big «6 | человек сообщили»): «0 / 5 | отвечено на этой неделе».
          var wk = state.data.week;
          box.appendChild(h("p", { class: "qa__week bk-big", "aria-label": tr("ask.staff.week", { n: wk.answered || 0 }) }, [
            h("b", { "aria-hidden": "true", text: num(wk.answered || 0) + " / " + num(wk.limit || 5) }),
            h("span", { "aria-hidden": "true", text: tr("ask.staff.week_caption") })]));
        }
        box.appendChild(h("div", { class: "qa-panel-body", role: "tabpanel", id: "qa-tabpanel",
          "aria-labelledby": "qa-tab-" + state.tab }, [renderBody()]));
      }
      fitAnswers();
      if (focusKey) {
        var again = box.querySelector('[data-focus="' + focusKey + '"]');
        if (again) again.focus();
      }
    }
    // «Читать полностью» — только у цитаты, которая не влезла в 2 строки: это зависит от ширины листа, языка и шрифта,
    // а не от числа знаков (100 знаков kk на телефоне — уже 3 строки). «Свернуть» — у раскрытой длиннее 2 строк.
    function fitAnswers() {
      var items = box.querySelectorAll(".qa-answer");
      for (var i = 0; i < items.length; i++) {
        var t = items[i].querySelector(".qa-answer__text");
        var more = items[i].querySelector(".qa-answer__more");
        if (!t || !more) continue;
        var lh = parseFloat(root.getComputedStyle(t).lineHeight) || 20;
        more.hidden = items[i].classList.contains("qa-answer--open") ? t.scrollHeight <= lh * 2 + 2 : t.scrollHeight <= t.clientHeight + 1;
      }
    }
    var fitTimer = null;
    function onResize() {
      if (fitTimer) return;
      fitTimer = root.setTimeout(function () {
        fitTimer = null;
        if (state.alive) fitAnswers();
      }, 150);
    }
    if (typeof root.addEventListener === "function") root.addEventListener("resize", onResize);

    // Сегменты как в эталоне (лист «Проекты и идеи»: «Идеи жителей · 6 | Проекты акимата · 4»): подложка, выбранный —
    // белый с тенью, число через «·». Роли tablist/tab и стрелки ←/→ — BirgeUI.tabs (без ui-kit — своё то же).
    function renderTabs() {
      var tabs = staff() ? ["queue", "top", "answered"] : ["top", "new", "answered"];
      var counts = (state.data && state.data.counts) || {};
      var list = h("div", { class: "qa-seg bk-seg qa-tabs", role: "tablist", "aria-label": tr("ask.tabs_label") });
      tabs.forEach(function (id) {
        var count = counts[id];
        list.appendChild(h("button", {
          type: "button", role: "tab", id: "qa-tab-" + id, value: id, "aria-controls": "qa-tabpanel",
          "aria-selected": String(state.tab === id), tabindex: state.tab === id ? "0" : "-1", "data-focus": "tab-" + id,
        }, [h("span", { class: "qa-seg__label", text: tr(staff() ? "ask.staff." + id : "ask.tab." + id) }),
          count != null && state.status === "ready" ? h("span", { class: "qa-seg__num", text: " · " + num(count) }) : null]));
      });
      function choose(id) {
        if (!id || state.tab === id) return;
        state.tab = id;
        state.open = null;
        load(false, true);
      }
      if (root.BirgeUI && typeof root.BirgeUI.tabs === "function") {
        root.BirgeUI.tabs(list, choose);
      } else {
        list.addEventListener("click", function (e) {
          var b = e.target.closest ? e.target.closest('[role="tab"]') : null;
          if (b) choose(b.value);
        });
      }
      return list;
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

    // Загрузка — три карточки-скелетона в форме настоящих (UX: скелетон вместо пустоты), статус — для чтения с экрана.
    function skeleton() {
      var list = h("ul", { class: "qa-list qa-skeleton", "aria-hidden": "true" });
      for (var i = 0; i < 3; i++) {
        list.appendChild(h("li", { class: "qa-card bk-pc qa-card--skel" }, [
          h("span", { class: "bk-skel bk-skel--line qa-skel--short" }),
          h("span", { class: "bk-skel bk-skel--title" }),
          h("span", { class: "bk-skel bk-skel--line" }),
          h("span", { class: "bk-skel bk-skel--line qa-skel--half" }),
        ]));
      }
      return h("div", { class: "qa-state", "aria-busy": "true" }, [
        h("p", { class: "bk-sr-only", role: "status", text: tr("common.state.loading") }), list]);
    }

    // Пустое состояние: линейная картинка в стиле иконок ui-kit, что здесь будет и (если есть) куда пойти.
    function emptyArt() {
      var NS = "http://www.w3.org/2000/svg";
      var svg = doc.createElementNS(NS, "svg");
      svg.setAttribute("class", "qa-empty__art");
      svg.setAttribute("viewBox", "0 0 120 88");
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("focusable", "false");
      // Два «облачка» разговора: вопрос жителя и ответ акима (тонкие линии, без заливки).
      [["path", { d: "M14 14h56a8 8 0 0 1 8 8v26a8 8 0 0 1-8 8H38l-12 10v-10H14a8 8 0 0 1-8-8V22a8 8 0 0 1 8-8Z" }],
        ["path", { d: "M38 27.5a6 6 0 1 1 8.5 5.4c-1.6.8-2.5 2-2.5 3.6v1.5" }],
        ["circle", { cx: "44", cy: "44", r: "1.4", class: "qa-empty__dot" }],
        ["path", { d: "M84 34h22a8 8 0 0 1 8 8v20a8 8 0 0 1-8 8h-2v9l-10-9H84a8 8 0 0 1-8-8" }],
        ["path", { d: "M88 47h16M88 55h10" }]].forEach(function (x) {
        var el = doc.createElementNS(NS, x[0]);
        Object.keys(x[1]).forEach(function (k) { el.setAttribute(k, x[1][k]); });
        svg.appendChild(el);
      });
      return svg;
    }
    function emptyState(title, hint, action) {
      return h("div", { class: "qa-empty", role: "status" }, [
        emptyArt(),
        h("p", { class: "qa-empty__title", text: title }),
        hint ? h("p", { class: "qa-empty__hint", text: hint }) : null,
        action ? h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: action.onClick, text: action.label }) : null,
      ]);
    }
    function emptyFor() {
      var goTab = function (id) {
        return function () {
          state.tab = id;
          load();
        };
      };
      if (staff()) {
        if (state.tab === "queue") return emptyState(tr("ask.staff.empty.queue"), tr("ask.staff.empty.queue_hint"));
        if (state.tab === "top") return emptyState(tr("ask.staff.empty.top"), tr("ask.staff.empty.top_hint"));
        return emptyState(tr("ask.empty.answered"), tr("ask.staff.empty.answered_hint"),
          { label: tr("ask.staff.empty.to_top"), onClick: goTab("top") });
      }
      if (state.tab === "answered") return emptyState(tr("ask.empty.answered"), tr("ask.empty.answered_hint"),
        { label: tr("ask.empty.to_top"), onClick: goTab("top") });
      return emptyState(tr("ask.empty." + state.tab + "_title"), tr("ask.empty.ask_hint"));
    }

    function renderBody() {
      if (state.status === "loading") return skeleton();
      if (state.status === "login") {
        var shell = root.CivicShell;
        var canLogin = shell && typeof shell.openEditor === "function";
        // Одно главное действие — «Войти»; «Повторить» — тихая (вдруг сессия уже открыта в другой вкладке).
        return h("div", { class: "qa-empty qa-login", role: "status" }, [
          h("span", { class: "qa-login__icon", "aria-hidden": "true" }, [icon("user")]),
          h("p", { class: "qa-empty__title", text: tr("ask.staff.login") }),
          h("div", { class: "qa-empty__actions" }, [
            canLogin ? h("button", { type: "button", class: "bk-btn bk-btn--primary", onclick: function () { shell.openEditor(); },
              text: tr("ask.staff.login_btn") }) : null,
            h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: function () { load(); } },
              [icon("refresh"), tr("common.action.retry")]),
          ]),
        ]);
      }
      if (state.status === "error") {
        return stateBox("error", tr("common.state.network_title"), tr("common.state.network_text"),
          { label: tr("common.action.retry"), onClick: function () { load(); } });
      }
      var items = (state.data && state.data.items) || [];
      if (!items.length && !state.switching) return emptyFor();
      var list = h("ul", { class: "qa-list" + (state.enter ? " qa-list--enter" : "") + (state.switching ? " qa-list--busy" : ""),
        "aria-labelledby": "qa-title", "aria-busy": state.switching ? "true" : null });
      items.forEach(function (q) {
        list.appendChild(staff() ? staffCard(q) : residentCard(q));
      });
      return list;
    }

    // ---------------------------------------------------------------- карточка (эталон: строка листа «Проекты и идеи»)
    // Сверху — сам вопрос (15/600), под ним одна строка «Пример · район · когда» (13), ниже — цитата ответа акима
    // (2 строки, «Читать полностью»), внизу — пилюля статуса слева и капсула «♡ 34» справа (она же «Поддержать»).
    function meta(q, extra) {
      var parts = [];
      if (q.demo) parts.push(tr("common.tag.demo"));
      parts.push(tr("district." + q.district));
      if (extra) parts.push(extra);
      return h("p", { class: "qa-card__meta bk-pc__sub", title: q.demo ? tr("common.tag.demo_hint") : null, text: parts.join(" · ") });
    }
    function questionText(q) {
      return h("p", { class: "qa-card__text bk-pc__title", lang: q.lang === "kk" ? "kk" : "ru", text: "«" + q.text + "»" });
    }
    // Цвета пилюль — как в эталоне: «На проверке» жёлтая (.pill.review), «Есть ответ» зелёная (.pill.ok), «Ждёт ответа» серая.
    // Перед словом — статус-иконка ui-kit (правило 3 Linear, одна на весь Birge): на проверке — кольцо, ждёт ответа —
    // половина, есть ответ — закрашенная галочка (путь вопроса: проверка → публикация → ответ).
    var PILL_UI = { queue: " bk-pill--review", answered: " bk-pill--accepted", waiting: "" };
    var PILL_ST = { queue: "st-ring", waiting: "st-half", answered: "st-done" };
    function stIcon(shape) {
      var NS = "http://www.w3.org/2000/svg";
      var svg = doc.createElementNS(NS, "svg");
      svg.setAttribute("class", "qa-st");
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("focusable", "false");
      var use = doc.createElementNS(NS, "use");
      use.setAttribute("href", ICONS + "#" + shape);
      svg.appendChild(use);
      return svg;
    }
    function pill(kind) {
      var key = kind === "queue" ? "ask.staff.queue" : kind === "answered" ? "ask.status.answered" : "ask.status.waiting";
      return h("span", { class: "qa-pill qa-pill--" + kind + " bk-pill" + PILL_UI[kind] }, [stIcon(PILL_ST[kind]), tr(key)]);
    }
    function answerBlock(q) {
      var a = q.answer;
      if (!a) return null;
      var l = lang();
      var text = a[l] || a[l === "kk" ? "ru" : "kk"] || "";
      var textLangAttr = a[l] ? l : l === "kk" ? "ru" : "kk";
      var open = !!state.openAnswer[q.id];
      // Подпись и дата — в строке над цитатой: «Ответ акима · 9 окт · изменён 12 окт» (R15 S39 — правка видна всем).
      return h("div", { class: "qa-answer" + (open ? " qa-answer--open" : "") }, [
        h("p", { class: "qa-answer__sign" }, [icon("building"), h("span", { text: tr("ask.answer") + " · " + date(a.answered_at)
          + (a.edited_at ? " · " + tr("ask.answer.edited", { date: date(a.edited_at) }) : "") })]),
        // Ответ только на другом языке — честно говорим об этом (R11 разбор 15 №3)
        !a[l] && text ? h("p", { class: "qa-answer__lang", text: tr(l === "kk" ? "ask.answer.only_ru" : "ask.answer.only_kk") }) : null,
        h("blockquote", { class: "qa-answer__text bk-quote", lang: textLangAttr, id: "qa-ans-" + q.id, text: text }),
        // Кнопка видна, только если цитата правда длиннее 2 строк — это решает fitAnswers() после раскладки.
        h("button", { type: "button", class: "qa-answer__more bk-more", hidden: true, "aria-expanded": String(open),
          "aria-controls": "qa-ans-" + q.id, "data-focus": "more-" + q.id, onclick: function () {
            state.openAnswer[q.id] = !open;
            render();
          }, text: tr(open ? "ask.answer.less" : "ask.answer.more") }),
      ]);
    }
    // Капсула «♡ 34»: нажатие — «Поддержать» (один голос с устройства); после голоса — «✓ 35», светлая, без нажатия.
    // Видно только число; «34 голоса» — словами для диктора и поиска по тексту страницы (приёмка R10 W2-9).
    function votesText(q) {
      return [h("span", { class: "qa-card__votes", "aria-hidden": "true", text: num(q.votes) }),
        h("span", { class: "bk-sr-only", text: tr("ask.votes", { n: q.votes }) })];
    }
    function voteCapsule(q) {
      if (q.answer) {
        return h("span", { class: "qa-votes" }, [icon("users")].concat(votesText(q)));
      }
      if (q.my_vote) {
        return h("span", { class: "qa-card__voted qa-vote qa-vote--done bk-vote" + (state.bump === q.id ? " qa-bump" : ""),
          role: "status", tabindex: "-1", "data-focus": "vote-" + q.id },
          [icon("check"), h("span", { class: "bk-sr-only", text: tr("ask.supported") + ", " })].concat(votesText(q)));
      }
      var busy = !!state.busyVote[q.id];
      return h("button", { type: "button", class: "qa-card__vote qa-vote bk-vote", "data-focus": "vote-" + q.id,
        "aria-label": tr("ask.support") + ", " + tr("ask.votes", { n: q.votes }),
        "aria-busy": busy ? "true" : null, "aria-disabled": busy ? "true" : null,
        onclick: function () { vote(q); } }, [icon("heart")].concat(votesText(q)));
    }
    // Строка списка — разметка листа эталона (.pc → .bk-pc, тело .bk-pc__body); картинки-превью у вопроса нет.
    function card(q, parts) {
      return h("li", { class: "qa-card bk-pc", "data-id": q.id }, [h("div", { class: "qa-card__body bk-pc__body" }, parts)]);
    }

    // ---------------------------------------------------------------- житель
    function residentCard(q) {
      return card(q, [
        questionText(q),
        meta(q, q.published_at ? relative(q.published_at) : null),
        answerBlock(q),
        h("div", { class: "qa-card__foot bk-pc__foot" }, [pill(q.answer ? "answered" : "waiting"), voteCapsule(q)]),
      ]);
    }

    function vote(q) {
      if (state.busyVote[q.id]) return;
      state.busyVote[q.id] = true;
      // Сразу показываем «Вы поддержали»; ошибка — вернуть как было и сказать об этом.
      q.my_vote = true;
      q.votes += 1;
      state.bump = q.id; // число голосов «подпрыгивает» один раз (без движения при prefers-reduced-motion)
      render();
      state.bump = null;
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
        // Ошибка уходит, как только текст стал подходящим (не ждём повторного нажатия «Отправить»).
        if (d.field === "text" && d.text.trim().length >= TEXT_MIN) {
          d.field = null;
          d.error = null;
          var f = area.closest(".bk-field");
          if (f) f.classList.remove("bk-field--error");
          area.removeAttribute("aria-invalid");
          var e = box.querySelector("#qa-text-error");
          if (e) e.remove();
        }
      });
      var select = h("select", { id: "qa-district", "aria-invalid": districtError ? "true" : null,
        "aria-describedby": districtError ? "qa-district-error" : null });
      select.appendChild(h("option", { value: "", text: tr("ask.district_choose") }));
      DISTRICTS.forEach(function (id) {
        var o = h("option", { value: id, text: tr("district." + id) });
        if (d.district === id) o.selected = true;
        select.appendChild(o);
      });
      select.addEventListener("change", function () {
        d.district = select.value;
        if (d.field === "district" && d.district) {
          d.field = null;
          d.error = null;
          var f = select.closest(".bk-field");
          if (f) f.classList.remove("bk-field--error");
          select.removeAttribute("aria-invalid");
          var e = box.querySelector("#qa-district-error");
          if (e) e.remove();
        }
      });
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
            "aria-disabled": d.busy ? "true" : null }, [tr("ask.send")]), // при отправке — только крутилка ui-kit
          h("button", { type: "button", class: "bk-btn", onclick: closeForm, text: tr("common.action.cancel") }),
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
      var NS = "http://www.w3.org/2000/svg";
      var mark = doc.createElementNS(NS, "svg");
      mark.setAttribute("class", "qa-sent__mark");
      mark.setAttribute("viewBox", "0 0 52 52");
      mark.setAttribute("aria-hidden", "true");
      // Галочка рисуется линией (240 мс) внутри круга; при prefers-reduced-motion — сразу целиком.
      mark.innerHTML = '<circle cx="26" cy="26" r="24"></circle><path d="m15 27 7.5 7.5L37.5 19"></path>';
      return h("div", { class: "qa-empty qa-sent", role: "status" }, [
        mark,
        h("p", { class: "qa-empty__title", id: "qa-sent-title", tabindex: "-1", "data-focus": "sent-title", text: tr("ask.sent_title") }),
        h("p", { class: "qa-empty__hint", text: tr("ask.sent_hint") }),
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
        warn.push(h("span", { class: "qa-pill qa-pill--warn bk-pill bk-pill--review" }, [icon("alert"), tr("ask.staff.pii", {
          what: q.pii.map(function (k) { return tr("ask.staff.pii." + k); }).join(", ") })]));
      }
      if (q.rude) warn.push(h("span", { class: "qa-pill qa-pill--warn bk-pill bk-pill--review" }, [icon("alert"), tr("ask.staff.rude")]));
      var open = state.open && state.open.id === q.id ? state.open.kind : null;
      return card(q, [
        questionText(q),
        meta(q, when),
        warn.length ? h("p", { class: "qa-card__warn" }, warn) : null,
        answerBlock(q),
        h("div", { class: "qa-card__foot bk-pc__foot" }, [pill(state.tab === "queue" ? "queue" : q.answer ? "answered" : "waiting"),
          state.tab !== "queue" ? h("span", { class: "qa-votes" }, [icon("users")].concat(votesText(q))) : null]),
        open === "reject" ? rejectPanel(q) : open === "answer" ? answerPanel(q) : staffActions(q),
      ]);
    }

    function staffActions(q) {
      var row = h("div", { class: "qa-card__actions" });
      if (state.tab === "queue") {
        row.appendChild(h("button", { type: "button", class: "bk-btn", "data-focus": "pub-" + q.id,
          onclick: function () { act(q, "publish", {}, "ask.staff.done.published"); }, text: tr("ask.staff.publish") }));
        row.appendChild(h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "rej-" + q.id,
          onclick: function () { openPanel(q, "reject"); }, text: tr("ask.staff.reject") }));
      } else if (state.tab === "top") {
        row.appendChild(h("button", { type: "button", class: "bk-btn", "data-focus": "ans-" + q.id,
          onclick: function () { openPanel(q, "answer"); }, text: tr("ask.staff.answer") }));
        row.appendChild(h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "rej-" + q.id,
          onclick: function () { openPanel(q, "reject"); }, text: tr("ask.staff.reject") }));
      } else {
        row.appendChild(h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "ans-" + q.id,
          onclick: function () { openPanel(q, "answer"); }, text: tr("ask.staff.edit_answer") }));
        // Снять отвеченный вопрос можно только по причине «личные данные» (сервер отвечает 409 на другие причины).
        row.appendChild(h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "rej-" + q.id,
          onclick: function () { openPanel(q, "reject"); }, text: tr("ask.staff.reject") }));
      }
      return row;
    }

    function openPanel(q, kind) {
      state.open = { id: q.id, kind: kind };
      state.staffDraft = { reason: kind === "reject" && q.answer ? "personal_data" : null, note: "",
        answer_ru: (q.answer && q.answer.ru) || "",
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
      // Отвеченный вопрос снимают только из-за личных данных (R15 S35; сервер на другие причины отвечает 409).
      var answered = !!q.answer;
      if (answered) group.appendChild(h("p", { class: "bk-meta", text: tr("ask.staff.reason_answered") }));
      (answered ? ["personal_data"] : REASONS).forEach(function (r) {
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
          h("button", { type: "button", class: "bk-btn", onclick: function () { closePanel(q); }, text: tr("common.action.cancel") }),
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
          h("button", { type: "submit", class: "bk-btn bk-btn--primary", "aria-busy": d.busy ? "true" : null, text: tr("ask.staff.answer_send") }),
          h("button", { type: "button", class: "bk-btn", onclick: function () { closePanel(q); }, text: tr("common.action.cancel") }),
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
        if (typeof root.removeEventListener === "function") root.removeEventListener("resize", onResize);
        if (fitTimer) root.clearTimeout(fitTimer);
        if (box.parentNode) box.parentNode.removeChild(box);
      },
    };
  }

  root.BirgeAsk = { mount: mount, version: "r13-qa-1" };
})(typeof window !== "undefined" ? window : this);
