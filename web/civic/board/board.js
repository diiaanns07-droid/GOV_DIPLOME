/*
 * Birge · Ситуационный центр акимата (R08, раунд 15) — страница на весь экран для большого экрана и проектора.
 *
 * Подключение: web/civic/board/index.html (отдельная страница; меню акимата открывает её ссылкой, схема R11),
 * или BirgeBoard.mount(элемент, { apiBase: "/api/civic/v2" }) → { destroy, setLang, refresh }.
 * Нужны ui-kit/tokens.css (шрифт, цвета карты) и i18n/i18n.js (BirgeI18n); без них работают запасные тексты.
 *
 * Данные: GET {apiBase}/akim/board?district=<id> — только сотруднику (сессия; иначе 403 и экран «Войдите»).
 * Числа считает сервер (ui/civic_akim/board.py: «Картина дня» + R17 + R16 + R13), здесь — только показ.
 *
 * Экран: шапка (район, часы Астаны, ҚАЗ/РУС, «Пример») · баннер кризиса · 4 числа с мини-графиками за 14 дней ·
 * слева «Пульс» и «Горячие места» (всегда на виду) · справа блоки по очереди каждые 15 с: кризисный штаб,
 * ведомства, решение акима, жители вместе, встречи, прогноз, темы, районы (только непустые — сервер даёт slides).
 * Управление: ← → — соседний блок, пробел — пауза, наведение и фокус — пауза, F — на весь экран. Курсор прячется,
 * если мышь не двигалась 4 с (большой экран). Новые числа приходят раз в минуту; число меняется плавно (600 мс),
 * при prefers-reduced-motion — сразу. Нет связи — остаются последние числа и пометка «Нет связи — данные на …».
 * Узкий экран (< 761 px) — все блоки подряд, без автосмены.
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var scriptBase = ((doc.currentScript && doc.currentScript.src) || "").replace(/[^/]*$/, "");
  var SPRITE = scriptBase + "../ui-kit/icons.svg";
  var DEFAULTS = {
    apiBase: "/api/civic/v2",
    loginHref: "/", // вход сотрудника — на главной (аватар → «Для сотрудников»)
    homeHref: "/",
    syncUrl: true, // район и язык — в адресе: ссылку на экран можно отправить
    timeoutMs: 15000,
  };
  var DISTRICTS = ["almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"];
  var IDLE_CURSOR_MS = 4000;
  var RETRY_MS = 30000;
  var STALE_MS = 3 * 60000;
  var SKELETON_DELAY_MS = 150;
  var TWEEN_MS = 600;
  var ASTANA_OFFSET_MS = 5 * 3600 * 1000;

  // ───────────── тексты ─────────────
  // Сначала словарь R11 (BirgeI18n); ключа там ещё нет — этот запас (ключи board.* переданы R11 в INTEGRATION R08 §7).
  var FALLBACK = {
    ru: {
      "board.title": "Ситуационный центр",
      "board.scope.city": "Весь город",
      "board.scope.district": "Район {name}",
      "board.district.label": "Район",
      "board.kpi.new_day": "Новые сегодня",
      "board.kpi.in_progress": "В работе",
      "board.kpi.overdue": "Просрочено",
      "board.kpi.fixed": "Исправлено за 7 дней",
      "board.kpi.week": "за 7 дней: {n}",
      "board.kpi.waiting": "ждут ответа: {n}",
      "board.kpi.verified": "проверено жителями: {n}",
      "board.kpi.reported": "служба сообщила об устранении",
      "board.kpi.overdue_hint": "не исправлено в срок",
      "board.delta.vs_week": ", чем неделю назад",
      "board.pulse.title": "Пульс",
      "board.hot.meta": "за 7 дней · человек",
      "board.crisis.title": "Кризис: {title} · {zone}",
      "board.crisis.meta": "с {time} · задачи {done} из {total} · служб: {services}",
      "board.crisis.updated": "обновлено {time}",
      "board.crisis.more": { one: "и ещё {n} кризис", few: "и ещё {n} кризиса", many: "и ещё {n} кризисов" },
      "board.crisis.open": "Открыть кризисный штаб",
      "board.crisis.in_hq": "в кризисном штабе",
      "board.crisis.zone_city": "весь город",
      "board.crisis.tasks": "Задачи служб",
      "board.crisis.since": "с {time}",
      "board.crisis.tasks_done": "Задачи служб: {done} из {total}",
      "board.crisis.last": "Жителям зоны",
      "board.slide.crisis": "Кризисный штаб",
      "board.slide.services": "Ведомства",
      "board.slide.decisions": "Нужно решение акима",
      "board.slide.together": "Жители вместе",
      "board.slide.meetings": "Встречи с жителями",
      "board.slide.forecast_week": "Прогноз на неделю",
      "board.slide.forecast_month": "Прогноз на месяц",
      "board.slide.topics": "Темы за 7 дней",
      "board.slide.districts": "Районы за 7 дней",
      "board.slide.of": "{i} из {n}",
      "board.services.name": "Служба",
      "board.services.open": "Открыто",
      "board.services.overdue": "Просрочено",
      "board.services.median": "Ответ, дн.",
      "board.services.verified": "Проверено жителями",
      "board.services.joint": "Совместных обращений: {n}",
      "board.services.handoffs": "Передач между службами за неделю: {n}",
      "board.services.lagging": "Красная точка — больше всего просрочек",
      "board.decisions.option": "Вариант {n}: {text}",
      "board.decisions.overdue": { one: "просрочено на {n} день", few: "просрочено на {n} дня", many: "просрочено на {n} дней" },
      "board.decisions.where": "Выбрать вариант — в «Картине дня»",
      "board.together.done": "Сделано вместе",
      "board.together.joined": "Откликов «Я приду»",
      "board.together.verified": "Проверено жителями",
      "board.together.supported": "Поддержано акиматом",
      "board.together.yard": "Двор недели",
      "board.together.members": { one: "{n} сосед в Birge", few: "{n} соседа в Birge", many: "{n} соседей в Birge" },
      "board.together.people": { one: "{n} сосед", few: "{n} соседа", many: "{n} соседей" },
      "board.together.when": "{date}",
      "board.together.done_tag": "Сделано",
      "board.meetings.done": "Сделано",
      "board.meetings.in_work": "В работе",
      "board.meetings.overdue": "Просрочено",
      "board.meetings.due": "срок {date}",
      "board.meetings.next": "Следующая встреча: {date} — {title}",
      "board.meetings.registered": { one: "придёт {n} житель", few: "придут {n} жителя", many: "придут {n} жителей" },
      "board.forecast.note": "Прототип: модель обучена на синтетической истории, это не настоящая оценка риска.",
      "board.prototype": "прототип",
      "board.forecast.level.high": "высокий",
      "board.forecast.level.medium": "средний",
      "board.forecast.level.low": "низкий",
      "board.topics.meta": "человек сообщили о нерешённом",
      "board.nodata": "Пока нет данных",
      "board.foot.updated": "Обновлено {time}",
      "board.foot.stale": "Нет связи — данные на {time}",
      "board.foot.pause": "Пауза",
      "board.foot.play": "Дальше",
      "board.foot.fullscreen": "На весь экран",
      "board.foot.keys": "← → блоки · пробел — пауза",
      "board.foot.demo": "Пример: числа посчитаны по синтетическим данным",
      "board.state.loading": "Собираем картину города…",
      "board.state.forbidden": "Ситуационный центр открывается сотрудникам акимата",
      "board.state.forbidden_hint": "Войдите на главной странице: аватар → «Для сотрудников», затем откройте центр снова.",
      "board.state.login": "Перейти ко входу",
      "board.state.not_ready": "Ситуационный центр ещё не подключён в этой сборке",
      "board.state.not_ready_hint": "Сервер работает, но маршрут akim/board пока не включён. Карта и «Картина дня» доступны.",
      "board.state.error": "Не удалось загрузить данные",
      "board.state.error_hint": "Проверьте связь с сервером. Повторим сами через 30 секунд.",
      "board.home": "Birge — на карту",
    },
    kk: {
      "board.title": "Жағдаяттық орталық",
      "board.scope.city": "Бүкіл қала",
      "board.scope.district": "{name} ауданы",
      "board.district.label": "Аудан",
      "board.kpi.new_day": "Бүгін жаңа",
      "board.kpi.in_progress": "Орындалуда",
      "board.kpi.overdue": "Мерзімі өткен",
      "board.kpi.fixed": "7 күнде түзетілді",
      "board.kpi.week": "7 күнде: {n}",
      "board.kpi.waiting": "жауап күтуде: {n}",
      "board.kpi.verified": "тұрғындар тексерді: {n}",
      "board.kpi.reported": "қызмет түзетілгенін хабарлады",
      "board.kpi.overdue_hint": "мерзімінде түзетілмеген",
      "board.delta.vs_week": " — бір апта бұрынғымен салыстырғанда",
      "board.pulse.title": "Пульс",
      "board.hot.meta": "соңғы 7 күн · адам саны",
      "board.crisis.title": "Дағдарыс: {title} · {zone}",
      "board.crisis.meta": "{time} бастап · тапсырмалар: {done}/{total} · қызметтер: {services}",
      "board.crisis.updated": "жаңартылды: {time}",
      "board.crisis.more": "тағы {n} дағдарыс",
      "board.crisis.open": "Дағдарыс штабын ашу",
      "board.crisis.in_hq": "дағдарыс штабында",
      "board.crisis.zone_city": "бүкіл қала",
      "board.crisis.tasks": "Қызметтердің тапсырмалары",
      "board.crisis.since": "{time} бастап",
      "board.crisis.tasks_done": "Қызметтердің тапсырмалары: {done}/{total}",
      "board.crisis.last": "Аймақ тұрғындарына",
      "board.slide.crisis": "Дағдарыс штабы",
      "board.slide.services": "Қызметтер",
      "board.slide.decisions": "Әкімнің шешімі керек",
      "board.slide.together": "Тұрғындар бірге",
      "board.slide.meetings": "Тұрғындармен кездесулер",
      "board.slide.forecast_week": "Апталық болжам",
      "board.slide.forecast_month": "Айлық болжам",
      "board.slide.topics": "Соңғы 7 күндегі тақырыптар",
      "board.slide.districts": "Аудандар, соңғы 7 күн",
      "board.slide.of": "{i}/{n}",
      "board.services.name": "Қызмет",
      "board.services.open": "Ашық",
      "board.services.overdue": "Мерзімі өткен",
      "board.services.median": "Жауап, күн",
      "board.services.verified": "Тұрғындар тексерді",
      "board.services.joint": "Бірлескен өтініштер: {n}",
      "board.services.handoffs": "Апта ішінде басқа қызметке берілгені: {n}",
      "board.services.lagging": "Қызыл нүкте — мерзімі өткені ең көп",
      "board.decisions.option": "{n}-нұсқа: {text}",
      "board.decisions.overdue": "мерзімі {n} күнге өтті",
      "board.decisions.where": "Нұсқаны «Күн қорытындысында» таңдаңыз",
      "board.together.done": "Бірге атқарылды",
      "board.together.joined": "«Барамын» белгісі",
      "board.together.verified": "Тұрғындар тексерді",
      "board.together.supported": "Әкімдік қолдады",
      "board.together.yard": "Апта ауласы",
      "board.together.members": "Birge-де {n} көрші",
      "board.together.people": "{n} көрші",
      "board.together.when": "{date}",
      "board.together.done_tag": "Атқарылды",
      "board.meetings.done": "Орындалды",
      "board.meetings.in_work": "Орындалуда",
      "board.meetings.overdue": "Мерзімі өткен",
      "board.meetings.due": "мерзімі {date}",
      "board.meetings.next": "Келесі кездесу: {date} — {title}",
      "board.meetings.registered": "{n} тұрғын келеді",
      "board.forecast.note": "Прототип: модель синтетикалық тарихта оқытылған, бұл нақты тәуекел бағасы емес.",
      "board.prototype": "прототип",
      "board.forecast.level.high": "жоғары",
      "board.forecast.level.medium": "орташа",
      "board.forecast.level.low": "төмен",
      "board.topics.meta": "адам шешілмеген мәселе туралы хабарлады",
      "board.nodata": "Әзірге дерек жоқ",
      "board.foot.updated": "Жаңартылды: {time}",
      "board.foot.stale": "Байланыс жоқ — деректер {time} уақытындағы",
      "board.foot.pause": "Кідірту",
      "board.foot.play": "Жалғастыру",
      "board.foot.fullscreen": "Толық экран",
      "board.foot.keys": "← → блоктар · бос орын — кідірту",
      "board.foot.demo": "Үлгі: сандар синтетикалық деректер бойынша есептелген",
      "board.state.loading": "Қала жағдайы жиналуда…",
      "board.state.forbidden": "Жағдаяттық орталық әкімдік қызметкерлеріне ашылады",
      "board.state.forbidden_hint": "Басты бетте кіріңіз: аватар → «Қызметкерлерге», содан кейін орталықты қайта ашыңыз.",
      "board.state.login": "Кіруге өту",
      "board.state.not_ready": "Жағдаяттық орталық бұл жинақта әлі қосылмаған",
      "board.state.not_ready_hint": "Сервер жұмыс істеп тұр, бірақ akim/board маршруты әлі қосылмаған. Карта мен «Күн қорытындысы» қолжетімді.",
      "board.state.error": "Деректер жүктелмеді",
      "board.state.error_hint": "Сервермен байланысты тексеріңіз. 30 секундтан кейін өзіміз қайталаймыз.",
      "board.home": "Birge — картаға",
    },
  };
  // Ключи общего словаря R11, которые экран берёт как есть (их запас — на случай, если словарь не загрузился).
  var SHARED = {
    ru: {
      "common.demo": "Пример", "common.action.retry": "Повторить", "common.lang.label": "Язык интерфейса",
      "common.lang.ru": "РУС", "common.lang.kk": "ҚАЗ", "akim.hot.title": "Горячие места",
      "akim.pulse.none": "Резких всплесков нет", "akim.delta.same": "без изменений", "akim.delta.new": "неделю назад не было",
      "akim.delta.more": "больше на {v}", "akim.delta.less": "меньше на {v}",
      "akim.delta.ratio": { one: "в {n} раз больше", few: "в {n} раза больше", many: "в {n} раз больше" },
      "akim.pulse.spike": "{category} · {district}: ×{k} к обычному уровню",
      "akim.pulse.spike_new": "{category} · {district}: раньше такого не было",
      "akim.pulse.spike_city": { one: "{category}: всплеск в {n} районе, ×{k}", few: "{category}: всплеск в {n} районах, ×{k}", many: "{category}: всплеск в {n} районах, ×{k}" },
      "akim.pulse.new_hot": "Новое горячее место: {place}",
      "akim.pulse.metoo_growth": "Чаще жмут «Я тоже»: {place}, +{n} за неделю",
      "akim.pulse.reason.spike": { one: "{n} сообщение за 7 дней, обычно {base} в неделю", few: "{n} сообщения за 7 дней, обычно {base} в неделю", many: "{n} сообщений за 7 дней, обычно {base} в неделю" },
      "akim.pulse.reason.spike_new": { one: "{n} сообщение за 7 дней, раньше — ни одного", few: "{n} сообщения за 7 дней, раньше — ни одного", many: "{n} сообщений за 7 дней, раньше — ни одного" },
      "akim.pulse.reason.city": "Больше всего: {list}",
      "akim.pulse.reason.new_hot": { one: "{n} человек за 7 дней, неделю назад места на карте не было", few: "{n} человека за 7 дней, неделю назад места на карте не было", many: "{n} человек за 7 дней, неделю назад места на карте не было" },
      "akim.pulse.reason.metoo": "Неделей раньше — {n}",
      "akim.pulse.more": { one: "Ещё {n} тревога", few: "Ещё {n} тревоги", many: "Ещё {n} тревог" },
      "status.new": "Новое", "status.accepted": "Принято", "status.in_progress": "В работе", "status.fixed": "Исправлено",
    },
    kk: {
      "common.demo": "Үлгі", "common.action.retry": "Қайталау", "common.lang.label": "Интерфейс тілі",
      "common.lang.ru": "РУС", "common.lang.kk": "ҚАЗ", "akim.hot.title": "Шағымы көп орындар",
      "akim.pulse.none": "Күрт өсу жоқ", "akim.delta.same": "өзгеріс жоқ", "akim.delta.new": "бір апта бұрын болмаған",
      "akim.delta.more": "{v} артық", "akim.delta.less": "{v} кем", "akim.delta.ratio": "{n} есе көп",
      "akim.pulse.spike": "{category} · {district}: әдеттегіден ×{k}",
      "akim.pulse.spike_new": "{category} · {district}: бұрын мұндай болмаған",
      "akim.pulse.spike_city": "{category}: {n} ауданда күрт өсу, ×{k}",
      "akim.pulse.new_hot": "Жаңа ыстық орын: {place}",
      "akim.pulse.metoo_growth": "«Мен де» жиі басылады: {place}, аптасына +{n}",
      "akim.pulse.reason.spike": "7 күнде {n} хабарлама, әдетте аптасына {base}",
      "akim.pulse.reason.spike_new": "7 күнде {n} хабарлама, бұрын бірде-бір болмаған",
      "akim.pulse.reason.city": "Ең көбі: {list}",
      "akim.pulse.reason.new_hot": "7 күнде {n} адам, бір апта бұрын бұл орын картада болмаған",
      "akim.pulse.reason.metoo": "Алдыңғы аптада — {n}",
      "akim.pulse.more": "Тағы {n}",
      "status.new": "Жаңа", "status.accepted": "Қабылданды", "status.in_progress": "Орындалуда", "status.fixed": "Түзетілді",
    },
  };
  var MONTHS = {
    ru: ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"],
    kk: ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"],
  };
  var WEEKDAYS = {
    ru: ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"],
    kk: ["жексенбі", "дүйсенбі", "сейсенбі", "сәрсенбі", "бейсенбі", "жұма", "сенбі"],
  };

  function I() { return root.BirgeI18n || null; }
  function lang() { return I() && I().getLang ? I().getLang() : "ru"; }
  function num(n) {
    if (I() && I().formatNumber) return I().formatNumber(n);
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }
  function pct(share) { return num(Math.round(share * 100)) + " %"; }
  function pluralRu(n) {
    var a = Math.abs(Number(n));
    if (a % 1 !== 0) return "few";
    var m10 = a % 10, m100 = a % 100;
    if (m10 === 1 && m100 !== 11) return "one";
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "few";
    return "many";
  }
  function interpolate(text, params) {
    return String(text).replace(/\{(\w+)\}/g, function (whole, name) {
      if (!params || params[name] == null) return whole;
      return typeof params[name] === "number" ? num(params[name]) : String(params[name]);
    });
  }
  function tr(key, params) {
    var B = I();
    if (B && B.has && B.has(key)) return B.t(key, params);
    var l = lang();
    var v = (FALLBACK[l] && FALLBACK[l][key]) || (SHARED[l] && SHARED[l][key]) || FALLBACK.ru[key] || SHARED.ru[key];
    if (v == null) return key;
    if (typeof v === "object") {
      var n = params && params.n != null ? params.n : 0;
      v = l === "ru" ? v[pluralRu(n)] || v.many : v.other || v.many || v.one;
    }
    return interpolate(v, params);
  }
  function catName(id) {
    var B = I();
    if (B && B.cat) { var c = B.cat(id); if (c && c !== id) return c; }
    return id || "";
  }
  function districtName(id) {
    var B = I();
    if (id && B && B.has && B.has("district." + id)) return B.t("district." + id);
    return id || "";
  }
  function pick(obj, base) {
    if (!obj) return "";
    return obj[base + "_" + lang()] || obj[base + "_ru"] || obj[base + "_kk"] || "";
  }

  // ───────────── время Астаны ─────────────
  function astana(ms) {
    var d = new Date((ms == null ? Date.now() : ms) + ASTANA_OFFSET_MS);
    return { y: d.getUTCFullYear(), m: d.getUTCMonth(), d: d.getUTCDate(), wd: d.getUTCDay(), hh: d.getUTCHours(), mm: d.getUTCMinutes() };
  }
  function pad2(v) { return (v < 10 ? "0" : "") + v; }
  function clockText(ms) { var p = astana(ms); return pad2(p.hh) + ":" + pad2(p.mm); }
  function longDate(ms) {
    var p = astana(ms), l = lang() === "kk" ? "kk" : "ru";
    var wd = WEEKDAYS[l][p.wd];
    return l === "kk" ? p.d + " " + MONTHS.kk[p.m] + ", " + wd : wd.charAt(0).toUpperCase() + wd.slice(1) + ", " + p.d + " " + MONTHS.ru[p.m];
  }
  function timeOf(iso) {
    var t = Date.parse(iso || "");
    return isFinite(t) ? clockText(t) : "—";
  }
  function shortDate(iso) {
    var B = I();
    if (B && B.formatDate) return B.formatDate(iso);
    var t = Date.parse(iso || "");
    if (!isFinite(t)) return "—";
    var p = astana(t);
    return p.d + " " + MONTHS[lang() === "kk" ? "kk" : "ru"][p.m];
  }
  function dayTime(iso) {
    var t = Date.parse(iso || "");
    return isFinite(t) ? shortDate(iso) + ", " + clockText(t) : "—";
  }

  // ───────────── DOM ─────────────
  function h(tag, attrs, children) {
    var el = doc.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v == null || v === false) return;
        if (k === "text") el.textContent = v;
        else if (k === "class") el.className = v;
        else if (k.slice(0, 2) === "on" && typeof v === "function") el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? "" : String(v));
      });
    }
    (children || []).forEach(function (c) {
      if (c == null || c === false) return;
      el.appendChild(typeof c === "string" || typeof c === "number" ? doc.createTextNode(String(c)) : c);
    });
    return el;
  }
  // replaceChildren без «null» в тексте: пустые части (нет кризиса, нет пометки) просто пропускаются.
  function fill(el, list) {
    el.replaceChildren.apply(el, list.filter(function (c) { return c != null && c !== false; }));
    return el;
  }
  var SVG = "http://www.w3.org/2000/svg";
  function icon(name, cls) {
    var svg = doc.createElementNS(SVG, "svg");
    svg.setAttribute("class", "ic" + (cls ? " " + cls : ""));
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var use = doc.createElementNS(SVG, "use");
    use.setAttribute("href", SPRITE + "#" + (name.indexOf("st-") === 0 || name.indexOf("ill-") === 0 ? name : "i-" + name));
    svg.appendChild(use);
    return svg;
  }
  // Пауза / дальше / весь экран: в наборе ui-kit таких нет — простые фигуры той же толщины линии.
  var GLYPHS = {
    pause: "M8 5v14M16 5v14",
    play: "M7 5l12 7-12 7z",
    expand: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
  };
  function glyph(name) {
    var svg = doc.createElementNS(SVG, "svg");
    svg.setAttribute("class", "ic");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var path = doc.createElementNS(SVG, "path");
    path.setAttribute("d", GLYPHS[name]);
    if (name === "play") path.setAttribute("fill", "currentColor");
    svg.appendChild(path);
    return svg;
  }
  // Статус-иконки ui-kit (правило Linear 3): пустой круг — новое, половина — в работе, галочка — сделано.
  function statusIcon(status) {
    var name = status === "done" ? "st-done" : status === "in_progress" || status === "doing" ? "st-half" : "st-ring";
    return h("span", { class: "sc-status", "data-status": status, "aria-hidden": "true" }, [icon(name)]);
  }
  function reducedMotion() {
    return !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }
  function narrow() {
    return !!(root.matchMedia && root.matchMedia("(max-width: 760px), (max-height: 600px) and (max-aspect-ratio: 4/3)").matches);
  }

  // Подгонка под высоту блока (большой экран без прокрутки): из списков [data-fit] убираем последние строки целиком,
  // пока блок не помещается, — никаких строк, обрезанных посередине. Минимум одна строка остаётся.
  function fit(box) {
    if (!box || narrow()) return;
    var lists = box.querySelectorAll("[data-fit]");
    for (var i = lists.length - 1; i >= 0; i--) {
      var list = lists[i];
      while (list.children.length > 1 && box.scrollHeight > box.clientHeight + 1) list.removeChild(list.lastElementChild);
    }
  }

  // Мини-график за 14 дней: линия + мягкая заливка + точка «сегодня».
  function sparkline(series, color) {
    var vals = (series || []).map(function (v) { return Number(v) || 0; });
    if (vals.length < 2) return null;
    var w = 140, hgt = 44, pad = 4, max = Math.max.apply(null, vals.concat([1]));
    var pts = vals.map(function (v, i) {
      return [pad + (i * (w - 2 * pad)) / (vals.length - 1), hgt - pad - (v / max) * (hgt - 2 * pad)];
    });
    var line = pts.map(function (p, i) { return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
    var area = line + " L" + pts[pts.length - 1][0].toFixed(1) + " " + (hgt - pad) + " L" + pts[0][0].toFixed(1) + " " + (hgt - pad) + " Z";
    var svg = doc.createElementNS(SVG, "svg");
    svg.setAttribute("class", "sc-spark");
    svg.setAttribute("viewBox", "0 0 " + w + " " + hgt);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("aria-hidden", "true");
    var a = doc.createElementNS(SVG, "path");
    a.setAttribute("class", "area"); a.setAttribute("d", area); a.setAttribute("fill", color);
    var l = doc.createElementNS(SVG, "path");
    l.setAttribute("class", "line"); l.setAttribute("d", line); l.setAttribute("stroke", color);
    var last = pts[pts.length - 1];
    var dot = doc.createElementNS(SVG, "circle");
    dot.setAttribute("cx", last[0].toFixed(1)); dot.setAttribute("cy", last[1].toFixed(1)); dot.setAttribute("r", "3.5");
    dot.setAttribute("fill", color);
    svg.appendChild(a); svg.appendChild(l); svg.appendChild(dot);
    return svg;
  }

  // Кольцо прогресса задач службы в кризисе.
  function ring(done, total) {
    var svg = doc.createElementNS(SVG, "svg");
    svg.setAttribute("class", "sc-chip__ring");
    svg.setAttribute("viewBox", "0 0 20 20");
    svg.setAttribute("aria-hidden", "true");
    var r = 8, c = 2 * Math.PI * r, part = total ? done / total : 0;
    var bg = doc.createElementNS(SVG, "circle");
    bg.setAttribute("cx", "10"); bg.setAttribute("cy", "10"); bg.setAttribute("r", String(r));
    bg.setAttribute("fill", "none"); bg.setAttribute("stroke", "rgba(255,255,255,.18)"); bg.setAttribute("stroke-width", "3");
    var fg = doc.createElementNS(SVG, "circle");
    fg.setAttribute("cx", "10"); fg.setAttribute("cy", "10"); fg.setAttribute("r", String(r));
    fg.setAttribute("fill", "none"); fg.setAttribute("stroke", part >= 1 ? "#8fd46c" : "#d7f57c"); fg.setAttribute("stroke-width", "3");
    fg.setAttribute("stroke-linecap", "round");
    fg.setAttribute("stroke-dasharray", (c * part).toFixed(2) + " " + c.toFixed(2));
    fg.setAttribute("transform", "rotate(-90 10 10)");
    svg.appendChild(bg); svg.appendChild(fg);
    return svg;
  }

  // ───────────── изменение к прошлой неделе (как в «Картине дня») ─────────────
  function ratioText(n) {
    if (n % 1 === 0 || lang() !== "ru") return tr("akim.delta.ratio", { n: n });
    var probe = tr("akim.delta.ratio", { n: 2 });
    return probe.indexOf(num(2)) >= 0 ? probe.replace(num(2), num(n)) : tr("akim.delta.ratio", { n: n });
  }
  function deltaText(ch) {
    if (!ch || ch.trend === "flat" || ch.trend == null) return tr("akim.delta.same");
    if (ch.mode === "new") return tr("akim.delta.new");
    if (ch.mode === "ratio") return ratioText(ch.ratio) + tr("board.delta.vs_week");
    var v = ch.mode === "pct" ? (I() && I().formatPercent ? I().formatPercent(ch.pct) : num(ch.pct) + " %") : num(ch.abs);
    return tr(ch.trend === "up" ? "akim.delta.more" : "akim.delta.less", { v: v }) + tr("board.delta.vs_week");
  }

  // ───────────── модуль ─────────────
  function mount(rootEl, options) {
    var opts = {};
    Object.keys(DEFAULTS).forEach(function (k) { opts[k] = options && options[k] != null ? options[k] : DEFAULTS[k]; });
    var params = new URLSearchParams(root.location.search);
    var state = {
      district: DISTRICTS.indexOf(params.get("district")) >= 0 ? params.get("district") : null,
      data: null, lastOk: 0, status: "loading", slide: 0, slideId: null,
      paused: false, hover: false, focus: false, timers: {}, request: 0, destroyed: false,
    };
    rootEl.classList.add("sc");
    if (/[?&]glass=off(&|$)/.test(root.location.search)) rootEl.setAttribute("data-glass", "off");
    rootEl.setAttribute("data-state", "loading");
    rootEl.setAttribute("aria-busy", "true");

    // Постоянный каркас: части обновляются на месте, страница не мигает при новых числах.
    var parts = {};
    parts.head = h("header", { class: "sc-head" });
    parts.crisis = h("section", { class: "sc-crisis", hidden: true, "aria-live": "polite" });
    parts.kpis = h("section", { class: "sc-kpis" });
    parts.pulse = h("section", { class: "sc-card sc-glass sc-pulse", "aria-labelledby": "sc-pulse-title" });
    parts.hot = h("section", { class: "sc-card sc-glass sc-hot", "aria-labelledby": "sc-hot-title" });
    parts.stage = h("section", { class: "sc-card sc-glass sc-stage", "aria-roledescription": "carousel" });
    parts.tabs = h("div", { class: "sc-tabs", role: "tablist" });
    parts.slide = h("div", { class: "sc-slide-host", id: "sc-slide-host", "aria-live": "off" });
    parts.stage.replaceChildren(parts.tabs, parts.slide);
    parts.all = h("div", { class: "sc-all" });
    parts.foot = h("footer", { class: "sc-foot" });
    parts.state = h("div", { class: "sc-state", role: "status" });
    var layout = h("div", { class: "sc-layout" }, [
      parts.head, parts.crisis, parts.kpis,
      h("div", { class: "sc-main" }, [h("div", { class: "sc-col" }, [parts.pulse, parts.hot]), parts.stage, parts.all]),
      parts.foot,
    ]);
    rootEl.replaceChildren(layout, parts.state);

    // ── шапка: собирается один раз, дальше меняются только тексты (список районов не закрывается при обновлении) ──
    var head = {
      scope: h("p", { class: "sc-scope" }),
      title: h("h1", { class: "sc-title" }),
      demo: h("span", { class: "sc-badge", hidden: true }),
      clock: h("time", { class: "sc-time" }),
      date: h("span", { class: "sc-date" }),
      select: h("select", { class: "sc-select", onchange: function (e) { setDistrict(e.target.value || null); } }),
      langs: ["kk", "ru"].map(function (l) {
        return h("button", { type: "button", lang: l, "data-lang": l,
          onclick: function () { if (I() && I().setLang) I().setLang(l); } });
      }),
    };
    head.brand = h("a", { class: "sc-brand", href: opts.homeHref }, [
      h("span", { class: "sc-mark", "aria-hidden": "true", text: "B" }), h("span", {}, [head.title, head.scope])]);
    head.seg = h("div", { class: "sc-seg", role: "group" }, head.langs);
    parts.head.replaceChildren(head.brand, h("div", { class: "sc-head__end" }, [
      head.demo, head.select,
      h("div", { class: "sc-clock" }, [h("span", { class: "sc-live", "aria-hidden": "true" }), head.clock, head.date]),
      head.seg,
    ]));
    parts.clock = head.clock;
    parts.date = head.date;
    function renderHead() {
      var d = state.data;
      head.title.textContent = tr("board.title");
      head.scope.textContent = state.district ? tr("board.scope.district", { name: districtName(state.district) }) : tr("board.scope.city");
      head.brand.setAttribute("aria-label", tr("board.home"));
      head.demo.hidden = !(d && d.demo && d.demo.any);
      head.demo.textContent = tr("common.demo");
      head.demo.title = tr("board.foot.demo");
      head.select.setAttribute("aria-label", tr("board.district.label"));
      if (doc.activeElement !== head.select) {
        head.select.replaceChildren.apply(head.select, [h("option", { value: "", text: tr("board.scope.city") })].concat(
          DISTRICTS.map(function (id) { return h("option", { value: id, text: districtName(id) }); })));
        head.select.value = state.district || "";
      }
      head.seg.setAttribute("aria-label", tr("common.lang.label"));
      head.langs.forEach(function (b) {
        b.textContent = tr("common.lang." + b.getAttribute("data-lang"));
        b.setAttribute("aria-pressed", String(lang() === b.getAttribute("data-lang")));
      });
      tickClock();
    }
    function tickClock() {
      if (!parts.clock) return;
      var now = Date.now();
      parts.clock.textContent = clockText(now);
      parts.date.textContent = longDate(now);
    }

    // ── кризис (баннер) ──
    function renderCrisis(d) {
      var c = d.crisis || {};
      var list = c.available ? c.active || [] : [];
      rootEl.setAttribute("data-crisis", list.length ? "yes" : "no");
      if (!list.length) { parts.crisis.hidden = true; parts.crisis.replaceChildren(); return; }
      var x = list[0];
      var zone = x.zone && x.zone.district ? pick(x.zone, "district") : tr("board.crisis.zone_city");
      var meta = tr("board.crisis.meta", { time: timeOf(x.started_at), done: x.tasks.done, total: x.tasks.total, services: (x.services || []).length });
      if (x.last_update) meta += " · " + tr("board.crisis.updated", { time: timeOf(x.last_update.at) });
      if (list.length > 1) meta += " · " + tr("board.crisis.more", { n: list.length - 1 });
      parts.crisis.hidden = false;
      fill(parts.crisis, [
        h("span", { class: "sc-crisis__mark", "aria-hidden": "true" }, [icon("alert")]),
        h("div", { class: "sc-crisis__text" }, [
          h("p", { class: "sc-crisis__title", text: tr("board.crisis.title", { title: pick(x, "title"), zone: zone }) }),
          h("p", { class: "sc-crisis__meta", text: meta }),
        ]),
        demoTag(x.demo),
        h("a", { class: "sc-btn sc-btn--danger", href: x.link }, [tr("board.crisis.open")]),
      ]);
    }

    // ── числа ──
    var KPI = [
      { id: "new_day", label: "board.kpi.new_day", color: "#ef9f27", bad: true },
      { id: "in_progress", label: "board.kpi.in_progress", color: "#b9c4bf", bad: null },
      { id: "overdue", label: "board.kpi.overdue", color: "#ff8478", bad: true },
      { id: "fixed_week", label: "board.kpi.fixed", color: "#8fd46c", bad: false },
    ];
    function kpiNote(k, d) {
      var all = d.kpi;
      if (k.id === "new_day" && all.new_week && all.new_week.value != null) return [tr("board.kpi.week", { n: all.new_week.value }), true];
      if (k.id === "in_progress" && all.in_progress.waiting != null) return [tr("board.kpi.waiting", { n: all.in_progress.waiting }), true];
      if (k.id === "overdue") return [tr("board.kpi.overdue_hint"), true];
      if (k.id === "fixed_week") {
        if (all.verification_available) return [tr("board.kpi.verified", { n: all.fixed_week.verified || 0 }), false];
        return [tr("board.kpi.reported"), true];
      }
      return ["", true];
    }
    function renderKpis(d) {
      var tiles = KPI.map(function (k) {
        var v = d.kpi[k.id] || {};
        var note = kpiNote(k, d);
        var valueEl = h("p", { class: "sc-kpi__value sc-num", "data-kpi": k.id, "data-zero": String(!v.value) });
        setNumber(valueEl, v.value);
        return h("article", { class: "sc-kpi sc-glass sc-kpi--" + k.id.replace("_week", "").replace("_day", "") }, [
          h("p", { class: "sc-kpi__label", text: tr(k.label) }),
          valueEl,
          h("p", { class: "sc-kpi__delta", "data-trend": v.trend || "flat", "data-bad": String(k.bad === true && v.trend === "up"), text: deltaText(v) }),
          note[0] ? h("p", { class: "sc-kpi__note" + (note[1] ? " sc-kpi__note--muted" : ""), text: note[0] }) : null,
          sparkline(v.series, k.color),
        ]);
      });
      parts.kpis.setAttribute("aria-label", tr("board.title"));
      parts.kpis.replaceChildren.apply(parts.kpis, tiles);
    }
    // Живые числа: новое значение «досчитывается» от прежнего за 600 мс (при reduced motion — сразу).
    var shown = {};
    function setNumber(el, value) {
      var key = el.getAttribute("data-kpi") || el.getAttribute("data-num");
      var to = Number(value) || 0;
      var from = key && shown[key] != null ? shown[key] : to;
      if (key) shown[key] = to;
      if (from === to || reducedMotion()) { el.textContent = value == null ? "—" : num(to); return; }
      var start = null;
      el.textContent = num(from);
      function step(ts) {
        if (start == null) start = ts;
        var t = Math.min(1, (ts - start) / TWEEN_MS), e = 1 - Math.pow(1 - t, 3);
        el.textContent = num(Math.round(from + (to - from) * e));
        if (t < 1 && el.isConnected) root.requestAnimationFrame(step);
      }
      root.requestAnimationFrame(step);
    }

    // ── пульс ──
    function alarmText(a) {
      var cat = a.category ? catName(a.category) : "";
      var dist = a.district ? districtName(a.district) : "";
      var place = a.target ? pick(a.target, "label") : "";
      var base = a.base >= 3 ? Math.round(a.base) : a.base;
      if (a.kind === "spike") return [tr("akim.pulse.spike", { category: cat, district: dist, k: num(a.k) }), tr("akim.pulse.reason.spike", { n: a.value, base: num(base) })];
      if (a.kind === "spike_new") return [tr("akim.pulse.spike_new", { category: cat, district: dist }), tr("akim.pulse.reason.spike_new", { n: a.value })];
      if (a.kind === "spike_city") {
        var names = (a.districts || []).slice(0, 3).map(function (x) { return districtName(x.district) + " — " + num(x.value); });
        return [tr("akim.pulse.spike_city", { category: cat, n: (a.districts || []).length, k: num(a.k) }), tr("akim.pulse.reason.city", { list: names.join(", ") })];
      }
      if (a.kind === "new_hot") return [tr("akim.pulse.new_hot", { place: place }), tr("akim.pulse.reason.new_hot", { n: a.value })];
      return [tr("akim.pulse.metoo_growth", { place: place, n: a.value }), tr("akim.pulse.reason.metoo", { n: a.prev || 0 })];
    }
    // Одна главная кнопка на экран (VISUAL_BRIEF §2 п. 3): идёт кризис — кнопка штаба только в баннере, у тревоги
    // того же штаба — тихая пометка; кризиса нет — кнопка «Открыть кризисный штаб» (создать) у первой такой тревоги.
    function alarmAction(a, d) {
      if (!a.crisis) return null;
      var banner = d.crisis && d.crisis.available && (d.crisis.active || [])[0];
      if (banner && a.crisis.incident === banner.id) return h("span", { class: "sc-tag sc-tag--plain", text: tr("board.crisis.in_hq") });
      var first = (d.pulse.items || []).filter(function (x) { return x.crisis; })[0];
      if (banner || first !== a) return h("a", { class: "sc-tag sc-tag--plain", href: a.crisis.link, text: tr("board.crisis.open") });
      return h("a", { class: "sc-btn sc-btn--danger", href: a.crisis.link }, [tr("board.crisis.open")]);
    }
    function renderPulse(d) {
      var p = d.pulse || {};
      var items = p.available ? p.items || [] : [];
      var limit = root.innerHeight >= 1000 ? 3 : 2;
      var more = h("p", { class: "sc-card__meta" });
      var head = h("div", { class: "sc-card__head" }, [h("h2", { class: "sc-card__title", id: "sc-pulse-title" }, [
        h("span", { class: "sc-live", "aria-hidden": "true" }), tr("board.pulse.title")]), more]);
      if (!items.length) {
        parts.pulse.replaceChildren(head, h("p", { class: "sc-empty", text: p.available === false ? tr("board.nodata") : tr("akim.pulse.none") }));
        return;
      }
      var list = h("ul", { class: "sc-alarms", "data-fit": "" }, items.slice(0, limit).map(function (a) {
        var txt = alarmText(a);
        return h("li", { class: "sc-alarm", "data-kind": a.kind }, [
          h("span", { class: "sc-alarm__icon", "aria-hidden": "true" }, [icon(a.kind === "new_hot" || a.kind === "spike_new" ? "pin" : a.kind === "metoo" ? "users" : "chart")]),
          h("p", { class: "sc-alarm__title", text: txt[0] }),
          h("div", { class: "sc-alarm__row" }, [
            h("p", { class: "sc-alarm__reason", text: txt[1] }),
            alarmAction(a, d),
          ]),
        ]);
      }));
      fill(parts.pulse, [head, list]);
      // Пульс берёт сколько нужно, но не больше 55 % колонки; остальное — «Горячим местам» (подгонка ниже).
      var col = parts.pulse.parentNode;
      parts.pulse.style.maxHeight = narrow() || !col ? "" : Math.floor(col.clientHeight * 0.55) + "px";
      fit(parts.pulse);
      var hidden = items.length - list.children.length;
      more.textContent = hidden > 0 ? tr("akim.pulse.more", { n: hidden }) : "";
      more.hidden = hidden <= 0;
    }

    // ── горячие места ──
    function hotRows(items, limit) {
      // Одна строка на место: число людей (цвет уровня + число) · место · тема и район — как на карте за 7 дней.
      return h("ol", { class: "sc-rows", "data-fit": "" }, items.slice(0, limit).map(function (it) {
        var sub = [it.category ? catName(it.category) : null, it.district ? districtName(it.district) : null].filter(Boolean).join(" · ");
        return h("li", { class: "sc-row sc-row--line" }, [
          h("span", { class: "sc-pin", "data-level": String(it.level || 0) }, [num(it.count)]),
          h("p", { class: "sc-row__title", text: pick(it.target, "label") || sub }),
          h("p", { class: "sc-row__end", text: sub }),
        ]);
      }));
    }
    function renderHot(d) {
      var hot = d.hot || {};
      var head = h("div", { class: "sc-card__head" }, [
        h("h2", { class: "sc-card__title", id: "sc-hot-title", text: tr("akim.hot.title") }),
        h("p", { class: "sc-card__meta", text: tr("board.hot.meta") }),
      ]);
      var items = hot.available ? hot.items || [] : [];
      parts.hot.replaceChildren(head, items.length ? hotRows(items, 5) : h("p", { class: "sc-empty", text: tr("board.nodata") }));
      fit(parts.hot);
    }

    // ── слайды ──
    var SLIDES = {
      crisis: { title: function () { return tr("board.slide.crisis"); }, render: slideCrisis },
      services: { title: function () { return tr("board.slide.services"); }, render: slideServices },
      decisions: { title: function () { return tr("board.slide.decisions"); }, render: slideDecisions },
      together: { title: function () { return tr("board.slide.together"); }, render: slideTogether },
      meetings: { title: function () { return tr("board.slide.meetings"); }, render: slideMeetings },
      forecast: { title: function (d) { return tr(d.forecast && d.forecast.horizon === "week" ? "board.slide.forecast_week" : "board.slide.forecast_month"); }, render: slideForecast },
      topics: { title: function () { return tr("board.slide.topics"); }, render: slideTopics },
      districts: { title: function () { return tr("board.slide.districts"); }, render: slideDistricts },
    };
    function demoTag(flag) {
      var d = state.data, whole = d && d.demo && d.demo.complaints;  // жалобы — пример: пометка в шапке говорит за всё
      return flag && !whole ? h("span", { class: "sc-badge", text: tr("common.demo") }) : null;
    }
    function stat(value, label, mod, key) {
      var v = h("p", { class: "sc-stat__value sc-num", "data-num": key || null });
      if (key) setNumber(v, value); else v.textContent = value == null ? "—" : num(value);
      return h("div", { class: "sc-stat" + (mod ? " sc-stat--" + mod : "") }, [v, h("p", { class: "sc-stat__label", text: label })]);
    }

    function slideCrisis(d) {
      var x = (d.crisis.active || [])[0];
      var zone = x.zone && x.zone.district ? pick(x.zone, "district") : tr("board.crisis.zone_city");
      var part = x.tasks.total ? x.tasks.done / x.tasks.total : 0;
      return [
        h("p", { class: "sc-row__title", text: pick(x, "title") + " · " + zone + " · " + tr("board.crisis.since", { time: timeOf(x.started_at) }) }),
        h("div", { class: "sc-progress-row" }, [
          h("span", { class: "sc-note", text: tr("board.crisis.tasks_done", { done: x.tasks.done, total: x.tasks.total }) }),
          h("div", { class: "sc-progress", role: "img", "aria-label": x.tasks.done + "/" + x.tasks.total }, [
            h("span", { style: "transform: scaleX(" + part.toFixed(3) + ")" })]),
        ]),
        h("div", { class: "sc-chips", "data-fit": "" }, (x.services || []).slice(0, 8).map(function (s) {
          return h("span", { class: "sc-chip", "data-done": String(s.done === s.total) }, [ring(s.done, s.total),
            lang() === "kk" ? s.kk : s.ru, " ", h("span", { class: "sc-num", text: num(s.done) + "/" + num(s.total) })]);
        })),
        x.last_update ? h("div", { class: "sc-update" }, [
          h("p", { class: "sc-update__time", text: tr("board.crisis.last") + " · " + timeOf(x.last_update.at) }),
          h("p", { class: "sc-update__text", text: pick(x.last_update, "text") }),
        ]) : null,
      ];
    }
    function slideServices(d) {
      var s = d.services;
      var lag = s.lagging || [];
      var rows = (s.items || []).slice().sort(function (a, b) {
        var la = lag.indexOf(a.service), lb = lag.indexOf(b.service);
        if ((la >= 0) !== (lb >= 0)) return la >= 0 ? -1 : 1;
        if (la >= 0) return la - lb;
        return (b.overdue || 0) - (a.overdue || 0) || (b.open || 0) - (a.open || 0);
      });
      var max = Math.max.apply(null, rows.map(function (r) { return r.overdue || 0; }).concat([1]));
      var limit = root.innerHeight >= 1000 ? 9 : 7;
      var head = h("div", { class: "sc-trow sc-trow--head" }, [
        h("span", { text: tr("board.services.name") }), h("span", { class: "sc-trow__num", text: tr("board.services.open") }),
        h("span", { text: tr("board.services.overdue") }), h("span", { class: "sc-trow__num", text: tr("board.services.median") }),
        h("span", { class: "sc-trow__num", text: tr("board.services.verified") }),
      ]);
      var table = h("div", { class: "sc-table", role: "table", "data-fit": "" }, [head].concat(rows.slice(0, limit).map(function (r) {
        return h("div", { class: "sc-trow", role: "row", "data-lagging": String(lag.indexOf(r.service) >= 0) }, [
          h("span", { class: "sc-trow__name", text: lang() === "kk" ? r.kk : r.ru }),
          h("span", { class: "sc-trow__num", text: r.open == null ? "—" : num(r.open) }),
          h("span", { class: "sc-bar" }, [
            h("span", { class: "sc-bar__track" }, [h("span", { class: "sc-bar__fill", style: "transform: scaleX(" + ((r.overdue || 0) / max).toFixed(3) + ")" })]),
            h("span", { class: "sc-bar__num", text: r.overdue == null ? "—" : num(r.overdue) }),
          ]),
          h("span", { class: "sc-trow__num", text: r.median_answer_days == null ? "—" : num(r.median_answer_days) }),
          h("span", { class: "sc-trow__num", text: r.verified_share == null ? "—" : pct(r.verified_share) }),
        ]);
      })));
      var foot = [];
      if (s.joint && s.joint.open != null) foot.push(tr("board.services.joint", { n: s.joint.open }));
      if (s.handoffs && s.handoffs.week != null) foot.push(tr("board.services.handoffs", { n: s.handoffs.week }));
      return [table, foot.length ? h("p", { class: "sc-note", text: foot.join(" · ") }) : null,
        lag.length ? h("p", { class: "sc-note sc-note--muted", text: tr("board.services.lagging") }) : null];
    }
    function slideDecisions(d) {
      var items = (d.decisions.items || []).slice(0, 3);
      return [h("ol", { class: "sc-rows", "data-fit": "" }, items.map(function (it) {
        var opt = (it.options || []).map(function (o) { return tr("board.decisions.option", { n: o.n, text: lang() === "kk" ? o.kk : o.ru }); });
        var sub = [it.place ? it.place[lang()] || it.place.ru : null, it.overdue_by ? tr("board.decisions.overdue", { n: it.overdue_by }) : null].filter(Boolean).join(" · ");
        return h("li", { class: "sc-row" }, [
          h("span", { class: "sc-alarm__icon", "aria-hidden": "true" }, [icon("alert")]),
          h("div", { class: "sc-row__main" }, [
            h("p", { class: "sc-row__title", text: pick(it, "problem") }),
            h("p", { class: "sc-row__sub", text: sub }),
            opt.length ? h("p", { class: "sc-row__sub", text: opt.join(" · ") }) : null,
          ]),
          it.demo ? h("span", { class: "sc-row__end", text: tr("common.demo") }) : null,
        ]);
      })), h("p", { class: "sc-note sc-note--muted", text: tr("board.decisions.where") })];
    }
    function slideTogether(d) {
      var t = d.together, c = t.counts || {};
      var stats = [stat(c.done || 0, tr("board.together.done"), "ok", "tg-done"), stat(c.joined || 0, tr("board.together.joined"), null, "tg-joined")];
      if (t.verified_week != null) stats.push(stat(t.verified_week, tr("board.together.verified"), "ok", "tg-verified"));
      var y = t.yard_of_week;
      var yard = y ? h("div", { class: "sc-yard" }, [
        h("span", { class: "sc-yard__icon", "aria-hidden": "true" }, [icon("home")]),
        h("p", { class: "sc-yard__title", text: tr("board.together.yard") + ": " + (pick(y, "label") || "") }),
        h("p", { class: "sc-yard__meta", text: [y.initiative ? y.initiative.title : null,
          y.initiative ? tr("board.together.people", { n: y.initiative.joined }) : null,
          y.members != null ? tr("board.together.members", { n: y.members }) : null].filter(Boolean).join(" · ") }),
      ]) : null;
      var rows = h("ol", { class: "sc-rows", "data-fit": "" }, (t.top || []).slice(0, 3).map(function (it) {
        var when = it.status === "done" ? tr("board.together.done_tag") : shortDate(it.starts_at);
        return h("li", { class: "sc-row" }, [
          h("span", { class: "sc-pin", "data-level": "0", "aria-hidden": "true" }, [icon(it.status === "done" ? "check" : "users")]),
          h("div", { class: "sc-row__main" }, [
            h("p", { class: "sc-row__title", lang: it.lang === "kk" ? "kk" : it.lang === "ru" ? "ru" : null, text: it.title }),
            h("p", { class: "sc-row__sub", text: [pick(it, "place"), when, tr("board.together.people", { n: it.joined })].filter(Boolean).join(" · ") }),
          ]),
          it.supported ? h("span", { class: "sc-tag", text: tr("board.together.supported") }) : null,
        ]);
      }));
      return [h("div", { class: "sc-stats" }, stats), yard, rows];
    }
    function slideMeetings(d) {
      var m = d.meetings, c = m.counts || {};
      var stats = h("div", { class: "sc-stats" }, [
        stat(c.done || 0, tr("board.meetings.done"), "ok", "mt-done"),
        stat((c.todo || 0) + (c.in_progress || 0), tr("board.meetings.in_work"), null, "mt-work"),
        stat(c.overdue || 0, tr("board.meetings.overdue"), c.overdue ? "danger" : null, "mt-overdue"),
      ]);
      var rows = h("ol", { class: "sc-rows", "data-fit": "" }, (m.orders || []).slice(0, 4).map(function (o) {
        var st = o.overdue ? "overdue" : o.status;
        return h("li", { class: "sc-row" }, [
          statusIcon(st),
          h("div", { class: "sc-row__main" }, [
            h("p", { class: "sc-row__title", text: pick(o, "text") }),
            h("p", { class: "sc-row__sub", text: [lang() === "kk" ? o.kk : o.ru, o.due ? tr("board.meetings.due", { date: shortDate(o.due) }) : null].filter(Boolean).join(" · ") }),
          ]),
          o.demo ? h("span", { class: "sc-row__end", text: tr("common.demo") }) : null,
        ]);
      }));
      var next = m.next ? h("p", { class: "sc-note", text: tr("board.meetings.next", { date: dayTime(m.next.at), title: pick(m.next, "title") }) +
        (m.next.registered ? " · " + tr("board.meetings.registered", { n: m.next.registered }) : "") }) : null;
      return [stats, rows, next];
    }
    function slideForecast(d) {
      var f = d.forecast;
      var rows = h("ol", { class: "sc-rows", "data-fit": "" }, (f.items || []).slice(0, 5).map(function (it, i) {
        return h("li", { class: "sc-row" }, [
          h("span", { class: "sc-pin", "data-level": it.level === "high" ? "3" : it.level === "medium" ? "2" : "1" }, [num(i + 1)]),
          h("div", { class: "sc-row__main" }, [
            h("p", { class: "sc-row__title", text: pick(it, "label") || districtName(it.district) }),
            h("p", { class: "sc-row__sub", text: [it.district ? districtName(it.district) : null, pick(it, "reason")].filter(Boolean).join(" · ") }),
          ]),
          it.level ? h("span", { class: "sc-row__end", text: tr("board.forecast.level." + it.level) }) : null,
        ]);
      }));
      return [rows, h("p", { class: "sc-note sc-note--muted", text: pick(f, "method") || tr("board.forecast.note") })];
    }
    function barRows(items, label, mod) {
      var max = Math.max.apply(null, items.map(function (r) { return r.value || 0; }).concat([1]));
      return h("div", { class: "sc-table", "data-fit": "" }, items.map(function (r) {
        return h("div", { class: "sc-trow", style: "grid-template-columns: minmax(0, 2.4fr) minmax(0, 3fr) minmax(0, 2fr)" }, [
          h("span", { class: "sc-trow__name", text: label(r) }),
          h("span", { class: "sc-bar" }, [
            h("span", { class: "sc-bar__track" }, [h("span", { class: "sc-bar__fill " + mod, style: "transform: scaleX(" + ((r.value || 0) / max).toFixed(3) + ")" })]),
            h("span", { class: "sc-bar__num", text: num(r.value || 0) }),
          ]),
          h("span", { class: "sc-trow__num", "data-trend": r.trend, text: r.trend === "flat" ? tr("akim.delta.same") : deltaText(r).replace(tr("board.delta.vs_week"), "") }),
        ]);
      }));
    }
    function slideTopics(d) {
      var items = (d.topics.items || []).slice(0, root.innerHeight >= 1000 ? 8 : 6);
      return [barRows(items, function (r) { return catName(r.category) || r[lang()] || r.ru; }, "sc-bar__fill--heat"),
        h("p", { class: "sc-note sc-note--muted", text: tr("board.topics.meta") })];
    }
    function slideDistricts(d) {
      var sel = d.districts.selected;
      var items = (d.districts.items || []).filter(function (r) { return r.value || r.prev; });
      if (!items.length) items = d.districts.items || [];
      return [barRows(items, function (r) { return districtName(r.district) + (r.district === sel ? " ●" : ""); }, "sc-bar__fill--heat"),
        h("p", { class: "sc-note sc-note--muted", text: tr("board.topics.meta") })];
    }

    function slideIds() {
      var d = state.data;
      return (d && d.slides || []).filter(function (id) { return SLIDES[id]; });
    }
    function slideNode(id, d, index, total) {
      var spec = SLIDES[id];
      var block = d[id] || {};
      var title = spec.title(d);
      var badge = id === "forecast" ? h("span", { class: "sc-badge sc-badge--proto", text: tr("board.prototype") }) : demoTag(block.demo);
      return h("div", { class: "sc-slide", role: "group", "aria-roledescription": "slide", "data-slide": id,
        "aria-label": tr("board.slide.of", { i: index + 1, n: total }) + ": " + title }, [
        h("div", { class: "sc-card__head" }, [h("h2", { class: "sc-card__title", text: title }),
          h("span", { class: "sc-card__end" }, [badge, h("span", { class: "sc-card__meta sc-num", text: (index + 1) + " / " + total })])]),
        h("div", { class: "sc-slide__body" }, spec.render(d)),
      ]);
    }
    function renderStage() {
      var d = state.data, ids = slideIds();
      if (!ids.length) {
        parts.slide.replaceChildren(h("p", { class: "sc-empty", text: tr("board.nodata") }));
        parts.tabs.replaceChildren();
        return;
      }
      var i = state.slideId ? ids.indexOf(state.slideId) : -1;
      if (i < 0) i = Math.min(state.slide, ids.length - 1);
      state.slide = i; state.slideId = ids[i];
      parts.stage.setAttribute("aria-label", tr("board.title"));
      parts.slide.replaceChildren(slideNode(ids[i], d, i, ids.length));
      fit(parts.slide.querySelector(".sc-slide__body"));
      // Узкий экран: все блоки подряд, без автосмены.
      parts.all.replaceChildren.apply(parts.all, narrow() ? ids.map(function (id, k) {
        return h("section", { class: "sc-card sc-glass" }, [slideNode(id, d, k, ids.length)]);
      }) : []);
      renderTabs();
    }
    function renderTabs() {
      var ids = slideIds();
      parts.tabs.setAttribute("aria-label", tr("board.title"));
      parts.tabs.replaceChildren.apply(parts.tabs, ids.map(function (id, i) {
        var title = SLIDES[id].title(state.data);
        return h("button", { type: "button", class: "sc-tab", role: "tab", "aria-selected": String(i === state.slide),
          "data-past": String(i < state.slide), "aria-controls": "sc-slide-host", tabindex: i === state.slide ? "0" : "-1",
          "aria-label": title, title: title, onclick: function () { go(i, true); } }, [h("span", { class: "sc-tab__bar", "aria-hidden": "true" })]);
      }));
    }

    // ── низ: пауза, подсказка клавиш, «обновлено», весь экран — тоже постоянные ──
    parts.pause = h("button", { type: "button", class: "sc-btn sc-btn--icon sc-pause", onclick: function () { setPaused(!state.paused); } });
    parts.updated = h("span", { class: "sc-updated", "aria-live": "off" });
    parts.footDemo = h("span", { hidden: true });
    parts.keys = h("span", { class: "sc-foot__keys" });
    parts.full = doc.fullscreenEnabled ? h("button", { type: "button", class: "sc-btn sc-btn--icon sc-full", onclick: toggleFull }, [glyph("expand")]) : null;
    parts.foot.replaceChildren.apply(parts.foot, [parts.pause, parts.keys, h("span", { class: "sc-foot__gap" }),
      h("div", { class: "sc-foot__end" }, [parts.footDemo, parts.updated]), parts.full].filter(Boolean));
    function renderFoot() {
      var d = state.data;
      parts.tabs.setAttribute("aria-label", tr("board.title"));
      parts.footDemo.hidden = true;
      parts.keys.textContent = tr("board.foot.keys");
      if (parts.full) { parts.full.setAttribute("aria-label", tr("board.foot.fullscreen")); parts.full.title = tr("board.foot.fullscreen"); }
      syncPause();
      syncUpdated();
      renderTabs();
    }
    function syncPause() {
      if (!parts.pause) return;
      var label = tr(state.paused ? "board.foot.play" : "board.foot.pause");
      parts.pause.replaceChildren(glyph(state.paused ? "play" : "pause"));
      parts.pause.setAttribute("aria-label", label);
      parts.pause.setAttribute("title", label);
      parts.pause.setAttribute("aria-pressed", String(state.paused));
      rootEl.setAttribute("data-paused", isHeld() ? "yes" : "no");
    }
    function syncUpdated() {
      if (!parts.updated || !state.lastOk) return;
      var stale = Date.now() - state.lastOk > STALE_MS || state.status === "stale";
      rootEl.setAttribute("data-stale", stale ? "yes" : "no");
      parts.updated.textContent = tr(stale ? "board.foot.stale" : "board.foot.updated", { time: clockText(state.lastOk) });
    }

    // ── автосмена блоков ──
    function rotateMs() {
      var s = state.data && state.data.rotate_s;
      return (s >= 5 && s <= 120 ? s : 15) * 1000;
    }
    function isHeld() { return state.paused || state.hover || state.focus; }
    function schedule() {
      clearTimeout(state.timers.rotate);
      rootEl.style.setProperty("--sc-rotate", rotateMs() / 1000 + "s");
      if (isHeld() || narrow() || slideIds().length < 2) return;
      state.timers.rotate = setTimeout(function () { go(state.slide + 1, false); }, rotateMs());
    }
    function go(i, byUser) {
      var ids = slideIds();
      if (!ids.length) return;
      state.slide = (i + ids.length) % ids.length;
      state.slideId = ids[state.slide];
      parts.slide.replaceChildren(slideNode(ids[state.slide], state.data, state.slide, ids.length));
      fit(parts.slide.querySelector(".sc-slide__body"));
      renderTabs();
      if (byUser) {
        var tab = parts.tabs && parts.tabs.children[state.slide];
        if (tab && parts.tabs.contains(doc.activeElement)) tab.focus();
      }
      schedule();
    }
    function setPaused(p) { state.paused = p; syncPause(); schedule(); }

    // ── загрузка ──
    function setState(s) {
      state.status = s;
      rootEl.setAttribute("data-state", s === "stale" ? "ready" : s);
      rootEl.setAttribute("aria-busy", String(s === "loading"));
    }
    function showState(kind) {
      var title, hint, action = null;
      if (kind === "loading") {
        parts.state.replaceChildren(h("span", { class: "sc-mark", "aria-hidden": "true", text: "B" }),
          h("p", { class: "sc-state__title", text: tr("board.state.loading") }), h("span", { class: "sc-skel", style: "width: 18em" }));
        parts.state.hidden = false;
        return;
      }
      if (kind === "forbidden") {
        title = tr("board.state.forbidden"); hint = tr("board.state.forbidden_hint");
        action = h("a", { class: "sc-btn sc-btn--primary", href: opts.loginHref }, [tr("board.state.login")]);
      } else if (kind === "not_ready") {
        title = tr("board.state.not_ready"); hint = tr("board.state.not_ready_hint");
        action = h("a", { class: "sc-btn", href: opts.homeHref }, [tr("board.home")]);
      } else {
        title = tr("board.state.error"); hint = tr("board.state.error_hint");
        action = h("button", { type: "button", class: "sc-btn sc-btn--primary", onclick: function () { load(true); } }, [icon("refresh"), tr("common.action.retry")]);
      }
      fill(parts.state, [h("span", { class: "sc-mark", "aria-hidden": "true", text: "B" }),
        h("h1", { class: "sc-state__title", text: title }), h("p", { class: "sc-state__hint", text: hint }), action]);
      parts.state.hidden = false;
    }
    function url() {
      return opts.apiBase + "/akim/board" + (state.district ? "?district=" + encodeURIComponent(state.district) : "");
    }
    function load(manual) {
      var id = ++state.request;
      clearTimeout(state.timers.refresh);
      clearTimeout(state.timers.skeleton);
      if (!state.data) {
        // Скелет — не раньше 150 мс: быстрый ответ не мигает заготовкой.
        state.timers.skeleton = setTimeout(function () { if (id === state.request && !state.data) showState("loading"); }, SKELETON_DELAY_MS);
      }
      var ctrl = root.AbortController ? new AbortController() : null;
      var killer = setTimeout(function () { if (ctrl) ctrl.abort(); }, opts.timeoutMs);
      fetch(url(), { headers: { Accept: "application/json" }, credentials: "same-origin", signal: ctrl ? ctrl.signal : undefined })
        .then(function (r) {
          return r.text().then(function (text) {
            var body = null;
            try { body = text ? JSON.parse(text) : null; } catch (e) { body = null; }
            return { status: r.status, body: body };
          });
        })
        .then(function (res) {
          clearTimeout(killer);
          if (id !== state.request || state.destroyed) return;
          if (res.status === 200 && res.body && res.body.kpi) {
            state.data = res.body;
            state.lastOk = Date.now();
            clearTimeout(state.timers.skeleton);
            parts.state.hidden = true;
            setState("ready");
            renderAll();
            planRefresh((res.body.refresh_s || 60) * 1000);
            return;
          }
          if (res.status === 401 || res.status === 403) { fail("forbidden"); return; }
          if (res.status === 503 || res.status === 404) { fail("not_ready", RETRY_MS * 4); return; }
          fail("error");
        })
        .catch(function () {
          clearTimeout(killer);
          if (id !== state.request || state.destroyed) return;
          fail("error");
        });
      if (manual) schedule();
    }
    function fail(kind, retryMs) {
      clearTimeout(state.timers.skeleton);
      if (state.data && kind === "error") {
        // Числа уже на экране — оставляем их и честно пишем, на какое время они (не пустой экран).
        setState("stale");
        syncUpdated();
        planRefresh(RETRY_MS);
        return;
      }
      setState(kind);
      showState(kind);
      if (kind !== "forbidden") planRefresh(retryMs || RETRY_MS);
    }
    function planRefresh(ms) {
      clearTimeout(state.timers.refresh);
      state.timers.refresh = setTimeout(function () {
        if (doc.visibilityState === "hidden") { planRefresh(ms); return; }
        load(false);
      }, ms);
    }

    function renderAll() {
      if (!state.data) return;
      renderHead();
      renderCrisis(state.data);
      renderKpis(state.data);
      renderPulse(state.data);
      renderHot(state.data);
      renderFoot();
      renderStage();
      schedule();
    }
    function rerender() {
      if (state.data) renderAll();
      else if (state.status !== "loading") showState(state.status);
      doc.title = tr("board.title") + " · Birge";
    }

    function setDistrict(id) {
      state.district = id;
      state.slideId = null; state.slide = 0;
      if (opts.syncUrl && root.history && root.history.replaceState) {
        var p = new URLSearchParams(root.location.search);
        if (id) p.set("district", id); else p.delete("district");
        root.history.replaceState(null, "", root.location.pathname + (p.toString() ? "?" + p : "") + root.location.hash);
      }
      load(true);
    }

    // ── полный экран, курсор, клавиши ──
    function toggleFull() {
      if (doc.fullscreenElement) doc.exitFullscreen && doc.exitFullscreen();
      else if (doc.documentElement.requestFullscreen) doc.documentElement.requestFullscreen().catch(function () {});
    }
    function wake() {
      doc.body.classList.remove("sc-idle");
      clearTimeout(state.timers.idle);
      state.timers.idle = setTimeout(function () { doc.body.classList.add("sc-idle"); }, IDLE_CURSOR_MS);
    }
    function onKey(e) {
      var t = e.target, tag = t && t.tagName;
      if (tag === "SELECT" || tag === "INPUT" || tag === "TEXTAREA" || e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === "ArrowRight") { go(state.slide + 1, true); e.preventDefault(); }
      else if (e.key === "ArrowLeft") { go(state.slide - 1, true); e.preventDefault(); }
      else if ((e.key === " " || e.key === "Spacebar") && (tag !== "BUTTON" && tag !== "A")) { setPaused(!state.paused); e.preventDefault(); }
      else if ((e.key === "f" || e.key === "F" || e.key === "а" || e.key === "А") && tag !== "BUTTON") { toggleFull(); }
    }
    function onEnter() { state.hover = true; syncPause(); schedule(); }
    function onLeave() { state.hover = false; syncPause(); schedule(); }
    function onFocusIn(e) {
      var t = e && e.target;
      var keyboard = !t || !t.matches || (function () { try { return t.matches(":focus-visible"); } catch (x) { return true; } })();
      if (!keyboard) return;
      state.focus = true; syncPause(); schedule();
    }
    function onFocusOut(e) {
      if (parts.stage.contains(e.relatedTarget) || parts.tabs.contains(e.relatedTarget)) return;
      if (state.focus) { state.focus = false; syncPause(); schedule(); }
    }
    function onVisible() { if (doc.visibilityState === "visible" && state.lastOk && Date.now() - state.lastOk > 60000) load(false); }
    var resizeTimer = null;
    function onResize() { clearTimeout(resizeTimer); resizeTimer = setTimeout(function () { if (state.data) renderAll(); }, 200); }

    doc.addEventListener("keydown", onKey);
    doc.addEventListener("mousemove", wake);
    doc.addEventListener("visibilitychange", onVisible);
    root.addEventListener("resize", onResize);
    parts.stage.addEventListener("mouseenter", onEnter);
    parts.stage.addEventListener("mouseleave", onLeave);
    parts.stage.addEventListener("focusin", onFocusIn);
    parts.stage.addEventListener("focusout", onFocusOut);
    parts.foot.addEventListener("focusin", function (e) { if (parts.tabs.contains(e.target)) onFocusIn(e); });
    parts.foot.addEventListener("focusout", onFocusOut);
    state.timers.clock = setInterval(function () { tickClock(); syncUpdated(); }, 1000);
    var offLang = I() && I().onChange ? I().onChange(rerender) : null;
    if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(function () { if (state.data && !state.destroyed) renderAll(); });
    wake();
    doc.title = tr("board.title") + " · Birge";
    if (I() && I().ready && I().ready.then) I().ready.then(function () { rerender(); load(false); }, function () { load(false); });
    else load(false);

    return {
      refresh: function () { load(true); },
      setLang: function (l) { if (I() && I().setLang) I().setLang(l); else rerender(); },
      destroy: function () {
        state.destroyed = true;
        Object.keys(state.timers).forEach(function (k) { clearTimeout(state.timers[k]); clearInterval(state.timers[k]); });
        doc.removeEventListener("keydown", onKey);
        doc.removeEventListener("mousemove", wake);
        doc.removeEventListener("visibilitychange", onVisible);
        root.removeEventListener("resize", onResize);
        if (typeof offLang === "function") offLang();
        doc.body.classList.remove("sc-idle");
        rootEl.replaceChildren();
      },
      _state: state,
    };
  }

  root.BirgeBoard = { mount: mount, version: "board-r15" };

  // Страница index.html: <main id="board" data-board-auto> — монтируется сама (CSP без встроенных скриптов).
  function auto() {
    var el = doc.querySelector("[data-board-auto]");
    if (el && !el.__board) el.__board = mount(el, { apiBase: el.getAttribute("data-api") || undefined });
    root.__board = el && el.__board;
  }
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", auto);
  else auto();
})(window);
