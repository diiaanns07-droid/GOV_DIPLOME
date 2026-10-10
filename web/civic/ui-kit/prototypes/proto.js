/*
 * Birge · макеты R11 — общий код трёх кликабельных макетов (карта акимата, мастер жалобы, «Картина дня»).
 * Это ОБРАЗЕЦ вида и поведения для R07, R08, R09, а не рабочий модуль: данных из API нет, всё — примеры (demo).
 *
 * Карта — SVG по настоящим осям улиц OSM (proto-streets.js, генератор tests/civic/R11/tools/make_proto_streets.py):
 * работает без тайлов и WebGL, линии участков собраны из рёбер графа и идут строго по форме улицы.
 * Цвета, размеры, тексты — только токены ui-kit и ключи i18n (ru/kk).
 */
(function (root) {
  "use strict";
  var I = root.BirgeI18n;
  var UI = root.BirgeUI;
  var S = root.BirgeProtoStreets;
  var t = function (k, p) { return I.t(k, p); };
  var SVGNS = "http://www.w3.org/2000/svg";

  // ── Уровни тепловой карты: из categories_v2.json (heat_levels.min_weight) ──
  var LEVELS = [{ min: 10, level: 4 }, { min: 6, level: 3 }, { min: 3, level: 2 }, { min: 1, level: 1 }];
  function levelOf(weight) {
    for (var i = 0; i < LEVELS.length; i++) if (weight >= LEVELS[i].min) return LEVELS[i].level;
    return 0;
  }
  // Цвет слоя на карте — CSS-переменные tokens.css (карта), значок — *-badge (текст с контрастом ≥ 4.5).
  var HEAT_VAR = { 1: "--heat-1", 2: "--heat-2", 3: "--heat-3", 4: "--heat-4", fixed: "--fixed" };
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // ── Демо-данные (demo: true). Геометрия — из proto-streets.js; дворы — схематичные области в кварталах. ──
  // counts — сколько людей сообщили за 7/30/90 дней; spark — по дням за 14 дней (старые → новые).
  function demoTargets() {
    var P = S.points, G = S.segments;
    return [
      { id: "t-stop-sauran", kind: "object", type: "stop", category: "transport", district: "nura", status: "in_progress",
        name: { ru: "Сауран", kk: "Сауран" }, where: { ru: "ул. Орынбор", kk: "Орынбор көшесі" },
        geom: { point: P.stop_orynbor.xy }, counts: { 7: 7, 30: 12, 90: 15 }, spark: [0, 0, 1, 0, 1, 0, 1, 1, 0, 2, 1, 2, 1, 2],
        groups: [{ ru: "Павильон сломан, нет крыши, зимой стоять негде", kk: "Павильон сынған, шатыры жоқ, қыста тұратын жер жоқ", n: 8 },
                 { ru: "Нет расписания автобусов", kk: "Автобус кестесі жоқ", n: 4 }],
        works: { stage: 2, late: 23, stale: 0 } },
      { id: "t-seg-kabanbay", kind: "segment", type: "segment", category: "snow_ice", district: "nura", status: "new",
        name: { ru: "пр. Кабанбай батыра", kk: "Қабанбай батыр даңғылы" },
        between: { ru: "ул. Бухар жырау – ул. Орынбор", kk: "Бұқар жырау көшесі – Орынбор көшесі" },
        geom: { d: G.kabanbay.d, length_m: G.kabanbay.length_m }, counts: { 7: 6, 30: 9, 90: 9 }, spark: [0, 0, 0, 0, 0, 0, 0, 1, 1, 2, 1, 1, 2, 1],
        groups: [{ ru: "Тротуар и проезжая часть не очищены от снега", kk: "Тротуар мен жол қардан тазаланбаған", n: 6 },
                 { ru: "Гололёд у перехода", kk: "Өткел жанында көктайғақ", n: 3 }] },
      { id: "t-seg-orynbor", kind: "segment", type: "segment", category: "roads", district: "nura", status: "accepted",
        name: { ru: "ул. Орынбор", kk: "Орынбор көшесі" }, between: { ru: "пр. Туран – пр. Кабанбай батыра", kk: "Тұран даңғылы – Қабанбай батыр даңғылы" },
        geom: { d: G.orynbor.d, length_m: G.orynbor.length_m }, counts: { 7: 2, 30: 4, 90: 7 }, spark: [0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1],
        groups: [{ ru: "Глубокая яма на правой полосе", kk: "Оң жақ жолақта терең шұңқыр", n: 4 }] },
      { id: "t-seg-bukhar", kind: "segment", type: "segment", category: "lighting", district: "nura", status: "new",
        name: { ru: "ул. Бухар жырау", kk: "Бұқар жырау көшесі" }, between: { ru: "у парка", kk: "саябақ жанында" },
        geom: { d: G.bukhar.d, length_m: G.bukhar.length_m }, counts: { 7: 1, 30: 2, 90: 2 }, spark: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1],
        groups: [{ ru: "Не горят фонари вдоль парка", kk: "Саябақ бойындағы шамдар жанбайды", n: 2 }] },
      { id: "t-yard-orynbor", kind: "area", type: "yard", category: "yards", district: "nura", status: "new",
        name: { ru: "ул. Орынбор, 21", kk: "Орынбор көшесі, 21" },
        geom: { poly: [[150, 255], [262, 270], [254, 338], [142, 322]] }, counts: { 7: 4, 30: 6, 90: 8 }, spark: [0, 0, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0, 1, 1],
        groups: [{ ru: "Сломаны качели на детской площадке", kk: "Балалар алаңындағы әткеншек сынған", n: 6 }] },
      { id: "t-yard-sauran", kind: "area", type: "yard", category: "waste", district: "nura", status: "new",
        name: { ru: "ул. Сауран, 7", kk: "Сауран көшесі, 7" },
        geom: { poly: [[780, 190], [880, 205], [872, 280], [770, 266]] }, counts: { 7: 2, 30: 3, 90: 5 }, spark: [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1],
        groups: [{ ru: "Баки переполнены, мусор не вывозят третий день", kk: "Контейнерлер толып кетті, қоқыс үш күннен бері шығарылмайды", n: 3 }] },
      { id: "t-stop-kabanbay", kind: "object", type: "stop", category: "transport", district: "nura", status: "fixed", fixedDaysAgo: 2,
        name: { ru: "Орынбор", kk: "Орынбор" }, where: { ru: "пр. Кабанбай батыра", kk: "Қабанбай батыр даңғылы" },
        geom: { point: P.stop_kabanbay.xy }, counts: { 7: 0, 30: 5, 90: 6 }, spark: [1, 1, 2, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        groups: [{ ru: "Разбито стекло павильона", kk: "Павильон әйнегі сынған", n: 5 }] },
      { id: "t-stop-bukhar", kind: "object", type: "stop", category: "snow_ice", district: "nura", status: "new",
        name: { ru: "Бухар жырау", kk: "Бұқар жырау" }, where: { ru: "ул. Бухар жырау", kk: "Бұқар жырау көшесі" },
        geom: { point: P.stop_bukhar.xy }, counts: { 7: 3, 30: 3, 90: 3 }, spark: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1],
        groups: [{ ru: "Наледь на посадочной площадке", kk: "Отырғызу алаңында мұз қатқан", n: 3 }] },
    ].map(function (x) { x.demo = true; return x; });
  }

  // ── Подписи целей (ключи target.kind.*) ──
  function label(x) {
    var l = I.getLang();
    if (x.type === "stop") return t("target.kind.stop", { name: x.name[l] });
    if (x.type === "segment") return t("target.kind.segment", { street: x.name[l], from: x.between[l].split(" – ")[0], to: x.between[l].split(" – ")[1] || "" }).replace(/ \( – \)$/, "");
    if (x.type === "yard") return t("target.kind.yard", { address: x.name[l] });
    return x.name[l];
  }
  function shortLabel(x) {
    var l = I.getLang();
    if (x.type === "segment") return t("target.kind.segment_short", { street: x.name[l] });
    return label(x);
  }
  function typeLabel(x) {
    return t("target.type." + x.type);
  }

  // ── SVG-карта ──
  function el(tag, attrs, parent) {
    var n = document.createElementNS(SVGNS, tag);
    for (var k in attrs) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }

  /*
   * createMap(container, {onSelect(target), onPick({x, y}), soft})
   * → {render(targets, opts), select(id), flash(id), highlight(geom|null), setPickMode(bool), destroy()}
   * Масштаб — viewBox (кнопки +/− и колесо), перетаскивание — мышь/палец. Карта не двигается сама,
   * пока пользователь её трогает (UX_BRIEF, правило 8).
   */
  function createMap(container, opts) {
    opts = opts || {};
    var W = S.size[0], H = S.size[1];
    var view = { x: 0, y: 0, w: W, h: H };
    var svg = el("svg", { "class": "pm-svg", role: "img", "aria-label": t("common.map.label"), preserveAspectRatio: "xMidYMid meet" });
    container.appendChild(svg);
    var defs = el("defs", {}, svg);
    el("rect", { x: -W, y: -H, width: W * 3, height: H * 3, "class": "pm-bg" }, svg);
    el("path", { d: S.paths, "class": "pm-path" }, svg);
    var gStreets = el("g", {}, svg);
    S.streets.forEach(function (st) { el("path", { d: st.d, "class": "pm-street-casing" }, gStreets); });
    S.streets.forEach(function (st) { el("path", { d: st.d, "class": "pm-street" }, gStreets); });
    // Порядок слоёв: дворы → участки → подписи улиц → объекты → выбор жителя (кольцо поверх значка, чтобы было видно)
    var gArea = el("g", {}, svg), gSeg = el("g", {}, svg), gLabels = el("g", {}, svg), gObj = el("g", {}, svg), gSel = el("g", { "class": "pm-sel" }, svg);
    // Подписи улиц по линии (как в 2ГИС): только длинные улицы, чтобы не налезали друг на друга.
    S.streets.forEach(function (st, i) {
      if (st.label_len < 260) return;
      el("path", { id: "pm-lbl-" + i, d: st.label_d, fill: "none", stroke: "none" }, defs);
      var tx = el("text", { "class": "pm-street-label", dy: "-6" }, gLabels);
      var tp = el("textPath", { href: "#pm-lbl-" + i, startOffset: "50%", "text-anchor": "middle" }, tx);
      tp.textContent = st.name.replace(/^улица /, "ул. ").replace(/^проспект /, "пр. ");
    });
    var targets = [], selected = null, picking = false;

    function applyView() {
      svg.setAttribute("viewBox", view.x + " " + view.y + " " + view.w + " " + view.h);
      var z = W / view.w; // 1 — весь фрагмент; больше — ближе
      svg.setAttribute("data-zoom", z >= 1.7 ? "near" : "mid");
      // единиц SVG на 1 пиксель экрана (preserveAspectRatio meet): значки и подписи — постоянного экранного размера
      var cw = container.clientWidth || 1, ch = container.clientHeight || 1;
      svg.style.setProperty("--pm-k", String(1 / Math.min(cw / view.w, ch / view.h)));
    }
    function zoom(f, cx, cy) {
      var nw = Math.min(W * 1.2, Math.max(W / 4, view.w / f));
      var k = nw / view.w;
      cx = cx == null ? view.x + view.w / 2 : cx;
      cy = cy == null ? view.y + view.h / 2 : cy;
      view = { x: cx - (cx - view.x) * k, y: cy - (cy - view.y) * k, w: nw, h: view.h * k };
      applyView();
    }
    function toSvg(evt) {
      var r = svg.getBoundingClientRect();
      var pt = svg.createSVGPoint();
      pt.x = evt.clientX; pt.y = evt.clientY;
      var m = svg.getScreenCTM();
      var p = m ? pt.matrixTransform(m.inverse()) : { x: 0, y: 0 };
      return { x: p.x, y: p.y, sx: evt.clientX - r.left, sy: evt.clientY - r.top };
    }
    // Перетаскивание: отличаем от клика порогом 5 px
    var drag = null;
    svg.addEventListener("pointerdown", function (e) {
      drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false };
      svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener("pointermove", function (e) {
      if (!drag) return;
      var dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 5) drag.moved = true;
      if (!drag.moved) return;
      var k = 1 / Math.min(svg.clientWidth / view.w, svg.clientHeight / view.h);
      view.x = drag.vx - dx * k; view.y = drag.vy - dy * k;
      applyView();
    });
    svg.addEventListener("pointerup", function (e) {
      var d = drag; drag = null;
      if (!d || d.moved) return;
      var p = toSvg(e);
      // С захватом указателя событие приходит на svg — цель ищем по точке на экране.
      var under = document.elementFromPoint(e.clientX, e.clientY);
      var hit = under && under.closest && under.closest("[data-id]");
      if (picking) { if (opts.onPick) opts.onPick(p); return; }
      if (hit && opts.onSelect) opts.onSelect(hit.getAttribute("data-id"));
      else if (opts.onSelect) opts.onSelect(null);
    });
    // Клавиатура: Tab до цели, Enter/пробел — открыть карточку
    svg.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var hit = e.target.closest && e.target.closest("[data-id]");
      if (hit && opts.onSelect) { e.preventDefault(); opts.onSelect(hit.getAttribute("data-id")); }
    });
    svg.addEventListener("wheel", function (e) {
      e.preventDefault();
      var p = toSvg(e);
      zoom(e.deltaY < 0 ? 1.25 : 0.8, p.x, p.y);
    }, { passive: false });

    function colorFor(x) {
      return x.level === "fixed" ? cssVar(HEAT_VAR.fixed) : cssVar(HEAT_VAR[x.level] || "--c-line-strong");
    }

    function render(list) {
      targets = list;
      [gArea, gSeg, gObj].forEach(function (g) { while (g.firstChild) g.removeChild(g.firstChild); });
      list.forEach(function (x) {
        var c = colorFor(x);
        var lvl = x.level === "fixed" ? 2 : x.level || 0;
        if (x.kind === "area") {
          var pts = x.geom.poly.map(function (p) { return p.join(","); }).join(" ");
          var a = el("polygon", { points: pts, "class": "pm-area", "data-id": x.id, tabindex: "0", role: "button", "aria-label": label(x) }, gArea);
          a.style.fill = c; a.style.stroke = c;
          var cx = x.geom.poly.reduce(function (s, p) { return s + p[0]; }, 0) / x.geom.poly.length;
          var cy = x.geom.poly.reduce(function (s, p) { return s + p[1]; }, 0) / x.geom.poly.length;
          badge(x, cx, cy);
        } else if (x.kind === "segment") {
          var g = el("g", { "data-id": x.id, "class": "pm-seg", tabindex: "0", role: "button", "aria-label": label(x) }, gSeg);
          el("path", { d: x.geom.d, "class": "pm-seg-hit" }, g);
          el("path", { d: x.geom.d, "class": "pm-seg-casing", style: "--w:" + (4 + lvl * 2) }, g);
          var line = el("path", { d: x.geom.d, "class": "pm-seg-line", style: "--w:" + (4 + lvl * 2) }, g);
          line.style.stroke = c;
          var mid = midOf(x.geom.d);
          badge(x, mid[0], mid[1]);
        } else {
          var o = el("g", { "data-id": x.id, "class": "pm-obj", tabindex: "0", role: "button", "aria-label": label(x) }, gObj);
          var halo = el("circle", { cx: x.geom.point[0], cy: x.geom.point[1], "class": "pm-halo", style: "--r:" + (10 + Math.min(x.count, 14) * 1.2) }, o);
          halo.style.fill = c;
          badge(x, x.geom.point[0], x.geom.point[1], o);
          var name = el("text", { x: x.geom.point[0] + 16, y: x.geom.point[1] + 4, "class": "pm-obj-label" }, o);
          name.textContent = x.name[I.getLang()];
        }
      });
      markSelected();
    }

    // Значок: цвет уровня + число людей (+ ✓ у исправленного). Размер — в пикселях экрана (через --pm-k).
    function badge(x, cx, cy, parent) {
      var g = el("g", { "class": "pm-badge", "data-id": x.id, "data-level": x.level, transform: "translate(" + cx + " " + cy + ")" }, parent || gObj);
      el("circle", { r: 14, "class": "pm-badge-bg" }, g);
      var tx = el("text", { "class": "pm-badge-text", dy: "0.35em" }, g);
      tx.textContent = (x.level === "fixed" ? "✓" : "") + (x.count || (x.level === "fixed" ? "" : "0"));
      return g;
    }
    // Середина участка — по первой ломаной (у проспекта две проезжие части: середина всего пути попала бы в конец)
    // Середина участка: рёбра графа — отдельные ломаные (у проспекта две проезжие части). Берём ребро,
    // чья середина ближе всего к центру всего участка, и ставим значок на его середину — значок всегда на линии.
    function midOf(d) {
      var mids = d.split("M").filter(Boolean).map(function (q) {
        var p = el("path", { d: "M" + q }, defs);
        var pt = p.getPointAtLength(p.getTotalLength() / 2);
        defs.removeChild(p);
        return [pt.x, pt.y];
      });
      var c = mids.reduce(function (s, m) { return [s[0] + m[0] / mids.length, s[1] + m[1] / mids.length]; }, [0, 0]);
      return mids.reduce(function (best, m) { return Math.hypot(m[0] - c[0], m[1] - c[1]) < Math.hypot(best[0] - c[0], best[1] - c[1]) ? m : best; }, mids[0]);
    }
    function markSelected() {
      svg.querySelectorAll("[data-id]").forEach(function (n) {
        n.classList.toggle("is-selected", n.getAttribute("data-id") === selected);
        n.classList.toggle("is-dim", !!selected && n.getAttribute("data-id") !== selected);
      });
    }
    function select(id) { selected = id; markSelected(); }
    // Пульс при новой жалобе: кольцо 800 мс ×2 на цели.
    function flash(id) {
      var x = targets.filter(function (q) { return q.id === id; })[0];
      if (!x) return;
      var p = x.geom.point || (x.geom.d ? midOf(x.geom.d) : [x.geom.poly[0][0], x.geom.poly[0][1]]);
      var ring = el("circle", { cx: p[0], cy: p[1], r: 16, "class": "pm-pulse" }, gObj);
      setTimeout(function () { if (ring.parentNode) ring.parentNode.removeChild(ring); }, 1700);
    }
    // Подсветка выбора жителя (цвет бренда, не цвет тепловой карты).
    function highlight(geom) {
      while (gSel.firstChild) gSel.removeChild(gSel.firstChild);
      if (!geom) return;
      if (geom.d) { el("path", { d: geom.d, "class": "pm-sel-casing" }, gSel); el("path", { d: geom.d, "class": "pm-sel-line" }, gSel); }
      if (geom.poly) el("polygon", { points: geom.poly.map(function (p) { return p.join(","); }).join(" "), "class": "pm-sel-area" }, gSel);
      if (geom.point) el("circle", { cx: geom.point[0], cy: geom.point[1], r: 12, "class": "pm-sel-point" }, gSel);
      if (geom.pick) el("circle", { cx: geom.pick[0], cy: geom.pick[1], r: 5, "class": "pm-pick" }, gSel);
      if (geom.approx) el("circle", { cx: geom.approx[0], cy: geom.approx[1], r: 150 / S.m_per_unit / 2, "class": "pm-sel-approx" }, gSel);
    }
    function setPickMode(on) { picking = !!on; svg.classList.toggle("is-picking", picking); }
    if (opts.soft) svg.classList.add("heat-soft");
    applyView();
    root.addEventListener("resize", applyView);
    return {
      render: render, select: select, flash: flash, highlight: highlight, setPickMode: setPickMode,
      zoomIn: function () { zoom(1.4); }, zoomOut: function () { zoom(1 / 1.4); },
      setSoft: function (on) { svg.classList.toggle("heat-soft", !!on); },
      svg: svg,
    };
  }

  // Ближайшие цели к точке (для шага ② жителя): расстояние в метрах по единицам макета.
  function nearest(targets, p, limit) {
    function distTo(x) {
      if (x.geom.point) return Math.hypot(x.geom.point[0] - p.x, x.geom.point[1] - p.y);
      if (x.geom.poly) {
        var c = x.geom.poly.reduce(function (s, q) { return [s[0] + q[0] / x.geom.poly.length, s[1] + q[1] / x.geom.poly.length]; }, [0, 0]);
        return Math.hypot(c[0] - p.x, c[1] - p.y);
      }
      // расстояние до ломаной участка
      var nums = x.geom.d.match(/-?[\d.]+/g).map(Number), best = Infinity;
      for (var i = 0; i + 3 < nums.length; i += 2) {
        var ax = nums[i], ay = nums[i + 1], bx = nums[i + 2], by = nums[i + 3];
        var dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy;
        var tt = L ? Math.max(0, Math.min(1, ((p.x - ax) * dx + (p.y - ay) * dy) / L)) : 0;
        best = Math.min(best, Math.hypot(ax + tt * dx - p.x, ay + tt * dy - p.y));
      }
      return best;
    }
    return targets.map(function (x) { return { target: x, distance_m: Math.round(distTo(x) * S.m_per_unit) }; })
      .filter(function (c) { return c.distance_m <= 250; })
      .sort(function (a, b) { return a.distance_m - b.distance_m; })
      .slice(0, limit || 3);
  }

  // Общая шапка макетов: Birge, (поиск), разделы, роль, ҚАЗ/РУС. page: "map" | "day" | "complaint".
  function header(host, page, opts) {
    opts = opts || {};
    host.className = "bk-header";
    host.innerHTML =
      '<a class="bk-header__brand" href="index.html" style="color:inherit;text-decoration:none"><span class="bk-header__mark">' + UI.icon("building") +
      '</span><span class="bk-header__brand-text" data-i18n="common.app_name"></span></a>' +
      (opts.search ? '<div class="bk-search bk-header__search">' + UI.icon("search") +
        '<input type="search" id="pm-search" data-i18n-attr="placeholder:' + (root.matchMedia("(max-width: 1023px)").matches ? "common.search.short" : "common.search.placeholder") + ';aria-label:common.search.label" /></div>' : "") +
      (opts.nav ? '<nav class="bk-seg bk-header__wide" aria-label="Birge"><a class="pm-nav" href="akimat-map.html" ' + (page === "map" ? 'aria-current="page"' : "") +
        ' data-i18n="common.nav.map"></a><a class="pm-nav" href="day.html" ' + (page === "day" ? 'aria-current="page"' : "") + ' data-i18n="common.nav.day"></a></nav>' : "") +
      '<div class="bk-header__end">' + (opts.role ? '<div class="bk-seg bk-header__wide" id="pm-role" role="group" data-i18n-attr="aria-label:common.role.label">' +
        '<button type="button" value="akimat" aria-pressed="true" data-i18n="common.role.akimat"></button>' +
        '<button type="button" value="resident" aria-pressed="false" data-i18n="common.role.resident"></button></div>' : "") +
      '<div id="pm-lang"></div></div>';
    UI.langSwitch(host.querySelector("#pm-lang"));
    I.apply(host);
  }

  // Плашка «Это макет» — честно: данные примеры, улицы OSM.
  function banner(host) {
    host.className = "pm-banner";
    host.setAttribute("role", "note");
    host.innerHTML = '<span class="bk-tag bk-tag--demo" data-i18n="common.tag.demo"></span> <span class="pm-banner__text" data-i18n="proto.banner"></span>';
    I.apply(host);
  }

  // Небольшая задержка для показа скелетона (как будто ответ сервера).
  function later(ms, fn) { return setTimeout(fn, ms); }

  function query(name) {
    var m = location.search.match(new RegExp("[?&]" + name + "=([^&]+)"));
    return m ? decodeURIComponent(m[1]) : null;
  }

  root.BirgeProto = {
    demoTargets: demoTargets, levelOf: levelOf, label: label, shortLabel: shortLabel, typeLabel: typeLabel,
    createMap: createMap, nearest: nearest, header: header, banner: banner, later: later, query: query,
  };
})(window);
