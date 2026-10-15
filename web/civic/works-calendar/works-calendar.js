/*
 * Birge · «Календарь работ» и «копаем один раз» (R12, раунд 15; CONTRACT §5.6, §7, §8; VISUAL_BRIEF п. 6, IDEA сцена 8).
 *
 *   <link rel="stylesheet" href="/civic/works-calendar/works-calendar.css">
 *   <script defer src="/civic/works-calendar/works-calendar.js"></script>
 *   BirgeWorksCalendar.mount(root, { apiBase: "/api/civic/v2", api, map, close, embedded, conflict })
 *     → { destroy(), setLang(lang), reload() }
 *   embedded: true — вкладка «Календарь работ» внутри «Ведомств» R17 (схема R11 §5.4): без своего заголовка, главная
 *   кнопка — «Добавить работу» (форма R06); conflict — id конфликта или работы, который открыть сразу.
 *
 * Данные: GET {apiBase}/works-calendar?from&to&district&service — только сотрудник (шлюз R01: сессия R02),
 * считает R12 engine/civic_geo/works_calendar.py: работы по участкам улиц графа OSM и конфликты:
 *   dig_after_surface («копаем дважды»), same_segment_overlap, parallel_closures. Совет ru/kk приходит с сервера.
 * Экран: строки по улицам, месяцы, полосы работ цвета службы (профиль R17, запасной цвет R12), красная связь между
 * конфликтующими работами с чипом; карточка выбранного конфликта с советом и одной главной кнопкой «Показать на карте» —
 * карта плавно ведёт к участкам, конфликтные участки подсвечены точно по форме улицы (рёбра OSM).
 * Оболочка R01: при загрузке файла — BirgeShell.registerScreen({id: "works-calendar", modes: ["akimat"]}) и
 * BirgeShell.registerLayer({id: "works-conflicts"}) — слой «Конфликты работ», выключен по умолчанию.
 * Тексты — ключи wcal.* и common.* словаря R11; запасные ru/kk — KEYS ниже (список для R11 — INTEGRATION.txt R12).
 * Весь текст данных выводится через textContent (без innerHTML).
 */
(function (root) {
  "use strict";

  const doc = root.document;
  const SCRIPT_BASE = ((doc.currentScript && doc.currentScript.src) || "/civic/works-calendar/works-calendar.js").replace(/[^/]*$/, "");
  const ICONS = SCRIPT_BASE + "../ui-kit/icons.svg";
  const SCREEN_ID = "works-calendar";
  const LAYER_ID = "works-conflicts";
  const DAY = 86400000;
  const LANE_H = 30;          // высота дорожки полосы: полоса 24 + зазор 6
  const ROW_PAD = 8;          // поля строки сверху и снизу
  const CHIP_LANE = 32;       // дорожка чипов конфликта над полосами строки: чип (зона 40 px) не закрывает полосу
  const HIT = 40;             // зона нажатия полосы и чипа (R10 B-111, правило ≥ 40, цель 44); видимая полоса — 24 px внутри
  const BAR_H = 24;
  const MIN_MONTH_W = 46;     // уже — месяц не читается: лента прокручивается вбок (телефон — 60)
  const SKELETON_DELAY = 150; // скелетон не раньше 150 мс (COMMON «Качество»)
  const MAP_SRC = "birge-r12-wc";
  const MAP_LAYERS = ["birge-r12-wc-casing", "birge-r12-wc-line"];  // П1: без слоя свечения — белая обводка и линия
  const MAP_PT_SRC = "birge-r12-wc-pt";   // точка конфликта на самой улице: видно, где конфликты, на масштабе города
  const MAP_DOT = "birge-r12-wc-dot";
  const DOT_MAX_ZOOM = 13.5;               // ближе — видна сама линия участка, точка не нужна
  const DANGER = "#b3362e";   // = --c-danger ui-kit: красный только у конфликта
  const PHONE = 761;

  // Ключи этого экрана, которых пока нет в словаре R11 (черновик kk — на проверку R11 и владельцу).
  const KEYS = {
    ru: {
      "wcal.title": "Календарь работ",
      "wcal.subtitle": "Работы всех служб по участкам улиц — конфликты видно до начала работ",
      "wcal.count.works": { one: "{n} работа", few: "{n} работы", many: "{n} работ" },
      "wcal.count.conflicts": { one: "{n} конфликт", few: "{n} конфликта", many: "{n} конфликтов" },
      "wcal.count.high": { one: "{n} важный", few: "{n} важных", many: "{n} важных" },
      "wcal.demo_note": "Работы придуманы, улицы — настоящие",
      "wcal.filter.district": "Район",
      "wcal.filter.all_districts": "Все районы",
      "wcal.filter.service": "Служба",
      "wcal.filter.all_services": "Все службы",
      "wcal.period.prev": "Раньше на 3 месяца",
      "wcal.period.next": "Позже на 3 месяца",
      "wcal.period.now": "К сегодняшнему дню",
      "wcal.period.label": "Период: {from} – {to}",
      "wcal.kind.dig_after_surface": "Копаем дважды",
      "wcal.kind.same_segment_overlap": "Две службы на одном участке",
      "wcal.kind.parallel_closures": "Параллельные улицы перекрыты одновременно",
      "wcal.chip.dig_after_surface": "копаем дважды",
      "wcal.chip.same_segment_overlap": "одновременно",
      "wcal.chip.parallel_closures": "нет объезда",
      "wcal.severity.high": "Важно",
      "wcal.severity.medium": "Проверить",
      "wcal.stage.surface_done": "асфальт уже уложен",
      "wcal.stage.now": "идёт сейчас",
      "wcal.stage.past": "уже прошло",
      "wcal.gap": "через {gap}",
      "wcal.overlap": { one: "{n} день вместе", few: "{n} дня вместе", many: "{n} дней вместе" },
      "wcal.of": "{i} из {n}",
      "wcal.prev_conflict": "Предыдущий конфликт",
      "wcal.next_conflict": "Следующий конфликт",
      "wcal.no_conflicts.title": "Конфликтов нет",
      "wcal.no_conflicts.text": "Работы служб в этом периоде не мешают друг другу.",
      "wcal.empty.title": "В этом периоде работ нет",
      "wcal.empty.text": "Выберите другой район, службу или период.",
      "wcal.empty.reset": "Сбросить фильтры",
      "wcal.staff.title": "Календарь работ — для сотрудников",
      "wcal.staff.text": "Войдите как сотрудник акимата — календарь откроется сам.",
      "wcal.staff.login": "Войти",
      "wcal.not_ready.title": "Календарь работ ещё не подключён",
      "wcal.not_ready.text": "В этой сборке нет модуля календаря. Остальные разделы работают.",
      "wcal.street_none": "Место не указано",
      "wcal.row.works": { one: "{n} работа", few: "{n} работы", many: "{n} работ" },
      "wcal.row.conflicts": { one: "{n} конфликт", few: "{n} конфликта", many: "{n} конфликтов" },
      "wcal.today": "сегодня",
      "wcal.work.service": "Служба",
      "wcal.work.kind": "Вид работ",
      "wcal.work.dates": "Сроки",
      "wcal.work.status": "Статус",
      "wcal.work.place": "Где",
      "wcal.work.days": { one: "{n} день", few: "{n} дня", many: "{n} дней" },
      "wcal.work.length": "участок {m} м",
      "wcal.work.context": "Показана как вторая сторона конфликта",
      "wcal.work.open": "Открыть запись",
      "wcal.work.source": "Источник",
      "wcal.real.tag": "Настоящие",
      "wcal.real.coverage": "работ из открытых источников: {n} · на участке улицы {exact} · примерно {approx}",
      "wcal.add": "Добавить работу",
      "wcal.work.delayed": "срок перенесён",
      "wcal.status.planned": "Запланировано",
      "wcal.status.in_progress": "Идут работы",
      "wcal.status.done": "Завершено",
      "wcal.status.completed": "Завершено",
      "wcal.status.unknown": "Статус не указан",
      "wcal.service_none": "Служба не указана",
      "wcal.map.back": "Вернуться в календарь",
      "wcal.map.where": "Участок по форме улицы (OpenStreetMap)",
      "wcal.layer": "Конфликты работ",
      "wcal.layer.empty": "В ближайший год конфликтов работ нет",
      "wcal.layer.staff": "Слой «Конфликты работ» — для сотрудников. Войдите как сотрудник.",
      "wcal.kind_short.dig": "Раскопка",
      "wcal.kind_short.surface": "Асфальт",
      "wcal.kind_short.closure": "Перекрытие",
      "wcal.kind_short.landscape": "Благоустройство",
      "wcal.kind_short.lighting": "Освещение",
      "wcal.kind_short.other": "Работы",
      "wcal.timeline": "Лента работ по месяцам",
      "wcal.bar.label": "{title}. {service}. {dates}",
    },
    kk: {
      "wcal.title": "Жұмыстар күнтізбесі",
      "wcal.subtitle": "Барлық қызметтердің жұмыстары көше бөліктері бойынша — қайшылық жұмыс басталғанға дейін көрінеді",
      "wcal.count.works": "{n} жұмыс",
      "wcal.count.conflicts": "{n} қайшылық",
      "wcal.count.high": "{n} маңызды",
      "wcal.demo_note": "Жұмыстар ойдан алынған, көшелер — нақты",
      "wcal.filter.district": "Аудан",
      "wcal.filter.all_districts": "Барлық аудандар",
      "wcal.filter.service": "Қызмет",
      "wcal.filter.all_services": "Барлық қызметтер",
      "wcal.period.prev": "3 ай бұрын",
      "wcal.period.next": "3 ай кейін",
      "wcal.period.now": "Бүгінгі күнге",
      "wcal.period.label": "Кезең: {from} – {to}",
      "wcal.kind.dig_after_surface": "Екі рет қазу",
      "wcal.kind.same_segment_overlap": "Бір бөлікте екі қызмет",
      "wcal.kind.parallel_closures": "Қатар көшелер бір уақытта жабылады",
      "wcal.chip.dig_after_surface": "екі рет қазу",
      "wcal.chip.same_segment_overlap": "бір уақытта",
      "wcal.chip.parallel_closures": "айналма жол жоқ",
      "wcal.severity.high": "Маңызды",
      "wcal.severity.medium": "Тексеру керек",
      "wcal.stage.surface_done": "асфальт төселіп қойды",
      "wcal.stage.now": "қазір жүріп жатыр",
      "wcal.stage.past": "өтіп кетті",
      "wcal.gap": "{gap}",
      "wcal.overlap": "{n} күн бірге",
      "wcal.of": "{n} ішінен {i}",
      "wcal.prev_conflict": "Алдыңғы қайшылық",
      "wcal.next_conflict": "Келесі қайшылық",
      "wcal.no_conflicts.title": "Қайшылық жоқ",
      "wcal.no_conflicts.text": "Бұл кезеңде қызметтердің жұмыстары бір-біріне кедергі келтірмейді.",
      "wcal.empty.title": "Бұл кезеңде жұмыс жоқ",
      "wcal.empty.text": "Басқа аудан, қызмет немесе кезең таңдаңыз.",
      "wcal.empty.reset": "Сүзгілерді тазарту",
      "wcal.staff.title": "Жұмыстар күнтізбесі — қызметкерлерге арналған",
      "wcal.staff.text": "Әкімдік қызметкері ретінде кіріңіз — күнтізбе өзі ашылады.",
      "wcal.staff.login": "Кіру",
      "wcal.not_ready.title": "Жұмыстар күнтізбесі әлі қосылмаған",
      "wcal.not_ready.text": "Бұл жинақта күнтізбе модулі жоқ. Басқа бөлімдер жұмыс істейді.",
      "wcal.street_none": "Орны көрсетілмеген",
      "wcal.row.works": "{n} жұмыс",
      "wcal.row.conflicts": "{n} қайшылық",
      "wcal.today": "бүгін",
      "wcal.work.service": "Қызмет",
      "wcal.work.kind": "Жұмыс түрі",
      "wcal.work.dates": "Мерзімі",
      "wcal.work.status": "Мәртебесі",
      "wcal.work.place": "Қайда",
      "wcal.work.days": "{n} күн",
      "wcal.work.length": "бөлік {m} м",
      "wcal.work.context": "Қайшылықтың екінші жағы ретінде көрсетілген",
      "wcal.work.open": "Жазбаны ашу",
      "wcal.work.source": "Дереккөз",
      "wcal.real.tag": "Нақты",
      "wcal.real.coverage": "ашық дереккөздердегі жұмыстар: {n} · көше бөлігінде {exact} · шамамен {approx}",
      "wcal.add": "Жұмыс қосу",
      "wcal.work.delayed": "мерзімі ауыстырылды",
      "wcal.status.planned": "Жоспарланған",
      "wcal.status.in_progress": "Жұмыс жүріп жатыр",
      "wcal.status.done": "Аяқталды",
      "wcal.status.completed": "Аяқталды",
      "wcal.status.unknown": "Мәртебесі көрсетілмеген",
      "wcal.service_none": "Қызмет көрсетілмеген",
      "wcal.map.back": "Күнтізбеге оралу",
      "wcal.map.where": "Бөлік көше пішіні бойынша (OpenStreetMap)",
      "wcal.layer": "Жұмыстар қайшылығы",
      "wcal.layer.empty": "Жақын жылы жұмыстар қайшылығы жоқ",
      "wcal.layer.staff": "«Жұмыстар қайшылығы» қабаты — қызметкерлерге арналған. Қызметкер ретінде кіріңіз.",
      "wcal.kind_short.dig": "Қазу",
      "wcal.kind_short.surface": "Асфальт",
      "wcal.kind_short.closure": "Жабу",
      "wcal.kind_short.landscape": "Абаттандыру",
      "wcal.kind_short.lighting": "Жарықтандыру",
      "wcal.kind_short.other": "Жұмыс",
      "wcal.timeline": "Жұмыстардың ай бойынша таспасы",
      "wcal.bar.label": "{title}. {service}. {dates}",
    },
  };
  // Общие ключи R11 (уже есть в словаре) — запасной текст, если словаря нет (страница стенда).
  const COMMON = {
    ru: { "common.action.show_on_map": "Показать на карте", "common.action.retry": "Повторить", "common.action.close": "Закрыть",
      "common.tag.demo": "Пример", "common.tag.approx": "Примерное место", "common.state.network_title": "Нет связи с сервером",
      "common.state.network_text": "Проверьте интернет и повторите.", "common.state.error_title": "Не получилось загрузить",
      "common.state.error_text": "Попробуйте ещё раз через минуту.", "common.state.loading": "Загрузка…" },
    kk: { "common.action.show_on_map": "Картадан көрсету", "common.action.retry": "Қайталау", "common.action.close": "Жабу",
      "common.tag.demo": "Үлгі", "common.tag.approx": "Шамамен көрсетілген орын", "common.state.network_title": "Сервермен байланыс жоқ",
      "common.state.network_text": "Интернетті тексеріп, қайталап көріңіз.", "common.state.error_title": "Жүктеу мүмкін болмады",
      "common.state.error_text": "Бір минуттан кейін қайталап көріңіз.", "common.state.loading": "Жүктелуде…" },
  };
  const MONTHS = {
    ru: ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
    kk: ["қаң", "ақп", "нау", "сәу", "мам", "мау", "шіл", "там", "қыр", "қаз", "қар", "жел"],
  };
  const MONTHS_GEN_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
  const MONTHS_KK = ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"];
  const DISTRICTS = [["almaty", "Алматы", "Алматы"], ["baikonur", "Байконур", "Байқоңыр"], ["esil", "Есиль", "Есіл"],
    ["nura", "Нура", "Нұра"], ["saraishyk", "Сарайшык", "Сарайшық"], ["saryarka", "Сарыарка", "Сарыарқа"]];

  // ------------------------------------------------------------------ тексты
  const I = () => root.BirgeI18n || null;
  function lang() {
    const i = I();
    const l = i && typeof i.getLang === "function" ? i.getLang() : (root.BirgeShell && root.BirgeShell.lang ? root.BirgeShell.lang() : "ru");
    return l === "kk" ? "kk" : "ru";
  }
  function pluralRu(n) {
    const a = Math.abs(n), m10 = a % 10, m100 = a % 100;
    if (m10 === 1 && m100 !== 11) return "one";
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "few";
    return "many";
  }
  function tr(key, params) {
    const i = I();
    if (i && typeof i.has === "function" && i.has(key)) return i.t(key, params);
    const l = lang();
    let v = (KEYS[l] && KEYS[l][key]) ?? (COMMON[l] && COMMON[l][key]) ?? KEYS.ru[key] ?? COMMON.ru[key] ?? key;
    if (v && typeof v === "object") v = v[pluralRu(Number(params && params.n) || 0)] || v.many || v.other || "";
    return String(v).replace(/\{(\w+)\}/g, (w, n) => (params && params[n] != null ? String(params[n]) : w));
  }
  // Заголовок конфликта: с сервера на языке экрана (там учтён вариант вида), иначе ключ вида.
  function conflictTitle(c) {
    return (lang() === "kk" ? c.title_kk : c.title_ru) || tr("wcal.kind." + c.kind);
  }
  function serviceName(id, svc) {
    if (!id) return tr("wcal.service_none");
    const i = I();
    if (i && i.has && i.has("service." + id)) return i.t("service." + id);
    return (svc && (lang() === "kk" ? svc.name_kk : svc.name_ru)) || id;
  }

  // ------------------------------------------------------------------ даты (календарные дни без пояса)
  const dayNum = (iso) => Math.floor(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / DAY);
  const dayDate = (n) => new Date(n * DAY);
  function fmtDay(iso, withYear) {
    const d = new Date(dayNum(iso) * DAY), m = d.getUTCMonth(), y = d.getUTCFullYear(), dd = d.getUTCDate();
    if (lang() === "kk") return (withYear ? y + " ж. " : "") + dd + " " + MONTHS_KK[m];
    return dd + " " + MONTHS_GEN_RU[m] + (withYear ? " " + y : "");
  }
  // «4–20 мая 2027» / «2027 ж. 4–20 мамыр»; разные месяцы — «20 июля – 14 августа 2027».
  function fmtRange(a, b) {
    const da = dayDate(dayNum(a)), db = dayDate(dayNum(b));
    const sameYear = da.getUTCFullYear() === db.getUTCFullYear();
    if (sameYear && da.getUTCMonth() === db.getUTCMonth()) {
      if (da.getUTCDate() === db.getUTCDate()) return fmtDay(a, true);
      return lang() === "kk"
        ? da.getUTCFullYear() + " ж. " + da.getUTCDate() + "–" + db.getUTCDate() + " " + MONTHS_KK[da.getUTCMonth()]
        : da.getUTCDate() + "–" + db.getUTCDate() + " " + MONTHS_GEN_RU[da.getUTCMonth()] + " " + da.getUTCFullYear();
    }
    if (sameYear && lang() !== "kk") return fmtDay(a, false) + " – " + fmtDay(b, true);
    if (sameYear) return da.getUTCFullYear() + " ж. " + da.getUTCDate() + " " + MONTHS_KK[da.getUTCMonth()] + " – " + db.getUTCDate() + " " + MONTHS_KK[db.getUTCMonth()];
    return fmtDay(a, true) + " – " + fmtDay(b, true);
  }
  // «сен 2026 – сен 2027» — подпись периода в группе стрелок.
  function monthSpan(a, b) {
    const da = dayDate(dayNum(a)), db = dayDate(dayNum(b));
    const m = MONTHS[lang()];
    return m[da.getUTCMonth()] + " " + da.getUTCFullYear() + " – " + m[db.getUTCMonth()] + " " + db.getUTCFullYear();
  }
  // Промежуток словами — как в совете сервера: < 45 дней — в днях, иначе в месяцах.
  function gapWords(days) {
    if (days < 45) {
      const n = Math.max(1, days);
      return lang() === "kk" ? n + " күннен кейін" : n + " " + ({ one: "день", few: "дня", many: "дней" })[pluralRu(n)];
    }
    const months = days / 30.4;
    // 45–53 дня (асфальт в мае → сети в июле) — «полтора месяца», а не «1 месяц»: так же считает движок (works.gap_words).
    if (months >= 1.25 && months < 1.75) return lang() === "kk" ? "бір жарым айдан кейін" : "полтора месяца";
    const n = Math.max(1, Math.round(months));
    return lang() === "kk" ? n + " айдан кейін" : n + " " + ({ one: "месяц", few: "месяца", many: "месяцев" })[pluralRu(n)];
  }

  // ------------------------------------------------------------------ DOM
  function h(tag, attrs, children) {
    const el = doc.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "text") el.textContent = v;
      else if (k === "class") el.className = v;
      else if (k === "style") el.style.cssText = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children || []) if (c != null && c !== false) el.append(typeof c === "string" ? doc.createTextNode(c) : c);
    return el;
  }
  function icon(name, cls) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = doc.createElementNS(NS, "svg");
    svg.setAttribute("class", "ic " + (cls || ""));
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    const use = doc.createElementNS(NS, "use");
    use.setAttribute("href", ICONS + "#i-" + name);
    svg.append(use);
    return svg;
  }
  // Подпись на полосе: белая на тёмном цвете службы, тёмная — на светлом (контраст ≥ 4.5:1 у 13 px).
  function textOn(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
    if (!m) return "#fff";
    const c = [0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
    const L = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    return (1.05) / (L + 0.05) >= 4.5 ? "#fff" : "#121a17";
  }
  // Ширина подписи полосы (13 px, 500) — по шрифту страницы; без canvas — оценка 7,5 px на знак.
  let measureCtx = null;
  function textWidth(text) {
    try {
      if (!measureCtx) {
        measureCtx = doc.createElement("canvas").getContext("2d");
        const fam = getComputedStyle(doc.body).getPropertyValue("--font").trim() || "Inter, system-ui, sans-serif";
        measureCtx.font = "500 13px " + fam;  // подписи полос — 13 px (решение владельца 12 окт: мельче 13 нет)
      }
      return measureCtx.measureText(text).width;
    } catch (e) {
      return text.length * 7.5;  // нет canvas: средняя ширина знака Inter 13 px
    }
  }
  const reducedMotion = () => !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches);

  // ------------------------------------------------------------------ данные
  function apiGet(opts, path) {
    const api = opts.api && typeof opts.api.v2 === "function" ? opts.api.v2 : null;
    if (api) return api("GET", path);
    return fetch((opts.apiBase || "/api/civic/v2") + path, { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(async (r) => {
        let body = null;
        try { body = await r.json(); } catch (e) { body = null; }
        if (!r.ok) { const err = new Error("HTTP " + r.status); err.status = r.status; err.body = body; throw err; }
        return body;
      }, () => { const err = new Error("network"); err.status = 0; throw err; });
  }
  function failKind(err) {
    const s = err && typeof err.status === "number" ? err.status : 0;
    if (s === 401 || s === 403) return "staff";
    if (s === 503) return "not_ready";
    if (s === 0) return "network";
    return "error";
  }

  // Какой конфликт открыть: BirgeWorksCalendar.openConflict(id) (палитра R01, сцена 8), opts.conflict или адрес
  // #works-calendar/<id конфликта или работы>. id работы — первый конфликт с этой работой.
  let wantedConflict = null;
  function takeWanted(data) {
    let want = wantedConflict;
    const m = /^#works-calendar\/([A-Za-z0-9._:-]{1,96})$/.exec(root.location && root.location.hash || "");
    if (!want && m) want = m[1];
    if (!want) return null;
    wantedConflict = null;
    const c = data.conflicts.find((x) => x.id === want) || data.conflicts.find((x) => x.works.includes(want));
    return c ? c.id : null;
  }

  // Общий кэш последнего ответа — слой карты рисует то же, что видел календарь (без второго запроса).
  const shared = { data: null, at: 0, pending: null };

  // ------------------------------------------------------------------ раскладка ленты
  // Диапазон ленты: период запроса, расширенный до целых месяцев всех показанных работ (вторая сторона конфликта
  // может начаться раньше периода — её полоса видна целиком, а не обрубком у края). Не длиннее 30 месяцев.
  function rangeOf(data) {
    let from = dayNum(data.period.from), to = dayNum(data.period.to);
    let lo = from, hi = to;
    for (const w of data.works) {
      if (w.starts_on) lo = Math.min(lo, dayNum(w.starts_on));
      if (w.ends_on) hi = Math.max(hi, dayNum(w.ends_on));
    }
    const a = dayDate(lo), b = dayDate(hi);
    lo = Math.floor(Date.UTC(a.getUTCFullYear(), a.getUTCMonth(), 1) / DAY);
    hi = Math.floor(Date.UTC(b.getUTCFullYear(), b.getUTCMonth() + 1, 0) / DAY);
    if (hi - lo <= 30 * 31) { from = lo; to = hi; }
    const months = [];
    for (let d = dayDate(from); d.getTime() <= to * DAY; d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1))) {
      months.push(d.toISOString().slice(0, 7));
    }
    return { from, to, months };
  }

  function layoutRows(data, range) {
    const byId = new Map(data.works.map((w) => [w.id, w]));
    const from = range.from, to = range.to;
    // Порядок строк: с важным конфликтом, затем с конфликтом, затем остальные (внутри — как прислал сервер).
    const rank = new Map();
    for (const c of data.conflicts) {
      for (const id of c.works) {
        const w = byId.get(id);
        if (!w) continue;
        const r = c.severity === "high" ? 0 : 1;
        rank.set(w.row, Math.min(rank.has(w.row) ? rank.get(w.row) : 2, r));
      }
    }
    const rows = data.rows.map((row, i) => ({ row, i, r: rank.has(row.key) ? rank.get(row.key) : 2 }))
      .sort((a, b) => a.r - b.r || a.i - b.i).map((x) => x.row);
    return rows.map((row) => {
      const works = row.works.map((id) => byId.get(id)).filter((w) => w && w.starts_on)
        .sort((a, b) => a.starts_on.localeCompare(b.starts_on) || a.id.localeCompare(b.id));
      const lanes = [];
      const placed = works.map((w) => {
        const s = Math.max(from, dayNum(w.starts_on)), e = Math.min(to, dayNum(w.ends_on || w.starts_on));
        let lane = lanes.findIndex((end) => end < s - 1);
        if (lane < 0) { lane = lanes.length; lanes.push(e); } else lanes[lane] = e;
        return { work: w, lane, s, e };
      });
      return { row, items: placed, lanes: Math.max(1, lanes.length) };
    });
  }

  // ------------------------------------------------------------------ экран
  function mount(rootEl, options) {
    const opts = Object.assign({ apiBase: "/api/civic/v2" }, options || {});
    if (opts.conflict) wantedConflict = String(opts.conflict);
    const state = {
      status: "loading", data: null, error: null, filters: { district: "", service: "" }, shift: 0,
      selected: null, popover: null, destroyed: false, seq: 0,
    };
    rootEl.classList.add("wcal", "bk-app");
    rootEl.setAttribute("data-wcal", "1");
    let skeletonTimer = null;
    let ro = null;
    let resizing = false;  // перерисовка из-за ширины листа: открытая карточка работы остаётся открытой
    let rafId = 0;

    // Хозяин вкладки сам даёт главную «Добавить работу» (рядом [data-action="add-work"], R17 «Ведомства») или просит
    // календарь без неё (addButton: false).
    function hostAdd() {
      return opts.addButton === false || !!(rootEl.parentElement && rootEl.parentElement.querySelector('[data-action="add-work"]'));
    }

    function query() {
      const p = new URLSearchParams();
      const now = new Date();
      if (state.shift) {
        // Сдвиг периода по 3 месяца от «прошлый месяц … +11». Только from (дата ГГГГ-ММ-ДД): конец сервер считает сам
        // (13 месяцев), а шлюз R01 проверяет from/to как ISO-даты и период ≤ 366 дней, если заданы оба.
        const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1 + state.shift, 1));
        p.set("from", start.toISOString().slice(0, 10));
      }
      if (state.filters.district) p.set("district", state.filters.district);
      if (state.filters.service) p.set("service", state.filters.service);
      const s = p.toString();
      return "/works-calendar" + (s ? "?" + s : "");
    }

    function load() {
      const seq = ++state.seq;
      state.status = "loading";
      clearTimeout(skeletonTimer);
      skeletonTimer = setTimeout(() => { if (state.status === "loading" && seq === state.seq) render(); }, SKELETON_DELAY);
      if (!state.data) render(true);
      apiGet(opts, query()).then((data) => {
        if (state.destroyed || seq !== state.seq) return;
        if (!data || !Array.isArray(data.works) || !Array.isArray(data.rows)) throw Object.assign(new Error("bad"), { status: 500 });
        state.data = data;
        state.status = "ready";
        state.animateLink = true;
        shared.data = data;
        shared.at = Date.now();
        const wanted = takeWanted(data);
        // Демо-мир: открыть на конфликте сцены 8 (сервер присылает scene_conflict только в режиме мира), иначе — первый
        // по срочности. Выбор пользователя при смене фильтров сохраняется.
        const scene = data.scene_conflict && data.conflicts.some((c) => c.id === data.scene_conflict) ? data.scene_conflict : null;
        if (wanted) state.selected = wanted;
        else if (!state.selected || !data.conflicts.some((c) => c.id === state.selected)) state.selected = scene || (data.conflicts[0] ? data.conflicts[0].id : null);
        render();
      }).catch((err) => {
        if (state.destroyed || seq !== state.seq) return;
        state.status = failKind(err);
        state.error = err;
        render();
        if (state.status === "staff") watchLogin();
      });
    }

    // --- шапка
    function header() {
      const d = state.data;
      const meta = h("p", { class: "wcal-meta" });
      if (d && state.status === "ready") {
        const c = d.counts || {};
        meta.append(h("span", { text: tr("wcal.count.works", { n: c.works || 0 }) }),
          h("span", { class: "wcal-dot", "aria-hidden": "true", text: "·" }),
          h("span", { class: c.conflicts ? "wcal-meta__bad" : "", text: tr("wcal.count.conflicts", { n: c.conflicts || 0 }) }));
        if (c.high) meta.append(h("span", { class: "wcal-dot", "aria-hidden": "true", text: "·" }), h("span", { text: tr("wcal.count.high", { n: c.high }) }));
      } else {
        meta.append(h("span", { text: tr("wcal.subtitle") }));
      }
      // embedded (вкладка «Календарь работ» в «Ведомствах» R17, схема R11 §5.4): заголовок и «Пример» — у экрана R17.
      const title = opts.embedded ? null : h(opts.titleTag || "h2", { class: "wcal-title", text: tr("wcal.title") });
      const titleBox = h("div", { class: "wcal-head__title" }, [title, meta]);
      if (d && d.demo && state.status === "ready") {
        titleBox.append(h("p", { class: "wcal-demo" }, [h("span", { class: "wcal-demo__tag", text: tr("common.tag.demo") }), tr("wcal.demo_note")]));
      }
      // Настоящие работы LOCAL-5 (если файл есть): сколько легло на участок улицы, сколько — примерным местом.
      const real = d && state.status === "ready" ? d.real : null;
      if (real && real.status === "OK" && real.total) {
        titleBox.append(h("p", { class: "wcal-demo wcal-real" }, [
          h("span", { class: "wcal-real__tag", text: tr("wcal.real.tag") }),
          tr("wcal.real.coverage", { n: real.total, exact: real.on_segments, approx: real.approximate }),
        ]));
      }
      // Фильтры нужны, когда есть данные или «пусто» (можно сменить район); при «войдите», «не подключён», ошибке — нет.
      const withControls = state.status === "ready" || (state.status === "loading" && state.data);
      return h("header", { class: "wcal-head" + (opts.embedded ? " wcal-head--embedded" : "") }, [titleBox, withControls ? controls() : null]);
    }

    function controls() {
      const district = h("select", { class: "wcal-select", "aria-label": tr("wcal.filter.district"),
        onchange: (e) => { state.filters.district = e.target.value; load(); } },
      [h("option", { value: "", text: tr("wcal.filter.all_districts") }),
        ...DISTRICTS.map(([id, ru, kk]) => h("option", { value: id, text: lang() === "kk" ? kk : ru }))]);
      district.value = state.filters.district;
      const services = (state.data && state.data.services) || [];
      const known = new Set(services.map((s) => s.id));
      if (state.filters.service) known.add(state.filters.service);
      const service = h("select", { class: "wcal-select", "aria-label": tr("wcal.filter.service"),
        onchange: (e) => { state.filters.service = e.target.value; load(); } },
      [h("option", { value: "", text: tr("wcal.filter.all_services") }),
        ...[...known].map((id) => h("option", { value: id, text: serviceName(id, services.find((s) => s.id === id)) }))]);
      service.value = state.filters.service;
      const d = state.data;
      const period = d ? monthSpan(d.period.from, d.period.to) : "";
      const nav = h("div", { class: "wcal-shift", role: "group", "aria-label": tr("wcal.period.label", { from: d ? fmtDay(d.period.from, true) : "", to: d ? fmtDay(d.period.to, true) : "" }) }, [
        h("button", { type: "button", class: "wcal-iconbtn", "aria-label": tr("wcal.period.prev"), title: tr("wcal.period.prev"),
          onclick: () => { state.shift -= 3; load(); } }, [icon("back")]),
        state.shift
          ? h("button", { type: "button", class: "wcal-iconbtn wcal-iconbtn--text", title: tr("wcal.period.now"),
            onclick: () => { state.shift = 0; load(); } }, [period || tr("wcal.today")])
          : h("span", { class: "wcal-shift__label", text: period }),
        h("button", { type: "button", class: "wcal-iconbtn", "aria-label": tr("wcal.period.next"), title: tr("wcal.period.next"),
          onclick: () => { state.shift += 3; load(); } }, [icon("forward")]),
      ]);
      // Поля — компонент ui-kit R11 (.bk-field): тот же вид, что в формах сотрудника. Во вкладке R17 главная кнопка —
      // «Добавить работу» (форма R06), здесь же, справа (схема R11 §5.4). Если хозяин вкладки уже дал её сам
      // ([data-action="add-work"] рядом, как у R17 191f81e7) или просит без неё (addButton: false) — своей нет:
      // на экране одна главная кнопка.
      const sh = root.BirgeShell;
      const addMain = opts.embedded && !hostAdd() && sh && root.BirgeWorks && typeof sh.setSection === "function"
        ? h("button", { type: "button", class: "bk-btn bk-btn--primary wcal-addmain", onclick: () => sh.setSection("works") }, [icon("plus"), tr("wcal.add")])
        : null;
      return h("div", { class: "wcal-controls" }, [
        h("label", { class: "bk-field wcal-field" }, [h("span", { class: "bk-field__label wcal-field__label", text: tr("wcal.filter.district") }), district]),
        h("label", { class: "bk-field wcal-field" }, [h("span", { class: "bk-field__label wcal-field__label", text: tr("wcal.filter.service") }), service]),
        nav,
        addMain,
      ]);
    }

    // --- карточка выбранного конфликта (одна главная кнопка экрана — «Показать на карте»)
    function worksOf(conflict) {
      const byId = new Map(state.data.works.map((w) => [w.id, w]));
      const first = byId.get(conflict.first) || byId.get(conflict.works[0]);
      const second = byId.get(conflict.second) || byId.get(conflict.works[1]);
      return [first, second].filter(Boolean);
    }
    function workPill(w) {
      const svc = state.data.services.find((s) => s.id === w.service);
      return h("div", { class: "wcal-wpill" }, [
        h("span", { class: "wcal-swatch", style: "background:" + ((svc && svc.color) || "#7b8494"), "aria-hidden": "true" }),
        h("span", { class: "wcal-wpill__kind", text: tr("wcal.kind_short." + w.kind) }),
        h("span", { class: "wcal-wpill__svc", text: serviceName(w.service, svc) }),
        h("span", { class: "wcal-wpill__dates", text: fmtRange(w.starts_on, w.ends_on) }),
      ]);
    }
    function focusCard() {
      const d = state.data;
      if (!d.conflicts.length) {
        return h("section", { class: "wcal-focus wcal-focus--calm", "aria-live": "polite" }, [
          h("span", { class: "wcal-calm-ic", "aria-hidden": "true" }, [icon("check")]),
          h("div", {}, [h("h3", { class: "wcal-focus__title", text: tr("wcal.no_conflicts.title") }),
            h("p", { class: "wcal-focus__advice", text: tr("wcal.no_conflicts.text") })]),
        ]);
      }
      const idx = Math.max(0, d.conflicts.findIndex((c) => c.id === state.selected));
      const c = d.conflicts[idx];
      const pair = worksOf(c);
      const street = lang() === "kk" ? (c.street_kk || c.street_ru) : c.street_ru;
      const facts = h("div", { class: "wcal-focus__facts" });
      if (pair[0]) facts.append(workPill(pair[0]));
      if (pair[1]) {
        let link = "";
        if (c.kind === "dig_after_surface" && c.gap_days != null) link = tr("wcal.gap", { gap: gapWords(c.gap_days) });
        else if (c.overlap_days) link = tr("wcal.overlap", { n: c.overlap_days });
        facts.append(h("span", { class: "wcal-focus__arrow" }, [icon("forward"), link ? h("span", { text: link }) : null]), workPill(pair[1]));
      }
      const sev = c.severity === "high";
      const advice = lang() === "kk" ? c.advice_kk : c.advice_ru;
      const counter = h("div", { class: "wcal-focus__nav" }, [
        h("button", { type: "button", class: "wcal-iconbtn", "aria-label": tr("wcal.prev_conflict"), title: tr("wcal.prev_conflict"),
          disabled: d.conflicts.length < 2 ? true : null, onclick: () => select(d.conflicts[(idx - 1 + d.conflicts.length) % d.conflicts.length].id, true) }, [icon("back")]),
        h("span", { class: "wcal-focus__count", text: tr("wcal.of", { i: idx + 1, n: d.conflicts.length }) }),
        h("button", { type: "button", class: "wcal-iconbtn", "aria-label": tr("wcal.next_conflict"), title: tr("wcal.next_conflict"),
          disabled: d.conflicts.length < 2 ? true : null, onclick: () => select(d.conflicts[(idx + 1) % d.conflicts.length].id, true) }, [icon("forward")]),
      ]);
      return h("section", { class: "wcal-focus" + (sev ? " wcal-focus--high" : ""), "data-conflict": c.id, "aria-live": "polite",
        "aria-label": conflictTitle(c) }, [
        h("div", { class: "wcal-focus__top" }, [
          h("span", { class: "wcal-sev" + (sev ? " wcal-sev--high" : ""), "aria-hidden": "true" }, [icon("alert")]),
          h("h3", { class: "wcal-focus__title", text: conflictTitle(c) }),
          h("span", { class: "wcal-chip wcal-chip--" + c.severity, text: tr("wcal.severity." + c.severity) }),
          c.stage && c.stage !== "planned" ? h("span", { class: "wcal-chip wcal-chip--stage", text: tr("wcal.stage." + c.stage) }) : null,
          street ? h("span", { class: "wcal-focus__street" }, [icon("pin"), street]) : null,
        ]),
        h("div", { class: "wcal-focus__actions" }, [
          counter,
          h("button", { type: "button", class: "bk-btn" + (opts.embedded && (root.BirgeWorks || hostAdd()) ? "" : " bk-btn--primary") + " wcal-mapbtn", onclick: () => showOnMap(c) },
            [icon("pin"), tr("common.action.show_on_map")]),
        ]),
        facts,
        advice ? h("p", { class: "wcal-focus__advice", text: advice }) : null,
      ]);
    }

    // --- лента
    function timeline() {
      const d = state.data;
      const wrap = h("div", { class: "wcal-tl", role: "region", "aria-label": tr("wcal.timeline"), tabindex: "-1" });
      const inner = h("div", { class: "wcal-tl__inner" });
      wrap.append(inner);
      const range = rangeOf(d);
      const from = range.from, to = range.to;
      const total = to - from + 1;
      const months = range.months;
      // Ширина: месяцы делят доступное место, но не уже MIN_MONTH_W — иначе прокрутка вбок.
      const avail = Math.max(0, (rootEl.clientWidth || 960) - labelWidth() - 2);
      const trackW = Math.max(avail, months.length * ((rootEl.clientWidth || 960) < PHONE ? 60 : MIN_MONTH_W));
      const x = (n) => ((n - from) / total) * trackW;
      inner.style.width = labelWidth() + trackW + "px";
      inner.style.setProperty("--wcal-label-w", labelWidth() + "px");
      // Шапка месяцев
      // Угол над названиями улиц: «Добавить работу» — форма R06 «Работы и отключения» (служба, вид, участок улицы
      // через R12). Тихая кнопка: главная на экране — «Показать на карте». Нет экрана R06 — угол пустой.
      const shell = root.BirgeShell;
      const add = !opts.embedded && shell && root.BirgeWorks && typeof shell.setSection === "function"
        ? h("button", { type: "button", class: "wcal-add", onclick: () => shell.setSection("works") }, [icon("plus"), tr("wcal.add")])
        : null;
      const head = h("div", { class: "wcal-tl__head" }, [h("div", { class: "wcal-tl__corner" }, [add])]);
      const monthsBox = h("div", { class: "wcal-tl__months", style: "width:" + trackW + "px" });
      months.forEach((key, i) => {
        const y = +key.slice(0, 4), m = +key.slice(5, 7) - 1;
        const start = Math.floor(Date.UTC(y, m, 1) / DAY), end = Math.floor(Date.UTC(y, m + 1, 1) / DAY);
        const left = x(Math.max(start, from)), right = x(Math.min(end, to + 1));
        monthsBox.append(h("div", { class: "wcal-month" + (m === 0 ? " wcal-month--year" : ""), style: `left:${left}px;width:${right - left}px`,
          text: MONTHS[lang()][m] }));
        // Год — отдельной меткой в нижней половине шапки: у первого месяца и у января (месяц не обрезается).
        if (m === 0 || i === 0) monthsBox.append(h("div", { class: "wcal-year", style: `left:${left}px`, text: String(y) }));
      });
      const today = dayNum(d.period.today);
      if (today >= from && today <= to) monthsBox.append(h("div", { class: "wcal-today-tag", style: `left:${x(today)}px`, text: tr("wcal.today") }));
      head.append(monthsBox);
      inner.append(head);
      // Строки
      const body = h("div", { class: "wcal-tl__body" });
      const grid = h("div", { class: "wcal-grid", style: `left:${labelWidth()}px;width:${trackW}px`, "aria-hidden": "true" });
      months.forEach((key) => {
        const y = +key.slice(0, 4), m = +key.slice(5, 7) - 1;
        const start = Math.floor(Date.UTC(y, m, 1) / DAY);
        if (start > from) grid.append(h("div", { class: "wcal-grid__line" + (m === 0 ? " wcal-grid__line--year" : ""), style: `left:${x(start)}px` }));
      });
      if (today >= from && today <= to) grid.append(h("div", { class: "wcal-grid__today", style: `left:${x(today)}px` }));
      body.append(grid);
      const rows = layoutRows(d, range);
      const geom = new Map();  // id работы → {x0, x1, y} для связей конфликтов
      // Чип конфликта стоит в своей дорожке над полосами верхней из двух строк — не закрывает короткую полосу.
      const rowOf = new Map();
      rows.forEach((r, i) => r.items.forEach((it) => rowOf.set(it.work.id, i)));
      const chipRows = new Set();
      for (const c of d.conflicts) {
        const ia = rowOf.get(c.first || c.works[0]), ib = rowOf.get(c.second || c.works[1]);
        if (ia !== undefined && ib !== undefined) chipRows.add(Math.min(ia, ib));
      }
      let top = 0;
      const sel = d.conflicts.find((c) => c.id === state.selected);
      const selWorks = new Set(sel ? sel.works : []);
      // Справа от этих полос — связь «копаем дважды» с чипом: подпись вида там не ставим (её говорит карточка).
      const linkStarts = new Set(d.conflicts.filter((c) => c.kind === "dig_after_surface").map((c) => c.first || c.works[0]));
      rows.forEach((r, ri) => {
        const lift = chipRows.has(ri) ? CHIP_LANE : 0;
        const height = r.lanes * LANE_H + ROW_PAD * 2 - 6 + lift;
        const street = r.row.street_ru ? (lang() === "kk" ? r.row.street_kk || r.row.street_ru : r.row.street_ru) : tr("wcal.street_none");
        const label = h("div", { class: "wcal-row__label", style: `height:${height}px` }, [
          h("span", { class: "wcal-row__street", text: street, title: street }),
          h("span", { class: "wcal-row__meta" }, [
            r.row.conflicts ? h("span", { class: "wcal-row__bad", text: tr("wcal.row.conflicts", { n: r.row.conflicts }) })
              : h("span", { text: tr("wcal.row.works", { n: r.row.works.length }) }),
          ]),
        ]);
        const track = h("div", { class: "wcal-row__track", style: `width:${trackW}px;height:${height}px` });
        // Зона нажатия полосы — HIT × HIT вокруг неё, но не дальше середины промежутка до соседней полосы той же дорожки:
        // нажатие на видимую полосу всегда открывает её саму. Подпись «вид» справа — только до зоны следующей полосы.
        const hitOf = new Map();
        const byLane = new Map();
        for (const it of r.items) byLane.set(it.lane, (byLane.get(it.lane) || []).concat([it]));
        for (const list of byLane.values()) {
          list.sort((a, b) => a.s - b.s);
          const vis = list.map((it) => { const a = x(it.s); return [a, a + Math.max(8, x(it.e + 1) - a)]; });
          list.forEach((it, k) => {
            const [a, b] = vis[k];
            const pad = Math.max(0, (HIT - (b - a)) / 2);
            const lo = k ? (vis[k - 1][1] + a) / 2 : -Infinity;
            const hi = k + 1 < list.length ? (b + vis[k + 1][0]) / 2 : Infinity;
            hitOf.set(it.work.id, { left: Math.max(a - pad, lo), right: Math.min(b + pad, hi), nextLeft: hi });
          });
        }
        for (const it of r.items) {
          const w = it.work;
          const svc = d.services.find((s) => s.id === w.service);
          const color = (svc && svc.color) || "#7b8494";
          const x0 = x(it.s), x1 = x(it.e + 1);
          const width = Math.max(8, x1 - x0);
          const y = ROW_PAD + lift + it.lane * LANE_H;
          geom.set(w.id, { x0, x1: x0 + width, y: top + y + 12, rowTop: top });
          const kindText = tr("wcal.kind_short." + w.kind);
          const svcText = serviceName(w.service, svc);
          // Подпись внутри полосы — только если помещается целиком (замер шрифта, поля 8 + 8); иначе — справа от полосы.
          const full = kindText + " · " + svcText;
          const inside = textWidth(full) + 18 <= width ? full : textWidth(kindText) + 18 <= width ? kindText : "";
          const cls = ["wcal-bar"];
          if (w.status === "done" || w.status === "completed") cls.push("wcal-bar--done");
          if (w.approximate) cls.push("wcal-bar--approx");
          if (w.context) cls.push("wcal-bar--context");
          if (w.conflicts && w.conflicts.length) cls.push("wcal-bar--conflict");
          if (sel && selWorks.has(w.id)) cls.push("is-sel");
          if (sel && !selWorks.has(w.id)) cls.push("is-dim");
          // Кнопка — зона нажатия (HIT × HIT, где есть место); сама полоса (24 px) — заливка внутри.
          const hz = hitOf.get(w.id) || { left: x0, right: x0 + width, nextLeft: Infinity };
          const hitX = hz.left, hitW = Math.max(width, hz.right - hz.left);
          const bar = h("button", { type: "button", class: cls.join(" "), "data-work": w.id,
            style: `left:${hitX}px;top:${y - (HIT - BAR_H) / 2}px;width:${hitW}px;--wcal-c:${color};--wcal-on:${textOn(color)}`,
            "aria-label": tr("wcal.bar.label", { title: lang() === "kk" ? w.title_kk || w.title_ru : w.title_ru, service: svcText, dates: fmtRange(w.starts_on, w.ends_on) })
              + (w.approximate ? ". " + tr("common.tag.approx") : ""),
            title: (lang() === "kk" ? w.title_kk || w.title_ru : w.title_ru) + " · " + fmtRange(w.starts_on, w.ends_on),
            onclick: (e) => openPopover(w, e.currentTarget) }, [
              h("span", { class: "wcal-bar__fill", style: `left:${x0 - hitX}px;width:${width}px` },
                [inside ? h("span", { class: "wcal-bar__text", text: inside }) : null]),
            ]);
          track.append(bar);
          const outLeft = Math.max(x0 + width + 6, hitX + hitW + 4);  // справа от зоны нажатия, а не под ней
          const room = Math.min(hz.nextLeft, trackW) - outLeft - 4;
          if (!inside && outLeft + 144 < trackW && textWidth(kindText) <= room && !linkStarts.has(w.id)) {
            track.append(h("span", { class: "wcal-bar__out", style: `left:${outLeft}px;top:${y + 3}px`, "aria-hidden": "true", text: kindText }));
          }
        }
        body.append(h("div", { class: "wcal-row" + (r.row.conflicts ? " wcal-row--bad" : "") + (height >= 58 ? " wcal-row--tall" : ""),
          "data-row": r.row.key }, [label, track]));
        top += height + 1;
      });
      // Связи конфликтов: SVG поверх строк (координаты — из той же раскладки, без замеров DOM).
      const chips = placeChips(d.conflicts, geom, trackW);
      const links = svgLinks(d.conflicts, geom, trackW, top, chips);
      links.style.left = labelWidth() + "px";
      body.append(links);
      body.append(...chipsFor(d.conflicts, chips));
      body.style.height = top + "px";
      inner.append(body);
      // Открыть сразу на выбранном конфликте или на «сегодня»; высота — до низа листа раздела.
      requestAnimationFrame(() => {
        if (state.destroyed) return;
        fitHeight(wrap);
        const g = sel && geom.get(sel.works[0]);
        const target = g ? g.x0 - 80 : today >= from ? x(today) - 120 : 0;
        if (wrap.scrollWidth > wrap.clientWidth) wrap.scrollLeft = Math.max(0, target);
        if (g && g.rowTop > wrap.clientHeight - 80) wrap.scrollTop = Math.max(0, g.rowTop - 40);
      });
      return wrap;
    }
    function fitHeight(wrap) {
      const r = wrap.getBoundingClientRect();
      if (!r.height || innerWidth < PHONE) { wrap.style.maxHeight = ""; return; }
      const sheet = rootEl.closest(".birge-day") || null;
      const bottom = sheet ? sheet.getBoundingClientRect().bottom - (parseFloat(getComputedStyle(sheet).paddingBottom) || 0) : innerHeight - 16;
      wrap.style.maxHeight = Math.max(240, Math.floor(bottom - r.top)) + "px";
    }
    function labelWidth() {
      return (rootEl.clientWidth || 960) < PHONE ? 118 : 196;
    }

    function svgLinks(conflicts, geom, width, height, chips) {
      const NS = "http://www.w3.org/2000/svg";
      const svg = doc.createElementNS(NS, "svg");
      svg.setAttribute("class", "wcal-links");
      svg.setAttribute("width", String(width));
      svg.setAttribute("height", String(height));
      svg.setAttribute("aria-hidden", "true");
      const add = (tag, attrs) => {
        const el = doc.createElementNS(NS, tag);
        for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
        svg.append(el);
        return el;
      };
      for (const c of conflicts) {
        const a = geom.get(c.first || c.works[0]), b = geom.get(c.second || c.works[1]);
        if (!a || !b) continue;
        const on = c.id === state.selected;
        const cls = "wcal-link" + (on ? " is-sel" : "") + (state.selected && !on ? " is-dim" : "");
        const chip = chips.get(c.id);
        if (chip && chip.stemTo - chip.y > CHIP_LANE / 2 + 3) {
          // Ножка от чипа (в дорожке над полосами) к его связи — какой чип к какой связи, видно без подписи.
          add("line", { class: cls + " wcal-link__stem", x1: chip.x, y1: chip.y + 12, x2: chip.ax, y2: chip.stemTo });
        }
        if (c.kind === "dig_after_surface") {
          // От конца асфальта к началу раскопки — на уровне полос (промежуток времени между ними); разные дорожки —
          // плавная S-кривая. Внутри строки: не уходит под липкую шапку месяцев.
          const x0 = a.x1 + 2, x1 = Math.max(a.x1 + 6, b.x0 - 2), y0 = a.y, y1 = b.y, mx = (x0 + x1) / 2;
          const d = y0 === y1 ? `M${x0},${y0} L${x1},${y1}` : `M${x0},${y0} C${mx},${y0} ${mx},${y1} ${x1},${y1}`;
          add("path", { class: cls + (on && state.animateLink ? " wcal-link--draw" : ""), pathLength: 1, d });
          add("circle", { class: cls + " wcal-link__end", cx: x0, cy: y0, r: 3.5 });
          add("circle", { class: cls + " wcal-link__end", cx: x1, cy: y1, r: 3.5 });
        } else {
          // Совпадение по времени: скобка на общем отрезке дат. Соседние дорожки одной строки — одна скобка на обе
          // полосы; разные строки (параллельные улицы) — скобка у каждой полосы и вертикальная связка между ними.
          const x0 = Math.max(a.x0, b.x0), x1 = Math.max(x0 + 4, Math.min(a.x1, b.x1));
          if (Math.abs(a.y - b.y) <= LANE_H) {
            const yTop = Math.min(a.y, b.y) - 15, yBot = Math.max(a.y, b.y) + 15;
            add("rect", { class: cls + " wcal-link__band", x: x0, y: yTop, width: x1 - x0, height: yBot - yTop, rx: 6 });
          } else {
            for (const g of [a, b]) add("rect", { class: cls + " wcal-link__band", x: x0, y: g.y - 15, width: x1 - x0, height: 30, rx: 6 });
            const top = Math.min(a.y, b.y) + 15, bottom = Math.max(a.y, b.y) - 15, mid = (x0 + x1) / 2;
            add("line", { class: cls + " wcal-link__tie", x1: mid, y1: top, x2: mid, y2: bottom });
          }
        }
      }
      return svg;
    }
    // Место чипа: по горизонтали — середина промежутка «асфальт → раскопка» или общего отрезка дат, по вертикали —
    // дорожка чипов верхней строки. Чипы одной дорожки не налезают друг на друга и не выходят за края ленты.
    function placeChips(conflicts, geom, width) {
      const out = new Map();
      const lanes = new Map();
      for (const c of conflicts) {
        const a = geom.get(c.first || c.works[0]), b = geom.get(c.second || c.works[1]);
        if (!a || !b) continue;
        let cx, stemTo;
        if (c.kind === "dig_after_surface") {
          cx = (a.x1 + Math.max(a.x1, b.x0)) / 2;
          stemTo = a.y === b.y ? a.y : (a.y + b.y) / 2;
        } else {
          const x0 = Math.max(a.x0, b.x0), x1 = Math.min(a.x1, b.x1);
          cx = (x0 + Math.max(x0, x1)) / 2;
          stemTo = Math.min(a.y, b.y) - 15;
        }
        const half = (textWidth(tr("wcal.chip." + c.kind)) * 1.04 + 24) / 2;  // 13 px полужирный + поля 10 + рамка
        const y = Math.min(a.rowTop, b.rowTop) + ROW_PAD / 2 + CHIP_LANE / 2;
        cx = Math.min(Math.max(cx, half + 2), width - half - 2);
        const lane = lanes.get(y) || [];
        lane.push({ id: c.id, cx, ax: cx, half, stemTo });
        lanes.set(y, lane);
      }
      for (const [y, lane] of lanes) {
        lane.sort((p, q) => p.cx - q.cx || (p.id < q.id ? -1 : 1));
        let right = -Infinity;
        for (const p of lane) {
          p.x = Math.max(p.cx, right + p.half + 6);
          right = p.x + p.half;
        }
        let limit = width - 2;  // сдвинуть влево то, что вышло за правый край
        for (let k = lane.length - 1; k >= 0; k--) {
          const p = lane[k];
          p.x = Math.min(p.x, limit - p.half);
          limit = p.x - p.half - 6;
        }
        for (const p of lane) out.set(p.id, { x: p.x, y, ax: p.ax, stemTo: p.stemTo });
      }
      return out;
    }
    function chipsFor(conflicts, chips) {
      const out = [];
      for (const c of conflicts) {
        const place = chips.get(c.id);
        if (!place) continue;
        const on = c.id === state.selected;
        out.push(h("button", { type: "button", class: "wcal-cchip wcal-cchip--" + c.severity + (on ? " is-sel" : ""), "data-conflict": c.id,
          style: `left:${labelWidth() + place.x}px;top:${place.y}px`, "aria-pressed": on ? "true" : "false",
          "aria-label": conflictTitle(c) + (c.street_ru ? ": " + (lang() === "kk" ? c.street_kk || c.street_ru : c.street_ru) : ""),
          onclick: () => select(c.id, false) }, [h("span", { class: "wcal-cchip__pill", text: tr("wcal.chip." + c.kind) })]));
      }
      return out;
    }

    // --- карточка работы (по нажатию на полосу)
    function openPopover(w, anchor) {
      closePopover(false);
      const svc = state.data.services.find((s) => s.id === w.service);
      const days = dayNum(w.ends_on || w.starts_on) - dayNum(w.starts_on) + 1;
      const street = lang() === "kk" ? w.street_kk || w.street_ru : w.street_ru;
      const place = w.approximate ? tr("common.tag.approx") + (street ? " · " + street : "")
        : (street || "") + (w.length_m ? " · " + tr("wcal.work.length", { m: Math.round(w.length_m) }) : "");
      const rows = [
        [tr("wcal.work.service"), h("span", { class: "wcal-pop__svc" }, [h("span", { class: "wcal-swatch", style: "background:" + ((svc && svc.color) || "#7b8494") }), serviceName(w.service, svc)])],
        [tr("wcal.work.kind"), tr("wcal.kind_short." + w.kind)],
        [tr("wcal.work.dates"), fmtRange(w.starts_on, w.ends_on) + " · " + tr("wcal.work.days", { n: days })],
        [tr("wcal.work.status"), tr("wcal.status." + (w.status || "unknown")) + (w.delayed ? " · " + tr("wcal.work.delayed") : "")],
        [tr("wcal.work.place"), place],
      ];
      // Настоящая работа — ссылка на источник (только http/https: проверено на сервере; здесь — ещё раз).
      if (w.source === "real" && w.source_ref && /^https?:\/\//.test(w.source_ref)) {
        rows.push([tr("wcal.work.source"), h("a", { class: "wcal-pop__src", href: w.source_ref, target: "_blank", rel: "noopener noreferrer" },
          [w.source_name || w.source_ref])]);
      }
      const pop = h("div", { class: "wcal-pop bk-glass bk-glass--strong", role: "dialog", "aria-label": lang() === "kk" ? w.title_kk || w.title_ru : w.title_ru, tabindex: "-1" }, [
        h("div", { class: "wcal-pop__hd" }, [
          h("h4", { class: "wcal-pop__title", text: lang() === "kk" ? w.title_kk || w.title_ru : w.title_ru }),
          h("button", { type: "button", class: "wcal-x", "aria-label": tr("common.action.close"), onclick: () => closePopover(true) }, [icon("close")]),
        ]),
        w.demo ? h("span", { class: "wcal-demo__tag", text: tr("common.tag.demo") }) : null,
        w.context ? h("p", { class: "wcal-pop__note", text: tr("wcal.work.context") }) : null,
        h("dl", { class: "wcal-pop__rows" }, rows.flatMap(([k, v]) => [h("dt", { text: k }), h("dd", {}, [v])])),
        ...(w.conflicts || []).map((id) => {
          const c = state.data.conflicts.find((x) => x.id === id);
          return c ? h("button", { type: "button", class: "wcal-cchip wcal-cchip--" + c.severity + " wcal-pop__conflict",
            onclick: () => { closePopover(false); select(c.id, true); } }, [h("span", { class: "wcal-cchip__pill", text: tr("wcal.chip." + c.kind) })]) : null;
        }),
        h("div", { class: "wcal-pop__acts" }, [
          !w.approximate && w.geometry ? h("button", { type: "button", class: "bk-btn wcal-pop__map", onclick: () => showWorkOnMap(w) }, [icon("pin"), tr("common.action.show_on_map")]) : null,
          // Запись R06 («Работы и отключения», #works/<id>) — открыть для правки сроков и участка.
          w.link && /^#works\/[A-Za-z0-9._:-]+$/.test(w.link) ? h("a", { class: "bk-btn bk-btn--ghost wcal-pop__open", href: w.link }, [icon("edit"), tr("wcal.work.open")]) : null,
        ]),
      ]);
      // Карточка — панель поверх ленты с той стороны, где нет нажатой полосы (лента не прокручивается и полоса видна);
      // телефон — шторка снизу экрана.
      const box = rootEl.querySelector(".wcal-tl");
      if (!box) return;
      rootEl.append(pop);
      if ((rootEl.clientWidth || innerWidth) < PHONE) {
        pop.classList.add("wcal-pop--sheet");
      } else {
        const rr = rootEl.getBoundingClientRect(), br = box.getBoundingClientRect(), ar = anchor.getBoundingClientRect();
        const onRight = (ar.left + ar.right) / 2 < (br.left + br.right) / 2;
        pop.style.top = br.top - rr.top + 8 + "px";
        pop.style.maxHeight = Math.max(200, br.height - 16) + "px";
        if (onRight) pop.style.right = rr.right - br.right + 8 + "px";
        else pop.style.left = br.left - rr.left + labelWidth() + 8 + "px";
      }
      state.popover = { el: pop, anchor, work: w.id };
      pop.focus({ preventScroll: true });
    }
    function closePopover(returnFocus) {
      if (!state.popover) return;
      const { el, anchor } = state.popover;
      state.popover = null;
      el.remove();
      if (returnFocus && anchor && anchor.isConnected) anchor.focus({ preventScroll: true });
    }

    function select(id, scrollTo) {
      state.selected = id;
      state.animateLink = true;
      render();
      if (scrollTo) {
        const chip = rootEl.querySelector(`.wcal-cchip[data-conflict="${CSS.escape(id)}"]`);
        if (chip) chip.scrollIntoView({ block: "nearest", inline: "center", behavior: reducedMotion() ? "auto" : "smooth" });
      }
    }

    // --- переход к карте
    function showOnMap(conflict) {
      MapView.focus({ conflict, works: worksOf(conflict), services: state.data.services, opts });
    }
    function showWorkOnMap(w) {
      closePopover(false);
      MapView.focus({ work: w, services: state.data.services, opts });
    }

    // --- состояния
    function stateBox(kind) {
      const map = {
        staff: ["wcal.staff.title", "wcal.staff.text", "user", null],
        not_ready: ["wcal.not_ready.title", "wcal.not_ready.text", "info", null],
        network: ["common.state.network_title", "common.state.network_text", "wifi-off", "retry"],
        error: ["common.state.error_title", "common.state.error_text", "alert", "retry"],
        empty: ["wcal.empty.title", "wcal.empty.text", "calendar", "reset"],
      };
      const [t1, t2, ic, act] = map[kind];
      const shellApi = root.CivicShell;
      const login = kind === "staff" && shellApi && typeof shellApi.openEditor === "function"
        ? h("button", { type: "button", class: "bk-btn bk-btn--primary", onclick: () => { watchLogin(); shellApi.openEditor(); } }, [icon("user"), tr("wcal.staff.login")])
        : null;
      // П1, правило 2: иконка + короткий текст + одна кнопка. Пусто без фильтров — «Добавить работу» (форма R06).
      const sh = root.BirgeShell;
      const filtered = state.filters.district || state.filters.service || state.shift;
      const btn = login || (act === "retry"
        ? h("button", { type: "button", class: "bk-btn bk-btn--primary", onclick: load }, [icon("refresh"), tr("common.action.retry")])
        : act === "reset" && filtered
          ? h("button", { type: "button", class: "bk-btn", onclick: () => { state.filters = { district: "", service: "" }; state.shift = 0; load(); } }, [tr("wcal.empty.reset")])
          : act === "reset" && sh && root.BirgeWorks && typeof sh.setSection === "function"
            ? h("button", { type: "button", class: "bk-btn", onclick: () => sh.setSection("works") }, [icon("plus"), tr("wcal.add")])
            : null);
      return h("div", { class: "wcal-state wcal-state--" + kind, role: kind === "error" || kind === "network" ? "alert" : "status" }, [
        h("span", { class: "wcal-state__ic", "aria-hidden": "true" }, [icon(ic)]),
        h("h3", { class: "wcal-state__title", text: tr(t1) }),
        h("p", { class: "wcal-state__text", text: tr(t2) }),
        btn,
      ]);
    }
    // После входа сотрудника (кабинет оболочки) — календарь загружается сам, без перезагрузки страницы.
    let loginTimer = 0;
    function watchLogin() {
      clearInterval(loginTimer);
      loginTimer = setInterval(() => {
        const sh = root.CivicShell;
        if (state.destroyed || state.status !== "staff") { clearInterval(loginTimer); return; }
        if (sh && typeof sh.csrfToken === "function" && sh.csrfToken()) { clearInterval(loginTimer); load(); }
      }, 1000);
    }
    function skeleton() {
      const rows = [];
      for (let i = 0; i < 6; i++) {
        rows.push(h("div", { class: "wcal-skel__row" }, [h("span", { class: "wcal-skel wcal-skel--label" }),
          h("span", { class: "wcal-skel wcal-skel--bar", style: `margin-left:${8 + ((i * 37) % 50)}%;width:${14 + ((i * 23) % 22)}%` })]));
      }
      return h("div", { class: "wcal-skel__box", "aria-busy": "true", "aria-label": tr("common.state.loading") }, [
        h("div", { class: "wcal-skel wcal-skel--focus" }), ...rows]);
    }

    function render(quiet) {
      if (state.destroyed) return;
      // Открытая карточка работы переживает перерисовку (ширина листа поменялась, полоса прокрутки появилась):
      // после неё — та же карточка у новой полосы.
      const reopen = resizing && state.popover && state.popover.work;
      resizing = false;
      closePopover(false);
      const scroll = rootEl.querySelector(".wcal-tl");
      const keep = scroll ? { left: scroll.scrollLeft, top: scroll.scrollTop } : null;
      const active = doc.activeElement && rootEl.contains(doc.activeElement) ? activeKey(doc.activeElement) : null;
      const parts = [header()];
      if (state.status === "loading") {
        if (state.data) parts.push(...readyParts(true));
        else if (!quiet) parts.push(skeleton());
      } else if (state.status === "ready") {
        parts.push(...readyParts(false));
      } else {
        parts.push(stateBox(state.status));
      }
      rootEl.replaceChildren(...parts);
      rootEl.toggleAttribute("aria-busy", state.status === "loading");
      if (keep && state.status === "ready") {
        const tl = rootEl.querySelector(".wcal-tl");
        if (tl && !active) { tl.scrollLeft = keep.left; tl.scrollTop = keep.top; }
      }
      if (active) restoreFocus(active);
      if (reopen && state.status === "ready") {
        const w = state.data.works.find((x) => x.id === reopen);
        const anchor = w && rootEl.querySelector(`.wcal-bar[data-work="${CSS.escape(reopen)}"]`);
        if (anchor) openPopover(w, anchor);
      }
      if (state.status === "ready") state.animateLink = false;
    }
    function readyParts(stale) {
      const d = state.data;
      if (!d.works.length) return [stateBox("empty")];
      const out = [focusCard(), timeline()];
      if (stale) out.forEach((el) => el.classList.add("is-stale"));
      return out;
    }
    // Фокус переживает перерисовку (клавиатура: «Следующий конфликт» нажимается подряд).
    function activeKey(el) {
      if (el.matches(".wcal-focus__nav button")) return { sel: ".wcal-focus__nav button", i: [...el.parentNode.querySelectorAll("button")].indexOf(el) };
      if (el.dataset.conflict) return { sel: `.wcal-cchip[data-conflict="${CSS.escape(el.dataset.conflict)}"]` };
      if (el.dataset.work) return { sel: `.wcal-bar[data-work="${CSS.escape(el.dataset.work)}"]` };
      if (el.matches("select")) return { sel: "select", i: [...rootEl.querySelectorAll("select")].indexOf(el) };
      if (el.matches(".wcal-shift button")) return { sel: ".wcal-shift button", i: [...rootEl.querySelectorAll(".wcal-shift button")].indexOf(el) };
      return null;
    }
    function restoreFocus(k) {
      const list = rootEl.querySelectorAll(k.sel);
      const el = k.i != null ? list[k.i] : list[0];
      if (el && !el.disabled) el.focus({ preventScroll: true });
    }

    function onKey(e) {
      if (e.key === "Escape" && state.popover) {
        e.preventDefault();
        e.stopPropagation();
        closePopover(true);
      }
    }
    function onDocClick(e) {
      if (state.popover && !state.popover.el.contains(e.target) && !e.target.closest(".wcal-bar")) closePopover(false);
    }
    function onLang() { if (!state.destroyed) render(); }
    rootEl.addEventListener("keydown", onKey);
    doc.addEventListener("click", onDocClick, true);
    doc.addEventListener("birge:lang", onLang);
    if (root.ResizeObserver) {
      let lastW = rootEl.clientWidth;
      ro = new ResizeObserver(() => {
        const w = rootEl.clientWidth;
        if (Math.abs(w - lastW) < 2) return;
        lastW = w;
        cancelAnimationFrame(rafId);
        rafId = requestAnimationFrame(() => { if (state.status === "ready") { resizing = true; render(); } });
      });
      ro.observe(rootEl);
    }
    load();

    const handle = {
      destroy() {
        state.destroyed = true;
        clearTimeout(skeletonTimer);
        clearInterval(loginTimer);
        cancelAnimationFrame(rafId);
        if (ro) ro.disconnect();
        rootEl.removeEventListener("keydown", onKey);
        doc.removeEventListener("click", onDocClick, true);
        doc.removeEventListener("birge:lang", onLang);
        delete rootEl.birgeWorksCalendar;
        rootEl.classList.remove("wcal");
        rootEl.removeAttribute("data-wcal");
        rootEl.replaceChildren();
      },
      setLang() { render(); },
      reload: load,
      get state() { return { status: state.status, selected: state.selected, filters: Object.assign({}, state.filters) }; },
    };
    rootEl.birgeWorksCalendar = handle;
    return handle;
  }

  // ------------------------------------------------------------------ карта: подсветка участков и карточка конфликта
  const MapView = (function () {
    let card = null;
    let current = null;     // что подсвечено: {conflict?, work?}
    let layerOn = false;
    let clickBound = null;
    let observer = null;

    function getMap(opts) {
      const m = opts && typeof opts.map === "function" ? opts.map() : opts && opts.map;
      if (m && typeof m.addLayer === "function") return m;
      try {
        // eslint-disable-next-line no-undef
        if (typeof map !== "undefined" && map && typeof map.addLayer === "function") return map;
      } catch (e) { /* нет глобальной карты web/map.js */ }
      return null;
    }
    function whenReady(m, fn) {
      if (m.isStyleLoaded && m.isStyleLoaded()) fn();
      else m.once("idle", fn);
    }
    function features(data, focus) {
      const out = [];
      const seen = new Set();
      for (const c of (data && data.conflicts) || []) {
        if (!c.geometry) continue;
        seen.add(c.id);
        out.push({ type: "Feature", geometry: c.geometry, properties: { id: c.id, severity: c.severity, focus: focus && focus.conflict && focus.conflict.id === c.id ? 1 : 0 } });
      }
      if (focus && focus.conflict && focus.conflict.geometry && !seen.has(focus.conflict.id)) {
        out.push({ type: "Feature", geometry: focus.conflict.geometry, properties: { id: focus.conflict.id, severity: focus.conflict.severity, focus: 1 } });
      }
      if (focus && focus.work && focus.work.geometry && focus.work.geometry.type !== "Point") {
        const svc = (focus.services || []).find((s) => s.id === focus.work.service);
        out.push({ type: "Feature", geometry: focus.work.geometry, properties: { id: focus.work.id, work: 1, focus: 1, color: (svc && svc.color) || "#5b6577" } });
      }
      return { type: "FeatureCollection", features: out };
    }
    // Точка конфликта — середина самой длинной линии участка по длине: лежит на форме улицы OSM (не «от руки»)
    // и не попадает на перекрёсток в конце участка.
    function anchorOf(geom) {
      const lines = geom.type === "MultiLineString" ? geom.coordinates : geom.type === "LineString" ? [geom.coordinates] : [];
      const len = (a, b) => Math.hypot((b[0] - a[0]) * Math.cos(a[1] * Math.PI / 180), b[1] - a[1]);
      let best = null, bestLen = -1;
      for (const line of lines) {
        let L = 0;
        for (let i = 1; i < line.length; i++) L += len(line[i - 1], line[i]);
        if (line.length && L > bestLen) { best = line; bestLen = L; }
      }
      if (!best) return null;
      let half = bestLen / 2;
      for (let i = 1; i < best.length; i++) {
        const d = len(best[i - 1], best[i]);
        if (d >= half && d > 0) {
          const t = half / d;
          return [best[i - 1][0] + (best[i][0] - best[i - 1][0]) * t, best[i - 1][1] + (best[i][1] - best[i - 1][1]) * t];
        }
        half -= d;
      }
      return best[best.length - 1];
    }
    function points(data) {
      const out = [];
      for (const c of (data && data.conflicts) || []) {
        const at = c.geometry && anchorOf(c.geometry);
        if (at) out.push({ type: "Feature", geometry: { type: "Point", coordinates: at }, properties: { id: c.id, severity: c.severity } });
      }
      return { type: "FeatureCollection", features: out };
    }
    function firstSymbolLayer(m) {
      const layers = (m.getStyle() && m.getStyle().layers) || [];
      const sym = layers.find((l) => l.type === "symbol");
      return sym ? sym.id : undefined;
    }
    function draw(m, data, focus) {
      const fc = features(data, focus);
      const src = m.getSource(MAP_SRC);
      if (src) {
        src.setData(fc);
        const pts = m.getSource(MAP_PT_SRC);
        if (pts) pts.setData(points(data));
        return;
      }
      m.addSource(MAP_SRC, { type: "geojson", data: fc });
      const before = firstSymbolLayer(m);
      m.addLayer({ id: MAP_LAYERS[0], type: "line", source: MAP_SRC, layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#ffffff", "line-opacity": 0.95,
          "line-width": ["interpolate", ["linear"], ["zoom"], 11, ["case", ["==", ["get", "focus"], 1], 6, 4], 16, ["case", ["==", ["get", "focus"], 1], 15, 10]] } }, before);
      m.addLayer({ id: MAP_LAYERS[1], type: "line", source: MAP_SRC, layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": ["case", ["==", ["get", "work"], 1], ["get", "color"], DANGER],
          "line-opacity": ["case", ["==", ["get", "focus"], 1], 1, 0.75],
          "line-width": ["interpolate", ["linear"], ["zoom"], 11, ["case", ["==", ["get", "focus"], 1], 3.5, 2.2], 16, ["case", ["==", ["get", "focus"], 1], 8, 5]] } }, before);
      // Масштаб города: участок в сотни метров — штрих в пару пикселей; точка показывает, где конфликт (нажатие — к нему).
      m.addSource(MAP_PT_SRC, { type: "geojson", data: points(data) });
      m.addLayer({ id: MAP_DOT, type: "circle", source: MAP_PT_SRC, maxzoom: DOT_MAX_ZOOM,
        paint: { "circle-color": DANGER, "circle-stroke-color": "#ffffff", "circle-stroke-width": 2.5,
          "circle-radius": ["case", ["==", ["get", "severity"], "high"], 7, 5.5] } }, before);
      if (!clickBound) {
        const pick = (zoomTo) => (e) => {
          const f = e.features && e.features[0];
          if (!f || f.properties.work) return;
          // Точка лежит на своей линии: щелчок по ней — один (у точки, с облётом), линия его не повторяет.
          if (!zoomTo && m.getLayer(MAP_DOT) && m.queryRenderedFeatures(e.point, { layers: [MAP_DOT] }).length) return;
          const data2 = shared.data;
          const c = data2 && data2.conflicts.find((x) => x.id === f.properties.id);
          if (c) focusOn(m, { conflict: c, works: worksFromShared(c), services: data2.services, opts: {} }, zoomTo);
        };
        clickBound = { line: pick(false), dot: pick(true),
          enter: () => { m.getCanvas().style.cursor = "pointer"; }, leave: () => { m.getCanvas().style.cursor = ""; } };
        m.on("click", MAP_LAYERS[1], clickBound.line);
        m.on("click", MAP_DOT, clickBound.dot);
        for (const id of [MAP_LAYERS[1], MAP_DOT]) {
          m.on("mouseenter", id, clickBound.enter);
          m.on("mouseleave", id, clickBound.leave);
        }
      }
    }
    function worksFromShared(c) {
      const d = shared.data;
      if (!d) return [];
      const byId = new Map(d.works.map((w) => [w.id, w]));
      return [byId.get(c.first || c.works[0]), byId.get(c.second || c.works[1])].filter(Boolean);
    }
    function remove(m) {
      if (!m) return;
      if (clickBound) {
        try {
          m.off("click", MAP_LAYERS[1], clickBound.line);
          m.off("click", MAP_DOT, clickBound.dot);
          for (const id of [MAP_LAYERS[1], MAP_DOT]) { m.off("mouseenter", id, clickBound.enter); m.off("mouseleave", id, clickBound.leave); }
        } catch (e) { /* слой уже снят */ }
        clickBound = null;
      }
      for (const id of [MAP_DOT, ...[...MAP_LAYERS].reverse()]) if (m.getLayer && m.getLayer(id)) m.removeLayer(id);
      for (const id of [MAP_PT_SRC, MAP_SRC]) if (m.getSource && m.getSource(id)) m.removeSource(id);
    }
    function bboxOf(geom) {
      const xs = [], ys = [];
      const walk = (c) => { if (typeof c[0] === "number") { xs.push(c[0]); ys.push(c[1]); } else c.forEach(walk); };
      walk(geom.coordinates);
      return xs.length ? [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)] : null;
    }
    function fly(m, bbox) {
      if (!bbox) return;
      const phone = innerWidth < PHONE;
      const padding = phone ? { top: 90, left: 32, right: 32, bottom: 300 } : { top: 130, left: 440, right: 480, bottom: 90 };
      try {
        m.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding, maxZoom: 16.6, duration: reducedMotion() ? 0 : 900, essential: true });
      } catch (e) {
        m.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 40, maxZoom: 16.6, duration: 0 });
      }
    }
    function closeCard() {
      if (card) { card.remove(); card = null; }
      doc.removeEventListener("keydown", onCardKey, true);
    }
    function onCardKey(e) {
      if (e.key === "Escape" && card) { e.stopPropagation(); closeCard(); }
    }
    function showCard(focus) {
      closeCard();
      const c = focus.conflict, w = focus.work;
      const title = c ? conflictTitle(c) : (lang() === "kk" ? w.title_kk || w.title_ru : w.title_ru);
      const street = c ? (lang() === "kk" ? c.street_kk || c.street_ru : c.street_ru) : (lang() === "kk" ? w.street_kk || w.street_ru : w.street_ru);
      const lines = (c ? focus.works : [w]).map((x) => {
        const svc = (focus.services || []).find((s) => s.id === x.service);
        return h("li", { class: "wcal-mapcard__work" }, [
          h("span", { class: "wcal-swatch", style: "background:" + ((svc && svc.color) || "#7b8494") }),
          h("span", { text: tr("wcal.kind_short." + x.kind) + " · " + serviceName(x.service, svc) + " · " + fmtRange(x.starts_on, x.ends_on) }),
        ]);
      });
      const advice = c ? (lang() === "kk" ? c.advice_kk : c.advice_ru) : null;
      card = h("aside", { class: "wcal-mapcard bk-app bk-glass bk-glass--strong" + (c && c.severity === "high" ? " wcal-mapcard--high" : ""),
        role: "dialog", "aria-label": title, tabindex: "-1" }, [
        h("div", { class: "wcal-mapcard__hd" }, [
          c ? h("span", { class: "wcal-sev" + (c.severity === "high" ? " wcal-sev--high" : ""), "aria-hidden": "true" }, [icon("alert")]) : null,
          h("h2", { class: "wcal-mapcard__title", text: title }),
          h("button", { type: "button", class: "wcal-x", "aria-label": tr("common.action.close"), onclick: closeCard }, [icon("close")]),
        ]),
        street ? h("p", { class: "wcal-mapcard__street", text: street }) : null,
        h("ul", { class: "wcal-mapcard__works" }, lines),
        advice ? h("p", { class: "wcal-mapcard__advice", text: advice }) : null,
        h("p", { class: "wcal-mapcard__where" }, [(c ? c.demo : w.demo) ? h("span", { class: "wcal-demo__tag", text: tr("common.tag.demo") }) : null, tr("wcal.map.where")]),
        root.BirgeShell ? h("button", { type: "button", class: "bk-btn bk-btn--primary wcal-mapcard__back", onclick: () => { closeCard(); root.BirgeShell.setSection(SCREEN_ID); } },
          [icon("calendar"), tr("wcal.map.back")]) : null,
      ]);
      doc.body.append(card);
      doc.addEventListener("keydown", onCardKey, true);
      card.focus({ preventScroll: true });
    }
    function focusOn(m, focus, moveMap) {
      current = focus;
      whenReady(m, () => {
        draw(m, layerOn ? shared.data : null, focus);
        if (moveMap !== false) fly(m, (focus.conflict && (focus.conflict.bbox || bboxOf(focus.conflict.geometry))) || (focus.work && (focus.work.bbox || bboxOf(focus.work.geometry))));
      });
      showCard(focus);
    }
    function watchSection() {
      if (observer || !root.MutationObserver) return;
      observer = new MutationObserver(() => {
        const s = doc.body.dataset.birgeSection;
        if (s && s !== "map") closeCard();
      });
      observer.observe(doc.body, { attributes: true, attributeFilter: ["data-birge-section"] });
    }
    // Экран календаря → карта: раздел «Карта», слой «Конфликты работ» включён, участок в центре, карточка слева.
    function focus(focusSpec) {
      const shell = root.BirgeShell;
      if (shell && typeof shell.setSection === "function") shell.setSection("map");
      else if (focusSpec.opts && typeof focusSpec.opts.close === "function") focusSpec.opts.close();
      watchSection();
      const m = getMap(focusSpec.opts);
      if (!m) return false;
      if (shell && typeof shell.setLayer === "function" && shell.layer !== LAYER_ID && focusSpec.conflict) {
        pendingFocus = focusSpec;   // show() слоя подхватит
        shell.setLayer(LAYER_ID);
        if (pendingFocus) { const f = pendingFocus; pendingFocus = null; focusOn(m, f); }
      } else {
        focusOn(m, focusSpec);
      }
      return true;
    }
    let pendingFocus = null;
    // Слой «Конфликты работ» для BirgeShell.registerLayer (выключен по умолчанию; одновременно — один доп. слой).
    function showLayer(m) {
      layerOn = true;
      const ready = (data) => {
        if (!layerOn) return;
        if (pendingFocus) { const f = pendingFocus; pendingFocus = null; focusOn(m, f); return; }
        whenReady(m, () => draw(m, data, current));
        if (data && !data.conflicts.length) toast(tr("wcal.layer.empty"));
      };
      const fresh = shared.data && Date.now() - shared.at < 5 * 60 * 1000;
      if (fresh) { ready(shared.data); return; }
      if (pendingFocus) { const f = pendingFocus; pendingFocus = null; focusOn(m, f); }
      const api = root.BirgeShell && root.BirgeShell.api && root.BirgeShell.api.v2;
      const req = api ? api("GET", "/works-conflicts") : fetch("/api/civic/v2/works-conflicts", { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then((r) => (r.ok ? r.json() : Promise.reject(Object.assign(new Error("HTTP " + r.status), { status: r.status }))));
      req.then((body) => {
        const works = Object.values(body.works || {});
        shared.data = { conflicts: body.conflicts || [], works, services: body.services || [], period: body.period };
        shared.at = Date.now();
        ready(shared.data);
      }, (err) => {
        if (err && (err.status === 401 || err.status === 403)) toast(tr("wcal.layer.staff"));
      });
    }
    function hideLayer(m) {
      layerOn = false;
      current = null;
      closeCard();
      remove(m || getMap({}));
    }
    function toast(text) {
      const el = h("div", { class: "wcal-toast bk-app bk-glass bk-glass--strong", role: "status", text });
      doc.body.append(el);
      setTimeout(() => el.remove(), 4200);
    }
    return { focus, showLayer, hideLayer, closeCard, get card() { return card; } };
  })();

  // Открыть календарь на конфликте (id конфликта или работы): для палитры R01 («Сцена 8») и ссылок соседей.
  function openConflict(id) {
    wantedConflict = id ? String(id) : null;
    const shell = root.BirgeShell;
    if (shell && typeof shell.setSection === "function") {
      if (shell.section === SCREEN_ID) {
        const el = doc.querySelector("[data-wcal]");
        if (el && el.birgeWorksCalendar) el.birgeWorksCalendar.reload();
      } else shell.setSection(SCREEN_ID);
      return true;
    }
    return false;
  }
  root.BirgeWorksCalendar = { mount, version: "wcal-r15-1", openConflict, map: MapView };

  // Оболочка R01: экран в меню акимата и слой «Конфликты работ» (место в меню решают R11 и R01).
  function register() {
    const shell = root.BirgeShell;
    if (!shell || typeof shell.registerScreen !== "function") return false;
    // Название — title {ru, kk} модуля, пока ключа wcal.title нет в словаре R11 (иначе меню показало бы сам ключ).
    const keyed = (key) => (I() && typeof I().has === "function" && I().has(key) ? key : undefined);
    shell.registerScreen({ id: SCREEN_ID, mount, modes: ["akimat"], titleKey: keyed("wcal.title"), title: { ru: KEYS.ru["wcal.title"], kk: KEYS.kk["wcal.title"] } });
    if (typeof shell.registerLayer === "function") {
      shell.registerLayer({ id: LAYER_ID, titleKey: keyed("wcal.layer"), title: { ru: KEYS.ru["wcal.layer"], kk: KEYS.kk["wcal.layer"] }, modes: ["akimat"],
        show: (m) => MapView.showLayer(m), hide: (m) => MapView.hideLayer(m) });
    }
    return true;
  }
  root.BirgeWorksCalendar.register = register;
  if (!register() && doc.readyState !== "complete") doc.addEventListener("DOMContentLoaded", register);
})(window);
