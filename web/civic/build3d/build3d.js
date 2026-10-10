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
 *
 * Handle: start(kind), cancel(), select(id), refresh(), setVisible(bool), getState(), destroy().
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
    },
    kk: {
      "build3d.loading": "3D жүктеліп жатыр…",
      "build3d.unsupported_title": "Көлемді көрініс қолжетімсіз",
      "build3d.unsupported_text": "Браузер 3D-ді қолдамайды. Картаны Chrome, Edge немесе Firefox-та ашыңыз.",
      "build3d.load_failed": "3D жүктелмеді. Байланысты тексеріп, қайталаңыз.",
      "build3d.hint.rotate": "Бұрып, «Орнату» түймесін басыңыз",
      "build3d.hint.touch": "Картаны жылжытыңыз немесе орынды түртіңіз. Содан кейін «Орнату» түймесін басыңыз",
      "build3d.hint.segment_start": "Көшені басыңыз — бөліктің басы",
      "build3d.hint.segment_end": "Енді бөліктің соңын таңдаңыз: {street}",
      "build3d.hint.segment_ready": "{street}, {length} м · {poles}. «Орнату» түймесін басыңыз",
      "build3d.poles": "{n} шам",
      "build3d.err.far_from_street": "Көшеге жақынырақ басыңыз",
      "build3d.err.other_street": "Соңын сол көшеден таңдаңыз: {street}",
      "build3d.err.too_short": "Бөлік тым қысқа. Нүктелерді бір-бірінен алысырақ таңдаңыз",
      "build3d.err.too_long": "Бөлік 900 м-ден ұзын. Нүктелерді жақынырақ таңдаңыз",
      "build3d.err.no_path": "Осы көше бойымен жол табылмады. Басқа нүктелерді таңдаңыз",
      "build3d.err.no_streets": "Жарықтандыруды әзірге тек Нұра ауданында ұсынуға болады",
      "build3d.err.outside_city": "Бұл жер Астанаға кірмейді. Қаладан орын таңдаңыз",
      "build3d.err.overlap": "Бұл жерде басқа жоба тұр. Нысанды жылжытыңыз",
      "build3d.placed": "Жоба орнатылды",
      "build3d.placed_local": "Жоба орнатылып, осы құрылғыда сақталды",
      "build3d.deleted": "Жоба жойылды",
      "build3d.save_failed": "Сақтау мүмкін болмады. Байланысты тексеріп, қайталаңыз",
      "build3d.vote_failed": "Дауыс жіберілмеді. Қайталап көріңіз",
      "build3d.card.near": "Жанында: {street}",
      "build3d.card.segment": "Бөлік: {street}, {length} м",
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
      "build3d.near.square_inside": "Бұл орын бұрыннан бар саябақ немесе гүлзардың ішінде",
      "build3d.near.lamps": "Бөлікте шамдар белгіленген: {n}",
      "build3d.near.source": "OpenStreetMap деректері бойынша",
      "build3d.card.yard": "Аула: {name}",
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
      "common.tag.demo_hint": "Пример для показа, не настоящее обращение",
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
      "common.tag.demo_hint": "Көрсетуге арналған үлгі, нақты өтініш емес",
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
  var LAYER_ID = "civic-build3d";
  var OUTLINE_COLOR = 0x176b4a; // пунктир границы проекта (бренд)
  var OUTLINE_SELECTED = 0x2f7fd6; // выбранный проект — цвет фокуса ui-kit

  // ───────────── mount ─────────────

  function mount(opts) {
    opts = opts || {};
    var map = opts.map;
    if (!map || typeof map.addLayer !== "function") throw new Error("CivicBuild3D.mount: нужна карта MapLibre (opts.map)");
    if (!Core || !ModelsLib) throw new Error("CivicBuild3D: подключите build3d-core.js и build3d-models.js раньше build3d.js");

    var o = {
      role: opts.role === "resident" ? "resident" : "akimat",
      apiPrefix: opts.apiPrefix || "/api/civic/v2",
      threeUrl: opts.threeUrl || "/vendor/three/three.module.min.js",
      dataUrl: (opts.dataUrl || "/civic/build3d/data/").replace(/\/?$/, "/"),
      iconsUrl: opts.iconsUrl || "/civic/ui-kit/icons.svg",
      year: opts.year || 2027,
      buildMs: opts.buildMs > 0 ? opts.buildMs : BUILD_MS,
      autoZoom: opts.autoZoom !== false,
      renderCard: opts.renderCard !== false,
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

    // ── DOM: корень, нижняя панель, тосты, подписи ──
    var hostRoot = opts.root || map.getContainer();
    var ui = el("div", "b3d bk-app" + (opts.root ? "" : " b3d--overlay"), { "data-b3d-role": o.role });
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
        S.phase, S.mode, S.kind, S.hint, S.visible, S.storeMode, S.cardBusy, t.lang(), Object.keys(S.objects).length,
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
      renderDock();
      labelsLayer.classList.toggle("b3d-labels--passive", S.mode === "placing");
      if (focusSel) {
        var again = dock.querySelector(focusSel);
        if (again) again.focus({ preventScroll: true });
      }
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
      if (o.role === "akimat") return renderCatalog();
      dock.setAttribute("data-state", "empty");
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

    function renderCard(p) {
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
      tags.appendChild(el("span", "bk-tag bk-tag--project", { text: t("proposal.label", { year: String(p.year) }) }));
      if (p.demo) tags.appendChild(el("span", "bk-tag bk-tag--demo", { text: t("common.tag.demo"), title: t("common.tag.demo_hint") }));
      tags.appendChild(el("span", "bk-meta", { text: t("proposal.status.proposal") }));
      card.appendChild(tags);
      var where = placeText(p);
      if (where) card.appendChild(el("p", "bk-meta b3d-pcard__where", { text: where }));
      if (p.target && p.target.kind === "area" && (p.target.label_ru || p.target.label_kk)) {
        var yardName = t.lang() === "kk" ? p.target.label_kk || p.target.label_ru : p.target.label_ru || p.target.label_kk;
        card.appendChild(el("p", "bk-meta b3d-pcard__yard", { text: t("build3d.card.yard", { name: yardName }) }));
      }
      var votes = el("div", "b3d-votes", { role: "group", "aria-label": t("proposal.one_vote") });
      votes.appendChild(voteBtn(p, 1));
      votes.appendChild(voteBtn(p, -1));
      card.appendChild(votes);
      var note = p.my_vote === 1 ? t("build3d.card.your_vote_up") : p.my_vote === -1 ? t("build3d.card.your_vote_down") : t("proposal.one_vote");
      card.appendChild(el("p", "bk-meta", { text: note }));
      if (o.role === "akimat") {
        var del = actionBtn("close", t("proposal.delete"), "bk-btn--danger", function () {
          removeProposal(p.id);
        }, "delete");
        if (S.cardBusy === "delete") del.setAttribute("aria-busy", "true");
        if (S.objects[p.id] && S.objects[p.id].pending) del.setAttribute("aria-disabled", "true");
        card.appendChild(del);
      }
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
      b.addEventListener("click", function () {
        vote(p.id, value);
      });
      return b;
    }

    function formatNum(n) {
      return i18n && i18n.formatNumber ? i18n.formatNumber(n) : formatNumberLocal(n);
    }

    function placeText(p) {
      if (p.kind === "lighting" && p.target && p.target.label_ru) {
        var len = Core.polylineLength(p.geometry.coordinates.map(function (c) {
          return Core.toLocal(p.geometry.coordinates[0], c);
        }));
        return t("build3d.card.segment", { street: p.target.label_ru, length: Math.round(len) });
      }
      return p.near_street ? t("build3d.card.near", { street: p.near_street }) : "";
    }

    // ── Тосты: что случилось + действие (Отменить / Повторить), 6 с ──
    function toast(text, opts2) {
      opts2 = opts2 || {};
      toasts.textContent = "";
      clearTimeout(toastTimer);
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
      var cfg = { prefix: o.apiPrefix, storage: o.storage, fixture: fixture };
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
      return store.list(currentBbox()).then(
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
          console.error("[build3d] предложения не загрузились", err);
          S.phase = "ready";
          render();
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
      return { poles: Core.sampleAlong(line, Core.LIGHT_STEP_M), line: line, offset: Core.LIGHT_OFFSET_M };
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
      var b = el("button", "b3d-label bk-tag bk-tag--project", { type: "button", "data-id": obj.p.id });
      b.addEventListener("click", function (ev) {
        ev.stopPropagation();
        if (S.mode === "placing") return;
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
      b.textContent = t("proposal.label", { year: String(obj.p.year) });
      obj.labelSize = null; // текст сменился — размер измерим заново (один раз, не в каждом кадре)
      b.setAttribute("aria-label", t("build3d.card.open", { kind: name, year: String(obj.p.year) }));
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
            disposeObject(id);
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
        lab.classList.remove("b3d-label--dot");
        it.obj.labelSize = { w: lab.offsetWidth || 110, h: lab.offsetHeight || 26 };
      });
      // Ближние к зрителю (ниже на экране) — первыми; они и остаются полными подписями.
      items.sort(function (a, b) {
        return b.sp.y - a.sp.y;
      });
      var placed = [];
      items.forEach(function (it) {
        var lab = it.obj.label;
        var compact = zoom < 14;
        var hiddenNow = lab.classList.contains("b3d-label--hidden"); // строится/удаляется — места не занимает
        var lw = compact ? 18 : it.obj.labelSize.w,
          lh = compact ? 18 : it.obj.labelSize.h;
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
        lab.style.transform = "translate(" + Math.round(it.sp.x) + "px," + Math.round(it.sp.y) + "px) translate(-50%,-100%)";
        lab.style.zIndex = String(1000 + Math.round(it.sp.y));
      });
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
        setHint(streets ? "build3d.hint.segment_start" : "build3d.err.no_streets", null, !streets);
      } else setHint(touch ? "build3d.hint.touch" : "proposal.place_hint");
      setTool(true);
      ensureExisting();
      if (o.autoZoom && map.getZoom() < 15.5) {
        map.easeTo({ zoom: 16.2, duration: reducedMotion() ? 0 : 700 });
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
          target: { kind: "segment", id: g.section.edge_ids[0], ids: g.section.edge_ids, label_ru: g.section.name, label_kk: g.section.name },
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

    function onMouseMove(e) {
      if (S.mode !== "placing" || !S.ghost) return;
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

    function clickLighting(ll) {
      var g = S.ghost;
      if (!streets) {
        setHint("build3d.err.no_streets", null, true);
        return render();
      }
      if (!g.a || (g.section && g.section.ok && g.b)) {
        var snap = streets.nearest(ll, Core.SNAP_STREET_M);
        g.section = null;
        g.preview = null;
        g.b = null;
        if (!snap) {
          g.a = null;
          setHint(inStreetArea(ll) ? "build3d.err.far_from_street" : "build3d.err.no_streets", null, true);
        } else {
          g.a = snap.lngLat;
          g.aStreet = snap.edge.name;
          g.dirHint = [Math.sin(snap.bearing * DEG), Math.cos(snap.bearing * DEG)];
          setHint("build3d.hint.segment_end", { street: snap.edge.name });
        }
      } else {
        var sec = streets.section(g.a, ll);
        if (sec.ok) {
          g.section = sec;
          g.b = ll;
          var n = Core.sampleAlong(lightingOpts(sec.coords).line, Core.LIGHT_STEP_M).length;
          setHint("build3d.hint.segment_ready", { street: sec.name, length: Math.round(sec.length_m), poles: t("build3d.poles", { n: n }) });
        } else {
          g.section = null;
          setHint("build3d.err." + sec.reason, { street: sec.name || g.aStreet }, true);
        }
      }
      updateGhost(true);
      render();
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
          console.error("[build3d] не сохранилось", err);
          animateRemove(tempId);
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
        function () {
          S.cardBusy = null;
          render();
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
        function () {
          S.cardBusy = null;
          render();
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
      if (id) focusDock("[data-action=vote-up]");
      repaint();
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
        setHint("build3d.hint.segment_ready", { street: sec.name, length: Math.round(sec.length_m), poles: t("build3d.poles", { n: n }) });
      }
      render(true);
      repaint();
    }

    // ───────────── Подписки ─────────────
    map.on("mousemove", onMouseMove);
    map.on("click", onMapClick);
    map.on("move", onMapMove);
    map.on("styledata", onStyleData);
    doc.addEventListener("keydown", onKey);
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
                  ? { ok: S.ghost.section.ok, length_m: S.ghost.section.length_m, name: S.ghost.section.name, coords: S.ghost.section.coords, edge_ids: S.ghost.section.edge_ids }
                  : null,
              }
            : null,
          hint: S.hint ? S.hint.key : null,
          proposals: Object.keys(S.objects).map(function (id) {
            return JSON.parse(JSON.stringify(S.objects[id].p));
          }),
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

  root.CivicBuild3D = { mount: mount, STRINGS: STRINGS, version: "r14-1" };
})(typeof self !== "undefined" ? self : this);
