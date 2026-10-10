/*
 * Birge · инструмент разметки (R02, раунд 14) — интерфейс.
 *
 * Поток: выбрать роль → открыть CSV/JSONL → для каждого текста нажать клавишу категории.
 * Всё хранится в localStorage этого браузера (автосохранение после каждого действия);
 * результат — файл JSONL (кнопка «Скачать JSONL» или Ctrl+S), его читает ml/labeling/agreement.py.
 *
 * Режим «второй разметчик»: детерминированный поднабор того же файла (ключ + размер),
 * метки первого разметчика не загружаются вообще (core.blindItems), хранение отдельное.
 */
(function () {
  "use strict";
  var C = window.BirgeLabelCore;
  var CATS = (window.BIRGE_CATEGORIES || { categories: [] }).categories;
  var STORE_PREFIX = "birge-labeling:v1:";
  var INDEX_KEY = STORE_PREFIX + "index";
  var UI_LANG_KEY = STORE_PREFIX + "ui-lang";
  var LANG_CYCLE = ["ru", "kk", "mixed"];
  var EXPORT_NUDGE = 50; // после стольких новых меток без экспорта шапка подсказывает скачать файл
  var MAX_MS = 10 * 60 * 1000; // дольше 10 минут на текст — человек отошёл, не считаем в скорость

  /* ---------- тексты интерфейса (ru / kk) ----------
   * Казахские строки помечены в research/round-14-results/R02/INTEGRATION.txt для проверки владельцем. */
  var STR = {
    ru: {
      title: "Разметка обращений", help: "Справка", export: "Скачать JSONL", changeFile: "Другой файл",
      storageOff: "Автосохранение в этом браузере недоступно. Скачивайте JSONL чаще.",
      startTitle: "Разметка обращений жителей",
      startLead: "Откройте файл с текстами (CSV или JSONL). Для каждого текста нажмите цифру категории — следующий текст появится сам.",
      resumeTitle: "Продолжить", whoAreYou: "Кто размечает",
      roleFirst: "Первый разметчик", roleFirstHint: "Все тексты файла по порядку",
      roleSecond: "Второй разметчик", roleSecondHint: "Тот же поднабор для проверки согласия; чужие метки скрыты",
      annotatorName: "Имя или код разметчика", subsetSize: "Сколько текстов", subsetSeed: "Ключ поднабора",
      subsetHint: "Одинаковый файл и одинаковый ключ дают одинаковый поднабор на любом компьютере.",
      openFile: "Открыть файл", dropHint: "или перетащите файл .csv / .jsonl сюда",
      privacy: "Файл не уходит в интернет: тексты и метки остаются в этом браузере, пока вы сами не скачаете JSONL.",
      unsureOn: "сомневаюсь", finishTitle: "Все тексты размечены",
      notComplaint: "Не жалоба", unsure: "Сомневаюсь", skip: "Пропустить", spaceKey: "Пробел", undo: "Отменить",
      prev: "Предыдущий", next: "Следующий", helpTitle: "Клавиши и правила",
      keysTitle: "Клавиши (работают в любой раскладке)", rulesTitle: "Главное правило",
      ruleMain: "Категорию определяет предмет проблемы, а не место. Если проблем несколько — главная (о чём просят).",
      casesTitle: "Спорные случаи", close: "Закрыть",
      roleChipFirst: "первый разметчик · {name}", roleChipSecond: "второй разметчик · {name} · ключ «{seed}»",
      progress: "{done} / {total}", itemNum: "Текст {n} из {total}",
      lang_ru: "рус", lang_kk: "қаз", lang_mixed: "смешанный", lang_: "язык?",
      labelIs: "метка: {label}", skippedIs: "пропущен",
      loaded: "Загружено текстов: {n}", dupes: "повторов убрано: {n}", empty: "пустых строк: {n}",
      bad: "нечитаемых строк: {n}", truncated: "обрезано длинных: {n}", priorLoaded: "готовых меток из файла: {n}",
      subsetMade: "Поднабор для второго разметчика: {n} из {total}",
      errEmpty: "В файле не нашлось ни одного текста. Проверьте, что это CSV или JSONL со столбцом text.",
      errRead: "Не получилось прочитать файл. Сохраните его как CSV (UTF-8) или JSONL и откройте снова.",
      errMismatch: "Это другой файл: он не совпадает с сохранённой разметкой. Откройте файл «{file}».",
      needFile: "Тексты этой разметки не поместились в память браузера. Откройте файл «{file}» ещё раз — метки сохранены.",
      saved: "{label}", undone: "Отменено: текст {n}", skipped: "Пропущено", nothingToUndo: "Нечего отменять",
      exported: "Файл скачан: {name}", exportNudge: "Скачайте JSONL: {n} новых меток с прошлого раза",
      finishStats: "Размечено {done} из {total}. Пропущено: {skipped}.",
      finishSkipped: "Все оставшиеся тексты пропущены", backToSkipped: "Вернуться к пропущенным ({n})",
      speed: "≈ {sec} с на текст · осталось ≈ {min} мин", speedNone: "",
      resumeItem: "{file} · {role} · {done} / {total}", roleFirstShort: "первый", roleSecondShort: "второй",
      deleteSession: "Удалить", confirmDelete: "Удалить сохранённую разметку «{file}» из этого браузера? Скачанные файлы останутся.",
      exportSubset: "Скачать поднабор без меток",
      k_cat: "категория", k_n: "не жалоба", k_f: "сомневаюсь (до или после выбора)", k_space: "пропустить",
      k_undo: "отменить последнее действие", k_arrows: "предыдущий / следующий текст", k_l: "сменить язык текста",
      k_save: "скачать JSONL", k_help: "эта справка", k_esc: "закрыть справку",
      notComplaintName: "Не жалоба"
    },
    kk: {
      title: "Өтініштерді белгілеу", help: "Анықтама", export: "JSONL жүктеп алу", changeFile: "Басқа файл",
      storageOff: "Бұл браузерде автосақтау жұмыс істемейді. JSONL файлын жиірек жүктеп алыңыз.",
      startTitle: "Тұрғындар өтініштерін белгілеу",
      startLead: "Мәтіндер бар файлды ашыңыз (CSV немесе JSONL). Әр мәтін үшін санат цифрын басыңыз — келесі мәтін өзі шығады.",
      resumeTitle: "Жалғастыру", whoAreYou: "Кім белгілейді",
      roleFirst: "Бірінші белгілеуші", roleFirstHint: "Файлдағы барлық мәтін ретімен",
      roleSecond: "Екінші белгілеуші", roleSecondHint: "Келісімді тексеруге арналған сол іріктеме; басқаның белгілері жасырын",
      annotatorName: "Белгілеушінің аты немесе коды", subsetSize: "Мәтін саны", subsetSeed: "Іріктеме кілті",
      subsetHint: "Бір файл мен бір кілт кез келген компьютерде бірдей іріктеме береді.",
      openFile: "Файлды ашу", dropHint: "немесе .csv / .jsonl файлын осында сүйреп әкеліңіз",
      privacy: "Файл интернетке жіберілмейді: мәтіндер мен белгілер JSONL-ды өзіңіз жүктеп алғанша осы браузерде қалады.",
      unsureOn: "күмәнім бар", finishTitle: "Барлық мәтін белгіленді",
      notComplaint: "Шағым емес", unsure: "Күмәнім бар", skip: "Өткізіп жіберу", spaceKey: "Бос орын", undo: "Болдырмау",
      prev: "Алдыңғы", next: "Келесі", helpTitle: "Пернелер мен ережелер",
      keysTitle: "Пернелер (кез келген пернетақта тілінде жұмыс істейді)", rulesTitle: "Басты ереже",
      ruleMain: "Санатты орын емес, мәселенің өзі анықтайды. Мәселе бірнешеу болса — негізгісі (не сұралып тұр).",
      casesTitle: "Даулы жағдайлар", close: "Жабу",
      roleChipFirst: "бірінші белгілеуші · {name}", roleChipSecond: "екінші белгілеуші · {name} · кілт «{seed}»",
      progress: "{done} / {total}", itemNum: "{total} мәтіннің {n}-сі",
      lang_ru: "орыс", lang_kk: "қаз", lang_mixed: "аралас", lang_: "тіл?",
      labelIs: "белгі: {label}", skippedIs: "өткізілді",
      loaded: "Жүктелген мәтін: {n}", dupes: "қайталау алынды: {n}", empty: "бос жол: {n}",
      bad: "оқылмаған жол: {n}", truncated: "қысқартылған ұзын мәтін: {n}", priorLoaded: "файлдағы дайын белгі: {n}",
      subsetMade: "Екінші белгілеушіге іріктеме: {total} ішінен {n}",
      errEmpty: "Файлдан бірде-бір мәтін табылмады. Бұл text бағаны бар CSV немесе JSONL екенін тексеріңіз.",
      errRead: "Файлды оқу мүмкін болмады. Оны CSV (UTF-8) немесе JSONL ретінде сақтап, қайта ашыңыз.",
      errMismatch: "Бұл басқа файл: сақталған белгілеумен сәйкес келмейді. «{file}» файлын ашыңыз.",
      needFile: "Бұл белгілеудің мәтіндері браузер жадына сыймады. «{file}» файлын қайта ашыңыз — белгілер сақталған.",
      saved: "{label}", undone: "Болдырылмады: {n}-мәтін", skipped: "Өткізілді", nothingToUndo: "Болдырмайтын әрекет жоқ",
      exported: "Файл жүктелді: {name}", exportNudge: "JSONL жүктеп алыңыз: соңғы реттен бері {n} жаңа белгі",
      finishStats: "{total} мәтіннің {done} белгіленді. Өткізілгені: {skipped}.",
      finishSkipped: "Қалған мәтіндердің бәрі өткізілді", backToSkipped: "Өткізілгендерге оралу ({n})",
      speed: "бір мәтінге ≈ {sec} с · ≈ {min} мин қалды", speedNone: "",
      resumeItem: "{file} · {role} · {done} / {total}", roleFirstShort: "бірінші", roleSecondShort: "екінші",
      deleteSession: "Жою", confirmDelete: "«{file}» белгілеуін осы браузерден жою керек пе? Жүктелген файлдар қалады.",
      exportSubset: "Іріктемені белгісіз жүктеп алу",
      k_cat: "санат", k_n: "шағым емес", k_f: "күмәнім бар (таңдауға дейін не кейін)", k_space: "өткізіп жіберу",
      k_undo: "соңғы әрекетті болдырмау", k_arrows: "алдыңғы / келесі мәтін", k_l: "мәтін тілін ауыстыру",
      k_save: "JSONL жүктеп алу", k_help: "осы анықтама", k_esc: "анықтаманы жабу",
      notComplaintName: "Шағым емес"
    }
  };

  // Спорные случаи — короткая выжимка из ml/datasets/LABELING_GUIDE_v2.md (полные правила там).
  var CASES = {
    ru: [
      "Снег, лёд, сосульки — везде «Снег и гололёд», даже на тротуаре или остановке.",
      "Яма во дворе или на проезде — «Дороги»; разбитая плитка — «Тротуары».",
      "Не горит фонарь на остановке — «Освещение»; сломан павильон — «Остановки».",
      "Светофор и разметка — «Дороги»; нет пешеходного перехода — «Шум и безопасность».",
      "Машины на газоне или тротуаре — «Парковки».",
      "Переполненные баки и урны, свалка — «Мусор»; сломанная урна в парке — «Дворы и площадки».",
      "Отопление, вода, канализация, лифт, крыша — «ЖКХ».",
      "Благодарность или вопрос о сроках без описания проблемы — «Другое».",
      "Реклама, тест, бессмыслица, не про город — «Не жалоба» (N)."
    ],
    kk: [
      "Қар, мұз, сүңгі — барлық жерде «Қар және көктайғақ», тротуарда не аялдамада болса да.",
      "Аулада не өтпе жолда шұңқыр — «Жолдар»; сынған плитка — «Жаяу жүргіншілер жолы».",
      "Аялдамада шам жанбайды — «Жарықтандыру»; павильон сынған — «Аялдамалар».",
      "Бағдаршам мен жол таңбасы — «Жолдар»; жаяу өткел жоқ — «Шу және қауіпсіздік».",
      "Көгалда не тротуарда тұрған көліктер — «Тұрақтар».",
      "Толып кеткен контейнер мен урна, үйінді — «Қоқыс»; саябақтағы сынған урна — «Аулалар мен алаңдар».",
      "Жылу, су, кәріз, лифт, шатыр — «ТКШ».",
      "Мәселесі жоқ алғыс не мерзім туралы сұрақ — «Басқа».",
      "Жарнама, тест, мағынасыз мәтін, қалаға қатысы жоқ — «Шағым емес» (N)."
    ]
  };

  /* ---------- иконки: собственный небольшой набор, рисованный штрихом 24×24 ---------- */
  var ICONS = {
    road: '<path d="M8 3 4 21M16 3l4 18M12 4v3M12 10.5v3M12 17v3"/>',
    snowflake: '<path d="M12 2v20M3.5 7l17 10M20.5 7l-17 10M9.5 3.5 12 6l2.5-2.5M9.5 20.5 12 18l2.5 2.5"/>',
    walk: '<circle cx="13" cy="4.5" r="2"/><path d="M10 21l2.2-6.2L10 12l1-4.5 3.5 2.5L18 11M8 12.5 6.5 16"/>',
    bus: '<rect x="5" y="3" width="14" height="15" rx="2.5"/><path d="M5 11h14M8 18v3M16 18v3M8.5 14.5h.01M15.5 14.5h.01"/>',
    bulb: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.8 10.6c.6.6.8 1.3.8 2.4h6c0-1.1.2-1.8.8-2.4A6 6 0 0 0 12 3z"/>',
    trees: '<path d="M12 3 7 10h3l-4 6h12l-4-6h3zM12 16v5"/>',
    trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6M14 11v6"/>',
    droplet: '<path d="M12 3s6 7 6 11a6 6 0 0 1-12 0c0-4 6-11 6-11z"/>',
    wind: '<path d="M3 8h10a3 3 0 1 0-3-3M3 12h15a3 3 0 1 1-3 3M3 16h7"/>',
    shield: '<path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z"/><path d="M12 8v5M12 16h.01"/>',
    parking: '<rect x="4" y="3" width="16" height="18" rx="3"/><path d="M10 17V7h3a3 3 0 0 1 0 6h-3"/>',
    dots: '<path d="M6 12h.01M12 12h.01M18 12h.01"/>',
    ban: '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
    flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
    skip: '<path d="M5 5l9 7-9 7zM18 5v14"/>',
    undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    left: '<path d="M15 5l-7 7 7 7"/>',
    right: '<path d="M9 5l7 7-7 7"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01"/>',
    download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    upload: '<path d="M12 20V9M7 14l5-5 5 5M5 4h14"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7"/>'
  };
  function icon(name) {
    return '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + (ICONS[name] || ICONS.dots) + "</svg>";
  }

  /* ---------- состояние ---------- */
  var uiLang = readLS(UI_LANG_KEY) === "kk" ? "kk" : "ru";
  var S = null;          // текущая сессия разметки
  var shownAt = 0;       // когда текущий текст появился на экране (для скорости)
  var pendingUnsure = false;
  var storageOk = true;
  var $ = function (id) { return document.getElementById(id); };

  function t(key, params) {
    var s = (STR[uiLang] && STR[uiLang][key]);
    if (s == null) { s = STR.ru[key]; if (s == null) { console.warn("[labeling] нет строки", key); s = key; } }
    if (params) s = s.replace(/\{(\w+)\}/g, function (m, k) { return params[k] != null ? params[k] : m; });
    return s;
  }
  function catName(id, lang) {
    if (id === C.NOT_COMPLAINT) return STR[lang || uiLang].notComplaintName;
    for (var i = 0; i < CATS.length; i++) if (CATS[i].id === id) return CATS[i][lang || uiLang];
    return id;
  }
  function fmtNum(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " "); }

  /* ---------- localStorage с защитой (приватный режим, переполнение) ---------- */
  function readLS(key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } }
  function writeLS(key, value) {
    try { window.localStorage.setItem(key, value); return true; } catch (e) { return false; }
  }
  function removeLS(key) { try { window.localStorage.removeItem(key); } catch (e) { /* нет доступа */ } }
  function readIndex() {
    try { return JSON.parse(readLS(INDEX_KEY) || "[]") || []; } catch (e) { return []; }
  }

  function save() {
    if (!S) return;
    S.updatedAt = new Date().toISOString();
    var full = JSON.stringify(S);
    var ok = writeLS(S.key, full);
    if (!ok) {
      // Тексты не поместились — храним только метки; при возврате попросим открыть файл заново.
      var light = {}; for (var k in S) if (k !== "items") light[k] = S[k];
      light.itemsStored = false;
      light.itemIds = S.items.map(function (it) { return it.id; });
      ok = writeLS(S.key, JSON.stringify(light));
    }
    storageOk = ok;
    $("storageBanner").hidden = ok;
    var c = C.counts(S.items, S.labels, S.skipped);
    var idx = readIndex().filter(function (e) { return e.key !== S.key; });
    idx.unshift({ key: S.key, fileName: S.fileName, mode: S.mode, annotator: S.annotator, total: c.total, done: c.done, updated: S.updatedAt });
    writeLS(INDEX_KEY, JSON.stringify(idx.slice(0, 12)));
  }

  /* ---------- экран выбора ---------- */
  function selectedRole() {
    var r = document.querySelector('input[name="role"]:checked');
    return r ? r.value : "first";
  }

  function renderResume() {
    var idx = readIndex().filter(function (e) { return readLS(e.key); });
    var box = $("resumeBox"), list = $("resumeList");
    list.innerHTML = "";
    box.hidden = !idx.length;
    idx.forEach(function (e) {
      var row = document.createElement("div");
      row.className = "resume-row";
      var b = document.createElement("button");
      b.type = "button"; b.className = "btn resume-btn";
      b.textContent = t("resumeItem", { file: e.fileName, role: e.mode === "second" ? t("roleSecondShort") : t("roleFirstShort"),
        done: fmtNum(e.done), total: fmtNum(e.total) });
      b.addEventListener("click", function () { resumeSession(e.key); });
      var del = document.createElement("button");
      del.type = "button"; del.className = "btn ghost small"; del.textContent = t("deleteSession");
      del.addEventListener("click", function () {
        if (!window.confirm(t("confirmDelete", { file: e.fileName }))) return;
        removeLS(e.key);
        writeLS(INDEX_KEY, JSON.stringify(readIndex().filter(function (x) { return x.key !== e.key; })));
        renderResume();
      });
      row.appendChild(b); row.appendChild(del);
      list.appendChild(row);
    });
  }

  var pendingResume = null; // сессия без текстов: ждём, пока человек откроет тот же файл

  function resumeSession(key) {
    var raw = readLS(key);
    if (!raw) { renderResume(); return; }
    var s; try { s = JSON.parse(raw); } catch (e) { showStartError(t("errRead")); return; }
    if (s.itemsStored === false) {
      pendingResume = s;
      showStartError(t("needFile", { file: s.fileName }));
      $("fileInput").click();
      return;
    }
    startSession(s);
  }

  function showStartError(msg) {
    var el = $("startError");
    el.textContent = msg; el.hidden = !msg;
  }

  function handleFile(file) {
    showStartError("");
    var reader = new FileReader();
    reader.onerror = function () { showStartError(t("errRead")); };
    reader.onload = function () {
      var parsed;
      try { parsed = C.parseFile(file.name, String(reader.result)); } catch (e) { showStartError(t("errRead")); return; }
      if (!parsed.items.length) { showStartError(t("errEmpty")); return; }
      openParsed(file.name, parsed);
    };
    reader.readAsText(file, "utf-8");
  }

  function openParsed(fileName, parsed) {
    var role = pendingResume ? pendingResume.mode : selectedRole();
    var items = parsed.items;
    var note = [t("loaded", { n: fmtNum(items.length) })];
    if (parsed.duplicates) note.push(t("dupes", { n: parsed.duplicates }));
    if (parsed.empty) note.push(t("empty", { n: parsed.empty }));
    if (parsed.badLines) note.push(t("bad", { n: parsed.badLines }));
    if (parsed.truncated) note.push(t("truncated", { n: parsed.truncated }));
    var seed = "";
    if (role === "second") {
      seed = pendingResume ? pendingResume.subsetSeed : ($("subsetSeed").value.trim() || "birge-2026");
      var size = pendingResume ? pendingResume.itemIds.length : parseInt($("subsetSize").value, 10) || 100;
      var total = items.length;
      items = C.blindItems(C.selectSubset(items, size, seed));
      note.push(t("subsetMade", { n: items.length, total: total }));
    }
    var fp = C.fingerprint(items);
    var key = STORE_PREFIX + fp + ":" + role;
    if (pendingResume) {
      if (pendingResume.key !== key) { showStartError(t("errMismatch", { file: pendingResume.fileName })); pendingResume = null; return; }
      var s = pendingResume; pendingResume = null;
      delete s.itemsStored; delete s.itemIds;
      s.items = items;
      startSession(s, note);
      return;
    }
    // Тот же файл уже размечался в этой роли — продолжаем, ничего не теряя.
    var existing = readLS(key);
    if (existing) {
      try {
        var old = JSON.parse(existing);
        old.items = items; delete old.itemsStored; delete old.itemIds;
        startSession(old, note);
        return;
      } catch (e) { /* испорченная запись — начинаем заново */ }
    }
    var labels = {};
    if (role === "first") {
      // Готовые метки берём только из НАШЕГО экспорта (продолжение после очистки браузера).
      var prior = 0;
      items.forEach(function (it) {
        if (it.prior) { labels[it.id] = { label: it.prior.label, unsure: it.prior.unsure, at: it.prior.at, ms: null }; prior++; }
        delete it.prior;
      });
      if (prior) note.push(t("priorLoaded", { n: prior }));
    }
    startSession({
      v: 1, key: key, fileName: fileName, fingerprint: fp, mode: role,
      annotator: ($("annotatorInput").value.trim() || (role === "second" ? "B" : "A")).slice(0, 24),
      subsetSeed: seed, items: items, labels: labels, skipped: {}, langs: {}, history: [], pos: -1,
      createdAt: new Date().toISOString(), exportedDone: 0
    }, note);
  }

  /* ---------- экран разметки ---------- */
  function startSession(s, note) {
    S = s;
    S.langs = S.langs || {}; S.skipped = S.skipped || {}; S.history = S.history || []; S.labels = S.labels || {};
    if (S.exportedDone == null) S.exportedDone = 0;
    if (S.pos == null || S.pos < 0 || S.pos >= S.items.length || S.labels[S.items[S.pos].id]) {
      S.pos = C.nextOpenIndex(S.items, S.labels, S.skipped, -1);
    }
    $("startScreen").hidden = true;
    $("workScreen").hidden = false;
    ["sessionInfo", "progressText", "bar", "exportBtn", "closeBtn"].forEach(function (id) { $(id).hidden = false; });
    save();
    render();
    if (note && note.length) toast(note.join(" · "), 4000);
  }

  function closeSession() {
    save();
    S = null;
    $("workScreen").hidden = true;
    $("startScreen").hidden = false;
    ["sessionInfo", "progressText", "bar", "exportBtn", "closeBtn"].forEach(function (id) { $(id).hidden = true; });
    $("fileInput").value = "";
    renderResume();
  }

  function current() { return S && S.pos >= 0 ? S.items[S.pos] : null; }

  function itemLang(it) { return S.langs[it.id] || (S.labels[it.id] && S.labels[it.id].lang) || it.lang || ""; }

  function renderCats() {
    var box = $("cats");
    box.innerHTML = "";
    CATS.forEach(function (c, i) {
      var key = C.CATEGORY_KEYS[i];
      var b = document.createElement("button");
      b.type = "button"; b.className = "cat"; b.dataset.cat = c.id;
      b.setAttribute("aria-keyshortcuts", key ? key.label : "");
      var other = uiLang === "ru" ? "kk" : "ru";
      b.innerHTML = '<kbd class="cat-key">' + (key ? key.label : "") + "</kbd>" + icon(c.icon) +
        '<span class="cat-names"><span class="cat-name"></span><span class="cat-alt"></span></span>';
      b.querySelector(".cat-name").textContent = c[uiLang];
      b.querySelector(".cat-alt").textContent = c[other];
      b.title = c.examples_ru || "";
      b.addEventListener("click", function () { label(c.id); blurActive(); });
      box.appendChild(b);
    });
  }

  function render() {
    if (!S) return;
    var c = C.counts(S.items, S.labels, S.skipped);
    $("fileName").textContent = S.fileName;
    $("roleChip").textContent = S.mode === "second"
      ? t("roleChipSecond", { name: S.annotator, seed: S.subsetSeed }) : t("roleChipFirst", { name: S.annotator });
    $("progressText").textContent = t("progress", { done: fmtNum(c.done), total: fmtNum(c.total) });
    $("barFill").style.width = (c.total ? (100 * c.done / c.total) : 0).toFixed(1) + "%";
    var sinceExport = c.done - (S.exportedDone || 0);
    $("exportBtn").classList.toggle("nudge", sinceExport >= EXPORT_NUDGE);
    $("exportBtn").title = sinceExport >= EXPORT_NUDGE ? t("exportNudge", { n: sinceExport }) : "";

    var it = current();
    var finished = !it;
    $("textCard").hidden = finished;
    $("finishCard").hidden = !finished;
    $("cats").classList.toggle("disabled", finished);
    if (finished) { renderFinish(c); renderSpeed(c); return; }

    $("itemNum").textContent = t("itemNum", { n: fmtNum(S.pos + 1), total: fmtNum(c.total) });
    var lang = itemLang(it);
    $("langChip").textContent = t("lang_" + (lang || ""));
    $("districtChip").hidden = !it.district;
    $("districtChip").textContent = it.district || "";
    $("itemId").textContent = it.id;
    $("itemText").textContent = it.text;
    var lab = S.labels[it.id];
    var unsure = lab ? !!lab.unsure : pendingUnsure;
    $("unsureChip").hidden = !unsure;
    $("unsureBtn").setAttribute("aria-pressed", unsure ? "true" : "false");
    $("unsureBtn").classList.toggle("on", unsure);
    $("labelChip").hidden = !lab && !S.skipped[it.id];
    $("labelChip").textContent = lab ? t("labelIs", { label: catName(lab.label) }) : t("skippedIs");
    var btns = document.querySelectorAll(".cat");
    for (var i = 0; i < btns.length; i++) btns[i].classList.toggle("chosen", !!lab && lab.label === btns[i].dataset.cat);
    $("notComplaintBtn").classList.toggle("chosen", !!lab && lab.label === C.NOT_COMPLAINT);
    $("undoBtn").disabled = !S.history.length;
    renderSpeed(c);
  }

  function renderSpeed(c) {
    var ms = [];
    S.items.forEach(function (it) { var l = S.labels[it.id]; if (l && l.ms != null) ms.push(l.ms); });
    var recent = ms.slice(-40);
    var med = C.median(recent);
    if (med == null || recent.length < 5 || !c.open) { $("speedInfo").textContent = ""; return; }
    $("speedInfo").textContent = t("speed", { sec: Math.round(med / 1000), min: Math.max(1, Math.round(med * c.open / 60000)) });
  }

  function renderFinish(c) {
    var allSkipped = c.open === 0 && c.skipped > 0;
    $("finishTitle").textContent = allSkipped ? t("finishSkipped") : t("finishTitle");
    $("finishStats").textContent = t("finishStats", { done: fmtNum(c.done), total: fmtNum(c.total), skipped: c.skipped });
    var back = $("backToSkipped");
    back.hidden = !c.skipped;
    back.textContent = t("backToSkipped", { n: c.skipped });
    var box = $("byLabel");
    box.innerHTML = "";
    CATS.map(function (x) { return x.id; }).concat([C.NOT_COMPLAINT]).forEach(function (id) {
      var n = c.byLabel[id] || 0;
      var row = document.createElement("div");
      row.className = "by-row";
      row.innerHTML = "<span></span><b></b>";
      row.firstChild.textContent = catName(id);
      row.lastChild.textContent = fmtNum(n);
      box.appendChild(row);
    });
  }

  /* ---------- действия ---------- */
  function remember(it) {
    S.history.push({ id: it.id, before: S.labels[it.id] || null, skipped: !!S.skipped[it.id], lang: S.langs[it.id] || null });
    if (S.history.length > 500) S.history.shift();
  }

  function advance() {
    var nxt = C.nextOpenIndex(S.items, S.labels, S.skipped, S.pos);
    S.pos = nxt;
    pendingUnsure = false;
    shownAt = performance.now();
  }

  function label(catId) {
    var it = current();
    if (!it) return;
    remember(it);
    var prev = S.labels[it.id];
    var ms = Math.round(performance.now() - shownAt);
    S.labels[it.id] = {
      label: catId,
      unsure: prev ? !!prev.unsure : pendingUnsure,
      lang: itemLang(it),
      at: new Date().toISOString(),
      ms: prev ? prev.ms : (ms > 0 && ms < MAX_MS ? ms : null)
    };
    delete S.skipped[it.id];
    advance();
    save(); render();
    toast(t("saved", { label: catName(catId) }), 900);
  }

  function skip() {
    var it = current();
    if (!it) return;
    remember(it);
    if (!S.labels[it.id]) S.skipped[it.id] = true;
    advance();
    save(); render();
    toast(t("skipped"), 700);
  }

  function undo() {
    if (!S || !S.history.length) { toast(t("nothingToUndo"), 900); return; }
    var h = S.history.pop();
    if (h.before) S.labels[h.id] = h.before; else delete S.labels[h.id];
    if (h.skipped) S.skipped[h.id] = true; else delete S.skipped[h.id];
    if (h.lang) S.langs[h.id] = h.lang; else delete S.langs[h.id];
    for (var i = 0; i < S.items.length; i++) if (S.items[i].id === h.id) { S.pos = i; break; }
    pendingUnsure = false;
    shownAt = performance.now();
    save(); render();
    toast(t("undone", { n: S.pos + 1 }), 1200);
  }

  function toggleUnsure() {
    var it = current();
    if (!it) return;
    var lab = S.labels[it.id];
    if (lab) { lab.unsure = !lab.unsure; save(); } else pendingUnsure = !pendingUnsure;
    render();
  }

  function cycleLang() {
    var it = current();
    if (!it) return;
    var cur = itemLang(it);
    var next = LANG_CYCLE[(LANG_CYCLE.indexOf(cur) + 1) % LANG_CYCLE.length];
    S.langs[it.id] = next;
    if (S.labels[it.id]) S.labels[it.id].lang = next;
    save(); render();
  }

  function move(delta) {
    if (!S || !S.items.length) return;
    var p = S.pos < 0 ? (delta > 0 ? -1 : S.items.length) : S.pos;
    p = Math.max(0, Math.min(S.items.length - 1, p + delta));
    S.pos = p;
    pendingUnsure = false;
    shownAt = performance.now();
    save(); render();
  }

  function backToSkipped() {
    S.skipped = {};
    S.pos = C.nextOpenIndex(S.items, S.labels, S.skipped, -1);
    shownAt = performance.now();
    save(); render();
  }

  function download(name, text) {
    var blob = new Blob([text], { type: "application/x-ndjson;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  function stamp() {
    var d = new Date(), p = function (n) { return (n < 10 ? "0" : "") + n; };
    return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + "-" + p(d.getHours()) + p(d.getMinutes());
  }

  function exportNow() {
    if (!S) return;
    var base = S.fileName.replace(/\.[^.]+$/, "");
    var name = "birge-labels_" + C.safeName(S.annotator) + "_" + (S.mode === "second" ? "second" : "first") + "_" +
      C.safeName(base) + "_" + stamp() + ".jsonl";
    download(name, C.exportLines(S));
    S.exportedDone = C.counts(S.items, S.labels, S.skipped).done;
    S.lastExportAt = new Date().toISOString();
    save(); render();
    toast(t("exported", { name: name }), 2500);
  }

  /* ---------- клавиатура ---------- */
  function blurActive() {
    if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur();
  }

  function onKey(e) {
    var tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    var helpOpen = !$("helpOverlay").hidden;
    if (e.code === "Escape" && helpOpen) { e.preventDefault(); showHelp(false); return; }
    if (e.code === "Slash" && e.shiftKey || e.code === "F1") { e.preventDefault(); showHelp(!helpOpen); return; }
    if (helpOpen || !S) return;
    if ((e.ctrlKey || e.metaKey) && e.code === "KeyS") { e.preventDefault(); exportNow(); return; }
    if ((e.ctrlKey || e.metaKey) && e.code === "KeyZ") { e.preventDefault(); undo(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    for (var i = 0; i < C.CATEGORY_KEYS.length && i < CATS.length; i++) {
      var k = C.CATEGORY_KEYS[i];
      if (e.code === k.code || e.code === k.alt) { e.preventDefault(); if (!e.repeat) label(CATS[i].id); return; }
    }
    switch (e.code) {
      case "KeyN": e.preventDefault(); if (!e.repeat) label(C.NOT_COMPLAINT); return;
      case "Space": e.preventDefault(); if (!e.repeat) skip(); return;
      case "Backspace": case "KeyZ": e.preventDefault(); if (!e.repeat) undo(); return;
      case "KeyF": e.preventDefault(); toggleUnsure(); return;
      case "KeyL": e.preventDefault(); cycleLang(); return;
      case "ArrowLeft": e.preventDefault(); move(-1); return;
      case "ArrowRight": e.preventDefault(); move(1); return;
    }
  }

  /* ---------- справка ---------- */
  function renderHelp() {
    var rows = [
      ["1 … 9, 0, -, =", t("k_cat")], ["N", t("k_n")], ["F", t("k_f")], [t("spaceKey"), t("k_space")],
      ["⌫ / Z / Ctrl+Z", t("k_undo")], ["← →", t("k_arrows")], ["L", t("k_l")], ["Ctrl+S", t("k_save")],
      ["?", t("k_help")], ["Esc", t("k_esc")]
    ];
    var tbl = $("keysTable");
    tbl.innerHTML = "";
    CATS.forEach(function (c, i) {
      var tr = document.createElement("tr");
      tr.innerHTML = "<td><kbd></kbd></td><td></td>";
      tr.querySelector("kbd").textContent = C.CATEGORY_KEYS[i] ? C.CATEGORY_KEYS[i].label : "";
      tr.lastChild.textContent = c[uiLang];
      tbl.appendChild(tr);
    });
    rows.slice(1).forEach(function (r) {
      var tr = document.createElement("tr");
      tr.innerHTML = "<td><kbd></kbd></td><td></td>";
      tr.querySelector("kbd").textContent = r[0];
      tr.lastChild.textContent = r[1];
      tbl.appendChild(tr);
    });
    var ul = $("casesList");
    ul.innerHTML = "";
    CASES[uiLang].forEach(function (s) { var li = document.createElement("li"); li.textContent = s; ul.appendChild(li); });
  }

  var lastFocus = null;
  function showHelp(open) {
    var ov = $("helpOverlay");
    if (open) { lastFocus = document.activeElement; renderHelp(); ov.hidden = false; $("helpClose").focus(); }
    else { ov.hidden = true; if (lastFocus && lastFocus.focus) lastFocus.focus(); else blurActive(); }
  }

  /* ---------- тост ---------- */
  var toastTimer = null;
  function toast(msg, ms) {
    var el = $("toast");
    el.textContent = msg;
    el.hidden = false;
    el.classList.remove("out");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.add("out"); toastTimer = setTimeout(function () { el.hidden = true; }, 250); }, ms || 1500);
  }

  /* ---------- язык интерфейса ---------- */
  function applyLang() {
    document.documentElement.lang = uiLang;
    document.title = "Birge · " + t("title");
    var nodes = document.querySelectorAll("[data-t]");
    for (var i = 0; i < nodes.length; i++) nodes[i].textContent = t(nodes[i].getAttribute("data-t"));
    var langs = document.querySelectorAll(".lang");
    for (i = 0; i < langs.length; i++) {
      var on = langs[i].dataset.lang === uiLang;
      langs[i].classList.toggle("on", on);
      langs[i].setAttribute("aria-pressed", on ? "true" : "false");
    }
    renderCats();
    renderResume();
    if (S) render();
    if (!$("helpOverlay").hidden) renderHelp();
  }

  /* ---------- запуск ---------- */
  function init() {
    var slots = document.querySelectorAll(".ic-slot");
    for (var i = 0; i < slots.length; i++) slots[i].outerHTML = icon(slots[i].getAttribute("data-icon"));
    if (!CATS.length) { showStartError("categories.js не загружен"); return; }
    if (!writeLS(STORE_PREFIX + "probe", "1")) { storageOk = false; $("storageBanner").hidden = false; }
    removeLS(STORE_PREFIX + "probe");

    document.querySelectorAll(".lang").forEach(function (b) {
      b.addEventListener("click", function () { uiLang = b.dataset.lang; writeLS(UI_LANG_KEY, uiLang); applyLang(); blurActive(); });
    });
    document.querySelectorAll('input[name="role"]').forEach(function (r) {
      r.addEventListener("change", function () {
        var second = selectedRole() === "second";
        $("subsetFields").hidden = !second;
        var name = $("annotatorInput");
        if (second && name.value === "A") name.value = "B";
        if (!second && name.value === "B") name.value = "A";
      });
    });
    $("openBtn").addEventListener("click", function () { pendingResume = null; $("fileInput").click(); });
    $("fileInput").addEventListener("change", function (e) { if (e.target.files[0]) handleFile(e.target.files[0]); });
    var dz = $("dropZone");
    ["dragenter", "dragover"].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add("over"); }); });
    ["dragleave", "drop"].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove("over"); }); });
    dz.addEventListener("drop", function (e) { var f = e.dataTransfer && e.dataTransfer.files[0]; if (f) handleFile(f); });

    $("notComplaintBtn").addEventListener("click", function () { label(C.NOT_COMPLAINT); blurActive(); });
    $("unsureBtn").addEventListener("click", function () { toggleUnsure(); blurActive(); });
    $("skipBtn").addEventListener("click", function () { skip(); blurActive(); });
    $("undoBtn").addEventListener("click", function () { undo(); blurActive(); });
    $("prevBtn").addEventListener("click", function () { move(-1); blurActive(); });
    $("nextBtn").addEventListener("click", function () { move(1); blurActive(); });
    $("langChip").addEventListener("click", function () { cycleLang(); blurActive(); });
    $("exportBtn").addEventListener("click", function () { exportNow(); blurActive(); });
    $("finishExport").addEventListener("click", exportNow);
    $("backToSkipped").addEventListener("click", function () { backToSkipped(); blurActive(); });
    $("closeBtn").addEventListener("click", closeSession);
    $("helpBtn").addEventListener("click", function () { showHelp(true); });
    $("helpClose").addEventListener("click", function () { showHelp(false); });
    $("helpOverlay").addEventListener("click", function (e) { if (e.target === $("helpOverlay")) showHelp(false); });
    document.addEventListener("keydown", onKey);
    window.addEventListener("beforeunload", save);
    applyLang();
    shownAt = performance.now();
  }

  // Для автотестов: доступ к состоянию без изменения поведения.
  window.BirgeLabeling = { state: function () { return S; }, exportText: function () { return S ? C.exportLines(S) : ""; },
    openText: function (name, text) { openParsed(name, C.parseFile(name, text)); } };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
