/*
 * Birge · «Картина недели» (R08, раунд 15) — отчёт для совещания акимата: 1–2 листа A4, ru / kk.
 *
 * Страница web/civic/akim/week.html (ссылка «Картина недели» внизу «Картины дня»), или
 * BirgeWeek.mount(элемент, { apiBase: "/api/civic/v2" }) → { destroy, refresh }.
 * Данные: GET {apiBase}/akim/week?date=YYYY-MM-DD&district=<id> — только сотруднику (ui/civic_akim/week.py).
 * Неделя — понедельник…воскресенье по Астане; идущая неделя считается до текущего момента. Числа считает сервер,
 * здесь только показ. Без картинок (поправка П1): числа, полосы, текст.
 * На экране — панель «Эта неделя / Прошлая неделя · район · ҚАЗ/РУС · Распечатать · ← Картина дня»; при печати — только лист.
 */
(function (root) {
  "use strict";

  var doc = root.document;
  var scriptBase = ((doc.currentScript && doc.currentScript.src) || "").replace(/[^/]*$/, "");
  var ICONS = scriptBase + "../ui-kit/icons.svg";
  var DEFAULTS = { apiBase: "/api/civic/v2", dayHref: "/#day", timeoutMs: 15000 };
  var DISTRICTS = ["almaty", "baikonur", "esil", "nura", "saraishyk", "saryarka"];
  var ASTANA_OFFSET_MS = 5 * 3600 * 1000;
  var DAYS = { ru: ["пн", "вт", "ср", "чт", "пт", "сб", "вс"], kk: ["дс", "сс", "ср", "бс", "жм", "сб", "жс"] };

  // Тексты: словарь R11 (BirgeI18n), нет ключа — этот запас (ключи week.* переданы R11 в INTEGRATION R08 §7).
  var FALLBACK = {
    ru: {
      "week.title": "Картина недели",
      "week.this": "Эта неделя",
      "week.prev": "Прошлая неделя",
      "week.back": "← Картина дня",
      "week.district": "Район",
      "week.city": "Весь город",
      "week.generated": "Сформировано {date}",
      "week.current": "неделя идёт — данные по {date}",
      "week.kpi.new": "Поступило обращений",
      "week.kpi.fixed": "Исправлено за неделю",
      "week.kpi.verified": "проверено жителями: {n}",
      "week.kpi.in_progress": "В работе на {date}",
      "week.kpi.overdue": "Просрочено на {date}",
      "week.delta.week": ", чем неделей раньше",
      "week.delta.week_before": "",
      "week.delta.ago": ", чем неделю назад",
      "week.delta.ago_before": "",
      "week.delta.new_short": "новое",
      "week.delta.col": "к прошлой неделе",
      "week.days.title": "Обращения по дням",
      "week.days.new": "поступило",
      "week.days.fixed": "исправлено",
      "week.summary": "Коротко",
      "week.heat_note": "Как тепловая карта за 7 дней на {date}: сколько человек сообщили о нерешённом",
      "week.neighbors": "Службы и жители — состояние на {date}",
      "week.agencies": "Ведомства",
      "week.agencies.lagging": "Больше всего просроченных ответов: {list}",
      "week.agencies.joint": "Совместных обращений: {n}",
      "week.agencies.handoffs": "Передач между службами: {n}",
      "week.together": "Жители вместе",
      "week.together.done": "Сделано вместе: {n}",
      "week.together.neighbors": "Соседей участвовало: {n}",
      "week.together.upcoming": "Впереди дел: {n} · записались: {m}",
      "week.meetings": "Поручения встреч с жителями",
      "week.meetings.counts": "Сделано {done} из {total} · просрочено {overdue}",
      "week.meetings.due": "срок {date}",
      "week.decisions": "Нужно решение акима",
      "week.decisions.overdue": "просрочено на {n} дн.",
      "week.overdue": "Просрочено дольше всех",
      "week.overdue.row": "{place} · {service} · просрочено на {n} дн.",
      "week.forecast.week": "Прогноз на неделю",
      "week.forecast.month": "Прогноз на месяц",
      "week.forecast.badge": "прототип",
      "week.forecast.note": "Прототип: модель обучена на синтетической истории, это не настоящая оценка риска.",
      "week.footer": "Birge · Картина недели. Числа посчитаны программой по данным платформы, без ручной правки.",
      "week.footer_demo": "«Пример» — синтетические данные для показа: жалобы придуманы, улицы и остановки — OpenStreetMap.",
      "week.empty": "За эту неделю обращений нет",
      "week.state.loading": "Собираем картину недели…",
      "week.state.forbidden": "Картина недели — для сотрудников акимата",
      "week.state.forbidden_hint": "В Birge: аватар → «Для сотрудников», затем «Картина дня» → «Картина недели».",
      "week.state.error": "Не удалось загрузить данные",
      "week.state.error_hint": "Проверьте связь с сервером и повторите.",
      "week.state.not_ready": "«Картина недели» ещё не подключена в этой сборке",
      "week.nodata": "Пока нет данных",
    },
    kk: {
      "week.title": "Апта қорытындысы",
      "week.this": "Осы апта",
      "week.prev": "Өткен апта",
      "week.back": "← Күн қорытындысы",
      "week.district": "Аудан",
      "week.city": "Бүкіл қала",
      "week.generated": "Жасалған уақыты: {date}",
      "week.current": "апта жүріп жатыр — {date} дейінгі деректер",
      "week.kpi.new": "Түскен өтініштер",
      "week.kpi.fixed": "Апта ішінде түзетілді",
      "week.kpi.verified": "тұрғындар тексерді: {n}",
      "week.kpi.in_progress": "{date} жағдайы: орындалуда",
      "week.kpi.overdue": "{date} жағдайы: мерзімі өткен",
      "week.delta.week": "",
      "week.delta.week_before": "алдыңғы аптадан ",
      "week.delta.ago": "",
      "week.delta.ago_before": "бір апта бұрынғыдан ",
      "week.delta.new_short": "жаңа",
      "week.delta.col": "өткен аптамен салыстырғанда",
      "week.days.title": "Күндер бойынша өтініштер",
      "week.days.new": "түсті",
      "week.days.fixed": "түзетілді",
      "week.summary": "Қысқаша",
      "week.heat_note": "{date} жағдайы бойынша соңғы 7 күндегі жылу картасы: шешілмеген мәселе туралы хабарлаған адам саны",
      "week.neighbors": "Қызметтер мен тұрғындар — {date} жағдайы",
      "week.agencies": "Ведомстволар",
      "week.agencies.lagging": "Жауап мерзімі өткені көп: {list}",
      "week.agencies.joint": "Бірлескен өтініштер: {n}",
      "week.agencies.handoffs": "Қызметтер арасында берілгені: {n}",
      "week.together": "Тұрғындар бірге",
      "week.together.done": "Бірге атқарылды: {n}",
      "week.together.neighbors": "Қатысқан көршілер: {n}",
      "week.together.upcoming": "Алдағы істер: {n} · жазылғандар: {m}",
      "week.meetings": "Тұрғындармен кездесу тапсырмалары",
      "week.meetings.counts": "Орындалды {done}/{total} · мерзімі өткені {overdue}",
      "week.meetings.due": "мерзімі {date}",
      "week.decisions": "Әкімнің шешімі керек",
      "week.decisions.overdue": "мерзімі {n} күнге өтті",
      "week.overdue": "Ең ұзақ кешіккендер",
      "week.overdue.row": "{place} · {service} · мерзімі {n} күнге өтті",
      "week.forecast.week": "Апталық болжам",
      "week.forecast.month": "Айлық болжам",
      "week.forecast.badge": "прототип",
      "week.forecast.note": "Прототип: модель синтетикалық тарихта оқытылған, бұл нақты тәуекел бағасы емес.",
      "week.footer": "Birge · Апта қорытындысы. Сандарды платформа деректері бойынша бағдарлама есептеді, қолмен түзетілмеген.",
      "week.footer_demo": "«Үлгі» — көрсетуге арналған синтетикалық деректер: шағымдар ойдан құрастырылған, көшелер мен аялдамалар — OpenStreetMap.",
      "week.empty": "Бұл аптада өтініш жоқ",
      "week.state.loading": "Апта қорытындысы жиналуда…",
      "week.state.forbidden": "Апта қорытындысы — әкімдік қызметкерлеріне арналған",
      "week.state.forbidden_hint": "Birge-де: аватар → «Қызметкерлерге», содан кейін «Күн қорытындысы» → «Апта қорытындысы».",
      "week.state.error": "Деректер жүктелмеді",
      "week.state.error_hint": "Сервермен байланысты тексеріп, қайталаңыз.",
      "week.state.not_ready": "«Апта қорытындысы» бұл жинақта әлі қосылмаған",
      "week.nodata": "Әзірге дерек жоқ",
    },
  };
  var SHARED = {
    ru: { "common.demo": "Пример", "common.action.print": "Распечатать", "common.action.retry": "Повторить",
      "common.lang.label": "Язык интерфейса", "common.lang.ru": "РУС", "common.lang.kk": "ҚАЗ",
      "akim.topics.title": "Темы", "akim.districts.title": "Районы", "akim.hot.title": "Горячие места",
      "akim.delta.same": "без изменений", "akim.delta.new": "неделей раньше не было",
      "akim.delta.more": "больше на {v}", "akim.delta.less": "меньше на {v}",
      "akim.delta.ratio": { one: "в {n} раз больше", few: "в {n} раза больше", many: "в {n} раз больше" } },
    kk: { "common.demo": "Үлгі", "common.action.print": "Басып шығару", "common.action.retry": "Қайталау",
      "common.lang.label": "Интерфейс тілі", "common.lang.ru": "РУС", "common.lang.kk": "ҚАЗ",
      "akim.topics.title": "Тақырыптар", "akim.districts.title": "Аудандар", "akim.hot.title": "Шағымы көп орындар",
      "akim.delta.same": "өзгеріс жоқ", "akim.delta.new": "бұрын болмаған", "akim.delta.more": "{v} артық",
      "akim.delta.less": "{v} кем", "akim.delta.ratio": "{n} есе көп" },
  };

  function I() { return root.BirgeI18n || null; }
  function lang() { return I() && I().getLang ? I().getLang() : "ru"; }
  function num(n) { return I() && I().formatNumber ? I().formatNumber(n) : String(n); }
  function pluralRu(n) {
    var a = Math.abs(Number(n));
    if (a % 1 !== 0) return "few";
    if (a % 10 === 1 && a % 100 !== 11) return "one";
    if (a % 10 >= 2 && a % 10 <= 4 && (a % 100 < 12 || a % 100 > 14)) return "few";
    return "many";
  }
  function interpolate(text, params) {
    return String(text).replace(/\{(\w+)\}/g, function (whole, name) {
      if (!params || params[name] == null) return whole;
      return typeof params[name] === "number" ? num(params[name]) : String(params[name]);
    });
  }
  function tr(key, params) {
    var B = I();
    if (B && B.has && B.has(key)) return B.t(key, params);
    var l = lang(), v;
    [FALLBACK[l], SHARED[l], FALLBACK.ru, SHARED.ru].some(function (d) {
      if (d && Object.prototype.hasOwnProperty.call(d, key)) { v = d[key]; return true; }
      return false;
    });
    if (v == null) return key;
    if (typeof v === "object") {
      var n = params && params.n != null ? params.n : 0;
      v = l === "ru" ? v[pluralRu(n)] || v.many : v.other || v.many || v.one;
    }
    return interpolate(v, params);
  }
  function catName(id) {
    var B = I();
    if (B && B.cat) { var c = B.cat(id); if (c && c !== id) return c; }
    return id || "";
  }
  function districtName(id) {
    var B = I();
    return id && B && B.has && B.has("district." + id) ? B.t("district." + id) : id || "";
  }
  function pick(obj, base) {
    if (!obj) return "";
    return obj[base + "_" + lang()] || obj[base + "_ru"] || obj[base + "_kk"] || "";
  }
  function fmtDate(iso) { return I() && I().formatDate ? I().formatDate(iso) : iso; }
  function fmtDateTime(iso) { return I() && I().formatDateTime ? I().formatDateTime(iso) : iso; }

  function h(tag, attrs, children) {
    var el = doc.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v == null || v === false) return;
        if (k === "text") el.textContent = v;
        else if (k === "class") el.className = v;
        else if (k.slice(0, 2) === "on" && typeof v === "function") el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? "" : String(v));
      });
    }
    (children || []).forEach(function (c) {
      if (c == null || c === false) return;
      el.appendChild(typeof c === "string" || typeof c === "number" ? doc.createTextNode(String(c)) : c);
    });
    return el;
  }
  var SVG = "http://www.w3.org/2000/svg";
  function svg(tag, attrs) {
    var el = doc.createElementNS(SVG, tag);
    Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    return el;
  }
  function icon(name, cls) {
    var s = svg("svg", { class: "ic" + (cls ? " " + cls : ""), "aria-hidden": "true", focusable: "false" });
    s.appendChild(svg("use", { href: ICONS + "#i-" + name }));
    return s;
  }

  // Изменение: «больше на 12 %, чем неделей раньше» / kk «алдыңғы аптадан 12 % артық»; при базе < 10 — в штуках.
  function ratioText(n) {
    if (n % 1 === 0 || lang() !== "ru") return tr("akim.delta.ratio", { n: n });
    var probe = tr("akim.delta.ratio", { n: 2 });
    return probe.indexOf(num(2)) >= 0 ? probe.replace(num(2), num(n)) : tr("akim.delta.ratio", { n: n });
  }
  function deltaText(ch, which) {
    if (!ch || ch.trend === "flat" || ch.trend == null) return tr("akim.delta.same");
    if (ch.mode === "new") return tr("akim.delta.new");
    var before = tr("week.delta." + which + "_before"), after = tr("week.delta." + which);
    if (ch.mode === "ratio") return before + ratioText(ch.ratio) + after;
    var v = ch.mode === "pct" ? (I() && I().formatPercent ? I().formatPercent(ch.pct) : num(ch.pct) + " %") : num(ch.abs);
    return before + tr(ch.trend === "up" ? "akim.delta.more" : "akim.delta.less", { v: v }) + after;
  }

  // Компактное изменение для строк отчёта: «+38 %», «−17 %», «+5», «×2,3», «новое»; знак и число — не только цвет.
  function deltaCompact(ch) {
    if (!ch || ch.trend === "flat" || ch.trend == null) return "=";
    if (ch.mode === "new") return tr("week.delta.new_short");
    if (ch.mode === "ratio") return "×" + num(ch.ratio);
    var sign = ch.trend === "up" ? "+" : "−";
    return sign + (ch.mode === "pct" ? num(ch.pct) + " %" : num(ch.abs));
  }

  function todayAstana() { return new Date(Date.now() + ASTANA_OFFSET_MS).toISOString().slice(0, 10); }
  function shiftDay(iso, days) {
    var d = new Date(iso + "T12:00:00Z");
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
  }

  function mount(rootEl, options) {
    var opts = {};
    Object.keys(DEFAULTS).forEach(function (k) { opts[k] = options && options[k] != null ? options[k] : DEFAULTS[k]; });
    var params = new URLSearchParams(root.location.search);
    var state = {
      date: /^\d{4}-\d{2}-\d{2}$/.test(params.get("date") || "") ? params.get("date") : null,
      district: DISTRICTS.indexOf(params.get("district")) >= 0 ? params.get("district") : null,
      data: null, status: "loading", request: 0,
    };
    rootEl.classList.add("wk");

    // Панель на экране (на бумаге её нет): неделя, район, язык, печать, назад.
    var bar = h("div", { class: "wk-bar" });
    var sheet = h("article", { class: "wk-sheet", "aria-live": "polite" });
    rootEl.replaceChildren(bar, sheet);

    function renderBar() {
      var isPrev = !!state.date;
      var seg = h("div", { class: "bk-seg wk-weeks", role: "group" }, [
        h("button", { type: "button", "aria-pressed": String(!isPrev), text: tr("week.this"), onclick: function () { setDate(null); } }),
        h("button", { type: "button", "aria-pressed": String(isPrev), text: tr("week.prev"),
          onclick: function () { setDate(shiftDay(todayAstana(), -7)); } }),
      ]);
      var select = h("select", { class: "bk-select wk-select", "aria-label": tr("week.district"),
        onchange: function (e) { setDistrict(e.target.value || null); } },
        [h("option", { value: "", text: tr("week.city") })].concat(DISTRICTS.map(function (id) {
          return h("option", { value: id, text: districtName(id), selected: id === state.district });
        })));
      var langs = h("div", { class: "bk-seg", role: "group", "aria-label": tr("common.lang.label") }, ["kk", "ru"].map(function (l) {
        return h("button", { type: "button", lang: l, "aria-pressed": String(lang() === l), text: tr("common.lang." + l),
          onclick: function () { if (I() && I().setLang) I().setLang(l); } });
      }));
      bar.replaceChildren(
        h("a", { class: "bk-btn bk-btn--ghost wk-back", href: opts.dayHref }, [tr("week.back")]),
        seg, select, langs,
        h("button", { type: "button", class: "bk-btn bk-btn--primary wk-print", onclick: function () { root.print(); } },
          [icon("print"), tr("common.action.print")])
      );
    }

    function section(cls, title, children, extra) {
      return h("section", { class: "wk-sec " + cls }, [h("h2", { class: "wk-h2" }, [title, extra || null])].concat(children));
    }
    function kpiTile(label, value, sub, note, mod) {
      return h("div", { class: "wk-kpi" + (mod ? " wk-kpi--" + mod : "") }, [
        h("p", { class: "wk-kpi__label", text: label }),
        h("p", { class: "wk-kpi__value", text: value == null ? "—" : num(value) }),
        sub ? h("p", { class: "wk-kpi__sub", text: sub }) : null,
        note ? h("p", { class: "wk-kpi__note", text: note }) : null,
      ]);
    }
    // Столбики по дням: поступило (тёмные) и исправлено (зелёные — только «исправлено»); будущие дни — пусто.
    function daysChart(k, week) {
      var news = k.new.series || [], fixed = k.fixed.series || [];
      var max = Math.max.apply(null, news.concat(fixed).map(function (v) { return v || 0; }).concat([1]));
      var W = 700, H = 124, top = 20, bottom = 22, col = W / 7, bw = 28;
      var chart = svg("svg", { class: "wk-chart", viewBox: "0 0 " + W + " " + H, role: "img",
        "aria-label": tr("week.days.title") + ": " + news.map(function (v, i) { return DAYS[lang() === "kk" ? "kk" : "ru"][i] + " " + (v == null ? "—" : v); }).join(", ") });
      var startDay = new Date(week.start + "T12:00:00Z");
      for (var i = 0; i < 7; i++) {
        var x = i * col + col / 2, base = H - bottom;
        var d = new Date(startDay.getTime() + i * 86400000);
        var label = DAYS[lang() === "kk" ? "kk" : "ru"][i] + " " + d.getUTCDate();
        var t = svg("text", { x: x, y: H - 6, class: "wk-chart__day", "text-anchor": "middle" });
        t.textContent = label;
        chart.appendChild(t);
        if (news[i] == null) {
          chart.appendChild(svg("line", { x1: x - bw, x2: x + bw, y1: base, y2: base, class: "wk-chart__future" }));
          continue;
        }
        var hn = ((news[i] || 0) / max) * (H - top - bottom), hf = ((fixed[i] || 0) / max) * (H - top - bottom);
        chart.appendChild(svg("rect", { x: x - bw + 2, y: base - hn, width: bw - 4, height: Math.max(hn, 1), rx: 3, class: "wk-chart__new" }));
        chart.appendChild(svg("rect", { x: x + 2, y: base - hf, width: bw - 4, height: Math.max(hf, 1), rx: 3, class: "wk-chart__fixed" }));
        var vn = svg("text", { x: x - bw / 2, y: base - hn - 6, class: "wk-chart__val", "text-anchor": "middle" });
        vn.textContent = num(news[i] || 0);
        chart.appendChild(vn);
        if (fixed[i]) {
          var vf = svg("text", { x: x + bw / 2, y: base - hf - 6, class: "wk-chart__val wk-chart__val--fixed", "text-anchor": "middle" });
          vf.textContent = num(fixed[i]);
          chart.appendChild(vf);
        }
      }
      var legend = h("p", { class: "wk-legend" }, [
        h("span", { class: "wk-legend__key wk-legend__key--new", "aria-hidden": "true" }), tr("week.days.new"),
        h("span", { class: "wk-legend__key wk-legend__key--fixed", "aria-hidden": "true" }), tr("week.days.fixed"),
      ]);
      return [chart, legend];
    }
    function bars(items, label, limit) {
      var max = Math.max.apply(null, items.map(function (r) { return r.value || 0; }).concat([1]));
      return h("ol", { class: "wk-bars" }, items.slice(0, limit).map(function (r) {
        return h("li", { class: "wk-bars__row" }, [
          h("span", { class: "wk-bars__name", text: label(r) }),
          h("span", { class: "wk-bars__track" }, [h("span", { class: "wk-bars__fill", style: "width:" + Math.round(((r.value || 0) / max) * 100) + "%" })]),
          h("span", { class: "wk-bars__num", text: num(r.value || 0) }),
          h("span", { class: "wk-bars__delta", "data-trend": r.trend, text: deltaCompact(r) }),
        ]);
      }));
    }
    function list(items) {
      return h("ul", { class: "wk-list" }, items.map(function (x) { return h("li", {}, x); }));
    }

    function renderSheet() {
      var d = state.data, k = d.kpi, w = d.week, l = lang();
      var year = (w.start || "").slice(0, 4);
      var asOf = w["as_of_label_" + l] || w.as_of_label_ru;
      var scope = d.district ? (d.district[l] || d.district.ru) : tr("week.city");
      var demoAll = d.demo && d.demo.any;
      var head = h("header", { class: "wk-head" }, [
        h("div", { class: "wk-head__main" }, [
          h("p", { class: "wk-brand" }, [h("span", { class: "wk-brand__mark", "aria-hidden": "true", text: "B" }), "Birge"]),
          h("h1", { class: "wk-title", text: tr("week.title") + " · " + (w["label_" + l] || w.label_ru) + " " + year }),
          h("p", { class: "wk-meta", text: [scope, w.current ? tr("week.current", { date: asOf }) : null,
            tr("week.generated", { date: fmtDateTime(d.generated_at) })].filter(Boolean).join(" · ") }),
        ]),
        demoAll ? h("span", { class: "bk-tag bk-tag--demo", text: tr("common.demo") }) : null,
      ]);
      var kpis = h("section", { class: "wk-kpis" }, [
        kpiTile(tr("week.kpi.new"), k.new.value, deltaText(k.new, "week"), null, "new"),
        kpiTile(tr("week.kpi.fixed"), k.fixed.value, deltaText(k.fixed, "week"),
          k.verification_available ? tr("week.kpi.verified", { n: k.fixed.verified || 0 }) : null, "fixed"),
        kpiTile(tr("week.kpi.in_progress", { date: asOf }), k.in_progress.value, deltaText(k.in_progress, "ago"), null),
        kpiTile(tr("week.kpi.overdue", { date: asOf }), k.overdue.value, deltaText(k.overdue, "ago"), null, k.overdue.value ? "late" : null),
      ]);
      var parts = [head, kpis];
      if (!k.new.value && !k.fixed.value && !k.in_progress.value && !k.overdue.value) {
        parts.push(h("p", { class: "wk-empty", text: tr("week.empty") }));
      }
      parts.push(section("wk-days", tr("week.days.title"), daysChart(k, w)));
      var sentences = (d.text && (d.text[l] || d.text.ru)) || [];
      if (sentences.length) parts.push(section("wk-text", tr("week.summary"), [h("p", { class: "wk-text__p", lang: l, text: sentences.join(" ") })]));

      var heatNote = h("p", { class: "wk-note", text: tr("week.heat_note", { date: asOf }) });
      var cols = [];
      if (d.topics && d.topics.available && (d.topics.items || []).length)
        cols.push(section("wk-topics", tr("akim.topics.title"), [bars(d.topics.items, function (r) { return catName(r.category) || r[l] || r.ru; }, 6)]));
      if (d.districts && d.districts.available && (d.districts.items || []).length)
        cols.push(section("wk-districts", tr("akim.districts.title"), [bars(d.districts.items, function (r) { return districtName(r.district) || r[l] || r.ru; }, 6)]));
      heatNote.textContent += " · " + tr("week.delta.col") + ": +/−";
      if (cols.length) parts.push(h("div", { class: "wk-cols" }, cols), heatNote);

      if (d.hot && d.hot.available && (d.hot.items || []).length) {
        parts.push(section("wk-hot", tr("akim.hot.title"), [h("ol", { class: "wk-hot__list" }, d.hot.items.slice(0, 5).map(function (it) {
          return h("li", { class: "wk-hot__row" }, [h("span", { class: "bk-heat wk-heat", "data-level": String(it.level || 0), text: num(it.count) }),
            h("span", { class: "wk-hot__name", text: pick(it.target, "label") || catName(it.category) }),
            h("span", { class: "wk-hot__sub", text: [catName(it.category), districtName(it.district)].filter(Boolean).join(" · ") })]);
        }))]));
      }

      // Соседи — только для идущей недели (они знают «сейчас»), с честной подписью «состояние на …».
      if (w.current) {
        var nb = [];
        var sv = d.services;
        if (sv && sv.available && (sv.items || []).length) {
          var rows = {};
          sv.items.forEach(function (r) { rows[r.service] = r; });
          var lag = (sv.lagging || []).filter(function (id) { return rows[id]; }).map(function (id) { return (l === "kk" ? rows[id].kk : rows[id].ru) + " — " + num(rows[id].overdue || 0); });
          nb.push(h("div", { class: "wk-card" }, [h("h3", { class: "wk-h3", text: tr("week.agencies") }), list([
            lag.length ? [tr("week.agencies.lagging", { list: lag.join(", ") })] : null,
            sv.joint && sv.joint.week != null ? [tr("week.agencies.joint", { n: sv.joint.week })] : null,
            sv.handoffs && sv.handoffs.week != null ? [tr("week.agencies.handoffs", { n: sv.handoffs.week })] : null,
          ].filter(Boolean))]));
        }
        var tg = d.together;
        if (tg && tg.available) {
          var c = tg.counts || {};
          nb.push(h("div", { class: "wk-card" }, [h("h3", { class: "wk-h3", text: tr("week.together") }), list([
            c.done != null ? [tr("week.together.done", { n: c.done })] : null,
            c.neighbors_done != null ? [tr("week.together.neighbors", { n: c.neighbors_done })] : null,
            c.upcoming != null ? [tr("week.together.upcoming", { n: c.upcoming, m: c.joined_upcoming || 0 })] : null,
          ].filter(Boolean))]));
        }
        var mt = d.meetings;
        if (mt && mt.available && (mt.counts || {}).total) {
          var mc = mt.counts;
          nb.push(h("div", { class: "wk-card" }, [h("h3", { class: "wk-h3", text: tr("week.meetings") }), list(
            [[tr("week.meetings.counts", { done: mc.done || 0, total: mc.total, overdue: mc.overdue || 0 })]].concat(
              (mt.orders || []).slice(0, 2).map(function (o) {
                return [h("span", { class: "wk-list__main", text: pick(o, "text") }),
                  h("span", { class: "wk-list__sub" + (o.overdue ? " wk-late" : ""), text: o.due ? tr("week.meetings.due", { date: fmtDate(o.due) }) : "" })];
              })))]));
        }
        if (nb.length) parts.push(section("wk-neighbors", tr("week.neighbors", { date: asOf }), [h("div", { class: "wk-trio", "data-count": String(nb.length) }, nb)]));
      }

      var dec = d.decisions && d.decisions.available ? d.decisions.items || [] : [];
      var od = d.overdue_places && d.overdue_places.items ? d.overdue_places.items : [];
      var low = [];
      if (dec.length)
        low.push(section("wk-decisions", tr("week.decisions"), [list(dec.map(function (it) {
          var opt = (it.options || []).map(function (o) { return o.n + ") " + (l === "kk" ? o.kk : o.ru); }).join("  ");
          return [h("span", { class: "wk-list__main", text: pick(it, "problem") }),
            h("span", { class: "wk-list__sub", text: [it.place ? it.place[l] || it.place.ru : null,
              it.overdue_by ? tr("week.decisions.overdue", { n: it.overdue_by }) : null].filter(Boolean).join(" · ") }),
            opt ? h("span", { class: "wk-list__sub", text: opt }) : null];
        }))]));
      if (od.length)
        low.push(section("wk-overdue", tr("week.overdue"), [list(od.slice(0, 5).map(function (it) {
          var svc = it.service ? (l === "kk" ? it.service.kk : it.service.ru) : "";
          var place = (l === "kk" ? it.place_kk : it.place_ru) || it.place_ru || catName(it.category);
          return [h("span", { class: "wk-list__main", text: place }),
            h("span", { class: "wk-list__sub", text: [svc, it.timer ? tr("week.decisions.overdue", { n: it.timer.overdue_by }) : null].filter(Boolean).join(" · ") })];
        }))]));
      if (low.length) parts.push(h("div", { class: "wk-cols" }, low));

      var f = d.forecast;
      if (f && f.available && (f.items || []).length) {
        parts.push(section("wk-forecast", tr(f.horizon === "week" ? "week.forecast.week" : "week.forecast.month"), [
          list(f.items.slice(0, 3).map(function (it) {
            return [h("span", { class: "wk-list__main", text: pick(it, "label") || districtName(it.district) }),
              h("span", { class: "wk-list__sub", text: [districtName(it.district), pick(it, "reason")].filter(Boolean).join(" · ") })];
          })),
          h("p", { class: "wk-note", text: pick(f, "method") || tr("week.forecast.note") }),
        ], h("span", { class: "bk-tag wk-proto", text: tr("week.forecast.badge") })));
      }
      parts.push(h("footer", { class: "wk-foot" }, [h("p", { text: tr("week.footer") }), demoAll ? h("p", { text: tr("week.footer_demo") }) : null]));
      sheet.replaceChildren.apply(sheet, parts);
      doc.title = tr("week.title") + " · " + (w["label_" + l] || w.label_ru) + " · Birge";
    }

    function renderState(kind) {
      var title, hint, action = null, name;
      if (kind === "loading") {
        sheet.replaceChildren(h("p", { class: "wk-boot", text: tr("week.state.loading") }));
        return;
      }
      if (kind === "forbidden") { name = "user"; title = tr("week.state.forbidden"); hint = tr("week.state.forbidden_hint");
        action = h("a", { class: "bk-btn", href: opts.dayHref }, [tr("week.back")]); }
      else if (kind === "not_ready") { name = "info"; title = tr("week.state.not_ready"); hint = "";
        action = h("a", { class: "bk-btn", href: opts.dayHref }, [tr("week.back")]); }
      else { name = "wifi-off"; title = tr("week.state.error"); hint = tr("week.state.error_hint");
        action = h("button", { type: "button", class: "bk-btn", onclick: function () { load(); } }, [icon("refresh"), tr("common.action.retry")]); }
      // П1: маленький монохромный значок + короткий текст + одна кнопка.
      sheet.replaceChildren(h("div", { class: "bk-error wk-state", role: "alert" }, [icon(name, "wk-state__ic"),
        h("p", { class: "bk-error__title", text: title }), hint ? h("p", { class: "bk-error__text", text: hint }) : null, action]));
    }

    function render() {
      renderBar();
      rootEl.setAttribute("data-state", state.status);
      rootEl.setAttribute("aria-busy", String(state.status === "loading"));
      if (state.status === "ok" && state.data) renderSheet();
      else renderState(state.status);
    }

    function syncUrl() {
      if (!root.history || !root.history.replaceState) return;
      var p = new URLSearchParams(root.location.search);
      if (state.date) p.set("date", state.date); else p.delete("date");
      if (state.district) p.set("district", state.district); else p.delete("district");
      root.history.replaceState(null, "", root.location.pathname + (p.toString() ? "?" + p : ""));
    }
    function setDate(v) { state.date = v; syncUrl(); load(); }
    function setDistrict(v) { state.district = v; syncUrl(); load(); }

    function load() {
      var id = ++state.request;
      state.status = "loading";
      render();
      var q = new URLSearchParams();
      if (state.date) q.set("date", state.date);
      if (state.district) q.set("district", state.district);
      var ctrl = root.AbortController ? new AbortController() : null;
      var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, opts.timeoutMs);
      fetch(opts.apiBase + "/akim/week" + (q.toString() ? "?" + q : ""), { headers: { Accept: "application/json" },
        credentials: "same-origin", signal: ctrl ? ctrl.signal : undefined })
        .then(function (r) {
          return r.json().catch(function () { return null; }).then(function (b) { return { status: r.status, body: b }; });
        })
        .then(function (res) {
          clearTimeout(timer);
          if (id !== state.request) return;
          if (res.status === 200 && res.body && res.body.kpi) { state.data = res.body; state.status = "ok"; }
          else if (res.status === 401 || res.status === 403) state.status = "forbidden";
          else if (res.status === 404 || res.status === 503) state.status = "not_ready";
          else state.status = "error";
          render();
        })
        .catch(function () {
          clearTimeout(timer);
          if (id !== state.request) return;
          state.status = "error";
          render();
        });
    }

    var off = I() && I().onChange ? I().onChange(render) : null;
    if (I() && I().ready && I().ready.then) I().ready.then(load, load);
    else load();
    return {
      refresh: load,
      destroy: function () { if (off) off(); state.request++; rootEl.replaceChildren(); },
    };
  }

  root.BirgeWeek = { mount: mount, version: "week-r15" };
  function auto() {
    var el = doc.querySelector("[data-week-auto]");
    if (el && !el.__week) el.__week = mount(el, { apiBase: el.getAttribute("data-api") || undefined });
  }
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", auto);
  else auto();
})(window);
