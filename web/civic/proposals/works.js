/*
 * Birge · «Работы и отключения» — форма сотрудника для раздела жителя «Рядом» (R06 данные, волна 2 п. 4).
 * Акимат: «Ещё → Работы и отключения» (#works; SCREENS.works в birge.js R01 ищет window.BirgeWorks).
 *
 *   BirgeWorks.mount(root, {api: {v2}, titleTag}) → {destroy, setLang}
 * API: GET /works?district (список района с ревизиями), POST /works (новая), POST /works/{id} (правка целиком,
 * expected_revision), POST /works/{id}/remove. Названия служб — таблица служб R08 GET /akim/routing (только общие
 * названия: «Водоканал», «Теплосеть»; реальные организации не придумываем).
 *
 * Правила R11 (IA_WAVE2 §4) — и в форме, и на сервере: 4 строки «Зачем?» обязательны; у отключения — источник,
 * время начала и конца и «где». Задержки показываем: у работы — срок по плану и новый срок, если сдвинулся.
 * Тексты — на языке интерфейса; перевод — та же запись после переключения ҚАЗ / РУС.
 *
 * Раунд 15 — работа v2 (CONTRACT §5.6) для «Календаря работ» R12: служба (id таблицы служб), вид работ v2
 * (раскопка, асфальт, перекрытие, благоустройство, освещение, другое), дата начала и «Участок улицы»: сотрудник
 * отмечает на карте начало и конец, линию по форме OSM строит R12 (GET /street-segment) — здесь только предпросмотр,
 * на сервер уходят две точки, и сервер строит участок сам. Форма переживает переход на карту (pending ниже).
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var API = "/api/civic/v2";
  var DISTRICTS = ["almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"];
  var DISTRICT_KEY = "birge.works.district";
  var WORK_STATUS = { in_progress: "nearby.tab.now", done: "nearby.tab.done", planned: "nearby.tab.planned" };
  var WORK_KINDS = ["roadworks", "construction", "landscaping", "lighting", "event", "other"];
  var UTILITIES = ["water", "heating", "power", "gas", "road_closure"];
  var WHY = ["problem", "reason", "result", "inconvenience"];
  var ASTANA_MS = 5 * 3600 * 1000;
  // Плитка-иллюстрация записи — значок ui-kit по виду работ / что отключат (дизайн-марафон).
  var KIND_ICON = { roadworks: "road", construction: "building", landscaping: "trees", lighting: "bulb", event: "calendar", other: "dots" };
  var UTILITY_ICON = { water: "droplet", heating: "droplet", power: "bulb", gas: "alert", road_closure: "road" };
  // Работа v2: вид для календаря R12 и его значок; вид раунда 14 (подпись в «Рядом» R08) выводит сервер.
  var KINDS_V2 = ["dig", "surface", "closure", "landscape", "lighting", "other"];
  var KIND_V2_ICON = { dig: "droplet", surface: "road", closure: "alert", landscape: "trees", lighting: "bulb", other: "dots" };
  var WORK_KIND_TO_V2 = { roadworks: "surface", construction: "other", landscaping: "landscape", lighting: "lighting", event: "other", other: "other" };
  // Таблица служб R08 (GET /akim/routing) — запасные общие названия, если её нет в сборке (реальных организаций нет).
  var SERVICE_NAMES = {
    road: ["Дорожная служба", "Жол қызметі"], traffic: ["Служба светофоров и разметки", "Бағдаршам және жол таңбасы қызметі"],
    street_cleaning: ["Служба уборки улиц", "Көшелерді тазалау қызметі"], transport: ["Служба общественного транспорта", "Қоғамдық көлік қызметі"],
    lighting: ["Служба освещения", "Жарықтандыру қызметі"], landscaping: ["Служба благоустройства", "Абаттандыру қызметі"],
    greenery: ["Служба озеленения", "Көгалдандыру қызметі"], waste: ["Оператор вывоза мусора", "Қоқыс шығару операторы"],
    utilities: ["Служба ЖКХ", "ТКШ қызметі"], heating: ["Теплосеть", "Жылу желісі"], water: ["Водоканал", "Сумен жабдықтау қызметі"],
    power: ["Электросети", "Электр желілері"], gas: ["Газовая служба", "Газ қызметі"], housing: ["Управляющая компания дома", "Үйді басқарушы компания"],
    ecology: ["Служба экологии", "Экология қызметі"], emergency: ["Служба спасения", "Құтқару қызметі"], police: ["Полиция", "Полиция"],
    animals: ["Служба отлова животных", "Жануарларды аулау қызметі"], parking: ["Служба парковок", "Тұрақ қызметі"],
    akimat: ["Аппарат акима района", "Аудан әкімінің аппараты"],
  };
  // Служба по умолчанию для нового вида работ (сотрудник может выбрать другую).
  var KIND_V2_SERVICE = { dig: "water", surface: "road", closure: "road", landscape: "landscaping", lighting: "lighting", other: "akimat" };
  var SECTION_SOURCE = "rw-section";
  var SECTION_COLOR = "#2563EB"; // линия участка в предпросмотре — синяя, как выбор на карте (не цвет уровня жалоб)
  // Форма, открытая до перехода на карту (выбор участка): экран раздела при этом пересоздаётся.
  var pending = null;

  var KEYS = {
    ru: {
      "works.form.add": "Добавить запись",
      "works.form.new_title": "Новая запись для раздела «Рядом»",
      "works.form.edit_title": "Изменить запись",
      "works.form.type": "Что это",
      "works.form.type_work": "Работа",
      "works.form.type_outage": "Отключение или перекрытие",
      "works.form.status": "Стадия",
      "works.form.kind": "Вид работ",
      "works.form.utility": "Что отключат",
      "works.form.source": "Источник (служба)",
      "works.form.title": "Коротко: что происходит",
      "works.form.zone": "Где (улица, дома)",
      "works.form.detour": "Как обойти (по желанию)",
      "works.form.start": "Начало",
      "works.form.end": "Окончание",
      "works.form.planned_end": "Срок по плану",
      "works.form.forecast_end": "Новый срок, если сдвинулся (по желанию)",
      "works.form.why": "Зачем? — 4 строки, их увидят жители",
      "works.form.lang_hint": "Пишите на языке интерфейса. Перевод: переключите ҚАЗ / РУС и сохраните запись ещё раз.",
      "works.form.other_lang": "Текст записи пока только на другом языке — переведите поля или оставьте как есть.",
      "works.form.required": "Заполните это поле",
      "works.form.bad_time": "Окончание — позже начала и не дольше 14 дней",
      "works.form.bad_date": "Проверьте дату",
      "works.form.stale": "Запись уже изменил другой сотрудник — список обновлён",
      "works.form.remove": "Удалить",
      "works.form.remove_confirm": "Точно удалить",
      "works.form.removed": "Запись удалена",
      "works.form.empty": "В этом районе пока нет работ и отключений",
      "works.form.district": "Район",
      "works.form.until": "до {date}",
      "works.form.error": "Не получилось сохранить. Проверьте связь и повторите.",
      "staff.login.note": "Учётную запись выдаёт администратор.",
      // Раунд 15 — работа v2 (I18N_R15_R06.json для R11)
      "works.form.service": "Служба",
      "works.form.kind_v2": "Вид работ",
      "works.kind_v2.dig": "Раскопка: трубы и кабели",
      "works.kind_v2.surface": "Асфальт и покрытие",
      "works.kind_v2.closure": "Перекрытие улицы",
      "works.kind_v2.landscape": "Благоустройство",
      "works.kind_v2.lighting": "Освещение",
      "works.kind_v2.other": "Другое",
      "works.kind_v2_short.dig": "Раскопка",
      "works.kind_v2_short.surface": "Асфальт",
      "works.kind_v2_short.closure": "Перекрытие",
      "works.kind_v2_short.landscape": "Благоустройство",
      "works.kind_v2_short.lighting": "Освещение",
      "works.kind_v2_short.other": "Другое",
      "works.form.starts_on": "Начало работ",
      "works.form.section": "Участок улицы",
      "works.form.section_hint": "По участкам «Календарь работ» видит, где улицу хотят раскопать после нового асфальта.",
      "works.form.section_none": "Участок не выбран — запись будет без линии на карте",
      "works.form.section_pick": "Отметить на карте",
      "works.form.section_change": "Изменить участок",
      "works.form.section_clear": "Убрать участок",
      "works.form.section_start": "Нажмите на карте начало участка улицы",
      "works.form.section_end": "Теперь нажмите конец участка",
      "works.form.section_wait": "Строим участок по улице…",
      "works.form.section_ready": "{street} · {m} м. Нажмите «Готово» или выберите заново",
      "works.form.section_value": "{street} · {m} м",
      "works.form.section_unnamed": "Участок улицы",
      "works.form.section_failed": "Участок не построить: {text}",
      "works.form.section_unavailable": "Карта улиц сейчас недоступна — сохраните запись без участка.",
      "works.form.section_kept": "Участок сохранён (по карте улиц)",
      "works.form.bad_order": "Окончание — не раньше начала",
    },
    kk: {
      "works.form.add": "Жазба қосу",
      "works.form.new_title": "«Маңайда» бөліміне жаңа жазба",
      "works.form.edit_title": "Жазбаны өзгерту",
      "works.form.type": "Бұл не",
      "works.form.type_work": "Жұмыс",
      "works.form.type_outage": "Өшіру немесе жол жабу",
      "works.form.status": "Кезеңі",
      "works.form.kind": "Жұмыс түрі",
      "works.form.utility": "Не өшіріледі",
      "works.form.source": "Дереккөз (қызмет)",
      "works.form.title": "Қысқаша: не болып жатыр",
      "works.form.zone": "Қай жерде (көше, үйлер)",
      "works.form.detour": "Қалай айналып өтуге болады (қаласаңыз)",
      "works.form.start": "Басталуы",
      "works.form.end": "Аяқталуы",
      "works.form.planned_end": "Жоспар бойынша мерзімі",
      "works.form.forecast_end": "Мерзімі ауысса — жаңа мерзімі (қаласаңыз)",
      "works.form.why": "Не үшін? — 4 жол, оларды тұрғындар көреді",
      "works.form.lang_hint": "Интерфейс тілінде жазыңыз. Аударма: ҚАЗ / РУС ауыстырып, жазбаны қайта сақтаңыз.",
      "works.form.other_lang": "Жазба мәтіні әзірге басқа тілде ғана — өрістерді аударыңыз немесе солай қалдырыңыз.",
      "works.form.required": "Бұл өрісті толтырыңыз",
      "works.form.bad_time": "Аяқталуы басталуынан кейін және 14 күннен аспауы керек",
      "works.form.bad_date": "Күнін тексеріңіз",
      "works.form.stale": "Жазбаны басқа қызметкер өзгертті — тізім жаңартылды",
      "works.form.remove": "Жою",
      "works.form.remove_confirm": "Нақты жою",
      "works.form.removed": "Жазба жойылды",
      "works.form.empty": "Бұл ауданда әзірге жұмыс пен өшіру жоқ",
      "works.form.district": "Аудан",
      "works.form.until": "мерзімі: {date}",
      "works.form.error": "Сақтау мүмкін болмады. Байланысты тексеріп, қайталаңыз.",
      "staff.login.note": "Тіркелгіні әкімші береді.",
      "works.form.service": "Қызмет",
      "works.form.kind_v2": "Жұмыс түрі",
      "works.kind_v2.dig": "Қазу: құбырлар мен кабельдер",
      "works.kind_v2.surface": "Асфальт және жабын",
      "works.kind_v2.closure": "Көшені жабу",
      "works.kind_v2.landscape": "Абаттандыру",
      "works.kind_v2.lighting": "Жарықтандыру",
      "works.kind_v2.other": "Басқа",
      "works.kind_v2_short.dig": "Қазу",
      "works.kind_v2_short.surface": "Асфальт",
      "works.kind_v2_short.closure": "Жол жабу",
      "works.kind_v2_short.landscape": "Абаттандыру",
      "works.kind_v2_short.lighting": "Жарықтандыру",
      "works.kind_v2_short.other": "Басқа",
      "works.form.starts_on": "Жұмыстың басталуы",
      "works.form.section": "Көше учаскесі",
      "works.form.section_hint": "Учаскелер бойынша «Жұмыс күнтізбесі» жаңа асфальттан кейін көшені қайта қазу жоспарын көреді.",
      "works.form.section_none": "Учаске таңдалмаған — жазба картада сызықсыз болады",
      "works.form.section_pick": "Картадан белгілеу",
      "works.form.section_change": "Учаскені өзгерту",
      "works.form.section_clear": "Учаскені алып тастау",
      "works.form.section_start": "Картадан көше учаскесінің басын басыңыз",
      "works.form.section_end": "Енді учаскенің соңын басыңыз",
      "works.form.section_wait": "Көше бойынша учаске құрылып жатыр…",
      "works.form.section_ready": "{street} · {m} м. «Дайын» батырмасын басыңыз немесе қайта таңдаңыз",
      "works.form.section_value": "{street} · {m} м",
      "works.form.section_unnamed": "Көше учаскесі",
      "works.form.section_failed": "Учаске құрылмады: {text}",
      "works.form.section_unavailable": "Көше картасы қазір қолжетімсіз — жазбаны учаскесіз сақтаңыз.",
      "works.form.section_kept": "Учаске сақталды (көше картасы бойынша)",
      "works.form.bad_order": "Аяқталуы басталуынан ерте болмауы керек",
    },
  };

  function I() {
    return root.BirgeI18n || null;
  }
  function lang() {
    return I() && I().getLang() === "kk" ? "kk" : "ru";
  }
  function tr(key, params) {
    var i18n = I(), l = lang();
    if (i18n && i18n.has(key)) return i18n.t(key, params);
    var v = KEYS[l][key];
    if (v == null && i18n && i18n.has(key, "ru")) return i18n.t(key, params);
    if (v == null) v = KEYS.ru[key] != null ? KEYS.ru[key] : key;
    return String(v).replace(/\{(\w+)\}/g, function (w, n) { return params && params[n] != null ? String(params[n]) : w; });
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
  function icon(name) {
    var span = doc.createElement("span");
    span.innerHTML = root.BirgeUI ? root.BirgeUI.icon(name) : "";
    return span.firstChild || doc.createTextNode("");
  }
  function button(cls, label, ic, attrs) {
    return h("button", Object.assign({ type: "button", class: "bk-btn" + (cls ? " " + cls : "") }, attrs || {}),
      [ic ? icon(ic) : null, h("span", { text: label })]);
  }
  function toast(text, opts) {
    if (root.BirgeUI) root.BirgeUI.toast(text, opts);
  }
  function store(key, value) {
    try {
      if (value === undefined) return root.localStorage.getItem(key);
      root.localStorage.setItem(key, value);
    } catch (e) {
      return null;
    }
    return null;
  }
  function date(iso) {
    return I() && iso ? I().formatDate(iso) : iso || "";
  }
  // Время отключения хранится как время Астаны (+05:00); поле datetime-local — «2026-10-13T10:00» без пояса.
  function toLocalInput(iso) {
    if (!iso) return "";
    return new Date(new Date(iso).getTime() + ASTANA_MS).toISOString().slice(0, 16);
  }
  function kindLabel(item) {
    if (item.type === "outage") return tr("nearby.utility." + item.utility);
    // Строка записи — короткое слово («Раскопка»); полное «Раскопка: трубы и кабели» — в списке формы.
    if (item.kind && KINDS_V2.indexOf(item.kind) >= 0) return tr("works.kind_v2_short." + item.kind);
    if (item.work_kind === "lighting") return tr("proposal.kind.lighting");
    return tr("works.kind." + (item.work_kind || "other"));
  }
  // Карта приложения (web/map.js R01): та же, что у мастера идей (ideas.js mapObject).
  function mapObject() {
    try {
      // eslint-disable-next-line no-undef
      return typeof mapReady !== "undefined" && mapReady && typeof map !== "undefined" && map && typeof map.on === "function" ? map : null;
    } catch (e) {
      return null;
    }
  }
  function reducedMotion() {
    return root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }
  function sectionText(section) {
    if (!section) return tr("works.form.section_none");
    var street = (lang() === "kk" ? section.street_kk || section.street_ru : section.street_ru || section.street_kk) || tr("works.form.section_unnamed");
    var m = section.length_m != null ? Math.round(section.length_m) : null;
    return m != null ? tr("works.form.section_value", { street: street, m: I() ? I().formatNumber(m) : String(m) }) : street;
  }

  // ── выбор участка улицы на карте (работа v2) ──
  // Модуль, а не экран: при переходе на карту экран раздела уничтожается, выбор живёт дальше и возвращает форму.
  // Нажатие 1 — начало, нажатие 2 — конец: R12 строит участок по графу OSM (предпросмотр синей линией). Третье
  // нажатие начинает заново. Esc и «Отменить» — вернуться к форме без изменений.
  var sectionPicker = null;
  function pickSection(m, request, onDone) {
    if (sectionPicker) sectionPicker.finish(false);
    root.BirgeShell.setSection("map");
    var a = null, b = null, picked = null, markers = [], seq = 0;
    var done = button("bk-btn--primary", tr("common.action.done"), "check", { disabled: true, "data-key": "section-done" });
    var cancel = button("bk-btn--ghost", tr("common.action.cancel"), "close", { "data-key": "section-cancel" });
    var hint = h("p", { class: "ri-pick__hint", role: "status", "aria-live": "polite", text: tr("works.form.section_start") });
    // Та же плавающая полоса, что у выбора места идеи (ideas.css .ri-pick, стекло ui-kit).
    var bar = h("div", { class: "ri-pick rw-pick bk-app bk-glass", role: "dialog", "aria-label": tr("works.form.section") },
      [hint, h("div", { class: "bk-actions" }, [done, cancel])]);
    doc.body.appendChild(bar);
    doc.body.classList.add("ri-picking");
    m.getCanvas().style.cursor = "crosshair";
    function round6(v) { return Math.round(v * 1e6) / 1e6; }
    function marker(p) {
      if (!root.maplibregl || !root.maplibregl.Marker) return null;
      return new root.maplibregl.Marker({ color: SECTION_COLOR, scale: 0.8 }).setLngLat(p).addTo(m);
    }
    function clearMarkers() {
      markers.forEach(function (x) { if (x) x.remove(); });
      markers = [];
    }
    function clearLine() {
      try {
        if (m.getLayer(SECTION_SOURCE)) m.removeLayer(SECTION_SOURCE);
        if (m.getSource(SECTION_SOURCE)) m.removeSource(SECTION_SOURCE);
      } catch (e) { /* стиль карты перезагружается — линии уже нет */ }
    }
    function drawLine(geometry) {
      clearLine();
      if (!geometry) return;
      try {
        m.addSource(SECTION_SOURCE, { type: "geojson", data: { type: "Feature", geometry: geometry, properties: {} } });
        m.addLayer({ id: SECTION_SOURCE, type: "line", source: SECTION_SOURCE, layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": SECTION_COLOR, "line-width": 6, "line-opacity": 0.9 } });
      } catch (e) { /* без линии предпросмотра участок всё равно сохранится — его строит сервер */ }
    }
    function onClick(e) {
      var p = [round6(e.lngLat.lng), round6(e.lngLat.lat)];
      if (!a || b) {
        a = p;
        b = null;
        picked = null;
        seq += 1;
        clearLine();
        clearMarkers();
        markers.push(marker(a));
        done.disabled = true;
        hint.textContent = tr("works.form.section_end");
        if (m.getZoom() < 15) m.easeTo({ center: p, zoom: 16, duration: reducedMotion() ? 0 : 500 });
        return;
      }
      b = p;
      markers.push(marker(b));
      hint.textContent = tr("works.form.section_wait");
      var my = ++seq;
      request("GET", "/street-segment?from=" + a.join(",") + "&to=" + b.join(",") + "&kind=road").then(function (seg) {
        if (my !== seq || !sectionPicker) return;
        drawLine(seg && seg.geometry);
        picked = { from: a, to: b, street_ru: seg && seg.street_ru, street_kk: seg && seg.street_kk, length_m: seg && seg.length_m };
        var street = (lang() === "kk" ? picked.street_kk || picked.street_ru : picked.street_ru || picked.street_kk) || tr("works.form.section_unnamed");
        var meters = picked.length_m != null ? Math.round(picked.length_m) : 0;
        hint.textContent = tr("works.form.section_ready", { street: street, m: I() ? I().formatNumber(meters) : String(meters) });
        done.disabled = false;
        done.focus();
      }, function (err) {
        if (my !== seq || !sectionPicker) return;
        var e2 = err && err.error && typeof err.error === "object" ? err.error : null;
        hint.textContent = err && (err.status === 503 || err.status === 0) ? tr("works.form.section_unavailable")
          : tr("works.form.section_failed", { text: (e2 && e2.message) || (err && err.message) || "" });
        b = null;
        var last = markers.pop();
        if (last) last.remove();
      });
    }
    function finish(ok) {
      m.off("click", onClick);
      m.getCanvas().style.cursor = "";
      clearLine();
      clearMarkers();
      bar.remove();
      doc.body.classList.remove("ri-picking");
      doc.removeEventListener("keydown", onKey, true);
      sectionPicker = null;
      onDone(ok ? picked : null);
    }
    function onKey(e) {
      if (e.key === "Escape") finish(false);
    }
    m.on("click", onClick);
    doc.addEventListener("keydown", onKey, true);
    done.addEventListener("click", function () { if (picked) finish(true); });
    cancel.addEventListener("click", function () { finish(false); });
    sectionPicker = { finish: finish };
    setTimeout(function () { cancel.focus(); }, 0);
  }

  function makeRequest(opts) {
    var v2 = opts.api && typeof opts.api.v2 === "function" ? opts.api.v2 : null;
    // Чтение для сотрудника (GET /staff/ideas, GET /works): шлюз R01 для staff-маршрутов требует CSRF-токен и на GET
    // (R15 route policy), а клиент оболочки шлёт его только в изменяющих запросах — такие GET идут напрямую с токеном.
    var staffGet = function (method, path) { return method === "GET" && /^\/(staff\/|works(\?|$))/.test(path); };
    // Все запросы сотрудника (чтение очереди, решения по идеям, записи «Рядом») — напрямую с токеном: не зависят от того,
    // успела ли оболочка узнать сессию после перезагрузки страницы.
    var staffPath = function (path) { return /^\/(staff\/|works(\/|\?|$))/.test(path) || /^\/ideas\/[^/]+\/decide$/.test(path); };
    // Токен сотрудника: у оболочки (CivicShell) — когда она уже узнала сессию; иначе (экран открыт сразу после
    // перезагрузки) — из GET /api/civic/v1/session, как у карточек R06 (proposals.js).
    var token = null;
    function csrf(fresh) {
      var shellToken = root.CivicShell && root.CivicShell.csrfToken ? root.CivicShell.csrfToken() : null;
      if (shellToken && !fresh) return Promise.resolve(shellToken);
      if (token && !fresh) return Promise.resolve(token);
      return root.fetch("/api/civic/v1/session", { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (j) { var d = (j && j.data) || j || {}; token = d.authenticated ? d.csrf_token || null : null; return token; },
          function () { return null; });
    }
    function direct(method, path, body, retried) {
      return csrf(retried).then(function (tok) {
        var headers = { Accept: "application/json" };
        if (body !== undefined) headers["Content-Type"] = "application/json";
        if (tok && (method !== "GET" || staffGet(method, path))) headers["X-CSRF-Token"] = tok;
        return root.fetch((opts.apiBase || API) + path, { method: method, headers: headers, credentials: "same-origin",
          body: body !== undefined ? JSON.stringify(body) : undefined });
      }).then(function (res) {
        return res.json().catch(function () { return null; }).then(function (json) {
          if (res.ok && json && json.ok === true) return json.data; // конверт стенда R06
          if (res.ok) return json;
          var e = (json && json.error) || {};
          var err = new Error((typeof e === "object" ? e.message : json && json.message) || "HTTP " + res.status);
          err.status = res.status;
          err.code = typeof e === "string" ? e : e.code;
          err.fields = (typeof e === "object" && e.fields) || (json && json.fields) || {};
          throw err;
        });
      }, function () {
        var err = new Error("network");
        err.status = 0;
        err.code = "network";
        throw err;
      }).catch(function (err) {
        if (!retried && err.code === "csrf_failed") return direct(method, path, body, true); // токен устарел — один повтор
        throw err;
      });
    }
    return function (method, path, body) {
      if (v2 && !staffPath(path)) {
        return Promise.resolve().then(function () { return v2(method, path, body); }).catch(function (err) {
          err.code = err.code || err.error;
          throw err;
        });
      }
      return direct(method, path, body, false);
    };
  }

  function mount(rootEl, options) {
    var opts = Object.assign({ titleTag: "h2" }, options || {});
    var request = makeRequest(opts);
    var saved = store(DISTRICT_KEY);
    var state = { district: DISTRICTS.indexOf(saved) >= 0 ? saved : "nura", items: null, error: null, services: null,
      view: "list", form: null, errors: {}, busy: false, confirm: null };
    var alive = true;
    rootEl.classList.add("rw");
    if (pending) {
      // Вернулись с карты после выбора участка: та же форма, что была открыта.
      state.form = pending.form;
      state.district = pending.district || state.district;
      state.view = "form";
      pending = null;
    }

    function load() {
      state.items = null;
      state.error = null;
      render();
      request("GET", "/works?district=" + encodeURIComponent(state.district)).then(function (data) {
        if (!alive) return;
        state.items = data.items || [];
        render();
      }, function (err) {
        if (!alive) return;
        state.error = err;
        render();
      });
    }
    function loadServices() {
      request("GET", "/akim/routing").then(function (data) {
        state.services = (data && data.services) || null;
        if (alive && state.view === "form") render();
      }, function () { state.services = null; });
    }
    function serviceName(id) {
      var s = state.services && state.services[id];
      if (s) return s[lang()] || s.ru;
      var f = SERVICE_NAMES[id];
      return f ? f[lang() === "kk" ? 1 : 0] : id || "";
    }
    function serviceIds() {
      var ids = state.services ? Object.keys(state.services) : [];
      Object.keys(SERVICE_NAMES).forEach(function (k) { if (ids.indexOf(k) < 0) ids.push(k); });
      return ids;
    }

    function render() {
      if (!alive) return;
      var focusKey = doc.activeElement && rootEl.contains(doc.activeElement) ? doc.activeElement.getAttribute("data-key") : null;
      rootEl.replaceChildren(h(opts.titleTag, { class: "bk-h1", text: tr("shell.nav.works_staff") }));
      if (state.view === "form") renderForm();
      else renderList();
      if (focusKey) {
        var again = rootEl.querySelector('[data-key="' + focusKey + '"]');
        if (again) again.focus();
      }
    }

    function renderList() {
      var select = h("select", { id: "rw-district", "data-key": "district", onchange: function (e) {
        state.district = e.target.value;
        store(DISTRICT_KEY, state.district);
        load();
      } }, DISTRICTS.map(function (d) {
        return h("option", { value: d, selected: d === state.district, text: tr("district." + d) });
      }));
      var list = h("div", { class: "rw-list" });
      var noStaff = state.error && (state.error.status === 401 || state.error.status === 403);
      if (noStaff) {
        // Без входа — ни района, ни «Добавить запись»: одно состояние «войдите» (R11 INTEGRATION §9.3 b, §11.4) —
        // рисунок «пропуск» ui-kit, подсказка и одна главная «Войти».
        var ill = root.BirgeUI && typeof root.BirgeUI.illustration === "function";
        root.BirgeUI.state(list, "empty", { title: tr("proposal.need_staff"), text: tr("staff.login.note"), illustration: "staff",
          icon: ill ? null : "user", action: { label: tr("staff.login.submit"), onClick: function () {
            if (root.BirgeShell) root.BirgeShell.setSection("map");
            if (root.CivicShell && root.CivicShell.openEditor) root.CivicShell.openEditor();
          } } });
        rootEl.appendChild(list);
        return;
      }
      rootEl.appendChild(h("div", { class: "rw-head" }, [
        h("div", { class: "bk-field" }, [h("label", { class: "bk-field__label", for: "rw-district", text: tr("works.form.district") }), select]),
        button("bk-btn--primary", tr("works.form.add"), "plus", { "data-key": "add", onclick: function () { openForm(null); } }),
      ]));
      if (state.error) {
        root.BirgeUI.state(list, "error", { action: { onClick: load } });
      } else if (!state.items) {
        root.BirgeUI.state(list, "loading");
      } else if (!state.items.length) {
        root.BirgeUI.state(list, "empty", { title: tr("works.form.empty"), icon: "calendar" });
      } else {
        state.items.forEach(function (item) { list.appendChild(card(item)); });
        if (state.items.some(function (x) { return x.demo; })) list.appendChild(h("p", { class: "bk-footnote", text: tr("common.tag.demo_hint") }));
      }
      rootEl.appendChild(list);
    }

    // Строка записи (дизайн-марафон): плитка вида работ, тихая строка «вид · Пример», название, срок одной строкой.
    // Сдвинутый срок — «до / после»: плановый зачёркнут → новый, метка «срок перенесён». «Изменить» — капсула, «Удалить» — тихая.
    function tileOf(item) {
      var ic = item.type === "outage" ? UTILITY_ICON[item.utility] || "alert"
        : KIND_V2_ICON[item.kind] || KIND_ICON[item.work_kind] || "dots";
      return h("span", { class: "ri-tile", "aria-hidden": "true" }, [icon(ic)]);
    }
    function whenLine(item) {
      if (item.type === "outage") {
        return h("p", { class: "rw-when" }, [date(item.start) + " " + (I() ? I().formatTime(item.start) + "–" + I().formatTime(item.end) : "")]);
      }
      var shifted = item.forecast_end && item.planned_end && item.forecast_end > item.planned_end;
      if (!shifted) {
        return h("p", { class: "rw-when" }, [tr(WORK_STATUS[item.status]) + " · " + tr("works.form.until", { date: date(item.forecast_end || item.planned_end) })]);
      }
      return h("p", { class: "rw-when" }, [
        h("span", { text: tr(WORK_STATUS[item.status]) + " ·" }),
        h("s", { text: tr("works.form.until", { date: date(item.planned_end) }) }),
        h("span", { "aria-hidden": "true", text: "→" }),
        h("span", { class: "rw-when__new", text: date(item.forecast_end) }),
        // Задержка — словом в той же строке, без плашки (чистый стиль R11 §2.5, как в «Рядом» R08).
        h("span", { class: "rw-late", text: "· " + tr("works.shift_later") }),
      ]);
    }
    function card(item) {
      var l = lang();
      var title = item["title_" + l] || item.title_ru;
      var confirming = state.confirm === item.id;
      // «Пример» — одной строкой под списком, а не у каждой записи (R11 INTEGRATION §13 D-5).
      // Раунд 15: служба и улица участка — в той же тихой строке (кто копает и где), без новых плашек.
      var metaText = [kindLabel(item), item.service ? serviceName(item.service) : null,
        item.segments && item.segments.length ? sectionText({ street_ru: item.street_ru, street_kk: item.street_kk }) : null]
        .filter(Boolean).join(" · ");
      var meta = h("p", { class: "ri-meta" }, [h("span", { text: metaText })]);
      return h("article", { class: "bk-card rw-card", "data-work": item.id, "data-demo": item.demo ? "" : null }, [
        h("div", { class: "ri-app" }, [tileOf(item), h("div", { class: "ri-app__body" }, [meta,
          h("h3", { class: "bk-card__title rw-title", lang: item["title_" + l] ? l : "ru", text: title }), whenLine(item)])]),
        item.type === "outage" && item.zone_ru ? h("p", { class: "rw-where", text: tr("nearby.outage.zone", { text: item["zone_" + l] || item.zone_ru }) }) : null,
        h("div", { class: "rw-foot" }, [
          button(confirming ? "bk-btn--danger" : "bk-btn--ghost rw-remove", tr(confirming ? "works.form.remove_confirm" : "works.form.remove"), "trash",
            { "data-key": "remove-" + item.id, title: tr(confirming ? "works.form.remove_confirm" : "works.form.remove"), onclick: function () { remove(item); } }),
          button("rw-capsule", tr("works.form.edit_title"), "edit", { "data-key": "edit-" + item.id, onclick: function () { openForm(item); } }),
        ]),
      ]);
    }

    function remove(item) {
      if (state.confirm !== item.id) {
        state.confirm = item.id;
        render();
        return;
      }
      state.confirm = null;
      request("POST", "/works/" + encodeURIComponent(item.id) + "/remove", { expected_revision: item.revision }).then(function () {
        toast(tr("works.form.removed"));
        load();
      }, failed);
    }

    // ── форма ──
    function openForm(item) {
      var l = lang();
      var texts = (item && item.texts) || {};
      var other = l === "kk" ? "ru" : "kk";
      var has = function (f) { return texts[f + "_" + l] != null; };
      var pick = function (f) { return texts[f + "_" + l] != null ? texts[f + "_" + l] : texts[f + "_" + other] || ""; };
      state.form = {
        id: item ? item.id : null, revision: item ? item.revision : null,
        otherLang: !!item && !has("title") && texts["title_" + other] != null,
        type: item ? item.type : "work", status: item && item.status || "in_progress", work_kind: item && item.work_kind || "roadworks",
        utility: item && item.utility || "water", source: item && item.source || "water", district: item ? item.district : state.district,
        title: pick("title"), zone: pick("zone"), detour: pick("detour"),
        start: item && item.type === "outage" ? toLocalInput(item.start) : "", end: item && item.type === "outage" ? toLocalInput(item.end) : "",
        planned_end: item && item.planned_end || "", forecast_end: item && item.forecast_end || "",
        why: { problem: pick("why_problem"), reason: pick("why_reason"), result: pick("why_result"), inconvenience: pick("why_inconvenience") },
        // Работа v2: вид, служба, начало работ и участок улицы (segments хранит сервер; здесь — что показать и что прислать).
        kind: item && item.kind || (item && item.type === "work" ? WORK_KIND_TO_V2[item.work_kind] || "other" : "dig"),
        service: item && (item.service || item.source) || "water",
        starts_on: item && item.type === "work" && item.start ? String(item.start).slice(0, 10) : "",
        section: item && item.segments && item.segments.length ? { street_ru: item.street_ru, street_kk: item.street_kk,
          length_m: item.place && item.place.length_m, kept: true } : null,
        sectionChanged: false, kindTouched: false, originalKind: item ? item.kind : null, originalWorkKind: item ? item.work_kind : null,
      };
      state.errors = {};
      state.view = "form";
      if (!state.services) loadServices();
      render();
      var first = rootEl.querySelector("[data-key=type-work]");
      if (first) first.focus();
    }
    function input(name, labelKey, type, value, onInput, extra) {
      var id = "rw-" + name.replace(/\./g, "-");
      var err = state.errors[name];
      var el = type === "textarea" ? h("textarea", Object.assign({ id: id, rows: "2", maxlength: "200", "data-key": id }, extra || {}))
        : h("input", Object.assign({ id: id, type: type, "data-key": id }, extra || {}));
      el.value = value || "";
      if (err) {
        el.setAttribute("aria-invalid", "true");
        el.setAttribute("aria-describedby", id + "-err");
      }
      el.addEventListener("input", function () {
        onInput(el.value);
        // Поле исправляют — ошибка этого поля уходит сразу, без перерисовки формы.
        if (state.errors[name]) {
          delete state.errors[name];
          el.removeAttribute("aria-invalid");
          el.removeAttribute("aria-describedby");
          var box = el.parentNode, msg = box.querySelector(".bk-field__error");
          box.classList.remove("bk-field--error");
          if (msg) msg.remove();
        }
      });
      return h("div", { class: "bk-field" + (err ? " bk-field--error" : "") }, [
        h("label", { class: "bk-field__label", for: id, text: tr(labelKey) }), el,
        err ? h("p", { class: "bk-field__error", id: id + "-err", text: err }) : null]);
    }
    function select(name, labelKey, options, value, onChange) {
      var id = "rw-" + name;
      var el = h("select", { id: id, "data-key": id, onchange: function (e) { onChange(e.target.value); } },
        options.map(function (o) { return h("option", { value: o.value, selected: o.value === value, text: o.label }); }));
      return h("div", { class: "bk-field" + (state.errors[name] ? " bk-field--error" : "") }, [
        h("label", { class: "bk-field__label", for: id, text: tr(labelKey) }), el,
        state.errors[name] ? h("p", { class: "bk-field__error", text: state.errors[name] }) : null]);
    }
    function seg(name, legendKey, options, value, onChange) {
      var box = h("div", { class: "bk-seg", role: "radiogroup", "aria-label": tr(legendKey) });
      options.forEach(function (o) {
        box.appendChild(h("button", { type: "button", role: "radio", "aria-checked": String(value === o.value), "aria-pressed": String(value === o.value),
          "data-key": name + "-" + o.value, onclick: function () { onChange(o.value); render(); } }, [o.label]));
      });
      return h("fieldset", {}, [h("legend", { text: tr(legendKey) }), box]);
    }
    function renderForm() {
      var f = state.form;
      var form = h("form", { class: "bk-card rw-form", novalidate: true, onsubmit: function (e) { e.preventDefault(); save(); } });
      form.appendChild(h("h3", { class: "bk-h2", text: tr(f.id ? "works.form.edit_title" : "works.form.new_title") }));
      form.appendChild(h("p", { class: "bk-field__hint", text: tr(f.otherLang ? "works.form.other_lang" : "works.form.lang_hint") }));
      form.appendChild(seg("type", "works.form.type", [{ value: "work", label: tr("works.form.type_work") },
        { value: "outage", label: tr("works.form.type_outage") }], f.type, function (v) { f.type = v; }));
      form.appendChild(select("district", "works.form.district", DISTRICTS.map(function (d) { return { value: d, label: tr("district." + d) }; }),
        f.district, function (v) { f.district = v; }));
      form.appendChild(input("title", "works.form.title", "text", f.title, function (v) { f.title = v; }, { maxlength: "120", autocomplete: "off" }));
      var grid = h("div", { class: "rw-grid" });
      var services = serviceIds().map(function (sv) { return { value: sv, label: serviceName(sv) }; });
      if (f.type === "work") {
        form.appendChild(seg("status", "works.form.status", Object.keys(WORK_STATUS).map(function (s) { return { value: s, label: tr(WORK_STATUS[s]) }; }),
          f.status, function (v) { f.status = v; }));
        // Вид работ v2 (для календаря R12) и служба. Вид раунда 14 для «Рядом» выводит сервер из вида v2.
        grid.appendChild(select("kind", "works.form.kind_v2", KINDS_V2.map(function (k) {
          return { value: k, label: tr("works.kind_v2." + k) };
        }), f.kind, function (v) {
          // Служба по виду — только пока сотрудник её не выбрал сам (новая запись).
          if (!f.id && !f.serviceTouched) f.service = KIND_V2_SERVICE[v] || f.service;
          f.kind = v;
          f.kindTouched = true;
          render();
        }));
        grid.appendChild(select("service", "works.form.service", services, f.service, function (v) { f.service = v; f.serviceTouched = true; }));
        grid.appendChild(input("start", "works.form.starts_on", "date", f.starts_on, function (v) { f.starts_on = v; }));
        grid.appendChild(input("planned_end", "works.form.planned_end", "date", f.planned_end, function (v) { f.planned_end = v; }));
        grid.appendChild(input("forecast_end", "works.form.forecast_end", "date", f.forecast_end, function (v) { f.forecast_end = v; }));
      } else {
        grid.appendChild(select("utility", "works.form.utility", UTILITIES.map(function (u) { return { value: u, label: tr("nearby.utility." + u) }; }),
          f.utility, function (v) { f.utility = v; render(); }));
        // У отключения служба и есть источник (сервер принимает оба поля одним значением).
        grid.appendChild(select("service", "works.form.service", services, f.service, function (v) { f.service = v; f.source = v; }));
        grid.appendChild(input("start", "works.form.start", "datetime-local", f.start, function (v) { f.start = v; }));
        grid.appendChild(input("end", "works.form.end", "datetime-local", f.end, function (v) { f.end = v; }));
        grid.appendChild(input("zone", "works.form.zone", "text", f.zone, function (v) { f.zone = v; }, { maxlength: "200" }));
        grid.appendChild(input("detour", "works.form.detour", "text", f.detour, function (v) { f.detour = v; }, { maxlength: "200" }));
      }
      form.appendChild(grid);
      // Участок улицы: у работы и у перекрытия проезда (по нему R12 ищет конфликты «копаем дважды»).
      if (f.type === "work" || f.utility === "road_closure") form.appendChild(sectionField(f));
      var whyGrid = h("div", { class: "rw-why" });
      var why = h("fieldset", {}, [h("legend", { text: tr("works.form.why") }), whyGrid]);
      WHY.forEach(function (k) {
        whyGrid.appendChild(input("why." + k, "nearby.why." + k, "textarea", f.why[k], function (v) { f.why[k] = v; }));
      });
      form.appendChild(why);
      form.appendChild(h("div", { class: "bk-actions" }, [
        h("button", { type: "submit", class: "bk-btn bk-btn--primary", "data-key": "save" }, [icon("check"), h("span", { text: tr("common.action.save") })]),
        button("bk-btn--ghost", tr("common.action.cancel"), "close", { onclick: function () { state.view = "list"; render(); } }),
      ]));
      rootEl.appendChild(form);
    }

    function sectionField(f) {
      var err = state.errors.segment || state.errors.segments;
      var value = h("p", { class: "rw-section__value" + (f.section ? "" : " rw-section__value--none"), id: "rw-section-value",
        role: "status", text: sectionText(f.section) });
      var actions = h("div", { class: "rw-section__actions" }, [
        button(f.section ? "bk-btn--ghost" : "rw-capsule", tr(f.section ? "works.form.section_change" : "works.form.section_pick"), "pin",
          { "data-key": "section-pick", "aria-describedby": "rw-section-value", onclick: function () { startSection(); } }),
        f.section ? button("bk-btn--ghost rw-remove", tr("works.form.section_clear"), "close", { "data-key": "section-clear", onclick: function () {
          f.section = null;
          f.sectionChanged = true;
          delete state.errors.segment;
          delete state.errors.segments;
          render();
        } }) : null,
      ]);
      return h("fieldset", { class: "rw-section" + (err ? " bk-field--error" : "") }, [
        h("legend", { text: tr("works.form.section") }),
        h("p", { class: "bk-field__hint", text: tr("works.form.section_hint") }), value, actions,
        err ? h("p", { class: "bk-field__error", text: err }) : null]);
    }
    // Выбор участка на карте: экран уходит на карту (форма — в pending), два нажатия → предпросмотр R12 → «Готово».
    function startSection() {
      var m = mapObject();
      if (!m || !root.BirgeShell) {
        toast(tr("works.form.section_unavailable"), { type: "error" });
        return;
      }
      pending = { form: state.form, district: state.district };
      pickSection(m, request, function (picked) {
        var f = pending && pending.form;
        if (f && picked) {
          f.section = picked;
          f.sectionChanged = true;
        }
        if (root.BirgeShell) root.BirgeShell.setSection("works");
      });
    }

    function body() {
      var f = state.form;
      var b = { type: f.type, district: f.district, lang: lang(), title: f.title.trim(), why: {} };
      WHY.forEach(function (k) { b.why[k] = f.why[k].trim(); });
      if (f.type === "work") {
        b.status = f.status;
        b.kind = f.kind;
        b.service = f.service;
        // Вид раунда 14 (подпись в «Рядом»): прежний, пока вид v2 не меняли; иначе его выведет сервер.
        if (f.id && !f.kindTouched && f.originalWorkKind && WORK_KIND_TO_V2[f.originalWorkKind] === f.kind) b.work_kind = f.originalWorkKind;
        b.start = f.starts_on || null;
        b.planned_end = f.planned_end || null;
        b.forecast_end = f.forecast_end || null;
      } else {
        b.utility = f.utility;
        b.source = f.service;
        b.service = f.service;
        b.start = f.start || null;
        b.end = f.end || null;
        b.zone = f.zone.trim() || null;
        b.detour = f.detour.trim() || null;
      }
      // Участок: новые две точки — сервер построит участок сам; убрали — пустой список; не трогали — не шлём (останется).
      if (f.type === "work" || f.utility === "road_closure") {
        if (f.sectionChanged) {
          if (f.section && f.section.from && f.section.to) b.segment = { from: f.section.from, to: f.section.to };
          else if (!f.section) b.segments = [];
        }
      } else if (f.id && f.section) {
        b.segments = [];  // отключение воды/тепла — не участок улицы
      }
      if (f.id) b.expected_revision = f.revision;
      return b;
    }
    // Проверка в форме — те же правила, что на сервере (сервер всё равно проверит сам).
    function check(b) {
      var e = {}, req = tr("works.form.required");
      if (!b.title) e.title = req;
      WHY.forEach(function (k) { if (!b.why[k]) e["why." + k] = req; });
      if (b.type === "work" && !b.planned_end) e.planned_end = req;
      if (b.type === "work" && b.start && b.planned_end && b.planned_end < b.start) e.planned_end = tr("works.form.bad_order");
      if (b.type === "outage") {
        if (!b.zone) e.zone = req;
        if (!b.start) e.start = req;
        if (!b.end) e.end = req;
        if (b.start && b.end && (b.end <= b.start || (Date.parse(b.end) - Date.parse(b.start)) > 14 * 86400000)) e.end = tr("works.form.bad_time");
      }
      return e;
    }
    function save() {
      if (state.busy) return;
      var b = body();
      state.errors = check(b);
      if (Object.keys(state.errors).length) {
        render();
        var bad = rootEl.querySelector("[aria-invalid=true]");
        if (bad) bad.focus();
        return;
      }
      state.busy = true;
      var f = state.form;
      var call = f.id ? request("POST", "/works/" + encodeURIComponent(f.id), b) : request("POST", "/works", b);
      call.then(function () {
        state.busy = false;
        toast(tr("common.state.saved"));
        state.view = "list";
        if (b.district !== state.district) {
          state.district = b.district;
          store(DISTRICT_KEY, state.district);
        }
        load();
      }, function (err) {
        state.busy = false;
        if (err.status === 422 && err.fields) {
          state.errors = {};
          Object.keys(err.fields).forEach(function (k) {
            var name = k === "why" ? "why.problem" : k === "starts_on" ? "start" : k === "ends_on" ? "planned_end" : k;
            // Участок, служба, вид — текст сервера (он объясняет, что не так: «далеко от улицы», «нет пути»).
            if (name === "segment" || name === "segments" || name === "service" || name === "kind") state.errors[name] = String(err.fields[k]);
            else state.errors[name] = name === "end" ? tr("works.form.bad_time") : /end|date|start/.test(name) ? tr("works.form.bad_date") : tr("works.form.required");
          });
          render();
          var bad = rootEl.querySelector("[aria-invalid=true]");
          if (bad) bad.focus();
          return;
        }
        failed(err);
      });
    }
    function failed(err) {
      if (err.status === 409) {
        toast(tr("works.form.stale"), { type: "error" });
        state.view = "list";
        load();
        return;
      }
      toast(tr(err.status === 401 || err.code === "csrf_failed" ? "proposal.need_staff" : "works.form.error"), { type: "error" });
    }

    var offLang = I() && I().onChange ? I().onChange(function () { render(); }) : null;
    if (state.view === "form") loadServices();
    if (I() && I().ready) I().ready.then(load, load);
    else load();
    return {
      setLang: function () { render(); },
      destroy: function () {
        alive = false;
        if (typeof offLang === "function") offLang();
        rootEl.classList.remove("rw");
        rootEl.replaceChildren();
      },
    };
  }

  root.BirgeWorks = { mount: mount, version: "works-r15-v2", KEYS: KEYS };
})(typeof self !== "undefined" ? self : this);
