/* R07 · Тепловая карта объектов (раунд 14, Birge).
 *
 * Подключение (R01, см. research/round-14-results/R07/INTEGRATION.txt):
 *   <link rel="stylesheet" href="/civic/heat/heat.css">  <script src="/civic/heat/heat.js"></script>
 *   const heat = window.CivicHeat.mount({ root, map, role: "akimat" | "resident" });
 *   heat.destroy();
 *   heat.setPickMode(true|false) — пока житель выбирает место (или класс body.birge-picking от оболочки):
 *     нажатие на значок = щелчок по карте в точке цели (мастер жалобы получает саму остановку), карточка не открывается.
 *
 * Что рисуется на карте MapLibre:
 *   объект (остановка) — кружок-ореол, растущий с весом, и значок «иконка + число»;
 *   участок улицы      — линия ТОЧНО по форме ребра OSM (геометрия приходит с сервера, здесь не меняется);
 *   двор / квартал     — заливка с контуром; «примерное место» — пунктирный контур;
 *   мелкий масштаб     — районы (заливка + значок с числом).
 * Цвет никогда не один: на каждом значке число людей, в карточке — слово уровня.
 * Все данные — GET /api/civic/v2/heat (ui/civic_heat). Тексты жалоб и точки жителей сюда не приходят.
 */
(function () {
  "use strict";

  const VERSION = "r07-round15";
  const NBSP = " ";
  const ANIM_MS = 800;           // перетекание цвета при новой жалобе (UX_BRIEF: ~0.8 с)
  // Значки ≥ 44 px (FINAL-3): кружок 44 + плашка с числом; размеры ниже — нижние границы, настоящие меряются в DOM.
  const BADGE_W = 60, BADGE_H = 44;   // полный значок (эталон A): кружок 34 + плашка числа; кнопка 44 по высоте
  const MINI_W = 44, MINI_H = 44;     // маленькая плашка с числом (районы), когда полному значку тесно (кнопка 44 по высоте)
  const CLUSTER_R = 56;          // значки ближе 56 px на экране собираются в один кластер
  const CLUSTER_W = 44;          // кружок-кластер 44 px
  const TOP_N = 10;              // «Горячие места»: список и стартовая подгонка карты — одни и те же 10 мест
  const DISTRICT_ZOOM = 12;      // меньше — районы (CONTRACT §6); сервер присылает то же значение в meta
  // «Меньше движения» в системе: карта не пролетает, а сразу встаёт на место (UX_BRIEF правило 8).
  const moveMs = (ms) => (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : ms);

  // ---------- Тексты ru / kk ----------
  // Ключи heat.* переданы R11 (INTEGRATION.txt, блок I18N_KEYS). Если общий Birge.i18n уже подключён
  // и знает ключ — берём его перевод, иначе — этот запасной словарь. Казахский проверяет владелец.
  const DICT = {
    ru: {
      "heat.title": "Карта жалоб",
      "heat.subtitle": "Где жители сообщают о проблемах",
      "heat.top_line": "Больше всего жалоб: {target} · {people}",
      "heat.demo_note": "Примеры: жалобы придуманы, улицы и остановки настоящие (OpenStreetMap).",
      "heat.demo_tag": "Пример",
      "heat.filters": "Фильтры",
      "heat.category_all": "Все категории",
      "heat.period": "Период",
      "heat.days": { one: "{count} день", few: "{count} дня", many: "{count} дней" },
      "heat.district": "Район",
      "heat.district_all": "Все районы",
      "heat.reset": "Сбросить",
      "heat.legend": "Сколько человек сообщили",
      "heat.legend_hint": "Свежие жалобы ярче: за 2 недели жалоба «остывает» вдвое.",
      "heat.fixed": "исправлено",
      "heat.hot_title": "Горячие места",
      "heat.people_short": { one: "{count} чел.", few: "{count} чел.", many: "{count} чел." },
      "heat.reported": { one: "Сообщил {count} человек", few: "Сообщили {count} человека", many: "Сообщили {count} человек" },
      "heat.reported_fixed": { one: "Сообщал {count} человек", few: "Сообщали {count} человека", many: "Сообщали {count} человек" },
      "heat.for_days": { one: "за {count} день", few: "за {count} дня", many: "за {count} дней" },
      "heat.level_word.1": "Немного жалоб", "heat.level_word.2": "Несколько жалоб", "heat.level_word.3": "Много жалоб", "heat.level_word.4": "Очень много жалоб",
      "heat.fixed_word": "Исправлено",
      "heat.fixed_until": "На карте зелёным до {date}",
      "heat.chart": "Жалобы по дням",
      "heat.chart_from": "14 дней назад",
      "heat.chart_to": "сегодня",
      "heat.topics": "О чём сообщают",
      "heat.status": "Статус",
      "heat.status.new": "Новое", "heat.status.accepted": "Принято", "heat.status.in_progress": "В работе", "heat.status.fixed": "Исправлено",
      "heat.kind.object": "Объект", "heat.kind.segment": "Участок улицы", "heat.kind.area": "Двор или квартал", "heat.kind.district": "Район",
      "heat.kind.approximate": "Область на карте",
      "heat.approximate": "Примерное место: точный объект не выбран, показана область.",
      "heat.take": "Взять в работу",
      "heat.mark_fixed": "Отметить исправленным",
      "qr.print": "Распечатать QR",
      "heat.metoo": "Я тоже",
      "heat.metoo_done": { one: "Вы с нами. Сообщил {count} человек", few: "Вы с нами. Сообщили {count} человека", many: "Вы с нами. Сообщили {count} человек" },
      "heat.metoo_already": "Вы уже отметились",
      "heat.toast_taken": "Взято в работу",
      "heat.toast_fixed": "Отмечено как исправленное",
      "heat.toast_metoo": "Спасибо. Ваш голос учтён",
      "heat.toast_new": "Новая жалоба: {target}",
      "heat.action_failed": "Не получилось сохранить. Проверьте связь и попробуйте ещё раз",
      "heat.back": "Горячие места",
      "heat.close": "Закрыть",
      "heat.card.people": { one: "человек сообщил", few: "человека сообщили", many: "человек сообщили" },
      "heat.card.people_fixed": { one: "человек сообщал", few: "человека сообщали", many: "человек сообщали" },
      "heat.tab.overview": "Обзор",
      "heat.tab.reports": "Обращения",
      "heat.tab.history": "История",
      "heat.row.most": "Чаще всего",
      "heat.row.topic": "Тема",
      "heat.row.qr": "Табличка с QR",
      "heat.row.qr_action": "Распечатать",
      "heat.row.period": "Период",
      "heat.row.reported": "Сообщили",
      "heat.more_reports": { one: "Ещё {count} обращение", few: "Ещё {count} обращения", many: "Ещё {count} обращений" },
      "heat.all_reports": "Все обращения",
      "heat.group.new": "Новые",
      "heat.group.work": "В работе",
      "heat.loading": "Загружаем жалобы…",
      // Пустой фильтр (UX_REVIEW R11, день 3, №8) — ключи и тексты из общего словаря R11
      "heat.empty.title": { one: "За {n} день жалоб нет", few: "За {n} дня жалоб нет", many: "За {n} дней жалоб нет" },
      "heat.place_empty": { one: "{place}: за {n} день жалоб нет", few: "{place}: за {n} дня жалоб нет", many: "{place}: за {n} дней жалоб нет" },
      "heat.empty.hint": "Попробуйте период побольше",
      "heat.empty.hint_filters": "Попробуйте другой период или сбросьте фильтры",
      "heat.empty.show_days": { one: "Показать {n} день", few: "Показать {n} дня", many: "Показать {n} дней" },
      "heat.filter.reset": "Сбросить фильтры",
      // «Что пишут жители» (№4): тексты только у примеров или для сотрудника после входа
      "heat.texts.title": "Что пишут жители",
      "heat.texts.people": { one: "{count} человек", few: "{count} человека", many: "{count} человек" },
      "heat.texts.staff_only": "Тексты жителей видны сотрудникам после входа",
      "heat.texts.none": "Текстов пока нет",
      "moderation.rude": "Содержит грубые слова",
      "merge.title": "Объединено с этим",
      "merge.hint": "Если объединили по ошибке — разделите. Число людей у цели пересчитается.",
      "merge.kind.metoo": "Нажал «Я тоже» · {date}",
      "merge.kind.duplicate": "Отмечено дублем · {code} · {date}",
      "merge.separate": "Это разные проблемы",
      "merge.separated": "Разделено. Теперь это отдельное обращение {code}",
      "merge.already": "Уже разделено",
      "heat.error_title": "Нет связи с сервером",
      "heat.error_hint": "Проверьте интернет и нажмите «Повторить».",
      "heat.not_ready": "Тепловая карта ещё не подключена к серверу",
      "heat.retry": "Повторить",
      "heat.zoom_hint": "Приблизьте карту, чтобы увидеть улицы, дворы и остановки",
      "heat.too_many": "Слишком много действий подряд. Повторите позже.",
      "heat.example_readonly": "Это пример: статус примеров не меняется. Действия — у настоящих обращений.",
      "heat.not_found": "Обращение не найдено, карта обновлена.",
      "heat.need_login": "Войдите как сотрудник акимата и повторите.",
      "heat.badge_label": "{target}: {reported}",
      "heat.open_on_map": "Показать на карте",
      "heat.district_targets": { one: "{count} место с жалобами", few: "{count} места с жалобами", many: "{count} мест с жалобами" },
      "heat.tip.people": { one: "{count} человек", few: "{count} человека", many: "{count} человек" },
      "heat.cluster.places": { one: "{count} место", few: "{count} места", many: "{count} мест" },
      "heat.cluster.label": "Рядом {places}: {people}. Нажмите, чтобы приблизить",
      "heat.cluster.tip": "{places} · {people} — нажмите, чтобы приблизить",
      "heat.cluster.zoom": "Нажмите, чтобы приблизить",
      // Раунд 15: кластер из одних исправленных мест — ✓ и число мест (людей прошлых жалоб на нём не считаем)
      "heat.cluster.fixed_label": "Рядом исправлено: {places}. Нажмите, чтобы приблизить",
      "heat.cluster.fixed_tip": "Исправлено: {places} — нажмите, чтобы приблизить",
      "heat.kind.bus_stop": "Остановка", "heat.kind.playground": "Детская площадка", "heat.kind.pitch": "Спортплощадка",
      "heat.kind.park": "Парк", "heat.kind.garden": "Сквер", "heat.kind.waste_disposal": "Контейнерная площадка",
      "heat.kind.recycling": "Приём вторсырья", "heat.kind.street_lamp": "Фонарь", "heat.kind.school": "Школа",
      "heat.kind.kindergarten": "Детский сад", "heat.kind.yard": "Двор",
      "heat.kind.traffic_signal": "Светофор", "heat.kind.crossing": "Пешеходный переход", "heat.kind.intersection": "Перекрёсток",
      // Волна 2 (ключи R11: heat.legend.*, heat.reopened_mark, deadline.*; status.* — как heat.status.*)
      "heat.status.reported_fixed": "Служба сообщила об устранении", "heat.status.verified": "Проверено жителями",
      "heat.level_word.reported": "Исправлено — ждёт проверки",
      "heat.legend.reported_fixed": "сообщили об устранении", "heat.legend.verified": "проверено жителями",
      "heat.legend.nodata": "нет свежих данных", "heat.legend.nodata_hint": "Нет жалоб и осмотров за период — это не значит, что всё хорошо",
      "heat.reopened_mark": "вернули жители",
      // Раунд 15: «Хроника города» — панель показывает горячие места выбранного дня (web/civic/replay)
      "heat.replay.list_note": "Хроника: так карта выглядела в этот день",
      "heat.replay.list_empty": "В этот день жалоб на карте не было",
      "heat.replay.command": "Хроника города: неделя за 10 секунд",
      "heat.replay.command_month": "Хроника города: месяц",
      "heat.reopened_note": "Проблема осталась — снова в работе · вернули жители",
      "heat.reported_wait": "Ждёт проверки жителями",
      "heat.verified_note": { one: "Подтвердил {count} житель", few: "Подтвердили {count} жителя", many: "Подтвердили {count} жителей" },
      "deadline.left": { one: "Остался {n} рабочий день", few: "Осталось {n} рабочих дня", many: "Осталось {n} рабочих дней" },
      "deadline.today": "Срок ответа — сегодня",
      "deadline.overdue": { one: "Просрочено на {n} день", few: "Просрочено на {n} дня", many: "Просрочено на {n} дней" },
      "heat.already_changed": "Статус уже изменён — карта обновлена",
      "heat.role.akimat": "Акимат", "heat.role.resident": "Житель",
      // Чистый дизайн (R11 CLEAN_PASS, FINAL-3): ключи R11 (common.*, heat.legend.few/many) — запасные значения здесь
      "common.demo_footnote": "Данные — пример: жалобы придуманы, улицы и остановки — OpenStreetMap.",
      "heat.legend.few": "мало", "heat.legend.many": "много",
      "heat.approx_short": "Примерное место",
    },
    kk: {
      "heat.title": "Шағымдар картасы",
      "heat.subtitle": "Тұрғындар қай жерде мәселе туралы хабарлайды",
      "heat.top_line": "Ең көп шағым: {target} · {people}",
      "heat.demo_note": "Мысалдар: шағымдар ойдан құрастырылған, көшелер мен аялдамалар нақты (OpenStreetMap).",
      "heat.demo_tag": "Үлгі",
      "heat.filters": "Сүзгілер",
      "heat.category_all": "Барлық санаттар",
      "heat.period": "Кезең",
      "heat.days": { other: "{count} күн" },
      "heat.district": "Аудан",
      "heat.district_all": "Барлық аудандар",
      "heat.reset": "Тазарту",
      "heat.legend": "Қанша адам хабарлады",
      "heat.legend_hint": "Жаңа шағымдар ашығырақ: 2 аптада шағымның салмағы екі есе азаяды.",
      "heat.fixed": "түзетілді",
      "heat.hot_title": "Шағымы көп орындар",
      "heat.people_short": { other: "{count} адам" },
      "heat.reported": { other: "{count} адам хабарлады" },
      "heat.reported_fixed": { other: "{count} адам хабарлаған" },
      "heat.for_days": { other: "соңғы {count} күнде" },
      "heat.level_word.1": "Шағым аз", "heat.level_word.2": "Бірнеше шағым", "heat.level_word.3": "Шағым көп", "heat.level_word.4": "Шағым өте көп",
      "heat.fixed_word": "Түзетілді",
      "heat.fixed_until": "Жасыл түспен көрсетілу мерзімі: {date}",
      "heat.chart": "Күндер бойынша шағымдар",
      "heat.chart_from": "14 күн бұрын",
      "heat.chart_to": "бүгін",
      "heat.topics": "Не туралы хабарлайды",
      "heat.status": "Мәртебесі",
      "heat.status.new": "Жаңа", "heat.status.accepted": "Қабылданды", "heat.status.in_progress": "Орындалуда", "heat.status.fixed": "Түзетілді",
      "heat.kind.object": "Нысан", "heat.kind.segment": "Көше бөлігі", "heat.kind.area": "Аула немесе орам", "heat.kind.district": "Аудан",
      "heat.kind.approximate": "Картадағы аумақ",
      "heat.approximate": "Шамамен көрсетілген орын: нақты нысан таңдалмаған, аумақ көрсетілген.",
      "heat.take": "Жұмысқа алу",
      "heat.mark_fixed": "Түзетілді деп белгілеу",
      "qr.print": "QR басып шығару",
      "heat.metoo": "Мен де",
      "heat.metoo_done": { other: "Сіз бізбен біргесіз. {count} адам хабарлады" },
      "heat.metoo_already": "Сіз бұған дейін белгі қойғансыз",
      "heat.toast_taken": "Жұмысқа алынды",
      "heat.toast_fixed": "Түзетілді деп белгіленді",
      "heat.toast_metoo": "Рақмет. Дауысыңыз есепке алынды",
      "heat.toast_new": "Жаңа шағым: {target}",
      "heat.action_failed": "Сақталмады. Байланысты тексеріп, қайталап көріңіз",
      "heat.back": "Шағымы көп орындар",
      "heat.close": "Жабу",
      "heat.card.people": { other: "адам хабарлады" },
      "heat.card.people_fixed": { other: "адам хабарлаған" },
      "heat.tab.overview": "Шолу",
      "heat.tab.reports": "Өтініштер",
      "heat.tab.history": "Тарих",
      "heat.row.most": "Ең жиі",
      "heat.row.topic": "Тақырып",
      "heat.row.qr": "QR тақтайша",
      "heat.row.qr_action": "Басып шығару",
      "heat.row.period": "Кезең",
      "heat.row.reported": "Хабарлады",
      "heat.more_reports": { other: "Тағы {count} өтініш" },
      "heat.all_reports": "Барлық өтініштер",
      "heat.group.new": "Жаңа",
      "heat.group.work": "Орындалуда",
      "heat.loading": "Шағымдар жүктеліп жатыр…",
      "heat.empty.title": { other: "Соңғы {n} күнде шағым жоқ" },
      "heat.place_empty": { other: "{place}: соңғы {n} күнде шағым жоқ" },
      "heat.empty.hint": "Ұзағырақ кезеңді таңдап көріңіз",
      "heat.empty.hint_filters": "Басқа кезеңді таңдаңыз немесе сүзгілерді тазартыңыз",
      "heat.empty.show_days": { other: "Соңғы {n} күнді көрсету" },
      "heat.filter.reset": "Сүзгілерді тазарту",
      "heat.texts.title": "Тұрғындар не жазады",
      "heat.texts.people": { other: "{count} адам" },
      "heat.texts.staff_only": "Тұрғындардың мәтіндерін қызметкерлер кіргеннен кейін көреді",
      "heat.texts.none": "Әзірге мәтін жоқ",
      "moderation.rude": "Дөрекі сөздер бар",
      "merge.title": "Осымен біріктірілген",
      "merge.hint": "Қате біріктірілсе — бөліңіз. Нысандағы адам саны қайта есептеледі.",
      "merge.kind.metoo": "«Мен де» басты · {date}",
      "merge.kind.duplicate": "Қайталанған деп белгіленді · {code} · {date}",
      "merge.separate": "Бұл әртүрлі мәселелер",
      "merge.separated": "Бөлінді. Енді бұл жеке өтініш: {code}",
      "merge.already": "Бұрын бөлінген",
      "heat.error_title": "Сервермен байланыс жоқ",
      "heat.error_hint": "Интернетті тексеріп, «Қайталау» түймесін басыңыз.",
      "heat.not_ready": "Шағымдар картасы серверге әлі қосылмаған",
      "heat.retry": "Қайталау",
      "heat.zoom_hint": "Көшелерді, аулаларды және аялдамаларды көру үшін картаны жақындатыңыз",
      "heat.too_many": "Қатарынан тым көп әрекет жасалды. Кейінірек қайталаңыз.",
      "heat.example_readonly": "Бұл — үлгі: үлгілердің мәртебесі өзгермейді. Әрекеттер нақты өтініштерде ғана.",
      "heat.not_found": "Өтініш табылмады, карта жаңартылды.",
      "heat.need_login": "Әкімдік қызметкері ретінде кіріп, қайталаңыз.",
      "heat.badge_label": "{target}: {reported}",
      "heat.open_on_map": "Картадан көрсету",
      "heat.district_targets": { other: "{count} орында шағым бар" },
      "heat.tip.people": { other: "{count} адам" },
      "heat.cluster.places": { other: "{count} орын" },
      "heat.cluster.label": "Жақын жерде {places}: {people}. Жақындату үшін басыңыз",
      "heat.cluster.tip": "{places} · {people} — жақындату үшін басыңыз",
      "heat.cluster.zoom": "Жақындату үшін басыңыз",
      "heat.cluster.fixed_label": "Жақын жерде түзетілді: {places}. Жақындату үшін басыңыз",
      "heat.cluster.fixed_tip": "Түзетілді: {places} — жақындату үшін басыңыз",
      "heat.kind.bus_stop": "Аялдама", "heat.kind.playground": "Балалар алаңы", "heat.kind.pitch": "Спорт алаңы",
      "heat.kind.park": "Саябақ", "heat.kind.garden": "Гүлзар", "heat.kind.waste_disposal": "Қоқыс алаңы",
      "heat.kind.recycling": "Қайталама шикізат қабылдау пункті", "heat.kind.street_lamp": "Көше шамы", "heat.kind.school": "Мектеп",
      "heat.kind.kindergarten": "Балабақша", "heat.kind.yard": "Аула",
      "heat.kind.traffic_signal": "Бағдаршам", "heat.kind.crossing": "Жаяу жүргіншілер өткелі", "heat.kind.intersection": "Қиылыс",
      "heat.status.reported_fixed": "Қызмет түзетілгенін хабарлады", "heat.status.verified": "Тұрғындар тексерді",
      "heat.level_word.reported": "Түзетілді — тексеруді күтуде",
      "heat.legend.reported_fixed": "түзетілгені хабарланды", "heat.legend.verified": "тұрғындар тексерді",
      "heat.legend.nodata": "жаңа дерек жоқ", "heat.legend.nodata_hint": "Кезеңде шағым да, тексеру де болмады — бұл бәрі жақсы дегенді білдірмейді",
      "heat.reopened_mark": "тұрғындар қайтарды",
      "heat.replay.list_note": "Шежіре: карта осы күні осындай болды",
      "heat.replay.list_empty": "Бұл күні картада шағым болған жоқ",
      "heat.replay.command": "Қала шежіресі: бір апта 10 секундта",
      "heat.replay.command_month": "Қала шежіресі: бір ай",
      "heat.reopened_note": "Мәселе қалды — қайта жұмыста · тұрғындар қайтарды",
      "heat.reported_wait": "Тұрғындардың тексеруін күтуде",
      "heat.verified_note": { other: "{count} тұрғын растады" },
      "deadline.left": { other: "{n} жұмыс күні қалды" },
      "deadline.today": "Жауап мерзімі — бүгін",
      "deadline.overdue": { other: "{n} күнге кешікті" },
      "heat.already_changed": "Мәртебесі бұрын өзгертілген — карта жаңартылды",
      "heat.role.akimat": "Әкімдік", "heat.role.resident": "Тұрғын",
      "common.demo_footnote": "Деректер — үлгі: шағымдар ойдан құрастырылған, көшелер мен аялдамалар — OpenStreetMap.",
      "heat.legend.few": "аз", "heat.legend.many": "көп",
      "heat.approx_short": "Шамамен көрсетілген орын",
    },
  };

  const MONTHS = {
    ru: ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
    kk: ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"],
  };

  // Иконки 24×24 (те же рисунки, что в ui-kit R11). Ключ — поле icon из categories_v2.json.
  const ICONS = {
    road: '<path d="M8 3 4 21M16 3l4 18"/><path d="M12 4v2.5M12 10.5v3M12 17.5V20"/>',
    snowflake: '<path d="M12 2v20M3.3 7l17.4 10M3.3 17 20.7 7"/><path d="m9.5 3.5 2.5 2 2.5-2M9.5 20.5l2.5-2 2.5 2"/>',
    walk: '<circle cx="13.5" cy="4" r="2"/><path d="m9 21 3-7 3 3v4M12 14l1-5.5M13 8.5l-4 1.5-1.5 4M13 8.5l2.5 3 3 1"/>',
    bus: '<rect x="4" y="3" width="16" height="15" rx="3"/><path d="M4 11h16M7 18v2.5M17 18v2.5M9 6.5h6"/>',
    bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.7.5 1.1 1.3 1.1 2.1V16h5v-.1c0-.8.4-1.6 1.1-2.1A6 6 0 0 0 12 3z"/>',
    trees: '<path d="M8 21v-4M8 3 3.5 11h2.5L3 15.5h10L10 11h2.5z"/><path d="M17 21v-6"/><circle cx="17" cy="11" r="4"/>',
    trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13M10 11v6M14 11v6"/>',
    droplet: '<path d="M12 3s6 6.6 6 11a6 6 0 0 1-12 0c0-4.4 6-11 6-11z"/>',
    wind: '<path d="M3 8h10a3 3 0 1 0-3-3M3 12h15a3 3 0 1 1-3 3M3 16h7"/>',
    shield: '<path d="M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6z"/><path d="m9 12 2 2 4-4"/>',
    parking: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M10 17V7h3a3 3 0 0 1 0 6h-3"/>',
    dots: '<circle cx="5.5" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="18.5" cy="12" r="1.6" fill="currentColor"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    playground: '<path d="M3 21 7 4h10l4 17M10 4v9M14 4v9M9 13h6"/>',
    ball: '<circle cx="12" cy="12" r="9"/><path d="m12 7.5 3.8 2.8-1.5 4.4H9.7l-1.5-4.4zM12 3v4.5M15.8 10.3l4.6-1.6M14.3 14.7l2.8 3.6M9.7 14.7l-2.8 3.6M8.2 10.3 3.6 8.7"/>',
    back: '<path d="M15 5l-7 7 7 7"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><circle cx="17" cy="9" r="2.5"/><path d="M16.5 14.1A5 5 0 0 1 21.5 19"/>',
    pin: '<path d="M12 21s-7-6.1-7-11.5a7 7 0 0 1 14 0C19 14.9 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    home: '<path d="M3 11.5 12 4l9 7.5M5.5 9.5V20h13V9.5M10 20v-5.5h4V20"/>',
    alert: '<path d="M10.3 4.2 2.6 17.5a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4M12 17h.01"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 2"/>',
    // Волна 1, п. 12: светофор, пешеходный переход («зебра»), перекрёсток
    traffic: '<rect x="8" y="2.5" width="8" height="19" rx="3"/><circle cx="12" cy="7" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/><circle cx="12" cy="17" r="1.5" fill="currentColor"/>',
    zebra: '<path d="M3.5 4.5h17M3.5 19.5h17"/><path d="M6.5 8v8M10.5 8v8M14.5 8v8M18.5 8v8" stroke-width="2.6"/>',
    crossroads: '<path d="M9 3v6H3M15 3v6h6M9 21v-6H3M15 21v-6h6"/>',
    list: '<path d="M8 6h12M8 12h12M8 18h8"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>',
    qr: '<rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><path d="M14 14h2v2M20 14v.01M14 20h.01M17 17h3v3"/>',
    wifi_off: '<path d="m3 3 18 18"/><path d="M8.5 16.4a5 5 0 0 1 7 0M5 12.9a10 10 0 0 1 4.2-2.6M14.8 10.3A10 10 0 0 1 19 12.9M2 9.3a15 15 0 0 1 4-2.6M10.5 5.1A15 15 0 0 1 22 9.3"/><path d="M12 20h.01"/>',
  };
  const KIND_ICON = { object: "pin", segment: "road", area: "home", district: "pin" };
  // Подтип реального объекта OSM (ui/civic_heat/osm_objects.py) → иконка в карточке
  const SUBTYPE_ICON = { bus_stop: "bus", playground: "playground", pitch: "ball", park: "trees", garden: "trees",
    waste_disposal: "trash", recycling: "trash", street_lamp: "bulb", school: "home", kindergarten: "home", yard: "home",
    traffic_signal: "traffic", crossing: "zebra", intersection: "crossroads" };
  // На значке на карте — иконка категории; у светофора, перехода и перекрёстка — своя (волна 1, п. 12)
  const BADGE_SUBTYPE_ICON = { traffic_signal: "traffic", crossing: "zebra", intersection: "crossroads" };

  // Пустое состояние и ошибка — поправка П1 «Без ИИ-слопа» (15 окт): одна маленькая монохромная иконка набора R11
  // (≤ 48 px) + короткий текст + одна кнопка. Больших рисунков нет. В оболочке — значок из спрайта ui-kit, без неё — тот же
  // рисунок из ICONS (те же линии 1,9).
  const STATE_ICON = { empty: "search", empty_filtered: "search", error: "wifi_off", not_ready: "alert" };
  const uiKit = () => (window.BirgeUI && typeof window.BirgeUI.icon === "function" ? window.BirgeUI : null);
  function illo(name) {
    const id = STATE_ICON[name] || "alert";
    const ui = uiKit();
    const inner = ui ? ui.icon(id.replace("_", "-")) : svgIcon(id, 32);
    return '<span class="r07-state-ic" aria-hidden="true">' + inner + "</span>";
  }
  // Статус-иконки (README эталона, правило 3 «Linear»; рисует R11 в ui-kit — если есть BirgeUI.statusIcon, берём её):
  // пустой кружок — новое, наполовину заполненный — в работе, кружок с галочкой — служба сообщила об устранении,
  // заполненный зелёный с галочкой — проверено жителями. Иконка + слово, одинаково на карте, в карточке и в списке.
  const STI_RING = '<circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" stroke-width="1.5"/>';
  const STI = {
    new: STI_RING,
    reopened: STI_RING,
    accepted: STI_RING + '<path d="M8 4.5A3.5 3.5 0 0 1 11.5 8H8Z" fill="currentColor"/>',
    in_progress: STI_RING + '<path d="M8 4.5a3.5 3.5 0 0 1 0 7Z" fill="currentColor"/>',
    reported_fixed: STI_RING + '<path d="m5.3 8.2 1.8 1.8 3.6-3.7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    verified: '<circle cx="8" cy="8" r="7" fill="currentColor"/><path d="m5.1 8.2 1.9 1.9 3.9-4" fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  };
  STI.fixed = STI.verified;
  const STC = { new: "#E24B4A", reopened: "#E24B4A", accepted: "#EF9F27", in_progress: "#EF9F27", reported_fixed: "#3B8A2E", verified: "#3B8A2E", fixed: "#3B8A2E", rejected: "#7E8A85" };
  function statusIcon(st) {
    const ui = window.BirgeUI;
    if (ui && typeof ui.statusIcon === "function") { try { const h = ui.statusIcon(st); if (h) return h; } catch (e) { /* своя ниже */ } }
    return '<svg class="r07-sti" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false" style="color:' + (STC[st] || STC.new) + '">' + (STI[st] || STI.new) + "</svg>";
  }
  function svgIcon(name, size) {
    const s = size || 20;
    return '<svg class="r07-ic" viewBox="0 0 24 24" width="' + s + '" height="' + s + '" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || ICONS.dots) + "</svg>";
  }

  // ---------- Мелкие помощники ----------
  function pluralForm(lang, n) {
    if (lang !== "ru") return "other";
    const a = Math.abs(n), n10 = a % 10, n100 = a % 100;
    if (Math.floor(a) !== a) return "other";
    if (n10 === 1 && n100 !== 11) return "one";
    if (n10 >= 2 && n10 <= 4 && (n100 < 12 || n100 > 14)) return "few";
    return "many";
  }
  const keep = (str) => String(str).replace(/ /g, NBSP);   // «за 30 дней» не рвётся на «за 30 / дней»
  function fmtNum(n) {
    const s = String(Math.round(Number(n) || 0));
    return s.length > 3 ? s.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP) : s;
  }
  function fmtDate(iso, lang) {
    const d = new Date(iso);
    if (isNaN(d)) return "";
    const t = new Date(d.getTime() + 5 * 3600 * 1000); // время Астаны, UTC+5
    return t.getUTCDate() + " " + MONTHS[lang][t.getUTCMonth()];
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }
  function hexToRgb(h) {
    const m = /^#?([0-9a-f]{6})$/i.exec(h || "");
    if (!m) return [200, 200, 200];
    const v = parseInt(m[1], 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }
  // Канал — всегда 0…255: метка кадра requestAnimationFrame бывает раньше performance.now() старта, и t < 0 давал
  // «#ffff100» (R01 r14_b2 на B0.18: MapLibre «Could not parse color», значок на кадр без цвета).
  const channel = (v) => Math.max(0, Math.min(255, Math.round(v)));
  function mix(a, b, t) {
    const x = hexToRgb(a), y = hexToRgb(b);
    const c = x.map((v, i) => channel(v + (y[i] - v) * t));
    return "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");
  }
  // Цвет с прозрачностью (хроника: новая цель проявляется из прозрачного, ушедшая — гаснет)
  function mixA(a, b, t, alpha) {
    const x = hexToRgb(a), y = hexToRgb(b);
    const c = x.map((v, i) => channel(v + (y[i] - v) * t));
    return "rgba(" + c.join(",") + "," + Math.max(0, Math.min(1, alpha)).toFixed(3) + ")";
  }
  function keyOf(target) { return target.kind + ":" + target.id; }
  // Цели, на которые можно повесить QR-табличку (R12: тот же вид id, что принимает /?report=): объект, участок, двор.
  const QR_ID = /^(osm-(node|way|relation)-[0-9]{1,15}|osm-w[0-9]{1,15}-[0-9]{1,6}|yard-r?[0-9]{1,15}(-[0-9]{1,3})?)$/;
  function inRing(pt, ring) {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  // Точка на линии на доле frac её длины (для коротких участков улиц плоские координаты точны достаточно).
  function alongLine(coords, frac) {
    const kx = Math.cos((coords[0][1] * Math.PI) / 180);
    const seg = [];
    let total = 0;
    for (let i = 0; i < coords.length - 1; i++) {
      const d = Math.hypot((coords[i + 1][0] - coords[i][0]) * kx, coords[i + 1][1] - coords[i][1]);
      seg.push(d);
      total += d;
    }
    let need = total * frac;
    for (let i = 0; i < seg.length; i++) {
      if (need <= seg[i] && seg[i] > 0) {
        const f = need / seg[i];
        return [coords[i][0] + (coords[i + 1][0] - coords[i][0]) * f, coords[i][1] + (coords[i + 1][1] - coords[i][1]) * f];
      }
      need -= seg[i];
    }
    return coords[coords.length - 1];
  }
  // Id устройства — ТОТ ЖЕ, что у формы жалобы R09 (ключ "birge.device", 16–80 символов [A-Za-z0-9_-]):
  // «Я тоже» одно на устройство, где бы его ни нажали (просьба R01, INTEGRATION §8). Старый ключ R07 переносим.
  const DEVICE_KEY = "birge.device";
  const DEVICE_RE = /^[A-Za-z0-9_-]{16,80}$/;
  let memoryDevice = null;
  function randomId(n) {
    const abc = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    const buf = new Uint8Array(n);
    if (window.crypto && window.crypto.getRandomValues) window.crypto.getRandomValues(buf);
    else for (let i = 0; i < n; i++) buf[i] = Math.floor(Math.random() * 256);
    return Array.from(buf, (b) => abc[b % abc.length]).join("");
  }
  function deviceId() {
    try {
      let id = localStorage.getItem(DEVICE_KEY);
      if (!id || !DEVICE_RE.test(id)) {
        // Старый ключ "birge.device_id" НЕ переносим: им же пользуется 3D-превью R05, и там id из Date.now + Math.random
        // (R15 S16) — по "birge.device" R09 открывает «Мои обращения». Новый id — только из crypto.
        id = memoryDevice || "d-" + randomId(24);
        if (window.crypto && window.crypto.getRandomValues) localStorage.setItem(DEVICE_KEY, id);   // без crypto — только в памяти
      }
      memoryDevice = id;
      return id;
    } catch (e) {
      memoryDevice = memoryDevice || "d-" + randomId(24);
      return memoryDevice;
    }
  }
  function metooDone(targetKey) {
    try { return JSON.parse(localStorage.getItem("birge.heat.metoo") || "{}")[targetKey] === true; } catch (e) { return false; }
  }
  function rememberMetoo(targetKey, on) {
    try {
      const all = JSON.parse(localStorage.getItem("birge.heat.metoo") || "{}");
      if (on === false) delete all[targetKey]; else all[targetKey] = true;
      localStorage.setItem("birge.heat.metoo", JSON.stringify(all));
    } catch (e) { /* приватный режим — не страшно */ }
  }

  // Шлюз R01 может завернуть ответ в конверт {ok, data} (как в civic-v1) — принимаем оба вида.
  function unwrap(body) {
    return body && body.ok === true && body.data && !body.items && !body.categories ? body.data : body;
  }

  // ---------- Модуль ----------
  let current = null;
  function mount(options) {
    const opts = options || {};
    const root = opts.root;
    const map = opts.map || null;
    const apiBase = (opts.apiBase || "/api/civic/v2").replace(/\/$/, "");
    const fetchFn = opts.fetch || window.fetch.bind(window);
    if (!root) throw new Error("CivicHeat.mount: нужен root");

    const S = {
      role: opts.role === "resident" ? "resident" : "akimat",
      lang: opts.lang || (window.Birge && window.Birge.i18n ? window.Birge.i18n.lang() : document.documentElement.lang === "kk" ? "kk" : "ru"),
      filters: { category: null, days: 30, district: null },
      meta: null,
      data: null,
      mode: "targets",
      status: "loading",      // loading | ready | error | not_ready
      selected: null,         // ключ выбранной цели
      catsOpen: false,        // раскрыт ли список категорий
      texts: new Map(),       // «Что пишут жители»: ключ|дни → {status, data}
      merged: new Map(),      // «Объединено с этим» (п. 9): ключ цели → {status, items}; только сотруднику
      mergedOpen: null,       // ключ цели, у которой список «Объединено» раскрыт
      legendEl: null,         // легенда на карте
      fitted: false,          // карта уже подогнана под горячие места (один раз, до первого касания)
      pendingSelect: null,    // цель из ссылки / «Картины дня», ждёт загрузки данных
      pendingPlace: null,     // место той же цели без жалоб (404 /heat/target с place) — для честного тоста с названием
      shownPlace: null,       // это место на карте: тёмный контур без цвета жалоб, пока не выбрали другое
      busyKey: null,          // строка «Горячих мест», которая «открывается» (перелёт к цели и её загрузка)
      detailsOpen: new Map(), // «цель|блок» → раскрыт ли «Подробнее» (выбор человека переживает перерисовку карточки)
      prevColors: new Map(),  // ключ → цвет до обновления (для плавного перехода)
      markers: new Map(),     // ключ → { marker, el, item }
      clusters: [],           // кружки-кластеры: { key, marker, el, members: [ключи], ll, w, h }
      clusterSeq: 0,
      top: [],                // 10 самых горячих мест (и в режиме районов) — список «Горячие места» и подгонка карты
      topItems: new Map(),    // ключ → место из top (в режиме районов его нет в S.data.items)
      places: [],             // все места (не районы) последнего ответа — для nearby() шторки «Рядом с вами»
      clusterSize: {},        // длина числа на кружке-кластере → [ширина, высота] (замер один раз на длину)
      badgeSize: {},          // вид значка (язык, состояние, длина числа, у района — название) → {w, h, mw, mh}
      anim: null,
      reqSeq: 0,
      destroyed: false,
    };
    const userMoved = { value: false };
    // «Хроника города» (раунд 15): on — карта показывает прошлый день; live — «сегодня», отложенное на время хроники;
    // frame — текущий день хроники; fading — ушедшие за день цели (ещё один шаг гаснут); shown — что сейчас на карте
    // (цвет, прозрачность, вес) — чтобы следующий день перетекал с того же места, даже если прошлый не доиграл.
    const R = { on: false, live: null, frame: null, missed: false, fading: [], shown: new Map(), tween: null, counts: null,
      cost: { ms: 0, n: 0, draws: 0, drawMs: 0 } };   // cost — сколько мс кадра уходит на код хроники (замер для DELIVERY)

    function t(key, params) {
      const p = params || {};
      const g = window.Birge && window.Birge.i18n;
      if (g && typeof g.has === "function" && g.has(key, S.lang)) return g.t(key, p, S.lang);
      let v = (DICT[S.lang] && DICT[S.lang][key]) || DICT.ru[key];
      if (v == null) { console.warn("[heat] нет текста", key); return key; }
      if (typeof v === "object") v = v[pluralForm(S.lang, Number(p.n != null ? p.n : p.count))] || v.other || v.many || "";
      return v.replace(/\{(\w+)\}/g, (w, name) => (name in p ? (typeof p[name] === "number" ? fmtNum(p[name]) : p[name]) : w));
    }
    const label = (target) => (S.lang === "kk" ? target.label_kk || target.label_ru : target.label_ru) || "";
    const catName = (id) => {
      const c = S.meta && S.meta.categories.find((x) => x.id === id);
      return c ? (S.lang === "kk" ? c.kk : c.ru) : id;
    };
    const catIcon = (id) => {
      const c = S.meta && S.meta.categories.find((x) => x.id === id);
      return (c && c.icon) || "dots";
    };
    // Уточнение (волна 1, п. 2): перевод из словаря R11 (subtopic.<id>), иначе — подпись из categories_v2.json (meta)
    const subName = (id) => {
      const g = window.Birge && window.Birge.i18n;
      if (g && typeof g.has === "function" && g.has("subtopic." + id, S.lang)) return g.t("subtopic." + id, {}, S.lang);
      const st = S.meta && (S.meta.subtopics || []).find((x) => x.id === id);
      return st ? (S.lang === "kk" ? st.kk || st.ru : st.ru) : null;
    };
    // Что за проблема у места: уточнение, если его выбрали хотя бы половина сообщивших, иначе категория
    // («Перекрёсток Кенесары и Иманова — светофор, 9 жалоб», волна 1, п. 12)
    const topicName = (it, cat) => {
      const top = it.top_subtopic;
      const name = top && top.count * 2 >= (it.count || 0) ? subName(top.id) || (S.lang === "kk" ? top.kk : top.ru) : null;
      return name || catName(cat || Object.keys(it.by_category || {})[0] || "other");
    };
    const legendLabel = (lv) => (S.lang === "kk" ? lv.kk : lv.ru);
    // Район места словами (из справочника /heat/meta): «Остановка · Нура» в строке над названием
    const distName = (id) => {
      const d = id && S.meta && (S.meta.districts || []).find((x) => x.id === id);
      return d ? (S.lang === "kk" ? d.kk || d.ru : d.ru) : "";
    };
    // У места только примеры R07 (в общей сборке их нет в хранилище жалоб R09): кнопок нет — честная пометка (R10 B-037)
    const examplesOnly = (it) => it.state !== "fixed" && !(it.open_ids || []).length && Number(it.examples_open) > 0;
    const lcFirst = (s) => (s ? s.charAt(0).toLocaleLowerCase(S.lang === "kk" ? "kk" : "ru") + s.slice(1) : s);

    // ----- разметка панели -----
    root.classList.add("r07-root");
    root.dataset.role = S.role;
    root.innerHTML = '<div class="r07-panel" aria-live="polite"></div><div class="r07-sr" role="status" aria-live="polite"></div><div class="r07-toasts" role="status" aria-live="polite"></div>';
    const panel = root.querySelector(".r07-panel");
    const srBox = root.querySelector(".r07-sr");
    const toastBox = root.querySelector(".r07-toasts");

    // action — {label, onClick}: у ошибки есть понятное действие («Повторить»), UX_BRIEF «Тексты».
    // Ошибка на экране одна: новая заменяет прежнюю (тост ui-kit с действием сам не закрывается), успех её закрывает.
    function closeErrorToast() {
      if (S.errorToast) { try { S.errorToast.close(); } catch (e) { /* уже закрыт */ } S.errorToast = null; }
    }
    function toast(text, kind, action) {
      if (kind === "error") closeErrorToast();
      const keep = (h) => { if (kind === "error") S.errorToast = h; else S.okToast = h; return h; };
      // В оболочке — общий тост ui-kit R11 (body, z-toast 60): не прячется под каталогом R05 и шторками (R10 B-023).
      const ui = window.BirgeUI;
      if (ui && typeof ui.toast === "function") {
        try { return keep(ui.toast(text, { type: kind === "error" ? "error" : "ok", action }) || null); } catch (e) { /* свой запасной */ }
      }
      const el = document.createElement("div");
      el.className = "r07-toast" + (kind === "error" ? " r07-toast--error" : "");
      el.setAttribute("role", kind === "error" ? "alert" : "status");
      const span = document.createElement("span");
      span.textContent = text;
      el.append(span);
      const close = () => { el.classList.add("r07-toast--out"); setTimeout(() => el.remove(), 300); if (S.errorToast && S.errorToast.el === el) S.errorToast = null; };
      if (action) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "r07-toast__action";
        b.textContent = action.label;
        b.addEventListener("click", () => { close(); action.onClick(); });
        el.append(b);
      }
      toastBox.append(el);
      setTimeout(close, action ? 8000 : 3600);
      return keep({ close, el });
    }

    // ----- загрузка -----
    async function getJson(path) {
      const res = await fetchFn(apiBase + path, { headers: { Accept: "application/json" } });
      let body = null;
      try { body = await res.json(); } catch (e) { body = null; }
      if (!res.ok) {
        const err = new Error((body && (body.message || (body.error && body.error.message))) || "HTTP " + res.status);
        err.status = res.status;
        err.body = body;
        throw err;
      }
      return unwrap(body);
    }

    function zoomNow() { return map ? map.getZoom() : 14; }
    function modeFor(z) { return z < ((S.meta && S.meta.district_zoom_max) || DISTRICT_ZOOM) ? "districts" : "targets"; }

    async function load(reason) {
      if (R.on) { R.missed = true; return; }   // хроника: «сегодня» догрузим после её закрытия (replay.end)
      const seq = ++S.reqSeq;
      if (!S.data) { S.status = "loading"; render(); }
      try {
        // Справочник (/heat/meta) и сами жалобы (/heat) — одновременно, а не друг за другом: на старте главный поток
        // занят картой и модулями, и каждый лишний круг «ответ → следующий запрос» стоил до 1 с до первого значка
        // (R01 INTEGRATION 21.9). Порог районов до прихода справочника — тот же DISTRICT_ZOOM, что присылает сервер.
        // Первый кадр оболочка R01 запрашивает заранее и отдаёт через opts.fetch (R01 INTEGRATION 22.1: /heat/meta,
        // районы и места за 30 дней при zoom 14) — здесь те же адреса.
        const metaReq = S.meta ? Promise.resolve(S.meta) : getJson("/heat/meta");
        const query = (zoom) => {
          const q = new URLSearchParams();
          q.set("days", String(S.filters.days));
          if (S.filters.category) q.set("category", S.filters.category);
          if (S.filters.district) q.set("district", S.filters.district);
          q.set("zoom", String(Math.floor(zoom * 10) / 10));
          return "/heat?" + q.toString();
        };
        // На мелком масштабе карта — районы, а список «Горячие места» — всё равно 10 мест: их берём вторым запросом.
        const districtsView = modeFor(zoomNow()) === "districts";
        const [meta, data, places] = await Promise.all([metaReq, getJson(query(zoomNow())),
          districtsView ? getJson(query(DISTRICT_ZOOM + 2)).catch(() => null) : Promise.resolve(null)]);
        if (seq !== S.reqSeq || S.destroyed) return;   // пришёл устаревший ответ — пропускаем
        S.meta = meta;
        const placeItems = ((places && places.mode === "targets") ? places : data).items || [];
        S.top = placeItems.filter((it) => it.state === "active" && it.count > 0 && it.target.kind !== "district").slice(0, TOP_N);
        S.topItems = new Map(S.top.map((it) => [keyOf(it.target), it]));
        S.places = placeItems.filter((it) => it.target.kind !== "district" && it.anchor && (it.count > 0 || it.state === "fixed"));
        S.prevColors = new Map((S.data ? S.data.items : []).map((it) => [keyOf(it.target), it.color]));
        S.data = data;
        S.mode = data.mode;
        S.status = "ready";
        closeErrorToast();   // связь вернулась — старое «Нет связи · Повторить» больше не нужно
        if (S.selected && !findItem(S.selected) && S.mode === "targets") S.selected = null;
        draw(reason === "event");
        render();
        afterLoad(reason);
      } catch (err) {
        if (seq !== S.reqSeq || S.destroyed) return;
        S.status = err.status === 503 ? "not_ready" : "error";
        if (!S.data) render();
        else {
          clearBusy();
          toast(S.status === "not_ready" ? t("heat.not_ready") : t("heat.error_title"), "error",
            { label: t("heat.retry"), onClick: () => void load() });
        }
      }
    }
    function findItem(key) { return S.data ? S.data.items.find((it) => keyOf(it.target) === key) : null; }

    // После каждой загрузки: открыть цель из ссылки / «Картины дня», иначе при открытии и при смене фильтра —
    // вписать 10 горячих мест из списка.
    function afterLoad(reason) {
      if (S.pendingSelect) {
        const key = S.pendingSelect;
        if (findItem(key)) { S.pendingSelect = null; clearBusy(); select(key, false); return; }
        if (S.mode === "targets" && !S.pendingMoving) {
          S.pendingSelect = null;   // за этот период жалоб по цели нет — честно сказать, а не молчать
          clearBusy();
          const place = S.pendingPlace && S.pendingPlace.key === key ? S.pendingPlace : null;
          S.pendingPlace = null;
          toast(place && label(place) ? t("heat.place_empty", { place: label(place), n: S.filters.days }) : t("heat.empty.title", { n: S.filters.days }));
        } else if (!S.pendingMoving && !(map && map.isMoving())) clearBusy();   // цель не открылась (перелёта не было) — строка не «крутится»
        return;
      }
      if (S.refitDistricts && S.mode === "districts") { S.refitDistricts = false; fitTop(reason === "filter"); return; }
      if (reason === "filter") { if (!fitTop(true)) fitDistrict(); return; }
      if (!S.fitted && !userMoved.value) { S.fitted = true; fitTop(false); }
    }
    // Фильтр района, а жалоб в нём за период нет — показать сам район (а не оставить карту где была).
    function fitDistrict() {
      const d = S.filters.district && S.meta && S.meta.districts.find((x) => x.id === S.filters.district);
      if (d && map && d.bbox) map.fitBounds([[d.bbox[0], d.bbox[1]], [d.bbox[2], d.bbox[3]]], { padding: fitPaddingNow(true), duration: moveMs(700) });
    }

    // Отступы для подгонки карты: шапка, шторка/панель и кнопки (opts.fitPadding — объект или функция, её даёт оболочка),
    // плюс половина значка (отступ считается до ЯКОРЯ, а значок шире точки) и место под легенду сверху/снизу.
    function fitPaddingNow(districts) {
      const padding = Object.assign({ top: 40, bottom: 40, left: 40, right: 40 },
        typeof opts.fitPadding === "function" ? opts.fitPadding() : opts.fitPadding || {});
      const halfW = districts ? 72 : BADGE_W / 2, halfH = BADGE_H / 2;
      padding.left += halfW; padding.right += halfW; padding.top += halfH; padding.bottom += halfH;
      if (map && S.legendEl && S.legendEl.isConnected) {
        const host = map.getContainer().getBoundingClientRect(), lr = S.legendEl.getBoundingClientRect();
        if (lr.top - host.top < host.height / 3) padding.top = Math.max(padding.top, lr.bottom - host.top + halfH + 8);
        else if (host.bottom - lr.bottom < host.height / 3 && lr.width > host.width * 0.6) padding.bottom = Math.max(padding.bottom, host.bottom - lr.top + halfH + 8);
      }
      return padding;
    }

    // Центр свободной части карты (без шапки, панели/шторки и кнопок — opts.fitPadding оболочки) относительно центра
    // контейнера: место, к которому летим, встаёт туда, а не в середину экрана — на телефоне это под шторкой
    // (R10 demo_flow 375 шаг 3: первое место из «Горячих мест» на обзоре города оставалось под ручкой шторки).
    function freeOffset() {
      if (!opts.fitPadding) return [0, 0];
      const p = Object.assign({ top: 0, bottom: 0, left: 0, right: 0 }, typeof opts.fitPadding === "function" ? opts.fitPadding() : opts.fitPadding);
      return [Math.round(((Number(p.left) || 0) - (Number(p.right) || 0)) / 2), Math.round(((Number(p.top) || 0) - (Number(p.bottom) || 0)) / 2)];
    }

    // Карта сама вписывает 10 горячих мест из списка (просьба владельца, п. 1): при открытии и при смене фильтров.
    // Список и карта совпадают: в списке те же места, что видны на карте (на мелком масштабе — внутри своих районов).
    // При открытии — только если пользователь ещё не трогал карту (UX_BRIEF, правило 8); при смене фильтра — всегда
    // (это действие пользователя), плавно и с учётом «меньше движения».
    function fitTop(animate) {
      if (!map || opts.fit === false) return false;
      const pts = (S.top || []).filter((it) => it.anchor);
      if (!pts.length) return false;
      const host = map.getContainer();
      // Отступы с учётом значков районов: если 10 мест разбросаны по городу, карта покажет районы.
      const padding = fitPaddingNow(false);
      // отступы больше самой карты — подгонять некуда (очень маленькое окно)
      if (padding.left + padding.right >= host.clientWidth - 20 || padding.top + padding.bottom >= host.clientHeight - 20) return false;
      const camFor = (list, pad, maxZoom) => {
        let a = 180, b = 90, c = -180, d = -90;
        list.forEach((it) => { a = Math.min(a, it.anchor[0]); c = Math.max(c, it.anchor[0]); b = Math.min(b, it.anchor[1]); d = Math.max(d, it.anchor[1]); });
        try { return map.cameraForBounds([[a, b], [c, d]], { padding: pad, maxZoom, bearing: map.getBearing() }); } catch (err) { return null; }
      };
      let cam = camFor(pts, padding, 16);
      if (!cam) return false;
      // 10 мест разбросаны по городу → карта покажет районы: тогда вписываем и сами районы с жалобами (значки районов
      // шире значков мест). Данных районов ещё нет (старт на крупном плане) — впишем их после загрузки (refitDistricts).
      const edge = (S.meta && S.meta.district_zoom_max) || DISTRICT_ZOOM;
      S.refitDistricts = false;
      if (cam.zoom < edge) {
        const ds = S.mode === "districts" ? S.data.items.filter((it) => it.target.kind === "district" && it.count > 0 && it.anchor) : [];
        const camD = ds.length >= 2 ? camFor(ds.concat(pts), fitPaddingNow(true), edge - 0.2) : null;
        if (camD) cam = camD;
        else if (S.mode !== "districts") S.refitDistricts = true;
      }
      S.fittedKeys = pts.map((it) => keyOf(it.target));
      const view = { center: cam.center, zoom: Math.max(cam.zoom, 9), bearing: map.getBearing() };
      if (animate) map.easeTo(Object.assign(view, { duration: moveMs(700) }));
      else map.jumpTo(view);
      return true;
    }

    // Открыть цель: из «Картины дня» (R08), по ссылке #target=kind:id&days=N или из оболочки R01.
    // days — тот же период, что в списке «Горячие места» (тогда число в карточке = числу в списке).
    async function focusTarget(kind, id, options) {
      const key = kind + ":" + id;
      const days = Number(options && options.days);
      const daysChanged = Number.isInteger(days) && days >= 1 && days <= 365 && days !== S.filters.days;
      if (daysChanged) S.filters.days = days;
      S.fitted = true;            // переход по ссылке важнее стартовой подгонки
      showPlace(null);
      if (!daysChanged && findItem(key)) { select(key, true); return; }
      S.pendingSelect = key;
      S.pendingMoving = true;
      S.busyKey = key;
      try {
        const q = new URLSearchParams({ kind, id, days: String(S.filters.days) });
        const res = await getJson("/heat/target?" + q.toString());
        const item = res && res.item;
        if (item) S.texts.set(textsKey(key), { status: "ready", data: item.texts || null });
        if (map && item && item.anchor) {
          const zoom = Math.max(map.getZoom(), kind === "object" ? 16 : 15);
          // ждём конца перелёта (если камера уже на месте, moveend может не прийти — страховка 1,2 с)
          await new Promise((done) => { map.once("moveend", done); setTimeout(done, 1200); map.easeTo({ center: item.anchor, zoom, offset: freeOffset(), duration: moveMs(600) }); });
        }
      } catch (err) {
        // Цели за период нет или сеть — ниже честно скажем. П3, сцена 0: «Показать на карте» у задачи «ИИ-разбора» R04
        // ведёт и на место без жалоб — сервер присылает его подпись и точку (place), карта всё равно летит туда.
        const place = err && err.status === 404 && err.body && err.body.place;
        if (place && Array.isArray(place.anchor) && map) {
          S.pendingPlace = Object.assign({ key }, place);
          showPlace(S.pendingPlace);
          const zoom = Math.max(map.getZoom(), kind === "object" ? 16 : 15);
          await new Promise((done) => { map.once("moveend", done); setTimeout(done, 1200); map.easeTo({ center: place.anchor, zoom, offset: freeOffset(), duration: moveMs(600) }); });
          if (S.shownPlace && S.shownPlace.key === key) placePulse(place.anchor);
        }
      }
      S.pendingMoving = false;
      await load();
    }
    // Строка «Горячих мест», по которой нажали на обзоре районов: пока карта перелетает и грузится место (S.pendingSelect),
    // она «открывается» — подсветка и кольцо вместо стрелки, чтобы нажатие не казалось потерянным (дизайн-марафон №8, №10).
    // Снимается, когда открылась карточка (списка уже нет), с честным тостом «жалоб нет» / «нет связи» или если перелёт
    // прервали.
    function clearBusy() {
      S.busyKey = null;
      panel.querySelectorAll(".r07-item--busy").forEach((b) => { b.classList.remove("r07-item--busy"); b.removeAttribute("aria-busy"); });
    }
    // Место цели без жалоб на карте — до выбора другой цели, следующего перехода или «Хроники».
    function placeData() {
      const p = S.shownPlace, type = String((p && p.geometry && p.geometry.type) || "");
      if (!type) return { type: "FeatureCollection", features: [] };
      const shape = type.includes("Point") ? "point" : type.includes("LineString") ? "line" : "area";
      return { type: "FeatureCollection", features: [{ type: "Feature", geometry: p.geometry, properties: { shape, approx: Boolean(p.approximate) } }] };
    }
    function showPlace(place) {
      if (!place && !S.shownPlace) return;
      S.shownPlace = place && place.geometry ? place : null;
      const src = map && layersReady && map.getSource(SRC_PLACE);
      if (src) src.setData(placeData());
    }
    // Одно спокойное кольцо там, куда прилетела карта (тот же пульс, что у новой жалобы, тёмный — не цвет уровня)
    function placePulse(anchor) {
      if (!map || !window.maplibregl) return;
      const el = document.createElement("div");
      el.className = "r07-pulse";
      el.style.setProperty("--r07-c", "#152c26");
      const marker = new window.maplibregl.Marker({ element: el, anchor: "center" }).setLngLat(anchor).addTo(map);
      setTimeout(() => marker.remove(), 2200);
    }

    function parseHash() {
      const raw = (window.location.hash || "").replace(/^#/, "");
      if (!raw) return null;
      const q = new URLSearchParams(raw);
      const target = q.get("target") || "";
      const i = target.indexOf(":");
      if (i <= 0) return null;
      return { kind: target.slice(0, i), id: target.slice(i + 1), days: q.get("days") ? Number(q.get("days")) : undefined };
    }
    function onHash() {
      const h = parseHash();
      if (h) void focusTarget(h.kind, h.id, { days: h.days });
    }

    // ----- слои карты -----
    const SRC = "r07-heat", SRC_PTS = "r07-heat-pts", SRC_PLACE = "r07-place";
    let layersReady = false;

    function beforeLayerId() {
      if (opts.beforeId) return opts.beforeId;
      const layers = (map.getStyle() && map.getStyle().layers) || [];
      const sym = layers.find((l) => l.type === "symbol");
      return sym ? sym.id : undefined;
    }

    function ensureLayers() {
      if (!map || layersReady) return;
      // isStyleLoaded() ждёт ещё и все источники подложки; слои же можно добавлять, как только
      // разобран сам стиль. Пробуем; если стиль ещё не готов — повторим на событии load.
      try {
        addLayers();
        layersReady = true;
      } catch (err) {
        if (map.getSource(SRC)) removeLayers();
        if (!waitingLoad) { waitingLoad = true; map.once("load", () => { waitingLoad = false; draw(false); }); }
      }
    }
    let waitingLoad = false;
    let handlersBound = false;   // обработчики кликов по слоям вешаются один раз (слои пересоздаются при смене роли)

    function addLayers() {
      const soft = S.role === "resident" ? 0.75 : 1;   // жителю — та же карта, но мягче
      map.addSource(SRC, { type: "geojson", data: { type: "FeatureCollection", features: [] }, promoteId: "key" });
      map.addSource(SRC_PTS, { type: "geojson", data: { type: "FeatureCollection", features: [] }, promoteId: "key" });
      const color = ["coalesce", ["feature-state", "color"], ["get", "color"]];
      // Вес цели: хроника (раунд 15) плавно меняет его через feature-state — ореол и толщина участка растут и опадают.
      const W = ["coalesce", ["feature-state", "w"], ["get", "w"]];
      const before = beforeLayerId();
      const add = (layer) => map.addLayer(layer, before);
      // Районы (мелкий масштаб)
      // «Нет свежих данных» (волна 2) — только районы на обзоре города: серая заливка, у мест серого нет (R11 §3)
      // Дизайн-марафон: обзор города спокойнее — заливка 0,22 (было 0,28), граница 1,5 px и 0,6 (было 2 px и 0,8)
      const districtFill = ["case", ["boolean", ["get", "nodata"], false], 0.2, ["==", ["get", "level"], 0], 0, 0.22 * soft];
      add({ id: "r07-district-fill", type: "fill", source: SRC, filter: ["==", ["get", "kind"], "district"],
        paint: { "fill-color": color, "fill-opacity": districtFill } });
      add({ id: "r07-district-line", type: "line", source: SRC, filter: ["==", ["get", "kind"], "district"],
        paint: { "line-color": color, "line-width": 1.5, "line-opacity": 0.6 } });
      // Дворы и кварталы
      // Мягкая ячейка: размытая кайма + полупрозрачная заливка, чтобы квартал не выглядел жёстким квадратом.
      // Дизайн-марафон: кайма тоньше и тише (0,22) — на среднем масштабе прежняя (0,45) читалась как грязное пятно.
      const AREA = ["in", ["get", "kind"], ["literal", ["area", "object_area"]]];
      add({ id: "r07-area-glow", type: "line", source: SRC, filter: AREA,
        paint: { "line-color": color, "line-width": ["interpolate", ["linear"], ["zoom"], 12, 3, 17, 12], "line-blur": ["interpolate", ["linear"], ["zoom"], 12, 2, 17, 9], "line-opacity": 0.22 * soft } });
      add({ id: "r07-area-fill", type: "fill", source: SRC, filter: AREA,
        paint: { "fill-color": color, "fill-opacity": ["case", ["get", "fixed"], 0.2, 0.34 * soft] } });
      // пунктир — «примерное место» и «служба сообщила об устранении» (ждёт проверки жителями)
      const DASHED = ["any", ["get", "approx"], ["boolean", ["get", "dashed"], false]];
      add({ id: "r07-area-line", type: "line", source: SRC, filter: ["all", AREA, ["!", DASHED]],
        paint: { "line-color": color, "line-width": 1.5, "line-opacity": 0.9 } });
      add({ id: "r07-area-approx", type: "line", source: SRC, filter: ["all", AREA, DASHED],
        paint: { "line-color": color, "line-width": 2, "line-dasharray": [2, 1.5] } });
      // Выделение выбранной цели: двор / площадка — тонкий тёмный контур поверх заливки
      add({ id: "r07-sel-outline", type: "line", source: SRC, filter: ["==", ["get", "key"], ""],
        paint: { "line-color": "#152c26", "line-width": 3 } });
      // участок улицы — тёмная подложка под цветной линией
      add({ id: "r07-sel-line", type: "line", source: SRC, filter: ["==", ["get", "key"], ""],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#152c26", "line-width": ["interpolate", ["linear"], ["zoom"], 11, ["+", 7, ["*", W, 0.25]], 17, ["+", 14, ["*", W, 1.1]]] } });
      // Участки улиц: белая подложка + цветная линия, толщина растёт с весом. Форма — из OSM как есть.
      add({ id: "r07-seg-casing", type: "line", source: SRC, filter: ["==", ["get", "kind"], "segment"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#ffffff", "line-width": ["interpolate", ["linear"], ["zoom"], 11, ["+", 4, ["*", W, 0.25 * soft]], 17, ["+", 9, ["*", W, 1.1 * soft]]] } });
      const segWidth = ["interpolate", ["linear"], ["zoom"], 11, ["+", 2, ["*", W, 0.2 * soft]], 17, ["+", 5, ["*", W, 0.9 * soft]]];
      add({ id: "r07-seg", type: "line", source: SRC, filter: ["all", ["==", ["get", "kind"], "segment"], ["!", ["boolean", ["get", "dashed"], false]]],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": color, "line-width": segWidth } });
      add({ id: "r07-seg-dashed", type: "line", source: SRC, filter: ["all", ["==", ["get", "kind"], "segment"], ["boolean", ["get", "dashed"], false]],
        layout: { "line-join": "round" },
        paint: { "line-color": color, "line-width": segWidth, "line-dasharray": [1.4, 1] } });
      // Объекты: ореол растёт с весом. Цвет никогда не один (UX_BRIEF, правило 5; UX_REVIEW R11 день 3, №2):
      // на 12–15 объекты уровней 1–2 не рисуются вовсе, а уровни 3–4 и «исправлено» — ореол + значок с числом;
      // с 15-го масштаба — все объекты: точка, ореол и значок.
      const haloRadius = ["interpolate", ["linear"], ["zoom"], 12, ["+", 8, ["*", W, 1.2 * soft]], 17, ["+", 20, ["*", W, 4 * soft]]];
      // Ореол — мягкий диск с тонким краем, а не размытое пятно (на 12–15 под кластером он читался как грязь)
      const haloPaint = { "circle-color": color, "circle-opacity": 0.2 * soft, "circle-blur": 0.18, "circle-radius": haloRadius,
        "circle-stroke-color": color, "circle-stroke-width": 1, "circle-stroke-opacity": 0.35 * soft };
      add({ id: "r07-obj-halo-lo", type: "circle", source: SRC_PTS, minzoom: 12, maxzoom: 15, filter: [">=", ["get", "level"], 3], paint: haloPaint });
      add({ id: "r07-obj-halo", type: "circle", source: SRC_PTS, minzoom: 15, paint: haloPaint });
      add({ id: "r07-obj-dot", type: "circle", source: SRC_PTS, minzoom: 15,
        paint: { "circle-color": color, "circle-radius": 6, "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
      // Место без жалоб (П3, «Показать на карте» из «ИИ-разбора»): тёмный контур, как у выбранной цели, без цвета жалоб;
      // точка — кольцо; пунктир — примерное место (как в легенде).
      map.addSource(SRC_PLACE, { type: "geojson", data: placeData() });
      const PLACE_W = ["case", ["==", ["get", "shape"], "line"], 5, 3];
      add({ id: "r07-place-line", type: "line", source: SRC_PLACE, filter: ["all", ["!=", ["get", "shape"], "point"], ["!", ["boolean", ["get", "approx"], false]]],
        layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#152c26", "line-width": PLACE_W } });
      add({ id: "r07-place-approx", type: "line", source: SRC_PLACE, filter: ["all", ["!=", ["get", "shape"], "point"], ["boolean", ["get", "approx"], false]],
        paint: { "line-color": "#152c26", "line-width": PLACE_W, "line-dasharray": [2, 1.5] } });
      add({ id: "r07-place-ring", type: "circle", source: SRC_PLACE, filter: ["==", ["get", "shape"], "point"],
        paint: { "circle-color": "rgba(255,255,255,0.6)", "circle-radius": 9, "circle-stroke-color": "#152c26", "circle-stroke-width": 3 } });

      // Прозрачность слоёв без фокуса — режим фокуса умножает её на 0,4 у всех целей, кроме выбранной.
      S.layerOpacity = {
        "r07-district-fill": ["fill-opacity", districtFill],
        "r07-seg-dashed": ["line-opacity", 1],
        "r07-district-line": ["line-opacity", 0.6],
        "r07-area-glow": ["line-opacity", 0.22 * soft],
        "r07-area-fill": ["fill-opacity", ["case", ["get", "fixed"], 0.2, 0.34 * soft]],
        "r07-area-line": ["line-opacity", 0.9],
        "r07-area-approx": ["line-opacity", 1],
        "r07-seg-casing": ["line-opacity", 1],
        "r07-seg": ["line-opacity", 1],
        "r07-obj-halo-lo": ["circle-opacity", 0.2 * soft],
        "r07-obj-halo": ["circle-opacity", 0.2 * soft],
        "r07-obj-dot": ["circle-opacity", 1],
      };
      applyFocus();
      if (handlersBound) return;
      handlersBound = true;
      const clickable = ["r07-seg", "r07-seg-dashed", "r07-area-fill", "r07-obj-dot", "r07-district-fill"];
      clickable.forEach((id) => {
        map.on("click", id, onFeatureClick);
        map.on("mouseenter", id, () => { hovered.add(id); syncCursor(); });
        map.on("mouseleave", id, () => { hovered.delete(id); syncCursor(); });
      });
    }

    // «Рука» над целью — своя и только когда щелчок по цели что-то делает. Чужой курсор (крестик мастера жалобы или
    // инструмента карты) не заменяем и не стираем: раньше уход с цели ставил "" и крестик пропадал до конца рисования.
    const hovered = new Set();
    let ownCursor = false;
    function syncCursor() {
      let cs = null;
      try { cs = map ? map.getCanvas().style : null; } catch (e) { cs = null; }
      if (!cs) return;
      const want = hovered.size > 0 && !R.on && !isPicking() && !mapTool();
      if (want && (!cs.cursor || cs.cursor === "pointer")) { cs.cursor = "pointer"; ownCursor = true; }
      // пока стоит крестик, «рука» под ним остаётся нашей: инструмент вернёт её, закончившись, — тогда и снимем
      else if (!want && ownCursor && cs.cursor !== "crosshair") { if (cs.cursor === "pointer") cs.cursor = ""; ownCursor = false; }
    }

    function onFeatureClick(e) {
      if (isPicking()) return;   // щелчок — для мастера жалобы, карточка цели под ним не открывается
      if (mapTool()) return;     // щелчок — инструменту карты (редактор рисует участок, 3D-проект, место идеи)
      if (R.on) return;          // хроника: карта показывает прошлый день, карточки «сегодня» не открываются
      const f = e.features && e.features[0];
      if (!f) return;
      const key = f.properties.key;
      if (f.properties.kind === "district") {
        // По району: приблизить к нему (это действие пользователя, не самопроизвольный прыжок).
        const it = findItem(key);
        if (it && it.anchor) map.easeTo({ center: it.anchor, zoom: 13, duration: moveMs(700) });
        return;
      }
      select(key, false);
    }

    function featureCollections() {
      const feats = [], pts = [];
      // Хроника: ушедшие за день цели ещё один шаг гаснут на карте (R.fading), значков у них уже нет.
      (S.data ? S.data.items : []).concat(R.on ? R.fading : []).forEach((it) => {
        const key = keyOf(it.target);
        const w = Math.min(Number(it.weight) || 0, 12);
        const props = { key, kind: it.target.kind, level: it.level === "fixed" ? 5 : it.level, color: it.color || "#999999",
          w: it.state === "fixed" ? 1 : w, fixed: it.state === "fixed", approx: !!it.approximate,
          dashed: it.state === "fixed" && it.fixed_kind === "reported",   // «служба сообщила об устранении» — пунктир
          nodata: it.state === "no_data" };                                // район без свежих данных — серый
        if (it.target.kind === "object") {
          // Ореол и точка — в центре объекта; если объект в OSM — многоугольник (площадка), рисуем и его контур.
          const point = it.geometry.type === "Point" ? it.geometry : (it.anchor ? { type: "Point", coordinates: it.anchor } : null);
          if (point) pts.push({ type: "Feature", properties: props, geometry: point });
          if (it.geometry.type !== "Point") feats.push({ type: "Feature", properties: Object.assign({}, props, { kind: "object_area" }), geometry: it.geometry });
        } else feats.push({ type: "Feature", properties: props, geometry: it.geometry });
      });
      return [{ type: "FeatureCollection", features: feats }, { type: "FeatureCollection", features: pts }];
    }

    function draw(animate) {
      if (map) {
        ensureLayers();
        if (layersReady) {
          const [fc, pc] = featureCollections();
          map.getSource(SRC).setData(fc);
          map.getSource(SRC_PTS).setData(pc);
          updateSelectionLayer();
          if (animate) animateColors();
        }
      }
      drawBadges();
    }

    // Плавное перетекание цвета целей, у которых сменился уровень (feature-state, ~0.8 с).
    function animateColors() {
      if (!map || !S.data) return;
      const changes = [];
      S.data.items.forEach((it) => {
        const key = keyOf(it.target);
        const before = S.prevColors.get(key);
        const src = it.target.kind === "object" ? SRC_PTS : SRC;
        if (it.color && before !== it.color) changes.push({ key, src, from: before || "#ffffff", to: it.color });
      });
      if (!changes.length) return;
      if (S.anim) cancelAnimationFrame(S.anim);
      const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const started = performance.now();
      const step = (now) => {
        const k = reduce ? 1 : Math.max(0, Math.min(1, (now - started) / ANIM_MS));   // первый кадр бывает раньше старта
        const eased = 1 - Math.pow(1 - k, 3);
        changes.forEach((c) => map.setFeatureState({ source: c.src, id: c.key }, { color: mix(c.from, c.to, eased) }));
        if (k < 1) S.anim = requestAnimationFrame(step);
        else { changes.forEach((c) => map.removeFeatureState({ source: c.src, id: c.key }, "color")); S.anim = null; }
      };
      S.anim = requestAnimationFrame(step);
    }

    // ----- «Хроника города» (раунд 15, web/civic/replay): карта показывает прошлый день -----
    // Хроника рисует теми же слоями и значками, что и «сегодня»: город «оживает», а не подменяется другой картой.
    //  replay.begin()            — запомнить «сегодня»; пока идёт хроника, живые обновления (новая жалоба, масштаб,
    //                              фильтр) не грузят /heat, а копятся; карточка закрыта, панель — горячие места дня;
    //  replay.frame(frame, {ms}) — нарисовать день {date, items, districts}: цвет, ореол и число перетекают за ms,
    //                              новые цели проявляются, ушедшие гаснут (ms = 0 и «меньше движения» — сразу);
    //  replay.end({ms})          — вернуть «сегодня» тем же перетеканием (последний кадр хроники = «сегодня»,
    //                              поэтому без мигания) и догрузить, что пришло за время хроники.
    function replayData(frame) {
      const mode = modeFor(zoomNow());
      return { mode, items: (mode === "districts" ? frame.districts : frame.items) || [], demo: frame.demo, replay: frame.date || null };
    }
    const wOf = (it) => (it.state === "fixed" ? 1 : Math.min(Number(it.weight) || 0, 12));
    function replayShow(data, ms) {
      const prev = new Map((S.data ? S.data.items : []).map((it) => [keyOf(it.target), it]));
      const next = new Map(data.items.map((it) => [keyOf(it.target), it]));
      const dur = moveMs(ms || 0);
      // Ушедшие за день цели гаснут (их значки — в drawBadges); прошлые угасшие уходят из источника карты насовсем.
      const fading = [];
      for (const [key, it] of prev) if (!next.has(key) && dur && R.on) fading.push(it);
      const dropped = R.fading.filter((it) => !next.has(keyOf(it.target)) && !fading.includes(it));
      R.fading = fading;
      if (map && layersReady) dropped.forEach((it) => clearState(keyOf(it.target), it));
      S.prevColors = new Map([...prev].map(([k, it]) => [k, it.color]));
      S.data = data;
      S.mode = data.mode;
      if (map) map.getContainer().style.setProperty("--r07-replay-ms", Math.max(dur, 1) + "ms");
      const counts = [];
      for (const [key, it] of next) {
        const before = prev.get(key);
        if (before && before.count !== it.count && dur) counts.push({ key, from: Number(before.count) || 0, to: Number(it.count) || 0 });
      }
      const d0 = performance.now();
      tweenFeatures(prev, fading, dur);   // начальные feature-state — до setData: новый день не мелькает «готовым»
      draw(false);
      tweenCounts(counts, dur);
      render();
      R.cost.draws += 1;
      R.cost.drawMs += performance.now() - d0;   // смена дня целиком: данные карты, значки, раскладка, панель
    }
    function stateSources(it) { return it.target.kind === "object" ? [SRC_PTS, SRC] : [SRC]; }
    function clearState(key, it) {
      R.shown.delete(key);
      stateSources(it).forEach((source) => { try { map.removeFeatureState({ source, id: key }); } catch (e) { /* слой пересоздан */ } });
    }
    function tweenFeatures(prev, fading, dur) {
      if (!map || !layersReady) { ensureLayers(); if (!layersReady) return; }
      if (R.tween) cancelAnimationFrame(R.tween);
      R.tween = null;
      const list = [];
      const startOf = (key, it) => R.shown.get(key) || (prev.get(key) ? { c: prev.get(key).color || "#999999", a: 1, w: wOf(prev.get(key)) } : { c: it.color || "#999999", a: 0, w: 0 });
      // Перетекают только цели в кадре (с запасом): остальные сразу встают в новый день — каждый кадр перетекания карта
      // пересчитывает краски всех изменившихся целей, а при 1 000 целях на экране обычно лишь часть.
      let view = null;
      try {
        const b = map.getBounds();
        const dx = (b.getEast() - b.getWest()) * 0.15, dy = (b.getNorth() - b.getSouth()) * 0.15;
        view = [b.getWest() - dx, b.getSouth() - dy, b.getEast() + dx, b.getNorth() + dy];
      } catch (e) { view = null; }
      const inView = (it) => {
        if (!view || it.target.kind === "district" || !it.anchor) return true;
        const [x, y] = it.anchor;
        return x >= view[0] && x <= view[2] && y >= view[1] && y <= view[3];
      };
      S.data.items.forEach((it) => {
        const key = keyOf(it.target);
        const to = { c: it.color || "#999999", a: 1, w: wOf(it) };
        const from = startOf(key, it);
        if (!dur || !inView(it) || (from.c === to.c && from.a === to.a && Math.abs(from.w - to.w) < 0.01)) {
          if (R.shown.has(key) || from.a !== 1) clearState(key, it);
          return;
        }
        list.push({ key, it, from, to });
      });
      fading.forEach((it) => {
        const key = keyOf(it.target);
        if (inView(it)) list.push({ key, it, from: startOf(key, it), to: { c: it.color || "#999999", a: 0, w: 0 }, out: true });
        else R.fading = R.fading.filter((x) => x !== it);   // вне кадра — уходит сразу
      });
      if (!list.length) return;
      const apply = (c, e) => {
        const now = { c: mix(c.from.c, c.to.c, e), a: c.from.a + (c.to.a - c.from.a) * e, w: c.from.w + (c.to.w - c.from.w) * e };
        R.shown.set(c.key, now);
        const st = { color: mixA(c.from.c, c.to.c, e, now.a), w: now.w };
        stateSources(c.it).forEach((source) => { try { map.setFeatureState({ source, id: c.key }, st); } catch (err) { /* нет слоя */ } });
      };
      list.forEach((c) => apply(c, 0));
      const started = performance.now();
      const step = (t) => {
        const c0 = performance.now();
        const k = Math.max(0, Math.min(1, (t - started) / dur));
        const e = 1 - Math.pow(1 - k, 3);   // ease-out, как перекраска карты (VISUAL_BRIEF п. 5)
        list.forEach((c) => apply(c, e));
        R.cost.ms += performance.now() - c0;
        R.cost.n += 1;
        if (k < 1) { R.tween = requestAnimationFrame(step); return; }
        R.tween = null;
        list.forEach((c) => { if (!c.out) clearState(c.key, c.it); });   // дошли — значения из данных, состояние не нужно
      };
      R.tween = requestAnimationFrame(step);
    }
    // Число на значке растёт и падает вместе с цветом (3 → 8 за шаг), а не прыгает
    function tweenCounts(list, dur) {
      if (R.counts) cancelAnimationFrame(R.counts);
      R.counts = null;
      // Прерванное перетекание (перемотка ← →) сразу дописывает свои итоговые числа: иначе значок, чьё число назавтра
      // не меняется (его не перерисовывают), так и остался бы с промежуточным
      (R.countList || []).forEach((c) => { const html = badgeCountHtml(c.item, c.to); if (c.el.r07Html !== html) { c.el.innerHTML = html; c.el.r07Html = html; } });
      R.countList = null;
      if (!list.length || !dur) return;
      const els = list.map((c) => {
        const m = S.markers.get(c.key);
        const el = m && m.el.querySelector(".r07-badge__count");
        return el ? Object.assign(c, { el, item: m.item }) : null;
      }).filter(Boolean);
      const started = performance.now();
      const step = (t) => {
        const c0 = performance.now();
        const k = Math.max(0, Math.min(1, (t - started) / dur));
        const e = 1 - Math.pow(1 - k, 3);
        R.cost.ms -= c0;   // время чисел — в ту же копилку, что перетекание цвета
        els.forEach((c) => {
          const html = badgeCountHtml(c.item, Math.round(c.from + (c.to - c.from) * e));
          if (c.el.r07Html !== html) { c.el.innerHTML = html; c.el.r07Html = html; }
        });
        R.cost.ms += performance.now();
        R.counts = k < 1 ? requestAnimationFrame(step) : null;
        if (k >= 1) R.countList = null;
      };
      els.forEach((c) => { const html = badgeCountHtml(c.item, c.from); c.el.innerHTML = html; c.el.r07Html = html; });
      R.countList = els;
      R.counts = requestAnimationFrame(step);
    }
    function replayBegin() {
      if (R.on) return false;
      R.on = true;
      R.live = S.data;
      R.missed = false;
      R.fading = [];
      R.cost = { ms: 0, n: 0, draws: 0, drawMs: 0 };
      if (S.selected) { S.selected = null; updateSelectionLayer(); }
      showPlace(null);
      hideTip();
      root.classList.add("r07-root--replay");
      if (map) map.getContainer().classList.add("r07-replaying");
      render();
      return true;
    }
    function replayFrame(frame, o) {
      if (!R.on || !frame) return;
      R.frame = frame;
      replayShow(replayData(frame), o && o.ms);
    }
    function replayEnd(o) {
      if (!R.on) return false;
      const live = R.live;
      const ms = o && o.ms != null ? o.ms : ANIM_MS;
      const sameMode = live && live.mode === modeFor(zoomNow());
      // «Сегодня» — тем же перетеканием, пока R.on (ушедшие за хронику места гаснут), и только потом обычный режим.
      if (sameMode) replayShow(live, ms);
      R.on = false;
      R.live = null;
      R.frame = null;
      root.classList.remove("r07-root--replay");
      if (map) map.getContainer().classList.remove("r07-replaying");
      render();
      if (R.missed || !sameMode) void load("event");
      return true;
    }
    // Панель во время хроники: горячие места этого дня (те же строки, что «Горячие места»); нажатие — к месту на карте
    function replayListHtml() {
      const day = R.frame && R.frame.date ? fmtDate(R.frame.date + "T12:00:00+05:00", S.lang) : "";
      const items = (R.frame && R.frame.items || []).filter((it) => it.state === "active" && it.count > 0)
        .slice().sort((a, b) => (b.weight || 0) - (a.weight || 0) || (b.count || 0) - (a.count || 0)).slice(0, TOP_N);
      const rows = items.map((it) => '<li><button type="button" class="r07-item" data-rkey="' + esc(keyOf(it.target)) + '">' +
        '<span class="r07-mini" data-level="' + esc(it.level) + '">' + fmtNum(it.count) + "</span>" +
        '<span class="r07-item__text"><span class="r07-item__title">' + esc(label(it.target)) + '</span><span class="r07-item__meta">' +
        esc(distName(it.district) || topicName(it)) + "</span></span></button></li>").join("");
      return '<section class="r07-hot r07-hot--replay" aria-labelledby="r07-hot-h"><header class="r07-lhd"><h2 class="r07-h" id="r07-hot-h">' +
        esc(t("heat.hot_title")) + '</h2><span class="r07-muted r07-lhd__days">' + esc(keep(day)) + "</span></header>" +
        (rows ? '<ol class="r07-list">' + rows + "</ol>" : '<p class="r07-muted r07-replay-empty">' + esc(t("heat.replay.list_empty")) + "</p>") +
        '<p class="r07-muted r07-replay-note">' + esc(t("heat.replay.list_note")) + "</p></section>";
    }
    function bindReplayList() {
      panel.querySelectorAll("[data-rkey]").forEach((b) => b.addEventListener("click", () => {
        const it = (R.frame && R.frame.items || []).find((x) => keyOf(x.target) === b.dataset.rkey);
        if (it && it.anchor && map) map.easeTo({ center: it.anchor, zoom: Math.max(map.getZoom(), 15), duration: moveMs(600) });
      }));
    }

    function updateSelectionLayer() {
      applyFocus();
      if (!map || !layersReady) return;
      const key = S.selected || "";
      map.setFilter("r07-sel-line", ["all", ["==", ["get", "key"], key], ["==", ["get", "kind"], "segment"]]);
      map.setFilter("r07-sel-outline", ["all", ["==", ["get", "key"], key], ["in", ["get", "kind"], ["literal", ["area", "object_area"]]]]);
    }

    // ----- значки с числом (DOM-маркеры: работают без шрифтов карты и доступны с клавиатуры) -----
    function drawBadges() {
      if (!map || !window.maplibregl) return;
      const items = S.data ? S.data.items : [];
      const keep = new Set();
      const measure = [];   // значки, у которых мог смениться размер, — меряются пачкой после всех записей
      items.forEach((it) => {
        if (!it.anchor || (it.target.kind === "district" && !it.count)) return;
        const key = keyOf(it.target);
        keep.add(key);
        let m = S.markers.get(key);
        if (!m) {
          const el = document.createElement("button");
          el.type = "button";
          // Новый значок мягко проявляется (дизайн-марафон №12): класс снимается после анимации, перерисовка его не повторяет.
          el.className = "r07-badge r07-badge--new";
          setTimeout(() => el.classList.remove("r07-badge--new"), 700);
          el.tabIndex = -1;
          el.dataset.key = key;   // строка «Горячих мест» того же места подсвечивается при наведении на значок
          el.addEventListener("click", (ev) => { ev.stopPropagation(); hideTip(); onBadgeClick(key, ev); });
          el.addEventListener("keydown", (ev) => onBadgeKey(key, ev));
          bindTip(el, () => { const cur = S.markers.get(key); return cur ? badgeTip(cur.item) : ""; });
          const marker = new window.maplibregl.Marker({ element: el, anchor: "center" }).setLngLat(it.anchor).addTo(map);
          m = { marker, el, item: it, spot: it.anchor };
          S.markers.set(key, m);
        }
        // Точку значка не сбрасываем к якорю у уже стоящего значка: её выбирает declutter (стабильность при сдвиге карты).
        if (!m.anchor || m.anchor[0] !== it.anchor[0] || m.anchor[1] !== it.anchor[1]) { m.marker.setLngLat(it.anchor); m.spot = it.anchor; }
        m.anchor = it.anchor;
        m.item = it;
        // Значок, у которого не изменилось видимое (число, уровень, цвет, состояние, подпись, язык, выбор), не трогаем:
        // «Хроника» меняет день каждые 0,5–1,5 с, а меняется за день обычно меньшая часть мест.
        const sig = [it.count, it.level, it.color, it.state, it.fixed_kind, it.reopened ? 1 : 0, S.lang, S.selected === key ? 1 : 0,
          it.target.label_ru, it.target.subtype, Object.keys(it.by_category || {})[0]].join("|");
        if (m.sig !== sig) {
          // Хроника: скрытый значок (в кластере, вне места) дорисуется, когда раскладка его покажет (declutter)
          if (R.on && m.el.hidden && m.sig) m.dirty = sig;
          else { fillBadge(m.el, it); m.sig = sig; m.dirty = null; }
        }
        m.el.classList.toggle("r07-badge--pick", !!S.picking);
        m.el.classList.remove("r07-badge--out");
        // Настоящий размер значка (у района с названием ~130 px, а не 64) — для честной проверки наложений.
        // Размер зависит только от вида значка (язык, состояние, длина числа, у района — название): меряем один раз на вид.
        const sizeKey = S.lang + "|" + (it.state === "fixed" ? "f" : "") + (it.reopened ? "r" : "") + "|" + String(fmtNum(it.count)).length +
          (it.target.kind === "district" ? "|" + label(it.target) : "");
        const known = S.badgeSize[sizeKey];
        if (known) { if (m.sizeKey !== sizeKey) { Object.assign(m, known); m.sizeKey = sizeKey; } }
        else if (m.dirty) { m.sizeKey = null; }   // размер узнаем, когда значок дорисуется
        else measure.push([m, sizeKey]);
      });
      // Замеры пачкой: сначала все записи, потом чтения. Пара «запись — замер» у каждого значка заставляла браузер
      // пересчитывать раскладку страницы ~2 000 раз — при 1 000 целей смена дня «Хроники» стоила ~0,3 с.
      if (measure.length) {
        measure.forEach(([m]) => { if (m.attached === false) { m.marker.addTo(map); m.attached = true; } m.el.hidden = false; m.el.classList.remove("r07-badge--mini"); });
        measure.forEach(([m]) => { if (m.el.offsetWidth) { m.w = m.el.offsetWidth; m.h = m.el.offsetHeight; } });
        // И размер маленькой плашки: с двузначным числом она ~47 px, а не 34 — иначе плашки налезали на соседей.
        measure.forEach(([m]) => m.el.classList.add("r07-badge--mini"));
        measure.forEach(([m, k]) => {
          if (m.el.offsetWidth) { m.mw = m.el.offsetWidth; m.mh = m.el.offsetHeight; }
          if (m.w) { m.sizeKey = k; S.badgeSize[k] = { w: m.w, h: m.h, mw: m.mw, mh: m.mh }; }
        });
        measure.forEach(([m]) => m.el.classList.remove("r07-badge--mini"));
      }
      for (const [key, m] of S.markers) {
        if (keep.has(key)) continue;
        S.markers.delete(key);
        if (R.on && !m.el.hidden && !moveMs(1)) { m.marker.remove(); continue; }
        if (R.on && !m.el.hidden) {   // хроника: место ушло с карты в этот день — значок мягко гаснет, а не исчезает
          m.el.classList.add("r07-badge--out");
          setTimeout(() => m.marker.remove(), 260);
        } else m.marker.remove();
      }
      declutter("full");   // новые данные — раскладываем заново
    }

    // ----- подсказка при наведении (просьба владельца, п. 9): название · сколько человек · категория -----
    function badgeTip(it) {
      if (!it) return "";
      if (it.target.kind === "district") {
        return label(it.target) + " · " + t("heat.tip.people", { count: it.count }) + " · " + t("heat.district_targets", { count: it.targets || 0 });
      }
      if (it.state === "fixed") {
        return label(it.target) + " · " + t(it.fixed_kind === "reported" ? "heat.status.reported_fixed" : it.fixed_kind === "verified" ? "heat.status.verified" : "heat.fixed_word");
      }
      const cat = Object.keys(it.by_category || {})[0];
      return label(it.target) + " · " + t("heat.tip.people", { count: it.count }) + " · " + topicName(it, cat) + (it.reopened ? " · " + t("heat.reopened_mark") : "");
    }
    const canHover = () => !window.matchMedia || window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    function bindTip(el, text) {
      const show = (viaFocus) => {
        if (!viaFocus && !canHover()) return;
        const s2 = text();
        if (!s2 || el.hidden) return;
        if (!S.tipEl || !S.tipEl.isConnected) {
          S.tipEl = document.createElement("div");
          S.tipEl.className = "r07-tip";
          S.tipEl.setAttribute("aria-hidden", "true");   // то же говорит aria-label значка
          map.getContainer().append(S.tipEl);
        }
        S.tipEl.textContent = s2;
        S.tipEl.hidden = false;
        const host = map.getContainer().getBoundingClientRect(), r = el.getBoundingClientRect();
        const tw = S.tipEl.offsetWidth, th = S.tipEl.offsetHeight;
        const x = Math.min(Math.max(r.left + r.width / 2 - host.left - tw / 2, 4), host.width - tw - 4);
        const below = r.top - host.top - th - 10 < 4;     // у верхнего края — под значком
        S.tipEl.style.left = Math.round(x) + "px";
        S.tipEl.style.top = Math.round(below ? r.bottom - host.top + 8 : r.top - host.top - th - 8) + "px";
      };
      el.addEventListener("mouseenter", () => { show(false); if (el.dataset.key) setHot(el.dataset.key); });
      el.addEventListener("mouseleave", () => { hideTip(); if (S.hotKey === el.dataset.key) setHot(null); });
      el.addEventListener("focus", () => { if (el.matches(":focus-visible")) show(true); });
      el.addEventListener("blur", hideTip);
    }
    function hideTip() { if (S.tipEl) S.tipEl.hidden = true; }

    // ----- режим фокуса (просьба владельца, п. 6): выбранная цель крупнее, остальное бледнеет до 40 %, Esc — сброс -----
    const FOCUS_DIM = 0.4;
    function applyFocus() {
      if (!map) return;
      const key = S.selected || "";
      map.getContainer().classList.toggle("r07-focusing", Boolean(key));
      if (!layersReady) return;
      for (const [id, [prop, base]] of Object.entries(S.layerOpacity || {})) {
        if (!map.getLayer(id)) continue;
        const v = key ? ["*", base, ["case", ["==", ["get", "key"], key], 1, FOCUS_DIM]] : base;
        try { map.setPaintProperty(id, prop, v); } catch (err) { /* слой пересоздаётся — поставим при следующей отрисовке */ }
      }
    }

    function fillBadge(el, it) {
      const fixed = it.state === "fixed";
      const district = it.target.kind === "district";
      const icon = fixed ? "check" : district ? "pin" : BADGE_SUBTYPE_ICON[it.target.subtype] || catIcon(Object.keys(it.by_category || {})[0] || "other");
      // Переход «служба сообщила» → «проверено жителями» и «новое» → «служба сообщила»: одно мягкое кольцо цвета нового
      // состояния (дизайн-марафон №12), а не скачок; первая отрисовка значка и «меньше движения» — без кольца (CSS).
      const before = el.dataset.level ? (el.dataset.fixed || el.dataset.level) : null;
      const after = fixed ? it.fixed_kind || "fixed" : String(it.level);
      if (before && before !== after && fixed) {
        el.classList.remove("r07-badge--settle");
        void el.offsetWidth;   // перезапуск анимации, если состояние сменилось ещё раз
        el.classList.add("r07-badge--settle");
        clearTimeout(el.r07SettleTimer);
        el.r07SettleTimer = setTimeout(() => el.classList.remove("r07-badge--settle"), 1000);   // кольцо --t-heat 800 мс
      }
      // Записи — только при изменении: хроника перерисовывает значки каждый день, и лишняя запись атрибута у 1 000 значков
      // — это пересчёт их стилей.
      const put = (name, value) => { if (value == null) { if (name in el.dataset) delete el.dataset[name]; } else if (el.dataset[name] !== value) el.dataset[name] = value; };
      put("level", fixed ? "fixed" : String(it.level));
      // Волна 2: «служба сообщила» — пунктирная кайма; «вернули жители» — отметка ↺ (R11 IA_WAVE2 §3)
      put("fixed", fixed && it.fixed_kind ? it.fixed_kind : null);
      put("reopened", it.reopened ? "true" : null);
      if (el.r07C !== (it.color || "#999")) { el.r07C = it.color || "#999"; el.style.setProperty("--r07-c", el.r07C); }
      put("kind", it.target.kind);
      el.classList.toggle("r07-badge--selected", S.selected === keyOf(it.target));
      const reported = t(fixed ? "heat.reported_fixed" : "heat.reported", { count: it.count });
      const stateWord = fixed ? t(it.fixed_kind === "reported" ? "heat.status.reported_fixed" : it.fixed_kind === "verified" ? "heat.status.verified" : "heat.fixed_word")
        : it.reopened ? t("heat.reopened_mark") : "";
      const aria = t("heat.badge_label", { target: label(it.target), reported }) + (stateWord ? ". " + stateWord : "");
      if (el.getAttribute("aria-label") !== aria) el.setAttribute("aria-label", aria);
      if (el.hasAttribute("title")) el.removeAttribute("title");   // подсказка при наведении — своя (название · люди · категория), без двойной системной
      put("label", label(it.target));   // для проверок (R10, тесты R07): какое место у значка
      // Обёртка __inner — для увеличения при наведении/выборе: сам el — маркер MapLibre, его transform двигает карта.
      // Кружок и плашку обновляем на месте, а не пересоздаём: тогда цвет кружка перетекает за 0,8 с (новая жалоба,
      // «исправлено → проверено»), а не меняется скачком (UX_BRIEF: плавное покраснение).
      const dotHtml = svgIcon(icon, 18) + (it.reopened ? '<span class="r07-badge__mark" aria-hidden="true">↺</span>' : "");
      const countHtml = badgeCountHtml(it, it.count);
      let dot = el.querySelector(".r07-badge__dot"), count = el.querySelector(".r07-badge__count");
      if (!dot || !count) {
        el.innerHTML = '<span class="r07-badge__inner"><span class="r07-badge__dot"></span><span class="r07-badge__count"></span></span>';
        dot = el.querySelector(".r07-badge__dot");
        count = el.querySelector(".r07-badge__count");
      }
      if (dot.r07C !== (it.color || "#999")) { dot.r07C = it.color || "#999"; dot.style.setProperty("--r07-c", dot.r07C); }
      if (dot.r07Html !== dotHtml) { dot.innerHTML = dotHtml; dot.r07Html = dotHtml; }
      if (count.r07Html !== countHtml) { count.innerHTML = countHtml; count.r07Html = countHtml; }
    }

    function badgeCountHtml(it, n) {
      return (it.target.kind === "district" ? '<span class="r07-badge__name">' + esc(label(it.target)) + " · </span>" : "") + fmtNum(n);
    }

    // Где можно поставить значок цели: у участка улицы — середина и ещё две точки на линии (30 % и 70 %),
    // чтобы число не пропадало, когда рядом значок горячее; у остальных — только якорь с сервера.
    function badgeSpots(it) {
      const spots = [it.anchor];
      const g = it.geometry;
      if (it.target.kind === "segment" && g && g.type === "LineString" && g.coordinates.length >= 2) {
        spots.push(alongLine(g.coordinates, 0.3), alongLine(g.coordinates, 0.7));
      }
      // Район большой: если у центра тесно, значок можно поставить в другой точке ВНУТРИ его границы.
      if (it.target.kind === "district" && g && (g.type === "Polygon" || g.type === "MultiPolygon")) {
        const polys = g.type === "Polygon" ? [g.coordinates] : g.coordinates;
        const ring = polys.reduce((best, poly) => (poly[0].length > best.length ? poly[0] : best), polys[0][0]);
        let w = 180, so = 90, e = -180, n = -90;
        ring.forEach(([x, y]) => { w = Math.min(w, x); e = Math.max(e, x); so = Math.min(so, y); n = Math.max(n, y); });
        const extra = [];
        for (const fy of [0.5, 0.35, 0.65, 0.2, 0.8]) for (const fx of [0.5, 0.35, 0.65, 0.2, 0.8]) {
          const pt = [w + (e - w) * fx, so + (n - so) * fy];
          if (inRing(pt, ring)) extra.push(pt);
        }
        extra.sort((a, b2) => Math.hypot(a[0] - it.anchor[0], a[1] - it.anchor[1]) - Math.hypot(b2[0] - it.anchor[0], b2[1] - it.anchor[1]));
        spots.push(...extra.slice(0, 12));
      }
      return spots;
    }

    // Значки не налезают друг на друга: сначала самые горячие. Не хватает места для полного значка —
    // маленькая плашка с числом (UX_REVIEW R11, день 3, №2: «а не пусто»); совсем некуда — прячем до приближения.
    // Видимая часть элемента: панель модуля длиннее экрана и прокручивается внутри своей шторки, а скрытая
    // (visibility: hidden у оболочки) значкам не мешает. Обрезаем по всем прокручиваемым / обрезающим предкам.
    function visibleRect(el) {
      if (!el || !el.isConnected || getComputedStyle(el).visibility === "hidden") return null;
      const r = el.getBoundingClientRect();
      let { left, top, right, bottom } = r;
      for (let p = el.parentElement; p && p !== document.body && p !== document.documentElement; p = p.parentElement) {
        const cs = getComputedStyle(p);
        if (cs.display === "none") return null;
        if (/(auto|scroll|hidden|clip)/.test(cs.overflowX + " " + cs.overflowY)) {
          const q = p.getBoundingClientRect();
          left = Math.max(left, q.left); top = Math.max(top, q.top); right = Math.min(right, q.right); bottom = Math.min(bottom, q.bottom);
        }
      }
      left = Math.max(left, 0); top = Math.max(top, 0); right = Math.min(right, innerWidth); bottom = Math.min(bottom, innerHeight);
      return right > left && bottom > top ? { left, top, right, bottom, width: right - left, height: bottom - top } : null;
    }

    // Раскладка значков. how: "full" — заново (новые данные); без аргумента — заново только если сменились масштаб,
    // поворот, наклон или размер карты. При простом сдвиге карты (и при перерисовке панели) уже поставленный значок
    // остаётся в своей точке: двигается, только если ушёл за край карты или налез на плашку / более горячий значок.
    // Иначе значки перепрыгивали после каждой остановки карты (замечание владельца на демо).
    // Смысловой зум (просьба владельца, п. 2): город (< 12) — районы; 12–15 — дворы и участки улиц; с 15 — и объекты.
    // Значок, которому тесно, и объекты на 12–15 не пропадают — собираются в кружок-кластер с числом людей и цветом
    // самого высокого уровня; нажатие на кластер приближает карту к его местам.
    // Плашки поверх карты, которые значок не должен закрывать: своя легенда и панель, кнопки MapLibre, чужие значки
    // и таблички проектов R05, плашки оболочки (opts.avoidRects).
    function overlayRects() {
      const overlays = [];
      if (S.legendEl && S.legendEl.isConnected) overlays.push(S.legendEl.getBoundingClientRect());
      // Своя панель / шторка поверх карты и кнопки MapLibre: значок наполовину под ними выглядит обрезанным.
      if (!root.contains(map.getContainer())) { const vr = visibleRect(root); if (vr) overlays.push(vr); }
      map.getContainer().querySelectorAll(".maplibregl-ctrl-group, .maplibregl-ctrl-attrib").forEach((el) => overlays.push(el.getBoundingClientRect()));
      // Чужие значки на той же карте: маркеры MapLibre и таблички проектов R05 (.b3d-label — свои кнопки в контейнере
      // холста, не маркеры): значок R07 не ложится поверх них (кадр Codex OFFLINE). Скрытые и прозрачные не мешают.
      map.getContainer().querySelectorAll(".maplibregl-marker:not(.r07-badge):not(.r07-pulse), .b3d-label:not(.b3d-label--hidden)").forEach((el) => {
        const r = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        if (r.width && r.height && cs.visibility !== "hidden" && Number(cs.opacity) > 0.1) overlays.push(r);
      });
      if (typeof opts.avoidRects === "function") overlays.push(...(opts.avoidRects() || []));
      // Полоса «Хроники города» (web/civic/replay) внизу карты: значки дня не прячутся под ней
      document.querySelectorAll(".rp-bar").forEach((el) => { const r = el.getBoundingClientRect(); if (r.width && r.height) overlays.push(r); });
      return overlays;
    }
    const overlaySig = (list) => list.map((r) => (r && r.width ? Math.round(r.left) + "," + Math.round(r.top) + "," + Math.round(r.right) + "," + Math.round(r.bottom) : "")).join(";");
    // Плашки оболочки появляются и двигаются без движения карты: строка легенды — после первой отрисовки, «Карта улиц
    // не загрузилась» — когда не пришли тайлы, гаснет через 6 с. Раз в секунду (пока карта стоит) сверяем их рамки с
    // прошлой раскладкой; изменились — раскладываем значки заново (R11 badges_covered 360×800: «Байқоңыр» под легендой).
    const overlayTimer = map ? setInterval(() => {
      if (S.destroyed || !S.markers.size || map.isMoving() || S.overlaySig === undefined) return;
      if (overlaySig(overlayRects()) !== S.overlaySig) declutter();
    }, 1000) : null;

    function declutter(how) {
      if (!map) return;
      const z = map.getZoom(), bearing = map.getBearing(), pitch = map.getPitch();
      const placed = [];
      // Значки не прячутся под легендой и другими плашками поверх карты (opts.avoidRects — от оболочки).
      const host = map.getContainer().getBoundingClientRect();
      const L = S.layout;
      const full = how === "full" || !L || Math.abs(L.z - z) > 0.01 || Math.abs(L.bearing - bearing) > 0.5 ||
        Math.abs(L.pitch - pitch) > 0.5 || Math.abs(L.w - host.width) > 1 || Math.abs(L.h - host.height) > 1;
      const overlays = overlayRects();
      S.overlaySig = overlaySig(overlays);
      overlays.forEach((r) => { if (r && r.width) placed.push([r.left - host.left, r.top - host.top, r.right - host.left, r.bottom - host.top]); });
      const boxAt = (p, w, h) => [p.x - w / 2, p.y - h / 2, p.x + w / 2, p.y + h / 2];
      // Значок — только целиком внутри карты (обрезанный краем выглядит сломанным) и не поверх уже поставленных.
      const inside = (box) => box[0] >= 2 && box[1] >= 2 && box[2] <= host.width - 2 && box[3] <= host.height - 2;
      const free = (box) => inside(box) && !placed.some((b) => !(box[2] < b[0] || b[2] < box[0] || box[3] < b[1] || b[3] < box[1]));
      const prio = (a, b) => (keyOf(b.item.target) === S.selected) - (keyOf(a.item.target) === S.selected) ||
        (b.item.weight || 0) - (a.item.weight || 0) || (b.item.count || 0) - (a.item.count || 0);
      const list = [...S.markers.values()].sort(prio);
      const districts = S.mode === "districts";
      const sizeOf = (m, mode) => (mode === "mini" ? [Math.max(m.mw || MINI_W, MINI_W), Math.max(m.mh || MINI_H, MINI_H)]
        : [Math.max(m.w || BADGE_W, 44), Math.max(m.h || BADGE_H, 44)]);
      const result = new Map();   // marker → [mode, spot]
      const pool = [];            // кому нет места / объекты на 12–15 → в кластеры
      // Объекты (остановки, площадки, фонари…) по отдельности — с 15-го масштаба; выбранная цель видна всегда.
      // На 12–15 горячие объекты (уровни 3–4) и исправленные входят в кластеры; объекты уровней 1–2 там не рисуются
      // вовсе (UX_BRIEF, правило 5; R11 день 3, № 2) — иначе карта среднего масштаба стала бы пестрее, а не чище.
      const quiet = (it) => it.target.kind === "object" && z < 15 && keyOf(it.target) !== S.selected;
      const silent = (it) => quiet(it) && it.state !== "fixed" && Number(it.level) < 3;
      // Кластеры с прошлой раскладки: при сдвиге карты остаются, если им по-прежнему свободно.
      const keptClusters = [];
      if (!full) {
        // Выбранная цель — всегда полный значок в своей точке; остальные его обходят.
        const sel = list.find((m) => keyOf(m.item.target) === S.selected);
        if (sel) {
          const ll = badgeSpots(sel.item)[0];
          const [w, h] = sizeOf(sel, "full");
          placed.push(boxAt(map.project(ll), w, h));
          result.set(sel, ["full", ll]);
        }
        // 1-й проход: значки и кластеры, которые уже стоят, остаются на месте, если им там по-прежнему свободно.
        list.forEach((m) => {
          const prev = m.el.dataset.mode;
          if (result.has(m) || (prev !== "full" && prev !== "mini") || !m.spot || quiet(m.item)) return;
          const [w, h] = sizeOf(m, prev);
          const box = boxAt(map.project(m.spot), w, h);
          if (free(box)) { placed.push(box); result.set(m, [prev, m.spot]); }
        });
        S.clusters.forEach((c) => {
          const box = boxAt(map.project(c.ll), c.w, c.h);
          if (c.members.every((m) => S.markers.get(m) && !result.has(S.markers.get(m))) && free(box)) {
            placed.push(box);
            keptClusters.push(c);
            c.members.forEach((k) => result.set(S.markers.get(k), ["cluster", S.markers.get(k).spot || S.markers.get(k).item.anchor]));
          }
        });
      }
      // 2-й проход (или вся раскладка заново): остальным ищем место — сначала самые горячие.
      list.forEach((m) => {
        if (result.has(m)) return;
        const it = m.item;
        const selected = keyOf(it.target) === S.selected;
        if (silent(it)) { result.set(m, ["hidden", m.spot || it.anchor]); return; }
        if (quiet(it)) { pool.push(m); return; }
        const spots = badgeSpots(it).map((ll) => ({ ll, p: map.project(ll) }));
        const [fw, fh] = sizeOf(m, "full");
        const best = selected ? spots[0] : spots.find((sp) => free(boxAt(sp.p, fw, fh)));
        if (best) {
          placed.push(boxAt(best.p, fw, fh));
          result.set(m, ["full", best.ll]);
          return;
        }
        if (districts) {
          // районов шесть — маленькая плашка с числом (название остаётся в подсказке, aria-label и списке)
          const [mw, mh] = sizeOf(m, "mini");
          const mini = spots.find((sp) => free(boxAt(sp.p, mw, mh)));
          result.set(m, mini ? ["mini", mini.ll] : ["hidden", m.spot || it.anchor]);
          if (mini) placed.push(boxAt(mini.p, mw, mh));
          return;
        }
        pool.push(m);
      });
      // Кластеры: близкие (≤ 56 px на экране) собираются вместе; кластер стоит в середине своих мест.
      const fresh = [];
      pool.forEach((m) => {
        const p = map.project(m.item.anchor);
        if (p.x < -40 || p.y < -40 || p.x > host.width + 40 || p.y > host.height + 40) { result.set(m, ["hidden", m.spot || m.item.anchor]); return; }
        const c = fresh.find((q) => Math.hypot(q.seed.x - p.x, q.seed.y - p.y) <= CLUSTER_R);
        if (c) { c.members.push(m); c.pts.push(p); } else fresh.push({ seed: p, members: [m], pts: [p] });
      });
      S.clusters.filter((c) => !keptClusters.includes(c)).forEach((c) => c.marker.remove());
      const clusters = keptClusters.slice();
      fresh.forEach((c) => {
        const cx = c.pts.reduce((a, q) => a + q.x, 0) / c.pts.length, cy = c.pts.reduce((a, q) => a + q.y, 0) / c.pts.length;
        const keys = c.members.map((m) => keyOf(m.item.target));
        const el = makeClusterEl(c.members.map((m) => m.item));
        // Размер кружка зависит только от длины числа: меряем один раз на длину (каждый замер нового элемента —
        // пересчёт раскладки страницы; при 1 000 целях «Хроника» строит десятки кластеров каждый день).
        const kind = (el.querySelector(".r07-cluster--fixed") ? "f" : "") + String(el.textContent || "").length;   // ✓ шире
        if (!S.clusterSize[kind]) S.clusterSize[kind] = [el.offsetWidth || CLUSTER_W, el.offsetHeight || CLUSTER_W];
        const [w, h] = S.clusterSize[kind];
        // в середине; тесно — рядом (кольцо 26 и 48 px); совсем некуда — к ближайшему уже стоящему кластеру.
        // Кружок одного места — только на самом месте: сдвинутый, он показывал бы не туда (и выбор места жалобой мимо).
        const tries = [[0, 0]];
        if (c.members.length > 1) for (const r of [26, 48]) for (let k = 0; k < 8; k++) tries.push([r * Math.cos((k * Math.PI) / 4), r * Math.sin((k * Math.PI) / 4)]);
        const at = tries.map(([dx, dy]) => ({ x: cx + dx, y: cy + dy })).find((q) => free(boxAt(q, w, h)));
        if (!at) {
          const near = clusters.filter((q) => q.fresh).sort((a, b) => Math.hypot(a.px.x - cx, a.px.y - cy) - Math.hypot(b.px.x - cx, b.px.y - cy))[0];
          el.remove();
          if (near && Math.hypot(near.px.x - cx, near.px.y - cy) < 120) {
            near.members.push(...keys);
            c.members.forEach((m) => result.set(m, ["cluster", m.spot || m.item.anchor]));
          } else {
            // у самого края или под плашкой (легенда, панель) — не рисуем обрезанным: появится при сдвиге карты
            c.members.forEach((m) => result.set(m, ["hidden", m.spot || m.item.anchor]));
          }
          return;
        }
        const q = at;
        const ll = map.unproject([q.x, q.y]);
        const marker = new window.maplibregl.Marker({ element: el, anchor: "center" }).setLngLat(ll).addTo(map);
        placed.push(boxAt(q, w, h));
        const cl = { key: "cluster:" + (++S.clusterSeq), marker, el, members: keys, ll: [ll.lng, ll.lat], w, h, px: q, fresh: true };
        el.dataset.key = cl.key;
        clusters.push(cl);
        c.members.forEach((m) => result.set(m, ["cluster", m.spot || m.item.anchor]));
      });
      clusters.forEach((c) => {
        c.fresh = false;
        if (c.el.dataset.n !== String(c.members.length)) fillCluster(c.el, c.members.map((k) => S.markers.get(k)).filter(Boolean).map((m) => m.item));
        c.el.classList.toggle("r07-badge--pick", !!S.picking);
        c.el.tabIndex = -1;
      });
      S.clusters = clusters;
      list.forEach((m) => {
        const [mode, spot] = result.get(m) || ["hidden", m.spot || m.item.anchor];
        if ((mode === "full" || mode === "mini") && (spot[0] !== m.spot?.[0] || spot[1] !== m.spot?.[1])) { m.marker.setLngLat(spot); m.spot = spot; }
        // Пишем только изменившееся: у 1 000 значков каждая лишняя запись — пересчёт их стилей
        const hide = mode === "hidden" || mode === "cluster";
        // Скрытый значок (в кластере, вне места) — не на карте: MapLibre двигает каждый маркер на каждом кадре
        // перемещения, а при 1 000 целях видно ~50. Показали — вернули на карту (тот же элемент и обработчики).
        if (!hide && m.attached === false) { m.marker.addTo(map); m.attached = true; }
        if (!hide && m.dirty) { fillBadge(m.el, m.item); m.sig = m.dirty; m.dirty = null; }   // хроника: дорисовать перед показом
        if (m.el.hidden !== hide) m.el.hidden = hide;
        if (hide && m.attached !== false) { m.marker.remove(); m.attached = false; }
        m.el.classList.toggle("r07-badge--mini", mode === "mini");
        if (m.el.tabIndex !== -1) m.el.tabIndex = -1;
        if (m.el.dataset.mode !== mode) m.el.dataset.mode = mode;
      });
      if (full) S.layout = { z, bearing, pitch, w: host.width, h: host.height };
      // Значки — одна остановка Tab (R10 B-025): внутрь входит Tab, между значками — стрелки (самый горячий первый).
      const order = list.filter((m) => m.el.dataset.mode === "full" || m.el.dataset.mode === "mini").map((m) => keyOf(m.item.target));
      S.badgeOrder = order.concat(clusters.map((c) => c.key));
      const roving = S.badgeOrder.includes(S.rovingKey) ? S.rovingKey : S.badgeOrder[0];
      const node = roving && nodeFor(roving);
      if (node) node.tabIndex = 0;
    }

    const nodeFor = (key) => (S.markers.get(key) || S.clusters.find((c) => c.key === key) || {}).el || null;

    // Кружок-кластер: число людей во всех его местах, цвет — самого высокого уровня (исправленные — зелёным, только
    // если в кластере одни исправленные). Это тоже .r07-badge: на карте не появляется новый вид значков.
    function makeClusterEl(items) {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "r07-badge r07-badge--cluster";
      el.tabIndex = -1;
      el.addEventListener("click", (ev) => { ev.stopPropagation(); onClusterClick(el, ev); });
      el.addEventListener("keydown", (ev) => onBadgeKey(el.dataset.key, ev));
      bindTip(el, () => clusterTip(el));
      fillCluster(el, items);
      map.getContainer().append(el);   // чтобы измерить размер до установки маркера
      return el;
    }
    function clusterTop(items) {
      const active = items.filter((it) => it.state !== "fixed");
      return (active.length ? active : items).slice().sort((a, b) => (b.weight || 0) - (a.weight || 0) || (b.count || 0) - (a.count || 0))[0];
    }
    // Число на кластере — люди только по открытым местам (как число района и «Обращения»): исправленное место своего
    // числа на карте не показывает, и в кластере его прошлые жалобы не складываются. Одни исправленные — ✓ и число мест.
    const activePeople = (items) => items.reduce((a, it) => a + (it.state === "fixed" ? 0 : Number(it.count) || 0), 0);
    function fillCluster(el, items) {
      const top = clusterTop(items);
      const people = activePeople(items);
      const allFixed = items.every((it) => it.state === "fixed");
      el.dataset.level = allFixed ? "fixed" : String(top.level);
      el.dataset.n = String(items.length);
      el.style.setProperty("--r07-c", top.color || "#999");
      const places = t("heat.cluster.places", { count: items.length });
      el.setAttribute("aria-label", items.length === 1
        ? t("heat.badge_label", { target: label(top.target), reported: t(allFixed ? "heat.reported_fixed" : "heat.reported", { count: top.count }) }) + ". " + t("heat.cluster.zoom")
        : allFixed ? t("heat.cluster.fixed_label", { places })
          : t("heat.cluster.label", { places, people: t("heat.tip.people", { count: people }) }));
      const body = allFixed ? svgIcon("check", 14) + (items.length > 1 ? "<span>" + fmtNum(items.length) + "</span>" : "") : fmtNum(people);
      el.innerHTML = '<span class="r07-badge__inner"><span class="r07-cluster' + (allFixed ? " r07-cluster--fixed" : "") + '" style="--r07-c:' + esc(top.color || "#999") + '">' + body + "</span></span>";
    }
    function clusterItems(el) {
      const c = S.clusters.find((q) => q.el === el);
      return c ? c.members.map((k) => S.markers.get(k)).filter(Boolean).map((m) => m.item) : [];
    }
    function clusterTip(el) {
      const items = clusterItems(el);
      if (items.length === 1) return badgeTip(items[0]);
      const places = t("heat.cluster.places", { count: items.length });
      if (items.every((it) => it.state === "fixed")) return t("heat.cluster.fixed_tip", { places });
      return t("heat.cluster.tip", { places, people: t("heat.tip.people", { count: activePeople(items) }) });
    }
    // Нажатие на кластер — приблизить к его местам (не меньше 15-го масштаба, если в нём объекты: там они видны поштучно).
    function onClusterClick(el, ev) {
      hideTip();
      const items = clusterItems(el);
      if (!items.length || !map) return;
      // Житель выбирает место для жалобы: кружок одного места — это само место (как значок), нескольких — приблизить
      if (isPicking() && items.length === 1) { forwardPick(keyOf(items[0].target), ev); return; }
      let w = 180, so = 90, e = -180, n = -90;
      items.forEach((it) => { const a = it.anchor; w = Math.min(w, a[0]); e = Math.max(e, a[0]); so = Math.min(so, a[1]); n = Math.max(n, a[1]); });
      const need = items.some((it) => it.target.kind === "object") ? 15.2 : map.getZoom() + 1;
      let cam = null;
      try { cam = map.cameraForBounds([[w, so], [e, n]], { padding: fitPaddingNow(), maxZoom: 17, bearing: map.getBearing() }); } catch (err) { cam = null; }
      const center = cam ? cam.center : [(w + e) / 2, (so + n) / 2];
      const zoom = Math.max(cam ? cam.zoom : 0, need, map.getZoom() + 1);
      map.easeTo({ center, zoom: Math.min(zoom, 18), duration: moveMs(600) });
      if (ev && ev.detail === 0) setTimeout(() => { const first = S.badgeOrder && S.badgeOrder[0]; const nd = first && nodeFor(first); if (nd) nd.focus({ preventScroll: true }); }, moveMs(650) + 50);
    }

    function onBadgeKey(key, ev) {
      const order = S.badgeOrder || [];
      const i = order.indexOf(key);
      if (i < 0) return;
      const moves = { ArrowRight: i + 1, ArrowDown: i + 1, ArrowLeft: i - 1, ArrowUp: i - 1, Home: 0, End: order.length - 1 };
      if (!(ev.key in moves)) return;
      ev.preventDefault();
      ev.stopPropagation();   // стрелки не двигают карту
      const next = order[(moves[ev.key] + order.length) % order.length];
      order.forEach((k) => { const el = nodeFor(k); if (el) el.tabIndex = k === next ? 0 : -1; });
      S.rovingKey = next;
      nodeFor(next)?.focus({ preventScroll: true });
    }

    // Житель выбирает место для жалобы (оболочка ставит body.birge-picking, мастер R09 — html.bc-picking и слушает
    // щелчок по карте). Тогда значок не открывает карточку, а передаёт карте щелчок в точке своей цели: житель нажал
    // на «13» у остановки — мастер получает саму остановку (UX_REVIEW R11 B1 п. 3, R10 B-019, LOCAL_B2 P1).
    // Новый R09 ловит нажатие по маркерам сам (фаза захвата) — тогда сюда событие не доходит, двойного выбора нет.
    const isPicking = () => S.picking || document.body.classList.contains("birge-picking") ||
      document.documentElement.classList.contains("bc-picking");

    // Карта у инструмента (R12 INTEGRATION §11; контракт R04: пока редактор рисует, щелчок по карте — только редактору).
    // Редактор R04 рисует участок (html[data-civic-editor-tool], CivicEditor.isDrawing() — держатся до конца щелчка, которым
    // инструмент закончился), сценарий выбирает перекрытие (civic-scenarios:tool), ставят 3D-проект (civic-build3d:tool,
    // .b3d-dock[data-state=placing]), выбирают место идеи (body.ri-picking). Тогда цель R07 не открывает карточку и не ставит
    // «руку» поверх крестика, а значки пропускают нажатие к карте (heat.css .r07-map-tool): точка — там, где нажали.
    const TOOL_EVENTS = ["civic-editor:tool", "civic-scenarios:tool", "civic-build3d:tool"];
    const toolOwners = new Map();   // событие → элемент, объявивший инструмент; элемент снят со страницы — инструмента нет
    function mapTool() {
      for (const [type, el] of toolOwners) {
        if (el && el.isConnected === false) toolOwners.delete(type);
        else return true;
      }
      let drawing = false;
      try { drawing = !!(window.CivicEditor && typeof window.CivicEditor.isDrawing === "function" && window.CivicEditor.isDrawing()); } catch (e) { drawing = false; }
      const on = drawing || document.documentElement.hasAttribute("data-civic-editor-tool") ||
        document.body.classList.contains("ri-picking") || !!document.querySelector(".b3d-dock[data-state='placing']");
      // панель инструмента сняли без «выключения» — значки снова ловят нажатие с первого же наведения или щелчка
      if (!on && map && !S.destroyed) map.getContainer().classList.remove("r07-map-tool");
      return on;
    }
    function onToolEvent(ev) {
      if (ev.detail && ev.detail.active) toolOwners.set(ev.type, ev.target);
      else toolOwners.delete(ev.type);
      if (!map || S.destroyed) return;
      const on = mapTool();
      map.getContainer().classList.toggle("r07-map-tool", on);
      if (on) hideTip();
      syncCursor();
    }

    function forwardPick(key, ev) {
      const m = S.markers.get(key);
      const it = m && m.item;
      if (!it || !map || !window.maplibregl) return;
      const ll = it.target.kind === "object" ? it.anchor : (m.spot || it.anchor);   // участок, двор — место значка
      if (it.target.kind === "district") {   // район — не место жалобы: только приблизить (как у R09)
        map.easeTo({ center: ll, zoom: Math.max(map.getZoom() + 2, 13), duration: moveMs(600) });
        return;
      }
      const lngLat = new window.maplibregl.LngLat(ll[0], ll[1]);
      map.fire("click", { lngLat, point: map.project(lngLat), originalEvent: ev });
    }

    function onBadgeClick(key, ev) {
      if (isPicking()) { forwardPick(key, ev); return; }
      if (mapTool()) return;   // карта у инструмента: мышью значок нажатие пропускает (heat.css), Enter — тоже не карточка
      const it = findItem(key);
      if (!it) return;
      if (R.on) {
        if (map && it.anchor) map.easeTo({ center: it.anchor, zoom: Math.max(map.getZoom() + 1.5, it.target.kind === "district" ? 13 : 15), duration: moveMs(600) });
        return;
      }
      if (it.target.kind === "district") {
        map.easeTo({ center: it.anchor, zoom: 13, duration: moveMs(700) });
        return;
      }
      select(key, false);
    }

    function select(key, moveMap) {
      showPlace(null);
      S.selected = key;
      updateSelectionLayer();
      for (const [k, m] of S.markers) m.el.classList.toggle("r07-badge--selected", k === key);
      hideTip();
      const it = findItem(key);
      if (it && moveMap && map && it.anchor) {
        // Плавно и только по просьбе пользователя (клик в списке). Наклон и поворот не трогаем.
        map.easeTo({ center: it.anchor, zoom: Math.max(map.getZoom(), it.target.kind === "object" ? 16 : 15), offset: freeOffset(), duration: moveMs(600) });
      }
      render();
      declutter();
      void loadTexts(key);
      void loadMerged(key);
      const heading = panel.querySelector(".r07-card__title");
      if (heading) heading.focus({ preventScroll: true });
      root.dispatchEvent(new CustomEvent("birge:heat-select", { bubbles: true, detail: { target: it ? it.target : null } }));
    }

    // Пульс-кольцо на цели при новой жалобе
    function pulse(key) {
      const it = findItem(key);
      if (!map || !it || !it.anchor || !window.maplibregl) return;
      const el = document.createElement("div");
      el.className = "r07-pulse";
      el.style.setProperty("--r07-c", it.color || "#E24B4A");
      const marker = new window.maplibregl.Marker({ element: el, anchor: "center" }).setLngLat(it.anchor).addTo(map);
      setTimeout(() => marker.remove(), 2200);   // два кольца по --t-heat 800 мс, второе — через 0,4 с
      srBox.textContent = t("heat.toast_new", { target: label(it.target) }) + ". " + t("heat.reported", { count: it.count });
    }

    // ----- действия -----
    async function post(path, body) {
      // X-Birge-Device — как у формы R09 (её API берёт id устройства из этого заголовка).
      const headers = { "Content-Type": "application/json", Accept: "application/json", "X-Birge-Device": deviceId() };
      const res = await fetchFn(apiBase + path, { method: "POST", headers, body: JSON.stringify(body || {}) });
      if (!res.ok) { const err = new Error("HTTP " + res.status); err.status = res.status; throw err; }
      try { return await res.json(); } catch (e) { return null; }
    }
    // Ошибка действия: что случилось + что сделать. Лимит (429) и нет входа (401/403) — без «Повторить»: повтор не поможет
    // (R15 U1). Остальное — «Проверьте связь» с кнопкой «Повторить».
    // retry — повтор того же действия с ТЕКУЩЕЙ кнопкой: панель могла перерисоваться (язык, Esc, новая жалоба).
    function actionFailed(e, retry) {
      // 404 — не «проверьте связь»: обращения уже нет; сообщение обычное (перезагрузка карты его не закрывает)
      if (e && e.status === 404) { toast(t("heat.not_found")); void load("event"); return; }
      if (e && (e.status === 409 || e.status === 422)) { toast(t("heat.already_changed")); void load("event"); return; }
      if (e && e.status === 429) toast(t("heat.too_many"), "error");
      else if (e && (e.status === 401 || e.status === 403)) toast(t("heat.need_login"), "error");
      else toast(t("heat.action_failed"), "error", { label: t("heat.retry"), onClick: retry });
    }
    // Кнопка действия в панели сейчас (или временная — тогда занятость просто не видна) и та же цель по ключу.
    const actButton = (act) => panel.querySelector('[data-act="' + act + '"]') || document.createElement("button");
    async function setStatus(it, status, btn) {
      // После перезагрузки у цели могли остаться только примеры или всё уже исправлено — тогда отправлять нечего
      // (иначе «Взято в работу» без единого запроса): просто перерисовать карточку.
      if (!(it.open_ids || []).length) { render(); return; }
      btn.setAttribute("aria-busy", "true");
      btn.disabled = true;
      // Мгновенный отклик (README эталона, правило 4): «В работе» видно сразу — в карточке, строке и на значке; сервер —
      // следом, затем перезагрузка сверяет данные; ошибка — откат той же перезагрузкой и «Повторить».
      const optimistic = status === "in_progress" && it.state === "active";
      if (optimistic) {
        const key = keyOf(it.target);
        for (const x of [].concat(S.data ? S.data.items : [], S.top || [])) if (keyOf(x.target) === key) x.status = "in_progress";
        render();
        // значки — в следующем кадре: карточка и строка показываются сразу, не дожидаясь перерисовки карты (WebGL)
        (window.requestAnimationFrame || setTimeout)(() => { if (!S.destroyed) drawBadges(); });
      }
      try {
        // У отдельного обращения 404 (нет в хранилище — пример R07 в общей сборке) или 409/422 (уже в этом статусе)
        // не обрывают остальные (R12, находка шага 6 демо); ошибка — только если не обновилось ни одно.
        let done = 0, skipped = null;
        for (const id of it.open_ids || []) {
          try { await post("/complaints/" + encodeURIComponent(id) + "/status", { status }); done += 1; }
          catch (e) { if (e && (e.status === 404 || e.status === 409 || e.status === 422)) { skipped = e; continue; } throw e; }
        }
        if (!done && skipped) throw skipped;
        toast(status === "fixed" ? t("heat.toast_fixed") : t("heat.toast_taken"));
        await load("event");
      } catch (e) {
        if (optimistic) await load("event").catch(() => {});   // откат: данные сервера
        actionFailed(e, () => {
          const cur = findItem(keyOf(it.target));
          if (cur) void setStatus(cur, status, actButton(status === "fixed" ? "fixed" : "take"));
        });
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
      }
    }
    // R09 в карточке цели (волна 2, IA_WAVE2 §2.2–2.4), только у сотрудника:
    //  - «Отметить исправленным» открывает форму R09 «Сообщить жителям» (что сделали + фото «после», «Увидят N человек»);
    //    пока она открыта, кнопки карточки скрыты (одна главная кнопка);
    //  - под кнопками — паспорт решения («Изменить» → 3 поля) и «Обновление для всех» R09 без своей главной кнопки.
    // Перерисовка карточки (язык, новое событие) открывает их снова. Без R09 на странице — карточка как раньше.
    function mountR09() {
      const it = S.selected && findItem(S.selected);
      const actions = panel.querySelector(".r07-actions");
      const R09 = window.BirgeComplaintStaff;
      if (!it || !actions || !R09 || !(it.open_ids || []).length) { S.fixFor = null; return; }
      if (S.fixFor && S.fixFor === S.selected && typeof R09.fixForm === "function") {
        // R09 M5: на телефоне тост «Взято в работу» (3–4 с) лежал на форме «Что сделали» — форма открылась, тост больше не нужен
        if (S.okToast) { try { S.okToast.close(); } catch (e) { /* уже закрыт */ } S.okToast = null; }
        actions.hidden = true;
        const holder = document.createElement("div");
        holder.className = "r07-fixform";
        actions.after(holder);
        R09.fixForm(holder, {
          complaintIds: it.open_ids,
          onDone: async () => { S.fixFor = null; toast(t("heat.toast_fixed")); await load("event"); },
          onCancel: () => { S.fixFor = null; render(); },
        });
        return;
      }
      S.fixFor = null;
      if (S.role === "akimat" && typeof R09.mount === "function") {
        const box = document.createElement("div");
        box.className = "r07-r09staff";
        // эталон A: вкладки — сразу под кнопками; паспорт решения и «Обновление для всех» R09 — во вкладке «Обзор»
        const overview = panel.querySelector("#r07-tp-overview");
        if (overview) overview.appendChild(box); else actions.after(box);
        R09.mount(box, { complaintId: it.open_ids[0], fix: false, compact: true, staffOnly: true });
      }
    }
    // «Я тоже» — оптимистично (эталон A, правило Linear 4): кнопка сразу «Вы уже отметились» и «Спасибо…», запрос — следом;
    // ошибка — откат кнопки и прежнее «Не получилось — Повторить». Число людей приходит с сервера (load), без догадок.
    async function metoo(it, btn) {
      const id = (it.open_ids || [])[0];
      if (!id) return;
      const key = keyOf(it.target);
      if (btn) { btn.setAttribute("aria-busy", "true"); btn.disabled = true; }
      rememberMetoo(key);
      render();
      toast(t("heat.toast_metoo"));
      try {
        await post("/complaints/" + encodeURIComponent(id) + "/metoo", { device_id: deviceId() });
        await load("event");
        pulse(key);
      } catch (e) {
        if (!(e && e.status === 409)) { rememberMetoo(key, false); render(); }   // 409 — это устройство уже отметилось
        actionFailed(e, () => {
          const cur = findItem(key);
          if (cur) void metoo(cur, actButton("metoo"));
        });
      }
    }

    // ----- панель -----
    function render() {
      if (S.destroyed) return;
      root.dataset.role = S.role;
      const parts = [];
      const cardItem = S.selected && findItem(S.selected);
      root.dataset.view = cardItem ? "card" : "list";
      // Чистый дизайн (R11 CLEAN_PASS, R07 №4): шапка «Карта жалоб / Больше всего жалоб: …» и фильтры — только у списка.
      // В карточке одна навигация «‹ Горячие места ✕»; кнопки действий видны без прокрутки. Пока данных нет (загрузка,
      // нет связи) — фильтров тоже нет: на телефоне в шторке сразу видно скелетон или «Нет связи · Повторить».
      // Список «Горячие места» (эталон A + Linear): заголовок, чипы тем, период и группы по статусу — одна секция (listHtml);
      // пока данных нет (скелет, «нет связи») — только заголовок над ними.
      if (R.on) {   // значки уже разложены drawBadges этого же дня — второй раскладки не нужно
        panel.innerHTML = replayListHtml() + footnoteHtml(null);
        bindReplayList();
        return;
      }
      if (!cardItem && !S.data) parts.push(listHeadHtml());
      if (S.status === "loading" && !S.data) parts.push(skeletonHtml());
      else if ((S.status === "error" || S.status === "not_ready") && !S.data) parts.push(errorHtml());
      else parts.push(cardItem ? cardHtml(cardItem) : listHtml());
      // «Данные — пример» — одна серая строка внизу панели, не плашка сверху (CLEAN_PASS R07 №5)
      parts.push(footnoteHtml(cardItem));
      // Легенда — на карте (в оболочке — под «?» её строки, opts.legendContainer). Без карты (страница-список) — в панели.
      if (map) renderMapLegend(); else parts.push(legendHtml(false));
      panel.innerHTML = parts.join("");
      // Карточка и список не «выскакивают»: при смене вида (список → карточка, карточка → другая, назад к списку) —
      // мягкий вход 240 мс (дизайн-марафон №7); перерисовка того же вида (тексты пришли, язык) — без анимации.
      const view = cardItem ? "card:" + S.selected : S.data ? "list" : S.status;
      if (S.lastView && S.lastView !== view && S.data) panel.querySelector(".r07-card, .r07-hot, .r07-empty")?.classList.add("r07-enter");
      S.lastView = view;
      if (S.textsFresh) {   // цитаты только что пришли на место скелета — мягкое проявление
        if (cardItem && S.textsFresh === textsKey(S.selected)) panel.querySelector(".r07-texts .r07-quotes")?.classList.add("r07-enter");
        S.textsFresh = null;
      }
      bindPanel();
      mountR09();
      if (map) declutter();   // легенда могла сменить размер (язык, режим) — значки не должны оказаться под ней
    }

    function footnoteHtml(it) {
      if (!S.data) return "";
      // У места одни примеры: та же строка внизу, второй фразой — «статус примеров не меняется» (R10 B-037)
      if (it && examplesOnly(it)) return '<p class="bk-footnote r07-footnote r07-note--demo">' + esc(t("heat.example_readonly")) + "</p>";
      return S.data.demo || (S.meta && S.meta.demo) ? '<p class="bk-footnote r07-footnote">' + esc(t("common.demo_footnote")) + "</p>" : "";
    }

    function renderMapLegend() {
      const host = opts.legendContainer || (map && map.getContainer());
      if (!host) return;
      if (!S.legendEl || !S.legendEl.isConnected) {
        S.legendEl = document.createElement("section");
        S.legendEl.className = "r07-maplegend r07-root";
        host.append(S.legendEl);
      }
      S.legendEl.dataset.role = S.role;
      S.legendEl.classList.toggle("r07-maplegend--more", Boolean(opts.legendContainer));
      S.legendEl.classList.toggle("bk-glass", Boolean(opts.legendContainer));   // GLASS §2: легенда — стекло (ui-kit)
      const html = legendHtml(true);
      S.legendEl.innerHTML = html;
      S.legendEl.hidden = !html;   // нет данных (нет связи) — не пустая белая плашка над картой (R10 B-034)
    }

    // Заголовок списка (эталон: 19/600 как у листа «Проекты и идеи»), «за 30 дней» серым; «Сбросить» — когда фильтры
    // изменены; × — если оболочка показывает список закрываемой карточкой (opts.closable, событие birge:heat-close).
    // opts.closable === "desktop" (R01 INTEGRATION §26.12): × только на ноутбуке — на телефоне список в шторке, × скрыт CSS.
    function listHeadHtml() {
      const dirty = S.filters.category || S.filters.district || S.filters.days !== ((S.meta && S.meta.default_days) || 30);
      const reset = dirty && (S.top || []).length ? '<button type="button" class="r07-link r07-reset" data-reset>' + esc(t("heat.reset")) + "</button>" : "";
      const close = opts.closable ? '<button type="button" class="r07-x' + (opts.closable === "desktop" ? " r07-x--desktop" : "") + '" data-close aria-label="' + esc(t("heat.close")) + '" title="' + esc(t("heat.close")) + '">' + svgIcon("close", 16) + "</button>" : "";
      return '<header class="r07-lhd"><h2 class="r07-h" id="r07-hot-h">' + esc(t("heat.hot_title")) + '</h2><span class="r07-muted r07-lhd__days">' +
        esc(keep(t("heat.for_days", { count: S.filters.days }))) + "</span>" + reset + close + "</header>";
    }
    function filtersHtml() {
      // Темы — ряд чипов (эталон .chip: 34 px, 14/500, точка цвета самого горячего места темы; выбранный — тёмный),
      // ряд листается вбок с мягким краем (.bk-scroll-x). Темы, где сейчас есть горячие места, — первыми. Первый чип —
      // «Все категории» (шаг 3б сценария R10). Когда оболочка R01 ставит свои чипы под поиском — opts.categoryChips: false.
      const hottest = new Map();
      (S.top || []).forEach((it) => { const c = Object.keys(it.by_category || {})[0]; if (c && !hottest.has(c)) hottest.set(c, it); });
      const metaCats = (S.meta ? S.meta.categories : []).slice();
      metaCats.sort((a, b) => (hottest.has(b.id) ? 1 : 0) - (hottest.has(a.id) ? 1 : 0));
      const dot = (c) => { const it = hottest.get(c); return it ? '<span class="r07-chip__dot" data-level="' + esc(it.level) + '"></span>' : ""; };
      const cats = metaCats.map((c) =>
        '<button type="button" class="r07-chip" data-cat="' + esc(c.id) + '" aria-pressed="' + (S.filters.category === c.id) + '"><span class="r07-chip__pill">' +
        dot(c.id) + "<span>" + esc(S.lang === "kk" ? c.kk : c.ru) + "</span></span></button>").join("");
      const all = '<button type="button" class="r07-chip" data-cat="" aria-pressed="' + (!S.filters.category) + '"><span class="r07-chip__pill"><span>' + esc(t("heat.category_all")) + "</span></span></button>";
      const periods = ((S.meta && S.meta.periods) || [7, 30, 90]).map((d) =>
        '<button type="button" data-days="' + d + '" aria-pressed="' + (S.filters.days === d) + '">' + esc(t("heat.days", { count: d })) + "</button>").join("");
      // Район — в поиске шапки оболочки (CLEAN_PASS R01 №2, R07 №6); свой список районов — только по opts.districtFilter
      // (страница без оболочки, demo.html) или если район уже выбран (чтобы его можно было снять).
      const showDistrict = opts.districtFilter === true || Boolean(S.filters.district);
      const districts = showDistrict ? ((S.meta && S.meta.districts) || []).slice().sort((a, b) => (a.ru > b.ru ? 1 : -1)).map((d) =>
        '<option value="' + esc(d.id) + '"' + (S.filters.district === d.id ? " selected" : "") + ">" + esc(S.lang === "kk" ? d.kk : d.ru) + "</option>").join("") : "";
      return '<div class="r07-filters" role="group" aria-label="' + esc(t("heat.filters")) + '">' +
        (opts.categoryChips === false ? "" : '<div class="r07-chips bk-scroll-x" id="r07-cats" role="group" aria-label="' + esc(t("heat.category_all")) + '">' + all + cats + "</div>") +
        '<div class="r07-frow"><div class="r07-seg bk-seg" role="group" aria-label="' + esc(t("heat.period")) + '">' + periods + "</div>" +
        (showDistrict ? '<label class="r07-select"><span class="r07-vh">' + esc(t("heat.district")) + '</span><select class="r07-field" data-district aria-label="' + esc(t("heat.district")) + '"><option value="">' + esc(t("heat.district_all")) + "</option>" + districts + "</select></label>" : "") +
        "</div></div>";
    }

    // Пункты легенды волны 2 — только по делу (R11 IA_WAVE2 §3): «сообщили об устранении», когда такая цель видна на
    // карте; «нет свежих данных», когда на обзоре города есть серые районы. На первом кадре легенда та же (5 пунктов).
    // В оболочке подробная легенда открывается «?» строки «мало ▬ много · ✓ исправлено» (CLEAN_PASS R01 №6) — там
    // показываем все состояния сразу: человек сам спросил, что значат цвета.
    function legendExtras() {
      if (!S.data) return { reported: false, nodata: false, verified: false };
      if (opts.legendContainer) return { reported: true, nodata: true, verified: true };
      let inView = () => true;
      if (map) {
        const b = map.getBounds();
        inView = (it) => it.anchor && b.contains(it.anchor);
      }
      return {
        reported: S.data.items.some((it) => it.state === "fixed" && it.fixed_kind === "reported" && inView(it)),
        nodata: S.mode === "districts" && S.data.items.some((it) => it.state === "no_data"),
        verified: false,
      };
    }
    function legendHtml(onMap) {
      const lg = (S.data && S.data.legend) || (S.meta && S.meta.legend);
      if (!lg) return "";
      const ex = legendExtras();
      const st = lg.states || {};
      // Рядом с пунктиром «сообщили об устранении» сплошной зелёный — это «проверено жителями» (heat_states.verified_fixed
      // в categories_v2.json): без пунктира — короткое «исправлено», как в строке легенды оболочки.
      const fixedLabel = ex.verified || ex.reported ? t("heat.legend.verified") : S.lang === "kk" ? lg.fixed.kk : lg.fixed.ru;
      const rows = lg.levels.filter((lv) => lv.level > 0).map((lv) =>
        '<li><i class="r07-sw" style="background:' + esc(lv.color) + '"></i>' + esc(legendLabel(lv)) + "</li>").join("") +
        (ex.reported && st.reported_fixed ? '<li data-extra="reported"><i class="r07-sw r07-sw--dashed" style="background:' + esc(st.reported_fixed.color) + '"></i>' + esc(t("heat.legend.reported_fixed")) + "</li>" : "") +
        '<li><i class="r07-sw" style="background:' + esc(lg.fixed.color) + '"></i>' + esc(fixedLabel) + "</li>" +
        (ex.nodata && st.no_data ? '<li data-extra="nodata"><i class="r07-sw" style="background:' + esc(st.no_data.color) + '"></i>' + esc(t("heat.legend.nodata")) + "</li>" : "");
      const zoomHint = S.mode === "districts" ? '<p class="r07-legend__hint r07-legend__zoom">' + esc(t("heat.zoom_hint")) + "</p>" : "";
      const nodataHint = ex.nodata && !opts.legendContainer ? '<p class="r07-legend__hint r07-legend__nodata">' + esc(t("heat.legend.nodata_hint")) + "</p>" : "";
      const inner = '<h3 class="r07-legend__title">' + esc(t("heat.legend")) + "</h3><ul>" + rows + '</ul><p class="r07-legend__hint r07-legend__fresh">' + esc(t("heat.legend_hint")) + "</p>" + nodataHint + zoomHint;
      S.legendKey = (ex.reported ? "r" : "") + (ex.nodata ? "n" : "");
      return onMap ? inner : '<section class="r07-legend" aria-label="' + esc(t("heat.legend")) + '">' + inner + "</section>";
    }

    // Скелетон — в форме того, что сейчас появится (поле темы, 7/30/90, строки «Горячих мест»), а не серые полосы.
    function skeletonHtml() {
      const row = '<span class="r07-skel__row"><i class="r07-skel__sq"></i><span class="r07-skel__lines"><i></i><i></i></span></span>';
      return '<div class="r07-skeleton" aria-busy="true" aria-label="' + esc(t("heat.loading")) + '"><i class="r07-skel__field"></i><i class="r07-skel__seg"></i>' +
        row + row + row + row + "</div>";
    }
    function errorHtml() {
      const notReady = S.status === "not_ready";
      // «Повторить» с ⟳ ui-kit — как у «нет связи» в остальных разделах (R11 §10.1)
      const ui = uiKit();
      const again = ui && typeof ui.icon === "function" ? ui.icon("refresh") : "";
      return '<div class="r07-error" role="alert">' + illo(notReady ? "not_ready" : "error") + '<p class="r07-error__title">' +
        esc(notReady ? t("heat.not_ready") : t("heat.error_title")) + "</p>" + (notReady ? "" : '<p class="r07-error__hint">' + esc(t("heat.error_hint")) + "</p>") +
        '<button type="button" class="r07-btn" data-retry>' + again + esc(t("heat.retry")) + "</button></div>";
    }

    function listHtml() {
      // Всегда места (и на мелком масштабе, где карта — районы): те же 10, что карта вписывает при открытии.
      const items = S.top || [];
      const head = listHeadHtml() + filtersHtml();
      // Районы: «Приблизьте карту…» — строкой на текущем языке (R11 ночь 4 п. 1, R10 B-038; видна только на телефоне —
      // на ноутбуке она в легенде). Под списком, а не над ним: на телефоне первая строка сразу под фильтрами, выше
      // кнопки «Сообщить о проблеме» (R10 INTEGRATION §10, эталон «Житель, телефон» — строки сразу под заголовком).
      const hint = S.mode === "districts" ? '<p class="r07-zoomhint">' + svgIcon("pin", 16) + esc(t("heat.zoom_hint")) + "</p>" : "";
      if (!items.length) {
        // Пусто ≠ «всё исправлено»: значок, «За 7 дней жалоб нет» и ОДНО действие (П1): с фильтром — «Сбросить фильтры»,
        // без фильтра — «Показать 30 дней» (№8).
        const filtered = Boolean(S.filters.category || S.filters.district);
        const next = (S.meta && S.meta.periods || [7, 30, 90]).find((d) => d > S.filters.days);
        const action = filtered ? '<button type="button" class="r07-btn r07-btn--primary" data-reset>' + esc(t("heat.filter.reset")) + "</button>"
          : next ? '<button type="button" class="r07-btn r07-btn--primary" data-days-next="' + next + '">' + esc(t("heat.empty.show_days", { n: next })) + "</button>" : "";
        return '<section class="r07-hot" aria-labelledby="r07-hot-h">' + head + '<div class="r07-empty" role="status">' + illo(filtered ? "empty_filtered" : "empty") + '<p class="r07-empty__title">' + esc(t("heat.empty.title", { n: S.filters.days })) +
          '</p><p class="r07-empty__hint">' + esc(t(filtered ? "heat.empty.hint_filters" : "heat.empty.hint")) + '</p><div class="r07-empty__actions">' + action + "</div></div>" + hint + "</section>";
      }
      // Строки как в Linear (README эталона, правило 5): 44 px — статус-иконка, число на плашке цвета места (эталон .cnt),
      // название 14/500 в одну строку, тема серым справа; группы по статусу «Новые» / «В работе». Порядок — по весу, как был.
      const row = (it, idx) => {
        const key = keyOf(it.target);
        const st = it.reopened ? "reopened" : it.status || "new";
        const busy = S.busyKey === key;   // перерисовка во время перелёта
        return '<li><button type="button" class="r07-item' + (busy ? ' r07-item--busy" aria-busy="true' : "") + '" data-key="' + esc(key) + '" data-idx="' + idx + '" tabindex="' + (idx === 0 ? 0 : -1) + '">' +
          statusIcon(st) + '<span class="r07-mini" data-level="' + esc(it.level) + '">' + fmtNum(it.count) + "</span>" +
          '<span class="r07-item__text"><span class="r07-item__title">' + esc(label(it.target)) + '</span><span class="r07-item__meta">' + esc(topicName(it)) + "</span></span>" +
          '<span class="r07-vh">' + esc(" · " + t("heat.people_short", { count: it.count })) + "</span></button></li>";
      };
      const isNew = (it) => it.reopened || !it.status || it.status === "new";
      const groups = [["new", t("heat.group.new"), items.slice(0, TOP_N).filter(isNew)], ["in_progress", t("heat.group.work"), items.slice(0, TOP_N).filter((it) => !isNew(it))]];
      let idx = 0;
      const body = groups.filter(([, , list]) => list.length).map(([st, name, list]) =>
        '<h3 class="r07-gh">' + statusIcon(st) + "<span>" + esc(name) + '</span><span class="r07-gh__n">' + fmtNum(list.length) + "</span></h3>" +
        '<ol class="r07-list">' + list.map((it) => row(it, idx++)).join("") + "</ol>").join("");
      // Смена статуса прямо из строки (Linear): одна плавающая кнопка у строки под мышью или в фокусе (вне строк — список
      // строк и их кнопки для сценария R10 не меняются); только у сотрудника и только у мест с обращениями, а не примерами.
      const quick = S.role === "akimat" ? '<button type="button" class="r07-quick" data-quick hidden></button>' : "";
      return '<section class="r07-hot" aria-labelledby="r07-hot-h">' + head + '<div class="r07-groups">' + body + "</div>" + hint + quick + "</section>";
    }

    // Статус места — один раз (CLEAN_PASS R07 №1, ui-kit .bk-statusline): точка + слово + одна строка пояснения.
    //  открытое — срок ответа акимату («Осталось 2 рабочих дня» / «Просрочено на 1 день») или ничего; «вернули жители» — ↺;
    //  служба сообщила — «12 окт · ждёт проверки жителями» (без «зелёным до …»: зелёный — только после проверки, R10 W2-1);
    //  проверено — «Подтвердили 3 жителя · На карте зелёным до 19 окт».
    function statusLineHtml(it) {
      const fixed = it.state === "fixed";
      const note = [];
      let st, word, overdue = false;
      if (fixed && it.fixed_kind === "reported") {
        st = "reported_fixed"; word = t("heat.status.reported_fixed");
        if (it.fixed_at) note.push(fmtDate(it.fixed_at, S.lang));
        note.push(note.length ? lcFirst(t("heat.reported_wait")) : t("heat.reported_wait"));
      } else if (fixed) {
        st = it.fixed_kind === "verified" ? "verified" : "fixed";
        word = t(st === "verified" ? "heat.status.verified" : "heat.fixed_word");
        if (st === "verified" && it.checks && it.checks.yes) note.push(t("heat.verified_note", { count: it.checks.yes }));
        if (it.fixed_until) note.push(t("heat.fixed_until", { date: fmtDate(it.fixed_until, S.lang) }));
      } else {
        st = it.reopened ? "reopened" : it.status || "new";
        word = t("heat.status." + (it.status || "new"));
        if (it.reopened) note.push("↺ " + t("heat.reopened_mark"));
        // Срок ответа (волна 1, п. 6) — только акимату и только у новых (R09: просрочено = никто не ответил, срок прошёл)
        const due = S.role === "akimat" && it.due && (it.status === "new" || it.due.overdue_days) ? it.due : null;
        if (due) {
          overdue = Boolean(due.overdue_days);
          note.push(due.overdue_days ? t("deadline.overdue", { n: due.overdue_days }) : due.workdays_left ? t("deadline.left", { n: due.workdays_left }) : t("deadline.today"));
        }
      }
      return '<div class="bk-statusline r07-statusline r07-st"><span class="bk-status r07-status" data-status="' + esc(st) + '">' + statusIcon(st) + esc(word) + "</span>" +
        (note.length ? '<span class="bk-statusline__note r07-statusline__note"' + (overdue ? ' data-overdue="true"' : "") + ">" + esc(note.join(" · ")) + "</span>" : "") + "</div>";
    }

    // Блок «Подробнее» карточки — <details> ui-kit; пустые блоки не рисуются вовсе (CLEAN_PASS R07 №3)
    function detailsHtml(cls, title, body, open) {
      // Раскрытый или свёрнутый человеком блок остаётся таким, когда карточка перерисовывается (пришли тексты, новая жалоба)
      const k = S.selected + "|" + cls;
      const isOpen = S.detailsOpen.has(k) ? S.detailsOpen.get(k) : open;
      return '<details class="bk-details r07-details ' + cls + '" data-dk="' + esc(k) + '"' + (isOpen ? " open" : "") + '><summary class="r07-h4">' + title + "</summary>" + body + "</details>";
    }

    // Карточка «Выбран объект» — как в эталоне A (research/round-14/design/REFERENCE.html, .card): плитка с иконкой
    // категории, название 19/600, «вид места · район», × справа; крупное число людей; статус одной строкой (статус-иконка +
    // слово, справа серым срок/дата); одна главная кнопка и вторая серая; вкладки «Обзор · Обращения · История».
    // «Карточка = 5 секунд»: подробности — во вкладках, цитаты не длиннее 2 строк.
    function cardHtml(it) {
      const fixed = it.state === "fixed";
      const key = keyOf(it.target);
      let actions = "";
      if (!examplesOnly(it) && !fixed && S.role === "akimat") {
        // Одна главная кнопка: у нового — «Взять в работу», «Отметить исправленным» рядом серой; в работе — только она.
        const inWork = it.status === "in_progress";
        actions = (!inWork ? '<button type="button" class="r07-btn r07-btn--primary" data-act="take">' + esc(t("heat.take")) + "</button>" : "") +
          (inWork ? '<button type="button" class="r07-btn r07-btn--primary" data-act="fixed">' + esc(t("heat.mark_fixed")) + "</button>"
            // эталон A: вторая кнопка рядом с главной и короче её (240 + 102) — у нового места «✓ Исправлено» (слово статуса),
            // полная подпись — в подсказке; «Отметить исправленным» целиком — главная кнопка места «В работе»
            : '<button type="button" class="r07-btn" data-act="fixed" title="' + esc(t("heat.mark_fixed")) + '">' + svgIcon("check", 18) + esc(t("heat.status.fixed")) + "</button>");
      } else if (!examplesOnly(it) && !fixed && S.role === "resident") {
        actions = metooDone(key)
          ? '<button type="button" class="r07-btn" disabled>' + svgIcon("check", 18) + esc(t("heat.metoo_already")) + "</button>"
          : '<button type="button" class="r07-btn r07-btn--primary" data-act="metoo">' + svgIcon("users", 20) + esc(t("heat.metoo")) + "</button>";
      }
      // «Примерное место» — словами здесь (CLEAN_PASS R07 №2); если оно уже в названии — «Область на карте»
      const kindWord = !it.approximate ? t("heat.kind." + (it.target.subtype || it.target.kind))
        : label(it.target) === t("heat.approx_short") ? t("heat.kind.approximate") : t("heat.approx_short");
      const eyebrow = [kindWord, distName(it.district)].filter(Boolean).map(esc).join(" · ") +
        (it.demo ? ' · <span class="r07-tag">' + esc(t("heat.demo_tag")) + "</span>" : "");
      const cats = Object.entries(it.by_category || {});
      const topCat = cats.length ? cats[0][0] : "other";
      const level = fixed ? (it.fixed_kind === "reported" ? "reported" : "fixed") : String(it.level);
      const tileIcon = BADGE_SUBTYPE_ICON[it.target.subtype] || catIcon(topCat);
      const people = t(fixed ? "heat.card.people_fixed" : "heat.card.people", { count: it.count });
      const tab = S.cardTab && S.cardTab.key === key ? S.cardTab.tab : "overview";
      const tabs = [["overview", t("heat.tab.overview")]];
      if (S.role === "akimat") tabs.push(["reports", t("heat.tab.reports") + " · " + fmtNum(it.count)]);
      tabs.push(["history", t("heat.tab.history")]);
      const panelOf = (id, html) => '<div class="r07-tp" role="tabpanel" id="r07-tp-' + id + '" aria-labelledby="r07-tab-' + id + '"' + (id === tab ? "" : " hidden") + ">" + html + "</div>";
      return '<article class="r07-card" data-level="' + esc(level) + '">' +
        '<header class="r07-card__hd"><span class="r07-tile" aria-hidden="true">' + svgIcon(tileIcon, 24) + "</span>" +
          '<div class="r07-card__hg"><h3 class="r07-card__title" tabindex="-1">' + esc(label(it.target)) + "</h3>" +
          '<p class="r07-card__sub r07-eyebrow">' + eyebrow + "</p></div>" +
          '<button type="button" class="r07-x" data-back aria-label="' + esc(t("heat.close")) + '" title="' + esc(t("heat.close")) + '">' + svgIcon("close", 16) + "</button></header>" +
        '<p class="r07-big"><b>' + fmtNum(it.count) + "</b><span>" + esc(people) + " · " + esc(keep(t("heat.for_days", { count: S.filters.days }))) + "</span></p>" +
        statusLineHtml(it) +
        (actions ? '<div class="r07-actions">' + actions + "</div>" : "") +
        '<div class="r07-tabs" role="tablist" aria-label="' + esc(label(it.target)) + '">' + tabs.map(([id, name]) =>
          '<button type="button" role="tab" class="r07-tab" id="r07-tab-' + id + '" data-tab="' + id + '" aria-controls="r07-tp-' + id +
          '" aria-selected="' + (id === tab) + '" tabindex="' + (id === tab ? 0 : -1) + '">' + esc(name) + "</button>").join("") + "</div>" +
        panelOf("overview", overviewHtml(it, key, topCat)) +
        (S.role === "akimat" ? panelOf("reports", textsHtml(key) || '<p class="r07-note r07-tp__empty">' + esc(t("heat.texts.staff_only")) + "</p>") : "") +
        panelOf("history", historyHtml(it, cats)) +
        "</article>";
    }
    // Строка «подпись — значение» с иконкой в плитке 30 px (эталон .row)
    function rowHtml(icon, name, value, extra) {
      return '<div class="r07-row' + (extra ? " " + extra : "") + '"><span class="r07-row__ic" aria-hidden="true">' + svgIcon(icon, 16) + "</span>" +
        '<span class="r07-row__k">' + esc(name) + '</span><b class="r07-row__v">' + value + "</b></div>";
    }
    // «Обзор»: чаще всего / тема / табличка QR, одна цитата (≤ 2 строк) и «Ещё N обращений», у сотрудника — «Объединено с этим»
    function overviewHtml(it, key, topCat) {
      const rows = [];
      const most = topicName(it, topCat);
      rows.push(rowHtml(catIcon(topCat), t("heat.row.most"), esc(most), "r07-card__topic-row"));
      if (catName(topCat) !== most) rows.push(rowHtml("list", t("heat.row.topic"), esc(catName(topCat))));
      // R12 волна 2 п. 6 (IA_WAVE2 §6.2): акимату — лист QR-табличек этого места
      if (S.role === "akimat" && QR_ID.test(it.target.id)) rows.push(rowHtml("qr", t("heat.row.qr"),
        '<a class="r07-qr" href="/civic/qr/print.html?ids=' + encodeURIComponent(it.target.id) + '" target="_blank" rel="noopener">' + esc(t("qr.print")) + "</a>"));
      let lead = "";
      if (S.role === "akimat") {
        const st = S.texts.get(textsKey(key));
        if (st && st.status === "loading") lead = '<div class="r07-lead r07-lead--skel" aria-hidden="true"><i></i><i></i></div>';
        else if (st && st.status === "ready" && st.data && (st.data.groups || []).length) {
          const g = st.data.groups[0];
          const rest = Math.max(0, (it.count || 0) - (g.people || 1));
          lead = '<div class="r07-lead"><p class="r07-quote r07-lead__q" lang="' + esc(g.lang === "kk" ? "kk" : g.lang === "ru" ? "ru" : S.lang) + '">«' + esc(g.text) + "»</p>" +
            (g.rude ? '<span class="r07-tag r07-tag--rude">' + esc(t("moderation.rude")) + "</span>" : "") +
            '<button type="button" class="r07-more" data-tab-go="reports">' + esc(rest ? t("heat.more_reports", { count: rest }) : t("heat.all_reports")) + "</button></div>";
        }
      }
      return '<div class="r07-rows">' + rows.join("") + lead + "</div>" + (S.role === "akimat" ? mergedHtml(key) : "");
    }
    // «История»: жалобы по дням и о чём сообщают (то, что раньше было в «Подробнее»)
    function historyHtml(it, cats) {
      const fixed = it.state === "fixed";
      const daily = it.daily || [];
      const maxDay = Math.max(1, ...daily, 0);
      const parts = [];
      parts.push('<div class="r07-rows">' + rowHtml("clock", t("heat.row.period"), esc(keep(t("heat.for_days", { count: S.filters.days })))) +
        rowHtml("users", t("heat.row.reported"), esc(t("heat.texts.people", { count: it.count }))) + "</div>");
      if (!fixed && daily.some((n) => n > 0)) {
        parts.push('<section class="r07-chart"><h4 class="r07-h4">' + esc(t("heat.chart")) + '</h4><div class="r07-spark" role="img" aria-label="' + esc(t("heat.chart")) + '">' +
          daily.map((n) => '<i style="height:' + Math.max(n ? 8 : 2, Math.round((n / maxDay) * 100)) + '%" title="' + n + '"></i>').join("") +
          '</div><div class="r07-axis"><span>' + esc(t("heat.chart_from")) + "</span><span>" + esc(t("heat.chart_to")) + "</span></div></section>");
      }
      // «О чём сообщают»: категория и под ней самое частое уточнение этой категории (волна 1, п. 2 и 12)
      const subOf = (c) => {
        const ids = Object.entries(it.subtopics || {}).filter(([id]) => {
          const st = S.meta && (S.meta.subtopics || []).find((x) => x.id === id);
          return st && st.category === c;
        });
        if (!ids.length) return "";
        const [id, n] = ids[0];
        const name = subName(id);
        return name ? '<small class="r07-topics__sub">' + esc(name) + " · " + fmtNum(n) + "</small>" : "";
      };
      if (cats.length > 1) parts.push('<section class="r07-topics-box"><h4 class="r07-h4">' + esc(t("heat.topics")) + '</h4><ul class="r07-topics">' + cats.map(([c, n]) =>
        "<li>" + svgIcon(catIcon(c), 18) + "<span>" + esc(catName(c)) + subOf(c) + "</span><b>" + fmtNum(n) + "</b></li>").join("") + "</ul></section>");
      return parts.join("");
    }

    // «Что пишут жители» (UX_REVIEW R11, день 3, №4): 1–3 группы похожих текстов с числом людей.
    // Только для акимата. Сервер отдаёт тексты примеров (synthetic) всем, а настоящих жалоб — только сотруднику
    // после входа (шлюз R01 передаёт staff=True); жителю этот раздел не показывается вовсе.
    // Чистый дизайн: блок «Подробнее», у акимата открыт; текстов нет — блока нет. Пока грузятся — та же строка «Что пишут
    // жители» и скелет цитат на их месте (дизайн-марафон №8): карточка не «прыгает», когда цитаты приходят через миг,
    // а сами цитаты мягко проявляются (S.textsFresh → .r07-enter, один раз).
    function textsKey(key) { return key + "|" + S.filters.days; }
    function textsHtml(key) {
      const st = S.texts.get(textsKey(key));
      if (st && st.status === "loading") {
        const q = '<span class="r07-texts__q"><i></i><i></i><i class="r07-skel__meta"></i></span>';   // цитата 2 строки + «N человек»
        return '<section class="r07-texts r07-texts--loading" aria-busy="true"><div class="r07-texts__skel" aria-hidden="true">' + q + q + q + "</div></section>";
      }
      if (!st || st.status !== "ready") return "";
      const groups = (st.data && st.data.groups) || [];
      const hidden = (st.data && st.data.hidden_people) || 0;
      if (!groups.length && !hidden) return "";
      const body = (groups.length
        ? '<ul class="r07-quotes">' + groups.map((g) =>
          '<li><p class="r07-quote" lang="' + esc(g.lang === "kk" ? "kk" : g.lang === "ru" ? "ru" : S.lang) + '" title="' + esc(g.text) + '">«' + esc(g.text) + '»</p><p class="r07-quote__meta">' +
          esc(t("heat.texts.people", { count: g.people })) + (g.demo ? ' · <span class="r07-tag">' + esc(t("heat.demo_tag")) + "</span>" : "") +
          (g.rude ? ' <span class="r07-tag r07-tag--rude">' + esc(t("moderation.rude")) + "</span>" : "") + "</p></li>").join("") + "</ul>"
        : "") + (hidden ? '<p class="r07-note">' + esc(t("heat.texts.staff_only")) + "</p>" : "");
      return '<section class="r07-texts">' + body + "</section>";
    }
    // «Объединено с этим» (волна мелочей п. 9, R04 + R09): дубли и «Я тоже» с текстом жителя, присоединённые к жалобам
    // этой цели. Ошибочное объединение акимат отменяет одним нажатием «Это разные проблемы» — R09 выделяет жалобу
    // обратно, цель пересчитывается. Блок свёрнут (карточка не растёт) и есть только у вошедшего сотрудника.
    function mergedHtml(key) {
      const st = S.merged.get(key);
      if (!st || st.status !== "ready" || !st.items.length) return "";
      const rows = st.items.map((m) => {
        const meta = m.kind === "duplicate"
          ? t("merge.kind.duplicate", { code: m.code || "", date: fmtDate(m.merged_at || m.at, S.lang) })
          : t("merge.kind.metoo", { date: fmtDate(m.at, S.lang) });
        return '<li><p class="r07-quote" lang="' + esc(m.lang === "kk" ? "kk" : m.lang === "ru" ? "ru" : S.lang) + '">«' + esc(m.text || "") + '»</p>' +
          '<p class="r07-quote__meta">' + esc(meta) + (m.moderation ? ' <span class="r07-tag r07-tag--rude">' + esc(t("moderation.rude")) + "</span>" : "") + "</p>" +
          '<button type="button" class="r07-btn r07-merged__btn" data-act="separate" data-item="' + esc(m.id) + '">' + esc(t("merge.separate")) + "</button></li>";
      }).join("");
      return '<details class="bk-details r07-details r07-merged"' + (S.mergedOpen === key ? " open" : "") + '><summary class="r07-h4">' + esc(t("merge.title")) +
        ' <span class="r07-merged__count">' + fmtNum(st.items.length) + "</span></summary>" +
        '<p class="r07-note">' + esc(t("merge.hint")) + '</p><ul class="r07-quotes">' + rows + "</ul></details>";
    }
    async function loadMerged(key) {
      if (S.role !== "akimat") return;
      const [kind, ...rest] = key.split(":");
      if (kind === "district") return;
      S.merged.set(key, { status: "loading", items: [] });
      try {
        const res = await getJson("/complaints/merged?target_id=" + encodeURIComponent(rest.join(":")));
        S.merged.set(key, { status: "ready", items: res && Array.isArray(res.items) ? res.items : [] });
      } catch (e) {
        S.merged.set(key, { status: "error", items: [] });   // 403 — не вошёл: блока просто нет
      }
      if (S.selected === key && !S.destroyed) render();
    }
    async function separate(it, itemId, btn) {
      const key = keyOf(it.target);
      btn.setAttribute("aria-busy", "true");
      btn.disabled = true;
      try {
        const res = await post("/complaints/" + encodeURIComponent(itemId) + "/separate", {});
        const made = res && res.data && res.data.complaint;
        toast(t("merge.separated", { code: (made && made.code) || "" }));
        await load("event");
        await loadMerged(key);
      } catch (e) {
        if (e && e.status === 409) { toast(t("merge.already")); void loadMerged(key); return; }
        actionFailed(e, () => {
          const again = panel.querySelector('[data-act="separate"][data-item="' + (window.CSS && CSS.escape ? CSS.escape(itemId) : itemId) + '"]');
          if (again) void separate(it, itemId, again);
        });
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
      }
    }
    async function loadTexts(key) {
      if (S.role !== "akimat") return;
      const tk = textsKey(key);
      if (S.texts.has(tk) && S.texts.get(tk).status === "ready") return;
      S.texts.set(tk, { status: "loading" });
      const [kind, ...rest] = key.split(":");
      try {
        const q = new URLSearchParams({ kind, id: rest.join(":"), days: String(S.filters.days) });
        const res = await getJson("/heat/target?" + q.toString());
        S.texts.set(tk, { status: "ready", data: res && res.item ? res.item.texts : null });
        S.textsFresh = tk;
      } catch (e) {
        S.texts.set(tk, { status: "error" });
      }
      if (S.selected === key && !S.destroyed) render();
    }

    // Список ↔ карта синхронно (README эталона, правило 5): наведение или фокус на строке подсвечивает значок места, наведение
    // на значок — его строку. Значок и строка получают .r07-badge--hot / .r07-item--hot; без анимации карты.
    function setHot(key, from) {
      if (S.hotKey === key) return;
      const prev = S.hotKey;
      S.hotKey = key || null;
      for (const k of [prev, S.hotKey]) {
        if (!k) continue;
        const on = k === S.hotKey;
        const m = S.markers.get(k);
        if (m && m.el) m.el.classList.toggle("r07-badge--hot", on);
        const sel = window.CSS && CSS.escape ? CSS.escape(k) : k;
        panel.querySelectorAll('.r07-item[data-key="' + sel + '"]').forEach((r) => r.classList.toggle("r07-item--hot", on));
      }
      // Правило 5 Linear «список ↔ карта» с «Обращениями» R09: значок под мышью подсвечивает строку там (source "map");
      // строку R09 под мышью сообщает то же событие с source "inbox" — его не пересылаем обратно.
      if (from !== "inbox") {
        const i = S.hotKey ? S.hotKey.indexOf(":") : -1;
        window.dispatchEvent(new CustomEvent("birge:target-hover",
          { detail: i > 0 ? { kind: S.hotKey.slice(0, i), id: S.hotKey.slice(i + 1), source: "map" } : null }));
      }
    }
    function onTargetHover(ev) {
      const d = ev && ev.detail;
      if (d && d.source === "map") return;
      setHot(d && d.kind && d.id ? d.kind + ":" + d.id : null, "inbox");
    }
    // Строки «Горячих мест»: ↑ ↓ (и J K, как в Linear) — по строкам, Home / End — к первой и последней; одна строка в порядке
    // Tab (roving tabindex). Плавающая кнопка смены статуса — у строки под мышью или в фокусе.
    function bindHotList() {
      const rows = [...panel.querySelectorAll(".r07-hot .r07-list .r07-item")];
      if (!rows.length) return;
      const quick = panel.querySelector("[data-quick]");
      const showQuick = (row) => {
        if (!quick) return;
        const it = row && findItem(row.dataset.key);
        const st = it && (it.reopened ? "new" : it.status || "new");
        if (!it || it.state !== "active" || examplesOnly(it) || !(it.open_ids || []).length) { quick.hidden = true; return; }
        const take = st === "new";
        const word = t(take ? "heat.take" : "heat.mark_fixed");
        quick.innerHTML = statusIcon(take ? "in_progress" : "reported_fixed");
        quick.dataset.key = row.dataset.key;
        quick.dataset.quick = take ? "take" : "fixed";
        quick.setAttribute("aria-label", word + ": " + label(it.target));
        quick.title = word;
        const box = panel.querySelector(".r07-hot").getBoundingClientRect(), r = row.getBoundingClientRect();
        quick.style.top = Math.round(r.top - box.top + (r.height - 32) / 2) + "px";
        quick.hidden = false;
      };
      rows.forEach((b, i) => {
        b.addEventListener("mouseenter", () => { setHot(b.dataset.key); showQuick(b); });
        b.addEventListener("focus", () => { setHot(b.dataset.key); showQuick(b); });
        b.addEventListener("keydown", (e) => {
          const k = e.key;
          const d = k === "ArrowDown" || k === "j" || k === "J" ? 1 : k === "ArrowUp" || k === "k" || k === "K" ? -1 : 0;
          const to = k === "Home" ? 0 : k === "End" ? rows.length - 1 : d ? Math.max(0, Math.min(rows.length - 1, i + d)) : -1;
          if (to < 0 || e.altKey || e.ctrlKey || e.metaKey) return;
          e.preventDefault();
          rows.forEach((r, j) => { r.tabIndex = j === to ? 0 : -1; });
          rows[to].focus();
        });
      });
      const list = panel.querySelector(".r07-hot");
      list.addEventListener("mouseleave", () => { setHot(null); if (quick && document.activeElement !== quick) quick.hidden = true; });
      if (quick) quick.addEventListener("click", () => {
        const key = quick.dataset.key, it = findItem(key);
        if (!it) return;
        if (quick.dataset.quick === "take") void setStatus(it, "in_progress", quick);
        else {
          // «Исправлено» — та же форма R09 «что сделали», что в карточке: открыть карточку места с формой
          if (window.BirgeComplaintStaff && typeof window.BirgeComplaintStaff.fixForm === "function") S.fixFor = key;
          select(key, true);
          if (!S.fixFor) void setStatus(it, "fixed", quick);
        }
      });
    }
    // Подсказки поиска оболочки: горячие места (S.top) и цели на карте сейчас (S.data), без повторов; совпадение с началом
    // слова — выше, чем в середине; затем по весу (горячее — выше).
    function suggest(q, n) {
      const norm = (x) => String(x || "").toLowerCase().replace(/ё/g, "е").replace(/[«»"]/g, "");
      const needle = norm(q).trim();
      if (!needle) return [];
      const seen = new Set(), out = [];
      const pool = (S.top || []).concat(S.data ? S.data.items.filter((it) => it.state === "active" && it.target.kind !== "district") : []);
      for (const it of pool) {
        const key = keyOf(it.target);
        if (seen.has(key)) continue;
        seen.add(key);
        const names = [it.target.label_ru, it.target.label_kk].map(norm);
        const at = Math.min(...names.map((x) => { const i = x.indexOf(needle); return i < 0 ? 1e9 : i === 0 || /[\s(«-]/.test(x[i - 1]) ? 0 : 1; }));
        if (at >= 1e9) continue;
        out.push({ rank: at, w: it.weight || it.count || 0, v: { key, kind: it.target.kind, id: it.target.id, label: label(it.target), count: it.count, level: it.level, topic: topicName(it) } });
      }
      return out.sort((a, b) => a.rank - b.rank || b.w - a.w).slice(0, Math.max(1, Number(n) || 5)).map((x) => x.v);
    }
    // «Рядом с вами» (эталон A, телефон; R11 §21.2 — разметка шторки у R09): n ближайших мест к точке [lng, lat]
    // (по умолчанию — центр карты), в том числе исправленные (строка с ✓ «… · проверьте»). Только данные и open().
    function nearby(n, center) {
      const c = Array.isArray(center) && center.length === 2 ? center.map(Number)
        : map ? (({ lng, lat }) => [lng, lat])(map.getCenter()) : null;
      if (!c) return [];
      const kx = Math.cos((c[1] * Math.PI) / 180) * 111320, ky = 110540;
      return (S.places || []).map((it) => {
        const key = keyOf(it.target);
        const fixed = it.state === "fixed";
        const status = fixed ? (it.fixed_kind === "verified" ? "verified" : it.fixed_kind === "reported" ? "reported_fixed" : "fixed")
          : ["accepted", "in_progress"].includes(it.status) ? it.status : "new";
        return { key, kind: it.target.kind, id: it.target.id, label: label(it.target), count: it.count, level: fixed ? null : it.level,
          state: it.state, status, status_word: t("heat.status." + status), check: fixed && status === "reported_fixed",
          topic: topicName(it), meters: Math.round(Math.hypot((it.anchor[0] - c[0]) * kx, (it.anchor[1] - c[1]) * ky)), open: () => openKey(key) };
      }).sort((a, b) => a.meters - b.meters).slice(0, Math.max(1, Number(n) || 3));
    }
    function openKey(key) {
      if (findItem(key)) { select(key, true); return; }
      const p = S.topItems.get(key);
      if (p) void focusTarget(p.target.kind, p.target.id);
    }
    function commands() {
      const out = [];
      (S.top || []).slice(0, TOP_N).forEach((it) => {
        const key = keyOf(it.target);
        out.push({ id: "heat:open:" + key, group: t("heat.hot_title"), title: label(it.target), hint: t("heat.people_short", { count: it.count }), run: () => openKey(key) });
      });
      ((S.meta && S.meta.periods) || [7, 30, 90]).forEach((d) => out.push({ id: "heat:days:" + d, group: t("heat.period"), title: t("heat.days", { count: d }),
        run: () => { S.filters.days = d; void load("filter"); } }));
      // «Хроника города» (раунд 15, web/civic/replay): неделя или месяц на этой же карте
      if (window.BirgeReplay && typeof window.BirgeReplay.open === "function" && map) {
        [[7, "heat.replay.command"], [30, "heat.replay.command_month"]].forEach(([d, key]) => out.push({ id: "heat:replay:" + d, group: t("heat.title"),
          title: t(key), run: () => window.BirgeReplay.open({ map, heat: handle, days: d }) }));
      }
      const it = S.selected && findItem(S.selected);
      if (it && S.role === "akimat" && it.state === "active" && !examplesOnly(it) && (it.open_ids || []).length) {
        const act = (a) => () => { const b = panel.querySelector('.r07-card [data-act="' + a + '"]'); if (b) b.click(); };
        if (it.status !== "in_progress") out.push({ id: "heat:take", group: label(it.target), title: t("heat.take"), run: act("take") });
        out.push({ id: "heat:fixed", group: label(it.target), title: t("heat.mark_fixed"), run: act("fixed") });
      }
      return out;
    }
    // J / K (Linear): следующее / предыдущее горячее место; без открытой карточки — первое (или последнее)
    function stepHot(d) {
      const keys = (S.top || []).slice(0, TOP_N).map((it) => keyOf(it.target));
      if (!keys.length) return null;
      const i = keys.indexOf(S.selected);
      const next = keys[i < 0 ? (d < 0 ? keys.length - 1 : 0) : Math.max(0, Math.min(keys.length - 1, i + (d < 0 ? -1 : 1)))];
      if (next !== S.selected) openKey(next);
      return next;
    }
    // Правило Linear 4 (эталон A, замер R10 response_check «период»): фильтр откликается сразу — выбранный чип или период
    // до ответа сервера; строки остаются на месте и бледнеют только если ответ дольше 150 мс (без мигания); render() после
    // ответа всё заменит.
    function filterNow(btn, group) {
      if (btn && group) panel.querySelectorAll(group).forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      const days = panel.querySelector(".r07-lhd__days");
      if (days) days.textContent = keep(t("heat.for_days", { count: S.filters.days }));
      const hot = panel.querySelector(".r07-hot");
      if (hot) hot.classList.add("r07-hot--updating");
    }
    function bindPanel() {
      panel.querySelectorAll("[data-cat]").forEach((b) => b.addEventListener("click", () => {
        S.filters.category = b.dataset.cat || null; S.selected = null; S.catsOpen = false; filterNow(b, "[data-cat]"); void load("filter");
      }));
      panel.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => {
        if (typeof opts.onClose === "function") opts.onClose();
        window.dispatchEvent(new CustomEvent("birge:heat-close"));
      }));
      panel.querySelectorAll("[data-days]").forEach((b) => b.addEventListener("click", () => {
        S.filters.days = Number(b.dataset.days); filterNow(b, "[data-days]"); void load("filter");
      }));
      const sel = panel.querySelector("[data-district]");
      if (sel) sel.addEventListener("change", () => {
        S.filters.district = sel.value || null; S.selected = null; void load("filter");   // карта впишет 10 мест района
      });
      panel.querySelectorAll("[data-days-next]").forEach((b) => b.addEventListener("click", () => {
        S.filters.days = Number(b.dataset.daysNext); void load("filter");
      }));
      panel.querySelectorAll("[data-reset]").forEach((b) => b.addEventListener("click", () => {
        S.filters = { category: null, days: (S.meta && S.meta.default_days) || 30, district: null }; S.selected = null; void load("filter");
      }));
      panel.querySelectorAll("[data-retry]").forEach((b) => b.addEventListener("click", () => { S.meta = null; void load(); }));
      panel.querySelectorAll(".r07-item").forEach((b) => b.addEventListener("click", () => {
        const it = findItem(b.dataset.key);
        if (it && it.target.kind === "district") { map && map.easeTo({ center: it.anchor, zoom: 13, duration: moveMs(700) }); return; }
        if (it) { select(b.dataset.key, true); return; }
        // Карта сейчас — районы: приблизить к месту и открыть его карточку.
        const place = S.topItems.get(b.dataset.key);
        if (place) { b.classList.add("r07-item--busy"); b.setAttribute("aria-busy", "true"); void focusTarget(place.target.kind, place.target.id); }
      }));
      bindHotList();
      panel.querySelectorAll("[data-back]").forEach((b) => b.addEventListener("click", () => {
        S.selected = null; updateSelectionLayer(); render(); drawBadges();
      }));
      // Вкладки карточки «Обзор · Обращения · История» (эталон A): выбор помнится для этого места (перерисовка не сбрасывает),
      // ← → — по вкладкам (ARIA tabs), «Ещё N обращений» ведёт во «Обращения»; смена — мягко, 180 мс.
      const tabs = [...panel.querySelectorAll(".r07-tab")];
      const goTab = (id, focus) => {
        if (!S.selected) return;
        S.cardTab = { key: S.selected, tab: id };
        tabs.forEach((b) => { const on = b.dataset.tab === id; b.setAttribute("aria-selected", String(on)); b.tabIndex = on ? 0 : -1; if (on && focus) b.focus(); });
        panel.querySelectorAll(".r07-tp").forEach((tp) => {
          const on = tp.id === "r07-tp-" + id;
          if (on && tp.hidden) { tp.classList.remove("r07-tp--in"); void tp.offsetWidth; tp.classList.add("r07-tp--in"); }
          tp.hidden = !on;
        });
      };
      tabs.forEach((b, i) => {
        b.addEventListener("click", () => goTab(b.dataset.tab));
        b.addEventListener("keydown", (e) => {
          const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
          if (!d) return;
          e.preventDefault();
          goTab(tabs[(i + d + tabs.length) % tabs.length].dataset.tab, true);
        });
      });
      panel.querySelectorAll("[data-tab-go]").forEach((b) => b.addEventListener("click", () => goTab(b.dataset.tabGo, true)));
      panel.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => {
        const it = findItem(S.selected);
        if (!it) return;
        if (b.dataset.act === "take") void setStatus(it, "in_progress", b);
        if (b.dataset.act === "fixed") {
          // R09 волна 2 (IA_WAVE2 §2.3, R11 разбор 9 №1): «что сделали» + фото «после» — форма R09 в этой же карточке.
          // Без модуля R09 на странице — как раньше: сразу «исправлено».
          if (window.BirgeComplaintStaff && typeof window.BirgeComplaintStaff.fixForm === "function" && (it.open_ids || []).length) {
            S.fixFor = S.selected; render();
          } else void setStatus(it, "fixed", b);
        }
        if (b.dataset.act === "metoo") void metoo(it, b);
        if (b.dataset.act === "separate") void separate(it, b.dataset.item, b);
      }));
      panel.querySelectorAll(".r07-merged").forEach((d) => d.addEventListener("toggle", () => {
        S.mergedOpen = d.open ? S.selected : null;
      }));
      // «Подробнее»: запомнить выбор; плавное раскрытие — только по нажатию, не при каждой перерисовке
      panel.querySelectorAll(".r07-details").forEach((d) => {
        if (d.dataset.dk) d.addEventListener("toggle", () => S.detailsOpen.set(d.dataset.dk, d.open));
        d.querySelector(":scope > summary")?.addEventListener("click", () => {
          if (d.open) return;
          d.classList.add("r07-details--opening");
          setTimeout(() => d.classList.remove("r07-details--opening"), 400);
        });
      });
    }

    // ----- события -----
    let moveTimer = null;
    function onMoveEnd() {
      const ex = legendExtras();
      if (((ex.reported ? "r" : "") + (ex.nodata ? "n" : "")) !== (S.legendKey || "")) renderMapLegend();
      declutter();
      const nextMode = modeFor(zoomNow());
      if (R.on) {   // хроника: тот же день районами или местами — из кадра, без запроса к серверу
        if (R.frame && nextMode !== S.mode) replayShow(replayData(R.frame), moveMs(300));
        return;
      }
      if (nextMode !== S.mode) {
        clearTimeout(moveTimer);
        moveTimer = setTimeout(() => void load(), 150);
      }
    }
    function onStyleData() {
      // После смены стиля карты (например, переход на офлайн-подложку) наши источники пропадают — добавляем заново.
      if (layersReady && !map.getSource(SRC)) layersReady = false;
      if (!layersReady && S.data) draw(false);
    }
    function onComplaintEvent(ev) {
      // R09 после create / metoo / status: window.dispatchEvent(new CustomEvent("birge:complaint", {detail:{type, target}}))
      if (R.on) { R.missed = true; return; }
      const d = (ev && ev.detail) || {};
      void load("event").then(() => { if (d.target && d.target.id && d.type !== "status") pulse(keyOf(d.target)); });
    }
    function onLang(ev) {
      const next = ev && ev.detail && ev.detail.lang;
      if (next && next !== S.lang) { S.lang = next; render(); drawBadges(); }
    }
    function onKey(ev) {
      if (R.on) return;
      if (ev.key === "Escape") showPlace(null);   // контур места без жалоб — как карточка, по Esc
      if (ev.key === "Escape" && S.selected) { S.selected = null; updateSelectionLayer(); render(); drawBadges(); }
    }
    if (map) {
      map.on("moveend", onMoveEnd);
      map.on("styledata", onStyleData);
      map.on("dragstart", () => { userMoved.value = true; });
      map.on("movestart", hideTip);
      map.on("movestart", (e) => { if (e && e.originalEvent) { userMoved.value = true; if (S.busyKey) clearBusy(); } });   // колесо, щипок, кнопки; перелёт к месту прерван — строка не «крутится»
    }
    window.addEventListener("birge:complaint", onComplaintEvent);
    // Шрифт Inter догрузился позже первой раскладки — ширины значков другие: замерить заново (один раз на вид значка)
    const onFonts = () => { S.badgeSize = {}; S.clusterSize = {}; for (const m of S.markers.values()) m.sizeKey = null; if (S.data) drawBadges(); };
    if (document.fonts && document.fonts.addEventListener) document.fonts.addEventListener("loadingdone", onFonts);
    window.addEventListener("birge:target-hover", onTargetHover);
    // Язык: i18n R11 шлёт "birge:lang" на document, другие модули — на window. Слушаем оба (повтор отсекается).
    window.addEventListener("birge:lang", onLang);
    document.addEventListener("birge:lang", onLang);
    document.addEventListener("keydown", onKey);
    TOOL_EVENTS.forEach((type) => document.addEventListener(type, onToolEvent));
    if (opts.hash !== false) window.addEventListener("hashchange", onHash);
    // «Горячее место» в «Картине дня» R08 шлёт отменяемое "birge:open-target". В сборке его ловит оболочка R01;
    // модуль ловит сам только по просьбе (opts.handleOpenTarget), чтобы не мешать оболочке переключить вкладку.
    function onOpenTarget(ev) {
      const d = (ev && ev.detail) || {};
      if (ev.defaultPrevented || !d.target || !d.target.kind || !d.target.id) return;
      ev.preventDefault();
      void focusTarget(d.target.kind, d.target.id, { days: d.days });
    }
    if (opts.handleOpenTarget) document.addEventListener("birge:open-target", onOpenTarget);

    render();
    const startHash = opts.hash !== false ? parseHash() : null;
    if (startHash) void focusTarget(startHash.kind, startHash.id, { days: startHash.days });
    else void load();

    const handle = {
      version: VERSION,
      refresh: () => load("event"),
      pulse: (target) => pulse(typeof target === "string" ? target : keyOf(target)),
      focusTarget: (kind, id, o) => focusTarget(kind, id, o),
      setRole: (role) => { S.role = role === "resident" ? "resident" : "akimat"; if (map && layersReady) { removeLayers(); } draw(false); render(); },
      setLang: (lang) => { S.lang = lang === "kk" ? "kk" : "ru"; render(); drawBadges(); },
      setFilters: (f) => { Object.assign(S.filters, f || {}); void load(); },
      // Для оболочки R01 (README эталона, правила 1, 2, 7):
      //  suggest(q, n) — горячие места для подсказок поиска (с первой буквы, ru/kk, по началу слова выше): [{ key, kind, id,
      //    label, count, level, topic }] — открыть: focusTarget(kind, id);
      //  stepHot(±1) — J / K по горячим местам: открыть карточку следующего / предыдущего (карта плавно ведёт к месту);
      //  close() — закрыть карточку места (×, Esc, нажатие на пустую карту — решает оболочка).
      suggest: (q, n) => suggest(q, n),
      stepHot: (d) => stepHot(d),
      nearby: (n, center) => nearby(n, center),
      //  commands() — пункты командной палитры акимата (Ctrl+K, README правило 2): [{ id, group, title, hint, run }] —
      //    открыть горячее место, период 7 / 30 / 90, «Взять в работу» / «Отметить исправленным» у открытого места.
      commands: () => commands(),
      close: () => { showPlace(null); if (!S.selected) return false; S.selected = null; updateSelectionLayer(); render(); drawBadges(); return true; },
      // Режим выбора места жалобой без класса body.birge-picking (другая оболочка): значки передают щелчок карте.
      setPickMode: (on) => {
        S.picking = !!on;
        for (const m of S.markers.values()) m.el.classList.toggle("r07-badge--pick", !!on);
        for (const c of S.clusters) c.el.classList.toggle("r07-badge--pick", !!on);
      },
      // Видимые значки: id цели, вид (full / mini), точка на карте и центр на экране — для проверок точности (R10, тесты R07).
      // Для проверок: центр значка на экране (cx, cy) и где он должен быть по карте (px, py = map.project точки значка).
      badges: () => [...S.markers.entries()].filter(([, m]) => !m.el.hidden).map(([key, m]) => ({ key, mode: m.el.dataset.mode, spot: m.spot, el: m.el }))
        .concat(S.clusters.map((c) => ({ key: c.key, mode: "cluster", spot: c.ll, el: c.el, members: c.members.slice() })))
        .map((b) => {
          const r = b.el.getBoundingClientRect();
          const host = map.getContainer().getBoundingClientRect();
          const p = map.project(b.spot);
          const out = { key: b.key, mode: b.mode, spot: b.spot, cx: r.left + r.width / 2, cy: r.top + r.height / 2, px: host.left + p.x, py: host.top + p.y };
          if (b.members) out.members = b.members;
          return out;
        }),
      isMoving: () => Boolean(map && map.isMoving()),
      // «Хроника города» (раунд 15): web/civic/replay рисует прошлые дни этими же значками и слоями (см. replayBegin).
      replay: {
        begin: () => replayBegin(),
        frame: (frame, o) => replayFrame(frame, o),
        end: (o) => replayEnd(o),
        get active() { return R.on; },
        cost: () => ({ tween_ms_per_frame: R.cost.n ? +(R.cost.ms / R.cost.n).toFixed(2) : 0, day_switch_ms: R.cost.draws ? +(R.cost.drawMs / R.cost.draws).toFixed(1) : 0,
          day_switches: R.cost.draws, targets: S.data ? S.data.items.length : 0 }),
        apiBase,
        lang: () => S.lang,
        filters: () => ({ ...S.filters }),
        fetch: fetchFn,
      },
      state: () => ({ role: S.role, lang: S.lang, filters: { ...S.filters }, selected: S.selected, mode: S.mode, status: S.status,
        items: S.data ? S.data.items.length : 0, pending: S.pendingSelect, fittedKeys: S.fittedKeys || [] }),
      destroy,
    };
    current = handle;   // для «Хроники» (web/civic/replay) на страницах без оболочки: CivicHeat.current
    return handle;

    function removeLayers() {
      // Все слои модуля — по префиксу (новый слой не забудется: иначе источник нельзя удалить при смене роли)
      let style = null;
      try { style = map.getStyle(); } catch (e) { style = null; }
      const own = ((style && style.layers) || []).map((l) => l.id).filter((id) => id.startsWith("r07-"));
      own.forEach((id) => { try { if (map.getLayer(id)) map.removeLayer(id); } catch (e) { /* стиль сменился */ } });
      [SRC, SRC_PTS, SRC_PLACE].forEach((id) => { try { if (map.getSource(id)) map.removeSource(id); } catch (e) { /* стиль сменился */ } });
      layersReady = false;
    }
    function destroy() {
      S.destroyed = true;
      if (current === handle) current = null;
      if (overlayTimer) clearInterval(overlayTimer);
      if (S.anim) cancelAnimationFrame(S.anim);
      if (R.tween) cancelAnimationFrame(R.tween);
      if (R.counts) cancelAnimationFrame(R.counts);
      R.on = false;
      if (map) map.getContainer().classList.remove("r07-replaying");
      window.removeEventListener("birge:complaint", onComplaintEvent);
      if (document.fonts && document.fonts.removeEventListener) document.fonts.removeEventListener("loadingdone", onFonts);
      window.removeEventListener("birge:target-hover", onTargetHover);
      window.removeEventListener("birge:lang", onLang);
      document.removeEventListener("birge:lang", onLang);
      document.removeEventListener("keydown", onKey);
      TOOL_EVENTS.forEach((type) => document.removeEventListener(type, onToolEvent));
      window.removeEventListener("hashchange", onHash);
      document.removeEventListener("birge:open-target", onOpenTarget);
      if (S.legendEl) S.legendEl.remove();
      for (const m of S.markers.values()) m.marker.remove();
      S.markers.clear();
      for (const c of S.clusters) c.marker.remove();
      S.clusters = [];
      if (S.tipEl) S.tipEl.remove();
      if (map) map.getContainer().classList.remove("r07-focusing", "r07-map-tool");
      if (map) {
        map.off("moveend", onMoveEnd);
        map.off("styledata", onStyleData);
        try { removeLayers(); } catch (e) { /* стиль уже сменился */ }
      }
      root.innerHTML = "";
      root.classList.remove("r07-root");
    }
  }

  // messages — запасной словарь ru/kk (R11 переносит ключи heat.* в общие ru.json / kk.json).
  // current — последний смонтированный экземпляр (его ручку берёт «Хроника», если оболочка не передала свою).
  window.CivicHeat = { mount, version: VERSION, schema: "civic-v2", messages: DICT, get current() { return current; } };
})();
