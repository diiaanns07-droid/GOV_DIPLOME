/*
 * Birge · «Штаб ведомств» (R17, раунд 15): табло служб, совместные обращения, журнал передач, кризисный штаб.
 *
 *   <link rel="stylesheet" href="/civic/agencies/agencies.css">
 *   <script defer src="/civic/agencies/agencies.js"></script>        (после birge.js и ui-kit.js)
 *   BirgeAgencies.mount(root, { apiBase: "/api/civic/v2", api, lang, openSection, openTarget, close }) → { setLang, destroy }
 *   BirgeAgencies.openCrisis({ incident } | { template, district }) — кнопка «Открыть кризисный штаб» (R08, R13)
 *
 * В оболочке R01 экран встаёт сам: BirgeShell.registerScreen({id: "agencies", mount, modes: ["akimat"], …});
 * место в меню решает R11 (IA_ROUND15 §5.4: «Ведомства»). Путь раздела (оболочка R01 раунда 15, handle.setPath):
 * #agencies/<board|joint|handoffs|calendar|crisis>, #agencies/crisis/<id>, #agencies/crisis/new/<шаблон>/<район>;
 * раздел «crisis» (#crisis/<id>) — публичная карточка кризиса (тот же модуль, opts.section = "crisis").
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

  // Значки служб раунда 15 — в спрайте ui-kit R11 (radiator, zap, flame, paw, traffic, siren, broom, wrench). Сборка со
  // старым спрайтом (FINAL-4) их не знает — тогда берём icon_fallback профиля. Спрайт читаем один раз (он уже в кэше).
  var sprite = { state: "none", ids: null, waiters: [] };
  function loadSprite(onReady) {
    if (sprite.state === "ready") return;
    if (typeof onReady === "function") sprite.waiters.push(onReady);
    if (sprite.state === "loading" || typeof root.fetch !== "function") return;
    sprite.state = "loading";
    root.fetch(SPRITE, { credentials: "same-origin" }).then(function (r) { return r.ok ? r.text() : ""; }).then(function (text) {
      var ids = {};
      (String(text).match(/id="i-[A-Za-z0-9_-]+"/g) || []).forEach(function (m) { ids[m.slice(6, -1)] = true; });
      sprite.ids = Object.keys(ids).length ? ids : null;
      sprite.state = "ready";
      sprite.waiters.splice(0).forEach(function (fn) { try { fn(); } catch (e) { /* экран уже закрыт */ } });
    }, function () { sprite.state = "ready"; sprite.ids = null; sprite.waiters.length = 0; });
  }
  function iconOf(p) {
    if (!p) return "dots";
    if (sprite.ids && p.icon && !sprite.ids[p.icon] && p.icon_fallback) return p.icon_fallback;
    return p.icon || p.icon_fallback || "dots";
  }

  // Запасные тексты (до словаря R11). Казахский — на вычитку R11 (INTEGRATION.txt R17 §5).
  var KEYS = {
    ru: {
      "agencies.title": "Штаб ведомств",
      "agencies.tab.board": "Табло",
      "agencies.tab.joint": "Совместные",
      "agencies.tab.handoffs": "Передачи",
      "agencies.tab.crisis": "Кризис",
      "agencies.tab.calendar": "Календарь работ",
      "agencies.calendar.add": "Добавить работу",
      "agencies.calendar.missing": "Календарь работ ещё не подключён в этой сборке",
      "agencies.services_link": "Кто за что отвечает",
      "crisis.chronicle": "Хроника недели",
      "crisis.open_hq": "Открыть в штабе",
      "crisis.public.services": "Работают службы",
      "crisis.public.updates": "Обновления служб",
      "crisis.public.show": "Показать зону на карте",
      "agencies.period": "Период",
      "agencies.period.days": "{n} дн.",
      "agencies.district.all": "Все районы",
      "agencies.refresh": "Обновить",
      "agencies.demo_note": "Пример: синтетические обращения до демо-мира",
      "agencies.source.r09": "Числа — из «Обращений»",
      "agencies.updated": "Обновлено {time}",
      "agencies.kpi.open": "открыто",
      "agencies.kpi.overdue": "ответ просрочен",
      "agencies.kpi.joint": "совместных",
      "agencies.kpi.handoffs": "передач",
      "agencies.kpi.verified": "проверено жителями",
      "agencies.kpi.overdue_answer": "ответ просрочен",
      "agencies.kpi.overdue_fix": "не исправлено в срок",
      "agencies.col.fix": "Срок испр.",
      "agencies.col.fix_hint": "Не исправлено в срок — норматив «Картины дня» (подано → исправлено)",
      "agencies.row.label_v2": "{name}: открыто {open}, ответ просрочен {overdue}, не исправлено в срок {fix}",
      "agencies.part.todo": "ждёт",
      "agencies.sort.fix": "по сроку исправления",
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
      "agencies.col.deadline_hint": "Полоса — открытые обращения службы: красное — ответ просрочен, жёлтое — срок ответа сегодня, серое — в срок, светлое — ответ уже дан. Число — сколько с просроченным ответом",
      "agencies.col.returned_hint": "Жители вернули в работу: проблема осталась",
      "agencies.col.handoffs_hint": "Передано в службу ↓ и из службы ↑ за период",
      "agencies.col.joint_hint": "Обращения, где работают две службы и больше",
      "agencies.days_short": "{n} дн.",
      "agencies.overdue_n": "{n} просроч.",
      "agencies.total": "Всего",
      "agencies.sort": "Сортировка",
      "agencies.sort.overdue": "по просроченному ответу",
      "agencies.sort.open": "по открытым",
      "agencies.sort.answer": "по времени ответа",
      "agencies.sort.verified": "по доле проверенных",
      "agencies.sort.name": "по названию",
      "agencies.deadline.overdue": "просрочено",
      "agencies.deadline.today": "срок сегодня",
      "agencies.deadline.ok": "в срок",
      "agencies.deadline.answered": "ответ дан",
      "agencies.row.label": "{name}: открыто {open}, ответ просрочен {overdue}",
      "agencies.detail.title": "Открытые обращения: {name}",
      "agencies.detail.empty": "Открытых обращений нет",
      "agencies.detail.inbox": "Открыть в «Обращениях»",
      "agencies.detail.more": "и ещё {n}",
      "agencies.detail.open_one": "Открыть обращение",
      "agencies.pickups.title": "Вывоз после дел жителей",
      "agencies.pickups.hint": "Акимат поддержал дела жителей — после них нужен вывоз: {n}",
      "agencies.pickups.when": "{date}, с {time}",
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
      "crisis.update.send": "Отправить обновление жителям",
      "crisis.update.save_note": "Сохранить заметку",
      "crisis.update.sent": "Обновление отправлено жителям зоны",
      "crisis.update.noted": "Заметка сохранена",
      "crisis.update.template": "Подставить текст шаблона",
      "crisis.update.empty": "Обновлений пока нет",
      "crisis.show_map": "Показать на карте",
      "crisis.close": "Закрыть с итогом",
      "crisis.close.title": "Итог для жителей",
      "crisis.close.ru": "Итог на русском",
      "crisis.close.kk": "Итог на казахском",
      "crisis.close.confirm": "Закрыть и сообщить итог",
      "crisis.closed_ok": "Кризис закрыт, жители зоны увидят итог",
      "crisis.result": "Итог",
      "crisis.none": "Сейчас кризисов нет",
      "crisis.none_text": "Когда случится буран, авария или прорыв, откройте штаб: зона, задачи служб, обновления жителям.",
      "crisis.new": "Открыть кризисный штаб",
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
      "agencies.tab.crisis": "Жедел штаб",
      "agencies.tab.calendar": "Жұмыстар күнтізбесі",
      "agencies.calendar.add": "Жұмыс қосу",
      "agencies.calendar.missing": "Жұмыстар күнтізбесі бұл жинақта әлі қосылмаған",
      "agencies.services_link": "Кім неге жауапты",
      "crisis.chronicle": "Апта шежіресі",
      "crisis.open_hq": "Штабта ашу",
      "crisis.public.services": "Жұмыс істеп жатқан қызметтер",
      "crisis.public.updates": "Қызметтердің жаңартулары",
      "crisis.public.show": "Аймақты картадан көрсету",
      "agencies.period": "Кезең",
      "agencies.period.days": "{n} күн",
      "agencies.district.all": "Барлық аудандар",
      "agencies.refresh": "Жаңарту",
      "agencies.demo_note": "Үлгі: демо-әлемге дейінгі синтетикалық өтініштер",
      "agencies.source.r09": "Сандар — «Өтініштерден»",
      "agencies.updated": "Жаңартылды {time}",
      "agencies.kpi.open": "ашық",
      "agencies.kpi.overdue": "жауап мерзімі өтті",
      "agencies.kpi.joint": "бірлескен",
      "agencies.kpi.handoffs": "жіберу",
      "agencies.kpi.verified": "тұрғындар тексерді",
      "agencies.kpi.overdue_answer": "жауап мерзімі өтті",
      "agencies.kpi.overdue_fix": "мерзімінде түзетілмеген",
      "agencies.col.fix": "Түзету мерзімі",
      "agencies.col.fix_hint": "Мерзімінде түзетілмеген — «Күн қорытындысы» нормативі (берілді → түзетілді)",
      "agencies.row.label_v2": "{name}: ашық {open}, жауап мерзімі өтті {overdue}, мерзімінде түзетілмеген {fix}",
      "agencies.part.todo": "күтуде",
      "agencies.sort.fix": "түзету мерзімі бойынша",
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
      "agencies.col.deadline_hint": "Жолақ — қызметтің ашық өтініштері: қызыл — жауап мерзімі өтті, сары — жауап мерзімі бүгін, сұр — мерзімінде, ақшыл — жауап берілді. Сан — жауап мерзімі өткендер саны",
      "agencies.col.returned_hint": "Тұрғындар жұмысқа қайтарды: мәселе қалды",
      "agencies.col.handoffs_hint": "Кезеңде қызметке ↓ және қызметтен ↑ жіберілгені",
      "agencies.col.joint_hint": "Екі және одан көп қызмет жұмыс істейтін өтініштер",
      "agencies.days_short": "{n} күн",
      "agencies.overdue_n": "{n} мерзімі өткен",
      "agencies.total": "Барлығы",
      "agencies.sort": "Сұрыптау",
      "agencies.sort.overdue": "жауап мерзімі өткені бойынша",
      "agencies.sort.open": "ашық өтініштер бойынша",
      "agencies.sort.answer": "жауап уақыты бойынша",
      "agencies.sort.verified": "тексерілген үлесі бойынша",
      "agencies.sort.name": "атауы бойынша",
      "agencies.deadline.overdue": "мерзімі өткен",
      "agencies.deadline.today": "мерзімі бүгін",
      "agencies.deadline.ok": "мерзімінде",
      "agencies.deadline.answered": "жауап берілді",
      "agencies.row.label": "{name}: ашық {open}, жауап мерзімі өтті {overdue}",
      "agencies.detail.title": "Ашық өтініштер: {name}",
      "agencies.detail.empty": "Ашық өтініш жоқ",
      "agencies.detail.inbox": "«Өтініштерде» ашу",
      "agencies.detail.more": "тағы {n}",
      "agencies.detail.open_one": "Өтінішті ашу",
      "agencies.pickups.title": "Тұрғындар ісінен кейін қоқыс шығару",
      "agencies.pickups.hint": "Әкімдік тұрғындардың ісін қолдады — кейін қоқыс шығару керек: {n}",
      "agencies.pickups.when": "{date}, {time} бастап",
      "agencies.joint.title": "Бірлескен өтініштер",
      "agencies.joint.hint": "Бір өтініш — бірнеше қызмет, әрқайсысының өз бөлігі бар. Тұрғынға жауап мерзімі ортақ.",
      "agencies.joint.empty": "Әзірге бірлескен өтініш жоқ",
      "agencies.joint.empty_text": "Өтінішке екі қызмет керек болса, ол осында шығады.",
      "agencies.joint.handoffs": "жіберу: {n}",
      "agencies.loop": "қайта оралған",
      "agencies.loop_hint": "Өтініш оны бұрын жіберген қызметке қайта оралды",
      "agencies.handoffs.title": "Жіберулер журналы",
      "agencies.handoffs.hint": "Жіберген кезде тұрғынға жауап мерзімі өзгермейді.",
      "agencies.handoffs.pairs": "Жиі кездесетіні",
      "agencies.handoffs.empty": "Кезеңде жіберу болған жоқ",
      "agencies.handoffs.empty_text": "Ұзағырақ кезеңді немесе басқа ауданды таңдаңыз.",
      "agencies.handoffs.due": "мерзім өзгермейді: {date} дейін",
      "agencies.handoffs.loops": "қайта оралған: {n}",
      "agencies.role.operator": "оператор",
      "agencies.role.editor": "қызметкер",
      "agencies.role.admin": "әкімші",
      "agencies.role.demo": "үлгі",
      "agencies.role.staff": "қызметкер",
      "agencies.part.done": "орындалды",
      "agencies.part.in_progress": "орындалуда",
      "agencies.part.accepted": "қабылданды",
      "agencies.part.new": "жаңа",
      "agencies.part.rejected": "қабылданбады",
      "agencies.lead": "жетекші",
      "agencies.not_ready": "Ведомстволар штабы бұл жинақта әлі қосылмаған",
      "agencies.not_ready_text": "Басқа бөлімдер жұмыс істейді. Кейінірек көріңіз.",
      "agencies.empty_board": "Әзірге өтініш жоқ",
      "agencies.empty_board_text": "Тұрғындар мәселе туралы хабарлай бастағанда табло толады.",
      "agencies.staff_only": "Ведомстволар штабы — әкімдік қызметкерлеріне арналған",
      "crisis.title": "Жедел штаб",
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
      "crisis.task.doing": "орындалуда",
      "crisis.task.done": "орындалды",
      "crisis.task.add": "Тапсырма қосу",
      "crisis.task.text": "Не істеу керек",
      "crisis.updates": "Жаңартулар",
      "crisis.update.public": "Аймақ тұрғындарына",
      "crisis.update.internal": "Тек штабқа",
      "crisis.update.ru": "Орысша мәтін",
      "crisis.update.kk": "Қазақша мәтін",
      "crisis.update.send": "Тұрғындарға жаңарту жіберу",
      "crisis.update.save_note": "Жазбаны сақтау",
      "crisis.update.sent": "Жаңарту аймақ тұрғындарына жіберілді",
      "crisis.update.noted": "Жазба сақталды",
      "crisis.update.template": "Дайын мәтінді қою",
      "crisis.update.empty": "Әзірге жаңарту жоқ",
      "crisis.show_map": "Картадан көрсету",
      "crisis.close": "Қорытындымен жабу",
      "crisis.close.title": "Тұрғындарға қорытынды",
      "crisis.close.ru": "Орысша қорытынды",
      "crisis.close.kk": "Қазақша қорытынды",
      "crisis.close.confirm": "Жабу және қорытындыны хабарлау",
      "crisis.closed_ok": "Штаб жабылды, аймақ тұрғындары қорытындыны көреді",
      "crisis.result": "Қорытынды",
      "crisis.none": "Қазір төтенше жағдай жоқ",
      "crisis.none_text": "Боран, апат немесе құбыр жарылса, штабты ашыңыз: аймақ, қызметтердің тапсырмалары, тұрғындарға жаңартулар.",
      "crisis.new": "Жедел штабты ашу",
      "crisis.new.title": "Жаңа жедел штаб",
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
      "common.demo": "Үлгі",
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
    // Задача кризиса: «не начата» — свой серый круг (не красное «новое» жалобы), в работе — оранжевый, сделано — зелёный.
    s.setAttribute("data-status", status === "doing" ? "in_progress" : status === "done" ? "verified" : status);
    s.setAttribute("width", String(size || 14));
    s.setAttribute("height", String(size || 14));
    return s;
  }
  function demoTag() { return h("span", { class: "ag-demo" }, [tr("common.demo")]); }

  // ------------------------------------------------------------------ сеть
  // Клиент API v2. X-CSRF-Token сотрудника — во ВСЕХ запросах (шлюз R01 раунда 15 требует его и для чтения табло,
  // CONTRACT §7 «сотрудник = сессия + CSRF»): из оболочки (CivicShell.csrfToken) или, если её токена ещё нет (сотрудник
  // не открывал редактор), один раз из GET /api/civic/v1/session — как R08 «Службы». Житель без сессии — без токена.
  // Клиент оболочки (opts.api.v2) не берём: он шлёт токен только из CivicShell и на свежей вкладке ушёл бы без него.
  function makeClient(opts) {
    var cached = null, asked = false;
    function csrf(force) {
      try {
        var cs = root.CivicShell;
        var token = cs && typeof cs.csrfToken === "function" ? cs.csrfToken() : null;
        if (token) return Promise.resolve(token);
      } catch (e) { /* оболочки нет */ }
      if (cached || (asked && !force)) return Promise.resolve(cached);
      asked = true;
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
      return csrf().then(function (token) {
        return send(method, path, body, token).catch(function (err) {
          // Токен устарел или вход случился после первого запроса — один повтор со свежим.
          if (err && (err.error === "csrf_failed" || err.status === 401 || err.status === 403) && !err.retried) {
            cached = null;
            return csrf(true).then(function (fresh) {
              if (!fresh) throw err;
              return send(method, path, body, fresh).catch(function (again) { again.retried = true; throw again; });
            });
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
  // Вкладки «Ведомств» (IA_ROUND15 §5.4): «Календарь работ» — модуль R12 внутри экрана R17, если он есть в сборке.
  var TABS = ["board", "joint", "handoffs", "calendar", "crisis"];
  var INC_RE = /^inc-[a-z0-9-]{4,40}$/;
  function calendarModule() {
    var m = root.BirgeWorksCalendar;
    return m && typeof m.mount === "function" ? m : null;
  }
  function tabsAvailable() { return TABS.filter(function (t) { return t !== "calendar" || calendarModule(); }); }
  // Путь раздела оболочки (IA_ROUND15 §7.3, #agencies/<путь>): board | joint | handoffs | calendar | crisis |
  // crisis/<id кризиса> | crisis/new[/<шаблон>[/<район>]]. Неизвестный путь — null (вкладка из памяти).
  function parsePath(path) {
    // Прежний вид ссылки (R08 «Картина дня»): crisis=<id> и crisis=new&template=<шаблон>&district=<район>.
    var prev = /^crisis=([^&/]+)(.*)$/.exec(String(path || ""));
    if (prev) {
      var params = {};
      (prev[2] || "").replace(/[&?]([a-z_]+)=([^&]*)/g, function (w, k, v) { params[k] = decodeURIComponent(v); });
      if (prev[1] === "new") return { tab: "crisis", create: { template: params.template || null,
        district: DISTRICTS.indexOf(params.district) >= 0 ? params.district : null } };
      var prevId = decodeURIComponent(prev[1]);
      return INC_RE.test(prevId) ? { tab: "crisis", incident: prevId } : { tab: "crisis" };
    }
    var parts = String(path || "").split("/").filter(Boolean);
    if (TABS.indexOf(parts[0]) < 0) return null;
    if (parts[0] === "calendar" && !calendarModule()) return { tab: "board" };
    if (parts[0] !== "crisis") return { tab: parts[0] };
    if (parts[1] === "new") return { tab: "crisis", create: { template: parts[2] || null, district: DISTRICTS.indexOf(parts[3]) >= 0 ? parts[3] : null } };
    if (INC_RE.test(parts[1] || "")) return { tab: "crisis", incident: parts[1] };
    return { tab: "crisis" };
  }

  function mount(rootEl, options) {
    var opts = { apiBase: "/api/civic/v2", titleTag: "h2" };
    Object.keys(options || {}).forEach(function (k) { if (options[k] != null) opts[k] = options[k]; });
    // Раздел «crisis» (#crisis/<id>) — публичная карточка кризиса для жителя и сотрудника (IA_ROUND15 §3, §5.12).
    if (opts.section === "crisis") return mountPublic(rootEl, opts);
    var request = makeClient(opts);
    // Старый спрайт без значков служб раунда 15 — один раз перерисовать значки запасными (iconOf), только если нужно.
    loadSprite(function () {
      if (!S.alive || !sprite.ids) return;
      var map = profileMap();
      if (Object.keys(map).some(function (k) { return map[k].icon && !sprite.ids[map[k].icon] && map[k].icon_fallback; })) render();
    });
    var S = {
      tab: "board", days: 30, district: "", sort: { key: "overdue", dir: -1 },
      meta: null, board: null, joint: null, handoffs: null, incidents: null, detail: {},
      open: null, openItems: {}, calendar: null, crisis: { id: null, form: null, closing: false, composer: { ru: "", kk: "", public: true } },
      loading: {}, slow: {}, error: {}, seq: 0, alive: true, lang: lang(),
    };
    try {
      var saved = JSON.parse(root.sessionStorage.getItem("birge.agencies") || "{}");
      if (tabsAvailable().indexOf(saved.tab) >= 0) S.tab = saved.tab;
      if (PERIODS.indexOf(saved.days) >= 0) S.days = saved.days;
      if (DISTRICTS.indexOf(saved.district) >= 0) S.district = saved.district;
    } catch (e) { /* приватный режим: умолчания */ }
    function remember() {
      try { root.sessionStorage.setItem("birge.agencies", JSON.stringify({ tab: S.tab, days: S.days, district: S.district })); } catch (e) { /* нет хранилища */ }
    }

    var startPath = parsePath(opts.path);
    var createOnStart = null;
    if (startPath) {
      S.tab = startPath.tab;
      if (startPath.incident) S.crisis.id = startPath.incident;
      if (startPath.create) createOnStart = startPath.create;
    }
    // Адрес раздела следует за вкладкой (#agencies/joint): оболочка R01 раунда 15 даёт navigate(path).
    function navigate(path) {
      if (typeof opts.navigate !== "function") return;
      S.navigating = path;
      try { opts.navigate(path); } catch (e) { /* оболочка без путей — адрес не меняем */ }
      S.navigating = null;
    }
    function currentPath() {
      if (S.tab !== "crisis") return S.tab;
      return S.crisis.id ? "crisis/" + S.crisis.id : "crisis";
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
        else if (S.tab === "calendar") { if (S.calendar && S.calendar.handle && S.calendar.handle.reload) S.calendar.handle.reload(); }
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
        tabsAvailable().map(function (id) {
          var live = null;
          // «У «Кризиса» точка-пульс, пока кризис активен» (IA_ROUND15 §5.4); для чтения с экрана — слово «идёт».
          if (id === "crisis" && activeCount() > 0) {
            live = h("span", { class: "ag-tabdot", "data-live": "" }, [h("span", { class: "bk-sr-only", text: " · " + tr("crisis.active") })]);
          }
          return h("button", { type: "button", role: "tab", value: id, "aria-selected": String(S.tab === id), "data-tab": id,
            tabindex: S.tab === id ? "0" : "-1" }, [tr("agencies.tab." + id), live]);
        }));
      tabs.addEventListener("click", function (e) {
        var b = e.target.closest('[role="tab"]');
        if (b && b.value !== S.tab) setTab(b.value);
      });
      tabs.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        var ids = tabsAvailable(), i = ids.indexOf(S.tab);
        e.preventDefault();
        setTab(ids[(i + (e.key === "ArrowRight" ? 1 : ids.length - 1)) % ids.length], true);
      });
      // В шапке — только заголовок и вкладки (длинные казахские подписи не переносят строку); период и район — в строке
      // KPI табло или в строке подсказки списков (filtersBar), «Обновить» — в строке «Обновлено» под ними.
      var filters = h("div", { class: "ag-filters" });
      if (S.tab === "crisis") {
        filters.appendChild(h("button", { type: "button", class: "ag-iconbtn", "aria-label": tr("agencies.refresh"),
          title: tr("agencies.refresh"), onclick: refresh }, [svg("i-refresh")]));
      }
      var title = h(opts.titleTag === "h1" ? "h1" : "h2", { class: "ag-title", text: tr("agencies.title") });
      // «Пример» — на виду, рядом с заголовком, если числа вкладки синтетические (COMMON «Честность»).
      var current = S.tab === "crisis" || S.tab === "calendar" ? null : S[S.tab];
      var demo = current && (current.source === "fixture" || current.demo) ? h("span", { class: "ag-demo ag-demo--head",
        title: current.source === "fixture" ? tr("agencies.demo_note") : null }, [tr("common.demo")]) : null;
      headBox.replaceChildren.apply(headBox, [title, demo, tabs, filters].filter(Boolean));
    }
    // Период 7 · 30 · 90 дней и район — для табло, совместных и передач.
    function filtersBar() {
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
      // «Пример» на телефоне — рядом с периодом (R11 R17-12); на компьютере он у заголовка (.ag-demo--head).
      // Только у табло: в «Совместных» и «Передачах» плашка «Пример» есть у каждой строки.
      var current = S.tab === "board" ? S.board : null;
      var demo = current && (current.source === "fixture" || current.demo)
        ? h("span", { class: "ag-demo ag-demo--bar", title: current.source === "fixture" ? tr("agencies.demo_note") : null }, [tr("common.demo")])
        : null;
      return h("div", { class: "ag-filters ag-filters--bar" }, [seg, select, demo].filter(Boolean));
    }
    function activeCount() {
      if (S.activeHint != null && !S.incidents) return S.activeHint;
      return ((S.incidents && S.incidents.items) || []).filter(function (x) { return x.status === "active"; }).length;
    }
    function setTab(id, focus) {
      S.tab = id;
      S.open = null;
      remember();
      navigate(currentPath());
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
      if (data.generated_at) {
        bits.push(h("button", { type: "button", class: "ag-link ag-link--quiet", "data-action": "refresh", onclick: refresh,
          title: tr("agencies.refresh") }, [svg("i-refresh"), tr("agencies.updated", { time: fmtTime(data.generated_at) })]));
      }
      return h("div", { class: "ag-note" }, bits);
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
      return h("span", { class: "ag-svc__ic" }, [svg("i-" + iconOf(p))]);
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
      fix: function (r) { return [r.overdue_fix || 0, r.open]; },
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
        // Два разных «просрочено» (R02 INTEGRATION §3, R10 B-104): срок первого ответа R09 и срок исправления R08.
        kpi(totals.overdue, tr("agencies.kpi.overdue_answer"), totals.overdue > 0),
        totals.overdue_fix == null ? null : kpi(totals.overdue_fix, tr("agencies.kpi.overdue_fix"), totals.overdue_fix > 0),
        kpi(totals.joint, tr("agencies.kpi.joint")),
        // Передачи и «проверено жителями» — в столбцах табло (по службам) и во вкладке «Передачи»: четыре плитки шире,
        // подписи двух «просрочено» и казахские слова не режутся (трёхзначные числа демо-мира на 1366).
        totals.overdue_fix == null ? kpi(totals.verified_share == null ? "—" : pct(totals.verified_share), tr("agencies.kpi.verified")) : null,
      ]);
      var table = h("div", { class: "ag-table", role: "table", "aria-label": tr("agencies.tab.board") });
      var hasFix = totals.overdue_fix != null;
      var cols = [["name", "agencies.col.service"], ["open", "agencies.col.open"], ["overdue", "agencies.col.deadline", "agencies.col.deadline_hint"],
        hasFix ? ["fix", "agencies.col.fix", "agencies.col.fix_hint"] : null,
        ["answer", "agencies.col.answer", "agencies.col.answer_hint"], ["verified", "agencies.col.verified", "agencies.col.verified_hint"],
        ["returned", "agencies.col.returned", "agencies.col.returned_hint"], ["handoffs", "agencies.col.handoffs", "agencies.col.handoffs_hint"],
        ["joint", "agencies.col.joint", "agencies.col.joint_hint"]].filter(Boolean);
      if (hasFix) table.classList.add("ag-table--fix");
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
      var sortSelect = h("select", { class: "ag-select" }, ["overdue", hasFix ? "fix" : null, "open", "answer", "verified", "name"].filter(Boolean).map(function (k) {
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
      var services = h("button", { type: "button", class: "ag-link", "data-action": "services", onclick: function () {
        if (typeof opts.openSection === "function") opts.openSection("services");
        else if (root.BirgeShell) root.BirgeShell.setSection("services");
      } }, [tr("agencies.services_link"), svg("i-chevron-right")]);
      var parts = [h("div", { class: "ag-kpirow" }, [kpis, filtersBar()]), sortbar, table,
        h("div", { class: "ag-foot" }, [legend, services]), noteLine(data)];
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
      var hasFix = r.overdue_fix != null;
      // Строка — role="row" с фокусом (Enter/пробел раскрывают), а не <button role="row">: у кнопки не может быть
      // роли строки (ARIA in HTML). Высота 26 px на компьютере — плотная таблица (20 служб на экране 1366, R10 B-110:
      // «строки не трогать»); на телефоне строка в две линии, выше 44 px.
      var row = h("div", { class: "ag-row" + (quiet ? " ag-row--quiet" : ""), role: "row", tabindex: "0", "data-service": r.service,
        "aria-expanded": String(S.open === r.service),
        "aria-label": hasFix ? tr("agencies.row.label_v2", { name: name, open: r.open, overdue: r.overdue, fix: r.overdue_fix })
          : tr("agencies.row.label", { name: name, open: r.open, overdue: r.overdue }) }, [
        h("span", { class: "ag-svc", role: "cell" }, [serviceBadge(r.service), h("span", { class: "ag-svc__name", text: name, title: name }),
          pickupsMark(r.service)]),
        h("span", { class: "ag-num" + (r.open ? "" : " ag-num--zero"), role: "cell", "data-col": "open", text: num(r.open) }),
        deadlineBar(r, maxOpen),
        hasFix ? h("span", { class: "ag-num" + (r.overdue_fix ? " ag-num--alert" : " ag-num--zero"), role: "cell", "data-col": "fix",
          title: tr("agencies.col.fix_hint"), text: num(r.overdue_fix) }) : null,
        h("span", { class: "ag-num" + (r.median_answer_days == null ? " ag-num--zero" : ""), role: "cell", "data-col": "answer",
          text: r.median_answer_days == null ? "—" : tr("agencies.days_short", { n: r.median_answer_days }) }),
        h("span", { class: "ag-share", role: "cell", "data-col": "verified" }, [
          h("span", { class: "ag-share__track", "aria-hidden": "true" }, [h("span", { class: "ag-share__fill",
            style: { width: Math.round((r.verified_share || 0) * 100) + "%" } })]),
          h("span", { class: "ag-num" + (r.verified_share == null ? " ag-num--zero" : ""), text: pct(r.verified_share) })]),
        h("span", { class: "ag-num" + (r.returned ? "" : " ag-num--zero"), role: "cell", "data-col": "returned", text: num(r.returned) }),
        h("span", { class: "ag-flow", role: "cell", "data-col": "handoffs" }, [
          h("span", { class: r.handoffs_in ? null : "bk-board__zero", "data-zero": r.handoffs_in ? null : "", text: "↓" + num(r.handoffs_in) }),
          h("span", { class: r.handoffs_out ? null : "bk-board__zero", "data-zero": r.handoffs_out ? null : "", text: "↑" + num(r.handoffs_out) })]),
        h("span", { class: "ag-num" + (r.joint ? "" : " ag-num--zero"), role: "cell", "data-col": "joint", text: num(r.joint) }),
        h("span", { class: "ag-mobile-meta" }, [
          h("span", { text: tr("agencies.kpi.overdue_answer") + ": " + num(r.overdue) }),
          hasFix ? h("span", { text: tr("agencies.kpi.overdue_fix") + ": " + num(r.overdue_fix) }) : null,
          h("span", { text: tr("agencies.col.answer") + ": " + (r.median_answer_days == null ? "—" : tr("agencies.days_short", { n: r.median_answer_days })) }),
          h("span", { text: tr("agencies.col.verified") + ": " + pct(r.verified_share) })]),
      ]);
      function toggle() {
        S.open = S.open === r.service ? null : r.service;
        if (S.open && !S.openItems[r.service]) loadServiceItems(r.service);
        render();
        var again = bodyBox.querySelector('[data-service="' + r.service + '"]');
        if (again) again.focus();
      }
      row.addEventListener("click", toggle);
      row.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") { e.preventDefault(); toggle(); }
      });
      return row;
    }
    // Задачи вывоза после дел жителей, поддержанных акиматом (R16 pickups): сколько — в строке службы, что — в раскрытой.
    function pickupsMark(service) {
      var n = ((S.board && S.board.pickups) || {})[service] || 0;
      if (!n) return null;
      return h("span", { class: "ag-pill ag-svc__extra", title: tr("agencies.pickups.hint", { n: n }),
        "aria-label": tr("agencies.pickups.hint", { n: n }) }, [svg("i-calendar"), num(n)]);
    }
    function loadServiceItems(service) {
      S.openItems[service] = { loading: true };
      request("GET", "/agencies/board" + query() + "&service=" + encodeURIComponent(service)).then(function (d) {
        S.openItems[service] = { items: d.items || [], pickups: d.pickup_items || [] };
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
        appendPickups(box, st.pickups);
        return box;
      }
      var list = h("ul", { class: "ag-items" });
      st.items.slice(0, 8).forEach(function (item) {
        list.appendChild(h("li", { class: "ag-item ag-item--link" }, [h("button", { type: "button", class: "ag-item__btn",
          "data-complaint": item.id, title: tr("agencies.detail.open_one"),
          onclick: function () { openComplaint(item.id, r.service); } }, [
          statusIcon(item.part && item.part.status === "done" ? "done" : item.status, 14),
          h("span", { class: "ag-item__code", text: item.code || "" }),
          h("span", { class: "ag-item__title", text: itemTitle(item) }),
          item.joint ? h("span", { class: "ag-pill", text: tr("agencies.tab.joint") }) : null,
          deadlinePill(item.deadline, item.tab),
          h("span", { class: "ag-item__meta", text: fmtDate(item.created_at) }),
          item.demo ? demoTag() : null,
        ])]));
      });
      box.appendChild(list);
      if (st.items.length > 8) box.appendChild(h("p", { class: "ag-note", text: tr("agencies.detail.more", { n: st.items.length - 8 }) }));
      appendPickups(box, st.pickups);
      return box;
    }
    function appendPickups(box, items) {
      if (!items || !items.length) return;
      box.appendChild(h("p", { class: "ag-detail__title ag-detail__sub", text: tr("agencies.pickups.title") }));
      box.appendChild(h("ul", { class: "ag-items", "data-list": "pickups" }, items.slice(0, 8).map(function (item) {
        return h("li", { class: "ag-item" }, [
          svg("i-calendar"),
          h("span", { class: "ag-item__title", text: [item.title, item.note].filter(Boolean).join(" · ") }),
          h("span", { class: "ag-item__meta", text: item.starts_at ? tr("agencies.pickups.when", { date: fmtDate(item.starts_at), time: fmtTime(item.starts_at) }) : "" }),
          item.demo ? demoTag() : null,
        ]);
      })));
    }
    // «Обращения» R09 одной службы: адрес #inbox/service=<id> (R09 v2.1 читает service= из адреса и ставит чип
    // «Служба: …»); оболочка без путей разделов (FINAL-4) — раздел inbox + событие (INTEGRATION R17 §4).
    function openInboxFor(service, items) {
      var detail = { service: service, ids: (items || []).map(function (x) { return x.id; }) };
      try { root.sessionStorage.setItem("birge.inbox.filter", JSON.stringify(detail)); } catch (e) { /* без хранилища */ }
      var shell = root.BirgeShell;
      var paths = !!(shell && typeof shell.alertSlot === "function");   // оболочка раунда 15: «#раздел/путь»
      var path = /^[a-z_]{2,30}$/.test(service || "") && paths ? "service=" + service : "";
      if (typeof opts.openSection === "function") opts.openSection(path ? "inbox/" + path : "inbox");
      else if (shell) shell.setSection("inbox", path ? { path: path } : undefined);
      setTimeout(function () { doc.dispatchEvent(new CustomEvent("birge:inbox-filter", { detail: detail })); }, 0);
    }

    // Одна жалоба в «Обращениях» R09: #inbox/<id> (оболочка R01 B0.6 сама кладёт фильтр «одна жалоба» для экрана R09);
    // старая оболочка — тот же фильтр в sessionStorage и раздел inbox (INTEGRATION R17 §4). Сцена 8: строка табло → карточка.
    function openComplaint(id, service) {
      if (!/^c-[A-Za-z0-9_-]{1,80}$/.test(id || "")) return openInboxFor(service, []);
      var detail = { ids: [id], service: service || null };
      try { root.sessionStorage.setItem("birge.inbox.filter", JSON.stringify(detail)); } catch (e) { /* без хранилища */ }
      var shell = root.BirgeShell;
      var paths = !!(shell && typeof shell.alertSlot === "function");
      if (typeof opts.openSection === "function") opts.openSection(paths ? "inbox/" + id : "inbox");
      else if (shell) shell.setSection("inbox", paths ? { path: id } : undefined);
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
      var head = h("div", { class: "ag-toolbar" }, [h("p", { class: "ag-note", text: tr("agencies.joint.hint") }), filtersBar()]);
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
          h("button", { type: "button", class: "ag-lrow__main ag-linkbtn", "data-complaint": item.id,
            title: tr("agencies.detail.open_one"), onclick: function () { openComplaint(item.id, item.lead); } },
            [h("span", { class: "ag-lrow__title", text: itemTitle(item) }), h("span", { class: "ag-lrow__sub" }, sub)]),
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
      var hint = h("div", { class: "ag-toolbar" }, [h("p", { class: "ag-note" }, [h("span", { text: tr("agencies.handoffs.hint") }),
        data.loops ? h("span", { class: "ag-pill ag-pill--loop", title: tr("agencies.loop_hint"), text: tr("agencies.handoffs.loops", { n: data.loops }) }) : null]),
        filtersBar()]);
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
          h("button", { type: "button", class: "ag-lrow__main ag-linkbtn", "data-complaint": e.complaint_id,
            title: tr("agencies.detail.open_one"), onclick: function () { openComplaint(e.complaint_id, e.to); } }, [
            h("span", { class: "ag-lrow__title" }, [serviceName(e.from) + " → " + serviceName(e.to)]),
            e.reason ? h("span", { class: "ag-quote", text: "«" + e.reason + "»" }) : null,
            h("span", { class: "ag-lrow__sub" }, sub)]),
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
        S.crisis.pick = S.crisis.pick || "blizzard";
        emptyState(box, tr("crisis.none"), tr("crisis.none_text"), null, "check");
        var picks = h("div", { class: "ag-templates ag-templates--center", role: "radiogroup", "aria-label": tr("crisis.new.kind") },
          ["blizzard", "heat_outage", "water_outage"].map(function (kind) {
            return h("button", { type: "button", class: "bk-chip", role: "radio", "aria-checked": String(S.crisis.pick === kind), "data-kind": kind,
              onclick: function () { S.crisis.pick = kind; render(); } }, [svg("i-" + KIND_ICONS[kind]), tr("crisis.kind." + kind)]);
          }));
        var open = h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-action": "new-crisis",
          onclick: function () { openForm(S.crisis.pick, null); } }, [tr("crisis.new")]);
        var inner = box.querySelector(".bk-empty") || box;
        inner.append(picks, open);
        parts.push(box);
      } else {
        if (active.length > 1) {
          parts.push(h("div", { class: "ag-chips", role: "group" }, active.map(function (inc) {
            return h("button", { type: "button", class: "bk-chip", "aria-pressed": String(S.crisis.id === inc.id),
              onclick: function () { S.crisis.id = inc.id; navigate("crisis/" + inc.id); loadIncident(inc.id); render(); } }, [pick(inc, "title")]);
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
        chronicleAvailable() ? h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-action": "chronicle",
          onclick: function () { openChronicle(full); } }, [svg("i-clock"), tr("crisis.chronicle")]) : null,
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
          h("span", { class: "ag-pill" + (u.public === false ? "" : " ag-pill--info"), text: u.public === false ? tr("crisis.update.internal") : tr("crisis.update.public") }),
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
        S.crisis.id = d.incident.id;
        navigate("crisis/" + d.incident.id);
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
    function chronicleAvailable() {
      var shell = root.BirgeShell;
      return !!((shell && typeof shell.openReplay === "function") || root.BirgeReplay);
    }
    function openChronicle(inc) {
      var shell = root.BirgeShell;
      var opts7 = { days: 7, district: inc.zone && inc.zone.district || null, from: inc.started_at };
      if (shell && typeof shell.openReplay === "function") { shell.openReplay(opts7); return; }
      if (shell) shell.setSection("map");
      setTimeout(function () {
        var chip = doc.querySelector(".birge-replay-chip");
        if (chip) chip.click();
      }, 50);
    }
    function showOnMap(inc) {
      var layer = root.BirgeCrisisLayer;
      if (layer && layer.focus) layer.focus(inc.id);
      else if (typeof opts.openSection === "function") opts.openSection("map");
    }

    // ---------------------------------------------------------------- отрисовка
    // ---------------------------------------------------------------- «Календарь работ» (модуль R12 внутри вкладки)
    // IA_ROUND15 §5.4: BirgeWorksCalendar.mount(panel, {map, apiBase, embedded: true, openTarget}); главная кнопка
    // вкладки — «Добавить работу» → раздел «Работы и отключения» R06 (#works). Модуль монтируется один раз за показ.
    function dropCalendar() {
      if (!S.calendar) return;
      try { if (S.calendar.handle && S.calendar.handle.destroy) S.calendar.handle.destroy(); } catch (e) { /* модуль R12 */ }
      S.calendar = null;
    }
    function renderCalendar() {
      var mod = calendarModule();
      if (!mod) {
        var box = h("div", { class: "ag-empty" });
        emptyState(box, tr("agencies.calendar.missing"), null, null, "calendar");
        return bodyBox.replaceChildren(box);
      }
      if (S.calendar && bodyBox.contains(S.calendar.panel)) return;
      dropCalendar();
      var panel = h("div", { class: "ag-calendar", "data-calendar": "" });
      var add = h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-action": "add-work", onclick: function () {
        if (typeof opts.openSection === "function") opts.openSection("works");
        else if (root.BirgeShell) root.BirgeShell.setSection("works");
      } }, [svg("i-plus"), tr("agencies.calendar.add")]);
      // R12 в режиме embedded сам рисует главную «Добавить работу» в строке фильтров (.wcal-addmain) — тогда своя
      // прячется (CSS :has), одна главная кнопка на экран (R10 B-115). Старый R12 без неё — видна эта.
      bodyBox.replaceChildren(h("div", { class: "ag-actions ag-actions--end", "data-calendar-actions": "" }, [add]), panel);
      try {
        // Клиент R17 вместо клиента оболочки: он сам достаёт CSRF сотрудника из сессии (шлюз R01 требует его и в GET
        // календаря), ошибки — {status, error, message}, как ждёт R12 (err.status).
        var calendarApi = { v2: request, ApiError: (opts.api && opts.api.ApiError) || Error };
        S.calendar = { panel: panel, handle: mod.mount(panel, { apiBase: opts.apiBase, api: calendarApi, map: opts.map, embedded: true,
          openTarget: opts.openTarget, close: opts.close, lang: lang(), t: opts.t }) || {} };
      } catch (e) {
        if (root.console) root.console.error("agencies calendar", e);
        S.calendar = null;
        errorState(panel, { status: 503 }, function () { S.calendar = null; render(); });
      }
    }

    function render() {
      if (!S.alive) return;
      renderHead();
      rootEl.setAttribute("data-tab", S.tab);
      if (S.tab !== "calendar") dropCalendar();
      if (S.tab === "board") renderBoard();
      else if (S.tab === "joint") renderJoint();
      else if (S.tab === "handoffs") renderHandoffs();
      else if (S.tab === "calendar") renderCalendar();
      else renderCrisis();
    }
    function relang() {
      if (S.lang === lang()) return;
      S.lang = lang();
      if (S.calendar && S.calendar.handle && S.calendar.handle.setLang) {
        try { S.calendar.handle.setLang(S.lang); } catch (e) { /* модуль R12 */ }
      }
      render();
    }
    // Тот же раздел, другой путь (оболочка зовёт setPath без перемонтажа): вкладка, кризис или форма нового.
    function setPath(path) {
      if (S.navigating != null && S.navigating === path) return;
      var next = parsePath(path);
      if (!next) return;
      if (next.create) { openForm(next.create.template, next.create.district); return; }
      var sameTab = next.tab === S.tab, sameIncident = !next.incident || next.incident === S.crisis.id;
      if (sameTab && sameIncident) return;
      S.tab = next.tab;
      S.open = null;
      if (next.incident) { S.crisis.id = next.incident; S.crisis.form = null; }
      remember();
      refresh();
    }
    var off = null;
    if (I() && typeof I().onChange === "function") off = I().onChange(relang);

    var handle = {
      setLang: relang,
      setPath: setPath,
      destroy: function () {
        S.alive = false;
        dropCalendar();
        if (typeof off === "function") off();
        if (mounted === handle) mounted = null;
        rootEl.classList.remove("ag");
        rootEl.removeAttribute("data-agencies");
      },
      openCrisis: function (target) {
        S.tab = "crisis";
        remember();
        if (target && target.incident) {
          S.crisis.id = target.incident;
          S.crisis.form = null;
          navigate("crisis/" + target.incident);
          loadMeta().then(function () { loadIncidents(target.incident); });
        } else openForm(target && target.template, target && target.district);
        render();
      },
      state: S,
    };
    mounted = handle;
    if (pending) {
      var p = pending;
      pending = null;
      handle.openCrisis(p);
    } else if (createOnStart) {
      openForm(createOnStart.template, createOnStart.district);
    } else {
      refresh();
    }
    if (S.tab === "crisis" && !S.incidents) loadMeta().then(function () { loadIncidents(S.crisis.id); });
    // Точка-пульс у вкладки «Кризис» видна сразу, даже если открыта другая вкладка (лёгкий запрос публичного списка).
    if (S.tab !== "crisis") {
      request("GET", "/incidents?status=active").then(function (d) {
        S.activeHint = ((d && d.items) || []).length;
        if (S.alive) renderHead();
      }, function () { /* без точки */ });
    }
    return handle;
  }

  // ------------------------------------------------------------------ публичная карточка кризиса (раздел «crisis»)
  // #crisis/<id> — баннер жителю, уведомление R06, Ctrl+K (IA_ROUND15 §3, §5.12). Только публичная часть: без задач
  // служб, заметок штаба и журнала. Без id — идущие кризисы списком. Сотруднику — ещё «Открыть в штабе».
  function mountPublic(rootEl, opts) {
    var request = makeClient(opts);
    var P = { alive: true, id: null, data: null, list: null, names: {}, error: null, lang: lang(), slow: false };
    rootEl.classList.add("ag", "ag-pub", "bk-app");
    rootEl.setAttribute("data-agencies-public", "");
    var box = h("div", { class: "ag-body", "aria-live": "polite" });
    rootEl.replaceChildren(box);
    function svcName(id) {
      var i = I();
      if (i && i.has && i.has("service." + id)) return i.t("service." + id);
      var n = P.names[id];
      return (n && (n[lang()] || n.ru)) || id;
    }
    function load(path) {
      var first = String(path || "").split("/").filter(Boolean)[0] || "";
      P.id = INC_RE.test(first) ? first : null;
      P.data = null;
      P.list = null;
      P.error = null;
      P.slow = false;
      var timer = setTimeout(function () { if (P.alive && !P.data && !P.list && !P.error) { P.slow = true; render(); } }, SKELETON_DELAY);
      var names = request("GET", "/agencies").then(function (d) {
        ((d && d.services) || []).forEach(function (svc) { P.names[svc.id] = svc; });
      }, function () { /* названия — из словаря R11 */ });
      var main = P.id
        ? request("GET", "/incidents/" + encodeURIComponent(P.id)).then(function (d) { P.data = d.incident; })
        : request("GET", "/incidents?status=active").then(function (d) { P.list = (d && d.items) || []; });
      Promise.all([names, main.catch(function (err) { P.error = err || { status: 0 }; })]).then(function () {
        clearTimeout(timer);
        if (P.alive) render();
      });
      render();
    }
    function zoneLabel(inc) {
      var label = inc.zone_label || {};
      return label[lang()] || label.ru || districtName(inc.zone && inc.zone.district);
    }
    function card(inc) {
      var active = inc.status === "active";
      var sub = [h("span", { text: tr("crisis.zone", { zone: zoneLabel(inc) }) }),
        h("span", { text: tr("crisis.started", { time: fmtWhen(inc.started_at) }) }),
        active ? null : h("span", { text: tr("crisis.closed") }), inc.demo ? demoTag() : null];
      var parts = [h("div", { class: "ag-card__head" }, [
        h("span", { class: "ag-card__badge", "data-live": active ? "" : null }, [svg("i-" + (KIND_ICONS[inc.kind] || "alert"))]),
        h("div", null, [h("h3", { class: "ag-card__title", text: pick(inc, "title") }), h("div", { class: "ag-card__sub" }, sub)])])];
      if ((inc.services || []).length) {
        parts.push(h("p", { class: "ag-upd__text" }, [h("strong", { text: tr("crisis.public.services") + ": " }),
          inc.services.map(svcName).join(" · ")]));
      }
      if (inc.result) parts.push(h("p", { class: "ag-upd__text" }, [h("strong", { text: tr("crisis.result") + ": " }), pick(inc.result, "text")]));
      var updates = (inc.updates || []).filter(function (u) { return u.public !== false; });
      parts.push(h("p", { class: "ag-section-title", text: tr("crisis.public.updates") }));
      parts.push(updates.length ? h("ul", { class: "ag-feed" }, updates.map(function (u) {
        return h("li", { class: "ag-upd" }, [h("div", { class: "ag-upd__meta" }, [h("span", { text: fmtWhen(u.at) }),
          u.kind === "closed" ? h("span", { class: "ag-pill", text: tr("crisis.result") }) : null]),
          h("p", { class: "ag-upd__text", text: pick(u, "text") })]);
      })) : h("p", { class: "ag-note", text: tr("crisis.update.empty") }));
      var actions = [h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-action": "show-zone", onclick: function () {
        if (root.BirgeCrisisLayer && root.BirgeCrisisLayer.focus) root.BirgeCrisisLayer.focus(inc.id);
        else if (typeof opts.openSection === "function") opts.openSection("map");
      } }, [svg("i-pin"), tr("crisis.public.show")])];
      if (opts.role === "akimat") {
        actions.push(h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-action": "open-hq", onclick: function () {
          if (typeof opts.openSection === "function") opts.openSection("agencies", "crisis/" + inc.id);
          else openCrisis({ incident: inc.id });
        } }, [tr("crisis.open_hq")]));
      }
      parts.push(h("div", { class: "ag-actions" }, actions));
      return h("section", { class: "ag-card ag-card--public", "data-incident": inc.id, "aria-label": pick(inc, "title") }, parts);
    }
    function render() {
      if (!P.alive) return;
      if (P.error) {
        if (P.error.status === 404) {
          var nf = h("div", { class: "ag-empty" });
          emptyState(nf, tr("crisis.none"), null, null, "check");
          return box.replaceChildren(nf);
        }
        return errorState(box, P.error, function () { load(P.id || ""); });
      }
      if (P.id && !P.data || !P.id && !P.list) {
        return box.replaceChildren(P.slow ? h("div", { class: "ag-card", "aria-busy": "true" }, [h("span", { class: "bk-skel bk-skel--title" }),
          h("span", { class: "bk-skel bk-skel--line" })]) : h("div", { "aria-busy": "true" }));
      }
      if (P.data) return box.replaceChildren(card(P.data));
      if (!P.list.length) {
        var empty = h("div", { class: "ag-empty" });
        emptyState(empty, tr("crisis.none"), null, null, "check");
        return box.replaceChildren(empty);
      }
      box.replaceChildren.apply(box, P.list.map(card));
    }
    function relang() {
      if (P.lang === lang()) return;
      P.lang = lang();
      render();
    }
    var off = I() && typeof I().onChange === "function" ? I().onChange(relang) : null;
    load(opts.path);
    return {
      setLang: relang,
      setPath: function (path) { load(path); },
      destroy: function () {
        P.alive = false;
        if (typeof off === "function") off();
        rootEl.classList.remove("ag", "ag-pub");
        rootEl.removeAttribute("data-agencies-public");
      },
    };
  }

  // ------------------------------------------------------------------ вход из других разделов
  function crisisPath(target) {
    if (target && target.incident) return "crisis/" + target.incident;
    var path = "crisis/new";
    if (target && target.template) path += "/" + target.template + (target.district ? "/" + target.district : "");
    return path;
  }
  function openCrisis(target) {
    target = target || {};
    if (mounted) {
      mounted.openCrisis(target);
      return;
    }
    pending = target;
    var shell = root.BirgeShell;
    if (shell && typeof shell.setSection === "function") shell.setSection("agencies", { path: crisisPath(target) });
  }
  // Глубокая ссылка на кризис для оболочки БЕЗ путей разделов (FINAL-4): #agencies/crisis/<id>,
  // #agencies/crisis/new/<шаблон>/<район> и прежний вид #agencies/crisis=<id>. Оболочка R01 раунда 15 ведёт такие
  // адреса сама (раздел agencies + путь) — тогда здесь ничего не делаем.
  function fromHash() {
    var hash = root.location.hash || "";
    var target = null;
    var m = /^#agencies\/(crisis(?:\/[A-Za-z0-9_-]+){0,3})$/.exec(hash);
    if (m) {
      var parsed = parsePath(m[1]);
      if (parsed && parsed.incident) target = { incident: parsed.incident };
      else if (parsed && parsed.create) target = parsed.create;
    }
    var old = /^#agencies\/crisis=([^&]+)(.*)$/.exec(hash);
    if (!target && old) {
      var params = {};
      (old[2] || "").replace(/[&?]([a-z_]+)=([^&]*)/g, function (w, k, v) { params[k] = decodeURIComponent(v); });
      target = old[1] === "new" ? { template: params.template, district: params.district } : { incident: decodeURIComponent(old[1]) };
    }
    if (!target) return false;
    // Старая оболочка сбросит неизвестный адрес на карту — открываем раздел после неё; новая уже открыла раздел.
    setTimeout(function () {
      var shell = root.BirgeShell;
      if (shell && shell.section === "agencies" && mounted) return;
      openCrisis(target);
    }, 0);
    return true;
  }

  root.BirgeAgencies = { mount: mount, openCrisis: openCrisis, version: "r15-2" };

  function register() {
    var shell = root.BirgeShell;
    if (!shell || typeof shell.registerScreen !== "function") return false;
    // Оболочка раунда 15 (R01, IA_ROUND15) сама знает разделы agencies и crisis (SCREENS → window.BirgeAgencies) и их
    // подписи из словаря R11 — своя регистрация перебила бы название пункта меню. Признак такой оболочки — alertSlot.
    if (typeof shell.alertSlot === "function") return true;
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
