/*
 * Birge · 3D-превью предложений (R05, раунд 14).
 *
 * Акимат выбирает объект в нижней панели → полупрозрачный «призрак» идёт за курсором (на телефоне —
 * за центром карты, касание ставит его в точку) → поворот ↺ ↻ → «Поставить» → объект «строится»
 * снизу вверх за ~1.2 с с лёгкой пылью → над ним табличка «Проект · 2027». Жители голосуют в карточке.
 *
 * Подключение (порядок важен; three.js грузится сам, только когда модуль смонтирован):
 *   <link rel="stylesheet" href="/civic/build3d/build3d.css">
 *   <script src="/civic/build3d/build3d-core.js"></script>
 *   <script src="/civic/build3d/build3d-models.js"></script>
 *   <script src="/civic/build3d/build3d.js"></script>
 *   const handle = CivicBuild3D.mount({ map, root, role: "akimat" });
 *
 * Опции mount:
 *   map        — карта MapLibre (обязательно);
 *   root       — элемент для нижней панели и карточки (по умолчанию — внутри контейнера карты);
 *   role       — "akimat" (каталог, удаление) | "resident" (только просмотр и голос);
 *   store      — "auto" (API R06, если есть, иначе заглушка этого устройства) | "api" | "local" | объект;
 *   apiPrefix  — "/api/civic/v2";  threeUrl — "/vendor/three/three.module.min.js";
 *   dataUrl    — папка data/ модуля ("/civic/build3d/data/");
 *   streets    — свой источник улиц {nearest(lngLat, maxM, name?), section(a, b)} (например, R12 /targets);
 *   year       — год на табличке (2027);  autoZoom — приблизить карту, если она дальше 15.5 (true);
 *   buildMs    — длительность анимации постройки (1200 мс);
 *   onToolChange(active, kind) — модуль взял/отдал щелчки по карте (R01: map.setInteractionEnabled);
 *   onSelect(proposal|null)    — выбрано предложение (R06 может показать свою карточку);
 *   renderCard: false          — не показывать встроенную карточку (её рисует R06).
 *   avoid: () => [элементы]    — элементы хозяина поверх карты (шапка, панели, кнопки карты R01): модуль ставит
 *                                объект при открытой карточке в свободную часть карты, а в режиме overlay — и свою
 *                                панель (справа от панели / над шторкой);
 *   dock: false                — спрятать каталог/подсказку (объекты, подписи и карточка по нажатию — видны);
 *   mode                       — "akimat" | "resident" (как у оболочки R01; role — старое имя), событие "birge:mode";
 *   api                        — клиент оболочки R01 ({v2(method, path, body)}); map — карта или функция map().
 *
 * Handle: start(kind), cancel(), select(id), flyToProposals(), setMode(mode), update({mode, dock, visible}), refresh(),
 *         setVisible(bool), getState(), destroy().
 * Событие для соседей: document "civic-build3d:tool" {active, kind} — как "civic-editor:tool" у редактора.
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var Core = root.CivicBuild3DCore;
  var ModelsLib = root.CivicBuild3DModels;
  var DEG = Math.PI / 180;

  // ───────────── Тексты ─────────────
  // Общие ключи (proposal.*, common.*) уже есть в словарях R11. Новые ключи build3d.* переданы R11
  // в research/round-14-results/R05/INTEGRATION.txt; пока их нет в общем словаре — берём отсюда.
  var STRINGS = {
    ru: {
      "build3d.loading": "Загружаем 3D…",
      "build3d.unsupported_title": "Объёмный вид недоступен",
      "build3d.unsupported_text": "Браузер не поддерживает 3D. Откройте карту в Chrome, Edge или Firefox.",
      "build3d.load_failed": "Не получилось загрузить 3D. Проверьте связь и повторите.",
      "build3d.hint.rotate": "Поверните и нажмите «Поставить»",
      "build3d.hint.touch": "Двигайте карту или коснитесь места. Затем нажмите «Поставить»",
      "build3d.hint.segment_start": "Нажмите на улицу — начало участка",
      "build3d.hint.segment_end": "Теперь выберите конец участка: {street}",
      "build3d.hint.segment_ready": "{street}, {length} м · {poles}. Нажмите «Поставить»",
      "build3d.poles": { one: "{n} фонарь", few: "{n} фонаря", many: "{n} фонарей" },
      "build3d.cluster": { one: "{n} проект", few: "{n} проекта", many: "{n} проектов" },
      "build3d.cluster.open": "{count} рядом — показать ближе",
      "build3d.err.far_from_street": "Нажмите ближе к улице",
      "build3d.err.other_street": "Выберите конец на той же улице: {street}",
      "build3d.err.too_short": "Участок слишком короткий. Выберите точки дальше друг от друга",
      "build3d.err.too_long": "Участок длиннее 900 м. Выберите точки ближе",
      "build3d.err.no_path": "Не нашли путь по этой улице. Выберите другие точки",
      "build3d.err.no_streets": "Освещение пока можно предложить только в районе Нура",
      "build3d.err.outside_city": "Это место за пределами Астаны. Выберите место в городе",
      "build3d.err.overlap": "Здесь уже стоит другой проект. Сдвиньте объект",
      "build3d.placed": "Проект поставлен",
      "build3d.placed_local": "Проект поставлен и сохранён на этом устройстве",
      "build3d.deleted": "Проект удалён",
      "build3d.save_failed": "Не удалось сохранить. Проверьте связь и повторите",
      "build3d.vote_failed": "Голос не отправлен. Повторите",
      "build3d.card.near": "Рядом: {street}",
      "build3d.card.segment": "Участок: {street}, {length} м",
      "build3d.card.segment_plain": "Участок улицы, {length} м",
      "build3d.street.this": "эта улица",
      "build3d.card.your_vote_up": "Ваш голос: за",
      "build3d.card.your_vote_down": "Ваш голос: против",
      "build3d.card.open": "{kind}: проект {year}, открыть карточку",
      "build3d.catalog.place": "{kind}: поставить на карту",
      "build3d.local_note": "Сохраняется только на этом устройстве, пока не подключён сервер предложений",
      "build3d.near.stop": "Рядом уже есть остановка, {m} м",
      "build3d.near.stop_named": "Рядом уже есть остановка: «{name}», {m} м",
      "build3d.near.playground": "Рядом уже есть детская площадка, {m} м",
      "build3d.near.sports": "Рядом уже есть спортплощадка, {m} м",
      "build3d.near.square": "Рядом уже есть парк или сквер, {m} м",
      "build3d.near.square_named": "Рядом уже есть парк или сквер: «{name}», {m} м",
      "build3d.near.square_inside": "Это место внутри существующего парка или сквера",
      "build3d.near.lamps": "На участке уже отмечены фонари: {n}",
      "build3d.near.source": "по данным OpenStreetMap",
      "build3d.card.yard": "Двор: {name}",
      "build3d.resident.hint": "Нажмите на проект, чтобы проголосовать",
      "build3d.resident.empty": "Здесь пока нет проектов",
      "build3d.demo.title": "3D-превью",
    },
    kk: {
      "build3d.loading": "3D жүктеліп жатыр…",
      "build3d.unsupported_title": "Көлемді көрініс қолжетімсіз",
      "build3d.unsupported_text": "Браузер көлемді көріністі қолдамайды. Картаны Chrome, Edge немесе Firefox-та ашыңыз.",
      "build3d.load_failed": "3D көрініс жүктелмеді. Байланысты тексеріп, қайталаңыз.",
      "build3d.hint.rotate": "Бұрып, «Орнату» түймесін басыңыз",
      "build3d.hint.touch": "Картаны жылжытыңыз немесе орынды түртіңіз. Содан кейін «Орнату» түймесін басыңыз",
      "build3d.hint.segment_start": "Көшені басыңыз — бөліктің басы",
      "build3d.hint.segment_end": "Енді бөліктің соңын таңдаңыз: {street}",
      "build3d.hint.segment_ready": "{street}, {length} м · {poles}. «Орнату» түймесін басыңыз",
      "build3d.poles": "{n} шам",
      "build3d.cluster": "{n} жоба",
      "build3d.cluster.open": "Жақын жерде {count} — жақындатып көрсету",
      "build3d.err.far_from_street": "Көшеге жақынырақ басыңыз",
      "build3d.err.other_street": "Соңын сол көшеден таңдаңыз: {street}",
      "build3d.err.too_short": "Бөлік тым қысқа. Нүктелерді бір-бірінен алысырақ таңдаңыз",
      "build3d.err.too_long": "Бөлік 900 м-ден ұзын. Нүктелерді жақынырақ таңдаңыз",
      "build3d.err.no_path": "Осы көше бойымен жол табылмады. Басқа нүктелерді таңдаңыз",
      "build3d.err.no_streets": "Жарықтандыруды әзірге тек Нұра ауданында ұсынуға болады",
      "build3d.err.outside_city": "Бұл жер Астанаға кірмейді. Қала ішінен орын таңдаңыз",
      "build3d.err.overlap": "Бұл жерде басқа жоба тұр. Нысанды жылжытыңыз",
      "build3d.placed": "Жоба орнатылды",
      "build3d.placed_local": "Жоба орнатылып, осы құрылғыда сақталды",
      "build3d.deleted": "Жоба жойылды",
      "build3d.save_failed": "Сақтау мүмкін болмады. Байланысты тексеріп, қайталаңыз",
      "build3d.vote_failed": "Дауыс жіберілмеді. Қайталап көріңіз",
      "build3d.card.near": "Жанында: {street}",
      "build3d.card.segment": "Бөлік: {street}, {length} м",
      "build3d.card.segment_plain": "Көше бөлігі, {length} м",
      "build3d.street.this": "осы көше",
      "build3d.card.your_vote_up": "Сіздің дауысыңыз: жақтаймын",
      "build3d.card.your_vote_down": "Сіздің дауысыңыз: қарсымын",
      "build3d.card.open": "{kind}: {year} жылғы жоба, карточканы ашу",
      "build3d.catalog.place": "{kind}: картаға қою",
      "build3d.local_note": "Ұсыныстар сервері қосылғанша тек осы құрылғыда сақталады",
      "build3d.near.stop": "Жанында аялдама бар, {m} м",
      "build3d.near.stop_named": "Жанында аялдама бар: «{name}», {m} м",
      "build3d.near.playground": "Жанында балалар алаңы бар, {m} м",
      "build3d.near.sports": "Жанында спорт алаңы бар, {m} м",
      "build3d.near.square": "Жанында саябақ немесе гүлзар бар, {m} м",
      "build3d.near.square_named": "Жанында саябақ немесе гүлзар бар: «{name}», {m} м",
      "build3d.near.square_inside": "Бұл орын бұрыннан бар саябақтың немесе гүлзардың ішінде",
      "build3d.near.lamps": "Бұл бөлікте шамдар бұрыннан белгіленген: {n}",
      "build3d.near.source": "OpenStreetMap деректері бойынша",
      "build3d.card.yard": "Аула: {name}",
      "build3d.resident.hint": "Дауыс беру үшін жобаны басыңыз",
      "build3d.resident.empty": "Мұнда әзірге жоба жоқ",
      "build3d.demo.title": "3D-көрініс",
    },
  };

  // Запасные значения общих ключей — на случай, если словари R11 ещё не загрузились или их нет.
  var COMMON_FALLBACK = {
    ru: {
      "proposal.catalog.title": "Что построить?",
      "proposal.kind.square": "Сквер",
      "proposal.kind.playground": "Детская площадка",
      "proposal.kind.sports": "Спортплощадка",
      "proposal.kind.stop": "Остановка",
      "proposal.kind.lighting": "Освещение улицы",
      "proposal.place_hint": "Нажмите на карту, где поставить",
      "proposal.rotate_left": "Повернуть влево",
      "proposal.rotate_right": "Повернуть вправо",
      "proposal.place": "Поставить",
      "proposal.delete": "Удалить",
      "proposal.label": "Проект · {year}",
      "proposal.vote_up": "За",
      "proposal.vote_down": "Против",
      "proposal.one_vote": "Один голос с устройства",
      "proposal.status.proposal": "Предложение",
      "proposal.limit": "Можно поставить до 20 объектов",
      "common.action.cancel": "Отменить",
      "common.action.close": "Закрыть",
      "common.action.retry": "Повторить",
      "common.tag.project": "Проект",
      "common.tag.demo": "Пример",
      "common.tag.demo_hint": "Пример для показа, не настоящие данные",
      "common.tag.project": "Проект",
      "proposal.status.approved": "Одобрено",
      "proposal.status.rejected": "Отклонено",
      "proposal.voting_closed": "Голосование по этому проекту закрыто",
      "proposal.need_staff": "Войдите как сотрудник акимата",
      // Общий ключ из предложения R15 (U1) для ответа 429 — пока его нет в словаре R11, текст отсюда.
      "common.error.too_many": "Слишком много действий подряд. Повторите через минуту.",
    },
    kk: {
      "proposal.catalog.title": "Не салайық?",
      "proposal.kind.square": "Гүлзар",
      "proposal.kind.playground": "Балалар алаңы",
      "proposal.kind.sports": "Спорт алаңы",
      "proposal.kind.stop": "Аялдама",
      "proposal.kind.lighting": "Көше жарығы",
      "proposal.place_hint": "Қай жерге қою керектігін картадан басыңыз",
      "proposal.rotate_left": "Солға бұру",
      "proposal.rotate_right": "Оңға бұру",
      "proposal.place": "Орнату",
      "proposal.delete": "Жою",
      "proposal.label": "Жоба · {year}",
      "proposal.vote_up": "Жақтаймын",
      "proposal.vote_down": "Қарсымын",
      "proposal.one_vote": "Бір құрылғыдан бір дауыс",
      "proposal.status.proposal": "Ұсыныс",
      "proposal.limit": "20 нысанға дейін қоюға болады",
      "common.action.cancel": "Болдырмау",
      "common.action.close": "Жабу",
      "common.action.retry": "Қайталау",
      "common.tag.project": "Жоба",
      "common.tag.demo": "Үлгі",
      "common.tag.demo_hint": "Көрсетуге арналған үлгі, нақты дерек емес",
      "common.tag.project": "Жоба",
      "proposal.status.approved": "Мақұлданды",
      "proposal.status.rejected": "Қабылданбады",
      "proposal.voting_closed": "Бұл жоба бойынша дауыс беру аяқталды",
      "proposal.need_staff": "Әкімдік қызметкері ретінде кіріңіз",
      "common.error.too_many": "Қатарынан тым көп әрекет жасалды. Бір минуттан кейін қайталаңыз.",
    },
  };

  function pluralRu(n) {
    var a = Math.abs(n) % 100,
      b = a % 10;
    if (a > 10 && a < 20) return "many";
    if (b === 1) return "one";
    if (b >= 2 && b <= 4) return "few";
    return "many";
  }
  function formatNumberLocal(v) {
    return String(Math.round(v)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }

  // Перевод: общий словарь R11, если в нём есть ключ; иначе — строки модуля. Никогда не показываем сам ключ.
  function makeT(i18n) {
    function lang() {
      var l = i18n && i18n.getLang ? i18n.getLang() : (doc && doc.documentElement.lang) || "ru";
      return l === "kk" ? "kk" : "ru";
    }
    function local(key, params) {
      var l = lang();
      var v = (STRINGS[l] && STRINGS[l][key]) || (COMMON_FALLBACK[l] && COMMON_FALLBACK[l][key]);
      if (v === undefined) v = (STRINGS.ru[key] || COMMON_FALLBACK.ru[key]);
      if (v === undefined) return "";
      if (typeof v === "object") {
        var n = params && params.n != null ? params.n : 0;
        v = l === "kk" ? v.other || v.many || v.one : v[pluralRu(n)] || v.many;
      }
      return String(v).replace(/\{(\w+)\}/g, function (all, name) {
        if (!params || params[name] == null) return all;
        var p = params[name];
        return typeof p === "number" ? (i18n && i18n.formatNumber ? i18n.formatNumber(p) : formatNumberLocal(p)) : String(p);
      });
    }
    var t = function (key, params) {
      if (i18n && typeof i18n.has === "function" && i18n.has(key)) return i18n.t(key, params);
      return local(key, params);
    };
    t.lang = lang;
    return t;
  }

  // ───────────── Мелочи DOM ─────────────

  function el(tag, cls, attrs) {
    var n = doc.createElement(tag);
    if (cls) n.className = cls;
    if (attrs)
      Object.keys(attrs).forEach(function (k) {
        if (attrs[k] === false || attrs[k] == null) return;
        if (k === "text") n.textContent = attrs[k];
        else n.setAttribute(k, attrs[k] === true ? "" : attrs[k]);
      });
    return n;
  }
  function icon(name, iconsUrl) {
    var NS = "http://www.w3.org/2000/svg";
    var svg = doc.createElementNS(NS, "svg");
    svg.setAttribute("class", "ic");
    svg.setAttribute("aria-hidden", "true");
    var use = doc.createElementNS(NS, "use");
    use.setAttribute("href", iconsUrl + "#i-" + name);
    svg.appendChild(use);
    return svg;
  }
  function reducedMotion() {
    try {
      return root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches;
    } catch (e) {
      return false;
    }
  }
  function hoverPointer() {
    try {
      return root.matchMedia && root.matchMedia("(hover: hover) and (pointer: fine)").matches;
    } catch (e) {
      return true;
    }
  }
  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }
  function easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }
  function easeOutBack(t) {
    var c1 = 1.4,
      c3 = c1 + 1;
    return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
  }
  function fetchJson(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status + " " + url);
      return r.json();
    });
  }

  var BUILD_MS = 1200; // анимация постройки
  var REMOVE_MS = 320;
  var ROTATE_STEP = 15;
  var PLACE_ZOOM = 17.5; // масштаб, на котором модели хорошо видны (UX_REVIEW день 3 #20)
  var VIEW_ZOOM = 17.4; // «показать проекты» — тот же крупный план
  var DOT_PX = 32; // сжатая подпись-точка: ≥ 24 px (UX_SPEC §5, R10 B-026), зона нажатия — 48 px
  var LAYER_ID = "civic-build3d";
  var OUTLINE_COLOR = 0x176b4a; // пунктир границы проекта (бренд)
  var OUTLINE_SELECTED = 0x2f7fd6; // выбранный проект — цвет фокуса ui-kit

  // ───────────── mount ─────────────

  // R01 передаёт карту функцией map() (null, пока карта грузится — как у R04 в раунде 13): ждём её до минуты
  // и только потом монтируем; до этого handle отвечает phase "waiting_map" и запоминает setVisible/setMode.
  function mount(opts) {
    opts = opts || {};
    if (typeof opts.map !== "function") return mountWithMap(opts);
    var getter = opts.map;
    var get = function () {
      try {
        return getter() || null;
      } catch (e) {
        return null;
      }
    };
    var now = get();
    if (now) return mountWithMap(Object.assign({}, opts, { map: now }));
    var inner = null,
      dead = false,
      queued = [],
      tries = 0,
      resolveReady;
    var ready = new Promise(function (r) {
      resolveReady = r;
    });
    var timer = setInterval(function () {
      var m = get();
      if (dead || (!m && ++tries < 240)) return;
      clearInterval(timer);
      if (dead || !m) return resolveReady(null);
      inner = mountWithMap(Object.assign({}, opts, { map: m }));
      queued.forEach(function (fn) {
        fn(inner);
      });
      inner.ready.then(resolveReady, resolveReady);
    }, 250);
    function later(name) {
      return function () {
        var args = arguments;
        if (inner) return inner[name].apply(inner, args);
        if (name === "update" || name === "setVisible" || name === "setMode")
          queued.push(function (h) {
            h[name].apply(h, args);
          });
        return name === "start" || name === "flyToProposals" ? false : undefined;
      };
    }
    return {
      ready: ready,
      start: later("start"),
      cancel: later("cancel"),
      select: later("select"),
      flyToProposals: later("flyToProposals"),
      refresh: later("refresh"),
      setVisible: later("setVisible"),
      setMode: later("setMode"),
      update: later("update"),
      getState: function () {
        return inner ? inner.getState() : { phase: "waiting_map", mode: "idle", count: 0, proposals: [], items: [] };
      },
      _project: later("_project"),
      destroy: function () {
        dead = true;
        clearInterval(timer);
        if (inner) inner.destroy();
      },
    };
  }

  function mountWithMap(opts) {
    opts = opts || {};
    var map = opts.map;
    if (!map || typeof map.addLayer !== "function") throw new Error("CivicBuild3D.mount: нужна карта MapLibre (opts.map)");
    if (!Core || !ModelsLib) throw new Error("CivicBuild3D: подключите build3d-core.js и build3d-models.js раньше build3d.js");

    var o = {
      // R01: «mode» — "akimat" | "resident" (переключатель в шапке); «role» — старое имя того же.
      role: (opts.mode || opts.role) === "resident" ? "resident" : "akimat",
      apiPrefix: opts.apiPrefix || "/api/civic/v2",
      geoPrefix: opts.geoPrefix || opts.apiPrefix || "/api/civic/v2", // маршруты R12 /street-snap, /street-segment
      threeUrl: opts.threeUrl || "/vendor/three/three.module.min.js",
      dataUrl: (opts.dataUrl || "/civic/build3d/data/").replace(/\/?$/, "/"),
      iconsUrl: opts.iconsUrl || "/civic/ui-kit/icons.svg",
      year: opts.year || 2027,
      buildMs: opts.buildMs > 0 ? opts.buildMs : BUILD_MS,
      autoZoom: opts.autoZoom !== false,
      renderCard: opts.renderCard !== false,
      useR06Card: opts.useR06Card !== false, // карточка R06 при настоящем API (если её модуль подключён)
      dock: opts.dock !== false, // каталог/подсказка видны (карточка и размещение — всегда)
      storage: opts.storage || safeLocalStorage(),
    };
    var i18n = opts.i18n || root.BirgeI18n || null;
    var t = makeT(i18n);

    // Состояние модуля. Всё, что видит пользователь, перерисовывается из него.
    var S = {
      phase: "loading", // loading | ready | error | unsupported
      mode: "idle", // idle | placing
      kind: null,
      ghost: null, // {pos, rot, shownRot, follow, valid, manualRot, a, aStreet, section, hover}
      objects: {}, // id → объект сцены
      selected: null,
      visible: true,
      destroyed: false,
      leaving: false, // страница уходит (перезагрузка, переход): обрыв запросов — не сбой
      storeMode: "pending",
      error: null,
      hint: null, // {key, params, error:true}
      cardBusy: null,
    };
    var THREE = null,
      Models = null,
      renderer = null,
      scene = null,
      camera = null,
      ghostGroup = null;
    var streets = opts.streets || null,
      existing = null, // настоящие объекты OSM (грузятся при первом размещении)
      existingLoading = null,
      districts = null,
      fixture = null,
      store = null;
    var origin = null,
      originMatrix = null,
      lastMatrix = null;
    var deviceId = Core.getDeviceId(o.storage);
    var anims = []; // активные анимации {update(now) → bool (ещё идёт)}
    var layerAdded = false;
    var unsubLang = null;
    var toastTimer = null;
    var toastIsError = false;

    // ── DOM: корень, нижняя панель, тосты, подписи ──
    var hostRoot = opts.root || map.getContainer();
    // overlay: панель внизу, карточка на ноутбуке справа. Без своего root — всегда; с root хозяина — по opts.overlay
    // (корень хозяина тогда должен покрывать свободную часть карты, см. INTEGRATION.txt).
    var ui = el("div", "b3d bk-app" + (!opts.root || opts.overlay ? " b3d--overlay" : ""), { "data-b3d-role": o.role });
    var dock = el("section", "b3d-dock", { "aria-live": "polite" });
    var toasts = el("div", "b3d-toasts");
    ui.appendChild(toasts);
    ui.appendChild(dock);
    hostRoot.appendChild(ui);
    var labelsLayer = el("div", "b3d-labels");
    map.getCanvasContainer().appendChild(labelsLayer);

    // ───────────── Отрисовка панели ─────────────

    // Панель перерисовывается целиком, но только когда что-то видимое изменилось (подпись состояния),
    // и фокус клавиатуры возвращается на ту же кнопку — Tab-навигация не сбивается.
    var lastSig = null;
    function signature() {
      var sel = S.selected && S.objects[S.selected] ? S.objects[S.selected] : null;
      var g = S.ghost;
      return JSON.stringify([
        S.phase, S.mode, S.kind, S.hint, S.visible, S.storeMode, S.cardBusy, t.lang(), Object.keys(S.objects).length, o.dock, o.role,
        g ? [g.valid && g.valid.ok, !!(g.section && g.section.ok), nearInfo()] : null,
        sel ? [sel.p.id, sel.p.votes_up, sel.p.votes_down, sel.p.my_vote, sel.pending] : null,
      ]);
    }
    function render(force) {
      if (S.destroyed) return;
      var sig = signature();
      if (!force && sig === lastSig) return;
      lastSig = sig;
      var active = doc.activeElement;
      var focusSel = null;
      if (active && dock.contains(active)) {
        if (active.getAttribute("data-action")) focusSel = '[data-action="' + active.getAttribute("data-action") + '"]';
        else if (active.getAttribute("data-kind")) focusSel = '[data-kind="' + active.getAttribute("data-kind") + '"]';
      }
      applyInsets();
      renderDock();
      fitDock();
      labelsLayer.classList.toggle("b3d-labels--passive", S.mode === "placing");
      if (focusSel) {
        var again = dock.querySelector(focusSel);
        if (again) again.focus({ preventScroll: true });
      }
    }
    // Свободная часть карты: не заходим под элементы хозяина (панель R01 слева, шторка снизу на телефоне).
    function applyInsets() {
      if (typeof opts.avoid !== "function" || !ui.classList.contains("b3d--overlay")) return;
      var host = ui.parentNode;
      if (!host || !host.getBoundingClientRect) return;
      var c = host.getBoundingClientRect();
      var ins = { left: 0, right: 0, top: 0, bottom: 0 };
      var gap = 12;
      var list = [];
      try {
        list = opts.avoid() || [];
      } catch (e) {
        list = [];
      }
      list.forEach(function (node) {
        if (!node || !node.getBoundingClientRect || node.hidden) return;
        var r = node.getBoundingClientRect();
        if (!r.width || !r.height || r.right <= c.left || r.left >= c.right || r.bottom <= c.top || r.top >= c.bottom) return;
        var wide = r.width > c.width * 0.6,
          tall = r.height > c.height * 0.25;
        // Полосы во всю ширину: шапка сверху, шторка снизу. Колонки: панель/кнопки слева или справа.
        if (wide && r.bottom >= c.bottom - 4) ins.bottom = Math.max(ins.bottom, c.bottom - r.top + gap);
        else if (wide && r.top - c.top < c.height * 0.2) ins.top = Math.max(ins.top, r.bottom - c.top + gap);
        else if (tall && r.right - c.left < c.width * 0.5) ins.left = Math.max(ins.left, r.right - c.left + gap);
        else if (tall && r.left - c.left > c.width * 0.5) ins.right = Math.max(ins.right, c.right - r.left + gap);
      });
      // Справа у хозяина своя панель (карточки целей R07): карточка проекта остаётся внизу, как каталог.
      ui.classList.toggle("b3d--host-right", ins.right > 0);
      ui.style.left = ins.left + "px";
      ui.style.right = ins.right + "px";
      ui.style.top = ins.top + "px";
      ui.style.bottom = ins.bottom + "px";
    }

    // Панель не заходит на верхние полосы хозяина (шапка оболочки R01). Хозяин ставит корень модуля над своей шторкой;
    // на телефоне у акимата при шторке «half» высокая карточка проекта росла вверх и закрывала шапку («Мәзір», ҚАЗ/РУС)
    // и сам объект. Высота панели — до нижнего края верхних полос из opts.avoid, остальное прокручивается внутри.
    var fitObserver = null;
    var fitWatched = [];
    var fitFrame = 0;
    function topLimit() {
      var cr = map.getCanvas().getBoundingClientRect();
      var lim = Math.max(0, cr.top);
      avoidRects().forEach(function (r) {
        // полоса во всю ширину у верхнего края карты (шапка), а не шторка или колонка
        if (r.width > cr.width * 0.6 && r.top - cr.top < cr.height * 0.2 && r.bottom - cr.top < cr.height * 0.4) lim = Math.max(lim, r.bottom);
      });
      return lim + 8;
    }
    function fitDock() {
      if (S.destroyed) return;
      watchHost();
      dock.style.maxHeight = "";
      dock.classList.remove("b3d-dock--fit");
      var st = dock.getAttribute("data-state");
      if (!st || st === "empty" || ui.hidden) return;
      var r = dock.getBoundingClientRect();
      if (!r.height) return;
      var top = topLimit();
      if (r.top >= top - 0.5) return;
      var avail = Math.floor(r.bottom - top);
      if (avail < 160) return; // места почти нет — не превращать панель в щель
      dock.style.maxHeight = avail + "px";
      dock.classList.add("b3d-dock--fit");
    }
    function refitSoon() {
      if (fitFrame || S.destroyed) return;
      var run = function () {
        fitFrame = 0;
        fitDock();
      };
      fitFrame = root.requestAnimationFrame ? root.requestAnimationFrame(run) : setTimeout(run, 16);
    }
    // Хозяин меняет свои панели (шторка R01: data-sheet) — место для панели меняется без событий модуля.
    function watchHost() {
      if (typeof opts.avoid !== "function" || typeof root.MutationObserver !== "function") return;
      var list = [];
      try {
        list = Array.prototype.slice.call(opts.avoid() || []);
      } catch (e) {
        list = [];
      }
      if (!fitObserver) fitObserver = new root.MutationObserver(refitSoon);
      list.forEach(function (node) {
        if (!node || fitWatched.indexOf(node) >= 0 || typeof node.nodeType !== "number") return;
        fitWatched.push(node);
        fitObserver.observe(node, { attributes: true });
      });
    }

    function renderDock() {
      ui.hidden = !S.visible;
      dock.textContent = "";
      dock.removeAttribute("data-state");
      if (S.phase === "loading") return renderLoading();
      if (S.phase === "unsupported") return renderMessage("alert", t("build3d.unsupported_title"), t("build3d.unsupported_text"), false);
      if (S.phase === "error") return renderMessage("wifi-off", t("build3d.load_failed"), "", true);
      if (S.mode === "placing") return renderPlacing();
      if (S.selected && S.objects[S.selected] && o.renderCard) return renderCard(S.objects[S.selected].p);
      if (!o.dock) {
        dock.setAttribute("data-state", "empty"); // хозяин спрятал каталог; объекты и карточки работают
        return;
      }
      if (o.role === "akimat") return renderCatalog();
      renderResidentHint();
    }

    // Житель: каталога нет, но есть понятная подсказка, что делать (UX_REVIEW день 3 #24).
    function renderResidentHint() {
      var count = Object.keys(S.objects).length;
      dock.setAttribute("data-state", "hint");
      var line = el("p", "b3d-hint b3d-hint--lead", { role: "status" });
      line.appendChild(icon(count ? "thumb-up" : "info", o.iconsUrl));
      line.appendChild(el("span", "", { text: t(count ? "build3d.resident.hint" : "build3d.resident.empty") }));
      dock.appendChild(line);
    }

    function renderLoading() {
      dock.setAttribute("data-state", "loading");
      if (o.role !== "akimat") return;
      var head = el("p", "b3d-title", { text: t("proposal.catalog.title") });
      var row = el("div", "b3d-cards");
      for (var i = 0; i < 5; i++) row.appendChild(el("span", "bk-skel b3d-card b3d-card--skel"));
      dock.appendChild(head);
      dock.appendChild(row);
      dock.appendChild(el("p", "bk-meta b3d-note", { text: t("build3d.loading"), role: "status" }));
    }

    function renderMessage(iconName, title, text, retry) {
      dock.setAttribute("data-state", "error");
      var box = el("div", "b3d-message", { role: "alert" });
      box.appendChild(icon(iconName, o.iconsUrl));
      var txt = el("div", "b3d-message__text");
      txt.appendChild(el("p", "b3d-message__title", { text: title }));
      if (text) txt.appendChild(el("p", "bk-meta", { text: text }));
      box.appendChild(txt);
      if (retry) {
        var b = el("button", "bk-btn", { type: "button" });
        b.appendChild(icon("refresh", o.iconsUrl));
        b.appendChild(el("span", "", { text: t("common.action.retry") }));
        b.addEventListener("click", boot);
        box.appendChild(b);
      }
      dock.appendChild(box);
    }

    function renderCatalog() {
      dock.setAttribute("data-state", "catalog");
      var head = el("div", "b3d-head");
      head.appendChild(el("p", "b3d-title", { text: t("proposal.catalog.title"), id: "b3d-catalog-title" }));
      var count = Object.keys(S.objects).length;
      if (count >= Core.MAX_OBJECTS) head.appendChild(el("span", "bk-tag bk-tag--warn", { text: t("proposal.limit") }));
      dock.appendChild(head);
      var row = el("div", "b3d-cards", { role: "group", "aria-labelledby": "b3d-catalog-title" });
      Core.KIND_ORDER.forEach(function (kind) {
        var k = Core.KINDS[kind];
        var name = t(k.key);
        var b = el("button", "b3d-card", { type: "button", "data-kind": kind, "aria-label": t("build3d.catalog.place", { kind: name }) });
        b.appendChild(icon(k.icon, o.iconsUrl));
        b.appendChild(el("span", "b3d-card__label", { text: name }));
        if (count >= Core.MAX_OBJECTS) b.disabled = true;
        b.addEventListener("click", function (ev) {
          start(kind, { keyboard: ev.detail === 0 });
        });
        row.appendChild(b);
      });
      dock.appendChild(row);
      if (S.storeMode === "local") dock.appendChild(el("p", "bk-meta b3d-note", { text: t("build3d.local_note") }));
    }

    function renderPlacing() {
      dock.setAttribute("data-state", "placing");
      var g = S.ghost;
      var k = Core.KINDS[S.kind];
      var head = el("div", "b3d-head");
      var title = el("p", "b3d-title");
      title.appendChild(icon(k.icon, o.iconsUrl));
      title.appendChild(el("span", "", { text: t(k.key) }));
      head.appendChild(title);
      head.appendChild(el("span", "bk-tag bk-tag--project", { text: t("common.tag.project") }));
      dock.appendChild(head);
      var hint = el("p", "b3d-hint" + (S.hint && S.hint.error ? " b3d-hint--error" : ""), { role: "status", "aria-live": "polite" });
      if (S.hint && S.hint.error) hint.appendChild(icon("alert", o.iconsUrl));
      hint.appendChild(el("span", "", { text: S.hint ? t(S.hint.key, S.hint.params) : "" }));
      dock.appendChild(hint);
      var info = nearInfo();
      if (info) {
        var line = el("p", "b3d-hint b3d-hint--info", { "data-near": info.id || "lamps" });
        line.appendChild(icon("info", o.iconsUrl));
        var txt = el("span", "");
        txt.appendChild(doc.createTextNode(t(info.key, info.params) + " "));
        txt.appendChild(el("span", "bk-meta", { text: "· " + t("build3d.near.source") }));
        line.appendChild(txt);
        dock.appendChild(line);
      }
      var actions = el("div", "b3d-actions");
      if (!k.line) {
        actions.appendChild(actionBtn("rotate-left", t("proposal.rotate_left"), "", function () {
          rotate(-ROTATE_STEP);
        }, "rotate-left"));
        actions.appendChild(actionBtn("rotate-right", t("proposal.rotate_right"), "", function () {
          rotate(ROTATE_STEP);
        }, "rotate-right"));
      }
      actions.appendChild(actionBtn("close", t("common.action.cancel"), "", cancel, "cancel"));
      var canPlace = g && g.valid && g.valid.ok && (!k.line || (g.section && g.section.ok));
      var place = actionBtn("check", t("proposal.place"), "bk-btn--primary", place_, "place");
      if (!canPlace) place.setAttribute("aria-disabled", "true");
      actions.appendChild(place);
      dock.appendChild(actions);
    }

    function actionBtn(iconName, label, extra, onClick, action) {
      var b = el("button", "bk-btn b3d-act " + (extra || ""), { type: "button", "data-action": action });
      b.appendChild(icon(iconName, o.iconsUrl));
      b.appendChild(el("span", "", { text: label }));
      b.addEventListener("click", function () {
        if (b.getAttribute("aria-disabled") === "true") return;
        onClick();
      });
      return b;
    }

    // С настоящим сервером R06 карточку проекта рисует сам R06 (BirgeProposals.renderProposal): одна карточка
    // во всей сборке — голоса, статус, «Одобрить / Отклонить» для акимата. От 3D-модуля — «Рядом / Двор» и «Удалить».
    function useR06Card() {
      return o.useR06Card && S.storeMode === "api" && root.BirgeProposals && typeof root.BirgeProposals.renderProposal === "function";
    }
    function toR06Item(p) {
      var name = Core.KINDS[p.kind] ? COMMON_FALLBACK.ru[Core.KINDS[p.kind].key] : p.kind;
      return {
        id: p.id, kind: p.kind, geometry: p.geometry, rotation_deg: p.rotation_deg, status: p.status,
        title_ru: p.title_ru || name, title_kk: p.title_kk || null, district: p.district, planned_year: p.year,
        votes_up: p.votes_up, votes_down: p.votes_down, my_vote: p.my_vote || null,
        voting_open: p.voting_open !== false, demo: p.demo,
      };
    }
    function renderR06Card(p) {
      dock.setAttribute("data-state", "card");
      var head = el("div", "b3d-head b3d-head--end");
      var close = el("button", "bk-iconbtn", { type: "button", "aria-label": t("common.action.close"), title: t("common.action.close"), "data-action": "close-card" });
      close.appendChild(icon("close", o.iconsUrl));
      close.addEventListener("click", function () {
        select(null);
      });
      head.appendChild(close);
      dock.appendChild(head);
      var host = el("div", "b3d-r06");
      dock.appendChild(host);
      try {
        root.BirgeProposals.renderProposal(host, toR06Item(p), {
          role: o.role,
          onChange: function (np) {
            // Голос/решение уже показаны карточкой R06 — обновляем только свои данные и подпись, без перерисовки.
            var obj = S.objects[p.id];
            var fresh = Core.normalizeProposal(np);
            if (!obj || !fresh) return;
            obj.p = Object.assign({}, obj.p, fresh);
            updateLabelText(obj);
            emitSelect(obj.p);
          },
        });
      } catch (e) {
        console.error("[build3d] карточка R06", e);
        dock.textContent = "";
        return renderOwnCard(p);
      }
      var where = placeText(p);
      if (where) dock.appendChild(el("p", "bk-meta b3d-pcard__where", { text: where }));
      var yard = yardOf(p);
      if (yard) {
        var yardName = t.lang() === "kk" ? yard.label_kk || yard.label_ru : yard.label_ru || yard.label_kk;
        dock.appendChild(el("p", "bk-meta b3d-pcard__yard", { text: t("build3d.card.yard", { name: yardName }) }));
      }
      if (o.role === "akimat") dock.appendChild(deleteBtn(p));
    }

    function deleteBtn(p) {
      var del = actionBtn("close", t("proposal.delete"), "bk-btn--danger b3d-delete", function () {
        removeProposal(p.id);
      }, "delete");
      if (S.cardBusy === "delete") del.setAttribute("aria-busy", "true");
      if (S.objects[p.id] && S.objects[p.id].pending) del.setAttribute("aria-disabled", "true");
      return del;
    }

    function renderCard(p) {
      if (useR06Card()) return renderR06Card(p);
      return renderOwnCard(p);
    }

    function renderOwnCard(p) {
      dock.setAttribute("data-state", "card");
      var card = el("article", "b3d-pcard", { "aria-labelledby": "b3d-pcard-title" });
      var head = el("div", "b3d-head");
      var title = el("h2", "b3d-pcard__title", { id: "b3d-pcard-title" });
      title.appendChild(icon(Core.KINDS[p.kind].icon, o.iconsUrl));
      title.appendChild(el("span", "", { text: t(Core.KINDS[p.kind].key) }));
      head.appendChild(title);
      var close = el("button", "bk-iconbtn", { type: "button", "aria-label": t("common.action.close"), title: t("common.action.close"), "data-action": "close-card" });
      close.appendChild(icon("close", o.iconsUrl));
      close.addEventListener("click", function () {
        select(null);
      });
      head.appendChild(close);
      card.appendChild(head);
      var tags = el("div", "bk-card__row");
      tags.appendChild(el("span", "bk-tag bk-tag--project", { text: projectLabel(p) }));
      if (p.demo) tags.appendChild(el("span", "bk-tag bk-tag--demo", { text: t("common.tag.demo"), title: t("common.tag.demo_hint") }));
      // Статус словом и цветом (R06: proposal | approved | rejected).
      var st = p.status === "approved" || p.status === "rejected" ? p.status : "proposal";
      tags.appendChild(el("span", "bk-status", { "data-status": st === "approved" ? "fixed" : st === "rejected" ? "rejected" : "accepted", text: t("proposal.status." + st) }));
      card.appendChild(tags);
      var where = placeText(p);
      if (where) card.appendChild(el("p", "bk-meta b3d-pcard__where", { text: where }));
      var yard = yardOf(p);
      if (yard) {
        var yardName = t.lang() === "kk" ? yard.label_kk || yard.label_ru : yard.label_ru || yard.label_kk;
        card.appendChild(el("p", "bk-meta b3d-pcard__yard", { text: t("build3d.card.yard", { name: yardName }) }));
      }
      var votes = el("div", "b3d-votes", { role: "group", "aria-label": t("proposal.one_vote") });
      votes.appendChild(voteBtn(p, 1));
      votes.appendChild(voteBtn(p, -1));
      card.appendChild(votes);
      var note = p.my_vote === 1 ? t("build3d.card.your_vote_up") : p.my_vote === -1 ? t("build3d.card.your_vote_down") : t("proposal.one_vote");
      if (p.voting_open === false) note = t("proposal.voting_closed");
      card.appendChild(el("p", "bk-meta", { text: note }));
      if (o.role === "akimat") card.appendChild(deleteBtn(p));
      dock.appendChild(card);
    }

    function voteBtn(p, value) {
      var up = value === 1;
      var b = el("button", "bk-btn b3d-vote", {
        type: "button",
        "aria-pressed": p.my_vote === value ? "true" : "false",
        "data-action": up ? "vote-up" : "vote-down",
      });
      b.appendChild(icon(up ? "thumb-up" : "thumb-down", o.iconsUrl));
      b.appendChild(el("span", "", { text: t(up ? "proposal.vote_up" : "proposal.vote_down") }));
      b.appendChild(el("span", "bk-btn__count", { text: formatNum(up ? p.votes_up : p.votes_down) }));
      if (S.cardBusy === "vote" + value) b.setAttribute("aria-busy", "true");
      if (p.voting_open === false) b.disabled = true; // проект одобрен или отклонён — голосование закрыто
      b.addEventListener("click", function () {
        vote(p.id, value);
      });
      return b;
    }

    // «Проект · 2027»; без года (у R06 planned_year может быть пустым) — просто «Проект». Пометка есть всегда.
    function projectLabel(p) {
      return p.year ? t("proposal.label", { year: String(p.year) }) : t("common.tag.project");
    }

    // Создавать и снимать проекты может только вошедший сотрудник (шлюз R01/R06: 401, 403, csrf_failed).
    // 429 — лимит с одного адреса (шлюз R01, R15 S02/S08): это не сбой связи, «Повторить» сразу снова упрётся в лимит.
    function isTooMany(err) {
      return !!err && (err.status === 429 || err.code === "too_many_requests" || err.code === "rate_limited");
    }
    function isStaffError(err) {
      return !!err && (err.status === 401 || err.status === 403 || /unauth|csrf|forbidden|staff/.test(String(err.code || "")));
    }
    // Перезагрузка или переход обрывают запросы старой страницы («TypeError: Failed to fetch», «network») — это не
    // ошибка модуля: в консоль не пишем (R01 I-05). Обрыв связи без ухода — тост и предупреждение, не console.error.
    function isNetworkError(err) {
      if (!err) return false;
      if (err.code === "network" || err.code === "timeout" || err.name === "AbortError") return true;
      return err.name === "TypeError" && /fetch|network|load failed/i.test(String(err.message || ""));
    }
    function logFail(label, err) {
      if (S.leaving) return;
      if (isNetworkError(err)) console.warn(label + ":", err.code || err.message);
      else console.error(label, err);
    }

    function formatNum(n) {
      return i18n && i18n.formatNumber ? i18n.formatNumber(n) : formatNumberLocal(n);
    }

    // Название улицы на языке интерфейса. kk: name:kk из OSM (13 из 59 улиц Нуры) → тип улицы по-казахски, имя как
    // есть (правило R07) → null (улицу не показываем — не по-русски внутри казахской фразы, R11 ночь B3 п. 5).
    function streetName(ru, kk) {
      if (!ru || t.lang() !== "kk") return ru;
      return kk || (streets && streets.kkOf ? streets.kkOf(ru) : null) || Core.kkStreetFromRu(ru);
    }

    function placeText(p) {
      if (p.kind === "lighting" && p.target && p.target.label_ru) {
        var len = Core.polylineLength(p.geometry.coordinates.map(function (c) {
          return Core.toLocal(p.geometry.coordinates[0], c);
        }));
        var sname = t.lang() === "kk" ? p.target.label_kk || streetName(p.target.label_ru) : p.target.label_ru;
        return sname ? t("build3d.card.segment", { street: sname, length: Math.round(len) }) : t("build3d.card.segment_plain", { length: Math.round(len) });
      }
      // У R06 нет полей улицы и двора — вычисляем по геометрии (настоящие улицы OSM), одинаково на любом устройстве.
      var street = p.near_street;
      if (!street && streets && p.kind !== "lighting") {
        var n = streets.nearest(p.geometry.coordinates, 120);
        street = n ? n.edge.name : null;
      }
      if (!street && p.kind === "lighting" && streets) {
        var c = p.geometry.coordinates;
        var m = streets.nearest(c[Math.floor(c.length / 2)], 30);
        if (m) {
          var L = Core.polylineLength(c.map(function (q) {
            return Core.toLocal(c[0], q);
          }));
          var segName = streetName(m.edge.name, m.edge.name_kk);
          return segName ? t("build3d.card.segment", { street: segName, length: Math.round(L) }) : t("build3d.card.segment_plain", { length: Math.round(L) });
        }
      }
      var shown = streetName(street);
      return shown ? t("build3d.card.near", { street: shown }) : "";
    }

    function yardOf(p) {
      if (p.target && p.target.kind === "area" && (p.target.label_ru || p.target.label_kk)) return p.target;
      if (existing && p.kind !== "lighting") {
        var y = existing.yardAt(p.geometry.coordinates);
        if (y && (y.name_ru || y.name_kk)) return { kind: "area", id: y.id, label_ru: y.name_ru, label_kk: y.name_kk };
      }
      return null;
    }

    // ── Тосты: что случилось + действие (Отменить / Повторить), 6 с ──
    function toast(text, opts2) {
      opts2 = opts2 || {};
      toasts.textContent = "";
      clearTimeout(toastTimer);
      toastIsError = !!opts2.error;
      var n = el("div", "bk-toast" + (opts2.error ? " bk-toast--error" : " bk-toast--ok"), { role: opts2.error ? "alert" : "status" });
      if (!opts2.error) n.appendChild(icon("check", o.iconsUrl));
      n.appendChild(el("span", "bk-toast__text", { text: text }));
      if (opts2.action) {
        var b = el("button", "bk-btn", { type: "button", "data-action": opts2.actionId || "toast-action" });
        b.textContent = opts2.action;
        b.addEventListener("click", function () {
          toasts.textContent = "";
          opts2.onAction();
        });
        n.appendChild(b);
      }
      toasts.appendChild(n);
      toastTimer = setTimeout(function () {
        if (n.parentNode) n.parentNode.removeChild(n);
      }, opts2.error ? 8000 : 6000);
    }
    function clearToast() {
      clearTimeout(toastTimer);
      toasts.textContent = "";
    }

    // ───────────── Загрузка ─────────────

    function boot() {
      S.phase = "loading";
      S.error = null;
      render();
      var threeP = THREE
        ? Promise.resolve(THREE)
        : import(/* webpackIgnore: true */ o.threeUrl).then(function (mod) {
            return mod;
          });
      // Улицы и районы нужны для освещения и проверки места; без них модуль работает, но беднее.
      var streetsP = streets
        ? Promise.resolve(null)
        : fetchJson(o.dataUrl + "nura-streets.json").then(
            function (d) {
              streets = new Core.StreetIndex(d);
            },
            function (err) {
              console.warn("[build3d] улицы не загрузились:", err.message);
            }
          );
      var districtsP = fetchJson(o.dataUrl + "astana-districts.json").then(
        function (d) {
          districts = d;
        },
        function (err) {
          console.warn("[build3d] районы не загрузились:", err.message);
        }
      );
      var fixtureP = fetchJson(o.dataUrl + "proposals.fixture.json").then(
        function (d) {
          fixture = d;
        },
        function () {
          fixture = { proposals: [] };
        }
      );
      return Promise.all([threeP, streetsP, districtsP, fixtureP])
        .then(function (res) {
          if (S.destroyed) return;
          THREE = res[0];
          Models = ModelsLib.create(THREE);
          store = makeStore();
          return whenStyleReady().then(addLayer);
        })
        .then(function () {
          if (S.destroyed) return;
          if (S.phase === "unsupported") return render();
          return loadProposals();
        })
        .catch(function (err) {
          if (S.destroyed) return;
          console.error("[build3d]", err);
          S.phase = "error";
          S.error = err;
          render();
        });
    }

    function safeLocalStorage() {
      try {
        return root.localStorage;
      } catch (e) {
        return null;
      }
    }

    function makeStore() {
      var s = opts.store;
      if (s && typeof s === "object") return s;
      var cfg = {
        prefix: o.apiPrefix,
        storage: o.storage,
        fixture: fixture,
        deviceId: deviceId,
        v2: opts.api && typeof opts.api.v2 === "function" ? opts.api.v2 : null, // клиент оболочки R01
      };
      if (s === "api") return Core.createApiStore(cfg);
      if (s === "local") return Core.createLocalStore(cfg);
      return Core.createAutoStore(cfg);
    }

    // Стиль готов принять слой, когда загружен сам JSON стиля (источники могут ещё грузиться —
    // map.isStyleLoaded() в это время false, поэтому ждём ещё и «load»/«idle»).
    function styleJsonReady() {
      try {
        return !!(map.style && map.style._loaded) || (map.isStyleLoaded && map.isStyleLoaded());
      } catch (e) {
        return false;
      }
    }
    function whenStyleReady() {
      return new Promise(function (resolve) {
        if (styleJsonReady()) return resolve();
        var done = false;
        var finish = function () {
          if (done) return;
          done = true;
          map.off("load", finish);
          map.off("idle", finish);
          map.off("styledata", check);
          resolve();
        };
        var check = function () {
          if (styleJsonReady()) finish();
        };
        map.on("load", finish);
        map.on("idle", finish);
        map.on("styledata", check);
      });
    }

    function loadProposals() {
      // Все проекты сразу, без bbox: их десятки, а запрос «по видимой части» терял бы проекты, к которым
      // пользователь потом прокрутит карту (найдено проверкой на стенде R06).
      return store.list(null).then(
        function (items) {
          if (S.destroyed) return;
          S.storeMode = store.mode || "api";
          var seen = {};
          items.forEach(function (p) {
            seen[p.id] = true;
            if (S.objects[p.id]) S.objects[p.id].p = p;
            else addObject(p, { animate: false }); // после перезагрузки — без повторной анимации
          });
          Object.keys(S.objects).forEach(function (id) {
            if (!seen[id] && !S.objects[id].pending) disposeObject(id);
          });
          S.phase = "ready";
          render();
          repaint();
        },
        function (err) {
          if (S.destroyed) return;
          logFail("[build3d] предложения не загрузились", err);
          S.phase = "ready";
          render();
          if (S.leaving) return;
          toast(t("build3d.load_failed"), {
            error: true,
            action: t("common.action.retry"),
            actionId: "retry-load",
            onAction: loadProposals,
          });
        }
      );
    }

    function currentBbox() {
      try {
        var b = map.getBounds();
        return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
      } catch (e) {
        return null;
      }
    }

    // ───────────── Слой MapLibre + three.js ─────────────
    // Как в официальном примере MapLibre «3D model with three.js»: камера three.js получает матрицу
    // проекции карты, умноженную на матрицу «метры сцены → меркатор». Сцена: x — восток, y — север,
    // z — вверх, метры от точки origin. Поэтому объект стоит ровно в своих lon/lat при любом наклоне
    // и повороте карты, а размеры — в настоящих метрах.

    var layer = {
      id: LAYER_ID,
      type: "custom",
      renderingMode: "3d",
      onAdd: function (m, gl) {
        if (renderer) return; // после смены стиля слой добавляется снова — рендерер тот же
        var isGL2 = typeof root.WebGL2RenderingContext !== "undefined" && gl instanceof root.WebGL2RenderingContext;
        if (!isGL2) {
          S.phase = "unsupported";
          return;
        }
        renderer = new THREE.WebGLRenderer({ canvas: m.getCanvas(), context: gl, antialias: true });
        renderer.autoClear = false;
        setupScene();
      },
      render: function (gl, args) {
        if (!renderer || S.destroyed) return;
        var mm = args && args.defaultProjectionData ? args.defaultProjectionData.mainMatrix : args;
        if (!mm || mm.length !== 16) return;
        var now = performance.now();
        stepAnimations(now);
        lastMatrix = new THREE.Matrix4().fromArray(mm).multiply(originMatrix);
        camera.projectionMatrix.copy(lastMatrix);
        renderer.resetState();
        renderer.render(scene, camera);
        updateLabels();
        if (anims.length) map.triggerRepaint();
      },
      onRemove: function () {
        layerAdded = false;
      },
    };

    function setupScene() {
      scene = new THREE.Scene();
      camera = new THREE.Camera();
      // Мягкий свет: небо/земля + солнце с юго-запада (тени не считаем — только мягкое пятно под объектом).
      var hemi = new THREE.HemisphereLight(0xffffff, 0xcfd6c8, 2.1);
      hemi.position.set(0, 0, 1);
      scene.add(hemi);
      var sun = new THREE.DirectionalLight(0xffffff, 1.7);
      sun.position.set(-0.55, -0.85, 1.3);
      scene.add(sun);
      var fill = new THREE.DirectionalLight(0xffffff, 0.45);
      fill.position.set(0.7, 0.6, 0.5);
      scene.add(fill);
      var c = map.getCenter();
      origin = [c.lng, c.lat];
      var s = Core.meterInMerc(origin[1]);
      originMatrix = new THREE.Matrix4()
        .makeTranslation(Core.mercX(origin[0]), Core.mercY(origin[1]), 0)
        .scale(new THREE.Vector3(s, -s, s));
      ghostGroup = new THREE.Group();
      ghostGroup.visible = false;
      scene.add(ghostGroup);
    }

    function addLayer() {
      if (S.destroyed || layerAdded) return;
      if (map.getLayer(LAYER_ID)) {
        layerAdded = true;
        return;
      }
      // Под подписями карты (symbol), но над зданиями: подписи улиц остаются читаемыми.
      var layers = (map.getStyle() && map.getStyle().layers) || [];
      var before = null;
      for (var i = 0; i < layers.length; i++) {
        if (layers[i].type === "symbol") {
          before = layers[i].id;
          break;
        }
      }
      map.addLayer(layer, before || undefined);
      layerAdded = true;
    }

    // После смены стиля карты (map.setStyle) MapLibre убирает все слои — возвращаем свой.
    function onStyleData() {
      if (!THREE || !renderer || S.destroyed || S.phase === "unsupported") return;
      if (map.getLayer(LAYER_ID)) return;
      layerAdded = false;
      try {
        addLayer();
      } catch (e) {
        // JSON стиля ещё не разобран — попробуем, когда карта успокоится.
        map.once("idle", onStyleData);
      }
    }

    function repaint() {
      if (map && !S.destroyed) map.triggerRepaint();
    }

    // ───────────── Материалы ─────────────
    // «Постройка снизу вверх»: вершины выше uReveal прижимаются к этой высоте. Программа шейдера общая,
    // значение — у каждого объекта своё (собственный экземпляр материала).
    function revealHook(shader) {
      shader.uniforms.uReveal = this.userData.reveal;
      shader.vertexShader =
        "uniform float uReveal;\n" +
        shader.vertexShader.replace("#include <begin_vertex>", "#include <begin_vertex>\ntransformed.z = min(transformed.z, uReveal);");
    }
    function revealKey() {
      return "birge-build3d-reveal";
    }
    function withReveal(mat) {
      mat.userData.reveal = { value: 1e4 };
      mat.onBeforeCompile = revealHook;
      mat.customProgramCacheKey = revealKey;
      return mat;
    }

    function makeMaterials(ghost, invalid) {
      if (ghost) {
        var color = invalid ? 0xb3362e : 0x176b4a;
        return {
          solid: new THREE.MeshLambertMaterial({ color: color, emissive: color, emissiveIntensity: 0.25, transparent: true, opacity: 0.55 }),
          glass: null,
          glow: new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.55 }),
          decal: null,
          outline: new THREE.MeshBasicMaterial({ color: color }),
        };
      }
      return {
        solid: withReveal(new THREE.MeshLambertMaterial({ vertexColors: true })),
        glass: withReveal(new THREE.MeshLambertMaterial({ vertexColors: true, transparent: true, depthWrite: false, side: THREE.DoubleSide })),
        glow: withReveal(new THREE.MeshBasicMaterial({ vertexColors: true })),
        decal: new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -1 }),
        outline: new THREE.MeshBasicMaterial({ color: OUTLINE_COLOR }),
      };
    }

    // Собрать группу мешей из геометрий модели. Порядок отрисовки: пятна → пунктир → тела → стекло.
    function makeMeshes(geos, mats) {
      var group = new THREE.Group();
      var order = { decal: 1, outline: 2, solid: 3, glow: 3, glass: 4 };
      ["decal", "outline", "solid", "glow", "glass"].forEach(function (k) {
        if (!geos[k] || !mats[k]) return;
        var mesh = new THREE.Mesh(geos[k], mats[k]);
        mesh.renderOrder = order[k];
        mesh.frustumCulled = false; // своя проекция: three.js не знает настоящую пирамиду камеры
        mesh.userData.part = k;
        group.add(mesh);
      });
      return group;
    }

    function disposeGroup(group) {
      if (!group) return;
      group.traverse(function (n) {
        if (n.isInstancedMesh) n.dispose();
        if (n.geometry) n.geometry.dispose();
        if (n.material) {
          (Array.isArray(n.material) ? n.material : [n.material]).forEach(function (m) {
            m.dispose();
          });
        }
      });
      if (group.parent) group.parent.remove(group);
    }

    // ───────────── Объекты предложений ─────────────

    function anchorOf(p) {
      return p.kind === "lighting" ? p.geometry.coordinates[0] : p.geometry.coordinates;
    }

    // Параметры модели освещения: точки опор (метры от первой точки участка).
    function lightingOpts(coords) {
      var a = coords[0];
      var line = coords.map(function (c) {
        return Core.toLocal(a, c);
      });
      var offset = streets && streets.poleOffset ? streets.poleOffset(coords) : Core.LIGHT_OFFSET_M;
      return { poles: Core.sampleAlong(line, Core.LIGHT_STEP_M), line: line, offset: offset };
    }

    function buildGeos(p) {
      if (p.kind === "lighting") return Models.build("lighting", lightingOpts(p.geometry.coordinates));
      var k = Core.KINDS[p.kind];
      return Models.build(p.kind, { seed: p.id, w: k.w, d: k.d });
    }

    function placeGroup(group, p) {
      var local = Core.toLocal(origin, anchorOf(p));
      group.position.set(local[0], local[1], 0);
      group.rotation.set(0, 0, -(p.rotation_deg || 0) * DEG); // азимут по часовой → против часовой в сцене
      group.updateMatrixWorld(true);
    }

    function addObject(p, flags) {
      flags = flags || {};
      if (!scene) return null;
      if (S.objects[p.id]) disposeObject(p.id); // тот же id ещё исчезает после «Удалить» — убрать сразу
      var geos = buildGeos(p);
      var mats = makeMaterials(false);
      var group = makeMeshes(geos, mats);
      placeGroup(group, p);
      scene.add(group);
      var obj = { p: p, group: group, height: geos.height, mats: mats, label: null, pending: !!flags.pending };
      obj.labelPoint = labelPointOf(p, geos);
      obj.label = makeLabel(obj);
      S.objects[p.id] = obj;
      if (flags.animate && !reducedMotion()) animateBuild(obj);
      repaint();
      return obj;
    }

    // Точка подписи «Проект · 2027» — над верхом объекта (у освещения — над средней опорой).
    function labelPointOf(p, geos) {
      if (p.kind === "lighting") {
        var lo = lightingOpts(p.geometry.coordinates);
        var mid = lo.poles[Math.floor(lo.poles.length / 2)] || { p: [0, 0] };
        return [mid.p[0], mid.p[1], geos.height + 1.2];
      }
      return [0, 0, geos.height + 1.5];
    }

    function makeLabel(obj) {
      // Кнопка — прозрачная зона нажатия ≥ 48 px; видимая «таблетка» внутри — 40 px (UX_REVIEW день 3 #21).
      var b = el("button", "b3d-label", { type: "button", "data-id": obj.p.id });
      var pill = el("span", "b3d-label__pill bk-tag bk-tag--project");
      // Значок вида — виден в сжатой подписи-точке; число — у группы рядом стоящих проектов (R10 B-026).
      var ic = icon(Core.KINDS[obj.p.kind].icon, o.iconsUrl);
      ic.setAttribute("class", "ic b3d-label__icon");
      pill.appendChild(ic);
      pill.appendChild(el("span", "b3d-label__text"));
      pill.appendChild(el("span", "b3d-label__count", { "aria-hidden": "true" }));
      b.appendChild(pill);
      b.addEventListener("click", function (ev) {
        ev.stopPropagation();
        if (S.mode === "placing") return;
        if (b._cluster && b._cluster.length > 1) return zoomToCluster(b._cluster);
        select(obj.p.id);
      });
      labelsLayer.appendChild(b);
      updateLabelText(obj, b);
      return b;
    }

    function updateLabelText(obj, b) {
      b = b || obj.label;
      if (!b) return;
      var name = t(Core.KINDS[obj.p.kind].key);
      b.querySelector(".b3d-label__text").textContent = projectLabel(obj.p);
      b._clusterKey = null; // группу (число, aria) пересоберёт updateLabels
      obj.labelSize = null; // текст сменился — размер измерим заново (один раз, не в каждом кадре)
      b.setAttribute("aria-label", t("build3d.card.open", { kind: name, year: String(obj.p.year || "") }).replace(/\s+,/, ","));
      b.setAttribute("aria-pressed", S.selected === obj.p.id ? "true" : "false");
    }

    function disposeObject(id) {
      var obj = S.objects[id];
      if (!obj) return;
      disposeGroup(obj.group);
      if (obj.dust) disposeGroup(obj.dust);
      if (obj.label && obj.label.parentNode) obj.label.parentNode.removeChild(obj.label);
      delete S.objects[id];
      if (S.selected === id) S.selected = null;
      repaint();
    }

    // ── Анимации ──

    function stepAnimations(now) {
      anims = anims.filter(function (a) {
        return a.update(now);
      });
    }

    // Постройка: вершины «вырастают» снизу вверх, объект слегка «пружинит», по краям — пыль.
    function animateBuild(obj) {
      var t0 = performance.now();
      var H = obj.height + 0.5;
      var revealMats = [obj.mats.solid, obj.mats.glass, obj.mats.glow].filter(Boolean);
      revealMats.forEach(function (m) {
        m.userData.reveal.value = 0;
      });
      obj.group.scale.set(0.94, 0.94, 1);
      if (obj.label) obj.label.classList.add("b3d-label--hidden");
      obj.dust = makeDust(obj);
      anims.push({
        update: function (now) {
          var k = Math.min(1, (now - t0) / o.buildMs);
          var reveal = easeInOutCubic(Math.min(1, k / 0.85)) * H;
          revealMats.forEach(function (m) {
            m.userData.reveal.value = k >= 1 ? 1e4 : reveal;
          });
          var sc = 0.94 + 0.06 * easeOutBack(Math.min(1, k / 0.6));
          obj.group.scale.set(sc, sc, 1);
          if (obj.dust) obj.dust.userData.step(k);
          if (k >= 1) {
            obj.group.scale.set(1, 1, 1);
            if (obj.dust) {
              disposeGroup(obj.dust);
              obj.dust = null;
            }
            if (obj.label) obj.label.classList.remove("b3d-label--hidden");
            return false;
          }
          return true;
        },
      });
      repaint();
    }

    // Лёгкая пыль: 14 низкополигональных «облачков» по контуру, растут, поднимаются и тают за ~1 с.
    function makeDust(obj) {
      var N = 14;
      var geo = new THREE.IcosahedronGeometry(0.9, 0);
      var mat = new THREE.MeshLambertMaterial({ color: 0xefe6d6, transparent: true, opacity: 0.6, depthWrite: false });
      var mesh = new THREE.InstancedMesh(geo, mat, N);
      mesh.frustumCulled = false;
      mesh.renderOrder = 5;
      var pts = [];
      var k = Core.KINDS[obj.p.kind];
      var rand = Models.rng(obj.p.id + "dust");
      for (var i = 0; i < N; i++) {
        var a = (i / N) * Math.PI * 2;
        var rx = k.line ? 6 : k.w / 2 + 0.5,
          ry = k.line ? 6 : k.d / 2 + 0.5;
        var base = obj.p.kind === "lighting" ? obj.labelPoint : [0, 0];
        pts.push({ x: base[0] + Math.cos(a) * rx * (0.85 + rand() * 0.2), y: base[1] + Math.sin(a) * ry * (0.85 + rand() * 0.2), d: rand() * 0.18, s: 0.7 + rand() * 0.6 });
      }
      var group = new THREE.Group();
      group.add(mesh);
      group.position.copy(obj.group.position);
      group.rotation.copy(obj.group.rotation);
      scene.add(group);
      var m4 = new THREE.Matrix4(),
        q = new THREE.Quaternion(),
        v = new THREE.Vector3(),
        sc = new THREE.Vector3();
      group.userData.step = function (kk) {
        pts.forEach(function (p, i) {
          var local = Math.max(0, Math.min(1, (kk - p.d) / 0.75));
          var e = easeOutCubic(local);
          var s = p.s * (0.4 + 1.3 * e);
          v.set(p.x, p.y, 0.3 + 1.4 * e);
          sc.set(s, s, s * 0.7);
          m4.compose(v, q, sc);
          mesh.setMatrixAt(i, m4);
        });
        mesh.instanceMatrix.needsUpdate = true;
        mat.opacity = 0.6 * (1 - easeOutCubic(Math.min(1, kk / 0.95)));
      };
      group.userData.step(0);
      return group;
    }

    // Удаление: объект оседает и исчезает за ~0.3 с, затем память освобождается.
    function animateRemove(id, done) {
      var obj = S.objects[id];
      if (!obj) return done && done();
      if (obj.label) obj.label.classList.add("b3d-label--hidden");
      if (reducedMotion()) {
        disposeObject(id);
        return done && done();
      }
      var t0 = performance.now();
      var H = obj.height + 0.5;
      var revealMats = [obj.mats.solid, obj.mats.glass, obj.mats.glow].filter(Boolean);
      obj.removing = true;
      anims.push({
        update: function (now) {
          var k = Math.min(1, (now - t0) / REMOVE_MS);
          revealMats.forEach(function (m) {
            m.userData.reveal.value = (1 - easeInOutCubic(k)) * H;
          });
          if (k >= 1) {
            // «Отменить» могло уже вернуть объект с тем же id (R06 ≥ d043e7b, заглушка) — новый не трогаем.
            if (S.objects[id] === obj) disposeObject(id);
            if (done) done();
            return false;
          }
          return true;
        },
      });
      repaint();
    }

    // ───────────── Подписи над объектами ─────────────
    // Позиция — проекция 3D-точки над объектом той же матрицей, что и сцена, поэтому подпись
    // остаётся над объектом при наклоне 0–60° и повороте карты. Перекрывающиеся подписи сжимаются
    // до точки (пометка «проект» остаётся: точка того же цвета + пунктир границы на земле).
    var v4 = null;
    function projectLocal(x, y, z) {
      if (!lastMatrix) return null;
      v4 = v4 || new THREE.Vector4();
      v4.set(x, y, z, 1).applyMatrix4(lastMatrix);
      if (v4.w <= 0) return null;
      var canvas = map.getCanvas();
      var w = canvas.clientWidth,
        h = canvas.clientHeight;
      return { x: ((v4.x / v4.w + 1) / 2) * w, y: ((1 - v4.y / v4.w) / 2) * h, depth: v4.z / v4.w };
    }

    function worldOf(obj, point) {
      var v = new THREE.Vector3(point[0], point[1], point[2]);
      return v.applyMatrix4(obj.group.matrixWorld);
    }

    function updateLabels() {
      var canvas = map.getCanvas();
      var w = canvas.clientWidth,
        h = canvas.clientHeight;
      var zoom = map.getZoom();
      var items = [];
      Object.keys(S.objects).forEach(function (id) {
        var obj = S.objects[id];
        if (!obj.label) return;
        var wp = worldOf(obj, obj.labelPoint);
        var sp = projectLocal(wp.x, wp.y, wp.z);
        if (!sp || sp.x < -80 || sp.x > w + 80 || sp.y < -40 || sp.y > h + 40) {
          obj.label.style.visibility = "hidden";
          return;
        }
        obj.label.style.visibility = "";
        items.push({ obj: obj, sp: sp });
      });
      // Размеры подписей меряем только после смены текста: чтение offsetWidth в каждом кадре
      // заставляло браузер пересчитывать раскладку на каждый объект.
      items.forEach(function (it) {
        if (it.obj.labelSize) return;
        var lab = it.obj.label;
        lab.classList.remove("b3d-label--dot", "b3d-label--cluster");
        var pill = lab.firstChild || lab; // наложение считаем по видимой таблетке, а не по зоне нажатия
        it.obj.labelSize = { w: pill.offsetWidth || 120, h: pill.offsetHeight || 40 };
      });
      // Ближние к зрителю (ниже на экране) — первыми; они и остаются полными подписями.
      items.sort(function (a, b) {
        return b.sp.y - a.sp.y;
      });
      var placed = [];
      var groups = [];
      items.forEach(function (it) {
        var lab = it.obj.label;
        var compact = zoom < 14;
        var hiddenNow = lab.classList.contains("b3d-label--hidden"); // строится/удаляется — места не занимает
        var lw = compact ? DOT_PX : it.obj.labelSize.w,
          lh = compact ? DOT_PX : it.obj.labelSize.h;
        var rect = { x: it.sp.x - lw / 2, y: it.sp.y - lh, w: lw, h: lh };
        if (!compact && !hiddenNow) {
          for (var i = 0; i < placed.length; i++) {
            var r = placed[i];
            if (rect.x < r.x + r.w + 4 && rect.x + rect.w + 4 > r.x && rect.y < r.y + r.h + 2 && rect.y + rect.h + 2 > r.y) {
              compact = true;
              break;
            }
          }
        }
        lab.classList.toggle("b3d-label--dot", compact);
        if (!compact && !hiddenNow) placed.push(rect);
        it.pos = it.sp;
        // Точки, которые легли друг на друга (пять проектов у одного сквера на виде «вся Астана»), — одна метка
        // с числом (R10 B-026). Выбранный проект в группу не прячем.
        if (compact && !hiddenNow && it.obj.p.id !== S.selected) {
          var g = null;
          for (var k = 0; k < groups.length; k++) {
            if (Math.abs(groups[k].x - it.sp.x) < DOT_PX + 8 && Math.abs(groups[k].y - it.sp.y) < DOT_PX + 8) {
              g = groups[k];
              break;
            }
          }
          if (g) g.members.push(it);
          else groups.push({ x: it.sp.x, y: it.sp.y, members: [it] });
        } else setCluster(it, null);
      });
      groups.forEach(function (g) {
        if (g.members.length < 2) return setCluster(g.members[0], null);
        var cx = 0,
          cy = 0;
        g.members.forEach(function (m) {
          cx += m.sp.x / g.members.length;
          cy += m.sp.y / g.members.length;
        });
        g.members.forEach(function (m, idx) {
          if (idx === 0) {
            setCluster(m, g.members.map(function (x) {
              return x.obj.p.id;
            }));
            m.pos = { x: cx, y: cy };
          } else {
            setCluster(m, null);
            m.obj.label.style.visibility = "hidden"; // показана общей меткой группы
          }
        });
      });
      items.forEach(function (it) {
        var lab = it.obj.label;
        lab.style.transform = "translate(" + Math.round(it.pos.x) + "px," + Math.round(it.pos.y) + "px) translate(-50%,-100%)";
        lab.style.zIndex = String(1000 + Math.round(it.pos.y) + (lab._cluster ? 2000 : 0));
      });
    }

    // Метка группы: число проектов, aria «5 проектов рядом — показать ближе»; нажатие приближает к ним.
    // DOM трогаем только при смене состава группы (updateLabels идёт в каждом кадре).
    function setCluster(it, ids) {
      var lab = it.obj.label;
      var key = ids ? ids.join(",") + "|" + t.lang() : null;
      if (lab._clusterKey === key) return;
      lab._clusterKey = key;
      lab._cluster = ids;
      lab.classList.toggle("b3d-label--cluster", !!ids);
      if (ids) {
        lab.querySelector(".b3d-label__count").textContent = String(ids.length);
        lab.setAttribute("aria-label", t("build3d.cluster.open", { count: t("build3d.cluster", { n: ids.length }) }));
      } else {
        lab.querySelector(".b3d-label__count").textContent = "";
        var name = t(Core.KINDS[it.obj.p.kind].key);
        lab.setAttribute("aria-label", t("build3d.card.open", { kind: name, year: String(it.obj.p.year || "") }).replace(/\s+,/, ","));
      }
    }
    function zoomToCluster(ids) {
      var pts = ids
        .map(function (id) {
          var p = S.objects[id] && S.objects[id].p;
          if (!p) return null;
          return p.kind === "lighting" ? p.geometry.coordinates[Math.floor(p.geometry.coordinates.length / 2)] : p.geometry.coordinates;
        })
        .filter(Boolean);
      if (!pts.length) return;
      var w = pts[0][0],
        sth = pts[0][1],
        e = pts[0][0],
        n = pts[0][1];
      pts.forEach(function (q) {
        w = Math.min(w, q[0]);
        e = Math.max(e, q[0]);
        sth = Math.min(sth, q[1]);
        n = Math.max(n, q[1]);
      });
      var dh = dock.getBoundingClientRect().height || 0;
      map.fitBounds(
        [
          [w, sth],
          [e, n],
        ],
        { padding: { top: 80, right: 60, bottom: Math.round(dh) + 40, left: 60 }, maxZoom: VIEW_ZOOM, duration: reducedMotion() ? 0 : 700 }
      );
    }

    // ───────────── Размещение ─────────────

    // Настоящие объекты OSM нужны только при размещении — грузим их при первом выборе в каталоге.
    function ensureExisting() {
      if (existing || existingLoading) return existingLoading || Promise.resolve(existing);
      existingLoading = fetchJson(o.dataUrl + "astana-existing.json").then(
        function (d) {
          existing = new Core.ExistingIndex(d);
          if (S.mode === "placing") {
            updateGhost(false);
            render();
          }
          return existing;
        },
        function (err) {
          console.warn("[build3d] объекты OSM не загрузились:", err.message);
          existingLoading = null;
          return null;
        }
      );
      return existingLoading;
    }

    // Подсказка «рядом уже есть …» по настоящим объектам OSM (не блокирует «Поставить»).
    function nearInfo() {
      var g = S.ghost;
      if (!g || !existing) return null;
      if (S.kind === "lighting") {
        var sec = g.section && g.section.ok ? g.section : g.preview && g.preview.ok ? g.preview : null;
        var n = sec ? existing.lampsAlong(sec.coords) : 0;
        return n ? { key: "build3d.near.lamps", params: { n: n } } : null;
      }
      var near = existing.nearestSame(S.kind, g.pos);
      if (!near) return null;
      var name = t.lang() === "kk" ? near.name_kk || near.name_ru : near.name_ru || near.name_kk;
      var m = Math.max(5, Math.round(near.dist_m / 5) * 5);
      if (S.kind === "square" && near.dist_m === 0) return { key: "build3d.near.square_inside", params: null, id: near.id };
      var named = name && (S.kind === "stop" || S.kind === "square");
      return { key: "build3d.near." + S.kind + (named ? "_named" : ""), params: { m: m, name: name }, id: near.id };
    }

    function start(kind, how) {
      how = how || {};
      if (!Core.KINDS[kind] || S.phase !== "ready" || o.role !== "akimat") return false;
      if (Object.keys(S.objects).length >= Core.MAX_OBJECTS) {
        toast(t("proposal.limit"), { error: true });
        return false;
      }
      if (S.mode === "placing") clearGhost();
      S.selected = null;
      S.mode = "placing";
      S.kind = kind;
      var c = map.getCenter();
      var touch = !hoverPointer() || how.keyboard;
      S.ghost = {
        pos: [c.lng, c.lat],
        rot: 0,
        shownRot: 0,
        follow: "center", // center → за центром карты (палец, клавиатура); cursor → за мышью; pinned → по щелчку
        manualRot: false,
        valid: { ok: true },
        a: null,
        section: null,
        hoverSnap: null,
        touch: touch,
      };
      if (kind === "lighting") {
        S.ghost.follow = "pinned";
        setHint("build3d.hint.segment_start"); // улицы: R12 по всему городу или свой индекс Нуры
      } else setHint(touch ? "build3d.hint.touch" : "proposal.place_hint");
      setTool(true);
      ensureExisting();
      // UX_REVIEW день 3 #20: на 16-м масштабе сквер — 70 px, фонари — штрихи. Выбрав объект в каталоге,
      // пользователь сам просит размещение, поэтому плавно приближаем до 17.5 (наклон и поворот не трогаем).
      if (o.autoZoom && map.getZoom() < PLACE_ZOOM - 0.5) {
        map.easeTo({ zoom: PLACE_ZOOM, duration: reducedMotion() ? 0 : 700 });
      }
      updateGhost(true);
      render();
      focusDock("[data-action=place]");
      return true;
    }

    function cancel() {
      if (S.mode !== "placing") return;
      clearGhost();
      S.mode = "idle";
      S.kind = null;
      S.ghost = null;
      S.hint = null;
      setTool(false);
      render();
      focusDock(".b3d-card");
    }

    function setTool(active) {
      map.getCanvas().style.cursor = active ? "crosshair" : "";
      if (typeof opts.onToolChange === "function") {
        try {
          opts.onToolChange(active, S.kind);
        } catch (e) {
          console.error(e);
        }
      }
      try {
        doc.dispatchEvent(new CustomEvent("civic-build3d:tool", { detail: { active: active, kind: S.kind } }));
      } catch (e) {
        /* старые браузеры без CustomEvent — не страшно */
      }
    }

    function setHint(key, params, error) {
      S.hint = key ? { key: key, params: params || null, error: !!error } : null;
    }

    function focusDock(selector) {
      setTimeout(function () {
        var n = dock.querySelector(selector);
        if (n && doc.activeElement && (doc.activeElement === doc.body || ui.contains(doc.activeElement) || !doc.activeElement.closest)) {
          try {
            n.focus({ preventScroll: true });
          } catch (e) {
            n.focus();
          }
        }
      }, 0);
    }

    function rotate(delta) {
      if (S.mode !== "placing" || !S.ghost || Core.KINDS[S.kind].line) return;
      S.ghost.rot = Core.normDeg(S.ghost.rot + delta);
      S.ghost.manualRot = true;
      if (S.ghost.follow !== "cursor") setHint("build3d.hint.rotate");
      updateGhost(false);
      render();
    }

    // Черновик предложения из текущего призрака.
    function draftFromGhost() {
      var g = S.ghost;
      if (!g) return null;
      if (S.kind === "lighting") {
        if (!g.section || !g.section.ok) return null;
        return {
          kind: "lighting",
          geometry: { type: "LineString", coordinates: g.section.coords },
          rotation_deg: 0,
          status: "proposal",
          year: o.year,
          district: districts ? Core.districtAt(districts, g.section.coords[0]) : null,
          near_street: g.section.name,
          target: { kind: "segment", id: g.section.edge_ids[0], ids: g.section.edge_ids, label_ru: g.section.name, label_kk: g.section.name_kk || g.section.name },
          demo: false,
        };
      }
      var near = streets ? streets.nearest(g.pos, 120) : null;
      var yard = existing ? existing.yardAt(g.pos) : null; // двор OSM → цель «area» (CONTRACT §4)
      return {
        kind: S.kind,
        target: yard ? { kind: "area", id: yard.id, label_ru: yard.name_ru, label_kk: yard.name_kk } : null,
        geometry: { type: "Point", coordinates: [round6(g.pos[0]), round6(g.pos[1])] },
        rotation_deg: Math.round(g.rot),
        status: "proposal",
        year: o.year,
        district: districts ? Core.districtAt(districts, g.pos) : null,
        near_street: near ? near.edge.name : null,
        demo: false,
      };
    }

    function round6(v) {
      return Math.round(v * 1e6) / 1e6;
    }

    function existingList() {
      return Object.keys(S.objects)
        .map(function (id) {
          return S.objects[id];
        })
        .filter(function (obj) {
          return !obj.removing;
        })
        .map(function (obj) {
          return obj.p;
        });
    }

    // Пересобрать призрак (при смене вида/участка) и обновить его положение, поворот и цвет.
    function updateGhost(rebuild) {
      if (!scene || !S.ghost) return;
      var g = S.ghost;
      var kind = S.kind;
      if (kind === "lighting") {
        rebuild = true;
        var chosen = g.section && g.section.ok ? g.section : null;
        var shown = chosen || (g.a && g.preview && g.preview.ok ? g.preview : null);
        var coords = shown ? shown.coords : null;
        var single = !coords && (g.hoverSnap || g.a) ? [g.a || g.hoverSnap.lngLat] : null;
        g.valid = { ok: !!chosen };
        if (coords) {
          var vc = Core.checkPlacement({ kind: "lighting", geometry: { type: "LineString", coordinates: coords } }, existingList(), districts);
          g.valid = chosen ? vc : { ok: false, reason: vc.ok ? "pending" : vc.reason };
        }
        var bad = !!(coords && g.valid.reason && g.valid.reason !== "pending");
        setGhostGeometry(
          coords
            ? lightingOpts(coords)
            : single
              ? { poles: [{ p: [0, 0], dir: g.dirHint || [1, 0] }], line: null, offset: Core.LIGHT_OFFSET_M }
              : null,
          coords ? coords[0] : single ? single[0] : null,
          0,
          bad
        );
        return;
      }
      // Остановка сама встаёт вдоль ближайшей улицы, пока её не повернули вручную.
      if (kind === "stop" && !g.manualRot && streets) {
        var near = streets.nearest(g.pos, Core.STOP_ALIGN_M);
        if (near) {
          var local = Core.toLocal(g.pos, near.lngLat);
          var toStreet = Core.bearingDeg(local[0], local[1]);
          var cand = [Core.normDeg(near.bearing - 90), Core.normDeg(near.bearing + 90)];
          // Улица должна оказаться с «открытой» стороны павильона (−y модели → азимут 180 + rot).
          var diff = function (a, b) {
            var d = Math.abs(Core.normDeg(a - b));
            return d > 180 ? 360 - d : d;
          };
          g.rot = diff(cand[0] + 180, toStreet) <= diff(cand[1] + 180, toStreet) ? cand[0] : cand[1];
          if (Math.hypot(local[0], local[1]) < 0.5) g.rot = cand[0];
        }
      }
      var draft = draftFromGhost();
      var v = Core.checkPlacement(draft, existingList(), districts);
      var wasInvalid = g.valid && !g.valid.ok;
      g.valid = v;
      if (!v.ok) setHint("build3d.err." + (v.reason === "limit" ? "overlap" : v.reason), null, true);
      else if (wasInvalid || (S.hint && S.hint.error)) setHint(g.follow === "pinned" ? "build3d.hint.rotate" : g.touch ? "build3d.hint.touch" : "proposal.place_hint");
      if (v.reason === "limit") setHint("proposal.limit", null, true);
      var k = Core.KINDS[kind];
      if (rebuild || !ghostGroup.children.length || ghostGroup.userData.kind !== kind || ghostGroup.userData.invalid !== !v.ok) {
        setGhostGeometry({ seed: "ghost", w: k.w, d: k.d }, g.pos, g.rot, !v.ok);
      } else {
        positionGhost(g.pos, g.rot);
      }
    }

    function setGhostGeometry(modelOpts, anchor, rot, invalid) {
      ghostGroup.children.slice().forEach(function (child) {
        disposeGroup(child);
      });
      ghostGroup.userData.kind = S.kind;
      ghostGroup.userData.invalid = !!invalid;
      if (!modelOpts || !anchor) {
        ghostGroup.visible = false;
        repaint();
        return;
      }
      var geos = Models.build(S.kind, modelOpts);
      var inner = makeMeshes(geos, makeMaterials(true, invalid));
      ghostGroup.add(inner);
      ghostGroup.visible = true;
      positionGhost(anchor, rot);
    }

    function positionGhost(anchor, rot) {
      var local = Core.toLocal(origin, anchor);
      ghostGroup.position.set(local[0], local[1], 0.05);
      ghostGroup.userData.targetRot = rot || 0;
      if (reducedMotion() || S.kind === "lighting") {
        S.ghost.shownRot = rot || 0;
      } else if (!anims.some(function (a) {
          return a.ghostRot;
        })) {
        // Плавный поворот призрака за 200 мс.
        anims.push({
          ghostRot: true,
          update: function () {
            if (!S.ghost) return false;
            var target = ghostGroup.userData.targetRot || 0;
            var d = Core.normDeg(target - S.ghost.shownRot);
            if (d > 180) d -= 360;
            if (Math.abs(d) < 0.5) {
              S.ghost.shownRot = target;
              ghostGroup.rotation.z = -target * DEG;
              return false;
            }
            S.ghost.shownRot = Core.normDeg(S.ghost.shownRot + d * 0.35);
            ghostGroup.rotation.z = -S.ghost.shownRot * DEG;
            return true;
          },
        });
      }
      ghostGroup.rotation.z = -(S.ghost.shownRot || 0) * DEG;
      ghostGroup.updateMatrixWorld(true);
      repaint();
    }

    function clearGhost() {
      if (!ghostGroup) return;
      ghostGroup.children.slice().forEach(function (child) {
        disposeGroup(child);
      });
      ghostGroup.visible = false;
      repaint();
    }

    // ── Ввод на карте ──

    // Подсказка, что модель можно нажать: курсор-указатель над объектом (UX_REVIEW день 3 #21).
    var hoverScheduled = false,
      hoverPoint = null,
      cursorOwned = false;
    function onHover(e) {
      hoverPoint = e.point;
      if (hoverScheduled) return;
      hoverScheduled = true;
      (root.requestAnimationFrame || setTimeout)(function () {
        hoverScheduled = false;
        if (S.mode === "placing" || !hoverPoint) return;
        var hit = hitTest(hoverPoint);
        var cv = map.getCanvas();
        if (hit) {
          cv.style.cursor = "pointer";
          cursorOwned = true;
        } else if (cursorOwned) {
          cv.style.cursor = ""; // возвращаем только свой курсор, чужой (например, перекрестие редактора) не трогаем
          cursorOwned = false;
        }
        Object.keys(S.objects).forEach(function (id) {
          if (S.objects[id].label) S.objects[id].label.classList.toggle("b3d-label--hover", id === hit);
        });
      });
    }

    function onMouseMove(e) {
      if (S.mode !== "placing") return onHover(e);
      if (!S.ghost) return;
      var g = S.ghost;
      var ll = [e.lngLat.lng, e.lngLat.lat];
      if (S.kind === "lighting") {
        if (!streets) return;
        if (g.section && g.section.ok && g.b) return; // участок выбран — ждём «Поставить» или новый щелчок
        if (g.a) {
          g.preview = streets.section(g.a, ll); // только предпросмотр: «Поставить» — после второго щелчка
        } else {
          var snap = streets.nearest(ll, Core.SNAP_STREET_M);
          g.hoverSnap = snap;
          g.dirHint = snap ? [Math.sin(snap.bearing * DEG), Math.cos(snap.bearing * DEG)] : null;
        }
        scheduleGhost();
        return;
      }
      if (g.follow === "pinned") return;
      g.follow = "cursor";
      g.touch = false;
      g.pos = ll;
      scheduleGhost();
    }

    var ghostScheduled = false;
    function scheduleGhost() {
      if (ghostScheduled) return;
      ghostScheduled = true;
      (root.requestAnimationFrame || setTimeout)(function () {
        ghostScheduled = false;
        if (S.mode === "placing") updateGhost(false);
        if (S.kind === "lighting") render();
      });
    }

    function onMapMove() {
      if (S.mode !== "placing" || !S.ghost || S.kind === "lighting") return;
      if (S.ghost.follow !== "center") return;
      var c = map.getCenter();
      S.ghost.pos = [c.lng, c.lat];
      scheduleGhost();
    }

    function onMapClick(e) {
      var target = e.originalEvent && e.originalEvent.target;
      if (target && target.closest && target.closest(".b3d-label")) return; // щелчок по подписи — её обработчик
      var ll = [e.lngLat.lng, e.lngLat.lat];
      if (S.mode === "placing") {
        if (e.originalEvent) e.originalEvent.civicBuild3d = true; // хост может не открывать свою карточку
        var g = S.ghost;
        if (S.kind === "lighting") return clickLighting(ll);
        g.pos = ll;
        g.follow = "pinned";
        setHint("build3d.hint.rotate");
        updateGhost(false);
        render();
        return;
      }
      var hit = hitTest(e.point);
      if (hit) {
        if (e.originalEvent) e.originalEvent.civicBuild3d = true;
        select(hit);
      } else if (S.selected) select(null);
    }

    // ── Участок улицы для освещения ──
    // Основной источник — R12 (engine.civic_geo через шлюз R01): GET /street-snap и /street-segment, весь город,
    // с казахским названием улицы. Пока маршрутов нет (404/405/501/503 или нет сервера) — свой индекс улиц Нуры
    // (data/nura-streets.json): та же форма OSM, тот же расчёт (проверено: ул. Сыганак 184.3 м у обоих).
    var geo = { state: "unknown" }; // unknown | ok | off
    function geoGet(path) {
      if (geo.state === "off") return Promise.resolve(null);
      var req =
        opts.api && typeof opts.api.v2 === "function" && o.geoPrefix === o.apiPrefix
          ? Promise.resolve().then(function () {
              return opts.api.v2("GET", path);
            })
          : fetch(o.geoPrefix + path, { credentials: "same-origin", headers: { Accept: "application/json" } }).then(function (res) {
              return res.json().then(
                function (data) {
                  return { res: res, data: data };
                },
                function () {
                  return { res: res, data: null };
                }
              ).then(function (r) {
                if (!r.res.ok) {
                  var e = new Error("geo");
                  e.status = r.res.status;
                  e.error = r.data && (typeof r.data.error === "string" ? r.data.error : (r.data.error && r.data.error.code) || r.data.code);
                  throw e;
                }
                return r.data;
              });
            });
      return req.then(
        function (data) {
          geo.state = "ok";
          return data && data.ok === true && data.data ? data.data : data;
        },
        function (err) {
          var st = err && err.status;
          if (!st || st === 404 || st === 405 || st === 501 || st === 503) {
            geo.state = "off"; // маршрутов R12 на этом сервере нет — дальше только свой индекс
            return null;
          }
          var e = new Error("geo");
          e.status = st;
          e.code = err.error || err.code;
          throw e;
        }
      );
    }
    function ll2(q) {
      return q[0].toFixed(7) + "," + q[1].toFixed(7);
    }
    // Ответ R12 segment_between → участок в формате модуля (как у StreetIndex.section).
    function fromR12Segment(seg, fallbackName, fallbackKk) {
      if (!seg || !seg.geometry || seg.geometry.type !== "LineString" || seg.geometry.coordinates.length < 2) return null;
      // Отказ — только если путь идёт по двум и более РАЗНЫМ названным улицам. Безымянные проезды R12 отдаёт
      // с same_street:false (у них нет имени) — это всё ещё один участок, его можно осветить.
      var names = (seg.names || []).filter(function (n, i, all) {
        return n && all.indexOf(n) === i;
      });
      var name = seg.street_ru || names[0] || seg.label_ru || fallbackName || null;
      if (names.length > 1) return { ok: false, reason: "other_street", name: name };
      var L = seg.length_m;
      if (L < Core.LIGHT_MIN_M) return { ok: false, reason: "too_short", name: name };
      if (L > Core.LIGHT_MAX_M) return { ok: false, reason: "too_long", name: name };
      var nameKk = seg.street_kk || seg.label_kk || (!seg.street_ru && !names.length ? fallbackKk : null) || null;
      return { ok: true, name: name, name_kk: nameKk, coords: seg.geometry.coordinates, length_m: L, edge_ids: seg.edge_ids || [], source: "r12" };
    }
    function geoReason(code) {
      return code === "not_on_street" ? "far_from_street" : code === "too_long" ? "too_long" : "no_path";
    }
    function streetLabel(sec) {
      return streetName(sec.name, sec.name_kk) || t("build3d.street.this");
    }
    function applySection(g, sec, ll) {
      if (sec && sec.ok) {
        g.section = sec;
        g.b = ll;
        var n = Core.sampleAlong(lightingOpts(sec.coords).line, Core.LIGHT_STEP_M).length;
        setHint("build3d.hint.segment_ready", { street: streetLabel(sec), length: Math.round(sec.length_m), poles: t("build3d.poles", { n: n }) });
      } else {
        g.section = null;
        setHint("build3d.err." + ((sec && sec.reason) || "no_path"), { street: (sec && sec.name ? streetName(sec.name, sec.name_kk) : streetName(g.aStreet, g.aStreetKk)) || t("build3d.street.this") }, true);
      }
      updateGhost(true);
      render();
    }

    function clickLighting(ll) {
      var g = S.ghost;
      var seq = (g.seq = (g.seq || 0) + 1);
      var stale = function () {
        return S.ghost !== g || g.seq !== seq;
      };
      if (!g.a || (g.section && g.section.ok && g.b)) {
        var snap = streets ? streets.nearest(ll, Core.SNAP_STREET_M) : null;
        g.section = null;
        g.preview = null;
        g.b = null;
        g.a = null;
        if (snap) {
          g.a = snap.lngLat;
          g.aStreet = snap.edge.name;
          g.aStreetKk = snap.edge.name_kk || null;
          g.dirHint = [Math.sin(snap.bearing * DEG), Math.cos(snap.bearing * DEG)];
          setHint("build3d.hint.segment_end", { street: streetName(snap.edge.name, snap.edge.name_kk) || t("build3d.street.this") });
        } else {
          setHint(streets && inStreetArea(ll) ? "build3d.err.far_from_street" : "build3d.err.no_streets", null, true);
          // Вне своего индекса — спросим привязку к улице у R12.
          geoGet("/street-snap?lon=" + ll[0].toFixed(7) + "&lat=" + ll[1].toFixed(7) + "&kind=road").then(
            function (sn) {
              if (stale() || !sn) return;
              if (sn.point && sn.distance_m <= Core.SNAP_STREET_M + 15) {
                g.a = sn.point;
                g.aStreet = sn.street_ru || sn.label_ru;
                g.aStreetKk = sn.street_kk || sn.label_kk || null;
                setHint("build3d.hint.segment_end", { street: t.lang() === "kk" ? sn.street_kk || sn.label_kk || g.aStreet : g.aStreet });
              } else setHint("build3d.err.far_from_street", null, true);
              updateGhost(true);
              render();
            },
            function (err) {
              if (stale()) return;
              setHint("build3d.err." + geoReason(err.code), null, true);
              render();
            }
          );
        }
        updateGhost(true);
        return render();
      }
      var a = g.a;
      var local = streets ? streets.section(a, ll) : { ok: false, reason: "no_streets" };
      if (local.ok || geo.state === "off") applySection(g, local, ll);
      // Участок от R12 точнее и с казахским названием — заменяет свой, когда приходит.
      geoGet("/street-segment?from=" + ll2(a) + "&to=" + ll2(ll) + "&kind=road").then(
        function (seg) {
          if (stale()) return;
          var sec = fromR12Segment(seg, g.aStreet, g.aStreetKk);
          if (sec && (sec.ok || !local.ok)) applySection(g, sec, ll);
          else if (!sec && !local.ok) applySection(g, local, ll);
        },
        function (err) {
          if (stale() || local.ok) return;
          applySection(g, { ok: false, reason: geoReason(err.code), name: g.aStreet }, ll);
        }
      );
    }

    function inStreetArea(ll) {
      var bb = streets && streets.bbox;
      if (!bb && streets && streets.origin) return true;
      return !bb || (ll[0] >= bb[0] && ll[0] <= bb[2] && ll[1] >= bb[1] && ll[1] <= bb[3]);
    }

    // Попадание щелчком в объект: экранный прямоугольник его 3D-габарита (у освещения — опоры).
    function hitTest(point) {
      if (!lastMatrix) return null;
      var best = null;
      Object.keys(S.objects).forEach(function (id) {
        var obj = S.objects[id];
        if (obj.removing) return;
        var box = obj.group.children.length ? new THREE.Box3().setFromObject(obj.group) : null;
        if (!box || box.isEmpty()) return;
        if (obj.p.kind === "lighting") {
          var lo = lightingOpts(obj.p.geometry.coordinates);
          lo.poles.forEach(function (pole) {
            var nx = pole.dir[1],
              ny = -pole.dir[0];
            var base = worldOf(obj, [pole.p[0] + nx * lo.offset, pole.p[1] + ny * lo.offset, 0]);
            var a = projectLocal(base.x, base.y, 0),
              b = projectLocal(base.x, base.y, 8.5);
            if (!a || !b) return;
            var d = distToSeg(point, a, b);
            if (d < 22 && (!best || d < best.d)) best = { id: id, d: d };
          });
          return;
        }
        var minX = Infinity,
          minY = Infinity,
          maxX = -Infinity,
          maxY = -Infinity,
          ok = true;
        [box.min.x, box.max.x].forEach(function (x) {
          [box.min.y, box.max.y].forEach(function (y) {
            [box.min.z, box.max.z].forEach(function (z) {
              var sp = projectLocal(x, y, z);
              if (!sp) {
                ok = false;
                return;
              }
              minX = Math.min(minX, sp.x);
              maxX = Math.max(maxX, sp.x);
              minY = Math.min(minY, sp.y);
              maxY = Math.max(maxY, sp.y);
            });
          });
        });
        if (!ok) return;
        if (point.x >= minX && point.x <= maxX && point.y >= minY && point.y <= maxY) {
          var d = Math.hypot(point.x - (minX + maxX) / 2, point.y - (minY + maxY) / 2);
          if (!best || d < best.d) best = { id: id, d: d };
        }
      });
      return best ? best.id : null;
    }

    function distToSeg(p, a, b) {
      var dx = b.x - a.x,
        dy = b.y - a.y;
      var L2 = dx * dx + dy * dy;
      var tt = L2 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L2)) : 0;
      return Math.hypot(p.x - a.x - dx * tt, p.y - a.y - dy * tt);
    }

    function onKey(e) {
      if (S.mode !== "placing") return;
      var tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "Escape") {
        e.preventDefault();
        cancel();
      } else if ((e.key === "r" || e.key === "R" || e.key === "к" || e.key === "К") && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        rotate(e.shiftKey ? -ROTATE_STEP : ROTATE_STEP);
      }
    }

    // ───────────── Действия с предложениями ─────────────

    function place_() {
      if (S.mode !== "placing" || !S.ghost) return;
      var draft = draftFromGhost();
      var v = draft ? Core.checkPlacement(draft, existingList(), districts) : { ok: false, reason: "invalid" };
      if (!v.ok) {
        if (v.reason === "limit") toast(t("proposal.limit"), { error: true });
        return;
      }
      // Сразу строим (отзывчиво), а сохраняем параллельно. Не сохранилось — убираем и предлагаем повторить.
      var tempId = Core.newId();
      draft.id = tempId;
      var provisional = Core.normalizeProposal(Object.assign({}, draft, { votes_up: 0, votes_down: 0 }));
      clearGhost();
      S.mode = "idle";
      S.kind = null;
      S.ghost = null;
      S.hint = null;
      setTool(false);
      var obj = addObject(provisional, { animate: true, pending: true });
      render();
      focusDock(".b3d-card");
      store.create(draft).then(
        function (saved) {
          if (S.destroyed) return;
          S.storeMode = store.mode || S.storeMode;
          if (saved.id !== tempId && S.objects[tempId]) {
            S.objects[saved.id] = S.objects[tempId];
            delete S.objects[tempId];
            obj.label.setAttribute("data-id", saved.id);
          }
          obj.p = saved;
          obj.pending = false;
          updateLabelText(obj);
          toast(t(S.storeMode === "local" ? "build3d.placed_local" : "build3d.placed"), {
            action: t("common.action.cancel"),
            actionId: "undo",
            onAction: function () {
              removeProposal(saved.id, { silent: true });
            },
          });
          render();
        },
        function (err) {
          logFail("[build3d] не сохранилось", err);
          animateRemove(tempId);
          if (isStaffError(err)) return toast(t("proposal.need_staff"), { error: true });
          if (isTooMany(err)) return toast(t("common.error.too_many"), { error: true });
          toast(t(err && err.code === "limit" ? "proposal.limit" : "build3d.save_failed"), {
            error: true,
            action: t("common.action.retry"),
            actionId: "retry-save",
            onAction: function () {
              delete draft.id;
              store.create(draft).then(function (saved) {
                addObject(saved, { animate: true });
                render();
              }, function () {
                toast(t("build3d.save_failed"), { error: true });
              });
            },
          });
        }
      );
    }

    function removeProposal(id, flags) {
      flags = flags || {};
      var obj = S.objects[id];
      if (!obj) return;
      var snapshot = JSON.parse(JSON.stringify(obj.p));
      S.cardBusy = "delete";
      render();
      store.remove(id).then(
        function () {
          S.cardBusy = null;
          if (S.selected === id) S.selected = null;
          animateRemove(id, function () {
            render();
          });
          render();
          emitSelect(null);
          if (!flags.silent) {
            toast(t("build3d.deleted"), {
              action: t("common.action.cancel"),
              actionId: "undo",
              onAction: function () {
                store.restore(snapshot).then(function (p) {
                  addObject(p, { animate: true });
                  render();
                }, function () {
                  toast(t("build3d.save_failed"), { error: true });
                });
              },
            });
          }
        },
        function (err) {
          S.cardBusy = null;
          render();
          if (isTooMany(err)) return toast(t("common.error.too_many"), { error: true });
          toast(t("build3d.save_failed"), {
            error: true,
            action: t("common.action.retry"),
            actionId: "retry-delete",
            onAction: function () {
              removeProposal(id, flags);
            },
          });
        }
      );
    }

    function vote(id, value) {
      var obj = S.objects[id];
      if (!obj || S.cardBusy) return;
      S.cardBusy = "vote" + value;
      render();
      store.vote(id, value, deviceId).then(
        function (p) {
          S.cardBusy = null;
          if (S.objects[id]) {
            S.objects[id].p = p;
            emitSelect(p);
          }
          render();
          focusDock("[data-action=" + (value === 1 ? "vote-up" : "vote-down") + "]");
        },
        function (err) {
          S.cardBusy = null;
          render();
          if (err && (err.code === "voting_closed" || err.code === "already_decided")) {
            toast(t("proposal.voting_closed"), { error: true });
            return loadProposals();
          }
          if (isTooMany(err)) return toast(t("common.error.too_many"), { error: true });
          toast(t("build3d.vote_failed"), {
            error: true,
            action: t("common.action.retry"),
            actionId: "retry-vote",
            onAction: function () {
              vote(id, value);
            },
          });
        }
      );
    }

    function select(id) {
      if (id && !S.objects[id]) id = null;
      if (S.mode === "placing" && id) cancel();
      S.selected = id;
      Object.keys(S.objects).forEach(function (k) {
        var obj = S.objects[k];
        updateLabelText(obj);
        var outline = obj.group.children.find(function (m) {
          return m.userData.part === "outline";
        });
        if (outline) outline.material.color.set(k === id ? OUTLINE_SELECTED : OUTLINE_COLOR);
      });
      render();
      emitSelect(id ? S.objects[id].p : null);
      if (id) {
        // «Проект поставлен · Отменить» больше не нужен: в карточке есть «Удалить», а тост закрывал бы объект
        // над карточкой (оболочка R01 ставит тосты над панелью). Ошибки с «Повторить» остаются.
        if (!toastIsError) clearToast();
        focusDock("[data-action=vote-up]");
        fitDock(); // хозяин мог опустить шторку в onSelect — место для карточки уже другое
        keepAboveDock(S.objects[id]);
      }
      repaint();
    }

    // Прямоугольники панелей хозяина поверх карты (шапка, шторка, колонки, кнопки), видимые сейчас.
    function avoidRects() {
      if (typeof opts.avoid !== "function") return [];
      var list = [];
      try {
        list = opts.avoid() || [];
      } catch (e) {
        list = [];
      }
      return Array.prototype.slice.call(list).map(function (node) {
        return node && node.getBoundingClientRect && !node.hidden ? node.getBoundingClientRect() : null;
      }).filter(function (r) {
        return r && r.width && r.height;
      });
    }
    // Вычесть из свободной области панель r: отрезаем ту сторону, после которой остаётся больше места
    // (шапка — сверху, колонка справа — справа, плашка «Территория» в углу — слева). Панель вне области — без изменений.
    function cutBest(a, r) {
      var g = 12;
      if (r.x1 <= a.x0 || r.x0 >= a.x1 || r.y1 <= a.y0 || r.y0 >= a.y1) return a;
      var opts2 = [
        { x0: Math.max(a.x0, r.x1 + g), y0: a.y0, x1: a.x1, y1: a.y1 },
        { x0: a.x0, y0: a.y0, x1: Math.min(a.x1, r.x0 - g), y1: a.y1 },
        { x0: a.x0, y0: Math.max(a.y0, r.y1 + g), x1: a.x1, y1: a.y1 },
        { x0: a.x0, y0: a.y0, x1: a.x1, y1: Math.min(a.y1, r.y0 - g) },
      ];
      var best = null,
        bestArea = 0;
      opts2.forEach(function (b) {
        var ar = Math.max(0, b.x1 - b.x0) * Math.max(0, b.y1 - b.y0);
        if (ar > bestArea) {
          best = b;
          bestArea = ar;
        }
      });
      // Слишком мало места (панели закрывают почти всё) — оставляем как было: лучше частично, чем никак.
      return best && best.x1 - best.x0 >= 160 && best.y1 - best.y0 >= 120 ? best : a;
    }
    function freeArea() {
      var canvas = map.getCanvas();
      var cr = canvas.getBoundingClientRect();
      var w = canvas.clientWidth,
        h = canvas.clientHeight;
      // Режим overlay: начинаем с области корня модуля (она уже без панелей хозяина, см. applyInsets).
      // Корень, который ставит хозяин (оболочка R01: полоса внизу по размеру панели), — не область карты:
      // тогда начинаем со всего холста. Порядок: своя панель → панели хозяина (opts.avoid) → тост.
      var ur = ui.getBoundingClientRect();
      var a = ui.classList.contains("b3d--overlay") && ur.width && ur.height
        ? { x0: Math.max(0, ur.left - cr.left), y0: Math.max(0, ur.top - cr.top), x1: Math.min(w, ur.right - cr.left), y1: Math.min(h, ur.bottom - cr.top) }
        : { x0: 0, y0: 0, x1: w, y1: h };
      var dr = dock.getBoundingClientRect();
      if (dr.width && dr.height && !ui.hidden) {
        var left = dr.left - cr.left,
          top = dr.top - cr.top;
        if (left > a.x0 + (a.x1 - a.x0) * 0.45 && top < a.y0 + (a.y1 - a.y0) * 0.3) a.x1 = Math.max(a.x0 + 120, left); // карточка справа
        else a.y1 = Math.max(a.y0 + 120, top); // панель снизу
      }
      avoidRects().forEach(function (r) {
        a = cutBest(a, { x0: r.left - cr.left, y0: r.top - cr.top, x1: r.right - cr.left, y1: r.bottom - cr.top });
      });
      // Видимый тост («Проект поставлен… Отменить») тоже занимает место над панелью — объект ставим выше него.
      var tr = toasts.getBoundingClientRect();
      if (tr.height && tr.top - cr.top < a.y1 && tr.left - cr.left < a.x1) a.y1 = Math.max(a.y0 + 120, tr.top - cr.top);
      return a;
    }
    // Выбранный объект не должен прятаться под карточкой (UX_REVIEW день 3 #21): считаем свободную часть карты
    // (слева от карточки на ноутбуке, над панелью на телефоне) и, если объект вне её, плавно ставим его в её
    // центр. Это ответ на нажатие пользователя, поэтому правило «карта сама не двигается» не нарушается.
    function keepAboveDock(obj) {
      if (!obj || !lastMatrix) return;
      var ground = worldOf(obj, obj.p.kind === "lighting" ? [obj.labelPoint[0], obj.labelPoint[1], 0] : [0, 0, 0]);
      var sp = projectLocal(ground.x, ground.y, 0);
      if (!sp) return;
      var f = freeArea();
      var m = 48; // запас: подпись над объектом тоже должна быть видна
      var inside = sp.x > f.x0 + m && sp.x < f.x1 - m && sp.y > f.y0 + m + 60 && sp.y < f.y1 - m;
      if (inside) return;
      var tx = (f.x0 + f.x1) / 2,
        ty = f.y0 + (f.y1 - f.y0) * 0.6;
      // easeTo с offset: MapLibre ставит точку объекта в нужное место экрана с учётом наклона
      // (panBy двигает центр, а при наклоне точки у края экрана смещаются на другое расстояние).
      var canvas = map.getCanvas();
      var anchor = obj.p.kind === "lighting" ? obj.p.geometry.coordinates[Math.floor(obj.p.geometry.coordinates.length / 2)] : obj.p.geometry.coordinates;
      map.easeTo({
        center: anchor,
        offset: [tx - canvas.clientWidth / 2, ty - canvas.clientHeight / 2],
        duration: reducedMotion() ? 0 : 450,
      });
    }

    // Крупный план проектов (для оболочки: открыли «3D-превью» — камера к проектам; UX_REVIEW день 3 #20).
    // Не «вписать всё»: с наклоном 60° это даёт масштаб ~16, где модели не видны. Берём проект, ближайший
    // к центру группы, и ставим его над панелью на масштабе 17.4; соседние проекты остаются в кадре.
    function flyToProposals(how) {
      how = how || {};
      var anchors = Object.keys(S.objects).map(function (id) {
        var p = S.objects[id].p;
        return p.kind === "lighting" ? p.geometry.coordinates[Math.floor(p.geometry.coordinates.length / 2)] : p.geometry.coordinates;
      });
      if (!anchors.length) return false;
      var cx = 0,
        cy = 0;
      anchors.forEach(function (a) {
        cx += a[0] / anchors.length;
        cy += a[1] / anchors.length;
      });
      var best = anchors[0];
      anchors.forEach(function (a) {
        if (Core.haversineM(a, [cx, cy]) < Core.haversineM(best, [cx, cy])) best = a;
      });
      var dh = dock.getBoundingClientRect().height || 0;
      map.easeTo({
        center: best,
        zoom: how.zoom || VIEW_ZOOM,
        padding: { top: 40, right: 0, bottom: Math.round(dh * 0.8), left: 0 },
        duration: how.duration != null ? how.duration : reducedMotion() ? 0 : 900,
      });
      return true;
    }

    function emitSelect(p) {
      if (typeof opts.onSelect === "function") {
        try {
          opts.onSelect(p ? JSON.parse(JSON.stringify(p)) : null);
        } catch (e) {
          console.error(e);
        }
      }
    }

    // ───────────── Язык ─────────────
    function onLang() {
      Object.keys(S.objects).forEach(function (id) {
        updateLabelText(S.objects[id]);
      });
      if (S.mode === "placing" && S.kind === "lighting" && S.ghost && S.ghost.section && S.ghost.section.ok) {
        var sec = S.ghost.section;
        var n = Core.sampleAlong(lightingOpts(sec.coords).line, Core.LIGHT_STEP_M).length;
        setHint("build3d.hint.segment_ready", { street: streetLabel(sec), length: Math.round(sec.length_m), poles: t("build3d.poles", { n: n }) });
      } else if (S.mode === "placing" && S.kind === "lighting" && S.ghost && S.ghost.a && S.ghost.aStreet && S.hint && S.hint.key === "build3d.hint.segment_end") {
        // Начало участка уже выбрано: название улицы — на новом языке (в подсказке оно подставлено текстом).
        setHint("build3d.hint.segment_end", { street: streetName(S.ghost.aStreet, S.ghost.aStreetKk) || t("build3d.street.this") });
      }
      render(true);
      repaint();
    }

    // «Акимат / Житель» без пересоздания модуля: событие оболочки R01 document "birge:mode" {detail:{mode}}.
    function setMode(mode) {
      var r = mode === "resident" ? "resident" : "akimat";
      if (r === o.role) return;
      if (S.mode === "placing") cancel();
      // «Проект поставлен · Отменить» акимата — не для жителя (и закрывал бы объект над карточкой).
      clearToast();
      o.role = r;
      ui.setAttribute("data-b3d-role", r);
      render(true);
    }
    function onShellMode(e) {
      if (e && e.detail && e.detail.mode) setMode(e.detail.mode);
    }

    // ───────────── Подписки ─────────────
    map.on("mousemove", onMouseMove);
    map.on("click", onMapClick);
    map.on("move", onMapMove);
    map.on("styledata", onStyleData);
    doc.addEventListener("keydown", onKey);
    if (opts.followShellMode !== false) doc.addEventListener("birge:mode", onShellMode);
    var onResize = function () {
      applyInsets();
      fitDock();
    };
    root.addEventListener("resize", onResize);
    var onPageHide = function () {
      S.leaving = true;
    };
    var onPageShow = function () {
      S.leaving = false; // вернулись из кэша страниц
    };
    root.addEventListener("pagehide", onPageHide);
    root.addEventListener("pageshow", onPageShow);
    if (i18n && typeof i18n.onChange === "function") unsubLang = i18n.onChange(onLang);

    render();
    var ready = (i18n && i18n.ready ? Promise.resolve(i18n.ready).catch(function () {}) : Promise.resolve()).then(function () {
      render();
      return boot();
    });

    // ───────────── Handle ─────────────
    var handle = {
      ready: ready,
      start: function (kind) {
        return start(kind, { keyboard: true });
      },
      cancel: cancel,
      select: select,
      flyToProposals: flyToProposals,
      setMode: setMode,
      // R01: update({mode, visible}) — то же, что setMode / setVisible.
      update: function (u) {
        u = u || {};
        if (u.mode || u.role) setMode(u.mode || u.role);
        if (typeof u.visible === "boolean") handle.setVisible(u.visible);
        if (typeof u.dock === "boolean" && u.dock !== o.dock) {
          o.dock = u.dock;
          render(true);
        }
        if (u.insets === true) applyInsets(); // хозяин передвинул свою панель — пересчитать свободную часть
        return handle;
      },
      refresh: function () {
        return store ? loadProposals() : ready;
      },
      setVisible: function (v) {
        S.visible = !!v;
        labelsLayer.hidden = !S.visible;
        if (layerAdded && map.getLayer(LAYER_ID)) map.setLayoutProperty(LAYER_ID, "visibility", S.visible ? "visible" : "none");
        if (!S.visible) cancel();
        render();
      },
      getState: function () {
        return {
          phase: S.phase,
          mode: S.mode,
          kind: S.kind,
          storeMode: S.storeMode,
          selected: S.selected,
          count: Object.keys(S.objects).length,
          ghost: S.ghost
            ? {
                pos: S.ghost.pos.slice(),
                rot: S.ghost.rot,
                follow: S.ghost.follow,
                valid: S.ghost.valid,
                a: S.ghost.a ? S.ghost.a.slice() : null,
                section: S.ghost.section
                  ? {
                      ok: S.ghost.section.ok,
                      length_m: S.ghost.section.length_m,
                      name: S.ghost.section.name,
                      name_kk: S.ghost.section.name_kk || null,
                      source: S.ghost.section.source || "local",
                      coords: S.ghost.section.coords,
                      edge_ids: S.ghost.section.edge_ids,
                    }
                  : null,
              }
            : null,
          hint: S.hint ? S.hint.key : null,
          proposals: Object.keys(S.objects).map(function (id) {
            return JSON.parse(JSON.stringify(S.objects[id].p));
          }),
          get items() {
            return this.proposals; // то же под именем items (так их ищет сценарий R11)
          },
          animating: anims.length > 0,
          memory: renderer ? { geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures, programs: renderer.info.programs ? renderer.info.programs.length : null } : null,
          origin: origin ? origin.slice() : null,
        };
      },
      // Для проверок точности (tests/civic/R05): экранная точка 3D-точки объекта (x, y, z в метрах модели).
      _project: function (id, point) {
        var obj = S.objects[id];
        if (!obj || !lastMatrix) return null;
        var wp = worldOf(obj, point || [0, 0, 0]);
        return projectLocal(wp.x, wp.y, wp.z);
      },
      destroy: function () {
        if (S.destroyed) return;
        if (S.mode === "placing") cancel();
        S.destroyed = true;
        map.off("mousemove", onMouseMove);
        map.off("click", onMapClick);
        map.off("move", onMapMove);
        map.off("styledata", onStyleData);
        doc.removeEventListener("keydown", onKey);
        doc.removeEventListener("birge:mode", onShellMode);
        root.removeEventListener("resize", onResize);
        root.removeEventListener("pagehide", onPageHide);
        root.removeEventListener("pageshow", onPageShow);
        if (fitObserver) fitObserver.disconnect();
        if (unsubLang) unsubLang();
        clearTimeout(toastTimer);
        Object.keys(S.objects).forEach(disposeObject);
        if (ghostGroup) disposeGroup(ghostGroup);
        anims = [];
        try {
          if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID);
        } catch (e) {
          /* карта уже удалена */
        }
        if (renderer) renderer.dispose();
        renderer = null;
        if (ui.parentNode) ui.parentNode.removeChild(ui);
        if (labelsLayer.parentNode) labelsLayer.parentNode.removeChild(labelsLayer);
      },
    };
    return handle;
  }

  root.CivicBuild3D = {
    mount: mount,
    STRINGS: STRINGS,
    // Перевод ключей модуля для страницы-хозяина (демо): словарь R11, если ключ уже там, иначе строки модуля.
    t: function (key, params) {
      return makeT(root.BirgeI18n || null)(key, params);
    },
    version: "r14-2",
  };
})(typeof self !== "undefined" ? self : this);
