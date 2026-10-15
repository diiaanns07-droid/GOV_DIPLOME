/*
 * Birge · «Штаб ведомств» (R17, раунд 15): табло служб, совместные обращения, журнал передач, кризисный штаб.
 *
 *   <link rel="stylesheet" href="/civic/agencies/agencies.css">
 *   <script defer src="/civic/agencies/agencies.js"></script>        (после birge.js и ui-kit.js)
 *   BirgeAgencies.mount(root, { apiBase: "/api/civic/v2", api, lang, openSection, openTarget, close }) → { setLang, destroy }
 *   BirgeAgencies.openCrisis({ incident } | { template, district }) — кнопка «Открыть кризисный штаб» (R08, R13)
 *
 * В оболочке R01 экран встаёт сам: BirgeShell.registerScreen({id: "agencies", mount, modes: ["akimat"], …});
 * место в меню решает R11. Глубокие ссылки: #agencies/crisis=<id> и #agencies/crisis=new&template=blizzard&district=nura.
 * Данные — только API v2 (ui.civic_agencies): числа считает сервер, экран их показывает. Тексты — словарь R11
 * (ключи agencies.* и crisis.*); пока ключей нет — запасные строки ниже (список — INTEGRATION.txt R17).
 * Без библиотек; разметка через createElement (тексты служб и жителей не попадают в innerHTML).
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var SCRIPT = (doc.currentScript && doc.currentScript.src) || "";
  var SPRITE = SCRIPT ? SCRIPT.replace(/[^/]*$/, "") + "../ui-kit/icons.svg" : "/civic/ui-kit/icons.svg";
  var NBSP = " ";
  var SKELETON_DELAY = 150;                // скелетон не раньше 150 мс (COMMON «Качество»)
  var DISTRICTS = ["almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"];
  var PERIODS = [7, 30, 90];
  var KIND_ICONS = { blizzard: "snowflake", heat_outage: "home", water_outage: "droplet", flood: "droplet", other: "alert" };

  // Запасные тексты (до словаря R11). Казахский — на вычитку R11 (INTEGRATION.txt R17 §5).
  var KEYS = {
    ru: {
      "agencies.title": "Штаб ведомств",
      "agencies.tab.board": "Табло",
      "agencies.tab.joint": "Совместные",
      "agencies.tab.handoffs": "Передачи",
      "agencies.tab.crisis": "Кризис",
      "agencies.period": "Период",
      "agencies.period.days": "{n} дн.",
      "agencies.district.all": "Все районы",
      "agencies.refresh": "Обновить",
      "agencies.demo_note": "Пример: синтетические обращения до демо-мира",
      "agencies.source.r09": "Числа — из «Обращений»",
      "agencies.updated": "Обновлено {time}",
      "agencies.kpi.open": "открыто",
      "agencies.kpi.overdue": "просрочено",
      "agencies.kpi.joint": "совместных",
      "agencies.kpi.handoffs": "передач",
      "agencies.kpi.verified": "проверено жителями",
      "agencies.col.service": "Служба",
      "agencies.col.open": "Открыто",
      "agencies.col.deadline": "Срок ответа",
      "agencies.col.answer": "Ответ",
      "agencies.col.verified": "Проверено",
      "agencies.col.returned": "Вернули",
      "agencies.col.handoffs": "Передачи",
      "agencies.col.joint": "Вместе",
      "agencies.col.answer_hint": "Медиана: рабочих дней от подачи до первого ответа (ведущая служба)",
      "agencies.col.verified_hint": "Доля исправленных, которые жители проверили",
      "agencies.col.returned_hint": "Жители вернули в работу: проблема осталась",
      "agencies.col.handoffs_hint": "Передано в службу ↓ и из службы ↑ за период",
      "agencies.col.joint_hint": "Обращения, где работают две службы и больше",
      "agencies.days_short": "{n} дн.",
      "agencies.overdue_n": "{n} просроч.",
      "agencies.total": "Всего",
      "agencies.sort": "Сортировка",
      "agencies.sort.overdue": "по просрочке",
      "agencies.sort.open": "по открытым",
      "agencies.sort.answer": "по времени ответа",
      "agencies.sort.verified": "по доле проверенных",
      "agencies.sort.name": "по названию",
      "agencies.deadline.overdue": "просрочено",
      "agencies.deadline.today": "срок сегодня",
      "agencies.deadline.ok": "в срок",
      "agencies.deadline.answered": "ответ дан",
      "agencies.row.label": "{name}: открыто {open}, просрочено {overdue}",
      "agencies.detail.title": "Открытые обращения: {name}",
      "agencies.detail.empty": "Открытых обращений нет",
      "agencies.detail.inbox": "Открыть в «Обращениях»",
      "agencies.detail.more": "и ещё {n}",
      "agencies.joint.title": "Совместные обращения",
      "agencies.joint.hint": "Одно обращение — несколько служб, у каждой своя часть. Срок ответа жителю общий.",
      "agencies.joint.empty": "Совместных обращений пока нет",
      "agencies.joint.empty_text": "Когда обращению нужны две службы, оно появится здесь.",
      "agencies.joint.handoffs": "передач: {n}",
      "agencies.loop": "по кругу",
      "agencies.loop_hint": "Обращение вернулось в службу, которая уже передавала его",
      "agencies.handoffs.title": "Журнал передач",
      "agencies.handoffs.hint": "Передача не обнуляет срок ответа жителю.",
      "agencies.handoffs.pairs": "Чаще всего",
      "agencies.handoffs.empty": "Передач за период нет",
      "agencies.handoffs.empty_text": "Выберите период длиннее или другой район.",
      "agencies.handoffs.due": "срок тот же: до {date}",
      "agencies.handoffs.loops": "по кругу: {n}",
      "agencies.role.operator": "оператор",
      "agencies.role.editor": "сотрудник",
      "agencies.role.admin": "администратор",
      "agencies.role.demo": "пример",
      "agencies.role.staff": "сотрудник",
      "agencies.part.done": "сделано",
      "agencies.part.in_progress": "в работе",
      "agencies.part.accepted": "принято",
      "agencies.part.new": "новое",
      "agencies.part.rejected": "отклонено",
      "agencies.lead": "ведущая",
      "agencies.not_ready": "Штаб ведомств ещё не подключён в этой сборке",
      "agencies.not_ready_text": "Остальные разделы работают. Попробуйте позже.",
      "agencies.empty_board": "Обращений пока нет",
      "agencies.empty_board_text": "Табло заполнится, когда жители начнут сообщать о проблемах.",
      "agencies.staff_only": "Штаб ведомств — для сотрудников акимата",
      "crisis.title": "Кризисный штаб",
      "crisis.active": "Идёт",
      "crisis.closed": "Закрыт",
      "crisis.started": "с {time}",
      "crisis.duration": "идёт {d}",
      "crisis.hours": "{n} ч",
      "crisis.minutes": "{n} мин",
      "crisis.zone": "Зона: {zone}",
      "crisis.services": "Службы и задачи",
      "crisis.task.next": "Отметить: {status}",
      "crisis.task.todo": "не начато",
      "crisis.task.doing": "в работе",
      "crisis.task.done": "сделано",
      "crisis.task.add": "Добавить задачу",
      "crisis.task.text": "Что сделать",
      "crisis.updates": "Обновления",
      "crisis.update.public": "Жителям зоны",
      "crisis.update.internal": "Только штабу",
      "crisis.update.ru": "Текст на русском",
      "crisis.update.kk": "Текст на казахском",
      "crisis.update.send": "Отправить жителям",
      "crisis.update.save_note": "Сохранить заметку",
      "crisis.update.sent": "Обновление отправлено жителям зоны",
      "crisis.update.noted": "Заметка сохранена",
      "crisis.update.template": "Подставить текст шаблона",
      "crisis.update.empty": "Обновлений пока нет",
      "crisis.show_map": "Показать на карте",
      "crisis.close": "Закрыть кризис",
      "crisis.close.title": "Итог для жителей",
      "crisis.close.ru": "Итог на русском",
      "crisis.close.kk": "Итог на казахском",
      "crisis.close.confirm": "Закрыть и сообщить итог",
      "crisis.closed_ok": "Кризис закрыт, жители зоны увидят итог",
      "crisis.result": "Итог",
      "crisis.none": "Сейчас кризисов нет",
      "crisis.none_text": "Когда случится буран, авария или прорыв, откройте штаб: зона, задачи служб, обновления жителям.",
      "crisis.new": "Новый кризис",
      "crisis.new.title": "Новый кризисный штаб",
      "crisis.new.kind": "Что случилось",
      "crisis.new.zone": "Зона",
      "crisis.new.zone.district": "Район",
      "crisis.new.zone.yards": "Отдельные дворы",
      "crisis.new.yards_search": "Найти двор",
      "crisis.new.yards_picked": "Выбрано дворов: {n}",
      "crisis.new.name_ru": "Название на русском",
      "crisis.new.name_kk": "Название на казахском",
      "crisis.new.tasks": "Задачи служб",
      "crisis.new.first_update": "Первое обновление жителям",
      "crisis.new.create": "Открыть штаб",
      "crisis.new.created": "Штаб открыт, жители зоны получили первое обновление",
      "crisis.new.no_zone": "Выберите район или хотя бы один двор",
      "crisis.history": "Прошедшие",
      "crisis.kind.blizzard": "Буран",
      "crisis.kind.heat_outage": "Авария теплосети",
      "crisis.kind.water_outage": "Прорыв водопровода",
      "crisis.kind.flood": "Подтопление",
      "crisis.kind.other": "Другое",
      "crisis.duplicate": "Такой кризис в этой зоне уже ведётся — открыли его",
      "crisis.stale": "Задачу уже изменили — показали свежую версию",
      "crisis.error.save": "Не сохранилось. Проверьте связь и повторите.",
      "crisis.layer": "Кризис",
      "crisis.remove": "Убрать",
      "agencies.returned_pill": "вернули жители",
      "agencies.widen": "Показать за 90 дней по всем районам",
      "common.demo": "Пример",
      "common.state.loading": "Загружаем…",
      "common.state.error_title": "Не получилось загрузить",
      "common.state.network_title": "Нет связи с сервером",
      "common.action.cancel": "Отменить",
      "common.action.retry": "Повторить",
      "staff.login.submit": "Войти",
    },
    kk: {
      "agencies.title": "Ведомстволар штабы",
      "agencies.tab.board": "Табло",
      "agencies.tab.joint": "Бірлескен",
      "agencies.tab.handoffs": "Жіберулер",
      "agencies.tab.crisis": "Төтенше жағдай",
      "agencies.period": "Кезең",
      "agencies.period.days": "{n} күн",
      "agencies.district.all": "Барлық аудандар",
      "agencies.refresh": "Жаңарту",
      "agencies.demo_note": "Мысал: демо-әлемге дейінгі синтетикалық өтініштер",
      "agencies.source.r09": "Сандар — «Өтініштерден»",
      "agencies.updated": "Жаңартылды {time}",
      "agencies.kpi.open": "ашық",
      "agencies.kpi.overdue": "мерзімі өткен",
      "agencies.kpi.joint": "бірлескен",
      "agencies.kpi.handoffs": "жіберу",
      "agencies.kpi.verified": "тұрғындар тексерді",
      "agencies.col.service": "Қызмет",
      "agencies.col.open": "Ашық",
      "agencies.col.deadline": "Жауап мерзімі",
      "agencies.col.answer": "Жауап",
      "agencies.col.verified": "Тексерілді",
      "agencies.col.returned": "Қайтарды",
      "agencies.col.handoffs": "Жіберулер",
      "agencies.col.joint": "Бірге",
      "agencies.col.answer_hint": "Медиана: өтініш берілгеннен алғашқы жауапқа дейінгі жұмыс күндері (жетекші қызмет)",
      "agencies.col.verified_hint": "Түзетілгендердің ішінде тұрғындар тексергендерінің үлесі",
      "agencies.col.returned_hint": "Тұрғындар жұмысқа қайтарды: мәселе қалды",
      "agencies.col.handoffs_hint": "Кезеңде қызметке ↓ және қызметтен ↑ жіберілгені",
      "agencies.col.joint_hint": "Екі және одан көп қызмет жұмыс істейтін өтініштер",
      "agencies.days_short": "{n} күн",
      "agencies.overdue_n": "{n} мерзімі өткен",
      "agencies.total": "Барлығы",
      "agencies.sort": "Сұрыптау",
      "agencies.sort.overdue": "мерзімі өткені бойынша",
      "agencies.sort.open": "ашығы бойынша",
      "agencies.sort.answer": "жауап уақыты бойынша",
      "agencies.sort.verified": "тексерілген үлесі бойынша",
      "agencies.sort.name": "атауы бойынша",
      "agencies.deadline.overdue": "мерзімі өткен",
      "agencies.deadline.today": "мерзімі бүгін",
      "agencies.deadline.ok": "мерзімінде",
      "agencies.deadline.answered": "жауап берілді",
      "agencies.row.label": "{name}: ашық {open}, мерзімі өткен {overdue}",
      "agencies.detail.title": "Ашық өтініштер: {name}",
      "agencies.detail.empty": "Ашық өтініш жоқ",
      "agencies.detail.inbox": "«Өтініштерде» ашу",
      "agencies.detail.more": "тағы {n}",
      "agencies.joint.title": "Бірлескен өтініштер",
      "agencies.joint.hint": "Бір өтініш — бірнеше қызмет, әрқайсысының өз бөлігі бар. Тұрғынға жауап мерзімі ортақ.",
      "agencies.joint.empty": "Әзірге бірлескен өтініш жоқ",
      "agencies.joint.empty_text": "Өтінішке екі қызмет керек болса, ол осында шығады.",
      "agencies.joint.handoffs": "жіберу: {n}",
      "agencies.loop": "шеңбер бойынша",
      "agencies.loop_hint": "Өтініш оны бұрын жіберген қызметке қайта оралды",
      "agencies.handoffs.title": "Жіберулер журналы",
      "agencies.handoffs.hint": "Жіберу тұрғынға жауап мерзімін жаңартпайды.",
      "agencies.handoffs.pairs": "Жиі кездесетіні",
      "agencies.handoffs.empty": "Кезеңде жіберу болған жоқ",
      "agencies.handoffs.empty_text": "Ұзағырақ кезеңді немесе басқа ауданды таңдаңыз.",
      "agencies.handoffs.due": "мерзімі сол: {date} дейін",
      "agencies.handoffs.loops": "шеңбер бойынша: {n}",
      "agencies.role.operator": "оператор",
      "agencies.role.editor": "қызметкер",
      "agencies.role.admin": "әкімші",
      "agencies.role.demo": "мысал",
      "agencies.role.staff": "қызметкер",
      "agencies.part.done": "орындалды",
      "agencies.part.in_progress": "жұмыста",
      "agencies.part.accepted": "қабылданды",
      "agencies.part.new": "жаңа",
      "agencies.part.rejected": "қабылданбады",
      "agencies.lead": "жетекші",
      "agencies.not_ready": "Ведомстволар штабы бұл жинақта әлі қосылмаған",
      "agencies.not_ready_text": "Басқа бөлімдер жұмыс істейді. Кейінірек көріңіз.",
      "agencies.empty_board": "Әзірге өтініш жоқ",
      "agencies.empty_board_text": "Тұрғындар мәселе туралы хабарлай бастағанда табло толады.",
      "agencies.staff_only": "Ведомстволар штабы — әкімдік қызметкерлеріне арналған",
      "crisis.title": "Төтенше жағдай штабы",
      "crisis.active": "Жүріп жатыр",
      "crisis.closed": "Аяқталды",
      "crisis.started": "{time} бастап",
      "crisis.duration": "{d} бойы",
      "crisis.hours": "{n} сағ",
      "crisis.minutes": "{n} мин",
      "crisis.zone": "Аймақ: {zone}",
      "crisis.services": "Қызметтер мен тапсырмалар",
      "crisis.task.next": "Белгілеу: {status}",
      "crisis.task.todo": "басталмаған",
      "crisis.task.doing": "жұмыста",
      "crisis.task.done": "орындалды",
      "crisis.task.add": "Тапсырма қосу",
      "crisis.task.text": "Не істеу керек",
      "crisis.updates": "Жаңартулар",
      "crisis.update.public": "Аймақ тұрғындарына",
      "crisis.update.internal": "Тек штабқа",
      "crisis.update.ru": "Орысша мәтін",
      "crisis.update.kk": "Қазақша мәтін",
      "crisis.update.send": "Тұрғындарға жіберу",
      "crisis.update.save_note": "Жазбаны сақтау",
      "crisis.update.sent": "Жаңарту аймақ тұрғындарына жіберілді",
      "crisis.update.noted": "Жазба сақталды",
      "crisis.update.template": "Үлгі мәтінін қою",
      "crisis.update.empty": "Әзірге жаңарту жоқ",
      "crisis.show_map": "Картадан көрсету",
      "crisis.close": "Төтенше жағдайды жабу",
      "crisis.close.title": "Тұрғындарға қорытынды",
      "crisis.close.ru": "Орысша қорытынды",
      "crisis.close.kk": "Қазақша қорытынды",
      "crisis.close.confirm": "Жабу және қорытындыны хабарлау",
      "crisis.closed_ok": "Төтенше жағдай жабылды, аймақ тұрғындары қорытындыны көреді",
      "crisis.result": "Қорытынды",
      "crisis.none": "Қазір төтенше жағдай жоқ",
      "crisis.none_text": "Боран, апат немесе құбыр жарылса, штабты ашыңыз: аймақ, қызметтердің тапсырмалары, тұрғындарға жаңартулар.",
      "crisis.new": "Жаңа төтенше жағдай",
      "crisis.new.title": "Жаңа төтенше жағдай штабы",
      "crisis.new.kind": "Не болды",
      "crisis.new.zone": "Аймақ",
      "crisis.new.zone.district": "Аудан",
      "crisis.new.zone.yards": "Жеке аулалар",
      "crisis.new.yards_search": "Аула іздеу",
      "crisis.new.yards_picked": "Таңдалған аула: {n}",
      "crisis.new.name_ru": "Орысша атауы",
      "crisis.new.name_kk": "Қазақша атауы",
      "crisis.new.tasks": "Қызметтердің тапсырмалары",
      "crisis.new.first_update": "Тұрғындарға алғашқы жаңарту",
      "crisis.new.create": "Штабты ашу",
      "crisis.new.created": "Штаб ашылды, аймақ тұрғындары алғашқы жаңартуды алды",
      "crisis.new.no_zone": "Ауданды немесе кемінде бір ауланы таңдаңыз",
      "crisis.history": "Өткендері",
      "crisis.kind.blizzard": "Боран",
      "crisis.kind.heat_outage": "Жылу желісіндегі апат",
      "crisis.kind.water_outage": "Су құбырының жарылуы",
      "crisis.kind.flood": "Су басу",
      "crisis.kind.other": "Басқа",
      "crisis.duplicate": "Бұл аймақта мұндай жағдай жүріп жатыр — соны аштық",
      "crisis.stale": "Тапсырма өзгертіліп қойған — жаңа нұсқасын көрсеттік",
      "crisis.error.save": "Сақталмады. Байланысты тексеріп, қайталаңыз.",
      "crisis.layer": "Төтенше жағдай",
      "crisis.remove": "Алып тастау",
      "agencies.returned_pill": "тұрғындар қайтарды",
      "agencies.widen": "Барлық аудандар бойынша 90 күнді көрсету",
      "common.demo": "Мысал",
      "common.state.loading": "Жүктеліп жатыр…",
      "common.state.error_title": "Жүктеу мүмкін болмады",
      "common.state.network_title": "Сервермен байланыс жоқ",
      "common.action.cancel": "Болдырмау",
      "common.action.retry": "Қайталау",
      "staff.login.submit": "Кіру",
    },
  };
  // Подписи районов — словарь R11 (district.<id>); запасные — здесь.
  var DISTRICT_NAMES = {
    ru: { almaty: "Алматы", baikonur: "Байконур", esil: "Есиль", nura: "Нура", saraishyk: "Сарайшык", saryarka: "Сарыарка" },
    kk: { almaty: "Алматы", baikonur: "Байқоңыр", esil: "Есіл", nura: "Нұра", saraishyk: "Сарайшық", saryarka: "Сарыарқа" },
  };

  // ------------------------------------------------------------------ тексты и формат
  function I() { return root.BirgeI18n || null; }
  function lang() { var i = I(); return i && typeof i.getLang === "function" && i.getLang() === "kk" ? "kk" : "ru"; }
  function fill(text, params) {
    return String(text).replace(/\{(\w+)\}/g, function (w, n) {
      if (!params || params[n] == null) return w;
      return typeof params[n] === "number" ? num(params[n]) : String(params[n]);
    });
  }
  function tr(key, params) {
    var i = I();
    if (i && typeof i.has === "function" && (i.has(key) || i.has(key, "ru"))) return i.t(key, params);
    var dict = KEYS[lang()] || KEYS.ru;
    return fill(dict[key] != null ? dict[key] : KEYS.ru[key] != null ? KEYS.ru[key] : key, params);
  }
  function num(n) {
    var i = I();
    if (i && typeof i.formatNumber === "function") return i.formatNumber(n);
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP).replace(".", ",");
  }
  function pct(share) { return share == null ? "—" : Math.round(share * 100) + NBSP + "%"; }
  function astana(iso) {
    var t = Date.parse(iso);
    if (!isFinite(t)) return null;
    var d = new Date(t + 5 * 3600000);
    return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate(), hh: d.getUTCHours(), mm: d.getUTCMinutes() };
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function fmtDate(iso) {
    var i = I();
    if (i && typeof i.formatDate === "function") return i.formatDate(iso);
    var p = astana(iso);
    return p ? p.d + "." + pad(p.m) : "—";
  }
  function fmtTime(iso) { var p = astana(iso); return p ? pad(p.hh) + ":" + pad(p.mm) : "—"; }
  function fmtWhen(iso) {
    var p = astana(iso), now = astana(new Date().toISOString());
    if (!p) return "—";
    return p.y === now.y && p.m === now.m && p.d === now.d ? fmtTime(iso) : fmtDate(iso) + ", " + fmtTime(iso);
  }
  function duration(fromIso, toIso) {
    var ms = (toIso ? Date.parse(toIso) : Date.now()) - Date.parse(fromIso);
    if (!isFinite(ms) || ms < 0) return "";
    var hours = Math.floor(ms / 3600000);
    if (hours >= 48) return tr("agencies.days_short", { n: Math.floor(hours / 24) });
    if (hours >= 1) return tr("crisis.hours", { n: hours });
    return tr("crisis.minutes", { n: Math.max(1, Math.round(ms / 60000)) });
  }
  function districtName(id) {
    var i = I();
    if (i && i.has && i.has("district." + id)) return i.t("district." + id);
    return (DISTRICT_NAMES[lang()] || DISTRICT_NAMES.ru)[id] || id;
  }
  function catName(id) {
    var i = I();
    if (id && i && i.has && i.has("cat." + id)) return i.t("cat." + id);
    return id || "";
  }
  function pick(obj, base) {
    if (!obj) return "";
    var l = lang();
    return obj[base + "_" + l] || obj[base + "_" + (l === "kk" ? "ru" : "kk")] || "";
  }

  // ------------------------------------------------------------------ DOM
  function h(tag, attrs, children) {
    var el = doc.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === "text") el.textContent = v;
      else if (k === "class") el.className = v;
      else if (k === "style" && typeof v === "object") Object.keys(v).forEach(function (p) { el.style.setProperty(p, v[p]); });
      else if (k.slice(0, 2) === "on" && typeof v === "function") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    (children || []).forEach(function (c) {
      if (c == null || c === false) return;
      el.appendChild(typeof c === "string" || typeof c === "number" ? doc.createTextNode(String(c)) : c);
    });
    return el;
  }
  function svg(id, cls) {
    var NS = "http://www.w3.org/2000/svg", s = doc.createElementNS(NS, "svg"), use = doc.createElementNS(NS, "use");
    s.setAttribute("class", cls || "ic");
    s.setAttribute("aria-hidden", "true");
    s.setAttribute("focusable", "false");
    use.setAttribute("href", SPRITE + "#" + id);
    s.appendChild(use);
    return s;
  }
  // Статус-иконка ui-kit (правило 3 Linear): пустой круг · половина · круг с галочкой · заполненный.
  var STATUS_SHAPE = { new: "st-ring", accepted: "st-ring", todo: "st-ring", in_progress: "st-half", doing: "st-half",
    done: "st-done", fixed: "st-ring-check", verified: "st-done", rejected: "st-reject" };
  function statusIcon(status, size) {
    var s = svg(STATUS_SHAPE[status] || "st-ring", "bk-st-ic");
    s.setAttribute("data-status", status === "todo" ? "new" : status === "doing" ? "in_progress" : status === "done" ? "verified" : status);
    s.setAttribute("width", String(size || 14));
    s.setAttribute("height", String(size || 14));
    return s;
  }
  function demoTag() { return h("span", { class: "ag-demo" }, [tr("common.demo")]); }

  // ------------------------------------------------------------------ сеть
  // Клиент API v2. Запись сотрудника — с X-CSRF-Token: из оболочки (CivicShell.csrfToken) или, если её токена ещё
  // нет (сотрудник не открывал редактор), из GET /api/civic/v1/session — как R08 «Службы». Клиент оболочки
  // (opts.api.v2) не берём: он шлёт токен только из CivicShell и на свежей вкладке отправил бы запись без него.
  function makeClient(opts) {
    var cached = null;
    function csrf() {
      try {
        var cs = root.CivicShell;
        var token = cs && typeof cs.csrfToken === "function" ? cs.csrfToken() : null;
        if (token) return Promise.resolve(token);
      } catch (e) { /* оболочки нет */ }
      if (cached) return Promise.resolve(cached);
      return fetch("/api/civic/v1/session", { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (b) {
          var d = b && b.data && typeof b.data === "object" ? b.data : b || {};
          cached = d.authenticated && typeof d.csrf_token === "string" ? d.csrf_token : null;
          return cached;
        }, function () { return null; });
    }
    function send(method, path, body, token) {
      var headers = { Accept: "application/json" };
      if (body !== undefined) headers["Content-Type"] = "application/json";
      if (token) headers["X-CSRF-Token"] = token;
      return fetch(opts.apiBase + path, { method: method, headers: headers, credentials: "same-origin",
        body: body !== undefined ? JSON.stringify(body) : undefined })
        .then(function (r) {
          return r.text().then(function (text) {
            var data = null;
            try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
            if (!r.ok) {
              throw { status: r.status, error: (data && data.error) || "error", message: data && data.message,
                field: data && data.field, current: data && data.current };
            }
            return data;
          });
        }, function () { throw { status: 0, error: "network" }; });
    }
    return function request(method, path, body) {
      if (method === "GET") return send(method, path, body, null);
      return csrf().then(function (token) {
        return send(method, path, body, token).catch(function (err) {
          // Токен устарел (сессию обновили в другой вкладке) — один повтор со свежим.
          if (err && err.error === "csrf_failed" && cached) {
            cached = null;
            return csrf().then(function (fresh) { return send(method, path, body, fresh); });
          }
          throw err;
        });
      });
    };
  }

  // Состояние «ошибка» для блока: нет входа / модуль не подключён / нет связи.
  function errorState(box, err, retry) {
    var UI = root.BirgeUI;
    if (err && (err.status === 401 || err.status === 403)) {
      var openLogin = function () {
        var cs = root.CivicShell;
        if (root.BirgeShell) root.BirgeShell.setSection("map");
        if (cs && typeof cs.openEditor === "function") cs.openEditor();
      };
      if (UI && UI.loginState) return UI.loginState(box, openLogin, { title: tr("agencies.staff_only") });
      box.replaceChildren(h("div", { class: "bk-empty", role: "status" }, [
        h("p", { class: "bk-empty__title", text: tr("agencies.staff_only") }),
        h("button", { class: "bk-btn bk-btn--primary", type: "button", onclick: openLogin, text: tr("staff.login.submit") })]));
      return;
    }
    var notReady = err && err.status === 503;
    if (UI && UI.state) {
      return UI.state(box, "error", {
        title: notReady ? tr("agencies.not_ready") : undefined,
        text: notReady ? tr("agencies.not_ready_text") : undefined,
        action: { onClick: retry },
      });
    }
    box.replaceChildren(h("div", { class: "bk-error", role: "alert" }, [
      h("p", { class: "bk-error__title", text: notReady ? tr("agencies.not_ready") : tr("common.state.network_title") }),
      h("button", { class: "bk-btn", type: "button", onclick: retry, text: tr("common.action.retry") })]));
  }
  // Пусто (поправка П1, правило 2): одна маленькая монохромная иконка набора ui-kit (48 px) + короткий текст + одна
  // кнопка. Без больших иллюстраций и «сценок».
  function emptyState(box, title, text, action, iconName) {
    var UI = root.BirgeUI;
    if (UI && UI.state) return UI.state(box, "empty", { title: title, text: text, action: action, icon: iconName || "list" });
    var ic = svg("i-" + (iconName || "list"), "ic ic--48");
    box.replaceChildren(h("div", { class: "bk-empty", role: "status" }, [ic,
      h("p", { class: "bk-empty__title", text: title }), text ? h("p", { class: "bk-empty__text", text: text }) : null,
      action ? h("button", { class: "bk-btn bk-btn--primary", type: "button", onclick: action.onClick, text: action.label }) : null]));
  }
  function toast(text, type) {
    var UI = root.BirgeUI;
    if (UI && UI.toast) UI.toast(text, type ? { type: type } : undefined);
  }

  // ------------------------------------------------------------------ экран
  var mounted = null;     // текущий экземпляр (для openCrisis)
  var pending = null;     // глубокая ссылка, которую ещё не открыли

  function mount(rootEl, options) {
    var opts = { apiBase: "/api/civic/v2", titleTag: "h2" };
    Object.keys(options || {}).forEach(function (k) { if (options[k] != null) opts[k] = options[k]; });
    var request = makeClient(opts);
    var S = {
      tab: "board", days: 30, district: "", sort: { key: "overdue", dir: -1 },
      meta: null, board: null, joint: null, handoffs: null, incidents: null, detail: {},
      open: null, openItems: {}, crisis: { id: null, form: null, closing: false, composer: { ru: "", kk: "", public: true } },
      loading: {}, slow: {}, error: {}, seq: 0, alive: true, lang: lang(),
    };
    try {
      var saved = JSON.parse(root.sessionStorage.getItem("birge.agencies") || "{}");
      if (["board", "joint", "handoffs", "crisis"].indexOf(saved.tab) >= 0) S.tab = saved.tab;
      if (PERIODS.indexOf(saved.days) >= 0) S.days = saved.days;
      if (DISTRICTS.indexOf(saved.district) >= 0) S.district = saved.district;
    } catch (e) { /* приватный режим: умолчания */ }
    function remember() {
      try { root.sessionStorage.setItem("birge.agencies", JSON.stringify({ tab: S.tab, days: S.days, district: S.district })); } catch (e) { /* нет хранилища */ }
    }

    rootEl.classList.add("ag", "bk-app");
    rootEl.setAttribute("data-agencies", "");
    var headBox = h("div", { class: "ag-head" });
    var bodyBox = h("div", { class: "ag-body", "aria-live": "polite" });
    rootEl.replaceChildren(headBox, bodyBox);

    // ---------------------------------------------------------------- загрузка с задержкой скелетона
    function load(key, path, after) {
      S.loading[key] = true;
      S.slow[key] = false;
      S.error[key] = null;
      // Скелетон — только если ответ дольше 150 мс: быстрый ответ не мигает (правило 4 Linear).
      var timer = setTimeout(function () { if (S.loading[key] && S.alive) { S.slow[key] = true; render(); } }, SKELETON_DELAY);
      return request("GET", path).then(function (data) {
        if (!S.alive) return;
        S[key] = data;
        if (after) after(data);
      }, function (err) {
        if (!S.alive) return;
        S.error[key] = err || { status: 0 };
      }).then(function () {
        clearTimeout(timer);
        S.loading[key] = false;
        S.slow[key] = false;
        if (S.alive) render();
      });
    }
    function query() {
      return "?days=" + S.days + (S.district ? "&district=" + S.district : "");
    }
    function loadMeta() {
      if (S.meta) return Promise.resolve();
      return request("GET", "/agencies").then(function (d) { S.meta = d; }, function () { S.meta = S.meta || null; });
    }
    function refresh() {
      S.openItems = {};
      loadMeta().then(function () {
        if (S.tab === "board") load("board", "/agencies/board" + query());
        else if (S.tab === "joint") load("joint", "/agencies/joint" + query());
        else if (S.tab === "handoffs") load("handoffs", "/agencies/handoffs" + query());
        else loadIncidents();
      });
      render();
    }
    function loadIncidents(selectId) {
      return load("incidents", "/incidents?status=all", function (d) {
        var items = (d && d.items) || [];
        var active = items.filter(function (x) { return x.status === "active"; });
        if (selectId) S.crisis.id = selectId;
        else if (!S.crisis.id || !items.some(function (x) { return x.id === S.crisis.id; })) S.crisis.id = active[0] ? active[0].id : null;
        if (S.crisis.id) loadIncident(S.crisis.id);
      });
    }
    function loadIncident(id) {
      return request("GET", "/incidents/" + encodeURIComponent(id)).then(function (d) {
        if (!S.alive) return;
        S.detail[id] = d.incident;
        render();
      }, function (err) {
        if (!S.alive) return;
        S.error.incident = err;
        render();
      });
    }

    // ---------------------------------------------------------------- шапка
    function renderHead() {
      var tabs = h("div", { class: "bk-tabs", role: "tablist", "aria-label": tr("agencies.title") },
        ["board", "joint", "handoffs", "crisis"].map(function (id) {
          var count = null;
          if (id === "crisis" && S.incidents) {
            var n = (S.incidents.items || []).filter(function (x) { return x.status === "active"; }).length;
            if (n) count = h("span", { class: "bk-num", text: String(n) });
          }
          return h("button", { type: "button", role: "tab", value: id, "aria-selected": String(S.tab === id), "data-tab": id,
            tabindex: S.tab === id ? "0" : "-1" }, [tr("agencies.tab." + id), count]);
        }));
      tabs.addEventListener("click", function (e) {
        var b = e.target.closest('[role="tab"]');
        if (b && b.value !== S.tab) setTab(b.value);
      });
      tabs.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        var ids = ["board", "joint", "handoffs", "crisis"], i = ids.indexOf(S.tab);
        e.preventDefault();
        setTab(ids[(i + (e.key === "ArrowRight" ? 1 : ids.length - 1)) % ids.length], true);
      });
      var filters = h("div", { class: "ag-filters" });
      if (S.tab !== "crisis") {
        var seg = h("div", { class: "ag-seg", role: "group", "aria-label": tr("agencies.period") }, PERIODS.map(function (d) {
          return h("button", { type: "button", value: String(d), "aria-pressed": String(S.days === d), text: tr("agencies.period.days", { n: d }) });
        }));
        seg.addEventListener("click", function (e) {
          var b = e.target.closest("button");
          if (!b || Number(b.value) === S.days) return;
          S.days = Number(b.value);
          remember();
          refresh();
        });
        var select = h("select", { class: "ag-select", "aria-label": tr("agencies.district.all") },
          [h("option", { value: "", text: tr("agencies.district.all") })].concat(DISTRICTS.map(function (d) {
            return h("option", { value: d, text: districtName(d) });
          })));
        select.value = S.district;
        select.addEventListener("change", function () {
          S.district = select.value;
          remember();
          refresh();
        });
        filters.append(seg, select);
      }
      var again = h("button", { type: "button", class: "ag-iconbtn", "aria-label": tr("agencies.refresh"), title: tr("agencies.refresh"),
        onclick: refresh }, [svg("i-refresh")]);
      filters.appendChild(again);
      var title = h(opts.titleTag === "h1" ? "h1" : "h2", { class: "ag-title", text: tr("agencies.title") });
      // «Пример» — на виду, рядом с заголовком, если числа вкладки синтетические (COMMON «Честность»).
      var current = S.tab === "crisis" ? null : S[S.tab];
      var demo = current && (current.source === "fixture" || current.demo) ? h("span", { class: "ag-demo ag-demo--head",
        title: current.source === "fixture" ? tr("agencies.demo_note") : null }, [tr("common.demo")]) : null;
      headBox.replaceChildren.apply(headBox, [title, demo, tabs, filters].filter(Boolean));
    }
    function setTab(id, focus) {
      S.tab = id;
      S.open = null;
      remember();
      refresh();
      if (focus) {
        var b = headBox.querySelector('[data-tab="' + id + '"]');
        if (b) b.focus();
      }
    }

    function noteLine(data) {
      if (!data) return null;
      var bits = [];
      if (data.source === "fixture") bits.push(h("span", { text: tr("agencies.demo_note") }));
      else if (data.source === "r09") bits.push(h("span", { text: tr("agencies.source.r09") }));
      if (data.generated_at) bits.push(h("span", { text: tr("agencies.updated", { time: fmtTime(data.generated_at) }) }));
      return h("p", { class: "ag-note" }, bits);
    }
    function profileMap() {
      var map = {};
      var list = (S.board && S.board.profiles) || (S.meta && S.meta.services) || [];
      list.forEach(function (p) { map[p.id] = p; });
      return map;
    }
    function serviceName(id) {
      var p = profileMap()[id];
      var i = I();
      if (p && p.name_edited) return p[lang()] || p.ru || id;      // акимат переименовал — его название
      if (i && i.has && i.has("service." + id)) return i.t("service." + id);
      return (p && (p[lang()] || p.ru)) || id;
    }
    // Значок службы — монохромный, набор ui-kit (П1: цвет только у важного — просрочки и сроков). Цвет вида службы
    // из профиля §5.4 остаётся для полос календаря работ R12.
    function serviceBadge(id) {
      var p = profileMap()[id] || {};
      return h("span", { class: "ag-svc__ic" }, [svg("i-" + (p.icon || "dots"))]);
    }

    // ---------------------------------------------------------------- табло
    var SORTS = {
      overdue: function (r) { return [r.overdue, r.open, -(r.median_answer_days == null ? 99 : r.median_answer_days)]; },
      open: function (r) { return [r.open, r.overdue]; },
      answer: function (r) { return [r.median_answer_days == null ? -1 : r.median_answer_days, r.open]; },
      verified: function (r) { return [r.verified_share == null ? -1 : r.verified_share, r.fixed]; },
      returned: function (r) { return [r.returned, r.open]; },
      handoffs: function (r) { return [r.handoffs_in + r.handoffs_out, r.handoffs_in]; },
      joint: function (r) { return [r.joint, r.open]; },
    };
    function sortedRows(rows) {
      var key = S.sort.key, dir = S.sort.dir;
      var copy = rows.slice();
      copy.sort(function (a, b) {
        if (key === "name") return dir * serviceName(a.service).localeCompare(serviceName(b.service), lang());
        var x = SORTS[key](a), y = SORTS[key](b);
        for (var i = 0; i < x.length; i++) if (x[i] !== y[i]) return dir * (x[i] - y[i]);
        return serviceName(a.service).localeCompare(serviceName(b.service), lang());
      });
      return copy;
    }
    function renderBoard() {
      var data = S.board;
      if (S.error.board) return errorState(bodyBox, S.error.board, refresh);
      if (!data) return bodyBox.replaceChildren(S.slow.board ? boardSkeleton() : h("div", { "aria-busy": "true" }));
      var rows = data.services || [];
      var totals = data.totals || {};
      var kpis = h("div", { class: "ag-kpis" }, [
        kpi(totals.open, tr("agencies.kpi.open")),
        kpi(totals.overdue, tr("agencies.kpi.overdue"), totals.overdue > 0),
        kpi(totals.joint, tr("agencies.kpi.joint")),
        kpi(totals.handoffs, tr("agencies.kpi.handoffs")),
        kpi(totals.verified_share == null ? "—" : pct(totals.verified_share), tr("agencies.kpi.verified")),
      ]);
      var table = h("div", { class: "ag-table", role: "table", "aria-label": tr("agencies.tab.board") });
      var cols = [["name", "agencies.col.service"], ["open", "agencies.col.open"], ["overdue", "agencies.col.deadline"],
        ["answer", "agencies.col.answer", "agencies.col.answer_hint"], ["verified", "agencies.col.verified", "agencies.col.verified_hint"],
        ["returned", "agencies.col.returned", "agencies.col.returned_hint"], ["handoffs", "agencies.col.handoffs", "agencies.col.handoffs_hint"],
        ["joint", "agencies.col.joint", "agencies.col.joint_hint"]];
      var head = h("div", { class: "ag-thead", role: "row" }, cols.map(function (c) {
        var active = S.sort.key === c[0];
        var b = h("button", { type: "button", class: "ag-th", role: "columnheader", "data-sort": c[0], title: c[2] ? tr(c[2]) : null,
          "aria-sort": active ? (S.sort.dir < 0 ? "descending" : "ascending") : "none" },
          [tr(c[1]), h("span", { class: "ag-th__arrow", "aria-hidden": "true", text: active ? (S.sort.dir < 0 ? "↓" : "↑") : "" })]);
        b.addEventListener("click", function () {
          if (S.sort.key === c[0]) S.sort.dir = -S.sort.dir;
          else S.sort = { key: c[0], dir: c[0] === "name" ? 1 : -1 };
          render();
        });
        return b;
      }));
      table.appendChild(head);
      var maxOpen = Math.max.apply(null, rows.map(function (r) { return r.open; }).concat([1]));
      sortedRows(rows).forEach(function (r) {
        table.appendChild(boardRow(r, maxOpen));
        if (S.open === r.service) table.appendChild(detailBox(r));
      });
      var sortbar = h("label", { class: "ag-sortbar" }, [tr("agencies.sort")]);
      var sortSelect = h("select", { class: "ag-select" }, ["overdue", "open", "answer", "verified", "name"].map(function (k) {
        return h("option", { value: k, text: tr("agencies.sort." + k) });
      }));
      sortSelect.value = S.sort.key in SORTS || S.sort.key === "name" ? S.sort.key : "overdue";
      sortSelect.addEventListener("change", function () {
        S.sort = { key: sortSelect.value, dir: sortSelect.value === "name" ? 1 : -1 };
        render();
      });
      sortbar.appendChild(sortSelect);
      var legend = h("p", { class: "ag-note ag-legend", "aria-hidden": "true" }, ["overdue", "today", "ok", "answered"].map(function (k) {
        return h("span", { class: "ag-legend__item" }, [h("span", { class: "ag-legend__sw ag-bar__" + k }), tr("agencies.deadline." + k)]);
      }));
      var parts = [kpis, sortbar, table, legend, noteLine(data)];
      if (data.empty) parts.splice(1, 0, h("p", { class: "ag-note", text: tr("agencies.empty_board_text") }));
      bodyBox.replaceChildren.apply(bodyBox, parts.filter(Boolean));
    }
    function kpi(value, label, alert) {
      return h("div", { class: "ag-kpi" + (alert ? " ag-kpi--alert" : "") }, [
        h("span", { class: "ag-kpi__value", text: typeof value === "number" ? num(value) : String(value == null ? "—" : value) }),
        h("span", { class: "ag-kpi__label", text: label })]);
    }
    function boardSkeleton() {
      var box = h("div", { class: "ag-table", "aria-hidden": "true" });
      for (var i = 0; i < 12; i++) box.appendChild(h("div", { class: "ag-skel-row" }, [h("span", { class: "bk-skel", style: { width: (40 + (i * 13) % 45) + "%" } })]));
      return h("div", { "aria-busy": "true" }, [h("p", { class: "bk-meta", role: "status", text: tr("common.state.loading") }), box]);
    }
    function deadlineBar(r, maxOpen) {
      var d = r.deadline || {};
      var total = r.open || 0;
      // Длина полосы — сколько открыто (относительно самой загруженной службы), цвета — состояние срока.
      var share = total ? Math.max(8, Math.round((total / Math.max(1, maxOpen)) * 100)) : 0;
      var bar = h("span", { class: "ag-bar", "aria-hidden": "true", style: { "--ag-fill": share + "%" } });
      ["overdue", "today", "ok", "answered"].forEach(function (k) {
        if (d[k]) bar.appendChild(h("span", { class: "ag-bar__" + k, style: { "flex-grow": String(d[k]) } }));
      });
      var note = r.overdue ? h("span", { class: "ag-deadline__note ag-num--alert", text: num(r.overdue) })
        : h("span", { class: "ag-deadline__note ag-num--zero", text: total ? "0" : "" });
      return h("span", { class: "ag-deadline", role: "cell", "data-col": "deadline",
        title: ["overdue", "today", "ok", "answered"].map(function (k) { return tr("agencies.deadline." + k) + ": " + (d[k] || 0); }).join(" · ") },
        [bar, note]);
    }
    function boardRow(r, maxOpen) {
      var name = serviceName(r.service);
      var quiet = !r.open && !r.received;
      var row = h("button", { type: "button", class: "ag-row" + (quiet ? " ag-row--quiet" : ""), role: "row", "data-service": r.service,
        "aria-expanded": String(S.open === r.service),
        "aria-label": tr("agencies.row.label", { name: name, open: r.open, overdue: r.overdue }) }, [
        h("span", { class: "ag-svc", role: "cell" }, [serviceBadge(r.service), h("span", { class: "ag-svc__name", text: name })]),
        h("span", { class: "ag-num" + (r.open ? "" : " ag-num--zero"), role: "cell", "data-col": "open", text: num(r.open) }),
        deadlineBar(r, maxOpen),
        h("span", { class: "ag-num" + (r.median_answer_days == null ? " ag-num--zero" : ""), role: "cell", "data-col": "answer",
          text: r.median_answer_days == null ? "—" : tr("agencies.days_short", { n: r.median_answer_days }) }),
        h("span", { class: "ag-share", role: "cell", "data-col": "verified" }, [
          h("span", { class: "ag-share__track", "aria-hidden": "true" }, [h("span", { class: "ag-share__fill",
            style: { width: Math.round((r.verified_share || 0) * 100) + "%" } })]),
          h("span", { class: "ag-num" + (r.verified_share == null ? " ag-num--zero" : ""), text: pct(r.verified_share) })]),
        h("span", { class: "ag-num" + (r.returned ? "" : " ag-num--zero"), role: "cell", "data-col": "returned", text: num(r.returned) }),
        h("span", { class: "ag-flow", role: "cell", "data-col": "handoffs" }, [
          h("span", { "data-zero": r.handoffs_in ? null : "", text: "↓" + num(r.handoffs_in) }),
          h("span", { "data-zero": r.handoffs_out ? null : "", text: "↑" + num(r.handoffs_out) })]),
        h("span", { class: "ag-num" + (r.joint ? "" : " ag-num--zero"), role: "cell", "data-col": "joint", text: num(r.joint) }),
        h("span", { class: "ag-mobile-meta" }, [
          h("span", { text: tr("agencies.kpi.overdue") + ": " + num(r.overdue) }),
          h("span", { text: tr("agencies.col.answer") + ": " + (r.median_answer_days == null ? "—" : tr("agencies.days_short", { n: r.median_answer_days })) }),
          h("span", { text: tr("agencies.col.verified") + ": " + pct(r.verified_share) })]),
      ]);
      row.addEventListener("click", function () {
        S.open = S.open === r.service ? null : r.service;
        if (S.open && !S.openItems[r.service]) loadServiceItems(r.service);
        render();
        var again = bodyBox.querySelector('[data-service="' + r.service + '"]');
        if (again) again.focus();
      });
      return row;
    }
    function loadServiceItems(service) {
      S.openItems[service] = { loading: true };
      request("GET", "/agencies/board" + query() + "&service=" + encodeURIComponent(service)).then(function (d) {
        S.openItems[service] = { items: d.items || [] };
      }, function (err) {
        S.openItems[service] = { error: err || { status: 0 } };
      }).then(function () { if (S.alive) render(); });
    }
    function deadlinePill(info, tab) {
      if (tab === "overdue" || (info && info.state === "overdue")) {
        var n = info && info.overdue_working_days, i = I();
        var text = n && i && i.has && i.has("deadline.overdue") ? i.t("deadline.overdue", { n: n }) : tr("agencies.deadline.overdue");
        return h("span", { class: "ag-pill ag-pill--danger", text: text });
      }
      if (info && info.state === "today") return h("span", { class: "ag-pill ag-pill--warn", text: tr("agencies.deadline.today") });
      if (tab === "reopened") return h("span", { class: "ag-pill ag-pill--warn", text: tr("agencies.returned_pill") });
      return null;
    }
    function itemTitle(item) {
      var target = item.target || {};
      var place = target[lang() === "kk" ? "label_kk" : "label_ru"] || target.label_ru || "";
      return [catName(item.category), place].filter(Boolean).join(" · ");
    }
    function detailBox(r) {
      var name = serviceName(r.service);
      var st = S.openItems[r.service] || { loading: true };
      var box = h("div", { class: "ag-detail", role: "region", "aria-label": tr("agencies.detail.title", { name: name }) });
      var openInbox = h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: function () { openInboxFor(r.service, st.items); } },
        [tr("agencies.detail.inbox")]);
      box.appendChild(h("div", { class: "ag-detail__head" }, [h("p", { class: "ag-detail__title", text: tr("agencies.detail.title", { name: name }) }), openInbox]));
      if (st.loading) {
        box.appendChild(h("p", { class: "bk-meta", role: "status", text: tr("common.state.loading") }));
        return box;
      }
      if (st.error) {
        box.appendChild(h("p", { class: "ag-note", role: "alert", text: tr("common.state.error_title") }));
        return box;
      }
      if (!st.items.length) {
        box.appendChild(h("p", { class: "ag-note", text: tr("agencies.detail.empty") }));
        return box;
      }
      var list = h("ul", { class: "ag-items" });
      st.items.slice(0, 8).forEach(function (item) {
        list.appendChild(h("li", { class: "ag-item" }, [
          statusIcon(item.part && item.part.status === "done" ? "done" : item.status, 14),
          h("span", { class: "ag-item__code", text: item.code || "" }),
          h("span", { class: "ag-item__title", text: itemTitle(item) }),
          item.joint ? h("span", { class: "ag-pill", text: tr("agencies.tab.joint") }) : null,
          deadlinePill(item.deadline, item.tab),
          h("span", { class: "ag-item__meta", text: fmtDate(item.created_at) }),
          item.demo ? demoTag() : null,
        ]));
      });
      box.appendChild(list);
      if (st.items.length > 8) box.appendChild(h("p", { class: "ag-note", text: tr("agencies.detail.more", { n: st.items.length - 8 }) }));
      return box;
    }
    // «Обращения» R09 с фильтром по службе: событие для экрана R09 + раздел inbox (подключение — INTEGRATION R17 §4).
    function openInboxFor(service, items) {
      var detail = { service: service, ids: (items || []).map(function (x) { return x.id; }) };
      try { root.sessionStorage.setItem("birge.inbox.filter", JSON.stringify(detail)); } catch (e) { /* без хранилища */ }
      if (typeof opts.openSection === "function") opts.openSection("inbox");
      else if (root.BirgeShell) root.BirgeShell.setSection("inbox");
      setTimeout(function () { doc.dispatchEvent(new CustomEvent("birge:inbox-filter", { detail: detail })); }, 0);
    }

    // Пусто из-за узкого фильтра — одна кнопка «шире» (П1: иконка + текст + одна кнопка).
    function widenAction() {
      if (S.days === 90 && !S.district) return null;
      return { label: tr("agencies.widen"), onClick: function () { S.days = 90; S.district = ""; remember(); refresh(); } };
    }

    // ---------------------------------------------------------------- совместные
    function partChip(p) {
      var prof = profileMap()[p.service] || {};
      var status = p.status === "done" ? "done" : p.status === "in_progress" ? "in_progress" : p.status === "rejected" ? "rejected" : "new";
      return h("span", { class: "ag-part", style: { "--ag-color": prof.color || "var(--c-demo)" },
        title: (p.role === "lead" ? tr("agencies.lead") + " · " : "") + tr("agencies.part." + (p.status === "done" ? "done" : p.status)) }, [
        statusIcon(status, 14), h("span", { text: serviceName(p.service) }),
        h("span", { class: "bk-sr-only", text: " — " + tr("agencies.part." + (p.status === "done" ? "done" : p.status)) })]);
    }
    function renderJoint() {
      var data = S.joint;
      if (S.error.joint) return errorState(bodyBox, S.error.joint, refresh);
      if (!data) return bodyBox.replaceChildren(S.slow.joint ? boardSkeleton() : h("div", { "aria-busy": "true" }));
      var items = data.items || [];
      var head = h("p", { class: "ag-note", text: tr("agencies.joint.hint") });
      if (!items.length) {
        var box = h("div", { class: "ag-empty" });
        emptyState(box, tr("agencies.joint.empty"), tr("agencies.joint.empty_text"), widenAction(), "users");
        return bodyBox.replaceChildren(head, box, noteLine(data));
      }
      var list = h("ul", { class: "ag-list", "aria-label": tr("agencies.joint.title") }, items.map(function (item) {
        var sub = [h("span", { text: item.code || "" }), h("span", { text: districtName(item.district) }), h("span", { text: fmtDate(item.created_at) })];
        if (item.handoffs) sub.push(h("span", { text: tr("agencies.joint.handoffs", { n: item.handoffs }) }));
        if (item.loop) sub.push(h("span", { class: "ag-pill ag-pill--loop", title: tr("agencies.loop_hint"), text: tr("agencies.loop") }));
        if (item.demo) sub.push(demoTag());
        return h("li", { class: "ag-lrow" }, [
          statusIcon(item.open ? (item.status === "new" ? "new" : "in_progress") : "fixed", 16),
          h("div", { class: "ag-lrow__main" }, [h("span", { class: "ag-lrow__title", text: itemTitle(item) }), h("div", { class: "ag-lrow__sub" }, sub)]),
          h("div", { class: "ag-lrow__end" }, item.parts.map(partChip).concat([deadlinePill(item.deadline, item.tab)])),
        ]);
      }));
      bodyBox.replaceChildren(head, list, noteLine(data));
    }

    // ---------------------------------------------------------------- передачи
    function roleName(role) {
      var key = "agencies.role." + role;
      var text = tr(key);
      return text === key ? tr("agencies.role.staff") : text;
    }
    function renderHandoffs() {
      var data = S.handoffs;
      if (S.error.handoffs) return errorState(bodyBox, S.error.handoffs, refresh);
      if (!data) return bodyBox.replaceChildren(S.slow.handoffs ? boardSkeleton() : h("div", { "aria-busy": "true" }));
      var items = data.items || [];
      var hint = h("p", { class: "ag-note" }, [h("span", { text: tr("agencies.handoffs.hint") }),
        data.loops ? h("span", { class: "ag-pill ag-pill--loop", title: tr("agencies.loop_hint"), text: tr("agencies.handoffs.loops", { n: data.loops }) }) : null]);
      if (!items.length) {
        var box = h("div", { class: "ag-empty" });
        emptyState(box, tr("agencies.handoffs.empty"), tr("agencies.handoffs.empty_text"), widenAction(), "forward");
        return bodyBox.replaceChildren(hint, box, noteLine(data));
      }
      var pairs = h("div", { class: "ag-pairs", "aria-label": tr("agencies.handoffs.pairs") }, (data.pairs || []).slice(0, 5).map(function (p) {
        return h("span", { class: "ag-part" }, [h("span", { text: serviceName(p.from) }), h("span", { class: "ag-arrow", "aria-hidden": "true", text: "→" }),
          h("span", { class: "bk-sr-only", text: " → " }), h("span", { text: serviceName(p.to) }), h("span", { class: "ag-svcchip__count", text: "· " + num(p.count) })]);
      }));
      var list = h("ul", { class: "ag-list", "aria-label": tr("agencies.handoffs.title") }, items.map(function (e) {
        var sub = [h("span", { text: fmtWhen(e.at) }), h("span", { text: e.code || "" }), h("span", { text: roleName(e.by_role) })];
        if (e.due_at) sub.push(h("span", { text: tr("agencies.handoffs.due", { date: fmtDate(e.due_at) }) }));
        if (e.loop) sub.push(h("span", { class: "ag-pill ag-pill--loop", title: tr("agencies.loop_hint"), text: tr("agencies.loop") }));
        if (e.demo) sub.push(demoTag());
        return h("li", { class: "ag-lrow" }, [
          svg("i-forward", "ic"),
          h("div", { class: "ag-lrow__main" }, [
            h("span", { class: "ag-lrow__title" }, [serviceName(e.from) + " → " + serviceName(e.to)]),
            e.reason ? h("span", { class: "ag-quote", text: "«" + e.reason + "»" }) : null,
            h("div", { class: "ag-lrow__sub" }, sub)]),
          h("div", { class: "ag-lrow__end" }, [deadlinePill(e.deadline, null), h("span", { class: "ag-pill", text: catName(e.category) })]),
        ]);
      }));
      bodyBox.replaceChildren(hint, h("p", { class: "ag-section-title", text: tr("agencies.handoffs.pairs") }), pairs,
        h("p", { class: "ag-section-title", text: tr("agencies.handoffs.title") }), list, noteLine(data));
    }

    // ---------------------------------------------------------------- кризисный штаб
    function templates() { return (S.meta && S.meta.templates) || []; }
    function templateOf(kind) { return templates().filter(function (t) { return t.kind === kind; })[0] || null; }
    function zoneText(inc) {
      var label = inc.zone_label || {};
      return label[lang()] || label.ru || districtName(inc.zone && inc.zone.district);
    }
    function renderCrisis() {
      if (S.error.incidents) return errorState(bodyBox, S.error.incidents, refresh);
      if (S.crisis.form) return renderCrisisForm();
      var data = S.incidents;
      if (!data) return bodyBox.replaceChildren(S.slow.incidents ? boardSkeleton() : h("div", { "aria-busy": "true" }));
      var items = data.items || [];
      var active = items.filter(function (x) { return x.status === "active"; });
      var closed = items.filter(function (x) { return x.status === "closed"; });
      var parts = [];
      var newBtn = h("button", { type: "button", class: "bk-btn" + (active.length ? "" : " bk-btn--primary"), "data-action": "new-crisis",
        onclick: function () { openForm(null, null); } }, [svg("i-plus"), tr("crisis.new")]);
      if (!active.length) {
        var box = h("div", { class: "ag-empty" });
        emptyState(box, tr("crisis.none"), tr("crisis.none_text"), { label: tr("crisis.new"), onClick: function () { openForm(null, null); } }, "check");
        parts.push(box);
      } else {
        if (active.length > 1) {
          parts.push(h("div", { class: "ag-chips", role: "group" }, active.map(function (inc) {
            return h("button", { type: "button", class: "bk-chip", "aria-pressed": String(S.crisis.id === inc.id),
              onclick: function () { S.crisis.id = inc.id; loadIncident(inc.id); render(); } }, [pick(inc, "title")]);
          })));
        }
        var current = S.detail[S.crisis.id] || active.filter(function (x) { return x.id === S.crisis.id; })[0] || active[0];
        parts.push(crisisView(current));
        parts.push(h("div", { class: "ag-actions" }, [newBtn]));
      }
      if (closed.length) {
        parts.push(h("p", { class: "ag-section-title", text: tr("crisis.history") }));
        parts.push(h("ul", { class: "ag-history" }, closed.slice(0, 6).map(function (inc) {
          return h("li", null, [svg("i-" + (KIND_ICONS[inc.kind] || "alert")), h("strong", { text: pick(inc, "title") }),
            h("span", { class: "ag-note", text: zoneText(inc) + " · " + fmtDate(inc.started_at) + " — " + fmtDate(inc.closed_at) }),
            inc.result ? h("span", { class: "ag-quote", text: pick(inc.result, "text") }) : null, inc.demo ? demoTag() : null]);
        })));
      }
      bodyBox.replaceChildren.apply(bodyBox, parts);
    }
    function crisisView(inc) {
      var full = S.detail[inc.id] || inc;
      var tasks = full.tasks || [];
      var progress = full.progress || [];
      var left = h("section", { class: "ag-card", "aria-label": pick(full, "title") });
      left.appendChild(h("div", { class: "ag-card__head" }, [
        h("span", { class: "ag-card__badge", "data-live": full.status === "active" ? "" : null }, [svg("i-" + (KIND_ICONS[full.kind] || "alert"))]),
        h("div", null, [
          h("h3", { class: "ag-card__title", text: pick(full, "title") }),
          h("div", { class: "ag-card__sub" }, [
            h("span", { text: tr("crisis.zone", { zone: zoneText(full) }) }),
            h("span", { text: tr("crisis.started", { time: fmtWhen(full.started_at) }) }),
            full.status === "active" ? h("span", { text: tr("crisis.duration", { d: duration(full.started_at) }) }) : null,
            full.demo ? demoTag() : null])]),
      ]));
      if (progress.length) {
        left.appendChild(h("div", { class: "ag-chips", "aria-label": tr("crisis.services") }, progress.map(function (p) {
          var share = p.total ? Math.round((p.done / p.total) * 100) : 0;
          var ring = h("span", { class: "ag-ring", "aria-hidden": "true", style: { "--p": String(share) } });
          return h("span", { class: "ag-svcchip", title: tr("crisis.task.done") + ": " + p.done + " / " + p.total }, [ring,
            h("span", { text: serviceName(p.service) }), h("span", { class: "ag-svcchip__count", text: num(p.done) + "/" + num(p.total) })]);
        })));
      }
      if (tasks.length) {
        left.appendChild(h("p", { class: "ag-section-title", text: tr("crisis.services") }));
        left.appendChild(h("ul", { class: "ag-tasks" }, tasks.map(function (task) { return taskRow(full, task); })));
      }
      if (full.status === "active" && S.meta) left.appendChild(addTaskForm(full));
      var actions = h("div", { class: "ag-actions" }, [
        h("button", { type: "button", class: "bk-btn", "data-action": "show-map", onclick: function () { showOnMap(full); } }, [svg("i-pin"), tr("crisis.show_map")]),
        full.status === "active" ? h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-action": "close-crisis",
          onclick: function () { S.crisis.closing = !S.crisis.closing; render(); } }, [tr("crisis.close")]) : null,
      ]);
      left.appendChild(actions);
      if (S.crisis.closing && full.status === "active") left.appendChild(closeForm(full));
      if (full.result) left.appendChild(h("p", { class: "ag-upd__text" }, [h("strong", { text: tr("crisis.result") + ": " }), pick(full.result, "text")]));
      var right = h("section", { class: "ag-card", "aria-label": tr("crisis.updates") });
      right.appendChild(h("h3", { class: "ag-card__title", text: tr("crisis.updates") }));
      if (full.status === "active") right.appendChild(composer(full));
      var updates = full.updates || [];
      if (!updates.length) right.appendChild(h("p", { class: "ag-note", text: tr("crisis.update.empty") }));
      else right.appendChild(h("ul", { class: "ag-feed" }, updates.map(updateItem)));
      return h("div", { class: "ag-crisis", "data-incident": full.id }, [left, right]);
    }
    var NEXT = { todo: "doing", doing: "done", done: "todo" };
    function taskRow(inc, task) {
      var canEdit = inc.status === "active" && S.detail[inc.id];
      var next = NEXT[task.status] || "doing";
      var btn = h("button", { type: "button", class: "ag-task__st", disabled: canEdit ? null : true,
        "aria-label": tr("crisis.task.next", { status: tr("crisis.task." + next) }) + " — " + pick(task, "text"),
        title: tr("crisis.task." + task.status) }, [statusIcon(task.status, 18)]);
      btn.addEventListener("click", function () {
        btn.disabled = true;
        var before = task.status;
        task.status = next;                 // оптимистично (правило 4 Linear), при ошибке вернём
        render();
        request("POST", "/incidents/" + encodeURIComponent(inc.id) + "/task", { task_id: task.id, status: next, expected: before })
          .then(function (d) { S.detail[inc.id] = d.incident; render(); }, function (err) {
            task.status = before;
            if (err && err.status === 409) { toast(tr("crisis.stale")); loadIncident(inc.id); }
            else toast(tr("crisis.error.save"), "error");
            render();
          });
      });
      return h("li", { class: "ag-task", "data-status": task.status, "data-task": task.id }, [btn,
        h("span", { class: "ag-task__text", text: pick(task, "text") }),
        h("span", { class: "ag-task__svc", text: serviceName(task.service) })]);
    }
    function addTaskForm(inc) {
      var details = h("details", { class: "bk-details" });
      var select = h("select", { "aria-label": tr("agencies.col.service") }, ((S.meta && S.meta.services) || []).map(function (p) {
        return h("option", { value: p.id, text: serviceName(p.id) });
      }));
      var input = h("input", { type: "text", maxlength: "200", "aria-label": tr("crisis.task.text"), placeholder: tr("crisis.task.text") });
      var add = h("button", { type: "button", class: "ag-iconbtn", "aria-label": tr("crisis.task.add"), title: tr("crisis.task.add") }, [svg("i-plus")]);
      add.addEventListener("click", function () {
        var text = input.value.trim();
        if (text.length < 3) { input.focus(); return; }
        add.disabled = true;
        var body = { service: select.value };
        body["text_" + lang()] = text;
        request("POST", "/incidents/" + encodeURIComponent(inc.id) + "/task", body).then(function (d) {
          S.detail[inc.id] = d.incident;
          render();
        }, function (err) {
          add.disabled = false;
          toast((err && err.message) || tr("crisis.error.save"), "error");
        });
      });
      details.append(h("summary", { text: tr("crisis.task.add") }), h("div", { class: "ag-taskedit" }, [select, input, add]));
      return details;
    }
    function updateItem(u) {
      var l = lang(), other = l === "kk" ? "ru" : "kk";
      var mine = u["text_" + l] || u["text_" + other] || "";
      var second = u["text_" + other] && u["text_" + l] ? u["text_" + other] : "";
      return h("li", { class: "ag-upd", "data-public": String(u.public !== false) }, [
        h("div", { class: "ag-upd__meta" }, [
          h("span", { text: fmtWhen(u.at) }),
          h("span", { class: "ag-pill" + (u.public === false ? "" : " ag-pill--ok"), text: u.public === false ? tr("crisis.update.internal") : tr("crisis.update.public") }),
          u.kind === "closed" ? h("span", { class: "ag-pill", text: tr("crisis.result") }) : null]),
        h("p", { class: "ag-upd__text", lang: u["text_" + l] ? l : other, text: mine }),
        second ? h("p", { class: "ag-upd__other", lang: other, text: second }) : null,
      ]);
    }
    function field(label, control, error) {
      return h("label", { class: "bk-field" + (error ? " bk-field--error" : "") }, [h("span", { class: "bk-field__label", text: label }), control,
        error ? h("span", { class: "bk-field__error", text: error }) : null]);
    }
    function composer(inc) {
      var c = S.crisis.composer;
      var ru = h("textarea", { maxlength: "600", rows: "2", lang: "ru", "data-lang": "ru" });
      var kk = h("textarea", { maxlength: "600", rows: "2", lang: "kk", "data-lang": "kk" });
      ru.value = c.ru;
      kk.value = c.kk;
      ru.addEventListener("input", function () { c.ru = ru.value; c.error = null; });
      kk.addEventListener("input", function () { c.kk = kk.value; c.error = null; });
      var pub = h("input", { type: "checkbox" });
      pub.checked = c.public !== false;
      var send = h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-action": "send-update" },
        [svg("i-send"), c.public !== false ? tr("crisis.update.send") : tr("crisis.update.save_note")]);
      pub.addEventListener("change", function () { c.public = pub.checked; render(); });
      var tpl = templateOf(inc.kind);
      var fillBtn = tpl && tpl.update_ru ? h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: function () {
        c.ru = tpl.update_ru;
        c.kk = tpl.update_kk;
        render();
      } }, [tr("crisis.update.template")]) : null;
      send.addEventListener("click", function () {
        var body = { text_ru: c.ru.trim(), text_kk: c.kk.trim(), public: c.public !== false };
        send.disabled = true;
        request("POST", "/incidents/" + encodeURIComponent(inc.id) + "/update", body).then(function (d) {
          S.detail[inc.id] = d.incident;
          S.crisis.composer = { ru: "", kk: "", public: true };
          toast(body.public ? tr("crisis.update.sent") : tr("crisis.update.noted"), "ok");
          render();
        }, function (err) {
          send.disabled = false;
          c.error = err || {};
          render();
        });
      });
      var err = c.error;
      var errFor = function (f) { return err && err.field === f ? err.message : null; };
      var general = err && !err.field ? h("p", { class: "ag-field-error", role: "alert", text: err.message || tr("crisis.error.save") }) : null;
      return h("div", { class: "ag-form", "data-form": "update" }, [
        h("div", { class: "ag-form__row" }, [field(tr("crisis.update.ru"), ru, errFor("text_ru")), field(tr("crisis.update.kk"), kk, errFor("text_kk"))]),
        h("div", { class: "ag-actions" }, [h("label", { class: "ag-switch" }, [pub, tr("crisis.update.public")]), fillBtn, send]),
        general,
      ]);
    }
    function closeForm(inc) {
      var c = S.crisis;
      c.result = c.result || { ru: "", kk: "" };
      var ru = h("textarea", { maxlength: "600", rows: "2", lang: "ru" });
      var kk = h("textarea", { maxlength: "600", rows: "2", lang: "kk" });
      ru.value = c.result.ru;
      kk.value = c.result.kk;
      ru.addEventListener("input", function () { c.result.ru = ru.value; });
      kk.addEventListener("input", function () { c.result.kk = kk.value; });
      var ok = h("button", { type: "button", class: "bk-btn bk-btn--dark", "data-action": "confirm-close" }, [tr("crisis.close.confirm")]);
      ok.addEventListener("click", function () {
        ok.disabled = true;
        request("POST", "/incidents/" + encodeURIComponent(inc.id) + "/close", { result_ru: c.result.ru.trim(), result_kk: c.result.kk.trim() })
          .then(function (d) {
            S.detail[inc.id] = d.incident;
            c.closing = false;
            c.result = null;
            toast(tr("crisis.closed_ok"), "ok");
            // Закрытый уходит в «Прошедшие»; на месте карточки — следующий идущий кризис или «Сейчас кризисов нет».
            S.crisis.id = null;
            loadIncidents();
            if (root.BirgeCrisisLayer && root.BirgeCrisisLayer.refresh) root.BirgeCrisisLayer.refresh();
          }, function (err) {
            ok.disabled = false;
            c.resultError = err || {};
            render();
          });
      });
      var err = c.resultError;
      return h("div", { class: "ag-form", "data-form": "close" }, [
        h("p", { class: "ag-section-title", text: tr("crisis.close.title") }),
        h("div", { class: "ag-form__row" }, [
          field(tr("crisis.close.ru"), ru, err && err.field === "result_ru" ? err.message : null),
          field(tr("crisis.close.kk"), kk, err && err.field === "result_kk" ? err.message : null)]),
        err && !err.field ? h("p", { class: "ag-field-error", role: "alert", text: err.message || tr("crisis.error.save") }) : null,
        h("div", { class: "ag-actions" }, [ok, h("button", { type: "button", class: "bk-btn bk-btn--ghost",
          onclick: function () { c.closing = false; c.resultError = null; render(); } }, [tr("common.action.cancel")])]),
      ]);
    }

    // Новый кризис: шаблон → зона → названия → задачи → первое обновление жителям.
    function openForm(template, district) {
      loadMeta().then(function () {
        var tpl = templateOf(template || "blizzard") || templates()[0] || { kind: "blizzard", tasks: [] };
        S.crisis.form = {
          kind: tpl.kind, zoneKind: "district", district: district || S.district || "nura", yards: [], yardQuery: "",
          title_ru: tpl.title_ru || "", title_kk: tpl.title_kk || "",
          tasks: (tpl.tasks || []).map(function (t) { return { service: t.service, text_ru: t.text_ru, text_kk: t.text_kk }; }),
          update_ru: tpl.update_ru || "", update_kk: tpl.update_kk || "", error: null, saving: false,
        };
        if (S.tab !== "crisis") { S.tab = "crisis"; remember(); }
        render();
        var first = bodyBox.querySelector("[data-form=create] button, [data-form=create] select");
        if (first) first.focus();
      });
    }
    function applyTemplate(kind) {
      var f = S.crisis.form, tpl = templateOf(kind);
      if (!tpl) return;
      f.kind = kind;
      f.title_ru = tpl.title_ru;
      f.title_kk = tpl.title_kk;
      f.tasks = (tpl.tasks || []).map(function (t) { return { service: t.service, text_ru: t.text_ru, text_kk: t.text_kk }; });
      f.update_ru = tpl.update_ru || "";
      f.update_kk = tpl.update_kk || "";
      render();
    }
    function renderCrisisForm() {
      var f = S.crisis.form;
      var err = f.error;
      var errFor = function (name) { return err && err.field && err.field.indexOf(name) === 0 ? err.message : null; };
      var kinds = h("div", { class: "ag-templates", role: "radiogroup", "aria-label": tr("crisis.new.kind") }, templates().map(function (t) {
        return h("button", { type: "button", class: "bk-chip", role: "radio", "aria-checked": String(f.kind === t.kind), "data-kind": t.kind,
          onclick: function () { applyTemplate(t.kind); } }, [svg("i-" + (KIND_ICONS[t.kind] || "alert")), tr("crisis.kind." + t.kind)]);
      }));
      var zoneSeg = h("div", { class: "ag-seg", role: "group", "aria-label": tr("crisis.new.zone") }, ["district", "yards"].map(function (z) {
        return h("button", { type: "button", "aria-pressed": String(f.zoneKind === z), onclick: function () { f.zoneKind = z; render(); },
          text: tr("crisis.new.zone." + z) });
      }));
      var district = h("select", { class: "ag-select", "aria-label": tr("crisis.new.zone.district") }, DISTRICTS.map(function (d) {
        return h("option", { value: d, text: districtName(d) });
      }));
      district.value = f.district;
      district.addEventListener("change", function () { f.district = district.value; f.yards = []; render(); });
      var zoneParts = [h("div", { class: "ag-actions" }, [zoneSeg, district])];
      if (f.zoneKind === "yards") {
        var search = h("input", { type: "search", class: "ag-select", style: { "max-width": "100%" }, placeholder: tr("crisis.new.yards_search"),
          "aria-label": tr("crisis.new.yards_search") });
        search.value = f.yardQuery;
        var listBox = h("ul", { class: "ag-yards" });
        var drawYards = function () {
          var q = f.yardQuery.trim().toLowerCase();
          var yards = ((S.meta && S.meta.yards) || []).filter(function (y) {
            return y.district === f.district && (!q || (y.label_ru + " " + y.label_kk).toLowerCase().indexOf(q) >= 0);
          }).slice(0, 60);
          listBox.replaceChildren.apply(listBox, yards.map(function (y) {
            var box = h("input", { type: "checkbox", value: y.id });
            box.checked = f.yards.indexOf(y.id) >= 0;
            box.addEventListener("change", function () {
              if (box.checked) f.yards.push(y.id);
              else f.yards = f.yards.filter(function (x) { return x !== y.id; });
              counter.textContent = tr("crisis.new.yards_picked", { n: f.yards.length });
            });
            return h("li", null, [h("label", null, [box, pick(y, "label")])]);
          }));
        };
        var counter = h("span", { class: "ag-note", text: tr("crisis.new.yards_picked", { n: f.yards.length }) });
        search.addEventListener("input", function () { f.yardQuery = search.value; drawYards(); });
        drawYards();
        zoneParts.push(search, listBox, counter);
      }
      var titleRu = h("input", { type: "text", maxlength: "80", value: f.title_ru, lang: "ru" });
      var titleKk = h("input", { type: "text", maxlength: "80", value: f.title_kk, lang: "kk" });
      titleRu.addEventListener("input", function () { f.title_ru = titleRu.value; });
      titleKk.addEventListener("input", function () { f.title_kk = titleKk.value; });
      var taskRows = f.tasks.map(function (t, i) {
        var sel = h("select", { "aria-label": tr("agencies.col.service") }, ((S.meta && S.meta.services) || []).map(function (p) {
          return h("option", { value: p.id, text: serviceName(p.id) });
        }));
        sel.value = t.service;
        sel.addEventListener("change", function () { t.service = sel.value; });
        var text = h("input", { type: "text", maxlength: "200", value: pick(t, "text"), "aria-label": tr("crisis.task.text") });
        text.addEventListener("input", function () { t["text_" + lang()] = text.value; });
        var del = h("button", { type: "button", class: "ag-iconbtn", "aria-label": tr("crisis.remove") + ": " + pick(t, "text"),
          title: tr("crisis.remove"), onclick: function () { f.tasks.splice(i, 1); render(); } }, [svg("i-close")]);
        return h("div", { class: "ag-taskedit" }, [sel, text, del]);
      });
      var addTask = h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: function () {
        f.tasks.push({ service: "akimat", text_ru: "", text_kk: "" });
        render();
      } }, [svg("i-plus"), tr("crisis.task.add")]);
      var upRu = h("textarea", { maxlength: "600", rows: "2", lang: "ru" });
      var upKk = h("textarea", { maxlength: "600", rows: "2", lang: "kk" });
      upRu.value = f.update_ru;
      upKk.value = f.update_kk;
      upRu.addEventListener("input", function () { f.update_ru = upRu.value; });
      upKk.addEventListener("input", function () { f.update_kk = upKk.value; });
      var create = h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-action": "create-crisis", disabled: f.saving ? true : null },
        [tr("crisis.new.create")]);
      create.addEventListener("click", submitCrisis);
      var cancel = h("button", { type: "button", class: "bk-btn bk-btn--ghost", onclick: function () { S.crisis.form = null; render(); } },
        [tr("common.action.cancel")]);
      var form = h("section", { class: "ag-card ag-form", "data-form": "create", "aria-label": tr("crisis.new.title") }, [
        h("h3", { class: "ag-card__title", text: tr("crisis.new.title") }),
        h("p", { class: "ag-section-title", text: tr("crisis.new.kind") }), kinds,
        h("p", { class: "ag-section-title", text: tr("crisis.new.zone") })].concat(zoneParts).concat([
        errFor("zone") ? h("p", { class: "ag-field-error", role: "alert", text: errFor("zone") }) : null,
        h("div", { class: "ag-form__row" }, [field(tr("crisis.new.name_ru"), titleRu, errFor("title_ru")),
          field(tr("crisis.new.name_kk"), titleKk, errFor("title_kk"))]),
        h("p", { class: "ag-section-title", text: tr("crisis.new.tasks") })]).concat(taskRows).concat([
        errFor("tasks") ? h("p", { class: "ag-field-error", role: "alert", text: errFor("tasks") }) : null,
        h("div", { class: "ag-actions" }, [addTask]),
        h("p", { class: "ag-section-title", text: tr("crisis.new.first_update") }),
        h("div", { class: "ag-form__row" }, [field(tr("crisis.update.ru"), upRu, errFor("text_ru")), field(tr("crisis.update.kk"), upKk, errFor("text_kk"))]),
        err && !err.field ? h("p", { class: "ag-field-error", role: "alert", text: err.message || tr("crisis.error.save") }) : null,
        h("div", { class: "ag-actions" }, [create, cancel]),
      ]));
      bodyBox.replaceChildren(form);
    }
    function submitCrisis() {
      var f = S.crisis.form;
      if (f.zoneKind === "yards" && !f.yards.length) { f.error = { field: "zone", message: tr("crisis.new.no_zone") }; render(); return; }
      var body = {
        kind: f.kind, title_ru: f.title_ru.trim(), title_kk: f.title_kk.trim(),
        zone: f.zoneKind === "district" ? { kind: "district", district: f.district } : { kind: "targets", targets: f.yards.slice(), district: f.district },
        tasks: f.tasks.filter(function (t) { return (t.text_ru || t.text_kk || "").trim(); }).map(function (t) {
          return { service: t.service, text_ru: (t.text_ru || "").trim() || null, text_kk: (t.text_kk || "").trim() || null };
        }),
      };
      if (f.update_ru.trim() || f.update_kk.trim()) body.update = { text_ru: f.update_ru.trim(), text_kk: f.update_kk.trim() };
      f.saving = true;
      f.error = null;
      render();
      request("POST", "/incidents", body).then(function (d) {
        S.crisis.form = null;
        S.detail[d.incident.id] = d.incident;
        toast(tr("crisis.new.created"), "ok");
        loadIncidents(d.incident.id);
        if (root.BirgeCrisisLayer && root.BirgeCrisisLayer.refresh) root.BirgeCrisisLayer.refresh();
      }, function (err) {
        f.saving = false;
        if (err && err.status === 409 && err.current) {
          S.crisis.form = null;
          toast(tr("crisis.duplicate"));
          loadIncidents(err.current);
          return;
        }
        f.error = err || {};
        render();
      });
    }
    function showOnMap(inc) {
      var layer = root.BirgeCrisisLayer;
      if (layer && layer.focus) layer.focus(inc.id);
      else if (typeof opts.openSection === "function") opts.openSection("map");
    }

    // ---------------------------------------------------------------- отрисовка
    function render() {
      if (!S.alive) return;
      renderHead();
      rootEl.setAttribute("data-tab", S.tab);
      if (S.tab === "board") renderBoard();
      else if (S.tab === "joint") renderJoint();
      else if (S.tab === "handoffs") renderHandoffs();
      else renderCrisis();
    }
    function relang() {
      if (S.lang === lang()) return;
      S.lang = lang();
      render();
    }
    var off = null;
    if (I() && typeof I().onChange === "function") off = I().onChange(relang);

    var handle = {
      setLang: relang,
      destroy: function () {
        S.alive = false;
        if (typeof off === "function") off();
        if (mounted === handle) mounted = null;
        rootEl.classList.remove("ag");
        rootEl.removeAttribute("data-agencies");
      },
      openCrisis: function (target) {
        S.tab = "crisis";
        remember();
        if (target && target.incident) { S.crisis.id = target.incident; S.crisis.form = null; loadMeta().then(function () { loadIncidents(target.incident); }); }
        else openForm(target && target.template, target && target.district);
        render();
      },
      state: S,
    };
    mounted = handle;
    if (pending) {
      var p = pending;
      pending = null;
      handle.openCrisis(p);
    } else {
      refresh();
    }
    if (S.tab === "crisis" && !S.incidents) loadMeta().then(function () { loadIncidents(); });
    return handle;
  }

  // ------------------------------------------------------------------ вход из других разделов
  function openCrisis(target) {
    if (mounted) {
      mounted.openCrisis(target || {});
      return;
    }
    pending = target || {};
    if (root.BirgeShell && typeof root.BirgeShell.setSection === "function") root.BirgeShell.setSection("agencies");
  }
  // #agencies/crisis=<id> · #agencies/crisis=new&template=…&district=… (кнопки R08, R13; ссылка из crisis_link()).
  function fromHash() {
    var m = /^#agencies\/crisis=([^&]+)(.*)$/.exec(root.location.hash || "");
    if (!m) return false;
    var params = {};
    (m[2] || "").replace(/[&?]([a-z_]+)=([^&]*)/g, function (w, k, v) { params[k] = decodeURIComponent(v); });
    var target = m[1] === "new" ? { template: params.template, district: params.district } : { incident: decodeURIComponent(m[1]) };
    // Оболочка сама сбросит неизвестный адрес на карту — открываем раздел после неё.
    setTimeout(function () { openCrisis(target); }, 0);
    return true;
  }

  root.BirgeAgencies = { mount: mount, openCrisis: openCrisis, version: "r15-1" };

  function register() {
    var shell = root.BirgeShell;
    if (!shell || typeof shell.registerScreen !== "function") return false;
    var spec = { id: "agencies", mount: mount, modes: ["akimat"], title: { ru: KEYS.ru["agencies.title"], kk: KEYS.kk["agencies.title"] } };
    if (I() && I().has && I().has("shell.nav.agencies")) spec.titleKey = "shell.nav.agencies";
    return shell.registerScreen(spec);
  }
  function start() {
    register();
    fromHash();
    root.addEventListener("hashchange", fromHash);
  }
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", start);
  else start();
})(typeof self !== "undefined" ? self : this);
