/*
 * Birge · «Вопросы и встречи» (R13, раунд 15). Схема — R11 IA_ROUND15 §5.3.
 * Вкладки «Встречи · Вопросы». Вкладка «Вопросы» — прежний «Вопрос акиму» (window.BirgeAsk, web/civic/qa/qa.js) внутри.
 *
 *   <link rel="stylesheet" href="/civic/meetings/meetings.css">
 *   <script src="/civic/meetings/meetings.js"></script>
 *   BirgeMeetings.mount(element, { role: "resident" | "akimat", api, path, navigate, openTarget, close, titleTag })
 *     → { setLang, setPath, destroy }
 *
 * Адреса раздела (IA §7.3): #meetings — встречи, #meetings/<m-id> — встреча, #meetings/<m-id>/<o-id|q-id> — поручение
 * или вопрос в ней (ссылка из ленты уведомлений R06), #meetings/questions — вкладка «Вопросы».
 *
 * Данные (ui/civic_meetings/service.py):
 *   GET  /meetings?district=&device_id=        список; GET /meetings/{id}?device_id= — карточка
 *   POST /meetings/{id}/register {going}         «Приду» (одно устройство — один раз; видно только число)
 *   POST /meetings/{id}/question {text, lang}    вопрос к встрече — на проверку (как «Вопрос акиму»)
 *   POST /questions/{id}/vote                    голос за вопрос (общий маршрут «Вопроса акиму»)
 *   сотрудник: POST /meetings · /meetings/{id}/order · /meetings/{id}/result; проверка вопросов — /questions/{id}/publish|reject
 *
 * Правила (IA §5.3, VISUAL_BRIEF): ведущий — «аким района», без имени; ни имён жителей, ни фото людей, ни комментариев;
 * одна главная кнопка: житель до встречи — «Приду», акимат во встрече — «Добавить поручение»; статус = иконка + слово;
 * у синтетики — «Пример»; все состояния (загрузка не раньше 150 мс, пусто с подсказкой, ошибка с «Повторить»).
 */
(function (root) {
  "use strict";

  const doc = root.document;
  const DISTRICTS = ["almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"];
  const SERVICES = ["road", "traffic", "street_cleaning", "transport", "lighting", "landscaping", "greenery", "waste",
    "utilities", "heating", "water", "power", "gas", "housing", "ecology", "emergency", "police", "animals", "parking", "akimat"];
  const DEVICE_KEY = "birge.device";            // как у мастера жалобы R09 и «Вопроса акиму»
  const DISTRICT_KEY = "birge.meetings.district";
  const QUESTION_MIN = 10, QUESTION_MAX = 300;
  const ASTANA_MS = 5 * 3600 * 1000;            // Астана — UTC+5 круглый год
  const KK_LETTERS = /[әғқңөұүһіӘҒҚҢӨҰҮҺІ]/;
  const scriptBase = ((doc.currentScript && doc.currentScript.src) || "").replace(/[^/]*$/, "");
  const ICONS = scriptBase + "../ui-kit/icons.svg";
  const SEARCH_INDEX = scriptBase + "../map/search_index.json";

  // Ключи, которых пока нет в словаре R11 (список для R11 — research/round-15-results/R13/INTEGRATION.txt §4).
  // Словарь главнее: есть ключ в BirgeI18n — берём его.
  const KEYS = {
    ru: {
      "meet.title": "Вопросы и встречи",
      "meet.tab.meetings": "Встречи",
      "meet.tab.questions": "Вопросы",
      "meet.tabs_label": "Встречи или вопросы",
      "meet.next": "Ближайшая встреча",
      "meet.host": "Ведёт аким района",
      "meet.in_days": { one: "через {n} день", few: "через {n} дня", many: "через {n} дней" },
      "meet.today": "сегодня",
      "meet.tomorrow": "завтра",
      "meet.phase.live": "Идёт сейчас",
      "meet.phase.held": "Прошла",
      "meet.phase.cancelled": "Отменена",
      "meet.on_map": "На карте",
      "meet.going": "Приду",
      "meet.going_done": "Вы придёте",
      "meet.not_going": "Не смогу прийти",
      "meet.going_count": { one: "{n} житель отметил «Приду»", few: "{n} жителя отметили «Приду»", many: "{n} жителей отметили «Приду»" },
      "meet.going_hint": "Отметка анонимная: видно только число.",
      "meet.questions": "Вопросы к встрече",
      "meet.questions_hint": "Аким ответит на самые поддержанные вопросы на встрече.",
      "meet.ask": "Задать вопрос к встрече",
      "meet.ask_label": "Ваш вопрос",
      "meet.ask_send": "Отправить вопрос",
      "meet.ask_privacy": "Не пишите имя, телефон и ИИН — вопрос увидят все.",
      "meet.ask_sent_title": "Вопрос отправлен",
      "meet.ask_sent": "Его опубликуют после проверки — тогда соседи смогут его поддержать.",
      "meet.questions_empty": "Вопросов пока нет. Задайте первый — его увидят соседи.",
      "meet.voting_closed": "Голосование закрыто — встреча уже началась.",
      "meet.support": "Поддержать",
      "meet.supported": "Вы поддержали",
      "meet.votes": { one: "{n} голос", few: "{n} голоса", many: "{n} голосов" },
      "meet.past": "Прошедшие встречи",
      "meet.upcoming": "Скоро",
      "meet.orders": "Поручения",
      "meet.orders_progress": "Выполнено {done} из {total}",
      "meet.orders_empty": "Поручений пока нет.",
      "meet.orders_soon": "Поручения появятся после встречи — со службой, сроком и статусом.",
      "meet.result": "Итоги встречи",
      "meet.result_lang_ru": "Итоги опубликованы на русском языке",
      "meet.result_lang_kk": "Итоги опубликованы на казахском языке",
      "meet.answered": "Ответы на встрече",
      "meet.answer_sign": "Аким района · {date}",
      "meet.due": "до {date}",
      "meet.overdue": "просрочено",
      "meet.status.todo": "Не начато",
      "meet.status.in_progress": "В работе",
      "meet.status.done": "Выполнено",
      "meet.link.complaint": "Обращение",
      "meet.link.work": "Работа",
      "meet.link.project": "Проект",
      "meet.linked.complaint": "Связано с обращением жителей",
      "meet.linked.work": "Связано с работой службы",
      "meet.linked.project": "Связано с проектом акимата",
      "meet.back": "Все встречи",
      "meet.empty_title": "Ближайших встреч пока нет",
      "meet.empty_text": "Когда акимат назначит встречу, она появится здесь. А пока можно задать вопрос акиму.",
      "meet.empty_action": "Задать вопрос акиму",
      "meet.district_all": "Все районы",
      "meet.district_label": "Район",
      "meet.error.closed": "Встреча уже началась — вопросы и отметки закрыты.",
      "meet.error.too_many": "С этого устройства к встрече уже есть 3 вопроса.",
      "meet.error.too_many_pending": "С этого устройства уже есть вопросы на проверке. Дождитесь, пока их проверят.",
      "meet.error.short": "Напишите вопрос подробнее — хотя бы 10 символов",
      "meet.error.long": "Не больше 300 символов",
      "meet.error.action": "Не получилось. Попробуйте ещё раз",
      "meet.not_found": "Встреча не найдена — возможно, её отменили.",
      "meet.staff.new": "Новая встреча",
      "meet.staff.list_empty_title": "Встреч пока нет",
      "meet.staff.list_empty_text": "Назначьте встречу — жители увидят дату и место и смогут задать вопросы заранее.",
      "meet.staff.add_order": "Добавить поручение",
      "meet.staff.order_text_ru": "Поручение на русском",
      "meet.staff.order_text_kk": "Поручение на казахском (по желанию)",
      "meet.staff.service": "Служба",
      "meet.staff.due": "Срок",
      "meet.staff.link": "Связь",
      "meet.staff.link_none": "Без связи",
      "meet.staff.link_pick": "Обращения района",
      "meet.staff.link_pick_none": "— выберите обращение —",
      "meet.staff.link_pick_empty": "Открытых обращений в районе нет — укажите номер записи",
      "meet.staff.link_pick_project": "Проекты и объекты района",
      "meet.staff.link_pick_work": "Работы района",
      "meet.staff.link_pick_any": "— выберите из списка —",
      "meet.staff.link_pick_list_empty": "В районе нет записей — укажите номер записи",
      "meet.staff.pick_object": "объект",
      "meet.staff.reporters": { one: "{n} житель", few: "{n} жителя", many: "{n} жителей" },
      "meet.staff.link_id": "Номер записи",
      "meet.staff.link_edit": "Связать",
      "meet.staff.link_save": "Сохранить связь",
      "meet.staff.save_order": "Сохранить поручение",
      "meet.staff.status_label": "Статус поручения",
      "meet.staff.result_ru": "Итог на русском",
      "meet.staff.result_kk": "Итог на казахском",
      "meet.staff.result_hint": "Коротко: сколько пришло, о чём говорили, сколько поручений. Увидят все.",
      "meet.staff.result_save": "Опубликовать итог",
      "meet.staff.result_edit": "Изменить итог",
      "meet.staff.result_after": "Итог можно написать, когда встреча начнётся.",
      "meet.staff.result_none": "Итог ещё не опубликован.",
      "meet.staff.result_empty": "Напишите итог хотя бы на одном языке — не короче 10 символов",
      "meet.staff.pending": { one: "{n} вопрос на проверке", few: "{n} вопроса на проверке", many: "{n} вопросов на проверке" },
      "meet.staff.publish": "Опубликовать",
      "meet.staff.reject": "Отклонить",
      "meet.staff.reject_reason": "Причина",
      "meet.staff.district": "Район",
      "meet.staff.title_ru": "Название на русском",
      "meet.staff.title_kk": "Название на казахском",
      "meet.staff.date": "Дата",
      "meet.staff.time": "Начало (время Астаны)",
      "meet.staff.duration": "Длительность",
      "meet.staff.minutes": "{n} мин",
      "meet.staff.place": "Место",
      "meet.staff.place_hint": "Двор, сквер или остановка — из карты; можно написать своё, например «Школа № 1, актовый зал».",
      "meet.staff.create": "Назначить встречу",
      "meet.staff.created": "Встреча назначена",
      "meet.staff.order_saved": "Поручение сохранено",
      "meet.staff.status_saved": "Статус обновлён",
      "meet.staff.link_saved": "Связь сохранена",
      "meet.staff.result_saved": "Итог опубликован",
      "meet.staff.published": "Вопрос опубликован",
      "meet.staff.rejected": "Вопрос отклонён",
      "meet.staff.login": "Чтобы назначать встречи и вести поручения, войдите как сотрудник акимата",
      "meet.staff.login_btn": "Войти",
      "meet.staff.registered": "Придут: {n}",
      "meet.staff.registered_past": "Отметили «Приду»: {n}",
      "meet.staff.questions_count": "Вопросов: {n}",
      "meet.staff.default_title": "Встреча акима района {district} с жителями",
      "meet.staff.pii": "Похоже на личные данные: {what}",
      "meet.staff.rude": "Есть грубые слова",
      "meet.staff.field_needed": "Заполните поле",
    },
    kk: {
      "meet.title": "Сұрақтар мен кездесулер",
      "meet.tab.meetings": "Кездесулер",
      "meet.tab.questions": "Сұрақтар",
      "meet.tabs_label": "Кездесулер немесе сұрақтар",
      "meet.next": "Жақын кездесу",
      "meet.host": "Аудан әкімі өткізеді",
      "meet.in_days": "{n} күннен кейін",
      "meet.today": "бүгін",
      "meet.tomorrow": "ертең",
      "meet.phase.live": "Қазір өтіп жатыр",
      "meet.phase.held": "Өтті",
      "meet.phase.cancelled": "Болдырылмады",
      "meet.on_map": "Картада",
      "meet.going": "Барамын",
      "meet.going_done": "Сіз барасыз",
      "meet.not_going": "Бара алмаймын",
      "meet.going_count": "{n} тұрғын «Барамын» деп белгіледі",
      "meet.going_hint": "Белгі жасырын: тек саны көрінеді.",
      "meet.questions": "Кездесуге қойылған сұрақтар",
      "meet.questions_hint": "Әкім кездесуде ең көп қолдау тапқан сұрақтарға жауап береді.",
      "meet.ask": "Кездесуге сұрақ қою",
      "meet.ask_label": "Сұрағыңыз",
      "meet.ask_send": "Сұрақты жіберу",
      "meet.ask_privacy": "Аты-жөніңізді, телефон мен ЖСН жазбаңыз — сұрақты бәрі көреді.",
      "meet.ask_sent_title": "Сұрақ жіберілді",
      "meet.ask_sent": "Ол тексерілгеннен кейін жарияланады — сонда көршілер оны қолдай алады.",
      "meet.questions_empty": "Әзірге сұрақ жоқ. Бірінші болып сұраңыз — оны көршілер көреді.",
      "meet.voting_closed": "Дауыс беру жабылды — кездесу басталып кетті.",
      "meet.support": "Қолдау",
      "meet.supported": "Сіз қолдадыңыз",
      "meet.votes": "{n} дауыс",
      "meet.past": "Өткен кездесулер",
      "meet.upcoming": "Жақында",
      "meet.orders": "Тапсырмалар",
      "meet.orders_progress": "{total} тапсырманың {done} орындалды",
      "meet.orders_empty": "Әзірге тапсырма жоқ.",
      "meet.orders_soon": "Тапсырмалар кездесуден кейін шығады — қызметі, мерзімі және мәртебесімен.",
      "meet.result": "Кездесу қорытындысы",
      "meet.result_lang_ru": "Қорытынды орыс тілінде жарияланған",
      "meet.result_lang_kk": "Қорытынды қазақ тілінде жарияланған",
      "meet.answered": "Кездесудегі жауаптар",
      "meet.answer_sign": "Аудан әкімі · {date}",
      "meet.due": "мерзімі: {date}",
      "meet.overdue": "мерзімі өтті",
      "meet.status.todo": "Басталмады",
      "meet.status.in_progress": "Орындалуда",
      "meet.status.done": "Орындалды",
      "meet.link.complaint": "Өтініш",
      "meet.link.work": "Жұмыс",
      "meet.link.project": "Жоба",
      "meet.linked.complaint": "Тұрғындар өтінішімен байланысты",
      "meet.linked.work": "Қызмет жұмысымен байланысты",
      "meet.linked.project": "Әкімдік жобасымен байланысты",
      "meet.back": "Барлық кездесулер",
      "meet.empty_title": "Жақын арада кездесу жоқ",
      "meet.empty_text": "Әкімдік кездесу белгілегенде, ол осында шығады. Әзірге әкімге сұрақ қоюға болады.",
      "meet.empty_action": "Әкімге сұрақ қою",
      "meet.district_all": "Барлық аудандар",
      "meet.district_label": "Аудан",
      "meet.error.closed": "Кездесу басталып кетті — сұрақтар мен белгілер жабық.",
      "meet.error.too_many": "Бұл құрылғыдан кездесуге 3 сұрақ қойылған.",
      "meet.error.too_many_pending": "Бұл құрылғыдан жіберілген сұрақтар әлі тексеруде. Тексерілгенін күтіңіз.",
      "meet.error.short": "Сұрақты толығырақ жазыңыз — кемінде 10 таңба",
      "meet.error.long": "300 таңбадан аспасын",
      "meet.error.action": "Орындалмады. Қайталап көріңіз",
      "meet.not_found": "Кездесу табылмады — мүмкін, ол болдырылмаған шығар.",
      "meet.staff.new": "Жаңа кездесу",
      "meet.staff.list_empty_title": "Әзірге кездесу жоқ",
      "meet.staff.list_empty_text": "Кездесу белгілеңіз — тұрғындар күні мен орнын көріп, сұрақтарды алдын ала қоя алады.",
      "meet.staff.add_order": "Тапсырма қосу",
      "meet.staff.order_text_ru": "Тапсырма орыс тілінде",
      "meet.staff.order_text_kk": "Тапсырма қазақ тілінде (қаласаңыз)",
      "meet.staff.service": "Қызмет",
      "meet.staff.due": "Мерзімі",
      "meet.staff.link": "Байланыс",
      "meet.staff.link_none": "Байланыссыз",
      "meet.staff.link_pick": "Ауданның өтініштері",
      "meet.staff.link_pick_none": "— өтінішті таңдаңыз —",
      "meet.staff.link_pick_empty": "Ауданда ашық өтініш жоқ — жазба нөмірін көрсетіңіз",
      "meet.staff.link_pick_project": "Ауданның жобалары мен нысандары",
      "meet.staff.link_pick_work": "Ауданның жұмыстары",
      "meet.staff.link_pick_any": "— тізімнен таңдаңыз —",
      "meet.staff.link_pick_list_empty": "Ауданда жазба жоқ — жазба нөмірін көрсетіңіз",
      "meet.staff.pick_object": "нысан",
      "meet.staff.reporters": "{n} тұрғын",
      "meet.staff.link_id": "Жазба нөмірі",
      "meet.staff.link_edit": "Байланыстыру",
      "meet.staff.link_save": "Байланысты сақтау",
      "meet.staff.save_order": "Тапсырманы сақтау",
      "meet.staff.status_label": "Тапсырма мәртебесі",
      "meet.staff.result_ru": "Қорытынды орыс тілінде",
      "meet.staff.result_kk": "Қорытынды қазақ тілінде",
      "meet.staff.result_hint": "Қысқаша: қанша адам келді, не талқыланды, қанша тапсырма берілді. Бәрі көреді.",
      "meet.staff.result_save": "Қорытындыны жариялау",
      "meet.staff.result_edit": "Қорытындыны өзгерту",
      "meet.staff.result_after": "Қорытындыны кездесу басталғанда жазуға болады.",
      "meet.staff.result_none": "Қорытынды әлі жарияланбаған.",
      "meet.staff.result_empty": "Қорытындыны кемінде бір тілде жазыңыз — 10 таңбадан қысқа болмасын",
      "meet.staff.pending": "Тексеруде: {n} сұрақ",
      "meet.staff.publish": "Жариялау",
      "meet.staff.reject": "Қабылдамау",
      "meet.staff.reject_reason": "Себебі",
      "meet.staff.district": "Аудан",
      "meet.staff.title_ru": "Атауы орыс тілінде",
      "meet.staff.title_kk": "Атауы қазақ тілінде",
      "meet.staff.date": "Күні",
      "meet.staff.time": "Басталуы (Астана уақыты)",
      "meet.staff.duration": "Ұзақтығы",
      "meet.staff.minutes": "{n} мин",
      "meet.staff.place": "Өтетін орны",
      "meet.staff.place_hint": "Аула, сквер немесе аялдама — картадан; өзіңіз де жаза аласыз, мысалы «№ 1 мектеп, мәжіліс залы».",
      "meet.staff.create": "Кездесуді белгілеу",
      "meet.staff.created": "Кездесу белгіленді",
      "meet.staff.order_saved": "Тапсырма сақталды",
      "meet.staff.status_saved": "Мәртебе жаңартылды",
      "meet.staff.link_saved": "Байланыс сақталды",
      "meet.staff.result_saved": "Қорытынды жарияланды",
      "meet.staff.published": "Сұрақ жарияланды",
      "meet.staff.rejected": "Сұрақ қабылданбады",
      "meet.staff.login": "Кездесу белгілеу және тапсырмаларды жүргізу үшін әкімдік қызметкері ретінде кіріңіз",
      "meet.staff.login_btn": "Кіру",
      "meet.staff.registered": "Келетіндер: {n}",
      "meet.staff.registered_past": "«Барамын» деп белгілегендер: {n}",
      "meet.staff.questions_count": "Сұрақтар: {n}",
      "meet.staff.default_title": "{district} ауданы әкімінің тұрғындармен кездесуі",
      "meet.staff.pii": "Жеке деректерге ұқсайды: {what}",
      "meet.staff.rude": "Дөрекі сөздер бар",
      "meet.staff.field_needed": "Өрісті толтырыңыз",
    },
  };
  // Общие ключи словаря R11 — запас на случай страницы без словаря.
  const COMMON = {
    ru: {
      "common.tag.demo": "Пример", "common.tag.demo_hint": "Пример для показа, не настоящие данные",
      "common.action.cancel": "Отменить", "common.action.retry": "Повторить", "common.action.close": "Закрыть",
      "common.action.open": "Открыть", "common.state.loading": "Загружаем…",
      "common.state.network_title": "Нет связи с сервером", "common.state.network_text": "Проверьте интернет и повторите.",
      "common.error.too_many": "Слишком много действий подряд. Повторите через минуту.",
      "district.almaty": "Алматы", "district.baikonur": "Байконур", "district.esil": "Есиль", "district.nura": "Нура",
      "district.saraishyk": "Сарайшык", "district.saryarka": "Сарыарка",
      "ask.staff.reason.personal_data": "Личные данные", "ask.staff.reason.rude": "Грубые слова",
      "ask.staff.reason.not_question": "Это жалоба — её отправляют через «Сообщить о проблеме»",
      "ask.staff.reason.duplicate": "Такой вопрос уже есть", "ask.staff.reason.other": "Другое",
      "ask.staff.pii.phone": "телефон", "ask.staff.pii.iin": "ИИН", "ask.staff.pii.email": "почта", "ask.staff.pii.card": "номер карты",
    },
    kk: {
      "common.tag.demo": "Үлгі", "common.tag.demo_hint": "Көрсетуге арналған үлгі, нақты дерек емес",
      "common.action.cancel": "Болдырмау", "common.action.retry": "Қайталау", "common.action.close": "Жабу",
      "common.action.open": "Ашу", "common.state.loading": "Жүктеліп жатыр…",
      "common.state.network_title": "Сервермен байланыс жоқ", "common.state.network_text": "Интернетті тексеріп, қайталап көріңіз.",
      "common.error.too_many": "Қатарынан тым көп әрекет жасалды. Бір минуттан кейін қайталаңыз.",
      "district.almaty": "Алматы", "district.baikonur": "Байқоңыр", "district.esil": "Есіл", "district.nura": "Нұра",
      "district.saraishyk": "Сарайшық", "district.saryarka": "Сарыарқа",
      "ask.staff.reason.personal_data": "Жеке деректер", "ask.staff.reason.rude": "Дөрекі сөздер",
      "ask.staff.reason.not_question": "Бұл — шағым, оны «Мәселе туралы хабарлау» арқылы жібереді",
      "ask.staff.reason.duplicate": "Мұндай сұрақ бұрыннан бар", "ask.staff.reason.other": "Басқа себеп",
      "ask.staff.pii.phone": "телефон", "ask.staff.pii.iin": "ЖСН", "ask.staff.pii.email": "электрондық пошта", "ask.staff.pii.card": "карта нөмірі",
    },
  };
  const WEEKDAYS = {  // 0 — воскресенье, как Date.getUTCDay()
    ru: ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"],
    kk: ["жексенбі", "дүйсенбі", "сейсенбі", "сәрсенбі", "бейсенбі", "жұма", "сенбі"],
  };
  const WEEKDAYS_SHORT = { ru: ["вс", "пн", "вт", "ср", "чт", "пт", "сб"], kk: ["жс", "дс", "сс", "ср", "бс", "жм", "сб"] };
  const MONTHS = {
    ru: ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
    kk: ["қаң", "ақп", "нау", "сәу", "мам", "мау", "шіл", "там", "қыр", "қаз", "қар", "жел"],
  };
  const REASONS = ["personal_data", "rude", "not_question", "duplicate", "other"];

  // ---------------------------------------------------------------- тексты
  const I = () => root.BirgeI18n || null;
  const lang = () => (I() && typeof I().getLang === "function" && I().getLang() === "kk" ? "kk" : "ru");
  const num = (n) => (I() && typeof I().formatNumber === "function" ? I().formatNumber(n) : String(n));
  function plural(l, n) {
    if (I() && typeof I().plural === "function") return I().plural(l, n);
    if (l === "kk") return "other";
    const m10 = n % 10, m100 = n % 100;
    if (m10 === 1 && m100 !== 11) return "one";
    if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "few";
    return "many";
  }
  function tr(key, params) {
    const i18n = I();
    if (i18n && typeof i18n.has === "function" && (i18n.has(key) || i18n.has(key, "ru"))) return i18n.t(key, params);
    const l = lang();
    let v = KEYS[l][key] != null ? KEYS[l][key] : COMMON[l][key] != null ? COMMON[l][key] : KEYS.ru[key];
    if (v == null) return i18n ? i18n.t(key, params) : key;
    if (typeof v === "object") {
      const n = params && params.n != null ? Number(params.n) : 0;
      v = v[plural(l, n)] || v.other || v.many;
    }
    return String(v).replace(/\{(\w+)\}/g, (w, name) => {
      if (!params || params[name] == null) return w;
      return typeof params[name] === "number" ? num(params[name]) : String(params[name]);
    });
  }
  // Подписи из записи: *_ru / *_kk по языку экрана, второй язык — запасной.
  const pick = (obj, base) => (obj ? (lang() === "kk" ? obj[base + "_kk"] || obj[base + "_ru"] : obj[base + "_ru"] || obj[base + "_kk"]) || "" : "");
  const textLang = (text) => (KK_LETTERS.test(text || "") ? "kk" : "ru");

  // ---------------------------------------------------------------- время Астаны
  function astana(iso) {
    const ms = Date.parse(iso);
    if (!isFinite(ms)) return null;
    const d = new Date(ms + ASTANA_MS);
    return { y: d.getUTCFullYear(), m: d.getUTCMonth(), d: d.getUTCDate(), wd: d.getUTCDay(), hh: d.getUTCHours(), mm: d.getUTCMinutes() };
  }
  const pad2 = (v) => (v < 10 ? "0" : "") + v;
  const time = (iso) => { const p = astana(iso); return p ? pad2(p.hh) + ":" + pad2(p.mm) : "—"; };
  function dayDiff(iso) {
    const p = astana(iso), now = astana(new Date().toISOString());
    if (!p || !now) return null;
    return Math.round((Date.UTC(p.y, p.m, p.d) - Date.UTC(now.y, now.m, now.d)) / 86400000);
  }
  function dateLong(iso) {  // «суббота, 18 окт» / «сенбі, 18 қаз»
    const p = astana(iso);
    if (!p) return "—";
    const l = lang();
    return WEEKDAYS[l][p.wd] + ", " + p.d + " " + MONTHS[l][p.m];
  }
  function dateShort(isoOrDate) {  // «23 окт» (дата срока без времени не сдвигаем)
    if (/^\d{4}-\d{2}-\d{2}$/.test(isoOrDate || "")) {
      const [y, m, d] = isoOrDate.split("-").map(Number);
      const thisYear = astana(new Date().toISOString()).y;
      return d + " " + MONTHS[lang()][m - 1] + (y !== thisYear ? " " + y : "");
    }
    const p = astana(isoOrDate);
    return p ? p.d + " " + MONTHS[lang()][p.m] : "—";
  }
  function whenWords(iso) {  // «сегодня», «завтра», «через 3 дня»
    const n = dayDiff(iso);
    if (n == null || n < 0) return "";
    if (n === 0) return tr("meet.today");
    if (n === 1) return tr("meet.tomorrow");
    return tr("meet.in_days", { n });
  }
  // Сегодня + days по Астане -> «ГГГГ-ММ-ДД» (значение по умолчанию для полей даты).
  function astanaDate(days, fromIso) {
    const base = fromIso ? Date.parse(fromIso) : Date.now();
    const d = new Date(base + ASTANA_MS + (days || 0) * 86400000);
    return d.getUTCFullYear() + "-" + pad2(d.getUTCMonth() + 1) + "-" + pad2(d.getUTCDate());
  }

  // ---------------------------------------------------------------- разметка
  function h(tag, attrs, children) {
    const el = doc.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "text") el.textContent = v;
      else if (k === "class") el.className = v;
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children || []) {
      if (c != null && c !== false) el.appendChild(typeof c === "string" ? doc.createTextNode(c) : c);
    }
    return el;
  }
  // Значок из спрайта ui-kit (одна толщина, IA §7.6); сердце — из эталона, если в спрайте его нет.
  const INLINE = { heart: "M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z" };
  function icon(name, cls) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = doc.createElementNS(NS, "svg");
    svg.setAttribute("class", cls || "ic");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    if (INLINE[name] && !(root.BirgeUI && root.BirgeUI.SPRITE)) {
      svg.setAttribute("viewBox", "0 0 24 24");
      const path = doc.createElementNS(NS, "path");
      path.setAttribute("d", INLINE[name]);
      svg.appendChild(path);
      return svg;
    }
    const use = doc.createElementNS(NS, "use");
    use.setAttribute("href", ((root.BirgeUI && root.BirgeUI.SPRITE) || ICONS) + "#" + (name.startsWith("st-") ? name : "i-" + name));
    svg.appendChild(use);
    return svg;
  }
  // Статус поручения — статус-иконка ui-kit + слово (VISUAL_BRIEF правило 4: цвет никогда не один).
  // Как в ui-kit R11 (.bk-orders): «выполнено» — кольцо с галочкой (сообщил акимат); заливка «проверено жителями» — только
  // для проверки жителями. Просроченное — красное кольцо.
  const ORDER_SHAPE = { todo: "st-ring", in_progress: "st-half", done: "st-ring-check" };
  const ORDER_TONE = { todo: "todo", in_progress: "in_progress", done: "fixed" };
  function statusIcon(order) {
    const svg = icon(ORDER_SHAPE[order.status] || "st-ring", "bk-st-ic mt-st-ic");
    svg.setAttribute("data-status", order.overdue ? "new" : ORDER_TONE[order.status] || "todo");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    return svg;
  }
  function demoTag() {
    return h("span", { class: "bk-tag bk-tag--demo mt-demo", title: tr("common.tag.demo_hint"), text: tr("common.tag.demo") });
  }
  function storage(key, value) {
    try {
      if (value === undefined) return root.localStorage.getItem(key);
      root.localStorage.setItem(key, value);
    } catch (e) {
      return null;  // приватный режим — работаем без памяти
    }
    return null;
  }
  function randomHex(bytes) {
    const arr = new Uint8Array(bytes);
    if (root.crypto && root.crypto.getRandomValues) root.crypto.getRandomValues(arr);
    else for (let i = 0; i < bytes; i++) arr[i] = Math.floor(Math.random() * 256);
    return Array.prototype.map.call(arr, (b) => ("0" + b.toString(16)).slice(-2)).join("");
  }
  let memoryDevice = null;  // хранилище недоступно — один id на страницу
  function deviceId() {
    const id = storage(DEVICE_KEY);
    if (id && /^[A-Za-z0-9._:-]{8,128}$/.test(id)) return id;
    if (!memoryDevice) {
      memoryDevice = "d-" + randomHex(12);
      storage(DEVICE_KEY, memoryDevice);
    }
    return memoryDevice;
  }
  function toast(text, type) {
    if (root.BirgeUI && typeof root.BirgeUI.toast === "function") root.BirgeUI.toast(text, type ? { type } : {});
  }
  const reducedMotion = () => !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches);

  // Места для формы «Новая встреча»: дворы, скверы и остановки из поиска карты R12 (OSM). Грузим один раз, по требованию.
  let placesPromise = null;
  function loadPlaces() {
    if (!placesPromise) {
      placesPromise = root.fetch(SEARCH_INDEX, { credentials: "same-origin" })
        .then((r) => (r.ok ? r.json() : { objects: [] }))
        .then((data) => (data.objects || []).filter((o) => o && o.id && o.ru && Array.isArray(o.c)))
        .catch(() => []);
    }
    return placesPromise;
  }

  // «#meetings/m-1/o-2» -> «m-1/o-2»; другой раздел — пустой путь.
  function hashPath() {
    const m = /^#meetings\/(.{1,120})$/.exec((root.location && root.location.hash) || "");
    return m ? decodeURIComponent(m[1]) : "";
  }

  function mount(rootEl, options) {
    const opts = Object.assign({ apiBase: "/api/civic/v2", titleTag: "h2", role: "resident" }, options || {});
    const state = {
      role: opts.role === "akimat" ? "akimat" : "resident",
      tab: "meetings",            // meetings | questions
      view: "list",               // list | detail | new (сотрудник: новая встреча)
      meetingId: null, anchor: null,
      list: null, listStatus: "loading",
      card: null, cardStatus: "idle",
      district: storage(DISTRICT_KEY) || "",
      ask: { open: false, text: "", error: null, busy: false, sent: false },
      order: null,                // сотрудник: черновик нового поручения
      linkFor: null, link: { kind: "complaint", id: "", busy: false, error: null },
      result: null,               // сотрудник: черновик итога {ru, kk, error, busy}
      draft: null,                // сотрудник: черновик новой встречи
      rejectFor: null, reject: { reason: null, busy: false },
      busy: {}, alive: true, lang: lang(), listReq: 0, cardReq: 0, skeletonTimer: null, showSkeleton: false, shown: "",
      bump: false, places: [], complaints: {}, linkLists: {},
    };
    let askHandle = null;
    const box = h("section", { class: "mt", "data-role": state.role });
    rootEl.appendChild(box);
    const staff = () => state.role === "akimat";

    // ---------------------------------------------------------------- API
    function call(method, path, body) {
      if (opts.api && typeof opts.api.v2 === "function") return opts.api.v2(method, path, body);
      const headers = { Accept: "application/json" };
      if (body !== undefined) headers["Content-Type"] = "application/json";
      const shell = root.CivicShell;
      const csrf = shell && typeof shell.csrfToken === "function" ? shell.csrfToken() : null;
      if (csrf && method !== "GET") headers["X-CSRF-Token"] = csrf;
      return root.fetch(opts.apiBase + path, {
        method, headers, credentials: "same-origin", body: body !== undefined ? JSON.stringify(body) : undefined,
      }).then((r) => r.text().then((text) => {
        let data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
        if (!r.ok) throw { status: r.status, error: (data && data.error) || "error", message: data && data.message, field: data && data.field };
        return data;
      }), () => { throw { status: 0, error: "network" }; });
    }
    const errorText = (err, fallbackKey) => {
      err = err || {};
      if (!err.status) return tr("common.state.network_title");
      if (err.status === 429) return tr("common.error.too_many");
      if (err.error === "closed" || err.error === "started") return tr("meet.error.closed");
      if (err.error === "too_many_meeting") return tr("meet.error.too_many");
      if (err.error === "too_many") return tr("meet.error.too_many_pending");
      return tr(fallbackKey || "meet.error.action");
    };

    // ---------------------------------------------------------------- адрес раздела (IA §7.3)
    function parsePath(path) {
      const parts = String(path || "").split("/").filter(Boolean);
      if (parts[0] === "questions") return { tab: "questions" };
      if (parts[0] && /^m-[A-Za-z0-9-]{1,40}$/.test(parts[0])) {
        return { tab: "meetings", meetingId: parts[0], anchor: /^[oq]-[A-Za-z0-9-]{1,60}$/.test(parts[1] || "") ? parts[1] : null };
      }
      return { tab: "meetings" };
    }
    function pathOf() {
      if (state.tab === "questions") return "questions";
      if (state.view === "detail" && state.meetingId) return state.meetingId;
      return "";
    }
    function navigate() {
      if (typeof opts.navigate === "function") {
        try { opts.navigate(pathOf()); } catch (e) { /* адрес — удобство, не условие работы */ }
      }
    }
    function applyPath(path, initial) {
      const p = parsePath(path);
      state.tab = p.tab;
      if (p.meetingId) {
        state.view = "detail";
        state.anchor = p.anchor;
        if (state.meetingId !== p.meetingId || initial) { state.meetingId = p.meetingId; state.card = null; }
      } else if (p.tab === "meetings" && state.view === "detail") {
        state.view = "list";
        state.meetingId = null;
        state.card = null;
      }
    }

    // ---------------------------------------------------------------- загрузка
    // Скелетон — только если ответ не пришёл за 150 мс (правило Linear 4): быстрый ответ не мигает.
    function armSkeleton() {
      clearTimeout(state.skeletonTimer);
      state.showSkeleton = false;
      state.skeletonTimer = setTimeout(() => {
        if (!state.alive) return;
        state.showSkeleton = true;
        render();
      }, 150);
    }
    function loadList(quiet) {
      const req = ++state.listReq;  // свой счётчик: ответ списка не отменяет карточку и наоборот
      if (!quiet || !state.list) {
        state.listStatus = "loading";
        armSkeleton();
        render();
      }
      const q = "?device_id=" + encodeURIComponent(deviceId()) + (state.district ? "&district=" + state.district : "");
      return call("GET", "/meetings" + q).then((data) => {
        if (!state.alive || req !== state.listReq) return;
        clearTimeout(state.skeletonTimer);
        state.list = data || { items: [] };
        state.listStatus = "ready";
        // Житель: карточку ближайшей встречи (вопросы с голосами) берём сразу — это главное на экране.
        const next = !staff() && state.view === "list" ? nextMeeting() : null;
        if (next) return loadCard(next.id, true);
        render();
        return null;
      }, (err) => {
        if (!state.alive || req !== state.listReq) return;
        clearTimeout(state.skeletonTimer);
        state.listStatus = "error";
        state.listError = err;
        render();
      });
    }
    function loadCard(id, quiet) {
      const req = ++state.cardReq;
      if (!quiet || !state.card || state.card.id !== id) {
        state.cardStatus = "loading";
        if (!quiet) { armSkeleton(); render(); }
      }
      return call("GET", "/meetings/" + encodeURIComponent(id) + "?device_id=" + encodeURIComponent(deviceId())).then((data) => {
        if (!state.alive || req !== state.cardReq) return;
        clearTimeout(state.skeletonTimer);
        state.card = data && data.meeting;
        state.cardStaff = !!(data && data.staff);
        state.services = (data && data.services) || state.services;
        state.cardStatus = state.card ? "ready" : "error";
        render();
        // Открыли встречу, а фокус потерялся вместе с прежней разметкой — ставим его на заголовок встречи.
        if (!quiet && (doc.activeElement === doc.body || !doc.activeElement)) focusTitle();
        scrollToAnchor();
      }, (err) => {
        if (!state.alive || req !== state.cardReq) return;
        clearTimeout(state.skeletonTimer);
        state.cardStatus = err && err.status === 404 ? "missing" : "error";
        state.cardError = err;
        render();
      });
    }
    function load() {
      if (state.tab === "questions") { render(); return; }
      if (state.view === "detail" && state.meetingId) {
        if (!state.list) loadList(true);
        loadCard(state.meetingId);
        return;
      }
      loadList();
    }
    const items = () => (state.list && state.list.items) || [];
    const nextMeeting = () => {
      const id = state.list && state.list.next_id;
      return id ? items().find((m) => m.id === id) : null;
    };
    function scrollToAnchor() {
      if (!state.anchor) return;
      const target = box.querySelector('[data-anchor="' + state.anchor + '"]');
      state.anchor = null;
      if (!target) return;
      target.classList.add("mt-flash");
      target.scrollIntoView({ block: "center", behavior: reducedMotion() ? "auto" : "smooth" });
      setTimeout(() => target.classList.remove("mt-flash"), 1600);
    }

    // ---------------------------------------------------------------- переходы
    function openMeeting(id) {
      state.view = "detail";
      state.meetingId = id;
      state.card = null;
      state.order = null;
      state.result = null;
      state.linkFor = null;
      state.rejectFor = null;
      state.ask = { open: false, text: "", error: null, busy: false, sent: false };
      navigate();
      loadCard(id);
      focusTitle();
    }
    function backToList() {
      state.view = "list";
      state.meetingId = null;
      state.card = null;
      state.order = null;
      state.result = null;
      state.draft = null;
      navigate();
      if (!state.list) loadList(); else if (!staff()) { const n = nextMeeting(); if (n) loadCard(n.id, true); else render(); } else render();
      focusTitle();
    }
    function setTab(tab) {
      if (tab === state.tab) return;
      state.tab = tab;
      if (tab === "meetings" && !state.list) loadList(); else render();
      navigate();
    }
    function focusTitle() {
      requestAnimationFrame(() => {
        const t = box.querySelector(".mt-focus-target");
        if (t && state.alive) t.focus({ preventScroll: false });
      });
    }

    // ---------------------------------------------------------------- действия жителя
    function register(meeting) {
      if (state.busy.register) return;
      const going = !meeting.my_registration;
      state.busy.register = true;
      // Сразу показываем результат (правило Linear 4), откатываем при ошибке.
      const before = { mine: meeting.my_registration, n: meeting.registered };
      meeting.my_registration = going;
      meeting.registered = Math.max(0, meeting.registered + (going ? 1 : -1));
      state.bump = going;
      render();
      call("POST", "/meetings/" + meeting.id + "/register", { going, device_id: deviceId() }).then((res) => {
        state.busy.register = false;
        if (!state.alive) return;
        meeting.registered = res.registered;
        meeting.my_registration = res.my_registration;
        syncSummary(meeting);
        render();
        const btn = box.querySelector(".mt-going");
        if (btn) btn.focus();
      }, (err) => {
        state.busy.register = false;
        meeting.my_registration = before.mine;
        meeting.registered = before.n;
        state.bump = false;
        render();
        toast(errorText(err), "error");
      });
    }
    // Число «Приду» в списке совпадает с карточкой.
    function syncSummary(meeting) {
      const row = items().find((m) => m.id === meeting.id);
      if (row) { row.registered = meeting.registered; row.my_registration = meeting.my_registration; }
    }
    function vote(meeting, q) {
      if (q.my_vote || state.busy["v" + q.id] || !meeting.voting_open) return;
      state.busy["v" + q.id] = true;
      q.my_vote = true;
      q.votes += 1;
      render();
      call("POST", "/questions/" + q.id + "/vote", { device_id: deviceId() }).then((res) => {
        delete state.busy["v" + q.id];
        if (!state.alive) return;
        q.votes = res.votes;
        render();
      }, (err) => {
        delete state.busy["v" + q.id];
        q.my_vote = false;
        q.votes = Math.max(0, q.votes - 1);
        if (err && err.error === "closed") meeting.voting_open = false;
        render();
        toast(errorText(err), "error");
      });
    }
    function sendQuestion(meeting) {
      const a = state.ask;
      const text = a.text.trim();
      if (text.length < QUESTION_MIN) { a.error = tr("meet.error.short"); render(); focusField(".mt-ask textarea"); return; }
      if (text.length > QUESTION_MAX) { a.error = tr("meet.error.long"); render(); focusField(".mt-ask textarea"); return; }
      a.busy = true;
      a.error = null;
      a.requestId = a.requestId || "rq-" + randomHex(8);
      render();
      call("POST", "/meetings/" + meeting.id + "/question", { text, lang: textLang(text) === "kk" ? "kk" : lang(),
        device_id: deviceId(), request_id: a.requestId }).then(() => {
        state.ask = { open: false, text: "", error: null, busy: false, sent: true };
        render();
        focusField(".mt-sent");
      }, (err) => {
        a.busy = false;
        a.error = errorText(err);
        render();
        focusField(".mt-ask textarea");
      });
    }
    function focusField(selector) {
      requestAnimationFrame(() => { const el = box.querySelector(selector); if (el) el.focus(); });
    }

    // ---------------------------------------------------------------- действия сотрудника
    function staffFail(err) {
      if (err && (err.status === 401 || err.status === 403)) { state.needLogin = true; render(); }
      toast(errorText(err), "error");
    }
    function saveOrder(meeting) {
      const d = state.order;
      d.error = null;
      d.field = null;
      if (!d.text_ru.trim()) { d.error = tr("meet.staff.field_needed"); d.field = "text_ru"; render(); focusField('[name="text_ru"]'); return; }
      const body = { text_ru: d.text_ru, service: d.service, due: d.due };
      if (d.text_kk.trim()) body.text_kk = d.text_kk;
      if (d.linkId.trim()) body.link = { kind: d.linkKind, id: d.linkId.trim() };
      d.busy = true;
      render();
      call("POST", "/meetings/" + meeting.id + "/order", body).then(() => {
        state.order = null;
        toast(tr("meet.staff.order_saved"), "ok");
        loadCard(meeting.id, true);
        loadList(true);
      }, (err) => {
        d.busy = false;
        d.field = err && err.field;
        d.error = err && err.status === 422 && err.message ? err.message : errorText(err);
        if (err && (err.status === 401 || err.status === 403)) state.needLogin = true;
        render();
      });
    }
    function setOrderStatus(meeting, order, status) {
      if (order.status === status || state.busy["o" + order.id]) return;
      state.busy["o" + order.id] = true;
      const before = order.status;
      order.status = status;
      order.overdue = status !== "done" && order.due < astanaDate(0);
      render();
      call("POST", "/meetings/" + meeting.id + "/order", { order_id: order.id, status }).then((res) => {
        delete state.busy["o" + order.id];
        Object.assign(order, res.order);
        render();
        toast(tr("meet.staff.status_saved"), "ok");
        loadList(true);
      }, (err) => {
        delete state.busy["o" + order.id];
        order.status = before;
        render();
        staffFail(err);
      });
    }
    function saveLink(meeting, order) {
      const l = state.link;
      const id = l.id.trim();
      l.busy = true;
      l.error = null;
      render();
      call("POST", "/meetings/" + meeting.id + "/order", { order_id: order.id, link: id ? { kind: l.kind, id } : null }).then((res) => {
        Object.assign(order, res.order);
        state.linkFor = null;
        state.link = { kind: "complaint", id: "", busy: false, error: null };
        render();
        toast(tr("meet.staff.link_saved"), "ok");
      }, (err) => {
        l.busy = false;
        l.error = err && err.status === 422 && err.message ? err.message : errorText(err);
        render();
      });
    }
    function saveResult(meeting) {
      const r = state.result;
      if (r.ru.trim().length < 10 && r.kk.trim().length < 10) { r.error = tr("meet.staff.result_empty"); render(); return; }
      r.busy = true;
      r.error = null;
      render();
      const body = {};
      if (r.ru.trim()) body.result_ru = r.ru;
      if (r.kk.trim()) body.result_kk = r.kk;
      call("POST", "/meetings/" + meeting.id + "/result", body).then((res) => {
        state.result = null;
        state.card = res.meeting;
        render();
        toast(tr("meet.staff.result_saved"), "ok");
        loadList(true);
      }, (err) => {
        r.busy = false;
        r.error = err && err.status === 422 && err.message ? err.message : errorText(err);
        render();
      });
    }
    function moderate(meeting, q, action) {
      if (state.busy["q" + q.id]) return;
      if (action === "reject" && !state.reject.reason) { state.reject.error = true; render(); return; }
      state.busy["q" + q.id] = true;
      render();
      const body = action === "reject" ? { reason: state.reject.reason } : {};
      call("POST", "/questions/" + q.id + "/" + action, body).then(() => {
        delete state.busy["q" + q.id];
        state.rejectFor = null;
        state.reject = { reason: null, busy: false };
        toast(tr(action === "publish" ? "meet.staff.published" : "meet.staff.rejected"), "ok");
        loadCard(meeting.id, true);
      }, (err) => {
        delete state.busy["q" + q.id];
        render();
        if (err && (err.status === 404 || err.status === 409)) loadCard(meeting.id, true);
        staffFail(err);
      });
    }
    function createMeeting() {
      const d = state.draft;
      d.error = null;
      d.field = null;
      for (const field of ["title_ru", "date", "time", "place"]) {
        if (!String(d[field] || "").trim()) { d.error = tr("meet.staff.field_needed"); d.field = field; render(); focusField('[name="' + field + '"]'); return; }
      }
      // Место из списка карты — цель {kind, id} и точка; своё название — только подпись (без кнопки «На карте»).
      const found = state.places.find((p) => p.ru === d.place.trim() || p.kk === d.place.trim());
      const place = found
        ? { kind: found.id.startsWith("yard-") ? "area" : "object", id: found.id, label_ru: found.ru, label_kk: found.kk || null }
        : { label_ru: d.place.trim() };
      const body = { district: d.district, title_ru: d.title_ru, at: d.date + "T" + d.time + ":00+05:00",
        duration_min: Number(d.duration) || 90, place };
      if (d.title_kk.trim()) body.title_kk = d.title_kk;
      if (found) body.point = found.c;
      d.busy = true;
      render();
      call("POST", "/meetings", body).then((res) => {
        state.draft = null;
        toast(tr("meet.staff.created"), "ok");
        loadList(true);
        openMeeting(res.meeting.id);
      }, (err) => {
        d.busy = false;
        d.field = err && err.field === "at" ? "date" : err && err.field;
        d.error = err && err.status === 422 && err.message ? err.message : errorText(err);
        if (err && (err.status === 401 || err.status === 403)) state.needLogin = true;
        render();
      });
    }
    // Открытые обращения района для связи поручения (R09 GET /complaints — публичный вид, без текстов жителей).
    // Грузим один раз на район; сначала те, о которых сообщило больше жителей.
    function loadComplaints(district) {
      if (!district || state.complaints[district]) return;
      state.complaints[district] = { loading: true, items: [] };
      call("GET", "/complaints?days=60&status=new,accepted,in_progress").then((data) => {
        const items = ((data && (data.items || (data.data && data.data.items))) || [])
          .filter((c) => c && c.id && c.district === district && !c.duplicate_of)
          .sort((a, b) => (b.reporters || 0) - (a.reporters || 0) || String(b.created_at).localeCompare(String(a.created_at)))
          .slice(0, 30);
        state.complaints[district] = { loading: false, items };
        if (state.alive) render();
      }, () => {
        state.complaints[district] = { loading: false, items: [], failed: true };
        if (state.alive) render();
      });
    }
    function complaintLabel(c) {
      const place = c.target ? pick(c.target, "label") : "";
      const category = I() && typeof I().cat === "function" && c.category ? I().cat(c.category) : c.category || "";
      return [place || c.id, category, tr("meet.staff.reporters", { n: c.reporters || 1 })].filter(Boolean).join(" · ");
    }
    // Выбор обращения (только для связи «Обращение»): список района + запасной ввод номера рядом.
    function complaintPicker(district, value, onPick, name) {
      loadComplaints(district);
      const box = state.complaints[district] || { loading: true, items: [] };
      if (box.loading) return null;
      if (!box.items.length) return h("p", { class: "bk-field__hint mt-pick-empty", text: tr("meet.staff.link_pick_empty") });
      const el = h("select", { id: "mt-f-" + name, name, class: "mt-select", "data-focus": "f-" + name, onchange: (e) => onPick(e.target.value) },
        [h("option", { value: "", text: tr("meet.staff.link_pick_none") })].concat(box.items.map((c) => h("option", { value: c.id, text: complaintLabel(c) }))));
      el.value = box.items.some((c) => c.id === value) ? value : "";
      return field(tr("meet.staff.link_pick"), el);
    }
    // Проекты и работы района для связи (R11 R13-1: сотрудник выбирает по названию, а не вводит номер).
    // Проект — проекты района (GET /proposals) и объекты с этапами (GET /objects) R06; работа — «Работы и отключения»
    // (GET /works, сотрудник). Нет маршрута или ошибка — остаётся ввод номера.
    const itemsOf = (data) => ((data && (data.items || (data.data && data.data.items))) || []).filter((x) => x && x.id);
    const titleOf = (x) => (lang() === "kk" ? x.title_kk || x.title_ru || x.title : x.title_ru || x.title || x.title_kk) || "";
    function loadLinkList(kind, district) {
      const key = kind + ":" + district;
      if (!district || state.linkLists[key]) return;
      state.linkLists[key] = { loading: true, items: [] };
      const q = "?district=" + encodeURIComponent(district);
      const asks = kind === "project"
        ? [call("GET", "/proposals" + q).then((d) => itemsOf(d).map((x) => ({ id: x.id, x, tag: "" })), () => []),
          call("GET", "/objects" + q).then((d) => itemsOf(d).map((x) => ({ id: x.id, x, tag: tr("meet.staff.pick_object") })), () => [])]
        : [call("GET", "/works" + q).then((d) => itemsOf(d).map((x) => ({ id: x.id, x, tag: "" })), () => [])];
      Promise.all(asks).then((parts) => {
        const seen = {};
        const items = [].concat(...parts).filter((it) => titleOf(it.x) && !seen[it.id] && (seen[it.id] = true)).slice(0, 40);
        state.linkLists[key] = { loading: false, items };
        if (state.alive) render();
      });
    }
    function linkPicker(kind, district, value, onPick, name) {
      if (kind === "complaint") return complaintPicker(district, value, onPick, name);
      loadLinkList(kind, district);
      const box = state.linkLists[kind + ":" + district] || { loading: true, items: [] };
      if (box.loading) return null;
      if (!box.items.length) return h("p", { class: "bk-field__hint mt-pick-empty", text: tr("meet.staff.link_pick_list_empty") });
      const el = h("select", { id: "mt-f-" + name, name, class: "mt-select", "data-focus": "f-" + name, onchange: (e) => onPick(e.target.value) },
        [h("option", { value: "", text: tr("meet.staff.link_pick_any") })].concat(box.items.map((it) =>
          h("option", { value: it.id, text: [titleOf(it.x), it.tag].filter(Boolean).join(" · ") }))));
      el.value = box.items.some((it) => it.id === value) ? value : "";
      return field(tr(kind === "project" ? "meet.staff.link_pick_project" : "meet.staff.link_pick_work"), el);
    }

    function newDraft() {
      const district = state.district || "nura";
      state.draft = { district, title_ru: defaultTitle(district, "ru"), title_kk: defaultTitle(district, "kk"),
        date: astanaDate(7), time: "18:30", duration: "90", place: "", busy: false, error: null, field: null, touched: false };
      state.view = "new";
      render();
      focusTitle();
      loadPlaces().then((places) => { state.places = places; if (state.alive && state.view === "new") render(); });
    }
    function defaultTitle(district, l) {
      const names = COMMON[l];
      const name = (I() && I().has && I().has("district." + district) && lang() === l) ? tr("district." + district) : names["district." + district];
      return KEYS[l]["meet.staff.default_title"].replace("{district}", name || district);
    }

    // ---------------------------------------------------------------- отрисовка
    function render() {
      if (!state.alive) return;
      const hadFocus = !!doc.activeElement && box.contains(doc.activeElement);
      const active = hadFocus ? doc.activeElement.getAttribute("data-focus") : null;
      const scroller = box.querySelector(".mt-body");
      const scrollTop = scroller ? scroller.scrollTop : 0;
      state.lang = lang();
      box.setAttribute("data-role", state.role);
      box.setAttribute("data-view", state.tab === "questions" ? "questions" : state.view);
      const keepAsk = state.tab === "questions" && askHandle && box.querySelector(".mt-askhost");
      if (keepAsk) {  // вкладка «Вопросы» уже смонтирована — не пересоздаём «Вопрос акиму» (его поля и фокус)
        renderHead(true);
        return;
      }
      if (askHandle) { try { askHandle.destroy(); } catch (e) { /* модуль вкладки не ломает экран */ } askHandle = null; }
      box.replaceChildren();
      renderHead(false);
      const body = h("div", { class: "mt-body", role: "tabpanel", id: "mt-panel", "aria-labelledby": "mt-tab-" + state.tab });
      box.appendChild(body);
      if (state.tab === "questions") body.appendChild(renderQuestionsTab());
      else if (state.view === "new") body.appendChild(renderNewMeeting());
      else if (state.view === "detail") body.appendChild(renderDetail());
      else body.appendChild(staff() ? renderStaffList() : renderResidentList());
      // Тот же вид — прокрутка остаётся (голос, «Приду», статус); новый вид или встреча — с начала.
      const shown = state.tab + "|" + state.view + "|" + (state.meetingId || "");
      body.scrollTop = shown === state.shown ? scrollTop : 0;
      state.shown = shown;
      // Фокус был в разделе и пропал вместе с прежней разметкой — на тот же элемент, а нет его (другой вид: встреча →
      // список) — на заголовок вида. Иначе Esc и Tab после «тихой» перезагрузки шли бы от body.
      if (hadFocus && (!doc.activeElement || doc.activeElement === doc.body)) {
        const again = active && box.querySelector('[data-focus="' + active + '"]');
        const target = again || box.querySelector(".mt-focus-target");
        if (target) target.focus({ preventScroll: !!again });
      }
      state.bump = false;
    }
    // Шапка листа (как «Вопрос акиму» и «Проекты и идеи» эталона): заголовок 19/600, круглая «×», сегменты.
    function renderHead(update) {
      let head = box.querySelector(".mt__head");
      if (update && head) {
        head.querySelector(".mt__title").textContent = tr("meet.title");
        for (const b of head.querySelectorAll("[role=tab]")) {
          b.querySelector(".mt-seg__label").textContent = tr("meet.tab." + b.value);
          b.setAttribute("aria-selected", String(b.value === state.tab));
          b.tabIndex = b.value === state.tab ? 0 : -1;
        }
        return;
      }
      head = h("div", { class: "mt__head" }, [
        h("div", { class: "mt__ttl" }, [
          h(opts.titleTag || "h2", { class: "mt__title" + (state.view === "list" ? " mt-focus-target" : ""), tabindex: "-1", "data-focus": "title",
            "data-focus": "title", text: tr("meet.title") }),
        ]),
        typeof opts.close === "function" ? h("button", { type: "button", class: "mt__close bk-x", "aria-label": tr("common.action.close"),
          "data-focus": "close", onclick: () => opts.close() }, [icon("close")]) : null,
      ]);
      const tabs = h("div", { class: "mt-seg bk-seg", role: "tablist", "aria-label": tr("meet.tabs_label") },
        ["meetings", "questions"].map((id) => h("button", { type: "button", role: "tab", id: "mt-tab-" + id, value: id,
          "aria-controls": "mt-panel", "aria-selected": String(state.tab === id), tabindex: state.tab === id ? "0" : "-1",
          "data-focus": "tab-" + id }, [h("span", { class: "mt-seg__label", text: tr("meet.tab." + id) })])));
      if (root.BirgeUI && typeof root.BirgeUI.tabs === "function") root.BirgeUI.tabs(tabs, (v) => setTab(v));
      else tabs.addEventListener("click", (e) => { const b = e.target.closest('[role="tab"]'); if (b) setTab(b.value); });
      box.appendChild(head);
      box.appendChild(tabs);
    }

    // Пустое состояние и ошибка (поправка владельца П1): маленький монохромный значок набора R11 (48 px), короткий текст,
    // одна кнопка. Не иллюстрация: BirgeUI.state рисует icon размером 48, когда передан opts.icon.
    const STATE_ICON = { question: "message", list: "calendar", search: "search" };
    function stateBox(kind, title, text, action, illustration) {
      const el = h("div", { class: "mt-state" });
      if (root.BirgeUI && typeof root.BirgeUI.state === "function") {
        const icon = kind === "error" ? "wifi-off" : STATE_ICON[illustration] || "info";
        root.BirgeUI.state(el, kind, { title, text, action, icon });
        return el;
      }
      el.appendChild(h("p", { class: kind === "error" ? "bk-error__title" : "bk-empty__title", text: title || "" }));
      if (text) el.appendChild(h("p", { class: "bk-meta", text }));
      if (action) el.appendChild(h("button", { type: "button", class: "bk-btn bk-btn--primary", onclick: action.onClick, text: action.label }));
      return el;
    }
    function errorBox(err, retry) {
      const net = !err || !err.status;
      return stateBox("error", net ? tr("common.state.network_title") : tr("meet.error.action"),
        net ? tr("common.state.network_text") : "", { label: tr("common.action.retry"), onClick: retry });
    }
    function skeleton() {
      if (!state.showSkeleton) return h("div", { class: "mt-wait", "aria-busy": "true" }, [h("p", { class: "bk-sr-only", role: "status", text: tr("common.state.loading") })]);
      const card = () => h("div", { class: "mt-skel bk-card", "aria-hidden": "true" }, [
        h("span", { class: "bk-skel mt-skel__tile" }),
        h("span", { class: "mt-skel__lines" }, [h("span", { class: "bk-skel bk-skel--line mt-skel--short" }),
          h("span", { class: "bk-skel bk-skel--title" }), h("span", { class: "bk-skel bk-skel--line" })])]);
      return h("div", { class: "mt-wait", "aria-busy": "true" }, [h("p", { class: "bk-sr-only", role: "status", text: tr("common.state.loading") }),
        card(), card()]);
    }

    // Плитка даты: день недели, число, месяц (как лист календаря) — узнаётся с первого взгляда.
    // Дата — блок ui-kit R11 .bk-meet__date (число и месяц); день недели — в строке времени рядом.
    function dateTile(iso, small) {
      const p = astana(iso);
      if (!p) return null;
      return h("div", { class: "bk-meet__date mt-date" + (small ? " mt-date--sm" : ""), "aria-hidden": "true" }, [
        h("b", { text: String(p.d) }),
        h("span", { text: MONTHS[lang()][p.m] }),
      ]);
    }
    function whenSpan(m) {
      return h("span", null, [icon("clock"), h("span", { text: dateLong(m.at) + ", " + time(m.at) + "–" + time(m.ends_at) })]);
    }
    function placeSpan(m) {
      if (!m.place) return null;
      const label = pick(m.place, "label");
      const canMap = m.place.kind && m.place.id && typeof opts.openTarget === "function";
      return h("span", { class: "mt-place" }, [icon("pin"), h("span", { class: "mt-place__label", text: label }),
        canMap ? h("button", { type: "button", class: "mt-link", "data-focus": "map-" + m.id,
          onclick: () => opts.openTarget(m.place.kind, m.place.id) }, [tr("meet.on_map")]) : null]);
    }
    function phaseTag(m) {
      if (m.phase === "upcoming") return null;
      return h("span", { class: "bk-tag mt-phase mt-phase--" + m.phase, text: tr("meet.phase." + m.phase) });
    }
    function districtName(id) {
      return id ? tr("district." + id) : "";
    }

    // ---------------------------------------------------------------- житель: список
    function renderResidentList() {
      const wrap = h("div", { class: "mt-list-view" });
      if (state.listStatus === "loading") { wrap.appendChild(skeleton()); return wrap; }
      if (state.listStatus === "error") { wrap.appendChild(errorBox(state.listError, () => loadList())); return wrap; }
      wrap.appendChild(districtFilter());
      const next = nextMeeting();
      if (next) {
        const card = state.card && state.card.id === next.id ? state.card : null;
        wrap.appendChild(renderHero(card || next, !!card));
        if (card) wrap.appendChild(renderQuestions(card));
      } else {
        wrap.appendChild(stateBox("empty", tr("meet.empty_title"), tr("meet.empty_text"),
          { label: tr("meet.empty_action"), onClick: () => setTab("questions") }, "question"));
      }
      // Остальные предстоящие встречи (в других районах или позже) — строками, чтобы ни одна не потерялась.
      const more = items().filter((m) => (m.phase === "upcoming" || m.phase === "live") && (!next || m.id !== next.id));
      if (more.length) {
        wrap.appendChild(h("section", { class: "mt-sec", "aria-labelledby": "mt-more" }, [
          h("h3", { class: "mt-sec__title", id: "mt-more", text: tr("meet.upcoming") }),
          h("ul", { class: "mt-rows" }, more.map((m) => h("li", null, [meetingRow(m)]))),
        ]));
      }
      const past = items().filter((m) => m.phase !== "upcoming" && m.phase !== "live");
      if (past.length) {
        wrap.appendChild(h("section", { class: "mt-sec", "aria-labelledby": "mt-past" }, [
          h("h3", { class: "mt-sec__title", id: "mt-past", text: tr("meet.past") }),
          h("ul", { class: "mt-rows" }, past.map((m) => h("li", null, [meetingRow(m)]))),
        ]));
      }
      return wrap;
    }
    function districtFilter() {
      const select = h("select", { class: "mt-select", "aria-label": tr("meet.district_label"), "data-focus": "district",
        onchange: (e) => { state.district = e.target.value; storage(DISTRICT_KEY, state.district); state.card = null; loadList(); } },
      [h("option", { value: "", text: tr("meet.district_all") })].concat(DISTRICTS.map((d) => h("option", { value: d, text: districtName(d) }))));
      select.value = state.district || "";
      return h("div", { class: "mt-filter" }, [h("label", { class: "mt-filter__label", text: tr("meet.district_label") }), select]);
    }
    // Ближайшая встреча крупно (IA §5.3): дата, место «На карте», «Приду · 54» — главная кнопка жителя.
    // Ближайшая встреча крупно (IA §5.3) — карточка ui-kit R11 .bk-meet: дата, название, время, место «На карте», ведущий;
    // «Приду · 54» — главная кнопка жителя (число — .bk-btn__count).
    function renderHero(m, full) {
      const going = !!m.my_registration;
      const open = m.phase === "upcoming";
      const count = h("span", { class: "bk-btn__count mt-count" + (state.bump ? " mt-count--bump" : ""), text: num(m.registered || 0) });
      const button = h("button", { type: "button", class: "bk-btn mt-going" + (going ? " is-on" : " bk-btn--primary"),
        "aria-pressed": String(going), "data-focus": "going", disabled: !open || state.busy.register ? true : null,
        "aria-describedby": "mt-going-hint", onclick: () => register(m) },
      [going ? icon("check") : null, h("span", { text: tr(going ? "meet.going_done" : "meet.going") }), count]);
      button.setAttribute("aria-label", tr(going ? "meet.going_done" : "meet.going") + ". " + tr("meet.going_count", { n: m.registered || 0 }));
      const article = h("article", { class: "bk-meet mt-hero", "data-state": open ? "upcoming" : "past",
        "aria-labelledby": "mt-hero-title", "data-anchor": m.id }, [
        dateTile(m.at),
        h("div", { class: "bk-meet__main" }, [
          h("p", { class: "mt-eyebrow" }, [h("span", { text: tr("meet.next") }), whenWords(m.at) ? h("span", { class: "mt-eyebrow__when", text: " · " + whenWords(m.at) }) : null,
            m.demo ? demoTag() : null]),
          h("h3", { class: "bk-meet__title mt-hero__title", id: "mt-hero-title", text: pick(m, "title") }),
          h("p", { class: "bk-meet__meta mt-meta" }, [whenSpan(m), placeSpan(m), h("span", null, [icon("user"), h("span", { text: tr("meet.host") })])]),
        ]),
        h("div", { class: "bk-meet__cta" }, [
          button,
          going && open ? h("button", { type: "button", class: "mt-link mt-notgoing", "data-focus": "notgoing", onclick: () => register(m),
            text: tr("meet.not_going") }) : null,
        ]),
        h("p", { class: "mt-hint", id: "mt-going-hint", text: tr("meet.going_hint") }),
      ]);
      if (!full) article.classList.add("mt-hero--loading");
      return article;
    }
    function votesText(q) {
      return tr("meet.votes", { n: q.votes || 0 });
    }
    function voteCapsule(m, q) {
      const label = q.my_vote ? tr("meet.supported") : tr("meet.support");
      const btn = h("button", { type: "button", class: "bk-vote mt-vote", "aria-pressed": String(!!q.my_vote), "data-focus": "vote-" + q.id,
        disabled: !m.voting_open && !q.my_vote ? true : null, title: label,
        "aria-label": label + " · " + votesText(q), onclick: () => vote(m, q) }, [icon("heart"), h("span", { text: num(q.votes || 0) })]);
      return btn;
    }
    function renderQuestions(m) {
      const sec = h("section", { class: "mt-sec", "aria-labelledby": "mt-q-title" }, [
        h("div", { class: "mt-sec__hd" }, [h("h3", { class: "mt-sec__title", id: "mt-q-title", text: tr("meet.questions") }),
          m.questions.length ? h("span", { class: "mt-sec__count", text: num(m.questions.length) }) : null]),
        h("p", { class: "mt-sec__hint", text: m.voting_open ? tr("meet.questions_hint") : tr("meet.voting_closed") }),
      ]);
      if (m.questions.length) {
        sec.appendChild(h("ol", { class: "mt-qlist" }, m.questions.map((q) => h("li", { class: "mt-q", "data-anchor": q.id }, [
          h("p", { class: "mt-q__text", lang: q.lang || textLang(q.text), text: q.text }),
          h("div", { class: "mt-q__foot" }, [q.demo ? demoTag() : h("span"), voteCapsule(m, q)]),
          q.answer ? answerQuote(q) : null,
        ]))));
      } else if (m.voting_open) {
        sec.appendChild(h("p", { class: "mt-empty-line", text: tr("meet.questions_empty") }));
      }
      if (m.voting_open) sec.appendChild(askBlock(m));
      return sec;
    }
    function askBlock(m) {
      const a = state.ask;
      if (a.sent) {
        return h("div", { class: "mt-sent", tabindex: "-1", role: "status" }, [
          h("span", { class: "mt-sent__ic", "aria-hidden": "true" }, [icon("check")]),
          h("div", null, [h("p", { class: "mt-sent__title", text: tr("meet.ask_sent_title") }), h("p", { class: "mt-sent__text", text: tr("meet.ask_sent") })]),
        ]);
      }
      if (!a.open) {
        return h("button", { type: "button", class: "bk-btn mt-askbtn", "data-focus": "ask-open",
          onclick: () => { a.open = true; render(); focusField(".mt-ask textarea"); } }, [icon("plus"), tr("meet.ask")]);
      }
      const area = h("textarea", { name: "text", rows: "3", maxlength: String(QUESTION_MAX), "aria-describedby": "mt-ask-hint mt-ask-count",
        "aria-invalid": a.error ? "true" : null, "data-focus": "ask-text",
        oninput: (e) => { a.text = e.target.value; const c = box.querySelector("#mt-ask-count"); if (c) c.textContent = num(a.text.length) + " / " + num(QUESTION_MAX); } });
      area.value = a.text;
      return h("form", { class: "mt-ask bk-field" + (a.error ? " bk-field--error" : ""), novalidate: true,
        onsubmit: (e) => { e.preventDefault(); sendQuestion(m); } }, [
        h("label", { class: "bk-field__label", text: tr("meet.ask_label") }, []),
        area,
        h("div", { class: "mt-ask__row" }, [h("p", { class: "bk-field__hint", id: "mt-ask-hint", text: tr("meet.ask_privacy") }),
          h("span", { class: "mt-ask__count", id: "mt-ask-count", text: num(a.text.length) + " / " + num(QUESTION_MAX) })]),
        a.error ? h("p", { class: "bk-field__error", role: "alert", text: a.error }) : null,
        h("div", { class: "mt-actions" }, [
          h("button", { type: "submit", class: "bk-btn bk-btn--primary", disabled: a.busy ? true : null, "data-focus": "ask-send", text: tr("meet.ask_send") }),
          h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "ask-cancel",
            onclick: () => { state.ask = { open: false, text: "", error: null, busy: false, sent: false }; render(); }, text: tr("common.action.cancel") }),
        ]),
      ]);
    }
    function answerQuote(q) {
      const text = lang() === "kk" ? q.answer.kk || q.answer.ru : q.answer.ru || q.answer.kk;
      if (!text) return null;
      // Без .bk-quote: его обрезка в 2 строки прячет подпись «Аким района · дата»; ответы на встрече короткие.
      return h("blockquote", { class: "mt-answer" }, [h("p", { lang: textLang(text), text }),
        h("footer", { class: "mt-answer__sign", text: tr("meet.answer_sign", { date: dateShort(q.answer.answered_at) }) })]);
    }
    // Строка встречи в списке: плитка даты, название, район, поручения «выполнено 4 из 5» полосой.
    function meetingRow(m) {
      const oc = m.orders_count || {};
      const progress = oc.total ? Math.round((oc.done / oc.total) * 100) : 0;
      const meta = [districtName(m.district)];
      if (staff()) {
        meta.push(tr(m.phase === "upcoming" ? "meet.staff.registered" : "meet.staff.registered_past", { n: m.registered || 0 }));
        meta.push(tr("meet.staff.questions_count", { n: (m.questions_count && m.questions_count.published) || 0 }));
      }
      return h("button", { type: "button", class: "mt-row", "data-focus": "row-" + m.id, onclick: () => openMeeting(m.id) }, [
        dateTile(m.at, true),
        h("span", { class: "mt-row__main" }, [
          h("span", { class: "mt-row__title", text: pick(m, "title") }),
          h("span", { class: "mt-row__meta" }, [h("span", { text: meta.filter(Boolean).join(" · ") }), phaseTag(m), m.demo ? demoTag() : null]),
          oc.total ? h("span", { class: "mt-row__orders" }, [
            h("span", { class: "mt-bar", "aria-hidden": "true" }, [h("span", { class: "mt-bar__fill", style: "width:" + progress + "%" })]),
            h("span", { class: "mt-row__progress", text: tr("meet.orders_progress", { done: oc.done || 0, total: oc.total }) }),
            oc.overdue ? h("span", { class: "bk-tag bk-tag--danger", text: tr("meet.overdue") + " · " + num(oc.overdue) }) : null,
          ]) : null,
        ]),
        icon("chevron-right", "ic mt-row__chev"),
      ]);
    }

    // ---------------------------------------------------------------- встреча (житель и сотрудник)
    function renderDetail() {
      const wrap = h("div", { class: "mt-detail" });
      wrap.appendChild(h("button", { type: "button", class: "mt-back mt-link", "data-focus": "back", onclick: backToList },
        [icon("back"), tr("meet.back")]));
      if (state.cardStatus === "loading" || (!state.card && state.cardStatus !== "error" && state.cardStatus !== "missing")) {
        wrap.appendChild(skeleton());
        return wrap;
      }
      if (state.cardStatus === "missing") {
        wrap.appendChild(stateBox("empty", tr("meet.not_found"), "", { label: tr("meet.back"), onClick: backToList }, "search"));
        return wrap;
      }
      if (state.cardStatus === "error") { wrap.appendChild(errorBox(state.cardError, () => loadCard(state.meetingId))); return wrap; }
      const m = state.card;
      if (staff()) return renderStaffDetail(wrap, m);
      if (m.phase === "upcoming") {
        wrap.appendChild(renderHero(m, true));
        wrap.appendChild(renderQuestions(m));
        return wrap;
      }
      wrap.appendChild(detailHeader(m));
      if (m.result) wrap.appendChild(resultBlock(m));
      wrap.appendChild(ordersBlock(m, false));
      const answered = m.questions.filter((q) => q.answer);
      if (answered.length) {
        wrap.appendChild(h("section", { class: "mt-sec", "aria-labelledby": "mt-ans" }, [
          h("h3", { class: "mt-sec__title", id: "mt-ans", text: tr("meet.answered") }),
          h("ol", { class: "mt-qlist" }, answered.map((q) => h("li", { class: "mt-q", "data-anchor": q.id }, [
            h("p", { class: "mt-q__text", lang: q.lang || textLang(q.text), text: q.text }),
            h("div", { class: "mt-q__foot" }, [q.demo ? demoTag() : h("span"), h("span", { class: "mt-q__votes", text: votesText(q) })]),
            answerQuote(q),
          ]))),
        ]));
      }
      return wrap;
    }
    function detailHeader(m) {
      return h("header", { class: "bk-meet mt-dhead", "data-state": m.phase === "upcoming" ? "upcoming" : "past" }, [
        dateTile(m.at),
        h("div", { class: "bk-meet__main" }, [
          h("p", { class: "mt-eyebrow" }, [phaseTag(m), m.demo ? demoTag() : null]),
          h("h3", { class: "bk-meet__title mt-dhead__title mt-focus-target", tabindex: "-1", "data-focus": "dtitle", text: pick(m, "title") }),
          h("p", { class: "bk-meet__meta mt-meta" }, [whenSpan(m), placeSpan(m),
            h("span", null, [icon("user"), h("span", { text: tr("meet.host") + " · " + districtName(m.district) })])]),
        ]),
      ]);
    }
    function resultBlock(m) {
      const own = lang() === "kk" ? m.result.kk : m.result.ru;
      const text = own || m.result.ru || m.result.kk;
      const other = !own ? (m.result.ru ? "meet.result_lang_ru" : "meet.result_lang_kk") : null;
      return h("section", { class: "mt-sec mt-result", "aria-labelledby": "mt-res" }, [
        h("h3", { class: "mt-sec__title", id: "mt-res", text: tr("meet.result") }),
        h("p", { class: "mt-result__text", lang: textLang(text), text }),
        other ? h("p", { class: "mt-sec__hint", text: tr(other) }) : null,
      ]);
    }
    function ordersBlock(m, editable) {
      const oc = m.orders_count || { total: 0, done: 0 };
      const sec = h("section", { class: "mt-sec", "aria-labelledby": "mt-ord" }, [
        h("div", { class: "mt-sec__hd" }, [h("h3", { class: "mt-sec__title", id: "mt-ord", text: tr("meet.orders") }),
          oc.total ? h("span", { class: "mt-sec__count", text: tr("meet.orders_progress", { done: oc.done || 0, total: oc.total }) }) : null]),
      ]);
      if (oc.total) {
        const progress = Math.round(((oc.done || 0) / oc.total) * 100);
        sec.appendChild(h("span", { class: "mt-bar mt-bar--wide", role: "img", "aria-label": tr("meet.orders_progress", { done: oc.done || 0, total: oc.total }) },
          [h("span", { class: "mt-bar__fill", style: "width:" + progress + "%" })]));
      }
      if (!m.orders.length) {
        sec.appendChild(h("p", { class: "mt-empty-line", text: m.phase === "upcoming" ? tr("meet.orders_soon") : tr("meet.orders_empty") }));
        return sec;
      }
      sec.appendChild(h("ol", { class: "bk-orders mt-orders" }, m.orders.map((o) => orderRow(m, o, editable))));
      return sec;
    }
    function serviceName(o) {
      if (I() && I().has && I().has("service." + o.service)) return tr("service." + o.service);
      const names = o.service_name || (state.services || {})[o.service];
      return names ? (lang() === "kk" ? names.kk || names.ru : names.ru) : o.service;
    }
    // Строка поручения — ui-kit R11 .bk-order: статус-иконка · текст · срок справа (красный, если просрочен) · ниже
    // статус словом, служба (VISUAL_BRIEF правило 4: цвет никогда не один), связь, у акимата — смена статуса.
    function orderRow(m, o, editable) {
      const text = pick(o, "text");
      const meta = h("span", { class: "bk-order__meta mt-order__meta" }, [
        h("span", { class: "mt-order__st", text: tr("meet.status." + o.status) }),
        h("span", { class: "mt-dot", "aria-hidden": "true", text: "·" }),
        h("span", { text: serviceName(o) }),
        o.overdue ? h("span", { class: "bk-tag bk-tag--danger", text: tr("meet.overdue") }) : null,
        o.demo && !m.demo ? demoTag() : null,  // у демо-встречи «Пример» уже стоит в шапке — без повтора в каждой строке
      ]);
      return h("li", { class: "bk-order mt-order" + (o.overdue ? " is-overdue" : "") + (o.status === "done" ? " is-done" : ""), "data-anchor": o.id }, [
        statusIcon(o),
        h("span", { class: "bk-order__text mt-order__text", lang: textLang(text), text }),
        h("time", { class: "bk-order__due mt-order__due", datetime: o.due, "data-late": String(!!o.overdue), text: tr("meet.due", { date: dateShort(o.due) }) }),
        meta,
        o.link ? linkChip(o) : null,
        editable ? orderTools(m, o) : null,
      ]);
    }
    function linkChip(o) {
      // С чем связано поручение и где это: подпись цели обращения R09 и его статус, название проекта или работы R06.
      // Номер записи на экране не пишем (R11 R13-1) — акимату он в подсказке. Есть цель — «На карте».
      const l = o.link;
      const place = pick(l, "label");
      let label = place ? tr("meet.link." + l.kind) + ": " + place : tr("meet.linked." + l.kind);
      if (l.status && I() && I().has && I().has("status." + l.status)) label += " · " + tr("status." + l.status);
      const canMap = l.target && l.target.kind && l.target.id && typeof opts.openTarget === "function";
      return h("span", { class: "mt-linkline" }, [
        h("span", { class: "mt-linkchip", title: staff() ? tr("meet.staff.link_id") + ": " + l.id : null },
          [icon(l.kind === "complaint" ? "message" : l.kind === "work" ? "calendar" : "cube"), h("span", { text: label })]),
        canMap ? h("button", { type: "button", class: "mt-link", "data-focus": "lmap-" + o.id,
          onclick: () => opts.openTarget(l.target.kind, l.target.id) }, [tr("meet.on_map")]) : null,
      ]);
    }

    // ---------------------------------------------------------------- сотрудник
    function loginBanner() {
      const shell = root.CivicShell;
      const canLogin = shell && typeof shell.openEditor === "function";
      return h("div", { class: "mt-login bk-banner", role: "status" }, [
        h("p", { class: "bk-banner__title", text: tr("meet.staff.login") }),
        canLogin ? h("button", { type: "button", class: "bk-btn", "data-focus": "login", onclick: () => shell.openEditor(), text: tr("meet.staff.login_btn") }) : null,
      ]);
    }
    const signedIn = () => (state.list && state.list.staff) || state.cardStaff;
    function renderStaffList() {
      const wrap = h("div", { class: "mt-list-view" });
      if (state.listStatus === "loading") { wrap.appendChild(skeleton()); return wrap; }
      if (state.listStatus === "error") { wrap.appendChild(errorBox(state.listError, () => loadList())); return wrap; }
      if (!signedIn() || state.needLogin) wrap.appendChild(loginBanner());
      else wrap.appendChild(h("div", { class: "mt-lead" }, [h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-focus": "new",
        onclick: newDraft }, [icon("plus"), tr("meet.staff.new")])]));
      wrap.appendChild(districtFilter());
      if (!items().length) {
        wrap.appendChild(stateBox("empty", tr("meet.staff.list_empty_title"), tr("meet.staff.list_empty_text"), null, "list"));
        return wrap;
      }
      const upcoming = items().filter((m) => m.phase === "upcoming" || m.phase === "live");
      const past = items().filter((m) => m.phase !== "upcoming" && m.phase !== "live");
      if (upcoming.length) wrap.appendChild(h("section", { class: "mt-sec" }, [h("h3", { class: "mt-sec__title", text: tr("meet.upcoming") }),
        h("ul", { class: "mt-rows" }, upcoming.map((m) => h("li", null, [meetingRow(m)])))]));
      if (past.length) wrap.appendChild(h("section", { class: "mt-sec" }, [h("h3", { class: "mt-sec__title", text: tr("meet.past") }),
        h("ul", { class: "mt-rows" }, past.map((m) => h("li", null, [meetingRow(m)])))]));
      return wrap;
    }
    function renderStaffDetail(wrap, m) {
      wrap.appendChild(detailHeader(m));
      wrap.appendChild(h("p", { class: "mt-staffmeta" }, [
        h("span", { text: tr(m.phase === "upcoming" ? "meet.staff.registered" : "meet.staff.registered_past", { n: m.registered || 0 }) }),
        h("span", { class: "mt-dot", "aria-hidden": "true", text: "·" }),
        h("span", { text: tr("meet.staff.questions_count", { n: m.questions.length }) }),
      ]));
      if (!state.cardStaff || state.needLogin) {
        wrap.appendChild(loginBanner());
      } else if (m.phase !== "cancelled") {
        // Главная кнопка акимата во встрече (IA §5.3) — «Добавить поручение».
        if (!state.order) {
          wrap.appendChild(h("div", { class: "mt-lead" }, [h("button", { type: "button", class: "bk-btn bk-btn--primary", "data-focus": "add-order",
            onclick: () => {
              // Срок по умолчанию — через 2 недели от встречи, но не раньше чем через 2 недели от сегодня (давняя встреча).
              const from = Date.parse(m.at) > Date.now() ? m.at : new Date().toISOString();
              state.order = { text_ru: "", text_kk: "", service: "akimat", due: astanaDate(14, from), linkKind: "complaint", linkId: "", busy: false, error: null, field: null };
              render();
              focusField('[name="text_ru"]');
            } }, [icon("plus"), tr("meet.staff.add_order")])]));
        } else {
          wrap.appendChild(orderForm(m));
        }
      }
      wrap.appendChild(ordersBlock(m, !!state.cardStaff && !state.needLogin));
      if (state.cardStaff) wrap.appendChild(staffQuestions(m));
      wrap.appendChild(staffResult(m));
      return wrap;
    }
    function field(label, control, opts2) {
      const o = opts2 || {};
      return h("div", { class: "bk-field mt-field" + (o.error ? " bk-field--error" : "") }, [
        h("label", { class: "bk-field__label", for: control.id, text: label }), control,
        o.hint ? h("p", { class: "bk-field__hint", text: o.hint }) : null,
        o.error ? h("p", { class: "bk-field__error", role: "alert", text: o.error }) : null,
      ]);
    }
    function input(name, value, onInput, attrs) {
      const el = h(attrs && attrs.tag === "textarea" ? "textarea" : "input", Object.assign({ id: "mt-f-" + name, name, "data-focus": "f-" + name,
        oninput: (e) => onInput(e.target.value) }, attrs && attrs.tag ? Object.assign({}, attrs, { tag: null }) : attrs || {}));
      el.value = value == null ? "" : value;
      return el;
    }
    function select(name, value, options, onChange) {
      const el = h("select", { id: "mt-f-" + name, name, class: "mt-select", "data-focus": "f-" + name, onchange: (e) => onChange(e.target.value) },
        options.map(([v, label]) => h("option", { value: v, text: label })));
      el.value = value;
      return el;
    }
    function orderForm(m) {
      const d = state.order;
      const err = (f) => (d.field === f ? d.error : null);
      const services = SERVICES.map((id) => [id, serviceName({ service: id })]).sort((a, b) => a[1].localeCompare(b[1], lang()));
      return h("form", { class: "mt-form", novalidate: true, onsubmit: (e) => { e.preventDefault(); saveOrder(m); } }, [
        field(tr("meet.staff.order_text_ru"), input("text_ru", d.text_ru, (v) => { d.text_ru = v; }, { tag: "textarea", rows: "2", maxlength: "300" }), { error: err("text_ru") }),
        field(tr("meet.staff.order_text_kk"), input("text_kk", d.text_kk, (v) => { d.text_kk = v; }, { tag: "textarea", rows: "2", maxlength: "300", lang: "kk" }), { error: err("text_kk") }),
        h("div", { class: "mt-grid2" }, [
          field(tr("meet.staff.service"), select("service", d.service, services, (v) => { d.service = v; }), { error: err("service") }),
          field(tr("meet.staff.due"), input("due", d.due, (v) => { d.due = v; }, { type: "date" }), { error: err("due") }),
        ]),
        h("div", { class: "mt-grid2" }, [
          field(tr("meet.staff.link"), select("link_kind", d.linkKind, [["complaint", tr("meet.link.complaint")], ["work", tr("meet.link.work")],
            ["project", tr("meet.link.project")]], (v) => { d.linkKind = v; render(); })),
          field(tr("meet.staff.link_id"), input("link_id", d.linkId, (v) => { d.linkId = v; }, { maxlength: "96", autocomplete: "off", spellcheck: "false" }), { error: err("link") }),
        ]),
        linkPicker(d.linkKind, m.district, d.linkId, (v) => { d.linkId = v; render(); }, "link_pick"),
        d.error && !d.field ? h("p", { class: "bk-field__error", role: "alert", text: d.error }) : null,
        h("div", { class: "mt-actions" }, [
          h("button", { type: "submit", class: "bk-btn bk-btn--primary", disabled: d.busy ? true : null, "data-focus": "order-save", text: tr("meet.staff.save_order") }),
          h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "order-cancel", onclick: () => { state.order = null; render(); }, text: tr("common.action.cancel") }),
        ]),
      ]);
    }
    // Статус меняется прямо из строки (IA §5.3): выбор из трёх — иконка остаётся слева, слово — в списке.
    function orderTools(m, o) {
      const sel = h("select", { class: "mt-select mt-select--sm", "aria-label": tr("meet.staff.status_label"), "data-focus": "st-" + o.id,
        disabled: state.busy["o" + o.id] ? true : null, onchange: (e) => setOrderStatus(m, o, e.target.value) },
      ["todo", "in_progress", "done"].map((s) => h("option", { value: s, text: tr("meet.status." + s) })));
      sel.value = o.status;
      const tools = h("div", { class: "mt-order__tools" }, [sel,
        state.linkFor !== o.id ? h("button", { type: "button", class: "mt-link", "data-focus": "link-" + o.id, onclick: () => {
          state.linkFor = o.id;
          state.link = { kind: (o.link && o.link.kind) || "complaint", id: (o.link && o.link.id) || "", busy: false, error: null };
          render();
          focusField('[name="order_link_id"]');
        } }, [icon("edit"), tr("meet.staff.link_edit")]) : null]);
      if (state.linkFor === o.id) {
        const l = state.link;
        tools.appendChild(h("form", { class: "mt-linkform", novalidate: true, onsubmit: (e) => { e.preventDefault(); saveLink(m, o); } }, [
          select("order_link_kind", l.kind, [["complaint", tr("meet.link.complaint")], ["work", tr("meet.link.work")], ["project", tr("meet.link.project")]],
            (v) => { l.kind = v; render(); }),
          linkPicker(l.kind, m.district, l.id, (v) => { l.id = v; render(); }, "order_link_pick"),
          input("order_link_id", l.id, (v) => { l.id = v; }, { maxlength: "96", "aria-label": tr("meet.staff.link_id"), placeholder: tr("meet.staff.link_none"),
            autocomplete: "off", spellcheck: "false" }),
          h("button", { type: "submit", class: "bk-btn", disabled: l.busy ? true : null, "data-focus": "link-save", text: tr("meet.staff.link_save") }),
          h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "link-cancel", onclick: () => { state.linkFor = null; render(); }, text: tr("common.action.cancel") }),
          l.error ? h("p", { class: "bk-field__error", role: "alert", text: l.error }) : null,
        ]));
      }
      return tools;
    }
    function staffQuestions(m) {
      const pending = m.pending_questions || [];
      const sec = h("section", { class: "mt-sec", "aria-labelledby": "mt-sq" }, [
        h("div", { class: "mt-sec__hd" }, [h("h3", { class: "mt-sec__title", id: "mt-sq", text: tr("meet.questions") }),
          pending.length ? h("span", { class: "bk-tag bk-tag--warn", text: tr("meet.staff.pending", { n: pending.length }) }) : null]),
      ]);
      if (pending.length) {
        sec.appendChild(h("ul", { class: "mt-qlist mt-qlist--pending" }, pending.map((q) => {
          const flags = [];
          if (q.pii && q.pii.length) flags.push(tr("meet.staff.pii", { what: q.pii.map((k) => tr("ask.staff.pii." + k)).join(", ") }));
          if (q.rude) flags.push(tr("meet.staff.rude"));
          const busy = !!state.busy["q" + q.id];
          const li = h("li", { class: "mt-q mt-q--pending", "data-anchor": q.id }, [
            h("p", { class: "mt-q__text", lang: q.lang || textLang(q.text), text: q.text }),
            flags.length ? h("p", { class: "mt-flags" }, [icon("alert"), h("span", { text: flags.join(" · ") })]) : null,
            h("div", { class: "mt-actions mt-actions--sm" }, [
              h("button", { type: "button", class: "bk-btn", disabled: busy ? true : null, "data-focus": "pub-" + q.id, onclick: () => moderate(m, q, "publish"), text: tr("meet.staff.publish") }),
              h("button", { type: "button", class: "bk-btn bk-btn--ghost", disabled: busy ? true : null, "data-focus": "rej-" + q.id,
                onclick: () => { state.rejectFor = state.rejectFor === q.id ? null : q.id; state.reject = { reason: null, busy: false }; render(); }, text: tr("meet.staff.reject") }),
            ]),
          ]);
          if (state.rejectFor === q.id) {
            li.appendChild(h("form", { class: "mt-rejectform", novalidate: true, onsubmit: (e) => { e.preventDefault(); moderate(m, q, "reject"); } }, [
              field(tr("meet.staff.reject_reason"), select("reject_reason", state.reject.reason || "", [["", "—"]].concat(REASONS.map((r) => [r, tr("ask.staff.reason." + r)])),
                (v) => { state.reject.reason = v || null; state.reject.error = false; }), { error: state.reject.error ? tr("meet.staff.field_needed") : null }),
              h("button", { type: "submit", class: "bk-btn", disabled: busy ? true : null, "data-focus": "rej-send", text: tr("meet.staff.reject") }),
            ]));
          }
          return li;
        })));
      }
      if (m.questions.length) {
        sec.appendChild(h("ol", { class: "mt-qlist" }, m.questions.map((q) => h("li", { class: "mt-q", "data-anchor": q.id }, [
          h("p", { class: "mt-q__text", lang: q.lang || textLang(q.text), text: q.text }),
          h("div", { class: "mt-q__foot" }, [q.demo ? demoTag() : h("span"), h("span", { class: "mt-q__votes", text: votesText(q) })]),
          q.answer ? answerQuote(q) : null,
        ]))));
      } else if (!pending.length) {
        sec.appendChild(h("p", { class: "mt-empty-line", text: tr("meet.questions_empty") }));
      }
      return sec;
    }
    function staffResult(m) {
      const sec = h("section", { class: "mt-sec", "aria-labelledby": "mt-sr" }, [h("h3", { class: "mt-sec__title", id: "mt-sr", text: tr("meet.result") })]);
      const canEdit = !!state.cardStaff && !state.needLogin && m.phase !== "upcoming" && m.phase !== "cancelled";
      if (state.result && canEdit) {
        const r = state.result;
        sec.appendChild(h("form", { class: "mt-form", novalidate: true, onsubmit: (e) => { e.preventDefault(); saveResult(m); } }, [
          h("p", { class: "bk-field__hint", text: tr("meet.staff.result_hint") }),
          field(tr("meet.staff.result_ru"), input("result_ru", r.ru, (v) => { r.ru = v; }, { tag: "textarea", rows: "4", maxlength: "1500" })),
          field(tr("meet.staff.result_kk"), input("result_kk", r.kk, (v) => { r.kk = v; }, { tag: "textarea", rows: "4", maxlength: "1500", lang: "kk" })),
          r.error ? h("p", { class: "bk-field__error", role: "alert", text: r.error }) : null,
          h("div", { class: "mt-actions" }, [
            h("button", { type: "submit", class: "bk-btn bk-btn--primary", disabled: r.busy ? true : null, "data-focus": "res-save", text: tr("meet.staff.result_save") }),
            h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "res-cancel", onclick: () => { state.result = null; render(); }, text: tr("common.action.cancel") }),
          ]),
        ]));
        return sec;
      }
      if (m.result) {
        const text = lang() === "kk" ? m.result.kk || m.result.ru : m.result.ru || m.result.kk;
        sec.appendChild(h("p", { class: "mt-result__text", lang: textLang(text), text }));
      } else {
        sec.appendChild(h("p", { class: "mt-empty-line", text: tr(m.phase === "upcoming" ? "meet.staff.result_after" : "meet.staff.result_none") }));
      }
      if (canEdit) {
        sec.appendChild(h("button", { type: "button", class: "bk-btn mt-askbtn", "data-focus": "res-edit", onclick: () => {
          state.result = { ru: (m.result && m.result.ru) || "", kk: (m.result && m.result.kk) || "", busy: false, error: null };
          render();
          focusField('[name="result_ru"]');
        } }, [icon("edit"), tr(m.result ? "meet.staff.result_edit" : "meet.staff.result_save")]));
      }
      return sec;
    }
    function renderNewMeeting() {
      const d = state.draft;
      const wrap = h("div", { class: "mt-detail" });
      wrap.appendChild(h("button", { type: "button", class: "mt-back mt-link", "data-focus": "back", onclick: backToList }, [icon("back"), tr("meet.back")]));
      wrap.appendChild(h("h3", { class: "mt-dhead__title mt-focus-target", tabindex: "-1", "data-focus": "ntitle", text: tr("meet.staff.new") }));
      const err = (f) => (d.field === f ? d.error : null);
      const placeInput = input("place", d.place, (v) => { d.place = v; }, { list: "mt-places", maxlength: "120", autocomplete: "off" });
      const durations = [60, 90, 120, 180].map((n) => [String(n), tr("meet.staff.minutes", { n })]);
      wrap.appendChild(h("form", { class: "mt-form", novalidate: true, onsubmit: (e) => { e.preventDefault(); createMeeting(); } }, [
        field(tr("meet.staff.district"), select("district", d.district, DISTRICTS.map((x) => [x, districtName(x)]), (v) => {
          // Название по умолчанию следует за районом, пока сотрудник его не правил.
          if (d.title_ru === defaultTitle(d.district, "ru")) d.title_ru = defaultTitle(v, "ru");
          if (d.title_kk === defaultTitle(d.district, "kk")) d.title_kk = defaultTitle(v, "kk");
          d.district = v;
          render();
        })),
        field(tr("meet.staff.title_ru"), input("title_ru", d.title_ru, (v) => { d.title_ru = v; }, { maxlength: "120" }), { error: err("title_ru") }),
        field(tr("meet.staff.title_kk"), input("title_kk", d.title_kk, (v) => { d.title_kk = v; }, { maxlength: "120", lang: "kk" }), { error: err("title_kk") }),
        h("div", { class: "mt-grid2" }, [
          field(tr("meet.staff.date"), input("date", d.date, (v) => { d.date = v; }, { type: "date" }), { error: err("date") }),
          field(tr("meet.staff.time"), input("time", d.time, (v) => { d.time = v; }, { type: "time", step: "300" }), { error: err("time") }),
        ]),
        field(tr("meet.staff.duration"), select("duration", d.duration, durations, (v) => { d.duration = v; })),
        field(tr("meet.staff.place"), placeInput, { hint: tr("meet.staff.place_hint"), error: err("place") }),
        h("datalist", { id: "mt-places" }, state.places.filter((p) => p.k === "yard" || p.k === "park" || p.k === "bus_stop")
          .filter((p) => !d.district || !p.d || p.d === d.district).slice(0, 400)
          .map((p) => h("option", { value: lang() === "kk" && p.kk ? p.kk : p.ru }))),
        d.error && !d.field ? h("p", { class: "bk-field__error", role: "alert", text: d.error }) : null,
        h("div", { class: "mt-actions" }, [
          h("button", { type: "submit", class: "bk-btn bk-btn--primary", disabled: d.busy ? true : null, "data-focus": "create", text: tr("meet.staff.create") }),
          h("button", { type: "button", class: "bk-btn bk-btn--ghost", "data-focus": "create-cancel", onclick: backToList, text: tr("common.action.cancel") }),
        ]),
      ]));
      return wrap;
    }

    // ---------------------------------------------------------------- вкладка «Вопросы» — «Вопрос акиму» внутри
    function renderQuestionsTab() {
      const host = h("div", { class: "mt-askhost" });
      const Ask = root.BirgeAsk;
      if (Ask && typeof Ask.mount === "function") {
        try {
          askHandle = Ask.mount(host, { role: state.role, api: opts.api, apiBase: opts.apiBase, titleTag: "h3", embedded: true });
        } catch (e) {
          askHandle = null;
          host.appendChild(errorBox({ status: 500 }, () => render()));
        }
      } else {
        host.appendChild(stateBox("empty", tr("meet.tab.questions"), tr("common.state.loading"), null, "question"));
      }
      return host;
    }

    // ---------------------------------------------------------------- клавиатура, язык, вид
    // Esc закрывает один слой (как в FINAL-4): форму → встречу → (дальше — оболочка закрывает раздел).
    // Слушаем документ в фазе захвата: после перерисовки фокус может оказаться на body (нажатая строка заменена новой
    // разметкой), а Esc оболочки («закрыть раздел → карта», R01) не должен опередить закрытие нашего слоя.
    function onKey(e) {
      if (e.key !== "Escape" || e.defaultPrevented || !box.isConnected || !box.getClientRects().length) return;
      if (state.tab !== "meetings") return;  // вкладка «Вопросы» — Esc у «Вопроса акиму» и оболочки
      // Фокус — в нашем разделе: в .mt или в экране оболочки, который его держит (оболочка R01 при открытии раздела
      // ставит фокус на свой скрытый заголовок #birge-screen-title), либо на body после перерисовки.
      const target = e.target;
      const host = box.closest("#birge-screen, .birge-screen") || box;
      const inside = target && target.nodeType === 1 && host.contains(target);
      if (!inside && target !== doc.body && target !== doc.documentElement) return;  // фокус в другом модуле
      if (doc.querySelector("#birge-account:not([hidden]), .birge-more-menu:not([hidden]), .birge-palette:not([hidden])")) return;
      let handled = true;
      if (state.linkFor) state.linkFor = null;
      else if (state.rejectFor) state.rejectFor = null;
      else if (state.order) state.order = null;
      else if (state.result) state.result = null;
      else if (state.ask.open) state.ask = { open: false, text: "", error: null, busy: false, sent: false };
      else if (state.view === "detail" || state.view === "new") { backToList(); e.preventDefault(); e.stopPropagation(); return; }
      else handled = false;
      if (handled) { e.preventDefault(); e.stopPropagation(); render(); }
    }
    doc.addEventListener("keydown", onKey, true);
    function relang() { if (state.lang !== lang()) render(); }
    const offLang = I() && typeof I().onChange === "function" ? I().onChange(relang) : null;
    function onMode(e) {
      const mode = e && e.detail && e.detail.mode;
      if ((mode === "akimat" || mode === "resident") && mode !== state.role) {
        state.role = mode;
        state.view = state.view === "new" ? "list" : state.view;
        state.order = null;
        state.result = null;
        state.needLogin = false;
        state.list = null;
        state.card = null;
        load();
      }
    }
    doc.addEventListener("birge:mode", onMode);

    // Путь раздела: от оболочки (IA §7.3, opts.path), а в оболочке FINAL-4 — из адреса страницы (#meetings/<m-id>).
    applyPath(opts.path != null ? opts.path : hashPath(), true);
    if (I() && I().ready && typeof I().ready.then === "function") I().ready.then(load, load);
    else load();

    return {
      setLang: relang,
      // Оболочка сменила адрес внутри раздела (#meetings/<m-id>, #meetings/questions) — без перемонтажа (IA §7.3).
      setPath(path) {
        const before = state.tab + "|" + state.view + "|" + state.meetingId;
        applyPath(path, false);
        if (before !== state.tab + "|" + state.view + "|" + state.meetingId) load();
        else scrollToAnchor();
      },
      refresh: () => load(),
      destroy() {
        state.alive = false;
        clearTimeout(state.skeletonTimer);
        if (offLang) offLang();
        doc.removeEventListener("birge:mode", onMode);
        doc.removeEventListener("keydown", onKey, true);
        if (askHandle) { try { askHandle.destroy(); } catch (e) { /* ничего */ } askHandle = null; }
        if (box.parentNode) box.parentNode.removeChild(box);
      },
    };
  }

  root.BirgeMeetings = { mount, version: "r13-meetings-1" };
  // Оболочка без строки meetings в SCREENS (до схемы R11 в сборке): регистрируемся сами — пункт в «Ещё».
  // Подпись пункта — ключ словаря R11 (IA §8), а пока его нет в словаре — свой запасной текст ru/kk.
  function selfRegister() {
    const shell = root.BirgeShell;
    if (!shell || typeof shell.registerScreen !== "function" || root.__birgeMeetingsRegistered) return;
    const spec = { id: "meetings", mount, modes: ["resident", "akimat"] };
    if (I() && typeof I().has === "function" && I().has("shell.nav.meetings")) spec.titleKey = "shell.nav.meetings";
    else spec.title = { ru: KEYS.ru["meet.title"], kk: KEYS.kk["meet.title"] };
    root.__birgeMeetingsRegistered = shell.registerScreen(spec);
    // Оболочка FINAL-4 разбирает адрес при запуске, когда раздела ещё нет: открываем его сами, если адрес наш.
    if (root.__birgeMeetingsRegistered && /^#meetings(\/|$)/.test((root.location && root.location.hash) || "")
        && shell.section !== "meetings" && typeof shell.setSection === "function") {
      shell.setSection("meetings", { hash: false });
    }
  }
  function whenReady() {
    if (I() && I().ready && typeof I().ready.then === "function") I().ready.then(selfRegister, selfRegister);
    else selfRegister();
  }
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", whenReady);
  else whenReady();
})(typeof window !== "undefined" ? window : this);
